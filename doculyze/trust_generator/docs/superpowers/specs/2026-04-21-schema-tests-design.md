# TGv3 schema.py — Test Suite Design Spec

**Date:** 2026-04-21
**Scope:** `trust_generator/v3/schema.py` behavior surface
**Supersedes:** `trust_generator/v2/test_schema.py` patterns (selectively ported)
**Intended target path:** `trust_generator/v3/test_schema.py` (30 cases across 15 clusters)

## 1. Purpose

Define the test cases that pin the v3 schema's externally-observable behavior before the test file is written. Each case lists its name, the assertion it makes, and why that assertion belongs in the suite. The spec is the source of truth; the eventual test file is a faithful translation.

The v3 schema is larger and better-typed than v2, so the suite grows: more validators to exercise, more computed properties to verify, a new bounded-context translation (`promote_seed`) to cover, and PEP 695 runtime semantics to pin so nobody accidentally reaches for `isinstance` on a type alias.

## 2. Patterns retained, dropped, and added

| Pattern                                                     | v2 coverage            | v3 status              | Reason                                                                                          |
| ----------------------------------------------------------- | ---------------------- | ---------------------- | ----------------------------------------------------------------------------------------------- |
| Round-trip serialization                                    | Yes                    | **Retained, expanded** | Covers new v3 fields (pets, digital assets, custom terms, external exclusions).                 |
| Default-value audit                                         | Yes                    | **Retained, expanded** | More enums, more captions, more booleans to pin.                                                |
| Sentinel behavior                                           | Yes (`[MISSING]`)      | **Retained, remapped** | v3 sentinels: `[TRUST NAME]`, `[GRANTOR NAME]`, `[CO-GRANTOR NAME]`, `[COUNTY]`, `[...ASSETS]`. |
| Enum coercion (husband/wife)                                | Yes                    | **Dropped**            | v3 dissolved `husband`/`wife`; no custom coercion remains. See §3 F-2.                          |
| JSON backward compat                                        | Yes                    | **Dropped**            | v3 is green-field. See §3 F-3.                                                                  |
| Logging side effects                                        | Yes (`get_or_default`) | **Relocated**          | No v3 analog in `schema.py`; pattern moves to diagnostics engine spec. See §3 F-1.              |
| Boolean conditional fix                                     | Yes                    | **Retained**           | Guards the same regression class in `Elections`.                                                |
| PEP 695 alias runtime non-identity                          | —                      | **Added**              | v3-specific; prevents a whole bug family.                                                       |
| 2+ token `full_legal_name` validator                        | —                      | **Added**              | New validator on `PersonReference`.                                                             |
| 4-digit SSN validator                                       | —                      | **Added**              | New validator on `GrantorInfo`.                                                                 |
| `BeneficiaryShare` / `SpecificBequest` recipient validators | —                      | **Added**              | Both rejection branches of each.                                                                |
| `is_minor_as_of` edge cases                                 | —                      | **Added**              | Boundary behavior of age computation.                                                           |
| Caption resolution via `promote_seed`                       | —                      | **Added**              | Full 2×2 matrix over `(trust_type, marital_status)`.                                            |
| Two-axis relationship edge                                  | —                      | **Added**              | Stepchild-later-adopted scenario.                                                               |
| `disinherited_beneficiaries` aggregation                    | —                      | **Added**              | Computed union across three lists.                                                              |
| `excluded_persons` union                                    | —                      | **Added**              | Disinherited ∪ external exclusions.                                                             |
| `variant_key` composition                                   | —                      | **Added**              | 18-variant selector integrity.                                                                  |

## 3. Scope decisions flagged for confirmation

**F-1 — Logging side effects.** v3 `schema.py` has no `get_or_default`-equivalent and emits no warnings by design. **Resolution:** the logging-side-effects pattern relocates wholesale to the diagnostics engine module(s); it is not a schema concern. Out of scope here; revisit when writing the diagnostics test spec.

