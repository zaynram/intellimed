"""
Parser registry — dispatch to the correct parser based on file extension.
"""

from __future__ import annotations

import logging
from pathlib import Path

from trust_generator.schema import TrustData

log = logging.getLogger(__name__)


def parse_file(filepath: str | Path) -> TrustData:
    """Detect the file format by extension and parse it into a TrustData.

    Supported formats:
    - ``.docx`` — Trust Intake Questionnaire (Word)
    - ``.json`` — JSON conforming to the TrustData schema
    - ``.pdf`` — Fillable PDF questionnaire

    Parameters
    ----------
    filepath:
        Path to the intake file.

    Returns
    -------
    TrustData

    Raises
    ------
    ValueError
        If the file extension is not supported.
    FileNotFoundError
        If the file does not exist.
    """
    filepath = Path(filepath)

    if not filepath.exists():
        raise FileNotFoundError(f"File not found: {filepath}")

    ext = filepath.suffix.lower()

    if ext == ".docx":
        log.info("Dispatching to docx parser for %s", filepath.name)
        from trust_generator.parsers.docx_parser import parse_docx

        return parse_docx(filepath)

    if ext == ".json":
        log.info("Dispatching to JSON parser for %s", filepath.name)
        from trust_generator.parsers.json_parser import parse_json

        return parse_json(filepath)

    if ext == ".pdf":
        log.info("Dispatching to PDF parser for %s", filepath.name)
        from trust_generator.parsers.pdf_parser import parse_pdf

        return parse_pdf(filepath)

    raise ValueError(
        f"Unsupported file format '{ext}' for {filepath.name}. "
        "Supported formats: .docx, .json, .pdf"
    )
