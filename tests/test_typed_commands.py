import time
from types import SimpleNamespace
from threading import Thread
from fastapi.testclient import TestClient
from app import main
from app.neural.typed_commands import parse_typed_command, interpret_game
from app.neural import gemini_client
from app.schemas import GameState, ActionType
from app.sessions import sessions, COOKIE


def test_exact_typed_commands_do_not_call_remote(monkeypatch):
    def unavailable(*args):
        raise AssertionError('Remote model should not be called')
    monkeypatch.setattr(gemini_client, 'interpret', unavailable)
    state = GameState()
    for text, action, target in [('ไปตู้ 4', ActionType.MOVE, 'first_class_car'),
                                 ('ดูรอบๆ', ActionType.EXAMINE, 'lounge_car'),
                                 ('สอบปากคำกิเดียน', ActionType.INTERROGATE, 'gideon_hart'),
                                 ('ตรวจนาฬิกาพกกลไก', ActionType.EXAMINE, 'pocket_watch')]:
        result = interpret_game(text, state)
        assert (result.action, result.target) == (action, target)


def test_negation_compound_and_ambiguous_input_are_not_shortcuts():
    for text in ['อย่าไปตู้ 4', 'ไปตู้ 4 แล้วตรวจนาฬิกา', 'กล่าวหากิเดียนหรือวินเซนต์', 'ตรวจนาฬิกา']:
        assert parse_typed_command(text, GameState(), main.engine.world) is None


def test_fast_input_still_obeys_location_rules(monkeypatch):
    monkeypatch.setattr(main, 'interpret', interpret_game)
    with TestClient(main.app) as client:
        client.get('/scene')
        result = client.post('/command', json={'text':'ตรวจนาฬิกาพกกลไก'}).json()
        assert not result['decision']['allowed']
        result = client.post('/command', json={'text':'ไปตู้ 4'}).json()
        assert result['new_state']['current_location'] == 'first_class_car'
        result = client.post('/command', json={'text':'ตรวจนาฬิกาพกกลไก'}).json()
        assert 'pocket_watch' in result['new_state']['discovered_evidence']


def test_model_has_bounded_timeout_and_no_automatic_retries(monkeypatch):
    configs=[]
    def generate(**kwargs):
        configs.append(kwargs['config'])
        return SimpleNamespace(text='{"action":"examine","target":"lounge_car","raw_text":"test"}')
    monkeypatch.setattr(gemini_client, '_clients', lambda:[SimpleNamespace(models=SimpleNamespace(generate_content=generate))])
    gemini_client.interpret('ช่วยมองรอบห้องหน่อย', GameState())
    assert 0 < configs[0].http_options.timeout <= 12000
    assert configs[0].http_options.retry_options.attempts == 1


def test_journal_does_not_wait_for_command_lock():
    with TestClient(main.app) as client:
        client.get('/scene')
        session = sessions[client.cookies[COOKIE]]
        results=[]
        with session.lock:
            worker = Thread(target=lambda:results.append(client.post('/journal')))
            worker.start()
            worker.join(timeout=2)
            completed = not worker.is_alive()
        worker.join(timeout=2)
        assert completed
        assert results[0].status_code == 200
