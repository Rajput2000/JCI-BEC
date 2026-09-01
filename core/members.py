"""Loads the Standard Member List.

This is deliberately the one isolated seam for that data source. It now
reads from Google Sheets first (the Member Directory tab -- see
core/sheets_client.py), falling back to a CSV (Streamlit secrets, then a
local file) when Sheets isn't configured -- the CSV path is kept as a
documented local-dev fallback, not removed. When the source needs to
change again, only the body of `load_standard_members` needs to change --
every call site stays the same.

Data is re-read fresh on every call (no caching) so a swapped-in live
source (the sheet edited between runs) is always reflected without needing
a cache-clear step.
"""

from __future__ import annotations

import io
import os
from pathlib import Path

import pandas as pd
import streamlit as st

from . import sheets_client
from .sheets_client import SheetsError

DEFAULT_CSV_PATH = os.getenv("STANDARD_MEMBERS_CSV_PATH", "data/standard_members.csv")

# Member Directory's real column names (confirmed via live read): Member
# Code, Member Name, Location, Family Unit.
_DIRECTORY_NAME_COL = "Member Name"
_DIRECTORY_LOCATION_COL = "Location"
_DIRECTORY_FAMILY_UNIT_COL = "Family Unit"


class MembersLoadError(RuntimeError):
    """Raised when the Standard Member List can't be loaded or is empty."""


def _read_from_sheets() -> pd.DataFrame | None:
    """Primary source: the Member Directory tab's Member Name column,
    renamed to 'name' for compatibility with the dedup/clean loop below.
    Returns None (never raises) if Sheets isn't configured/reachable, so
    load_standard_members() falls through to the existing secrets/file CSV
    chain -- same "try new source, fall back to old" shape as that chain
    already has."""
    try:
        records = sheets_client.read_all_records(sheets_client.MEMBER_DIRECTORY_TAB)
    except SheetsError:
        return None
    if not records or _DIRECTORY_NAME_COL not in records[0]:
        return None
    return pd.DataFrame(records).rename(columns={_DIRECTORY_NAME_COL: "name"})


def load_member_directory_records() -> list[dict]:
    """Full Member Directory rows (Member Name, Location, Family Unit) for
    the Step 5 Location/Family Unit lookup. Sheets-only, no CSV fallback --
    Location/Family Unit don't exist in the legacy CSV format, so Step 5
    inherently requires Sheets to be configured. Raises MembersLoadError
    (not SheetsError) so callers only need the one except-clause shape this
    module already uses everywhere else."""
    try:
        records = sheets_client.read_all_records(sheets_client.MEMBER_DIRECTORY_TAB)
    except SheetsError as exc:
        raise MembersLoadError(f"Could not load Member Directory from Google Sheets: {exc}") from exc

    if not records:
        raise MembersLoadError("Member Directory tab is empty.")

    missing = [
        c for c in (_DIRECTORY_NAME_COL, _DIRECTORY_LOCATION_COL, _DIRECTORY_FAMILY_UNIT_COL)
        if c not in records[0]
    ]
    if missing:
        raise MembersLoadError(
            f"Member Directory is missing column(s) {missing}. Found: {list(records[0].keys())}"
        )
    return records


def _read_from_secrets() -> pd.DataFrame | None:
    """On Streamlit Community Cloud, the real roster lives in the app's
    Secrets (Settings -> Secrets in the dashboard), never in the repo. Local
    dev typically has no secrets.toml at all, so any failure here just means
    "fall back to the file" rather than an error."""
    try:
        csv_text = st.secrets["data"]["standard_members_csv"]
    except Exception:
        return None
    return pd.read_csv(io.StringIO(csv_text))


def _read_from_file(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise MembersLoadError(
            f"Standard member list not found at: {path}. Either create that "
            "file locally (see data/standard_members.example.csv), or set it "
            "in Streamlit secrets under [data] standard_members_csv for a "
            "cloud deployment."
        )
    try:
        return pd.read_csv(path)
    except Exception as exc:
        raise MembersLoadError(f"Could not read standard member list at {path}: {exc}") from exc


def load_standard_members(path: str | Path = DEFAULT_CSV_PATH) -> list[str]:
    df = _read_from_sheets()
    source = "Google Sheets (Member Directory)"
    if df is None:
        df = _read_from_secrets()
        source = "Streamlit secrets"
        if df is None:
            df = _read_from_file(Path(path))
            source = str(path)

    if "name" not in df.columns:
        raise MembersLoadError(f"Expected a 'name' column in {source}, found: {list(df.columns)}")

    names: list[str] = []
    seen: set[str] = set()
    for raw in df["name"].dropna():
        name = str(raw).strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)

    if not names:
        raise MembersLoadError(f"Standard member list from {source} is empty.")

    return names
