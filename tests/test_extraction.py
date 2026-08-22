import io
import json
from types import SimpleNamespace

import pytest
from PIL import Image

from core import extraction
from core.gemini_client import GeminiCallError


def _fake_response(text, finish_reason="STOP"):
    return SimpleNamespace(text=text, candidates=[SimpleNamespace(finish_reason=finish_reason)])


def _png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), color="white").save(buffer, format="PNG")
    return buffer.getvalue()


def test_encode_image_valid_returns_jpeg_bytes():
    jpeg_bytes = extraction.encode_image(_png_bytes())
    assert isinstance(jpeg_bytes, bytes)
    assert jpeg_bytes[:2] == b"\xff\xd8"  # JPEG magic bytes


def test_encode_image_invalid_bytes_raises():
    with pytest.raises(extraction.ImageDecodeError):
        extraction.encode_image(b"not an image")


def test_extract_names_from_image_success(monkeypatch):
    monkeypatch.setattr(
        extraction,
        "safe_generate_content",
        lambda **kwargs: _fake_response(json.dumps({"names": ["John Doe", "Jane Smith"]})),
    )
    names, error = extraction.extract_names_from_image(_png_bytes(), "shot.png")
    assert names == ["John Doe", "Jane Smith"]
    assert error is None


def test_extract_names_from_image_bad_json(monkeypatch):
    # Defensive path — response_schema should make this rare in practice,
    # but the code still guards against a malformed/empty result.
    monkeypatch.setattr(extraction, "safe_generate_content", lambda **kwargs: _fake_response("nope"))
    names, error = extraction.extract_names_from_image(_png_bytes(), "shot.png")
    assert names == []
    assert error is not None and "shot.png" in error


def test_extract_names_from_image_bad_file():
    names, error = extraction.extract_names_from_image(b"garbage", "bad.png")
    assert names == []
    assert error is not None and "bad.png" in error


def test_extract_names_from_image_empty_response_reports_finish_reason(monkeypatch):
    # Reproduces the thinking-budget-exhaustion failure class: empty text,
    # finish_reason explains why instead of a generic parse error.
    monkeypatch.setattr(
        extraction,
        "safe_generate_content",
        lambda **kwargs: _fake_response("", finish_reason="MAX_TOKENS"),
    )
    names, error = extraction.extract_names_from_image(_png_bytes(), "dense.jpeg")
    assert names == []
    assert error is not None and "MAX_TOKENS" in error


def test_extract_names_from_image_reports_error_on_api_failure(monkeypatch):
    def fake_call(**kwargs):
        raise GeminiCallError("boom")

    monkeypatch.setattr(extraction, "safe_generate_content", fake_call)
    names, error = extraction.extract_names_from_image(_png_bytes(), "shot.jpeg")
    assert names == []
    assert error is not None and "shot.jpeg" in error


def test_extract_names_from_images_aggregates(monkeypatch):
    monkeypatch.setattr(
        extraction,
        "safe_generate_content",
        lambda **kwargs: _fake_response(json.dumps({"names": ["A", "B"]})),
    )
    files = [(_png_bytes(), "one.png"), (_png_bytes(), "two.png")]
    all_names, errors = extraction.extract_names_from_images(files)
    assert all_names == ["A", "B", "A", "B"]
    assert errors == []


def test_extract_names_from_images_reports_progress(monkeypatch):
    monkeypatch.setattr(
        extraction,
        "safe_generate_content",
        lambda **kwargs: _fake_response(json.dumps({"names": ["A"]})),
    )
    files = [(_png_bytes(), "one.png"), (_png_bytes(), "two.png"), (_png_bytes(), "three.png")]

    calls = []
    extraction.extract_names_from_images(
        files, on_progress=lambda completed, total, filename: calls.append((completed, total, filename))
    )

    assert calls == [(1, 3, "one.png"), (2, 3, "two.png"), (3, 3, "three.png")]


def test_extract_names_from_images_progress_called_even_on_error(monkeypatch):
    monkeypatch.setattr(extraction, "safe_generate_content", lambda **kwargs: _fake_response("nope"))
    files = [(_png_bytes(), "bad.png")]

    calls = []
    _, errors = extraction.extract_names_from_images(
        files, on_progress=lambda completed, total, filename: calls.append((completed, total, filename))
    )

    assert calls == [(1, 1, "bad.png")]
    assert len(errors) == 1
