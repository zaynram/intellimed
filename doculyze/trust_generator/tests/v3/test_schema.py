"""Tests for the v3 canonical schema (trust_generator.v3.schema).

Scope: externally-observable behavior of schema.py only. The schema itself is
out of scope for edits this session (see the design spec, §3 F-2). Failing
tests should be investigated as either test defects or latent schema defects
worth escalating, but schema.py is not modified from within this suite.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from trust_generator.v3.schema import (
    BeneficiaryShare,
    BiologicalParent,
    Child,
    ChildCountTier,
    ChildRelationship,
    CustomTerm,
    CustomTermCategory,
    Descendant,
    DigitalAssetAccess,
    DigitalAssetDirective,
    DigitalAssetType,
    DistributionStandard,
    Elections,
    EstateValueRange,
    FinancialAccount,
    GrantorInfo,
    GuardianshipDesignation,
    GuardianshipPolicy,
    InitialTrustee,
    InsurancePolicy,
    MaritalStatus,
    OtherBeneficiary,
    Pension,
    PersonReference,
    Pet,
    PropertyClassification,
    QuestionnaireSeed,
    RealProperty,
    SpecificBequest,
    SsnOwner,
    TrustData,
    TrustType,
    Valuable,
    Vehicle,
    WithdrawalStep,
    _ChildRelationship,
    _resolve_captions,
    promote_seed,
)

# ---------------------------------------------------------------------------
# 4.1 PersonReference name validator
# ---------------------------------------------------------------------------


def test_full_legal_name_empty_is_accepted():
    """Empty name is permitted so default-constructed person-refs stay valid."""
    ref = PersonReference()
    assert ref.full_legal_name == ""


def test_full_legal_name_single_token_rejected():
    """Single-token names are almost always intake errors; validator rejects them."""
    with pytest.raises(ValidationError) as exc_info:
        PersonReference(full_legal_name="Madonna")
    assert "Madonna" in str(exc_info.value)
    assert "two or more tokens" in str(exc_info.value)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("John Smith", "John Smith"),
        ("Mary Ann Smith", "Mary Ann Smith"),
        ("  John   Smith  ", "John   Smith"),
    ],
    ids=["two-tokens", "three-tokens", "padded-whitespace"],
)
def test_full_legal_name_accepts_two_or_more_tokens(raw: str, expected: str):
    """Two+ whitespace-separated tokens pass; leading/trailing whitespace stripped."""
    ref = PersonReference(full_legal_name=raw)
    assert ref.full_legal_name == expected


# ---------------------------------------------------------------------------
# 4.2 is_minor_as_of edge cases
# ---------------------------------------------------------------------------


def test_is_minor_returns_false_when_dob_is_none():
    """Missing DOB fails closed (False) to avoid false-positive minor status."""
    ref = PersonReference(full_legal_name="John Smith")
    assert ref.is_minor_as_of(date(2026, 4, 21)) is False


def test_is_minor_returns_false_for_entity():
    """Entities short-circuit to False even with a spurious DOB populated."""
    ref = PersonReference(
        is_entity=True,
        entity_name="Acme Trust Co.",
        date_of_birth=date(2020, 1, 1),
    )
    assert ref.is_minor_as_of(date(2026, 4, 21)) is False


def test_is_minor_true_day_before_eighteenth_birthday():
    """Pre-birthday boundary: tuple comparison treats as 'not yet had birthday'."""
    ref = PersonReference(
        full_legal_name="Alex Example",
        date_of_birth=date(2008, 4, 22),
    )
    assert ref.is_minor_as_of(date(2026, 4, 21)) is True


@pytest.mark.parametrize(
    "dob,ref_date,expected",
    [
        (date(2008, 4, 21), date(2026, 4, 21), False),
        (date(2008, 2, 29), date(2026, 2, 28), True),
        (date(2008, 2, 29), date(2026, 3, 1), False),
    ],
    ids=["on-birthday", "leap-day-pre", "leap-day-post"],
)
def test_is_minor_false_on_eighteenth_birthday(
    dob: date, ref_date: date, expected: bool
):
    """Inclusive-birthday + leap-day boundary (see spec §3 F-4)."""
    ref = PersonReference(full_legal_name="Alex Example", date_of_birth=dob)
    assert ref.is_minor_as_of(ref_date) is expected


# ---------------------------------------------------------------------------
# 4.3 GrantorInfo SSN validator
# ---------------------------------------------------------------------------


def test_ssn_last_four_empty_allowed():
    """Empty ssn_last_four permitted so default-constructed grantors stay valid."""
    info = GrantorInfo(full_legal_name="John Smith")
    assert info.ssn_last_four == ""


def test_ssn_last_four_four_digits_accepted():
    """Happy path: exactly four ASCII digits."""
    info = GrantorInfo(full_legal_name="John Smith", ssn_last_four="1234")
    assert info.ssn_last_four == "1234"


@pytest.mark.parametrize(
    "bad_input",
    ["123", "12345", "abcd", "12a4", "12 4", "-234"],
    ids=["too-short", "too-long", "alphabetic", "mixed", "whitespace", "punctuation"],
)
def test_ssn_last_four_rejects_wrong_length_or_non_digits(bad_input: str):
    """len == 4 and isdigit() — each parametrized row hits a distinct rejection."""
    with pytest.raises(ValidationError):
        GrantorInfo(full_legal_name="John Smith", ssn_last_four=bad_input)


# ---------------------------------------------------------------------------
# 4.4 Recipient-XOR validators on distributions
# ---------------------------------------------------------------------------


def test_beneficiary_share_rejects_neither_recipient():
    """Both refs None → validation error citing 'requires recipient_ref or recipient_external'."""
    with pytest.raises(ValidationError) as exc_info:
        BeneficiaryShare(share_percent=Decimal(50))
    assert "requires recipient_ref or recipient_external" in str(exc_info.value)


def test_beneficiary_share_rejects_both_recipients():
    """Both refs populated → 'specify recipient_ref OR recipient_external'."""
    with pytest.raises(ValidationError) as exc_info:
        BeneficiaryShare(
            recipient_ref="child_1",
            recipient_external=PersonReference(full_legal_name="Jane Smith"),
            share_percent=Decimal(50),
        )
    assert "specify recipient_ref OR recipient_external" in str(exc_info.value)


def test_specific_bequest_rejects_neither_recipient():
    """Same neither-supplied branch as BeneficiaryShare, parallel validator."""
    with pytest.raises(ValidationError) as exc_info:
        SpecificBequest(item="grandfather clock")
    assert "requires recipient_ref or recipient_external" in str(exc_info.value)


def test_specific_bequest_rejects_both_recipients():
    """Same both-supplied branch, parallel validator."""
    with pytest.raises(ValidationError) as exc_info:
        SpecificBequest(
            item="clock",
            recipient_ref="other_1",
            recipient_external=PersonReference(full_legal_name="Jane Smith"),
        )
    assert "specify recipient_ref OR recipient_external" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 4.5 PEP 695 type alias runtime semantics
# ---------------------------------------------------------------------------


def test_child_relationship_alias_is_not_runtime_class():
    """PEP 695 ``type`` aliases are typing.TypeAliasType, not classes.

    Load-bearing guardrail: any downstream code reaching for
    ``isinstance(x, ChildRelationship)`` will fail here, pointing the
    author to the supported ``.value == "..."`` comparison idiom.
    """
    # (a) The underlying Enum is a real class; isinstance works against it.
    assert isinstance(_ChildRelationship.ADOPTED, _ChildRelationship)

    # (b) The PEP 695 alias is NOT a runtime class.
    with pytest.raises(TypeError):
        isinstance(_ChildRelationship.ADOPTED, ChildRelationship)  # type: ignore[arg-type]

    # (c) Value-string equality is the supported comparison idiom.
    assert _ChildRelationship.ADOPTED.value == "adopted"


# ---------------------------------------------------------------------------
# 4.6 Two-axis relationship
# ---------------------------------------------------------------------------


def test_child_adopted_with_other_biological_parent_roundtrips():
    """Stepchild-later-adopted scenario: legal status ADOPTED, biology OTHER.

    The two-axis model exists precisely to distinguish this from a plain
    ADOPTED-with-both-grantor-biology case. Single-axis collapse loses it.
    """
    original = Child(
        full_legal_name="Alice Smith",
        relationship=_ChildRelationship.ADOPTED,
        biological_parent=BiologicalParent.OTHER,
    )
    payload = original.model_dump_json()
    restored = Child.model_validate_json(payload)

    assert restored.relationship == _ChildRelationship.ADOPTED
    assert restored.biological_parent == BiologicalParent.OTHER
    assert restored.full_legal_name == "Alice Smith"


# ---------------------------------------------------------------------------
# 4.7 Defaults audit
# ---------------------------------------------------------------------------


def test_trust_data_defaults_match_spec():
    """Consolidated defaults gate. Any drift fails this single test.

    Captions, policies, and protective booleans are all load-bearing for
    generator output — cheaper to regress here than in a document diff.
    """
    data = TrustData()

    # trust_id block
    assert data.trust_id.trust_type == TrustType.JOINT
    assert data.trust_id.marital_status == MaritalStatus.MARRIED
    assert data.trust_id.grantor_caption == "Grantor"
    assert data.trust_id.co_grantor_caption == "Spouse"
    assert data.trust_id.tax_id_ssn_preference == SsnOwner.GRANTOR
    assert data.trust_id.state_of_governing_law == "Illinois"

    # elections block
    assert data.elections.initial_trustee == InitialTrustee.GRANTORS
    assert data.elections.property_classification == PropertyClassification.COMMUNAL
    assert data.elections.distribution_standard == DistributionStandard.HEMS
    assert (
        data.elections.guardianship_policy == GuardianshipPolicy.EXPLICIT_DESIGNATIONS
    )
    assert data.elections.spendthrift is True
    assert data.elections.no_contest is True
    assert data.elections.probate_coordination is True
    assert data.elections.portability is True
    assert data.elections.trustee_bond is False

    # roots
    assert data.children == []
    assert data.custom_terms == []
    assert data.co_grantor is None


def test_boolean_elections_preserve_false_when_set():
    """Regression guard against the v2 boolean-conditional bug.

    Defaults-true booleans are the classic Pydantic trap if a parser
    ever coerces falsy values incorrectly.
    """
    elections = Elections(
        spendthrift=False,
        no_contest=False,
        probate_coordination=False,
        portability=False,
    )
    assert elections.spendthrift is False
    assert elections.no_contest is False
    assert elections.probate_coordination is False
    assert elections.portability is False


# ---------------------------------------------------------------------------
# 4.8 Computed-property sentinel chains
# ---------------------------------------------------------------------------


def test_trust_name_fallback_chain():
    """Explicit name → surname-derived → [TRUST NAME] sentinel, in that order."""
    data = TrustData()

    # 1. explicit desired_trust_name wins
    data.trust_id.desired_trust_name = "The Anderson Family Trust"
    data.grantor.full_legal_name = "Robert James Wilson"
    assert data.trust_name == "The Anderson Family Trust"

    # 2. empty desired + populated grantor → surname-derived fallback
    data.trust_id.desired_trust_name = ""
    assert data.trust_name == "The Wilson Family Trust"

    # 3. both empty → sentinel so missingness is visible in draft output
    data.grantor.full_legal_name = ""
    assert data.trust_name == "[TRUST NAME]"


def test_grantor_name_sentinels():
    """Three-state distinction of the co-grantor axis: absent, unfilled, populated."""
    # absent: empty string so generator omits co-grantor lines entirely
    data = TrustData()
    assert data.grantor_full_name == "[GRANTOR NAME]"
    assert data.co_grantor_full_name == ""

    # present-but-unfilled: sentinel so the draft surfaces the gap
    data.co_grantor = GrantorInfo()
    assert data.co_grantor_full_name == "[CO-GRANTOR NAME]"


# ---------------------------------------------------------------------------
# 4.9 Caption and display properties
# ---------------------------------------------------------------------------


def test_grantor_display_name_and_combined_name():
    """Captions are first-class fields; display properties read them directly."""
    # dual-grantor populated
    data = TrustData()
    data.grantor.full_legal_name = "John Smith"
    data.co_grantor = GrantorInfo(full_legal_name="Jane Smith")

    assert data.grantor_display_name == "Grantor: John Smith"
    assert data.grantors_combined_name == "John Smith and Jane Smith"

    # solo-grantor branch
    data.co_grantor = None
    assert data.co_grantor_display_name == ""
    assert data.grantors_combined_name == "John Smith"


@pytest.mark.parametrize(
    "trust_type,marital_status,grantor_caption,co_grantor_caption,co_grantor_none",
    [
        (TrustType.JOINT, MaritalStatus.MARRIED, "Grantor A", "Grantor B", False),
        (TrustType.JOINT, MaritalStatus.UNMARRIED, "Grantor A", "Grantor B", False),
        (TrustType.INDIVIDUAL, MaritalStatus.MARRIED, "Grantor", "Spouse", False),
        (TrustType.INDIVIDUAL, MaritalStatus.UNMARRIED, "Grantor", "Spouse", True),
    ],
    ids=[
        "joint-married",
        "joint-unmarried",
        "individual-married",
        "individual-unmarried",
    ],
)
def test_promote_seed_caption_resolution_matrix(
    trust_type: TrustType,
    marital_status: MaritalStatus,
    grantor_caption: str,
    co_grantor_caption: str,
    co_grantor_none: bool,
):
    """Full 2x2 over (trust_type, marital_status): captions + co_grantor presence.

    promote_seed is the single point where this resolves. Skipping any row
    leaves a conditional branch unverified.
    """
    seed = QuestionnaireSeed(trust_type=trust_type, marital_status=marital_status)
    data = promote_seed(seed)

    assert data.trust_id.grantor_caption == grantor_caption
    assert data.trust_id.co_grantor_caption == co_grantor_caption
    assert (data.co_grantor is None) is co_grantor_none


# ---------------------------------------------------------------------------
# 4.10 SSN owner name
# ---------------------------------------------------------------------------


def test_ssn_owner_name_switches_on_preference():
    """ssn_owner_name routes through tax_id_ssn_preference; EIN workflow depends on it."""
    data = TrustData(
        grantor=GrantorInfo(full_legal_name="John Smith"),
        co_grantor=GrantorInfo(full_legal_name="Jane Smith"),
    )

    # default: GRANTOR
    assert data.trust_id.tax_id_ssn_preference == SsnOwner.GRANTOR
    assert data.ssn_owner_name == "John Smith"

    # switched to CO_GRANTOR
    data.trust_id.tax_id_ssn_preference = SsnOwner.CO_GRANTOR
    assert data.ssn_owner_name == "Jane Smith"


SEED_ONLY_FIELDS = (
    "paralegal_name",
    "attorney_name",
    "consultation_date",
    "accessibility_overrides",
    "has_pets",
    "child_count_tier",
)


# ---------------------------------------------------------------------------
# 4.11 promote_seed fidelity
# ---------------------------------------------------------------------------


def test_promote_seed_projects_expected_fields():
    """The four fields promote_seed explicitly forwards must land on TrustData."""
    seed = QuestionnaireSeed(
        trust_type=TrustType.JOINT,
        marital_status=MaritalStatus.MARRIED,
        estate_value_estimate=EstateValueRange.ABOVE_THRESHOLD,
        preliminary_trust_name="The Test Trust",
    )
    data = promote_seed(seed)

    assert data.trust_id.trust_type == TrustType.JOINT
    assert data.trust_id.marital_status == MaritalStatus.MARRIED
    assert data.trust_id.desired_trust_name == "The Test Trust"
    assert data.elections.estate_value_estimate == EstateValueRange.ABOVE_THRESHOLD


def test_promote_seed_drops_seed_only_fields():
    """Bounded-context boundary: seed-only fields must not appear as TrustData model fields."""
    seed = QuestionnaireSeed(
        paralegal_name="Sam",
        attorney_name="Alice",
        consultation_date=date(2026, 4, 1),
        accessibility_overrides={"font_size": "14pt"},
        has_pets=True,
        child_count_tier=ChildCountTier.ONE_TO_FIVE,
    )
    data = promote_seed(seed)
    for seed_only in SEED_ONLY_FIELDS:
        assert seed_only not in TrustData.model_fields, (
            f"TrustData unexpectedly exposes seed-only field {seed_only!r}"
        )
    assert data.trust_id.desired_trust_name == ""
    assert data.elections.estate_value_estimate == EstateValueRange.BELOW_THRESHOLD


def test_promote_seed_is_one_shot_initializer():
    """I2: re-invocation returns a fresh TrustData; mutations on prior returns do not leak."""
    seed = QuestionnaireSeed(
        trust_type=TrustType.JOINT, marital_status=MaritalStatus.MARRIED
    )
    first = promote_seed(seed)
    first.grantor.full_legal_name = "Alice Wonderland"
    first.trust_id.desired_trust_name = "Mutated Trust"

    second = promote_seed(seed)

    assert second.grantor.full_legal_name == ""
    assert second.trust_id.desired_trust_name == ""
    assert first is not second
    assert first.grantor is not second.grantor
    assert first.trust_id is not second.trust_id


# ---------------------------------------------------------------------------
# 4.12 Aggregation properties
# ---------------------------------------------------------------------------


def test_disinherited_beneficiaries_aggregates_across_sections():
    """Union across children / descendants / other_beneficiaries, in that order."""
    data = TrustData(
        children=[
            Child(full_legal_name="Alice Smith", disinherit=True),
            Child(full_legal_name="Bob Smith"),
        ],
        descendants=[
            Descendant(full_legal_name="Carla Smith", disinherit=True),
        ],
        other_beneficiaries=[
            OtherBeneficiary(full_legal_name="Dan Smith", disinherit=True),
        ],
    )

    disinherited = data.disinherited_beneficiaries
    assert len(disinherited) == 3
    # Ordering matters: children-first, then descendants, then other.
    assert isinstance(disinherited[0], Child)
    assert isinstance(disinherited[1], Descendant)
    assert isinstance(disinherited[2], OtherBeneficiary)


def test_excluded_persons_unions_disinherited_and_external():
    """Section 11's exclusion clause iterates this union; ordering is observable."""
    data = TrustData(
        children=[Child(full_legal_name="Alice Smith", disinherit=True)],
        external_exclusions=[PersonReference(full_legal_name="Zed Example")],
    )

    excluded = data.excluded_persons
    assert len(excluded) == 2
    # Disinherited precedes external.
    assert excluded[0].full_legal_name == "Alice Smith"
    assert excluded[1].full_legal_name == "Zed Example"


