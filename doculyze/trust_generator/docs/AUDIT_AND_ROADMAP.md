# Trust Generator — Codebase Audit & v2.1 Feature Specification

**Date:** 2026-03-29
**Branch:** `claude/audit-and-feature-planning-2isX8`
**Status:** Implemented (document preserved as historical record)

---

## Part 1: Codebase Audit

### 1.1 Stale & Redundant Files

| File                                             | Issue                                                                                                                                                                                  | Recommendation                                                                                       |
| ------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `README.old.md`                                  | Legacy v1.x README. References Python 3.8+, pip-based install, original 3-file architecture (`trust_generator.py`, `questionnaire_parser.py`, `trust_builder.py`). No longer accurate. | **Delete.** Historical context is already captured in CLAUDE.md's "Origin" section.                  |
| `src/trust_generator/_legacy/__init__.py`        | Empty init for legacy package.                                                                                                                                                         | Retain with legacy dir (excluded from lint/typecheck).                                               |
| `src/trust_generator/_legacy/build.py` (33.7 KB) | Original monolithic trust builder — the largest file in the repo. Kept for reference.                                                                                                  | Retain for now. Consider archiving to a `docs/legacy/` folder or a tagged git ref to reduce clutter. |
| `src/trust_generator/_legacy/parse.py` (13.7 KB) | Original parser.                                                                                                                                                                       | Same as above.                                                                                       |
| `src/trust_generator/_legacy/app.py` (8.6 KB)    | Original GUI/CLI entry point.                                                                                                                                                          | Same as above.                                                                                       |
| `src/trust_generator/_legacy/dev.py`             | Original dev entry point.                                                                                                                                                              | Same as above.                                                                                       |
| `assets/Family_Trust_Template.docx`              | Template from v1.x. The v2.0 generator builds documents programmatically via `DocxFormatter` and does not read this template.                                                          | **Verify if referenced anywhere.** If not, move to `docs/legacy/` or delete.                         |

### 1.2 Version Number Inconsistencies

| Location                                     | Version         | Notes                                                                                    |
| -------------------------------------------- | --------------- | ---------------------------------------------------------------------------------------- |
| `pyproject.toml` `[project].version`         | `1.0.0`         | Should be `2.0.0` to match the v2.0 rewrite.                                             |
| `pixi.toml` `[package].version`              | `2.0.0.0-alpha` | Conda build version — correct intent, but 4-part version is non-standard.                |
| `generators/trust_document.py` `__version__` | `2.0.0-alpha`   | Hardcoded in a single module — should be sourced from `pyproject.toml` or `__init__.py`. |

**Recommendation:** Unify to a single source of truth. Set `pyproject.toml` version to `2.0.0` (or `2.1.0-dev` once v2.1 work begins). Use `importlib.metadata` in `__init__.py` to expose `__version__`, and remove the hardcoded string from `trust_document.py`.

### 1.3 Code Quality

| Area                        | Status                                                                                                                                                                                     |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Ruff lint**               | All checks passed (0 warnings, 0 errors)                                                                                                                                                   |
| **TODO/FIXME/HACK markers** | None found in source or tests. Clean.                                                                                                                                                      |
| **Dead imports**            | None detected by ruff.                                                                                                                                                                     |
| **Legacy references**       | No imports from `_legacy` anywhere in the active codebase. Clean separation.                                                                                                               |
| **Unused exports**          | `__init__.py` re-exports `TrustData`, `AppConfig`, `load_config`, `parse_file`, `validate`, `generate_trust_document`, `generate_printable_questionnaire` — all are meaningful public API. |

### 1.4 Test Coverage Gaps

| Source Module                           | Test File             | Status                                                                           |
| --------------------------------------- | --------------------- | -------------------------------------------------------------------------------- |
| `schema.py`                             | `test_schema.py`      | Covered                                                                          |
| `config.py`                             | `test_config.py`      | Covered                                                                          |
| `parsers/`                              | `test_parsers.py`     | Covered                                                                          |
| `validators/`                           | `test_validators.py`  | Covered                                                                          |
| `generators/trust_document.py`          | `test_generators.py`  | Covered                                                                          |
| `generators/printable_questionnaire.py` | `test_printable.py`   | Covered                                                                          |
| `ui/cli.py`                             | `test_cli.py`         | Covered                                                                          |
| `ui/gui.py`                             | **No test file**      | GUI code — difficult to unit test without mocking Tkinter. Consider smoke tests. |
| `ui/app.py`                             | **No test file**      | Entry-point dispatcher — low risk, but could have a simple mode-detection test.  |
| `logging_setup.py`                      | **No test file**      | Low risk.                                                                        |
| Integration                             | `test_integration.py` | Covered                                                                          |

