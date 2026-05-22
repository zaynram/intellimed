# Shared firm_config — Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Cycle blocks are XML-tagged for dispatcher-side cycle-scope addressing — see "Dispatch Protocol" below.

**Goal:** Land the public-API surface for the two-source firm-config loader. Composes the foundation plan's three primitives (`deep_merge`, two discovery chains, `_cache_path`) and the cache plan's read/write helpers (`_read_shared_with_fallback`, `_read_cache_or_raise`, `_write_cache`, `SharedConfigStalenessWarning`, `SharedConfigIntegrityWarning`) into the rewritten `load_firm_config(local_path=, shared_path=)`. Adds the shared-side relative-path validator (§5.3.7.3-4), the §5.4.8 partial-sync completeness check, the constant rename per §5.6.2, the `__init__.py` re-export delta, fixture migration in `test_firm.py`, the cross-caller migration in `test_config_integration.py`, the dev-environment template `config/firm.shared.dev.toml`, and the onboarding documentation `config/README.md`.

**Architecture:** Three TDD cycles plus three single-commit tasks. **Cycle 13-1** wires the two-source signature, helpers, fixture migration, cross-caller migration, constant rename, cache-write gate (D-11), and `${user.upn}` post-merge timing — covering spec §6.7 tests 1-11. **Cycle 13-2** wires the §5.4.8 partial-sync completeness check (`_SHARED_REQUIRED_SECTIONS` + the §5.4.8.3 re-route via direct `_read_cache_or_raise` call, no wrapper) — covering tests 12-13. **Task 13-3** pins the walker-coverage tripwire (test 14) as a regression-pin against silent under-enumeration of `_enumerate_path_fields`. **Task 13-4** is the cross-plan coordination audit — an adversarial review against drift between the three sibling plans' implementations and the spec. **Task 13-5** authors the dev-environment template and onboarding README per spec §8.2 step 0 + §10 chore #6. **Task 13-6** closes `.claude/context/plans.xml` entry 13 (dispatcher-owned per spec-pipeline invariant #5).

**Tech Stack:** Python 3.12 (pixi-pinned, do not invoke bare `python`), Pydantic v2, `tomllib` (stdlib, already imported in firm.py), `pathlib.Path`, `pytest` + `monkeypatch` + `pytest.raises` + `pytest.warns`, `warnings.warn`. No new dependencies. Project-internal imports only.

**Spec source:** `docs/superpowers/specs/2026-04-28-shared-firm-config-design.md` §5.3.7 (path resolution), §5.4.5–§5.4.8 (cache fallback error variants + completeness check), §5.6.1–§5.6.5 (loader API + signature change + constant rename + no-shim posture), §6.7 (Cycle 6 — `load_firm_config` integration), §8.2 step 0 (dev template), §10 chore #6 (onboarding doc), D-8 (no backward-compatibility shim), D-11 (cache write only on validation success).

**Plan-composition decisions recorded:**

