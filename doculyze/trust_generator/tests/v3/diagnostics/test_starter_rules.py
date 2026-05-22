"""Cycles 7-9 starter rule tests.

Each test exercises one starter rule end-to-end through ``diagnose()``,
asserting both fires-on-violation and silent-on-clean scenarios. Test bodies
filter the diagnostics list to the rule's code so other rules firing or not
firing in the same scenario do not interfere with the assertion.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from trust_generator.v3.diagnostics import diagnose
from trust_generator.v3.schema import (
    BeneficiaryShare,
    DiagnosticLevel,
    DiagnosticSource,
    TrustType,
)


@pytest.mark.parametrize(
    ("shares", "expected_fires"),
    [
        (
            [
                BeneficiaryShare(recipient_ref="a", share_percent=Decimal(33)),
                BeneficiaryShare(recipient_ref="b", share_percent=Decimal(33)),
                BeneficiaryShare(recipient_ref="c", share_percent=Decimal(33)),
            ],
            True,
        ),
        ([], False),
        (
            [
                BeneficiaryShare(recipient_ref="a", share_percent=Decimal(50)),
                BeneficiaryShare(recipient_ref="b", share_percent=Decimal(50)),
            ],
            False,
        ),
        (
            [
                BeneficiaryShare(recipient_ref="a", share_percent=Decimal("33.33")),
                BeneficiaryShare(recipient_ref="b", share_percent=Decimal("33.33")),
                BeneficiaryShare(recipient_ref="c", share_percent=Decimal("33.34")),
            ],
            False,
        ),
        (
            [
                BeneficiaryShare(recipient_ref="a", share_percent=Decimal("33.33")),
                BeneficiaryShare(recipient_ref="b", share_percent=Decimal("33.33")),
                BeneficiaryShare(recipient_ref="c", share_percent=Decimal("33.33")),
            ],
            True,
        ),
    ],
    ids=[
        "sum_99_fires",
        "empty_silent",
        "sum_100_silent",
        "precision_100_silent",
        "precision_99_99_fires",
    ],
)
def test_shares_sum_not_100(
    firm_config_factory, trust_data_factory, shares, expected_fires
):
    """``shares.sum_not_100`` fires iff shares is non-empty AND sum != 100."""
    config = firm_config_factory()
    trust = trust_data_factory(beneficiary_shares=shares)

    diagnostics = diagnose(trust, config, ref_date=date(2026, 4, 23))

    meta = [d for d in diagnostics if d.code.startswith("engine.")]
    assert meta == [], f"unexpected meta-diagnostics: {[d.code for d in meta]}"

    matching = [d for d in diagnostics if d.code == "shares.sum_not_100"]
    if expected_fires:
        assert len(matching) == 1
        assert matching[0].level == DiagnosticLevel.ERROR
        assert matching[0].source == DiagnosticSource.SCHEMA
    else:
        assert matching == []


@pytest.mark.parametrize(
    ("trust_type", "estate_value", "expected_fires"),
    [
        (TrustType.INDIVIDUAL, Decimal(4_500_000), True),
        (TrustType.INDIVIDUAL, Decimal(3_500_000), False),
        (TrustType.JOINT, Decimal(9_000_000), True),
        (TrustType.JOINT, Decimal(5_000_000), False),
        (TrustType.JOINT, None, False),
    ],
    ids=[
        "individual_above_hard",
        "individual_below_hard",
        "joint_above_hard",
        "joint_between_thresholds",
        "null_estimate",
    ],
)
def test_estate_crossed_cliff(
    firm_config_factory,
    trust_data_factory,
    trust_type,
    estate_value,
    expected_fires,
):
    """``estate.crossed_cliff`` fires when estate >= the trust-type-specific hard threshold."""
    config = firm_config_factory()
    trust = trust_data_factory(
        trust_type=trust_type, estate_value_approximate=estate_value
    )

    diagnostics = diagnose(trust, config, ref_date=date(2026, 4, 23))

    meta = [d for d in diagnostics if d.code.startswith("engine.")]
    assert meta == [], f"unexpected meta-diagnostics: {[d.code for d in meta]}"

    matching = [d for d in diagnostics if d.code == "estate.crossed_cliff"]
    if expected_fires:
        assert len(matching) == 1
        assert matching[0].level == DiagnosticLevel.WARNING
        assert matching[0].source == DiagnosticSource.BUSINESS_RULE
    else:
        assert matching == []


@pytest.mark.parametrize(
    ("text", "expected_fires"),
    [
        ("[OCR_LOW_CONFIDENCE]", True),
        ("", False),
        ("I, John Doe, declare...", False),
        ("preamble [OCR_LOW_CONFIDENCE] tail", True),
    ],
    ids=[
        "exact_marker_fires",
        "empty_silent",
        "real_text_silent",
        "embedded_marker_fires",
    ],
)
def test_extraction_placeholder_unfilled(
    firm_config_factory, trust_data_factory, text, expected_fires
):
    """``extraction.placeholder_unfilled`` fires when statement_of_intent contains the OCR marker."""
    config = firm_config_factory()
    trust = trust_data_factory(statement_of_intent=text)

    diagnostics = diagnose(trust, config, ref_date=date(2026, 4, 23))

    meta = [d for d in diagnostics if d.code.startswith("engine.")]
    assert meta == [], f"unexpected meta-diagnostics: {[d.code for d in meta]}"

    matching = [
        d for d in diagnostics if d.code == "extraction.placeholder_unfilled"
    ]
    if expected_fires:
        assert len(matching) == 1
        assert matching[0].level == DiagnosticLevel.WARNING
        assert matching[0].source == DiagnosticSource.EXTRACTION
    else:
        assert matching == []