**71 tests** per CLAUDE.md. No test file for the GUI, app dispatcher, or logging module.

### 1.5 Configuration & Build Issues

| Issue                       | Details                                                                                                                                                                                                                                                                |
| --------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Python version mismatch** | `pyproject.toml` requires `>=3.12`, but `pixi.lock` locks Python 3.14.3. This is fine for forward compat, but the `config.py` still has a `sys.version_info >= (3, 11)` guard for `tomllib` vs `tomli` — since the minimum is 3.12, the `tomli` fallback is dead code. |
| **Windows-only platform**   | `pixi.toml` targets `win-64` only. The code itself is cross-platform (config.py handles both win32 and Unix paths), but CI/testing on non-Windows is unsupported by the build config.                                                                                  |
| **No CI/CD**                | No `.github/workflows/` directory. Tests, lint, and typecheck are manual.                                                                                                                                                                                              |
| **No CHANGELOG**            | No changelog file exists. Version history is only in git log.                                                                                                                                                                                                          |
| **`scripts/bundle.py`**     | Functional but minimal — no error handling, no logging. Acceptable for an internal build script.                                                                                                                                                                       |

### 1.6 Schema & Architecture Observations

| Observation                                       | Impact                                                                                                                                                                                                                    |
| ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Husband/Wife assumption**                       | `TrustData` has `husband: PersonInfo` and `wife: PersonInfo` as hardcoded fields. Single-grantor trusts and non-traditional couples require schema changes. This is the v2.1 roadmap item "single-grantor trust support." |
| **`MarriageInfo` unused in generation**           | `MarriageInfo` is parsed and stored but the trust document generator does not reference it. It is "available for future use" per its docstring.                                                                           |
| **`InsuranceStrategy` enum has only one variant** | `InsuranceStrategy.SPOUSE_THEN_CHILDREN` is the only option. This is a placeholder for future expansion.                                                                                                                  |

### 1.7 GitHub Issues

- **Open issues:** 0
- **Closed issues:** 0
- No issue tracker activity.

---

## Part 2: v2.1 Feature Update — Design & Specification

The v2.1 roadmap (from CLAUDE.md) defines three features. Below is the implementation design for each, ordered by recommended priority.

### Feature 1: Single-Grantor Trust Support

**Priority:** High — This is the most impactful feature. Many clients are single individuals, widows/widowers, or unmarried partners. Currently the tool cannot serve them at all.

#### 1.1 Requirements

- Support trusts with exactly one grantor (no spouse).
- The 12-article structure and 4-schedule layout must be preserved.
- The questionnaire, parser, validator, generator, and GUI must all handle the single-grantor case.
- Existing husband+wife (joint) trust behavior must not regress.

#### 1.2 Schema Changes (`schema.py`)

```
# New enum
class TrustType(str, Enum):
    JOINT = "joint"        # husband + wife (current behavior)
    INDIVIDUAL = "individual"  # single grantor

# Modified TrustData
class TrustData(BaseModel):
    trust_type: TrustType = TrustType.JOINT

    # Replace husband/wife with a flexible grantors list
    # Option A: Add grantor field, keep husband/wife for backward compat
    grantor: PersonInfo = Field(default_factory=PersonInfo)  # primary (individual trusts)
    husband: PersonInfo = Field(default_factory=PersonInfo)  # joint trusts
    wife: PersonInfo = Field(default_factory=PersonInfo)     # joint trusts

    # Option B (recommended): Use a grantors list
    # grantors: list[PersonInfo] = Field(default_factory=list)
```

