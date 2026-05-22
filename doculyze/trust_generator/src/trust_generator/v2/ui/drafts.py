"""Draft save/load management for trust data.

Provides managed draft storage so paralegals can resume incomplete
trust data entry sessions without interacting with raw JSON files.
SSNs are excluded from saved drafts for security.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from trust_generator.v2.schema import TrustData, TrustType

log = logging.getLogger(__name__)

_SSN_EXCLUDE = {"party_a": {"ssn"}, "party_b": {"ssn"}, "grantor": {"ssn"}}


@dataclass
class DraftInfo:
    """Metadata for a saved draft displayed in the draft picker."""

    path: Path
    display_name: str
    modified_date: datetime


def drafts_dir() -> Path:
    """Return the drafts directory, creating it if needed."""
    import os
    import sys

    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", str(Path.home())))
    else:
        base = Path.home() / ".config"
    d = base / "trust-generator" / "drafts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def draft_display_name(data: TrustData) -> str:
    """Derive a human-readable name for the draft."""
    if data.trust_id.desired_trust_name:
        return data.trust_id.desired_trust_name
    name = ""
    if data.trust_type == TrustType.INDIVIDUAL and data.grantor.full_legal_name:
        name = data.grantor.full_legal_name.split()[-1]
    elif data.party_a.full_legal_name:
        name = data.party_a.full_legal_name.split()[-1]
    return f"{name} Trust" if name else "(Unnamed Trust)"


def _slug(name: str) -> str:
    """Convert a display name to a filesystem-safe slug."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "draft"


def save_draft(data: TrustData) -> Path:
    """Save TrustData as a managed draft (SSNs excluded)."""
    name = draft_display_name(data)
    slug = _slug(name)
    date_str = datetime.now().strftime("%Y-%m-%d")  # noqa: DTZ005
    path = drafts_dir() / f"{date_str}_{slug}.json"
    path.write_text(
        data.model_dump_json(indent=2, exclude=_SSN_EXCLUDE), encoding="utf-8"
    )
    log.info("Draft saved to %s", path)
    return path


def list_drafts() -> list[DraftInfo]:
    """List all saved drafts, most recent first."""
    results: list[DraftInfo] = []
    for p in drafts_dir().glob("*.json"):
        try:
            data = TrustData.model_validate_json(p.read_text(encoding="utf-8"))
            display = draft_display_name(data)
        except Exception:
            log.warning("Could not parse draft %s for display", p, exc_info=True)
            display = f"{p.stem} (unreadable)"
        mod_time = datetime.fromtimestamp(p.stat().st_mtime)  # noqa: DTZ006
        results.append(DraftInfo(path=p, display_name=display, modified_date=mod_time))
    results.sort(key=lambda d: d.modified_date, reverse=True)
    return results


def load_draft(path: Path) -> TrustData:
    """Load a draft JSON file into TrustData."""
    return TrustData.model_validate_json(path.read_text(encoding="utf-8"))


def delete_draft(path: Path) -> None:
    """Delete a draft file."""
    path.unlink(missing_ok=True)
    log.info("Draft deleted: %s", path)


def purge_old_drafts(max_age_days: int = 90) -> int:
    """Remove drafts older than max_age_days. Returns count of purged files."""
    cutoff = time.time() - (max_age_days * 86400)
    count = 0
    for p in drafts_dir().glob("*.json"):
        try:
            if p.stat().st_mtime < cutoff:
                p.unlink()
                count += 1
        except OSError:
            log.warning("Could not purge draft %s", p, exc_info=True)
    if count:
        log.info("Purged %d draft(s) older than %d days", count, max_age_days)
    return count
