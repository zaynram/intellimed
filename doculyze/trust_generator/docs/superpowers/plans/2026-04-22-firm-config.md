# TGv3 `firm_config` Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the TGv3 `firm_config` module: a TOML-backed, Pydantic-validated firm configuration loader with an editor-facing JSON Schema generator and a one-time v2→v3 config migration, per the Finalized spec at `docs/superpowers/specs/2026-04-21-firm-config-design.md`.

**Architecture:** `src/trust_generator/v3/config/firm.py` exposes `FirmConfig` (a `pydantic_settings.BaseSettings` composed of eight nested `BaseModel` sections) and a single public loader `load_firm_config(path: Path | None = None) -> FirmConfig`. Precedence is explicit kwargs → `TGV3_*` env vars → TOML file → Pydantic defaults, pinned via `settings_customise_sources`. A companion script `scripts/generate_firm_config_schema.py` emits `config/firm-config.schema.json` (JSON Schema draft-2020-12 + `x-tombi-*` root extensions) derived from `FirmConfig.model_json_schema(...)`, and a pytest test asserts byte-equality against the on-disk artifact as drift protection.

**Tech Stack:** Python 3.12+, Pydantic v2, `pydantic-settings >=2.14,<3` (new runtime dep), stdlib `tomllib`, `jsonschema >=4,<5` (new dev dep for round-trip test). pixi-as-primary for dependency management.

**Spec amendments in force (all under §Post-finalization amendments in the spec):**

- **A-1** — `firm.office_address` imports the existing `Address` model from `trust_generator.v3.schema` as-is. TOML key is `zip_code` (not `zip`); lat/lon are `float | None` (not `SchemaNumber`/`Decimal`). No `SchemaNumber` alias is introduced. The `SchemaNumber` coercion test in §10.2 is rewritten to assert native `float` → `{"type": "number"}` emission.
- **A-2** — §10.3 integration tests assert the config-surface contract (loaded `FirmConfig` exposes the values consumers will read) rather than wiring consumer subsystems that don't yet exist in v3. Task 11 carries a scoped grep step as a clean-slate check.
- **A-3** — The loader reads TOML via stdlib `tomllib` and passes the payload as init-kwargs to `FirmConfig(**toml_data)`, rather than via `TomlConfigSettingsSource`. `settings_customise_sources` still pins env > TOML > defaults; only the TOML-routing mechanism differs from spec §7's illustrative internal-shape note.

**Operational note on `pixi run test`:** the task at `pixi.toml:59-62` has `cwd = 'tests/'`, so every `pixi run test <target>` in this plan uses a `target` that is **relative to `tests/`** (e.g., `v3/config`, NOT `tests/v3/config`). Getting this wrong silently miscollects zero tests. All invocations below follow the correct form.

---

## File Structure

**New files under `src/trust_generator/v3/config/`:**

- `__init__.py` — re-exports `FirmConfig`, `load_firm_config`, `FirmConfigError`, and each nested section model so callers can `from trust_generator.v3.config import FirmConfig`.
- `firm.py` — all nested Pydantic models, the `FirmConfig` settings class, the `load_firm_config` loader, the `FirmConfigError` exception, and `DEFAULT_CONFIG_PATH` / `ENV_VAR_CONFIG_PATH` / `ENV_PREFIX` constants.
- `schema_gen.py` — `TombiAwareGenerator` subclass of `pydantic.json_schema.GenerateJsonSchema`, which injects root-level `x-tombi-*` extensions and is the single source of JSON Schema emission.

**New files under `scripts/`:**

- `generate_firm_config_schema.py` — CLI entry point that imports `FirmConfig` + `TombiAwareGenerator`, emits pretty-printed JSON with deterministic key sort, and writes to `config/firm-config.schema.json`.

**New test files under `tests/v3/`:**

- `config/__init__.py` — empty package marker.
- `config/test_firm.py` — covers §10.1 loader unit tests (discovery order, defaults, required-field failure, cross-field validation, env overlay, path resolution, strict-extra semantics, meta permissiveness).
- `config/test_firm_schema.py` — covers §10.2 schema-generation tests (dialect, tombi extensions, property coverage, URL format, meta permissiveness, freshness byte-equality, jsonschema round-trip).
- `integration/__init__.py` — empty package marker (may already exist; create if missing).
- `integration/test_config_integration.py` — covers §10.3: trustee_catalog and diagnostics consumers read from loaded `FirmConfig`.

**New / modified config files:**

- Create `config/firm.toml` — v3-shape firm configuration, migrated from `config/firm.v2.toml` per §9; includes the `#:schema ./firm-config.schema.json` directive at the top.
- Create `config/firm-config.schema.json` — generated JSON Schema artifact checked into the repo.
- Modify `pixi.toml` — add `pydantic-settings >=2.14,<3` under `[pypi-dependencies]` + `[package.run-dependencies]`; add `jsonschema >=4,<5` under `[feature.dev.dependencies]`.
- Modify `README.md` — add a firm_config section covering env-var convention, schema regeneration command, and file location.

**Files explicitly NOT modified:**

- `src/trust_generator/v3/schema.py` (spec §2 hard out-of-scope boundary; reinforced by amendment A-1).
- `config/firm.v2.toml` (preserved as historical reference).
- Any v2 source under `src/trust_generator/` outside `v3/`.

---

## Task 1: Stub for importability

**Why first:** per spec §12 step 1 and the TDD ordering. The stubs exist only so the failing tests in Task 2 can import without raising at collection time.

**Files:**
- Create: `src/trust_generator/v3/config/__init__.py`
- Create: `src/trust_generator/v3/config/firm.py`

- [ ] **Step 1: Create the package `__init__.py`**

Create `src/trust_generator/v3/config/__init__.py`:

```python
"""TGv3 firm configuration package.

Exposes the canonical ``FirmConfig`` settings object and its ``load_firm_config``
loader. The loader is the only public entry point; construct ``FirmConfig``
directly only in tests.
"""

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
    "TrusteeCatalog",
    "load_firm_config",
]
```

- [ ] **Step 2: Create the stub `firm.py`**

Create `src/trust_generator/v3/config/firm.py`:

```python
"""TGv3 firm configuration loader and models (stub — Task 1).

This stub exists to make the package importable while tests are authored
against the intended surface. Real implementations land in Tasks 4 and 5.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict

DEFAULT_CONFIG_PATH: Final[Path] = Path("config/firm.toml")
ENV_VAR_CONFIG_PATH: Final[str] = "TGV3_FIRM_CONFIG"
ENV_PREFIX: Final[str] = "TGV3_"


class FirmConfigError(Exception):
    """Raised when firm_config cannot be loaded or fails validation."""


class Meta(BaseModel):
    model_config = ConfigDict(extra="allow")


class FirmIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Jurisdiction(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EstateThresholds(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TrusteeCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Diagnostics(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Guardianship(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Drafts(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FirmConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meta: Meta = Meta()


def load_firm_config(path: Path | None = None) -> FirmConfig:  # noqa: ARG001
    raise NotImplementedError("Implemented in Task 5.")
```

> Note: `FirmConfig` temporarily subclasses `BaseModel` (not `BaseSettings`) because `pydantic-settings` has not yet been added as a dep. Task 3 adds the dep; Task 4 switches the base class.

- [ ] **Step 3: Verify import works**

