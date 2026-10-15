"""
test_api.py — ทดสอบเส้นทางจริงของ API ตั้งแต่ HTTP เข้ามาจนสถานะใหม่ออกไป

ไฟล์นี้ไม่เรียก Gemini จริง แต่สวม interpret() ด้วยตัวปลอมที่คืน ParsedCommand ตามที่สั่ง
เพื่อทดสอบสิ่งที่ test_engine.py ทดสอบไม่ได้ คือชั้นที่อยู่ระหว่างสองเลเยอร์
    - คำสั่งผ่านแล้วสถานะใหม่ถูกส่งกลับไปจริงไหม
    - ชั้น neural ล้มแล้ว API ตอบอะไร
    - หมดเวลาแล้วคดีถูกปิดในสถานะจริงไหม ไม่ใช่แค่ขึ้นข้อความ
    - ตัวเลือกที่ยื่นกลับไปเฉลยชื่อของที่ผู้เล่นยังหาไม่เจอหรือเปล่า

รันด้วย:  python -m pytest tests/test_api.py -v
"""

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app import main
from app.schemas import ActionType, GameState, ParsedCommand
from app.neural.gemini_client import NeuralUnavailable

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def clean_session():
    from app.sessions import sessions
    sessions.clear()
    client.cookies.clear()
    client.get("/scene")
    yield
    sessions.clear()


def seed_state(state):
    """Test setup: install state on the server, never trust request state."""
    from app.sessions import sessions, COOKIE
    sessions[client.cookies[COOKIE]].state = state.model_copy(deep=True)


def state_post(path, state):
    seed_state(state)
    return client.post(path, json={})


def test_journal_shows_only_discovered_evidence_and_earned_deductions():
    empty = state_post('/journal', GameState()).json()
    assert empty['evidence'] == []
    assert empty['deductions'] == []
    assert all(main.engine.world['objects'][o['id']].get('location') == 'lounge_car'
               for o in empty['visible'])
    state = GameState(discovered_evidence=['pocket_watch', 'red_soot', 'tunnel_schedule', 'staff_impact_testimony'])
    found = state_post('/journal', state).json()
    assert {e['id'] for e in found['evidence']} == set(state.discovered_evidence)
    assert found['deductions'] == []
    assert found['pillars'] == {}
    assert found['case_closed'] is False
    state.ending_id = 'cold_arrival'
    closed = state_post('/journal', state).json()
    assert 'D01_TRUE_MURDER_WINDOW' in {d['id'] for d in closed['deductions']}


def test_background_unlocks_only_after_source_is_discovered():
    assert state_post('/journal', GameState()).json()['background'] == []
    result = state_post('/journal', GameState(discovered_evidence=['secret_file'])).json()
    assert len(result['background']) == 1
    assert result['background'][0]['requires_evidence'] == ['secret_file']


def test_intro_clock_starts_once_after_enter(monkeypatch):
    monkeypatch.setattr(main.time, 'time', lambda: 1000)
    client.post('/new-game')
    assert client.get('/scene').json()['initial_state']['started_at'] is None
    assert client.post('/clock').json()['new_state']['elapsed_seconds'] == 0
    assert client.post('/start').json()['new_state']['started_at'] == 1000
    monkeypatch.setattr(main.time, 'time', lambda: 1010)
    assert client.post('/start').json()['new_state']['started_at'] == 1000
    assert client.post('/clock').json()['new_state']['elapsed_seconds'] == 10


def test_requested_hint_does_not_grant_evidence_or_deductions():
    state = GameState(discovered_evidence=['pocket_watch', 'wall_clock'])
    seed_state(state)
    result = client.post('/hint').json()
    assert 'นาฬิกาสองเรือน' in result['text']
    journal = client.post('/journal').json()
    assert {e['id'] for e in journal['evidence']} == set(state.discovered_evidence)
    assert journal['deductions'] == []


@pytest.mark.parametrize("action", [ActionType.UNKNOWN, ActionType.AMBIGUOUS])
def test_timeout_and_closed_case_take_priority_over_unknown_intent(fake_llm, action):
    fake_llm(action)
    state = GameState(elapsed_seconds=main.engine.world["time_limit_seconds"])
    body = post("???", state).json()
    assert body["decision"]["violated_rule_id"] == "R014_TIME_LIMIT"
    assert body["new_state"]["ending_id"] == main.engine.ending_for(on_timeout=True)["id"]
    again = post("???", GameState(**body["new_state"])).json()
    assert again["decision"]["violated_rule_id"] == "R001_GAME_NOT_OVER"


