# OCR Extraction Core (9a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Cycle blocks are XML-tagged for dispatcher-side cycle-scope addressing — see "Dispatch Protocol" below.

**Goal:** Land §5.2 (markers), §5.3 (trace types), §5.4 (Protocol), §5.7 (paths resolver) from the OCR spec — the pure-data foundation that 9b (OllamaBackend) and 9c (diagnostics integration) consume.

**Architecture:** Five new modules under a fresh `src/trust_generator/v3/extraction/` package plus mirrored tests under `tests/v3/extraction/`. Four Red/Green TDD cycles, one mechanical dep-add task, one plans-close task. No `src/` change touches any existing v3 module; no consumer of these surfaces lands in 9a (consumers are 9b's `OllamaBackend.extract` and 9c's `diagnose()` integration).

**Tech Stack:** Python 3.12, Pydantic v2, `ollama >= 0.6.1` (dep added in Task 5; first imported in 9b). All other deps already present from prior plans.

**Spec source:** `docs/superpowers/specs/2026-04-27-ocr-protocol-ollama-design.md` (§§3.1-3.2 reference material; §5.2 markers; §5.3 trace; §5.4 Protocol; §5.7 paths; §6.1-6.3 cycles 1-3 verbatim; §7.1 `ollama` floor `>=0.6.1`; §11 constraint compliance). Sections §5.6 (OllamaBackend), §5.8-5.10 (synthesis / eval_context / verify lifecycle), §6.4-6.10 (cycles 4-10), §7.2-7.7, §8 (prompt), §12 (spec amendment) are owned by 9b/9c and are NOT modified by this plan.

**Plan-composition decisions recorded:**

- **Q1 — Spec scope split: 9a / 9b / 9c.** Per `reject-monolithic-scopes` (CLAUDE.md), the spec's 11+ production-file footprint and 10 cycles exceed the hard-deny threshold for a single plan. Split along the spec's natural seams — 9a (data + Protocol + paths), 9b (OllamaBackend + dep + prompt + live smoke test), 9c (synthesis + diagnose() integration + override + spec amendment). 9a is foundational; 9b and 9c are independent sibling plans rooted on 9a's surface. This plan-md is **9a only**; 9b and 9c are separate `plans.xml` entries with their own spec-to-plan sessions.

- **Q2 — Spec amendment landing site: 9c, not a separate predecessor.** The OCR spec's §12 is explicit: amendments to `2026-04-23-diagnostics-engine-design.md` "land as part of this implementation's PR, not as a separate prior session" — sequencing them as a predecessor would create a window during which `diagnose()` has the new signature with no exercising caller. 9c will land the spec amendment atomically with its synthesis-and-integration work.

- **Q3 — `ollama >= 0.6.1` added in 9a (Task 5), not deferred to 9b.** The dep is mechanically harmless to add early (no source consumer until 9b cycle 5), unifies the dependency floor across all three sibling plans, and means 9c's tests can import the dep transitively without retroactive `pixi install` dance. Cost: `pixi.toml` and `pyproject.toml` carry an unused dep through the 9c-only window if 9c lands first; benefit: dep-version drift between sibling plans is impossible.

- **Q4 — Cycle-id format `9a-N`; dispatcher scope-token `cycles=[9a-N]` / range form `cycles=[9a-N..9a-M]`.** Plan-suffix + dash + ordinal (e.g., `9a-1`, `9a-2`) keeps cycle ids terse within a plan and Python-list-shaped scope tokens look identical for one cycle, several cycles, or a range. Convention is documented in "Dispatch Protocol" below and binds 9b/9c when those plan-mds are authored.

