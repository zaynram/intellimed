"""Tests for trust_generator.v3.parsers.coercion.

Four pure helpers, each tested via pytest.parametrize batches covering positive
formats from the v2 corpus plus negative (unparseable) inputs that exercise the
soft-fail surface (return-default + log.warning). Regression guards pin:
  - §5.4.2 share-percent vs. asset-value semantics (NOT enforced in _to_decimal
    itself — the row-drop is a parser-level decision; this batch documents the
    contract by asserting _to_decimal returns None on soft-fail so a real zero
    is distinguishable from a parse failure).
  - §5.4.4 placeholder-prefix stripping for PersonReference cells.
  - §5.4.4 one-token-name entity-reference reconstruction.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from trust_generator.v3.parsers.coercion import (
    _to_address,
    _to_date,
    _to_decimal,
    _to_person_reference,
)
from trust_generator.v3.schema import Address, PersonReference

# ---------------------------------------------------------------------------
# _to_date — §5.4.1
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("01/15/2000", date(2000, 1, 15)),
        ("1/15/2000", date(2000, 1, 15)),
        ("2000-01-15", date(2000, 1, 15)),
        ("September 17, 1980", date(1980, 9, 17)),
        ("Sep 17, 1980", date(1980, 9, 17)),
        ("not a date", None),
        ("", None),
        ("   ", None),
    ],
    ids=[
        "mm_dd_yyyy_zero_padded",
        "m_d_yyyy_unpadded",
        "iso_yyyy_mm_dd",
        "long_form_full_month",
        "long_form_abbreviated_month",
        "unparseable_returns_none",
        "empty_returns_none",
        "whitespace_returns_none",
    ],
)
def test_to_date_positive_and_negative(text, expected):
    assert _to_date(text) == expected


def test_to_date_unparseable_emits_warning(caplog):
    """Soft-fail surface: unparseable date emits log.warning (spec §5.5)."""
    with caplog.at_level(logging.WARNING, logger="trust_generator.v3.parsers.coercion"):
        result = _to_date("not a date")
    assert result is None
    assert any("could not parse date" in rec.message for rec in caplog.records)


# ---------------------------------------------------------------------------
# _to_decimal — §5.4.2
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("$500,000", Decimal(500000)),
        ("500,000", Decimal(500000)),
        ("$500000.50", Decimal("500000.50")),
        ("500000", Decimal(500000)),
        ("50%", Decimal(50)),
        ("50.5%", Decimal("50.5")),
        ("  $1,234.56  ", Decimal("1234.56")),
        ("-$50.00", Decimal("-50.00")),
        ("a lot", None),
        ("", None),
    ],
    ids=[
        "dollar_thousands_separator",
        "thousands_separator_no_dollar",
        "dollar_with_cents",
        "bare_integer",
        "percent_integer",
        "percent_fractional",
        "whitespace_stripped",
        "dollar_prefixed_negative",
        "unparseable_returns_none",
        "empty_returns_none",
    ],
)
def test_to_decimal_positive_and_negative(text, expected):
    assert _to_decimal(text) == expected


def test_to_decimal_returns_none_on_unparseable():
    """Regression guard for §5.4.2 contract: helper returns None on soft-fail.

    The parser-level row-drop on share-percent failure (per §5.4.2) is the docx/pdf
    sibling's responsibility — NOT this helper's. This helper's soft-fail return is
    None for all unparseable inputs (not Decimal(0)), so a genuine zero value is
    distinguishable from a parse failure; the calling parser decides how to treat
    None based on the target field's own default.
    """
    for unparseable in ("a lot", "", "   ", "not a number"):
        assert _to_decimal(unparseable) is None


def test_to_decimal_unparseable_emits_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="trust_generator.v3.parsers.coercion"):
        _to_decimal("a lot")
    assert any("could not parse decimal" in rec.message for rec in caplog.records)


# ---------------------------------------------------------------------------
# _to_address — §5.4.3
# ---------------------------------------------------------------------------

def test_to_address_three_parts():
    """Free text with three comma-separated parts: street, city, state+zip.

    With no 4th part the `country` kwarg is omitted, so the schema default
    (`Address.country == "US"`) is preserved rather than clobbered with "".
    """
    result = _to_address("123 Main St, Springfield, IL 62701")
    assert isinstance(result, Address)
    assert result.street == "123 Main St"
    assert result.city == "Springfield"
    assert result.state == "IL"
    assert result.zip_code == "62701"
    assert result.country == "US"


def test_to_address_four_parts_with_country():
    """Free text with four parts: street, city, state+zip, country."""
    result = _to_address("123 Main St, Springfield, IL 62701, US")
    assert result.street == "123 Main St"
    assert result.city == "Springfield"
    assert result.state == "IL"
    assert result.zip_code == "62701"
    assert result.country == "US"


def test_to_address_unparseable_single_string():
    """Zero / one comma: full string lands in street, other fields empty."""
    result = _to_address("just a single string with no commas")
    assert result.street == "just a single string with no commas"
    assert result.city == ""
    assert result.state == ""
    assert result.zip_code == ""
    assert result.country == "US"


def test_to_address_four_parts_emits_no_warning(caplog):
    """The 4-part shape (street, city, state-zip, country) is documented-valid.

    Regression pin for B3: only 4+ parts should warn — a clean 4-part input
    must NOT trip the mis-shape diagnostic.
    """
    with caplog.at_level(logging.WARNING, logger="trust_generator.v3.parsers.coercion"):
        _to_address("123 Main St, Springfield, IL 62701, US")
    assert caplog.records == []


def test_to_address_five_parts_emits_warning(caplog):
    """B3: more than 4 comma parts is an ambiguous mis-shape — surface a warning.

    A second street line ("Apt 4") pushes the part count past the documented
    maximum of 4, so the heuristic silently absorbs "Apt 4" as the city. The
    soft-fail return is unchanged, but the diagnostic makes the mis-shape
    visible. Warn fires on `len(parts) > 4`, not on the valid 4-part shape.
    """
    with caplog.at_level(logging.WARNING, logger="trust_generator.v3.parsers.coercion"):
        result = _to_address("123 Main St, Apt 4, Springfield, IL 62704, US")
    assert any(
        "comma-separated parts" in rec.message for rec in caplog.records
    )
    # Soft-fail return is unchanged: still an Address built from the first parts.
    assert isinstance(result, Address)
    assert result.street == "123 Main St"


def test_to_address_unparseable_emits_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="trust_generator.v3.parsers.coercion"):
        _to_address("just a single string")
    assert any("could not parse address" in rec.message for rec in caplog.records)


def test_to_address_empty_string():
    """Empty input yields a fully-defaulted Address (no warning)."""
    result = _to_address("")
    assert result.street == ""
    assert result.city == ""
    assert result.state == ""
    assert result.zip_code == ""
    assert result.country == "US"


def test_to_address_never_geocodes():
    """latitude / longitude are NEVER populated by the coercion helper (spec §5.4.3)."""
    result = _to_address("123 Main St, Springfield, IL 62701")
    assert result.latitude is None
    assert result.longitude is None


# ---------------------------------------------------------------------------
# _to_person_reference — §5.4.4
# ---------------------------------------------------------------------------

def test_to_person_reference_two_token_name():
    """Standard two-token name → PersonReference with full_legal_name set."""
    result = _to_person_reference("John Andrew Doe")
    assert isinstance(result, PersonReference)
    assert result.full_legal_name == "John Andrew Doe"
    assert result.is_entity is False


def test_to_person_reference_one_token_name_traps_and_reconstructs_as_entity():
    """One-token name fails the two-token validator → re-constructed as entity (§5.4.4).

    Note: the §5.4.4 trap fires on inputs that fail the `len(v.split()) < 2`
    validator — i.e., true one-token strings. Multi-token entity names like
    `"ABC Corporation"` or `"First National Bank"` are detected separately by
    the §5.4.9 CorporateTrustee suffix heuristic, which lives inside
    `_apply_post_merge_resolution` (docx-6, not this helper).
    """
    result = _to_person_reference("AcmeCorp")
    assert result.is_entity is True
    assert result.entity_name == "AcmeCorp"
    assert result.full_legal_name == ""


def test_to_person_reference_strips_placeholder_prefix():
    """v2 corpus pattern: '[Spouse name] Jane Doe' → coerces to 'Jane Doe' (§5.4.4)."""
    result = _to_person_reference("[Spouse's full legal name] Jane Doe")
    assert result.full_legal_name == "Jane Doe"
    assert result.is_entity is False


def test_to_person_reference_placeholder_prefix_with_one_token_remaining_becomes_entity():
    """Placeholder strip leaves one token → entity re-construction fires."""
    result = _to_person_reference("[Entity name] AcmeCorp")
    assert result.is_entity is True
    assert result.entity_name == "AcmeCorp"


def test_to_person_reference_empty_string():
    """Empty input yields an entity-shaped reference with empty entity_name."""
    result = _to_person_reference("")
    # Either interpretation is acceptable per the spec; pin observed behavior:
    # an empty string is one "token" (or zero), so the entity branch fires.
    assert result.full_legal_name == ""
    # entity_name may be "" (empty) — this is the natural outcome of the trap path.
    assert result.is_entity is True


def test_to_person_reference_one_token_name_emits_warning(caplog):
    """H2 soft-fail surface: the §5.4.4 entity-reconstruction trap emits a warning.

    Previously the lone silent soft-fail among the four helpers; it must now warn
    consistently with `_to_date` / `_to_decimal` / `_to_address` (spec §5.5).
    """
    with caplog.at_level(logging.WARNING, logger="trust_generator.v3.parsers.coercion"):
        result = _to_person_reference("AcmeCorp")
    assert result.is_entity is True
    assert any("one-token name" in rec.message for rec in caplog.records)


def test_to_person_reference_reraises_unrelated_validation_error(monkeypatch):
    """H2 narrowing fitness guard: a non-`full_legal_name` ValidationError propagates.

    The trap must catch ONLY the schema's two-token-name validator failure. Any
    other PersonReference validation failure is an unrelated schema break and
    must surface, not be silently reinterpreted as an entity. Monkeypatching the
    `PersonReference` symbol the helper imports with a stricter model proves the
    `except ValidationError` is narrowed, not broad.
    """
    from pydantic import BaseModel, field_validator

    from trust_generator.v3.parsers import coercion as coercion_mod

    class _StrictPersonReference(BaseModel):
        """Stand-in whose validator fails on a DIFFERENT field than full_legal_name."""

        full_legal_name: str = ""
        entity_name: str = ""
        is_entity: bool = False

        @field_validator("full_legal_name")
        @classmethod
        def _reject_all(cls, v: str) -> str:
            if v:
                msg = "entity_name must be supplied for this reference"
                raise ValueError(msg)
            return v

    monkeypatch.setattr(coercion_mod, "PersonReference", _StrictPersonReference)

    # The validator error here is NOT the two-token-name failure — it must
    # propagate rather than being swallowed into an entity reconstruction.
    with pytest.raises(ValidationError):
        _to_person_reference("John Doe")
