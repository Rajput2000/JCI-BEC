"""Provider-neutral request/result types and the single error type shared by every LLM adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

LLMTask = Literal["vision", "text"]


class LLMCallError(RuntimeError):
    """Raised when an LLM call fails, after that provider's retries are exhausted."""


@dataclass(frozen=True)
class LLMRequest:
    task: LLMTask
    prompt: str
    max_output_tokens: int
    thinking_budget: int
    system_prompt: str | None = None
    image_jpeg: bytes | None = None
    # When set, the model must reply with a single JSON object matching this schema.
    json_schema: dict | None = None


@dataclass(frozen=True)
class LLMResult:
    text: str
    finish_reason: str | None
    provider: str