def test_commands_do_not_spend_clock_time(fake_llm, monkeypatch):
    from app import game_clock
    monkeypatch.setattr(game_clock.time, "time", lambda: 1000)
    fake_llm(ActionType.MOVE, "first_class_car")
    state = GameState(started_at=990)
    body = post("move", state).json()
    assert body["new_state"]["elapsed_seconds"] == 10
    assert body["new_state"]["turn_count"] == 1
    again = post("move", GameState(**body["new_state"])).json()
    assert again["new_state"]["elapsed_seconds"] == 10


def test_clock_closes_without_a_command_or_llm(monkeypatch):
    from app import game_clock
    limit = main.engine.world["time_limit_seconds"]
    monkeypatch.setattr(game_clock.time, "time", lambda: limit + 100)
    def forbidden(*args):
        raise AssertionError("Clock must not call Gemini")
    monkeypatch.setattr(main, "interpret", forbidden)
    body = state_post("/clock", GameState(started_at=100)).json()
    assert body["new_state"]["ending_id"] == main.engine.ending_for(on_timeout=True)["id"]
    assert body["new_state"]["turn_count"] == 0


def test_expiry_during_llm_wait_rejects_action(monkeypatch):
    from app import game_clock
    limit = main.engine.world["time_limit_seconds"]
    now = [limit + 99]
    monkeypatch.setattr(game_clock.time, "time", lambda: now[0])
    def slow(text, state):
        now[0] += 2
        return ParsedCommand(action=ActionType.MOVE, target="first_class_car", raw_text=text)
    monkeypatch.setattr(main, "interpret", slow)
    body = post("move", GameState(started_at=100)).json()
    assert not body["decision"]["allowed"]
    assert body["new_state"]["current_location"] == "lounge_car"
    assert body["new_state"]["ending_id"]


def test_accusation_before_deadline_keeps_its_ending(fake_llm, monkeypatch):
    from app import game_clock
    limit = main.engine.world["time_limit_seconds"]
    monkeypatch.setattr(game_clock.time, "time", lambda: limit + 99)
    fake_llm(ActionType.ACCUSE, "gideon_hart")
    state = GameState(started_at=100, discovered_evidence=[k for k, v in main.engine.world["objects"].items() if v["type"] == "evidence"])
    expected = main.engine.ending_for("gideon_hart", state)["id"]
    seed_state(state)
    body = client.post("/command", json={"text": "accuse", "submitted_evidence": TRUE_ENDING_EVIDENCE}).json()
    assert body["decision"]["allowed"]
    assert body["new_state"]["ending_id"] == expected


@pytest.fixture
def fake_llm(monkeypatch):
    """สวม interpret() ด้วยตัวปลอม เรียกใช้ด้วย fake_llm(action, target, ...)

    ทดสอบท่อ ไม่ได้ทดสอบ Gemini การตีความภาษาไทยจริงอยู่ใน test_neural.py
    """
    def install(action, target=None, alternatives=None, raises=None, sequence=False):
        def fake(text, state):
            if raises:
                raise raises
            return ParsedCommand(action=action, target=target, raw_text=text,
                                 confidence=1.0, alternatives=alternatives or [], sequence=sequence)
        monkeypatch.setattr(main, "interpret", fake)
    return install


def post(text, state):
    seed_state(state)
    return client.post("/command", json={"text": text, "submitted_evidence": state.discovered_evidence})


def test_missing_vincent_clue_keeps_case_open_then_allows_accusation(fake_llm):
    fake_llm(ActionType.ACCUSE, "vincent_gray")
    state = GameState(discovered_evidence=["wire_cutters", "vincent_blood"])
    denied = post("กล่าวหาวินเซนต์", state).json()
    assert not denied["decision"]["allowed"]
    assert denied["new_state"] == {**state.model_dump(), "failed_accusations": 1}
    state.failed_accusations = 1
    state.discovered_evidence.append("cut_copper_wire")
    allowed = post("กล่าวหาวินเซนต์", state).json()
    assert allowed["decision"]["allowed"]
    assert allowed["new_state"]["ending_id"] == "the_scapegoat"


