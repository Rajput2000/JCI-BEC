"""Runs the user's name-matching prompt (reused verbatim, unmodified) against
a Gemini text model to match meeting attendee names to the standard roster.
"""

from __future__ import annotations

from pathlib import Path

from google.genai import types

from .gemini_client import TEXT_MODEL, GeminiCallError, safe_generate_content

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "matching_prompt.txt"

# This is a "thinking" model: on a large/complex enough prompt (a 150+ name
# roster, many meeting names, the consolidation/certainty/sorting rules) it
# can spend its entire token budget reasoning and return empty content
# (finish_reason="MAX_TOKENS", no visible answer) — the same failure class
# Groq's reasoning model hit here before the migration. A capped (not
# disabled — the fuzzy-matching judgment calls genuinely benefit from some
# reasoning) thinking budget plus a generous max_output_tokens keeps that
# from happening.
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


def run_matching(
    standard_list: list[str], meeting_list: list[str], model: str = TEXT_MODEL
) -> str | None:
    """Returns the raw markdown-table text from the model, or None if there
    was nothing to match (skips the API call entirely in that case)."""
    if not meeting_list:
        return None

    prompt = build_matching_prompt(standard_list, meeting_list)
    response = safe_generate_content(
        model=model,
        contents=[prompt],
        config=types.GenerateContentConfig(
            temperature=0,
            max_output_tokens=_MAX_OUTPUT_TOKENS,
            thinking_config=types.ThinkingConfig(thinking_budget=_THINKING_BUDGET),
        ),
    )

    content = response.text
    if not content or not content.strip():
        finish_reason = response.candidates[0].finish_reason if response.candidates else None
        raise GeminiCallError(
            f"Gemini returned an empty response (finish_reason={finish_reason!r}) — "
            "it likely ran out of its token budget reasoning through a large list "
            "before writing any answer. Try again, or split the meeting list into "
            "smaller batches."
        )

    return content
