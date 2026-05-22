# Shared firm_config Cache Layer (cache) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Cycle blocks are XML-tagged for dispatcher-side cycle-scope addressing — see "Dispatch Protocol" below.

**Goal:** Land §5.4.2 (cache writer), §5.4.3-§5.4.5 (four-case fallback decision tree), §5.4.4 (staleness warning), §5.4.4.1 (integrity warning), §5.4.7 (helper-return-shape contract), and §6.5-§6.6 (TDD cycles 4-5) of the shared firm_config spec — the atomic cache writer plus the four-case read-with-fallback helper that returns `tuple[bytes, dict[str, Any], bool]`, including the two distinct `UserWarning` subclasses for availability vs. integrity fallback events.

**Architecture:** Two cycles in `src/trust_generator/v3/config/firm.py`, both modifying the existing module. Cycle 4 adds the verbatim-byte atomic writer (`_write_cache`). Cycle 5 adds the read-with-fallback helper (`_read_shared_with_fallback`), its parameter-driven sub-helper (`_read_cache_or_raise`), the two warning classes (`SharedConfigStalenessWarning`, `SharedConfigIntegrityWarning`), three error-message templates, and the `_format_duration` formatting helper. Both cycles depend on `_cache_path()` from the foundation plan (`2026-04-29-shared-firm-config-foundation`, plan index #5, spec cycle 3). Cycle 5's `_read_cache_or_raise` is keyword-only signature so the integration plan (`2026-04-29-shared-firm-config-integration`, plan index #13) can re-call it directly per spec §5.4.8.3 (partial-sync re-route). Cycle numbering matches the spec's global §6 cycle indices (4 = cache writer, 5 = cache reader), aligning with foundation plan's bare-integer cycle-id convention. Tests live in a new `tests/v3/config/test_firm_cache.py` module so the integration plan's `test_firm.py` fixture migration (Cycle 6) doesn't collide with cache-test setup; foundation's `_clean_env` autouse fixture in `test_firm.py` does not reach `test_firm_cache.py`, so cycle 5 tests carry their own defensive env clearing.

**Tech Stack:** Python 3.12; stdlib `tomllib` (parse), `warnings` (emission), `time` + `datetime.timedelta` (age formatting), `os.replace` (atomic rename); pytest with `pytest.warns` and `pytest.raises` for warning/error assertions; `tmp_path` + `monkeypatch.setenv("XDG_CACHE_HOME", ...)` for cache-directory isolation.

**Spec source:** `docs/superpowers/specs/2026-04-28-shared-firm-config-design.md` (§5.4.1 cache path resolution — landed by foundation plan as `_cache_path`; §5.4.2 atomic write; §5.4.3 four-case decision tree; §5.4.4 staleness warning; §5.4.4.1 integrity warning; §5.4.5 onboarding error; §5.4.5.1 empty-shared error; §5.4.5.2 integrity error; §5.4.7 helper-return-shape contract and TOCTOU properties; §6.5 cycle 4 — cache writer; §6.6 cycle 5 — cache reader and fallback; D-7, D-10, D-11, D-13 design decisions). Section §5.4.8 (`_SHARED_REQUIRED_SECTIONS` partial-sync completeness check) is referenced because cycle 5's `_read_cache_or_raise` keyword signature must accommodate §5.4.8.3's re-route call shape, but `_SHARED_REQUIRED_SECTIONS` itself is owned by the integration plan, NOT this plan.

**Plan-composition decisions recorded:**

- **Q1 — Two cycles, no sub-tasks beyond the close-out. Bare-integer cycle ids matching spec §6.** Spec §6.5 (cycle 4) and §6.6 (cycle 5) map cleanly to this plan's cycle 4 and cycle 5. Foundation plan #5 uses bare cycle numbers (`cycle 1`, `cycle 2`, `cycle 3`) matching spec global indices; this plan continues that convention rather than introducing plan-local prefixes (`cache-1`/`cache-2`). The cycles are contiguous in the spec (4 and 5 with no gaps), so the spec's numbering doubles as plan-local numbering with no ambiguity. There is no equivalent of 9b's prompt-cycle-vs-extract-cycle split here: cycle 4's `_write_cache` is independent of cycle 5's `_read_shared_with_fallback` (cycle 5 reads from cache, never writes), so neither cycle subsumes the other and there is no opportunity to fold them. The `_format_duration` helper, the two warning classes, and the three error templates are all introduced atomically inside cycle 5's green phase because every test in cycle 5's red phase fails on at least one of them — splitting them into a separate sub-cycle would produce a green commit that doesn't make any failing test pass, which violates the inside-out TDD discipline.

- **Q2 — `tuple[bytes, dict[str, Any], bool]` return shape is contract-load-bearing, not implementation detail.** Per spec §6.6 closing note ("C1 finding"), the predecessor draft proposed simplifying the return type to bare `bytes` and offloading the cache-decision signal to a re-`exists()` check in cycle 6. Plan-review found this introduces a TOCTOU window: a mid-load file-appears or file-disappears event would corrupt cache mtime or skip a needed cache write. The current cycle 5 design — and this plan-md — treats the 3-tuple as a pinned contract surface; cycle 5's tests assert against all three positions; refactor-stage simplifications that collapse it are explicitly forbidden. The integration plan (#13) consumes the 3-tuple directly in cycle 6 without re-querying `exists()`, which is what the contract is designed to enable.

- **Q3 — `_read_cache_or_raise` is keyword-only so the integration plan can re-use it for partial-sync re-route.** Spec §5.4.8.3 (partial-sync completeness check, added round-2 plan-review) instructs cycle 6 to call `_read_cache_or_raise` directly with `warning_class=SharedConfigIntegrityWarning` and a custom `warning_phrasing` describing the missing sections. The keyword-only signature `(_read_cache_or_raise(shared_path, *, warning_class, warning_phrasing, no_cache_error_template, integrity_reason=None))` makes this re-use unambiguous: the integration plan's call site doesn't have to match positional argument order, and the integrity-reason channel is explicit. This plan freezes the signature; the integration plan must consume it as-is.

- **Q4 — Two warning classes, not one (D-7).** Spec D-7 prescribes `SharedConfigStalenessWarning` (availability fallback: case 2 or 3) and `SharedConfigIntegrityWarning` (integrity fallback: case 4) as siblings under `UserWarning`, neither subclass of the other. Cycle 5 test #10 pins this with `issubclass` assertions in both directions. Rationale: warnings are non-failing signals; consumers may filter or elevate categorically. Staleness ("shared was unavailable, cache is being used as known-good — routine") is operationally distinct from integrity ("shared was reachable but the maintainer's edit produced something the loader can't trust — non-routine, requires human action"). Flattening to a single class would erase the distinction.

- **Q5 — Cycle commits attribute and refactor-stage reasoning.** Per `.claude/rules/development-strategy.md` (`refactor_threshold` rule), refactor stages are prescribed only when green-phase code has structural duplication, nested conditionals that flatten into dispatch, or orthogonal concerns that extract cleanly. **Cycle 4** (`_write_cache`): 9-line green output with no structural duplication and no nested conditionals → `commits="red,green"`, no refactor stage. **Cycle 5** (`_read_shared_with_fallback` + helper + warnings): the green output already factors the four-case dispatch through `_read_cache_or_raise`'s parameter-driven branching; the four `if not / try / except` branches in `_read_shared_with_fallback` could collapse into a dispatch table mapping `(file_exists, read_succeeded, parse_succeeded) → (warning_class, phrasing, template, integrity_reason)` but spec §6.6 explicitly identifies that as YAGNI (extra abstraction layer for 4 lines saved) → `commits="red,green"`, no refactor stage. Both cycles record the no-refactor reasoning inline per the rule's `if-none-met` clause.

- **Q6 — Test file is `tests/v3/config/test_firm_cache.py`, not extensions to `test_firm.py`.** The cache tests use an autouse fixture that sets `XDG_CACHE_HOME=tmp_path` so every cache test gets an isolated cache directory. The existing `test_firm.py` (which foundation plan #5 extends with 21 new cycle-1/2/3 tests) does not need this fixture per-module — its `XDG_CACHE_HOME` monkeypatching happens per-test inside the cycle 3 cache-path tests, and its `_clean_env` autouse fixture covers `TGV3_*` env vars. Putting cache tests in a sibling file (a) keeps the autouse `XDG_CACHE_HOME=tmp_path` isolation tight to the cycle 4/5 surface, (b) avoids any interaction between foundation's `_clean_env` fixture and the cache tests' explicit `delenv("TGV3_FIRM_SHARED_CONFIG")`, and (c) prevents collision when the integration plan (#13) migrates `test_firm.py` from the single-file fixture pattern to the two-file pattern in cycle 6. The integration plan is informed of this boundary via the cross-plan handoff (see §"Cross-plan handoff" in Self-Review Checklist).

- **Q7 — Inside-out (Detroit/classicist) TDD with no mocks.** Per `.claude/rules/development-strategy.md` `methodology="test-driven-development" approach="inside-out"`. Both cycles run against real `Path`, real `tomllib`, real `os.replace`, real `warnings.warn`. The only test-only seam is `tmp_path` (pytest-provided real temporary directory) and `monkeypatch.setenv("XDG_CACHE_HOME", ...)` (pytest-provided real environment-variable shim). Failure simulation in cycle 4 test 6 uses real `os.chmod` to make the cache directory unwriteable — a real `OSError` from a real syscall, not a mock. Failure simulation in cycle 5 tests uses real malformed TOML bytes written to real files.

- **Q8 — Scope size acceptance.** Cache plan touches 3 file paths: `src/trust_generator/v3/config/firm.py` (modified, both cycles), `src/trust_generator/v3/config/__init__.py` (modified, cycle 5 adds two warning classes to `__all__`), `tests/v3/config/test_firm_cache.py` (created). Plus `.claude/context/plans.xml` for the close-out. Total = 4 paths. Logical complexity: 2 cycles (complex). CLAUDE.md soft-warn at >5 files / >2 complex tasks; hard-deny at >10 / >5. Cache plan sits comfortably below soft-warn on both axes — well within the per-plan budget.

---

## Dispatch Protocol

When invoking `/spec-pipeline 2026-04-29-shared-firm-config-cache exec-plan`, the dispatcher controls which cycles execute via a scope-token in the dispatcher prompt, mirroring 9b's convention:

| Scope-token | Effect |
| ----------- | ------ |
| (no scope-token, or `cycles=all`)        | Plan-executor walks `<cycle>` and `<task>` blocks in document order, executing each per its `commits` attribute. |
| `cycles=[4]`                             | Plan-executor opens only the cycle whose `id` attribute matches; verifies `depends-on` cycles' Green commits exist via `git log --grep`; executes Red→Green for that cycle alone. |
| `cycles=[4..5]` (inclusive range)        | Plan-executor walks the contiguous cycle range; same dependency check at the range's lower bound. |
| `cycles=[5]`                             | Use only after cycle 4 is green on the branch — cycle 5 has `depends-on="4"` because the cycle 5 test helper (`_seed_cache`) consumes `_write_cache`'s atomic-byte-write contract to populate fixtures, and the case-2/3/4 dispatch tests rely on those cache files existing. |

Each `<cycle>` and `<task>` block carries five attributes:

| Attribute        | Purpose                                                                                     |
| ---------------- | ------------------------------------------------------------------------------------------- |
| `id`             | Stable scope token (bare integer matching spec §6 cycle index — `4`, `5`, plus `6` for the close-out task to keep the dispatch sequence linear). |
| `spec-ref`       | Backlink to the spec section(s) the cycle/task implements.                                  |
| `blast-radius`   | Semicolon-separated list of file paths the cycle/task is allowed to create or modify. Plan-executor must NOT edit any path outside this list during the cycle; new paths surfaced at green-time become chores via scope-maintenance. |
| `depends-on`     | Cycle/task-id list whose commits must already exist. Cycle 4's `depends-on="3"` references the foundation plan's spec cycle 3 (`_cache_path()` helper); the dependency is cross-plan, verified operationally by the predecessor-verification section below. |
| `commits`        | The cycle's commit shape — `red,green` (default), `red,green,refactor` when warranted, or `single` (for `<task>` blocks). |

The dispatching session retains responsibility for the post-execution close-out (review chore-list, commit `plans.xml` flip — invariant #5 in spec-pipeline SKILL.md). The close-out is captured as Task 6 in this plan-md but executes outside the plan-executor's scope.

---

## File Structure

**Created (production):**

(none — both cycles modify the existing `firm.py`)

**Created (tests):**

| Path | Responsibility |
| ---- | -------------- |
| `tests/v3/config/test_firm_cache.py` | Cycle 4 tests (6: `_write_cache` atomicity, parent-dir creation, mtime, write-failure-warns); cycle 5 tests (13: four-case dispatch, both warning classes, three error variants, BOM tolerance). Includes an autouse fixture that pins `XDG_CACHE_HOME` to `tmp_path` for every test in the module. |

**Modified (production):**

| Path | Change |
| ---- | ------ |
| `src/trust_generator/v3/config/firm.py` | Cycle 4: add `import warnings`, define `_write_cache`. Cycle 5: add `import time` and `from datetime import timedelta`, define `SharedConfigStalenessWarning`, `SharedConfigIntegrityWarning`, three module-private error templates (`_ONBOARDING_ERROR_TEMPLATE`, `_EMPTY_SHARED_ERROR_TEMPLATE`, `_INTEGRITY_ERROR_TEMPLATE`), `_format_duration`, `_read_cache_or_raise`, `_read_shared_with_fallback`. |
| `src/trust_generator/v3/config/__init__.py` | Cycle 5: append `SharedConfigStalenessWarning` and `SharedConfigIntegrityWarning` to the package's import list and `__all__` tuple (RUF022 will re-alphabetize on `pixi run fix`; the alphabetic positions are between `Meta` and `TrusteeCatalog` for both — verify with `pixi run fix --diff` after editing). |

**Modified (metadata):**

| Path | Change |
| ---- | ------ |
| `.claude/context/plans.xml` | Task 6: set `status="closed"` on the cache plan entry (index #12); bump `<reference>` element's `modified-at`. The `plan-md` attribute itself is set during the spec-to-plan drafting commit that authors this plan-md (a separate session — not part of task 6). |

**Files explicitly NOT modified by this plan:**

- `tests/v3/config/test_firm.py` — owned by integration plan #13 cycle 6 fixture migration.
- `tests/v3/config/test_firm_schema.py` — orthogonal (schema-generation tests).
- `src/trust_generator/v3/config/firm.py` symbols outside the cache surface — `_discover_path` rename, `load_firm_config` signature change, `_resolve_paths` shared-side anchor, `_SHARED_REQUIRED_SECTIONS`, `DEFAULT_CONFIG_PATH` rename → all owned by integration plan #13.
- `config/firm.shared.dev.toml`, `config/README.md` — owned by integration plan #13.
- The `_cache_path` function itself — owned by foundation plan #5 cycle-3. This plan only consumes it.
- The `deep_merge`, `_discover_local_path`, `_discover_shared_path` functions — owned by foundation plan #5 cycles 1 and 2. Not consumed by this plan.

**Total touched files:** 4 (1 new test, 2 modified production, 1 modified metadata). See Q8.

---

## Predecessor verification (run once before any cycle)

Gating, not implementing. If any check fails, escalate.

- [ ] **Step P1: Verify the foundation plan's Green commits exist**

Run:

```bash
git log --oneline --extended-regexp --grep='feat\(v3/config\):.*\(cycle [123]\)' | wc -l
```

Expected: at least `3` (one Green commit per foundation cycle 1 = `deep_merge`, cycle 2 = discovery, cycle 3 = `_cache_path`). The foundation plan's commit-message convention is `feat(v3/config): implement <thing> ... (cycle N)` per `docs/superpowers/plans/2026-04-29-shared-firm-config-foundation.md`. If less than 3 matches: the foundation plan did not complete; halt and finish foundation first.

(P2 below performs the load-bearing check by importing the foundation symbols. P1 is a sanity signal that surfaces missing-cycle commits separately from any import-shape regression — useful when both predecessor verification and a downstream change are in flight.)

- [ ] **Step P2: Verify the foundation surface is importable**

Run:

```bash
pixi run python -c "from trust_generator.v3.config.firm import (
    CONVENTIONAL_SHARED_CONFIG_PATH,
    FirmConfigError,
    _cache_path,
    _discover_local_path,
    _discover_shared_path,
    deep_merge,
); print('ok')"
```

Expected: `ok` (no traceback). If `ImportError` for any of `_cache_path`, `deep_merge`, `_discover_local_path`, `_discover_shared_path`, or `CONVENTIONAL_SHARED_CONFIG_PATH`: foundation plan's cycles 1/2/3 did not land in their entirety; halt and finish foundation first.

(The cache plan only consumes `_cache_path` directly. The other foundation symbols are imported here as a load-bearing readiness signal: if any of them are missing, the foundation plan is partially complete and the integration plan #13 will block; better to surface that here than mid-cycle. `FirmConfigError` is the existing exception class from the original firm-config plan #4 and should be unchanged.)

- [ ] **Step P3: Verify the project gate is green pre-cycle**

Run: `pixi run check`

Expected: lint passes, mypy passes, all tests pass. Exit code 0.

If non-green: halt — cache plan starts from a green baseline so each cycle's Red/Green delta is unambiguous. Do NOT begin cycle 4 against a yellow baseline.

- [ ] **Step P4: Verify the current branch is a feature branch**

Run: `git branch --show-current`

Expected: a branch name that is NOT `main`. The current working branch (per session start: `v3.0.0`) is fine.

- [ ] **Step P5: Verify the test directory has no stale `test_firm_cache.py`**

Run: `ls tests/v3/config/test_firm_cache.py 2>&1`

Expected: `ls: cannot access 'tests/v3/config/test_firm_cache.py': No such file or directory` (the file is created by cycle 4 step 1; if it already exists, halt and reconcile — a prior partial run may have left state behind).

---

## Cycle 4 — `_write_cache` atomic byte writer

<cycle id="4"
       spec-ref="§5.4.2, §5.4.7 cache-write properties, §6.5"
       blast-radius="src/trust_generator/v3/config/firm.py; tests/v3/config/test_firm_cache.py"
       depends-on="3"
       commits="red,green">

**Files:**

- Create: `tests/v3/config/test_firm_cache.py`
- Modify: `src/trust_generator/v3/config/firm.py` (add `import warnings`; add `_write_cache` function at module-private location near other private helpers — append after foundation cycle 3's `_cache_path` definition)

This cycle pins the verbatim-byte atomic-write contract for the shared-config cache file per spec §5.4.2: a successful write atomically replaces the cache file with the given bytes via tmp-file + `os.replace`, leaves no `.tmp` artifact behind, creates the parent directory on first use, and updates mtime within the wall-clock window. Write failures (any `OSError`) emit a `UserWarning` rather than raising, so a workstation that cannot update its cache (e.g., disk-full, read-only filesystem) does not fail the load — the user gets a warning and the next successful load will retry.

**Refactor decision:** Per `refactor_threshold` evaluation — green-phase output is 9 lines: one path-resolution call, one parent-dir mkdir, one tmp-path construction, one byte-write, one `os.replace`, one `try/except OSError`, one `warnings.warn`. No structural duplication (each operation appears once); no nested conditionals; the `try/except` wraps the whole atomic-write sequence rather than gating per-step branches that could flatten. Spec §6.5 explicitly notes the temp-file/byte-write/rename sequence could be factored into its own helper for fine-grained failure-mode testing, but the current test set treats any `OSError` uniformly (test #6) so factoring purely for hypothetical future tests is YAGNI. `commits="red,green"`; **no refactor stage — green output is already minimal; the `OSError` failure mode is uniform across the test set, and factoring the tmp/rename sequence prematurely would not pass any new test (concurs with spec §6.5 Refactor decision).**

- [ ] **Step 1: Author the failing test (Red)**

Create `tests/v3/config/test_firm_cache.py`:

```python
"""Cycle 4 + cycle 5 tests — shared firm_config cache writer and read-with-fallback helper.

Per spec §5.4.2 (atomic cache write) and §5.4.3-§5.4.5 (four-case
fallback decision tree), §5.4.4 (staleness warning), §5.4.4.1
(integrity warning), §5.4.7 (helper-return-shape contract: tuple of
bytes, parsed dict, used_cache boolean).

Tests in this module run with `XDG_CACHE_HOME` redirected to a
per-test ``tmp_path`` via the autouse fixture below, so every test
gets an isolated cache directory and the cycle-3 ``_cache_path()``
helper resolves predictably under POSIX. Windows-platform branches
of ``_cache_path()`` are covered in the foundation plan's
``test_firm.py`` (cycle 3); this file does not re-test ``_cache_path``
itself, only consumes it.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture(autouse=True)
def _isolate_cache_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect ``XDG_CACHE_HOME`` so every test has an isolated cache directory.

    Spec §5.4.1 routes POSIX cache resolution through
    ``XDG_CACHE_HOME``; setting it to ``tmp_path`` means
    ``_cache_path()`` returns a path under ``tmp_path`` and tests
    cannot collide with the real user cache directory.
    """
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    # Defensive: also clear any TGV3_FIRM_SHARED_CONFIG that might leak
    # from a parent process, so cycle 5's discovery exercises do
    # not inadvertently route to an unrelated path.
    monkeypatch.delenv("TGV3_FIRM_SHARED_CONFIG", raising=False)


# ---------------------------------------------------------------------------
# Cycle 4 — _write_cache (spec §5.4.2)
# ---------------------------------------------------------------------------


def test_cache_write_creates_file(tmp_path: Path) -> None:
    """``_write_cache(bytes)`` produces a file at the resolved cache path."""
    from trust_generator.v3.config.firm import _cache_path, _write_cache

    payload = b"firm_name = 'Example LLP'\n"
    _write_cache(payload)

    target = _cache_path()
    assert target.exists()
    assert target.read_bytes() == payload


def test_cache_write_creates_parent_directory(tmp_path: Path) -> None:
    """If the cache directory does not yet exist, ``_write_cache`` creates it."""
    from trust_generator.v3.config.firm import _cache_path, _write_cache

    target = _cache_path()
    # Sanity: parent should not exist before the first call (the autouse
    # fixture pins XDG_CACHE_HOME but does not pre-create the
    # ``trust-generator/`` subdirectory).
    assert not target.parent.exists(), (
        f"precondition violated — cache parent {target.parent} already exists"
    )

    _write_cache(b"k = 1\n")

    assert target.parent.is_dir()
    assert target.exists()


def test_cache_write_is_atomic(tmp_path: Path) -> None:
    """A successful write leaves no ``firm.shared.cache.toml.tmp`` artifact."""
    from trust_generator.v3.config.firm import _cache_path, _write_cache

    _write_cache(b"k = 1\n")

    target = _cache_path()
    tmp_artifact = target.with_suffix(target.suffix + ".tmp")
    assert not tmp_artifact.exists(), (
        f"atomicity violated — tmp artifact {tmp_artifact} survived the write"
    )


def test_cache_write_overwrites_existing(tmp_path: Path) -> None:
    """A second call with different bytes replaces the first call's content."""
    from trust_generator.v3.config.firm import _cache_path, _write_cache

    _write_cache(b"first = 1\n")
    _write_cache(b"second = 2\n")

    assert _cache_path().read_bytes() == b"second = 2\n"


def test_cache_write_updates_mtime(tmp_path: Path) -> None:
    """Cache file's mtime after a write is within 5 seconds of wall-clock time."""
    import time as _time

    from trust_generator.v3.config.firm import _cache_path, _write_cache

    before = _time.time()
    _write_cache(b"k = 1\n")
    after = _time.time()

    mtime = _cache_path().stat().st_mtime
    assert before - 1.0 <= mtime <= after + 1.0, (
        f"mtime {mtime} outside the [{before - 1.0}, {after + 1.0}] window"
    )


def test_cache_write_failure_emits_warning_not_error(tmp_path: Path) -> None:
    """Write failure (unwriteable cache dir) emits a warning rather than raising."""
    from trust_generator.v3.config.firm import _cache_path, _write_cache

    # Force the parent directory to exist but be unwriteable. The
    # write attempts a tmp-file write inside the parent; chmod 0o500
    # (read+execute, no write) makes that fail with PermissionError on
    # POSIX. (PermissionError is a subclass of OSError, so the
    # function's blanket ``except OSError`` covers it.)
    target = _cache_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.parent.chmod(0o500)
    try:
        with pytest.warns(UserWarning, match="failed to update shared firm.toml cache"):
            _write_cache(b"k = 1\n")
    finally:
        # Restore writeability so tmp_path teardown can remove the dir.
        target.parent.chmod(stat.S_IRWXU)
```

- [ ] **Step 2: Run the test suite to verify failures (Red expected)**

Run: `pixi run test v3/config/test_firm_cache`

Expected: 6 errors with `ImportError: cannot import name '_write_cache' from 'trust_generator.v3.config.firm'`. The autouse fixture itself does not import `_write_cache`, so the first failure mode is the per-test import. (If pytest reports `ModuleNotFoundError` on the test file itself: re-check that step 1 created `tests/v3/config/test_firm_cache.py` with the correct path.)

- [ ] **Step 3: Commit Red**

```bash
git add tests/v3/config/test_firm_cache.py
git commit -m "test(v3/config): add _write_cache red tests (cycle 4)"
```

- [ ] **Step 4: Write minimal implementation (Green)**

Edit `src/trust_generator/v3/config/firm.py`:

**4a.** Add `import warnings` to the top-of-file stdlib import block. The existing imports are:

```python
import os
import re
import tomllib
```

After step 4a, the block reads:

```python
import os
import re
import tomllib
import warnings
```

(Ruff's `I` rule will sort imports alphabetically on `pixi run fix` if needed; `warnings` follows `tomllib` alphabetically so this is the final order.)

**4b.** Append `_write_cache` to the module. Place it after foundation cycle 3's `_cache_path` definition (which itself was appended after the cycle-2 discovery helpers), before the existing `_resolve_paths` and `load_firm_config` functions:

```python
def _write_cache(content: bytes) -> None:
    """Atomically replace the shared-config cache file with ``content``.

    Per spec §5.4.2: writes go to a tmp file in the same parent
    directory and ``os.replace`` swaps it into place, so the cache
    file is either fully old or fully new — never partially written.
    Write failures emit a ``UserWarning`` rather than raising, so a
    workstation that cannot update its cache (disk full, read-only
    filesystem, permission denied) still completes its load on the
    shared file's bytes; the next successful load retries.
    """
    target = _cache_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_bytes(content)
        os.replace(tmp, target)
    except OSError as exc:
        warnings.warn(
            f"failed to update shared firm.toml cache: {exc}",
            stacklevel=2,
        )
```

- [ ] **Step 5: Run the test suite to verify Green**

Run: `pixi run test v3/config/test_firm_cache`

Expected: 6 passed. If any test fails:
- Test 1 fails with `FileNotFoundError`: the parent `mkdir` is missing or the path is wrong; re-check that `_cache_path()` is the same one the test imports.
- Test 3 fails (tmp artifact survives): `os.replace` did not run (an exception escaped before the swap); re-check the `try` block scope.
- Test 6 fails (no warning): the `except OSError` clause did not match the raised exception; on POSIX, `chmod 0o500` raises `PermissionError`, which is a subclass of `OSError` — confirm the except clause is `except OSError as exc` and not a narrower type.

- [ ] **Step 6: Run the full project gate to confirm no regressions**

Run: `pixi run check`

Expected: lint passes, mypy passes, all tests pass.

If lint complains about unused `warnings` (e.g., before step 4b lands the `warnings.warn` call) or import order: re-run `pixi run fix` and re-verify.

- [ ] **Step 7: Commit Green**

```bash
git add src/trust_generator/v3/config/firm.py
git commit -m "feat(v3/config): implement _write_cache atomic byte writer (cycle 4)"
```

</cycle>

---

## Cycle 5 — `_read_shared_with_fallback` four-case dispatch + warning classes

<cycle id="5"
       spec-ref="§5.4.3, §5.4.4, §5.4.4.1, §5.4.5, §5.4.5.1, §5.4.5.2, §5.4.7, §6.6, D-7, D-10"
       blast-radius="src/trust_generator/v3/config/firm.py; src/trust_generator/v3/config/__init__.py; tests/v3/config/test_firm_cache.py"
       depends-on="4"
       commits="red,green">

**Files:**

- Modify: `src/trust_generator/v3/config/firm.py` (add `import time`, `from datetime import timedelta`; add `SharedConfigStalenessWarning`, `SharedConfigIntegrityWarning`, three error templates, `_format_duration`, `_read_cache_or_raise`, `_read_shared_with_fallback`)
- Modify: `src/trust_generator/v3/config/__init__.py` (export the two warning classes)
- Append to: `tests/v3/config/test_firm_cache.py` (13 new tests for cycle 5)

This cycle pins the four-case fallback decision tree from spec §5.4.3 plus its dependent surfaces:

- **Case 1 (happy path)** — shared exists, non-empty, parses → return `(content_bytes, parsed_dict, used_cache=False)`, no warning.
- **Case 2 (availability fallback: missing or unreadable)** — shared path does not exist OR `read_bytes()` raises `OSError` → fall back to cache with `SharedConfigStalenessWarning`; raise onboarding error if no cache exists; raise corruption error if cache exists but fails to parse.
- **Case 3 (availability fallback: empty bytes)** — shared exists but `read_bytes()` returns `b""` (OneDrive placeholder state) → fall back to cache with `SharedConfigStalenessWarning` whose phrasing contains "advertised but empty"; raise empty-shared error if no cache exists.
- **Case 4 (integrity fallback)** — shared exists, non-empty, but `tomllib.loads` raises `TOMLDecodeError` → fall back to cache with `SharedConfigIntegrityWarning`; raise integrity error if no cache exists.

The helper's return shape is `tuple[bytes, dict[str, Any], bool]` per spec §5.4.7 (verbatim source bytes for cache-write gating; pre-parsed dict for merge consumption without re-parsing; `used_cache` boolean for the integration plan's cache-write gate). The C1 plan-review finding (spec §6.6 closing note) explicitly forbids collapsing this to `bytes`-only — the third element is load-bearing for closing the TOCTOU window in the integration plan's cycle 6.

The two warning classes are siblings under `UserWarning` (D-7): neither is a subclass of the other, so consumers can filter staleness vs. integrity independently. Test #10 pins this with `issubclass` assertions in both directions.

**Refactor decision:** Per `refactor_threshold` evaluation — the green-phase output already factors the four-case dispatch through `_read_cache_or_raise`'s parameter-driven branching: a single helper serves all three fallback paths (availability-missing, availability-empty, integrity-malformed) by varying its `warning_class`, `warning_phrasing`, and `no_cache_error_template` arguments. The four `if not / try / except` branches in `_read_shared_with_fallback` could collapse into a dispatch table mapping `(file_exists, read_succeeded, parse_succeeded) → (warning_class, phrasing, template, integrity_reason)`, but per spec §6.6 Refactor note this is YAGNI: the cost (extra abstraction layer; indirection on every call) exceeds the benefit (4 lines saved; dispatch becomes harder to read for the narrow benefit of being slightly more uniform). `commits="red,green"`; **no refactor stage — green output is already minimal; the dispatch-flattening that motivated the predecessor refactor is preserved via the parameter-driven `_read_cache_or_raise` helper, and per spec §6.6 collapsing the four branches into a state-tuple table is YAGNI (concurs with spec §6.6 Refactor decision).**

- [ ] **Step 1: Author the failing tests (Red)**

Append to `tests/v3/config/test_firm_cache.py` (after the cycle 4 tests):

```python


# ---------------------------------------------------------------------------
# Cycle 5 — _read_shared_with_fallback (spec §5.4.3-§5.4.5)
# ---------------------------------------------------------------------------


def _seed_cache(content: bytes) -> Path:
    """Helper: write ``content`` to the cache path via the cache writer.

    Uses ``_write_cache`` (cycle 4) to populate the cache so
    cycle 5 tests do not depend on the cache-write
    implementation detail beyond its public contract.
    """
    from trust_generator.v3.config.firm import _cache_path, _write_cache

    _write_cache(content)
    cache = _cache_path()
    assert cache.exists(), "test setup failed: _write_cache did not produce a cache file"
    return cache


# Happy-path (case 1) -------------------------------------------------------


def test_shared_present_reads_shared(tmp_path: Path) -> None:
    """When shared exists, non-empty, and parses, returns (bytes, dict, used_cache=False) with no warning."""
    import warnings as _warnings

    from trust_generator.v3.config.firm import _read_shared_with_fallback

    shared = tmp_path / "firm.shared.toml"
    shared_bytes = b"[firm]\nname = 'Example LLP'\n"
    shared.write_bytes(shared_bytes)

    with _warnings.catch_warnings(record=True) as captured:
        _warnings.simplefilter("always")
        content, parsed, used_cache = _read_shared_with_fallback(shared)

    assert content == shared_bytes
    assert parsed == {"firm": {"name": "Example LLP"}}
    assert used_cache is False
    assert captured == [], f"happy path emitted unexpected warnings: {[str(w.message) for w in captured]}"


# Availability-fallback (case 2) --------------------------------------------


def test_shared_missing_cache_present_uses_cache_with_staleness_warning(
    tmp_path: Path,
) -> None:
    """When shared is missing but cache exists, returns cache content + StalenessWarning."""
    from trust_generator.v3.config.firm import (
        SharedConfigStalenessWarning,
        _read_shared_with_fallback,
    )

    cache_bytes = b"[firm]\nname = 'Cached LLP'\n"
    _seed_cache(cache_bytes)

    shared = tmp_path / "firm.shared.toml"  # deliberately not created
    assert not shared.exists(), "test setup violated — shared should not exist"

    with pytest.warns(SharedConfigStalenessWarning) as captured:
        content, parsed, used_cache = _read_shared_with_fallback(shared)

    assert content == cache_bytes
    assert parsed == {"firm": {"name": "Cached LLP"}}
    assert used_cache is True
    assert len(captured) == 1
    assert "unreachable" in str(captured[0].message)


def test_shared_missing_cache_present_warning_includes_age(tmp_path: Path) -> None:
    """The staleness warning includes the cache file's age in human-readable form."""
    from trust_generator.v3.config.firm import (
        SharedConfigStalenessWarning,
        _read_shared_with_fallback,
    )

    _seed_cache(b"[firm]\nname = 'Cached LLP'\n")

    shared = tmp_path / "firm.shared.toml"
    with pytest.warns(SharedConfigStalenessWarning) as captured:
        _read_shared_with_fallback(shared)

    message = str(captured[0].message)
    # Age should appear formatted via timedelta — at minimum, the
    # message contains "old" and a digit-bearing duration token.
    assert "old" in message
    assert any(c.isdigit() for c in message), (
        f"warning lacks any duration digits — got {message!r}"
    )


def test_shared_missing_cache_missing_raises_onboarding_error(tmp_path: Path) -> None:
    """When both shared and cache are missing, raises FirmConfigError naming both paths and 'no cached copy exists'."""
    from trust_generator.v3.config.firm import (
        FirmConfigError,
        _cache_path,
        _read_shared_with_fallback,
    )

    shared = tmp_path / "firm.shared.toml"
    cache = _cache_path()
    assert not shared.exists()
    assert not cache.exists()

    with pytest.raises(FirmConfigError) as excinfo:
        _read_shared_with_fallback(shared)

    message = str(excinfo.value)
    assert str(shared) in message
    assert str(cache) in message
    assert "no cached copy exists" in message


def test_shared_missing_cache_corrupt_raises_corruption_error(tmp_path: Path) -> None:
    """When shared is missing and cache fails to parse, raises FirmConfigError naming cache + 'corrupt'."""
    from trust_generator.v3.config.firm import (
        FirmConfigError,
        _cache_path,
        _read_shared_with_fallback,
    )

    _seed_cache(b"this is not valid TOML\n[unterminated")
    cache = _cache_path()

    shared = tmp_path / "firm.shared.toml"
    assert not shared.exists()

    with pytest.raises(FirmConfigError) as excinfo:
        _read_shared_with_fallback(shared)

    message = str(excinfo.value)
    assert str(cache) in message
    assert "corrupt" in message


# Empty-shared-fallback (case 3) --------------------------------------------


def test_shared_empty_bytes_falls_back_to_cache_with_staleness_warning(
    tmp_path: Path,
) -> None:
    """When shared exists but is empty, returns cache content + StalenessWarning ('advertised but empty')."""
    from trust_generator.v3.config.firm import (
        SharedConfigStalenessWarning,
        _read_shared_with_fallback,
    )

    cache_bytes = b"[firm]\nname = 'Cached LLP'\n"
    _seed_cache(cache_bytes)

    shared = tmp_path / "firm.shared.toml"
    shared.write_bytes(b"")  # OneDrive placeholder state simulation

    with pytest.warns(SharedConfigStalenessWarning) as captured:
        content, parsed, used_cache = _read_shared_with_fallback(shared)

    assert content == cache_bytes
    assert parsed == {"firm": {"name": "Cached LLP"}}
    assert used_cache is True
    assert len(captured) == 1
    assert "advertised but empty" in str(captured[0].message)


def test_shared_empty_bytes_no_cache_raises_empty_shared_error(tmp_path: Path) -> None:
    """When shared is empty and no cache exists, raises FirmConfigError with 'unexpectedly empty' and 'OneDrive placeholder'."""
    from trust_generator.v3.config.firm import (
        FirmConfigError,
        _cache_path,
        _read_shared_with_fallback,
    )

    shared = tmp_path / "firm.shared.toml"
    shared.write_bytes(b"")
    assert not _cache_path().exists()

    with pytest.raises(FirmConfigError) as excinfo:
        _read_shared_with_fallback(shared)

    message = str(excinfo.value)
    assert "unexpectedly empty" in message
    assert "OneDrive placeholder state" in message


# Integrity-fallback (case 4) -----------------------------------------------


def test_shared_malformed_falls_back_to_cache_with_integrity_warning(
    tmp_path: Path,
) -> None:
    """When shared is reachable but TOML-malformed and cache exists, returns cache content + IntegrityWarning."""
    from trust_generator.v3.config.firm import (
        SharedConfigIntegrityWarning,
        SharedConfigStalenessWarning,
        _read_shared_with_fallback,
    )

    cache_bytes = b"[firm]\nname = 'Cached LLP'\n"
    _seed_cache(cache_bytes)

    shared = tmp_path / "firm.shared.toml"
    shared.write_bytes(b"[firm\nname = 'Broken")  # unterminated table header

    with pytest.warns(SharedConfigIntegrityWarning) as captured:
        content, parsed, used_cache = _read_shared_with_fallback(shared)

    assert content == cache_bytes
    assert parsed == {"firm": {"name": "Cached LLP"}}
    assert used_cache is True
    assert len(captured) == 1
    assert "is malformed" in str(captured[0].message)
    # Must NOT also emit a staleness warning.
    assert not isinstance(captured[0].message, SharedConfigStalenessWarning)


def test_shared_malformed_no_cache_raises_integrity_error(tmp_path: Path) -> None:
    """When shared is malformed and no cache exists, raises FirmConfigError with 'is malformed' and 'no cached copy exists to fall back to'."""
    from trust_generator.v3.config.firm import (
        FirmConfigError,
        _cache_path,
        _read_shared_with_fallback,
    )

    shared = tmp_path / "firm.shared.toml"
    shared.write_bytes(b"[firm\nname = 'Broken")
    assert not _cache_path().exists()

    with pytest.raises(FirmConfigError) as excinfo:
        _read_shared_with_fallback(shared)

    message = str(excinfo.value)
    assert "is malformed" in message
    assert "no cached copy exists to fall back to" in message


def test_integrity_warning_distinct_from_staleness_warning() -> None:
    """Both warning classes are UserWarning subclasses; neither subclasses the other."""
    from trust_generator.v3.config.firm import (
        SharedConfigIntegrityWarning,
        SharedConfigStalenessWarning,
    )

    assert issubclass(SharedConfigStalenessWarning, UserWarning)
    assert issubclass(SharedConfigIntegrityWarning, UserWarning)
    assert not issubclass(SharedConfigStalenessWarning, SharedConfigIntegrityWarning)
    assert not issubclass(SharedConfigIntegrityWarning, SharedConfigStalenessWarning)


# Single-emission and category properties -----------------------------------


def test_warning_emitted_exactly_once_per_call(tmp_path: Path) -> None:
    """A single fallback produces exactly one warning, not multiple."""
    import warnings as _warnings

    from trust_generator.v3.config.firm import (
        SharedConfigStalenessWarning,
        _read_shared_with_fallback,
    )

    _seed_cache(b"[firm]\nname = 'Cached LLP'\n")
    shared = tmp_path / "firm.shared.toml"  # missing → case 2

    with _warnings.catch_warnings(record=True) as captured:
        _warnings.simplefilter("always")
        _read_shared_with_fallback(shared)

    staleness = [w for w in captured if isinstance(w.message, SharedConfigStalenessWarning)]
    assert len(staleness) == 1, (
        f"expected exactly one StalenessWarning; got {len(staleness)}: "
        f"{[str(w.message) for w in captured]}"
    )


@pytest.mark.parametrize(
    "scenario,expected_used_cache",
    [
        ("case_1_happy", False),
        ("case_2_missing", True),
        ("case_3_empty", True),
        ("case_4_malformed", True),
    ],
)
def test_used_cache_boolean_matches_fallback_decision(
    tmp_path: Path,
    scenario: str,
    expected_used_cache: bool,
) -> None:
    """``used_cache`` is False for case 1, True for cases 2/3/4."""
    import warnings as _warnings

    from trust_generator.v3.config.firm import _read_shared_with_fallback

    shared = tmp_path / "firm.shared.toml"
    if scenario == "case_1_happy":
        shared.write_bytes(b"[firm]\nname = 'Example LLP'\n")
    elif scenario == "case_2_missing":
        _seed_cache(b"[firm]\nname = 'Cached LLP'\n")
        # shared deliberately absent
    elif scenario == "case_3_empty":
        _seed_cache(b"[firm]\nname = 'Cached LLP'\n")
        shared.write_bytes(b"")
    elif scenario == "case_4_malformed":
        _seed_cache(b"[firm]\nname = 'Cached LLP'\n")
        shared.write_bytes(b"[firm\nbroken")
    else:
        pytest.fail(f"unexpected scenario {scenario!r}")

    with _warnings.catch_warnings():
        _warnings.simplefilter("always")
        _, _, used_cache = _read_shared_with_fallback(shared)

    assert used_cache is expected_used_cache


# Encoding tolerance (round-2 plan-review) ----------------------------------


def test_shared_with_utf8_bom_loads_normally(tmp_path: Path) -> None:
    """A shared file saved with a UTF-8 BOM loads via case 1, not integrity-fallback."""
    import warnings as _warnings

    from trust_generator.v3.config.firm import _read_shared_with_fallback

    bom = b"\xef\xbb\xbf"
    shared = tmp_path / "firm.shared.toml"
    shared.write_bytes(bom + b"[firm]\nname = 'Example LLP'\n")

    with _warnings.catch_warnings(record=True) as captured:
        _warnings.simplefilter("always")
        content, parsed, used_cache = _read_shared_with_fallback(shared)

    assert content.startswith(bom)
    assert parsed == {"firm": {"name": "Example LLP"}}
    assert used_cache is False
    assert captured == [], (
        f"BOM-prefixed shared emitted unexpected warnings: {[str(w.message) for w in captured]}"
    )
```

**Note on test count:** 13 test functions appended (one per spec §6.6 enumerated case 1-13). The test #12 parameterization expands to 4 pytest cases (case_1_happy, case_2_missing, case_3_empty, case_4_malformed) under a single function, so collected-test count is `1 + 4 + 7 + 1 = 13` plus the 6 cycle 4 tests already present = 19 total in the module.

- [ ] **Step 2: Run the test suite to verify failures (Red expected)**

Run: `pixi run test v3/config/test_firm_cache`

Expected: 6 from cycle 4 PASS; the 13 new tests fail with `ImportError` for one of:
- `_read_shared_with_fallback` (every cycle 5 test)
- `SharedConfigStalenessWarning` (tests 2, 3, 6, 10, 11)
- `SharedConfigIntegrityWarning` (tests 8, 10)

The first failure mode in each test is the per-test import; pytest collects each test independently so the surfacing of all 13 failures is expected.

If a cycle 4 test now fails: a green-phase regression slipped in between cycles; halt and reconcile before proceeding.

- [ ] **Step 3: Commit Red**

```bash
git add tests/v3/config/test_firm_cache.py
git commit -m "test(v3/config): add _read_shared_with_fallback red tests (cycle 5)"
```

- [ ] **Step 4: Write minimal implementation (Green)**

Edit `src/trust_generator/v3/config/firm.py`:

**4a.** Add `import time` and `from datetime import timedelta` to the top-of-file import block. After step 4a, the stdlib import block reads (assuming foundation plan #5 has landed `sys` per its cycle 3 step 4 and `from collections.abc import Mapping` per its cycle 1 step 4, plus this plan's cycle 4 added `warnings`):

```python
import os
import re
import sys
import time
import tomllib
import warnings
from collections.abc import Mapping
from datetime import timedelta
from pathlib import Path
from typing import Any, Final, Literal
```

(`time` falls between `sys` and `tomllib` alphabetically; `from datetime import timedelta` goes in the `from` block before `from pathlib import Path` because `datetime` precedes `pathlib` alphabetically. The `from collections.abc import Mapping` line was added by foundation cycle 1 — leave it untouched. If the import block doesn't already contain `sys` and `Mapping`: foundation didn't fully land; halt and reconcile per predecessor verification step P2.)

**4b.** Add the two warning classes near the top of the module, immediately after the existing `class FirmConfigError(Exception):` declaration (around current line 47):

```python
class SharedConfigStalenessWarning(UserWarning):
    """Emitted when the loader falls back to a cached shared config copy due to availability failure.

    Per spec §5.4.4 + D-7. Distinct from ``SharedConfigIntegrityWarning``
    so consumers can route the categories to different surfaces.
    Operational signal: shared was unavailable (file missing, OSError,
    or empty bytes consistent with OneDrive placeholder state); the
    cache is being used as a known-good fallback. Routine; the next
    successful sync resolves it.
    """


class SharedConfigIntegrityWarning(UserWarning):
    """Emitted when the loader falls back to a cached shared config copy due to integrity failure.

    Per spec §5.4.4.1 + D-7 + D-10. Distinct from
    ``SharedConfigStalenessWarning``. Operational signal: shared was
    reachable and non-empty but TOML-malformed; the cache is being
    used as a known-good fallback. Non-routine — the maintainer must
    repair the shared file before the cache is overwritten on a
    successful load.
    """
```

**4c.** Add the three error-message templates as module-level `Final[str]` constants. Place them after the warning classes:

```python
_ONBOARDING_ERROR_TEMPLATE: Final[str] = (
    "Shared firm.toml is unreachable and no cached copy exists.\n"
    "  Resolved shared path: {shared_path}\n"
    "  Expected cache path:  {cache}\n"
    "\n"
    "  This typically indicates first-time workstation setup before the "
    "shared file has synced. Verify TGV3_FIRM_SHARED_CONFIG points at the "
    "correct location, or contact the maintainer."
)


_EMPTY_SHARED_ERROR_TEMPLATE: Final[str] = (
    "Shared firm.toml at {shared_path} is unexpectedly empty and no "
    "cached copy exists to fall back to.\n"
    "  Resolved shared path: {shared_path}\n"
    "  Expected cache path:  {cache}\n"
    "\n"
    "  This typically indicates an in-progress OneDrive sync that has "
    "advertised the file but not yet propagated its content. Retry "
    "shortly, or contact the maintainer if the condition persists past "
    "the firm's expected sync window."
)


_INTEGRITY_ERROR_TEMPLATE: Final[str] = (
    "Shared firm.toml at {shared_path} is malformed (TOML parse error: "
    "{integrity_reason}) and no cached copy exists to fall back to.\n"
    "  Resolved shared path: {shared_path}\n"
    "  Expected cache path:  {cache}\n"
    "\n"
    "  The maintainer must repair the shared file. This workstation has "
    "no cached copy to fall back to, so it cannot operate until the "
    "shared file is fixed and re-synced."
)
```

(All three templates take `{shared_path}` and `{cache}` placeholders; `_INTEGRITY_ERROR_TEMPLATE` additionally takes `{integrity_reason}`. The other two ignore `integrity_reason` if it is supplied — `str.format` allows extra named arguments to be unused unless a `KeyError` occurs on a referenced placeholder, but since neither template references `{integrity_reason}`, passing an unused value is safe.)

Wait — `str.format` does NOT silently ignore unused kwargs but DOES raise `KeyError` on referenced-but-unsupplied keys. Reading carefully: extra unused kwargs are accepted silently. So passing `integrity_reason=None` to `_ONBOARDING_ERROR_TEMPLATE.format(shared_path=p, cache=c, integrity_reason=None)` is fine because the template doesn't reference `{integrity_reason}`.

**4d.** Add `_format_duration` helper. Place it after the error templates:

```python
def _format_duration(seconds: float) -> str:
    """Format a duration in seconds as a human-readable string.

    Wraps ``datetime.timedelta`` for the ``__str__`` representation —
    ``'0:05:23'`` for short windows; ``'1 day, 2:15:40'`` for longer.
    Used in fallback warnings to surface cache age. Not a design
    surface — a one-line passthrough kept as a named helper so
    callers read intent rather than inline ``str(timedelta(...))``.
    """
    return str(timedelta(seconds=int(seconds)))
```

**4e.** Add `_read_cache_or_raise` helper. Place it after `_format_duration`:

```python
def _read_cache_or_raise(
    shared_path: Path,
    *,
    warning_class: type[UserWarning],
    warning_phrasing: str,
    no_cache_error_template: str,
    integrity_reason: str | None = None,
) -> tuple[bytes, dict[str, Any], bool]:
    """Read from the cache file or raise with a case-specific error template.

    Per spec §5.4.3 cases 2/3/4 fallback dispatch and §5.4.5 /
    §5.4.5.1 / §5.4.5.2 error variants. Keyword-only past
    ``shared_path`` so the integration plan's partial-sync re-route
    (spec §5.4.8.3) can call this directly with explicit category
    arguments. Returns ``(cache_bytes, parsed_cache_dict, used_cache=True)``;
    raises ``FirmConfigError`` if the cache is missing (using
    ``no_cache_error_template``) or fails to parse (corruption error).
    """
    cache = _cache_path()
    if not cache.exists():
        raise FirmConfigError(
            no_cache_error_template.format(
                shared_path=shared_path,
                cache=cache,
                integrity_reason=integrity_reason or "",
            )
        )
    content = cache.read_bytes()
    try:
        parsed = tomllib.loads(content.decode("utf-8-sig"))
    except tomllib.TOMLDecodeError as exc:
        raise FirmConfigError(
            f"shared firm.toml cache at {cache} is corrupt: {exc}"
        ) from exc
    age_seconds = time.time() - cache.stat().st_mtime
    age_str = _format_duration(age_seconds)
    warnings.warn(
        f"shared firm.toml at {shared_path} {warning_phrasing}; "
        f"falling back to cached copy ({age_str} old).\n"
        f"  source: {shared_path}\n  cache:  {cache}",
        category=warning_class,
        stacklevel=3,
    )
    return content, parsed, True
```

**4f.** Add `_read_shared_with_fallback`. Place it after `_read_cache_or_raise`:

```python
def _read_shared_with_fallback(
    shared_path: Path,
) -> tuple[bytes, dict[str, Any], bool]:
    """Read shared TOML, falling back to cache on any availability or integrity failure.

    Per spec §5.4.3 four-case dispatch and §5.4.7 helper-return-shape
    contract.

    Returns ``(bytes, parsed_dict, used_cache)``. The bytes are the
    verbatim source content (used by cycle 6 to gate cache writing).
    The parsed dict is the result of parsing those bytes, returned to
    avoid double-parse. The boolean indicates whether the fallback
    path was taken (``True`` = cache was consumed; ``False`` = shared
    was the source).

    Raises ``FirmConfigError`` when both shared and cache are
    unavailable, with case-specific message variants per §5.4.5 /
    §5.4.5.1 / §5.4.5.2.

    The 3-tuple return shape is contract-load-bearing per the
    spec §6.6 C1 plan-review finding — collapsing it to ``bytes``
    re-introduces a TOCTOU window in the integration plan's cache-
    write gate. Do not simplify.
    """
    # Case 2: file missing or unreadable → availability-fallback.
    if not shared_path.exists():
        return _read_cache_or_raise(
            shared_path,
            warning_class=SharedConfigStalenessWarning,
            warning_phrasing="unreachable",
            no_cache_error_template=_ONBOARDING_ERROR_TEMPLATE,
        )
    try:
        content = shared_path.read_bytes()
    except OSError:
        return _read_cache_or_raise(
            shared_path,
            warning_class=SharedConfigStalenessWarning,
            warning_phrasing="unreachable",
            no_cache_error_template=_ONBOARDING_ERROR_TEMPLATE,
        )

    # Case 3: empty bytes → availability-fallback (OneDrive placeholder).
    if not content:
        return _read_cache_or_raise(
            shared_path,
            warning_class=SharedConfigStalenessWarning,
            warning_phrasing="advertised but empty",
            no_cache_error_template=_EMPTY_SHARED_ERROR_TEMPLATE,
        )

    # Case 4: parse-fail → integrity-fallback.
    try:
        parsed = tomllib.loads(content.decode("utf-8-sig"))
    except tomllib.TOMLDecodeError as exc:
        return _read_cache_or_raise(
            shared_path,
            warning_class=SharedConfigIntegrityWarning,
            warning_phrasing=f"is malformed (TOML parse error: {exc})",
            no_cache_error_template=_INTEGRITY_ERROR_TEMPLATE,
            integrity_reason=str(exc),
        )

    # Case 1: happy path.
    return content, parsed, False
```

**4g.** Edit `src/trust_generator/v3/config/__init__.py` to export the two warning classes. The current file imports a list of names from `trust_generator.v3.config.firm`; add `SharedConfigStalenessWarning` and `SharedConfigIntegrityWarning` to that import block AND to the `__all__` tuple. After the edit, the relevant section reads (alphabetic positions for both new names: between `Meta` and `TrusteeCatalog`):

```python
from trust_generator.v3.config.firm import (
    DEFAULT_CONFIG_PATH,
    ENV_PREFIX,
    ENV_VAR_CONFIG_PATH,
    Diagnostics,
    Drafts,
    EstateThresholds,
    FirmConfig,
    FirmConfigError,
    FirmIdentity,
    Guardianship,
    Jurisdiction,
    Meta,
    SharedConfigIntegrityWarning,
    SharedConfigStalenessWarning,
    TrusteeCatalog,
    load_firm_config,
)

__all__ = [
    "DEFAULT_CONFIG_PATH",
    "ENV_PREFIX",
    "ENV_VAR_CONFIG_PATH",
    "Diagnostics",
    "Drafts",
    "EstateThresholds",
    "FirmConfig",
    "FirmConfigError",
    "FirmIdentity",
    "Guardianship",
    "Jurisdiction",
    "Meta",
    "SharedConfigIntegrityWarning",
    "SharedConfigStalenessWarning",
    "TrusteeCatalog",
    "load_firm_config",
]
```

(RUF022 enforces alphabetic ordering on `__all__`. The two new entries land between `Meta` and `TrusteeCatalog` because `SharedConfig...` > `Meta` > ... wait, `Meta` < `SharedConfig...` < `TrusteeCatalog` — yes, that's the alphabetic position. `SharedConfigIntegrityWarning` precedes `SharedConfigStalenessWarning` because `I` < `S`.)

- [ ] **Step 5: Run the test suite to verify Green**

Run: `pixi run test v3/config/test_firm_cache`

Expected: 19 passed (6 from cycle 4 + 13 from cycle 5; the parameterized test #12 expands to 4 cases for a collected count of 22 if pytest reports per-parametrization, but the parent test counts as 1 in summary tools). If any test fails:

- Test 1 (happy path) emits a warning: the fallthrough path in `_read_shared_with_fallback` is calling `_read_cache_or_raise` instead of returning `(content, parsed, False)`; verify the case 1 return is unconditional after the case 4 try/except.
- Test 6 (empty-bytes warning phrasing): the `warning_phrasing` argument for case 3 is wrong; should be `"advertised but empty"`.
- Test 8 (malformed shared with cache → IntegrityWarning): the dispatch is routing to `SharedConfigStalenessWarning` instead; verify case 4's `warning_class=SharedConfigIntegrityWarning`.
- Test 10 (warning class hierarchy): one of the warning classes was declared as a subclass of the other; verify both inherit directly from `UserWarning`.
- Test 13 (BOM tolerance): the `decode("utf-8-sig")` step is `decode("utf-8")` instead; only `utf-8-sig` strips BOM.

- [ ] **Step 6: Run the full project gate to confirm no regressions**

Run: `pixi run check`

Expected: lint passes, mypy passes, all tests pass. If `__all__` ordering trips RUF022: run `pixi run fix` and re-verify (note: per CLAUDE.md, `pixi run fix` is a development tool, not a code-review tool — running it here is appropriate because we are still in the implementation phase).

If mypy flags `_read_cache_or_raise`'s `type[UserWarning]` parameter or `dict[str, Any]` return annotation: confirm the imports include `from typing import Any` and `Path` is imported from `pathlib` (both should already be present from the existing module).

- [ ] **Step 7: Commit Green**

```bash
git add src/trust_generator/v3/config/firm.py src/trust_generator/v3/config/__init__.py
git commit -m "feat(v3/config): implement _read_shared_with_fallback + warning classes (cycle 5)"
```

</cycle>

---

## Task 6 — Close `plans.xml` cache entry

<task id="6"
      spec-ref="(plans.xml bookkeeping per spec-pipeline invariant #5)"
      blast-radius=".claude/context/plans.xml"
      depends-on="5"
      commits="single">

**Files:**

- Modify: `.claude/context/plans.xml`

Mark this plan closed in the canonical plan reference. Per spec-pipeline invariant #5, the **dispatching session** — not the plan-executor — commits this flip. The plan-executor's prior cycles report completion; the dispatcher then issues this single bookkeeping commit. If you (the plan-executor) reach this task: stop, report cycle 5 Green, and hand off.

- [ ] **Step 1: Edit `.claude/context/plans.xml`**

The cache plan's entry is index #12. The `id`, `plan-md`, `spec-md`, and `synopsis` were set during the spec-to-plan drafting commit (the session that authored this plan-md). Task 6 flips the entry's `status` only:

1. Set `status="closed"` on the `<plan index="12" id="2026-04-29-shared-firm-config-cache">` entry (was `"open"`).
2. On the `<reference>` element: update `modified-at` to the current ISO 8601 timestamp with timezone offset:

```bash
date '+%Y-%m-%dT%H:%M:%S%:z'
```

The post-edit cache entry should read approximately:

```xml
    <plan index="12"
          id="2026-04-29-shared-firm-config-cache"
          status="closed"
          expendable="false"
          plan-md="docs/superpowers/plans/2026-04-29-shared-firm-config-cache.md"
          spec-md="docs/superpowers/specs/2026-04-28-shared-firm-config-design.md"
          synopsis="Cache layer: spec §6 cycles 4-5 — atomic _write_cache, four-case _read_shared_with_fallback (availability/empty/integrity), SharedConfigStalenessWarning + SharedConfigIntegrityWarning. Depends on foundation plan." />
```

The integration sibling entry (index #13) remains `status="open"` with empty `plan-md` until its own spec-to-plan session authors it.

- [ ] **Step 2: Validate against the schema**

Run:

```bash
pixi run python -c "import xml.etree.ElementTree as ET; ET.parse('.claude/context/plans.xml')"
```

Expected: no output (parses cleanly).

If the project has a stricter XSD validator wired up (per `.claude/context/schema/`), prefer that over the bare `ElementTree.parse` call. Check `.claude/context/schema/plans.xsd` for the canonical schema.

- [ ] **Step 3: Commit the close**

```bash
git add .claude/context/plans.xml
git commit -m "chore(context/plans): close cache plan (2026-04-29-shared-firm-config-cache)"
```

- [ ] **Step 4: Final sanity check**

Run: `pixi run check`

Expected: green.

Run: `git log --oneline -10`

Expected: most recent commits trace `red (cycle 4) → green (cycle 4) → red (cycle 5) → green (cycle 5) → close cache plan`. Five commits from this plan, sandwiched between the foundation plan's cycle-1/2/3 commits below and the (parallel-drafted) integration plan's cycle-6 commits above.

</task>

---

## Self-Review Checklist (run before handoff)

**Spec coverage:**

- §5.4.1 (cache path resolution) → consumed via `_cache_path()` import; predecessor verification step P2 confirms it.
- §5.4.2 (atomic cache write) → cycle 4 green.
- §5.4.3 (four-case decision tree) → cycle 5 green; tests cover all four cases.
- §5.4.4 (staleness warning class) → cycle 5 step 4b.
- §5.4.4.1 (integrity warning class) → cycle 5 step 4b.
- §5.4.5 (onboarding error variant) → cycle 5 step 4c (`_ONBOARDING_ERROR_TEMPLATE`).
- §5.4.5.1 (empty-shared error variant) → cycle 5 step 4c (`_EMPTY_SHARED_ERROR_TEMPLATE`).
- §5.4.5.2 (integrity error variant) → cycle 5 step 4c (`_INTEGRITY_ERROR_TEMPLATE`).
- §5.4.6 (cache invalidation policy) → no implementation needed; spec explicitly says "no automatic invalidation, no public API surface."
- §5.4.7 (testable properties) → cycle 4 + cycle 5 tests cover all 12 enumerated properties (cycle 4 covers cache-write properties; cycle 5 covers availability-fallback, empty-shared-fallback, integrity-fallback, single-parse/TOCTOU properties).
- §5.4.8 (`_SHARED_REQUIRED_SECTIONS` partial-sync completeness check) → owned by integration plan #13. The cache plan's `_read_cache_or_raise` keyword-only signature is calibrated to support §5.4.8.3's re-route call shape; the constant itself and the completeness check live in cycle 6.
- §6.5 (cycle 4 — cache writer) → cycle 4.
- §6.6 (cycle 5 — cache reader and fallback) → cycle 5.
- §6.6 C1 finding (3-tuple return shape) → cycle 5 green pins the `tuple[bytes, dict[str, Any], bool]` return; refactor decision explicitly forbids collapse.
- D-7 (two distinct warning classes) → cycle 5 step 4b + test #10.
- D-10 (integrity-fallback semantics) → cycle 5 step 4f case 4 routes to `SharedConfigIntegrityWarning` rather than fail-fast.
- D-11 (cache-write-after-validation gating) → owned by integration plan #13. The cache plan's `_write_cache` is unconditional; gating happens in cycle 6.
- D-13 (cycle 5 return-shape revert per spec §6.6) → cycle 5 green honors the 3-tuple shape.

**Sections explicitly NOT modified by cache plan** (out-of-cache-scope, owned by foundation #5 or integration #13):

- §5.1 (motivation), §5.2 (discovery and path conventions), §5.3 (merge contract), §5.4.1 (cache path resolution helper) → foundation plan.
- §5.5 (SharePoint permission model) → operational concern, not implementation.
- §5.6 (loader API surface — two-arg `load_firm_config`, `_resolve_paths`, `DEFAULT_CONFIG_PATH` rename) → integration plan.
- §5.4.8 (partial-sync completeness check, `_SHARED_REQUIRED_SECTIONS`) → integration plan.
- §6.2 (cycle 1 — `deep_merge`), §6.3 (cycle 2 — discovery), §6.4 (cycle 3 — `_cache_path`) → foundation plan.
- §6.7 (cycle 6 — `load_firm_config` integration, fixture migration, cache-write gate, completeness check) → integration plan.
- §7 (open seams), §8 (migration from current state), §9 (firm-config spec amendment A-7), §10 (pre-planning chores) → mostly out-of-scope or owned by other plans; A-7 has already landed (commit `d807e97`).

**No gaps.**

**Placeholder scan:** No "TBD", "implement later", "similar to Task N", or unspecified error handling. Every code block, command, expected output, and edit is complete and self-contained. The autouse fixture's `monkeypatch.delenv("TGV3_FIRM_SHARED_CONFIG", raising=False)` is defensive (clears env vars that may leak from a parent process) but is not a placeholder — it has explicit purpose and behavior.

**Type consistency:**

- `_write_cache(content: bytes) -> None` introduced in cycle 4; consumed by `_seed_cache` test helper in cycle 5 tests.
- `SharedConfigStalenessWarning(UserWarning)`, `SharedConfigIntegrityWarning(UserWarning)` introduced in cycle 5 step 4b; consumed by cycle 5 tests #2, #3, #6, #8, #10, #11; re-exported via `__init__.py` step 4g.
- `_format_duration(seconds: float) -> str` introduced in cycle 5 step 4d; consumed by `_read_cache_or_raise` step 4e.
- `_read_cache_or_raise(shared_path, *, warning_class, warning_phrasing, no_cache_error_template, integrity_reason=None) -> tuple[bytes, dict[str, Any], bool]` introduced in cycle 5 step 4e; consumed by `_read_shared_with_fallback` step 4f, AND will be consumed by integration plan #13 cycle 6 partial-sync re-route per spec §5.4.8.3 (cross-plan handoff).
- `_read_shared_with_fallback(shared_path: Path) -> tuple[bytes, dict[str, Any], bool]` introduced in cycle 5 step 4f; consumed by cycle 5 tests #1-13; will be consumed by integration plan #13 cycle 6 as the shared-side read path.
- `_ONBOARDING_ERROR_TEMPLATE`, `_EMPTY_SHARED_ERROR_TEMPLATE`, `_INTEGRITY_ERROR_TEMPLATE` introduced in cycle 5 step 4c; consumed by `_read_cache_or_raise` and (for `_INTEGRITY_ERROR_TEMPLATE`) by integration plan #13 cycle 6 partial-sync re-route.
- The 3-tuple return shape `tuple[bytes, dict[str, Any], bool]` is consistent across `_read_shared_with_fallback` and `_read_cache_or_raise`; type signatures match exactly.

**Cross-plan handoff (cache → integration):**

The integration plan #13 must consume the following surface as-frozen by this plan:

1. **Public re-exports** (`SharedConfigStalenessWarning`, `SharedConfigIntegrityWarning`) — re-exported via `src/trust_generator/v3/config/__init__.py` as of cycle 5 step 4g. Consumers may filter on either class independently per D-7.

2. **Module-private symbols consumed by cycle 6** (NOT just by cycle 5):
   - `_read_shared_with_fallback(shared_path) -> tuple[bytes, dict[str, Any], bool]` — cycle 6 calls this once; consumes the 3-tuple directly without re-querying `shared_path.exists()`.
   - `_read_cache_or_raise(shared_path, *, warning_class, warning_phrasing, no_cache_error_template, integrity_reason=None) -> tuple[bytes, dict[str, Any], bool]` — cycle 6 calls this directly with `warning_class=SharedConfigIntegrityWarning` and a missing-sections phrasing per spec §5.4.8.3 partial-sync re-route. The keyword-only signature is calibrated for this re-use; the integration plan must NOT propose alternative signatures.
   - `_write_cache(content: bytes) -> None` — cycle 6 calls this with the verbatim `shared_bytes` (tuple position 0) after `FirmConfig(**merged)` validation succeeds (D-11). Cycle 6 must NOT re-serialize the parsed dict for caching.
   - `_INTEGRITY_ERROR_TEMPLATE` — consumed by cycle 6's partial-sync re-route (the `no_cache_error_template` argument).
   - `_cache_path` — consumed by cycle 6 for cache-existence checks.

3. **Frozen contracts** (do NOT modify in cycle 6):
   - 3-tuple return shape `tuple[bytes, dict[str, Any], bool]` — collapsing reintroduces the C1 TOCTOU finding.
   - Two-warning-class hierarchy (D-7) — flattening erases categorical signal.
   - `_read_cache_or_raise`'s keyword-only signature — wrapping it for "cleanliness" breaks the partial-sync re-use.
   - BOM-tolerant decoding (`utf-8-sig`) — already inside the helper; cycle 6 must NOT add another decode layer.

4. **Test-file boundaries**:
   - `tests/v3/config/test_firm_cache.py` (created by this plan) is independent of `tests/v3/config/test_firm.py`. The integration plan's fixture migration (cycle 6) must NOT merge them.
   - The autouse `_isolate_cache_dir` fixture in `test_firm_cache.py` is local to that file. Integration tests that need cache isolation should declare their own fixture (or scope it via a sibling `conftest.py` only if the fixture is genuinely shared).

5. **Cache-write gating ownership**:
   - `_write_cache` itself is unconditional — it writes whatever bytes the caller hands it. The validation-gating per D-11 (cache write only after `FirmConfig(**merged)` succeeds) is integration-plan responsibility. The integration plan's cycle 6 green must implement: parse → completeness check → merge → validate → THEN `_write_cache(shared_bytes)` — and skip the call entirely when `used_cache=True` is returned from `_read_shared_with_fallback`.

**Out-of-scope items deliberately deferred:**

- `_SHARED_REQUIRED_SECTIONS` constant and partial-sync completeness check (§5.4.8) → integration plan #13 cycle 6.
- `load_firm_config` two-arg signature and `_resolve_paths` shared-side anchor (§5.6, D-8) → integration plan #13.
- `DEFAULT_CONFIG_PATH` → `CONVENTIONAL_LOCAL_CONFIG_PATH` rename (§5.6.2) → integration plan #13.
- `config/firm.shared.dev.toml` and `config/README.md` artifacts → integration plan #13.
- `test_firm.py` migration from single-file to two-file fixture pattern (§6.7) → integration plan #13 cycle 6.
- Cache CLI command for explicit invalidation (§5.4.6) → out of scope, deferred to a future spec per the spec's own deferral note.
- Manifest/checksum integrity protocol (§5.4.8.5) → out of scope, deferred per spec.

---

## Execution Handoff

After cycle 5 reports Green and Task 6's plans.xml flip is committed, the dispatching session should verify:

1. `pixi run check` passes on a clean working tree.
2. `git log --oneline -5` shows the expected 5-commit trace: `test(...): add _write_cache red tests (cycle 4)` → `feat(...): implement _write_cache atomic byte writer (cycle 4)` → `test(...): add _read_shared_with_fallback red tests (cycle 5)` → `feat(...): implement _read_shared_with_fallback + warning classes (cycle 5)` → `chore(context/plans): close cache plan (...)`.
3. The integration plan #13 (`2026-04-29-shared-firm-config-integration`) is now unblocked. The next pipeline step is `/spec-pipeline 2026-04-29-shared-firm-config-integration spec-to-plan` (if integration plan-md is still empty) or `exec-plan` (if it has been authored in parallel).

If any of those checks fail, halt and reconcile before considering the cache plan closed.
