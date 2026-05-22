# Diagnostics Engine Starter Rules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land cycles 7-9 of the diagnostics engine spec — three starter rules demonstrating the three `DiagnosticSource` categories (`SCHEMA`, `BUSINESS_RULE`, `EXTRACTION`) — and turn the engine's outer Cycle 1 integration test green.

**Architecture:** The engine landed by the sibling `2026-04-23-diagnostics-engine-core` plan ships an empty `builtin.yaml` (`[]`). This plan appends three YAML rule entries (one per cycle, each rule self-contained) and authors three pytest test functions in a single `test_starter_rules.py` file. No production-code changes outside the YAML rules file. The final task removes the `pytest.mark.xfail(strict=True)` decorator from the core plan's `test_diagnose.py`, transitioning Cycle 1 from XFAIL to PASS.

**Tech Stack:** Python 3.12, Pydantic v2, `rule-engine >= 4.5.3, <5`, `pyyaml >=6,<7`. All dependencies introduced by the core plan; no new dependencies in this plan.

**Spec source:** `docs/superpowers/specs/2026-04-23-diagnostics-engine-design.md` (§§3.1-3.2 reference material; §5.3-5.4 rule organization + dedupe; §6.8-6.10 cycles 7-9; §14.1-14.2 plan boundaries + ordering; §14.4 Cycle 1 Red-period option-choice resolution). Sections §§4-5.2, §6.1-6.7, §11, §13 are owned by the core plan or were closed via chores; this plan does not modify them.

**Plan-composition decisions recorded:**

- **Q1 — Cycle 8 scope: §6.9 only.** Cycle 8 implements a single `WARNING`-level `estate.crossed_cliff` rule using `firm.estate_thresholds.single_hard` / `joint_hard` per the spec's §6.9 cycle definition. The §14.1 plan-boundary summary's mention of "WARNING/ERROR with approaching-cliff variant" is a spec inconsistency tracked as chore index 4 in `chores.xml` (`2026-04-24-diagnostics-spec-cycle8-summary-realign`). The chore proposes (a) realigning §14.1's wording to §6.9, or (b) authoring a separate `estate.approaching_cliff` rule in a future plan. This plan implements §6.9 verbatim.

- **Q2 — xfail marker timing: removed atomically with cycle 9 Green, not on first commit.** §14.4 names the rules plan's "first commit" as the marker-removal point, but the core plan's `pytest.mark.xfail(..., strict=True)` decorator combined with three-rule asserts means an early removal would cause a hard FAIL during cycles 7→8 (rules absent → assertion fails for real, not XPASS). The marker is removed in Task 4, after all three Green rules land. The first commit of this plan therefore lands cycle 7's test+rule pair (Task 1), not the marker removal — a deliberate deviation from §14.4's literal wording, justified by `strict=True` semantics.

- **Q3 — Test file structure: single file, three test functions.** Per spec §6.8-6.10, all three starter-rule tests live in `tests/v3/diagnostics/test_starter_rules.py`. The file is created in Task 1 (cycle 7) with one test; Tasks 2 and 3 append one test each.

- **Q4 — TDD commit granularity: 2 commits per cycle for cycles 7 and 8 (Red, Green); 2 commits for cycle 9 (Red, Green); a separate commit for the xfail removal in Task 4; a final plans.xml-close commit in Task 5.** Cycles 7-9 spec refactor notes are documentary (verify rule-engine semantics, re-run cycle 1) rather than substantive code refactor — no Refactor commit per cycle. The cycle-9 spec note "re-run Cycle 1's integration test" becomes Task 4's verification step.

- **Q5 — Cycle 9 deviates from spec literal: `=~` → `=~~`.** Spec §6.10's YAML reads `expression: 'trust.text_blocks.statement_of_intent =~ "\\[OCR_LOW_CONFIDENCE\\]"'`, but the same section's test 4 ("Embedded placeholder. `statement_of_intent = 'preamble [OCR_LOW_CONFIDENCE] tail'` → diagnostic fires (regex matches anywhere in the string)") requires regex-SEARCH semantics. Per the `rule-engine` 4.5.3 source (`lib/rule_engine/ast.py`, `FuzzyComparisonExpression.__op_regex`), `=~` is `re.match` (anchored at position 0) and `=~~` is `re.search` (matches anywhere). The plan emits `=~~` to honor the documented test-4 semantics. Tracked as chore index 5 (`2026-04-24-diagnostics-spec-cycle9-regex-operator-fix`) in `chores.xml` for spec amendment. Task 0 includes an empirical probe that aborts the plan if the operator distinction is not present in the installed rule-engine version.

- **Predecessor: `2026-04-23-diagnostics-engine-core` (plans.xml index 7) MUST be landed before this plan starts.** Task 0 verifies. The diagnostics module, the conftest fixtures (`firm_config_factory`, `trust_data_factory`, `tmp_audit_dir`, `tmp_rules_dir`), and the empty `builtin.yaml` must all exist on the working tree.

---

## File Structure

**Modified (production):**

| Path | Change |
| ---- | ------ |
| `src/trust_generator/v3/diagnostics/rules/builtin.yaml` | Replaces `[]` (post-core empty list) with three rule entries appended one per cycle. |

**Created (tests):**

| Path | Responsibility |
| ---- | -------------- |
| `tests/v3/diagnostics/test_starter_rules.py` | Three parametrized test functions, one per cycle, each driving `diagnose()` end-to-end and asserting on the rule-specific code/level/source. |

