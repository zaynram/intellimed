"""Mechanism benchmark runner for AnthropicBackend (task 13a).

NOT a pytest module — the leading underscore prevents pytest collection.

This script performs the live-API mechanism comparison between
``tool_use`` and ``output_config`` per the plan-md cycle 13a
procedure and writes the per-trial logs + ``_decision.json``
aggregator to ``tests/data/anthropic_mechanism_log/``.

User invocation (per the credit-cap audit trail):

    pixi run python tests/v3/extraction/_run_mechanism_benchmark.py

Requirements:
    - ANTHROPIC_API_KEY exported in the user's shell (read at runtime;
      fails with a clear error if absent — no default credential).
    - Working directory: repo root (the script resolves paths relative
      to this file's location and the repo's `assets/` directory).

Spend estimate (per plan-md / live-API STEP-0-GATE):
    2 mechanisms × 3 cache-warmed runs = 6 live API calls.
    Per-call ~$0.10 at claude-sonnet-4-6 with 5,000-token thinking budget.
    Total ~$0.60 (refined estimate after the actual usage block is read).

Idempotency:
    Per-trial filenames are date+timestamp-stamped, so re-runs do not
    clobber prior data. ``_decision.json`` is overwritten on each run
    (it is the canonical aggregator).
"""

from __future__ import annotations

import json
import os
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

# Ensure ``src/`` is on sys.path when run directly (pixi pyproject's src layout).
_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


# Pricing per million tokens at claude-sonnet-4-6 (model-pinned at SDK pin time).
# Source: Anthropic pricing page snapshot at plan-md authoring time. If pricing
# changes, update these constants and re-run the benchmark — the per-call cost
# estimate in printed output will track.
_PRICE_INPUT_PER_MTOK = 3.00
_PRICE_OUTPUT_PER_MTOK = 15.00
_PRICE_CACHE_WRITE_PER_MTOK = 3.75  # 1.25x input
_PRICE_CACHE_READ_PER_MTOK = 0.30  # 0.10x input

# Benchmark parameters (per plan-md cycle 13a procedure).
_MECHANISMS: tuple[str, ...] = ("tool_use", "output_config")
_RUNS_PER_MECHANISM = 3  # 1 cache-priming + 2 measurement
_THINKING_BUDGET_TOKENS = 5000
_MODEL = "claude-sonnet-4-6"  # Mirrors core cycle 4 __init__ default & _TEST_MODEL.
_FIXTURE_REL = "assets/handwriting-samples/pages/print.jpg"

# Artifact locations.
_LOG_DIR = _REPO_ROOT / "tests/data/anthropic_mechanism_log"
_DECISION_PATH = _LOG_DIR / "_decision.json"


def _require_api_key() -> str:
    """Read ANTHROPIC_API_KEY from env; fail with a clear message if absent.

    Per the project's credit-cap protocol, the key is never embedded in
    repo/agents/scripts — it lives in the user's shell only.
    """
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        print(
            "ERROR: ANTHROPIC_API_KEY is not set. "
            "Export it in your shell before running this benchmark:\n"
            "    export ANTHROPIC_API_KEY=<your-key>\n"
            "    pixi run python tests/v3/extraction/_run_mechanism_benchmark.py",
            file=sys.stderr,
        )
        sys.exit(2)
    return key


def _estimate_cost_usd(
    *,
    input_tokens: int,
    output_tokens: int,
    cache_creation_input_tokens: int,
    cache_read_input_tokens: int,
) -> float:
    """Approximate USD spend for one call based on the usage block.

    Note: ``input_tokens`` reported by the SDK is the *uncached* input
    portion; cache-creation and cache-read tokens are reported separately.
    """
    return (
        input_tokens * _PRICE_INPUT_PER_MTOK / 1_000_000
        + output_tokens * _PRICE_OUTPUT_PER_MTOK / 1_000_000
        + cache_creation_input_tokens * _PRICE_CACHE_WRITE_PER_MTOK / 1_000_000
        + cache_read_input_tokens * _PRICE_CACHE_READ_PER_MTOK / 1_000_000
    )


