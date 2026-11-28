"""หน้าต่างเลือกบริการ AI: แสดงเฉพาะคีย์ที่ใช้ได้ และกดบริการที่ไม่มีคีย์ใช้ได้ไม่ได้

ไม่ต่อเน็ต: ใช้ไคลเอนต์ปลอมแทน Gemini และแทน httpx.get สำหรับ Groq/GPT
"""
import json
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main
from app.neural import gemini_client, key_check, narrator
from app.schemas import ActionType, GameState

ROOT = Path(__file__).resolve().parents[1]


class RejectedKey(Exception):
    code = 400

    def __init__(self):
        super().__init__("400 INVALID_ARGUMENT. API key not valid. Please pass a valid API key.")


def fake_client(key, valid=True, calls=None):
    def get(**kwargs):
        if not valid:
            raise RejectedKey()
        return SimpleNamespace(name="models/x")

    def generate_content(**kwargs):
        if calls is not None:
            calls.append(key)
        if not valid:
            raise RejectedKey()
        reply = {"action": "examine", "target": "wall_clock", "raw_text": "x", "confidence": 1.0, "alternatives": []}
        return SimpleNamespace(text=json.dumps(reply), usage_metadata=None)

    return SimpleNamespace(_api_client=SimpleNamespace(api_key=key),
                           models=SimpleNamespace(get=get, generate_content=generate_content))


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    monkeypatch.setenv("KEY_CHECK", "on")
    monkeypatch.setattr(key_check, "_results", {})
    monkeypatch.setattr(gemini_client, "_key_statuses", {})
    monkeypatch.setattr(gemini_client, "_last_api_status", None)
    monkeypatch.setattr(gemini_client, "_active_key_index", 1)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def use_clients(monkeypatch, clients):
    monkeypatch.setattr(gemini_client, "_clients", lambda: clients)
    monkeypatch.setattr(main, "_clients", lambda: clients)


def test_rejected_key_is_hidden_and_never_shown_as_active(monkeypatch):
    bad, good = fake_client("bad", valid=False), fake_client("good")
    use_clients(monkeypatch, [bad, good])
    gemini_client.refresh_key_checks()
    status = gemini_client.get_api_status()
    rows = {k["label"]: k for k in status["keys"]}
    assert rows["Key 1"]["usable"] is False and rows["Key 1"]["is_active"] is False
    assert rows["Key 2"]["usable"] is True and status["active_key"] == 2


def test_parser_skips_a_rejected_key(monkeypatch):
    calls = []
    use_clients(monkeypatch, [fake_client("bad", valid=False, calls=calls), fake_client("good", calls=calls)])
    gemini_client.refresh_key_checks()
    parsed = gemini_client.interpret("ดูนาฬิกา", GameState(), enable_repair=False)
    assert parsed.action == ActionType.EXAMINE and calls == ["good"]


def test_a_key_rejected_during_play_is_remembered(monkeypatch):
    """ตรวจไม่ทัน (เช่นเน็ตกระตุกตอนตรวจ) แต่การเรียกจริงโดนปฏิเสธ ต้องจำไว้และไม่ลองซ้ำ"""
    calls = []
    use_clients(monkeypatch, [fake_client("bad", valid=False, calls=calls), fake_client("good", calls=calls)])
    gemini_client.interpret("ดูนาฬิกา", GameState(), enable_repair=False)
    gemini_client._active_key_index = 1
    calls.clear()
    gemini_client.interpret("ดูนาฬิกา", GameState(), enable_repair=False)
    assert calls == ["good"]
    assert gemini_client.get_api_status()["keys"][0]["usable"] is False


def test_daily_quota_hides_a_key_until_pacific_midnight(monkeypatch):
    use_clients(monkeypatch, [fake_client("a"), fake_client("b")])
    gemini_client._key_statuses[1] = {"state": "quota_exceeded", "since": time.time(), "per_day": True}
    assert [k["usable"] for k in gemini_client.get_api_status()["keys"]] == [False, True]
    gemini_client._key_statuses[1]["per_day"] = False          # รายนาทีกลับมาเร็ว ยังแสดง
    assert [k["usable"] for k in gemini_client.get_api_status()["keys"]] == [True, True]

    since = datetime(2026, 11, 28, 23, 30, tzinfo=key_check.QUOTA_RESET_ZONE).timestamp()
    reset = datetime.fromtimestamp(key_check.daily_quota_resets_at(since), key_check.QUOTA_RESET_ZONE)
    assert (reset.day, reset.hour, reset.minute) == (29, 0, 0)