**Recommended approach (Option A):** Add `trust_type` and `grantor` fields. For `JOINT` trusts, `husband` and `wife` continue to work as-is. For `INDIVIDUAL` trusts, `grantor` is the single person. Computed properties (`trust_name`, `trustee_names`, etc.) branch on `trust_type`. This minimizes disruption to the existing generator.

#### 1.3 Validator Changes (`validators/validate.py`)

- When `trust_type == INDIVIDUAL`: skip wife-specific field checks, skip marriage info checks, validate `grantor` instead of `husband`.
- When `trust_type == JOINT`: existing validation unchanged.
- New cross-field rule: `trust_type == INDIVIDUAL` must have empty `wife` and `marriage` fields (warn if populated).

#### 1.4 Generator Changes (`generators/trust_document.py`)

- The `_TrustDocGen` class methods that reference `data.husband_name` and `data.wife_name` need conditionals:
    - Article 1 (Declaration): "I, [GRANTOR], hereby declare..." vs "We, [HUSBAND] and [WIFE], hereby declare..."
    - Article 2 (Property): Drop community/separate property classification for individual trusts.
    - Article 5 (Surviving Spouse): Skip or replace with incapacity provisions for individual trusts.
    - Articles referencing "both Grantors" need singular alternatives.
- Estimated touch points: ~15-20 locations in the generator.

#### 1.5 Parser Changes

- `docx_parser.py`: Detect single-grantor questionnaires (e.g., "Wife" section is blank or absent). Set `trust_type` accordingly.
- `json_parser.py`: Accept `trust_type` field directly.

#### 1.6 GUI Changes

- Step 1 (Import): Show detected trust type.
- Step 2 (Review): Hide wife/marriage sections for individual trusts.

#### 1.7 Migration & Compatibility

- Existing `.json` files without `trust_type` default to `JOINT` (backward compatible).
- Existing `.docx` questionnaires with both spouses filled in → `JOINT`.
- New printable questionnaire variant for individual trusts.

---

### Feature 2: Full Data Entry GUI Mode

**Priority:** Medium — Enables paralegals to create trusts from scratch in the GUI without preparing a .docx questionnaire first. Increases adoption for simple cases.

#### 2.1 Requirements

- The GUI must support field-by-field data entry for all `TrustData` fields.
- The current 4-step workflow (Import → Review → Generate → Results) becomes 5 steps (New/Import → Entry → Review → Generate → Results).
- Validation runs continuously as data is entered, with inline feedback.
- Data can be saved/loaded as `.json` for work-in-progress.

#### 2.2 GUI Architecture

```sh
Step 0 (New): Choose mode
  ├─ "Import Questionnaire" → existing Step 1 (file picker)
  └─ "New Trust" → Step 1a (data entry)

Step 1a (Data Entry): Tabbed form
  ├─ Tab: Trust Info (trust_type, trust_id, office)
  ├─ Tab: Grantor(s) (husband/wife or single grantor)
  ├─ Tab: Family (children)
  ├─ Tab: Trustees (successor_trustees)
  ├─ Tab: Assets (6 sub-tabs, one per asset category)
  ├─ Tab: Beneficiaries (shares, bequests, withdrawal schedule)
  ├─ Tab: Elections (checkboxes and dropdowns for all Elections fields)
  └─ Tab: Notes & Custom Terms (text_blocks)

Step 2 (Review): Same as current, shows validation report
Step 3 (Generate): Same as current
Step 4 (Results): Same as current
```

#### 2.3 Implementation Plan

1. **`ui/forms.py` (new):** Reusable form widget classes:
    - `TextField` — label + entry, bound to a schema field path.
    - `DropdownField` — label + combobox, bound to an enum field.
    - `CheckboxField` — label + checkbutton, bound to a bool field.
    - `ListField` — dynamic add/remove rows for list-type fields (children, assets, etc.).
    - `FormTab` — a `ttk.Frame` that holds a set of fields and can serialize to/from a `dict`.

2. **`ui/data_binder.py` (new):** Two-way binding between form widgets and a `TrustData` instance:
    - `bind(widget, field_path)` — connects a widget to a dotted path (e.g., `"husband.full_legal_name"`).
    - `to_trust_data()` → `TrustData` — collects all widget values into a model.
    - `from_trust_data(data)` — populates widgets from a model.

