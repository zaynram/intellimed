"""
Trust Generator v3 — Canonical schema.

Two bounded contexts live here:

- QuestionnaireSeed: consultation-captured metadata driving the tailored
  printable questionnaire. Authored by the paralegal before the client sees
  anything. Consumed by the printable generator.

- TrustData: the canonical post-fill model. Consumed by document generators,
  validators, and the diagnostic engine. This is what a completed trust
  intake distills to.

An explicit ``promote_seed()`` translation function bridges them. Seed fields
that have a TrustData counterpart are projected forward; seed-only concerns
(paralegal identity, print options) are dropped.

Design commitments codified here (see project memory for full context):

- Python >=3.12 floor; PEP 695 ``type`` statement for enum unions
- Pydantic v2.x; ``ConfigDict``, ``field_validator``, ``model_validator``
- stdlib ``datetime.date`` only; no third-party date library
- Enum comparisons via ``value.value`` equality, never ``isinstance``
- PersonReference as shared base for every person-like entity
- Minor status computed from DOB, never stored
- Two-axis relationship model (ChildRelationship × BiologicalParent)
- grantor / co_grantor canonical naming; captions are first-class fields
- Reference-by-id pattern for distribution recipients
- Estate-value thresholds live in firm_config, not hardcoded
- Diagnostics computed, never stored
- External exclusions as separate list, not force-through-Section-2
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Trust-structure enums
# ---------------------------------------------------------------------------


class TrustType(str, Enum):
    JOINT = "joint"
    INDIVIDUAL = "individual"


class MaritalStatus(str, Enum):
    MARRIED = "married"
    UNMARRIED = "unmarried"


class SsnOwner(str, Enum):
    GRANTOR = "grantor"
    CO_GRANTOR = "co_grantor"


class EstateValueRange(str, Enum):
    BELOW_THRESHOLD = "below_threshold"
    ABOVE_THRESHOLD = "above_threshold"
    DECLINED_TO_ESTIMATE = "declined"


class ChildCountTier(str, Enum):
    NONE = "none"
    ONE_TO_FIVE = "one_to_five"
    SIX_PLUS = "six_plus"


# ---------------------------------------------------------------------------
# Relationship enums — three-tier pattern
# ---------------------------------------------------------------------------
#
# GenericRelationship carries the shared vocabulary used across contexts.
# Scoped enums carry context-specific values. Type aliases union them where
# a context needs both shared and scoped values.
#
# All comparisons use ``value.value == "..."`` equality, never isinstance —
# PEP 695 type aliases are type-checker-visible only, not runtime classes.


class GenericRelationship(str, Enum):
    CHILD = "child"
    SIBLING = "sibling"
    PARENT = "parent"
    SPOUSE = "spouse"
    GRANDCHILD = "grandchild"
    NIECE = "niece"
    NEPHEW = "nephew"
    AUNT = "aunt"
    UNCLE = "uncle"
    COUSIN = "cousin"


class _ChildRelationship(str, Enum):
    BIOLOGICAL = "biological"
    ADOPTED = "adopted"
    STEPCHILD = "stepchild"
    FOSTER = "foster"


class _TrusteeRelationship(str, Enum):
    FRIEND = "friend"
    ATTORNEY = "attorney"
    ACCOUNTANT = "accountant"
    CORPORATE = "corporate"
    OTHER = "other"


class BiologicalParent(str, Enum):
    BOTH = "both"
    GRANTOR_ONLY = "grantor_only"
    CO_GRANTOR_ONLY = "co_grantor_only"
    OTHER = "other"


type ChildRelationship = _ChildRelationship
type TrusteeRelationship = GenericRelationship | _TrusteeRelationship
type DescendantRelationship = GenericRelationship

# ---------------------------------------------------------------------------
# Election enums — Sections 3C, 6, 7, 8, 9, 10
# ---------------------------------------------------------------------------


class InitialTrustee(str, Enum):
    GRANTORS = "grantors"
    GRANTOR_ONLY = "grantor_only"
    CO_GRANTOR_ONLY = "co_grantor_only"
    OTHER = "other"


class PropertyClassification(str, Enum):
    COMMUNAL = "communal"
    SEPARATE = "separate"


class TangibleDistribution(str, Enum):
    EQUAL_CHILDREN = "equal_children"
    EQUAL_BENEFICIARIES = "equal_beneficiaries"


class DivisionMethod(str, Enum):
    TRUSTEE = "trustee"
    LOTTERY = "lottery"
    SELL = "sell"


class DistributionStandard(str, Enum):
    HEMS = "hems"
    BROAD = "broad"


class BeneficiaryDeath(str, Enum):
    PER_STIRPES_BENEFICIARY = "per_stirpes_beneficiary"
    PER_STIRPES_GRANTORS = "per_stirpes_grantors"
    REDISTRIBUTE = "redistribute"


class RemoteContingent(str, Enum):
    INTESTACY = "intestacy"
    CHARITY = "charity"
    OTHER = "other"


class RetirementStrategy(str, Enum):
    POD = "pod"
    TRUST = "trust"
    MIX = "mix"


class InsuranceStrategy(str, Enum):
    SPOUSE_THEN_CHILDREN = "spouse_then_children"
    TO_TRUST = "to_trust"
    OTHER = "other"


class SurvivingAmendment(str, Enum):
    FULL = "full"
    LIMITED = "limited"
    IRREVOCABLE = "irrevocable"


class PowerOfAppointment(str, Enum):
    GENERAL = "general"
    LIMITED = "limited"
    NONE = "none"


class DisputeResolution(str, Enum):
    MEDIATION_ARBITRATION = "mediation_arbitration"
    COURT = "court"


class TrusteeCompensation(str, Enum):
    REASONABLE = "reasonable"
    NONE_FAMILY = "none_family"
    FIXED_ANNUAL = "fixed_annual"
    OTHER = "other"


class GuardianshipPolicy(str, Enum):
    DELEGATE_TO_TRUSTEES = "delegate_to_trustees"
    EXPLICIT_DESIGNATIONS = "explicit_designations"


class CustomTermCategory(str, Enum):
    DISTRIBUTION = "distribution"
    BENEFICIARY = "beneficiary"
    TRUSTEE_POWER = "trustee_power"
    ADMINISTRATION = "administration"
    OTHER = "other"


class DigitalAssetType(str, Enum):
    EMAIL = "email"
    SOCIAL = "social"
    FINANCIAL = "financial"
    CLOUD_STORAGE = "cloud_storage"
    CRYPTO = "crypto"
    OTHER = "other"


class DigitalAssetAccess(str, Enum):
    FULL_ACCESS = "full_access"
    MEMORIALIZE = "memorialize"
    DELETE = "delete"
    PER_PROVIDER_POLICY = "per_provider_policy"


# ---------------------------------------------------------------------------
# Diagnostics enums
# ---------------------------------------------------------------------------


class DiagnosticLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class DiagnosticSource(str, Enum):
    SCHEMA = "schema"
    BUSINESS_RULE = "business_rule"
    EXTRACTION = "extraction"


class DiagnosticContext(str, Enum):
    FILL = "fill"
    GENERATE = "generate"
    BOTH = "both"


# ---------------------------------------------------------------------------
# Shared primitives
# ---------------------------------------------------------------------------


class Address(BaseModel):
    """Structured address. Geocoding populates lat/lon when OSM lookup succeeds."""

    model_config = ConfigDict(str_strip_whitespace=True)

    street: str = ""
    city: str = ""
    state: str = ""
    zip_code: str = ""
    country: str = "US"
    latitude: float | None = None
    longitude: float | None = None

    def is_populated(self) -> bool:
        return bool(self.street or self.city or self.state or self.zip_code)


class PersonReference(BaseModel):
    """Shared base for every person-like entity in the schema.

    Natural persons have ``is_entity=False`` and typically populate
    ``date_of_birth``. Legal entities (corporate trustees, charitable
    remainders, insurance companies referenced as entities) have
    ``is_entity=True``, populate ``entity_name``, and omit DOB.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    full_legal_name: str = ""
    date_of_birth: date | None = None
    address: Address | None = None
    phone: str = ""
    email: str = ""
    notes: str = ""
    is_entity: bool = False
    entity_name: str = ""

    @field_validator("full_legal_name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        """Name must be two or more whitespace-separated tokens when populated.

        Empty is permitted (many schema positions accept empty defaults);
        validation fires only when the user supplied something.
        """
        if v and len(v.split()) < 2:
            msg = f"full_legal_name must have two or more tokens; got {v!r}"
            raise ValueError(msg)
        return v

    def is_minor_as_of(self, ref_date: date) -> bool:
        """Return True if this person is a minor as of ``ref_date``.

        Reference date policy (see project memory):
          - Primary: trust execution date
          - Fallback: questionnaire fill date
          - Callers resolve the reference date; this method only computes
        """
        if self.date_of_birth is None or self.is_entity:
            return False
        years = ref_date.year - self.date_of_birth.year
        had_birthday = (ref_date.month, ref_date.day) >= (
            self.date_of_birth.month,
            self.date_of_birth.day,
        )
        age = years if had_birthday else years - 1
        return age < 18


class Diagnostic(BaseModel):
    """Computed observation about a TrustData instance.

    Diagnostics are never persisted on TrustData itself — they are produced
    by ``diagnose(trust: TrustData, config: FirmConfig) -> list[Diagnostic]``
    at the boundaries between fill, generate, and validation stages.
    """

    level: DiagnosticLevel
    code: str
    message: str
    field_path: str | None = None
    source: DiagnosticSource = DiagnosticSource.SCHEMA
    context: DiagnosticContext = DiagnosticContext.BOTH


# ---------------------------------------------------------------------------
# Beneficiary hierarchy
# ---------------------------------------------------------------------------


class Beneficiary(PersonReference):
    """Extends PersonReference with disinheritance election.

    Disinheritance here is intake-as-election only — the trust document
    generator emits a firm-drafted disinheritance clause when ``disinherit``
    is True. This intake does not produce the binding legal statement;
    that lives in the generated document.
    """

    disinherit: bool = False
    disinherit_reason: str = ""


class Child(Beneficiary):
    """A child of one or both grantors.

    Two-axis relationship model:
      - ``relationship`` gives legal nature (biological, adopted, stepchild, foster)
      - ``biological_parent`` attributes biological origin when applicable

    Rationale: a stepchild who is later adopted by the non-biological parent
    has ``relationship = ADOPTED`` (legal status changed) while
    ``biological_parent`` remains the original (biology unchanged).
    Single-axis collapse loses this distinction.
    """

    relationship: _ChildRelationship = _ChildRelationship.BIOLOGICAL
    biological_parent: BiologicalParent | None = None


class Descendant(Beneficiary):
    """A lineal descendant (grandchild, great-grandchild, etc.).

    The descendants table captures lineal blood relatives specifically;
    collaterals (nieces/nephews) and affines (in-laws) belong under
    ``other_beneficiaries`` to preserve the legal definition of "descendant."
    """

    relationship: GenericRelationship = GenericRelationship.GRANDCHILD


class OtherBeneficiary(Beneficiary):
    """Beneficiary who is not a child or lineal descendant.

    Uses a free-form relationship string alongside the enum to allow
    unusual relationships that don't fit GenericRelationship values
    (e.g., "longtime caregiver", "godchild").
    """

    relationship: GenericRelationship | None = None
    relationship_other: str = ""


# ---------------------------------------------------------------------------
# Trustee hierarchy
# ---------------------------------------------------------------------------


class SuccessorTrustee(PersonReference):
    """A successor trustee in the chain of succession.

    Position in the succession chain is computed from list index, never stored.
    Relationship uses the TrusteeRelationship type alias (generic + scoped
    values united).
    """

    # TrusteeRelationship is a type alias; the runtime field accepts either
    # GenericRelationship or _TrusteeRelationship instances.
    relationship: GenericRelationship | _TrusteeRelationship = (
        _TrusteeRelationship.FRIEND
    )
    relationship_detail: str = ""
    compensation_override: str = ""


class CorporateTrustee(PersonReference):
    """A legal-entity trustee, typically a bank's trust department.

    Populated from the SQLite-cached FDIC catalog when available;
    falls back to free-text entry when the entity is not in the catalog.
    """

    is_entity: bool = True
    fdic_cert_id: str | None = None
    has_trust_powers: bool = True
    last_verified: date | None = None


# ---------------------------------------------------------------------------
# Grantor identity
# ---------------------------------------------------------------------------


class GrantorInfo(PersonReference):
    """Grantor personal information.

    SSN is collected as last-four digits only (data minimization principle).
    Full SSN lives in the EIN application workflow, not the trust tool.
    """

    ssn_last_four: str = ""
    citizenship: str = "US"
    occupation: str = ""
    employer: str = ""
    maiden_name: str = ""

    @field_validator("ssn_last_four")
    @classmethod
    def _validate_ssn_last_four(cls, v: str) -> str:
        if v and (len(v) != 4 or not v.isdigit()):
            msg = f"ssn_last_four must be exactly four digits; got {v!r}"
            raise ValueError(msg)
        return v


# ---------------------------------------------------------------------------
# Trust identity and firm tracking
# ---------------------------------------------------------------------------


class TrustIdentity(BaseModel):
    """Trust identification, jurisdiction, and tax-ID election.

    ``grantor_caption`` and ``co_grantor_caption`` are first-class fields —
    the generator reads them rather than deriving from trust_type alone.
    This lets the firm override captions if local convention differs.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    trust_type: TrustType = TrustType.JOINT
    marital_status: MaritalStatus = MaritalStatus.MARRIED
    desired_trust_name: str = ""
    execution_date: date | None = None
    state_of_governing_law: str = "Illinois"
    county_of_execution: str = ""
    tax_id_ssn_preference: SsnOwner = SsnOwner.GRANTOR
    grantor_caption: str = "Grantor"
    co_grantor_caption: str = "Spouse"


class MarriageInfo(BaseModel):
    """Marriage facts. Present when marital_status == MARRIED."""

    date_of_marriage: date | None = None
    state_of_marriage: str = ""
    is_first_marriage_both: bool = True
    prior_marriages: str = ""
    prenuptial_agreement: bool = False
    prenuptial_details: str = ""


class OfficeInfo(BaseModel):
    """Internal firm tracking fields."""

    file_number: str = ""
    attorney: str = ""
    paralegal: str = ""
    date_opened: date | None = None


# ---------------------------------------------------------------------------
# Asset models
# ---------------------------------------------------------------------------
#
# Real property is collected unconditionally. The other five asset types
# are gated on estate_value_estimate: collected when ABOVE_THRESHOLD or
# DECLINED_TO_ESTIMATE; skipped when BELOW_THRESHOLD.


class RealProperty(BaseModel):
    address: Address = Field(default_factory=Address)
    value: Decimal = Decimal(0)
    equity: Decimal = Decimal(0)
    transfer: str = ""
    value_as_of: date | None = None


class FinancialAccount(BaseModel):
    institution: str = ""
    account_type: str = ""
    value: Decimal = Decimal(0)
    owner: str = ""
    designation: str = ""
    value_as_of: date | None = None


class Vehicle(BaseModel):
    description: str = ""
    vin: str = ""
    value: Decimal = Decimal(0)
    owner: str = ""
    transfer: str = ""


class InsurancePolicy(BaseModel):
    company: PersonReference = Field(
        default_factory=lambda: PersonReference(is_entity=True)
    )
    policy_number: str = ""
    benefit: Decimal = Decimal(0)
    insured: str = ""
    beneficiary: str = ""


class Pension(BaseModel):
    source: PersonReference = Field(
        default_factory=lambda: PersonReference(is_entity=True)
    )
    pension_type: str = ""
    value: Decimal = Decimal(0)
    owner: str = ""
    survivor: str = ""


class Valuable(BaseModel):
    description: str = ""
    value: Decimal = Decimal(0)
    owner: str = ""
    specific_bequest: str = ""


# ---------------------------------------------------------------------------
# Distribution models — reference-by-id pattern
# ---------------------------------------------------------------------------


class BeneficiaryShare(BaseModel):
    """A share of the trust's residuary distribution.

    Recipients are referenced by id into the TrustData's people lists
    (children, descendants, other_beneficiaries). External recipients
    (charities, non-enumerated persons) use ``recipient_external``.

    Exactly one of recipient_ref or recipient_external must be populated.
    """

    recipient_ref: str | None = None
    recipient_external: PersonReference | None = None
    share_percent: Decimal = Decimal(0)
    conditions: str = ""

    @model_validator(mode="after")
    def _validate_recipient(self) -> BeneficiaryShare:
        if self.recipient_ref is None and self.recipient_external is None:
            msg = "BeneficiaryShare requires recipient_ref or recipient_external"
            raise ValueError(msg)
        if self.recipient_ref is not None and self.recipient_external is not None:
            msg = "BeneficiaryShare: specify recipient_ref OR recipient_external, not both"
            raise ValueError(msg)
        return self


class SpecificBequest(BaseModel):
    """A specific bequest of property to a named recipient.

    Same ref-or-external pattern as BeneficiaryShare.
    """

    item: str = ""
    recipient_ref: str | None = None
    recipient_external: PersonReference | None = None
    instructions: str = ""

    @model_validator(mode="after")
    def _validate_recipient(self) -> SpecificBequest:
        if self.recipient_ref is None and self.recipient_external is None:
            msg = "SpecificBequest requires recipient_ref or recipient_external"
            raise ValueError(msg)
        if self.recipient_ref is not None and self.recipient_external is not None:
            msg = (
                "SpecificBequest: specify recipient_ref OR recipient_external, not both"
            )
            raise ValueError(msg)
        return self


class WithdrawalStep(BaseModel):
    """An age-staggered withdrawal allocation.

    Example: age=25, percent=Decimal("25.00"), description="First withdrawal"
    """

    age: int
    percent: Decimal
    description: str = ""


# ---------------------------------------------------------------------------
# Pet and guardianship models
# ---------------------------------------------------------------------------


class Pet(BaseModel):
    """Pet-trust data under Illinois 760 ILCS 3/408.

    Caretaker references point into the TrustData's people lists
    (typically a beneficiary or trustee).
    """

    name: str = ""
    species: str = ""
    distinguishing_features: str = ""
    microchip_id: str = ""
    designated_caretaker_ref: str = ""
    successor_caretaker_ref: str | None = None
    care_instructions: str = ""
    funding_amount: Decimal | None = None
    annual_allowance: Decimal | None = None
    residual_distribution: str = ""


class GuardianshipDesignation(BaseModel):
    """Guardianship designation for a minor beneficiary.

    Only populated when Elections.guardianship_policy == EXPLICIT_DESIGNATIONS.
    Distinguishes guardian-of-person (physical care) from
    guardian-of-estate (property management). The two may be the same person
    or different.
    """

    minor_child_ref: str
    guardian_of_person_ref: str
    successor_guardian_of_person_ref: str | None = None
    guardian_of_estate_ref: str
    successor_guardian_of_estate_ref: str | None = None
    instructions: str = ""


class DigitalAssetDirective(BaseModel):
    """Directive for digital asset handling under Illinois RUFADAA (755 ILCS 70)."""

    asset_type: DigitalAssetType
    service_provider: str = ""
    access_instruction: DigitalAssetAccess
    notes: str = ""


# ---------------------------------------------------------------------------
# Custom terms and text blocks
# ---------------------------------------------------------------------------


class CustomTerm(BaseModel):
    """A categorized custom provision to be reviewed and placed by attorney.

    Replaces v2.2's three separate text block fields (custom_distribution_terms,
    custom_beneficiary_terms, additional_notes). Category tagging lets the
    generator surface each term into the correct article of the trust document.
    """

    category: CustomTermCategory
    content: str
    manual_review: bool = True


class TextBlocks(BaseModel):
    """Freeform narrative text blocks.

    Scope reduction from v2.2:
      - ``exclusions`` REMOVED (superseded by Beneficiary.disinherit)
      - three custom-text fields COLLAPSED into ``custom_terms`` on TrustData
      - ``incapacity_provisions`` ADDED as new v3 field
    """

    statement_of_intent: str = ""
    personal_message: str = ""
    incapacity_provisions: str = ""


# ---------------------------------------------------------------------------
# Elections — unified model for Sections 3C, 6, 7, 8, 9, 10
# ---------------------------------------------------------------------------


class Elections(BaseModel):
    """All checkbox-driven and enum-driven trust configuration.

    Defaults reflect Illinois-law common practice, with the most
    protective choice selected where options differ in client protection.
    """

    # Section 3A — initial trustee composition
    initial_trustee: InitialTrustee = InitialTrustee.GRANTORS

    # Section 3C — trustee powers
    allow_trustee_coappoint: bool = False
    allow_corporate_fiduciary: bool = False
    corporate_fiduciary_min_capital: Decimal = Decimal(50000)

    # Section 4 gating
    estate_value_estimate: EstateValueRange = EstateValueRange.BELOW_THRESHOLD
    estate_value_approximate: Decimal | None = None

    # Property classification
    property_classification: PropertyClassification = PropertyClassification.COMMUNAL

    # Section 5 — distribution standard
    distribution_standard: DistributionStandard = DistributionStandard.HEMS

    # Section 6 — contingencies
    beneficiary_death: BeneficiaryDeath = BeneficiaryDeath.PER_STIRPES_BENEFICIARY
    remote_contingent: RemoteContingent = RemoteContingent.INTESTACY
    remote_contingent_other: str = ""

    # Section 7 — tangible property
    tangible_distribution: TangibleDistribution = TangibleDistribution.EQUAL_CHILDREN
    division_method: DivisionMethod = DivisionMethod.TRUSTEE

    # Section 8 — special assets
    retirement_strategy: RetirementStrategy = RetirementStrategy.POD
    insurance_strategy: InsuranceStrategy = InsuranceStrategy.SPOUSE_THEN_CHILDREN
    insurance_strategy_other: str = ""

    # Section 9 — protective elections
    surviving_amendment: SurvivingAmendment = SurvivingAmendment.FULL
    power_of_appointment: PowerOfAppointment = PowerOfAppointment.GENERAL
    no_contest: bool = True
    spendthrift: bool = True
    probate_coordination: bool = True
    portability: bool = True
    trustee_bond: bool = False

    # Section 10 — trustee terms
    dispute_resolution: DisputeResolution = DisputeResolution.MEDIATION_ARBITRATION
    trustee_compensation: TrusteeCompensation = TrusteeCompensation.REASONABLE
    trustee_compensation_amount: Decimal | None = None
    trustee_compensation_other: str = ""

    # Guardianship and digital asset policies
    guardianship_policy: GuardianshipPolicy = GuardianshipPolicy.EXPLICIT_DESIGNATIONS
    digital_assets_handling: Literal["include_default", "opt_in_per_client", "omit"] = (
        "include_default"
    )


# ---------------------------------------------------------------------------
# Root model: QuestionnaireSeed
# ---------------------------------------------------------------------------


class QuestionnaireSeed(BaseModel):
    """Consultation-captured metadata that drives the tailored printable.

    This is a DISTINCT bounded context from TrustData. It carries concerns
    that belong to the questionnaire generation workflow (paralegal identity,
    print options) and a narrow subset of facts that project forward into
    TrustData (trust_type, marital_status, child-count tier, possibly a
    preliminary trust name).

    The ``promote_seed()`` function is the canonical one-way translation.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    # Fields that project forward into TrustData
    trust_type: TrustType = TrustType.JOINT
    marital_status: MaritalStatus = MaritalStatus.MARRIED
    estate_value_estimate: EstateValueRange = EstateValueRange.BELOW_THRESHOLD
    child_count_tier: ChildCountTier = ChildCountTier.NONE
    preliminary_trust_name: str = ""
    has_pets: bool = False

    # Seed-only fields, NOT projected into TrustData
    consultation_date: date | None = None
    paralegal_name: str = ""
    attorney_name: str = ""
    accessibility_overrides: dict[str, str] = Field(default_factory=dict)
    # accessibility_overrides keys: "font_size", "line_spacing", "contrast"
    # populated when the client has specific accessibility needs beyond defaults

    # Derived variant identifier (computed, not stored in parsed form)
    @property
    def variant_key(self) -> str:
        """The 18-variant key composed from base + child-count.

        Example: "joint_married_above_one_to_five" selects variant for
        joint trust, married grantors, above-threshold assets, 1-5 children.
        """
        base = f"{self.trust_type.value}_{self.marital_status.value}"
        return (
            f"{base}_{self.estate_value_estimate.value}_{self.child_count_tier.value}"
        )


# ---------------------------------------------------------------------------
# Root model: TrustData
# ---------------------------------------------------------------------------


class TrustData(BaseModel):
    """The canonical post-fill model.

    Every input parser produces a TrustData instance. Every output
    generator consumes one. The diagnostic engine inspects one. The GUI
    edits one.
    """

    model_config = ConfigDict(str_strip_whitespace=True, populate_by_name=True)

    # Trust identity
    trust_id: TrustIdentity = Field(default_factory=TrustIdentity)
    office: OfficeInfo = Field(default_factory=OfficeInfo)

    # People — grantor always present; co_grantor present when joint
    # or individual+married
    grantor: GrantorInfo = Field(default_factory=GrantorInfo)
    co_grantor: GrantorInfo | None = None
    marriage: MarriageInfo = Field(default_factory=MarriageInfo)

    # Family — Section 2
    children: list[Child] = Field(default_factory=list)
    descendants: list[Descendant] = Field(default_factory=list)
    other_beneficiaries: list[OtherBeneficiary] = Field(default_factory=list)
    pets: list[Pet] = Field(default_factory=list)

    # Succession — Section 3
    successor_trustees: list[SuccessorTrustee | CorporateTrustee] = Field(
        default_factory=list
    )
    initial_trustee_other: SuccessorTrustee | None = None

    # Guardianship — Section 3, conditional on Elections.guardianship_policy
    guardianship_designations: list[GuardianshipDesignation] = Field(
        default_factory=list
    )

    # Assets — Section 4
    real_property: list[RealProperty] = Field(default_factory=list)
    financial_accounts: list[FinancialAccount] = Field(default_factory=list)
    vehicles: list[Vehicle] = Field(default_factory=list)
    insurance_policies: list[InsurancePolicy] = Field(default_factory=list)
    pensions: list[Pension] = Field(default_factory=list)
    valuables: list[Valuable] = Field(default_factory=list)

    # Distribution — Section 5
    beneficiary_shares: list[BeneficiaryShare] = Field(default_factory=list)
    specific_bequests: list[SpecificBequest] = Field(default_factory=list)

    # Contingencies — Section 6
    withdrawal_schedule: list[WithdrawalStep] = Field(default_factory=list)
    remote_contingent_charity: PersonReference | None = None

    # Digital assets — Section 9 extension
    digital_asset_directives: list[DigitalAssetDirective] = Field(default_factory=list)

    # Elections and text
    elections: Elections = Field(default_factory=Elections)
    text_blocks: TextBlocks = Field(default_factory=TextBlocks)
    custom_terms: list[CustomTerm] = Field(default_factory=list)

    # Section 11 — external exclusions (persons not in the beneficiary lists)
    external_exclusions: list[PersonReference] = Field(default_factory=list)
    external_exclusion_reasons: dict[str, str] = Field(default_factory=dict)
    # keyed by PersonReference.full_legal_name

    # -----------------------------------------------------------------------
    # Computed properties
    # -----------------------------------------------------------------------

    @property
    def trust_name(self) -> str:
        """Desired name, or a fallback derived from the grantor's surname."""
        if self.trust_id.desired_trust_name:
            return self.trust_id.desired_trust_name
        name = self.grantor.full_legal_name
        if name:
            surname = name.split()[-1]
            return f"The {surname.capitalize()} Family Trust"
        return "[TRUST NAME]"

    @property
    def trust_date(self) -> date | None:
        return self.trust_id.execution_date

    @property
    def grantor_full_name(self) -> str:
        return self.grantor.full_legal_name or "[GRANTOR NAME]"

    @property
    def co_grantor_full_name(self) -> str:
        if self.co_grantor is None:
            return ""
        return self.co_grantor.full_legal_name or "[CO-GRANTOR NAME]"

    @property
    def grantor_display_name(self) -> str:
        """Caption-prefixed grantor name for display in generated artifacts."""
        caption = self.trust_id.grantor_caption
        return f"{caption}: {self.grantor_full_name}"

    @property
    def co_grantor_display_name(self) -> str:
        if self.co_grantor is None:
            return ""
        caption = self.trust_id.co_grantor_caption
        return f"{caption}: {self.co_grantor_full_name}"

    @property
    def grantors_combined_name(self) -> str:
        """Joint display: "X and Y" when co-grantor present, "X" alone otherwise."""
        if self.co_grantor is None:
            return self.grantor_full_name
        return f"{self.grantor_full_name} and {self.co_grantor_full_name}"

    @property
    def ssn_owner_name(self) -> str:
        """Name of the person whose SSN serves as trust tax ID."""
        if self.trust_id.tax_id_ssn_preference == SsnOwner.GRANTOR:
            return self.grantor_full_name
        return self.co_grantor_full_name

    @property
    def county(self) -> str:
        return self.trust_id.county_of_execution or "[COUNTY]"

    @property
    def state(self) -> str:
        return self.trust_id.state_of_governing_law or "Illinois"

    @property
    def collected_total_value(self) -> Decimal:
        """Sum of all collected asset values. Used by diagnostic rules."""
        total = Decimal(0)
        total += sum((p.value for p in self.real_property), Decimal(0))
        total += sum((a.value for a in self.financial_accounts), Decimal(0))
        total += sum((v.value for v in self.vehicles), Decimal(0))
        total += sum((p.benefit for p in self.insurance_policies), Decimal(0))
        total += sum((p.value for p in self.pensions), Decimal(0))
        total += sum((v.value for v in self.valuables), Decimal(0))
        return total

    @property
    def beneficiary_shares_total(self) -> Decimal:
        return sum((s.share_percent for s in self.beneficiary_shares), Decimal(0))

    @property
    def withdrawal_schedule_total(self) -> Decimal:
        return sum((w.percent for w in self.withdrawal_schedule), Decimal(0))

    @property
    def disinherited_beneficiaries(self) -> list[Beneficiary]:
        """Aggregated list of all disinherited beneficiaries across Section 2 lists.

        Used by Section 11's computed summary and by the trust document generator
        to emit appropriate disinheritance clauses.
        """
        result: list[Beneficiary] = []
        result.extend(c for c in self.children if c.disinherit)
        result.extend(d for d in self.descendants if d.disinherit)
        result.extend(b for b in self.other_beneficiaries if b.disinherit)
        return result

    @property
    def excluded_persons(self) -> list[PersonReference]:
        """Union of disinherited beneficiaries and external exclusions.

        For trust document generation: the clause "I intentionally exclude..."
        iterates this list.
        """
        return [*self.disinherited_beneficiaries, *self.external_exclusions]

    def minor_beneficiaries(self, ref_date: date) -> list[Beneficiary]:
        """List of beneficiaries who are minors as of ``ref_date``.

        Reference date policy: trust_id.execution_date preferred; caller
        supplies fallback (typically questionnaire-fill date).
        """
        candidates: list[Beneficiary] = [
            *self.children,
            *self.descendants,
            *self.other_beneficiaries,
        ]
        return [b for b in candidates if b.is_minor_as_of(ref_date)]

    def asset_summary(self) -> list[str]:
        """Human-readable asset list for inclusion in generated artifacts.

        Returns a placeholder when no assets have been collected, making
        missing data visible in draft output rather than silently empty.
        """
        items: list[str] = []
        for real_property in self.real_property:
            label = "Real property"
            if real_property.address.is_populated():
                parts = [real_property.address.street, real_property.address.city]
                label = f"Real property at {', '.join(s for s in parts if s)}"
            if real_property.equity:
                label += f" (equity: ${real_property.equity:,.2f})"
            items.append(label)
        for account in self.financial_accounts:
            label = account.account_type or "Financial account"
            if account.institution:
                label = f"{label} at {account.institution}"
            if account.value:
                label += f" (value: ${account.value:,.2f})"
            items.append(label)
        for vehicle in self.vehicles:
            label = (
                f"Vehicle: {vehicle.description}" if vehicle.description else "Vehicle"
            )
            if vehicle.value:
                label += f" (value: ${vehicle.value:,.2f})"
            items.append(label)
        for policy in self.insurance_policies:
            company = (
                policy.company.entity_name
                or policy.company.full_legal_name
                or "insurer"
            )
            label = f"Life insurance with {company}"
            if policy.benefit:
                label += f" (benefit: ${policy.benefit:,.2f})"
            items.append(label)
        for pension in self.pensions:
            source = pension.source.entity_name or pension.source.full_legal_name
            label = pension.pension_type or "Pension"
            if source:
                label = f"{label} from {source}"
            if pension.value:
                label += f" (value: ${pension.value:,.2f})"
            items.append(label)
        for valuable in self.valuables:
            label = valuable.description or "Valuable item"
            if valuable.value:
                label += f" (value: ${valuable.value:,.2f})"
            items.append(label)
        return items or ["[...ASSETS]"]


# ---------------------------------------------------------------------------
# Seed-to-TrustData promotion
# ---------------------------------------------------------------------------


def _resolve_captions(trust_type: TrustType) -> tuple[str, str]:
    """Default captions for (grantor_caption, co_grantor_caption) given trust_type.

    Used by promote_seed at initialization and by the parser when fill
    mutates trust_id.trust_type post-promotion. Firm-custom captions
    in firm_config override these defaults at application time.
    """
    if trust_type == TrustType.JOINT:
        return ("Grantor A", "Grantor B")
    return ("Grantor", "Spouse")


def promote_seed(seed: QuestionnaireSeed) -> TrustData:
    """Translate consultation-captured seed metadata into an initial TrustData.

    This is the bounded-context translation and a ONE-SHOT INITIALIZER.
    It is called exactly once per trust, at TrustData creation. Re-invocation
    on an already-populated TrustData produces a fresh instance and silently
    discards fill state; callers must not do so.

    Post-promotion seed edits (paralegal corrects preliminary_trust_name;
    attorney changes trust_type after consultation review) are the parser's
    responsibility. For edits affecting captions or co_grantor materialization,
    use the `_resolve_captions()` helper rather than re-promoting.

    Seed fields with a TrustData counterpart project forward; seed-only
    concerns (paralegal identity, print options, accessibility overrides)
    are dropped. Fields not populated by the seed default to TrustData's own
    defaults — nothing is fabricated.

    Notably NOT projected:
      - ``consultation_date``, ``paralegal_name``, ``attorney_name``
      - ``accessibility_overrides`` (printable generator concern)
      - ``has_pets`` (printable signal; Pet list built during fill)
      - ``child_count_tier`` (printable layout signal; children enumerated during fill)
    """
    data = TrustData()
    data.trust_id.trust_type = seed.trust_type
    data.trust_id.marital_status = seed.marital_status
    data.trust_id.desired_trust_name = seed.preliminary_trust_name
    data.elections.estate_value_estimate = seed.estate_value_estimate

    grantor_caption, co_grantor_caption = _resolve_captions(seed.trust_type)
    data.trust_id.grantor_caption = grantor_caption
    data.trust_id.co_grantor_caption = co_grantor_caption

    # co_grantor is present when joint, or individual+married.
    # It remains None when individual+unmarried.
    if (
        seed.trust_type == TrustType.JOINT
        or seed.marital_status == MaritalStatus.MARRIED
    ):
        data.co_grantor = GrantorInfo()

    return data


# ---------------------------------------------------------------------------
# Public exports
# ---------------------------------------------------------------------------

__all__ = [
    "Address",
    "Beneficiary",
    "BeneficiaryDeath",
    "BeneficiaryShare",
    "BiologicalParent",
    "Child",
    "ChildCountTier",
    "ChildRelationship",
    "CorporateTrustee",
    "CustomTerm",
    "CustomTermCategory",
    "Descendant",
    "DescendantRelationship",
    "Diagnostic",
    "DiagnosticContext",
    "DiagnosticLevel",
    "DiagnosticSource",
    "DigitalAssetAccess",
    "DigitalAssetDirective",
    "DigitalAssetType",
    "DisputeResolution",
    "DistributionStandard",
    "DivisionMethod",
    "Elections",
    "EstateValueRange",
    "FinancialAccount",
    "GenericRelationship",
    "GrantorInfo",
    "GuardianshipDesignation",
    "GuardianshipPolicy",
    "InitialTrustee",
    "InsurancePolicy",
    "InsuranceStrategy",
    "MaritalStatus",
    "MarriageInfo",
    "OfficeInfo",
    "OtherBeneficiary",
    "Pension",
    "PersonReference",
    "Pet",
    "PowerOfAppointment",
    "PropertyClassification",
    "QuestionnaireSeed",
    "RealProperty",
    "RemoteContingent",
    "RetirementStrategy",
    "SpecificBequest",
    "SsnOwner",
    "SuccessorTrustee",
    "SurvivingAmendment",
    "TangibleDistribution",
    "TextBlocks",
    "TrustData",
    "TrustIdentity",
    "TrustType",
    "TrusteeCompensation",
    "TrusteeRelationship",
    "Valuable",
    "Vehicle",
    "WithdrawalStep",
    "promote_seed",
]
