"""Cycle 5 — audit log writer: JSONL, append, monthly rotation, path absoluteness."""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path

import freezegun

from trust_generator.v3.diagnostics.audit import AuditLog, AuditRecord


def _make_record(timestamp: datetime) -> AuditRecord:
    return AuditRecord(
        timestamp=timestamp,
        user="testuser",
        trust_ref="F-2026-0001",
        overridden_codes=["estate.crossed_cliff"],
        reason="Client confirmed estate value with attorney 2026-04-22.",
        restriction_level="error",
    )


@freezegun.freeze_time("2026-04-23T14:30:00")
def test_write_produces_file(tmp_audit_dir: Path):
    log = AuditLog(tmp_audit_dir)
    record = _make_record(datetime.now().astimezone())
    path = log.write(record)
    assert path.exists()
    assert path.name == "audit-2026-04.jsonl"


@freezegun.freeze_time("2026-04-23T14:30:00")
def test_jsonline_shape(tmp_audit_dir: Path):
    log = AuditLog(tmp_audit_dir)
    record = _make_record(datetime.now().astimezone())
    path = log.write(record)
    line = path.read_text(encoding="utf-8").strip()
    parsed = json.loads(line)
    assert set(parsed.keys()) == {
        "timestamp",
        "user",
        "trust_ref",
        "overridden_codes",
        "reason",
        "restriction_level",
    }
    assert parsed["user"] == "testuser"
    assert parsed["overridden_codes"] == ["estate.crossed_cliff"]
    assert parsed["restriction_level"] == "error"


@freezegun.freeze_time("2026-04-23T14:30:00")
def test_append(tmp_audit_dir: Path):
    log = AuditLog(tmp_audit_dir)
    record = _make_record(datetime.now().astimezone())
    log.write(record)
    log.write(record)
    path = tmp_audit_dir / "audit-2026-04.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2


def test_monthly_rotation(tmp_audit_dir: Path):
    log = AuditLog(tmp_audit_dir)
    with freezegun.freeze_time("2026-04-30T23:59:00"):
        log.write(_make_record(datetime.now().astimezone()))
    with freezegun.freeze_time("2026-05-01T00:00:00"):
        log.write(_make_record(datetime.now().astimezone()))
    assert (tmp_audit_dir / "audit-2026-04.jsonl").exists()
    assert (tmp_audit_dir / "audit-2026-05.jsonl").exists()


def test_path_is_absolute(tmp_audit_dir: Path):
    """Constructor accepts a Path and writes against it as-is."""
    log = AuditLog(tmp_audit_dir.resolve())
    assert log.directory.is_absolute()


def test_dir_creation_on_write(tmp_path: Path):
    """First write creates the dir if it doesn't exist (mkdir parents=True, exist_ok=True)."""
    nested = tmp_path / "users" / "testuser" / "logs"
    log = AuditLog(nested)
    record = AuditRecord(
        timestamp=datetime(2026, 4, 23, 14, 30).astimezone(),
        user="testuser",
        trust_ref="F-X",
        overridden_codes=[],
        reason="ten or more chars",
        restriction_level="error",
    )
    log.write(record)
    assert nested.exists()


@freezegun.freeze_time("2026-04-23T14:30:00")
def test_atomic_write_per_line(tmp_audit_dir: Path):
    """Concurrent writes from two AuditLog instances against the same dir must
    not interleave bytes within a single record (spec §6.6 test 6).

    POSIX guarantees ``O_APPEND`` writes ≤ ``PIPE_BUF`` (4096 bytes) are atomic.
    Each serialized record is ~150 bytes, well under that limit, so a single
    ``write()`` call from each thread lands as one contiguous chunk.
    """
    n_per_thread = 50
    log_a = AuditLog(tmp_audit_dir)
    log_b = AuditLog(tmp_audit_dir)
    timestamp = datetime.now().astimezone()

    def _write_many(log: AuditLog, user: str) -> None:
        for i in range(n_per_thread):
            log.write(
                AuditRecord(
                    timestamp=timestamp,
                    user=user,
                    trust_ref=f"F-2026-{i:04d}",
                    overridden_codes=["estate.crossed_cliff"],
                    reason="Client confirmed estate value with attorney 2026-04-22.",
                    restriction_level="error",
                )
            )

    thread_a = threading.Thread(target=_write_many, args=(log_a, "threadA"))
    thread_b = threading.Thread(target=_write_many, args=(log_b, "threadB"))
    thread_a.start()
    thread_b.start()
    thread_a.join()
    thread_b.join()

    path = tmp_audit_dir / "audit-2026-04.jsonl"
    raw = path.read_text(encoding="utf-8")
    # Trailing newline after last record means splitlines() yields exactly the
    # records, no spurious empty trailing element.
    lines = raw.splitlines()
    assert len(lines) == 2 * n_per_thread

    users_seen: set[str] = set()
    for line in lines:
        parsed = json.loads(line)  # raises if any line has interleaved bytes
        users_seen.add(parsed["user"])
    assert users_seen == {"threadA", "threadB"}
