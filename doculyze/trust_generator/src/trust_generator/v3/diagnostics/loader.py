"""Rule loader and DiagnosticRule model.

Per spec §6.4: load builtin (packaged) + custom (firm-side) rules,
enforce namespaces and code-collisions, dedupe custom against builtin,
compile every expression at load time.
"""

from __future__ import annotations

import importlib.resources
import logging
from pathlib import Path
from typing import Any

import rule_engine  # type: ignore[import-untyped]
import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, PrivateAttr

from trust_generator.v3.config.firm import FirmConfig
from trust_generator.v3.diagnostics.errors import DiagnosticConfigError
from trust_generator.v3.schema import (
    Diagnostic,
    DiagnosticContext,
    DiagnosticLevel,
    DiagnosticSource,
)

__all__ = ("DiagnosticRule", "load_rules")

_LOGGER = logging.getLogger(__name__)
_BUILTIN_RESOURCE = "trust_generator.v3.diagnostics.rules"
_BUILTIN_FILENAME = "builtin.yaml"


class DiagnosticRule(BaseModel):
    """A loaded, compiled rule. Evaluator method on the model per plan decision Q2."""

    model_config = ConfigDict(extra="forbid")

    code: str
    level: DiagnosticLevel
    source: DiagnosticSource
    context: DiagnosticContext = DiagnosticContext.BOTH
    message: str
    field_path: str | None = None
    expression: str
    enabled: bool = True

    _compiled: rule_engine.Rule | None = PrivateAttr(default=None)

    def evaluate(self, ctx: dict[str, Any]) -> Diagnostic | None:
        """Return a Diagnostic if the rule fires, else None.

        Runtime errors yield meta-diagnostics rather than raising, across
        four catch clauses (subclass-first per Python exception semantics):

        1. ``SymbolResolutionError`` (unresolved top-level symbol) →
           ``engine.symbol_unknown``.
        2. ``AttributeResolutionError`` (unresolved attribute) →
           ``engine.symbol_unknown``. Per spec §6.5, the meta code's
           intent is "attribute or top-level symbol could not be
           resolved" — both rule-engine subclasses map to it.
        3. ``EvaluationError`` (parent: arithmetic, lookup, type
           mismatches that rule-engine wraps) → ``engine.eval_error``.
        4. Bare ``TypeError`` (defensive workaround for rule-engine
           4.5.3's ``_assert_is_string`` truncation bug — see the inline
           comment at the catch site) → ``engine.eval_error``.

        Catch ordering matters: ``SymbolResolutionError`` and
        ``AttributeResolutionError`` are siblings under ``EvaluationError``,
        so listing the parent first would shadow both. Bare ``TypeError``
        sits outside the ``rule_engine.errors`` hierarchy and goes last.
        """
        if not self.enabled:
            return None
        if self._compiled is None:
            raise RuntimeError(
                f"DiagnosticRule {self.code!r} was not compiled by loader"
            )
        try:
            matched = self._compiled.matches(ctx)
        except rule_engine.errors.SymbolResolutionError as exc:
            return _meta_diagnostic(
                "engine.symbol_unknown", self.code, str(exc.symbol_name)
            )
        except rule_engine.errors.AttributeResolutionError as exc:
            return _meta_diagnostic(
                "engine.symbol_unknown", self.code, str(exc.attribute_name)
            )
        except rule_engine.errors.EvaluationError as exc:
            return _meta_diagnostic("engine.eval_error", self.code, str(exc))
        except TypeError as exc:
            # rule-engine bug: _assert_is_string uses map(isinstance, values, [str])
            # which truncates to the shorter iterable, so mixed-type additions
            # (e.g. str + Decimal) bypass the guard and raise a bare TypeError
            # from operator.add. Surface it as eval_error rather than propagating.
            return _meta_diagnostic("engine.eval_error", self.code, str(exc))
        if not matched:
            return None
        return Diagnostic(
            level=self.level,
            code=self.code,
            message=self.message,
            field_path=self.field_path,
            source=self.source,
            context=self.context,
        )


def load_rules(config: FirmConfig) -> list[DiagnosticRule]:
    """Load builtin and custom rules; enforce namespaces, collisions, dedupe; compile."""
    builtin = _load_builtin_rules()
    _enforce_namespace(builtin, allow_custom=False)
    _enforce_no_code_collisions(builtin, scope="builtin")
    _compile_expressions(builtin)

    custom = _load_custom_rules(config.diagnostics.rules_dir)
    _enforce_namespace(custom, allow_custom=True)
    _enforce_no_code_collisions(custom, scope="custom")
    _enforce_no_cross_code_collisions(builtin, custom)
    _compile_expressions(custom)
    custom = _dedupe_against(custom, builtin)

    return [r for r in (*builtin, *custom) if r.enabled]


def _load_builtin_rules() -> list[DiagnosticRule]:
    """Load the packaged builtin.yaml. Raises DiagnosticConfigError if absent or malformed."""
    try:
        resource = importlib.resources.files(_BUILTIN_RESOURCE) / _BUILTIN_FILENAME
        if not resource.is_file():
            raise DiagnosticConfigError(
                f"Packaged resource {_BUILTIN_FILENAME} not found in {_BUILTIN_RESOURCE}"
            )
        text = resource.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise DiagnosticConfigError(
            f"Packaged resource {_BUILTIN_FILENAME} missing: {exc}"
        ) from exc

    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise DiagnosticConfigError(
            f"Malformed YAML in packaged {_BUILTIN_FILENAME}: {exc}"
        ) from exc

    if parsed is None or parsed == []:
        return []
    if not isinstance(parsed, list):
        raise DiagnosticConfigError(
            f"Packaged {_BUILTIN_FILENAME} must be a YAML list, got {type(parsed).__name__}"
        )
    return [_validate_rule(item, source_label=_BUILTIN_FILENAME) for item in parsed]


