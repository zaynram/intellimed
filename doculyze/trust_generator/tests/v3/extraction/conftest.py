"""Shared fixtures for OCR extraction cycle tests.

Reused by 9a-2 (trace), 9a-4 (protocol), and 9c (synthesis).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest

from trust_generator.v3.extraction.trace import (
    ExtractionTrace,
    FieldExtraction,
)


@pytest.fixture
def field_extraction_factory() -> Callable[..., FieldExtraction]:
    """Build a minimal FieldExtraction; kwargs override per-test."""

    def _build(**overrides: Any) -> FieldExtraction:
        defaults: dict[str, Any] = {
            "field_path": "grantor.full_legal_name",
            "raw_value": "Test Value",
            "normalized_value": None,
            "illegible": False,
            "confidence_self_report": None,
            "verified": False,
            "verified_at": None,
        }
        defaults.update(overrides)
        return FieldExtraction(**defaults)

    return _build


@pytest.fixture
def extraction_trace_factory(
    field_extraction_factory: Callable[..., FieldExtraction],
) -> Callable[..., ExtractionTrace]:
    """Build a minimal ExtractionTrace; kwargs override per-test."""

    def _build(**overrides: Any) -> ExtractionTrace:
        defaults: dict[str, Any] = {
            "fields": [],
            "backend_id": "test:test-model",
            "extracted_at": datetime(2026, 4, 28, tzinfo=UTC),
        }
        defaults.update(overrides)
        return ExtractionTrace(**defaults)

    return _build
