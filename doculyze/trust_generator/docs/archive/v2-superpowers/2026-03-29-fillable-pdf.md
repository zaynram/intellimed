# Fillable PDF Questionnaire — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate a fillable PDF Trust Intake Questionnaire with form fields mapped to `TrustData` schema paths, and parse completed PDFs back into `TrustData` for the existing validate → generate pipeline.

**Architecture:** Two new modules: `generators/pdf_questionnaire.py` (generates fillable PDF using `reportlab`) and `parsers/pdf_parser.py` (extracts form field values using `pypdf`). The parser registry gains `.pdf` support. A new CLI subcommand `create-fillable-pdf` mirrors the existing `create-printable`.

**Tech Stack:** Python 3.12+, reportlab (PDF generation), pypdf (PDF parsing), Pydantic 2, pytest

---

## File Structure

| Action | File                                                  | Responsibility                              |
| ------ | ----------------------------------------------------- | ------------------------------------------- |
| Create | `src/trust_generator/generators/pdf_questionnaire.py` | Generate fillable PDF with AcroForm fields  |
| Create | `src/trust_generator/parsers/pdf_parser.py`           | Parse completed PDF form fields → TrustData |
| Modify | `src/trust_generator/parsers/registry.py`             | Register `.pdf` extension                   |
| Modify | `src/trust_generator/parsers/__init__.py`             | Export `parse_pdf`                          |
| Modify | `src/trust_generator/generators/__init__.py`          | Export `generate_fillable_pdf`              |
| Modify | `src/trust_generator/ui/cli.py`                       | Add `create-fillable-pdf` subcommand        |
| Modify | `pyproject.toml`                                      | Add reportlab and pypdf dependencies        |
| Modify | `pixi.toml`                                           | Add reportlab and pypdf to run-dependencies |
| Create | `tests/test_pdf_questionnaire.py`                     | Tests for PDF generation                    |
| Create | `tests/test_pdf_parser.py`                            | Tests for PDF parsing                       |
| Modify | `tests/test_integration.py`                           | End-to-end PDF pipeline test                |

---

### Task 1: Add reportlab and pypdf dependencies

**Files:**

- Modify: `pyproject.toml`
- Modify: `pixi.toml`

- [ ] **Step 1: Update pyproject.toml**

In `pyproject.toml`, add `reportlab` and `pypdf` to the dependencies list:

```toml
dependencies    = ["python-docx", "pydantic>=2", "reportlab", "pypdf>=4"]
```

- [ ] **Step 2: Update pixi.toml**

In `pixi.toml`, add to `[package.run-dependencies]`:

```toml
    [package.run-dependencies]
    pydantic    = ">=2"
    python-docx = "*"
    reportlab   = "*"
    pypdf       = ">=4"
```

- [ ] **Step 3: Install dependencies**

Run: `pip install reportlab pypdf` (or `pixi install` if available)
Expected: Both packages install successfully

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml pixi.toml
git commit -m "chore: add reportlab and pypdf dependencies for PDF questionnaire"
```

---

### Task 2: Define the field mapping between PDF form fields and TrustData

**Files:**

- Create: `src/trust_generator/generators/pdf_questionnaire.py` (partial — field map only)
- Create: `tests/test_pdf_questionnaire.py` (partial — field map test)

The field map is the contract between the PDF generator and the PDF parser. Each PDF form field name is a dotted schema path (e.g., `husband.full_legal_name`). This ensures the parser can trivially map fields back to `TrustData`.

- [ ] **Step 1: Write test for field map completeness**

Create `tests/test_pdf_questionnaire.py`:

```python
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
        "husband.full_legal_name",
        "wife.full_legal_name",
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
```

- [ ] **Step 2: Create pdf_questionnaire.py with field map**

Create `src/trust_generator/generators/pdf_questionnaire.py`:

```python
"""Generate a fillable PDF Trust Intake Questionnaire.

PDF form field names use dotted schema paths (e.g., 'husband.full_legal_name')
so the PDF parser can map values directly to TrustData fields.
"""

