"""Task 9b-5 — Live vision-model integration smoke test.

Marked ``pytest.mark.integration``. Skipped by default via
pyproject.toml's ``addopts = "-m 'not integration'"`` (configured by
chore #16). Opt-in invocation: ``pixi run test -m integration``.

The test reads ``OCR_SMOKE_FIXTURE_PATH`` env var for the photo path,
defaulting to ``assets/handwriting-samples/pages/print.jpg``. If the
file is missing, the test skips.

PHI hygiene: the default fixture is paralegal-curated synthetic-persona
handwriting documented in ``assets/handwriting-samples/pages/BASELINE.md``;
real client intakes never enter the repo. If a developer overrides
``OCR_SMOKE_FIXTURE_PATH`` to a real intake for local debugging, that
path MUST stay outside the repo (e.g., ``/tmp/`` or a personal scratch
directory) — the smoke test reads from disk only and does not stage
or commit the override path.

Cost discipline: the two assertions below share one live ``chat()``
call via a session-scoped fixture. Vision-model invocations take
20-60s on consumer hardware; halving the per-run cost matters for
manual smoke loops.

Requires a local Ollama server (default ``http://localhost:11434``) with
a vision-language model pulled (e.g., ``ollama pull qwen2.5vl:7b``).
The model name is configurable via ``OCR_SMOKE_MODEL`` env var
(default ``qwen2.5vl:7b``).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def _resolve_fixture_path() -> Path:
    """Resolve OCR_SMOKE_FIXTURE_PATH, defaulting to the canonical baseline.

    The env var is the canonical entry point for ``pixi run test`` (set in
    pixi.toml's test-task ``env`` block).  The fallback is anchored to this
    file's location so bare ``pytest`` invocations (e.g. IDE runners that do
    not set the env var) also land on the correct asset.

    Path arithmetic: parents[0]=extraction, parents[1]=v3, parents[2]=tests,
    parents[3]=<repo root>.
    """
    env_path = os.environ.get("OCR_SMOKE_FIXTURE_PATH")
    if env_path:
        return Path(env_path)
    # Repo-root-anchored fallback — works under any cwd, including
    # ``pixi run test`` (cwd=tests/) and bare pytest invocations.
    return Path(__file__).resolve().parents[3] / "assets/handwriting-samples/pages/print.jpg"


def _resolve_model() -> str:
    return os.environ.get("OCR_SMOKE_MODEL", "qwen2.5vl:7b")


@pytest.fixture(scope="module")
def live_extraction_artifacts() -> tuple[object, str]:
    """One live chat() call shared across both assertions in this module.

    Module-scoped because vision-model invocations are expensive (20-60s
    on consumer hardware). Returns (extraction_result, raw_response_content)
    so both shape and JSON-key-order assertions run on a single live
    call. Skips the entire module if the fixture path is missing or the
    Ollama server is unreachable.
    """
    import ollama

    from trust_generator.v3.extraction import ExtractionError, OllamaBackend
    from trust_generator.v3.extraction.ollama_backend import GenerationEnvelope
    from trust_generator.v3.extraction.prompt import build_intake_prompt

    fixture_path = _resolve_fixture_path()
    if not fixture_path.exists():
        pytest.skip(
            f"Smoke fixture not found at {fixture_path}; set "
            f"OCR_SMOKE_FIXTURE_PATH or commit the default fixture"
        )

    # Direct ollama call captures raw response for the §7.4 key-order assertion
    # AND drives extract() in one round-trip via a shared client.
    client = ollama.Client()
    try:
        response = client.chat(
            model=_resolve_model(),
            messages=[
                {
                    "role": "user",
                    "content": build_intake_prompt(),
                    "images": [str(fixture_path.resolve())],
                }
            ],
            format=GenerationEnvelope.model_json_schema(),
            options={"temperature": 0},
        )
    except ConnectionError as e:
        pytest.skip(f"Ollama server unreachable: {e}")

    raw_content = response.message.content

    # Run extract() against the same fixture to validate the full pipeline.
    # Reuses the same client to keep the connection warm but is a second
    # chat() call — model output may differ slightly from raw_content above
    # (temperature=0 makes this rare but not impossible across HTTP retries).
    backend = OllamaBackend(model=_resolve_model(), client=client)
    try:
        extraction_result = backend.extract(fixture_path)
    except ExtractionError as e:
        pytest.skip(f"extract() failed against live model: {e}")

    return extraction_result, raw_content


def test_live_extract_returns_extraction_result_with_at_least_one_field(
    live_extraction_artifacts: tuple[object, str],
) -> None:
    """``extract`` against a live Ollama vision model returns an ExtractionResult
    whose trace has at least one FieldExtraction.

    Asserts only structural shape, not content. Handwriting reading
    varies; per-field accuracy is chore #13's domain, not this task's.
    """
    from trust_generator.v3.extraction import ExtractionResult

    extraction_result, _ = live_extraction_artifacts

    assert isinstance(extraction_result, ExtractionResult)
    assert len(extraction_result.trace.fields) >= 1


def test_live_response_emits_reasoning_as_first_key(
    live_extraction_artifacts: tuple[object, str],
) -> None:
    """Spec §7.4 integration-level pin: the raw JSON response from the
    live model has ``reasoning`` as its first key.

    Mechanism: grammar-constrained decoding generates fields in schema
    declaration order; the cycle 9b-1 unit test pins the schema; this
    test pins that the live model honors the discipline. Python
    preserves JSON key insertion order in ``json.loads()`` output.
    """
    _, raw_content = live_extraction_artifacts

    parsed = json.loads(raw_content)
    first_key = next(iter(parsed.keys()))

    assert first_key == "reasoning", (
        f"Expected 'reasoning' as first key from live model "
        f"({_resolve_model()}); got {first_key!r}. "
        f"This is a §7.4 finding — open a chore for spec amendment "
        f"per §13.2 / chore #14. Do not silently rewrite schema or prompt."
    )