Run: `pixi run python -c "from trust_generator.v3.config import FirmConfig, load_firm_config, FirmConfigError; print('ok')"`
Expected: prints `ok` with no traceback.

- [ ] **Step 4: Commit**

```bash
git add src/trust_generator/v3/config/__init__.py src/trust_generator/v3/config/firm.py
git commit -m "feat(v3/config): stub firm_config package for tdd-first authoring"
```

---

## Task 2: Author the failing loader and integration tests

**Why second:** spec §12 step 2 and §10 acceptance criteria declare these tests as the implementation acceptance contract, authored against stubs before any real logic lands. They must fail at the end of this task.

**Files:**
- Create: `tests/v3/config/__init__.py`
- Create: `tests/v3/config/test_firm.py`
- Create: `tests/v3/integration/__init__.py` (if missing)
- Create: `tests/v3/integration/test_config_integration.py`

- [ ] **Step 1: Create test package markers**

Create `tests/v3/config/__init__.py` (empty file).

Create `tests/v3/integration/__init__.py` if `ls tests/v3/integration/` does not already show it (empty file).

- [ ] **Step 2: Write `tests/v3/config/test_firm.py`**

Create `tests/v3/config/test_firm.py`:

```python
"""Loader unit tests for trust_generator.v3.config.firm (spec §10.1)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from trust_generator.v3.config import (
    DEFAULT_CONFIG_PATH,
    ENV_PREFIX,
    ENV_VAR_CONFIG_PATH,
    FirmConfig,
    FirmConfigError,
    load_firm_config,
)


WELL_FORMED = """
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
"""


MINIMAL = """
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


def _write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith(ENV_PREFIX):
            monkeypatch.delenv(key, raising=False)


def test_constants_match_spec() -> None:
    assert DEFAULT_CONFIG_PATH == Path("config/firm.toml")
    assert ENV_VAR_CONFIG_PATH == "TGV3_FIRM_CONFIG"
    assert ENV_PREFIX == "TGV3_"


def test_happy_path_loads_expected_values(tmp_path: Path) -> None:
    path = _write(tmp_path / "firm.toml", WELL_FORMED)
    cfg = load_firm_config(path)
    assert isinstance(cfg, FirmConfig)
    assert cfg.firm.name == "Test Firm LLP"
    assert cfg.firm.phone == "(555) 555-5555"
    assert cfg.firm.office_address.zip_code == "61114"
    assert cfg.jurisdiction.default_state == "Illinois"


def test_minimal_file_yields_section_defaults(tmp_path: Path) -> None:
    path = _write(tmp_path / "firm.toml", MINIMAL)
    cfg = load_firm_config(path)
    assert cfg.estate_thresholds.single_soft == 3_000_000
    assert cfg.estate_thresholds.joint_soft == 6_000_000
    assert cfg.estate_thresholds.single_hard == 4_000_000
    assert cfg.estate_thresholds.joint_hard == 8_000_000
    assert cfg.estate_thresholds.approaching_cliff_ratio == pytest.approx(0.90)
    assert cfg.trustee_catalog.radius_miles == 100
    assert cfg.trustee_catalog.refresh_days == 30
    assert cfg.trustee_catalog.fdic_request_timeout_s == 30
    assert cfg.diagnostics.default_restriction_level == "error"
    assert cfg.diagnostics.allow_force_generation is True
    assert cfg.diagnostics.audit_log_rotation == "monthly"
    assert cfg.guardianship.default_policy == "EXPLICIT_DESIGNATIONS"
    assert cfg.drafts.auto_purge_days == 90
    assert cfg.meta.schema_version is None
    assert cfg.meta.comment is None


def test_missing_required_firm_name_raises(tmp_path: Path) -> None:
    broken = WELL_FORMED.replace('name = "Test Firm LLP"\n', "")
    path = _write(tmp_path / "firm.toml", broken)
    with pytest.raises(FirmConfigError) as exc:
        load_firm_config(path)
    assert "name" in str(exc.value)


def test_cross_field_hard_less_than_soft_raises(tmp_path: Path) -> None:
    bad = WELL_FORMED + """
[estate_thresholds]
single_soft = 5_000_000
single_hard = 4_000_000
joint_soft = 6_000_000
joint_hard = 8_000_000
approaching_cliff_ratio = 0.9
"""
    path = _write(tmp_path / "firm.toml", bad)
    with pytest.raises(FirmConfigError):
        load_firm_config(path)


def test_env_overlay_overrides_toml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write(tmp_path / "firm.toml", WELL_FORMED)
    monkeypatch.setenv("TGV3_ESTATE_THRESHOLDS__SINGLE_HARD", "5000000")
    cfg = load_firm_config(path)
    assert cfg.estate_thresholds.single_hard == 5_000_000


def test_relative_paths_resolve_against_config_parent(tmp_path: Path) -> None:
    body = WELL_FORMED + """
[diagnostics]
audit_log_dir = "./relative/audit"
rules_dir = "./relative/rules"
"""
    cfg_dir = tmp_path / "nested"
    cfg_dir.mkdir()
    path = _write(cfg_dir / "firm.toml", body)
    cfg = load_firm_config(path)
    assert cfg.diagnostics.audit_log_dir.is_absolute()
    assert cfg.diagnostics.audit_log_dir == (cfg_dir / "relative" / "audit").resolve()
    assert cfg.diagnostics.rules_dir == (cfg_dir / "relative" / "rules").resolve()


def test_absolute_paths_preserved(tmp_path: Path) -> None:
    abs_audit = tmp_path / "abs_audit"
    body = WELL_FORMED + f"""
[diagnostics]
audit_log_dir = "{abs_audit.as_posix()}"
"""
    path = _write(tmp_path / "firm.toml", body)
    cfg = load_firm_config(path)
    assert cfg.diagnostics.audit_log_dir == abs_audit.resolve()


def test_strict_extra_outside_meta_rejects_unknown_key(tmp_path: Path) -> None:
    # Inject the unknown key INSIDE the existing [firm] table to exercise
    # pydantic's extra="forbid". Appending a second [firm] header would raise
    # tomllib.TOMLDecodeError (duplicate table), which reaches the same
    # FirmConfigError wrapper but via the wrong failure mode.
    bad = WELL_FORMED.replace(
        'phone = "(555) 555-5555"',
        'phone = "(555) 555-5555"\nmystery_extra = "nope"',
    )
    path = _write(tmp_path / "firm.toml", bad)
    with pytest.raises(FirmConfigError) as exc:
        load_firm_config(path)
    # Sanity-check: the error names the offending key, proving it came from
    # extra="forbid" rather than a TOML parse failure.
    assert "mystery_extra" in str(exc.value)


def test_meta_accepts_unknown_keys(tmp_path: Path) -> None:
    body = WELL_FORMED + """
[meta]
schema_version = "1.0"
comment = "firm notes"
custom_key = "future forward-compat payload"
"""
    path = _write(tmp_path / "firm.toml", body)
    cfg = load_firm_config(path)
    assert cfg.meta.schema_version == "1.0"
    assert cfg.meta.comment == "firm notes"
    assert cfg.meta.model_extra is not None
    assert cfg.meta.model_extra["custom_key"] == "future forward-compat payload"


def test_discovery_explicit_path_wins_over_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    explicit = _write(tmp_path / "explicit.toml", WELL_FORMED)
    other_body = WELL_FORMED.replace("Test Firm LLP", "EnvVar Firm LLP")
    via_env = _write(tmp_path / "via_env.toml", other_body)
    monkeypatch.setenv("TGV3_FIRM_CONFIG", str(via_env))
    cfg = load_firm_config(explicit)
    assert cfg.firm.name == "Test Firm LLP"


def test_discovery_env_wins_over_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write(tmp_path / "via_env.toml", WELL_FORMED)
    monkeypatch.setenv("TGV3_FIRM_CONFIG", str(path))
    cfg = load_firm_config(None)
    assert cfg.firm.name == "Test Firm LLP"


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FirmConfigError):
        load_firm_config(tmp_path / "does_not_exist.toml")


def test_approaching_cliff_ratio_bounds(tmp_path: Path) -> None:
    bad_body = WELL_FORMED + """
[estate_thresholds]
single_soft = 3_000_000
single_hard = 4_000_000
joint_soft = 6_000_000
joint_hard = 8_000_000
approaching_cliff_ratio = 1.2
"""
    path = _write(tmp_path / "firm.toml", bad_body)
    with pytest.raises(FirmConfigError):
        load_firm_config(path)


def test_fdic_api_base_must_be_http_url(tmp_path: Path) -> None:
    bad = WELL_FORMED + """
[trustee_catalog]
fdic_api_base = "not-a-url"
"""
    path = _write(tmp_path / "firm.toml", bad)
    with pytest.raises(FirmConfigError):
        load_firm_config(path)
```