**Modified (tests):**

| Path | Change |
| ---- | ------ |
| `tests/v3/diagnostics/test_diagnose.py` | Remove `@pytest.mark.xfail(...)` decorator and `import pytest`; trim docstring's xfail-rationale paragraph. |

**Modified (metadata):**

| Path | Change |
| ---- | ------ |
| `.claude/context/plans.xml` | Set `status="closed"` on plan index 8 entry; set `plan-md` attribute; bump `modified-at`. |

**Total touched files:** 4 (1 modified production, 1 created test, 1 modified test, 1 modified metadata). Well under the 10-file hard threshold.

---

## Task 0: Predecessor verification

**Files:**
- Read-only: `src/trust_generator/v3/diagnostics/rules/builtin.yaml`
- Read-only: `tests/v3/diagnostics/test_diagnose.py`
- Read-only: `tests/v3/diagnostics/conftest.py`

This task is gating, not implementing. Confirm the core plan landed cleanly before any cycle work begins. If any check fails, escalate — the rules plan cannot proceed without the engine.

- [ ] **Step 1: Verify the diagnostics package exists**

Run: `ls src/trust_generator/v3/diagnostics/`
Expected: at minimum `__init__.py`, `engine.py`, `eval_context.py`, `loader.py`, `audit.py`, `errors.py`, `rules/`.
If missing: the core plan has not landed; halt.

- [ ] **Step 2: Verify `builtin.yaml` is the empty-list sentinel**

Run: `cat src/trust_generator/v3/diagnostics/rules/builtin.yaml`
Expected output: `[]` (single line, empty YAML list).
If non-empty: investigate — either the core plan deviated from its scope or another rules-authoring effort is in flight.

- [ ] **Step 3: Verify the conftest defines the four fixtures used in this plan**

Run: `grep -E '^def (firm_config_factory|trust_data_factory|tmp_audit_dir|tmp_rules_dir)\b|^@pytest\.fixture' tests/v3/diagnostics/conftest.py`
Expected: each fixture decorator-and-name pair appears.
If missing: halt and reconcile with the core plan's Task 1.

- [ ] **Step 4: Verify the Cycle 1 integration test is XFAIL'd**

Run: `pixi run test match=test_diagnose_triggers_all_starter_rules`
Expected: pytest reports `1 xfailed` (not `1 failed`, not `1 passed`). The xfail decorator must be live.
If `failed`: collection or runtime error — escalate.
If `xpassed` (with `strict=True`, this surfaces as `failed`): a rule has leaked into `builtin.yaml` ahead of this plan; halt and reconcile.

- [ ] **Step 5: Verify the project gate is green**

Run: `pixi run check`
Expected: lint passes, mypy passes, all non-xfailed tests pass, the cycle-1 test reports XFAIL. Exit code 0.
If non-green: halt and resolve before starting cycle 7.

- [ ] **Step 6: Verify the public engine surface is importable**

Run: `pixi run python -c "from trust_generator.v3.diagnostics import diagnose; from trust_generator.v3.schema import BeneficiaryShare, DiagnosticLevel, DiagnosticSource, TrustType; print('ok')"`
Expected: `ok` (no traceback). This proves both the diagnostics package re-exports and the schema enum imports the rules-plan tests rely on are wired correctly.
If `ImportError`: the core plan's Task 7 (`__init__.py` re-exports) or schema enum names have drifted; halt.

- [ ] **Step 7: Verify the conftest fixture signature matches the kwargs this plan consumes**

Run: `grep -E 'beneficiary_shares|estate_value_approximate|statement_of_intent|file_number|trust_type|execution_date' tests/v3/diagnostics/conftest.py`
Expected: each of the six tokens appears at least once in the `trust_data_factory` definition.
If any token is missing or has been renamed: halt — the plan's Task 1-3 test fixtures will fail with `TypeError: unexpected keyword argument`.

- [ ] **Step 8: Empirically verify rule-engine's regex-operator distinction (defense-in-depth for plan decision Q5)**

Run:

```bash
pixi run python <<'PY'
import rule_engine
m = rule_engine.Rule('text =~ "world"')
s = rule_engine.Rule('text =~~ "world"')
ctx = {'text': 'hello world'}
match_anchored = m.matches(ctx)
search_anywhere = s.matches(ctx)
print(f"=~ ('hello world' vs pattern 'world' at pos 6): {match_anchored}")
print(f"=~~ ('hello world' vs pattern 'world' at pos 6): {search_anywhere}")
assert match_anchored is False, f"=~ unexpectedly matched anywhere; library may be different version"
assert search_anywhere is True, f"=~~ failed to find pattern; library may be different version"
print("OK — operator distinction matches plan decision Q5")
PY
```

Expected output:
```
=~ ('hello world' vs pattern 'world' at pos 6): False
=~~ ('hello world' vs pattern 'world' at pos 6): True
OK — operator distinction matches plan decision Q5
```

If the assertions fail: rule-engine's installed version does not match the operator semantics this plan assumes. Halt and reconcile — possible causes: (a) rule-engine is a different version than `>=4.5.3,<5`, or (b) upstream changed the operator semantics in a patch release. In either case, do not proceed with cycle 9 until the operator distinction is confirmed.

- [ ] **Step 9: Empirically verify rule-engine's `and` short-circuit behavior (defense-in-depth for assumption I1)**

Run:

```bash
pixi run python <<'PY'
import rule_engine
r = rule_engine.Rule('x == null and y > 1.0')
result = r.matches({'x': None, 'y': 0.0})
print(f"and short-circuit ('null and y > 1'): {result}")
PY
```

