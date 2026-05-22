"""Generate a fillable PDF Trust Intake Questionnaire.

PDF form field names use dotted schema paths (e.g., 'party_a.full_legal_name')
so the PDF parser can map values directly to TrustData fields.
"""

from __future__ import annotations

import logging
from pathlib import Path

from reportlab.lib.pagesizes import letter  # type: ignore[import-untyped]
from reportlab.lib.units import inch  # type: ignore[import-untyped]
from reportlab.pdfgen import canvas as pdfcanvas  # type: ignore[import-untyped]

from trust_generator.v2.config import AppConfig, load_config

log = logging.getLogger(__name__)

# Each entry: {"path": dotted schema path, "label": human label, "section": grouping}
# Section names for Party A/B use placeholders that are replaced at generation time.
_PARTY_A_SECTION = "Party A Information"
_PARTY_B_SECTION = "Party B Information"

FIELD_MAP: list[dict[str, str]] = [
    # Office
    {"path": "office.file_number", "label": "File Number", "section": "Office Use"},
    {"path": "office.attorney", "label": "Attorney", "section": "Office Use"},
    {"path": "office.paralegal", "label": "Paralegal", "section": "Office Use"},
    {"path": "office.date_opened", "label": "Date Opened", "section": "Office Use"},
    # Trust Type
    {
        "path": "trust_type",
        "label": "Trust Type (joint / individual)",
        "section": "Trust Type",
    },
    # Grantor (for individual trusts)
    {
        "path": "grantor.full_legal_name",
        "label": "Full Legal Name",
        "section": "Grantor (Individual Trust)",
    },
    {
        "path": "grantor.date_of_birth",
        "label": "Date of Birth",
        "section": "Grantor (Individual Trust)",
    },
    {
        "path": "grantor.ssn",
        "label": "Social Security Number",
        "section": "Grantor (Individual Trust)",
    },
    {
        "path": "grantor.address",
        "label": "Address",
        "section": "Grantor (Individual Trust)",
    },
    {
        "path": "grantor.phone",
        "label": "Phone",
        "section": "Grantor (Individual Trust)",
    },
    {
        "path": "grantor.email",
        "label": "Email",
        "section": "Grantor (Individual Trust)",
    },
    {
        "path": "grantor.employer",
        "label": "Employer",
        "section": "Grantor (Individual Trust)",
    },
    # Party A
    {
        "path": "party_a.full_legal_name",
        "label": "Full Legal Name",
        "section": _PARTY_A_SECTION,
    },
    {
        "path": "party_a.date_of_birth",
        "label": "Date of Birth",
        "section": _PARTY_A_SECTION,
    },
    {
        "path": "party_a.ssn",
        "label": "Social Security Number",
        "section": _PARTY_A_SECTION,
    },
    {"path": "party_a.address", "label": "Address", "section": _PARTY_A_SECTION},
    {"path": "party_a.phone", "label": "Phone", "section": _PARTY_A_SECTION},
    {"path": "party_a.email", "label": "Email", "section": _PARTY_A_SECTION},
    {"path": "party_a.employer", "label": "Employer", "section": _PARTY_A_SECTION},
    # Party B
    {
        "path": "party_b.full_legal_name",
        "label": "Full Legal Name",
        "section": _PARTY_B_SECTION,
    },
    {
        "path": "party_b.date_of_birth",
        "label": "Date of Birth",
        "section": _PARTY_B_SECTION,
    },
    {
        "path": "party_b.ssn",
        "label": "Social Security Number",
        "section": _PARTY_B_SECTION,
    },
    {"path": "party_b.address", "label": "Address", "section": _PARTY_B_SECTION},
    {"path": "party_b.phone", "label": "Phone", "section": _PARTY_B_SECTION},
    {"path": "party_b.email", "label": "Email", "section": _PARTY_B_SECTION},
    {"path": "party_b.employer", "label": "Employer", "section": _PARTY_B_SECTION},
    {
        "path": "party_b.maiden_name",
        "label": "Maiden Name",
        "section": _PARTY_B_SECTION,
    },
    # Marriage
    {
        "path": "marriage.date_of_marriage",
        "label": "Date of Marriage",
        "section": "Marriage Information",
    },
    {
        "path": "marriage.state_of_marriage",
        "label": "State of Marriage",
        "section": "Marriage Information",
    },
    {
        "path": "marriage.prenuptial_agreement",
        "label": "Prenuptial Agreement",
        "section": "Marriage Information",
    },
    {
        "path": "marriage.prenuptial_details",
        "label": "Prenuptial Details",
        "section": "Marriage Information",
    },
    # Trust ID
    {
        "path": "trust_id.desired_trust_name",
        "label": "Desired Trust Name",
        "section": "Trust Information",
    },
    {"path": "trust_id.date", "label": "Trust Date", "section": "Trust Information"},
    {
        "path": "trust_id.state_of_governing_law",
        "label": "State of Governing Law",
        "section": "Trust Information",
    },
    {
        "path": "trust_id.county_of_execution",
        "label": "County of Execution",
        "section": "Trust Information",
    },
    {
        "path": "trust_id.whose_ssn_for_tax_id",
        "label": "Whose SSN for Tax ID",
        "section": "Trust Information",
    },
    # Text blocks
    {
        "path": "text_blocks.statement_of_intent",
        "label": "Statement of Intent",
        "section": "Text Sections",
    },
    {
        "path": "text_blocks.personal_message",
        "label": "Personal Message",
        "section": "Text Sections",
    },
    {
        "path": "text_blocks.additional_notes",
        "label": "Additional Notes",
        "section": "Text Sections",
    },
]


def generate_fillable_pdf(
    output_path: str | Path,
    config: AppConfig | None = None,
    *,
    party_a_label: str = "Husband",
    party_b_label: str = "Wife",
    trust_type: str = "joint",
) -> str:
    """Generate a fillable PDF questionnaire with AcroForm fields.

    Parameters
    ----------
    trust_type:
        ``"joint"`` (default) includes Party A/B sections.
        ``"individual"`` excludes Party A/B and Marriage sections,
        includes only Grantor sections.

    Returns the output path as a string.
    """
    cfg = config or load_config()
    out = str(Path(output_path))

    # Filter field map based on trust type
    if trust_type == "individual":
        excluded_sections = {_PARTY_A_SECTION, _PARTY_B_SECTION, "Marriage Information"}
        fields = [f for f in FIELD_MAP if f["section"] not in excluded_sections]
    else:
        excluded_sections = {"Grantor (Individual Trust)"}
        fields = [f for f in FIELD_MAP if f["section"] not in excluded_sections]

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

    # Apply dynamic party labels to section names
    section_remap = {
        _PARTY_A_SECTION: f"{party_a_label} Information",
        _PARTY_B_SECTION: f"{party_b_label} Information",
    }

    for entry in fields:
        # Section header
        display_section = section_remap.get(entry["section"], entry["section"])
        if display_section != current_section:
            current_section = display_section
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
        )
        y -= field_height + 6

    c.save()
    log.info("Fillable PDF questionnaire written to %s", out)
    return out
