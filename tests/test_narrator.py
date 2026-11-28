"""ผู้เล่าเรื่อง: AI เรียบเรียงข้อความได้ แต่ห้ามเฉลย ห้ามเพิ่มหรือทำข้อมูลหาย และห้ามแตะผลตัดสิน

เทสต์ทั้งหมดสวมตัวปลอมแทนการเรียก AI จริง
"""
import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.neural import narrator
from app.neural.narrator import narrate_messages, validate_narration
from app.schemas import ActionType, GameState, ParsedCommand

WORLD = main.engine.world


def fake_generate(replies):
    def generate(sources, player_text, provider):
        out = replies(sources) if callable(replies) else replies
        return list(out), "fake:model"
    return generate


# ---------- ตัวตรวจ ----------

def test_faithful_rewrite_passes():
    source = "นาฬิกาพกกลไก กระจกแตกร้าว เข็มค้างที่ 20:25"
    rewrite = "คุณหยิบนาฬิกาพกกลไกขึ้นมาดู กระจกร้าวเป็นทาง เข็มหยุดนิ่งอยู่ที่ 20:25"
    assert validate_narration(source, rewrite, "ตรวจนาฬิกา", WORLD) is None


@pytest.mark.parametrize("rewrite, reason", [
    ("นาฬิกาพกกลไกแตก เข็มค้างที่ 20:25 ตรงกับเวลาตายตอน 20:22", "new_number"),
    ("นาฬิกาพกกลไกแตกร้าว เข็มค้างอยู่", "dropped_number"),
    ("นาฬิกาพกกลไกค้างที่ 20:25 ใกล้ๆ มีกระดุมเย็บติดแขนเสื้อ", "new_entity"),
    ("กระจกแตกร้าว เข็มค้างที่ 20:25", "dropped_entity"),
    ("นาฬิกาพกกลไกค้างที่ 20:25 ฆาตกรคงทำมันตกตอนต่อสู้", "spoiler_cue"),
    ("นาฬิกาพกกลไก (pocket_watch) ค้างที่ 20:25", "leaked_id"),
    ("", "empty"),
])
def test_unfaithful_rewrites_are_rejected(rewrite, reason):
    source = "นาฬิกาพกกลไก กระจกแตกร้าว เข็มค้างที่ 20:25"
    assert validate_narration(source, rewrite, "ตรวจนาฬิกา", WORLD) == reason


def test_quoted_testimony_must_stay_verbatim():
    source = 'กิเดียนตอบว่า “ผมอยู่ในตู้เลานจ์ตลอดเวลา”'
    assert validate_narration(source, "กิเดียนยืนยันว่าเขาอยู่ตู้เลานจ์ตลอด", "", WORLD) == "dropped_quote"
    assert validate_narration(source, 'กิเดียนเงยหน้าแล้วตอบว่า “ผมอยู่ในตู้เลานจ์ตลอดเวลา”', "", WORLD) is None


def test_possessive_khong_does_not_change_the_name():
    """'แหวนตราของกิเดียน' กับ 'แหวนตรากิเดียน' คือสิ่งเดียวกัน ไม่นับเป็นชื่อใหม่หรือชื่อหาย"""
    assert validate_narration("แหวนตรากิเดียนมีรอยบิ่น", "แหวนตราของกิเดียนมีรอยบิ่น", "", WORLD) is None
    assert validate_narration("ตลับยาอมกิเดียนอยู่บนโต๊ะ", "ตลับยาอมของกิเดียนวางอยู่บนโต๊ะ", "", WORLD) is None
    assert validate_narration("ตลับยาอมกิเดียนอยู่บนโต๊ะ", "ตลับยาอมกิเดียนอยู่ข้างแหวนตราของกิเดียน",
                              "", WORLD) == "new_entity"


def test_stray_foreign_script_is_rejected():
    source = "ตู้เสบียงอบอวลด้วยกลิ่นชาเอิร์ลเกรย์"
    assert validate_narration(source, "ตู้เสบียงหอมกลิ่นชาเอิร์לเกรย์", "", WORLD) == "foreign_script"
    assert validate_narration(source, "คุณก้าวเข้าตู้เสบียง กลิ่นชาเอิร์ลเกรย์ลอยมา — อบอุ่น 💡", "", WORLD) is None


