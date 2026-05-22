# `promote_seed()` Design Specification

**Date:** 2026-04-22
**Session:** 1.2_desktop (promote_seed refinement spec)
**Status:** Final
**Review:** Inline plan-review, `validation_tier: Fallback` (subagent dispatch unavailable in session). 13 findings: 1 critical, 6 important, 6 minor. All applied.

## 1. Scope

### In scope

- Analysis of the current `promote_seed()` implementation in `src/trust_generator/v3/schema.py`.
- Location decision: keep in `schema.py` vs extract to a dedicated `promote_seed.py` module.
- Full variant coverage: seed-input cross-product mapped to expected `TrustData` shape.
- Edge-case enumeration at the bounded-context boundary.
- Test coverage gap analysis against the current three promote_seed-specific tests.
- Diagnostic rule **contracts** (signatures, levels, codes, trigger conditions) that downstream sessions must implement.
- Helper extraction proposal to support post-promotion seed edits without re-promotion.

### Out of scope (non-goals, per session context)

- Modifications to Pydantic model field definitions in `schema.py` (docstring and one private helper extraction are not field changes).
- Printable generator design or layout.
- Accessibility override application at any generator.
- Diagnostic rule **implementation** — this spec defines contracts the diagnostics session must implement.
- Parser internal design — this spec specifies the parser's obligations at the `promote_seed` boundary only.
- Seed/TrustData persistence layout — GUI session concern.

## 2. Location Decision

**Decision: `promote_seed()` remains in `schema.py`.**

### Rationale

| Criterion | Evaluation |
|---|---|
| Coupling | Intrinsic. Constructs `TrustData`, reads `QuestionnaireSeed`; both live in `schema.py`. Extraction would produce a module whose sole content is glue code importing the two. |
| Imports | Zero new dependencies. Uses only `TrustType`, `MaritalStatus`, `GrantorInfo`, `TrustData`, `QuestionnaireSeed` — all local. |
| Session weight | Graph entity `critical_path` ranks `promote_seed` refinement as the lightest item. No growth pressure justifies a dedicated module. |
| Test cohesion | Existing tests import from `trust_generator.v3.schema`. Extraction adds an import surface without organizational benefit. |
| Reversibility | Extraction is mechanical. If seed-validity assertions, diagnostic emission on promotion, or seed-version migrations arrive later, the function moves in a single commit. |

### Revisit triggers

- Function body exceeds ~120 lines.
- `promote_seed` accumulates dependencies outside `schema.py` (diagnostic engine, firm_config, audit logger).
- Seed-version migration logic requires multiple promotion variants.

## 3. Current Behavior Inventory

### 3.1 Explicit projections

Four fields cross the bounded-context boundary:

| Seed field | TrustData destination | Notes |
|---|---|---|
| `trust_type` | `trust_id.trust_type` | Drives caption resolution branch. |
| `marital_status` | `trust_id.marital_status` | Drives `co_grantor` materialization. |
| `preliminary_trust_name` | `trust_id.desired_trust_name` | Empty string is legitimate; falls through to fallback naming in `TrustData.trust_name`. |
| `estate_value_estimate` | `elections.estate_value_estimate` | Controls Section-4 asset-detail gating during fill. |

### 3.2 Derived effects

**Caption resolution** — branch on `trust_type`:

- `JOINT` → `("Grantor A", "Grantor B")`
- `INDIVIDUAL` → `("Grantor", "Spouse")`

Note: `INDIVIDUAL + UNMARRIED` still sets `co_grantor_caption = "Spouse"` even though `co_grantor` is `None`. This latent value is harmless — the caption is never read when `co_grantor is None` — but is residual state worth documenting.

**`co_grantor` materialization** — `GrantorInfo()` instance created when `trust_type == JOINT` OR `marital_status == MARRIED`. Remains `None` only for `INDIVIDUAL + UNMARRIED`.

### 3.3 Explicitly dropped seed-only fields

| Seed field | Reason dropped |
|---|---|
| `consultation_date` | Paralegal workflow metadata; not trust data. |
| `paralegal_name` | Seed authorship attribution; not trust data. |
| `attorney_name` | Same as above. |
| `accessibility_overrides` | Printable-generator concern; consumed directly from seed, not via TrustData. |
| `has_pets` | Signal to the printable generator to emit the pet-trust overlay. Pet instances are collected during fill. |
| `child_count_tier` | Printable layout signal; not trust data. Children are enumerated during fill via `TrustData.children`. |

### 3.4 TrustData defaults relied upon

`promote_seed` sets four fields explicitly and relies on `TrustData`'s own field defaults for everything else. `test_trust_data_defaults_match_spec` (lines 259–291 of `tests/v3/test_schema.py`, read and verified) guards the following defaults that `promote_seed`'s behavior depends on:

- `trust_id.state_of_governing_law == "Illinois"`, `tax_id_ssn_preference == SsnOwner.GRANTOR`
- `elections.initial_trustee == GRANTORS`, `property_classification == COMMUNAL`, `distribution_standard == HEMS`, `guardianship_policy == EXPLICIT_DESIGNATIONS`
- Protective booleans: `spendthrift`, `no_contest`, `probate_coordination`, `portability` all `True`; `trustee_bond` `False`
- `co_grantor is None` (materialized conditionally by `promote_seed` only)
- All list-typed fields empty

## 4. Bounded-Context Invariants

