# Single-Grantor Trust Support — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable the trust generator to produce valid trust documents for single individuals (not just married couples), while preserving full backward compatibility with existing joint-trust behavior.

**Architecture:** Add a `TrustType` enum (`JOINT` | `INDIVIDUAL`) and a `grantor` field to `TrustData`. Computed properties branch on `trust_type`. The validator, generator, parsers, printable questionnaire, GUI, and CLI all gain awareness of the trust type. Existing joint-trust behavior is the default and is unaffected.

**Tech Stack:** Python 3.12+, Pydantic 2, python-docx, pytest

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `src/trust_generator/schema.py` | Add `TrustType` enum, `grantor` field, update computed properties |
| Modify | `src/trust_generator/validators/validate.py` | Branch validation on `trust_type` |
| Modify | `src/trust_generator/generators/trust_document.py` | Branch article text on `trust_type` |
| Modify | `src/trust_generator/generators/printable_questionnaire.py` | Add individual-trust questionnaire variant |
| Modify | `src/trust_generator/parsers/docx_parser.py` | Auto-detect trust type from questionnaire |
| Modify | `src/trust_generator/parsers/json_parser.py` | Accept `trust_type` field (backward compat) |
| Modify | `src/trust_generator/ui/gui.py` | Show trust type in review, hide wife sections for individual |
| Modify | `src/trust_generator/ui/cli.py` | Show trust type in summary output |
| Modify | `tests/test_schema.py` | Tests for new schema fields and computed properties |
| Modify | `tests/test_validators.py` | Tests for individual-trust validation rules |
| Modify | `tests/test_generators.py` | Tests for individual-trust document output |
| Modify | `tests/test_integration.py` | End-to-end individual-trust pipeline test |
| Modify | `tests/test_printable.py` | Test individual-trust printable questionnaire |

---

### Task 1: Add TrustType enum and grantor field to schema

**Files:**
- Modify: `src/trust_generator/schema.py:25-29` (add enum after existing enums)
- Modify: `src/trust_generator/schema.py:275-314` (add field + update computed properties)
- Test: `tests/test_schema.py`

- [ ] **Step 1: Write failing tests for TrustType and grantor field**

Add to `tests/test_schema.py`:

```python
from trust_generator.schema import (
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
        husband=PersonInfo(full_legal_name="John Smith"),
        wife=PersonInfo(full_legal_name="Jane Smith"),
    )
    assert td.grantor_name == "John Smith and Jane Smith"


def test_individual_ssn_owner():
    td = TrustData(
        trust_type=TrustType.INDIVIDUAL,
        grantor=PersonInfo(full_legal_name="Robert Wilson"),
    )
    assert td.ssn_owner_name == "Robert Wilson"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_schema.py -v -x`
Expected: FAIL with `ImportError: cannot import name 'TrustType'`

- [ ] **Step 3: Add TrustType enum to schema.py**

In `src/trust_generator/schema.py`, after the `InitialTrustee` enum (line 28), add:

```python
class TrustType(str, Enum):
    JOINT = "joint"
    INDIVIDUAL = "individual"
```

- [ ] **Step 4: Add grantor field and trust_type to TrustData**

In `src/trust_generator/schema.py`, in the `TrustData` class, add these fields after the class docstring and before `husband`:

```python
    trust_type: TrustType = TrustType.JOINT
    grantor: PersonInfo = Field(default_factory=PersonInfo)
```

- [ ] **Step 5: Update computed properties to branch on trust_type**

Replace the computed properties in `TrustData` (lines 317-398) with:

```python
    @property
    def trust_name(self) -> str:
        if self.trust_id.desired_trust_name:
            return self.trust_id.desired_trust_name
        if self.trust_type == TrustType.INDIVIDUAL:
            last = self.grantor.full_legal_name.split()[-1] if self.grantor.full_legal_name else "Family"
        else:
            last = self.husband.full_legal_name.split()[-1] if self.husband.full_legal_name else "Family"
        return f"The {last} Family Trust"

    @property
    def trust_date(self) -> str:
        if self.trust_id.date:
            return self.trust_id.date
        return datetime.now().strftime("%B %d, %Y")

    @property
    def trustee_names(self) -> str:
        if self.trust_type == TrustType.INDIVIDUAL:
            return self.grantor.full_legal_name or "[GRANTOR FULL NAME]"
        h = self.husband.full_legal_name or "[HUSBAND FULL NAME]"
        w = self.wife.full_legal_name or "[WIFE FULL NAME]"
        match self.elections.initial_trustee:
            case InitialTrustee.BOTH:
                return f"{h} and {w}"
            case InitialTrustee.HUSBAND:
                return h
            case InitialTrustee.WIFE:
                return w

    @property
    def ssn_owner_name(self) -> str:
        if self.trust_type == TrustType.INDIVIDUAL:
            return self.grantor.full_legal_name or "[GRANTOR FULL NAME]"
        who = self.trust_id.whose_ssn_for_tax_id.lower()
        if "wife" in who:
            return self.wife.full_legal_name or "[WIFE FULL NAME]"
        return self.husband.full_legal_name or "[HUSBAND FULL NAME]"

    @property
    def grantor_name(self) -> str:
        """Human-readable grantor name(s) for use in documents."""
        if self.trust_type == TrustType.INDIVIDUAL:
            return self.grantor.full_legal_name or "[GRANTOR FULL NAME]"
        h = self.husband.full_legal_name or "[HUSBAND FULL NAME]"
        w = self.wife.full_legal_name or "[WIFE FULL NAME]"
        return f"{h} and {w}"

    @property
    def husband_name(self) -> str:
        return self.husband.full_legal_name or "[HUSBAND FULL NAME]"

    @property
    def wife_name(self) -> str:
        return self.wife.full_legal_name or "[WIFE FULL NAME]"

    @property
    def county(self) -> str:
        return self.trust_id.county_of_execution or "Winnebago"

    @property
    def state(self) -> str:
        return self.trust_id.state_of_governing_law or "Illinois"

    def asset_summary(self) -> list[str]:
        """Compile human-readable asset list across all 6 categories."""
        items: list[str] = []
        for p in self.real_property:
            s = f"Real property at {p.address}" if p.address else "Real property"
            if p.equity:
                s += f" (equity: {p.equity})"
            items.append(s)
        for a in self.financial_accounts:
            s = f"{a.type or 'Account'} at {a.institution}" if a.institution else a.type or "Financial account"
            if a.value:
                s += f" (value: {a.value})"
            items.append(s)
        for v in self.vehicles:
            s = f"Vehicle: {v.description}" if v.description else "Vehicle"
            if v.value:
                s += f" (value: {v.value})"
            items.append(s)
        for p in self.insurance_policies:
            s = f"Life insurance with {p.company}" if p.company else "Life insurance policy"
            if p.benefit:
                s += f" (benefit: {p.benefit})"
            items.append(s)
        for p in self.pensions:
            s = f"{p.type or 'Pension'} from {p.source}" if p.source else p.type or "Pension"
            if p.value:
                s += f" (value: {p.value})"
            items.append(s)
        for v in self.valuables:
            s = v.description or "Valuable item"
            if v.value:
                s += f" (value: {v.value})"
            items.append(s)
        return items or ["[LIST ASSETS]"]
```

- [ ] **Step 6: Update the existing test import to include TrustType**

In `tests/test_schema.py`, update the import block at the top to add `TrustType`:

```python
from trust_generator.schema import (
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
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_schema.py -v`
Expected: ALL PASS (both new and existing tests)

- [ ] **Step 8: Commit**

```bash
git add src/trust_generator/schema.py tests/test_schema.py
git commit -m "feat: add TrustType enum and grantor field to schema"
```

---

### Task 2: Update validator for individual trusts

**Files:**
- Modify: `src/trust_generator/validators/validate.py:1-301`
- Test: `tests/test_validators.py`

- [ ] **Step 1: Write failing tests for individual-trust validation**

Add to `tests/test_validators.py`:

```python
from trust_generator.schema import (
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
from trust_generator.validators import Severity, validate


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
    """Individual trust with grantor name should pass validation."""
    report = validate(_individual_data())
    assert report.can_generate is True


def test_individual_trust_missing_grantor_name():
    """Individual trust without grantor name should error."""
    data = TrustData(trust_type=TrustType.INDIVIDUAL)
    report = validate(data)
    error_paths = [f.field_path for f in report.errors]
    assert "grantor.full_legal_name" in error_paths


def test_individual_trust_no_wife_error():
    """Individual trust should NOT require wife's name."""
    data = _individual_data()
    report = validate(data)
    error_paths = [f.field_path for f in report.errors]
    assert "wife.full_legal_name" not in error_paths


def test_individual_trust_no_husband_error():
    """Individual trust should NOT require husband's name."""
    data = _individual_data()
    report = validate(data)
    error_paths = [f.field_path for f in report.errors]
    assert "husband.full_legal_name" not in error_paths
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_validators.py::test_individual_trust_can_generate -v -x`
Expected: FAIL (no `TrustType` import or validation logic yet)

- [ ] **Step 3: Update validate() to branch on trust_type**