Expected output:
```
and short-circuit ('null and y > 1'): False
```

If output is `False`: `and` short-circuits on null — the cycle-8 expression `trust.elections.estate_value_approximate != null and (...)` is safe.
If `EvaluationError` raised: `and` is eager; the cycle-8 rule will produce `engine.eval_error` meta-diagnostics for every trust without an estate value (an extremely common state during fill stage). Reconcile by restructuring the cycle-8 expression (e.g., split into two trust-type-guarded rules each starting with the type predicate), or accept the meta-diagnostic noise as a v1 known-issue. Do not start cycle 8 until the path is chosen.

The silent-case assertions in Tasks 1-3 also include an `engine.*` meta-diagnostic check as a backstop, so even if this probe is skipped the plan tests will surface eager-evaluation regressions — but probing here is faster than diagnosing a confused test failure later.

---

## Task 1: Cycle 7 — `shares.sum_not_100` (SCHEMA, ERROR)

**Files:**
- Create: `tests/v3/diagnostics/test_starter_rules.py`
- Modify: `src/trust_generator/v3/diagnostics/rules/builtin.yaml`

The first rule. SCHEMA-source structural invariant: the cross-entry sum of `BeneficiaryShare.share_percent` must be exactly 100, except when the list is empty. The expression's `!= []` left conjunct silences the rule on a fresh trust; the `!= 100` right conjunct catches partial entries, over-allocations, and rounding-induced 99.99 totals.

- [ ] **Step 1: Author the test file (Red)**

Create `tests/v3/diagnostics/test_starter_rules.py`:

```python
"""Cycles 7-9 starter rule tests.

Each test exercises one starter rule end-to-end through ``diagnose()``,
asserting both fires-on-violation and silent-on-clean scenarios. Test bodies
filter the diagnostics list to the rule's code so other rules firing or not
firing in the same scenario do not interfere with the assertion.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from trust_generator.v3.diagnostics import diagnose
from trust_generator.v3.schema import (
    BeneficiaryShare,
    DiagnosticLevel,
    DiagnosticSource,
)


@pytest.mark.parametrize(
    ("shares", "expected_fires"),
    [
        (
            [
                BeneficiaryShare(recipient_ref="A", share_percent=Decimal(33)),
                BeneficiaryShare(recipient_ref="B", share_percent=Decimal(33)),
                BeneficiaryShare(recipient_ref="C", share_percent=Decimal(33)),
            ],
            True,
        ),
        ([], False),
        (
            [
                BeneficiaryShare(recipient_ref="A", share_percent=Decimal(50)),
                BeneficiaryShare(recipient_ref="B", share_percent=Decimal(50)),
            ],
            False,
        ),
        (
            [
                BeneficiaryShare(recipient_ref="A", share_percent=Decimal("33.33")),
                BeneficiaryShare(recipient_ref="B", share_percent=Decimal("33.33")),
                BeneficiaryShare(recipient_ref="C", share_percent=Decimal("33.34")),
            ],
            False,
        ),
        (
            [
                BeneficiaryShare(recipient_ref="A", share_percent=Decimal("33.33")),
                BeneficiaryShare(recipient_ref="B", share_percent=Decimal("33.33")),
                BeneficiaryShare(recipient_ref="C", share_percent=Decimal("33.33")),
            ],
            True,
        ),
    ],
    ids=[
        "sum_99_fires",
        "empty_silent",
        "sum_100_silent",
        "precision_100_silent",
        "precision_99_99_fires",
    ],
)
def test_shares_sum_not_100(
    firm_config_factory, trust_data_factory, shares, expected_fires
):
    """``shares.sum_not_100`` fires iff shares is non-empty AND sum != 100."""
    config = firm_config_factory()
    trust = trust_data_factory(beneficiary_shares=shares)

    diagnostics = diagnose(trust, config, ref_date=date(2026, 4, 23))

    meta = [d for d in diagnostics if d.code.startswith("engine.")]
    assert meta == [], f"unexpected meta-diagnostics: {[d.code for d in meta]}"

    matching = [d for d in diagnostics if d.code == "shares.sum_not_100"]
    if expected_fires:
        assert len(matching) == 1
        assert matching[0].level == DiagnosticLevel.ERROR
        assert matching[0].source == DiagnosticSource.SCHEMA
    else:
        assert matching == []
```

The `meta == []` assertion is a backstop for I1 (the eager-evaluation concern Task 0 Step 9 probes empirically). It catches any rule expression that produces an `engine.eval_error` / `engine.symbol_unknown` meta-diagnostic during evaluation — a category of failure that would otherwise be silently filtered by the rule-code filter below.

- [ ] **Step 2: Run the test to confirm Red**

Run: `pixi run test match=test_shares_sum_not_100`
Expected: 5 parametrized cases all FAIL — the rule does not yet exist in `builtin.yaml`, so `diagnose()` returns `[]` for every case. The two fires-expecting cases (`sum_99_fires`, `precision_99_99_fires`) fail with `assert len(matching) == 1` (actual: 0). The three silent-expecting cases pass trivially because `[] == []`. Net: 2 failed, 3 passed.

If all 5 pass: investigate — the rule may have been authored ahead of this plan; reconcile.

- [ ] **Step 3: Author the rule in `builtin.yaml` (Green)**

Replace the entire content of `src/trust_generator/v3/diagnostics/rules/builtin.yaml` with:

