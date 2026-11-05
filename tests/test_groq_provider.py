import httpx
import pytest
from fastapi.testclient import TestClient

from app import main
from app.neural import gemini_client as gemini, openai_client as provider
from app.schemas import GameState, ParsedCommand


@pytest.mark.parametrize("status", [200, 429, 401])
def test_groq_routing_and_errors(monkeypatch, status):
    monkeypatch.setenv("GROQ_API_KEY", "groq-test-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "different-secret")
    monkeypatch.setenv("GROQ_MODEL", "openai/gpt-oss-20b")
    monkeypatch.setattr(gemini, "_last_api_status", None)
    monkeypatch.setattr(gemini, "_clients", lambda: [])
    monkeypatch.setattr(gemini, "_interpret_gemini", lambda *a: pytest.fail("unexpected Gemini"))
    monkeypatch.setattr(gemini, "build_interpret_system_prompt", lambda *a, **k: "system")
    def post(url, **kwargs):
        assert url == "https://api.groq.com/openai/v1/chat/completions"
        assert kwargs["headers"]["Authorization"] == "Bearer groq-test-secret"
        assert kwargs["json"]["model"] == "openai/gpt-oss-20b"
        assert kwargs["json"]["response_format"]["json_schema"]["strict"] is True
        parsed = ParsedCommand(action="examine", target="lounge_car", raw_text="x")
        return httpx.Response(status, json={"choices": [{"finish_reason": "stop",
            "message": {"content": parsed.model_dump_json()}}]})
    monkeypatch.setattr(provider.httpx, "post", post)
    if status == 200:
        parsed = gemini.interpret("x", GameState(), provider="groq", enable_repair=False)
        assert parsed.parser_mode == "groq:openai/gpt-oss-20b"
        assert gemini.get_api_status()["provider"] == "groq"
    else:
        with pytest.raises(gemini.NeuralQuotaExceeded if status == 429 else gemini.NeuralUnavailable) as exc:
            gemini.interpret("x", GameState(), provider="groq", enable_repair=False)
        assert "secret" not in str(exc.value)
        assert gemini.get_api_status()["online"] is False


def test_groq_button_availability_and_selection(monkeypatch):
    monkeypatch.setattr(main, "_clients", lambda: [])
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with TestClient(main.app) as client:
        client.get("/scene")
        assert client.get("/api-provider").json()["available"]["groq"] is False
        assert client.post("/api-provider", json={"provider": "groq"}).status_code == 400
        monkeypatch.setenv("GROQ_API_KEY", "test")
        assert client.post("/api-provider", json={"provider": "groq"}).json()["selected"] == "groq"


@pytest.mark.parametrize("groq_fails,gpt_enabled,expected_calls", [
    (False, True, ["groq"]),
    (True, True, ["groq", "openai"]),
    (True, False, ["groq"]),
])
def test_auto_tries_groq_before_paid_gpt(monkeypatch, groq_fails, gpt_enabled, expected_calls):
    monkeypatch.setattr(gemini, "_clients", lambda: [])
    monkeypatch.setattr(gemini, "_last_api_status", None)
    monkeypatch.setattr(provider, "groq_configured", lambda: True)
    monkeypatch.setattr(provider, "configured", lambda **kw: gpt_enabled)
    monkeypatch.setattr(gemini, "build_interpret_system_prompt", lambda *a, **k: "system")
    calls = []
    def call(*args, provider="openai"):
        calls.append(provider)
        if provider == "groq" and groq_fails:
            raise gemini.NeuralQuotaExceeded("429")
        return ParsedCommand(action="ambiguous", raw_text="x",
            parser_mode="groq:test-model" if provider == "groq" else "openai_fallback:test-model")
    monkeypatch.setattr(provider, "interpret_structured", call)
    if groq_fails and not gpt_enabled:
        with pytest.raises(gemini.NeuralQuotaExceeded):
            gemini.interpret("x", GameState(), enable_repair=False)
    else:
        result = gemini.interpret("x", GameState(), enable_repair=False)
        assert result.parser_mode == ("openai_fallback:test-model" if groq_fails else "groq_fallback:test-model")
    assert calls == expected_calls


@pytest.mark.parametrize("failure", ["quota", "server", "timeout", "invalid"])
def test_auto_http_command_recovers_after_groq_failure(monkeypatch, failure):
    monkeypatch.setattr(gemini, "_clients", lambda: [])
    monkeypatch.setattr(gemini, "_last_api_status", None)
    monkeypatch.setattr(main, "_clients", lambda: [])
    monkeypatch.setenv("GROQ_API_KEY", "groq-test")
    monkeypatch.setenv("OPENAI_API_KEY", "gpt-test")
    monkeypatch.setenv("OPENAI_FALLBACK_ENABLED", "true")
    monkeypatch.setattr(gemini, "build_interpret_system_prompt", lambda *a, **k: "test")
    calls = []
    def post(url, **kwargs):
        calls.append(url)
        if 'groq.com' in url:
            if failure == 'timeout':
                raise httpx.ReadTimeout('test timeout')
            if failure == 'invalid':
                return httpx.Response(200, json={'choices': []})
            return httpx.Response(429 if failure == 'quota' else 503)
        result = ParsedCommand(action='examine', target='lounge_car', raw_text='x', confidence=.99)
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop',
            'message': {'content': result.model_dump_json()}}]})
    monkeypatch.setattr(provider.httpx, 'post', post)
    with TestClient(main.app) as client:
        client.get('/scene?case_id=case_01_gideon')
        response = client.post('/command', json={'text': 'ช่วยอธิบายสิ่งรอบตัวตอนนี้หน่อย'})
        data = response.json()
        assert response.status_code == 200
        assert not data.get('service_error')
        assert data['parsed']['parser_mode'].startswith('openai_fallback:')
        assert data['decision']['allowed']
    assert len(calls) == 2
    assert 'groq.com' in calls[0] and 'openai.com' in calls[1]


def test_all_providers_fail_preserves_game_state(monkeypatch):
    from app.sessions import sessions, COOKIE
    monkeypatch.setattr(gemini, '_clients', lambda: [])
    monkeypatch.setattr(main, '_clients', lambda: [])
    monkeypatch.setattr(gemini, '_last_api_status', None)
    monkeypatch.setattr(provider, 'groq_configured', lambda: True)
    monkeypatch.setattr(provider, 'configured', lambda **kw: True)
    monkeypatch.setattr(gemini, 'build_interpret_system_prompt', lambda *a, **k: 'test')
    def fail(*a, **kw):
        raise gemini.NeuralUnavailable('unavailable')
    monkeypatch.setattr(provider, 'interpret_structured', fail)
    with TestClient(main.app) as client:
        client.get('/scene')
        before = sessions[client.cookies[COOKIE]].state.model_dump()
        data = client.post('/command', json={'text': 'ช่วยอธิบายสิ่งรอบตัวตอนนี้หน่อย'}).json()
        assert data['service_error'] == 'unavailable'
        assert not data['decision']['allowed']
        assert data['new_state'] == before


def test_groq_only_configuration_is_ready(monkeypatch):
    monkeypatch.setattr(gemini, '_clients', lambda: [])
    monkeypatch.setattr(gemini, '_last_api_status', None)
    monkeypatch.setattr(provider, 'groq_configured', lambda: True)
    assert gemini.get_api_status()['provider'] == 'groq'
    assert gemini.get_api_status()['online'] is True