- **Q1 — 3-cycle decomposition.** Spec §6.7 frames Cycle 6 as a single TDD cycle (Red + Green, no Refactor). The cache-plan drafter explicitly granted the integration drafter permission to sub-task ("the integration drafter should consider whether Cycle 6 needs sub-tasking ... to keep each commit's session-bounded"). Taking that permission. Decomposition: 13-1 = core integration + path validator + cache-write gate + fixture migration (tests 1-11); 13-2 = §5.4.8 completeness check (tests 12-13); 13-3 = walker tripwire (test 14, single-commit pin). Rationale: spec test 14 is a regression-pin against silent under-enumeration of `_enumerate_path_fields` (a bug at cycle 13-1's green that 11 other tests would NOT catch); landing it as its own commit documents the regression-pin intent at commit-message granularity. §5.4.8 is a discrete plan-review-round-2 addition with its own constant + warning routing + cache-write-gate property; folding it into 13-1 doubles the green-phase surface area in one session.

- **Q2 — Cross-plan coordination audit lands as task 13-4.** Three sibling plans (foundation #5, cache #12, integration #13) modify the same `firm.py` and `test_firm.py` sequentially. Coordination drift risks: symbol-name divergence (e.g., `DEFAULT_LOCAL_CONFIG_PATH` vs the cache drafter brief's `CONVENTIONAL_LOCAL_CONFIG_PATH` typo); helper-signature drift (the C1 finding's tuple shape); test-fixture leak between modules; constant-block organization across three append-only edits; lint-fix convention drift. The audit is dispatched to a fresh subagent with an adversarial prompt, runs after cycles 13-1/13-2 and task 13-3 land, and produces a structured report. Issues are classified blocker (HALT integration) or chore-grade (open via scope-maintenance protocol). The audit's gating role belongs BEFORE task 13-5 (dev template) so any blockers don't reach the documentation surface.

- **Q3 — `tests/v3/integration/test_config_integration.py` absorbed into cycle 13-1's blast radius.** Spec §5.6.4 names only `test_firm.py` for migration; `rg load_firm_config\(` surfaces a second caller (`test_config_integration.py:46,53`) using the old positional signature. Two options were considered: (a) absorb into 13-1's blast radius (mechanical 4-line update); (b) defer to a chore. Option (a) accepted: option (b) leaves main red between cycle 13-1 and the chore close, violating the post-cycle-green-pass invariant. The migration is mechanical: split the BODY constant into SHARED + LOCAL, two writes per test, keyword call form.

- **Q4 — D-11 cache-write gating uses `used_cache` boolean exclusively, not a re-query of `resolved_shared.exists()`.** The C1 plan-review finding (spec §6.6 "Note on the C1 finding") explicitly rejects collapsing the helper's tuple return to bare bytes + a re-`exists()` call: re-querying introduces a TOCTOU window where mid-load file-appears or file-disappears events corrupt the cache mtime or skip a cache write. Cycle 13-1 green's gate is `if not used_cache: _write_cache(shared_bytes)` literally — no `resolved_shared.exists()` re-check, no equivalent. Spec test 7 (`test_load_no_cache_write_on_integrity_fallback`) is the regression pin against accidental gate-by-exists() reintroduction.

- **Q5 — §5.4.8.3 partial-sync re-route is a direct call to `_read_cache_or_raise`, no wrapper.** Cache plan's keyword-only `_read_cache_or_raise(shared_path, *, warning_class, warning_phrasing, no_cache_error_template, integrity_reason=None)` was deliberately designed to be readable at the call site without intermediate naming. Cycle 13-2 green's re-route block calls it directly with the integrity warning class and `_INTEGRITY_ERROR_TEMPLATE`. No `_check_completeness_or_reroute` / `_validate_shared_completeness` / `_shared_with_validation` helper. Auditor (task 13-4) greps for these patterns to enforce.

- **Q6 — No double-parse, no `tomli_w` round-trip, no `_format_duration` redefinition.** The cache plan's `_read_shared_with_fallback` returns `tuple[bytes, dict[str, Any], bool]` exactly so cycle 13-1 green can consume the parsed dict directly without `tomllib.loads(shared_bytes)` re-parse. The verbatim source bytes (tuple position 0) feed directly into `_write_cache(shared_bytes)` without re-serialization through `tomli_w` or `toml.dumps(shared_dict)`. The cache plan's `_format_duration` handles age formatting inside `_read_cache_or_raise`; integration plan does NOT redefine it. Auditor enforces these via grep.

- **Q7 — Constant rename is `DEFAULT_LOCAL_CONFIG_PATH` (per spec §5.6.2), NOT `CONVENTIONAL_LOCAL_CONFIG_PATH`.** Cache drafter's handoff brief (item #8) had a typo. Spec §5.6.2 lines 1969-1977 specify `DEFAULT_LOCAL_CONFIG_PATH = Path("config/firm.toml")` replacing `DEFAULT_CONFIG_PATH`, and `ENV_VAR_LOCAL_CONFIG_PATH = "TGV3_FIRM_CONFIG"` replacing `ENV_VAR_CONFIG_PATH`. The "CONVENTIONAL_" prefix is reserved for the new shared-side constant `CONVENTIONAL_SHARED_CONFIG_PATH` (§5.2.3). Foundation plan introduced `CONVENTIONAL_SHARED_CONFIG_PATH` and `ENV_VAR_SHARED_CONFIG_PATH` at the constants block; integration plan renames the two old constants and updates foundation's `_discover_local_path` body (which references the soon-to-be-renamed `ENV_VAR_CONFIG_PATH`).

- **Q8 — `__init__.py` re-export delta.** Removed: `DEFAULT_CONFIG_PATH`, `ENV_VAR_CONFIG_PATH` (renamed). Added: `DEFAULT_LOCAL_CONFIG_PATH`, `ENV_VAR_LOCAL_CONFIG_PATH`, `ENV_VAR_SHARED_CONFIG_PATH`, `SharedConfigStalenessWarning`, `SharedConfigIntegrityWarning`. NOT re-exported (private per spec §5.6.2 line 1990): `CONVENTIONAL_SHARED_CONFIG_PATH`. RUF022 will alphabetize the resulting `__all__` on `pixi run fix`. Foundation plan deferred this re-export decision to integration plan #13 (foundation plan-md line 27).

- **Q9 — Scope-size threshold acceptance.** Integration plan touches 6 plan-executor-blast-radius files: `src/trust_generator/v3/config/firm.py` (modified), `src/trust_generator/v3/config/__init__.py` (modified), `tests/v3/config/test_firm.py` (modified), `tests/v3/integration/test_config_integration.py` (modified, the Q3 finding), `config/firm.shared.dev.toml` (created), `config/README.md` (created). Plus dispatcher-owned `.claude/context/plans.xml` (task 13-6). Logical complexity: 2 complex cycles (13-1, 13-2) + 1 mechanical pin (13-3) + 1 audit (13-4) + 1 mechanical docs task (13-5). CLAUDE.md soft-warn at >5 files / >2 complex tasks; hard-deny at >10 / >5. Sits at the soft-warn boundary on file count (6 > 5) and complexity (2 = limit, not exceeded). Mitigating factors: (a) all 4 modified files cluster around a single contract (the loader's two-source signature); no orthogonal surfaces; (b) the two created files are docs/data with one commit each; (c) the integration-test migration is 4 lines mechanical. 9c plan accepted a comparable edge (its Q8). Threshold acceptance recorded.

- **Q10 — Inside-out (Detroit/classicist) TDD with no mocks.** Per `.claude/rules/development-strategy.md` `methodology="test-driven-development" approach="inside-out"`. Cycle 13-1 uses no mocks: real `tmp_path` for both local and shared file fixtures, real `monkeypatch.setenv` for env-var discovery tests, real `pytest.warns` for warning emission. Cycle 13-2 uses no mocks: real partial-shared TOML fixtures missing one of `_SHARED_REQUIRED_SECTIONS`, real `pytest.warns(SharedConfigIntegrityWarning)`. Task 13-3 introspects `FirmConfig`'s field annotations directly via `_enumerate_path_fields` (no mocking of Pydantic).

- **Q11 — Refactor-stage discipline.** Per `.claude/rules/development-strategy.md` `<refactor_threshold>` (structural duplication / nested conditionals flatten into dispatch / mixed orthogonal concerns extract cleanly), and per spec §6.7's own refactor decision ("There is no structural duplication and no nested conditionals... Decision: no refactor stage"), neither cycle 13-1 nor cycle 13-2 includes a Refactor stage. Both record "no refactor stage — green output is already minimal" with reasoning at the cycle-end. Same precedent as foundation plan cycles 2 + 3 and 9c cycles 1 + 2.

---

## Dispatch Protocol

When invoking `/spec-pipeline 2026-04-29-shared-firm-config-integration exec-plan`, the dispatcher (you, or a routing skill) controls which cycles/tasks execute via a scope-token in the dispatcher prompt:

| Scope-token | Effect |
| ----------- | ------ |
| (no scope-token, or `cycles=all`) | Plan-executor walks `<cycle>` and `<task>` blocks in document order, executing each per its `commits` attribute. |
| `cycles=[13-1]` | Plan-executor opens only the cycle whose `id` attribute matches; verifies `depends-on` cycles' Green commits exist via `git log --grep`; executes Red→Green for that cycle alone. |
| `cycles=[13-1..13-3]` (inclusive range) | Plan-executor walks the contiguous cycle/task range; same dependency check at the range's lower bound. |
| `cycles=[13-1, 13-3]` (explicit list) | Plan-executor walks each id in the order supplied. Use sparingly — non-contiguous execution risks skipping a `depends-on` link. |

Each `<cycle>` and `<task>` block carries five attributes:

| Attribute        | Purpose                                                                                     |
| ---------------- | ------------------------------------------------------------------------------------------- |
| `id`             | Stable scope token (`13-1`, …, `13-6`).                                                     |
| `spec-ref`       | Backlink to the spec section(s) the cycle/task implements.                                  |
| `blast-radius`   | Semicolon-separated list of file paths the cycle/task is allowed to create or modify. Plan-executor must NOT edit any path outside this list during the cycle; new paths surfaced at green-time become chores via scope-maintenance. |
| `depends-on`     | Cycle/task-id list whose commits must already exist. Cycle 13-1 depends on foundation cycles 1 + 2 + 3 and cache cycles 4 + 5; cycles 13-2/13-3 depend on 13-1; tasks 13-4 + 13-5 depend on 13-3; task 13-6 depends on 13-5. |
| `commits`        | The cycle's commit shape — `red,green` (default for cycles 13-1, 13-2), `single` (for tasks 13-3, 13-5, 13-6), or `audit` (for task 13-4: zero commits if clean, N chore-open commits if issues found). |

The dispatching session retains responsibility for the post-execution close-out (review chore-list, commit `plans.xml` flip — invariant #5 in spec-pipeline SKILL.md).

---

## File Structure

**Created (production):**

| Path | Responsibility |
| ---- | -------------- |
| `config/firm.shared.dev.toml` | Task 13-5: dev-environment shared template per spec §8.2 step 0. Content = current `config/firm.toml` with the `[user]` section removed; `[meta]` retained. Devs without OneDrive set `TGV3_FIRM_SHARED_CONFIG=$(realpath config/firm.shared.dev.toml)` to load. |
| `config/README.md` | Task 13-5: onboarding doc per spec §10 chore #6. Documents the two-source loader's discovery chains (pointer to spec §5.2), the dev-environment env-var workflow, and the production-paralegal expectation that `config/` is NOT in the deployed bundle. |

**Modified (production):**

| Path | Change |
| ---- | ------ |
| `src/trust_generator/v3/config/firm.py` | Cycle 13-1: rename `DEFAULT_CONFIG_PATH` → `DEFAULT_LOCAL_CONFIG_PATH`; rename `ENV_VAR_CONFIG_PATH` → `ENV_VAR_LOCAL_CONFIG_PATH`; update foundation cycle 2's `_discover_local_path` body's `os.environ.get(ENV_VAR_CONFIG_PATH)` reference to the new constant name; add `_validate_shared_paths_absolute`, `_enumerate_path_fields`, `_get_dotted`, `_is_windows_absolute`; rewrite `load_firm_config` per spec §6.7 green; update `_resolve_paths` caller (anchor change from `resolved.parent` to `resolved_local.parent`); delete the old `_discover_path` (dead code post-rewrite). Cycle 13-2: add `_SHARED_REQUIRED_SECTIONS: Final[frozenset[str]]`; add the §5.4.8.3 re-route block to `load_firm_config` between `_read_shared_with_fallback` and `deep_merge`. |
| `src/trust_generator/v3/config/__init__.py` | Cycle 13-1: remove `DEFAULT_CONFIG_PATH` + `ENV_VAR_CONFIG_PATH`; add `DEFAULT_LOCAL_CONFIG_PATH` + `ENV_VAR_LOCAL_CONFIG_PATH` + `ENV_VAR_SHARED_CONFIG_PATH` + `SharedConfigStalenessWarning` + `SharedConfigIntegrityWarning`; update `__all__` (RUF022 alphabetizes). Do NOT re-export `CONVENTIONAL_SHARED_CONFIG_PATH` (private per spec §5.6.2). |

**Modified (tests):**

| Path | Change |
| ---- | ------ |
| `tests/v3/config/test_firm.py` | Cycle 13-1: rewrite imports; split `WELL_FORMED` → `WELL_FORMED_SHARED` + `WELL_FORMED_LOCAL`; split `MINIMAL` → `MINIMAL_SHARED` + `MINIMAL_LOCAL`; migrate every existing test's call site from `load_firm_config(path)` to `load_firm_config(local_path=, shared_path=)` (~30 tests); update `test_constants_match_spec` for renamed + new constants; rename `test_relative_paths_resolve_against_config_parent` → `test_relative_paths_resolve_against_local_parent` and relocate the relative-path declaration to LOCAL (per spec §5.3.7.3); add 11 new tests covering spec §6.7 tests 1-11. Cycle 13-2: add 2 new tests covering spec §6.7 tests 12-13. Task 13-3: add 1 new test covering spec §6.7 test 14. |
| `tests/v3/integration/test_config_integration.py` | Cycle 13-1: split `BODY` → `SHARED_BODY` + `LOCAL_BODY`; update both test functions to do two writes and call `load_firm_config(local_path=, shared_path=)`. Mechanical 4-line edit per the Q3 finding. |

**Created via task 13-4 if audit surfaces issues:**

| Path | Conditional |
| ---- | ----------- |
| `.claude/context/chores.xml` | Task 13-4: zero or more chore entries opened per scope-maintenance protocol. Each chore documents one drift finding from the audit. NOT a created file (chores.xml exists); just appended-to. |

**Modified (metadata):**

| Path | Change |
| ---- | ------ |
| `.claude/context/plans.xml` | Task 13-6: set `status="closed"` on plan #13 entry; bump `modified-at`. **Dispatcher-owned** per spec-pipeline invariant #5. |

**Total executor-blast-radius file count:** 6 (2 created, 4 modified). Plus dispatcher-owned `.claude/context/plans.xml`. See Q9 for threshold-acceptance reasoning.

---

## Predecessor verification (run once before any cycle)

Gating, not implementing. If any check fails, escalate — there is no "stub-and-skip" path per cache drafter's handoff item #6.

- [ ] **Step P1: Verify foundation plan #5 closed**

```bash
grep -A2 'id="2026-04-29-shared-firm-config-foundation"' .claude/context/plans.xml | grep 'status='
```

Expected: `status="closed"`. If `status="open"`: foundation has not landed; halt and execute foundation plan first (`/spec-pipeline 2026-04-29-shared-firm-config-foundation exec-plan`).

- [ ] **Step P2: Verify cache plan #12 closed**

```bash
grep -A2 'id="2026-04-29-shared-firm-config-cache"' .claude/context/plans.xml | grep 'status='
```

Expected: `status="closed"`. If `status="open"`: cache has not landed; halt and execute cache plan first (`/spec-pipeline 2026-04-29-shared-firm-config-cache exec-plan`).

- [ ] **Step P3: Verify foundation + cache cycle commits exist**

```bash
git log --oneline --grep='cycle [1-5])$' | wc -l
```

Expected: `≥11`. Counting: foundation cycle 1 (Red + Green + Refactor = 3), cycle 2 (Red + Green = 2), cycle 3 (Red + Green = 2) = 7; cache cycle 4 (Red + Green = 2), cycle 5 (Red + Green = 2) = 4; total = 11. If less than 11: a predecessor cycle is missing a commit; halt and reconcile.

- [ ] **Step P4: Verify foundation + cache symbols importable**

```bash
pixi run python -c "from trust_generator.v3.config.firm import (
    deep_merge,
    _is_empty,
    _EMPTY_LITERALS,
    _discover_local_path,
    _discover_shared_path,
    CONVENTIONAL_SHARED_CONFIG_PATH,
    ENV_VAR_SHARED_CONFIG_PATH,
    _cache_path,
    _write_cache,
    _read_shared_with_fallback,
    _read_cache_or_raise,
    _format_duration,
    SharedConfigStalenessWarning,
    SharedConfigIntegrityWarning,
)
print('ok')"
```

Expected: `ok` (no traceback). If `ImportError`: a predecessor symbol drifted; halt and reconcile (likely points to a foundation or cache plan deviation from spec).

- [ ] **Step P5: Verify pre-existing constants still present (rename target)**

```bash
pixi run python -c "from trust_generator.v3.config.firm import DEFAULT_CONFIG_PATH, ENV_VAR_CONFIG_PATH; print('ok')"
```

Expected: `ok`. These constants still exist at this point (foundation explicitly does NOT touch them per its plan-md line 19). Cycle 13-1 renames them. If this import fails BEFORE cycle 13-1: a predecessor cycle accidentally renamed/removed them; halt.

- [ ] **Step P6: Verify project gate green pre-cycle**

```bash
pixi run check
```

Expected: lint passes, mypy passes, all tests pass, exit code 0. If non-green: halt — integration starts from a green baseline so each cycle's red/green delta is unambiguous.

- [ ] **Step P7: Verify feature branch (not main)**

```bash
git branch --show-current
```

Expected: a branch name that is NOT `main` or `master`. The current working branch (per session start: `v3.0.0`) is fine.

---

## Cycle 13-1 — Core integration

<cycle id="13-1"
       spec-ref="§6.7 tests 1-11; §5.6.1-§5.6.4 (signature, public symbols, exception surface, no-shim posture); §5.3.7.2-§5.3.7.5 (path resolution + walker); §5.4.7 (helper-return contract); D-8, D-11"
       blast-radius="src/trust_generator/v3/config/firm.py; src/trust_generator/v3/config/__init__.py; tests/v3/config/test_firm.py; tests/v3/integration/test_config_integration.py"
       depends-on="foundation-cycle-1, foundation-cycle-2, foundation-cycle-3, cache-cycle-4, cache-cycle-5"
       commits="red,green">

**Refactor decision:** No refactor stage. Per spec §6.7 Refactor: "The integration is now an 11-step linear sequence... There is no structural duplication and no nested conditionals. The composition is intentional and reads top-to-bottom. Decision: no refactor stage." Cycle 13-1 honors that decision verbatim. The green-phase code is the spec's pseudocode adapted to absorb the constant rename, the cross-caller migration, the validator addition, and the dead-code deletion of `_discover_path`.

**Files:**

- Modify: `src/trust_generator/v3/config/firm.py`
- Modify: `src/trust_generator/v3/config/__init__.py`
- Modify: `tests/v3/config/test_firm.py`
- Modify: `tests/v3/integration/test_config_integration.py`

### Stage 1.A — Red

Red lands the test-side migration + new tests + cross-caller updates. After Red commit, the test suite is fully updated to expect the new signature; the production code is unchanged so all migrated tests (existing + new) fail.

- [ ] **Step 1: Update `tests/v3/config/test_firm.py` imports**

Edit `tests/v3/config/test_firm.py` lines 10-17 (the import-from block from `trust_generator.v3.config`). Replace the current block:

```python
from trust_generator.v3.config import (
    DEFAULT_CONFIG_PATH,
    ENV_PREFIX,
    ENV_VAR_CONFIG_PATH,
    FirmConfig,
    FirmConfigError,
    load_firm_config,
)
```

with the new block:

```python
from trust_generator.v3.config import (
    DEFAULT_LOCAL_CONFIG_PATH,
    ENV_PREFIX,
    ENV_VAR_LOCAL_CONFIG_PATH,
    ENV_VAR_SHARED_CONFIG_PATH,
    FirmConfig,
    FirmConfigError,
    SharedConfigIntegrityWarning,
    SharedConfigStalenessWarning,
    load_firm_config,
)
```

The new symbols are alphabetized (RUF022 will enforce). `SharedConfigIntegrityWarning` is imported now even though it's only used in cycle 13-2 tests — a single edit is cleaner than re-touching the import block in 13-2.

- [ ] **Step 2: Split fixture constants**

Replace the `WELL_FORMED` constant (lines 19-37 of the current file, the multi-line TOML string) with a placeholder constant + two split constants. The placeholder constant **forecasts cycle 13-2's `_SHARED_REQUIRED_SECTIONS` membership check**: cycle 13-1 lands during Red before that constant exists, but the migrated fixtures need to satisfy it the moment cycle 13-2 Green wires the check, or every legacy test using `WELL_FORMED_SHARED` would regress. Concatenating the placeholders onto `WELL_FORMED_SHARED` (and only that one — see asymmetric-application paragraph after `MINIMAL_*`) avoids a follow-up patch.

```python
# Required-sections placeholders. Concatenated onto WELL_FORMED_SHARED so the
# fixture survives cycle 13-2's _SHARED_REQUIRED_SECTIONS membership check
# (which lands in cycle 13-2 Green). Empty section bodies suffice — the check
# is for section presence, not content. Tests that need to populate these
# sections splice content into these placeholders via `.replace()` rather
# than appending duplicate headers.
_REQUIRED_SECTION_PLACEHOLDERS = """
[estate_thresholds]
[diagnostics]
"""

WELL_FORMED_SHARED = """
[firm]
name = "Test Firm LLP"
phone = "(555) 555-5555"

[firm.office_address]
street = "1 Main St."
city = "Rockford"
state = "IL"
zip_code = "61114"

[jurisdiction]
default_state = "Illinois"
default_county = "Winnebago"
trust_code_citation = "Illinois Trust Code (760 ILCS 3/101, et seq.)"
""" + _REQUIRED_SECTION_PLACEHOLDERS


WELL_FORMED_LOCAL = """
[user]
upn = "testuser"
"""
```

Replace the `MINIMAL` constant (lines 40-58) with two constants:

```python
MINIMAL_SHARED = """
[firm]
name = "Minimal LLP"
phone = "(555) 000-0000"

[firm.office_address]
street = "1 Way"
city = "City"
state = "XX"
zip_code = "00000"

[jurisdiction]
default_state = "Illinois"
default_county = "Winnebago"
trust_code_citation = "Illinois Trust Code"
"""


MINIMAL_LOCAL = """
[user]
upn = "testuser"
"""
```

The `[user]` section moves to the LOCAL fixture; everything else stays in SHARED. This matches spec §6.7 Migration paragraph: "`MINIMAL_SHARED` and `MINIMAL_LOCAL` follow the same split shape."

**Asymmetric application of `_REQUIRED_SECTION_PLACEHOLDERS`.** Only `WELL_FORMED_SHARED` concatenates the placeholders; `MINIMAL_SHARED` deliberately omits them. Reason: cycle 13-2 test 13 (the missing-sections rejection test, spec §6.7 test 13) consumes `MINIMAL_SHARED` and asserts that a shared file lacking `[estate_thresholds]` and `[diagnostics]` triggers the `_SHARED_REQUIRED_SECTIONS` re-route. Adding placeholders to `MINIMAL_SHARED` would silently satisfy the check and destroy the test's trigger. The asymmetry is intent-preserving: `WELL_FORMED_*` is the "happy-path" fixture (must survive every downstream gate, including the cycle 13-2 check); `MINIMAL_*` is the "minimal-coverage" fixture (deliberately incomplete to exercise the missing-sections path). Any future required-section addition to `_SHARED_REQUIRED_SECTIONS` must update `_REQUIRED_SECTION_PLACEHOLDERS` in lockstep but must NOT touch `MINIMAL_SHARED`.

- [ ] **Step 3: Rewrite `test_constants_match_spec`**

Replace the current `test_constants_match_spec` function (lines 73-76) with:

```python
def test_constants_match_spec() -> None:
    assert DEFAULT_LOCAL_CONFIG_PATH == Path("config/firm.toml")
    assert ENV_VAR_LOCAL_CONFIG_PATH == "TGV3_FIRM_CONFIG"
    assert ENV_VAR_SHARED_CONFIG_PATH == "TGV3_FIRM_SHARED_CONFIG"
    assert ENV_PREFIX == "TGV3_"
```

The renamed constants keep their values (per spec §5.6.2: "The string value is unchanged so existing environment-variable bindings keep working"). The new shared env-var assertion lands here.

- [ ] **Step 4: Migrate every existing test's call site**

For every test function in `test_firm.py` from line 79 (`test_happy_path_loads_expected_values`) through the file end, rewrite the body to use two writes and the keyword call form. The migration follows a repeatable pattern:

**Pattern A — tests using `WELL_FORMED` directly:** Replace
```python
path = _write(tmp_path / "firm.toml", WELL_FORMED)
cfg = load_firm_config(path)
```
with
```python
local = _write(tmp_path / "local.toml", WELL_FORMED_LOCAL)
shared = _write(tmp_path / "shared.toml", WELL_FORMED_SHARED)
cfg = load_firm_config(local_path=local, shared_path=shared)
```

**Pattern B — tests appending to `WELL_FORMED`:** for tests that build a body via `WELL_FORMED + """[section]\n..."""`, route the appended section into the SIDE matching the test's intent (per spec §6.7 Migration paragraph: "the appended section goes into `WELL_FORMED_LOCAL` if the test exercises a local-side override path or into `WELL_FORMED_SHARED` if the test exercises firm-wide defaults"). The specific routing for each test is enumerated below.

**Pattern C — tests using `MINIMAL` directly:** Same as Pattern A with `MINIMAL_SHARED` / `MINIMAL_LOCAL`.

**Pattern D — tests calling `load_firm_config(None)` for default-discovery:** Replace `load_firm_config(None)` with `load_firm_config()` (no args; both kwargs default to `None`). For tests using `monkeypatch.chdir(tmp_path)` to simulate the discovery default, the test must also write BOTH `tmp_path / "config" / "firm.toml"` (local default) AND set up a shared discovery path (env var or file at the conventional path).

Concrete migrations follow. Each line shows the **post-migration** body of the named test function:

For `test_happy_path_loads_expected_values(tmp_path: Path) -> None`:

```python
def test_happy_path_loads_expected_values(tmp_path: Path) -> None:
    local = _write(tmp_path / "local.toml", WELL_FORMED_LOCAL)
    shared = _write(tmp_path / "shared.toml", WELL_FORMED_SHARED)
    cfg = load_firm_config(local_path=local, shared_path=shared)
    assert isinstance(cfg, FirmConfig)
    assert cfg.firm.name == "Test Firm LLP"
    assert cfg.firm.phone == "(555) 555-5555"
    assert cfg.firm.office_address.zip_code == "61114"
```

For `test_minimal_file_yields_section_defaults(tmp_path: Path) -> None`:

```python
def test_minimal_file_yields_section_defaults(tmp_path: Path) -> None:
    local = _write(tmp_path / "local.toml", MINIMAL_LOCAL)
    shared = _write(tmp_path / "shared.toml", MINIMAL_SHARED)
    cfg = load_firm_config(local_path=local, shared_path=shared)
    # ... rest of the assertions unchanged from current line 91 onwards
```

For `test_missing_required_firm_name_raises(tmp_path: Path) -> None`:

```python
def test_missing_required_firm_name_raises(tmp_path: Path) -> None:
    broken_shared = WELL_FORMED_SHARED.replace('name = "Test Firm LLP"\n', "")
    local = _write(tmp_path / "local.toml", WELL_FORMED_LOCAL)
    shared = _write(tmp_path / "shared.toml", broken_shared)
    with pytest.raises(FirmConfigError):
        load_firm_config(local_path=local, shared_path=shared)
```

For `test_cross_field_hard_less_than_soft_raises(tmp_path: Path) -> None`:

```python
def test_cross_field_hard_less_than_soft_raises(tmp_path: Path) -> None:
    bad_shared = WELL_FORMED_SHARED + """
[estate_thresholds]
single_soft = 5_000_000
single_hard = 4_000_000
"""
    local = _write(tmp_path / "local.toml", WELL_FORMED_LOCAL)
    shared = _write(tmp_path / "shared.toml", bad_shared)
    with pytest.raises(FirmConfigError):
        load_firm_config(local_path=local, shared_path=shared)
```

The `[estate_thresholds]` section is firm-policy-bearing per spec §5.4.8.1 — appended to SHARED.

For `test_env_overlay_overrides_toml(monkeypatch, tmp_path)`:

```python
def test_env_overlay_overrides_toml(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    local = _write(tmp_path / "local.toml", WELL_FORMED_LOCAL)
    shared = _write(tmp_path / "shared.toml", WELL_FORMED_SHARED)
    monkeypatch.setenv("TGV3_FIRM__NAME", "EnvOverride LLP")
    cfg = load_firm_config(local_path=local, shared_path=shared)
    assert cfg.firm.name == "EnvOverride LLP"
```

For `test_relative_paths_resolve_against_config_parent` — **rename to `test_relative_paths_resolve_against_local_parent`** and route the relative-path declaration to LOCAL (per spec §5.3.7.3, shared-side relative paths are forbidden). New body:

```python
def test_relative_paths_resolve_against_local_parent(tmp_path: Path) -> None:
    local_dir = tmp_path / "nested"
    local_dir.mkdir()
    local_body = WELL_FORMED_LOCAL + """
[diagnostics]
audit_log_dir = "./relative/audit"
"""
    local = _write(local_dir / "local.toml", local_body)
    shared = _write(tmp_path / "shared.toml", WELL_FORMED_SHARED)
    cfg = load_firm_config(local_path=local, shared_path=shared)
    assert cfg.diagnostics.audit_log_dir == (local_dir / "relative" / "audit").resolve()
```

The `nested/` subdirectory is a deliberate observability trick (per spec §6.7 test 9: "with the local file in a `nested/` subdirectory so the difference between local-parent and CWD is observable").

For `test_absolute_paths_preserved(tmp_path)`:

```python
def test_absolute_paths_preserved(tmp_path: Path) -> None:
    abs_audit = tmp_path / "absolute" / "audit"
    local_body = WELL_FORMED_LOCAL + f"""
[diagnostics]
audit_log_dir = "{abs_audit}"
"""
    local = _write(tmp_path / "local.toml", local_body)
    shared = _write(tmp_path / "shared.toml", WELL_FORMED_SHARED)
    cfg = load_firm_config(local_path=local, shared_path=shared)
    assert cfg.diagnostics.audit_log_dir == abs_audit.resolve()
```

For `test_strict_extra_outside_meta_rejects_unknown_key(tmp_path)`:

```python
def test_strict_extra_outside_meta_rejects_unknown_key(tmp_path: Path) -> None:
    bad_shared = WELL_FORMED_SHARED.replace(
        "trust_code_citation = ", 'unknown_key = "junk"\ntrust_code_citation = '
    )
    local = _write(tmp_path / "local.toml", WELL_FORMED_LOCAL)
    shared = _write(tmp_path / "shared.toml", bad_shared)
    with pytest.raises(FirmConfigError):
        load_firm_config(local_path=local, shared_path=shared)
```

For `test_meta_accepts_unknown_keys(tmp_path)`:

```python
def test_meta_accepts_unknown_keys(tmp_path: Path) -> None:
    shared_body = WELL_FORMED_SHARED + """
[meta]
custom_key = "custom_value"
"""
    local = _write(tmp_path / "local.toml", WELL_FORMED_LOCAL)
    shared = _write(tmp_path / "shared.toml", shared_body)
    cfg = load_firm_config(local_path=local, shared_path=shared)
    assert cfg.meta.custom_key == "custom_value"  # type: ignore[attr-defined]
```

`[meta]` is firm-side metadata; routed to SHARED.

For `test_discovery_explicit_path_wins_over_env(monkeypatch, tmp_path)`:

```python
def test_discovery_explicit_path_wins_over_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    explicit_local = _write(tmp_path / "explicit.toml", WELL_FORMED_LOCAL)
    other_local = _write(
        tmp_path / "from_env.toml",
        WELL_FORMED_LOCAL.replace("testuser", "envuser"),
    )
    shared = _write(tmp_path / "shared.toml", WELL_FORMED_SHARED)
    monkeypatch.setenv("TGV3_FIRM_CONFIG", str(other_local))
    monkeypatch.setenv("TGV3_FIRM_SHARED_CONFIG", str(shared))
    cfg = load_firm_config(local_path=explicit_local)
    assert cfg.user.upn == "testuser"  # explicit local wins, not env-pointed local
```

For `test_discovery_env_wins_over_default(monkeypatch, tmp_path)`:

```python
def test_discovery_env_wins_over_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    via_env_local = _write(tmp_path / "via_env.toml", WELL_FORMED_LOCAL)
    shared = _write(tmp_path / "shared.toml", WELL_FORMED_SHARED)
    monkeypatch.setenv("TGV3_FIRM_CONFIG", str(via_env_local))
    monkeypatch.setenv("TGV3_FIRM_SHARED_CONFIG", str(shared))
    cfg = load_firm_config()
    assert cfg.user.upn == "testuser"
```

For `test_missing_file_raises(tmp_path)` — currently `load_firm_config(tmp_path / "does_not_exist.toml")`. Under the new signature, missing-local raises with the local-specific message:

```python
def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FirmConfigError, match="local firm.toml not found"):
        load_firm_config(local_path=tmp_path / "does_not_exist.toml")
```

For `test_approaching_cliff_ratio_bounds(tmp_path)`:

```python
def test_approaching_cliff_ratio_bounds(tmp_path: Path) -> None:
    bad_shared = WELL_FORMED_SHARED + """
[estate_thresholds]
approaching_cliff_ratio = 1.5
"""
    local = _write(tmp_path / "local.toml", WELL_FORMED_LOCAL)
    shared = _write(tmp_path / "shared.toml", bad_shared)
    with pytest.raises(FirmConfigError):
        load_firm_config(local_path=local, shared_path=shared)
```

For `test_us_zip_format_validator_accepts_canonical_shapes(tmp_path)`:

```python
def test_us_zip_format_validator_accepts_canonical_shapes(tmp_path: Path) -> None:
    plus_four_shared = WELL_FORMED_SHARED.replace(
        'zip_code = "61114"', 'zip_code = "61114-1234"'
    )
    local = _write(tmp_path / "local.toml", WELL_FORMED_LOCAL)
    shared = _write(tmp_path / "shared.toml", plus_four_shared)
    cfg = load_firm_config(local_path=local, shared_path=shared)
    assert cfg.firm.office_address.zip_code == "61114-1234"
```

For `test_us_zip_format_validator_rejects_malformed(tmp_path)`:

```python
def test_us_zip_format_validator_rejects_malformed(tmp_path: Path) -> None:
    bad_shared = WELL_FORMED_SHARED.replace(
        'zip_code = "61114"', 'zip_code = "abcde"'
    )
    local = _write(tmp_path / "local.toml", WELL_FORMED_LOCAL)
    shared = _write(tmp_path / "shared.toml", bad_shared)
    with pytest.raises(FirmConfigError):
        load_firm_config(local_path=local, shared_path=shared)
```

For `test_us_zip_format_validator_skipped_for_non_us_country(tmp_path)`:

```python
def test_us_zip_format_validator_skipped_for_non_us_country(tmp_path: Path) -> None:
    non_us_shared = WELL_FORMED_SHARED.replace(
        'state = "IL"',
        'state = "ON"\ncountry = "CA"',
    )
    local = _write(tmp_path / "local.toml", WELL_FORMED_LOCAL)
    shared = _write(tmp_path / "shared.toml", non_us_shared)
    cfg = load_firm_config(local_path=local, shared_path=shared)
    assert cfg.firm.office_address.country == "CA"
```

For `test_fdic_api_base_must_be_http_url(tmp_path)`:

```python
def test_fdic_api_base_must_be_http_url(tmp_path: Path) -> None:
    bad_shared = WELL_FORMED_SHARED + """
[trustee_catalog]
fdic_api_base = "not-a-url"
"""
    local = _write(tmp_path / "local.toml", WELL_FORMED_LOCAL)
    shared = _write(tmp_path / "shared.toml", bad_shared)
    with pytest.raises(FirmConfigError):
        load_firm_config(local_path=local, shared_path=shared)
```

For `test_user_upn_is_loaded(tmp_path)`:

```python
def test_user_upn_is_loaded(tmp_path: Path) -> None:
    local = _write(tmp_path / "local.toml", WELL_FORMED_LOCAL)
    shared = _write(tmp_path / "shared.toml", WELL_FORMED_SHARED)
    cfg = load_firm_config(local_path=local, shared_path=shared)
    assert cfg.user.upn == "testuser"
```

For `test_missing_user_section_raises(tmp_path)`:

```python
def test_missing_user_section_raises(tmp_path: Path) -> None:
    no_user_local = WELL_FORMED_LOCAL.replace('[user]\nupn = "testuser"\n', "")
    local = _write(tmp_path / "local.toml", no_user_local)
    shared = _write(tmp_path / "shared.toml", WELL_FORMED_SHARED)
    with pytest.raises(FirmConfigError):
        load_firm_config(local_path=local, shared_path=shared)
```

For `test_empty_user_upn_rejected(tmp_path)`:

```python
def test_empty_user_upn_rejected(tmp_path: Path) -> None:
    empty_local = WELL_FORMED_LOCAL.replace('upn = "testuser"', 'upn = ""')
    local = _write(tmp_path / "local.toml", empty_local)
    shared = _write(tmp_path / "shared.toml", WELL_FORMED_SHARED)
    with pytest.raises(FirmConfigError):
        load_firm_config(local_path=local, shared_path=shared)
```

For `test_whitespace_only_user_upn_rejected(tmp_path)`:

```python
def test_whitespace_only_user_upn_rejected(tmp_path: Path) -> None:
    blank_local = WELL_FORMED_LOCAL.replace('upn = "testuser"', 'upn = "   "')
    local = _write(tmp_path / "local.toml", blank_local)
    shared = _write(tmp_path / "shared.toml", WELL_FORMED_SHARED)
    with pytest.raises(FirmConfigError):
        load_firm_config(local_path=local, shared_path=shared)
```

For `test_tilde_in_audit_log_dir_expands_to_home(tmp_path)`:

```python
def test_tilde_in_audit_log_dir_expands_to_home(tmp_path: Path) -> None:
    local_body = WELL_FORMED_LOCAL + """
[diagnostics]
audit_log_dir = "~/firm-logs/audit"
"""
    local = _write(tmp_path / "local.toml", local_body)
    shared = _write(tmp_path / "shared.toml", WELL_FORMED_SHARED)
    cfg = load_firm_config(local_path=local, shared_path=shared)
    assert cfg.diagnostics.audit_log_dir == (
        Path.home() / "firm-logs" / "audit"
    ).resolve()
```

For `test_tilde_expansion_applies_to_all_path_fields(tmp_path)`:

```python
def test_tilde_expansion_applies_to_all_path_fields(tmp_path: Path) -> None:
    local_body = WELL_FORMED_LOCAL + """
[trustee_catalog]
db_path = "~/data/catalog.sqlite"

[diagnostics]
audit_log_dir = "~/logs/audit"
rules_dir = "~/config/rules"
"""
    local = _write(tmp_path / "local.toml", local_body)
    shared = _write(tmp_path / "shared.toml", WELL_FORMED_SHARED)
    cfg = load_firm_config(local_path=local, shared_path=shared)
    assert cfg.trustee_catalog.db_path == (
        Path.home() / "data" / "catalog.sqlite"
    ).resolve()
    assert cfg.diagnostics.audit_log_dir == (
        Path.home() / "logs" / "audit"
    ).resolve()
    assert cfg.diagnostics.rules_dir == (
        Path.home() / "config" / "rules"
    ).resolve()
```

For `test_user_upn_substitution_in_audit_log_dir(tmp_path)`:

```python
def test_user_upn_substitution_in_audit_log_dir(tmp_path: Path) -> None:
    local_body = WELL_FORMED_LOCAL + """
[diagnostics]
audit_log_dir = "~/firm-logs/users/${user.upn}/logs"
"""
    local = _write(tmp_path / "local.toml", local_body)
    shared = _write(tmp_path / "shared.toml", WELL_FORMED_SHARED)
    cfg = load_firm_config(local_path=local, shared_path=shared)
    assert cfg.diagnostics.audit_log_dir == (
        Path.home() / "firm-logs" / "users" / "testuser" / "logs"
    ).resolve()
```

For `test_user_upn_substitution_scoped_to_audit_log_dir_only(tmp_path)`:

```python
def test_user_upn_substitution_scoped_to_audit_log_dir_only(tmp_path: Path) -> None:
    local_body = WELL_FORMED_LOCAL + """
[trustee_catalog]
db_path = "~/data/${user.upn}/catalog.sqlite"
"""
    local = _write(tmp_path / "local.toml", local_body)
    shared = _write(tmp_path / "shared.toml", WELL_FORMED_SHARED)
    cfg = load_firm_config(local_path=local, shared_path=shared)
    # ${user.upn} is NOT substituted in trustee_catalog.db_path
    assert "${user.upn}" in str(cfg.trustee_catalog.db_path)
```

For `test_path_resolution_order_substitute_then_expand_then_resolve(tmp_path)`:

```python
def test_path_resolution_order_substitute_then_expand_then_resolve(
    tmp_path: Path,
) -> None:
    local_body = WELL_FORMED_LOCAL.replace(
        'upn = "testuser"', 'upn = "myuser"'
    ) + """
[diagnostics]
audit_log_dir = "~/firm-logs/${user.upn}"
"""
    local = _write(tmp_path / "local.toml", local_body)
    shared = _write(tmp_path / "shared.toml", WELL_FORMED_SHARED)
    cfg = load_firm_config(local_path=local, shared_path=shared)
    assert cfg.diagnostics.audit_log_dir == (
        Path.home() / "firm-logs" / "myuser"
    ).resolve()
```

For `test_absolute_audit_log_dir_still_gets_substitution(tmp_path)`:

```python
def test_absolute_audit_log_dir_still_gets_substitution(tmp_path: Path) -> None:
    abs_dir = tmp_path / "logs" / "${user.upn}"
    local_body = WELL_FORMED_LOCAL + f"""
[diagnostics]
audit_log_dir = "{abs_dir}"
"""
    local = _write(tmp_path / "local.toml", local_body)
    shared = _write(tmp_path / "shared.toml", WELL_FORMED_SHARED)
    cfg = load_firm_config(local_path=local, shared_path=shared)
    assert cfg.diagnostics.audit_log_dir == (
        tmp_path / "logs" / "testuser"
    ).resolve()
```

For `test_path_resolution_errors_wrapped_as_firm_config_error(monkeypatch, tmp_path)`:

```python
def test_path_resolution_errors_wrapped_as_firm_config_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def boom(self: Path) -> Path:
        raise OSError("simulated symlink loop")
    monkeypatch.setattr(Path, "resolve", boom)
    local = _write(tmp_path / "local.toml", WELL_FORMED_LOCAL)
    shared = _write(tmp_path / "shared.toml", WELL_FORMED_SHARED)
    with pytest.raises(FirmConfigError, match="path resolution failed"):
        load_firm_config(local_path=local, shared_path=shared)
```

This concludes the migration of all existing tests. The pattern is uniform: two writes per test (local + shared); keyword call form; `WELL_FORMED_LOCAL` for `[user]`-side concerns and `WELL_FORMED_SHARED` for everything else.

- [ ] **Step 5: Add 11 new tests for spec §6.7 tests 1-11**

Append to `tests/v3/config/test_firm.py` after the migrated tests:

```python
# ─── Cycle 13-1: load_firm_config two-source integration (spec §6.7) ─────────


def test_load_with_explicit_paths_succeeds(tmp_path: Path) -> None:
    """Spec §6.7 test 1: explicit local_path + shared_path returns merged FirmConfig."""
    local = _write(tmp_path / "local.toml", WELL_FORMED_LOCAL)
    shared = _write(tmp_path / "shared.toml", WELL_FORMED_SHARED)
    cfg = load_firm_config(local_path=local, shared_path=shared)
    assert cfg.firm.name == "Test Firm LLP"  # from shared
    assert cfg.user.upn == "testuser"  # from local


def test_load_writes_cache_on_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Spec §6.7 test 2: successful load with reachable shared writes the cache."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    local = _write(tmp_path / "local.toml", WELL_FORMED_LOCAL)
    shared = _write(tmp_path / "shared.toml", WELL_FORMED_SHARED)
    load_firm_config(local_path=local, shared_path=shared)
    cache_file = (
        tmp_path / "cache" / "trust-generator" / "firm.shared.cache.toml"
    )
    assert cache_file.exists()
    assert cache_file.read_bytes() == shared.read_bytes()


def test_load_default_paths_use_discovery_chains(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Spec §6.7 test 3: no-args call uses both env-var discovery chains independently."""
    local = _write(tmp_path / "via_local_env.toml", WELL_FORMED_LOCAL)
    shared = _write(tmp_path / "via_shared_env.toml", WELL_FORMED_SHARED)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("TGV3_FIRM_CONFIG", str(local))
    monkeypatch.setenv("TGV3_FIRM_SHARED_CONFIG", str(shared))
    cfg = load_firm_config()
    assert cfg.user.upn == "testuser"
    assert cfg.firm.name == "Test Firm LLP"


def test_load_keyword_path_alias_not_supported(tmp_path: Path) -> None:
    """Spec §6.7 test 4: legacy `path=` kwarg raises TypeError per §5.6.4 no-shim."""
    with pytest.raises(TypeError):
        load_firm_config(path=tmp_path / "firm.toml")  # type: ignore[call-arg]


def test_load_uses_cache_when_shared_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Spec §6.7 test 5: missing shared + present cache emits one staleness warning."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    cache_dir = tmp_path / "cache" / "trust-generator"
    cache_dir.mkdir(parents=True)
    (cache_dir / "firm.shared.cache.toml").write_bytes(WELL_FORMED_SHARED.encode())
    local = _write(tmp_path / "local.toml", WELL_FORMED_LOCAL)
    missing_shared = tmp_path / "does-not-exist.toml"
    with pytest.warns(SharedConfigStalenessWarning) as captured:
        cfg = load_firm_config(local_path=local, shared_path=missing_shared)
    assert cfg.firm.name == "Test Firm LLP"
    assert len(captured) == 1


def test_load_no_cache_write_on_availability_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Spec §6.7 test 6: case-2/3 fallback does not modify cache mtime."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    cache_dir = tmp_path / "cache" / "trust-generator"
    cache_dir.mkdir(parents=True)
    cache_file = cache_dir / "firm.shared.cache.toml"
    cache_file.write_bytes(WELL_FORMED_SHARED.encode())
    initial_mtime = cache_file.stat().st_mtime
    local = _write(tmp_path / "local.toml", WELL_FORMED_LOCAL)
    missing_shared = tmp_path / "does-not-exist.toml"
    with pytest.warns(SharedConfigStalenessWarning):
        load_firm_config(local_path=local, shared_path=missing_shared)
    assert cache_file.stat().st_mtime == initial_mtime


def test_load_no_cache_write_on_integrity_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Spec §6.7 test 7 (C1-fix regression pin): malformed shared + cache used does not write cache."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    cache_dir = tmp_path / "cache" / "trust-generator"
    cache_dir.mkdir(parents=True)
    cache_file = cache_dir / "firm.shared.cache.toml"
    cache_file.write_bytes(WELL_FORMED_SHARED.encode())
    initial_mtime = cache_file.stat().st_mtime
    local = _write(tmp_path / "local.toml", WELL_FORMED_LOCAL)
    malformed_shared = _write(tmp_path / "shared.toml", "not = valid = toml = at = all")
    with pytest.warns(SharedConfigIntegrityWarning):
        load_firm_config(local_path=local, shared_path=malformed_shared)
    assert cache_file.stat().st_mtime == initial_mtime


def test_load_validation_error_does_not_write_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Spec §6.7 test 8: validation failure on merged dict skips cache write (D-11)."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    cache_dir = tmp_path / "cache" / "trust-generator"
    cache_dir.mkdir(parents=True)
    cache_file = cache_dir / "firm.shared.cache.toml"
    cache_file.write_bytes(b"# pre-existing cache content\n")
    initial_mtime = cache_file.stat().st_mtime
    local = _write(tmp_path / "local.toml", WELL_FORMED_LOCAL)
    bad_shared = _write(
        tmp_path / "shared.toml",
        WELL_FORMED_SHARED + '\n[estate_thresholds]\nsingle_soft = -1\n',
    )
    with pytest.raises(FirmConfigError):
        load_firm_config(local_path=local, shared_path=bad_shared)
    assert cache_file.stat().st_mtime == initial_mtime


def test_relative_paths_resolve_against_local_parent_new(tmp_path: Path) -> None:
    """Spec §6.7 test 9: confirms anchor identity is resolved_local.parent.

    NOTE: this test deliberately differs from the renamed migrated test
    (test_relative_paths_resolve_against_local_parent) by using a deeper
    nested directory structure to make the local-parent vs CWD difference
    unambiguous in the assertion path.
    """
    nested = tmp_path / "nested" / "deep"
    nested.mkdir(parents=True)
    local_body = WELL_FORMED_LOCAL + """
[diagnostics]
audit_log_dir = "./relative/audit"
"""
    local = _write(nested / "local.toml", local_body)
    shared = _write(tmp_path / "shared.toml", WELL_FORMED_SHARED)
    cfg = load_firm_config(local_path=local, shared_path=shared)
    expected = (nested / "relative" / "audit").resolve()
    assert cfg.diagnostics.audit_log_dir == expected


@pytest.mark.parametrize(
    "field_path",
    [
        "trustee_catalog.db_path",
        "diagnostics.audit_log_dir",
        "diagnostics.rules_dir",
    ],
)
def test_shared_side_relative_path_rejected(
    tmp_path: Path, field_path: str
) -> None:
    """Spec §6.7 test 10: relative path declared in SHARED raises with field name + value."""
    section, field = field_path.split(".")
    shared_body = WELL_FORMED_SHARED + f"""
[{section}]
{field} = "./relative/path"
"""
    local = _write(tmp_path / "local.toml", WELL_FORMED_LOCAL)
    shared = _write(tmp_path / "shared.toml", shared_body)
    with pytest.raises(FirmConfigError, match=field_path) as exc_info:
        load_firm_config(local_path=local, shared_path=shared)
    assert "./relative/path" in str(exc_info.value)


def test_user_upn_substitution_uses_post_merge_user_value(tmp_path: Path) -> None:
    """Spec §6.7 test 11: ${user.upn} substitution happens after merge."""
    shared_body = WELL_FORMED_SHARED + """
[diagnostics]
audit_log_dir = "~/firm-logs/users/${user.upn}/logs"
"""
    local = _write(tmp_path / "local.toml", WELL_FORMED_LOCAL)
    shared = _write(tmp_path / "shared.toml", shared_body)
    cfg = load_firm_config(local_path=local, shared_path=shared)
    expected = (Path.home() / "firm-logs" / "users" / "testuser" / "logs").resolve()
    assert cfg.diagnostics.audit_log_dir == expected
```

The 11 new tests cover spec §6.7 tests 1-11 verbatim. The shared-side relative-path test (test 10) uses `pytest.mark.parametrize` to cover all three Path-typed fields per spec wording ("Verified across all three Path-typed fields").

- [ ] **Step 6: Migrate `tests/v3/integration/test_config_integration.py`**

Replace the `BODY` constant (lines 16-41) with two constants:

```python
SHARED_BODY = """
[firm]
name = "Integration Firm LLP"
phone = "(555) 000-0000"

[firm.office_address]
street = "1 Way"
city = "City"
state = "IL"
zip_code = "61114"

[jurisdiction]
default_state = "Illinois"
default_county = "Winnebago"
trust_code_citation = "Illinois Trust Code"

[trustee_catalog]
fdic_api_base = "https://example.test/fdic-api"
fdic_request_timeout_s = 45

[diagnostics]
default_restriction_level = "warning"
"""


LOCAL_BODY = """
[user]
upn = "testuser"
"""
```

Replace `test_trustee_catalog_consumer_reads_from_config(tmp_path)` (lines 44-48):

```python
def test_trustee_catalog_consumer_reads_from_config(tmp_path: Path) -> None:
    (tmp_path / "shared.toml").write_text(SHARED_BODY, encoding="utf-8")
    (tmp_path / "local.toml").write_text(LOCAL_BODY, encoding="utf-8")
    cfg = load_firm_config(
        local_path=tmp_path / "local.toml",
        shared_path=tmp_path / "shared.toml",
    )
    assert str(cfg.trustee_catalog.fdic_api_base).startswith(
        "https://example.test/"
    )
    assert cfg.trustee_catalog.fdic_request_timeout_s == 45
```

Replace `test_diagnostics_consumer_reads_default_restriction_level(tmp_path)` (lines 51-54):

```python
def test_diagnostics_consumer_reads_default_restriction_level(
    tmp_path: Path,
) -> None:
    (tmp_path / "shared.toml").write_text(SHARED_BODY, encoding="utf-8")
    (tmp_path / "local.toml").write_text(LOCAL_BODY, encoding="utf-8")
    cfg = load_firm_config(
        local_path=tmp_path / "local.toml",
        shared_path=tmp_path / "shared.toml",
    )
    assert cfg.diagnostics.default_restriction_level == "warning"
```

- [ ] **Step 7: Run pixi run test, verify all red**

```bash
pixi run test v3/config v3/integration
```

Expected: ImportError on `DEFAULT_LOCAL_CONFIG_PATH`, `ENV_VAR_LOCAL_CONFIG_PATH`, `ENV_VAR_SHARED_CONFIG_PATH`, `SharedConfigStalenessWarning`, `SharedConfigIntegrityWarning` — collection-level error blocks all tests in the affected modules. The collection-level error IS the meaningful failure for this Red commit (the gap the cycle exists to fill: the renamed/new public symbols don't exist yet).

If pytest collection succeeds despite missing imports (it should NOT), individual tests will fail with `TypeError: load_firm_config() got an unexpected keyword argument 'local_path'` — also valid Red.

- [ ] **Step 8: Commit Red**

```bash
git add tests/v3/config/test_firm.py tests/v3/integration/test_config_integration.py
git commit -m "test(v3/config): add load_firm_config two-source red tests + fixture migration (cycle 13-1)"
```

### Stage 1.B — Green

Green lands the production-side rename + helpers + load_firm_config rewrite + dead-code deletion + `__init__.py` updates. After Green commit, the test suite is fully green for cycles 13-1's scope (spec §6.7 tests 1-11 plus all migrated existing tests; the §5.4.8 completeness check from cycle 13-2 is not yet wired, so test 12-13 do not exist yet).

- [ ] **Step 9: Rename module-level constants in `firm.py`**

Edit `src/trust_generator/v3/config/firm.py`. Replace the constant block at lines 36-37:

```python
DEFAULT_CONFIG_PATH: Final[Path] = Path("config/firm.toml")
ENV_VAR_CONFIG_PATH: Final[str] = "TGV3_FIRM_CONFIG"
```

with:

```python
DEFAULT_LOCAL_CONFIG_PATH: Final[Path] = Path("config/firm.toml")
ENV_VAR_LOCAL_CONFIG_PATH: Final[str] = "TGV3_FIRM_CONFIG"
```

The string values are unchanged (per spec §5.6.2: "The string value is unchanged so existing environment-variable bindings keep working"). Only the Python identifiers change.

- [ ] **Step 10: Update foundation cycle 2's `_discover_local_path` body**

Foundation plan introduced `_discover_local_path` referencing `ENV_VAR_CONFIG_PATH`. After step 9 renames the constant, `_discover_local_path`'s body must reference `ENV_VAR_LOCAL_CONFIG_PATH`. Find the line:

```python
    env = os.environ.get(ENV_VAR_CONFIG_PATH)
```

inside `_discover_local_path`, and replace with:

```python
    env = os.environ.get(ENV_VAR_LOCAL_CONFIG_PATH)
```

- [ ] **Step 11: Add path-validator helpers**

Append to `src/trust_generator/v3/config/firm.py` after `_cache_path` (introduced by foundation cycle 3) and before `_resolve_paths`:

```python
def _enumerate_path_fields(schema: type[BaseModel]) -> list[str]:
    """Yield dotted-key strings for every Path-typed field on `schema`.

    Walks the model's nested model fields one level deep (TGv3's `FirmConfig`
    has Path fields exclusively in direct sub-models; deeper recursion is
    not exercised by the current schema and is deferred per spec §5.3.7.5).
    """
    out: list[str] = []
    for top_name, top_field in schema.model_fields.items():
        annotation = top_field.annotation
        if annotation is None:
            continue
        if not isinstance(annotation, type):
            continue
        if not issubclass(annotation, BaseModel):
            continue
        for sub_name, sub_field in annotation.model_fields.items():
            sub_annotation = sub_field.annotation
            if sub_annotation is Path:
                out.append(f"{top_name}.{sub_name}")
    return out


def _get_dotted(d: dict[str, Any], dotted_key: str) -> str | None:
    """Look up a dotted-key path in a nested dict; return None if absent.

    Returns the value as a `str` if present (TOML serialization always yields
    string for path-typed fields pre-validation). Returns None if any segment
    along the path is missing.
    """
    parts = dotted_key.split(".")
    current: Any = d
    for part in parts:
        if not isinstance(current, dict):
            return None
        if part not in current:
            return None
        current = current[part]
    return current if isinstance(current, str) else None


def _is_windows_absolute(value: str) -> bool:
    """Return True if `value` looks like a Windows absolute path.

    Matches drive-letter prefixes (`C:\\`, `D:\\`, etc.) and UNC prefixes
    (`\\\\`). Used by the shared-side relative-path validator to recognize
    cross-platform absolute paths since `os.path.isabs` is platform-dependent.
    """
    if len(value) >= 3 and value[1] == ":" and value[2] in ("\\", "/"):
        return True
    return value.startswith("\\\\")


def _validate_shared_paths_absolute(
    shared_dict: dict[str, Any],
    schema: type[BaseModel] = FirmConfig,
) -> None:
    """Reject relative paths declared in shared per spec §5.3.7.3-4.

    Iterates every Path-typed field in `schema` (via `_enumerate_path_fields`),
    looks up the corresponding value in `shared_dict` (via `_get_dotted`),
    and rejects values that are not absolute, tilde-prefixed, or Windows-
    style absolute. Raises `FirmConfigError` with the dotted field name
    and the rejected value in the message per spec §5.6.3.
    """
    for dotted_key in _enumerate_path_fields(schema):
        value = _get_dotted(shared_dict, dotted_key)
        if value is None:
            continue
        if not (
            value.startswith("/")
            or value.startswith("~")
            or _is_windows_absolute(value)
        ):
            raise FirmConfigError(
                f"shared firm.toml field {dotted_key} must be absolute or "
                f"tilde-prefixed; got {value!r}. Relative paths in shared "
                f"have ambiguous semantics across workstations and are "
                f"not permitted."
            )
```

The four helpers are private (leading-underscore convention per spec §5.6.2 line 1990). They are imported by `load_firm_config` only.

- [ ] **Step 12: Rewrite `load_firm_config`**

Replace the entire `load_firm_config` function body (current lines 296-350) with the spec §6.7 green pseudocode adapted to the project:

```python
def load_firm_config(
    local_path: Path | None = None,
    shared_path: Path | None = None,
) -> FirmConfig:
    """Load, validate, and return the firm configuration from two sources.

    Discovery order for the LOCAL TOML file (workstation-specific):

    1. ``local_path`` argument, if provided.
    2. ``$TGV3_FIRM_CONFIG`` environment variable, if set.
    3. ``./config/firm.toml`` relative to CWD.

    Discovery order for the SHARED TOML file (firm-wide, SharePoint-hosted):

    1. ``shared_path`` argument, if provided.
    2. ``$TGV3_FIRM_SHARED_CONFIG`` environment variable, if set.
    3. ``CONVENTIONAL_SHARED_CONFIG_PATH`` (OneDrive-synced library default).

    Merge precedence: shared file provides firm-wide policy; local file
    overrides per-workstation values. Empty TOML literals on the local
    side are treated as unset (per spec §5.3.3).

    Cache fallback: on shared-file unavailability or integrity failure,
    falls back to a local cache file at `%LOCALAPPDATA%/trust-generator/...`
    (Windows) or `${XDG_CACHE_HOME:-~/.cache}/trust-generator/...` (POSIX),
    emitting `SharedConfigStalenessWarning` or `SharedConfigIntegrityWarning`.

    Path resolution: ``${user.upn}`` substitution applies to
    `diagnostics.audit_log_dir`; relative paths in LOCAL resolve against
    the local file's parent directory. Relative paths in SHARED are rejected.

    Raises:
        FirmConfigError: on missing local file, parse error, validation
            error, shared-side relative-path declaration, missing required
            shared section (cycle 13-2), or unrecoverable cache state.
    """
    resolved_local = _discover_local_path(local_path)
    resolved_shared = _discover_shared_path(shared_path)

    if not resolved_local.exists():
        raise FirmConfigError(
            f"local firm.toml not found at {resolved_local}"
        )

    shared_bytes, shared_dict, used_cache = _read_shared_with_fallback(
        resolved_shared
    )

    _validate_shared_paths_absolute(shared_dict)

    local_bytes = resolved_local.read_bytes()
    try:
        local_dict = tomllib.loads(local_bytes.decode("utf-8-sig"))
    except tomllib.TOMLDecodeError as exc:
        raise FirmConfigError(
            f"local firm.toml at {resolved_local} is malformed: {exc}"
        ) from exc

    merged = deep_merge(shared_dict, local_dict)

    try:
        cfg = FirmConfig(**merged)
    except ValidationError as exc:
        raise FirmConfigError(str(exc)) from exc

    try:
        cfg = _resolve_paths(cfg, resolved_local.parent)
    except (OSError, RuntimeError) as exc:
        raise FirmConfigError(
            f"firm_config path resolution failed for "
            f"local={resolved_local}: {exc}"
        ) from exc

    if not used_cache:
        _write_cache(shared_bytes)

    return cfg
```

**D-11 invariant pinned:** the cache write at the bottom is gated on `if not used_cache:` — the helper's authoritative signal — and runs AFTER `FirmConfig(**merged)` validation succeeds and AFTER `_resolve_paths` succeeds. No `if resolved_shared.exists():` re-check (the C1 finding's TOCTOU hole). Validation failures raise before reaching the cache write; integrity-fallback or staleness-fallback set `used_cache=True` so the gate skips.

- [ ] **Step 13: Delete the old `_discover_path` function**

Find the current `_discover_path` function body (currently around line 257-263, after `FirmConfig` and before `_resolve_paths`):

```python
def _discover_path(path: Path | None) -> Path:
    if path is not None:
        return Path(path)
    env_value = os.environ.get(ENV_VAR_CONFIG_PATH)
    if env_value:
        return Path(env_value)
    return DEFAULT_CONFIG_PATH
```

Delete it entirely. After step 9-10 it would have a `NameError` on `ENV_VAR_CONFIG_PATH` and `DEFAULT_CONFIG_PATH` — but the rewrite of `load_firm_config` (step 12) no longer calls it, so this is dead code. Removing eliminates a stale reference.

- [ ] **Step 14: Update `src/trust_generator/v3/config/__init__.py` re-exports**

Replace the entire current file content with:

```python
"""TGv3 firm configuration package.

Exposes the canonical ``FirmConfig`` settings object, the ``load_firm_config``
loader, and the two warning classes the loader emits on cache fallback.
The loader is the only public entry point; construct ``FirmConfig`` directly
only in tests.
"""

from trust_generator.v3.config.firm import (
    DEFAULT_LOCAL_CONFIG_PATH,
    ENV_PREFIX,
    ENV_VAR_LOCAL_CONFIG_PATH,
    ENV_VAR_SHARED_CONFIG_PATH,
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
    User,
    load_firm_config,
)

__all__ = [
    "DEFAULT_LOCAL_CONFIG_PATH",
    "ENV_PREFIX",
    "ENV_VAR_LOCAL_CONFIG_PATH",
    "ENV_VAR_SHARED_CONFIG_PATH",
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
    "User",
    "load_firm_config",
]
```

`CONVENTIONAL_SHARED_CONFIG_PATH` is intentionally NOT re-exported (private per spec §5.6.2 line 1990). RUF022 will keep `__all__` alphabetized on `pixi run fix`.

- [ ] **Step 15: Run pixi run test, verify green**

```bash
pixi run test v3/config v3/integration
```

Expected: all migrated tests + the 11 new tests + `test_config_integration.py` tests pass. Total green count for the cycle's scope: ~30 migrated + 11 new + 2 integration-test = ~43 tests. (Cycle 13-2's tests 12-13 do not yet exist; cycle 13-3's test 14 does not yet exist.)

- [ ] **Step 16: Run pixi run check for full project gate**

```bash
pixi run check
```

Expected: lint clean, mypy clean, full test suite passes. If lint surfaces RUF022 import-sort or I001 import-block nits, run `pixi run format` and add a follow-up commit named `chore(v3/config): apply ruff import sorting (cycle 13-1)`. Per CLAUDE.md, never `--amend`.

- [ ] **Step 17: Commit Green**

```bash
git add src/trust_generator/v3/config/firm.py src/trust_generator/v3/config/__init__.py
git commit -m "feat(v3/config): implement two-source load_firm_config + path validator (cycle 13-1)"
```

</cycle>

---

## Cycle 13-2 — Shared completeness check (§5.4.8)

<cycle id="13-2"
       spec-ref="§5.4.8.1-§5.4.8.5; §6.7 tests 12-13"
       blast-radius="src/trust_generator/v3/config/firm.py; tests/v3/config/test_firm.py; tests/v3/integration/test_config_integration.py"
       depends-on="13-1"
       commits="red,green">

**Refactor decision:** No refactor stage. The §5.4.8.3 re-route is a single conditional block inserted between `_read_shared_with_fallback` and `deep_merge` in `load_firm_config`. It calls `_read_cache_or_raise` directly with the partial-sync warning phrasing per spec §5.4.8.3 sample code (lines 1538-1556). No structural duplication, no nested conditionals, no orthogonal concerns. Per `.claude/rules/development-strategy.md` `<refactor_threshold if-none-met>`, the absence is recorded explicitly.

**Files:**

- Modify: `src/trust_generator/v3/config/firm.py`
- Modify: `tests/v3/config/test_firm.py`

### Stage 2.A — Red

- [ ] **Step 1: Append two new tests to `test_firm.py`**

Append after the cycle-13-1 tests:

```python
# ─── Cycle 13-2: Shared completeness check (spec §5.4.8) ─────────────────────


@pytest.mark.parametrize(
    "missing_section",
    ["firm", "estate_thresholds", "diagnostics"],
)
def test_load_partial_shared_falls_back_to_cache_with_integrity_warning(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, missing_section: str
) -> None:
    """Spec §6.7 test 12: partial shared (parses but missing required section) → cache + integrity warning."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    cache_dir = tmp_path / "cache" / "trust-generator"
    cache_dir.mkdir(parents=True)
    cache_file = cache_dir / "firm.shared.cache.toml"
    cache_file.write_bytes(WELL_FORMED_SHARED.encode())
    initial_mtime = cache_file.stat().st_mtime

    # Build a parseable shared file missing one required section.
    partial_lines = [
        line
        for line in WELL_FORMED_SHARED.splitlines(keepends=True)
        if not line.startswith(f"[{missing_section}")
        and not (
            missing_section == "firm"
            and line.startswith("[firm.")
        )
    ]
    # firm-section requires the firm.office_address subsection too;
    # the predicate above strips both [firm] and [firm.office_address].
    partial_shared_text = "".join(partial_lines)
    if missing_section == "firm":
        # Strip firm-section field assignments too (name/phone) since
        # they exist outside the section header in the original.
        pass
    # `estate_thresholds` and `diagnostics` are not in WELL_FORMED_SHARED;
    # we add a placeholder section to ensure the check sees them as
    # required-but-missing rather than required-and-absent-but-not-the-test.
    if missing_section == "estate_thresholds":
        partial_shared_text += '\n[estate_thresholds]\n# stripped for test\n'
        partial_shared_text = partial_shared_text.replace(
            '\n[estate_thresholds]\n# stripped for test\n', ''
        )
    if missing_section == "diagnostics":
        partial_shared_text += '\n[diagnostics]\n# stripped for test\n'
        partial_shared_text = partial_shared_text.replace(
            '\n[diagnostics]\n# stripped for test\n', ''
        )

    local = _write(tmp_path / "local.toml", WELL_FORMED_LOCAL)
    shared = _write(tmp_path / "shared.toml", partial_shared_text)
    with pytest.warns(SharedConfigIntegrityWarning) as captured:
        cfg = load_firm_config(local_path=local, shared_path=shared)
    assert len(captured) == 1
    assert missing_section in str(captured[0].message)
    # Cache used for actual config (cache had WELL_FORMED_SHARED).
    assert cfg.firm.name == "Test Firm LLP"
    # Cache mtime unchanged (no cache write on integrity-fallback).
    assert cache_file.stat().st_mtime == initial_mtime


def test_load_partial_shared_no_cache_raises_with_missing_sections_message(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Spec §6.7 test 13: partial shared + no cache raises with section list in message."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "no-cache"))
    # Build a shared file missing `estate_thresholds` (which isn't in
    # WELL_FORMED_SHARED to begin with). For this test, build from MINIMAL_SHARED
    # which also lacks estate_thresholds + diagnostics.
    local = _write(tmp_path / "local.toml", WELL_FORMED_LOCAL)
    shared = _write(tmp_path / "shared.toml", MINIMAL_SHARED)
    with pytest.raises(FirmConfigError, match="missing required section") as exc_info:
        load_firm_config(local_path=local, shared_path=shared)
    msg = str(exc_info.value)
    assert "estate_thresholds" in msg or "diagnostics" in msg
```

The first test is parameterized across the three sections in `_SHARED_REQUIRED_SECTIONS`; it asserts the integrity warning fires and cache mtime is unchanged. The second test asserts the no-cache error variant per spec §5.4.5.2 names the missing sections.

- [ ] **Step 2: Run tests, verify red**

```bash
pixi run test test_load_partial_shared
```

Expected: tests fail because `_SHARED_REQUIRED_SECTIONS` is not yet defined and the completeness check is not yet wired into `load_firm_config`. The first test will fail on the assertion `assert len(captured) == 1` (no integrity warning is emitted because the check is absent — instead the load proceeds with partial shared content, which then fails Pydantic validation with a different error). The second test will fail because the partial shared content silently passes through and hits some Pydantic validation error rather than the spec-mandated "missing required section" message.

- [ ] **Step 3: Commit Red**

```bash
git add tests/v3/config/test_firm.py
git commit -m "test(v3/config): add §5.4.8 shared completeness check red tests (cycle 13-2)"
```

### Stage 2.B — Green

- [ ] **Step 4: Add `_SHARED_REQUIRED_SECTIONS` constant**

Append to `src/trust_generator/v3/config/firm.py` near the other module-level constants (after `_USER_UPN_SENTINEL`):

```python
_SHARED_REQUIRED_SECTIONS: Final[frozenset[str]] = frozenset({
    "firm",
    "estate_thresholds",
    "diagnostics",
})
```

The constant is module-private (leading-underscore convention; spec §5.6.2 line 1989 lists it as private; spec §5.4.8.4 confirms tests in the same package import it directly).

- [ ] **Step 5: Wire the §5.4.8.3 re-route into `load_firm_config`**

Edit the `load_firm_config` body. After the line:

```python
    shared_bytes, shared_dict, used_cache = _read_shared_with_fallback(
        resolved_shared
    )
```

and BEFORE the line:

```python
    _validate_shared_paths_absolute(shared_dict)
```

insert the §5.4.8.3 partial-sync re-route block (per spec §5.4.8.3 sample code, lines 1535-1557):

```python
    # Spec §5.4.8: shared completeness check. If shared was reachable
    # (used_cache is False) but is missing one of _SHARED_REQUIRED_SECTIONS,
    # route to integrity-fallback. Cache-side reads (used_cache already True)
    # cannot be partial in a recoverable way — a parsed cache missing
    # required sections is a corrupt cache, surfaced separately via
    # _read_cache_or_raise's existing corruption error path.
    if not used_cache:
        missing = _SHARED_REQUIRED_SECTIONS - set(shared_dict.keys())
        if missing:
            shared_bytes, shared_dict, used_cache = _read_cache_or_raise(
                resolved_shared,
                warning_class=SharedConfigIntegrityWarning,
                warning_phrasing=(
                    f"is missing required section(s) "
                    f"{sorted(missing)} (likely partial OneDrive sync)"
                ),
                no_cache_error_template=_INTEGRITY_ERROR_TEMPLATE,
                integrity_reason=(
                    f"missing required section(s): {sorted(missing)}"
                ),
            )
```

The re-route is a direct call to the cache plan's `_read_cache_or_raise` — no wrapper helper, per Q5. After the re-route runs, `used_cache=True` (the second tuple position from `_read_cache_or_raise`) gates the cache write off at the function bottom — which is the correct behavior per Q4 + spec test 7's regression-pin philosophy.

`_INTEGRITY_ERROR_TEMPLATE` is imported from the cache plan's module-level error templates (introduced in cycle 5).

- [ ] **Step 6: Run pixi run test, verify green**

```bash
pixi run test test_load_partial_shared
```

Expected: both new tests pass. The parametrized test fires once per missing section (3 cases) — total 4 passes.

- [ ] **Step 7: Run pixi run check for full gate**

```bash
pixi run check
```

Expected: lint + mypy + full suite green.

- [ ] **Step 8: Commit Green**

```bash
git add src/trust_generator/v3/config/firm.py
git commit -m "feat(v3/config): implement _SHARED_REQUIRED_SECTIONS check + reroute (cycle 13-2)"
```

</cycle>

---

## Task 13-3 — Walker coverage tripwire (§5.3.7.5)

<task id="13-3"
      spec-ref="§5.3.7.5; §6.7 test 14"
      blast-radius="tests/v3/config/test_firm.py"
      depends-on="13-1"
      commits="single">

**Rationale:** Spec test 14 is a regression-pin against silent under-enumeration of `_enumerate_path_fields`. The walker was implemented in cycle 13-1 step 11; if its implementation accidentally yields fewer fields than expected (e.g., a one-character typo in the recursion check), the path-validator tests (10) still pass for the fields it DOES yield, while the missing fields silently bypass the shared-side prohibition. Test 14 pins the walker's coverage at exactly `{"trustee_catalog.db_path", "diagnostics.audit_log_dir", "diagnostics.rules_dir"}` — equality, not subset, so additions to schema also trip the test. As a separate single-commit pin (rather than folded into cycle 13-1's Red), it documents the regression-pin intent at commit-message granularity.

**Files:**

- Modify: `tests/v3/config/test_firm.py`

- [ ] **Step 1: Append the walker-coverage test**

Append to `tests/v3/config/test_firm.py` after the cycle-13-2 tests:

```python
# ─── Task 13-3: Walker coverage tripwire (spec §5.3.7.5) ─────────────────────


def test_enumerate_path_fields_yields_known_set() -> None:
    """Spec §6.7 test 14: walker coverage is pinned at the known three Path fields.

    Equality, not subset: a regression that accidentally yields fewer fields
    silently leaves the shared-side relative-path prohibition unenforced for
    the missed fields. A schema extension that adds a new Path field also
    trips this test (caught at unit level, not in production).
    """
    from trust_generator.v3.config.firm import _enumerate_path_fields

    assert set(_enumerate_path_fields(FirmConfig)) == {
        "trustee_catalog.db_path",
        "diagnostics.audit_log_dir",
        "diagnostics.rules_dir",
    }
```

The local import inside the test function avoids re-touching the file's top-of-file import block (the helper is private and only used here in tests).

- [ ] **Step 2: Run pixi run test, verify it passes on cycle 13-1's green**

```bash
pixi run test test_enumerate_path_fields
```

Expected: PASS. The walker should yield exactly the three fields; cycle 13-1's implementation is correct if and only if this test passes on first run.

If the test fails: cycle 13-1's `_enumerate_path_fields` has a bug. Halt task 13-3 and reopen cycle 13-1 (file a chore against cycle 13-1 per scope-maintenance, fix the walker, re-run task 13-3).

- [ ] **Step 3: Commit the pin**

```bash
git add tests/v3/config/test_firm.py
git commit -m "test(v3/config): pin _enumerate_path_fields walker coverage (task 13-3)"
```

</task>

---

## Task 13-4 — Cross-plan coordination audit

<task id="13-4"
      spec-ref="(audit gates the integration plan against drift from foundation #5 + cache #12 + spec)"
      blast-radius=".claude/context/chores.xml (only if issues surfaced; via scope-maintenance protocol)"
      depends-on="13-1, 13-2, 13-3"
      commits="audit">

**Purpose:** Three sibling plans modify the same `firm.py` and `test_firm.py` sequentially. The audit runs after cycles 13-1, 13-2, and task 13-3 land but BEFORE the dev-template + README task (13-5) and the plans.xml close (13-6). It reviews ALL three plan-mds, the spec, and the actual implementation state, and aggressively pokes holes for coordination drift. Output is a structured report with one of three classifications per finding: HALT (blocker — revert and re-plan), CHORE (small isolatable cleanup; opens a chore via scope-maintenance), NIT (informational, recorded in plan-md self-review only).

**Why a separate task, not in-loop validation:** Three sibling drafters produced independent plan-mds. Their cross-references describe each other — but a fresh perspective unbiased by any single plan's framing is more likely to spot drift. The audit is dispatched to a SUBAGENT (not the integration session itself). The audit subagent reads three plan-mds, two spec sections, the git log, and the post-cycle-13-3 source/test files; it does not execute code edits.

### Step 1: Verify cycles 13-1 + 13-2 + task 13-3 commits exist

```bash
git log --oneline --grep='cycle 13-[12])$\|task 13-3)$' | wc -l
```

Expected: `≥5` (cycle 13-1 Red + Green = 2; cycle 13-2 Red + Green = 2; task 13-3 single = 1; plus zero or more `chore: apply ruff import sorting` follow-ups). If less than 5, halt and reconcile.

### Step 2: Dispatch the audit subagent

The audit prompt names every check explicitly. Use the `general-purpose` subagent with the following prompt (paste verbatim into the `Agent` tool's `prompt` parameter):

````
You are auditing three sibling implementation plans for coordination drift.
The plans modify the same module `src/trust_generator/v3/config/firm.py`
and test file `tests/v3/config/test_firm.py` sequentially. Your job is
to aggressively poke holes — find places where the plans drifted from
each other or from the spec, where symbols don't match, where contracts
were quietly violated, or where coordination was degraded.

INPUTS (all read-only):
1. Spec: `docs/superpowers/specs/2026-04-28-shared-firm-config-design.md`
2. Foundation plan-md: `docs/superpowers/plans/2026-04-29-shared-firm-config-foundation.md`
3. Cache plan-md: `docs/superpowers/plans/2026-04-29-shared-firm-config-cache.md`
4. Integration plan-md: `docs/superpowers/plans/2026-04-29-shared-firm-config-integration.md`
5. Current source: `src/trust_generator/v3/config/firm.py`,
   `src/trust_generator/v3/config/__init__.py`,
   `tests/v3/config/test_firm.py`,
   `tests/v3/config/test_firm_cache.py` (if exists),
   `tests/v3/integration/test_config_integration.py`
6. Git log via `git log --oneline --all -- src/trust_generator/v3/config/firm.py`

DO NOT edit any file. Your output is a structured report only.

CHECKS (run all, report findings under each):

A. Symbol drift
- A1. Every symbol referenced in any plan-md exists at the named identifier in firm.py.
- A2. Every symbol in __init__.py.__all__ is importable from firm.py.
- A3. Every public symbol named in spec §5.6.2 is in __init__.py.__all__.
     Every spec-§5.6.2-private symbol is NOT in __all__.

B. Signature drift
- A4. `_read_shared_with_fallback(shared_path: Path) -> tuple[bytes, dict[str, Any], bool]`
     matches verbatim in cache plan and at every call site in integration plan.
- A5. `_read_cache_or_raise` keyword-only signature is honored at every call site;
     no positional-arg call slipped in.
- A6. `load_firm_config(local_path: Path | None = None, shared_path: Path | None = None)`
     matches spec §5.6.1. Old positional `path` is completely gone.

C. Tuple-shape preservation (C1 finding)
- A7. Cycle 13-1 green never destructures a 2-tuple from `_read_shared_with_fallback`.
     Always 3-tuple `(shared_bytes, shared_dict, used_cache)`.
- A8. Cycle 13-1 green never calls `tomllib.loads(shared_bytes)` after the helper
     has already parsed.
- A9. Cycle 13-1 green never re-queries `resolved_shared.exists()` to gate the
     cache write. The gate is `if not used_cache:` exclusively.

D. Cache-write D-11 invariant
- A10. `_write_cache(...)` call follows AFTER FirmConfig validation.
- A11. `_write_cache(...)` is gated on `if not used_cache:`.
- A12. After §5.4.8.3 re-route, `used_cache=True`, so the gate skips the write.
     Spec test 12 must exist and pass.

E. No-wrapper invariant (Q5)
- A13. Grep cycles 13-1 + 13-2 source for `def _check_completeness`,
     `def _completeness_check_or_reroute`, `def _shared_with_validation`,
     `def _read_shared_helper`. Must return zero. The §5.4.8.3 re-route
     is a direct call to `_read_cache_or_raise`.

F. Format-duration / utility re-introduction (Q6)
- A14. Grep integration plan source for `def _format_duration` — must return zero.
     Cache plan owns it.
- A15. Grep for `tomli_w` import or `tomllib.dumps` — must return zero.
     Verbatim source bytes pass through unchanged.

G. Constant rename completeness (Q7)
- A16. Grep `src/` and `tests/` for `DEFAULT_CONFIG_PATH` — must return zero
     after cycle 13-1.
- A17. Grep `src/` and `tests/` for `ENV_VAR_CONFIG_PATH` — must return zero
     after cycle 13-1.
- A18. Foundation cycle 2's `_discover_local_path` body referenced
     `ENV_VAR_CONFIG_PATH`. Verify it now references `ENV_VAR_LOCAL_CONFIG_PATH`.

H. Dead-code removal
- A19. `def _discover_path` (the old single-source helper) is removed from firm.py.
- A20. No unused imports in firm.py (e.g., the rewrite may have orphaned an import).

I. Test-file boundaries
- A21. `test_firm_cache.py` (cache plan) is unchanged by integration plan.
     Diff against cache plan's last commit; integration cycles must show zero edits.
- A22. The `XDG_CACHE_HOME` autouse fixture in `test_firm_cache.py` did NOT
     propagate to `test_firm.py`. (Cycle 13-1 + 13-2 tests use explicit
     `monkeypatch.setenv("XDG_CACHE_HOME", ...)` in test bodies, not autouse.)
- A23. `_clean_env` autouse in `test_firm.py` is unchanged. (Foundation plan
     line 560 claimed no fixture extension needed; integration honors that.)

J. Integration-test migration (Q3)
- A24. `test_config_integration.py` now uses `load_firm_config(local_path=, shared_path=)`
     keyword form. Grep for `load_firm_config(tmp_path` (positional) — zero.

K. __init__.py delta (Q8)
- A25. `DEFAULT_LOCAL_CONFIG_PATH`, `ENV_VAR_LOCAL_CONFIG_PATH`,
     `ENV_VAR_SHARED_CONFIG_PATH`, `SharedConfigStalenessWarning`,
     `SharedConfigIntegrityWarning` are all in __init__.py.__all__.
- A26. `CONVENTIONAL_SHARED_CONFIG_PATH` is NOT in __init__.py.__all__
     (private per spec §5.6.2).
- A27. __all__ is alphabetically sorted (RUF022 enforcement).

L. Predecessor commit log
- A28. `git log --oneline --grep='cycle [1-5])$' | wc -l` returns ≥7
     (foundation cycles 1+2+3 = R+G+R for 1, R+G for 2, R+G for 3 = 7).
- A29. `git log --oneline --grep='cycle [4-5])$' | wc -l` returns ≥4
     (cache cycles 4+5 = R+G each = 4).
- A30. `git log --oneline --grep='cycle 13-[12])$\|task 13-3)$' | wc -l`
     returns ≥5 at the audit point.

M. Spec coverage gap-check
- A31. Every paragraph in spec §5.4.8 has a corresponding implementation site.
     §5.4.8.1 (constant) → cycle 13-2; §5.4.8.2-3 (re-route) → cycle 13-2;
     §5.4.8.4 (testable properties) → cycle 13-2 tests 12-13; §5.4.8.5
     (manifest deferred) → no implementation needed.
- A32. Every paragraph in spec §5.3.7 (path resolution) has a corresponding
     implementation. §5.3.7.1-2 (anchor + ${user.upn}) → cycle 13-1
     load_firm_config; §5.3.7.3 (shared-side prohibition) →
     `_validate_shared_paths_absolute`; §5.3.7.4 (validator implementation
     choice) → `_enumerate_path_fields` + `_get_dotted` + `_is_windows_absolute`;
     §5.3.7.5 (recursion semantics) → walker test 14 in task 13-3.

N. Drafter handoff brief enforcement (cache → integration)
- A33. The cache drafter's brief item #2 (frozen function signatures) is
     honored: every cache-plan-introduced symbol in firm.py has its
     signature unchanged by the integration plan.

OUTPUT FORMAT:

Report structure:
```
# Cross-Plan Coordination Audit — 2026-04-29 Shared Firm Config

## Summary
- Total checks run: <N>
- HALT findings: <count>
- CHORE findings: <count>
- NIT findings: <count>
- Audit verdict: CLEAN | CHORES | HALT

## HALT findings
(if any; one entry per finding)

### H1. <one-line summary>
**Check ID:** A<N>
**Evidence:** <file:line; grep output; commit sha>
**Why HALT:** <reasoning>
**Recommended action:** <revert-and-re-cycle / spec-amendment / etc.>

## CHORE findings
(if any; one entry per finding)

### C1. <one-line summary>
**Check ID:** A<N>
**Evidence:** <file:line>
**Why CHORE:** <reasoning>
**Proposed chore:** <synopsis suitable for chores.xml entry>

## NIT findings
(if any; informational only)

### N1. <one-line summary>
**Check ID:** A<N>
**Evidence:** <...>
```

CLASSIFICATION RULES:
- Symbol drift / signature drift / tuple-shape (A1-A12) → HALT (correctness bugs)
- Format-duration / wrapper / double-parse (A13-A15) → HALT (architectural deviations)
- Constant rename / dead-code / __init__.py delta (A16-A27) → CHORE
- Test-file boundaries (A21-A23) → CHORE if minor, HALT if cross-module fixture leak
- Predecessor commit log (A28-A30) → HALT (broken predecessor chain)
- Spec coverage gap (A31-A32) → HALT if §5.4.8 or §5.3.7 paragraphs unimplemented;
  CHORE if peripheral
- Drafter handoff (A33) → HALT (signature freeze breach)

Be aggressive: if you have any doubt, surface it as a finding rather than skip.
The integration plan's success criterion is that the audit passes CLEAN, or
that all CHORE findings are scope-isolatable from the integration's main
deliverable.
````

Run via:

```bash
# (Pseudocode for Agent dispatch - actual invocation is via the Agent tool)
# Agent(description="Cross-plan coordination audit",
#       subagent_type="general-purpose",
#       prompt="<the audit prompt above>")
```

### Step 3: Process the audit report

Read the subagent's structured report. Apply the verdict:

- **CLEAN** — Proceed to task 13-5.
- **CHORES** — For each CHORE finding:
  1. Open a chore in `.claude/context/chores.xml` per scope-maintenance protocol (`docs/.prompts/base.xml` `<scope-maintenance>`).
  2. Set `type="code"` if the chore touches `src/` or `tests/`; `type="simple"` otherwise.
  3. Use the audit's `Proposed chore` synopsis verbatim (or a refined version) as the chore's `synopsis` attribute.
  4. Commit the chore-open(s) as one commit: `chore(context/chores): open coordination-audit findings (task 13-4)`.
  5. Then proceed to task 13-5. The chores will be addressed as separate dispatches AFTER plan #13 closes.
- **HALT** — Halt the integration session. For each HALT finding:
  1. Identify the responsible cycle (typically 13-1 or 13-2).
  2. Open a chore for the fix per scope-maintenance.
  3. Do NOT proceed to task 13-5 or 13-6.
  4. Surface to the dispatcher with a halt-reason summary; the dispatcher decides whether to revert the offending cycle's commits and re-execute, or to amend with a follow-up commit.

### Step 4: Record audit verdict in plan-md self-review

Append a one-paragraph note to the Self-Review Checklist section (below) recording the audit's verdict and any chores opened. This is the only commit-bearing edit to the integration plan-md itself; do not amend cycle commits.

If verdict is CLEAN: append `Audit verdict (task 13-4): CLEAN. No coordination drift detected.`
If verdict is CHORES: append `Audit verdict (task 13-4): N CHORES opened — see chores.xml entries [<ids>].`
If verdict is HALT: do not append; halt the session per Step 3.

Commit the plan-md edit (CLEAN or CHORES path only):

```bash
git add docs/superpowers/plans/2026-04-29-shared-firm-config-integration.md
git commit -m "docs(plans): record coordination-audit verdict (task 13-4)"
```

</task>

---

## Task 13-5 — Dev-environment template + onboarding README

<task id="13-5"
      spec-ref="§8.2 step 0; §8.4 (dev-environment fallback); §10 chore #6"
      blast-radius="config/firm.shared.dev.toml; config/README.md"
      depends-on="13-4"
      commits="single">

**Rationale:** Spec §8.2 step 0 mandates that the dev template `config/firm.shared.dev.toml` lands AS PART OF the Cycle 6 PR. Without it, any dev pulling main from the moment cycle 13-1 lands hits `FirmConfigError: local firm.toml not found / shared firm.toml unreachable` with no mitigation, until the maintainer's migration session lands the SharePoint shared file (which may be days later). The `config/README.md` per spec §10 chore #6 documents the dev-environment workflow: `export TGV3_FIRM_SHARED_CONFIG=$(realpath config/firm.shared.dev.toml)`.

**Files:**

- Create: `config/firm.shared.dev.toml`
- Create: `config/README.md`

- [ ] **Step 1: Read current `config/firm.toml`**

```bash
cat config/firm.toml
```

The current single-source firm.toml contains every section: `[user]`, `[firm]`, `[firm.office_address]`, `[jurisdiction]`, plus optionally `[meta]`, `[estate_thresholds]`, `[trustee_catalog]`, `[diagnostics]`, `[guardianship]`, `[drafts]`. Capture the verbatim content for step 2.

- [ ] **Step 2: Author `config/firm.shared.dev.toml`**

Create `config/firm.shared.dev.toml` with the verbatim content of `config/firm.toml` MINUS the `[user]` section. `[meta]` is RETAINED (firm-policy-bearing metadata per spec §5.4.8.1's logic; integration drafter Q3 confirmation).

The exact content depends on what's in the current `config/firm.toml` at execution time. Skeleton:

```toml
# Dev-environment template for the shared firm.toml file.
#
# This file is intentionally checked in. Production paralegal workstations
# load the shared file from the OneDrive-synced SharePoint library at
# CONVENTIONAL_SHARED_CONFIG_PATH; this template exists for environments
# without OneDrive sync (WSL development, CI, future automated agents).
#
# Usage: export TGV3_FIRM_SHARED_CONFIG=$(realpath config/firm.shared.dev.toml)
#
# See config/README.md for the full dev-environment onboarding workflow.

[meta]
# (verbatim copy of [meta] from config/firm.toml, if present)

[firm]
# (verbatim copy of [firm] from config/firm.toml)

[firm.office_address]
# (verbatim copy of [firm.office_address] from config/firm.toml)

[jurisdiction]
# (verbatim copy of [jurisdiction] from config/firm.toml)

[estate_thresholds]
# (verbatim copy of [estate_thresholds] from config/firm.toml, if present)

[trustee_catalog]
# (verbatim copy of [trustee_catalog] from config/firm.toml, if present)

[diagnostics]
# (verbatim copy of [diagnostics] from config/firm.toml, if present)

[guardianship]
# (verbatim copy of [guardianship] from config/firm.toml, if present)

[drafts]
# (verbatim copy of [drafts] from config/firm.toml, if present)
```

The `(verbatim copy of [section] ...)` placeholders are filled in by the executor reading `config/firm.toml` at step 1. Sections not present in `config/firm.toml` are omitted from the dev template.

`[user]` is NEVER copied — it's per-workstation and lives in `config/firm.toml` post-migration.

- [ ] **Step 3: Author `config/README.md`**

Create `config/README.md`:

```markdown
# Trust Generator — `config/` directory

This directory holds firm-configuration files for development environments.
Production paralegal workstations resolve their shared configuration from
SharePoint via OneDrive; the files in this directory are convenience
templates and per-workstation defaults for non-OneDrive environments.

## Two-source loader

`load_firm_config()` reads two TOML files and merges them:

- **Local file** (`config/firm.toml`): per-workstation, version-controlled.
  Currently contains only `[user]` post-migration.
- **Shared file**: firm-wide policy. Production loads from the OneDrive-synced
  SharePoint library; development environments load from
  `config/firm.shared.dev.toml` via env-var override.

Discovery for each file is:

1. Explicit `local_path=` / `shared_path=` argument to `load_firm_config()`.
2. Environment variable: `TGV3_FIRM_CONFIG` (local) or `TGV3_FIRM_SHARED_CONFIG` (shared).
3. Conventional default: `config/firm.toml` (local), or the OneDrive-synced library path (shared).

See `docs/superpowers/specs/2026-04-28-shared-firm-config-design.md` §5.2 for
the discovery contract.

## Dev-environment workflow

If you are developing locally without OneDrive (e.g., WSL, CI, fresh checkout
pre-sync), the conventional shared path will not resolve. Use the dev template:

```bash
export TGV3_FIRM_SHARED_CONFIG=$(realpath config/firm.shared.dev.toml)
```

Then run the application normally. The first successful load also populates
the local cache at `${XDG_CACHE_HOME:-~/.cache}/trust-generator/firm.shared.cache.toml`
(POSIX) or `%LOCALAPPDATA%/trust-generator/firm.shared.cache.toml` (Windows);
subsequent invocations succeed without the env var until the cache file
is removed or expires.

## Production deployment posture

Paralegal production deployments do **NOT** include the `config/` directory.
The deployed application reads the local file from the workstation's user
profile and the shared file from OneDrive. The dev template is never used
in production.

## Files

- `config/firm.toml` — local per-workstation firm config (currently `[user]` only post-migration).
- `config/firm.shared.dev.toml` — dev-environment shared template; copy of
  the SharePoint-hosted shared file at migration time. May drift from
  SharePoint over time; see spec §8.4.1.
- `config/firm.v2.toml` — legacy v2 single-source config (preserved for
  reference/migration).
- `config/firm-config.schema.json` — JSON Schema for editor integrations.

## Migration provenance

The split into `config/firm.toml` (local-only post-migration) and
`config/firm.shared.dev.toml` (dev-environment shared) lands as part of plan
#13 (`docs/superpowers/plans/2026-04-29-shared-firm-config-integration.md`).
The maintainer's migration session that uploads the shared content to
SharePoint and strips the duplicate sections from `config/firm.toml`
is described in spec §8.2 migration steps 1-8.
```

- [ ] **Step 4: Verify both files lint-clean**

```bash
pixi run lint
```

Expected: no errors. (TOML and Markdown files are not linted by ruff, but the project gate may include other checks.)

```bash
pixi run check
```

Expected: full gate green (lint + mypy + tests).

- [ ] **Step 5: Commit**

```bash
git add config/firm.shared.dev.toml config/README.md
git commit -m "feat(config): add shared dev template + onboarding README (task 13-5)"
```

</task>

---

## Task 13-6 — Close `.claude/context/plans.xml` entry 13

<task id="13-6"
      spec-ref="(spec-pipeline invariant #5: dispatcher-owned)"
      blast-radius=".claude/context/plans.xml"
      depends-on="13-5"
      commits="single">

**Rationale:** Per spec-pipeline SKILL.md invariant #5, the chores.xml status flip on chore-completion is dispatcher-owned to eliminate parallel-write races. The same principle applies to plans.xml status flips. Task 13-6 is executed by the DISPATCHING SESSION, not the plan-executor subagent.

**Files:**

- Modify: `.claude/context/plans.xml`

- [ ] **Step 1: Edit plan #13 entry to status="closed"**

Find the entry:

```xml
<plan index="13"
      id="2026-04-29-shared-firm-config-integration"
      status="open"
      expendable="false"
      plan-md=""
      spec-md="docs/superpowers/specs/2026-04-28-shared-firm-config-design.md"
      synopsis="Integration: spec §6 cycle 6 — load_firm_config two-source signature, _SHARED_REQUIRED_SECTIONS completeness check, shared-side path validator, fixture migration. Cycle-6 PR also lands config/firm.shared.dev.toml + config/README.md." />
```

Update three attributes:
- `status="open"` → `status="closed"`
- `plan-md=""` → `plan-md="docs/superpowers/plans/2026-04-29-shared-firm-config-integration.md"`

And bump `modified-at` on the root `<reference>` element to the current timestamp.

- [ ] **Step 2: Validate against the schema**

```bash
xmllint --noout --schema .claude/context/schema/plans.xsd .claude/context/plans.xml
```

Expected: `.claude/context/plans.xml validates`. If validation fails: revert and reconcile.

- [ ] **Step 3: Commit the close**

```bash
git add .claude/context/plans.xml
git commit -m "chore(context/plans): close #13 — shared-firm-config integration"
```

- [ ] **Step 4: Final sanity check**

```bash
pixi run check
```

Expected: full gate green.

</task>

---

## Self-Review Checklist (run before handoff)

**Spec coverage:**

- §6.7 cycle 6 → cycles 13-1 (tests 1-11) + 13-2 (tests 12-13) + task 13-3 (test 14). All 14 spec tests covered.
- §5.6.1 (function signature) → cycle 13-1 step 12 `load_firm_config(local_path=, shared_path=)`.
- §5.6.2 (module-level public symbols) → cycle 13-1 step 9 (constant renames) + step 14 (`__init__.py` re-exports).
- §5.6.3 (exception surface) → cycle 13-1 step 12 (load_firm_config error paths) + cycle 13-2 step 5 (§5.4.8.3 missing-section message).
- §5.6.4 (no-shim posture) → cycle 13-1 step 13 (delete `_discover_path`) + spec test 4 (cycle 13-1 new test 4).
- §5.6.5 (idempotence + side-effect inventory) → spec test 2 + 5 (cache-write determinism); pinned by cycle 13-1 tests.
- §5.4.8.1 (`_SHARED_REQUIRED_SECTIONS`) → cycle 13-2 step 4.
- §5.4.8.2-3 (check timing + re-route) → cycle 13-2 step 5.
- §5.4.8.4 (testable properties) → cycle 13-2 tests 12-13.
- §5.4.8.5 (manifest deferred) → no action needed; spec defers explicitly.
- §5.3.7.1 (anchor at resolved_local.parent) → cycle 13-1 step 12 `_resolve_paths(cfg, resolved_local.parent)`.
- §5.3.7.2 (`${user.upn}` post-merge timing) → cycle 13-1 step 12 (existing `_resolve_paths` body unchanged; substitution runs against merged dict).
- §5.3.7.3 (shared-side prohibition) → cycle 13-1 step 11 `_validate_shared_paths_absolute`.
- §5.3.7.4 (validator implementation choice) → cycle 13-1 step 11 `_enumerate_path_fields` + `_get_dotted` + `_is_windows_absolute`.
- §5.3.7.5 (recursion semantics) → task 13-3 walker tripwire.
- §8.2 step 0 (dev template) → task 13-5 step 2.
- §10 chore #6 (onboarding README) → task 13-5 step 3.
- D-8 (no backward-compatibility shim) → cycle 13-1 step 13 (delete `_discover_path`) + new test 4 (TypeError on `path=`).
- D-11 (cache write only on validation success) → cycle 13-1 step 12 (write at function bottom, after validation) + new tests 6-8.

**Out-of-scope items confirmed deferred:**

- The actual SharePoint-side migration session (§8.2 steps 1-8) → operational, post-PR.
- Diagnostics-engine warning subscriber (§5.5.5.4 / pre-planning chore #4) → separate plan against the diagnostics-engine spec.
- Audit-log effective-config capture (pre-planning chore #5) → diagnostics-engine spec amendment, not this scope.
- Production-deployment paths (§5.2.7) → spec defers.
- Manifest/checksum integrity layer (§5.4.8.5) → spec defers.

**Type consistency:**

- `_read_shared_with_fallback(shared_path: Path) -> tuple[bytes, dict[str, Any], bool]` matches between the cache plan's introduction and integration plan's call site (cycle 13-1 step 12).
- `_read_cache_or_raise(shared_path, *, warning_class, warning_phrasing, no_cache_error_template, integrity_reason=None) -> tuple[bytes, dict[str, Any], bool]` matches between cache plan and the §5.4.8.3 re-route call (cycle 13-2 step 5).
- `load_firm_config(local_path: Path | None = None, shared_path: Path | None = None) -> FirmConfig` matches spec §5.6.1.
- `_validate_shared_paths_absolute(shared_dict: dict[str, Any], schema: type[BaseModel] = FirmConfig) -> None` is consistent across step 11 and step 12.
- `_enumerate_path_fields(schema: type[BaseModel]) -> list[str]` is consistent between step 11 (definition) and task 13-3 (test pin).
- `_SHARED_REQUIRED_SECTIONS: Final[frozenset[str]]` is consistent between cycle 13-2 step 4 (definition) and step 5 (consumption).

**Placeholder scan:**

- All test bodies are concrete; all Green code blocks contain runnable Python; all commit messages are spelled out; all run commands are exact `pixi run test <pattern>` or `pixi run check` invocations. No "TBD" / "etc." / "similar to above" left in.
- Task 13-5 step 2 contains placeholder text `(verbatim copy of [section] from config/firm.toml, if present)` — these are deliberate templates for the executor to fill in by reading `config/firm.toml` at step 1; the executor's instruction is exact ("verbatim copy"), the indeterminacy is in the source data, not the plan.

**Audit verdict (task 13-4):** 2 CHORES opened — see chores.xml entries [#23, #24]. Audit ran 33 checks (A1-A33); 0 HALT, 2 CHORE (both `type="simple"`, doc-side reconciliation), 3 NIT (informational). Correctness invariants all pass cleanly: 3-tuple `_read_shared_with_fallback` contract honored, keyword-only `_read_cache_or_raise` signature honored at every call site, D-11 cache-write gate is `if not used_cache:` exclusively (no `resolved_shared.exists()` re-query), §5.4.8.3 re-route is a direct call to `_read_cache_or_raise` with no wrapper helper, no `tomllib.loads` re-parse of `shared_bytes`, no `tomli_w` round-trip, no `_format_duration` redefinition, constant rename to `DEFAULT_LOCAL_CONFIG_PATH` + `ENV_VAR_LOCAL_CONFIG_PATH` is complete (zero residual `DEFAULT_CONFIG_PATH`/`ENV_VAR_CONFIG_PATH` references in src/+tests/), `__init__.py` re-export delta correct, predecessor commit chain intact. Chore #23 captures the cycle 13-2 in-cycle blast-radius expansion to `test_config_integration.py` (necessary to preserve post-cycle-green-pass invariant; same precedent as Q3); chore #24 captures the cycle 13-1 `_REQUIRED_SECTION_PLACEHOLDERS` fixture forecast that anticipated cycle 13-2's `_SHARED_REQUIRED_SECTIONS` check. Both chores are scope-isolatable from the integration's main deliverable; integration's success criterion is met.

---

## Plan-composition decisions index (Q-tags by reference)

For traceability when later sessions read this plan-md cold:

- **Q1** — 3-cycle decomposition rationale (§ Plan-composition decisions recorded)
- **Q2** — Cross-plan coordination audit as task 13-4 (§ Plan-composition + § Task 13-4)
- **Q3** — `test_config_integration.py` absorption (§ Plan-composition + § Cycle 13-1 step 6)
- **Q4** — D-11 cache-write gating (§ Plan-composition + § Cycle 13-1 step 12)
- **Q5** — No-wrapper around `_read_cache_or_raise` (§ Plan-composition + § Cycle 13-2 step 5)
- **Q6** — No double-parse / no `tomli_w` / no `_format_duration` redefinition (§ Plan-composition)
- **Q7** — `DEFAULT_LOCAL_CONFIG_PATH` (spec §5.6.2) over cache drafter's typo (§ Plan-composition + § Cycle 13-1 step 9)
- **Q8** — `__init__.py` re-export delta (§ Plan-composition + § Cycle 13-1 step 14)
- **Q9** — Scope-size threshold acceptance (§ Plan-composition + § File Structure)
- **Q10** — Inside-out TDD with no mocks (§ Plan-composition)
- **Q11** — Refactor-stage discipline (§ Plan-composition + § Cycle 13-1 + § Cycle 13-2)
