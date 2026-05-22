"""Diagnostics engine — see docs/superpowers/specs/2026-04-23-diagnostics-engine-design.md.

Public surface:
    diagnose(trust, config, *, ref_date=None) -> list[Diagnostic]
    force_generation(trust, config, diagnostics, *, reason) -> AuditRecord
    validate_override_reason(reason) -> None  (raises ValueError on short reason)
    AuditRecord — return type of force_generation; persisted as JSONL
    DiagnosticConfigError — raised on rule load failure
"""

from __future__ import annotations

from trust_generator.v3.diagnostics.audit import (
    AuditRecord,
    force_generation,
    validate_override_reason,
)
from trust_generator.v3.diagnostics.engine import diagnose
from trust_generator.v3.diagnostics.errors import DiagnosticConfigError

__all__ = [
    "AuditRecord",
    "DiagnosticConfigError",
    "diagnose",
    "force_generation",
    "validate_override_reason",
]
