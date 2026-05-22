"""Tests for the canonical TrustData schema."""

from trust_generator.v2.schema import (
    BeneficiaryShare,
    Child,
    Elections,
    InitialTrustee,
    PersonInfo,
    PropertyClassification,
    SuccessorTrustee,
    TrustData,
    TrustIdentity,
    TrustType,
)


def test_empty_trust_data_has_defaults():
    """A TrustData with no arguments should have sensible defaults."""
    td = TrustData()
    assert td.elections.initial_trustee == InitialTrustee.BOTH
    assert td.elections.spendthrift is True
    assert td.elections.no_contest is True
    assert td.elections.probate_coordination is True
    assert td.elections.property_classification == PropertyClassification.COMMUNAL
    assert td.children == []
    assert td.asset_summary() == ["[...ASSETS]"]


def test_boolean_elections_can_be_false():
    """Verify that boolean elections actually respect False values.
    This is the fix for the original boolean conditional bug.
    """
    td = TrustData(
        elections=Elections(
            spendthrift=False,
            no_contest=False,
            probate_coordination=False,
        )
    )
    assert td.elections.spendthrift is False
    assert td.elections.no_contest is False
    assert td.elections.probate_coordination is False


def test_trust_name_derived_from_party_a():
    td = TrustData(party_a=PersonInfo(full_legal_name="John Andrew Smith"))
    assert td.trust_name == "The Smith Family Trust"


def test_trust_name_explicit():
    td = TrustData(
        trust_id=TrustIdentity(desired_trust_name="The Anderson Family Trust")
    )
    assert td.trust_name == "The Anderson Family Trust"


def test_trustee_names_both():
    td = TrustData(
        party_a=PersonInfo(full_legal_name="John Smith"),
        party_b=PersonInfo(full_legal_name="Jane Smith"),
        elections=Elections(initial_trustee=InitialTrustee.BOTH),
    )
    assert td.trustee_names == "John Smith and Jane Smith"


def test_trustee_names_party_a_only():
    td = TrustData(
        party_a=PersonInfo(full_legal_name="John Smith"),
        elections=Elections(initial_trustee=InitialTrustee.PARTY_A),
    )
    assert td.trustee_names == "John Smith"


def test_json_round_trip():
    """Schema should serialize to JSON and back without data loss."""
    original = TrustData(
        party_a=PersonInfo(full_legal_name="John Smith", ssn="123-45-6789"),
        party_b=PersonInfo(full_legal_name="Jane Smith"),
        children=[
            Child(name="Alice Smith", dob="01/15/2000", relationship="Daughter"),
            Child(name="Bob Smith", dob="03/22/2002", relationship="Son"),
        ],
        successor_trustees=[
            SuccessorTrustee(order="1", name="Alice Smith", relationship="Daughter"),
        ],
        beneficiary_shares=[
            BeneficiaryShare(name="Alice Smith", share="50"),
            BeneficiaryShare(name="Bob Smith", share="50"),
        ],
        elections=Elections(spendthrift=False),
    )
    json_str = original.model_dump_json()
    restored = TrustData.model_validate_json(json_str)
    assert restored.party_a.full_legal_name == "John Smith"
    assert restored.party_a.ssn == "123-45-6789"
    assert len(restored.children) == 2
    assert restored.children[0].name == "Alice Smith"
    assert restored.elections.spendthrift is False
    assert len(restored.beneficiary_shares) == 2


def test_trust_type_defaults_to_joint():
    td = TrustData()
    assert td.trust_type == TrustType.JOINT


def test_individual_trust_type():
    td = TrustData(trust_type=TrustType.INDIVIDUAL)
    assert td.trust_type == TrustType.INDIVIDUAL


def test_individual_trust_name_from_grantor():
    td = TrustData(
        trust_type=TrustType.INDIVIDUAL,
        grantor=PersonInfo(full_legal_name="Robert James Wilson"),
    )
    assert td.trust_name == "The Wilson Family Trust"


def test_individual_trustee_names():
    td = TrustData(
        trust_type=TrustType.INDIVIDUAL,
        grantor=PersonInfo(full_legal_name="Robert James Wilson"),
    )
    assert td.trustee_names == "Robert James Wilson"


def test_individual_grantor_name_property():
    td = TrustData(
        trust_type=TrustType.INDIVIDUAL,
        grantor=PersonInfo(full_legal_name="Robert James Wilson"),
    )
    assert td.grantor_name == "Robert James Wilson"


def test_joint_grantor_name_property():
    td = TrustData(
        party_a=PersonInfo(full_legal_name="John Smith"),
        party_b=PersonInfo(full_legal_name="Jane Smith"),
    )
    assert td.grantor_name == "John Smith and Jane Smith"


def test_individual_ssn_owner():
    td = TrustData(
        trust_type=TrustType.INDIVIDUAL,
        grantor=PersonInfo(full_legal_name="Robert Wilson"),
    )
    assert td.ssn_owner_name == "Robert Wilson"


