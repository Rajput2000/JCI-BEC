"""Shared Gemini client setup: API key resolution, model-id config, and a
retry/error-normalizing wrapper around content generation.

Model IDs are intentionally env-var overridable (not hardcoded at call
sites) because Google rotates/deprecates hosted models over time. Check
https://ai.google.dev/gemini-api/docs/models if a default here goes stale.

Migrated from Groq (see README.md's "Why Gemini, not Groq" section) because
Groq's free-tier token-per-minute cap (8,000 TPM for the models we were
using) was the direct cause of repeated failures against this app's real
workload (a 150+ name roster plus a full matching table as output).
Gemini's free tier has dramatically more TPM headroom for the same kind of
work. That said, Gemini's "thinking" models have the *same* failure class
Groq's did — they can spend their whole token budget reasoning and return
empty content — so the same defensive pattern (explicit thinking control,
generous max_output_tokens, and an empty-response check) is applied here
too, not assumed away by the switch.
"""

from __future__ import annotations

import logging
import os
import time

import streamlit as st
from dotenv import load_dotenv
from google import genai
from google.genai import errors, types

load_dotenv()

logger = logging.getLogger(__name__)

# Gemini models are natively multimodal, so one model can do both jobs —
# but these stay separately configurable (like the old Groq setup) in case
# you want a cheaper/faster model for one step and a stronger one for the
# other. Verified against Google's docs as of Aug 2026.
VISION_MODEL = os.getenv("GEMINI_VISION_MODEL", "gemini-2.5-flash")
TEXT_MODEL = os.getenv("GEMINI_TEXT_MODEL", "gemini-2.5-flash")

_MAX_RETRIES = 2
_BASE_BACKOFF_SECONDS = 2.0
_RATE_LIMIT_STATUS = 429


class GeminiCallError(RuntimeError):
    """Raised for any Gemini API failure, after retries are exhausted."""


def _resolve_api_key() -> str | None:
    """Look for the API key in the environment first, then Streamlit secrets
    (so this works both for local `.env` runs and Streamlit Cloud)."""
    key = os.environ.get("GEMINI_API_KEY")
    if key:
        return key
    try:
        return st.secrets["GEMINI_API_KEY"]
    except Exception:
        return None


@st.cache_resource(show_spinner=False)
def get_client() -> genai.Client:
    api_key = _resolve_api_key()
    if not api_key:
        raise GeminiCallError(
            "GEMINI_API_KEY is not set. Add it to a .env file (see "
            ".env.example) or to Streamlit secrets. Get a key at "
            "https://aistudio.google.com/apikey"
        )
    return genai.Client(api_key=api_key)


def safe_generate_content(
    *, model: str, contents: list, config: types.GenerateContentConfig
) -> types.GenerateContentResponse:
    """Thin wrapper around client.models.generate_content with retry/backoff
    on rate limits and uniform error handling for callers. The SDK already
    retries some transient errors internally; this adds an app-level retry
    specifically for 429s plus a consistent GeminiCallError for callers,
    mirroring the old Groq wrapper's shape."""
    client = get_client()
    last_error: Exception | None = None

    for attempt in range(_MAX_RETRIES + 1):
        try:
            return client.models.generate_content(model=model, contents=contents, config=config)
        except errors.APIError as exc:
            last_error = exc
            if exc.code == _RATE_LIMIT_STATUS and attempt < _MAX_RETRIES:
                wait = _BASE_BACKOFF_SECONDS * (2**attempt)
                logger.warning("Gemini rate limited, retrying in %.1fs", wait)
                time.sleep(wait)
                continue
            break

    raise GeminiCallError(f"Gemini API call failed: {last_error}") from last_error