- [ ] **Step 3: Write `tests/v3/integration/test_config_integration.py`**

Create `tests/v3/integration/test_config_integration.py`:

```python
"""Integration tests: downstream subsystems read from FirmConfig (spec §10.3)."""

from __future__ import annotations

from pathlib import Path

from trust_generator.v3.config import load_firm_config


BODY = """
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


def test_trustee_catalog_consumer_reads_from_config(tmp_path: Path) -> None:
    (tmp_path / "firm.toml").write_text(BODY, encoding="utf-8")
    cfg = load_firm_config(tmp_path / "firm.toml")
    assert str(cfg.trustee_catalog.fdic_api_base).startswith("https://example.test/")
    assert cfg.trustee_catalog.fdic_request_timeout_s == 45


def test_diagnostics_consumer_reads_default_restriction_level(tmp_path: Path) -> None:
    (tmp_path / "firm.toml").write_text(BODY, encoding="utf-8")
    cfg = load_firm_config(tmp_path / "firm.toml")
    assert cfg.diagnostics.default_restriction_level == "warning"
```

> Rationale: §10.3 calls for the refresh client and diagnostics subsystems to consume the loaded config. Those subsystems do not yet exist in the repo (spec §2 flags them as "deferred"). The integration tests therefore assert the config-surface contract: that a loaded `FirmConfig` exposes the values those consumers will read. When the consumers land, they swap their constants for `cfg.trustee_catalog.*` / `cfg.diagnostics.*` and the tests grow assertions on consumer behavior. This is the minimum that honors §10.3 today without fabricating consumer code outside this plan's scope.

- [ ] **Step 4: Run tests to verify they fail**

Run: `pixi run test v3/config`
Then: `pixi run test v3/integration`
Expected: All of the tests above fail. Most fail with `NotImplementedError` from `load_firm_config`; `test_constants_match_spec` passes. Failures are by design at this step.

> The `target` arg is relative to the `pixi run test` task's `cwd = 'tests/'` (see operational note above). Do **not** use `tests/v3/...` — that would resolve to `tests/tests/v3/...` and silently collect zero tests.

- [ ] **Step 5: Commit**

```bash
git add tests/v3/config tests/v3/integration/__init__.py tests/v3/integration/test_config_integration.py
git commit -m "test(v3/config): author failing loader + integration suites against stubs"
```

---

## Task 3: Add `pydantic-settings` as a runtime dependency

**Why third:** `FirmConfig` must subclass `pydantic_settings.BaseSettings`, which requires the package before Task 4's model implementation can run.

**Files:**
- Modify: `pixi.toml` (add `pydantic-settings` in two places)

- [ ] **Step 1: Add to `[pypi-dependencies]`**

Open `pixi.toml`. Under `[pypi-dependencies]`, add the line:

```toml
pydantic-settings = '>=2.14,<3'
```

The block should now read:

```toml
[pypi-dependencies]
    trust-generator   = { path = '.', editable = true }
    reportlab         = '*'
    pypdf             = '>=4'
    types-reportlab   = '>=4.4.10.20260408, <5'
    pydantic-settings = '>=2.14,<3'
```

- [ ] **Step 2: Add to `[package.run-dependencies]`**

Under `[package.run-dependencies]`, add:

```toml
pydantic-settings = '>=2.14,<3'
```

The block should now read:

```toml
[package.run-dependencies]
    pydantic          = '>=2'
    python-docx       = '*'
    reportlab         = '*'
    pypdf             = '>=4'
    pydantic-settings = '>=2.14,<3'
```

- [ ] **Step 3: Install and verify**

Run: `pixi install`
Expected: resolves successfully, downloads `pydantic-settings` 2.14.x.

Run: `pixi run python -c "from pydantic_settings import BaseSettings, SettingsConfigDict, TomlConfigSettingsSource; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 4: Commit**

```bash
git add pixi.toml pixi.lock
git commit -m "build: add pydantic-settings >=2.14 as a runtime dependency"
```

---

## Task 4: Implement the nested Pydantic models

**Why fourth:** spec §12 step 4. All field-shape and field-validator tests from Task 2 drive this work.

**Files:**
- Modify: `src/trust_generator/v3/config/firm.py` (replace stubs with real models; keep `FirmConfig` shell so Task 5 can wire the loader)

- [ ] **Step 1: Write the real model definitions**

Replace the body of `src/trust_generator/v3/config/firm.py` with:

```python
"""TGv3 firm configuration models and loader.

Public surface (see ``__init__.py`` for re-exports):

* ``FirmConfig``       — the full typed configuration, composed of nested sections.
* ``load_firm_config`` — the single public loader entry point.
* ``FirmConfigError``  — raised on discovery, parse, or validation failure.

Construct ``FirmConfig`` directly only in tests. Production code uses the loader.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

from trust_generator.v3.schema import Address

DEFAULT_CONFIG_PATH: Final[Path] = Path("config/firm.toml")
ENV_VAR_CONFIG_PATH: Final[str] = "TGV3_FIRM_CONFIG"
ENV_PREFIX: Final[str] = "TGV3_"


class FirmConfigError(Exception):
    """Raised when firm_config cannot be loaded or fails validation.

    The message quotes the originating pydantic / tomllib error for diagnostics.
    """


class Meta(BaseModel):
    """Forward-compatibility seam (spec §5.8).

    Uses ``extra='allow'`` so future v3.x additions or firm-side annotations
    under ``[meta]`` never trigger validation errors. Every other section in
    ``FirmConfig`` remains ``extra='forbid'`` to catch typos.
    """

    model_config = ConfigDict(extra="allow")

    schema_version: str | None = None
    comment: str | None = None


class FirmIdentity(BaseModel):
    """Firm identity and office location (spec §5.1).

    ``office_address`` reuses the v3 ``Address`` model as-is per amendment A-1.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    phone: str = Field(min_length=1)
    office_address: Address


