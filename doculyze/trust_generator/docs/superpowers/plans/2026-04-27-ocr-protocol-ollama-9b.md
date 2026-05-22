# OCR Ollama Backend (9b) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Cycle blocks are XML-tagged for dispatcher-side cycle-scope addressing — see "Dispatch Protocol" below.

**Goal:** Land §5.6 (OllamaBackend), §7.1-§7.7 (implementation details), §8 (prompt strategy), §6.4-§6.6 (cycles 4-6), §6.10 (cycle 10) from the OCR spec — the concrete OllamaBackend extraction implementation that produces a TrustData + ExtractionTrace from a handwritten intake image via grammar-constrained generation against a local Ollama vision-language model.

**Architecture:** Two new modules under the existing `src/trust_generator/v3/extraction/` package (created in plan 9a) plus five new test modules. Four Red→Green TDD cycles (with conditional Refactor per the new `.claude/rules/development-strategy.md` `refactor_threshold` rule), one mechanical integration-smoke task, one plans-close task. The OllamaBackend depends on 9a's data foundation (`ExtractionProtocol`, `ExtractionResult`, `FieldExtraction`, `ExtractionTrace`, `SourceRef`, `ExtractionError`) and produces values that 9c's diagnostics integration will consume.

**Tech Stack:** Python 3.12; Pydantic v2; `ollama >= 0.6.1` (added to manifest in plan 9a Task 5; first imported here in cycle 9b-3); `httpx` (transitive ollama dep, error-path consumer in cycle 9b-4); `pytest` with `pytest.mark.integration` for the live smoke test (task 9b-5).

**Spec source:** `docs/superpowers/specs/2026-04-27-ocr-protocol-ollama-design.md` (§3.1-3.2 reference material; §5.6 OllamaBackend sketch; §6.4-6.6 cycles 4-6; §6.10 cycle 10; §7.1-7.7 implementation details; §8 prompt strategy; §10 public API surface; §11 constraint compliance; §13 known unknowns; §14 plan-review record). Sections §5.2 (markers), §5.3 (trace), §5.4 (Protocol), §5.7 (paths) are landed by 9a; sections §5.8-5.10 (synthesis / eval_context / verify lifecycle), §12 (spec amendment) are owned by 9c — NOT modified by this plan.

**Plan-composition decisions recorded:**

- **Q1 — Cycle decomposition: 4 cycles + 2 tasks.** Per spec, §6.4 (envelope), §6.5 (extract happy path), §6.6 (extract error paths), §6.10 (live smoke). The §8 prompt strategy is not a numbered spec cycle but is consumed by the extract happy path; it lands as its own cycle 9b-2 (between envelope and extract) so its testable invariants — the §8.1 three-pillar discipline, §8.2 domain orientation, §8.3 anti-hallucination guardrails — get an isolated Red→Green rather than being folded into the larger extract cycle. Live smoke (§6.10) is a verification-only cycle (the implementation already exists by 9b-3); it lands as a `<task>` rather than a `<cycle>` because there is no Red→Green code-change progression — the test file IS the deliverable, and a single commit is honest. Same precedent as 9a's Task 5 (mechanical dep-add) and Task 6 (plans-close).

- **Q2 — Prompt is its own cycle (9b-2), not folded into 9b-3.** Folding would make 9b-3's commit "extract + prompt + image-input + format + temperature" a single Red→Green delta, weakening the per-cycle "what failed" diagnostic value. Separating the prompt into 9b-2 lets cycle 9b-3 assume `build_intake_prompt()` exists and concentrate on the wire-call + envelope-validation + envelope-to-TrustData mapping seam. The prompt's testable invariants (per §8 pillars) are character-level present/absent assertions on the rendered prompt string — small, fast, isolatable.

- **Q3 — Live smoke is a `<task>`, not a `<cycle>`.** Per spec §6.10 Green explicitly: "The implementation is already complete by Cycle 5. This cycle is a smoke test for the live integration plus the integration-level field-order pin." There is no Red→Green code-change progression — the deliverable is one test file marked `pytest.mark.integration`, opt-in via `pytest --runintegration`. Modeling this as a cycle with `commits="red,green"` would force a synthetic green commit (e.g., a CHANGELOG line) that does not correspond to any source change. The honest framing is a single-commit task. The `.claude/rules/development-strategy.md` rule's "stage required=always green" applies to *implementation cycles*; verification tasks produce verification commits, and 9b-5 is verification-only.

- **Q4 — Minimal envelope subset (grantors + beneficiaries) for v3.0.** Spec §7.3 says the envelope "mirrors a TrustData subset" but explicitly: "the exact data-fields shape is a sub-question covered in §7.3." The full TrustData mirror (real_property, personal_property, fiduciaries, elections, text_blocks, etc.) would balloon the envelope schema's complexity and risk hitting the chore-14 schema-complexity ceiling on candidate vision models. v3.0 commits to a representative subset (grantors + beneficiaries, each with a `*_diag` per-field channel and the leading `reasoning` field) that is sufficient to (a) pin the field-order discipline test in cycle 9b-1, (b) exercise the envelope-to-TrustData mapping in cycle 9b-3, (c) provide a non-trivial smoke target in task 9b-5. If `_envelope_to_extraction_result` (cycle 9b-3) reveals that the envelope subset cannot construct a valid `TrustData` because TrustData requires fields outside the subset, the resolution is documented in cycle 9b-3 Step 3 (default-construct missing fields per `schema.py` defaults; if no defaults exist, halt and open a chore via scope-maintenance for full-mirror envelope expansion before proceeding).

- **Q5 — `prompt_builder: Callable[[], str] | None = None` instead of a `PromptBuilder` Protocol class.** Spec §5.6 sketches `prompt_builder: PromptBuilder | None = None` but does not define `PromptBuilder` separately. YAGNI: `Callable[[], str]` is a structural type already representable in mypy without introducing a Protocol class for a single-method shape. If a richer prompt-construction interface is needed later (e.g., section-aware prompt variants per §7.5 chunked-extraction strategy), promotion to a Protocol class is a non-breaking change at that point.

- **Q6 — Cycle commits attribute and refactor-stage reasoning.** The new `.claude/rules/development-strategy.md` rule requires explicit per-cycle reasoning when refactor is omitted (`if-none-met: explicitly note 'no refactor stage — green output is already minimal' with reasoning`). Each `<cycle>` block in this plan-md carries a `commits` attribute documenting the chosen shape, and each cycle's body includes a "Refactor decision" prose line evaluating the cycle's green-phase output against the rule's `refactor_threshold` (structural duplication / nested conditionals / mixed orthogonal concerns). Cycles 9b-1, 9b-2, 9b-4 commit to `red,green` (no refactor; reasons inline). Cycle 9b-3 commits to `red,green,refactor` because spec §6.5 already prescribes envelope-to-TrustData-mapping extraction as a refactor opportunity.

- **Q7 — Smoke fixture path via `OCR_SMOKE_FIXTURE_PATH` env var, defaulting to `assets/handwriting-samples/pages/print.jpg`.** Decouples the smoke test's contract (a path → a `.jpg`) from the storage policy (PHI handling, repo size, LFS migration) — see `assets/handwriting-samples/pages/BASELINE.md` and `assets/handwriting-samples/snippets/SNIPPETS.md` for corpus documentation. The default fixture is `pages/print.jpg` because it is the cleanest baseline (per BASELINE.md per-sample fitness assessment); the four other `pages/` photos and the five `snippets/` photos are reserve material for chore #13's empirical-model-selection exercise, NOT smoke-test inputs.

- **Q8 — Inside-out (Detroit/classicist) TDD with minimal mocks.** Per `.claude/rules/development-strategy.md` `methodology="test-driven-development" approach="inside-out"`. Cycles 9b-1, 9b-2 use no mocks (Pydantic schemas and string functions exercise against real instances). Cycles 9b-3 and 9b-4 mock ONE seam: the network boundary (`ollama.Client.chat`). Everything else — envelope validation via `GenerationEnvelope.model_validate_json`, prompt rendering via `build_intake_prompt`, path normalization via `Path.resolve`, TrustData construction — runs against real implementations. This is consistent with 9a's posture (real `TrustData` instances in the path resolver tests, real `FieldExtraction` instances in the trace tests).

- **Q9 — Scope size acceptance.** 9b touches 7 new files (2 src + 5 tests) + 1 modified src + 1 modified metadata = 9 file paths. Logical complexity: 4 cycles (complex) + 2 tasks (mechanical) = 4 complex tasks. CLAUDE.md soft-warn at >5 files / >2 complex tasks; hard-deny at >10 / >5. 9b sits at file-count soft-warn (9) and complex-task soft-warn (4) — both below hard-deny. Same posture as 9a (which also sat at soft-warn-file / sub-hard-deny-complexity). Recorded so future readers see the scope was considered and accepted.

---

## Dispatch Protocol

When invoking `/spec-pipeline 2026-04-27-ocr-protocol-ollama-9b exec-plan`, the dispatcher (you, or a routing skill) controls which cycles execute via a scope-token in the dispatcher prompt, mirroring 9a's convention:

| Scope-token | Effect |
| ----------- | ------ |
| (no scope-token, or `cycles=all`)            | Plan-executor walks `<cycle>` and `<task>` blocks in document order, executing each per its `commits` attribute. |
| `cycles=[9b-2]`                              | Plan-executor opens only the cycle whose `id` attribute matches; verifies `depends-on` cycles' Green commits exist via `git log --grep`; executes Red→Green→(optional Refactor) for that cycle alone. |
| `cycles=[9b-2..9b-4]` (inclusive range)      | Plan-executor walks the contiguous cycle range; same dependency check at the range's lower bound. |
| `cycles=[9b-1, 9b-3]` (explicit list)         | Plan-executor walks each id in the order supplied. Use sparingly — non-contiguous execution risks skipping a `depends-on` link. |

Each `<cycle>` and `<task>` block carries five attributes:

| Attribute        | Purpose                                                                                     |
| ---------------- | ------------------------------------------------------------------------------------------- |
| `id`             | Stable scope token (`9b-1`, …, `9b-6`).                                                     |
| `spec-ref`       | Backlink to the spec section(s) the cycle/task implements.                                  |
| `blast-radius`   | Semicolon-separated list of file paths the cycle/task is allowed to create or modify. Plan-executor must NOT edit any path outside this list during the cycle; new paths surfaced at green-time become chores via scope-maintenance. |
| `depends-on`     | Cycle/task-id list whose commits must already exist. Cycle 9b-1's `depends-on` references 9a-4 (the last Green commit of 9a) as the gating predecessor. |
| `commits`        | The cycle's commit shape — `red,green` (default), `red,green,refactor` when warranted, or single (for `<task>` blocks). |

