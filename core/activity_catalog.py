"""Loads the Activity Catalog tab for the Step 5 Activity dropdown and its
per-activity point lookup.

Real column names (confirmed via a live read-only connection to the actual
spreadsheet): Activity Code, Category, Activity Name, Points.
"""

from __future__ import annotations

from . import sheets_client
from .sheets_client import SheetsError

ACTIVITY_NAME_COL = "Activity Name"
POINTS_COL = "Points"


class ActivityCatalogError(RuntimeError):
    """Raised when the Activity Catalog can't be loaded or is malformed."""


def load_activity_catalog() -> list[dict]:
    """Live read of the Activity Catalog tab. Raises ActivityCatalogError if
    Sheets is unreachable, the tab is empty, or expected columns are
    missing."""
    try:
        records = sheets_client.read_all_records(sheets_client.ACTIVITY_CATALOG_TAB)
    except SheetsError as exc:
        raise ActivityCatalogError(f"Could not load the Activity Catalog: {exc}") from exc

    if not records:
        raise ActivityCatalogError("Activity Catalog tab is empty.")

    missing = [c for c in (ACTIVITY_NAME_COL, POINTS_COL) if c not in records[0]]
    if missing:
        raise ActivityCatalogError(
            f"Activity Catalog is missing column(s) {missing}. Found: {list(records[0].keys())}"
        )
    return records


def get_activity_options(records: list[dict]) -> list[str]:
    """Ordered, deduped, blank-filtered list of Activity Name values for the
    dropdown."""
    options: list[str] = []
    seen: set[str] = set()
    for rec in records:
        name = str(rec.get(ACTIVITY_NAME_COL, "")).strip()
        if name and name not in seen:
            seen.add(name)
            options.append(name)
    return options


def get_point_value(records: list[dict], activity: str) -> float:
    """Case/whitespace-tolerant lookup of Points for the given Activity
    Name. Raises ActivityCatalogError if not found or the Points cell isn't
    numeric."""
    target = activity.strip().casefold()
    for rec in records:
        if str(rec.get(ACTIVITY_NAME_COL, "")).strip().casefold() == target:
            raw = rec.get(POINTS_COL)
            try:
                return float(raw)
            except (TypeError, ValueError):
                raise ActivityCatalogError(f"Points value for {activity!r} is not numeric: {raw!r}")
    raise ActivityCatalogError(f"Activity {activity!r} not found in Activity Catalog.")
