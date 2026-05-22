# TGv3 Parser Migration — PDF Parser Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `src/trust_generator/v3/parsers/pdf_parser.py` — the v3 PDF parser that iterates AcroForm fields via `pypdf`, applies `§5.4.A` field-presence normalization, reuses the shared coercion helpers and the `_apply_post_promotion_protocol` helper extracted by the `docx` plan, and satisfies invariants P1–P3 of the post-promotion merge protocol.

**Architecture:** Single TDD cycle (§6.9). The parser is structurally simpler than docx — AcroForm field iteration yields a flat dict directly (no table walking). Novelty is confined to `_normalize_field_values` (AcroForm-specific) and the v3 schema name adaptation. All coercion and protocol work is delegated to pre-built helpers from sibling plans. Tests are Tier 2 (synthetic, `tmp_path`-constructed PDF fixtures via `reportlab`) plus three explicit §5.4.A field-presence pin tests.

**Tech Stack:** Python 3.12, `pypdf` (AcroForm read), `reportlab` (PDF fixture generation in tests), Pydantic v2, pytest, pixi.

**Spec:** `docs/superpowers/specs/2026-04-23-parser-migration-design.md` — focus on §5.2 (public API), §5.3 (post-promotion merge protocol), §5.4 (coercion patterns), §5.4.A (AcroForm field-presence semantics), §6.9 (Cycle 7 implementation).

**Scope lock:** §6.9 only — `pdf_parser.py` and its tests. `__init__.py` re-exports, `registry.py`, and `parse_file` dispatch are `registry`'s blast-radius and are explicitly out of scope here. Imports from `docx_parser.py` and `coercion.py` are read-only consumption; this plan does not modify either file.

**Blast-radius:**

```
src/trust_generator/v3/parsers/pdf_parser.py
tests/v3/parsers/test_pdf_parser.py
```

---

## File map

**Created:**

- `src/trust_generator/v3/parsers/pdf_parser.py` — `parse_pdf(filepath, seed_initialized)` + `_normalize_field_values(fields_dict)` helper.
- `tests/v3/parsers/test_pdf_parser.py` — Tier 2 synthetic fixture tests + §5.4.A field-presence pin tests.

**Modified:** none.

**Out of scope (handed to sibling plans):**

- `json-and-coercion` owns §6.1–§6.4: JSON parser (`json_parser.py`), the `parsers/__init__.py` package stub, and `coercion.py` with `_to_date`, `_to_decimal`, `_to_address`, `_to_person_reference`. This plan consumes those helpers by import; it does not author or modify them.
- `docx` owns §6.5–§6.8: docx parser (`docx_parser.py`), `_docx_fixtures.py`, and `test_assets_integration.py`. Two module-level helpers are imported by `pdf_parser.py` but remain authored and owned by `docx`: `_apply_post_promotion_protocol(result, parsed_trust_type, parsed_marital_status)` (extracted in `docx` §6.6 cycle 4b refactor) and `_apply_post_merge_resolution(result, exclusions_string)` (from `docx` §6.8 — 2-arg signature confirmed; CorporateTrustee discrimination runs inside the helper via re-application of `_is_entity_name(name)` per trustee entry, not via a caller-side flags argument). This plan does not modify `docx_parser.py`.
- `registry` owns §6.10–§6.11: `registry.py` (`parse_file` extension dispatch) and the `parsers/__init__.py` public re-exports (`parse_pdf`, `parse_docx`, `parse_json`, `parse_file`). The `__init__.py` file is not touched by this plan. Executor must import directly via `from trust_generator.v3.parsers.pdf_parser import parse_pdf` in tests — the re-export does not exist until `registry` executes.

---

## Commit plan

| # | Commit message | Produces |
|---|---|---|
| 1 | `test(v3/parsers): red — pdf parser smoke + field-presence normalization tests (§6.9)` | Task 1 |
| 2 | `feat(v3/parsers): green — pdf_parser AcroForm iteration + _normalize_field_values (§6.9)` | Task 2 |

