"""Cycle 2 — build_eval_context() shape and semantics."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import freezegun
import rule_engine

from trust_generator.v3.diagnostics.eval_context import build_eval_context
from trust_generator.v3.schema import BeneficiaryShare, Child, TrustType


def test_returned_top_level_keys(firm_config_factory, trust_data_factory):
    config = firm_config_factory()
    trust = trust_data_factory()

    ctx = build_eval_context(trust, config, date(2026, 4, 23))

    assert set(ctx.keys()) == {"trust", "firm", "now"}


def test_trust_namespace_field_passthrough(firm_config_factory, trust_data_factory):
    config = firm_config_factory()
    trust = trust_data_factory()

    ctx = build_eval_context(trust, config, date(2026, 4, 23))

    assert ctx["trust"]["grantor"]["full_legal_name"] == "Test Grantor"


def test_firm_namespace_field_passthrough(firm_config_factory, trust_data_factory):
    config = firm_config_factory()
    trust = trust_data_factory()

    ctx = build_eval_context(trust, config, date(2026, 4, 23))

    assert "estate_thresholds" in ctx["firm"]
    assert "single_hard" in ctx["firm"]["estate_thresholds"]


def test_computed_property_injection(firm_config_factory, trust_data_factory):
    config = firm_config_factory()
    trust = trust_data_factory(
        beneficiary_shares=[
            BeneficiaryShare(recipient_ref="a", share_percent=Decimal(33)),
            BeneficiaryShare(recipient_ref="b", share_percent=Decimal(33)),
            BeneficiaryShare(recipient_ref="c", share_percent=Decimal(33)),
        ],
    )

    ctx = build_eval_context(trust, config, date(2026, 4, 23))

    assert ctx["trust"]["beneficiary_shares_total"] == Decimal(99)


def test_now_resolution_explicit(firm_config_factory, trust_data_factory):
    config = firm_config_factory()
    trust = trust_data_factory()

    ctx = build_eval_context(trust, config, date(2026, 1, 1))

    assert ctx["now"] == date(2026, 1, 1)


@freezegun.freeze_time("2026-04-23")
def test_now_resolution_no_implicit_fallback(firm_config_factory, trust_data_factory):
    """`build_eval_context` requires explicit `ref_date` — it does not fall back
    to `trust.execution_date` or `date.today()`. The fallback chain
    (None → trust.execution_date → date.today()) is `diagnose()`'s responsibility,
    not this function's.

    With freezegun pinning today() to 2026-04-23 and execution_date pinned to
    2026-06-15, an explicit ref_date of 2027-01-01 must win. If the function
    silently fell back to either candidate, the assertion would fail.
    """
    config = firm_config_factory()
    trust = trust_data_factory(execution_date=date(2026, 6, 15))

    ctx = build_eval_context(trust, config, date(2027, 1, 1))

    assert ctx["now"] == date(2027, 1, 1)
    assert ctx["now"] != date(2026, 4, 23)  # would equal today() if function called date.today()
    assert ctx["now"] != date(2026, 6, 15)  # would equal execution_date if function fell back


def test_minor_injection(firm_config_factory):
    """A Child whose DOB makes them 17 at ref_date appears in minor_beneficiaries; an adult does not.

    Schema shape: TrustData.children is list[Child]; Child extends Beneficiary
    extends PersonReference (which carries date_of_birth). minor_beneficiaries(
    ref_date) aggregates over children, descendants, other_beneficiaries —
    populating only the children list is sufficient to exercise injection.
    """
    from trust_generator.v3.schema import (
        GrantorInfo,
        OfficeInfo,
        TrustData,
        TrustIdentity,
    )

    minor_dob = date(2009, 5, 1)  # age 16 on 2026-04-23 (birthday 5/1)
    adult_dob = date(2000, 1, 1)  # age 26 on 2026-04-23

    trust = TrustData(
        grantor=GrantorInfo(full_legal_name="Test Grantor"),
        trust_id=TrustIdentity(desired_trust_name="Test Family Trust"),
        office=OfficeInfo(),
        children=[
            Child(full_legal_name="Minor Child", date_of_birth=minor_dob),
            Child(full_legal_name="Adult Child", date_of_birth=adult_dob),
        ],
    )
    config = firm_config_factory()

    ctx = build_eval_context(trust, config, date(2026, 4, 23))

    minor_names = [b["full_legal_name"] for b in ctx["trust"]["minor_beneficiaries"]]
    assert "Minor Child" in minor_names
    assert "Adult Child" not in minor_names


def test_enum_value_pin(firm_config_factory, trust_data_factory):
    """`build_eval_context` unwraps Enum instances to their `.value`, so rule
    expressions like ``trust.trust_id.trust_type == "individual"`` evaluate
    correctly through rule-engine.

    The str-mixin inheritance on ``TrustType(str, Enum)`` makes Python-level
    equality (``TrustType.INDIVIDUAL == "individual"``) return True, but
    rule-engine bypasses Python's ``__eq__`` and calls ``str()`` on the value —
    which returns the enum repr (``'TrustType.INDIVIDUAL'``), not the value
    string. The unwrap helper inside ``build_eval_context`` normalizes Enum
    instances to their ``.value`` so the rule-engine roundtrip is correct.
    This pin guards against regression where the unwrap helper is removed or
    bypassed (e.g., a future refactor swapping ``model_dump`` modes).
    """
    config = firm_config_factory()
    trust = trust_data_factory(trust_type=TrustType.JOINT)

    ctx = build_eval_context(trust, config, date(2026, 4, 23))

    val = ctx["trust"]["trust_id"]["trust_type"]
    assert isinstance(val, str)  # post-unwrap: a plain str, not a TrustType instance
    assert val == "joint"
    assert val != "individual"

    # rule-engine roundtrip — guards against regression where _unwrap_enums
    # is removed (Python-level equality alone would still pass via str-mixin
    # inheritance, but rule-engine evaluation would silently return False).
    assert rule_engine.Rule(
        'trust.trust_id.trust_type == "joint"'
    ).matches(ctx) is True
    assert rule_engine.Rule(
        'trust.trust_id.trust_type == "individual"'
    ).matches(ctx) is False


# ---------------------------------------------------------------------------
# Cycle 9c-2: extraction namespace
# ---------------------------------------------------------------------------

from datetime import UTC
from datetime import datetime as _dt

from trust_generator.v3.extraction.trace import ExtractionTrace, FieldExtraction


def _make_trace() -> ExtractionTrace:
    return ExtractionTrace(
        fields=[
            FieldExtraction(
                field_path="grantor.full_legal_name",
                raw_value="James William Thompson Jr.",
                illegible=True,
            ),
        ],
        backend_id="ollama:test-model",
        extracted_at=_dt.now(UTC),
    )


def test_extraction_namespace_omitted_when_not_supplied(
    firm_config_factory, trust_data_factory
):
    """`extraction=None` (default) → no `extraction` key in the context."""
    trust = trust_data_factory()
    config = firm_config_factory()
    ctx = build_eval_context(trust, config, _dt.now(UTC).date())
    assert "extraction" not in ctx


def test_extraction_namespace_present_when_supplied(
    firm_config_factory, trust_data_factory
):
    """`extraction=trace` → `extraction` key present in the context."""
    trust = trust_data_factory()
    config = firm_config_factory()
    ctx = build_eval_context(
        trust, config, _dt.now(UTC).date(), extraction=_make_trace()
    )
    assert "extraction" in ctx
    assert "fields" in ctx["extraction"]
    assert "backend_id" in ctx["extraction"]
    assert ctx["extraction"]["backend_id"] == "ollama:test-model"


def test_extraction_namespace_fields_payload_matches_model_dump(
    firm_config_factory, trust_data_factory
):
    """The fields list mirrors `model_dump`; field_path is preserved verbatim."""
    trust = trust_data_factory()
    config = firm_config_factory()
    trace = _make_trace()
    ctx = build_eval_context(
        trust, config, _dt.now(UTC).date(), extraction=trace
    )
    assert len(ctx["extraction"]["fields"]) == 1
    assert (
        ctx["extraction"]["fields"][0]["field_path"]
        == "grantor.full_legal_name"
    )
    assert ctx["extraction"]["fields"][0]["illegible"] is True
