"""Validation layer — inspects TrustData for completeness and consistency."""

from __future__ import annotations

from .report import FieldStatus, Severity, ValidationReport
from .validate import validate

__all__ = [
    "FieldStatus",
    "Severity",
    "ValidationReport",
    "validate",
]
