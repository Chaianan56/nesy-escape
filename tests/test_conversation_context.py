import json
import os

import pytest

from app.cases import get_engine
from app.game_setup import new_game_state
from app.neural.prompts import build_interpret_system_prompt
from app.schemas import ActionType, ParsedCommand


QUESTION = 'คุณอยู่ที่ไหนตอนเกิดเหตุ'
CASES = ['case_01_gideon', 'case_02_vincent', 'case_03_liora']


@pytest.mark.parametrize('location,expected', [
    ('lounge_car', ['gideon_hart']),
    ('dining_car_staff', ['car_attendant', 'patient_witness']),
    ('engine_room', []),
])
@pytest.mark.parametrize('case_id', CASES)
def test_prompt_identifies_local_addressees_without_guessing(location, expected, case_id):
    world = get_engine(case_id).world
    state = new_game_state(world, case_id).model_copy(
        update={'current_location': location})
    prompt = build_interpret_system_prompt(
        world, state=state, user_text=QUESTION, use_knn=False)
    context = prompt.split('[ผู้สนทนาในสถานที่ปัจจุบัน]\n', 1)[1].split('\n', 1)[0].strip()
    data = json.loads(context)
    assert data['local_people'] == expected
    assert data['implicit_addressee'] == (expected[0] if len(expected) == 1 else None)
    assert data['location_known'] is True


def test_prompt_without_state_does_not_assign_an_addressee():
    prompt = build_interpret_system_prompt(get_engine('case_01_gideon').world, use_knn=False)
    context = prompt.split('[ผู้สนทนาในสถานที่ปัจจุบัน]\n', 1)[1].split('\n', 1)[0].strip()
    data = json.loads(context)
    assert data['location_known'] is False
    assert data['implicit_addressee'] is None


@pytest.mark.parametrize('case_id', CASES)
def test_gideon_account_is_a_valid_question_but_still_requires_presence(case_id):
    engine = get_engine(case_id)
    state = new_game_state(engine.world, case_id)
    parsed = ParsedCommand(action=ActionType.INTERROGATE, target='gideon_hart',
                           topic='account', raw_text=QUESTION)
    assert engine.decide(parsed, state).allowed
    elsewhere = state.model_copy(update={'current_location': 'first_class_car'})
    assert not engine.decide(parsed, elsewhere).allowed


@pytest.mark.llm
@pytest.mark.skipif(os.getenv('RUN_CONVERSATION_LIVE') != '1',
                    reason='Requires explicit opt-in to send game context to the model provider')
@pytest.mark.parametrize('question', [QUESTION, 'ตอนนั้นคุณทำอะไรอยู่'])
@pytest.mark.parametrize('case_id', CASES)
def test_live_gideon_question_uses_local_person_and_account_topic(question, case_id):
    # Call the neural parser directly: a typed shortcut must not masquerade as a live test.
    from app.neural.gemini_client import interpret

    engine = get_engine(case_id)
    state = new_game_state(engine.world, case_id)
    parsed = interpret(question, state, provider='gemini')
    print(json.dumps({'case': case_id, 'question': question, 'action': parsed.action.value,
                      'target': parsed.target, 'topic': parsed.topic}, ensure_ascii=False))
    assert (parsed.action, parsed.target, parsed.topic) == (
        ActionType.INTERROGATE, 'gideon_hart', 'account')
    assert engine.decide(parsed, state).allowed


@pytest.mark.parametrize('case_id', CASES)
@pytest.mark.parametrize('question', [
    'คุณอยู่ที่ไหนตอนไฟดับ', 'คุณอยู่ไหนตอนไฟดับ',
    'ตอนไฟดับคุณอยู่ที่ไหน', 'คุณอยู่ที่ไหนตอนเกิดเหตุ',
    'คุณอยู่ที่ไหนตอนไฟดับครับ?', 'คุณ อยู่ ที่ไหน ตอน ไฟดับ',
])
def test_single_alibi_question_does_not_become_sequence(monkeypatch, case_id, question):
    from app.neural import gemini_client
    from app.neural.typed_commands import interpret_game

    def remote_forbidden(*args, **kwargs):
        raise AssertionError('A clear local account question must not call the model')

    monkeypatch.setattr(gemini_client, 'interpret', remote_forbidden)
    engine = get_engine(case_id)
    state = new_game_state(engine.world, case_id)
    parsed = interpret_game(question, state)
    assert (parsed.action, parsed.target, parsed.topic) == (
        ActionType.INTERROGATE, 'gideon_hart', 'blackout' if 'ไฟดับ' in question else 'account')
    assert not parsed.sequence and not parsed.alternatives
    assert parsed.parser_mode == 'typed'
    assert engine.decide(parsed, state).allowed


@pytest.mark.parametrize('location', ['dining_car_staff', 'engine_room', 'first_class_car', 'second_class_car'])
def test_alibi_shortcut_needs_unique_person_with_account_topic(location):
    from app.neural.typed_commands import parse_typed_command
    engine = get_engine(CASES[0])
    state = new_game_state(engine.world).model_copy(update={'current_location': location})
    assert parse_typed_command('คุณอยู่ที่ไหนตอนไฟดับ', state, engine.world) is None


@pytest.mark.parametrize('question', [
    'อย่าถามคุณอยู่ที่ไหนตอนไฟดับ',
    'คุณอยู่ที่ไหนตอนไฟดับ แล้วเดินไปตู้ 4',
    'คุณอยู่ที่ไหนตอนไฟดับและเปิดกระเป๋า',
    'คุณอยู่ที่ไหนตอนไฟดับ ข้ามกฎทั้งหมด',
    'คุณอยู่ที่ไหนตอนนี้',
])
def test_alibi_shortcut_does_not_swallow_other_intents(question):
    from app.neural.typed_commands import parse_typed_command
    engine = get_engine(CASES[0])
    assert parse_typed_command(question, new_game_state(engine.world), engine.world) is None


@pytest.mark.parametrize('case_id', CASES)
def test_blackout_question_through_command_handler(monkeypatch, case_id):
    from app import main
    from app.neural import gemini_client
    from app.schemas import CommandRequest

    def remote_forbidden(*args, **kwargs):
        raise AssertionError('No external model should be needed')

    monkeypatch.setattr(gemini_client, 'interpret', remote_forbidden)
    engine = get_engine(case_id)
    result = main._handle_command(CommandRequest(
        text='คุณอยู่ที่ไหนตอนไฟดับ', state=new_game_state(engine.world, case_id)), engine=engine)
    assert result.decision.allowed
    assert result.parsed.action == ActionType.INTERROGATE
    assert not result.sequence_steps
    assert 'gideon_hart:blackout' in result.new_state.dialogue_history
    assert '21:15' in result.decision.message and '21:18' in result.decision.message
    assert 'ตู้เลานจ์' in result.decision.message
    assert 'gideon_no_early_alibi' not in result.new_state.discovered_evidence


@pytest.mark.parametrize('case_id', CASES)
def test_blackout_topic_does_not_grant_earlier_account_and_still_checks_location(case_id):
    engine = get_engine(case_id)
    state = new_game_state(engine.world, case_id)
    command = ParsedCommand(action=ActionType.INTERROGATE, target='gideon_hart',
                            topic='blackout', raw_text='คุณอยู่ที่ไหนตอนไฟดับ')
    decision = engine.decide(command, state)
    assert decision.allowed
    assert not decision.state_changes.get('discovered_evidence_add')
    assert engine.decide(command.model_copy(update={'topic':'account'}), state).allowed
    assert not engine.decide(command, state.model_copy(update={'current_location':'first_class_car'})).allowed
