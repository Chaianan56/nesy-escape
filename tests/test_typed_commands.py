"""
tests/test_typed_commands.py — ทดสอบตัวแยกคำสั่งเร็วแบบกำหนดรูปแบบแน่นอน (Deterministic Fast-Path Parser)

หน้าที่:
- ทดสอบคำสั่งมาตรฐาน (เช่น "ไปตู้ 4", "ดูรอบๆ", "ตรวจนาฬิกาพก", "สอบปากคำกิเดียน")
  ว่าถูกประมวลผลผ่าน Fast-Path ทันทีโดยไม่เรียก Gemini API
- ทดสอบการจับคู่ชื่อไทย, ชื่ออังกฤษ, คำพ้อง (Aliases), และคำสั่งที่พิมพ์ผิดเล็กน้อย
- ทดสอบการทำงานคู่ขนานของคำสั่งที่รวดเร็ว
"""
from types import SimpleNamespace
from threading import Thread
from fastapi.testclient import TestClient
from app import main
from app.neural.typed_commands import parse_typed_command, interpret_game
from app.neural import gemini_client
from app.schemas import GameState, ActionType, ParsedCommand
from app.sessions import sessions, COOKIE


def test_exact_typed_commands_do_not_call_remote(monkeypatch):
    """ทดสอบว่าคำสั่งที่มีรูปแบบชัดเจนจะถูกประมวลผลผ่านตัวแยกคำสั่งเร็วทันที โดยไม่เรียก Gemini API"""
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
    """ทดสอบว่าคำสั่งปฏิเสธ คำสั่งผสมหลายกริยา และคำสั่งคลุมเครือจะไม่ผ่าน Fast-Path เพื่อส่งต่อให้ LLM ตีความ"""
    for text in ['อย่าไปตู้ 4', 'ไปตู้ 4 แล้วตรวจนาฬิกา', 'กล่าวหากิเดียนหรือวินเซนต์', 'ตรวจนาฬิกา',
                 'examine no_such_thing', 'ambiguous pocket_watch']:
        assert parse_typed_command(text, GameState(), main.engine.world) is None


def test_visible_dialogue_labels_locks_and_inference_parse_without_model(monkeypatch):
    """ทดสอบว่าคำสั่งคุยตามหัวข้อ ปลดล็อกด้วยรหัส หรือการอนุมาน สามารถแยกคำสั่งได้ถูกต้องโดยไม่ต้องพึ่งพาโมเดล"""
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
    """ทดสอบว่าคำสั่งหยิบกุญแจแบบไม่ระบุชื่อ จะจับคู่อัตโนมัติเฉพาะเมื่อมีกุญแจดอกเดียวที่หยิบได้ในห้องนั้น"""
    world = main.engine.world
    state = GameState(current_location='dining_car_staff')
    parsed = parse_typed_command('หยิบกุญแจ', state, world)
    assert parsed is not None
    assert (parsed.action, parsed.target) == (ActionType.TAKE, 'staff_key')
    assert main.engine.decide(parsed, state).allowed

    # ไม่เดาเป้าหมายหากไม่มีลูกกุญแจอยู่ในตู้นี้
    elsewhere = GameState(current_location='luggage_van_electrical')
    assert parse_typed_command('หยิบกุญแจ', elsewhere, world) is None

    # ไม่เดาเป้าหมายหากมีกุญแจในตู้เดียวกันมากกว่าหนึ่งดอกที่สามารถหยิบได้
    multiple_keys = {**world, 'objects': dict(world['objects'])}
    multiple_keys['objects']['spare_staff_key'] = {
        'name_th': 'กุญแจสำรอง', 'type': 'key',
        'location': 'dining_car_staff', 'supports': ['take'],
    }
    assert parse_typed_command('หยิบกุญแจ', state, multiple_keys) is None


def test_fast_input_still_obeys_location_rules(monkeypatch):
    """ทดสอบว่าคำสั่งที่ผ่าน Fast-Path ยังคงอยู่ภายใต้การควบคุมของกฎตำแหน่งและระยะทางของ Symbolic Engine"""
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
    """ทดสอบว่าการเรียก Gemini มีการจำกัดเพดานเวลา Timeout และไม่มีการ Retry ซ่อนอยู่"""
    configs=[]
    def generate(**kwargs):
        configs.append(kwargs['config'])
        return SimpleNamespace(text='{"action":"examine","target":"lounge_car","raw_text":"test"}')
    monkeypatch.setattr(gemini_client, '_clients', lambda:[SimpleNamespace(models=SimpleNamespace(generate_content=generate))])
    gemini_client.interpret('ช่วยมองรอบห้องหน่อย', GameState())
    assert 0 < configs[0].http_options.timeout <= 8000
    assert configs[0].http_options.retry_options.attempts == 1