```yaml
- code: shares.sum_not_100
  level: error
  source: schema
  context: both
  message: "Beneficiary shares must sum to exactly 100%."
  field_path: beneficiary_shares
  expression: "trust.beneficiary_shares != [] and trust.beneficiary_shares_total != 100"
  enabled: true
```

- [ ] **Step 4: Run the test to confirm Green**

Run: `pixi run test match=test_shares_sum_not_100`
Expected: 5 parametrized cases all pass.

If a fires-expecting case fails: check `trust.beneficiary_shares_total` returns `Decimal` and `rule-engine` is coercing both sides of `!= 100` to FLOAT (per spec §6.8 refactor note). If a silent-expecting case fails (e.g., `precision_100_silent` fires): the Decimal-to-float coercion may be carrying drift — escalate.

- [ ] **Step 5: Run the project gate**

Run: `pixi run check`
Expected: green, with one known deviation — adding a rule to `builtin.yaml` collides with three loader tests (`test_builtin_loads_empty`, `test_empty_rules_dir`, `test_missing_rules_dir`) that assume `builtin.yaml == []`. Apply `monkeypatch.setattr(loader, "_load_builtin_rules", list)` to each, mirroring the in-file `test_builtin_namespace_enforcement` precedent; this decoupling deviation is expected and must land in the cycle-7 commit alongside the rule itself. The cycle-1 integration test still reports XFAIL.

- [ ] **Step 6: Commit cycle 7**

```bash
git add tests/v3/diagnostics/test_starter_rules.py src/trust_generator/v3/diagnostics/rules/builtin.yaml
git commit -m "feat(diagnostics): cycle 7 — shares.sum_not_100 starter rule (SCHEMA, ERROR)"
```

---

## Task 2: Cycle 8 — `estate.crossed_cliff` (BUSINESS_RULE, WARNING)

**Files:**
- Modify: `tests/v3/diagnostics/test_starter_rules.py` (append test function)
- Modify: `src/trust_generator/v3/diagnostics/rules/builtin.yaml` (append rule)

The second rule. BUSINESS_RULE-source policy threshold: when `estate_value_approximate` crosses the trust-type-specific hard cliff (`single_hard` for INDIVIDUAL, `joint_hard` for JOINT), surface a WARNING. The rule depends on the firm-config defaults (`single_hard=4_000_000`, `joint_hard=8_000_000`) being live in the test fixtures — `firm_config_factory()` returns those defaults.

The rule's WARNING level (not ERROR) is deliberate: a high-estate trust is not a defective document, only a tax-planning concern. Hard-block ERRORs are reserved for invalidating conditions.

- [ ] **Step 1: Append the test function (Red)**

Append to `tests/v3/diagnostics/test_starter_rules.py` (after the `test_shares_sum_not_100` function), and add `TrustType` to the existing schema import block:

```python
from trust_generator.v3.schema import (
    BeneficiaryShare,
    DiagnosticLevel,
    DiagnosticSource,
    TrustType,
)
```

Then append:

```python
@pytest.mark.parametrize(
    ("trust_type", "estate_value", "expected_fires"),
    [
        (TrustType.INDIVIDUAL, Decimal(4_500_000), True),
        (TrustType.INDIVIDUAL, Decimal(3_500_000), False),
        (TrustType.JOINT, Decimal(9_000_000), True),
        (TrustType.JOINT, Decimal(5_000_000), False),
        (TrustType.JOINT, None, False),
    ],
    ids=[
        "individual_above_hard",
        "individual_below_hard",
        "joint_above_hard",
        "joint_between_thresholds",
        "null_estimate",
    ],
)
def test_estate_crossed_cliff(
    firm_config_factory,
    trust_data_factory,
    trust_type,
    estate_value,
    expected_fires,
):
    """``estate.crossed_cliff`` fires when estate >= the trust-type-specific hard threshold."""
    config = firm_config_factory()
    trust = trust_data_factory(
        trust_type=trust_type, estate_value_approximate=estate_value
    )

    diagnostics = diagnose(trust, config, ref_date=date(2026, 4, 23))

    meta = [d for d in diagnostics if d.code.startswith("engine.")]
    assert meta == [], f"unexpected meta-diagnostics: {[d.code for d in meta]}"

    matching = [d for d in diagnostics if d.code == "estate.crossed_cliff"]
    if expected_fires:
        assert len(matching) == 1
        assert matching[0].level == DiagnosticLevel.WARNING
        assert matching[0].source == DiagnosticSource.BUSINESS_RULE
    else:
        assert matching == []
```

The `meta == []` assertion is the I1 backstop. It is most acute on the `null_estimate` parametrize case: if `rule-engine`'s `and` is eager (Task 0 Step 9 probes this), the cycle-8 expression's right-side `null >= firm.estate_thresholds.single_hard` raises `EvaluationError` → `engine.eval_error` meta-diagnostic → this assertion fails, surfacing the regression at test time rather than letting it slip into production where it would fire on every fill-stage trust without an estate estimate.

- [ ] **Step 2: Run the test to confirm Red**

Run: `pixi run test match=test_estate_crossed_cliff`
Expected: 5 parametrized cases. The two fires-expecting cases fail (rule absent → diagnostic list empty). The three silent-expecting cases pass trivially.

- [ ] **Step 3: Append the rule to `builtin.yaml` (Green)**

Append to `src/trust_generator/v3/diagnostics/rules/builtin.yaml` (the file should now have two rule entries):