In `src/trust_generator/validators/validate.py`, update the import to include `TrustType`:

```python
from trust_generator.schema import (
    PropertyClassification,
    RemoteContingent,
    RetirementStrategy,
    TrustData,
    TrustType,
)
```

Then replace the field-level checks section (lines 212-288) of the `validate()` function with:

```python
    # --- Field-level checks ---

    if data.trust_type == TrustType.INDIVIDUAL:
        _check_field(
            report,
            field_path="grantor.full_legal_name",
            label="Grantor's Full Legal Name",
            value=data.grantor.full_legal_name,
            required=True,
        )
    else:
        _check_field(
            report,
            field_path="husband.full_legal_name",
            label="Husband's Full Legal Name",
            value=data.husband.full_legal_name,
            required=True,
        )

        _check_field(
            report,
            field_path="wife.full_legal_name",
            label="Wife's Full Legal Name",
            value=data.wife.full_legal_name,
            required=True,
        )

    _check_field(
        report,
        field_path="trust_id.desired_trust_name",
        label="Desired Trust Name",
        value=data.trust_id.desired_trust_name,
        default_reason="will be derived from grantor's last name",
    )

    _check_field(
        report,
        field_path="trust_id.date",
        label="Trust Date",
        value=data.trust_id.date,
        default_reason="defaults to today's date",
    )

    _check_field(
        report,
        field_path="trust_id.state_of_governing_law",
        label="State of Governing Law",
        value=data.trust_id.state_of_governing_law,
        default_value="Illinois",
        default_reason="firm default jurisdiction",
    )

    _check_field(
        report,
        field_path="trust_id.county_of_execution",
        label="County of Execution",
        value=data.trust_id.county_of_execution,
        default_value="Winnebago",
        default_reason="firm default county",
    )

    # List fields
    _check_list_field(
        report,
        field_path="children",
        label="Children",
        items=data.children,
        warning_message="No children listed",
    )

    _check_list_field(
        report,
        field_path="successor_trustees",
        label="Successor Trustees",
        items=data.successor_trustees,
        warning_message="No successor trustees listed",
    )

    _check_list_field(
        report,
        field_path="beneficiary_shares",
        label="Beneficiary Shares",
        items=data.beneficiary_shares,
        warning_message="No beneficiaries listed",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_validators.py -v`
Expected: ALL PASS (both new and existing tests)

- [ ] **Step 5: Commit**

```bash
git add src/trust_generator/validators/validate.py tests/test_validators.py
git commit -m "feat: branch validation logic on trust_type for individual trusts"
```

---

### Task 3: Update trust document generator for individual trusts

**Files:**
- Modify: `src/trust_generator/generators/trust_document.py`
- Test: `tests/test_generators.py`

This is the largest task. The generator has 12 articles + signatures + schedules. For individual trusts, the key differences are:
- Singular pronouns ("I" instead of "We")
- No wife references
- No surviving-spouse articles (Article 5 becomes incapacity provisions)
- Signature page has one signature line
- No Schedules C/D for separate property (individual has no community/separate distinction)

- [ ] **Step 1: Write failing tests for individual-trust generation**

Add to `tests/test_generators.py`:

```python
from trust_generator.schema import (
    BeneficiaryShare,
    Child,
    Elections,
    PersonInfo,
    PropertyClassification,
    SpecificBequest,
    SuccessorTrustee,
    TrustData,
    TrustIdentity,
    TrustType,
    WithdrawalStep,
)


def _individual_data() -> TrustData:
    """Create a minimally complete individual TrustData for testing."""
    return TrustData(
        trust_type=TrustType.INDIVIDUAL,
        grantor=PersonInfo(full_legal_name="Robert James Wilson"),
        trust_id=TrustIdentity(
            desired_trust_name="The Wilson Family Trust",
            date="March 15, 2026",
        ),
        children=[
            Child(name="Sarah Wilson", dob="05/10/1995"),
        ],
        successor_trustees=[
            SuccessorTrustee(order="1", name="Sarah Wilson", relationship="Daughter"),
        ],
        beneficiary_shares=[
            BeneficiaryShare(name="Sarah Wilson", share="100"),
        ],
    )


def test_individual_generates_valid_docx(tmp_path):
    data = _individual_data()
    path = tmp_path / "individual.docx"
    result = generate_trust_document(data, path)
    assert Path(result).exists()
    doc = Document(result)
    assert len(doc.paragraphs) > 50


def test_individual_contains_all_articles(tmp_path):
    text = _generate_to_text(_individual_data(), tmp_path)
    for i in range(1, 13):
        assert f"Article {i}:" in text, f"Article {i} missing"


def test_individual_contains_grantor_name(tmp_path):
    text = _generate_to_text(_individual_data(), tmp_path)
    assert "Robert James Wilson" in text


def test_individual_no_wife_references(tmp_path):
    text = _generate_to_text(_individual_data(), tmp_path)
    assert "[WIFE FULL NAME]" not in text
    assert "Wife" not in text or "Wife" in "Husband and Wife"  # some generic legal terms ok


def test_individual_uses_singular_pronouns(tmp_path):
    text = _generate_to_text(_individual_data(), tmp_path)
    assert "the \u201cGrantor\u201d" in text
    assert "I intend to create" in text or "I have transferred" in text


def test_individual_single_signature_line(tmp_path):
    text = _generate_to_text(_individual_data(), tmp_path)
    assert "Robert James Wilson, Grantor and Trustee" in text
    # Should not have a second grantor signature
    lines = text.split("\n")
    grantor_sig_count = sum(1 for line in lines if "Grantor and Trustee" in line and "________" not in line and "Robert" in line)
    assert grantor_sig_count >= 1


def test_individual_empty_data_no_crash(tmp_path):
    data = TrustData(trust_type=TrustType.INDIVIDUAL)
    path = tmp_path / "empty_individual.docx"
    generate_trust_document(data, path)
    assert path.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_generators.py::test_individual_generates_valid_docx -v -x`
