# TGv3 firm_config Module Design

| Field        | Value                                                   |
| ------------ | ------------------------------------------------------- |
| Spec date    | 2026-04-21                                              |
| Status       | Finalized (amended 2026-04-24 — A-4, A-5, A-6)          |
| Supersedes   | `config/firm.v2.toml` (v2.2)                            |
| Relevant entities | `library_selections`, `estate_thresholds`, `corporate_trustee_catalog`, `diagnostics_enforcement`, `bounded_context_design` |
| Out of scope | Diagnostic rule files, GUI rules pane, audit log writer, `schema.py` modifications |

## 1. Motivation

TGv3 consumes firm-scoped runtime configuration from multiple subsystems: estate-tax threshold evaluation, corporate trustee catalog queries, diagnostic enforcement levels, guardianship defaults, and letterhead/jurisdictional identity. v2's `firm.toml` covered only a thin slice (firm identity, jurisdiction defaults, draft retention). The v3 footprint is broader, it is read by subsystems that run outside the GUI (CLI, background refresh jobs), and several fields require validation that cannot be expressed in raw TOML.

This spec defines: the config key surface, the loader's API, the file format choice, and the precedence rules for overlays.

## 2. Scope

### In scope

- Enumerated key list with types, defaults, and owning subsystem.
- Loader function signature and discovery order.
- Validation strategy via Pydantic models.
- Precedence between file contents, environment variables, and explicit construction kwargs.
- Format choice (TOML vs YAML) with rationale.
- Migration mapping from `config/firm.v2.toml`.

### Out of scope (enforced)

- Diagnostic rule content, YAML rule files, rule-engine wiring — addressed in the diagnostics rules spec.
- GUI config editor pane and its write path — a later concern.
- Audit log writer implementation — addressed in the diagnostics enforcement spec.
- Modifications to `schema.py` or the `Elections` defaults documented there (they remain code-defined by v2 policy; see §9).

## 3. Library reconnaissance outcomes

### pydantic-settings (v2.14.0, MIT, Python >=3.10)

**Resolution:** adopt-as-dependency.

Released 2026-04-20. Provides `TomlConfigSettingsSource` and `YamlConfigSettingsSource` as first-class citizens, a documented precedence-override hook (`settings_customise_sources`), env-var nested delimiter support for overlays, and native nested-`BaseModel` composition. Unifies file load, env override, and field validation in one package, which is the exact seam shape this module needs.

### stdlib tomllib (Python 3.11+, PSF License)

**Resolution:** adopt-direct (transitively, via pydantic-settings).

