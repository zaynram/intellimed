# TGv3 OCR Extraction Protocol & OllamaBackend Design

| Field             | Value                                                                                                                                                       |
| ----------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Spec date         | 2026-04-27                                                                                                                                                  |
| Status            | Draft                                                                                                                                                       |
| Supersedes        | n/a (new subsystem)                                                                                                                                         |
| Relevant entities | `bounded_context_design`, `added_models`, `modified_surfaces`, `relationship_enum_design`, `library_selections`, `python_stack_commitments`                 |
| Out of scope      | AnthropicBackend (Session 4.3b); ConfidenceProtocol implementation (Session 4.3c); GUI integration; per-firm model selection commitment; v3 parser registry implementation beyond the OCR slot; persistence transport for the trace artifact (consumer-layer concern) |

## 1. Motivation

TGv3 generates printable intake documents (the *paralegal printable*) from a `QuestionnaireSeed`, which the firm hands to the client to fill in by hand. The handwritten artifact returns to the firm as scanned image input. To complete the consultation-to-canonical pipeline, the firm needs an extraction surface that produces a `TrustData` from those images — the same canonical type that the existing `.docx`, `.json`, and `.pdf` paths produce.

A handwritten form is not a `.docx`: extraction is probabilistic, illegibility is a first-class outcome, and per-field confidence varies across a single page. None of these signals exist in the established parser contract. They cannot be reconstructed from the produced `TrustData` alone — once a value lands, the post-fill model is silent on whether the value is a confident transcription, a best guess, or a leak from a smudged stroke. The diagnostics engine's `extraction.placeholder_unfilled` rule covers a single sentinel-string case in one free-text field; it does not generalize to typed fields (`Decimal`, `date`, enums, references) where in-band sentinels cannot be encoded.

This spec defines the OCR extraction surface end to end: a backend-agnostic `ExtractionProtocol`, a structured-diagnostics result shape (`ExtractionResult`, `ExtractionTrace`, `FieldExtraction`), an `OllamaBackend` concrete implementation that drives a local vision-language model via the official `ollama` Python client with grammar-constrained Pydantic-schema generation, the prompt strategy for legal handwritten intake, the integration seam with `diagnose()` that produces per-field `Diagnostic` instances from trace state, and the verification lifecycle that lets paralegals mark extraction findings as resolved.

## 2. Scope

### In scope

- `ExtractionProtocol` (backend-agnostic) — the `extract(source: SourceRef) -> ExtractionResult` method shape and contract.
- `ExtractionResult` — the `(TrustData, ExtractionTrace)` pairing returned by every extraction.
- `ExtractionTrace`, `FieldExtraction` — the per-field provenance/diagnostics sidecar.
- Marker classes: `RawSelfReport`, `IncompleteUntilValidated`.
- `INCOMPLETE` — the v3 sentinel for unverified `normalized_value` placeholder semantics.
- `OllamaBackend` — concrete implementation against `ollama >= 0.6.1` using `format=Schema.model_json_schema()` constrained generation.
- Vision-language model output Pydantic schema (the *generation envelope*) and field-order discipline.
- Prompt-engineering strategy for legal handwritten intake.
- `diagnose()` integration: `extraction` namespace in `eval_context`; trace-driven Diagnostic synthesis sitting alongside rule-driven evaluation.
- Verify lifecycle: per-field verification on the trace; interaction with the existing `force_generation()` override flow.
- Stale-path filtering: trace entries whose `field_path` no longer resolves against current `TrustData`.
- Test scenarios: parser round-trip; trace propagation; verify lifecycle; stale-path behavior; constrained-decoding schema field-order; vision-model invocation; merge order in `diagnose()`; override-after-verify interaction.

### Out of scope (enforced)

- **AnthropicBackend (Session 4.3b)** — the Protocol surface defined here constrains 4.3b but the implementation lives in its own session.
- **ConfidenceProtocol implementation (Session 4.3c)** — this spec reserves the `confidence_self_report` slot via `Annotated[float, RawSelfReport] | None`; 4.3c populates it.
- **GUI** — display of extraction state, click-to-verify affordances, and bulk-verify gestures are GUI concerns. This spec defines the data-model contract those affordances bind to.
- **Per-firm model selection commitment** — the spec names *indicative* models (Qwen2.5-VL:7b, MiniCPM-V) based on recon. Empirical validation against firm-side handwriting samples is a separate exercise (see in-flight chores below).
- **v3 parser registry beyond the OCR slot** — non-OCR parsers (`.docx`, `.json`, `.pdf`) are reference-only legacy from v2 (per amendment to memory: v2 is reference, not API to maintain). The registry shape is defined here for the OCR slot only; other parser types adopt the contract as they are reimplemented for v3.
- **Persistence transport for `ExtractionTrace`** — whether the trace lives in SQLite alongside the trust, in a sibling JSON file, or in a synced SharePoint folder is a consumer-layer (CLI/GUI) concern. This spec specifies the in-memory contract.
- **Multi-page batching strategy** — `extract()` accepts a single `SourceRef` per call. Whether a multi-page form decomposes into multiple calls, a single call with multiple images, or a streaming variant is a backend-internal concern documented for `OllamaBackend` only (§7.5).
- **Re-extraction and trace merging** — `extract()` produces a single trace per call. If a paralegal re-runs OCR on the same source (e.g., to try a different model), the result is a new `ExtractionResult` with its own trace; merging traces from multiple runs (and reconciling potentially-different field indexing) is out of scope for v3.0. If this lands as a feature, it gets its own session.

### In-flight chores

These are tracked workstreams that begin during 4.3a implementation but extend beyond its closure. They live in `.claude/context/chores.xml` once the spec is finalized. They are documented here in the Scope section because their existence shapes scope decisions made elsewhere in the spec (for example, the deferral of empirical model commitment in *Out of scope* above, and the deferral of persistence machinery for `INCOMPLETE` in §6.2).

#### Empirical model selection

Goal: validate the indicative model recommendation (Qwen2.5-VL:7b primary, MiniCPM-V alternative) against firm-side handwriting samples.

Method:

1. Collect a small representative set of handwritten intake forms (target: 10–20 forms covering realistic handwriting variability; consult with paralegal staff on representativeness).
2. Run each through `OllamaBackend` configured for each candidate model, with `temperature=0`.
3. Score each result on: per-field accuracy (matches paralegal-truth), illegibility flag precision and recall, hallucination rate (transcribed values for blank fields).
4. Document findings in a separate session note. Promote the winning model to be the default-recommended `model=` constructor argument in `OllamaBackend` documentation; do not hard-code (the constructor accepts model name as configuration).

Exit criteria: documented model recommendation with sample-size-disclosed confidence; if neither candidate meets a usability bar (e.g., >85% per-field accuracy on legible fields), the chore extends to evaluating additional models.

#### Schema complexity ceiling under constrained decoding

Goal: characterize the boundary at which grammar-constrained decoding produces EOF errors or schema-violation retries on the candidate vision models, given the production envelope schema's complexity.

Method:

1. Add a benchmarking test (`test_envelope_complexity_ceiling.py`, `pytest.mark.integration`) that runs `OllamaBackend.extract` against synthetic forms with controlled field counts and observes pass-rate vs. envelope size.
2. The test is informational, not gating; it logs results to `tests/data/extraction_ceiling_log/`.
3. Opportunistically test reasoning-omission (envelope variant without the `reasoning` field) as part of the same exercise to gather evidence for §7.4's reasoning-first posture.
4. **Persistence in code (per request).** A module-level docstring comment in `ollama_backend.py` references this chore by name and links to the test path, so the constraint surfaces during any future schema modification. The same comment lands at the top of `trace.py` (already present in §5.3) and at the OllamaBackend docstring.

Exit criteria: documented threshold (in fields, in JSON-schema bytes, or both) at which production-class models become unreliable; if the threshold falls below the production envelope's complexity, the chunked-extraction strategy (§7.5) lands as its own session. Reasoning-channel evidence (kept or dropped) lands as a §7.4 amendment.

#### Trace persistence and serialization contract

Goal: define the canonical serialization for `ExtractionTrace` so that consumer-layer persistence (CLI, GUI, future SharePoint integration) does not reinvent the wheel.

