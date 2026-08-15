"""Shared Groq client setup: API key resolution, model-id config, and a
retry/error-normalizing wrapper around chat completions.

Model IDs are intentionally env-var overridable (not hardcoded at call
sites) because Groq deprecates/rotates hosted models on a rolling basis.
Check https://console.groq.com/docs/models if a default here goes stale.
"""

from __future__ import annotations

import logging
import os
import time

import groq
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Current recommended defaults (verified against Groq's docs, Aug 2026).
# Override via env var without touching code if Groq's lineup changes.
VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "qwen/qwen3.6-27b")
TEXT_MODEL = os.getenv("GROQ_TEXT_MODEL", "openai/gpt-oss-120b")

_MAX_RETRIES = 2
_BASE_BACKOFF_SECONDS = 2.0


class GroqCallError(RuntimeError):
    """Raised for any Groq API failure, after retries are exhausted."""


def _resolve_api_key() -> str | None:
    """Look for the API key in the environment first, then Streamlit secrets
    (so this works both for local `.env` runs and Streamlit Cloud)."""
    key = os.environ.get("GROQ_API_KEY")
    if key:
        return key
    try:
        return st.secrets["GROQ_API_KEY"]
    except Exception:
        return None


@st.cache_resource(show_spinner=False)
def get_client() -> groq.Groq:
    api_key = _resolve_api_key()
    if not api_key:
        raise GroqCallError(
            "GROQ_API_KEY is not set. Add it to a .env file (see "
            ".env.example) or to Streamlit secrets."
        )
    return groq.Groq(api_key=api_key)


def safe_chat_completion(**kwargs):
    """Thin wrapper around client.chat.completions.create with retry/backoff
    on rate limits and uniform error handling for callers."""
    client = get_client()
    last_error: Exception | None = None

    for attempt in range(_MAX_RETRIES + 1):
        try:
            return client.chat.completions.create(**kwargs)
        except groq.RateLimitError as exc:
            last_error = exc
            if attempt < _MAX_RETRIES:
                wait = _BASE_BACKOFF_SECONDS * (2**attempt)
                logger.warning("Groq rate limited, retrying in %.1fs", wait)
                time.sleep(wait)
                continue
        except (
            groq.APIConnectionError,
            groq.APIStatusError,
            groq.AuthenticationError,
        ) as exc:
            last_error = exc
            break

    raise GroqCallError(f"Groq API call failed: {last_error}") from last_error