Expected: FAIL — generator doesn't know about `TrustType` yet

- [ ] **Step 3: Add TrustType import and helper property to _TrustDocGen**

In `src/trust_generator/generators/trust_document.py`, add `TrustType` to the imports:

```python
from trust_generator.schema import (
    BeneficiaryDeath,
    DistributionStandard,
    DisputeResolution,
    PowerOfAppointment,
    PropertyClassification,
    RemoteContingent,
    RetirementStrategy,
    SurvivingAmendment,
    TangibleDistribution,
    TrustData,
    TrusteeCompensation,
    TrustType,
)
```

Add an `is_individual` property to `_TrustDocGen` after the existing convenience aliases:

```python
    @property
    def is_individual(self) -> bool:
        return self.d.trust_type == TrustType.INDIVIDUAL

    @property
    def grantor_label(self) -> str:
        """'Grantor' for individual, 'Grantors' for joint."""
        return "Grantor" if self.is_individual else "Grantors"
```

- [ ] **Step 4: Update _article_1 for individual trusts**

Replace the `_article_1` method with one that branches on `self.is_individual`. The individual version uses:
- "I, [GRANTOR]" instead of "[HUSBAND] and [WIFE] (the 'Grantors')"
- "I intend" instead of "We intend"
- "I have" instead of "We have"
- Section 1.1 lists just the grantor, no spouse mention
- Section 1.7 uses grantor's SSN directly
- Section 1.8 uses singular powers

The joint version remains identical to the current implementation.

Key individual-trust text for Article 1:

```python
    def _article_1(self) -> None:
        self.f.h1("Article 1: Establishing the Trust")
        if self.is_individual:
            grantor = self.d.grantor_name
            self.f.body(
                f"The date of this Trust is {self.trust_date}. The parties are "
                f"{grantor} (the \u201cGrantor\u201d) and "
                f"{self.trustee_names} (the \u201cTrustee\u201d). I have transferred "
                f"certain assets to the Trustee to be held in trust subject to "
                f"this instrument."
            )
            self.f.body(
                f"I intend to create a valid trust under the laws of {self.state}."
            )
        else:
            self.f.body(
                f"The date of this Trust is {self.trust_date}. The parties are "
                f"{self.husband} and {self.wife} (the \u201cGrantors\u201d) and "
                f"{self.trustee_names} (our \u201cTrustee(s)\u201d). We have transferred "
                f"certain assets to our Trustee(s) to be held in trust subject to "
                f"this instrument."
            )
            self.f.body(
                f"We intend to create a valid trust under the laws of {self.state}."
            )
        # ... remainder of Article 1 follows the same pattern
```

Apply the same `if self.is_individual` / `else` branching to each subsection (1.1 through 1.8). The pattern is consistent: replace "we/our/us" with "I/my/me", replace "Grantors" with "Grantor", and remove wife-specific references.

- [ ] **Step 5: Update Articles 2-4 for individual trusts**

Article 2 (Trustee Succession): Replace "either of us" with "I" for individual. Replace "surviving spouse continues" with "successor trustees serve per order listed."

Article 3 (Administration During Our Lives): For individual, simplify to "Administration During My Life." Remove surviving-spouse amendment rights (Section 3.2). Simplify incapacity section.

