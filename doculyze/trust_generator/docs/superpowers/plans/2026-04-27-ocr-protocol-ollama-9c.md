# OCR Diagnostics Integration (9c) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Cycle blocks are XML-tagged for dispatcher-side cycle-scope addressing — see "Dispatch Protocol" below.

**Goal:** Land §5.8 (`synthesize_extraction_diagnostics`), §5.9 (`extraction` eval-context namespace), §5.10 (verify lifecycle), §6.7-§6.9 (cycles 7-9), §7.7 (new `extraction.*` codes), and §12 (atomic diagnostics-engine spec amendment) from the OCR spec — the integration leg that wires `ExtractionTrace` into `diagnose()` as a second emission source alongside YAML-driven rules.

**Architecture:** One new module under `src/trust_generator/v3/extraction/` (synthesis), three modified modules under `src/trust_generator/v3/diagnostics/` (engine, eval_context, loader), one modified `__init__` (extraction surface), three augmented test modules (existing diagnostics tests gain extraction-aware cases), one new test module (synthesis-only tests). Two Red→Green TDD cycles (no refactor stages — green outputs are minimal plumbing additions per `.claude/rules/development-strategy.md` `refactor_threshold` rule), one mechanical test-pin task, one docs-amendment task, one plans-close task. The synthesis function consumes 9a's surface (`ExtractionTrace`, `FieldExtraction`, `paths.resolve`, `INCOMPLETE`) and produces `Diagnostic` instances that the existing override flow (`force_generation`) accepts unchanged.

**Tech Stack:** Python 3.12; Pydantic v2; `rule-engine` (existing diagnostics dep, type-resolver expansion in cycle 9c-2); `pytest` with the existing `firm_config_factory` / `trust_data_factory` / `tmp_audit_dir` fixtures from `tests/v3/diagnostics/conftest.py` and `tests/conftest.py`.

**Spec source:** `docs/superpowers/specs/2026-04-27-ocr-protocol-ollama-design.md` (§3.1-3.2 reference material; §5.8 synthesis sketch; §5.9 namespace contract; §5.10 verify lifecycle; §6.7-6.9 cycles 7-9; §7.7 new diagnostic codes; §10 public API surface — `diagnose()` signature update; §11 constraint compliance; §12 atomic spec amendment to `2026-04-23-diagnostics-engine-design.md`; §13 known unknowns; §14 plan-review record). Sections §5.2-5.7 (markers, trace, Protocol, OllamaBackend, paths) are landed by 9a/9b; sections §5.6, §6.4-§6.6, §6.10, §7.1-§7.6, §8 are landed by 9b — NOT modified by this plan. The `extraction.placeholder_unfilled` rule (existing builtin from `2026-04-23-diagnostics-engine-rules`) is unchanged; the new `extraction.*` codes coexist with it (spec §7.7 paragraph 3).

**Plan-composition decisions recorded:**

- **Q1 — Cycle decomposition: 2 cycles + 3 tasks.** Per spec, §6.7 (synthesis), §6.8 (diagnose integration), §6.9 (override interaction). The end-to-end lifecycle test from §6.7 ("emit → verify → no re-emit") relocates into cycle 9c-2's Red because it calls `diagnose(trust, config, extraction=trace)` — which only exists once 9c-2's Green lands the new kwarg. Splitting it across cycles would force an out-of-order test (Red in 9c-1 with no Green path until 9c-2). Cycle 9c-1 retains the seven function-level synthesis tests (empty, verified-suppression, unverified-emit, stale-path filter, low-confidence branch, multi-field order, FieldExtraction.field_path match); cycle 9c-2 owns the lifecycle test plus all four §6.8 plumbing tests. Cycle 9c-3 is verification-only (spec §6.9 Green: "No new code; the test pins the integration") and lands as a `<task>` rather than a `<cycle>` — same Q3 reasoning as 9b's task 9b-5 (verification deliverable, single honest commit). Tasks 9c-4 (spec amendment) and 9c-5 (plans.xml close) follow the precedent of 9b-6 and the spec §12 atomicity requirement.

- **Q2 — Spec amendment (§12) lands as task 9c-4 *after* code/test work.** §12 mandates same-PR atomicity but does not mandate ordering. Landing the docs amendment after cycles 9c-1+9c-2 and task 9c-3 lets the amendment text be informed by what actually shipped (parameter spelling, signature shape, eval_context layout, type-resolver entry name). The PR remains atomic; any reader scanning the PR sees code + tests + spec moved together. Same precedent as chore #2 (firm-config A-4/A-5/A-6 amendments) per spec §12 paragraph 3.

- **Q3 — `extraction.*` codes emit directly from `synthesis.py`, not via YAML registration.** The three new codes (`extraction.illegible_field`, `extraction.low_confidence_field`, `extraction.no_normalized_value`) are constructed by Python with hard-coded `code=` strings. They bypass the YAML loader's namespace enforcement (`_enforce_namespace`) because that gate guards rule-engine-evaluated rules, not direct `Diagnostic` instances. The DiagnosticLevel for each code is fixed at the call site per spec §7.7 (warning / info / warning); `context=DiagnosticContext.BOTH` for all three per spec §7.7 last paragraph; `source=DiagnosticSource.EXTRACTION` (already enum-defined in `schema.py`).

- **Q4 — `LOW_CONFIDENCE_THRESHOLD` is a module-level `Final` constant in `synthesis.py`, not config-driven at v3.0.** Spec §7.7 leaves the threshold unspecified ("below threshold" without a number) because all v3.0 `FieldExtraction` instances have `confidence_self_report=None` (parsers don't populate it; chore 4.3c is the gate for ConfidenceProtocol). The branch is structurally live so a future backend wiring confidence reports gets warnings without a follow-up code change. v3.0 pins the threshold at `0.5` as a placeholder; the test suite exercises the branch by constructing a hand-crafted `FieldExtraction(confidence_self_report=0.3)`. Promotion to firm-config is a non-breaking change at the point a real backend populates the field.

- **Q5 — `eval_context` extraction namespace uses `model_dump(mode='python')` + `_unwrap_enums`, mirroring `trust` and `firm`.** The trace contains `datetime` (`extracted_at`, `verified_at`) and a list of `FieldExtraction` records. Pydantic's `model_dump(mode='python')` preserves these as native types; `_unwrap_enums` is a no-op on the trace (no Enum fields) but kept for shape consistency with the other two namespaces. Rule expressions thus read `extraction.fields[0].field_path` and `extraction.backend_id` naturally. The conditional inclusion (`if extraction is not None`) keeps the YAML guard pattern (`extraction != null and ...`) honest: rules that omit the guard correctly emit `engine.symbol_unknown` for non-OCR'd trusts, mirroring the documented `estate.crossed_cliff` guard pattern.

- **Q6 — Cycle commits attribute and refactor-stage reasoning.** Per `.claude/rules/development-strategy.md`, refactor stages are conditional on `refactor_threshold` (structural duplication / nested conditionals / mixed orthogonal concerns); when none apply, the cycle records "no refactor stage — green output is already minimal" with reasoning. Cycle 9c-1 commits `red,green` because `synthesize_extraction_diagnostics` is a single linear loop with three guarded predicates (illegible / low-confidence / no-normalized-value) each emitting a structurally identical `Diagnostic` — the only refactor candidate would be `_make_diag` extraction, which is included inline in the Green draft and explicitly NOT promoted to a separate refactor commit because the green-phase output is already at minimum surface (a small private helper used three times within the same function). Cycle 9c-2 commits `red,green` because the changes are pure plumbing additions to existing functions: a new kwarg, a conditional dict entry, a new type-resolver line, a new prepend call. No structural duplication, no nested conditionals, no orthogonal concerns to extract. Both cycles' Refactor decisions are recorded explicitly per the rule's `if-none-met` clause.

- **Q7 — Inside-out (Detroit/classicist) TDD with minimal mocks.** Per `.claude/rules/development-strategy.md` `methodology="test-driven-development" approach="inside-out"`. Cycle 9c-1 uses no mocks: real `TrustData` instances (via `trust_data_factory`), real `ExtractionTrace` instances constructed inline, real `paths.resolve` invocations. Cycle 9c-2 uses no mocks for the synthesis path; the rule-engine YAML rule tests construct a temporary custom-rules directory (mirroring `tests/v3/diagnostics/test_rule_loader.py` precedent) with a one-rule YAML file referencing `extraction.fields` — no mocking of `rule_engine.Rule` itself. Task 9c-3 reuses `force_generation` against a real `tmp_audit_dir`, mirroring `test_override.py::test_happy_path_writes_record`.

- **Q8 — Scope size acceptance.** 9c touches 11 file paths total: 1 new src + 1 new test + 4 modified src + 3 modified tests + 1 modified spec docs + 1 modified plans.xml metadata. Logical complexity: 2 complex cycles + 3 mechanical tasks. CLAUDE.md soft-warn at >5 files / >2 complex tasks; hard-deny at >10 / >5. 9c sits at the **letter-of-the-rule edge for file count (11 > 10)** but well under hard-deny on complexity (2 complex tasks ≤ 5). Mitigating factors: (a) the plans.xml edit is dispatcher-owned per spec-pipeline invariant #5 and lives outside the plan-executor's blast-radius, reducing the executor-side count to 10; (b) the spec amendment (task 9c-4) is docs-only and §12 explicitly forbids splitting it out as a predecessor session; (c) the three test-file modifications are additive (new functions in existing files), not file-creation. Accepted by the user during the spec-to-plan confirmation step. Recorded so future readers see the threshold was deliberated.

- **Q9 — `synthesize_extraction_diagnostics` returns a fresh list, never mutates inputs.** Mirrors the diagnostics-engine "Diagnostics are computed, never stored" invariant (spec §11 line 2). The trace is read-only input; the function emits new `Diagnostic` instances and returns a new list. This keeps the constraint compliance audit trivial: there is exactly one mutation site for `ExtractionTrace` state — `verify_field` (added in 9a cycle 9a-2), called by paralegal action, never by the diagnostics engine.

- **Q10 — `INCOMPLETE` sentinel handling in synthesis.** The synthesis predicate for `extraction.no_normalized_value` is `field.normalized_value is None or field.normalized_value is INCOMPLETE`. Identity comparison (`is`), not equality. This matches spec §5.3's "Compared via identity" docstring on `INCOMPLETE`. The sentinel is imported from `trust_generator.v3.extraction.trace` (NOT exported via `__all__` per the established discipline; consumers import explicitly).

---

## Dispatch Protocol

When invoking `/spec-pipeline 2026-04-27-ocr-protocol-ollama-9c exec-plan`, the dispatcher (you, or a routing skill) controls which cycles execute via a scope-token in the dispatcher prompt, mirroring 9a/9b's convention:

| Scope-token | Effect |
| ----------- | ------ |
| (no scope-token, or `cycles=all`) | Plan-executor walks `<cycle>` and `<task>` blocks in document order, executing each per its `commits` attribute. |
| `cycles=[9c-1]` | Plan-executor opens only the cycle whose `id` attribute matches; verifies `depends-on` cycles' Green commits exist via `git log --grep`; executes Red→Green for that cycle alone. |
| `cycles=[9c-1..9c-2]` (inclusive range) | Plan-executor walks the contiguous cycle range; same dependency check at the range's lower bound. |
| `cycles=[9c-1, 9c-3]` (explicit list) | Plan-executor walks each id in the order supplied. Use sparingly — non-contiguous execution risks skipping a `depends-on` link. |

Each `<cycle>` and `<task>` block carries five attributes:

| Attribute        | Purpose                                                                                     |
| ---------------- | ------------------------------------------------------------------------------------------- |
| `id`             | Stable scope token (`9c-1`, …, `9c-5`).                                                     |
| `spec-ref`       | Backlink to the spec section(s) the cycle/task implements.                                  |
| `blast-radius`   | Semicolon-separated list of file paths the cycle/task is allowed to create or modify. Plan-executor must NOT edit any path outside this list during the cycle; new paths surfaced at green-time become chores via scope-maintenance. |
| `depends-on`     | Cycle/task-id list whose commits must already exist. Cycle 9c-1's `depends-on` references 9a-3 (the path-resolver Green commit) and 9a-2 (the trace Green commit) as the gating predecessors; 9b commits are NOT required (9c consumes 9a's surface only). |
| `commits`        | The cycle's commit shape — `red,green` (default for both 9c cycles), or single (for `<task>` blocks). |

