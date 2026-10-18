from types import SimpleNamespace
from threading import Thread
from fastapi.testclient import TestClient
from app import main
from app.neural.typed_commands import parse_typed_command, interpret_game
from app.neural import gemini_client
from app.schemas import GameState, ActionType, ParsedCommand
from app.sessions import sessions, COOKIE


def test_exact_typed_commands_do_not_call_remote(monkeypatch):
    def unavailable(*args):
        raise AssertionError('Remote model should not be called')
    monkeypatch.setattr(gemini_client, 'interpret', unavailable)
    state = GameState()
    for text, action, target in [('ไปตู้ 4', ActionType.MOVE, 'first_class_car'),
                                 ('ดูรอบๆ', ActionType.EXAMINE, 'lounge_car'),
                                 ('look around', ActionType.EXAMINE, 'lounge_car'),
                                 ('สอบปากคำกิเดียน', ActionType.INTERROGATE, 'gideon_hart'),
                                 ('talk to gideon', ActionType.INTERROGATE, 'gideon_hart'),
                                 ('ตรวจนาฬิกาพกกลไก', ActionType.EXAMINE, 'pocket_watch'),
                                 ('examine pocket_watch', ActionType.EXAMINE, 'pocket_watch'),
                                 ('examine pocket watch', ActionType.EXAMINE, 'pocket_watch'),
                                 ('go to car 4', ActionType.MOVE, 'first_class_car'),
                                 ('move first_class_car', ActionType.MOVE, 'first_class_car')]:
        result = interpret_game(text, state)
        assert (result.action, result.target) == (action, target)


def test_negation_compound_and_ambiguous_input_are_not_shortcuts():
    for text in ['อย่าไปตู้ 4', 'ไปตู้ 4 แล้วตรวจนาฬิกา', 'กล่าวหากิเดียนหรือวินเซนต์', 'ตรวจนาฬิกา',
                 'examine no_such_thing', 'ambiguous pocket_watch']:
        assert parse_typed_command(text, GameState(), main.engine.world) is None


def test_visible_dialogue_labels_locks_and_inference_parse_without_model(monkeypatch):
    def unavailable(*args):
        raise AssertionError('Exact investigation commands must work without a model')
    monkeypatch.setattr(gemini_client, 'interpret', unavailable)
    samples = [
        ('ถามพนักงานตรวจตู้ เรื่องเสียงกระแทกและนาฬิกาแตก',
         'interrogate', 'car_attendant', {'topic': 'impact'}),
        ('ถามดร. ลิโอรา เวนน์ (Dr. Liora Venn) เรื่องคำให้การของเอเลียส',
         'interrogate', 'dr_liora_venn', {'topic': 'father'}),
        ('ปลดล็อกกระเป๋าสำนวนล็อกรหัส รหัส 1923',
         'unlock', 'dossier_bag', {'code': '1923'}),
        ('ใช้กุญแจห้องแพทย์กับประตูห้องแพทย์',
         'use', 'medical_room_door', {'instrument': 'medical_key'}),
        ('ใช้กุญแจเปิดประตูห้องแพทย์',
         'use', 'medical_room_door', {'instrument': 'medical_key'}),
        ('unlock electrical_room_door staff_key',
         'unlock', 'electrical_room_door', {'instrument': 'staff_key'}),
        ('infer claim_two_times', 'infer', 'claim_two_times', {'evidence': []}),
    ]
    for text, action, target, fields in samples:
        state = GameState(inventory=['medical_key']) if text == 'ใช้กุญแจเปิดประตูห้องแพทย์' else GameState()
        parsed = interpret_game(text, state)
        assert (parsed.action.value, parsed.target) == (action, target), text
        assert all(getattr(parsed, field) == value for field, value in fields.items()), text


def test_generic_key_pick_resolves_only_when_one_takeable_key_is_local():
    world = main.engine.world
    state = GameState(current_location='dining_car_staff')
    parsed = parse_typed_command('หยิบกุญแจ', state, world)
    assert parsed is not None
    assert (parsed.action, parsed.target) == (ActionType.TAKE, 'staff_key')
    assert main.engine.decide(parsed, state).allowed

    # Do not guess when no key is in this car.
    elsewhere = GameState(current_location='luggage_van_electrical')
    assert parse_typed_command('หยิบกุญแจ', elsewhere, world) is None

    # Do not guess when two locally takeable keys are possible.
    multiple_keys = {**world, 'objects': dict(world['objects'])}
    multiple_keys['objects']['spare_staff_key'] = {
        'name_th': 'กุญแจสำรอง', 'type': 'key',
        'location': 'dining_car_staff', 'supports': ['take'],
    }
    assert parse_typed_command('หยิบกุญแจ', state, multiple_keys) is None


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
    assert 0 < configs[0].http_options.timeout <= 8000
    assert configs[0].http_options.retry_options.attempts == 1