# ---------------------------------------------------------------------------
# 4.13 Asset totalization
# ---------------------------------------------------------------------------


def test_collected_total_value_sums_all_asset_types():
    """Sum must span all six asset types and preserve Decimal exactness."""
    # empty-case zero, preserved as Decimal
    assert TrustData().collected_total_value == Decimal(0)
    assert isinstance(TrustData().collected_total_value, Decimal)

    data = TrustData(
        real_property=[RealProperty(value=Decimal(100))],
        financial_accounts=[FinancialAccount(value=Decimal(200))],
        vehicles=[Vehicle(value=Decimal(50))],
        insurance_policies=[InsurancePolicy(benefit=Decimal(500))],
        pensions=[Pension(value=Decimal(300))],
        valuables=[Valuable(value=Decimal(25))],
    )
    total = data.collected_total_value
    assert total == Decimal(1175)
    assert isinstance(total, Decimal)


# ---------------------------------------------------------------------------
# 4.14 QuestionnaireSeed variant key
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "trust_type,marital_status,estate,child_count,expected",
    [
        (
            TrustType.JOINT,
            MaritalStatus.MARRIED,
            EstateValueRange.ABOVE_THRESHOLD,
            ChildCountTier.ONE_TO_FIVE,
            "joint_married_above_threshold_one_to_five",
        ),
        (
            TrustType.INDIVIDUAL,
            MaritalStatus.UNMARRIED,
            EstateValueRange.BELOW_THRESHOLD,
            ChildCountTier.NONE,
            "individual_unmarried_below_threshold_none",
        ),
        (
            TrustType.INDIVIDUAL,
            MaritalStatus.MARRIED,
            EstateValueRange.DECLINED_TO_ESTIMATE,
            ChildCountTier.SIX_PLUS,
            "individual_married_declined_six_plus",
        ),
    ],
    ids=[
        "joint-above-1to5",
        "individual-unmarried-below-none",
        "individual-declined-6plus",
    ],
)
def test_variant_key_composition(
    trust_type: TrustType,
    marital_status: MaritalStatus,
    estate: EstateValueRange,
    child_count: ChildCountTier,
    expected: str,
):
    """variant_key is the print-layout selector — an API surface.

    The printable generator looks up templates by this exact string. Any
    change to hyphens, capitalization, or axis ordering silently breaks
    generation.
    """
    seed = QuestionnaireSeed(
        trust_type=trust_type,
        marital_status=marital_status,
        estate_value_estimate=estate,
        child_count_tier=child_count,
    )
    assert seed.variant_key == expected