Article 4 (Administration Upon Death): For individual, simplify — no "surviving and deceased" split. The trust becomes irrevocable upon the grantor's death.

- [ ] **Step 6: Update Article 5 for individual trusts**

For individual trusts, Article 5 should NOT be "The Survivor's Trust" (there is no survivor). Instead, replace with "Incapacity Provisions" — a shorter article covering what happens if the grantor becomes incapacitated (already partially covered in Article 3, so this article can reference Section 3.4 and 3.5 and add any incapacity-specific distribution provisions).

- [ ] **Step 7: Update Articles 6-12 for individual trusts**

These articles are largely the same for both trust types. The main changes:
- Article 6: Replace "Our Trustee" with "the Trustee" and "our" with "the Grantor's"
- Article 12: Section 12.4 (Survivorship Presumption) — for individual trusts, simplify to only the beneficiary 30-day rule (no simultaneous-death provision for spouses)

- [ ] **Step 8: Update _signatures for individual trusts**

For individual trusts, render one signature block instead of two:

```python
    def _signatures(self) -> None:
        self.f.h1("Execution")
        self.f.body(
            f"Executed on {self.trust_date}. Effective when signed."
        )
        self.f.blank(3)
        if self.is_individual:
            self.f.body("________________________________________")
            self.f.body(f"{self.d.grantor_name}, Grantor and Trustee")
        else:
            self.f.body("________________________________________")
            self.f.body(f"{self.husband}, Grantor and Trustee")
            self.f.blank(2)
            self.f.body("________________________________________")
            self.f.body(f"{self.wife}, Grantor and Trustee")
        self.f.blank(2)
        self.f.body(f"STATE OF {self.state.upper()} )")
        self.f.body(") ss.")
        self.f.body(f"COUNTY OF {self.county.upper()} )")
        self.f.blank()
        if self.is_individual:
            self.f.body(
                f"Acknowledged before me on {self.trust_date}, by "
                f"{self.d.grantor_name}, as Grantor and Trustee."
            )
        else:
            self.f.body(
                f"Acknowledged before me on {self.trust_date}, by {self.husband}, "
                f"as Grantor and Trustee, and {self.wife}, as Grantor and Trustee."
            )
        self.f.blank(2)
        self.f.body("[Seal]")
        self.f.blank()
        self.f.body("________________________________________")
        self.f.body("Notary Public")
        self.f.body("My commission expires: _______________")
```

- [ ] **Step 9: Update _schedules for individual trusts**

For individual trusts, Schedule A is "Grantor's Property" (not "Communal Property"). Schedules C and D (Husband's/Wife's Separate Property) are never generated for individual trusts.

```python
    def _schedules(self) -> None:
        if self.is_individual:
            self.f.h1("Schedule A: Grantor\u2019s Property")
        else:
            self.f.h1("Schedule A: Communal Property")
        self.f.body("Transferred to this Trust:")
        self.f.blank()
        self.f.body("Ten Dollars Cash")
        if self.is_individual:
            self.f.manual_review("Additional property to be transferred")
        else:
            self.f.manual_review("Additional communal property")

        self.f.pb()
        self.f.h1("Schedule B: Memorandum of Distribution [OPTIONAL]")
        bequests = self.d.specific_bequests
        if bequests:
            for b in bequests:
                instr = f" ({b.instructions})" if b.instructions else ""
                self.f.indent(f"{b.item} \u2192 {b.recipient}{instr}")
        else:
            self.f.manual_review("Specific bequests if applicable")

        if (
            not self.is_individual
            and self.d.elections.property_classification
            == PropertyClassification.SEPARATE
        ):
            self.f.pb()
            self.f.h1("Schedule C: Husband\u2019s Separate Property")
            self.f.manual_review("Husband\u2019s separate property")
            self.f.pb()
            self.f.h1("Schedule D: Wife\u2019s Separate Property")
            self.f.manual_review("Wife\u2019s separate property")
```

- [ ] **Step 10: Run all generator tests**

Run: `pytest tests/test_generators.py -v`
Expected: ALL PASS

- [ ] **Step 11: Commit**

```bash
git add src/trust_generator/generators/trust_document.py tests/test_generators.py
git commit -m "feat: generate individual trust documents with single-grantor language"
```

---

### Task 4: Update parsers for individual trust detection

**Files:**
- Modify: `src/trust_generator/parsers/docx_parser.py`
- Modify: `src/trust_generator/parsers/json_parser.py` (no change needed — Pydantic handles `trust_type` automatically)
- Test: `tests/test_parsers.py`

- [ ] **Step 1: Write failing tests for trust type detection**