Read-only. No `dump()` and none planned (CPython issue #103188 closed without accepting). The read-only limitation is non-binding here: the GUI config editor's write path is out of scope. When that scope opens, `tomlkit` is the expected companion choice. Returns a plain `dict`, so comment and style preservation is not available on read, but that is irrelevant for our load-then-validate pipeline.

### ruamel.yaml (0.19.x, MIT, Python 3.9–3.14)

**Resolution:** NOT adopted for firm_config. Reserved for diagnostic rule files (separate scope).

Round-trip mode preserves comments, key order, and quote styles, but normalizes scalar representations (booleans, `None`, indentation). Not a byte-exact editor. The right tool for files authors will hand-edit repeatedly with interleaved comments and structure — rule files qualify, `firm.toml` does not.

## 4. Format decision: TOML

TOML wins on four grounds:

1. **Zero dependency for the read path.** `tomllib` is stdlib at our 3.12 floor. YAML would pull `ruamel.yaml` (or PyYAML) in as a mandatory dependency purely for config.
2. **Lower footgun surface for hand-editing.** Firm staff are non-developers. TOML's `key = value` + bracketed tables resemble INI, which is more forgiving than YAML's indentation-significant grammar where a single stray space silently rebinds a value.
3. **Shape fit.** The firm_config content is predominantly scalar values under shallow nested tables. TOML's table syntax maps cleanly; YAML's advantages (deep nesting, tag syntax, multi-line strings) are unused here.
4. **First-class pydantic-settings support.** `TomlConfigSettingsSource` is the documented idiom.

YAML is the correct choice for diagnostic rule files, where rules are authored with interleaved comments and expression-heavy scalar values. That is a different file, a different consumer, and a different decision — recorded separately.

## 5. Configuration schema

All values below are enumerated with type, default (or `REQUIRED`), and consuming subsystem. Types refer to Pydantic/stdlib types. Numeric types follow the rationalization in §13.2 (driven by tombi's JSON Schema format support): whole-dollar amounts use `int`, ratios use `Decimal` with an explicit `WithJsonSchema` override, and lat/lon use `Decimal` with the same override pattern.

### 5.1 `[firm]` — firm identity and office location

| Key                        | Type    | Default    | Consumer                         |
| -------------------------- | ------- | ---------- | -------------------------------- |
| `firm.name`                | `str`   | `REQUIRED` | Letterhead, generator preamble   |
| `firm.phone`               | `str`   | `REQUIRED` | Letterhead                       |
| `firm.office_address.street`    | `str`      | `REQUIRED` | Letterhead, geocoding anchor     |
| `firm.office_address.city`      | `str`      | `REQUIRED` | Letterhead, geocoding anchor     |
| `firm.office_address.state`     | `str`      | `REQUIRED` | Letterhead                       |
| `firm.office_address.zip`       | `str`      | `REQUIRED` | Letterhead                       |
| `firm.office_address.country`   | `str`      | `"US"`     | geocoding normalization          |
| `firm.office_address.latitude`  | `SchemaNumber | None`† | `None`     | trustee_catalog radius queries (resolved on demand) |
| `firm.office_address.longitude` | `SchemaNumber | None`† | `None`     | trustee_catalog radius queries (resolved on demand) |

† `SchemaNumber` is the type alias defined in §13.2: `Annotated[Decimal, WithJsonSchema({"type": "number"})]`. Decimal is used for coordinate precision; the annotation overrides Pydantic's default `Decimal`-as-string JSON Schema emission so tombi sees a validated number.

Shape note: `office_address` imports the `Address` model from `trust_generator.v3.schema`, which is step 1 of the v3 critical path and therefore available before firm_config's implementation begins. Lat/lon are optional because most consumers don't require geographic queries; when a consumer needs them (e.g., `trustee_catalog` radius queries), the consumer resolves them on demand via geopy. Persistent caching of resolved coordinates is explicitly out of scope for v3 and deferred to a future spec if geocoder load becomes a measurable concern.

### 5.2 `[jurisdiction]` — legal/jurisdictional defaults

| Key                                 | Type   | Default                                                | Consumer          |
| ----------------------------------- | ------ | ------------------------------------------------------ | ----------------- |
| `jurisdiction.default_state`        | `str`  | `"Illinois"`                                           | Generator, parser |
| `jurisdiction.default_county`       | `str`  | `"Winnebago"`                                          | Generator         |
| `jurisdiction.trust_code_citation`  | `str`  | `"Illinois Trust Code (760 ILCS 3/101, et seq.)"`      | Generator (Art. 11) |

### 5.3 `[estate_thresholds]` — IL estate-tax cliff parameters

Sourced from `estate_thresholds` entity. Illinois taxes the entire excess above threshold (cliff behavior), so these values drive both the soft detail-collection gate and the hard blocking diagnostic.

| Key                                                | Type       | Default     | Consumer              |
| -------------------------------------------------- | ---------- | ----------- | --------------------- |
| `estate_thresholds.single_soft`                    | `int`      | `3_000_000` | Diagnostics (gate)    |
| `estate_thresholds.joint_soft`                     | `int`      | `6_000_000` | Diagnostics (gate)    |
| `estate_thresholds.single_hard`                    | `int`      | `4_000_000` | Diagnostics (cliff)   |
| `estate_thresholds.joint_hard`                     | `int`      | `8_000_000` | Diagnostics (cliff)   |
| `estate_thresholds.approaching_cliff_ratio`        | `float`    | `0.90`      | Diagnostics (warning) |

Semantic: the approaching-cliff diagnostic fires when `estate_value >= hard_threshold * approaching_cliff_ratio`. The default `0.90` means "warn at 90% of hard threshold." `float` (not `Decimal`) because the value has no more than two significant digits and participates in arithmetic against `int` thresholds; `Decimal` would require conversion ceremony for no precision gain. Tombi validates `float` as JSON Schema `number` natively — no `WithJsonSchema` override needed.

Validation rules (Pydantic model validators):

- `0 < single_soft < single_hard`, `0 < joint_soft < joint_hard`.
- `single_soft <= joint_soft`, `single_hard <= joint_hard`.
- `0 < approaching_cliff_ratio < 1` (enforced via `Field(gt=0, lt=1)` for edit-time tombi visibility).

Rationale for keeping as config not constants: legislative changes (HB2601 pending as of April 2026) may shift these on a statutory schedule; attorneys track this manually and update the file.

### 5.4 `[trustee_catalog]` — corporate trustee catalog

Sourced from `corporate_trustee_catalog` entity.

| Key                                     | Type   | Default                                  | Consumer                |
| --------------------------------------- | ------ | ---------------------------------------- | ----------------------- |
| `trustee_catalog.db_path`               | `Path` | `"./data/trustee_catalog.sqlite"`        | Catalog persistence     |
| `trustee_catalog.radius_miles`          | `int`  | `100`                                    | Catalog geographic query |
| `trustee_catalog.refresh_days`          | `int`  | `30`                                     | Background refresh job  |
| `trustee_catalog.fdic_api_base`         | `str`  | `"https://banks.data.fdic.gov/api"`      | Refresh client          |
| `trustee_catalog.fdic_request_timeout_s`| `int`  | `30`                                     | Refresh client          |

Validation:

- `radius_miles > 0`, `refresh_days > 0`, `fdic_request_timeout_s > 0`.
- `fdic_api_base` validated as `HttpUrl`.

Geographic anchor is not set here; it is derived from `firm.office_address.latitude/longitude`.

### 5.5 `[diagnostics]` — diagnostic enforcement

Sourced from `diagnostics_enforcement` entity.

| Key                                      | Type                              | Default                    | Consumer                |
| ---------------------------------------- | --------------------------------- | -------------------------- | ----------------------- |
| `diagnostics.default_restriction_level`  | `Literal["info","warning","error"]` | `"error"`                | CLI, GUI default        |
| `diagnostics.allow_force_generation`     | `bool`                            | `true`                     | CLI, GUI                |
| `diagnostics.audit_log_dir`              | `Path`                            | `"./logs/audit"`           | Audit writer (deferred) |
| `diagnostics.audit_log_rotation`         | `Literal["monthly","weekly","daily"]` | `"monthly"`            | Audit writer (deferred) |
| `diagnostics.rules_dir`                  | `Path`                            | `"./config/rules"`         | Rule loader (deferred)  |

Paths are resolved relative to the firm_config file's parent directory when given as relative paths. Absolute paths are used as-is. This keeps a firm's whole config bundle portable: moving the config directory moves all referenced paths with it.

### 5.6 `[guardianship]` — guardianship policy default

Sourced from userMemories note and the `bounded_context_design` entity's questionnaire/TrustData split.

| Key                             | Type                                           | Default                    | Consumer                         |
| ------------------------------- | ---------------------------------------------- | -------------------------- | -------------------------------- |
| `guardianship.default_policy`   | `Literal["DELEGATE_TO_TRUSTEES","EXPLICIT_DESIGNATIONS"]` | `"EXPLICIT_DESIGNATIONS"`  | Questionnaire seed defaulting    |

### 5.7 `[drafts]` — preserved from v2

| Key                    | Type  | Default | Consumer                 |
| ---------------------- | ----- | ------- | ------------------------ |
| `drafts.auto_purge_days`| `int` | `90`    | Startup purge (GUI scope) |

Preserved verbatim from v2 because the startup purge behavior still applies. If GUI-scope work reshapes draft retention, this key is the anchor for that refactor; do not remove in the interim.

### 5.8 `[meta]` — forward-compatibility seam

| Key                   | Type         | Default | Consumer                                |
| --------------------- | ------------ | ------- | --------------------------------------- |
| `meta.schema_version` | `str | None` | `None`  | Informational; reserved for future use  |
| `meta.comment`        | `str | None` | `None`  | Free-form firm-maintainer notes; unused at runtime |

The `Meta` nested model is configured with `model_config = ConfigDict(extra="allow")` while the rest of `FirmConfig` retains `extra="forbid"`. This creates a scoped relaxation: unknown keys anywhere else fail loudly (typo protection), but unknown keys under `[meta]` are permitted (forward-compat seam). Firms can use `[meta]` to annotate the file without triggering validation errors, and future v3.x additions that need to carry metadata forward can land under `[meta]` without breaking older binaries.

This resolves the open question flagged in §11.2: `schema_version` exists as a string field but carries no runtime behavior in v3. If migrations ever need it, the field is available without a schema change.

## 6. File layout

Final path: `config/firm.toml`. v2 lives as `config/firm.v2.toml` (already renamed) for historical reference and is not read by v3.

Illustrative shape:

```toml
#:schema ./firm-config.schema.json
# Trust Generator v3 — Firm Configuration
# Hand-editable. Reloaded on application start.

[meta]
# schema_version and comment are optional.
# Additional keys under [meta] are permitted (forward-compat seam).

[firm]
name  = "Crosby and Crosby LLP"
phone = "(815) 367-6432"

  [firm.office_address]
  street = "3815 N Mulford Rd. 4"
  city   = "Rockford"
  state  = "IL"
  zip    = "61114"
  # latitude and longitude resolved on demand; not persisted here.

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

## 7. Loader API

```python
# src/trust_generator/v3/config/firm.py

from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_CONFIG_PATH: Final[Path] = Path("config/firm.toml")
ENV_VAR_CONFIG_PATH: Final[str] = "TGV3_FIRM_CONFIG"
ENV_PREFIX: Final[str] = "TGV3_"

class FirmConfigError(Exception):
    """Raised when firm_config cannot be loaded or fails validation."""

class Meta(BaseModel):
    """Forward-compatibility seam. Unknown keys under [meta] are permitted."""
    model_config = ConfigDict(extra="allow")

    schema_version: str | None = None
    comment: str | None = None

class FirmConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix=ENV_PREFIX,
        env_nested_delimiter="__",
        extra="forbid",
    )

    meta: Meta = Meta()
    firm: FirmIdentity
    jurisdiction: Jurisdiction
    estate_thresholds: EstateThresholds = EstateThresholds()
    trustee_catalog: TrusteeCatalog = TrusteeCatalog()
    diagnostics: Diagnostics = Diagnostics()
    guardianship: Guardianship = Guardianship()
    drafts: Drafts = Drafts()

def load_firm_config(path: Path | None = None) -> FirmConfig:
    """Load, validate, and return the firm configuration.

    Discovery order for the TOML file:
      1. `path` argument if provided.
      2. $TGV3_FIRM_CONFIG environment variable if set.
      3. ./config/firm.toml relative to CWD.

    Precedence for conflicting values (highest first):
      1. Explicit kwargs passed to FirmConfig(...) (tests only).
      2. Environment variables prefixed TGV3_ (with __ as nested delimiter).
      3. TOML file contents.
      4. Pydantic field defaults declared on the nested models.

    Raises:
      FirmConfigError: if the file is missing when required-without-default
      fields have no env-var override, if TOML parsing fails, or if
      Pydantic validation fails. The exception message quotes the
      originating error for diagnostic purposes.
    """
    ...
```

Notes on the signature:

- The function is intentionally the only public entry point. `FirmConfig(...)` should not be constructed directly outside tests.
- Paths resolved inside the loader are rewritten to be absolute before being passed on, using the config file's parent directory as the anchor (see §5.5).
- Env-var example: `TGV3_ESTATE_THRESHOLDS__SINGLE_HARD=4500000` overlays the TOML value. Useful for one-off experiments and containerized test runs.
- Failure mode is fail-fast: a missing `firm.name` (required, no default) raises `FirmConfigError` at load time rather than deferring the error to generation time.

### Internal shape

The loader composes pydantic-settings sources explicitly via `settings_customise_sources` to force the precedence order declared above, overriding the library's default (which places file below env by default, which matches our intent, but we pin it to avoid surprises on library updates).

## 8. Validation strategy

Three validation layers, in order:

1. **TOML parse.** Handled by `tomllib` via pydantic-settings. Syntax errors raise `FirmConfigError`.
2. **Field-level.** Pydantic enforces types, literal values, URL shapes, non-negative numerics. Uses field validators on each nested `BaseModel`.
3. **Cross-field.** Pydantic model-level validators on `EstateThresholds` (soft < hard, joint >= single, ratio bounds) and on `FirmIdentity` (ZIP format if state is US).

Strict-extra exception: `FirmConfig` and all nested models use `extra="forbid"` to catch typos at load time. The single exception is `Meta` (§5.8), which uses `extra="allow"` so that future v3.x additions or firm-side annotations under `[meta]` don't trigger validation errors. The relaxation is scoped to that subtree only.

No validation occurs outside these three layers; downstream consumers (e.g., the trustee_catalog refresh client) trust the typed `FirmConfig` object and do not re-validate its fields.

## 9. Migration from v2

| v2 key                          | v3 key                                                    | Notes                                  |
| ------------------------------- | --------------------------------------------------------- | -------------------------------------- |
| `firm.address_line1`            | `firm.office_address.street`                              | Rename. v2's free-form line1 maps to street. |
| `firm.address_line2`            | `firm.office_address.{city,state,zip}`                    | Split. v2 mashed city/state/zip into line2; v3 requires structured decomposition. Migration is one-time manual work for the one existing file. |
| `firm.name`                     | `firm.name`                                               | Unchanged.                             |
| `firm.phone`                    | `firm.phone`                                              | Unchanged.                             |
| `jurisdiction.default_state`    | `jurisdiction.default_state`                              | Unchanged.                             |
| `jurisdiction.default_county`   | `jurisdiction.default_county`                             | Unchanged.                             |
| `jurisdiction.trust_code_citation` | `jurisdiction.trust_code_citation`                     | Unchanged.                             |
| `drafts.auto_purge_days`        | `drafts.auto_purge_days`                                  | Unchanged.                             |
| (not in v2)                     | `estate_thresholds.*`                                     | New. Ships with IL defaults.           |
| (not in v2)                     | `trustee_catalog.*`                                       | New. Ships with sensible defaults.     |
| (not in v2)                     | `diagnostics.*`                                           | New. Ships with sensible defaults.     |
| (not in v2)                     | `guardianship.default_policy`                             | New. Ships as EXPLICIT_DESIGNATIONS.   |
| (not in v2)                     | `meta.*`                                                  | New. Optional forward-compat seam (§5.8); empty by default. |

Preserved boundary from v2: legal election defaults (spendthrift, no-contest, distribution standard, etc.) remain code-defined in `schema.py`'s `Elections` class. v2's comment rationale is correct — changes to legal defaults require code review, not config edits — and v3 inherits this constraint. firm_config does not expose Elections fields.

One-time migration: the existing `config/firm.v2.toml` will be translated into a new `config/firm.toml` at the time of the implementation commit. A migration script is optional; the surface is small enough that manual transcription is acceptable and auditable.

## 10. Testing strategy (TDD acceptance criteria)

The tests below are the implementation acceptance criteria, not a post-hoc verification step. Per the project's TDD principle, they are written first against import-only stubs of `FirmConfig` and `load_firm_config`, fail by design at the start of implementation, and drive the model, loader, and schema-generator work to completion. The implementation checklist in §12 reflects this ordering. A test that doesn't appear here represents either a missing acceptance criterion (add it) or a scope creep (reject it).

### 10.1 Loader unit tests

Covered in `tests/v3/config/test_firm.py`:

- **Happy path.** A well-formed TOML file loads into a `FirmConfig` with expected values.
- **Defaults.** A minimal TOML file with only `[firm]` and `[jurisdiction]` populated yields defaults for all other sections (including an empty `Meta`).
- **Required-field failure.** Missing `firm.name` raises `FirmConfigError` with a message that names the field.
- **Cross-field failure.** `single_hard < single_soft` raises `FirmConfigError`.
- **Env overlay.** `TGV3_ESTATE_THRESHOLDS__SINGLE_HARD=5_000_000` overrides the file value.
- **Path resolution.** Relative `audit_log_dir` resolves against the config file's parent directory; absolute `audit_log_dir` is used as-is.
- **Strict extra outside meta.** `extra="forbid"` causes an unknown key in any non-`[meta]` table to fail loudly.
- **Permissive extra inside meta.** `[meta]` accepts arbitrary keys without raising. The known fields (`schema_version`, `comment`) parse normally; unknown keys are accessible via `meta.model_extra`.
- **Discovery order.** Explicit `path` argument wins over env var; env var wins over default path.

### 10.2 Schema generation tests

Covered in `tests/v3/config/test_firm_schema.py`:

- **Generator runs.** Invoking the generator script produces a JSON Schema dict without raising.
- **Dialect.** The generated schema declares `$schema` as `https://json-schema.org/draft/2020-12/schema`.
- **Tombi root extensions.** The generated schema includes `x-tombi-toml-version` and `x-tombi-table-keys-order` at the root.
- **Property coverage.** The generated schema's top-level `properties` keys match `FirmConfig.model_fields` exactly (no orphans, no missing). `[meta]` is among them.
- **SchemaNumber coercion.** Lat/lon emit `{"type": "number"}` rather than the default `Decimal`-as-string schema. `approaching_cliff_ratio` emits `{"type": "number", "exclusiveMinimum": 0, "exclusiveMaximum": 1}` natively (no override needed; it is `float`).
- **URL format.** `trustee_catalog.fdic_api_base` emits `format: "uri"` and the root carries `x-tombi-string-formats` including `"uri"`.
- **Meta permissiveness.** The `[meta]` subschema declares `additionalProperties: true` (or omits the constraint entirely) so tombi does not flag unknown keys there.
- **Freshness.** The generator output equals the on-disk `config/firm-config.schema.json` byte-for-byte (after deterministic key sort and pretty-print). This is the drift detector.
- **Validation round-trip.** A serialized canonical `FirmConfig` instance, written to TOML, loaded by `tomllib`, and validated against the generated schema using the `jsonschema` library (added as a dev dependency per §12 step 7), passes without error.

### 10.3 Integration tests

Covered in `tests/v3/integration/test_config_integration.py`:

- The `trustee_catalog` refresh client receives its URL and timeout from the loaded config, not from hardcoded defaults.
- The diagnostics subsystem reads its default restriction level from the loaded config.

## 11. Open questions

1. **Secrets.** Nothing in the current key list qualifies as a secret. If the FDIC API ever gains authentication, or if an email-sending subsystem is added, revisit whether to pull in pydantic-settings' `SecretsSettingsSource` or use env vars exclusively for secret material. No action required now.
2. **Locale/timezone.** Not included. The audit log rotation cadence is naive-monthly; if the firm operates across time zones this becomes a correctness concern. Flagged for the audit-log-writer spec.

## 12. Implementation checklist (TDD-ordered)

Each step ends with a green `pixi run test` for the tests that drive it. No step is considered done while its tests remain red, and no later step begins until the earlier ones are green. Dependency declarations conform to the project's pixi-as-primary convention: runtime deps go in `pixi.toml` under `[pypi-dependencies]` and `[package.run-dependencies]`; dev deps go under `[feature.dev.dependencies]` (conda) or the equivalent pypi slot.

1. [ ] **Stub for importability.** Create `src/trust_generator/v3/config/firm.py` and `src/trust_generator/v3/config/__init__.py` with `Meta`, `FirmConfig` (empty `BaseSettings` subclass with the `meta` field), and `load_firm_config(path: Path | None = None) -> FirmConfig` raising `NotImplementedError`. Just enough for the test suite to import.
2. [ ] **Author the failing tests.** Write all of §10.1 and §10.3 against the stubs at `tests/v3/config/test_firm.py` and `tests/v3/integration/test_config_integration.py`. They must all fail (most with `NotImplementedError`, the rest with `AssertionError` or import errors). Commit the failing suite — this is the spec made executable.
3. [ ] **Add `pydantic-settings >=2.14,<3` as a runtime dep.** Add to `pixi.toml` `[pypi-dependencies]` and `[package.run-dependencies]`. Required before model implementation can use `BaseSettings`-with-sources.
4. [ ] **Implement nested models.** `Meta`, `FirmIdentity`, `Jurisdiction`, `EstateThresholds`, `TrusteeCatalog`, `Diagnostics`, `Guardianship`, `Drafts`. Import `Address` from `trust_generator.v3.schema`. Iterate until every model-shape and field-validator test from §10.1 passes.
5. [ ] **Implement `load_firm_config`.** Source customization, discovery order, env-var nested overlay, fail-fast `FirmConfigError`. Iterate until all of §10.1 is green.
6. [ ] **Translate `config/firm.v2.toml` to `config/firm.toml`** under the v3 shape per §9. Include the `#:schema ./firm-config.schema.json` directive at the top of the new file. The schema artifact does not yet exist, but tombi degrades to a warning rather than an error on a missing schema reference; the directive lands in its final position now to avoid a second edit later. The integration tests in step 11 depend on this file.
7. [ ] **Add `jsonschema >=4,<5` as a dev dep.** Add to `pixi.toml` `[feature.dev.dependencies]`. Required by the §10.2 round-trip validation test. Explicitly dev-only; the runtime loader does not use it.
8. [ ] **Author the failing schema-generation tests** (§10.2). Add to `tests/v3/config/test_firm_schema.py`. Stub the generator script as `scripts/generate_firm_config_schema.py` raising `NotImplementedError`. The tests must fail.
9. [ ] **Implement the schema generator.** `TombiAwareGenerator` subclass, the `SchemaNumber` type alias and any per-field `WithJsonSchema` overrides, root-level `x-tombi-*` extensions. Iterate until all of §10.2 except the freshness test is green.
10. [ ] **Run the generator and check in `config/firm-config.schema.json`.** Re-run §10.2 — the freshness test should now pass and tombi's missing-schema warning on `firm.toml` should disappear.
11. [ ] **Implement integration coverage.** Make §10.3 green. May require small adjustments to consumer subsystems (trustee_catalog refresh client, diagnostics) to read from `FirmConfig` instead of constants.
12. [ ] **Document.** Add `README.md` section covering: env-var override convention, schema regeneration command (`pixi run python scripts/generate_firm_config_schema.py`), and where the firm_config file lives. One paragraph per topic.

## 13. Editor schema generation

The firm_config TOML file is hand-edited by a single maintainer using Helix with tombi as the LSP. To raise the feedback loop on edits from "load-time validation error in a CLI run" to "edit-time inline diagnostic + completion + hover documentation," a JSON Schema is generated from the same Pydantic models the loader validates against, and associated with `config/firm.toml` via tombi's schema discovery.

The hand-edit context is the load-bearing assumption: a sole maintainer hand-editing a config file with mixed scalar formats (URLs, paths, dollar amounts, ratios, enum literals) gets disproportionate value from edit-time feedback that catches typos, malformed URLs, out-of-range values, and unknown keys before save.

### 13.1 Generation strategy: derived, not parallel

There is no second source of truth. The schema is a build artifact derived from `FirmConfig`. The generator is a script that:

1. Imports `FirmConfig` from `src/trust_generator/config/firm.py`.
2. Calls `FirmConfig.model_json_schema(schema_generator=TombiAwareGenerator)`.
3. Writes the result to `config/firm-config.schema.json`, pretty-printed with deterministic key sort.

`TombiAwareGenerator` is a `pydantic.json_schema.GenerateJsonSchema` subclass. Its `generate()` override calls `super().generate()` then injects root-level tombi extensions:

- `x-tombi-toml-version`: pinned to `"1.0.0"` (TOML 1.1 is preview as of April 2026, not yet supported by enough tooling).
- `x-tombi-table-keys-order`: keyed to the canonical section order (firm → jurisdiction → estate_thresholds → trustee_catalog → diagnostics → guardianship → drafts), so `tombi format` rearranges hand-shuffled tables back into the canonical order on save.
- `x-tombi-string-formats`: includes `"uri"` so tombi opts the URL-format fields into validation rather than treating `format: "uri"` as decorative.

Per-field tombi extensions (where any are needed) are declared on the Pydantic fields themselves via `Field(json_schema_extra={"x-tombi-...": ...})`. This keeps schema concerns colocated with field definitions rather than scattered across a separate post-processing pass — which is the same colocation principle Pydantic itself follows for `Field(description=...)`, `Field(ge=...)`, and so on.

### 13.2 Type rationalization for tombi compatibility

Tombi's default validator only recognizes JSON Schema's standard built-in string formats. Pydantic emits `Decimal` as `{"type": "string", "format": "decimal"}` by default, which tombi treats as an unconstrained string — losing the constraint we wanted in the first place. Three adjustments resolve this without compromising Pydantic's runtime validation:

1. **Whole-dollar amounts use `int`.** The four threshold fields (`single_soft`, `joint_soft`, `single_hard`, `joint_hard`) are typed `int` rather than `Decimal`. Whole-dollar precision is the legal reality at the millions scale; Illinois statute does not contemplate fractional cents in cliff thresholds.
2. **`approaching_cliff_ratio` uses `float`.** Two-significant-digit ratios derive no benefit from `Decimal` precision; thresholds are now `int`, so there is no Decimal arithmetic to protect. `float` emits as native JSON Schema `number` with no override required, and `Field(gt=0, lt=1)` surfaces the bounds as `exclusiveMinimum`/`exclusiveMaximum` for tombi.
3. **Coordinate values use `SchemaNumber`.** Lat/lon retain `Decimal` for coordinate-grade precision but use a type alias that bundles the override:

       from decimal import Decimal
       from typing import Annotated
       from pydantic import WithJsonSchema

       type SchemaNumber = Annotated[Decimal, WithJsonSchema({"type": "number"})]

   The alias prevents drift if more such fields appear later. Bounded variants (e.g., for latitude in `[-90, 90]`) extend by composition: `Annotated[SchemaNumber, Field(ge=-90, le=90)]`.

Adjustments 1 and 2 are reflected in §5.3; adjustment 3 in §5.1.

**Footnote on `WithJsonSchema` + `json_schema_extra` interaction.** `WithJsonSchema` replaces the entire field schema rather than merging into it. If a field needs both a tombi extension (e.g., `x-tombi-array-values-order`) and a number-coercion override, the extension must be encoded inside the `WithJsonSchema` payload — `x-tombi-*` keys are valid JSON Schema vendor extensions and pass through unchanged. For example: `WithJsonSchema({"type": "number", "x-tombi-array-values-order": "ascending"})`. No firm_config field requires both today, but the pattern is documented for future fields.

### 13.3 Schema discovery

The `#:schema` directive at the top of `config/firm.toml` is the sole association mechanism:

    #:schema ./firm-config.schema.json

Path is relative to the TOML file's location. The directive travels with the file — anyone who reads the file in a tombi-aware editor sees the schema applied automatically, no editor-side configuration required. It is also taplo-compatible, so the file remains validatable if Helix's LSP setup ever pivots away from tombi.

A `[tool.tombi]` association block in `pyproject.toml` was considered as a fallback layer and rejected: the firm_config file is hand-edited in the repo by a single maintainer, never out-of-tree; the directive suffices and a fallback adds maintenance surface for a case that does not occur. Tombi's built-in schema catalog is also irrelevant — there is no published schema for our format; we own the only one.

### 13.4 Limitations (acknowledged, not deferred)

- **Cross-field constraints don't surface at edit time.** `single_soft < single_hard`, `joint_soft <= joint_hard`, and similar are model-level Pydantic validators (§8). JSON Schema can express them via `if/then/else`/`allOf` constructs but tombi's diagnostic quality on those is uncertain enough that the maintenance cost outweighs the editor-time benefit. They remain load-time errors. This is acceptable: cross-field violations are infrequent (the values change quarterly at most), the load-time message is precise, and the tests in §10.1 enforce the rule from the model side.
- **`trust_code_citation` is not pattern-validated.** Illinois Trust Code citations have legitimate format variation (chapter, act, section, et seq./et al., parenthetical year, abbreviation conventions). A regex that accepts the canonical Crosby-and-Crosby form would create false negatives more annoying than catching a typo. Field stays a plain `str` with a descriptive `Field(description="...")` that surfaces as hover text — letting tombi document the field at edit time without lying about its constraint.
- **Schema dialect.** Pydantic emits draft-2020-12. Tombi supports it. If tombi ever drops 2020-12 support, regenerate with `schema_dialect = "..."` on `TombiAwareGenerator`.
- **Float/Decimal-in-JSON-Schema corner.** TOML's `nan` and `inf` values do not validate as JSON-Schema `number`. Irrelevant here — none of the fields admit those values — but flagged for any future config that adds floating-point fields.

### 13.5 Freshness enforcement

The generated schema is checked into the repo so a fresh clone gets LSP support without running the generator. This creates drift risk: a model change without a regen produces a stale schema that lies to the editor.

**Mechanism: pytest test that regenerates in-memory and asserts byte-equality with the on-disk artifact** (the freshness test in §10.2). Failure prints both the missing and surplus content. Fix: re-run `pixi run python scripts/generate_firm_config_schema.py` and re-commit. Single canonical place to catch drift, no new dependency.

**Where the test runs.** The repo has no CI (no `.github/` directory exists at the time of this spec). The freshness test runs as part of the local test suite via `pixi run test`, which is included in the `pixi run check` aggregate task that also runs `lint` and `mypy`. The maintainer's discipline — running `pixi run check` before committing — is the enforcement boundary. If CI is added later, the test runs there automatically without spec changes; no special configuration needed.

Pre-commit hook approach considered and rejected on three grounds: (1) requires opt-in per-clone installation, fails open on fresh checkouts; (2) duplicates the test-suite check without adding coverage; (3) the regen is fast enough to fold into pytest setup if drift becomes routine, which would make the hook actively misleading.

### 13.6 Library reconnaissance summary

| Library                         | Role considered                          | Resolution      | Why                                                                                                              |
| ------------------------------- | ---------------------------------------- | --------------- | ---------------------------------------------------------------------------------------------------------------- |
| pydantic native (`model_json_schema`, `GenerateJsonSchema`, `Field(json_schema_extra=...)`, `WithJsonSchema`) | Schema source + customization        | adopt-direct    | Already in dep tree, emits draft-2020-12, native subclass mechanism handles vendor extensions, per-field colocation principle. |
| `pydantic-to-schema` (aorumbayev) | Pre-commit hook wrapping schema dump     | NOT adopted     | Last release 2020, no tombi-extension hook, wrapper thinner than what we need. We'd extend it to the point of replacement. |
| `check-jsonschema`              | CI-side TOML-against-schema validation   | NOT adopted     | Redundant with tombi (edit-time) and Pydantic (load-time); adds CI minutes without catching a different failure class. |
| `datamodel-code-generator`      | Schema → model generator                 | N/A             | Wrong direction.                                                                                                 |
| `json-schema-to-pydantic`       | Schema → model generator                 | N/A             | Wrong direction.                                                                                                 |
| `pydantic-extra-types`          | Custom field types                       | NOT adopted     | No firm_config field needs it; pydantic core covers `HttpUrl`, `Path`, `Decimal`, `Literal`.                     |

---

## Design decisions and scope additions

This section enumerates everything in the spec that is not directly traceable to an entity observation in the knowledge graph or to an explicit userMemories note. Each is a deliberate analytical decision made during spec authoring; none is implementation-discretion deferred to plan composition.

**Approved scope additions (confirmed with Zayn during authoring):**

1. **Editor schema generation subsystem** (§13 in full, §10.2 test bucket, §12 steps 7–10). Resolves the open-ended-TOML risk for a hand-edited config with mixed scalar formats. Approved before §13's revision pass.

**Inline design decisions (made by the author within scope):**

2. **`FirmConfigError` exception type** (§7). Required for fail-fast loader behavior; the alternative (raising raw `pydantic.ValidationError`) leaks library types into the loader's API contract.
3. **Dollar threshold types: `Decimal` → `int`** (§5.3). Whole-dollar precision is the legal reality at the millions scale; `int` emits as native JSON Schema `number` for tombi without an override. Refines the `estate_thresholds` entity's structural decisions; not a reframing.
4. **`approaching_cliff_ratio` type: `Decimal` → `float`** (§5.3, §13.2). Two significant digits derive no benefit from `Decimal`; thresholds are now `int`, eliminating the Decimal-arithmetic-protection argument; `float` skips one `WithJsonSchema` override.
5. **`SchemaNumber` type alias** (§13.2). Encapsulates the `Annotated[Decimal, WithJsonSchema(...)]` pattern for lat/lon and any future Decimal-as-number fields; prevents drift across multiple override sites.
6. **`[meta]` forward-compatibility seam** (§5.8, §11 question 2 struck). Scoped `extra="allow"` on `Meta` only; rest of `FirmConfig` remains `extra="forbid"`. Resolves the previously-deferred config-versioning question with two lines of Pydantic and zero user-facing impact today.
7. **Lat/lon caching dropped** (§5.1). The original "populated by geocoder on first resolve, cached" language contradicted §3's deferral of write paths to GUI scope. Coordinates now resolve on demand via geopy; persistent caching is deferred to a future spec if geocoder load proves measurable.
8. **`Address` import path: `trust_generator.v3.schema`** (§5.1, §12 step 4). The v3 namespace is established (verified at repo path `src/trust_generator/v3/schema.py`), and `schema.py` is step 1 of the v3 critical path per userMemories — it lands before firm_config implementation begins. Import preferred over redefinition to eliminate drift risk for a genuinely shared shape.
9. **Package placement: `src/trust_generator/v3/config/`** (§7, §12). The v3 namespace already exists in the repo; placing config under it matches the established convention.
10. **Test placement: `tests/v3/config/` and `tests/v3/integration/`** (§10, §12). Mirrors the source layout under the established `tests/v3/` namespace.
11. **`#:schema` directive insertion at migration time, not at artifact landing** (§12 step 6). Tombi degrades to a warning rather than an error on a missing schema reference, so the directive can land in its final position during the migration step without requiring a second edit later. Eliminates a needless touchpoint.
12. **`[tool.tombi]` fallback association rejected** (§13.3). The hand-edit-in-repo workflow makes the fallback layer YAGNI; the `#:schema` directive travels with the file and suffices.
13. **No-CI freshness enforcement model** (§13.5). Verified absence of `.github/` in the repo. The freshness test runs locally via `pixi run check`; the maintainer's pre-commit discipline is the enforcement boundary. Setup transparent to future CI adoption.
14. **Pixi-as-primary dep convention adopted in checklist** (§12 steps 3, 7). Verified from `pixi.toml`: runtime deps live under `[pypi-dependencies]` + `[package.run-dependencies]`; dev deps under `[feature.dev.dependencies]`. `pyproject.toml`'s `[project.dependencies]` is not the source of truth in this repo.
15. **`jsonschema >=4,<5` as a dev dependency** (§10.2, §12 step 7). Required by the round-trip validation test; explicitly excluded from runtime dependencies. Mainstream BSD-3 package; not flagged as recon.

**What does trace to the graph or userMemories:**

- `bounded_context_design` → §1 motivation, §3 scope, §5.1 Address shape note, §13.1 single-source-of-truth principle.
- `estate_thresholds` → §5.3 base structure, §11 (formerly question 2 about HB2601 pending status, now folded into §5.3 rationale).
- `corporate_trustee_catalog` → §5.4.
- `diagnostics_enforcement` → §5.5.
- `library_selections` → §3, §13.6 (the new pydantic-native + NOT-adopted entries are pending memory commit; see session-end note).
- userMemories `guardianship.default_policy` note → §5.6.
- userMemories Python 3.12+ floor and Pydantic v2.x preference → §7 imports and type-hint conventions throughout.

Anything not enumerated above and not in this trace list is either stylistic or implementation-discretion that the plan composition session can settle without analytical work.

---

## Post-finalization amendments

Amendments below were recorded during plan composition after the spec was marked Finalized. They resolve conflicts between the spec's authoring-time intent and the actual state of the codebase that the spec relies on. They are recorded here (rather than silently edited into the body) so the historical record of what was decided — and when — remains auditable.

### A-1 (2026-04-22): `Address` model reuse — honor the existing schema, not the §5.1 table

**Conflict:** Spec §5.1 lists `firm.office_address.zip` and types `firm.office_address.latitude`/`longitude` as `SchemaNumber` (a `Decimal`-based alias defined in §13.2). The shape note in §5.1 also directs the implementation to import `Address` from `trust_generator.v3.schema` rather than redefine it. The actual `Address` model at `src/trust_generator/v3/schema.py:264-275` exposes `zip_code: str` (not `zip`) and `latitude: float | None` / `longitude: float | None` (not `Decimal`). Spec §2 lists "Modifications to `schema.py`" as hard out-of-scope, so the conflict cannot be resolved by renaming or retyping the fields on the imported model.

**Resolution:** The `Address` import wins. TOML keys for the office address follow the imported model's field names (`zip_code`, not `zip`). Latitude and longitude remain `float` via the imported model; no `SchemaNumber` alias is introduced in firm_config, because no firm_config field requires `Decimal`. The §13.2 rationale for `SchemaNumber` is documented-for-future-use only and does not land in this implementation.

**Downstream effects:**

- §5.1 table row `firm.office_address.zip` → actual TOML key is `firm.office_address.zip_code`. The illustrative file layout in §6 is updated correspondingly (`zip_code = "61114"`, not `zip = "61114"`).
- §5.1 table rows `firm.office_address.latitude` / `longitude` → actual type is `float | None` (via imported `Address`), not `SchemaNumber`. JSON Schema emission for these fields is Pydantic's native `{"type": "number"}` for `float` — no override required.
- §13.2 adjustment 3 (`SchemaNumber` type alias) is not implemented in firm_config. The alias pattern remains documented in the spec for any future config field that needs `Decimal`-as-number; its introduction is deferred to that hypothetical spec.
- §10.2 schema-generation test "SchemaNumber coercion" is rewritten to assert that lat/lon emit `{"type": "number"}` via native `float` handling rather than via the `SchemaNumber` alias. The test's intent (tombi sees a validated number, not a string) is preserved; the mechanism changes.

**Rationale for this resolution over alternatives:**

- Defining a parallel `FirmAddress` model with `zip` + `SchemaNumber` lat/lon was rejected: it creates two `Address` shapes in v3, contradicts the spec's §5.1 "imports `Address`" directive, and invites drift because any future `Address` evolution would need to be mirrored by hand.
- Relaxing §2 to permit a narrow schema.py change (renaming `zip_code` → `zip`, retyping lat/lon) was rejected: it widens blast radius into other v3 callers that already use `Address.zip_code` and the `float` lat/lon (including the v3 schema test suite closed in plan `2026-04-21-schema-tests`), and the table text is not load-bearing enough to justify a boundary violation.
- The `SchemaNumber` work is not orphaned on rejection — it simply has no trigger in firm_config. If a later config field needs `Decimal`-as-number, §13.2's pattern is the first thing that spec reaches for.

**Confirmed:** 2026-04-22, Zayn.

### A-2 (2026-04-22): Integration tests assert config-surface contract only; consumer wiring deferred

**Conflict:** Spec §10.3 reads, in present tense, "The `trustee_catalog` refresh client **receives** its URL and timeout from the loaded config, not from hardcoded defaults" and "The diagnostics subsystem **reads** its default restriction level from the loaded config." The language implies the two consumer subsystems (a `trustee_catalog` refresh client and the diagnostics subsystem) already exist at implementation time and must be wired to `FirmConfig`. Neither subsystem exists in the v3 codebase at the time of plan composition; the `corporate_trustee_catalog` and `diagnostics_enforcement` entities reference future work that will land in separate specs.

**Resolution:** The integration tests cover the **config-surface contract** — they assert that a loaded `FirmConfig` instance exposes the exact values (`fdic_api_base`, `fdic_request_timeout_s`, `default_restriction_level`) that the future consumers will read. When those consumer subsystems land in their own specs, they pivot from constants to `cfg.trustee_catalog.*` / `cfg.diagnostics.*` and the integration tests grow assertions on consumer behavior at that time. This plan does not fabricate consumer code outside the firm_config scope.

**Downstream effects:**

- §10.3 bullets are satisfied by the config-surface tests for the purpose of this plan's acceptance gate.
- The firm_config implementation plan carries a scoped grep step (Task 11 Step 3) to confirm no pre-existing v3 code hardcodes values that `FirmConfig` now owns — if any are found, they are rewired as part of Task 11; if none are found, the clean-slate state is noted and consumer wiring is left to the future specs.

**Rationale for this resolution over alternatives:**

- Writing stub consumer subsystems inside the firm_config plan widens scope beyond §2 ("Out of scope: the trustee_catalog refresh client's implementation is governed by the `corporate_trustee_catalog` entity's own spec, forthcoming"). A stub introduces maintenance burden in the same release.
- Leaving §10.3 uncovered is unacceptable — the spec names these as acceptance criteria.
- The config-surface interpretation preserves the spirit of §10.3 (consumer-owned values live in `FirmConfig`, not in constants) while deferring the consumer-wiring mechanics to the specs that own them.

**Confirmed:** 2026-04-22, Zayn (via plan-review protocol disposition).

### A-3 (2026-04-22): Loader reads TOML via `tomllib` and passes payload as init-kwargs, not via `TomlConfigSettingsSource`

**Conflict:** Spec §7 internal-shape note reads, "The loader composes pydantic-settings sources explicitly via `settings_customise_sources` to force the precedence order declared above, overriding the library's default (which places file below env by default, which matches our intent, but we pin it to avoid surprises on library updates)." This implies the TOML file is routed through pydantic-settings' source machinery (`TomlConfigSettingsSource`). The plan's loader reads the TOML file directly with stdlib `tomllib`, then passes the parsed payload into `FirmConfig(**toml_data)` — so the TOML content rides the `InitSettingsSource` channel, not `TomlConfigSettingsSource`.

**Resolution:** The loader keeps the direct-tomllib approach. `settings_customise_sources` remains the precedence-pinning mechanism, but the sources in play are `(env_settings, init_settings, file_secret_settings)` — env overlays sit above the TOML payload (supplied as init-kwargs). The `deep_update` machinery inside pydantic-settings composes the env overlay on top of the TOML-derived init dict, satisfying the documented precedence env > TOML > defaults.

**Rationale for this resolution over the literal spec reading:**

- `TomlConfigSettingsSource` reads its path from class-level `model_config['toml_file']`. The loader's path is discovered at runtime (explicit arg → env var → default), so the "read the TOML" step cannot be driven by static class-level config without a per-load `FirmConfig` subclass — which is awkward, obscures the stack trace on failure, and is not a documented pydantic-settings idiom.
- The direct-`tomllib` path is trivially testable in isolation (parse errors surface as `TOMLDecodeError` → `FirmConfigError` with a precise message), which is what §8 (validation layers) ranks as the highest-priority failure mode.
- Env overlay still works end-to-end (verified in tests). The precedence contract in §7 is honored; only the mechanism for routing the TOML payload differs from the illustrative note.

**Downstream effects:**

- §7 internal-shape note is now historically accurate for its authoring intent; the implementation's actual mechanism is captured here.
- Future maintainers reading the loader and expecting `TomlConfigSettingsSource` will find this amendment via the cross-reference in the plan.

**Confirmed:** 2026-04-22, Zayn (via plan-review protocol disposition).

### A-4 (2026-04-24): Tilde expansion in loader path resolution

**Conflict:** Spec §5.5 declares the path-resolution contract as "Paths are resolved relative to the firm_config file's parent directory when given as relative paths. Absolute paths are used as-is." There is no provision for paths beginning with `~` (the Unix/Windows convention for the current user's home directory). The diagnostics-engine spec (`docs/superpowers/specs/2026-04-23-diagnostics-engine-design.md` §11.1) defines the audit-log destination as a per-user subfolder of a SharePoint library synced under `~/Crosby and Crosby LLP/...`. Without tilde expansion, the literal `~` would survive as a directory-name segment during relative-resolution, producing an unreachable path like `<cfg_parent>/~/Crosby.../...`.

**Resolution:** `load_firm_config()` applies `Path.expanduser()` to every `Path`-typed field before the existing relative-to-absolute transformation. The resolution order for each Path field becomes:

1. `Path.expanduser()` — expands a leading `~` against the current user's home directory. Paths without a leading tilde are unchanged by this step.
2. Resolve-relative — if the expanded path is still relative, join against the config file's parent directory.
3. `Path.resolve()` — canonicalize (symlink resolution, existing behavior).

**Downstream effects:**

- §5.5 path-resolution semantics gain the expanduser step. All three `Path`-typed fields in the schema (`trustee_catalog.db_path`, `diagnostics.audit_log_dir`, `diagnostics.rules_dir`) receive tilde-expansion uniformly — the change lives in the shared `_resolve_paths` helper rather than per-field.
- §7 `load_firm_config` docstring narrative and the loader's internal `_resolve` closure gain the new resolution step. Behavior for absolute-no-tilde paths is unchanged.
- §10.1 loader unit tests gain coverage for: tilde in `audit_log_dir` expands to `Path.home()`, expansion applies to all Path fields uniformly.

**Rationale for this resolution over alternatives:**

- Hardcoding the Windows profile directory (`C:\Users\<name>\...`) into `firm.toml` was rejected: it breaks workstation portability for a single `firm.toml` that the future shared-firm-config plan (deferred, `2026-04-23-shared-firm-config`) intends to host in the synced library.
- Scoping expanduser to only `audit_log_dir` was rejected: the cost of extending it to all Path fields is one line inside `_resolve`, and a future per-user field (e.g., a drafts cache) would otherwise re-open this decision.
- A custom `${HOME}` substitution sharing machinery with A-6's `${user.upn}` was rejected: `Path.expanduser()` is cross-platform stdlib (Windows `%USERPROFILE%`, POSIX `$HOME`) and the tilde idiom is the idiomatic form for hand-edited config files.

**Confirmed:** 2026-04-24, Zayn.

### A-5 (2026-04-24): New `[user]` section with required `upn` field

**Conflict:** Spec §5 enumerates the firm_config schema but has no surface for per-workstation user identity. The diagnostics-engine spec (`docs/superpowers/specs/2026-04-23-diagnostics-engine-design.md` §11.2) requires an M365 UPN prefix to attribute audit-log records and to form the per-user subfolder path of the synced SharePoint library. Deriving the UPN from the OS (`whoami`, `%USERNAME%`) was rejected in the diagnostics-engine spec on environmental-trust grounds; the value must be explicitly set in the firm_config file per workstation.

**Resolution:** A new `[user]` table is added to the firm_config schema with one required field:

```toml
[user]
upn = "zramdass"   # M365 account prefix; non-empty string
```

The field is validated as non-empty at load time via `Field(min_length=1)` on a new `User(BaseModel)` nested model. Format validation (tenant-specific M365 policy conformance) is explicitly the onboarding workflow's responsibility and is NOT enforced by `load_firm_config()`. Pre-onboarding deployments hand-set the value during installation; the paralegal-onboarding plan (deferred, `2026-04-23-paralegal-onboarding`) will populate it programmatically when it lands.

**Downstream effects:**

- §5 gains an effective §5.9 entry for `[user]` — defined here by reference; the narrative section-5 tables are not edited in-place per the amendment-as-authoritative convention established by A-1.
- §6 illustrative file layout gains a `[user] upn = "zramdass"` block immediately after `[meta]` and before `[firm]`.
- §7 `FirmConfig` composition gains a required `user: User` field (no default, no factory). A missing `[user]` section raises `FirmConfigError` at load time via Pydantic's required-field machinery.
- §8 validation layer 2 (field-level) gains the `upn` non-empty check.
- §9 migration table gains a `(not in v2) → [user].upn` row; v2 had no concept of per-workstation user identity.
- §10.1 loader unit tests gain coverage for: `upn` loaded correctly, missing `[user]` rejected, empty `upn` rejected, whitespace-only `upn` rejected (strip-then-`min_length=1`).
- A new `User(BaseModel)` class lives in `src/trust_generator/v3/config/firm.py` alongside the other nested models and is re-exported from `trust_generator.v3.config.__init__` for symmetry with the other sections.
- **Backward compatibility break.** Any `firm.toml` file authored before this amendment will fail to load with `FirmConfigError` until a `[user] upn = "..."` block is added. Acceptable for pre-release v3.0.0 with a single active deployment; the maintainer hand-sets the value during the deployment step that lands this amendment. Post-release, the paralegal-onboarding workflow (deferred) owns the programmatic population mechanism.
- **Accepted residual risk: path-traversal via malformed UPN.** The load-time non-empty gate does not prevent a malformed UPN (e.g., `"../../etc"`) from being substituted into `audit_log_dir` at A-6 time, producing a resolved path outside the intended subtree. In the single-maintainer, pre-onboarding threat model this is defensible — the maintainer authors the UPN by hand. The deferred onboarding workflow (diagnostics-engine spec §12.1) is the correct venue for format-level validation; adding regex-shape validation here would duplicate the tenant-policy check that workflow must perform against an authoritative source.

**Rationale for this resolution over alternatives:**

- Placing the UPN under `[firm]` was rejected: `[firm]` represents firm identity (shared across workstations); per-workstation fields belong in their own table.
- Stronger `upn` format validation at load time (regex, M365-policy shape) was rejected: formats vary across tenants and drift over time; source-of-truth validation belongs to the onboarding workflow. The load-time strip+non-empty gate is a sanity check against silent-corruption vectors, not a format contract.
- An optional `[user]` with a sentinel default (e.g., `upn = "unknown"`) was rejected: the field is load-bearing for A-6 substitution and for audit-log attribution; a sentinel would silently produce misleading audit records. Fail-fast on missing `[user]` is the safer default and matches the `firm.name` required-field precedent.

**Confirmed:** 2026-04-24, Zayn.

### A-6 (2026-04-24): `${user.upn}` post-parse substitution in `diagnostics.audit_log_dir`

**Conflict:** The diagnostics-engine spec (`docs/superpowers/specs/2026-04-23-diagnostics-engine-design.md` §11.1, §11.2) specifies a per-user-subfolder audit-log destination whose prefix is the UPN. Two mechanisms were considered for composing this path:

1. TOML-native string interpolation — impossible; TOML has no interpolation syntax.
2. Caller-side path composition — the audit writer joins a base directory from `firm.toml` with `config.user.upn` at write time.

Option 2 splits the resolved path across two sources (config file + writer code), making it harder for a deployment engineer to verify the final path by inspecting `firm.toml` alone.

**Resolution:** The loader performs a literal-string replacement of `${user.upn}` with the validated `[user] upn` value in `diagnostics.audit_log_dir`, after Pydantic validation and before the A-4 expanduser + relative-resolve passes. The substitution is explicitly NOT a TOML language feature; it is a two-operand `str.replace()` call inside `_resolve_paths`, keyed on a module-level `_USER_UPN_SENTINEL` constant.

The full resolution order for `diagnostics.audit_log_dir` becomes:

1. Substitute `${user.upn}` with `cfg.user.upn` (A-6).
2. `Path.expanduser()` (A-4).
3. Resolve-relative against the config file's parent if still relative.
4. `Path.resolve()` canonicalize.

**Downstream effects:**

- §5.5 `diagnostics.audit_log_dir` gains substitution semantics alongside the tilde-expansion from A-4. Other Path fields (`diagnostics.rules_dir`, `trustee_catalog.db_path`) do NOT receive substitution; the sentinel is scoped to `audit_log_dir` only. A literal `${user.upn}` appearing in any other Path field survives unchanged into the resolved path.
- §6 illustrative `audit_log_dir` value changes from `"./logs/audit"` to the production value:
  `"~/Crosby and Crosby LLP/internal-applications - trust-generator/users/${user.upn}/logs"`
- §7 loader narrative documents the new substitution pass as the first step of `_resolve_paths`.
- §10.1 loader unit tests gain coverage for: substitution in `audit_log_dir`, substitution NOT applied to other Path fields, resolution order (substitute → expanduser → resolve-relative), absolute-with-sentinel still substitutes correctly.
- A module-level constant `_USER_UPN_SENTINEL: Final[str] = "${user.upn}"` is introduced in `firm.py` alongside `_resolve_paths` to avoid magic-string duplication.

**Rationale for this resolution over alternatives:**

- Caller-side path composition (Option 2 above) was rejected: it splits the path's definition across `firm.toml` and the audit writer's code. A deployment engineer inspecting `firm.toml` should see the shape of the resolved path, not a base-directory-only placeholder that requires reading writer source to understand.
- Supporting substitution in all Path fields was rejected as premature generalization: no other field today motivates it, and an implicit sentinel across all fields would become surface that future field additions have to re-evaluate.
- Using a TOML-compliant placeholder syntax (e.g., `"<<upn>>"` or `"%upn%"`) was rejected: `${name}` is the ubiquitous convention across shell, env files, Helm charts, SystemD unit files, and CI configs; inventing a novel delimiter would surprise maintainers without technical benefit.
- Performing substitution AFTER expanduser was rejected: a hypothetical UPN containing a literal `~` would then be mis-expanded. Substitute-first preserves the UPN's literal content before any path-level transformation runs.

**Confirmed:** 2026-04-24, Zayn.

### A-7 (2026-04-28): Two-source loader for shared + local firm config

The loader described in §3–§5 of this spec resolves a single TOML file
from the discovery chain and parses it. As of the
`2026-04-28-shared-firm-config-design` spec, the loader is restructured to
resolve and merge TWO TOML files: a shared firm-wide file (read-mostly,
hosted on SharePoint) and a local per-workstation file (writable, lives on
the user's machine). The merged dict feeds into the same Pydantic
validation pass; `FirmConfig`'s schema is unchanged.

Key contract changes:

- `load_firm_config()` signature changes from `load_firm_config(path=None)`
  to `load_firm_config(local_path=None, shared_path=None)`. The legacy
  `path=` keyword is no longer accepted.
- The shared file's discovery chain mirrors the local file's chain:
  explicit arg → `TGV3_FIRM_SHARED_CONFIG` env var →
  `CONVENTIONAL_SHARED_CONFIG_PATH` constant.
- A cache layer at `%LOCALAPPDATA%/trust-generator/firm.shared.cache.toml`
  (Windows) or `${XDG_CACHE_HOME:-~/.cache}/trust-generator/firm.shared.cache.toml`
  (POSIX) provides continuity when SharePoint sync is unavailable. Cache
  fallbacks emit a `SharedConfigStalenessWarning`.
- The merge contract specifies recursive deep-merge with EXTEND semantics
  for lists (shared-first, verbatim concatenation), empty-as-unset for
  empty TOML literals, and Pydantic-deferred type-mismatch handling.

For the full contract, see
`docs/superpowers/specs/2026-04-28-shared-firm-config-design.md`.

**Confirmed:** 2026-04-29, Zayn.
