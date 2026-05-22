"""Input parsers — each produces a TrustData instance from a different format."""

from __future__ import annotations

from .docx_parser import parse_docx
from .json_parser import parse_json
from .registry import parse_file


def parse_pdf(filepath):  # type: ignore[no-untyped-def]
    """Lazy import to avoid hard dependency on pypdf at module load time."""
    from .pdf_parser import parse_pdf as _parse_pdf

    return _parse_pdf(filepath)


__all__ = ["parse_docx", "parse_file", "parse_json", "parse_pdf"]
