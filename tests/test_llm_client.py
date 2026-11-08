"""Covers llm_client.generate: Gemini success, fallback on Gemini error or empty text,
no fallback when OpenRouter isn't configured, and a combined error when both fail."""

import pytest

from core import llm_client
from core.llm_types import LLMCallError, LLMRequest, LLMResult

REQUEST = LLMRequest(task="text", prompt="hi", max_output_tokens=100, thinking_budget=0)


def _result(text, provider, finish_reason="STOP"):
    return LLMResult(text=text, finish_reason=finish_reason, provider=provider)


def _raise(message):
    def _fail(request):
        raise LLMCallError(message)

    return _fail


@pytest.fixture
def fallback_calls(monkeypatch):
    calls = []

    def fake_fallback(request):
        calls.append(request)
        return _result("backup answer", "openrouter")

    monkeypatch.setattr(llm_client.openrouter_client, "is_configured", lambda: True)
    monkeypatch.setattr(llm_client.openrouter_client, "generate", fake_fallback)
    return calls


def test_returns_gemini_result_without_calling_fallback(monkeypatch, fallback_calls):
    monkeypatch.setattr(llm_client.gemini_client, "generate", lambda request: _result("answer", "gemini"))

    result = llm_client.generate(REQUEST)

    assert result.provider == "gemini"
    assert fallback_calls == []


def test_falls_back_when_gemini_raises(monkeypatch, fallback_calls):
    monkeypatch.setattr(llm_client.gemini_client, "generate", _raise("429 quota"))

    result = llm_client.generate(REQUEST)

    assert result.provider == "openrouter"
    assert fallback_calls == [REQUEST]


def test_falls_back_when_gemini_returns_empty_text(monkeypatch, fallback_calls):
    monkeypatch.setattr(
        llm_client.gemini_client, "generate", lambda request: _result("  ", "gemini", "MAX_TOKENS")
    )

    result = llm_client.generate(REQUEST)

    assert result.text == "backup answer"


def test_raises_gemini_error_when_fallback_not_configured(monkeypatch):
    monkeypatch.setattr(llm_client.openrouter_client, "is_configured", lambda: False)
    monkeypatch.setattr(
        llm_client.gemini_client, "generate", lambda request: _result("", "gemini", "MAX_TOKENS")
    )

    with pytest.raises(LLMCallError, match="MAX_TOKENS"):
        llm_client.generate(REQUEST)


def test_raises_combined_error_when_both_providers_fail(monkeypatch):
    monkeypatch.setattr(llm_client.openrouter_client, "is_configured", lambda: True)
    monkeypatch.setattr(llm_client.gemini_client, "generate", _raise("gemini down"))
    monkeypatch.setattr(llm_client.openrouter_client, "generate", _raise("backup down"))

    with pytest.raises(LLMCallError) as exc_info:
        llm_client.generate(REQUEST)

    assert "gemini down" in str(exc_info.value)
    assert "backup down" in str(exc_info.value)


def test_raises_when_fallback_returns_empty_text(monkeypatch):
    monkeypatch.setattr(llm_client.openrouter_client, "is_configured", lambda: True)
    monkeypatch.setattr(llm_client.gemini_client, "generate", _raise("gemini down"))
    monkeypatch.setattr(
        llm_client.openrouter_client, "generate", lambda request: _result("", "openrouter", "length")
    )

    with pytest.raises(LLMCallError, match="length"):
        llm_client.generate(REQUEST)
