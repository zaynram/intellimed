"""Parse a completed fillable PDF questionnaire into TrustData (v3).

AcroForm field names use dotted schema paths (e.g., 'grantor.full_legal_name')
matching the v3 schema layout — the same convention as the v2.2 fillable PDF.

Repeated (list-shaped) sections use 0-indexed numbered field names of the
form ``<section>[i].<attr>``. The withdrawal-schedule and successor-trustee
loops establish this convention; the beneficiary loops follow it verbatim:

- ``children[i].full_legal_name`` / ``children[i].date_of_birth``
- ``other_beneficiaries[i].full_legal_name``
- ``beneficiary_shares[i].recipient_name`` / ``beneficiary_shares[i].share_percent``

Public API:
    parse_pdf(filepath: Path, seed_initialized: TrustData) -> TrustData

Internal helpers:
    _normalize_field_values(fields_dict) -> dict[str, str | None]
        Implements §5.4.A: absent / present-None / present-empty / whitespace-only
        all normalize to None. After normalization all coercion helpers receive
        either None or a non-empty stripped string.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from pathlib import Path

from pypdf import PdfReader  # type: ignore[import-untyped]
from pypdf.errors import PyPdfError  # type: ignore[import-untyped]

from trust_generator.v3.parsers.coercion import (
    _to_address,
    _to_date,
    _to_decimal,
    _to_person_reference,
)
from trust_generator.v3.parsers.docx_parser import (
    _apply_post_merge_resolution,
    _apply_post_promotion_protocol,
)
from trust_generator.v3.schema import (
    BeneficiaryShare,
    Child,
    MaritalStatus,
    OtherBeneficiary,
    SuccessorTrustee,
    TrustData,
    TrustType,
    WithdrawalStep,
    promote_seed,  # imported for P1 patch binding; NEVER called here
)

log = logging.getLogger(__name__)


def _normalize_field_values(
    fields_dict: dict,
) -> dict[str, str | None]:
    """Normalize AcroForm field values per §5.4.A.

    Three field-presence states all collapse to None:
    1. Field absent — key not in fields_dict (caller excludes it; None implied).
    2. Field present, value None — Field.value is None.
    3. Field present, value empty or whitespace-only — Field.value.strip() == "".

    Returns a plain dict[str, str | None]. Values are either None or a
    non-empty stripped string; coercion helpers downstream receive no
    empty strings.
    """
    result: dict[str, str | None] = {}
    for name, field_obj in fields_dict.items():
        raw = getattr(field_obj, "value", None)
        if raw is None:
            result[name] = None
        elif isinstance(raw, str):
            stripped = raw.strip()
            result[name] = stripped if stripped else None
        else:
            # Non-string non-None values (e.g., bool for checkboxes): stringify.
            as_str = str(raw).strip()
            result[name] = as_str if as_str else None
    return result


def parse_pdf(filepath: Path, seed_initialized: TrustData) -> TrustData:
    """Parse a fillable PDF questionnaire INTO a copy of seed_initialized.

    Implements the seven-step post-promotion merge protocol (spec §5.3).
    seed_initialized is never mutated (P3): the parser deepcopies at entry.

    Parameters
    ----------
    filepath:
        Path to the completed fillable PDF.
    seed_initialized:
        The TrustData produced by promote_seed() at consultation time.
        This argument is required (no default) to keep the post-promotion
        contract loud at every call site. P3 postcondition: this value is
        field-level equal before and after this call.

    Returns
    -------
    TrustData
        A filled copy of seed_initialized. Return shape is TrustData only
        (no ExtractionTrace pairing — the trace is OCR-specific, per §5.2).

    Raises
    ------
    FileNotFoundError
        The path does not exist.
    ValueError
        The file exists but cannot be read as a PDF — corrupt, encrypted,
        or empty. The raw ``pypdf`` failure (any ``PyPdfError`` subclass:
        ``PdfReadError`` / ``FileNotDecryptedError`` / ``EmptyFileError``)
        is wrapped into ``ValueError`` so the parser-layer error contract
        stays uniform with ``json_parser`` (the registry enumerates only
        ``FileNotFoundError`` and ``ValueError`` for parser dispatch).
    """
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"PDF not found: {filepath}")

    log.info("Parsing PDF questionnaire: %s", filepath)

    # §5.3 step 1: deepcopy — satisfies P3 immutability postcondition.
    result = seed_initialized.model_copy(deep=True)

    # §5.3 step 2: extract content from AcroForm fields. A corrupt or
    # encrypted PDF makes PdfReader/get_fields raise a raw pypdf error
    # (PdfReadError / FileNotDecryptedError / EmptyFileError — all
    # subclass PyPdfError); wrap as ValueError per the parser-layer
    # error contract (registry.parse_file documents ValueError only).
    try:
        reader = PdfReader(str(filepath))
        raw_fields = reader.get_fields() or {}
    except PyPdfError as exc:
        raise ValueError(
            f"could not read PDF {filepath}: {type(exc).__name__}"
        ) from exc
    flat = _normalize_field_values(raw_fields)

    # Capture parser-internal carriers for post-merge resolution (§5.3 step 6).
    # exclusions_string does not transit through `result` (no v3 schema field).
    exclusions_string: str = flat.get("text_blocks.exclusions") or ""

    # §5.3 step 3–4: coerce trust_type / marital_status and apply the
    # post-promotion protocol.  _apply_post_promotion_protocol from docx §6.6.
    # None / absent gate: if the field normalized to None, pass None — the
    # helper treats None as "no mutation requested" (spec §5.3 step 4).
    _trust_type_raw = flat.get("trust_id.trust_type")
    parsed_trust_type: TrustType | None = None
    if _trust_type_raw is not None:
        try:
            parsed_trust_type = TrustType(_trust_type_raw)
        except ValueError:
            log.warning(
                "Unknown trust_type value %r in PDF field trust_id.trust_type; "
                "seed value preserved.",
                _trust_type_raw,
            )

    _marital_raw = flat.get("trust_id.marital_status")
    parsed_marital_status: MaritalStatus | None = None
    if _marital_raw is not None:
        try:
            parsed_marital_status = MaritalStatus(_marital_raw)
        except ValueError:
            log.warning(
                "Unknown marital_status value %r in PDF field trust_id.marital_status; "
                "seed value preserved.",
                _marital_raw,
            )

    _apply_post_promotion_protocol(result, parsed_trust_type, parsed_marital_status)

    # §5.3 step 5: apply remaining field mutations.

    # Grantor fields.
    if (_name := flat.get("grantor.full_legal_name")) is not None:
        result.grantor.full_legal_name = _name
    if (_dob := flat.get("grantor.date_of_birth")) is not None:
        _parsed_dob = _to_date(_dob)
        if _parsed_dob is not None:
            result.grantor.date_of_birth = _parsed_dob
    if (_addr := flat.get("grantor.address")) is not None:
        result.grantor.address = _to_address(_addr)

    # Co-grantor fields (when co_grantor was materialized by the protocol).
    if result.co_grantor is not None:
        if (_co_name := flat.get("co_grantor.full_legal_name")) is not None:
            result.co_grantor.full_legal_name = _co_name
        if (_co_dob := flat.get("co_grantor.date_of_birth")) is not None:
            _parsed_co_dob = _to_date(_co_dob)
            if _parsed_co_dob is not None:
                result.co_grantor.date_of_birth = _parsed_co_dob

    # Trust identity fields beyond trust_type / marital_status.
    if (_tname := flat.get("trust_id.desired_trust_name")) is not None:
        result.trust_id.desired_trust_name = _tname

    # Withdrawal steps: numbered fields withdrawal[i].age / .percent / .description.
    _withdrawal_steps: list[WithdrawalStep] = []
    i = 0
    while True:
        _age_raw = flat.get(f"withdrawal[{i}].age")
        _pct_raw = flat.get(f"withdrawal[{i}].percent")
        _desc_raw = flat.get(f"withdrawal[{i}].description")
        if _age_raw is None and _pct_raw is None and _desc_raw is None:
            break
        if _age_raw is None:
            log.warning(
                "withdrawal[%d] has no age (percent=%r, description=%r); "
                "row dropped (§5.4.7 — age is required).",
                i,
                _pct_raw,
                _desc_raw,
            )
            i += 1
            continue
        try:
            _age = int(_age_raw)
        except (ValueError, TypeError):
            log.warning(
                "Could not parse withdrawal[%d].age %r; row dropped (§5.4.7).",
                i,
                _age_raw,
            )
            i += 1
            continue
        if _pct_raw is None:
            log.warning(
                "withdrawal[%d] has no percent; defaulting to 0 "
                "(§5.4.7 missing-percent disposition under review — plan #16).",
                i,
            )
        # WithdrawalStep.percent is a required Decimal (no schema default).
        # _to_decimal returns None on a missing/unparseable percent; the row
        # still survives (the age is valid) so substitute Decimal(0) — the
        # missing-percent warning above already surfaces the substitution.
        _withdrawal_steps.append(
            WithdrawalStep(
                age=_age,
                percent=_to_decimal(_pct_raw or "0") or Decimal(0),
                description=_desc_raw or "",
            )
        )
        i += 1
    if _withdrawal_steps:
        result.withdrawal_schedule = _withdrawal_steps

    # Successor trustees: numbered fields successor_trustees[i].full_legal_name.
    # Step 5 emits plain SuccessorTrustee(full_legal_name=name) entries onto
    # result.successor_trustees. CorporateTrustee discrimination (§5.4.9) runs
    # entirely inside _apply_post_merge_resolution (step 6) via re-application
    # of _is_entity_name per entry — no caller-side entity-flag bookkeeping needed.
    i = 0
    while True:
        _tname_raw = flat.get(f"successor_trustees[{i}].full_legal_name")
        if _tname_raw is None:
            break
        result.successor_trustees.append(SuccessorTrustee(full_legal_name=_tname_raw))
        i += 1

    # Children: numbered fields children[i].full_legal_name / .date_of_birth.
    # Mirrors docx_parser's children extraction (docx §6.x) — one Child per
    # row, name routed through _to_person_reference so the §5.4.4 one-token
    # entity trap fires, DOB coerced via _to_date.
    i = 0
    while True:
        _child_name_raw = flat.get(f"children[{i}].full_legal_name")
        _child_dob_raw = flat.get(f"children[{i}].date_of_birth")
        if _child_name_raw is None and _child_dob_raw is None:
            break
        if _child_name_raw is None:
            log.warning(
                "children[%d] has a date_of_birth (%r) but no full_legal_name; "
                "row dropped.",
                i,
                _child_dob_raw,
            )
            i += 1
            continue
        _child_ref = _to_person_reference(_child_name_raw)
        result.children.append(
            Child(
                full_legal_name=_child_ref.full_legal_name,
                is_entity=_child_ref.is_entity,
                entity_name=_child_ref.entity_name,
                date_of_birth=_to_date(_child_dob_raw) if _child_dob_raw else None,
            )
        )
        i += 1

    # Other beneficiaries: numbered fields other_beneficiaries[i].full_legal_name.
    # Mirrors docx_parser's other-beneficiary extraction.
    i = 0
    while True:
        _ob_name_raw = flat.get(f"other_beneficiaries[{i}].full_legal_name")
        if _ob_name_raw is None:
            break
        _ob_ref = _to_person_reference(_ob_name_raw)
        result.other_beneficiaries.append(
            OtherBeneficiary(
                full_legal_name=_ob_ref.full_legal_name,
                is_entity=_ob_ref.is_entity,
                entity_name=_ob_ref.entity_name,
            )
        )
        i += 1

    # Beneficiary shares: numbered fields beneficiary_shares[i].recipient_name /
    # .share_percent. Mirrors docx_parser's §5.4.2 share-percent branch — rows
    # whose share-percent fails to parse to a non-zero Decimal are dropped with
    # a warning naming the dropped row (Decision log #11). The recipient is
    # stored as recipient_external (a PersonReference), matching docx_parser.
    i = 0
    while True:
        _share_name_raw = flat.get(f"beneficiary_shares[{i}].recipient_name")
        _share_pct_raw = flat.get(f"beneficiary_shares[{i}].share_percent")
        if _share_name_raw is None and _share_pct_raw is None:
            break
        if _share_name_raw is None:
            log.warning(
                "beneficiary_shares[%d] has a share_percent (%r) but no "
                "recipient_name; row dropped.",
                i,
                _share_pct_raw,
            )
            i += 1
            continue
        # _to_decimal returns None on an unparseable/blank percent and
        # Decimal(0) on a legitimate zero; the §5.4.2 row-drop fires on
        # either — a 0% share is as meaningless as an unparseable one.
        _share_pct = _to_decimal(_share_pct_raw or "0")
        if _share_pct is None or _share_pct == Decimal(0):
            log.warning(
                "Dropping beneficiary_shares[%d] row for %r: could not parse "
                "share-percent %r per §5.4.2",
                i,
                _share_name_raw,
                _share_pct_raw,
            )
            i += 1
            continue
        _share_ref = _to_person_reference(_share_name_raw)
        result.beneficiary_shares.append(
            BeneficiaryShare(
                recipient_external=_share_ref,
                share_percent=_share_pct,
            )
        )
        i += 1

    # §5.3 step 6: post-merge resolution passes.
    # _apply_post_merge_resolution from docx §6.8 — 2-arg form (confirmed).
    # Internally iterates result.successor_trustees, applies _is_entity_name,
    # reconstructs CorporateTrustee entries, and runs disinheritance resolution.
    _apply_post_merge_resolution(result, exclusions_string)

    log.info(
        "Parsed PDF successfully — %d fields with values.",
        sum(1 for v in flat.values() if v is not None),
    )

    # §5.3 step 7: return result.
    return result
