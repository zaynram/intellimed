"""Output generators — each consumes a TrustData instance to produce a document."""

from __future__ import annotations

from .printable_questionnaire import generate_printable_questionnaire
from .trust_document import generate_trust_document

__all__ = ["generate_printable_questionnaire", "generate_trust_document"]

try:
    from .pdf_questionnaire import generate_fillable_pdf  # noqa: F401

    __all__.append("generate_fillable_pdf")
except ImportError:  # reportlab not installed
    pass
