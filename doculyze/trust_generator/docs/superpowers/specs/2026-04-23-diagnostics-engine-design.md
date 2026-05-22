# TGv3 Diagnostics Engine Design

| Field             | Value                                                                                                                                                       |
| ----------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Spec date         | 2026-04-23                                                                                                                                                  |
| Status            | Finalized (amended 2026-04-24 — §14 added: downstream plan split formalization)                                                                             |
| Supersedes        | n/a (new subsystem)                                                                                                                                         |
| Relevant entities | `diagnostics_design`, `diagnostics_enforcement`, `rule_engine_binding`, `estate_thresholds`, `python_stack_commitments`, `bounded_context_design`           |
| Out of scope      | GUI rules pane (Session 4.1); generator-side integration of `diagnose()` (Session 2.2); full production rule set; firm-level rule-toggle table in `firm.toml`; paralegal onboarding workflow (deferred; see §12); shared firm-config distribution (deferred; see §12) |

## 1. Motivation

TGv3 produces legal documents whose correctness depends on facts the Pydantic schema cannot enforce on its own: distribution shares must sum to 100%, estate values approaching the Illinois cliff demand tax-planning attention, OCR-derived fields can carry unverified placeholder values into otherwise-valid trust data. These are computed observations, not validation errors — they vary in severity, they live at different points in the workflow (fill / generate / both), and they need an audit trail when an attorney chooses to override them.

This spec defines the diagnostic engine: the `diagnose()` function, the rule loader and evaluator that drive declarative paralegal-authored rules through the `rule-engine` library, the audit log writer that records overrides, the override flow itself, three starter rules — one per `DiagnosticSource` — that demonstrate the engine end-to-end, and the audit log persistence layer that routes firm-side override records to a shared SharePoint library via the OneDrive sync client.

## 2. Scope

### In scope

- `diagnose(trust, config, *, ref_date) -> list[Diagnostic]` entry point.
- `build_eval_context(trust, config, ref_date) -> dict` — derived rule-evaluation context.
- `DiagnosticRule` Pydantic wrapper around `rule_engine.Rule`.
- Rule loader: builtin (in-repo, packaged) + custom (firm-side, GUI-authored). Rule construction at load time (not at first evaluation).
- Code-namespace conventions, code-collision detection, and dedupe semantics.
- Audit log writer: JSON-lines, monthly rotation, per-user subfolder structure.
- `force_generation()` override flow.
- Three starter rules: `shares.sum_not_100`, `estate.crossed_cliff`, `extraction.placeholder_unfilled`.
- Audit log persistence: routing records to a shared SharePoint library via the OneDrive sync client, including the `firm.toml` fields required to resolve the user-scoped write path.
- Deployment requirements for the persistence layer (per-workstation sync setup).

### Out of scope (enforced)

- **GUI rules pane** — Session 4.1 owns paralegal-facing rule authoring UI. This spec defines only the YAML on-disk format the GUI will read and write.
- **Generator integration of `diagnose()`** — Session 2.2 owns the wiring of `diagnose()` into the document generator's pre-emit checkpoint. This spec defines the function and its contract; calling it from the generator is downstream work.
- **Full production rule set** — three starter rules ship with v3 to demonstrate each `DiagnosticSource` category. Production rules accumulate over time as the firm encounters edge cases.
- **Firm-level rule-toggle table in `firm.toml`** — YAGNI given the firm's single config-maintainer model. Per-rule `enabled: bool` in the YAML rule definitions is the v3 disable mechanism. A `firm.toml` override layer can be added if a future operational need surfaces.
- **Paralegal onboarding workflow** — the mechanism by which `firm.toml` `[user] upn` gets populated on each workstation. This spec specifies the *reader contract* for that field; the workflow that populates it is deferred to its own session. See §12.
- **Shared firm-config distribution** — hosting `firm.toml` in the synced SharePoint folder with tiered permissions is a substantive change to the firm-config spec's load contract. Deferred to its own session. See §12.

## 3. Reference material

A claude-code session composing the implementation plan should load the following before writing any code.

### 3.1 Memory entities (open via `memory:open_nodes`)

| Entity                       | Why                                                                                                          |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------ |
| `diagnostics_design`         | Diagnostic Pydantic class shape; code-namespace convention (`<domain>.<n>`); the never-stored, always-computed contract. |
| `diagnostics_enforcement`    | Production blocking semantics; override flow; audit log shape; per-rule toggle.                              |
| `rule_engine_binding`        | Library coupling rationale; integration shape (`DiagnosticRule` wrapper); debug REPL availability.           |
| `estate_thresholds`          | Cliff structure (single/joint, soft/hard, approaching ratio); values come from `firm_config`, not constants. |
| `python_stack_commitments`   | Pydantic v2.x; stdlib `datetime.date`; PEP 695 type alias runtime non-identity.                              |
| `bounded_context_design`     | `diagnose()` consumes `TrustData` (post-fill canonical), not `QuestionnaireSeed`.                            |

### 3.2 Source files (read before authoring)

| Path                                              | Why                                                                                                              |
| ------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `src/trust_generator/v3/schema.py`                | `Diagnostic`, `DiagnosticLevel`, `DiagnosticSource`, `DiagnosticContext` already defined here. `TrustData` computed properties (`collected_total_value`, `beneficiary_shares_total`, etc.) — these are the rule expressions' attack surface. |
| `src/trust_generator/v3/config/firm.py`           | `FirmConfig.diagnostics.audit_log_dir`, `rules_dir` — already absolute after `load_firm_config()` resolves them. `EstateThresholds` shape consumed by `estate.crossed_cliff` rule. §11 adds a `[user] upn` field and tilde-expansion to path resolution, both of which extend this module. |
| `config/firm.toml`                                | Concrete production values: confirms threshold magnitudes, `audit_log_dir` and `rules_dir` defaults. §11 updates this file's `audit_log_dir` to the SharePoint-synced location and adds a `[user]` section. |
| `docs/superpowers/specs/2026-04-21-firm-config-design.md` | §5.5 and §7 define the path-resolution mechanism this spec extends with tilde expansion. §12.8 step 6 is where the new `[user]` section lands. |

### 3.3 External references

- `rule-engine` getting-started: <https://zerosteiner.github.io/rule-engine/getting_started.html> — authoritative for `Context`, `type_resolver_from_dict`, `resolve_item` vs `resolve_attribute` semantics.
- `rule-engine` syntax: <https://zerosteiner.github.io/rule-engine/syntax.html> — operator reference for rule authors and reviewers.

## 4. Library reconnaissance: `rule-engine` (BSD-3, PyPI)

