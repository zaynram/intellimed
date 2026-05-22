# TGv3 AnthropicBackend Design (Session 4.3b)

| Field             | Value                                                                                                                                                                                                                                          |
| ----------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Spec date         | 2026-05-14                                                                                                                                                                                                                                     |
| Status            | Draft                                                                                                                                                                                                                                          |
| Supersedes        | n/a (new backend; sibling to OllamaBackend per 4.3a)                                                                                                                                                                                           |
| Constrained by    | `2026-04-27-ocr-protocol-ollama-design.md` §5.1–§5.4 (the `ExtractionProtocol`, `ExtractionResult`, `ExtractionTrace`, `FieldExtraction` surfaces are fixed contracts here)                                                                     |
| Relevant entities | `bounded_context_design`, `library_selections`, `python_stack_commitments`                                                                                                                                                                     |
| Out of scope      | Adaptive extended-thinking retry (Plan B, separate session); ConfidenceProtocol implementation (Session 4.3c); GUI; persistence transport for the trace artifact (consumer-layer concern); empirical model selection (separate exercise)       |

## 1. Motivation

The 4.3a session shipped a backend-agnostic `ExtractionProtocol` and a single concrete implementation, `OllamaBackend`, against a locally-hosted vision-language model. The Ollama path is a development convenience: it lets the project iterate on schema design, prompt strategy, and the trace contract without per-call API cost. It is **not** the production extraction path. The auto-memory record `project_extraction_backend_split.md` pins this distinction: `OllamaBackend` stays dev-only; the firm-facing pipeline runs against Anthropic's hosted Claude API via an `AnthropicBackend`.

This spec defines that AnthropicBackend. The 4.3a spec explicitly named it (its §2 *Out of scope* line: "AnthropicBackend (Session 4.3b) — the Protocol surface defined here constrains 4.3b but the implementation lives in its own session.") and reserved the `anthropic` prefix in the `backend_id` convention. Plan A — the scope of this spec — produces a production-shaped v1 of the backend: PDF-native input, structured output via Anthropic's tool-use or `output_config` mechanism (the choice is benchmarked at implementation time; `output_config` is the working default — see §8.4), prompt caching on stable inputs, and always-on extended thinking. Plan B (a separate session, deferred) layers adaptive thinking-on-retry on top of this core.

**Primary-source constraint that shapes Plan A.** Anthropic's docs explicitly forbid combining `tool_choice={"type": "tool", ...}` (forced tool emission) with `thinking={"type": "enabled", ...}` (extended thinking). The combination errors at request time. Plan A therefore makes `output_config` the working default mechanism: it composes with extended thinking (subject to a plan-authoring verification step, since the structured-outputs docs are silent on thinking-compat rather than affirming it). `tool_use` remains supported as a fallback mechanism under `tool_choice={"type": "auto"}`; refusal under auto choice is mapped to `ExtractionError` rather than degraded trace (§8.5).

The motivation is not "feature parity with OllamaBackend." OllamaBackend's envelope schema is shaped by llama.cpp grammar-constrained decoding pathologies — reasoning-as-first-field warm-up, integer-keyed dict workarounds, declaration-order pinning. Anthropic's structured-output mechanism has none of these constraints. The Anthropic envelope can be redesigned for its own strengths, the mappers fork, and the trace contract (the boundary the diagnostics engine reads against) stays stable across backends. The trace shape is the project's ubiquitous language between extraction and diagnostics; backend divergence below it is acceptable and expected.

## 2. Scope

### In scope

- `AnthropicBackend` — concrete `ExtractionProtocol` implementation against `anthropic>=<pin>` (pin set at plan authoring time, after verifying current SDK support for PDF document blocks + extended thinking + `cache_control` + chosen output mechanism, **including the `output_config` + `thinking` compatibility check required by §1**).
- `AnthropicGenerationEnvelope` and supporting Pydantic models — the redesigned, Anthropic-shaped tool/response schema. Forked from `GenerationEnvelope`; no shared base.
- Forked mapper functions translating `AnthropicGenerationEnvelope` → `(TrustData, ExtractionTrace)`. Same TrustData target shape and same `FieldExtraction` shape as OllamaBackend; the mappers are forked because the envelope-source shape differs.
- Dual mechanism seam (`_invoke_envelope_call`): `output_config` is the working default (chosen because it composes with extended thinking); `tool_use` is supported as a fallback under `tool_choice="auto"`. The §9.4 benchmark records observations on both; the plan-authoring step pins the default once `output_config` + `thinking` compat is verified against the live API.
- PDF-native input handling. Anthropic's `document` content block accepts base64-encoded PDFs natively (no rasterization step on the project side). Images remain supported via the `image` content block for backwards compatibility with `SourceRef = Path`'s existing scope.
- Page-count and file-size pre-checks against Anthropic's PDF limits, performed locally before any API call (reuses `pypdf` already in deps).
- Prompt caching layout: up to three `cache_control` breakpoints — system prompt, document/image content block, and a reserved-but-unused slot for future few-shot examples. (Whether the `output_config` schema accepts `cache_control` placement is a plan-authoring verification step; see §8.2.)
- Always-on extended thinking (`thinking={"type": "enabled", "budget_tokens": N}`), with the budget exposed as an `AnthropicBackend` constructor argument. Compatibility constraint: tool_use mode runs under `tool_choice="auto"` to satisfy Anthropic's thinking-compat rules.
- `prompt.py` split into a shared coordinator plus backend-specific differentiation modules (`prompt_ollama.py`, `prompt_anthropic.py`). The shared module retains the legal-handwriting domain constants; backend-specific modules assemble final prompts with backend-relevant additions (Anthropic-specific reminders about thinking, PDF document blocks, etc.).
- Error mapping policy: which conditions raise `ExtractionError` vs. degrade to a success-path trace with illegible fields (§8.5 of this spec).
- Refusal handling: `tool_use`-missing-from-response is `ExtractionError`, not a degraded trace.
- Test scenarios: per-field illegibility, schema validation defense-in-depth, refusal, API error mapping, PDF size/page prechecks, prompt-caching call-args assertions, extended-thinking call-args assertion, mechanism-seam parity, Protocol conformance.

### Out of scope (enforced)

- **Adaptive thinking-on-retry (Plan B)** — a separate session will layer a retry policy on top of the always-on baseline shipped here. The retry triggers (illegibility threshold, low-confidence threshold once 4.3c lands, deterministic conditions on trace state), the trace-merge semantics (full re-extraction vs. focused re-prompt vs. critique pass), the cost-cap policy, and the unified-trace shape are all design questions deferred to Plan B. Plan A's design must not preclude Plan B (the construction-injectable `client` and the `_invoke_envelope_call` seam are sufficient retry hooks).
- **ConfidenceProtocol implementation (Session 4.3c)** — this spec drops `overall_confidence` from the envelope and leaves every `FieldExtraction.confidence_self_report=None`, parity with OllamaBackend. 4.3c will define confidence semantics for both backends. Pre-empting 4.3c by emitting raw envelope-level confidence into a new trace slot is rejected in §4 below.
- **Auto-retry on transient API errors** — rate-limit and network failures raise `ExtractionError`; the consumer decides on retries. Auto-retry shares concerns with Plan B (idempotency, cost-cap, trace identity) and waits.
- **Multi-PDF batching across calls** — `extract()` accepts a single `SourceRef` per call (the Protocol contract pinned by 4.3a). Whether a multi-PDF intake packet (e.g., two related forms) decomposes into multiple calls and reconciles is consumer-layer concern.
- **Streaming responses** — the synchronous, non-streaming `messages.create` is used. Streaming is non-breaking to add later if the consumer layer wants progress feedback.
- **Empirical model selection** — the spec names *indicative* models (e.g., Claude Sonnet 4.6 / 4.7 as a reasonable default for legal intake OCR). Empirical validation against firm-side handwriting samples is a separate exercise, mirroring the 4.3a in-flight chore on Ollama model selection.
- **Cost telemetry / spend tracking** — recording per-call cost on the trace, aggregating monthly spend, surfacing cost in the consumer layer, etc. — all consumer-layer concerns. The SDK response carries usage data; the spec does not commit to capturing it.
- **GUI** — display of extraction results, click-to-verify affordances, etc. The spec defines the data-model contract those affordances bind to; rendering belongs to the consumer.

