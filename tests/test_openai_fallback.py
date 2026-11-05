import json

import httpx
import pytest

from app.neural import gemini_client as gemini, openai_client as gpt
from app.schemas import GameState, ParsedCommand


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    monkeypatch.setenv("OPENAI_FALLBACK_ENABLED", "true")
    monkeypatch.setattr(gemini, "_last_api_status", None)
    monkeypatch.setattr(gemini, "_clients", lambda: [])
    monkeypatch.setattr(gemini, "build_interpret_system_prompt", lambda *a, **k: "system")


def command():
    return ParsedCommand(action="examine", target="lounge_car", raw_text="model text",
                         parser_mode="openai_fallback:test-model")


@pytest.mark.parametrize("error", [gemini.NeuralQuotaExceeded, gemini.NeuralUnavailable,
                                   gemini.NeuralNotConfigured])
def test_falls_back_only_after_gemini_failure(monkeypatch, error):
    def fail(*a, **k):
        raise error("Gemini unavailable")
    monkeypatch.setattr(gemini, "_interpret_gemini", fail)
    monkeypatch.setattr(gpt, "interpret_structured", lambda *a: command())
    state = GameState()
    before = state.model_dump()
    result = gemini.interpret("ตรวจรอบห้อง", state, enable_repair=False)
    assert result.raw_text == "ตรวจรอบห้อง"
    assert result.parser_mode == "openai_fallback:test-model"
    assert state.model_dump() == before
    assert gemini.get_api_status()["provider"] == "openai"


def test_valid_ambiguous_result_does_not_fallback(monkeypatch):
    result = ParsedCommand(action="ambiguous", raw_text="x")
    monkeypatch.setattr(gemini, "_interpret_gemini", lambda *a: result)
    monkeypatch.setattr(gpt, "interpret_structured", lambda *a: pytest.fail("unexpected GPT"))
    assert gemini.interpret("x", GameState()) is result


def test_explicit_gpt_skips_gemini_even_if_fallback_disabled(monkeypatch):
    monkeypatch.setenv("OPENAI_FALLBACK_ENABLED", "false")
    monkeypatch.setattr(gemini, "_interpret_gemini", lambda *a: pytest.fail("unexpected Gemini"))
    monkeypatch.setattr(gpt, "interpret_structured", lambda *a: command())
    result = gemini.interpret("x", GameState(), provider="openai", enable_repair=False)
    assert result.parser_mode == "openai:test-model"


def test_explicit_gemini_never_calls_gpt(monkeypatch):
    monkeypatch.setattr(gpt, "interpret_structured", lambda *a: pytest.fail("unexpected GPT"))
    with pytest.raises(gemini.NeuralNotConfigured):
        gemini.interpret("x", GameState(), provider="gemini")


@pytest.mark.parametrize("setting", ["disabled", "missing_key"])
def test_optional_fallback(monkeypatch, setting):
    if setting == "disabled":
        monkeypatch.setenv("OPENAI_FALLBACK_ENABLED", "false")
    else:
        monkeypatch.delenv("OPENAI_API_KEY")
    monkeypatch.setattr(gpt, "interpret_structured", lambda *a: pytest.fail("unexpected GPT"))
    with pytest.raises(gemini.NeuralNotConfigured):
        gemini.interpret("x", GameState())


def test_gpt_http_contract(monkeypatch):
    def post(url, **kwargs):
        assert url == "https://api.openai.com/v1/chat/completions"
        schema = kwargs["json"]["response_format"]["json_schema"]
        assert schema["strict"] is True
        assert schema["schema"]["additionalProperties"] is False
        assert set(schema["schema"]["required"]) == set(schema["schema"]["properties"])
        assert "parser_mode" not in schema["schema"]["properties"]
        return httpx.Response(200, json={"model": "gpt-test-snapshot", "choices": [{
            "finish_reason": "stop", "message": {"content": command().model_dump_json()}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20}})
    monkeypatch.setattr(gpt.httpx, "post", post)
    parsed = gpt.interpret_structured("system", "user")
    assert parsed.parser_mode == "openai_fallback:gpt-test-snapshot"
    assert parsed.prompt_tokens == 10


@pytest.mark.parametrize("kind", ["quota", "auth", "timeout", "invalid", "refusal", "truncated"])
def test_gpt_failure_is_service_error_without_secret(monkeypatch, kind):
    def post(*a, **k):
        if kind == "timeout":
            raise httpx.ReadTimeout("test-secret")
        if kind in ("quota", "auth"):
            return httpx.Response(429 if kind == "quota" else 401, text="test-secret")
        return httpx.Response(200, json={"choices": [{
            "finish_reason": "length" if kind == "truncated" else "stop",
            "message": {"content": "invalid JSON", "refusal": "no" if kind == "refusal" else None}}]})
    monkeypatch.setattr(gpt.httpx, "post", post)
    with pytest.raises(gemini.NeuralUnavailable) as exc:
        gemini.interpret("x", GameState(), enable_repair=False)
    assert "test-secret" not in str(exc.value)
    assert gemini.get_api_status()["online"] is False


def test_repair_flag_is_respected(monkeypatch):
    calls = []
    monkeypatch.setattr(gpt, "interpret_structured", lambda *a: command())
    monkeypatch.setattr(gemini, "repair_parsed_command", lambda parsed, *a, **k: (calls.append(parsed) or parsed, None))
    gemini.interpret("x", GameState(), enable_repair=False)
    assert not calls
    gemini.interpret("x", GameState(), enable_repair=True)
    assert len(calls) == 1
