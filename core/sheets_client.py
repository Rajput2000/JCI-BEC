"""Google Sheets boundary layer: service-account credential resolution,
client/spreadsheet setup, and uniform error handling for the three tabs
this app reads/writes (Member Directory, Activity Catalog, Raw Data).

This is the *only* module that imports gspread or google.oauth2 — every
other module talks to Sheets through the functions here, so it's the one
seam callers' tests need to mock. Mirrors core/gemini_client.py's shape:
env-var-first-then-st.secrets resolution, a cached client getter, and one
uniform exception (SheetsError) instead of letting raw gspread/google-auth
exceptions escape to callers.

The target spreadsheet in production use has 40+ unrelated tabs (old
monthly copies, leaderboards, etc.) alongside the three this app cares
about — every read/write here addresses a tab strictly by exact name via
the *_TAB constants below, never "first sheet" or fuzzy matching.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

import gspread
import streamlit as st
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

load_dotenv()

logger = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Tab names are env-overridable (same rationale as GEMINI_VISION_MODEL etc.
# in gemini_client.py) in case the sheet owner ever renames a tab.
MEMBER_DIRECTORY_TAB = os.getenv("SHEETS_MEMBER_DIRECTORY_TAB", "Member Directory")
ACTIVITY_CATALOG_TAB = os.getenv("SHEETS_ACTIVITY_CATALOG_TAB", "Activity Catalog")
RAW_DATA_TAB = os.getenv("SHEETS_RAW_DATA_TAB", "Raw Data")

_MAX_RETRIES = 2
_BASE_BACKOFF_SECONDS = 2.0
_RATE_LIMIT_STATUS = 429


class SheetsError(RuntimeError):
    """Raised for any Google Sheets access failure: missing config, auth
    failure, missing tab, or an API error — after retries are exhausted."""


def _resolve_credentials() -> Credentials | None:
    """Local dev: GOOGLE_SERVICE_ACCOUNT_JSON_PATH env var (default
    service_account.json at the repo root) -> a gitignored key file.
    Streamlit Cloud: st.secrets["gcp_service_account"] -- Streamlit's own
    documented convention for this exact use case. Returns None (never
    raises) so callers can treat "not configured" uniformly rather than
    catching two different failure shapes."""
    file_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_PATH", "service_account.json")
    if file_path and Path(file_path).exists():
        try:
            return Credentials.from_service_account_file(file_path, scopes=_SCOPES)
        except Exception as exc:
            logger.warning("Could not load service account file %s: %s", file_path, exc)

    try:
        info = dict(st.secrets["gcp_service_account"])
    except Exception:
        return None
    try:
        return Credentials.from_service_account_info(info, scopes=_SCOPES)
    except Exception as exc:
        logger.warning("Could not build credentials from st.secrets: %s", exc)
        return None


def _resolve_spreadsheet_id() -> str | None:
    """Same env-then-secrets shape as gemini_client._resolve_api_key()."""
    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    if sheet_id:
        return sheet_id
    try:
        return st.secrets["GOOGLE_SHEET_ID"]
    except Exception:
        return None


def is_configured() -> bool:
    """Cheap, no-API-call check for whether Sheets is usable at all --
    lets app.py decide whether to show the Step 5 section without making
    a network round-trip just to find out."""
    return _resolve_credentials() is not None and bool(_resolve_spreadsheet_id())


@st.cache_resource(show_spinner=False)
def get_client() -> gspread.Client:
    creds = _resolve_credentials()
    if creds is None:
        raise SheetsError(
            "Google Sheets credentials not found. For local dev, save a "
            "service-account JSON key as service_account.json (or set "
            "GOOGLE_SERVICE_ACCOUNT_JSON_PATH). For Streamlit Cloud, add a "
            "[gcp_service_account] block to secrets (see "
            ".streamlit/secrets.toml.example)."
        )
    return gspread.authorize(creds)


@st.cache_resource(show_spinner=False)
def get_spreadsheet() -> gspread.Spreadsheet:
    spreadsheet_id = _resolve_spreadsheet_id()
    if not spreadsheet_id:
        raise SheetsError(
            "GOOGLE_SHEET_ID is not set. Add it to .env (see .env.example) "
            "or to Streamlit secrets."
        )
    client = get_client()
    try:
        return client.open_by_key(spreadsheet_id)
    except gspread.exceptions.APIError as exc:
        raise SheetsError(f"Could not open spreadsheet {spreadsheet_id}: {exc}") from exc
    except gspread.exceptions.SpreadsheetNotFound as exc:
        raise SheetsError(
            f"Spreadsheet {spreadsheet_id} not found, or not shared with "
            "this service account (share it with the client_email in your "
            "service-account key, as Editor)."
        ) from exc


def _with_retry(fn, *args, **kwargs):
    """Retries once/twice on a 429 rate-limit response before giving up --
    the same shape as gemini_client.safe_generate_content's retry, needed
    here too since a single Sheets API key can be shared across many tabs
    (this spreadsheet has 40+) and rate limits are per-project, not
    per-tab."""
    last_error: Exception | None = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            return fn(*args, **kwargs)
        except gspread.exceptions.APIError as exc:
            last_error = exc
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status == _RATE_LIMIT_STATUS and attempt < _MAX_RETRIES:
                wait = _BASE_BACKOFF_SECONDS * (2**attempt)
                logger.warning("Sheets API rate limited, retrying in %.1fs", wait)
                time.sleep(wait)
                continue
            raise SheetsError(f"Google Sheets API call failed: {exc}") from exc
    raise SheetsError(f"Google Sheets API call failed: {last_error}") from last_error


def _get_worksheet(tab_name: str) -> gspread.Worksheet:
    spreadsheet = get_spreadsheet()
    try:
        return spreadsheet.worksheet(tab_name)
    except gspread.exceptions.WorksheetNotFound as exc:
        raise SheetsError(
            f"Tab {tab_name!r} not found in the spreadsheet. Available tabs: "
            f"{[ws.title for ws in spreadsheet.worksheets()]}"
        ) from exc


def read_all_records(tab_name: str) -> list[dict]:
    """Reads every data row of a tab as a list of dicts keyed by its header
    row (row 1). Never cached -- every call is a live read, so Preview
    always reflects the sheet's current contents."""
    worksheet = _get_worksheet(tab_name)
    return _with_retry(worksheet.get_all_records)


def append_rows(tab_name: str, rows: list[list]) -> int:
    """Appends rows after the last existing row of a tab -- never touches
    the header or any existing row. No-ops (no API call) on an empty list."""
    if not rows:
        return 0
    worksheet = _get_worksheet(tab_name)
    _with_retry(worksheet.append_rows, rows, value_input_option="USER_ENTERED")
    return len(rows)


def append_attendance_rows(rows: list[dict]) -> int:
    """Attendance-specific convenience wrapper: column-orders rows (each
    keyed by core.records.RAW_DATA_COLUMNS) and appends them to
    RAW_DATA_TAB."""
    from .records import RAW_DATA_COLUMNS

    as_lists = [[row.get(col, "") for col in RAW_DATA_COLUMNS] for row in rows]
    return append_rows(RAW_DATA_TAB, as_lists)