# ---------------------------------------------------------------------------
# 4.15 Round-trip serialization
# ---------------------------------------------------------------------------


def test_trust_data_json_round_trip_preserves_v3_fields():
    """Every new v3 field must survive JSON round-trip.

    JSON is the persistence format between GUI, parser, and generator.
    If a field doesn't round-trip, it doesn't exist for downstream consumers.
    """
    original = TrustData(
        pets=[
            Pet(
                name="Rex",
                species="dog",
                designated_caretaker_ref="child_1",
                funding_amount=Decimal(5000),
            ),
        ],
        digital_asset_directives=[
            DigitalAssetDirective(
                asset_type=DigitalAssetType.EMAIL,
                access_instruction=DigitalAssetAccess.DELETE,
                service_provider="ExampleMail",
            ),
        ],
        custom_terms=[
            CustomTerm(
                category=CustomTermCategory.DISTRIBUTION,
                content="Distribute equally among surviving issue.",
            ),
        ],
        external_exclusions=[
            PersonReference(full_legal_name="Zed Example"),
        ],
        guardianship_designations=[
            GuardianshipDesignation(
                minor_child_ref="child_1",
                guardian_of_person_ref="sibling_1",
                guardian_of_estate_ref="attorney_1",
            ),
        ],
        children=[
            Child(
                full_legal_name="Alice Smith",
                relationship=_ChildRelationship.ADOPTED,
                biological_parent=BiologicalParent.OTHER,
            ),
        ],
        beneficiary_shares=[
            BeneficiaryShare(
                recipient_ref="child_1",
                share_percent=Decimal("50.00"),
            ),
        ],
        specific_bequests=[
            SpecificBequest(
                item="grandfather clock",
                recipient_external=PersonReference(full_legal_name="Jane Smith"),
            ),
        ],
        withdrawal_schedule=[
            WithdrawalStep(age=25, percent=Decimal("25.00")),
        ],
    )

    payload = original.model_dump_json()
    restored = TrustData.model_validate_json(payload)

    # list-length preservation
    assert len(restored.pets) == 1
    assert len(restored.digital_asset_directives) == 1
    assert len(restored.custom_terms) == 1
    assert len(restored.external_exclusions) == 1
    assert len(restored.guardianship_designations) == 1
    assert len(restored.children) == 1
    assert len(restored.beneficiary_shares) == 1
    assert len(restored.specific_bequests) == 1
    assert len(restored.withdrawal_schedule) == 1

    # enum fields preserved as enum members
    assert restored.digital_asset_directives[0].asset_type == DigitalAssetType.EMAIL
    assert (
        restored.digital_asset_directives[0].access_instruction
        == DigitalAssetAccess.DELETE
    )
    assert restored.custom_terms[0].category == CustomTermCategory.DISTRIBUTION

    # Decimal preservation — exact, not float-coerced
    assert restored.pets[0].funding_amount == Decimal(5000)
    assert isinstance(restored.pets[0].funding_amount, Decimal)
    assert restored.beneficiary_shares[0].share_percent == Decimal("50.00")
    assert isinstance(restored.beneficiary_shares[0].share_percent, Decimal)
    assert restored.withdrawal_schedule[0].percent == Decimal("25.00")

    # two-axis Child relationship — both axes preserved
    assert restored.children[0].relationship == _ChildRelationship.ADOPTED
    assert restored.children[0].biological_parent == BiologicalParent.OTHER


