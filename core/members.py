"""Loads the Standard Member List.

This is deliberately the one isolated seam for that data source. Today it
reads a CSV — from Streamlit secrets when deployed (so the real roster never
has to live in the git repo), or from a local file for local dev — and the
user has flagged that it will later be sourced from a Google Form's
responses instead. When that happens, only the body of
`load_standard_members` needs to change — every call site stays the same.

Data is re-read fresh on every call (no caching) so that a swapped-in live
source (CSV edited between runs, or eventually a form/sheet) is always
reflected without needing a cache-clear step.
"""

from __future__ import annotations

import io
import os
from pathlib import Path

import pandas as pd
import streamlit as st

DEFAULT_CSV_PATH = os.getenv("STANDARD_MEMBERS_CSV_PATH", "data/standard_members.csv")


class MembersLoadError(RuntimeError):
    """Raised when the Standard Member List can't be loaded or is empty."""


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
