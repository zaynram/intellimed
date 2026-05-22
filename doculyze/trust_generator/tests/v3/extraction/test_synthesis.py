"""Cycle 9c-1: trace-driven Diagnostic synthesis."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from trust_generator.v3.extraction.synthesis import (
    LOW_CONFIDENCE_THRESHOLD,
    synthesize_extraction_diagnostics,
)
from trust_generator.v3.extraction.trace import (
    INCOMPLETE,
    ExtractionTrace,
    FieldExtraction,
)
from trust_generator.v3.schema import (
    Child,
    Diagnostic,
    DiagnosticContext,
    DiagnosticLevel,
    DiagnosticSource,
    GrantorInfo,
    OfficeInfo,
    TrustData,
    TrustIdentity,
)


@pytest.fixture
def trust():
    """A populated TrustData with at least one grantor and one child so
    realistic field_paths resolve."""
    return TrustData(
        grantor=GrantorInfo(full_legal_name="Test Grantor"),
        trust_id=TrustIdentity(desired_trust_name="Test Family Trust"),
        office=OfficeInfo(),
        children=[
            Child(full_legal_name="Mary Margaret Thompson"),
        ],
    )


def _trace(*fields: FieldExtraction) -> ExtractionTrace:
    return ExtractionTrace(
        fields=list(fields),
        backend_id="ollama:test-model",
        extracted_at=datetime.now(UTC),
    )


def test_none_extraction_returns_empty_list(trust):
    """`extraction is None` → no Diagnostics."""
    assert synthesize_extraction_diagnostics(trust, None) == []


def test_empty_trace_returns_empty_list(trust):
    """A trace with zero fields → no Diagnostics."""
    assert synthesize_extraction_diagnostics(trust, _trace()) == []


def test_verified_illegible_field_is_suppressed(trust):
    """A verified illegible field never emits a Diagnostic."""
    trace = _trace(
        FieldExtraction(
            field_path="grantor.full_legal_name",
            raw_value="(scribble)",
            illegible=True,
            verified=True,
            verified_at=datetime.now(UTC),
        ),
    )
    assert synthesize_extraction_diagnostics(trust, trace) == []


def test_unverified_illegible_resolved_path_emits_diagnostic(trust):
    """An unverified illegible field whose path resolves emits one
    extraction.illegible_field Diagnostic."""
    trace = _trace(
        FieldExtraction(
            field_path="grantor.full_legal_name",
            raw_value="(scribble)",
            illegible=True,
        ),
    )
    diags = synthesize_extraction_diagnostics(trust, trace)
    assert len(diags) == 1
    diag = diags[0]
    assert isinstance(diag, Diagnostic)
    assert diag.code == "extraction.illegible_field"
    assert diag.level == DiagnosticLevel.WARNING
    assert diag.source == DiagnosticSource.EXTRACTION
    assert diag.context == DiagnosticContext.BOTH
    assert diag.field_path == "grantor.full_legal_name"


def test_stale_path_is_silently_filtered(trust):
    """A trace entry whose field_path no longer resolves emits no
    Diagnostic (post-edit cleanup behavior)."""
    trace = _trace(
        FieldExtraction(
            field_path="children[99].full_legal_name",  # out of range
            raw_value="Jane Q. Public",
            illegible=True,
        ),
    )
    assert synthesize_extraction_diagnostics(trust, trace) == []


def test_low_confidence_branch_emits_when_below_threshold(trust):
    """A hand-constructed FieldExtraction with confidence_self_report
    below LOW_CONFIDENCE_THRESHOLD emits an info-level Diagnostic.
    Branch is structurally live for the future ConfidenceProtocol
    (chore 4.3c); v3.0 backends do not populate confidence_self_report
    so this branch is unreachable from production traces."""
    assert LOW_CONFIDENCE_THRESHOLD == pytest.approx(0.5)
    trace = _trace(
        FieldExtraction(
            field_path="grantor.full_legal_name",
            raw_value="James William Thompson Jr.",
            normalized_value="James William Thompson Jr.",
            confidence_self_report=0.3,
        ),
    )
    diags = synthesize_extraction_diagnostics(trust, trace)
    assert len(diags) == 1
    assert diags[0].code == "extraction.low_confidence_field"
    assert diags[0].level == DiagnosticLevel.INFO


def test_low_confidence_branch_silent_when_none(trust):
    """v3.0 production case: confidence_self_report is None → no emission
    from the low-confidence branch."""
    trace = _trace(
        FieldExtraction(
            field_path="grantor.full_legal_name",
            raw_value="James William Thompson Jr.",
            normalized_value="James William Thompson Jr.",
            confidence_self_report=None,
        ),
    )
    assert synthesize_extraction_diagnostics(trust, trace) == []


def test_no_normalized_value_emits_when_normalized_is_none(trust):
    """Field is not illegible, normalized_value is None, not verified
    → extraction.no_normalized_value warning."""
    trace = _trace(
        FieldExtraction(
            field_path="grantor.full_legal_name",
            raw_value="James William Thompson Jr.",
            normalized_value=None,
        ),
    )
    diags = synthesize_extraction_diagnostics(trust, trace)
    assert len(diags) == 1
    assert diags[0].code == "extraction.no_normalized_value"
    assert diags[0].level == DiagnosticLevel.WARNING


def test_no_normalized_value_emits_when_normalized_is_INCOMPLETE(trust):
    """The INCOMPLETE sentinel triggers no_normalized_value (identity
    comparison, not equality)."""
    trace = _trace(
        FieldExtraction(
            field_path="grantor.full_legal_name",
            raw_value="James William Thompson Jr.",
            normalized_value=INCOMPLETE,
        ),
    )
    diags = synthesize_extraction_diagnostics(trust, trace)
    assert len(diags) == 1
    assert diags[0].code == "extraction.no_normalized_value"


def test_emission_order_matches_trace_fields_insertion_order(trust):
    """Multiple problematic unverified fields emit in trace.fields order."""
    trace = _trace(
        FieldExtraction(
            field_path="grantor.full_legal_name",
            raw_value="(scribble 1)",
            illegible=True,
        ),
        FieldExtraction(
            field_path="children[0].full_legal_name",
            raw_value="(scribble 2)",
            illegible=True,
        ),
    )
    diags = synthesize_extraction_diagnostics(trust, trace)
    assert [d.field_path for d in diags] == [
        "grantor.full_legal_name",
        "children[0].full_legal_name",
    ]


def test_diagnostic_field_path_matches_field_extraction_field_path(trust):
    """Synthesized Diagnostic.field_path is exactly FieldExtraction.field_path
    (single shared convention; no mangling)."""
    trace = _trace(
        FieldExtraction(
            field_path="children[0].full_legal_name",
            raw_value="Mary Margaret Thompson",
            illegible=True,
        ),
    )
    diags = synthesize_extraction_diagnostics(trust, trace)
    assert diags[0].field_path == "children[0].full_legal_name"