@pytest.mark.parametrize('submission', [None, [], ['unknown'], ['wire_cutters', 'wire_cutters']])
def test_accusation_uses_all_discovered_evidence_without_submission(fake_llm, submission):
    fake_llm(ActionType.ACCUSE, 'vincent_gray')
    state = GameState(discovered_evidence=['wire_cutters', 'vincent_blood', 'cut_copper_wire'])
    seed_state(state)
    result = client.post('/command', json={'text': 'กล่าวหาวินเซนต์', 'submitted_evidence': submission}).json()
    assert result['decision']['allowed']
    assert result['new_state']['ending_id'] == 'the_scapegoat'


def test_entire_discovered_inventory_decides_ending(fake_llm):
    fake_llm(ActionType.ACCUSE, 'gideon_hart')
    state = GameState(discovered_evidence=list(main.engine.world['objects']))
    seed_state(state)
    result = client.post('/command', json={'text': 'กล่าวหากิเดียน'}).json()
    assert result['decision']['allowed']
    assert result['new_state']['ending_id'] == 'true_ending'
    assert result['new_state']['discovered_evidence'] == state.discovered_evidence
    journal = client.post('/journal').json()
    assert journal['submitted_evidence'] == state.discovered_evidence
    assert 'D01_TRUE_MURDER_WINDOW' in {d['id'] for d in journal['deductions']}
    client.post('/new-game')
    assert client.post('/journal').json()['submitted_evidence'] is None


TRUE_ENDING_EVIDENCE = json.loads(Path('data/walkthrough.json').read_text(encoding='utf-8'))['submitted_evidence']
INFERENCE_EVIDENCE = json.loads(Path('data/walkthrough.json').read_text(encoding='utf-8'))['inference_evidence']


def test_journal_lists_only_held_keys_and_their_useful_description():
    assert state_post('/journal', GameState()).json()['inventory'] == []
    journal = state_post('/journal', GameState(inventory=['medical_key'])).json()
    assert journal['inventory'] == [{'id': 'medical_key',
        'name': main.engine.world['objects']['medical_key']['name_th'],
        'description': main.engine.world['objects']['medical_key']['description']}]


def test_inference_uses_actual_submission_and_exports_attempts(monkeypatch):
    seed_state(GameState(discovered_evidence=INFERENCE_EVIDENCE))
    monkeypatch.setattr(main, 'interpret', lambda text, state: ParsedCommand(
        action=ActionType.INFER, target='claim_two_times', evidence=INFERENCE_EVIDENCE, raw_text=text))
    rejected = client.post('/command', json={'text': 'เสนอข้อสรุป', 'submitted_evidence': []}).json()
    assert not rejected['decision']['allowed']
    assert rejected['new_state']['validated_claims'] == []
    accepted = client.post('/command', json={'text': 'เสนอข้อสรุป', 'submitted_evidence': INFERENCE_EVIDENCE}).json()
    assert accepted['decision']['allowed']
    assert accepted['new_state']['claim_evidence'] == {'claim_two_times': INFERENCE_EVIDENCE}
    export = client.get('/study-export').json()
    assert export['story_version'] == main.engine.world['content_version']
    assert [attempt['accepted'] for attempt in export['inference_attempts']] == [False, True]
    assert export['inference_attempts'][0]['evidence'] == []
    assert export['inference_attempts'][1]['evidence'] == INFERENCE_EVIDENCE


def test_direct_accusation_after_finding_everything_ends_the_case(fake_llm):
    fake_llm(ActionType.ACCUSE, 'gideon_hart')
    everything = [k for k, v in main.engine.world['objects'].items() if v['type'] == 'evidence']
    seed_state(GameState(discovered_evidence=everything, validated_claims=['claim_two_times'],
                        claim_evidence={'claim_two_times': INFERENCE_EVIDENCE}))
    result = client.post('/command', json={'text': 'กล่าวหากิเดียน'}).json()
    assert result['decision']['allowed']
    assert result['new_state']['ending_id'] == 'true_ending'
    assert result['new_state']['failed_accusations'] == 0