class Jurisdiction(BaseModel):
    """Legal/jurisdictional defaults (spec §5.2)."""

    model_config = ConfigDict(extra="forbid")

    default_state: str = "Illinois"
    default_county: str = "Winnebago"
    trust_code_citation: str = "Illinois Trust Code (760 ILCS 3/101, et seq.)"


class EstateThresholds(BaseModel):
    """IL estate-tax cliff parameters (spec §5.3).

    Illinois taxes the entire excess above threshold (cliff). The soft
    thresholds gate detail-collection prompts; the hard thresholds drive the
    blocking diagnostic; ``approaching_cliff_ratio`` sets the near-cliff warning.
    """

    model_config = ConfigDict(extra="forbid")

    single_soft: int = Field(default=3_000_000, gt=0)
    joint_soft: int = Field(default=6_000_000, gt=0)
    single_hard: int = Field(default=4_000_000, gt=0)
    joint_hard: int = Field(default=8_000_000, gt=0)
    approaching_cliff_ratio: float = Field(default=0.90, gt=0, lt=1)

    @model_validator(mode="after")
    def _validate_threshold_ordering(self) -> "EstateThresholds":
        if self.single_soft >= self.single_hard:
            raise ValueError(
                "estate_thresholds.single_soft must be strictly less than single_hard"
            )
        if self.joint_soft >= self.joint_hard:
            raise ValueError(
                "estate_thresholds.joint_soft must be strictly less than joint_hard"
            )
        if self.single_soft > self.joint_soft:
            raise ValueError(
                "estate_thresholds.single_soft must be <= joint_soft"
            )
        if self.single_hard > self.joint_hard:
            raise ValueError(
                "estate_thresholds.single_hard must be <= joint_hard"
            )
        return self


class TrusteeCatalog(BaseModel):
    """Corporate trustee catalog (spec §5.4).

    ``db_path``, ``audit_log_dir``, and similar paths are resolved to absolute
    paths by the loader against the config file's parent directory. Relative
    paths here are pre-resolution placeholders.
    """

    model_config = ConfigDict(extra="forbid")

    db_path: Path = Path("./data/trustee_catalog.sqlite")
    radius_miles: int = Field(default=100, gt=0)
    refresh_days: int = Field(default=30, gt=0)
    fdic_api_base: HttpUrl = "https://banks.data.fdic.gov/api"  # type: ignore[assignment]
    fdic_request_timeout_s: int = Field(default=30, gt=0)


class Diagnostics(BaseModel):
    """Diagnostic enforcement (spec §5.5)."""

    model_config = ConfigDict(extra="forbid")

    default_restriction_level: Literal["info", "warning", "error"] = "error"
    allow_force_generation: bool = True
    audit_log_dir: Path = Path("./logs/audit")
    audit_log_rotation: Literal["monthly", "weekly", "daily"] = "monthly"
    rules_dir: Path = Path("./config/rules")


class Guardianship(BaseModel):
    """Guardianship policy default (spec §5.6)."""

    model_config = ConfigDict(extra="forbid")

    default_policy: Literal["DELEGATE_TO_TRUSTEES", "EXPLICIT_DESIGNATIONS"] = (
        "EXPLICIT_DESIGNATIONS"
    )


class Drafts(BaseModel):
    """Preserved from v2 (spec §5.7)."""

    model_config = ConfigDict(extra="forbid")

    auto_purge_days: int = Field(default=90, gt=0)


class FirmConfig(BaseSettings):
    """Full typed firm configuration, composed of nested sections.

    See ``load_firm_config`` for loader semantics. Do not construct directly
    outside tests.
    """

    model_config = SettingsConfigDict(
        env_prefix=ENV_PREFIX,
        env_nested_delimiter="__",
        extra="forbid",
    )

    meta: Meta = Field(default_factory=Meta)
    firm: FirmIdentity
    jurisdiction: Jurisdiction = Field(default_factory=Jurisdiction)
    estate_thresholds: EstateThresholds = Field(default_factory=EstateThresholds)
    trustee_catalog: TrusteeCatalog = Field(default_factory=TrusteeCatalog)
    diagnostics: Diagnostics = Field(default_factory=Diagnostics)
    guardianship: Guardianship = Field(default_factory=Guardianship)
    drafts: Drafts = Field(default_factory=Drafts)


def load_firm_config(path: Path | None = None) -> FirmConfig:  # noqa: ARG001
    raise NotImplementedError("Implemented in Task 5.")
```

- [ ] **Step 2: Run lint + typecheck**

Run: `pixi run lint src/trust_generator/v3/config/`
Expected: no violations.

Run: `pixi run mypy v3/config`
Expected: no type errors.

- [ ] **Step 3: Run the model-shape portion of Task 2's tests**

Run: `pixi run test v3/config/test_firm.py::test_minimal_file_yields_section_defaults`
Expected: still fails with `NotImplementedError` (loader isn't wired yet). That's fine — Task 5 flips it green.

Instead, run a direct construction smoke test to confirm the models are sound:

```bash
pixi run python -c "
from trust_generator.v3.config import FirmConfig, FirmIdentity
from trust_generator.v3.schema import Address
cfg = FirmConfig(firm=FirmIdentity(name='X', phone='Y', office_address=Address(street='1 Main', city='C', state='IL', zip_code='61114')))
print(cfg.estate_thresholds.single_hard)
print(cfg.diagnostics.default_restriction_level)
print(cfg.guardianship.default_policy)
"
```

Expected output:
```
4000000
error
EXPLICIT_DESIGNATIONS
```

- [ ] **Step 4: Commit**

```bash
git add src/trust_generator/v3/config/firm.py
git commit -m "feat(v3/config): define nested FirmConfig section models + validators"
```

---

## Task 5: Implement `load_firm_config`

**Why fifth:** spec §12 step 5. Closes the loader acceptance criteria (§10.1).

**Files:**
- Modify: `src/trust_generator/v3/config/firm.py` (replace the `NotImplementedError` loader with the real implementation)

- [ ] **Step 1: Implement the loader**

In `src/trust_generator/v3/config/firm.py`, replace the stub `load_firm_config` at the bottom of the file with the implementation below. Also update the top-of-file imports to add `os`, `tomllib`, and `ValidationError`:

Add to imports (top of file):

```python
import os
import tomllib
from pydantic import ValidationError
```

Replace the stub loader:

```python
def _discover_path(path: Path | None) -> Path:
    if path is not None:
        return Path(path)
    env_value = os.environ.get(ENV_VAR_CONFIG_PATH)
    if env_value:
        return Path(env_value)
    return DEFAULT_CONFIG_PATH


def _resolve_paths(cfg: FirmConfig, anchor: Path) -> FirmConfig:
    def _resolve(p: Path) -> Path:
        return p if p.is_absolute() else (anchor / p).resolve()

    cfg.trustee_catalog.db_path = _resolve(cfg.trustee_catalog.db_path)
    cfg.diagnostics.audit_log_dir = _resolve(cfg.diagnostics.audit_log_dir)
    cfg.diagnostics.rules_dir = _resolve(cfg.diagnostics.rules_dir)
    return cfg


