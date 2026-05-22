"""Audit log writer for force_generation overrides.

Per spec §5.5, §6.6: JSONL, monthly-rotated, per-user-subfolder path scheme.
The override flow (force_generation, validate_override_reason) lands in
Cycle 6 alongside this writer.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from trust_generator.v3.config.firm import FirmConfig
from trust_generator.v3.schema import Diagnostic, TrustData

__all__ = (
    "AuditLog",
    "AuditRecord",
    "force_generation",
    "validate_override_reason",
)


class AuditRecord(BaseModel):
    """One override event. JSONL-serialized via model_dump_json()."""

    model_config = ConfigDict(extra="forbid")

    timestamp: datetime
    user: str
    trust_ref: str
    overridden_codes: list[str]
    reason: str
    restriction_level: str


class AuditLog:
    """Append-only JSONL writer to a per-user audit directory."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def write(self, record: AuditRecord) -> Path:
        """Append the record as one JSONL line; return the file path.

        Raises ``OSError`` on filesystem failure (permission denied, disk full,
        path resolution errors); caller decides escalation policy.
        """
        # mkdir per-write per spec §6.6 Refactor: tolerates external dir
        # deletion between writes at the cost of one extra stat() per call.
        self.directory.mkdir(parents=True, exist_ok=True)
        filename = f"audit-{record.timestamp:%Y-%m}.jsonl"
        path = self.directory / filename
        line = record.model_dump_json() + "\n"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line)
        return path


def validate_override_reason(reason: str) -> None:
    """Reject reasons shorter than 10 non-whitespace characters.

    Exposed at module level so GUI flows can live-validate before submit
    per spec §5.6. The raised ``ValueError`` includes the actual stripped
    length so callers can render targeted feedback (e.g. "needs 3 more").
    """
    stripped_length = len(reason.strip())
    if stripped_length < 10:
        raise ValueError(
            "force_generation requires a reason of at least 10 non-whitespace "
            f"characters (received {stripped_length})"
        )


def force_generation(
    trust: TrustData,
    config: FirmConfig,
    diagnostics: list[Diagnostic],
    *,
    reason: str,
) -> AuditRecord:
    """Record an authorized override of blocking diagnostics.

    Per spec §5.6: pure with respect to its inputs (no mutation), writes
    one JSONL record to the configured audit directory, returns the
    written record.

    No ``user`` parameter is accepted by design. The override identity is
    sourced from ``config.user.upn`` — i.e. the trusted authenticated
    identity on the firm-config — never caller-supplied input. Accepting
    a caller ``user`` arg would let any caller forge audit attribution,
    so the API deliberately omits it.

    ``overridden_codes`` is the diagnostic codes in caller-supplied order
    with no de-duplication. If the caller passes diagnostics with
    duplicate codes, duplicates land in the audit record verbatim. Dedup
    (when desired) is the caller's concern; this writer treats the input
    list as authoritative.
    """
    validate_override_reason(reason)
    record = AuditRecord(
        timestamp=datetime.now().astimezone(),
        user=config.user.upn,
        trust_ref=(trust.office.file_number or "").strip() or "unidentified",
        overridden_codes=[d.code for d in diagnostics],
        reason=reason,
        restriction_level=config.diagnostics.default_restriction_level,
    )
    AuditLog(config.diagnostics.audit_log_dir).write(record)
    return record
