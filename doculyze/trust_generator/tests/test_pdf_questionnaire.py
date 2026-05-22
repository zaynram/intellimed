"""Tests for the fillable PDF questionnaire generator."""

from __future__ import annotations

from pathlib import Path

import pytest

try:
    import reportlab  # noqa: F401
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

pytestmark = pytest.mark.skipif(not HAS_REPORTLAB, reason="reportlab not installed")


def test_field_map_covers_required_fields():
    from trust_generator.generators.pdf_questionnaire import FIELD_MAP

    required_paths = [
        "party_a.full_legal_name",
        "party_b.full_legal_name",
        "trust_id.desired_trust_name",
        "trust_id.date",
        "trust_id.state_of_governing_law",
        "trust_id.county_of_execution",
    ]
    field_paths = [entry["path"] for entry in FIELD_MAP]
    for path in required_paths:
        assert path in field_paths, f"Required field {path} missing from FIELD_MAP"


def test_field_map_has_no_duplicate_paths():
    from trust_generator.generators.pdf_questionnaire import FIELD_MAP

    paths = [entry["path"] for entry in FIELD_MAP]
    assert len(paths) == len(set(paths)), "Duplicate paths in FIELD_MAP"


def test_generate_fillable_pdf(tmp_path):
    from trust_generator.generators.pdf_questionnaire import generate_fillable_pdf

    path = tmp_path / "questionnaire.pdf"
    result = generate_fillable_pdf(path)
    assert Path(result).exists()
    assert Path(result).stat().st_size > 1000  # non-trivial PDF


def test_generated_pdf_has_form_fields(tmp_path):
    from pypdf import PdfReader
    from trust_generator.generators.pdf_questionnaire import FIELD_MAP, generate_fillable_pdf

    path = tmp_path / "questionnaire.pdf"
    generate_fillable_pdf(path)

    reader = PdfReader(str(path))
    fields = reader.get_fields() or {}
    field_names = set(fields.keys())

    # Joint PDF excludes Grantor (Individual Trust) section
    excluded = {"Grantor (Individual Trust)"}
    expected = [e for e in FIELD_MAP if e["section"] not in excluded]
    for entry in expected:
        assert entry["path"] in field_names, f"Field {entry['path']} missing from PDF"


def test_generated_pdf_contains_firm_branding(tmp_path):
    from pypdf import PdfReader
    from trust_generator.config import load_config
    from trust_generator.generators.pdf_questionnaire import generate_fillable_pdf

    path = tmp_path / "questionnaire.pdf"
    generate_fillable_pdf(path)

    reader = PdfReader(str(path))
    text = ""
    for page in reader.pages:
        text += page.extract_text() or ""

    cfg = load_config()
    assert cfg.firm.name in text