def load_firm_config(path: Path | None = None) -> FirmConfig:
    """Load, validate, and return the firm configuration.

    Discovery order for the TOML file:

    1. ``path`` argument, if provided.
    2. ``$TGV3_FIRM_CONFIG`` environment variable, if set.
    3. ``./config/firm.toml`` relative to CWD.

    Precedence for conflicting values (highest first):

    1. Environment variables prefixed ``TGV3_`` (nested delimiter ``__``).
    2. TOML file contents.
    3. Pydantic field defaults.

    Relative paths inside the loaded config (``audit_log_dir``, ``rules_dir``,
    ``db_path``) are rewritten to absolute paths, anchored at the config file's
    parent directory.

    Raises:
        FirmConfigError: on missing file, TOML parse error, or validation error.
            The exception's message quotes the originating error.
    """
    resolved = _discover_path(path)
    if not resolved.is_file():
        raise FirmConfigError(
            f"firm_config file not found at {resolved!s}. "
            f"Set {ENV_VAR_CONFIG_PATH} or pass an explicit path."
        )

    try:
        with resolved.open("rb") as handle:
            toml_data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise FirmConfigError(
            f"firm_config TOML parse error in {resolved!s}: {exc}"
        ) from exc

    try:
        cfg = FirmConfig(**toml_data)
    except ValidationError as exc:
        raise FirmConfigError(
            f"firm_config validation failed for {resolved!s}:\n{exc}"
        ) from exc

    return _resolve_paths(cfg, resolved.parent)
```

> **Note on env overlay.** `BaseSettings` automatically reads `TGV3_*` env vars into the settings instance on construction. The `FirmConfig(**toml_data)` call merges TOML payload (passed as init kwargs) with env-var sources; pydantic-settings' default precedence puts init kwargs above env vars, which contradicts the spec's stated precedence (env above TOML). **This must be pinned** — proceed to Step 2.

- [ ] **Step 2: Pin source precedence via `settings_customise_sources`**

In the `FirmConfig` class definition, add the classmethod below as the last method (after `model_config` and the field declarations):

```python
    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type["FirmConfig"],
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        return (env_settings, init_settings, file_secret_settings)
```

This pins env vars above init-kwargs (the TOML payload), matching the spec §7 precedence: env > TOML > defaults. Explicit kwargs passed to `FirmConfig(...)` in tests are the init path, which here sits below env for consistency with the documented model. Tests that need to override env-controlled fields set `monkeypatch.delenv(...)` first (already handled by `_clean_env` in the test suite).

- [ ] **Step 3: Run the full loader test file**

Run: `pixi run test v3/config/test_firm.py`
Expected: all tests pass. If any fail, iterate on the model/loader code until green.

Run: `pixi run test v3/integration/test_config_integration.py`
Expected: both integration tests pass.

- [ ] **Step 4: Run the project's quality gates**

The `lint` task takes a single `include` arg (default `'src/ tests/'`), so multi-path invocations must be passed as one quoted token.

Run: `pixi run lint "src/trust_generator/v3/config/ tests/v3/config/ tests/v3/integration/"`
Expected: no violations.

Run: `pixi run mypy v3/config`
Expected: no type errors.

- [ ] **Step 5: Commit**

```bash
git add src/trust_generator/v3/config/firm.py
git commit -m "feat(v3/config): implement load_firm_config with env/TOML/default precedence"
```

---

## Task 6: Migrate `config/firm.v2.toml` to `config/firm.toml`

**Why sixth:** spec §12 step 6 and §9 migration mapping. Integration tests in Task 11 and tombi in-editor validation both depend on this file existing in v3 shape.

**Files:**
- Create: `config/firm.toml`
- Preserve: `config/firm.v2.toml` (no edits; retained for historical reference)

- [ ] **Step 1: Author the v3 firm.toml**

Create `config/firm.toml` with exactly this content:

```toml
#:schema ./firm-config.schema.json
# Trust Generator v3 — Firm Configuration
# Hand-editable. Reloaded on application start.
#
# See docs/superpowers/specs/2026-04-21-firm-config-design.md for the canonical
# key reference. Env-var overlay: TGV3_<SECTION>__<KEY> (double underscore as
# nested delimiter). Example: TGV3_ESTATE_THRESHOLDS__SINGLE_HARD=5000000.

[meta]
# schema_version and comment are optional.
# Additional keys under [meta] are permitted (forward-compat seam).

[firm]
name  = "Crosby and Crosby LLP"
phone = "(815) 367-6432"

  [firm.office_address]
  street   = "3815 N Mulford Rd. 4"
  city     = "Rockford"
  state    = "IL"
  zip_code = "61114"
  # country defaults to "US"; latitude/longitude resolved on demand.

[jurisdiction]
default_state       = "Illinois"
default_county      = "Winnebago"
trust_code_citation = "Illinois Trust Code (760 ILCS 3/101, et seq.)"

[estate_thresholds]
single_soft              = 3_000_000
joint_soft               = 6_000_000
single_hard              = 4_000_000
joint_hard               = 8_000_000
approaching_cliff_ratio  = 0.90

[trustee_catalog]
db_path       = "./data/trustee_catalog.sqlite"
radius_miles  = 100
refresh_days  = 30
fdic_api_base = "https://banks.data.fdic.gov/api"

[diagnostics]
default_restriction_level = "error"
allow_force_generation    = true
audit_log_dir             = "./logs/audit"
audit_log_rotation        = "monthly"
rules_dir                 = "./config/rules"

[guardianship]
default_policy = "EXPLICIT_DESIGNATIONS"

[drafts]
auto_purge_days = 90
```

> **Migration notes per spec §9:**
>
> - v2's `firm.address_line1` ("3815 N Mulford Rd. 4") → `firm.office_address.street`.
> - v2's `firm.address_line2` ("Rockford, IL 61114") is manually split into `city`, `state`, `zip_code`.
> - All other v2 keys are preserved byte-for-byte in their new sections.
> - TOML key is `zip_code` (not `zip`) per amendment A-1.

- [ ] **Step 2: Verify the new file loads**

Run:

```bash
pixi run python -c "
from trust_generator.v3.config import load_firm_config
cfg = load_firm_config('config/firm.toml')
print(cfg.firm.name)
print(cfg.firm.office_address.zip_code)
print(cfg.estate_thresholds.single_hard)
"
```

Expected output:
```
Crosby and Crosby LLP
61114
4000000
```

- [ ] **Step 3: Commit**

```bash
git add config/firm.toml
git commit -m "feat(config): migrate firm.v2.toml to v3 shape at config/firm.toml"
```

---

## Task 7: Add `jsonschema` as a dev dependency

**Why seventh:** spec §12 step 7. Required by the round-trip validation test in Task 8.

**Files:**
- Modify: `pixi.toml` under `[feature.dev.dependencies]`

- [ ] **Step 1: Add the dev dep**

Open `pixi.toml`. Under `[feature.dev.dependencies]`, add:

```toml
jsonschema = '>=4,<5'
```

The block should now read:

```toml
[feature.dev.dependencies]
    pyinstaller = '*'
    pytest      = '*'
    ruff        = '*'
    mypy        = '*'
    jsonschema  = '>=4,<5'
```

- [ ] **Step 2: Install and verify**

Run: `pixi install`
Expected: resolves successfully, downloads `jsonschema` 4.x.

Run: `pixi run python -c "import jsonschema; print(jsonschema.__version__)"`
Expected: prints `4.x.x`.

- [ ] **Step 3: Commit**

```bash
git add pixi.toml pixi.lock
git commit -m "build: add jsonschema >=4 as a dev dependency for schema round-trip test"
```

---

## Task 8: Author the failing schema-generation tests

**Why eighth:** spec §12 step 8. Declares the acceptance contract for the generator before any generator code exists.

**Files:**
- Create: `tests/v3/config/test_firm_schema.py`
- Create: `scripts/generate_firm_config_schema.py` (stub raising `NotImplementedError`)

- [ ] **Step 1: Stub the generator script**

Create `scripts/generate_firm_config_schema.py`:

```python
"""Generate config/firm-config.schema.json from FirmConfig (Tasks 9-10).

Stub — raises NotImplementedError until Task 9 lands.
"""