def test_asset_summary():
    from trust_generator.v2.schema import FinancialAccount, RealProperty, Vehicle

    td = TrustData(
        real_property=[RealProperty(address="123 Main St", equity="$200,000")],
        financial_accounts=[
            FinancialAccount(institution="Chase", type="Checking", value="$50,000")
        ],
        vehicles=[Vehicle(description="2020 Toyota Camry", value="$25,000")],
    )
    summary = td.asset_summary()
    assert len(summary) == 3
    assert "123 Main St" in summary[0]
    assert "Chase" in summary[1]
    assert "Toyota Camry" in summary[2]


def test_ssn_owner_coercion_from_old_strings():
    from trust_generator.v2.schema import SsnOwner, TrustIdentity

    ti = TrustIdentity(whose_ssn_for_tax_id="wife")
    assert ti.whose_ssn_for_tax_id == SsnOwner.PARTY_B
    ti2 = TrustIdentity(whose_ssn_for_tax_id="husband")
    assert ti2.whose_ssn_for_tax_id == SsnOwner.PARTY_A
    ti3 = TrustIdentity(whose_ssn_for_tax_id="")
    assert ti3.whose_ssn_for_tax_id == SsnOwner.PARTY_A


def test_json_backward_compat_husband_wife_keys():
    old_json = (
        '{"husband": {"full_legal_name": "John"}, "wife": {"full_legal_name": "Jane"}}'
    )
    data = TrustData.model_validate_json(old_json)
    assert data.party_a.full_legal_name == "John"
    assert data.party_b.full_legal_name == "Jane"


def test_missing_sentinel_is_bracket_missing():
    data = TrustData()
    assert data.party_a_name == "[MISSING]"


def test_custom_party_labels_default():
    data = TrustData()
    assert data.party_a_label == "Husband"
    assert data.party_b_label == "Wife"


def test_custom_party_labels_set():
    data = TrustData(party_a_label="Spouse 1", party_b_label="Spouse 2")
    assert data.party_a_label == "Spouse 1"
    assert data.party_b_label == "Spouse 2"


# ---------------------------------------------------------------------------
# SsnOwner coercion edge cases
# ---------------------------------------------------------------------------


def test_ssn_owner_coercion_uppercase():
    """Uppercase old values should be coerced correctly."""
    from trust_generator.v2.schema import SsnOwner, TrustIdentity

    ti = TrustIdentity(whose_ssn_for_tax_id="WIFE")
    assert ti.whose_ssn_for_tax_id == SsnOwner.PARTY_B
    ti2 = TrustIdentity(whose_ssn_for_tax_id="Husband")
    assert ti2.whose_ssn_for_tax_id == SsnOwner.PARTY_A


def test_ssn_owner_coercion_enum_values():
    """Enum string values should work directly."""
    from trust_generator.v2.schema import SsnOwner, TrustIdentity

    ti = TrustIdentity(whose_ssn_for_tax_id="party_a")
    assert ti.whose_ssn_for_tax_id == SsnOwner.PARTY_A
    ti2 = TrustIdentity(whose_ssn_for_tax_id="party_b")
    assert ti2.whose_ssn_for_tax_id == SsnOwner.PARTY_B
    ti3 = TrustIdentity(whose_ssn_for_tax_id="grantor")
    assert ti3.whose_ssn_for_tax_id == SsnOwner.GRANTOR


def test_ssn_owner_name_individual_uses_grantor():
    """Individual trust ssn_owner_name should use grantor name."""
    data = TrustData(
        trust_type=TrustType.INDIVIDUAL,
        grantor=PersonInfo(full_legal_name="Alice Smith"),
    )
    assert data.ssn_owner_name == "Alice Smith"


def test_ssn_owner_name_joint_party_b():
    """Joint trust with PARTY_B ssn owner should use party_b name."""
    from trust_generator.v2.schema import SsnOwner, TrustIdentity

    data = TrustData(
        party_a=PersonInfo(full_legal_name="John Smith"),
        party_b=PersonInfo(full_legal_name="Jane Smith"),
        trust_id=TrustIdentity(whose_ssn_for_tax_id=SsnOwner.PARTY_B),
    )
    assert data.ssn_owner_name == "Jane Smith"


# ---------------------------------------------------------------------------
# Backward-compat: labels preserved after old JSON load
# ---------------------------------------------------------------------------


def test_json_backward_compat_preserves_default_labels():
    """Loading old-format JSON should keep default party labels."""
    old_json = (
        '{"husband": {"full_legal_name": "John"}, "wife": {"full_legal_name": "Jane"}}'
    )
    data = TrustData.model_validate_json(old_json)
    assert data.party_a_label == "Husband"
    assert data.party_b_label == "Wife"


# ---------------------------------------------------------------------------
# get_or_default logs on bad field path
# ---------------------------------------------------------------------------


def test_get_or_default_logs_on_bad_field_path(caplog):
    """get_or_default should log a warning for invalid field paths."""
    import logging

    data = TrustData()
    with caplog.at_level(logging.WARNING, logger="trust_generator.schema"):
        result = data.get_or_default("nonexistent_field.name")
    assert result == "[MISSING]"
    assert "nonexistent_field.name" in caplog.text