| # | Statement | Surfacing mechanism |
|---|---|---|
| I1 | No seed-only field name appears on `TrustData`. | Test: `test_promote_seed_drops_seed_only_fields` (line 445); hardened by §7.2-T2. |
| I2 | Promotion is one-shot. `promote_seed` is called exactly once per trust, at TrustData initialization. Re-invocation on an already-populated TrustData produces a fresh instance, discarding fill state. | Convention. Codified by §7.2-T3 (`test_promote_seed_is_one_shot_initializer`). Docstring (§6.2.1). Parser contract (§6.2.3). Helper `_resolve_captions` enables seed-edit handling without re-promotion. |
| I3 | Caption/trust_type consistency is established at promotion. Post-promotion mutations can cause drift. Detection is a diagnostic-layer concern; enforcement is explicitly rejected because firm-override of captions is a design goal (graph entity `party_naming`). | Detection only — diagnostic rule `CAPTION_TRUST_TYPE_MISMATCH`. Tests specified in §8.3 (diagnostics session). |
| I4 | `accessibility_overrides` never enters `TrustData`. | Architectural — `TrustData` has no field for overrides. Test: `test_promote_seed_drops_seed_only_fields` asserts absence. Whether other generators (final trust document) should consider accessibility is a separate question (open in §9). |
| I5 | `promote_seed` fabricates nothing. Every TrustData field not set by the four projections retains its own type default. | Tests: `test_trust_data_defaults_match_spec` + §7.2-T1 (`test_promote_seed_projects_estate_value_across_domain`). |

## 5. Variant Coverage

### 5.1 Domain note

`promote_seed` operates on the full typed cross-product of its input axes:

- `trust_type`: 2 values (JOINT, INDIVIDUAL)
- `marital_status`: 2 values (MARRIED, UNMARRIED)
- `estate_value_estimate`: 3 values (BELOW_THRESHOLD, ABOVE_THRESHOLD, DECLINED_TO_ESTIMATE)
- `child_count_tier`: 3 values (NONE, ONE_TO_FIVE, SIX_PLUS)
- `preliminary_trust_name`, `has_pets`, and seed-only fields do not affect output shape.

Full cross-product: **2 × 2 × 3 × 3 = 36 combinations.**

> **Reconciliation of printable variant count (resolved):** The graph entity `printable_variants` records "18 total = 6 base × 3 child-count." The 6-base collapse derives as follows:
>
> - **Marital/type axis (3 printable variants, not 4):** `JT+MR` and `IN+MR` have identical field requirements but differ in section language → two distinct printable variants. `IN+UM` is a third. `JT+UM` is legally nonsensical (a joint trust presumes co-grantors in an enduring partnership; `UNMARRIED` negates the premise) and excluded.
> - **Estate-value axis (2 printable branches, not 3):** `BELOW_THRESHOLD` is its own branch; `ABOVE_THRESHOLD` and `DECLINED_TO_ESTIMATE` collapse to one branch because both trigger full asset-detail collection.
> - **Child-count tier (3 variants):** unchanged.
>
> `3 × 2 × 3 = 18` printable variants. This collapse is a printable-generator concern; `promote_seed` itself operates on the full typed cross-product (36 combinations producing 12 distinct TrustData shapes) because it is unopinionated about which typed combinations are "real." §5.4 contrasts the two spaces.

### 5.2 Output shape dimensions

Across the 36 combinations, the resulting `TrustData` differs along **six** fields:

1. `trust_id.trust_type`
2. `trust_id.marital_status`
3. `trust_id.grantor_caption`
4. `trust_id.co_grantor_caption`
5. `co_grantor` presence (`GrantorInfo()` or `None`)
6. `elections.estate_value_estimate`

`preliminary_trust_name` projection is orthogonal (unchanged pass-through across all 36 rows).

### 5.3 Full variant table

Abbreviations: `JT=JOINT`, `IN=INDIVIDUAL`; `MR=MARRIED`, `UM=UNMARRIED`; `BT=BELOW_THRESHOLD`, `AT=ABOVE_THRESHOLD`, `DC=DECLINED_TO_ESTIMATE`; `N=NONE`, `1-5=ONE_TO_FIVE`, `6+=SIX_PLUS`. `cg?`: ✓ = `co_grantor` materialized as `GrantorInfo()`, ✗ = `None`.