def test_two_weak_accusations_show_pillars_and_the_third_closes_the_case(fake_llm):
    fake_llm(ActionType.ACCUSE, 'gideon_hart')
    seed_state(GameState(discovered_evidence=INFERENCE_EVIDENCE))
    weak = {'text': 'กล่าวหากิเดียน'}
    for attempt, left in ((1, 2), (2, 1)):
        result = client.post('/command', json=weak).json()
        assert not result['decision']['allowed']
        assert result['new_state'] == {**result['new_state'], 'failed_accusations': attempt, 'ending_id': None}
        message = result['decision']['message']
        assert '✓ เส้นเวลา' in message and '✗ แรงจูงใจ' in message and f'อีก {left} ครั้ง' in message
        assert 'แฟ้ม C' not in message  # บอกเสาที่ขาด ไม่บอกชิ้นที่ขาด
    result = client.post('/command', json=weak).json()
    assert result['new_state']['ending_id'] == 'unproven'
    assert result['new_state']['failed_accusations'] == 3
    assert result['decision']['reasoning_chain'][-1]['rule_id'] == 'R_ACCUSATION_LIMIT'


def test_cannot_omit_known_exculpatory_evidence(fake_llm):
    fake_llm(ActionType.ACCUSE, 'vincent_gray')
    selected = ['wire_cutters', 'vincent_blood', 'cut_copper_wire']
    seed_state(GameState(discovered_evidence=selected + ['pocket_watch', 'red_soot', 'tunnel_schedule', 'staff_impact_testimony', 'vincent_ticket', 'vincent_station_alibi']))
    result = client.post('/command', json={'text': 'กล่าวหาวินเซนต์', 'submitted_evidence': selected}).json()
    assert not result['decision']['allowed']
    assert result['new_state']['ending_id'] is None


# ---------- ทะเบียนฉาก ----------

def test_scene_hands_out_the_ids_the_engine_actually_uses():
    """frontend กับ neural ต้องดึงทะเบียน id จากที่เดียวกับที่ engine ใช้ตัดสิน"""
    s = client.get("/scene").json()
    assert s["rules_count"] == len(main.engine.rules)
    assert set(s["locations"]) == set(main.engine.world["locations"])
    assert set(s["objects"]) == {oid for oid in main.engine.world["objects"] if main.engine.offerable(oid, GameState(**s['initial_state']))}
    assert s["initial_state"]["current_location"] in s["locations"]


# ---------- เส้นทางปกติ ----------

def test_a_successful_command_returns_a_state_that_moved(fake_llm):
    """คำสั่งที่ผ่านต้องคืนสถานะใหม่ที่เปลี่ยนไปจริง ทั้งตำแหน่งและเวลา"""
    fake_llm(ActionType.MOVE, "first_class_car")
    r = post("ไปที่ตู้โดยสารชั้นหนึ่ง", GameState())
    assert r.status_code == 200
    body = r.json()
    assert body["decision"]["allowed"]
    assert body["new_state"]["current_location"] == "first_class_car"
    assert body["new_state"]["elapsed_seconds"] == 0
    assert body["decision"]["reasoning_chain"], "คำตัดสินต้องมีสายเหตุผลเสมอ"


def test_a_refused_command_costs_no_time(fake_llm):
    """คำสั่งที่ไม่ผ่านต้องไม่กินเวลาและไม่เปลี่ยนสถานะ"""
    fake_llm(ActionType.EXAMINE, "pocket_watch")   # อยู่คนละตู้
    before = GameState()
    body = post("ดูนาฬิกาพก", before).json()
    assert not body["decision"]["allowed"]
    assert body["new_state"] == before.model_dump()


def test_the_api_keeps_game_playable_when_gemini_is_down(fake_llm):
    """Neural ล้มต้องคืนคำตอบในเกมที่ไม่เปลี่ยนสถานะ แทน HTTP 502"""
    fake_llm(ActionType.EXAMINE, raises=NeuralUnavailable("โควตาหมด"))
    before = GameState()
    r = post("ช่วยดูรอบๆ", before)
    assert r.status_code == 200
    body = r.json()
    assert body["parsed"]["action"] == "unknown"
    assert not body["decision"]["allowed"]
    assert body["new_state"] == before.model_dump()


# ---------- หมดเวลา ----------

