"""Cycle 9a-4 tests — ExtractionProtocol, SourceRef, ExtractionError."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from trust_generator.v3.extraction.protocol import (
    ExtractionError,
    ExtractionProtocol,
    SourceRef,
)
from trust_generator.v3.extraction.trace import (
    ExtractionResult,
    ExtractionTrace,
)
from trust_generator.v3.schema import TrustData

# --- ExtractionError ---------------------------------------------------------


def test_extraction_error_is_exception_subclass() -> None:
    """ExtractionError is an Exception subclass."""
    assert issubclass(ExtractionError, Exception)


def test_extraction_error_raises_and_catches() -> None:
    """ExtractionError can be raised and caught as itself."""
    with pytest.raises(ExtractionError, match="boom"):
        raise ExtractionError("boom")


def test_extraction_error_caught_as_exception() -> None:
    """ExtractionError is caught by a plain ``except Exception``."""
    try:
        raise ExtractionError("boom")
    except Exception as exc:  # noqa: BLE001 — test-only: asserting Exception supertype
        assert isinstance(exc, ExtractionError)


# --- SourceRef ---------------------------------------------------------------


def test_source_ref_resolves_to_path_at_typecheck_time() -> None:
    """SourceRef is a PEP 695 type alias for Path.

    The PEP 695 ``type`` statement creates a ``TypeAliasType`` whose
    ``__value__`` is the aliased type. We assert ``SourceRef.__value__
    is Path`` rather than comparing the alias itself to ``Path`` (the
    alias is not Path at runtime — it's a TypeAliasType wrapper).
    """
    assert SourceRef.__value__ is Path


def test_source_ref_runtime_isinstance_uses_path() -> None:
    """isinstance checks must use Path (not SourceRef) per python_stack_commitments."""
    p = Path("/tmp/example.png")
    # The supported runtime check:
    assert isinstance(p, Path)
    # The unsupported runtime check (PEP 695 alias is not a class) — pinning
    # the documented limitation so a future contributor sees the test that
    # fails when they assume otherwise.
    with pytest.raises(TypeError):
        isinstance(p, SourceRef)  # type: ignore[arg-type]


# --- ExtractionProtocol ------------------------------------------------------


class _StubBackend:
    """Minimal class structurally satisfying ExtractionProtocol."""

    def extract(self, source: SourceRef) -> ExtractionResult:
        return ExtractionResult(
            data=TrustData(),
            trace=ExtractionTrace(
                fields=[],
                backend_id="stub:stub-model",
                extracted_at=datetime(2026, 4, 28, tzinfo=UTC),
            ),
        )


def test_extraction_protocol_structural_conformance() -> None:
    """A class implementing ``extract(source) -> ExtractionResult`` satisfies the Protocol.

    Conformance is enforced by mypy via the typed assignment below — at
    runtime this is a no-op (Protocol is not @runtime_checkable per
    spec §5.4). The static type-check role is sufficient for v3.0.
    """
    backend: ExtractionProtocol = _StubBackend()
    result = backend.extract(Path("ignored.png"))
    assert isinstance(result, ExtractionResult)


def test_extraction_protocol_not_runtime_checkable() -> None:
    """ExtractionProtocol is NOT @runtime_checkable.

    Pinned because the spec §5.4 explicitly defers runtime-checkable to
    a later session if a use case surfaces. A future contributor adding
    the decorator should see this test fail and re-read the spec
    rationale before doing so.
    """
    with pytest.raises(TypeError):
        isinstance(_StubBackend(), ExtractionProtocol)