The dispatching session retains responsibility for the post-execution close-out (review chore-list, commit `plans.xml` flip — invariant #5 in spec-pipeline SKILL.md).

---

## File Structure

**Created (production):**

| Path | Responsibility |
| ---- | -------------- |
| `src/trust_generator/v3/extraction/synthesis.py` | `synthesize_extraction_diagnostics(trust, extraction) -> list[Diagnostic]`; `LOW_CONFIDENCE_THRESHOLD` constant; private `_make_diag` helper. Emits the three new `extraction.*` codes per spec §7.7. |

**Created (tests):**

| Path | Responsibility |
| ---- | -------------- |
| `tests/v3/extraction/test_synthesis.py` | Cycle 9c-1 tests (empty trace, verified-suppression, unverified-illegible-emit, stale-path filter, low-confidence branch live, no-normalized-value branch, multi-field emission order, FieldExtraction.field_path match). |

**Modified (production):**

| Path | Change |
| ---- | ------ |
| `src/trust_generator/v3/extraction/__init__.py` | Cycle 9c-1: append `synthesize_extraction_diagnostics` to `__all__` (RUF022 will auto-alphabetize on `pixi run fix`; the alphabetic position is between `resolve` and `RawSelfReport` after sort). |
| `src/trust_generator/v3/diagnostics/engine.py` | Cycle 9c-2: add `extraction: ExtractionTrace \| None = None` kwarg to `diagnose()`; pass through to `build_eval_context`; call `synthesize_extraction_diagnostics(trust, extraction)` and use its result as the seed list (trace-driven Diagnostics first per §5.8 merge order). |
| `src/trust_generator/v3/diagnostics/eval_context.py` | Cycle 9c-2: add `extraction: ExtractionTrace \| None = None` kwarg to `build_eval_context()`; conditionally inject `"extraction"` key into the returned dict using `model_dump(mode="python")` + `_unwrap_enums`. |
| `src/trust_generator/v3/diagnostics/loader.py` | Cycle 9c-2: add `"extraction": rule_engine.DataType.UNDEFINED` to the `_build_rule_context()` type resolver dict (between `now` and the closing brace). |

**Modified (tests):**

| Path | Change |
| ---- | ------ |
| `tests/v3/diagnostics/test_diagnose.py` | Cycle 9c-2: add four new tests (regression-pin: no extraction equivalent to old behavior; merge-order pin: trace-driven first; lifecycle pin: emit→verify→no re-emit; namespace inclusion/omission). |
| `tests/v3/diagnostics/test_eval_context.py` | Cycle 9c-2: add three new tests (extraction namespace present when supplied, absent when None, fields content matches `model_dump`). |
| `tests/v3/diagnostics/test_override.py` | Task 9c-3: add two regression tests (extraction-source diagnostic accepted by `force_generation`; verified field never reaches override). |

**Modified (docs):**

| Path | Change |
| ---- | ------ |
| `docs/superpowers/specs/2026-04-23-diagnostics-engine-design.md` | Task 9c-4: §5.1 signature, §5.2 eval_context shape, new subsection on trace-driven synthesis, new cycle entry in §6 covering the synthesis cycle. Per spec §12. |

**Modified (metadata):**

| Path | Change |
| ---- | ------ |
| `.claude/context/plans.xml` | Task 9c-5: set `status="closed"` on the 9c entry; bump `modified-at`. |

**Total touched files:** 11 (1 new src, 1 new test, 4 modified src/init, 3 modified tests, 1 modified docs, 1 modified metadata). See Q8.

---

## Predecessor verification (run once before any cycle)

Gating, not implementing. If any check fails, escalate.

- [ ] **Step P1: Verify 9a's Green commits exist**

Run:

```bash
git log --oneline --grep='GREEN — cycle 9a-' | wc -l
```

Expected: `4` (one Green commit per 9a cycle: 9a-1, 9a-2, 9a-3, 9a-4). If less than 4: 9a did not complete; halt and finish 9a first.

- [ ] **Step P2: Verify 9a's surface is importable (synthesis depends on `ExtractionTrace`, `FieldExtraction`, `paths.resolve`, `INCOMPLETE`)**

Run:

```bash
pixi run python -c "from trust_generator.v3.extraction import (
    ExtractionTrace, FieldExtraction, resolve,
); from trust_generator.v3.extraction.trace import INCOMPLETE; print('ok')"
```

Expected: `ok` (no traceback). If `ImportError`: 9a's `__init__.py` has drifted; halt and reconcile.

- [ ] **Step P3: Verify diagnostics-engine surface is present (cycle 9c-2 modifies `diagnose`, `build_eval_context`, `_build_rule_context`)**

Run:

```bash
pixi run python -c "from trust_generator.v3.diagnostics.engine import diagnose; from trust_generator.v3.diagnostics.eval_context import build_eval_context; from trust_generator.v3.diagnostics.loader import _build_rule_context; print('ok')"
```

Expected: `ok`. If `ImportError`: the diagnostics-engine plans (`2026-04-23-diagnostics-engine-core` and `2026-04-23-diagnostics-engine-rules`, both currently `closed`) drifted; halt and reconcile.

- [ ] **Step P4: Verify `Diagnostic`, `DiagnosticSource.EXTRACTION`, `DiagnosticContext.BOTH`, `DiagnosticLevel` are importable**

Run:

```bash
pixi run python -c "from trust_generator.v3.schema import Diagnostic, DiagnosticContext, DiagnosticLevel, DiagnosticSource; assert DiagnosticSource.EXTRACTION.value == 'extraction'; assert DiagnosticContext.BOTH.value == 'both'; print('ok')"
```

Expected: `ok`. If `AssertionError` or `ImportError`: the schema enum constants drifted; halt and reconcile.

- [ ] **Step P5: Verify the project gate is green pre-cycle**

Run: `pixi run check`
Expected: lint passes, mypy passes, all tests pass. Exit code 0.
If non-green: halt — 9c starts from a green baseline so each cycle's red/green delta is unambiguous.

- [ ] **Step P6: Verify the current branch is a feature branch**

Run: `git branch --show-current`
Expected: a branch name that is NOT `main`. The current working branch (per session start: `v3.0.0`) is fine.

- [ ] **Step P7: Verify `firm_config_factory` and `trust_data_factory` fixtures exist**

Run:

```bash
pixi run python -c "import importlib.util, pathlib; p = pathlib.Path('tests/v3/diagnostics/conftest.py'); spec = importlib.util.spec_from_file_location('conftest', p); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); print('ok')"
```

Expected: `ok`. If `FileNotFoundError`: the conftest moved; halt and locate the new path before proceeding.

---

## Cycle 9c-1 — `synthesize_extraction_diagnostics` and stale-path filtering

<cycle id="9c-1"
       spec-ref="§5.8, §6.7 (minus lifecycle test), §7.7"
       blast-radius="src/trust_generator/v3/extraction/synthesis.py; src/trust_generator/v3/extraction/__init__.py; tests/v3/extraction/test_synthesis.py"
       depends-on="9a-2, 9a-3"
       commits="red,green">

Land the trace-driven Diagnostic emitter as a pure function. This cycle covers the seven function-level tests from spec §6.7 (the lifecycle test relocates to 9c-2 because it depends on `diagnose(trust, config, extraction=trace)` which 9c-2 lands).

**Refactor decision:** No refactor stage. The Green-phase output is a single linear loop over `extraction.fields` with three guarded predicates (illegible / low-confidence / no-normalized-value), each emitting a structurally identical `Diagnostic` via the `_make_diag` helper. The only refactor candidate would be promoting `_make_diag` to a module-level public helper, but it is consumed only within `synthesize_extraction_diagnostics` and is private (`_` prefix); promoting it would expand surface without consumer demand. Per `.claude/rules/development-strategy.md` `refactor_threshold` (structural duplication / nested conditionals / mixed orthogonal concerns), none apply: the three predicates are not duplicated (each tests a distinct field state), the conditionals are flat (each `if` body is a single `result.append(...)` plus `continue`), and the function has one concern (synthesize Diagnostics from a trace).

**Files:**

- Create: `src/trust_generator/v3/extraction/synthesis.py`
- Modify: `src/trust_generator/v3/extraction/__init__.py`
- Test: `tests/v3/extraction/test_synthesis.py`

### Step 1: Write the failing test file

- [ ] Create `tests/v3/extraction/test_synthesis.py` with the following content:

```python
"""Cycle 9c-1: trace-driven Diagnostic synthesis."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from trust_generator.v3.extraction.synthesis import (
    LOW_CONFIDENCE_THRESHOLD,
    synthesize_extraction_diagnostics,
)
from trust_generator.v3.extraction.trace import (
    INCOMPLETE,
    ExtractionTrace,
    FieldExtraction,
)
from trust_generator.v3.schema import (
    Diagnostic,
    DiagnosticContext,
    DiagnosticLevel,
    DiagnosticSource,
)


@pytest.fixture
def trust(trust_data_factory):
    """A populated TrustData with at least one grantor and one child so
    realistic field_paths resolve."""
    return trust_data_factory()


def _trace(*fields: FieldExtraction) -> ExtractionTrace:
    return ExtractionTrace(
        fields=list(fields),
        backend_id="ollama:test-model",
        extracted_at=datetime.now(UTC),
    )


def test_none_extraction_returns_empty_list(trust):
    """`extraction is None` → no Diagnostics."""
    assert synthesize_extraction_diagnostics(trust, None) == []


def test_empty_trace_returns_empty_list(trust):
    """A trace with zero fields → no Diagnostics."""
    assert synthesize_extraction_diagnostics(trust, _trace()) == []


def test_verified_illegible_field_is_suppressed(trust):
    """A verified illegible field never emits a Diagnostic."""
    trace = _trace(
        FieldExtraction(
            field_path="grantor.full_legal_name",
            raw_value="(scribble)",
            illegible=True,
            verified=True,
            verified_at=datetime.now(UTC),
        ),
    )
    assert synthesize_extraction_diagnostics(trust, trace) == []


def test_unverified_illegible_resolved_path_emits_diagnostic(trust):
    """An unverified illegible field whose path resolves emits one
    extraction.illegible_field Diagnostic."""
    trace = _trace(
        FieldExtraction(
            field_path="grantor.full_legal_name",
            raw_value="(scribble)",
            illegible=True,
        ),
    )
    diags = synthesize_extraction_diagnostics(trust, trace)
    assert len(diags) == 1
    diag = diags[0]
    assert isinstance(diag, Diagnostic)
    assert diag.code == "extraction.illegible_field"
    assert diag.level == DiagnosticLevel.WARNING
    assert diag.source == DiagnosticSource.EXTRACTION
    assert diag.context == DiagnosticContext.BOTH
    assert diag.field_path == "grantor.full_legal_name"


def test_stale_path_is_silently_filtered(trust):
    """A trace entry whose field_path no longer resolves emits no
    Diagnostic (post-edit cleanup behavior)."""
    trace = _trace(
        FieldExtraction(
            field_path="children[99].full_legal_name",  # out of range
            raw_value="Jane Q. Public",
            illegible=True,
        ),
    )
    assert synthesize_extraction_diagnostics(trust, trace) == []


def test_low_confidence_branch_emits_when_below_threshold(trust):
    """A hand-constructed FieldExtraction with confidence_self_report
    below LOW_CONFIDENCE_THRESHOLD emits an info-level Diagnostic.
    Branch is structurally live for the future ConfidenceProtocol
    (chore 4.3c); v3.0 backends do not populate confidence_self_report
    so this branch is unreachable from production traces."""
    assert LOW_CONFIDENCE_THRESHOLD == pytest.approx(0.5)
    trace = _trace(
        FieldExtraction(
            field_path="grantor.full_legal_name",
            raw_value="James William Thompson Jr.",
            normalized_value="James William Thompson Jr.",
            confidence_self_report=0.3,
        ),
    )
    diags = synthesize_extraction_diagnostics(trust, trace)
    assert len(diags) == 1
    assert diags[0].code == "extraction.low_confidence_field"
    assert diags[0].level == DiagnosticLevel.INFO


def test_low_confidence_branch_silent_when_none(trust):
    """v3.0 production case: confidence_self_report is None → no emission
    from the low-confidence branch."""
    trace = _trace(
        FieldExtraction(
            field_path="grantor.full_legal_name",
            raw_value="James William Thompson Jr.",
            normalized_value="James William Thompson Jr.",
            confidence_self_report=None,
        ),
    )
    assert synthesize_extraction_diagnostics(trust, trace) == []


def test_no_normalized_value_emits_when_normalized_is_none(trust):
    """Field is not illegible, normalized_value is None, not verified
    → extraction.no_normalized_value warning."""
    trace = _trace(
        FieldExtraction(
            field_path="grantor.full_legal_name",
            raw_value="James William Thompson Jr.",
            normalized_value=None,
        ),
    )
    diags = synthesize_extraction_diagnostics(trust, trace)
    assert len(diags) == 1
    assert diags[0].code == "extraction.no_normalized_value"
    assert diags[0].level == DiagnosticLevel.WARNING


def test_no_normalized_value_emits_when_normalized_is_INCOMPLETE(trust):
    """The INCOMPLETE sentinel triggers no_normalized_value (identity
    comparison, not equality)."""
    trace = _trace(
        FieldExtraction(
            field_path="grantor.full_legal_name",
            raw_value="James William Thompson Jr.",
            normalized_value=INCOMPLETE,
        ),
    )
    diags = synthesize_extraction_diagnostics(trust, trace)
    assert len(diags) == 1
    assert diags[0].code == "extraction.no_normalized_value"


def test_emission_order_matches_trace_fields_insertion_order(trust):
    """Multiple problematic unverified fields emit in trace.fields order."""
    trace = _trace(
        FieldExtraction(
            field_path="grantor.full_legal_name",
            raw_value="(scribble 1)",
            illegible=True,
        ),
        FieldExtraction(
            field_path="children[0].full_legal_name",
            raw_value="(scribble 2)",
            illegible=True,
        ),
    )
    diags = synthesize_extraction_diagnostics(trust, trace)
    assert [d.field_path for d in diags] == [
        "grantor.full_legal_name",
        "children[0].full_legal_name",
    ]


def test_diagnostic_field_path_matches_field_extraction_field_path(trust):
    """Synthesized Diagnostic.field_path is exactly FieldExtraction.field_path
    (single shared convention; no mangling)."""
    trace = _trace(
        FieldExtraction(
            field_path="children[0].full_legal_name",
            raw_value="Mary Margaret Thompson",
            illegible=True,
        ),
    )
    diags = synthesize_extraction_diagnostics(trust, trace)
    assert diags[0].field_path == "children[0].full_legal_name"
```

### Step 2: Run the failing test to verify Red

- [ ] Run:

```bash
pixi run test test_synthesis -v
```

Expected: collection-time `ImportError: cannot import name 'synthesize_extraction_diagnostics' from 'trust_generator.v3.extraction.synthesis'` (the module does not exist yet).

If the error is something else (e.g., a `trust_data_factory` fixture issue): halt and reconcile the test file before proceeding to Green.

### Step 3: Commit the Red

- [ ] Stage and commit:

```bash
git add tests/v3/extraction/test_synthesis.py
git commit -m "test(extraction): RED — cycle 9c-1 synthesize_extraction_diagnostics"
```

### Step 4: Implement the Green minimal source

- [ ] Create `src/trust_generator/v3/extraction/synthesis.py` with the following content:

```python
"""Trace-driven Diagnostic synthesis (spec §5.8, §7.7).

The diagnostics engine has two emission sources after 9c lands:

1. **Rule-driven (existing).** YAML-defined ``DiagnosticRule`` evaluated
   by rule-engine against ``eval_context``. One rule emits zero or one
   Diagnostic per call.
2. **Trace-driven (new).** ``synthesize_extraction_diagnostics(trust,
   extraction)`` walks the trace and emits Diagnostics for each
   unverified, problematic FieldExtraction whose ``field_path``
   resolves against ``trust``. One trace emits zero or many Diagnostics
   per call.

The split is a deliberate architectural seam, not a workaround — see
spec §5.8 for rationale.
"""

from __future__ import annotations

from typing import Final

from trust_generator.v3.extraction.paths import resolve
from trust_generator.v3.extraction.trace import INCOMPLETE, ExtractionTrace
from trust_generator.v3.schema import (
    Diagnostic,
    DiagnosticContext,
    DiagnosticLevel,
    DiagnosticSource,
    TrustData,
)

__all__ = ("LOW_CONFIDENCE_THRESHOLD", "synthesize_extraction_diagnostics")

LOW_CONFIDENCE_THRESHOLD: Final[float] = 0.5
"""Threshold below which ``confidence_self_report`` triggers the
``extraction.low_confidence_field`` Diagnostic. Placeholder until chore
4.3c lands the ConfidenceProtocol; v3.0 backends do not populate
``confidence_self_report`` so this branch is unreachable from
production traces. Promotion to firm-config is a non-breaking change at
the point a backend wires real confidence reports.
"""


def synthesize_extraction_diagnostics(
    trust: TrustData,
    extraction: ExtractionTrace | None,
) -> list[Diagnostic]:
    """Emit one Diagnostic per unverified, problematic FieldExtraction
    whose ``field_path`` resolves against ``trust``.

    Returns ``[]`` when ``extraction is None``. Stale entries
    (``field_path`` does not resolve) are silently skipped — they
    correspond to TrustData edits that already removed the field, so the
    user-visible concern is gone.

    Emission order matches ``extraction.fields`` insertion order
    (parser-emission-order pin, spec §6.7).
    """
    if extraction is None:
        return []
    diagnostics: list[Diagnostic] = []
    for field in extraction.fields:
        if field.verified:
            continue
        resolved, _ = resolve(trust, field.field_path)
        if not resolved:
            continue
        if field.illegible:
            diagnostics.append(
                _make_diag(
                    code="extraction.illegible_field",
                    level=DiagnosticLevel.WARNING,
                    message=f"Field {field.field_path!r} marked illegible by extraction backend",
                    field_path=field.field_path,
                )
            )
            continue
        if (
            field.confidence_self_report is not None
            and field.confidence_self_report < LOW_CONFIDENCE_THRESHOLD
        ):
            diagnostics.append(
                _make_diag(
                    code="extraction.low_confidence_field",
                    level=DiagnosticLevel.INFO,
                    message=(
                        f"Field {field.field_path!r} extracted with low "
                        f"confidence ({field.confidence_self_report:.2f})"
                    ),
                    field_path=field.field_path,
                )
            )
            continue
        if field.normalized_value is None or field.normalized_value is INCOMPLETE:
            diagnostics.append(
                _make_diag(
                    code="extraction.no_normalized_value",
                    level=DiagnosticLevel.WARNING,
                    message=f"Field {field.field_path!r} extracted but not normalized",
                    field_path=field.field_path,
                )
            )
    return diagnostics


def _make_diag(
    *,
    code: str,
    level: DiagnosticLevel,
    message: str,
    field_path: str,
) -> Diagnostic:
    return Diagnostic(
        level=level,
        code=code,
        message=message,
        field_path=field_path,
        source=DiagnosticSource.EXTRACTION,
        context=DiagnosticContext.BOTH,
    )
```

### Step 5: Update the extraction package `__init__.py`

- [ ] Open `src/trust_generator/v3/extraction/__init__.py` and:

  1. Add an import block for `synthesize_extraction_diagnostics`:

```python
from trust_generator.v3.extraction.synthesis import synthesize_extraction_diagnostics
```

  Place it in alphabetical position among the existing `from trust_generator.v3.extraction.<module> import ...` block (between `from trust_generator.v3.extraction.protocol import (...)` and `from trust_generator.v3.extraction.trace import (...)`).

  2. Append `"synthesize_extraction_diagnostics"` to the `__all__` tuple. Final tuple should read (alphabetized per RUF022):

```python
__all__ = (
    "ExtractionError",
    "ExtractionProtocol",
    "ExtractionResult",
    "ExtractionTrace",
    "FieldExtraction",
    "IncompleteUntilValidated",
    "OllamaBackend",
    "RawSelfReport",
    "SourceRef",
    "resolve",
    "synthesize_extraction_diagnostics",
)
```

### Step 6: Run the test to verify Green

- [ ] Run:

```bash
pixi run test test_synthesis -v
```

Expected: `11 passed` (one per `def test_*` in the file). All asserts hold.

If any test fails, halt and read the failure message; do not modify the tests to make them pass — modify the source until the tests pass as written.

### Step 7: Run lint + typecheck on the new files only

- [ ] Run:

```bash
pixi run lint && pixi run mypy src/trust_generator/v3/extraction/synthesis.py
```

Expected: both exit 0.

If lint flags RUF022 on `__all__`: run `pixi run fix` (safe autofix) and re-stage the file.

### Step 8: Commit the Green

- [ ] Stage and commit:

```bash
git add src/trust_generator/v3/extraction/synthesis.py src/trust_generator/v3/extraction/__init__.py
git commit -m "feat(extraction): GREEN — cycle 9c-1 synthesize_extraction_diagnostics"
```

### Step 9: Refactor decision recorded (no refactor commit)

- [ ] Per Q6 above and the cycle preamble, no refactor commit. The Green-phase output meets minimum surface; promoting `_make_diag` to a module-level public helper would expand the surface without consumer demand. Move on to cycle 9c-2.

</cycle>

---

## Cycle 9c-2 — `diagnose()` integration, `extraction` namespace, end-to-end lifecycle

<cycle id="9c-2"
       spec-ref="§5.9, §5.10, §6.7 lifecycle, §6.8"
       blast-radius="src/trust_generator/v3/diagnostics/engine.py; src/trust_generator/v3/diagnostics/eval_context.py; src/trust_generator/v3/diagnostics/loader.py; tests/v3/diagnostics/test_diagnose.py; tests/v3/diagnostics/test_eval_context.py"
       depends-on="9c-1"
       commits="red,green">

Plumb the `extraction` parameter through `diagnose()` and `build_eval_context()`, declare the namespace in `_build_rule_context()`, and pin the verify-lifecycle behavior end-to-end.

**Refactor decision:** No refactor stage. The Green-phase changes are pure plumbing additions — a new kwarg on each function, a conditional dict entry, a new type-resolver line, a new prepend call to the result list. Per `.claude/rules/development-strategy.md` `refactor_threshold` (structural duplication / nested conditionals / mixed orthogonal concerns): none apply. The kwarg is a single threadthrough, the conditional dict entry is one `if ...: ctx[...] = ...` block, and the prepend is a `diagnostics = synthesize_extraction_diagnostics(...)` initializer replacing the empty list literal.

**Files:**

- Modify: `src/trust_generator/v3/diagnostics/engine.py`
- Modify: `src/trust_generator/v3/diagnostics/eval_context.py`
- Modify: `src/trust_generator/v3/diagnostics/loader.py`
- Test: `tests/v3/diagnostics/test_diagnose.py` (additive)
- Test: `tests/v3/diagnostics/test_eval_context.py` (additive)

### Step 1: Write the failing tests in `test_eval_context.py`

- [ ] Open `tests/v3/diagnostics/test_eval_context.py` and append the following block at the bottom of the file (after the existing tests):

```python
# ---------------------------------------------------------------------------
# Cycle 9c-2: extraction namespace
# ---------------------------------------------------------------------------

from datetime import UTC, datetime as _dt

from trust_generator.v3.extraction.trace import ExtractionTrace, FieldExtraction


def _make_trace() -> ExtractionTrace:
    return ExtractionTrace(
        fields=[
            FieldExtraction(
                field_path="grantor.full_legal_name",
                raw_value="James William Thompson Jr.",
                illegible=True,
            ),
        ],
        backend_id="ollama:test-model",
        extracted_at=_dt.now(UTC),
    )


def test_extraction_namespace_omitted_when_not_supplied(
    firm_config_factory, trust_data_factory
):
    """`extraction=None` (default) → no `extraction` key in the context."""
    trust = trust_data_factory()
    config = firm_config_factory()
    ctx = build_eval_context(trust, config, _dt.now(UTC).date())
    assert "extraction" not in ctx


def test_extraction_namespace_present_when_supplied(
    firm_config_factory, trust_data_factory
):
    """`extraction=trace` → `extraction` key present in the context."""
    trust = trust_data_factory()
    config = firm_config_factory()
    ctx = build_eval_context(
        trust, config, _dt.now(UTC).date(), extraction=_make_trace()
    )
    assert "extraction" in ctx
    assert "fields" in ctx["extraction"]
    assert "backend_id" in ctx["extraction"]
    assert ctx["extraction"]["backend_id"] == "ollama:test-model"


def test_extraction_namespace_fields_payload_matches_model_dump(
    firm_config_factory, trust_data_factory
):
    """The fields list mirrors `model_dump`; field_path is preserved verbatim."""
    trust = trust_data_factory()
    config = firm_config_factory()
    trace = _make_trace()
    ctx = build_eval_context(
        trust, config, _dt.now(UTC).date(), extraction=trace
    )
    assert len(ctx["extraction"]["fields"]) == 1
    assert (
        ctx["extraction"]["fields"][0]["field_path"]
        == "grantor.full_legal_name"
    )
    assert ctx["extraction"]["fields"][0]["illegible"] is True
```

### Step 2: Write the failing tests in `test_diagnose.py`

- [ ] Open `tests/v3/diagnostics/test_diagnose.py` and append the following block at the bottom of the file:

```python
# ---------------------------------------------------------------------------
# Cycle 9c-2: extraction integration
# ---------------------------------------------------------------------------

from datetime import UTC, datetime as _dt
from pathlib import Path
from textwrap import dedent

from trust_generator.v3.diagnostics.engine import diagnose
from trust_generator.v3.extraction.trace import ExtractionTrace, FieldExtraction
from trust_generator.v3.schema import DiagnosticSource


def _illegible_trace_for(field_path: str) -> ExtractionTrace:
    return ExtractionTrace(
        fields=[
            FieldExtraction(
                field_path=field_path,
                raw_value="(scribble)",
                illegible=True,
            ),
        ],
        backend_id="ollama:test-model",
        extracted_at=_dt.now(UTC),
    )


def test_diagnose_without_extraction_is_regression_equivalent(
    firm_config_factory, trust_data_factory
):
    """diagnose() called without the new extraction kwarg behaves
    identically to the pre-9c implementation. Regression pin."""
    trust = trust_data_factory()
    config = firm_config_factory()
    diags = diagnose(trust, config)
    # No extraction-source diagnostics should appear when extraction is omitted.
    assert all(d.source != DiagnosticSource.EXTRACTION for d in diags)


def test_diagnose_merges_trace_driven_first_then_rule_driven(
    firm_config_factory, trust_data_factory
):
    """Trace-driven Diagnostics emit before rule-driven Diagnostics in the
    returned list (spec §5.8 merge-order pin)."""
    trust = trust_data_factory()
    config = firm_config_factory()
    trace = _illegible_trace_for("grantor.full_legal_name")
    diags = diagnose(trust, config, extraction=trace)
    extraction_indices = [
        i for i, d in enumerate(diags) if d.source == DiagnosticSource.EXTRACTION
    ]
    non_extraction_indices = [
        i for i, d in enumerate(diags) if d.source != DiagnosticSource.EXTRACTION
    ]
    assert extraction_indices, "expected at least one extraction-source diagnostic"
    if non_extraction_indices:
        # If any rule-driven diagnostics exist, every extraction diagnostic
        # must precede every rule-driven diagnostic.
        assert max(extraction_indices) < min(non_extraction_indices)


def test_diagnose_lifecycle_emit_verify_no_re_emit(
    firm_config_factory, trust_data_factory
):
    """End-to-end: emit illegible_field, verify the field, re-call
    diagnose(), assert the matching diagnostic is gone (spec §6.7
    lifecycle pin)."""
    trust = trust_data_factory()
    config = firm_config_factory()
    trace = _illegible_trace_for("grantor.full_legal_name")

    first = diagnose(trust, config, extraction=trace)
    assert any(
        d.code == "extraction.illegible_field"
        and d.field_path == "grantor.full_legal_name"
        for d in first
    )

    trace.verify_field("grantor.full_legal_name")

    second = diagnose(trust, config, extraction=trace)
    assert not any(
        d.code == "extraction.illegible_field"
        and d.field_path == "grantor.full_legal_name"
        for d in second
    )


def test_yaml_rule_with_guard_reads_extraction_namespace(
    firm_config_factory, trust_data_factory, tmp_path: Path
):
    """A custom YAML rule guarded with `extraction != null and ...`
    evaluates without `engine.symbol_unknown` when extraction is
    provided."""
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()
    (rules_dir / "extraction_guarded.yml").write_text(
        dedent(
            """\
            - code: custom.illegible_count_high
              level: warning
              message: "More than zero illegible fields"
              source: extraction
              context: both
              expression: "extraction != null and extraction.fields.length > 0"
            """
        )
    )
    config = firm_config_factory(custom_rules_dir=rules_dir)
    trust = trust_data_factory()
    trace = _illegible_trace_for("grantor.full_legal_name")

    diags = diagnose(trust, config, extraction=trace)
    codes = [d.code for d in diags]
    assert "custom.illegible_count_high" in codes
    assert not any(d.code == "engine.symbol_unknown" for d in diags)


def test_yaml_rule_without_guard_emits_symbol_unknown_when_no_extraction(
    firm_config_factory, trust_data_factory, tmp_path: Path
):
    """Documented behavior pin: an unguarded `extraction.fields`
    reference in a YAML rule emits `engine.symbol_unknown` when
    extraction is None."""
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()
    (rules_dir / "extraction_unguarded.yml").write_text(
        dedent(
            """\
            - code: custom.unguarded_extraction_ref
              level: warning
              message: "References extraction.fields without guard"
              source: extraction
              context: both
              expression: "extraction.fields.length > 0"
            """
        )
    )
    config = firm_config_factory(custom_rules_dir=rules_dir)
    trust = trust_data_factory()

    diags = diagnose(trust, config)
    assert any(d.code == "engine.symbol_unknown" for d in diags)
```

### Step 3: Run the failing tests to verify Red

- [ ] Run:

```bash
pixi run test "test_eval_context or test_diagnose" -v
```

Expected: the new tests fail with one of:
- `TypeError: build_eval_context() got an unexpected keyword argument 'extraction'`
- `TypeError: diagnose() got an unexpected keyword argument 'extraction'`
- `engine.symbol_unknown` for the guarded YAML rule (because `_build_rule_context()` does not yet declare `extraction` in the type resolver, the rule fails to evaluate)

The pre-existing tests in those files MUST still pass. If they do not, halt: a Red commit is only valid if the new tests fail and the existing tests pass.

> **Note on `firm_config_factory(custom_rules_dir=...)`:** if the existing factory does not accept `custom_rules_dir`, inspect `tests/v3/diagnostics/conftest.py` and the factory body; either add the kwarg via fixture parameterization, or construct a `FirmConfig` directly inside the test using `FirmConfig.model_validate({...})` with the `custom_rules_dir` set. The two YAML-rule tests are the only ones that need this; the lifecycle and merge-order tests use the default factory.

### Step 4: Commit the Red

- [ ] Stage and commit:

```bash
git add tests/v3/diagnostics/test_eval_context.py tests/v3/diagnostics/test_diagnose.py
git commit -m "test(diagnostics): RED — cycle 9c-2 diagnose() extraction integration"
```

### Step 5: Implement the Green minimal source — `eval_context.py`

- [ ] Open `src/trust_generator/v3/diagnostics/eval_context.py` and apply two edits:

**Edit 1: Update the imports block at the top of the file** (add `ExtractionTrace`):

```python
from trust_generator.v3.config.firm import FirmConfig
from trust_generator.v3.extraction.trace import ExtractionTrace
from trust_generator.v3.schema import TrustData
```

**Edit 2: Update `build_eval_context` signature and body.** Replace the existing function with:

```python
def build_eval_context(
    trust: TrustData,
    config: FirmConfig,
    ref_date: date,
    *,
    extraction: ExtractionTrace | None = None,
) -> dict[str, Any]:
    """Compose the eval context for rule expression evaluation.

    Args:
        trust: post-fill canonical TrustData (consumed, not mutated).
        config: FirmConfig (consumed, not mutated).
        ref_date: explicit reference date; resolution chain handled by diagnose().
        extraction: optional ExtractionTrace; when supplied, exposed under
            the ``extraction`` namespace so YAML rules can reference
            ``extraction.fields`` (with a ``extraction != null and ...``
            guard).

    Returns:
        ``{"trust": dict, "firm": dict, "now": date}``, plus
        ``"extraction": dict`` when ``extraction`` is supplied.
    """
    trust_dict: dict[str, Any] = trust.model_dump(mode="python")

    for prop in COMPUTED_PROPERTIES:
        value = getattr(trust, prop)
        if isinstance(value, list):
            trust_dict[prop] = [
                v.model_dump(mode="python") if hasattr(v, "model_dump") else v
                for v in value
            ]
        else:
            trust_dict[prop] = value

    trust_dict["minor_beneficiaries"] = [
        b.model_dump(mode="python") for b in trust.minor_beneficiaries(ref_date)
    ]

    ctx: dict[str, Any] = {
        "trust": _unwrap_enums(trust_dict),
        "firm": _unwrap_enums(config.model_dump(mode="python")),
        "now": ref_date,
    }
    if extraction is not None:
        ctx["extraction"] = _unwrap_enums(extraction.model_dump(mode="python"))
    return ctx
```

### Step 6: Implement the Green minimal source — `loader.py`

- [ ] Open `src/trust_generator/v3/diagnostics/loader.py` and modify `_build_rule_context()` to add the extraction entry:

```python
def _build_rule_context() -> rule_engine.Context:
    type_resolver = rule_engine.type_resolver_from_dict(
        {
            "trust": rule_engine.DataType.UNDEFINED,
            "firm": rule_engine.DataType.UNDEFINED,
            "now": rule_engine.DataType.DATETIME,
            "extraction": rule_engine.DataType.UNDEFINED,
        }
    )
    return rule_engine.Context(type_resolver=type_resolver)
```

The new line is the `"extraction": rule_engine.DataType.UNDEFINED,` entry, placed after `now` and before the closing brace.

### Step 7: Implement the Green minimal source — `engine.py`

- [ ] Open `src/trust_generator/v3/diagnostics/engine.py` and replace its body with:

```python
"""diagnose() entry point — pure coordinator over the diagnostics subsystem.

Per spec §5.1: builds eval context, loads + caches rules, evaluates each,
returns the diagnostic list. Trace-driven Diagnostics (from
``synthesize_extraction_diagnostics``) precede rule-driven Diagnostics
in the returned list per spec §5.8 merge order.
"""

from __future__ import annotations

from datetime import date, datetime

from trust_generator.v3.config.firm import FirmConfig
from trust_generator.v3.diagnostics.eval_context import build_eval_context
from trust_generator.v3.diagnostics.loader import load_rules
from trust_generator.v3.extraction.synthesis import synthesize_extraction_diagnostics
from trust_generator.v3.extraction.trace import ExtractionTrace
from trust_generator.v3.schema import Diagnostic, TrustData

__all__ = ("diagnose",)


def diagnose(
    trust: TrustData,
    config: FirmConfig,
    *,
    ref_date: date | None = None,
    extraction: ExtractionTrace | None = None,
) -> list[Diagnostic]:
    """Compute diagnostics for a TrustData against a FirmConfig.

    Args:
        trust: post-fill canonical TrustData (consumed, not mutated).
        config: FirmConfig (consumed, not mutated).
        ref_date: explicit reference date for time-dependent rule context;
            defaults via chain ``trust.trust_id.execution_date -> datetime.now().astimezone().date()``.
        extraction: optional ExtractionTrace produced by an
            ``ExtractionProtocol`` backend; when supplied, trace-driven
            Diagnostics (illegible/low-confidence/no-normalized-value)
            precede rule-driven Diagnostics in the returned list.

    Returns:
        List of Diagnostic instances. Order is
        (trace-driven, builtin_load_order, custom_load_order). Never
        raises during evaluation; runtime failures yield meta-diagnostics
        in-stream.
    """
    resolved_ref_date = (
        ref_date or trust.trust_id.execution_date or datetime.now().astimezone().date()
    )
    ctx = build_eval_context(trust, config, resolved_ref_date, extraction=extraction)
    rules = load_rules(config)
    diagnostics: list[Diagnostic] = synthesize_extraction_diagnostics(trust, extraction)
    for rule in rules:
        result = rule.evaluate(ctx)
        if result is not None:
            diagnostics.append(result)
    return diagnostics
```

The only line-level deltas from the pre-9c version are:
- Two new imports (`synthesize_extraction_diagnostics`, `ExtractionTrace`)
- Updated docstring
- New `extraction` kwarg in the signature
- `extraction=extraction` passed to `build_eval_context`
- `synthesize_extraction_diagnostics(trust, extraction)` replaces the bare `[]` initializer for `diagnostics`

### Step 8: Run the tests to verify Green

- [ ] Run:

```bash
pixi run test "test_eval_context or test_diagnose" -v
```

Expected: all tests pass — both pre-existing and new. If a pre-existing test now fails: halt, the change broke a regression invariant. If a new test fails, read the failure and fix the source (not the test).

### Step 9: Run the full diagnostics test suite for cross-impact

- [ ] Run:

```bash
pixi run test tests/v3/diagnostics -v
```

Expected: all green. Pay attention to `test_starter_rules.py` and `test_rule_loader.py` — the type-resolver expansion could in principle affect them; if any starter-rule test fails, halt and read the failure.

### Step 10: Run lint + mypy on the modified files

- [ ] Run:

```bash
pixi run lint && pixi run mypy src/trust_generator/v3/diagnostics
```

Expected: both exit 0.

### Step 11: Commit the Green

- [ ] Stage and commit:

```bash
git add src/trust_generator/v3/diagnostics/engine.py src/trust_generator/v3/diagnostics/eval_context.py src/trust_generator/v3/diagnostics/loader.py
git commit -m "feat(diagnostics): GREEN — cycle 9c-2 diagnose() extraction integration"
```

### Step 12: Refactor decision recorded (no refactor commit)

- [ ] Per Q6 above and the cycle preamble, no refactor commit. The Green-phase changes are minimal plumbing — kwarg threadthrough, conditional dict entry, type-resolver line, prepend call. No structural duplication, no nested conditionals, no orthogonal concerns to extract. Move on to task 9c-3.

</cycle>

---

## Task 9c-3 — Override interaction regression pin (test-only)

<task id="9c-3"
      spec-ref="§6.9"
      blast-radius="tests/v3/diagnostics/test_override.py"
      depends-on="9c-2">

Verification-only task. Spec §6.9 Green explicitly: "The existing `force_generation` already accepts arbitrary Diagnostics by code. No new code; the test pins the integration." Same pattern as 9b-5 (verification deliverable, single honest commit).

**Files:**

- Modify: `tests/v3/diagnostics/test_override.py`

### Step 1: Append the regression tests

- [ ] Open `tests/v3/diagnostics/test_override.py` and append the following block at the bottom of the file:

```python
# ---------------------------------------------------------------------------
# Task 9c-3: extraction-source diagnostics flow through force_generation
# ---------------------------------------------------------------------------

from datetime import UTC, datetime as _dt
from pathlib import Path as _Path

from trust_generator.v3.diagnostics.engine import diagnose
from trust_generator.v3.extraction.trace import ExtractionTrace, FieldExtraction
from trust_generator.v3.schema import (
    DiagnosticContext,
    DiagnosticLevel,
    DiagnosticSource,
)


def _extraction_diag() -> Diagnostic:
    """A Diagnostic shaped like one synthesized by 9c-1 from an
    illegible FieldExtraction."""
    return Diagnostic(
        level=DiagnosticLevel.WARNING,
        code="extraction.illegible_field",
        message="Field 'grantor.full_legal_name' marked illegible",
        field_path="grantor.full_legal_name",
        source=DiagnosticSource.EXTRACTION,
        context=DiagnosticContext.BOTH,
    )


def test_force_generation_accepts_extraction_source_diagnostic(
    firm_config_factory, trust_data_factory, tmp_audit_dir: _Path
):
    """force_generation writes an audit record listing the
    extraction-source diagnostic's code; pins that the override flow
    treats extraction-source codes identically to schema/business_rule
    codes."""
    trust = trust_data_factory()
    config = firm_config_factory(audit_log_dir=tmp_audit_dir)
    diag = _extraction_diag()
    record = force_generation(
        trust, config, [diag], reason="paralegal confirmed illegible field at intake review"
    )
    assert record.overridden_codes == ["extraction.illegible_field"]
    audit_files = list(tmp_audit_dir.glob("audit-*.jsonl"))
    assert len(audit_files) == 1
    line = audit_files[0].read_text(encoding="utf-8").splitlines()[0]
    assert "extraction.illegible_field" in line


def test_verified_field_never_reaches_force_generation(
    firm_config_factory, trust_data_factory, tmp_audit_dir: _Path
):
    """A verified extraction field is filtered by synthesis (cycle
    9c-1) before diagnose() returns; force_generation never sees it.
    Pins the merge-step filter."""
    trust = trust_data_factory()
    config = firm_config_factory(audit_log_dir=tmp_audit_dir)
    trace = ExtractionTrace(
        fields=[
            FieldExtraction(
                field_path="grantor.full_legal_name",
                raw_value="(scribble)",
                illegible=True,
            ),
        ],
        backend_id="ollama:test-model",
        extracted_at=_dt.now(UTC),
    )
    trace.verify_field("grantor.full_legal_name")

    diags = diagnose(trust, config, extraction=trace)
    extraction_diags = [d for d in diags if d.source == DiagnosticSource.EXTRACTION]
    assert extraction_diags == []

    # If a caller still tries to override an extraction diagnostic that
    # was never returned, force_generation is signature-tolerant — but
    # the merge step ensures verified fields don't surface to the user
    # in the first place. Pin both halves.
    record = force_generation(
        trust,
        config,
        diags,
        reason="overriding remaining diagnostics after paralegal verification",
    )
    assert "extraction.illegible_field" not in record.overridden_codes
```

> **Note on fixture availability:** if `tmp_audit_dir` and `firm_config_factory(audit_log_dir=...)` are not the existing wiring, inspect the conftest fixtures used by `test_happy_path_writes_record` (line 31 of the same file) and replicate the same fixture composition. The test must use the same fixtures as the existing `force_generation` happy-path test.

### Step 2: Run the new tests

- [ ] Run:

```bash
pixi run test test_force_generation_accepts_extraction_source_diagnostic -v
pixi run test test_verified_field_never_reaches_force_generation -v
```

Expected: both pass on the first run (verification-only — no source change required).

If either test fails, read the failure carefully:
- A failure on `test_force_generation_accepts_extraction_source_diagnostic` would indicate that `force_generation` rejects the EXTRACTION source — this would be a contract violation worth investigating before a Green-no-op commit.
- A failure on `test_verified_field_never_reaches_force_generation` would indicate a bug in cycle 9c-1's verify-suppression logic (a field marked verified is still emitting). Halt, fix the synthesis bug in a 9c-1 follow-up commit, and re-run.

### Step 3: Run the full override test suite for cross-impact

- [ ] Run:

```bash
pixi run test tests/v3/diagnostics/test_override.py -v
```

Expected: every test in the file passes (existing + new).

### Step 4: Commit the test pin

- [ ] Stage and commit:

```bash
git add tests/v3/diagnostics/test_override.py
git commit -m "test(diagnostics): cycle 9c-3 force_generation accepts extraction-source diagnostics"
```

</task>

---

## Task 9c-4 — Diagnostics-engine spec amendment (atomic, §12)

<task id="9c-4"
      spec-ref="§12"
      blast-radius="docs/superpowers/specs/2026-04-23-diagnostics-engine-design.md"
      depends-on="9c-3">

Land the diagnostics-engine spec amendment per OCR spec §12 in the same PR as the implementation. Per §12 paragraph 2: "Sequencing them as a separate predecessor would create a window during which `diagnose()` has the new signature but no caller exercises it, with no test coverage in between. Landing them together keeps the amendment grounded in working code." This task is the docs half of that atomicity.

The amendment text is informed by what actually shipped (parameter spelling, signature shape, eval_context layout) — landing this after cycles 9c-1+9c-2+9c-3 ensures the amendment matches the code.

**Files:**

- Modify: `docs/superpowers/specs/2026-04-23-diagnostics-engine-design.md`

### Step 1: Read the current diagnostics-engine spec sections that change

- [ ] Run:

```bash
pixi run python -c "
import re
text = open('docs/superpowers/specs/2026-04-23-diagnostics-engine-design.md').read()
for m in re.finditer(r'^### 5\.\d.*$|^## 6\..*$|^### 6\.\d.*$', text, re.MULTILINE):
    print(m.group(0))
"
```

Expected: a list of subsection headings under §5 and §6. Identify the lines that map to "diagnose() entry point" (§5.1) and "Eval context (build_eval_context)" (§5.2), and the §6 cycle list. These are the amendment targets.

### Step 2: Amend §5.1 — `diagnose()` signature

- [ ] In `docs/superpowers/specs/2026-04-23-diagnostics-engine-design.md`, locate the §5.1 code block that documents the `diagnose()` signature (around the line `# src/trust_generator/v3/diagnostics/engine.py`). Replace the signature line with the post-9c form. The replacement must:

  1. Add `extraction: ExtractionTrace | None = None` as the second keyword-only parameter.
  2. Update any prose that lists the kwargs (typically a "diagnose() accepts" or "kwarg list:" sentence) to include the new parameter.
  3. Add a sentence noting that when `extraction` is supplied, trace-driven Diagnostics from `synthesize_extraction_diagnostics` precede rule-driven Diagnostics in the returned list (cross-reference: OCR spec §5.8 and §6.7).

The specific edit will mirror this shape (verify the surrounding lines before writing):

```python
def diagnose(
    trust: TrustData,
    config: FirmConfig,
    *,
    ref_date: date | None = None,
    extraction: ExtractionTrace | None = None,
) -> list[Diagnostic]:
    ...
```

### Step 3: Amend §5.2 — eval_context shape

- [ ] In the §5.2 subsection, locate the prose or code block that enumerates the top-level keys of the eval_context dict (`trust`, `firm`, `now`). Add a fourth bullet/key:

  - Key: `extraction`
  - Type: `dict` (the `model_dump(mode="python")` of the supplied `ExtractionTrace`, with enums unwrapped)
  - Conditional: present when `diagnose()` is called with `extraction != None`; absent otherwise
  - Cross-reference: OCR spec §5.9

If §5.2 has a code block showing the literal returned dict, update it to include the conditional `"extraction"` entry with a comment noting the conditionality.

### Step 4: Add a new subsection — trace-driven synthesis seam

- [ ] After §5.X (the last subsection under §5 before §6), add a new subsection. Choose the next available number (likely `### 5.7` or higher; check the current numbering and pick `(highest existing + 1)`). The subsection MUST contain:

  - Heading: `### 5.<N> Trace-driven Diagnostic synthesis (9c)`
  - One short paragraph stating the architectural seam: rule-driven evaluation handles TrustData-as-a-whole properties; trace-driven synthesis handles per-field extraction concerns (illegibility, low confidence, no normalized value). Both merge into one `list[Diagnostic]` returned by `diagnose()`.
  - One sentence explicitly cross-referencing OCR spec §5.8 for the full rationale and §7.7 for the new code list.
  - One sentence stating the merge order (trace-driven first), with cross-reference to OCR spec §5.8 last paragraph.

Keep the subsection under ~10 lines. The detail lives in the OCR spec; the diagnostics-engine spec amendment is the index entry that says "this seam exists, here is where it lives."

### Step 5: Add a new cycle entry under §6

- [ ] Under §6 (Implementation: TDD cycles), add a new subsection at the end of the cycle list (after the existing last cycle, likely `### 6.10` per the spec outline). The subsection MUST contain:

  - Heading: `### 6.<N+1> Cycle <K> — Trace-driven synthesis (9c)` where `<K>` is one greater than the last existing cycle number in the diagnostics-engine spec.
  - A pointer sentence: "Implementation lives in OCR spec §6.7 and is exercised by the synthesis cycle in OCR plan `2026-04-27-ocr-protocol-ollama-9c.md`."
  - A note that no rule-engine YAML rules were added; the new `extraction.*` codes (`extraction.illegible_field`, `extraction.low_confidence_field`, `extraction.no_normalized_value`) are emitted directly from `synthesize_extraction_diagnostics` and bypass the YAML loader's namespace enforcement.

Keep this subsection under ~8 lines. It is a backlink, not an implementation guide.

### Step 6: Verify the amended spec is well-formed Markdown

- [ ] Run:

```bash
pixi run python -c "
import pathlib
text = pathlib.Path('docs/superpowers/specs/2026-04-23-diagnostics-engine-design.md').read_text()
heading_lines = [(i+1, line) for i, line in enumerate(text.splitlines()) if line.startswith('#')]
for num, line in heading_lines:
    print(f'{num:4d} {line}')
"
```

Expected: the new §5.<N> and §6.<N+1> headings appear in the listing at the right positions. Section numbers should be monotonically increasing within each top-level heading.

### Step 7: Commit the amendment

- [ ] Stage and commit:

```bash
git add docs/superpowers/specs/2026-04-23-diagnostics-engine-design.md
git commit -m "docs(specs): amend diagnostics-engine spec for 9c trace-driven synthesis (atomic per spec §12)"
```

</task>

---

## Task 9c-5 — Close `plans.xml` 9c entry

<task id="9c-5"
      spec-ref="(plans.xml bookkeeping per spec-pipeline invariant #5)"
      blast-radius=".claude/context/plans.xml"
      depends-on="9c-4">

**Files:**

- Modify: `.claude/context/plans.xml`

Mark this plan closed in the canonical plan reference. Per spec-pipeline invariant #5, the dispatching session — not the plan-executor — commits this flip. The plan-executor's prior cycles report completion; the dispatcher then issues this single bookkeeping commit.

### Step 1: Edit `.claude/context/plans.xml`

The 9c entry's `id`, `plan-md`, and `synopsis` are set during the spec-to-plan drafting commit (this plan-md's authoring session, immediately preceding execution). Task 9c-5 flips the 9c entry's `status` only:

- [ ] In `.claude/context/plans.xml`:
  1. Set `status="closed"` on the `<plan index="11" id="2026-04-27-ocr-protocol-ollama-9c">` entry (was `"open"`).
  2. On the `<reference>` element: update `modified-at` to the current ISO 8601 timestamp with timezone offset:

```bash
date '+%Y-%m-%dT%H:%M:%S%:z'
```

The post-edit 9c entry should read approximately:

```xml
    <plan index="11"
          id="2026-04-27-ocr-protocol-ollama-9c"
          status="closed"
          expendable="false"
          plan-md="docs/superpowers/plans/2026-04-27-ocr-protocol-ollama-9c.md"
          spec-md="docs/superpowers/specs/2026-04-27-ocr-protocol-ollama-design.md"
          synopsis="OCR diagnostics integration (spec §6 cycles 7-9): synthesize_extraction_diagnostics, diagnose() extraction namespace, verify lifecycle, override interaction, new extraction.* codes. Lands diagnostics-engine spec amendment §12. Depends on 9a." />
```

### Step 2: Validate against the schema

- [ ] Run:

```bash
pixi run python -c "import xml.etree.ElementTree as ET; ET.parse('.claude/context/plans.xml')"
```

Expected: no output (parses cleanly).

### Step 3: Commit the close

