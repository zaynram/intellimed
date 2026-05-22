"""Shared fixtures for diagnostics-engine cycle tests."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from trust_generator.v3.config.firm import FirmConfig, FirmIdentity, User
from trust_generator.v3.schema import (
    Address,
    BeneficiaryShare,
    Elections,
    GrantorInfo,
    OfficeInfo,
    TextBlocks,
    TrustData,
    TrustIdentity,
    TrustType,
)


@pytest.fixture
def tmp_audit_dir(tmp_path: Path) -> Path:
    """A clean per-test directory for AuditLog writes."""
    audit_dir = tmp_path / "audit"
    audit_dir.mkdir()
    return audit_dir


@pytest.fixture
def tmp_rules_dir(tmp_path: Path) -> Path:
    """A clean per-test directory for custom rule YAML files."""
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()
    return rules_dir


@pytest.fixture
def firm_config_factory(
    tmp_audit_dir: Path, tmp_rules_dir: Path
) -> Callable[..., FirmConfig]:
    """Build a minimal FirmConfig with overridable fields.

    Both ``user`` and ``firm`` are required FirmConfig fields with no
    default_factory, so both must be provided. The factory uses
    ``Address()`` (all-empty strings) for office_address, which keeps
    the US-ZIP cross-field validator dormant (it only fires when
    ``zip_code`` is non-empty).
    """

    def _build(**overrides: Any) -> FirmConfig:
        defaults: dict[str, Any] = {
            "user": User(upn="testuser"),
            "firm": FirmIdentity(
                name="Test Firm",
                phone="555-0100",
                office_address=Address(),
            ),
        }
        defaults.update(overrides)
        cfg = FirmConfig.model_validate(defaults)
        cfg.diagnostics.audit_log_dir = tmp_audit_dir
        cfg.diagnostics.rules_dir = tmp_rules_dir
        return cfg

    return _build


@pytest.fixture
def trust_data_factory() -> Callable[..., TrustData]:
    """Build a minimal TrustData; kwargs inject rule-triggering states."""

    def _build(
        *,
        beneficiary_shares: list[BeneficiaryShare] | None = None,
        estate_value_approximate: Decimal | None = None,
        statement_of_intent: str = "",
        file_number: str = "",
        trust_type: TrustType = TrustType.JOINT,
        execution_date: date | None = None,
    ) -> TrustData:
        return TrustData(
            grantor=GrantorInfo(full_legal_name="Test Grantor"),
            trust_id=TrustIdentity(
                desired_trust_name="Test Family Trust",
                trust_type=trust_type,
                execution_date=execution_date,
            ),
            office=OfficeInfo(file_number=file_number),
            elections=Elections(estate_value_approximate=estate_value_approximate),
            text_blocks=TextBlocks(statement_of_intent=statement_of_intent),
            beneficiary_shares=beneficiary_shares or [],
        )

    return _build
