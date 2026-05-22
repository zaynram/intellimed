# TGv3 Parser Migration Design

| Field             | Value                                                                                                                                                                                              |
| ----------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Spec date         | 2026-04-23                                                                                                                                                                                         |
| Status            | Final (post-review-iteration-2)                                                                                                                                                                    |
| Supersedes        | n/a (new module under v3; reference-only legacy parsers remain at `src/trust_generator/v2/parsers/`)                                                                                               |
| Relevant entities | `bounded_context_design`, `person_reference_hierarchy`, `address_model`, `added_models`, `modified_surfaces`, `party_naming`, `relationship_enum_design`, `python_stack_commitments`, `ocr_extraction_design`, `diagnostics_design`, `firm_config_loader` |
| Out of scope      | Generator adaptation (separate session); new parser sources beyond v2.2's three (docx / pdf / json); schema modifications (recorded forward as graph-edit proposals, implementation deferred); GUI parsing surfaces; v3 questionnaire DOCX template authoring (separate session: "word template and parser"); fillable PDF form generator authoring (separate session: "pdf completion") |

## 1. Motivation

The v3 schema has landed: `TrustData`, `QuestionnaireSeed`, `promote_seed`, the `Diagnostic` model, `FirmConfig`, the diagnostics engine, and the OCR extraction surface. What is still missing is the bridge from intake artifact (a Word questionnaire, a fillable PDF, or a JSON dump) to the canonical post-fill `TrustData`. That bridge is the parser layer.

The legacy v2 parsers cannot be lifted-and-shifted. Two structural shifts make this a migration rather than a port. First, the v2 schema is predominantly stringly-typed (`str = ""` defaults across PersonInfo, RealProperty, FinancialAccount, BeneficiaryShare, WithdrawalStep, TextBlocks); the v3 schema is heavily typed (`date | None`, `Decimal`, `Address`, `PersonReference`, structured enums, the reference-or-external invariant on distribution recipients). Every v2 string-bearing field that maps to a v3 typed field is a coercion site. Second, the v2 parsers construct `TrustData` from scratch; the v3 parsers must fill into a `TrustData` that was already initialized by `promote_seed(seed)` at consultation time. The post-promotion contract from the `promote_seed` spec (§6.2.3 of `2026-04-22-promote-seed-design.md`) governs how parsers may mutate that `TrustData` without breaching the bounded-context translation invariant.

This spec defines the v3 parser layer's public surface, the per-parser coercion patterns, the post-promotion merge protocol, the regression test corpus strategy, and the structure of the migration notes that downstream sessions will write as they exercise the parsers against real intake artifacts.

## 2. Scope

### In scope

- Module layout under `src/trust_generator/v3/parsers/` (new package).
- Public API: `parse_docx`, `parse_pdf`, `parse_json`, `parse_file` registry dispatch.
- Per-parser coercion patterns: date, Decimal, Address, PersonReference, enum, reference-or-external, WithdrawalStep, plus three resolution-class patterns (new-v3-models with no v2 source, CorporateTrustee discrimination, disinheritance resolution).
- AcroForm field-presence semantics for the PDF parser.
- Post-promotion merge protocol: how parsers fill into a seed-initialized `TrustData` without violating the one-shot-initializer invariant, including the joint-mutation ordering rule for `trust_type` and `marital_status`.
- Error policy: hard-fail surface (Pydantic `ValidationError`, `FileNotFoundError`) vs soft-fail surface (logging warnings).
- Regression test corpus strategy: fixture organization, parametrization, what's gated by optional dependencies (pypdf / reportlab / docx).
- Migration notes structure: template that downstream sessions exercising the parsers fill in as they encounter v2-shape artifacts in production.
- TDD implementation cycles, ordered red → green → refactor.

### Out of scope (enforced)

- **Generator adaptation.** Document, printable-questionnaire, and fillable-PDF generators are downstream sessions. This spec specifies what TrustData parsers produce; what generators do with it is not this session's concern.
- **New parser sources.** v3 ships with the same three parser sources v2.2 had: `.docx`, `.pdf`, `.json`. Adding image parsers, scanned-PDF parsers, or web-form parsers is outside scope. The OCR extraction surface (`OllamaBackend`) is a separate parser variant already specified by `ocr_extraction_design` and lives at `src/trust_generator/v3/extraction/`; this spec does not touch it.
- **Schema modifications.** No changes to `TrustData`, `QuestionnaireSeed`, or any sub-model. Where parsers encounter intake content that would benefit from a schema-side accommodation, the accommodation is captured as a graph-edit proposal and deferred to a future schema-modification session.
- **GUI parsing surfaces.** A GUI workflow that lets a paralegal trigger parsing, view diagnostics, and accept/reject parsed values is the GUI session's concern. This spec defines the parser API; the GUI session wires the call.
- **v3 questionnaire DOCX template.** The v2.2 questionnaire DOCX in `assets/Trust_Intake_Questionnaire.docx` will be redesigned in a separate "word template and parser" session. The docx parser specified here targets the v2.2 layout (tables + checkboxes + text blocks) for the existing intake artifact; when the v3 questionnaire DOCX lands, the docx parser will be revisited.
- **Fillable PDF form authoring.** The PDF generator that emits the form structure the PDF parser reads is a separate "pdf completion" session. The PDF parser specified here targets the v2.2 form-field convention (dotted schema paths in AcroForm field names).
- **Partial-JSON workflows.** `parse_json` accepts only full v3 TrustData JSON documents (the canonical `model_dump_json()` shape). Partial JSON, JSON patches, and hand-edited fragmentary JSON are explicitly out of scope. The relaxation question is logged as §9 Q3.

### Dependencies on prior decisions

- `2026-04-22-promote-seed-design.md` §6.2.3 (parser contract at the promote_seed boundary). This spec implements that contract.
- `2026-04-23-diagnostics-engine-design.md` §5.1 (diagnose entry point). This spec defines what diagnose() consumes (the parsed TrustData).
- `2026-04-21-firm-config-design.md` and the 2026-04-28 shared-firm-config follow-up (FirmConfig surface; `firm_config_loader` infrastructure entity). This spec consumes config defaults (e.g., `jurisdiction.default_state`) when parsers need to fill missing values; the consumption is read-only and goes through the `FirmConfig` Pydantic model, not the loader's internals.
- `2026-04-27-ocr-protocol-ollama-design.md` (OCR extraction surface). This spec coexists with that surface; the two parser families share a uniform contract that they all produce a TrustData fit for downstream `diagnose()`.

## 3. Reference Material

A claude-code session composing the implementation plan from this spec should load the following before writing any code.

### 3.1 Memory entities (open via `memory:open_nodes`)

| Entity                          | Why                                                                                                                                                            |
| ------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `bounded_context_design`        | Seed-vs-TrustData split; one-way translation rule; one-shot-initializer invariant on promote_seed.                                                             |
| `person_reference_hierarchy`    | PersonReference shape, two-token name validator, is_entity discrimination, minor-status computation. The PersonReference-coercion branch consumes this entity. |
| `address_model`                 | Address shape, geocoding policy. The address-coercion branch consumes this entity.                                                                             |
| `added_models`                  | Pet, GuardianshipDesignation, DigitalAssetDirective, CustomTerm. These models were not collected by the v2 questionnaire and have no v2-side coercion source.  |
| `modified_surfaces`             | exclusions removed, custom-text fields collapsed, BeneficiaryShare/SpecificBequest reference-or-external pattern, WithdrawalStep typed, incapacity_provisions added, external_exclusions list. |
| `party_naming`                  | grantor / co_grantor canonical naming; captions as first-class fields. The post-promotion protocol's caption branch consumes this entity.                      |
| `relationship_enum_design`      | Three-tier enum pattern; `value.value` comparison methodology. Parsers populating Child / Descendant / SuccessorTrustee relationships consume this.            |
| `python_stack_commitments`      | Pydantic v2.x; stdlib datetime.date; PEP 695 type alias runtime non-identity.                                                                                  |
| `ocr_extraction_design`         | Confirms parsers are a parser variant of OCR; sets the uniform contract that every parser produces a TrustData fit for downstream diagnose().                  |
| `diagnostics_design`            | Diagnostic model shape; never-stored, always-computed contract. Parsers do not produce Diagnostic instances directly; they leave content the engine fires on.  |
| `firm_config_loader`            | Two-file (shared + local) FirmConfig load semantics. Parsers consume `FirmConfig` defaults (e.g., `jurisdiction.default_state`) read-only; this entity documents the load chain that produces the FirmConfig the parsers may receive. Parsers themselves never invoke `load_firm_config`. |

### 3.2 Source files (read before authoring)

