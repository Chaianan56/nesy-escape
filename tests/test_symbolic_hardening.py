import ast
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from app import main, game_clock
from app.schemas import ActionType, GameState, ParsedCommand
from app.sessions import COOKIE, sessions
from app.symbolic.engine import SymbolicEngine, apply_changes


def command(action, target=None):
    return ParsedCommand(action=action, target=target, raw_text='test')


def test_testimony_cannot_be_examined_until_interrogated():
    engine = SymbolicEngine()
    for eid, obj in engine.world['objects'].items():
        owner = obj.get('from_testimony')
        if not owner:
            continue
        state = GameState(current_location=engine.world['suspects'][owner]['location'])
        denied = engine.decide(command(ActionType.EXAMINE, eid), state)
        assert not denied.allowed
        assert denied.violated_rule_id == 'R008_EVIDENCE_SOURCE'
        interview = engine.decide(command(ActionType.INTERROGATE, owner), state)
        assert interview.allowed
        state = apply_changes(state, interview.state_changes)
        assert eid in state.discovered_evidence
        assert engine.decide(command(ActionType.EXAMINE, eid), state).allowed


def test_time_override_is_shared_by_checker_and_clock(tmp_path):
    engine = SymbolicEngine()
    for rule in engine.rules:
        if rule['check'] == 'within_time_limit':
            rule['params'] = {'limit_seconds': 10}
    path = tmp_path / 'rules.json'
    path.write_text(json.dumps({'rules': engine.rules}), encoding='utf-8')
    engine = SymbolicEngine(rules_path=path)
    for elapsed, expected in [(9, True), (10, False), (11, False)]:
        state = GameState(elapsed_seconds=elapsed)
        assert engine.decide(command(ActionType.MOVE, 'first_class_car'), state).allowed == expected
        assert engine.is_out_of_time(state) != expected
        assert engine.seconds_left(state) == 10 - elapsed


@pytest.mark.parametrize('broken', ['checker', 'duplicate_rule', 'reference', 'order', 'threshold', 'cycle', 'duplicate_pool', 'zero_time'])
def test_bad_data_rejected_at_startup(tmp_path, broken):
    engine = SymbolicEngine()
    rules, world = engine.rules, engine.world
    if broken == 'checker': rules[0]['check'] = 'missing'
    if broken == 'duplicate_rule': rules.append(rules[0])
    if broken == 'reference': world['deductions']['D01_TRUE_MURDER_WINDOW']['requires_evidence'] = ['missing']
    if broken == 'order': world['ending_order'].remove('true_ending')
    if broken == 'threshold': world['deductions']['D07_GIDEON_IN_CASSIAN_ROOM']['at_least'] = 9
    if broken == 'cycle': world['deductions']['D01_TRUE_MURDER_WINDOW']['requires_deductions'] = ['D01_TRUE_MURDER_WINDOW']
    if broken == 'duplicate_pool': world['deductions']['D07_GIDEON_IN_CASSIAN_ROOM']['of'] *= 2
    if broken == 'zero_time': rules[1]['params'] = {'limit_seconds': 0}
    rp, sp = tmp_path/'rules.json', tmp_path/'story.json'
    rp.write_text(json.dumps({'rules': rules}), encoding='utf-8')
    sp.write_text(json.dumps(world), encoding='utf-8')
    with pytest.raises(ValueError, match='Invalid game data'):
        SymbolicEngine(rp, sp)


@pytest.fixture
def clients(monkeypatch):
    sessions.clear()
    monkeypatch.setattr(main, 'interpret', lambda text, state: command(ActionType.MOVE, 'first_class_car'))
    a, b = TestClient(main.app), TestClient(main.app)
    a.get('/scene'); b.get('/scene')
    yield a, b
    sessions.clear()


def test_client_cannot_forge_evidence_clock_or_location(clients, monkeypatch):
    a, b = clients
    original = a.get('/scene').json()['initial_state']
    fake = GameState(current_location='first_class_car', discovered_evidence=list(main.engine.world['objects']),
                     started_at=None, ending_id='true_ending').model_dump()
    assert a.post('/journal', json=fake).json()['evidence'] == []
    assert a.post('/clock', json=fake).json()['new_state']['started_at'] == original['started_at']
    monkeypatch.setattr(main, 'interpret', lambda text, state: command(ActionType.ACCUSE, 'gideon_hart'))
    rejected = a.post('/command', json={'text':'accuse', 'state': fake}).json()
    assert not rejected['decision']['allowed']
    assert rejected['new_state']['ending_id'] is None
    assert rejected['new_state']['discovered_evidence'] == []
    assert b.post('/journal').json()['evidence'] == []


