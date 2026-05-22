"""Main validation logic for TrustData instances."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from functools import partial
from operator import attrgetter

from trust_generator.config import AppConfig, load_config
from trust_generator.schema import (
    PropertyClassification,
    RemoteContingent,
    RetirementStrategy,
    TrustData,
    TrustType,
)

from .report import (
    FieldEntry,
    FieldStatus,
    Finding,
    Severity,
    ValidationReport,
)

log = logging.getLogger(__name__)


def _check_field(
    data: TrustData,
    report: ValidationReport,
    *,
    field_path: str,
    label: str,
    required: bool = False,
    set_default: str = "",
    default_reason: str = "",
) -> None:
    """Classify a single field and append a FieldEntry (and optionally a Finding)."""
    value: str = attrgetter(field_path)(data)
    if set_default and not value:
        segments = field_path.split(".")
        last = segments.pop()
        current: object = data
        for seg in segments:
            current = getattr(current, seg)
        setattr(current, last, value := set_default)
        report.fields.append(
            FieldEntry(
                field_path=field_path,
                label=label,
                status=FieldStatus.DEFAULTED,
                value=value,
                default_reason=default_reason,
            )
        )
        report.findings.append(
            Finding(
                message=f"{label} is using default value: {value}",
                severity=Severity.INFO,
                field_path=field_path,
            )
        )
    elif value:
        report.fields.append(
            FieldEntry(
                field_path=field_path,
                label=label,
                status=FieldStatus.PROVIDED,
                value=value,
            )
        )
    elif required:
        report.fields.append(
            FieldEntry(
                field_path=field_path,
                label=label,
                status=FieldStatus.MISSING_REQUIRED,
            )
        )
        report.findings.append(
            Finding(
                message=f"{label} is required but empty",
                severity=Severity.ERROR,
                field_path=field_path,
            )
        )
    else:
        report.fields.append(
            FieldEntry(
                field_path=field_path,
                label=label,
                status=FieldStatus.MISSING_OPTIONAL,
            )
        )
        if default_reason:
            report.findings.append(
                Finding(
                    message=f"{label} is empty — {default_reason}",
                    severity=Severity.WARNING,
                    field_path=field_path,
                )
            )


def _check_list_field(
    report: ValidationReport,
    *,
    field_path: str,
    label: str,
    items: list,
    warning_message: str,
) -> None:
    """Check a list field and warn if empty."""
    if items:
        report.fields.append(
            FieldEntry(
                field_path=field_path,
                label=label,
                status=FieldStatus.PROVIDED,
                value=f"{len(items)} item(s)",
            )
        )
    else:
        report.fields.append(
            FieldEntry(
                field_path=field_path,
                label=label,
                status=FieldStatus.MISSING_OPTIONAL,
            )
        )
        report.findings.append(
            Finding(
                message=warning_message,
                severity=Severity.WARNING,
                field_path=field_path,
            )
        )


def _parse_share(share_str: str) -> float | None:
    """Try to parse a share string as a number, returning None on failure."""
    cleaned = re.sub(r"[%\s]", "", share_str)
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _cross_field_checks(data: TrustData, report: ValidationReport) -> None:
    """Run cross-field validation rules."""
    # Beneficiary shares sum check
    if data.beneficiary_shares:
        values = [_parse_share(b.share) for b in data.beneficiary_shares]
        if all(v is not None for v in values):
            total = sum(v for v in values if v is not None)
            if abs(total - 100.0) > 0.01:
                report.findings.append(
                    Finding(
                        message=f"Beneficiary shares sum to {total}%, not 100%",
                        severity=Severity.WARNING,
                        field_path="beneficiary_shares",
                    )
                )
        else:
            report.findings.append(
                Finding(
                    message="Some beneficiary share percentages could not be parsed as numbers",
                    severity=Severity.WARNING,
                    field_path="beneficiary_shares",
                )
            )

    # Separate property requires assets
    if data.elections.property_classification == PropertyClassification.SEPARATE:
        has_assets = any([
            data.real_property,
            data.financial_accounts,
            data.vehicles,
            data.insurance_policies,
            data.pensions,
            data.valuables,
        ])
        if not has_assets:
            report.findings.append(
                Finding(
                    message="Property classification is SEPARATE but no assets are listed",
                    severity=Severity.WARNING,
                    field_path="elections.property_classification",
                )
            )

    # Charity contingent requires charity name
    if (
        data.elections.remote_contingent == RemoteContingent.CHARITY
        and not data.elections.remote_contingent_charity
    ):
        report.findings.append(
            Finding(
                message="Remote contingent is CHARITY but no charity name is specified",
                severity=Severity.ERROR,
                field_path="elections.remote_contingent_charity",
            )
        )

    # Mutual exclusivity: trust type vs grantor/party fields
    if data.trust_type == TrustType.INDIVIDUAL:
        if data.party_a.full_legal_name or data.party_b.full_legal_name:
            report.findings.append(
                Finding(
                    message="Party A/B fields are populated but trust type is Individual — these will be ignored.",
                    severity=Severity.WARNING,
                    field_path="party_a.full_legal_name",
                )
            )
    elif data.grantor.full_legal_name:
        report.findings.append(
            Finding(
                message="Grantor field is populated but trust type is Joint — this will be ignored.",
                severity=Severity.WARNING,
                field_path="grantor.full_legal_name",
            )
        )

    # Trust retirement strategy info
    if data.elections.retirement_strategy == RetirementStrategy.TRUST:
        report.findings.append(
            Finding(
                message="Trust-controlled retirement requires attorney review of SECURE Act compliance",
                severity=Severity.INFO,
                field_path="elections.retirement_strategy",
            )
        )


def validate(data: TrustData, config: AppConfig | None = None) -> ValidationReport:
    """Validate a TrustData instance and return a structured report."""
    if config is None:
        config = load_config()
    report = ValidationReport()

    # --- Field-level checks ---

    check = partial(_check_field, data, report)

    if data.trust_type == TrustType.INDIVIDUAL:
        report.findings.append(
            Finding(
                message=(
                    "Trust type is Individual (single grantor). "
                    "If this should be a Joint trust, verify both party names "
                    "are filled in the questionnaire."
                ),
                severity=Severity.INFO,
                field_path="trust_type",
            )
        )
        check(
            field_path="grantor.full_legal_name",
            label="Grantor's Full Legal Name",
            required=True,
        )
    else:
        check(
            field_path="party_a.full_legal_name",
            label=f"{data.party_a_label}'s Full Legal Name",
            required=True,
        )
        check(
            field_path="party_b.full_legal_name",
            label=f"{data.party_b_label}'s Full Legal Name",
            required=True,
        )

    name_reason = (
        "will be derived from grantor's last name"
        if data.trust_type == TrustType.INDIVIDUAL
        else f"will be derived from {data.party_a_label}'s last name"
    )

    check(
        field_path="trust_id.desired_trust_name",
        label="Trust Name",
        default_reason=name_reason,
    )

    check(
        field_path="trust_id.date",
        label="Trust Date",
        default_reason="defaults to today's date",
        set_default=datetime.now().strftime("%B %d, %Y"),  # noqa: DTZ005
    )

    check(
        field_path="trust_id.state_of_governing_law",
        label="State of Governing Law",
        default_reason="firm default jurisdiction",
        set_default=config.jurisdiction.default_state,
    )

    check(
        field_path="trust_id.county_of_execution",
        label="County of Execution",
        default_reason="firm default county",
        set_default=config.jurisdiction.default_county,
    )

    check_ls = partial(_check_list_field, report)

    # List fields
    check_ls(
        field_path="children",
        label="Children",
        items=data.children,
        warning_message="No children listed",
    )

    check_ls(
        field_path="successor_trustees",
        label="Successor Trustees",
        items=data.successor_trustees,
        warning_message="No successor trustees listed",
    )

    check_ls(
        field_path="beneficiary_shares",
        label="Beneficiary Shares",
        items=data.beneficiary_shares,
        warning_message="No beneficiaries listed",
    )

    # --- Cross-field checks ---
    _cross_field_checks(data, report)

    log.debug(
        "Validation complete: %d fields, %d findings (%d errors, %d warnings)",
        len(report.fields),
        len(report.findings),
        len(report.errors),
        len(report.warnings),
    )

    return report
