"""Cycle 6 — override flow: force_generation + validate_override_reason."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from trust_generator.v3.diagnostics.audit import (
    AuditRecord,
    force_generation,
    validate_override_reason,
)
from trust_generator.v3.schema import (
    Diagnostic,
    DiagnosticLevel,
    DiagnosticSource,
)


def _diag(code: str) -> Diagnostic:
    return Diagnostic(
        level=DiagnosticLevel.ERROR,
        code=code,
        message=f"{code} fired",
        source=DiagnosticSource.SCHEMA,
    )


def test_happy_path_writes_record(firm_config_factory, trust_data_factory, tmp_audit_dir: Path):
    config = firm_config_factory()
    trust = trust_data_factory(file_number="F-2026-0042")
    diagnostics = [_diag("shares.sum_not_100")]

    record = force_generation(
        trust, config, diagnostics, reason="Confirmed by attorney 2026-04-22."
    )

    assert isinstance(record, AuditRecord)
    assert record.user == "testuser"
    assert record.trust_ref == "F-2026-0042"
    assert record.overridden_codes == ["shares.sum_not_100"]
    assert record.restriction_level == "error"

    files = list(tmp_audit_dir.glob("*.jsonl"))
    assert len(files) == 1
    parsed = json.loads(files[0].read_text(encoding="utf-8").splitlines()[0])
    assert parsed["overridden_codes"] == ["shares.sum_not_100"]


def test_empty_reason_rejected(firm_config_factory, trust_data_factory):
    config = firm_config_factory()
    trust = trust_data_factory()
    with pytest.raises(ValueError, match="10 non-whitespace"):
        force_generation(trust, config, [_diag("x.y")], reason="")


def test_short_reason_rejected(firm_config_factory, trust_data_factory):
    config = firm_config_factory()
    trust = trust_data_factory()
    with pytest.raises(ValueError, match="10 non-whitespace"):
        force_generation(trust, config, [_diag("x.y")], reason="ok")


def test_validate_override_reason_module_helper():
    """The standalone helper is exposed for GUI live-validation per spec §5.6."""
    with pytest.raises(ValueError):
        validate_override_reason("short")
    validate_override_reason("this is long enough to pass")  # no raise


def test_trust_ref_fallback(firm_config_factory, trust_data_factory):
    """Empty file_number yields trust_ref='unidentified'."""
    config = firm_config_factory()
    trust = trust_data_factory(file_number="")
    record = force_generation(
        trust, config, [_diag("x.y")], reason="ten or more characters here"
    )
    assert record.trust_ref == "unidentified"


def test_trust_ref_whitespace_only_coerced_to_unidentified(
    firm_config_factory, trust_data_factory
):
    """Whitespace-only file_number is truthy in Python; explicit strip required."""
    config = firm_config_factory()
    trust = trust_data_factory(file_number="   ")
    record = force_generation(
        trust, config, [_diag("x.y")], reason="ten or more characters here"
    )
    assert record.trust_ref == "unidentified"


def test_trust_ref_preserves_real_file_number(
    firm_config_factory, trust_data_factory
):
    """Regression guard: the strip-coerce change must not perturb normal values."""
    config = firm_config_factory()
    trust = trust_data_factory(file_number="F-2026-0099")
    record = force_generation(
        trust, config, [_diag("x.y")], reason="ten or more characters here"
    )
    assert record.trust_ref == "F-2026-0099"


def test_validate_override_reason_error_includes_received_length():
    """Caller diagnostics: error message surfaces the stripped length received."""
    reason = "  short  "  # 5 stripped chars
    with pytest.raises(ValueError, match=r"received 5"):
        validate_override_reason(reason)


def test_validate_override_reason_error_includes_zero_length():
    """Pure-whitespace input reports zero stripped chars in the error."""
    with pytest.raises(ValueError, match=r"received 0"):
        validate_override_reason("        ")


def test_codes_preserved_in_order(firm_config_factory, trust_data_factory):
    config = firm_config_factory()
    trust = trust_data_factory()
    diagnostics = [_diag("a.b"), _diag("c.d"), _diag("e.f")]
    record = force_generation(
        trust, config, diagnostics, reason="ten or more characters here"
    )
    assert record.overridden_codes == ["a.b", "c.d", "e.f"]


def test_no_mutation(firm_config_factory, trust_data_factory):
    config = firm_config_factory()
    trust = trust_data_factory(file_number="F-X")
    diagnostics = [_diag("a.b")]

    trust_before = trust.model_copy(deep=True)
    config_before = config.model_copy(deep=True)
    diagnostics_before = list(diagnostics)

    force_generation(
        trust, config, diagnostics, reason="ten or more characters here"
    )

    assert trust == trust_before
    assert config == config_before
    assert diagnostics == diagnostics_before


# ---------------------------------------------------------------------------
# Task 9c-3: extraction-source diagnostics flow through force_generation
# ---------------------------------------------------------------------------

from datetime import UTC
from datetime import datetime as _dt
from pathlib import Path as _Path

from trust_generator.v3.diagnostics.engine import diagnose
from trust_generator.v3.extraction.trace import ExtractionTrace, FieldExtraction
from trust_generator.v3.schema import (
    DiagnosticContext,
)


def _extraction_diag() -> Diagnostic:
    """A Diagnostic shaped like one synthesized by 9c-1 from an
    illegible FieldExtraction."""
    return Diagnostic(
        level=DiagnosticLevel.WARNING,
        code="extraction.illegible_field",
        message="Field 'grantor.full_legal_name' marked illegible",
        field_path="grantor.full_legal_name",
        source=DiagnosticSource.EXTRACTION,
        context=DiagnosticContext.BOTH,
    )


def test_force_generation_accepts_extraction_source_diagnostic(
    firm_config_factory, trust_data_factory, tmp_audit_dir: _Path
):
    """force_generation writes an audit record listing the
    extraction-source diagnostic's code; pins that the override flow
    treats extraction-source codes identically to schema/business_rule
    codes."""
    trust = trust_data_factory()
    config = firm_config_factory()
    diag = _extraction_diag()
    record = force_generation(
        trust, config, [diag], reason="paralegal confirmed illegible field at intake review"
    )
    assert record.overridden_codes == ["extraction.illegible_field"]
    audit_files = list(tmp_audit_dir.glob("audit-*.jsonl"))
    assert len(audit_files) == 1
    line = audit_files[0].read_text(encoding="utf-8").splitlines()[0]
    assert "extraction.illegible_field" in line


def test_verified_field_never_reaches_force_generation(
    firm_config_factory, trust_data_factory, tmp_audit_dir: _Path
):
    """A verified extraction field is filtered by synthesis (cycle
    9c-1) before diagnose() returns; force_generation never sees it.
    Pins the merge-step filter."""
    trust = trust_data_factory()
    config = firm_config_factory()
    trace = ExtractionTrace(
        fields=[
            FieldExtraction(
                field_path="grantor.full_legal_name",
                raw_value="(scribble)",
                illegible=True,
            ),
        ],
        backend_id="ollama:test-model",
        extracted_at=_dt.now(UTC),
    )
    trace.verify_field("grantor.full_legal_name")

    diags = diagnose(trust, config, extraction=trace)
    extraction_diags = [d for d in diags if d.source == DiagnosticSource.EXTRACTION]
    assert extraction_diags == []

    # If a caller still tries to override an extraction diagnostic that
    # was never returned, force_generation is signature-tolerant — but
    # the merge step ensures verified fields don't surface to the user
    # in the first place. Pin both halves.
    record = force_generation(
        trust,
        config,
        diags,
        reason="overriding remaining diagnostics after paralegal verification",
    )
    assert "extraction.illegible_field" not in record.overridden_codes
