import json
import pytest

from core import dedupe
from core.llm_types import LLMCallError, LLMResult


def _fake_result(text):
    return LLMResult(text=text, finish_reason="STOP", provider="gemini")


def test_prefilter_dedupe_merges_case_and_whitespace_only():
    names = ["John Doe", "john doe", "  John   Doe ", "Jon Doe"]
    result = dedupe.prefilter_dedupe(names)
    # First-seen casing wins for the case/whitespace duplicates...
    assert "John Doe" in result
    # ...but a genuinely different spelling is NOT merged by the prefilter.
    assert "Jon Doe" in result
    assert len(result) == 2


def test_run_dedupe_llm_parses_response(monkeypatch):
    monkeypatch.setattr(
        dedupe,
        "generate",
        lambda request: _fake_result(json.dumps({"unique_names": ["Ada Lovelace", "Alan Turing"]})),
    )
    result = dedupe.run_dedupe_llm(["Ada Lovelace", "Ada  Lovelace", "Alan Turing"])
    assert result == ["Ada Lovelace", "Alan Turing"]


def test_run_dedupe_llm_raises_on_bad_json(monkeypatch):
    monkeypatch.setattr(dedupe, "generate", lambda request: _fake_result("not json"))
    with pytest.raises(LLMCallError):
        dedupe.run_dedupe_llm(["Ada Lovelace"])


def test_run_dedupe_llm_raises_when_response_has_no_names(monkeypatch):
    monkeypatch.setattr(dedupe, "generate", lambda request: _fake_result(json.dumps({"unique_names": []})))
    with pytest.raises(LLMCallError, match="no names"):
        dedupe.run_dedupe_llm(["Ada Lovelace"])


def test_dedupe_names_falls_back_on_gemini_failure(monkeypatch):
    def _raise(request):
        raise LLMCallError("simulated failure")

    monkeypatch.setattr(dedupe, "generate", _raise)
    names, warning = dedupe.dedupe_names(["John Doe", "john doe"])
    assert names == ["John Doe"]
    assert warning is not None


def test_dedupe_names_success_path(monkeypatch):
    monkeypatch.setattr(
        dedupe,
        "generate",
        lambda request: _fake_result(json.dumps({"unique_names": ["John Doe"]})),
    )
    names, warning = dedupe.dedupe_names(["John Doe", "john doe"])
    assert names == ["John Doe"]
    assert warning is None
