"""Diagnostics-engine exception types."""

from __future__ import annotations

__all__ = ("DiagnosticConfigError",)


class DiagnosticConfigError(Exception):
    """Raised when rule loading fails: malformed YAML, schema mismatch,
    namespace violation, code collision, or expression compilation error.
    The loader's only failure mode; runtime evaluation errors yield
    meta-diagnostics rather than exceptions.
    """
