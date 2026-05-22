"""Integration tests: downstream subsystems read from FirmConfig (spec §10.3).

Per spec amendment A-2 (2026-04-22), these tests cover the config-surface
contract only. The ``trustee_catalog`` refresh client and diagnostics
subsystem are both deferred to their own specs; when those subsystems land,
they swap their constants for ``cfg.trustee_catalog.*`` / ``cfg.diagnostics.*``
and these tests grow assertions on consumer behavior.
"""

from __future__ import annotations

from pathlib import Path

from trust_generator.v3.config import load_firm_config

SHARED_BODY = """
[firm]
name = "Integration Firm LLP"
phone = "(555) 000-0000"

[firm.office_address]
street = "1 Way"
city = "City"
state = "IL"
zip_code = "61114"

[jurisdiction]
default_state = "Illinois"
default_county = "Winnebago"
trust_code_citation = "Illinois Trust Code"

[estate_thresholds]

[trustee_catalog]
fdic_api_base = "https://example.test/fdic-api"
fdic_request_timeout_s = 45

[diagnostics]
default_restriction_level = "warning"
"""


LOCAL_BODY = """
[user]
upn = "testuser"
"""


def test_trustee_catalog_consumer_reads_from_config(tmp_path: Path) -> None:
    (tmp_path / "shared.toml").write_text(SHARED_BODY, encoding="utf-8")
    (tmp_path / "local.toml").write_text(LOCAL_BODY, encoding="utf-8")
    cfg = load_firm_config(
        local_path=tmp_path / "local.toml",
        shared_path=tmp_path / "shared.toml",
    )
    assert str(cfg.trustee_catalog.fdic_api_base).startswith("https://example.test/")
    assert cfg.trustee_catalog.fdic_request_timeout_s == 45


def test_diagnostics_consumer_reads_default_restriction_level(tmp_path: Path) -> None:
    (tmp_path / "shared.toml").write_text(SHARED_BODY, encoding="utf-8")
    (tmp_path / "local.toml").write_text(LOCAL_BODY, encoding="utf-8")
    cfg = load_firm_config(
        local_path=tmp_path / "local.toml",
        shared_path=tmp_path / "shared.toml",
    )
    assert cfg.diagnostics.default_restriction_level == "warning"
