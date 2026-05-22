# v3 Schema Test Suite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the 30-case v3 schema test suite defined in `docs/superpowers/specs/2026-04-21-schema-tests-design.md`, pinning the externally-observable behavior of `trust_generator/v3/schema.py`.

**Architecture:** Test-only scope. The v3 schema (`src/trust_generator/v3/schema.py`) is already written and is **out of scope** for edits this session (per spec §3 F-2). Every test case is an observational pin: it asserts what the schema currently does. Any failing test signals (a) a spec transcription error, (b) a test bug, or (c) a latent schema defect worth escalating — fix the test or escalate, but do not modify `schema.py` without an explicit out-of-band decision from the user.

**Tech Stack:** pytest (+ `pytest.mark.parametrize`), Pydantic v2.x, Python 3.12+, pixi for environment orchestration (`pixi run test`, `pixi run format`, `pixi run lint`, `pixi run typecheck`).

**TDD inversion note:** Canonical TDD writes a failing test before the implementation. Here the implementation exists. Each task still verifies the test has teeth: after writing the test and seeing it PASS, temporarily flip one assertion value to confirm the test can fail, then restore. This catches accidentally-tautological tests (e.g., `assert x == x`).

**File layout:**

- Create: `tests/v3/__init__.py` — empty; makes `tests.v3` a package so pytest discovers it alongside `tests/v2/`.
- Create: `tests/v3/test_schema.py` — all 30 cases across 15 clusters, one test function or parametrized group per case.

**Naming convention:** All test function names match the spec's `T-NN` label exactly (`test_full_legal_name_empty_is_accepted`, etc.). The failure message alone should point to the schema invariant being protected (§6 of spec).

---

### Task 1: Scaffold v3 test package

**Files:**
- Create: `tests/v3/__init__.py`
- Create: `tests/v3/test_schema.py`

- [ ] **Step 1: Create empty `__init__.py`**

Create `tests/v3/__init__.py` with zero bytes (pytest discovery needs it to mirror `tests/v2/__init__.py`; pyproject.toml has no `[tool.pytest.ini_options]` overriding discovery).

- [ ] **Step 2: Create test file header with imports**

Create `tests/v3/test_schema.py` with:

```python
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
    Beneficiary,
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
    GenericRelationship,
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
    promote_seed,
)
```

Note: `_ChildRelationship` is imported with its leading underscore — the PEP 695 alias `ChildRelationship` is the type-checker name, but the enum itself is `_ChildRelationship`, and T-15 needs both in scope.

- [ ] **Step 3: Run the empty file to verify collection**

Run: `pixi run test -- tests/v3/test_schema.py -v`
Expected: `collected 0 items` — file imports cleanly, no items yet. If the import line fails, the symbol list is wrong; fix before proceeding.

- [ ] **Step 4: Commit**

```bash
git add tests/v3/__init__.py tests/v3/test_schema.py
git commit -m "test(v3): scaffold schema test package"
```

---

### Task 2: PersonReference name validator (T-01, T-02, T-03)

**Files:**
- Modify: `tests/v3/test_schema.py`

- [ ] **Step 1: Write the three validator tests**

Append to `tests/v3/test_schema.py`:

```python
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
```

- [ ] **Step 2: Run the three tests, verify all pass**

Run: `pixi run test -- tests/v3/test_schema.py -v -k "full_legal_name"`
Expected: 5 passes (T-01, T-02, and 3 parametrized rows of T-03). If T-02 fails because the raised `ValueError` text differs, align the `in` check to what the validator actually produces — do not edit the validator.

- [ ] **Step 3: Teeth-check**

Temporarily change `assert "Madonna" in str(exc_info.value)` to `assert "Cher" in str(exc_info.value)`, rerun, confirm it FAILS, then revert.

- [ ] **Step 4: Commit**

```bash
git add tests/v3/test_schema.py
git commit -m "test(v3): pin PersonReference name validator (T-01..T-03)"
```

---

### Task 3: is_minor_as_of edge cases (T-04, T-05, T-06, T-07)

**Files:**
- Modify: `tests/v3/test_schema.py`

- [ ] **Step 1: Write the four age-boundary tests**

Append:

```python
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
```

- [ ] **Step 2: Run the tests, verify all pass**

Run: `pixi run test -- tests/v3/test_schema.py -v -k "is_minor"`
Expected: 6 passes (3 standalone + 3 parametrized rows).

- [ ] **Step 3: Teeth-check the leap-day edge**

In the parametrize table, change `(date(2008, 2, 29), date(2026, 2, 28), True)` → `False`, rerun, confirm it FAILS on that row with a clear diff, then revert. This is the row that catches F-4 regressions.

- [ ] **Step 4: Commit**

```bash
git add tests/v3/test_schema.py
git commit -m "test(v3): pin is_minor_as_of boundary and leap-day behavior (T-04..T-07)"
```