- **Q5 — Protocol module (`protocol.py`) gets its own cycle 9a-4, factored out of spec cycle 6.5.** The OCR spec embeds the `ExtractionProtocol` structural-conformance test inside cycle 5 (OllamaBackend.extract happy path) — but the Protocol surface itself is a pure 9a concern (no Ollama dependency). Lifting it to its own cycle in 9a (a) keeps all four 9a modules under one plan's blast radius, (b) lets 9b's cycle 5 assume the Protocol exists rather than constructing it mid-extract, (c) gives `ExtractionError` and `SourceRef` a clean Red/Green of their own. The structural-conformance assertion against `OllamaBackend` instances stays in 9b cycle 5 where it belongs (its target class doesn't exist yet in 9a).

- **Q6 — Tests use positional pixi-task arguments, not `name=value`.** Per chore index 7 (`2026-04-26-diagnostics-core-plan-md-staleness`), `pixi run test match=foo` is silently treated as a literal positional arg matching no tests. Correct form: `pixi run test test_markers`. This plan-md uses the correct form throughout. Same applies to `pixi run mypy v3/extraction` (positional `target`, not `target=...`).

- **Q7 — Trace persistence (round-tripping `INCOMPLETE` through `model_dump_json()`) is deferred.** Per spec §6.2 Refactor note and chore index 15 (`2026-04-27-trace-persistence-serialization-contract`), v3.0 ships `INCOMPLETE` as an in-memory-identity-only sentinel. 9a does NOT add a custom serializer/validator pair; tests assert in-memory identity only.

- **Q8 — Scope sits at the soft-warn boundary.** 9a touches 5 new src files + 5 new test files + 3 modified manifest/index files = 13 file paths. The CLAUDE.md soft-warn threshold is 5 different files / 2 complex tasks; the hard-deny is 10 / 5. 9a's logical complexity is 4 cycles + 2 mechanical tasks, all narrowly scoped to a fresh package; this is below the hard-deny on complexity even though file count is above it. Recorded so future readers see the scope was considered and accepted.

---

## Dispatch Protocol

When invoking `/spec-pipeline 2026-04-27-ocr-protocol-ollama-9a exec-plan`, the dispatcher (you, or a routing skill) controls which cycles execute via a scope-token in the dispatcher prompt:

| Scope-token | Effect |
| ----------- | ------ |
| (no scope-token, or `cycles=all`)            | Plan-executor walks `<cycle>` blocks in document order, executing each per-cycle Red→Green→(optional Refactor). |
| `cycles=[9a-2]`                              | Plan-executor opens only the cycle whose `id` attribute matches; verifies `depends-on` cycles' Green commits exist via `git log --grep`; executes Red→Green→(optional Refactor) for that cycle alone. |
| `cycles=[9a-2..9a-4]` (inclusive range)      | Plan-executor walks the contiguous cycle range; same dependency check at the range's lower bound. |
| `cycles=[9a-1, 9a-3]` (explicit list)         | Plan-executor walks each id in the order supplied. Use sparingly — non-contiguous execution risks skipping a `depends-on` link. |

Each `<cycle>` block carries five attributes the plan-executor honors:

| Attribute        | Purpose                                                                                     |
| ---------------- | ------------------------------------------------------------------------------------------- |
| `id`             | Stable scope token (`9a-1`, …, `9a-4`). Referenced by the dispatcher's `cycles=[…]` arg.    |
| `spec-ref`       | Backlink to the spec section(s) the cycle implements (e.g., `§5.2, §6.1`).                  |
| `blast-radius`   | Semicolon-separated list of file paths the cycle is allowed to create or modify. Plan-executor must NOT edit any path outside this list during the cycle; new paths surfaced at green-time become chores via scope-maintenance. |
| `depends-on`     | Cycle-id list whose Green commits must already exist. `none` for cycle 1.                   |
| `commits`        | The cycle's commit shape — `red,green` (default) or `red,green,refactor` when warranted.    |

Tasks 5 and 6 are not cycles — they are mechanical (Task 5: dep manifest change, single commit) and bookkeeping (Task 6: `plans.xml` status flip, single commit). They have a `<task>` block instead, with the same attributes (minus `commits`, which is implicitly one commit each).

The dispatching session retains responsibility for the post-execution close-out (review chore-list, commit `plans.xml` flip — invariant #5 in spec-pipeline SKILL.md).

---

## File Structure

**Created (production):**

| Path | Responsibility |
| ---- | -------------- |
| `src/trust_generator/v3/extraction/__init__.py` | Package init; declares `__all__` listing the public surface (markers, trace types, INCOMPLETE, Protocol, SourceRef, ExtractionError). No re-export logic in 9a beyond the `__all__` tuple. |
| `src/trust_generator/v3/extraction/markers.py` | `IncompleteUntilValidated`, `RawSelfReport` marker classes (per spec §5.2). |
| `src/trust_generator/v3/extraction/trace.py` | `INCOMPLETE` sentinel, `FieldExtraction`, `ExtractionTrace`, `ExtractionResult` (per spec §5.3). |
| `src/trust_generator/v3/extraction/paths.py` | `resolve(trust, field_path) -> tuple[bool, object]` (per spec §5.7). |
| `src/trust_generator/v3/extraction/protocol.py` | `SourceRef` PEP 695 alias, `ExtractionError`, `ExtractionProtocol` Protocol class (per spec §5.4). |

**Created (tests):**

| Path | Responsibility |
| ---- | -------------- |
| `tests/v3/extraction/__init__.py` | Empty file to make `tests/v3/extraction/` a package (mirrors `tests/v3/diagnostics/` convention). |
| `tests/v3/extraction/conftest.py` | `extraction_trace_factory` fixture builder (used by 9a-2, 9a-4 tests; reused by 9c synthesis tests). |
| `tests/v3/extraction/test_markers.py` | Cycle 9a-1 tests. |
| `tests/v3/extraction/test_trace.py` | Cycle 9a-2 tests. |
| `tests/v3/extraction/test_paths.py` | Cycle 9a-3 tests. |
| `tests/v3/extraction/test_protocol.py` | Cycle 9a-4 tests. |

**Modified (manifests):**

| Path | Change |
| ---- | ------ |
| `pyproject.toml` | Append `"ollama>=0.6.1"` to `[project].dependencies`. |
| `pixi.toml` | Append `ollama = '>=0.6.1'` to `[pypi-dependencies]` and to `[package.run-dependencies]`. |

**Modified (metadata):**

| Path | Change |
| ---- | ------ |
| `.claude/context/plans.xml` | Set `status="closed"` on the 9a entry; set `plan-md` attribute to this file's path; bump `modified-at`. |

**Total touched files:** 13 (5 new src, 6 new tests including `__init__.py` + conftest, 2 modified manifests, 1 modified metadata). See Q8 above.

---

## Predecessor verification (run once before any cycle)

This is gating, not implementing. If any check fails, escalate — the OCR core cannot proceed without the v3 base.

- [ ] **Step P1: Verify the v3 schema package is importable**

Run: `pixi run python -c "from trust_generator.v3.schema import TrustData, GrantorInfo, TrustIdentity; print('ok')"`
Expected: `ok` (no traceback). If `ImportError`: the schema module has drifted; halt and reconcile.

- [ ] **Step P2: Verify the project gate is green pre-cycle**

Run: `pixi run check`
Expected: lint passes, mypy passes, all tests pass. Exit code 0.
If non-green: halt — 9a starts from a green baseline so each cycle's red/green delta is unambiguous.

- [ ] **Step P3: Verify the extraction package does NOT yet exist**

Run: `ls src/trust_generator/v3/extraction 2>&1`
Expected: `ls: cannot access ...: No such file or directory`.
If the directory exists with content: investigate before proceeding — another effort may have started 9a.

- [ ] **Step P4: Verify the current branch is a feature branch**

Run: `git branch --show-current`
Expected: a branch name that is NOT `main`. The current working branch (per session start: `v3.0.0`) is fine.
If on `main`: halt and create or switch to a feature branch (per spec-pipeline invariant #10).

---

## Cycle 9a-1 — Marker classes and `INCOMPLETE` sentinel

<cycle id="9a-1"
       spec-ref="§5.2, §6.1"
       blast-radius="src/trust_generator/v3/extraction/__init__.py; src/trust_generator/v3/extraction/markers.py; src/trust_generator/v3/extraction/trace.py; tests/v3/extraction/__init__.py; tests/v3/extraction/test_markers.py"
       depends-on="none"
       commits="red,green">

**Files:**

- Create: `src/trust_generator/v3/extraction/__init__.py`
- Create: `src/trust_generator/v3/extraction/markers.py`
- Create: `src/trust_generator/v3/extraction/trace.py` (only `INCOMPLETE` for now; the BaseModel classes land in cycle 9a-2)
- Create: `tests/v3/extraction/__init__.py` (empty)
- Create: `tests/v3/extraction/test_markers.py`

The two marker classes are pure type-level vocabulary: each carries a `__doc__` describing its contract. `INCOMPLETE` is a module-level identity sentinel — compared with `is`, never with `==`. Cycle-1 tests assert importability, contract docstrings, and identity-distinctness.

The `__init__.py` lands in this cycle (vs. delaying to cycle 9a-4) because once the package directory exists (created when `markers.py` is written), Python treats it as an implicit namespace package without one — and `pixi run check` runs ruff and mypy across the new directory immediately. The `__init__.py` declares `__all__ = ()` initially; subsequent cycles append exports as their symbols land.

- [ ] **Step 1: Author the failing test (Red)**

Create `tests/v3/extraction/__init__.py` (empty file).

Create `tests/v3/extraction/test_markers.py`:

```python
"""Cycle 9a-1 tests — marker classes and INCOMPLETE sentinel."""

from __future__ import annotations


def test_incomplete_until_validated_importable() -> None:
    """``IncompleteUntilValidated`` is importable from the markers module."""
    from trust_generator.v3.extraction.markers import IncompleteUntilValidated

    assert IncompleteUntilValidated.__name__ == "IncompleteUntilValidated"


def test_incomplete_until_validated_has_contract_docstring() -> None:
    """``IncompleteUntilValidated`` carries a non-empty docstring describing its contract."""
    from trust_generator.v3.extraction.markers import IncompleteUntilValidated

    assert IncompleteUntilValidated.__doc__ is not None
    assert IncompleteUntilValidated.__doc__.strip() != ""


def test_raw_self_report_importable() -> None:
    """``RawSelfReport`` is importable from the markers module."""
    from trust_generator.v3.extraction.markers import RawSelfReport

    assert RawSelfReport.__name__ == "RawSelfReport"


def test_raw_self_report_has_contract_docstring() -> None:
    """``RawSelfReport`` carries a non-empty docstring describing its contract."""
    from trust_generator.v3.extraction.markers import RawSelfReport

    assert RawSelfReport.__doc__ is not None
    assert RawSelfReport.__doc__.strip() != ""


def test_incomplete_sentinel_importable() -> None:
    """``INCOMPLETE`` is importable from the trace module."""
    from trust_generator.v3.extraction.trace import INCOMPLETE

    assert INCOMPLETE is not None


def test_incomplete_sentinel_identity_distinct() -> None:
    """``INCOMPLETE`` is identity-distinct from None, 0, '', and ()."""
    from trust_generator.v3.extraction.trace import INCOMPLETE

    assert INCOMPLETE is not None
    assert INCOMPLETE is not 0  # noqa: F632 — identity check is the assertion
    assert INCOMPLETE is not ""  # noqa: F632
    assert INCOMPLETE is not ()  # noqa: F632


def test_incomplete_sentinel_not_in_dunder_all() -> None:
    """``INCOMPLETE`` is not exported via ``trace.__all__`` (per spec §5.3 docstring).

    Consumers must import the sentinel explicitly to make the discipline visible.
    """
    from trust_generator.v3.extraction import trace

    assert "INCOMPLETE" not in getattr(trace, "__all__", ())
```

- [ ] **Step 2: Run the test to confirm Red**

Run: `pixi run test test_markers`
Expected: 7 tests fail with `ModuleNotFoundError: No module named 'trust_generator.v3.extraction'`.
If a different error: investigate — the import path may be off.

- [ ] **Step 3: Author the production code (Green)**

Create `src/trust_generator/v3/extraction/__init__.py`:

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

__all__ = (
    "IncompleteUntilValidated",
    "RawSelfReport",
)
```

Create `src/trust_generator/v3/extraction/markers.py`:

```python
"""Type-level marker classes for the OCR extraction surface (spec §5.2)."""

from __future__ import annotations


class IncompleteUntilValidated:
    """Type-level marker on ``FieldExtraction.normalized_value``.

    Indicates the value has not been validated against its target
    TrustData field's type and may not satisfy that field's constraints.
    Consumers MUST narrow via isinstance against the target type before
    use. The field's static type is ``object``, which makes this
    discipline visible to type checkers.
    """


class RawSelfReport:
    """Type-level marker on ``FieldExtraction.confidence_self_report``.

    Indicates the value is the model's own first-order confidence report
    in [0.0, 1.0], with no calibration applied. Consumers requiring
    calibrated confidence MUST route the value through a
    ``ConfidenceProtocol`` implementation (Session 4.3c). Both readers
    and producers must respect this marker; any future calibrated
    channel receives a sibling marker (e.g., ``Calibrated``) and a
    separate field.
    """
```

Create `src/trust_generator/v3/extraction/trace.py`:

```python
"""ExtractionTrace, FieldExtraction, ExtractionResult, INCOMPLETE sentinel.

IMPORTANT: This module embodies the v3.0 commitment to Approach B'
(free generation with structurally constrained diagnostics, sidecar
form). See spec §7.4 for the rationale: the generation envelope (the
model's Pydantic output schema) reserves a string-typed ``reasoning``
field that is declared first to materialize the chain-of-thought
benefit under grammar-constrained decoding. This is the current
best-practice posture for grammar-constrained generation; reordering or
removing it is plausible-only-with-evidence (chore index 14 —
``2026-04-27-envelope-complexity-ceiling-benchmark`` — is the gathering
point). Do not move it without re-reading §7.4 and the field-order test
in §6.4.

IMPORTANT: Schema complexity ceiling under constrained decoding —
small models can produce unexpected EOF errors on complex schemas. If
this surfaces in production, consult §7.5 (chunked extraction) and the
in-flight chore index 14 before changing this module's shape.
"""

from __future__ import annotations

from typing import Final

INCOMPLETE: Final[object] = object()
"""Module-level sentinel for ``FieldExtraction.normalized_value`` when
extraction completed but normalization against the target TrustData
field type has not yet been validated.

Compared via identity (``field.normalized_value is INCOMPLETE``), never
by equality. The sentinel is not exported via ``__all__``; consumers
import it explicitly.
"""

__all__: tuple[str, ...] = ()
```

The two module-level docstring blocks (the Approach B' rationale and the schema-complexity-ceiling pointer) satisfy the spec §2 "persistence in code" requirement — they reference chore index 14 by name so the constraint surfaces during any future schema modification. The same comment lands at the top of `ollama_backend.py` in 9b cycle 4 per spec §2.

- [ ] **Step 4: Run the test to confirm Green**

Run: `pixi run test test_markers`
Expected: 7 tests pass.

- [ ] **Step 5: Run the project gate**

Run: `pixi run check`
Expected: green (lint + mypy + all tests). The new package adds zero coupling to existing v3 code.

- [ ] **Step 6: Commit Red and Green as one cycle's worth**

Per project convention (TDD, Red commit + Green commit), commit them separately:

```bash
git add tests/v3/extraction/__init__.py tests/v3/extraction/test_markers.py
git commit -m "test(extraction): RED — cycle 9a-1 marker classes and INCOMPLETE sentinel"
```

Then:

```bash
git add src/trust_generator/v3/extraction/__init__.py \
        src/trust_generator/v3/extraction/markers.py \
        src/trust_generator/v3/extraction/trace.py
git commit -m "feat(extraction): GREEN — cycle 9a-1 marker classes and INCOMPLETE sentinel"
```

If the plan-executor agent prefers staging Red+Green into a single working tree before committing (writing both files, then issuing two `git add` + `git commit` calls in sequence) that is acceptable — the final `git log` shows two distinct commits regardless.

</cycle>

---

## Cycle 9a-2 — `FieldExtraction`, `ExtractionTrace`, `ExtractionResult`

<cycle id="9a-2"
       spec-ref="§5.3, §6.2"
       blast-radius="src/trust_generator/v3/extraction/__init__.py; src/trust_generator/v3/extraction/trace.py; tests/v3/extraction/conftest.py; tests/v3/extraction/test_trace.py"
       depends-on="9a-1"
       commits="red,green">

**Files:**

- Modify: `src/trust_generator/v3/extraction/__init__.py` (extend `__all__` with the three BaseModel names)
- Modify: `src/trust_generator/v3/extraction/trace.py` (add `FieldExtraction`, `ExtractionTrace`, `ExtractionResult`)
- Create: `tests/v3/extraction/conftest.py`
- Create: `tests/v3/extraction/test_trace.py`

The trace types are Pydantic BaseModels with `extra="forbid"`. Three invariants land in this cycle:

1. **Illegibility / value mutual exclusion.** `illegible=True` AND `normalized_value is not None` is structurally invalid (per spec §5.3 docstring) — enforced by a `model_validator(mode="after")` raising `ValueError`.
2. **Verify-field uniqueness on lookup.** `ExtractionTrace.verify_field(path)` raises `KeyError` when no field matches; raises `ValueError` when multiple match (data-integrity invariant).
3. **`INCOMPLETE` identity preservation.** A `FieldExtraction(normalized_value=INCOMPLETE)` round-trip through the model preserves `field.normalized_value is INCOMPLETE` — Pydantic does not coerce or copy the sentinel.

Persistence (round-tripping `INCOMPLETE` through `model_dump_json()`) is deliberately not tested — per spec §6.2 Refactor note and chore 15, that contract belongs to the consumer-layer persistence session.

- [ ] **Step 1: Author the conftest fixture (preparatory; no test logic yet)**

Create `tests/v3/extraction/conftest.py`:

```python
"""Shared fixtures for OCR extraction cycle tests.

Reused by 9a-2 (trace), 9a-4 (protocol), and 9c (synthesis).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest

from trust_generator.v3.extraction.trace import (
    ExtractionTrace,
    FieldExtraction,
)


@pytest.fixture
def field_extraction_factory() -> Callable[..., FieldExtraction]:
    """Build a minimal FieldExtraction; kwargs override per-test."""

    def _build(**overrides: Any) -> FieldExtraction:
        defaults: dict[str, Any] = {
            "field_path": "grantor.full_legal_name",
            "raw_value": "Test Value",
            "normalized_value": None,
            "illegible": False,
            "confidence_self_report": None,
            "verified": False,
            "verified_at": None,
        }
        defaults.update(overrides)
        return FieldExtraction(**defaults)

    return _build


@pytest.fixture
def extraction_trace_factory(
    field_extraction_factory: Callable[..., FieldExtraction],
) -> Callable[..., ExtractionTrace]:
    """Build a minimal ExtractionTrace; kwargs override per-test."""

    def _build(**overrides: Any) -> ExtractionTrace:
        defaults: dict[str, Any] = {
            "fields": [],
            "backend_id": "test:test-model",
            "extracted_at": datetime(2026, 4, 28, tzinfo=UTC),
        }
        defaults.update(overrides)
        return ExtractionTrace(**defaults)

    return _build
```

- [ ] **Step 2: Author the failing tests (Red)**

Create `tests/v3/extraction/test_trace.py`:

```python
"""Cycle 9a-2 tests — FieldExtraction, ExtractionTrace, ExtractionResult."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from trust_generator.v3.extraction.trace import (
    INCOMPLETE,
    ExtractionResult,
    ExtractionTrace,
    FieldExtraction,
)
from trust_generator.v3.schema import TrustData


# --- FieldExtraction shape ---------------------------------------------------


def test_field_extraction_accepts_documented_fields(
    field_extraction_factory: Callable[..., FieldExtraction],
) -> None:
    """FieldExtraction accepts the documented field set with sensible defaults."""
    fe = field_extraction_factory()
    assert fe.field_path == "grantor.full_legal_name"
    assert fe.raw_value == "Test Value"
    assert fe.normalized_value is None
    assert fe.illegible is False
    assert fe.confidence_self_report is None
    assert fe.verified is False
    assert fe.verified_at is None


def test_field_extraction_rejects_unknown_fields() -> None:
    """``extra='forbid'`` rejects unexpected fields at construction."""
    with pytest.raises(ValidationError):
        FieldExtraction(
            field_path="grantor.full_legal_name",
            raw_value="x",
            unknown_field="boom",  # type: ignore[call-arg]
        )


def test_field_extraction_illegible_with_value_rejected() -> None:
    """Mutual-exclusion invariant: illegible=True + non-None normalized_value rejected."""
    with pytest.raises(ValidationError) as exc_info:
        FieldExtraction(
            field_path="grantor.full_legal_name",
            raw_value="x",
            illegible=True,
            normalized_value="some-value",
        )
    msg = str(exc_info.value)
    assert "illegible" in msg.lower()


def test_field_extraction_illegible_with_none_value_accepted() -> None:
    """Mutual-exclusion invariant: illegible=True + normalized_value=None is fine."""
    fe = FieldExtraction(
        field_path="grantor.full_legal_name",
        raw_value="?",
        illegible=True,
        normalized_value=None,
    )
    assert fe.illegible is True
    assert fe.normalized_value is None


def test_field_extraction_incomplete_sentinel_identity_preserved() -> None:
    """FieldExtraction accepts INCOMPLETE; identity survives in-memory round-trip."""
    fe = FieldExtraction(
        field_path="grantor.full_legal_name",
        raw_value="John Doe",
        normalized_value=INCOMPLETE,
    )
    assert fe.normalized_value is INCOMPLETE


# --- ExtractionTrace.verify_field -------------------------------------------


def test_verify_field_happy_path(
    field_extraction_factory: Callable[..., FieldExtraction],
    extraction_trace_factory: Callable[..., ExtractionTrace],
) -> None:
    """verify_field mutates only the matching FieldExtraction's verified+verified_at."""
    fe_a = field_extraction_factory(field_path="grantor.full_legal_name", raw_value="A")
    fe_b = field_extraction_factory(field_path="trust_id.desired_trust_name", raw_value="B")
    trace = extraction_trace_factory(fields=[fe_a, fe_b])

    at = datetime(2026, 4, 28, 12, 0, 0, tzinfo=UTC)
    trace.verify_field("grantor.full_legal_name", at=at)

    assert trace.fields[0].verified is True
    assert trace.fields[0].verified_at == at
    assert trace.fields[1].verified is False
    assert trace.fields[1].verified_at is None


def test_verify_field_default_at_uses_now(
    field_extraction_factory: Callable[..., FieldExtraction],
    extraction_trace_factory: Callable[..., ExtractionTrace],
) -> None:
    """verify_field's default ``at`` is datetime.now(UTC)."""
    fe = field_extraction_factory(field_path="grantor.full_legal_name", raw_value="A")
    trace = extraction_trace_factory(fields=[fe])

    before = datetime.now(UTC)
    trace.verify_field("grantor.full_legal_name")
    after = datetime.now(UTC)

    assert trace.fields[0].verified is True
    assert trace.fields[0].verified_at is not None
    assert before <= trace.fields[0].verified_at <= after


def test_verify_field_missing_path_raises_keyerror(
    extraction_trace_factory: Callable[..., ExtractionTrace],
) -> None:
    """verify_field raises KeyError for an unknown field_path."""
    trace = extraction_trace_factory(fields=[])
    with pytest.raises(KeyError):
        trace.verify_field("does.not.exist")


def test_verify_field_duplicate_path_raises_valueerror(
    field_extraction_factory: Callable[..., FieldExtraction],
    extraction_trace_factory: Callable[..., ExtractionTrace],
) -> None:
    """verify_field raises ValueError on duplicate field_path entries (data-integrity invariant)."""
    fe_dup_1 = field_extraction_factory(field_path="grantor.full_legal_name", raw_value="A")
    fe_dup_2 = field_extraction_factory(field_path="grantor.full_legal_name", raw_value="B")
    trace = extraction_trace_factory(fields=[fe_dup_1, fe_dup_2])

    with pytest.raises(ValueError, match="duplicate"):
        trace.verify_field("grantor.full_legal_name")


# --- ExtractionResult --------------------------------------------------------


def test_extraction_result_requires_data_and_trace(
    extraction_trace_factory: Callable[..., ExtractionTrace],
) -> None:
    """ExtractionResult requires both ``data`` and ``trace``."""
    with pytest.raises(ValidationError):
        ExtractionResult(data=TrustData())  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        ExtractionResult(trace=extraction_trace_factory())  # type: ignore[call-arg]


def test_extraction_result_accepts_data_and_trace(
    extraction_trace_factory: Callable[..., ExtractionTrace],
) -> None:
    """ExtractionResult round-trips a TrustData and a trace."""
    data = TrustData()
    trace = extraction_trace_factory()
    result = ExtractionResult(data=data, trace=trace)
    assert result.data is data
    assert result.trace is trace
```

- [ ] **Step 3: Run the tests to confirm Red**

Run: `pixi run test test_trace`
Expected: tests fail with `ImportError` on `ExtractionResult`, `ExtractionTrace`, or `FieldExtraction` — those names do not yet exist in `trace.py`.

- [ ] **Step 4: Author the production code (Green)**

Replace `src/trust_generator/v3/extraction/trace.py` with the full module (the existing INCOMPLETE block + new BaseModels):

```python
"""ExtractionTrace, FieldExtraction, ExtractionResult, INCOMPLETE sentinel.

IMPORTANT: This module embodies the v3.0 commitment to Approach B'
(free generation with structurally constrained diagnostics, sidecar
form). See spec §7.4 for the rationale: the generation envelope (the
model's Pydantic output schema) reserves a string-typed ``reasoning``
field that is declared first to materialize the chain-of-thought
benefit under grammar-constrained decoding. This is the current
best-practice posture for grammar-constrained generation; reordering or
removing it is plausible-only-with-evidence (chore index 14 —
``2026-04-27-envelope-complexity-ceiling-benchmark`` — is the gathering
point). Do not move it without re-reading §7.4 and the field-order test
in §6.4.

IMPORTANT: Schema complexity ceiling under constrained decoding —
small models can produce unexpected EOF errors on complex schemas. If
this surfaces in production, consult §7.5 (chunked extraction) and the
in-flight chore index 14 before changing this module's shape.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Final

from pydantic import BaseModel, ConfigDict, Field, model_validator

from trust_generator.v3.extraction.markers import (
    IncompleteUntilValidated,
    RawSelfReport,
)
from trust_generator.v3.schema import TrustData

INCOMPLETE: Final[object] = object()
"""Module-level sentinel for ``FieldExtraction.normalized_value`` when
extraction completed but normalization against the target TrustData
field type has not yet been validated.

Compared via identity (``field.normalized_value is INCOMPLETE``), never
by equality. The sentinel is not exported via ``__all__``; consumers
import it explicitly.
"""


class FieldExtraction(BaseModel):
    """A single per-field extraction record.

    ``field_path`` uses the dotted-path convention shared with
    ``Diagnostic.field_path`` (e.g., 'children[0].full_legal_name',
    'real_property[2].value'). The match is deliberate: a single
    convention across both surfaces keeps GUI anchor logic uniform.
    The path is resolved against the paired TrustData via
    ``extraction.paths.resolve`` at synthesis time; paths that no
    longer resolve are filtered as stale.

    ``field_path`` MUST be unique within an ``ExtractionTrace``
    (data-integrity invariant; ``verify_field`` raises ``ValueError``
    when duplicates are present).

    Verification is bound to the value at verify time. If ``TrustData``
    is mutated to a different value at the same path AFTER
    verification, the verification flag is not invalidated by the
    mutation; the trace remains a faithful record of "the paralegal
    confirmed this field was correct at the time of verification."
    Surfacing post-verification divergence to the paralegal is a
    consumer-layer (GUI/CLI) concern; the trace itself does not detect
    it.
    """

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    field_path: str
    raw_value: str
    normalized_value: Annotated[object, IncompleteUntilValidated] | None = None
    illegible: bool = False
    confidence_self_report: Annotated[float, RawSelfReport] | None = None
    verified: bool = False
    verified_at: datetime | None = None

    @model_validator(mode="after")
    def _illegible_excludes_normalized_value(self) -> FieldExtraction:
        """Reject illegible=True alongside a non-None normalized_value."""
        if self.illegible and self.normalized_value is not None:
            msg = (
                "FieldExtraction invariant violated: illegible=True is mutually "
                "exclusive with a non-None normalized_value (field_path="
                f"{self.field_path!r})"
            )
            raise ValueError(msg)
        return self


class ExtractionTrace(BaseModel):
    """A list of per-field extraction records produced by a single
    ``extract()`` call, with verify-mutation methods.

    The trace is the spine of the verification, provenance, and
    forward-compatible confidence architecture. It is paired with a
    ``TrustData`` (in ``ExtractionResult``) and consumed by
    ``diagnose()`` via the ``extraction`` namespace in eval_context
    (added in 9c).
    """

    model_config = ConfigDict(extra="forbid")

    fields: list[FieldExtraction] = Field(default_factory=list)
    backend_id: str
    """``<backend>:<model>`` convention (e.g., ``ollama:qwen2.5vl:7b``)."""
    extracted_at: datetime

    def verify_field(self, field_path: str, *, at: datetime | None = None) -> None:
        """Mark the field at ``field_path`` as verified.

        Raises ``KeyError`` if no FieldExtraction has a matching
        ``field_path``. Raises ``ValueError`` if multiple do
        (data-integrity invariant: ``field_path`` is unique within a
        trace).
        """
        matches = [fe for fe in self.fields if fe.field_path == field_path]
        if not matches:
            msg = f"no FieldExtraction matches field_path={field_path!r}"
            raise KeyError(msg)
        if len(matches) > 1:
            msg = (
                f"duplicate FieldExtraction entries for field_path={field_path!r}: "
                f"trace data-integrity invariant violated"
            )
            raise ValueError(msg)
        target = matches[0]
        target.verified = True
        target.verified_at = at if at is not None else datetime.now(UTC)


class ExtractionResult(BaseModel):
    """The pairing returned by every ``ExtractionProtocol.extract()`` call.

    Both fields are required.
    """

    model_config = ConfigDict(extra="forbid")

    data: TrustData
    trace: ExtractionTrace


__all__: tuple[str, ...] = (
    "ExtractionResult",
    "ExtractionTrace",
    "FieldExtraction",
)
```

Then extend `src/trust_generator/v3/extraction/__init__.py`:

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
from trust_generator.v3.extraction.trace import (
    ExtractionResult,
    ExtractionTrace,
    FieldExtraction,
)

__all__ = (
    "ExtractionResult",
    "ExtractionTrace",
    "FieldExtraction",
    "IncompleteUntilValidated",
    "RawSelfReport",
)
```

YAML/lint note: ruff's RUF022 will alphabetize the `__all__` tuple — the order above is already alphabetical, so the linter is a no-op. If a future reader adds a name out of order, `pixi run fix` will reorder it; trust the autofix.

The `arbitrary_types_allowed=True` on `FieldExtraction.model_config` is required because `normalized_value`'s `Annotated[object, IncompleteUntilValidated]` references a class Pydantic does not have a built-in schema for. The marker class is type-level vocabulary, not a runtime-validated type.

- [ ] **Step 5: Run the tests to confirm Green**

Run: `pixi run test test_trace`
Expected: 11 tests pass.

If `test_field_extraction_illegible_with_value_rejected` fails: confirm the `model_validator(mode="after")` is registered and raises `ValueError` (Pydantic surfaces it as `ValidationError` to the caller).

If `test_field_extraction_incomplete_sentinel_identity_preserved` fails: investigate — Pydantic v2 may have coerced the sentinel via its `object` schema. The `arbitrary_types_allowed=True` flag is what makes identity preservation possible.

If `test_verify_field_default_at_uses_now` flakes: the test bounds `before <= verified_at <= after` should be wide enough to absorb sub-millisecond drift; if not, widen the bracket.

- [ ] **Step 6: Run the project gate**

Run: `pixi run check`
Expected: green.

- [ ] **Step 7: Commit Red and Green**

```bash
git add tests/v3/extraction/conftest.py tests/v3/extraction/test_trace.py
git commit -m "test(extraction): RED — cycle 9a-2 FieldExtraction, ExtractionTrace, ExtractionResult"
```

```bash
git add src/trust_generator/v3/extraction/__init__.py src/trust_generator/v3/extraction/trace.py
git commit -m "feat(extraction): GREEN — cycle 9a-2 trace types with illegibility invariant and verify-field uniqueness"
```

</cycle>

---

## Cycle 9a-3 — Path resolver

<cycle id="9a-3"
       spec-ref="§5.7, §6.3"
       blast-radius="src/trust_generator/v3/extraction/__init__.py; src/trust_generator/v3/extraction/paths.py; tests/v3/extraction/test_paths.py"
       depends-on="9a-2"
       commits="red,green">

**Files:**

- Create: `src/trust_generator/v3/extraction/paths.py`
- Modify: `src/trust_generator/v3/extraction/__init__.py` (extend `__all__` with `resolve`)
- Create: `tests/v3/extraction/test_paths.py`

`resolve(trust, field_path) -> tuple[bool, object]` walks a dotted-path string against a TrustData:

- attribute access: `grantor`, `office.file_number`
- bracket indexing: `children[0]`
- chains: `children[0].full_legal_name`

The function returns `(False, None)` on any unresolvable path — out-of-range index, missing attribute, malformed input — rather than raising. Pathological inputs (empty string, trailing dot, malformed bracket) all fall into the same `(False, None)` bucket; the caller decides whether to filter or surface.

This is small and reusable: it serves trace-driven Diagnostic synthesis (in 9c) and any future feature mapping `field_path` strings to TrustData values.

- [ ] **Step 1: Author the failing tests (Red)**

Create `tests/v3/extraction/test_paths.py`:

```python
"""Cycle 9a-3 tests — extraction.paths.resolve."""

from __future__ import annotations

from trust_generator.v3.extraction.paths import resolve
from trust_generator.v3.schema import (
    Child,
    GrantorInfo,
    OfficeInfo,
    TrustData,
)


# --- Happy paths -------------------------------------------------------------


def test_resolve_top_level_attribute() -> None:
    """resolve handles a top-level attribute lookup."""
    trust = TrustData(grantor=GrantorInfo(full_legal_name="John Doe"))
    resolved, value = resolve(trust, "grantor")
    assert resolved is True
    assert value is trust.grantor


def test_resolve_nested_attribute() -> None:
    """resolve walks nested attribute chains."""
    trust = TrustData(office=OfficeInfo(file_number="2026-001"))
    resolved, value = resolve(trust, "office.file_number")
    assert resolved is True
    assert value == "2026-001"


def test_resolve_list_attribute_returns_list() -> None:
    """resolve returns the list itself when the path stops at a list-typed attribute."""
    trust = TrustData(children=[Child(full_legal_name="Jane Doe")])
    resolved, value = resolve(trust, "children")
    assert resolved is True
    assert isinstance(value, list)
    assert len(value) == 1


def test_resolve_bracket_index_into_list() -> None:
    """resolve walks ``children[0]`` to the indexed element."""
    trust = TrustData(
        children=[
            Child(full_legal_name="Jane Doe"),
            Child(full_legal_name="John Doe Jr"),
        ]
    )
    resolved, value = resolve(trust, "children[0]")
    assert resolved is True
    assert isinstance(value, Child)
    assert value.full_legal_name == "Jane Doe"


def test_resolve_bracket_index_then_attribute() -> None:
    """resolve walks ``children[0].full_legal_name`` end-to-end."""
    trust = TrustData(children=[Child(full_legal_name="Jane Doe")])
    resolved, value = resolve(trust, "children[0].full_legal_name")
    assert resolved is True
    assert value == "Jane Doe"


# --- Unresolvable paths (return (False, None)) ------------------------------


def test_resolve_index_out_of_range_returns_false() -> None:
    """resolve returns (False, None) when the bracket index is out of range."""
    trust = TrustData(children=[Child(full_legal_name="Jane Doe")])
    resolved, value = resolve(trust, "children[5].full_legal_name")
    assert resolved is False
    assert value is None


def test_resolve_unknown_attribute_returns_false() -> None:
    """resolve returns (False, None) when an attribute name does not exist."""
    trust = TrustData(children=[Child(full_legal_name="Jane Doe")])
    resolved, value = resolve(trust, "children[0].nonexistent_attr")
    assert resolved is False
    assert value is None


def test_resolve_unknown_top_level_attribute_returns_false() -> None:
    """resolve returns (False, None) when the top-level attribute is unknown."""
    trust = TrustData()
    resolved, value = resolve(trust, "no_such_section")
    assert resolved is False
    assert value is None


# --- Pathological inputs (return (False, None) rather than raising) ---------


def test_resolve_empty_string_returns_false() -> None:
    """resolve returns (False, None) on the empty string."""
    trust = TrustData()
    resolved, value = resolve(trust, "")
    assert resolved is False
    assert value is None


def test_resolve_trailing_dot_returns_false() -> None:
    """resolve returns (False, None) on a trailing dot."""
    trust = TrustData()
    resolved, value = resolve(trust, "grantor.")
    assert resolved is False
    assert value is None


def test_resolve_malformed_bracket_returns_false() -> None:
    """resolve returns (False, None) on a malformed bracket expression."""
    trust = TrustData()
    resolved, value = resolve(trust, "children[abc].full_legal_name")
    assert resolved is False
    assert value is None


def test_resolve_unbalanced_bracket_returns_false() -> None:
    """resolve returns (False, None) on an unbalanced bracket."""
    trust = TrustData()
    resolved, value = resolve(trust, "children[0")
    assert resolved is False
    assert value is None


def test_resolve_index_into_non_list_returns_false() -> None:
    """resolve returns (False, None) when bracket-indexing a non-list."""
    trust = TrustData()
    resolved, value = resolve(trust, "grantor[0]")
    assert resolved is False
    assert value is None
```

- [ ] **Step 2: Run the tests to confirm Red**

Run: `pixi run test test_paths`
Expected: tests fail with `ImportError` on `resolve` — the module does not yet exist.

- [ ] **Step 3: Author the production code (Green)**

Create `src/trust_generator/v3/extraction/paths.py`:

```python
"""Path resolver for ``field_path`` strings against a TrustData (spec §5.7).

Supports attribute access (``grantor``, ``office.file_number``),
bracket indexing (``children[0]``), and chains
(``children[0].full_legal_name``). Returns ``(False, None)`` on any
unresolvable path, including pathological inputs.
"""

from __future__ import annotations

import re

_SEGMENT_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)(?:\[(\d+)\])?$")


def resolve(trust: object, field_path: str) -> tuple[bool, object]:
    """Walk ``field_path`` against ``trust`` and return (resolved, value).

    Returns ``(True, value)`` when the path resolves end-to-end. Returns
    ``(False, None)`` on any failure: missing attribute, out-of-range
    index, bracket on a non-list, or malformed segment syntax.
    """
    if not field_path:
        return (False, None)

    segments = field_path.split(".")
    if any(seg == "" for seg in segments):
        return (False, None)

    current: object = trust
    for segment in segments:
        match = _SEGMENT_RE.match(segment)
        if match is None:
            return (False, None)
        attr_name, index_str = match.group(1), match.group(2)

        if not hasattr(current, attr_name):
            return (False, None)
        current = getattr(current, attr_name)

        if index_str is not None:
            if not isinstance(current, list):
                return (False, None)
            index = int(index_str)
            if index >= len(current) or index < 0:
                return (False, None)
            current = current[index]

    return (True, current)


__all__ = ("resolve",)
```

Then extend `src/trust_generator/v3/extraction/__init__.py`:

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
from trust_generator.v3.extraction.paths import resolve
from trust_generator.v3.extraction.trace import (
    ExtractionResult,
    ExtractionTrace,
    FieldExtraction,
)

__all__ = (
    "ExtractionResult",
    "ExtractionTrace",
    "FieldExtraction",
    "IncompleteUntilValidated",
    "RawSelfReport",
    "resolve",
)
```

The regex `^([A-Za-z_][A-Za-z0-9_]*)(?:\[(\d+)\])?$` rejects anything that isn't a Python identifier optionally followed by `[<digits>]`. That catches `children[abc]` (non-digit index), `children[0` (unclosed bracket), trailing-dot-introduced empty segments (caught by the `any(seg == "")` short-circuit), and stray characters.

- [ ] **Step 4: Run the tests to confirm Green**

Run: `pixi run test test_paths`
Expected: 13 tests pass.

If `test_resolve_empty_string_returns_false` fails: confirm the early-return for `not field_path` is in place.

If `test_resolve_index_into_non_list_returns_false` fails: confirm the `isinstance(current, list)` check happens after the attribute lookup but before the index step. Pydantic models support `__getitem__` on some submodels, but the spec-mandated semantics are list-only.

- [ ] **Step 5: Run the project gate**

Run: `pixi run check`
Expected: green.

- [ ] **Step 6: Commit Red and Green**

```bash
git add tests/v3/extraction/test_paths.py
git commit -m "test(extraction): RED — cycle 9a-3 paths.resolve dotted-path walker"
```

```bash
git add src/trust_generator/v3/extraction/paths.py src/trust_generator/v3/extraction/__init__.py
git commit -m "feat(extraction): GREEN — cycle 9a-3 paths.resolve with identifier+bracket grammar"
```

</cycle>

---

## Cycle 9a-4 — Protocol module (`SourceRef`, `ExtractionError`, `ExtractionProtocol`)

<cycle id="9a-4"
       spec-ref="§5.4, §6.5 (factored out per Q5)"
       blast-radius="src/trust_generator/v3/extraction/__init__.py; src/trust_generator/v3/extraction/protocol.py; tests/v3/extraction/test_protocol.py"
       depends-on="9a-2"
       commits="red,green">

**Files:**

- Create: `src/trust_generator/v3/extraction/protocol.py`
- Modify: `src/trust_generator/v3/extraction/__init__.py` (extend `__all__` with `ExtractionError`, `ExtractionProtocol`, `SourceRef`)
- Create: `tests/v3/extraction/test_protocol.py`

The Protocol surface is small but load-bearing: it defines the contract every backend (9b's `OllamaBackend`, future `AnthropicBackend`) implements. Three pieces:

1. `SourceRef` — a PEP 695 `type` alias for `Path`. Type-checker-visible only; no runtime class. Per `python_stack_commitments`, runtime comparisons must use `Path`, not the alias name.
2. `ExtractionError` — `Exception` subclass, the base class backends raise on extraction failure. Per spec §5.4, "partial extraction with per-field illegibility flags is the success path and does not raise."
3. `ExtractionProtocol` — `typing.Protocol` (NOT `@runtime_checkable`) with one method: `extract(self, source: SourceRef) -> ExtractionResult`.

Tests assert:

- `SourceRef` is `Path` at runtime (via `typing.get_origin` / direct comparison fallbacks acknowledging the PEP 695 caveat)
- `ExtractionError` is an `Exception` subclass and is raisable/catchable
- A minimal stub class implementing `extract(source: SourceRef) -> ExtractionResult` is structurally compatible with `ExtractionProtocol` — verified via a typed assignment that mypy validates and pytest runs trivially at runtime

- [ ] **Step 1: Author the failing tests (Red)**

Create `tests/v3/extraction/test_protocol.py`:

```python
"""Cycle 9a-4 tests — ExtractionProtocol, SourceRef, ExtractionError."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from trust_generator.v3.extraction.protocol import (
    ExtractionError,
    ExtractionProtocol,
    SourceRef,
)
from trust_generator.v3.extraction.trace import (
    ExtractionResult,
    ExtractionTrace,
)
from trust_generator.v3.schema import TrustData


# --- ExtractionError ---------------------------------------------------------


def test_extraction_error_is_exception_subclass() -> None:
    """ExtractionError is an Exception subclass."""
    assert issubclass(ExtractionError, Exception)


def test_extraction_error_raises_and_catches() -> None:
    """ExtractionError can be raised and caught as itself."""
    with pytest.raises(ExtractionError, match="boom"):
        raise ExtractionError("boom")


def test_extraction_error_caught_as_exception() -> None:
    """ExtractionError is caught by a plain ``except Exception``."""
    try:
        raise ExtractionError("boom")
    except Exception as exc:
        assert isinstance(exc, ExtractionError)


# --- SourceRef ---------------------------------------------------------------


def test_source_ref_resolves_to_path_at_typecheck_time() -> None:
    """SourceRef is a PEP 695 type alias for Path.

    The PEP 695 ``type`` statement creates a ``TypeAliasType`` whose
    ``__value__`` is the aliased type. We assert ``SourceRef.__value__
    is Path`` rather than comparing the alias itself to ``Path`` (the
    alias is not Path at runtime — it's a TypeAliasType wrapper).
    """
    assert SourceRef.__value__ is Path


def test_source_ref_runtime_isinstance_uses_path() -> None:
    """isinstance checks must use Path (not SourceRef) per python_stack_commitments."""
    p = Path("/tmp/example.png")
    # The supported runtime check:
    assert isinstance(p, Path)
    # The unsupported runtime check (PEP 695 alias is not a class) — pinning
    # the documented limitation so a future contributor sees the test that
    # fails when they assume otherwise.
    with pytest.raises(TypeError):
        isinstance(p, SourceRef)  # type: ignore[arg-type]


# --- ExtractionProtocol ------------------------------------------------------


class _StubBackend:
    """Minimal class structurally satisfying ExtractionProtocol."""

    def extract(self, source: SourceRef) -> ExtractionResult:
        return ExtractionResult(
            data=TrustData(),
            trace=ExtractionTrace(
                fields=[],
                backend_id="stub:stub-model",
                extracted_at=datetime(2026, 4, 28, tzinfo=UTC),
            ),
        )


def test_extraction_protocol_structural_conformance() -> None:
    """A class implementing ``extract(source) -> ExtractionResult`` satisfies the Protocol.

    Conformance is enforced by mypy via the typed assignment below — at
    runtime this is a no-op (Protocol is not @runtime_checkable per
    spec §5.4). The static type-check role is sufficient for v3.0.
    """
    backend: ExtractionProtocol = _StubBackend()
    result = backend.extract(Path("ignored.png"))
    assert isinstance(result, ExtractionResult)


def test_extraction_protocol_not_runtime_checkable() -> None:
    """ExtractionProtocol is NOT @runtime_checkable.

    Pinned because the spec §5.4 explicitly defers runtime-checkable to
    a later session if a use case surfaces. A future contributor adding
    the decorator should see this test fail and re-read the spec
    rationale before doing so.
    """
    with pytest.raises(TypeError):
        isinstance(_StubBackend(), ExtractionProtocol)
```

- [ ] **Step 2: Run the tests to confirm Red**

Run: `pixi run test test_protocol`
Expected: tests fail with `ModuleNotFoundError: No module named 'trust_generator.v3.extraction.protocol'`.

- [ ] **Step 3: Author the production code (Green)**

Create `src/trust_generator/v3/extraction/protocol.py`:

```python
"""Backend-agnostic OCR extraction Protocol surface (spec §5.4)."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from trust_generator.v3.extraction.trace import ExtractionResult

type SourceRef = Path
"""v3.0 SourceRef: a filesystem path to a single image or PDF.

Multi-page handling is backend-internal (see spec §7.5). The alias
exists to mark the public name of this concept; if a later session
needs to widen its meaning, the alias is the change site. v3.0 makes
no commitment about future variants.

PEP 695 type aliases are type-checker-visible only; runtime-side
isinstance checks would not see this alias. Per
``python_stack_commitments``, comparisons should not rely on this name
at runtime.
"""


class ExtractionError(Exception):
    """Base for backend-emitted extraction failures.

    Backends raise this (or a subclass) when extraction cannot proceed;
    partial extraction with per-field illegibility flags is the success
    path and does not raise.
    """


class ExtractionProtocol(Protocol):
    """Backend-agnostic OCR extraction surface.

    The Protocol's return type is the only return type. There is no
    bare-TrustData escape hatch: backends that produce TrustData
    without a paired trace would defeat the verification contract that
    ``diagnose()``'s trace-driven synthesis depends on. This is a
    deliberate interface invariant; tests in 9b cycle 5 enforce it on
    ``OllamaBackend`` and any future backend.

    Not ``@runtime_checkable`` at v3.0: the structural type-check role
    is served by the static type checker; runtime isinstance checks
    are not currently needed and the decorator carries an unfunded
    cost (slower checks; signature subtleties). If a runtime use case
    surfaces, add it then.
    """

    def extract(self, source: SourceRef) -> ExtractionResult:
        """Extract a TrustData and ExtractionTrace from one source.

        Failure modes raise ``ExtractionError`` (or subclass).
        Per-field illegibility, missing fields, and low-confidence
        transcriptions are NOT failures: they are returned as
        ``FieldExtraction`` entries on the trace with
        ``illegible=True`` and/or ``normalized_value=None``. A trace
        with zero usable fields is a valid (if unhelpful) result.
        """
        ...


__all__ = (
    "ExtractionError",
    "ExtractionProtocol",
    "SourceRef",
)
```

Then extend `src/trust_generator/v3/extraction/__init__.py`:

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
    "RawSelfReport",
    "SourceRef",
    "resolve",
)
```

PEP 695 caveat: `type SourceRef = Path` creates a `typing.TypeAliasType` instance, NOT a class. Its `__value__` attribute is `Path`. The test `test_source_ref_resolves_to_path_at_typecheck_time` asserts via `__value__`; the test `test_source_ref_runtime_isinstance_uses_path` pins the documented limitation that `isinstance(x, SourceRef)` raises `TypeError` at runtime — a future contributor expecting alias-as-class behavior will see this test fail and revisit `python_stack_commitments`.

- [ ] **Step 4: Run the tests to confirm Green**

Run: `pixi run test test_protocol`
Expected: 7 tests pass.

If `test_extraction_protocol_not_runtime_checkable` fails: someone has added `@runtime_checkable`. The fix is to revert (per spec §5.4). If `test_source_ref_resolves_to_path_at_typecheck_time` fails with `AttributeError: ... has no attribute '__value__'`: Python 3.12's PEP 695 syntax is not active — verify the pixi env's Python version is 3.12+, and the file uses the `type` keyword (not `TypeAlias` from typing).

- [ ] **Step 5: Run the project gate**

Run: `pixi run check`
Expected: green. mypy validates the structural-conformance assertion (`backend: ExtractionProtocol = _StubBackend()`) — if mypy reports a type error there, the stub class's `extract` signature has drifted from the Protocol.

- [ ] **Step 6: Commit Red and Green**

```bash
git add tests/v3/extraction/test_protocol.py
git commit -m "test(extraction): RED — cycle 9a-4 ExtractionProtocol, SourceRef, ExtractionError"
```

```bash
git add src/trust_generator/v3/extraction/protocol.py src/trust_generator/v3/extraction/__init__.py
git commit -m "feat(extraction): GREEN — cycle 9a-4 Protocol surface for OCR backends"
```

</cycle>

---

## Task 5 — `ollama >= 0.6.1` dep add (mechanical)

<task id="9a-5"
      spec-ref="§7.1, §4.1"
      blast-radius="pyproject.toml; pixi.toml"
      depends-on="9a-4">

**Files:**

- Modify: `pyproject.toml` (`[project].dependencies`)
- Modify: `pixi.toml` (`[pypi-dependencies]` and `[package.run-dependencies]`)

Mechanical dependency addition. No source code consumes the dep yet — first import lands in 9b cycle 5 (`OllamaBackend.extract`). The dep is added in 9a so all three sibling plans share a single floor (per Q3).

**Naming hazard pinned in the comment:** the wheel `ollama` is the one we want; the third-party abandoned `ollama-python` (last release 2024-01) must NOT be added. Both `pyproject.toml` and `pixi.toml` get an inline comment to prevent autocorrect-style mistakes by future contributors.

- [ ] **Step 1: Edit `pyproject.toml`**

Change line 8 from:

```toml
dependencies    = ["python-docx", "pydantic>=2", "reportlab", "pypdf>=4"]
```

to:

```toml
# NOTE: `ollama` is the official client (Apache-2.0, maintained by the
# Ollama team). Do NOT replace with `ollama-python` (third-party,
# abandoned 2024-01-17, four total releases). Per OCR spec §4.1.
dependencies    = ["python-docx", "pydantic>=2", "reportlab", "pypdf>=4", "ollama>=0.6.1"]
```

- [ ] **Step 2: Edit `pixi.toml`**

In the `[pypi-dependencies]` block (currently lines 12-19), append `ollama` after `pyyaml`:

```toml
[pypi-dependencies]
    trust-generator   = { path = '.', editable = true }
    reportlab         = '*'
    pypdf             = '>=4'
    types-reportlab   = '>=4.4.10.20260408, <5'
    pydantic-settings = '>=2.14,<3'
    rule-engine       = '>=4.5.3,<5'
    pyyaml            = '>=6,<7'
    ollama            = '>=0.6.1'  # OCR backend client (spec §4.1); NOT `ollama-python`
```

In the `[package.run-dependencies]` block (currently lines 113-120), append `ollama` after `pyyaml`:

```toml
    [package.run-dependencies]
        pydantic          = '>=2'
        python-docx       = '*'
        reportlab         = '*'
        pypdf             = '>=4'
        pydantic-settings = '>=2.14,<3'
        rule-engine       = '>=4.5.3,<5'
        pyyaml            = '>=6,<7'
        ollama            = '>=0.6.1'  # OCR backend client (spec §4.1); NOT `ollama-python`
```

- [ ] **Step 3: Re-resolve the pixi env**

Run: `pixi install`
Expected: `ollama` and its transitive deps (`httpx`, already-pinned `pydantic`) install cleanly. Existing `pixi.lock` is updated.

If conflict with an existing pin: investigate before forcing. The official `ollama` wheel depends on `httpx >= 0.27` and `pydantic >= 2.9` — both compatible with the v3 stack.

- [ ] **Step 4: Verify the dep is importable but not yet imported in src/**

Run:

```bash
pixi run python -c "import ollama; print(ollama.__name__, getattr(ollama, '__version__', 'no-attr'))"
```

Expected: `ollama 0.6.1` (or a `>=0.6.1` patch).

Run: `grep -r "import ollama\|from ollama" src/ 2>&1`
Expected: empty output. The dep is on the manifest but no `src/` consumer exists yet. If a stray import is found: investigate — 9b is the first consumer; nothing in 9a should import `ollama`.

- [ ] **Step 5: Run the project gate**

Run: `pixi run check`
Expected: green. The dep adds nothing testable yet but should not break lint, mypy, or existing tests.

- [ ] **Step 6: Commit the manifest change**

```bash
git add pyproject.toml pixi.toml pixi.lock
git commit -m "chore(deps): add ollama>=0.6.1 (OCR backend; consumed in 9b)"
```

If `pixi.lock` is gitignored or auto-managed by CI, omit it from the staging command — the project's existing commit history (e.g., `git log --oneline pixi.lock`) is the reference.

</task>

---

## Task 6 — Close `plans.xml` 9a entry

<task id="9a-6"
      spec-ref="(plans.xml bookkeeping per spec-pipeline invariant #5)"
      blast-radius=".claude/context/plans.xml"
      depends-on="9a-5">

**Files:**

- Modify: `.claude/context/plans.xml`

Mark this plan closed in the canonical plan reference. Per spec-pipeline invariant #5, the dispatching session — not the plan-executor — commits this flip. The plan-executor's prior cycles report completion; the dispatcher then issues this single bookkeeping commit.

- [ ] **Step 1: Edit `.claude/context/plans.xml`**

The 9a entry's `id`, `plan-md`, and `synopsis` were set during the spec-to-plan drafting commit (this plan-md's authoring session). The 9b and 9c sibling entries were also opened then, with empty `plan-md`. Task 6 flips the 9a entry's `status` only:

1. Set `status="closed"` (was `"open"`).
2. On the `<reference>` element: update `modified-at` to the current ISO 8601 timestamp with timezone offset (`date '+%Y-%m-%dT%H:%M:%S%:z'`).

The post-edit 9a entry should read approximately:

```xml
    <plan index="9"
          id="2026-04-27-ocr-protocol-ollama-9a"
          status="closed"
          expendable="false"
          plan-md="docs/superpowers/plans/2026-04-27-ocr-protocol-ollama-9a.md"
          spec-md="docs/superpowers/specs/2026-04-27-ocr-protocol-ollama-design.md"
          synopsis="OCR extraction core (cycles 1-3 from spec §6 + protocol cycle): markers, trace types, INCOMPLETE sentinel, paths.resolve, ExtractionProtocol surface. ollama>=0.6.1 dep added; 9b/9c open separately." />
```

The 9b and 9c sibling entries remain `status="open"` with empty `plan-md` until their own spec-to-plan sessions author them.

- [ ] **Step 2: Validate against the schema**

Run: `pixi run python -c "import xml.etree.ElementTree as ET; ET.parse('.claude/context/plans.xml')"`
Expected: no output (parses cleanly).

- [ ] **Step 3: Commit the close**

```bash
git add .claude/context/plans.xml
git commit -m "chore(context/plans): close 9a plan (2026-04-27-ocr-protocol-ollama-9a)"
```

- [ ] **Step 4: Final sanity check**

Run: `pixi run check`
Expected: green.

Run: `git log --oneline -15`
Expected: most recent commits trace `Red → Green (9a-1) → Red → Green (9a-2) → Red → Green (9a-3) → Red → Green (9a-4) → deps → plans-close`. Nine commits from this plan when no Refactor commits land.

</task>

---

## Self-Review Checklist (run before handoff)

**Spec coverage:** §3.1 + §3.2 → predecessor verification reads the spec's listed source files. §5.2 (markers) → cycle 9a-1. §5.3 (trace types) → cycle 9a-2. §5.4 (Protocol surface) → cycle 9a-4. §5.7 (path resolver) → cycle 9a-3. §6.1 → 9a-1. §6.2 → 9a-2. §6.3 → 9a-3. §6.5 structural-conformance assertion against backend → factored to 9b cycle 5 (per Q5; documented). §7.1 (`ollama >=0.6.1` floor) → Task 5. §11 (constraint compliance — bounded_context_design, python_stack_commitments) → all four cycles uphold; tests pin the PEP 695 caveat for `SourceRef`. Out-of-9a-scope sections (§5.6, §5.8-5.10, §6.4, §6.6-6.10, §7.2-7.7, §8, §12) are explicitly NOT modified — confirmed by blast-radius scoping. **No gaps.**

**Placeholder scan:** No "TBD", "implement later", "similar to Task N", or unspecified error handling. Every code block, command, expected output, and YAML/TOML edit is complete and self-contained.

**Type consistency:** `IncompleteUntilValidated`, `RawSelfReport` introduced in 9a-1 and re-imported in 9a-2's `trace.py`. `INCOMPLETE` introduced in 9a-1 and used in 9a-2 tests. `FieldExtraction`, `ExtractionTrace`, `ExtractionResult` introduced in 9a-2 and consumed by 9a-4's `_StubBackend.extract` return type and `protocol.py`'s `extract` signature. `SourceRef` (PEP 695 alias for `Path`) introduced in 9a-4 and used as the `extract` parameter type. `resolve` introduced in 9a-3, exported from `__init__.py` cumulatively across cycles. The `__all__` tuple in `__init__.py` grows monotonically; final form (after 9a-4) lists all 9 public names alphabetized.

**Cross-plan handoff:**

- 9b will import `ExtractionResult`, `ExtractionTrace`, `FieldExtraction`, `ExtractionProtocol`, `SourceRef`, `ExtractionError`, `INCOMPLETE` from `trust_generator.v3.extraction`. All eight names are landed by end of 9a.
- 9c will import `ExtractionTrace`, `FieldExtraction`, `resolve` (for stale-path filtering in `synthesize_extraction_diagnostics`). All three are landed by end of 9a.
- The `ollama` dep is on the manifest by end of Task 5 — 9b's first import (`from ollama import Client` in `ollama_backend.py`) does not need a dep-manifest edit; only a `pixi install` if 9b runs in a fresh worktree.

**Out-of-scope items deliberately deferred:**

- `INCOMPLETE` JSON serialization → chore index 15 (`2026-04-27-trace-persistence-serialization-contract`); deferred to consumer-layer persistence session.
- Empirical model selection → chore index 13 (`2026-04-27-empirical-vision-model-selection`); gated by 9b cycle 5.
- Schema-complexity-ceiling benchmark → chore index 14 (`2026-04-27-envelope-complexity-ceiling-benchmark`); gated by 9b cycle 4.
- Diagnostics-engine spec amendment (§12) → 9c (per Q2; lands atomically with `diagnose()` signature change).
