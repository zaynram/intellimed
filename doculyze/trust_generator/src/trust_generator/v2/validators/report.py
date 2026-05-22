"""Validation report data structures."""

from __future__ import annotations

import logging
from enum import Enum

from pydantic import BaseModel

log = logging.getLogger(__name__)


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class FieldStatus(str, Enum):
    PROVIDED = "provided"
    DEFAULTED = "defaulted"
    MISSING_REQUIRED = "missing_required"
    MISSING_OPTIONAL = "missing_optional"


class FieldEntry(BaseModel):
    field_path: str
    label: str
    status: FieldStatus
    value: str = ""
    default_reason: str = ""


class Finding(BaseModel):
    message: str
    severity: Severity
    field_path: str = ""


class ValidationReport(BaseModel):
    fields: list[FieldEntry] = []
    findings: list[Finding] = []

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == Severity.ERROR]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == Severity.WARNING]

    @property
    def can_generate(self) -> bool:
        """True if there are no blocking errors."""
        return len(self.errors) == 0