### In-flight chores (post-spec)

- Empirical model commitment (separate chore, post-Plan-A implementation) — pick a default model based on real-intake quality measurement on Anthropic's models.
- Mechanism benchmark (in-plan; not a chore) — the `_invoke_envelope_call` mechanism seam is benchmarked during Plan A implementation. Benchmark fixture set, output log convention, and metrics are described in §9.4.

## 3. Reference Material

Directed at the future Claude Code session composing the implementation plan-md from this spec. Open the listed memory entities, read the listed source files, and treat the listed external references as canonical for SDK-shape questions. Open graph entities via `mcp__memory__open_nodes` with the names below.

### Memory entities

Minimal cross-section of v3 graph nodes whose specifications constrain or inform the AnthropicBackend implementation. Open all before plan authoring.

- `ocr_extraction_design` — Parent design decision. Pins the `ExtractionResult` / `ExtractionTrace` / `FieldExtraction` contract, the parser-variant placement of OCR, the diagnostics seam (rule-driven vs. trace-driven), and the confidence-deferral commitment. AnthropicBackend is a backend implementation under this design; its surfaces are fixed contracts for the plan.
- `bounded_context_design` — Seed-vs-TrustData split that the trace shape respects. The mapper functions produce a TrustData whose validation regime this entity describes.
- `library_selections` — Existing library pin observations (geopy, pydantic-settings, ollama, etc.). Adding the `anthropic` SDK pin observation to this entity is a candidate graph edit raised in the spec session; the plan-md cycle that lands the SDK pin in `pyproject.toml` should also land the observation update.
- `library_reconnaissance_process` — Recon procedure for any further dependency additions surfaced during plan execution (e.g., test-helper libraries).
- `python_stack_commitments` — Python >=3.12, Pydantic v2, stdlib datetime. `AnthropicGenerationEnvelope` and `AnthropicFieldFlag` Pydantic models conform to these conventions.
- `modified_surfaces` — TrustData shape changes. The mappers' target shape (singular grantor, `other_beneficiaries` list, `beneficiary_shares` list) is described here.
- `person_reference_hierarchy` — `GrantorInfo`, `OtherBeneficiary` class lineage. The types the mappers instantiate.
- `party_naming` — grantor/co_grantor positional convention. The mapper's `[0]→grantor`, `[1]→co_grantor` logic mirrors the conventions described here.
- `parser_post_promotion_protocol` — Parser conventions. AnthropicBackend is a parser variant per `ocr_extraction_design` observation 2; the JSON-parser exemption note is the closest analogue to OCR's seed-initialization-bypass posture.
- `parser_coercion_patterns` — Date / Decimal / Address coercion conventions. The mappers handle similar string→typed transitions; the `INCOMPLETE`-sentinel pattern for legible-but-not-yet-normalized is consistent with the deferred-normalization posture described here.
- `diagnostics_design` — Diagnostic code namespace. AnthropicBackend does not add new codes; the `extraction.*` namespace is consumed by `synthesis.py` against the trace AnthropicBackend produces.

### Source files

Read in the order a plan-authoring session would consume them.

**Contracts and fixed surfaces (do not modify):**

- `src/trust_generator/v3/extraction/protocol.py` — `ExtractionProtocol`, `SourceRef`, `ExtractionError`. The class signature contract AnthropicBackend implements.
- `src/trust_generator/v3/extraction/trace.py` — `ExtractionResult`, `ExtractionTrace`, `FieldExtraction`, `INCOMPLETE` sentinel, `_illegible_excludes_normalized_value` invariant validator. The shapes the mappers produce.
- `src/trust_generator/v3/extraction/markers.py` — `RawSelfReport`, `IncompleteUntilValidated` typed annotation markers.
- `src/trust_generator/v3/extraction/paths.py` — `field_path` resolution helpers.
- `src/trust_generator/v3/extraction/synthesis.py` — Diagnostics consumer of the trace. Not modified by this plan; reading it confirms the trace contract AnthropicBackend produces is consumable identically to OllamaBackend's.

**Sibling backend (mirror its shape):**

- `src/trust_generator/v3/extraction/ollama_backend.py` — Single-file backend with envelope + class + mappers. Mirror the structure; do not share helpers.

**Module-split target (will be edited):**

- `src/trust_generator/v3/extraction/prompt.py` — Currently single-file Ollama-aware prompt builder. The plan's first cycle splits this into a shared coordinator plus `prompt_ollama.py` plus `prompt_anthropic.py` (see §4 Architecture).

**Schema (mapper targets):**

- `src/trust_generator/v3/schema.py` — `TrustData`, `GrantorInfo`, `OtherBeneficiary`, `BeneficiaryShare`. The mapper functions populate these types.

**Project config:**

- `pyproject.toml` — Dependency pins. `pypdf>=4` is already present; `anthropic>=<pin>` lands in plan execution. `[tool.pytest.ini_options]` markers config landed via chore #16; the integration smoke depends on it.
- `pixi.toml` — Task surface. `test`, `lint`, `mypy`, `check` are the gates the plan must keep green.

**Tests (patterns to mirror; the AnthropicBackend tests are new files):**

- `tests/v3/extraction/test_ollama_backend.py` — Unit-test patterns (MagicMock client, content-block shape assertions).
- `tests/v3/extraction/test_ollama_backend_integration.py` — Integration smoke convention. Fixture path: `assets/handwriting-samples/pages/print.jpg`. `OCR_SMOKE_FIXTURE_PATH` env-var override. The Anthropic smoke uses its own env-var name (e.g., `ANTHROPIC_SMOKE_FIXTURE_PATH`) and follows the same convention.
- `tests/v3/extraction/conftest.py` — Fixture conventions.

**Parent spec (constrained-by):**

- `docs/superpowers/specs/2026-04-27-ocr-protocol-ollama-design.md` — Defines `ExtractionProtocol`, `ExtractionResult`, `ExtractionTrace`, the `backend_id` convention, the `INCOMPLETE` sentinel semantics, and the §7.3.1 positional-mapping convention this spec relies on.

### External references

SDK-shape claims in this spec (e.g., `messages.create` parameter names, `cache_control` placement, `tool_choice` shape, `thinking` parameter, document content block) are stated to the best knowledge available at spec authoring time. The plan-authoring session should re-verify against Anthropic's current docs before code lands. Canonical roots:

- Anthropic API docs: https://docs.anthropic.com/ — Messages API, prompt caching, extended thinking, tool use, PDF support live under this root. Specific paths drift; treat the table of contents at the root as authoritative.
- Anthropic Python SDK: https://github.com/anthropics/anthropic-sdk-python — pin a version that supports PDF document blocks, extended thinking, prompt caching breakpoints, and the chosen mechanism(s).
- `claude-api` skill (available in this Claude Code installation) — recommended check during plan execution. Its description signals the prompt-caching mandate and migration support across Claude model versions.
- pypdf docs: https://pypdf.readthedocs.io/ — `PdfReader(path).pages` length is the page-count check used in `_load_pdf_or_image`.
- Pydantic v2 docs: https://docs.pydantic.dev/latest/ — `model_validate`, `model_json_schema`, `ConfigDict(extra="forbid")` patterns referenced throughout §6 Public surface.

### Plan-authoring verification gates

Three API-level uncertainties in this spec must be resolved against the live Anthropic API (or current docs) **before** the plan-md commits to cycle scope. Each gate has a stated fallback so plan authoring can proceed regardless of outcome.

