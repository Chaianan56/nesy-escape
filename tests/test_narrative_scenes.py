"""Narrative presentation follows earned knowledge and the case actually submitted."""
import copy
import json
from pathlib import Path

import pytest

from app.schemas import ActionType, GameState, ParsedCommand
from app.symbolic.engine import CHECKERS, SymbolicEngine, apply_changes
from app.symbolic.validation import validate_world


WALKTHROUGH = json.loads((Path(__file__).resolve().parents[1] / 'data/walkthrough.json').read_text(encoding='utf-8'))
SUPPORT = WALKTHROUGH['inference_evidence']
LIE_EVIDENCE = ['postponed_meeting_claim', 'staff_no_message']


def page(page_id, **extra):
    return {'id': page_id, 'speaker': 'ผู้บรรยาย', 'time_label': 'คืนนี้',
            'text': page_id, 'art': 'scene-05-lounge', **extra}


@pytest.fixture
def engine():
    result = SymbolicEngine()
    result.world.setdefault('narrative_scenes', {}).update({
        'test_boarding': {'title': 'ขึ้นขบวน', 'pages': [page('arrival')]},
        'test_confrontation': {'title': 'ทักท้วงคำให้การ', 'pages': [
            page('earned', requires_claims=['claim_two_times'], requires_deductions=['D16_POSTPONEMENT_LIE'],
                 evidence_ids=['postponed_meeting_claim', 'staff_no_message']),
            page('future', requires_evidence=['burnt_folder_c'], evidence_ids=['burnt_folder_c']),
        ]},
        'test_recap': {'title': 'ประกอบคดี', 'pages': [
            page('timeline', requires_claims=['claim_two_times'], evidence_ids=SUPPORT),
            page('tea', requires_deductions=['D04_GIDEON_TEA_LINK'], evidence_ids=['second_teacup']),
            page('button', requires_deductions=['D05_GIDEON_BUTTON_LINK'], evidence_ids=['obsidian_cufflink']),
            page('wax', requires_deductions=['D06_GIDEON_WAX_LINK'], evidence_ids=['wax_seal_imprint']),
        ]},
    })
    result.world['suspects']['gideon_hart']['dialogue_nodes'].append({
        'id': 'test_confrontation', 'topic': 'test_confrontation', 'label': 'ทักท้วงคำให้การ',
        'text': 'บทนำฉาก', 'requires_claims': ['claim_two_times'],
        'requires_deductions': ['D16_POSTPONEMENT_LIE'], 'scene_id': 'test_confrontation',
    })
    return result


def confront():
    return ParsedCommand(action=ActionType.INTERROGATE, target='gideon_hart',
                         topic='test_confrontation', raw_text='test')


def earned_state(engine):
    state = GameState(discovered_evidence=SUPPORT + LIE_EVIDENCE)
    inference = engine.decide(ParsedCommand(action=ActionType.INFER, target='claim_two_times',
                                            evidence=SUPPORT, raw_text='test'), state)
    assert inference.allowed
    return apply_changes(state, inference.state_changes)


def test_collected_facts_do_not_replace_the_players_inference(engine):
    state = GameState(discovered_evidence=SUPPORT + LIE_EVIDENCE)
    assert 'D16_POSTPONEMENT_LIE' in engine.deductions(state)
    assert not engine.decide(confront(), state).allowed
    assert engine.dialogue_scene(confront(), state) is None
    assert not any(item['topic'] == 'test_confrontation' for item in engine.narrative_followups(state))
    assert not any(item['topic'] == 'test_confrontation' for item in engine.dialogue_options('gideon_hart', state))


@pytest.mark.parametrize('missing', ['record', 'support', 'lie'])
def test_forged_or_incomplete_claim_does_not_open_confrontation(engine, missing):
    state = earned_state(engine)
    if missing == 'record':
        state.claim_evidence = {}
    elif missing == 'support':
        state.discovered_evidence.remove('wall_clock')
    else:
        state.discovered_evidence.remove('staff_no_message')
    assert state.validated_claims == ['claim_two_times']
    assert not engine.decide(confront(), state).allowed
    assert engine.dialogue_scene(confront(), state) is None
    assert not any(item['topic'] == 'test_confrontation' for item in engine.narrative_followups(state))