| # | trust_type | marital | estate | children | grantor_caption | co_grantor_caption | cg? | elections.estate_value |
|---|---|---|---|---|---|---|---|---|
| 1 | JT | MR | BT | N | Grantor A | Grantor B | ✓ | BELOW_THRESHOLD |
| 2 | JT | MR | BT | 1-5 | Grantor A | Grantor B | ✓ | BELOW_THRESHOLD |
| 3 | JT | MR | BT | 6+ | Grantor A | Grantor B | ✓ | BELOW_THRESHOLD |
| 4 | JT | MR | AT | N | Grantor A | Grantor B | ✓ | ABOVE_THRESHOLD |
| 5 | JT | MR | AT | 1-5 | Grantor A | Grantor B | ✓ | ABOVE_THRESHOLD |
| 6 | JT | MR | AT | 6+ | Grantor A | Grantor B | ✓ | ABOVE_THRESHOLD |
| 7 | JT | MR | DC | N | Grantor A | Grantor B | ✓ | DECLINED_TO_ESTIMATE |
| 8 | JT | MR | DC | 1-5 | Grantor A | Grantor B | ✓ | DECLINED_TO_ESTIMATE |
| 9 | JT | MR | DC | 6+ | Grantor A | Grantor B | ✓ | DECLINED_TO_ESTIMATE |
| 10 | JT | UM | BT | N | Grantor A | Grantor B | ✓ | BELOW_THRESHOLD |
| 11 | JT | UM | BT | 1-5 | Grantor A | Grantor B | ✓ | BELOW_THRESHOLD |
| 12 | JT | UM | BT | 6+ | Grantor A | Grantor B | ✓ | BELOW_THRESHOLD |
| 13 | JT | UM | AT | N | Grantor A | Grantor B | ✓ | ABOVE_THRESHOLD |
| 14 | JT | UM | AT | 1-5 | Grantor A | Grantor B | ✓ | ABOVE_THRESHOLD |
| 15 | JT | UM | AT | 6+ | Grantor A | Grantor B | ✓ | ABOVE_THRESHOLD |
| 16 | JT | UM | DC | N | Grantor A | Grantor B | ✓ | DECLINED_TO_ESTIMATE |
| 17 | JT | UM | DC | 1-5 | Grantor A | Grantor B | ✓ | DECLINED_TO_ESTIMATE |
| 18 | JT | UM | DC | 6+ | Grantor A | Grantor B | ✓ | DECLINED_TO_ESTIMATE |
| 19 | IN | MR | BT | N | Grantor | Spouse | ✓ | BELOW_THRESHOLD |
| 20 | IN | MR | BT | 1-5 | Grantor | Spouse | ✓ | BELOW_THRESHOLD |
| 21 | IN | MR | BT | 6+ | Grantor | Spouse | ✓ | BELOW_THRESHOLD |
| 22 | IN | MR | AT | N | Grantor | Spouse | ✓ | ABOVE_THRESHOLD |
| 23 | IN | MR | AT | 1-5 | Grantor | Spouse | ✓ | ABOVE_THRESHOLD |
| 24 | IN | MR | AT | 6+ | Grantor | Spouse | ✓ | ABOVE_THRESHOLD |
| 25 | IN | MR | DC | N | Grantor | Spouse | ✓ | DECLINED_TO_ESTIMATE |
| 26 | IN | MR | DC | 1-5 | Grantor | Spouse | ✓ | DECLINED_TO_ESTIMATE |
| 27 | IN | MR | DC | 6+ | Grantor | Spouse | ✓ | DECLINED_TO_ESTIMATE |
| 28 | IN | UM | BT | N | Grantor | Spouse | ✗ | BELOW_THRESHOLD |
| 29 | IN | UM | BT | 1-5 | Grantor | Spouse | ✗ | BELOW_THRESHOLD |
| 30 | IN | UM | BT | 6+ | Grantor | Spouse | ✗ | BELOW_THRESHOLD |
| 31 | IN | UM | AT | N | Grantor | Spouse | ✗ | ABOVE_THRESHOLD |
| 32 | IN | UM | AT | 1-5 | Grantor | Spouse | ✗ | ABOVE_THRESHOLD |
| 33 | IN | UM | AT | 6+ | Grantor | Spouse | ✗ | ABOVE_THRESHOLD |
| 34 | IN | UM | DC | N | Grantor | Spouse | ✗ | DECLINED_TO_ESTIMATE |
| 35 | IN | UM | DC | 1-5 | Grantor | Spouse | ✗ | DECLINED_TO_ESTIMATE |
| 36 | IN | UM | DC | 6+ | Grantor | Spouse | ✗ | DECLINED_TO_ESTIMATE |

### 5.4 Collapse observations

- **`child_count_tier`** is dropped entirely. Rows within each `(trust_type, marital_status, estate)` triplet produce identical TrustData — the structural evidence that printable-layout concerns do not leak into TrustData.
- **Captions** depend only on `trust_type`. Rows 28–36 demonstrate the latent-caption state: `co_grantor_caption = "Spouse"` is set but `co_grantor is None`.
- **`co_grantor`** materialization collapses three axes: present for all JT rows and for all IN+MR rows; absent only for IN+UM rows.
- **`estate_value_estimate`** passes through unchanged.
- The 36 distinct inputs produce **12 distinct TrustData shapes** (4 caption/cg combinations × 3 estate values).
- **Relationship to the 18 printable variants:** `promote_seed`'s 12-shape output space is orthogonal to the printable generator's 18-variant space. The printable applies three collapses: excludes `JT+UM` as legally nonsensical, recognizes `JT+MR` and `IN+MR` as field-equivalent (but renders them as two distinct variants because section language differs), and merges `AT`/`DC` into one estate branch. `promote_seed` applies none of these — it faithfully projects every typed input to the corresponding TrustData shape without interpreting which inputs are "real variants." The collapse is the printable generator's business; the schema's business is fidelity.

## 6. Edge Cases

### 6.1 Seed-fill disagreement — diagnostic rule contract

**Scenario:** Paralegal captures `trust_type=JOINT` at consultation. `promote_seed` produces TrustData with captions `"Grantor A"/"Grantor B"` and `co_grantor=GrantorInfo()`. Fill phase mutates `trust_id.trust_type=INDIVIDUAL` based on the parsed questionnaire.

**Resulting state:** `trust_type=INDIVIDUAL` but captions remain `"Grantor A"/"Grantor B"`; `co_grantor` is still populated. Internally inconsistent TrustData. Generator would emit "Grantor A" on a document asserting INDIVIDUAL.

**Resolution:** Detected by diagnostic rule `CAPTION_TRUST_TYPE_MISMATCH`.

#### 6.1.1 Diagnostic rule contract

To be implemented in the diagnostics session.

| Field | Value |
|---|---|
| `code` | `CAPTION_TRUST_TYPE_MISMATCH` |
| `level` | `DiagnosticLevel.WARNING` |
| `source` | `DiagnosticSource.BUSINESS_RULE` |
| `context` | `DiagnosticContext.BOTH` |
| `field_path` | `"trust_id.grantor_caption"` — and a second diagnostic with `"trust_id.co_grantor_caption"` if that field also mismatches |
| `message template` | `"Caption {caption!r} does not match expected default for trust_type={trust_type.value} (expected {expected!r}). If this is intentional, disable CAPTION_TRUST_TYPE_MISMATCH in the firm_config rules directory."` |