def _load_custom_rules(rules_dir: Path) -> list[DiagnosticRule]:
    """Load all .yaml files under rules_dir as custom rules. Missing dir = empty list."""
    if not rules_dir.exists():
        return []
    rules: list[DiagnosticRule] = []
    for path in sorted(rules_dir.glob("*.yaml")):
        try:
            with path.open(encoding="utf-8") as fh:
                text = fh.read()
        except OSError as exc:
            raise DiagnosticConfigError(
                f"Failed to read custom rule file {path}: {exc}"
            ) from exc

        try:
            parsed = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise DiagnosticConfigError(
                f"Malformed YAML in {path}: {exc}"
            ) from exc

        if parsed is None:
            continue
        items = parsed if isinstance(parsed, list) else [parsed]
        for item in items:
            rules.append(_validate_rule(item, source_label=str(path)))
    return rules


def _validate_rule(item: Any, source_label: str) -> DiagnosticRule:
    try:
        return DiagnosticRule.model_validate(item)
    except Exception as exc:
        raise DiagnosticConfigError(
            f"Invalid rule entry in {source_label}: {exc}"
        ) from exc


def _enforce_namespace(rules: list[DiagnosticRule], *, allow_custom: bool) -> None:
    for rule in rules:
        is_custom = rule.code.startswith("custom.")
        if allow_custom and not is_custom:
            raise DiagnosticConfigError(
                f"Custom rule {rule.code!r} must use 'custom.' namespace prefix"
            )
        if not allow_custom and is_custom:
            raise DiagnosticConfigError(
                f"Builtin rule {rule.code!r} must not use 'custom.' namespace prefix"
            )


def _enforce_no_code_collisions(rules: list[DiagnosticRule], *, scope: str) -> None:
    seen: set[str] = set()
    for rule in rules:
        if rule.code in seen:
            raise DiagnosticConfigError(
                f"Duplicate rule code {rule.code!r} within {scope} rule set"
            )
        seen.add(rule.code)


def _enforce_no_cross_code_collisions(
    builtin: list[DiagnosticRule], custom: list[DiagnosticRule]
) -> None:
    builtin_codes = {r.code for r in builtin}
    for rule in custom:
        if rule.code in builtin_codes:
            raise DiagnosticConfigError(
                f"Rule code {rule.code!r} collides between builtin and custom sets"
            )


def _compile_expressions(rules: list[DiagnosticRule]) -> None:
    ctx = _build_rule_context()
    for rule in rules:
        try:
            compiled = rule_engine.Rule(rule.expression, context=ctx)
        except (
            rule_engine.errors.RuleSyntaxError,
            rule_engine.errors.RegexSyntaxError,
        ) as exc:
            # Note: AttributeResolutionError is NOT raised at compile time
            # because trust/firm are typed UNDEFINED (rule-engine defers
            # attribute resolution to evaluation). Catching it here would
            # be dead code. It IS caught at evaluation time (see
            # DiagnosticRule.evaluate, Cycle 4) where it surfaces as the
            # engine.symbol_unknown meta-diagnostic.
            raise DiagnosticConfigError(
                f"Expression compilation failed for rule {rule.code!r}: {exc}"
            ) from exc
        rule._compiled = compiled


def _build_rule_context() -> rule_engine.Context:
    type_resolver = rule_engine.type_resolver_from_dict(
        {
            "trust": rule_engine.DataType.UNDEFINED,
            "firm": rule_engine.DataType.UNDEFINED,
            "now": rule_engine.DataType.DATETIME,
            "extraction": rule_engine.DataType.UNDEFINED,
        }
    )
    return rule_engine.Context(type_resolver=type_resolver)


def _dedupe_key(rule: DiagnosticRule) -> tuple[str, DiagnosticLevel]:
    """Whitespace-stripped expression + level. Refactor target (§7 open seam: AST normalization)."""
    return ("".join(rule.expression.split()), rule.level)


def _dedupe_against(
    custom: list[DiagnosticRule], builtin: list[DiagnosticRule]
) -> list[DiagnosticRule]:
    builtin_keys = {_dedupe_key(r) for r in builtin}
    kept: list[DiagnosticRule] = []
    for rule in custom:
        if _dedupe_key(rule) in builtin_keys:
            _LOGGER.info(
                "Dropped custom rule %r: matches builtin (expression, level)", rule.code
            )
            continue
        kept.append(rule)
    return kept


def _meta_diagnostic(code: str, rule_code: str, detail: str) -> Diagnostic:
    """Construct a meta-diagnostic for runtime evaluation failures (Cycle 4)."""
    return Diagnostic(
        level=DiagnosticLevel.WARNING,
        code=code,
        message=f"Rule {rule_code} failed at engine evaluation: {detail}",
        field_path=None,
        source=DiagnosticSource.SCHEMA,
        context=DiagnosticContext.BOTH,
    )