**F-2 — Enum coercion.** Case-insensitive enum coercion was evaluated as a candidate v3 feature and deferred: adopting it requires editing `schema.py`, which is explicitly out of scope for this session. **Resolution:** v3 retains Pydantic v2's default case-sensitive `str → Enum` parsing. No test in this suite pins or asserts this surface; pinning an absent feature would add maintenance cost with no matching invariant to protect. If the feature is adopted in a later session, a new spec will cover it then.

**F-3 — Backward-compat JSON.** v3 has no key aliases; v2 JSON payloads will not load. **Resolution:** confirmed intentional. v3 is a successor to v2, not a refactor; the breaking-change count is large enough that migration-by-tool is the correct path, not migration-by-alias. No compat tests in this suite. If a migration tool is later written, its tests belong under `migration/`, not here.

**F-4 — Leap-day `is_minor_as_of`.** Person born Feb 29, observed Feb 28 of a non-leap year before age 18: the tuple comparison evaluates `(2,28) >= (2,29) == False`, so the method reports "not yet had birthday this year." **Resolution:** pinned via T-07's parameterized leap-day subcases; behavior cannot drift silently.

## 4. Test cases

Organized by behavior cluster. Each case lists name, expected behavior, rationale.

### 4.1 PersonReference name validator (3 cases)

**T-01 — `test_full_legal_name_empty_is_accepted`**

- _Behavior:_ `PersonReference()` constructs with `full_legal_name=""` and no validation error.
- _Rationale:_ Many schema positions (default-constructed grantor, empty beneficiary list entries) rely on empty defaults. The validator must fire only when the user supplied a value.

**T-02 — `test_full_legal_name_single_token_rejected`**

- _Behavior:_ `PersonReference(full_legal_name="Madonna")` raises `ValidationError`; error message includes the received value.
- _Rationale:_ Enforces the "two or more tokens" rule. Single-token names are almost always intake errors (first-name only, missing surname), and the validator is the only place that catches them.

**T-03 — `test_full_legal_name_accepts_two_or_more_tokens`**

- _Behavior:_ `"John Smith"`, `"Mary Ann Smith"`, and `"  John   Smith  "` all construct without error; leading/trailing whitespace is stripped per `ConfigDict(str_strip_whitespace=True)`.
- _Rationale:_ Confirms the happy path and confirms whitespace-split semantics (matters when intake data arrives with padding).

### 4.2 is_minor_as_of edge cases (4 cases)

**T-04 — `test_is_minor_returns_false_when_dob_is_none`**

- _Behavior:_ `PersonReference(full_legal_name="John Smith").is_minor_as_of(date(2026,4,21))` returns `False`.
- _Rationale:_ Missing DOB must not produce false-positive minor classification. Failing closed (False) prevents accidental minor-trust provisions for unknown-age people; diagnostics will separately warn on the missing DOB.

**T-05 — `test_is_minor_returns_false_for_entity`**

- _Behavior:_ `PersonReference(is_entity=True, entity_name="Acme Trust Co.", date_of_birth=date(2020,1,1))` returns `False` even with a DOB present.
- _Rationale:_ Entities cannot be minors. Short-circuit on `is_entity` prevents corporate trustees with spurious DOB data from triggering minor logic downstream.

**T-06 — `test_is_minor_true_day_before_eighteenth_birthday`**

- _Behavior:_ Person born `2008-04-22`, evaluated on `2026-04-21`, returns `True`.
- _Rationale:_ Verifies the tuple-comparison age computation treats pre-birthday as "not yet had birthday, subtract one". Boundary day of minor status.

**T-07 — `test_is_minor_false_on_eighteenth_birthday`**

- _Behavior:_ Person born `2008-04-21`, evaluated on `2026-04-21`, returns `False`. Parameterized companion: leap-day (`2008-02-29`), evaluated on `2026-02-28`, returns `True`; on `2026-03-01`, returns `False`.
- _Rationale:_ Pins the inclusive-birthday boundary and the leap-day behavior noted in F-4. If leap-day handling ever changes, this test fails loudly.

### 4.3 GrantorInfo SSN validator (3 cases)

**T-08 — `test_ssn_last_four_empty_allowed`**

- _Behavior:_ `GrantorInfo(full_legal_name="John Smith")` constructs with `ssn_last_four=""`.
- _Rationale:_ SSN is optional at intake time; the validator must not reject unpopulated defaults.

