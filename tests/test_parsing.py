import pytest

from core.parsing import (
    MarkdownTableParseError,
    count_meeting_names,
    is_no_match,
    parse_markdown_table,
    split_meeting_names,
    to_display_rows,
)

WELL_FORMED = """
| Name(s) in Meeting | Matched Standard Name | Match Certainty | Notes |
|---------------------|------------------------|------------------|-------|
| John Doe | John Doe | Exact | |
| J. Smith | [NO MATCH] | No Match | |
"""

CONSOLIDATED_ROW = """
| Name(s) in Meeting | Matched Standard Name | Match Certainty | Notes |
|---------------------|------------------------|------------------|-------|
| Michael Kanu | Michael Kanu | Exact | |
| Alao; Alao Anu | Alao Anu | High | |
"""

MIXED_COLUMN_COUNTS = """
| Name(s) in Meeting | Matched Standard Name | Match Certainty | Notes |
|---------------------|------------------------|------------------|-------|
| Femi A. | Olufemi Akinrotimi | Medium | Matched by nickname |
| Jane Doe | Jane Emmanuel | High |
"""

PROSE_WRAPPED = """
Here is the requested table:

| Name(s) in Meeting | Matched Standard Name | Match Certainty | Notes |
|---------------------|------------------------|------------------|-------|
| Bola | Bola Adekunle | Exact | |

Let me know if you need anything else.
"""

NO_TABLE = "Sorry, I can't produce a table right now."


def test_well_formed_table():
    rows = parse_markdown_table(WELL_FORMED)
    assert len(rows) == 2
    assert rows[0] == {
        "names_in_meeting": "John Doe",
        "matched_standard_name": "John Doe",
        "match_certainty": "Exact",
        "notes": "",
    }
    assert rows[1]["matched_standard_name"] == "[NO MATCH]"
    assert rows[1]["match_certainty"] == "No Match"


def test_mixed_column_counts_row_missing_notes_cell():
    rows = parse_markdown_table(MIXED_COLUMN_COUNTS)
    assert len(rows) == 2
    assert rows[0]["notes"] == "Matched by nickname"
    assert rows[1]["notes"] == ""  # row had no fourth cell at all


def test_prose_wrapped_table_still_parses():
    rows = parse_markdown_table(PROSE_WRAPPED)
    assert len(rows) == 1
    assert rows[0]["names_in_meeting"] == "Bola"


def test_no_table_raises():
    with pytest.raises(MarkdownTableParseError):
        parse_markdown_table(NO_TABLE)


def test_split_meeting_names_single():
    assert split_meeting_names("John Doe") == ["John Doe"]


def test_split_meeting_names_consolidated():
    assert split_meeting_names("Alao; Alao Anu") == ["Alao", "Alao Anu"]


def test_split_meeting_names_tolerates_spacing():
    assert split_meeting_names("Alao;Alao Anu  ;  A. Anu") == ["Alao", "Alao Anu", "A. Anu"]


def test_count_meeting_names_across_consolidated_rows():
    rows = parse_markdown_table(CONSOLIDATED_ROW)
    # "Michael Kanu" (1) + "Alao" + "Alao Anu" (2) = 3, even though there
    # are only 2 rows — this is the number that should be checked against
    # the input count, not len(rows).
    assert count_meeting_names(rows) == 3


def test_to_display_rows_shape():
    rows = parse_markdown_table(WELL_FORMED)
    display = to_display_rows(rows)
    assert display[0]["Match Certainty"] == "Exact"
    assert display[1]["Match Certainty"] == "No Match"
    assert set(display[0].keys()) == {
        "Extracted Name(s)",
        "Matched Standard Name",
        "Match Certainty",
        "Notes",
    }


def test_is_no_match_exact():
    assert is_no_match("[NO MATCH]") is True


def test_is_no_match_case_and_whitespace_tolerant():
    assert is_no_match("  [no match] ") is True
    assert is_no_match("[No Match]") is True


def test_is_no_match_false_for_real_name():
    assert is_no_match("Ada Lovelace") is False
    assert is_no_match("") is False
