# Shared firm_config — Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Each cycle (Task) maps to one Red commit + one Green commit + (Cycle 1 only) one Refactor commit, per `.claude/rules/development-strategy.md`.

**Goal:** Land the three pure-utility surfaces (`deep_merge`, two-source discovery chains, `_cache_path`) that the cache plan (#12) and the integration plan (#13) compose on top of. No filesystem state, no signature changes to `load_firm_config`, no public-API surface yet — these primitives are added as module-private helpers in `trust_generator.v3.config.firm`.

**Architecture:** Bottom-up TDD per spec §6.1. Cycles 1–3 are independent leaves; the integration plan's Cycle 6 will compose them. All three cycles ship to `src/trust_generator/v3/config/firm.py` and exercise via `tests/v3/config/test_firm.py`. The existing `_clean_env` autouse fixture (`test_firm.py:67-70`) already strips every `TGV3_*` env var — `TGV3_FIRM_SHARED_CONFIG` is covered automatically, so spec §6.3's "extend the fixture" note is moot and intentionally not actioned here.

**Tech Stack:** Python 3.12 (pixi-pinned, do not invoke bare `python`), pytest + monkeypatch, `pathlib.Path`, `tomllib` (already imported in firm.py). No new dependencies.

**Spec reference:** `docs/superpowers/specs/2026-04-28-shared-firm-config-design.md` §6.1–§6.4, §5.2, §5.3, §5.4.1.

---

## File Structure

| Path | Action | Responsibility |
|---|---|---|
| `src/trust_generator/v3/config/firm.py` | Modify (append) | Adds `deep_merge`, `_is_empty`, `_EMPTY_LITERALS`, `_discover_local_path`, `_discover_shared_path`, `CONVENTIONAL_SHARED_CONFIG_PATH`, `_cache_path`. Existing `_discover_path` and `load_firm_config` are NOT touched (Cycle 6 territory, plan #13). |
| `tests/v3/config/test_firm.py` | Modify (append) | Adds 21 new test functions (9 + 8 + 4) and 2 new import blocks. No edits to existing tests. |

**Out of scope (handed to sibling plans):**
- `_write_cache` (Cycle 4) → plan #12
- `_read_shared_with_fallback` + `SharedConfigStalenessWarning` + `SharedConfigIntegrityWarning` (Cycle 5) → plan #12
- `load_firm_config(local_path=, shared_path=)` two-source signature, `_SHARED_REQUIRED_SECTIONS`, shared-side path validator, fixture migration, `config/firm.shared.dev.toml`, `config/README.md` (Cycle 6) → plan #13

**Public-surface decision deferred:** `CONVENTIONAL_SHARED_CONFIG_PATH` is added at module level but is NOT re-exported from `src/trust_generator/v3/config/__init__.py` by this plan. Plan #13 (integration) owns the public-API decision when wiring the loader signature.

---

## Task 1: Cycle 1 — `deep_merge`

**Spec ref:** §6.2 (cycle), §5.3 (merge contract).

**Files:**
- Modify: `src/trust_generator/v3/config/firm.py` (append after the existing `_USER_UPN_SENTINEL` constant block, before `class FirmConfigError`)
- Modify: `tests/v3/config/test_firm.py` (append at end of file)

### Stage 1.A — Red

- [ ] **Step 1: Add the failing tests + import**

Append to `tests/v3/config/test_firm.py`:

```python
# ─── Cycle 1: deep_merge (foundation plan §6.2) ────────────────────────────

from trust_generator.v3.config.firm import deep_merge


def test_deep_merge_both_empty_returns_empty() -> None:
    assert deep_merge({}, {}) == {}


def test_deep_merge_shared_only_passes_through() -> None:
    shared = {"a": 1, "section": {"b": 2}}
    assert deep_merge(shared, {}) == {"a": 1, "section": {"b": 2}}


def test_deep_merge_local_only_passes_through() -> None:
    local = {"a": 1, "section": {"b": 2}}
    assert deep_merge({}, local) == {"a": 1, "section": {"b": 2}}


def test_deep_merge_scalar_overlap_local_wins() -> None:
    assert deep_merge({"k": "shared"}, {"k": "local"}) == {"k": "local"}


def test_deep_merge_table_overlap_recurses() -> None:
    shared = {"section": {"a": 1, "b": 2}}
    local = {"section": {"b": 20, "c": 3}}
    assert deep_merge(shared, local) == {"section": {"a": 1, "b": 20, "c": 3}}


def test_deep_merge_list_overlap_extends_shared_first() -> None:
    shared = {"items": ["a", "b"]}
    local = {"items": ["c", "a"]}
    assert deep_merge(shared, local) == {"items": ["a", "b", "c", "a"]}


def test_deep_merge_empty_string_treated_as_unset() -> None:
    assert deep_merge({"k": "value"}, {"k": ""}) == {"k": "value"}


def test_deep_merge_empty_table_treated_as_no_op() -> None:
    shared = {"section": {"k": 1}}
    local = {"section": {}}
    assert deep_merge(shared, local) == {"section": {"k": 1}}


def test_deep_merge_inputs_not_mutated() -> None:
    shared = {"a": 1, "section": {"b": 2}}
    local = {"a": 10, "section": {"c": 3}}
    shared_snapshot = {"a": 1, "section": {"b": 2}}
    local_snapshot = {"a": 10, "section": {"c": 3}}
    deep_merge(shared, local)
    assert shared == shared_snapshot
    assert local == local_snapshot
```

Note: ruff (I001) may want this `from trust_generator.v3.config.firm import deep_merge` line hoisted to the top-of-file import block. Let it. After Cycle 1's Red lands, the consolidated module-level imports will look like:

```python
from trust_generator.v3.config.firm import deep_merge
```

right below the existing `from trust_generator.v3.config import (...)` block. If `pixi run lint` fails with I001, run `pixi run format` to auto-resolve.

- [ ] **Step 2: Verify red**

```bash
pixi run test test_deep_merge
```

Expected: `ImportError: cannot import name 'deep_merge' from 'trust_generator.v3.config.firm'`. The collection-level error blocks all 9 tests — that is the correct meaningful failure (the gap the cycle exists to fill).

- [ ] **Step 3: Commit red**

```bash
git add tests/v3/config/test_firm.py
git commit -m "test(v3/config): add deep_merge red tests (cycle 1)"
```

### Stage 1.B — Green

- [ ] **Step 4: Implement minimal `deep_merge`**

Append to `src/trust_generator/v3/config/firm.py` after the `_USER_UPN_SENTINEL` line (line 39), before `class FirmConfigError`. Adjust imports at the top of the file: change `from typing import Any, Final, Literal` to additionally import `Mapping`:

```python
from collections.abc import Mapping
```

Add the new module-level definitions:

```python
def deep_merge(
    shared: Mapping[str, Any], local: Mapping[str, Any]
) -> dict[str, Any]:
    result: dict[str, Any] = dict(shared)
    for key, local_value in local.items():
        if _is_empty(local_value):
            continue
        if (
            key in result
            and isinstance(result[key], Mapping)
            and isinstance(local_value, Mapping)
        ):
            result[key] = deep_merge(result[key], local_value)
        elif (
            key in result
            and isinstance(result[key], list)
            and isinstance(local_value, list)
        ):
            result[key] = list(result[key]) + list(local_value)
        else:
            result[key] = local_value
    return result


def _is_empty(value: Any) -> bool:
    return value == "" or value == {} or value == []
```

- [ ] **Step 5: Verify green**

```bash
pixi run test test_deep_merge
```

Expected: 9 passed.

- [ ] **Step 6: Commit green**

```bash
git add src/trust_generator/v3/config/firm.py
git commit -m "feat(v3/config): implement deep_merge utility (cycle 1)"
```

### Stage 1.C — Refactor

The cycle meets `refactor_threshold`: green-phase code has structural duplication (twin `key in result` + per-side `isinstance` clauses across the table and list branches), and `_is_empty` collapses three independent equality checks into a literal-set lookup. Spec §6.2 prescribes the exact refactored shape.

- [ ] **Step 7: Refactor `deep_merge` and `_is_empty`**

Replace the two function bodies in `src/trust_generator/v3/config/firm.py` with:

```python
def deep_merge(
    shared: Mapping[str, Any], local: Mapping[str, Any]
) -> dict[str, Any]:
    result: dict[str, Any] = dict(shared)
    for key, local_value in local.items():
        if _is_empty(local_value):
            continue
        existing = result.get(key)
        if isinstance(existing, Mapping) and isinstance(local_value, Mapping):
            result[key] = deep_merge(existing, local_value)
        elif isinstance(existing, list) and isinstance(local_value, list):
            result[key] = [*existing, *local_value]
        else:
            result[key] = local_value
    return result


_EMPTY_LITERALS: Final[tuple[str, dict[str, Any], list[Any]]] = ("", {}, [])


def _is_empty(value: Any) -> bool:
    return value in _EMPTY_LITERALS
```

The `result.get(key)` consolidates the existence-and-type check; `[*existing, *local_value]` reads more clearly than `list() + list()`; `_EMPTY_LITERALS` makes the rule's surface explicit and extensible.

- [ ] **Step 8: Verify refactor stays green**

```bash
pixi run test test_deep_merge
```

Expected: 9 passed (unchanged from Stage 1.B).

- [ ] **Step 9: Commit refactor**

```bash
git add src/trust_generator/v3/config/firm.py
git commit -m "refactor(v3/config): consolidate deep_merge dispatch (cycle 1)"
```

---

## Task 2: Cycle 2 — Discovery functions

**Spec ref:** §6.3 (cycle), §5.2 (discovery and path conventions).

**Files:**
- Modify: `src/trust_generator/v3/config/firm.py` (append discovery helpers + `CONVENTIONAL_SHARED_CONFIG_PATH` constant)
- Modify: `tests/v3/config/test_firm.py` (append 8 tests + import)

### Stage 2.A — Red

- [ ] **Step 1: Add the failing tests + imports**

Append to `tests/v3/config/test_firm.py`:

```python
# ─── Cycle 2: Discovery functions (foundation plan §6.3) ───────────────────

from trust_generator.v3.config.firm import (
    CONVENTIONAL_SHARED_CONFIG_PATH,
    _discover_local_path,
    _discover_shared_path,
)


def test_local_explicit_arg_wins(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("TGV3_FIRM_CONFIG", str(tmp_path / "from_env.toml"))
    explicit = tmp_path / "from_arg.toml"
    assert _discover_local_path(explicit) == explicit.resolve()


def test_local_env_var_used_when_no_arg(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    via_env = tmp_path / "from_env.toml"
    monkeypatch.setenv("TGV3_FIRM_CONFIG", str(via_env))
    assert _discover_local_path(None) == via_env.resolve()


def test_local_convention_used_when_no_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    assert _discover_local_path(None) == (
        tmp_path / "config" / "firm.toml"
    ).resolve()


def test_shared_explicit_arg_wins(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("TGV3_FIRM_SHARED_CONFIG", str(tmp_path / "env.toml"))
    explicit = tmp_path / "shared.toml"
    assert _discover_shared_path(explicit) == explicit.resolve()


def test_shared_env_var_used_when_no_arg(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    via_env = tmp_path / "shared_env.toml"
    monkeypatch.setenv("TGV3_FIRM_SHARED_CONFIG", str(via_env))
    assert _discover_shared_path(None) == via_env.resolve()


def test_shared_convention_uses_path_constant() -> None:
    assert _discover_shared_path(None) == (
        CONVENTIONAL_SHARED_CONFIG_PATH.expanduser().resolve()
    )


def test_shared_path_expanduser_applied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TGV3_FIRM_SHARED_CONFIG", "~/my-shared.toml")
    assert _discover_shared_path(None) == (
        Path.home() / "my-shared.toml"
    ).resolve()


def test_local_and_shared_independent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    explicit_local = tmp_path / "local.toml"
    monkeypatch.setenv("TGV3_FIRM_SHARED_CONFIG", str(tmp_path / "shared.toml"))
    assert _discover_local_path(explicit_local) == explicit_local.resolve()
    assert _discover_shared_path(None) == (tmp_path / "shared.toml").resolve()
```

ruff I001 will likely consolidate the two new firm-module imports into one block during `pixi run format`. Let it.

- [ ] **Step 2: Verify red**

```bash
pixi run test test_local_ test_shared_
```

Expected: `ImportError` on `CONVENTIONAL_SHARED_CONFIG_PATH`, `_discover_local_path`, `_discover_shared_path`.

- [ ] **Step 3: Commit red**

```bash
git add tests/v3/config/test_firm.py
git commit -m "test(v3/config): add discovery red tests (cycle 2)"
```

### Stage 2.B — Green

- [ ] **Step 4: Implement discovery helpers + path constant**

Append to `src/trust_generator/v3/config/firm.py` after the existing `_discover_path` function (around line 263). The new `CONVENTIONAL_SHARED_CONFIG_PATH` constant is added next to the other module-level path constants (near line 36):

Add at the constants block (around `DEFAULT_CONFIG_PATH`):

```python
CONVENTIONAL_SHARED_CONFIG_PATH: Final[Path] = Path(
    "~/Crosby and Crosby LLP/internal-applications - trust-generator"
    "/firm/config/firm.toml"
)
ENV_VAR_SHARED_CONFIG_PATH: Final[str] = "TGV3_FIRM_SHARED_CONFIG"
```

Add after the existing `_discover_path` function:

```python
def _discover_local_path(arg: Path | None) -> Path:
    if arg is not None:
        return arg.expanduser().resolve(strict=False)
    env = os.environ.get(ENV_VAR_CONFIG_PATH)
    if env:
        return Path(env).expanduser().resolve(strict=False)
    return (Path.cwd() / "config" / "firm.toml").resolve(strict=False)


def _discover_shared_path(arg: Path | None) -> Path:
    if arg is not None:
        return arg.expanduser().resolve(strict=False)
    env = os.environ.get(ENV_VAR_SHARED_CONFIG_PATH)
    if env:
        return Path(env).expanduser().resolve(strict=False)
    return CONVENTIONAL_SHARED_CONFIG_PATH.expanduser().resolve(strict=False)
```

Note on `ENV_VAR_SHARED_CONFIG_PATH`: introduced here for symmetry with the existing `ENV_VAR_CONFIG_PATH` constant (`firm.py:37`). The constant is module-level only; not re-exported by `__init__.py` in this plan.

- [ ] **Step 5: Verify green**

```bash
pixi run test test_local_ test_shared_
```

Expected: 8 passed.

- [ ] **Step 6: Commit green**

```bash
git add src/trust_generator/v3/config/firm.py
git commit -m "feat(v3/config): implement two-source discovery helpers (cycle 2)"
```

### Stage 2.C — Refactor

**No refactor stage — green output is already minimal.** The two helpers' shared shape (arg → env → default, with uniform `expanduser` + `resolve`) is already factored: each helper is three lines of dispatch plus a single default. Extracting the common shape into a higher-order helper (e.g., `_discover(arg, env_var, default)`) would add an abstraction layer for two call sites that diverge only on string literals and a constant. The cost (one more name, one more call frame, indirection on every lookup) outweighs the benefit (~3 duplicated lines saved). Per `.claude/rules/development-strategy.md` `<refactor_threshold if-none-met>`, this absence is recorded explicitly here rather than skipped silently.

---

## Task 3: Cycle 3 — `_cache_path`

**Spec ref:** §6.4 (cycle), §5.4.1 (cache directory).

**Files:**
- Modify: `src/trust_generator/v3/config/firm.py` (append `_cache_path`)
- Modify: `tests/v3/config/test_firm.py` (append 4 tests + `import sys` + import)

### Stage 3.A — Red

- [ ] **Step 1: Add the failing tests + imports**

Add `import sys` to the top-of-file stdlib import block in `tests/v3/config/test_firm.py` (it sorts after `import os`). Then append:

```python
# ─── Cycle 3: _cache_path (foundation plan §6.4) ───────────────────────────

from trust_generator.v3.config.firm import _cache_path


def test_windows_uses_localappdata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert _cache_path() == (
        tmp_path / "trust-generator" / "firm.shared.cache.toml"
    )


def test_windows_missing_localappdata_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    with pytest.raises(FirmConfigError):
        _cache_path()


def test_posix_uses_xdg_cache_home_when_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert _cache_path() == (
        tmp_path / "trust-generator" / "firm.shared.cache.toml"
    )


def test_posix_falls_back_to_home_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    expected = (
        Path.home() / ".cache" / "trust-generator" / "firm.shared.cache.toml"
    )
    assert _cache_path() == expected
```

- [ ] **Step 2: Verify red**

```bash
pixi run test test_windows_ test_posix_
```

Expected: `ImportError: cannot import name '_cache_path' from 'trust_generator.v3.config.firm'`.

- [ ] **Step 3: Commit red**

```bash
git add tests/v3/config/test_firm.py
git commit -m "test(v3/config): add _cache_path red tests (cycle 3)"
```

### Stage 3.B — Green

- [ ] **Step 4: Implement `_cache_path`**

Add `import sys` to the top of `src/trust_generator/v3/config/firm.py` if it is not already there (the stdlib imports block currently has `os`, `re`, `tomllib` — `sys` sorts before `tomllib`).

Append `_cache_path` after the discovery helpers from Cycle 2:

```python
def _cache_path() -> Path:
    if sys.platform == "win32":
        local_appdata = os.environ.get("LOCALAPPDATA")
        if not local_appdata:
            raise FirmConfigError(
                "LOCALAPPDATA environment variable is not set; "
                "cannot determine cache directory."
            )
        cache_dir = Path(local_appdata) / "trust-generator"
    else:
        xdg = os.environ.get("XDG_CACHE_HOME")
        cache_dir = (
            Path(xdg) if xdg else Path.home() / ".cache"
        ) / "trust-generator"
    return cache_dir / "firm.shared.cache.toml"
```

`FirmConfigError` is the existing exception class (`firm.py:42`); reuse — do NOT introduce a new type. Spec §5.6.3 / D-6 mandate a single exception class for all loader error paths.

- [ ] **Step 5: Verify green**

```bash
pixi run test test_windows_ test_posix_
```

Expected: 4 passed.

- [ ] **Step 6: Commit green**

```bash
git add src/trust_generator/v3/config/firm.py
git commit -m "feat(v3/config): implement _cache_path platform branching (cycle 3)"
```

### Stage 3.C — Refactor

**No refactor stage — green output is already minimal.** The function has two platform branches and one literal filename suffix. Extracting `"firm.shared.cache.toml"` to a constant is premature — referenced exactly once. Extracting the "trust-generator" subdirectory name is symmetric premature optimization for a single literal that the cache writer (Cycle 4) will not co-reference (it goes through `_cache_path()`, not the directory name). Per `.claude/rules/development-strategy.md` `<refactor_threshold if-none-met>`, this absence is recorded explicitly.

---

## Final verification

After all three Tasks land, run the full project gate to confirm no regressions in adjacent test_firm.py cases or other suites.

- [ ] **Final Step: Run the combined check**

```bash
pixi run check
```

Expected: lint clean, mypy clean, full test suite passes (existing tests + 21 new tests).

If lint surfaces import-ordering nits, run `pixi run format` and amend the relevant cycle's commit IS NOT PERMITTED (per CLAUDE.md "always create new commits, never `--amend`"). Instead, add a new commit `chore(v3/config): apply ruff import sorting` at the end.

---

## Self-review checklist

**Spec coverage:**
- §6.2 (Cycle 1, deep_merge) → Task 1 (all 9 enumerated tests, Green code, Refactor code)
- §6.3 (Cycle 2, discovery) → Task 2 (all 8 enumerated tests, Green code, explicit no-refactor rationale)
- §6.4 (Cycle 3, _cache_path) → Task 3 (all 4 enumerated tests, Green code, explicit no-refactor rationale)
- §5.2.3 (`CONVENTIONAL_SHARED_CONFIG_PATH` constant) → Task 2 Stage B
- §5.2.4 (expanduser + resolve uniform pipeline) → Task 2 Stage B (each helper)
- §5.3.1–§5.3.3 (recursion / list extend / empty-as-unset) → Task 1 tests 4, 5, 6, 7, 8
- §5.3.6 (input non-mutation) → Task 1 test 9
- §5.4.1 (cache directory branching) → Task 3 (all 4 tests)

**Out-of-scope items confirmed deferred:**
- `_write_cache` → plan #12 (cache)
- `_read_shared_with_fallback` + warnings → plan #12 (cache)
- `load_firm_config` two-source signature → plan #13 (integration)
- Public re-export of `CONVENTIONAL_SHARED_CONFIG_PATH` from `__init__.py` → plan #13

**Type consistency:** `deep_merge` returns `dict[str, Any]`, accepts `Mapping[str, Any]` — symmetric with the spec's signature in §5.3. The discovery helpers all return `Path`. `_cache_path` returns `Path` and raises `FirmConfigError` (existing class, reused). No method-name inconsistencies across cycles — each cycle exposes a distinct symbol with no overlap.

**Placeholder scan:** All test bodies are concrete; all Green code blocks contain runnable Python; all commit messages are spelled out; all run commands are exact `pixi run test <pattern>` or `pixi run check` invocations. No "TBD" / "etc." / "similar to above" left in.

**Spec deviation tracked in plan-md (intentional):** Spec §6.3 prescribes "extend the autouse `_clean_env` fixture to also clear `TGV3_FIRM_SHARED_CONFIG`." The existing fixture (`test_firm.py:67-70`) already strips every key starting with `ENV_PREFIX = "TGV3_"`, so the new env var is covered automatically. Plan-md does not action that step. If the executor finds the spec wording confusing, this paragraph is the authoritative interpretation.