**T-09 — `test_ssn_last_four_four_digits_accepted`**

- _Behavior:_ `GrantorInfo(full_legal_name="John Smith", ssn_last_four="1234")` constructs; stored value is `"1234"`.
- _Rationale:_ Happy path for the canonical input form.

**T-10 — `test_ssn_last_four_rejects_wrong_length_or_non_digits`**

- _Behavior:_ Parameterized over `["123", "12345", "abcd", "12a4", "12 4", "-234"]`; each raises `ValidationError`.
- _Rationale:_ The validator enforces `len == 4 and isdigit()`. Each parameter exercises a distinct rejection reason: short, long, alphabetic, mixed, whitespace, punctuation. Ensures no permissive escape hatch.

### 4.4 Recipient-XOR validators on distributions (4 cases)

**T-11 — `test_beneficiary_share_rejects_neither_recipient`**

- _Behavior:_ `BeneficiaryShare(share_percent=Decimal("50"))` (both refs `None`) raises `ValidationError` citing "requires recipient_ref or recipient_external".
- _Rationale:_ Covers the "nothing supplied" rejection branch. Catches intake forms where the recipient cell is blank.

**T-12 — `test_beneficiary_share_rejects_both_recipients`**

- _Behavior:_ `BeneficiaryShare(recipient_ref="child_1", recipient_external=PersonReference(full_legal_name="Jane Smith"), share_percent=Decimal("50"))` raises `ValidationError` citing "specify recipient_ref OR recipient_external".
- _Rationale:_ Covers the "both supplied" rejection branch. Catches parser bugs that populate both fields; keeps the ref-or-external invariant enforceable.

**T-13 — `test_specific_bequest_rejects_neither_recipient`**

- _Behavior:_ `SpecificBequest(item="grandfather clock")` raises `ValidationError` with the parallel message.
- _Rationale:_ Parallel to T-11 for `SpecificBequest`. Both models share the validator pattern but each owns its own validator method — coverage must be symmetric.

**T-14 — `test_specific_bequest_rejects_both_recipients`**

- _Behavior:_ `SpecificBequest(item="clock", recipient_ref="other_1", recipient_external=PersonReference(full_legal_name="Jane Smith"))` raises `ValidationError`.
- _Rationale:_ Parallel to T-12.

### 4.5 PEP 695 type alias runtime semantics (1 case)

**T-15 — `test_child_relationship_alias_is_not_runtime_class`**

- _Behavior:_ Three assertions: (a) `isinstance(_ChildRelationship.ADOPTED, _ChildRelationship)` is `True`; (b) attempting `isinstance(_ChildRelationship.ADOPTED, ChildRelationship)` raises `TypeError` because `ChildRelationship` is a `typing.TypeAliasType`, not a class; (c) value-equality `_ChildRelationship.ADOPTED.value == "adopted"` is the supported comparison idiom.
- _Rationale:_ PEP 695 `type` statements do not create runtime classes. Downstream code reading the schema must compare via `.value` string equality per the design decision. This test is the load-bearing guardrail: if anyone writes `isinstance(x, TrusteeRelationship)`, their own test fails with this one pointing them to the right idiom.

### 4.6 Two-axis relationship (1 case)

**T-16 — `test_child_adopted_with_other_biological_parent_roundtrips`**

- _Behavior:_ `Child(full_legal_name="Alice Smith", relationship=_ChildRelationship.ADOPTED, biological_parent=BiologicalParent.OTHER)` constructs; JSON dump and reload preserves both axes.
- _Rationale:_ The two-axis model's reason for existing is to distinguish "stepchild later adopted by non-biological parent" — legal status changed to ADOPTED; biology unchanged at OTHER. This test pins the scenario that single-axis designs collapsed.

### 4.7 Defaults audit (2 cases)

**T-17 — `test_trust_data_defaults_match_spec`**