from __future__ import annotations

import logging
from pathlib import Path

from trust_generator.config import AppConfig, load_config

log = logging.getLogger(__name__)

# Each entry: {"path": dotted schema path, "label": human label, "section": grouping}
FIELD_MAP: list[dict[str, str]] = [
    # Office
    {"path": "office.file_number", "label": "File Number", "section": "Office Use"},
    {"path": "office.attorney", "label": "Attorney", "section": "Office Use"},
    {"path": "office.paralegal", "label": "Paralegal", "section": "Office Use"},
    {"path": "office.date_opened", "label": "Date Opened", "section": "Office Use"},
    # Husband
    {"path": "husband.full_legal_name", "label": "Full Legal Name", "section": "Husband Information"},
    {"path": "husband.date_of_birth", "label": "Date of Birth", "section": "Husband Information"},
    {"path": "husband.ssn", "label": "Social Security Number", "section": "Husband Information"},
    {"path": "husband.address", "label": "Address", "section": "Husband Information"},
    {"path": "husband.phone", "label": "Phone", "section": "Husband Information"},
    {"path": "husband.email", "label": "Email", "section": "Husband Information"},
    {"path": "husband.employer", "label": "Employer", "section": "Husband Information"},
    # Wife
    {"path": "wife.full_legal_name", "label": "Full Legal Name", "section": "Wife Information"},
    {"path": "wife.date_of_birth", "label": "Date of Birth", "section": "Wife Information"},
    {"path": "wife.ssn", "label": "Social Security Number", "section": "Wife Information"},
    {"path": "wife.address", "label": "Address", "section": "Wife Information"},
    {"path": "wife.phone", "label": "Phone", "section": "Wife Information"},
    {"path": "wife.email", "label": "Email", "section": "Wife Information"},
    {"path": "wife.employer", "label": "Employer", "section": "Wife Information"},
    {"path": "wife.maiden_name", "label": "Maiden Name", "section": "Wife Information"},
    # Marriage
    {"path": "marriage.date_of_marriage", "label": "Date of Marriage", "section": "Marriage Information"},
    {"path": "marriage.state_of_marriage", "label": "State of Marriage", "section": "Marriage Information"},
    {"path": "marriage.prenuptial_agreement", "label": "Prenuptial Agreement", "section": "Marriage Information"},
    {"path": "marriage.prenuptial_details", "label": "Prenuptial Details", "section": "Marriage Information"},
    # Trust ID
    {"path": "trust_id.desired_trust_name", "label": "Desired Trust Name", "section": "Trust Information"},
    {"path": "trust_id.date", "label": "Trust Date", "section": "Trust Information"},
    {"path": "trust_id.state_of_governing_law", "label": "State of Governing Law", "section": "Trust Information"},
    {"path": "trust_id.county_of_execution", "label": "County of Execution", "section": "Trust Information"},
    {"path": "trust_id.whose_ssn_for_tax_id", "label": "Whose SSN for Tax ID", "section": "Trust Information"},
    # Text blocks
    {"path": "text_blocks.statement_of_intent", "label": "Statement of Intent", "section": "Text Sections"},
    {"path": "text_blocks.personal_message", "label": "Personal Message", "section": "Text Sections"},
    {"path": "text_blocks.additional_notes", "label": "Additional Notes", "section": "Text Sections"},
]
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_pdf_questionnaire.py -v`
Expected: ALL PASS (or skip if reportlab not installed)

- [ ] **Step 4: Commit**

```bash
git add src/trust_generator/generators/pdf_questionnaire.py tests/test_pdf_questionnaire.py
git commit -m "feat: define PDF field map for fillable questionnaire"
```

---

### Task 3: Implement PDF generation with reportlab

**Files:**

- Modify: `src/trust_generator/generators/pdf_questionnaire.py`
- Modify: `tests/test_pdf_questionnaire.py`

- [ ] **Step 1: Write failing test for PDF generation**

Add to `tests/test_pdf_questionnaire.py`:

```python
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

    # All scalar FIELD_MAP paths should be present as PDF form fields
    for entry in FIELD_MAP:
        assert entry["path"] in field_names, f"Field {entry['path']} missing from PDF"