def test_station_must_not_become_a_tunnel():
    source = "บันทึกเดินรถ: อุโมงค์แบล็กโฮล 20:20–20:26; ฮัลเบิร์ด 20:45"
    bad = "รถผ่านอุโมงค์แบล็กโฮล 20:20–20:26 และอุโมงค์ฮัลเบิร์ด 20:45"
    good = "ตามบันทึกเดินรถ รถผ่านอุโมงค์ช่วง 20:20–20:26 ในอุโมงค์แบล็กโฮล แล้วถึงสถานีฮัลเบิร์ด 20:45"
    assert validate_narration(source, bad, "ผ่านอุโมงค์ช่วงไหน", WORLD) == "wrong_place_type"
    assert validate_narration(source, good, "ผ่านอุโมงค์ช่วงไหน", WORLD) is None
    assert validate_narration(source, "รถผ่านสถานีแบล็กโฮล 20:20–20:26 แล้วถึงฮัลเบิร์ด 20:45",
                              "", WORLD) == "wrong_place_type"


def test_narrator_must_not_decide_a_characters_feelings():
    source = "กิเดียนหยุดก่อนตอบ “ผมอาจจำผู้ส่งข่าวคลาดเคลื่อน”"
    bad = "กิเดียนไม่ได้แสดงความกังวล เขาหยุดก่อนตอบ “ผมอาจจำผู้ส่งข่าวคลาดเคลื่อน”"
    good = "กิเดียนเงียบไปครู่หนึ่งก่อนตอบ “ผมอาจจำผู้ส่งข่าวคลาดเคลื่อน”"
    assert validate_narration(source, bad, "กิเดียนดูกังวลไหม", WORLD) == "new_emotion"
    assert validate_narration(source, good, "กิเดียนดูกังวลไหม", WORLD) is None


def test_player_may_name_things_the_narrator_echoes():
    source = "คุณไม่ได้อยู่ในตู้เดียวกับสิ่งนี้"
    rewrite = "นาฬิกาพกกลไกไม่ได้อยู่ใกล้คุณ คุณไม่ได้อยู่ในตู้เดียวกับมัน"
    assert validate_narration(source, rewrite, "ตรวจนาฬิกาพกกลไก", WORLD) is None


# ---------- การเรียบเรียง ----------

def test_rejected_items_fall_back_to_engine_text(monkeypatch):
    monkeypatch.setattr(narrator, "_generate", fake_generate(["ฆาตกรคือคนที่คุณคิด", "ไปต่อกันเลย"]))
    out, info = narrate_messages(["ประตูล็อกอยู่", "เดินทางต่อ"], "เปิดประตู", WORLD)
    assert out == ["ประตูล็อกอยู่", "ไปต่อกันเลย"]
    assert [i["accepted"] for i in info["items"]] == [False, True]


