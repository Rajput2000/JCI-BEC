"""Vision-model extraction of attendee names from meeting screenshots.

Scope is intentionally narrow: this module's only job is "image -> list of
name strings that appear in it". Deduplication across images lives in
dedupe.py, and matching against the official roster lives in matching.py.
"""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Callable

from PIL import Image, UnidentifiedImageError

from .llm_client import generate
from .llm_types import LLMCallError, LLMRequest

logger = logging.getLogger(__name__)

_MAX_DIMENSION = 2000  # cap longest side so uploads stay well under API limits

_EXTRACTION_SYSTEM_PROMPT = (
    "You are an OCR assistant. You will be shown a screenshot of a video "
    "call's participant/attendance list (e.g. Zoom or Teams). Read every "
    "attendee name visible in the image.\n\n"
    "Ignore anything that is not a person's name: panel titles like "
    '"Participants (24)", buttons like "Mute All" or "Admit", timestamps, '
    "role labels, and UI chrome in general. If a name has a suffix like "
    '"(Host)" or "(Co-host)", strip the suffix and keep just the name.\n\n'
    "If no names are visible, return an empty list."
)

_NAMES_SCHEMA = {
    "type": "object",
    "properties": {
        "names": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["names"],
}


class ImageDecodeError(RuntimeError):
    """Raised when an uploaded file isn't a readable image."""


def encode_image(file_bytes: bytes) -> bytes:
    """Validate and downsize if needed, returning re-encoded JPEG bytes."""
    try:
        image = Image.open(io.BytesIO(file_bytes))
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise ImageDecodeError(f"Not a readable image: {exc}") from exc

    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")

    if max(image.size) > _MAX_DIMENSION:
        image.thumbnail((_MAX_DIMENSION, _MAX_DIMENSION))

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


def extract_names_from_image(file_bytes: bytes, filename: str) -> tuple[list[str], str | None]:
    """Returns (names, error_message). error_message is None on success;
    on failure names is [] and error_message describes what went wrong,
    letting callers skip a bad file without aborting the whole batch."""
    try:
        jpeg_bytes = encode_image(file_bytes)
    except ImageDecodeError as exc:
        return [], f"{filename}: {exc}"

    request = LLMRequest(
        task="vision",
        prompt="Extract every attendee name from this screenshot.",
        system_prompt=_EXTRACTION_SYSTEM_PROMPT,
        image_jpeg=jpeg_bytes,
        json_schema=_NAMES_SCHEMA,
        max_output_tokens=4096,
        # Reading names needs no reasoning; thinking can eat the whole token budget.
        thinking_budget=0,
    )

    try:
        raw_content = generate(request).text
    except LLMCallError as exc:
        return [], f"{filename}: {exc}"

    try:
        payload = json.loads(raw_content)
        names = payload.get("names", [])
        if not isinstance(names, list):
            raise ValueError("'names' was not a list")
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Could not parse extraction response for %s: %s", filename, exc)
        return [], f"{filename}: model response wasn't valid JSON ({exc})"

    return [str(n).strip() for n in names if str(n).strip()], None


def extract_names_from_images(
    files: list[tuple[bytes, str]],
    on_progress: Callable[[int, int, str], None] | None = None,
) -> tuple[list[str], list[tuple[str, str]]]:
    """Sequential (not concurrent, to stay well within rate limits)
    extraction across multiple uploaded files. Returns (all_names,
    [(filename, error)]).

    If given, on_progress(completed_count, total_count, filename) is called
    right after each image finishes (success or failure), so a caller like
    the Streamlit UI can show live "N of M done" progress across a batch
    instead of one opaque spinner for the whole thing."""
    all_names: list[str] = []
    errors: list[tuple[str, str]] = []
    total = len(files)

    for completed, (file_bytes, filename) in enumerate(files, start=1):
        names, error = extract_names_from_image(file_bytes, filename)
        all_names.extend(names)
        if error:
            errors.append((filename, error))
        if on_progress is not None:
            on_progress(completed, total, filename)

    return all_names, errors
