# Parser Migration — JSON Parser & Coercion Helpers Implementation Plan

> **For agentic workers:** Use `spec-pipeline:plan-executor-team` (member of plan-group `2026-04-23-parser-migration`). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the v3 parser package skeleton, ship the JSON round-trip parser with explicit error surfaces, and land the four pure coercion helpers (`_to_date`, `_to_decimal`, `_to_address`, `_to_person_reference`) that the sibling `docx` and `pdf` plans will consume. Endpoint: `parse_json` is callable, validated against round-trip + error contracts; `coercion.py` exposes four pure helpers with parametrized regression coverage; package `__init__.py` re-exports `parse_json` (the `parse_file` / `parse_docx` / `parse_pdf` exports land in sibling `registry`).

**Architecture:** A new `src/trust_generator/v3/parsers/` package. `json_parser.py` mirrors v2's two-line `model_validate_json` body (Pydantic does the typing work for us — no coercion). `coercion.py` houses four free functions that consume strings produced by docx-cell extraction or PDF-AcroForm reads and emit v3-typed values (`date | None`, `Decimal`, `Address`, `PersonReference`). Coercion helpers are pure (no logging-side-effects beyond `log.warning(...)` on soft-fail per spec §5.5) and exhaustively unit-tested via `pytest.mark.parametrize`. No `base.py` ABC — see spec §5.1.

**Tech Stack:** Python ≥3.12, Pydantic v2 (`model_validate_json`, field validators on `Address` / `PersonReference`), stdlib `datetime.date` + `decimal.Decimal` + `re` + `logging`, pytest with `pytest.parametrize` and `caplog`.

---

## Plan Metadata (binding, validated by lead against splits.xml)

| Field | Value |
|---|---|
| Plan id | `2026-04-23-parser-migration-json-and-coercion` |
| Plan-group | `2026-04-23-parser-migration` (plans.xml index 15) |
| Suffix | `json-and-coercion` |
| Cycles | `[§6.1..§6.4]` (Cycle 0 precondition; Cycle 1 JSON round-trip; Cycle 2 JSON error surfaces; Cycle 3 coercion helpers) |
| Depends-on | (none — root of the parser-migration dependency chain) |
| Worktree | not-required |
| Blast-radius | `src/trust_generator/v3/parsers/__init__.py;src/trust_generator/v3/parsers/json_parser.py;src/trust_generator/v3/parsers/coercion.py;tests/v3/parsers/__init__.py;tests/v3/parsers/test_json_parser.py;tests/v3/parsers/test_coercion.py` |
| Spec | `docs/superpowers/specs/2026-04-23-parser-migration-design.md` |
| Splits | `docs/superpowers/specs/2026-04-23-parser-migration-splits.xml` |
| Siblings | `docx` (depends-on=`json-and-coercion`); `pdf` (depends-on=`docx`); `registry` (depends-on=`docx,pdf`) |

**Discipline notes:**

- Feature branch only — never `main`. Always create a new commit; never `--amend`. Never bypass hooks (`--no-verify`, `--no-gpg-sign`).
- All ad-hoc Python invocation goes through `pixi run python` / `pixi run test` / `pixi run check` (system Python is 3.14; the pixi env pins 3.12 for rule-engine compat).
- `ruff` runs in preview mode targeting py312. RUF022 auto-alphabetizes `__all__` — declare `__all__` entries in sorted order. RUF032 autofixes integer-valued `Decimal("n")` to `Decimal(n)` — write integer-form Decimal literals directly.
- Per `.claude/rules/development-strategy.md`: one Red commit + one Green commit per coding cycle. A Refactor commit lands only when the `refactor_threshold` is met; each cycle below lists its verdict.
- Mid-cycle scope drift opens a chore-entry via the `spec-pipeline` scope-maintenance protocol. Do not silently expand a cycle.

## File structure

```
src/trust_generator/v3/parsers/
├── __init__.py        # CREATE: re-export parse_json (parse_file / parse_docx / parse_pdf land in sibling `registry`)
├── json_parser.py     # CREATE: parse_json — model_validate_json + ValidationError→ValueError wrap + FileNotFoundError check
└── coercion.py        # CREATE: _to_date, _to_decimal, _to_address, _to_person_reference (four pure helpers)

tests/v3/parsers/
├── __init__.py            # CREATE: empty package marker
├── test_json_parser.py    # CREATE: round-trip + three error-surface tests
└── test_coercion.py       # CREATE: parametrized batches per helper + regression guards (share-percent drops, placeholder-prefix stripping)
```

Files in sibling-owned scopes (NOT created here):

- `src/trust_generator/v3/parsers/docx_parser.py` — created by sibling `docx`
- `src/trust_generator/v3/parsers/pdf_parser.py` — created by sibling `pdf`
- `src/trust_generator/v3/parsers/registry.py` — created by sibling `registry`

## Cross-plan `__init__.py` handoff (explicit overlap call-out)

`src/trust_generator/v3/parsers/__init__.py` appears in BOTH this plan's blast-radius and the sibling `registry`'s blast-radius. This is an intended sequential overlap, not a contention:

