"""Cycle 9a-2 tests — FieldExtraction, ExtractionTrace, ExtractionResult."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from trust_generator.v3.extraction.trace import (
    INCOMPLETE,
    ExtractionResult,
    ExtractionTrace,
    FieldExtraction,
)
from trust_generator.v3.schema import TrustData

# --- FieldExtraction shape ---------------------------------------------------


def test_field_extraction_accepts_documented_fields(
    field_extraction_factory: Callable[..., FieldExtraction],
) -> None:
    """FieldExtraction accepts the documented field set with sensible defaults."""
    fe = field_extraction_factory()
    assert fe.field_path == "grantor.full_legal_name"
    assert fe.raw_value == "Test Value"
    assert fe.normalized_value is None
    assert fe.illegible is False
    assert fe.confidence_self_report is None
    assert fe.verified is False
    assert fe.verified_at is None


def test_field_extraction_rejects_unknown_fields() -> None:
    """``extra='forbid'`` rejects unexpected fields at construction."""
    with pytest.raises(ValidationError):
        FieldExtraction(
            field_path="grantor.full_legal_name",
            raw_value="x",
            unknown_field="boom",  # type: ignore[call-arg]
        )


def test_field_extraction_illegible_with_value_rejected() -> None:
    """Mutual-exclusion invariant: illegible=True + non-None normalized_value rejected."""
    with pytest.raises(ValidationError) as exc_info:
        FieldExtraction(
            field_path="grantor.full_legal_name",
            raw_value="x",
            illegible=True,
            normalized_value="some-value",
        )
    msg = str(exc_info.value)
    assert "illegible" in msg.lower()


def test_field_extraction_illegible_with_none_value_accepted() -> None:
    """Mutual-exclusion invariant: illegible=True + normalized_value=None is fine."""
    fe = FieldExtraction(
        field_path="grantor.full_legal_name",
        raw_value="?",
        illegible=True,
        normalized_value=None,
    )
    assert fe.illegible is True
    assert fe.normalized_value is None


def test_field_extraction_incomplete_sentinel_identity_preserved() -> None:
    """FieldExtraction accepts INCOMPLETE; identity survives in-memory round-trip."""
    fe = FieldExtraction(
        field_path="grantor.full_legal_name",
        raw_value="John Doe",
        normalized_value=INCOMPLETE,
    )
    assert fe.normalized_value is INCOMPLETE


# --- ExtractionTrace.verify_field -------------------------------------------


def test_verify_field_happy_path(
    field_extraction_factory: Callable[..., FieldExtraction],
    extraction_trace_factory: Callable[..., ExtractionTrace],
) -> None:
    """verify_field mutates only the matching FieldExtraction's verified+verified_at."""
    fe_a = field_extraction_factory(field_path="grantor.full_legal_name", raw_value="A")
    fe_b = field_extraction_factory(field_path="trust_id.desired_trust_name", raw_value="B")
    trace = extraction_trace_factory(fields=[fe_a, fe_b])

    at = datetime(2026, 4, 28, 12, 0, 0, tzinfo=UTC)
    trace.verify_field("grantor.full_legal_name", at=at)

    assert trace.fields[0].verified is True
    assert trace.fields[0].verified_at == at
    assert trace.fields[1].verified is False
    assert trace.fields[1].verified_at is None


def test_verify_field_default_at_uses_now(
    field_extraction_factory: Callable[..., FieldExtraction],
    extraction_trace_factory: Callable[..., ExtractionTrace],
) -> None:
    """verify_field's default ``at`` is datetime.now(UTC)."""
    fe = field_extraction_factory(field_path="grantor.full_legal_name", raw_value="A")
    trace = extraction_trace_factory(fields=[fe])

    before = datetime.now(UTC)
    trace.verify_field("grantor.full_legal_name")
    after = datetime.now(UTC)

    assert trace.fields[0].verified is True
    assert trace.fields[0].verified_at is not None
    assert before <= trace.fields[0].verified_at <= after


def test_verify_field_missing_path_raises_keyerror(
    extraction_trace_factory: Callable[..., ExtractionTrace],
) -> None:
    """verify_field raises KeyError for an unknown field_path."""
    trace = extraction_trace_factory(fields=[])
    with pytest.raises(KeyError):
        trace.verify_field("does.not.exist")


def test_verify_field_duplicate_path_raises_valueerror(
    field_extraction_factory: Callable[..., FieldExtraction],
    extraction_trace_factory: Callable[..., ExtractionTrace],
) -> None:
    """Construction with duplicate field_path entries is rejected (data-integrity invariant)."""
    fe_dup_1 = field_extraction_factory(field_path="grantor.full_legal_name", raw_value="A")
    fe_dup_2 = field_extraction_factory(field_path="grantor.full_legal_name", raw_value="B")
    with pytest.raises(ValidationError, match="duplicate"):
        extraction_trace_factory(fields=[fe_dup_1, fe_dup_2])


def test_extraction_trace_rejects_duplicate_field_paths_at_construction() -> None:
    """ExtractionTrace construction raises ValidationError on duplicate field_path values.

    The field_path-uniqueness invariant must be enforced at construction time, not
    only inside verify_field. Direct construction with duplicate entries bypasses
    method-level checks.
    """
    fe_dup_1 = FieldExtraction(field_path="grantor.full_legal_name", raw_value="A")
    fe_dup_2 = FieldExtraction(field_path="grantor.full_legal_name", raw_value="B")
    with pytest.raises(ValidationError, match="duplicate"):
        ExtractionTrace(
            fields=[fe_dup_1, fe_dup_2],
            backend_id="test:test-model",
            extracted_at=datetime(2026, 4, 28, tzinfo=UTC),
        )


# --- ExtractionResult --------------------------------------------------------


def test_extraction_result_requires_data_and_trace(
    extraction_trace_factory: Callable[..., ExtractionTrace],
) -> None:
    """ExtractionResult requires both ``data`` and ``trace``."""
    with pytest.raises(ValidationError):
        ExtractionResult(data=TrustData())  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        ExtractionResult(trace=extraction_trace_factory())  # type: ignore[call-arg]


def test_extraction_result_accepts_data_and_trace(
    extraction_trace_factory: Callable[..., ExtractionTrace],
) -> None:
    """ExtractionResult round-trips a TrustData and a trace."""
    data = TrustData()
    trace = extraction_trace_factory()
    result = ExtractionResult(data=data, trace=trace)
    assert result.data is data
    assert result.trace is trace