Add to `tests/test_parsers.py`:

```python
from trust_generator.schema import TrustData, TrustType


def test_json_round_trip_individual(tmp_path):
    """Individual trust type should survive JSON round-trip."""
    from trust_generator.parsers import parse_json
    from trust_generator.schema import PersonInfo

    data = TrustData(
        trust_type=TrustType.INDIVIDUAL,
        grantor=PersonInfo(full_legal_name="Robert Wilson"),
    )
    json_file = tmp_path / "individual.json"
    json_file.write_text(data.model_dump_json(indent=2), encoding="utf-8")

    restored = parse_json(json_file)
    assert restored.trust_type == TrustType.INDIVIDUAL
    assert restored.grantor.full_legal_name == "Robert Wilson"


def test_json_default_trust_type_is_joint(tmp_path):
    """JSON without trust_type field should default to JOINT (backward compat)."""
    from trust_generator.parsers import parse_json

    json_file = tmp_path / "legacy.json"
    json_file.write_text('{"husband": {"full_legal_name": "John Smith"}}', encoding="utf-8")

    restored = parse_json(json_file)
    assert restored.trust_type == TrustType.JOINT


def test_docx_parser_detects_individual_trust():
    """Docx parser should set trust_type=INDIVIDUAL when wife section is empty and husband is filled."""
    # This test requires the blank questionnaire asset
    import pytest
    ASSETS_DIR = Path(__file__).resolve().parents[1] / "assets"
    QUESTIONNAIRE_PATH = ASSETS_DIR / "Trust_Intake_Questionnaire.docx"
    if not QUESTIONNAIRE_PATH.exists():
        pytest.skip("Questionnaire asset not found")

    from trust_generator.parsers import parse_docx
    # The blank questionnaire has no data, so trust_type detection
    # should default to JOINT (both sections are empty)
    data = parse_docx(QUESTIONNAIRE_PATH)
    assert data.trust_type == TrustType.JOINT
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_parsers.py::test_json_round_trip_individual -v -x`
Expected: FAIL with `ImportError: cannot import name 'TrustType'` (from test file)

- [ ] **Step 3: Update docx_parser to detect trust type**

In `src/trust_generator/parsers/docx_parser.py`, add `TrustType` to the imports from `trust_generator.schema`.

In the `_flat_to_trust_data` function, add trust type detection logic. After building the `TrustData`, detect if it should be individual:

```python
def _flat_to_trust_data(
    flat: dict[str, str],
    *,
    # ... existing params ...
) -> TrustData:
    """Assemble a TrustData from the various parsed components."""
    husband_data = _map_person(flat, "husband")
    wife_data = _map_person(flat, "wife")

    # Auto-detect trust type: if husband is filled but wife is empty, individual trust
    husband_name = husband_data.get("full_legal_name", "")
    wife_name = wife_data.get("full_legal_name", "")

    if husband_name and not wife_name:
        trust_type = TrustType.INDIVIDUAL
        grantor_data = husband_data
    else:
        trust_type = TrustType.JOINT
        grantor_data = {}

    return TrustData(
        trust_type=trust_type,
        grantor=PersonInfo(**grantor_data) if grantor_data else PersonInfo(),
        husband=PersonInfo(**husband_data),
        wife=PersonInfo(**wife_data),
        marriage=MarriageInfo(**_map_section(flat, "marriage", _MARRIAGE_KEY_MAP)),
        trust_id=TrustIdentity(**_map_section(flat, "trust_id", _TRUST_ID_KEY_MAP)),
        office=OfficeInfo(**_map_section(flat, "office", _OFFICE_KEY_MAP)),
        children=[Child(**c) for c in children],
        successor_trustees=[SuccessorTrustee(**s) for s in successor_trustees],
        real_property=[RealProperty(**r) for r in real_property],
        financial_accounts=[FinancialAccount(**a) for a in financial_accounts],
        vehicles=[Vehicle(**v) for v in vehicles],
        insurance_policies=[InsurancePolicy(**p) for p in insurance_policies],
        pensions=[Pension(**p) for p in pensions],
        valuables=[Valuable(**v) for v in valuables],
        beneficiary_shares=[BeneficiaryShare(**b) for b in beneficiary_shares],
        specific_bequests=[SpecificBequest(**b) for b in specific_bequests],
        withdrawal_schedule=[WithdrawalStep(**w) for w in withdrawal_schedule],
        other_beneficiaries=[OtherBeneficiary(**o) for o in other_beneficiaries],
        elections=_build_elections(checkbox_data),
        text_blocks=TextBlocks(**text_blocks),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_parsers.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/trust_generator/parsers/docx_parser.py tests/test_parsers.py
git commit -m "feat: auto-detect individual trust type in parsers"
```