**Trigger pseudocode:**

```text
expected_grantor, expected_co_grantor = _resolve_captions(trust_type)

If grantor_caption != expected_grantor:
    emit diagnostic for grantor_caption

If co_grantor is not None:
    If co_grantor_caption != expected_co_grantor:
        emit diagnostic for co_grantor_caption
```

**Why compare against `_resolve_captions()` rather than literal strings:** reusing the helper keeps the rule synchronized with the schema's canonical defaults. If default captions ever evolve (e.g., a localization pass), the helper change propagates automatically; a literal-string rule would drift silently. Firm-override of captions is out of scope for v3 — no `[captions]` section exists in the finalized firm-config spec (`docs/superpowers/specs/2026-04-21-firm-config-design.md`), and adding one would require amending a spec whose plan is already in execution. When firm-override becomes a need, the rule extends to consult a firm-config override list; until then, the diagnostic's value is catching drift from the canonical defaults (e.g., parser bugs, test misuse, accidental direct mutation). See §9 Q5.

**Test mapping:** Contract tests in §8.3 (diagnostics session): four named tests covering the emit / symmetric / both-captions / co_grantor-None cases. Suppression is the responsibility of the rule-loader (firm disables the rule entirely via the rules-directory toggle), not of this rule's trigger logic.

### 6.2 Re-promotion and parser contract

**Scenario:** A caller invokes `promote_seed(seed)` on an already-populated TrustData after the seed has been edited.

**Current behavior:** Fresh TrustData returned; fill state discarded.

#### 6.2.1 Docstring replacement

Replaces the current docstring at lines 1084–1097 of `schema.py`:

```python
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
```

#### 6.2.2 Helper extraction: `_resolve_captions`

Extract caption resolution into a private helper so the parser can reuse it on `trust_type` change without re-promotion:

```python
def _resolve_captions(trust_type: TrustType) -> tuple[str, str]:
    """Default captions for (grantor_caption, co_grantor_caption) given trust_type.

    Used by promote_seed at initialization and by the parser when fill
    mutates trust_id.trust_type post-promotion. Firm-custom captions
    in firm_config override these defaults at application time.
    """
    if trust_type == TrustType.JOINT:
        return ("Grantor A", "Grantor B")
    return ("Grantor", "Spouse")
```

`promote_seed` body then becomes:

```python
grantor_caption, co_grantor_caption = _resolve_captions(seed.trust_type)
data.trust_id.grantor_caption = grantor_caption
data.trust_id.co_grantor_caption = co_grantor_caption
```

#### 6.2.3 Parser contract at the `promote_seed` boundary

The parser session must honor these rules:

1. **Never re-invoke `promote_seed`** on an existing TrustData.
2. **On `trust_id.trust_type` mutation** (questionnaire reveals a different trust type than the seed):
   - Call `_resolve_captions(new_trust_type)`.
   - Update both caption fields to the returned values.
   - Adjust `co_grantor` presence: materialize as `GrantorInfo()` if transitioning into a state where `co_grantor` should exist (JT or MR) and currently `None`. If already populated with fill data, preserve it (the data is meaningful; the fill decided the grantor exists).
3. **On `trust_id.marital_status` mutation**:
   - `co_grantor` adjustment rule per (2) above.
   - Captions unchanged (captions depend only on `trust_type`).

**Test mapping:** §7.2-T3 asserts I2 (one-shot). §7.2-T5 asserts `_resolve_captions` output. Parser-side tests specified in §8.3 (parser session).

### 6.3 `co_grantor` materialized but unpopulated

**Scenario:** `promote_seed` creates an empty `GrantorInfo()` for `co_grantor`. Fill never populates it.

**Behavior:** `co_grantor_full_name` returns `"[CO-GRANTOR NAME]"` sentinel. Downstream display shows the placeholder, making incomplete data visible in draft output rather than silently omitting the co-grantor.

**Assessment:** Correct by design. No action.

**Test mapping:** `test_grantor_name_sentinels` covers the `[CO-GRANTOR NAME]` sentinel path.

### 6.4 `DECLINED_TO_ESTIMATE` estate value

**Scenario:** Paralegal cannot estimate estate value and records `DECLINED_TO_ESTIMATE`.

**Behavior:** Value flows through to `elections.estate_value_estimate` unchanged. Per schema comment at lines 519–521, the fill workflow's Section-4 gating treats `DECLINED` equivalently to `ABOVE_THRESHOLD` — full asset collection is performed.

**Assessment:** Correct by design. Conservative default (collect more when uncertain). No action.

**Test mapping:** §7.2-T1 (`test_promote_seed_projects_estate_value_across_domain`) asserts pass-through for all three values including `DECLINED_TO_ESTIMATE`.

### 6.5 Accessibility overrides at generator boundary

**Scenario:** Seed carries `accessibility_overrides={"font_size": "16pt"}`. `promote_seed` drops this field.

**Assessment:** Intended bounded-context behavior. Three flow participants:

- **Seed → `promote_seed()` → TrustData** — fill/generate pipeline. Overrides are irrelevant.
- **Seed → printable_generator → PDF questionnaire** — overrides applied here, from seed directly.
- **TrustData → trust_document_generator → trust document** — a separate concern with its own styling policy. Whether the final trust document should honor questionnaire accessibility settings is an open design question (logged in §9), not a position `promote_seed` takes.

