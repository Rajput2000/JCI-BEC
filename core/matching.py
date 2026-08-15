"""Runs the user's name-matching prompt (reused verbatim, unmodified) against
a Groq text model to match meeting attendee names to the standard roster.
"""

from __future__ import annotations

from pathlib import Path

from .groq_client import TEXT_MODEL, safe_chat_completion

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "matching_prompt.txt"


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
    response = safe_chat_completion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    return response.choices[0].message.content
