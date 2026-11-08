"""Gemini adapter: turns an LLMRequest into a google-genai call, with a 429 retry and a request timeout.

Model IDs are env-overridable because Google rotates hosted models; see
https://ai.google.dev/gemini-api/docs/models if a default goes stale.
"""

from __future__ import annotations

import logging
import os
import time

import httpx
import streamlit as st
from dotenv import load_dotenv
from google import genai
from google.genai import errors, types

from .llm_types import LLMCallError, LLMRequest, LLMResult
from .settings import resolve_setting

load_dotenv()

logger = logging.getLogger(__name__)

PROVIDER_NAME = "gemini"
VISION_MODEL = os.getenv("GEMINI_VISION_MODEL", "gemini-3.8-flash")
TEXT_MODEL = os.getenv("GEMINI_TEXT_MODEL", "gemini-3.8-flash")
# Without a timeout a hung call never fails, so the fallback provider never gets a chance.
_TIMEOUT_SECONDS = float(os.getenv("GEMINI_TIMEOUT_SECONDS", "120"))

_MAX_RETRIES = 2
_BASE_BACKOFF_SECONDS = 2.0
_RATE_LIMIT_STATUS = 429


@st.cache_resource(show_spinner=False)
def get_client() -> genai.Client:
    api_key = resolve_setting("GEMINI_API_KEY")
    if not api_key:
        raise LLMCallError(
            "GEMINI_API_KEY is not set. Add it to a .env file (see .env.example) "
            "or to Streamlit secrets. Get a key at https://aistudio.google.com/apikey"
        )
    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=int(_TIMEOUT_SECONDS * 1000)),
    )


def build_config(request: LLMRequest) -> types.GenerateContentConfig:
    json_options = {}
    if request.json_schema is not None:
        json_options = {"response_mime_type": "application/json", "response_schema": request.json_schema}
    return types.GenerateContentConfig(
        system_instruction=request.system_prompt,
        temperature=0,
        max_output_tokens=request.max_output_tokens,
        thinking_config=types.ThinkingConfig(thinking_budget=request.thinking_budget),
        **json_options,
    )


def build_contents(request: LLMRequest) -> list:
    if request.image_jpeg is None:
        return [request.prompt]
    return [request.prompt, types.Part.from_bytes(data=request.image_jpeg, mime_type="image/jpeg")]


def _finish_reason_name(response: types.GenerateContentResponse) -> str | None:
    if not response.candidates:
        return None
    reason = response.candidates[0].finish_reason
    return getattr(reason, "name", None) or (str(reason) if reason is not None else None)


def generate(request: LLMRequest) -> LLMResult:
    """Returns the model's text (possibly empty); raises LLMCallError on API or network failure."""
    model = VISION_MODEL if request.task == "vision" else TEXT_MODEL
    client = get_client()
    config = build_config(request)
    contents = build_contents(request)
    last_error: Exception | None = None

    for attempt in range(_MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(model=model, contents=contents, config=config)
            return LLMResult(
                text=response.text or "",
                finish_reason=_finish_reason_name(response),
                provider=PROVIDER_NAME,
            )
        except errors.APIError as exc:
            last_error = exc
            if exc.code == _RATE_LIMIT_STATUS and attempt < _MAX_RETRIES:
                wait = _BASE_BACKOFF_SECONDS * (2**attempt)
                logger.warning("gemini_rate_limited: retry_in_seconds=%.1f", wait)
                time.sleep(wait)
                continue
            break
        except httpx.HTTPError as exc:
            last_error = exc
            break

    raise LLMCallError(f"Gemini API call failed: {last_error}") from last_error