No refactor commit — see §6.9 note in Task 2.

### Gate convention (applies to every task)

Every commit is gated by `pixi run check` (composite lint + mypy + test). Lint and type-check failures are treated like test failures: stop, fix, re-run before committing. The scoped `pixi run test <match>` steps in each task are for fast TDD-cycle feedback; they do not substitute for the gate.

`<match>` is a pytest `-k` substring pattern. The pixi `test` task applies `--ignore-glob **/$TASK_EXCLUDE`, so v2 code is excluded automatically.

---

## Task 0: Precondition check

Not a commit. Validates the suite is green before any changes.

- [ ] **Step 1: Run the full project gate.**
  ```bash
  pixi run check
  ```
  Expected: **green**. If red, a latent failure predates this plan. Stop and resolve before continuing.

---

## Task 1: Red — pdf parser tests

**Commit:** `test(v3/parsers): red — pdf parser smoke + field-presence normalization tests (§6.9)`

Create `tests/v3/parsers/test_pdf_parser.py`. All tests must fail at this stage because `pdf_parser.py` does not yet exist. The expected failure mode is `ModuleNotFoundError` or `ImportError` — no parser absent → no `parse_pdf`. The field-presence tests may also fail with `AttributeError` if `_normalize_field_values` does not exist; either is an unambiguous red signal.

### Step 1: Verify the test directory exists

- [ ] Confirm `tests/v3/parsers/` exists (created by `json-and-coercion`). If absent, this plan has a dependency gap — stop and notify the lead.

### Step 2: Create the test file

- [ ] Create `tests/v3/parsers/test_pdf_parser.py` with the following content:

