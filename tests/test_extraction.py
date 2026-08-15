import io
import json
from types import SimpleNamespace

import pytest
from PIL import Image

from core import extraction


def _fake_response(content: str):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def _png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), color="white").save(buffer, format="PNG")
    return buffer.getvalue()


def test_encode_image_valid():
    data_url = extraction.encode_image(_png_bytes())
    assert data_url.startswith("data:image/jpeg;base64,")


def test_encode_image_invalid_bytes_raises():
    with pytest.raises(extraction.ImageDecodeError):
        extraction.encode_image(b"not an image")


def test_extract_names_from_image_success(monkeypatch):
    monkeypatch.setattr(
        extraction,
        "safe_chat_completion",
        lambda **kwargs: _fake_response(json.dumps({"names": ["John Doe", "Jane Smith"]})),
    )
    names, error = extraction.extract_names_from_image(_png_bytes(), "shot.png")
    assert names == ["John Doe", "Jane Smith"]
    assert error is None


def test_extract_names_from_image_bad_json(monkeypatch):
    monkeypatch.setattr(extraction, "safe_chat_completion", lambda **kwargs: _fake_response("nope"))
    names, error = extraction.extract_names_from_image(_png_bytes(), "shot.png")
    assert names == []
    assert error is not None and "shot.png" in error


def test_extract_names_from_image_bad_file():
    names, error = extraction.extract_names_from_image(b"garbage", "bad.png")
    assert names == []
    assert error is not None and "bad.png" in error


def test_extract_names_from_images_aggregates(monkeypatch):
    monkeypatch.setattr(
        extraction,
        "safe_chat_completion",
        lambda **kwargs: _fake_response(json.dumps({"names": ["A", "B"]})),
    )
    files = [(_png_bytes(), "one.png"), (_png_bytes(), "two.png")]
    all_names, errors = extraction.extract_names_from_images(files)
    assert all_names == ["A", "B", "A", "B"]
    assert errors == []
