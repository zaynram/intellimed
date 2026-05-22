# Diagnostics Engine Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land cycles 1-6 of the diagnostics engine spec — `diagnose()` entry point, `build_eval_context`, rule loader, rule evaluator, audit log writer, and `force_generation()` override flow — leaving Cycle 1's integration test xfailed pending the sibling rules plan.

**Architecture:** Greenfield Python module at `src/trust_generator/v3/diagnostics/` consuming `TrustData` (post-fill canonical) and `FirmConfig` (post chore A-4/A-5/A-6) and producing `list[Diagnostic]`. Built on the BSD-3 `rule-engine` library, wrapped via `build_eval_context()` (composition surface) and `DiagnosticRule` (Pydantic compile-on-load surface). Audit log persists as JSONL to a per-user SharePoint-synced subfolder. Pure `diagnose()` / side-effecting `force_generation()` split is deliberate.

**Tech Stack:** Python 3.12 (pinned by `rule-engine` upstream metadata; pixi env enforces this), Pydantic v2, `rule-engine >= 4.5.3, <5`, `pyyaml >=6,<7`, `freezegun >=1.5,<2` (dev-only). Existing project: pixi-managed, ruff/mypy/pytest gates via `pixi run check`.

**Spec source:** `docs/superpowers/specs/2026-04-23-diagnostics-engine-design.md` (§§3-5, §6.1-6.7, §§7-11, §14.1, §14.4 in scope; §6.8-6.10 + §13 explicitly out of scope per `core.xml` plan boundary).

**Plan-composition decisions recorded:**