```python
"""Tests for the v3 PDF parser (§6.9).

Tier 2 (synthetic): constructs PDF fixtures via reportlab in tmp_path.
All tests are gated on pypdf + reportlab availability.
Import path: from trust_generator.v3.parsers.pdf_parser import parse_pdf
(parse_pdf is not re-exported from __init__ until the 'registry' plan executes).
"""
from __future__ import annotations

import pytest

pypdf = pytest.importorskip("pypdf")
reportlab = pytest.importorskip("reportlab")

from io import BytesIO  # noqa: E402
from pathlib import Path  # noqa: E402

from reportlab.pdfgen import canvas  # noqa: E402
from pypdf import PdfReader, PdfWriter  # noqa: E402

from trust_generator.v3.schema import (  # noqa: E402
    MaritalStatus,
    QuestionnaireSeed,
    TrustType,
    promote_seed,
)


# ---------------------------------------------------------------------------
# §5.4.A field-presence normalization — three required pin tests + whitespace
# ---------------------------------------------------------------------------

class TestFieldPresenceNormalization:
    """§5.4.A: absent / present-None / present-empty all normalize to None."""

    def test_pdf_field_absent_is_None_at_coercion(self, tmp_path):
        """A field not present in get_fields() dict is treated as None."""
        from trust_generator.v3.parsers.pdf_parser import _normalize_field_values

        # Simulate get_fields() returning a dict without the key.
        fields: dict = {}  # 'grantor.full_legal_name' absent
        normalized = _normalize_field_values(fields)
        assert "grantor.full_legal_name" not in normalized

    def test_pdf_field_present_None_is_None_at_coercion(self, tmp_path):
        """A field present in get_fields() with value None normalizes to None."""
        from trust_generator.v3.parsers.pdf_parser import _normalize_field_values

        # Simulate a Field object whose .value is None.
        class _MockField:
            value = None

        fields = {"grantor.full_legal_name": _MockField()}
        normalized = _normalize_field_values(fields)
        assert normalized.get("grantor.full_legal_name") is None

    def test_pdf_field_present_empty_is_None_at_coercion(self, tmp_path):
        """A field present in get_fields() with value '' normalizes to None."""
        from trust_generator.v3.parsers.pdf_parser import _normalize_field_values

        class _MockField:
            value = ""

        fields = {"grantor.full_legal_name": _MockField()}
        normalized = _normalize_field_values(fields)
        assert normalized.get("grantor.full_legal_name") is None

    def test_pdf_field_whitespace_only_is_None_at_coercion(self, tmp_path):
        """A field with a whitespace-only string normalizes to None after .strip()."""
        from trust_generator.v3.parsers.pdf_parser import _normalize_field_values

        class _MockField:
            value = "   "

        fields = {"grantor.full_legal_name": _MockField()}
        normalized = _normalize_field_values(fields)
        assert normalized.get("grantor.full_legal_name") is None


# ---------------------------------------------------------------------------
# Smoke test — parser exists, opens a minimal PDF, returns TrustData
# ---------------------------------------------------------------------------

class TestParsePdfSmoke:
    """Cycle 7 parallel to cycle 4a (docx smoke). Parser-existence signal only."""

    def test_parse_pdf_smoke(self, tmp_path):
        """parse_pdf exists, opens a blank-field PDF, returns a TrustData.

        Also asserts P3 invariant: seed_initialized is field-level equal
        before and after the call.
        """
        from trust_generator.v3.parsers.pdf_parser import parse_pdf

        seed = QuestionnaireSeed(
            trust_type=TrustType.JOINT,
            marital_status=MaritalStatus.MARRIED,
        )
        seed_initialized = promote_seed(seed)
        seed_snapshot = seed_initialized.model_copy(deep=True)

        # Build a minimal PDF with no meaningful content.
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        pdf_path = tmp_path / "blank.pdf"
        with open(pdf_path, "wb") as f:
            writer.write(f)

        result = parse_pdf(pdf_path, seed_initialized)

        assert result is not None
        # P3: seed_initialized must be field-level equal before and after.
        assert seed_initialized == seed_snapshot
        # Deepcopy proof: returned instance is distinct.
        assert result is not seed_initialized

    def test_parse_pdf_preserves_seed_trust_type(self, tmp_path):
        """When no trust_type field is present in the PDF, seed trust_type persists."""
        from trust_generator.v3.parsers.pdf_parser import parse_pdf

        seed = QuestionnaireSeed(
            trust_type=TrustType.INDIVIDUAL,
            marital_status=MaritalStatus.UNMARRIED,
        )
        seed_initialized = promote_seed(seed)

        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        pdf_path = tmp_path / "no_trust_type.pdf"
        with open(pdf_path, "wb") as f:
            writer.write(f)

        result = parse_pdf(pdf_path, seed_initialized)
        assert result.trust_id.trust_type == TrustType.INDIVIDUAL


# ---------------------------------------------------------------------------
# Error surfaces
# ---------------------------------------------------------------------------

class TestParsePdfErrors:
    """Hard-fail surface per §5.5."""

    def test_parse_pdf_raises_for_missing_file(self, tmp_path):
        """FileNotFoundError raised when the path does not exist."""
        from trust_generator.v3.parsers.pdf_parser import parse_pdf

        seed_initialized = promote_seed(
            QuestionnaireSeed(trust_type=TrustType.JOINT, marital_status=MaritalStatus.MARRIED)
        )
        with pytest.raises(FileNotFoundError):
            parse_pdf(tmp_path / "nonexistent.pdf", seed_initialized)


# ---------------------------------------------------------------------------
# Fill-and-reparse pattern (parallel to v2 tests/v2/test_pdf_parser.py)
# ---------------------------------------------------------------------------

class TestParsePdfFillAndReparse:
    """AcroForm round-trip: fill fields → write PDF → parse → assert TrustData."""

    def _write_acroform_pdf(self, tmp_path: Path, fields: dict[str, str]) -> Path:
        """Build a PDF with AcroForm fields set to the given values."""
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        # update_page_form_field_values requires existing fields; use the
        # low-level add_annotation approach for synthetic fixture PDFs.
        # For simplicity, write raw field data using PdfWriter.clone_reader_document_root
        # is not needed — we set fields directly.
        if fields:
            writer.update_page_form_field_values(writer.pages[0], fields)
        out = tmp_path / "filled.pdf"
        with open(out, "wb") as f:
            writer.write(f)
        return out

    def test_grantor_name_round_trips(self, tmp_path):
        """'grantor.full_legal_name' field value is reflected in result.grantor."""
        from trust_generator.v3.parsers.pdf_parser import parse_pdf

        pdf_path = self._write_acroform_pdf(
            tmp_path, {"grantor.full_legal_name": "Alice Marie Doe"}
        )
        seed = QuestionnaireSeed(trust_type=TrustType.JOINT, marital_status=MaritalStatus.MARRIED)
        result = parse_pdf(pdf_path, promote_seed(seed))
        assert result.grantor.full_legal_name == "Alice Marie Doe"

    def test_trust_type_mutation_via_field(self, tmp_path):
        """A 'trust_id.trust_type' field value overrides the seed trust_type."""
        from trust_generator.v3.parsers.pdf_parser import parse_pdf

        pdf_path = self._write_acroform_pdf(
            tmp_path, {"trust_id.trust_type": "individual"}
        )
        seed = QuestionnaireSeed(trust_type=TrustType.JOINT, marital_status=MaritalStatus.MARRIED)
        result = parse_pdf(pdf_path, promote_seed(seed))
        # trust_type change → _apply_post_promotion_protocol fires
        assert result.trust_id.trust_type == TrustType.INDIVIDUAL

    def test_date_field_coercion(self, tmp_path):
        """A date field in MM/DD/YYYY format is coerced correctly."""
        from datetime import date
        from trust_generator.v3.parsers.pdf_parser import parse_pdf

        pdf_path = self._write_acroform_pdf(
            tmp_path, {"grantor.date_of_birth": "03/15/1975"}
        )
        seed = QuestionnaireSeed(trust_type=TrustType.INDIVIDUAL, marital_status=MaritalStatus.UNMARRIED)
        result = parse_pdf(pdf_path, promote_seed(seed))
        assert result.grantor.date_of_birth == date(1975, 3, 15)

    def test_malformed_date_falls_back_to_None(self, tmp_path, caplog):
        """A date field with unparseable text falls back to None; warning logged."""
        import logging
        from trust_generator.v3.parsers.pdf_parser import parse_pdf

        pdf_path = self._write_acroform_pdf(
            tmp_path, {"grantor.date_of_birth": "sometime in 1975"}
        )
        seed = QuestionnaireSeed(trust_type=TrustType.INDIVIDUAL, marital_status=MaritalStatus.UNMARRIED)
        with caplog.at_level(logging.WARNING, logger="trust_generator.v3.parsers.pdf_parser"):
            result = parse_pdf(pdf_path, promote_seed(seed))
        assert result.grantor.date_of_birth is None
        assert any("could not parse date" in r.message for r in caplog.records)

    def test_post_promotion_protocol_not_reinvoked(self, tmp_path):
        """parse_pdf does not call promote_seed under any branch (P1)."""
        from unittest.mock import patch
        from trust_generator.v3.parsers.pdf_parser import parse_pdf

        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        pdf_path = tmp_path / "blank.pdf"
        with open(pdf_path, "wb") as f:
            writer.write(f)

        seed_initialized = promote_seed(
            QuestionnaireSeed(trust_type=TrustType.JOINT, marital_status=MaritalStatus.MARRIED)
        )
        with patch("trust_generator.v3.parsers.pdf_parser.promote_seed", autospec=True) as m:
            parse_pdf(pdf_path, seed_initialized)
        assert m.call_count == 0
```

