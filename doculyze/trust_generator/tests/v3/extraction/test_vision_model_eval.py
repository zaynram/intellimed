"""Chore #29 — vision-model eval extension (integration test).

Extends chore-#13's evaluation methodology (qwen2.5vl:7b vs minicpm-v)
to additional candidates with per-field MATCH/MISMATCH/OMITTED/
HALLUCINATION verdicts.  See
``docs/session-notes/2026-04-30-vision-model-eval.md`` for the
methodology details and historical results.

Inter-candidate hygiene: ``keep_alive=0`` ping between models —
required because IPEX-LLM SYCL doesn't surface to Ollama's GPU
residency tracking, so the default 10-min keep-alive leaves the prior
model resident and the second model fails with
``unable to allocate SYCL0 buffer`` even when total bytes would fit.

Marked ``pytest.mark.integration``; skipped by default.  Run with::

    pixi run test -- -m integration v3/extraction/test_vision_model_eval.py

Scope overrides via environment variable:

``OCR_EVAL_MODELS``
    Comma-separated allowlist of exact model names; when set, restricts
    candidates to the named models.  Example:
    ``OCR_EVAL_MODELS=qwen2.5vl:3b``.  Default candidates are
    ``qwen2.5vl:3b`` and ``gemma3:12b`` per chore #29.

Logs to ``tests/data/vision_eval_log/<ISO-timestamp>.jsonl`` (gitignored;
the session note is the durable record).
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import httpx
import ollama
import pytest

from trust_generator.v3.extraction.ollama_backend import OllamaBackend
from trust_generator.v3.extraction.protocol import ExtractionError
from trust_generator.v3.extraction.trace import FieldExtraction

pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_CANDIDATES = ("qwen2.5vl:3b", "gemma3:12b")
"""Default candidate models for chore #29.  Override via OCR_EVAL_MODELS."""

_CANDIDATES: tuple[str, ...] = (
    tuple(s.strip() for s in os.environ["OCR_EVAL_MODELS"].split(",") if s.strip())
    if os.environ.get("OCR_EVAL_MODELS")
    else _DEFAULT_CANDIDATES
)

_REPO = Path(__file__).resolve().parents[3]
_FIXTURES_ROOT = _REPO / "assets/handwriting-samples"
_LOG_DIR = Path(__file__).resolve().parents[2] / "data" / "vision_eval_log"

_OLLAMA_REQUEST_TIMEOUT_S = float(os.environ.get("OCR_EVAL_REQUEST_TIMEOUT_S", "600"))


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


class Verdict(StrEnum):
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    OMITTED = "OMITTED"
    HALLUCINATION = "HALLUCINATION"
    ILLEGIBLE_CORRECT = "ILLEGIBLE_CORRECT"
    ILLEGIBLE_FALSE_POSITIVE = "ILLEGIBLE_FALSE_POSITIVE"
    ILLEGIBLE_FALSE_NEGATIVE = "ILLEGIBLE_FALSE_NEGATIVE"


@dataclass(frozen=True)
class Expected:
    """Ground-truth row for one (fixture, field_path) slot."""

    field_path: str
    raw_value: str
    illegible: bool = False


# ---------------------------------------------------------------------------
# Ground truth (BASELINE.md + SNIPPETS.md)
# ---------------------------------------------------------------------------

_CANONICAL_PAYLOAD = [
    Expected("grantor.full_legal_name", "James William Thompson, Jr."),
    Expected("grantor.date_of_birth", "March 15, 1958"),
    Expected("co_grantor.full_legal_name", "Mary-Beth O'Brien"),
    Expected("co_grantor.date_of_birth", "11/08/1960"),
    Expected("other_beneficiaries[0].full_legal_name", "Sarah Lin Thompson"),
    Expected("other_beneficiaries[0].relationship_other", "daughter"),
    Expected("beneficiary_shares[0].share_percent", "50"),
    Expected("other_beneficiaries[1].full_legal_name", "Michael Thompson"),
    Expected("other_beneficiaries[1].relationship_other", "son"),
    Expected("beneficiary_shares[1].share_percent", "50"),
]