1. **`output_config` + extended thinking compatibility** (load-bearing for §1, §6, §8.3, §8.4). The structured-outputs docs are silent on whether `output_config` composes with `thinking={"type": "enabled", ...}`; they neither affirm nor forbid it. Plan-authoring verifies via a smoke call (one PDF fixture, one model). **If compatible:** Plan A ships as designed (`output_config` default, always-on thinking). **If incompatible:** the spec falls back to `tool_use` mode as the Plan A default with thinking opt-in via the constructor budget arg; §2 In-scope's "always-on extended thinking" bullet rewrites accordingly. This gate must clear **during plan-md authoring** — before the plan-md commits to cycle scope, since the verified outcome propagates into cycle 4's ctor default and cycle 12's call-args assertion. Deferring this until just-before-cycle-12 would risk a spec-level rewrite mid-plan if the combination is rejected.

2. **`cache_control` placement on `output_config.format`** (load-bearing for §8.2, §9.1 test 16). The structured-outputs docs note the `output_config.format` parameter participates in the cache key (changing it invalidates the cache) but do not document it as a `cache_control` breakpoint slot. Plan-authoring verifies via experiment whether the API accepts `cache_control={"type": "ephemeral"}` on `output_config.format`. **If accepted:** §8.2 breakpoint 3 applies in `output_config` mode (schema-level caching). **If rejected:** §8.2 relies on breakpoints 1 (system) and 2 (document/image content) only in `output_config` mode; §9.1 test 16 omits the schema-placement assertion for that mode. This gate must clear **during plan-md authoring** — before the plan-md commits to cycle 11's assertion shape.

3. **SDK version covers all four required features** (load-bearing for §5). The `anthropic` Python SDK pin must support: PDF document content blocks, extended thinking, prompt caching with `cache_control` breakpoints, and both `tool_use` and `output_config` structured-output mechanisms. Plan-authoring queries the SDK changelog (or invokes the `claude-api` skill) to identify the lowest version satisfying all four; that version becomes the `pyproject.toml` pin. **Fallback:** if no single SDK version supports all four GA, the pin tracks the latest stable release and the spec's claim of feature coverage degrades to whatever is supported (a structural change to §2 In-scope flagged at plan-md authoring time).

The plan-md should land a small smoke-script artifact (e.g., `tests/data/anthropic_verification_smoke/`) recording each gate's outcome, so future spec or plan amendments can re-check against the same gate text without re-deriving the questions.

## 4. Architecture

```
src/trust_generator/v3/extraction/
├── __init__.py                # export AnthropicBackend
├── protocol.py                # unchanged (4.3a contract)
├── trace.py                   # unchanged (FieldExtraction/ExtractionTrace shape stable)
├── markers.py                 # unchanged
├── paths.py                   # unchanged
├── prompt.py                  # NOW: shared coordinator + legal-handwriting constants
├── prompt_ollama.py           # NEW: Ollama-specific assembly (relocated content from prompt.py)
├── prompt_anthropic.py        # NEW: Anthropic-specific assembly
├── synthesis.py               # unchanged
├── ollama_backend.py          # unchanged
└── anthropic_backend.py       # NEW: envelope + mappers + AnthropicBackend class
```

**Module placement rationale.** `OllamaBackend` is one file containing the envelope schema, the class, and the mappers. `AnthropicBackend` mirrors this layout. The temptation to extract a shared "envelope mapping helper" module is resisted: the mappers are forked deliberately (different envelope source shapes, same TrustData target shape), and shared helpers would couple the backends at exactly the seam this spec chooses to fork.