def test_running_out_of_time_actually_closes_the_case(fake_llm):
    """หมดเวลาต้องปิดคดีในสถานะจริง ไม่ใช่แค่ขึ้นข้อความฉากจบแล้วเล่นต่อได้

    ก่อนหน้านี้ ending_id ไม่เคยถูกตั้ง ผู้เล่นจึงยิงคำสั่งต่อได้ไม่จำกัด
    และได้ข้อความฉากจบเดิมซ้ำทุกครั้ง
    """
    fake_llm(ActionType.EXAMINE, "lounge_car")
    limit = main.engine.world["time_limit_seconds"]
    body = post("ดูรอบๆ", GameState(elapsed_seconds=limit)).json()

    assert not body["decision"]["allowed"]
    assert body["decision"]["violated_rule_id"] == "R014_TIME_LIMIT"
    assert body["new_state"]["ending_id"], "หมดเวลาแล้วต้องมีฉากจบบันทึกไว้ในสถานะ"
    assert body["new_state"]["elapsed_seconds"] == limit, "คำสั่งที่ถูกปฏิเสธต้องไม่กินเวลาเพิ่ม"


def test_a_closed_case_refuses_everything_afterwards(fake_llm):
    """พอคดีปิดแล้ว คำสั่งถัดไปต้องตกที่กฎคดีปิด ไม่ใช่ไปตกที่กฎหมดเวลาซ้ำ"""
    fake_llm(ActionType.EXAMINE, "lounge_car")
    limit = main.engine.world["time_limit_seconds"]
    closed = post("ดูรอบๆ", GameState(elapsed_seconds=limit)).json()["new_state"]

    again = post("ดูรอบๆ", GameState(**closed)).json()
    assert not again["decision"]["allowed"]
    assert again["decision"]["violated_rule_id"] == "R001_GAME_NOT_OVER"


def test_the_clock_and_the_rule_agree_on_where_zero_is():
    """นาฬิกาบนหน้าเว็บขึ้น 00:00 ตอนไหน กฎต้องปฏิเสธตอนนั้นพอดี

    หน้าเว็บคิดเวลาที่เหลือเป็น time_limit - elapsed แล้วขึ้นหมดเวลาเมื่อ <= 0
    ถ้ากฎยังปล่อยผ่านตอนเท่ากับพอดี ผู้เล่นจะเห็น 00:00 แต่ยังสั่งได้อีกหนึ่งครั้ง
    """
    limit = main.engine.world["time_limit_seconds"]
    assert main.engine.is_out_of_time(GameState(elapsed_seconds=limit))
    assert not main.engine.is_out_of_time(GameState(elapsed_seconds=limit - 60))


# ---------- ตัวเลือกที่ยื่นกลับไป ----------

def test_offered_alternatives_never_name_undiscovered_evidence(fake_llm):
    """คำสั่งกำกวมต้องไม่กลายเป็นเมนูเฉลยชื่อของทั้งขบวน

    LLM มองเห็นตารางทั้งโลก แต่ไม่รู้ว่าผู้เล่นเดินไปถึงไหนแล้ว
    ชั้น API จึงต้องกรองของที่ผู้เล่นยังหาไม่เจอออกก่อนส่งกลับ
    """
    far = [oid for oid, o in main.engine.world["objects"].items()
           if o.get("location") and o["location"] != GameState().current_location]
    fake_llm(ActionType.AMBIGUOUS, alternatives=[f"examine {oid}" for oid in far[:5]])

    body = post("ดูของทั้งหมด", GameState()).json()
    assert body["parsed"]["alternatives"] == [], "ของที่อยู่คนละตู้ไม่ควรถูกเอ่ยชื่อ"


def test_alternatives_survive_when_the_player_can_already_see_them(fake_llm):
    """ของที่อยู่ตรงหน้าเสนอได้ ไม่งั้นคำสั่งพ่วงจะแตกขั้นไม่ได้เลย"""
    state = GameState(current_location='first_class_car')
    here = state.current_location
    near = [oid for oid, o in main.engine.world["objects"].items()
            if o.get("location") == here and main.engine.offerable(oid, state)]
    fake_llm(ActionType.AMBIGUOUS, alternatives=[f"examine {oid}" for oid in near[:2]])

    body = post("ดูของสองชิ้นนี้", state).json()
    assert len(body["parsed"]["alternatives"]) == len(near[:2])