# Cursive: same payload, beneficiaries swapped per BASELINE.md.
_CURSIVE_SWAPPED_PAYLOAD = [
    e
    for e in _CANONICAL_PAYLOAD
    if not e.field_path.startswith(("other_beneficiaries", "beneficiary_shares"))
] + [
    Expected("other_beneficiaries[0].full_legal_name", "Michael Thompson"),
    Expected("other_beneficiaries[0].relationship_other", "son"),
    Expected("beneficiary_shares[0].share_percent", "50"),
    Expected("other_beneficiaries[1].full_legal_name", "Sarah Lin Thompson"),
    Expected("other_beneficiaries[1].relationship_other", "daughter"),
    Expected("beneficiary_shares[1].share_percent", "50"),
]

_GROUND_TRUTH: dict[str, list[Expected]] = {
    "pages/print.jpg": _CANONICAL_PAYLOAD,
    "pages/cursive.jpg": _CURSIVE_SWAPPED_PAYLOAD,
    "pages/hurried.jpg": _CANONICAL_PAYLOAD,
    "pages/all-caps.jpg": _CANONICAL_PAYLOAD,
    "snippets/absent-fields.jpg": [
        # [?] wildcard: model may emit at either index — match by suffix+value.
        Expected("beneficiary_shares[?].share_percent", "50"),
        Expected("other_beneficiaries[?].full_legal_name", "Michael Thompson"),
    ],
    "snippets/label-on-line-N.jpg": [
        Expected("grantor.full_legal_name", "James William Thompson, Jr."),
    ],
}

_QUALITATIVE_FIXTURES = (
    "snippets/punctuation-stress.jpg",
    "snippets/date-format-variance.jpg",
)
_ILLEGIBILITY_FIXTURE = "snippets/illegibility-stress.jpg"