- _Behavior:_ `TrustData()` instance has: `trust_id.trust_type == TrustType.JOINT`; `trust_id.marital_status == MaritalStatus.MARRIED`; `trust_id.grantor_caption == "Grantor"`; `trust_id.co_grantor_caption == "Spouse"`; `trust_id.tax_id_ssn_preference == SsnOwner.GRANTOR`; `trust_id.state_of_governing_law == "Illinois"`; `elections.initial_trustee == InitialTrustee.GRANTORS`; `elections.property_classification == PropertyClassification.COMMUNAL`; `elections.distribution_standard == DistributionStandard.HEMS`; `elections.guardianship_policy == GuardianshipPolicy.EXPLICIT_DESIGNATIONS`; `elections.spendthrift is True`; `elections.no_contest is True`; `elections.probate_coordination is True`; `elections.portability is True`; `elections.trustee_bond is False`; `children == []`; `custom_terms == []`; `co_grantor is None`.
- _Rationale:_ Consolidated defaults gate. Any defaults drift fails this one test rather than requiring many single-assertion tests. Captions, policies, and protective booleans are all load-bearing for generator output.

**T-18 — `test_boolean_elections_preserve_false_when_set`**

- _Behavior:_ `Elections(spendthrift=False, no_contest=False, probate_coordination=False, portability=False)` preserves all four as `False`.
- _Rationale:_ Direct port of the v2 "boolean conditional bug" regression guard. Defaults-true booleans are the classic pydantic trap if a parser coerces falsy values incorrectly.

### 4.8 Computed-property sentinel chains (2 cases)

**T-19 — `test_trust_name_fallback_chain`**

- _Behavior:_ Three subcases on one instance:
    1. `trust_id.desired_trust_name="The Anderson Family Trust"` → returns `"The Anderson Family Trust"`.
    2. `desired_trust_name=""` with `grantor.full_legal_name="Robert James Wilson"` → returns `"The Wilson Family Trust"`.
    3. Both empty → returns the sentinel `"[TRUST NAME]"`.
- _Rationale:_ Pins the three-step fallback order. Order matters: explicit name takes precedence over derived, and the sentinel must be visible in draft output rather than an empty string (silent missingness is the anti-pattern the sentinel defeats).

**T-20 — `test_grantor_name_sentinels`**

- _Behavior:_ (a) `TrustData().grantor_full_name == "[GRANTOR NAME]"`. (b) `TrustData().co_grantor_full_name == ""` (co_grantor is `None`). (c) `TrustData(co_grantor=GrantorInfo()).co_grantor_full_name == "[CO-GRANTOR NAME]"`.
- _Rationale:_ Distinguishes the three states of the co-grantor axis: absent (empty string, generator omits entirely), present-but-unfilled (sentinel, draft surfaces the gap), populated. Three-state distinction is easy to regress if someone collapses `None` and empty.

### 4.9 Caption and display properties (2 cases)

**T-21 — `test_grantor_display_name_and_combined_name`**

- _Behavior:_ With `grantor.full_legal_name="John Smith"`, `co_grantor.full_legal_name="Jane Smith"`, and default captions: `grantor_display_name == "Grantor: John Smith"`; `grantors_combined_name == "John Smith and Jane Smith"`. With `co_grantor=None` and grantor populated: `co_grantor_display_name == ""`; `grantors_combined_name == "John Smith"`.
- _Rationale:_ Captions are first-class fields (see `party_naming` design memo); the display properties are what the generator actually emits. Coverage includes both the dual-grantor and solo-grantor branches of `grantors_combined_name`.

**T-22 — `test_promote_seed_caption_resolution_matrix`**

- _Behavior:_ Parameterized over all four `(trust_type, marital_status)` combinations:

    | `trust_type` | `marital_status` | `grantor_caption` | `co_grantor_caption` | `co_grantor is None` |
    | ------------ | ---------------- | ----------------- | -------------------- | -------------------- |
    | JOINT        | MARRIED          | "Grantor A"       | "Grantor B"          | False                |
    | JOINT        | UNMARRIED        | "Grantor A"       | "Grantor B"          | False                |
    | INDIVIDUAL   | MARRIED          | "Grantor"         | "Spouse"             | False                |
    | INDIVIDUAL   | UNMARRIED        | "Grantor"         | "Spouse"             | True                 |

