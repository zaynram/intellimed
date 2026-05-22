# `promote_seed()` Refinement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute §8.2 of the design spec — extract `_resolve_captions` helper, refactor `promote_seed` body to call it, replace the docstring, and add five tests (four new + one rewrite) codifying the bounded-context contract.

**Architecture:** Six TDD cycles against two files. No Pydantic field-definition changes. No new exports. Behavioral surface of `promote_seed` is unchanged; the only observable additions are the private `_resolve_captions` helper (imported by one test and, in a later session, by the parser) and a tighter docstring.

**Tech Stack:** Python 3.12+, Pydantic v2, pytest, pixi.

**Spec:** `docs/superpowers/specs/2026-04-22-promote-seed-design.md`.

**Scope lock (per user confirmation):** §8.2 only. The §8.3 downstream-session obligations (diagnostic rule `CAPTION_TRUST_TYPE_MISMATCH`, parser contract) are **out of scope** for this plan and will be handled in dedicated sessions.

---

## File map

**Modified:**

- `src/trust_generator/v3/schema.py` — one new private helper (`_resolve_captions`), one refactor inside `promote_seed` body, one docstring replacement. No other changes.
- `tests/v3/test_schema.py` — one added import (`_resolve_captions`), four new tests (T1, T3, T4, T5), one existing test rewritten in place (T2), one module-level constant (`SEED_ONLY_FIELDS`).

**Created:** none.

**Field definitions on `TrustData`, `QuestionnaireSeed`, `GrantorInfo`, `Elections`, etc.:** unchanged.

---

## Commit plan

Per user confirmation (Q2 = "one per TDD cycle"):

| # | Commit | Produces |
|---|---|---|
| 1 | `test(v3/schema): codify promote_seed one-shot invariant (T3)` | Task 1 |
| 2 | `refactor(v3/schema): extract _resolve_captions helper (T5)` | Task 2 |
| 3 | `test(v3/schema): cover estate_value_estimate across full domain (T1)` | Task 3 |
| 4 | `test(v3/schema): harden seed-only-field drop to model_fields (T2)` | Task 4 |
| 5 | `test(v3/schema): codify empty preliminary_trust_name passthrough (T4)` | Task 5 |
| 6 | `docs(v3/schema): rewrite promote_seed docstring as one-shot initializer` | Task 6 |

Six commits on branch `v3.0.0` (the active feature branch — no worktree).

### Gate convention (applies to every task)

Per user directive, **every commit is gated by `pixi run check`** (the composite lint + typecheck + test gate). Lint/typecheck failures are treated exactly like test failures: **stop, fix, and re-run before the commit.** This appears as an explicit step in every task below and is not optional.

