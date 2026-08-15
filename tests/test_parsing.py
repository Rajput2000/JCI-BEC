import pytest

from core.parsing import MarkdownTableParseError, derive_match, parse_markdown_table, to_display_rows

WELL_FORMED = """
| Name in Meeting | Matched Standard Name | Notes |
|-----------------|------------------------|-------|
| John Doe | John Doe | |
| J. Smith | [NO MATCH] | |
"""

MIXED_COLUMN_COUNTS = """
| Name in Meeting | Matched Standard Name | Notes |
|-----------------|------------------------|-------|
| Femi A. | Olufemi Akinrotimi | Matched by nickname |
| Jane Doe | Jane Emmanuel |
"""

PROSE_WRAPPED = """
Here is the requested table:

| Name in Meeting | Matched Standard Name | Notes |
|-----------------|------------------------|-------|
| Bola | Bola Adekunle | |

Let me know if you need anything else.
"""

NO_TABLE = "Sorry, I can't produce a table right now."


def test_well_formed_table():
    rows = parse_markdown_table(WELL_FORMED)
    assert len(rows) == 2
    assert rows[0] == {
        "name_in_meeting": "John Doe",
        "matched_standard_name": "John Doe",
        "notes": "",
    }
    assert rows[1]["matched_standard_name"] == "[NO MATCH]"


def test_mixed_column_counts_row_missing_notes_cell():
    rows = parse_markdown_table(MIXED_COLUMN_COUNTS)
    assert len(rows) == 2
    assert rows[0]["notes"] == "Matched by nickname"
    assert rows[1]["notes"] == ""  # row had no third cell at all


def test_prose_wrapped_table_still_parses():
    rows = parse_markdown_table(PROSE_WRAPPED)
    assert len(rows) == 1
    assert rows[0]["name_in_meeting"] == "Bola"


def test_no_table_raises():
    with pytest.raises(MarkdownTableParseError):
        parse_markdown_table(NO_TABLE)


def test_derive_match_case_and_whitespace_tolerant():
    assert derive_match("[NO MATCH]") == "No"
    assert derive_match(" [no match] ") == "No"
    assert derive_match("John Doe") == "Yes"


def test_to_display_rows_shape():
    rows = parse_markdown_table(WELL_FORMED)
    display = to_display_rows(rows)
    assert display[0]["Match"] == "Yes"
    assert display[1]["Match"] == "No"
    assert set(display[0].keys()) == {
        "Extracted Name",
        "Matched Standard Name",
        "Match",
        "Notes",
    }