- _Rationale:_ `promote_seed` is the single point where captions resolve from `(trust_type, marital_status)` and where `co_grantor` presence is decided. The 2×2 matrix is fully enumerated: skipping rows would leave a branch of `promote_seed`'s conditional unverified. The `JOINT + UNMARRIED` row is rare in practice (joint trusts usually imply a marital unit) but legally valid and the code admits it; pinning it prevents accidental regression that would silently drop `co_grantor` for unmarried joint grantors.

### 4.10 SSN owner name (1 case)

**T-23 — `test_ssn_owner_name_switches_on_preference`**

- _Behavior:_ Two subcases on a populated joint TrustData with `grantor="John Smith"`, `co_grantor="Jane Smith"`: (a) default `tax_id_ssn_preference=SsnOwner.GRANTOR` → `ssn_owner_name == "John Smith"`. (b) after setting `tax_id_ssn_preference=SsnOwner.CO_GRANTOR` → `ssn_owner_name == "Jane Smith"`.
- _Rationale:_ Confirms the property routes correctly through the enum. Simple switch, but the EIN workflow depends on it.

### 4.11 promote_seed fidelity (2 cases)

**T-24 — `test_promote_seed_projects_expected_fields`**

- _Behavior:_ Given `QuestionnaireSeed(trust_type=TrustType.JOINT, marital_status=MaritalStatus.MARRIED, estate_value_estimate=EstateValueRange.ABOVE_THRESHOLD, preliminary_trust_name="The Test Trust")`, the resulting `TrustData` has `trust_id.trust_type == TrustType.JOINT`, `trust_id.marital_status == MaritalStatus.MARRIED`, `trust_id.desired_trust_name == "The Test Trust"`, and `elections.estate_value_estimate == EstateValueRange.ABOVE_THRESHOLD`.
- _Rationale:_ Pins the four fields promote_seed explicitly forwards. If the projection ever drops a field, this fails before the generator reads empty data.

**T-25 — `test_promote_seed_drops_seed_only_fields`**

- _Behavior:_ `QuestionnaireSeed(paralegal_name="Sam", attorney_name="Alice", consultation_date=date(2026,4,1), accessibility_overrides={"font_size":"14pt"}, has_pets=True, child_count_tier=ChildCountTier.ONE_TO_FIVE)` promotes to a `TrustData` that exposes none of those values. Assertions: `TrustData` has no field matching any of those names; `trust_id` and `elections` carry their own defaults for everything promote_seed didn't explicitly populate.
- _Rationale:_ The bounded-context boundary is enforced by omission. If promote_seed ever sprouts a `paralegal_name` projection, the two contexts are leaking into each other; this test fails and makes the leak visible.

### 4.12 Aggregation properties (2 cases)

**T-26 — `test_disinherited_beneficiaries_aggregates_across_sections`**

