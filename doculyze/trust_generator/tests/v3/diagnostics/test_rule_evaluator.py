"""Cycle 4 — rule evaluator: match, no-match, disabled, meta-diagnostic surfacing."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import rule_engine  # type: ignore[import-untyped]

from trust_generator.v3.diagnostics.loader import (
    DiagnosticRule,
    _build_rule_context,
)
from trust_generator.v3.schema import (
    DiagnosticLevel,
    DiagnosticSource,
)


def _compile(rule: DiagnosticRule) -> DiagnosticRule:
    """Helper: compile a freshly-constructed rule (loader normally does this)."""
    rule._compiled = rule_engine.Rule(rule.expression, context=_build_rule_context())
    return rule


def test_evaluator_match():
    rule = _compile(
        DiagnosticRule.model_validate(
            {
                "code": "shares.sum_not_100",
                "level": "error",
                "source": "schema",
                "message": "shares must sum to 100",
                "field_path": "beneficiary_shares",
                "expression": "trust.beneficiary_shares_total != 100",
            }
        )
    )
    ctx = {"trust": {"beneficiary_shares_total": Decimal(99)}, "firm": {}, "now": date(2026, 4, 23)}
    result = rule.evaluate(ctx)
    assert result is not None
    assert result.code == "shares.sum_not_100"
    assert result.level == DiagnosticLevel.ERROR
    assert result.source == DiagnosticSource.SCHEMA
    assert result.field_path == "beneficiary_shares"


def test_evaluator_no_match():
    rule = _compile(
        DiagnosticRule.model_validate(
            {
                "code": "shares.sum_not_100",
                "level": "error",
                "source": "schema",
                "message": "shares must sum to 100",
                "expression": "trust.beneficiary_shares_total != 100",
            }
        )
    )
    ctx = {"trust": {"beneficiary_shares_total": Decimal(100)}, "firm": {}, "now": date(2026, 4, 23)}
    assert rule.evaluate(ctx) is None


def test_evaluator_disabled():
    rule = _compile(
        DiagnosticRule.model_validate(
            {
                "code": "shares.sum_not_100",
                "level": "error",
                "source": "schema",
                "message": "shares must sum to 100",
                "expression": "trust.beneficiary_shares_total != 100",
                "enabled": False,
            }
        )
    )
    ctx = {"trust": {"beneficiary_shares_total": Decimal(99)}, "firm": {}, "now": date(2026, 4, 23)}
    assert rule.evaluate(ctx) is None


def test_evaluator_symbol_unknown_meta():
    rule = _compile(
        DiagnosticRule.model_validate(
            {
                "code": "x.symbol",
                "level": "error",
                "source": "schema",
                "message": "x",
                "expression": "trust.nonexistent_field == 1",
            }
        )
    )
    ctx = {"trust": {}, "firm": {}, "now": date(2026, 4, 23)}
    result = rule.evaluate(ctx)
    assert result is not None
    assert result.code == "engine.symbol_unknown"
    assert result.level == DiagnosticLevel.WARNING
    assert "x.symbol" in result.message
    assert "nonexistent_field" in result.message


def test_evaluator_eval_error_meta():
    # Pins the 4th `except TypeError` clause: rule-engine 4.5.3's
    # `_assert_is_string` truncation bug lets `str + Decimal` raise a bare
    # `builtins.TypeError` from `operator.add` rather than a wrapped
    # `EvaluationError`. The test name is preserved per Cycle 4 plan
    # template; the parent-`EvaluationError` arm is pinned separately by
    # `test_evaluator_evaluation_error_branch` below.
    rule = _compile(
        DiagnosticRule.model_validate(
            {
                "code": "x.evalerr",
                "level": "error",
                "source": "schema",
                "message": "x",
                "expression": "trust.name + 1",
            }
        )
    )
    ctx = {"trust": {"name": "alice"}, "firm": {}, "now": date(2026, 4, 23)}
    result = rule.evaluate(ctx)
    assert result is not None
    assert result.code == "engine.eval_error"
    assert result.level == DiagnosticLevel.WARNING
    assert "x.evalerr" in result.message


def test_evaluator_evaluation_error_branch():
    # Pins the 3rd `except rule_engine.errors.EvaluationError` parent
    # clause. Division by zero is raised by rule-engine as a bare
    # `EvaluationError` ("arithmetic error: division by zero") — distinct
    # from the `TypeError` workaround path in the test above.
    rule = _compile(
        DiagnosticRule.model_validate(
            {
                "code": "x.divzero",
                "level": "error",
                "source": "schema",
                "message": "x",
                "expression": "trust.x / trust.y == 1",
            }
        )
    )
    ctx = {"trust": {"x": Decimal(5), "y": Decimal(0)}, "firm": {}, "now": date(2026, 4, 23)}
    result = rule.evaluate(ctx)
    assert result is not None
    assert result.code == "engine.eval_error"
    assert result.level == DiagnosticLevel.WARNING
    assert "x.divzero" in result.message


def test_evaluator_no_recompile_between_calls():
    """Compiled-rule identity: evaluator does not mutate _compiled."""
    rule = _compile(
        DiagnosticRule.model_validate(
            {
                "code": "x.identity",
                "level": "error",
                "source": "schema",
                "message": "x",
                "expression": "trust.beneficiary_shares_total != 100",
            }
        )
    )
    ctx = {"trust": {"beneficiary_shares_total": Decimal(99)}, "firm": {}, "now": date(2026, 4, 23)}
    initial_compiled = rule._compiled
    rule.evaluate(ctx)
    rule.evaluate(ctx)
    assert rule._compiled is initial_compiled