@pytest.mark.parametrize(
    ("trust_type", "expected"),
    [
        (TrustType.JOINT, ("Grantor A", "Grantor B")),
        (TrustType.INDIVIDUAL, ("Grantor", "Spouse")),
    ],
    ids=["joint", "individual"],
)
def test_resolve_captions_returns_expected_tuple(
    trust_type: TrustType, expected: tuple[str, str]
):
    """_resolve_captions returns (grantor_caption, co_grantor_caption) by trust_type."""
    assert _resolve_captions(trust_type) == expected


@pytest.mark.parametrize(
    "estate_value",
    [
        EstateValueRange.BELOW_THRESHOLD,
        EstateValueRange.ABOVE_THRESHOLD,
        EstateValueRange.DECLINED_TO_ESTIMATE,
    ],
    ids=["below", "above", "declined"],
)
def test_promote_seed_projects_estate_value_across_domain(
    estate_value: EstateValueRange,
):
    """estate_value_estimate projects unchanged across all three values."""
    seed = QuestionnaireSeed(estate_value_estimate=estate_value)
    data = promote_seed(seed)
    assert data.elections.estate_value_estimate == estate_value


def test_promote_seed_projects_empty_preliminary_name_as_empty_desired_name():
    """Empty preliminary_trust_name flows through as empty desired_trust_name, enabling the fallback chain."""
    seed = QuestionnaireSeed()  # preliminary_trust_name default is ""
    data = promote_seed(seed)
    assert data.trust_id.desired_trust_name == ""
