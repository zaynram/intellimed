# Crosby & Crosby Law (Internal): Trust-Generator

**v2.2.0**

## Project Context

**Trust Generator** is a Python tool for Crosby and Crosby LLP that automates generation of Family Trust documents. It accepts client intake data from multiple formats (.docx questionnaire, .json, .pdf fillable form, or GUI entry), validates it, and produces fully populated trust documents with attorney-review sections highlighted.

The trust document structure is derived from a **75-page WealthCounsel trust template**, condensed to ~18 pages covering 12 articles + 4 schedules. The 12-article structure and the set of information collected must be preserved — attorneys are trained to review documents in this format.

Target users: **paralegals** who run it day-to-day, **attorneys** who review output. Clients (often elderly) never interact with the software directly.

### Origin

The original codebase was a proof-of-concept built by the lead developer using AI-assisted coding, described as "rudimentary." It was rewritten from scratch (v2.0) to fix critical bugs and transform it into a production-quality paralegal workflow tool. The legacy code is preserved in `src/trust_generator/_legacy/` for reference but is excluded from linting and type checking.

## Features

- **Schema-centric pipeline**: All components connect through the `TrustData` Pydantic model for type safety and validation
- **Multiple input formats**: Parse `.docx` questionnaires, `.json` files, or filled `.pdf` forms
- **Full GUI data entry**: Paralegals can enter and edit data field-by-field with reusable form widgets, list editors, and inline validation
- **Gender-inclusive party labels**: Configurable `party_a_label`/`party_b_label` replace hardcoded husband/wife terminology
- **Draft management**: Auto-save/load/purge drafts in `%APPDATA%/trust-generator/drafts/` with SSN exclusion and 90-day auto-purge
- **List editing**: Add and remove children, trustees, beneficiaries, and assets via ListEditor widgets
- **Fillable PDF questionnaire**: Generate fillable PDFs for client intake; parse completed PDFs back into TrustData
- **Validation before generation**: Fields classified as provided/defaulted/missing with cross-field rule checks
- **Pre-generation check**: Critical fields must be non-empty before document generation proceeds
- **Clean printable questionnaire**: Blank `.docx` with empty answer cells, checkbox symbols, and firm branding
- **Configurable firm identity**: Firm name, address, phone, and jurisdiction defaults in `config/firm.toml`

## Architecture

Schema-centric pipeline (hexagonal architecture). Every component connects through the `TrustData` Pydantic model:

```sh
Input (.docx | .json | .pdf | GUI manual entry)
  |
  v
Parser (parsers/)  -->  TrustData (schema.py)  +  ValidationReport
                              |
                              +-->  Validator (validators/)
                              |         checks completeness, cross-field rules
                              |
                              +-->  GUI Review (ui/gui.py)
                              |         displays data + validation inline
                              |
                              +-->  Generator (generators/)
                                        TrustData + AppConfig -> .docx output
```

### Module Structure

```sh
src/trust_generator/
├── schema.py                  # TrustData Pydantic model — the canonical data type
├── config.py                  # TOML config loader (firm info, jurisdiction defaults)
├── logging_setup.py           # Logging configuration (file + console)
├── parsers/
│   ├── registry.py            # parse_file() — auto-detects format by extension
│   ├── docx_parser.py         # Parses .docx questionnaire → TrustData
│   ├── json_parser.py         # Parses .json → TrustData (via Pydantic validation)
│   └── pdf_parser.py          # Parses completed fillable PDFs → TrustData
├── validators/
│   ├── report.py              # ValidationReport, Finding, FieldEntry models
│   └── validate.py            # validate(TrustData) → ValidationReport
├── generators/
│   ├── docx_formatter.py      # Reusable DocxFormatter class (h1, body, manual_review, etc.)
│   ├── trust_document.py      # generate_trust_document() — 12 articles + 4 schedules
│   ├── printable_questionnaire.py  # generate_printable_questionnaire() — clean blank form
│   └── pdf_questionnaire.py   # Fillable PDF generation (requires reportlab)
├── ui/
│   ├── app.py                 # main() entry point — auto-detects GUI vs CLI
│   ├── gui.py                 # Tkinter 4-step workflow: Import → Review → Generate → Results
│   ├── cli.py                 # Argparse subcommands: generate, validate, parse, create-printable
│   ├── dev.py                 # trust-generator-cli entry point (forces CLI mode)
│   ├── forms.py               # Reusable form widgets (TextField, DropdownField, CheckboxField, ListEditor, ToolTip)
│   └── drafts.py              # Managed draft save/load/purge (%APPDATA%/trust-generator/drafts/)
├── _legacy/                   # Original code (excluded from lint/typecheck, kept for reference)
├── app.py                     # Thin wrapper → ui.app.main (for pyproject.toml entry point)
└── dev.py                     # Thin wrapper → ui.app.main("cli") (for pyproject.toml entry point)
config/
└── firm.toml                  # Editable firm identity + jurisdiction defaults
```

