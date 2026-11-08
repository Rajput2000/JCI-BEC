"""OpenRouter fallback adapter: sends an LLMRequest to OpenRouter's OpenAI-compatible chat completions API.

Free models are listed at https://openrouter.ai/models?q=free; they can be
withdrawn without notice, so OPENROUTER_MODELS takes a comma-separated list
and OpenRouter tries each in order.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time

import httpx

from .llm_types import LLMCallError, LLMRequest, LLMResult
from .settings import resolve_setting

logger = logging.getLogger(__name__)

PROVIDER_NAME = "openrouter"
_API_URL = "https://openrouter.ai/api/v1/chat/completions"
_DEFAULT_MODELS = "dots-studio/dots-3-note-preview:free"
# Free models measured at 85-110s per call on this app's workload.
_TIMEOUT_SECONDS = float(os.getenv("OPENROUTER_TIMEOUT_SECONDS", "240"))
# Reasoning models count thinking toward max_tokens; matching used ~11k output tokens in testing.
_MIN_MAX_TOKENS = 16384
_RETRYABLE_STATUSES = {429, 500, 502, 503, 504}
_RETRY_BACKOFF_SECONDS = 3.0

_JSON_INSTRUCTION = (
    "Reply with only one JSON object that matches this JSON Schema, with no other "
    "text and no code fences:\n{schema}"
)


def get_api_key() -> str | None:
    return resolve_setting("OPENROUTER_API_KEY")


def is_configured() -> bool:
    return bool(get_api_key())


def get_models() -> list[str]:
    raw = resolve_setting("OPENROUTER_MODELS", _DEFAULT_MODELS) or _DEFAULT_MODELS
    return [model.strip() for model in raw.split(",") if model.strip()]


def build_messages(request: LLMRequest) -> list[dict]:
    system_parts = [request.system_prompt] if request.system_prompt else []
    if request.json_schema is not None:
        system_parts.append(_JSON_INSTRUCTION.format(schema=json.dumps(request.json_schema)))

    messages: list[dict] = []
    if system_parts:
        messages.append({"role": "system", "content": "\n\n".join(system_parts)})

    if request.image_jpeg is None:
        messages.append({"role": "user", "content": request.prompt})
        return messages

    image_url = "data:image/jpeg;base64," + base64.b64encode(request.image_jpeg).decode("ascii")
    messages.append({
        "role": "user",
        "content": [
            {"type": "text", "text": request.prompt},
            {"type": "image_url", "image_url": {"url": image_url}},
        ],
    })
    return messages


def build_payload(request: LLMRequest, models: list[str]) -> dict:
    payload: dict = {
        "model": models[0],
        "messages": build_messages(request),
        "temperature": 0,
        "max_tokens": max(request.max_output_tokens, _MIN_MAX_TOKENS),
    }
    if len(models) > 1:
        payload["models"] = models
    if request.json_schema is not None:
        payload["response_format"] = {"type": "json_object"}
    return payload


def strip_code_fences(text: str) -> str:
    cleaned = text.strip()
    if not cleaned.startswith("```"):
        return cleaned
    cleaned = cleaned.removeprefix("```json").removeprefix("```")
    return cleaned.removesuffix("```").strip()


def parse_response(body: dict, expects_json: bool) -> LLMResult:
    choices = body.get("choices")
    if not choices:
        error = body.get("error") or "response contained no choices"
        raise LLMCallError(f"OpenRouter returned no answer: {error}")
    choice = choices[0]
    text = choice.get("message", {}).get("content") or ""
    if expects_json:
        text = strip_code_fences(text)
    return LLMResult(text=text, finish_reason=choice.get("finish_reason"), provider=PROVIDER_NAME)


def _post_once(payload: dict, api_key: str) -> httpx.Response:
    return httpx.post(
        _API_URL,
        headers={"Authorization": f"Bearer {api_key}", "X-Title": "JCI-BEC Attendance Matcher"},
        json=payload,
        timeout=_TIMEOUT_SECONDS,
    )


def generate(request: LLMRequest) -> LLMResult:
    """Returns the model's text (possibly empty); raises LLMCallError on API or network failure."""
    api_key = get_api_key()
    if not api_key:
        raise LLMCallError("OPENROUTER_API_KEY is not set.")

    models = get_models()
    payload = build_payload(request, models)
    logger.info("openrouter_generate called: task=%s models=%s", request.task, models)

    for attempt in range(2):
        is_last_attempt = attempt == 1
        try:
            response = _post_once(payload, api_key)
        except httpx.HTTPError as exc:
            if is_last_attempt:
                raise LLMCallError(f"OpenRouter request failed: {exc}") from exc
            logger.warning("openrouter_network_error: retrying error=%s", exc)
            time.sleep(_RETRY_BACKOFF_SECONDS)
            continue

        if response.status_code in _RETRYABLE_STATUSES and not is_last_attempt:
            logger.warning("openrouter_retryable_status: status=%s", response.status_code)
            time.sleep(_RETRY_BACKOFF_SECONDS)
            continue
        if response.status_code != 200:
            raise LLMCallError(f"OpenRouter returned HTTP {response.status_code}: {response.text[:300]}")

        try:
            body = response.json()
        except ValueError as exc:
            raise LLMCallError(f"OpenRouter response wasn't JSON: {exc}") from exc
        return parse_response(body, expects_json=request.json_schema is not None)

    raise LLMCallError("OpenRouter request failed after retrying.")  # unreachable; keeps type checkers happy