_ALL_FIXTURES = [
    *(f"pages/{n}" for n in ("print.jpg", "cursive.jpg", "hurried.jpg", "all-caps.jpg")),
    *(
        f"snippets/{n}"
        for n in (
            "absent-fields.jpg",
            "illegibility-stress.jpg",
            "label-on-line-N.jpg",
            "punctuation-stress.jpg",
            "date-format-variance.jpg",
        )
    ),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _norm(s: str | None) -> str:
    """Lenient normalization: case-fold + whitespace-collapse + strip.

    Preserves punctuation, dollar signs, hyphens — §8.1 verbatim
    discipline is checked at strict-equality tier, not lenient.
    """
    if s is None:
        return ""
    return re.sub(r"\s+", " ", s).strip().casefold()


def _score_field(
    expected: Expected,
    observed: FieldExtraction | None,
) -> tuple[Verdict, str | None]:
    """Compare one observed FieldExtraction against ground truth.

    Returns ``(verdict, optional_note)``.  Decision tree:

    1. ``observed is None`` → OMITTED, or ILLEGIBLE_FALSE_NEGATIVE if the
       ground truth expected an illegibility flag.
    2. Illegibility flag 2×2 against expected:
       (both True) ILLEGIBLE_CORRECT;
       (obs=True, exp=False) ILLEGIBLE_FALSE_POSITIVE;
       (obs=False, exp=True) ILLEGIBLE_FALSE_NEGATIVE.
    3. Both legible: strict equality → MATCH (no note);
       lenient (via ``_norm``) → MATCH with note describing what made it
       lenient (case-only / whitespace-only / case+whitespace);
       neither → MISMATCH.

    HALLUCINATION detection is fixture-level (see ``_run_fixture``); this
    function operates only on ground-truthed slots.
    """
    if observed is None:
        return (
            (Verdict.ILLEGIBLE_FALSE_NEGATIVE, None)
            if expected.illegible
            else (Verdict.OMITTED, None)
        )
    if observed.illegible and expected.illegible:
        return Verdict.ILLEGIBLE_CORRECT, None
    if observed.illegible and not expected.illegible:
        return Verdict.ILLEGIBLE_FALSE_POSITIVE, None
    if not observed.illegible and expected.illegible:
        return Verdict.ILLEGIBLE_FALSE_NEGATIVE, None
    if observed.raw_value == expected.raw_value:
        return Verdict.MATCH, None
    if _norm(observed.raw_value) == _norm(expected.raw_value):
        case_diff = observed.raw_value.lower() == expected.raw_value.lower()
        ws_diff = re.sub(r"\s+", " ", observed.raw_value).strip() == re.sub(
            r"\s+", " ", expected.raw_value
        ).strip()
        if case_diff and not ws_diff:
            note = "lenient match: case-only"
        elif ws_diff and not case_diff:
            note = "lenient match: whitespace-only"
        else:
            note = "lenient match: case+whitespace"
        return Verdict.MATCH, note
    return Verdict.MISMATCH, None


def _find_match(
    expected: Expected,
    observed_fields: list[FieldExtraction],
) -> FieldExtraction | None:
    """Find the observed FieldExtraction matching ``expected.field_path``.

    Handles the ``[?]`` wildcard for ``absent-fields.jpg`` ground truth —
    the model may emit at either index, so the match is by path-suffix
    plus value-equivalence under ``_norm``.
    """
    if "[?]" in expected.field_path:
        prefix = expected.field_path.split("[?]", 1)[0]
        suffix = expected.field_path.split("]", 1)[1]
        for obs in observed_fields:
            if (
                obs.field_path.startswith(prefix)
                and obs.field_path.endswith(suffix)
                and _norm(obs.raw_value) == _norm(expected.raw_value)
            ):
                return obs
        return None
    for obs in observed_fields:
        if obs.field_path == expected.field_path:
            return obs
    return None


def _evict_model(model: str) -> None:
    """Force-evict a model via ``keep_alive=0`` ping."""
    try:
        httpx.post(
            "http://127.0.0.1:11434/api/generate",
            json={"model": model, "keep_alive": 0},
            timeout=10.0,
        )
    except httpx.HTTPError:
        pass  # best-effort


def _run_fixture(backend: OllamaBackend, fixture_rel: str) -> dict[str, Any]:
    """Run inference on one fixture; return a record dict for the log."""
    src = _FIXTURES_ROOT / fixture_rel
    t_start = time.monotonic()
    error_class: str | None = None
    error_detail: str | None = None
    verdicts: list[dict[str, Any]] = []
    observed: list[FieldExtraction] = []

    try:
        result = backend.extract(src)
        observed = list(result.trace.fields)

        if fixture_rel in _GROUND_TRUTH:
            expected_rows = _GROUND_TRUTH[fixture_rel]
            matched_obs_paths: set[str] = set()
            for exp in expected_rows:
                obs = _find_match(exp, observed)
                v, note = _score_field(exp, obs)
                verdicts.append(
                    {
                        "expected_path": exp.field_path,
                        "expected_value": exp.raw_value,
                        "observed_path": obs.field_path if obs else None,
                        "observed_value": obs.raw_value if obs else None,
                        "observed_illegible": obs.illegible if obs else None,
                        "verdict": v.value,
                        "note": note,
                    }
                )
                if obs is not None:
                    matched_obs_paths.add(obs.field_path)
            for obs in observed:
                if obs.field_path not in matched_obs_paths:
                    verdicts.append(
                        {
                            "expected_path": None,
                            "expected_value": None,
                            "observed_path": obs.field_path,
                            "observed_value": obs.raw_value,
                            "observed_illegible": obs.illegible,
                            "verdict": Verdict.HALLUCINATION.value,
                            "note": "field emitted outside ground truth",
                        }
                    )
        elif fixture_rel == _ILLEGIBILITY_FIXTURE:
            illegible_count = sum(1 for f in observed if f.illegible)
            legible_match = any(
                not f.illegible
                and _norm(f.raw_value) == _norm("Sarah Lin Thompson")
                for f in observed
            )
            shape_pass = illegible_count >= 1 and legible_match
            verdicts.append(
                {
                    "fixture_shape_check": True,
                    "illegible_count": illegible_count,
                    "legible_match_present": legible_match,
                    "verdict": (
                        Verdict.MATCH.value if shape_pass else Verdict.MISMATCH.value
                    ),
                    "note": "§8.1 illegibility-shape-check (no per-field scoring)",
                }
            )
        elif fixture_rel in _QUALITATIVE_FIXTURES:
            pass  # qualitative review only
    except ExtractionError as e:
        error_class = type(e).__name__
        error_detail = str(e)[:500]
    except Exception as e:  # noqa: BLE001
        error_class = type(e).__name__
        error_detail = str(e)[:500]

    return {
        "model": backend.model,
        "fixture": fixture_rel,
        "elapsed_s": round(time.monotonic() - t_start, 3),
        "field_count_extracted": len(observed),
        "error_class": error_class,
        "error_detail": error_detail,
        "verdicts": verdicts,
        "raw_observed": [
            {
                "field_path": f.field_path,
                "raw_value": f.raw_value,
                "illegible": f.illegible,
            }
            for f in observed
        ]
        if not error_class
        else [],
        "timestamp": datetime.now(UTC).isoformat(),
    }


def _ollama_reachable() -> bool:
    try:
        httpx.get("http://127.0.0.1:11434/api/tags", timeout=5.0).raise_for_status()
        return True
    except (httpx.HTTPError, ConnectionError, OSError):
        return False


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


def test_vision_model_eval() -> None:
    """Chore-#29 vision-model eval over all candidates × all fixtures.

    Single test cell that runs the full grid (per chore-#13's
    methodology).  Logs per-(candidate, fixture) records to JSONL; the
    test soft-fails (``pytest.xfail``) only when *no* candidate clears
    the chore-#13 illustrative >85% per-field MATCH bar — i.e., the
    test is a data-collection harness, not a model-acceptance gate.
    """
    if not _ollama_reachable():
        pytest.skip("Ollama unreachable at 127.0.0.1:11434")

    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    log_path = _LOG_DIR / f"{ts}.jsonl"

    records: list[dict[str, Any]] = []
    scorable = {
        Verdict.MATCH.value,
        Verdict.MISMATCH.value,
        Verdict.OMITTED.value,
        Verdict.HALLUCINATION.value,
    }

    for candidate in _CANDIDATES:
        client = ollama.Client(timeout=_OLLAMA_REQUEST_TIMEOUT_S)
        backend = OllamaBackend(model=candidate, client=client)
        for fixture_rel in _ALL_FIXTURES:
            rec = _run_fixture(backend, fixture_rel)
            records.append(rec)
        _evict_model(candidate)

    with log_path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, default=str) + "\n")

    # Aggregate
    cleared = False
    for candidate in _CANDIDATES:
        cand_recs = [r for r in records if r["model"] == candidate]
        match_n = sum(
            1
            for r in cand_recs
            for v in r["verdicts"]
            if v.get("verdict") == Verdict.MATCH.value
        )
        scored_n = sum(
            1
            for r in cand_recs
            for v in r["verdicts"]
            if v.get("verdict") in scorable
        )
        rate = (match_n / scored_n * 100) if scored_n else 0.0
        if rate > 85.0:
            cleared = True

    if not cleared:
        pytest.xfail(
            "No candidate cleared the chore-#13 illustrative >85% MATCH bar. "
            f"See log {log_path} for per-cell detail."
        )
