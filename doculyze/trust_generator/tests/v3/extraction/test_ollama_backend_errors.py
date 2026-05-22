"""Cycle 9b-4 tests — OllamaBackend.extract error paths."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import httpx
import ollama
import pytest


def _make_failing_client(error: Exception) -> MagicMock:
    """Construct a MagicMock-shaped ollama.Client whose chat() raises ``error``."""
    client = MagicMock()
    client.chat.side_effect = error
    return client


def _make_envelope_returning_client(envelope_json: str) -> MagicMock:
    """Construct a MagicMock-shaped ollama.Client whose chat() returns
    a response object with .message.content equal to envelope_json."""
    response = MagicMock()
    response.message.content = envelope_json
    client = MagicMock()
    client.chat.return_value = response
    return client


def test_response_error_is_wrapped_as_extraction_error() -> None:
    """``ollama.ResponseError`` from chat() raises ExtractionError, chained."""
    from trust_generator.v3.extraction import ExtractionError, OllamaBackend

    err = ollama.ResponseError("model not found", status_code=404)
    backend = OllamaBackend(model="qwen2.5vl:7b", client=_make_failing_client(err))

    with pytest.raises(ExtractionError) as exc_info:
        backend.extract(Path("fake.png"))

    assert exc_info.value.__cause__ is err


def test_response_error_message_includes_status_code() -> None:
    """The ExtractionError message references the upstream status_code."""
    from trust_generator.v3.extraction import ExtractionError, OllamaBackend

    err = ollama.ResponseError("model not found", status_code=404)
    backend = OllamaBackend(model="qwen2.5vl:7b", client=_make_failing_client(err))

    with pytest.raises(ExtractionError, match="404"):
        backend.extract(Path("fake.png"))


def test_connection_error_is_wrapped_as_extraction_error() -> None:
    """Python builtin ``ConnectionError`` from chat() raises ExtractionError, chained.

    This is the production failure mode when the Ollama server is unreachable:
    ``ollama-python`` catches ``httpx.ConnectError`` internally and re-raises
    ``ConnectionError`` with ``from None`` (verified against
    ollama/_client.py lines 134-135). Catching ``httpx.HTTPError`` alone
    would leak this error class unwrapped.
    """
    from trust_generator.v3.extraction import ExtractionError, OllamaBackend

    err = ConnectionError("Failed to connect to Ollama")
    backend = OllamaBackend(model="qwen2.5vl:7b", client=_make_failing_client(err))

    with pytest.raises(ExtractionError) as exc_info:
        backend.extract(Path("fake.png"))

    assert exc_info.value.__cause__ is err


def test_residual_httpx_error_is_wrapped_as_extraction_error() -> None:
    """Residual ``httpx.HTTPError`` (timeouts, protocol errors) raises ExtractionError, chained.

    These are httpx errors NOT wrapped by ollama-python — timeouts,
    read/write errors, protocol errors. The library only converts
    ``httpx.HTTPStatusError`` (→ ``ResponseError``) and
    ``httpx.ConnectError`` (→ ``ConnectionError``); everything else
    passes through and our error contract must still wrap.
    """
    from trust_generator.v3.extraction import ExtractionError, OllamaBackend

    err = httpx.ReadTimeout("read timeout")
    backend = OllamaBackend(model="qwen2.5vl:7b", client=_make_failing_client(err))

    with pytest.raises(ExtractionError) as exc_info:
        backend.extract(Path("fake.png"))

    assert exc_info.value.__cause__ is err


def test_missing_image_path_is_wrapped_as_extraction_error() -> None:
    """A non-existent image path surfaces as ExtractionError, chained.

    Production failure mode: ``ollama-python``'s ``Image.serialize_model``
    raises ``ValueError`` when a path-typed image value points to a
    non-existent file with a recognized image extension (verified against
    ollama/_types.py lines 178-179: ``raise ValueError(f'File {value}
    does not exist')``). Without our wrapping, this leaks as ValueError
    from extract() — confusing for paralegals who expect ExtractionError
    for any extract() failure.
    """
    from trust_generator.v3.extraction import ExtractionError, OllamaBackend

    err = ValueError("File /tmp/nonexistent.png does not exist")
    backend = OllamaBackend(model="qwen2.5vl:7b", client=_make_failing_client(err))

    with pytest.raises(ExtractionError) as exc_info:
        backend.extract(Path("/tmp/nonexistent.png"))

    assert exc_info.value.__cause__ is err


def test_malformed_envelope_json_is_wrapped_as_extraction_error() -> None:
    """An envelope JSON that fails ``model_validate_json`` raises ExtractionError, chained."""
    from pydantic import ValidationError

    from trust_generator.v3.extraction import ExtractionError, OllamaBackend

    # Missing required ``reasoning`` field
    bad_json = '{"grantors": [], "beneficiaries": []}'
    client = _make_envelope_returning_client(bad_json)
    backend = OllamaBackend(model="qwen2.5vl:7b", client=client)

    with pytest.raises(ExtractionError) as exc_info:
        backend.extract(Path("fake.png"))

    assert isinstance(exc_info.value.__cause__, ValidationError)


def test_oversized_reasoning_is_wrapped_as_extraction_error() -> None:
    """An envelope with oversized ``reasoning`` is rejected at validation time.

    Note: This case should not occur with constrained decoding (the
    schema enforces max_length at sample-time). The test pins what
    happens if it does.
    """
    from pydantic import ValidationError

    from trust_generator.v3.extraction import ExtractionError, OllamaBackend

    oversized = "x" * 2001
    bad_json = (
        '{"reasoning": "' + oversized + '",'
        ' "grantors": [], "beneficiaries": []}'
    )
    client = _make_envelope_returning_client(bad_json)
    backend = OllamaBackend(model="qwen2.5vl:7b", client=client)

    with pytest.raises(ExtractionError) as exc_info:
        backend.extract(Path("fake.png"))

    assert isinstance(exc_info.value.__cause__, ValidationError)


def test_non_json_response_is_wrapped_as_extraction_error() -> None:
    """A non-JSON ``message.content`` (e.g., model emits prose) raises ExtractionError, chained."""
    from pydantic import ValidationError

    from trust_generator.v3.extraction import ExtractionError, OllamaBackend

    bad_content = "I cannot extract from this image."
    client = _make_envelope_returning_client(bad_content)
    backend = OllamaBackend(model="qwen2.5vl:7b", client=client)

    with pytest.raises(ExtractionError) as exc_info:
        backend.extract(Path("fake.png"))

    assert isinstance(exc_info.value.__cause__, ValidationError)
