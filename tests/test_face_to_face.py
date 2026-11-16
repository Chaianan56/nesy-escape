"""Talking to Vincent face to face is also looking at him: "ทำไมเสื้อมีรอยเลือด" must not be hidden."""
import pytest
from app.cases import get_engine
from app.game_setup import new_game_state
from app.schemas import ActionType, ParsedCommand
from app.symbolic.engine import apply_changes

CASES = ['case_01_gideon', 'case_02_vincent', 'case_03_liora']


def cmd(action, target, topic=None):
    return ParsedCommand(action=action, target=target, raw_text='(test)', confidence=1.0,
                         **({'topic': topic} if topic else {}))


@pytest.mark.parametrize('case', CASES)
def test_interrogating_vincent_lets_you_see_his_sleeve(case):
    engine = get_engine(case)
    state = new_game_state(engine.world, case).model_copy(update={'current_location': 'second_class_car'})
    assert not engine.decide(cmd(ActionType.EXAMINE, 'vincent_blood'), state).allowed

    talk = engine.decide(cmd(ActionType.INTERROGATE, 'vincent_gray', 'arrival'), state)
    assert talk.allowed
    state = apply_changes(state, talk.state_changes)
    assert engine.decide(cmd(ActionType.EXAMINE, 'vincent_blood'), state).allowed


@pytest.mark.parametrize('case', CASES)
def test_asking_vincent_about_the_blood(case):
    """"แกเป็นใคร แล้วทำไมเสื้อมีรอยเลือด" แตกเป็นถามสองครั้ง ครั้งที่สองต้องได้เรื่องเลือด ไม่ใช่คำตอบเดิมซ้ำ"""
    engine = get_engine(case)
    state = new_game_state(engine.world, case).model_copy(update={'current_location': 'second_class_car'})
    first = engine.decide(cmd(ActionType.INTERROGATE, 'vincent_gray'), state)
    state = apply_changes(state, first.state_changes)
    second = engine.decide(cmd(ActionType.INTERROGATE, 'vincent_gray'), state)
    assert second.allowed and second.message != first.message
    assert 'แผล' in second.message
    state = apply_changes(state, second.state_changes)
    assert 'vincent_blood' in state.discovered_evidence
    assert engine.decide(cmd(ActionType.INTERROGATE, 'vincent_gray', 'blood'), state).allowed