`pixi run check` is expected to invoke the full test suite as part of its composite, so the scoped `pixi run test <test_name>` step preserved in each task is for fast TDD-cycle feedback, not a substitute for the gate. The positional argument is a `pytest -k` name pattern (substring match on test function names, passed to the pixi task's templated `{{ match }}` variable); the pixi task runs with `--ignore-glob **/$TASK_EXCLUDE` applied, so v2/ code is already excluded.

---

## Task 0: Precondition check

Per spec §8.1 Step 0. Not a commit; just a guardrail that the suite + lint + typecheck start green. If any of them don't, a latent failure predates this plan and must be resolved before continuing.

**Files:** none.

- [ ] **Step 1: Run the full project gate.**

  Run:
  ```bash
  pixi run check
  ```
  Expected: **ALL PASS** — tests, lint, and typecheck. The `<test lang="python" tool="pixi" status="pass"/>` marker at session start attests to the test portion; this step verifies the gate as a whole is clean before we touch anything.

  If any portion is red: **stop**. Open an issue or resolve the failure before beginning Task 1. Do not begin the plan on a red gate.

No commit.

---

## Task 1: Codify the one-shot-initializer invariant (T3)

Implements spec §7.2-T3 and §8.1 Step 1. Asserts invariant I2 from §4.

**Pre-change state:** green (characterization guard). Current `promote_seed` returns a fresh `TrustData()` per call, so the test passes immediately against the unchanged implementation. The test exists to **pin** that behavior so a future refactor (e.g., instance reuse, caching) is caught.

**Files:**

- Modify: `tests/v3/test_schema.py` — append new test to the end of section `4.11 promote_seed fidelity` (immediately after `test_promote_seed_drops_seed_only_fields`, which currently ends at line 476).

- [ ] **Step 1: Add the test.**

  Append after line 476 of `tests/v3/test_schema.py`:

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

- [ ] **Step 2: Run the new test.**

  Run:
  ```bash
  pixi run test test_promote_seed_is_one_shot_initializer
  ```
  Expected: **PASS** (the single test, run via `pytest -k`).

  If red: the test is catching a latent bug — not a driver of new behavior in this plan. Stop and investigate before proceeding.

- [ ] **Step 3: Run the full project gate (pre-commit).**

  Run:
  ```bash
  pixi run check
  ```
  Expected: **ALL PASS** (tests, lint, typecheck). If red, treat like a test failure: fix the underlying issue (lint, type, or test), re-run `pixi run check`, and only then proceed to commit.

- [ ] **Step 4: Commit.**

  ```bash
  git add tests/v3/test_schema.py
  git commit -m "$(cat <<'EOF'
  test(v3/schema): codify promote_seed one-shot invariant (T3)

  Characterization guard for invariant I2 (spec §4, §7.2-T3): re-invocation
  of promote_seed() returns a fresh TrustData and discards any mutations
  made to prior returns. Test passes against the current implementation;
  pins the behavior against future drift (e.g., instance reuse, caching).
  EOF
  )"
  ```

---

## Task 2: Extract `_resolve_captions` helper under a change-driving test (T5)

Implements spec §7.2-T5 (test) and §6.2.2 (helper + refactor). Combines §8.1 Step 2's three sub-phases (red → green → refactor) into a single commit so the feature addition and its in-place consumer arrive together.

**Pre-change state:** red (change-driving). `_resolve_captions` does not yet exist; the test import fails with `ImportError`. This is the only change-driving test in the plan.

**Files:**

- Modify: `src/trust_generator/v3/schema.py`
  - Add the `_resolve_captions` helper immediately above the `def promote_seed(...)` line at schema.py:1083.
  - Refactor the caption-resolution block inside `promote_seed` (currently lines 1108–1113) to call `_resolve_captions`.
- Modify: `tests/v3/test_schema.py`
  - Insert `_resolve_captions` into the top-of-file `from trust_generator.v3.schema import (...)` block (immediately after `_ChildRelationship`, before `promote_seed` — matching the existing ordering).
  - Append the new parametrized test to the end of the file.

- [ ] **Step 1: Add the failing test.**

  Append the following at the end of `tests/v3/test_schema.py`:

  ```python


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
  ```

  And update the import block near the top of `tests/v3/test_schema.py` — change:

  ```python
      _ChildRelationship,
      promote_seed,
  )
  ```

  to:

  ```python
      _ChildRelationship,
      _resolve_captions,
      promote_seed,
  )
  ```

- [ ] **Step 2: Run to confirm red.**

  Run:
  ```bash
  pixi run test test_resolve_captions_returns_expected_tuple
  ```
  Expected: **RED (collection error — expected; the rest of the module's coverage is recovered at Step 6).** The failure surfaces as `ImportError: cannot import name '_resolve_captions' from 'trust_generator.v3.schema'`, which aborts pytest collection for the entire module. `pytest -k` can't match a test it never collected, so expect the run to report zero tests executed and the import error at collection time. That's fine for this red phase — the missing-symbol import is the signal we need.

- [ ] **Step 3: Add `_resolve_captions` to `schema.py` (do NOT refactor `promote_seed` yet).**

  Insert immediately above the `def promote_seed(seed: QuestionnaireSeed) -> TrustData:` line at schema.py:1083:

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

  Note: two blank lines between `_resolve_captions` and `def promote_seed` to match PEP 8 module-level spacing used elsewhere in the file.

- [ ] **Step 4: Run to confirm the new test passes; `promote_seed` still uses its inline branch at this point.**

  Run:
  ```bash
  pixi run test test_resolve_captions_returns_expected_tuple
  ```
  Expected: **PASS** — both parametrized rows (`[joint]`, `[individual]`). The existing `test_promote_seed_caption_resolution_matrix` still passes (run separately if you want to confirm: `pixi run test test_promote_seed_caption_resolution_matrix`), but that's covered by Step 6's full-suite run.

- [ ] **Step 5: Refactor `promote_seed` to call the helper.**

  Replace the caption-resolution block at schema.py:1104–1113:

  ```python
      # Caption resolution from (trust_type, marital_status):
      #   Joint                -> "Grantor A" / "Grantor B"
      #   Individual + married -> "Grantor"   / "Spouse"
      #   Individual + single  -> "Grantor"   / (co_grantor omitted)
      if seed.trust_type == TrustType.JOINT:
          data.trust_id.grantor_caption = "Grantor A"
          data.trust_id.co_grantor_caption = "Grantor B"
      else:
          data.trust_id.grantor_caption = "Grantor"
          data.trust_id.co_grantor_caption = "Spouse"
  ```

  with:

  ```python
      grantor_caption, co_grantor_caption = _resolve_captions(seed.trust_type)
      data.trust_id.grantor_caption = grantor_caption
      data.trust_id.co_grantor_caption = co_grantor_caption
  ```

  The comment block is removed — the helper's docstring now owns the explanation.

- [ ] **Step 6: Run the full suite to confirm behavior is preserved.**

  Run:
  ```bash
  pixi run test
  ```
  Expected: **ALL PASS.** The default `match=test_` selects every test function; `test_promote_seed_caption_resolution_matrix` (all four parametrized rows) guards the refactor — if captions drift from their prior values, it fails here.

- [ ] **Step 7: Run the full project gate (pre-commit).**

  Run:
  ```bash
  pixi run check
  ```
  Expected: **ALL PASS** (tests, lint, typecheck). The new `_resolve_captions` helper and the refactored `promote_seed` body must both clear lint + type gates. If red, treat like a test failure: fix, re-run `pixi run check`, and only then proceed to commit.

- [ ] **Step 8: Commit.**

  ```bash
  git add src/trust_generator/v3/schema.py tests/v3/test_schema.py
  git commit -m "$(cat <<'EOF'
  refactor(v3/schema): extract _resolve_captions helper (T5)

  Adds private helper _resolve_captions(trust_type) that returns the
  default (grantor_caption, co_grantor_caption) tuple. promote_seed()
  now routes caption resolution through the helper instead of inlining
  the if/else branch. Parser (future session) will consume the same
  helper on post-promotion trust_type mutation per spec §6.2.3.

  New test test_resolve_captions_returns_expected_tuple drove the
  extraction; test_promote_seed_caption_resolution_matrix guards the
  behavior-preservation of the refactor.
  EOF
  )"
  ```

---

## Task 3: Extend estate-value projection coverage (T1)

Implements spec §7.2-T1 and §8.1 Step 3. Converts the single-estate-value assertion in `test_promote_seed_projects_expected_fields` (which only covers `ABOVE_THRESHOLD`) into a parametrized sweep over the full `EstateValueRange` domain.

**Pre-change state:** green (regression guard). `promote_seed` already projects `estate_value_estimate` unchanged for all three values; the test documents this completely.

**Files:**

- Modify: `tests/v3/test_schema.py` — append after `test_resolve_captions_returns_expected_tuple` (added in Task 2).

- [ ] **Step 1: Add the test.**

  Append at the end of `tests/v3/test_schema.py`:

  ```python


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
  ```

- [ ] **Step 2: Run.**

  Run:
  ```bash
  pixi run test test_promote_seed_projects_estate_value_across_domain
  ```
  Expected: **PASS** for all three parametrized rows (`[below]`, `[above]`, `[declined]`).

- [ ] **Step 3: Run the full project gate (pre-commit).**

  Run:
  ```bash
  pixi run check
  ```
  Expected: **ALL PASS** (tests, lint, typecheck). If red, treat like a test failure: fix, re-run `pixi run check`, and only then proceed to commit.

- [ ] **Step 4: Commit.**

  ```bash
  git add tests/v3/test_schema.py
  git commit -m "$(cat <<'EOF'
  test(v3/schema): cover estate_value_estimate across full domain (T1)

  Expands coverage from a single (JT, MR, ABOVE_THRESHOLD) combination
  to a parametrized sweep over the three-value EstateValueRange domain
  (BELOW_THRESHOLD, ABOVE_THRESHOLD, DECLINED_TO_ESTIMATE). Regression
  guard per spec §7.2-T1; asserts the "fabricates nothing" invariant I5.
  EOF
  )"
  ```

---

## Task 4: Harden seed-only-field drop to `TrustData.model_fields` (T2)

Implements spec §7.2-T2 and §8.1 Step 4. Rewrites the body of the existing `test_promote_seed_drops_seed_only_fields` (currently at `tests/v3/test_schema.py:445`) to assert against `TrustData.model_fields` rather than `hasattr()`. Hoists the seed-only field names into a module-level `SEED_ONLY_FIELDS` constant.

**Pre-change state:** green (mechanism refactor). Both the old `hasattr`-based formulation and the new `model_fields`-based formulation pass under Pydantic v2. The swap is a defensive hardening: `hasattr` on a Pydantic model is higher-level and could shift semantics across Pydantic versions; `model_fields` is the canonical v2 introspection API and more stable.

**Files:**

- Modify: `tests/v3/test_schema.py`
  - Add module-level `SEED_ONLY_FIELDS` constant immediately above the `§4.11 promote_seed fidelity` section header comment (around line 424).
  - Rewrite the body of `test_promote_seed_drops_seed_only_fields` (`tests/v3/test_schema.py:445-476`).

- [ ] **Step 1: Add the `SEED_ONLY_FIELDS` constant.**

  Insert immediately above the `# ---\n# 4.11 promote_seed fidelity\n# ---` header comment at `tests/v3/test_schema.py:424`:

  ```python
  SEED_ONLY_FIELDS = (
      "paralegal_name",
      "attorney_name",
      "consultation_date",
      "accessibility_overrides",
      "has_pets",
      "child_count_tier",
  )


  ```

- [ ] **Step 2: Rewrite the test body.**

  Replace the existing `test_promote_seed_drops_seed_only_fields` at `tests/v3/test_schema.py:445-476`:

  ```python
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

  with:

  ```python
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

- [ ] **Step 3: Run.**

  Run:
  ```bash
  pixi run test test_promote_seed_drops_seed_only_fields
  ```
  Expected: **PASS.** No behavior change, just assertion mechanism.

- [ ] **Step 4: Run the full project gate (pre-commit).**

  Run:
  ```bash
  pixi run check
  ```
  Expected: **ALL PASS** (tests, lint, typecheck). If red, treat like a test failure: fix, re-run `pixi run check`, and only then proceed to commit.

- [ ] **Step 5: Commit.**

  ```bash
  git add tests/v3/test_schema.py
  git commit -m "$(cat <<'EOF'
  test(v3/schema): harden seed-only-field drop to model_fields (T2)

  Replaces hasattr()-based assertion with TrustData.model_fields lookup
  (the canonical Pydantic v2 introspection API). Hoists seed-only field
  names into a module-level SEED_ONLY_FIELDS constant. No behavior
  change; defensive hardening against future Pydantic semantics drift.
  Per spec §7.2-T2 and §7.3.
  EOF
  )"
  ```

---

## Task 5: Add explicit empty preliminary-name coverage (T4)

Implements spec §7.2-T4 and §8.1 Step 5. Lifts the implicit assertion at `tests/v3/test_schema.py:475` (part of `test_promote_seed_drops_seed_only_fields`) into a named, single-purpose test.

**Pre-change state:** green (regression guard). The behavior — empty `preliminary_trust_name` flows through as empty `desired_trust_name` — is already asserted incidentally; this test gives it a name.

**Files:**

- Modify: `tests/v3/test_schema.py` — append after `test_promote_seed_projects_estate_value_across_domain` (added in Task 3).

- [ ] **Step 1: Add the test.**

  Append at the end of `tests/v3/test_schema.py`:

  ```python


  def test_promote_seed_projects_empty_preliminary_name_as_empty_desired_name():
      """Empty preliminary_trust_name flows through as empty desired_trust_name, enabling the fallback chain."""
      seed = QuestionnaireSeed()  # preliminary_trust_name default is ""
      data = promote_seed(seed)
      assert data.trust_id.desired_trust_name == ""
  ```

- [ ] **Step 2: Run.**

  Run:
  ```bash
  pixi run test test_promote_seed_projects_empty_preliminary_name_as_empty_desired_name
  ```
  Expected: **PASS.**

- [ ] **Step 3: Run the full project gate (pre-commit).**

  Run:
  ```bash
  pixi run check
  ```
  Expected: **ALL PASS** (tests, lint, typecheck). If red, treat like a test failure: fix, re-run `pixi run check`, and only then proceed to commit.

- [ ] **Step 4: Commit.**

  ```bash
  git add tests/v3/test_schema.py
  git commit -m "$(cat <<'EOF'
  test(v3/schema): codify empty preliminary_trust_name passthrough (T4)

  Lifts the implicit assertion at test_schema.py:475 into a named,
  single-purpose test. Empty preliminary_trust_name flows through as
  empty desired_trust_name; the trust_name fallback chain takes over
  downstream (guarded by test_trust_name_fallback_chain). Regression
  guard per spec §7.2-T4 and §6.6.
  EOF
  )"
  ```

---

## Task 6: Replace `promote_seed` docstring

Implements spec §8.1 Step 6 and §6.2.1. No behavior change. No test change — the docstring is not asserted by any test.

**Files:**

- Modify: `src/trust_generator/v3/schema.py` — replace the docstring at schema.py:1084-1097.

- [ ] **Step 1: Replace the docstring.**

  Replace the docstring block at schema.py:1084-1097:

  ```python
      """Translate consultation-captured seed metadata into an initial TrustData.

      This is the bounded-context translation. Seed fields that have a TrustData
      counterpart project forward; seed-only concerns (paralegal identity, print
      options, accessibility overrides) are dropped. Fields not populated by the
      seed default to TrustData's own defaults — nothing is fabricated.

      Notably NOT projected:
        - ``consultation_date``, ``paralegal_name``, ``attorney_name`` (seed-only)
        - ``accessibility_overrides`` (printable generator concern, not legal data)
        - ``has_pets`` (signal to the generator, but the Pet list itself is built
          during fill, not at promotion)
        - ``child_count_tier`` (signal for print layout; not itself trust data)
      """
  ```

  with:

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

- [ ] **Step 2: Run the full suite.**

  Run:
  ```bash
  pixi run test
  ```
  Expected: **ALL PASS.** Docstring changes cannot affect behavior; this is a sanity check only.

- [ ] **Step 3: Run the full project gate (pre-commit).**

  Run:
  ```bash
  pixi run check
  ```
  Expected: **ALL PASS** (tests, lint, typecheck). If red, treat like a test failure: fix, re-run `pixi run check`, and only then proceed to commit.

- [ ] **Step 4: Commit.**

  ```bash
  git add src/trust_generator/v3/schema.py
  git commit -m "$(cat <<'EOF'
  docs(v3/schema): rewrite promote_seed docstring as one-shot initializer

  Replaces the promote_seed() docstring with the §6.2.1 text from the
  design spec: explicit one-shot-initializer framing, parser-responsibility
  note for post-promotion seed edits, and a pointer to _resolve_captions()
  for caption/co_grantor adjustments. No behavior change.
  EOF
  )"
  ```

---

## Post-implementation verification

Every task ends with a `pixi run check` gate, so by the time Task 6 commits, the full gate has already been exercised six times. As a belt-and-suspenders sanity pass, run it once more on the clean post-commit tree:

```bash
pixi run check
```

Expected: **ALL PASS**. If this surfaces a new failure that the per-task gates missed, investigate — it likely indicates a cross-task interaction (unlikely given the narrow scope, but worth confirming). Do not fix failures rooted outside `src/trust_generator/v3/schema.py` or `tests/v3/test_schema.py` — those are pre-existing and out of scope.

---

## Self-review checklist (ran before handoff)

**1. Spec coverage (§8.2 code changes):**
- `_resolve_captions` helper — Task 2 Step 3.
- `promote_seed` body refactor — Task 2 Step 5.
- `promote_seed` docstring replacement — Task 6 Step 1.

**Spec coverage (§8.2 test changes):**
- T1 — Task 3.
- T2 rewrite — Task 4 (with `SEED_ONLY_FIELDS` constant).
- T3 — Task 1.
- T4 — Task 5.
- T5 (change-driving) — Task 2.

**2. Placeholder scan:** No TBDs, no "implement later," no "write tests similar to above" — every step contains its code and command verbatim.

**3. Type consistency:**
- Test function names match exactly across plan tasks and spec §7.2.
- `_resolve_captions` signature `(TrustType) -> tuple[str, str]` matches spec §6.2.2.
- Import ordering in `tests/v3/test_schema.py` — underscore-prefixed names (`_ChildRelationship`, `_resolve_captions`) appear together, followed by `promote_seed`, matching existing convention.
- `SEED_ONLY_FIELDS` is referenced in Task 4 Step 2 (where the tuple is used) after being defined in Task 4 Step 1 (where the constant is inserted).

**4. §8.3 out-of-scope items confirmed:**
- `CAPTION_TRUST_TYPE_MISMATCH` diagnostic rule (§6.1.1) — diagnostics session.
- Parser contract tests at the `promote_seed` boundary (§6.2.3, §8.3) — parser session.
- Firm-override of captions / `[captions]` section in firm-config — future v3.x work (spec §9 Q5).

**5. Command shape:** `pixi run test <name_pattern>` matches the registered pixi task (`<task index="4" name="test" usage="pixi run test [match=test_]"/>`), which binds the positional arg to `{{ match }}` and runs `pytest $PYTEST_EXTRA_ARGS -k {{ match }} -v` from `tests/` with `--ignore-glob **/v2` applied. Substring matching via `pytest -k` on full test names suffices for each task's single-test verification. Invoking `pixi run test` with no argument uses the default pattern `test_`, which matches every test function — used for full-suite verification in Task 2 Step 6 and Task 6 Step 2.

---

## Execution handoff

**Plan complete. Path:** `docs/superpowers/plans/2026-04-23-promote-seed.md`.

**Execution mode** (per user confirmation in command args): **inline batched** via `superpowers:executing-plans`. A plan-review pass runs first, concerns are resolved, and then implementation proceeds with batched checkpoints.
