"""Covers gemini_client: config/contents built from an LLMRequest, empty text passed through
with its finish reason, retry on 429, and API errors raised as LLMCallError."""

from types import SimpleNamespace

import pytest
from google.genai import errors, types

from core import gemini_client
from core.llm_types import LLMCallError, LLMRequest

SCHEMA = {"type": "object", "properties": {"names": {"type": "array", "items": {"type": "string"}}}}


def _request(**overrides):
    fields = {"task": "text", "prompt": "list names", "max_output_tokens": 4096, "thinking_budget": 0}
    fields.update(overrides)
    return LLMRequest(**fields)


def _fake_client(generate_content):
    return SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))


def _response(text, finish_reason=types.FinishReason.STOP):
    return SimpleNamespace(text=text, candidates=[SimpleNamespace(finish_reason=finish_reason)])


def _api_error(code):
    return errors.APIError(code, {"error": {"message": "simulated", "status": "X"}})


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(gemini_client.time, "sleep", lambda seconds: None)


def test_build_config_sets_json_schema_and_token_limits():
    config = gemini_client.build_config(_request(json_schema=SCHEMA, thinking_budget=2048))

    assert config.response_mime_type == "application/json"
    assert config.max_output_tokens == 4096
    assert config.thinking_config.thinking_budget == 2048


def test_build_contents_includes_image_part_for_vision():
    contents = gemini_client.build_contents(_request(task="vision", image_jpeg=b"\xff\xd8jpeg"))

    assert contents[0] == "list names"
    assert contents[1].inline_data.mime_type == "image/jpeg"


def test_generate_passes_empty_text_through_with_finish_reason(monkeypatch):
    client = _fake_client(lambda **kwargs: _response(None, types.FinishReason.MAX_TOKENS))
    monkeypatch.setattr(gemini_client, "get_client", lambda: client)

    result = gemini_client.generate(_request())

    assert result.text == ""
    assert result.finish_reason == "MAX_TOKENS"


def test_generate_retries_rate_limit_then_succeeds(monkeypatch):
    outcomes = iter([_api_error(429), _response("ok")])

    def generate_content(**kwargs):
        outcome = next(outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(gemini_client, "get_client", lambda: _fake_client(generate_content))

    assert gemini_client.generate(_request()).text == "ok"


def test_generate_raises_llm_call_error_on_server_error(monkeypatch):
    def generate_content(**kwargs):
        raise _api_error(503)

    monkeypatch.setattr(gemini_client, "get_client", lambda: _fake_client(generate_content))

    with pytest.raises(LLMCallError, match="Gemini API call failed"):
        gemini_client.generate(_request())
