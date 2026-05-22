"""
Parse a JSON file into a TrustData instance.

The JSON must conform to the TrustData Pydantic schema.
"""

from __future__ import annotations

import logging
from pathlib import Path

from pydantic import ValidationError

from trust_generator.v2.schema import TrustData

log = logging.getLogger(__name__)


def parse_json(filepath: str | Path) -> TrustData:
    """Parse a JSON file and validate it against the TrustData schema.

    Parameters
    ----------
    filepath:
        Path to the ``.json`` file.

    Returns
    -------
    TrustData
        Validated trust data.

    Raises
    ------
    FileNotFoundError
        If the file does not exist.
    ValueError
        If the JSON is invalid or does not match the TrustData schema.
    """
    filepath = Path(filepath)
    log.info("Parsing JSON intake file: %s", filepath)

    if not filepath.exists():
        raise FileNotFoundError(f"JSON file not found: {filepath}")

    raw = filepath.read_text(encoding="utf-8")

    try:
        td = TrustData.model_validate_json(raw)
    except ValidationError as exc:
        msg = f"JSON validation failed for {filepath}:\n{exc}"
        log.error(msg)
        raise ValueError(msg) from exc

    log.info("Parsed JSON successfully: %s", filepath)
    return td