### Step 3: Run tests — confirm red

- [ ] Run the scoped test to confirm failure:
  ```bash
  pixi run test test_pdf_parser
  ```
  Expected failure: `ModuleNotFoundError` or `ImportError` on `from trust_generator.v3.parsers.pdf_parser import parse_pdf` (and `_normalize_field_values`). If `pypdf` or `reportlab` are not installed, `pytest.importorskip` causes a module-level skip — confirm these are available first via `pixi run python -c "import pypdf, reportlab"`.

### Step 4: Commit red

- [ ] Stage and commit:
  ```bash
  git add tests/v3/parsers/test_pdf_parser.py
  git commit -m "test(v3/parsers): red — pdf parser smoke + field-presence normalization tests (§6.9)"
  ```

---

## Task 2: Green — pdf_parser.py implementation

**Commit:** `feat(v3/parsers): green — pdf_parser AcroForm iteration + _normalize_field_values (§6.9)`

### Dependencies (imports from sibling plans)

Both helpers below are authored and owned by the `docx` plan. This plan consumes them read-only; it does not modify `docx_parser.py`.

| Helper | Owning plan | Spec reference | Confirmed signature | Import path |
|--------|-------------|----------------|---------------------|-------------|
| `_apply_post_promotion_protocol` | `docx` §6.6 (cycle 4b refactor) | Spec §5.3 step 4, Implementation note | `(result: TrustData, parsed_trust_type: TrustType \| None, parsed_marital_status: MaritalStatus \| None) -> None` | `from trust_generator.v3.parsers.docx_parser import _apply_post_promotion_protocol` |
| `_apply_post_merge_resolution` | `docx` §6.8 (cycle 6 green) | Spec §5.3 step 6, Implementation note | `(result: TrustData, exclusions_string: str) -> None` — CorporateTrustee discrimination runs inside via `_is_entity_name`; no caller-side flags argument | `from trust_generator.v3.parsers.docx_parser import _apply_post_merge_resolution` |
| `_is_entity_name` *(optional direct import)* | `docx` §6.8 | Spec §5.4.9 | `(name: str) -> bool` — available as module-level helper; import only if pdf_parser needs it independently | `from trust_generator.v3.parsers.docx_parser import _is_entity_name` |