- [ ] Stage and commit:

```bash
git add .claude/context/plans.xml
git commit -m "chore(context/plans): close 9c plan (2026-04-27-ocr-protocol-ollama-9c)"
```

### Step 4: Final sanity check

- [ ] Run: `pixi run check`
Expected: green.

- [ ] Run: `git log --oneline -10`
Expected: most recent commits trace `Red (9c-1) → Green (9c-1) → Red (9c-2) → Green (9c-2) → test (9c-3) → docs (9c-4) → plans-close (9c-5)`. Seven commits from this plan.

</task>

---

## Self-Review Checklist (run before handoff)

**Spec coverage:**

- §3.1 + §3.2 (reference material) → predecessor verification reads 9a's surface and the diagnostics-engine surface.
- §5.8 (synthesis sketch) → cycle 9c-1 lands `synthesize_extraction_diagnostics` per the docstring contract.
- §5.9 (extraction namespace in eval_context) → cycle 9c-2 lands the `extraction` parameter on `build_eval_context` and the type-resolver entry in `_build_rule_context`.
- §5.10 (verify lifecycle) → cycle 9c-2's lifecycle test (emit → verify → no re-emit) is the end-to-end pin.
- §6.7 (synthesis + stale-path filter + low-confidence branch + multi-field order + lifecycle) → cycle 9c-1 covers the seven function-level tests; cycle 9c-2 covers the lifecycle test (relocated per Q1).
- §6.8 (diagnose integration) → cycle 9c-2 covers the four plumbing tests (regression-pin, merge-order, namespace inclusion/omission, YAML guard behavior).
- §6.9 (override interaction) → task 9c-3 covers both regression tests (force_generation accepts extraction-source; verified field never reaches override).
- §7.7 (new diagnostic codes) → cycle 9c-1 emits all three codes from `synthesis.py` with the prescribed levels and `context=both`. The `extraction.placeholder_unfilled` rule (existing builtin from `2026-04-23-diagnostics-engine-rules`) is unchanged; coexistence pinned by the spec, no new test required since the existing starter-rule test exercises it.
- §10 (public API surface) → cycle 9c-1 adds `synthesize_extraction_diagnostics` to `__all__`; cycle 9c-2 updates `diagnose()` signature.
- §11 (constraint compliance) → all cycles uphold: TrustData stays validation-uniform (synthesis reads, never writes); diagnostics computed never stored (synthesis returns fresh list); force_generation no-user-parameter contract unaffected (no change to its signature).
- §12 (atomic spec amendment) → task 9c-4 lands the diagnostics-engine spec amendment in this same PR.
- §13 (open questions) → none addressed by this plan; they are explicitly carried as open.
- §14 (plan-review record) → noted; the plan-md treats the spec as final pending the existing review record.