- _Behavior:_ Build a `TrustData` with one disinherited `Child`, one non-disinherited `Child`, one disinherited `Descendant`, one disinherited `OtherBeneficiary`. Assert `len(data.disinherited_beneficiaries) == 3` and the order is children-then-descendants-then-other_beneficiaries (matches implementation's `extend` order).
- _Rationale:_ The property's job is to union across three lists for Section 11 and for the generator's disinheritance clause. Both presence and ordering matter for deterministic document output.

**T-27 — `test_excluded_persons_unions_disinherited_and_external`**

- _Behavior:_ With one disinherited `Child` and one `PersonReference` in `external_exclusions`, assert `len(data.excluded_persons) == 2` and the disinherited beneficiary precedes the external exclusion in the returned list.
- _Rationale:_ Section 11's "I intentionally exclude…" clause iterates this union. Ordering is observable in the generated document, so pinning it prevents silent reordering from minor refactors.

### 4.13 Asset totalization (1 case)

**T-28 — `test_collected_total_value_sums_all_asset_types`**

- _Behavior:_ Populate one entry in each of the six asset lists (`real_property.value=100`, `financial_accounts.value=200`, `vehicles.value=50`, `insurance_policies.benefit=500`, `pensions.value=300`, `valuables.value=25`). Assert `data.collected_total_value == Decimal("1175")`. Also assert `TrustData().collected_total_value == Decimal("0")`.
- _Rationale:_ Diagnostic rules compare this total to the firm-configured estate thresholds. The test locks the sum logic across all six types and confirms the empty-case zero so the sum doesn't regress to `None` or `0.0` (float) — `Decimal` preservation is the real invariant.

### 4.14 QuestionnaireSeed variant key (1 case)

**T-29 — `test_variant_key_composition`**

- _Behavior:_ Parameterized over a representative sample of the 18-space:

    | trust_type | marital_status | estate               | child_count | → variant_key                               |
    | ---------- | -------------- | -------------------- | ----------- | ------------------------------------------- |
    | JOINT      | MARRIED        | ABOVE_THRESHOLD      | ONE_TO_FIVE | `joint_married_above_threshold_one_to_five` |
    | INDIVIDUAL | UNMARRIED      | BELOW_THRESHOLD      | NONE        | `individual_unmarried_below_threshold_none` |
    | INDIVIDUAL | MARRIED        | DECLINED_TO_ESTIMATE | SIX_PLUS    | `individual_married_declined_six_plus`      |

- _Rationale:_ `variant_key` is the print-layout selector. The string form is an API surface — the printable generator looks up templates by this exact key, so any change (hyphens, capitalization, ordering) breaks generation silently. Three rows cover the three enum axes plus the declined-estimate edge.

### 4.15 Round-trip serialization (1 case)

**T-30 — `test_trust_data_json_round_trip_preserves_v3_fields`**

- _Behavior:_ Construct a richly-populated `TrustData` that exercises every new v3 field: `pets=[Pet(...)]`, `digital_asset_directives=[DigitalAssetDirective(...)]`, `custom_terms=[CustomTerm(...)]`, `external_exclusions=[PersonReference(...)]`, `guardianship_designations=[GuardianshipDesignation(...)]`, a `Child` with two-axis relationship fields, a `BeneficiaryShare` with `recipient_ref`, a `SpecificBequest` with `recipient_external`, and `withdrawal_schedule=[WithdrawalStep(age=25, percent=Decimal("25"))]`. Serialize via `model_dump_json()`; reload via `model_validate_json()`. Assert: all list lengths preserved, all enum fields preserved as enum members, `Decimal` values preserved exactly, the two-axis `Child` relationship both axes preserved.
- _Rationale:_ JSON is the persistence format between the GUI, the parser, and the generator. Every new v3 field must survive round-trip or it doesn't really exist for downstream consumers. The single comprehensive test catches cross-field regressions better than many small ones.

## 5. Out of scope for this spec

- `Diagnostic` engine behavior (lives in a separate module, separate spec).
- `FirmConfig` / estate-threshold resolution (separate component).
- Address geocoding (network-dependent, mocked in its own suite).
- Generator / printable output (covered under generator specs).
- Migration from v2 → v3 JSON payloads (see F-3 in §3).

## 6. Completion criteria for the eventual test file

- All 30 cases implemented with the exact names above.
- Parameterized cases (T-07, T-10, T-22, T-29) use `pytest.mark.parametrize` with named parameter sets.
- No test references `trust_generator.v2.*`; v3 imports only.
- Test file runs green on Python 3.12+ with Pydantic v2.x and no network.
- Every test's failure message points at the schema invariant it protects (rely on clear assertions, not bare `assert x`).

## 7. Scope decisions (resolved 2026-04-21)

- **F-1** — logging-side-effects pattern relocated to diagnostics spec; not exercised here.
- **F-2** — case-insensitive coercion considered and deferred; not in scope for this session (would require `schema.py` edit). v3 retains Pydantic-default case-sensitive parsing.
- **F-3** — no backward-compat JSON; v3 treated as a successor.
- **F-4** — leap-day `is_minor_as_of` pinned via T-07 subcases.
- **T-22** — caption matrix expanded from 3 rows to 4 during self-audit; all `(trust_type, marital_status)` branches of `promote_seed` now covered.
- **Case count** — 30 cases across 15 clusters.

Any re-opening of F-1/F-2 or re-scoping of the test target belongs in a new spec, not this one.
