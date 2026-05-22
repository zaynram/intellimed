"""Parse a completed fillable PDF questionnaire into a TrustData instance.

Reads AcroForm field values from a PDF. Field names are dotted schema paths
(e.g., 'party_a.full_legal_name') set by the PDF generator.
"""

from __future__ import annotations

import logging
from pathlib import Path

from pypdf import PdfReader  # type: ignore[import-untyped]

from trust_generator.v2.schema import (
    MarriageInfo,
    OfficeInfo,
    PersonInfo,
    TextBlocks,
    TrustData,
    TrustIdentity,
    TrustType,
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
        Populated from form field values. Fields not present in the PDF
        (or left blank) default to empty strings.
    """
    filepath = Path(filepath)
    log.info("Parsing PDF questionnaire: %s", filepath)

    reader = PdfReader(str(filepath))
    fields = reader.get_fields() or {}

    # Extract field values into a flat dict.
    # pypdf Field objects expose a .value property (pypdf 4.x).
    flat: dict[str, str] = {}
    for name, field_obj in fields.items():
        raw = field_obj.value
        if isinstance(raw, str):
            flat[name] = raw.strip()
        else:
            flat[name] = str(raw).strip() if raw else ""

    # Build sub-model dicts by prefix
    def _extract(prefix: str) -> dict[str, str]:
        result: dict[str, str] = {}
        pfx = f"{prefix}."
        for key, val in flat.items():
            if key.startswith(pfx) and val:
                result[key[len(pfx) :]] = val
        return result

    party_a_info = PersonInfo(**_extract("party_a"))
    party_b_info = PersonInfo(**_extract("party_b"))
    grantor_info = PersonInfo(**_extract("grantor"))

    # Auto-detect trust type
    trust_type_raw = flat.get("trust_type", "")
    if trust_type_raw and trust_type_raw in ("joint", "individual"):
        trust_type = TrustType(trust_type_raw)
    else:
        party_a_name = party_a_info.full_legal_name or ""
        party_b_name = party_b_info.full_legal_name or ""
        if bool(party_a_name) ^ bool(party_b_name):
            trust_type = TrustType.INDIVIDUAL
            if not grantor_info.full_legal_name:
                grantor_info = PersonInfo(
                    full_legal_name=party_a_name or party_b_name,
                )
        else:
            trust_type = TrustType.JOINT

    td = TrustData(
        trust_type=trust_type,
        grantor=grantor_info,
        party_a=party_a_info,
        party_b=party_b_info,
        marriage=MarriageInfo(**_extract("marriage")),
        trust_id=TrustIdentity(**_extract("trust_id")),  # type: ignore[arg-type]  # validator coerces str→SsnOwner
        office=OfficeInfo(**_extract("office")),
        text_blocks=TextBlocks(**_extract("text_blocks")),
    )

    log.info(
        "Parsed PDF successfully — %d fields with values",
        sum(1 for v in flat.values() if v),
    )
    return td