Recommendation (informational; commitment lives in the consumer's session): adopt `model_dump_json()` / `model_validate_json()` as the canonical round-trip. `INCOMPLETE` requires a custom serializer/validator pair when persistence lands; the v3.0 trace ships without it (see §6.2 refactor note). The same chore captures the question of whether the trace persists alongside the trust (sibling JSON), embedded in TrustData metadata, or in a separate store.

Exit criteria: a brief design note documenting the chosen persistence shape, ratified by the consumer session that introduces it.

## 3. Reference material

A claude-code session composing the implementation plan should load the following before writing any code.

### 3.1 Memory entities (open via `memory:open_nodes`)

| Entity                     | Why                                                                                                                                                |
| -------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| `bounded_context_design`   | The Seed-vs-TrustData separation and its load-bearing principle (no single model with conditional validation conflating two contexts).             |
| `added_models`             | The TrustData submodel population pattern — what counts as a "fully constructed" sub-model the parser may emit.                                    |
| `modified_surfaces`        | Where TrustData fields hang off the canonical model; relevant for `field_path` semantics on `FieldExtraction`.                                     |
| `relationship_enum_design` | Enum vocabulary for relationship fields the OCR backend must produce; tightens what the constrained schema may emit.                               |
| `library_selections`       | Will be updated by this session to add `ollama >=0.6.1` with the naming-hazard caveat.                                                             |
| `python_stack_commitments` | Pydantic v2.x; PEP 695 type alias runtime non-identity; `stdlib datetime` only — these constrain how the trace and marker classes are written.     |

### 3.2 Source files (read before authoring)

| Path                                                              | Why                                                                                                                                                                                       |
| ----------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/trust_generator/v3/schema.py`                                | `TrustData`, `Diagnostic`, `DiagnosticLevel`, `DiagnosticSource`, `DiagnosticContext` definitions. Every `field_path` semantics in the trace traces against this module's structure.       |
| `src/trust_generator/v3/diagnostics/engine.py`                    | The `diagnose()` entry point this spec extends with an `extraction` keyword argument and a trace-driven synthesis step.                                                                  |
| `src/trust_generator/v3/diagnostics/eval_context.py`              | The eval-context shape; this spec adds the `extraction` namespace.                                                                                                                       |
| `src/trust_generator/v3/diagnostics/loader.py`                    | The `_build_rule_context()` type resolver; this spec adds the `extraction` symbol declaration.                                                                                            |
| `src/trust_generator/v3/diagnostics/rules/builtin.yaml`           | Existing rule corpus including `extraction.placeholder_unfilled`. This spec coexists with that rule and adds new declarative rules that read the trace.                                  |
| `src/trust_generator/v3/config/firm.py`                           | `FirmConfig.diagnostics` shape; reference for any future firm-config knobs governing OCR behavior (none in v3.0).                                                                         |
| `docs/superpowers/specs/2026-04-23-diagnostics-engine-design.md`  | §5.1 (signature), §5.2 (eval context), §5.4 (dedupe/collision); this spec is amended in lockstep (§14).                                                                                  |

### 3.3 External references

- `ollama` Python client: <https://pypi.org/project/ollama/> — official client, Apache-2.0, depends on `httpx` and `pydantic`. NOT to be confused with the `ollama-python` package on PyPI (third-party, abandoned 2024-01).
- Ollama structured outputs: <https://ollama.com/blog/structured-outputs> — `format=Pydantic.model_json_schema()` pattern.
- Ollama structured outputs reference: <https://docs.ollama.com/capabilities/structured-outputs> — definitive capability documentation; notes that Cloud does not support structured outputs (self-hosted only).
- llama.cpp grammar system (mechanism Ollama inherits): <https://deepwiki.com/ggml-org/llama.cpp/8.1-speculative-decoding> — the GBNF grammar-constrained decoding underlying `format=` in Ollama.

## 4. Library reconnaissance

### 4.1 `ollama` (Apache-2.0, PyPI)

Resolution: **adopt-as-dependency** at floor `>=0.6.1`.

Reasons:

1. **Official.** The `ollama` package is maintained by the Ollama team and tracks the core release cadence. Latest is 0.6.1 (released 2025-11-13). The disambiguating PyPI package `ollama-python` is a third-party abandoned client (last release 2024-01-17, four total releases) and must not be selected; the spec pins the import name explicitly to avoid ambiguity.
2. **Thin surface.** The wheel is 14.4 kB and depends only on `httpx` and `pydantic`. Both are already first-class dependencies of the v3 stack. No incidental complexity.
3. **Pydantic-native structured-output pathway.** The `chat()` and `generate()` calls accept `format=Schema.model_json_schema()`, with the model output validated round-trip via `Schema.model_validate_json(response.message.content)`. This is the canonical pathway and the load-bearing capability for the design (§7).
4. **Mechanism is grammar-constrained decoding.** Ollama inherits llama.cpp's GBNF grammar-constrained sampling: schemas are converted to grammars and constraints are applied at every token via logit masking, not post-hoc retry. Two consequences shape the design — (a) any "reasoning" or commentary channel the model emits must exist as a string-typed field declared *before* data fields in the Pydantic schema (Pydantic v2 preserves declaration order in `model_json_schema()`); (b) deterministic schema adherence requires `options={'temperature': 0}`. Both are pinned in §7 and tested in §6.
5. **Vision-model interaction.** `messages=[{..., 'images': [path]}]` works alongside `format=...`. The same call shape supports text-only chat and vision-augmented chat. No backend-side branching needed for image input.
6. **Sync and async clients available.** `Client` and `AsyncClient` are parallel surfaces. v3.0 adopts the sync client (`OllamaBackend` is sync); async migration is non-breaking when needed.
7. **Cloud caveat.** Ollama Cloud does not support structured outputs. TGv3's local-inference posture matches the supported configuration; the spec records this constraint for future maintainers.

Recon findings recorded as a candidate observation on the `library_selections` graph entity (proposed at §15).

### 4.2 Vision-language model recon (informational)

Per the session non-goal that recon informs but does not commit to a specific model: the spec names *indicative* candidates without binding `OllamaBackend` to any one. The model name is configuration; `OllamaBackend` accepts it as a constructor parameter.

| Candidate            | Strength on handwriting / forms (per recon)                                                          | Caveat                                                              |
| -------------------- | ----------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| Qwen2.5-VL:7b        | Trained explicitly for document/form structured-output extraction; DocVQA 95.7; recommended for OCR | Older Ollama compatibility note (≥0.7.0); confirm on target version |
| MiniCPM-V (2.6)      | Recommended alongside Qwen2.5-VL for handwriting and non-standard fonts                              | Spotty on some recent benchmark comparisons                          |
| Llama 3.2-Vision     | Widely cited but recent benchmarks show higher hallucination on text-heavy tasks                     | Consider deprioritizing pending firm-side evaluation per the *Empirical model selection* chore in §2; single-source caveat applies |

The empirical selection exercise is captured as an in-flight chore in §2.

## 5. Architecture overview

The OCR extraction surface is composed of seven units. Each unit is small enough to test in isolation. §6 gives the test-first construction order; this section is the reference shape that all cycles target.

### 5.1 Module layout

```
src/trust_generator/v3/extraction/
├── __init__.py
├── markers.py        # IncompleteUntilValidated, RawSelfReport
├── trace.py          # FieldExtraction, ExtractionTrace, ExtractionResult, INCOMPLETE
├── protocol.py       # ExtractionProtocol, SourceRef, ExtractionError
├── paths.py          # field_path resolution helpers
├── ollama_backend.py # OllamaBackend, the generation envelope schema
├── prompt.py         # prompt construction for legal handwritten intake
└── synthesis.py      # trace-driven Diagnostic synthesis (called from diagnose())
```

### 5.2 The marker classes

```python
# src/trust_generator/v3/extraction/markers.py

class IncompleteUntilValidated:
    """Type-level marker on `FieldExtraction.normalized_value`.

    Indicates the value has not been validated against its target TrustData
    field's type and may not satisfy that field's constraints. Consumers
    MUST narrow via isinstance against the target type before use. The
    field's static type is `object`, which makes this discipline visible
    to type checkers.
    """


class RawSelfReport:
    """Type-level marker on `FieldExtraction.confidence_self_report`.

    Indicates the value is the model's own first-order confidence report
    in [0.0, 1.0], with no calibration applied. Consumers requiring
    calibrated confidence MUST route the value through a
    `ConfidenceProtocol` implementation (Session 4.3c). Both readers and
    producers must respect this marker; any future calibrated channel
    receives a sibling marker (e.g., `Calibrated`) and a separate field.
    """
```

The two markers form a coherent design vocabulary: each names a property of its field that consumers must respect before use. They live in their own module so the trace and protocol modules can import them without circularity.

### 5.3 The trace types

```python
# src/trust_generator/v3/extraction/trace.py

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Final

from pydantic import BaseModel, ConfigDict, Field

from trust_generator.v3.extraction.markers import (
    IncompleteUntilValidated,
    RawSelfReport,
)
from trust_generator.v3.schema import TrustData

# IMPORTANT: This module embodies the v3.0 commitment to Approach B′
# (free generation with structurally constrained diagnostics, sidecar form).
# See spec §7.4 for the rationale: the generation envelope (the model's
# Pydantic output schema) reserves a string-typed `reasoning` field that
# is declared first to materialize the chain-of-thought benefit under
# grammar-constrained decoding. This is the current best-practice
# posture for grammar-constrained generation; reordering or removing it
# is plausible-only-with-evidence (§13.2 chore is the gathering point).
# Do not move it without re-reading §7.4 and the field-order test in
# §6.4.
#
# IMPORTANT: Schema complexity ceiling under constrained decoding —
# small models can produce unexpected EOF errors on complex schemas. If
# this surfaces in production, consult §7.5 (chunked extraction) and
# §13.2 (in-flight chore) before changing this module's shape.

INCOMPLETE: Final[object] = object()
"""Module-level sentinel for `FieldExtraction.normalized_value` when
extraction completed but normalization against the target TrustData
field type has not yet been validated.

Compared via identity (``field.normalized_value is INCOMPLETE``), never
by equality. The sentinel is not exported via `__all__`; consumers
import it explicitly.
"""


class FieldExtraction(BaseModel):
    """A single per-field extraction record.

    `field_path` uses the dotted-path convention shared with
    `Diagnostic.field_path` (e.g., 'children[0].full_legal_name',
    'real_property[2].value'). The match is deliberate: a single
    convention across both surfaces keeps GUI anchor logic uniform.
    The path is resolved against the paired TrustData via
    `extraction.paths.resolve` (§5.7) at synthesis time; paths that no
    longer resolve are filtered as stale.

    `field_path` MUST be unique within an `ExtractionTrace` (data-integrity
    invariant; see `verify_field` and §6.2 tests).

    Verification is bound to the value at verify time. If `TrustData`
    is mutated to a different value at the same path AFTER
    verification, the verification flag is not invalidated by the
    mutation; the trace remains a faithful record of "the paralegal
    confirmed this field was correct at the time of verification."
    Surfacing post-verification divergence to the paralegal is a
    consumer-layer (GUI/CLI) concern; the trace itself does not detect
    it.
    """

    model_config = ConfigDict(extra="forbid")

    field_path: str
    raw_value: str
    """The model's verbatim transcription of the field, including any
    illegibility markers, original whitespace, etc. This is the
    forensic record of what was on the form, before normalization."""

    normalized_value: Annotated[object, IncompleteUntilValidated] | None = None
    """The parsed/typed value the parser derived from `raw_value`, if it
    completed normalization. `None` indicates extraction did not produce
    a value (e.g., illegible). The `INCOMPLETE` sentinel indicates
    extraction produced a `raw_value` but normalization against the
    target TrustData field type has not yet been validated.

    Static type is `object`: consumers MUST narrow via isinstance
    against the target field's type before use. See the
    `IncompleteUntilValidated` marker for the contract."""

    illegible: bool = False
    """True when the model reports the field could not be read with any
    confidence. Mutually consistent with `normalized_value is None`:
    the parser MUST NOT emit `illegible=True` alongside a non-None
    `normalized_value`."""

    confidence_self_report: Annotated[float, RawSelfReport] | None = None
    """v3.0 reserves this slot for Session 4.3c's ConfidenceProtocol.
    Populated as `None` by `OllamaBackend` in v3.0. See the
    `RawSelfReport` marker for the contract."""

    verified: bool = False
    """True when a paralegal has confirmed the extraction is correct.
    Mutated via `ExtractionTrace.verify_field()`; never mutated directly
    by parser code."""

    verified_at: datetime | None = None
    """Set in lockstep with `verified=True` by `verify_field()`. The
    parser MUST emit `verified_at=None`."""


class ExtractionTrace(BaseModel):
    """A list of per-field extraction records produced by a single
    `extract()` call, with verify-mutation methods.

    The trace is the spine of the verification, provenance, and
    forward-compatible confidence architecture. It is paired with a
    `TrustData` (in `ExtractionResult`) and consumed by `diagnose()`
    via the `extraction` namespace in eval_context.
    """

    model_config = ConfigDict(extra="forbid")

    fields: list[FieldExtraction] = Field(default_factory=list)
    """Per-field records, in parser-emission order. `synthesize_extraction_diagnostics`
    walks this list in order, so the parser's emission order determines the
    Diagnostic emission order for trace-driven Diagnostics."""

    backend_id: str
    """Identifier of the backend that produced this trace. Convention:
    `<backend>:<model>` where `<backend>` is a short backend name
    (`ollama`, `anthropic`) and `<model>` is the model identifier
    (e.g., `qwen2.5vl:7b`, `claude-sonnet-4-7`). A version suffix is
    permitted when meaningful. Forensic record only; diagnostic logic
    does not branch on backend identity."""
    extracted_at: datetime

    def verify_field(self, field_path: str, *, at: datetime | None = None) -> None:
        """Mark the field at `field_path` as verified.

        Mutates the matching `FieldExtraction` in place, setting
        `verified=True` and `verified_at` to `at` (defaults to
        `datetime.now(UTC)`).

        Raises `KeyError` if no FieldExtraction has a matching
        `field_path`. Raises `ValueError` if multiple do (data-integrity
        invariant: `field_path` is unique within a trace).
        """
        ...


class ExtractionResult(BaseModel):
    """The pairing returned by every `ExtractionProtocol.extract()` call.

    Both fields are required. `data` is the canonical TrustData; `trace`
    is the per-field provenance sidecar. Non-OCR parsers under the v3
    registry contract return `(data, None)` for `trace` (see §5.4).
    """

    model_config = ConfigDict(extra="forbid")

    data: TrustData
    trace: ExtractionTrace
```

### 5.4 The Protocol

```python
# src/trust_generator/v3/extraction/protocol.py

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from trust_generator.v3.extraction.trace import ExtractionResult


type SourceRef = Path
"""v3.0 SourceRef: a filesystem path to a single image or PDF.

Multi-page handling is backend-internal (see `OllamaBackend.extract`,
§7.5). The alias exists to mark the public name of this concept; if a
later session needs to widen its meaning, the alias is the change site.
v3.0 makes no commitment about future variants.

PEP 695 type aliases are type-checker-visible only; runtime-side
isinstance checks would not see this alias. Per
`python_stack_commitments`, comparisons should not rely on this name
at runtime.
"""


class ExtractionError(Exception):
    """Base for backend-emitted extraction failures. Backends raise this
    (or a subclass) when extraction cannot proceed; partial extraction
    with per-field illegibility flags is the success path and does not
    raise."""


class ExtractionProtocol(Protocol):
    """Backend-agnostic OCR extraction surface.

    The Protocol's return type is the only return type. There is no
    bare-TrustData escape hatch: backends that produce TrustData
    without a paired trace would defeat the verification contract that
    `diagnose()`'s trace-driven synthesis depends on. This is a
    deliberate interface invariant; tests in §6.5 enforce it on
    `OllamaBackend` and any future backend.

    Not `@runtime_checkable` at v3.0: the structural type-check role is
    served by the static type checker; runtime isinstance checks are
    not currently needed and the decorator carries an unfunded cost
    (slower checks; signature subtleties). If a runtime use case
    surfaces, add it then.
    """

    def extract(self, source: SourceRef) -> ExtractionResult:
        """Extract a TrustData and ExtractionTrace from one source.

        Failure modes raise `ExtractionError` (or subclass). Per-field
        illegibility, missing fields, and low-confidence transcriptions
        are NOT failures: they are returned as `FieldExtraction`
        entries on the trace with `illegible=True` and/or
        `normalized_value=None`. A trace with zero usable fields is a
        valid (if unhelpful) result.
        """
        ...
```

### 5.5 The non-OCR parser registry slot (v3.0)

The v3 parser registry is greenfield. `ExtractionProtocol` is the contract for the OCR slot. Non-OCR parsers (`.docx`, `.json`, `.pdf`) are reference-only legacy from v2 (per amendment to memory: "v2 code is purely referential and should not be regarded as an API to maintain. consider v3 a spiritual successor, not a revision").

When v3 parsers for non-OCR formats are reimplemented (out of scope for 4.3a), they adopt the same Protocol shape. For non-OCR formats the trace is constructed with `fields=[]`, since per-field provenance is not meaningful for structured input — the registry contract is uniform.

### 5.6 The `OllamaBackend` (concrete)

Surface:

```python
# src/trust_generator/v3/extraction/ollama_backend.py (sketch)

class OllamaBackend:
    """ExtractionProtocol implementation against a local Ollama server.

    Pinned dependency: `ollama >= 0.6.1`. Pinned schema delivery:
    `format=GenerationEnvelope.model_json_schema()`. Pinned
    determinism: `options={'temperature': 0}`. Pinned field-order
    discipline: see §7.4 and the test in §6.4.
    """

    def __init__(
        self,
        model: str,                             # e.g., 'qwen2.5vl:7b'
        client: ollama.Client | None = None,    # default constructed
        prompt_builder: PromptBuilder | None = None,
    ) -> None: ...

    def extract(self, source: SourceRef) -> ExtractionResult: ...
```

The implementation flow is documented in §7.

### 5.7 Path resolution helper

```python
# src/trust_generator/v3/extraction/paths.py (sketch)

def resolve(trust: TrustData, field_path: str) -> tuple[bool, object]:
    """Walk a dotted field_path against a TrustData.

    Returns (resolved, value). resolved=False indicates the path no
    longer corresponds to a live attribute (e.g., paralegal removed
    children[0] post-parse); the trace entry is treated as stale and
    filtered from synthesis.

    Supports attribute access (`children`), bracket indexing
    (`children[0]`), and the chain (`children[0].full_legal_name`).
    """
```

This helper is small but reusable: it serves trace-driven Diagnostic synthesis (§5.8) and any future feature that needs to map field_path strings to TrustData values. Stale-path handling at synthesis time is a load-bearing correctness property — without it, a paralegal-removed beneficiary leaves an orphan extraction diagnostic that cannot clear.

### 5.8 Trace-driven Diagnostic synthesis

The diagnostics engine has two diagnostic-emission sources after this spec lands:

1. **Rule-driven (existing).** YAML-defined `DiagnosticRule` evaluated by the rule-engine library against `eval_context`. One rule emits zero or one Diagnostic per call. Suitable for properties of `TrustData` as a whole.
2. **Trace-driven (new).** `synthesize_extraction_diagnostics(trust, extraction)` walks the trace and emits Diagnostic instances for each unverified, illegible-or-low-confidence FieldExtraction whose `field_path` resolves against `trust`. One trace emits zero or many Diagnostics per call.

This split is a deliberate architectural seam, not a workaround. The rule-engine library evaluates one expression against one context dict and has no per-list-element fan-out; expressing per-field extraction concerns as YAML rules would force per-field rule definitions (brittle) or generic summary booleans (loses paralegal-actionable detail). Synthesizing in-engine sidesteps the library shape rather than fighting it. Future Diagnostic-emitting features choose which side they live on; the spec records this seam so the choice is explicit.

`synthesize_extraction_diagnostics` shape:

```python
# src/trust_generator/v3/extraction/synthesis.py (sketch)

def synthesize_extraction_diagnostics(
    trust: TrustData,
    extraction: ExtractionTrace | None,
) -> list[Diagnostic]:
    """Emit one Diagnostic per unverified, problematic FieldExtraction
    whose field_path resolves against `trust`.

    Returns [] when `extraction is None`. Stale entries (field_path
    does not resolve) are silently skipped — they correspond to
    TrustData edits that already removed the field, so the user-visible
    concern is gone.
    """
```

The function emits Diagnostics with `source=DiagnosticSource.EXTRACTION` and a code drawn from the new `extraction.*` namespace (specific codes in §7.7). Both rule-driven and trace-driven Diagnostics merge into one `list[Diagnostic]` returned by `diagnose()`.

**Merge order.** Trace-driven Diagnostics emit first, then rule-driven (`builtin_load_order`, `custom_load_order` per existing spec §5.1). Extraction concerns are pre-validation in lifecycle terms — surfacing them before rule-driven diagnostics matches the natural review order.

### 5.9 The `extraction` namespace in `eval_context`

`build_eval_context` gains an `extraction: ExtractionTrace | None` parameter. When present, it dumps to the eval context under the `extraction` namespace; when absent, the namespace is omitted. Rule expressions referencing `extraction.*` MUST guard with `extraction != null and ...` to avoid `engine.symbol_unknown` meta-diagnostics on non-OCR'd trusts. This pattern matches how `estate.crossed_cliff` already guards (`trust.elections.estate_value_approximate != null and ...`).

The namespace is added to `loader._build_rule_context()`'s type resolver as `rule_engine.DataType.UNDEFINED`, parallel to `trust` and `firm`. This enables firm-side YAML rules to reference trace state without code changes — useful for any future declarative checks that read trace summary state (e.g., "fail if more than 30% of fields are unverified").

### 5.10 Verify lifecycle

A paralegal verifies a field by calling `trace.verify_field(path)`. The mutation is in-memory; persistence is consumer-layer (the GUI or CLI persists the modified trace alongside its TrustData, however its persistence story is wired).

`force_generation()` and verify are intentionally distinct actions:

| Aspect              | Verify                                                         | Override (`force_generation`)                                           |
| ------------------- | -------------------------------------------------------------- | ----------------------------------------------------------------------- |
| Granularity         | Per field                                                      | Per generation event (across all surviving Diagnostics)                 |
| Audit               | None at v3.0 (in-memory mutation; persistence via consumer)    | JSONL audit record per call (existing `force_generation`)               |
| Friction            | Low (single verb, no reason required)                          | High (≥10-character reason, validated)                                  |
| Common-case         | Many per session                                               | Rare                                                                    |
| Effect on `diagnose()` | Filtered out of subsequent synthesis (verified=True skip)   | Diagnostics still emit; override allows generation to proceed anyway    |

A field can be both verified and overridden: a paralegal who verifies a field's transcription still might invoke `force_generation()` on remaining schema or business-rule diagnostics. The two paths are independent.

## 6. TDD construction order

Each cycle is a contained red→green progression. The refactor leg is included only where genuinely warranted (per project spec: refactor cycles are not forced).

### 6.1 Cycle 1 — marker classes and `INCOMPLETE` sentinel

**Red.**

- Test: `IncompleteUntilValidated` and `RawSelfReport` exist and are importable from `trust_generator.v3.extraction.markers`.
- Test: each marker has a non-empty `__doc__` describing its contract.
- Test: `INCOMPLETE` exists and is importable from `trust_generator.v3.extraction.trace`; identity-distinct from `None`, `0`, `""`, and `()`.

**Green.**

- Implement `markers.py` with both classes (no behavior, just docstrings).
- Implement `INCOMPLETE = object()` at module scope of `trace.py`.

No refactor cycle — surface is too small to warrant one.

### 6.2 Cycle 2 — `FieldExtraction`, `ExtractionTrace`, `ExtractionResult`

**Red.**

- Test: `FieldExtraction` accepts the documented field set; rejects unknown fields (`extra='forbid'`).
- Test: `FieldExtraction` enforces invariant — `illegible=True` with non-None `normalized_value` is rejected by a model validator.
- Test: `FieldExtraction` accepts `INCOMPLETE` as `normalized_value` and identity-survives in-memory: `field.normalized_value is INCOMPLETE`.
- Test: `ExtractionTrace.verify_field('children[0].full_legal_name')` mutates the matching FieldExtraction's `verified` and `verified_at` fields and only those.
- Test: `ExtractionTrace.verify_field` raises `KeyError` for a missing `field_path`.
- Test: `ExtractionTrace.verify_field` raises `ValueError` if duplicate `field_path` entries exist (data-integrity invariant).
- Test: `ExtractionResult` requires both `data` and `trace`.

**Green.**

- Implement `trace.py` per §5.3 sketch.
- Implement `verify_field` per the docstring contract.

**Refactor.**

- No refactor. The persistence question — whether `INCOMPLETE` survives `model_dump_json` round-trips — is deferred to the consumer-layer persistence session (see §13.3) where the serialization contract for the trace is defined as a whole. v3.0 keeps `INCOMPLETE` as an in-memory sentinel only.

### 6.3 Cycle 3 — Path resolution helper

**Red.**

- Test: `resolve(trust, 'children')` returns `(True, list_of_children)`.
- Test: `resolve(trust, 'children[0].full_legal_name')` returns `(True, the_name)` for a populated list.
- Test: `resolve(trust, 'children[5].full_legal_name')` returns `(False, _)` when the index is out of range.
- Test: `resolve(trust, 'children[0].nonexistent_attr')` returns `(False, _)`.
- Test: `resolve(trust, 'office.file_number')` resolves nested attribute access.
- Test: pathological inputs (empty string, malformed bracket, trailing dot) return `(False, _)` rather than raising.

**Green.**

- Implement `paths.resolve` as a small parser-walker over `field_path`.

**Refactor.**

- If the resolver grows to support write-paths or partial-resolution returns (out of scope for v3.0), refactor into a `Resolver` class. v3.0 ships the function form.

### 6.4 Cycle 4 — Generation envelope schema and field-order discipline test

This cycle pins the load-bearing constrained-decoding contract. The test suite must catch a future contributor reordering schema fields or removing the reasoning channel.

**Red.**

- Test: import `GenerationEnvelope` from `ollama_backend`; the class is a Pydantic BaseModel.
- Test: `GenerationEnvelope.model_json_schema()` lists fields in this declaration order: `reasoning` first, then `data`, then any auxiliary diagnostics fields. Use `list((schema['properties']).keys())` for a deterministic comparison.
- Test: `reasoning` has a `maxLength` (concrete numeric value pinned, e.g., 2000 characters as ~500-token proxy).
- Test: the schema validates a sample envelope JSON the suite constructs.

**Green.**

- Implement `GenerationEnvelope` in `ollama_backend.py` with `reasoning: str = Field(max_length=2000)` first, then nested data fields modeled after the relevant TrustData subset, then per-field illegibility/note structure.
- The exact data-fields shape is a sub-question covered in §7.3.

**Refactor.**

- The envelope schema is structurally unique to OCR generation; it does not generalize. No refactor.

### 6.5 Cycle 5 — `OllamaBackend.extract`, the happy path

**Red.**

- Test: `OllamaBackend(model='test')` satisfies `ExtractionProtocol` structurally (assert via static type narrowing in a typed test helper, since `@runtime_checkable` is not applied — see §5.4).
- Test: `OllamaBackend(model='qwen2.5vl:7b').trace_returned.backend_id` matches the `<backend>:<model>` convention (`'ollama:qwen2.5vl:7b'`).
- Test: with a mocked `ollama.Client.chat` returning a known envelope JSON, `backend.extract(Path('fake.png'))` returns an `ExtractionResult` whose `data` is the expected TrustData and whose `trace.fields` reflects the mocked envelope.
- Test: the chat call is invoked with `format=GenerationEnvelope.model_json_schema()` and `options={'temperature': 0}`.
- Test: the chat call's `messages[0]['images']` contains the source path as a string (the backend converts `Path` to `str` per §7.6).

**Green.**

- Implement `extract` per §7 (image loading via `Path`, prompt construction, ollama call, envelope parsing, mapping to TrustData + trace).

**Refactor.**

- Extract envelope-to-TrustData mapping to a private function if it grows beyond ~30 lines.

### 6.6 Cycle 6 — `OllamaBackend.extract`, error paths

**Red.**

- Test: `ollama.ResponseError` from `client.chat` raises `ExtractionError` with the `status_code` and `content` propagated.
- Test: a malformed envelope (parses as JSON but fails `GenerationEnvelope.model_validate_json`) raises `ExtractionError` with the underlying ValidationError chained.
- Test: a network/connection error from the underlying `httpx` layer raises `ExtractionError`.
- Test: an envelope with `reasoning` exceeding `max_length` is rejected at envelope-validation time. *(Note: this case should not occur with constrained decoding; the test pins what happens if it does.)*

**Green.**

- Implement the error contract per §7.6.

### 6.7 Cycle 7 — `synthesize_extraction_diagnostics` and stale-path filtering

**Red.**

- Test: empty trace → empty diagnostic list.
- Test: trace with one verified illegible field → empty diagnostic list (verified suppresses).
- Test: trace with one unverified illegible field whose path resolves → one Diagnostic with `source=EXTRACTION` and code `extraction.illegible_field` (proposed code).
- Test: trace with one unverified illegible field whose path no longer resolves against the trust → empty diagnostic list (stale-path filter).
- Test: trace with one unverified field where `confidence_self_report` is below threshold (deferred to 4.3c, but the synthesis branch is structurally present today via `confidence_self_report is not None and below_threshold`) — at v3.0, the branch is unreachable because all entries have `confidence_self_report=None`; the test pins the no-op behavior.
- Test: synthesized Diagnostics have `field_path` matching the FieldExtraction.
- Test: when multiple unverified problematic fields are present, synthesized Diagnostic order matches `trace.fields` insertion order (parser-emission order pin).
- **End-to-end lifecycle test:** construct a trace with one unverified illegible field; call `diagnose(trust, config, extraction=trace)` and assert the resulting list contains the matching `extraction.illegible_field` Diagnostic; call `trace.verify_field(path)`; call `diagnose(...)` again with the same arguments and assert the matching Diagnostic is now absent. Pins the full red→green of the verify lifecycle.

**Green.**

- Implement `synthesize_extraction_diagnostics` per §5.8.

**Refactor.**

- If multiple synthesis criteria accumulate (illegible, low-confidence, unverified-aged) and the function grows past ~50 LOC, refactor into a list of small predicate-emit functions composed by the entry. v3.0 ships the inline form.

### 6.8 Cycle 8 — `diagnose()` integration

**Red.**

- Test: `diagnose(trust, config)` (no extraction) behaves identically to the existing implementation. Regression pin.
- Test: `diagnose(trust, config, extraction=trace)` returns trace-driven Diagnostics first, then rule-driven Diagnostics (merge-order pin).
- Test: `eval_context` includes the `extraction` namespace when extraction is provided; absent otherwise.
- Test: a YAML rule referencing `extraction.fields` evaluates without `engine.symbol_unknown` when extraction is provided AND when the rule guards with `extraction != null and ...`.
- Test: a YAML rule referencing `extraction.fields` without a guard emits `engine.symbol_unknown` when extraction is None — pins the documented behavior.

**Green.**

- Add `extraction: ExtractionTrace | None = None` parameter to `diagnose()`.
- Pass `extraction` to `build_eval_context`.
- Call `synthesize_extraction_diagnostics(trust, extraction)` and prepend to the rule-driven Diagnostics.
- Update `loader._build_rule_context()` to declare `extraction` in the type resolver.

### 6.9 Cycle 9 — Override interaction

**Red.**

- Test: `force_generation(trust, config, [unverified_extraction_diagnostic], reason='...')` writes an audit record listing the extraction diagnostic's code; the test verifies the JSONL line.
- Test: a verified field never produces a diagnostic that reaches `force_generation` (the merge step filters it before the override flow sees it).

**Green.**

- The existing `force_generation` already accepts arbitrary Diagnostics by code. No new code; the test pins the integration.

### 6.10 Cycle 10 — Vision-model invocation (integration)

This cycle requires a live Ollama server with a vision model pulled. Marked `pytest.mark.integration` so it is skipped in CI by default.

**Red.**

- Test: `backend.extract(Path('fixtures/handwriting_sample.png'))` against a live Qwen2.5-VL:7b model returns an `ExtractionResult` whose `trace` has at least one FieldExtraction. Asserts only structural shape, not content (handwriting reading varies).
- Test: against a live model, capture `response.message.content` (the raw JSON string returned by Ollama before envelope validation), parse it as a Python `dict` (Python preserves key insertion order from JSON), and assert that `reasoning` is the FIRST key. This is the integration-level pin for the assumption underlying §7.4: that grammar-constrained decoding generates fields in schema declaration order.

**Green.**

- The implementation is already complete by Cycle 5. This cycle is a smoke test for the live integration plus the integration-level field-order pin.

## 7. OllamaBackend implementation details

### 7.1 Dependency pin

`pyproject.toml` adds `ollama >= 0.6.1`. The pin floor is the version at which `format=Pydantic.model_json_schema()` is reliable and the API for vision-model image input is stable.

The package on PyPI is named `ollama` (NOT `ollama-python`; that is a third-party abandoned package that must not be added). The import name is `ollama`.

### 7.2 Client construction

`OllamaBackend.__init__` defaults to `client=ollama.Client()` (connects to `http://localhost:11434` per the client default). The constructor accepts an injected client to facilitate testing and to allow the consumer to point at a non-local Ollama deployment.

### 7.3 Generation envelope shape

The generation envelope is the Pydantic schema sent as `format=` to constrain model output. It mirrors a TrustData subset adapted for OCR-time concerns:

```python
class FieldDiag(BaseModel):
    """Per-field illegibility/note channel emitted by the model alongside data."""
    illegible: bool = False
    note: str | None = Field(None, max_length=240)


class GrantorEnvelope(BaseModel):
    full_legal_name: str | None = None
    full_legal_name_diag: FieldDiag = Field(default_factory=FieldDiag)
    # ... mirrored for every grantor field ...


class GenerationEnvelope(BaseModel):
    """Constrained-decoding envelope. CRITICAL: `reasoning` MUST be the
    first field — see §7.4."""
    reasoning: str = Field(max_length=2000)
    grantors: list[GrantorEnvelope] = Field(default_factory=list)
    # ... mirrored for every TrustData section the form covers ...
```

The envelope is a flatter, OCR-shaped mirror of TrustData rather than TrustData itself. Two reasons: (a) TrustData fields have computed-property dependencies and validators that are hostile to grammar-constrained decoding; (b) the OCR-time `FieldDiag` channel is alien to TrustData's bounded context. The mapping from envelope to TrustData runs in `_envelope_to_extraction_result` (parser-internal, post-generation).

#### 7.3.1 Envelope-to-TrustData mapping

The envelope's plural-list shape (`grantors: list[GrantorEnvelope]`, `beneficiaries: list[BeneficiaryEnvelope]`) is faithful to what the model sees on the form. The mapper collapses these onto TrustData's singular-grantor + three-list-beneficiary topology:

| Envelope source | TrustData attribute set | `field_path` emitted on the trace |
| --- | --- | --- |
| `envelope.grantors[0].full_legal_name` | `data.grantor.full_legal_name` (singular `GrantorInfo`) | `grantor.full_legal_name` |
| `envelope.grantors[0].date_of_birth` (raw string) | `data.grantor.date_of_birth` (left default; raw kept on the trace, normalization deferred) | `grantor.date_of_birth` |
| `envelope.grantors[1].*` (when present) | `data.co_grantor.*` (after instantiating `data.co_grantor = GrantorInfo()`) | `co_grantor.full_legal_name`, `co_grantor.date_of_birth` |
| `envelope.beneficiaries[i].full_legal_name` | `data.other_beneficiaries[i].full_legal_name` | `other_beneficiaries[i].full_legal_name` |
| `envelope.beneficiaries[i].relationship` (raw string) | `data.other_beneficiaries[i].relationship_other` (free-text fallback; the typed `relationship` enum stays default) | `other_beneficiaries[i].relationship_other` |
| `envelope.beneficiaries[i].share_percent` (raw string) | `data.beneficiary_shares[i]` with `recipient_ref="other_beneficiaries[{i}]"` and `share_percent=Decimal(0)` (default) | `beneficiary_shares[i].share_percent` |

The `field_path` strings use the dotted-attribute convention shared with `Diagnostic.field_path` and resolved via `extraction.paths.resolve` (live `hasattr`/list-index walking against TrustData). Paths that fail to resolve are filtered as stale by the diagnostics integration in plan 9c — so the convention here is load-bearing for OCR data reaching the diagnostic surface.

#### 7.3.2 Beneficiary classification fallback

TrustData has three beneficiary lists (`children`, `descendants`, `other_beneficiaries`) reflecting legal distinctions (a stepchild later adopted by the non-biological parent has `_ChildRelationship.ADOPTED` while `BiologicalParent` retains the original — single-axis collapse loses this). OCR cannot reliably make this classification at the stroke level: the corpus forms in §10 do not provide labeled subsections that disambiguate "child" vs "grandchild" vs "longtime caregiver."

The mapper therefore defaults envelope `beneficiaries[i]` to `other_beneficiaries[i]` — the most permissive list — and surfaces the OCR'd name there. Paralegal review (post-OCR, during fill) reclassifies misplaced rows to `children` or `descendants` as appropriate. This conservative default is observable in the trace via the `field_path` emitted; if the form structure changes to include labeled subsections, the per-form-version mapping is refined explicitly, not by guessing in the OCR. Paralegal reclassification (moving an `other_beneficiaries[i]` row to `children`) is a fill-time concern; the corresponding `beneficiary_shares[i].recipient_ref` rewrite to track the move is a fill-time follow-up flagged by diagnostics, not an OCR concern.

#### 7.3.3 Deferred normalization for non-string TrustData fields

The envelope captures `share_percent` and `date_of_birth` as raw strings (e.g., `"50%"`, `"33-1/3"`, `"March 15, 1958"`). The corresponding TrustData fields are typed `Decimal` and `date | None` respectively. The mapper does NOT attempt to normalize at OCR time:

- TrustData fields are left at their defaults (`Decimal(0)` for `share_percent`, `None` for `date_of_birth`).
- The verbatim string lands on the trace via `FieldExtraction.raw_value`.
- `FieldExtraction.normalized_value` is set to the `INCOMPLETE` sentinel — the type-system enforcement of deferred normalization (the `IncompleteUntilValidated` marker on the field type makes this discipline visible to consumers).
- Plan 9c's diagnostics integration synthesizes an `extraction.no_normalized_value` warning if the field remains unnormalized at verify time (a paralegal-curable signal, not a hard failure).

This preserves the Approach B' commitment: the OCR backend produces faithful data + structurally-rich diagnostics; downstream layers (paralegal review, diagnostics-driven fill UI) own the normalization decisions where ambiguity matters legally.

#### 7.3.4 Validator-fragility coercion

TrustData's `PersonReference._validate_name` requires `full_legal_name` to have ≥2 whitespace-separated tokens *when populated*. An envelope where the model OCRs a single token (e.g., a form section the writer left as `"James"` only) would, if mapped directly to `data.grantor.full_legal_name = "James"`, raise `ValidationError` at TrustData construction — the §7.6 row 3 failure mode (raise `ExtractionError`).

The mapper avoids this by treating the envelope's data-fields as evidence rather than as facts: TrustData is default-constructed (no `full_legal_name` is set on `data.grantor`), the OCR'd value lands on the trace via `FieldExtraction.raw_value`, and paralegal review during fill is responsible for either correcting the value or confirming the form genuinely has only one token. This means the §7.6 row 3 failure mode is reserved for envelope shapes that violate TrustData invariants outside the validator-coercible per-field surface (e.g., a malformed `beneficiary_shares[i]` recipient discriminator) — not for OCR-time transcription drift.

### 7.4 Field-order discipline

Pydantic v2's `model_json_schema()` preserves field declaration order. Grammar-constrained decoding generates fields in schema order. The current best-practice posture for constrained generation is that a string-typed reasoning field declared first lets the model "think aloud" before committing to typed values, mitigating hallucination on illegible inputs. The mechanism (logit-mask sampling against grammar productions traversed in declaration order) makes this structurally plausible, but the magnitude of the benefit is empirical, not contractual. v3.0 adopts the discipline; the §13.2 chore is the evidence-gathering point. The schema field-order test (§6.4) catches accidental regressions; intentional changes require evidence and a cross-reference update in this section.

### 7.5 Multi-page handling and chunked extraction

v3.0 ships single-call extraction. A multi-page intake form handed to `extract()` is presumed to be a single image (or PDF page rasterized externally to an image). If the schema-complexity ceiling under constrained decoding (§13.2 in-flight chore) shows EOF errors on full-form schemas with small models, the chunked-extraction strategy lands as a separate session: `extract` decomposes the source into per-section calls, each with a sub-schema, and the trace merges results. The Protocol surface does not foreclose this — it remains `extract(source) -> result` regardless of internal strategy.

### 7.6 Error contract

`OllamaBackend.extract` converts the input `SourceRef` (a `Path`) to whatever string form the `ollama` client expects when populating `messages[*].images`. The conversion is internal to the backend (`str(path.resolve())`); callers pass `Path` objects; the wire format is the backend's concern.

| Failure                                              | Backend response                                                            |
| ---------------------------------------------------- | --------------------------------------------------------------------------- |
| HTTP-status error from `ollama.Client.chat` (404, 500, etc.) | Raise `ExtractionError`; chain the `ollama.ResponseError` |
| Connection failure (Ollama unreachable)              | Raise `ExtractionError`; chain the Python builtin `ConnectionError`. Note: `ollama-python` catches `httpx.ConnectError` internally and re-raises `ConnectionError` (verified against `ollama/_client.py` lines 134-135); the backend's `except` clause MUST include `ConnectionError`, NOT only `httpx.HTTPError`. |
| Residual transport error (timeout, read/write, protocol) | Raise `ExtractionError`; chain the `httpx.HTTPError` subclass. These pass through `ollama-python` unwrapped. |
| Image path does not exist (or is malformed) | Raise `ExtractionError`; chain the `ValueError`. `ollama-python`'s `Image.serialize_model` raises `ValueError(f'File {value} does not exist')` for missing path-typed image values with recognized extensions (`ollama/_types.py:178-179`); the backend's `except` clause MUST include `ValueError` to wrap this. |
| Model returns malformed JSON                         | Raise `ExtractionError`; chain the `ValidationError`                        |
| Model returns valid envelope but maps to invalid TrustData | Raise `ExtractionError`; chain the TrustData `ValidationError`. Reserved for envelope shapes that violate TrustData invariants outside per-field validator-coercible surface (see §7.3.4); does NOT fire on partial-form OCR transcription drift, since the mapper keeps TrustData default-constructed and surfaces values via the trace. |
| Per-field illegibility on the form                   | NOT a failure: emit FieldExtraction with `illegible=True`, `normalized_value=None` |
| Empty form (no fields legible)                       | NOT a failure: return `ExtractionResult` with empty `trace.fields` and a default-constructed TrustData (caller decides whether to proceed) |

### 7.7 New diagnostic codes

The trace-driven synthesis emits Diagnostics under the new `extraction.*` builtin codes:

| Code                              | Level   | Context | Trigger                                                          |
| --------------------------------- | ------- | ------- | ---------------------------------------------------------------- |
| `extraction.illegible_field`      | warning | both    | `field.illegible == True` and `field.verified == False`           |
| `extraction.low_confidence_field` | info    | both    | `field.confidence_self_report is not None` and below threshold; reserved branch (no v3.0 emission since 4.3c not landed) and `field.verified == False` |
| `extraction.no_normalized_value`  | warning | both    | `field.illegible == False`, `field.normalized_value is None or INCOMPLETE`, and `field.verified == False`. Only fires for *attempted* extractions: the parser does not emit `FieldExtraction` entries for fields absent from the form (per the prompt's omit-if-absent guardrail), so this code surfaces only when the model tried and could not normalize. |

The `context: both` choice is deliberate: extraction concerns matter both during fill review (paralegal workflow) and as a generate-time gate (a field with an unverified low-confidence transcription should block generation until verified or overridden).

These codes coexist with the existing `extraction.placeholder_unfilled` rule. The placeholder rule continues to serve free-text fields where the in-band `[OCR_LOW_CONFIDENCE]` marker is meaningful (the existing `text_blocks.statement_of_intent` field). The OCR backend explicitly does NOT use placeholder markers — the trace is the canonical signal channel for OCR. The placeholder pattern remains for hypothetical free-text uses outside the OCR path.

Two diagnostics may legitimately fire on the same field path if both the trace flags it and a placeholder marker is present in TrustData. This is acceptable: each diagnostic addresses a distinct concern and the paralegal resolution paths differ (verify the trace vs. replace the placeholder). No deduplication is performed.

## 8. Prompt strategy for legal handwritten intake

`prompt.py` builds the user message text. The strategy has three parts:

### 8.1 Role and reading discipline

The prompt assigns the model the role of a careful legal-intake transcriber, not a content interpreter. Three dimensions are emphasized:

1. **Verbatim transcription first.** The model transcribes what is written, not what the writer "meant." If the form says "James William Thompson Jr." the model emits the full string; it does not reformat to "James W. Thompson Jr." or "James Thompson, Jr.". The prompt explicitly forbids normalization in the `raw_value` channel.
2. **Illegibility is first-class.** The model is told that marking a field illegible is preferred over guessing. The schema's `illegible: bool` flag is described as the "I can't read this" channel; the prompt frames it as the legitimate output state for unreadable fields.
3. **Reasoning aloud first.** The prompt instructs the model to use the `reasoning` field (which it sees first in the constrained schema) to walk through what it sees on the form, noting handwriting irregularities, before committing to data fields. This converts the schema's structural ordering into instructional reinforcement.

### 8.2 Domain orientation

The prompt notes the document is a legal trust intake form and references the structural sections it expects (grantors, beneficiaries, real property, personal property, fiduciaries). This domain context constrains the model's interpretive space without committing it to any specific TrustData layout.

### 8.3 Anti-hallucination guardrails

Three guardrails are encoded:

- "If a field is not present on the form at all, omit it from the output (do not invent a default)."
- "If a field is partially filled, transcribe what is there; do not complete it."
- "If multiple readings are plausible, pick the most likely transcription and use the `note` channel to record the ambiguity."

The prompt is short by design — verbose system prompts are noisy under grammar-constrained decoding, where the model's deviation surface is already small.

## 9. Test scenarios summary

(Full enumeration in §6 cycles. This is the list-form summary for navigation.)

| Scenario                                                        | Cycle | Notes                                            |
| --------------------------------------------------------------- | ----- | ------------------------------------------------ |
| Marker classes importable; documented contracts                 | 6.1   |                                                   |
| `INCOMPLETE` sentinel identity                                  | 6.1   |                                                   |
| FieldExtraction shape; illegible-vs-value invariant             | 6.2   |                                                   |
| INCOMPLETE sentinel identity preserved in-memory                | 6.2   | Round-trip serialization deferred to *Trace persistence* chore in §2 |
| ExtractionTrace.verify_field happy path                         | 6.2   |                                                   |
| ExtractionTrace.verify_field error paths                        | 6.2   | Missing path → KeyError; duplicate → ValueError  |
| ExtractionResult requires both data and trace                   | 6.2   |                                                   |
| Path resolver: bracket index, attribute chain, malformed input  | 6.3   |                                                   |
| Generation envelope field order: reasoning first                | 6.4   | Load-bearing test for §7.4                       |
| Generation envelope `reasoning` has max_length                  | 6.4   |                                                   |
| OllamaBackend satisfies ExtractionProtocol structurally          | 6.5   | Static type narrowing (no runtime_checkable)      |
| OllamaBackend.trace.backend_id matches `<backend>:<model>` format | 6.5   | Convention pin                                    |
| OllamaBackend.extract with mocked client returns expected shape | 6.5   |                                                   |
| OllamaBackend.extract calls chat with correct format/options    | 6.5   | Pins format=schema and temperature=0              |
| OllamaBackend.extract image input shape                         | 6.5   | messages[0]['images'] correctness                 |
| OllamaBackend error path: ResponseError → ExtractionError       | 6.6   |                                                   |
| OllamaBackend error path: malformed envelope                    | 6.6   |                                                   |
| OllamaBackend error path: network failure                       | 6.6   |                                                   |
| OllamaBackend error path: oversized reasoning                   | 6.6   | Should not happen under constrained decoding      |
| Synthesis: empty trace → []                                     | 6.7   |                                                   |
| Synthesis: verified illegible suppresses emission               | 6.7   |                                                   |
| Synthesis: unverified illegible emits Diagnostic                | 6.7   |                                                   |
| Synthesis: stale-path filter                                    | 6.7   |                                                   |
| Synthesis: low-confidence branch unreachable in v3.0            | 6.7   | Pin no-op until 4.3c lands                        |
| Synthesis: emission order matches trace.fields insertion order  | 6.7   | Multi-field deterministic ordering                |
| End-to-end verify lifecycle: emit → verify → no re-emit         | 6.7   | Lifecycle pin                                     |
| diagnose() with no extraction is regression-equivalent          | 6.8   |                                                   |
| diagnose() merge order: trace-driven first                      | 6.8   |                                                   |
| diagnose() eval_context includes/omits extraction namespace     | 6.8   |                                                   |
| YAML rule with guard reads extraction without meta-diagnostic   | 6.8   |                                                   |
| YAML rule without guard emits engine.symbol_unknown             | 6.8   | Documented behavior pin                           |
| force_generation accepts extraction-source diagnostics          | 6.9   |                                                   |
| Verified field never reaches override flow                      | 6.9   |                                                   |
| Live vision-model smoke test                                    | 6.10  | `pytest.mark.integration`; opt-in                 |
| Live vision-model JSON-key-order pin (reasoning first)          | 6.10  | `pytest.mark.integration`; integration evidence for §7.4 |

## 10. Public API surface

After this spec lands, the new public surface is:

```python
from trust_generator.v3.extraction import (
    ExtractionProtocol,        # protocol (not runtime-checkable; see §5.4)
    ExtractionResult,          # BaseModel
    ExtractionTrace,           # BaseModel
    FieldExtraction,           # BaseModel
    ExtractionError,           # Exception
    SourceRef,                 # type alias for Path
    INCOMPLETE,                # sentinel
    IncompleteUntilValidated,  # marker class
    RawSelfReport,             # marker class
    OllamaBackend,             # ExtractionProtocol implementation
)

# Updated existing surface in trust_generator.v3.diagnostics:
from trust_generator.v3.diagnostics import diagnose
# diagnose() now accepts: diagnose(trust, config, *, ref_date=None, extraction=None)
```

## 11. Constraint compliance

This spec preserves established v3 architectural commitments:

- **`bounded_context_design`.** TrustData stays validation-uniform. Extraction-layer concerns (illegibility, verification, raw-value provenance) live exclusively on the `ExtractionTrace` sidecar, not on TrustData. The "single model with conditional validation conflating two contexts" anti-pattern that justified the Seed/TrustData split is preserved at this layer too.
- **Diagnostics-engine invariant: "Diagnostics are computed, never stored."** Trace-driven Diagnostics are synthesized fresh in each `diagnose()` call from the current trace state. The trace itself is the *input* to diagnostic computation, not stored Diagnostic instances. The invariant holds.
- **`force_generation` no-user-parameter contract.** Verify is a separate path that does not write to the audit log in v3.0; the existing `force_generation` identity-from-config invariant is unaffected.
- **`python_stack_commitments`.** The `SourceRef = Path` PEP 695 alias is type-checker-visible only; runtime comparisons are by `Path` itself, not by the alias name (per the established commitment that PEP 695 aliases are not runtime classes).

## 12. Migration and amendment to existing specs

The diagnostics-engine spec (`2026-04-23-diagnostics-engine-design.md`) is amended in lockstep:

- §5.1 — `diagnose()` signature gains `extraction: ExtractionTrace | None = None`.
- §5.2 — eval_context shape gains an `extraction` top-level namespace (when provided).
- New subsection §5.X (number to be assigned) — trace-driven Diagnostic synthesis explicitly described as a second emission source alongside rule-driven evaluation; the seam named.
- New subsection §6.X — synthesis cycle added to the construction order (§6.7 of this spec maps into the diagnostics spec's cycle numbering).

The amendments land **as part of this implementation's PR**, not as a separate prior session. Sequencing them as a separate predecessor would create a window during which `diagnose()` has the new signature but no caller exercises it, with no test coverage in between. Landing them together keeps the amendment grounded in working code.

The atomic-amendment-pass approach mirrors the precedent of chore 2 (firm-config A-4/A-5/A-6 amendments), which kept the spec, code, and tests in lockstep within a single change.

## 13. Open questions and known unknowns

1. **Is `model_json_schema()` field order stable across Pydantic v2 minor versions?** Pydantic v2 documents declaration-order preservation; the field-order test (§6.4) is the safety net against silent regressions from a Pydantic upgrade.
2. **How does `OllamaBackend` behave when the Ollama server is unreachable at construction time?** v3.0 defers connection to first call (matches `ollama.Client` default behavior). If pre-flight validation is desirable in a CLI or GUI, the consumer can call `client.list()` to probe.
3. **Does the verify-mutation in-memory model survive concurrent edits?** v3.0 has no concurrency story. The trace mutation is single-threaded; if the consumer (CLI/GUI) introduces concurrency, locking is the consumer's concern.
4. **Should `synthesize_extraction_diagnostics` log when it filters stale entries?** v3.0 silently filters. If observability becomes important (e.g., paralegal complains about a missing flag), structured logging surfaces in a follow-up.

## 14. Plan-review record

The spec was reviewed via `plan-review` (validation_tier: Full, sequentialthinking-backed) before finalization. Findings and resolutions:

| Severity  | Finding                                                                                  | Resolution                                                                                                            |
| --------- | ---------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| Critical  | Reasoning-first claim asserted as established fact without empirical backing             | §7.4 softened to "current best-practice posture"; *Schema complexity ceiling* chore in §2 extended to gather reasoning-omission evidence |
| Critical  | Schema field-order test is unit-only; no integration-level pin                           | §6.10 cycle gains a JSON-key-order test against live model output                                                     |
| Important | Llama 3.2-Vision drop recommendation overweighted (single-source benchmark)              | §4.2 weakened to "consider deprioritizing pending firm-side evaluation"                                               |
| Important | `Path` vs. `str` ambiguity in ollama image input                                         | §7.6 clarifies backend converts `Path` to `str` internally                                                            |
| Important | Verify-vs-TrustData-edit lifecycle interaction undefined                                 | §5.3 docstring clause added: verification bound to value at verify time; mutation does not invalidate                  |
| Important | Re-extraction (multiple `extract()` calls on same source) not addressed                  | §2 out-of-scope expanded                                                                                              |
| Important | Diagnostics-engine spec amendment ordering ambiguous                                     | §12 pins amendments land in same PR as implementation                                                                 |
| Important | Trace persistence contract undefined for consumer layer                                  | *Trace persistence* chore added in §2 (recommendation: `model_dump_json()` round-trip)                                |
| Important | `@runtime_checkable` over-defensive on ExtractionProtocol                                | §5.4 drops decorator; tests adjust to static type narrowing                                                           |
| Important | `context` field on new `extraction.*` codes unspecified                                  | §7.7 pins `context: both` for all three new codes                                                                     |
| Important | End-to-end verify lifecycle test missing                                                 | §6.7 adds explicit emit→verify→no-re-emit lifecycle test                                                              |
| Minor     | `extraction.no_normalized_value` semantics ambiguous (blank-vs-failed)                   | §7.7 clarifies: parser does not emit FieldExtraction for absent fields                                                |
| Minor     | Coexistence with `extraction.placeholder_unfilled` rule unclear                          | §7.7 confirms two diagnostics for two concerns is acceptable; no dedup                                                |
| Minor     | `SourceRef = Path` future-widening prose speculative                                     | §5.4 softened to "the alias is the change site if widening is needed"                                                 |
| Minor     | INCOMPLETE serializer machinery may be premature for v3.0                                | §6.2 defers to *Trace persistence* chore in §2; v3.0 ships in-memory-identity only                                    |
| Minor     | `field_path` convention match between FieldExtraction and Diagnostic not noted           | §5.3 docstring clarified ("the match is deliberate")                                                                  |
| Minor     | Synthesis emission order undefined for multi-field traces                                | §5.3 docstring + §6.7 test pin parser-emission order                                                                  |
| Minor     | `backend_id` format unconvened                                                           | §5.3 docstring + §6.5 test pin `<backend>:<model>` convention                                                         |

No findings invalidated the architecture. The γ.C-with-trace-driven-synthesis design surface survives intact; adjustments are language refinement, lifecycle clauses, test coverage expansion, and disciplined deferrals.

The spec status (header, Field "Status") is "Finalized" pending Zayn's review.