def _run_single_trial(
    *,
    backend,
    fixture_path: Path,
    mechanism: str,
    run_index: int,
    timestamp: str,
) -> dict:
    """Execute one extract() call, capture usage + timing, return the
    per-trial JSON dict per spec §9.4 shape (plus computed cost_usd).
    """
    from trust_generator.v3.extraction.protocol import ExtractionError

    captured_responses: list = []
    original_create = backend.client.messages.create

    def _capture(*args, **kwargs):
        response = original_create(*args, **kwargs)
        captured_responses.append(response)
        return response

    backend.client.messages.create = _capture  # type: ignore[assignment]

    success = False
    refusal = False
    schema_valid = False
    trace_field_count = 0
    error_message: str | None = None
    t0 = time.monotonic()
    try:
        result = backend.extract(fixture_path)
        success = True
        schema_valid = True
        trace_field_count = len(result.trace.fields)
    except ExtractionError as e:
        error_message = str(e)
        # Detect refusal in tool_use mode (no tool_use block emitted).
        if mechanism == "tool_use" and "tool_use" in str(e):
            refusal = True
    finally:
        latency_seconds = time.monotonic() - t0
        backend.client.messages.create = original_create  # restore

    # Pull usage from the captured response (if any).
    input_tokens = 0
    output_tokens = 0
    thinking_tokens = 0
    cache_read_input_tokens = 0
    cache_creation_input_tokens = 0
    if captured_responses:
        usage = captured_responses[-1].usage
        input_tokens = getattr(usage, "input_tokens", 0) or 0
        output_tokens = getattr(usage, "output_tokens", 0) or 0
        # The Anthropic SDK exposes thinking inside output_tokens (it's a
        # subset). When the SDK adds a separate counter, this assignment
        # picks it up automatically.
        thinking_tokens = getattr(usage, "thinking_tokens", 0) or 0
        cache_read_input_tokens = getattr(usage, "cache_read_input_tokens", 0) or 0
        cache_creation_input_tokens = (
            getattr(usage, "cache_creation_input_tokens", 0) or 0
        )

    cost_usd = _estimate_cost_usd(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_creation_input_tokens=cache_creation_input_tokens,
        cache_read_input_tokens=cache_read_input_tokens,
    )

    return {
        "run_id": f"{timestamp}-{mechanism}-run{run_index}",
        "fixture": _FIXTURE_REL,
        "mechanism": mechanism,
        "model": _MODEL,
        "thinking_budget_tokens": _THINKING_BUDGET_TOKENS,
        "latency_seconds": round(latency_seconds, 3),
        "input_tokens": int(input_tokens),
        "output_tokens": int(output_tokens),
        "thinking_tokens": int(thinking_tokens),
        "cache_read_input_tokens": int(cache_read_input_tokens),
        "cache_creation_input_tokens": int(cache_creation_input_tokens),
        "cost_usd_estimate": round(cost_usd, 4),
        "success": success,
        "refusal": refusal,
        "schema_valid": schema_valid,
        "trace_field_count": int(trace_field_count),
        "error_message": error_message,
        "cache_role": "priming" if run_index == 1 else "measurement",
    }


def _aggregate_and_decide(trials: list[dict]) -> dict:
    """Pick a winner from the per-trial logs. The prior is ``output_config``
    per spec §8.4 + G1-positive (composes with thinking). Tie-break uses
    success/refusal first, then measurement-run mean latency (warm cache).
    """
    by_mechanism: dict[str, list[dict]] = {m: [] for m in _MECHANISMS}
    for t in trials:
        by_mechanism[t["mechanism"]].append(t)

    stats: dict[str, dict] = {}
    for mechanism, mech_trials in by_mechanism.items():
        measurement_trials = [t for t in mech_trials if t["cache_role"] == "measurement"]
        latencies = [t["latency_seconds"] for t in measurement_trials]
        costs = [t["cost_usd_estimate"] for t in mech_trials]
        successes = [t["success"] for t in mech_trials]
        refusals = [t["refusal"] for t in mech_trials]
        stats[mechanism] = {
            "measurement_mean_latency": (
                round(statistics.mean(latencies), 3) if latencies else None
            ),
            "measurement_stdev_latency": (
                round(statistics.stdev(latencies), 3) if len(latencies) > 1 else 0.0
            ),
            "total_cost_usd": round(sum(costs), 4),
            "success_rate": (
                round(sum(successes) / len(successes), 3) if successes else 0.0
            ),
            "refusal_rate": (
                round(sum(refusals) / len(refusals), 3) if refusals else 0.0
            ),
        }

    # Tie-break order: success first, then refusal-free, then mean latency.
    # Under G1-positive prior, output_config wins ties.
    def _score(mechanism: str) -> tuple:
        s = stats[mechanism]
        # Lower is better for refusal_rate and latency; higher is better for success_rate.
        # Convert success/refusal to "lower-is-better" by negation/inversion.
        return (
            -s["success_rate"],
            s["refusal_rate"],
            s["measurement_mean_latency"] if s["measurement_mean_latency"] is not None else float("inf"),
        )

    sorted_mechanisms = sorted(_MECHANISMS, key=_score)
    raw_winner = sorted_mechanisms[0]

    # G1-positive tie-break in favor of output_config when both mechanisms
    # achieve full success and zero refusals AND mean latencies are within ~20%.
    output_config_stats = stats["output_config"]
    tool_use_stats = stats["tool_use"]
    if (
        output_config_stats["success_rate"] == 1.0
        and tool_use_stats["success_rate"] == 1.0
        and output_config_stats["refusal_rate"] == 0.0
        and tool_use_stats["refusal_rate"] == 0.0
        and output_config_stats["measurement_mean_latency"] is not None
        and tool_use_stats["measurement_mean_latency"] is not None
    ):
        oc_lat = output_config_stats["measurement_mean_latency"]
        tu_lat = tool_use_stats["measurement_mean_latency"]
        ratio = oc_lat / tu_lat
        if 0.8 <= ratio <= 1.25:
            winner = "output_config"
            rationale = (
                f"both mechanisms 100% success, 0% refusals; mean measurement "
                f"latency within ~20% ({oc_lat:.2f}s output_config vs "
                f"{tu_lat:.2f}s tool_use). G1-positive prior favors output_config "
                f"(composes cleanly with extended thinking; spec §8.4)."
            )
        else:
            winner = raw_winner
            rationale = (
                f"output_config mean latency {oc_lat:.2f}s vs tool_use "
                f"{tu_lat:.2f}s; ratio {ratio:.2f} outside tie-band — "
                f"raw winner {raw_winner} on latency."
            )
    else:
        winner = raw_winner
        rationale = (
            f"winner={raw_winner} chosen by success/refusal/latency ordering: "
            f"output_config success={output_config_stats['success_rate']}, "
            f"refusal={output_config_stats['refusal_rate']}, "
            f"mean_latency={output_config_stats['measurement_mean_latency']}; "
            f"tool_use success={tool_use_stats['success_rate']}, "
            f"refusal={tool_use_stats['refusal_rate']}, "
            f"mean_latency={tool_use_stats['measurement_mean_latency']}."
        )

    winner_log_files = [
        f"{t['run_id']}.json" for t in trials if t["mechanism"] == winner
    ]
    decided_at = datetime.now(tz=UTC).astimezone().isoformat()
    return {
        "winner": winner,
        "winner_log_files": winner_log_files,
        "rationale": rationale,
        "decided_at": decided_at,
        "per_mechanism_stats": stats,
        "total_calls": len(trials),
        "total_cost_usd_estimate": round(
            sum(t["cost_usd_estimate"] for t in trials), 4
        ),
    }


