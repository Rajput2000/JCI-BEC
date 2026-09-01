"""Pure row-building logic for Step 5 ("post attendance to Google Sheets").

Deliberately has no gspread or Streamlit import -- plain data in, plain
data out -- so it's independently unit-testable without mocking anything,
per this project's "core/ modules get unit tests" convention. Everything
that actually talks to Sheets lives in sheets_client.py / activity_catalog.py
/ members.py instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .dedupe import normalize_name
from .parsing import is_no_match

# Raw Data's real column order (confirmed via a live read-only connection to
# the actual spreadsheet): Member Name, Location, Activity, Point, Quantity
# (the sheet's literal header has a trailing space on "Quantity ", but rows
# are appended by column position, not by header text, so that's irrelevant
# here), Total Point, Month, Family Unit.
RAW_DATA_COLUMNS = [
    "Member Name",
    "Location",
    "Activity",
    "Point",
    "Quantity",
    "Total Point",
    "Month",
    "Family Unit",
]

MONTH_OPTIONS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

# Member Directory's real column names (confirmed via live read): Member
# Code, Member Name, Location, Family Unit.
_DIRECTORY_NAME_COL = "Member Name"
_DIRECTORY_LOCATION_COL = "Location"
_DIRECTORY_FAMILY_UNIT_COL = "Family Unit"


@dataclass
class BuildResult:
    rows: list[dict]
    skipped_no_match: int = 0
    skipped_not_found: list[str] = field(default_factory=list)


def build_member_lookup(directory_records: list[dict]) -> dict[str, dict]:
    """Builds a normalize_name-keyed lookup from raw Member Directory rows
    (as returned by sheets_client.read_all_records), reusing the same
    strip/collapse/casefold key already used for name dedup elsewhere in
    this app. Blank-name rows are skipped."""
    lookup: dict[str, dict] = {}
    for rec in directory_records:
        name = str(rec.get(_DIRECTORY_NAME_COL, "")).strip()
        if not name:
            continue
        lookup[normalize_name(name)] = {
            "name": name,
            "location": str(rec.get(_DIRECTORY_LOCATION_COL, "")).strip(),
            "family_unit": str(rec.get(_DIRECTORY_FAMILY_UNIT_COL, "")).strip(),
        }
    return lookup


def build_attendance_rows(
    match_rows: list[dict],
    member_lookup: dict[str, dict],
    *,
    activity: str,
    point_value: float,
    month: str,
) -> BuildResult:
    """Builds the rows that would be appended to Raw Data from the
    (possibly hand-edited) Results table -- each dict in match_rows is
    expected to have a "Matched Standard Name" key (the shape
    core.parsing.to_display_rows() produces). [NO MATCH] rows are always
    skipped. A matched name not found in member_lookup is skipped and
    recorded in skipped_not_found rather than raising, so one bad row
    doesn't block previewing the rest."""
    rows: list[dict] = []
    skipped_no_match = 0
    skipped_not_found: list[str] = []

    for row in match_rows:
        matched_name = str(row.get("Matched Standard Name", "")).strip()
        if not matched_name or is_no_match(matched_name):
            skipped_no_match += 1
            continue

        member = member_lookup.get(normalize_name(matched_name))
        if member is None:
            skipped_not_found.append(matched_name)
            continue

        quantity = 1
        rows.append({
            "Member Name": matched_name,
            "Location": member["location"],
            "Activity": activity,
            "Point": point_value,
            "Quantity": quantity,
            "Total Point": quantity * point_value,
            "Month": month,
            "Family Unit": member["family_unit"],
        })

    return BuildResult(rows=rows, skipped_no_match=skipped_no_match, skipped_not_found=skipped_not_found)