### Key Design Decisions

- **Pydantic schema as the single source of truth**: All parsers produce `TrustData`, all generators consume it. Type safety eliminates the entire class of string-key typo bugs and dict-access crashes from the original.
- **Elections are typed enums with `bool` fields**: The original `if self.g("spendthrift", str(True))` bug (always truthy) is impossible — `spendthrift` is a proper `bool` that defaults to `True` but respects `False`.
- **Config file for firm identity**: Firm name, address, phone, and jurisdiction defaults are in `config/firm.toml`, not hardcoded in Python. For deployed `.exe`, config is copied to `%APPDATA%/trust-generator/` on first run.
- **Validation before generation**: The validator classifies every field as provided/defaulted/missing and checks cross-field rules (share percentages sum to 100, etc.). Generation is blocked on errors.
- **Clean printable questionnaire**: Solves the placeholder-text complaint. `create-printable` generates a blank .docx with empty answer cells, checkbox symbols, and firm branding — no hint text to remove.
- **Configurable party labels**: `party_a_label`/`party_b_label` control all display text. Internal field names use `party_a`/`party_b` with JSON backward compat via Pydantic `validation_alias`.
- **Managed draft system**: Drafts saved in `%APPDATA%/trust-generator/drafts/` with SSN exclusion and 90-day auto-purge.
- **Pre-generation check**: Critical fields (trust_name, trust_date, state, county, grantor/party names, trustee_names, ssn_owner_name) must be non-empty before document generation.

## Key Data Structures

The `TrustData` model in `schema.py` contains nested Pydantic models:

| Model                                           | Fields                                                                                  | Purpose                                     |
| ----------------------------------------------- | --------------------------------------------------------------------------------------- | ------------------------------------------- |
| `PersonInfo`                                    | full_legal_name, dob, ssn, address, phone, email, employer, maiden_name                 | Grantor (party_a or party_b)                |
| `TrustIdentity`                                 | desired_trust_name, date, state, county, whose_ssn                                      | Trust ID and jurisdiction                   |
| `Elections`                                     | 19 fields (enums + bools)                                                               | All checkbox-driven trust configuration     |
| `TextBlocks`                                    | statement_of_intent, personal_message, custom terms, notes                              | Freeform attorney-review sections           |
| `Child`, `SuccessorTrustee`, `BeneficiaryShare` | Varies                                                                                  | List items                                  |
| 6 asset models                                  | `RealProperty`, `FinancialAccount`, `Vehicle`, `InsurancePolicy`, `Pension`, `Valuable` | Asset categories                            |
| `party_a_label`, `party_b_label`                | `str`                                                                                   | Display labels for joint trust parties (default: Husband/Wife) |
| `SsnOwner`                                      | enum                                                                                    | Whose SSN to use for trust tax ID (PARTY_A, PARTY_B, GRANTOR)  |

Computed properties on `TrustData`: `trust_name`, `trust_date`, `trustee_names`, `ssn_owner_name`, `party_a_name`, `party_b_name`, `state`, `county`, `asset_summary()`.

## v2.3 Roadmap

- **Firm config GUI settings screen**: Edit `firm.toml` values from within the GUI
- **SSN field masking/encryption**: Mask SSN display in the GUI and encrypt at rest in drafts
- **Complete PDF questionnaire**: Add list fields (children, assets) and elections to fillable PDF

### v3 Firm Configuration (`config/firm.toml`)

**Location.** Hand-edited firm configuration lives at `config/firm.toml`, anchored by a `#:schema ./firm-config.schema.json` directive that tombi (and any JSON-Schema-aware TOML LSP) uses for edit-time validation. The canonical key reference is in `docs/superpowers/specs/2026-04-21-firm-config-design.md`.

**Env-var overlay.** Any field can be overridden at runtime via an environment variable prefixed `TGV3_` with `__` as the nested delimiter. Example: `TGV3_ESTATE_THRESHOLDS__SINGLE_HARD=5000000` overrides `estate_thresholds.single_hard` without editing the file. Env overlay sits above TOML in the precedence order (env > TOML > Pydantic defaults).

**Schema regeneration.** The JSON Schema at `config/firm-config.schema.json` is a generated artifact, derived from the same Pydantic models the loader validates against. After any change to `src/trust_generator/v3/config/firm.py`, regenerate with:

```bash
pixi run python scripts/generate_firm_config_schema.py
```

The pytest suite includes a freshness test (`test_on_disk_schema_matches_generator_byte_equal`) that fails if the checked-in schema drifts from the generator output. If it fails, regenerate and re-commit.