| Path                                                                  | Why                                                                                                                                                              |
| --------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/trust_generator/v3/schema.py`                                    | The v3 schema this layer targets. Includes `_resolve_captions` helper, `promote_seed`, every typed model, every enum.                                            |
| `src/trust_generator/v2/parsers/docx_parser.py`                       | Reference implementation. The table-detection, checkbox-detection, and text-block extraction logic has been hardened over multiple iterations; the v3 docx parser inherits this logic and extends the post-construction step with v3 type coercion. |
| `src/trust_generator/v2/parsers/pdf_parser.py`                        | Reference implementation. AcroForm field-name dotted-path convention is preserved into v3.                                                                       |
| `src/trust_generator/v2/parsers/json_parser.py`                       | Reference implementation. Round-trip is via Pydantic `model_validate_json`; v3 inherits this pattern unchanged because v3 schema has its own validators.         |
| `src/trust_generator/v2/parsers/registry.py`                          | Reference implementation. Extension-based dispatch is preserved into v3.                                                                                         |
| `src/trust_generator/v3/extraction/protocol.py`                       | The parser-variant contract for OCR. The v3 docx/pdf/json parsers' return shape aligns with this contract, deliberately.                                         |
| `src/trust_generator/v3/extraction/trace.py`                          | `ExtractionResult` shape (TrustData + ExtractionTrace). The migrated parsers do NOT produce ExtractionTrace at v3.0 — the trace is OCR-specific. The shape is referenced for design consistency only. |
| `src/trust_generator/v3/diagnostics/engine.py`                        | `diagnose(trust, config, *, ref_date, extraction)` is the consumer of parsed TrustData. Parsers produce TrustData fit for this consumer.                         |
| `src/trust_generator/v3/diagnostics/rules/builtin.yaml`               | The `extraction.placeholder_unfilled` rule fires on `[OCR_LOW_CONFIDENCE]` markers. Migrated parsers may emit similar `[UNPARSEABLE_*]` markers; rule extensions to surface those markers are deferred to a future diagnostics session. |
| `tests/v2/test_parsers.py`                                            | Reference test corpus. The JSON round-trip pattern, the registry-dispatch tests, and the blank-template parsing test are the v3 starting point.                  |
| `tests/v2/test_pdf_parser.py`                                         | Reference test corpus. The PDF-fill-and-reparse pattern is preserved into v3.                                                                                    |
| `assets/Trust_Intake_Questionnaire.docx`                              | The questionnaire artifact the docx parser reads. Currently the v2.2 layout; will be redesigned in the "word template and parser" session.                       |
| `assets/Trust_Intake_Questionnaire.pdf`                               | The fillable PDF the PDF parser reads. Currently the v2.2 layout; will be redesigned in the "pdf completion" session.                                            |
| `assets/Trust_Intake_Questionnaire_data.json`                         | A JSON corpus instance for round-trip testing.                                                                                                                   |
| `docs/superpowers/specs/2026-04-22-promote-seed-design.md`            | §6.2.3 parser contract. This spec implements it.                                                                                                                 |

### 3.3 External references

- `python-docx` library: <https://python-docx.readthedocs.io/> — table iteration, paragraph extraction, cell text retrieval. Already a v2 dependency; no new wrapping needed.
- `pypdf` library: <https://pypdf.readthedocs.io/> — `PdfReader.get_fields()`, `Field.value`. Already a v2 dependency.
- Pydantic v2 docs on field validators: <https://docs.pydantic.dev/latest/concepts/validators/> — used to understand v3 field-validator semantics that parsers indirectly trigger via `model_validate(...)`.

## 4. Bounded-Context Position

The parser layer sits between the file system and `diagnose()`. The flow:

```text
file (.docx/.pdf/.json)            seed-initialized TrustData
        │                                    │
        └────────────► parse_X() ◄───────────┘
                          │
                          ▼
                   filled TrustData
                          │
                          ├──► diagnose(trust, config, ref_date) ──► list[Diagnostic]
                          │
                          └──► generators (downstream session)
```

The seed-initialized `TrustData` is produced by `promote_seed(seed)` at consultation time. Parsers receive both the file and that seed-initialized `TrustData`, fill content into it, and return the filled instance. Three invariants govern this:

| # | Invariant | Source |
|---|-----------|--------|
| P1 | Parsers never re-invoke `promote_seed`. The seed-initialized TrustData is provided by the caller; parsers mutate (an internal copy of) it. | `promote_seed` spec §6.2.3 rule 1. |
| P2 | Parsers update captions and `co_grantor` materialization per the `_resolve_captions` helper when parsing reveals a different `trust_type` or `marital_status` than the seed captured. | `promote_seed` spec §6.2.3 rules 2–3. |
| P3 | Parsers treat `seed_initialized` as immutable. The reference implementation achieves this by deepcopying at parser entry; alternative implementations satisfying the immutability postcondition are conformant. The conformance test is field-level equality of `seed_initialized` before and after the call. | This spec §5.3 step 1; tested via the cycle-4 deepcopy fixture. |

The JSON parser is exempt from these invariants under a narrow scope rule: `parse_json` accepts only **full v3 TrustData JSON documents** (the canonical post-fill representation produced by `model_dump_json()`). It does NOT accept partial JSON, JSON patches, or hand-edited fragmentary JSON. The reasoning: a full v3 dump is itself authoritative end-state, with no merge to perform. Partial-JSON workflows (e.g., a paralegal saving in-progress fill state and resuming) are explicitly out of scope; if such a workflow surfaces, the right response is a new `parse_json_patch` API or a JSON-merge utility at the call site, not relaxing `parse_json`'s contract. The validation gate that distinguishes "full" from "partial" is `TrustData.model_validate(...)` itself: a partial JSON either fails Pydantic validation (because it omits required structure) or it parses with all unspecified fields at schema defaults, which is observationally equivalent to a fresh-default TrustData and indistinguishable from a deliberate full dump. Q3 in §9 logs the future relaxation question.

## 5. Architecture Overview

The parser layer is composed of four units. §6 gives the test-first construction order; this section is the reference shape that all cycles target.

### 5.1 Module layout

```text
src/trust_generator/v3/parsers/
├── __init__.py        # re-exports parse_docx, parse_pdf, parse_json, parse_file
├── registry.py        # parse_file dispatch by extension
├── docx_parser.py     # parse_docx
├── pdf_parser.py      # parse_pdf
├── json_parser.py     # parse_json
└── coercion.py        # shared coercion helpers (date, Decimal, Address, PersonReference)
```

Two organizational decisions inform this layout:

- **Coercion lives in its own module.** The coercion helpers (`_to_date`, `_to_decimal`, `_to_address`, `_to_person_reference`) are shared across docx and pdf parsers and tested independently. Inlining them into one parser would force the other to re-implement or import via a private cross-module path; either is worse than a dedicated module. The JSON parser does not consume coercion helpers because Pydantic's own validators run during `model_validate_json`.
- **No `base.py` parser ABC.** The three parsers do not share a runtime base class. Each is a free function whose signature is dictated by its input format. A common ABC would force per-parser noise (e.g., a docx-only `_parse_table` method on the JSON parser's class) without enabling any polymorphic call site beyond what `parse_file`'s extension dispatch already provides.

### 5.2 Public API

```python
# src/trust_generator/v3/parsers/__init__.py

from pathlib import Path

from trust_generator.v3.schema import TrustData

def parse_docx(filepath: Path, seed_initialized: TrustData) -> TrustData:
    """Parse a Trust Intake Questionnaire .docx INTO a copy of seed_initialized.

    The seed_initialized argument is required (no default) to make the
    post-promotion contract loud at every call site. Postcondition (P3):
    seed_initialized is field-level equal before and after this call.
    The reference implementation achieves this by deepcopying at entry.
    """

def parse_pdf(filepath: Path, seed_initialized: TrustData) -> TrustData:
    """Parse a fillable PDF questionnaire INTO a copy of seed_initialized.

    Same semantics as parse_docx. Field names use dotted schema paths
    (e.g., 'grantor.full_legal_name') matching the v3 schema layout.
    """

def parse_json(filepath: Path) -> TrustData:
    """Parse a full v3 TrustData JSON dump; return a fresh validated instance.

    Accepts only canonical full v3 documents (the model_dump_json() shape).
    Partial JSON, JSON patches, and hand-edited fragmentary JSON are out
    of scope (§4, §9 Q3). Callers reconciling a JSON parse against an
    in-progress seed do so explicitly at the call site.
    """

def parse_file(
    filepath: Path,
    seed_initialized: TrustData | None = None,
) -> TrustData:
    """Dispatch by extension. Required arg shape varies by extension.

    Calls parse_json for .json (seed_initialized is ignored if provided);
    calls parse_docx or parse_pdf for .docx and .pdf respectively
    (seed_initialized is required and a ValueError is raised if absent).
    """