**Prompt module split rationale.** The current `prompt.py` mixes (a) legal-handwriting domain knowledge that survives backend swaps and (b) Ollama-specific assembly (reasoning-aloud-first instruction, references to the constrained schema's reasoning channel). Splitting reduces coupling: `prompt.py` becomes a coordinator hosting shared constants; `prompt_ollama.py` and `prompt_anthropic.py` each assemble backend-specific final prompts. Existing `build_intake_prompt()` is moved into `prompt_ollama.py` (its current shape is Ollama-aware). A new `prompt_anthropic.build_intake_prompt()` ships alongside.

**Single-fragment prompt strategy.** `prompt_anthropic.build_intake_prompt()` returns a single string consumed as the cacheable system prompt. The user message carries only the document/image content block — no separate per-call text fragment. This keeps the seam (`prompt_builder: Callable[[], str] | None`) one-shot and zero-arg. If the §9.4 benchmark surfaces a need for per-call text variation (e.g., explicit "this is a PDF" cueing improving extraction quality), a later session can extend the seam; Plan A trades that future flexibility for current clarity.

**Trace shape stability.** The 4.3a trace shape (`ExtractionTrace`, `FieldExtraction`) is unchanged by this spec. Both backends produce traces consumable by `synthesis.py` without backend-specific branching. The `ExtractionTrace.backend_id` field already encodes which backend ran (e.g., `anthropic:claude-sonnet-4-6` — naming follows the spec 4.3a §5.3 docstring convention); diagnostic logic does not branch on it.

**No diagnostics engine changes.** `synthesis.py` and `diagnose()` consume the trace via the contract pinned in 4.3a / 9c. AnthropicBackend produces traces that satisfy that contract identically to OllamaBackend. Zero changes to the diagnostics layer.

## 5. Library selections

### `anthropic` (Python SDK)

Pinned at plan authoring time. Minimum version requirements:

- PDF document content block (`{"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": ...}}`).
- Extended thinking (`thinking={"type": "enabled", "budget_tokens": N}`).
- Prompt caching (`cache_control={"type": "ephemeral"}` on system, tools, and content blocks; placement on `output_config.format` is a plan-authoring verification step).
- Tool use with `tool_choice={"type": "auto"}` (forced `{"type": "tool"}` is incompatible with extended thinking per §1).
- `output_config={"format": {"type": "json_schema", "schema": <AnthropicGenerationEnvelope.model_json_schema()>}}` — GA structured-outputs parameter (Anthropic's; not OpenAI's `response_format`). GA support requires Claude Opus 4.5+, Sonnet 4.5+, or Haiku 4.5 (pinned per model selection).

The pin lands in `pyproject.toml` and `pixi.toml` during plan execution, after verifying these features are GA on the target version. The plan authoring step invokes the `claude-api` skill to confirm the current SDK API surface for each feature; the spec does not commit to a specific version number to avoid drift.

### `pypdf` (already a project dependency)

`pyproject.toml` already pins `pypdf>=4`. The page-count pre-check uses `pypdf.PdfReader(path).pages` (or equivalent length). No new dependency.

### No other new dependencies

PDF base64 encoding uses stdlib `base64`. MIME-type detection uses stdlib `mimetypes` augmented by a small allow-list (PDF + supported image types) defined in `anthropic_backend.py`.

## 6. Public surface

### `AnthropicBackend`

```python
class AnthropicBackend:
    """`ExtractionProtocol` implementation backed by Anthropic's Claude API.

    Production-facing extraction backend. Sibling to OllamaBackend
    (dev-only). The two backends produce identical ExtractionTrace
    shapes; mappers and envelope schemas are intentionally forked.

    Always-on extended thinking per Plan A. Adaptive retry is deferred
    to Plan B (a separate session); this class's constructor surface
    is forward-compatible with that addition via the injectable
    `client` parameter.
    """

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None = None,
        client: anthropic.Anthropic | None = None,
        thinking_budget_tokens: int = 5000,
        mechanism: Literal["tool_use", "output_config"] = "output_config",
        prompt_builder: Callable[[], str] | None = None,
    ) -> None:
        """
        Args:
            model: Anthropic model identifier (e.g., "claude-sonnet-4-6").
                No default — the `backend_id` convention requires
                explicit model commitment so traces unambiguously
                identify the producing model.
            api_key: API key. Defaults to ANTHROPIC_API_KEY env var if
                None. Ignored if `client` is provided.
            client: Pre-constructed `anthropic.Anthropic` client. Test
                injection seam. If None, the backend constructs one
                from `api_key`.
            thinking_budget_tokens: Extended-thinking token budget per
                call. Default chosen for production legal-intake OCR
                quality vs. cost; tuned in plan authoring.
            mechanism: Structured-output mechanism. Default
                "output_config" because it composes with extended
                thinking (§1). "tool_use" runs under
                `tool_choice="auto"` as a fallback; the §9.4 benchmark
                may revise the default. Both code paths exercised by
                cycle-5 / cycle-6 unit tests (§7).
            prompt_builder: Custom prompt assembler. Defaults to
                `prompt_anthropic.build_intake_prompt`. Same seam shape
                as OllamaBackend's `prompt_builder` parameter for
                cross-backend consistency.
        """
        ...

    def extract(self, source: SourceRef) -> ExtractionResult:
        """Extract a (TrustData, ExtractionTrace) pair from one source.

        See `ExtractionProtocol.extract` for contract (4.3a §5.4).
        Failure modes raise `ExtractionError`; per-field illegibility
        is a success-path trace entry, not an error.
        """
        ...
```

### `AnthropicGenerationEnvelope` (Pydantic v2)

The tool input / response schema. Anthropic-shaped: no reasoning field (extended thinking handles that channel out-of-band), no per-field numeric confidence (deferred to 4.3c), `illegible` as a bare bool flag paired with each value field.

```python
class AnthropicFieldFlag(BaseModel):
    """Per-field illegibility marker. Bare bool; numeric confidence
    deferred to 4.3c ConfidenceProtocol."""

    model_config = ConfigDict(extra="forbid")

    illegible: bool = False


class AnthropicGrantorEnvelope(BaseModel):
    """Grantor fields + per-field illegibility flags."""

    model_config = ConfigDict(extra="forbid")

    full_legal_name: str | None = None
    full_legal_name_flag: AnthropicFieldFlag = Field(default_factory=AnthropicFieldFlag)
    date_of_birth: str | None = None
    date_of_birth_flag: AnthropicFieldFlag = Field(default_factory=AnthropicFieldFlag)


class AnthropicBeneficiaryEnvelope(BaseModel):
    """Beneficiary fields + per-field illegibility flags."""

    model_config = ConfigDict(extra="forbid")

    full_legal_name: str | None = None
    full_legal_name_flag: AnthropicFieldFlag = Field(default_factory=AnthropicFieldFlag)
    relationship: str | None = None
    relationship_flag: AnthropicFieldFlag = Field(default_factory=AnthropicFieldFlag)
    share_percent: str | None = None
    share_percent_flag: AnthropicFieldFlag = Field(default_factory=AnthropicFieldFlag)


class AnthropicGenerationEnvelope(BaseModel):
    """Top-level Anthropic envelope. No reasoning field, no
    overall_confidence (Plan A); both deferred."""

    model_config = ConfigDict(extra="forbid")

    grantors: list[AnthropicGrantorEnvelope] = Field(default_factory=list)
    beneficiaries: list[AnthropicBeneficiaryEnvelope] = Field(default_factory=list)
```

**Field choices.**

- **`str | None` for value fields**, not `str` with `""`-as-sentinel. The mapper degrades `None` to "field not on form" (omitted from the trace, per the anti-hallucination rule). `""` would be ambiguous.
- **No reasoning field.** Extended thinking carries the reasoning channel. The model emits a `thinking` block in the response that is intentionally not surfaced in the structured output.
- **No `overall_confidence`.** Deferred to 4.3c per §2 *Out of scope*. Both backends ship Plan A with `FieldExtraction.confidence_self_report=None` populated by both mappers.
- **No integer-indexed dicts.** Plain `list[...]`. Anthropic's structured-output mechanism has no GBNF key-order pin to navigate.
- **`AnthropicFieldFlag` as a nested model with a single bool field**, not a bare bool inline. The wrapper is forward-compatible with 4.3c adding per-field signals (confidence, note channel) without changing the parent envelope's schema shape.
- **`extra="forbid"`** at every model level — schema-violation rejection happens at parse time even when server-side validation is in play.

### Forked mappers

Three module-level functions, signatures mirroring OllamaBackend's `_map_grantor_envelope`, `_map_beneficiary_envelope`, `_envelope_to_extraction_result`:

```python
def _map_grantor_anthropic_envelope(
    grantors: list[AnthropicGrantorEnvelope],
) -> tuple[list[FieldExtraction], bool]: ...

def _map_beneficiary_anthropic_envelope(
    beneficiaries: list[AnthropicBeneficiaryEnvelope],
) -> tuple[list[FieldExtraction], list[OtherBeneficiary], list[BeneficiaryShare]]: ...

def _anthropic_envelope_to_extraction_result(
    envelope: AnthropicGenerationEnvelope, *, model: str
) -> ExtractionResult: ...
```

**Positional mapping semantics (mirroring 4.3a §7.3.1).** The `TrustData` schema has `grantor: GrantorInfo` (singular, always present) and `co_grantor: GrantorInfo | None` — not a `grantors` list. The grantor mapper consumes `envelope.grantors` positionally: index 0 → `grantor`, index 1 → `co_grantor`, entries beyond [1] are ignored at this layer. The mapper returns `(fields, needs_co_grantor)`; the composer uses `needs_co_grantor` to decide whether to instantiate `TrustData.co_grantor`. Beneficiaries follow the conservative classification fallback from 4.3a §7.3.2: each envelope beneficiary lands at `other_beneficiaries[j]` plus a paired `beneficiary_shares[j]` with `recipient_ref=f"other_beneficiaries[{j}]"`. The mapper returns `(fields, others, shares)`.

**Composer construction pattern.** The composer default-constructs `TrustData()` (all factories fire), optionally instantiates `co_grantor`, then assigns `other_beneficiaries` and `beneficiary_shares` via attribute mutation — identical to OllamaBackend's `_envelope_to_extraction_result` (`src/trust_generator/v3/extraction/ollama_backend.py:371–387`). Mirroring the Ollama pattern keeps the two backends' composers structurally identical at the call site, simplifying diff-driven review when the schema or mapper conventions evolve.

The composer (`_anthropic_envelope_to_extraction_result`) takes `model: str`, computes `backend_id=f"anthropic:{model}"` internally, generates `extracted_at=datetime.now(UTC)`, invokes both mappers, builds `TrustData`, and returns `ExtractionResult`. Tracking actual API-call latency on the trace is forensic value deferred (a candidate amendment, not Plan A scope).

The mappers' bodies do not share code with OllamaBackend's mappers. The envelope source shape differs (no `*_diag` per-field FieldDiag nested struct; `*_flag` paired with bare-bool `illegible` instead). Shared helpers would carry conditional branches on which envelope flavor they're translating, defeating the forked-mapper decision. Date and numeric normalization remain deferred to the same INCOMPLETE-sentinel pattern as 4.3a (`normalized_value=INCOMPLETE` for legible-but-not-yet-validated values; `normalized_value=None` for illegible — the existing `_illegible_excludes_normalized_value` validator on `FieldExtraction` enforces the invariant identically for both backends).

## 7. Implementation outline

The plan-md derived from this spec is expected to follow these cycles (subject to plan authoring step refinement):

| Cycle | Surface | Red test | Green increment | Refactor? |
|---|---|---|---|---|
| 1a | `prompt.py` refactor (Ollama-side, safety-net cycle) | Existing OllamaBackend test suite stays green after the move; new `prompt_ollama.build_intake_prompt()` returns the existing string | Create `prompt_ollama.py` with `_INTAKE_PROMPT` + `build_intake_prompt` relocated; have `prompt.py` re-export `build_intake_prompt` so OllamaBackend's import path keeps working unchanged | None — pure rename |
| 1b | `prompt_anthropic.build_intake_prompt` | Returns a string containing expected legal-intake instructions and Anthropic-specific reminders (PDF-as-image awareness, no-reasoning-channel-in-schema note) | Implement function | Possibly dedupe shared constants with `prompt_ollama` |
| 2 | `AnthropicGenerationEnvelope` and nested models | Schema round-trip: `model_validate(model_dump())` survives; `extra="forbid"` rejects unknown keys | Implement Pydantic classes | None |
| 3 | Forked mappers | Per-field happy path + illegibility degradation + None-omission; deterministic on a fixture envelope | Implement `_map_*_anthropic_envelope` and `_anthropic_envelope_to_extraction_result` | Possibly factor common FieldExtraction construction within mapper file |
| 4 | `AnthropicBackend.__init__` | Constructor accepts model, api_key, client, thinking_budget_tokens, mechanism (default `"output_config"`), prompt_builder; raises on missing model | Implement | None |
| 5 | `_invoke_envelope_call` seam (tool-use path) | Mocked client returns tool_use block with valid envelope; seam returns dict equal to envelope. Tool_choice is `"auto"` (not forced) — see §1, §8.4 | Implement tool-use branch under tool_choice=auto | None |
| 6 | `_invoke_envelope_call` seam (output_config path) | Mocked client returns text block with JSON matching the schema; seam parses to dict | Implement output_config branch | Factor parsing if duplication emerges |
| 7 | `AnthropicBackend.extract` happy path | End-to-end mocked, parametrized over `mechanism in ("tool_use", "output_config")`: PDF source → envelope → ExtractionResult with correct backend_id and field count. Cycles 5/6 exercise the seam units; this cycle exercises the full `_load_pdf_or_image → _build_* → _invoke_envelope_call → mappers → ExtractionResult` pipeline through both code paths | Wire `_load_pdf_or_image` + `_build_*` + `_invoke_envelope_call` + mappers | Likely yes — `extract` is the integration site |
| 8 | PDF size and page-count prechecks | Oversized PDF (mocked file size) raises ExtractionError; PDF exceeding the context-window-tier page limit (mocked `pypdf`; constant pinned to the chosen model variant's context-window tier — 100 pages for 200K-context models, 600 for 1M-context variants) raises ExtractionError; both raise before any API call | Implement `_load_pdf_or_image` with prechecks | None |
| 9 | Image source acceptance | JPEG/PNG source produces an image content block, not a document block; per-field illegibility flows through identically | Implement image branch in `_load_pdf_or_image` and `_build_user_message` | None |
| 10a | Error mapping: APIConnectionError | Mocked client raises `anthropic.APIConnectionError`; assert ExtractionError wrap with no api_key substring leak | Implement APIConnectionError mapping | None |
| 10b | Error mapping: RateLimitError | Mocked client raises `anthropic.RateLimitError`; assert wrap, no retry attempt | Implement RateLimitError mapping | None |
| 10c | Error mapping: AuthenticationError | Mocked client raises `anthropic.AuthenticationError`; assert wrap, no api_key substring leak | Implement AuthenticationError mapping | None |
| 10d | Error mapping: generic APIError | Mocked client raises a non-specialized `anthropic.APIError`; assert wrap | Implement generic APIError mapping | Factor try/except shape if duplication accrues across 10a–10d |
| 10e | Refusal — tool_use mode under auto choice | Mocked response has no `tool_use` block (stop_reason="end_turn" with text-only content); assert ExtractionError with stop_reason in message | Implement refusal detection in tool_use branch | None |
| 10f | Schema-invalid envelope | Mocked response provides malformed `tool_use.input` or non-JSON `output_config` text; assert ExtractionError wrapping ValidationError / parse failure | Implement defense-in-depth schema-validation error path | None |
| 11 | Prompt caching call-args assertion | Mocked client: assert `cache_control={"type": "ephemeral"}` on the system block and on the document/image content block. Whether `cache_control` is accepted on `output_config.format` is verified at plan-authoring time (see §8.2) and the assertion is conditional on that verification | Implement cache_control placement in message construction | None |
| 12 | Extended thinking call-args assertion | Mocked client: assert `thinking={"type": "enabled", "budget_tokens": <constructor value>}` in the call; assert tool_choice (when present) is `"auto"`, never `{"type": "tool", ...}` | Wire thinking parameter through `messages.create` invocation | None |
| 13a | Mechanism benchmark (measurement task — **not a TDD cycle**) | n/a — this row records observations, not assertions. Run a fixture intake set against both mechanism backings under `pytest.mark.integration`; record latency, total tokens, success rate, refusal rate to `tests/data/anthropic_mechanism_log/`. Commit message records observed numbers; cycle 13b consumes the result | Run benchmark; capture log file(s) | None |
| 13b | Pin mechanism default | Red test: `AnthropicBackend(model="…").mechanism == "<winner>"` (where `<winner>` is read from the 13a log file or the commit message) | Pin the default in `__init__`; commit message cites the 13a log path | None |
| 14 | Protocol conformance | Structural type check: `AnthropicBackend` satisfies `ExtractionProtocol` (mirrors 9b cycle 5 test on OllamaBackend) | None (passes once class is implemented) | None |
| 15 | Live-API smoke (`@pytest.mark.integration`) | Real Anthropic API call against the shared fixture (`assets/handwriting-samples/pages/print.jpg` by default, overridable via env var per the OllamaBackend smoke convention); asserts ExtractionResult, populated grantor, `backend_id` prefix, and token-usage ceiling | Implement integration test scaffolding (env-var-gated API key, env-var-overridable fixture path) | None |

The cycle count (22 rows; 21 TDD cycles with 13a a non-TDD measurement) plausibly splits across two plan-mds; the plan-authoring step decides the cut so that **each split lands a backend that's safe to ship at its endpoint**. Error mapping (10a–10f) must land in the same split as the seam that emits the errors — stopping mid-plan with the seam but not the error wraps would ship a backend that crashes on real-API failure modes. One workable cut: Plan A.1 = cycles 1a, 1b, 2, 3, 4, 5, 6, 7, 10a–10f, 14 (working backend with seams + mappers + error handling + Protocol conformance); Plan A.2 = cycles 8, 9, 11, 12, 13a, 13b, 15 (prechecks, image branch, caching/thinking call-args, benchmark, smoke). Plan authoring will commit.

## 8. Backend internals

### 8.1 Data flow (per-call)

```
AnthropicBackend.extract(source: Path)
  │
  ├── _load_pdf_or_image(source)
  │     ├── mime_type detection (stdlib mimetypes + allow-list)
  │     ├── file-size check (≤ Anthropic PDF limit, e.g., 32MB at SDK pin time)
  │     ├── if PDF: page-count check via pypdf.PdfReader.pages length
  │     │           (≤ context-window-tier limit: 100 pages for
  │     │           200K-context models — incl. the indicative
  │     │           claude-sonnet-4-6 default; 600 pages for 1M-context
  │     │           variants. Constant lives module-level in
  │     │           anthropic_backend.py and is verified at plan authoring)
  │     ├── base64-encode bytes
  │     └── return (mime_type, base64_data)   # page_count discarded
  │                                           # — precheck raises in-flight
  │                                           # if over limit
  │
  ├── _build_system_prompt()  [cacheable]
  │     └── prompt_anthropic.build_intake_prompt()
  │           composes shared constants from prompt.py
  │
  ├── _build_user_message(mime, b64)
  │     ├── if PDF:   content block 1 = {"type": "document",
  │     │                                "source": {"type": "base64",
  │     │                                           "media_type": mime,
  │     │                                           "data": b64},
  │     │                                "cache_control": {"type": "ephemeral"}}
  │     └── if image: content block 1 = {"type": "image", ...same shape,
  │                                      "cache_control": {"type": "ephemeral"}}
  │     # No second text block — all instructions live in the system prompt
  │     # (§4 Prompt module split rationale / single-fragment strategy)
  │
  ├── _invoke_envelope_call(system, user_msg, schema)
  │     │  [tool_use OR output_config — selected by `mechanism`]
  │     │  Both paths pass `thinking={"type": "enabled", "budget_tokens": …}`
  │     │  Both paths use `tool_choice="auto"` (or no tool_choice for
  │     │  output_config mode) — forced tool_choice is incompatible
  │     │  with extended thinking per Anthropic docs.
  │     │
  │     ├── tool_use path:
  │     │     client.messages.create(
  │     │       model=self.model,
  │     │       system=[{"type": "text", "text": system,
  │     │                "cache_control": {"type": "ephemeral"}}],
  │     │       messages=[user_msg],
  │     │       tools=[{"name": "submit_intake_extraction",
  │     │               "description": ...,
  │     │               "input_schema": schema,
  │     │               "cache_control": {"type": "ephemeral"}}],
  │     │       tool_choice={"type": "auto"},  # required for thinking-compat
  │     │       thinking={"type": "enabled",
  │     │                 "budget_tokens": self.thinking_budget_tokens})
  │     │     → locate tool_use block; if missing (refusal under auto),
  │     │       raise ExtractionError; else return tool_use.input as dict
  │     │
  │     └── output_config path:
  │           client.messages.create(
  │             model=..., system=..., messages=...,
  │             output_config={"format": {"type": "json_schema",
  │                                       "schema": schema}},
  │             thinking={"type": "enabled",
  │                       "budget_tokens": self.thinking_budget_tokens})
  │           → locate final text block; json.loads(block.text); return dict
  │
  ├── AnthropicGenerationEnvelope.model_validate(dict)
  │     └── ExtractionError on ValidationError (defense-in-depth)
  │
  ├── _anthropic_envelope_to_extraction_result(envelope, model=self.model)
  │     ├── _map_grantor_anthropic_envelope(envelope.grantors)
  │     │     → (grantor_fields, needs_co_grantor) ;  positional [0]→grantor, [1]→co_grantor
  │     ├── _map_beneficiary_anthropic_envelope(envelope.beneficiaries)
  │     │     → (beneficiary_fields, others, shares)
  │     ├── data = TrustData()                          # default factories fire
  │     │   if needs_co_grantor: data.co_grantor = GrantorInfo()
  │     │   data.other_beneficiaries = others
  │     │   data.beneficiary_shares = shares
  │     │   # Grantor field assignment happens via the field-extraction
  │     │   # apply step (mirrors OllamaBackend's pattern in ollama_backend.py:371–387)
  │     ├── build ExtractionTrace(backend_id=f"anthropic:{model}",
  │     │                         extracted_at=datetime.now(UTC),
  │     │                         fields=grantor_fields + beneficiary_fields)
  │     └── return ExtractionResult(data=data, trace=trace)
  │
  └── return ExtractionResult
```

### 8.2 Prompt caching layout

Anthropic permits up to four `cache_control` breakpoints per request. This spec commits to two active breakpoints with one reserved:

| Breakpoint | What it caches | Stability | Plan A status |
|---|---|---|---|
| 1 | System prompt block | Stable per firm (changes only on prompt updates) | Active |
| 2 | Document/image content block | Stable across retries of the same intake; cache-key changes per intake but the SDK still benefits when retries occur within TTL | Active |
| 3 | Tools array (tool_use mode); placement on `output_config.format` is **unverified** against primary docs and gated on a plan-authoring check (see below) | Stable per backend version | Conditional on tool_use mode + plan-authoring verification |
| 4 | *Reserved for few-shot examples* | Stable per firm once populated | Reserved; not used in Plan A |

The PDF/image content block is the per-call payload but `cache_control={"type": "ephemeral"}` on it still helps when the consumer layer retries the same source within the TTL window. Anthropic's PDF-support docs explicitly support this placement.

**Output_config + cache_control verification.** The structured-outputs docs note that changing the `output_config.format` parameter invalidates the prompt cache for the conversation thread — consistent with the format participating in the cache key, but **not** with the format being a `cache_control` breakpoint slot. The plan-authoring step verifies via experiment whether the API accepts `cache_control` on `output_config.format`. If yes, breakpoint 3 in `output_config` mode caches the schema. If no, Plan A relies on breakpoints 1 and 2 only under `output_config` mode; the third slot remains reserved.

**Why reserve the third breakpoint.** Once a firm has 5–15 representative tagged intake forms, prepending them as a few-shot block — marked `cache_control={"type": "ephemeral"}` — is the canonical Claude-cookbook way to improve extraction quality without per-call cost beyond the one-time cache write. Plan A does not ship this, but the cache layout shouldn't preclude it. A later session can populate the slot without forcing a cache-key shuffle that invalidates the system / tools cache.

### 8.3 Extended thinking

Always-on per Plan A. The `thinking` parameter is set unconditionally on every `messages.create` call with `budget_tokens=self.thinking_budget_tokens`. The default budget is committed in plan authoring (a 5,000-token budget is the working starting point; benchmark may revise).

**Tool_choice compatibility constraint.** Extended thinking is incompatible with forced `tool_choice` (`{"type": "tool", ...}` or `{"type": "any"}`). Plan A handles this by:
- Using `output_config` mode as the default (no `tool_choice` parameter required).
- Running tool_use mode under `tool_choice={"type": "auto"}` when invoked as a fallback. Refusal under auto choice is rare on legal-intake content (it is not adversarial), but possible; §8.5 maps the case to `ExtractionError`.

The thinking block in the response is **not** surfaced in the trace. It is read implicitly via the structured output: the model's improved transcription quality is the only signal that thinking did anything. Recording thinking content for forensic value is a candidate for a separate session (it interacts with retention/privacy concerns the firm has not yet specified).

Plan B's adaptive variant — first call without thinking, second call with thinking if trace state warrants — depends on a confidence or illegibility signal that Plan A does not emit (envelope-level confidence was rejected per §2). Plan B will define the trigger; until then, always-on is the durable behavior. The `output_config` mode keeps adaptive-thinking-on-retry composable: thinking can flip per call without changing mechanism or `tool_choice`.

### 8.4 Mechanism seam — tool_use vs. output_config

A single internal seam, `AnthropicBackend._invoke_envelope_call(system: str, user_msg: dict, schema: dict) -> dict`, abstracts the choice. The `system` and `user_msg` parameters mirror the Anthropic API's split (system is a top-level kwarg; the user message is a content-block-bearing message dict). Both mechanisms produce a `dict` matching the envelope schema; downstream parsing/validation/mapping is unchanged.

| Property | `tool_use` | `output_config` |
|---|---|---|
| API call shape | `tools=[{name, input_schema, cache_control}]` + `tool_choice={"type": "auto"}` | `output_config={"format": {"type": "json_schema", "schema": ...}}` |
| Response shape | A `tool_use` content block (when emitted); the `input` field is the parsed dict | A text content block whose `.text` parses to JSON |
| Schema validation | Server-side; malformed `tool_use.input` rejected by API | Server-side; malformed JSON rejected by API |
| Extended thinking compatibility | **Compatible only under `tool_choice="auto"`** — forced `tool_choice={"type": "tool", ...}` errors per Anthropic docs ([extended-thinking](https://platform.claude.com/docs/en/build-with-claude/extended-thinking)) | **Plan-authoring verifies before cycle 12 lands** — docs are silent on the combination rather than affirming it ([structured-outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)) |
| Prompt caching | `cache_control` on tools array is documented and supported | `cache_control` on `output_config.format` is **unverified** against primary docs; plan-authoring verifies (see §8.2) |
| Refusal handling | Under auto choice, refusal produces stop_reason="end_turn" with no tool_use block — mapped to `ExtractionError` (§8.5). Legal-intake content is non-adversarial; refusal is rare in practice but plausible | JSON parse failure or empty text on refusal — also mapped to `ExtractionError` |
| Cookbook coverage | High (Claude cookbook + partner integrations + Anthropic docs); auto-choice usage is the default cookbook pattern | Lower (newer GA surface; less corpus) |
| Test mock complexity | Tool-use blocks have a specific content-block shape | Text + JSON parsing is more straightforward |

**Decision: `output_config` is the working default, benchmarked alongside `tool_use`.** The thinking-compat constraint (§1, §8.3) pushes `output_config` to default: it composes cleanly with extended thinking without the `tool_choice="auto"` refusal-rate residual that tool_use mode carries. The §9.4 benchmark records observations on both mechanisms — the comparison is necessarily asymmetric (output_config gets thinking unconditionally; tool_use gets thinking only under auto choice and accepts a residual refusal-rate risk) and the benchmark log documents this asymmetry explicitly. The plan's cycle 13b pins the default after benchmark observations, with `output_config` as the prior.

**Why keep both behind the seam.** The `output_config + thinking` compatibility is *plausibly-supported, not docs-affirmed*. If the plan-authoring verification shows the combination is in fact rejected by the API, the spec falls back to: `tool_use` becomes the Plan A default, thinking switches to opt-in via the constructor budget arg (a follow-up edit gated on that finding). Keeping both code paths behind the seam preserves this optionality without a structural rewrite.

### 8.5 Error mapping policy

| Condition | Site of detection | Outcome |
|---|---|---|
| Source path does not exist | `_load_pdf_or_image` | `ExtractionError("source path not found: <path>")` |
| Source is neither PDF nor a supported image MIME | `_load_pdf_or_image` | `ExtractionError("unsupported source mime-type: <mime>")` |
| PDF exceeds Anthropic file-size limit | `_load_pdf_or_image` | `ExtractionError("PDF exceeds Anthropic file-size limit (<n>MB)")` |
| PDF exceeds Anthropic page-count limit | `_load_pdf_or_image` | `ExtractionError("PDF exceeds Anthropic page limit (got <n>)")` |
| `anthropic.APIConnectionError` / timeout | `_invoke_envelope_call` | `ExtractionError` wrapping the cause |
| `anthropic.RateLimitError` (HTTP 429) | `_invoke_envelope_call` | `ExtractionError` wrapping; **no auto-retry in v1** |
| `anthropic.AuthenticationError` / `PermissionDeniedError` | `_invoke_envelope_call` | `ExtractionError` wrapping |
| Other `anthropic.APIError` subclasses | `_invoke_envelope_call` | `ExtractionError` wrapping |
| Refusal: response has no `tool_use` block under `tool_choice="auto"` (tool_use mode) | `_invoke_envelope_call` | `ExtractionError("model did not emit submit_intake_extraction tool_use: stop_reason=<n>")` |
| Refusal: `output_config` mode produces text that does not parse as JSON | `_invoke_envelope_call` | `ExtractionError("output_config JSON parse failure: <head>")` |
| Schema-invalid envelope (defense-in-depth) | `AnthropicGenerationEnvelope.model_validate` | `ExtractionError` wrapping `ValidationError` |
| Per-field `illegible=True` in envelope | mapper | **Success path** — `FieldExtraction.illegible=True`, `normalized_value=None` |
| Per-field value is `None` (omitted by model) | mapper | **Success path** — field omitted from trace; not a `FieldExtraction` entry |
| Date string fails ISO parse during mapper validation | mapper | **Success path** — degrade to `illegible=True`, `normalized_value=None` |
| Numeric string fails parse during mapper validation | mapper | **Success path** — `normalized_value=INCOMPLETE` if mapper defers numeric normalization (consistent with OllamaBackend) |

**Refusal as hard error.** `tool_choice="auto"` (required for thinking-compat in tool_use mode) permits refusal-as-prose; legal-intake content is non-adversarial so refusal is rare in practice but plausible. A response without the expected structured output — under either mechanism — is a contract violation, not a partial extraction; raising `ExtractionError` lets the consumer layer route the situation appropriately. Returning a trace with every field illegible would lie about what happened.

**No auto-retry.** Rate-limit and network errors raise. Auto-retry interacts with idempotency (re-running OCR isn't side-effect free if it incurs cost), cost budgeting, and trace identity (does a retry produce one trace or many?). Plan B will tackle related questions; until then, retry policy lives in the consumer layer.

**`ExtractionError` message hygiene.** When wrapping SDK exceptions, the wrapped message preserves the cause's class name and a sanitized excerpt — but MUST NOT serialize request headers, authentication context, or the full `repr()` of the cause object. Cycle 10a–10d tests assert that the wrapped error string does not contain the api_key substring. Treat the `ExtractionError` message as user-visible (it can land in logs the firm administrator reads); the original cause stays available through `__cause__` for debug-time inspection.

## 9. Testing

### 9.1 Unit tests (`tests/v3/extraction/test_anthropic_backend.py`)

Default-run on `pixi run check`. All tests mock `anthropic.Anthropic`; zero live API calls.

*Catalog convention.* The tests are grouped by topic (happy path → mapping → refusal → prechecks → API errors → call-args → conformance), not by §7 cycle order. The cycle column in §7's table is the authoritative test→cycle mapping; the plan-md authoring step pairs catalog entries to cycles.

1. **Happy path — tool_use mode (under `tool_choice="auto"`).** Mocked client returns a content block list with a `tool_use` block whose `input` parses cleanly. Assert: `ExtractionResult` returned; `TrustData.grantor.full_legal_name` populated from `envelope.grantors[0]` per the positional mapping; `ExtractionTrace.backend_id == f"anthropic:{model}"`; one `FieldExtraction` entry per non-None envelope field (entries are emitted only when the source value is non-None or `illegible=True`, mirroring the OllamaBackend mapper's conditional-emit pattern).
2. **Happy path — output_config mode.** Parallel test against the output_config branch of the seam.
3. **Per-field illegibility degradation.** Envelope contains `full_legal_name_flag.illegible=True`. Assert: matching `FieldExtraction.illegible=True`, `normalized_value=None`, invariant satisfied.
4. **Per-field None omission.** Envelope contains `full_legal_name=None`. Assert: no FieldExtraction emitted for that path; mapper omits, does not synthesize a placeholder.
5. **Date parse degradation.** Envelope contains a malformed date string. Assert: mapper degrades to `illegible=True`, `normalized_value=None`.
6. **Numeric INCOMPLETE.** Envelope contains a legible share_percent like `"50"`. Assert: `FieldExtraction.normalized_value is INCOMPLETE` (consistent with OllamaBackend's deferred numeric normalization).
7. **Refusal — tool_use mode under auto choice.** Mocked response has no `tool_use` block (`stop_reason="end_turn"` with text-only content). Assert: `ExtractionError` raised with `stop_reason` in message; api_key substring not present in message.
8. **Refusal — output_config mode.** Mocked response text is non-JSON prose. Assert: `ExtractionError` raised.
9. **Schema-invalid envelope.** Mocked response provides malformed `tool_use.input`. Assert: `ExtractionError` wrapping `ValidationError`.
10. **PDF size precheck.** Mocked filesystem with a PDF exceeding limit. Assert: `ExtractionError` raised **before** `client.messages.create` is invoked.
11. **PDF page-count precheck.** Mocked `pypdf.PdfReader` returns more pages than the context-window-tier limit (100 pages for 200K-context variants; 600 for 1M-context variants). Assert: `ExtractionError` raised before API call.
12. **Image source acceptance.** PNG fixture. Assert: API call constructed with an `image` content block, not `document`.
13. **APIConnectionError mapping.** Mocked client raises. Assert: `ExtractionError` wraps cause; api_key substring not present in error message.
14. **RateLimitError mapping.** Mocked client raises. Assert: wrapping; no retry attempted.
15. **AuthenticationError mapping.** Mocked client raises. Assert: wrapping; api_key substring not present.
16. **Prompt caching presence.** Inspect captured `messages.create` kwargs. Assert: `cache_control={"type": "ephemeral"}` on the system block and on the PDF/image content block (per §8.2 breakpoints 1 and 2). In tool_use mode, also assert `cache_control` on the tools array entry. In `output_config` mode, the schema-placement assertion is gated on the plan-authoring verification step (see §8.2); if verification confirms support, add the assertion; otherwise, omit it for this mode.
17. **Extended thinking presence.** Inspect captured kwargs. Assert: `thinking={"type": "enabled", "budget_tokens": <constructor value>}` on every call regardless of mechanism.
18. **`tool_choice` shape (tool_use mode).** Inspect captured kwargs. Assert: `tool_choice == {"type": "auto"}`; assert the kwargs do **not** contain `tool_choice={"type": "tool", ...}` or `{"type": "any"}` (would violate the thinking-compat constraint and produce an API-side error).
19. **Protocol conformance.** Static type check that `AnthropicBackend` matches `ExtractionProtocol` (mirrors 4.3a 9b cycle 5 OllamaBackend test).

The 19 tests collapse to fewer Red→Green cycles in plan authoring per §7's cycle table — many catalog entries are assertions on the same mocked call and pair into a single cycle.

### 9.2 Integration smoke (`tests/v3/extraction/test_anthropic_backend_integration.py`)

Marked `@pytest.mark.integration`. Opt-in via `pixi run test -m integration` per the pyproject.toml config landed in chore #16. **Requires** `ANTHROPIC_API_KEY` env var; absent key skips the test with a clear message.

1. **Real-API single-page intake.** Default fixture path follows the OllamaBackend smoke convention: `assets/handwriting-samples/pages/print.jpg` (synthetic-persona handwriting sample, already committed alongside `cursive.jpg`, `all-caps.jpg`, `hurried.jpg` per the BASELINE.md adjacent). The default fixture is a JPG, so the smoke exercises AnthropicBackend's image-content-block branch by default. The default fixture path is overridable via an env var (mirroring `OCR_SMOKE_FIXTURE_PATH`; the Anthropic smoke uses its own env-var name, e.g., `ANTHROPIC_SMOKE_FIXTURE_PATH`, decided in plan execution) so PDF coverage can be added once a representative PDF fixture is committed. Invoke the real Anthropic API. Assert:
   - `ExtractionResult` returned.
   - `TrustData.grantor.full_legal_name` is non-empty (singular grantor per 4.3a §7.3.1 positional mapping).
   - `trace.backend_id` starts with `"anthropic:"`.
   - `trace.fields` contains at least one entry under the `grantor.` path prefix.
   - Token usage from the SDK response stays under a per-fixture sanity ceiling (calibrated during plan execution; e.g., 50k total tokens for a single-page form). The ceiling catches prompt-regression bloat in CI runs.

The smoke covers both mechanisms once: the test is parametrized over `mechanism in ("tool_use", "output_config")`.

### 9.3 Mocking patterns

`_make_mock_tool_use_response(envelope: dict) -> anthropic.types.Message` and `_make_mock_text_response(json_text: str) -> anthropic.types.Message` test helpers, both module-local in `test_anthropic_backend.py`. They return real SDK response types so the test exercises actual block-extraction logic instead of a duck-typed shim.

The `anthropic.Anthropic` mock is constructed with `MagicMock(spec=anthropic.Anthropic)` and its `.messages.create` attribute is configured per test. This catches typos in the SDK surface (e.g., a future SDK rename of `create` would fail the spec check).

### 9.4 Mechanism benchmark (cycle 13a measurement → cycle 13b pin)

A small benchmark — same shape as plan #14's envelope-complexity-ceiling exercise — runs both mechanisms against a fixture intake set and logs metrics for the plan's Green phase to commit a winner.

Output convention: `tests/data/anthropic_mechanism_log/YYYY-MM-DD-<run-id>.json`, structured as a list of trial records:

```json
{
  "run_id": "...",
  "fixture": "tests/data/...",
  "mechanism": "tool_use" | "output_config",
  "model": "claude-...",
  "thinking_budget_tokens": 5000,
  "latency_seconds": <float>,
  "input_tokens": <int>,
  "output_tokens": <int>,
  "thinking_tokens": <int>,
  "cache_read_input_tokens": <int>,
  "cache_creation_input_tokens": <int>,
  "success": true | false,
  "refusal": true | false,
  "schema_valid": true | false,
  "trace_field_count": <int>
}
```

The benchmark runs each mechanism against each fixture at least three times (cache-warmed) to capture variance, then aggregates into per-mechanism mean ± stdev. Cycle 13a (the benchmark task — not a TDD cycle) emits the log file(s); cycle 13b (a Red→Green cycle) pins the chosen `mechanism` default in `AnthropicBackend.__init__`. The cycle 13b commit message records the decision rationale and cites the 13a log path (analogous to plan #14's qwen2.5vl ceiling commit shape).

**Asymmetry note.** Per §8.4, the benchmark is necessarily asymmetric: `output_config` runs with extended thinking unconditionally, while `tool_use` runs under `tool_choice="auto"` with thinking and accepts a residual refusal-rate risk. The log records both the success-rate and refusal-rate columns so the decision can weigh the asymmetric quality picture rather than assuming like-for-like.

## 10. Open questions / future work

### Plan B — Adaptive thinking-on-retry

Scope locked for a future session, not specced here:

- **Trigger.** What trace state fires a retry? Plan A doesn't emit confidence, so the trigger candidates are: illegibility ratio above threshold; specific high-value fields illegible (e.g., grantor name); zero-grantor extraction. Plan B will pick.
- **Retry shape.** Full re-extraction with thinking? Focused re-prompt for the uncertain fields? Critique-pass on the original extraction? Each has different cost and design implications.
- **Trace merge semantics.** Two passes, one result. Which pass's field wins per `field_path`? Are both retained? How is the trace shape extended (without breaking 4.3a's contract)?
- **Cost cap.** Strict one-retry-only, or escalating-budget retry until quality threshold? Interaction with 4.3c confidence-based stopping.
- **Behavior parity.** OllamaBackend has no analogous mechanism. Does Plan B introduce a `RetryProtocol` that wraps any backend? Or stay Anthropic-specific?

### Confidence semantics — Session 4.3c

Plan A drops confidence emission. 4.3c will define:

- Per-field vs. envelope-level granularity.
- Calibration approach (raw self-report → calibrated probability mapping).
- Trace-shape impact: keeping `FieldExtraction.confidence_self_report` per-field vs. adding `ExtractionTrace.overall_confidence_self_report`.
- Backend parity: how OllamaBackend produces a confidence signal (post-hoc heuristic? second pass? grammar-constrained additional field?).

### Forensic logging of thinking blocks

Currently not surfaced anywhere. Candidate session: capture thinking content into a sibling artifact alongside the trace, gated by a firm-config flag for retention/privacy reasons. Interacts with the open chore #15 (trace-persistence serialization contract).

### Empirical model commitment

The constructor takes `model` as a required argument. The spec does not commit to a default; an in-flight chore (analogous to OllamaBackend's empirical model exercise) runs candidate Anthropic models against firm-side intake samples and promotes a winner to the **recommended** default in `AnthropicBackend`'s docstring. Hard-coding a default in code is rejected — `model` stays required to keep the `backend_id` honest.

### Mechanism stability

The cycle 13b commit pins the `mechanism` default in plan A; the non-default mechanism remains supported behind the `mechanism` parameter. If `output_config` matures further in the SDK (or if Anthropic clarifies thinking-compat docs) between Plan A landing and any consumer-layer integration, re-running the §9.4 benchmark and flipping the default is a small, low-risk operation. The spec preserves this optionality intentionally — both code paths are exercised by their cycle-5/cycle-6 unit tests so neither bitrots.

## 11. Cross-references

- `2026-04-27-ocr-protocol-ollama-design.md` — 4.3a parent spec; defines the `ExtractionProtocol`, `ExtractionResult`, `ExtractionTrace`, `FieldExtraction`, `INCOMPLETE` surfaces this spec consumes.
- `.claude/context/chores.xml` chore #15 (`2026-04-27-trace-persistence-serialization-contract`) — open chore on trace serialization; relevant to any future session that persists Anthropic-produced traces.
- `.claude/context/chores.xml` chore #16 — pytest integration marker config; this spec's integration smoke depends on it (already landed).
- `.claude/context/plans.xml` plan index 14 (this plan) — added with `id="2026-05-14-anthropic-extraction-backend"`, `status="open"`, `spec-md="docs/superpowers/specs/2026-05-14-anthropic-extraction-backend-design.md"`, `plan-md=""` (filled by plan authoring).
- Auto-memory `project_extraction_backend_split.md` — pins the dev/prod backend split that motivates this work.
