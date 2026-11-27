"""ซ่อมเป้าหมายจากถ้อยคำของผู้เล่น: แก้คำสั่งที่ LLM ตีความผิดในรอบเล่นจริง โดยไม่ไปเปลี่ยนคำสั่งที่ถูกอยู่แล้ว

ทดสอบโดยไม่เรียก API: ใช้ผลที่ LLM ตอบผิดจริงในรอบเล่นทดสอบเป็นข้อมูลตั้งต้น
แล้วตรวจที่สถานะเกมของขั้นนั้นจริง (เล่น walkthrough ด้วยกฎจนถึงขั้นนั้น)
"""
import json
from pathlib import Path

import pytest

import app.main as main
from app.cases import get_engine
from app.neural.repair import repair_parsed_command
from app.schemas import ActionType, ParsedCommand

ROOT = Path(__file__).resolve().parents[1]
CASES = {
    "case_01_gideon": ("walkthrough.json", "natural-rollout-texts-A-v3.json"),
    "case_02_vincent": ("walkthrough_case_02.json", "natural-rollout-texts-B-v2.json"),
    "case_03_liora": ("walkthrough_case_03.json", "natural-rollout-texts-C-v2.json"),
}


def to_command(step, raw=""):
    action, target, *rest = step
    fields = {"action": ActionType(action), "target": target, "raw_text": raw, "confidence": 1.0}
    if rest:
        if action == "interrogate":
            fields["topic"] = rest[0]
        elif rest[0].isdigit():
            fields["code"] = rest[0]
        else:
            fields["instrument"] = rest[0]
    return ParsedCommand(**fields)


def states_before_each_step(case_id):
    """[state ก่อนทำขั้นที่ 1, ก่อนขั้นที่ 2, ...] จากการเล่น walkthrough ด้วยกฎล้วน"""
    engine = get_engine(case_id)
    steps = json.loads((ROOT / "data" / CASES[case_id][0]).read_text(encoding="utf-8"))["steps"]
    state = main.new_game_state(engine.world, case_id=case_id)
    states = []
    for step in steps:
        states.append(state)
        decision = engine.decide(to_command(step), state)
        assert decision.allowed, (case_id, step, decision.message)
        state = main.apply_changes(state, decision.state_changes)
    return steps, states


def repair(case_id, step_no, parsed):
    _, states = states_before_each_step(case_id)
    fixed, note = repair_parsed_command(parsed, get_engine(case_id).world, state=states[step_no - 1],
                                        raw_text=parsed.raw_text)
    return fixed, note


# ---------- what the LLM actually returned in live runs, and what it should have been ----------

MISREADS = [
    # (case, step, player text, LLM output, expected)
    ("case_01_gideon", 11, "กระเป๋าสำนวนขาดแฟ้มไหนไป",
     dict(action="examine", target="dossier_bag"), ("examine", "dossier_missing_file_c")),
    ("case_02_vincent", 11, "ขอดูสารบัญกับแฟ้ม C ในกระเป๋าหน่อย",
     dict(action="sequence", alternatives=["examine dossier_missing_file_c", "examine file_c_initials"]),
     ("examine", "dossier_missing_file_c")),
    ("case_03_liora", 11, "ขอดูสารบัญกับแฟ้ม C ในกระเป๋าหน่อย",
     dict(action="sequence", alternatives=["examine dossier_missing_file_c", "examine file_c"]),
     ("examine", "dossier_missing_file_c")),
    ("case_02_vincent", 17, "ขอดูแฟ้มประวัติการรักษาในห้องแพทย์หน่อย",
     dict(action="examine", target="liora_patient_log"), ("examine", "secret_file")),
    ("case_03_liora", 17, "ขอดูแฟ้มประวัติการรักษาในห้องแพทย์หน่อย",
     dict(action="examine", target="liora_patient_log"), ("examine", "secret_file")),
    ("case_02_vincent", 37, "กระดาษในกระเป๋าเสื้อเขาเขียนว่าอะไร",
     dict(action="examine", target=None), ("examine", "mara_job_note")),
    ("case_03_liora", 37, "กระดาษในกระเป๋าเสื้อเขาเขียนว่าอะไร",
     dict(action="examine", target="cassian_reed"), ("examine", "mara_job_note")),
    ("case_03_liora", 36, "คราบเลือดบนแขนเสื้อวินเซนต์เป็นยังไง",
     dict(action="interrogate", target="vincent_gray", topic="arrival"), ("examine", "vincent_blood")),
]