from __future__ import annotations


def main() -> int:
    raise NotImplementedError("Implemented in Task 9.")


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Write the schema tests**

Create `tests/v3/config/test_firm_schema.py`:

```python
"""Schema-generation tests for firm_config (spec §10.2)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import jsonschema
import pytest

from trust_generator.v3.config import FirmConfig
from trust_generator.v3.config.firm import (
    Diagnostics,
    Drafts,
    EstateThresholds,
    FirmIdentity,
    Guardianship,
    Jurisdiction,
    Meta,
    TrusteeCatalog,
)
from trust_generator.v3.config.schema_gen import TombiAwareGenerator
from trust_generator.v3.schema import Address


REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = REPO_ROOT / "config" / "firm-config.schema.json"
GENERATOR_SCRIPT = REPO_ROOT / "scripts" / "generate_firm_config_schema.py"


def _load_generator_main():
    spec = importlib.util.spec_from_file_location(
        "generate_firm_config_schema", GENERATOR_SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _emit_schema() -> dict:
    return FirmConfig.model_json_schema(schema_generator=TombiAwareGenerator)


def _canonical_firm_config() -> FirmConfig:
    return FirmConfig(
        meta=Meta(),
        firm=FirmIdentity(
            name="Canon LLP",
            phone="(555) 555-5555",
            office_address=Address(
                street="1 Main",
                city="Rockford",
                state="IL",
                zip_code="61114",
            ),
        ),
        jurisdiction=Jurisdiction(),
        estate_thresholds=EstateThresholds(),
        trustee_catalog=TrusteeCatalog(),
        diagnostics=Diagnostics(),
        guardianship=Guardianship(),
        drafts=Drafts(),
    )


def test_generator_runs_without_error() -> None:
    schema = _emit_schema()
    assert isinstance(schema, dict)


def test_schema_declares_draft_2020_12_dialect() -> None:
    schema = _emit_schema()
    assert schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema"


def test_root_carries_tombi_extensions() -> None:
    schema = _emit_schema()
    assert schema.get("x-tombi-toml-version") == "1.0.0"
    assert "x-tombi-table-keys-order" in schema
    order = schema["x-tombi-table-keys-order"]
    assert order == [
        "meta",
        "firm",
        "jurisdiction",
        "estate_thresholds",
        "trustee_catalog",
        "diagnostics",
        "guardianship",
        "drafts",
    ]
    assert "x-tombi-string-formats" in schema
    assert "uri" in schema["x-tombi-string-formats"]


def test_top_level_properties_match_firm_config_fields() -> None:
    schema = _emit_schema()
    properties = set(schema.get("properties", {}).keys())
    expected = set(FirmConfig.model_fields.keys())
    assert properties == expected
    assert "meta" in properties


def test_lat_lon_emit_number_not_decimal_string() -> None:
    schema = _emit_schema()
    address_schema = _address_subschema(schema)
    for key in ("latitude", "longitude"):
        sub = address_schema["properties"][key]
        types = _collect_types(sub)
        assert "number" in types
        assert "string" not in types


def test_approaching_cliff_ratio_emits_bounded_number() -> None:
    schema = _emit_schema()
    sub = _resolve_ref(schema, schema["properties"]["estate_thresholds"])
    ratio = sub["properties"]["approaching_cliff_ratio"]
    assert ratio["type"] == "number"
    assert ratio.get("exclusiveMinimum") == 0
    assert ratio.get("exclusiveMaximum") == 1


def test_fdic_api_base_emits_uri_format() -> None:
    schema = _emit_schema()
    sub = _resolve_ref(schema, schema["properties"]["trustee_catalog"])
    fdic = sub["properties"]["fdic_api_base"]
    assert fdic.get("format") == "uri"


def test_meta_subschema_is_permissive() -> None:
    schema = _emit_schema()
    sub = _resolve_ref(schema, schema["properties"]["meta"])
    additional = sub.get("additionalProperties", True)
    assert additional is True or additional == {}


def test_on_disk_schema_matches_generator_byte_equal() -> None:
    assert SCHEMA_PATH.is_file(), (
        f"Expected checked-in schema at {SCHEMA_PATH}. "
        f"Run: pixi run python scripts/generate_firm_config_schema.py"
    )
    expected = json.dumps(
        _emit_schema(), indent=2, sort_keys=True, ensure_ascii=False
    ) + "\n"
    actual = SCHEMA_PATH.read_text(encoding="utf-8")
    assert actual == expected, (
        "Schema drift detected. Regenerate via "
        "`pixi run python scripts/generate_firm_config_schema.py`."
    )


def test_canonical_round_trip_against_generated_schema(tmp_path: Path) -> None:
    import tomllib

    cfg = _canonical_firm_config()
    # exclude_none=True drops unset optional fields (lat/lon, meta.schema_version,
    # meta.comment) — TOML has no null literal and the JSON Schema marks these
    # as number|null / string|null. Dropping them is the canonical round-trip.
    payload = cfg.model_dump(mode="json", exclude_none=True)
    toml_body = _to_toml(payload)
    path = tmp_path / "canonical.toml"
    path.write_text(toml_body, encoding="utf-8")
    with path.open("rb") as handle:
        loaded = tomllib.load(handle)
    schema = _emit_schema()
    jsonschema.validate(loaded, schema)


def test_generator_script_writes_schema(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config").mkdir()
    module = _load_generator_main()
    rc = module.main()
    assert rc == 0
    produced = (tmp_path / "config" / "firm-config.schema.json").read_text(
        encoding="utf-8"
    )
    assert produced.endswith("\n")
    expected = json.dumps(
        _emit_schema(), indent=2, sort_keys=True, ensure_ascii=False
    ) + "\n"
    assert produced == expected


# --- helpers ------------------------------------------------------------

def _resolve_ref(root: dict, node: dict) -> dict:
    if "$ref" in node:
        ref = node["$ref"]
        assert ref.startswith("#/"), ref
        target = root
        for segment in ref.removeprefix("#/").split("/"):
            target = target[segment]
        return target
    return node


def _address_subschema(schema: dict) -> dict:
    firm = _resolve_ref(schema, schema["properties"]["firm"])
    return _resolve_ref(schema, firm["properties"]["office_address"])


def _collect_types(node: dict) -> set[str]:
    """Accept either ``type: "x"`` or ``anyOf: [{"type": "x"}, {"type": "null"}]``."""
    types: set[str] = set()
    if "type" in node:
        value = node["type"]
        if isinstance(value, list):
            types.update(value)
        else:
            types.add(value)
    for branch_key in ("anyOf", "oneOf"):
        for branch in node.get(branch_key, []):
            types.update(_collect_types(branch))
    return types


def _to_toml(payload: dict) -> str:
    """Round-trip a ``FirmConfig.model_dump()`` payload into TOML text.

    Minimal encoder; only handles the shapes FirmConfig emits (scalars, nested
    tables, strings, bools, ints, floats, lists of scalars). Not a general TOML
    writer — exists only for the round-trip test.
    """

    import re

    def _encode_scalar(value: object) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return repr(value)
        if value is None:
            # TOML has no null literal. Callers pass exclude_none=True upstream;
            # if a None slips through, raise loudly rather than silently mis-encode
            # as empty string.
            raise ValueError("cannot encode None in TOML; use exclude_none=True upstream")
        text = str(value)
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'

    def _emit_table(header: str, data: dict) -> list[str]:
        lines = [f"[{header}]"] if header else []
        tail: list[str] = []
        for key, value in data.items():
            if isinstance(value, dict):
                nested_header = f"{header}.{key}" if header else key
                tail.extend(_emit_table(nested_header, value))
            else:
                lines.append(f"{key} = {_encode_scalar(value)}")
        lines.append("")
        return lines + tail

    top_scalars = {k: v for k, v in payload.items() if not isinstance(v, dict)}
    tables = {k: v for k, v in payload.items() if isinstance(v, dict)}

    output: list[str] = []
    if top_scalars:
        output.extend(_emit_table("", top_scalars))
    for key, value in tables.items():
        output.extend(_emit_table(key, value))

    rendered = "\n".join(output)
    rendered = re.sub(r"\n{3,}", "\n\n", rendered)
    return rendered
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pixi run test v3/config/test_firm_schema.py`
Expected: all tests fail because `trust_generator.v3.config.schema_gen` doesn't exist and the generator script raises `NotImplementedError`.