1. **This plan (Cycle 1, Green):** creates `__init__.py` with a single re-export — `from .json_parser import parse_json` — and an `__all__ = ["parse_json"]`.
2. **Sibling `registry` (§6.10–§6.11):** extends `__init__.py` to add `parse_file`, `parse_docx`, `parse_pdf` and grows `__all__` accordingly. `registry` lands strictly after `docx` + `pdf`, which both depend on this plan's coercion helpers, so the file's evolution is monotonic (add-only) across the plan-group.

If the lead reviewing this plan flags the overlap: the resolution is that this plan ships a minimal `__init__.py` (one import line, one `__all__` tuple) and `registry` strictly extends it; no editing-around-each-other is required because the plans are serialized in the dependency chain.

## Out of scope (handed to sibling plans)

The following cycles + surfaces belong to siblings in plan-group `2026-04-23-parser-migration`. Cross-reference by exact suffix name.

| Sibling suffix | Spec cycles | Owned scope |
|---|---|---|
| `docx` | §6.5–§6.8 | `docx_parser.py` end-to-end: smoke test (§6.5, parser-existence signal), asset integration against `assets/Trust_Intake_Questionnaire.docx` (§6.6, includes the cycle-4b refactor extracting `_apply_post_promotion_protocol`), combinatorial post-promotion contract tests covering all four (seed_state, parsed_state) trust_type/marital_status pairs (§6.7), and coercion integration wiring the four helpers from THIS plan into the docx flat-dict → TrustData step plus the §5.3 step 6 post-merge resolution passes (§6.8). |
| `pdf` | §6.9 | `pdf_parser.py` via `pypdf.PdfReader.get_fields()` AcroForm iteration. Reuses THIS plan's four coercion helpers verbatim. Reuses the `_apply_post_promotion_protocol` helper extracted by sibling `docx` in its cycle 4b refactor. Implements §5.4.A field-presence normalization (`_normalize_field_values`) so that absent fields, present-but-None fields, and present-but-empty-string fields all reduce to `None` before reaching this plan's coercion helpers. |
| `registry` | §6.10–§6.11 | `registry.py` housing `parse_file` extension dispatch; extension of `__init__.py` `__all__` to include `parse_file` / `parse_docx` / `parse_pdf`; the M2 contract test `test_parse_file_ignores_seed_for_json` from plan-review pass 1 (asserts `parse_file('foo.json', seed_initialized=non_None) == parse_file('foo.json', seed_initialized=None)`). |

**Coercion surfaces NOT owned by this plan's `coercion.py` (despite mentions in spec §5.4):**

The dispatcher prompt names exactly four pure coercion helpers, and §6.4 imports the same four. Other coercion patterns enumerated in §5.4 are NOT free functions in `coercion.py` — they live inside docx/pdf parser bodies because they require parser-format context (e.g., a docx checkbox map, a PDF AcroForm field-name prefix). The mapping:

| §5.4 sub-section | Surface | Home |
|---|---|---|
| §5.4.1 Date coercion (`_to_date`) | Pure helper | **`coercion.py` (THIS plan, Cycle 3)** |
| §5.4.2 Decimal coercion (`_to_decimal`) | Pure helper | **`coercion.py` (THIS plan, Cycle 3)** |
| §5.4.3 Address coercion (`_to_address`) | Pure helper | **`coercion.py` (THIS plan, Cycle 3)** |
| §5.4.4 PersonReference coercion (`_to_person_reference`) | Pure helper | **`coercion.py` (THIS plan, Cycle 3)** |
| §5.4.5 Enum coercion | Parser-internal (`_CHECKBOX_MAP` dict + `Enum(value)` try/except) | sibling `docx` (§6.8) + sibling `pdf` (§6.9) |
| §5.4.6 Reference-or-external coercion (BeneficiaryShare / SpecificBequest) | Parser-internal row-construction | sibling `docx` (§6.8) + sibling `pdf` (§6.9) |
| §5.4.7 WithdrawalStep coercion | Parser-internal row-construction (consumes `_to_decimal` from THIS plan) | sibling `docx` (§6.8) + sibling `pdf` (§6.9) |
| §5.4.8 New v3 models with no v2 source | Parser-internal (mostly empty-list defaults; CustomTerm built from three v2 free-text fields) | sibling `docx` (§6.8) + sibling `pdf` (§6.9) |
| §5.4.9 CorporateTrustee discrimination | Parser-internal heuristic on trustee-row text | sibling `docx` (§6.8) + sibling `pdf` (§6.9) |
| §5.4.10 Disinheritance resolution (post-merge) | Post-merge resolution pass inside `_apply_post_merge_resolution` | sibling `docx` (§6.8); also exercised by sibling `pdf` (§6.9) |
| §5.4.A AcroForm field-presence semantics | `_normalize_field_values` helper in `pdf_parser.py` | sibling `pdf` (§6.9) |
| §5.3 step 4 (trust_type / marital_status joint-mutation protocol) | `_apply_post_promotion_protocol` helper | sibling `docx` (extracted in §6.6 refactor; reused by sibling `pdf` in §6.9) |

