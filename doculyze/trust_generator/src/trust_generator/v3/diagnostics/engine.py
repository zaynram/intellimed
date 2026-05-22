"""diagnose() entry point — pure coordinator over the diagnostics subsystem.

Per spec §5.1: builds eval context, loads + caches rules, evaluates each,
returns the diagnostic list. Trace-driven Diagnostics (from
``synthesize_extraction_diagnostics``) precede rule-driven Diagnostics
in the returned list per spec §5.8 merge order.
"""

from __future__ import annotations

from datetime import date, datetime

from trust_generator.v3.config.firm import FirmConfig
from trust_generator.v3.diagnostics.eval_context import build_eval_context
from trust_generator.v3.diagnostics.loader import load_rules
from trust_generator.v3.extraction.synthesis import synthesize_extraction_diagnostics
from trust_generator.v3.extraction.trace import ExtractionTrace
from trust_generator.v3.schema import Diagnostic, TrustData

__all__ = ("diagnose",)


def diagnose(
    trust: TrustData,
    config: FirmConfig,
    *,
    ref_date: date | None = None,
    extraction: ExtractionTrace | None = None,
) -> list[Diagnostic]:
    """Compute diagnostics for a TrustData against a FirmConfig.

    Args:
        trust: post-fill canonical TrustData (consumed, not mutated).
        config: FirmConfig (consumed, not mutated).
        ref_date: explicit reference date for time-dependent rule context;
            defaults via chain ``trust.trust_id.execution_date -> datetime.now().astimezone().date()``.
        extraction: optional ExtractionTrace produced by an
            ``ExtractionProtocol`` backend; when supplied, trace-driven
            Diagnostics (illegible/low-confidence/no-normalized-value)
            precede rule-driven Diagnostics in the returned list.

    Returns:
        List of Diagnostic instances. Order is
        (trace-driven, builtin_load_order, custom_load_order). Never
        raises during evaluation; runtime failures yield meta-diagnostics
        in-stream.
    """
    resolved_ref_date = (
        ref_date or trust.trust_id.execution_date or datetime.now().astimezone().date()
    )
    ctx = build_eval_context(trust, config, resolved_ref_date, extraction=extraction)
    rules = load_rules(config)
    diagnostics: list[Diagnostic] = synthesize_extraction_diagnostics(trust, extraction)
    for rule in rules:
        result = rule.evaluate(ctx)
        if result is not None:
            diagnostics.append(result)
    return diagnostics