```yaml
- code: estate.crossed_cliff
  level: warning
  source: business_rule
  context: both
  message: "Estimated estate value crosses the Illinois cliff threshold; tax-planning attention required."
  field_path: elections.estate_value_approximate
  expression: |
    trust.elections.estate_value_approximate != null
    and (
      (trust.trust_id.trust_type == "individual" and trust.elections.estate_value_approximate >= firm.estate_thresholds.single_hard)
      or (trust.trust_id.trust_type == "joint" and trust.elections.estate_value_approximate >= firm.estate_thresholds.joint_hard)
    )
  enabled: true
```

The full file should now read:

```yaml
- code: shares.sum_not_100
  level: error
  source: schema
  context: both
  message: "Beneficiary shares must sum to exactly 100%."
  field_path: beneficiary_shares
  expression: "trust.beneficiary_shares != [] and trust.beneficiary_shares_total != 100"
  enabled: true

- code: estate.crossed_cliff
  level: warning
  source: business_rule
  context: both
  message: "Estimated estate value crosses the Illinois cliff threshold; tax-planning attention required."
  field_path: elections.estate_value_approximate
  expression: |
    trust.elections.estate_value_approximate != null
    and (
      (trust.trust_id.trust_type == "individual" and trust.elections.estate_value_approximate >= firm.estate_thresholds.single_hard)
      or (trust.trust_id.trust_type == "joint" and trust.elections.estate_value_approximate >= firm.estate_thresholds.joint_hard)
    )
  enabled: true
```

- [ ] **Step 4: Run the test to confirm Green**

Run: `pixi run test match=test_estate_crossed_cliff`
Expected: 5 cases pass.

If `individual_above_hard` or `joint_above_hard` fails: check that the eval-context exposes `firm.estate_thresholds.single_hard` / `joint_hard` as plain ints (the `model_dump(mode='python')` baseline emits ints for nested int fields, and `build_eval_context`'s `_unwrap_enums()` helper normalizes the `trust.trust_id.trust_type` enum to its string value so the `== "individual"` / `== "joint"` comparison fires under rule-engine — verified by Cycle 2 test 8's rule-engine roundtrip).

If `null_estimate` fires unexpectedly: the rule's `!= null` left conjunct may not be short-circuiting — verify rule-engine's null semantics against `model_dump`'s `None` representation.

- [ ] **Step 5: Run the broader test suite**

Run: `pixi run test match=test_starter_rules`
Expected: both `test_shares_sum_not_100` (5 cases) and `test_estate_crossed_cliff` (5 cases) pass. 10 cases total.

- [ ] **Step 6: Run the project gate**

Run: `pixi run check`
Expected: green. Cycle-1 integration test still XFAIL (now 2 of 3 expected codes present).

- [ ] **Step 7: Commit cycle 8**

```bash
git add tests/v3/diagnostics/test_starter_rules.py src/trust_generator/v3/diagnostics/rules/builtin.yaml
git commit -m "feat(diagnostics): cycle 8 — estate.crossed_cliff starter rule (BUSINESS_RULE, WARNING)"
```

---

## Task 3: Cycle 9 — `extraction.placeholder_unfilled` (EXTRACTION, WARNING)

**Files:**
- Modify: `tests/v3/diagnostics/test_starter_rules.py` (append test function)
- Modify: `src/trust_generator/v3/diagnostics/rules/builtin.yaml` (append rule)

The third rule. EXTRACTION-source artifact: when `text_blocks.statement_of_intent` contains the OCR low-confidence marker `[OCR_LOW_CONFIDENCE]` (anywhere in the string, not just full-string match), surface a WARNING. The marker convention `[OCR_LOW_CONFIDENCE]` is established by this rule for the future OCR pipeline to adopt (Sessions 4.3a-4.3c).

The rule's `context: fill` (not `both`) is deliberate: an OCR placeholder is a fill-time concern; by generation time, the placeholder either has been resolved (no diagnostic) or has slipped through to the document (still relevant, but the EXTRACTION classification routes it to the fill-stage review pane regardless). Future evolution may broaden this.

- [ ] **Step 1: Append the test function (Red)**

Append to `tests/v3/diagnostics/test_starter_rules.py`:

```python
@pytest.mark.parametrize(
    ("text", "expected_fires"),
    [
        ("[OCR_LOW_CONFIDENCE]", True),
        ("", False),
        ("I, John Doe, declare...", False),
        ("preamble [OCR_LOW_CONFIDENCE] tail", True),
    ],
    ids=[
        "exact_marker_fires",
        "empty_silent",
        "real_text_silent",
        "embedded_marker_fires",
    ],
)
def test_extraction_placeholder_unfilled(
    firm_config_factory, trust_data_factory, text, expected_fires
):
    """``extraction.placeholder_unfilled`` fires when statement_of_intent contains the OCR marker."""
    config = firm_config_factory()
    trust = trust_data_factory(statement_of_intent=text)

    diagnostics = diagnose(trust, config, ref_date=date(2026, 4, 23))

    meta = [d for d in diagnostics if d.code.startswith("engine.")]
    assert meta == [], f"unexpected meta-diagnostics: {[d.code for d in meta]}"

    matching = [
        d for d in diagnostics if d.code == "extraction.placeholder_unfilled"
    ]
    if expected_fires:
        assert len(matching) == 1
        assert matching[0].level == DiagnosticLevel.WARNING
        assert matching[0].source == DiagnosticSource.EXTRACTION
    else:
        assert matching == []
```

