"""Chore #14 — Envelope complexity ceiling benchmark.

Characterises pass-rate vs. envelope size for candidate vision models
under grammar-constrained decoding (the llama.cpp mechanism Ollama
inherits).  Marked ``pytest.mark.integration``; skipped by default
under ``pixi run test``.  Opt-in: ``pixi run test -- -m integration``.

Two variants per (model × field-count) cell:

reasoning_present=True
    The envelope's first field is a ``str``-typed ``reasoning`` channel,
    matching the §7.4 production posture.

reasoning_present=False
    The envelope omits the leading ``reasoning`` field entirely, yielding
    the same data fields starting at position 0.  This is the §7.4
    evidence-gathering surface: does omitting ``reasoning`` shift the
    complexity ceiling?

Results are persisted per run to
``tests/data/extraction_ceiling_log/<ISO-timestamp>.jsonl`` (one JSON
line per cell) regardless of pass/fail.  The log is the primary
deliverable; the test assertions are soft (the test logs and continues
on failure, collecting a full grid per run).

Requires a local Ollama server on ``127.0.0.1:11434`` with at least one
vision-capable model available.  If the server is unreachable or no
vision models are present, the entire module is skipped.

Model filtering: vision-capable families are identified by name prefix
(``qwen2.5vl``, ``minicpm``, ``gemma3``).  ``qwen2.5:0.5b`` is
text-only and excluded.

Scope overrides via environment variables (both optional):

``OCR_CEILING_MODELS``
    Comma-separated allowlist of exact model names; when set, restricts
    discovery to the named models only.  Example:
    ``OCR_CEILING_MODELS=qwen2.5vl:7b``.

``OCR_CEILING_FIELD_COUNTS``
    Comma-separated list of integers overriding ``_FIELD_COUNT_SWEEP``.
    Example: ``OCR_CEILING_FIELD_COUNTS=3,5,10`` runs only the small
    cells (the chore-#32 scope).

Historical: chore #14 ran this harness against ``qwen2.5vl:3b`` only
(GPU stack was degraded at the time); chore #30 resolved the SYCL
runner crash that gated ``qwen2.5vl:7b`` vision (see
``docs/session-notes/2026-05-11-chore-30-resolution.md``).
"""

from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict, Field

pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VISION_FAMILY_PREFIXES = ("qwen2.5vl", "minicpm-v", "minicpm_v", "minicpm", "gemma3")
"""Name prefixes considered vision-capable for model filtering."""

# Field-count sweep: production envelope has 3 top-level fields.
# Sweep from production scale upward to find the ceiling.
# Override via OCR_CEILING_FIELD_COUNTS env var (comma-separated ints).
_FIELD_COUNT_SWEEP = (
    [int(s.strip()) for s in os.environ["OCR_CEILING_FIELD_COUNTS"].split(",") if s.strip()]
    if os.environ.get("OCR_CEILING_FIELD_COUNTS")
    else [3, 5, 10, 15, 20, 30, 50]
)
"""Synthetic envelope sizes (top-level field count) to sweep."""

# Optional allowlist of exact model names; when set, restricts discovery
# to the named models only.  Comma-separated.
_MODEL_ALLOWLIST: frozenset[str] | None = (
    frozenset(s.strip() for s in os.environ["OCR_CEILING_MODELS"].split(",") if s.strip())
    if os.environ.get("OCR_CEILING_MODELS")
    else None
)
"""Optional allowlist restricting discovery to named models."""

# Per-request timeout (seconds); 7b vision on a 10-field schema can run
# 2-4 minutes under SYCL.  Default of 600s gives headroom without
# masking pathological wedges.
_OLLAMA_REQUEST_TIMEOUT_S = float(os.environ.get("OCR_CEILING_REQUEST_TIMEOUT_S", "600"))
"""Per-request timeout for the Ollama client (seconds)."""

_REASONING_VARIANTS = [True, False]
"""Whether the leading ``reasoning`` field is included."""

