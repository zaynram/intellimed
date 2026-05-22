# AnthropicBackend — Core Implementation Plan

> **For agentic workers:** Use `spec-pipeline:plan-executor-team` (member of plan-group `2026-05-14-anthropic-extraction-backend`). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a production-shaped `AnthropicBackend` (`ExtractionProtocol` implementation against Anthropic's Claude API) — envelope models + forked mappers + constructor + `extract()` pipeline + dual-mechanism seam + SDK error mapping + `Protocol` conformance — such that the endpoint of this plan is **shape-complete (mocked-test green; live-API smoke deferred to instrumentation cycle 15)**. PDF size/page prechecks, image-source branch, caching call-args assertions, extended-thinking call-args assertions, mechanism benchmark, and the live-API smoke land in the sibling plan `instrumentation`.

**Architecture:** Mirrors `OllamaBackend`'s single-file layout (`anthropic_backend.py` houses envelope + class + mappers; no shared helpers with the Ollama path). Splits `prompt.py` into a coordinator hosting the shared legal-handwriting domain constants plus two backend-specific assembly modules (`prompt_ollama.py`, `prompt_anthropic.py`). Adds the `anthropic` SDK pin to `pyproject.toml`. The trace shape stays stable across backends (`ExtractionTrace.backend_id = f"anthropic:{model}"`); `synthesis.py` is not touched.

**Tech Stack:** Python ≥3.12, Pydantic v2, `anthropic` Python SDK (version pinned in Cycle 4 after SDK feature-coverage verification per spec §3 / §5), stdlib `base64` + `mimetypes`, pytest with `MagicMock(spec=anthropic.Anthropic)`.

---

## Plan Metadata (binding, validated by lead against splits.xml)

| Field | Value |
|---|---|
| Plan id | `2026-05-14-anthropic-extraction-backend-core` |
| Plan-group | `2026-05-14-anthropic-extraction-backend` (plans.xml index 14) |
| Suffix | `core` |
| Cycles | `[§7.1..§7.7,§7.10..§7.10,§7.14..§7.14]` (collapsed sub-cycles: 1a, 1b, 2, 3, 4, 5, 6, 7, 10a, 10b, 10c, 10d, 10e, 10f, 14) |
| Depends-on | (none — root) |
| Worktree | not-required |
| Blast-radius | `src/trust_generator/v3/extraction/__init__.py;src/trust_generator/v3/extraction/prompt.py;src/trust_generator/v3/extraction/prompt_ollama.py;src/trust_generator/v3/extraction/prompt_anthropic.py;src/trust_generator/v3/extraction/anthropic_backend.py;tests/v3/extraction/test_anthropic_backend.py;pyproject.toml` |
| Spec | `docs/superpowers/specs/2026-05-14-anthropic-extraction-backend-design.md` |
| Splits | `docs/superpowers/specs/2026-05-14-anthropic-extraction-backend-splits.xml` |
| Sibling | `instrumentation` (depends-on=core; lands atop this work) |

**Discipline notes:**

- Feature branch only — never `main`. Always create a new commit; never `--amend`. Never bypass hooks (`--no-verify`, `--no-gpg-sign`).
- All ad-hoc Python invocation goes through `pixi run python` / `pixi run test` / `pixi run check` (system Python is 3.14; the pixi env pins 3.12 for rule-engine compat).
- `ruff` runs in preview mode targeting py312. RUF022 auto-alphabetizes `__all__` — declare `__all__` entries in sorted order. RUF032 autofixes integer-valued `Decimal("n")` to `Decimal(n)` — write integer-form Decimal literals directly.
- One Red commit + one Green commit per cycle (per `.claude/rules/development-strategy.md`). A Refactor commit is added only when the refactor threshold is met; each cycle lists its threshold verdict.
- For items surfaced mid-implementation that aren't covered by the active plan: open a chore-entry via the `spec-pipeline` scope-maintenance protocol. Do not silently expand the cycle.

## File structure

```
src/trust_generator/v3/extraction/
├── __init__.py                # MODIFY: add `AnthropicBackend` to imports + __all__
├── prompt.py                  # MODIFY: shared legal-handwriting domain constants + back-compat re-export of build_intake_prompt for OllamaBackend's existing import path
├── prompt_ollama.py           # CREATE: relocated Ollama-side _INTAKE_PROMPT + build_intake_prompt()
├── prompt_anthropic.py        # CREATE: Anthropic-shaped build_intake_prompt() (PDF-aware, no reasoning-aloud channel)
├── anthropic_backend.py       # CREATE: envelope models + forked mappers + AnthropicBackend class + seam
├── protocol.py                # NOT TOUCHED (4.3a contract; in this plan only as the conformance target)
├── trace.py                   # NOT TOUCHED
├── markers.py                 # NOT TOUCHED
├── paths.py                   # NOT TOUCHED
├── synthesis.py               # NOT TOUCHED
└── ollama_backend.py          # NOT TOUCHED (its `from ...prompt import build_intake_prompt` line is preserved via the re-export in prompt.py — explicit back-compat seam since ollama_backend.py is OUTSIDE this plan's blast-radius)

tests/v3/extraction/
└── test_anthropic_backend.py  # CREATE: all unit tests for the cycles below
```

`pyproject.toml` is modified once, in Cycle 4, to add the `anthropic` SDK pin to `dependencies`.

## Spec §3 plan-authoring verification gates — accommodation policy

Spec §3 lists three plan-authoring verification gates. Two of them (`output_config + thinking` compat in §8.4; `cache_control` on `output_config.format` in §8.2) are load-bearing for the call-args assertions in the sibling plan `instrumentation` (cycles 11 + 12).

### Lead-verified gate outcomes (2026-05-18, recorded in memory entity `project-anthropic-api-gate-outcomes.md`)

The lead session resolved gates G1 and G2 against the live Anthropic API (`claude-sonnet-4-6`, api-version `2023-06-01`) via raw httpx REST calls (deliberately not through the SDK, so the cycle-4 SDK-pin decision is preserved as the executor's responsibility):

| Gate | Spec § | Question | Verified outcome (2026-05-18) | Consequence for this plan |
|---|---|---|---|---|
| G1 | §8.4 | Does `output_config` compose with `thinking={"type": "enabled", ...}`? | **POSITIVE** — request succeeds; thinking content + structured output both emitted | Cycle 4 default `mechanism="output_config"` stands. Cycle 6's unconditional `thinking={...}` pass-through is correct shape. |
| G2 | §8.2 | Does the API accept `cache_control={"type": "ephemeral"}` on `output_config.format`? | **NEGATIVE** — HTTP 400 *Extra inputs are not permitted* | Sibling `instrumentation` cycle 11 omits the schema-placement assertion under `output_config` mode. Core cycles 5 / 6 / 7 place `cache_control` ONLY on the system block and the document/image content block — never on `output_config.format`. |
| G3 | §5 | SDK version covers PDF document blocks + extended thinking + cache_control breakpoints + both mechanisms GA | Deferred to cycle 4 execution (the executor verifies the SDK pin against the verified API behavior above). G1/G2 outcomes narrow the verification surface: cycle 4 only needs to confirm SDK-side kwarg exposure for `output_config`, `thinking`, `cache_control` on system/document blocks — NOT `cache_control` on `output_config.format`. | See cycle 4 metadata. |

**Forward-looking caveat:** the API verification was a single point-in-time check (one model, one api-version). If a future SDK release or API change flips G1 to negative, spec §1 / §8.4 documents the fallback (flip the default to `mechanism="tool_use"`, switch thinking to opt-in via the constructor budget arg). The seam structure landed below does not require restructuring under that fallback — it is a single-line edit to cycle 4's ctor default.

### Seam structural posture

**The seam landed by Cycles 5 / 6 / 7 of this plan is gate-outcome-agnostic by design:**

- `AnthropicBackend._invoke_envelope_call(system, user_msg, schema) -> dict` takes the mechanism-agnostic responsibility for constructing `messages.create(...)` kwargs, including `thinking={"type": "enabled", "budget_tokens": self.thinking_budget_tokens}` on every call regardless of mechanism, and `cache_control` placement on the system block and on the document content block. The unit tests in Cycles 5 / 6 of this plan assert response-handling and `tool_choice` shape only; the call-args assertions for `thinking` and `cache_control` live in `instrumentation` cycles 11/12.
- **If §8.4 verification flips to "incompatible"** (output_config rejects thinking at request time): the absorption happens entirely in `instrumentation`. The fallback (per spec §1, §8.4) is to flip the constructor default `mechanism="tool_use"` and switch thinking to opt-in via the budget arg. Both flips are confined to Cycle 4's constructor default + Cycle 12's assertion shape. **No restructuring of Cycles 5 / 6 / 7 is required.** Both code paths remain exercised by their unit tests.
- **If §8.2 verification flips to "not accepted"** (cache_control rejected on `output_config.format`): `instrumentation` Cycle 11 omits the schema-placement assertion under `output_config` mode and keeps breakpoints 1 (system) + 2 (document/image content) only. **No restructuring of Cycles 5 / 6 / 7 is required.**
- **§3 SDK feature-coverage gate** clears at Cycle 4 below; the pin lands in `pyproject.toml` after the executor verifies the SDK version supports PDF document blocks + extended thinking + `cache_control` breakpoints + both structured-output mechanisms. See Cycle 4 for the procedure.

This plan commits to `mechanism="output_config"` as the working default in Cycle 4 — consistent with the spec §1 + §8.4 commitment that `output_config` composes with thinking. Should `instrumentation` cycle 12 surface live-API evidence that the combination is rejected, the fallback is a single-line edit to Cycle 4's default, not a structural re-design.

## Out of scope (handed to sibling plans)

The sibling child plan `instrumentation` (file: `docs/superpowers/plans/2026-05-14-anthropic-extraction-backend-instrumentation.md`; `depends-on=core`) owns the following cycles. Cross-reference by exact suffix name `instrumentation`.

| Sibling cycle | Surface | One-line from spec §7 |
|---|---|---|
| 8 | PDF size + page-count prechecks | Oversized PDF and page-count-exceeding PDF raise `ExtractionError` before any API call (`_load_pdf_or_image` precheck branch; `pypdf.PdfReader.pages` length check) |
| 9 | Image-source branch | JPEG/PNG source produces an `image` content block (not `document`); per-field illegibility flows identically (`_load_pdf_or_image` + `_build_user_message` image branch) |
| 11 | Prompt-caching call-args assertion | Captured `messages.create` kwargs carry `cache_control={"type": "ephemeral"}` on system + document/image blocks (and on tools array under tool_use mode); `output_config.format` placement gated on spec §8.2 verification |
| 12 | Extended-thinking call-args assertion | Captured kwargs carry `thinking={"type": "enabled", "budget_tokens": <ctor value>}` on every call regardless of mechanism; `tool_choice == {"type": "auto"}` (never `{"type": "tool", ...}` or `{"type": "any"}`) |
| 13a | Mechanism benchmark (**measurement, not TDD**) | Run both mechanisms against the fixture intake set under `pytest.mark.integration`; emit `tests/data/anthropic_mechanism_log/YYYY-MM-DD-<run-id>.json` records (latency, tokens, success/refusal/schema-valid rates) |
| 13b | Pin mechanism default | Red test: `AnthropicBackend(model="…").mechanism == "<winner>"` where `<winner>` is read from the 13a log; Green: flip `__init__`'s default; commit message cites the 13a log path |
| 15 | Live-API integration smoke | `tests/v3/extraction/test_anthropic_backend_integration.py` under `@pytest.mark.integration`; `ANTHROPIC_API_KEY` gated, `ANTHROPIC_SMOKE_FIXTURE_PATH` overridable; asserts `ExtractionResult`, populated grantor, `backend_id` prefix, token-usage ceiling |

`instrumentation`'s blast-radius is `src/trust_generator/v3/extraction/anthropic_backend.py;tests/v3/extraction/test_anthropic_backend.py;tests/v3/extraction/test_anthropic_backend_integration.py;tests/data/anthropic_mechanism_log` — overlapping with this plan on `anthropic_backend.py` and `test_anthropic_backend.py`, which is the expected layering (sibling lands atop core's seam, extending the same two files).

---

## Cycle 1a — Relocate the Ollama prompt to `prompt_ollama.py` (safety-net cycle)

**Files:**
- Create: `src/trust_generator/v3/extraction/prompt_ollama.py`
- Modify: `src/trust_generator/v3/extraction/prompt.py` (replace body with shared-constants + back-compat re-export)
- Test: `tests/v3/extraction/test_anthropic_backend.py` (new file; first test landed here is the byte-equality test below)

**Threshold verdicts:**
- design_surface_threshold: composition of two units (`prompt_ollama.build_intake_prompt` and the `prompt.build_intake_prompt` re-export), satisfies the criterion.
- refactor_threshold: **none met — green output is already minimal** (pure rename + re-export, no structural duplication).

**Cross-plan note:** `ollama_backend.py:13` (`from trust_generator.v3.extraction.prompt import build_intake_prompt`) is OUTSIDE this plan's blast-radius and MUST be preserved unchanged. The back-compat re-export in `prompt.py` is the explicit seam that protects this constraint.

- [ ] **Step 1: Write the failing test (Red)**

Append to `tests/v3/extraction/test_anthropic_backend.py`:

```python
"""Unit tests for AnthropicBackend and the prompt-module split."""

from __future__ import annotations


def test_prompt_ollama_module_exposes_build_intake_prompt() -> None:
    """`prompt_ollama.build_intake_prompt()` returns a non-empty str."""
    from trust_generator.v3.extraction import prompt_ollama

    out = prompt_ollama.build_intake_prompt()
    assert isinstance(out, str)
    assert out.strip()  # non-empty after stripping


def test_prompt_ollama_build_intake_prompt_byte_equal_to_prompt_module_reexport() -> None:
    """Relocation is byte-exact — `prompt.build_intake_prompt()` and
    `prompt_ollama.build_intake_prompt()` return the same string.

    This pins the Ollama-side relocation as a pure rename: the existing
    OllamaBackend import path (`from ...prompt import build_intake_prompt`,
    ollama_backend.py:13) MUST continue resolving to the same string,
    since ollama_backend.py is outside this plan's blast-radius and
    cannot be edited.
    """
    from trust_generator.v3.extraction import prompt, prompt_ollama

    assert prompt.build_intake_prompt() == prompt_ollama.build_intake_prompt()


def test_prompt_module_reexports_build_intake_prompt_for_ollama_backend_compat() -> None:
    """The `prompt.build_intake_prompt` name is still importable.

    OllamaBackend imports `build_intake_prompt` from `prompt`; the
    relocation must not break that path.
    """
    from trust_generator.v3.extraction.prompt import build_intake_prompt

    assert callable(build_intake_prompt)
    assert isinstance(build_intake_prompt(), str)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pixi run test -- tests/v3/extraction/test_anthropic_backend.py -v`

Expected: `ModuleNotFoundError: No module named 'trust_generator.v3.extraction.prompt_ollama'` on the import-line.

- [ ] **Step 3: Write minimal implementation (Green)**

Create `src/trust_generator/v3/extraction/prompt_ollama.py`:

```python
"""Ollama-side intake prompt assembly.

Spec §8 strategy retained verbatim from the original
``prompt.build_intake_prompt`` (relocation; not a rewrite). The body is
Ollama-aware because it references the constrained-decoding `reasoning`
channel and the grammar-constrained sample-time discipline.
"""

from __future__ import annotations

_INTAKE_PROMPT = """\
You are a careful legal-intake transcriber. The attached image is a handwritten trust intake form. Extract its field values into the structured output schema.

Reading discipline:
1. Verbatim transcription. Transcribe what is written, not what the writer "meant." Do not normalize names, dates, currency, suffixes, or punctuation. Do not reformat. If the form says "James William Thompson, Jr." emit that exact string; do not rewrite to "James W. Thompson Jr."
2. Illegibility is first-class. If you cannot read a field with confidence, set its illegible flag to true. Marking a field illegible is preferred over guessing.
3. Reasoning aloud first. The output schema reserves a "reasoning" field at the start. Use it to walk through what you see on the form, noting handwriting irregularities, before committing to data fields.

Domain context: the document is a legal trust intake form. Expected sections include grantors, beneficiaries, real property, personal property, and fiduciaries.

Anti-hallucination guardrails:
- If a field is not present on the form at all, omit it from the output. Do not invent a default value.
- If a field is partially filled, transcribe what is there. Do not complete it.
- If multiple readings are plausible, pick the most likely transcription and use the "note" channel to record the ambiguity.
"""


def build_intake_prompt() -> str:
    """Return the Ollama-side OCR extraction prompt.

    See module docstring; relocation from ``prompt.build_intake_prompt``
    with byte-equal text body. Future Ollama-side prompt refinements
    land here; the Anthropic backend has its own assembly module.
    """
    return _INTAKE_PROMPT
```

Replace `src/trust_generator/v3/extraction/prompt.py` body with:

```python
"""Shared legal-handwriting prompt coordinator.

Hosts the back-compat re-export of ``build_intake_prompt`` so that
``ollama_backend.py``'s existing import path
(``from trust_generator.v3.extraction.prompt import build_intake_prompt``)
keeps working unchanged. The Ollama-side prompt body now lives in
``prompt_ollama.py``; the Anthropic-side body lives in
``prompt_anthropic.py``.

Pure shared-constants extraction (e.g., a single ``_DOMAIN_CONTEXT``
constant referenced by both backend assemblers) is a future refactor —
deferred because both prompt strings are short enough that DRY-driven
extraction would obscure them. Revisit if a third backend lands.
"""

from __future__ import annotations

from trust_generator.v3.extraction.prompt_ollama import build_intake_prompt

__all__ = ("build_intake_prompt",)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pixi run test -- tests/v3/extraction/test_anthropic_backend.py -v` — expect PASS on the three relocation tests.

Run: `pixi run test -- tests/v3/extraction/test_ollama_backend.py tests/v3/extraction/test_ollama_backend_errors.py tests/v3/extraction/test_ollama_backend_integration.py -v` — expect green (unchanged; the OllamaBackend safety net validates the back-compat re-export).

Run: `pixi run check` — full gate must stay green.

- [ ] **Step 5: Commit Red**

```bash
git add tests/v3/extraction/test_anthropic_backend.py
git commit -m "test(v3/extraction): pin prompt_ollama relocation (Red, cycle 1a)"
```

- [ ] **Step 6: Commit Green**

```bash
git add src/trust_generator/v3/extraction/prompt_ollama.py src/trust_generator/v3/extraction/prompt.py
git commit -m "refactor(v3/extraction): relocate Ollama intake prompt to prompt_ollama (Green, cycle 1a)"
```

---

## Cycle 1b — `prompt_anthropic.build_intake_prompt`

**Files:**
- Create: `src/trust_generator/v3/extraction/prompt_anthropic.py`
- Test: `tests/v3/extraction/test_anthropic_backend.py` (append)

**Threshold verdicts:**
- design_surface_threshold: contract surface external consumers (the `AnthropicBackend` constructor's `prompt_builder` default) depend on; satisfies the criterion.
- refactor_threshold: **none met — green output is already minimal**. The Anthropic prompt body is a freshly authored single string; deduping shared constants with `prompt_ollama` is rejected as premature (only two backends, both bodies are short, the proposed shared substrings carry backend-specific framing that would require parameterization to merge).

- [ ] **Step 1: Write the failing test (Red)**

Append:

```python
def test_prompt_anthropic_module_exposes_build_intake_prompt() -> None:
    """`prompt_anthropic.build_intake_prompt()` returns a non-empty str."""
    from trust_generator.v3.extraction import prompt_anthropic

    out = prompt_anthropic.build_intake_prompt()
    assert isinstance(out, str)
    assert out.strip()


def test_prompt_anthropic_prompt_contains_legal_intake_framing() -> None:
    """The Anthropic prompt names the legal-intake domain context.

    Pins that the backend-fork retains the §8.2 domain orientation
    (legal trust intake; grantors / beneficiaries / etc.).
    """
    from trust_generator.v3.extraction.prompt_anthropic import build_intake_prompt

    out = build_intake_prompt()
    assert "legal" in out.lower()
    assert "trust" in out.lower()
    assert "grantor" in out.lower()


def test_prompt_anthropic_prompt_omits_reasoning_aloud_channel() -> None:
    """The Anthropic prompt does NOT instruct the model to reason aloud
    in a schema reasoning field — extended thinking handles that channel
    out-of-band, and the AnthropicGenerationEnvelope has no ``reasoning``
    field (spec §6).
    """
    from trust_generator.v3.extraction.prompt_anthropic import build_intake_prompt

    out = build_intake_prompt().lower()
    # The Ollama prompt uses the phrase "reasoning aloud first" / "reasoning"
    # field; Anthropic-side must not direct the model to populate such a field.
    assert "reasoning" not in out
    assert '"reasoning"' not in out


def test_prompt_anthropic_prompt_acknowledges_pdf_intake() -> None:
    """The Anthropic prompt mentions PDF intake explicitly.

    Anthropic's `document` content block accepts PDFs natively (spec
    §2 In-scope, §8.1); the prompt should cue the model that the
    attachment may be a multi-page PDF rather than a single image.
    """
    from trust_generator.v3.extraction.prompt_anthropic import build_intake_prompt

    out = build_intake_prompt().lower()
    assert "pdf" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pixi run test -- tests/v3/extraction/test_anthropic_backend.py::test_prompt_anthropic_module_exposes_build_intake_prompt -v`

Expected: `ModuleNotFoundError: No module named 'trust_generator.v3.extraction.prompt_anthropic'`.

- [ ] **Step 3: Write minimal implementation (Green)**

Create `src/trust_generator/v3/extraction/prompt_anthropic.py`:

```python
"""Anthropic-side intake prompt assembly.

Backend-specific differentiation from ``prompt_ollama``:
- No reasoning-aloud directive (extended thinking carries that channel
  out-of-band; the AnthropicGenerationEnvelope has no ``reasoning``
  field).
- Acknowledges PDF intake (Anthropic's ``document`` content block
  accepts PDFs natively).
- Retains §8.1 verbatim-transcription / illegibility-as-first-class
  discipline and §8.3 anti-hallucination guardrails.

Spec §4 *Prompt module split rationale*; §4 *Single-fragment prompt
strategy* — this builder returns a single string consumed as the
cacheable system prompt; the user message carries only the document /
image content block.
"""

from __future__ import annotations

_INTAKE_PROMPT = """\
You are a careful legal-intake transcriber. The attached document — which may be a multi-page PDF or a single image — is a handwritten trust intake form. Extract its field values into the structured output schema provided alongside this request.

Reading discipline:
1. Verbatim transcription. Transcribe what is written, not what the writer "meant." Do not normalize names, dates, currency, suffixes, or punctuation. Do not reformat. If the form says "James William Thompson, Jr." emit that exact string; do not rewrite to "James W. Thompson Jr."
2. Illegibility is first-class. If you cannot read a field with confidence, set the matching illegible flag to true on that field. Marking a field illegible is preferred over guessing.

Domain context: the document is a legal trust intake form. Expected sections include grantors, beneficiaries, real property, personal property, and fiduciaries.

Anti-hallucination guardrails:
- If a field is not present on the form at all, omit it from the output. Do not invent a default value.
- If a field is partially filled, transcribe what is there. Do not complete it.
- If multiple readings are plausible, pick the most likely transcription. Set the matching illegible flag on the field rather than presenting a confident transcription you do not actually hold.
"""


def build_intake_prompt() -> str:
    """Return the Anthropic-side OCR extraction prompt.

    Used as the cacheable system prompt (spec §8.2 breakpoint 1).
    The ``prompt_builder`` constructor seam on ``AnthropicBackend``
    defaults to this function; passing a custom builder is supported
    for future firm-customized variants.
    """
    return _INTAKE_PROMPT
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pixi run test -- tests/v3/extraction/test_anthropic_backend.py -v` — expect PASS on all six tests so far (three relocation + four Anthropic prompt).

Run: `pixi run check` — gate stays green.

- [ ] **Step 5: Commit Red**

```bash
git add tests/v3/extraction/test_anthropic_backend.py
git commit -m "test(v3/extraction): pin Anthropic prompt builder shape (Red, cycle 1b)"
```

- [ ] **Step 6: Commit Green**

```bash
git add src/trust_generator/v3/extraction/prompt_anthropic.py
git commit -m "feat(v3/extraction): add prompt_anthropic.build_intake_prompt (Green, cycle 1b)"
```

---

## Cycle 2 — `AnthropicGenerationEnvelope` and nested Pydantic models

**Files:**
- Create: `src/trust_generator/v3/extraction/anthropic_backend.py` (first content)
- Test: `tests/v3/extraction/test_anthropic_backend.py` (append)

**Threshold verdicts:**
- design_surface_threshold: contract surface (envelope schema is consumed by the seam + mappers; serialized into the API call via `model_json_schema()`). Satisfies the criterion.
- refactor_threshold: **none met — green output is already minimal** (four small `BaseModel` declarations, no branching, no duplication).

- [ ] **Step 1: Write the failing tests (Red)**

Append:

```python
def test_anthropic_field_flag_default_is_not_illegible() -> None:
    from trust_generator.v3.extraction.anthropic_backend import AnthropicFieldFlag

    assert AnthropicFieldFlag().illegible is False


def test_anthropic_field_flag_rejects_extra_keys() -> None:
    from pydantic import ValidationError

    from trust_generator.v3.extraction.anthropic_backend import AnthropicFieldFlag

    with pytest.raises(ValidationError):
        AnthropicFieldFlag.model_validate({"illegible": True, "note": "extra"})


def test_anthropic_grantor_envelope_default_field_flags_are_inert() -> None:
    from trust_generator.v3.extraction.anthropic_backend import AnthropicGrantorEnvelope

    g = AnthropicGrantorEnvelope()
    assert g.full_legal_name is None
    assert g.full_legal_name_flag.illegible is False
    assert g.date_of_birth is None
    assert g.date_of_birth_flag.illegible is False


def test_anthropic_beneficiary_envelope_default_field_flags_are_inert() -> None:
    from trust_generator.v3.extraction.anthropic_backend import (
        AnthropicBeneficiaryEnvelope,
    )

    b = AnthropicBeneficiaryEnvelope()
    assert b.full_legal_name is None
    assert b.relationship is None
    assert b.share_percent is None
    assert b.full_legal_name_flag.illegible is False
    assert b.relationship_flag.illegible is False
    assert b.share_percent_flag.illegible is False


def test_anthropic_generation_envelope_round_trips() -> None:
    """model_validate(model_dump()) is an identity for a populated envelope."""
    from trust_generator.v3.extraction.anthropic_backend import (
        AnthropicBeneficiaryEnvelope,
        AnthropicFieldFlag,
        AnthropicGenerationEnvelope,
        AnthropicGrantorEnvelope,
    )

    env = AnthropicGenerationEnvelope(
        grantors=[
            AnthropicGrantorEnvelope(
                full_legal_name="James William Thompson, Jr.",
                date_of_birth="1962-03-14",
            ),
            AnthropicGrantorEnvelope(
                full_legal_name_flag=AnthropicFieldFlag(illegible=True),
            ),
        ],
        beneficiaries=[
            AnthropicBeneficiaryEnvelope(
                full_legal_name="Jane Doe",
                relationship="daughter",
                share_percent="50",
            ),
        ],
    )

    dumped = env.model_dump()
    rehydrated = AnthropicGenerationEnvelope.model_validate(dumped)
    assert rehydrated == env


def test_anthropic_generation_envelope_rejects_extra_keys() -> None:
    from pydantic import ValidationError

    from trust_generator.v3.extraction.anthropic_backend import (
        AnthropicGenerationEnvelope,
    )

    with pytest.raises(ValidationError):
        AnthropicGenerationEnvelope.model_validate(
            {"grantors": [], "beneficiaries": [], "reasoning": "should-be-rejected"}
        )


def test_anthropic_generation_envelope_has_no_reasoning_field() -> None:
    """Spec §6: no reasoning field (extended thinking carries that
    channel out-of-band) and no overall_confidence (deferred to 4.3c).
    """
    from trust_generator.v3.extraction.anthropic_backend import (
        AnthropicGenerationEnvelope,
    )

    fields = set(AnthropicGenerationEnvelope.model_fields)
    assert "reasoning" not in fields
    assert "overall_confidence" not in fields
    assert fields == {"grantors", "beneficiaries"}
```

Also ensure pytest is imported at the top of `test_anthropic_backend.py`:

```python
import pytest
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pixi run test -- tests/v3/extraction/test_anthropic_backend.py -v`

Expected: `ModuleNotFoundError: No module named 'trust_generator.v3.extraction.anthropic_backend'`.

- [ ] **Step 3: Write minimal implementation (Green)**

Create `src/trust_generator/v3/extraction/anthropic_backend.py` with just the envelope models:

```python
"""AnthropicBackend: ExtractionProtocol implementation against the
Anthropic Claude API.

Spec §6 (Public surface), §8 (Backend internals), §8.5 (Error mapping).
Mirrors ``ollama_backend.py``'s single-file layout: envelope models +
forked mappers + class + dual-mechanism seam, no shared helpers with
the Ollama path.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AnthropicFieldFlag(BaseModel):
    """Per-field illegibility marker.

    Spec §6: bare bool today; numeric confidence is deferred to 4.3c
    ConfidenceProtocol. The wrapper exists (rather than a raw bool
    inline on each parent envelope row) so 4.3c can add per-field
    signals without changing the parent envelope's schema shape.
    """

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
    """Top-level Anthropic envelope.

    Spec §6: no ``reasoning`` field (extended thinking carries the
    reasoning channel out-of-band); no ``overall_confidence`` (deferred
    to 4.3c ConfidenceProtocol per spec §2). Plain ``list[...]`` for
    sub-envelopes — Anthropic's structured-output mechanism has no
    GBNF key-order pin and no integer-keyed-dict workaround need.
    """

    model_config = ConfigDict(extra="forbid")

    grantors: list[AnthropicGrantorEnvelope] = Field(default_factory=list)
    beneficiaries: list[AnthropicBeneficiaryEnvelope] = Field(default_factory=list)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pixi run test -- tests/v3/extraction/test_anthropic_backend.py -v` — all envelope tests PASS.

Run: `pixi run check` — gate stays green.

- [ ] **Step 5: Commit Red**

```bash
git add tests/v3/extraction/test_anthropic_backend.py
git commit -m "test(v3/extraction): pin AnthropicGenerationEnvelope shape (Red, cycle 2)"
```

- [ ] **Step 6: Commit Green**

```bash
git add src/trust_generator/v3/extraction/anthropic_backend.py
git commit -m "feat(v3/extraction): add AnthropicGenerationEnvelope models (Green, cycle 2)"
```

---

## Cycle 3 — Forked mappers

**Files:**
- Modify: `src/trust_generator/v3/extraction/anthropic_backend.py` (append three mapper functions)
- Test: `tests/v3/extraction/test_anthropic_backend.py` (append)

**Threshold verdicts:**
- design_surface_threshold: composition of three units; non-obvious failure modes (positional grantor mapping, illegibility-degradation, None-omission, INCOMPLETE-sentinel discipline); satisfies the criterion.
- refactor_threshold: **conditional — green-phase code likely has structural duplication across the two value-field branches (full_legal_name + date_of_birth + share_percent emission share a "if value is not None or flag.illegible: emit FieldExtraction" shape)**. If duplication crystallizes during Green, factor a `_emit_field` helper module-local to `anthropic_backend.py`. The mapper bodies do NOT share code with `OllamaBackend`'s mappers — spec §6 *Forked mappers* explicitly forbids that.

- [ ] **Step 1: Write the failing tests (Red)**

Append:

```python
def test_map_grantor_anthropic_envelope_happy_path() -> None:
    from trust_generator.v3.extraction.anthropic_backend import (
        AnthropicGrantorEnvelope,
        _map_grantor_anthropic_envelope,
    )

    fields, needs_co_grantor = _map_grantor_anthropic_envelope(
        [
            AnthropicGrantorEnvelope(
                full_legal_name="James William Thompson, Jr.",
                date_of_birth="1962-03-14",
            ),
        ]
    )

    assert needs_co_grantor is False
    field_paths = [f.field_path for f in fields]
    assert field_paths == ["grantor.full_legal_name", "grantor.date_of_birth"]
    name_field = fields[0]
    assert name_field.raw_value == "James William Thompson, Jr."
    assert name_field.normalized_value == "James William Thompson, Jr."
    assert name_field.illegible is False


def test_map_grantor_anthropic_envelope_two_grantors_signals_co_grantor() -> None:
    from trust_generator.v3.extraction.anthropic_backend import (
        AnthropicGrantorEnvelope,
        _map_grantor_anthropic_envelope,
    )

    fields, needs_co_grantor = _map_grantor_anthropic_envelope(
        [
            AnthropicGrantorEnvelope(full_legal_name="A"),
            AnthropicGrantorEnvelope(full_legal_name="B"),
        ]
    )

    assert needs_co_grantor is True
    assert [f.field_path for f in fields] == [
        "grantor.full_legal_name",
        "co_grantor.full_legal_name",
    ]


def test_map_grantor_anthropic_envelope_ignores_third_grantor() -> None:
    """Positional mapping caps at index 1; entries beyond are ignored."""
    from trust_generator.v3.extraction.anthropic_backend import (
        AnthropicGrantorEnvelope,
        _map_grantor_anthropic_envelope,
    )

    fields, needs_co_grantor = _map_grantor_anthropic_envelope(
        [
            AnthropicGrantorEnvelope(full_legal_name="A"),
            AnthropicGrantorEnvelope(full_legal_name="B"),
            AnthropicGrantorEnvelope(full_legal_name="C"),
        ]
    )

    paths = [f.field_path for f in fields]
    assert "C" not in [f.raw_value for f in fields]
    assert paths == ["grantor.full_legal_name", "co_grantor.full_legal_name"]
    assert needs_co_grantor is True


def test_map_grantor_anthropic_envelope_illegibility_degrades_value() -> None:
    from trust_generator.v3.extraction.anthropic_backend import (
        AnthropicFieldFlag,
        AnthropicGrantorEnvelope,
        _map_grantor_anthropic_envelope,
    )

    fields, _ = _map_grantor_anthropic_envelope(
        [
            AnthropicGrantorEnvelope(
                full_legal_name_flag=AnthropicFieldFlag(illegible=True),
            ),
        ]
    )

    assert len(fields) == 1
    assert fields[0].field_path == "grantor.full_legal_name"
    assert fields[0].illegible is True
    assert fields[0].normalized_value is None
    assert fields[0].raw_value == ""


def test_map_grantor_anthropic_envelope_omits_absent_field() -> None:
    """Per spec §8.3 omit-if-absent: data=None AND flag quiet → no entry."""
    from trust_generator.v3.extraction.anthropic_backend import (
        AnthropicGrantorEnvelope,
        _map_grantor_anthropic_envelope,
    )

    fields, _ = _map_grantor_anthropic_envelope([AnthropicGrantorEnvelope()])

    assert fields == []


def test_map_grantor_anthropic_envelope_date_uses_incomplete_sentinel() -> None:
    """Legible-but-not-yet-normalized date → normalized_value is INCOMPLETE."""
    from trust_generator.v3.extraction.anthropic_backend import (
        AnthropicGrantorEnvelope,
        _map_grantor_anthropic_envelope,
    )
    from trust_generator.v3.extraction.trace import INCOMPLETE

    fields, _ = _map_grantor_anthropic_envelope(
        [AnthropicGrantorEnvelope(date_of_birth="1962-03-14")]
    )
    dob = next(f for f in fields if f.field_path == "grantor.date_of_birth")
    assert dob.normalized_value is INCOMPLETE
    assert dob.illegible is False
    assert dob.raw_value == "1962-03-14"


def test_map_beneficiary_anthropic_envelope_happy_path() -> None:
    from trust_generator.v3.extraction.anthropic_backend import (
        AnthropicBeneficiaryEnvelope,
        _map_beneficiary_anthropic_envelope,
    )
    from trust_generator.v3.extraction.trace import INCOMPLETE
    from trust_generator.v3.schema import BeneficiaryShare, OtherBeneficiary

    fields, others, shares = _map_beneficiary_anthropic_envelope(
        [
            AnthropicBeneficiaryEnvelope(
                full_legal_name="Jane Doe",
                relationship="daughter",
                share_percent="50",
            ),
        ]
    )

    assert len(others) == 1 and isinstance(others[0], OtherBeneficiary)
    assert len(shares) == 1 and isinstance(shares[0], BeneficiaryShare)
    assert shares[0].recipient_ref == "other_beneficiaries[0]"

    paths = [f.field_path for f in fields]
    assert paths == [
        "other_beneficiaries[0].full_legal_name",
        "other_beneficiaries[0].relationship_other",
        "beneficiary_shares[0].share_percent",
    ]
    share_field = next(f for f in fields if f.field_path.endswith("share_percent"))
    assert share_field.normalized_value is INCOMPLETE
    assert share_field.raw_value == "50"


def test_map_beneficiary_anthropic_envelope_illegibility_degrades_value() -> None:
    from trust_generator.v3.extraction.anthropic_backend import (
        AnthropicBeneficiaryEnvelope,
        AnthropicFieldFlag,
        _map_beneficiary_anthropic_envelope,
    )

    fields, others, shares = _map_beneficiary_anthropic_envelope(
        [
            AnthropicBeneficiaryEnvelope(
                share_percent_flag=AnthropicFieldFlag(illegible=True),
            ),
        ]
    )

    assert len(others) == 1
    assert len(shares) == 1
    share_field = next(f for f in fields if f.field_path.endswith("share_percent"))
    assert share_field.illegible is True
    assert share_field.normalized_value is None
    assert share_field.raw_value == ""


def test_anthropic_envelope_to_extraction_result_assembles_trace() -> None:
    """Composer mirrors ``_envelope_to_extraction_result`` in ollama_backend
    (spec §6 composer construction pattern)."""
    from trust_generator.v3.extraction.anthropic_backend import (
        AnthropicBeneficiaryEnvelope,
        AnthropicGenerationEnvelope,
        AnthropicGrantorEnvelope,
        _anthropic_envelope_to_extraction_result,
    )

    env = AnthropicGenerationEnvelope(
        grantors=[
            AnthropicGrantorEnvelope(full_legal_name="Alice"),
            AnthropicGrantorEnvelope(full_legal_name="Bob"),
        ],
        beneficiaries=[
            AnthropicBeneficiaryEnvelope(full_legal_name="Charlie"),
        ],
    )

    result = _anthropic_envelope_to_extraction_result(env, model="claude-sonnet-4-6")

    assert result.trace.backend_id == "anthropic:claude-sonnet-4-6"
    assert result.data.co_grantor is not None  # second grantor → co_grantor
    assert len(result.data.other_beneficiaries) == 1
    assert len(result.data.beneficiary_shares) == 1
    field_paths = [f.field_path for f in result.trace.fields]
    assert "grantor.full_legal_name" in field_paths
    assert "co_grantor.full_legal_name" in field_paths
    assert "other_beneficiaries[0].full_legal_name" in field_paths
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pixi run test -- tests/v3/extraction/test_anthropic_backend.py -v`

Expected: `ImportError: cannot import name '_map_grantor_anthropic_envelope' from 'trust_generator.v3.extraction.anthropic_backend'` on the first new test.

- [ ] **Step 3: Write minimal implementation (Green)**

Append to `src/trust_generator/v3/extraction/anthropic_backend.py`:

```python
from datetime import UTC, datetime

from trust_generator.v3.extraction.trace import (
    INCOMPLETE,
    ExtractionResult,
    ExtractionTrace,
    FieldExtraction,
)
from trust_generator.v3.schema import (
    BeneficiaryShare,
    GrantorInfo,
    OtherBeneficiary,
    TrustData,
)


def _map_grantor_anthropic_envelope(
    grantors: list[AnthropicGrantorEnvelope],
) -> tuple[list[FieldExtraction], bool]:
    """Map envelope.grantors → trace fields under 'grantor.*' / 'co_grantor.*'.

    Spec §6 *Positional mapping semantics*: envelope.grantors[0] collapses
    onto ``grantor`` and [1] onto ``co_grantor``; entries beyond [1] are
    ignored at this layer. Returns ``(fields, needs_co_grantor)``.
    """
    fields: list[FieldExtraction] = []
    grantor_paths = ("grantor", "co_grantor")
    for idx, grantor in enumerate(grantors[:2]):
        prefix = grantor_paths[idx]
        if (
            grantor.full_legal_name is not None
            or grantor.full_legal_name_flag.illegible
        ):
            illegible = grantor.full_legal_name_flag.illegible
            fields.append(
                FieldExtraction(
                    field_path=f"{prefix}.full_legal_name",
                    raw_value=grantor.full_legal_name or "",
                    normalized_value=None if illegible else grantor.full_legal_name,
                    illegible=illegible,
                )
            )
        if (
            grantor.date_of_birth is not None
            or grantor.date_of_birth_flag.illegible
        ):
            illegible = grantor.date_of_birth_flag.illegible
            fields.append(
                FieldExtraction(
                    field_path=f"{prefix}.date_of_birth",
                    raw_value=grantor.date_of_birth or "",
                    # Date normalization deferred per spec §6 final paragraph:
                    # INCOMPLETE sentinel for legible-but-not-yet-normalized;
                    # None for illegible (the _illegible_excludes_normalized_value
                    # validator on FieldExtraction enforces the invariant).
                    normalized_value=None if illegible else INCOMPLETE,
                    illegible=illegible,
                )
            )
    return fields, len(grantors) >= 2


def _map_beneficiary_anthropic_envelope(
    beneficiaries: list[AnthropicBeneficiaryEnvelope],
) -> tuple[list[FieldExtraction], list[OtherBeneficiary], list[BeneficiaryShare]]:
    """Map envelope.beneficiaries → trace fields + TrustData lists.

    Spec §6: conservative classification fallback (every envelope
    beneficiary lands in ``other_beneficiaries[j]`` with paired
    ``beneficiary_shares[j]``; ``recipient_ref=f"other_beneficiaries[{j}]"``).
    Relationship lands as the free-text fallback (``relationship_other``).
    """
    fields: list[FieldExtraction] = []
    others: list[OtherBeneficiary] = []
    shares: list[BeneficiaryShare] = []
    for j, beneficiary in enumerate(beneficiaries):
        others.append(OtherBeneficiary())
        shares.append(BeneficiaryShare(recipient_ref=f"other_beneficiaries[{j}]"))

        if (
            beneficiary.full_legal_name is not None
            or beneficiary.full_legal_name_flag.illegible
        ):
            illegible = beneficiary.full_legal_name_flag.illegible
            fields.append(
                FieldExtraction(
                    field_path=f"other_beneficiaries[{j}].full_legal_name",
                    raw_value=beneficiary.full_legal_name or "",
                    normalized_value=None if illegible else beneficiary.full_legal_name,
                    illegible=illegible,
                )
            )
        if (
            beneficiary.relationship is not None
            or beneficiary.relationship_flag.illegible
        ):
            illegible = beneficiary.relationship_flag.illegible
            fields.append(
                FieldExtraction(
                    field_path=f"other_beneficiaries[{j}].relationship_other",
                    raw_value=beneficiary.relationship or "",
                    normalized_value=None if illegible else beneficiary.relationship,
                    illegible=illegible,
                )
            )
        if (
            beneficiary.share_percent is not None
            or beneficiary.share_percent_flag.illegible
        ):
            illegible = beneficiary.share_percent_flag.illegible
            fields.append(
                FieldExtraction(
                    field_path=f"beneficiary_shares[{j}].share_percent",
                    raw_value=beneficiary.share_percent or "",
                    # Numeric normalization deferred per spec §6: INCOMPLETE
                    # sentinel for legible-but-not-yet-normalized.
                    normalized_value=None if illegible else INCOMPLETE,
                    illegible=illegible,
                )
            )
    return fields, others, shares


def _anthropic_envelope_to_extraction_result(
    envelope: AnthropicGenerationEnvelope, *, model: str
) -> ExtractionResult:
    """Map a validated AnthropicGenerationEnvelope to an ExtractionResult.

    Composer construction pattern (spec §6): default-construct
    ``TrustData()``; optionally instantiate ``co_grantor``; assign
    ``other_beneficiaries`` and ``beneficiary_shares`` via attribute
    mutation. Mirrors OllamaBackend's ``_envelope_to_extraction_result``
    at the call-site, simplifying diff-driven review when conventions
    evolve.

    ``backend_id`` follows spec 4.3a §5.3's ``<backend>:<model>``
    convention (e.g., ``"anthropic:claude-sonnet-4-6"``).
    """
    data = TrustData()
    grantor_fields, needs_co_grantor = _map_grantor_anthropic_envelope(envelope.grantors)
    if needs_co_grantor:
        data.co_grantor = GrantorInfo()
    beneficiary_fields, others, shares = _map_beneficiary_anthropic_envelope(
        envelope.beneficiaries
    )
    data.other_beneficiaries = others
    data.beneficiary_shares = shares

    trace = ExtractionTrace(
        fields=[*grantor_fields, *beneficiary_fields],
        backend_id=f"anthropic:{model}",
        extracted_at=datetime.now(UTC),
    )
    return ExtractionResult(data=data, trace=trace)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pixi run test -- tests/v3/extraction/test_anthropic_backend.py -v` — all mapper tests PASS.

Run: `pixi run check` — gate stays green.

- [ ] **Step 5: Commit Red**

```bash
git add tests/v3/extraction/test_anthropic_backend.py
git commit -m "test(v3/extraction): pin Anthropic envelope mappers (Red, cycle 3)"
```

- [ ] **Step 6: Commit Green**

```bash
git add src/trust_generator/v3/extraction/anthropic_backend.py
git commit -m "feat(v3/extraction): add forked mappers _*_anthropic_envelope (Green, cycle 3)"
```

- [ ] **Step 7 (conditional): Refactor**

If the Green-phase mappers reveal cleanly extractable duplication across the field-emission branches, factor a module-local helper (e.g., `_emit_field(prefix, name, raw, illegible, deferred_normalize) -> FieldExtraction | None`). Run `pixi run check`; commit:

```bash
git commit -m "refactor(v3/extraction): factor field-emission helper in Anthropic mappers"
```

If no duplication is structural, note "no refactor stage — green output is already minimal" in the cycle close-out message and skip Step 7.

---

## Cycle 4 — `AnthropicBackend.__init__` + `anthropic` SDK pin

**Files:**
- Modify: `src/trust_generator/v3/extraction/anthropic_backend.py` (add class)
- Modify: `pyproject.toml` (add `anthropic` pin to `dependencies`)
- Test: `tests/v3/extraction/test_anthropic_backend.py` (append)

**Threshold verdicts:**
- design_surface_threshold: contract surface external consumers depend on (the class's constructor signature is the public seam called by every downstream caller). Satisfies the criterion.
- refactor_threshold: **none met — green output is already minimal** (constructor body is a straight assignment of normalized defaults).

**SDK pin procedure (spec §3 verification gate 3; narrowed by lead-verified G1/G2 outcomes 2026-05-18):**

Lead-verified gate outcomes from memory entity `project-anthropic-api-gate-outcomes.md` (see "Spec §3 plan-authoring verification gates — accommodation policy" above) narrow this gate: G1 (output_config + thinking) POSITIVE and G2 (cache_control on output_config.format) NEGATIVE are settled. The executor only verifies SDK-side kwarg exposure for the verified behaviors — not the API behavior itself.

Before editing `pyproject.toml`:

1. Read the current Anthropic SDK changelog: `https://github.com/anthropics/anthropic-sdk-python/releases`. (Alternatively, invoke the `claude-api` skill if available in the executor's installation — its description signals prompt-caching mandate + cross-model migration support.)
2. Identify the lowest version satisfying **all four** required SDK features per spec §5:
   - PDF document content block (`{"type": "document", "source": {"type": "base64", ...}}`).
   - Extended thinking (`thinking={"type": "enabled", "budget_tokens": N}`) kwarg on `messages.create`.
   - Prompt caching with `cache_control={"type": "ephemeral"}` breakpoints — SDK exposure for system block + content block placement (NOT on `output_config.format` — G2-negative per lead verification).
   - Both `tool_use` (with `tool_choice={"type": "auto"}`) and `output_config={"format": {"type": "json_schema", "schema": ...}}` kwargs on `messages.create`.
3. If a single version satisfies all four GA, pin `>=<that-version>`. If no single version does, pin the latest stable release and surface the spec §3 fallback (degrade §2 In-scope coverage to whatever IS supported) as a chore-entry suggestion to the lead before continuing — do not silently drop coverage.
4. **Exception-constructor signature audit.** The cycle 10a–10d test code below instantiates `anthropic.APIConnectionError`, `anthropic.RateLimitError`, `anthropic.AuthenticationError`, and `anthropic.APIError` directly. These constructor signatures (which kwargs are required; whether `response` accepts a `MagicMock` or requires a real httpx-shaped object; whether `body` is required) have shifted across SDK 0.20 → 0.30+ → current. Before landing cycle 10a's Red, the executor verifies against the pinned SDK's `anthropic._exceptions` module what each exception class's `__init__` accepts and adapts the test ctor calls accordingly. The plan's test code below is a template; the kwargs may need to flex (e.g., `response=MagicMock(spec=httpx.Response, status_code=401, request=MagicMock(spec=httpx.Request))` instead of bare `MagicMock`).

**Memory-entity update (out-of-blast-radius — executor session uses mcp memory tools):** Spec §3 names this as an in-cycle action coupled with a `library_selections` graph observation update. After landing the SDK pin in `pyproject.toml`, the executor session invokes `mcp__memory__add_observations` on entity `library_selections` with an observation citing the pin (e.g., "anthropic SDK pinned at >=<version> in plan #14 cycle 4; supports PDF document blocks, extended thinking, cache_control breakpoints, tool_use + output_config GA"). The memory entity update is NOT a file edit and is NOT in this plan's blast-radius — it is performed via the mcp memory tool surface only.

- [ ] **Step 1: Write the failing tests (Red)**

Append:

```python
def test_anthropic_backend_importable_from_module() -> None:
    from trust_generator.v3.extraction.anthropic_backend import AnthropicBackend

    assert AnthropicBackend.__name__ == "AnthropicBackend"


def test_anthropic_backend_requires_model_keyword_only() -> None:
    """``model`` is required and keyword-only (spec §6 ``__init__`` signature)."""
    from unittest.mock import MagicMock

    from trust_generator.v3.extraction.anthropic_backend import AnthropicBackend

    with pytest.raises(TypeError):
        AnthropicBackend()  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        AnthropicBackend("claude-sonnet-4-6", client=MagicMock())  # type: ignore[misc]

    backend = AnthropicBackend(model="claude-sonnet-4-6", client=MagicMock())
    assert backend.model == "claude-sonnet-4-6"


def test_anthropic_backend_constructor_defaults_match_spec() -> None:
    """Spec §6 defaults: thinking_budget_tokens=5000, mechanism='output_config',
    prompt_builder defaults to prompt_anthropic.build_intake_prompt."""
    from unittest.mock import MagicMock

    from trust_generator.v3.extraction.anthropic_backend import AnthropicBackend
    from trust_generator.v3.extraction.prompt_anthropic import build_intake_prompt

    backend = AnthropicBackend(model="claude-sonnet-4-6", client=MagicMock())
    assert backend.thinking_budget_tokens == 5000
    assert backend.mechanism == "output_config"
    assert backend.prompt_builder is build_intake_prompt


def test_anthropic_backend_accepts_injected_client() -> None:
    from unittest.mock import MagicMock

    from trust_generator.v3.extraction.anthropic_backend import AnthropicBackend

    injected = MagicMock()
    backend = AnthropicBackend(model="claude-sonnet-4-6", client=injected)
    assert backend.client is injected


def test_anthropic_backend_accepts_mechanism_choice() -> None:
    """Both literal values accepted; invalid mechanism reaches the type
    checker but at runtime the constructor simply stores the value."""
    from unittest.mock import MagicMock

    from trust_generator.v3.extraction.anthropic_backend import AnthropicBackend

    a = AnthropicBackend(
        model="claude-sonnet-4-6", client=MagicMock(), mechanism="tool_use"
    )
    b = AnthropicBackend(
        model="claude-sonnet-4-6", client=MagicMock(), mechanism="output_config"
    )
    assert a.mechanism == "tool_use"
    assert b.mechanism == "output_config"


def test_anthropic_backend_accepts_custom_prompt_builder() -> None:
    from unittest.mock import MagicMock

    from trust_generator.v3.extraction.anthropic_backend import AnthropicBackend

    custom = lambda: "custom-prompt"  # noqa: E731
    backend = AnthropicBackend(
        model="claude-sonnet-4-6", client=MagicMock(), prompt_builder=custom
    )
    assert backend.prompt_builder is custom


def test_anthropic_backend_accepts_thinking_budget_override() -> None:
    from unittest.mock import MagicMock

    from trust_generator.v3.extraction.anthropic_backend import AnthropicBackend

    backend = AnthropicBackend(
        model="claude-sonnet-4-6",
        client=MagicMock(),
        thinking_budget_tokens=8000,
    )
    assert backend.thinking_budget_tokens == 8000


def test_anthropic_sdk_is_pinned_in_pyproject() -> None:
    """The `anthropic` package appears in pyproject.toml's `dependencies`.

    Defense against accidental removal during a future merge / rebase.
    The exact version pin is whatever Cycle 4 committed (see commit
    message); this test only asserts the package is declared.

    Path resolution: ``pixi run test`` sets cwd to ``tests/``; ``__file__``
    is the only stable anchor. ``parents[3]`` is the repo root
    (parents[0]=extraction, [1]=v3, [2]=tests, [3]=repo root).
    """
    import tomllib
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[3]
    pyproject = tomllib.loads(
        (repo_root / "pyproject.toml").read_text(encoding="utf-8")
    )
    deps = pyproject["project"]["dependencies"]
    assert any(d.startswith("anthropic") for d in deps), (
        f"anthropic SDK not declared in [project].dependencies: {deps}"
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pixi run test -- tests/v3/extraction/test_anthropic_backend.py -v`

Expected: `ImportError: cannot import name 'AnthropicBackend' ...` on the first new test; the `test_anthropic_sdk_is_pinned_in_pyproject` test fails the assertion.

- [ ] **Step 3: Add the SDK pin to `pyproject.toml`**

Edit `pyproject.toml` line 11. Current content:

```toml
dependencies    = ["python-docx", "pydantic>=2", "reportlab", "pypdf>=4", "ollama>=0.6.1"]
```

After SDK feature-coverage verification (see SDK pin procedure above), replace with:

```toml
dependencies    = ["python-docx", "pydantic>=2", "reportlab", "pypdf>=4", "ollama>=0.6.1", "anthropic>=<verified-version>"]
```

Where `<verified-version>` is the lowest GA version satisfying §5's four-feature coverage. The plan-md does NOT name a specific version number — the pin is committed during execution after live verification.

Run `pixi install` (or whatever the pixi env-refresh equivalent is in the execution context) to bring the dependency into the env.

- [ ] **Step 4: Implement `AnthropicBackend.__init__` (Green)**

Append to `src/trust_generator/v3/extraction/anthropic_backend.py`:

```python
from collections.abc import Callable
from typing import TYPE_CHECKING, Literal

import anthropic

from trust_generator.v3.extraction.prompt_anthropic import build_intake_prompt

if TYPE_CHECKING:
    from trust_generator.v3.extraction.protocol import SourceRef


class AnthropicBackend:
    """ExtractionProtocol implementation against Anthropic's Claude API.

    Spec §6. Production-facing extraction backend; sibling to
    OllamaBackend (dev-only). Always-on extended thinking; adaptive
    retry deferred to Plan B per spec §2 *Out of scope*. The
    injectable ``client`` parameter is the construction seam Plan B
    relies on.

    The default ``mechanism="output_config"`` reflects spec §1 + §8.4's
    commitment that ``output_config`` composes with extended thinking.
    If the §8.4 verification gate flips to "incompatible" at the live
    API (cycles in the sibling plan ``instrumentation`` exercise the
    call-args assertions), the fallback is a single-line edit here to
    ``mechanism="tool_use"`` — no structural changes to the seam.
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
        self.model = model
        self.thinking_budget_tokens = thinking_budget_tokens
        self.mechanism = mechanism
        self.prompt_builder = (
            prompt_builder if prompt_builder is not None else build_intake_prompt
        )
        self.client = (
            client if client is not None else anthropic.Anthropic(api_key=api_key)
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pixi run test -- tests/v3/extraction/test_anthropic_backend.py -v` — all constructor tests PASS plus the pyproject SDK-pin test.

Run: `pixi run check` — gate stays green (including mypy clearing on the new `anthropic` import).

- [ ] **Step 6: Commit Red**

```bash
git add tests/v3/extraction/test_anthropic_backend.py
git commit -m "test(v3/extraction): pin AnthropicBackend.__init__ surface (Red, cycle 4)"
```

- [ ] **Step 7: Commit Green (pin + ctor in one Green commit)**

```bash
git add pyproject.toml src/trust_generator/v3/extraction/anthropic_backend.py
git commit -m "feat(v3/extraction): add anthropic SDK pin + AnthropicBackend.__init__ (Green, cycle 4)"
```

- [ ] **Step 8: Memory-entity observation update (out-of-file blast-radius)**

Invoke `mcp__memory__add_observations` on entity `library_selections`. Observation text suggestion:

```
anthropic SDK pinned at >=<version> in plan-group 2026-05-14-anthropic-extraction-backend, child plan core (cycle 4). Verified features at pin time: PDF document content block, extended thinking (thinking={"type": "enabled", "budget_tokens": N}), prompt-caching cache_control breakpoints (system + content blocks), structured-output mechanisms tool_use + output_config GA. Sibling pin: ollama>=0.6.1 (development-only backend per project_extraction_backend_split.md).
```

If the memory tools are unavailable in the executor's environment, surface the update as a chore-entry suggestion to the lead at end-of-cycle and continue. Do not block on the entity update. If `mcp__memory__add_observations` fails because the `library_selections` entity does not exist in this project's graph yet, fall back to `mcp__memory__create_entities` to seed it (entity type: `library-selection-summary`; the observation above as the first observation), then proceed.

---

## Cycle 5 — `_invoke_envelope_call` seam: tool_use path

**Files:**
- Modify: `src/trust_generator/v3/extraction/anthropic_backend.py` (add `_invoke_envelope_call` method + tool_use branch)
- Test: `tests/v3/extraction/test_anthropic_backend.py` (append)

**Threshold verdicts:**
- design_surface_threshold: non-obvious failure modes (locate tool_use block in a content-block list; refusal-shape disambiguation under `tool_choice="auto"`). Satisfies the criterion.
- refactor_threshold: **none met — green output is already minimal**. The tool_use branch is a single linear flow.

**Spec §3 / §8.4 gate accommodation (see "Spec §3 plan-authoring verification gates" section above):** This cycle's tests assert response-handling and `tool_choice == {"type": "auto"}` (spec §1, §8.4 — forced `tool_choice` is incompatible with extended thinking). The cycle ALREADY wires `thinking` and `cache_control` into the `messages.create` kwargs; the assertion for those kwargs lives in the sibling plan `instrumentation` cycle 11 + 12. If the §8.4 gate flips at instrumentation-time, the absorption is a single-line edit to Cycle 4's default — no change to this cycle's seam structure.

**`max_tokens` decision (executor-set, not spec-pinned):** The spec §8.1 data flow does not pin `max_tokens` for `messages.create`. The Green-phase code below uses `max_tokens=8192` as a working default sized for the envelope's expected output (the envelope is small; the bulk of generation budget goes to extended-thinking content which the SDK accounts separately). The executor adjusts at verification time if the SDK requires a different ceiling (some SDK versions require `max_tokens` to exceed `thinking_budget_tokens`). If the decision turns into a parameter the consumer layer needs to tune, surface as a chore-entry suggestion — do not silently widen the constructor.

- [ ] **Step 1: Write the failing tests (Red)**

Append:

```python
def _make_mock_anthropic_message_with_tool_use(envelope_dict: dict) -> object:
    """Construct a mock anthropic.types.Message with a tool_use content block.

    Spec §9.3 mocking convention. Returns a MagicMock shaped to match
    the SDK's Message type (`stop_reason`, `content` list with blocks
    each carrying `type` discriminator).
    """
    from unittest.mock import MagicMock

    tool_use_block = MagicMock()
    tool_use_block.type = "tool_use"
    tool_use_block.name = "submit_intake_extraction"
    tool_use_block.input = envelope_dict

    response = MagicMock()
    response.stop_reason = "tool_use"
    response.content = [tool_use_block]
    return response


def test_invoke_envelope_call_tool_use_returns_input_dict() -> None:
    """tool_use mode: seam returns the tool_use block's `input` as dict."""
    from unittest.mock import MagicMock

    from trust_generator.v3.extraction.anthropic_backend import (
        AnthropicBackend,
        AnthropicGenerationEnvelope,
    )

    envelope_dict = {"grantors": [], "beneficiaries": []}
    client = MagicMock()
    client.messages.create.return_value = (
        _make_mock_anthropic_message_with_tool_use(envelope_dict)
    )
    backend = AnthropicBackend(
        model="claude-sonnet-4-6", client=client, mechanism="tool_use"
    )

    schema = AnthropicGenerationEnvelope.model_json_schema()
    out = backend._invoke_envelope_call(
        system="sys-prompt",
        user_msg={"role": "user", "content": [{"type": "text", "text": "x"}]},
        schema=schema,
    )

    assert out == envelope_dict


def test_invoke_envelope_call_tool_use_passes_tool_choice_auto() -> None:
    """Spec §1, §8.4: tool_choice MUST be `{"type": "auto"}` — forced
    `{"type": "tool", ...}` or `{"type": "any"}` is incompatible with
    extended thinking and would raise at the API.
    """
    from unittest.mock import MagicMock

    from trust_generator.v3.extraction.anthropic_backend import (
        AnthropicBackend,
        AnthropicGenerationEnvelope,
    )

    client = MagicMock()
    client.messages.create.return_value = (
        _make_mock_anthropic_message_with_tool_use({"grantors": [], "beneficiaries": []})
    )
    backend = AnthropicBackend(
        model="claude-sonnet-4-6", client=client, mechanism="tool_use"
    )

    backend._invoke_envelope_call(
        system="sys",
        user_msg={"role": "user", "content": []},
        schema=AnthropicGenerationEnvelope.model_json_schema(),
    )

    _, kwargs = client.messages.create.call_args
    assert kwargs["tool_choice"] == {"type": "auto"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pixi run test -- tests/v3/extraction/test_anthropic_backend.py::test_invoke_envelope_call_tool_use_returns_input_dict -v`

Expected: `AttributeError: 'AnthropicBackend' object has no attribute '_invoke_envelope_call'`.

- [ ] **Step 3: Write minimal implementation (Green)**

Add the seam method to `AnthropicBackend`:

```python
    def _invoke_envelope_call(
        self, *, system: str, user_msg: dict, schema: dict
    ) -> dict:
        """Mechanism-agnostic structured-output seam.

        Spec §8.4: ``output_config`` is the working default; ``tool_use``
        is supported as a fallback. Both paths pass extended thinking
        unconditionally. Refusal under either mechanism (no tool_use
        block or non-JSON text) raises ExtractionError (mapped in
        cycles 10e / 10f below).

        Plan-authoring verification gates §8.2 + §8.4 are accommodated
        structurally: the gate outcomes only affect the constructor
        default mechanism and the instrumentation cycle 11 + 12 call-args
        assertions; the seam structure here is gate-outcome-agnostic.
        """
        if self.mechanism == "tool_use":
            response = self.client.messages.create(
                model=self.model,
                system=[
                    {
                        "type": "text",
                        "text": system,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[user_msg],
                tools=[
                    {
                        "name": "submit_intake_extraction",
                        "description": (
                            "Submit the extracted intake form fields as a structured "
                            "envelope."
                        ),
                        "input_schema": schema,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                tool_choice={"type": "auto"},
                thinking={
                    "type": "enabled",
                    "budget_tokens": self.thinking_budget_tokens,
                },
                max_tokens=8192,
            )
            for block in response.content:
                if getattr(block, "type", None) == "tool_use":
                    return dict(block.input)
            # Refusal under auto-choice: no tool_use block emitted.
            # Cycle 10e tightens this message to include stop_reason; the
            # Cycle 5 placeholder is deliberately generic so Cycle 10e's
            # Red ("end_turn" substring assertion) fails meaningfully
            # against pre-10e state.
            from trust_generator.v3.extraction.protocol import ExtractionError

            raise ExtractionError("model returned no structured tool_use block")

        # output_config branch lands in cycle 6.
        msg = f"unsupported mechanism: {self.mechanism!r}"
        raise NotImplementedError(msg)
```

(The `output_config` branch is intentionally a stub until Cycle 6 fills it. The Cycle 5 tests only exercise `mechanism="tool_use"`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pixi run test -- tests/v3/extraction/test_anthropic_backend.py -v` — all Cycle 5 tests PASS; earlier cycles stay green.

Run: `pixi run check` — gate stays green.

- [ ] **Step 5: Commit Red**

```bash
git add tests/v3/extraction/test_anthropic_backend.py
git commit -m "test(v3/extraction): pin _invoke_envelope_call tool_use path (Red, cycle 5)"
```

- [ ] **Step 6: Commit Green**

```bash
git add src/trust_generator/v3/extraction/anthropic_backend.py
git commit -m "feat(v3/extraction): implement _invoke_envelope_call tool_use branch (Green, cycle 5)"
```

---

## Cycle 6 — `_invoke_envelope_call` seam: output_config path

**Files:**
- Modify: `src/trust_generator/v3/extraction/anthropic_backend.py` (replace stub with output_config branch)
- Test: `tests/v3/extraction/test_anthropic_backend.py` (append)

**Threshold verdicts:**
- design_surface_threshold: composition of two units (request construction + JSON-parse of the text response); satisfies the criterion.
- refactor_threshold: **conditional — Green-phase code may have orthogonal concerns (request construction vs. response parsing) that extract cleanly into two helpers; assess after Green**. If extraction would yield a clearer mental model and the resulting helpers are individually testable, factor; otherwise inline.

**Spec §3 / §8.2 + §8.4 gate accommodation:** This cycle's tests assert that the seam returns the parsed dict from the text block; they do NOT assert `cache_control` placement on `output_config.format` (gated to instrumentation cycle 11, contingent on §8.2 verification) nor `thinking` kwargs (gated to instrumentation cycle 12). The seam ALREADY wires both into the call regardless of gate outcomes; instrumentation tightens the assertions.

- [ ] **Step 1: Write the failing tests (Red)**

Append:

```python
def _make_mock_anthropic_message_with_text(json_text: str) -> object:
    """Construct a mock anthropic.types.Message with a single text block."""
    from unittest.mock import MagicMock

    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = json_text

    response = MagicMock()
    response.stop_reason = "end_turn"
    response.content = [text_block]
    return response


def test_invoke_envelope_call_output_config_parses_text_block_json() -> None:
    """output_config mode: seam json.loads the final text block."""
    import json
    from unittest.mock import MagicMock

    from trust_generator.v3.extraction.anthropic_backend import (
        AnthropicBackend,
        AnthropicGenerationEnvelope,
    )

    envelope_dict = {"grantors": [], "beneficiaries": []}
    client = MagicMock()
    client.messages.create.return_value = (
        _make_mock_anthropic_message_with_text(json.dumps(envelope_dict))
    )
    backend = AnthropicBackend(
        model="claude-sonnet-4-6", client=client, mechanism="output_config"
    )

    out = backend._invoke_envelope_call(
        system="sys",
        user_msg={"role": "user", "content": []},
        schema=AnthropicGenerationEnvelope.model_json_schema(),
    )

    assert out == envelope_dict


def test_invoke_envelope_call_output_config_passes_output_config_kwarg() -> None:
    """output_config mode constructs ``output_config={"format": {...}}``."""
    import json
    from unittest.mock import MagicMock

    from trust_generator.v3.extraction.anthropic_backend import (
        AnthropicBackend,
        AnthropicGenerationEnvelope,
    )

    client = MagicMock()
    client.messages.create.return_value = (
        _make_mock_anthropic_message_with_text(
            json.dumps({"grantors": [], "beneficiaries": []})
        )
    )
    backend = AnthropicBackend(
        model="claude-sonnet-4-6", client=client, mechanism="output_config"
    )
    schema = AnthropicGenerationEnvelope.model_json_schema()

    backend._invoke_envelope_call(
        system="sys",
        user_msg={"role": "user", "content": []},
        schema=schema,
    )

    _, kwargs = client.messages.create.call_args
    output_config = kwargs["output_config"]
    assert output_config["format"]["type"] == "json_schema"
    assert output_config["format"]["schema"] == schema


def test_invoke_envelope_call_output_config_does_not_pass_tools_or_tool_choice() -> None:
    """output_config mode: no tools array, no tool_choice."""
    import json
    from unittest.mock import MagicMock

    from trust_generator.v3.extraction.anthropic_backend import (
        AnthropicBackend,
        AnthropicGenerationEnvelope,
    )

    client = MagicMock()
    client.messages.create.return_value = (
        _make_mock_anthropic_message_with_text(
            json.dumps({"grantors": [], "beneficiaries": []})
        )
    )
    backend = AnthropicBackend(
        model="claude-sonnet-4-6", client=client, mechanism="output_config"
    )

    backend._invoke_envelope_call(
        system="sys",
        user_msg={"role": "user", "content": []},
        schema=AnthropicGenerationEnvelope.model_json_schema(),
    )

    _, kwargs = client.messages.create.call_args
    assert "tools" not in kwargs
    assert "tool_choice" not in kwargs
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pixi run test -- tests/v3/extraction/test_anthropic_backend.py::test_invoke_envelope_call_output_config_parses_text_block_json -v`

Expected: `NotImplementedError: unsupported mechanism: 'output_config'`.

- [ ] **Step 3: Write minimal implementation (Green)**

Replace the `output_config` stub in `_invoke_envelope_call` with the actual branch:

```python
        # output_config branch.
        import json as _json

        response = self.client.messages.create(
            model=self.model,
            system=[
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[user_msg],
            output_config={
                "format": {"type": "json_schema", "schema": schema},
            },
            thinking={
                "type": "enabled",
                "budget_tokens": self.thinking_budget_tokens,
            },
            max_tokens=8192,
        )
        text_chunks: list[str] = []
        for block in response.content:
            if getattr(block, "type", None) == "text":
                text_chunks.append(block.text)
        joined = "".join(text_chunks)
        try:
            parsed = _json.loads(joined)
        except _json.JSONDecodeError as e:
            # Cycle 10e tightens this message to include the substring
            # "JSON" (the cycle 10e Red asserts a case-insensitive "json"
            # match). The Cycle 6 placeholder is deliberately generic so
            # 10e's Red fails meaningfully against pre-10e state.
            from trust_generator.v3.extraction.protocol import ExtractionError

            raise ExtractionError("text-block did not decode to structured output") from e
        if not isinstance(parsed, dict):
            from trust_generator.v3.extraction.protocol import ExtractionError

            raise ExtractionError("text-block decoded to non-mapping payload")
        return parsed
```

(Remove the `NotImplementedError` stub from Cycle 5; the seam now handles both branches.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pixi run test -- tests/v3/extraction/test_anthropic_backend.py -v` — all Cycle 6 tests PASS; Cycle 5 stays green.

Run: `pixi run check` — gate stays green.

- [ ] **Step 5: Commit Red**

```bash
git add tests/v3/extraction/test_anthropic_backend.py
git commit -m "test(v3/extraction): pin _invoke_envelope_call output_config path (Red, cycle 6)"
```

- [ ] **Step 6: Commit Green**

```bash
git add src/trust_generator/v3/extraction/anthropic_backend.py
git commit -m "feat(v3/extraction): implement _invoke_envelope_call output_config branch (Green, cycle 6)"
```

- [ ] **Step 7 (conditional): Refactor**

If `_invoke_envelope_call`'s two branches share enough request-construction (system block dict literal, max_tokens, thinking kwargs) that a small helper `_make_base_kwargs(system: str, user_msg: dict) -> dict` would clarify the dispatch, factor and commit:

```bash
git commit -m "refactor(v3/extraction): factor _make_base_kwargs in _invoke_envelope_call"
```

Otherwise: "no refactor stage — green output is already minimal (the two branches diverge sufficiently that shared request-kwargs would obscure the mechanism distinction)."

---

## Cycle 7 — `AnthropicBackend.extract` happy path (end-to-end, parametrized over both mechanisms)

**Files:**
- Modify: `src/trust_generator/v3/extraction/anthropic_backend.py` (add `extract`, `_load_pdf_or_image` minimal PDF branch, `_build_system_prompt`, `_build_user_message` PDF branch)
- Modify: `src/trust_generator/v3/extraction/__init__.py` (export `AnthropicBackend`)
- Test: `tests/v3/extraction/test_anthropic_backend.py` (append)

**Threshold verdicts:**
- design_surface_threshold: integration site — composes `_load_pdf_or_image` + `_build_system_prompt` + `_build_user_message` + `_invoke_envelope_call` + `AnthropicGenerationEnvelope.model_validate` + `_anthropic_envelope_to_extraction_result`. Satisfies the criterion.
- refactor_threshold: **conditional — `extract` is the integration site; if the Green-phase code mixes orthogonal concerns (source-loading, prompt assembly, API invocation, mapping) without clear delineation, factor**. The seam-method skeleton naturally suggests four phases; if the Green-phase body is already a clean linear composition of four helper calls, no refactor is needed.

**Out-of-scope to instrumentation:** PDF size + page-count prechecks (cycle 8); image source branch in `_load_pdf_or_image` + `_build_user_message` (cycle 9). This cycle's `_load_pdf_or_image` handles **PDF only, no prechecks**; tests use a minimally-mockable PDF source so the mocked client never actually consumes file bytes.

- [ ] **Step 1: Write the failing tests (Red)**

Append:

```python
def _make_pdf_fixture(tmp_path) -> object:
    """Write a minimal PDF byte sequence to a tmp path. The file is
    only opened for base64 encoding inside _load_pdf_or_image; the
    mocked client never reads the bytes back, so a stub %PDF header
    suffices for both branches."""
    p = tmp_path / "intake.pdf"
    # Smallest valid-ish PDF header; pypdf is not invoked in this
    # cycle (page-count precheck lands in instrumentation cycle 8).
    p.write_bytes(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    return p


@pytest.mark.parametrize("mechanism", ["tool_use", "output_config"])
def test_anthropic_backend_extract_happy_path(tmp_path, mechanism: str) -> None:
    """End-to-end extract() returns an ExtractionResult through both mechanisms.

    Asserts: TrustData.grantor.full_legal_name reflects envelope[0]
    positional mapping; backend_id is f"anthropic:{model}"; trace.fields
    is populated; ExtractionTrace consumable identically across
    mechanisms.
    """
    import json
    from unittest.mock import MagicMock

    from trust_generator.v3.extraction import ExtractionResult
    from trust_generator.v3.extraction.anthropic_backend import AnthropicBackend

    envelope_dict = {
        "grantors": [
            {"full_legal_name": "Alice Tester"},
            {"full_legal_name": "Bob Tester"},
        ],
        "beneficiaries": [
            {"full_legal_name": "Charlie Child", "share_percent": "100"},
        ],
    }

    client = MagicMock()
    if mechanism == "tool_use":
        client.messages.create.return_value = (
            _make_mock_anthropic_message_with_tool_use(envelope_dict)
        )
    else:
        client.messages.create.return_value = (
            _make_mock_anthropic_message_with_text(json.dumps(envelope_dict))
        )

    backend = AnthropicBackend(
        model="claude-sonnet-4-6", client=client, mechanism=mechanism
    )
    pdf = _make_pdf_fixture(tmp_path)

    result = backend.extract(pdf)

    assert isinstance(result, ExtractionResult)
    assert result.trace.backend_id == "anthropic:claude-sonnet-4-6"
    assert result.data.co_grantor is not None  # two grantors in envelope
    assert len(result.data.other_beneficiaries) == 1
    paths = {f.field_path for f in result.trace.fields}
    assert "grantor.full_legal_name" in paths
    assert "co_grantor.full_legal_name" in paths
    assert "other_beneficiaries[0].full_legal_name" in paths
    assert "beneficiary_shares[0].share_percent" in paths

    # Mechanism-specific kwarg presence on messages.create. MagicMock
    # accepts any kwarg silently — without this assertion a typo in
    # the seam (e.g., "output_configs", "tool_uses") would surface
    # only at live-API time. Cycles 5/6 cover the seam units; this is
    # the integration-site safety net.
    _, kwargs = client.messages.create.call_args
    if mechanism == "output_config":
        assert "output_config" in kwargs
        assert "tools" not in kwargs and "tool_choice" not in kwargs
    else:
        assert "tools" in kwargs
        assert kwargs["tool_choice"] == {"type": "auto"}


def test_anthropic_backend_extract_invokes_messages_create_once(tmp_path) -> None:
    """Single call per extract() (no auto-retry in v1 per spec §2)."""
    import json
    from unittest.mock import MagicMock

    from trust_generator.v3.extraction.anthropic_backend import AnthropicBackend

    client = MagicMock()
    client.messages.create.return_value = (
        _make_mock_anthropic_message_with_text(
            json.dumps({"grantors": [], "beneficiaries": []})
        )
    )
    backend = AnthropicBackend(
        model="claude-sonnet-4-6", client=client, mechanism="output_config"
    )
    pdf = _make_pdf_fixture(tmp_path)

    backend.extract(pdf)

    assert client.messages.create.call_count == 1


def test_anthropic_backend_exported_from_extraction_package() -> None:
    """AnthropicBackend is importable from the extraction package
    and listed in __all__, mirroring OllamaBackend."""
    from trust_generator.v3 import extraction

    assert hasattr(extraction, "AnthropicBackend")
    assert "AnthropicBackend" in extraction.__all__
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pixi run test -- tests/v3/extraction/test_anthropic_backend.py -v`

Expected: `AttributeError: 'AnthropicBackend' object has no attribute 'extract'` for the parametrized cases, plus the `extraction.AnthropicBackend` import failure.

- [ ] **Step 3: Write minimal implementation (Green)**

Append to `AnthropicBackend` (the class body):

```python
    def extract(self, source: SourceRef) -> ExtractionResult:
        """Extract a (TrustData, ExtractionTrace) pair from one source.

        Spec §5.4 + §8.1. Failure modes raise ``ExtractionError``;
        per-field illegibility is a success-path trace entry.

        This cycle implements the PDF path with no size/page-count
        prechecks; the prechecks land in the sibling plan
        ``instrumentation`` (cycle 8). The image-source branch lands
        in ``instrumentation`` cycle 9.
        """
        mime, b64 = self._load_pdf_or_image(source)
        system = self._build_system_prompt()
        user_msg = self._build_user_message(mime, b64)

        try:
            raw = self._invoke_envelope_call(
                system=system,
                user_msg=user_msg,
                schema=AnthropicGenerationEnvelope.model_json_schema(),
            )
        except anthropic.APIError as e:
            # Specific subclass mapping lands in cycles 10a–10d below;
            # this catch-site is the dispatch point.
            raise _wrap_anthropic_error(e) from e

        try:
            envelope = AnthropicGenerationEnvelope.model_validate(raw)
        except ValidationError as e:
            # Cycle 10f tightens this message to include the substring
            # "envelope" / "schema-invalid". The Cycle 7 placeholder is
            # deliberately generic so 10f's Red fails meaningfully against
            # pre-10f state. Note that ``str(e)`` includes the class name
            # "AnthropicGenerationEnvelope" — to keep the placeholder
            # truly substring-free for 10f, we do NOT inline ``{e}`` here;
            # the cause stays available via ``__cause__``.
            raise ExtractionError("Anthropic SDK returned malformed structured output") from e

        return _anthropic_envelope_to_extraction_result(envelope, model=self.model)

    def _load_pdf_or_image(self, source: SourceRef) -> tuple[str, str]:
        """Return (mime_type, base64_data). Spec §8.1.

        This cycle handles PDF only with no prechecks. Image branch and
        size/page-count prechecks land in the sibling plan
        ``instrumentation`` (cycles 9 + 8).
        """
        import base64
        import mimetypes

        if not source.exists():
            raise ExtractionError(f"source path not found: {source}")
        mime, _ = mimetypes.guess_type(str(source))
        if mime != "application/pdf":
            # Image branch is instrumentation cycle 9's responsibility;
            # core's _load_pdf_or_image rejects non-PDF until that lands.
            raise ExtractionError(
                f"unsupported source mime-type for core path: {mime!r}"
            )
        with source.open("rb") as fh:
            data_bytes = fh.read()
        b64 = base64.standard_b64encode(data_bytes).decode("ascii")
        return mime, b64

    def _build_system_prompt(self) -> str:
        return self.prompt_builder()

    def _build_user_message(self, mime: str, b64: str) -> dict:
        """Construct the user-message dict carrying the document content block.

        Spec §8.1: PDF path; image branch deferred to instrumentation
        cycle 9. ``cache_control`` placement on the document block is
        the §8.2 breakpoint 2; the assertion lives in instrumentation
        cycle 11.
        """
        return {
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": mime,
                        "data": b64,
                    },
                    "cache_control": {"type": "ephemeral"},
                }
            ],
        }
```

Add the top-level imports needed (`anthropic`, `ValidationError`, `ExtractionError`) — re-arrange the file's imports so they sit cleanly at the top:

```python
from __future__ import annotations

import anthropic
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from trust_generator.v3.extraction.protocol import ExtractionError
from trust_generator.v3.extraction.prompt_anthropic import build_intake_prompt
```

Add the (yet-empty) `_wrap_anthropic_error` helper as a module-level forward declaration — it will be implemented in cycles 10a–10d. For Cycle 7 it can be the trivial identity-wrap below; cycle 10a tests will subsume this:

```python
def _wrap_anthropic_error(exc: anthropic.APIError) -> ExtractionError:
    """Translate an anthropic.APIError into an ExtractionError.

    Spec §8.5 *ExtractionError message hygiene*: preserve the cause's
    class name and a sanitized excerpt; MUST NOT serialize the api_key
    substring, request headers, or the full ``repr()`` of the cause.

    Cycles 10a–10d add subclass-specific mapping (APIConnectionError,
    RateLimitError, AuthenticationError, generic APIError). This Cycle 7
    placeholder is deliberately generic — it omits the subclass class
    name so cycles 10a/10c can Red-fail meaningfully (their assertions
    look for subclass-specific substrings like ``"connection"`` or
    ``"authentication"`` that the placeholder must NOT contain).
    """
    return ExtractionError("Anthropic SDK call failed")
```

Edit `src/trust_generator/v3/extraction/__init__.py` to export `AnthropicBackend`. Maintain alphabetical order to satisfy RUF022:

```python
"""OCR extraction surface — markers, trace, Protocol, and helpers.

Public surface declared in ``__all__``; the ``INCOMPLETE`` sentinel is
intentionally NOT exported (per spec §5.3 — consumers import it
explicitly to make the in-memory-identity discipline visible).
"""

from __future__ import annotations

from trust_generator.v3.extraction.anthropic_backend import AnthropicBackend
from trust_generator.v3.extraction.markers import (
    IncompleteUntilValidated,
    RawSelfReport,
)
from trust_generator.v3.extraction.ollama_backend import OllamaBackend
from trust_generator.v3.extraction.paths import resolve
from trust_generator.v3.extraction.protocol import (
    ExtractionError,
    ExtractionProtocol,
    SourceRef,
)
from trust_generator.v3.extraction.synthesis import synthesize_extraction_diagnostics
from trust_generator.v3.extraction.trace import (
    ExtractionResult,
    ExtractionTrace,
    FieldExtraction,
)

__all__ = (
    "AnthropicBackend",
    "ExtractionError",
    "ExtractionProtocol",
    "ExtractionResult",
    "ExtractionTrace",
    "FieldExtraction",
    "IncompleteUntilValidated",
    "OllamaBackend",
    "RawSelfReport",
    "SourceRef",
    "resolve",
    "synthesize_extraction_diagnostics",
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pixi run test -- tests/v3/extraction/test_anthropic_backend.py -v` — both parametrized happy-path tests + the call-count test + the export test PASS.

Run: `pixi run test -- tests/v3/extraction/ -v` — sibling Ollama test files stay green (the prompt-relocation safety net + the package-export integrity).

Run: `pixi run check` — full gate (lint + mypy + test) stays green.

- [ ] **Step 5: Commit Red**

```bash
git add tests/v3/extraction/test_anthropic_backend.py
git commit -m "test(v3/extraction): pin AnthropicBackend.extract happy path (Red, cycle 7)"
```

- [ ] **Step 6: Commit Green**

```bash
git add src/trust_generator/v3/extraction/anthropic_backend.py src/trust_generator/v3/extraction/__init__.py
git commit -m "feat(v3/extraction): wire AnthropicBackend.extract end-to-end (Green, cycle 7)"
```

- [ ] **Step 7 (conditional): Refactor**

If `extract`'s body mixes phases (loading, prompt assembly, API call, parsing, mapping) without clear delineation, no further structural extraction is needed because each phase is already a single line calling a helper. If the helper bodies grew during Green (especially `_load_pdf_or_image`), revisit and commit:

```bash
git commit -m "refactor(v3/extraction): clarify extract pipeline structure"
```

Otherwise: "no refactor stage — extract() is already a five-statement linear composition; further extraction would defeat the readability gain."

---

## Cycle 10a — Error mapping: `anthropic.APIConnectionError`

**Files:**
- Modify: `src/trust_generator/v3/extraction/anthropic_backend.py` (`_wrap_anthropic_error` dispatch)
- Test: `tests/v3/extraction/test_anthropic_backend.py` (append)

**Threshold verdicts:**
- design_surface_threshold: contract surface (paralegals see the wrapped message; api_key leak is a security concern). Satisfies the criterion.
- refactor_threshold: **none met for 10a individually**. The dispatch consolidation across 10a–10d lands as a single Refactor stage at the end of 10d.

- [ ] **Step 1: Write the failing tests (Red)**

Append:

```python
def _make_failing_client(error: Exception) -> object:
    """Construct a MagicMock-shaped anthropic.Anthropic whose
    messages.create raises ``error``.

    Spec §9.3 mocking convention: ``MagicMock(spec=anthropic.Anthropic)``
    catches typos in the SDK surface (a future rename of ``create``
    would fail the spec check). The same convention should retrofit
    the happy-path helpers (``_make_mock_anthropic_message_with_*``)
    introduced in cycles 5/6 — assess as a refactor at end-of-cycle-10d
    when the test-helper surface has stabilized.
    """
    from unittest.mock import MagicMock

    client = MagicMock(spec=anthropic.Anthropic)
    client.messages.create.side_effect = error
    return client


def test_api_connection_error_is_wrapped(tmp_path) -> None:
    """anthropic.APIConnectionError → ExtractionError, chained via __cause__."""
    from trust_generator.v3.extraction import ExtractionError
    from trust_generator.v3.extraction.anthropic_backend import AnthropicBackend

    err = anthropic.APIConnectionError(request=MagicMock(method="POST", url="x"))
    backend = AnthropicBackend(
        model="claude-sonnet-4-6", client=_make_failing_client(err)
    )
    pdf = _make_pdf_fixture(tmp_path)

    with pytest.raises(ExtractionError) as exc_info:
        backend.extract(pdf)

    assert exc_info.value.__cause__ is err
    assert "APIConnectionError" in str(exc_info.value) or "connection" in str(
        exc_info.value
    ).lower()


def test_api_connection_error_message_does_not_leak_api_key(tmp_path) -> None:
    """Spec §8.5 *ExtractionError message hygiene*: api_key substring
    MUST NOT appear in the wrapped error message."""
    from trust_generator.v3.extraction import ExtractionError
    from trust_generator.v3.extraction.anthropic_backend import AnthropicBackend

    secret = "sk-ant-fake-key-do-not-leak-XYZ"
    err = anthropic.APIConnectionError(request=MagicMock())
    backend = AnthropicBackend(
        model="claude-sonnet-4-6",
        api_key=secret,
        client=_make_failing_client(err),
    )
    pdf = _make_pdf_fixture(tmp_path)

    with pytest.raises(ExtractionError) as exc_info:
        backend.extract(pdf)

    assert secret not in str(exc_info.value)
```

Add the import at the top of the test file (alongside the existing `anthropic` and `MagicMock` use sites):

```python
import anthropic
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pixi run test -- tests/v3/extraction/test_anthropic_backend.py::test_api_connection_error_is_wrapped -v`

Expected: **FAIL** — the Cycle 7 placeholder wrap is deliberately generic (`"Anthropic SDK call failed"`); neither `"APIConnectionError"` nor `"connection"` is in the wrapped message, so the substring assertion fails meaningfully. The cause-chain (`__cause__`) assertion would pass (the placeholder already chains via `raise ... from e`), but the substring assertion is the gating Red.

- [ ] **Step 3: Write minimal implementation (Green)**

Replace the trivial `_wrap_anthropic_error` placeholder with a subclass-aware dispatch:

```python
def _wrap_anthropic_error(exc: anthropic.APIError) -> ExtractionError:
    """Translate an anthropic.APIError into an ExtractionError.

    Spec §8.5 *ExtractionError message hygiene*: preserve the cause's
    class name; MUST NOT serialize the api_key, request headers, or
    the full ``repr()`` of the cause.

    Subclass-specific phrasing aids paralegals reading the log; the
    original exception remains accessible via ``__cause__`` for
    debug-time inspection.
    """
    cls_name = type(exc).__name__
    if isinstance(exc, anthropic.APIConnectionError):
        return ExtractionError(
            f"Anthropic network/connection error ({cls_name})"
        )
    return ExtractionError(f"Anthropic API error ({cls_name})")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pixi run test -- tests/v3/extraction/test_anthropic_backend.py -v` — Cycle 10a tests PASS; earlier cycles stay green.

Run: `pixi run check` — gate stays green.

- [ ] **Step 5: Commit Red**

```bash
git add tests/v3/extraction/test_anthropic_backend.py
git commit -m "test(v3/extraction): pin APIConnectionError mapping (Red, cycle 10a)"
```

- [ ] **Step 6: Commit Green**

```bash
git add src/trust_generator/v3/extraction/anthropic_backend.py
git commit -m "feat(v3/extraction): map APIConnectionError to ExtractionError (Green, cycle 10a)"
```

---

## Cycle 10b — Error mapping: `anthropic.RateLimitError`

**Files:** same as 10a.

**Threshold verdicts:**
- design_surface_threshold: contract surface (no-auto-retry semantics is asserted here per spec §8.5). Satisfies.
- refactor_threshold: **none met individually** (single new `isinstance` branch). Consolidation deferred to 10d.

- [ ] **Step 1: Write the failing tests (Red)**

Append:

```python
def test_rate_limit_error_is_wrapped(tmp_path) -> None:
    """anthropic.RateLimitError → ExtractionError, chained, no retry attempted."""
    from unittest.mock import MagicMock

    from trust_generator.v3.extraction import ExtractionError
    from trust_generator.v3.extraction.anthropic_backend import AnthropicBackend

    err = anthropic.RateLimitError(
        message="rate limit", response=MagicMock(status_code=429), body=None
    )
    client = _make_failing_client(err)
    backend = AnthropicBackend(model="claude-sonnet-4-6", client=client)
    pdf = _make_pdf_fixture(tmp_path)

    with pytest.raises(ExtractionError) as exc_info:
        backend.extract(pdf)

    assert exc_info.value.__cause__ is err
    assert client.messages.create.call_count == 1  # no auto-retry


def test_rate_limit_error_message_mentions_rate_limit(tmp_path) -> None:
    from trust_generator.v3.extraction import ExtractionError
    from trust_generator.v3.extraction.anthropic_backend import AnthropicBackend

    err = anthropic.RateLimitError(
        message="rate limit", response=MagicMock(status_code=429), body=None
    )
    backend = AnthropicBackend(
        model="claude-sonnet-4-6", client=_make_failing_client(err)
    )
    pdf = _make_pdf_fixture(tmp_path)

    with pytest.raises(ExtractionError, match="(?i)rate"):
        backend.extract(pdf)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pixi run test -- tests/v3/extraction/test_anthropic_backend.py::test_rate_limit_error_message_mentions_rate_limit -v`

Expected: FAIL — the current `_wrap_anthropic_error` only specializes `APIConnectionError`; `RateLimitError` falls through to the generic wrap whose message does not match `"rate"`.

- [ ] **Step 3: Write minimal implementation (Green)**

Extend `_wrap_anthropic_error` with the RateLimitError branch:

```python
def _wrap_anthropic_error(exc: anthropic.APIError) -> ExtractionError:
    cls_name = type(exc).__name__
    if isinstance(exc, anthropic.APIConnectionError):
        return ExtractionError(
            f"Anthropic network/connection error ({cls_name})"
        )
    if isinstance(exc, anthropic.RateLimitError):
        return ExtractionError(
            f"Anthropic rate limit hit ({cls_name}); no auto-retry attempted"
        )
    return ExtractionError(f"Anthropic API error ({cls_name})")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pixi run test -- tests/v3/extraction/test_anthropic_backend.py -v` — Cycle 10b tests PASS.

Run: `pixi run check` — gate stays green.

- [ ] **Step 5: Commit Red**

```bash
git add tests/v3/extraction/test_anthropic_backend.py
git commit -m "test(v3/extraction): pin RateLimitError mapping (Red, cycle 10b)"
```

- [ ] **Step 6: Commit Green**

```bash
git add src/trust_generator/v3/extraction/anthropic_backend.py
git commit -m "feat(v3/extraction): map RateLimitError to ExtractionError (Green, cycle 10b)"
```

---

## Cycle 10c — Error mapping: `anthropic.AuthenticationError`

**Files:** same as 10a.

**Threshold verdicts:**
- design_surface_threshold: contract surface (api_key non-leak invariant is most acute here — the cause of the error is the key itself). Satisfies.
- refactor_threshold: **none met individually**. Consolidation deferred to 10d.

- [ ] **Step 1: Write the failing tests (Red)**

Append:

```python
def test_authentication_error_is_wrapped(tmp_path) -> None:
    """AuthenticationError → ExtractionError.

    Unlike the other 10a/10b/10d mappings, AuthenticationError uses
    ``raise ... from None`` (NOT ``from err``) to drop the cause-chain
    — the SDK's AuthenticationError carries the bad api_key in its
    own message, which would bleed through every standard log surface
    (``logging.exception``, ``traceback.format_exception``,
    pytest failure rendering) if ``__cause__`` retained ``err``. The
    sibling test ``test_authentication_error_message_does_not_leak_api_key``
    pins this against a traceback-rendered surface.
    """
    from unittest.mock import MagicMock

    from trust_generator.v3.extraction import ExtractionError
    from trust_generator.v3.extraction.anthropic_backend import AnthropicBackend

    err = anthropic.AuthenticationError(
        message="invalid api key",
        response=MagicMock(status_code=401),
        body=None,
    )
    backend = AnthropicBackend(
        model="claude-sonnet-4-6", client=_make_failing_client(err)
    )
    pdf = _make_pdf_fixture(tmp_path)

    with pytest.raises(ExtractionError) as exc_info:
        backend.extract(pdf)

    # AuthenticationError uses ``from None`` — cause-chain is deliberately
    # dropped (see docstring). The cause class name + status are preserved
    # in the wrap message text.
    assert exc_info.value.__cause__ is None
    assert "authentication" in str(exc_info.value).lower()


def test_authentication_error_message_does_not_leak_api_key(tmp_path) -> None:
    """The api_key MUST NOT appear anywhere log-paths walk —
    including ``__cause__``-chain rendering via
    ``traceback.format_exception``. Spec §8.5: the ExtractionError
    message is user-visible (firm-admin logs); the Anthropic SDK's
    AuthenticationError carries the bad key in its OWN message
    (adversarial cause). ``raise ... from None`` is required on the
    AuthenticationError branch to drop the chain — ``str(outer_exc)``
    alone does not check what ``logging.exception()`` /
    ``traceback.format_exception(...)`` render.
    """
    import traceback
    from unittest.mock import MagicMock

    from trust_generator.v3.extraction import ExtractionError
    from trust_generator.v3.extraction.anthropic_backend import AnthropicBackend

    secret = "sk-ant-fake-key-XXXX"
    err = anthropic.AuthenticationError(
        message=f"invalid api key: {secret}",  # adversarial cause-message
        response=MagicMock(status_code=401),
        body=None,
    )
    backend = AnthropicBackend(
        model="claude-sonnet-4-6",
        api_key=secret,
        client=_make_failing_client(err),
    )
    pdf = _make_pdf_fixture(tmp_path)

    with pytest.raises(ExtractionError) as exc_info:
        backend.extract(pdf)

    # Necessary but not sufficient: outer wrap text alone.
    assert secret not in str(exc_info.value)
    # Sufficient: the surface CI logs / paralegal-visible logs walk.
    exc = exc_info.value
    rendered = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    assert secret not in rendered, (
        "api_key leaked through __cause__-chain rendering — "
        "AuthenticationError branch must use ``raise ... from None``"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pixi run test -- tests/v3/extraction/test_anthropic_backend.py::test_authentication_error_is_wrapped -v`

Expected: **FAIL** on `assert "authentication" in str(exc_info.value).lower()` — the Cycle 10b state of `_wrap_anthropic_error` has branches for `APIConnectionError` + `RateLimitError` and falls through to `"Anthropic SDK call failed"` for `AuthenticationError`, which does not contain `"authentication"`. The api_key-non-leak assertion in the sibling test passes (the wrap text contains no key); the substring assertion is the gating Red.

- [ ] **Step 3: Write minimal implementation (Green)**

Extend `_wrap_anthropic_error` AND change the dispatch site so AuthenticationError drops the cause-chain. First, extend the helper (insert after the RateLimitError branch; before the fallthrough):

```python
    if isinstance(exc, anthropic.AuthenticationError):
        # Do NOT serialize the cause's message — its body may contain
        # the api_key per the adversarial test (spec §8.5).
        return ExtractionError(
            f"Anthropic authentication failed ({cls_name}); "
            "check ANTHROPIC_API_KEY"
        )
```

Then update `extract()`'s dispatch so AuthenticationError uses `raise ... from None` (the cause-chain is deliberately dropped — the SDK's AuthenticationError carries the api_key in its own message, which would render through `logging.exception` / `traceback.format_exception`):

```python
        try:
            raw = self._invoke_envelope_call(
                system=system,
                user_msg=user_msg,
                schema=AnthropicGenerationEnvelope.model_json_schema(),
            )
        except anthropic.AuthenticationError as e:
            # Drop the cause-chain: the SDK's AuthenticationError message
            # may contain the api_key adversarially (spec §8.5 hygiene).
            raise _wrap_anthropic_error(e) from None
        except anthropic.APIError as e:
            raise _wrap_anthropic_error(e) from e
```

The catch-order matters: `AuthenticationError` is a subclass of `APIError`, so the specific catch must precede the general one.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pixi run test -- tests/v3/extraction/test_anthropic_backend.py -v` — Cycle 10c tests PASS.

Run: `pixi run check` — gate stays green.

- [ ] **Step 5: Commit Red**

```bash
git add tests/v3/extraction/test_anthropic_backend.py
git commit -m "test(v3/extraction): pin AuthenticationError mapping + api_key non-leak (Red, cycle 10c)"
```

- [ ] **Step 6: Commit Green**

```bash
git add src/trust_generator/v3/extraction/anthropic_backend.py
git commit -m "feat(v3/extraction): map AuthenticationError to ExtractionError (Green, cycle 10c)"
```

---

## Cycle 10d — Error mapping: generic `anthropic.APIError`

**Files:** same as 10a.

**Threshold verdicts:**
- design_surface_threshold: catches the fallthrough; pinned-by-test guarantees all subclasses route through `_wrap_anthropic_error` and not raw.
- refactor_threshold: **conditional — consolidation opportunity after 10a + 10b + 10c land**. The three subclass branches plus this fallthrough form a `isinstance` ladder; if the dispatch becomes long enough that a dict-driven lookup or a `match` statement reads more cleanly, factor.

- [ ] **Step 1: Write the failing tests (Red)**

Append:

```python
def test_generic_api_error_is_wrapped(tmp_path) -> None:
    """A non-specialized anthropic.APIError raises ExtractionError, chained."""
    from unittest.mock import MagicMock

    from trust_generator.v3.extraction import ExtractionError
    from trust_generator.v3.extraction.anthropic_backend import AnthropicBackend

    err = anthropic.APIError(
        message="unexpected", request=MagicMock(), body=None
    )
    backend = AnthropicBackend(
        model="claude-sonnet-4-6", client=_make_failing_client(err)
    )
    pdf = _make_pdf_fixture(tmp_path)

    with pytest.raises(ExtractionError) as exc_info:
        backend.extract(pdf)

    assert exc_info.value.__cause__ is err
    assert "APIError" in str(exc_info.value)
```

- [ ] **Step 2: Run test to verify it fails**

The current `_wrap_anthropic_error` already has a generic fallthrough, so this test likely passes after Cycle 10c. **Strengthen the Red** if needed by asserting the wrapped message includes class-name discriminator or a sanitization tag.

If after strengthening the test passes trivially, this cycle reduces to a regression-pin commit (Red + Green collapse): the wrap already does the right thing; the test ensures it stays that way.

- [ ] **Step 3: Write minimal implementation (Green)**

Already in place; no implementation delta if the test passes against the existing fallthrough. Otherwise, tighten the fallthrough branch's message to satisfy the strengthened assertion.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pixi run test -- tests/v3/extraction/test_anthropic_backend.py -v` — Cycle 10d test PASSES; earlier cycles stay green.

Run: `pixi run check` — gate stays green.

- [ ] **Step 5: Commit Red**

```bash
git add tests/v3/extraction/test_anthropic_backend.py
git commit -m "test(v3/extraction): pin generic APIError fallthrough mapping (Red, cycle 10d)"
```

- [ ] **Step 6: Commit Green**

```bash
git add src/trust_generator/v3/extraction/anthropic_backend.py
git commit -m "feat(v3/extraction): tighten generic APIError mapping (Green, cycle 10d)"
```

(If implementation delta was zero, the Green commit may be a no-op — in which case skip Step 6 and note "no Green delta — fallthrough already satisfies the assertion" in the cycle close-out message.)

- [ ] **Step 7 (conditional): Refactor**

The four subclass branches now form a flat `isinstance` ladder in `_wrap_anthropic_error`. If a dispatch table reads more cleanly:

```python
_ERROR_MESSAGES: dict[type, Callable[[str], str]] = {
    anthropic.APIConnectionError: lambda cls: f"Anthropic network/connection error ({cls})",
    anthropic.RateLimitError: lambda cls: f"Anthropic rate limit hit ({cls}); no auto-retry attempted",
    anthropic.AuthenticationError: lambda cls: (
        f"Anthropic authentication failed ({cls}); check ANTHROPIC_API_KEY"
    ),
}
```

And the lookup short-circuits to the fallthrough on miss — assess after Cycle 10d's Green commit. Commit:

```bash
git commit -m "refactor(v3/extraction): dispatch-table _wrap_anthropic_error"
```

Otherwise: "no refactor stage — the four-branch ladder is already a flat dispatch; extracting a table would obscure the per-subclass phrasing."

---

## Cycle 10e — Refusal: tool_use mode under `tool_choice="auto"`

**Cycle classification: REAL TDD CYCLE.** Cycles 5 + 6 wired refusal-as-`ExtractionError` with deliberately-generic raise-site messages ("model returned no structured tool_use block"; "text-block did not decode to structured output"). This cycle tightens those messages to satisfy spec §8.5's diagnostic contract: tool_use refusal includes `stop_reason` (so paralegals reading the log can distinguish refusal-under-auto-choice from other shapes); output_config refusal explicitly names "JSON" so the parse-failure mode is readable.

**Files:**
- Modify: `src/trust_generator/v3/extraction/anthropic_backend.py` (tighten refusal messages in both seam branches)
- Test: `tests/v3/extraction/test_anthropic_backend.py` (append)

**Threshold verdicts:**
- design_surface_threshold: contract surface (refusal-as-`ExtractionError` is the spec §8.5 hard-error policy; the message content is the user-visible part of that contract per §8.5 *ExtractionError message hygiene*). Satisfies.
- refactor_threshold: **none met — green output is already minimal** (single substring addition per branch).

- [ ] **Step 1: Write the failing tests (Red)**

Append:

```python
def test_tool_use_refusal_under_auto_choice_raises(tmp_path) -> None:
    """No tool_use block in response (stop_reason='end_turn' with text-only
    content) → ExtractionError with stop_reason in message."""
    from unittest.mock import MagicMock

    from trust_generator.v3.extraction import ExtractionError
    from trust_generator.v3.extraction.anthropic_backend import AnthropicBackend

    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "I cannot extract this image."

    response = MagicMock()
    response.stop_reason = "end_turn"
    response.content = [text_block]

    client = MagicMock()
    client.messages.create.return_value = response
    backend = AnthropicBackend(
        model="claude-sonnet-4-6", client=client, mechanism="tool_use"
    )
    pdf = _make_pdf_fixture(tmp_path)

    with pytest.raises(ExtractionError) as exc_info:
        backend.extract(pdf)

    assert "end_turn" in str(exc_info.value)
    assert "submit_intake_extraction" in str(exc_info.value) or "tool_use" in str(
        exc_info.value
    )


def test_output_config_refusal_non_json_raises(tmp_path) -> None:
    """output_config mode + non-JSON text → ExtractionError with JSON parse failure."""
    from unittest.mock import MagicMock

    from trust_generator.v3.extraction import ExtractionError
    from trust_generator.v3.extraction.anthropic_backend import AnthropicBackend

    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "I refuse to process this image."

    response = MagicMock()
    response.stop_reason = "end_turn"
    response.content = [text_block]

    client = MagicMock()
    client.messages.create.return_value = response
    backend = AnthropicBackend(
        model="claude-sonnet-4-6", client=client, mechanism="output_config"
    )
    pdf = _make_pdf_fixture(tmp_path)

    with pytest.raises(ExtractionError, match="(?i)json"):
        backend.extract(pdf)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pixi run test -- tests/v3/extraction/test_anthropic_backend.py::test_tool_use_refusal_under_auto_choice_raises -v`

Expected: **FAIL** on `assert "end_turn" in str(exc_info.value)` — the Cycle 5 placeholder ("model returned no structured tool_use block") does not contain `stop_reason` text. The output_config test in this cycle also FAILS on the `(?i)json` match — Cycle 6's placeholder ("text-block did not decode to structured output") does not contain "JSON".

- [ ] **Step 3: Write minimal implementation (Green)**

Tighten the tool_use refusal raise-site in `_invoke_envelope_call` (the cycle 5 branch):

```python
raise ExtractionError(
    "model did not emit submit_intake_extraction tool_use: "
    f"stop_reason={response.stop_reason!r}"
)
```

Tighten the output_config refusal raise-site (the cycle 6 branch):

```python
head = joined[:120]
raise ExtractionError(
    f"output_config JSON parse failure: {head!r}"
) from e
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pixi run test -- tests/v3/extraction/test_anthropic_backend.py -v`

Run: `pixi run check` — gate stays green.

- [ ] **Step 5: Commit Red**

```bash
git add tests/v3/extraction/test_anthropic_backend.py
git commit -m "test(v3/extraction): pin tool_use + output_config refusal mappings (Red, cycle 10e)"
```

- [ ] **Step 6: Commit Green**

```bash
git add src/trust_generator/v3/extraction/anthropic_backend.py
git commit -m "feat(v3/extraction): include stop_reason + JSON in refusal-error messages (Green, cycle 10e)"
```

---

## Cycle 10f — Schema-invalid envelope (defense-in-depth)

**Cycle classification: REAL TDD CYCLE.** Cycle 7 wired the `ValidationError` wrap with a deliberately-generic raise-site message ("Anthropic SDK returned malformed structured output"). This cycle tightens the message to name the envelope schema and the schema-invalid mode, satisfying spec §8.5's diagnostic contract for the defense-in-depth validation layer (the `extra="forbid"` rationale per spec §6).

**Files:** same as 10e.

**Threshold verdicts:**
- design_surface_threshold: contract surface (schema-validation defense-in-depth even when server-side validation is in play, per spec §6 `extra="forbid"` rationale + §8.5).
- refactor_threshold: **none met — green output is already minimal** (single substring addition).

- [ ] **Step 1: Write the failing tests (Red)**

Append:

```python
def test_tool_use_malformed_input_raises_validation_error_wrap(tmp_path) -> None:
    """tool_use.input does not match envelope schema → ExtractionError."""
    from unittest.mock import MagicMock

    from pydantic import ValidationError

    from trust_generator.v3.extraction import ExtractionError
    from trust_generator.v3.extraction.anthropic_backend import AnthropicBackend

    # Missing required structure: pass a string where a dict is expected.
    tool_use_block = MagicMock()
    tool_use_block.type = "tool_use"
    tool_use_block.name = "submit_intake_extraction"
    tool_use_block.input = {"grantors": "not-a-list", "beneficiaries": []}

    response = MagicMock()
    response.stop_reason = "tool_use"
    response.content = [tool_use_block]

    client = MagicMock()
    client.messages.create.return_value = response
    backend = AnthropicBackend(
        model="claude-sonnet-4-6", client=client, mechanism="tool_use"
    )
    pdf = _make_pdf_fixture(tmp_path)

    with pytest.raises(ExtractionError) as exc_info:
        backend.extract(pdf)

    assert isinstance(exc_info.value.__cause__, ValidationError)
    assert "schema-invalid" in str(exc_info.value).lower() or "envelope" in str(
        exc_info.value
    ).lower()


def test_output_config_unknown_keys_raises_validation_error_wrap(tmp_path) -> None:
    """output_config mode + JSON that violates extra='forbid' → ExtractionError."""
    import json
    from unittest.mock import MagicMock

    from pydantic import ValidationError

    from trust_generator.v3.extraction import ExtractionError
    from trust_generator.v3.extraction.anthropic_backend import AnthropicBackend

    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = json.dumps(
        {
            "grantors": [],
            "beneficiaries": [],
            "rogue_reasoning_field": "should be rejected by extra=forbid",
        }
    )

    response = MagicMock()
    response.stop_reason = "end_turn"
    response.content = [text_block]

    client = MagicMock()
    client.messages.create.return_value = response
    backend = AnthropicBackend(
        model="claude-sonnet-4-6", client=client, mechanism="output_config"
    )
    pdf = _make_pdf_fixture(tmp_path)

    with pytest.raises(ExtractionError) as exc_info:
        backend.extract(pdf)

    assert isinstance(exc_info.value.__cause__, ValidationError)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pixi run test -- tests/v3/extraction/test_anthropic_backend.py::test_tool_use_malformed_input_raises_validation_error_wrap -v`

Expected: **FAIL** on the substring assertion. The Cycle 7 placeholder ("Anthropic SDK returned malformed structured output") does not contain `"schema-invalid"` or `"envelope"`. The `__cause__` assertion passes (placeholder chains via `from e`).

- [ ] **Step 3: Write minimal implementation (Green)**

Tighten the Cycle 7 validation wrap-site message:

```python
try:
    envelope = AnthropicGenerationEnvelope.model_validate(raw)
except ValidationError as e:
    raise ExtractionError(
        f"Anthropic envelope schema-invalid: {e}"
    ) from e
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pixi run test -- tests/v3/extraction/test_anthropic_backend.py -v`

Run: `pixi run check` — gate stays green.

- [ ] **Step 5: Commit Red**

```bash
git add tests/v3/extraction/test_anthropic_backend.py
git commit -m "test(v3/extraction): pin schema-invalid envelope mapping (Red, cycle 10f)"
```

- [ ] **Step 6: Commit Green**

```bash
git add src/trust_generator/v3/extraction/anthropic_backend.py
git commit -m "feat(v3/extraction): tighten schema-invalid envelope error text (Green, cycle 10f)"
```

---

## Cycle 14 — `ExtractionProtocol` conformance

**Cycle classification: mypy-gated Red.** The Red surface here is the static type-check layer (mypy strictly verifies structural compatibility when `AnthropicBackend` is assigned to a variable typed as `ExtractionProtocol`). The runtime body of the test asserts only that `extract` is callable — that assertion alone would not produce a meaningful Red, because the cycle-7 endpoint already yields a callable `extract`. The meaningful Red is the mypy diagnostic that fires when the signature diverges from the Protocol (e.g., parameter typed `Path` instead of `SourceRef`, or `extract` returns `TrustData` instead of `ExtractionResult`).

This cycle is distinct from cycles 10e/10f (which are real-TDD raise-site tightening) and from "pinning cycle" framing (which has no Red surface at all). The mypy gate IS the Red surface — runs as part of `pixi run check` per the cycle's gate command.

**Files:**
- Test: `tests/v3/extraction/test_anthropic_backend.py` (append)
- Modify (only if mypy surfaces a divergence): `src/trust_generator/v3/extraction/anthropic_backend.py`

**Threshold verdicts:**
- design_surface_threshold: contract surface (the Protocol is the project's ubiquitous-language boundary between extraction and diagnostics). Satisfies.
- refactor_threshold: **none met — green output is already minimal**. The Protocol conformance is automatic once `AnthropicBackend.extract(source: SourceRef) -> ExtractionResult` is in place (Cycle 7).

- [ ] **Step 1: Write the failing test (Red)**

Append:

```python
def test_anthropic_backend_satisfies_extraction_protocol() -> None:
    """Structural type check: ``AnthropicBackend`` matches
    ``ExtractionProtocol`` (mirrors the 4.3a 9b cycle 5 test on
    OllamaBackend).

    Pattern: assignment to a variable typed as ``ExtractionProtocol``
    forces the static type checker (mypy) to verify structural
    compatibility. At runtime the Protocol is not @runtime_checkable
    (per spec 4.3a §5.4 commentary), so the test serves primarily as
    a mypy gate; the runtime assertion is the absence of an exception
    during construction and assignment.
    """
    from unittest.mock import MagicMock

    from trust_generator.v3.extraction import (
        AnthropicBackend,
        ExtractionProtocol,
    )

    backend: ExtractionProtocol = AnthropicBackend(
        model="claude-sonnet-4-6", client=MagicMock()
    )
    # Probe the protocol method exists on the bound instance.
    assert callable(backend.extract)
```

- [ ] **Step 2: Run test to verify it fails (or passes trivially)**

Run: `pixi run test -- tests/v3/extraction/test_anthropic_backend.py::test_anthropic_backend_satisfies_extraction_protocol -v`

Expected: PASS at runtime (the import succeeds and `extract` is bound). The mypy gate runs in `pixi run check` — if `AnthropicBackend.extract` has a signature divergent from `ExtractionProtocol.extract`, mypy fails here.

If both checks pass against the Cycle 7 endpoint, the Red is a pinning cycle: it captures the invariant against future regressions.

- [ ] **Step 3: Write minimal implementation (Green)**

No code change required — the conformance holds by construction (per Cycle 7). If mypy surfaces a divergence (e.g., `source` parameter typed `Path` rather than `SourceRef`, mismatched return type), reconcile in `anthropic_backend.py`.

- [ ] **Step 4: Run tests + full gate**

Run: `pixi run test -- tests/v3/extraction/test_anthropic_backend.py -v` — all cycles green.

Run: `pixi run check` — gate stays green (lint + mypy + test).

- [ ] **Step 5: Commit Red + Green (atomic since Green is no-op)**

```bash
git add tests/v3/extraction/test_anthropic_backend.py
git commit -m "test(v3/extraction): pin AnthropicBackend ExtractionProtocol conformance (cycle 14)"
```

If a Green delta was required (mypy reconciliation), commit it separately:

```bash
git add src/trust_generator/v3/extraction/anthropic_backend.py
git commit -m "fix(v3/extraction): align AnthropicBackend.extract signature with ExtractionProtocol (Green, cycle 14)"
```

---

## Plan completion criteria

At the endpoint of Cycle 14, the following holds:

1. `AnthropicBackend` is importable from `trust_generator.v3.extraction` and listed in `__all__`.
2. `pyproject.toml` declares the `anthropic` SDK pin at a version verified to support PDF document blocks, extended thinking, `cache_control` breakpoints, and both `tool_use` + `output_config` mechanisms (spec §5).
3. `AnthropicBackend.extract(source)` handles PDF sources end-to-end through both `mechanism="tool_use"` and `mechanism="output_config"` paths, with the seam wiring `thinking={"type": "enabled", ...}` unconditionally and `cache_control={"type": "ephemeral"}` on system + document content blocks.
4. All six error-mapping branches from spec §8.5 raise `ExtractionError` with `__cause__` chained: APIConnectionError, RateLimitError, AuthenticationError, generic APIError, refusal under either mechanism, and schema-invalid envelope.
5. The `api_key` substring does not leak into wrapped error messages **OR through the `__cause__` chain as rendered by `traceback.format_exception` / `logging.exception`** (verified by adversarial tests in cycles 10a + 10c; the AuthenticationError branch uses `raise ... from None` deliberately to drop the SDK's adversarial cause-message from log-walked surfaces).
6. `AnthropicBackend` satisfies `ExtractionProtocol` (static + runtime).
7. `pixi run check` is fully green (ruff lint preview py312 + mypy + pytest).
8. `synthesis.py` is not modified (the diagnostics consumer reads the trace identically regardless of producing backend).
9. `ollama_backend.py` is not modified (the back-compat re-export in `prompt.py` keeps its import paths working).

The endpoint is **shape-complete pending live-API smoke in instrumentation cycle 15**. All assertions land via mocked clients (per spec §9.1's `MagicMock(spec=anthropic.Anthropic)` convention); no live API call has been issued from `tests/`. The sibling plan `instrumentation` (depends-on=core) lands atop this work to add prechecks, the image-source branch, the caching + thinking call-args assertions, the mechanism benchmark, and the live-API integration smoke that exercises this shape against real Claude responses.

## Self-review (per writing-plans skill methodology)

**Spec coverage:** Every collapsed sub-cycle from spec §7 within this plan's cycle-range maps to exactly one cycle entry above (1a → Cycle 1a; 1b → Cycle 1b; 2 → Cycle 2; 3 → Cycle 3; 4 → Cycle 4; 5 → Cycle 5; 6 → Cycle 6; 7 → Cycle 7; 10a–10f → Cycles 10a–10f; 14 → Cycle 14). Cycles 8 / 9 / 11 / 12 / 13a / 13b / 15 are enumerated under "Out of scope (handed to sibling plans)" and cross-referenced by exact suffix `instrumentation`.

**Placeholder scan:** All cycles include actual test code, actual implementation code, and exact pixi commands with expected output. The `<verified-version>` placeholder in the SDK pin is intentional and procedural — the executor verifies and pins during Cycle 4 per the spec §3 gate.

**Type consistency:** All cross-cycle symbol references use exact names — `AnthropicGenerationEnvelope`, `AnthropicGrantorEnvelope`, `AnthropicBeneficiaryEnvelope`, `AnthropicFieldFlag`, `_map_grantor_anthropic_envelope`, `_map_beneficiary_anthropic_envelope`, `_anthropic_envelope_to_extraction_result`, `_invoke_envelope_call`, `_wrap_anthropic_error`, `_load_pdf_or_image`, `_build_system_prompt`, `_build_user_message`, `AnthropicBackend`. The constructor signature `__init__(*, model, api_key=None, client=None, thinking_budget_tokens=5000, mechanism="output_config", prompt_builder=None)` matches spec §6 exactly.

**Blast-radius compliance:** Every file referenced as Create/Modify is within the declared blast-radius. `ollama_backend.py` is explicitly NOT touched (back-compat preserved via `prompt.py` re-export). The `library_selections` memory-entity observation update is performed via mcp memory tools (out of file blast-radius by design).