def test_overloaded_model_is_retried_once_not_hammered(monkeypatch):
    """ทดสอบว่าเมื่อโมเดลเกิดภาวะทำงานหนักเกินไป (503) จะลองใหม่เพียง 1 ครั้งเท่านั้นโดยไม่กระหน่ำยิงซ้ำ"""
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
    """ทดสอบว่าการอ่านสมุดบันทึก (/journal) สามารถทำงานคู่ขนานได้โดยไม่ติดล็อกคำสั่ง (/command)"""
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
    """ทดสอบการปลดล็อกประตูเมื่อถือกุญแจที่ถูกต้อง ทั้งกรณีระบุอุปกรณ์และกรณีละเว้นอุปกรณ์"""
    world = main.engine.world
    state_with_key = GameState(current_location='luggage_van_electrical', inventory=['staff_key'])
    # 1. คำสั่งเร็ว "ปลดล็อกประตูห้องระบบไฟ" จะผูกอุปกรณ์ (instrument) ให้โดยอัตโนมัติ
    parsed = parse_typed_command('ปลดล็อกประตูห้องระบบไฟ', state_with_key, world)
    assert parsed is not None
    assert parsed.action == ActionType.UNLOCK
    assert parsed.target == 'electrical_room_door'
    assert parsed.instrument == 'staff_key'
    decision = main.engine.decide(parsed, state_with_key)
    assert decision.allowed

    # 2. Symbolic Engine อนุญาตให้ปลดล็อกได้เมื่อผู้เล่นถือกุญแจที่ถูกต้อง แม้ไม่ได้ระบุ instrument ชัดเจน
    bare_cmd = ParsedCommand(action=ActionType.UNLOCK, target='electrical_room_door', raw_text='เปิดห้องระบบไฟ')
    decision2 = main.engine.decide(bare_cmd, state_with_key)
    assert decision2.allowed

    # 3. แต่จะปฏิเสธคำสั่งหากผู้เล่นไม่ได้ถือกุญแจดอกนั้นไว้ในกระเป๋า
    state_without_key = GameState(current_location='luggage_van_electrical', inventory=[])
    decision3 = main.engine.decide(bare_cmd, state_without_key)
    assert not decision3.allowed
    assert decision3.violated_rule_id == 'R010_UNLOCK_REQUIREMENTS'


def test_medical_room_door_and_dossier_bag_interactions():
    """ทดสอบปฏิสัมพันธ์คำสั่งปลดล็อกประตูห้องแพทย์ด้วยกุญแจ และการไขรหัสกระเป๋าเอกสาร 1923"""
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

    # การเปิดห้องแพทย์โดยไม่มีกุญแจห้องแพทย์ (medical_key) จะต้องถูกปฏิเสธ
    state_no_key = GameState(current_location='first_class_car', inventory=[])
    parsed_no_key = parse_typed_command('เปิดห้องพยาบาล', state_no_key, world)
    dec = main.engine.decide(parsed_no_key, state_no_key)
    assert not dec.allowed
    assert dec.violated_rule_id == 'R010_UNLOCK_REQUIREMENTS'

    # ทดสอบรูปแบบคำสั่งการปลดล็อกกระเป๋าเอกสารด้วยรหัสผ่านหลากหลายรูปแบบ
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

    # การใส่รหัสกระเป๋าผิดจะต้องถูกปฏิเสธ
    wrong_code_cmd = parse_typed_command('เปิดกระเป๋า 9999', state_med, world)
    assert not main.engine.decide(wrong_code_cmd, state_med).allowed


def test_cassian_body_examination_commands():
    """ทดสอบคำสั่งสำรวจและชันสูตรศพของแคสเซียนทั้งภาษาไทยและอังกฤษ พร้อมตรวจการติดกฎระยะทาง"""
    world = main.engine.world
    state_car4 = GameState(current_location='first_class_car')
    state_car5 = GameState(current_location='lounge_car')

    for cmd_text in [
        'look cassian',
        'look at cassian',
        'look at the body',
        'look body',
        'examine cassian',
        'examine cassian_reed',
        'ดูแคสเซียน',
        'ดู แคสเซียน',
        'ตรวจศพ',
        'ชันสูตรศพ',
        'ชันสูตร',
        'ดูศพ',
        'ตรวจ แคสเซียน',
        'ตรวจดู แคสเซียน รีด',
    ]:
        parsed = parse_typed_command(cmd_text, state_car4, world)
        assert parsed is not None, f"Failed to parse '{cmd_text}'"
        assert parsed.action == ActionType.EXAMINE, f"Expected EXAMINE for '{cmd_text}'"
        assert parsed.target == 'cassian_reed', f"Expected cassian_reed for '{cmd_text}'"
        decision = main.engine.decide(parsed, state_car4)
        assert decision.allowed, f"Should be allowed in Car 4 for '{cmd_text}'"

    # หากอยู่ในตู้ 5 (lounge_car) การตรวจศพแคสเซียนในตู้ 4 จะต้องติดกฎ R005_SAME_LOCATION
    parsed_car5 = parse_typed_command('look cassian', state_car5, world)
    decision_car5 = main.engine.decide(parsed_car5, state_car5)
    assert not decision_car5.allowed
    assert decision_car5.violated_rule_id == 'R005_SAME_LOCATION'

