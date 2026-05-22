"""Tests for the validation layer."""

from __future__ import annotations

from functools import partial

from trust_generator.v2.config import load_config
from trust_generator.v2.schema import (
    BeneficiaryShare,
    Child,
    Elections,
    PersonInfo,
    PropertyClassification,
    RealProperty,
    RemoteContingent,
    RetirementStrategy,
    SuccessorTrustee,
    TrustData,
    TrustType,
)
from trust_generator.v2.validators import Severity
from trust_generator.v2.validators import validate as _validate

validate = partial(_validate, config=load_config())


def _complete_data() -> TrustData:
    """Return a fully populated TrustData that should pass validation."""
    return TrustData(
        party_a=PersonInfo(full_legal_name="John Andrew Smith"),
        party_b=PersonInfo(full_legal_name="Jane Marie Smith"),
        children=[
            Child(name="Alice Smith", dob="01/15/2000", relationship="Daughter"),
        ],
        successor_trustees=[
            SuccessorTrustee(order="1", name="Alice Smith", relationship="Daughter"),
        ],
        beneficiary_shares=[
            BeneficiaryShare(name="Alice Smith", share="100"),
        ],
        real_property=[
            RealProperty(address="123 Main St"),
        ],
    )


def test_empty_data_has_errors():
    """Empty TrustData should have errors for missing grantor names."""
    report = validate(TrustData())
    error_paths = [f.field_path for f in report.errors]
    assert "party_a.full_legal_name" in error_paths
    assert "party_b.full_legal_name" in error_paths


def test_empty_data_cannot_generate():
    """report.can_generate should be False for empty data."""
    report = validate(TrustData())
    assert report.can_generate is False


def test_complete_data_can_generate():
    """Fully populated TrustData should have can_generate == True."""
    report = validate(_complete_data())
    assert report.can_generate is True


def test_beneficiary_shares_sum_warning():
    """Shares summing to 90 should produce a warning."""
    data = _complete_data()
    data.beneficiary_shares = [
        BeneficiaryShare(name="Alice Smith", share="50"),
        BeneficiaryShare(name="Bob Smith", share="40"),
    ]
    report = validate(data)
    share_warnings = [
        f
        for f in report.warnings
        if f.field_path == "beneficiary_shares" and "sum" in f.message.lower()
    ]
    assert len(share_warnings) == 1
    assert "90" in share_warnings[0].message


def test_beneficiary_shares_sum_ok():
    """Shares summing to 100 should NOT produce a sum warning."""
    data = _complete_data()
    data.beneficiary_shares = [
        BeneficiaryShare(name="Alice Smith", share="60"),
        BeneficiaryShare(name="Bob Smith", share="40"),
    ]
    report = validate(data)
    share_warnings = [
        f
        for f in report.warnings
        if f.field_path == "beneficiary_shares" and "sum" in f.message.lower()
    ]
    assert len(share_warnings) == 0


def test_no_successor_trustees_warning():
    """Empty successor_trustees should produce a warning."""
    data = _complete_data()
    data.successor_trustees = []
    report = validate(data)
    trustee_warnings = [
        f for f in report.warnings if f.field_path == "successor_trustees"
    ]
    assert len(trustee_warnings) == 1
    assert "no successor trustees" in trustee_warnings[0].message.lower()


def test_separate_property_no_assets_warning():
    """SEPARATE classification with no assets should warn."""
    data = _complete_data()
    data.elections = Elections(property_classification=PropertyClassification.SEPARATE)
    data.real_property = []
    data.financial_accounts = []
    data.vehicles = []
    data.insurance_policies = []
    data.pensions = []
    data.valuables = []
    report = validate(data)
    sep_warnings = [
        f
        for f in report.warnings
        if f.field_path == "elections.property_classification"
    ]
    assert len(sep_warnings) == 1
    assert "separate" in sep_warnings[0].message.lower()


def test_charity_contingent_no_name_error():
    """CHARITY remote contingent with empty charity name should error."""
    data = _complete_data()
    data.elections = Elections(
        remote_contingent=RemoteContingent.CHARITY,
        remote_contingent_charity="",
    )
    report = validate(data)
    charity_errors = [
        f
        for f in report.errors
        if f.field_path == "elections.remote_contingent_charity"
    ]
    assert len(charity_errors) == 1
    assert "charity" in charity_errors[0].message.lower()


def test_retirement_trust_strategy_info():
    """TRUST retirement strategy should produce an info finding."""
    data = _complete_data()
    data.elections = Elections(retirement_strategy=RetirementStrategy.TRUST)
    report = validate(data)
    retire_infos = [
        f
        for f in report.findings
        if f.severity == Severity.INFO
        and f.field_path == "elections.retirement_strategy"
    ]
    assert len(retire_infos) == 1
    assert "secure act" in retire_infos[0].message.lower()


def _individual_data() -> TrustData:
    """Return a complete individual TrustData."""
    return TrustData(
        trust_type=TrustType.INDIVIDUAL,
        grantor=PersonInfo(full_legal_name="Robert James Wilson"),
        children=[
            Child(name="Sarah Wilson", dob="05/10/1995", relationship="Daughter"),
        ],
        successor_trustees=[
            SuccessorTrustee(order="1", name="Sarah Wilson", relationship="Daughter"),
        ],
        beneficiary_shares=[
            BeneficiaryShare(name="Sarah Wilson", share="100"),
        ],
        real_property=[
            RealProperty(address="456 Oak Ave"),
        ],
    )


def test_individual_trust_can_generate():
    report = validate(_individual_data())
    assert report.can_generate is True


def test_individual_trust_missing_grantor_name():
    data = TrustData(trust_type=TrustType.INDIVIDUAL)
    report = validate(data)
    error_paths = [f.field_path for f in report.errors]
    assert "grantor.full_legal_name" in error_paths


def test_individual_trust_no_party_b_error():
    data = _individual_data()
    report = validate(data)
    error_paths = [f.field_path for f in report.errors]
    assert "party_b.full_legal_name" not in error_paths


def test_individual_trust_no_party_a_error():
    data = _individual_data()
    report = validate(data)
    error_paths = [f.field_path for f in report.errors]
    assert "party_a.full_legal_name" not in error_paths


def test_party_labels_in_validation_messages():
    """Validation messages should use the data's party labels, not hardcoded names."""
    data = TrustData(party_a_label="Spouse 1", party_b_label="Spouse 2")
    report = validate(data)
    # Find the error findings for the name fields
    name_errors = [f for f in report.errors if "full_legal_name" in f.field_path]
    labels_in_messages = " ".join(f.message for f in name_errors)
    assert "Spouse 1" in labels_in_messages
    assert "Spouse 2" in labels_in_messages
    # Should NOT use generic "Party A" / "Party B"
    assert "Party A" not in labels_in_messages
    assert "Party B" not in labels_in_messages
