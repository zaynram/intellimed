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
    model; falls back to ``claude-sonnet-4-6`` (mirrors core cycle 4
    ctor default and the unit suite's _TEST_MODEL).
  - ``ANTHROPIC_SMOKE_CONFIRM_SPEND`` (required for live runs) — set to
    "y" to acknowledge the spend per project-anthropic-api-credit-cap;
    absent ⇒ the session-scoped gate skips all tests in this module.

Cost: each live ``messages.create`` call costs real Anthropic API
spend. The test parametrizes over both mechanisms ⇒ 2 live calls per
opt-in run. Refined estimate from task 13a actuals: ~$0.013/call ⇒
~$0.026/run total (down from the plan-md's stale $0.20 quote, which
predated task 13a's empirical per-call measurement).

Observation-only on token usage — see plan §"Cycle 15" Q7 / observation-only
posture. Each call's response.usage block is printed; commit message
records totals. No in-test ceiling assertion in this plan; calibration
is deferred to a follow-up chore once N≥3 observations accumulate
across separate runs.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from trust_generator.v3.extraction import ExtractionError, ExtractionResult
from trust_generator.v3.extraction.anthropic_backend import AnthropicBackend

pytestmark = pytest.mark.integration


# Default test model — mirrors core cycle 4's ctor default and the
# unit suite's _TEST_MODEL constant.
_DEFAULT_MODEL: str = "claude-sonnet-4-6"


def _resolve_fixture_path() -> Path:
    """Resolve ANTHROPIC_SMOKE_FIXTURE_PATH, defaulting to the canonical baseline."""
    env_path = os.environ.get("ANTHROPIC_SMOKE_FIXTURE_PATH")
    if env_path:
        return Path(env_path)
    # parents[0]=extraction, [1]=v3, [2]=tests, [3]=<repo root>
    return (
        Path(__file__).resolve().parents[3]
        / "assets/handwriting-samples/pages/print.jpg"
    )


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
            "Refined estimate (per task 13a actuals): 2 calls × ~$0.013 "
            "≈ $0.026 against the ~$5 credit cap. "
            "Set ANTHROPIC_SMOKE_CONFIRM_SPEND=y to confirm and re-run."
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
) -> None:
    """One live Anthropic API call per mechanism. Asserts:
      - ExtractionResult returned (not ExtractionError).
      - trace.backend_id starts with "anthropic:".
      - trace.fields contains at least one entry under the "grantor." prefix.

    Contract surface (established by wave-1 cycles 5/6/7, mirrored on
    OllamaBackend at ollama_backend.py:351-387): the extraction layer
    populates ``result.trace.fields[i].raw_value`` with extracted OCR
    values; ``TrustData.grantor`` is the *downstream* normalization
    target, default-constructed at the extraction layer. This test
    therefore asserts ``trace.*`` shape, NOT ``data.grantor.*``
    population — that would target the wrong contract surface.

    Observation-only on token usage: the test prints the response.usage
    block to stdout for the commit message to record. No ceiling
    assertion lands in this plan; calibration is deferred to a follow-up
    chore once N≥3 observations accumulate.
    """
    backend = AnthropicBackend(
        model=_resolve_model(),
        mechanism=mechanism,  # type: ignore[arg-type]
    )

    # Monkey-patch the client's messages.create to record the response.
    # Alternative: rely on AnthropicBackend exposing the last response —
    # but no such attribute is added in this plan (Q7).
    captured_responses: list = []
    original_create = backend.client.messages.create

    def _capture(*args: object, **kwargs: object) -> object:
        response = original_create(*args, **kwargs)
        captured_responses.append(response)
        return response

    backend.client.messages.create = _capture  # type: ignore[assignment]

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

    # backend_id prefix.
    assert result.trace.backend_id.startswith("anthropic:"), (
        f"backend_id should start with 'anthropic:'; got {result.trace.backend_id!r}"
    )

    # At least one grantor field in the trace.
    grantor_fields = [
        f for f in result.trace.fields if f.field_path.startswith("grantor.")
    ]
    assert grantor_fields, (
        f"trace.fields contains no entries under 'grantor.'; "
        f"all paths: {[f.field_path for f in result.trace.fields]}"
    )

    # NOTE: deliberately no assertion on result.data.grantor.full_legal_name.
    # The extraction-layer contract is "trace carries extracted values; data
    # is downstream normalization target" (see test docstring above and
    # ollama_backend.py:351-387's _envelope_to_extraction_result docstring).
    # An earlier failed run of this smoke (committed Red at 914f9bb) asserted
    # data.grantor.full_legal_name and fired against a default-constructed
    # GrantorInfo on both mechanisms — proving the assertion targeted the
    # wrong contract surface, not a code defect. The corrected assertion set
    # asserts on trace.fields shape only; a future chore may add an assertion
    # that raw_value is non-empty + illegible=False once N≥3 legible-handwriting
    # observations stabilize the empirical expectation.

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