The `embedded_marker_fires` parametrize case (`"preamble [OCR_LOW_CONFIDENCE] tail"`) is the canary case for plan decision Q5's operator choice. With `=~~` (regex-search) it fires; with `=~` (regex-match, anchored at position 0) it would not fire because the pattern starts after `"preamble "`. Task 0 Step 8 already verified the operator distinction at the library level; this test validates the plan's chosen operator threads through correctly into a real diagnose() call.

- [ ] **Step 2: Run the test to confirm Red**

Run: `pixi run test match=test_extraction_placeholder_unfilled`
Expected: 4 parametrized cases. The two fires-expecting cases (`exact_marker_fires`, `embedded_marker_fires`) fail; the two silent-expecting cases (`empty_silent`, `real_text_silent`) pass.

- [ ] **Step 3: Append the rule to `builtin.yaml` (Green)**

Append to `src/trust_generator/v3/diagnostics/rules/builtin.yaml`:

```yaml
- code: extraction.placeholder_unfilled
  level: warning
  source: extraction
  context: fill
  message: "OCR low-confidence placeholder detected in statement of intent; verify and replace before generation."
  field_path: text_blocks.statement_of_intent
  expression: 'trust.text_blocks.statement_of_intent =~~ "\\[OCR_LOW_CONFIDENCE\\]"'
  enabled: true
```

The full file should now read:

```yaml
- code: shares.sum_not_100
  level: error
  source: schema
  context: both
  message: "Beneficiary shares must sum to exactly 100%."
  field_path: beneficiary_shares
  expression: "trust.beneficiary_shares != [] and trust.beneficiary_shares_total != 100"
  enabled: true

- code: estate.crossed_cliff
  level: warning
  source: business_rule
  context: both
  message: "Estimated estate value crosses the Illinois cliff threshold; tax-planning attention required."
  field_path: elections.estate_value_approximate
  expression: |
    trust.elections.estate_value_approximate != null
    and (
      (trust.trust_id.trust_type == "individual" and trust.elections.estate_value_approximate >= firm.estate_thresholds.single_hard)
      or (trust.trust_id.trust_type == "joint" and trust.elections.estate_value_approximate >= firm.estate_thresholds.joint_hard)
    )
  enabled: true

- code: extraction.placeholder_unfilled
  level: warning
  source: extraction
  context: fill
  message: "OCR low-confidence placeholder detected in statement of intent; verify and replace before generation."
  field_path: text_blocks.statement_of_intent
  expression: 'trust.text_blocks.statement_of_intent =~~ "\\[OCR_LOW_CONFIDENCE\\]"'
  enabled: true
```

Operator note (plan decision Q5): the expression uses `=~~` (regex-search), NOT `=~` (regex-match) as the spec literal in §6.10 reads. Rationale and chore-tracking are recorded in the plan-md header (Q5) and `chores.xml` index 5. The deviation is required to honor §6.10 test 4's documented "matches anywhere in the string" semantics.

YAML escaping note: the outer single quotes preserve the inner `\\[` / `\\]` literally; rule-engine's string-literal parser interprets `\\` as one backslash, producing the regex pattern `\[OCR_LOW_CONFIDENCE\]` which matches the literal bracketed marker anywhere in the input string.

- [ ] **Step 4: Run the test to confirm Green**

Run: `pixi run test match=test_extraction_placeholder_unfilled`
Expected: 4 cases pass.

If `embedded_marker_fires` fails (input `"preamble [OCR_LOW_CONFIDENCE] tail"`, expected fires): the operator may be wrong. Per the rule-engine 4.5.3 source (`lib/rule_engine/ast.py`, `FuzzyComparisonExpression.__op_regex`), `=~` is `re.match` (anchored at position 0) and `=~~` is `re.search` (matches anywhere). The plan emits `=~~`; if the YAML accidentally reverted to `=~`, the embedded-marker case fails because the pattern does not match at position 0 of `"preamble [OCR_..."`. Re-check the YAML against Step 3's expected file content, and re-run Task 0 Step 8 to confirm the operator distinction holds in the installed library version.

If `exact_marker_fires` (input `"[OCR_LOW_CONFIDENCE]"`) passes but `embedded_marker_fires` fails: the operator is definitely `=~` (match) when it should be `=~~` (search) — `re.match` matches at position 0 in the exact case but not in the embedded case. That asymmetric pass/fail is the diagnostic signature.

- [ ] **Step 5: Run the full diagnostics test suite**

Run: `pixi run test match=test_starter_rules`
Expected: all three test functions pass — 14 parametrized cases total (5 + 5 + 4).

- [ ] **Step 6: Manually verify cycle 1 would now pass (without removing xfail)**

Run: `pixi run test match=test_diagnose_triggers_all_starter_rules`
Expected: pytest reports `1 failed` — but check the output: the assertion `codes == {three expected}` should now succeed in the test body, which with `strict=True` xfail manifests as `XPASS (strict)` → counted as `failed`. This is the canary signal that the test is ready to lose its marker.

If `xfailed` instead of `failed`: one of the three rules is not firing on the cycle-1 fixture; investigate before proceeding to Task 4. The cycle-1 fixture uses `INDIVIDUAL` trust_type with `estate_value_approximate=Decimal(5000000)` (above `single_hard=4_000_000`), three shares totaling 99, and `statement_of_intent="[OCR_LOW_CONFIDENCE]"` — all three rules should fire.

- [ ] **Step 7: Commit cycle 9**