def test_progress_is_persistent_and_isolated_between_sessions(clients):
    a, b = clients
    moved = a.post('/command', json={'text':'move'}).json()['new_state']
    assert moved['current_location'] == 'first_class_car'
    assert a.get('/scene').json()['initial_state'] == moved
    assert b.get('/scene').json()['initial_state']['current_location'] == 'lounge_car'
    stale = a.post('/clock', json=GameState().model_dump()).json()['new_state']
    assert stale['current_location'] == 'first_class_car'
    assert stale['turn_count'] == 1
    reset = a.post('/new-game').json()['new_state']
    assert reset['current_location'] == 'lounge_car'
    assert reset['turn_count'] == 0


def test_complete_walkthrough_uses_only_server_state(clients, monkeypatch):
    a, _ = clients
    monkeypatch.setattr(main, 'interpret', lambda text, state: command(ActionType(text.split()[0]), text.split()[1]))
    steps = json.loads(Path('data/walkthrough.json').read_text(encoding='utf-8'))['steps']
    for action, target in steps:
        payload = {'text': f'{action} {target}'}
        if action == 'accuse':
            payload['submitted_evidence'] = [e['id'] for e in a.post('/journal').json()['evidence']]
        result = a.post('/command', json=payload).json()
        assert result['decision']['allowed'], result
    assert result['new_state']['ending_id'] == 'true_ending'
    assert a.get('/scene').json()['initial_state']['ending_id'] == 'true_ending'


def test_expired_server_clock_cannot_be_reset_by_client(clients, monkeypatch):
    a, _ = clients
    sessions[a.cookies[COOKIE]].state.started_at = 100
    monkeypatch.setattr(game_clock.time, 'time', lambda: 100 + main.engine.time_limit_seconds)
    data = a.post('/clock', json=GameState().model_dump()).json()
    assert data['new_state']['ending_id'] == 'cold_arrival'
    assert a.get('/scene').json()['initial_state']['ending_id'] == 'cold_arrival'


def test_session_required_and_scene_hides_unseen_objects():
    c = TestClient(main.app)
    assert c.post('/command', json={'text':'move'}).status_code == 401
    assert c.post('/journal').status_code == 401
    response = c.get('/scene')
    assert 'HttpOnly' in response.headers['set-cookie']
    assert 'secret_file' not in response.json()['objects']
    assert not main.engine.offerable('unknown_id', GameState())


def test_overlapping_commands_do_not_overwrite_progress(clients, monkeypatch):
    a, _ = clients
    started, release = threading.Event(), threading.Event()
    calls = []
    def interpret(text, state):
        calls.append(state.turn_count)
        if len(calls) == 1:
            started.set()
            assert release.wait(5)
        return command(ActionType.MOVE, 'first_class_car')
    monkeypatch.setattr(main, 'interpret', interpret)
    # Separate HTTP clients share one session cookie to simulate two browser requests.
    other = TestClient(main.app)
    other.cookies.set(COOKIE, a.cookies[COOKIE])
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(a.post, '/command', json={'text':'one'})
        assert started.wait(5)
        second = pool.submit(other.post, '/command', json={'text':'two'})
        release.set()
        assert first.result().status_code == second.result().status_code == 200
    assert calls == [0, 1]
    assert a.post('/clock').json()['new_state']['turn_count'] == 2


def test_cli_pillar_labels_work_and_wrong_ending_does_not_name_a_killer(capsys):
    source = Path('play.py').read_text(encoding='utf-8')
    tree = ast.parse(source)
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ('show_pillars','th_name')]
    engine = SymbolicEngine()
    scope = {'engine':engine, 'state':GameState(), 'world':engine.world,
             'PILLAR_TH':engine.world['pillar_labels'], 're':__import__('re')}
    exec(compile(ast.Module(body=functions, type_ignores=[]), 'play.py', 'exec'), scope)
    scope['show_pillars']()
    assert 'เส้นเวลา' in capsys.readouterr().out
    assert 'ผู้ลงมือคือ{th_name(parsed.target)}' not in source
