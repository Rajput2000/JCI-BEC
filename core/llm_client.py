"""Single entry point for LLM calls: tries Gemini, then falls back to OpenRouter when Gemini fails or returns nothing."""

from __future__ import annotations

import logging

import streamlit as st

from . import gemini_client, openrouter_client
from .llm_types import LLMCallError, LLMRequest, LLMResult

logger = logging.getLogger(__name__)

_FALLBACK_NOTICE = "Gemini is unavailable — using the backup model. This step may take 1–2 minutes."


def _require_text(result: LLMResult) -> LLMResult:
    if result.text.strip():
        return result
    raise LLMCallError(
        f"{result.provider} returned an empty response (finish_reason={result.finish_reason!r}). "
        "It likely ran out of its token budget before writing an answer. Try again, or "
        "split the list into smaller batches."
    )


def _notify_fallback() -> None:
    try:
        st.toast(_FALLBACK_NOTICE)
    except Exception:  # no Streamlit session (e.g. tests or scripts): the log line is enough
        pass


def generate(request: LLMRequest) -> LLMResult:
    """Returns a non-empty result from Gemini or, failing that, OpenRouter; raises LLMCallError if both fail."""
    logger.info("llm_generate called: task=%s", request.task)
    try:
        return _require_text(gemini_client.generate(request))
    except LLMCallError as primary_error:
        if not openrouter_client.is_configured():
            raise
        logger.warning("llm_fallback_triggered: task=%s reason=%s", request.task, primary_error)
        _notify_fallback()
        try:
            result = _require_text(openrouter_client.generate(request))
        except LLMCallError as fallback_error:
            logger.error("llm_fallback_failed: task=%s reason=%s", request.task, fallback_error)
            raise LLMCallError(
                f"Both AI providers failed. Gemini: {primary_error} | Backup: {fallback_error}"
            ) from fallback_error
        logger.info("llm_fallback_succeeded: task=%s finish_reason=%s", request.task, result.finish_reason)
        return result
