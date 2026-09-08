"""
test_engine.py — ทดสอบ Symbolic Engine ของ Nocturne Express 1938 โดยไม่ต้องใช้ LLM

รันด้วย:  python -m pytest -v
"""

import pytest

from app.scenario import STEPS
from app.schemas import ActionType, ParsedCommand, GameState
from app.symbolic.engine import SECONDS_PER_TURN, SymbolicEngine, apply_changes


@pytest.fixture
def engine():
    return SymbolicEngine()


def cmd(action, target=None, instrument=None, text="(mock)"):
    return ParsedCommand(action=action, target=target, instrument=instrument,
                         raw_text=text, confidence=1.0)


# เส้นทางเฉลยอยู่ใน data/walkthrough.json ที่เดียว
FULL_WALKTHROUGH = [(ActionType(a), t) for a, t in STEPS]


def run_walkthrough(engine, steps=None) -> GameState:
    s = GameState()
    for action, target in (steps or FULL_WALKTHROUGH):
        d = engine.decide(cmd(action, target), s)
        assert d.allowed, f"{action.value} {target} ควรผ่านแต่ถูกปฏิเสธ: {d.message}"
        s = apply_changes(s, d.state_changes)
    return s


@pytest.fixture
def solved(engine):
    return run_walkthrough(engine)


# ---------- กลุ่ม A: คำสั่งที่ถูกกฎ ----------

def test_move_to_open_car(engine):
    assert engine.decide(cmd(ActionType.MOVE, "first_class_car"), GameState()).allowed


def test_examine_evidence_in_same_car(engine):
    s = apply_changes(GameState(), {"move_to": "first_class_car"})
    d = engine.decide(cmd(ActionType.EXAMINE, "pocket_watch"), s)
    assert d.allowed
    assert d.state_changes["discovered_evidence_add"] == "pocket_watch"


def test_full_walkthrough_is_completable(engine):
    """เส้นทางหลักของเกมต้องเดินได้จนจบ — กันกฎที่ขัดกันเองจนเกมตัน"""
    s = run_walkthrough(engine)
    assert len(s.discovered_evidence) >= 5
    assert s.ending_id == "true_ending"


def test_cannot_examine_evidence_in_another_car(engine):
    # ยืนอยู่ตู้เลานจ์ (lounge_car) แต่จะตรวจนาฬิกาพกในตู้ 4 (first_class_car) ต้องไม่ผ่าน
    d = engine.decide(cmd(ActionType.EXAMINE, "pocket_watch"), GameState())
    assert not d.allowed
    assert d.violated_rule_id == "R005_SAME_LOCATION"


def test_unknown_object_denied(engine):
    d = engine.decide(cmd(ActionType.EXAMINE, "non_existent_item"), GameState())
    assert not d.allowed
    assert d.violated_rule_id == "R002_TARGET_EXISTS"


def test_time_limit_enforced(engine):
    s = GameState(elapsed_seconds=5460)  # เกิน 5400 วินาที
    d = engine.decide(cmd(ActionType.MOVE, "first_class_car"), s)
    assert not d.allowed
    assert d.violated_rule_id == "R014_TIME_LIMIT"


def test_accuse_vincent_triggers_bad_ending_a(engine):
    s = run_walkthrough(engine, steps=[
        (ActionType.MOVE, "second_class_car"),
        (ActionType.EXAMINE, "wire_cutters"),
        (ActionType.ACCUSE, "vincent_gray")
    ])
    assert s.ending_id == "bad_ending_a"


def test_accuse_liora_triggers_bad_ending_b(engine):
    s = run_walkthrough(engine, steps=[
        (ActionType.MOVE, "first_class_car"),
        (ActionType.EXAMINE, "secret_file"),
        (ActionType.ACCUSE, "dr_liora_venn")
    ])
    assert s.ending_id == "bad_ending_b"


def test_accuse_gideon_with_flexible_evidence(engine):
    """กล่าวหา Gideon โดยมีหลักฐานกายภาพ 3 ใน 5 ชิ้น + หักล้างเวลาตาย -> True Ending"""
    s = run_walkthrough(engine, steps=[
        (ActionType.MOVE, "first_class_car"),
        (ActionType.EXAMINE, "pocket_watch"),      # หักล้างเวลาตาย (20:25)
        (ActionType.EXAMINE, "burnt_folder_c"),   # ชิ้นที่ 1
        (ActionType.EXAMINE, "second_teacup"),    # ชิ้นที่ 2
        (ActionType.EXAMINE, "wax_seal_imprint"), # ชิ้นที่ 3 (ได้ 3 ชิ้นครบตามโควตา)
        (ActionType.ACCUSE, "gideon_hart")
    ])
    assert s.ending_id == "true_ending"


def test_accuse_gideon_with_insufficient_evidence_triggers_tragic_ending(engine):
    """กล่าวหา Gideon โดยมีหลักฐานกายภาพไม่ถึง 3 ชิ้น -> Tragic Ending"""
    s = run_walkthrough(engine, steps=[
        (ActionType.MOVE, "first_class_car"),
        (ActionType.EXAMINE, "pocket_watch"),      # หักล้างเวลาตาย
        (ActionType.EXAMINE, "burnt_folder_c"),   # ชิ้นที่ 1 เท่านั้น
        (ActionType.ACCUSE, "gideon_hart")
    ])
    assert s.ending_id == "tragic_ending"
