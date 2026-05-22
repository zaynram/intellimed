# AnthropicBackend Instrumentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Cycle blocks are XML-tagged for dispatcher-side cycle-scope addressing — see "Dispatch Protocol" below.

**Goal:** Layer instrumentation surface onto the working `AnthropicBackend` shipped by sibling `core` — file-size + PDF page-count prechecks (cycle 8), image source branch incl. image-size precheck (cycle 9), prompt-caching call-arg assertions (cycle 11), extended-thinking call-arg assertions (cycle 12), mechanism benchmark + default pin (cycles 13a/13b), and the live-API integration smoke (cycle 15).

**Architecture:** Six TDD cycles plus one non-TDD measurement task. Cycles 8 and 9 extend `_load_pdf_or_image` with prechecks and an image branch — cycle 8 places a *generic* size guard immediately after MIME detection (PDF and image both pass through it, dispatched by per-MIME byte limit constants) and a PDF-only page-count guard. Cycles 11 and 12 inject `cache_control` and `thinking` kwargs into the existing `_invoke_envelope_call` seam. Task 13a runs a fixture-set benchmark under `@pytest.mark.integration`, emits per-trial logs in spec §9.4's JSON shape, and writes a stable-pointer `_decision.json` aggregator. Cycle 13b reads `_decision.json` and pins `AnthropicBackend.__init__`'s `mechanism` default. Cycle 15 is the live-API smoke (env-var-gated API key, env-var-overridable fixture path, parametrized over both mechanisms, observation-only token usage — no ceiling assertion this plan).

