"""GPT backup interpreter. Credentials stay on the server; no state mutation."""
import os
import time

import httpx

from app.schemas import ParsedCommand


def configured(*, fallback: bool = True) -> bool:
    return ((not fallback or os.getenv("OPENAI_FALLBACK_ENABLED", "true").lower() == "true")
            and bool(os.getenv("OPENAI_API_KEY", "").strip()))


def interpret_structured(system: str, content: str) -> ParsedCommand:
    from app.neural.gemini_client import NeuralUnavailable, NeuralQuotaExceeded

    schema = ParsedCommand.model_json_schema()
    # Telemetry is supplied by the application, never by the model.
    for name in ("prompt_tokens", "completion_tokens", "latency_ms", "parser_mode", "repair_note"):
        schema["properties"].pop(name, None)

    def strict(node):
        if isinstance(node, dict):
            node.pop("default", None)
            if node.get("type") == "object":
                node["additionalProperties"] = False
                node["required"] = list(node["properties"])
            for value in node.values():
                strict(value)
        elif isinstance(node, list):
            for value in node:
                strict(value)
    strict(schema)
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip() or "gpt-4.1-mini"
    started = time.perf_counter()
    try:
        response = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"].strip()},
            json={"model": model, "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": content},
            ], "response_format": {"type": "json_schema", "json_schema": {
                "name": "parsed_command", "strict": True, "schema": schema,
            }}, "max_completion_tokens": 2048},
            timeout=httpx.Timeout(15.0, connect=5.0),
        )
        if response.status_code == 429:
            raise NeuralQuotaExceeded("OpenAI quota/rate limit (HTTP 429)")
        if response.is_error:
            raise NeuralUnavailable(f"OpenAI request failed (HTTP {response.status_code})")
        data = response.json()
        choice = data["choices"][0]
        if choice.get("finish_reason") != "stop" or choice["message"].get("refusal"):
            raise NeuralUnavailable("OpenAI did not return a complete command")
        parsed = ParsedCommand.model_validate_json(choice["message"]["content"])
        usage = data.get("usage") or {}
        parsed.prompt_tokens = usage.get("prompt_tokens")
        parsed.completion_tokens = usage.get("completion_tokens")
        parsed.latency_ms = round((time.perf_counter() - started) * 1000, 2)
        parsed.parser_mode = "openai_fallback:" + data.get("model", model)
        parsed.repair_note = None
        return parsed
    except NeuralUnavailable:
        raise
    except Exception as exc:
        # Do not expose provider response bodies or credentials through /health.
        raise NeuralUnavailable("OpenAI connection or response validation failed") from exc
