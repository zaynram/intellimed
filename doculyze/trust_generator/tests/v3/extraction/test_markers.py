"""Cycle 9a-1 tests — marker classes and INCOMPLETE sentinel."""

from __future__ import annotations


def test_incomplete_until_validated_importable() -> None:
    """``IncompleteUntilValidated`` is importable from the markers module."""
    from trust_generator.v3.extraction.markers import IncompleteUntilValidated

    assert IncompleteUntilValidated.__name__ == "IncompleteUntilValidated"


def test_incomplete_until_validated_has_contract_docstring() -> None:
    """``IncompleteUntilValidated`` carries a non-empty docstring describing its contract."""
    from trust_generator.v3.extraction.markers import IncompleteUntilValidated

    assert IncompleteUntilValidated.__doc__ is not None
    assert IncompleteUntilValidated.__doc__.strip() != ""


def test_raw_self_report_importable() -> None:
    """``RawSelfReport`` is importable from the markers module."""
    from trust_generator.v3.extraction.markers import RawSelfReport

    assert RawSelfReport.__name__ == "RawSelfReport"


def test_raw_self_report_has_contract_docstring() -> None:
    """``RawSelfReport`` carries a non-empty docstring describing its contract."""
    from trust_generator.v3.extraction.markers import RawSelfReport

    assert RawSelfReport.__doc__ is not None
    assert RawSelfReport.__doc__.strip() != ""


def test_incomplete_sentinel_importable() -> None:
    """``INCOMPLETE`` is importable from the trace module."""
    from trust_generator.v3.extraction.trace import INCOMPLETE

    assert INCOMPLETE is not None


def test_incomplete_sentinel_identity_distinct() -> None:
    """``INCOMPLETE`` is identity-distinct from None, 0, '', and ()."""
    from trust_generator.v3.extraction.trace import INCOMPLETE

    assert INCOMPLETE is not None
    assert INCOMPLETE is not 0  # noqa: F632 — identity check is the assertion
    assert INCOMPLETE is not ""  # noqa: F632
    assert INCOMPLETE is not ()  # noqa: F632


def test_incomplete_sentinel_not_in_dunder_all() -> None:
    """``INCOMPLETE`` is not exported via ``trace.__all__`` (per spec §5.3 docstring).

    Consumers must import the sentinel explicitly to make the discipline visible.
    """
    from trust_generator.v3.extraction import trace

    assert "INCOMPLETE" not in getattr(trace, "__all__", ())
