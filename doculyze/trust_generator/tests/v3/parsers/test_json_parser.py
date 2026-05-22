"""Tests for trust_generator.v3.parsers.json_parser.

Round-trip + error surfaces. JSON parsing is symmetric with v3 schema validation;
Pydantic's validators do all the coercion, so the parser body is a thin wrapper
that adapts (FileNotFoundError, ValidationError) to the v2-compatible exception
contract (ValueError on schema violation).
"""

from __future__ import annotations

import pytest


def test_json_round_trip(tmp_path):
    """A TrustData dumped to JSON parses back to an equal TrustData."""
    from trust_generator.v3.parsers import parse_json
    from trust_generator.v3.schema import (
        GrantorInfo,
        TrustData,
        TrustIdentity,
        TrustType,
    )

    original = TrustData(
        trust_id=TrustIdentity(
            trust_type=TrustType.JOINT,
            desired_trust_name="Test Family Trust",
        ),
        grantor=GrantorInfo(full_legal_name="Test Grantor"),
    )
    json_file = tmp_path / "intake.json"
    json_file.write_text(original.model_dump_json(), encoding="utf-8")

    restored = parse_json(json_file)
    assert restored == original


def test_json_parser_raises_for_missing_file(tmp_path):
    """parse_json raises FileNotFoundError for a non-existent path."""
    from trust_generator.v3.parsers import parse_json

    missing = tmp_path / "does_not_exist.json"
    with pytest.raises(FileNotFoundError):
        parse_json(missing)


def test_json_parser_raises_for_invalid_json(tmp_path):
    """parse_json raises ValueError for malformed JSON syntax.

    Pydantic's model_validate_json wraps a JSON decode error in a
    ValidationError, which parse_json re-wraps as ValueError. The
    point of this test is the outer exception class, not the cause chain.
    """
    from trust_generator.v3.parsers import parse_json

    broken = tmp_path / "broken.json"
    broken.write_text("{this is not valid json", encoding="utf-8")
    with pytest.raises(ValueError):
        parse_json(broken)


def test_json_parser_raises_value_error_for_non_utf8_file(tmp_path):
    """parse_json raises ValueError (not bare UnicodeDecodeError) for non-UTF-8 input.

    read_text(encoding='utf-8') on a file with invalid UTF-8 bytes raises
    UnicodeDecodeError (a ValueError subclass). The parser must wrap it so
    callers receive ValueError — consistent with the module error contract and
    the registry.parse_file enumerate-only contract (FileNotFoundError |
    ValueError). Pins: (1) outer type is exactly ValueError, not a subclass;
    (2) cause chain preserves the original UnicodeDecodeError.
    """
    from trust_generator.v3.parsers import parse_json

    non_utf8 = tmp_path / "non_utf8.json"
    # b'\xff\xfe' is a UTF-16 BOM — invalid as UTF-8.
    non_utf8.write_bytes(b"\xff\xfe{}")
    with pytest.raises(ValueError) as excinfo:
        parse_json(non_utf8)

    assert type(excinfo.value) is ValueError, (
        "parse_json must wrap UnicodeDecodeError as ValueError, "
        f"not raise it bare. Got: {type(excinfo.value)!r}"
    )
    assert isinstance(excinfo.value.__cause__, UnicodeDecodeError), (
        "cause chain must preserve the original UnicodeDecodeError"
    )


def test_json_parser_raises_for_schema_violation(tmp_path):
    """parse_json raises ValueError for JSON that parses but fails v3 schema validation.

    v3's typed schema (date / Decimal / enums) admits many schema-violation paths
    that v2's mostly-string schema did not — this test exercises one (a date field
    populated with a malformed string) and asserts the outer exception class is
    ValueError, matching the v2 CLI contract.
    """
    from trust_generator.v3.parsers import parse_json

    # Valid JSON structure; invalid value (date field receives non-date string).
    bad_schema = tmp_path / "bad_schema.json"
    bad_schema.write_text(
        '{"trust_id": {"trust_type": "JOINT", "trust_date": "not-a-date"}, '
        '"grantor": {"full_legal_name": "Test Grantor"}}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError) as excinfo:
        parse_json(bad_schema)

    # The wrapped Pydantic error message survives in the str() of the ValueError.
    # This pins the message-shape promise (callers do not parse the message, but
    # the user-facing CLI surfaces it in error logs).
    assert "JSON validation failed for" in str(excinfo.value)
