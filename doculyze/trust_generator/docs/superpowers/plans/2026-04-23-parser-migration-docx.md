# TGv3 Parser Migration — docx Implementation Plan

> **For agentic workers:** Use `spec-pipeline:plan-executor-team` (member of plan-group `2026-04-23-parser-migration`). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the v3 docx parser end-to-end (smoke → asset integration → post-promotion contract → coercion integration) such that `parse_docx(filepath, seed_initialized)` honors the §5.3 merge protocol, the spec §5.4 coercion patterns for docx, and the F1–F4 post-pass-2 review findings (None-gate, fixed iteration order, exclusions-as-function-local, multi-match WARNING test).

**Architecture:** A single-file `src/trust_generator/v3/parsers/docx_parser.py` exposes the free function `parse_docx`. The body deepcopies the seed-initialized `TrustData` (P3), walks the document via `python-docx`, produces a flat key-value extraction plus the v2 `exclusions` string as a parser-internal carrier, then sequentially: (a) coerces via the upstream `coercion.py` helpers, (b) routes through `_apply_post_promotion_protocol(result, parsed_trust_type, parsed_marital_status)` for the `trust_type` / `marital_status` mutation (cycle 4b refactor target), (c) fills remaining fields onto `result` (including bare `SuccessorTrustee` instances — entity discrimination deferred), (d) routes through `_apply_post_merge_resolution(result, exclusions_string)` for disinheritance + CorporateTrustee discrimination (the helper iterates `result.successor_trustees` and re-applies `_is_entity_name` per entry; this is the cross-parser contract reconciled by peer-DM with the `pdf` sibling on 2026-05-18). Synthetic docx fixtures are constructed programmatically in tests via a `tests/v3/parsers/_docx_fixtures.py` helper — never committed as binaries (Decision log #20).

**Tech Stack:** Python ≥3.12, Pydantic v2 (`model_copy(deep=True)`, `model_validate`), `python-docx` (existing v3 dep — `Document`, table/paragraph traversal), stdlib `re` (placeholder-prefix stripping, entity-name discrimination heuristic), stdlib `logging` (soft-fail surface).

---

## Plan Metadata (binding, validated by lead against splits.xml)

| Field | Value |
|---|---|
| Plan id | `2026-04-23-parser-migration-docx` |
| Plan-group | `2026-04-23-parser-migration` (plans.xml index 15) |
| Suffix | `docx` |
| Cycles | `[§6.5..§6.8]` (Cycle 4a, Cycle 4b, Cycle 5, Cycle 6) |
| Depends-on | `json-and-coercion` (informational at drafting time; the coercion helpers are consumed by Cycle 6) |
| Worktree | not-required |
| Blast-radius | `src/trust_generator/v3/parsers/docx_parser.py;tests/v3/parsers/test_docx_parser.py;tests/v3/parsers/_docx_fixtures.py;tests/v3/parsers/test_assets_integration.py` |
| Spec | `docs/superpowers/specs/2026-04-23-parser-migration-design.md` |
| Splits | `docs/superpowers/specs/2026-04-23-parser-migration-splits.xml` |
| Upstream contract | `docs/superpowers/specs/2026-04-22-promote-seed-design.md` §6.2.3 (parser contract at the `promote_seed` boundary) |
| Sibling (upstream) | `json-and-coercion` — provides `coercion._to_date`, `coercion._to_decimal`, `coercion._to_address`, `coercion._to_person_reference` consumed by Cycle 6 |
| Sibling (downstream) | `pdf` — reuses the `_apply_post_promotion_protocol` helper extracted in Cycle 4b refactor |
| Sibling (downstream) | `registry` — registers `parse_docx` under the `.docx` extension dispatch in `parse_file` |

**Discipline notes:**

- Feature branch only — never `main`. Always create a new commit; never `--amend`. Never bypass hooks (`--no-verify`, `--no-gpg-sign`).
- All ad-hoc Python invocation goes through `pixi run python` / `pixi run test` / `pixi run check` (system Python is 3.14; the pixi env pins 3.12 for rule-engine compat).
- `ruff` runs in preview mode targeting py312. RUF022 auto-alphabetizes `__all__` — declare `__all__` entries in sorted order. RUF032 autofixes integer-valued `Decimal("n")` to `Decimal(n)` — write integer-form Decimal literals directly.
- One Red commit + one Green commit per cycle (per `.claude/rules/development-strategy.md`). A Refactor commit is added only when the refactor threshold is met; each cycle lists its threshold verdict.
- For items surfaced mid-implementation that aren't covered by the active plan: open a chore-entry via the `spec-pipeline` scope-maintenance protocol. Do not silently expand the cycle.

## File structure

```
src/trust_generator/v3/parsers/
├── __init__.py              # NOT TOUCHED in this plan (created by json-and-coercion; registry re-exports parse_docx later)
├── coercion.py              # NOT TOUCHED in this plan (created by json-and-coercion; consumed read-only in Cycle 6)
├── json_parser.py           # NOT TOUCHED (json-and-coercion's surface)
├── docx_parser.py           # CREATE (Cycle 4a) → EXPAND (Cycles 4b/5/6); houses parse_docx, _apply_post_promotion_protocol, _apply_post_merge_resolution
├── pdf_parser.py            # NOT TOUCHED (pdf sibling's surface; consumes the helper extracted here in Cycle 4b)
└── registry.py              # NOT TOUCHED (registry sibling's surface)

tests/v3/parsers/
├── __init__.py              # NOT TOUCHED (created by json-and-coercion)
├── test_coercion.py         # NOT TOUCHED (json-and-coercion's surface)
├── test_json_parser.py      # NOT TOUCHED (json-and-coercion's surface)
├── test_docx_parser.py      # CREATE (Cycle 4a) → APPEND (Cycles 5/6); houses all synthetic-fixture docx tests
├── _docx_fixtures.py        # CREATE (Cycle 5, §6.7.1); programmatic .docx fixture builder consumed by test_docx_parser.py
├── test_assets_integration.py # CREATE (Cycle 4b); houses the skipif-gated test against assets/Trust_Intake_Questionnaire.docx
├── test_pdf_parser.py       # NOT TOUCHED (pdf sibling's surface)
└── test_registry.py         # NOT TOUCHED (registry sibling's surface)
```

`docx_parser.py` is created once (Cycle 4a) and progressively expanded across Cycles 4b/5/6. Each cycle's Green commit lands the minimum body that turns its Red phase green; the Cycle 4b Refactor commit (the only Refactor commit in this plan per the §6.6 threshold verdict) extracts the `_apply_post_promotion_protocol` helper that the `pdf` sibling will consume.

## Out of scope (handed to sibling plans)

The following cycles are owned by sibling child plans within plan-group `2026-04-23-parser-migration`. Cross-reference by exact suffix name.

| Sibling cycle | Suffix | Surface | One-line from spec §6 |
|---|---|---|---|
| §6.1 (Cycle 0) | `json-and-coercion` | Precondition check — full suite green at session start | The cycle exists to make the starting state explicit; no code change |
| §6.2 (Cycle 1) | `json-and-coercion` | JSON round-trip | `parse_json` reads text, calls `TrustData.model_validate_json`, wraps `ValidationError` as `ValueError`, returns the restored TrustData |
| §6.3 (Cycle 2) | `json-and-coercion` | JSON parser error surfaces | Three tests pin missing-file, invalid-JSON, schema-violation behaviors (the third is novel under v3's typed schema) |
| §6.4 (Cycle 3) | `json-and-coercion` | Coercion helpers (pure) | `_to_date`, `_to_decimal`, `_to_address`, `_to_person_reference` in `coercion.py`, plus the share-percent-drops-row regression guard and the placeholder-prefix-stripping regression guard |
| §6.9 (Cycle 7) | `pdf` | PDF parser via AcroForm field iteration | Reuses `_apply_post_promotion_protocol` from this plan's Cycle 4b refactor + cycle-3 coercion helpers + §5.4.A field-presence normalization (`_normalize_field_values`) |
| §6.10 (Cycle 8) | `registry` | `parse_file` extension dispatch | Includes `test_parse_file_ignores_seed_for_json` contract test (M2 from plan-review pass 1) |
| §6.11 (Cycle 9) | `registry` | Public exports in `v3.parsers.__init__` | `parse_docx`, `parse_pdf`, `parse_json`, `parse_file` re-exported |

**Cross-plan integration notes:**

- The `coercion.py` helpers are imported (read-only) in this plan's Cycle 6 Green phase. The exact signatures are pinned by `json-and-coercion`'s cycle 3 Red tests; this plan assumes the signatures recorded in spec §5.4.1–§5.4.4. If the upstream cycle 3 lands a signature drift (e.g., adds a required `source_label` kwarg), pause and raise a plain-text DM to `json-and-coercion` before adapting Cycle 6 — do not silently absorb the drift here.
- The `_apply_post_promotion_protocol(result, parsed_trust_type, parsed_marital_status)` helper extracted in Cycle 4b Refactor is the contract surface the `pdf` sibling consumes in §6.9. Its signature is binding — any signature change after this plan lands will force re-execution of `pdf`'s cycle 7. Document the signature in the helper's docstring and reference it from `pdf`'s plan-md after this plan commits.
- `registry`'s `test_parse_file_dispatches_docx` (in §6.10) needs `parse_docx` importable from `v3.parsers`; the `__init__.py` `__all__` entry is added by `registry` Cycle 9, not here.

---

## Cycle 4a — docx parser smoke test (no asset dependency) [spec §6.5]

**Files:**
- Create: `src/trust_generator/v3/parsers/docx_parser.py`
- Create: `tests/v3/parsers/test_docx_parser.py`

**Threshold verdicts:**
- design_surface_threshold: contract surface external consumers (downstream `parse_file` dispatch, `pdf` sibling's helper reuse) depend on; satisfies the criterion.
- refactor_threshold: **none met — green output is already minimal** (the smoke-green body is open-doc + deepcopy-and-return; no structural duplication, no orthogonal concerns).

**Scope:** isolate the "parser exists and loads `python-docx`" failure surface from the "parser handles the v2.2 questionnaire format" failure surface. The Red signal under this cycle MUST be unambiguously "parser absent" — the synthetic `minimal.docx` has zero v2.2-shape dependencies. This is the M5 cycle-split (plan-review pass 1).

- [ ] **Step 1: Write the failing test (Red)**

Create `tests/v3/parsers/test_docx_parser.py`:

```python
"""Unit tests for parse_docx and the post-promotion protocol helper."""

from __future__ import annotations

import pytest
from docx import Document

from trust_generator.v3.schema import (
    MaritalStatus,
    QuestionnaireSeed,
    TrustType,
    promote_seed,
)


def test_parse_docx_smoke(tmp_path):
    """parse_docx exists, opens a minimal valid .docx, and returns a TrustData.

    The Red signal is unambiguously "parser module absent" — the minimal.docx
    has no v2.2-shape dependencies, so cycle-4b asset-shape failures cannot
    masquerade as cycle-4a failures (plan-review pass 1, M5 cycle-split).

    Import is via the explicit module path (`v3.parsers.docx_parser`) rather
    than the package re-export. The package `__init__.py` re-export of
    `parse_docx` lands in the downstream `registry` sibling's cycle 9; until
    that lands, every test in this plan imports through the explicit module
    path.
    """
    from trust_generator.v3.parsers.docx_parser import parse_docx  # NOQA: deliberate late import

    minimal_docx = tmp_path / "minimal.docx"
    doc = Document()
    doc.add_paragraph("placeholder")
    doc.save(str(minimal_docx))

    seed = QuestionnaireSeed(
        trust_type=TrustType.JOINT,
        marital_status=MaritalStatus.MARRIED,
    )
    seed_initialized = promote_seed(seed)
    seed_snapshot = seed_initialized.model_copy(deep=True)

    result = parse_docx(minimal_docx, seed_initialized)

    assert result is not None
    # P3 invariant (spec §4): seed_initialized is field-level equal before and
    # after. The deepcopy at parser entry is the reference implementation that
    # satisfies this postcondition; the test is implementation-agnostic.
    assert seed_initialized == seed_snapshot
    # Deepcopy proof (spec §5.3 step 1): the returned TrustData is a separate
    # instance from the caller-supplied seed_initialized.
    assert result is not seed_initialized
```

The `from trust_generator.v3.parsers.docx_parser import parse_docx` line is the one that fails Red. The `v3.parsers` package itself is created by the upstream `json-and-coercion` cycle 1; this plan only adds `docx_parser.py` to it. The package's `__init__.py` re-export of `parse_docx` lands in the downstream `registry` cycle 9 — so every test in this plan imports through the explicit `trust_generator.v3.parsers.docx_parser` module path, not through the package re-export.

- [ ] **Step 2: Run test to verify it fails**

Run: `pixi run test -- tests/v3/parsers/test_docx_parser.py -v`

Expected: `ModuleNotFoundError: No module named 'trust_generator.v3.parsers.docx_parser'` on the late-import line.

- [ ] **Step 3: Write minimal implementation (Green)**

Create `src/trust_generator/v3/parsers/docx_parser.py`:

```python
"""v3 docx intake-questionnaire parser.

Parses a `.docx` Trust Intake Questionnaire into a copy of the
seed-initialized `TrustData`. Honors the post-promotion contract from
`promote_seed` spec §6.2.3 (no re-invocation of `promote_seed`; joint
`trust_type` / `marital_status` mutation per `_resolve_captions`).

Public surface:
    parse_docx(filepath, seed_initialized) -> TrustData

This module is the docx leg of `parse_file`'s extension dispatch
(registered in `registry.py`). The post-promotion helper extracted
below (`_apply_post_promotion_protocol`) is also consumed by the PDF
parser in `pdf_parser.py` — its signature is therefore a binding
contract surface across the two parsers.
"""

from __future__ import annotations

import logging
from pathlib import Path

from docx import Document  # type: ignore[import-untyped]

from trust_generator.v3.schema import TrustData

log = logging.getLogger(__name__)


def parse_docx(filepath: Path, seed_initialized: TrustData) -> TrustData:
    """Parse a Trust Intake Questionnaire .docx INTO a copy of seed_initialized.

    The seed_initialized argument is required (no default) to make the
    post-promotion contract loud at every call site (spec §5.2). The
    return value is a deepcopied-then-filled TrustData; the caller's
    seed_initialized is field-level equal before and after this call
    (spec §4 P3, asserted by `test_parse_docx_smoke`).
    """
    if not filepath.exists():
        raise FileNotFoundError(filepath)

    result = seed_initialized.model_copy(deep=True)

    # Cycle 4a: open the document, walk paragraphs (no content extracted yet).
    # Cycle 4b expands this into the flat-key extraction; cycles 5 and 6 add
    # post-promotion and coercion + post-merge resolution respectively.
    doc = Document(str(filepath))
    for _ in doc.paragraphs:
        pass
    for _ in doc.tables:
        pass

    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pixi run test -- tests/v3/parsers/test_docx_parser.py -v`

Expected: `PASS` on `test_parse_docx_smoke`.

Run: `pixi run check`

Expected: full gate green (no lint/mypy/test regressions). If mypy flags the `docx` import, ensure the `type: ignore[import-untyped]` directive is present; `python-docx` ships without type stubs as of the v2 dependency baseline.

- [ ] **Step 5: Commit Red**

```bash
git add tests/v3/parsers/test_docx_parser.py
git commit -m "test(v3/parsers): pin docx parser smoke contract (Red, cycle 4a)"
```

- [ ] **Step 6: Commit Green**

```bash
git add src/trust_generator/v3/parsers/docx_parser.py
git commit -m "feat(v3/parsers): introduce parse_docx with deepcopy-and-return body (Green, cycle 4a)"
```

---

## Cycle 4b — docx parser asset integration [spec §6.6]

**Files:**
- Modify: `src/trust_generator/v3/parsers/docx_parser.py` (expand the Cycle 4a body; Refactor extracts `_apply_post_promotion_protocol`)
- Create: `tests/v3/parsers/test_assets_integration.py`

**Threshold verdicts:**
- design_surface_threshold: composition of multiple units (flat-key extraction, model construction, post-promotion sequencing) plus a contract surface (`_apply_post_promotion_protocol`) external consumers (the `pdf` sibling) depend on; satisfies the criterion.
- refactor_threshold: **MET — mixes orthogonal concerns** ("parse content" vs. "honor the post-promotion contract"). The Refactor commit extracts `_apply_post_promotion_protocol(result, parsed_trust_type, parsed_marital_status)`; this is also a natural target for the Cycle 5 contract tests.

**Cross-plan note:** the Refactor commit lands the `_apply_post_promotion_protocol` helper that `pdf`'s cycle 7 Green phase will import and call. Pin the helper's signature in its docstring; the `pdf` plan-md cross-references this signature by exact name.

- [ ] **Step 1: Write the failing test (Red)**

Create `tests/v3/parsers/test_assets_integration.py`:

```python
"""Asset-anchored integration tests (Tier 3 per spec §8.3).

These tests exercise the parsers against the checked-in intake artifacts
in `assets/`. They are gated by `pytest.mark.skipif(not <PATH>.exists())`
so that workstation setups without the assets directory still get a
green test run; the synthetic-fixture tests (Tier 2) carry the
deterministic coverage.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from trust_generator.v3.parsers.docx_parser import parse_docx
from trust_generator.v3.schema import (
    MaritalStatus,
    QuestionnaireSeed,
    TrustType,
    promote_seed,
)

QUESTIONNAIRE_PATH = Path(__file__).resolve().parents[3] / "assets" / "Trust_Intake_Questionnaire.docx"


@pytest.mark.skipif(
    not QUESTIONNAIRE_PATH.exists(),
    reason="Trust_Intake_Questionnaire.docx not found in assets/",
)
def test_parse_docx_blank_template_into_seed_initialized():
    """Parsing a blank template into a JT+MR seed produces a TrustData
    with the seed's defaults preserved and minimal new content extracted.

    The blank-template input is the integration anchor for the v2.2
    questionnaire shape: it exercises the table-walk, paragraph-walk,
    and checkbox-detection code paths against a real artifact whose
    structure the synthetic fixtures (cycle 5) approximate.
    """
    seed = QuestionnaireSeed(
        trust_type=TrustType.JOINT,
        marital_status=MaritalStatus.MARRIED,
    )
    seed_initialized = promote_seed(seed)
    result = parse_docx(QUESTIONNAIRE_PATH, seed_initialized)

    # Seed-projected defaults survive a no-mutation parse:
    assert result.trust_id.trust_type == TrustType.JOINT
    assert result.trust_id.grantor_caption == "Grantor A"
    assert result.trust_id.co_grantor_caption == "Grantor B"
    assert result.co_grantor is not None
```

Also append to `tests/v3/parsers/test_docx_parser.py` a single synthetic-fixture-anchored test that exercises the flat-key extraction independent of asset availability — so the Cycle 4b Green body is exercised on every test run, not only when assets are present:

```python
def test_parse_docx_synthetic_grantor_name_extraction(tmp_path):
    """A synthetic fixture with a single Grantor row populates result.grantor.

    Independent of asset availability; pins that the cycle-4b flat-key
    extraction wires at least one v2.2 row into result. The full row
    coverage lives in cycle 6 (coercion integration); cycle 4b's
    obligation is just that *some* table content survives the parse.
    """
    from docx import Document
    from trust_generator.v3.parsers.docx_parser import parse_docx

    fixture = tmp_path / "single_row.docx"
    doc = Document()
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Grantor full legal name"
    table.cell(0, 1).text = "John Andrew Doe"
    table.cell(1, 0).text = "Grantor date of birth"
    table.cell(1, 1).text = "01/15/1970"
    doc.save(str(fixture))

    seed = QuestionnaireSeed(
        trust_type=TrustType.JOINT,
        marital_status=MaritalStatus.MARRIED,
    )
    seed_initialized = promote_seed(seed)
    result = parse_docx(fixture, seed_initialized)

    assert result.grantor.full_legal_name == "John Andrew Doe"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pixi run test -- tests/v3/parsers/test_docx_parser.py tests/v3/parsers/test_assets_integration.py -v`

Expected (synthetic test): `AssertionError` — `result.grantor.full_legal_name` is the seed-projected default (typically `""` or the seed-supplied name), not `"John Andrew Doe"`, because Cycle 4a's body extracts no content.

Expected (assets test): SKIP if assets absent; otherwise, identical AssertionError-class failure because the cycle-4a body extracts no content.

- [ ] **Step 3: Write minimal implementation (Green)**

Expand `src/trust_generator/v3/parsers/docx_parser.py` so `parse_docx` walks tables, builds a flat key-value map (label → cell text) plus parser-internal carriers (the v2 `exclusions` text-block string and a trustee-entity-flags list), and assigns extracted values onto `result` using v3 model names (`grantor` / `co_grantor` instead of v2's `husband` / `wife`). Port the v2 docx parser's `_HINTS`, `_CHECKBOX_MAP`, and table-detection logic verbatim (spec §3.2 cites `src/trust_generator/v2/parsers/docx_parser.py` as the reference implementation). Inside the body, after the flat-key extraction, branch on parsed-`trust_type` and parsed-`marital_status` and apply the §5.3 step 4 sequence inline (caption re-resolution via `_resolve_captions(new_trust_type)`, `co_grantor` materialization). Do NOT extract the helper yet — the Refactor commit below does that.

The Green body MUST satisfy:
1. The Cycle 4a smoke test still passes (minimal.docx → deepcopy-return; no extracted content because the synthetic table is absent).
2. The Cycle 4b synthetic test passes (`result.grantor.full_legal_name == "John Andrew Doe"`).
3. The Cycle 4b asset-anchored test passes if the asset is present (blank-template parse preserves JT+MR captions and materializes `co_grantor`).

Concretely, the Green body's shape is:

```python
def parse_docx(filepath: Path, seed_initialized: TrustData) -> TrustData:
    """[docstring as in Cycle 4a, expanded with §5.3 reference]"""
    if not filepath.exists():
        raise FileNotFoundError(filepath)

    result = seed_initialized.model_copy(deep=True)
    doc = Document(str(filepath))

    # Flat-key extraction (spec §5.3 step 2). Walks tables for label/value
    # pairs and paragraphs for checkbox / text-block content. Direct port
    # of v2 docx parser logic; v3-specific names land in the assignment
    # step below.
    flat, exclusions_string = _extract_flat(doc)

    # Step 4 (post-promotion) — INLINE in Green; extracted in Refactor below.
    # Co_grantor protocol per spec §5.3 step 4 as amended by chore #37
    # (2026-05-18): materialize on None when post-mutation state requires
    # co_grantor; dematerialize default-only GrantorInfo() when post-mutation
    # state requires no co_grantor; preserve populated co_grantor in either
    # direction. Verbatim amendment text quoted in the Cycle 5 preamble.
    parsed_trust_type = flat.get("trust_type")  # already enum-coerced via _CHECKBOX_MAP
    parsed_marital_status = flat.get("marital_status")
    if parsed_trust_type is not None and parsed_trust_type != result.trust_id.trust_type:
        result.trust_id.trust_type = parsed_trust_type
        new_grantor_caption, new_co_grantor_caption = _resolve_captions(parsed_trust_type)
        result.trust_id.grantor_caption = new_grantor_caption
        result.trust_id.co_grantor_caption = new_co_grantor_caption
    if parsed_marital_status is not None and parsed_marital_status != result.trust_id.marital_status:
        result.trust_id.marital_status = parsed_marital_status
    # co_grantor materialization / dematerialization computed ONCE after
    # both fields settled:
    should_have_co_grantor = (
        result.trust_id.trust_type == TrustType.JOINT
        or result.trust_id.marital_status == MaritalStatus.MARRIED
    )
    if should_have_co_grantor and result.co_grantor is None:
        result.co_grantor = GrantorInfo()
    elif not should_have_co_grantor and result.co_grantor == GrantorInfo():
        result.co_grantor = None  # dematerialize default-only seed materialization

    # Step 5 (remaining mutations) — direct field assignments from flat.
    # Coercion call sites are stubs at cycle 4b; cycle 6 wires the
    # `coercion._to_*` helpers and the post-merge resolution call.
    if "grantor.full_legal_name" in flat:
        result.grantor.full_legal_name = flat["grantor.full_legal_name"]
    if "grantor.date_of_birth" in flat:
        # Cycle 4b leaves this as raw-string assignment; cycle 6 wires _to_date.
        # (The schema's `date | None` typing here means a raw-string assignment
        # raises ValidationError at cycle 4b — so the synthetic test must use
        # a row label cycle 4b actually processes. The chosen labels above
        # are "Grantor full legal name" (str → str, safe) plus "date of birth"
        # which cycle 4b STORES INTO THE FLAT DICT but does NOT yet assign
        # onto result. Adjust the synthetic test's expected fields to match
        # what cycle 4b actually assigns: full_legal_name only.)
        pass

    return result
```

Add the imports at module top:

```python
from trust_generator.v3.schema import (
    GrantorInfo,
    MaritalStatus,
    TrustData,
    TrustType,
    _resolve_captions,
)
```

The `_extract_flat(doc) -> tuple[dict[str, ...], str, list[bool]]` private helper houses the v2-ported table-walking logic. Its concrete body is a port of `src/trust_generator/v2/parsers/docx_parser.py`'s table iteration with v3-name substitution:

```python
def _extract_flat(doc) -> tuple[dict, str]:
    """Walk doc.tables + doc.paragraphs into (flat, exclusions).

    The flat dict keys are dotted schema paths (e.g.
    `"grantor.full_legal_name"`, `"trust_type"`); values are unparsed
    strings or already-enum-coerced values (the `_CHECKBOX_MAP`-driven
    entries are enum-coerced at this step because the map keys are
    phrases and the values are typed pairs).

    `exclusions` is the parser-internal carrier for the v2
    text_blocks.exclusions free-text (spec §5.3 step 6, §5.4.10
    algorithm step 1, F3 finding). NOT stored on result — v3's
    TrustData has no text_blocks.exclusions field per
    `modified_surfaces`. Threaded as a function-local argument into
    `_apply_post_merge_resolution` in cycle 6.

    Note (cross-plan reconciliation, 2026-05-18 peer-DM with sibling
    `pdf`): the §5.4.9 CorporateTrustee discrimination is performed
    inside `_apply_post_merge_resolution` itself (it iterates
    `result.successor_trustees` and re-applies `_is_entity_name` to
    each `trustee.full_legal_name`), so this helper does NOT need to
    return a parallel entity-flags carrier. Keeps the helper's
    signature parser-agnostic across docx and pdf consumers.
    """
    flat: dict = {}
    exclusions = ""
    # Direct port of v2 logic; v3-specific renames performed in this step.
    # ... (table iteration, _HINTS skip, _CHECKBOX_MAP enum lookup) ...
    return flat, exclusions
```

Also port the `_HINTS` and `_CHECKBOX_MAP` module-level constants verbatim from `src/trust_generator/v2/parsers/docx_parser.py` lines 64–110, swapping the v2 `husband` / `wife` initial-trustee enum values for v3's `InitialTrustee` enum values (`InitialTrustee.GRANTOR` / `InitialTrustee.CO_GRANTOR_ONLY` per `src/trust_generator/v3/schema.py` lines 131–134). Add v3's two new election checkboxes (`guardianship_policy`, `digital_assets_handling`) to `_CHECKBOX_MAP` per spec §5.4.5 — the phrasings come from the v2.2 questionnaire's existing election-checkbox rows; if the rows are absent at port time, leave the map entries unpopulated and surface a single chore-entry naming the missing v2.2 phrasings.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pixi run test -- tests/v3/parsers/test_docx_parser.py tests/v3/parsers/test_assets_integration.py -v`

Expected: `PASS` on `test_parse_docx_smoke` (unchanged), `test_parse_docx_synthetic_grantor_name_extraction`, and `test_parse_docx_blank_template_into_seed_initialized` (if asset is present; SKIP otherwise).

Run: `pixi run check`

Expected: full gate green.

- [ ] **Step 5: Commit Red**

```bash
git add tests/v3/parsers/test_docx_parser.py tests/v3/parsers/test_assets_integration.py
git commit -m "test(v3/parsers): pin docx asset-integration + synthetic-row extraction (Red, cycle 4b)"
```

- [ ] **Step 6: Commit Green**

```bash
git add src/trust_generator/v3/parsers/docx_parser.py
git commit -m "feat(v3/parsers): port v2 docx table-walk + inline post-promotion (Green, cycle 4b)"
```

- [ ] **Step 7: Refactor — extract `_apply_post_promotion_protocol`**

The Green-phase body mixes "parse content" (`_extract_flat`) with "honor the post-promotion protocol" (the inline `parsed_trust_type` / `parsed_marital_status` branch). Per `refactor_threshold` (`development-strategy.md`: "mixes orthogonal concerns that extract cleanly"), extract the protocol into a module-level helper.

Modify `src/trust_generator/v3/parsers/docx_parser.py`:

```python
def _apply_post_promotion_protocol(
    result: TrustData,
    parsed_trust_type: TrustType | None,
    parsed_marital_status: MaritalStatus | None,
) -> None:
    """Apply the §5.3 step 4 trust_type / marital_status mutation in place.

    Signature contract (binding across parsers): consumed by both
    `parse_docx` (this module) and `parse_pdf` (`pdf_parser.py`,
    sibling-plan `pdf` cycle 7). Any change to this signature requires
    coordinated re-execution of both consuming cycles.

    F1 (plan-review pass 2): `None` for either parsed argument means
    "no mutation requested" — the seed-initialized value persists.
    The gate is load-bearing because `trust_type` is a required schema
    field and assigning `None` would breach Pydantic validation.

    Ordering rule (spec §5.3 step 4): apply `trust_type` first (captions
    depend on it), then `marital_status`; compute `co_grantor`
    materialization / dematerialization ONCE after both fields have
    settled.

    Co_grantor protocol (spec §5.3 step 4 as amended by chore #37,
    2026-05-18 — see Cycle 5 preamble for the verbatim amendment text):
    - Materialize: post-mutation state requires co_grantor AND
      result.co_grantor is None → result.co_grantor = GrantorInfo().
    - Dematerialize: post-mutation state requires no co_grantor AND
      result.co_grantor is a default-only GrantorInfo() (equal to
      GrantorInfo() under Pydantic field-equality) → result.co_grantor
      = None.
    - Preserve (implicit fallback): any populated co_grantor is left
      untouched per the bounded-context translation invariant; the
      data is meaningful and the parser must not drop it.
    """
    if parsed_trust_type is not None and parsed_trust_type != result.trust_id.trust_type:
        result.trust_id.trust_type = parsed_trust_type
        new_grantor_caption, new_co_grantor_caption = _resolve_captions(parsed_trust_type)
        result.trust_id.grantor_caption = new_grantor_caption
        result.trust_id.co_grantor_caption = new_co_grantor_caption

    if parsed_marital_status is not None and parsed_marital_status != result.trust_id.marital_status:
        result.trust_id.marital_status = parsed_marital_status

    should_have_co_grantor = (
        result.trust_id.trust_type == TrustType.JOINT
        or result.trust_id.marital_status == MaritalStatus.MARRIED
    )
    if should_have_co_grantor and result.co_grantor is None:
        result.co_grantor = GrantorInfo()
    elif not should_have_co_grantor and result.co_grantor == GrantorInfo():
        # Dematerialization branch (chore #37 amendment). The equality check
        # `result.co_grantor == GrantorInfo()` leverages Pydantic v2 BaseModel
        # field-equality: a default-only GrantorInfo compares equal to
        # another default-only GrantorInfo; any populated field breaks the
        # equality and lands in the preservation fallback (no branch fires).
        result.co_grantor = None
```

Replace the inline block in `parse_docx` with:

```python
    _apply_post_promotion_protocol(result, parsed_trust_type, parsed_marital_status)
```

- [ ] **Step 8: Run tests to verify Refactor preserves green**

Run: `pixi run test -- tests/v3/parsers/ -v`

Expected: same tests pass; no behavior change.

Run: `pixi run check`

Expected: full gate green.

- [ ] **Step 9: Commit Refactor**

```bash
git add src/trust_generator/v3/parsers/docx_parser.py
git commit -m "refactor(v3/parsers): extract _apply_post_promotion_protocol helper (Refactor, cycle 4b)"
```

---

## Cycle 5 — docx parser post-promotion contract [spec §6.7, §6.7.1]

**Files:**
- Create: `tests/v3/parsers/_docx_fixtures.py`
- Modify: `tests/v3/parsers/test_docx_parser.py` (append)
- Modify: `src/trust_generator/v3/parsers/docx_parser.py` (only as needed to make tests pass; the bulk of the helper landed in Cycle 4b Refactor)

**Threshold verdicts:**
- design_surface_threshold: contract surface (`_apply_post_promotion_protocol`) external consumers (the `pdf` sibling) depend on; mutation tests pin behavior the spec's review pass 2 explicitly called out (F1 None-gate). Satisfies the criterion.
- refactor_threshold: **none met — green output is already minimal**. The helper landed in Cycle 4b Refactor; Cycle 5's Green body is at most a one-line fix per parametrization (e.g., the None-gate branch under F1) and is structurally already correct.

**Scope:** codify the §6.2.3 invariants the upstream `promote_seed` spec specifies, parametrized over the four `(seed, parsed) ∈ {(JT,MR), (IN,UM), (JT,MR), (IN,MR)} × {(IN,UM), (JT,MR), (IN,MR), (JT,MR)}` combinations from spec §5.3 step 4 "combinatorial cycle-5 coverage." Each combination is a discrete cell — the test parametrization is the source of truth for which seed/parsed pair maps to which expected captions and `co_grantor` materialization.

**Spec §5.3 step 4 amendment — verbatim from chore #37 (open as of 2026-05-18; lead-approved 2026-05-18, commit 2bc05da; chore body carries the load-bearing text reproduced below).** The amendment is inserted as a new bullet between §5.3 step 4's existing materialization rule and the preservation rule. The existing "If `co_grantor` is already populated, preserve it ..." sentence remains as the fallback when the dematerialization branch does NOT fire.

> **Dematerialization branch:** if the post-mutation state is one where `co_grantor` should NOT exist (`trust_type != JOINT` AND `marital_status != MARRIED`) AND `result.co_grantor` is a default-only `GrantorInfo()` (no fields populated beyond schema defaults — check via `result.co_grantor == GrantorInfo()`), dematerialize by setting `result.co_grantor = None`. If `result.co_grantor` is populated (any field differs from schema defaults), preserve it; the populated data is meaningful and dropping it would breach the bounded-context translation invariant.

The amended protocol distinguishes seed-materialized-empty from paralegal-populated `co_grantor`: the former dematerializes on post-mutation no-co_grantor states; the latter is preserved unconditionally per the spec's bounded-context translation invariant. The four §6.7 parametrized rows produce the documented `expected_co_grantor_present` values under this amended rule:

| Row | Seed | Parsed | Post-mutation state | Seed-side co_grantor | Branch fired | Expected |
|---|---|---|---|---|---|---|
| `jt_mr_to_in_um` | (JT, MR) | (IN, UM) | `trust_type=IN, marital_status=UM` → no co_grantor required | `GrantorInfo()` (default-only, from JT-side materialization in promote_seed) | **dematerialize** | `False` |
| `in_um_to_jt_mr` | (IN, UM) | (JT, MR) | `trust_type=JT, marital_status=MR` → co_grantor required | `None` (IN+UM seed produces no co_grantor) | **materialize** | `True` |
| `jt_mr_to_in_mr` | (JT, MR) | (IN, MR) | `trust_type=IN, marital_status=MR` → co_grantor required | `GrantorInfo()` (default-only) | none (preservation fallback) | `True` |
| `in_mr_to_jt_mr` | (IN, MR) | (JT, MR) | `trust_type=JT, marital_status=MR` → co_grantor required | `GrantorInfo()` (default-only, from MR-side materialization in promote_seed) | none (preservation fallback) | `True` |

The third row's preservation outcome looks identical to materialization, but the helper's branch logic differs — the dematerialization condition `trust_type != JOINT AND marital_status != MARRIED` evaluates `True AND False` = `False`, so the elif-branch does not fire. The if-branch's materialization condition `should_have_co_grantor` is `True`, but `result.co_grantor is None` is `False`, so the if-branch does not fire either. Both checks skip and the populated-but-default GrantorInfo() remains in place — that is the preservation fallback. The test asserts `expected_co_grantor_present=True` which the preserved (default-only) instance satisfies via the `is not None` check; field-level identity inside the GrantorInfo() is unchanged.

The §6.7.1 fixture-builder module (`_docx_fixtures.py`) codifies Decision log #20: synthetic fixtures are constructed programmatically with `python-docx` in tests; checked-in binary fixtures are explicitly NOT used.

**Sequencing note on Red / Green:** the Red commit lands the four new test functions inside `tests/v3/parsers/test_docx_parser.py`; they import from `tests.v3.parsers._docx_fixtures`, which does not yet exist. The Red failure is therefore `ModuleNotFoundError: No module named 'tests.v3.parsers._docx_fixtures'`. The Green commit lands the fixture-builder module — at which point the parametrized tests pass-on-arrival because Cycle 4b's `_apply_post_promotion_protocol` helper already covers all four combinatorial branches. This is the §6.3 Cycle 2 pattern (tests-as-regression-guard rather than change-driving) applied to a new dimension: the change-driving artifact is `_docx_fixtures.py` itself, which is a Green-phase implementation file even though it lives under `tests/`. The helper this cycle exercises (`_apply_post_promotion_protocol`) was authored in Cycle 4b; Cycle 5 pins its observable behavior under the spec §5.3 step 4 combinatorial coverage rule.

- [ ] **Step 1: Draft the fixture-builder file (intended Green; do NOT commit yet)**

Open `tests/v3/parsers/_docx_fixtures.py` as a new file with the body below. Hold off on committing — the file is staged behind the Red commit so the failure surface in Step 3 is unambiguous.

```python
"""Programmatic .docx fixture builder for parser tests.

Decision log #20 (spec §6.7.1): synthetic docx fixtures are constructed
in-test via python-docx's `Document()` API. Checked-in fixture binaries
are explicitly NOT used because:

1. Programmatic construction couples fixture content to parser
   expectations directly in the test source — changes to parser
   table-detection logic can be reflected in the fixture builder in
   the same commit.
2. Binary fixtures drift silently when the parser's expectations
   change; the diff becomes opaque.

The builder emits .docx files into a caller-supplied tmp_path and
returns the path. Each kwarg controls one section of the v2.2
questionnaire layout; absent kwargs produce no content for that
section. Expand kwargs as cycles 5 / 6 surface needs — adding a kwarg
is a Refactor-class change, not a behavior change, and lands in the
cycle whose Red phase first references it.
"""

from __future__ import annotations

from pathlib import Path

from docx import Document  # type: ignore[import-untyped]


def make_docx_with(
    tmp_path: Path,
    *,
    trust_type: str | None = None,  # raw cell text, e.g. "Joint" / "Individual"
    marital_status: str | None = None,  # raw cell text, e.g. "Married" / "Unmarried"
    grantor_name: str | None = None,
    co_grantor_name: str | None = None,
    children: list[tuple[str, str]] | None = None,  # (name, dob)
    successor_trustees: list[str] | None = None,
    beneficiary_shares: list[tuple[str, str]] | None = None,  # (name, share-percent)
    other_beneficiaries: list[str] | None = None,
    exclusions: str | None = None,  # v2 text-block free text
) -> Path:
    """Construct a minimal .docx with table rows wired to specified content.

    Each kwarg controls one table or paragraph block per the v2.2
    questionnaire layout. Returns a path under tmp_path. The .docx
    structure mirrors the v2.2 layout closely enough that the parser's
    table-detection logic (ported in Cycle 4b) walks it identically.
    """
    out = tmp_path / "fixture.docx"
    doc = Document()

    # Trust-type / marital-status checkbox table (one row per option,
    # with an "X" marker in the chosen row's first cell — the v2.2
    # _CHECKBOX_MAP convention).
    if trust_type is not None or marital_status is not None:
        table = doc.add_table(rows=2, cols=2)
        if trust_type is not None:
            table.cell(0, 0).text = "X"
            table.cell(0, 1).text = f"This is a {trust_type} trust"
        if marital_status is not None:
            table.cell(1, 0).text = "X"
            table.cell(1, 1).text = f"Grantor is {marital_status}"

    # Grantor / co_grantor name rows.
    if grantor_name is not None or co_grantor_name is not None:
        name_tbl = doc.add_table(rows=2, cols=2)
        if grantor_name is not None:
            name_tbl.cell(0, 0).text = "Grantor full legal name"
            name_tbl.cell(0, 1).text = grantor_name
        if co_grantor_name is not None:
            name_tbl.cell(1, 0).text = "Co-grantor full legal name"
            name_tbl.cell(1, 1).text = co_grantor_name

    # Children table.
    if children:
        child_tbl = doc.add_table(rows=len(children), cols=2)
        for row_idx, (name, dob) in enumerate(children):
            child_tbl.cell(row_idx, 0).text = name
            child_tbl.cell(row_idx, 1).text = dob

    # Successor-trustees table.
    if successor_trustees:
        tr_tbl = doc.add_table(rows=len(successor_trustees), cols=1)
        for row_idx, name in enumerate(successor_trustees):
            tr_tbl.cell(row_idx, 0).text = name

    # Beneficiary-shares table.
    if beneficiary_shares:
        bs_tbl = doc.add_table(rows=len(beneficiary_shares), cols=2)
        for row_idx, (name, share) in enumerate(beneficiary_shares):
            bs_tbl.cell(row_idx, 0).text = name
            bs_tbl.cell(row_idx, 1).text = share

    # Other-beneficiaries table.
    if other_beneficiaries:
        ob_tbl = doc.add_table(rows=len(other_beneficiaries), cols=1)
        for row_idx, name in enumerate(other_beneficiaries):
            ob_tbl.cell(row_idx, 0).text = name

    # Exclusions paragraph (v2 text-block free text; parsed as the
    # parser-internal exclusions_string carrier per F3 finding).
    if exclusions is not None:
        doc.add_paragraph(f"Exclusions: {exclusions}")

    doc.save(str(out))
    return out
```

The exact label strings (e.g. `"Grantor full legal name"`, `"This is a {trust_type} trust"`, `"Exclusions:"`) MUST match the labels the parser's `_HINTS` / table-row-detection logic recognizes when ported in Cycle 4b. Cross-check by reading the v2 docx parser body (`src/trust_generator/v2/parsers/docx_parser.py:64-176`) and adopt the v2 phrasings verbatim. If a phrasing drift is unavoidable (e.g., v3's `co_grantor` row had no v2 analogue under the same label), document the chosen phrasing in the helper's docstring and reflect the same phrasing in the Cycle 4b port.

- [ ] **Step 2: Write the failing tests (Red)**

Append to `tests/v3/parsers/test_docx_parser.py`:

```python
from trust_generator.v3.schema import GrantorInfo

from tests.v3.parsers._docx_fixtures import make_docx_with


def test_grantor_info_default_constructor_equality_is_deterministic():
    """Pinned precondition for the chore #37 dematerialization branch.

    The dematerialization branch in `_apply_post_promotion_protocol`
    checks `result.co_grantor == GrantorInfo()` to detect a
    seed-materialized-empty co_grantor. This relies on Pydantic v2
    BaseModel field-equality being deterministic for default-constructed
    GrantorInfo instances.

    A future schema change that introduces a non-deterministic default
    (e.g., `default_factory=uuid.uuid4` or `default_factory=datetime.now`)
    would silently break the branch: `GrantorInfo() != GrantorInfo()` and
    the elif-branch never fires, leaving seed-materialized-empty
    co_grantors in place across (IN, UM) transitions. This single-line
    test catches the regression at the next pixi run test.

    If this test ever fails, fix the branch by switching the equality
    check to `result.co_grantor.model_dump(exclude_defaults=True) == {}`,
    which is robust against non-deterministic defaults.
    """
    assert GrantorInfo() == GrantorInfo()


@pytest.mark.parametrize(
    (
        "seed_state",
        "parsed_state",
        "expected_grantor_caption",
        "expected_co_grantor_caption",
        "expected_co_grantor_present",
    ),
    [
        # (JT, MR) -> (IN, UM): joint mutation — both fields change; captions
        # collapse to individual; default-only co_grantor dematerializes.
        # Under spec §5.3 step 4 as amended by chore #37 (2026-05-18):
        # seed (JT, MR) → promote_seed materializes co_grantor = GrantorInfo()
        # (default-only). Parser sees (IN, UM); post-mutation state requires
        # no co_grantor; the current GrantorInfo() compares equal to
        # GrantorInfo() under Pydantic field-equality → dematerialization
        # branch fires → result.co_grantor ← None.
        (
            (TrustType.JOINT, MaritalStatus.MARRIED),
            (TrustType.INDIVIDUAL, MaritalStatus.UNMARRIED),
            "Grantor",
            "Spouse",
            False,  # default-only co_grantor dematerialized per chore #37
        ),
        # (IN, UM) -> (JT, MR): re-materialization — co_grantor was None
        # after promote_seed (IN+UM), and the joint transition flips it to
        # GrantorInfo().
        (
            (TrustType.INDIVIDUAL, MaritalStatus.UNMARRIED),
            (TrustType.JOINT, MaritalStatus.MARRIED),
            "Grantor A",
            "Grantor B",
            True,
        ),
        # (JT, MR) -> (IN, MR): caption-only mutation; co_grantor preserved
        # (materialized by promote_seed for the seed-side joint state).
        (
            (TrustType.JOINT, MaritalStatus.MARRIED),
            (TrustType.INDIVIDUAL, MaritalStatus.MARRIED),
            "Grantor",
            "Spouse",
            True,
        ),
        # (IN, MR) -> (JT, MR): caption mutation; co_grantor preserved
        # (materialized by promote_seed for the seed-side married state).
        (
            (TrustType.INDIVIDUAL, MaritalStatus.MARRIED),
            (TrustType.JOINT, MaritalStatus.MARRIED),
            "Grantor A",
            "Grantor B",
            True,
        ),
    ],
    ids=["jt_mr_to_in_um", "in_um_to_jt_mr", "jt_mr_to_in_mr", "in_mr_to_jt_mr"],
)
def test_post_promotion_protocol_combinatorial(
    seed_state,
    parsed_state,
    expected_grantor_caption,
    expected_co_grantor_caption,
    expected_co_grantor_present,
    tmp_path,
):
    """All four (seed, parsed) trust_type/marital_status combinations apply
    correctly per spec §5.3 step 4. Combinatorial cycle-5 coverage rule.
    """
    from trust_generator.v3.parsers.docx_parser import parse_docx

    seed_trust_type, seed_marital = seed_state
    parsed_trust_type, parsed_marital = parsed_state

    seed = QuestionnaireSeed(trust_type=seed_trust_type, marital_status=seed_marital)
    seed_initialized = promote_seed(seed)

    # The fixture's checkbox rows encode the parsed state.
    fixture = make_docx_with(
        tmp_path,
        trust_type="Joint" if parsed_trust_type == TrustType.JOINT else "Individual",
        marital_status="Married" if parsed_marital == MaritalStatus.MARRIED else "Unmarried",
    )

    result = parse_docx(fixture, seed_initialized)

    assert result.trust_id.trust_type == parsed_trust_type
    assert result.trust_id.marital_status == parsed_marital
    assert result.trust_id.grantor_caption == expected_grantor_caption
    assert result.trust_id.co_grantor_caption == expected_co_grantor_caption
    assert (result.co_grantor is not None) == expected_co_grantor_present


def test_post_promotion_protocol_none_gate_preserves_seed_value(tmp_path):
    """F1 finding (plan-review pass 2): parsed-None means "no mutation
    requested"; the seed-initialized value persists. The None-gate is
    load-bearing because trust_type is a required schema field — assigning
    None would breach Pydantic validation.

    Fixture has no trust_type / marital_status checkboxes; the parser's
    flat-key extraction emits None for both. The seed-initialized state
    (JT+MR captions, materialized co_grantor) is unchanged.
    """
    from trust_generator.v3.parsers.docx_parser import parse_docx

    seed = QuestionnaireSeed(
        trust_type=TrustType.JOINT,
        marital_status=MaritalStatus.MARRIED,
    )
    seed_initialized = promote_seed(seed)
    fixture = make_docx_with(tmp_path)  # no trust_type / marital_status rows

    result = parse_docx(fixture, seed_initialized)

    assert result.trust_id.trust_type == TrustType.JOINT
    assert result.trust_id.marital_status == MaritalStatus.MARRIED
    assert result.trust_id.grantor_caption == "Grantor A"
    assert result.trust_id.co_grantor_caption == "Grantor B"
    assert result.co_grantor is not None


def test_parser_preserves_populated_co_grantor_on_marital_transition(tmp_path):
    """Already-populated co_grantor survives a marital_status change.

    Spec §5.3 step 4 sub-bullet: "If co_grantor is already populated,
    preserve it (the populated data is meaningful; the mutation decided
    the grantor exists, not what their identity is)."
    """
    from trust_generator.v3.parsers.docx_parser import parse_docx

    seed = QuestionnaireSeed(
        trust_type=TrustType.JOINT,
        marital_status=MaritalStatus.MARRIED,
    )
    seed_initialized = promote_seed(seed)
    # Populate co_grantor BEFORE parsing — simulates a downstream caller
    # that filled co_grantor identity from a prior workflow.
    seed_initialized.co_grantor = GrantorInfo(full_legal_name="Jane Doe")
    snapshot_co_grantor = seed_initialized.co_grantor.model_copy(deep=True)

    fixture = make_docx_with(
        tmp_path,
        trust_type="Individual",  # transition to IN+MR — keeps co_grantor required
        marital_status="Married",
    )

    result = parse_docx(fixture, seed_initialized)

    assert result.trust_id.trust_type == TrustType.INDIVIDUAL
    assert result.trust_id.marital_status == MaritalStatus.MARRIED
    assert result.co_grantor is not None
    assert result.co_grantor.full_legal_name == "Jane Doe"
    # P3 invariant: caller's seed_initialized.co_grantor is field-level
    # equal pre- vs. post-call.
    assert seed_initialized.co_grantor == snapshot_co_grantor


def test_parser_preserves_populated_co_grantor_under_dematerialization_target(
    tmp_path,
):
    """Chore #37 preservation rule: a POPULATED co_grantor survives a
    (JT, MR) → (IN, UM) transition even though the post-mutation state
    requires no co_grantor.

    The dematerialization branch fires only when the current co_grantor
    is field-equal to GrantorInfo() (default-only). Any populated field
    breaks the equality → preservation fallback → co_grantor retained.
    This is the regression guard for the chore #37 amendment's
    "populated data is meaningful" carve-out: parsers must not drop
    paralegal-supplied co_grantor identity when a competing trust-type
    or marital-status mutation would otherwise dematerialize the slot.
    """
    from trust_generator.v3.parsers.docx_parser import parse_docx

    seed = QuestionnaireSeed(
        trust_type=TrustType.JOINT,
        marital_status=MaritalStatus.MARRIED,
    )
    seed_initialized = promote_seed(seed)
    seed_initialized.co_grantor = GrantorInfo(full_legal_name="Jane Doe")
    snapshot_co_grantor = seed_initialized.co_grantor.model_copy(deep=True)

    fixture = make_docx_with(
        tmp_path,
        trust_type="Individual",
        marital_status="Unmarried",
    )

    result = parse_docx(fixture, seed_initialized)

    # Post-mutation state requires no co_grantor, but the populated
    # identity is preserved by the chore #37 carve-out.
    assert result.trust_id.trust_type == TrustType.INDIVIDUAL
    assert result.trust_id.marital_status == MaritalStatus.UNMARRIED
    assert result.co_grantor is not None
    assert result.co_grantor.full_legal_name == "Jane Doe"
    # P3 invariant: caller's seed_initialized.co_grantor field-level equal
    # pre- vs. post-call.
    assert seed_initialized.co_grantor == snapshot_co_grantor


def test_parser_never_reinvokes_promote_seed(tmp_path):
    """Spec §5.3 step 4 ("parsers do not call promote_seed under any branch")
    and §4 P1 invariant ("parsers never re-invoke promote_seed").
    """
    from unittest.mock import patch

    seed = QuestionnaireSeed(
        trust_type=TrustType.JOINT,
        marital_status=MaritalStatus.MARRIED,
    )
    seed_initialized = promote_seed(seed)
    fixture = make_docx_with(
        tmp_path,
        trust_type="Individual",
        marital_status="Unmarried",
    )

    with patch(
        "trust_generator.v3.parsers.docx_parser.promote_seed"
    ) as mock_promote:
        from trust_generator.v3.parsers.docx_parser import parse_docx
        parse_docx(fixture, seed_initialized)
        assert mock_promote.call_count == 0
```

- [ ] **Step 3: Run tests to verify they fail (Red)**

With `_docx_fixtures.py` not yet staged into the working tree (or staged but not committed), run:

`pixi run test -- tests/v3/parsers/test_docx_parser.py -v -k "post_promotion or never_reinvoke or populated_co_grantor"`

Expected: `ModuleNotFoundError: No module named 'tests.v3.parsers._docx_fixtures'` at collection time on every appended test. This is the Red signal — change-driving for the fixture-builder module.

If `_docx_fixtures.py` is already present at the file-system level from Step 1's drafting, temporarily move it out (`git stash`-equivalent) before running the Red verification so the collection-time `ModuleNotFoundError` actually fires. Restore the file before the Green commit. Skipping the Red verification breaks the `development-strategy.md` `<stage name="red">` requirement; do not gloss past it.

Once the fixture builder is in place (Step 4 / Green commit) the failure surface shifts to per-parametrization:
- `test_post_promotion_protocol_combinatorial[jt_mr_to_in_um]`: passes IF the Cycle 4b Refactor correctly populates `parsed_trust_type` from the checkbox (the test depends on `_CHECKBOX_MAP` recognizing the fixture's "This is a Joint trust" / "This is a Individual trust" phrasings). If the `_CHECKBOX_MAP` entries don't match the fixture's phrasings, ALL four parametrizations fail with `parsed_trust_type=None` (which the F1 None-gate then preserves the seed for) — the failure mode points at the fixture/parser-label coupling.
- `test_post_promotion_protocol_none_gate_preserves_seed_value`: passes IF Cycle 4b's body correctly emits `parsed_trust_type=None` for a fixture without the checkbox rows — this is already true after Cycle 4b Green.
- `test_parser_preserves_populated_co_grantor_on_marital_transition`: passes (the §5.3 step 4 helper preserves a populated `co_grantor` by construction — the helper only materializes when `result.co_grantor is None`).
- `test_parser_never_reinvokes_promote_seed`: passes only if `docx_parser.py` imports `promote_seed` at module level so the `patch` site resolves. The Cycle 4b Green body imports `_resolve_captions` from `trust_generator.v3.schema` but does not import `promote_seed`; the patch site as written would fail with `AttributeError: module 'trust_generator.v3.parsers.docx_parser' has no attribute 'promote_seed'`. Adjust:

Add to the imports at the top of `src/trust_generator/v3/parsers/docx_parser.py`:

```python
from trust_generator.v3.schema import (
    GrantorInfo,
    MaritalStatus,
    TrustData,
    TrustType,
    _resolve_captions,
    promote_seed,  # imported (for patch-site visibility) but NEVER called
)
```

Add a `__all__` export tuple at module level to silence the unused-import warning that ruff would flag:

```python
__all__ = ("parse_docx",)
```

The `promote_seed` import is intentional — it makes the patch target real without polluting `parse_docx`'s behavior. Document the intent in a module-level comment:

```python
# `promote_seed` is imported to give `test_parser_never_reinvokes_promote_seed`
# a real patch site (per spec §6.7's contract test). The parser MUST NOT call
# it; the test asserts call_count == 0.
```

Even cleaner: use `# noqa: F401` on the unused import and skip the `__all__` workaround — ruff's preview mode tolerates the noqa annotation.

- [ ] **Step 4: Land the fixture builder + run tests to verify they pass (Green)**

The Green commit lands `tests/v3/parsers/_docx_fixtures.py` (the file drafted in Step 1). With that file in place, the four appended test functions resolve their imports and pass-on-arrival against Cycle 4b's already-committed `_apply_post_promotion_protocol` helper.

If the parametrized combinatorial test fails because the `_CHECKBOX_MAP` doesn't recognize the fixture's trust-type phrasings, add the missing entries to `_CHECKBOX_MAP` in `docx_parser.py` in the same Green commit. The Cycle 4b port should already cover the v2.2 phrasings; if the fixture's `"This is a Joint trust"` / `"This is a Individual trust"` phrasings drift from v2.2, prefer adjusting the fixture builder's emitted phrasings to match the parser's expected labels (the parser's labels are authoritative — they come from v2.2 questionnaire content).

The N=4 combinatorial cases the parametrization MUST exercise:
1. **(JT, MR) → (IN, UM)** asserts both fields mutate and captions collapse to `"Grantor"` / `"Spouse"`. The co_grantor — which `promote_seed` materialized as part of (JT, MR) — is preserved (the populated-data rule applies even when "populated" means "empty GrantorInfo()").
2. **(IN, UM) → (JT, MR)** asserts both fields mutate AND `co_grantor` materializes from None to `GrantorInfo()` (the re-materialization branch).
3. **(JT, MR) → (IN, MR)** asserts caption-only mutation (`trust_type` changes; `marital_status` unchanged → only the caption assignment fires) with `co_grantor` preservation.
4. **(IN, MR) → (JT, MR)** asserts caption mutation across a marital-equivalent transition (`marital_status` already MR; only `trust_type` changes).

The Cycle 4b Refactor helper already handles all four branches correctly. The Cycle 5 Green obligation is to ensure (a) the `_CHECKBOX_MAP` phrasings in the parser match the fixture's emitted phrasings, and (b) the F1 None-gate is exercised by the dedicated `_none_gate_preserves_seed_value` test.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pixi run test -- tests/v3/parsers/test_docx_parser.py -v`

Expected: all parametrized cases pass; the None-gate test passes; the populated-co_grantor preservation test passes; the never-reinvoke test passes.

Run: `pixi run check`

Expected: full gate green.

- [ ] **Step 6: Commit Red**

Stage ONLY the test file (the fixture builder stays out of this commit so the Red signal is collection-time `ModuleNotFoundError`):

```bash
git add tests/v3/parsers/test_docx_parser.py
git commit -m "test(v3/parsers): pin combinatorial post-promotion + F1 None-gate + P1 never-reinvoke (Red, cycle 5)"
```

If `docx_parser.py` needed the `from trust_generator.v3.schema import promote_seed  # noqa: F401` line added so the never-reinvoke patch site resolves, that source-file edit belongs in the Cycle 4b Refactor commit's amendment or — if Cycle 4b has already landed — in the Green commit below alongside the fixture builder. Do NOT bundle it into this Red commit; Red is tests-only.

- [ ] **Step 7: Commit Green**

```bash
git add tests/v3/parsers/_docx_fixtures.py src/trust_generator/v3/parsers/docx_parser.py
git commit -m "feat(v3/parsers): introduce _docx_fixtures builder for combinatorial post-promotion coverage (Green, cycle 5)"
```

The Green commit lands the fixture-builder module (the change-driving artifact for Cycle 5) plus any `_CHECKBOX_MAP` / `promote_seed`-patch-site adjustments to `docx_parser.py` the Red commit's failing tests surfaced. If `docx_parser.py` required no edits, drop it from the `git add` line; the fixture builder alone is sufficient to satisfy `<stage name="green" required="always">` because it is the file the Red commit's `ModuleNotFoundError` named as missing.

- [ ] **Step 8: Refactor — none expected**

Per `refactor_threshold`: the helper is small and was extracted in Cycle 4b. Cycle 5 adds tests, not structural code; the `refactor_threshold` criteria (structural duplication, nested conditionals, mixed concerns) are not met. Explicitly note "no refactor stage — green output is already minimal; helper extraction landed in Cycle 4b" in the cycle summary.

---

## Cycle 6 — docx parser coercion integration [spec §6.8]

**Files:**
- Modify: `src/trust_generator/v3/parsers/docx_parser.py` (wire `coercion._to_*` helpers; add `_apply_post_merge_resolution` helper)
- Modify: `tests/v3/parsers/test_docx_parser.py` (append)
- Modify (if needed): `tests/v3/parsers/_docx_fixtures.py` (kwargs may need expansion to support malformed-date / corporate-trustee / etc. fixtures)

**Threshold verdicts:**
- design_surface_threshold: composition of multiple already-tested units (the four `_to_*` coercion helpers from `json-and-coercion` Cycle 3) plus a non-obvious failure mode (the F2 fixed iteration order pin and the F4 multi-match WARNING) worth pinning. Satisfies the criterion.
- refactor_threshold: **none met — green output is already minimal**. The coercion helpers were authored in `json-and-coercion`; Cycle 6's Green body is field-by-field call sites that consume them, plus the `_apply_post_merge_resolution` helper. No structural duplication that warrants extraction beyond the helper already factored out per spec §5.3's implementation note.

**Cross-plan note:** the four `coercion._to_*` helpers are imported (read-only) from `trust_generator.v3.parsers.coercion`. The exact signatures (return types `date | None` / `Decimal` / `Address` / `PersonReference`; soft-fail policies) are pinned by upstream `json-and-coercion` cycle 3. If a signature drift surfaces (e.g., the helper grows a `source_label: str` kwarg), pause and peer-DM `json-and-coercion`:

```json
SendMessage({
  "to": "json-and-coercion",
  "message": "Cycle 6 wiring detected a coercion-helper signature drift. _to_date in coercion.py exposes [signature]; my call site assumes [signature]. Reconcile by [option A: update spec §5.4.1 docstring; option B: my call sites adapt to your signature]. Confirm preference."
})
```

This is a plain-text DM under the peer-DM allowance — not a structured `plan_approval_request`.

- [ ] **Step 1: Write the failing tests (Red)**

Append to `tests/v3/parsers/test_docx_parser.py`:

```python
import logging

from decimal import Decimal


def test_coercion_integration_malformed_date_falls_back_to_None(tmp_path, caplog):
    """A malformed date in a "Grantor date of birth" cell coerces to None
    and emits a log.warning. The parse succeeds (no exception)."""
    from trust_generator.v3.parsers.docx_parser import parse_docx

    fixture = make_docx_with(
        tmp_path,
        grantor_name="John Andrew Doe",
        children=[("Alice Doe", "sometime in 2010")],  # unparseable date
    )
    seed = QuestionnaireSeed(
        trust_type=TrustType.JOINT,
        marital_status=MaritalStatus.MARRIED,
    )
    seed_initialized = promote_seed(seed)

    with caplog.at_level(logging.WARNING, logger="trust_generator.v3.parsers"):
        result = parse_docx(fixture, seed_initialized)

    assert result.grantor.full_legal_name == "John Andrew Doe"
    assert len(result.children) == 1
    assert result.children[0].full_legal_name == "Alice Doe"
    assert result.children[0].date_of_birth is None
    assert any("could not parse date" in rec.message.lower() for rec in caplog.records)


def test_coercion_integration_one_token_corporate_trustee_routes_to_CorporateTrustee(
    tmp_path, caplog
):
    """A one-token trustee name matching the §5.4.9 entity heuristic
    routes to CorporateTrustee with an INFO log."""
    from trust_generator.v3.parsers.docx_parser import parse_docx
    from trust_generator.v3.schema import CorporateTrustee

    fixture = make_docx_with(
        tmp_path,
        successor_trustees=["First National Bank"],
    )
    seed = QuestionnaireSeed(
        trust_type=TrustType.JOINT,
        marital_status=MaritalStatus.MARRIED,
    )
    seed_initialized = promote_seed(seed)

    with caplog.at_level(logging.INFO, logger="trust_generator.v3.parsers"):
        result = parse_docx(fixture, seed_initialized)

    assert len(result.successor_trustees) == 1
    assert isinstance(result.successor_trustees[0], CorporateTrustee)
    assert result.successor_trustees[0].entity_name == "First National Bank"
    assert any(
        "discriminated as CorporateTrustee" in rec.message
        or "CorporateTrustee" in rec.message
        for rec in caplog.records
    )


def test_coercion_integration_placeholder_prefix_stripped_from_person_reference(
    tmp_path,
):
    """A v2-corpus cell typed beside a bracketed hint (per spec §5.4.4 +
    Decision log #12) has the prefix stripped before _to_person_reference."""
    from trust_generator.v3.parsers.docx_parser import parse_docx

    fixture = make_docx_with(
        tmp_path,
        co_grantor_name="[Spouse's full legal name] Jane Doe",
    )
    seed = QuestionnaireSeed(
        trust_type=TrustType.JOINT,
        marital_status=MaritalStatus.MARRIED,
    )
    seed_initialized = promote_seed(seed)

    result = parse_docx(fixture, seed_initialized)

    assert result.co_grantor is not None
    assert result.co_grantor.full_legal_name == "Jane Doe"


def test_coercion_integration_disinherit_multi_match_warns_and_picks_iteration_order(
    tmp_path, caplog
):
    """F4 finding (plan-review pass 2): a v2 exclusions token matching
    multiple beneficiaries across the fixed iteration order
    (children → descendants → other_beneficiaries) emits exactly one
    disinherit flip on the iteration-order-first match plus one WARNING
    naming both candidates.

    Concrete example pinned by spec F4 / §5.4.10:
      Token: "John"
      Match candidates: "John Smith" (children), "Johnny Doe" (other_beneficiaries)
      Expected: "John Smith".disinherit = True; "Johnny Doe".disinherit = False;
                exactly one WARNING naming both names.
    """
    from trust_generator.v3.parsers.docx_parser import parse_docx

    fixture = make_docx_with(
        tmp_path,
        children=[("John Smith", "2010-01-01")],
        other_beneficiaries=["Johnny Doe"],
        exclusions="John",
    )
    seed = QuestionnaireSeed(
        trust_type=TrustType.JOINT,
        marital_status=MaritalStatus.MARRIED,
    )
    seed_initialized = promote_seed(seed)

    with caplog.at_level(logging.WARNING, logger="trust_generator.v3.parsers"):
        result = parse_docx(fixture, seed_initialized)

    # F2 iteration-order pin (plan-review pass 2): children first.
    assert len(result.children) == 1
    assert result.children[0].full_legal_name == "John Smith"
    assert result.children[0].disinherit is True
    assert result.children[0].disinherit_reason == "John"

    # The other_beneficiaries entry retains disinherit=False.
    assert len(result.other_beneficiaries) == 1
    assert result.other_beneficiaries[0].full_legal_name == "Johnny Doe"
    assert result.other_beneficiaries[0].disinherit is False

    # Exactly one WARNING naming both candidates.
    multi_match_warnings = [
        rec
        for rec in caplog.records
        if rec.levelno == logging.WARNING
        and "John Smith" in rec.message
        and "Johnny Doe" in rec.message
    ]
    assert len(multi_match_warnings) == 1


def test_coercion_integration_unmatched_exclusion_token_flows_to_external_exclusions(
    tmp_path,
):
    """Spec §5.4.10 algorithm step 4: an exclusions token with no beneficiary
    match flows to result.external_exclusions as a PersonReference, with
    result.external_exclusion_reasons[token] = token."""
    from trust_generator.v3.parsers.docx_parser import parse_docx

    fixture = make_docx_with(
        tmp_path,
        children=[("Alice Doe", "2010-01-01")],
        exclusions="Bob Roe",  # no match in children / descendants / other_beneficiaries
    )
    seed = QuestionnaireSeed(
        trust_type=TrustType.JOINT,
        marital_status=MaritalStatus.MARRIED,
    )
    seed_initialized = promote_seed(seed)

    result = parse_docx(fixture, seed_initialized)

    assert len(result.external_exclusions) == 1
    assert result.external_exclusions[0].full_legal_name == "Bob Roe"
    assert result.external_exclusion_reasons.get("Bob Roe") == "Bob Roe"
    # The unmatched-only case must NOT flip any beneficiary's disinherit.
    assert result.children[0].disinherit is False


def test_coercion_integration_unparseable_currency_falls_back_to_decimal_zero(
    tmp_path, caplog
):
    """Asset-value Decimal coercion failure → Decimal(0) per spec §5.4.2;
    a log.warning is emitted. (Share-percent fields drop the row instead;
    that branch is covered by upstream `json-and-coercion` Cycle 3 tests.)
    """
    from trust_generator.v3.parsers.docx_parser import parse_docx

    fixture = make_docx_with(
        tmp_path,
        # Real-property row with unparseable value cell. The fixture
        # builder may need expansion to support this; if so, document
        # the kwarg addition here and update _docx_fixtures.py in the
        # same Red commit.
        beneficiary_shares=[("Alice Doe", "a lot")],
    )
    seed = QuestionnaireSeed(
        trust_type=TrustType.JOINT,
        marital_status=MaritalStatus.MARRIED,
    )
    seed_initialized = promote_seed(seed)

    with caplog.at_level(logging.WARNING, logger="trust_generator.v3.parsers"):
        result = parse_docx(fixture, seed_initialized)

    # Share-percent row should be DROPPED per spec §5.4.2 share-percent
    # branch (Decision log #11), NOT coerced to Decimal(0). Assert empty.
    assert result.beneficiary_shares == []
    assert any("could not parse" in rec.message.lower() for rec in caplog.records)
```

If `_docx_fixtures.make_docx_with` lacks the kwargs the above tests need (e.g., a `real_properties` kwarg for the §5.4.2 asset-value branch — note the test above narrowed scope to the share-percent branch via `beneficiary_shares`, which the existing kwarg already supports, but a true asset-value Decimal(0) regression would need a `real_properties` kwarg), expand the helper here and document the kwarg addition in the Red commit. The expansion is mechanical — add the kwarg signature, add the table-emission block.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pixi run test -- tests/v3/parsers/test_docx_parser.py -v -k coercion_integration`

Expected: every coercion-integration test fails. The failure modes vary:
- `malformed_date_falls_back_to_None`: AttributeError or AssertionError because Cycle 4b/5's Green body never wires `_to_date` — the `children[0].date_of_birth` field assignment is either absent or raises Pydantic ValidationError on the raw string.
- `corporate_trustee_routes_to_CorporateTrustee`: AssertionError because Cycle 4b/5's Green body has no §5.4.9 entity-heuristic branch — trustees populate as `SuccessorTrustee` uniformly.
- `placeholder_prefix_stripped_from_person_reference`: AssertionError because Cycle 4b/5's Green body assigns the raw cell text — the bracketed prefix is preserved.
- `disinherit_multi_match_warns_and_picks_iteration_order`: AssertionError because Cycle 4b/5's Green body has no §5.4.10 post-merge resolution pass — no disinherit flips, no external_exclusions entries.
- `unmatched_exclusion_token_flows_to_external_exclusions`: same root cause as above.
- `unparseable_currency_falls_back_to_decimal_zero`: AssertionError because the share-percent drop-row rule is not wired (the test asserts the row is dropped per the share-percent branch).

- [ ] **Step 3: Write minimal implementation (Green)**

Expand `src/trust_generator/v3/parsers/docx_parser.py` to:

1. Import the four `_to_*` coercion helpers from `trust_generator.v3.parsers.coercion`.
2. Replace direct raw-string field assignments with `_to_date(...)`, `_to_decimal(...)`, `_to_address(...)`, `_to_person_reference(...)` calls at the relevant call sites.
3. For placeholder-prefix stripping (spec §5.4.4): `_to_person_reference` should strip the `\[[^\]]+\]\s*` prefix internally per Decision log #12 — verify in `json-and-coercion`'s Cycle 3 test that this rule is wired upstream; if it isn't, peer-DM `json-and-coercion` to reconcile.
4. For CorporateTrustee discrimination (spec §5.4.9): land the `_ENTITY_NAME_PATTERN` regex and the `_is_entity_name(name)` module-level helper. Do NOT call `_is_entity_name` from the step-5 field-assignment loop — `parse_docx` constructs bare `SuccessorTrustee(full_legal_name=name, ...)` instances during step 5. The §5.4.9 re-detection + `CorporateTrustee` re-construction + `log.info` emission all happen inside `_apply_post_merge_resolution` (per the cross-parser signature contract reconciled with the `pdf` sibling on 2026-05-18; spec §5.3 step 6 covers the placement, and the parser-agnostic 2-arg helper signature is the contract surface both consumers depend on).
5. For the share-percent drop-row rule (spec §5.4.2): when `_to_decimal` returns `Decimal(0)` for a share-percent cell, drop the row entirely AND emit a log.warning. The drop rule MUST be applied at the row-construction site in `parse_docx` — not inside `_to_decimal` (which has no context about whether the field is share-percent or asset-value).
6. Add the `_apply_post_merge_resolution(result, exclusions_string)` helper per spec §5.3 implementation note (2-arg signature is the cross-parser contract; sibling `pdf`'s cycle 7 imports and invokes this exact symbol). Body implements §5.4.10's name-matching algorithm with the F2 fixed iteration order (`children` → `descendants` → `other_beneficiaries`, Pydantic insertion order within each list) and the F4 multi-match WARNING, plus the §5.4.9 CorporateTrustee re-construction pass iterating `result.successor_trustees` directly.

Concrete helper body:

```python
import re

from decimal import Decimal

from trust_generator.v3.parsers.coercion import (
    _to_address,
    _to_date,
    _to_decimal,
    _to_person_reference,
)
from trust_generator.v3.schema import (
    CorporateTrustee,
    PersonReference,
    SuccessorTrustee,
)

# Spec §5.4.9 entity-name heuristic. Conservative — known limitation:
# a natural person with surname "Bank" (e.g. "John Bank") is mis-typed.
# The INFO log is the operator-side recovery surface.
_ENTITY_NAME_PATTERN = re.compile(
    r"\b(Bank|Trust Company|Trust Department|N\.A\.|LLC|LLP|Corporation|Corp\.|Inc\.|Insurance Co)\b",
    re.IGNORECASE,
)


def _is_entity_name(name: str) -> bool:
    """§5.4.9 heuristic: does the name look like a corporate-trustee entity?"""
    return bool(_ENTITY_NAME_PATTERN.search(name))


def _apply_post_merge_resolution(
    result: TrustData,
    exclusions_string: str,
) -> None:
    """§5.3 step 6: post-merge resolution passes.

    1. Disinheritance resolution (§5.4.10): tokenize `exclusions_string`
       on commas, semicolons, and newlines; case-insensitive substring
       match against beneficiaries in fixed iteration order:
       children → descendants → other_beneficiaries; first match wins;
       multi-match logs WARNING but does not change the chosen target.
    2. CorporateTrustee discrimination (§5.4.9): iterate
       `result.successor_trustees`, re-apply `_is_entity_name` to each
       entry's `full_legal_name`, and re-construct matching entries as
       `CorporateTrustee` instances. Each discrimination emits an
       INFO log naming the entry.

    Signature contract (binding across parsers, 2026-05-18 peer-DM
    docx ↔ pdf): two arguments only. The parser-agnostic shape avoids
    coupling the helper to docx-side parallel lists or pdf-side
    AcroForm-dict keying. Both consuming parsers (parse_docx here,
    parse_pdf in pdf_parser.py sibling-plan cycle 7) construct
    `SuccessorTrustee(full_legal_name=name)` instances during their
    step 5 field-assignment phase; this helper performs the §5.4.9
    re-construction by re-detecting entity status from the preserved
    name string. Any change to this signature requires coordinated
    re-execution of both consuming cycles.

    F3 (plan-review pass 2): `exclusions_string` is a function-local
    argument — NOT a field on `result`. v3's TrustData has no
    `text_blocks.exclusions` field per `modified_surfaces`.
    """
    # Pass 1: disinheritance resolution.
    if exclusions_string:
        tokens = [
            tok.strip()
            for tok in re.split(r"[,\n;]", exclusions_string)
            if tok.strip()
        ]
        # F2 (plan-review pass 2): fixed iteration order.
        iteration_buckets = [
            ("children", result.children),
            ("descendants", result.descendants),
            ("other_beneficiaries", result.other_beneficiaries),
        ]
        for token in tokens:
            chosen: tuple[str, int, str] | None = None  # (bucket, idx, name)
            secondary_matches: list[tuple[str, str]] = []  # (bucket, name)
            for bucket_name, bucket in iteration_buckets:
                for idx, beneficiary in enumerate(bucket):
                    if token.lower() in beneficiary.full_legal_name.lower():
                        if chosen is None:
                            chosen = (bucket_name, idx, beneficiary.full_legal_name)
                        else:
                            secondary_matches.append((bucket_name, beneficiary.full_legal_name))
            if chosen is None:
                # No match → external_exclusions (§5.4.10 step 4).
                result.external_exclusions.append(PersonReference(full_legal_name=token))
                result.external_exclusion_reasons[token] = token
            else:
                bucket_name, idx, chosen_name = chosen
                bucket = dict(iteration_buckets)[bucket_name]
                bucket[idx].disinherit = True
                bucket[idx].disinherit_reason = token
                if secondary_matches:
                    secondary_names = ", ".join(name for _, name in secondary_matches)
                    log.warning(
                        "Disinheritance multi-match for token %r: chose %r (iteration-order first); secondary candidates: %s",
                        token,
                        chosen_name,
                        secondary_names,
                    )

    # Pass 2: CorporateTrustee discrimination (re-detect from preserved
    # name string; signature-coupling-free across docx / pdf consumers).
    if result.successor_trustees:
        new_trustees: list[SuccessorTrustee | CorporateTrustee] = []
        for trustee in result.successor_trustees:
            if _is_entity_name(trustee.full_legal_name):
                new_trustees.append(
                    CorporateTrustee(
                        is_entity=True,
                        full_legal_name="",
                        entity_name=trustee.full_legal_name,
                    )
                )
                log.info(
                    "Discriminated %r as CorporateTrustee per §5.4.9 heuristic",
                    trustee.full_legal_name,
                )
            else:
                new_trustees.append(trustee)
        result.successor_trustees = new_trustees
```

In `parse_docx`, after the existing `_apply_post_promotion_protocol` call AND after the field-assignment loop, add:

```python
    _apply_post_merge_resolution(result, exclusions_string)
```

Adjust the field-assignment loop's coercion call sites:

```python
    if "grantor.full_legal_name" in flat:
        result.grantor.full_legal_name = flat["grantor.full_legal_name"]
    if "grantor.date_of_birth" in flat:
        result.grantor.date_of_birth = _to_date(flat["grantor.date_of_birth"])
    if "co_grantor.full_legal_name" in flat:
        co_grantor_ref = _to_person_reference(flat["co_grantor.full_legal_name"])
        if result.co_grantor is not None:
            result.co_grantor.full_legal_name = co_grantor_ref.full_legal_name

    # Children, descendants, other_beneficiaries, successor_trustees, etc.
    # follow the same pattern: per-row construction with _to_* coercion
    # plus row-drop on share-percent Decimal failures per §5.4.2.
    for name, dob_str in flat.get("children", []):
        ref = _to_person_reference(name)
        result.children.append(
            Child(
                full_legal_name=ref.full_legal_name,
                is_entity=ref.is_entity,
                entity_name=ref.entity_name,
                date_of_birth=_to_date(dob_str),
            )
        )
    for trustee_name in flat.get("successor_trustees", []):
        ref = _to_person_reference(trustee_name)
        # NOTE: do NOT pre-flag entity status here. The §5.4.9 discrimination
        # + CorporateTrustee re-construction + INFO log all live inside
        # `_apply_post_merge_resolution`, which iterates `result.successor_trustees`
        # directly and re-applies `_is_entity_name`. Keeping the discrimination
        # in one place is the cross-parser contract (peer-DM docx ↔ pdf, 2026-05-18).
        result.successor_trustees.append(
            SuccessorTrustee(
                full_legal_name=ref.full_legal_name,
                is_entity=ref.is_entity,
                entity_name=ref.entity_name,
            )
        )
    for share_name, share_pct_str in flat.get("beneficiary_shares", []):
        share_pct = _to_decimal(share_pct_str)
        if share_pct == Decimal(0):
            log.warning(
                "Dropping beneficiary_shares row for %r: could not parse share-percent %r per §5.4.2",
                share_name,
                share_pct_str,
            )
            continue
        ref = _to_person_reference(share_name)
        result.beneficiary_shares.append(
            BeneficiaryShare(
                recipient_external=ref,
                share_percent=share_pct,
            )
        )
```

Imports to add at the top of the module:

```python
from trust_generator.v3.schema import (
    BeneficiaryShare,
    Child,
    CorporateTrustee,
    GrantorInfo,
    MaritalStatus,
    PersonReference,
    SuccessorTrustee,
    TrustData,
    TrustType,
    _resolve_captions,
    promote_seed,  # noqa: F401 — patch-site for P1 invariant test
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pixi run test -- tests/v3/parsers/test_docx_parser.py tests/v3/parsers/test_assets_integration.py -v`

Expected: all Cycle 4a/4b/5/6 tests pass. The full parser test count for this plan: ~12–15 docx tests + 1 asset-integration test.

Run: `pixi run check`

Expected: full gate green.

Run: `pixi run test` (full suite)

Expected: no regression in other modules. The §5.5 error-policy split (parser warnings vs. diagnostic-engine output) ensures the diagnostics suite remains green.

- [ ] **Step 5: Commit Red**

```bash
git add tests/v3/parsers/test_docx_parser.py tests/v3/parsers/_docx_fixtures.py
git commit -m "test(v3/parsers): pin coercion integration + F2/F4 disinherit multi-match (Red, cycle 6)"
```

- [ ] **Step 6: Commit Green**

```bash
git add src/trust_generator/v3/parsers/docx_parser.py
git commit -m "feat(v3/parsers): wire coercion helpers + _apply_post_merge_resolution (Green, cycle 6)"
```

- [ ] **Step 7: Refactor — none expected**

Per `refactor_threshold`: the green body extracts a single new helper (`_apply_post_merge_resolution`) at write-time, not as a post-hoc refactor — the helper-vs-inline split is dictated by spec §5.3's implementation note ("step 4 lives in `_apply_post_promotion_protocol`; step 6 lives in a separate `_apply_post_merge_resolution` helper"). No additional structural duplication or nested conditional emerges from Cycle 6 Green that warrants a Refactor commit. Explicitly note "no refactor stage — green output already factors the helper at write-time per spec §5.3 implementation note" in the cycle summary.

---

## Exit criteria for this plan

The plan is complete when:

1. All four cycles' Red commits land on the feature branch with the failure messages they were designed to surface.
2. All four cycles' Green commits land such that `pixi run check` (full lint + mypy + test gate) passes after each commit individually.
3. The Cycle 4b Refactor commit lands with `_apply_post_promotion_protocol` extracted as a module-level helper whose signature is documented (the `pdf` sibling depends on this).
4. The plan-md is marked done in the lead's `plans.xml` plan-md attribute update (this is a lead concern per the spec-pipeline invariants, not this plan's executor's).
5. No silent expansions of scope into `src/trust_generator/v3/parsers/__init__.py`, `coercion.py`, `json_parser.py`, `pdf_parser.py`, `registry.py`, or any tests outside the four files in this plan's blast-radius. Items surfaced mid-execution are routed via the `spec-pipeline` scope-maintenance protocol to a chore-entry or a plan-entry, not absorbed into the active cycle.

## Cycle-summary verdict table

| Cycle | Spec § | Red | Green | Refactor verdict |
|---|---|---|---|---|
| 4a | §6.5 | smoke test (parser-absent failure mode) | open-doc + deepcopy-return | none met — already minimal |
| 4b | §6.6 | asset-anchored + synthetic-row extraction | v2-port flat-key extraction + inline post-promotion | **MET** — extract `_apply_post_promotion_protocol` (mixes orthogonal concerns) |
| 5 | §6.7, §6.7.1 | combinatorial 4-case post-promotion + F1 None-gate + P1 never-reinvoke + populated-co_grantor preservation | helper from Cycle 4b already covers all branches; only `_CHECKBOX_MAP` / fixture-phrasing alignment may need adjustment | none met — helper landed in Cycle 4b |
| 6 | §6.8 | coercion-integration tests + F2 iteration order + F4 multi-match WARNING + share-percent drop-row | wire `_to_*` calls + `_apply_post_merge_resolution` helper authored at write-time | none met — helper authored at write-time per spec §5.3 implementation note |

The only Refactor commit in this plan is the Cycle 4b extraction of `_apply_post_promotion_protocol`. Cycles 4a, 5, and 6 explicitly declare "no refactor stage" per `development-strategy.md`'s `refactor_threshold` `if-none-met` rule.