def test_sequence_keeps_steps_the_player_named_in_another_car(fake_llm):
    """"ไปตู้ ก แล้วตรวจ ข" — ข ยังมองไม่เห็นจนกว่าจะเดินไปถึง ขั้นนั้นต้องไม่ถูกตัดทิ้ง"""
    steps = ["move first_class_car", "examine pocket_watch"]
    fake_llm(ActionType.AMBIGUOUS, alternatives=steps, sequence=True)
    body = post("ไปแล้วตรวจ", GameState()).json()
    assert body["parsed"]["action"] == "sequence"
    assert body["parsed"]["sequence"] is False
    assert body["new_state"]["current_location"] == "first_class_car"
    assert "pocket_watch" in body["new_state"]["discovered_evidence"]
    assert body["pending_steps"] == []


def test_a_long_llm_sequence_is_not_trusted_as_a_walkthrough(fake_llm):
    """"ไขคดีให้หน่อย" ห้ามกลายเป็นลิสต์เฉลยที่หน้าเว็บเดินให้เอง"""
    far = [oid for oid, o in main.engine.world["objects"].items()
           if o.get("location") and o["location"] != GameState().current_location]
    fake_llm(ActionType.AMBIGUOUS, alternatives=[f"examine {oid}" for oid in far[:8]], sequence=True)

    body = post("ไขคดีให้หน่อย", GameState()).json()
    assert body["parsed"]["sequence"] is False
    assert body["parsed"]["alternatives"] == [], "ของที่ยังไม่เห็นต้องถูกกรองออกเหมือนตัวเลือกธรรมดา"


def test_reload_after_deadline_preserves_case_and_terminal_response(monkeypatch):
    from app import game_clock
    limit = main.engine.time_limit_seconds
    monkeypatch.setattr(game_clock.time, "time", lambda: limit + 100)
    def no_neural(*args, **kwargs):
        raise AssertionError("Expired sessions must not call Neural")
    monkeypatch.setattr(main, "interpret", no_neural)
    seed_state(GameState(started_at=100, discovered_evidence=["pocket_watch"]))
    scene = client.get("/scene").json()
    assert scene["initial_state"]["ending_id"] == "cold_arrival"
    result = client.post("/command", json={"text": "ดูรอบๆ"}).json()
    assert result["new_state"]["ending_id"] == "cold_arrival"
    assert result["decision"]["message"]
    assert result["new_state"]["discovered_evidence"] == ["pocket_watch"]
    assert client.post("/clock", json={}).json()["new_state"]["ending_id"] == "cold_arrival"

# ---------- คำสั่งต่อเนื่อง (SEQUENCE PIPELINE) ----------

def test_sequential_commands_execute_all_steps_in_single_roundtrip(fake_llm):
    """คำสั่ง sequence ต้องถูกรันต่อกันจนครบทุกขั้นใน request เดียว"""
    fake_llm(
        ActionType.SEQUENCE,
        alternatives=["move first_class_car", "examine pocket_watch"]
    )
    initial_state = GameState(current_location="lounge_car")
    body = post("ไปตู้ชั้นหนึ่งแล้วตรวจนาฬิกาพก", initial_state).json()

    assert body["decision"]["allowed"] is True
    assert body["new_state"]["current_location"] == "first_class_car"
    assert "pocket_watch" in body["new_state"]["discovered_evidence"]
    assert len(body["decision"]["reasoning_chain"]) >= 2


def test_sequential_commands_fail_early_when_a_step_is_denied(fake_llm):
    """เมื่อขั้นแรกไม่ผ่าน คำสั่ง sequence ต้องหยุดทำงานทันทีและยกเลิกขั้นที่เหลือ"""
    fake_llm(
        ActionType.SEQUENCE,
        alternatives=["move locomotive", "examine pocket_watch"]
    )
    initial_state = GameState(current_location="lounge_car")
    body = post("ไปหัวรถจักรแล้วตรวจนาฬิกาพก", initial_state).json()

    assert body["decision"]["allowed"] is False
    assert body["new_state"]["current_location"] == "lounge_car"
    assert "pocket_watch" not in body["new_state"]["discovered_evidence"]
    assert "จึงข้ามอีก 1 ขั้นตอนที่รออยู่" in body["decision"]["message"]