def test_overloaded_model_is_retried_once_not_hammered(monkeypatch):
    calls=[]
    def generate(**kwargs):
        calls.append(1)
        raise RuntimeError('503 UNAVAILABLE. This model is currently experiencing high demand')
    monkeypatch.setattr(gemini_client, '_clients', lambda:[SimpleNamespace(models=SimpleNamespace(generate_content=generate))])
    try:
        gemini_client.interpret('สำรวจ', GameState())
    except gemini_client.NeuralUnavailable:
        pass
    assert len(calls) == 2


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


def test_unlock_door_with_carried_key_resolves_and_succeeds():
    world = main.engine.world
    state_with_key = GameState(current_location='luggage_van_electrical', inventory=['staff_key'])
    # 1. Typed command "ปลดล็อกประตูห้องระบบไฟ" auto-binds instrument
    parsed = parse_typed_command('ปลดล็อกประตูห้องระบบไฟ', state_with_key, world)
    assert parsed is not None
    assert parsed.action == ActionType.UNLOCK
    assert parsed.target == 'electrical_room_door'
    assert parsed.instrument == 'staff_key'
    decision = main.engine.decide(parsed, state_with_key)
    assert decision.allowed

    # 2. Symbolic engine allows unlock when player carries the required key even without instrument
    bare_cmd = ParsedCommand(action=ActionType.UNLOCK, target='electrical_room_door', raw_text='เปิดห้องระบบไฟ')
    decision2 = main.engine.decide(bare_cmd, state_with_key)
    assert decision2.allowed

    # 3. But rejects if player does not have the key
    state_without_key = GameState(current_location='luggage_van_electrical', inventory=[])
    decision3 = main.engine.decide(bare_cmd, state_without_key)
    assert not decision3.allowed
    assert decision3.violated_rule_id == 'R010_UNLOCK_REQUIREMENTS'


def test_medical_room_door_and_dossier_bag_interactions():
    world = main.engine.world
    state_med = GameState(current_location='first_class_car', inventory=['medical_key'])

    for text in [
        'เปิดห้องพยาบาล',
        'เปิดห้องแพทย์',
        'เปิดประตูห้องแพทย์',
        'เปิดประตูห้องพยาบาล',
        'ปลดล็อกห้องแพทย์',
        'ปลดล็อกห้องพยาบาล',
        'ไขห้องแพทย์',
        'ไขประตูห้องแพทย์',
        'ใช้กุญแจห้องแพทย์',
        'ใช้กุญแจห้องแพทย์เปิดประตู',
        'ใช้กุญแจเปิดประตู',
        'ใช้กุญแจ',
    ]:
        parsed = parse_typed_command(text, state_med, world)
        assert parsed is not None, f"Failed to parse '{text}'"
        assert parsed.target == 'medical_room_door', f"Wrong target for '{text}': {parsed.target}"
        assert parsed.instrument == 'medical_key', f"Missing instrument for '{text}'"
        assert main.engine.decide(parsed, state_med).allowed, f"Decision rejected for '{text}'"

    # Opening medical room without medical_key is rejected
    state_no_key = GameState(current_location='first_class_car', inventory=[])
    parsed_no_key = parse_typed_command('เปิดห้องพยาบาล', state_no_key, world)
    dec = main.engine.decide(parsed_no_key, state_no_key)
    assert not dec.allowed
    assert dec.violated_rule_id == 'R010_UNLOCK_REQUIREMENTS'

    # Dossier bag code unlocking variations
    for text in [
        'เปิดกระเป๋า 1923',
        'ปลดล็อกกระเป๋า 1923',
        'ไขกระเป๋า 1923',
        'ใส่รหัสกระเป๋า 1923',
        'ใส่รหัส 1923',
        'รหัส 1923',
    ]:
        parsed_bag = parse_typed_command(text, state_med, world)
        assert parsed_bag is not None, f"Failed to parse bag cmd '{text}'"
        assert parsed_bag.target == 'dossier_bag'
        assert parsed_bag.code == '1923'
        assert main.engine.decide(parsed_bag, state_med).allowed

    # Wrong code is rejected
    wrong_code_cmd = parse_typed_command('เปิดกระเป๋า 9999', state_med, world)
    assert not main.engine.decide(wrong_code_cmd, state_med).allowed