- **§14.4 Cycle 1 Red-period option-choice resolution: Option A (xfail-marker).** Rationale: the integration test anchors the engine's contract in the core PR's diff, which is the moment engine design is reviewed. The xfail reason explicitly names the dependent plan (`diagnostics-engine-rules`), making the temporary state self-documenting. The sibling rules plan's first commit removes the marker. Option B (defer test entirely) was rejected because it loses the contract anchor at the engine's own review window.
- **§9 module organization decision: `DiagnosticRule.evaluate` lives on the model in `loader.py`.** No separate `evaluator.py` module. Helpers `_meta_diagnostic` and `_build_rule_context` live alongside in `loader.py`. Spec §6.5 already shows `evaluate` as a model method; a separate file would re-export the model with no added value.
- **§9 `__init__.py` re-exports decision: include `validate_override_reason`.** Spec §5.6 exposes it for future GUI live-validation; not re-exporting forces callers to import from a private path.
- **TDD commit granularity: Red commit + Green commit per cycle, Refactor commit only when the spec's refactor note describes substantive code work.** Cycles 2, 4, 5, 6 land in 2 commits. Cycle 3 lands in 3 commits (Refactor extracts `_dedupe_key` per §6.4 explicit refactor note). Cycle 1 is one commit (Red xfailed test, no Green in this plan).
- **Empty `builtin.yaml` semantics: empty file parses to empty rule list, no error.** Mirrors §6.4 test #3 ("empty rules_dir yields only builtins, no error"). Adds one positive Cycle 3 test for this case beyond the spec's enumerated 17. Recorded as a scope addition.
- **Python interpreter discipline: any ad-hoc Python invocation uses `pixi run python`, never bare `python`.** System Python is 3.14; pixi env is constrained to 3.12 by `rule-engine` upstream. Pixi-defined tasks (`pixi run check`, `pixi run test`, etc.) handle this automatically; the rule applies to direct interpreter calls during debugging.
- **Evaluator catches both `SymbolResolutionError` and `AttributeResolutionError` and maps both to `engine.symbol_unknown`.** Per spec §6.5 intent ("attribute/symbol not resolvable → symbol_unknown meta"). Rule-engine raises `AttributeResolutionError` (not `SymbolResolutionError`) for `trust.nonexistent_field` against `{"trust": {}}` — both inherit `EvaluationError` but they are siblings, not ancestor-descendant. The `EvaluationError` handler remains as the catch-all for other runtime errors, mapped to `engine.eval_error`. This was a plan-review finding (C4) corrected against the rule-engine 4.5.3 API.
- **`rules/` is a regular package with `__init__.py` (not a PEP 420 namespace package).** Required for `importlib.resources.files("trust_generator.v3.diagnostics.rules")` to behave consistently across editable installs, wheel installs, and frozen pyinstaller bundles. Plan-review finding (I2).
- **Python pin tightened to `>=3.12,<3.13` in `pixi.toml`** (not relying on rule-engine's upstream metadata to enforce). Plan-review finding (I4).
- **Cycle 1 integration test uses a deferred import inside the test body** (`from trust_generator.v3.diagnostics import diagnose` lives in the function, not at module top). This avoids a collection-time `ImportError` between Task 1 and Task 7, which `pytest.mark.xfail` cannot catch (xfail covers test-body failures, not import-time collection failures). Plan-review finding (I1).

---

## File Structure

**Created (production):**

| Path | Responsibility |
| ---- | -------------- |
| `src/trust_generator/v3/diagnostics/__init__.py` | Public re-exports: `diagnose`, `force_generation`, `validate_override_reason`, `DiagnosticConfigError`. |
| `src/trust_generator/v3/diagnostics/engine.py` | `diagnose(trust, config, *, ref_date=None) -> list[Diagnostic]`. Coordinator only — composes eval context, loads rules, iterates evaluations. |
| `src/trust_generator/v3/diagnostics/eval_context.py` | `build_eval_context(trust, config, ref_date) -> dict`. Composes `{trust, firm, now}` namespace, injects computed properties, pre-computes `minor_beneficiaries(ref_date)`. |
| `src/trust_generator/v3/diagnostics/loader.py` | `DiagnosticRule` (Pydantic), `load_rules(config)`, namespace/collision/dedupe enforcement, expression compilation, `_build_rule_context()`, `_meta_diagnostic()`. `DiagnosticRule.evaluate` lives here. |
| `src/trust_generator/v3/diagnostics/audit.py` | `AuditRecord` (Pydantic), `AuditLog`, `force_generation()`, `validate_override_reason()`. |
| `src/trust_generator/v3/diagnostics/errors.py` | `DiagnosticConfigError` (the loader's only failure mode). |
| `src/trust_generator/v3/diagnostics/rules/builtin.yaml` | Empty YAML list (`[]`). Rules land in the sibling `2026-04-23-diagnostics-engine-rules` plan. |

**Created (tests):**

| Path | Responsibility |
| ---- | -------------- |
| `tests/v3/diagnostics/__init__.py` | Empty; package marker. |
| `tests/v3/diagnostics/conftest.py` | Shared fixtures: `firm_config_factory`, `trust_data_factory`, `tmp_audit_dir`, `tmp_rules_dir`. |
| `tests/v3/diagnostics/test_diagnose.py` | Cycle 1 — outer integration. Single test, `pytest.mark.xfail`. |
| `tests/v3/diagnostics/test_eval_context.py` | Cycle 2 — eight tests covering shape, namespaces, computed-property injection, ref-date fallback, minor injection, enum value pin. |
| `tests/v3/diagnostics/test_rule_loader.py` | Cycle 3 — 18 tests (spec's 17 + empty-builtin scope addition). |
| `tests/v3/diagnostics/test_rule_evaluator.py` | Cycle 4 — six tests covering match, no-match, disabled, symbol-unknown meta, eval-error meta, compiled-rule identity. |
| `tests/v3/diagnostics/test_audit_log.py` | Cycle 5 — six tests covering write/append/rotation/path-absoluteness. |
| `tests/v3/diagnostics/test_override.py` | Cycle 6 — seven tests covering happy path, reason validation, UPN-missing-at-load (cross-reference), trust-ref fallback, codes ordering, no-mutation. |

**Modified:**

| Path | Change |
| ---- | ------ |
| `pixi.toml` | Add `rule-engine = '>=4.5.3,<5'`, `pyyaml = '>=6,<7'` to `[pypi-dependencies]` AND `[package.run-dependencies]`. Add `freezegun = '>=1.5,<2'` to `[feature.dev.dependencies]`. |

**Total touched files:** 17 (16 created + 1 modified). This exceeds the global CLAUDE.md hard threshold (>10 files), but matches the spec's pre-considered §14.3 split — the rules plan would have pushed totals to ~22 files in a single session, which is why the spec authored the core/rules split. The plan-execution session may further subdivide if needed (e.g., one PR per cycle), but the implementation-cycle boundaries are themselves a natural review unit.

---

## Task 0: Dependency setup and environment verification

**Files:**
- Modify: `pixi.toml:9-10` (tighten Python pin to `>=3.12,<3.13`)
- Modify: `pixi.toml:12-17` (add `rule-engine`, `pyyaml` to `[pypi-dependencies]`)
- Modify: `pixi.toml:28-33` (add `freezegun` to `[feature.dev.dependencies]`)
- Modify: `pixi.toml:110-115` (add `rule-engine`, `pyyaml` to `[package.run-dependencies]`)
- Modify: `pyproject.toml:9` (tighten `requires-python` to `">=3.12,<3.13"`)

- [ ] **Step 0a: Tighten the Python pin in `pixi.toml`**

Edit `pixi.toml` lines 9-10 to:

```toml
[dependencies]
    python = '>=3.12,<3.13'
```

Rationale: `rule-engine` 4.5.3 supports up to Python 3.12. The system Python on the maintainer's machine is 3.14; without an explicit upper bound in pixi.toml, the solver could resolve Python 3.13+ if rule-engine's upstream metadata is permissive. Pinning here makes the constraint explicit and project-owned.

- [ ] **Step 0b: Tighten `requires-python` in `pyproject.toml`**

Edit `pyproject.toml` line 9 to:

```toml
requires-python = ">=3.12,<3.13"
```

Rationale: aligns the package's PEP 621 metadata with the runtime constraint. Anyone installing via `pip` outside pixi gets a clear error if their interpreter is too new.

- [ ] **Step 1: Add `rule-engine` and `pyyaml` to `[pypi-dependencies]`**

Edit `pixi.toml` lines 12-17 to:

```toml
[pypi-dependencies]
    trust-generator   = { path = '.', editable = true }
    reportlab         = '*'
    pypdf             = '>=4'
    types-reportlab   = '>=4.4.10.20260408, <5'
    pydantic-settings = '>=2.14,<3'
    rule-engine       = '>=4.5.3,<5'
    pyyaml            = '>=6,<7'
```

- [ ] **Step 2: Add `freezegun` to `[feature.dev.dependencies]`**

Edit `pixi.toml` lines 28-33 to:

```toml
    [feature.dev.dependencies]
        pyinstaller = '*'
        pytest      = '*'
        ruff        = '*'
        mypy        = '*'
        jsonschema  = '>=4,<5'
        freezegun   = '>=1.5,<2'
```

- [ ] **Step 3: Add `rule-engine` and `pyyaml` to `[package.run-dependencies]`**

Edit `pixi.toml` lines 110-115 to:

```toml
    [package.run-dependencies]
        pydantic          = '>=2'
        python-docx       = '*'
        reportlab         = '*'
        pypdf             = '>=4'
        pydantic-settings = '>=2.14,<3'
        rule-engine       = '>=4.5.3,<5'
        pyyaml            = '>=6,<7'
```

- [ ] **Step 4: Resolve and install**

Run: `pixi install`
Expected: solver succeeds, lockfile updates. If solver fails citing Python version conflict, escalate — the resolution intersection of `python>=3.12` (workspace) and `rule-engine`'s upstream metadata bound should pin the env to 3.12.

- [ ] **Step 5: Verify the resolved Python is 3.12**

Run: `pixi run python --version`
Expected: `Python 3.12.x` (any patch version). If 3.13+, escalate — `rule-engine` does not support newer Python.

- [ ] **Step 6: Verify rule-engine is importable**

Run: `pixi run python -c "import rule_engine; print(rule_engine.__version__)"`
Expected: `4.5.3` (or higher patch in the 4.5.x line).

- [ ] **Step 7: Commit dependency additions**

```bash
git add pixi.toml pixi.lock pyproject.toml
git commit -m "chore(deps): add rule-engine, pyyaml, freezegun; pin Python to 3.12 for rule-engine compat"
```

---

## Task 1: Cycle 1 — `diagnose()` integration test (Red, xfailed)

**Files:**
- Create: `tests/v3/diagnostics/__init__.py`
- Create: `tests/v3/diagnostics/conftest.py`
- Create: `tests/v3/diagnostics/test_diagnose.py`

This task commits the engine's integration contract as a Red test marked `pytest.mark.xfail`. The marker is removed in the sibling `2026-04-23-diagnostics-engine-rules` plan's first commit (when the three starter rules land and the test would actually pass).

The conftest is authored here with the full fixture set used by all subsequent cycles' tests, even though only Cycle 1 exercises it now. Authoring once avoids per-cycle conftest churn.

- [ ] **Step 1: Create the package marker**

Create `tests/v3/diagnostics/__init__.py` with empty content.

- [ ] **Step 2: Author the shared conftest**

Create `tests/v3/diagnostics/conftest.py`:

```python
"""Shared fixtures for diagnostics-engine cycle tests."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from trust_generator.v3.config.firm import FirmConfig, FirmIdentity, User
from trust_generator.v3.schema import (
    Address,
    BeneficiaryShare,
    Elections,
    GrantorInfo,
    OfficeInfo,
    TextBlocks,
    TrustData,
    TrustIdentity,
    TrustType,
)


@pytest.fixture
def tmp_audit_dir(tmp_path: Path) -> Path:
    """A clean per-test directory for AuditLog writes."""
    audit_dir = tmp_path / "audit"
    audit_dir.mkdir()
    return audit_dir


@pytest.fixture
def tmp_rules_dir(tmp_path: Path) -> Path:
    """A clean per-test directory for custom rule YAML files."""
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()
    return rules_dir


@pytest.fixture
def firm_config_factory(
    tmp_audit_dir: Path, tmp_rules_dir: Path
) -> Callable[..., FirmConfig]:
    """Build a minimal FirmConfig with overridable fields.

    Both ``user`` and ``firm`` are required FirmConfig fields with no
    default_factory, so both must be provided. The factory uses
    ``Address()`` (all-empty strings) for office_address, which keeps
    the US-ZIP cross-field validator dormant (it only fires when
    ``zip_code`` is non-empty).
    """

    def _build(**overrides: Any) -> FirmConfig:
        defaults: dict[str, Any] = {
            "user": User(upn="testuser"),
            "firm": FirmIdentity(
                name="Test Firm",
                phone="555-0100",
                office_address=Address(),
            ),
        }
        defaults.update(overrides)
        cfg = FirmConfig.model_validate(defaults)
        cfg.diagnostics.audit_log_dir = tmp_audit_dir
        cfg.diagnostics.rules_dir = tmp_rules_dir
        return cfg

    return _build


@pytest.fixture
def trust_data_factory() -> Callable[..., TrustData]:
    """Build a minimal TrustData; kwargs inject rule-triggering states."""

    def _build(
        *,
        beneficiary_shares: list[BeneficiaryShare] | None = None,
        estate_value_approximate: Decimal | None = None,
        statement_of_intent: str = "",
        file_number: str = "",
        trust_type: TrustType = TrustType.JOINT,
        execution_date: date | None = None,
    ) -> TrustData:
        return TrustData(
            grantor=GrantorInfo(full_legal_name="Test Grantor"),
            trust_id=TrustIdentity(
                desired_trust_name="Test Family Trust",
                trust_type=trust_type,
                execution_date=execution_date,
            ),
            office=OfficeInfo(file_number=file_number),
            elections=Elections(estate_value_approximate=estate_value_approximate),
            text_blocks=TextBlocks(statement_of_intent=statement_of_intent),
            beneficiary_shares=beneficiary_shares or [],
        )

    return _build
```

Notes on shape:
- `GrantorInfo` (not `PersonInfo`) is the schema's grantor model — extends `PersonReference`. Verified at `src/trust_generator/v3/schema.py:447`.
- `FirmConfig` requires both `user: User` and `firm: FirmIdentity` (verified at `src/trust_generator/v3/config/firm.py:233-234`); all other top-level fields have `default_factory`.
- `Address()` with all-default empty strings is valid — the `FirmIdentity._validate_us_zip_format` validator only fires when `zip_code` is non-empty. This keeps the fixture minimal.

- [ ] **Step 3: Author the Cycle 1 integration test**

Create `tests/v3/diagnostics/test_diagnose.py`:

```python
"""Cycle 1 — outer integration test for diagnose().

This test is committed Red and marked xfail until the diagnostics-engine-rules
plan lands (which authors the three starter rules in builtin.yaml). Removing
the xfail marker is the rules plan's first commit.

Import discipline: the diagnose() symbol is imported INSIDE the test body, not
at module top. Reason: pytest.mark.xfail catches test-body failures, not
collection-time ImportError. Pre-Task 7, the diagnostics package's __init__.py
does not re-export ``diagnose``, so a top-level import would fail at collection
and break ``pixi run check``. With deferred import, the import error happens
inside the function body and is correctly caught by the xfail marker.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from trust_generator.v3.schema import BeneficiaryShare, TrustType


@pytest.mark.xfail(
    reason="diagnostics-engine-rules plan pending: starter rules not yet authored",
    strict=True,
)
def test_diagnose_triggers_all_starter_rules(
    firm_config_factory, trust_data_factory
):
    """A TrustData crafted to trigger all three starter rules yields three diagnostics."""
    from trust_generator.v3.diagnostics import diagnose  # deferred per module docstring

    config = firm_config_factory()
    trust = trust_data_factory(
        beneficiary_shares=[
            BeneficiaryShare(recipient_ref="A", share_percent=Decimal("33")),
            BeneficiaryShare(recipient_ref="B", share_percent=Decimal("33")),
            BeneficiaryShare(recipient_ref="C", share_percent=Decimal("33")),
        ],
        estate_value_approximate=Decimal("5000000"),
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

The `strict=True` xfail flag means the test will fail (as XPASS) if it unexpectedly passes — protecting against the case where someone implements the rules in this plan instead of the sibling plan.

Lifecycle of this test through the plan:
- After Task 1 commits: pytest collects the test (no top-level import), test body runs, deferred import fails (`ImportError: ... no module named 'trust_generator.v3.diagnostics'`), xfail marker swallows it → reported as XFAIL. `pixi run check` is green.
- After Task 7 commits: deferred import succeeds; assertions fail because the rules don't exist; xfail catches → reported as XFAIL.
- After the sibling rules plan's first commit (out of this plan's scope): the xfail marker is removed; the test passes; the engine's contract is now actively asserted.

- [ ] **Step 4: Run the test to confirm Red**

Run: `pixi run test test_diagnose_triggers_all_starter_rules`
Expected: collection error (`ModuleNotFoundError: trust_generator.v3.diagnostics`). This is the contract anchor — the test exists and fails because the engine doesn't exist yet.

- [ ] **Step 5: Commit Cycle 1 Red**

```bash
git add tests/v3/diagnostics/__init__.py tests/v3/diagnostics/conftest.py tests/v3/diagnostics/test_diagnose.py
git commit -m "test(diagnostics): cycle 1 — diagnose() integration contract (xfailed pending rules plan)"
```

---

## Task 2: Cycle 2 — `build_eval_context`

**Files:**
- Create: `src/trust_generator/v3/diagnostics/__init__.py` (skeleton; full re-exports finalized in Task 7)
- Create: `src/trust_generator/v3/diagnostics/eval_context.py`
- Test: `tests/v3/diagnostics/test_eval_context.py`

- [ ] **Step 1: Author the Cycle 2 test file (Red)**

Create `tests/v3/diagnostics/test_eval_context.py`:

```python
"""Cycle 2 — build_eval_context() shape and semantics."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import freezegun
import pytest

from trust_generator.v3.diagnostics.eval_context import build_eval_context
from trust_generator.v3.schema import BeneficiaryShare, Child, TrustType


def test_returned_top_level_keys(firm_config_factory, trust_data_factory):
    config = firm_config_factory()
    trust = trust_data_factory()

    ctx = build_eval_context(trust, config, date(2026, 4, 23))

    assert set(ctx.keys()) == {"trust", "firm", "now"}


def test_trust_namespace_field_passthrough(firm_config_factory, trust_data_factory):
    config = firm_config_factory()
    trust = trust_data_factory()

    ctx = build_eval_context(trust, config, date(2026, 4, 23))

    assert ctx["trust"]["grantor"]["full_legal_name"] == "Test Grantor"


def test_firm_namespace_field_passthrough(firm_config_factory, trust_data_factory):
    config = firm_config_factory()
    trust = trust_data_factory()

    ctx = build_eval_context(trust, config, date(2026, 4, 23))

    assert "estate_thresholds" in ctx["firm"]
    assert "single_hard" in ctx["firm"]["estate_thresholds"]


def test_computed_property_injection(firm_config_factory, trust_data_factory):
    config = firm_config_factory()
    trust = trust_data_factory(
        beneficiary_shares=[
            BeneficiaryShare(recipient_ref="A", share_percent=Decimal("33")),
            BeneficiaryShare(recipient_ref="B", share_percent=Decimal("33")),
            BeneficiaryShare(recipient_ref="C", share_percent=Decimal("33")),
        ],
    )

    ctx = build_eval_context(trust, config, date(2026, 4, 23))

    assert ctx["trust"]["beneficiary_shares_total"] == Decimal("99")


def test_now_resolution_explicit(firm_config_factory, trust_data_factory):
    config = firm_config_factory()
    trust = trust_data_factory()

    ctx = build_eval_context(trust, config, date(2026, 1, 1))

    assert ctx["now"] == date(2026, 1, 1)


@freezegun.freeze_time("2026-04-23")
def test_now_resolution_fallback_chain(firm_config_factory, trust_data_factory):
    """Cycle 2 only tests build_eval_context's explicit ref_date param.
    The fallback chain (None -> trust.execution_date -> date.today()) lives
    in diagnose() (Cycle 1's helper) and is exercised there indirectly.
    This test pins that build_eval_context itself is not the place where
    fallback happens — it requires an explicit ref_date.
    """
    config = firm_config_factory()
    trust = trust_data_factory(execution_date=date(2026, 6, 15))

    # When called with explicit ref_date, that wins.
    ctx = build_eval_context(trust, config, date(2026, 6, 15))
    assert ctx["now"] == date(2026, 6, 15)


def test_minor_injection(firm_config_factory):
    """A Child whose DOB makes them 17 at ref_date appears in minor_beneficiaries; an adult does not.

    Schema shape: TrustData.children is list[Child]; Child extends Beneficiary
    extends PersonReference (which carries date_of_birth). minor_beneficiaries(
    ref_date) aggregates over children, descendants, other_beneficiaries —
    populating only the children list is sufficient to exercise injection.
    """
    from trust_generator.v3.schema import (
        Child,
        GrantorInfo,
        OfficeInfo,
        TrustData,
        TrustIdentity,
    )

    minor_dob = date(2009, 5, 1)  # age 16 on 2026-04-23 (birthday 5/1)
    adult_dob = date(2000, 1, 1)  # age 26 on 2026-04-23

    trust = TrustData(
        grantor=GrantorInfo(full_legal_name="Test Grantor"),
        trust_id=TrustIdentity(desired_trust_name="Test Family Trust"),
        office=OfficeInfo(),
        children=[
            Child(full_legal_name="Minor Child", date_of_birth=minor_dob),
            Child(full_legal_name="Adult Child", date_of_birth=adult_dob),
        ],
    )
    config = firm_config_factory()

    ctx = build_eval_context(trust, config, date(2026, 4, 23))

    minor_names = [b["full_legal_name"] for b in ctx["trust"]["minor_beneficiaries"]]
    assert "Minor Child" in minor_names
    assert "Adult Child" not in minor_names


def test_enum_value_pin(firm_config_factory, trust_data_factory):
    """`build_eval_context` unwraps Enum instances to their `.value`, so rule
    expressions like ``trust.trust_id.trust_type == "individual"`` evaluate
    correctly through rule-engine.

    The str-mixin inheritance on ``TrustType(str, Enum)`` makes Python-level
    equality work, but rule-engine bypasses Python's ``__eq__`` and calls
    ``str()`` on the value — which returns the enum repr
    (``'TrustType.INDIVIDUAL'``), not the value string. The unwrap helper
    inside ``build_eval_context`` normalizes Enum instances so the
    rule-engine roundtrip is correct. This pin guards against regression
    where the unwrap helper is removed.
    """
    import rule_engine

    config = firm_config_factory()
    trust = trust_data_factory(trust_type=TrustType.JOINT)

    ctx = build_eval_context(trust, config, date(2026, 4, 23))

    val = ctx["trust"]["trust_id"]["trust_type"]
    assert isinstance(val, str)  # post-unwrap: a plain str, not a TrustType instance
    assert val == "joint"
    assert val != "individual"

    # rule-engine roundtrip — guards against regression where _unwrap_enums
    # is removed (Python-level equality alone would still pass via str-mixin
    # inheritance, but rule-engine evaluation would silently return False).
    assert rule_engine.Rule(
        'trust.trust_id.trust_type == "joint"'
    ).matches(ctx) is True
    assert rule_engine.Rule(
        'trust.trust_id.trust_type == "individual"'
    ).matches(ctx) is False
```

The `test_minor_injection` test imports `Beneficiary` and `BeneficiaryRelation` directly from schema — verify these exist with these names. If schema uses different names (e.g., `BeneficiaryShare` is on the trust but children may live elsewhere), adjust during Red. The schema exploration confirmed `minor_beneficiaries(ref_date)` is a method, but did not enumerate the model it returns; the spec §5.2 implies `list[Beneficiary]`.

- [ ] **Step 2: Run tests to confirm Red**

Run: `pixi run test test_eval_context`
Expected: 8 tests, all fail with `ModuleNotFoundError: trust_generator.v3.diagnostics.eval_context`.

- [ ] **Step 3: Commit Cycle 2 Red**

```bash
git add tests/v3/diagnostics/test_eval_context.py
git commit -m "test(diagnostics): cycle 2 red — build_eval_context shape + injection contract"
```

- [ ] **Step 4: Author the production code (Green)**

Create `src/trust_generator/v3/diagnostics/__init__.py` as a placeholder (final exports added in Task 7):

```python
"""Diagnostics engine — see docs/superpowers/specs/2026-04-23-diagnostics-engine-design.md."""
```

Create `src/trust_generator/v3/diagnostics/eval_context.py`:

```python
"""Compose the dict-shaped context that rule expressions evaluate against.

Per spec §5.2: nested under three top-level namespaces (`trust`, `firm`, `now`)
so rule expressions read as ``trust.elections.estate_value_approximate >
firm.estate_thresholds.single_hard``.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any

from trust_generator.v3.config.firm import FirmConfig
from trust_generator.v3.schema import TrustData

COMPUTED_PROPERTIES: tuple[str, ...] = (
    "collected_total_value",
    "beneficiary_shares_total",
    "withdrawal_schedule_total",
    "disinherited_beneficiaries",
    "excluded_persons",
)


def _unwrap_enums(obj: Any) -> Any:
    """Recursively replace ``Enum`` instances with their ``.value``.

    rule-engine bypasses Python's ``__eq__`` when comparing context values
    against string literals; for ``str``-mixin Enum subclasses (e.g.
    ``TrustType(str, Enum)``) the raw instance compares correctly in
    Python but not through rule-engine, because rule-engine appears to
    call ``str()`` on the value — which returns the enum repr
    (``'TrustType.INDIVIDUAL'``), not the value (``'individual'``).

    Walks ``dict`` and ``list`` containers recursively. ``Decimal``,
    ``date``, ``UUID``, and other non-Enum scalars are returned untouched.
    """
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, dict):
        return {k: _unwrap_enums(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_unwrap_enums(v) for v in obj]
    return obj


def build_eval_context(
    trust: TrustData, config: FirmConfig, ref_date: date
) -> dict[str, Any]:
    """Compose the eval context for rule expression evaluation.

    Args:
        trust: post-fill canonical TrustData (consumed, not mutated).
        config: FirmConfig (consumed, not mutated).
        ref_date: explicit reference date; resolution chain handled by diagnose().

    Returns:
        ``{"trust": dict, "firm": dict, "now": date}``.
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

    return {
        "trust": _unwrap_enums(trust_dict),
        "firm": _unwrap_enums(config.model_dump(mode="python")),
        "now": ref_date,
    }
```

- [ ] **Step 5: Run tests to confirm Green**

Run: `pixi run test test_eval_context`
Expected: 8 tests pass.

If `test_minor_injection` fails because the schema's minor model is named differently from the test's import, adjust the test's import — the production code calls `trust.minor_beneficiaries(ref_date)` which the schema already provides per the source-grounding report.

- [ ] **Step 6: Run lint + type-check**

Run: `pixi run lint && pixi run mypy v3/diagnostics`
Expected: no errors.

- [ ] **Step 7: Commit Cycle 2 Green**

```bash
git add src/trust_generator/v3/diagnostics/__init__.py src/trust_generator/v3/diagnostics/eval_context.py
git commit -m "feat(diagnostics): cycle 2 green — build_eval_context with computed-property injection"
```

Cycle 2 has no substantive refactor (the spec's refactor note describes a hypothetical extraction "if a second consumer needs the same pattern" — no current second consumer). Skip Refactor commit.

---

## Task 3: Cycle 3 — Rule loader

**Files:**
- Create: `src/trust_generator/v3/diagnostics/errors.py`
- Create: `src/trust_generator/v3/diagnostics/loader.py` (DiagnosticRule + load_rules + helpers; evaluate stub for Cycle 4)
- Create: `src/trust_generator/v3/diagnostics/rules/builtin.yaml` (empty list)
- Test: `tests/v3/diagnostics/test_rule_loader.py`

This is the largest cycle (18 tests). The Red commit lands all tests at once; Green progressively makes them pass during one implementation pass; Refactor extracts `_dedupe_key` per the spec's explicit refactor note.

- [ ] **Step 1: Author the Cycle 3 test file (Red)**

Create `tests/v3/diagnostics/test_rule_loader.py`:

```python
"""Cycle 3 — rule loader: builtin + custom + namespace + collision + dedupe."""

from __future__ import annotations

import logging
from pathlib import Path
from textwrap import dedent

import pytest

from trust_generator.v3.diagnostics.errors import DiagnosticConfigError
from trust_generator.v3.diagnostics.loader import DiagnosticRule, load_rules


def _write_yaml(dir: Path, filename: str, content: str) -> Path:
    path = dir / filename
    path.write_text(dedent(content))
    return path


def _seed_builtin(content: str) -> None:
    """Overwrite the packaged builtin.yaml for the duration of a test.
    Since the loader resolves builtin via importlib.resources, tests that
    need a non-default builtin payload patch the resource. For this cycle's
    tests, we use the actual file in the source tree — which means tests
    must restore it. Use the pytest fixture in conftest if a non-default
    builtin is needed; here we test against the empty default.
    """
    # Implementation note: see Step 4's _load_builtin_rules; tests that
    # need to override builtin contents will use monkeypatch to swap
    # importlib.resources.files() return value.


def test_builtin_loads_empty(firm_config_factory):
    """Empty builtin.yaml yields no rules from the builtin set (no error).

    SCOPE ADDITION: spec did not pin empty-builtin behavior. This plan
    chose 'empty file = empty list' to mirror the empty-rules_dir
    semantics in test 3 below.
    """
    config = firm_config_factory()
    rules = load_rules(config)
    # Until rules plan lands, builtin.yaml is empty. Custom rules_dir is
    # also empty in this fixture. So load returns empty list.
    assert rules == []


def test_custom_loads(firm_config_factory, tmp_rules_dir: Path):
    config = firm_config_factory()
    _write_yaml(
        tmp_rules_dir,
        "custom_test_rule.yaml",
        """
        - code: custom.test.foo
          level: warning
          source: schema
          context: both
          message: "Test rule"
          expression: "trust.beneficiary_shares_total != 100"
        """,
    )
    rules = load_rules(config)
    codes = [r.code for r in rules]
    assert "custom.test.foo" in codes


def test_empty_rules_dir(firm_config_factory):
    """rules_dir with no files yields only builtins (which is also empty here)."""
    config = firm_config_factory()
    rules = load_rules(config)
    assert rules == []


def test_missing_rules_dir(firm_config_factory, tmp_path: Path):
    """rules_dir that does not exist on disk yields only builtins, no error."""
    config = firm_config_factory()
    config.diagnostics.rules_dir = tmp_path / "does_not_exist"
    rules = load_rules(config)
    assert rules == []


def test_builtin_namespace_enforcement(firm_config_factory, monkeypatch):
    """A builtin entry whose code starts with 'custom.' raises DiagnosticConfigError."""
    # Patch _load_builtin_rules to return a tampered rule list.
    from trust_generator.v3.diagnostics import loader

    def fake_builtin():
        return [
            DiagnosticRule.model_validate(
                {
                    "code": "custom.illegal",
                    "level": "error",
                    "source": "schema",
                    "message": "illegal",
                    "expression": "trust.x == 1",
                }
            )
        ]

    monkeypatch.setattr(loader, "_load_builtin_rules", fake_builtin)
    with pytest.raises(DiagnosticConfigError, match="custom.illegal"):
        load_rules(firm_config_factory())


def test_custom_namespace_enforcement(firm_config_factory, tmp_rules_dir: Path):
    """A custom file with code lacking 'custom.' prefix raises DiagnosticConfigError."""
    _write_yaml(
        tmp_rules_dir,
        "bad.yaml",
        """
        - code: estate.illegal
          level: error
          source: schema
          message: "no prefix"
          expression: "trust.x == 1"
        """,
    )
    with pytest.raises(DiagnosticConfigError, match="estate.illegal"):
        load_rules(firm_config_factory())


def test_expression_dedupe_positive(firm_config_factory, tmp_rules_dir, caplog, monkeypatch):
    """A custom rule duplicating a builtin's (expression, level) is dropped, with INFO log."""
    from trust_generator.v3.diagnostics import loader

    def fake_builtin():
        return [
            DiagnosticRule.model_validate(
                {
                    "code": "shares.sum_not_100",
                    "level": "error",
                    "source": "schema",
                    "message": "builtin",
                    "expression": "trust.beneficiary_shares_total != 100",
                }
            )
        ]

    monkeypatch.setattr(loader, "_load_builtin_rules", fake_builtin)
    _write_yaml(
        tmp_rules_dir,
        "duplicate.yaml",
        """
        - code: custom.dup
          level: error
          source: schema
          message: "custom dup"
          expression: "trust.beneficiary_shares_total!=100"
        """,
    )
    caplog.set_level(logging.INFO)
    rules = load_rules(firm_config_factory())
    codes = [r.code for r in rules]
    assert "custom.dup" not in codes
    assert "shares.sum_not_100" in codes
    assert any("custom.dup" in record.message for record in caplog.records)


def test_expression_dedupe_negative_level_differs(
    firm_config_factory, tmp_rules_dir, monkeypatch
):
    """Same expression but different level: not deduped."""
    from trust_generator.v3.diagnostics import loader

    def fake_builtin():
        return [
            DiagnosticRule.model_validate(
                {
                    "code": "shares.sum_not_100",
                    "level": "error",
                    "source": "schema",
                    "message": "builtin",
                    "expression": "trust.beneficiary_shares_total != 100",
                }
            )
        ]

    monkeypatch.setattr(loader, "_load_builtin_rules", fake_builtin)
    _write_yaml(
        tmp_rules_dir,
        "warning.yaml",
        """
        - code: custom.warn
          level: warning
          source: schema
          message: "custom warning"
          expression: "trust.beneficiary_shares_total != 100"
        """,
    )
    rules = load_rules(firm_config_factory())
    codes = [r.code for r in rules]
    assert "custom.warn" in codes


def test_malformed_yaml(firm_config_factory, tmp_rules_dir):
    _write_yaml(tmp_rules_dir, "broken.yaml", "this: : is: : invalid")
    with pytest.raises(DiagnosticConfigError, match="broken.yaml"):
        load_rules(firm_config_factory())


def test_schema_mismatch_missing_code(firm_config_factory, tmp_rules_dir):
    _write_yaml(
        tmp_rules_dir,
        "no_code.yaml",
        """
        - level: error
          source: schema
          message: "missing code"
          expression: "trust.x == 1"
        """,
    )
    with pytest.raises(DiagnosticConfigError, match="code"):
        load_rules(firm_config_factory())


def test_single_mapping_form(firm_config_factory, tmp_rules_dir):
    _write_yaml(
        tmp_rules_dir,
        "single.yaml",
        """
        code: custom.single.foo
        level: info
        source: schema
        message: "single mapping form"
        expression: "trust.x == 1"
        """,
    )
    rules = load_rules(firm_config_factory())
    assert any(r.code == "custom.single.foo" for r in rules)


def test_duplicate_code_within_builtins(firm_config_factory, monkeypatch):
    from trust_generator.v3.diagnostics import loader

    def fake_builtin():
        rule = DiagnosticRule.model_validate(
            {
                "code": "shares.dup",
                "level": "error",
                "source": "schema",
                "message": "dup",
                "expression": "trust.x == 1",
            }
        )
        return [rule, rule.model_copy()]

    monkeypatch.setattr(loader, "_load_builtin_rules", fake_builtin)
    with pytest.raises(DiagnosticConfigError, match="shares.dup"):
        load_rules(firm_config_factory())


def test_duplicate_code_across_files(firm_config_factory, tmp_rules_dir):
    body = """
        - code: custom.foo.bar
          level: error
          source: schema
          message: "rule"
          expression: "trust.x == 1"
        """
    _write_yaml(tmp_rules_dir, "first.yaml", body)
    _write_yaml(tmp_rules_dir, "second.yaml", body)
    with pytest.raises(DiagnosticConfigError, match="custom.foo.bar"):
        load_rules(firm_config_factory())


def test_malformed_expression_syntax(firm_config_factory, tmp_rules_dir):
    _write_yaml(
        tmp_rules_dir,
        "bad_expr.yaml",
        """
        - code: custom.bad.syntax
          level: error
          source: schema
          message: "bad expression"
          expression: "trust.x ===== 1"
        """,
    )
    with pytest.raises(DiagnosticConfigError, match="custom.bad.syntax"):
        load_rules(firm_config_factory())


def test_malformed_expression_regex(firm_config_factory, tmp_rules_dir):
    _write_yaml(
        tmp_rules_dir,
        "bad_regex.yaml",
        r"""
        - code: custom.bad.regex
          level: error
          source: schema
          message: "bad regex"
          expression: 'trust.name =~ "[unclosed"'
        """,
    )
    with pytest.raises(DiagnosticConfigError, match="custom.bad.regex"):
        load_rules(firm_config_factory())


def test_missing_builtin_yaml(firm_config_factory, monkeypatch):
    """If packaged builtin.yaml is absent, loader raises with resource identification."""
    import importlib.resources

    from trust_generator.v3.diagnostics import loader

    def fake_files(_pkg: str):
        class _MissingTraversable:
            def __truediv__(self, _other):
                return self

            def is_file(self):
                return False

            def read_text(self, encoding="utf-8"):
                raise FileNotFoundError("builtin.yaml missing")

        return _MissingTraversable()

    monkeypatch.setattr(importlib.resources, "files", fake_files)
    with pytest.raises(DiagnosticConfigError, match="builtin.yaml"):
        load_rules(firm_config_factory())


def test_unreadable_custom_file(firm_config_factory, tmp_rules_dir, monkeypatch):
    _write_yaml(
        tmp_rules_dir,
        "unreadable.yaml",
        """
        - code: custom.x.y
          level: info
          source: schema
          message: "x"
          expression: "trust.x == 1"
        """,
    )
    real_open = Path.open

    def patched_open(self, *args, **kwargs):
        if self.name == "unreadable.yaml":
            raise OSError("permission denied")
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", patched_open)
    with pytest.raises(DiagnosticConfigError, match="unreadable.yaml"):
        load_rules(firm_config_factory())
```

- [ ] **Step 2: Run tests to confirm Red**

Run: `pixi run test test_rule_loader`
Expected: 17 tests collected, all fail with `ModuleNotFoundError: trust_generator.v3.diagnostics.errors` (or `loader`).

- [ ] **Step 3: Commit Cycle 3 Red**

```bash
git add tests/v3/diagnostics/test_rule_loader.py
git commit -m "test(diagnostics): cycle 3 red — rule loader namespace, collision, dedupe contract"
```

- [ ] **Step 4: Author the production code (Green)**

Create `src/trust_generator/v3/diagnostics/errors.py`:

```python
"""Diagnostics-engine exception types."""

from __future__ import annotations


class DiagnosticConfigError(Exception):
    """Raised when rule loading fails: malformed YAML, schema mismatch,
    namespace violation, code collision, or expression compilation error.
    The loader's only failure mode; runtime evaluation errors yield
    meta-diagnostics rather than exceptions.
    """
```

Create `src/trust_generator/v3/diagnostics/rules/__init__.py` with empty content (makes `rules/` a regular package, not a PEP 420 namespace package — required for consistent `importlib.resources.files()` behavior across editable installs, wheel installs, and pyinstaller bundles per plan-review I2).

Create `src/trust_generator/v3/diagnostics/rules/builtin.yaml`:

```yaml
[]
```

Create `src/trust_generator/v3/diagnostics/loader.py`:

```python
"""Rule loader and DiagnosticRule model.

Per spec §6.4: load builtin (packaged) + custom (firm-side) rules,
enforce namespaces and code-collisions, dedupe custom against builtin,
compile every expression at load time.
"""

from __future__ import annotations

import importlib.resources
import logging
from pathlib import Path
from typing import Any

import rule_engine
import yaml
from pydantic import BaseModel, ConfigDict, PrivateAttr

from trust_generator.v3.config.firm import FirmConfig
from trust_generator.v3.diagnostics.errors import DiagnosticConfigError
from trust_generator.v3.schema import (
    Diagnostic,
    DiagnosticContext,
    DiagnosticLevel,
    DiagnosticSource,
)

_LOGGER = logging.getLogger(__name__)
_BUILTIN_RESOURCE = "trust_generator.v3.diagnostics.rules"
_BUILTIN_FILENAME = "builtin.yaml"


class DiagnosticRule(BaseModel):
    """A loaded, compiled rule. Evaluator method on the model per plan decision Q2."""

    model_config = ConfigDict(extra="forbid")

    code: str
    level: DiagnosticLevel
    source: DiagnosticSource
    context: DiagnosticContext = DiagnosticContext.BOTH
    message: str
    field_path: str | None = None
    expression: str
    enabled: bool = True

    _compiled: rule_engine.Rule | None = PrivateAttr(default=None)

    def evaluate(self, ctx: dict[str, Any]) -> Diagnostic | None:
        """Return a Diagnostic if the rule fires, else None.

        Cycle 4 implementation lands here; this stub returns None so
        Cycle 3's tests can construct rules without exercising eval.
        """
        if not self.enabled:
            return None
        if self._compiled is None:
            raise RuntimeError(
                f"DiagnosticRule {self.code!r} was not compiled by loader"
            )
        # Cycle 4 fills this in.
        return None


def load_rules(config: FirmConfig) -> list[DiagnosticRule]:
    """Load builtin and custom rules; enforce namespaces, collisions, dedupe; compile."""
    builtin = _load_builtin_rules()
    _enforce_namespace(builtin, allow_custom=False)
    _enforce_no_code_collisions(builtin, scope="builtin")
    _compile_expressions(builtin)

    custom = _load_custom_rules(config.diagnostics.rules_dir)
    _enforce_namespace(custom, allow_custom=True)
    _enforce_no_code_collisions(custom, scope="custom")
    _enforce_no_cross_code_collisions(builtin, custom)
    _compile_expressions(custom)
    custom = _dedupe_against(custom, builtin)

    return [r for r in (*builtin, *custom) if r.enabled]


def _load_builtin_rules() -> list[DiagnosticRule]:
    """Load the packaged builtin.yaml. Raises DiagnosticConfigError if absent or malformed."""
    try:
        resource = importlib.resources.files(_BUILTIN_RESOURCE) / _BUILTIN_FILENAME
        if not resource.is_file():
            raise DiagnosticConfigError(
                f"Packaged resource {_BUILTIN_FILENAME} not found in {_BUILTIN_RESOURCE}"
            )
        text = resource.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise DiagnosticConfigError(
            f"Packaged resource {_BUILTIN_FILENAME} missing: {exc}"
        ) from exc

    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise DiagnosticConfigError(
            f"Malformed YAML in packaged {_BUILTIN_FILENAME}: {exc}"
        ) from exc

    if parsed is None or parsed == []:
        return []
    if not isinstance(parsed, list):
        raise DiagnosticConfigError(
            f"Packaged {_BUILTIN_FILENAME} must be a YAML list, got {type(parsed).__name__}"
        )
    return [_validate_rule(item, source_label=_BUILTIN_FILENAME) for item in parsed]


def _load_custom_rules(rules_dir: Path) -> list[DiagnosticRule]:
    """Load all .yaml files under rules_dir as custom rules. Missing dir = empty list."""
    if not rules_dir.exists():
        return []
    rules: list[DiagnosticRule] = []
    for path in sorted(rules_dir.glob("*.yaml")):
        try:
            with path.open(encoding="utf-8") as fh:
                text = fh.read()
        except OSError as exc:
            raise DiagnosticConfigError(
                f"Failed to read custom rule file {path}: {exc}"
            ) from exc

        try:
            parsed = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise DiagnosticConfigError(
                f"Malformed YAML in {path}: {exc}"
            ) from exc

        if parsed is None:
            continue
        items = parsed if isinstance(parsed, list) else [parsed]
        for item in items:
            rules.append(_validate_rule(item, source_label=str(path)))
    return rules


def _validate_rule(item: Any, source_label: str) -> DiagnosticRule:
    try:
        return DiagnosticRule.model_validate(item)
    except Exception as exc:  # noqa: BLE001 — Pydantic raises ValidationError + others
        raise DiagnosticConfigError(
            f"Invalid rule entry in {source_label}: {exc}"
        ) from exc


def _enforce_namespace(rules: list[DiagnosticRule], *, allow_custom: bool) -> None:
    for rule in rules:
        is_custom = rule.code.startswith("custom.")
        if allow_custom and not is_custom:
            raise DiagnosticConfigError(
                f"Custom rule {rule.code!r} must use 'custom.' namespace prefix"
            )
        if not allow_custom and is_custom:
            raise DiagnosticConfigError(
                f"Builtin rule {rule.code!r} must not use 'custom.' namespace prefix"
            )


def _enforce_no_code_collisions(rules: list[DiagnosticRule], *, scope: str) -> None:
    seen: set[str] = set()
    for rule in rules:
        if rule.code in seen:
            raise DiagnosticConfigError(
                f"Duplicate rule code {rule.code!r} within {scope} rule set"
            )
        seen.add(rule.code)


def _enforce_no_cross_code_collisions(
    builtin: list[DiagnosticRule], custom: list[DiagnosticRule]
) -> None:
    builtin_codes = {r.code for r in builtin}
    for rule in custom:
        if rule.code in builtin_codes:
            raise DiagnosticConfigError(
                f"Rule code {rule.code!r} collides between builtin and custom sets"
            )


def _compile_expressions(rules: list[DiagnosticRule]) -> None:
    ctx = _build_rule_context()
    for rule in rules:
        try:
            compiled = rule_engine.Rule(rule.expression, context=ctx)
        except (
            rule_engine.errors.RuleSyntaxError,
            rule_engine.errors.RegexSyntaxError,
        ) as exc:
            # Note: AttributeResolutionError is NOT raised at compile time
            # because trust/firm are typed UNDEFINED (rule-engine defers
            # attribute resolution to evaluation). Catching it here would
            # be dead code. It IS caught at evaluation time (see
            # DiagnosticRule.evaluate, Cycle 4) where it surfaces as the
            # engine.symbol_unknown meta-diagnostic.
            raise DiagnosticConfigError(
                f"Expression compilation failed for rule {rule.code!r}: {exc}"
            ) from exc
        rule._compiled = compiled


def _build_rule_context() -> rule_engine.Context:
    type_resolver = rule_engine.type_resolver_from_dict(
        {
            "trust": rule_engine.DataType.UNDEFINED,
            "firm": rule_engine.DataType.UNDEFINED,
            "now": rule_engine.DataType.DATETIME,
        }
    )
    return rule_engine.Context(type_resolver=type_resolver)


def _dedupe_key(rule: DiagnosticRule) -> tuple[str, DiagnosticLevel]:
    """Whitespace-stripped expression + level. Refactor target (§7 open seam: AST normalization)."""
    return ("".join(rule.expression.split()), rule.level)


def _dedupe_against(
    custom: list[DiagnosticRule], builtin: list[DiagnosticRule]
) -> list[DiagnosticRule]:
    builtin_keys = {_dedupe_key(r) for r in builtin}
    kept: list[DiagnosticRule] = []
    for rule in custom:
        if _dedupe_key(rule) in builtin_keys:
            _LOGGER.info(
                "Dropped custom rule %r: matches builtin (expression, level)", rule.code
            )
            continue
        kept.append(rule)
    return kept


def _meta_diagnostic(code: str, rule_code: str, detail: str) -> Diagnostic:
    """Construct a meta-diagnostic for runtime evaluation failures (Cycle 4)."""
    return Diagnostic(
        level=DiagnosticLevel.WARNING,
        code=code,
        message=f"Rule {rule_code} failed at engine evaluation: {detail}",
        field_path=None,
        source=DiagnosticSource.SCHEMA,
        context=DiagnosticContext.BOTH,
    )
```

The `loader.py` is large because it concentrates both Cycle 3 (loader) and Cycle 4 (evaluator) production code. Cycle 4's Green step adds the evaluator body to `DiagnosticRule.evaluate` only.

Note on `_dedupe_key` placement: it's already extracted in this Green commit because doing so makes it directly testable in Cycle 3's test suite (test_expression_dedupe_*) without an awkward inner-function reach. This is a minor early-extraction that makes Step 6's "Refactor" step lighter but still substantive (the refactor commit will additionally add a docstring and a unit test that targets `_dedupe_key` directly to pin the AST-normalization seam from §7).

- [ ] **Step 5: Run tests to confirm Green**

Run: `pixi run test test_rule_loader`
Expected: 17 tests pass.

- [ ] **Step 6: Run lint + type-check**

Run: `pixi run lint && pixi run mypy v3/diagnostics`
Expected: no errors. Note: mypy may flag the `except Exception` in `_validate_rule`; if so, narrow to `pydantic.ValidationError, TypeError, ValueError` after running tests once to see which are actually raised.

- [ ] **Step 6b: Verify the wheel includes `builtin.yaml`**

Run: `pixi run build && pixi run python -c "import zipfile; print([n for n in zipfile.ZipFile(__import__('glob').glob('*.whl')[0]).namelist() if n.endswith('.yaml')])"`

Expected output: a list including `trust_generator/v3/diagnostics/rules/builtin.yaml`. If empty, hatchling is excluding non-`.py` files from the wheel — add explicit inclusion to `pyproject.toml`:

```toml
[tool.hatch.build.targets.wheel.force-include]
"src/trust_generator/v3/diagnostics/rules/builtin.yaml" = "trust_generator/v3/diagnostics/rules/builtin.yaml"
```

Then re-run the verification. This protects the production install path (where `importlib.resources.files()` reads from the installed wheel, not from the source tree).

- [ ] **Step 7: Commit Cycle 3 Green**

```bash
git add src/trust_generator/v3/diagnostics/errors.py src/trust_generator/v3/diagnostics/loader.py src/trust_generator/v3/diagnostics/rules/__init__.py src/trust_generator/v3/diagnostics/rules/builtin.yaml
# If pyproject.toml was edited in step 6b, also: git add pyproject.toml
git commit -m "feat(diagnostics): cycle 3 green — rule loader with namespace, collision, dedupe, compilation"
```

- [ ] **Step 8: Refactor — pin `_dedupe_key` as the AST-normalization seam**

Add a focused unit test `tests/v3/diagnostics/test_rule_loader.py` (append to existing file):

```python
def test_dedupe_key_whitespace_normalization():
    """Pin the dedupe-key contract: whitespace-stripped expression + level.

    Documented as the AST-normalization seam (§7 open seam): future versions
    may replace whitespace stripping with rule-engine AST traversal.
    """
    from trust_generator.v3.diagnostics.loader import _dedupe_key

    rule_a = DiagnosticRule.model_validate(
        {
            "code": "x.a",
            "level": "error",
            "source": "schema",
            "message": "a",
            "expression": "trust.x  ==  1",
        }
    )
    rule_b = DiagnosticRule.model_validate(
        {
            "code": "x.b",
            "level": "error",
            "source": "schema",
            "message": "b",
            "expression": "trust.x==1",
        }
    )
    rule_c = DiagnosticRule.model_validate(
        {
            "code": "x.c",
            "level": "warning",  # different level!
            "source": "schema",
            "message": "c",
            "expression": "trust.x==1",
        }
    )

    assert _dedupe_key(rule_a) == _dedupe_key(rule_b)
    assert _dedupe_key(rule_a) != _dedupe_key(rule_c)
```

Run: `pixi run test test_dedupe_key_whitespace_normalization`
Expected: passes.

- [ ] **Step 9: Commit Cycle 3 Refactor**

```bash
git add tests/v3/diagnostics/test_rule_loader.py
git commit -m "refactor(diagnostics): cycle 3 — pin _dedupe_key as AST-normalization seam"
```

---

## Task 4: Cycle 4 — Rule evaluator

**Files:**
- Modify: `src/trust_generator/v3/diagnostics/loader.py` (fill in `DiagnosticRule.evaluate` body)
- Test: `tests/v3/diagnostics/test_rule_evaluator.py`

- [ ] **Step 1: Author the Cycle 4 test file (Red)**

Create `tests/v3/diagnostics/test_rule_evaluator.py`:

```python
"""Cycle 4 — rule evaluator: match, no-match, disabled, meta-diagnostic surfacing."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from trust_generator.v3.diagnostics.loader import (
    DiagnosticRule,
    _build_rule_context,
)
from trust_generator.v3.schema import (
    BeneficiaryShare,
    DiagnosticLevel,
    DiagnosticSource,
)


def _compile(rule: DiagnosticRule) -> DiagnosticRule:
    """Helper: compile a freshly-constructed rule (loader normally does this)."""
    import rule_engine

    rule._compiled = rule_engine.Rule(rule.expression, context=_build_rule_context())
    return rule


def test_evaluator_match():
    rule = _compile(
        DiagnosticRule.model_validate(
            {
                "code": "shares.sum_not_100",
                "level": "error",
                "source": "schema",
                "message": "shares must sum to 100",
                "field_path": "beneficiary_shares",
                "expression": "trust.beneficiary_shares_total != 100",
            }
        )
    )
    ctx = {"trust": {"beneficiary_shares_total": Decimal("99")}, "firm": {}, "now": date(2026, 4, 23)}
    result = rule.evaluate(ctx)
    assert result is not None
    assert result.code == "shares.sum_not_100"
    assert result.level == DiagnosticLevel.ERROR
    assert result.source == DiagnosticSource.SCHEMA
    assert result.field_path == "beneficiary_shares"


def test_evaluator_no_match():
    rule = _compile(
        DiagnosticRule.model_validate(
            {
                "code": "shares.sum_not_100",
                "level": "error",
                "source": "schema",
                "message": "shares must sum to 100",
                "expression": "trust.beneficiary_shares_total != 100",
            }
        )
    )
    ctx = {"trust": {"beneficiary_shares_total": Decimal("100")}, "firm": {}, "now": date(2026, 4, 23)}
    assert rule.evaluate(ctx) is None


def test_evaluator_disabled():
    rule = _compile(
        DiagnosticRule.model_validate(
            {
                "code": "shares.sum_not_100",
                "level": "error",
                "source": "schema",
                "message": "shares must sum to 100",
                "expression": "trust.beneficiary_shares_total != 100",
                "enabled": False,
            }
        )
    )
    ctx = {"trust": {"beneficiary_shares_total": Decimal("99")}, "firm": {}, "now": date(2026, 4, 23)}
    assert rule.evaluate(ctx) is None


def test_evaluator_symbol_unknown_meta():
    rule = _compile(
        DiagnosticRule.model_validate(
            {
                "code": "x.symbol",
                "level": "error",
                "source": "schema",
                "message": "x",
                "expression": "trust.nonexistent_field == 1",
            }
        )
    )
    ctx = {"trust": {}, "firm": {}, "now": date(2026, 4, 23)}
    result = rule.evaluate(ctx)
    assert result is not None
    assert result.code == "engine.symbol_unknown"
    assert result.level == DiagnosticLevel.WARNING
    assert "x.symbol" in result.message
    assert "nonexistent_field" in result.message


def test_evaluator_eval_error_meta():
    rule = _compile(
        DiagnosticRule.model_validate(
            {
                "code": "x.evalerr",
                "level": "error",
                "source": "schema",
                "message": "x",
                "expression": "trust.name + 1",
            }
        )
    )
    ctx = {"trust": {"name": "alice"}, "firm": {}, "now": date(2026, 4, 23)}
    result = rule.evaluate(ctx)
    assert result is not None
    assert result.code == "engine.eval_error"
    assert result.level == DiagnosticLevel.WARNING
    assert "x.evalerr" in result.message


def test_evaluator_no_recompile_between_calls():
    """Compiled-rule identity: evaluator does not mutate _compiled."""
    rule = _compile(
        DiagnosticRule.model_validate(
            {
                "code": "x.identity",
                "level": "error",
                "source": "schema",
                "message": "x",
                "expression": "trust.beneficiary_shares_total != 100",
            }
        )
    )
    ctx = {"trust": {"beneficiary_shares_total": Decimal("99")}, "firm": {}, "now": date(2026, 4, 23)}
    initial_compiled = rule._compiled
    rule.evaluate(ctx)
    rule.evaluate(ctx)
    assert rule._compiled is initial_compiled
```

- [ ] **Step 2: Run tests to confirm Red**

Run: `pixi run test test_rule_evaluator`
Expected: 6 tests fail. The first three (match/no-match/disabled) fail because the stub returns `None` always; the meta tests fail because the symbol/eval-error paths aren't wired; the identity test depends on the others succeeding.

- [ ] **Step 3: Commit Cycle 4 Red**

```bash
git add tests/v3/diagnostics/test_rule_evaluator.py
git commit -m "test(diagnostics): cycle 4 red — rule evaluator match/meta-diagnostic contract"
```

- [ ] **Step 4: Implement `DiagnosticRule.evaluate` body**

In `src/trust_generator/v3/diagnostics/loader.py`, replace the `DiagnosticRule.evaluate` method with:

```python
    def evaluate(self, ctx: dict[str, Any]) -> Diagnostic | None:
        """Return a Diagnostic if the rule fires, else None.

        Runtime errors (symbol unknown, attribute unresolvable, evaluation
        type mismatch) yield meta-diagnostics rather than raising. Per
        spec §6.5: the intent of "engine.symbol_unknown" is "attribute
        or top-level symbol could not be resolved" — rule-engine raises
        ``SymbolResolutionError`` for unresolved top-level symbols and
        ``AttributeResolutionError`` for unresolved attributes; both are
        siblings under ``EvaluationError``. The evaluator maps both to
        the same meta code per the spec's intent.

        Catch ordering: subclass-first per Python exception semantics —
        SymbolResolutionError and AttributeResolutionError are subclasses
        of EvaluationError, so they must be caught before the parent.
        """
        if not self.enabled:
            return None
        if self._compiled is None:
            raise RuntimeError(
                f"DiagnosticRule {self.code!r} was not compiled by loader"
            )
        try:
            matched = self._compiled.matches(ctx)
        except rule_engine.errors.SymbolResolutionError as exc:
            return _meta_diagnostic(
                "engine.symbol_unknown", self.code, str(exc.symbol_name)
            )
        except rule_engine.errors.AttributeResolutionError as exc:
            return _meta_diagnostic(
                "engine.symbol_unknown", self.code, str(exc.attribute_name)
            )
        except rule_engine.errors.EvaluationError as exc:
            return _meta_diagnostic("engine.eval_error", self.code, str(exc))
        if not matched:
            return None
        return Diagnostic(
            level=self.level,
            code=self.code,
            message=self.message,
            field_path=self.field_path,
            source=self.source,
            context=self.context,
        )
```

Note on rule-engine attribute names: per the rule-engine 4.5.3 docs (`rule_engine/errors.py`), `SymbolResolutionError.symbol_name` and `AttributeResolutionError.attribute_name` are the canonical attributes. If the installed package version exposes different names, the test failures will surface them — adjust accordingly.

- [ ] **Step 5: Run tests to confirm Green**

Run: `pixi run test test_rule_evaluator`
Expected: 6 tests pass.

- [ ] **Step 6: Run full diagnostics test sweep + lint + type-check**

Run: `pixi run test test_ && pixi run lint && pixi run mypy v3/diagnostics`
Expected: all diagnostics tests pass except the xfailed Cycle 1 test (which still fails at import); no lint/type errors.

- [ ] **Step 7: Commit Cycle 4 Green**

```bash
git add src/trust_generator/v3/diagnostics/loader.py
git commit -m "feat(diagnostics): cycle 4 green — DiagnosticRule.evaluate with meta-diagnostic surfacing"
```

Cycle 4 has no substantive refactor (the spec's note is "verify `now` typed as DATETIME doesn't reject `date` objects" — covered by the existing test suite's use of `date` values in ctx, no separate refactor commit needed).

---

## Task 5: Cycle 5 — Audit log writer

**Files:**
- Create: `src/trust_generator/v3/diagnostics/audit.py` (AuditRecord, AuditLog; force_generation/validate_override_reason added in Task 6)
- Test: `tests/v3/diagnostics/test_audit_log.py`

- [ ] **Step 1: Author the Cycle 5 test file (Red)**

Create `tests/v3/diagnostics/test_audit_log.py`:

```python
"""Cycle 5 — audit log writer: JSONL, append, monthly rotation, path absoluteness, atomic write."""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path

import freezegun

from trust_generator.v3.diagnostics.audit import AuditLog, AuditRecord


def _make_record(timestamp: datetime) -> AuditRecord:
    return AuditRecord(
        timestamp=timestamp,
        user="testuser",
        trust_ref="F-2026-0001",
        overridden_codes=["estate.crossed_cliff"],
        reason="Client confirmed estate value with attorney 2026-04-22.",
        restriction_level="error",
    )


@freezegun.freeze_time("2026-04-23T14:30:00")
def test_write_produces_file(tmp_audit_dir: Path):
    log = AuditLog(tmp_audit_dir)
    record = _make_record(datetime.now().astimezone())
    path = log.write(record)
    assert path.exists()
    assert path.name == "audit-2026-04.jsonl"


@freezegun.freeze_time("2026-04-23T14:30:00")
def test_jsonline_shape(tmp_audit_dir: Path):
    log = AuditLog(tmp_audit_dir)
    record = _make_record(datetime.now().astimezone())
    path = log.write(record)
    line = path.read_text(encoding="utf-8").strip()
    parsed = json.loads(line)
    assert set(parsed.keys()) == {
        "timestamp",
        "user",
        "trust_ref",
        "overridden_codes",
        "reason",
        "restriction_level",
    }
    assert parsed["user"] == "testuser"
    assert parsed["overridden_codes"] == ["estate.crossed_cliff"]
    assert parsed["restriction_level"] == "error"


@freezegun.freeze_time("2026-04-23T14:30:00")
def test_append(tmp_audit_dir: Path):
    log = AuditLog(tmp_audit_dir)
    record = _make_record(datetime.now().astimezone())
    log.write(record)
    log.write(record)
    path = tmp_audit_dir / "audit-2026-04.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2


def test_monthly_rotation(tmp_audit_dir: Path):
    log = AuditLog(tmp_audit_dir)
    with freezegun.freeze_time("2026-04-30T23:59:00"):
        log.write(_make_record(datetime.now().astimezone()))
    with freezegun.freeze_time("2026-05-01T00:00:00"):
        log.write(_make_record(datetime.now().astimezone()))
    assert (tmp_audit_dir / "audit-2026-04.jsonl").exists()
    assert (tmp_audit_dir / "audit-2026-05.jsonl").exists()


def test_path_is_absolute(tmp_audit_dir: Path):
    """Constructor accepts a Path and writes against it as-is."""
    log = AuditLog(tmp_audit_dir.resolve())
    assert log.dir.is_absolute()


@freezegun.freeze_time("2026-04-23T14:30:00")
def test_atomic_write_per_line(tmp_audit_dir: Path):
    """Concurrent writes from two AuditLog instances against the same dir must
    not interleave bytes within a single record (spec §6.6 test 6).

    POSIX guarantees ``O_APPEND`` writes ≤ ``PIPE_BUF`` (4096 bytes) are atomic.
    Each serialized record is ~150 bytes, well under that limit, so a single
    ``write()`` call from each thread lands as one contiguous chunk.
    """
    n_per_thread = 50
    log_a = AuditLog(tmp_audit_dir)
    log_b = AuditLog(tmp_audit_dir)
    timestamp = datetime.now().astimezone()

    def _write_many(log: AuditLog, user: str) -> None:
        for i in range(n_per_thread):
            log.write(
                AuditRecord(
                    timestamp=timestamp,
                    user=user,
                    trust_ref=f"F-2026-{i:04d}",
                    overridden_codes=["estate.crossed_cliff"],
                    reason="Client confirmed estate value with attorney 2026-04-22.",
                    restriction_level="error",
                )
            )

    thread_a = threading.Thread(target=_write_many, args=(log_a, "threadA"))
    thread_b = threading.Thread(target=_write_many, args=(log_b, "threadB"))
    thread_a.start()
    thread_b.start()
    thread_a.join()
    thread_b.join()

    path = tmp_audit_dir / "audit-2026-04.jsonl"
    raw = path.read_text(encoding="utf-8")
    # Trailing newline after last record means splitlines() yields exactly the
    # records, no spurious empty trailing element.
    lines = raw.splitlines()
    assert len(lines) == 2 * n_per_thread

    users_seen: set[str] = set()
    for line in lines:
        parsed = json.loads(line)  # raises if any line has interleaved bytes
        users_seen.add(parsed["user"])
    assert users_seen == {"threadA", "threadB"}
```

- [ ] **Step 2: Run tests to confirm Red**

Run: `pixi run test test_audit_log`
Expected: 6 tests fail with `ModuleNotFoundError: trust_generator.v3.diagnostics.audit`.

- [ ] **Step 3: Commit Cycle 5 Red**

```bash
git add tests/v3/diagnostics/test_audit_log.py
git commit -m "test(diagnostics): cycle 5 red — audit log JSONL/append/rotation contract"
```

- [ ] **Step 4: Author the production code (Green)**

Create `src/trust_generator/v3/diagnostics/audit.py`:

```python
"""Audit log writer for force_generation overrides.

Per spec §5.5, §6.6: JSONL, monthly-rotated, per-user-subfolder path scheme.
The override flow (force_generation, validate_override_reason) lands in
Cycle 6 alongside this writer.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class AuditRecord(BaseModel):
    """One override event. JSONL-serialized via model_dump_json()."""

    model_config = ConfigDict(extra="forbid")

    timestamp: datetime
    user: str
    trust_ref: str
    overridden_codes: list[str]
    reason: str
    restriction_level: str


class AuditLog:
    """Append-only JSONL writer to a per-user audit directory."""

    def __init__(self, dir: Path) -> None:
        self.dir = dir

    def write(self, record: AuditRecord) -> Path:
        """Append the record as one JSONL line; return the file path."""
        self.dir.mkdir(parents=True, exist_ok=True)
        filename = f"audit-{record.timestamp:%Y-%m}.jsonl"
        path = self.dir / filename
        line = record.model_dump_json() + "\n"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line)
        return path
```

- [ ] **Step 5: Run tests to confirm Green**

Run: `pixi run test test_audit_log`
Expected: 6 tests pass.

- [ ] **Step 6: Run lint + type-check**

Run: `pixi run lint && pixi run mypy v3/diagnostics`
Expected: no errors.

- [ ] **Step 7: Commit Cycle 5 Green**

```bash
git add src/trust_generator/v3/diagnostics/audit.py
git commit -m "feat(diagnostics): cycle 5 green — JSONL audit log with monthly rotation"
```

Cycle 5 has no substantive refactor (the spec's note is operational documentation about timezone seams, not a code change).

---

## Task 6: Cycle 6 — Override flow

**Files:**
- Modify: `src/trust_generator/v3/diagnostics/audit.py` (add `force_generation`, `validate_override_reason`)
- Test: `tests/v3/diagnostics/test_override.py`

- [ ] **Step 1: Author the Cycle 6 test file (Red)**

Create `tests/v3/diagnostics/test_override.py`:

```python
"""Cycle 6 — override flow: force_generation + validate_override_reason."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from trust_generator.v3.diagnostics.audit import (
    AuditRecord,
    force_generation,
    validate_override_reason,
)
from trust_generator.v3.schema import (
    BeneficiaryShare,
    Diagnostic,
    DiagnosticLevel,
    DiagnosticSource,
)


def _diag(code: str) -> Diagnostic:
    return Diagnostic(
        level=DiagnosticLevel.ERROR,
        code=code,
        message=f"{code} fired",
        source=DiagnosticSource.SCHEMA,
    )


def test_happy_path_writes_record(firm_config_factory, trust_data_factory, tmp_audit_dir: Path):
    config = firm_config_factory()
    trust = trust_data_factory(file_number="F-2026-0042")
    diagnostics = [_diag("shares.sum_not_100")]

    record = force_generation(
        trust, config, diagnostics, reason="Confirmed by attorney 2026-04-22."
    )

    assert isinstance(record, AuditRecord)
    assert record.user == "testuser"
    assert record.trust_ref == "F-2026-0042"
    assert record.overridden_codes == ["shares.sum_not_100"]
    assert record.restriction_level == "error"

    files = list(tmp_audit_dir.glob("*.jsonl"))
    assert len(files) == 1
    parsed = json.loads(files[0].read_text(encoding="utf-8").splitlines()[0])
    assert parsed["overridden_codes"] == ["shares.sum_not_100"]


def test_empty_reason_rejected(firm_config_factory, trust_data_factory):
    config = firm_config_factory()
    trust = trust_data_factory()
    with pytest.raises(ValueError, match="10 non-whitespace"):
        force_generation(trust, config, [_diag("x.y")], reason="")


def test_short_reason_rejected(firm_config_factory, trust_data_factory):
    config = firm_config_factory()
    trust = trust_data_factory()
    with pytest.raises(ValueError, match="10 non-whitespace"):
        force_generation(trust, config, [_diag("x.y")], reason="ok")


def test_validate_override_reason_module_helper():
    """The standalone helper is exposed for GUI live-validation per spec §5.6."""
    with pytest.raises(ValueError):
        validate_override_reason("short")
    validate_override_reason("this is long enough to pass")  # no raise


def test_trust_ref_fallback(firm_config_factory, trust_data_factory):
    """Empty file_number yields trust_ref='unidentified'."""
    config = firm_config_factory()
    trust = trust_data_factory(file_number="")
    record = force_generation(
        trust, config, [_diag("x.y")], reason="ten or more characters here"
    )
    assert record.trust_ref == "unidentified"


def test_codes_preserved_in_order(firm_config_factory, trust_data_factory):
    config = firm_config_factory()
    trust = trust_data_factory()
    diagnostics = [_diag("a.b"), _diag("c.d"), _diag("e.f")]
    record = force_generation(
        trust, config, diagnostics, reason="ten or more characters here"
    )
    assert record.overridden_codes == ["a.b", "c.d", "e.f"]


def test_no_mutation(firm_config_factory, trust_data_factory):
    config = firm_config_factory()
    trust = trust_data_factory(file_number="F-X")
    diagnostics = [_diag("a.b")]

    trust_before = trust.model_copy(deep=True)
    config_before = config.model_copy(deep=True)
    diagnostics_before = list(diagnostics)

    force_generation(
        trust, config, diagnostics, reason="ten or more characters here"
    )

    assert trust == trust_before
    assert config == config_before
    assert diagnostics == diagnostics_before
```

Note on test_no_mutation: Pydantic's `model_copy(deep=True)` plus `==` works for `BaseModel` instances (they support equality). If the comparison fails for an unexpected reason (e.g., `Path` resolution differences inside FirmConfig), the test will need adjustment, but the contract is "no mutation" not "byte-identical."

The `test_missing_upn_at_load` test referenced in spec §6.7 #4 is intentionally absent here — that's a firm-config-level test and lives adjacent in `tests/v3/config/test_firm.py`, not in this plan's scope. The cross-reference is documented in the cycle's docstring.

- [ ] **Step 2: Run tests to confirm Red**

Run: `pixi run test test_override`
Expected: 7 tests fail with `ImportError: cannot import name 'force_generation' from 'trust_generator.v3.diagnostics.audit'`.

- [ ] **Step 3: Commit Cycle 6 Red**

```bash
git add tests/v3/diagnostics/test_override.py
git commit -m "test(diagnostics): cycle 6 red — force_generation override flow contract"
```

- [ ] **Step 4: Implement override flow**

In `src/trust_generator/v3/diagnostics/audit.py`, append after the `AuditLog` class:

```python
from trust_generator.v3.config.firm import FirmConfig
from trust_generator.v3.schema import Diagnostic, TrustData


def validate_override_reason(reason: str) -> None:
    """Reject reasons shorter than 10 non-whitespace characters.

    Exposed at module level so GUI flows can live-validate before submit
    per spec §5.6.
    """
    if len(reason.strip()) < 10:
        raise ValueError(
            "force_generation requires a reason of at least 10 non-whitespace characters"
        )


def force_generation(
    trust: TrustData,
    config: FirmConfig,
    diagnostics: list[Diagnostic],
    *,
    reason: str,
) -> AuditRecord:
    """Record an authorized override of blocking diagnostics.

    Per spec §5.6: pure with respect to its inputs (no mutation), writes
    one JSONL record to the configured audit directory, returns the
    written record.
    """
    validate_override_reason(reason)
    record = AuditRecord(
        timestamp=datetime.now().astimezone(),
        user=config.user.upn,
        trust_ref=trust.office.file_number or "unidentified",
        overridden_codes=[d.code for d in diagnostics],
        reason=reason,
        restriction_level=config.diagnostics.default_restriction_level,
    )
    AuditLog(config.diagnostics.audit_log_dir).write(record)
    return record
```

Note: the `from trust_generator.v3.config.firm import FirmConfig` import lands at module top per ruff convention; if ruff complains about ordering, move it to the existing top-level imports in audit.py.

- [ ] **Step 5: Run tests to confirm Green**

Run: `pixi run test test_override`
Expected: 7 tests pass.

- [ ] **Step 6: Run lint + type-check**

Run: `pixi run lint && pixi run mypy v3/diagnostics`
Expected: no errors.

- [ ] **Step 7: Commit Cycle 6 Green**

```bash
git add src/trust_generator/v3/diagnostics/audit.py
git commit -m "feat(diagnostics): cycle 6 green — force_generation override with audit log write"
```

---

## Task 7: Wire `diagnose()` entry point and finalize public surface

**Files:**
- Create: `src/trust_generator/v3/diagnostics/engine.py`
- Modify: `src/trust_generator/v3/diagnostics/__init__.py` (full re-exports)

This task wires the coordinator (`diagnose()`) and finalizes the package's public surface. The Cycle 1 integration test will progress from `ImportError` (collection failure) to `xfail` (collected, marker takes effect). The xfail remains until the rules plan lands.

- [ ] **Step 1: Author `engine.py`**

Create `src/trust_generator/v3/diagnostics/engine.py`:

```python
"""diagnose() entry point — pure coordinator over the diagnostics subsystem.

Per spec §5.1: builds eval context, loads + caches rules, evaluates each,
returns the diagnostic list in (builtin_load_order, custom_load_order) sequence.
"""

from __future__ import annotations

from datetime import date

from trust_generator.v3.config.firm import FirmConfig
from trust_generator.v3.diagnostics.eval_context import build_eval_context
from trust_generator.v3.diagnostics.loader import load_rules
from trust_generator.v3.schema import Diagnostic, TrustData


def diagnose(
    trust: TrustData,
    config: FirmConfig,
    *,
    ref_date: date | None = None,
) -> list[Diagnostic]:
    """Compute diagnostics for a TrustData against a FirmConfig.

    Args:
        trust: post-fill canonical TrustData (consumed, not mutated).
        config: FirmConfig (consumed, not mutated).
        ref_date: explicit reference date for time-dependent rule context;
            defaults via chain ``trust.trust_id.execution_date -> date.today()``.

    Returns:
        List of Diagnostic instances in (builtin_load_order, custom_load_order)
        sequence. Never raises during evaluation; runtime failures yield
        meta-diagnostics in-stream.
    """
    resolved_ref_date = (
        ref_date or trust.trust_id.execution_date or date.today()
    )
    ctx = build_eval_context(trust, config, resolved_ref_date)
    rules = load_rules(config)
    diagnostics: list[Diagnostic] = []
    for rule in rules:
        result = rule.evaluate(ctx)
        if result is not None:
            diagnostics.append(result)
    return diagnostics
```

- [ ] **Step 2: Finalize the package `__init__.py`**

Replace `src/trust_generator/v3/diagnostics/__init__.py` with:

```python
"""Diagnostics engine — see docs/superpowers/specs/2026-04-23-diagnostics-engine-design.md.

Public surface:
    diagnose(trust, config, *, ref_date=None) -> list[Diagnostic]
    force_generation(trust, config, diagnostics, *, reason) -> AuditRecord
    validate_override_reason(reason) -> None
    DiagnosticConfigError — raised on rule load failure
"""

from __future__ import annotations

from trust_generator.v3.diagnostics.audit import (
    force_generation,
    validate_override_reason,
)
from trust_generator.v3.diagnostics.engine import diagnose
from trust_generator.v3.diagnostics.errors import DiagnosticConfigError

__all__ = [
    "DiagnosticConfigError",
    "diagnose",
    "force_generation",
    "validate_override_reason",
]
```

- [ ] **Step 3: Run the full diagnostics test suite to confirm Cycle 1 reaches xfail state**

Run: `pixi run test test_diagnose_triggers_all_starter_rules`
Expected: one test reported as `XFAIL` (not `FAILED` due to collection error). The marker is now active because the import succeeds.

- [ ] **Step 4: Run the full project gate**

Run: `pixi run check`
Expected: lint passes, mypy passes, all non-xfailed tests pass, Cycle 1 reports XFAIL. The gate is **green** (xfail does not fail the gate).

- [ ] **Step 5: Commit engine wire-up**

```bash
git add src/trust_generator/v3/diagnostics/engine.py src/trust_generator/v3/diagnostics/__init__.py
git commit -m "feat(diagnostics): cycle 1 wire-up — diagnose() coordinator + public re-exports"
```

- [ ] **Step 6: Update plans.xml status**

Edit `.claude/context/plans.xml`:
1. Set the `status` attribute on the index 7 entry from `"open"` to `"closed"`.
2. Set the `plan-md` attribute to `"docs/superpowers/plans/2026-04-23-diagnostics-engine-core.md"`.
3. Update the `modified-at` timestamp on the `<reference>` element.

```bash
git add .claude/context/plans.xml
git commit -m "chore(context/plans): close diagnostics-engine-core plan"
```

---

## Self-Review Checklist (run before handoff)

**Spec coverage:** §3 reference material is informational (no task). §4 library reconnaissance is informational (no task). §5.1 → Task 7. §5.2 → Task 2. §5.3 → Task 3 (loader namespace + file layout). §5.4 → Task 3 (dedupe). §5.5 → Task 5 (audit log shape). §5.6 → Task 6 (override). §6.1 → reflected in task ordering (1, 2, 3, 4, 5, 6, 7). §6.2 → Task 1. §6.3 → Task 2. §6.4 → Task 3. §6.5 → Task 4. §6.6 → Task 5. §6.7 → Task 6. §7 open seams → noted in code comments + Task 3 Refactor. §8 testing layout → matches conftest + 6 test files. §9 file layout → matches Task 7 surface. §10 deps → Task 0. §11 audit log persistence → consumed by Tasks 5 + 6 (FirmConfig already provides the surface). §14.1 plan boundaries → enforced (cycles 7-9 absent). §14.4 Red period → Option A documented in plan header + Task 1 + Task 7. **No gaps.**

**Placeholder scan:** No "TBD", no "implement later", no "similar to Task N", no "add appropriate error handling." Every code block is complete.

**Type consistency:** `DiagnosticRule` fields used identically in Tasks 3, 4. `AuditRecord` fields used identically in Tasks 5, 6. `force_generation` signature matches between Task 6 implementation and Task 7 import.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-04-23-diagnostics-engine-core.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — A fresh subagent per task, two-stage review between tasks, fast iteration. Good fit because each cycle's tests are self-contained and reviewable in isolation.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints. Good fit if you want to walk through each cycle interactively.

**Which approach?**