Invariant I4 is narrower than "accessibility is a printable-only concern" — it states specifically that `accessibility_overrides` is not trust data. The final-document accessibility question remains open.

**Test mapping:** `test_promote_seed_drops_seed_only_fields` asserts `accessibility_overrides` absent from TrustData (I4). No test covers the final-document question because the question itself is open (§9 Q4).

### 6.6 Empty `preliminary_trust_name`

**Scenario:** Paralegal did not capture a preliminary trust name at consultation.

**Behavior:** Empty string projected to `trust_id.desired_trust_name`. `TrustData.trust_name` falls back to `"The {Surname} Family Trust"` or `"[TRUST NAME]"` sentinel (verified by `test_trust_name_fallback_chain`, lines 317–332).

**Assessment:** Correct by design. No action.

**Test mapping:** §7.2-T4 (`test_promote_seed_projects_empty_preliminary_name_as_empty_desired_name`) asserts the pass-through; `test_trust_name_fallback_chain` asserts the downstream fallback.

### 6.7 `JOINT + UNMARRIED` combination

**Scenario:** `trust_type=JOINT` with `marital_status=UNMARRIED` — unmarried domestic partners, siblings holding joint property, parent/adult-child co-ownership, etc.

**Behavior:** `promote_seed` produces JT-style output: captions `"Grantor A"/"Grantor B"`, `co_grantor` materialized. `marital_status=UNMARRIED` flows through to `trust_id.marital_status`.

**Assessment:** Valid, uncommon, correctly handled without special-casing. Downstream implications:

- `marriage` field (`MarriageInfo`) will be an empty default — irrelevant, no marriage to record.
- Printable-generator may require a distinct variant for this combination (boilerplate for an unmarried-grantor joint trust differs from a married-grantor joint trust). This is a printable-session concern, out of scope here.
- No action required in `promote_seed`.

**Test mapping:** `test_promote_seed_caption_resolution_matrix` includes the `joint-unmarried` row, asserting JT-style captions and materialized `co_grantor` for this combination.

## 7. Test Plan

Tests are the authoritative behavioral contract for `promote_seed`. Every claim in §3, §4, and §6 either maps to an existing test or specifies a new one below. Implementation work in §8 is ordered test-first: write failing test → minimum change to pass → next test.

### 7.1 Behavioral contract matrix

Maps each behavior or invariant to the test that asserts it. Status values: **Exists** (test present, possibly hardened by a new test), **Missing** (new test required in §7.2), **Downstream contract** (test specified here; authored in a later session per §8.3). Status reflects session start; §8.1 drives transitions.

| Claim | Test | Status |
|---|---|---|
| Four fields project forward: `trust_type`, `marital_status`, `preliminary_trust_name`, `estate_value_estimate` | `test_promote_seed_projects_expected_fields` (line 429) | Exists — one combination `(JT, MR, AT)`. Extended by §7.2-T1. |
| Caption resolution by `trust_type` | `test_promote_seed_caption_resolution_matrix` (line 383) | Exists — full 2×2 matrix. |
| `co_grantor` materialization when `trust_type == JOINT` OR `marital_status == MARRIED` | `test_promote_seed_caption_resolution_matrix` (via `co_grantor_none` column) | Exists. |
| I1: no seed-only field appears on TrustData | `test_promote_seed_drops_seed_only_fields` (line 445) | Exists. Hardened by §7.2-T2. |
| I2: promotion is one-shot | — | **Missing.** §7.2-T3. |
| I3: caption/trust_type drift detection | `test_caption_trust_type_mismatch_*` | **Downstream contract** (diagnostics session, §8.3). |
| I4: `accessibility_overrides` never on TrustData | `test_promote_seed_drops_seed_only_fields` (asserts `accessibility_overrides` absence) | Exists. |
| I5: `promote_seed` fabricates nothing | `test_trust_data_defaults_match_spec` (line 259) + §7.2-T1 | Exists + extension. |
| `estate_value_estimate` propagation across all 3 values | — | **Missing.** §7.2-T1. |
| Empty `preliminary_trust_name` → empty `desired_trust_name` | Implicit at `test_schema.py:475` | Exists implicitly. Elevated by §7.2-T4. |
| Edge §6.3: unpopulated `co_grantor` yields sentinel | `test_grantor_name_sentinels` | Exists. |
| Edge §6.6: empty `preliminary_trust_name` fallback chain | `test_trust_name_fallback_chain` (line 317) | Exists. |
| Edge §6.7: `JT+UM` produces JT-style output | `test_promote_seed_caption_resolution_matrix` (row `joint-unmarried`) | Exists. |
| `_resolve_captions` helper output tuple by `trust_type` | — | **Missing, blocking for helper extraction.** §7.2-T5. |

### 7.2 New tests required

Each new test is stated as a failing assertion that the proposed implementation will make pass. The pre-change state for each test is documented so the TDD role of each is explicit: change-driving (red → green), characterization (green on first run; codifies existing behavior), or regression-guard (green on first run; protects against future drift).

#### T1 — `test_promote_seed_projects_estate_value_across_domain`

Parametrizes `projects_expected_fields`-style assertion over the full 3-value `EstateValueRange` domain.

```python
@pytest.mark.parametrize(
    "estate_value",
    [
        EstateValueRange.BELOW_THRESHOLD,
        EstateValueRange.ABOVE_THRESHOLD,
        EstateValueRange.DECLINED_TO_ESTIMATE,
    ],
)
def test_promote_seed_projects_estate_value_across_domain(
    estate_value: EstateValueRange,
):
    """estate_value_estimate projects unchanged across all three values."""
    seed = QuestionnaireSeed(estate_value_estimate=estate_value)
    data = promote_seed(seed)
    assert data.elections.estate_value_estimate == estate_value
```

