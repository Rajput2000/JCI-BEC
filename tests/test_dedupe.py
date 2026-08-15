import json
from types import SimpleNamespace

import pytest

from core import dedupe
from core.groq_client import GroqCallError


def _fake_response(content: str):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


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
        "safe_chat_completion",
        lambda **kwargs: _fake_response(json.dumps({"unique_names": ["Ada Lovelace", "Alan Turing"]})),
    )
    result = dedupe.run_dedupe_llm(["Ada Lovelace", "Ada  Lovelace", "Alan Turing"])
    assert result == ["Ada Lovelace", "Alan Turing"]


def test_run_dedupe_llm_raises_on_bad_json(monkeypatch):
    monkeypatch.setattr(dedupe, "safe_chat_completion", lambda **kwargs: _fake_response("not json"))
    with pytest.raises(GroqCallError):
        dedupe.run_dedupe_llm(["Ada Lovelace"])


def test_dedupe_names_falls_back_on_groq_failure(monkeypatch):
    def _raise(**kwargs):
        raise GroqCallError("simulated failure")

    monkeypatch.setattr(dedupe, "safe_chat_completion", _raise)
    names, warning = dedupe.dedupe_names(["John Doe", "john doe"])
    assert names == ["John Doe"]
    assert warning is not None


def test_dedupe_names_success_path(monkeypatch):
    monkeypatch.setattr(
        dedupe,
        "safe_chat_completion",
        lambda **kwargs: _fake_response(json.dumps({"unique_names": ["John Doe"]})),
    )
    names, warning = dedupe.dedupe_names(["John Doe", "john doe"])
    assert names == ["John Doe"]
    assert warning is None
