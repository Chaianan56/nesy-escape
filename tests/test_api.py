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


@pytest.fixture
def fake_llm(monkeypatch):
    """สวม interpret() ด้วยตัวปลอม เรียกใช้ด้วย fake_llm(action, target, ...)

    ทดสอบท่อ ไม่ได้ทดสอบ Gemini การตีความภาษาไทยจริงอยู่ใน test_neural.py
    """
    def install(action, target=None, alternatives=None, raises=None):
        def fake(text, state):
            if raises:
                raise raises
            return ParsedCommand(action=action, target=target, raw_text=text,
                                 confidence=1.0, alternatives=alternatives or [])
        monkeypatch.setattr(main, "interpret", fake)
    return install


def post(text, state):
    return client.post("/command", json={"text": text, "state": state.model_dump()})


# ---------- ทะเบียนฉาก ----------

def test_scene_hands_out_the_ids_the_engine_actually_uses():
    """frontend กับ neural ต้องดึงทะเบียน id จากที่เดียวกับที่ engine ใช้ตัดสิน"""
    s = client.get("/scene").json()
    assert s["rules_count"] == len(main.engine.rules)
    assert set(s["locations"]) == set(main.engine.world["locations"])
    assert set(s["objects"]) == set(main.engine.world["objects"])
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
    assert body["new_state"]["elapsed_seconds"] > 0
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
