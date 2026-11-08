import pytest

from core import matching
from core.llm_types import LLMCallError, LLMResult


def _fake_result(text):
    return LLMResult(text=text, finish_reason="STOP", provider="gemini")


def test_build_matching_prompt_substitutes_both_lists():
    prompt = matching.build_matching_prompt(["Ada Lovelace"], ["ada"])
    assert "Ada Lovelace" in prompt
    assert "ada" in prompt


def test_run_matching_returns_none_when_meeting_list_empty():
    assert matching.run_matching(["Ada Lovelace"], []) is None


def test_run_matching_returns_content(monkeypatch):
    monkeypatch.setattr(matching, "generate", lambda request: _fake_result("| table |"))
    result = matching.run_matching(["Ada Lovelace"], ["ada"])
    assert result == "| table |"


def test_run_matching_propagates_llm_failure(monkeypatch):
    def _raise(request):
        raise LLMCallError("gemini returned an empty response (finish_reason='MAX_TOKENS')")

    monkeypatch.setattr(matching, "generate", _raise)
    with pytest.raises(LLMCallError, match="MAX_TOKENS"):
        matching.run_matching(["Ada Lovelace"], ["ada"])


def test_run_matching_caps_thinking_budget_and_output_tokens(monkeypatch):
    captured = {}

    def fake_call(request):
        captured["request"] = request
        return _fake_result("| table |")

    monkeypatch.setattr(matching, "generate", fake_call)
    matching.run_matching(["Ada Lovelace"], ["ada"])
    assert captured["request"].thinking_budget == matching._THINKING_BUDGET
    assert captured["request"].max_output_tokens == matching._MAX_OUTPUT_TOKENS