**Sections explicitly NOT modified by 9c** (out-of-9c-scope, owned by 9a/9b or carried as deferred): §5.2, §5.3, §5.4, §5.7 (9a); §5.6, §6.4-6.6, §6.10, §7.1-7.6, §8 (9b).

**No gaps.**

**Placeholder scan:** No "TBD", "implement later", "similar to Task N", or unspecified error handling. Every code block, command, expected output, and edit is complete and self-contained. Two conditional escapes are documented:

1. Cycle 9c-2 Step 3 note about `firm_config_factory(custom_rules_dir=...)` — if the existing factory does not accept the kwarg, the plan instructs the executor to either parameterize the fixture or construct `FirmConfig` directly. This is a documented escape, not a placeholder, with explicit fallback paths.
2. Task 9c-3 Step 1 note about `tmp_audit_dir` and `firm_config_factory(audit_log_dir=...)` fixture availability — the plan instructs the executor to mirror the fixture composition used by `test_happy_path_writes_record` at line 31 of the same file.

**Type consistency:**

- `synthesize_extraction_diagnostics(trust: TrustData, extraction: ExtractionTrace | None) -> list[Diagnostic]` introduced in 9c-1; consumed by 9c-2 (`engine.py` import); exported via 9c-1's `__all__` update.
- `LOW_CONFIDENCE_THRESHOLD: Final[float]` introduced in 9c-1; consumed by the cycle 9c-1 test that pins the threshold value.
- `INCOMPLETE` sentinel imported from `trust_generator.v3.extraction.trace` in `synthesis.py` (NOT exported via `__all__`, per established discipline); consumed by the no-normalized-value branch.
- `build_eval_context` gains `*, extraction: ExtractionTrace | None = None` in 9c-2; consumed by `engine.py`'s updated call.
- `diagnose` gains `*, extraction: ExtractionTrace | None = None` in 9c-2; consumed by 9c-2 and 9c-3 tests.
- `_build_rule_context` gains `"extraction": rule_engine.DataType.UNDEFINED` in the type-resolver dict in 9c-2; consumed implicitly by the YAML-rule tests in 9c-2.
- `Diagnostic`, `DiagnosticLevel`, `DiagnosticSource.EXTRACTION`, `DiagnosticContext.BOTH` consumed from `schema.py` (no shape changes; verified in P4).
- `ExtractionTrace`, `FieldExtraction`, `INCOMPLETE` consumed from `trust_generator.v3.extraction.trace` (9a surface, no shape changes).
- `force_generation(trust, config, diagnostics, *, reason)` signature unchanged; 9c-3 tests pin behavior with new diagnostic source.

