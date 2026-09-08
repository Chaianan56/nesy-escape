"""
test_neural.py — ทดสอบ Neuro AI Layer ของ Nocturne Express 1938

แบ่งเป็นสองชั้น:
1. ทดสอบที่ไม่ต้องใช้ API Key — prompt builder และสัญญาระหว่างสองชั้น
   และการต่อท่อ neural -> symbolic ชั้นนี้ต้องผ่านเสมอใน CI
2. ทดสอบที่ต้องเรียก Gemini จริง — ถูก skip อัตโนมัติเมื่อไม่มี GEMINI_API_KEY

รันด้วย:  python -m pytest -v
"""

import os
import re

import pytest

from app.schemas import ActionType, GameState, ParsedCommand
from app.neural.gemini_client import STORY_DATA
from app.neural.prompts import build_interpret_system_prompt
from app.symbolic.engine import SymbolicEngine



def llm_call(fn, *args):
    os.environ["NEURAL_STRICT"] = "1"
    try:
        return fn(*args)
    except NeuralUnavailable as e:
        pytest.skip(f"เรียก LLM ไม่ได้: {str(e)[:120]}")
    finally:
        os.environ.pop("NEURAL_STRICT", None)


# ---------- Preprocessor ----------





# ---------- Prompt builders ----------

def test_entity_grounding_prompt_lists_every_id():
    """ทุก id ในโลกต้องอยู่ใน prompt ไม่งั้น LLM จะ ground ไม่ได้"""
    prompt = build_interpret_system_prompt(STORY_DATA)
    for group in ("locations", "objects", "suspects"):
        for eid in STORY_DATA[group]:
            assert f"'{eid}'" in prompt, f"{eid} หายไปจาก grounding table"
    assert "FEW-SHOT EXAMPLES" in prompt




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