---

### Task 5: Update printable questionnaire for individual trusts

**Files:**
- Modify: `src/trust_generator/generators/printable_questionnaire.py`
- Test: `tests/test_printable.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_printable.py`:

```python
from trust_generator.generators.printable_questionnaire import generate_printable_questionnaire


def test_individual_printable_questionnaire(tmp_path):
    """Generate an individual-trust printable questionnaire."""
    path = tmp_path / "individual_questionnaire.docx"
    result = generate_printable_questionnaire(path, trust_type="individual")
    assert Path(result).exists()
    doc = Document(result)
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "Grantor Information" in text
    assert "Husband Information" not in text
    assert "Wife Information" not in text
    assert "Marriage Information" not in text


def test_joint_printable_questionnaire_unchanged(tmp_path):
    """Default (joint) printable questionnaire should be unchanged."""
    path = tmp_path / "joint_questionnaire.docx"
    result = generate_printable_questionnaire(path)
    doc = Document(result)
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "Husband Information" in text
    assert "Wife Information" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_printable.py::test_individual_printable_questionnaire -v -x`
Expected: FAIL — `generate_printable_questionnaire()` doesn't accept `trust_type`

- [ ] **Step 3: Add trust_type parameter to generate_printable_questionnaire**

In `src/trust_generator/generators/printable_questionnaire.py`, update the function signature:

```python
def generate_printable_questionnaire(
    output_path: str | Path,
    config: AppConfig | None = None,
    trust_type: str = "joint",
) -> str:
```

Add a `_section_grantor` function:

```python
def _section_grantor(fmt: DocxFormatter) -> None:
    fmt.h2("Grantor Information")
    _person_table(fmt, [
        "Full Legal Name",
        "Date of Birth",
        "Social Security Number",
        "Address",
        "Phone",
        "Email",
        "Employer",
    ])
```

Update the section sequence in the function body to branch on `trust_type`:

```python
    _header(fmt, cfg)
    _section_office(fmt)
    if trust_type == "individual":
        _section_grantor(fmt)
    else:
        _section_husband(fmt)
        _section_wife(fmt)
        _section_marriage(fmt)
    _section_trust_info(fmt)
    # ... rest unchanged
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_printable.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/trust_generator/generators/printable_questionnaire.py tests/test_printable.py
git commit -m "feat: add individual-trust variant to printable questionnaire"
```

---

### Task 6: Update GUI and CLI for trust type display

**Files:**
- Modify: `src/trust_generator/ui/gui.py`
- Modify: `src/trust_generator/ui/cli.py`

- [ ] **Step 1: Update GUI review sections**

In `src/trust_generator/ui/gui.py`, in the `_add_review_sections` method (line 345), update the "Grantors" section to branch on trust type:

```python
        from trust_generator.schema import TrustType

        if d.trust_type == TrustType.INDIVIDUAL:
            grantor_section = (
                "Grantor",
                [
                    ("Grantor", d.grantor.full_legal_name or "(empty)", "grantor.full_legal_name"),
                    ("Trust Type", "Individual", ""),
                ],
            )
        else:
            grantor_section = (
                "Grantors",
                [
                    ("Husband", d.husband.full_legal_name or "(empty)", "husband.full_legal_name"),
                    ("Wife", d.wife.full_legal_name or "(empty)", "wife.full_legal_name"),
                    ("Trust Type", "Joint", ""),
                ],
            )
```

Then use `grantor_section` as the first element of the `sections` list instead of the hardcoded "Grantors" tuple.

- [ ] **Step 2: Update CLI summary**

In `src/trust_generator/ui/cli.py`, update the `_print_summary` function to show trust type:

```python
def _print_summary(data: TrustData) -> None:
    from trust_generator.schema import TrustType

    print("=== Trust Data Summary ===")
    print(f"  Trust Type: {data.trust_type.value.title()}")
    if data.trust_type == TrustType.INDIVIDUAL:
        print(f"  Grantor:    {data.grantor.full_legal_name or '(empty)'}")
    else:
        print(f"  Husband:    {data.husband.full_legal_name or '(empty)'}")
        print(f"  Wife:       {data.wife.full_legal_name or '(empty)'}")
    print(f"  Trust Name: {data.trust_name}")
    # ... rest unchanged
```

- [ ] **Step 3: Run existing CLI tests to confirm no regressions**

Run: `pytest tests/test_cli.py -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add src/trust_generator/ui/gui.py src/trust_generator/ui/cli.py
git commit -m "feat: show trust type in GUI review and CLI summary"
```

