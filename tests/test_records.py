from core.records import build_attendance_rows, build_member_lookup

DIRECTORY_RECORDS = [
    {"Member Code": "001", "Member Name": "Ada Lovelace", "Location": "Lagos", "Family Unit": "JCI Sen. X"},
    {"Member Code": "002", "Member Name": "Alan Turing", "Location": "Abuja", "Family Unit": "JCI Sen. Y"},
    {"Member Code": "003", "Member Name": "", "Location": "Ibadan", "Family Unit": "JCI Sen. Z"},  # blank name
]


def _lookup():
    return build_member_lookup(DIRECTORY_RECORDS)


def test_build_member_lookup_skips_blank_names():
    lookup = _lookup()
    assert len(lookup) == 2


def test_normal_match_builds_row():
    match_rows = [{"Matched Standard Name": "Ada Lovelace"}]
    result = build_attendance_rows(
        match_rows, _lookup(), activity="Attending LO Meetings", point_value=3, month="January"
    )
    assert result.rows == [
        {
            "Member Name": "Ada Lovelace",
            "Location": "Lagos",
            "Activity": "Attending LO Meetings",
            "Point": 3,
            "Quantity": 1,
            "Total Point": 3,
            "Month": "January",
            "Family Unit": "JCI Sen. X",
        }
    ]
    assert result.skipped_no_match == 0
    assert result.skipped_not_found == []


def test_total_point_math_with_fractional_point():
    match_rows = [{"Matched Standard Name": "Ada Lovelace"}]
    result = build_attendance_rows(
        match_rows, _lookup(), activity="X", point_value=2.5, month="March"
    )
    assert result.rows[0]["Total Point"] == 2.5
    assert result.rows[0]["Quantity"] == 1


def test_no_match_rows_skipped():
    match_rows = [{"Matched Standard Name": "[NO MATCH]"}]
    result = build_attendance_rows(match_rows, _lookup(), activity="X", point_value=1, month="May")
    assert result.rows == []
    assert result.skipped_no_match == 1


def test_no_match_case_and_whitespace_tolerant():
    match_rows = [{"Matched Standard Name": " [no match] "}, {"Matched Standard Name": "[No Match]"}]
    result = build_attendance_rows(match_rows, _lookup(), activity="X", point_value=1, month="May")
    assert result.rows == []
    assert result.skipped_no_match == 2


def test_name_missing_from_directory_skipped_with_warning():
    match_rows = [{"Matched Standard Name": "Nobody Here"}]
    result = build_attendance_rows(match_rows, _lookup(), activity="X", point_value=1, month="May")
    assert result.rows == []
    assert result.skipped_not_found == ["Nobody Here"]


def test_name_lookup_is_whitespace_case_tolerant():
    match_rows = [{"Matched Standard Name": "  ada lovelace"}]
    result = build_attendance_rows(match_rows, _lookup(), activity="X", point_value=1, month="May")
    assert len(result.rows) == 1
    # Member Name written is the literal (trimmed) Matched Standard Name
    # cell text, not the directory's canonical casing — per spec.
    assert result.rows[0]["Member Name"] == "ada lovelace"
    assert result.rows[0]["Location"] == "Lagos"


def test_empty_match_rows_returns_empty_result():
    result = build_attendance_rows([], _lookup(), activity="X", point_value=1, month="May")
    assert result.rows == []
    assert result.skipped_no_match == 0
    assert result.skipped_not_found == []


def test_multiple_rows_same_activity_month():
    match_rows = [
        {"Matched Standard Name": "Ada Lovelace"},
        {"Matched Standard Name": "Alan Turing"},
    ]
    result = build_attendance_rows(
        match_rows, _lookup(), activity="Attending Trainings", point_value=5, month="July"
    )
    assert len(result.rows) == 2
    assert {row["Member Name"] for row in result.rows} == {"Ada Lovelace", "Alan Turing"}
    assert all(row["Activity"] == "Attending Trainings" and row["Month"] == "July" for row in result.rows)


def test_independent_across_two_calls():
    match_rows = [{"Matched Standard Name": "Ada Lovelace"}]
    first = build_attendance_rows(match_rows, _lookup(), activity="A1", point_value=1, month="January")
    second = build_attendance_rows(match_rows, _lookup(), activity="A2", point_value=9, month="February")
    assert first.rows[0]["Activity"] == "A1"
    assert first.rows[0]["Point"] == 1
    assert second.rows[0]["Activity"] == "A2"
    assert second.rows[0]["Point"] == 9
