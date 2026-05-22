"""Cycle 9a-3 tests — extraction.paths.resolve."""

from __future__ import annotations

from trust_generator.v3.extraction.paths import resolve
from trust_generator.v3.schema import (
    Child,
    GrantorInfo,
    OfficeInfo,
    TrustData,
)

# --- Happy paths -------------------------------------------------------------


def test_resolve_top_level_attribute() -> None:
    """resolve handles a top-level attribute lookup."""
    trust = TrustData(grantor=GrantorInfo(full_legal_name="John Doe"))
    resolved, value = resolve(trust, "grantor")
    assert resolved is True
    assert value is trust.grantor


def test_resolve_nested_attribute() -> None:
    """resolve walks nested attribute chains."""
    trust = TrustData(office=OfficeInfo(file_number="2026-001"))
    resolved, value = resolve(trust, "office.file_number")
    assert resolved is True
    assert value == "2026-001"


def test_resolve_list_attribute_returns_list() -> None:
    """resolve returns the list itself when the path stops at a list-typed attribute."""
    trust = TrustData(children=[Child(full_legal_name="Jane Doe")])
    resolved, value = resolve(trust, "children")
    assert resolved is True
    assert isinstance(value, list)
    assert len(value) == 1


def test_resolve_bracket_index_into_list() -> None:
    """resolve walks ``children[0]`` to the indexed element."""
    trust = TrustData(
        children=[
            Child(full_legal_name="Jane Doe"),
            Child(full_legal_name="John Doe Jr"),
        ]
    )
    resolved, value = resolve(trust, "children[0]")
    assert resolved is True
    assert isinstance(value, Child)
    assert value.full_legal_name == "Jane Doe"


def test_resolve_bracket_index_then_attribute() -> None:
    """resolve walks ``children[0].full_legal_name`` end-to-end."""
    trust = TrustData(children=[Child(full_legal_name="Jane Doe")])
    resolved, value = resolve(trust, "children[0].full_legal_name")
    assert resolved is True
    assert value == "Jane Doe"


# --- Unresolvable paths (return (False, None)) ------------------------------


def test_resolve_index_out_of_range_returns_false() -> None:
    """resolve returns (False, None) when the bracket index is out of range."""
    trust = TrustData(children=[Child(full_legal_name="Jane Doe")])
    resolved, value = resolve(trust, "children[5].full_legal_name")
    assert resolved is False
    assert value is None


def test_resolve_unknown_attribute_returns_false() -> None:
    """resolve returns (False, None) when an attribute name does not exist."""
    trust = TrustData(children=[Child(full_legal_name="Jane Doe")])
    resolved, value = resolve(trust, "children[0].nonexistent_attr")
    assert resolved is False
    assert value is None


def test_resolve_unknown_top_level_attribute_returns_false() -> None:
    """resolve returns (False, None) when the top-level attribute is unknown."""
    trust = TrustData()
    resolved, value = resolve(trust, "no_such_section")
    assert resolved is False
    assert value is None


# --- Pathological inputs (return (False, None) rather than raising) ---------


def test_resolve_empty_string_returns_false() -> None:
    """resolve returns (False, None) on the empty string."""
    trust = TrustData()
    resolved, value = resolve(trust, "")
    assert resolved is False
    assert value is None


def test_resolve_trailing_dot_returns_false() -> None:
    """resolve returns (False, None) on a trailing dot."""
    trust = TrustData()
    resolved, value = resolve(trust, "grantor.")
    assert resolved is False
    assert value is None


def test_resolve_malformed_bracket_returns_false() -> None:
    """resolve returns (False, None) on a malformed bracket expression."""
    trust = TrustData()
    resolved, value = resolve(trust, "children[abc].full_legal_name")
    assert resolved is False
    assert value is None


def test_resolve_unbalanced_bracket_returns_false() -> None:
    """resolve returns (False, None) on an unbalanced bracket."""
    trust = TrustData()
    resolved, value = resolve(trust, "children[0")
    assert resolved is False
    assert value is None


def test_resolve_index_into_non_list_returns_false() -> None:
    """resolve returns (False, None) when bracket-indexing a non-list."""
    trust = TrustData()
    resolved, value = resolve(trust, "grantor[0]")
    assert resolved is False
    assert value is None