The graph entity `rule_engine_binding` records `rule-engine` as the rule-evaluation library and notes its safe-grammar guarantee (no `eval`/`exec`). This recon refines the resolution from `adopt-direct` (the entity's original framing) to **`wrap`**, with the wrap surface being `build_eval_context()` and the `DiagnosticRule` Pydantic model. The reasons:

1. **Multi-object context.** Rule expressions need to mix `TrustData` and `FirmConfig` symbols in a single boolean expression — e.g., comparing `elections.estate_value_approximate` (TrustData) against `estate_thresholds.single_hard` (FirmConfig). Neither object provides this combined surface; the wrap composes it.
2. **Computed-property exposure.** `TrustData.collected_total_value`, `beneficiary_shares_total`, and `withdrawal_schedule_total` are useful rule operands, but `model_dump()` strips Python `@property` values (Pydantic only serializes `@computed_field` properties, which these are not). Re-adding `@computed_field` decorators would change schema.py output and breach this spec's hard out-of-scope on schema.py modification. The wrap injects them by direct `getattr`.
3. **Reference-date dependency.** Minor-status determination requires a reference date that is not stored on `TrustData`. The wrap accepts `ref_date` and pre-computes any reference-date-dependent helpers (`minor_beneficiaries`) into the context dict so rule expressions don't need to reach for time directly.
4. **Resolver uniformity.** `resolve_attribute` (rule-engine's attribute-backed resolver) doesn't traverse method calls on Pydantic models. Routing everything through `model_dump(mode='python')` plus injected helpers gives rule expressions a uniform `dict`-shaped surface, allowing the default `resolve_item` resolver — no custom Context resolver needed.
5. **Type-resolver posture.** `rule-engine`'s static type checking is opt-in per symbol via a `dict[str, DataType]` resolver. Top-level symbols (`trust`, `firm`, `now`) are declared `DataType.UNDEFINED` in v1 — sufficient to catch unknown-symbol typos, deferred on per-leaf type tightening until the rule corpus motivates the discipline. Recorded as an open seam (§7).
6. **Rule construction failure surface.** `rule_engine.Rule(expression, context=...)` can raise `RuleSyntaxError` (malformed grammar), `RegexSyntaxError` (broken `=~` pattern), and `AttributeResolutionError` (malformed attribute access) at *construction* time, not at evaluation. The loader compiles every rule immediately after Pydantic validation so these failures surface as `DiagnosticConfigError` at load time with the file and rule-code identified. Runtime-only failures (`SymbolResolutionError`, `EvaluationError`) remain handled by the evaluator as meta-diagnostics.

The `rule_engine_binding` entity gains observations recording these refinements (see graph edits at end of session).

## 5. Architecture overview

The diagnostic engine is composed of five units that compose into a single entry point. Each unit is small enough to test in isolation. Section 6 gives the test-first construction order; this section is the reference shape that all cycles target.

### 5.1 The `diagnose()` entry point

```python
# src/trust_generator/v3/diagnostics/engine.py

from __future__ import annotations

from datetime import date

from trust_generator.v3.schema import Diagnostic, TrustData
from trust_generator.v3.config.firm import FirmConfig
from trust_generator.v3.extraction.trace import ExtractionTrace


def diagnose(
    trust: TrustData,
    config: FirmConfig,
    *,
    ref_date: date | None = None,
    extraction: ExtractionTrace | None = None,
) -> list[Diagnostic]:
    """Compute diagnostics for a TrustData against a FirmConfig.

    Pure function: no I/O, no side effects, no caller-visible state mutation.
    Determinism: rules execute in load order (builtin first, custom second);
    the returned list preserves that order. When ``extraction`` is supplied,
    trace-driven Diagnostics from ``synthesize_extraction_diagnostics`` (§5.7)
    precede rule-driven Diagnostics in the returned list — see OCR spec §5.8
    and §6.7 for the full rationale.

    ``ref_date`` is the reference date for time-dependent rule context
    (today, minor-beneficiary computation). Default resolution chain:
    explicit argument -> ``trust.trust_id.execution_date`` -> ``date.today()``.
    The resolved date is exposed as ``ctx["now"]`` to rule expressions.

    ``extraction`` is an optional ``ExtractionTrace`` produced by an
    ``ExtractionProtocol`` backend (OCR spec §5.4); when supplied, the trace
    is exposed under the ``extraction`` namespace in ``ctx`` (see §5.2) and
    drives an additional emission source via the §5.7 synthesis seam.
    """
```

Semantic commitments:

- **Pure.** `diagnose()` does not write the audit log, does not mutate `trust` or `config`, does not perform I/O during evaluation. The audit log is written only inside `force_generation()` (§5.6).
- **Deterministic.** Rules execute in `(builtin_load_order, custom_load_order)` sequence. The diagnostic list preserves that order. Tests can rely on positional indexing.
- **Reference-date contract.** The fallback chain is fixed and documented above. Callers needing reproducibility (e.g., test suites, the future GUI's "preview at execution date" feature) pass `ref_date` explicitly.
- **Trace-driven seam.** When `extraction` is supplied, `synthesize_extraction_diagnostics(trust, extraction)` (§5.7) is called as a second emission source. Its output prepends the rule-evaluated list, so the returned shape is `(trace_driven, builtin_load_order, custom_load_order)`. Callers MUST tolerate either an empty or non-empty trace-driven prefix; rule-driven indices are not stable across calls with and without `extraction`.

### 5.2 Eval context (`build_eval_context`)

```python
def build_eval_context(
    trust: TrustData,
    config: FirmConfig,
    ref_date: date,
    *,
    extraction: ExtractionTrace | None = None,
) -> dict:
    """Compose the dict that rule expressions evaluate against.

    Shape: nested under three top-level namespaces so rule expressions
    read like ``trust.elections.estate_value_approximate >
    firm.estate_thresholds.single_hard``. When ``extraction`` is supplied,
    a fourth conditional namespace ``extraction`` is added — see OCR spec
    §5.9 and §5.7 below.
    """
```

Returned shape:

```python
{
    "trust": {
        # ... trust.model_dump(mode='python') ...
        # plus injected computed properties:
        "collected_total_value": Decimal,
        "beneficiary_shares_total": Decimal,
        "withdrawal_schedule_total": Decimal,
        "disinherited_beneficiaries": list[dict],
        "excluded_persons": list[dict],
        "minor_beneficiaries": list[dict],   # pre-computed at ref_date
    },
    "firm": {
        # ... config.model_dump(mode='python') ...
    },
    "now": date,        # the resolved ref_date
    # Conditional — present iff ``extraction`` was supplied to ``diagnose()`` /
    # ``build_eval_context``. When absent, YAML rules referencing
    # ``extraction.*`` must guard with ``extraction != null and ...`` to
    # avoid ``engine.symbol_unknown``. Cross-ref: OCR spec §5.9.
    "extraction": {
        # ... extraction.model_dump(mode='python') with enums unwrapped ...
        "fields": list[dict],          # one per FieldExtraction
        "backend_id": str,
        "extracted_at": datetime,
        "verified_at": datetime | None,
    },
}
```

Notes:

- `model_dump(mode='python')` preserves `Decimal`, `date`, and `Enum` instances as native Python objects. `rule-engine` consumes `Decimal` and `date` directly via its `FLOAT` (numbers) and `DATETIME` (dates and datetimes) data types; `Enum` instances are explicitly unwrapped to their `.value` by `build_eval_context` (see the next bullet) before reaching rule-engine, so the rule-engine `STRING` type sees plain strings.
- Six keys land in the `trust` namespace beyond the base `model_dump()` output. Five arrive via the `COMPUTED_PROPERTIES` getattr loop (§6.3); the sixth (`minor_beneficiaries`) is injected separately because it requires `ref_date` as an argument. New computed properties on `TrustData` require manual addition to this injection set — the deliberate cost of avoiding the `@computed_field` decoration churn on `schema.py`.
- `minor_beneficiaries` is the only ref-date-dependent injection. Other reference-date-aware logic should follow the same pattern: pre-compute in `build_eval_context`, expose as a flat key.
- Enum values: Pydantic v2 `model_dump(mode='python')` returns enum instances, not their string values. For `str`-mixin enums like `TrustType(str, Enum)` the instance is-a `str` via inheritance and Python-level `==` against a string literal works, but rule-engine bypasses Python's `__eq__` and coerces the operand via `str()`, which for a `str`-mixin Enum returns the enum repr (`'TrustType.INDIVIDUAL'`), not the value (`'individual'`). `build_eval_context` therefore applies an explicit `_unwrap_enums()` helper that walks the dumped trust- and firm-namespace dicts and replaces every `Enum` instance with its `.value`. This is load-bearing for the `estate.crossed_cliff` rule's `trust.trust_id.trust_type == "individual"` clause; Cycle 2 includes a rule-engine roundtrip test pin.

### 5.3 Rule organization, namespaces, and file layout

Rules live in two locations with distinct ownership:

| Class    | Location                                                              | Authored by             | Distribution            |
| -------- | --------------------------------------------------------------------- | ----------------------- | ----------------------- |
| Builtin  | `src/trust_generator/v3/diagnostics/rules/builtin.yaml` (one file)    | Maintainer              | Shipped with the package |
| Custom   | `<firm_config.diagnostics.rules_dir>/*.yaml` (one rule per file)      | Paralegals (via GUI, Session 4.1) | Firm-side, host-local |

**Code namespace.** Builtin codes use `<domain>.<n>` (e.g., `estate.crossed_cliff`). Custom codes use `custom.<topic>.<n>` (e.g., `custom.intake.spousal_consent_missing`). The loader rejects any builtin entry whose code starts with `custom.`, and any custom entry whose code does not start with `custom.`. Promotion of a custom rule to a builtin is a deliberate maintainer step: the rule is moved into `builtin.yaml`, its code is rewritten to drop the `custom.` prefix, and the next bundled update ships it. The previously-custom file remains on the host until the next dedupe run drops it (§5.4).

**YAML rule schema:**

```yaml
- code: shares.sum_not_100
  level: error              # info | warning | error
  source: schema            # schema | business_rule | extraction
  context: both             # fill | generate | both
  message: "Beneficiary shares must sum to 100%."
  field_path: beneficiary_shares    # optional; dotted path into TrustData for GUI anchor
  expression: "trust.beneficiary_shares != [] and trust.beneficiary_shares_total != 100"
  enabled: true             # default true
```

`builtin.yaml` is a YAML list of these entries. Each custom file accepts either a YAML list (one or more entries) or a single YAML mapping (one entry); the loader normalizes the latter to a one-element list internally. Supporting both shapes preserves downstream freedom for Session 4.1's GUI to pick whichever serialization form it prefers without the loader becoming the constraint.

### 5.4 Dedupe and collision semantics

Two distinct checks run at load time:

**Code collision (identity).** The loader builds a dict of `{code: (filename, rule)}` as rules are loaded. A duplicate code within the builtin set, within the custom set, or across the two sets raises `DiagnosticConfigError` naming both source locations. Codes are identity; two rules with the same code is a configuration error regardless of their expressions.

**Expression dedupe (behavior).** After code-collision detection passes, a custom rule is silently dropped when its `(normalized_expression, level)` tuple matches any already-loaded builtin rule. Normalization in v1 is whitespace-stripping (`"".join(expression.split())`); AST-based normalization via `rule-engine`'s parser is an open seam (§7).

Builtin always wins on expression dedupe. Rationale: a custom rule that survives a builtin-promotion bundled update has either (a) the same semantics as the builtin, in which case dropping it is correct, or (b) different semantics caused by the paralegal modifying it after authoring, in which case the expression strings differ and the dedupe key doesn't match — both rules survive, which is correct.

The loader emits a structured log entry (Python `logging` at `INFO` level) for each dropped rule, naming the custom file and the conflicting builtin code. Dropped rules do not appear in the audit log; the audit log is reserved for runtime override events (§5.5), not load-time bookkeeping.

### 5.5 Audit log

Format: JSON Lines (`.jsonl`). One record per `force_generation()` invocation.

Record shape:

```json
{
  "timestamp": "2026-04-23T14:44:25.123-05:00",
  "user": "zramdass",
  "trust_ref": "F-2026-0042",
  "overridden_codes": ["estate.crossed_cliff", "shares.sum_not_100"],
  "reason": "Client confirmed estate value with attorney 2026-04-22; shares total intentional 99.5% with 0.5% in side letter to charity.",
  "restriction_level": "error"
}
```

Field semantics:

- `timestamp` — ISO 8601 with timezone offset; written via `datetime.datetime.now().astimezone().isoformat()`. Naive datetimes are not permitted (open seam: timezone-config awareness is deferred).
- `user` — the M365 UPN prefix, sourced from `config.user.upn`. Set per-workstation in `firm.toml`; populated by the future onboarding workflow (§12) or hand-set during pre-onboarding deployment.
- `trust_ref` — derived from `trust.office.file_number`. If empty, falls back to `"unidentified"`. The audit record exists to be human-correlatable; `unidentified` is a flag for "the trust file lacked an internal reference at override time".
- `overridden_codes` — the list of `Diagnostic.code` values that triggered the block.
- `reason` — caller-supplied free-text justification. `force_generation()` rejects empty strings and strings shorter than 10 non-whitespace characters (a soft guard against `"ok"`-style ceremonial text).
- `restriction_level` — the effective restriction threshold at override time, for forensic reproduction of the policy in effect.

Path resolution: `<config.diagnostics.audit_log_dir>/audit-YYYY-MM.jsonl`. The directory is already absolute by the time `load_firm_config()` returns (with tilde-expansion applied; see §11). `YYYY-MM` is derived from the write timestamp (monthly rotation per `diagnostics_enforcement` entity). Files are opened in append mode; a new month creates a new file on first write.

Concurrent-write isolation is achieved structurally: `audit_log_dir` is itself a per-user subfolder of the synced SharePoint library (see §11), so no two workstations ever target the same path. This eliminates the Windows `O_APPEND`-over-SMB interleaving risk that a shared file would expose.

### 5.6 Override flow

The override is a two-step API. `diagnose()` returns observations; `force_generation()` records an authorized override.

```python
def force_generation(
    trust: TrustData,
    config: FirmConfig,
    diagnostics: list[Diagnostic],
    *,
    reason: str,
) -> AuditRecord:
    """Record an authorized override of blocking diagnostics.

    Validates ``reason`` (>= 10 non-whitespace characters). Writes one
    JSON-line record to the audit log directory derived from
    ``config.diagnostics.audit_log_dir``. Returns the written record so
    the caller can echo or display it.

    The attributed user is sourced from ``config.user.upn``. The caller
    does not pass a user — identity is a property of the workstation's
    firm_config, not a per-call argument. This prevents accidental
    misattribution at the call site and ensures every override record
    on a given workstation carries the same user identity.

    Does not mutate ``trust``, ``config``, or ``diagnostics``. Does not
    re-run ``diagnose()``. The caller is responsible for filtering
    ``diagnostics`` to the codes actually being overridden.
    """
```

The split is deliberate: `diagnose()` is pure and re-runnable, suitable for live GUI feedback; `force_generation()` is the side-effecting commitment. A caller that wants to know "would override succeed?" without writing the record can validate `reason` itself via the exposed `validate_override_reason(reason: str) -> None` module-level helper.

`AuditRecord` is a Pydantic model defined in `diagnostics/audit.py` (not in `schema.py` — it is a diagnostics-internal concern, not a trust-data concern).

### 5.7 Trace-driven Diagnostic synthesis (9c)

Rule-driven evaluation handles `TrustData`-as-a-whole properties (cross-field invariants, business-rule cliffs, structural shape). Trace-driven synthesis handles per-field extraction concerns (illegibility, low confidence, no normalized value) sourced from an `ExtractionTrace`. Both emission sources merge into the single `list[Diagnostic]` returned by `diagnose()`; the seam is an architectural split, not a workaround.

The full rationale, the contract for `synthesize_extraction_diagnostics(trust, extraction) -> list[Diagnostic]`, and the three new `extraction.*` codes (`extraction.illegible_field`, `extraction.low_confidence_field`, `extraction.no_normalized_value`) are specified in OCR spec §5.8 and §7.7. Stale entries (a `field_path` that no longer resolves) are silently filtered; verified entries are suppressed; the function returns a fresh list and never mutates inputs.

Merge order: trace-driven Diagnostics precede rule-driven Diagnostics in the returned list (OCR spec §5.8 last paragraph).

## 6. Implementation: TDD cycles

The implementation follows the red-green-refactor discipline with one outer cycle and eight inner cycles. The outer cycle (§6.2) is the integration test for `diagnose()` and stays red until the inner cycles complete; closing the last inner cycle naturally turns it green. Each cycle's `Red` describes the failing test and its location, `Green` describes the production code that makes it pass referencing §5 for shape, and `Refactor` describes post-green polish.

### 6.1 Cycle ordering and dependency graph

```
Cycle 1 (outer, integration)  ──┐
                                │
  Cycle 2 (build_eval_context) ─┤
  Cycle 3 (rule loader)         ├──> all green => Cycle 1 green
  Cycle 4 (rule evaluator) ─────┤
  Cycle 5 (audit log writer) ───┤
  Cycle 6 (override flow) ──────┤
  Cycle 7 (rule: shares) ───────┤
  Cycle 8 (rule: estate) ───────┤
  Cycle 9 (rule: extraction) ───┘

Inner dependencies:
  Cycle 4 depends on the eval-context shape from Cycle 2
  Cycle 6 depends on the writer from Cycle 5
  Cycles 7-9 depend on Cycle 4 (evaluator must exist to assert rule firing)
```

Recommended construction order: **2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 1 verifies green**. Cycle 1's test exists from the start (red); it is checked at the end as a confirmation that the inner cycles compose correctly.

### 6.2 Cycle 1 — `diagnose()` entry point integration test (outer)

**Red.** Author `tests/v3/diagnostics/test_diagnose.py::test_diagnose_triggers_all_starter_rules`. The test:

1. Loads a `FirmConfig` from a test fixture TOML.
2. Synthesizes a `TrustData` crafted to trigger all three starter rules:
   - `beneficiary_shares` totaling 99% (triggers `shares.sum_not_100`).
   - `elections.estate_value_approximate = Decimal("5_000_000")` and `trust_id.trust_type = INDIVIDUAL` (triggers `estate.crossed_cliff` against `single_hard = 4_000_000`).
   - `text_blocks.statement_of_intent = "[OCR_LOW_CONFIDENCE]"` (triggers `extraction.placeholder_unfilled`).
3. Calls `diagnose(trust, config, ref_date=date(2026, 4, 23))`.
4. Asserts the returned list has length 3 with codes `{"shares.sum_not_100", "estate.crossed_cliff", "extraction.placeholder_unfilled"}` and matching levels and sources per §6.8–6.10.

The test fails initially because `trust_generator.v3.diagnostics.engine` does not exist. Commit this red test as the contract.

**Green.** Implement `diagnose()` per §5.1: build the eval context, load and cache rules, evaluate each rule, return the diagnostic list. The implementation is a thin coordinator — all real work lives in the inner-cycle units.

```python
def diagnose(trust, config, *, ref_date=None):
    resolved_ref_date = ref_date or trust.trust_id.execution_date or date.today()
    ctx = build_eval_context(trust, config, resolved_ref_date)
    rules = load_rules(config)
    diagnostics: list[Diagnostic] = []
    for rule in rules:
        result = rule.evaluate(ctx)
        if result is not None:
            diagnostics.append(result)
    return diagnostics
```

**Refactor.** If `load_rules()` is called once per `diagnose()` invocation in production, that's acceptable (small N), but a per-`FirmConfig` cache (`functools.lru_cache(maxsize=8)` keyed on `id(config)`) eliminates redundant disk reads. Defer until profiling shows it matters; document the caching seam in code comments.

### 6.3 Cycle 2 — `build_eval_context`

**Red.** Author `tests/v3/diagnostics/test_eval_context.py` covering:

1. **Shape.** Returned dict has top-level keys `{"trust", "firm", "now"}`.
2. **Trust namespace.** `ctx["trust"]["grantor"]["full_legal_name"]` matches the input model field.
3. **Firm namespace.** `ctx["firm"]["estate_thresholds"]["single_hard"]` matches the loaded config value.
4. **Computed-property injection.** With three `BeneficiaryShare` entries summing to 99, `ctx["trust"]["beneficiary_shares_total"]` equals `Decimal("99")`.
5. **`now` resolution (explicit).** Explicit `ref_date=date(2026, 1, 1)` → `ctx["now"] == date(2026, 1, 1)`.
6. **Ref-date fallback chain.** Wrapped in `freezegun.freeze_time("2026-04-23")`: `ref_date=None` and `trust.trust_id.execution_date = date(2026, 6, 15)` → `ctx["now"] == date(2026, 6, 15)`. With both unset, `ctx["now"] == date(2026, 4, 23)` exactly.
7. **Minor injection.** A child with DOB making them 17 as of `ref_date` appears in `ctx["trust"]["minor_beneficiaries"]`; an adult does not.
8. **Enum value pin.** With `trust_id.trust_type = TrustType.JOINT`, `ctx["trust"]["trust_id"]["trust_type"] == "joint"` evaluates True (and equivalently `!= "individual"`) at the Python level, AND `rule_engine.Rule('trust.trust_id.trust_type == "joint"').matches(ctx)` returns True (with the `"individual"` variant returning False). The rule-engine roundtrip assertion guards against regressions where the `_unwrap_enums()` helper is removed — Python-level equality alone would still pass via `str`-mixin inheritance, masking the rule-engine breakage.

**Green.** Implement `build_eval_context()` per §5.2:

```python
COMPUTED_PROPERTIES = (
    "collected_total_value",
    "beneficiary_shares_total",
    "withdrawal_schedule_total",
    "disinherited_beneficiaries",
    "excluded_persons",
)

def build_eval_context(trust, config, ref_date):
    trust_dict = trust.model_dump(mode="python")
    for prop in COMPUTED_PROPERTIES:
        value = getattr(trust, prop)
        # Lists of Pydantic models need recursive dump for rule access:
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
        "trust": trust_dict,
        "firm": config.model_dump(mode="python"),
        "now": ref_date,
    }
```

**Refactor.** Extract the property-injection loop into `_inject_computed(model, dump, prop_names)` if a second consumer needs the same pattern. Otherwise inline.

### 6.4 Cycle 3 — Rule loader

**Red.** Author `tests/v3/diagnostics/test_rule_loader.py` covering:

1. **Builtin loads.** `load_rules(config)` includes a known builtin (`shares.sum_not_100` from §6.8) when `builtin.yaml` is present.
2. **Custom loads.** A custom rule file at `<rules_dir>/custom_test_rule.yaml` with code `custom.test.foo` appears in the loaded list.
3. **Empty rules_dir.** A `rules_dir` with no files yields only builtins, no error.
4. **Missing rules_dir.** A `rules_dir` that does not exist on disk yields only builtins, no error (loader treats absent dir as empty).
5. **Builtin namespace enforcement.** A builtin entry with code `custom.illegal` raises `DiagnosticConfigError` naming the file and code.
6. **Custom namespace enforcement.** A custom file containing a rule with code `estate.illegal` (no `custom.` prefix) raises `DiagnosticConfigError`.
7. **Expression dedupe (positive).** A custom rule with the same `(whitespace-stripped expression, level)` as a builtin is dropped from the returned list and produces a `logging.INFO` entry naming both.
8. **Expression dedupe (negative — level differs).** A custom rule with the same expression but a different `level` is NOT dropped.
9. **Malformed YAML.** A custom file containing invalid YAML raises `DiagnosticConfigError` quoting the parser error and the file path.
10. **Schema mismatch.** A YAML entry missing `code` (required field) raises `DiagnosticConfigError` quoting the Pydantic validation error.
11. **Single-mapping form.** A custom file containing a single YAML mapping (not a list) parses as one rule.
12. **Duplicate code within builtins.** Two entries in `builtin.yaml` sharing the same `code` raise `DiagnosticConfigError` naming both file offsets.
13. **Duplicate code across files.** Two custom files each defining `custom.foo.bar` raise `DiagnosticConfigError` naming both file paths.
14. **Malformed rule expression (syntax).** A custom rule with expression `"trust.x ===== 1"` (invalid grammar) raises `DiagnosticConfigError` at load time with the file, code, and parser error. Does not defer to first evaluation.
15. **Malformed rule expression (regex).** A custom rule with expression `'trust.name =~ "[unclosed"'` raises `DiagnosticConfigError` at load time.
16. **Missing builtin.yaml.** If the packaged `builtin.yaml` is absent (simulated via `importlib.resources` patching), the loader raises `DiagnosticConfigError` with a message identifying the expected resource.
17. **Unreadable custom file.** A custom file that raises `IOError` on read (simulated via permission manipulation or patched `open()`) surfaces as `DiagnosticConfigError` naming the file and the OS error.

**Green.** Implement `load_rules(config: FirmConfig) -> list[DiagnosticRule]`:

```python
def load_rules(config):
    builtin = _load_builtin_rules()              # may raise DiagnosticConfigError
    _enforce_namespace(builtin, allow_custom=False)
    _enforce_no_code_collisions(builtin)
    _compile_expressions(builtin)                # may raise DiagnosticConfigError
    custom = _load_custom_rules(config.diagnostics.rules_dir)
    _enforce_namespace(custom, allow_custom=True)
    _enforce_no_code_collisions(custom)
    _enforce_no_cross_code_collisions(builtin, custom)
    _compile_expressions(custom)
    custom = _dedupe_against(custom, builtin)
    return [r for r in (*builtin, *custom) if r.enabled]
```

`DiagnosticRule` is a Pydantic model:

```python
class DiagnosticRule(BaseModel):
    code: str
    level: DiagnosticLevel
    source: DiagnosticSource
    context: DiagnosticContext = DiagnosticContext.BOTH
    message: str
    field_path: str | None = None
    expression: str
    enabled: bool = True
```

`_compile_expressions` iterates the rule list, attempts `rule_engine.Rule(rule.expression, context=_build_rule_context())` for each, and wraps `RuleSyntaxError`, `RegexSyntaxError`, and `AttributeResolutionError` as `DiagnosticConfigError` with the originating file and rule code attached. The compiled `rule_engine.Rule` instance is attached to the `DiagnosticRule` via a `PrivateAttr` so the evaluator does not re-compile.

`_dedupe_against` builds a `set[tuple[str, DiagnosticLevel]]` from builtin entries (keys: `("".join(r.expression.split()), r.level)`) and filters custom entries against it, logging each drop.

`DiagnosticConfigError` is defined in `diagnostics/errors.py`. It is the loader's only failure mode; runtime evaluation errors yield meta-diagnostics (Cycle 4), not exceptions.

**Refactor.** Pull the dedupe key construction into a `_dedupe_key(rule) -> tuple` function for unit-testability. Document `_dedupe_key` as the AST-normalization seam (§7).

### 6.5 Cycle 4 — Rule evaluator

**Red.** Author `tests/v3/diagnostics/test_rule_evaluator.py` covering:

1. **Match.** A `DiagnosticRule` with expression `"trust.beneficiary_shares_total != 100"` evaluated against a context where `trust.beneficiary_shares_total == 99` returns a `Diagnostic` with the rule's code/level/source/context/message/field_path.
2. **No match.** Same rule against context where total is 100 returns `None`.
3. **Disabled.** A rule with `enabled=False` returns `None` regardless of expression match.
4. **Symbol unknown.** An expression referencing `trust.nonexistent_field` yields a meta-diagnostic with code `engine.symbol_unknown`, source `SCHEMA`, level `WARNING`, message naming the rule code and the unknown symbol. The original rule does not crash the run.
5. **Eval error.** An expression with a type mismatch (e.g., `trust.grantor.full_legal_name + 1`) yields a meta-diagnostic with code `engine.eval_error`, source `SCHEMA`, level `WARNING`.
6. **Compiled-rule identity (no re-parse).** The `DiagnosticRule._compiled` attribute is populated by the loader, not by the evaluator. The evaluator accesses it directly; asserting that `evaluate()` does not mutate `_compiled` between two successive calls pins the no-re-parse contract. (Loader-side Cycle 3 test 14 covers failure-at-construct-time.)

**Green.** Implement `DiagnosticRule.evaluate(self, ctx: dict) -> Diagnostic | None`:

```python
class DiagnosticRule(BaseModel):
    # ... fields as in §6.4 ...
    _compiled: rule_engine.Rule | None = PrivateAttr(default=None)

    def evaluate(self, ctx):
        if not self.enabled:
            return None
        if self._compiled is None:
            # Loader guarantees compilation; this branch is a defensive
            # safeguard that should never execute in production.
            raise RuntimeError(f"DiagnosticRule {self.code!r} was not compiled by loader")
        try:
            matched = self._compiled.matches(ctx)
        except rule_engine.errors.SymbolResolutionError as exc:
            return _meta_diagnostic("engine.symbol_unknown", self.code, exc.symbol)
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

`_meta_diagnostic(code, rule_code, detail)` constructs a `Diagnostic` with `level=WARNING`, `source=SCHEMA`, `context=BOTH`, message `"Rule {rule_code} failed at engine evaluation: {detail}"`, and `field_path=None`.

The rule-engine `Context` is constructed by the loader via `_build_rule_context()`:

```python
def _build_rule_context():
    type_resolver = rule_engine.type_resolver_from_dict({
        "trust": rule_engine.DataType.UNDEFINED,
        "firm": rule_engine.DataType.UNDEFINED,
        "now": rule_engine.DataType.DATETIME,
    })
    return rule_engine.Context(type_resolver=type_resolver)
```

**Refactor.** If meta-diagnostic construction grows, extract into a small helper class. Verify that `now` typed as `DATETIME` doesn't reject `date` objects passed in the context — `rule-engine` accepts `date` and treats it as `DATETIME` at midnight (per docs §"Literal Values"); add a test to pin this if uncertain.

### 6.6 Cycle 5 — Audit log writer

**Red.** Author `tests/v3/diagnostics/test_audit_log.py` covering:

1. **Write produces file.** First write to a clean `audit_log_dir` creates `audit-YYYY-MM.jsonl` (where YYYY-MM matches a `freezegun.freeze_time` value).
2. **JSON-line shape.** The written line, parsed as JSON, has keys `{timestamp, user, trust_ref, overridden_codes, reason, restriction_level}` and values matching the input record.
3. **Append.** A second `write()` appends a second line; the file has exactly two lines.
4. **Monthly rotation.** A `write()` at `freeze_time("2026-04-30T23:59:00")` writes to `audit-2026-04.jsonl`; a `write()` at `freeze_time("2026-05-01T00:00:00")` writes to `audit-2026-05.jsonl`.
5. **Path is absolute.** Constructor accepts a `Path` and does not modify it; writes open against that absolute path.
6. **Atomic write per line.** Concurrent writes (simulated via two `AuditLog` instances against the same dir) do not interleave bytes within a single record. (On POSIX, `O_APPEND` is atomic for writes ≤ `PIPE_BUF`. On Windows, the per-user subfolder structure in §11 guarantees concurrent writes from different users target different files, so cross-user interleaving cannot occur; this test exercises the same-user same-machine case which is rare but handled via stdlib `open()` defaults.)

**Green.** Implement `AuditLog`:

```python
# src/trust_generator/v3/diagnostics/audit.py

from datetime import datetime
from pathlib import Path
from pydantic import BaseModel

class AuditRecord(BaseModel):
    timestamp: datetime
    user: str
    trust_ref: str
    overridden_codes: list[str]
    reason: str
    restriction_level: str

class AuditLog:
    def __init__(self, dir: Path):
        self.dir = dir

    def write(self, record: AuditRecord) -> Path:
        self.dir.mkdir(parents=True, exist_ok=True)
        filename = f"audit-{record.timestamp:%Y-%m}.jsonl"
        path = self.dir / filename
        line = record.model_dump_json() + "\n"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line)
        return path
```

`AuditRecord.model_dump_json()` emits ISO 8601 timestamps natively (Pydantic v2 default for `datetime`). The path is returned so callers can log or display where the record landed.

**Refactor.** Decide on `mkdir(parents=True, exist_ok=True)` placement: per-write (resilient to dir deletion mid-run) or once per `AuditLog` instance (faster). Per-write wins on robustness at negligible cost (one `stat` call). Document the timezone-naive vs. timezone-aware open seam (§7).

### 6.7 Cycle 6 — Override flow

**Red.** Author `tests/v3/diagnostics/test_override.py` covering:

1. **Happy path.** Synthesize a TrustData triggering an error. Run `diagnose()`, get the diagnostic. Call `force_generation(trust, config, [diagnostic], reason="...")`. Assert returned `AuditRecord` has the expected fields (including `user` sourced from `config.user.upn`) and an audit file now exists with one line matching the record.
2. **Empty reason rejected.** `reason=""` raises `ValueError`.
3. **Short reason rejected.** `reason="ok"` raises `ValueError` (< 10 chars after strip).
4. **Missing UPN rejected at load.** A `firm.toml` with `[user] upn = ""` fails `load_firm_config()` validation. (This test lives adjacent in the firm-config test suite per §11, referenced here for completeness.)
5. **Trust ref fallback.** `trust.office.file_number == ""` produces `trust_ref="unidentified"` in the written record.
6. **Codes preserved.** Multiple diagnostics yield an `overridden_codes` list in the same order.
7. **No mutation.** `trust`, `config`, and the input `diagnostics` list are unchanged after the call.

**Green.** Implement `force_generation()`:

```python
def force_generation(
    trust: TrustData,
    config: FirmConfig,
    diagnostics: list[Diagnostic],
    *,
    reason: str,
) -> AuditRecord:
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


def validate_override_reason(reason: str) -> None:
    if len(reason.strip()) < 10:
        raise ValueError(
            "force_generation requires a reason of at least 10 non-whitespace characters"
        )
```

`validate_override_reason` is exposed at module level so a future GUI can call it for live form validation before the user clicks "Override".

### 6.8 Cycle 7 — Starter rule: `shares.sum_not_100` (source: SCHEMA)

**Red.** Author `tests/v3/diagnostics/test_starter_rules.py::test_shares_sum_not_100` covering:

1. **Triggers when non-empty and != 100.** Three shares totaling 99 → exactly one diagnostic with code `shares.sum_not_100`, level `ERROR`, source `SCHEMA`.
2. **Silent on empty.** Zero shares → no diagnostic.
3. **Silent on exactly 100.** Three shares totaling 100 → no diagnostic.
4. **Decimal precision.** Shares of `Decimal("33.33")`, `Decimal("33.33")`, `Decimal("33.34")` (sum 100.00) → no diagnostic. Shares of `Decimal("33.33")`, `Decimal("33.33")`, `Decimal("33.33")` (sum 99.99) → diagnostic fires.

**Green.** Add to `src/trust_generator/v3/diagnostics/rules/builtin.yaml`:

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

**Why source `SCHEMA`.** This is a structural invariant on `TrustData` that Pydantic does not enforce (Pydantic validates each `BeneficiaryShare` in isolation; the cross-entry sum is a list-level invariant outside Pydantic's per-field model). It's the canonical example of a `SCHEMA`-source rule: structural, not policy-driven.

**Refactor.** Verify `rule-engine`'s numeric semantics: `Decimal("100")` from `trust.beneficiary_shares_total` compared to literal `100` in the expression — `rule-engine` coerces both to `FLOAT`. At three-share precision the comparison is exact; at deeper precision (more shares with finer fractions) drift is theoretically possible but irrelevant for this rule's typical use. Document.

### 6.9 Cycle 8 — Starter rule: `estate.crossed_cliff` (source: BUSINESS_RULE)

**Red.** Author `test_starter_rules.py::test_estate_crossed_cliff` covering:

1. **Individual trust above single_hard.** `trust_type=INDIVIDUAL`, `estate_value_approximate=Decimal("4_500_000")`, `single_hard=4_000_000` → one diagnostic with code `estate.crossed_cliff`, level `WARNING`, source `BUSINESS_RULE`.
2. **Individual trust below single_hard.** Same shape with `estate_value_approximate=Decimal("3_500_000")` → no diagnostic.
3. **Joint trust above joint_hard.** `trust_type=JOINT`, `estate_value_approximate=Decimal("9_000_000")`, `joint_hard=8_000_000` → diagnostic fires.
4. **Joint trust between single_hard and joint_hard.** `trust_type=JOINT`, `estate_value_approximate=Decimal("5_000_000")` → no diagnostic (joint threshold applies, not single).
5. **Null estimate.** `estate_value_approximate=None` → no diagnostic (rule cannot fire without a value).

**Green.** Add to `builtin.yaml`:

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

**Why level `WARNING`, not `ERROR`.** Crossing the cliff is not an invalidating condition — clients with high-value estates legitimately exist. The diagnostic flags that the document needs additional tax-planning provisions; that is attorney attention, not a hard block. Hard-block (`ERROR`) is reserved for conditions that would render the trust document itself defective.

**Why source `BUSINESS_RULE`.** Threshold values come from the firm's interpretation of Illinois statute; the firm changes them when legislation moves (per `estate_thresholds` entity). This is policy, not structure — the canonical `BUSINESS_RULE` shape.

**Refactor.** The `trust.trust_id.trust_type == "individual"` comparison relies on `build_eval_context`'s `_unwrap_enums()` helper, which explicitly replaces `Enum` instances with their `.value` so rule-engine sees a plain string (verified by Cycle 2 test 8's rule-engine roundtrip).

### 6.10 Cycle 9 — Starter rule: `extraction.placeholder_unfilled` (source: EXTRACTION)

**Red.** Author `test_starter_rules.py::test_extraction_placeholder_unfilled` covering:

1. **Triggers on placeholder.** `text_blocks.statement_of_intent = "[OCR_LOW_CONFIDENCE]"` → one diagnostic with code `extraction.placeholder_unfilled`, level `WARNING`, source `EXTRACTION`, context `FILL`.
2. **Silent on empty.** `statement_of_intent = ""` → no diagnostic.
3. **Silent on real text.** `statement_of_intent = "I, John Doe, declare..."` → no diagnostic.
4. **Embedded placeholder.** `statement_of_intent = "preamble [OCR_LOW_CONFIDENCE] tail"` → diagnostic fires (regex matches anywhere in the string).

**Green.** Add to `builtin.yaml`:

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

**Caveat on this starter.** The OCR pipeline (Tier 4, Sessions 4.3a–4.3c) will define and emit the placeholder marker. Until that lands, this rule is a documentation-by-shape artifact: it demonstrates the EXTRACTION-source pattern (a rule that fires on extraction-pipeline-derived markers) and provides the canonical placeholder convention `[OCR_LOW_CONFIDENCE]` for the OCR session to adopt. The rule trigger is structurally narrow (one field) by design — generalization to "scan all extraction-prone text fields" is an open seam (§7).

**Why source `EXTRACTION`.** The diagnostic fires because of an artifact of the extraction process, not because of structural or business invariants. The `DiagnosticSource` taxonomy is about the origin of the *concern*, not the origin of the *value*; a placeholder injected by OCR raises an extraction-origin concern even when the placeholder string itself is structurally valid.

**Refactor.** Cycle close-out: re-run Cycle 1's integration test. It should now be green: all three starter rules fire on the synthesized TrustData, producing the expected three-diagnostic list.

### 6.11 Cycle 10 — Trace-driven synthesis (9c)

Implementation lives in OCR spec §6.7 and is exercised by the synthesis cycle in OCR plan `2026-04-27-ocr-protocol-ollama-9c.md` (cycles 9c-1 and 9c-2; integration test 9c-3).

No rule-engine YAML rules were added by this cycle. The three new `extraction.*` codes (`extraction.illegible_field`, `extraction.low_confidence_field`, `extraction.no_normalized_value`) are constructed directly inside `synthesize_extraction_diagnostics` and bypass the YAML loader's `_enforce_namespace` check — that gate guards rule-engine-evaluated rules, not direct `Diagnostic` instances. The pre-existing `extraction.placeholder_unfilled` rule (§6.10) remains a YAML-driven builtin; the new codes coexist with it (OCR spec §7.7 paragraph 3).

## 7. Open seams

These are intentionally unimplemented in v3, captured as anchored future work:

- **Firm-level rule toggle in `firm.toml`.** Per-rule `enabled` in YAML is the v3 disable mechanism. If operational pressure surfaces (multiple paralegals needing per-host overrides without YAML edits), add a `[diagnostics.rules]` table to `firm.toml` mapping rule-code → bool, layered above the YAML `enabled` field.
- **AST-based dedupe normalization.** v1 strips whitespace. AST normalization via `rule-engine.Rule.is_valid()` + traversal would catch `(a + b)` vs `a+b` and `a == b` vs `b == a` as duplicates. Defer until a duplicate-but-not-detected case is observed in practice.
- **Type-resolver tightening.** Top-level symbols are `UNDEFINED` in v1. As the rule corpus grows, declare typed leaf symbols (e.g., `trust.elections.estate_value_approximate: FLOAT`) for the most-referenced paths to catch type errors at rule-load time rather than rule-evaluation time.
- **Message templating.** Messages are static strings in v1. A post-evaluation interpolation pass (e.g., `f"... ({ctx.eval(self.message_template)})"`) would let rules reference computed values in their messages. Defer until a starter rule motivates it.
- **Generalized extraction-source rule.** The `extraction.placeholder_unfilled` starter inspects one field. A generalization that scans all extraction-prone text fields requires either an injected `_all_extraction_strings: list[str]` in the eval context or a per-field-list rule format. Defer to the OCR-integration sessions (4.3a–4.3c).
- **Audit log timezone awareness.** v1 uses `datetime.now().astimezone()` which respects the host's local timezone. Multi-timezone firm operation would require a `firm_config.diagnostics.audit_log_timezone` field. Out of scope per §2.
- **Audit log fsync semantics.** v1 relies on stdlib `open()` defaults. A firm that requires guaranteed durability across kernel-level crashes can add `os.fsync(fh.fileno())` after each write at the cost of throughput.
- **GUI surfacing of dropped custom rules.** The dedupe loader logs drops to Python `logging`. The future GUI rules pane (Session 4.1) should surface these to the paralegal so they understand why their custom rule is no longer firing after a bundled update.
- **Sync latency between write and cloud availability.** The writer's `write()` call returns after local `fh.close()`; the OneDrive sync client uploads asynchronously. During offline operation, records queue locally until reconnect. Incident-triage readers inspecting the SharePoint web view during an outage will not see the most recent records until sync completes. Out of scope; documented so investigators understand the behavior.
- **UPN collision risk at onboarding.** The audit-log subfolder is keyed on `config.user.upn` with no uniqueness enforcement. If two paralegals are configured with the same UPN (deployment error), their audit records commingle in the same subfolder. The future onboarding workflow (§12) should validate UPN uniqueness against a canonical source before accepting it.
- **Tamper-evidence.** JSONL records are unsigned and editable by anyone with SharePoint write permission on the subtree. For malpractice-defense purposes this is acceptable (the records exist and are difficult-but-not-impossible to alter); for regulatory contexts requiring provable integrity, a HMAC signature chain or WORM storage would be required. Out of scope.

## 8. Testing summary

The cycles above define the test surface in full. Test files land at:

```
tests/v3/diagnostics/
    test_diagnose.py             # Cycle 1: outer integration
    test_eval_context.py         # Cycle 2
    test_rule_loader.py          # Cycle 3
    test_rule_evaluator.py       # Cycle 4
    test_audit_log.py            # Cycle 5
    test_override.py             # Cycle 6
    test_starter_rules.py        # Cycles 7, 8, 9
```

A test in `tests/v3/diagnostics/conftest.py` provides shared fixtures: a synthetic `FirmConfig` instance with overridable fields (including a populated `[user] upn`), a `TrustData` factory that defaults to the minimal shape and accepts kwargs to inject the three rule-triggering states.

Per the project's TDD principle, each cycle's `Red` tests are committed before the corresponding `Green` implementation. A test that doesn't appear in §6 is either a missing acceptance criterion (add it during plan composition) or a scope creep (reject it).

## 9. Implementation file layout

```
src/trust_generator/v3/diagnostics/
    __init__.py              # public re-exports: diagnose, force_generation, DiagnosticConfigError
    engine.py                # diagnose()
    eval_context.py          # build_eval_context()
    loader.py                # load_rules(), DiagnosticRule, DiagnosticConfigError
    evaluator.py             # DiagnosticRule.evaluate (lives on the model)
    audit.py                 # AuditRecord, AuditLog, force_generation(), validate_override_reason()
    errors.py                # DiagnosticConfigError exception
    rules/
        builtin.yaml         # the three starter rules + future builtins
```

Note: `evaluator.py` may be unnecessary if `DiagnosticRule.evaluate` lives on the model in `loader.py`. Resolve during Cycle 4 implementation; the spec does not pin module-internal organization.

## 10. Dependencies

Add to `pixi.toml` `[pypi-dependencies]` and `[package.run-dependencies]`:

- `rule-engine >=4.5,<5` — core. Released April 2026, BSD-3, Python 3.12-compatible per the recon page.
- `pyyaml >=6,<7` — YAML rule file loader. (Or `ruamel.yaml >=0.19,<0.20` if comment-preservation on the GUI's write path becomes a near-term concern; the loader's read path is library-agnostic. Default to `pyyaml` for the read-only loader.)

Add to `pixi.toml` `[feature.dev.dependencies]` (or equivalent dev slot):

- `freezegun >=1.5,<2` — time-freezing for Cycle 2 ref-date fallback tests and Cycle 5 monthly-rotation tests. Dev-only; runtime code uses `datetime.now()` and `date.today()` unmocked.

## 11. Audit log persistence and access

The audit log's readers (incident-triage investigators) are not necessarily on the machine that wrote the record. Persistence must deliver records from the writing workstation to a location readable by any authorized investigator. This section defines the persistence mechanism, the `firm.toml` surface it requires, and the per-workstation deployment steps that must complete before the diagnostic engine can run.

### 11.1 Destination and mechanism

Destination: shared SharePoint document library provisioned at:

```
https://crosbycrosbyllp.sharepoint.com/sites/internal-applications/Shared%20Documents/trust-generator/
```

Mechanism: the OneDrive sync client mounts the `trust-generator` folder (a Teams-backed channel folder under the `internal-applications` Team's SharePoint site) as a local directory on each paralegal workstation. Local resolved path:

```
~/Crosby and Crosby LLP/internal-applications - trust-generator/users/<upn>/logs/audit-YYYY-MM.jsonl
```

where `~` expands to the current user's Windows profile directory, and `<upn>` is the paralegal's M365 account prefix (e.g., `zramdass`). Per-user subfolders guarantee that no two workstations ever write to the same file — the I-4 Windows `O_APPEND`-over-SMB interleaving risk is structurally eliminated, not guarded against.

**Why Path A (sync client) over Path B (Microsoft Graph API).** Adopting the sync client keeps the writer's code identical to a local-disk write: stdlib `open('a')` against a `Path`, no authentication, no retry logic, no credential rotation. The sync client handles upload asynchronously and queues records when offline. The tradeoff — the sync client's conflict-resolution policy becomes a failure mode — is eliminated by the per-user subfolder structure, which prevents any conflict from arising in the first place. Path B would be the correct answer only if we required server-side atomicity guarantees the sync client does not provide; we do not.

**Why user subfolders over host-prefixed filenames.** Two reasons. First, SharePoint permissions apply at the folder level naturally — granting an investigator read access to the whole `users/` subtree is one permission assignment; granting read access to filenames matching `audit-*-<someone>.jsonl` across a shared folder requires external tooling. Second, the subfolder structure anticipates future per-user synchronized artifacts (drafts, custom rules) landing alongside logs under `users/<upn>/`, preserving a stable organization without reshape work later.

### 11.2 `firm.toml` surface

This spec requires the firm-config spec to gain the following fields. These are additions to `src/trust_generator/v3/config/firm.py` and `config/firm.toml` beyond what the firm-config spec originally defined.

**New `[user]` section (required):**

```toml
[user]
upn = "zramdass"   # M365 account prefix; non-empty string; used for audit-log attribution and path resolution
```

Validation: `upn` must be non-empty. Format validation (e.g., matching an M365 policy) is the onboarding workflow's responsibility and is not enforced by `load_firm_config()`. Pre-onboarding deployments hand-set this to a distinct test value (`"user"`, or the maintainer's own UPN) to produce unambiguous audit records.

**Updated `diagnostics.audit_log_dir` semantics:**

The existing `diagnostics.audit_log_dir` field gains tilde-expansion at load time. `load_firm_config()` calls `Path(value).expanduser()` during path resolution, prior to the existing relative-path-to-absolute transformation. The production value in `config/firm.toml` becomes:

```toml
[diagnostics]
audit_log_dir = "~/Crosby and Crosby LLP/internal-applications - trust-generator/users/${user.upn}/logs"
```

The `${user.upn}` interpolation is **not** a new TOML feature; TOML does not support string interpolation. Instead, the loader performs a post-parse substitution: after loading the TOML and validating `[user] upn`, the loader replaces the literal substring `${user.upn}` in `diagnostics.audit_log_dir` with the validated UPN value, then applies tilde-expansion.

**Why post-parse substitution over caller-side construction.** The alternative is keeping `audit_log_dir` as a literal path without substitution, and having `force_generation()` construct the final path at write time from `config.user.upn` and a separate base directory. Rejected: that splits the path's definition across two places (config and code), making it harder for a deployment engineer to verify the resolved path by inspecting `firm.toml`. Post-parse substitution keeps the config file the single source of truth for the resolved path, with the substitution rule documented in the firm-config spec's amendment.

### 11.3 Deployment requirements

The diagnostic engine cannot write records on a workstation where the SharePoint library is not synced. The following per-workstation setup is a prerequisite; the future paralegal-onboarding workflow (§12) will automate verification of these steps.

1. **Library sync.** Navigate to `https://crosbycrosbyllp.sharepoint.com/sites/internal-applications/Shared Documents/trust-generator/` in a browser, click the Sync button in the SharePoint toolbar, accept the OneDrive sync client prompt. Verify the local path `~/Crosby and Crosby LLP/internal-applications - trust-generator` exists.
2. **"Always keep on this device."** Right-click the synced `trust-generator` folder in File Explorer; select "Always keep on this device." This prevents OneDrive from converting files to online-only placeholders that would break `open('a')` append semantics by triggering per-access downloads.
3. **`.jsonl` extension allowlist verification.** Create a test file `test.jsonl` in the synced folder. Wait 60 seconds. Verify it appears in the SharePoint web view. Delete. If the file does not sync, the tenant-level extension allowlist is blocking it; escalate to the M365 administrator or fall back to `.log` extension (JSONL content is unaffected by filename extension).
4. **`firm.toml` `[user] upn` set.** Add the paralegal's M365 account prefix to their workstation's `firm.toml`. Pre-onboarding, this is hand-set by the maintainer.
5. **User subfolder creation.** The writer creates `users/<upn>/logs/` on first override if it does not exist (via `Path.mkdir(parents=True, exist_ok=True)` in `AuditLog.write()`). No manual setup of the subfolder is required.

### 11.4 Reader access

Incident triage proceeds by opening the SharePoint site in a browser, navigating to `trust-generator/users/<upn>/logs/`, and inspecting `audit-YYYY-MM.jsonl` for the relevant month. The SharePoint web view renders `.jsonl` as plain text with line-by-line JSON records; each line is a complete override event.

Glob-style queries across users ("all overrides in April 2026") are supported by SharePoint's search but are not the primary triage pattern. The primary pattern is: a concern surfaces about a specific trust; the investigator identifies which paralegal prepared it; they open that paralegal's subfolder.

Readers require SharePoint read permission on the `trust-generator/users/` subtree. By default, members of the `internal-applications` Team have this access. Non-Team-member attorneys (e.g., a partner performing compliance review) require explicit sharing.

## 12. Deferred scope

Two scopes surfaced during this session's context-gathering but fall outside the diagnostic engine proper. They are recorded here so they can be tracked in the project roadmap and `plans.xml` post-finalization; the maintainer is responsible for formalizing roadmap entries.

### 12.1 Paralegal onboarding workflow

**Problem.** §11 requires each workstation's `firm.toml` to carry a valid `[user] upn` value and a synced SharePoint library. Pre-onboarding, the maintainer hand-sets these during deployment. As the firm scales, hand-set configuration becomes a bottleneck and an error surface.

**Scope shape.** A first-run workflow that runs when the application starts on a workstation where onboarding has not completed. Prompts the paralegal for their M365 UPN prefix (or validates against a source of truth if one exists); verifies SharePoint library sync status; writes the validated UPN into `firm.toml`; marks onboarding complete. Re-runs on detection of UPN drift (e.g., paralegal account renamed).

**Dependencies.** Shares firm-config mutation surface with §12.2 — if both workflows write to `firm.toml`, they must agree on a write mechanism.

**Target completion.** v3.0.0 (pre-release).

### 12.2 Shared firm-config distribution

**Problem.** Each workstation currently maintains its own `firm.toml`. When estate thresholds change (HB2601 enactment, for example), the maintainer must propagate the change to every workstation. Error-prone and slow.

**Scope shape.** Host a canonical `firm.toml` in the synced SharePoint library at `trust-generator/firm/config/`. Each workstation reads from the synced location as its primary source; per-workstation `firm.toml` carries only workstation-local fields (the `[user]` section from §11). The firm-config loader merges the two, with the per-workstation values overlaying the shared defaults for overlapping keys. Write access to the shared file is restricted to the maintainer via SharePoint permissions; paralegals have read-only access.

**Dependencies.** Requires post-finalization amendment to the firm-config spec (`2026-04-21-firm-config-design.md`) documenting the new merge contract. Must coordinate with §12.1 on `firm.toml` mutation.

**Target completion.** v3.0.0 (pre-release).

## 13. Pre-planning chores

Before the implementation plan for this spec can be finalized, the plan-composition session must complete the following chores. These are obligations this spec creates on the firm-config spec (`docs/superpowers/specs/2026-04-21-firm-config-design.md`, currently Finalized) and must land as post-finalization amendments to that spec before the diagnostics implementation begins. The chores are actionable work items, not reading material; §3 covers the reading list.

### 13.1 Why these chores exist

§11 of this spec specifies audit log persistence in terms of three `firm.toml` surfaces that do not currently exist: a `[user]` section with a `upn` field, tilde expansion in path resolution, and loader-side `${user.upn}` post-parse substitution in `diagnostics.audit_log_dir`. Without these surfaces, the diagnostics writer has no populated path to open. The firm-config spec is the authoritative source for what `firm.toml` contains and how `load_firm_config()` resolves paths; adding these surfaces requires amending that spec, not this one.

Handling these as post-finalization amendments to the firm-config spec (analogous to the A-3 amendment already present in that spec) keeps the firm-config spec the single source of truth for its domain and prevents the diagnostics spec from shipping a persistence mechanism its supporting infrastructure has not been committed to.

### 13.2 Survey-before-amend requirement

Before drafting the amendments, the plan-composition session must survey the current state of the firm-config spec and its implementation to confirm:

1. The firm-config spec's Status is still Finalized (no in-flight amendments that would conflict).
2. `src/trust_generator/v3/config/firm.py` matches the spec's current state (no uncommitted divergence).
3. `config/firm.toml` matches the spec's current state (no uncommitted divergence).
4. The firm-config implementation plan (if it exists as a separate plan file) has completed at least through the loader implementation (Task 5 of the firm-config spec's §12 checklist), so amendments can reference a working `load_firm_config()` rather than a stub.

If any of the four checks fails, the session must surface the conflict to the maintainer before proceeding rather than drafting amendments against a moving target.

### 13.3 Required amendments

Three amendments land against `docs/superpowers/specs/2026-04-21-firm-config-design.md` in one post-finalization-amendment pass, numbered A-4 through A-6 to continue the existing amendment sequence.

**A-4: Tilde expansion in path resolution.** Amends the firm-config spec's §5.5 (path resolution) and §7 (loader internal shape). `load_firm_config()` applies `Path(value).expanduser()` to all `Path`-typed fields *before* the existing relative-to-absolute transformation. Rationale: per-user paths (like the `audit_log_dir` introduced by diagnostics §11) must resolve against the host's current Windows profile without hardcoding the username in the config file. Tilde expansion preserves cross-workstation portability for a single `firm.toml`.

**A-5: New `[user]` section with `upn` field.** Amends the firm-config spec's §5 (configuration schema) and §6 (file layout) to add a `[user]` table:

```toml
[user]
upn = "zramdass"   # M365 account prefix; non-empty string
```

The field is validated as non-empty at load time (Pydantic field validator on `User` nested model). Format validation (e.g., conforming to an M365 policy) is the onboarding workflow's responsibility and is NOT enforced by `load_firm_config()`. Pre-onboarding deployments hand-set the value; §12.1 of this spec describes the future onboarding workflow that will populate it programmatically.

**A-6: `${user.upn}` post-parse substitution in `audit_log_dir`.** Amends the firm-config spec's §5.5 (path resolution semantics). After loading the TOML and validating the `[user] upn` field, the loader performs a literal string replacement of `${user.upn}` with the validated UPN value in `diagnostics.audit_log_dir`, then applies the tilde expansion from A-4, then applies the existing relative-to-absolute transformation. The substitution is a loader-side string replacement, NOT a TOML language feature (TOML has no interpolation). The amendment must document the order of operations explicitly: substitute → expanduser → resolve-relative.

### 13.4 Production value for `audit_log_dir`

After A-4, A-5, and A-6 land, the production `config/firm.toml` sets:

```toml
[user]
upn = "zramdass"   # replaced per workstation during deployment

[diagnostics]
audit_log_dir = "~/Crosby and Crosby LLP/internal-applications - trust-generator/users/${user.upn}/logs"
```

On load, the loader resolves this to (for the maintainer's machine):

```
C:\Users\ramda\Crosby and Crosby LLP\internal-applications - trust-generator\users\zramdass\logs
```

This is the `AuditLog.dir` that `force_generation()` writes against.

### 13.5 Amendment ordering in the plan

The three amendments are co-dependent and should land as a single commit to the firm-config spec. A-4 alone is not useful (nothing needs tilde expansion yet). A-5 alone is not useful (no consumer). A-6 requires both. The plan-composition session should not interleave these amendments with diagnostics-side work; the amendment pass completes first, the firm-config implementation is updated to match, and the diagnostics implementation then consumes the updated `FirmConfig` surface.

### 13.6 Firm-config implementation updates

The amendments also obligate corresponding updates to the firm-config implementation:

- `src/trust_generator/v3/config/firm.py` gains a `User(BaseModel)` nested model with a `upn: str` field and a non-empty validator; adds `user: User` to `FirmConfig`.
- `load_firm_config()` gains the `${user.upn}` substitution pass and the `expanduser()` call, in the order specified in A-6.
- Existing tests in `tests/v3/config/test_firm.py` gain coverage for: `[user] upn` required-field validation, tilde expansion, `${user.upn}` substitution correctness, and the order-of-operations for combined path resolution.
- `config/firm.toml` gains the `[user]` section and the updated `audit_log_dir` value.

These implementation updates are part of the same commit as the spec amendments, keeping the spec-implementation coupling tight.

## 14. Downstream plan split: core engine vs. starter rules

The §6 implementation cycles split across two downstream plans rather than landing in a single session. The split formalizes the cycle dependency graph (§6.1) into two reviewable units, bounds session size, and matches the chore precedent of separating infrastructure work from rule authoring.

### 14.1 Plan boundaries

**Plan `2026-04-23-diagnostics-engine-core` (cycles 1–6):**

- Cycle 1 (outer integration test) — committed Red as the engine's contract; turns Green only after the rules plan lands.
- Cycle 2 (`build_eval_context`).
- Cycle 3 (rule loader: builtin + firm-side custom + namespace/dedupe).
- Cycle 4 (rule evaluator + meta-diagnostic surfacing).
- Cycle 5 (audit log writer: JSON-lines, monthly rotation, per-user subfolder).
- Cycle 6 (`force_generation()` override flow).
- Consumes the `firm.toml` surface delivered by chore `2026-04-24-firm-config-amendments-a4-a6`.
- Produces: `diagnose()`, `build_eval_context()`, `DiagnosticRule`, `load_rules()`, `AuditLog`, `force_generation()`.

**Plan `2026-04-23-diagnostics-engine-rules` (cycles 7–9):**

- Cycle 7 (`shares.sum_not_100` — `DiagnosticSource.SCHEMA`, `ERROR`).
- Cycle 8 (`estate.crossed_cliff` — `DiagnosticSource.BUSINESS_RULE`, `WARNING`).
- Cycle 9 (`extraction.placeholder_unfilled` — `DiagnosticSource.EXTRACTION`, `WARNING`).
- Depends on the engine being green; closes Cycle 1 as the final checkpoint.
- Produces: three YAML rule files, their tests, end-to-end demonstration of all three `DiagnosticSource` categories.

### 14.2 Dependency and ordering

The rules plan strictly follows the core plan. Cycle 1's integration test (§6.2) is committed Red in the core plan and stays Red until the rules plan lands. The two sessions are sequential, not concurrent.

### 14.3 Why this split (not a single session)

1. **Reviewability.** Engine plumbing (cycles 2–6) and rule definitions (cycles 7–9) have orthogonal review concerns. Engine review focuses on infrastructure correctness (loader robustness, evaluator failure modes, audit log durability). Rules review focuses on domain accuracy (when the cliff fires, what `shares.sum_not_100` returns for boundary-edge totals). Bundling both in one PR would force reviewers to context-switch between the two modes; splitting lets each session's review settle on one.
2. **Session size.** Cycles 2–6 alone are six TDD cycles touching engine, persistence, and override flow. Adding three more rule cycles in the same session would likely exceed the project's hard threshold (≥10 files or ≥5 complex tasks per session) per the global CLAUDE.md scope-rejection rule.
3. **Rule corpus extensibility.** The rules plan establishes the YAML authoring pattern that future firm-authored rules will follow. Isolating it in its own session lets the plan-composition for that session focus narrowly on the YAML schema, naming convention, and cycle structure — making the pattern legible for non-engine-author readers (paralegals authoring custom rules through Session 4.1's GUI).

### 14.4 Cycle 1's Red period

The core plan commits Cycle 1's integration test (§6.2) Red. Between the core plan landing and the rules plan landing, `pixi run check` will fail on the Cycle 1 test. This Red period is a deliberate signal that the engine is not yet usable — the engine ships behind the rules, and the rules plan's final commit turns Cycle 1 Green.

To prevent the Red period from blocking unrelated work on the v3 branch, the core plan may either:

- **(A) Skip Cycle 1's test** by marking it `pytest.mark.xfail(reason="diagnostics-engine-rules plan pending")` and removing the marker in the rules plan's first commit, or
- **(B) Defer Cycle 1's test entirely** to the rules plan, with the core plan owning only cycles 2–6.

Option (A) preserves the test as an explicit contract anchor in the core plan's diff; option (B) keeps the gate green but loses the contract anchor. The plan-composition session for the core plan picks one and records the choice in its plan-md.

---

## Design decisions and scope additions

This section enumerates analytical decisions made during spec authoring that are not directly traceable to a graph entity observation or userMemories note. Each is deliberate, not implementation discretion.

**Approved scope additions (confirmed with Zayn during authoring):**

1. **Two-tier rule organization (builtin in-repo, custom in firm config dir).** Builtin codes use `<domain>.<n>`; custom codes use `custom.<topic>.<n>`. Promotion of custom → builtin is a deliberate maintainer step.
2. **Dedupe and collision semantics.** Code-collision detection (identity) separate from expression dedupe (behavior). `(normalized_expression, level)` key for expression dedupe, builtin wins, drop logged at `INFO` not in audit log. Code collision raises `DiagnosticConfigError` regardless of source set.
3. **Per-rule `enabled` only — firm-level toggle deferred to YAGNI.** Recorded as open seam in §7.
4. **Rule construction at load time, not first evaluation.** Loader compiles every rule immediately; construction failures (`RuleSyntaxError`, `RegexSyntaxError`, `AttributeResolutionError`) surface as `DiagnosticConfigError` with file and rule-code attribution. Evaluator handles only runtime-only failures.
5. **YAML custom file accepts both list and single-mapping forms.** Preserves downstream freedom for Session 4.1's GUI to pick its serialization form without the loader imposing a constraint.
6. **Audit log persistence via Path A (OneDrive sync client).** Rejected Path B (Microsoft Graph API) on dependency/authentication cost grounds; structural elimination of concurrent-write risk via per-user subfolders removes the main reason to prefer Path B.
7. **Per-user subfolders over per-host filename suffixes.** Grants SharePoint-native permission granularity and anticipates future per-user synchronized artifacts without structural reshape.
8. **`firm.toml` `[user] upn` field as identity source.** Rejected `whoami`-family stdlib sources on environmental-trust grounds (generic hostnames, inconsistent local usernames, non-Entra-joined machines). Rejected Microsoft Graph API on scope/dependency grounds. The spec specifies the reader contract; population (hand-set pre-onboarding, onboarding-collected post-§12.1) is upstream.
9. **Tilde expansion added to firm-config load-time path resolution.** Keeps per-user paths portable across workstations without requiring each `firm.toml` to hardcode its machine's username. Extends the existing relative-path-resolution pass in firm-config §5.5.
10. **`${user.upn}` post-parse substitution in `audit_log_dir`.** Chosen over caller-side path construction to keep `firm.toml` the single source of truth for the resolved path. Documented as a loader-side substitution, not a TOML language feature.

**Inline design decisions (within scope):**

11. **Wrap (not adopt-direct) resolution for `rule-engine`** (§4). Refines the `rule_engine_binding` entity's original `adopt` framing. The wrap surface is `build_eval_context()` and `DiagnosticRule`.
12. **Eval context shape: nested under `trust`/`firm`/`now`** (§5.2). Chosen over flat namespace for readability and schema-topology preservation.
13. **Computed-property injection list is fixed in code, not auto-discovered** (§5.2). Six keys: five via `COMPUTED_PROPERTIES` getattr loop, one (`minor_beneficiaries`) injected separately because it requires `ref_date`. Cost of avoiding `@computed_field` decoration churn on `schema.py`.
14. **`AuditRecord` lives in `diagnostics/audit.py`, not in `schema.py`** (§5.6). Diagnostics-internal concern; `schema.py` remains untouched per scope.
15. **`force_generation` reason validation: ≥10 non-whitespace characters** (§5.6). Soft guard against ceremonial `"ok"` overrides. Heuristic; tightenable if abuse patterns emerge. Exposed as `validate_override_reason()` for GUI live-validation.
16. **`force_generation` sources user from `config.user.upn`, not a per-call argument** (§5.6). Identity is a property of the workstation's firm_config, not a per-call choice. Prevents misattribution and ensures all records on a workstation share the same user.
17. **`trust_ref` fallback to `"unidentified"` when `office.file_number` is empty** (§5.5). The audit record must always be human-correlatable; an empty string would be silently misleading. The string `"unidentified"` is itself a flag.
18. **Type-resolver UNDEFINED posture for v1** (§4, §6.5). Explicit `UNDEFINED` for top-level symbols catches unknown-symbol typos (rule-engine raises `SymbolResolutionError`) without forcing exhaustive leaf-type declarations. Tightening is an open seam.
19. **Message templating not in v1** (§6.8 refactor note, §7 open seam). Messages are static strings. Templating would add a post-evaluation interpolation pass; defer until a starter rule motivates it.
20. **`extraction.placeholder_unfilled` starter rule scoped to one field** (§6.10). The OCR pipeline doesn't exist yet; the starter establishes the canonical `[OCR_LOW_CONFIDENCE]` placeholder convention and the EXTRACTION-source pattern. Generalization to all extraction-prone fields is an open seam.
21. **Determinism: rules execute in load order; diagnostics list preserves it** (§5.1). Explicit semantic commitment so tests can rely on positional indexing and the GUI can render diagnostics in a stable order.
22. **`DiagnosticConfigError` is the loader's only failure mode; runtime evaluation errors yield meta-diagnostics, not exceptions** (§6.4, §6.5). Distinguishes config-time concerns (which should surface immediately and loudly) from runtime concerns (which should be visible in the diagnostic stream alongside data-driven diagnostics).
23. **`freezegun` for time-dependent tests** (§6.3 test 6, §6.6 test 4). Patches `datetime.now`, `date.today`, `time.time` globally regardless of implementation import structure. Chosen over monkeypatching specific import sites because the latter couples test to implementation.
24. **Compiled rule instance lives on `DiagnosticRule` via `PrivateAttr`** (§6.5). Loader populates; evaluator reads. Evaluator never re-compiles. Prevents silent per-evaluation re-parsing under mutation.

**What does trace to the graph or userMemories:**

- `diagnostics_design` → §5.1 entry-point shape, §5.6 override flow shape.
- `diagnostics_enforcement` → §5.5 audit log JSON-lines + monthly rotation, §5.6 override flow, §11 persistence destination (refines "firm-config directory" to "shared SharePoint library").
- `rule_engine_binding` → §4 (refined to `wrap`), §6.5 evaluator shape, §6.4 load-time compilation.
- `estate_thresholds` → §6.9 starter rule.
- `python_stack_commitments` → Pydantic v2.x model usage, stdlib `datetime.date` throughout.
- `bounded_context_design` → §1 motivation (`diagnose()` consumes `TrustData`, the canonical post-fill model).

Anything not enumerated above and not in this trace list is implementation discretion that the plan composition session can settle without analytical work.