**Pre-change state: green (regression guard).** Test passes against current implementation; extends coverage from one `estate_value` combination to three. Codifies the pass-through guarantee.

#### T2 — harden `test_promote_seed_drops_seed_only_fields` to `TrustData.model_fields`

Replaces `hasattr`-based assertion with canonical Pydantic v2 introspection.

```python
SEED_ONLY_FIELDS = (
    "paralegal_name",
    "attorney_name",
    "consultation_date",
    "accessibility_overrides",
    "has_pets",
    "child_count_tier",
)

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
```

**Pre-change state: green (mechanism refactor).** Test passes in both `hasattr` and `model_fields` formulations under Pydantic v2.x. The swap is a defensive hardening against future Pydantic behavior changes, not a regression driver.

#### T3 — `test_promote_seed_is_one_shot_initializer`

Asserts I2. Promotion returns fresh TrustData; mutations to one return do not leak into a subsequent call.

```python
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
```

**Pre-change state: green (characterization guard).** Test passes against current implementation (`TrustData()` always constructs fresh). Codifies I2 so a future refactor that caches or reuses an instance is caught immediately.

#### T4 — `test_promote_seed_projects_empty_preliminary_name_as_empty_desired_name`

Lifts the implicit assertion at `test_schema.py:475` into a named, single-purpose test.

```python
def test_promote_seed_projects_empty_preliminary_name_as_empty_desired_name():
    """Empty preliminary_trust_name flows through as empty desired_trust_name, enabling the fallback chain."""
    seed = QuestionnaireSeed()  # preliminary_trust_name default is ""
    data = promote_seed(seed)
    assert data.trust_id.desired_trust_name == ""
```

**Pre-change state: green (regression guard).** Test passes; adds named coverage for a behavior currently asserted only incidentally.

#### T5 — `test_resolve_captions_returns_expected_tuple`

**Blocking test for the helper extraction in §6.2.2.** Written before the helper exists; drives its creation.

```python
from trust_generator.v3.schema import _resolve_captions

@pytest.mark.parametrize(
    ("trust_type", "expected"),
    [
        (TrustType.JOINT, ("Grantor A", "Grantor B")),
        (TrustType.INDIVIDUAL, ("Grantor", "Spouse")),
    ],
)
def test_resolve_captions_returns_expected_tuple(
    trust_type: TrustType, expected: tuple[str, str]
):
    """_resolve_captions returns (grantor_caption, co_grantor_caption) by trust_type."""
    assert _resolve_captions(trust_type) == expected
```

**Pre-change state: red (change-driving).** `ImportError` — `_resolve_captions` does not yet exist. This is the session's only change-driving test: §8.1 Step 2 adds the helper body, turning this test from red to green before any refactor of `promote_seed`.

### 7.3 Test-mechanism considerations

`test_promote_seed_drops_seed_only_fields` currently uses `hasattr()`. This works under Pydantic v2.x because `BaseModel` does not surface undefined fields via `hasattr`. T2 hardens this by asserting against `TrustData.model_fields` directly — the canonical Pydantic v2 introspection API, robust to any future changes in attribute-access semantics.

## 8. TDD Implementation Plan

Every code change is driven by a test. Each step is: **write test → run → observe red/green → minimum change → run → observe green → refactor if needed → run → observe green**.

### 8.1 Work sequence for this session

The sequence is strictly ordered. Do not begin a step until the prior step is green.

**Step 0 — Precondition check.**

1. Run the full test suite.
2. Expected: **green**. If red, a latent failure predates this session; stop and resolve before proceeding. The TDD ordering below assumes a clean starting state.

**Step 1 — Codify the one-shot invariant.**

1. Add §7.2-T3 (`test_promote_seed_is_one_shot_initializer`).
2. Run the test suite.
3. Expected: **green** — current implementation already satisfies I2 because `TrustData()` always constructs fresh. The test is a codification guard, not a driver of new behavior.
4. No code change at this step. If the test is red, a latent bug predates this work; stop and investigate before proceeding.

**Step 2 — Extract `_resolve_captions` helper under test.**

1. Add §7.2-T5 (`test_resolve_captions_returns_expected_tuple`).
2. Run the test suite.
3. Expected: **red** — `ImportError` on `_resolve_captions`.
4. Minimum change: add the `_resolve_captions` function body per §6.2.2. Do NOT yet refactor `promote_seed`.
5. Run. Expected: **green** on T5. The existing `test_promote_seed_caption_resolution_matrix` is unaffected (behavior unchanged).
6. Refactor: update `promote_seed` to call `_resolve_captions` instead of inlining the branch.
7. Run. Expected: **green across the suite**. `test_promote_seed_caption_resolution_matrix` validates that the refactor preserves observable behavior.

**Step 3 — Extend estate-value coverage.**

1. Add §7.2-T1 (`test_promote_seed_projects_estate_value_across_domain`).
2. Run. Expected: **green** — current implementation already projects the value unchanged.
3. No code change. Regression guard only.

**Step 4 — Harden seed-only-fields drop assertion.**

1. Replace the body of `test_promote_seed_drops_seed_only_fields` with §7.2-T2's `TrustData.model_fields` formulation.
2. Run. Expected: **green**.
3. No behavior change; defensive hardening only.

**Step 5 — Add explicit empty-name coverage.**

1. Add §7.2-T4 (`test_promote_seed_projects_empty_preliminary_name_as_empty_desired_name`).
2. Run. Expected: **green**.

**Step 6 — Docstring replacement.**