def test_generated_pdf_contains_firm_branding(tmp_path):
    from pypdf import PdfReader
    from trust_generator.generators.pdf_questionnaire import generate_fillable_pdf

    path = tmp_path / "questionnaire.pdf"
    generate_fillable_pdf(path)

    reader = PdfReader(str(path))
    text = ""
    for page in reader.pages:
        text += page.extract_text() or ""

    assert "Crosby and Crosby LLP" in text
```

- [ ] **Step 2: Implement generate_fillable_pdf**

Add to `src/trust_generator/generators/pdf_questionnaire.py`:

```python
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas as pdfcanvas


def generate_fillable_pdf(
    output_path: str | Path,
    config: AppConfig | None = None,
) -> str:
    """Generate a fillable PDF questionnaire with AcroForm fields.

    Returns the output path as a string.
    """
    cfg = config or load_config()
    out = str(Path(output_path))

    c = pdfcanvas.Canvas(out, pagesize=letter)
    width, height = letter

    # Page setup
    margin = inch
    usable_width = width - 2 * margin
    y = height - margin

    # Header / firm branding
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(width / 2, y, cfg.firm.name)
    y -= 18
    c.setFont("Helvetica", 10)
    c.drawCentredString(width / 2, y, cfg.firm.address_line1)
    y -= 14
    c.drawCentredString(width / 2, y, cfg.firm.address_line2)
    y -= 14
    c.drawCentredString(width / 2, y, cfg.firm.phone)
    y -= 24
    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(width / 2, y, "Trust Intake Questionnaire")
    y -= 30

    # Build form
    form = c.acroForm

    current_section = ""
    field_height = 18
    label_width = 180

    for entry in FIELD_MAP:
        # Section header
        if entry["section"] != current_section:
            current_section = entry["section"]
            y -= 10
            if y < margin + 40:
                c.showPage()
                y = height - margin
            c.setFont("Helvetica-Bold", 11)
            c.drawString(margin, y, current_section)
            y -= 20

        # Check for page break
        if y < margin + 30:
            c.showPage()
            y = height - margin

        # Label
        c.setFont("Helvetica", 9)
        c.drawString(margin, y + 3, entry["label"])

        # Text field
        field_x = margin + label_width
        field_width = usable_width - label_width
        form.textfield(
            name=entry["path"],
            x=field_x,
            y=y - 2,
            width=field_width,
            height=field_height,
            borderWidth=1,
            fontSize=9,
            fieldFlags="",
        )
        y -= field_height + 6

    c.save()
    log.info("Fillable PDF questionnaire written to %s", out)
    return out
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_pdf_questionnaire.py -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add src/trust_generator/generators/pdf_questionnaire.py tests/test_pdf_questionnaire.py
git commit -m "feat: implement fillable PDF questionnaire generation with reportlab"
```

---

### Task 4: Implement PDF parser

**Files:**

- Create: `src/trust_generator/parsers/pdf_parser.py`
- Create: `tests/test_pdf_parser.py`

- [ ] **Step 1: Write failing tests for PDF parsing**

Create `tests/test_pdf_parser.py`:

```python
"""Tests for the PDF questionnaire parser."""

from __future__ import annotations

from pathlib import Path

import pytest

try:
    import pypdf  # noqa: F401
    import reportlab  # noqa: F401
    HAS_PDF_DEPS = True
except ImportError:
    HAS_PDF_DEPS = False

pytestmark = pytest.mark.skipif(not HAS_PDF_DEPS, reason="pypdf/reportlab not installed")