---

### Task 4: GrantorInfo SSN validator (T-08, T-09, T-10)

**Files:**
- Modify: `tests/v3/test_schema.py`

- [ ] **Step 1: Write the three SSN tests**

Append:

```python
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
```

- [ ] **Step 2: Run the tests, verify all pass**

Run: `pixi run test -- tests/v3/test_schema.py -v -k "ssn_last_four"`
Expected: 8 passes (2 standalone + 6 parametrized rows).

- [ ] **Step 3: Commit**

```bash
git add tests/v3/test_schema.py
git commit -m "test(v3): pin GrantorInfo ssn_last_four validator (T-08..T-10)"
```

---

### Task 5: Recipient-XOR validators on distributions (T-11, T-12, T-13, T-14)

**Files:**
- Modify: `tests/v3/test_schema.py`

- [ ] **Step 1: Write the four recipient-XOR tests**

Append:

```python
# ---------------------------------------------------------------------------
# 4.4 Recipient-XOR validators on distributions
# ---------------------------------------------------------------------------


def test_beneficiary_share_rejects_neither_recipient():
    """Both refs None → validation error citing 'requires recipient_ref or recipient_external'."""
    with pytest.raises(ValidationError) as exc_info:
        BeneficiaryShare(share_percent=Decimal("50"))
    assert "requires recipient_ref or recipient_external" in str(exc_info.value)


def test_beneficiary_share_rejects_both_recipients():
    """Both refs populated → 'specify recipient_ref OR recipient_external'."""
    with pytest.raises(ValidationError) as exc_info:
        BeneficiaryShare(
            recipient_ref="child_1",
            recipient_external=PersonReference(full_legal_name="Jane Smith"),
            share_percent=Decimal("50"),
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
```

- [ ] **Step 2: Run the tests, verify all pass**

Run: `pixi run test -- tests/v3/test_schema.py -v -k "recipient"`
Expected: 4 passes.

- [ ] **Step 3: Commit**

```bash
git add tests/v3/test_schema.py
git commit -m "test(v3): pin recipient-XOR on BeneficiaryShare and SpecificBequest (T-11..T-14)"
```

---

### Task 6: PEP 695 type alias runtime semantics (T-15)

**Files:**
- Modify: `tests/v3/test_schema.py`

- [ ] **Step 1: Write the alias-runtime test**

Append:

```python
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
```

- [ ] **Step 2: Run the test, verify it passes**

Run: `pixi run test -- tests/v3/test_schema.py::test_child_relationship_alias_is_not_runtime_class -v`
Expected: PASS. If `isinstance` does NOT raise, Python's PEP 695 semantics have changed (or this interpreter is pre-3.12) — investigate before touching anything else.

- [ ] **Step 3: Commit**

```bash
git add tests/v3/test_schema.py
git commit -m "test(v3): pin PEP 695 type alias runtime non-identity (T-15)"
```

---

### Task 7: Two-axis relationship round-trip (T-16)

**Files:**
- Modify: `tests/v3/test_schema.py`

- [ ] **Step 1: Write the two-axis round-trip test**

Append:

```python
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
```

- [ ] **Step 2: Run the test, verify it passes**

Run: `pixi run test -- tests/v3/test_schema.py::test_child_adopted_with_other_biological_parent_roundtrips -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/v3/test_schema.py
git commit -m "test(v3): pin two-axis Child relationship round-trip (T-16)"
```

---

### Task 8: Defaults audit (T-17, T-18)

**Files:**
- Modify: `tests/v3/test_schema.py`

- [ ] **Step 1: Write the defaults audit and boolean-preservation tests**

Append:

```python
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
    assert data.elections.guardianship_policy == GuardianshipPolicy.EXPLICIT_DESIGNATIONS
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
```

- [ ] **Step 2: Run the tests, verify both pass**

Run: `pixi run test -- tests/v3/test_schema.py -v -k "defaults or boolean_elections"`
Expected: 2 passes.

- [ ] **Step 3: Commit**

```bash
git add tests/v3/test_schema.py
git commit -m "test(v3): pin TrustData defaults and boolean-election preservation (T-17, T-18)"
```

---

### Task 9: Computed-property sentinel chains (T-19, T-20)

**Files:**
- Modify: `tests/v3/test_schema.py`

- [ ] **Step 1: Write the sentinel-chain tests**

Append:

```python
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
```

- [ ] **Step 2: Run the tests, verify both pass**

Run: `pixi run test -- tests/v3/test_schema.py -v -k "fallback_chain or grantor_name_sentinel"`
Expected: 2 passes.

- [ ] **Step 3: Commit**

```bash
git add tests/v3/test_schema.py
git commit -m "test(v3): pin trust-name and grantor-name sentinel chains (T-19, T-20)"
```