3. **`ui/gui.py` modifications:**
    - Add "New Trust" button to Step 0.
    - Insert data entry step with tabbed form.
    - Add "Save Draft" / "Load Draft" buttons (JSON serialization via `TrustData.model_dump_json()` / `TrustData.model_validate_json()`).
    - Wire "Continue to Review" to run validation.

4. **Validation integration:**
    - Run `validate()` on every tab change (debounced).
    - Show inline indicators (red/yellow icons) next to fields with findings.

#### 2.4 Estimated Scope

- ~2 new files (`forms.py`, `data_binder.py`), ~400-600 lines each.
- ~100-150 lines of modifications to `gui.py`.
- New tests for form serialization and data binding.

---

### Feature 3: Fillable PDF Questionnaire

**Priority:** Lower — Nice-to-have for firms that prefer PDF intake over .docx. Requires two new dependencies (`reportlab`, `pypdf`).

#### 3.1 Requirements

- Generate a fillable PDF with form fields mapped to `TrustData` schema paths.
- Parse a completed fillable PDF back into `TrustData`.
- PDF must have the same firm branding as the printable .docx questionnaire.
- Checkbox fields in the PDF must map to `Elections` enum values.

#### 3.2 Architecture

```
generators/
├── pdf_questionnaire.py    # NEW: generate fillable PDF
parsers/
├── pdf_parser.py           # NEW: parse completed PDF → TrustData
├── registry.py             # Updated: register .pdf extension
```

#### 3.3 Implementation Plan

1. **`generators/pdf_questionnaire.py`:**
    - Use `reportlab` to build a PDF with `AcroForm` fields.
    - Field naming convention: use dotted schema paths as PDF field names (e.g., `husband.full_legal_name`).
    - Layout mirrors the printable .docx questionnaire structure.
    - Firm branding (name, address, phone) from `AppConfig`.

2. **`parsers/pdf_parser.py`:**
    - Use `pypdf` to extract form field values.
    - Map field names back to `TrustData` paths.
    - Handle checkboxes → enum conversion.
    - Produce `TrustData` via the same validation pipeline as other parsers.

3. **`parsers/registry.py`:**
    - Register `.pdf` extension → `pdf_parser.parse_pdf()`.

4. **CLI integration:**
    - `create-fillable-pdf` subcommand (parallel to `create-printable`).
    - `generate` and `validate` accept `.pdf` input.

5. **Dependencies:**
    - Add `reportlab` and `pypdf` to `pyproject.toml` and `pixi.toml`.
    - Both are pure-Python, well-maintained, and conda-forge available.

#### 3.4 Field Mapping Strategy

```python
# PDF field name → TrustData path
FIELD_MAP = {
    "husband.full_legal_name": ("husband", "full_legal_name"),
    "husband.date_of_birth": ("husband", "date_of_birth"),
    "elections.spendthrift": ("elections", "spendthrift"),
    # ... ~60 scalar fields
    # List fields use indexed names:
    "children.0.name": ("children", 0, "name"),
    "children.0.dob": ("children", 0, "dob"),
    # Up to N rows pre-allocated in the PDF
}
```

#### 3.5 Estimated Scope

- ~2 new files, ~300-500 lines each.
- ~20 lines of registry changes.
- New test files for PDF generation and parsing.
- New CLI subcommand (~10 lines in `cli.py`).

---

## Part 3: Recommended Action Items

### Immediate (housekeeping)

1. Delete `README.old.md`.
2. Unify version numbers: set `pyproject.toml` version to `2.0.0`, remove hardcoded `__version__` from `trust_document.py`.
3. Remove the dead `tomli` fallback in `config.py` (minimum Python is 3.12, `tomllib` is always available).
4. Verify `assets/Family_Trust_Template.docx` is unused and remove or archive it.

### Short-term (v2.1 development)

1. Implement single-grantor trust support (Feature 1).
2. Add basic CI (GitHub Actions) for test + lint + typecheck on push.
3. Create a CHANGELOG.md.

### Medium-term (v2.2+)

1. Implement full data entry GUI (Feature 2).
2. Implement fillable PDF questionnaire (Feature 3).
3. Add GUI smoke tests (headless Tkinter or screenshot-based).