def test_parse_empty_pdf(tmp_path):
    """Parse a freshly generated (empty) PDF questionnaire."""
    from trust_generator.generators.pdf_questionnaire import generate_fillable_pdf
    from trust_generator.parsers.pdf_parser import parse_pdf
    from trust_generator.schema import TrustData

    pdf_path = tmp_path / "empty.pdf"
    generate_fillable_pdf(pdf_path)

    data = parse_pdf(pdf_path)
    assert isinstance(data, TrustData)
    # All fields should be empty/default
    assert data.husband.full_legal_name == ""


def test_parse_filled_pdf_round_trip(tmp_path):
    """Fill a PDF form programmatically, then parse it back."""
    from pypdf import PdfReader, PdfWriter
    from trust_generator.generators.pdf_questionnaire import generate_fillable_pdf
    from trust_generator.parsers.pdf_parser import parse_pdf

    # Generate blank PDF
    pdf_path = tmp_path / "blank.pdf"
    generate_fillable_pdf(pdf_path)

    # Fill in some fields programmatically
    reader = PdfReader(str(pdf_path))
    writer = PdfWriter()
    writer.append(reader)

    writer.update_page_form_field_values(
        writer.pages[0],
        {
            "husband.full_legal_name": "John Smith",
            "trust_id.desired_trust_name": "The Smith Trust",
        },
    )

    filled_path = tmp_path / "filled.pdf"
    with open(filled_path, "wb") as f:
        writer.write(f)

    # Parse the filled PDF
    data = parse_pdf(filled_path)
    assert data.husband.full_legal_name == "John Smith"
    assert data.trust_id.desired_trust_name == "The Smith Trust"
```

- [ ] **Step 2: Implement parse_pdf**

Create `src/trust_generator/parsers/pdf_parser.py`:

```python
"""Parse a completed fillable PDF questionnaire into a TrustData instance.

Reads AcroForm field values from a PDF. Field names are dotted schema paths
(e.g., 'husband.full_legal_name') set by the PDF generator.
"""

from __future__ import annotations

import logging
from pathlib import Path

from pypdf import PdfReader

from trust_generator.schema import (
    Elections,
    MarriageInfo,
    OfficeInfo,
    PersonInfo,
    TextBlocks,
    TrustData,
    TrustIdentity,
)

log = logging.getLogger(__name__)


def parse_pdf(filepath: str | Path) -> TrustData:
    """Parse a fillable PDF questionnaire into TrustData.

    Parameters
    ----------
    filepath:
        Path to the completed PDF.

    Returns
    -------
    TrustData
        Populated from form field values.
    """
    filepath = Path(filepath)
    log.info("Parsing PDF questionnaire: %s", filepath)

    reader = PdfReader(str(filepath))
    fields = reader.get_fields() or {}

    # Extract field values into a flat dict
    flat: dict[str, str] = {}
    for name, field_obj in fields.items():
        value = field_obj.get("/V", "")
        if isinstance(value, str):
            flat[name] = value.strip()
        else:
            flat[name] = str(value).strip() if value else ""

    # Build sub-model dicts by prefix
    def _extract(prefix: str) -> dict[str, str]:
        result: dict[str, str] = {}
        pfx = f"{prefix}."
        for key, val in flat.items():
            if key.startswith(pfx) and val:
                result[key[len(pfx):]] = val
        return result

    td = TrustData(
        husband=PersonInfo(**_extract("husband")),
        wife=PersonInfo(**_extract("wife")),
        marriage=MarriageInfo(**_extract("marriage")),
        trust_id=TrustIdentity(**_extract("trust_id")),
        office=OfficeInfo(**_extract("office")),
        text_blocks=TextBlocks(**_extract("text_blocks")),
    )

    log.info("Parsed PDF successfully — %d fields with values",
             sum(1 for v in flat.values() if v))
    return td
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_pdf_parser.py -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add src/trust_generator/parsers/pdf_parser.py tests/test_pdf_parser.py
git commit -m "feat: implement PDF questionnaire parser with pypdf"
```

---

### Task 5: Register .pdf in parser registry and update exports

**Files:**

- Modify: `src/trust_generator/parsers/registry.py`
- Modify: `src/trust_generator/parsers/__init__.py`
- Modify: `src/trust_generator/generators/__init__.py`

- [ ] **Step 1: Write failing test for PDF dispatch**

Add to `tests/test_pdf_parser.py`:

```python
def test_registry_dispatches_pdf(tmp_path):
    """parse_file should accept .pdf extension."""
    from trust_generator.generators.pdf_questionnaire import generate_fillable_pdf
    from trust_generator.parsers import parse_file
    from trust_generator.schema import TrustData

    pdf_path = tmp_path / "test.pdf"
    generate_fillable_pdf(pdf_path)

    data = parse_file(pdf_path)
    assert isinstance(data, TrustData)