The four helpers in `coercion.py` are the symbol-level contract this plan exposes to downstream siblings. If a sibling needs an additional pure helper that didn't surface during their drafting, they open a chore-entry per the scope-maintenance protocol — this plan does NOT speculatively pre-create helpers.

---

## Cycle 0 — Precondition check (non-coding gate; spec §6.1)

**Files:** none touched.

**Threshold verdicts:**
- design_surface_threshold: **n/a — non-coding gate**, no design surface introduced.
- refactor_threshold: **n/a — non-coding gate**, no green-phase code authored.

This cycle has no Red / Green / Refactor stages because it does not change code. It exists to make the starting state explicit (per spec §6.1: "the cycle exists to make the starting state explicit").

- [ ] **Step 1: Run the full test suite at session start**

Run: `pixi run check`

Expected: **green** (lint + mypy + pytest all pass). The `check` task aggregates `lint`, `mypy`, and `test` per `pixi.toml`.

- [ ] **Step 2: On red, halt and surface**

If `pixi run check` returns non-zero, a latent failure predates this session and is OUT of scope for this plan. Stop, capture the failing test/diagnostic in a fresh chore-entry via the `spec-pipeline` scope-maintenance protocol (the chore is classified as `code` if a fix requires non-trivial reasoning or `simple` if it is a docs / lint backfill), and abort this plan-execution session. The lead re-dispatches once the precondition is restored.

- [ ] **Step 3: On green, proceed to Cycle 1**

No commit. The successful exit from Step 1 is the signal to proceed; no artifact is produced.

---

## Cycle 1 — JSON round-trip (spec §6.2)

**Files:**
- Create: `src/trust_generator/v3/parsers/__init__.py`
- Create: `src/trust_generator/v3/parsers/json_parser.py`
- Create: `tests/v3/parsers/__init__.py` (empty marker)
- Create: `tests/v3/parsers/test_json_parser.py`

**Threshold verdicts:**
- design_surface_threshold: contract surface external consumers depend on (`parse_json` is re-exported from `trust_generator.v3.parsers`), satisfies the criterion.
- refactor_threshold: **none met — green output is already minimal.** The body is two lines (`read → model_validate_json`); no structural duplication, no nested conditionals, no orthogonal concerns to extract. Spec §6.2 makes this verdict explicit.

- [ ] **Step 1: Write the failing test (Red)**

Create `tests/v3/parsers/__init__.py` as an empty file (pytest package marker).

Create `tests/v3/parsers/test_json_parser.py`:

```python
"""Tests for trust_generator.v3.parsers.json_parser.

Round-trip + error surfaces. JSON parsing is symmetric with v3 schema validation;
Pydantic's validators do all the coercion, so the parser body is a thin wrapper
that adapts (FileNotFoundError, ValidationError) to the v2-compatible exception
contract (ValueError on schema violation).
"""

from __future__ import annotations

import pytest


def test_json_round_trip(tmp_path):
    """A TrustData dumped to JSON parses back to an equal TrustData."""
    from trust_generator.v3.parsers import parse_json
    from trust_generator.v3.schema import (
        GrantorInfo,
        TrustData,
        TrustIdentity,
        TrustType,
    )

    original = TrustData(
        trust_id=TrustIdentity(
            trust_type=TrustType.JOINT,
            desired_trust_name="Test Family Trust",
        ),
        grantor=GrantorInfo(full_legal_name="Test Grantor"),
    )
    json_file = tmp_path / "intake.json"
    json_file.write_text(original.model_dump_json(), encoding="utf-8")

    restored = parse_json(json_file)
    assert restored == original
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pixi run test test_json_round_trip`

Expected: **FAIL** with `ImportError: cannot import name 'parse_json' from 'trust_generator.v3.parsers'` (or `ModuleNotFoundError: No module named 'trust_generator.v3.parsers'` if the package directory does not exist yet).

- [ ] **Step 3: Commit the failing test (Red commit)**

```bash
git add tests/v3/parsers/__init__.py tests/v3/parsers/test_json_parser.py
git commit -m "test(v3.parsers): red — json round-trip parser does not exist yet"
```

- [ ] **Step 4: Write minimal implementation (Green)**

Create `src/trust_generator/v3/parsers/json_parser.py`:

