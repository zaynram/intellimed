"""JSON parser for v3 TrustData.

Accepts only full v3 TrustData JSON documents — the canonical `model_dump_json()`
shape. Partial JSON, JSON patches, and hand-edited fragmentary JSON are explicitly
out of scope per spec §4 / §9 Q3. Pydantic's own validators handle every coercion
(dates, Decimals, enums, nested models), so the parser body is a thin wrapper.

Error contract:
- FileNotFoundError if the path does not exist (raised before any read).
- ValueError wrapping a Pydantic ValidationError on schema violation — matches
  v2's `ValueError("JSON validation failed for ...")` convention so existing CLI
  callers receive the same exception class.
- ValueError wrapping UnicodeDecodeError if the file is not valid UTF-8 —
  the raw UnicodeDecodeError is preserved as the cause. Consistent with
  pdf_parser's wrap pattern; registry.parse_file enumerates only
  FileNotFoundError and ValueError, so both sub-error paths must surface as
  ValueError for the registry contract to hold.
- OSError from the underlying file read surfaces uncaught (matches v2).
"""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from trust_generator.v3.schema import TrustData


def parse_json(filepath: Path) -> TrustData:
    """Parse a full v3 TrustData JSON dump; return a fresh validated instance.

    Args:
        filepath: Path to a `.json` file containing the canonical full v3
            TrustData dump (`TrustData.model_dump_json()` shape).

    Returns:
        A `TrustData` instance equal to the dumped original.

    Raises:
        FileNotFoundError: input file does not exist.
        ValueError: the JSON does not validate against the v3 TrustData schema.
            The wrapped Pydantic `ValidationError` is preserved as the cause.
        ValueError: the file is not valid UTF-8 — raised when
            ``read_text(encoding="utf-8")`` encounters bytes that cannot be
            decoded. The original ``UnicodeDecodeError`` is preserved as the
            cause. Consistent with ``pdf_parser``'s wrap pattern so that
            ``registry.parse_file`` callers see only ``ValueError`` for all
            file-content failures.
    """
    if not filepath.exists():
        raise FileNotFoundError(f"JSON file not found: {filepath}")
    try:
        text = filepath.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(
            f"could not decode JSON file {filepath} as UTF-8: {exc}"
        ) from exc
    try:
        return TrustData.model_validate_json(text)
    except ValidationError as exc:
        raise ValueError(f"JSON validation failed for {filepath}: {exc}") from exc
