"""Tests for trust_generator.v3.parsers.registry — §6.10 (parse_file dispatch).

Cycle 8 (Red → Green):  six tests covering extension dispatch, missing-seed
guard, unsupported-extension guard, and the M2 contract property (JSON parsing
is seed-agnostic).

Cycle 9 (Red → Green):  one additional test asserting the full §5.2 public
surface is importable from trust_generator.v3.parsers.

Chore #50 (2026-05-21-registry-dispatch-test-backfill):
  - Parametrized the missing-seed ValueError guard to cover .pdf in addition
    to .docx (both share the same gate in parse_file).
  - Added case-insensitivity tests for .JSON / .PDF / .DOCX: registry.parse_file
    normalises via Path.suffix.lower(), so dispatch is already case-insensitive;
    these tests pin that invariant.  No registry.py change was required.
"""

from __future__ import annotations

import pytest
from docx import Document  # type: ignore[import-untyped]
from pypdf import PdfWriter  # type: ignore[import-untyped]

from trust_generator.v3.schema import (
    MaritalStatus,
    QuestionnaireSeed,
    TrustType,
    promote_seed,
)

# ---------------------------------------------------------------------------
# Helpers — minimal fixture builders (used across multiple tests)
# ---------------------------------------------------------------------------

def _make_json_file(tmp_path):
    """Write a minimal full-TrustData JSON file and return its path."""
    from trust_generator.v3.schema import promote_seed

    seed = QuestionnaireSeed(
        trust_type=TrustType.JOINT,
        marital_status=MaritalStatus.MARRIED,
    )
    td = promote_seed(seed)
    json_path = tmp_path / "data.json"
    json_path.write_text(td.model_dump_json(), encoding="utf-8")
    return json_path


def _make_docx_file(tmp_path):
    """Write a minimal blank .docx and return its path."""
    docx_path = tmp_path / "data.docx"
    doc = Document()
    doc.add_paragraph("placeholder")
    doc.save(str(docx_path))
    return docx_path


def _make_pdf_file(tmp_path):
    """Write a minimal blank-page PDF and return its path."""
    pdf_path = tmp_path / "data.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with open(pdf_path, "wb") as f:
        writer.write(f)
    return pdf_path


def _make_seed_initialized():
    """Return a promoted TrustData from a minimal seed."""
    seed = QuestionnaireSeed(
        trust_type=TrustType.JOINT,
        marital_status=MaritalStatus.MARRIED,
    )
    return promote_seed(seed)


# ---------------------------------------------------------------------------
# Cycle 8 — §6.10 parse_file extension dispatch (6 tests)
# ---------------------------------------------------------------------------


def test_parse_file_dispatches_json(tmp_path):
    """parse_file('data.json') delegates to parse_json and returns a TrustData.

    Seed is omitted (None) — JSON parsing does not require it.
    """
    from trust_generator.v3.parsers.registry import parse_file

    json_path = _make_json_file(tmp_path)
    result = parse_file(json_path)
    assert result is not None


def test_parse_file_dispatches_docx(tmp_path):
    """parse_file('data.docx', seed_initialized=...) delegates to parse_docx."""
    from trust_generator.v3.parsers.registry import parse_file

    docx_path = _make_docx_file(tmp_path)
    seed_initialized = _make_seed_initialized()
    result = parse_file(docx_path, seed_initialized=seed_initialized)
    assert result is not None


def test_parse_file_dispatches_pdf(tmp_path):
    """parse_file('data.pdf', seed_initialized=...) delegates to parse_pdf."""
    from trust_generator.v3.parsers.registry import parse_file

    pdf_path = _make_pdf_file(tmp_path)
    seed_initialized = _make_seed_initialized()
    result = parse_file(pdf_path, seed_initialized=seed_initialized)
    assert result is not None


def test_parse_file_raises_for_unsupported_extension(tmp_path):
    """parse_file raises ValueError for an unrecognised extension."""
    from trust_generator.v3.parsers.registry import parse_file

    txt_path = tmp_path / "data.txt"
    txt_path.write_text("hello", encoding="utf-8")
    with pytest.raises(ValueError, match=r"Unsupported file extension"):
        parse_file(txt_path)


@pytest.mark.parametrize(
    "make_fixture,label",
    [
        (_make_docx_file, "docx"),
        (_make_pdf_file, "pdf"),
    ],
)
def test_parse_file_raises_when_seed_required(tmp_path, make_fixture, label):
    """Calling parse_file on a .docx or .pdf without seed_initialized raises ValueError.

    Both branches share the same gate in registry.parse_file; parametrize to
    pin that the .pdf branch fires the same guard as .docx.
    """
    from trust_generator.v3.parsers.registry import parse_file

    fixture_path = make_fixture(tmp_path)
    with pytest.raises(ValueError, match=r"seed_initialized"):
        parse_file(fixture_path)  # seed_initialized defaults to None


def test_parse_file_ignores_seed_for_json(tmp_path):
    """parse_file('foo.json', seed_initialized=non_None) equals parse_file('foo.json').

    M2 contract test (spec plan-review pass 1, finding M2; §6.10):
    the equality assertion verifies that seed_initialized is *ignored* —
    not merely accepted — when the extension is .json.  Both calls must
    produce an equal TrustData regardless of whether seed_initialized is
    None or a fully-promoted instance.
    """
    from trust_generator.v3.parsers.registry import parse_file

    json_path = _make_json_file(tmp_path)
    seed_td = _make_seed_initialized()

    result_with_seed = parse_file(json_path, seed_initialized=seed_td)
    result_without_seed = parse_file(json_path, seed_initialized=None)

    assert result_with_seed == result_without_seed


@pytest.mark.parametrize(
    "make_lowercase_fixture,uppercase_ext,needs_seed",
    [
        (_make_json_file, ".JSON", False),
        (_make_pdf_file, ".PDF", True),
        (_make_docx_file, ".DOCX", True),
    ],
)
def test_parse_file_dispatch_is_case_insensitive(
    tmp_path, make_lowercase_fixture, uppercase_ext, needs_seed
):
    """parse_file dispatches correctly for uppercase extensions (.JSON, .PDF, .DOCX).

    registry.parse_file normalises the suffix via Path.suffix.lower(), so
    .JSON / .PDF / .DOCX must dispatch identically to their lowercase forms.
    Pins the behaviour so an inadvertent removal of .lower() would Red these
    tests immediately.
    """
    from trust_generator.v3.parsers.registry import parse_file

    # Build the fixture with a lowercase extension, then rename to uppercase.
    lowercase_path = make_lowercase_fixture(tmp_path)
    uppercase_path = lowercase_path.with_suffix(uppercase_ext)
    lowercase_path.rename(uppercase_path)

    seed_initialized = _make_seed_initialized() if needs_seed else None
    result = parse_file(uppercase_path, seed_initialized=seed_initialized)
    assert result is not None


# ---------------------------------------------------------------------------
# Cycle 9 — §6.11 public API surface importability (1 test)
# ---------------------------------------------------------------------------


def test_public_api_importable():
    """All four names declared in §5.2 are importable from trust_generator.v3.parsers."""
    from trust_generator.v3.parsers import (
        parse_docx,
        parse_file,
        parse_json,
        parse_pdf,
    )

