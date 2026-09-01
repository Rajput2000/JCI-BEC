"""Parses the LLM's markdown table response into structured rows.

The matching prompt (prompts/matching_prompt.txt) renders a 4-column table
— Name(s) in Meeting | Matched Standard Name | Match Certainty | Notes —
with one row per matched standard-list person: every meeting-name variant
that maps to the same person is consolidated into that person's row
(semicolon-separated in the first column — NOT pipe-separated, since `|` is
markdown's own table-column delimiter and would corrupt the row), while
unmatched names each keep their own row (never squashed together). Match
Certainty (Exact/High/Medium/Low/No Match) comes straight from the model
rather than being re-derived here, since it's strictly more informative
than a plain Yes/No.
"""

from __future__ import annotations

import re

_NAME_SPLIT_RE = re.compile(r"\s*;\s*")

NO_MATCH_SENTINEL = "[NO MATCH]"


def is_no_match(matched_standard_name: str) -> bool:
    """Case/whitespace-tolerant check for the [NO MATCH] sentinel. Tolerant
    because by the time this is checked (e.g. before posting attendance),
    the value has passed through an editable st.data_editor -- the model
    always emits the exact literal, but a hand edit could introduce stray
    whitespace or casing drift."""
    return str(matched_standard_name).strip().casefold() == NO_MATCH_SENTINEL.casefold()


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

        names_in_meeting = cells[0]
        matched_standard_name = cells[1]
        match_certainty = cells[2] if len(cells) >= 3 else ""
        notes = cells[3] if len(cells) >= 4 else ""

        if not names_in_meeting:
            continue

        rows.append(
            {
                "names_in_meeting": names_in_meeting,
                "matched_standard_name": matched_standard_name,
                "match_certainty": match_certainty,
                "notes": notes,
            }
        )

    if not rows:
        raise MarkdownTableParseError(
            "Found a table-like block but couldn't parse any data rows from it."
        )

    return rows


def split_meeting_names(names_in_meeting: str) -> list[str]:
    """Splits a possibly-consolidated 'Name(s) in Meeting' cell (semicolon-
    separated when multiple raw meeting names matched the same person) back
    into individual names."""
    return [name for name in _NAME_SPLIT_RE.split(names_in_meeting) if name]


def count_meeting_names(rows: list[dict]) -> int:
    """Total individual meeting names across all rows, un-collapsing any
    semicolon-separated consolidation. This — not len(rows) — is the right
    count to sanity-check against the input list, since consolidation means
    row count is *expected* to come out smaller than the number of names sent."""
    return sum(len(split_meeting_names(row["names_in_meeting"])) for row in rows)


def to_display_rows(parsed_rows: list[dict]) -> list[dict]:
    return [
        {
            "Extracted Name(s)": row["names_in_meeting"],
            "Matched Standard Name": row["matched_standard_name"],
            "Match Certainty": row["match_certainty"],
            "Notes": row["notes"],
        }
        for row in parsed_rows
    ]