def test_provider_failure_keeps_engine_text(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("down")
    monkeypatch.setattr(narrator, "_generate", boom)
    out, info = narrate_messages(["ประตูล็อกอยู่"], "เปิดประตู", WORLD)
    assert out == ["ประตูล็อกอยู่"] and info["applied"] is False


def test_system_hints_are_kept_verbatim_and_not_sent(monkeypatch):
    seen = {}
    def generate(sources, player_text, provider):
        seen["sources"] = sources
        return ["ประตูบานนี้ยังล็อกแน่น"], "fake"
    monkeypatch.setattr(narrator, "_generate", generate)
    hint = "💡 *[ข้อสังเกตของผู้สืบสวน]*: ลองหากุญแจ"
    out, _ = narrate_messages([f"ประตูล็อกอยู่\n\n{hint}"], "เปิดประตู", WORLD)
    assert seen["sources"] == ["ประตูล็อกอยู่"]
    assert out == [f"ประตูบานนี้ยังล็อกแน่น\n\n{hint}"]


def test_narrator_is_off_under_pytest_by_default(monkeypatch):
    monkeypatch.delenv("NARRATOR", raising=False)
    assert narrator.narrator_enabled() is False
    monkeypatch.setenv("NARRATOR", "off")
    assert narrator.narrator_enabled() is False


# ---------- ผ่าน API: แก้ได้แค่ข้อความ ----------

def test_api_narration_changes_only_the_message(monkeypatch):
    client = TestClient(main.app)
    client.get("/scene?case_id=case_01_gideon")
    client.post("/start")
    monkeypatch.setattr(main, "interpret", lambda text, state, **k: ParsedCommand(
        action=ActionType.MOVE, target="first_class_car", raw_text=text, confidence=1.0))

    plain = client.post("/command", json={"text": "ไปตู้ 4"}).json()

    client.get("/scene?case_id=case_01_gideon")
    client.cookies.clear()
    client.get("/scene?case_id=case_01_gideon")
    client.post("/start")
    monkeypatch.setattr(main, "narrator_enabled", lambda: True)
    monkeypatch.setattr(narrator, "_generate", fake_generate(lambda s: s))  # คืนต้นฉบับ = ผ่านการตรวจแน่นอน
    narrated = client.post("/command", json={"text": "ไปตู้ 4"}).json()

    assert narrated["narration"]["applied"] is True
    assert narrated["narration"]["original_message"] == plain["decision"]["message"]
    for key in ("allowed", "reasoning_chain", "violated_rule_id", "state_changes"):
        assert narrated["decision"][key] == plain["decision"][key]
    assert narrated["new_state"]["current_location"] == plain["new_state"]["current_location"]


def test_narrator_must_stay_inside_the_story():
    source = "ไม่เข้าใจคำสั่งนี้ สิ่งที่ทำได้คือ ดูรอบๆ เดินไปตู้อื่น"
    assert validate_narration(source, "ระบบไม่เข้าใจคำสั่งนี้ สิ่งที่ทำได้คือ ดูรอบๆ เดินไปตู้อื่น", "", WORLD) == "meta_talk"
    quote = "“ผมอาจจำผู้ส่งข่าวคลาดเคลื่อน”"
    assert validate_narration(quote, "ข้อความต้นฉบับไม่ได้บอกไว้ มีเพียง " + quote, "", WORLD) == "meta_talk"
    assert validate_narration(source, "คุณเอ่ยถามออกไปแต่ไม่มีใครตอบ สิ่งที่ทำได้คือ ดูรอบๆ เดินไปตู้อื่น", "", WORLD) is None
    # คำว่าต้นฉบับในเนื้อเรื่องเองไม่นับ
    story = "กระเป๋ามีแฟ้ม B สมุดต้นฉบับแอนเซลม์"
    assert validate_narration(story, "ในกระเป๋ามีแฟ้ม B คือสมุดต้นฉบับแอนเซลม์", "", WORLD) is None


@pytest.mark.parametrize("text, narrated", [
    ("ดูรอบๆ", False),            # หน้าเว็บส่งเองตอนกด "คลิกเพื่อไปต่อ" และตอนเริ่มเกม
    ("สำรวจห้อง", False),
    ("ห้องนี้มีอะไรแปลกๆ ไหม", True),  # คำถามธรรมชาติยังเรียบเรียงตามปกติ
])
def test_plain_look_around_skips_the_narrator(monkeypatch, text, narrated):
    calls = []
    def generate(sources, player_text, provider):
        calls.append(player_text)
        return list(sources), "fake:model"
    client = TestClient(main.app)
    client.cookies.clear()
    client.get("/scene?case_id=case_01_gideon")
    client.post("/start")
    monkeypatch.setattr(main, "interpret", lambda t, state, **k: ParsedCommand(
        action=ActionType.EXAMINE, target=state.current_location, raw_text=t, confidence=1.0))
    monkeypatch.setattr(main, "narrator_enabled", lambda: True)
    monkeypatch.setattr(narrator, "_generate", generate)
    reply = client.post("/command", json={"text": text}).json()
    assert reply["decision"]["allowed"] is True
    assert bool(calls) is narrated
    assert (reply.get("narration") is not None) is narrated