**Cross-plan handoff:**

- 9c does NOT depend on 9b (the OCR backend); the synthesis function works against any `ExtractionTrace`, not specifically one produced by `OllamaBackend`. Predecessor verification P1 checks 9a only.
- The next consumer of 9c's surface is the GUI/CLI session (out of scope for v3.0 plans inventory), which will pair an `OllamaBackend.extract(path)` call with a `diagnose(trust, config, extraction=trace)` call to surface paralegal-actionable extraction concerns.
- Trace persistence (chore #15 — in-flight, owned by consumer-layer persistence session) consumes the `INCOMPLETE` sentinel discipline. 9c does not write, modify, or expand the persistence story; it only reads `extraction.fields` and `field.normalized_value` via identity comparison.

**Out-of-scope items deliberately deferred:**

- ConfidenceProtocol (Session 4.3c) — `confidence_self_report` slot reserved on `FieldExtraction`; populated as `None` by `OllamaBackend` (per spec §5.3 docstring); the `extraction.low_confidence_field` branch is structurally live in cycle 9c-1 but unreachable from production traces until 4.3c lands.
- Verify lifecycle UI surfaces — GUI concern; v3.0 ships the data-model contract and the Diagnostics integration only.
- Trace persistence (round-trip serialization including `INCOMPLETE`) — chore #15, owned by the consumer-layer persistence session.
- Schema-complexity-ceiling benchmark — chore #14, gated by 9b-1; unrelated to 9c.
- `firm_config_factory` extension to accept `custom_rules_dir` and `audit_log_dir` — if the factory doesn't already support these, cycle 9c-2 Step 3 and task 9c-3 Step 1 describe the fallback (construct FirmConfig directly). Promoting these to first-class factory kwargs is a future ergonomic improvement, not a 9c blocker.
- Threshold promotion to firm-config (`LOW_CONFIDENCE_THRESHOLD`) — non-breaking change at the point a backend wires real confidence reports; out of scope for v3.0 per Q4.
- Full integration test exercising `OllamaBackend.extract` followed by `diagnose(extraction=...)` — would require a live Ollama server (per 9b's `pytest.mark.integration` discipline). The cycle 9c-2 lifecycle test uses a hand-constructed `ExtractionTrace` so it runs in CI; the live OllamaBackend → diagnose pipeline is an opportunistic future smoke test, not a 9c deliverable.