Signatures confirmed via peer-DM with the `docx` teammate during plan drafting. The 2-arg form of `_apply_post_merge_resolution` (dropping `trustee_entity_flags`) is the docx plan's committed shape — CorporateTrustee discrimination moves entirely inside the helper via re-application of `_is_entity_name` per `result.successor_trustees` entry. The pdf parser's step 5 therefore emits plain `SuccessorTrustee(full_legal_name=name)` entries and carries no entity-flag bookkeeping.

Coercion helpers owned by `json-and-coercion` §6.4 (cycle 3):

| Helper | Import path |
|--------|-------------|
| `_to_date(text) -> date \| None` | `from trust_generator.v3.parsers.coercion import _to_date` |
| `_to_decimal(text) -> Decimal` | `from trust_generator.v3.parsers.coercion import _to_decimal` |
| `_to_address(text_or_fields) -> Address` | `from trust_generator.v3.parsers.coercion import _to_address` |
| `_to_person_reference(text_or_fields) -> PersonReference` | `from trust_generator.v3.parsers.coercion import _to_person_reference` |

### Step 1: Create pdf_parser.py

- [ ] Create `src/trust_generator/v3/parsers/pdf_parser.py`:

```python
"""Parse a completed fillable PDF questionnaire into TrustData (v3).

AcroForm field names use dotted schema paths (e.g., 'grantor.full_legal_name')
matching the v3 schema layout — the same convention as the v2.2 fillable PDF.

Public API:
    parse_pdf(filepath: Path, seed_initialized: TrustData) -> TrustData

Internal helpers:
    _normalize_field_values(fields_dict) -> dict[str, str | None]
        Implements §5.4.A: absent / present-None / present-empty / whitespace-only
        all normalize to None. After normalization all coercion helpers receive
        either None or a non-empty stripped string.
"""
from __future__ import annotations

import logging
from pathlib import Path

from pypdf import PdfReader  # type: ignore[import-untyped]

from trust_generator.v3.parsers.coercion import (
    _to_address,
    _to_date,
    _to_decimal,
    _to_person_reference,
)
from trust_generator.v3.parsers.docx_parser import (
    _apply_post_merge_resolution,
    _apply_post_promotion_protocol,
)
from trust_generator.v3.schema import TrustData, TrustType, MaritalStatus

log = logging.getLogger(__name__)


def _normalize_field_values(
    fields_dict: dict,
) -> dict[str, str | None]:
    """Normalize AcroForm field values per §5.4.A.

    Three field-presence states all collapse to None:
    1. Field absent — key not in fields_dict (caller excludes it; None implied).
    2. Field present, value None — Field.value is None.
    3. Field present, value empty or whitespace-only — Field.value.strip() == "".

    Returns a plain dict[str, str | None]. Values are either None or a
    non-empty stripped string; coercion helpers downstream receive no
    empty strings.
    """
    result: dict[str, str | None] = {}
    for name, field_obj in fields_dict.items():
        raw = getattr(field_obj, "value", None)
        if raw is None:
            result[name] = None
        elif isinstance(raw, str):
            stripped = raw.strip()
            result[name] = stripped if stripped else None
        else:
            # Non-string non-None values (e.g., bool for checkboxes): stringify.
            as_str = str(raw).strip()
            result[name] = as_str if as_str else None
    return result


def parse_pdf(filepath: Path, seed_initialized: TrustData) -> TrustData:
    """Parse a fillable PDF questionnaire INTO a copy of seed_initialized.

    Implements the seven-step post-promotion merge protocol (spec §5.3).
    seed_initialized is never mutated (P3): the parser deepcopies at entry.

    Parameters
    ----------
    filepath:
        Path to the completed fillable PDF. Raises FileNotFoundError if absent.
    seed_initialized:
        The TrustData produced by promote_seed() at consultation time.
        This argument is required (no default) to keep the post-promotion
        contract loud at every call site. P3 postcondition: this value is
        field-level equal before and after this call.

    Returns
    -------
    TrustData
        A filled copy of seed_initialized. Return shape is TrustData only
        (no ExtractionTrace pairing — the trace is OCR-specific, per §5.2).
    """
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"PDF not found: {filepath}")

    log.info("Parsing PDF questionnaire: %s", filepath)

    # §5.3 step 1: deepcopy — satisfies P3 immutability postcondition.
    result = seed_initialized.model_copy(deep=True)

    # §5.3 step 2: extract content from AcroForm fields.
    reader = PdfReader(str(filepath))
    raw_fields = reader.get_fields() or {}
    flat = _normalize_field_values(raw_fields)

    # Capture parser-internal carriers for post-merge resolution (§5.3 step 6).
    # exclusions_string does not transit through `result` (no v3 schema field).
    exclusions_string: str = flat.get("text_blocks.exclusions") or ""

    # §5.3 step 3: coerce values to v3 types.
    # Helpers from json-and-coercion §6.4 (coercion._to_*).
    # Each helper receives None or a non-empty stripped string (post-normalization).

    # §5.3 step 4: detect and apply trust_type / marital_status mutations.
    # _apply_post_promotion_protocol from docx §6.6 cycle 4b refactor.
    # None / absent gate: if the field normalized to None, pass None to the
    # helper — the helper treats None as "no mutation requested" (spec §5.3 step 4
    # "None / absent gate" sub-bullet).
    _trust_type_raw = flat.get("trust_id.trust_type")
    parsed_trust_type: TrustType | None = None
    if _trust_type_raw is not None:
        try:
            parsed_trust_type = TrustType(_trust_type_raw)
        except ValueError:
            log.warning(
                "Unknown trust_type value %r in PDF field trust_id.trust_type; "
                "seed value preserved.",
                _trust_type_raw,
            )

    _marital_raw = flat.get("trust_id.marital_status")
    parsed_marital_status: MaritalStatus | None = None
    if _marital_raw is not None:
        try:
            parsed_marital_status = MaritalStatus(_marital_raw)
        except ValueError:
            log.warning(
                "Unknown marital_status value %r in PDF field trust_id.marital_status; "
                "seed value preserved.",
                _marital_raw,
            )

    _apply_post_promotion_protocol(result, parsed_trust_type, parsed_marital_status)

    # §5.3 step 5: apply remaining mutations.
    # Grantor fields.
    if (_name := flat.get("grantor.full_legal_name")) is not None:
        result.grantor.full_legal_name = _name
    if (_dob := flat.get("grantor.date_of_birth")) is not None:
        _parsed_dob = _to_date(_dob, source_label="grantor.date_of_birth")
        if _parsed_dob is not None:
            result.grantor.date_of_birth = _parsed_dob
    if (_addr := flat.get("grantor.address")) is not None:
        # Prefer structured sub-fields if present; fall back to free-text.
        _structured_addr = {
            k.removeprefix("grantor.address."): v
            for k, v in flat.items()
            if k.startswith("grantor.address.") and v is not None
        }
        result.grantor.address = (
            _to_address(_structured_addr) if _structured_addr else _to_address(_addr)
        )

    # Co-grantor fields (when co_grantor was materialized by the protocol).
    if result.co_grantor is not None:
        if (_co_name := flat.get("co_grantor.full_legal_name")) is not None:
            result.co_grantor.full_legal_name = _co_name
        if (_co_dob := flat.get("co_grantor.date_of_birth")) is not None:
            _parsed_co_dob = _to_date(_co_dob, source_label="co_grantor.date_of_birth")
            if _parsed_co_dob is not None:
                result.co_grantor.date_of_birth = _parsed_co_dob

    # Trust identity fields beyond trust_type / marital_status.
    if (_tname := flat.get("trust_id.desired_trust_name")) is not None:
        result.trust_id.desired_trust_name = _tname

    # Withdrawal steps: numbered fields withdrawal[i].age / .percent / .description.
    _withdrawal_steps = []
    i = 0
    while True:
        _age_raw = flat.get(f"withdrawal[{i}].age")
        _pct_raw = flat.get(f"withdrawal[{i}].percent")
        _desc_raw = flat.get(f"withdrawal[{i}].description")
        if _age_raw is None and _pct_raw is None and _desc_raw is None:
            break
        if _age_raw is not None:
            try:
                _age = int(_age_raw)
            except (ValueError, TypeError):
                log.warning(
                    "Could not parse withdrawal[%d].age %r; row dropped (§5.4.7).",
                    i,
                    _age_raw,
                )
                i += 1
                continue
            from trust_generator.v3.schema import WithdrawalStep
            _withdrawal_steps.append(
                WithdrawalStep(
                    age=_age,
                    percent=_to_decimal(_pct_raw or "0"),
                    description=_desc_raw or "",
                )
            )
        i += 1
    if _withdrawal_steps:
        result.withdrawal_schedule = _withdrawal_steps

    # Successor trustees: numbered fields successor_trustees[i].full_legal_name.
    # Step 5 emits plain SuccessorTrustee(full_legal_name=name) entries onto
    # result.successor_trustees. CorporateTrustee discrimination (§5.4.9) runs
    # entirely inside _apply_post_merge_resolution (step 6) via re-application
    # of _is_entity_name per entry — no caller-side entity-flag bookkeeping needed.
    from trust_generator.v3.schema import SuccessorTrustee
    i = 0
    while True:
        _tname_raw = flat.get(f"successor_trustees[{i}].full_legal_name")
        if _tname_raw is None:
            break
        result.successor_trustees.append(SuccessorTrustee(full_legal_name=_tname_raw))
        i += 1

    # §5.3 step 6: post-merge resolution passes.
    # _apply_post_merge_resolution from docx §6.8 — 2-arg form (confirmed).
    # Internally iterates result.successor_trustees, applies _is_entity_name,
    # reconstructs CorporateTrustee entries, and runs disinheritance resolution.
    _apply_post_merge_resolution(result, exclusions_string)

    log.info(
        "Parsed PDF successfully — %d fields with values.",
        sum(1 for v in flat.values() if v is not None),
    )

    # §5.3 step 7: return result.
    return result
```

