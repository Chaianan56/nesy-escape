"""
test_neural.py — ทดสอบ Neuro AI Layer ของ Nocturne Express 1938

แบ่งเป็นสองชั้น:
1. ทดสอบที่ไม่ต้องใช้ API Key — preprocessor, prompt builder, fallback parser
   และการต่อท่อ neural -> symbolic ชั้นนี้ต้องผ่านเสมอใน CI
2. ทดสอบที่ต้องเรียก Gemini จริง — ถูก skip อัตโนมัติเมื่อไม่มี GEMINI_API_KEY

รันด้วย:  python -m pytest -v
"""

import os
import re

import pytest

from app.schemas import ActionType, GameState, ParsedCommand
from app.neural import interpret, decide_autonomously, preprocess_text
from app.neural.gemini_client import STORY_DATA, RULES_DATA, NeuralUnavailable, llm_online
from app.neural.prompts import build_interpret_system_prompt, build_baseline_decision_prompt
from app.symbolic.engine import SymbolicEngine

needs_llm = pytest.mark.skipif(not llm_online(), reason="ไม่มี GEMINI_API_KEY จึงข้ามการทดสอบที่เรียก LLM จริง")


def llm_call(fn, *args):
    os.environ["NEURAL_STRICT"] = "1"
    try:
        return fn(*args)
    except NeuralUnavailable as e:
        pytest.skip(f"เรียก LLM ไม่ได้: {str(e)[:120]}")
    finally:
        os.environ.pop("NEURAL_STRICT", None)


# ---------- Preprocessor ----------

def test_preprocessor_thai():
    feat = preprocess_text("  ลอง ตรวจสอบ   pocket_watch  ")
    assert feat.language in ("th", "mixed")
    assert feat.normalized_text == "ลอง ตรวจสอบ pocket_watch"
    assert feat.tokens


def test_preprocessor_english():
    feat = preprocess_text("examine pocket_watch")
    assert feat.language in ("en", "mixed")
    assert "pocket_watch" in feat.normalized_text


# ---------- Prompt builders ----------

def test_entity_grounding_prompt_lists_every_id():
    """ทุก id ในโลกต้องอยู่ใน prompt ไม่งั้น LLM จะ ground ไม่ได้"""
    prompt = build_interpret_system_prompt(STORY_DATA)
    for group in ("locations", "objects", "suspects"):
        for eid in STORY_DATA[group]:
            assert f"'{eid}'" in prompt, f"{eid} หายไปจาก grounding table"
    assert "FEW-SHOT EXAMPLES" in prompt


def test_rules_injection_prompt_builder():
    prompt = build_baseline_decision_prompt(RULES_DATA, STORY_DATA)
    for rule in RULES_DATA["rules"]:
        assert rule["id"] in prompt


# ---------- Fallback parser (ไม่ต้องใช้ API Key) ----------

def fallback(text: str, state: GameState = None) -> ParsedCommand:
    from app.neural.gemini_client import _fallback_parse
    state = state or GameState()
    return _fallback_parse(text, preprocess_text(text).normalized_text, state)


@pytest.mark.parametrize("text, action, target", [
    ("examine pocket_watch", ActionType.EXAMINE, "pocket_watch"),
    ("move first_class_car", ActionType.MOVE, "first_class_car"),
    ("ตรวจดูนาฬิกาพกกลไก", ActionType.EXAMINE, "pocket_watch"),
    ("เดินไปที่ตู้โดยสารชั้นหนึ่ง", ActionType.MOVE, "first_class_car"),
    ("ขอสอบปากคำกิเดียน ฮาร์ตหน่อย", ActionType.INTERROGATE, "gideon_hart"),
    ("กล่าวหากิเดียน ฮาร์ต", ActionType.ACCUSE, "gideon_hart"),
])
def test_fallback_parses_action_and_grounds_target(text, action, target):
    cmd = fallback(text)
    assert cmd.action == action
    assert cmd.target == target
    assert cmd.raw_text == text


def test_fallback_marks_command_without_target_as_ambiguous():
    cmd = fallback("เปิดมันหน่อย")
    assert cmd.action == ActionType.AMBIGUOUS
    assert cmd.alternatives


def test_fallback_marks_out_of_scope_as_unknown():
    cmd = fallback("ร้องเพลงให้ฟังหน่อย")
    assert cmd.action == ActionType.UNKNOWN


def test_fallback_treats_look_around_as_examining_the_current_car():
    cmd = fallback("ดูรอบๆ", GameState(current_location="first_class_car"))
    assert cmd.action == ActionType.EXAMINE
    assert cmd.target == "first_class_car"


def test_move_never_grounds_to_a_non_location():
    cmd = fallback("เดินไปที่ตู้เลานจ์")
    assert cmd.target in STORY_DATA["locations"]


# ---------- สัญญาระหว่างสองเลเยอร์ ----------

def test_parsed_command_carries_no_permission_field():
    fields = set(ParsedCommand.model_fields)
    assert not fields & {"allowed", "permitted", "valid", "decision"}


def cmd(action, target=None):
    return ParsedCommand(action=action, target=target, raw_text="", confidence=1.0)


def test_neural_output_is_consumable_by_symbolic_engine():
    engine = SymbolicEngine()
    state = GameState()

    denied = engine.decide(cmd(ActionType.EXAMINE, "pocket_watch"), state)
    assert not denied.allowed

    allowed = engine.decide(cmd(ActionType.MOVE, "first_class_car"), state)
    assert allowed.allowed


def test_symbolic_always_explains_itself(engine=None):
    eng = SymbolicEngine()
    for action, target in [(ActionType.EXAMINE, "pocket_watch"),
                           (ActionType.MOVE, "first_class_car"),
                           (ActionType.ACCUSE, "gideon_hart"),
                           (ActionType.UNKNOWN, None)]:
        d = eng.decide(ParsedCommand(action=action, target=target, raw_text="", confidence=0.5),
                       GameState())
        assert d.reasoning_chain, f"{action.value} คืนสายเหตุผลว่าง"


def test_prompt_says_who_the_victim_is():
    assert STORY_DATA.get("victim_name_th"), "story.json ต้องระบุชื่อผู้ตายไว้"