```

Three commitments codified by these signatures:

- **Required `seed_initialized` for docx/pdf.** The argument is positional and required (no default) so call sites cannot accidentally bypass the post-promotion protocol. The JSON parser's API is asymmetric for the reason stated in §4.
- **Return value is the parsed TrustData.** No tuple, no `ParseResult` wrapper, no paired ExtractionTrace. The trace is OCR-specific (illegibility, confidence, verification); a docx/pdf/json parser produces no trace data of meaningful structure. Adding a vestigial trace to satisfy the OCR contract would be ceremonial; OCR's `extract()` returning `ExtractionResult` is the right shape for that variant, and the docx/pdf/json variants returning `TrustData` is the right shape for theirs. `diagnose()` accepts an optional `extraction` kwarg (`extraction: ExtractionTrace | None = None`); callers of the migrated parsers simply do not pass that kwarg.
- **`parse_file` accepts `seed_initialized` as Optional.** This keeps the dispatch site uniform for callers that don't know in advance which extension they're handing in. The docstring documents the dispatch-site rule: required for docx/pdf, ignored for json. The "ignored for json" rule is testable via the cycle-8 contract test `test_parse_file_ignores_seed_for_json`, which asserts that dispatching `.json` with a non-None `seed_initialized` produces output equal to dispatching with `seed_initialized=None`.

### 5.3 Post-promotion merge protocol

`parse_docx` and `parse_pdf` implement the following sequence inside their bodies:

1. **Deepcopy seed_initialized.** `result = seed_initialized.model_copy(deep=True)`. This is the implementation that satisfies invariant P3 in §4; alternative implementations are conformant if and only if they preserve field-level equality of `seed_initialized` before and after the call. The cycle-4a test fixture asserts this equality.
2. **Extract content from the file.** Format-specific (table walk for docx, AcroForm field iteration for pdf). For pdf, the field-presence normalization in §5.4.A runs at this step. Produces a flat key-value map plus list-structured data.
3. **Coerce values to v3 types.** Applied per the per-field coercion patterns in §5.4.
4. **Detect and apply trust_type / marital_status mutations transactionally.** Compare the parsed values against `result.trust_id.trust_type` and `result.trust_id.marital_status`. The two fields are mutated jointly to avoid invalid intermediate states (e.g., `(JT, UM)` momentarily while one field has changed and the other has not). The protocol:
   - **None / absent gate:** if a parsed value is `None` (the natural §5.4.A normalization outcome for an absent or empty PDF field, or the docx parser's coercion-failure outcome), treat it as "no mutation requested" for that field. The seed-initialized value persists; the comparison-and-assign step below is skipped for that field. This rule is load-bearing: `trust_type` is a required schema field and assigning `None` would breach Pydantic validation.
   - **Single ordering rule:** apply `trust_type` mutation first, then `marital_status` mutation. Captions depend only on `trust_type`, so capture the new captions first; co_grantor materialization depends on the post-mutation value of both, so apply it last.
   - **On `trust_type` change:** call `_resolve_captions(new_trust_type)` and assign both `result.trust_id.grantor_caption` and `result.trust_id.co_grantor_caption`.
   - **On `marital_status` change OR `trust_type` change (computed once after both have been assigned):** evaluate the `co_grantor` materialization rule. If the post-mutation state is one where `co_grantor` should exist (`trust_type == JOINT` OR `marital_status == MARRIED`) and `result.co_grantor is None`, materialize it as `GrantorInfo()`. If `co_grantor` is already populated, preserve it (the populated data is meaningful; the mutation decided the grantor exists, not what their identity is).
   - **Dematerialization branch:** if the post-mutation state is one where `co_grantor` should NOT exist (`trust_type != JOINT` AND `marital_status != MARRIED`) AND `result.co_grantor` is a default-only `GrantorInfo()` (no fields populated beyond schema defaults — check via `result.co_grantor == GrantorInfo()`), dematerialize by setting `result.co_grantor = None`. If `result.co_grantor` is populated (any field differs from schema defaults), preserve it; the populated data is meaningful and dropping it would breach the bounded-context translation invariant.
   - **Combinatorial cycle-5 coverage:** the cycle-5 tests parametrize over four combinations of (seed (trust_type, marital_status), parsed (trust_type, marital_status)): (JT, MR)→(IN, UM); (IN, UM)→(JT, MR); (JT, MR)→(IN, MR); (IN, MR)→(JT, MR). The first asserts the joint mutation; the second asserts re-materialization; the third asserts caption-only mutation with co_grantor preservation; the fourth asserts caption mutation with co_grantor preservation across a marital-equivalent transition.
5. **Apply remaining mutations.** Fill all other fields onto `result` (PersonReferences, Address, Lists, Elections, TextBlocks, etc.) per §5.4 coercion patterns.
6. **Apply post-merge resolution passes.** Two passes run after step 5 because they require the full TrustData state, not just per-row fragments:
   - **Beneficiary disinherit resolution** (per §5.4.10): the v2 exclusions free-text — captured during step 2 extraction as a parser-internal string variable, NOT a v3 schema field — is name-matched against the populated `children` / `descendants` / `other_beneficiaries` lists; matched entries get `disinherit=True` with `disinherit_reason` set to the matching exclusion text fragment. Unmatched exclusion strings flow into `external_exclusions` as `PersonReference(full_legal_name=string)` entries, with `external_exclusion_reasons[string] = string`. The exclusions string is threaded as a function-local argument into the post-merge resolution call; it does not transit through `result` (v3's TrustData has no `text_blocks.exclusions` field per `modified_surfaces`).
   - **CorporateTrustee discrimination** (per §5.4.9): trustee entries flagged for entity discrimination in step 5 are re-constructed as `CorporateTrustee` instances rather than `SuccessorTrustee`.
7. **Return `result`.** Pydantic validation runs as fields are assigned (because `model_config` on relevant sub-models has `validate_assignment` semantics or because re-construction of nested models triggers validators).

The flat key-value extraction (step 2) borrows wholesale from the v2 docx parser. The novelty is in step 3 (coercion), step 4 (post-promotion contract enforcement), and step 6 (post-merge resolution).

**Implementation note (helper structure).** Step 4 lives in `_apply_post_promotion_protocol(result, parsed_trust_type, parsed_marital_status)` (extracted in cycle 4b's refactor). Step 6 lives in a separate `_apply_post_merge_resolution(result, exclusions_string, trustee_entity_flags)` helper. The split is clean because step 4 is per-field and atomic, while step 6 is full-state and ordered. Keeping them in one helper would conflate two concerns and violate the cycle-5 vs. cycle-6 test boundary.

### 5.4 Per-Parser Coercion Patterns

Coercion patterns are organized by target type. Each pattern lists its inputs (across the three parser sources where applicable), the coercion mechanism, and the failure-handling policy.

#### 5.4.1 Date coercion (`coercion._to_date`)

| Source | Input shape | Behavior |
|--------|-------------|----------|
| docx | Cell text from a "Date of Birth" / "Date of Marriage" / etc. row. Common formats: `MM/DD/YYYY`, `M/D/YYYY`, ISO `YYYY-MM-DD`. Also seen: `Sep 17, 1980`, `September 17, 1980`. | Try ISO first (`date.fromisoformat`), then `MM/DD/YYYY` (`datetime.strptime`), then a small allowlist of long-form patterns (`%B %d, %Y`, `%b %d, %Y`). On all-fail: return `None`, emit `log.warning("could not parse date %r at %s", text, source_label)`. |
| pdf  | AcroForm field value (always a string after §5.4.A normalization). | Same coercion chain as docx. |
| json | n/a (Pydantic's `date` field validator handles ISO `YYYY-MM-DD` natively). | n/a. |

The coercion function returns `date | None`. No exception escapes; the warning is the soft-fail surface. Pydantic's date validator is **not** relied on because the parser's coercion failure path leaves the field as `None` rather than raising — Pydantic's behavior on a malformed string is to raise a `ValidationError`, which would abort the whole parse.

#### 5.4.2 Decimal coercion (`coercion._to_decimal`)

| Source | Input shape | Behavior |
|--------|-------------|----------|
| docx | Cell text for asset values, equity, percentages. Common formats: `$500,000`, `500,000`, `$500000.50`, `500000`, `50%`, `50.5%`. | Strip leading `$`, strip thousands `,`, strip trailing `%`. Strip whitespace. Try `Decimal(stripped)`. On `InvalidOperation`: return `Decimal(0)`, emit logging warning. |
| pdf  | AcroForm field value (always a string after §5.4.A normalization). | Same chain as docx. |
| json | n/a. | n/a. |

The coercion function returns `Decimal`. Failed coercions yield `Decimal(0)`, never raise. The `Decimal(0)` default matches the schema-side default for value/equity/benefit fields.

The diagnostic-layer indistinguishability claim (that `Decimal(0)` is observationally equivalent to a missing value) is **bounded**: it holds for asset-value fields where `Decimal(0)` is naturally interpreted as "missing/uncollected" (a real-property entry with `value=0` is functionally a missing value for tax-planning purposes); it does **not** hold for share-percent fields like `BeneficiaryShare.share_percent` where `Decimal(0)` is a meaningful declared allocation distinct from "unspecified." For share-percent fields specifically, a coercion failure logs the warning AND drops the row entirely (the same rule as WithdrawalStep age failures in §5.4.7), preserving the meaningfulness of `Decimal(0)` in surviving rows. The list of fields where `Decimal(0)` is meaningful-rather-than-default is enumerated in cycle-3 test cases as a regression guard.

#### 5.4.3 Address coercion (`coercion._to_address`)

| Source | Input shape | Behavior |
|--------|-------------|----------|
| docx | Single cell containing free-text address: `"123 Main St, Springfield, IL 62701"`, `"123 Main St, Springfield, IL 62701, US"`. | Best-effort split on commas. Heuristics: 3 parts → (street, city, state+zip); 4 parts → (street, city, state+zip, country); each "state+zip" element is further split on the last whitespace to separate state from zip. On unparseable input (zero or one comma): populate `street` with the full string, leave other Address fields empty, emit logging warning. |
| pdf  | Either a single field (`'<prefix>.address'` containing free text) or a structured set of fields (`'<prefix>.address.street'`, `.city`, `.state`, `.zip_code`). | Prefer structured fields when present. Fall back to free-text coercion when only the single-field form is present. |
| json | n/a (the Address Pydantic model handles structured input directly). | n/a. |

The coercion function returns `Address`. `latitude` and `longitude` are never populated by the parser; the geocoder is invoked separately by the GUI / generators when needed.

#### 5.4.4 PersonReference coercion (`coercion._to_person_reference`)

| Source | Input shape | Behavior |
|--------|-------------|----------|
| docx | Single cell containing a name string. v2 corpus: `"John Andrew Doe"`, `"ABC Corporation"`, occasional empty cells, occasional placeholder-prefixed cells like `"[Spouse's full legal name] Jane Doe"`. | Apply placeholder-prefix stripping first (regex `\[[^\]]+\]\s*` removed from start of cell text); then construct `PersonReference(full_legal_name=name)`. The two-token validator on `full_legal_name` raises `ValidationError` on one-token names; the parser traps this and re-constructs as `PersonReference(is_entity=True, entity_name=name, full_legal_name="")`. |
| pdf  | Either a single field (`'<prefix>.full_legal_name'`) or a structured set (`.full_legal_name`, `.entity_name`, `.is_entity`). | Prefer structured fields when present; fall back to single-field coercion. |
| json | n/a (PersonReference's own validator runs during `model_validate`). | n/a. |

The trap-and-reconstruct pattern preserves data: a one-token name (e.g., `"AcmeCorp"`, `"Corporation"`, or a single surname entered without a first name) becomes a valid `PersonReference` with `is_entity=True`, rather than a hard parse failure. Multi-token entity names like `"ABC Corporation"` or `"First National Bank"` pass the two-token validator cleanly and reach `_apply_post_merge_resolution`, where §5.4.9's CorporateTrustee suffix heuristic discriminates them — `_to_person_reference` deliberately does NOT carry a suffix detector, keeping the layered design intact. The placeholder-prefix-stripping rule handles the v2-corpus pattern where users typed beside (rather than instead of) bracketed hint text; this is a coercion concern (one input → one PersonReference) rather than a hint-cell concern (handled separately by the v2 parser's `_HINTS` table). A future docx-template revision (the "word template and parser" session) may add an explicit "entity?" checkbox per row, at which point the parser reads the checkbox and skips the trap; until then, the trap is the safe default.

#### 5.4.5 Enum coercion

| Source | Input shape | Behavior |
|--------|-------------|----------|
| docx | Checkboxes mapped to (election_field, enum_value) per `_CHECKBOX_MAP` dict. | Direct lookup. The v2 implementation works as-is for v3 enum types via `_ELECTION_ENUM[field](value)`; v3 adds two new election fields (`guardianship_policy`, `digital_assets_handling`) whose values come from new checkbox phrases. The mapping table extension is mechanical and lives in the docx parser's module-level dict. |
| pdf  | AcroForm field name encodes the field; field value is the enum `.value` string. | `Enum(value)` constructor with try/except: unknown values emit a logging warning and the field falls through to its schema-side default. |
| json | n/a (Pydantic enum validators handle this). | n/a. |

#### 5.4.6 Reference-or-external coercion (BeneficiaryShare, SpecificBequest)

The v3 schema requires either `recipient_ref` or `recipient_external` populated; both populated raises a `model_validator` error. v2 input has only a `name` string per row.

| Source | Input shape | Behavior |
|--------|-------------|----------|
| docx | A name + share row in the beneficiary-shares table. | Construct `BeneficiaryShare(recipient_external=PersonReference(full_legal_name=name), share_percent=Decimal(share))`. Always external; never ref. |
| pdf  | Same shape as docx. | Same coercion. |
| json | n/a. | n/a. |

The "always external" rule is provisional. A future GUI session that lets the paralegal point at an existing person in `children` / `descendants` / `other_beneficiaries` will refactor parsing flows to assign `recipient_ref`; the parser-side coercion will then become "external by default; ref when the GUI has supplied an id." Until that refactor lands, the always-external rule is correct: there is no id surface in v2 intake.

#### 5.4.7 WithdrawalStep coercion

The v3 schema types `WithdrawalStep` as `(age: int, percent: Decimal, description: str)`. The v2 schema typed it as three strings (`step`, `timing`, `percentage`). The v2 questionnaire collects free text like "upon college graduation" / "1 year after funding" alongside numeric ages.

| Source | Input shape | Behavior |
|--------|-------------|----------|
| docx | Three-cell rows: step / timing / percentage. | Parse `timing` as an int age via regex `r'\d+'` → first integer match. Parse `percentage` via `_to_decimal`. Use the original `step` text as `description`. On age-parse failure: skip the row entirely and emit a logging warning naming the unparsed `timing` value. |
| pdf  | Numbered fields: `withdrawal[i].age`, `withdrawal[i].percent`, `withdrawal[i].description`. | Direct construction via `_to_decimal` for percent and `int(value)` for age. |
| json | n/a. | n/a. |

The "skip the row" rule on age-parse failure is conservative: the v3 schema's `age: int` (no default, required) cannot accept `None`, so a row with unparseable timing has no place in the schema. A future schema-modification session may relax this constraint (`age: int | None = None` with a parallel `age_description: str = ""` for non-numeric timing); until then, the parser drops the row.

#### 5.4.8 New v3 models with no v2 source

Four v3 models have no v2 questionnaire source: `Pet`, `GuardianshipDesignation`, `DigitalAssetDirective`, and `CustomTerm`. Plus `external_exclusion_reasons: dict[str, str]` on `TrustData`.

| Target | Parser behavior |
|--------|-----------------|
| `pets: list[Pet]` | Empty list (`[]`) on output. Population is a v3-questionnaire-redesign concern (the "word template and parser" session). |
| `guardianship_designations: list[GuardianshipDesignation]` | Empty list. Population is a v3-questionnaire concern; the v2 questionnaire's checkbox phrasings around guardianship are mapped only into `Elections.guardianship_policy`, not into structured designations. |
| `digital_asset_directives: list[DigitalAssetDirective]` | Empty list. Same rationale. |
| `custom_terms: list[CustomTerm]` | Built from the three v2 free-text fields (`custom_distribution_terms`, `custom_beneficiary_terms`, `additional_notes`), each becoming one `CustomTerm` instance with `category` derived from the source field name (`DISTRIBUTION`, `BENEFICIARY`, `OTHER` respectively) and `manual_review=True`. Empty source strings yield no CustomTerm entry. |
| `external_exclusions: list[PersonReference]` | Built from the post-merge resolution pass in §5.4.10 (unmatched tokens from the v2 exclusions string, which the parser captures during step 2 extraction as a parser-internal carrier — there is no v3 schema field for it). |
| `external_exclusion_reasons: dict[str, str]` | Built from the post-merge resolution pass in §5.4.10 (keyed by `PersonReference.full_legal_name`, value is the matching exclusion text fragment). |

The pattern is uniform: where v2 has no analogous content, the parser emits the empty default; where v2 has analogous content under a different shape, the parser performs the coercion with explicit rules above.

#### 5.4.9 CorporateTrustee discrimination

The v3 schema has `successor_trustees: list[SuccessorTrustee | CorporateTrustee]`. v2 had a single `SuccessorTrustee` shape. The v2 questionnaire's trustee table accepts entity names (e.g., "First National Bank Trust Department") in the same column as natural-person names. The parser must discriminate.

**Heuristic:** name matches one of the patterns `\b(Bank|Trust Company|Trust Department|N\.A\.|LLC|LLP|Corporation|Corp\.|Inc\.|Insurance Co)\b` (case-insensitive). Match → `CorporateTrustee(is_entity=True, full_legal_name="", entity_name=name)`. No match → `SuccessorTrustee(full_legal_name=name)` (and the §5.4.4 trap-and-reconstruct fires for one-token edge cases).

The heuristic is intentionally conservative — it matches obvious entity-bearing tokens without trying to cover every legal-entity nomenclature. A future docx-template revision may add an explicit "entity?" checkbox per row that supersedes this heuristic. Until then, the parser logs an INFO-level message naming each entry it discriminated as `CorporateTrustee`, so the paralegal can review.

**Known limitation:** a natural person with a surname like "Bank" (e.g., "John Bank") is mis-typed by this heuristic and loses their `full_legal_name` in re-construction. The INFO log is the operator-side recovery surface — the paralegal who reviews the log sees the discriminated entry and can manually correct it post-parse. The structural fix is the v3-questionnaire "entity?" checkbox (Q4 in §9). Listing the surname as a known limitation here pins the scenario as expected-and-mitigated, not a defect.

#### 5.4.10 Disinheritance resolution (post-merge)

The v2 schema has a `text_blocks.exclusions: str` field (free-text list of names). The v3 schema replaces this with `Beneficiary.disinherit: bool` per beneficiary, plus `external_exclusions: list[PersonReference]` for names that don't match any beneficiary.

This is **not** a per-row coercion — it requires the fully-populated `children` / `descendants` / `other_beneficiaries` lists. The resolution runs as step 6 of the post-promotion merge protocol (§5.3), after step 5 has populated all beneficiary lists.

**Algorithm:**

1. Tokenize the v2 exclusions string on commas, semicolons, and newlines. Each token is a candidate excluded-name (whitespace-stripped). The exclusions string is a parser-internal carrier captured during step 2 extraction; it is not stored on `result` (v3's TrustData has no `text_blocks.exclusions` field per `modified_surfaces`).
2. For each token, attempt name-match against the beneficiary lists in **fixed iteration order**: `children` first, then `descendants`, then `other_beneficiaries`. Within each list, Pydantic insertion order applies. Match rule: case-insensitive substring match of `token` against `beneficiary.full_legal_name`. The first match across this fixed sequence wins. If any later element in the sequence also matches the same token, log a WARNING naming both candidates but do not change the chosen target — the iteration-order-first beneficiary is the deterministic outcome.
3. On match: set the matched beneficiary's `disinherit=True` and `disinherit_reason=token`.
4. On no match: append `PersonReference(full_legal_name=token)` to `external_exclusions`, and `external_exclusion_reasons[token] = token` (the dict's current shape just keys the name to itself — a future GUI session may add per-name reasons).

**Rationale for placement:** the resolution requires the fully-populated beneficiary lists, which step 5 produces. Placing the resolution at row-construction time would require name-matching across rows the parser hasn't yet populated. Placing it at the call site would force every caller to know about the v2→v3 transform; encapsulating it inside the parser keeps the call site simple.

#### 5.4.A AcroForm field-presence semantics (PDF parser)

`pypdf`'s `PdfReader.get_fields()` returns a `dict[str, Field]` for AcroForm fields present in the document. Three field-presence states must be distinguished by the PDF parser:

1. **Field absent** — key not in the returned dict. Parser treats as `None` at coercion entry. Fields not present in the source PDF cannot be assumed to have any value, including the empty string.
2. **Field present, value None** — key in dict, `Field.value is None`. Parser treats as `None` at coercion entry (same as absent).
3. **Field present, value empty string** — key in dict, `Field.value == ""`. Parser treats as `None` at coercion entry (whitespace-only strings are normalized to `None` after `.strip()`).

All three normalize to `None` because, for the current v2.2 fillable-PDF generator, they are observationally equivalent in operator intent. If the v3 fillable-PDF generator (the "pdf completion" session) introduces structured semantics where empty-string is meaningful (e.g., "explicitly cleared by the operator"), the normalization rule above is revisited at that point.

The normalization happens in `pdf_parser._normalize_field_values(fields_dict)`, a parser-internal helper. After normalization, all coercion helpers (`_to_date`, `_to_decimal`, etc.) receive either `None` or a non-empty stripped string.

### 5.5 Error policy

The parser layer has two error tiers:

**Hard fail (exception raised, parse aborts).**

- `FileNotFoundError`: input file does not exist.
- `Pydantic ValidationError` (wrapped as `ValueError`): JSON does not match the TrustData schema (parse_json only). The wrap matches v2's `ValueError("JSON validation failed for ...")` convention so existing CLI callers get the same exception class.
- `OSError` from the underlying `python-docx` / `pypdf` library: file is locked, malformed, or corrupted at a level the library cannot recover from.

**Soft fail (logging warning emitted, field falls back to default or empty value).**

- Date parse failure → `None`.
- Decimal parse failure on an asset-value field → `Decimal(0)`.
- Decimal parse failure on a share-percent field → row dropped (per §5.4.2).
- Address split failure → `street` populated with full text, other fields empty.
- PersonReference one-token name → re-constructed as entity reference.
- Enum unknown value → schema default.
- WithdrawalStep age-parse failure → row dropped.
- Disinheritance resolution multi-match → first match wins; WARNING logged.
- CorporateTrustee discrimination → INFO logged per discriminated entry.

Soft fails are surfaced via `log.warning(...)` calls. The diagnostic engine is **not** invoked from inside the parser. A downstream caller running `diagnose()` against the parsed TrustData will receive any rule-driven diagnostics that fire on the resulting state (e.g., `shares.sum_not_100` if a row was dropped); the parser's own warnings live in the application log and are surfaced by the future GUI's "parse log" panel.

This is a deliberate split: parser warnings describe what the parser did, diagnostics describe what the resulting TrustData looks like. Conflating the two would force the parser to import the diagnostics engine and create a dependency cycle (parsers → diagnostics → eval_context → schema; schema is shared). The split is consistent with v2's pattern (`log.warning`-only) and with the OCR backend's pattern (diagnostics produced by `synthesize_extraction_diagnostics`, not by the backend).

#### 5.5.1 Placeholder markers (deferred)

A possible future extension: when a coercion fails for a free-text field that has high downstream salience (e.g., `text_blocks.statement_of_intent`), the parser could emit a placeholder marker like `[UNPARSEABLE_DATE]` or `[OCR_LOW_CONFIDENCE]` into the field. The diagnostic rule `extraction.placeholder_unfilled` (already shipping in `builtin.yaml`) fires on the OCR marker, and a parallel rule could be added for the parser markers.

This is **deferred**: v3.0 parsers do not emit placeholder markers. The reasons are that the soft-fail surface (logging) is sufficient for v3.0's call sites (CLI + future GUI), and adding markers without the corresponding GUI surfacing would create unhandled noise. When the GUI's "parse log" panel lands, the placeholder-marker pathway is the natural next step. Logged as §9 Q1.

### 5.6 Dependency injection and the JSON parser asymmetry

`parse_json` does not take a `seed_initialized` argument. The asymmetry is principled:

- A docx or pdf intake artifact captures a *partial* state of the trust — fields filled by the client, sections left blank, sections in placeholder form. The parser's job is to transcribe that partial state into a TrustData that may have many gaps.
- A JSON dump of TrustData is *complete* state — every field has a value (defaulted or filled). It's the canonical post-fill representation.

The seed-initialized TrustData carries pre-fill defaults that the docx/pdf parsers must avoid clobbering for fields the artifact does not address. A JSON parse has no such concern: every field in the JSON is authoritative.

If a workflow needs to reconcile a JSON parse against an in-progress seed (for example, a paralegal saved the in-progress fill as JSON and wants to resume), the reconciliation belongs at the call site — the workflow knows whether to overwrite, merge, or treat the JSON as a fresh start. Pushing reconciliation into the parser would force the parser to embed workflow policy. The narrow scope rule (full v3 documents only) is stated in §4 and reinforced by Q3 in §9.

## 6. TDD Implementation Cycles

Cycles are stated test-first. Each cycle has a Red phase (write failing test), a Green phase (minimum change to pass), and an optional Refactor phase (only when `refactor_threshold` is met; explicitly noted otherwise per the hybrid_methodology rule).

### 6.1 Cycle 0 — Precondition check

1. Run the full test suite at session start.
2. Expected: **green**. If red, a latent failure predates this session; stop and resolve before proceeding.

No code change at this step. The cycle exists to make the starting state explicit.

### 6.2 Cycle 1 — JSON round-trip

The simplest parser. No coercion (Pydantic handles it), no merge (JSON is authoritative).

**Red:**

```python
# tests/v3/parsers/test_json_parser.py

