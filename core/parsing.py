"""Parses the LLM's markdown table response into structured rows, and
derives the Match Yes/No column ourselves rather than asking the LLM for it.

The matching prompt (prompts/matching_prompt.txt) always renders a 3-column
table — Name in Meeting | Matched Standard Name | Notes — with Notes left
blank except on ambiguous rows. The parser expects 3 cells per row but
tolerates 2-cell rows defensively (treated as an empty Notes).
"""

from __future__ import annotations

import re

_NO_MATCH_SENTINEL = "[no match]"


class MarkdownTableParseError(RuntimeError):
    """Raised when no table-like block can be found in the model's response."""


def _is_separator_row(cells: list[str]) -> bool:
    return all(re.fullmatch(r":?-+:?", cell) for cell in cells if cell)


def parse_markdown_table(markdown_text: str) -> list[dict]:
    lines = [line.strip() for line in markdown_text.splitlines() if line.strip().startswith("|")]
    if not lines:
        raise MarkdownTableParseError(
            "No markdown table found in the model's response."
        )

    rows: list[dict] = []
    header_seen = False

    for line in lines:
        cells = [cell.strip() for cell in line.strip("|").split("|")]

        if _is_separator_row(cells):
            continue

        if not header_seen:
            # First non-separator row is the header — skip it.
            header_seen = True
            continue

        if len(cells) < 2:
            continue

        name_in_meeting = cells[0]
        matched_standard_name = cells[1]
        notes = cells[2] if len(cells) >= 3 else ""

        if not name_in_meeting:
            continue

        rows.append(
            {
                "name_in_meeting": name_in_meeting,
                "matched_standard_name": matched_standard_name,
                "notes": notes,
            }
        )

    if not rows:
        raise MarkdownTableParseError(
            "Found a table-like block but couldn't parse any data rows from it."
        )

    return rows


def derive_match(matched_standard_name: str) -> str:
    """Case/whitespace-tolerant check against the literal [NO MATCH]
    sentinel, as a defensive measure against minor model formatting drift."""
    normalized = matched_standard_name.strip().casefold()
    return "No" if normalized == _NO_MATCH_SENTINEL else "Yes"


def to_display_rows(parsed_rows: list[dict]) -> list[dict]:
    return [
        {
            "Extracted Name": row["name_in_meeting"],
            "Matched Standard Name": row["matched_standard_name"],
            "Match": derive_match(row["matched_standard_name"]),
            "Notes": row["notes"],
        }
        for row in parsed_rows
    ]