**Implementation notes for the executor:**

- `_to_date`, `_to_decimal`, `_to_address`, `_to_person_reference` signatures may differ slightly from what is shown above (e.g., `source_label` parameter). Verify exact signatures from `coercion.py` (authored by `json-and-coercion`) before writing and adjust call sites accordingly.
- `_apply_post_promotion_protocol` and `_apply_post_merge_resolution` signatures are specified in spec §5.3 Implementation note. Verify the exact signatures by reading `docx_parser.py` (authored by `docx`) before writing.
- The field mapping above is representative. Adapt based on the actual v3 schema field names in `src/trust_generator/v3/schema.py` and the v2.2 PDF field naming convention in `src/trust_generator/v2/parsers/pdf_parser.py`.
- Do NOT import `promote_seed` into `pdf_parser.py` — importing is fine for the schema models, but the parser must never call `promote_seed` (P1). The `test_post_promotion_protocol_not_reinvoked` test patches the name in the module's namespace; the import must exist for the patch to bind. If `promote_seed` is not imported, omit the patch target and adjust the test.
- `pypdf`'s `PdfReader.get_fields()` returns `None` if the PDF has no AcroForm; the `or {}` guard handles this (mirrored from v2).

### Step 2: Run tests — confirm green

- [ ] Run the scoped test:
  ```bash
  pixi run test test_pdf_parser
  ```
  All tests in `test_pdf_parser.py` should pass. If the fill-and-reparse tests fail because `PdfWriter.update_page_form_field_values` does not emit fields readable by `PdfReader.get_fields()` (a known pypdf version quirk), construct fixtures using `reportlab`'s `canvas` + AcroForm API instead. Adjust fixture helper `_write_acroform_pdf` in the test file accordingly (test-file edits are within blast-radius).