```

- [ ] **Step 2: Update registry.py**

In `src/trust_generator/parsers/registry.py`, add `.pdf` support to `parse_file`:

```python
def parse_file(filepath: str | Path) -> TrustData:
    filepath = Path(filepath)
    ext = filepath.suffix.lower()

    if ext == ".docx":
        from trust_generator.parsers.docx_parser import parse_docx
        return parse_docx(filepath)
    elif ext == ".json":
        from trust_generator.parsers.json_parser import parse_json
        return parse_json(filepath)
    elif ext == ".pdf":
        from trust_generator.parsers.pdf_parser import parse_pdf
        return parse_pdf(filepath)
    else:
        raise ValueError(
            f"Unsupported file format: {ext!r}. "
            f"Expected .docx, .json, or .pdf"
        )
```

- [ ] **Step 3: Update parsers/**init**.py**

```python
from trust_generator.parsers.docx_parser import parse_docx
from trust_generator.parsers.json_parser import parse_json
from trust_generator.parsers.pdf_parser import parse_pdf
from trust_generator.parsers.registry import parse_file

__all__ = ["parse_docx", "parse_file", "parse_json", "parse_pdf"]
```

- [ ] **Step 4: Update generators/**init**.py**

```python
from .pdf_questionnaire import generate_fillable_pdf
from .printable_questionnaire import generate_printable_questionnaire
from .trust_document import generate_trust_document

__all__ = [
    "generate_fillable_pdf",
    "generate_printable_questionnaire",
    "generate_trust_document",
]
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_pdf_parser.py tests/test_pdf_questionnaire.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/trust_generator/parsers/registry.py src/trust_generator/parsers/__init__.py src/trust_generator/generators/__init__.py
git commit -m "feat: register .pdf in parser registry and update module exports"
```

---

### Task 6: Add CLI create-fillable-pdf subcommand

**Files:**

- Modify: `src/trust_generator/ui/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing test for new subcommand**

Add to `tests/test_cli.py`:

```python
def test_create_fillable_pdf(tmp_path):
    """create-fillable-pdf should produce a PDF file."""
    try:
        import reportlab  # noqa: F401
    except ImportError:
        pytest.skip("reportlab not installed")

    from trust_generator.ui.cli import run_cli

    out = tmp_path / "fillable.pdf"
    run_cli(["create-fillable-pdf", "-o", str(out)])
    assert out.exists()
    assert out.stat().st_size > 1000
```

- [ ] **Step 2: Add subcommand to CLI**

In `src/trust_generator/ui/cli.py`, add `generate_fillable_pdf` to imports:

```python
from trust_generator.generators import (
    generate_fillable_pdf,
    generate_printable_questionnaire,
    generate_trust_document,
)
```

Add handler function:

