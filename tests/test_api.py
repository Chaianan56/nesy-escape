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

import pytest
from fastapi.testclient import TestClient

from app import main
from app.schemas import ActionType, GameState, ParsedCommand

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
    state = GameState(discovered_evidence=['pocket_watch', 'liora_time_estimate'])
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
    body = post("accuse", state).json()
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
    assert denied["new_state"] == state.model_dump()
    state.discovered_evidence.append("cut_copper_wire")
    allowed = post("กล่าวหาวินเซนต์", state).json()
    assert allowed["decision"]["allowed"]
    assert allowed["new_state"]["ending_id"] == "the_scapegoat"


@pytest.mark.parametrize('submission', [None, [], ['unknown'], ['wire_cutters', 'wire_cutters']])
def test_accusation_rejects_missing_or_invalid_submission(fake_llm, submission):
    fake_llm(ActionType.ACCUSE, 'vincent_gray')
    state = GameState(discovered_evidence=['wire_cutters', 'vincent_blood', 'cut_copper_wire'])
    seed_state(state)
    result = client.post('/command', json={'text': 'กล่าวหาวินเซนต์', 'submitted_evidence': submission}).json()
    assert result['decision']['violated_rule_id'] == 'R_SUBMITTED_EVIDENCE'
    assert result['new_state'] == state.model_dump()


def test_submission_not_entire_inventory_decides_ending(fake_llm):
    fake_llm(ActionType.ACCUSE, 'gideon_hart')
    state = GameState(discovered_evidence=list(main.engine.world['objects']))
    seed_state(state)
    selected = ['dossier_missing_file_c', 'burnt_folder_c', 'file_c_initials']
    result = client.post('/command', json={'text': 'กล่าวหากิเดียน', 'submitted_evidence': selected}).json()
    assert result['decision']['allowed']
    assert result['new_state']['ending_id'] == 'cold_justice'
    assert result['new_state']['discovered_evidence'] == state.discovered_evidence
    journal = client.post('/journal').json()
    assert journal['submitted_evidence'] == selected
    assert 'D01_TRUE_MURDER_WINDOW' not in {d['id'] for d in journal['deductions']}
    client.post('/new-game')
    assert client.post('/journal').json()['submitted_evidence'] is None


def test_cannot_omit_known_exculpatory_evidence(fake_llm):
    fake_llm(ActionType.ACCUSE, 'vincent_gray')
    selected = ['wire_cutters', 'vincent_blood', 'cut_copper_wire']
    seed_state(GameState(discovered_evidence=selected + ['pocket_watch', 'liora_time_estimate']))
    result = client.post('/command', json={'text': 'กล่าวหาวินเซนต์', 'submitted_evidence': selected}).json()
    assert not result['decision']['allowed']
    assert result['new_state']['ending_id'] is None


# ---------- ทะเบียนฉาก ----------

def test_scene_hands_out_the_ids_the_engine_actually_uses():
    """frontend กับ neural ต้องดึงทะเบียน id จากที่เดียวกับที่ engine ใช้ตัดสิน"""
    s = client.get("/scene").json()
    assert s["rules_count"] == len(main.engine.rules)
    assert set(s["locations"]) == set(main.engine.world["locations"])
    assert set(s["objects"]) == {oid for oid in main.engine.world["objects"] if main.engine.offerable(oid, GameState())}
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


def test_the_api_says_which_layer_failed_when_gemini_is_down(fake_llm):
    """ชั้น neural ล้มต้องตอบ 502 พร้อมบอกว่าล้มที่ชั้นไหน ไม่ใช่ 500 เปล่าๆ"""
    fake_llm(ActionType.EXAMINE, raises=RuntimeError("โควตาหมด"))
    r = post("ดูรอบๆ", GameState())
    assert r.status_code == 502
    assert "Neural" in r.json()["detail"]


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
    here = GameState().current_location
    near = [oid for oid, o in main.engine.world["objects"].items()
            if o.get("location") == here]
    fake_llm(ActionType.AMBIGUOUS, alternatives=[f"examine {oid}" for oid in near[:2]])

    body = post("ดูของสองชิ้นนี้", GameState()).json()
    assert len(body["parsed"]["alternatives"]) == len(near[:2])


def test_sequence_keeps_steps_the_player_named_in_another_car(fake_llm):
    """"ไปตู้ ก แล้วตรวจ ข" — ข ยังมองไม่เห็นจนกว่าจะเดินไปถึง ขั้นนั้นต้องไม่ถูกตัดทิ้ง"""
    far = next(oid for oid, o in main.engine.world["objects"].items()
               if o.get("location") and o["location"] != GameState().current_location)
    steps = [f"move {main.engine.world['objects'][far]['location']}", f"examine {far}"]
    fake_llm(ActionType.AMBIGUOUS, alternatives=steps, sequence=True)

    body = post("ไปแล้วตรวจ", GameState()).json()
    assert body["parsed"]["alternatives"] == steps
    assert body["new_state"] == GameState().model_dump(mode="json"), "ตัวคำสั่งพ่วงเองต้องไม่เปลี่ยนสถานะ"
