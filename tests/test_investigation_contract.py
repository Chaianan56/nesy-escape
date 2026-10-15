"""State transitions that distinguish earned knowledge from a player's assertion."""
import copy
import json
from pathlib import Path

import pytest

from app.schemas import ActionType, GameState, ParsedCommand
from app.symbolic.engine import SymbolicEngine, apply_changes, accusation_submission
from app.symbolic.validation import validate_world


def command(action, target, **kwargs):
    return ParsedCommand(action=action, target=target, raw_text="test", **kwargs)


@pytest.fixture
def engine():
    return SymbolicEngine()


def run(engine, state, action, target, **kwargs):
    decision = engine.decide(command(action, target, **kwargs), state)
    assert decision.allowed, decision.message
    return apply_changes(state, decision.state_changes), decision


def test_dialogue_only_grants_spoken_node_and_reacts_to_new_evidence(engine):
    engine.world['suspects']['test_witness'] = {
        'location': 'lounge_car', 'accusable': False,
        'dialogue_nodes': [
            {'id': 'initial', 'topic': 'night', 'text': 'Initial account', 'grants_evidence': ['test_first']},
            {'id': 'clarify', 'topic': 'night', 'text': 'Revised account', 'requires_evidence': ['pocket_watch'],
             'grants_evidence': ['test_second'], 'grants_inventory': ['test_key']},
        ],
    }
    state, first = run(engine, GameState(), ActionType.INTERROGATE, 'test_witness')
    assert first.message == 'Initial account'
    assert state.discovered_evidence == ['test_first']
    assert state.dialogue_history == ['test_witness:initial']
    assert engine.dialogue_options('test_witness', state) == [{'topic': 'night', 'label': 'night'}]
    denied = engine.decide(command(ActionType.INTERROGATE, 'test_witness', topic='unavailable'), state)
    assert not denied.allowed and not denied.state_changes
    state.discovered_evidence.append('pocket_watch')
    state, revised = run(engine, state, ActionType.INTERROGATE, 'test_witness', topic='night')
    assert revised.message == 'Revised account'
    assert state.inventory == ['test_key']
    assert state.discovered_evidence == ['test_first', 'pocket_watch', 'test_second']
    state, repeated = run(engine, state, ActionType.INTERROGATE, 'test_witness', topic='night')
    assert repeated.message == 'Revised account'
    assert state.dialogue_history.count('test_witness:clarify') == 1
    assert not engine.decide(command(ActionType.ACCUSE, 'test_witness'), state).allowed


def test_default_dialogue_reads_unseen_nodes_before_latest_repeat(engine):
    engine.world['suspects']['test_witness'] = {'location': 'lounge_car', 'dialogue_nodes': [
        {'id': str(i), 'topic': 'night', 'text': str(i)} for i in range(3)]}
    state = GameState()
    for expected in ['0', '1', '2', '2']:
        state, decision = run(engine, state, ActionType.INTERROGATE, 'test_witness')
        assert decision.message == expected


@pytest.mark.parametrize('method', ['code', 'key'])
def test_unlock_requires_correct_code_or_held_key_and_examine_never_opens(engine, method):
    gate = {'code': '1923'} if method == 'code' else {'key': 'test_key'}
    engine.world['objects']['test_door'] = {'name_th': 'door', 'location': 'lounge_car',
        'type': 'object', 'supports': ['unlock', 'use'], 'unlock_requirements': gate}
    engine.world['objects']['test_hidden'] = {'name_th': 'hidden', 'location': 'lounge_car',
        'type': 'evidence', 'visible_requirements': {'requires_unlocked': ['test_door']}}
    state, _ = run(engine, GameState(), ActionType.EXAMINE, 'test_door')
    assert state.examined_objects == ['test_door'] and state.unlocked_objects == []
    assert not engine.offerable('test_hidden', state)
    assert not engine.decide(command(ActionType.EXAMINE, 'test_hidden'), state).allowed
    assert not engine.decide(command(ActionType.UNLOCK, 'test_door', code='wrong', instrument='test_key'), state).allowed
    if method == 'code':
        state, _ = run(engine, state, ActionType.UNLOCK, 'test_door', code='1923')
    else:
        state.inventory.append('test_key')
        state, _ = run(engine, state, ActionType.USE, 'test_door', instrument='test_key')
    assert engine.offerable('test_hidden', state)
    state, _ = run(engine, state, ActionType.EXAMINE, 'test_hidden')
    assert 'test_hidden' in state.discovered_evidence


def configure_claim(engine):
    engine.world['claims'] = {
        'test_correct': {'name_th': 'supported conclusion', 'supported': True,
                         'requires_evidence': ['pocket_watch', 'wall_clock'], 'feedback': 'Need both observations'},
        'test_wrong': {'name_th': 'unsupported conclusion', 'supported': False, 'feedback': 'This overstates the evidence'},
    }
    engine.world['inference_questions'] = [{'id': 'test_q', 'prompt': 'What follows?',
        'requires_evidence': ['pocket_watch'], 'choices': [
            {'id': 'a', 'label': 'A', 'target': 'test_correct'},
            {'id': 'b', 'label': 'B', 'target': 'test_wrong'}]}]