```python
def _cmd_create_fillable_pdf(args: argparse.Namespace) -> None:
    """Handle the 'create-fillable-pdf' subcommand."""
    output_path = Path(args.output)
    log.info("Generating fillable PDF questionnaire: %s", output_path)
    result_path = generate_fillable_pdf(output_path)
    print(_green(f"Fillable PDF questionnaire generated: {result_path}"), file=sys.stderr)
```

Add subparser in `_build_parser`:

```python
    fillable_parser = subparsers.add_parser(
        "create-fillable-pdf",
        help="Generate a fillable PDF questionnaire.",
    )
    fillable_parser.add_argument(
        "-o", "--output",
        default="Trust_Intake_Questionnaire.pdf",
        help="Output path (default: Trust_Intake_Questionnaire.pdf).",
    )
```

Register in the handlers dict:

```python
    handlers = {
        "generate": _cmd_generate,
        "validate": _cmd_validate,
        "parse": _cmd_parse,
        "create-printable": _cmd_create_printable,
        "create-fillable-pdf": _cmd_create_fillable_pdf,
    }
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_cli.py -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add src/trust_generator/ui/cli.py tests/test_cli.py
git commit -m "feat: add create-fillable-pdf CLI subcommand"
```

---

### Task 7: End-to-end integration test

**Files:**

- Modify: `tests/test_integration.py`

- [ ] **Step 1: Write integration test for PDF pipeline**

Add to `tests/test_integration.py`:

```python
try:
    import pypdf  # noqa: F401
    import reportlab  # noqa: F401
    HAS_PDF_DEPS = True
except ImportError:
    HAS_PDF_DEPS = False


@pytest.mark.skipif(not HAS_PDF_DEPS, reason="pypdf/reportlab not installed")
def test_pdf_generate_fill_parse_validate_generate(tmp_path: Path) -> None:
    """Full PDF pipeline: generate blank PDF → fill → parse → validate → generate trust doc."""
    from pypdf import PdfReader, PdfWriter
    from trust_generator.generators import generate_fillable_pdf
    from trust_generator.parsers import parse_pdf

    # Step 1: Generate blank PDF
    blank_pdf = tmp_path / "blank.pdf"
    generate_fillable_pdf(blank_pdf)
    assert blank_pdf.exists()

    # Step 2: Fill in fields programmatically
    reader = PdfReader(str(blank_pdf))
    writer = PdfWriter()
    writer.append(reader)

    fill_data = {
        "husband.full_legal_name": "John Andrew Smith",
        "wife.full_legal_name": "Jane Marie Smith",
        "trust_id.desired_trust_name": "The Smith Family Trust",
        "trust_id.date": "January 1, 2026",
        "trust_id.state_of_governing_law": "Illinois",
        "trust_id.county_of_execution": "Winnebago",
    }

    for page in writer.pages:
        writer.update_page_form_field_values(page, fill_data)

    filled_pdf = tmp_path / "filled.pdf"
    with open(filled_pdf, "wb") as f:
        writer.write(f)

    # Step 3: Parse
    data = parse_pdf(filled_pdf)
    assert data.husband.full_legal_name == "John Andrew Smith"
    assert data.wife.full_legal_name == "Jane Marie Smith"

    # Step 4: Validate
    report = validate(data)
    assert report.can_generate is True

    # Step 5: Generate trust document
    out = tmp_path / "smith_trust.docx"
    generate_trust_document(data, out)
    assert out.exists()

    doc = Document(str(out))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "John Andrew Smith" in text
    assert "The Smith Family Trust" in text
    for i in range(1, 13):
        assert f"Article {i}:" in text
```

- [ ] **Step 2: Run integration test**

Run: `pytest tests/test_integration.py::test_pdf_generate_fill_parse_validate_generate -v`
Expected: PASS

- [ ] **Step 3: Run full test suite**

Run: `pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 4: Run linter**

Run: `ruff check src/ tests/`
Expected: `All checks passed!`

- [ ] **Step 5: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add end-to-end integration test for fillable PDF pipeline"
```