- [ ] **Step 4: Commit**

```bash
git add tests/v3/config/test_firm_schema.py scripts/generate_firm_config_schema.py
git commit -m "test(v3/config): author failing schema-generation acceptance suite"
```

---

## Task 9: Implement `TombiAwareGenerator` and the generator script

**Why ninth:** spec §12 step 9. Drives every schema test except the freshness byte-equality and the script-output test green.

**Files:**
- Create: `src/trust_generator/v3/config/schema_gen.py`
- Modify: `scripts/generate_firm_config_schema.py` (replace the `NotImplementedError` stub)

- [ ] **Step 1: Implement `TombiAwareGenerator`**

Create `src/trust_generator/v3/config/schema_gen.py`:

```python
"""JSON Schema generator with tombi-aware root extensions.

Subclasses ``pydantic.json_schema.GenerateJsonSchema`` so the root schema
carries ``x-tombi-*`` vendor extensions required by the tombi LSP for accurate
edit-time validation of ``config/firm.toml``. Per-field tombi extensions (when
any are needed) live on the Pydantic fields themselves via
``Field(json_schema_extra=...)`` so schema concerns stay colocated with field
definitions.
"""

from __future__ import annotations

from typing import Any

from pydantic.json_schema import GenerateJsonSchema, JsonSchemaMode, JsonSchemaValue

TOMBI_TABLE_KEYS_ORDER: tuple[str, ...] = (
    "meta",
    "firm",
    "jurisdiction",
    "estate_thresholds",
    "trustee_catalog",
    "diagnostics",
    "guardianship",
    "drafts",
)


class TombiAwareGenerator(GenerateJsonSchema):
    """Emit JSON Schema draft-2020-12 with tombi root extensions."""

    def generate(
        self, schema: Any, mode: JsonSchemaMode = "validation"
    ) -> JsonSchemaValue:
        result = super().generate(schema, mode=mode)
        result["x-tombi-toml-version"] = "1.0.0"
        result["x-tombi-table-keys-order"] = list(TOMBI_TABLE_KEYS_ORDER)
        result["x-tombi-string-formats"] = ["uri"]
        return result
```

- [ ] **Step 2: Implement the generator script**

Replace `scripts/generate_firm_config_schema.py` with:

```python
"""Generate config/firm-config.schema.json from FirmConfig.

Usage:

    pixi run python scripts/generate_firm_config_schema.py

Writes to config/firm-config.schema.json relative to the current working
directory. Output is pretty-printed with deterministic key sort and a trailing
newline. Re-run after any change to FirmConfig or its nested models.
"""

from __future__ import annotations

import json
from pathlib import Path

from trust_generator.v3.config import FirmConfig
from trust_generator.v3.config.schema_gen import TombiAwareGenerator

OUTPUT_PATH = Path("config") / "firm-config.schema.json"


def main() -> int:
    schema = FirmConfig.model_json_schema(schema_generator=TombiAwareGenerator)
    rendered = json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Run the schema tests (except freshness)**

The `pixi run test` task's `target` arg is relative to `tests/`. The `--deselect` flag takes a nodeid; the project uses the `tests/` cwd, so the nodeid is `v3/config/test_firm_schema.py::...`. Append pytest args via the `target` string (pixi substitutes it verbatim into the `pytest {{ target }} -v` command):

```bash
pixi run test "v3/config/test_firm_schema.py --deselect v3/config/test_firm_schema.py::test_on_disk_schema_matches_generator_byte_equal"
```

Expected: all selected tests pass (the deselected freshness test still fails because `config/firm-config.schema.json` does not yet exist — Task 10 fixes that).

- [ ] **Step 4: Commit**

```bash
git add src/trust_generator/v3/config/schema_gen.py scripts/generate_firm_config_schema.py
git commit -m "feat(v3/config): implement TombiAwareGenerator + schema-export script"
```

---

## Task 10: Generate and check in `config/firm-config.schema.json`

**Why tenth:** spec §12 step 10. Locks in the drift detector and eliminates tombi's missing-schema warning on `config/firm.toml`.

**Files:**
- Create: `config/firm-config.schema.json` (via the script in Task 9)

- [ ] **Step 1: Run the generator**

Run: `pixi run python scripts/generate_firm_config_schema.py`
Expected: exits 0, creates `config/firm-config.schema.json`.

- [ ] **Step 2: Sanity-check the output**

Run: `pixi run python -c "import json; d = json.load(open('config/firm-config.schema.json')); print(d['\$schema']); print(d['x-tombi-toml-version'])"`
Expected:
```
https://json-schema.org/draft/2020-12/schema
1.0.0
```

- [ ] **Step 3: Run the full schema test file**

Run: `pixi run test v3/config/test_firm_schema.py`
Expected: **all** tests pass, including the freshness byte-equality test.

- [ ] **Step 4: Commit**

```bash
git add config/firm-config.schema.json
git commit -m "chore(config): generate checked-in firm-config.schema.json drift artifact"
```

---

## Task 11: Confirm integration coverage stays green

**Why eleventh:** spec §12 step 11. The integration tests from Task 2 already cover the contract against `FirmConfig`; this task verifies nothing regressed after Tasks 4–10 and flags any follow-up work for downstream consumers.

**Files:**
- No new files; verify only.

- [ ] **Step 1: Run the integration tests**

Run: `pixi run test v3/integration/test_config_integration.py`
Expected: both tests pass.

- [ ] **Step 2: Run the whole project test suite as a regression check**

Run: `pixi run check`
Expected: `lint`, `mypy`, and `test` all pass.

- [ ] **Step 3: Document consumer-side follow-ups (if any)**

Grep for lingering v3 references to hardcoded values that `FirmConfig` now owns:

```bash
grep -rn "banks.data.fdic.gov" src/trust_generator/v3/ || echo "no hardcoded FDIC URL"
grep -rn "3_000_000\|3000000" src/trust_generator/v3/ --include '*.py' || echo "no hardcoded threshold"
```

Expected: no hits outside `config/firm.py`. If any hit exists, record it in a follow-up note at the end of this plan's commit message rather than expanding this task's scope.

- [ ] **Step 4: Commit (no-op if no changes)**

If nothing was modified, skip the commit. Otherwise:

```bash
git add <files>
git commit -m "test(v3): verify integration coverage + prune hardcoded v3 constants"
```

---

## Task 12: Documentation

**Why twelfth:** spec §12 step 12. Keeps the README accurate for the maintainer who hand-edits the config file.

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a firm_config section to `README.md`**

Append the following section to `README.md` (after any existing v2.x documentation, before any trailing license footer):

```markdown
### v3 Firm Configuration (`config/firm.toml`)

