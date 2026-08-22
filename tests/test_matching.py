from types import SimpleNamespace

import pytest

from core import matching
from core.gemini_client import GeminiCallError


def _fake_response(text, finish_reason="STOP"):
    return SimpleNamespace(text=text, candidates=[SimpleNamespace(finish_reason=finish_reason)])


def test_build_matching_prompt_substitutes_both_lists():
    prompt = matching.build_matching_prompt(["Ada Lovelace"], ["ada"])
    assert "Ada Lovelace" in prompt
    assert "ada" in prompt


def test_run_matching_returns_none_when_meeting_list_empty():
    assert matching.run_matching(["Ada Lovelace"], []) is None


def test_run_matching_returns_content(monkeypatch):
    monkeypatch.setattr(matching, "safe_generate_content", lambda **kwargs: _fake_response("| table |"))
    result = matching.run_matching(["Ada Lovelace"], ["ada"])
    assert result == "| table |"


def test_run_matching_raises_on_empty_content_with_diagnostic(monkeypatch):
    # Reproduces the real failure: the model exhausts its token budget
    # reasoning and never emits any visible answer.
    monkeypatch.setattr(
        matching,
        "safe_generate_content",
        lambda **kwargs: _fake_response("", finish_reason="MAX_TOKENS"),
    )
    with pytest.raises(GeminiCallError, match="MAX_TOKENS"):
        matching.run_matching(["Ada Lovelace"], ["ada"])


def test_run_matching_caps_thinking_budget_and_output_tokens(monkeypatch):
    captured = {}

    def fake_call(**kwargs):
        captured.update(kwargs)
        return _fake_response("| table |")

    monkeypatch.setattr(matching, "safe_generate_content", fake_call)
    matching.run_matching(["Ada Lovelace"], ["ada"])
    assert captured["config"].thinking_config.thinking_budget == matching._THINKING_BUDGET
    assert captured["config"].max_output_tokens == matching._MAX_OUTPUT_TOKENS