```bash
git add tests/v3/diagnostics/test_starter_rules.py src/trust_generator/v3/diagnostics/rules/builtin.yaml
git commit -m "feat(diagnostics): cycle 9 — extraction.placeholder_unfilled starter rule (EXTRACTION, WARNING)"
```

Note: the project gate (`pixi run check`) is intentionally **not** run between Steps 6 and 7. Cycle 1 is now XPASS-strict-failing; that is expected and is the entry condition for Task 4. Running `pixi run check` here would report a red gate that Task 4 immediately resolves.

**Do not push to remote between Task 3 and Task 4.** The XPASS-strict failure window is deliberately a local-only state. Task 3's commit and Task 4's commit must land together as one push (or in the same PR if branch-protected). A literal-interpreting executor who pushes after Task 3 alone would expose the v3 branch's CI to a red gate that this plan has already arranged the immediate fix for.

---

## Task 4: Close Cycle 1 — remove xfail marker

**Files:**
- Modify: `tests/v3/diagnostics/test_diagnose.py`

The Cycle 1 integration test now passes. Remove the `pytest.mark.xfail(strict=True)` decorator and the now-unused `import pytest`. Trim the module docstring's xfail-rationale paragraph (the deferred-import idiom is kept — harmless, costs nothing, removing it is unnecessary churn).

This task is the spec's §6.10 Refactor work ("Cycle close-out: re-run Cycle 1's integration test. It should now be green") packaged as a discrete commit so the engine's contract-anchor transition (XFAIL → PASS) is auditable in `git log` as a single atomic change.

- [ ] **Step 1: Read the current test file to confirm shape**

Run: `cat tests/v3/diagnostics/test_diagnose.py`
Expected: the file matches the structure committed by core plan Task 1, Step 3 — module docstring, `from __future__ import annotations`, three import lines (`from datetime import date`, `from decimal import Decimal`, `import pytest`), `from trust_generator.v3.schema import BeneficiaryShare, TrustType`, the `@pytest.mark.xfail(...)` decorator, and the `def test_diagnose_triggers_all_starter_rules(...)` function.

If the file has drifted: reconcile against the core plan's content before proceeding.

- [ ] **Step 2: Replace the file content**

Replace the entire content of `tests/v3/diagnostics/test_diagnose.py` with:

```python
"""Cycle 1 — outer integration test for diagnose().

Asserts that a TrustData crafted to trigger all three starter rules
(shares.sum_not_100, estate.crossed_cliff, extraction.placeholder_unfilled)
yields exactly those three diagnostic codes through the diagnose() coordinator.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from trust_generator.v3.schema import BeneficiaryShare, TrustType


def test_diagnose_triggers_all_starter_rules(
    firm_config_factory, trust_data_factory
):
    """A TrustData crafted to trigger all three starter rules yields three diagnostics."""
    from trust_generator.v3.diagnostics import diagnose

    config = firm_config_factory()
    trust = trust_data_factory(
        beneficiary_shares=[
            BeneficiaryShare(recipient_ref="A", share_percent=Decimal(33)),
            BeneficiaryShare(recipient_ref="B", share_percent=Decimal(33)),
            BeneficiaryShare(recipient_ref="C", share_percent=Decimal(33)),
        ],
        estate_value_approximate=Decimal(5000000),
        trust_type=TrustType.INDIVIDUAL,
        statement_of_intent="[OCR_LOW_CONFIDENCE]",
    )

    result = diagnose(trust, config, ref_date=date(2026, 4, 23))

    codes = {d.code for d in result}
    assert codes == {
        "shares.sum_not_100",
        "estate.crossed_cliff",
        "extraction.placeholder_unfilled",
    }
```

