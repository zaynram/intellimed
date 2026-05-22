"""Tests for configuration loading."""

from trust_generator.v2.config import AppConfig, load_config


def test_load_config_returns_defaults():
    """Config loader should never crash, even with no file."""
    cfg = load_config()
    assert isinstance(cfg, AppConfig)
    assert cfg.firm.name == "Crosby and Crosby LLP"
    assert cfg.jurisdiction.default_state == "Illinois"
    assert cfg.jurisdiction.default_county == "Winnebago"
    assert "760 ILCS" in cfg.jurisdiction.trust_code_citation


def test_default_firm_config_has_all_fields():
    cfg = AppConfig()
    assert cfg.firm.address_line1
    assert cfg.firm.address_line2
    assert cfg.firm.phone
