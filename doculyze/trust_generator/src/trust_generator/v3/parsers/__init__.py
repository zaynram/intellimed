"""v3 parser package — public API surface (§5.2).

All four entry points are available directly from this package:

    parse_json(filepath)                          → TrustData
    parse_docx(filepath, seed_initialized)        → TrustData
    parse_pdf(filepath, seed_initialized)         → TrustData
    parse_file(filepath, seed_initialized=None)   → TrustData  # dispatches by extension
"""

from trust_generator.v3.parsers.docx_parser import parse_docx
from trust_generator.v3.parsers.json_parser import parse_json
from trust_generator.v3.parsers.pdf_parser import parse_pdf
from trust_generator.v3.parsers.registry import parse_file

__all__ = [
    "parse_docx",
    "parse_file",
    "parse_json",
    "parse_pdf",
]