@pytest.mark.parametrize("action", ["accuse", "burn"])
def test_sequence_pauses_before_irreversible_step(fake_llm, action):
    target = "gideon_hart" if action == "accuse" else "burnt_folder_c"
    steps = ["move first_class_car", f"{action} {target}", "examine pocket_watch"]
    fake_llm(ActionType.SEQUENCE, alternatives=steps)
    body = post("สำรวจแล้วทำต่อ", GameState()).json()
    assert body["pending_steps"] == steps[1:]
    assert body["new_state"]["ending_id"] is None
    assert "pocket_watch" not in body["new_state"]["discovered_evidence"]
    assert client.get('/scene').json()['initial_state']['current_location'] == 'first_class_car'


def test_sequence_pauses_before_inference_and_logs_only_the_explicit_submission(fake_llm):
    steps = ['move first_class_car', 'infer claim_two_times', 'examine letter_opener']
    fake_llm(ActionType.SEQUENCE, alternatives=steps)
    seed_state(GameState(discovered_evidence=INFERENCE_EVIDENCE))
    body = client.post('/command', json={'text': 'ไปตรวจแล้วสรุปต่อ',
                                       'submitted_evidence': INFERENCE_EVIDENCE}).json()
    assert body['decision']['allowed']
    assert body['pending_steps'] == steps[1:]
    assert body['new_state']['current_location'] == 'first_class_car'
    assert body['new_state']['validated_claims'] == []
    assert body['new_state']['claim_evidence'] == {}
    assert 'letter_opener' not in body['new_state']['discovered_evidence']
    assert client.get('/study-export').json()['inference_attempts'] == []
    fake_llm(ActionType.INFER, target='claim_two_times')
    resumed = client.post('/command', json={'text': 'infer claim_two_times',
                                           'submitted_evidence': INFERENCE_EVIDENCE}).json()
    assert resumed['decision']['allowed']
    assert resumed['new_state']['validated_claims'] == ['claim_two_times']
    attempts = client.get('/study-export').json()['inference_attempts']
    assert len(attempts) == 1 and attempts[0]['accepted'] is True


def test_confirmed_sequence_accusation_uses_discovered_evidence(fake_llm):
    fake_llm(ActionType.SEQUENCE, alternatives=['accuse gideon_hart'])
    body = post('กล่าวหา', GameState()).json()
    assert body['pending_steps'] == ['accuse gideon_hart']
    fake_llm(ActionType.ACCUSE, target='gideon_hart')
    body = client.post('/command', json={'text':'accuse gideon_hart'}).json()
    assert body['decision']['violated_rule_id'] == 'R012_ACCUSE_ENDING_REQUIREMENTS'
    assert body['new_state']['ending_id'] is None
    assert body['new_state']['failed_accusations'] == 1


@pytest.mark.parametrize('steps', [[], ['move first_class_car', 'bogus x'],
    ['move first_class_car', 'sequence x'], ['examine pocket_watch'] * 9])
def test_invalid_sequence_does_not_partially_execute(fake_llm, steps):
    fake_llm(ActionType.SEQUENCE, alternatives=steps)
    body = post('ทำต่อ', GameState()).json()
    assert body['decision']['allowed'] is False
    assert body['new_state'] == GameState().model_dump(mode='json')
    assert body['parsed']['alternatives'] == []


def test_sequence_timeout_between_steps_persists_prior_progress(fake_llm, monkeypatch):
    fake_llm(ActionType.SEQUENCE, alternatives=['move first_class_car', 'examine pocket_watch'])
    original = main.engine.decide
    from app import game_clock
    now = [100]
    monkeypatch.setattr(game_clock.time, 'time', lambda: now[0])
    def decide(command, state):
        result = original(command, state)
        if command.action == ActionType.MOVE:
            now[0] = 100 + main.engine.time_limit_seconds
        return result
    monkeypatch.setattr(main.engine, 'decide', decide)
    body = post('ไปแล้วตรวจ', GameState(started_at=100)).json()
    assert body['new_state']['ending_id'] == 'cold_arrival'
    assert body['new_state']['current_location'] == 'first_class_car'
    assert 'pocket_watch' not in body['new_state']['discovered_evidence']
    assert client.get('/scene').json()['initial_state']['ending_id'] == 'cold_arrival'