---

### Task 7: End-to-end integration test for individual trusts

**Files:**
- Modify: `tests/test_integration.py`

- [ ] **Step 1: Write integration test**

Add to `tests/test_integration.py`:

```python
from trust_generator.schema import TrustType


def test_individual_trust_json_pipeline(tmp_path: Path) -> None:
    """Individual trust: create -> JSON -> parse -> validate -> generate."""
    original = TrustData(
        trust_type=TrustType.INDIVIDUAL,
        grantor=PersonInfo(full_legal_name="Robert James Wilson", ssn="987-65-4321"),
        trust_id=TrustIdentity(
            desired_trust_name="The Wilson Family Trust",
            date="March 15, 2026",
        ),
        children=[
            Child(name="Sarah Wilson", dob="05/10/1995", relationship="Daughter"),
        ],
        successor_trustees=[
            SuccessorTrustee(order="1", name="Sarah Wilson", relationship="Daughter"),
        ],
        beneficiary_shares=[
            BeneficiaryShare(name="Sarah Wilson", share="100"),
        ],
        real_property=[RealProperty(address="456 Oak Ave", equity="$300,000")],
    )

    # Dump to JSON
    json_file = tmp_path / "individual_intake.json"
    json_file.write_text(original.model_dump_json(indent=2), encoding="utf-8")

    # Parse back
    parsed = parse_json(json_file)
    assert parsed.trust_type == TrustType.INDIVIDUAL
    assert parsed.grantor.full_legal_name == "Robert James Wilson"
    assert parsed == original

    # Validate
    report = validate(parsed)
    assert report.can_generate is True

    # Generate
    out = tmp_path / "wilson_trust.docx"
    generate_trust_document(parsed, out)
    assert out.exists()

    doc = Document(str(out))
    text = "\n".join(p.text for p in doc.paragraphs)
    for i in range(1, 13):
        assert f"Article {i}:" in text, f"Article {i} missing"
    assert "Robert James Wilson" in text
    assert "The Wilson Family Trust" in text
    assert "[WIFE FULL NAME]" not in text


def test_individual_trust_all_elections_non_default(tmp_path: Path) -> None:
    """Individual trust with non-default elections should not crash."""
    data = TrustData(
        trust_type=TrustType.INDIVIDUAL,
        grantor=PersonInfo(full_legal_name="Robert Wilson"),
        trust_id=TrustIdentity(
            desired_trust_name="The Wilson Trust",
            date="March 15, 2026",
        ),
        children=[Child(name="Sarah Wilson")],
        successor_trustees=[SuccessorTrustee(order="1", name="Sarah Wilson")],
        beneficiary_shares=[BeneficiaryShare(name="Sarah Wilson", share="100")],
        elections=Elections(
            spendthrift=False,
            no_contest=False,
            probate_coordination=False,
            distribution_standard=DistributionStandard.BROAD,
            remote_contingent=RemoteContingent.CHARITY,
            remote_contingent_charity="Local Food Bank",
            power_of_appointment=PowerOfAppointment.NONE,
        ),
    )
    text = _generate_to_text(data, tmp_path)
    assert "Robert Wilson" in text
    assert "Local Food Bank" in text
    assert "Spendthrift Provision" not in text
    assert "Contest Provision" not in text
```

- [ ] **Step 2: Run integration tests**

Run: `pytest tests/test_integration.py -v`
Expected: ALL PASS

- [ ] **Step 3: Run full test suite**

Run: `pytest tests/ -v`
Expected: ALL PASS — no regressions in any existing test

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add end-to-end integration tests for individual trust pipeline"
```

---

### Task 8: Export TrustType from package __init__.py

**Files:**
- Modify: `src/trust_generator/__init__.py`

- [ ] **Step 1: Update __init__.py exports**

In `src/trust_generator/__init__.py`, add `TrustType` to `__all__` and the import:

```python
__all__ = [
    "TrustData",
    "TrustType",
    "AppConfig",
    "load_config",
    "parse_file",
    "validate",
    "generate_trust_document",
    "generate_printable_questionnaire",
]

from .config import AppConfig, load_config
from .generators import generate_printable_questionnaire, generate_trust_document
from .parsers import parse_file
from .schema import TrustData, TrustType
from .validators import validate
```

- [ ] **Step 2: Run full test suite one final time**

Run: `pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 3: Run linter**

Run: `ruff check src/ tests/`
Expected: `All checks passed!`

- [ ] **Step 4: Commit**

```bash
git add src/trust_generator/__init__.py
git commit -m "feat: export TrustType from package public API"
```