```python
"""JSON parser for v3 TrustData.

Accepts only full v3 TrustData JSON documents — the canonical `model_dump_json()`
shape. Partial JSON, JSON patches, and hand-edited fragmentary JSON are explicitly
out of scope per spec §4 / §9 Q3. Pydantic's own validators handle every coercion
(dates, Decimals, enums, nested models), so the parser body is a thin wrapper.

Error contract:
- FileNotFoundError if the path does not exist (raised before any read).
- ValueError wrapping a Pydantic ValidationError on schema violation — matches
  v2's `ValueError("JSON validation failed for ...")` convention so existing CLI
  callers receive the same exception class.
- OSError from the underlying file read surfaces uncaught (matches v2).
"""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from trust_generator.v3.schema import TrustData


def parse_json(filepath: Path) -> TrustData:
    """Parse a full v3 TrustData JSON dump; return a fresh validated instance.

    Args:
        filepath: Path to a `.json` file containing the canonical full v3
            TrustData dump (`TrustData.model_dump_json()` shape).

    Returns:
        A `TrustData` instance equal to the dumped original.

    Raises:
        FileNotFoundError: input file does not exist.
        ValueError: the JSON does not validate against the v3 TrustData schema.
            The wrapped Pydantic `ValidationError` is preserved as the cause.
    """
    if not filepath.exists():
        raise FileNotFoundError(f"JSON file not found: {filepath}")
    try:
        return TrustData.model_validate_json(filepath.read_text(encoding="utf-8"))
    except ValidationError as exc:
        raise ValueError(f"JSON validation failed for {filepath}: {exc}") from exc
```

Create `src/trust_generator/v3/parsers/__init__.py`:

```python
"""v3 parser package.

This module currently exposes `parse_json` only. The full public surface
(`parse_file`, `parse_docx`, `parse_pdf`) lands in sibling plan
`2026-04-23-parser-migration-registry` (§6.10–§6.11).
"""

from trust_generator.v3.parsers.json_parser import parse_json

__all__ = ["parse_json"]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pixi run test test_json_round_trip`

Expected: **PASS**.

- [ ] **Step 6: Run the gate suite to confirm no regression**

Run: `pixi run check`

Expected: lint + mypy + full pytest all green. (The new module is type-clean; the new tests pass; no v2 or v3-existing surface is touched.)

- [ ] **Step 7: Commit the green implementation**

```bash
git add src/trust_generator/v3/parsers/__init__.py src/trust_generator/v3/parsers/json_parser.py
git commit -m "feat(v3.parsers): green — parse_json round-trip via model_validate_json"
```

- [ ] **Step 8: Refactor — explicitly skipped**

Per the `refactor_threshold` verdict above: **no refactor stage; green output is already minimal** (two-line body, no structural duplication, no orthogonal concerns). Spec §6.2 confirms this disposition.

---

## Cycle 2 — JSON parser error surfaces (spec §6.3)

**Files:**
- Modify: `tests/v3/parsers/test_json_parser.py` (append three new test functions)

**Threshold verdicts:**
- design_surface_threshold: contract surface external consumers depend on (the documented exception contract). Satisfies the criterion.
- refactor_threshold: **moot — no green-phase code authored in this cycle.** The Cycle 1 implementation already raises `FileNotFoundError` and wraps `ValidationError` as `ValueError`, so the three error-surface tests pass on first run. Per spec §6.3: "The error-surface tests pass with the cycle-1 implementation already; the test additions are characterization-and-regression-guard, not change-driving."

**Important framing:** the tests added in this cycle are **characterization / regression-guard** — they pin the cycle-1 surface against future drift, but they do not drive a behavior change. The single commit in this cycle is a test-only commit. There is no `src/` change.

- [ ] **Step 1: Append the three error-surface tests**

Append to `tests/v3/parsers/test_json_parser.py`:

```python
def test_json_parser_raises_for_missing_file(tmp_path):
    """parse_json raises FileNotFoundError for a non-existent path."""
    from trust_generator.v3.parsers import parse_json

    missing = tmp_path / "does_not_exist.json"
    with pytest.raises(FileNotFoundError):
        parse_json(missing)


def test_json_parser_raises_for_invalid_json(tmp_path):
    """parse_json raises ValueError for malformed JSON syntax.

    Pydantic's model_validate_json wraps a JSON decode error in a
    ValidationError, which parse_json re-wraps as ValueError. The
    point of this test is the outer exception class, not the cause chain.
    """
    from trust_generator.v3.parsers import parse_json

    broken = tmp_path / "broken.json"
    broken.write_text("{this is not valid json", encoding="utf-8")
    with pytest.raises(ValueError):
        parse_json(broken)


def test_json_parser_raises_for_schema_violation(tmp_path):
    """parse_json raises ValueError for JSON that parses but fails v3 schema validation.

    v3's typed schema (date / Decimal / enums) admits many schema-violation paths
    that v2's mostly-string schema did not — this test exercises one (a date field
    populated with a malformed string) and asserts the outer exception class is
    ValueError, matching the v2 CLI contract.
    """
    from trust_generator.v3.parsers import parse_json

    # Valid JSON structure; invalid value (date field receives non-date string).
    bad_schema = tmp_path / "bad_schema.json"
    bad_schema.write_text(
        '{"trust_id": {"trust_type": "JOINT", "trust_date": "not-a-date"}, '
        '"grantor": {"full_legal_name": "Test Grantor"}}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError) as excinfo:
        parse_json(bad_schema)

    # The wrapped Pydantic error message survives in the str() of the ValueError.
    # This pins the message-shape promise (callers do not parse the message, but
    # the user-facing CLI surfaces it in error logs).
    assert "JSON validation failed for" in str(excinfo.value)
```