def test_earned_confrontation_exposes_only_supported_public_pages(engine):
    state = earned_state(engine)
    before = state.model_dump()
    assert engine.decide(confront(), state).allowed
    scene = engine.dialogue_scene(confront(), state)
    assert set(scene) == {'id', 'title', 'pages'}
    assert [entry['id'] for entry in scene['pages']] == ['earned']
    shown = scene['pages'][0]
    assert set(shown) == {'id', 'speaker', 'time_label', 'text', 'art', 'evidence'}
    assert shown['evidence'] == [{'id': eid, 'name': engine.world['objects'][eid]['name_th']} for eid in LIE_EVIDENCE]
    assert 'burnt_folder_c' not in json.dumps(scene)
    assert state.model_dump() == before


def test_followup_is_visible_from_other_car_but_scene_waits_for_actual_dialogue(engine):
    state = earned_state(engine)
    state.current_location = 'first_class_car'
    followups = [item for item in engine.narrative_followups(state) if item['topic'] == 'test_confrontation']
    assert len(followups) == 1
    assert set(followups[0]) == {'person_id', 'person_name', 'location', 'topic', 'label'}
    assert followups[0]['location'] == 'lounge_car'
    assert engine.dialogue_scene(confront(), state) is None
    state.current_location = 'lounge_car'
    decision = engine.decide(confront(), state)
    assert decision.allowed
    scene = engine.dialogue_scene(confront(), state)
    assert scene['id'] == 'test_confrontation'
    state = apply_changes(state, decision.state_changes)
    assert not any(item['topic'] == 'test_confrontation' for item in engine.narrative_followups(state))


@pytest.mark.parametrize('closed', ['ending', 'timeout'])
def test_followups_disappear_when_the_case_is_over(engine, closed):
    state = earned_state(engine)
    if closed == 'ending':
        state.ending_id = 'cold_arrival'
    else:
        state.elapsed_seconds = engine.time_limit_seconds
    assert engine.narrative_followups(state) == []
    assert engine.dialogue_scene(confront(), state) is None


@pytest.mark.parametrize('route,expected', [
    ('button_wax', {'timeline', 'button', 'wax'}),
    ('tea_button', {'timeline', 'tea', 'button'}),
    ('tea_wax', {'timeline', 'tea', 'wax'}),
])
def test_reconstruction_uses_submitted_case_not_all_collected_clues(engine, route, expected):
    state = earned_state(engine)
    state.discovered_evidence = [eid for eid, obj in engine.world['objects'].items() if obj.get('type') == 'evidence']
    state.ending_id = 'true_ending'
    submitted = WALKTHROUGH['winning_cases'][route]
    scene = engine.narrative_scene('test_recap', state, evidence_scope=submitted)
    assert {entry['id'] for entry in scene['pages']} == expected
    assert all(evidence['id'] in submitted for entry in scene['pages'] for evidence in entry['evidence'])
    assert engine.narrative_scene('test_recap', state, evidence_scope=[]) is None


def test_scope_cannot_invent_unseen_evidence_and_tags_also_gate_pages(engine):
    engine.world['narrative_scenes']['test_boarding']['pages'].append(page('hidden_tag', evidence_ids=['burnt_folder_c']))
    state = GameState()
    scene = engine.narrative_scene('test_boarding', state, evidence_scope=['burnt_folder_c'])
    assert [entry['id'] for entry in scene['pages']] == ['arrival']
    assert engine.narrative_scene('missing', state) is None


@pytest.mark.parametrize('broken', ['unknown_scene', 'scene_type', 'duplicate_page', 'unknown_evidence',
                                   'unknown_claim', 'unknown_deduction', 'unsafe_art', 'missing_text'])
def test_scene_contract_is_validated_at_startup(engine, broken):
    world = copy.deepcopy(engine.world)
    scene = world['narrative_scenes']['test_boarding']
    if broken == 'unknown_scene':
        world['suspects']['gideon_hart']['dialogue_nodes'][-1]['scene_id'] = 'missing'
    elif broken == 'scene_type':
        world['suspects']['gideon_hart']['dialogue_nodes'][-1]['scene_id'] = []
    elif broken == 'duplicate_page':
        scene['pages'].append(copy.deepcopy(scene['pages'][0]))
    elif broken == 'unknown_evidence':
        scene['pages'][0]['evidence_ids'] = ['missing']
    elif broken == 'unknown_claim':
        scene['pages'][0]['requires_claims'] = ['missing']
    elif broken == 'unknown_deduction':
        scene['pages'][0]['requires_deductions'] = ['missing']
    elif broken == 'unsafe_art':
        scene['pages'][0]['art'] = '../secrets.svg'
    else:
        del scene['pages'][0]['text']
    with pytest.raises(ValueError, match='Invalid game data'):
        validate_world(engine.rules, world, CHECKERS, {action.value for action in ActionType})