1. No test change required — the docstring is not asserted by any test.
2. Replace the docstring per §6.2.1.
3. Run. Expected: **green** (no behavior change).

At this point the session's work is complete. Verify all tests pass, then the schema is ready for downstream sessions.

### 8.2 Code changes this session produces

Direct changes to `src/trust_generator/v3/schema.py`:

1. Add private `_resolve_captions(trust_type: TrustType) -> tuple[str, str]` helper (§6.2.2).
2. Refactor `promote_seed` body to call `_resolve_captions` (§6.2.2).
3. Replace `promote_seed` docstring with the §6.2.1 text.

Direct changes to `tests/v3/test_schema.py`:

1. Add T1, T3, T4, T5 as new test functions.
2. Rewrite T2 body in-place (same test name, hardened mechanism).

No changes to:

- `QuestionnaireSeed` or `TrustData` model field definitions.
- The four field projections.
- The `co_grantor` materialization logic.
- Any field defaults.
- Any Pydantic `model_config` settings.

### 8.3 Downstream session TDD obligations

Each downstream session arrives with tests before implementation, following the same red-green pattern. Tests below are specified here as contracts; downstream sessions author and run them.

**Diagnostics session** — implements `CAPTION_TRUST_TYPE_MISMATCH` per §6.1.1.

Required tests:

- `test_caption_trust_type_mismatch_fires_on_individual_with_joint_captions` — TrustData with `trust_type=INDIVIDUAL` and `grantor_caption="Grantor A"` emits one WARNING diagnostic with `code=CAPTION_TRUST_TYPE_MISMATCH`, `field_path="trust_id.grantor_caption"`.
- `test_caption_trust_type_mismatch_fires_on_joint_with_individual_captions` — symmetric.
- `test_caption_trust_type_mismatch_fires_on_both_captions_independently` — both captions mismatched produce two diagnostics with distinct `field_path` values.
- `test_caption_trust_type_mismatch_no_emission_when_co_grantor_is_none` — `co_grantor is None` suppresses any diagnostic on `co_grantor_caption` regardless of value.

**Parser session** — honors contract in §6.2.3.

Required tests:

- `test_parser_never_reinvokes_promote_seed` — via `unittest.mock.patch` on `promote_seed`, asserts `call_count == 0` after parser entry runs against an already-populated TrustData.
- `test_parser_updates_captions_on_trust_type_mutation` — when parse mutates `trust_id.trust_type`, captions update to `_resolve_captions(new_trust_type)` output.
- `test_parser_materializes_co_grantor_on_joint_transition` — transitioning from `(IN, UM)` to `(JT, MR)` materializes `co_grantor` as `GrantorInfo()` if currently `None`.
- `test_parser_preserves_populated_co_grantor_on_marital_transition` — already-populated `co_grantor` survives `marital_status` change.

## 9. Open Questions / Deferred

| # | Question | Owner session |
|---|---|---|
| Q1 | Should seed capture an approximate dollar estimate of estate value (Decimal), not just a range? `Elections.estate_value_approximate: Decimal \| None` exists on TrustData but has no seed counterpart. | Seed-design |
| Q2 | Should `QuestionnaireSeed` be frozen? Currently mutable — "captured at consultation" is a mental model, not a schema invariant. Post-consultation mutation is legal. | Seed-design |
| Q3 | Seed/TrustData joint persistence layout. The printable_generator reads seed directly (§6.5); this requires seed persistence distinct from TrustData persistence. | GUI |
| Q4 | Should the final trust document inherit questionnaire accessibility settings? `promote_seed` takes no position; the question is genuinely open. | Document-generator |
| Q5 | Firm-override of captions is not supported in v3. The finalized firm-config spec (`docs/superpowers/specs/2026-04-21-firm-config-design.md`) has no `[captions]` section, and its plan is already in execution. When firm-override becomes a need, add a `[captions]` section (or equivalent) and extend `CAPTION_TRUST_TYPE_MISMATCH` to consult it before emitting. | Firm-config v3.x (future) |

---

## Decision log

