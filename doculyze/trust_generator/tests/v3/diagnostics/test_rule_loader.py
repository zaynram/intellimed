"""Cycle 3 — rule loader: builtin + custom + namespace + collision + dedupe."""

from __future__ import annotations

import logging
from pathlib import Path
from textwrap import dedent

import pytest

from trust_generator.v3.diagnostics.errors import DiagnosticConfigError
from trust_generator.v3.diagnostics.loader import DiagnosticRule, load_rules


def _write_yaml(dir: Path, filename: str, content: str) -> Path:
    path = dir / filename
    path.write_text(dedent(content))
    return path


def test_builtin_loads_empty(firm_config_factory, monkeypatch):
    """Empty builtin set yields no rules (no error).

    SCOPE ADDITION: spec did not pin empty-builtin behavior. This plan
    chose 'empty file = empty list' to mirror the empty-rules_dir
    semantics in test 3 below.

    Monkeypatches `_load_builtin_rules` so the test asserts loader behavior
    on an empty builtin set regardless of `builtin.yaml`'s actual contents.
    """
    from trust_generator.v3.diagnostics import loader

    monkeypatch.setattr(loader, "_load_builtin_rules", list)
    config = firm_config_factory()
    rules = load_rules(config)
    assert rules == []


def test_custom_loads(firm_config_factory, tmp_rules_dir: Path):
    config = firm_config_factory()
    _write_yaml(
        tmp_rules_dir,
        "custom_test_rule.yaml",
        """
        - code: custom.test.foo
          level: warning
          source: schema
          context: both
          message: "Test rule"
          expression: "trust.beneficiary_shares_total != 100"
        """,
    )
    rules = load_rules(config)
    codes = [r.code for r in rules]
    assert "custom.test.foo" in codes


def test_empty_rules_dir(firm_config_factory, monkeypatch):
    """rules_dir with no files yields only builtins (stubbed empty here)."""
    from trust_generator.v3.diagnostics import loader

    monkeypatch.setattr(loader, "_load_builtin_rules", list)
    config = firm_config_factory()
    rules = load_rules(config)
    assert rules == []


def test_missing_rules_dir(firm_config_factory, monkeypatch, tmp_path: Path):
    """rules_dir that does not exist on disk yields only builtins, no error."""
    from trust_generator.v3.diagnostics import loader

    monkeypatch.setattr(loader, "_load_builtin_rules", list)
    config = firm_config_factory()
    config.diagnostics.rules_dir = tmp_path / "does_not_exist"
    rules = load_rules(config)
    assert rules == []


def test_builtin_namespace_enforcement(firm_config_factory, monkeypatch):
    """A builtin entry whose code starts with 'custom.' raises DiagnosticConfigError."""
    from trust_generator.v3.diagnostics import loader

    def fake_builtin():
        return [
            DiagnosticRule.model_validate(
                {
                    "code": "custom.illegal",
                    "level": "error",
                    "source": "schema",
                    "message": "illegal",
                    "expression": "trust.x == 1",
                }
            )
        ]

    monkeypatch.setattr(loader, "_load_builtin_rules", fake_builtin)
    with pytest.raises(DiagnosticConfigError, match="custom.illegal"):
        load_rules(firm_config_factory())


def test_custom_namespace_enforcement(firm_config_factory, tmp_rules_dir: Path):
    """A custom file with code lacking 'custom.' prefix raises DiagnosticConfigError."""
    _write_yaml(
        tmp_rules_dir,
        "bad.yaml",
        """
        - code: estate.illegal
          level: error
          source: schema
          message: "no prefix"
          expression: "trust.x == 1"
        """,
    )
    with pytest.raises(DiagnosticConfigError, match="estate.illegal"):
        load_rules(firm_config_factory())


def test_expression_dedupe_positive(firm_config_factory, tmp_rules_dir, caplog, monkeypatch):
    """A custom rule duplicating a builtin's (expression, level) is dropped, with INFO log."""
    from trust_generator.v3.diagnostics import loader

    def fake_builtin():
        return [
            DiagnosticRule.model_validate(
                {
                    "code": "shares.sum_not_100",
                    "level": "error",
                    "source": "schema",
                    "message": "builtin",
                    "expression": "trust.beneficiary_shares_total != 100",
                }
            )
        ]

    monkeypatch.setattr(loader, "_load_builtin_rules", fake_builtin)
    _write_yaml(
        tmp_rules_dir,
        "duplicate.yaml",
        """
        - code: custom.dup
          level: error
          source: schema
          message: "custom dup"
          expression: "trust.beneficiary_shares_total!=100"
        """,
    )
    caplog.set_level(logging.INFO)
    rules = load_rules(firm_config_factory())
    codes = [r.code for r in rules]
    assert "custom.dup" not in codes
    assert "shares.sum_not_100" in codes
    assert any("custom.dup" in record.message for record in caplog.records)


def test_expression_dedupe_negative_level_differs(
    firm_config_factory, tmp_rules_dir, monkeypatch
):
    """Same expression but different level: not deduped."""
    from trust_generator.v3.diagnostics import loader

    def fake_builtin():
        return [
            DiagnosticRule.model_validate(
                {
                    "code": "shares.sum_not_100",
                    "level": "error",
                    "source": "schema",
                    "message": "builtin",
                    "expression": "trust.beneficiary_shares_total != 100",
                }
            )
        ]

    monkeypatch.setattr(loader, "_load_builtin_rules", fake_builtin)
    _write_yaml(
        tmp_rules_dir,
        "warning.yaml",
        """
        - code: custom.warn
          level: warning
          source: schema
          message: "custom warning"
          expression: "trust.beneficiary_shares_total != 100"
        """,
    )
    rules = load_rules(firm_config_factory())
    codes = [r.code for r in rules]
    assert "custom.warn" in codes