**Location.** Hand-edited firm configuration lives at `config/firm.toml`, anchored by a `#:schema ./firm-config.schema.json` directive that tombi (and any JSON-Schema-aware TOML LSP) uses for edit-time validation. The canonical key reference is in `docs/superpowers/specs/2026-04-21-firm-config-design.md`.

**Env-var overlay.** Any field can be overridden at runtime via an environment variable prefixed `TGV3_` with `__` as the nested delimiter. Example: `TGV3_ESTATE_THRESHOLDS__SINGLE_HARD=5000000` overrides `estate_thresholds.single_hard` without editing the file. Env overlay sits above TOML in the precedence order (env > TOML > Pydantic defaults).

**Schema regeneration.** The JSON Schema at `config/firm-config.schema.json` is a generated artifact, derived from the same Pydantic models the loader validates against. After any change to `src/trust_generator/v3/config/firm.py`, regenerate with:

```bash
pixi run python scripts/generate_firm_config_schema.py
```

The pytest suite includes a freshness test (`test_on_disk_schema_matches_generator_byte_equal`) that fails if the checked-in schema drifts from the generator output. If it fails, regenerate and re-commit.
```

- [ ] **Step 2: Run the check suite one more time**

Run: `pixi run check`
Expected: lint, mypy, and all tests pass.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs(v3): document firm_config env overlay + schema regen command"
```

---

## Spec coverage self-check

| Spec section | Covered by task(s) |
| ------------ | ------------------ |
| §5.1 FirmIdentity + Address | Task 4 (see amendment A-1) |
| §5.2 Jurisdiction | Task 4 |
| §5.3 EstateThresholds (incl. cross-field) | Task 4 (model_validator) |
| §5.4 TrusteeCatalog + HttpUrl | Task 4 |
| §5.5 Diagnostics (incl. path anchoring) | Task 4, Task 5 (_resolve_paths) |
| §5.6 Guardianship | Task 4 |
| §5.7 Drafts | Task 4 |
| §5.8 Meta forward-compat seam | Task 4 (extra="allow") |
| §6 File layout + `#:schema` directive | Task 6 |
| §7 Loader API + precedence | Task 5 |
| §8 Validation layers | Task 4 (field + model validators), Task 5 (FirmConfigError wrapping) |
| §9 v2→v3 migration mapping | Task 6 |
| §10.1 Loader unit tests | Task 2 (authoring), Task 5 (green) |
| §10.2 Schema tests | Task 8 (authoring), Tasks 9–10 (green) |
| §10.3 Integration tests | Task 2 (authoring), Task 5+11 (green) |
| §12 Implementation checklist | All tasks |
| §13 Editor schema generation | Task 9 (TombiAwareGenerator), Task 10 (artifact) |
| §13.5 Freshness enforcement | Task 8 test + Task 10 artifact |
| §13.6 Library reconnaissance | Tasks 3, 7 (adopt pydantic-settings + jsonschema) |
| Amendment A-1 (Address reuse) | Tasks 4, 6, 8 |

**Intentionally not implemented by this plan:**

- GUI editor / config write path — spec §2 out-of-scope.
- Audit log writer — spec §2 out-of-scope; `diagnostics.audit_log_dir` is populated but the writer is deferred.
- Rule loader — spec §2 out-of-scope; `diagnostics.rules_dir` is populated but the loader is deferred.
- Downstream consumer code (`trustee_catalog` refresh client implementation, diagnostics subsystem) — spec §10.3 covers the config-surface contract only; consumer code is a separate scope.
- `SchemaNumber` type alias — suppressed by amendment A-1 (no firm_config field requires `Decimal`).

---

## Execution notes

- **Frequent commits.** Each task ends with a commit. Do not batch tasks into a single commit; the per-task history is the reviewer's walkthrough.
- **Branch.** v3.0.0 (active feature branch). No worktree per user instructions.
- **No `--no-verify` commits.** If a pre-commit hook or lint check fails, fix the root cause and commit again. Never skip hooks.
- **Schema freshness.** If any code change after Task 10 touches `FirmConfig` or its nested models, re-run `pixi run python scripts/generate_firm_config_schema.py` and commit the updated artifact in the same commit that changed the models.

---

## Plan-review disposition (2026-04-22)

The `reasoning-protocols:plan-review` protocol was run against the initial draft of this plan. Two blockers and four significant concerns were raised; all have been addressed in the plan text above:

| Ref | Concern | Resolution |
| --- | ------- | ---------- |
| B1  | `pixi run test tests/...` paths collided with `cwd = 'tests/'` → silent zero-collection | All `pixi run test` invocations now use paths relative to `tests/` (e.g. `v3/config`). Operational note added to the plan header. |
| B2  | `_to_toml` encoded `None` as `""`, breaking the round-trip test against a `number|null` schema for lat/lon | Round-trip test now uses `exclude_none=True`; `_to_toml._encode_scalar` raises `ValueError` if a `None` slips through. |
| S1  | Strict-extra test appended a duplicate `[firm]` header → `tomllib.TOMLDecodeError`, not `extra="forbid"` rejection | Test now injects the unknown key inline inside the existing `[firm]` table and asserts the error message names the key. |
| S2  | Spec §10.3 implies consumer-behavior assertions; plan only tested config-surface | Spec amendment **A-2** recorded, explicitly narrowing §10.3 to config-surface contract and deferring consumer wiring to the downstream specs that own those subsystems. Task 11 Step 3 carries a grep to confirm no pre-existing v3 code needs rewiring. |
| S3  | `HttpUrl("...")` direct construction as a `Field` default is brittle across pydantic v2 point releases | `fdic_api_base` default is now a string literal coerced by Pydantic at validation time. |
| S4  | Loader bypasses `TomlConfigSettingsSource` (reads TOML directly, passes as init-kwargs) — diverges from spec §7 internal-shape note | Spec amendment **A-3** recorded, documenting the direct-`tomllib` approach and explaining why runtime-discovered paths preclude the static `toml_file` idiom. |
| M1  | Multi-path `pixi run lint` invocations need quoting (single `include` arg) | Quoted: `pixi run lint "src/... tests/... tests/..."`. |
| M2  | `TombiAwareGenerator.generate` mode annotation widened `JsonSchemaMode` → `str` | Now imports and uses `JsonSchemaMode` + `JsonSchemaValue` from `pydantic.json_schema`. |
| M3  | Empty `__init__.py` markers optional under pytest's rootdir discovery | Retained for consistency with the existing `tests/v3/__init__.py` convention in this repo. No change required. |

No remaining unresolved concerns. Plan is ready for implementation pending user approval.