def test_json_round_trip(tmp_path):
    """A TrustData dumped to JSON parses back to an equal TrustData."""
    from trust_generator.v3.parsers import parse_json
    from trust_generator.v3.schema import GrantorInfo, TrustData, TrustIdentity, TrustType

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

Runs **red** with `ImportError` (parser module does not exist).

**Green:** Create `src/trust_generator/v3/parsers/__init__.py` and `json_parser.py`. The `parse_json` body mirrors v2: read text, `TrustData.model_validate_json`, return. Wrap `ValidationError` as `ValueError`. Add `FileNotFoundError` check.

**Refactor:** None — green output is already minimal. Two-line body; no structural duplication; no orthogonal concerns. Per `refactor_threshold` rule: explicitly note "no refactor stage — green output is already minimal."

### 6.3 Cycle 2 — JSON parser error surfaces

**Red:** Three tests in one batch:

```python
def test_json_parser_raises_for_missing_file(tmp_path): ...
def test_json_parser_raises_for_invalid_json(tmp_path): ...
def test_json_parser_raises_for_schema_violation(tmp_path):
    """Invalid TrustData JSON (e.g., wrong type for date) raises ValueError."""
```

The third test is novel: v3's typed schema (date / Decimal / enums) creates many more schema-violation paths than v2's mostly-string schema. The test exercises one (a date field with a malformed string) and asserts a `ValueError` whose message preserves the originating Pydantic error.

