"""Reads a config value from the environment first, then Streamlit secrets, so local `.env` runs and Streamlit Cloud both work."""

from __future__ import annotations

import os

import streamlit as st


def resolve_setting(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value:
        return value
    try:
        return st.secrets[name]
    except Exception:  # st.secrets raises different errors when no secrets file exists
        return default
