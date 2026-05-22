"""
Canonical data schema for trust document generation.

Every input parser must produce a TrustData instance.
Every output generator must consume a TrustData instance.
The validation layer inspects TrustData for completeness and consistency.

The field set here preserves every piece of information collected by the
original Trust Intake Questionnaire — no fields were dropped or renamed
without reason.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from enum import Enum
from operator import attrgetter

from pydantic import BaseModel, ConfigDict, Field, field_validator

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Enumerations for checkbox elections
# ---------------------------------------------------------------------------


class InitialTrustee(str, Enum):
    BOTH = "both"
    PARTY_A = "husband"  # value preserved for backward compat
    PARTY_B = "wife"  # value preserved for backward compat


class TrustType(str, Enum):
    JOINT = "joint"
    INDIVIDUAL = "individual"


class SsnOwner(str, Enum):
    PARTY_A = "party_a"
    PARTY_B = "party_b"
    GRANTOR = "grantor"


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


class RetirementStrategy(str, Enum):
    POD = "pod"
    TRUST = "trust"
    MIX = "mix"


class InsuranceStrategy(str, Enum):
    SPOUSE_THEN_CHILDREN = "spouse_then_children"


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
    NONE = "none"


# ---------------------------------------------------------------------------
# Sub-models for structured data
# ---------------------------------------------------------------------------


class PersonInfo(BaseModel):
    """Grantor (husband or wife) personal information."""

    full_legal_name: str = ""
    date_of_birth: str = ""
    ssn: str = ""
    address: str = ""
    phone: str = ""
    email: str = ""
    employer: str = ""
    # Wife-specific fields
    maiden_name: str = ""


class TrustIdentity(BaseModel):
    """Trust identification and jurisdiction."""

    desired_trust_name: str = ""
    date: str = ""
    state_of_governing_law: str = ""
    county_of_execution: str = ""
    whose_ssn_for_tax_id: SsnOwner = SsnOwner.PARTY_A

    @field_validator("whose_ssn_for_tax_id", mode="before")
    @classmethod
    def _coerce_ssn_owner(cls, v: object) -> object:
        if isinstance(v, str):
            if not v:
                return SsnOwner.PARTY_A
            mapping = {
                "wife": SsnOwner.PARTY_B,
                "husband": SsnOwner.PARTY_A,
                "grantor": SsnOwner.GRANTOR,
            }
            return mapping.get(v.lower(), v)
        return v


class MarriageInfo(BaseModel):
    """Marriage details (parsed but available for future use)."""

    date_of_marriage: str = ""
    state_of_marriage: str = ""
    prenuptial_agreement: str = ""
    prenuptial_details: str = ""


class OfficeInfo(BaseModel):
    """Internal firm tracking fields."""

    file_number: str = ""
    attorney: str = ""
    paralegal: str = ""
    date_opened: str = ""


class Child(BaseModel):
    """A child of the grantors."""

    name: str
    dob: str = ""
    relationship: str = ""
    minor: str = ""
    notes: str = ""


class SuccessorTrustee(BaseModel):
    """A successor trustee in the chain of succession."""

    order: str
    name: str
    relationship: str = ""
    contact: str = ""


class RealProperty(BaseModel):
    address: str = ""
    value: str = ""
    equity: str = ""
    transfer: str = ""


class FinancialAccount(BaseModel):
    institution: str = ""
    type: str = ""
    value: str = ""
    owner: str = ""
    designation: str = ""


class Vehicle(BaseModel):
    description: str = ""
    vin: str = ""
    value: str = ""
    owner: str = ""
    transfer: str = ""


class InsurancePolicy(BaseModel):
    company: str = ""
    policy_number: str = ""
    benefit: str = ""
    insured: str = ""
    beneficiary: str = ""


class Pension(BaseModel):
    source: str = ""
    type: str = ""
    value: str = ""
    owner: str = ""
    survivor: str = ""


class Valuable(BaseModel):
    description: str = ""
    value: str = ""
    owner: str = ""
    specific_bequest: str = ""


class BeneficiaryShare(BaseModel):
    name: str
    relationship: str = ""
    share: str = ""
    conditions: str = ""


class SpecificBequest(BaseModel):
    item: str
    recipient: str
    instructions: str = ""


class WithdrawalStep(BaseModel):
    step: str = ""
    timing: str = ""
    percentage: str = ""


class OtherBeneficiary(BaseModel):
    name: str
    relationship: str = ""
    dob: str = ""
    notes: str = ""


# ---------------------------------------------------------------------------
# Elections — checkbox-driven trust configuration
# ---------------------------------------------------------------------------


class Elections(BaseModel):
    """All checkbox-driven trust configuration options.

    Defaults here match the Illinois-law defaults from the original parser.
    Each field defaults to the most common / protective choice.
    """

    initial_trustee: InitialTrustee = InitialTrustee.BOTH
    property_classification: PropertyClassification = PropertyClassification.COMMUNAL
    tangible_distribution: TangibleDistribution = TangibleDistribution.EQUAL_CHILDREN
    division_method: DivisionMethod = DivisionMethod.TRUSTEE
    distribution_standard: DistributionStandard = DistributionStandard.HEMS
    beneficiary_death: BeneficiaryDeath = BeneficiaryDeath.PER_STIRPES_BENEFICIARY
    remote_contingent: RemoteContingent = RemoteContingent.INTESTACY
    remote_contingent_charity: str = ""
    retirement_strategy: RetirementStrategy = RetirementStrategy.POD
    insurance_strategy: InsuranceStrategy = InsuranceStrategy.SPOUSE_THEN_CHILDREN
    surviving_amendment: SurvivingAmendment = SurvivingAmendment.FULL
    power_of_appointment: PowerOfAppointment = PowerOfAppointment.GENERAL
    # Boolean elections — these default to True but ARE opt-out-able
    no_contest: bool = True
    spendthrift: bool = True
    probate_coordination: bool = True
    portability: bool = True
    trustee_bond: bool = False
    dispute_resolution: DisputeResolution = DisputeResolution.MEDIATION_ARBITRATION
    trustee_compensation: TrusteeCompensation = TrusteeCompensation.REASONABLE


# ---------------------------------------------------------------------------
# Freeform text blocks
# ---------------------------------------------------------------------------


class TextBlocks(BaseModel):
    """Freeform text sections that get MANUAL REVIEW flags in output."""

    statement_of_intent: str = ""
    personal_message: str = ""
    custom_distribution_terms: str = ""
    custom_beneficiary_terms: str = ""
    additional_notes: str = ""


# ---------------------------------------------------------------------------
# Root schema
# ---------------------------------------------------------------------------


class TrustData(BaseModel):
    """Complete trust intake data.

    This is the single type that flows through the entire pipeline:
    parsers produce it, validators inspect it, the GUI displays/edits it,
    and generators consume it.
    """

    model_config = ConfigDict(populate_by_name=True)

    def get_or_default(
        self,
        *field_path: str,
        default: str | Callable[[], str | None] | None = None,
    ) -> str:
        getter = attrgetter(".".join(field_path))

        def _default():
            nonlocal default
            if callable(default):
                default = default()
            return default or "[MISSING]"

        try:
            current: object = getter(self) or _default()
        except AttributeError:
            log.warning(
                "Field path %r not found on TrustData — returning default",
                ".".join(field_path),
                exc_info=True,
            )
            return _default()
        else:
            if isinstance(current, str):
                return current
            msg = f"expected {str!r}; received {type(current)!r}"
            raise TypeError(msg)

    # Trust type (joint vs individual)
    trust_type: TrustType = TrustType.JOINT
    grantor: PersonInfo = Field(default_factory=PersonInfo)

    # People
    party_a: PersonInfo = Field(default_factory=PersonInfo, validation_alias="husband")
    party_b: PersonInfo = Field(default_factory=PersonInfo, validation_alias="wife")
    party_a_label: str = "Husband"
    party_b_label: str = "Wife"
    marriage: MarriageInfo = Field(default_factory=MarriageInfo)

    # Trust identity and firm info
    trust_id: TrustIdentity = Field(default_factory=TrustIdentity)
    office: OfficeInfo = Field(default_factory=OfficeInfo)

    # Family
    children: list[Child] = Field(default_factory=list)

    # Succession
    successor_trustees: list[SuccessorTrustee] = Field(default_factory=list)

    # Assets (6 categories)
    real_property: list[RealProperty] = Field(default_factory=list)
    financial_accounts: list[FinancialAccount] = Field(default_factory=list)
    vehicles: list[Vehicle] = Field(default_factory=list)
    insurance_policies: list[InsurancePolicy] = Field(default_factory=list)
    pensions: list[Pension] = Field(default_factory=list)
    valuables: list[Valuable] = Field(default_factory=list)

    # Beneficiaries and distribution
    beneficiary_shares: list[BeneficiaryShare] = Field(default_factory=list)
    specific_bequests: list[SpecificBequest] = Field(default_factory=list)
    withdrawal_schedule: list[WithdrawalStep] = Field(default_factory=list)
    other_beneficiaries: list[OtherBeneficiary] = Field(default_factory=list)

    # Elections and text
    elections: Elections = Field(default_factory=Elections)
    text_blocks: TextBlocks = Field(default_factory=TextBlocks)

    # --- Computed helpers used by the generator ---

    @property
    def trust_name(self) -> str:
        return self.get_or_default(
            "trust_id.desired_trust_name",
            default=lambda: (
                None
                if not (
                    name := (
                        self.grantor
                        if self.trust_type == TrustType.INDIVIDUAL
                        else self.party_a
                    ).full_legal_name
                )
                else f"The {name.split()[-1].capitalize()} Family Trust"
            ),
        )

    @property
    def trust_date(self) -> str:
        return self.get_or_default("trust_id.date")

    @property
    def trustee_names(self) -> str:
        if self.trust_type == TrustType.INDIVIDUAL:
            return self.grantor_name
        match self.elections.initial_trustee:
            case InitialTrustee.BOTH:
                return self.grantor_name
            case InitialTrustee.PARTY_A:
                return self.party_a_name
            case InitialTrustee.PARTY_B:
                return self.get_or_default("party_b.full_legal_name")

    @property
    def ssn_owner_name(self) -> str:
        if self.trust_type == TrustType.INDIVIDUAL:
            return self.get_or_default("grantor", "full_legal_name")
        match self.trust_id.whose_ssn_for_tax_id:
            case SsnOwner.PARTY_B:
                return self.get_or_default("party_b", "full_legal_name")
            case SsnOwner.GRANTOR:
                return self.get_or_default("grantor", "full_legal_name")
            case _:
                return self.get_or_default("party_a", "full_legal_name")

    @property
    def grantor_name(self) -> str:
        if self.trust_type == TrustType.INDIVIDUAL:
            return self.get_or_default("grantor.full_legal_name")
        return " and ".join(
            self.get_or_default(person, "full_legal_name")
            for person in ("party_a", "party_b")
        )

    @property
    def party_a_name(self) -> str:
        return self.get_or_default("party_a.full_legal_name")

    @property
    def party_b_name(self) -> str:
        return self.get_or_default("party_b.full_legal_name")

    @property
    def county(self) -> str:
        return self.get_or_default("trust_id.county_of_execution")

    @property
    def state(self) -> str:
        return self.get_or_default(
            "trust_id.state_of_governing_law",
            default="Illinois",
        )

    def asset_summary(self) -> list[str]:
        """Compile human-readable asset list across all 6 categories."""
        items: list[str] = []
        for p in self.real_property:
            s = f"Real property at {p.address}" if p.address else "Real property"
            if p.equity:
                s += f" (equity: {p.equity})"
            items.append(s)
        for a in self.financial_accounts:
            s = (
                f"{a.type or 'Account'} at {a.institution}"
                if a.institution
                else a.type or "Financial account"
            )
            if a.value:
                s += f" (value: {a.value})"
            items.append(s)
        for v in self.vehicles:
            s = f"Vehicle: {v.description}" if v.description else "Vehicle"
            if v.value:
                s += f" (value: {v.value})"
            items.append(s)
        for p in self.insurance_policies:
            s = (
                f"Life insurance with {p.company}"
                if p.company
                else "Life insurance policy"
            )
            if p.benefit:
                s += f" (benefit: {p.benefit})"
            items.append(s)
        for p in self.pensions:
            s = (
                f"{p.type or 'Pension'} from {p.source}"
                if p.source
                else p.type or "Pension"
            )
            if p.value:
                s += f" (value: {p.value})"
            items.append(s)
        for v in self.valuables:
            s = v.description or "Valuable item"
            if v.value:
                s += f" (value: {v.value})"
            items.append(s)
        return items or ["[...ASSETS]"]