**Green:** The error-surface tests pass with the cycle-1 implementation already; the test additions are characterization-and-regression-guard, not change-driving. (Per `refactor_threshold`: no refactor stage.)

### 6.4 Cycle 3 — Coercion helpers (pure)

The coercion helpers in `coercion.py` are pure functions over inputs to outputs. Tests are pure assertion of input → output.

**Red:** A parametrized test file `tests/v3/parsers/test_coercion.py` covering all six coercion functions with positive and negative cases. ~30 parametrized cases total.

```python
import pytest
from datetime import date
from decimal import Decimal
from trust_generator.v3.parsers.coercion import (
    _to_address, _to_date, _to_decimal, _to_person_reference,
)

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
    ],
)
def test_to_date(text, expected):
    assert _to_date(text) == expected

# ... analogous batches for _to_decimal, _to_address, _to_person_reference,
# plus the share-percent-drops-row regression guard for §5.4.2,
# plus the placeholder-prefix-stripping regression guard for §5.4.4.
```

**Green:** Implement each helper. Each is small enough to fit in 10–20 lines.

**Refactor target:** the three "long-form" date patterns (`%B %d, %Y`, `%b %d, %Y`, ...) are a candidate for a module-level `_DATE_FORMATS` tuple iterated in `_to_date`. Apply when the green-phase code has a visible loop body containing the literal patterns; this satisfies `refactor_threshold`'s "structural duplication" criterion.

### 6.5 Cycle 4a — docx parser smoke test (no asset dependency)

This cycle isolates "parser exists and loads python-docx" from "parser handles the v2.2 questionnaire format."

**Red:**

```python
def test_parse_docx_smoke(tmp_path):
    """parse_docx exists, opens a minimal valid .docx, and returns a TrustData."""
    from docx import Document
    from trust_generator.v3.parsers import parse_docx
    from trust_generator.v3.schema import (
        MaritalStatus, QuestionnaireSeed, TrustType, promote_seed,
    )

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
    # P3 invariant: seed_initialized untouched.
    assert seed_initialized == seed_snapshot
    # Deepcopy proof: returned TrustData is a separate instance.
    assert result is not seed_initialized
```

Runs **red** with `ImportError`. The smoke-test red signal is unambiguous: only "parser absent" can produce it (the synthetic minimal.docx has no v2.2-shape dependencies).

**Green:** Create `docx_parser.py` with a body that opens the doc, walks paragraphs/tables, and returns a deepcopy of `seed_initialized` (no content extracted yet). The smoke test passes.

**Refactor:** None.

### 6.6 Cycle 4b — docx parser asset integration (asset-dependent)

The docx parser's full happy path against `assets/Trust_Intake_Questionnaire.docx`. This cycle fails for asset-dependent reasons distinguishable from cycle 4a's parser-absent reason.

**Red:**

```python
@pytest.mark.skipif(
    not QUESTIONNAIRE_PATH.exists(),
    reason="Trust_Intake_Questionnaire.docx not found in assets/",
)
def test_parse_docx_blank_template_into_seed_initialized():
    """Parsing a blank template into a JT+MR seed produces a TrustData
    with the seed's defaults preserved and minimal new content extracted."""
    seed = QuestionnaireSeed(
        trust_type=TrustType.JOINT,
        marital_status=MaritalStatus.MARRIED,
    )
    seed_initialized = promote_seed(seed)
    result = parse_docx(QUESTIONNAIRE_PATH, seed_initialized)

    assert result.trust_id.trust_type == TrustType.JOINT
    assert result.trust_id.grantor_caption == "Grantor A"
    assert result.trust_id.co_grantor_caption == "Grantor B"
    assert result.co_grantor is not None
```

**Green:** Port the v2 docx parser body. Adapt the flat-key → TrustData mapping to fill `result` (the deepcopy from 4a) instead of constructing fresh. Use v3 model names (`grantor` / `co_grantor` instead of `husband` / `wife`).

