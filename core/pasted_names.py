"""Parses names pasted directly into the app — the alternative to uploading
screenshots, for when you already have a plain-text attendee list. Accepts
one name per line, comma-separated, or a mix of both.
"""

from __future__ import annotations

import re

_SPLIT_PATTERN = re.compile(r"[\n,]+")


def parse_pasted_names(text: str) -> list[str]:
    return [part.strip() for part in _SPLIT_PATTERN.split(text) if part.strip()]
