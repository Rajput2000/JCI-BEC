import io
import json
import pytest
from PIL import Image

from core import extraction
from core.llm_types import LLMCallError, LLMResult


def _fake_result(text):
    return LLMResult(text=text, finish_reason="STOP", provider="gemini")


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
        "generate",
        lambda request: _fake_result(json.dumps({"names": ["John Doe", "Jane Smith"]})),
    )
    names, error = extraction.extract_names_from_image(_png_bytes(), "shot.png")
    assert names == ["John Doe", "Jane Smith"]
    assert error is None


def test_extract_names_from_image_bad_json(monkeypatch):
    # Defensive path — response_schema should make this rare in practice,
    # but the code still guards against a malformed/empty result.
    monkeypatch.setattr(extraction, "generate", lambda request: _fake_result("nope"))
    names, error = extraction.extract_names_from_image(_png_bytes(), "shot.png")
    assert names == []
    assert error is not None and "shot.png" in error


def test_extract_names_from_image_bad_file():
    names, error = extraction.extract_names_from_image(b"garbage", "bad.png")
    assert names == []
    assert error is not None and "bad.png" in error


def test_extract_names_from_image_sends_image_as_vision_json_request(monkeypatch):
    captured = {}

    def fake_call(request):
        captured["request"] = request
        return _fake_result(json.dumps({"names": []}))

    monkeypatch.setattr(extraction, "generate", fake_call)
    extraction.extract_names_from_image(_png_bytes(), "shot.png")

    request = captured["request"]
    assert request.task == "vision"
    assert request.image_jpeg[:2] == b"\xff\xd8"
    assert request.json_schema == extraction._NAMES_SCHEMA
    assert request.thinking_budget == 0


def test_extract_names_from_image_reports_error_on_api_failure(monkeypatch):
    def fake_call(request):
        raise LLMCallError("boom")

    monkeypatch.setattr(extraction, "generate", fake_call)
    names, error = extraction.extract_names_from_image(_png_bytes(), "shot.jpeg")
    assert names == []
    assert error is not None and "shot.jpeg" in error


def test_extract_names_from_images_aggregates(monkeypatch):
    monkeypatch.setattr(
        extraction,
        "generate",
        lambda request: _fake_result(json.dumps({"names": ["A", "B"]})),
    )
    files = [(_png_bytes(), "one.png"), (_png_bytes(), "two.png")]
    all_names, errors = extraction.extract_names_from_images(files)
    assert all_names == ["A", "B", "A", "B"]
    assert errors == []


def test_extract_names_from_images_reports_progress(monkeypatch):
    monkeypatch.setattr(
        extraction,
        "generate",
        lambda request: _fake_result(json.dumps({"names": ["A"]})),
    )
    files = [(_png_bytes(), "one.png"), (_png_bytes(), "two.png"), (_png_bytes(), "three.png")]

    calls = []
    extraction.extract_names_from_images(
        files, on_progress=lambda completed, total, filename: calls.append((completed, total, filename))
    )

    assert calls == [(1, 3, "one.png"), (2, 3, "two.png"), (3, 3, "three.png")]


def test_extract_names_from_images_progress_called_even_on_error(monkeypatch):
    monkeypatch.setattr(extraction, "generate", lambda request: _fake_result("nope"))
    files = [(_png_bytes(), "bad.png")]

    calls = []
    _, errors = extraction.extract_names_from_images(
        files, on_progress=lambda completed, total, filename: calls.append((completed, total, filename))
    )

    assert calls == [(1, 1, "bad.png")]
    assert len(errors) == 1
