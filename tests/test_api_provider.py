from fastapi.testclient import TestClient

from app import main
from app.neural import openai_client
from app.schemas import ParsedCommand


def test_provider_selection_is_session_local_and_validated(monkeypatch):
    monkeypatch.setattr(main, "_clients", lambda: [object()])
    monkeypatch.setattr(openai_client, "configured", lambda **kw: True)
    with TestClient(main.app) as a, TestClient(main.app) as b:
        a.get("/scene")
        b.get("/scene")
        assert a.post("/api-provider", json={"provider": "openai"}).json()["selected"] == "openai"
        assert a.get("/api-provider").json()["selected"] == "openai"
        assert b.get("/api-provider").json()["selected"] == "auto"
        assert a.post("/api-provider", json={"provider": "evil"}).status_code == 422
        monkeypatch.setattr(openai_client, "configured", lambda **kw: False)
        assert b.post("/api-provider", json={"provider": "openai"}).status_code == 400
        assert b.get("/api-provider").json()["selected"] == "auto"


def test_command_uses_selected_provider(monkeypatch):
    monkeypatch.setattr(openai_client, "configured", lambda **kw: True)
    seen = []
    def interpret(text, state, **kwargs):
        seen.append(kwargs.get("provider"))
        return ParsedCommand(action="ambiguous", raw_text=text)
    monkeypatch.setattr(main, "interpret", interpret)
    with TestClient(main.app) as client:
        client.get("/scene")
        client.post("/api-provider", json={"provider": "openai"})
        response = client.post("/command", json={"text": "ขอลอง AI"})
        assert response.status_code == 200
        assert seen == ["openai"]
