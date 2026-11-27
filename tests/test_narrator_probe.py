"""สคริปต์วัดผู้เล่าเรื่อง (scripts/run_narrator_probe.py) เล่นได้ครบทั้งสามคดี ทดสอบโดยไม่เรียก API จริง"""
import json
from pathlib import Path

import pytest

import app.main as main
from app.neural import narrator
from app.schemas import ActionType, ParsedCommand
from scripts import run_narrator_probe as probe

ROOT = Path(__file__).resolve().parents[1]
WALKTHROUGHS = {"A": "walkthrough.json", "B": "walkthrough_case_02.json", "C": "walkthrough_case_03.json"}


def test_importing_the_probe_leaves_the_narrator_setting_alone(monkeypatch):
    """ถ้า import แล้วเปิด NARRATOR เทสต์อื่นทั้งชุดจะเรียก API จริงเมื่อมีคีย์ในเครื่อง"""
    import importlib
    import os
    monkeypatch.delenv("NARRATOR", raising=False)
    importlib.reload(probe)
    assert "NARRATOR" not in os.environ


@pytest.mark.parametrize("case", ["A", "B", "C"])
def test_turns_cover_the_walkthrough_with_bait_turns_inserted(case):
    doc = json.loads(probe.CASES[case][1].read_text(encoding="utf-8"))
    turns = probe.build_turns(case)
    walk = [text for kind, text in turns if kind == "walkthrough"]
    assert walk == [c["text"] for c in doc["cases"]]
    extras = [i for i, (kind, _) in enumerate(turns) if kind == "extra"]
    assert extras, "every case should include off-path turns"
    for i in extras:  # an extra turn always sits right before a walkthrough turn
        assert turns[i + 1][0] == "walkthrough"


@pytest.mark.parametrize("case", ["B", "C"])
def test_case_texts_match_their_walkthrough(case):
    doc = json.loads(probe.CASES[case][1].read_text(encoding="utf-8"))
    steps = json.loads((ROOT / "data" / WALKTHROUGHS[case]).read_text(encoding="utf-8"))["steps"]
    assert doc["case_id"] == probe.CASES[case][0]
    assert [c["step"] for c in doc["cases"]] == list(range(1, len(steps) + 1))
    for entry, step in zip(doc["cases"], steps):
        expected = entry["expected_command"]
        assert (expected["action"], expected["target"]) == (step[0], step[1]), entry["step"]
        if len(step) > 2:
            assert step[2] in (expected.get("topic"), expected.get("code"), expected.get("instrument")), entry["step"]
        assert entry["text"].strip()


def test_summary_counts_verdicts_and_ending():
    rows = [
        {"narration": {"provider": "fake"}, "action": "examine", "service_error": None, "ending": None,
         "checks": [{"source": "ก", "reply": "ก", "reason": None}, {"source": "ข", "reply": "x", "reason": "new_number"}]},
        {"narration": {}, "action": "unknown", "service_error": "unavailable", "ending": "true_ending", "checks": []},
    ]
    summary = probe.summarize(rows)
    assert summary["verdicts"] == {"accepted": 1, "new_number": 1}
    assert summary["reject_rate"] == 0.5
    assert summary["accepted_identical_to_engine"] == 1
    assert summary["narrator_skipped"] == 1
    assert summary["parsed_unknown"] == 1
    assert summary["service_errors"] == 1
    assert summary["ending"] == "true_ending"


@pytest.mark.parametrize("case", ["A", "B", "C"])
def test_play_case_runs_every_turn_in_its_own_case(monkeypatch, case):
    monkeypatch.setattr(main, "interpret", lambda text, state, **k: ParsedCommand(
        action=ActionType.UNKNOWN, raw_text=text, confidence=0.0))
    monkeypatch.setattr(main, "narrator_enabled", lambda: True)
    monkeypatch.setattr(narrator, "_generate", lambda sources, player_text, provider: (list(sources), "fake:model"))
    rows = probe.play_case(case, [], pause=0, quota_wait=0)
    assert len(rows) == len(probe.build_turns(case))
    assert all(r["service_error"] is None for r in rows)
    assert all(r["narration"].get("provider") == "fake:model" for r in rows)