### Step 3: Run the full gate

- [ ] Run the full project gate:
  ```bash
  pixi run check
  ```
  Expected: **green**. Fix any lint or mypy issues before proceeding.

### Step 4: Commit green

- [ ] Stage and commit:
  ```bash
  git add src/trust_generator/v3/parsers/pdf_parser.py
  git commit -m "feat(v3/parsers): green — pdf_parser AcroForm iteration + _normalize_field_values (§6.9)"
  ```

**Refactor:** None expected — the green output is already minimal. The pdf parser is structurally thin: AcroForm field iteration produces a flat dict directly (no table walking), `_normalize_field_values` is a single-pass dict comprehension, and all coercion and protocol complexity is delegated to pre-built helpers. There is no structural duplication within `pdf_parser.py`, no nested conditionals that flatten into dispatch, and no mixed orthogonal concerns that extract cleanly at this point. Per the `refactor_threshold` rule in `development-strategy.md`: **no refactor stage — green output is already minimal.**

---

## Exit criterion

`pixi run check` passes green after Task 2's commit. The pdf parser test suite (~10–12 tests: 4 field-presence + 2 smoke + 1 error surface + 5 fill-and-reparse) is green. The suite does not touch `__init__.py`, `registry.py`, `docx_parser.py`, or `coercion.py` — those are sibling blast-radii.