def main() -> int:
    api_key = _require_api_key()

    fixture_path = _REPO_ROOT / _FIXTURE_REL
    if not fixture_path.exists():
        print(f"ERROR: fixture not found at {fixture_path}", file=sys.stderr)
        return 2

    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Defer import until after env-validation so missing-dep errors are
    # clearly distinguishable from credential errors.
    from trust_generator.v3.extraction.anthropic_backend import AnthropicBackend

    timestamp = datetime.now(tz=UTC).strftime("%Y-%m-%d-%H%M%S")
    print(
        f"=== Mechanism benchmark — {timestamp} ===\n"
        f"  model: {_MODEL}\n"
        f"  thinking_budget_tokens: {_THINKING_BUDGET_TOKENS}\n"
        f"  fixture: {fixture_path} ({fixture_path.stat().st_size:,} bytes)\n"
        f"  mechanisms: {list(_MECHANISMS)}\n"
        f"  runs per mechanism: {_RUNS_PER_MECHANISM} "
        f"(1 cache-priming + {_RUNS_PER_MECHANISM - 1} measurement)\n"
        f"  log dir: {_LOG_DIR}\n"
    )

    trials: list[dict] = []
    grand_total_cost = 0.0
    for mechanism in _MECHANISMS:
        print(f"--- mechanism={mechanism} ---")
        # Fresh AnthropicBackend per mechanism — fresh prompt cache, no
        # bleed-through. The first run primes the cache for that mechanism;
        # runs 2..N measure warm-cache latency.
        backend = AnthropicBackend(
            model=_MODEL,
            api_key=api_key,
            mechanism=mechanism,  # type: ignore[arg-type]
            thinking_budget_tokens=_THINKING_BUDGET_TOKENS,
        )
        for run_index in range(1, _RUNS_PER_MECHANISM + 1):
            print(
                f"  run {run_index}/{_RUNS_PER_MECHANISM} "
                f"({'priming' if run_index == 1 else 'measurement'})... ",
                end="",
                flush=True,
            )
            trial = _run_single_trial(
                backend=backend,
                fixture_path=fixture_path,
                mechanism=mechanism,
                run_index=run_index,
                timestamp=timestamp,
            )
            trials.append(trial)
            log_path = _LOG_DIR / f"{trial['run_id']}.json"
            log_path.write_text(json.dumps(trial, indent=2) + "\n")
            print(
                f"done — latency={trial['latency_seconds']:.2f}s, "
                f"in={trial['input_tokens']} out={trial['output_tokens']} "
                f"cache_r={trial['cache_read_input_tokens']} "
                f"cache_c={trial['cache_creation_input_tokens']} "
                f"cost≈${trial['cost_usd_estimate']:.4f} "
                f"{'OK' if trial['success'] else ('REFUSAL' if trial['refusal'] else 'FAIL')}"
            )
            grand_total_cost += trial["cost_usd_estimate"]

    print(f"\n=== aggregating decision (total ≈ ${grand_total_cost:.4f}) ===")
    decision = _aggregate_and_decide(trials)
    _DECISION_PATH.write_text(json.dumps(decision, indent=2) + "\n")
    print(
        f"winner: {decision['winner']}\n"
        f"rationale: {decision['rationale']}\n"
        f"decision file: {_DECISION_PATH}\n"
        f"total_cost_usd_estimate: ${decision['total_cost_usd_estimate']:.4f}\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
