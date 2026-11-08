"""Covers openrouter_client: message/payload building (image, JSON mode, token floor, model list),
response parsing, retry on 429/network errors, and errors on non-retryable statuses."""

import json

import httpx
import pytest

from core import openrouter_client
from core.llm_types import LLMCallError, LLMRequest

SCHEMA = {"type": "object", "properties": {"names": {"type": "array"}}}


def _request(**overrides):
    fields = {"task": "text", "prompt": "list names", "max_output_tokens": 4096, "thinking_budget": 0}
    fields.update(overrides)
    return LLMRequest(**fields)


def _http_response(status, body):
    return httpx.Response(status, json=body, request=httpx.Request("POST", "https://openrouter.ai"))


def _ok_body(content, finish_reason="stop"):
    return {"choices": [{"message": {"content": content}, "finish_reason": finish_reason}]}


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("OPENROUTER_MODELS", raising=False)
    monkeypatch.setattr(openrouter_client.time, "sleep", lambda seconds: None)


def test_is_configured_false_without_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY")
    monkeypatch.setattr(openrouter_client, "resolve_setting", lambda name, default=None: default)
    assert openrouter_client.is_configured() is False


def test_get_models_splits_comma_list(monkeypatch):
    monkeypatch.setenv("OPENROUTER_MODELS", "a/one:free, b/two:free ,")
    assert openrouter_client.get_models() == ["a/one:free", "b/two:free"]


def test_build_messages_sends_image_as_data_url():
    messages = openrouter_client.build_messages(_request(task="vision", image_jpeg=b"\xff\xd8jpeg"))

    image_part = messages[-1]["content"][1]
    assert image_part["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_build_messages_adds_schema_instruction_for_json_requests():
    messages = openrouter_client.build_messages(_request(system_prompt="You read names.", json_schema=SCHEMA))

    system_content = messages[0]["content"]
    assert system_content.startswith("You read names.")
    assert json.dumps(SCHEMA) in system_content


def test_build_payload_raises_token_floor_and_sets_json_mode():
    payload = openrouter_client.build_payload(_request(json_schema=SCHEMA), ["a/one:free"])

    assert payload["max_tokens"] == openrouter_client._MIN_MAX_TOKENS
    assert payload["response_format"] == {"type": "json_object"}
    assert "models" not in payload


def test_build_payload_lists_backup_models_when_several_configured():
    payload = openrouter_client.build_payload(_request(), ["a/one:free", "b/two:free"])

    assert payload["model"] == "a/one:free"
    assert payload["models"] == ["a/one:free", "b/two:free"]


def test_parse_response_strips_code_fences_for_json():
    result = openrouter_client.parse_response(_ok_body('```json\n{"names": []}\n```'), expects_json=True)
    assert result.text == '{"names": []}'


def test_parse_response_raises_when_no_choices():
    with pytest.raises(LLMCallError, match="no answer"):
        openrouter_client.parse_response({"error": {"message": "overloaded"}}, expects_json=False)


def test_generate_retries_once_on_rate_limit(monkeypatch):
    responses = iter([_http_response(429, {}), _http_response(200, _ok_body("| table |"))])
    monkeypatch.setattr(openrouter_client.httpx, "post", lambda *args, **kwargs: next(responses))

    result = openrouter_client.generate(_request())

    assert result.text == "| table |"
    assert result.provider == "openrouter"


def test_generate_retries_once_on_network_error(monkeypatch):
    attempts = []

    def fake_post(*args, **kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            raise httpx.ConnectTimeout("timed out")
        return _http_response(200, _ok_body("ok"))

    monkeypatch.setattr(openrouter_client.httpx, "post", fake_post)

    assert openrouter_client.generate(_request()).text == "ok"
    assert len(attempts) == 2


def test_generate_raises_on_non_retryable_status(monkeypatch):
    monkeypatch.setattr(
        openrouter_client.httpx, "post", lambda *args, **kwargs: _http_response(404, {"error": "no endpoints"})
    )

    with pytest.raises(LLMCallError, match="HTTP 404"):
        openrouter_client.generate(_request())


def test_generate_raises_after_second_rate_limit(monkeypatch):
    monkeypatch.setattr(openrouter_client.httpx, "post", lambda *args, **kwargs: _http_response(429, {}))

    with pytest.raises(LLMCallError, match="HTTP 429"):
        openrouter_client.generate(_request())
