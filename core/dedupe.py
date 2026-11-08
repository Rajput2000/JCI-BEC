"""Two-stage deduplication of names extracted from meeting screenshots.

Stage 1 (prefilter_dedupe): cheap, code-level, exact/case/whitespace
duplicates only. No API call, no ambiguity.

Stage 2 (run_dedupe_llm): an LLM text call that catches near-
duplicate *spellings* a plain normalize won't (OCR noise, inconsistent
spacing, a one-character misread) across different screenshots of the same
meeting.

This step is deliberately narrow in scope: it never does nickname/initials
consolidation (e.g. "Mike" + "Michael Smith") — that ambiguity is left
entirely to matching.py, which resolves it against the authoritative
standard roster. Keeping the two steps' responsibilities separate avoids
them fighting each other's logic.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from .llm_client import generate
from .llm_types import LLMCallError, LLMRequest

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "dedupe_prompt.txt"

_UNIQUE_NAMES_SCHEMA = {
    "type": "object",
    "properties": {
        "unique_names": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["unique_names"],
}


def normalize_name(name: str) -> str:
    """Comparison key only: strip, collapse internal whitespace, casefold."""
    return re.sub(r"\s+", " ", name.strip()).casefold()


def prefilter_dedupe(names: list[str]) -> list[str]:
    """Collapse exact/case/whitespace duplicates. First-seen casing wins,
    order of first appearance is preserved."""
    seen: dict[str, str] = {}
    for name in names:
        name = name.strip()
        if not name:
            continue
        key = normalize_name(name)
        if key not in seen:
            seen[key] = name
    return list(seen.values())


def load_dedupe_prompt() -> str:
    return _PROMPT_PATH.read_text()


def build_dedupe_prompt(names: list[str]) -> str:
    template = load_dedupe_prompt()
    name_list = "\n".join(names)
    return template.format(name_list=name_list)


def run_dedupe_llm(names: list[str]) -> list[str]:
    """Merges remaining near-duplicate spellings. Raises LLMCallError on failure;
    callers should fall back to the prefiltered list rather than hard-stop."""
    if not names:
        return []

    request = LLMRequest(
        task="text",
        prompt=build_dedupe_prompt(names),
        json_schema=_UNIQUE_NAMES_SCHEMA,
        max_output_tokens=4096,
        # Merging spellings needs no reasoning; thinking can eat the whole token budget.
        thinking_budget=0,
    )
    raw_content = generate(request).text

    try:
        payload = json.loads(raw_content)
        unique_names = payload.get("unique_names", [])
        if not isinstance(unique_names, list):
            raise ValueError("'unique_names' was not a list")
    except (json.JSONDecodeError, ValueError) as exc:
        raise LLMCallError(f"Dedup response wasn't valid JSON: {exc}") from exc

    cleaned = [str(n).strip() for n in unique_names if str(n).strip()]
    if not cleaned:
        raise LLMCallError("Dedup response contained no names.")
    return cleaned


def dedupe_names(names: list[str]) -> tuple[list[str], str | None]:
    """Orchestrates prefilter -> LLM dedup. Returns (deduped_names, warning).
    warning is None on success; if the LLM call fails, falls back to the
    prefiltered list and returns a warning message instead of raising, so
    one dedup-call failure doesn't hard-stop the whole pipeline."""
    prefiltered = prefilter_dedupe(names)

    try:
        return run_dedupe_llm(prefiltered), None
    except LLMCallError as exc:
        logger.warning("LLM dedup failed, falling back to prefiltered list: %s", exc)
        return prefiltered, (
            f"Could not run LLM-based dedup ({exc}); showing the "
            "case/whitespace-deduped list instead. Please review it below."
        )