def test_malformed_yaml(firm_config_factory, tmp_rules_dir):
    _write_yaml(tmp_rules_dir, "broken.yaml", "this: : is: : invalid")
    with pytest.raises(DiagnosticConfigError, match="broken.yaml"):
        load_rules(firm_config_factory())


def test_schema_mismatch_missing_code(firm_config_factory, tmp_rules_dir):
    _write_yaml(
        tmp_rules_dir,
        "no_code.yaml",
        """
        - level: error
          source: schema
          message: "missing code"
          expression: "trust.x == 1"
        """,
    )
    with pytest.raises(DiagnosticConfigError, match="code"):
        load_rules(firm_config_factory())


def test_single_mapping_form(firm_config_factory, tmp_rules_dir):
    _write_yaml(
        tmp_rules_dir,
        "single.yaml",
        """
        code: custom.single.foo
        level: info
        source: schema
        message: "single mapping form"
        expression: "trust.x == 1"
        """,
    )
    rules = load_rules(firm_config_factory())
    assert any(r.code == "custom.single.foo" for r in rules)


def test_duplicate_code_within_builtins(firm_config_factory, monkeypatch):
    from trust_generator.v3.diagnostics import loader

    def fake_builtin():
        rule = DiagnosticRule.model_validate(
            {
                "code": "shares.dup",
                "level": "error",
                "source": "schema",
                "message": "dup",
                "expression": "trust.x == 1",
            }
        )
        return [rule, rule.model_copy()]

    monkeypatch.setattr(loader, "_load_builtin_rules", fake_builtin)
    with pytest.raises(DiagnosticConfigError, match="shares.dup"):
        load_rules(firm_config_factory())


def test_duplicate_code_across_files(firm_config_factory, tmp_rules_dir):
    body = """
        - code: custom.foo.bar
          level: error
          source: schema
          message: "rule"
          expression: "trust.x == 1"
        """
    _write_yaml(tmp_rules_dir, "first.yaml", body)
    _write_yaml(tmp_rules_dir, "second.yaml", body)
    with pytest.raises(DiagnosticConfigError, match="custom.foo.bar"):
        load_rules(firm_config_factory())


def test_malformed_expression_syntax(firm_config_factory, tmp_rules_dir):
    _write_yaml(
        tmp_rules_dir,
        "bad_expr.yaml",
        """
        - code: custom.bad.syntax
          level: error
          source: schema
          message: "bad expression"
          expression: "trust.x ===== 1"
        """,
    )
    with pytest.raises(DiagnosticConfigError, match="custom.bad.syntax"):
        load_rules(firm_config_factory())


def test_malformed_expression_regex(firm_config_factory, tmp_rules_dir):
    _write_yaml(
        tmp_rules_dir,
        "bad_regex.yaml",
        r"""
        - code: custom.bad.regex
          level: error
          source: schema
          message: "bad regex"
          expression: 'trust.name =~ "[unclosed"'
        """,
    )
    with pytest.raises(DiagnosticConfigError, match="custom.bad.regex"):
        load_rules(firm_config_factory())


def test_missing_builtin_yaml(firm_config_factory, monkeypatch):
    """If packaged builtin.yaml is absent, loader raises with resource identification."""
    import importlib.resources

    from trust_generator.v3.diagnostics import loader

    def fake_files(_pkg: str):
        class _MissingTraversable:
            def __truediv__(self, _other):
                return self

            def is_file(self):
                return False

            def read_text(self, encoding="utf-8"):
                raise FileNotFoundError("builtin.yaml missing")

        return _MissingTraversable()

    monkeypatch.setattr(importlib.resources, "files", fake_files)
    with pytest.raises(DiagnosticConfigError, match="builtin.yaml"):
        load_rules(firm_config_factory())


def test_unreadable_custom_file(firm_config_factory, tmp_rules_dir, monkeypatch):
    _write_yaml(
        tmp_rules_dir,
        "unreadable.yaml",
        """
        - code: custom.x.y
          level: info
          source: schema
          message: "x"
          expression: "trust.x == 1"
        """,
    )
    real_open = Path.open

    def patched_open(self, *args, **kwargs):
        if self.name == "unreadable.yaml":
            raise OSError("permission denied")
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", patched_open)
    with pytest.raises(DiagnosticConfigError, match="unreadable.yaml"):
        load_rules(firm_config_factory())


def test_dedupe_key_whitespace_normalization():
    """Pin the dedupe-key contract: whitespace-stripped expression + level.

    Documented as the AST-normalization seam (§7 open seam): future versions
    may replace whitespace stripping with rule-engine AST traversal.
    """
    from trust_generator.v3.diagnostics.loader import _dedupe_key

    rule_a = DiagnosticRule.model_validate(
        {
            "code": "x.a",
            "level": "error",
            "source": "schema",
            "message": "a",
            "expression": "trust.x  ==  1",
        }
    )
    rule_b = DiagnosticRule.model_validate(
        {
            "code": "x.b",
            "level": "error",
            "source": "schema",
            "message": "b",
            "expression": "trust.x==1",
        }
    )
    rule_c = DiagnosticRule.model_validate(
        {
            "code": "x.c",
            "level": "warning",  # different level!
            "source": "schema",
            "message": "c",
            "expression": "trust.x==1",
        }
    )

    assert _dedupe_key(rule_a) == _dedupe_key(rule_b)
    assert _dedupe_key(rule_a) != _dedupe_key(rule_c)
