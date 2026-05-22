"""Backend-agnostic OCR extraction Protocol surface (spec §5.4)."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from trust_generator.v3.extraction.trace import ExtractionResult

type SourceRef = Path
"""v3.0 SourceRef: a filesystem path to a single image or PDF.

Multi-page handling is backend-internal (see spec §7.5). The alias
exists to mark the public name of this concept; if a later session
needs to widen its meaning, the alias is the change site. v3.0 makes
no commitment about future variants.

PEP 695 type aliases are type-checker-visible only; runtime-side
isinstance checks would not see this alias. Per
``python_stack_commitments``, comparisons should not rely on this name
at runtime.
"""


class ExtractionError(Exception):
    """Base for backend-emitted extraction failures.

    Backends raise this (or a subclass) when extraction cannot proceed;
    partial extraction with per-field illegibility flags is the success
    path and does not raise.
    """


class ExtractionProtocol(Protocol):
    """Backend-agnostic OCR extraction surface.

    The Protocol's return type is the only return type. There is no
    bare-TrustData escape hatch: backends that produce TrustData
    without a paired trace would defeat the verification contract that
    ``diagnose()``'s trace-driven synthesis depends on. This is a
    deliberate interface invariant; tests in 9b cycle 5 enforce it on
    ``OllamaBackend`` and any future backend.

    Not ``@runtime_checkable`` at v3.0: the structural type-check role
    is served by the static type checker; runtime isinstance checks
    are not currently needed and the decorator carries an unfunded
    cost (slower checks; signature subtleties). If a runtime use case
    surfaces, add it then.
    """

    def extract(self, source: SourceRef) -> ExtractionResult:
        """Extract a TrustData and ExtractionTrace from one source.

        Failure modes raise ``ExtractionError`` (or subclass).
        Per-field illegibility, missing fields, and low-confidence
        transcriptions are NOT failures: they are returned as
        ``FieldExtraction`` entries on the trace with
        ``illegible=True`` and/or ``normalized_value=None``. A trace
        with zero usable fields is a valid (if unhelpful) result.
        """
        ...


__all__ = (
    "ExtractionError",
    "ExtractionProtocol",
    "SourceRef",
)