_LOG_DIR = Path(__file__).resolve().parents[2] / "data" / "extraction_ceiling_log"
"""Absolute path to the JSONL log directory (tests/data/extraction_ceiling_log/)."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_fixture_path() -> Path:
    """Resolve image fixture path; anchored to repo root."""
    env_path = os.environ.get("OCR_SMOKE_FIXTURE_PATH")
    if env_path:
        return Path(env_path)
    # parents: [0]=extraction, [1]=v3, [2]=tests, [3]=<repo root>
    return (
        Path(__file__).resolve().parents[3]
        / "assets/handwriting-samples/pages/print.jpg"
    )


def _is_vision_model(name: str) -> bool:
    """Return True if the model name matches a known vision-capable family."""
    lower = name.lower()
    return any(lower.startswith(prefix) for prefix in _VISION_FAMILY_PREFIXES)


def _build_synthetic_envelope_schema(
    field_count: int,
    *,
    reasoning_present: bool,
) -> dict[str, Any]:
    """Build a flat JSON schema with ``field_count`` string-or-null fields.

    When ``reasoning_present=True`` the first field is ``reasoning``
    (max_length=2000, required), matching the §7.4 production posture.
    The remaining fields are named ``field_01`` … ``field_N``.

    When ``reasoning_present=False`` all fields are ``field_01`` …
    ``field_N`` with no leading reasoning channel.

    All fields are simple ``string | null`` (optional, default null)
    except ``reasoning`` when present (required string).  This is the
    simplest flat schema that stresses the grammar FSM at the target
    complexity without introducing $refs or nested objects.
    """
    properties: dict[str, Any] = {}
    required: list[str] = []

    if reasoning_present:
        properties["reasoning"] = {
            "title": "Reasoning",
            "type": "string",
            "maxLength": 2000,
        }
        required.append("reasoning")
        data_field_count = field_count - 1
    else:
        data_field_count = field_count

    for i in range(1, data_field_count + 1):
        fname = f"field_{i:02d}"
        properties[fname] = {
            "anyOf": [{"type": "string"}, {"type": "null"}],
            "default": None,
            "title": fname.replace("_", " ").title(),
        }

    schema: dict[str, Any] = {
        "title": "SyntheticEnvelope",
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
    }
    if required:
        schema["required"] = required
    return schema


# ---------------------------------------------------------------------------
# Module-scoped setup: discover models and open log file
# ---------------------------------------------------------------------------


def _discover_vision_models() -> list[str]:
    """Query local Ollama tags endpoint; return vision-model names.

    Honors ``OCR_CEILING_MODELS`` env var (exact-name allowlist) when
    set; otherwise filters by vision-family prefix.
    """
    import httpx

    try:
        resp = httpx.get("http://127.0.0.1:11434/api/tags", timeout=5.0)
        resp.raise_for_status()
        models = resp.json().get("models", [])
        names = [m["name"] for m in models if _is_vision_model(m["name"])]
        if _MODEL_ALLOWLIST is not None:
            names = [n for n in names if n in _MODEL_ALLOWLIST]
        return names
    except (httpx.HTTPError, ConnectionError, OSError, ValueError, KeyError):
        return []


@pytest.fixture(scope="module")
def vision_models() -> list[str]:
    """Return available vision models; skip module if none present."""
    models = _discover_vision_models()
    if not models:
        pytest.skip("No vision-capable Ollama models found on 127.0.0.1:11434")
    return models


@pytest.fixture(scope="module")
def log_writer() -> Any:
    """Open the per-run JSONL log file; yield a writer callable; flush on teardown."""
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    log_path = _LOG_DIR / f"{ts}.jsonl"
    records: list[str] = []

    def _write(record: dict[str, Any]) -> None:
        records.append(json.dumps(record))

    yield _write

    with log_path.open("w", encoding="utf-8") as fh:
        for line in records:
            fh.write(line + "\n")


@pytest.fixture(scope="module")
def fixture_image(vision_models: list[str]) -> Path:
    """Resolve and validate the fixture image path."""
    path = _resolve_fixture_path()
    if not path.exists():
        pytest.skip(
            f"OCR fixture not found at {path}; "
            "set OCR_SMOKE_FIXTURE_PATH or commit the default fixture"
        )
    return path


# ---------------------------------------------------------------------------
# Parametrized benchmark
# ---------------------------------------------------------------------------


def _make_params() -> list[tuple[int, bool]]:
    """Return the full (field_count, reasoning_present) grid."""
    return [
        (fc, rp)
        for fc in _FIELD_COUNT_SWEEP
        for rp in _REASONING_VARIANTS
    ]


@pytest.mark.parametrize("field_count,reasoning_present", _make_params())
def test_envelope_complexity_ceiling(
    field_count: int,
    reasoning_present: bool,
    vision_models: list[str],
    log_writer: Any,
    fixture_image: Path,
) -> None:
    """Drive all available vision models against a synthetic envelope of the
    given size; log pass/fail/timing to the JSONL sink.

    The test never hard-fails on model-side errors — it logs the result
    and continues.  An ``xfail`` is issued when *all* models fail for
    a given cell, which surfaces in the test report without blocking the
    run.

    Pass criterion: Ollama returns 200 and the response parses as valid
    JSON conforming to the schema (checked via ``model_validate_json``
    on a dynamically created Pydantic model).  Schema-violation retries
    are counted as failures at this layer; the benchmark does not retry.
    """
    import ollama

    schema = _build_synthetic_envelope_schema(
        field_count, reasoning_present=reasoning_present
    )
    schema_bytes = len(json.dumps(schema))

    # Dynamically create a Pydantic validator for post-hoc response validation
    field_defs: dict[str, Any] = {}
    if reasoning_present:
        field_defs["reasoning"] = (str, Field(max_length=2000))

    data_field_count = field_count - (1 if reasoning_present else 0)
    for i in range(1, data_field_count + 1):
        fname = f"field_{i:02d}"
        field_defs[fname] = (str | None, Field(default=None))

    SyntheticModel = type(
        "SyntheticModel",
        (BaseModel,),
        {
            "__annotations__": {k: v[0] for k, v in field_defs.items()},
            "model_config": ConfigDict(extra="forbid"),
            **{k: v[1] for k, v in field_defs.items()},
        },
    )

    all_passed = True
    prompt = (
        "You are extracting fields from a handwritten intake form. "
        "Fill in each field from the form. Leave fields null if not visible."
    )

    for model_name in vision_models:
        client = ollama.Client(timeout=_OLLAMA_REQUEST_TIMEOUT_S)
        t_start = time.monotonic()
        passed = False
        error_class: str | None = None
        error_detail: str | None = None
        raw_content: str | None = None

        try:
            response = client.chat(
                model=model_name,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                        "images": [str(fixture_image.resolve())],
                    }
                ],
                format=schema,
                options={"temperature": 0},
            )
            raw_content = response.message.content or ""
            # Validate: must parse as valid JSON matching our schema
            SyntheticModel.model_validate_json(raw_content)
            passed = True
        except ollama.ResponseError as e:
            error_class = "OllamaResponseError"
            error_detail = f"status={e.status_code}: {e}"
        except ConnectionError as e:
            error_class = "ConnectionError"
            error_detail = str(e)
        except Exception as e:  # noqa: BLE001
            # Pydantic ValidationError, JSON decode error, etc.
            error_class = type(e).__name__
            error_detail = str(e)[:500]

        elapsed = time.monotonic() - t_start
        if not passed:
            all_passed = False

        log_writer(
            {
                "model": model_name,
                "field_count": field_count,
                "reasoning_present": reasoning_present,
                "schema_bytes": schema_bytes,
                "passed": passed,
                "error_class": error_class,
                "error_detail": error_detail,
                "elapsed_s": round(elapsed, 3),
                "raw_content_snippet": (raw_content or "")[:300] if raw_content else None,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

    if not all_passed and len(vision_models) > 0:
        # Soft-fail: mark as expected-failure so the grid completes
        # but failures are visible in the test report.
        pytest.xfail(
            f"One or more models failed at field_count={field_count}, "
            f"reasoning_present={reasoning_present}. "
            "See tests/data/extraction_ceiling_log/ for per-model detail."
        )
