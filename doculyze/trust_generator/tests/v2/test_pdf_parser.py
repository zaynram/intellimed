"""Tests for the PDF questionnaire parser."""

from __future__ import annotations

import pytest

try:
    import pypdf
    import reportlab

    HAS_PDF_DEPS = True
except ImportError:
    HAS_PDF_DEPS = False

pytestmark = pytest.mark.skipif(
    not HAS_PDF_DEPS, reason="pypdf/reportlab not installed"
)


def test_parse_empty_pdf(tmp_path):
    """Parse a freshly generated (empty) PDF questionnaire."""
    from trust_generator.v2.generators.pdf_questionnaire import generate_fillable_pdf
    from trust_generator.v2.parsers.pdf_parser import parse_pdf
    from trust_generator.v2.schema import TrustData

    pdf_path = tmp_path / "empty.pdf"
    generate_fillable_pdf(pdf_path)

    data = parse_pdf(pdf_path)
    assert isinstance(data, TrustData)
    # All fields should be empty/default
    assert data.party_a.full_legal_name == ""


def test_parse_filled_pdf_round_trip(tmp_path):
    """Fill a PDF form programmatically, then parse it back."""
    from pypdf import PdfReader, PdfWriter

    from trust_generator.v2.generators.pdf_questionnaire import generate_fillable_pdf
    from trust_generator.v2.parsers.pdf_parser import parse_pdf

    # Generate blank PDF
    pdf_path = tmp_path / "blank.pdf"
    generate_fillable_pdf(pdf_path)

    # Fill in some fields programmatically
    reader = PdfReader(str(pdf_path))
    writer = PdfWriter()
    writer.append(reader)

    # Pass None to update fields on all pages (husband is on page 0,
    # trust_id is on page 1)
    writer.update_page_form_field_values(
        None,
        {
            "party_a.full_legal_name": "John Smith",
            "trust_id.desired_trust_name": "The Smith Trust",
        },
    )

    filled_path = tmp_path / "filled.pdf"
    with open(filled_path, "wb") as f:
        writer.write(f)

    # Parse the filled PDF
    data = parse_pdf(filled_path)
    assert data.party_a.full_legal_name == "John Smith"
    assert data.trust_id.desired_trust_name == "The Smith Trust"


def test_registry_dispatches_pdf(tmp_path):
    """parse_file should accept .pdf extension."""
    from trust_generator.v2.generators.pdf_questionnaire import generate_fillable_pdf
    from trust_generator.v2.parsers import parse_file
    from trust_generator.v2.schema import TrustData

    pdf_path = tmp_path / "test.pdf"
    generate_fillable_pdf(pdf_path)

    data = parse_file(pdf_path)
    assert isinstance(data, TrustData)