**Tech Stack:** Python 3.12 (pixi-pinned — never invoke bare `python`; use `pixi run python` or `pixi run test`), `anthropic` SDK (version pinned by sibling `core` cycle 4 in `pyproject.toml`), `pypdf>=4` (already in deps), stdlib `base64`/`mimetypes`/`json`, `pytest` + `pytest-mock` (`MagicMock(spec=anthropic.Anthropic)`), `pytest.mark.integration` (`addopts = "-m 'not integration'"` already configured by chore #16). No new dependencies; the integration smoke surfaces `ANTHROPIC_API_KEY` and `ANTHROPIC_SMOKE_FIXTURE_PATH` env vars at runtime.

**Spec source:** `docs/superpowers/specs/2026-05-14-anthropic-extraction-backend-design.md` §3 (plan-authoring verification gates — resolved by lead; see preamble below), §7 (cycle table — rows 8, 9, 11, 12, 13a, 13b, 15), §8.1 (data flow), §8.2 (prompt caching layout), §8.3 (extended thinking always-on), §8.4 (mechanism seam), §8.5 (error mapping — size/page-precheck rows), §9.1 (unit tests 10–18), §9.2 (integration smoke), §9.4 (mechanism benchmark + log format).

**Lead-verified gate resolution preamble:**

Spec §3 gates G1 and G2 were verified by the lead session against the live Anthropic API on 2026-05-18 (`claude-sonnet-4-6`, api version 2023-06-01, via `/tmp/verify_g1_g2.py` using `httpx` + REST to preserve `core` cycle 4's SDK pin decision). Outcomes recorded in auto-memory `project-anthropic-api-gate-outcomes` (path: `~/.claude/projects/-home-ramda-code-trust-generator/memory/project_anthropic_api_gate_outcomes.md`):

| Gate                                                            | Outcome      | Plan-md consequence                                                                                                          |
| --------------------------------------------------------------- | ------------ | ---------------------------------------------------------------------------------------------------------------------------- |
| BASELINE — `output_config` shape itself                         | HTTP 200     | confirms `output_config={"format":{"type":"json_schema","schema":...}}` is the current parameter name (no drift)              |
| G1 — `output_config` + `thinking` compat                        | **POSITIVE** | cycle 12 asserts thinking-always-on unconditionally; no fallback branch; matches spec §8.3 documented prior                  |
| G2 — `cache_control` on `output_config.format`                  | **NEGATIVE** | cycle 11 asserts `cache_control` on system + document/image only under `output_config`; tool_use mode also on tools array     |

These outcomes are point-in-time; if a future SDK / API change flips G1 to negative, spec §1/§8.4 fallback policy applies and Plan A's defaults flip via the established §8.3 procedure. No cross-plan amendment to `core` cycle 4 is required under the verified G1-positive outcome.

**Plan metadata (binding — matches splits.xml verbatim):**

| Field           | Value                                                                                                                                                                                                                       |
| --------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| plan-group      | `2026-05-14-anthropic-extraction-backend`                                                                                                                                                                                   |
| suffix          | `instrumentation`                                                                                                                                                                                                           |
| cycles          | `[§7.8..§7.9,§7.11..§7.13,§7.15..§7.15]` (collapsed sub-cycles: 8, 9, 11, 12, 13a, 13b, 15)                                                                                                                                 |
| depends-on      | `core` (informational at drafting time; binding at execution time — see Predecessor verification)                                                                                                                           |
| worktree        | not-required                                                                                                                                                                                                                |
| blast-radius    | `src/trust_generator/v3/extraction/anthropic_backend.py;tests/v3/extraction/test_anthropic_backend.py;tests/v3/extraction/test_anthropic_backend_integration.py;tests/data/anthropic_mechanism_log`                          |

The `tests/data/anthropic_mechanism_log` directory **does not exist** before this plan executes. Task 13a creates it implicitly when it writes its first per-trial log file; cycle 13b reads `_decision.json` from inside it. No cycle creates the directory as a separate action.

**Plan-composition decisions recorded:**

- **Q1 — Verification gates verified by lead; dual-branch machinery collapses to single-branch.** Spec §3 gates G1 and G2 were resolved against the live API by the lead session before this plan-md was approved. G1-positive ⇒ cycle 12 asserts thinking-always-on unconditionally; G2-negative ⇒ cycle 11 omits the `output_config.format` cache_control assertion (the API rejects that placement with HTTP 400 `Extra inputs are not permitted`). The plan body encodes single-branch assertion shapes only; gate-conditional constants like `_G1_*` / `_G2_*` do not exist in this plan. Re-verification of the gates is required only if the `anthropic` SDK pin changes materially OR Anthropic announces structured-outputs API changes; the verification script preserved at `/tmp/verify_g1_g2.py` is the canonical re-run vehicle.

- **Q2 — Gate-outcome record is the auto-memory entity, not a repo artifact.** Spec §3 *suggested* landing the gate-outcome record at `tests/data/anthropic_verification_smoke/`. Neither child plan's blast-radius (per splits.xml) includes that path. The lead's verification used auto-memory (`project-anthropic-api-gate-outcomes`) which is durable per-session and references the verification script at a non-repo path. This plan body cites the memory entity by name; no repo artifact is created.

- **Q3 — Cycle 13b reads a stable-pointer aggregator (`_decision.json`), not the latest per-trial log.** Spec §7 row 13b permits the test to read either the log file or the commit message; the lead's dispatch picks read-from-log. The per-trial JSON files (spec §9.4 shape) have date-stamped names; a test that reads "the latest" couples to filesystem timestamps and to which trials happened to run last. Task 13a therefore writes two artifact shapes: (a) the per-trial JSON files per spec §9.4 verbatim, and (b) a single `_decision.json` aggregator at `tests/data/anthropic_mechanism_log/_decision.json` containing `{"winner": "output_config" | "tool_use", "winner_log_files": ["YYYY-MM-DD-<run-id>.json", ...], "rationale": "<one line>", "decided_at": "<ISO 8601>"}`. Cycle 13b's Red test reads `_decision.json` at module-load and skips with a clear message if absent. This makes the test resilient to log-file churn while preserving the "test reads the log" semantics.

- **Q4 — Cycle 11 assertion matrix (single-branch under verified G2-negative).** Always-on assertions: `cache_control={"type": "ephemeral"}` on system block; same on document/image content block (spec §8.2 breakpoints 1 + 2). Tool_use-mode adds: `cache_control` on tools-array entry (spec §8.2 breakpoint 3 in tool_use mode; spec §9.1 test 16). Output_config-mode does **NOT** assert on `output_config.format` (gate G2-negative confirmed at lead-time). No truth-table dimension over gate outcome — that dual-branch machinery collapsed when G2 verified.

- **Q5 — Cycle 12 asserts thinking always-on (single-branch under verified G1-positive).** Gate G1 verified positive at lead-time; spec §8.3's "always-on extended thinking" is durable Plan A behavior. The opt-in fallback branch (spec §8.3 alternative under G1-negative) is not encoded in this plan; if a future SDK/API change flips G1 to negative, the fallback procedure lives in the spec and would trigger a re-spec rather than an inline plan branch.

- **Q6 — Cycle 13b prior is `output_config` (under verified G1-positive).** Spec §8.4 selects `output_config` as the working default because it composes with thinking without `tool_choice="auto"` refusal-rate residual. Under the verified G1-positive outcome, this prior holds; the benchmark records observations on both mechanisms and cycle 13b confirms (or, if benchmark observations surprisingly favor `tool_use`, flips) the default. The expected outcome is no-op Green: `_decision.json` records `output_config` and `core` cycle 4's default is already `output_config`.

- **Q7 — Cycle 15 is observation-only on token usage.** Spec §9.2 mentions a "per-fixture sanity ceiling (calibrated during plan execution; e.g., 50k total tokens)." With extended thinking enabled (spec §8.3) and only N=1 observation at execution time, a pinned ceiling is noise-bait — token counts vary substantially on identical prompts and a 1.5× ceiling from one observation will flake CI. Cycle 15 therefore prints the SDK response's `usage` block from each live call and records it in the Green commit message; **no in-test usage-ceiling assertion lands in this plan**. After N≥3 observations accumulate across separate cycle 15 runs, a follow-up chore (flagged in the re-submission message) calibrates and pins a CI ceiling. This decision moots the "path (a) in-test vs. path (b) `_last_usage` attribute" discretion entirely — no attribute is added to `AnthropicBackend`, no blast-radius conflict.

- **Q8 — Cycle 15 parametrizes over both mechanisms.** Spec §9.2: "the test is parametrized over `mechanism in ("tool_use", "output_config")`." Two live calls per opt-in run is the verified-cost budget (Q12).

- **Q9 — Refactor-stage discipline.** Per `.claude/rules/development-strategy.md`'s `<refactor_threshold>` (structural duplication / nested conditionals flatten into dispatch / mixed orthogonal concerns extract cleanly): cycles 8, 9, 11, 12, 13b, 15 each evaluate the threshold at Green-end. The default position per cycle is "no refactor stage — green output is already minimal" with explicit reasoning; cycle bodies below state the per-cycle decision.

- **Q10 — Cycle 13a is a `<task>` block, not a `<cycle>` block.** Spec §7 row 13a is explicitly tagged "n/a — this row records observations, not assertions." Per `.claude/rules/development-strategy.md` the TDD `<cycle>` (Red → Green → optional Refactor) shape does not apply: there is no test, no implementation, only a benchmark run and an artifact write. Mirroring the integration-plan exemplar's pattern, 13a is a `<task>` block with `commits="single"` (one commit lands the per-trial JSON files + the `_decision.json` aggregator). The cycle 13b `<cycle>` block depends on task 13a's commit.

- **Q11 — Scope-size threshold acceptance.** Plan touches 4 blast-radius surfaces: `src/trust_generator/v3/extraction/anthropic_backend.py` (modified — cycles 8, 9, 11, 12, 13b), `tests/v3/extraction/test_anthropic_backend.py` (modified — cycles 8, 9, 11, 12, 13b), `tests/v3/extraction/test_anthropic_backend_integration.py` (created — cycle 15), `tests/data/anthropic_mechanism_log/` (created implicitly by task 13a). 6 cycles + 1 task = 7 dispatched units. Threshold acceptance recorded; the `<cycle>` `commits` attribute carries `red,green` for each TDD cycle so the dispatcher can scope-execute one cycle at a time.

- **Q12 — Anthropic API spend is gated at $5 pre-loaded credit; live-API cycles require explicit user confirmation.** Per auto-memory `project-anthropic-api-credit-cap` (path: `~/.claude/projects/-home-ramda-code-trust-generator/memory/project_anthropic_api_credit_cap.md`): the account currently has ~$5 of credit (post-gate-verification: $5 minus negligible verification-cost). Plan A's two live-API surfaces are task 13a (mechanism benchmark — multiple calls, multiplicative across mechanism × runs) and cycle 15 (integration smoke — one call per mechanism per opt-in run). Both encode a pre-run confirmation gate (Step 0 of each procedure) printing the estimated spend and requiring user `y` confirmation before any live-API call. Per-call estimate at `claude-sonnet-4-6` with 5,000-token thinking budget: ~$0.10/call (rough estimate — input ~2,000 tokens at $3/MTok = $0.006; output incl. thinking ~6,000 tokens at $15/MTok = $0.09; the executor refines this estimate after cycle 11/12 lands actual token counts). Task 13a's 2 mechanisms × 3 cache-warmed runs = 6 calls ≈ $0.60; cycle 15's 2 mechanisms × 1 warm-cache run = 2 calls ≈ $0.20.

- **Q13 — Shared `_TEST_MODEL` constant for the model identifier.** Hard-coding `"claude-sonnet-4-6"` in every test (cycles 8, 9, 11, 12, 13b each instantiate an `AnthropicBackend`) couples this plan's tests to `core` cycle 4's chosen default. A single module-level constant `_TEST_MODEL` at the top of `tests/v3/extraction/test_anthropic_backend.py` sources the model identifier; if `core` picks a different default model, only one line edits. Integration test uses `os.environ.get("ANTHROPIC_SMOKE_MODEL", _TEST_MODEL)` for runtime override.

---

## Dispatch Protocol

When invoking `/spec-pipeline 2026-05-14-anthropic-extraction-backend exec-multi-plan`, the dispatcher (the multi-plan lead, or a routing skill) controls which cycles/tasks execute via a scope-token in the dispatcher prompt:

| Scope-token                       | Effect                                                                                                                                       |
| --------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| (no scope-token, or `cycles=all`) | Plan-executor walks `<cycle>` and `<task>` blocks in document order, executing each per its `commits` attribute.                              |
| `cycles=[cycle-8]`                | Plan-executor opens only the cycle whose `id` attribute matches; verifies `depends-on` cycles' Green commits exist via `git log --grep`.      |
| `cycles=[cycle-8..cycle-13b]`     | Plan-executor walks the contiguous cycle/task range; same dependency check at the range's lower bound.                                       |
| `cycles=[cycle-11, cycle-12]`     | Plan-executor walks each id in the order supplied. Use sparingly — non-contiguous execution risks skipping a `depends-on` link.              |

Each `<cycle>` and `<task>` block carries five attributes (`id`, `spec-ref`, `blast-radius`, `depends-on`, `commits`). The dispatching session (the multi-plan lead) retains responsibility for the post-execution close-out (commit the per-child plan status flip in `plans.xml` — invariant #5 in spec-pipeline SKILL.md).

---

## File Structure

**Modified (production):**

| Path                                                       | Change                                                                                                                                                                                                                                                                                                                                                                                  |
| ---------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `src/trust_generator/v3/extraction/anthropic_backend.py`   | Cycle 8: extend `_load_pdf_or_image` with a generic size guard (any allowed MIME passes through it, per-MIME byte limit) + PDF-only page-count guard. Cycle 9: add image MIMEs to the allow-list and add an image branch to `_build_user_message` (the size guard already added in cycle 8 auto-extends to images). Cycle 11: inject `cache_control` on system + document/image + (tool_use mode) tools-array entry in `_invoke_envelope_call`'s kwargs. Cycle 12: inject `thinking={"type": "enabled", "budget_tokens": self.thinking_budget_tokens}` on every `messages.create` invocation. Cycle 13b: pin the `mechanism` default in `__init__` (literal flip if needed — actual default chosen by reading `_decision.json`). |

**Modified (tests):**

| Path                                                       | Change                                                                                                                                                                                                                                                                                                                                                                                  |
| ---------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `tests/v3/extraction/test_anthropic_backend.py`            | All cycles add a shared `_TEST_MODEL` constant near imports if not yet present. Cycle 8: add `test_pdf_size_precheck_raises_before_api_call`, `test_pdf_page_count_precheck_raises_before_api_call`. Cycle 9: add `test_image_source_uses_image_content_block`, `test_image_size_precheck_raises_before_api_call`. Cycle 11: add `test_cache_control_breakpoints_layout` parametrized over mechanism. Cycle 12: add `test_thinking_param_always_present` (parametrized over mechanism) + `test_tool_use_mode_uses_auto_choice`. Cycle 13b: add `test_default_mechanism_matches_benchmark_winner`. |

**Created (tests):**

| Path                                                              | Responsibility                                                                                                                                                                                                                       |
| ----------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `tests/v3/extraction/test_anthropic_backend_integration.py`       | Cycle 15: live-API smoke. `@pytest.mark.integration`. Skips on missing `ANTHROPIC_API_KEY`. Reads `ANTHROPIC_SMOKE_FIXTURE_PATH` env var; defaults to `assets/handwriting-samples/pages/print.jpg`. Parametrized over both mechanisms. Observation-only on token usage (no ceiling assertion). |

**Created (test data; implicitly):**

| Path                                            | Responsibility                                                                                                                                                                                                                                                          |
| ----------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `tests/data/anthropic_mechanism_log/`           | Task 13a creates this directory implicitly when it writes its first per-trial JSON log. Cycle 13b reads `_decision.json` from it. Layout: per-trial logs (`YYYY-MM-DD-<run-id>.json` matching spec §9.4 shape) + one `_decision.json` aggregator (Q3 shape). |

**Total executor-blast-radius surfaces:** 3 modified + 1 created file + 1 implicitly-created directory. Plus dispatcher-owned `plans.xml` flip (multi-plan lead, invariant #5).

---

## Predecessor verification (run once before any cycle)

Gating, not implementing. If any check fails, halt and escalate to the multi-plan lead — there is no "stub-and-skip" path. Sibling `core`'s 15 cycles must have landed (id `2026-05-14-anthropic-extraction-backend-core`) before any instrumentation cycle's Red can land.

- [ ] **Step P1 (load-bearing): Verify sibling `core` plan-md is non-empty and the plan-group child status is `closed`**

```bash
grep -A4 'id="2026-05-14-anthropic-extraction-backend-core"' .claude/context/plans.xml | grep -E 'status=|plan-md='
```

Expected: `status="closed"` AND `plan-md="docs/superpowers/plans/2026-05-14-anthropic-extraction-backend-core.md"`. If `status="open"` or `plan-md=""`: sibling `core` has not landed; halt and route execution to `core` first. **This is the authoritative gate for "core is committed."** P2 below is advisory only.

- [ ] **Step P2 (advisory only — does NOT halt on failure): Count `cycle N` commits in recent history**

```bash
git log --oneline --grep='cycle [0-9]\+' | wc -l
```

Expected: a positive integer (likely ≥15 after `core` lands, more after other plans). This check is informational — recent project commits follow `feat(<surface>): … (cycle N)` form, so the pattern `cycle [0-9]+` matches them; older OllamaBackend cycles also match. The count is a sanity-check signal, **not a halt condition** — P1 is the load-bearing check for `core` completion. If P2 returns 0, log the surprise and check that the working tree's git log is intact, but proceed to P3.

- [ ] **Step P3: Verify `core` symbols importable**

```bash
pixi run python -c "from trust_generator.v3.extraction.anthropic_backend import (
    AnthropicBackend,
    AnthropicGenerationEnvelope,
    AnthropicGrantorEnvelope,
    AnthropicBeneficiaryEnvelope,
    AnthropicFieldFlag,
    _anthropic_envelope_to_extraction_result,
    _map_grantor_anthropic_envelope,
    _map_beneficiary_anthropic_envelope,
)
from trust_generator.v3.extraction.prompt_anthropic import build_intake_prompt
print('ok')"
```

Expected: `ok` (no traceback). If `ImportError`: a `core` symbol drifted from the spec; halt and reconcile.

- [ ] **Step P4: Verify `_load_pdf_or_image` and `_invoke_envelope_call` exist on `AnthropicBackend`**

```bash
pixi run python -c "from trust_generator.v3.extraction.anthropic_backend import AnthropicBackend
import inspect
members = dict(inspect.getmembers(AnthropicBackend))
assert '_load_pdf_or_image' in members, 'cycle 8 extends this seam; core must have created it'
assert '_invoke_envelope_call' in members, 'cycles 11/12 inject kwargs into this seam; core must have created it'
print('ok')"
```

Expected: `ok`. If `AssertionError`: a `core` cycle that should have created the seam is missing. Halt and reconcile.

- [ ] **Step P5: Verify project gate green pre-cycle**

```bash
pixi run check
```

Expected: lint passes, mypy passes, all tests pass, exit code 0. If non-green: halt — instrumentation starts from a green baseline.

- [ ] **Step P6: Verify feature branch (not main)**

```bash
git branch --show-current
```

Expected: a branch name that is NOT `main` or `master`. Current branch (per session start: `v3.0.0`) is fine.

- [ ] **Step P7 (new — credit-cap gate): Acknowledge Anthropic API credit cap before any live-API cycle**

Per auto-memory `project-anthropic-api-credit-cap`: the firm's Anthropic API account has ~$5 of pre-loaded credit; explicit user confirmation is required before any run that would meaningfully consume the balance. This plan's live-API surfaces are **task 13a** (mechanism benchmark) and **cycle 15** (integration smoke). Their per-cycle pre-run gates (Step 0 of each procedure) print the estimated spend and require user confirmation.

```bash
cat <<'EOF'
=== Anthropic API credit-cap acknowledgment ===

Per auto-memory project-anthropic-api-credit-cap (2026-05-18):
  Account credit: ~$5 pre-loaded (minus negligible verification cost)

This plan's live-API cycles:
  - Task 13a (benchmark): ~$0.60 estimate (2 mechanisms × 3 cache-warmed runs × ~$0.10/call incl. 5k thinking)
  - Cycle 15 (smoke): ~$0.20 estimate (2 mechanisms × 1 warm-cache run × ~$0.10/call)
  Total live-API spend estimate: ~$0.80

Per-cycle Step 0 will re-confirm at run time with refined estimates.
EOF
```

Run the command, read the output, acknowledge. This is informational at P-step time; the per-cycle Step 0 gates are the load-bearing user-confirmation moments.

---

## Out of scope (handed to sibling plans)

The following spec §7 cycles are **NOT** part of this plan-md. They land via sibling `core` (id `2026-05-14-anthropic-extraction-backend-core`). Cross-references in this plan-md use the exact suffix `core`.

| Sibling cycle | Surface                                                                                                                       |
| ------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| 1a            | `prompt.py` refactor (Ollama-side, safety-net cycle); relocate `_INTAKE_PROMPT` + `build_intake_prompt` into `prompt_ollama.py`. |
| 1b            | `prompt_anthropic.build_intake_prompt`: implement Anthropic-specific prompt assembly with PDF-as-image awareness.              |
| 2             | `AnthropicGenerationEnvelope` + nested Pydantic models (`AnthropicFieldFlag`, `AnthropicGrantorEnvelope`, `AnthropicBeneficiaryEnvelope`); `extra="forbid"` at every level. |
| 3             | Forked mappers `_map_grantor_anthropic_envelope`, `_map_beneficiary_anthropic_envelope`, `_anthropic_envelope_to_extraction_result`. |
| 4             | `AnthropicBackend.__init__` (ctor surface: model, api_key, client, thinking_budget_tokens, mechanism default, prompt_builder); SDK pin in `pyproject.toml`. |
| 5             | `_invoke_envelope_call` seam, **tool_use branch** under `tool_choice={"type": "auto"}` (thinking-compat constraint).            |
| 6             | `_invoke_envelope_call` seam, **output_config branch** (`output_config={"format": {"type": "json_schema", "schema": ...}}`).    |
| 7             | `AnthropicBackend.extract` happy path: end-to-end mocked, parametrized over both mechanisms; wires `_load_pdf_or_image` (sans prechecks) + `_build_*` + `_invoke_envelope_call` + mappers. |
| 10a           | Error mapping: `anthropic.APIConnectionError` → `ExtractionError`; api_key substring not leaked.                                |
| 10b           | Error mapping: `anthropic.RateLimitError` → `ExtractionError`; no retry attempted.                                              |
| 10c           | Error mapping: `anthropic.AuthenticationError` → `ExtractionError`; api_key substring not leaked.                               |
| 10d           | Error mapping: generic `anthropic.APIError` → `ExtractionError`.                                                                |
| 10e           | Refusal — tool_use mode under auto choice: missing `tool_use` block → `ExtractionError` with `stop_reason` in message.          |
| 10f           | Schema-invalid envelope (defense-in-depth): malformed `tool_use.input` / non-JSON `output_config` text → `ExtractionError` wrapping `ValidationError`. |
| 14            | Protocol conformance: `AnthropicBackend` satisfies `ExtractionProtocol` (structural type check; mirrors 9b cycle 5 OllamaBackend test). |

This plan **assumes** the following symbols exist (created by `core`) before any of its cycles execute: `AnthropicBackend`, `AnthropicBackend.__init__`, `AnthropicBackend.extract`, `AnthropicBackend._invoke_envelope_call`, `AnthropicBackend._load_pdf_or_image` (without prechecks), `AnthropicBackend._build_user_message` (PDF branch only), `AnthropicGenerationEnvelope`, mapper helpers, `prompt_anthropic.build_intake_prompt`. **Cycle 8 extends `_load_pdf_or_image`; cycle 9 adds a branch to `_load_pdf_or_image`'s MIME allow-list and to `_build_user_message`; cycles 11 and 12 inject kwargs into the existing `_invoke_envelope_call`. No instrumentation cycle creates a new top-level function.**

---

## Shared test-module preamble (cycle 8 adds if not present)

The first cycle to touch `tests/v3/extraction/test_anthropic_backend.py` (cycle 8) adds these shared imports and constants near the top of the test file, after any `core`-installed imports. Subsequent cycles reference them.

```python
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from trust_generator.v3.extraction import ExtractionError, ExtractionResult
from trust_generator.v3.extraction.anthropic_backend import AnthropicBackend


# Shared test-model identifier — mirrors core cycle 4's ctor default.
# If core changes the default model, update this one constant; the
# tests instantiate AnthropicBackend(model=_TEST_MODEL, ...) throughout.
_TEST_MODEL: str = "claude-sonnet-4-6"
```

If `core`'s `test_anthropic_backend.py` already defines `_TEST_MODEL`, do not duplicate; reuse the existing definition.

---

## Cycle 8 — File-size + PDF page-count prechecks

<cycle id="cycle-8"
       spec-ref="§7 row 8; §8.1 (_load_pdf_or_image flow); §8.5 (error mapping rows 'PDF exceeds Anthropic file-size limit', 'PDF exceeds Anthropic page-count limit'); §9.1 tests 10-11"
       blast-radius="src/trust_generator/v3/extraction/anthropic_backend.py; tests/v3/extraction/test_anthropic_backend.py"
       depends-on="(predecessor: core plan-md status=closed)"
       commits="red,green">

**Refactor decision:** No refactor stage — green output is already minimal. The size + page-count guards are sequential guard clauses; no structural duplication, no nested conditional flatten-target, no orthogonal-concerns split.

**Structural note:** The size guard is placed **after** MIME-allow-list dispatch and **before** the PDF-only page-count guard. This makes the size guard inherently general — at cycle 8 time the MIME allow-list only contains `application/pdf` (from `core` cycle 4/7), but the structure auto-extends to any MIME cycle 9 adds. Per-MIME byte-limit constants dispatch the appropriate threshold.

**Files:**

- Modify: `src/trust_generator/v3/extraction/anthropic_backend.py`
- Modify: `tests/v3/extraction/test_anthropic_backend.py`

### Stage 8.A — Red

Red lands two failing tests against `_load_pdf_or_image` (created by `core` cycle 7).

- [ ] **Step 1: Add the shared test-module preamble**

If the `pathlib`, `MagicMock`/`patch`, `pytest`, `ExtractionError`, `ExtractionResult`, `AnthropicBackend`, and `_TEST_MODEL` symbols are not already present at the top of `tests/v3/extraction/test_anthropic_backend.py`, add them per "Shared test-module preamble" above.

- [ ] **Step 2: Add the PDF-size-precheck Red test**

Append to `tests/v3/extraction/test_anthropic_backend.py`:

```python
def test_pdf_size_precheck_raises_before_api_call(tmp_path: Path) -> None:
    """A PDF exceeding the Anthropic PDF file-size limit raises ExtractionError
    *before* any client.messages.create call (spec §8.5).

    Per Anthropic docs at SDK pin time: PDF documents accept up to 32 MiB.
    """
    oversized = tmp_path / "oversized.pdf"
    # 33 MiB of zero bytes — beyond the 32 MiB Anthropic PDF cap.
    oversized.write_bytes(b"%PDF-1.7\n" + b"\x00" * (33 * 1024 * 1024))

    fake_client = MagicMock()
    backend = AnthropicBackend(
        model=_TEST_MODEL,
        client=fake_client,
    )

    with pytest.raises(ExtractionError, match=r"PDF exceeds Anthropic file-size limit"):
        backend.extract(oversized)

    fake_client.messages.create.assert_not_called()
```

- [ ] **Step 3: Add the PDF-page-count-precheck Red test**

Append:

```python
def test_pdf_page_count_precheck_raises_before_api_call(tmp_path: Path) -> None:
    """A PDF exceeding the model's context-window page-count limit raises
    ExtractionError before any API call (spec §8.5).

    The 200K-context tier (claude-sonnet-4-6 default) caps at 100 pages
    per the spec §8.1 constant pin. We mock pypdf so the disk fixture
    stays tiny.
    """
    small_pdf = tmp_path / "many_pages.pdf"
    small_pdf.write_bytes(b"%PDF-1.7\n" + b"\x00" * 1024)  # well under size cap

    fake_client = MagicMock()
    backend = AnthropicBackend(
        model=_TEST_MODEL,
        client=fake_client,
    )

    fake_pdf = MagicMock()
    fake_pdf.pages = [MagicMock()] * 101  # one over the 200K-tier limit

    with patch(
        "trust_generator.v3.extraction.anthropic_backend.PdfReader",
        return_value=fake_pdf,
    ):
        with pytest.raises(ExtractionError, match=r"PDF exceeds Anthropic page limit"):
            backend.extract(small_pdf)

    fake_client.messages.create.assert_not_called()
```

- [ ] **Step 4: Run the tests to confirm they fail**

```bash
pixi run test -- tests/v3/extraction/test_anthropic_backend.py -v -k "precheck"
```

Expected: FAIL — `_load_pdf_or_image` does not yet raise on oversized / overpaged PDFs.

- [ ] **Step 5: Commit Red**

```bash
git add tests/v3/extraction/test_anthropic_backend.py
git commit -m "test(anthropic-backend): add PDF size + page-count precheck Red tests (cycle 8)"
```

### Stage 8.B — Green

Green introduces per-MIME size-limit constants, places a *generic* size guard after MIME dispatch (auto-extends to images cycle 9 adds), and adds a PDF-only page-count guard.

- [ ] **Step 1: Add the size + page-count constants to `anthropic_backend.py`**

Locate the module-top constants block. Add (next to whatever MIME allow-list constant `core` cycle 4/7 named):

```python
# Anthropic source-size limits — per-MIME, pinned at SDK pin time per spec §8.1
# and Anthropic's documented input constraints.
#
# PDFs: 32 MiB documented limit on document content blocks.
# Images: 5 MiB documented limit on image content blocks (image/jpeg,
#         image/png, image/gif, image/webp).
#
# At cycle 8 time only PDFs are in the allow-list; the image constant is
# unused until cycle 9 expands the allow-list. Defining both up-front
# keeps the dispatch structure in this cycle's Green so cycle 9 only
# expands the allow-list and adds a Red test.
_ANTHROPIC_PDF_SIZE_LIMIT_BYTES: Final[int] = 32 * 1024 * 1024  # 32 MiB
_ANTHROPIC_IMAGE_SIZE_LIMIT_BYTES: Final[int] = 5 * 1024 * 1024  # 5 MiB

# Anthropic PDF page-count cap — tiered by context window. 100 pages for
# 200K-context variants (claude-sonnet-4-6 default, claude-opus-4-5+),
# 600 for 1M-context variants. Plan A pins the 200K-context tier
# because the spec's indicative model is 200K. If a future session
# migrates to a 1M-context variant, this constant flips to 600 and the
# cycle 8 page-precheck test updates the boundary.
_ANTHROPIC_PDF_PAGE_LIMIT: Final[int] = 100
```

`Final` is `typing.Final`. If `from typing import Final` is not yet at the top of the file, add it.

- [ ] **Step 2: Extend `_load_pdf_or_image` with size + page-count guards**

Locate `_load_pdf_or_image` (created in `core` cycle 7). The flow is: detect MIME, validate against allow-list, base64-encode, return `(mime_type, b64_data)`. Insert the guards **between** the MIME allow-list check and the base64 encode:

```python
# Spec §8.5 prechecks — raise before any client.messages.create call.

# Generic size guard — per-MIME byte limit dispatch. At cycle 8 time
# only PDFs are in the allow-list; cycle 9 expands to image MIMEs and
# the same guard handles them via _ANTHROPIC_IMAGE_SIZE_LIMIT_BYTES.
size_bytes = source.stat().st_size
if mime_type == "application/pdf":
    size_limit = _ANTHROPIC_PDF_SIZE_LIMIT_BYTES
    size_label = "PDF"
elif mime_type.startswith("image/"):
    size_limit = _ANTHROPIC_IMAGE_SIZE_LIMIT_BYTES
    size_label = "image"
else:
    # Allow-list gating happens upstream; reaching here is a programmer
    # error. Conservative fallback uses the smaller image limit.
    size_limit = _ANTHROPIC_IMAGE_SIZE_LIMIT_BYTES
    size_label = "source"
if size_bytes > size_limit:
    raise ExtractionError(
        f"{size_label} exceeds Anthropic file-size limit "
        f"({size_limit // (1024 * 1024)}MiB): "
        f"got {size_bytes // (1024 * 1024)}MiB"
    )

# PDF-only page-count guard.
if mime_type == "application/pdf":
    page_count = len(PdfReader(source).pages)
    if page_count > _ANTHROPIC_PDF_PAGE_LIMIT:
        raise ExtractionError(
            f"PDF exceeds Anthropic page limit "
            f"({_ANTHROPIC_PDF_PAGE_LIMIT}): got {page_count}"
        )
```

If `from pypdf import PdfReader` is not yet at the top of the file, add it. `PdfReader` is the surface the cycle 8 page-count test patches.

- [ ] **Step 3: Run the cycle 8 tests to confirm they pass**

```bash
pixi run test -- tests/v3/extraction/test_anthropic_backend.py -v -k "precheck"
```

Expected: 2 passed.

- [ ] **Step 4: Run the project gate to confirm no regression**

```bash
pixi run check
```

Expected: green.

- [ ] **Step 5: Commit Green**

```bash
git add src/trust_generator/v3/extraction/anthropic_backend.py tests/v3/extraction/test_anthropic_backend.py
git commit -m "feat(anthropic-backend): PDF size + page-count prechecks (cycle 8)"
```

</cycle>

---

## Cycle 9 — Image source acceptance + image-size precheck

<cycle id="cycle-9"
       spec-ref="§7 row 9; §8.1 (image branch of _build_user_message); §8.5 (size precheck auto-extends to images); §9.1 test 12"
       blast-radius="src/trust_generator/v3/extraction/anthropic_backend.py; tests/v3/extraction/test_anthropic_backend.py"
       depends-on="cycle-8"
       commits="red,green">

**Refactor decision:** No refactor stage — green output is already minimal. The image branch is a single conditional on `mime_type.startswith("image/")` mirroring the PDF branch's shape; no duplication-flatten target. The image size-precheck assertion uses the dispatch structure already in cycle 8 Green.

**Files:**

- Modify: `src/trust_generator/v3/extraction/anthropic_backend.py`
- Modify: `tests/v3/extraction/test_anthropic_backend.py`

### Stage 9.A — Red

Red lands two failing tests: (a) a JPG/PNG source produces an `image` content block, not a `document` block; (b) an oversized JPG raises ExtractionError before the API call (the size guard added in cycle 8 should auto-extend to images once the MIME allow-list expands).

- [ ] **Step 1: Add the image-source Red test**

Append to `tests/v3/extraction/test_anthropic_backend.py`:

```python
def test_image_source_uses_image_content_block(tmp_path: Path) -> None:
    """A JPG/PNG source produces an `image` content block, not a
    `document` block (spec §8.1 image branch; §9.1 test 12)."""
    jpg = tmp_path / "intake.jpg"
    # Minimal JPEG SOI + EOI bytes — passes mimetypes detection.
    jpg.write_bytes(bytes.fromhex("ffd8ffe000104a464946") + b"\x00" * 64 + bytes.fromhex("ffd9"))

    fake_client = MagicMock()
    # Simulate a successful response so we reach the seam without
    # asserting on the response shape (that's core's cycles 5/6/7).
    fake_client.messages.create.return_value = _make_minimal_anthropic_response()

    backend = AnthropicBackend(
        model=_TEST_MODEL,
        client=fake_client,
    )

    try:
        backend.extract(jpg)
    except ExtractionError:
        # The minimal mock response may not parse cleanly into the
        # envelope; we only care about the *call args* here.
        pass

    fake_client.messages.create.assert_called_once()
    _, kwargs = fake_client.messages.create.call_args
    user_message = kwargs["messages"][0]
    content_block = user_message["content"][0]

    assert content_block["type"] == "image", (
        f"Expected image content block for JPG source; got {content_block['type']!r}"
    )
    assert content_block["source"]["media_type"] == "image/jpeg"
```

The `_make_minimal_anthropic_response` helper is defined by `core` cycles 5/6 test fixtures. If `core`'s `test_anthropic_backend.py` named it differently, replace the call with that helper. Verify with `grep -n "_make_" tests/v3/extraction/test_anthropic_backend.py` before adapting.

- [ ] **Step 2: Add the image-size-precheck Red test**

Append:

```python
def test_image_size_precheck_raises_before_api_call(tmp_path: Path) -> None:
    """An image exceeding the Anthropic image file-size limit (5 MiB)
    raises ExtractionError before any client.messages.create call.

    Per spec §8.5 + the lead's M2 finding: the size guard added in
    cycle 8 dispatches per-MIME and auto-extends to images once the
    allow-list expands in cycle 9 Green. This test asserts the
    auto-extension fires.
    """
    oversized = tmp_path / "oversized.jpg"
    # 6 MiB JPEG header + padding — beyond the 5 MiB image cap.
    oversized.write_bytes(
        bytes.fromhex("ffd8ffe000104a464946") + b"\x00" * (6 * 1024 * 1024 - 12) + bytes.fromhex("ffd9")
    )

    fake_client = MagicMock()
    backend = AnthropicBackend(
        model=_TEST_MODEL,
        client=fake_client,
    )

    with pytest.raises(ExtractionError, match=r"image exceeds Anthropic file-size limit"):
        backend.extract(oversized)

    fake_client.messages.create.assert_not_called()
```

- [ ] **Step 3: Run the tests to confirm they fail**

```bash
pixi run test -- tests/v3/extraction/test_anthropic_backend.py -v -k "image_source or image_size"
```

Expected: 2 FAIL. The image-source test fails because `_build_user_message` (created by `core` cycle 7) currently emits only `document` blocks; the image-size test fails because the MIME allow-list does not yet include `image/jpeg`, so the precheck branch is unreachable.

- [ ] **Step 4: Commit Red**

```bash
git add tests/v3/extraction/test_anthropic_backend.py
git commit -m "test(anthropic-backend): add image-source + image-size precheck Red tests (cycle 9)"
```

### Stage 9.B — Green

Green expands the MIME allow-list to image types and adds an image branch to `_build_user_message`. The size precheck added in cycle 8 auto-fires on images via the per-MIME dispatch structure.

- [ ] **Step 1: Extend `_load_pdf_or_image`'s MIME allow-list**

Locate the MIME allow-list constant in `anthropic_backend.py` (created by `core` cycle 4/7). Extend to include the documented Anthropic image types:

```python
# MIME allow-list — PDFs + Anthropic-supported image types.
# Anthropic's docs name image/jpeg, image/png, image/gif, image/webp
# as supported.
_ANTHROPIC_SUPPORTED_MIMES: Final[frozenset[str]] = frozenset({
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
})
```

If `core` already pinned this constant with a different name, edit in place rather than introducing a duplicate.

- [ ] **Step 2: Add the image branch to `_build_user_message`**

Locate `_build_user_message` (created by `core` cycle 7). The PDF branch currently constructs `{"type": "document", "source": {"type": "base64", "media_type": mime, "data": b64}, "cache_control": {"type": "ephemeral"}}`. Replace the function body with:

```python
def _build_user_message(self, mime_type: str, b64_data: str) -> dict:
    """Construct the user message with one content block (PDF or image)."""
    if mime_type == "application/pdf":
        block_type = "document"
    elif mime_type.startswith("image/"):
        block_type = "image"
    else:
        # _load_pdf_or_image already gates on the allow-list; this
        # branch is defensive — reaching it is a programmer error.
        raise ExtractionError(f"unsupported mime-type at message build: {mime_type}")

    return {
        "role": "user",
        "content": [
            {
                "type": block_type,
                "source": {
                    "type": "base64",
                    "media_type": mime_type,
                    "data": b64_data,
                },
                "cache_control": {"type": "ephemeral"},
            }
        ],
    }
```

The `cache_control` slot persists on both branches per spec §8.2 breakpoint 2.

- [ ] **Step 3: Run the cycle 9 tests to confirm they pass**

```bash
pixi run test -- tests/v3/extraction/test_anthropic_backend.py -v -k "image_source or image_size"
```

Expected: 2 passed. The image-size test passes because cycle 8's per-MIME dispatch now reaches the `image/*` branch.

- [ ] **Step 4: Run the project gate**

```bash
pixi run check
```

Expected: green.

- [ ] **Step 5: Commit Green**

```bash
git add src/trust_generator/v3/extraction/anthropic_backend.py tests/v3/extraction/test_anthropic_backend.py
git commit -m "feat(anthropic-backend): image-source content-block branch + size precheck auto-extension (cycle 9)"
```

</cycle>

---

## Cycle 11 — Prompt-caching call-args assertion (single-branch under G2-negative)

<cycle id="cycle-11"
       spec-ref="§7 row 11; §8.2 (prompt caching layout — G2-negative collapses output_config.format breakpoint); §9.1 test 16"
       blast-radius="src/trust_generator/v3/extraction/anthropic_backend.py; tests/v3/extraction/test_anthropic_backend.py"
       depends-on="cycle-9"
       commits="red,green">

**Refactor decision:** No refactor stage — green output is already minimal. `cache_control` injection is a single-line addition at each of three placement sites (system, document/image, tools-array in tool_use mode); no duplication-flatten target.

**Gate G2 outcome:** **NEGATIVE** (verified by lead session 2026-05-18 against live API; recorded in auto-memory `project-anthropic-api-gate-outcomes`). The API rejects `cache_control` on `output_config.format` with HTTP 400 `Extra inputs are not permitted`. Therefore: **cycle 11 does NOT assert `cache_control` on `output_config.format` in either mode.** Output_config mode caches via breakpoints 1 (system) and 2 (document/image) only.

**Files:**

- Modify: `src/trust_generator/v3/extraction/anthropic_backend.py`
- Modify: `tests/v3/extraction/test_anthropic_backend.py`

### Assertion shape (collapsed single-branch)

| Placement site                       | tool_use mode | output_config mode |
| ------------------------------------ | ------------- | ------------------ |
| system block (breakpoint 1)          | assert        | assert             |
| document/image content block (br. 2) | assert        | assert             |
| tools-array entry (br. 3, tool_use)  | assert        | n/a (no tools)     |
| `output_config.format`               | n/a           | **omit assertion** (G2-negative) |

Tool_choice in tool_use mode is also asserted to be `{"type": "auto"}` per spec §8.4 (thinking-compat). The defensive negative assertions on `{"type": "tool"}` / `{"type": "any"}` live in cycle 12 (where the thinking parameter is the primary subject and the tool_choice constraints are co-located).

### Stage 11.A — Red

- [ ] **Step 1: Add the parametrized Red test**

Append to `tests/v3/extraction/test_anthropic_backend.py`:

```python
@pytest.mark.parametrize("mechanism", ["tool_use", "output_config"])
def test_cache_control_breakpoints_layout(
    tmp_path: Path,
    mechanism: str,
) -> None:
    """Spec §8.2 breakpoints 1 + 2 always-on; breakpoint 3 conditional on mode.

    Always-on:
      - cache_control={'type': 'ephemeral'} on system block (breakpoint 1)
      - cache_control on document/image content block (breakpoint 2)

    tool_use mode adds:
      - cache_control on tools-array entry (breakpoint 3 in tool_use mode)

    output_config mode does NOT assert cache_control on
    output_config.format — gate G2-negative confirmed at lead-time
    (auto-memory project-anthropic-api-gate-outcomes 2026-05-18:
    API rejects the placement with HTTP 400 "Extra inputs are not
    permitted").
    """
    pdf = tmp_path / "intake.pdf"
    pdf.write_bytes(b"%PDF-1.7\n" + b"\x00" * 1024)

    fake_client = MagicMock()
    fake_client.messages.create.return_value = _make_minimal_anthropic_response()

    backend = AnthropicBackend(
        model=_TEST_MODEL,
        client=fake_client,
        mechanism=mechanism,
    )

    try:
        backend.extract(pdf)
    except ExtractionError:
        pass  # we only assert on call kwargs

    fake_client.messages.create.assert_called_once()
    _, kwargs = fake_client.messages.create.call_args

    # Breakpoint 1: system block.
    system_blocks = kwargs["system"]
    assert any(
        block.get("cache_control") == {"type": "ephemeral"} for block in system_blocks
    ), f"system block missing cache_control: {system_blocks!r}"

    # Breakpoint 2: document/image content block on the user message.
    user_message = kwargs["messages"][0]
    content_block = user_message["content"][0]
    assert content_block.get("cache_control") == {"type": "ephemeral"}, (
        f"content block missing cache_control: {content_block!r}"
    )

    if mechanism == "tool_use":
        # Breakpoint 3 in tool_use mode: tools-array entry.
        tools = kwargs.get("tools") or []
        assert tools, "tool_use mode must pass a tools array"
        assert tools[0].get("cache_control") == {"type": "ephemeral"}, (
            f"tools[0] missing cache_control: {tools[0]!r}"
        )
    else:
        # output_config mode: per G2-negative, format-block cache_control
        # would be API-rejected. Defensive negative assertion documents
        # that this plan intentionally does NOT place cache_control here.
        output_config = kwargs.get("output_config") or {}
        format_block = output_config.get("format") or {}
        assert "cache_control" not in format_block, (
            f"output_config.format must NOT carry cache_control "
            f"(API-rejected per gate G2-negative); got {format_block!r}"
        )
```

- [ ] **Step 2: Run the test to confirm both parametrizations fail**

```bash
pixi run test -- tests/v3/extraction/test_anthropic_backend.py -v -k "cache_control_breakpoints_layout"
```

Expected: 2 FAIL (one per `mechanism` parametrization). The expected failure mode is "cache_control missing" on system/tools — `core`'s cycles 5/6 wired the seam shape but did not inject `cache_control` on the tools array (the system-block `cache_control` may already be wired by `core` cycle 7's `_build_system_prompt`; narrow Green edits per the failure messages).

- [ ] **Step 3: Commit Red**

```bash
git add tests/v3/extraction/test_anthropic_backend.py
git commit -m "test(anthropic-backend): add prompt-caching breakpoint Red test (cycle 11)"
```

### Stage 11.B — Green

Green injects `cache_control={"type": "ephemeral"}` at three placement sites and explicitly does NOT inject it on `output_config.format`.

- [ ] **Step 1: Ensure `_build_system_prompt` emits the system block with `cache_control`**

Locate `_build_system_prompt` (or the call site that constructs the `system=` kwarg). If `core` left it as `[{"type": "text", "text": ...}]`, replace with:

```python
def _build_system_prompt(self) -> list[dict]:
    return [
        {
            "type": "text",
            "text": self._prompt_builder(),
            "cache_control": {"type": "ephemeral"},
        }
    ]
```

If `core` already wired the `cache_control` here, skip this step.

- [ ] **Step 2: Confirm `_build_user_message` emits `cache_control` on the content block**

Cycle 9's Green already wired this. Verify:

```bash
grep -n 'cache_control' src/trust_generator/v3/extraction/anthropic_backend.py
```

Expected: matches inside `_build_user_message`. If absent, re-run cycle 9 Green's step 2.

- [ ] **Step 3: Inject `cache_control` on the tools-array entry (tool_use branch of `_invoke_envelope_call`)**

Locate the tool_use branch of `_invoke_envelope_call`. The `tools=` argument should be a list of one dict; add `cache_control`:

```python
tools=[
    {
        "name": "submit_intake_extraction",
        "description": "Submit the structured intake extraction.",
        "input_schema": schema,
        "cache_control": {"type": "ephemeral"},
    }
],
```

- [ ] **Step 4: Explicitly do NOT inject `cache_control` on `output_config.format`**

Locate the output_config branch of `_invoke_envelope_call`. Verify the structure is:

```python
output_config={
    "format": {
        "type": "json_schema",
        "schema": schema,
        # No cache_control here — gate G2-negative (2026-05-18):
        # API rejects with HTTP 400 "Extra inputs are not permitted".
        # Caching for output_config mode relies on breakpoints 1
        # (system) and 2 (document/image) only.
    }
},
```

If a previous `core` cycle accidentally placed `cache_control` on `output_config.format`, remove it.

- [ ] **Step 5: Run the cycle 11 test**

```bash
pixi run test -- tests/v3/extraction/test_anthropic_backend.py -v -k "cache_control_breakpoints_layout"
```

Expected: 2 passed.

- [ ] **Step 6: Run the project gate**

```bash
pixi run check
```

Expected: green.

- [ ] **Step 7: Commit Green**

```bash
git add src/trust_generator/v3/extraction/anthropic_backend.py tests/v3/extraction/test_anthropic_backend.py
git commit -m "$(cat <<'EOF'
feat(anthropic-backend): prompt-caching breakpoint layout (cycle 11)

Per gate G2-negative (auto-memory project-anthropic-api-gate-outcomes,
verified 2026-05-18 against live API): cache_control placed on system +
document/image always; on tools-array entry in tool_use mode; NOT placed
on output_config.format (API rejects).
EOF
)"
```

</cycle>

---

## Cycle 12 — Extended-thinking call-args assertion (single-branch under G1-positive)

<cycle id="cycle-12"
       spec-ref="§7 row 12; §8.3 (extended thinking always-on); §8.4 (tool_choice='auto' under thinking-compat); §9.1 tests 17, 18"
       blast-radius="src/trust_generator/v3/extraction/anthropic_backend.py; tests/v3/extraction/test_anthropic_backend.py"
       depends-on="cycle-11"
       commits="red,green">

**Refactor decision:** No refactor stage — green output is already minimal. The `thinking` kwarg is injected at one or two sites; no duplication-flatten target.

**Gate G1 outcome:** **POSITIVE** (verified by lead session 2026-05-18; recorded in auto-memory `project-anthropic-api-gate-outcomes`). `output_config` + `thinking` compose; the spec §8.3 always-on default is durable. No cross-plan amendment to `core` cycle 4 is required.

**Files:**

- Modify: `src/trust_generator/v3/extraction/anthropic_backend.py`
- Modify: `tests/v3/extraction/test_anthropic_backend.py`

### Stage 12.A — Red

Red lands two test assertions: (a) `thinking={"type": "enabled", "budget_tokens": <ctor value>}` is present on every `messages.create` call regardless of mechanism (spec §8.3 always-on under G1-positive); (b) under tool_use mode, `tool_choice == {"type": "auto"}` is enforced (spec §8.4 thinking-compat constraint).

- [ ] **Step 1: Add the always-on thinking Red test**

Append:

```python
@pytest.mark.parametrize("mechanism", ["tool_use", "output_config"])
def test_thinking_param_always_present(
    tmp_path: Path,
    mechanism: str,
) -> None:
    """Spec §8.3 (under gate G1-positive): extended thinking is always-on.

    The constructor's thinking_budget_tokens default is 5000 per spec §6
    / core cycle 4. This test asserts the parameter lands on the
    messages.create call with that budget, in both mechanism branches.
    """
    pdf = tmp_path / "intake.pdf"
    pdf.write_bytes(b"%PDF-1.7\n" + b"\x00" * 1024)

    fake_client = MagicMock()
    fake_client.messages.create.return_value = _make_minimal_anthropic_response()

    backend = AnthropicBackend(
        model=_TEST_MODEL,
        client=fake_client,
        mechanism=mechanism,
    )

    try:
        backend.extract(pdf)
    except ExtractionError:
        pass

    fake_client.messages.create.assert_called_once()
    _, kwargs = fake_client.messages.create.call_args

    assert kwargs.get("thinking") == {"type": "enabled", "budget_tokens": 5000}, (
        f"thinking must be always-on with budget=5000 (spec §8.3, "
        f"gate G1-positive); got {kwargs.get('thinking')!r}"
    )
```

- [ ] **Step 2: Add the tool_choice auto-mode Red test**

Append:

```python
def test_tool_use_mode_uses_auto_choice(tmp_path: Path) -> None:
    """Spec §8.4 thinking-compat: tool_use mode must run under
    tool_choice={'type': 'auto'}; never {'type': 'tool'} or
    {'type': 'any'} (incompatible with extended thinking per
    Anthropic docs).
    """
    pdf = tmp_path / "intake.pdf"
    pdf.write_bytes(b"%PDF-1.7\n" + b"\x00" * 1024)

    fake_client = MagicMock()
    fake_client.messages.create.return_value = _make_minimal_anthropic_response()

    backend = AnthropicBackend(
        model=_TEST_MODEL,
        client=fake_client,
        mechanism="tool_use",
    )

    try:
        backend.extract(pdf)
    except ExtractionError:
        pass

    fake_client.messages.create.assert_called_once()
    _, kwargs = fake_client.messages.create.call_args

    assert kwargs.get("tool_choice") == {"type": "auto"}, (
        f"tool_use mode must use tool_choice={{'type': 'auto'}}; "
        f"got {kwargs.get('tool_choice')!r}"
    )
    # Defensive negatives.
    assert kwargs.get("tool_choice") != {"type": "tool"}, (
        f"forbidden tool_choice (thinking-incompatible per spec §8.4)"
    )
    assert kwargs.get("tool_choice") != {"type": "any"}, (
        f"forbidden tool_choice (thinking-incompatible per spec §8.4)"
    )
```

- [ ] **Step 3: Run the tests to confirm they fail**

```bash
pixi run test -- tests/v3/extraction/test_anthropic_backend.py -v -k "thinking or tool_use_mode_uses_auto_choice"
```

Expected: 3 FAIL (two `mechanism` parametrizations of `test_thinking_param_always_present` + `test_tool_use_mode_uses_auto_choice`). `core`'s seam does not yet inject `thinking` into the kwargs.

- [ ] **Step 4: Commit Red**

```bash
git add tests/v3/extraction/test_anthropic_backend.py
git commit -m "test(anthropic-backend): add extended-thinking + tool_choice Red tests (cycle 12)"
```

### Stage 12.B — Green

Green injects `thinking={"type": "enabled", "budget_tokens": self.thinking_budget_tokens}` into both branches of `_invoke_envelope_call`, unconditionally (always-on under G1-positive). The `tool_choice={"type": "auto"}` should already be wired by `core` cycle 5 (per spec §8.4); if not, this Green confirms it.

- [ ] **Step 1: Locate both branches of `_invoke_envelope_call`**

```bash
grep -n 'def _invoke_envelope_call\|tool_use\|output_config' src/trust_generator/v3/extraction/anthropic_backend.py
```

There should be two `client.messages.create(...)` invocations — one in each mechanism branch.

- [ ] **Step 2: Inject `thinking` (always-on) into both invocations**

For each `client.messages.create(...)` call, add the kwarg:

```python
thinking={"type": "enabled", "budget_tokens": self.thinking_budget_tokens},
```

- [ ] **Step 3: Verify `tool_choice` in the tool_use branch is `{"type": "auto"}`**

Inspect the tool_use branch's `messages.create` call. The `tool_choice` kwarg should read `{"type": "auto"}` per spec §8.4. If `core` left it absent (`messages.create` defaults to auto-choice when `tools` is provided), make it explicit so the cycle 12 assertion lands cleanly:

```python
tool_choice={"type": "auto"},  # required for thinking-compat (spec §8.4)
```

- [ ] **Step 4: Run the cycle 12 tests**

```bash
pixi run test -- tests/v3/extraction/test_anthropic_backend.py -v -k "thinking or tool_use_mode_uses_auto_choice"
```

Expected: 3 passed.

- [ ] **Step 5: Run the project gate**

```bash
pixi run check
```

Expected: green.

- [ ] **Step 6: Commit Green**

```bash
git add src/trust_generator/v3/extraction/anthropic_backend.py tests/v3/extraction/test_anthropic_backend.py
git commit -m "$(cat <<'EOF'
feat(anthropic-backend): extended-thinking always-on + tool_choice=auto (cycle 12)

Per gate G1-positive (auto-memory project-anthropic-api-gate-outcomes,
verified 2026-05-18 against live API): output_config + thinking compose;
thinking lands unconditionally with budget=self.thinking_budget_tokens
on every messages.create call. tool_use mode runs under
tool_choice={'type': 'auto'} per spec §8.4 thinking-compat.
EOF
)"
```

</cycle>

---

## Task 13a — Mechanism benchmark (measurement only — NOT a TDD cycle)

<task id="task-13a"
      spec-ref="§7 row 13a; §9.4 (mechanism benchmark + log format); §8.4 (asymmetry note)"
      blast-radius="tests/data/anthropic_mechanism_log"
      depends-on="cycle-12"
      commits="single">

**This is a measurement task, not a TDD cycle.** Per spec §7 row 13a verbatim: "n/a — this row records observations, not assertions." There is no Red stage, no Green stage, no test assertion. The task runs a benchmark, captures per-trial logs in spec §9.4's JSON shape, writes a `_decision.json` aggregator (per Q3), and commits the artifact directory.

**Files:**

- Create: `tests/data/anthropic_mechanism_log/YYYY-MM-DD-<run-id>.json` (one per trial — at least 6 files: 2 mechanisms × 3 cache-warmed runs minimum per spec §9.4)
- Create: `tests/data/anthropic_mechanism_log/_decision.json` (the stable-pointer aggregator)

**Procedure:**

- [ ] **Step 0 (credit-cap gate — user confirmation required before live API):**

Per auto-memory `project-anthropic-api-credit-cap`: the firm's Anthropic API account has ~$5 of pre-loaded credit. This task makes 6 live API calls; running it without explicit user consent violates the credit-cap protocol.

```bash
cat <<'EOF'
=== Task 13a — Mechanism benchmark spend estimate ===

Calls to run: 2 mechanisms × 3 cache-warmed runs = 6 live API calls
Per-call estimate (at claude-sonnet-4-6, 5,000-token thinking budget):
  Input: ~2,000 tokens × $3/MTok = $0.006
  Output (incl. thinking): ~6,000 tokens × $15/MTok = $0.090
  Per-call total: ~$0.10
Estimated total task cost: ~$0.60

Remaining account credit (per project-anthropic-api-credit-cap, 2026-05-18):
  ~$5 minus negligible verification cost

After this task: ~$4.40 remaining.

Per project-anthropic-api-credit-cap: explicit user confirmation
required before consuming a meaningful portion of the balance.
EOF
read -p "Continue with task 13a benchmark (y/N)? " ans
[ "$ans" = "y" ] || { echo "Aborted"; exit 1; }
```

If user denies, halt the task. If user requests an updated estimate (e.g., after cycle 11/12 lands actual token counts), recompute from the observed input + output token counts, present a refined estimate, and re-confirm.

- [ ] **Step 1: Verify `ANTHROPIC_API_KEY` is set**

```bash
test -n "$ANTHROPIC_API_KEY" && echo "ok" || { echo "MISSING — halt"; exit 1; }
```

Expected: `ok`.

- [ ] **Step 2: Run the benchmark**

There is no dedicated benchmark script in `core`'s blast-radius. The executor writes a one-off Python script in a scratch location (e.g., `/tmp/anthropic_benchmark.py` — outside the repo) that:

1. Constructs an `AnthropicBackend` once per mechanism (`tool_use` and `output_config`).
2. For each mechanism, runs `backend.extract(fixture_path)` three times against `assets/handwriting-samples/pages/print.jpg` (cache-warmed: the first run primes the prompt cache; runs 2 and 3 are the measurement runs).
3. For each invocation, captures: `latency_seconds`, `input_tokens`, `output_tokens`, `thinking_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens` (from `response.usage`); `success` boolean; `refusal` boolean (True iff `tool_use` mode received no `tool_use` block); `schema_valid` boolean (True iff `model_validate` succeeded); `trace_field_count` (length of `result.trace.fields`).
4. Writes one JSON file per trial to `tests/data/anthropic_mechanism_log/YYYY-MM-DD-<run-id>.json` in the spec §9.4 shape:

```json
{
  "run_id": "<uuid4 or sequential>",
  "fixture": "assets/handwriting-samples/pages/print.jpg",
  "mechanism": "tool_use",
  "model": "claude-sonnet-4-6",
  "thinking_budget_tokens": 5000,
  "latency_seconds": 12.34,
  "input_tokens": 2345,
  "output_tokens": 678,
  "thinking_tokens": 1500,
  "cache_read_input_tokens": 0,
  "cache_creation_input_tokens": 2345,
  "success": true,
  "refusal": false,
  "schema_valid": true,
  "trace_field_count": 5
}
```

5. Aggregates per-mechanism mean ± stdev for `latency_seconds`, `input_tokens`, `output_tokens`. Per spec §8.4 asymmetry note, the success-rate and refusal-rate columns weigh the comparison.

6. Picks a winner. Under the verified G1-positive outcome, the prior is `output_config` (composes cleanly with thinking; no refusal-rate residual). If `output_config`'s latency/tokens are within ~20% of `tool_use` and both have zero refusals, `output_config` wins on tie-break.

- [ ] **Step 3: Write the `_decision.json` aggregator**

Write `tests/data/anthropic_mechanism_log/_decision.json`:

```json
{
  "winner": "output_config",
  "winner_log_files": [
    "2026-MM-DD-run-001.json",
    "2026-MM-DD-run-002.json",
    "2026-MM-DD-run-003.json"
  ],
  "rationale": "output_config composes with thinking unconditionally; mean latency 11.2±0.8s vs tool_use 13.5±1.1s; zero refusals across 3 runs.",
  "decided_at": "2026-MM-DDTHH:MM:SS-05:00"
}
```

Substitute concrete values from the benchmark run.

- [ ] **Step 4: Commit the benchmark artifacts**

```bash
git add tests/data/anthropic_mechanism_log/
git commit -m "$(cat <<'EOF'
chore(anthropic-backend): mechanism benchmark (task 13a)

3 cache-warmed trials per mechanism against
assets/handwriting-samples/pages/print.jpg.

Winner: <output_config|tool_use> per tests/data/anthropic_mechanism_log/_decision.json
Rationale: <one-line summary>

Spend observed: ~$<actual> against the $5 credit cap.

Per spec §9.4: per-trial JSON logs at
tests/data/anthropic_mechanism_log/YYYY-MM-DD-<run-id>.json.
_decision.json is the stable-pointer aggregator cycle 13b reads.
EOF
)"
```

</task>

---

## Cycle 13b — Pin mechanism default

<cycle id="cycle-13b"
       spec-ref="§7 row 13b; §9.4 (commit message records rationale and cites 13a log path)"
       blast-radius="src/trust_generator/v3/extraction/anthropic_backend.py; tests/v3/extraction/test_anthropic_backend.py"
       depends-on="task-13a"
       commits="red,green">

**Refactor decision:** No refactor stage — green output is already minimal. The pin is a one-line literal flip in `__init__`'s signature default (or a no-op if the benchmark winner equals `core` cycle 4's prior).

**Cycle 13b prior:** Under verified G1-positive, `output_config` is the spec-aligned default that `core` cycle 4 should already have set. The expected case is "Red passes immediately; Green is a no-op rationale-pinning commit." If the benchmark surprisingly favors `tool_use`, Red fails until Green flips the default.

**Files:**

- Modify: `src/trust_generator/v3/extraction/anthropic_backend.py`
- Modify: `tests/v3/extraction/test_anthropic_backend.py`

### Stage 13b.A — Red

- [ ] **Step 1: Add the cycle 13b Red test**

Append to `tests/v3/extraction/test_anthropic_backend.py`:

```python
import json


_MECHANISM_LOG_DIR = Path(__file__).resolve().parents[3] / "tests/data/anthropic_mechanism_log"
_DECISION_PATH = _MECHANISM_LOG_DIR / "_decision.json"


def test_default_mechanism_matches_benchmark_winner() -> None:
    """Spec §7 row 13b — AnthropicBackend default `mechanism` matches
    the cycle 13a benchmark winner recorded in _decision.json.

    Skips if _decision.json is absent (e.g., a fresh clone where task
    13a has not run). The skip is intentional: the benchmark is opt-in
    (real API spend gated by project-anthropic-api-credit-cap); the
    unit suite cannot block on it.
    """
    if not _DECISION_PATH.exists():
        pytest.skip(
            f"benchmark decision file absent at {_DECISION_PATH}; "
            f"run task 13a (mechanism benchmark) to generate it"
        )

    decision = json.loads(_DECISION_PATH.read_text())
    winner = decision["winner"]
    assert winner in ("tool_use", "output_config"), (
        f"_decision.json winner must be 'tool_use' or 'output_config'; "
        f"got {winner!r}"
    )

    # Use a MagicMock client so __init__'s eager validation (if any)
    # does not require a real API key. Mirror cycles 8/9 pattern.
    backend = AnthropicBackend(
        model=_TEST_MODEL,
        client=MagicMock(),
    )

    assert backend.mechanism == winner, (
        f"AnthropicBackend default mechanism is {backend.mechanism!r}, "
        f"but the cycle 13a benchmark "
        f"({decision.get('winner_log_files', ['_decision.json'])[0]}) "
        f"selected {winner!r}. Flip the ctor default to match."
    )
```

- [ ] **Step 2: Run the test**

```bash
pixi run test -- tests/v3/extraction/test_anthropic_backend.py -v -k "default_mechanism_matches"
```

Expected (most likely): PASS — under G1-positive, `core` cycle 4's default `output_config` matches the expected benchmark winner. If task 13a ran differently (e.g., `tool_use` won), expect FAIL — Green flips the default.

- [ ] **Step 3: Commit Red**

```bash
git add tests/v3/extraction/test_anthropic_backend.py
git commit -m "test(anthropic-backend): add benchmark-winner assertion (cycle 13b)"
```

### Stage 13b.B — Green

- [ ] **Step 1: Read the winner from `_decision.json`**

```bash
pixi run python -c "
import json, pathlib
d = json.loads(pathlib.Path('tests/data/anthropic_mechanism_log/_decision.json').read_text())
print(f'winner={d[\"winner\"]}')
"
```

- [ ] **Step 2: Update `AnthropicBackend.__init__` signature default**

Locate the `__init__` signature in `anthropic_backend.py`. The current default (from `core` cycle 4) is `mechanism: Literal["tool_use", "output_config"] = "output_config"` (the documented prior). If the winner from step 1 equals the current default, the line stays unchanged — Green is a no-op rationale-pinning commit. If the winner differs, edit the literal to match.

- [ ] **Step 3: Run the cycle 13b test**

```bash
pixi run test -- tests/v3/extraction/test_anthropic_backend.py -v -k "default_mechanism_matches"
```

Expected: 1 passed.

- [ ] **Step 4: Run the project gate**

```bash
pixi run check
```

Expected: green.

- [ ] **Step 5: Commit Green**

```bash
git add src/trust_generator/v3/extraction/anthropic_backend.py
git commit -m "$(cat <<'EOF'
feat(anthropic-backend): pin mechanism default to benchmark winner (cycle 13b)

Per tests/data/anthropic_mechanism_log/_decision.json:
  winner: <output_config|tool_use>
  rationale: <one-line summary from _decision.json>
  supporting logs: <YYYY-MM-DD-<run-id>.json files>
EOF
)"
```

If the winner matched the prior (no source edit), commit only the test file (`git add tests/v3/extraction/test_anthropic_backend.py` — already committed at Red) — or use `git commit --allow-empty` to land the rationale-only Green commit. Either approach preserves the cycle's Red→Green commit-pair shape.

</cycle>

---

## Cycle 15 — Live-API integration smoke (observation-only)

<cycle id="cycle-15"
       spec-ref="§7 row 15; §9.2 (integration smoke)"
       blast-radius="tests/v3/extraction/test_anthropic_backend_integration.py"
       depends-on="cycle-13b"
       commits="red,green">

**Refactor decision:** No refactor stage — green output is already minimal.

**Observation-only posture (Q7):** This plan does NOT land an in-test token-usage ceiling assertion. Each live call's `response.usage` block is captured and printed; the Green commit message records the observed totals. A follow-up chore calibrates a CI ceiling once N≥3 observations accumulate across separate runs. The cycle's blast-radius is therefore the test file alone — no `_last_usage` attribute is added to `AnthropicBackend`.

**Files:**

- Create: `tests/v3/extraction/test_anthropic_backend_integration.py`

### Stage 15.A — Red

Red creates the test file with one parametrized smoke test. The test is `@pytest.mark.integration`-marked, skips on missing `ANTHROPIC_API_KEY` or fixture, and parametrizes over both mechanisms.

- [ ] **Step 0 (credit-cap gate — user confirmation required before opt-in invocation):**

When a developer invokes the smoke via `pixi run test -- -m integration ...`, the test file's session-level fixture prints a spend estimate before any live call. Encoded in the test file itself so the gate is unavoidable for opt-in runs:

```python
# Session-scoped credit-cap gate. Lives in the test file (not in a
# conftest fixture) so opt-in invocation cannot bypass it.
```

See Step 1 below — the gate is implemented as a session-scoped pytest fixture inside the test file.

- [ ] **Step 1: Write `tests/v3/extraction/test_anthropic_backend_integration.py`**

Create the file with:

```python
"""Cycle 15 — Live-API integration smoke for AnthropicBackend.

Marked ``pytest.mark.integration``. Skipped by default via
pyproject.toml's ``addopts = "-m 'not integration'"`` (configured by
chore #16). Opt-in invocation: ``pixi run test -- -m integration``.

Env-var contract:
  - ``ANTHROPIC_API_KEY`` (required) — absent ⇒ skip with clear message.
  - ``ANTHROPIC_SMOKE_FIXTURE_PATH`` (optional) — overrides the default
    fixture; defaults to ``assets/handwriting-samples/pages/print.jpg``
    (synthetic-persona handwriting; PHI-clean per BASELINE.md).
  - ``ANTHROPIC_SMOKE_MODEL`` (optional) — overrides the default
    model; falls back to the shared _TEST_MODEL pinned by the unit suite.
  - ``ANTHROPIC_SMOKE_CONFIRM_SPEND`` (required for live runs) — set to
    "y" to acknowledge the spend per project-anthropic-api-credit-cap;
    absent ⇒ the session-scoped gate skips all tests in this module.

Cost: each live ``messages.create`` call costs real Anthropic API
spend. The test parametrizes over both mechanisms ⇒ 2 live calls per
opt-in run, ~$0.10/call = ~$0.20/run (estimate; refine after cycle 12
lands actual token counts).

Observation-only on token usage — see plan §"Cycle 15" Q7 / observation-only
posture. Each call's response.usage block is printed; commit message
records totals. No in-test ceiling assertion in this plan.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from trust_generator.v3.extraction import ExtractionError, ExtractionResult
from trust_generator.v3.extraction.anthropic_backend import AnthropicBackend

pytestmark = pytest.mark.integration


# Default test model — mirrors core cycle 4's ctor default.
_DEFAULT_MODEL: str = "claude-sonnet-4-6"


def _resolve_fixture_path() -> Path:
    """Resolve ANTHROPIC_SMOKE_FIXTURE_PATH, defaulting to the canonical baseline."""
    env_path = os.environ.get("ANTHROPIC_SMOKE_FIXTURE_PATH")
    if env_path:
        return Path(env_path)
    # parents[0]=extraction, [1]=v3, [2]=tests, [3]=<repo root>
    return Path(__file__).resolve().parents[3] / "assets/handwriting-samples/pages/print.jpg"


def _resolve_model() -> str:
    return os.environ.get("ANTHROPIC_SMOKE_MODEL", _DEFAULT_MODEL)


@pytest.fixture(scope="session", autouse=True)
def _credit_cap_gate() -> None:
    """Skip all live-API tests in this module unless the developer has
    acknowledged the spend per project-anthropic-api-credit-cap.

    Auto-use + session-scope: applies to every test in this module
    once, at session start. Cannot be bypassed by opt-in invocation
    without also setting ANTHROPIC_SMOKE_CONFIRM_SPEND=y.
    """
    if os.environ.get("ANTHROPIC_SMOKE_CONFIRM_SPEND", "").lower() != "y":
        pytest.skip(
            "Live-API spend gated by project-anthropic-api-credit-cap. "
            "Estimated cost: 2 calls × ~$0.10 ≈ $0.20 against the $5 "
            "credit cap. Set ANTHROPIC_SMOKE_CONFIRM_SPEND=y to confirm "
            "and re-run."
        )


@pytest.fixture
def fixture_path_or_skip() -> Path:
    """Resolve the fixture path; skip if absent or ANTHROPIC_API_KEY unset."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set; live-API smoke requires a real key")
    path = _resolve_fixture_path()
    if not path.exists():
        pytest.skip(
            f"Smoke fixture not found at {path}; set ANTHROPIC_SMOKE_FIXTURE_PATH "
            f"or commit the default fixture"
        )
    return path


@pytest.mark.parametrize("mechanism", ["tool_use", "output_config"])
def test_live_anthropic_extract_smoke(
    mechanism: str,
    fixture_path_or_skip: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """One live Anthropic API call per mechanism. Asserts:
      - ExtractionResult returned (not ExtractionError).
      - TrustData.grantor.full_legal_name is non-empty.
      - trace.backend_id starts with "anthropic:".
      - trace.fields contains at least one entry under the "grantor." prefix.

    Observation-only on token usage: the test prints the response.usage
    block to stdout for the commit message to record. No ceiling assertion
    lands in this plan; calibration is deferred to a follow-up chore once
    N≥3 observations accumulate.
    """
    backend = AnthropicBackend(
        model=_resolve_model(),
        mechanism=mechanism,
    )

    # Capture the SDK response by monkey-patching the client's messages.create
    # to record the response. Alternative: rely on AnthropicBackend exposing
    # the last response — but no such attribute is added in this plan (Q7).
    captured_responses = []
    original_create = backend._client.messages.create

    def _capture(*args, **kwargs):
        response = original_create(*args, **kwargs)
        captured_responses.append(response)
        return response

    backend._client.messages.create = _capture  # type: ignore[assignment]

    try:
        result = backend.extract(fixture_path_or_skip)
    except ExtractionError as e:
        # Unexpected under verified G1-positive — the gate-resolution
        # preamble says output_config + thinking compose. If this fires,
        # re-run the verification script at /tmp/verify_g1_g2.py and
        # update project-anthropic-api-gate-outcomes.
        raise AssertionError(
            f"Live extract raised ExtractionError ({e}) — unexpected under "
            f"verified G1-positive outcome. Re-verify gates."
        ) from e

    assert isinstance(result, ExtractionResult)

    # Grantor full_legal_name populated.
    assert result.data.grantor is not None
    assert result.data.grantor.full_legal_name, (
        f"grantor.full_legal_name is empty; fixture should have a legible name"
    )

    # backend_id prefix.
    assert result.trace.backend_id.startswith("anthropic:"), (
        f"backend_id should start with 'anthropic:'; got {result.trace.backend_id!r}"
    )

    # At least one grantor field in the trace.
    grantor_fields = [f for f in result.trace.fields if f.field_path.startswith("grantor.")]
    assert grantor_fields, (
        f"trace.fields contains no entries under 'grantor.'; "
        f"all paths: {[f.field_path for f in result.trace.fields]}"
    )

    # Observation-only: print usage for the commit message.
    if captured_responses:
        usage = captured_responses[-1].usage
        print(
            f"\n[cycle-15 observation] mechanism={mechanism} "
            f"input_tokens={getattr(usage, 'input_tokens', 'n/a')} "
            f"output_tokens={getattr(usage, 'output_tokens', 'n/a')} "
            f"cache_read_input_tokens={getattr(usage, 'cache_read_input_tokens', 'n/a')} "
            f"cache_creation_input_tokens={getattr(usage, 'cache_creation_input_tokens', 'n/a')}"
        )
```

- [ ] **Step 2: Run in collect-only mode to confirm discovery**

```bash
pixi run test -- tests/v3/extraction/test_anthropic_backend_integration.py --collect-only
```

Expected: 2 tests collected (one per mechanism), marked as `integration`. Both skip by default.

- [ ] **Step 3: Run with the integration marker (opt-in, no spend confirmation yet)**

```bash
pixi run test -- -m integration tests/v3/extraction/test_anthropic_backend_integration.py -v
```

Expected: 2 SKIPPED — the credit-cap gate skips without `ANTHROPIC_SMOKE_CONFIRM_SPEND=y`. This is the safe default.

- [ ] **Step 4: Commit Red**

```bash
git add tests/v3/extraction/test_anthropic_backend_integration.py
git commit -m "test(anthropic-backend): add live-API integration smoke scaffold with credit-cap gate (cycle 15)"
```

### Stage 15.B — Green

Green confirms the smoke passes against the live API and records the observed token usage in the commit message.

- [ ] **Step 1 (credit-cap gate — user confirmation required for live invocation)**

```bash
cat <<'EOF'
=== Cycle 15 Green — live-API smoke spend estimate ===

Calls to run: 2 (one per mechanism parametrization)
Per-call estimate (at claude-sonnet-4-6, 5,000-token thinking, warm cache):
  ~$0.05-$0.10 per call (warm cache lowers input cost)
Estimated total: ~$0.10-$0.20

Per project-anthropic-api-credit-cap: explicit user confirmation
required before consuming a meaningful portion of the $5 cap.
EOF
read -p "Continue with live smoke (y/N)? " ans
[ "$ans" = "y" ] || { echo "Aborted"; exit 1; }
```

- [ ] **Step 2: Run the live smoke with both confirmations set**

```bash
ANTHROPIC_API_KEY=<key> ANTHROPIC_SMOKE_CONFIRM_SPEND=y \
  pixi run test -- -m integration tests/v3/extraction/test_anthropic_backend_integration.py -v -s
```

The `-s` flag forwards stdout so the `[cycle-15 observation]` print lines are visible.

Expected: 2 PASS (or 1 PASS + 1 FAIL — if the live model unexpectedly raises ExtractionError under G1-positive, re-verify gates per the test's `AssertionError` branch).

- [ ] **Step 3: Record observed token usage**

Capture the `[cycle-15 observation]` lines from stdout. Note per-mechanism `input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`.

- [ ] **Step 4: Run the project gate (default mode)**

```bash
pixi run check
```

Expected: green; the integration test is skipped under default mode (the credit-cap gate fires before the no-API-key skip — both are valid skip mechanisms).

- [ ] **Step 5: Commit Green**

```bash
git add tests/v3/extraction/test_anthropic_backend_integration.py
git commit -m "$(cat <<'EOF'
feat(anthropic-backend): live-API smoke observation-only (cycle 15)

Both mechanisms passed live: ExtractionResult returned, grantor populated,
trace.backend_id prefix asserted, ≥1 grantor field in trace.

Observed token usage (one warm-cache run per mechanism):
  output_config: input=<N> output=<M> cache_read=<R> cache_creation=<C>
  tool_use:      input=<N> output=<M> cache_read=<R> cache_creation=<C>

Observation-only — no in-test ceiling assertion (per plan Q7).
Follow-up chore: calibrate CI ceiling after N≥3 observations.
EOF
)"
```

The Green commit is essentially observational record-keeping; no test source edits if Step 2 confirmed the scaffold from Red already passes. If the live call surfaced a structural issue (e.g., a missing assertion path), use the natural staged delta to land it.

</cycle>

---

## Self-review checklist (run once before declaring plan-md complete)

- [ ] **Spec coverage:** Every spec §7 row in the cycle range maps to exactly one `<cycle>` or `<task>` block. (8 → cycle-8; 9 → cycle-9; 11 → cycle-11; 12 → cycle-12; 13a → task-13a; 13b → cycle-13b; 15 → cycle-15. 7 rows, 7 blocks.)
- [ ] **Cross-references** to sibling cycles use the exact suffix `core` and the §7 cycle ids (1a, 1b, 2, 3, 4, 5, 6, 7, 10a, 10b, 10c, 10d, 10e, 10f, 14).
- [ ] **Gate G1-positive / G2-negative** referenced consistently; no dual-branch machinery remaining; no `_G1_*` / `_G2_*` constants.
- [ ] **Cycle 13a** is a `<task>` block, marked "NOT a TDD cycle" prominently, with Step 0 credit-cap gate.
- [ ] **Cycle 13b Red** reads `_decision.json` (stable-pointer aggregator) and skips if absent.
- [ ] **Cycle 15** scaffold has: `@pytest.mark.integration`, `ANTHROPIC_API_KEY` skip, `ANTHROPIC_SMOKE_FIXTURE_PATH` env-var override defaulting to `assets/handwriting-samples/pages/print.jpg`, parametrization over both mechanisms, observation-only on token usage, `ANTHROPIC_SMOKE_CONFIRM_SPEND` credit-cap gate.
- [ ] **Cycle 8 size guard** placed after MIME dispatch, per-MIME byte limits; **cycle 9 Red** asserts size guard auto-extension on oversized image.
- [ ] **Shared `_TEST_MODEL`** constant referenced in all cycles 8/9/11/12/13b; integration test uses `ANTHROPIC_SMOKE_MODEL` env override.
- [ ] **Predecessor verification** P1 (load-bearing), P2 (advisory only), P3-P6 (gates), P7 (credit-cap acknowledgment).
- [ ] **Blast-radius declared in plan metadata** matches splits.xml verbatim.
- [ ] **Cycle-range declared in plan metadata** matches splits.xml verbatim (`[§7.8..§7.9,§7.11..§7.13,§7.15..§7.15]`).