**Refactor:** Extract `_apply_post_promotion_protocol(result, parsed_trust_type, parsed_marital_status)` helper. The green-phase code mixes "parse content" with "honor the protocol"; the helper extraction satisfies the `refactor_threshold` "mixes orthogonal concerns" criterion. The helper is also a natural test target for cycle 5.

### 6.7 Cycle 5 — docx parser post-promotion contract

This is the cycle that codifies the §6.2.3 invariants. The parametrization covers the four (seed, parsed) combinations from §5.3 step 4's "combinatorial cycle-5 coverage" rule.

**Red:**

```python
@pytest.mark.parametrize(
    ("seed_state", "parsed_state",
     "expected_grantor_caption", "expected_co_grantor_caption",
     "expected_co_grantor_present"),
    [
        # (JT, MR) -> (IN, UM): joint mutation — both fields change
        ((TrustType.JOINT, MaritalStatus.MARRIED),
         (TrustType.INDIVIDUAL, MaritalStatus.UNMARRIED),
         "Grantor", "Spouse", False),
        # (IN, UM) -> (JT, MR): re-materialization
        ((TrustType.INDIVIDUAL, MaritalStatus.UNMARRIED),
         (TrustType.JOINT, MaritalStatus.MARRIED),
         "Grantor A", "Grantor B", True),
        # (JT, MR) -> (IN, MR): caption-only mutation; co_grantor preserved
        ((TrustType.JOINT, MaritalStatus.MARRIED),
         (TrustType.INDIVIDUAL, MaritalStatus.MARRIED),
         "Grantor", "Spouse", True),
        # (IN, MR) -> (JT, MR): caption mutation; co_grantor preserved
        ((TrustType.INDIVIDUAL, MaritalStatus.MARRIED),
         (TrustType.JOINT, MaritalStatus.MARRIED),
         "Grantor A", "Grantor B", True),
    ],
    ids=["jt_mr_to_in_um", "in_um_to_jt_mr", "jt_mr_to_in_mr", "in_mr_to_jt_mr"],
)
def test_post_promotion_protocol_combinatorial(
    seed_state, parsed_state,
    expected_grantor_caption, expected_co_grantor_caption,
    expected_co_grantor_present,
    tmp_path,
):
    """All four (seed, parsed) trust_type/marital_status combinations apply
    correctly per §5.3 step 4."""
    ...

def test_parser_preserves_populated_co_grantor_on_marital_transition():
    """Already-populated co_grantor survives marital_status change."""
    ...

def test_parser_never_reinvokes_promote_seed():
    """parse_docx does not call promote_seed under any branch."""
    from unittest.mock import patch
    with patch("trust_generator.v3.parsers.docx_parser.promote_seed") as m:
        ...
        assert m.call_count == 0
```

**Green:** The cycle-4b refactor extracted `_apply_post_promotion_protocol`; this cycle's tests drive its branches. Test fixtures provide synthetic docx files via the §6.7.1 helper.

**Refactor:** None expected; the helper is small.

#### 6.7.1 Synthetic docx fixture authoring (committed approach)

The test fixtures construct `.docx` files in `tmp_path` via `python-docx`'s `Document()` API at test time. **Programmatic construction is the committed approach**; checked-in fixture binaries are explicitly NOT used. Rationale: programmatic construction couples fixture content to parser expectations directly in the test source (changes to parser table-detection logic can be reflected in the fixture builder in the same commit), whereas binary fixtures drift silently when the parser's expectations change.

A fixture builder helper lives at `tests/v3/parsers/_docx_fixtures.py`:

```python
from pathlib import Path
from docx import Document

def make_docx_with(
    tmp_path: Path,
    *,
    trust_type: str | None = None,            # raw text, e.g. "Joint" / "Individual"
    grantor_name: str | None = None,
    co_grantor_name: str | None = None,
    marital_status: str | None = None,        # "Married" / "Unmarried"
    children: list[tuple[str, str]] | None = None,         # (name, dob)
    successor_trustees: list[tuple[str, str]] | None = None,
    beneficiary_shares: list[tuple[str, str]] | None = None,
    # ... expanded as cycles 5-7 surface needs
) -> Path:
    """Construct a minimal .docx with table rows wired to specified content.
    Returns a path under tmp_path. Each kwarg controls one table or paragraph
    block; absent kwargs produce no content for that section.
    """
    out = tmp_path / "fixture.docx"
    doc = Document()
    if trust_type is not None or grantor_name is not None:
        # ... emit the husband/grantor table per v2.2 layout
        ...
    # ... etc
    doc.save(str(out))
    return out
```

The builder produces docs that traverse the parser's table-detection logic. Synthetic fixtures complement (do not replace) the assets-directory template-based test in cycle 4b; the assets test is the integration anchor, the synthetic tests are the fine-grained branch tests.

### 6.8 Cycle 6 — docx parser coercion integration

Wires the cycle-3 coercion helpers into the docx parser's flat-dict → TrustData step.

**Red:** Tests that load fixtures with malformed dates (`"sometime in 2010"`), unparseable currency (`"a lot"`), one-token names (`"Acme Corp"`), placeholder-prefixed cells (`"[Spouse name] Jane Doe"`), one-token corporate-trustee names (`"First National Bank"`), and assert that:

