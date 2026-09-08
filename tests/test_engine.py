"""
test_engine.py — ทดสอบ Symbolic Engine ของ Nocturne Express 1938 โดยไม่ต้องใช้ LLM

รันด้วย:  python -m pytest -v
"""

import json
from pathlib import Path

import pytest

STEPS = [tuple(x) for x in json.loads(
    (Path(__file__).resolve().parents[1] / "data" / "walkthrough.json")
    .read_text(encoding="utf-8"))["steps"]]
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


# ---------- ชั้น Deduction ----------

def ev(engine, *ids) -> GameState:
    """สถานะที่ผู้เล่นเจอหลักฐานตามที่ระบุแล้ว ใช้ทดสอบตรรกะโดยไม่ต้องเดินทั้งเกม"""
    return GameState(current_location="lounge_car", discovered_evidence=list(ids))


def test_every_deduction_needs_all_of_its_evidence(engine):
    """ข้อสรุปทุกข้อต้องมีหลักฐานครบถึงจะสรุปได้ ขาดชิ้นเดียวก็ไม่ได้

    นี่คือ R-SYS-03 ในสเปก ถ้าข้อไหนสรุปได้ทั้งที่ขาดหลักฐาน แปลว่ามีทางลัดที่ไม่ควรมี
    """
    for did, cond in engine.world["deductions"].items():
        need = cond.get("requires_evidence", [])
        if not need:
            continue
        assert did not in engine.deductions(ev(engine, *need[:-1])),             f"{did} สรุปได้ทั้งที่ขาดหลักฐาน {need[-1]}"


def test_true_murder_window_is_what_unlocks_the_case(engine):
    """นาฬิกาไฟฟ้าอย่างเดียวไม่พอ ต้องมีนาฬิกาพกกับคำประเมินของแพทย์

    แก่นของคดีคือการลวงเวลาตาย ถ้าสรุปเวลาจริงได้จากนาฬิกาไฟฟ้าอย่างเดียว คดีก็ไม่มีปริศนา
    """
    D01 = "D01_TRUE_MURDER_WINDOW"
    assert D01 not in engine.deductions(ev(engine, "wall_clock"))
    assert D01 not in engine.deductions(ev(engine, "pocket_watch"))
    assert D01 in engine.deductions(ev(engine, "pocket_watch", "liora_time_estimate"))


def test_opportunity_needs_at_least_two_independent_links(engine):
    """R-OPP-01 การไม่มีที่อยู่บวกร่องรอยเดียวยังไม่พอ ต้องสองทางขึ้นไป"""
    D07 = "D07_GIDEON_IN_CASSIAN_ROOM"
    one_link = ev(engine, "gideon_no_early_alibi",
                  "obsidian_cufflink", "gideon_missing_button")
    assert D07 not in engine.deductions(one_link)

    two_links = ev(engine, "gideon_no_early_alibi",
                   "obsidian_cufflink", "gideon_missing_button",
                   "wax_seal_imprint", "gideon_signet_ring")
    assert D07 in engine.deductions(two_links)


def test_no_alibi_alone_never_proves_opportunity(engine):
    """ไม่มีที่อยู่ ไม่ใช่หลักฐานว่าอยู่ในห้อง"""
    assert "D07_GIDEON_IN_CASSIAN_ROOM" not in engine.deductions(ev(engine, "gideon_no_early_alibi"))


# ---------- ฉากจบ ----------

ALL_EVIDENCE = None


def all_evidence(engine):
    return [o for o, v in engine.world["objects"].items() if v["type"] == "evidence"]


def test_walkthrough_reaches_the_true_ending(engine):
    s = run_walkthrough(engine)
    assert s.ending_id == "true_ending"


def test_true_ending_needs_the_other_two_suspects_cleared(engine):
    """ชี้ถูกคนอย่างเดียวไม่พอ ต้องตัดอีกสองคนออกด้วยหลักฐาน ไม่ใช่ด้วยความรู้สึก"""
    full = ev(engine, *all_evidence(engine))
    assert engine.ending_for("gideon_hart", full)["id"] == "true_ending"

    for drop in ("vincent_blackout_confession", "liora_patient_witness"):
        short = ev(engine, *[x for x in all_evidence(engine) if x != drop])
        assert engine.ending_for("gideon_hart", short)["id"] != "true_ending",             f"ขาด {drop} แล้วยังได้ฉากจบแท้"


def test_cold_justice_is_right_suspect_but_unproven_case(engine):
    """สามเสาครบแต่หลักฐานสนับสนุนไม่ครบ ต้องได้ฉากจบขมขื่น ไม่ใช่ฉากจบแท้"""
    short = ev(engine, *[x for x in all_evidence(engine) if x != "gideon_sleeve_soot"])
    assert engine.ending_for("gideon_hart", short)["id"] == "cold_justice"


def test_scapegoat_only_happens_before_the_timeline_is_broken(engine):
    """กล่าวหาวินเซนต์เป็นความผิดพลาดเชิงเหตุผล ไม่ใช่ผลของหลักฐาน

    ถ้าผู้เล่นหักล้างเวลาตายลวงตาไปแล้ว ความผิดพลาดนั้นหายไป
    การกล่าวหาเขาจึงไม่ควรได้ฉากจบเดิมอีก
    """
    ignorant = ev(engine, "vincent_blood", "wire_cutters", "wall_clock")
    assert engine.ending_for("vincent_gray", ignorant)["id"] == "the_scapegoat"

    knows_time = ev(engine, "vincent_blood", "wire_cutters",
                    "pocket_watch", "liora_time_estimate")
    assert engine.ending_for("vincent_gray", knows_time)["id"] != "the_scapegoat"


def test_paranoia_trap_treats_a_secret_as_if_it_were_proof(engine):
    ignorant = ev(engine, "secret_file", "liora_medical_access", "wall_clock")
    assert engine.ending_for("dr_liora_venn", ignorant)["id"] == "the_paranoia_trap"


def test_only_the_culprit_can_ever_close_the_case(engine):
    """ต่อให้เจอหลักฐานครบทุกชิ้น คนที่ไม่ใช่คนร้ายก็ต้องไม่ได้ฉากจบที่นับว่าคลี่คลาย

    SUSPICION != PROOF ตามที่สเปกเขียนไว้
    """
    full = ev(engine, *all_evidence(engine))
    for sid in engine.world["suspects"]:
        solved = engine.ending_for(sid, full).get("solved", False)
        assert solved == (sid == "gideon_hart"), f"{sid} ให้ผล solved={solved}"


def test_accusation_is_allowed_but_recorded_as_unproven(engine):
    """กล่าวหาได้เสมอ แต่กฎสี่เสาต้องบันทึกตามจริงว่ายังไม่ครบ

    ถ้าบล็อกไปเลย ฉากจบที่เป็นความผิดพลาดของผู้เล่นจะไปไม่ถึง
    แต่ถ้าไม่บันทึก ผู้เล่นก็ไม่รู้ว่าคดีอ่อนตรงไหน
    """
    d = engine.decide(cmd(ActionType.ACCUSE, "gideon_hart"), GameState())
    assert d.allowed
    step = next(x for x in d.reasoning_chain if x.rule_id == "R013_ACCUSE_FOUR_PILLARS")
    assert not step.passed
    assert "ขาดเสา" in step.description
