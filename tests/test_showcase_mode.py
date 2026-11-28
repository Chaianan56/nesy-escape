"""ของที่เพิ่มสำหรับเปิดให้คนอื่นลองเล่น: ผู้เล่าหลีกทางเมื่อโควตาตึง บันทึกประโยคที่พลาด และแถบเคล็ดลับ"""
import json
import time
from pathlib import Path
from types import SimpleNamespace

from app.neural import gemini_client, narrator
from app import parser_log
from app.schemas import ActionType, Decision, ParsedCommand

ROOT = Path(__file__).resolve().parents[1]
WORLD = {"objects": {}, "suspects": {}, "locations": {}}


# ---------- ผู้เล่าหลีกทางให้ตัวแปลคำสั่ง ----------

def test_narrator_steps_aside_right_after_a_key_hits_its_limit(monkeypatch):
    called = []
    monkeypatch.setattr(narrator, "_generate", lambda *a, **k: called.append(1) or (["x"], "fake"))
    monkeypatch.setattr(narrator, "_paused_until", 0.0)
    monkeypatch.setattr(gemini_client, "_key_statuses",
                        {1: {"state": "quota_exceeded", "since": time.time() - 30, "per_day": False}})
    out, info = narrator.narrate_messages(["ข้อความเดิม"], "ดูรอบๆ", WORLD)
    assert out == ["ข้อความเดิม"] and info["reason"] == "quota_guard" and not called


def test_old_minute_limit_no_longer_blocks_but_a_recent_daily_one_does(monkeypatch):
    monkeypatch.setattr(gemini_client, "_key_statuses",
                        {1: {"state": "quota_exceeded", "since": time.time() - 300, "per_day": False}})
    assert gemini_client.recent_quota_trouble() is False
    monkeypatch.setattr(gemini_client, "_key_statuses",
                        {1: {"state": "quota_exceeded", "since": time.time() - 300, "per_day": True}})
    assert gemini_client.recent_quota_trouble() is True


def test_narrator_pauses_itself_after_its_own_quota_error(monkeypatch):
    monkeypatch.setattr(narrator, "_paused_until", 0.0)
    monkeypatch.setattr(gemini_client, "_key_statuses", {})

    def failing(*a, **k):
        raise RuntimeError("no narrator provider succeeded") from RuntimeError("429 RESOURCE_EXHAUSTED per day limit")
    monkeypatch.setattr(narrator, "_generate", failing)
    narrator.narrate_messages(["ข้อความ"], "ตรวจนาฬิกา", WORLD)
    assert narrator._paused_until - time.time() > narrator.QUOTA_PAUSE_SECONDS     # ติดรายวัน หยุดนานกว่า
    out, info = narrator.narrate_messages(["ข้อความ"], "ตรวจนาฬิกา", WORLD)
    assert info["reason"] == "quota_guard"


# ---------- บันทึกประโยคที่ตัวแปลคำสั่งพลาด ----------

def result(action, allowed, mode="gemini_knn", service_error=None):
    return SimpleNamespace(parsed=ParsedCommand(action=action, raw_text="x", parser_mode=mode),
                           decision=Decision(allowed=allowed, message="m", violated_rule_id=None if allowed else "R009"),
                           service_error=service_error)


def test_log_records_only_ai_misses(monkeypatch, tmp_path):
    log = tmp_path / "misses.jsonl"
    monkeypatch.setattr(parser_log, "LOG_PATH", log)
    monkeypatch.setenv("PARSER_LOG", "on")
    assert parser_log.log_if_missed("กระดาษในเสื้อเขาเขียนว่าอะไร", result(ActionType.UNKNOWN, False), "case_02_vincent", "second_class_car")
    assert not parser_log.log_if_missed("ตรวจนาฬิกาพกกลไก", result(ActionType.EXAMINE, False, mode="typed"), "c", "l")
    assert not parser_log.log_if_missed("ไปดูห้องที่เกิดเหตุ", result(ActionType.MOVE, True), "c", "l")
    rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["text"] == "กระดาษในเสื้อเขาเขียนว่าอะไร" and rows[0]["parsed"]["action"] == "unknown"


def test_log_is_off_during_tests_unless_asked(monkeypatch, tmp_path):
    log = tmp_path / "misses.jsonl"
    monkeypatch.setattr(parser_log, "LOG_PATH", log)
    monkeypatch.delenv("PARSER_LOG", raising=False)
    assert not parser_log.log_if_missed("x", result(ActionType.UNKNOWN, False), "c", "l")
    assert not log.exists()


def test_log_file_is_not_committed():
    assert "data/telemetry/*.jsonl" in (ROOT / ".gitignore").read_text(encoding="utf-8")


# ---------- แถบเคล็ดลับเหนือช่องพิมพ์ ----------

def test_tip_bar_is_on_the_page_and_hides_itself():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "frontend" / "js" / "chat.js").read_text(encoding="utf-8")
    assert 'id="playTips"' in html and 'id="closeTips"' in html
    assert "TIPS_HIDE_AFTER = 3" in js and "countCommandForTips();" in js
