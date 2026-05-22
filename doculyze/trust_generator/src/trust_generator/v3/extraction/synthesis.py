"""Trace-driven Diagnostic synthesis (spec §5.8, §7.7).

The diagnostics engine has two emission sources after 9c lands:

1. **Rule-driven (existing).** YAML-defined ``DiagnosticRule`` evaluated
   by rule-engine against ``eval_context``. One rule emits zero or one
   Diagnostic per call.
2. **Trace-driven (new).** ``synthesize_extraction_diagnostics(trust,
   extraction)`` walks the trace and emits Diagnostics for each
   unverified, problematic FieldExtraction whose ``field_path``
   resolves against ``trust``. One trace emits zero or many Diagnostics
   per call.

The split is a deliberate architectural seam, not a workaround — see
spec §5.8 for rationale.
"""

from __future__ import annotations

from typing import Final

from trust_generator.v3.extraction.paths import resolve
from trust_generator.v3.extraction.trace import INCOMPLETE, ExtractionTrace
from trust_generator.v3.schema import (
    Diagnostic,
    DiagnosticContext,
    DiagnosticLevel,
    DiagnosticSource,
    TrustData,
)

__all__ = ("LOW_CONFIDENCE_THRESHOLD", "synthesize_extraction_diagnostics")

LOW_CONFIDENCE_THRESHOLD: Final[float] = 0.5
"""Threshold below which ``confidence_self_report`` triggers the
``extraction.low_confidence_field`` Diagnostic. Placeholder until chore
4.3c lands the ConfidenceProtocol; v3.0 backends do not populate
``confidence_self_report`` so this branch is unreachable from
production traces. Promotion to firm-config is a non-breaking change at
the point a backend wires real confidence reports.
"""


def synthesize_extraction_diagnostics(
    trust: TrustData,
    extraction: ExtractionTrace | None,
) -> list[Diagnostic]:
    """Emit one Diagnostic per unverified, problematic FieldExtraction
    whose ``field_path`` resolves against ``trust``.

    Returns ``[]`` when ``extraction is None``. Stale entries
    (``field_path`` does not resolve) are silently skipped — they
    correspond to TrustData edits that already removed the field, so the
    user-visible concern is gone.

    Emission order matches ``extraction.fields`` insertion order
    (parser-emission-order pin, spec §6.7).
    """
    if extraction is None:
        return []
    diagnostics: list[Diagnostic] = []
    for field in extraction.fields:
        if field.verified:
            continue
        resolved, _ = resolve(trust, field.field_path)
        if not resolved:
            continue
        if field.illegible:
            diagnostics.append(
                _make_diag(
                    code="extraction.illegible_field",
                    level=DiagnosticLevel.WARNING,
                    message=f"Field {field.field_path!r} marked illegible by extraction backend",
                    field_path=field.field_path,
                )
            )
            continue
        if (
            field.confidence_self_report is not None
            and field.confidence_self_report < LOW_CONFIDENCE_THRESHOLD
        ):
            diagnostics.append(
                _make_diag(
                    code="extraction.low_confidence_field",
                    level=DiagnosticLevel.INFO,
                    message=(
                        f"Field {field.field_path!r} extracted with low "
                        f"confidence ({field.confidence_self_report:.2f})"
                    ),
                    field_path=field.field_path,
                )
            )
            continue
        if field.normalized_value is None or field.normalized_value is INCOMPLETE:
            diagnostics.append(
                _make_diag(
                    code="extraction.no_normalized_value",
                    level=DiagnosticLevel.WARNING,
                    message=f"Field {field.field_path!r} extracted but not normalized",
                    field_path=field.field_path,
                )
            )
    return diagnostics


def _make_diag(
    *,
    code: str,
    level: DiagnosticLevel,
    message: str,
    field_path: str,
) -> Diagnostic:
    return Diagnostic(
        level=level,
        code=code,
        message=message,
        field_path=field_path,
        source=DiagnosticSource.EXTRACTION,
        context=DiagnosticContext.BOTH,
    )