- The parse succeeds (no exception).
- The corresponding TrustData fields fall back to schema defaults, are populated as entities, or are routed to CorporateTrustee per §5.4.9.
- `caplog` captures the expected `log.warning` and `log.info` calls.
- The disinheritance resolution (§5.4.10) correctly routes named excludees into `Beneficiary.disinherit` / `external_exclusions` based on name-match.
- The disinheritance multi-match WARNING is exercised: a v2 exclusions token (`"John"`) that matches both a `children` entry (`"John Smith"`) and an `other_beneficiaries` entry (`"Johnny Doe"`) produces exactly one `disinherit=True` flip on the iteration-order-first match (`"John Smith"` per §5.4.10's fixed order) plus one `caplog`-asserted WARNING naming both candidates. `"Johnny Doe"` retains `disinherit=False`.

**Green:** Replace direct field assignments with calls to the coercion helpers; wire the §5.3 step 6 post-merge resolution passes.

**Refactor:** None expected; the helpers are already cycle-3 outputs.

### 6.9 Cycle 7 — pdf parser

The pdf parser is structurally simpler than docx: AcroForm field iteration produces a flat dict directly, no table walking. It reuses the post-promotion protocol helper from cycle 5, the coercion helpers from cycle 3, and the field-presence normalization from §5.4.A.

**Red:** Tests parallel to cycle 4b's docx tests, gated behind `pytest.importorskip("pypdf"); pytest.importorskip("reportlab")`. The fill-and-reparse pattern from `tests/v2/test_pdf_parser.py` is the template. Adds three field-presence tests:

```python
def test_pdf_field_absent_is_None_at_coercion(): ...
def test_pdf_field_present_None_is_None_at_coercion(): ...
def test_pdf_field_present_empty_is_None_at_coercion(): ...
```

**Green:** Port v2 pdf parser body; adapt to v3 schema names; wire post-promotion helper; implement `_normalize_field_values` per §5.4.A.

**Refactor:** None expected.

### 6.10 Cycle 8 — registry

`parse_file` dispatches by extension.

**Red:**

```python
def test_parse_file_dispatches_json(tmp_path): ...
def test_parse_file_dispatches_docx(tmp_path, seed_initialized): ...
def test_parse_file_dispatches_pdf(tmp_path, seed_initialized): ...
def test_parse_file_raises_for_unsupported_extension(tmp_path): ...
def test_parse_file_raises_when_seed_required_for_docx(tmp_path):
    """Calling parse_file('foo.docx') without seed_initialized raises ValueError."""
def test_parse_file_ignores_seed_for_json(tmp_path):
    """parse_file('foo.json', seed_initialized=non_None) and
    parse_file('foo.json', seed_initialized=None) produce equal TrustData."""
```

**Green:** Implement `parse_file` as a thin extension-dispatch function. The "ignore seed for json" rule is testable via the equality contract above.

**Refactor:** None — green output is already minimal.

### 6.11 Cycle 9 — public exports

**Red:** A test asserting that `from trust_generator.v3.parsers import parse_docx, parse_pdf, parse_json, parse_file` succeeds.

**Green:** Update `__init__.py` `__all__`.

**Refactor:** None.

### Cycle ordering rationale

Cycles 1–2 (JSON) come first because the JSON parser is the most independent — it has no merge protocol, no coercion helpers, no shared infrastructure. Cycle 3 (coercion helpers, pure) precedes any parser that consumes them. Cycles 4a–6 build the docx parser inside-out: smoke test (4a, parser-existence-only signal) → asset integration (4b) → contract (5) → coercion integration (6). Cycle 7 (pdf) reuses the cycle-3 and cycle-5 outputs and is correspondingly thinner. Cycles 8–9 stitch the public surface.

Each cycle's tests, once green, regress no future cycle. The full-suite run at the end of cycle 9 is the session's exit criterion.

## 7. Migration Notes Structure

Migration notes are produced by downstream sessions exercising the parsers against real intake artifacts. They are **not** the parser's tests; they are a record of v2-shape inputs the parser has handled, with explicit notes on coercion outcomes.

Each migration note lives at `docs/superpowers/notes/parsers/<date>-<artifact-id>.md`.

### 7.1 Migration note template

```markdown
# Parser Migration Note — <artifact id>

| Field         | Value                                          |
| ------------- | ---------------------------------------------- |
| Date          | YYYY-MM-DD                                     |
| Artifact      | <path or descriptor of the intake artifact>    |
| Source format | docx / pdf / json                              |
| Author        | <session name>                                 |

## 1. Input shape
<Description of the artifact's structure: for docx, the table layout; for
pdf, the form-field naming convention; for json, the schema generation
context. Link to the artifact in `assets/` if checked in.>

## 2. Parse outcome
<What the parser produced. Field-by-field summary, organized by sub-model:
trust_id / grantor / co_grantor / family / assets / distribution / elections
/ text_blocks / external_exclusions.>

## 3. Coercions applied
<Per coercion category (date / Decimal / Address / PersonReference / enum /
reference-or-external / WithdrawalStep / new-v3-empty / CorporateTrustee /
disinheritance-resolution): which inputs hit which branch, which produced
warnings.>

## 4. Soft-fail surface
<List of `log.warning` and `log.info` calls observed, with the input that
triggered each.>

## 5. Schema-side observations
<Cases where the v2 input shape revealed a v3 schema gap or friction.
Captured as graph-edit proposals if the gap is structural; captured as
parser-side issues if the friction is in coercion logic.>

## 6. Diagnostic-rule observations
<Diagnostics fired by `diagnose()` against the parsed TrustData, with
note on which are signal (correctly fired) vs noise (false positives
to address).>

## 7. Open follow-ups
<Action items the note itself does not resolve.>
```

### 7.2 When to author a migration note

A migration note is authored when:

- A new artifact source is exercised end-to-end through `parse_file` for the first time.
- A v2 corpus instance is migrated to v3 and the migration produces non-trivial coercion paths.
- A parse run produces unexpected diagnostics that warrant investigation regardless of whether the issue is in the parser or in the schema.

A migration note is **not** authored when:

- A unit test changes (test code is its own record).
- A parser implementation detail changes without behavior shift (commit message is the record).

### 7.3 Migration note review and decay

Migration notes have a 6-month relevance window. After 6 months:

- If the artifact source is still in production, the note is reviewed; observations confirmed against current behavior or marked stale.
- If the artifact source is retired, the note is moved to `docs/superpowers/notes/archive/parsers/` with no further review.

A future "parser migration index" document at `docs/superpowers/notes/parsers/INDEX.md` aggregates active notes by artifact source. Its authoring is deferred until at least 3 notes exist (YAGNI under the current scope).

## 8. Regression Test Corpus Strategy

The regression test corpus has three tiers, each with its own location, gating, and authoring policy. Each tier guards a distinct failure mode (logic bugs, file-handling bugs, corpus-shape drift); merging any two would lose the failure-mode isolation.

### 8.1 Tier 1 — Pure unit tests (no external artifacts)

Location: `tests/v3/parsers/test_coercion.py`.

These exercise the cycle-3 coercion helpers with parametrized input → output assertions. No file I/O, no asset dependencies. Always run. Failure mode guarded: pure-logic bugs in coercion functions.

### 8.2 Tier 2 — Synthetic fixture tests

Location: `tests/v3/parsers/test_docx_parser.py`, `test_pdf_parser.py`, `test_json_parser.py`, plus the fixture builder at `tests/v3/parsers/_docx_fixtures.py`.

These construct intake artifacts (`.docx` via `python-docx`, `.pdf` via `reportlab`+`pypdf`, `.json` via `model_dump_json()`) inside `tmp_path` and parse them. The constructed artifacts target specific branches of the parsers — the post-promotion contract, each coercion category, the registry's dispatch branches. Failure mode guarded: parser-with-files bugs (table walking, AcroForm iteration, Pydantic validation paths) without dependence on real artifacts.

Gating:

- docx tests: ungated — `python-docx` is a v3 dependency.
- pdf tests: gated behind `pytest.importorskip("pypdf"); pytest.importorskip("reportlab")` per the v2 pattern.
- json tests: ungated — JSON is stdlib.

These tests are the bulk of the corpus. They are deterministic and fast and parametrize cleanly across coercion variants.

### 8.3 Tier 3 — Asset-anchored integration tests

Location: `tests/v3/parsers/test_assets_integration.py`.

These exercise the parsers against the checked-in intake artifacts in `assets/`:

- `Trust_Intake_Questionnaire.docx` — the v2.2 blank questionnaire template.
- `Trust_Intake_Questionnaire.pdf` — the v2.2 blank fillable PDF.
- `Trust_Intake_Questionnaire_data.json` — a JSON corpus instance.
- `Trust_Intake_Questionnaire_Clean.docx` — a "clean" template variant (purpose to be confirmed during cycle 4b fixture investigation; the file exists but its provenance is not documented in v2 specs).

Gating: each test is `@pytest.mark.skipif(not <PATH>.exists(), reason=...)`. The intent is that asset files may be ignored from version control in some workstation setups; tests should not break a green CI when assets are absent. Failure mode guarded: corpus-shape drift (the v2.2 questionnaire's actual content evolving away from what the synthetic fixtures model).

These tests are the integration anchor: they are slower, broader, and prove the parser handles real artifact shapes the synthetic fixtures may not cover.

### 8.4 What is NOT in the corpus (deliberately)

- **No CI-gated golden-file comparison.** A corpus pattern of "parse intake → dump TrustData JSON → byte-compare against committed golden" is rejected because the v3 schema includes Decimal, date, and enum types whose JSON representations have multiple valid forms; byte comparison creates churn on Pydantic version updates and on incidental ordering changes. The asset tests assert specific field values instead.
- **No production-data corpus.** Real client trust data is not committed to the repo. Migration notes (§7) document parser behavior on production data without reproducing the data itself.
- **No fuzzing harness.** Property-based tests on coercion helpers were considered (Hypothesis-style); deferred to a future session if coercion bugs accumulate. The cycle-3 parametrized tests are sufficient for v3.0.

### 8.5 Test execution and flake budget

- All Tier 1 and Tier 2 tests run on every `pixi run test`.
- Tier 3 tests run when assets are present.
- No retry logic, no mark.flaky. A test that flakes is a test that has a bug.

The expected total parser-test count at end of cycle 9: ~50–70 tests (~30 coercion, ~25 synthetic, ~5–10 asset integration). Test runtime budget: under 5 seconds for the full parser suite.

### 8.6 OCR coexistence

The OCR extraction surface (`OllamaBackend`, specified in `2026-04-27-ocr-protocol-ollama-design.md`) is an **independent input pre-stage** sibling to the docx/pdf/json parsers, not a text-source consumed by the pdf parser. Its return shape is `ExtractionResult(data: TrustData, trace: ExtractionTrace)`; the migrated parsers' return shape is `TrustData`. Both feed into `diagnose()` independently, with `diagnose()`'s optional `extraction` kwarg distinguishing the two. The corpus described in §8 does NOT exercise OCR — that is the OCR specs' responsibility — and the migrated parsers do NOT consume OCR-produced traces (the `extraction` kwarg flows directly from the OCR backend to `diagnose()`).

## 9. Open Questions / Deferred

| # | Question | Owner session |
|---|----------|---------------|
| Q1 | Should the parser emit placeholder markers (`[UNPARSEABLE_DATE]`, etc.) into target fields when soft-fail coercion fires, paired with diagnostic-rule extensions to surface them? §5.5.1 deferred this; the GUI's "parse log" surface is the natural place to land it. | GUI session |
| Q2 | Should `WithdrawalStep` accept `age: int \| None = None` plus an `age_description: str = ""` field for non-numeric timing (e.g., "upon college graduation")? §5.4.7 currently drops such rows; the schema relaxation would preserve them. | Future schema-modification session |
| Q3 | Should `parse_json` accept partial JSON (patches, fragmentary saves)? §4 narrows scope to full v3 documents only. The relaxation might be addressed via a separate `parse_json_patch` API rather than relaxing `parse_json`'s contract. | Future parser-revision session |
| Q4 | What is the v3 questionnaire DOCX layout? The "word template and parser" session redesigns the source artifact; the docx parser specified here will be revisited at that point. The redesign may add structured cells (e.g., explicit "is entity?" checkboxes, structured address blocks) that simplify §5.4 coercion. | Word template and parser session |
| Q5 | What is the v3 fillable PDF layout? The "pdf completion" session redesigns the source artifact; same revisit dynamic as Q4. | PDF completion session |
| Q6 | Should the registry support a `fileobj`-based dispatch (`parse_stream(fp, format=...)`) to enable parsing from memory? CLI use cases haven't required it; GUI use cases may. | GUI session |
| Q7 | Re-review trigger from plan-review pass 1: §5.3 (post-promotion merge protocol) and §5.4 (three new subsections plus §5.4.A) underwent substantive re-architecture during review. The second plan-review pass ran in Direct tier (file-accessible to the reviewer agent) and surfaced six findings (F1–F3 Important, F4–F6 Minor); all six are addressed in this revision and the clean threshold is now met. Q7 is closed. | Resolved in pass 2 |

## Decision log

| # | Decision | Section |
|---|----------|---------|
| 1 | New parser module under `src/trust_generator/v3/parsers/`; v2 parsers remain reference-only and are not deprecated in this session. | §2, §5.1 |
| 2 | `parse_docx` and `parse_pdf` take a required `seed_initialized: TrustData` argument. `parse_json` does not. The asymmetry is principled per §5.6. | §5.2, §5.6 |
| 3 | Return shape is `TrustData` (no tuple, no `ParseResult`, no paired ExtractionTrace). The OCR backend's `ExtractionResult` is the right shape for OCR; the migrated parsers' `TrustData` is the right shape for theirs. | §5.2 |
| 4 | Post-promotion merge protocol is deepcopy-and-fill: parsers do not mutate the caller's seed-initialized instance. Invariant P3 codifies the immutability postcondition. | §4 P3, §5.3 |
| 5 | Coercion helpers live in a dedicated `coercion.py` module, shared between docx and pdf parsers. | §5.1, §5.4 |
| 6 | Soft-fail surface is `log.warning(...)` / `log.info(...)`. Parsers do not invoke the diagnostics engine. | §5.5 |
| 7 | Placeholder markers in target fields are deferred to the GUI session. v3.0 parsers do not emit them. | §5.5.1, §9 Q1 |
| 8 | Three test tiers: pure unit, synthetic fixture, asset-anchored. Asset tests are skipif-gated on file existence. Each tier guards a distinct failure mode. | §8 |
| 9 | No golden-file byte comparison. No production-data corpus. No fuzzing harness. | §8.4 |
| 10 | TDD ordering: JSON parser first (most independent), coercion helpers second (pure), docx parser inside-out third (smoke 4a → asset 4b → contract → coercion integration), pdf parser fourth (reuses prior outputs), registry fifth, public exports sixth. | §6 |
| 11 | WithdrawalStep age-parse failure drops the row. Decimal coercion failure on a share-percent field also drops the row. Schema relaxation logged as §9 Q2. | §5.4.2, §5.4.7 |
| 12 | PersonReference one-token name is trapped and re-constructed as `is_entity=True`. Placeholder-prefix stripping (regex `\[[^\]]+\]\s*`) runs before the trap-and-reconstruct. | §5.4.4 |
| 13 | BeneficiaryShare/SpecificBequest always emit `recipient_external` from the v2 corpus shape; `recipient_ref` is reserved for a future GUI-id workflow. | §5.4.6 |
| 14 | Migration notes structure is template-based (§7.1), authored on first-exercise of an artifact source, decay-reviewed at 6 months. | §7 |
| 15 | New v3 models with no v2 source (Pet, GuardianshipDesignation, DigitalAssetDirective) emit empty list; CustomTerm built from the three v2 free-text fields with category-by-source-name. external_exclusion_reasons populated by the §5.4.10 resolution pass. | §5.4.8 |
| 16 | CorporateTrustee discrimination uses a conservative case-insensitive regex on the name; matches yield CorporateTrustee instances, non-matches yield SuccessorTrustee. INFO-logged per discriminated entry. | §5.4.9 |
| 17 | Disinheritance resolution runs as a post-merge step (§5.3 step 6), name-matching the v2 `exclusions` text against populated beneficiary lists; matches set `Beneficiary.disinherit=True`, non-matches flow to `external_exclusions`. | §5.4.10 |
| 18 | AcroForm field-presence states (absent / present-None / present-empty) all normalize to `None` at coercion entry via `pdf_parser._normalize_field_values`. | §5.4.A |
| 19 | trust_type and marital_status mutations are applied jointly with a fixed ordering (trust_type first, marital_status second, co_grantor materialization computed once after both); cycle 5 parametrizes over four combinatorial (seed, parsed) cases. | §5.3 step 4 |
| 20 | Synthetic docx fixtures are constructed programmatically in tests via `python-docx`, not committed as binaries. | §6.7.1 |
| 21 | Distinguish seed-materialized-empty from paralegal-populated co_grantor in §5.3 step 4. Dematerialize the former on post-mutation no-co_grantor states; preserve the latter unconditionally. Resolves contradiction with §6.7 row 1 (jt_mr_to_in_um). | §5.3 step 4 |

## Plan-review summary

**Validation tier:** Fallback. Plan-review subagent dispatch ran but the agent could not directly read the spec file (the wsl-mounted path was outside its connected folders). The review proceeded against a detailed structural summary of the spec rather than the verbatim text. Findings are tagged accordingly; high-confidence findings target structural decisions explicitly described in the prompt; low-confidence findings target sections only sketched in the prompt. The review's H1–H4 and M1–M6 findings have all been addressed in this revision; the review pass is recorded as the spec's first review iteration.

**Findings inventory and dispositions:**

| ID | Category | Severity | Disposition |
|----|----------|----------|-------------|
| H1 | invalid-assumption | High | Applied to §5.4.2: the diagnostic-indistinguishability claim is now bounded; share-percent fields are explicitly carved out and treated like WithdrawalStep (drop-the-row on coercion failure). Decision log #11 codifies. |
| H2 | missing-edge-case / coercion-completeness | High | Applied via three new subsections: §5.4.8 (new v3 models with no v2 source), §5.4.9 (CorporateTrustee discrimination heuristic), §5.4.10 (disinheritance resolution as post-merge step). Decision log #15–17 codify. |
| H3 | invalid-assumption | High | Applied to §4: parse_json's scope is explicitly narrowed to "full v3 TrustData JSON documents." Partial-JSON workflows are deferred to §9 Q3. |
| H4 | missing-edge-case | High | Applied to §5.3: step 4 now specifies trust_type-first ordering and combinatorial cycle-5 coverage of joint mutations. Decision log #19 codifies. |
| M1 | underspecified-integration | Medium | Applied to §4 (new invariant P3) and §5.3 (step 1 bridges postcondition + implementation). The cycle-4a smoke test asserts the postcondition directly. |
| M2 | underspecified-integration | Medium | Applied to §6.10: the `test_parse_file_ignores_seed_for_json` contract test is defined as an explicit equality assertion. |
| M3 | missing-edge-case | Medium | Applied to §5.4.4: placeholder-prefix stripping rule defined with regex `\[[^\]]+\]\s*`. Decision log #12 codifies. |
| M4 | missing-edge-case | Medium | Applied via new §5.4.A: AcroForm field-presence states (absent / present-None / present-empty) explicitly normalized. Decision log #18 codifies. |
| M5 | TDD-ordering | Medium | Applied via cycle split: §6.5 is now cycle 4a (smoke test, no asset dep), §6.6 is cycle 4b (asset integration); cycle 4a's red signal is unambiguously "parser absent." |
| M6 | underspecified-integration | Medium | Applied to §6.7.1: programmatic-construction approach explicitly committed; binary fixtures explicitly NOT used; rationale recorded. Decision log #20 codifies. |
| L1 | over-engineering | Low | Accepted with rationale: the migration-notes structure is for FUTURE sessions exercising parsers against production artifacts; collapsing to a CHANGELOG-style entry would lose the per-coercion-category surface that future-session reviewers rely on. The structure is a cheap-to-author template, not a bureaucratic burden. |
| L2 | over-engineering | Low | Accepted with rationale: the three tiers carry distinct invariants (Tier 1 = pure I/O-free unit, Tier 2 = parser-with-files-but-no-assets, Tier 3 = real-artifact-anchored). Each is a different gate against a different failure mode (logic bug / fixture-handling bug / corpus-shape drift). Merging would lose either fixture-creation cost reduction or asset-dependent failure isolation. §8.1–§8.3 now state each tier's distinct invariant explicitly. |
| L3 | over-engineering — rejected | Low | Reviewer withdrew finding; no action. |
| L4 | underspecified-integration | Low | Applied via new §8.6: OCR's coexistence with the migrated parsers is explicitly stated (independent pre-stage sibling, not a text-source consumer of pdf parser). |

**Re-review trigger (pass 1 → pass 2):** §5.3 underwent substantive re-architecture (a new step 6 for post-merge resolution; the trust_type/marital_status mutation rule restructured). §5.4 acquired three new subsections (§5.4.8, §5.4.9, §5.4.10) plus one cross-cutting subsection (§5.4.A). Per `review_termination.re_review_trigger`, these warranted a second plan-review pass.

## Plan-review pass 2

**Validation tier:** Direct. The spec was copied to a Windows-accessible path before the agent ran; the reviewer used Read against the file and walked the body line-by-line.

**Findings inventory and dispositions (pass 2):**

| ID | Category | Severity | Disposition |
|----|----------|----------|-------------|
| F1 | underspecified-integration | Important | Applied to §5.3 step 4: explicit "None / absent gate" sub-bullet specifying that a parsed `None` means "no mutation requested" and the seed-initialized value persists. The gate is load-bearing because `trust_type` is a required schema field. |
| F2 | underspecified-integration | Important | Applied to §5.4.10 algorithm step 2: fixed iteration order pinned (`children` → `descendants` → `other_beneficiaries`, then Pydantic insertion order within each list). Multi-match WARNING explicitly logs both candidates without changing the chosen target. |
| F3 | underspecified-integration | Important | Applied to §5.3 step 6 (disinheritance bullet), §5.4.8 (`external_exclusions` row), and §5.4.10 (algorithm step 1): the v2 exclusions string is captured during step 2 extraction as a parser-internal string variable, NOT stored on `result`. It is threaded as a function-local argument into the post-merge resolution call. |
| F4 | missing-edge-case | Minor | Applied to §6.8 cycle 6 red phase: explicit multi-match WARNING test case added with concrete example tokens (`"John"` matching both `"John Smith"` in children and `"Johnny Doe"` in other_beneficiaries). Depends on F2's iteration-order pin. |
| F5 | missing-edge-case | Minor | Applied to §5.4.9: explicit "Known limitation" paragraph naming the natural-person-named-Bank scenario. The INFO log + future entity-checkbox structural fix is the documented mitigation. |
| F6 | underspecified-integration | Minor | Applied to §5.3 (Implementation note at end): step 4 lives in `_apply_post_promotion_protocol`; step 6 lives in a separate `_apply_post_merge_resolution` helper. Split rationale stated. |

**Clean threshold assessment (pass 2):** Met. After F1–F6 are applied:

- No severity-high findings remain.
- No severity-medium findings touching §5 or §6 contracts remain (F1–F3 were Important and have been resolved with surgical text additions, not re-architecture).
- All Minor findings are addressed; none are accepted-with-rationale.

**No third-pass trigger.** F1–F6's resolutions are surgical text additions (one paragraph or sub-bullet each) without re-architecting any subsection. Per `review_termination.re_review_trigger`, surgical fixes do not warrant another pass. The spec is final.

**Confidence on remaining gaps:** Low. The two findings the original pass-1 reviewer expressed lowest confidence in (the v2 corpus is finite/exhaustively-enumerated assumption and the diagnostic indistinguishability claim) have been tightened (pass-1 H1) but cannot be fully resolved at the spec level — the v2 corpus surprises are revealed at exercise time, which is what migration notes (§7) capture. The spec's commitment is that future-session migration notes flag any coercion-pattern gaps as graph-edit proposals, not in-spec amendments.