| # | Decision | Section |
|---|---|---|
| 1 | Keep `promote_seed()` in `schema.py`. | §2 |
| 2 | Document full 36-combination cross-product of `promote_seed` inputs; the 18 printable variants (a separate printable-generator concern) reconciled in §5.1 via field-shape equivalence of `JT+MR`/`IN+MR`, exclusion of nonsensical `JT+UM`, and `AT`/`DC` estate-branch collapse. | §5 |
| 3 | Extract `_resolve_captions(trust_type)` as a private helper. | §6.2.2 |
| 4 | Replace docstring with one-shot-initializer language. | §6.2.1 |
| 5 | Diagnostic rule `CAPTION_TRUST_TYPE_MISMATCH` — full contract specified; implementation deferred to diagnostics session. | §6.1.1 |
| 6 | `FirmCaptionsConfig` schema — contract specified; implementation deferred to firm_config session. | §6.1.2 |
| 7 | Parser contract at the `promote_seed` boundary — specified in three rules. | §6.2.3 |
| 8 | No changes to field projections, `co_grantor` materialization, dropped-field categorizations, or TrustData defaults. | §3, §8.2 |
| 9 | §7 is the authoritative test plan: every behavioral claim maps to a named existing or new test. | §7 |
| 10 | §8 follows TDD red-green ordering: no code change precedes its driving test; downstream sessions inherit the same obligation. | §8 |
| 11 | Diagnostic rule `CAPTION_TRUST_TYPE_MISMATCH` compares against hardcoded `_resolve_captions()` output, not a firm-configurable surface. Firm-override of captions is out of scope for v3 — no `[captions]` section exists in the finalized firm-config spec; adding one would require amending a spec whose plan is already in execution. Rule-level suppression (disable via firm_config's rules directory) remains available as the firm's escape hatch. Future work logged as §9 Q5. | §6.1.1, §9 Q5 |

## Plan-review summary

**Validation tier:** Fallback — inline review via `sequential-thinking`; subagent dispatch unavailable in session.

**Findings:** 13 total. All applied.

| ID | Category | Severity | Disposition |
|---|---|---|---|
| F1 | Invalid assumption | Important | §6.5 reasoning softened; final-doc accessibility moved to §9 Q4. |
| F2 | Invalid assumption | Dissolved (post-reconciliation #2) | Concern (rule false-positives on firm-custom captions) does not materialize in v3 because no firm-override surface exists. Hardcoded-defaults rule is correct for v3 scope; extension path logged as §9 Q5. |
| F3 | Missing edge case | Important | §6.7 added for JT+UM combination. |
| F4 | Missing edge case | Minor | Logged as §9 Q1 (estate_value_approximate seeding). |
| F5 | Missing edge case | Minor | Logged as §9 Q2 (seed mutability). |
| F6 | Underspecified integration | **Critical** | §6.1.1 now contains the full rule contract with trigger pseudocode against `_resolve_captions()` output. The originally-planned §6.1.2 `FirmCaptionsConfig` contract was dropped per post-reconciliation #2 (cross-spec conflict). |
| F7 | Underspecified integration | Important | §6.2.2 proposes `_resolve_captions` helper (test §7.2-T5); §6.2.3 specifies parser contract in three rules. |
| F8 | Underspecified integration | Minor | Logged as §9 Q3 (persistence layout, GUI session). |
| F9 | Over-engineering | Minor | Full 36-row table retained as test-authoring reference; §5.4 synthesis compensates for redundancy. |
| F10 | Over-engineering | Minor | §6.2.1 now provides final docstring text, not an "amendment" framing. |
| F11 | Under-specification | Important | §7.2-T2 hardens `test_promote_seed_drops_seed_only_fields` to `TrustData.model_fields`; §7.3 documents the rationale. |
| F12 | Under-specification | Dissolved | `test_trust_data_defaults_match_spec` verified (covers listed defaults plus additional protective booleans); §3.3 updated. |
| F13 | Consistency | Important | §4 I3 reworded: "detection only" — warning surfaces drift, does not enforce. |
| F14 | Consistency | Minor | §5.2 now lists six dimensions correctly (was "only five" with six items). |
| F15 | Consistency | Important | §1 out-of-scope rescoped: contracts specified here, implementation deferred. |

**Assumption inventory — confidence ratings after review:**

- **High:** four-field projection completeness (verified by reading lines 1098–1122); TrustData defaults coverage (verified via reading `test_trust_data_defaults_match_spec`); `child_count_tier` as layout signal (confirmed by `printable_variants` graph entity); empty `preliminary_trust_name` fallback chain (verified via `test_trust_name_fallback_chain`); `GrantorInfo` sentinel behavior (verified via `co_grantor_full_name` property read).
- **Medium-High:** captions as diagnostic-layer concern rather than schema-enforced (confirmed by `party_naming` graph entity; rule design in §6.1.1 reflects firm-override goal).
- **Medium:** one-shot initializer invariant (inferred from current `TrustData()` construction; now explicit via §7.2-T3 test, §6.2.1 docstring, and §6.2.3 parser contract); accessibility-override boundary scope (reasoning narrowed to "overrides are not trust data"; final-document question logged as §9 Q4).
- **Low:** none remaining.

**Post-review reconciliation note (outside the original 13 findings):** The 6-vs-12 base-variant count ambiguity in §5.1 has been resolved by user confirmation — 6 base = 3 marital/type linguistic variants × 2 estate-branch collapse. The prior "flag for printable-generator session" has been replaced with a derivation in §5.1 and a corresponding contrast in §5.4 between `promote_seed`'s 12-shape output space and the printable's 18-variant space.

**Post-review reconciliation note #2 (outside the original 13 findings):** Cross-spec compatibility check against `docs/superpowers/specs/2026-04-21-firm-config-design.md` revealed that the finalized firm-config spec has no `[captions]` section and uses `extra="forbid"`, blocking the originally-specified `FirmCaptionsConfig` contract. The rule has been downscoped to compare against hardcoded `_resolve_captions()` output (§6.1.1); §6.1.2 has been removed; §6.2.3 parser contract no longer references `firm_config.captions`; §8.3 firm_config test obligations have been removed and one parser test was narrowed to exclude the nonsensical `(JT, UM)` transition. Firm-override of captions is logged as §9 Q5 for future work. F2 dissolves in light of this reconciliation (see findings table above). The diagnostic's detection value is preserved (drift from defaults is still surfaced); only the speculative firm-override mechanism is deferred.

**Post-review reconciliation note #3 (Option 4 adversarial pass, outside the original 13 findings):** A targeted adversarial pass on the restructured §7/§8 surfaced six findings (two important, four minor). Resolutions applied: §7.1 matrix header gained a temporal-frame clarification ("Status reflects session start; §8.1 drives transitions"); §7.2 pre-change states relabeled from uniform "Red state" to mode-accurate labels (change-driving / characterization / regression-guard); §8.1 gained Step 0 (precondition check); §8.3 `test_parser_never_reinvokes_promote_seed` now specifies `unittest.mock.patch` mechanism; §8.3 `test_parser_materializes_co_grantor_on_joint_transition` narrowed from `(JT, *)` to `(JT, MR)` to exclude the nonsensical combination flagged in §6.7.