- [ ] **Step 2: Run the three new tests to confirm they pass on first run**

Run: `pixi run test test_json_parser_raises_for`

Expected: **PASS** (all three). This is the spec-prescribed disposition (§6.3): the cycle-1 implementation already satisfies the contract.

If any of the three returns **FAIL** on first run: the cycle-1 implementation diverged from the spec contract. Halt, restore the cycle-1 implementation to match spec §6.2, and re-run.

- [ ] **Step 3: Run the gate suite**

Run: `pixi run check`

Expected: lint + mypy + full pytest all green.

- [ ] **Step 4: Commit the characterization tests**

```bash
git add tests/v3/parsers/test_json_parser.py
git commit -m "test(v3.parsers): pin parse_json error surface (FileNotFoundError / ValueError on bad json / ValueError on schema violation)"
```

The commit message deliberately omits a "feat:" or "red→green" cadence — the commit is a single characterization-test addition, not a TDD cycle. The verbose message documents the intent so a future archeologist sees why this commit has no `src/` paired delta.

- [ ] **Step 5: Refactor — n/a**

No code authored this cycle; the refactor_threshold is moot. No refactor commit.

---

## Cycle 3 — Coercion helpers, pure (spec §6.4)

**Files:**
- Create: `src/trust_generator/v3/parsers/coercion.py`
- Create: `tests/v3/parsers/test_coercion.py`

**Threshold verdicts:**
- design_surface_threshold: four functions with branching logic (date format chain, decimal strip chain, address comma-split chain, person-reference trap-and-reconstruct), all consumed across two sibling plans (`docx` + `pdf`). Satisfies the criterion squarely.
- refactor_threshold: **met — the green-phase `_to_date` body has structural duplication** (three literal long-form strptime patterns). The refactor stage extracts a module-level `_DATE_FORMATS` tuple and iterates over it. Spec §6.4 specifies this exact refactor.

**Scope reminder:** `coercion.py` holds **exactly four** pure helpers per the dispatcher prompt and §6.4's test imports: `_to_date`, `_to_decimal`, `_to_address`, `_to_person_reference`. The §5.4.5–§5.4.10 patterns are parser-internal and belong to the docx/pdf siblings; do NOT pre-create helpers for them here (see "Out of scope" above for the full mapping).

### Cycle 3 — Red phase

- [ ] **Step 1: Write the failing parametrized tests**

Create `tests/v3/parsers/test_coercion.py`:

```python
"""Tests for trust_generator.v3.parsers.coercion.

Four pure helpers, each tested via pytest.parametrize batches covering positive
formats from the v2 corpus plus negative (unparseable) inputs that exercise the
soft-fail surface (return-default + log.warning). Regression guards pin:
  - §5.4.2 share-percent vs. asset-value semantics (NOT enforced in _to_decimal
    itself — the row-drop is a parser-level decision; this batch documents the
    contract by asserting _to_decimal alone always returns Decimal, never None).
  - §5.4.4 placeholder-prefix stripping for PersonReference cells.
  - §5.4.4 one-token-name entity-reference reconstruction.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

import pytest

from trust_generator.v3.parsers.coercion import (
    _to_address,
    _to_date,
    _to_decimal,
    _to_person_reference,
)
from trust_generator.v3.schema import Address, PersonReference


# ---------------------------------------------------------------------------
# _to_date — §5.4.1
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("01/15/2000", date(2000, 1, 15)),
        ("1/15/2000", date(2000, 1, 15)),
        ("2000-01-15", date(2000, 1, 15)),
        ("September 17, 1980", date(1980, 9, 17)),
        ("Sep 17, 1980", date(1980, 9, 17)),
        ("not a date", None),
        ("", None),
        ("   ", None),
    ],
    ids=[
        "mm_dd_yyyy_zero_padded",
        "m_d_yyyy_unpadded",
        "iso_yyyy_mm_dd",
        "long_form_full_month",
        "long_form_abbreviated_month",
        "unparseable_returns_none",
        "empty_returns_none",
        "whitespace_returns_none",
    ],
)
def test_to_date_positive_and_negative(text, expected):
    assert _to_date(text) == expected


def test_to_date_unparseable_emits_warning(caplog):
    """Soft-fail surface: unparseable date emits log.warning (spec §5.5)."""
    with caplog.at_level(logging.WARNING, logger="trust_generator.v3.parsers.coercion"):
        result = _to_date("not a date")
    assert result is None
    assert any("could not parse date" in rec.message for rec in caplog.records)


# ---------------------------------------------------------------------------
# _to_decimal — §5.4.2
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("$500,000", Decimal(500000)),
        ("500,000", Decimal(500000)),
        ("$500000.50", Decimal("500000.50")),
        ("500000", Decimal(500000)),
        ("50%", Decimal(50)),
        ("50.5%", Decimal("50.5")),
        ("  $1,234.56  ", Decimal("1234.56")),
        ("a lot", Decimal(0)),
        ("", Decimal(0)),
    ],
    ids=[
        "dollar_thousands_separator",
        "thousands_separator_no_dollar",
        "dollar_with_cents",
        "bare_integer",
        "percent_integer",
        "percent_fractional",
        "whitespace_stripped",
        "unparseable_returns_zero",
        "empty_returns_zero",
    ],
)
def test_to_decimal_positive_and_negative(text, expected):
    assert _to_decimal(text) == expected


def test_to_decimal_always_returns_decimal_never_none():
    """Regression guard for §5.4.2 contract: helper alone always returns Decimal.

    The parser-level row-drop on share-percent failure (per §5.4.2) is the docx/pdf
    sibling's responsibility — NOT this helper's. This helper's soft-fail return is
    Decimal(0) for all unparseable inputs; the calling parser decides whether
    Decimal(0) means 'missing' or 'meaningfully zero' based on the target field.
    """
    for unparseable in ("a lot", "", "   ", "not a number"):
        assert isinstance(_to_decimal(unparseable), Decimal)
        assert _to_decimal(unparseable) == Decimal(0)


def test_to_decimal_unparseable_emits_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="trust_generator.v3.parsers.coercion"):
        _to_decimal("a lot")
    assert any("could not parse decimal" in rec.message for rec in caplog.records)


# ---------------------------------------------------------------------------
# _to_address — §5.4.3
# ---------------------------------------------------------------------------

def test_to_address_three_parts():
    """Free text with three comma-separated parts: street, city, state+zip."""
    result = _to_address("123 Main St, Springfield, IL 62701")
    assert isinstance(result, Address)
    assert result.street == "123 Main St"
    assert result.city == "Springfield"
    assert result.state == "IL"
    assert result.zip_code == "62701"


def test_to_address_four_parts_with_country():
    """Free text with four parts: street, city, state+zip, country."""
    result = _to_address("123 Main St, Springfield, IL 62701, US")
    assert result.street == "123 Main St"
    assert result.city == "Springfield"
    assert result.state == "IL"
    assert result.zip_code == "62701"
    assert result.country == "US"


def test_to_address_unparseable_single_string():
    """Zero / one comma: full string lands in street, other fields empty."""
    result = _to_address("just a single string with no commas")
    assert result.street == "just a single string with no commas"
    assert result.city == ""
    assert result.state == ""
    assert result.zip_code == ""


def test_to_address_unparseable_emits_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="trust_generator.v3.parsers.coercion"):
        _to_address("just a single string")
    assert any("could not parse address" in rec.message for rec in caplog.records)


def test_to_address_empty_string():
    """Empty input yields a fully-defaulted Address (no warning)."""
    result = _to_address("")
    assert result.street == ""
    assert result.city == ""
    assert result.state == ""
    assert result.zip_code == ""


def test_to_address_never_geocodes():
    """latitude / longitude are NEVER populated by the coercion helper (spec §5.4.3)."""
    result = _to_address("123 Main St, Springfield, IL 62701")
    assert result.latitude is None
    assert result.longitude is None


# ---------------------------------------------------------------------------
# _to_person_reference — §5.4.4
# ---------------------------------------------------------------------------

def test_to_person_reference_two_token_name():
    """Standard two-token name → PersonReference with full_legal_name set."""
    result = _to_person_reference("John Andrew Doe")
    assert isinstance(result, PersonReference)
    assert result.full_legal_name == "John Andrew Doe"
    assert result.is_entity is False


def test_to_person_reference_one_token_name_traps_and_reconstructs_as_entity():
    """One-token name fails the two-token validator → re-constructed as entity (§5.4.4).

    Note: the §5.4.4 trap fires on inputs that fail the `len(v.split()) < 2`
    validator — i.e., true one-token strings. Multi-token entity names like
    `"ABC Corporation"` or `"First National Bank"` are detected separately by
    the §5.4.9 CorporateTrustee suffix heuristic, which lives inside
    `_apply_post_merge_resolution` (docx-6, not this helper).
    """
    result = _to_person_reference("AcmeCorp")
    assert result.is_entity is True
    assert result.entity_name == "AcmeCorp"
    assert result.full_legal_name == ""


def test_to_person_reference_strips_placeholder_prefix():
    """v2 corpus pattern: '[Spouse name] Jane Doe' → coerces to 'Jane Doe' (§5.4.4)."""
    result = _to_person_reference("[Spouse's full legal name] Jane Doe")
    assert result.full_legal_name == "Jane Doe"
    assert result.is_entity is False


def test_to_person_reference_placeholder_prefix_with_one_token_remaining_becomes_entity():
    """Placeholder strip leaves one token → entity re-construction fires."""
    result = _to_person_reference("[Entity name] AcmeCorp")
    assert result.is_entity is True
    assert result.entity_name == "AcmeCorp"


def test_to_person_reference_empty_string():
    """Empty input yields an entity-shaped reference with empty entity_name."""
    result = _to_person_reference("")
    # Either interpretation is acceptable per the spec; pin observed behavior:
    # an empty string is one "token" (or zero), so the entity branch fires.
    assert result.full_legal_name == ""
    # entity_name may be "" (empty) — this is the natural outcome of the trap path.
    assert result.is_entity is True
```