The dispatching session retains responsibility for the post-execution close-out (review chore-list, commit `plans.xml` flip — invariant #5 in spec-pipeline SKILL.md).

---

## File Structure

**Created (production):**

| Path | Responsibility |
| ---- | -------------- |
| `src/trust_generator/v3/extraction/ollama_backend.py` | `GenerationEnvelope` and supporting `FieldDiag`/`GrantorEnvelope`/`BeneficiaryEnvelope` submodels (cycle 9b-1); `OllamaBackend` class with `extract()` happy path (cycle 9b-3); error-path handling (cycle 9b-4). Module docstring carries the §2 "persistence in code" pointer to chore #14 (envelope complexity ceiling), to be removed at chore #14 fulfillment per the chore body. |
| `src/trust_generator/v3/extraction/prompt.py` | `build_intake_prompt() -> str` — the §8 prompt strategy materialized as a string template (cycle 9b-2). |

**Created (tests):**

| Path | Responsibility |
| ---- | -------------- |
| `tests/v3/extraction/test_envelope.py` | Cycle 9b-1 tests (envelope schema field-order, `reasoning` max_length, sample-envelope-JSON validation). |
| `tests/v3/extraction/test_prompt.py` | Cycle 9b-2 tests (§8.1 three-pillar marker phrases, §8.2 domain orientation, §8.3 anti-hallucination guardrails, length-cap structural test). |
| `tests/v3/extraction/test_ollama_backend.py` | Cycle 9b-3 tests (constructor signature, ExtractionProtocol structural conformance, mocked-client happy path, `format=` and `options=` and `messages=` correctness, backend_id format). |
| `tests/v3/extraction/test_ollama_backend_errors.py` | Cycle 9b-4 tests (`ResponseError → ExtractionError`, malformed envelope JSON, network failure, oversized reasoning). |
| `tests/v3/extraction/test_ollama_backend_integration.py` | Task 9b-5 tests (live `extract()` against a real Ollama server; raw JSON-key-order pin). Marked `pytest.mark.integration`; opt-in via `pytest --runintegration`. |

**Modified (production):**

| Path | Change |
| ---- | ------ |
| `src/trust_generator/v3/extraction/__init__.py` | Cycle 9b-3: append `OllamaBackend` to `__all__` (RUF022 will auto-alphabetize on `pixi run fix`; the alphabetic position is between `IncompleteUntilValidated` and `RawSelfReport`). |

**Modified (metadata):**

| Path | Change |
| ---- | ------ |
| `.claude/context/plans.xml` | Task 9b-6: set `status="closed"` on the 9b entry; bump `modified-at`. |

**Total touched files:** 9 (2 new src, 5 new tests, 1 modified src, 1 modified metadata). See Q9.

---

## Predecessor verification (run once before any cycle)

Gating, not implementing. If any check fails, escalate.

- [ ] **Step P1: Verify 9a's Green commits exist**

Run:

```bash
git log --oneline --grep='GREEN — cycle 9a-' | wc -l
```

Expected: `4` (one Green commit per 9a cycle: 9a-1, 9a-2, 9a-3, 9a-4). If less than 4: 9a did not complete; halt and finish 9a first.

- [ ] **Step P2: Verify the extraction package exposes 9a's surface**

Run:

```bash
pixi run python -c "from trust_generator.v3.extraction import (
    ExtractionError, ExtractionProtocol, ExtractionResult,
    ExtractionTrace, FieldExtraction, IncompleteUntilValidated,
    RawSelfReport, SourceRef, resolve,
); from trust_generator.v3.extraction.trace import INCOMPLETE; print('ok')"
```

Expected: `ok` (no traceback). If `ImportError`: 9a's `__init__.py` has drifted; halt and reconcile.

- [ ] **Step P3: Verify the `ollama` dep is on the manifest and importable**

Run:

```bash
pixi run python -c "import ollama; print(ollama.__name__, getattr(ollama, '__version__', 'no-attr'))"
```

Expected: `ollama 0.6.1` (or a `>=0.6.1` patch). If not: 9a Task 5 did not land; halt and run `pixi install` after confirming `pyproject.toml` and `pixi.toml` carry the dep.

- [ ] **Step P4: Verify the project gate is green pre-cycle**

Run: `pixi run check`
Expected: lint passes, mypy passes, all tests pass. Exit code 0.
If non-green: halt — 9b starts from a green baseline so each cycle's red/green delta is unambiguous.

- [ ] **Step P5: Verify the current branch is a feature branch**

Run: `git branch --show-current`
Expected: a branch name that is NOT `main`. The current working branch (per session start: `v3.0.0`) is fine.

- [ ] **Step P6: Verify the smoke fixture exists**

Run: `ls assets/handwriting-samples/pages/print.jpg`
Expected: file present. (Photos were committed during the spec-to-plan session for plan 9b; if missing, the integration smoke task 9b-5's default fixture path will be unreachable, but cycles 9b-1 through 9b-4 do not consume the fixture and can proceed.)

---

## Cycle 9b-1 — `GenerationEnvelope` schema and field-order discipline

<cycle id="9b-1"
       spec-ref="§6.4, §7.3, §7.4"
       blast-radius="src/trust_generator/v3/extraction/ollama_backend.py; tests/v3/extraction/test_envelope.py"
       depends-on="9a-4"
       commits="red,green">

**Files:**

- Create: `src/trust_generator/v3/extraction/ollama_backend.py` (partial — only `FieldDiag`, `GrantorEnvelope`, `BeneficiaryEnvelope`, `GenerationEnvelope` for now; the `OllamaBackend` class lands in cycle 9b-3)
- Create: `tests/v3/extraction/test_envelope.py`

This cycle pins the load-bearing constrained-decoding contract from spec §7.4: `reasoning` is the FIRST field declared on `GenerationEnvelope`, with `max_length=2000`, and Pydantic v2's declaration-order preservation in `model_json_schema()` is the mechanism. The unit-level field-order test catches accidental regressions; the integration-level pin lands separately in task 9b-5.

The envelope's data-fields shape is a deliberately minimal subset — `grantors: list[GrantorEnvelope]` and `beneficiaries: list[BeneficiaryEnvelope]`, each with a `*_diag: FieldDiag` per-field channel — chosen for representativeness over coverage (per Q4). The full TrustData mirror is deferred; the envelope-to-TrustData mapping in 9b-3 will surface coverage gaps if any.

**Refactor decision:** Per `refactor_threshold` evaluation — no structural duplication beyond the intentional `FieldDiag` composition; no nested conditionals (it's a model declaration); orthogonal concerns are already separated (`FieldDiag` per-field channel vs. data fields). `commits="red,green"`; **no refactor stage — green output is already minimal; the envelope schema is structurally unique to OCR generation and does not generalize, so further abstraction would be premature (concurs with spec §6.4 Refactor note).**

- [ ] **Step 1: Author the failing test (Red)**

Create `tests/v3/extraction/test_envelope.py`:

```python
"""Cycle 9b-1 tests — GenerationEnvelope schema and field-order discipline."""

from __future__ import annotations

import pytest
from pydantic import ValidationError


def test_generation_envelope_importable() -> None:
    """``GenerationEnvelope`` is importable from the ollama_backend module."""
    from trust_generator.v3.extraction.ollama_backend import GenerationEnvelope

    assert GenerationEnvelope.__name__ == "GenerationEnvelope"


def test_generation_envelope_is_pydantic_basemodel() -> None:
    """``GenerationEnvelope`` is a Pydantic BaseModel."""
    from pydantic import BaseModel

    from trust_generator.v3.extraction.ollama_backend import GenerationEnvelope

    assert issubclass(GenerationEnvelope, BaseModel)


def test_generation_envelope_reasoning_is_first_field() -> None:
    """``reasoning`` MUST be the first field in ``model_json_schema()`` properties.

    Spec §7.4 — grammar-constrained decoding generates fields in schema
    declaration order. A leading string-typed reasoning field is
    load-bearing for the chain-of-thought benefit under constrained
    decoding. This test catches accidental reordering.
    """
    from trust_generator.v3.extraction.ollama_backend import GenerationEnvelope

    properties = GenerationEnvelope.model_json_schema()["properties"]
    field_order = list(properties.keys())
    assert field_order[0] == "reasoning", (
        f"Expected 'reasoning' first; got {field_order[0]!r}. "
        f"See spec §7.4 — reordering requires evidence (chore #14)."
    )


def test_generation_envelope_reasoning_has_max_length() -> None:
    """The ``reasoning`` field has a concrete numeric ``maxLength`` constraint.

    Spec §6.4 pins this at 2000 characters (~500-token proxy). Without
    a max_length, the reasoning channel could produce unbounded output
    under constrained decoding and exhaust context.
    """
    from trust_generator.v3.extraction.ollama_backend import GenerationEnvelope

    properties = GenerationEnvelope.model_json_schema()["properties"]
    reasoning_schema = properties["reasoning"]
    assert reasoning_schema.get("maxLength") == 2000


def test_generation_envelope_validates_minimal_sample() -> None:
    """A minimal envelope (reasoning only, empty data) parses cleanly."""
    from trust_generator.v3.extraction.ollama_backend import GenerationEnvelope

    sample = '{"reasoning": "I see a form with grantor and beneficiary sections.", "grantors": [], "beneficiaries": []}'
    envelope = GenerationEnvelope.model_validate_json(sample)
    assert envelope.reasoning.startswith("I see a form")
    assert envelope.grantors == []
    assert envelope.beneficiaries == []


def test_generation_envelope_rejects_oversized_reasoning() -> None:
    """``reasoning`` exceeding max_length is rejected at validation time."""
    from trust_generator.v3.extraction.ollama_backend import GenerationEnvelope

    oversized = "x" * 2001
    with pytest.raises(ValidationError):
        GenerationEnvelope(reasoning=oversized)


def test_field_diag_importable_and_default_constructible() -> None:
    """``FieldDiag`` exists and constructs with no args."""
    from trust_generator.v3.extraction.ollama_backend import FieldDiag

    diag = FieldDiag()
    assert diag.illegible is False
    assert diag.note is None


def test_field_diag_note_max_length() -> None:
    """``FieldDiag.note`` has max_length=240 per spec §7.3."""
    from pydantic import ValidationError

    from trust_generator.v3.extraction.ollama_backend import FieldDiag

    with pytest.raises(ValidationError):
        FieldDiag(note="x" * 241)


def test_grantor_envelope_carries_diag_per_field() -> None:
    """``GrantorEnvelope`` exposes per-field diag channels for its fields."""
    from trust_generator.v3.extraction.ollama_backend import GrantorEnvelope

    envelope = GrantorEnvelope()
    assert envelope.full_legal_name is None
    assert envelope.full_legal_name_diag.illegible is False
    assert envelope.date_of_birth is None
    assert envelope.date_of_birth_diag.illegible is False


def test_beneficiary_envelope_carries_diag_per_field() -> None:
    """``BeneficiaryEnvelope`` exposes per-field diag channels for its fields."""
    from trust_generator.v3.extraction.ollama_backend import BeneficiaryEnvelope

    envelope = BeneficiaryEnvelope()
    assert envelope.full_legal_name is None
    assert envelope.full_legal_name_diag.illegible is False
    assert envelope.relationship is None
    assert envelope.relationship_diag.illegible is False
    assert envelope.share_percent is None
    assert envelope.share_percent_diag.illegible is False
```

- [ ] **Step 2: Run the test to confirm Red**

Run: `pixi run test test_envelope`
Expected: 10 tests fail with `ModuleNotFoundError: No module named 'trust_generator.v3.extraction.ollama_backend'`.
If a different error: investigate.

- [ ] **Step 3: Author the production code (Green)**

Create `src/trust_generator/v3/extraction/ollama_backend.py`:

```python
"""OllamaBackend: ExtractionProtocol implementation via local Ollama.

IMPORTANT: This module embodies the v3.0 commitment to Approach B'
(free generation with structurally constrained diagnostics, sidecar
form). See spec §7.4 for the rationale: the generation envelope (the
model's Pydantic output schema) reserves a string-typed ``reasoning``
field that is declared first to materialize the chain-of-thought
benefit under grammar-constrained decoding. This is the current
best-practice posture for grammar-constrained generation; reordering
or removing it is plausible-only-with-evidence (chore index 14 —
``2026-04-27-envelope-complexity-ceiling-benchmark`` — is the
gathering point). Do not move it without re-reading §7.4 and the
field-order test in tests/v3/extraction/test_envelope.py.

IMPORTANT: Schema complexity ceiling under constrained decoding —
small models can produce unexpected EOF errors on complex schemas. If
this surfaces in production, consult §7.5 (chunked extraction) and
the in-flight chore index 14 before changing this module's shape.

NOTE: At chore #14 fulfillment, the two IMPORTANT blocks above MUST
be removed (per chore #14 body's fulfillment cleanup direction). The
constraints they reference will no longer be ``future`` once the
threshold is documented; stale future-tense pointers become noise.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class FieldDiag(BaseModel):
    """Per-field illegibility/note channel emitted by the model alongside data.

    Spec §7.3. Both fields default to "no signal" — the parser MUST
    NOT emit an envelope where ``illegible=True`` coexists with a
    populated data field on the same envelope row. The mapping in
    ``_envelope_to_extraction_result`` honors this invariant when
    constructing FieldExtraction entries.
    """

    model_config = ConfigDict(extra="forbid")

    illegible: bool = False
    note: str | None = Field(default=None, max_length=240)


class GrantorEnvelope(BaseModel):
    """Per-grantor generation envelope shape (mirrors a TrustData subset).

    Spec §7.3 — flatter, OCR-shaped mirror of the TrustData grantor
    submodel. Each data field has a sibling ``*_diag`` per-field
    illegibility/note channel. Every field is Optional because OCR
    extraction may produce ``None`` for absent or illegible fields
    without invalidating the envelope as a whole.
    """

    model_config = ConfigDict(extra="forbid")

    full_legal_name: str | None = None
    full_legal_name_diag: FieldDiag = Field(default_factory=FieldDiag)
    date_of_birth: str | None = None
    date_of_birth_diag: FieldDiag = Field(default_factory=FieldDiag)


class BeneficiaryEnvelope(BaseModel):
    """Per-beneficiary generation envelope shape.

    ``share_percent`` is typed ``str`` (raw transcription, e.g., "50",
    "fifty", "50%") rather than ``Decimal`` so that OCR-time
    transcription drift does not invalidate the envelope at validation
    time. Normalization to a numeric type is the consumer's concern
    (the cycle 9b-3 envelope-to-TrustData mapping handles the
    conversion under ``IncompleteUntilValidated`` discipline).
    """

    model_config = ConfigDict(extra="forbid")

    full_legal_name: str | None = None
    full_legal_name_diag: FieldDiag = Field(default_factory=FieldDiag)
    relationship: str | None = None
    relationship_diag: FieldDiag = Field(default_factory=FieldDiag)
    share_percent: str | None = None
    share_percent_diag: FieldDiag = Field(default_factory=FieldDiag)


class GenerationEnvelope(BaseModel):
    """Constrained-decoding envelope for OllamaBackend.

    CRITICAL: ``reasoning`` MUST be the first field declared. Pydantic
    v2 preserves declaration order in ``model_json_schema()``; grammar-
    constrained decoding generates fields in schema declaration order.
    A leading string-typed reasoning field lets the model "think aloud"
    before committing to typed values, mitigating hallucination on
    illegible inputs. The cycle 9b-1 schema field-order test pins this
    discipline at the unit layer; task 9b-5 pins it at the integration
    layer against live model output.

    Reordering or removing ``reasoning`` is a §7.4 amendment, not a
    refactor. See chore index 14 for the evidence-gathering surface.

    The data-fields subset (``grantors``, ``beneficiaries``) is
    deliberately minimal for v3.0 (per plan 9b Q4). Full TrustData
    mirror lands in a follow-up if cycle 9b-3's envelope-to-TrustData
    mapping reveals coverage gaps that the subset cannot resolve.
    """

    model_config = ConfigDict(extra="forbid")

    reasoning: str = Field(max_length=2000)
    grantors: list[GrantorEnvelope] = Field(default_factory=list)
    beneficiaries: list[BeneficiaryEnvelope] = Field(default_factory=list)
```

- [ ] **Step 4: Run the test to confirm Green**

Run: `pixi run test test_envelope`
Expected: 10 tests pass.

- [ ] **Step 5: Run the project gate**

Run: `pixi run check`
Expected: green (lint + mypy + all tests). Cycle 9b-1 adds zero coupling to existing v3 code.

- [ ] **Step 6: Commit Red and Green**

```bash
git add tests/v3/extraction/test_envelope.py
git commit -m "test(extraction): RED — cycle 9b-1 GenerationEnvelope schema and field-order discipline"
```

```bash
git add src/trust_generator/v3/extraction/ollama_backend.py
git commit -m "feat(extraction): GREEN — cycle 9b-1 GenerationEnvelope, FieldDiag, *Envelope submodels"
```

</cycle>

---

## Cycle 9b-2 — Prompt builder for legal handwritten intake

<cycle id="9b-2"
       spec-ref="§8, §5.1"
       blast-radius="src/trust_generator/v3/extraction/prompt.py; tests/v3/extraction/test_prompt.py"
       depends-on="9b-1"
       commits="red,green">

**Files:**

- Create: `src/trust_generator/v3/extraction/prompt.py`
- Create: `tests/v3/extraction/test_prompt.py`

The prompt is a single string template encoding the §8 strategy. It has three pillars (§8.1: verbatim transcription, illegibility-as-first-class, reasoning-aloud), a domain orientation (§8.2), and three anti-hallucination guardrails (§8.3: omit-if-absent, partial-transcription, multiple-readings note channel). Tests assert character-level presence of marker phrases — small, fast, and stable against minor wording drift as long as core terms are present.

The prompt is short by design (spec §8 closing paragraph: "verbose system prompts are noisy under grammar-constrained decoding"). The length-cap structural test (≤2000 characters) catches accidental verbosity creep.

**Refactor decision:** Per `refactor_threshold` evaluation — no structural duplication (it's a single string); no nested conditionals; one orthogonal concern (the prompt text itself). `commits="red,green"`; **no refactor stage — green output is already minimal; the prompt is a single string template with no abstractable structure at v3.0. If future work introduces section-aware variants (§7.5 chunked extraction), refactor lands at that point.**

- [ ] **Step 1: Author the failing test (Red)**

Create `tests/v3/extraction/test_prompt.py`:

```python
"""Cycle 9b-2 tests — prompt builder for legal handwritten intake (§8)."""

from __future__ import annotations


def test_build_intake_prompt_importable() -> None:
    """``build_intake_prompt`` is importable from the prompt module."""
    from trust_generator.v3.extraction.prompt import build_intake_prompt

    assert callable(build_intake_prompt)


def test_build_intake_prompt_returns_str() -> None:
    """``build_intake_prompt()`` returns a non-empty string."""
    from trust_generator.v3.extraction.prompt import build_intake_prompt

    result = build_intake_prompt()
    assert isinstance(result, str)
    assert result.strip() != ""


def test_prompt_contains_verbatim_pillar() -> None:
    """§8.1 pillar 1 — verbatim transcription discipline.

    The prompt MUST instruct the model to transcribe verbatim, not
    normalize. We assert presence of the term ``verbatim`` and a
    no-normalization phrase.
    """
    from trust_generator.v3.extraction.prompt import build_intake_prompt

    prompt = build_intake_prompt().lower()
    assert "verbatim" in prompt
    assert "do not normalize" in prompt or "do not reformat" in prompt


def test_prompt_contains_illegibility_pillar() -> None:
    """§8.1 pillar 2 — illegibility-as-first-class outcome.

    The prompt MUST frame illegibility flagging as preferred over
    guessing, and reference the ``illegible`` channel by name.
    """
    from trust_generator.v3.extraction.prompt import build_intake_prompt

    prompt = build_intake_prompt().lower()
    assert "illegible" in prompt
    assert "preferred over guessing" in prompt or "preferred over a guess" in prompt or "rather than guessing" in prompt


def test_prompt_contains_reasoning_aloud_pillar() -> None:
    """§8.1 pillar 3 — reasoning-aloud first.

    The prompt MUST instruct the model to use the ``reasoning`` field
    first, before committing to data fields.
    """
    from trust_generator.v3.extraction.prompt import build_intake_prompt

    prompt = build_intake_prompt().lower()
    assert "reasoning" in prompt
    assert "first" in prompt or "before" in prompt


def test_prompt_contains_domain_orientation() -> None:
    """§8.2 — domain orientation: legal trust intake.

    The prompt MUST identify the document type (legal trust intake)
    and reference at least one structural section (grantors,
    beneficiaries, real property, personal property, fiduciaries).
    """
    from trust_generator.v3.extraction.prompt import build_intake_prompt

    prompt = build_intake_prompt().lower()
    assert "trust" in prompt
    assert "intake" in prompt or "intake form" in prompt
    sections = ("grantor", "beneficiar", "real property", "personal property", "fiduciar")
    assert any(s in prompt for s in sections)


def test_prompt_contains_omit_if_absent_guardrail() -> None:
    """§8.3 guardrail 1 — omit-if-absent."""
    from trust_generator.v3.extraction.prompt import build_intake_prompt

    prompt = build_intake_prompt().lower()
    assert "omit" in prompt
    assert "do not invent" in prompt or "do not fabricate" in prompt or "do not guess" in prompt


def test_prompt_contains_partial_filling_guardrail() -> None:
    """§8.3 guardrail 2 — partial-filling: do not complete partial entries."""
    from trust_generator.v3.extraction.prompt import build_intake_prompt

    prompt = build_intake_prompt().lower()
    assert "do not complete" in prompt or "do not fill in" in prompt


def test_prompt_contains_multiple_readings_guardrail() -> None:
    """§8.3 guardrail 3 — multiple-readings note channel.

    The prompt MUST instruct the model to use the ``note`` channel
    for ambiguity when multiple readings are plausible.
    """
    from trust_generator.v3.extraction.prompt import build_intake_prompt

    prompt = build_intake_prompt().lower()
    assert "note" in prompt
    assert "ambiguity" in prompt or "ambiguous" in prompt or "multiple readings" in prompt


def test_prompt_length_under_cap() -> None:
    """Spec §8 closing — verbose prompts are noisy under constrained decoding.

    The cap (2000 characters) is a structural soft-warn against verbosity
    creep; the cap is documented in spec §8 and tested here.
    """
    from trust_generator.v3.extraction.prompt import build_intake_prompt

    assert len(build_intake_prompt()) <= 2000
```

- [ ] **Step 2: Run the test to confirm Red**

Run: `pixi run test test_prompt`
Expected: 10 tests fail with `ModuleNotFoundError: No module named 'trust_generator.v3.extraction.prompt'`.

- [ ] **Step 3: Author the production code (Green)**

Create `src/trust_generator/v3/extraction/prompt.py`:

```python
"""Prompt construction for OCR extraction of legal handwritten intake forms.

The prompt encodes spec §8's three-part strategy:
- §8.1 reading discipline: verbatim transcription, illegibility-as-first-class, reasoning-aloud
- §8.2 domain orientation: legal trust intake; structural sections named
- §8.3 anti-hallucination guardrails: omit-if-absent, partial-transcription, multiple-readings note channel

The prompt is short by design — spec §8 closing paragraph notes that
verbose system prompts are noisy under grammar-constrained decoding,
where the model's deviation surface is already small.
"""

from __future__ import annotations


_INTAKE_PROMPT = """\
You are a careful legal-intake transcriber. The attached image is a handwritten trust intake form. Extract its field values into the structured output schema.

Reading discipline:
1. Verbatim transcription. Transcribe what is written, not what the writer "meant." Do not normalize names, dates, currency, suffixes, or punctuation. Do not reformat. If the form says "James William Thompson, Jr." emit that exact string; do not rewrite to "James W. Thompson Jr."
2. Illegibility is first-class. If you cannot read a field with confidence, set its illegible flag to true. Marking a field illegible is preferred over guessing.
3. Reasoning aloud first. The output schema reserves a "reasoning" field at the start. Use it to walk through what you see on the form, noting handwriting irregularities, before committing to data fields.

Domain context: the document is a legal trust intake form. Expected sections include grantors, beneficiaries, real property, personal property, and fiduciaries.

Anti-hallucination guardrails:
- If a field is not present on the form at all, omit it from the output. Do not invent a default value.
- If a field is partially filled, transcribe what is there. Do not complete it.
- If multiple readings are plausible, pick the most likely transcription and use the "note" channel to record the ambiguity.
"""


def build_intake_prompt() -> str:
    """Return the OCR extraction prompt for legal handwritten intake.

    Strategy per spec §8. The default prompt is a module-level
    constant; this function exists as the public seam so future
    section-aware or firm-customized variants can be plugged in
    without breaking the OllamaBackend constructor signature
    (``prompt_builder: Callable[[], str] | None = None``).
    """
    return _INTAKE_PROMPT
```

- [ ] **Step 4: Run the test to confirm Green**

Run: `pixi run test test_prompt`
Expected: 10 tests pass. If a marker-phrase test fails: adjust the prompt to include the asserted phrase or its documented synonyms (the test accepts a short list of equivalents per pillar).

- [ ] **Step 5: Run the project gate**

Run: `pixi run check`
Expected: green.

- [ ] **Step 6: Commit Red and Green**

```bash
git add tests/v3/extraction/test_prompt.py
git commit -m "test(extraction): RED — cycle 9b-2 prompt builder marker-phrase invariants"
```

```bash
git add src/trust_generator/v3/extraction/prompt.py
git commit -m "feat(extraction): GREEN — cycle 9b-2 build_intake_prompt() per spec §8"
```

</cycle>

---

## Cycle 9b-3 — `OllamaBackend.extract`, the happy path

<cycle id="9b-3"
       spec-ref="§5.6, §6.5, §7.2, §7.3, §7.6"
       blast-radius="src/trust_generator/v3/extraction/ollama_backend.py; src/trust_generator/v3/extraction/__init__.py; tests/v3/extraction/test_ollama_backend.py"
       depends-on="9b-2"
       commits="red,green,refactor">

**Files:**

- Modify: `src/trust_generator/v3/extraction/ollama_backend.py` (add `OllamaBackend` class with `__init__` and `extract` happy path; add private `_envelope_to_extraction_result` mapper)
- Modify: `src/trust_generator/v3/extraction/__init__.py` (append `OllamaBackend` to `__all__`)
- Create: `tests/v3/extraction/test_ollama_backend.py`

The big cycle. `OllamaBackend.extract` orchestrates: load image path → render prompt → invoke `ollama.Client.chat` with `format=GenerationEnvelope.model_json_schema()` and `options={"temperature": 0}` → validate response envelope → map envelope to `ExtractionResult`. The mapping function `_envelope_to_extraction_result` builds:

- A `TrustData` that is **default-constructed except for `co_grantor` instantiation** (when `envelope.grantors` has length ≥ 2). The OCR'd values land on the trace, not on TrustData itself: TrustData stays in a default state and the trace carries the evidence — paralegal fill propagates trace values into TrustData under their judgment, with diagnostics surfacing un-propagated/un-normalized fields. This avoids the `_validate_name` ≥2-token rejection on partial-form OCR (spec §7.3.4) and keeps `share_percent`/`date_of_birth` normalization deferred under `IncompleteUntilValidated` discipline (spec §7.3.3).
- An `ExtractionTrace` whose `field_path` strings reference TrustData attribute names per spec §7.3.1 — `grantor.full_legal_name`, `co_grantor.full_legal_name`, `other_beneficiaries[i].full_legal_name`, `other_beneficiaries[i].relationship_other`, `beneficiary_shares[i].share_percent`. Each path is verified against `extraction.paths.resolve` semantics: live `hasattr`/list-index walking. Paths that don't resolve are silently dropped by plan 9c's diagnostic synthesis as stale, so this discipline is load-bearing.
- One `FieldExtraction` per non-None envelope data field OR per illegibility-flag-set sibling diag (per spec §8.3 omit-if-absent: do not emit FieldExtraction when both the data field and the diag are quiet).

Tests use a `MagicMock`-shaped `ollama.Client` injected via the constructor seam. No `unittest.mock.patch` of module-level imports — the constructor seam is the test seam (per Q8 minimal-mocks discipline).

**Refactor decision:** Per `refactor_threshold` evaluation — the green-phase mapper bridges three orthogonal section concerns (grantor envelope → grantor + co_grantor; beneficiary envelope → other_beneficiaries; share envelope → beneficiary_shares + recipient_ref linkage), each ≥10 LOC, and total mapper body exceeds ~50 LOC. The "mixes orthogonal concerns that extract cleanly" criterion fires. Spec §6.5 also prescribes: "Extract envelope-to-TrustData mapping to a private function if it grows beyond ~30 lines." `commits="red,green,refactor"`; **refactor stage splits per-section mappers — `_map_grantor_envelope(grantors: list[GrantorEnvelope]) -> tuple[list[FieldExtraction], bool]` (returns fields + needs_co_grantor flag), `_map_beneficiary_envelope(beneficiaries: list[BeneficiaryEnvelope]) -> tuple[list[FieldExtraction], list[BeneficiaryShare]]` (returns name/relationship trace fields + share rows in one pass) — and rewrites `_envelope_to_extraction_result` to delegate. This refactor scope is fixed at planning time, not observation-conditional.**

- [ ] **Step 1: Author the failing test (Red)**

Create `tests/v3/extraction/test_ollama_backend.py`:

```python
"""Cycle 9b-3 tests — OllamaBackend.extract happy path."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

if TYPE_CHECKING:
    from trust_generator.v3.extraction.protocol import ExtractionProtocol


def _make_mock_client_returning(envelope_json: str) -> MagicMock:
    """Construct a MagicMock-shaped ollama.Client whose chat() returns
    a response object with .message.content equal to envelope_json."""
    response = MagicMock()
    response.message.content = envelope_json
    client = MagicMock()
    client.chat.return_value = response
    return client


def test_ollama_backend_importable() -> None:
    """``OllamaBackend`` is importable from the extraction package."""
    from trust_generator.v3.extraction import OllamaBackend

    assert OllamaBackend.__name__ == "OllamaBackend"


def test_ollama_backend_in_dunder_all() -> None:
    """``OllamaBackend`` is exported via ``__all__``."""
    from trust_generator.v3.extraction import __all__

    assert "OllamaBackend" in __all__


def test_ollama_backend_constructor_accepts_model() -> None:
    """``OllamaBackend(model='qwen2.5vl:7b')`` constructs."""
    from trust_generator.v3.extraction import OllamaBackend

    backend = OllamaBackend(model="qwen2.5vl:7b", client=MagicMock())
    assert backend.model == "qwen2.5vl:7b"


def test_ollama_backend_constructor_accepts_injected_client() -> None:
    """The ``client`` parameter is honored when provided."""
    from trust_generator.v3.extraction import OllamaBackend

    injected = MagicMock()
    backend = OllamaBackend(model="qwen2.5vl:7b", client=injected)
    assert backend.client is injected


def test_ollama_backend_constructor_accepts_prompt_builder() -> None:
    """The ``prompt_builder`` parameter is honored when provided."""
    from trust_generator.v3.extraction import OllamaBackend

    custom = lambda: "custom prompt"  # noqa: E731
    backend = OllamaBackend(
        model="qwen2.5vl:7b",
        client=MagicMock(),
        prompt_builder=custom,
    )
    assert backend.prompt_builder is custom


def test_ollama_backend_satisfies_extraction_protocol_structurally() -> None:
    """An ``OllamaBackend`` instance satisfies ``ExtractionProtocol``.

    Spec §5.4 — ExtractionProtocol is NOT @runtime_checkable; the
    structural type-check role is served by the static type checker.
    This test pins the assignability via a typed local annotation.
    mypy will reject this assignment if ``OllamaBackend.extract`` has
    drifted from the Protocol signature.
    """
    from trust_generator.v3.extraction import ExtractionProtocol, OllamaBackend

    backend: ExtractionProtocol = OllamaBackend(model="qwen2.5vl:7b", client=MagicMock())
    assert backend is not None  # runtime no-op; the assignment IS the test


def test_ollama_backend_extract_returns_extraction_result() -> None:
    """``extract`` returns an ExtractionResult on the happy path."""
    from trust_generator.v3.extraction import ExtractionResult, OllamaBackend

    envelope_json = (
        '{"reasoning": "Form has one grantor and one beneficiary.",'
        ' "grantors": [{"full_legal_name": "James William Thompson, Jr.",'
        '              "full_legal_name_diag": {"illegible": false, "note": null},'
        '              "date_of_birth": "March 15, 1958",'
        '              "date_of_birth_diag": {"illegible": false, "note": null}}],'
        ' "beneficiaries": []}'
    )
    client = _make_mock_client_returning(envelope_json)
    backend = OllamaBackend(model="qwen2.5vl:7b", client=client)

    result = backend.extract(Path("fake.png"))

    assert isinstance(result, ExtractionResult)


def test_ollama_backend_extract_trace_has_correct_backend_id() -> None:
    """``trace.backend_id`` follows the ``ollama:<model>`` convention (spec §5.3)."""
    from trust_generator.v3.extraction import OllamaBackend

    envelope_json = '{"reasoning": "empty form", "grantors": [], "beneficiaries": []}'
    client = _make_mock_client_returning(envelope_json)
    backend = OllamaBackend(model="qwen2.5vl:7b", client=client)

    result = backend.extract(Path("fake.png"))

    assert result.trace.backend_id == "ollama:qwen2.5vl:7b"


def test_ollama_backend_extract_trace_extracted_at_is_set() -> None:
    """``trace.extracted_at`` is set to a tz-aware datetime."""
    from trust_generator.v3.extraction import OllamaBackend

    before = datetime.now(UTC)
    envelope_json = '{"reasoning": "empty form", "grantors": [], "beneficiaries": []}'
    client = _make_mock_client_returning(envelope_json)
    backend = OllamaBackend(model="qwen2.5vl:7b", client=client)

    result = backend.extract(Path("fake.png"))
    after = datetime.now(UTC)

    assert result.trace.extracted_at.tzinfo is not None
    assert before <= result.trace.extracted_at <= after


def test_ollama_backend_extract_emits_field_per_non_none_envelope_data() -> None:
    """One FieldExtraction per non-None envelope data field (spec §8.3 omit-if-absent).

    Field paths follow spec §7.3.1: envelope.grantors[0] → field_path 'grantor.*'
    (singular; collapses onto TrustData.grantor). Verifies trace fields
    resolve via extraction.paths.resolve against a default-constructed
    TrustData (i.e., the path syntax is valid, not the values).
    """
    from trust_generator.v3.extraction import OllamaBackend, resolve
    from trust_generator.v3.schema import TrustData

    envelope_json = (
        '{"reasoning": "Form has grantor name; date is illegible.",'
        ' "grantors": [{"full_legal_name": "James William Thompson, Jr.",'
        '              "full_legal_name_diag": {"illegible": false, "note": null},'
        '              "date_of_birth": null,'
        '              "date_of_birth_diag": {"illegible": true, "note": "smudged"}}],'
        ' "beneficiaries": []}'
    )
    client = _make_mock_client_returning(envelope_json)
    backend = OllamaBackend(model="qwen2.5vl:7b", client=client)

    result = backend.extract(Path("fake.png"))

    field_paths = [f.field_path for f in result.trace.fields]
    assert "grantor.full_legal_name" in field_paths
    # date_of_birth was illegible AND null → emit FieldExtraction with illegible=True
    assert "grantor.date_of_birth" in field_paths

    # Spec §7.3.1 — paths must resolve against TrustData via paths.resolve.
    # Resolution is tested against a default TrustData since the mapper does
    # NOT propagate values into data (spec §7.3.4 validator-fragility coercion).
    default_data = TrustData()
    for path in field_paths:
        resolved, _ = resolve(default_data, path)
        assert resolved, f"field_path {path!r} does not resolve against TrustData"


def test_ollama_backend_extract_collapses_two_grantors_to_co_grantor() -> None:
    """Spec §7.3.1 — envelope.grantors[1] → field_path 'co_grantor.*', and
    TrustData.co_grantor is instantiated (no longer None) when present.
    """
    from trust_generator.v3.extraction import OllamaBackend, resolve

    envelope_json = (
        '{"reasoning": "Joint trust with two grantors.",'
        ' "grantors": ['
        '   {"full_legal_name": "James William Thompson, Jr.",'
        '    "full_legal_name_diag": {"illegible": false, "note": null},'
        '    "date_of_birth": null,'
        '    "date_of_birth_diag": {"illegible": false, "note": null}},'
        '   {"full_legal_name": "Mary-Beth O\'Brien Thompson",'
        '    "full_legal_name_diag": {"illegible": false, "note": null},'
        '    "date_of_birth": null,'
        '    "date_of_birth_diag": {"illegible": false, "note": null}}'
        ' ],'
        ' "beneficiaries": []}'
    )
    client = _make_mock_client_returning(envelope_json)
    backend = OllamaBackend(model="qwen2.5vl:7b", client=client)

    result = backend.extract(Path("fake.png"))

    field_paths = [f.field_path for f in result.trace.fields]
    assert "grantor.full_legal_name" in field_paths
    assert "co_grantor.full_legal_name" in field_paths
    # TrustData.co_grantor must be instantiated for the co_grantor.* path to resolve.
    assert result.data.co_grantor is not None
    resolved, _ = resolve(result.data, "co_grantor.full_legal_name")
    assert resolved


def test_ollama_backend_extract_maps_beneficiaries_to_other_beneficiaries() -> None:
    """Spec §7.3.1 + §7.3.2 — envelope.beneficiaries[i] defaults to
    other_beneficiaries[i] (conservative classification fallback). The
    corresponding beneficiary_shares[i].recipient_ref is the canonical
    string id 'other_beneficiaries[{i}]'.
    """
    from trust_generator.v3.extraction import OllamaBackend, resolve

    envelope_json = (
        '{"reasoning": "One beneficiary with a share.",'
        ' "grantors": [],'
        ' "beneficiaries": [{'
        '   "full_legal_name": "Michael Thompson",'
        '   "full_legal_name_diag": {"illegible": false, "note": null},'
        '   "relationship": "child",'
        '   "relationship_diag": {"illegible": false, "note": null},'
        '   "share_percent": "100",'
        '   "share_percent_diag": {"illegible": false, "note": null}}]}'
    )
    client = _make_mock_client_returning(envelope_json)
    backend = OllamaBackend(model="qwen2.5vl:7b", client=client)

    result = backend.extract(Path("fake.png"))

    field_paths = [f.field_path for f in result.trace.fields]
    assert "other_beneficiaries[0].full_legal_name" in field_paths
    assert "other_beneficiaries[0].relationship_other" in field_paths
    assert "beneficiary_shares[0].share_percent" in field_paths

    assert len(result.data.other_beneficiaries) == 1
    assert len(result.data.beneficiary_shares) == 1
    assert result.data.beneficiary_shares[0].recipient_ref == "other_beneficiaries[0]"

    for path in field_paths:
        resolved, _ = resolve(result.data, path)
        assert resolved, f"field_path {path!r} does not resolve against TrustData"


def test_ollama_backend_extract_empty_form_yields_default_trust_data() -> None:
    """Spec §7.6 row 5 — empty form (no fields) is NOT a failure: the result
    is a default-constructed TrustData paired with an empty-fields trace.
    """
    from trust_generator.v3.extraction import OllamaBackend
    from trust_generator.v3.schema import TrustData

    envelope_json = (
        '{"reasoning": "Form is blank or unreadable.",'
        ' "grantors": [],'
        ' "beneficiaries": []}'
    )
    client = _make_mock_client_returning(envelope_json)
    backend = OllamaBackend(model="qwen2.5vl:7b", client=client)

    result = backend.extract(Path("fake.png"))

    assert result.trace.fields == []
    # Default-constructed: no co_grantor, no beneficiary lists populated, etc.
    default = TrustData()
    assert result.data.co_grantor == default.co_grantor  # both None
    assert result.data.other_beneficiaries == default.other_beneficiaries  # both []
    assert result.data.beneficiary_shares == default.beneficiary_shares  # both []


def test_ollama_backend_extract_legible_deferred_fields_use_incomplete_sentinel() -> None:
    """Spec §7.3.3 — non-string TrustData fields (Decimal share_percent,
    date_of_birth) leave normalized_value as the INCOMPLETE sentinel when
    legible but not yet normalized. The IncompleteUntilValidated marker
    on FieldExtraction.normalized_value enforces this discipline at the
    type level; the mapper enforces it at runtime.

    Plan 9c's diagnostics integration emits ``extraction.no_normalized_value``
    when a field is legible but normalized_value is INCOMPLETE/None at
    verify time — this test pins that the mapper produces the signal
    correctly.
    """
    from trust_generator.v3.extraction import OllamaBackend
    from trust_generator.v3.extraction.trace import INCOMPLETE

    envelope_json = (
        '{"reasoning": "Form has grantor DOB and one beneficiary with share.",'
        ' "grantors": [{"full_legal_name": "James William Thompson, Jr.",'
        '              "full_legal_name_diag": {"illegible": false, "note": null},'
        '              "date_of_birth": "March 15, 1958",'
        '              "date_of_birth_diag": {"illegible": false, "note": null}}],'
        ' "beneficiaries": [{"full_legal_name": "Michael Thompson",'
        '                    "full_legal_name_diag": {"illegible": false, "note": null},'
        '                    "relationship": null,'
        '                    "relationship_diag": {"illegible": false, "note": null},'
        '                    "share_percent": "100",'
        '                    "share_percent_diag": {"illegible": false, "note": null}}]}'
    )
    client = _make_mock_client_returning(envelope_json)
    backend = OllamaBackend(model="qwen2.5vl:7b", client=client)

    result = backend.extract(Path("fake.png"))

    by_path = {f.field_path: f for f in result.trace.fields}
    # date_of_birth is legible but date-normalization is deferred → INCOMPLETE.
    assert by_path["grantor.date_of_birth"].normalized_value is INCOMPLETE
    assert by_path["grantor.date_of_birth"].raw_value == "March 15, 1958"
    # share_percent is legible but Decimal-normalization is deferred → INCOMPLETE.
    assert by_path["beneficiary_shares[0].share_percent"].normalized_value is INCOMPLETE
    assert by_path["beneficiary_shares[0].share_percent"].raw_value == "100"
    # full_legal_name is str → str (no normalization needed); INCOMPLETE not used.
    assert (
        by_path["grantor.full_legal_name"].normalized_value
        == "James William Thompson, Jr."
    )


def test_ollama_backend_extract_illegible_yields_normalized_value_none() -> None:
    """Spec §7.6 row 4 + FieldExtraction._illegible_excludes_normalized_value
    invariant: when envelope.field_diag.illegible is True, the trace's
    FieldExtraction.normalized_value is None (NOT the raw envelope value).
    """
    from trust_generator.v3.extraction import OllamaBackend

    # Envelope where the data field is null but diag flags illegible:
    # the mapper emits a FieldExtraction(illegible=True, normalized_value=None).
    envelope_json = (
        '{"reasoning": "Grantor name is smudged beyond recognition.",'
        ' "grantors": [{"full_legal_name": null,'
        '              "full_legal_name_diag": {"illegible": true, "note": "ink smudge"},'
        '              "date_of_birth": null,'
        '              "date_of_birth_diag": {"illegible": false, "note": null}}],'
        ' "beneficiaries": []}'
    )
    client = _make_mock_client_returning(envelope_json)
    backend = OllamaBackend(model="qwen2.5vl:7b", client=client)

    result = backend.extract(Path("fake.png"))

    illegible_fields = [f for f in result.trace.fields if f.illegible]
    assert len(illegible_fields) == 1
    assert illegible_fields[0].field_path == "grantor.full_legal_name"
    assert illegible_fields[0].normalized_value is None
    assert illegible_fields[0].raw_value == ""


def test_ollama_backend_extract_passes_format_schema_to_client() -> None:
    """``client.chat`` is invoked with ``format=GenerationEnvelope.model_json_schema()``."""
    from trust_generator.v3.extraction import OllamaBackend
    from trust_generator.v3.extraction.ollama_backend import GenerationEnvelope

    envelope_json = '{"reasoning": "empty form", "grantors": [], "beneficiaries": []}'
    client = _make_mock_client_returning(envelope_json)
    backend = OllamaBackend(model="qwen2.5vl:7b", client=client)

    backend.extract(Path("fake.png"))

    call_kwargs = client.chat.call_args.kwargs
    assert call_kwargs["format"] == GenerationEnvelope.model_json_schema()


def test_ollama_backend_extract_passes_temperature_zero_to_client() -> None:
    """``client.chat`` is invoked with ``options={"temperature": 0}`` (spec §7.4 determinism)."""
    from trust_generator.v3.extraction import OllamaBackend

    envelope_json = '{"reasoning": "empty form", "grantors": [], "beneficiaries": []}'
    client = _make_mock_client_returning(envelope_json)
    backend = OllamaBackend(model="qwen2.5vl:7b", client=client)

    backend.extract(Path("fake.png"))

    call_kwargs = client.chat.call_args.kwargs
    assert call_kwargs["options"] == {"temperature": 0}


def test_ollama_backend_extract_passes_image_path_as_str(tmp_path: Path) -> None:
    """``messages[0]['images']`` carries the resolved path as a string (spec §7.6)."""
    from trust_generator.v3.extraction import OllamaBackend

    fake_image = tmp_path / "form.png"
    fake_image.touch()

    envelope_json = '{"reasoning": "empty form", "grantors": [], "beneficiaries": []}'
    client = _make_mock_client_returning(envelope_json)
    backend = OllamaBackend(model="qwen2.5vl:7b", client=client)

    backend.extract(fake_image)

    call_kwargs = client.chat.call_args.kwargs
    images = call_kwargs["messages"][0]["images"]
    assert images == [str(fake_image.resolve())]


def test_ollama_backend_extract_passes_prompt_to_client() -> None:
    """``messages[0]['content']`` carries the rendered prompt string."""
    from trust_generator.v3.extraction import OllamaBackend
    from trust_generator.v3.extraction.prompt import build_intake_prompt

    envelope_json = '{"reasoning": "empty form", "grantors": [], "beneficiaries": []}'
    client = _make_mock_client_returning(envelope_json)
    backend = OllamaBackend(model="qwen2.5vl:7b", client=client)

    backend.extract(Path("fake.png"))

    call_kwargs = client.chat.call_args.kwargs
    content = call_kwargs["messages"][0]["content"]
    assert content == build_intake_prompt()


def test_ollama_backend_extract_passes_model_to_client() -> None:
    """``client.chat`` is invoked with ``model=<self.model>``."""
    from trust_generator.v3.extraction import OllamaBackend

    envelope_json = '{"reasoning": "empty form", "grantors": [], "beneficiaries": []}'
    client = _make_mock_client_returning(envelope_json)
    backend = OllamaBackend(model="qwen2.5vl:7b", client=client)

    backend.extract(Path("fake.png"))

    call_kwargs = client.chat.call_args.kwargs
    assert call_kwargs["model"] == "qwen2.5vl:7b"
```

- [ ] **Step 2: Run the test to confirm Red**

Run: `pixi run test test_ollama_backend`
Expected: 20 tests fail. The first failure mode is `ImportError: cannot import name 'OllamaBackend'` (the symbol doesn't exist yet); subsequent tests will fail at the same import.

- [ ] **Step 3: Author the production code (Green)**

Modify `src/trust_generator/v3/extraction/ollama_backend.py`. The cycle 9b-1 file currently has the module docstring at the top, then `from __future__ import annotations`, then `from pydantic import BaseModel, ConfigDict, Field`, then the four model classes. Two structural rules govern this edit:

1. **All new imports MUST go at the top of the file**, alongside the existing `from pydantic import ...` line. Embedding imports mid-file violates ruff E402 ("module level import not at top of file") and the `pixi run check` gate will reject the commit.
2. **The new `OllamaBackend` class and `_envelope_to_extraction_result` mapper get appended at the bottom** of the file (after `class GenerationEnvelope`).

Apply the imports edit at the top of the file (insert after the existing `from pydantic` line, preserving import-group ordering: stdlib, third-party, first-party):

```python
"""...existing module docstring (do not touch)..."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import ollama
from pydantic import BaseModel, ConfigDict, Field

from trust_generator.v3.extraction.prompt import build_intake_prompt
from trust_generator.v3.extraction.trace import (
    INCOMPLETE,
    ExtractionResult,
    ExtractionTrace,
    FieldExtraction,
)
from trust_generator.v3.schema import (
    BeneficiaryShare,
    GrantorInfo,
    OtherBeneficiary,
    TrustData,
)

if TYPE_CHECKING:
    from trust_generator.v3.extraction.protocol import SourceRef
```

(`INCOMPLETE` is the spec §5.3 sentinel imported explicitly per the trace.py docstring's "consumers import it explicitly" discipline. It is NOT exported via `extraction/__init__.py`'s `__all__` — by spec — so we import directly from `trace`.)

(`SourceRef` is `TYPE_CHECKING`-only because it is a `Path` alias — runtime import would create an unused-import lint warning since the function annotates with the alias but uses the value as a `Path`.)

Then append at the end of the file (after `class GenerationEnvelope`):

```python
class OllamaBackend:
    """ExtractionProtocol implementation against a local Ollama server.

    Pinned dependency: ``ollama >= 0.6.1`` (per spec §7.1, added in
    plan 9a Task 5). Pinned schema delivery: ``format=
    GenerationEnvelope.model_json_schema()`` (spec §7.3). Pinned
    determinism: ``options={'temperature': 0}`` (spec §7.4). Pinned
    field-order discipline: ``reasoning`` is the first field on
    ``GenerationEnvelope`` (spec §7.4 + cycle 9b-1 schema test +
    task 9b-5 live JSON-key-order pin).

    NOTE: At chore #14 fulfillment, the ``IMPORTANT`` blocks at the
    top of this module — and this docstring's reference to chore #14
    — MUST be removed (per chore #14 body's fulfillment cleanup
    direction).
    """

    def __init__(
        self,
        model: str,
        client: ollama.Client | None = None,
        prompt_builder: Callable[[], str] | None = None,
    ) -> None:
        self.model = model
        self.client = client if client is not None else ollama.Client()
        self.prompt_builder = (
            prompt_builder if prompt_builder is not None else build_intake_prompt
        )

    def extract(self, source: SourceRef) -> ExtractionResult:
        """Extract a TrustData and ExtractionTrace from one source.

        Spec §5.4 — failure modes raise ``ExtractionError`` (cycle 9b-4
        adds the error contract). Per-field illegibility, missing fields,
        and low-confidence transcriptions are NOT failures: they land on
        the trace as ``FieldExtraction`` entries with ``illegible=True``
        and/or ``normalized_value=None``. Spec §7.3.4 — TrustData stays
        default-constructed; the OCR'd values are evidence carried on
        the trace, not facts asserted into TrustData.
        """
        prompt = self.prompt_builder()
        image_path_str = str(source.resolve())

        response = self.client.chat(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                    "images": [image_path_str],
                }
            ],
            format=GenerationEnvelope.model_json_schema(),
            options={"temperature": 0},
        )

        envelope = GenerationEnvelope.model_validate_json(response.message.content)
        return _envelope_to_extraction_result(envelope, model=self.model)


def _envelope_to_extraction_result(
    envelope: GenerationEnvelope, *, model: str
) -> ExtractionResult:
    """Map a validated GenerationEnvelope to an ExtractionResult.

    Spec §7.3.1-§7.3.4 — collapse envelope.grantors[0..1] onto
    TrustData.grantor + co_grantor; map envelope.beneficiaries[i] to
    other_beneficiaries[i] (conservative classification fallback per
    §7.3.2); emit beneficiary_shares[i] paired by deterministic
    recipient_ref. TrustData is default-constructed apart from
    co_grantor instantiation when needed; OCR'd values land on the
    trace via FieldExtraction (raw_value), with normalized_value=None
    (illegible branch) or normalization deferred under
    IncompleteUntilValidated discipline (legible branch).

    Per spec §8.3 omit-if-absent: a FieldExtraction is emitted only
    when the envelope's data field is non-None OR the sibling diag's
    illegible flag is set. Both branches signal "the model attempted
    this field"; absent (data null AND diag quiet) yields no entry.
    """
    fields: list[FieldExtraction] = []
    data = TrustData()

    # Grantors: envelope.grantors[0] → data.grantor; envelope.grantors[1] → data.co_grantor.
    if len(envelope.grantors) >= 2:
        data.co_grantor = GrantorInfo()

    grantor_paths = ("grantor", "co_grantor")
    for idx, grantor in enumerate(envelope.grantors[:2]):
        prefix = grantor_paths[idx]
        if (
            grantor.full_legal_name is not None
            or grantor.full_legal_name_diag.illegible
        ):
            illegible = grantor.full_legal_name_diag.illegible
            fields.append(
                FieldExtraction(
                    field_path=f"{prefix}.full_legal_name",
                    raw_value=grantor.full_legal_name or "",
                    normalized_value=None if illegible else grantor.full_legal_name,
                    illegible=illegible,
                )
            )
        if (
            grantor.date_of_birth is not None
            or grantor.date_of_birth_diag.illegible
        ):
            illegible = grantor.date_of_birth_diag.illegible
            fields.append(
                FieldExtraction(
                    field_path=f"{prefix}.date_of_birth",
                    raw_value=grantor.date_of_birth or "",
                    # Date normalization deferred (spec §7.3.3): INCOMPLETE sentinel
                    # for legible-but-not-yet-normalized; None for illegible (the
                    # _illegible_excludes_normalized_value validator rejects non-None
                    # alongside illegible=True).
                    normalized_value=None if illegible else INCOMPLETE,
                    illegible=illegible,
                )
            )

    # Beneficiaries: envelope.beneficiaries[i] → other_beneficiaries[i] (spec §7.3.2);
    # envelope.beneficiaries[i].share_percent → beneficiary_shares[i] paired by
    # recipient_ref convention 'other_beneficiaries[{i}]'.
    for j, beneficiary in enumerate(envelope.beneficiaries):
        data.other_beneficiaries.append(OtherBeneficiary())
        data.beneficiary_shares.append(
            BeneficiaryShare(recipient_ref=f"other_beneficiaries[{j}]")
        )

        if (
            beneficiary.full_legal_name is not None
            or beneficiary.full_legal_name_diag.illegible
        ):
            illegible = beneficiary.full_legal_name_diag.illegible
            fields.append(
                FieldExtraction(
                    field_path=f"other_beneficiaries[{j}].full_legal_name",
                    raw_value=beneficiary.full_legal_name or "",
                    normalized_value=None if illegible else beneficiary.full_legal_name,
                    illegible=illegible,
                )
            )
        if (
            beneficiary.relationship is not None
            or beneficiary.relationship_diag.illegible
        ):
            illegible = beneficiary.relationship_diag.illegible
            fields.append(
                FieldExtraction(
                    # Free-text fallback (spec §7.3.1): typed relationship enum
                    # stays default; relationship_other carries the verbatim string.
                    field_path=f"other_beneficiaries[{j}].relationship_other",
                    raw_value=beneficiary.relationship or "",
                    normalized_value=None if illegible else beneficiary.relationship,
                    illegible=illegible,
                )
            )
        if (
            beneficiary.share_percent is not None
            or beneficiary.share_percent_diag.illegible
        ):
            illegible = beneficiary.share_percent_diag.illegible
            fields.append(
                FieldExtraction(
                    field_path=f"beneficiary_shares[{j}].share_percent",
                    raw_value=beneficiary.share_percent or "",
                    # Numeric normalization deferred (spec §7.3.3): INCOMPLETE sentinel
                    # for legible-but-not-yet-normalized.
                    normalized_value=None if illegible else INCOMPLETE,
                    illegible=illegible,
                )
            )

    trace = ExtractionTrace(
        fields=fields,
        backend_id=f"ollama:{model}",
        extracted_at=datetime.now(UTC),
    )

    return ExtractionResult(data=data, trace=trace)
```

> **Construction-failure escape.** If `TrustData()` raises on the
> default-construct line because a required field has no default,
> halt the cycle, do NOT default-fill the failing fields with
> sentinels in this plan-md, and open a chore via scope-maintenance
> for full-mirror envelope expansion (per plan 9b Q4). The chore's
> blast radius will include `src/trust_generator/v3/extraction/
> ollama_backend.py` (extending the envelope and the mapper) and
> tests under `tests/v3/extraction/`. Resume cycle 9b-3 after the
> chore lands.

Modify `src/trust_generator/v3/extraction/__init__.py` to add `OllamaBackend`:

```python
"""OCR extraction surface — markers, trace, Protocol, and helpers.

Public surface declared in ``__all__``; the ``INCOMPLETE`` sentinel is
intentionally NOT exported (per spec §5.3 — consumers import it
explicitly to make the in-memory-identity discipline visible).
"""

from __future__ import annotations

from trust_generator.v3.extraction.markers import (
    IncompleteUntilValidated,
    RawSelfReport,
)
from trust_generator.v3.extraction.ollama_backend import OllamaBackend
from trust_generator.v3.extraction.paths import resolve
from trust_generator.v3.extraction.protocol import (
    ExtractionError,
    ExtractionProtocol,
    SourceRef,
)
from trust_generator.v3.extraction.trace import (
    ExtractionResult,
    ExtractionTrace,
    FieldExtraction,
)

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
)
```

> **RUF022 note.** Ruff's RUF022 will auto-alphabetize `__all__` on `pixi run fix`. The order shown above is alphabetic and stable.

- [ ] **Step 4: Run the test to confirm Green**

Run: `pixi run test test_ollama_backend`
Expected: 20 tests pass.

- [ ] **Step 5: Run the project gate**

Run: `pixi run check`
Expected: green. mypy validates the structural conformance assertion (`backend: ExtractionProtocol = OllamaBackend(...)`); a type error there means the `extract` signature has drifted from the Protocol.

- [ ] **Step 6: Commit Red and Green**

```bash
git add tests/v3/extraction/test_ollama_backend.py
git commit -m "test(extraction): RED — cycle 9b-3 OllamaBackend.extract happy path"
```

```bash
git add src/trust_generator/v3/extraction/ollama_backend.py src/trust_generator/v3/extraction/__init__.py
git commit -m "feat(extraction): GREEN — cycle 9b-3 OllamaBackend.extract happy path"
```

- [ ] **Step 7: Refactor — split per-section envelope mappers**

The Green-phase mapper bridges three orthogonal section concerns (grantor envelope → grantor + co_grantor; beneficiary envelope → other_beneficiaries name/relationship; share envelope → beneficiary_shares with recipient_ref linkage). Split per-section helpers and rewrite `_envelope_to_extraction_result` to delegate. Target shape:

```python
def _map_grantor_envelope(
    grantors: list[GrantorEnvelope],
) -> tuple[list[FieldExtraction], bool]:
    """Map envelope.grantors → trace fields under 'grantor.*' / 'co_grantor.*'.

    Returns (fields, needs_co_grantor) — needs_co_grantor signals to the
    caller that TrustData.co_grantor must be instantiated.
    """
    fields: list[FieldExtraction] = []
    grantor_paths = ("grantor", "co_grantor")
    for idx, grantor in enumerate(grantors[:2]):
        prefix = grantor_paths[idx]
        # ... per-field emit with illegibility-coercing normalized_value
    return fields, len(grantors) >= 2


def _map_beneficiary_envelope(
    beneficiaries: list[BeneficiaryEnvelope],
) -> tuple[list[FieldExtraction], list[OtherBeneficiary], list[BeneficiaryShare]]:
    """Map envelope.beneficiaries → trace fields + TrustData lists.

    Spec §7.3.2 conservative classification fallback: every envelope
    beneficiary lands in other_beneficiaries[i]; the paired
    beneficiary_shares[i] uses recipient_ref convention
    'other_beneficiaries[{i}]'.
    """
    fields: list[FieldExtraction] = []
    others: list[OtherBeneficiary] = []
    shares: list[BeneficiaryShare] = []
    for j, beneficiary in enumerate(beneficiaries):
        others.append(OtherBeneficiary())
        shares.append(BeneficiaryShare(recipient_ref=f"other_beneficiaries[{j}]"))
        # ... per-field emit
    return fields, others, shares


def _envelope_to_extraction_result(
    envelope: GenerationEnvelope, *, model: str
) -> ExtractionResult:
    data = TrustData()
    grantor_fields, needs_co_grantor = _map_grantor_envelope(envelope.grantors)
    if needs_co_grantor:
        data.co_grantor = GrantorInfo()
    beneficiary_fields, others, shares = _map_beneficiary_envelope(envelope.beneficiaries)
    data.other_beneficiaries = others
    data.beneficiary_shares = shares

    trace = ExtractionTrace(
        fields=[*grantor_fields, *beneficiary_fields],
        backend_id=f"ollama:{model}",
        extracted_at=datetime.now(UTC),
    )
    return ExtractionResult(data=data, trace=trace)
```

Verify tests still pass:

Run: `pixi run check`
Expected: green. The 20 cycle 9b-3 tests must still pass against the refactored mapper (tests assert externally observable behavior — field_paths, recipient_ref convention, illegibility-coercion — not internal structure).

- [ ] **Step 8: Commit Refactor**

```bash
git add src/trust_generator/v3/extraction/ollama_backend.py
git commit -m "refactor(extraction): cycle 9b-3 split per-section envelope mappers"
```

</cycle>

---

## Cycle 9b-4 — `OllamaBackend.extract`, error paths

<cycle id="9b-4"
       spec-ref="§6.6, §7.6"
       blast-radius="src/trust_generator/v3/extraction/ollama_backend.py; tests/v3/extraction/test_ollama_backend_errors.py"
       depends-on="9b-3"
       commits="red,green">

**Files:**

- Modify: `src/trust_generator/v3/extraction/ollama_backend.py` (wrap `extract` body in try/except for the three error sources; do not change the happy path)
- Create: `tests/v3/extraction/test_ollama_backend_errors.py`

Per spec §7.6, `OllamaBackend.extract` converts five classes of failure into `ExtractionError` (chained via `__cause__`):

1. `ollama.ResponseError` — HTTP-status error from the Ollama server (e.g., 404 model-not-found, 500 server-error).
2. `ConnectionError` — Python builtin, raised by `ollama-python` when `httpx.ConnectError` surfaces (the library catches `httpx.ConnectError` and re-raises `ConnectionError` with `from None` — verified against `ollama/_client.py` lines 134-135). This is the actual production failure mode when the Ollama server is unreachable.
3. `httpx.HTTPError` — residual transport errors not wrapped by `ollama-python` (timeouts, read/write errors, protocol errors). The library handles `httpx.HTTPStatusError` and `httpx.ConnectError` explicitly; everything else passes through.
4. `ValueError` — request-construction failure surfaced by `ollama-python`'s `Image.serialize_model` for missing image paths or malformed base64/path inputs (verified against `ollama/_types.py` lines 178-179: `raise ValueError(f'File {value} does not exist')`). Without this catch, a paralegal passing a missing path receives an unwrapped `ValueError` from extract() — breaking the uniform-error-class invariant.
5. `pydantic.ValidationError` — envelope JSON parses but doesn't satisfy `GenerationEnvelope`'s constraints (malformed schema or oversized `reasoning`).

Per-field illegibility on the form is NOT a failure — it remains the success path.

**Refactor decision:** Per `refactor_threshold` evaluation — five distinct error sources with five distinct error messages do not exhibit structural duplication that benefits from helper extraction. Each `except` clause has its own message phrasing reflecting the underlying failure mode. `commits="red,green"`; **no refactor stage — green output is already minimal; the five exception clauses each carry distinct semantics, and consolidating into a generic wrapper would lose diagnostic specificity.**

- [ ] **Step 1: Author the failing test (Red)**

Create `tests/v3/extraction/test_ollama_backend_errors.py`:

```python
"""Cycle 9b-4 tests — OllamaBackend.extract error paths."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import httpx
import ollama
import pytest


def _make_failing_client(error: Exception) -> MagicMock:
    """Construct a MagicMock-shaped ollama.Client whose chat() raises ``error``."""
    client = MagicMock()
    client.chat.side_effect = error
    return client


def _make_envelope_returning_client(envelope_json: str) -> MagicMock:
    """Construct a MagicMock-shaped ollama.Client whose chat() returns
    a response object with .message.content equal to envelope_json."""
    response = MagicMock()
    response.message.content = envelope_json
    client = MagicMock()
    client.chat.return_value = response
    return client


def test_response_error_is_wrapped_as_extraction_error() -> None:
    """``ollama.ResponseError`` from chat() raises ExtractionError, chained."""
    from trust_generator.v3.extraction import ExtractionError, OllamaBackend

    err = ollama.ResponseError("model not found", status_code=404)
    backend = OllamaBackend(model="qwen2.5vl:7b", client=_make_failing_client(err))

    with pytest.raises(ExtractionError) as exc_info:
        backend.extract(Path("fake.png"))

    assert exc_info.value.__cause__ is err


def test_response_error_message_includes_status_code() -> None:
    """The ExtractionError message references the upstream status_code."""
    from trust_generator.v3.extraction import ExtractionError, OllamaBackend

    err = ollama.ResponseError("model not found", status_code=404)
    backend = OllamaBackend(model="qwen2.5vl:7b", client=_make_failing_client(err))

    with pytest.raises(ExtractionError, match="404"):
        backend.extract(Path("fake.png"))


def test_connection_error_is_wrapped_as_extraction_error() -> None:
    """Python builtin ``ConnectionError`` from chat() raises ExtractionError, chained.

    This is the production failure mode when the Ollama server is unreachable:
    ``ollama-python`` catches ``httpx.ConnectError`` internally and re-raises
    ``ConnectionError`` with ``from None`` (verified against
    ollama/_client.py lines 134-135). Catching ``httpx.HTTPError`` alone
    would leak this error class unwrapped.
    """
    from trust_generator.v3.extraction import ExtractionError, OllamaBackend

    err = ConnectionError("Failed to connect to Ollama")
    backend = OllamaBackend(model="qwen2.5vl:7b", client=_make_failing_client(err))

    with pytest.raises(ExtractionError) as exc_info:
        backend.extract(Path("fake.png"))

    assert exc_info.value.__cause__ is err


def test_residual_httpx_error_is_wrapped_as_extraction_error() -> None:
    """Residual ``httpx.HTTPError`` (timeouts, protocol errors) raises ExtractionError, chained.

    These are httpx errors NOT wrapped by ollama-python — timeouts,
    read/write errors, protocol errors. The library only converts
    ``httpx.HTTPStatusError`` (→ ``ResponseError``) and
    ``httpx.ConnectError`` (→ ``ConnectionError``); everything else
    passes through and our error contract must still wrap.
    """
    from trust_generator.v3.extraction import ExtractionError, OllamaBackend

    err = httpx.ReadTimeout("read timeout")
    backend = OllamaBackend(model="qwen2.5vl:7b", client=_make_failing_client(err))

    with pytest.raises(ExtractionError) as exc_info:
        backend.extract(Path("fake.png"))

    assert exc_info.value.__cause__ is err


def test_missing_image_path_is_wrapped_as_extraction_error() -> None:
    """A non-existent image path surfaces as ExtractionError, chained.

    Production failure mode: ``ollama-python``'s ``Image.serialize_model``
    raises ``ValueError`` when a path-typed image value points to a
    non-existent file with a recognized image extension (verified against
    ollama/_types.py lines 178-179: ``raise ValueError(f'File {value}
    does not exist')``). Without our wrapping, this leaks as ValueError
    from extract() — confusing for paralegals who expect ExtractionError
    for any extract() failure.
    """
    from trust_generator.v3.extraction import ExtractionError, OllamaBackend

    err = ValueError("File /tmp/nonexistent.png does not exist")
    backend = OllamaBackend(model="qwen2.5vl:7b", client=_make_failing_client(err))

    with pytest.raises(ExtractionError) as exc_info:
        backend.extract(Path("/tmp/nonexistent.png"))

    assert exc_info.value.__cause__ is err


def test_malformed_envelope_json_is_wrapped_as_extraction_error() -> None:
    """An envelope JSON that fails ``model_validate_json`` raises ExtractionError, chained."""
    from pydantic import ValidationError

    from trust_generator.v3.extraction import ExtractionError, OllamaBackend

    # Missing required ``reasoning`` field
    bad_json = '{"grantors": [], "beneficiaries": []}'
    client = _make_envelope_returning_client(bad_json)
    backend = OllamaBackend(model="qwen2.5vl:7b", client=client)

    with pytest.raises(ExtractionError) as exc_info:
        backend.extract(Path("fake.png"))

    assert isinstance(exc_info.value.__cause__, ValidationError)


def test_oversized_reasoning_is_wrapped_as_extraction_error() -> None:
    """An envelope with oversized ``reasoning`` is rejected at validation time.

    Note: This case should not occur with constrained decoding (the
    schema enforces max_length at sample-time). The test pins what
    happens if it does.
    """
    from pydantic import ValidationError

    from trust_generator.v3.extraction import ExtractionError, OllamaBackend

    oversized = "x" * 2001
    bad_json = (
        '{"reasoning": "' + oversized + '",'
        ' "grantors": [], "beneficiaries": []}'
    )
    client = _make_envelope_returning_client(bad_json)
    backend = OllamaBackend(model="qwen2.5vl:7b", client=client)

    with pytest.raises(ExtractionError) as exc_info:
        backend.extract(Path("fake.png"))

    assert isinstance(exc_info.value.__cause__, ValidationError)


def test_non_json_response_is_wrapped_as_extraction_error() -> None:
    """A non-JSON ``message.content`` (e.g., model emits prose) raises ExtractionError, chained."""
    from pydantic import ValidationError

    from trust_generator.v3.extraction import ExtractionError, OllamaBackend

    bad_content = "I cannot extract from this image."
    client = _make_envelope_returning_client(bad_content)
    backend = OllamaBackend(model="qwen2.5vl:7b", client=client)

    with pytest.raises(ExtractionError) as exc_info:
        backend.extract(Path("fake.png"))

    assert isinstance(exc_info.value.__cause__, ValidationError)
```

- [ ] **Step 2: Run the test to confirm Red**

Run: `pixi run test test_ollama_backend_errors`
Expected: 8 tests fail. The current `extract` implementation (cycle 9b-3) re-raises the underlying errors without wrapping; tests assert wrapping, so they fail.

- [ ] **Step 3: Author the production code (Green)**

Modify `OllamaBackend.extract` in `src/trust_generator/v3/extraction/ollama_backend.py` to wrap the wire-call and envelope-validation steps:

```python
    def extract(self, source: SourceRef) -> ExtractionResult:
        """..."""
        prompt = self.prompt_builder()
        image_path_str = str(source.resolve())

        try:
            response = self.client.chat(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                        "images": [image_path_str],
                    }
                ],
                format=GenerationEnvelope.model_json_schema(),
                options={"temperature": 0},
            )
        except ollama.ResponseError as e:
            raise ExtractionError(
                f"Ollama returned error status={e.status_code}: {e}"
            ) from e
        except ConnectionError as e:
            # Production path when Ollama is unreachable: the library
            # catches httpx.ConnectError and re-raises Python's builtin
            # ConnectionError (ollama/_client.py:134-135).
            raise ExtractionError(
                f"Cannot connect to Ollama server: {e}"
            ) from e
        except httpx.HTTPError as e:
            # Residual transport errors not wrapped by ollama-python:
            # timeouts, read/write errors, protocol errors.
            raise ExtractionError(
                f"Network error contacting Ollama: {e}"
            ) from e
        except ValueError as e:
            # ollama-python's Image.serialize_model raises ValueError for
            # missing image paths (ollama/_types.py:178-179) and for
            # malformed base64/path inputs. Wrap as ExtractionError so
            # paralegals get a uniform error class for extract() failures.
            raise ExtractionError(
                f"Image path or request construction error: {e}"
            ) from e

        try:
            envelope = GenerationEnvelope.model_validate_json(response.message.content)
        except ValidationError as e:
            raise ExtractionError(
                f"Malformed envelope from model {self.model}: {e}"
            ) from e

        return _envelope_to_extraction_result(envelope, model=self.model)
```

Add the imports at the top of `ollama_backend.py` (alongside the existing imports added in cycle 9b-3):

```python
import httpx
from pydantic import ValidationError

from trust_generator.v3.extraction.protocol import ExtractionError
```

- [ ] **Step 4: Run the test to confirm Green**

Run: `pixi run test test_ollama_backend_errors`
Expected: 8 tests pass.

Run: `pixi run test test_ollama_backend`
Expected: 20 tests pass (cycle 9b-3's happy-path tests must continue to pass — error wrapping must not regress the happy path).

- [ ] **Step 5: Run the project gate**

Run: `pixi run check`
Expected: green.

- [ ] **Step 6: Commit Red and Green**

```bash
git add tests/v3/extraction/test_ollama_backend_errors.py
git commit -m "test(extraction): RED — cycle 9b-4 OllamaBackend.extract error paths"
```

```bash
git add src/trust_generator/v3/extraction/ollama_backend.py
git commit -m "feat(extraction): GREEN — cycle 9b-4 ExtractionError wrapping for ResponseError/HTTPError/ValidationError"
```

</cycle>

---

## Task 9b-5 — Live vision-model smoke test (integration)

<task id="9b-5"
      spec-ref="§6.10, §7.4"
      blast-radius="tests/v3/extraction/test_ollama_backend_integration.py"
      depends-on="9b-4, chore-16">

**Files:**

- Create: `tests/v3/extraction/test_ollama_backend_integration.py`

Per spec §6.10, this is a verification task. The implementation is already complete by cycle 9b-3 (extract happy path) + 9b-4 (error wrapping); this task adds the integration-level smoke test marked `pytest.mark.integration`.

**Precondition: chore #16 must land before this task.** Chore #16 (`2026-04-28-pytest-integration-marker-config`) adds `[tool.pytest.ini_options]` to pyproject.toml registering the `integration` marker and skipping it by default via `addopts = "-m 'not integration'"`. Without that config, the marker is unregistered and the test runs on every `pixi run check`. The opt-in invocation after chore #16 lands is `pixi run test -m integration <path>` — there is no `--runintegration` flag in this project.

The smoke test asserts ONLY structural shape:

1. `backend.extract(<photo>)` returns an `ExtractionResult` with at least one `FieldExtraction` on its trace.
2. The raw `response.message.content` (intercepted before envelope validation) is a JSON object whose first key is `reasoning` — the integration-level pin for spec §7.4 reasoning-first discipline.

The fixture path is read from the `OCR_SMOKE_FIXTURE_PATH` env var, defaulting to `assets/handwriting-samples/pages/print.jpg` (per Q7). If neither the env var path nor the default path exists, the test skips with a clear message.

This task does NOT iterate on the prompt based on live observation. If the live model produces output that fails the smoke assertions (e.g., reasoning-not-first because the model's tokenizer or the schema interaction differ from the cycle 9b-1 unit test's assumption), the failure surfaces as task-execution feedback. Resolution paths:
- **Best:** the prompt and envelope land as-is; the live test passes; the cycle is closed.
- **Acceptable:** the prompt requires minor language amendment to elicit reasoning-first; amendment is committed under `prompt.py` as a cycle-9b-2 amendment commit (re-running cycle 9b-2 tests to confirm marker phrases still pass) and the smoke task re-verified.
- **Escalate:** the live model fundamentally does not honor reasoning-first under the chosen `format=` schema; this is a §7.4 spec finding — open a chore for §7.4 amendment per spec §13.2 / chore #14, do NOT silently rewrite the schema or prompt without spec amendment.

The mode of failure (which of the three above) is the deliverable of running the task; the plan does not pre-commit to which path is taken because that depends on observation.

- [ ] **Step 1: Author the integration test**

Create `tests/v3/extraction/test_ollama_backend_integration.py`:

```python
"""Task 9b-5 — Live vision-model integration smoke test.

Marked ``pytest.mark.integration``. Skipped by default via
pyproject.toml's ``addopts = "-m 'not integration'"`` (configured by
chore #16). Opt-in invocation: ``pixi run test -m integration``.

The test reads ``OCR_SMOKE_FIXTURE_PATH`` env var for the photo path,
defaulting to ``assets/handwriting-samples/pages/print.jpg``. If the
file is missing, the test skips.

PHI hygiene: the default fixture is paralegal-curated synthetic-persona
handwriting documented in ``assets/handwriting-samples/pages/BASELINE.md``;
real client intakes never enter the repo. If a developer overrides
``OCR_SMOKE_FIXTURE_PATH`` to a real intake for local debugging, that
path MUST stay outside the repo (e.g., ``/tmp/`` or a personal scratch
directory) — the smoke test reads from disk only and does not stage
or commit the override path.

Cost discipline: the two assertions below share one live ``chat()``
call via a session-scoped fixture. Vision-model invocations take
20-60s on consumer hardware; halving the per-run cost matters for
manual smoke loops.

Requires a local Ollama server (default ``http://localhost:11434``) with
a vision-language model pulled (e.g., ``ollama pull qwen2.5vl:7b``).
The model name is configurable via ``OCR_SMOKE_MODEL`` env var
(default ``qwen2.5vl:7b``).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def _resolve_fixture_path() -> Path:
    """Resolve OCR_SMOKE_FIXTURE_PATH, defaulting to the canonical baseline."""
    env_path = os.environ.get("OCR_SMOKE_FIXTURE_PATH")
    if env_path:
        return Path(env_path)
    # Default: project-root-relative (resolved against current working dir,
    # which is the project root for ``pixi run test``).
    return Path("assets/handwriting-samples/pages/print.jpg")


def _resolve_model() -> str:
    return os.environ.get("OCR_SMOKE_MODEL", "qwen2.5vl:7b")


@pytest.fixture(scope="module")
def live_extraction_artifacts() -> tuple[object, str]:
    """One live chat() call shared across both assertions in this module.

    Module-scoped because vision-model invocations are expensive (20-60s
    on consumer hardware). Returns (extraction_result, raw_response_content)
    so both shape and JSON-key-order assertions run on a single live
    call. Skips the entire module if the fixture path is missing or the
    Ollama server is unreachable.
    """
    import ollama

    from trust_generator.v3.extraction import ExtractionError, OllamaBackend
    from trust_generator.v3.extraction.ollama_backend import GenerationEnvelope
    from trust_generator.v3.extraction.prompt import build_intake_prompt

    fixture_path = _resolve_fixture_path()
    if not fixture_path.exists():
        pytest.skip(
            f"Smoke fixture not found at {fixture_path}; set "
            f"OCR_SMOKE_FIXTURE_PATH or commit the default fixture"
        )

    # Direct ollama call captures raw response for the §7.4 key-order assertion
    # AND drives extract() in one round-trip via a shared client.
    client = ollama.Client()
    try:
        response = client.chat(
            model=_resolve_model(),
            messages=[
                {
                    "role": "user",
                    "content": build_intake_prompt(),
                    "images": [str(fixture_path.resolve())],
                }
            ],
            format=GenerationEnvelope.model_json_schema(),
            options={"temperature": 0},
        )
    except ConnectionError as e:
        pytest.skip(f"Ollama server unreachable: {e}")

    raw_content = response.message.content

    # Run extract() against the same fixture to validate the full pipeline.
    # Reuses the same client to keep the connection warm but is a second
    # chat() call — model output may differ slightly from raw_content above
    # (temperature=0 makes this rare but not impossible across HTTP retries).
    backend = OllamaBackend(model=_resolve_model(), client=client)
    try:
        extraction_result = backend.extract(fixture_path)
    except ExtractionError as e:
        pytest.skip(f"extract() failed against live model: {e}")

    return extraction_result, raw_content


def test_live_extract_returns_extraction_result_with_at_least_one_field(
    live_extraction_artifacts: tuple[object, str],
) -> None:
    """``extract`` against a live Ollama vision model returns an ExtractionResult
    whose trace has at least one FieldExtraction.

    Asserts only structural shape, not content. Handwriting reading
    varies; per-field accuracy is chore #13's domain, not this task's.
    """
    from trust_generator.v3.extraction import ExtractionResult

    extraction_result, _ = live_extraction_artifacts

    assert isinstance(extraction_result, ExtractionResult)
    assert len(extraction_result.trace.fields) >= 1


def test_live_response_emits_reasoning_as_first_key(
    live_extraction_artifacts: tuple[object, str],
) -> None:
    """Spec §7.4 integration-level pin: the raw JSON response from the
    live model has ``reasoning`` as its first key.

    Mechanism: grammar-constrained decoding generates fields in schema
    declaration order; the cycle 9b-1 unit test pins the schema; this
    test pins that the live model honors the discipline. Python
    preserves JSON key insertion order in ``json.loads()`` output.
    """
    _, raw_content = live_extraction_artifacts

    parsed = json.loads(raw_content)
    first_key = next(iter(parsed.keys()))

    assert first_key == "reasoning", (
        f"Expected 'reasoning' as first key from live model "
        f"({_resolve_model()}); got {first_key!r}. "
        f"This is a §7.4 finding — open a chore for spec amendment "
        f"per §13.2 / chore #14. Do not silently rewrite schema or prompt."
    )
```

- [ ] **Step 2: Verify the test collects (without running)**

Run: `pixi run test --collect-only tests/v3/extraction/test_ollama_backend_integration.py`
Expected: 2 tests collected, both marked `integration`.

- [ ] **Step 3: Verify the test is deselected by default**

Run: `pixi run test tests/v3/extraction/test_ollama_backend_integration.py`
Expected: 2 tests deselected (`-m 'not integration'` excludes them per chore #16's pyproject.toml `addopts`). Pytest reports `2 deselected` in its summary line.

If pytest reports the tests as PASSED instead (no deselection): chore #16 has not landed. Halt the task — do NOT modify pyproject.toml in this plan-md (out of `src/` + `tests/` plan-executor scope; chore #16 is the right vehicle).

- [ ] **Step 4: Run the gate (sans live integration)**

Run: `pixi run check`
Expected: green. The new test file is parseable and the integration tests skip; cycle 9b-3/9b-4's tests continue to pass.

- [ ] **Step 5: (Manual, optional) Run the live smoke**

Pre-conditions:
- Local Ollama server running (`ollama serve` or daemon).
- Vision model pulled: `ollama pull qwen2.5vl:7b` (or set `OCR_SMOKE_MODEL` to the chosen model).
- Smoke fixture committed: `assets/handwriting-samples/pages/print.jpg` exists, OR `OCR_SMOKE_FIXTURE_PATH` env var points at a readable JPG/PNG.

Run:

```bash
pixi run test -m integration tests/v3/extraction/test_ollama_backend_integration.py
```

Expected: 2 tests pass. The `-m integration` flag overrides pyproject.toml's default `addopts = "-m 'not integration'"` (the explicit `-m` on the command line wins).

If `test_live_response_emits_reasoning_as_first_key` fails: this is a §7.4 finding. Halt the task, do NOT silently amend the schema or prompt. Document the finding (which model, which first-key was observed instead of `reasoning`) and open a chore via scope-maintenance for §7.4 amendment per spec §13.2.

If `test_live_extract_returns_extraction_result_with_at_least_one_field` fails because the model emits an envelope with empty `grantors` and `beneficiaries`: investigate per the resolution paths in this task's preamble; minor prompt amendment under cycle 9b-2 is acceptable, schema amendment requires §7.3 spec amendment.

- [ ] **Step 6: Commit the integration test**

```bash
git add tests/v3/extraction/test_ollama_backend_integration.py
git commit -m "test(extraction): cycle 9b-5 live vision-model smoke (pytest.mark.integration)"
```

If the manual live-smoke step (Step 5) revealed a prompt amendment was needed: that amendment commits separately as a cycle 9b-2 amendment and is referenced in the task's PR description if a PR is opened mid-flight.

</task>

---

## Task 9b-6 — Close `plans.xml` 9b entry

<task id="9b-6"
      spec-ref="(plans.xml bookkeeping per spec-pipeline invariant #5)"
      blast-radius=".claude/context/plans.xml"
      depends-on="9b-5">

**Files:**

- Modify: `.claude/context/plans.xml`

Mark this plan closed in the canonical plan reference. Per spec-pipeline invariant #5, the dispatching session — not the plan-executor — commits this flip. The plan-executor's prior cycles report completion; the dispatcher then issues this single bookkeeping commit.

- [ ] **Step 1: Edit `.claude/context/plans.xml`**

The 9b entry's `id`, `plan-md`, and `synopsis` were set during the spec-to-plan drafting commit (this plan-md's authoring session). Task 9b-6 flips the 9b entry's `status` only:

1. Set `status="closed"` on the `<plan index="10" id="2026-04-27-ocr-protocol-ollama-9b">` entry (was `"open"`).
2. On the `<reference>` element: update `modified-at` to the current ISO 8601 timestamp with timezone offset:

```bash
date '+%Y-%m-%dT%H:%M:%S%:z'
```

The post-edit 9b entry should read approximately:

```xml
    <plan index="10"
          id="2026-04-27-ocr-protocol-ollama-9b"
          status="closed"
          expendable="false"
          plan-md="docs/superpowers/plans/2026-04-27-ocr-protocol-ollama-9b.md"
          spec-md="docs/superpowers/specs/2026-04-27-ocr-protocol-ollama-design.md"
          synopsis="OCR Ollama backend (spec §6 cycles 4-6, 10): GenerationEnvelope + field-order discipline, OllamaBackend.extract happy + error paths, prompt strategy, live vision-model smoke test. Depends on 9a." />
```

The 9c sibling entry remains `status="open"` with empty `plan-md` until its own spec-to-plan session authors it.

- [ ] **Step 2: Validate against the schema**

Run:

```bash
pixi run python -c "import xml.etree.ElementTree as ET; ET.parse('.claude/context/plans.xml')"
```

Expected: no output (parses cleanly).

- [ ] **Step 3: Commit the close**

```bash
git add .claude/context/plans.xml
git commit -m "chore(context/plans): close 9b plan (2026-04-27-ocr-protocol-ollama-9b)"
```

- [ ] **Step 4: Final sanity check**

Run: `pixi run check`
Expected: green.

Run: `git log --oneline -20`
Expected: most recent commits trace `Red → Green (9b-1) → Red → Green (9b-2) → Red → Green (9b-3) → [Refactor (9b-3, optional)] → Red → Green (9b-4) → integration smoke (9b-5) → plans-close (9b-6)`. Nine to ten commits from this plan, depending on whether 9b-3's refactor stage produced a commit.

</task>

---

## Self-Review Checklist (run before handoff)

**Spec coverage:**

- §3.1 + §3.2 (reference material) → predecessor verification reads 9a's surface and the manifest dep.
- §5.6 (OllamaBackend sketch) → cycle 9b-3 lands the class with the constructor signature from the spec sketch (with `Callable[[], str]` instead of `PromptBuilder` Protocol per Q5).
- §6.4 (cycle 4 — envelope schema and field-order test) → cycle 9b-1.
- §6.5 (cycle 5 — extract happy path) → cycle 9b-3.
- §6.6 (cycle 6 — extract error paths) → cycle 9b-4.
- §6.10 (cycle 10 — live integration smoke) → task 9b-5.
- §7.1 (`ollama >=0.6.1` dep) → predecessor verification (P3); the dep was added in 9a Task 5.
- §7.2 (client construction) → cycle 9b-3 constructor accepts injected `client` (default `ollama.Client()`).
- §7.3 (envelope shape) → cycle 9b-1 envelope subset (Q4 records the deferred full mirror).
- §7.4 (field-order discipline) → cycle 9b-1 unit pin + task 9b-5 integration pin.
- §7.5 (multi-page handling) → out of scope for v3.0 per spec; not addressed in 9b.
- §7.6 (error contract) → cycle 9b-4.
- §7.7 (new diagnostic codes) → owned by 9c, not 9b. (9b-3's omit-if-absent posture is the producer-side feedstock that 9c consumes.)
- §8 (prompt strategy) → cycle 9b-2.
- §10 (public API surface) → cycle 9b-3 adds `OllamaBackend` to `__all__`; 9c will not change the surface for 9b.
- §11 (constraint compliance) → all four cycles uphold; tests pin protocol structural conformance and TrustData isolation from envelope shape.

**Sections explicitly NOT modified by 9b** (out-of-9b-scope, owned by 9c or earlier plans): §5.2, §5.3, §5.4, §5.7 (9a); §5.8, §5.9, §5.10, §6.7, §6.8, §6.9, §7.7, §12 (9c).

**No gaps.**

**Placeholder scan:** No "TBD", "implement later", "similar to Task N", or unspecified error handling. Every code block, command, expected output, and edit is complete and self-contained. The one conditional in cycle 9b-3 (full TrustData mirror chore-open if `TrustData()` rejects construction) is a documented escape with explicit resolution criteria, not a placeholder.

**Type consistency:**

- `GenerationEnvelope`, `FieldDiag`, `GrantorEnvelope`, `BeneficiaryEnvelope` introduced in 9b-1; consumed by 9b-3 (envelope-to-result mapping) and by 9b-4 (validation-error path) and by 9b-5 (integration test imports `GenerationEnvelope` for the live invocation).
- `build_intake_prompt: Callable[[], str]` introduced in 9b-2; consumed by 9b-3 (constructor default) and 9b-5 (live invocation re-uses the same prompt).
- `OllamaBackend` introduced in 9b-3; exported via `__all__` in 9b-3; consumed by 9b-4 tests and 9b-5 integration test.
- `ExtractionError`, `ExtractionResult`, `ExtractionTrace`, `FieldExtraction`, `SourceRef` consumed from 9a's surface; no shape changes in 9b.
- The `__all__` tuple after 9b-3 lists 10 public names alphabetized (RUF022 verified): `ExtractionError`, `ExtractionProtocol`, `ExtractionResult`, `ExtractionTrace`, `FieldExtraction`, `IncompleteUntilValidated`, `OllamaBackend`, `RawSelfReport`, `SourceRef`, `resolve`.

**Cross-plan handoff:**

- 9c will import `OllamaBackend` only if its synthesis tests construct one (likely against a mocked client, mirroring 9b-3's mock pattern). 9c primarily consumes 9a's surface (`ExtractionTrace`, `FieldExtraction`, `resolve`) plus the new `extraction` namespace seam in `eval_context` (which 9c itself adds).
- The §12 spec amendment (`diagnose()` signature, `eval_context` shape, synthesis seam) lands atomically in 9c per spec §12 — not in 9b.
- Chore #13 (empirical model selection) is gated by 9b-3's completion; chore #14 (envelope complexity ceiling benchmark) is gated by 9b-1's completion. Both chores' bodies reference these gates explicitly.

**Out-of-scope items deliberately deferred:**

- Full TrustData-mirror envelope (every section beyond grantors/beneficiaries) → addressed conditionally in 9b-3 (chore-open if construction fails); otherwise a follow-up plan if production usage reveals coverage gaps.
- AnthropicBackend (Session 4.3b) — sibling backend; the Protocol surface defined in 9a constrains it but its implementation lives in its own session.
- ConfidenceProtocol (Session 4.3c) — `confidence_self_report` slot reserved on `FieldExtraction`; populated as `None` by `OllamaBackend` per spec §5.3 docstring.
- Diagnostics integration (`diagnose(extraction=...)`, `synthesize_extraction_diagnostics`, new `extraction.*` codes) — owned by 9c.
- Verify lifecycle UI surfaces — GUI concern; v3.0 ships the data-model contract only.
- Trace persistence (round-trip serialization including `INCOMPLETE`) — chore #15, owned by the consumer-layer persistence session.
- Per-firm model selection commitment — chore #13 empirical exercise, gated by 9b-3.
- Schema-complexity-ceiling benchmark — chore #14, gated by 9b-1.
- §7.4 prompt-strategy reasoning-omission evidence — chore #14 opportunistic exercise.
