"""Runs the user's name-matching prompt (reused verbatim) to match meeting attendee names to the standard roster."""

from __future__ import annotations

from pathlib import Path

from .llm_client import generate
from .llm_types import LLMRequest

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "matching_prompt.txt"

# Thinking is capped, not disabled: fuzzy matching benefits from some reasoning,
# but an uncapped budget on a 150+ name roster can leave no tokens for the answer.
_MAX_OUTPUT_TOKENS = 8192
_THINKING_BUDGET = 2048


def load_prompt_template() -> str:
    return _PROMPT_PATH.read_text()


def build_matching_prompt(standard_list: list[str], meeting_list: list[str]) -> str:
    template = load_prompt_template()
    return template.format(
        standard_list="\n".join(standard_list),
        meeting_list="\n".join(meeting_list),
    )


def run_matching(standard_list: list[str], meeting_list: list[str]) -> str | None:
    """Returns the raw markdown-table text from the model, or None if there
    was nothing to match (skips the API call entirely in that case)."""
    if not meeting_list:
        return None

    request = LLMRequest(
        task="text",
        prompt=build_matching_prompt(standard_list, meeting_list),
        max_output_tokens=_MAX_OUTPUT_TOKENS,
        thinking_budget=_THINKING_BUDGET,
    )
    return generate(request).text
