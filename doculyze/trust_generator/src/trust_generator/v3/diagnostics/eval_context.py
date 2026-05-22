"""Compose the dict-shaped context that rule expressions evaluate against.

Per spec §5.2: nested under three top-level namespaces (`trust`, `firm`, `now`)
so rule expressions read as ``trust.elections.estate_value_approximate >
firm.estate_thresholds.single_hard``.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any

from trust_generator.v3.config.firm import FirmConfig
from trust_generator.v3.extraction.trace import ExtractionTrace
from trust_generator.v3.schema import TrustData

__all__ = ("build_eval_context",)

COMPUTED_PROPERTIES: tuple[str, ...] = (
    "collected_total_value",
    "beneficiary_shares_total",
    "withdrawal_schedule_total",
    "disinherited_beneficiaries",
    "excluded_persons",
)


def _unwrap_enums(obj: Any) -> Any:
    """Recursively replace ``Enum`` instances with their ``.value``.

    rule-engine bypasses Python's ``__eq__`` when comparing context values
    against string literals; for ``str``-mixin Enum subclasses (e.g.
    ``TrustType(str, Enum)``) the raw instance compares correctly in Python
    but not through rule-engine, because rule-engine appears to call
    ``str()`` on the value — which returns the enum repr
    (``'TrustType.INDIVIDUAL'``), not the value (``'individual'``).

    Walks ``dict`` and ``list`` containers recursively. ``Decimal``,
    ``date``, ``UUID``, and other non-Enum scalars are returned untouched.
    """
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, dict):
        return {k: _unwrap_enums(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_unwrap_enums(v) for v in obj]
    return obj


def build_eval_context(
    trust: TrustData,
    config: FirmConfig,
    ref_date: date,
    *,
    extraction: ExtractionTrace | None = None,
) -> dict[str, Any]:
    """Compose the eval context for rule expression evaluation.

    Args:
        trust: post-fill canonical TrustData (consumed, not mutated).
        config: FirmConfig (consumed, not mutated).
        ref_date: explicit reference date; resolution chain handled by diagnose().
        extraction: optional ExtractionTrace; when supplied, exposed under
            the ``extraction`` namespace so YAML rules can reference
            ``extraction.fields`` (with a ``extraction != null and ...``
            guard).

    Returns:
        ``{"trust": dict, "firm": dict, "now": date}``, plus
        ``"extraction": dict`` when ``extraction`` is supplied.
    """
    trust_dict: dict[str, Any] = trust.model_dump(mode="python")

    for prop in COMPUTED_PROPERTIES:
        value = getattr(trust, prop)
        if isinstance(value, list):
            trust_dict[prop] = [
                v.model_dump(mode="python") if hasattr(v, "model_dump") else v
                for v in value
            ]
        else:
            trust_dict[prop] = value

    trust_dict["minor_beneficiaries"] = [
        b.model_dump(mode="python") for b in trust.minor_beneficiaries(ref_date)
    ]

    ctx: dict[str, Any] = {
        "trust": _unwrap_enums(trust_dict),
        "firm": _unwrap_enums(config.model_dump(mode="python")),
        "now": ref_date,
    }
    if extraction is not None:
        ctx["extraction"] = _unwrap_enums(extraction.model_dump(mode="python"))
    return ctx