@pytest.mark.parametrize("case_id, step_no, text, llm, expected", MISREADS)
def test_observed_misreads_are_repaired(case_id, step_no, text, llm, expected):
    parsed = ParsedCommand(raw_text=text, confidence=0.9, **{**llm, "action": ActionType(llm["action"])})
    fixed, note = repair(case_id, step_no, parsed)
    assert (fixed.action.value, fixed.target) == expected, note
    assert note
    assert not fixed.alternatives


# ---------- correct readings must pass through unchanged ----------

def walkthrough_cases():
    for case_id, (_, texts_file) in CASES.items():
        texts = json.loads((ROOT / "data" / "research" / texts_file).read_text(encoding="utf-8"))["cases"]
        for entry in texts:
            yield case_id, entry["step"], entry["text"]


@pytest.mark.parametrize("case_id, step_no, text", list(walkthrough_cases()))
def test_correct_readings_are_left_alone(case_id, step_no, text):
    steps, states = states_before_each_step(case_id)
    expected = to_command(steps[step_no - 1], raw=text)
    fixed, _ = repair_parsed_command(expected, get_engine(case_id).world, state=states[step_no - 1], raw_text=text)
    assert (fixed.action, fixed.target) == (expected.action, expected.target), (text, fixed.repair_note)


def test_asking_a_person_about_an_object_stays_a_question():
    parsed = ParsedCommand(action=ActionType.INTERROGATE, target="vincent_gray", topic="blackout",
                           raw_text="ถามวินเซนต์เรื่องคราบเลือดบนแขนเสื้อวินเซนต์", confidence=0.9)
    fixed, _ = repair("case_03_liora", 36, parsed)
    assert (fixed.action, fixed.target) == (ActionType.INTERROGATE, "vincent_gray")


def test_vague_wording_does_not_override_the_llm():
    """'ตรวจกระเป๋า' ตรงกับกระเป๋าสองใบพอๆ กัน ต้องไม่เลือกแทน LLM"""
    parsed = ParsedCommand(action=ActionType.EXAMINE, target="dossier_bag", raw_text="ตรวจกระเป๋าหน่อย", confidence=0.9)
    fixed, _ = repair("case_01_gideon", 11, parsed)
    assert fixed.target == "dossier_bag"


def test_hidden_objects_are_never_chosen():
    """เศษเอกสารไหม้ยังซ่อนอยู่ตอนเพิ่งเข้าห้องเกิดเหตุ ต่อให้ผู้เล่นเอ่ยชื่อเต็มก็ต้องไม่ถูกเลือก"""
    parsed = ParsedCommand(action=ActionType.EXAMINE, target=None, raw_text="ขอดูเศษเอกสารไหม้ไฟหน่อย", confidence=0.9)
    fixed, _ = repair("case_01_gideon", 4, parsed)
    assert fixed.target != "burnt_folder_c"


def test_two_named_objects_stay_a_sequence():
    """ผู้เล่นเอ่ยถึงของสองชิ้นจริง ต้องคงเป็นคำสั่งพ่วง ไม่รวมเหลือชิ้นเดียว"""
    parsed = ParsedCommand(action=ActionType.SEQUENCE, raw_text="ตรวจนาฬิกาพกกลไกกับกระดุมเย็บติดแขนเสื้อ",
                           alternatives=["examine pocket_watch", "examine obsidian_cufflink"], confidence=0.9)
    fixed, _ = repair("case_01_gideon", 5, parsed)
    assert fixed.action == ActionType.SEQUENCE and len(fixed.alternatives) == 2


@pytest.mark.parametrize("case_id", list(CASES))
def test_object_buttons_keep_their_target(case_id):
    """ปุ่มสำรวจในหน้าเว็บส่ง "ตรวจดู<ชื่อเต็ม>" ทุกชิ้นที่มองเห็นได้ทุกขั้นต้องได้เป้าหมายของตัวเอง"""
    engine = get_engine(case_id)
    world = engine.world
    _, states = states_before_each_step(case_id)
    for state in states:
        for oid, obj in world["objects"].items():
            if obj.get("location") != state.current_location or not engine.offerable(oid, state):
                continue
            text = "ตรวจดู" + obj["name_th"]
            parsed = ParsedCommand(action=ActionType.EXAMINE, target=oid, raw_text=text, confidence=1.0)
            fixed, note = repair_parsed_command(parsed, world, state=state, raw_text=text)
            assert fixed.target == oid, (case_id, oid, note)