Diff-level summary of the change (described by content rather than line numbers, since the predecessor's exact line layout depends on its own formatting decisions):
- Replaced the multi-paragraph module docstring (which explained the xfail rationale and the deferred-import discipline) with a single-paragraph summary describing what the test asserts.
- Removed the `import pytest` line — no longer used after the decorator removal; ruff would flag it as F401.
- Removed the `@pytest.mark.xfail(reason=..., strict=True)` decorator block immediately preceding `def test_diagnose_triggers_all_starter_rules`.
- Removed the trailing `# deferred per module docstring` inline comment on the `from trust_generator.v3.diagnostics import diagnose` line inside the function body (the comment referenced the now-removed docstring paragraph).
- The deferred import inside the function body is preserved — it works regardless and removing it is unrelated churn that would expand the diff without semantic value.

- [ ] **Step 3: Run cycle 1 directly to confirm PASS**

Run: `pixi run test match=test_diagnose_triggers_all_starter_rules`
Expected: `1 passed`. Not XPASS, not XFAIL — a real pass.

If `failed`: re-check the rule list in `builtin.yaml` against Tasks 1-3 Step 3 outputs. If `xfailed`: the marker removal did not stick — re-edit.

- [ ] **Step 4: Run the project gate**

Run: `pixi run check`
Expected: lint passes (no unused-import warning on the now-removed `import pytest`), mypy passes, all tests pass — including the now-unmasked cycle 1 integration test. **Exit code 0.**

This is the gate-green moment for the entire diagnostics engine. The engine's outer contract is now actively asserted on every CI run.

- [ ] **Step 5: Commit the marker removal**

```bash
git add tests/v3/diagnostics/test_diagnose.py
git commit -m "test(diagnostics): cycle 1 — remove xfail marker; integration test now green"
```

---

## Task 5: Close `plans.xml` index 8 entry

**Files:**
- Modify: `.claude/context/plans.xml`

Mark this plan closed in the canonical plan reference. Mirrors the precedent from the firm-config and promote-seed plans.

- [ ] **Step 1: Edit `.claude/context/plans.xml`**

On the index 8 entry:
1. Set `status="closed"` (was `"open"`).
2. Set `plan-md="docs/superpowers/plans/2026-04-23-diagnostics-engine-rules.md"` (was empty string).

On the `<reference>` element:
3. Update `modified-at` to the current ISO 8601 timestamp with timezone offset (use `date '+%Y-%m-%dT%H:%M:%S%:z'` to generate).

The post-edit entry should read:

```xml
    <plan index="8"
          id="2026-04-23-diagnostics-engine-rules"
          status="closed"
          expendable="false"
          plan-md="docs/superpowers/plans/2026-04-23-diagnostics-engine-rules.md"
          spec-md="docs/superpowers/specs/2026-04-23-diagnostics-engine-design.md"
          synopsis="Diagnostics engine starter rules (cycles 7-9): shares.sum_not_100 (SCHEMA), estate.crossed_cliff (BUSINESS_RULE), extraction.placeholder_unfilled (EXTRACTION). Closes Cycle 1 integration test." />
```

- [ ] **Step 2: Validate against the schema**

Run: `pixi run python -c "import xml.etree.ElementTree as ET; ET.parse('.claude/context/plans.xml')"`
Expected: no output (XML parses cleanly). The XSD validation is not run inline — that is enforced separately by the project's editor/IDE schema-mode tooling.

- [ ] **Step 3: Commit the close**

```bash
git add .claude/context/plans.xml
git commit -m "$(cat <<'EOF'
chore(context/plans): close diagnostics-engine-rules plan

Spec inconsistencies surfaced during plan composition remain open in chores.xml
and require separate closing commits:
  - chore index 4 (2026-04-24-diagnostics-spec-cycle8-summary-realign): §14.1 cycle-8 summary drift
  - chore index 5 (2026-04-24-diagnostics-spec-cycle9-regex-operator-fix): §6.10 =~ → =~~ amendment

Both are docs-only and do not block any other plan.
EOF
)"
```

- [ ] **Step 4: Final sanity check**

Run: `pixi run check`
Expected: green.

Run: `git log --oneline -10`
Expected: the most recent commits trace cycles 7 → 8 → 9 → cycle-1-close → plans-close. Five commits total from this plan.

---

## Self-Review Checklist (run before handoff)

**Spec coverage:** §3.1 + §3.2 → Task 0 verifies the predecessor surfaces. §5.3 (rule organization) → Tasks 1, 2, 3 each author one builtin entry under the `<domain>.<n>` namespace. §5.4 (dedupe + collision) → not exercised by this plan; the loader's collision/dedupe logic is owned by core Task 3. §6.8 (cycle 7) → Task 1. §6.9 (cycle 8) → Task 2 (single WARNING rule per Q1; §14.1 inconsistency tracked as chore index 4). §6.10 (cycle 9) → Task 3, with the cycle's "re-run cycle 1" Refactor split into Task 3 Step 6 (verify) + Task 4 (close). §14.1 (plan boundaries) → enforced (cycles 1-6 untouched). §14.2 (dependency and ordering) → Task 0 gates on core's completion. §14.4 (Cycle 1 Red period) → resolved per Q2; xfail closes in Task 4. **No gaps.**

**Placeholder scan:** No "TBD", "implement later", "similar to Task N", or unspecified error handling. Every code block, command, and YAML entry is complete and self-contained.

**Type consistency:** `BeneficiaryShare`, `DiagnosticLevel`, `DiagnosticSource`, `TrustType` imported once in Task 1 / extended in Task 2; same enum members used in Tasks 1-3 and Task 4. Rule expression attribute paths (`trust.beneficiary_shares`, `trust.beneficiary_shares_total`, `trust.elections.estate_value_approximate`, `trust.trust_id.trust_type`, `trust.text_blocks.statement_of_intent`, `firm.estate_thresholds.single_hard`, `firm.estate_thresholds.joint_hard`) verified against `src/trust_generator/v3/schema.py` and `src/trust_generator/v3/config/firm.py` during plan composition.

**Cross-plan handoff:** Predecessor (plans index 7, `2026-04-23-diagnostics-engine-core`) produces all consumed surfaces — `diagnose()`, `DiagnosticRule`, `load_rules()`, conftest fixtures, empty `builtin.yaml`, xfailed `test_diagnose.py`. Task 0 verifies each.

**Out-of-scope chores opened:** Two spec-amendment chores are tracked independently of this plan's closure:
- Chore index 4 (`2026-04-24-diagnostics-spec-cycle8-summary-realign`) for the §14.1 vs §6.9 spec inconsistency (Q1).
- Chore index 5 (`2026-04-24-diagnostics-spec-cycle9-regex-operator-fix`) for the §6.10 `=~` → `=~~` operator drift (Q5, surfaced by plan-review).

Both are docs-only; both can land before, during, or after this plan. Closing this plan does NOT close either spec inconsistency — they require separate amendment commits to the spec itself.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-04-23-diagnostics-engine-rules.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — A fresh subagent per task, two-stage review between tasks, fast iteration. Good fit because each cycle's Red+Green+Commit triple is small (one test, one YAML rule) and reviewable in isolation.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints. Good fit if the executor wants to walk through the cycles interactively, especially Task 4's marker-removal (the most semantically loaded change).

**Which approach?**