def test_inference_rejects_unavailable_unseen_and_incomplete_evidence(engine):
    configure_claim(engine)
    empty = GameState()
    assert engine.inference_questions(empty) == []
    assert not engine.decide(command(ActionType.INFER, 'test_correct', evidence=['pocket_watch', 'wall_clock']), empty).allowed
    partial = GameState(discovered_evidence=['pocket_watch'])
    question = engine.inference_questions(partial)[0]
    assert set(question) == {'id', 'prompt', 'choices'}
    assert all(set(c) == {'id', 'label', 'target'} for c in question['choices'])
    for evidence in [['pocket_watch'], ['pocket_watch', 'wall_clock'], ['pocket_watch', 'pocket_watch']]:
        assert not engine.decide(command(ActionType.INFER, 'test_correct', evidence=evidence), partial).allowed
    state = GameState(discovered_evidence=['pocket_watch', 'wall_clock'])
    assert not engine.decide(command(ActionType.INFER, 'test_wrong', evidence=state.discovered_evidence), state).allowed
    state, _ = run(engine, state, ActionType.INFER, 'test_correct', evidence=state.discovered_evidence)
    assert state.validated_claims == ['test_correct']
    assert state.claim_evidence == {'test_correct': ['pocket_watch', 'wall_clock']}


def test_claim_pillar_requires_player_inference_and_its_submitted_support(engine):
    configure_claim(engine)
    engine.world['deductions']['test_d'] = {'requires_evidence': ['pocket_watch']}
    engine.world['pillars']['gideon_hart']['timeline'] = {
        'requires_deductions': ['test_d'], 'requires_claims': ['test_correct']}
    state = GameState(discovered_evidence=['pocket_watch', 'wall_clock'])
    assert not engine.pillar_status('gideon_hart', state)['timeline']
    state, _ = run(engine, state, ActionType.INFER, 'test_correct', evidence=state.discovered_evidence)
    assert engine.pillar_status('gideon_hart', state)['timeline']
    state.discovered_evidence.remove('wall_clock')
    assert not engine.pillar_status('gideon_hart', state)['timeline']


def test_accusation_uses_all_discovered_evidence_and_ignores_submitted_subset(engine):
    walkthrough = json.loads((Path(__file__).resolve().parents[1] / 'data/walkthrough.json').read_text(encoding='utf-8'))
    support = walkthrough['inference_evidence']
    submitted = walkthrough['winning_cases']['button_wax']
    assert len(submitted) == 19 and 'letter_opener' not in submitted
    state = GameState(discovered_evidence=submitted + ['letter_opener'])
    state, _ = run(engine, state, ActionType.INFER, 'claim_two_times', evidence=support + ['letter_opener'])
    assert 'letter_opener' in state.claim_evidence['claim_two_times']
    decision = accusation_submission(engine, command(ActionType.ACCUSE, 'gideon_hart'), state, submitted)
    assert decision.allowed and decision.state_changes['ending'] == 'true_ending'
    # A subset supplied by an old caller cannot hide evidence already found in the case.
    decision = accusation_submission(engine, command(ActionType.ACCUSE, 'gideon_hart'), state, ['pocket_watch'])
    assert decision.allowed and decision.state_changes['ending'] == 'true_ending'
    assert engine.pillar_status('gideon_hart', state)['timeline']


def test_known_exculpatory_evidence_cannot_be_hidden_from_accusation(engine):
    engine.world['suspects']['vincent_gray']['exculpatory_evidence'] = ['wall_clock']
    state = GameState(discovered_evidence=['wall_clock', 'pocket_watch'])
    decision = accusation_submission(engine, command(ActionType.ACCUSE, 'vincent_gray'), state, ['pocket_watch'])
    assert not decision.allowed
    assert decision.violated_rule_id == 'R016_ACCUSABLE'
    assert not decision.state_changes


def test_accusation_does_not_apply_a_submission_cap_and_failed_accusations_persist(engine):
    engine.world['max_submitted_evidence'] = 1
    state = GameState(discovered_evidence=['wall_clock', 'pocket_watch'])
    decision = accusation_submission(engine, command(ActionType.ACCUSE, 'gideon_hart'), state, state.discovered_evidence)
    assert decision.violated_rule_id == 'R012_ACCUSE_ENDING_REQUIREMENTS'
    assert apply_changes(state, decision.state_changes).failed_accusations == 1


def test_raw_sequence_cannot_bypass_individual_action_checks(engine):
    decision = engine.decide(command(ActionType.SEQUENCE, None,
                                    alternatives=['move first_class_car', 'examine pocket_watch']), GameState())
    assert not decision.allowed and decision.violated_rule_id == 'R000_KNOWN_ACTION'
    assert not decision.state_changes


def test_examine_person_describes_person_without_granting_testimony(engine):
    state = GameState(current_location=engine.world['suspects']['dr_liora_venn']['location'])
    decision = engine.decide(command(ActionType.EXAMINE, 'dr_liora_venn'), state)
    assert decision.allowed
    assert decision.message == engine.world['suspects']['dr_liora_venn']['description']
    result = apply_changes(state, decision.state_changes)
    assert not result.discovered_evidence and not result.dialogue_history and not result.inventory


@pytest.mark.parametrize('broken', ['node_grant', 'claim_reference', 'gate_key', 'duplicate_question', 'evidence_cap'])
def test_new_contract_references_fail_at_load(engine, broken):
    from app.symbolic.engine import CHECKERS
    world = copy.deepcopy(engine.world)
    if broken == 'node_grant':
        world['suspects']['gideon_hart']['dialogue_nodes'] = [
            {'id': 'bad', 'topic': 'night', 'text': 'text', 'grants_evidence': ['missing']}]
    elif broken == 'claim_reference':
        world['pillars']['gideon_hart']['timeline']['requires_claims'] = ['missing']
    elif broken == 'gate_key':
        world['objects']['pocket_watch']['unlock_requirements'] = {'key': 'missing'}
    elif broken == 'duplicate_question':
        world['inference_questions'] = [{'id': 'same'}, {'id': 'same'}]
    else:
        world['max_submitted_evidence'] = 0
    with pytest.raises(ValueError, match='Invalid game data'):
        validate_world(engine.rules, world, CHECKERS, {action.value for action in ActionType})
