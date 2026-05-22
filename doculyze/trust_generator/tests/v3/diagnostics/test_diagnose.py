"""Cycle 1 — outer integration test for diagnose().

Asserts that a TrustData crafted to trigger all three starter rules
(shares.sum_not_100, estate.crossed_cliff, extraction.placeholder_unfilled)
yields exactly those three diagnostic codes through the diagnose() coordinator.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from trust_generator.v3.schema import BeneficiaryShare, TrustType


def test_diagnose_triggers_all_starter_rules(
    firm_config_factory, trust_data_factory
):
    """A TrustData crafted to trigger all three starter rules yields three diagnostics."""
    from trust_generator.v3.diagnostics import diagnose

    config = firm_config_factory()
    trust = trust_data_factory(
        beneficiary_shares=[
            BeneficiaryShare(recipient_ref="a", share_percent=Decimal(33)),
            BeneficiaryShare(recipient_ref="b", share_percent=Decimal(33)),
            BeneficiaryShare(recipient_ref="c", share_percent=Decimal(33)),
        ],
        estate_value_approximate=Decimal(5000000),
        trust_type=TrustType.INDIVIDUAL,
        statement_of_intent="[OCR_LOW_CONFIDENCE]",
    )

    result = diagnose(trust, config, ref_date=date(2026, 4, 23))

    codes = {d.code for d in result}
    assert codes == {
        "shares.sum_not_100",
        "estate.crossed_cliff",
        "extraction.placeholder_unfilled",
    }


# ---------------------------------------------------------------------------
# Cycle 9c-2: extraction integration
# ---------------------------------------------------------------------------

from datetime import UTC
from datetime import datetime as _dt
from pathlib import Path
from textwrap import dedent

from trust_generator.v3.diagnostics.engine import diagnose
from trust_generator.v3.extraction.trace import ExtractionTrace, FieldExtraction
from trust_generator.v3.schema import DiagnosticSource


def _illegible_trace_for(field_path: str) -> ExtractionTrace:
    return ExtractionTrace(
        fields=[
            FieldExtraction(
                field_path=field_path,
                raw_value="(scribble)",
                illegible=True,
            ),
        ],
        backend_id="ollama:test-model",
        extracted_at=_dt.now(UTC),
    )


def test_diagnose_without_extraction_is_regression_equivalent(
    firm_config_factory, trust_data_factory
):
    """diagnose() called without the new extraction kwarg behaves
    identically to the pre-9c implementation. Regression pin."""
    trust = trust_data_factory()
    config = firm_config_factory()
    diags = diagnose(trust, config)
    # No extraction-source diagnostics should appear when extraction is omitted.
    assert all(d.source != DiagnosticSource.EXTRACTION for d in diags)


def test_diagnose_merges_trace_driven_first_then_rule_driven(
    firm_config_factory, trust_data_factory
):
    """Trace-driven Diagnostics emit before rule-driven Diagnostics in the
    returned list (spec §5.8 merge-order pin)."""
    trust = trust_data_factory()
    config = firm_config_factory()
    trace = _illegible_trace_for("grantor.full_legal_name")
    diags = diagnose(trust, config, extraction=trace)
    extraction_indices = [
        i for i, d in enumerate(diags) if d.source == DiagnosticSource.EXTRACTION
    ]
    non_extraction_indices = [
        i for i, d in enumerate(diags) if d.source != DiagnosticSource.EXTRACTION
    ]
    assert extraction_indices, "expected at least one extraction-source diagnostic"
    if non_extraction_indices:
        # If any rule-driven diagnostics exist, every extraction diagnostic
        # must precede every rule-driven diagnostic.
        assert max(extraction_indices) < min(non_extraction_indices)


def test_diagnose_lifecycle_emit_verify_no_re_emit(
    firm_config_factory, trust_data_factory
):
    """End-to-end: emit illegible_field, verify the field, re-call
    diagnose(), assert the matching diagnostic is gone (spec §6.7
    lifecycle pin)."""
    trust = trust_data_factory()
    config = firm_config_factory()
    trace = _illegible_trace_for("grantor.full_legal_name")

    first = diagnose(trust, config, extraction=trace)
    assert any(
        d.code == "extraction.illegible_field"
        and d.field_path == "grantor.full_legal_name"
        for d in first
    )

    trace.verify_field("grantor.full_legal_name")

    second = diagnose(trust, config, extraction=trace)
    assert not any(
        d.code == "extraction.illegible_field"
        and d.field_path == "grantor.full_legal_name"
        for d in second
    )


def test_yaml_rule_with_guard_reads_extraction_namespace(
    firm_config_factory, trust_data_factory, tmp_path: Path
):
    """A custom YAML rule guarded with `extraction != null and ...`
    evaluates without `engine.symbol_unknown` when extraction is
    provided."""
    rules_dir = tmp_path / "custom_rules"
    rules_dir.mkdir()
    (rules_dir / "extraction_guarded.yaml").write_text(
        dedent(
            """\
            - code: custom.illegible_count_high
              level: warning
              message: "More than zero illegible fields"
              source: extraction
              context: both
              expression: "extraction != null and extraction.fields.length > 0"
            """
        )
    )
    config = firm_config_factory()
    config.diagnostics.rules_dir = rules_dir
    trust = trust_data_factory()
    trace = _illegible_trace_for("grantor.full_legal_name")

    diags = diagnose(trust, config, extraction=trace)
    codes = [d.code for d in diags]
    assert "custom.illegible_count_high" in codes
    assert not any(d.code == "engine.symbol_unknown" for d in diags)


def test_yaml_rule_without_guard_emits_symbol_unknown_when_no_extraction(
    firm_config_factory, trust_data_factory, tmp_path: Path
):
    """Documented behavior pin: an unguarded `extraction.fields`
    reference in a YAML rule emits `engine.symbol_unknown` when
    extraction is None."""
    rules_dir = tmp_path / "custom_rules_unguarded"
    rules_dir.mkdir()
    (rules_dir / "extraction_unguarded.yaml").write_text(
        dedent(
            """\
            - code: custom.unguarded_extraction_ref
              level: warning
              message: "References extraction.fields without guard"
              source: extraction
              context: both
              expression: "extraction.fields.length > 0"
            """
        )
    )
    config = firm_config_factory()
    config.diagnostics.rules_dir = rules_dir
    trust = trust_data_factory()

    diags = diagnose(trust, config)
    assert any(d.code == "engine.symbol_unknown" for d in diags)