- [ ] **Step 2: Run the test file to verify it fails**

Run: `pixi run test test_coercion`

Expected: **FAIL** with `ModuleNotFoundError: No module named 'trust_generator.v3.parsers.coercion'` (the import line at the top of the test file is the first failure point).

- [ ] **Step 3: Commit the Red phase**

```bash
git add tests/v3/parsers/test_coercion.py
git commit -m "test(v3.parsers): red — coercion helpers (_to_date / _to_decimal / _to_address / _to_person_reference) do not exist yet"
```

### Cycle 3 — Green phase

- [ ] **Step 4: Write the minimal implementation**

Create `src/trust_generator/v3/parsers/coercion.py`:

```python
"""Pure coercion helpers consumed by the docx and pdf parsers.

Each helper takes a string from a docx cell or a normalized PDF AcroForm field
(see pdf_parser._normalize_field_values in sibling plan `pdf`) and returns the
v3-typed equivalent. Failures soft-fail (log.warning + return a schema-default-
shaped value), never raise — the parser-layer error policy (spec §5.5) reserves
hard fails for FileNotFoundError, OSError from the underlying library, and
parse_json's schema-validation wrap.

JSON parsing does NOT use this module: Pydantic's own validators handle every
coercion path on model_validate_json.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from pydantic import ValidationError

from trust_generator.v3.schema import Address, PersonReference

log = logging.getLogger(__name__)

# Placeholder-prefix pattern for §5.4.4: strips a leading bracketed hint
# (e.g., '[Spouse name] ') from the start of a person-reference cell.
_PLACEHOLDER_PREFIX_RE = re.compile(r"^\[[^\]]+\]\s*")


def _to_date(text: str) -> date | None:
    """Coerce a docx cell / PDF field to a date (§5.4.1).

    Try formats in order: ISO (`YYYY-MM-DD`), `M/D/YYYY` (zero-padded or not),
    long-form (`%B %d, %Y` / `%b %d, %Y`). On all-fail: return None + warn.
    """
    if not text or not text.strip():
        return None
    stripped = text.strip()

    # ISO first.
    try:
        return date.fromisoformat(stripped)
    except ValueError:
        pass

    # MM/DD/YYYY and M/D/YYYY.
    try:
        return datetime.strptime(stripped, "%m/%d/%Y").date()
    except ValueError:
        pass

    # Long-form patterns: full month name, then abbreviated.
    try:
        return datetime.strptime(stripped, "%B %d, %Y").date()
    except ValueError:
        pass
    try:
        return datetime.strptime(stripped, "%b %d, %Y").date()
    except ValueError:
        pass

    log.warning("could not parse date %r", text)
    return None


def _to_decimal(text: str) -> Decimal:
    """Coerce a docx cell / PDF field to a Decimal (§5.4.2).

    Strips leading '$', thousands ',', trailing '%', surrounding whitespace.
    On parse failure: return Decimal(0) + warn. The Decimal(0) default matches
    the schema-side default for asset-value / equity / benefit fields. The
    parser-level row-drop rule for share-percent fields is the docx/pdf
    sibling's responsibility — this helper alone always returns Decimal.
    """
    if not text or not text.strip():
        return Decimal(0)
    stripped = text.strip().lstrip("$").rstrip("%").replace(",", "").strip()
    try:
        return Decimal(stripped)
    except InvalidOperation:
        log.warning("could not parse decimal %r", text)
        return Decimal(0)


def _to_address(text: str) -> Address:
    """Coerce a docx cell free-text address to an Address (§5.4.3).

    Heuristic comma-split:
      3 parts -> (street, city, "state zip")
      4 parts -> (street, city, "state zip", country)
    Each "state zip" element is split on the last whitespace.
    On unparseable input (zero or one comma): street = full text, other fields
    empty + warn. latitude / longitude are NEVER set here (spec §5.4.3); the
    geocoder is invoked separately by the GUI / generators.
    """
    if not text:
        return Address()
    parts = [p.strip() for p in text.split(",")]
    if len(parts) < 3:
        log.warning("could not parse address %r", text)
        return Address(street=text.strip())

    street = parts[0]
    city = parts[1]
    state_zip = parts[2]
    country = parts[3] if len(parts) >= 4 else ""

    # Split "state zip" on the last whitespace.
    state_zip_tokens = state_zip.rsplit(None, 1)
    if len(state_zip_tokens) == 2:
        state, zip_code = state_zip_tokens
    else:
        state, zip_code = state_zip, ""

    return Address(
        street=street,
        city=city,
        state=state,
        zip_code=zip_code,
        country=country,
    )


def _to_person_reference(text: str) -> PersonReference:
    """Coerce a docx cell name to a PersonReference (§5.4.4).

    Steps:
      1. Strip a leading bracketed placeholder hint (e.g., '[Spouse name]').
      2. Try PersonReference(full_legal_name=name). On the schema's
         two-token-name validator failure (one-token / entity-like name),
         re-construct as PersonReference(is_entity=True, entity_name=name,
         full_legal_name="").
    """
    if text is None:
        text = ""
    stripped = _PLACEHOLDER_PREFIX_RE.sub("", text).strip()

    try:
        return PersonReference(full_legal_name=stripped)
    except ValidationError:
        return PersonReference(
            is_entity=True,
            entity_name=stripped,
            full_legal_name="",
        )
```