---

### Task 10: Caption + display properties and promote_seed caption matrix (T-21, T-22)

**Files:**
- Modify: `tests/v3/test_schema.py`

- [ ] **Step 1: Write the display-name and caption-matrix tests**

Append:

```python
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
```

- [ ] **Step 2: Run the tests, verify all pass**

Run: `pixi run test -- tests/v3/test_schema.py -v -k "display_name or caption_resolution"`
Expected: 5 passes (1 + 4 parametrized rows).

- [ ] **Step 3: Commit**

```bash
git add tests/v3/test_schema.py
git commit -m "test(v3): pin display names and promote_seed caption matrix (T-21, T-22)"
```

---

### Task 11: SSN owner name (T-23)

**Files:**
- Modify: `tests/v3/test_schema.py`

- [ ] **Step 1: Write the SSN-owner switch test**

Append:

```python
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
```

- [ ] **Step 2: Run the test, verify it passes**

Run: `pixi run test -- tests/v3/test_schema.py::test_ssn_owner_name_switches_on_preference -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/v3/test_schema.py
git commit -m "test(v3): pin ssn_owner_name switch on tax_id preference (T-23)"
```

---

### Task 12: promote_seed fidelity (T-24, T-25)

**Files:**
- Modify: `tests/v3/test_schema.py`

- [ ] **Step 1: Write the promote_seed fidelity tests**

Append:

```python
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
    """Bounded-context boundary: seed-only fields must not appear on TrustData.

    If promote_seed ever sprouts a paralegal_name projection, this fails and
    surfaces the leak between the two contexts.
    """
    seed = QuestionnaireSeed(
        paralegal_name="Sam",
        attorney_name="Alice",
        consultation_date=date(2026, 4, 1),
        accessibility_overrides={"font_size": "14pt"},
        has_pets=True,
        child_count_tier=ChildCountTier.ONE_TO_FIVE,
    )
    data = promote_seed(seed)

    # None of the seed-only field names exist on TrustData.
    for seed_only in (
        "paralegal_name",
        "attorney_name",
        "consultation_date",
        "accessibility_overrides",
        "has_pets",
        "child_count_tier",
    ):
        assert not hasattr(data, seed_only), (
            f"TrustData unexpectedly exposed seed-only field {seed_only!r}"
        )

    # Defaults still intact for fields promote_seed did not explicitly set.
    assert data.trust_id.desired_trust_name == ""
    assert data.elections.estate_value_estimate == EstateValueRange.BELOW_THRESHOLD
```

- [ ] **Step 2: Run the tests, verify both pass**

Run: `pixi run test -- tests/v3/test_schema.py -v -k "promote_seed_projects or promote_seed_drops"`
Expected: 2 passes.

- [ ] **Step 3: Commit**

```bash
git add tests/v3/test_schema.py
git commit -m "test(v3): pin promote_seed projection and seed-only omission (T-24, T-25)"
```

---

### Task 13: Aggregation properties (T-26, T-27)

**Files:**
- Modify: `tests/v3/test_schema.py`

- [ ] **Step 1: Write the aggregation-property tests**

Append:

```python
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
```

- [ ] **Step 2: Run the tests, verify both pass**

Run: `pixi run test -- tests/v3/test_schema.py -v -k "disinherited_beneficiaries or excluded_persons"`
Expected: 2 passes.

- [ ] **Step 3: Commit**

```bash
git add tests/v3/test_schema.py
git commit -m "test(v3): pin disinherited/excluded aggregation with ordering (T-26, T-27)"
```

---

### Task 14: Asset totalization (T-28)

**Files:**
- Modify: `tests/v3/test_schema.py`

- [ ] **Step 1: Write the asset-totalization test**

Append:

```python
# ---------------------------------------------------------------------------
# 4.13 Asset totalization
# ---------------------------------------------------------------------------


def test_collected_total_value_sums_all_asset_types():
    """Sum must span all six asset types and preserve Decimal exactness."""
    # empty-case zero, preserved as Decimal
    assert TrustData().collected_total_value == Decimal("0")
    assert isinstance(TrustData().collected_total_value, Decimal)

    data = TrustData(
        real_property=[RealProperty(value=Decimal("100"))],
        financial_accounts=[FinancialAccount(value=Decimal("200"))],
        vehicles=[Vehicle(value=Decimal("50"))],
        insurance_policies=[InsurancePolicy(benefit=Decimal("500"))],
        pensions=[Pension(value=Decimal("300"))],
        valuables=[Valuable(value=Decimal("25"))],
    )
    total = data.collected_total_value
    assert total == Decimal("1175")
    assert isinstance(total, Decimal)
```

- [ ] **Step 2: Run the test, verify it passes**