def test_unreachable_key_is_hidden_briefly_and_rechecked(monkeypatch):
    """ติดต่อไม่ได้ก็ใช้ไม่ได้ตอนนี้ แต่ตรวจใหม่หลังหนึ่งนาที ไม่ใช่สิบนาที"""
    online = []
    def get(**kwargs):
        if not online:
            raise httpx.ConnectError("offline")
        return SimpleNamespace(name="models/x")
    client = fake_client("k")
    client.models.get = get
    use_clients(monkeypatch, [client])
    gemini_client.refresh_key_checks()
    row = gemini_client.get_api_status()["keys"][0]
    assert row["usable"] is False and row["message"] == gemini_client.KEY_PROBLEM_MESSAGES["unreachable"]

    online.append(1)
    gemini_client.refresh_key_checks()                       # ยังไม่ครบนาที ไม่ตรวจซ้ำ
    assert gemini_client.get_api_status()["keys"][0]["usable"] is False
    real_time = time.time
    monkeypatch.setattr(key_check.time, "time", lambda: real_time() + key_check.RETRY_UNREACHABLE + 1)
    gemini_client.refresh_key_checks()
    assert gemini_client.get_api_status()["keys"][0]["usable"] is True


def test_provider_buttons_follow_real_key_checks(monkeypatch):
    use_clients(monkeypatch, [fake_client("bad", valid=False)])
    monkeypatch.setenv("GROQ_API_KEY", "groq-bad")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-good")
    monkeypatch.setattr(httpx, "get", lambda url, **kw: httpx.Response(401 if "groq" in url else 200))
    with TestClient(main.app) as client:
        client.get("/scene")
        options = client.get("/api-provider").json()
        assert options["available"] == {"auto": True, "gemini": False, "openai": True, "groq": False}
        assert options["reasons"]["gemini"] == "ไม่มีคีย์ที่ใช้ได้"
        assert options["reasons"]["groq"] == gemini_client.KEY_PROBLEM_MESSAGES["invalid"]
        rejected = client.post("/api-provider", json={"provider": "groq"})
        assert rejected.status_code == 400 and rejected.json()["detail"] == options["reasons"]["groq"]
        assert client.post("/api-provider", json={"provider": "openai"}).json()["selected"] == "openai"
        rows = options["api_status"]["keys"]
        assert [(r["label"], r["usable"]) for r in rows] == [("Key 1", False), ("Groq", False), ("GPT", True)]


def test_selection_falls_back_to_auto_when_its_key_stops_working(monkeypatch):
    use_clients(monkeypatch, [fake_client("good")])
    with TestClient(main.app) as client:
        client.get("/scene")
        assert client.post("/api-provider", json={"provider": "gemini"}).json()["selected"] == "gemini"
        key_check.mark_gemini_invalid(gemini_client._clients()[0])
        assert client.get("/api-provider").json()["selected"] == "auto"


def test_narrator_skips_a_rejected_key(monkeypatch):
    calls = []
    use_clients(monkeypatch, [fake_client("bad", valid=False, calls=calls), fake_client("good", calls=calls)])
    gemini_client.refresh_key_checks()
    monkeypatch.setattr(gemini_client, "types", SimpleNamespace(
        GenerateContentConfig=lambda **kw: None, HttpOptions=lambda **kw: None, HttpRetryOptions=lambda **kw: None))
    narrator._call_gemini("system", "content")
    assert calls == ["good"]


def test_checks_never_run_during_tests_by_default(monkeypatch):
    monkeypatch.delenv("KEY_CHECK")
    use_clients(monkeypatch, [fake_client("bad", valid=False)])
    gemini_client.refresh_key_checks()
    assert key_check._results == {}


def test_popup_lists_only_usable_keys():
    source = (ROOT / "frontend" / "js" / "chat.js").read_text(encoding="utf-8")
    assert "info.keys.filter(k => k.usable !== false)" in source
    assert "providerOptions?.reasons?.[name]" in source