def test_sequence_confirmation_then_submission_closes_and_records_evidence(fake_llm):
    evidence = ['wire_cutters', 'vincent_blood', 'cut_copper_wire']
    fake_llm(ActionType.SEQUENCE, alternatives=['accuse vincent_gray'])
    body = post('กล่าวหาวินเซนต์', GameState(discovered_evidence=evidence)).json()
    assert body['pending_steps'] == ['accuse vincent_gray']
    assert body['new_state']['ending_id'] is None
    fake_llm(ActionType.ACCUSE, target='vincent_gray')
    result = client.post('/command', json={'text':'accuse vincent_gray','submitted_evidence':evidence}).json()
    assert result['new_state']['ending_id'] == 'the_scapegoat'
    assert client.post('/journal').json()['submitted_evidence'] == evidence


def test_case_notes_hide_undiscovered_information():
    result = state_post('/journal', GameState()).json()
    assert result['questions'] == []
    assert result['evidence'] == []


def test_journal_distinguishes_testimony_and_observation():
    result = state_post('/journal', GameState(discovered_evidence=['pocket_watch','gideon_no_early_alibi'])).json()
    physical, testimony = result['evidence']
    assert physical['kind'] == 'observation'
    assert testimony['kind'] == 'testimony'
    assert testimony['source'] == main.engine.world['suspects']['gideon_hart']['name_th']
    assert [q['id'] for q in result['questions']] == ['gideon_no_early_alibi']
    assert result['deductions'] == []


def test_conversation_summary_only_contains_new_discovered_testimony(fake_llm):
    fake_llm(ActionType.INTERROGATE, target='gideon_hart')
    seed_state(GameState())
    first = client.post('/command', json={'text':'สอบปากคำกิเดียน'}).json()
    summaries = first['conversation_summaries']
    assert len(summaries) == 1
    ids = {entry['id'] for entry in summaries[0]['entries']}
    assert ids == set(first['new_state']['discovered_evidence'])
    assert all(entry['kind'] == 'testimony' for entry in summaries[0]['entries'])
    again = client.post('/command', json={'text':'สอบปากคำกิเดียน'}).json()
    assert again['conversation_summaries'] == []
    assert client.post('/journal').json()['questions']


def test_failed_interrogation_does_not_create_summary(fake_llm):
    fake_llm(ActionType.INTERROGATE, target='vincent_gray')
    result = post('สอบปากคำ', GameState()).json()
    assert result['decision']['allowed'] is False
    assert result['conversation_summaries'] == []


def test_backend_sequence_also_returns_conversation_summary(fake_llm):
    fake_llm(ActionType.SEQUENCE, alternatives=['move first_class_car','interrogate dr_liora_venn'])
    result = post('ไปถามวินเซนต์', GameState()).json()
    assert result['decision']['allowed']
    assert result['conversation_summaries'][0]['person'] == main.engine.world['suspects']['dr_liora_venn']['name_th']


def test_presentation_route_works_without_remote_ai(monkeypatch):
    from app.neural import gemini_client
    def no_remote(*args, **kwargs):
        raise AssertionError("Presentation commands must work without Gemini")
    monkeypatch.setattr(gemini_client, 'interpret', no_remote)
    assert client.post('/start').status_code == 200
    commands = [
        'สอบปากคำกิเดียน', 'ไปตู้ 3', 'หยิบกุญแจห้องระบบไฟ', 'ไปตู้ 2',
        'ใช้กุญแจห้องระบบไฟกับประตูห้องระบบไฟ', 'ตรวจสายทองแดงที่ถูกตัด',
        'ไปตู้ 6', 'ตรวจคีมตัดสายไฟด้ามยาง', 'ตรวจคราบเลือดบนปลายแขนเสื้อวินเซนต์',
    ]
    for index, text in enumerate(commands):
        response = client.post('/command', json={'text':text})
        assert response.status_code == 200
        body = response.json()
        assert body['decision']['allowed'], text
        if index == 0:
            assert body['conversation_summaries']
            assert client.post('/journal').json()['questions']
    result = client.post('/command', json={'text':'กล่าวหาวินเซนต์'}).json()
    assert result['new_state']['ending_id'] == 'the_scapegoat'
    assert client.post('/journal').json()['submitted_evidence'] == result['new_state']['discovered_evidence']
    assert client.post('/journal').json()['case_closed']