- [ ] **Step 5: Run the test file to verify it passes**

Run: `pixi run test test_coercion`

Expected: **PASS** (all parametrized cases + all standalone tests).

If a test fails: the most-likely cause is a `PersonReference` validator shape mismatch — open `src/trust_generator/v3/schema.py`, find the `PersonReference` model + its two-token validator, and confirm the trap-and-reconstruct path matches. Do NOT modify the schema in this plan (schema modifications are out-of-scope per spec §2); open a chore-entry if a schema-side gap surfaces.

- [ ] **Step 6: Run the gate suite**

Run: `pixi run check`

Expected: lint + mypy + full pytest all green.

- [ ] **Step 7: Commit the green implementation**

```bash
git add src/trust_generator/v3/parsers/coercion.py
git commit -m "feat(v3.parsers): green — pure coercion helpers (_to_date / _to_decimal / _to_address / _to_person_reference)"
```

### Cycle 3 — Refactor phase (spec-prescribed, §6.4)

The green-phase `_to_date` body contains three literal `datetime.strptime(stripped, "<fmt>")` calls in sequence — structural duplication that satisfies `refactor_threshold`. Spec §6.4 prescribes extracting a module-level `_DATE_FORMATS` tuple.

- [ ] **Step 8: Refactor `_to_date` to iterate over a `_DATE_FORMATS` tuple**

Edit `src/trust_generator/v3/parsers/coercion.py`. Replace the body of `_to_date` and add the module-level constant:

```python
# Long-form date formats tried after ISO and MM/DD/YYYY. Order matters:
# longer / more-specific patterns first to prevent strptime accepting a
# shorter pattern on a longer string.
_DATE_FORMATS: tuple[str, ...] = (
    "%m/%d/%Y",
    "%B %d, %Y",
    "%b %d, %Y",
)


def _to_date(text: str) -> date | None:
    """Coerce a docx cell / PDF field to a date (§5.4.1).

    Try ISO first (`date.fromisoformat`), then each `_DATE_FORMATS` pattern in
    order via `datetime.strptime`. On all-fail: return None + warn.
    """
    if not text or not text.strip():
        return None
    stripped = text.strip()

    try:
        return date.fromisoformat(stripped)
    except ValueError:
        pass

    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(stripped, fmt).date()
        except ValueError:
            continue

    log.warning("could not parse date %r", text)
    return None
```

- [ ] **Step 9: Re-run the gate suite — tests must stay green**

Run: `pixi run check`

Expected: all tests still pass. The refactor is behavior-preserving — every input that hit a specific strptime branch in the green phase now hits the same branch via the loop.

- [ ] **Step 10: Commit the refactor**

```bash
git add src/trust_generator/v3/parsers/coercion.py
git commit -m "refactor(v3.parsers): collapse _to_date format chain into _DATE_FORMATS tuple iteration"
```

---

## Session exit criteria

Per the spec's "Cycle ordering rationale" (§6) and this plan's scope, the session is complete when:

1. `pixi run check` returns green (lint + mypy + full pytest).
2. `from trust_generator.v3.parsers import parse_json` succeeds; `parse_json(<full v3 JSON dump>)` round-trips.
3. `from trust_generator.v3.parsers.coercion import _to_date, _to_decimal, _to_address, _to_person_reference` succeeds; the parametrized test batches in `tests/v3/parsers/test_coercion.py` all pass.
4. The plans.xml `plan-md` attribute for child `2026-04-23-parser-migration-json-and-coercion` is non-empty (set by the lead at plan-group commit time).

The session does NOT close the plan-group. Sibling `docx` (depends-on=`json-and-coercion`) is the next node in the dependency chain and will be sequenced by `spec-pipeline:sequence-multi-plan`.

## Hand-off contract to siblings

When `docx` and `pdf` begin drafting / executing, they import from this plan's deliverables as follows:

```python
# In docx_parser.py (sibling `docx`) and pdf_parser.py (sibling `pdf`):
from trust_generator.v3.parsers.coercion import (
    _to_address,
    _to_date,
    _to_decimal,
    _to_person_reference,
)
```

If a sibling discovers a coercion need not covered by these four helpers (e.g., a free-text phone-number-to-structured-shape coercion), the sibling does NOT extend `coercion.py` directly — that would breach the plan-group's serial dependency chain. The sibling opens a chore-entry per the scope-maintenance protocol; the chore either lands as a follow-up commit on this plan's branch or as a separate plan-entry in `plans.xml`. The lead arbitrates.
