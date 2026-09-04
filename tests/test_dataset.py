"""
test_dataset.py — ตรวจว่า ground truth ใน data/commands.json ตรงกับกฎจริง

ชุดคำสั่งคือฐานของตัวเลขทุกตัวในงานวิจัย ถ้า label ผิดแม้ข้อเดียว ผลที่รายงานจะผิดตาม
เทสชุดนี้จึงตรวจ label ของกลุ่ม A/B กับ symbolic engine ทุกครั้งที่รัน
ไม่ต้องใช้ LLM
"""

import json
from pathlib import Path

import pytest

from app.scenario import CHECKPOINTS, checkpoint
from app.schemas import ActionType, GameState, ParsedCommand
from app.symbolic.engine import SymbolicEngine

DATA = Path(__file__).resolve().parents[1] / "data"

# ชุดคำสั่งผูกกับฉาก ถ้าฉากเปลี่ยน id ที่อ้างไว้ก็ใช้ไม่ได้ทันที
# แทนที่จะปล่อยให้พังแบบงงๆ ให้ข้ามพร้อมบอกเหตุผล แล้วกลับมาทำงานเองเมื่อมีชุดใหม่
if not (DATA / "commands.json").exists():
    pytest.skip(
        "ยังไม่มี data/commands.json สำหรับฉากปัจจุบัน "
        "ชุดเดิมของฉากเก่าถูกย้ายไปที่ data/archive/ แล้ว "
        "เขียนชุดใหม่ที่อ้าง id ของฉากปัจจุบัน แล้วเทสชุดนี้จะกลับมารันเอง",
        allow_module_level=True,
    )

DATASET = json.loads((DATA / "commands.json").read_text(encoding="utf-8"))
COMMANDS = DATASET["commands"]
RULE_IDS = {r["id"] for r in json.loads((DATA / "rules.json").read_text(encoding="utf-8"))["rules"]}
WORLD = json.loads((DATA / "story.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def engine():
    return SymbolicEngine()


def state_for(entry) -> GameState:
    s = checkpoint(entry["checkpoint"])
    return s.model_copy(update=entry["state_override"]) if entry.get("state_override") else s


DECIDABLE = [c for c in COMMANDS if c["group"] in ("A", "B")]


def test_ids_are_unique():
    ids = [c["id"] for c in COMMANDS]
    assert len(ids) == len(set(ids))


def test_every_group_is_present():
    groups = {c["group"] for c in COMMANDS}
    assert groups == {"A", "B", "C", "D"}


def test_every_checkpoint_exists():
    for c in COMMANDS:
        assert c["checkpoint"] in CHECKPOINTS, f"{c['id']} อ้าง checkpoint ที่ไม่มีอยู่"


def test_every_expected_rule_exists_in_rules_json():
    for c in COMMANDS:
        if c["expected_rule"]:
            assert c["expected_rule"] in RULE_IDS, f"{c['id']} อ้างกฎที่ไม่มีอยู่จริง"


@pytest.mark.parametrize("entry", DECIDABLE, ids=[c["id"] for c in DECIDABLE])
def test_label_matches_what_the_engine_actually_decides(entry, engine):
    """ground truth ของกลุ่ม A/B ต้องมาจากกฎ ไม่ใช่ความเห็นของคนเขียนชุดข้อมูล"""
    cmd = ParsedCommand(
        action=ActionType(entry["expected_action"]),
        target=entry["expected_target"],
        instrument=entry["expected_instrument"],
        raw_text=entry["text"],
        confidence=1.0,
    )
    d = engine.decide(cmd, state_for(entry))
    assert d.allowed == entry["expected_allowed"], (
        f"{entry['id']} label ว่า allowed={entry['expected_allowed']} "
        f"แต่ engine ตัดสินว่า {d.allowed}: {d.message}"
    )
    if entry["expected_rule"]:
        assert d.violated_rule_id == entry["expected_rule"], (
            f"{entry['id']} label ว่าตก {entry['expected_rule']} "
            f"แต่ engine ตกที่ {d.violated_rule_id}"
        )


def test_group_b_covers_every_rule_except_the_neural_one():
    """ทุกกฎต้องมีคำสั่งทดสอบ ไม่งั้นมีกฎที่ไม่เคยถูกวัดเลย

    R000 ตรวจ action ที่มาจากชั้น neural จึงถูกทดสอบด้วยกลุ่ม C/D แทน
    """
    covered = {c["expected_rule"] for c in COMMANDS if c["group"] == "B"}
    missing = RULE_IDS - covered - {"R000_KNOWN_ACTION"}
    assert not missing, f"กฎที่ยังไม่มีคำสั่งทดสอบ: {sorted(missing)}"
    assert any(c["expected_rule"] == "R000_KNOWN_ACTION" for c in COMMANDS if c["group"] in ("C", "D"))


def test_targets_refer_to_real_entities_or_are_deliberately_fake():
    """กลุ่ม A ต้องอ้าง id ที่มีจริงเสมอ ส่วนกลุ่ม B อ้าง id ปลอมได้เฉพาะเมื่อตั้งใจทดสอบกฎ *_EXISTS"""
    known = {*WORLD["locations"], *WORLD["objects"], *WORLD["suspects"]}
    for c in COMMANDS:
        for field in ("expected_target", "expected_instrument"):
            t = c.get(field)
            if not t:
                continue
            if c["group"] == "A":
                assert t in known, f"{c['id']} อ้าง id ที่ไม่มีอยู่จริง: {t}"
            elif t not in known:
                assert "EXISTS" in (c["expected_rule"] or ""), (
                    f"{c['id']} ใช้ id ปลอม '{t}' แต่ไม่ได้ทดสอบกฎ *_EXISTS"
                )


def test_group_c_and_d_expect_the_neural_layer_to_refuse():
    for c in COMMANDS:
        if c["group"] == "C":
            assert c["expected_action"] == "unknown"
            assert c["expected_allowed"] is False
        if c["group"] == "D":
            assert c["expected_action"] == "ambiguous"
            assert c["expected_allowed"] is False