Run: `pixi run test -- tests/v3/test_schema.py::test_collected_total_value_sums_all_asset_types -v`
Expected: PASS. The `isinstance` check guards against silent regression to `float` or `int`; diagnostic rules compare this to firm-configured thresholds and rely on `Decimal` precision.

- [ ] **Step 3: Commit**

```bash
git add tests/v3/test_schema.py
git commit -m "test(v3): pin collected_total_value sum across six asset types (T-28)"
```

---

### Task 15: QuestionnaireSeed variant_key composition (T-29)

**Files:**
- Modify: `tests/v3/test_schema.py`

- [ ] **Step 1: Write the variant-key composition test**

Append:

```python
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
    ids=["joint-above-1to5", "individual-unmarried-below-none", "individual-declined-6plus"],
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
```

- [ ] **Step 2: Run the test, verify all rows pass**

Run: `pixi run test -- tests/v3/test_schema.py -v -k "variant_key"`
Expected: 3 passes.

- [ ] **Step 3: Commit**

```bash
git add tests/v3/test_schema.py
git commit -m "test(v3): pin QuestionnaireSeed.variant_key composition (T-29)"
```

---

### Task 16: Round-trip serialization (T-30)

**Files:**
- Modify: `tests/v3/test_schema.py`

- [ ] **Step 1: Write the comprehensive round-trip test**

Append:

```python
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
                funding_amount=Decimal("5000"),
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
    assert restored.pets[0].funding_amount == Decimal("5000")
    assert isinstance(restored.pets[0].funding_amount, Decimal)
    assert restored.beneficiary_shares[0].share_percent == Decimal("50.00")
    assert isinstance(restored.beneficiary_shares[0].share_percent, Decimal)
    assert restored.withdrawal_schedule[0].percent == Decimal("25.00")

    # two-axis Child relationship — both axes preserved
    assert restored.children[0].relationship == _ChildRelationship.ADOPTED
    assert restored.children[0].biological_parent == BiologicalParent.OTHER
```

- [ ] **Step 2: Run the test, verify it passes**

Run: `pixi run test -- tests/v3/test_schema.py::test_trust_data_json_round_trip_preserves_v3_fields -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/v3/test_schema.py
git commit -m "test(v3): pin TrustData JSON round-trip across new v3 fields (T-30)"
```

---

### Task 17: Full-suite verification and hygiene

**Files:** (verification only)

- [ ] **Step 1: Run the whole v3 suite**

Run: `pixi run test -- tests/v3/test_schema.py -v`
Expected: 39 passing items (30 named cases; parametrized rows in T-03, T-07, T-10, T-22, T-29 expand past 30). Zero failures, zero errors. If anything fails, stop and investigate — the schema is treated as fixed, so a failure is either a test defect or a genuine schema regression worth escalating to the user before proceeding.

- [ ] **Step 2: Run the full project test suite to confirm no cross-contamination**

Run: `pixi run test`
Expected: The existing v2 suite still passes alongside v3. If v2 breaks, the new imports accidentally introduced a side effect — revert and investigate.

- [ ] **Step 3: Lint and format**

Run: `pixi run lint -- tests/v3/test_schema.py`
Run: `pixi run format -- tests/v3/test_schema.py`
Run: `pixi run typecheck`
Expected: All clean. Fix any ruff or pyright findings within the test file only; do not touch `schema.py`.

- [ ] **Step 4: Final commit**

If any lint/format/typecheck fixes were applied, commit them:

```bash
git add tests/v3/test_schema.py
git commit -m "test(v3): apply lint/format to schema test suite"
```

If nothing changed, skip this step.

---

## Spec coverage checklist (self-review)

Every T-NN maps to exactly one task:

| Task | Cases              | Cluster(s) |
| ---- | ------------------ | ---------- |
| 1    | —                  | scaffold   |
| 2    | T-01, T-02, T-03   | §4.1       |
| 3    | T-04, T-05, T-06, T-07 | §4.2   |
| 4    | T-08, T-09, T-10   | §4.3       |
| 5    | T-11, T-12, T-13, T-14 | §4.4   |
| 6    | T-15               | §4.5       |
| 7    | T-16               | §4.6       |
| 8    | T-17, T-18         | §4.7       |
| 9    | T-19, T-20         | §4.8       |
| 10   | T-21, T-22         | §4.9       |
| 11   | T-23               | §4.10      |
| 12   | T-24, T-25         | §4.11      |
| 13   | T-26, T-27         | §4.12      |
| 14   | T-28               | §4.13      |
| 15   | T-29               | §4.14      |
| 16   | T-30               | §4.15      |
| 17   | —                  | verification |

All 30 cases covered. Parametrized cases (T-03, T-07, T-10, T-22, T-29) use `pytest.mark.parametrize` with `ids=[...]` for readable failure output. All imports use `trust_generator.v3.*`; no v2 references.
