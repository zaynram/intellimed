"""
Configuration loader for trust-generator.

Strategy:
1. Look for config/firm.toml relative to the project root (development).
2. Look in %APPDATA%/trust-generator/firm.toml (deployed .exe).
3. If neither exists, copy the bundled default to %APPDATA% and load it.
4. If all else fails, use hardcoded defaults (the app never crashes on missing config).
"""

# ruff: noqa: BLE001
from __future__ import annotations

import logging
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

import tomllib

log = logging.getLogger(__name__)


@dataclass
class FirmConfig:
    name: str = "Crosby and Crosby LLP"
    address_line1: str = "3815 N Mulford Rd. 4"
    address_line2: str = "Rockford, IL 61114"
    phone: str = "(815) 367-6432"


@dataclass
class JurisdictionConfig:
    default_state: str = "Illinois"
    default_county: str = "Winnebago"
    trust_code_citation: str = "Illinois Trust Code (760 ILCS 3/101, et seq.)"


@dataclass
class DraftsConfig:
    auto_purge_days: int = 90


@dataclass
class AppConfig:
    firm: FirmConfig = field(default_factory=FirmConfig)
    jurisdiction: JurisdictionConfig = field(default_factory=JurisdictionConfig)
    drafts: DraftsConfig = field(default_factory=DraftsConfig)
    config_path: Path | None = None


def _bundled_config_path() -> Path | None:
    """Path to config/firm.toml bundled with the source or .exe."""
    # PyInstaller sets sys._MEIPASS to the temp extraction dir
    base = Path(getattr(sys, "_MEIPASS", ""))
    if base.is_dir():
        p = base / "config" / "firm.toml"
        if p.exists():
            return p
    # Development: relative to this file → src/trust_generator/../../config/
    p = Path(__file__).resolve().parents[2] / "config" / "firm.toml"
    if p.exists():
        return p
    return None


def _appdata_config_path() -> Path:
    """Writable config location in the user's app data directory."""
    if sys.platform == "win32":
        base = Path.home() / "AppData" / "Local" / "trust-generator"
    else:
        base = Path.home() / ".config" / "trust-generator"
    return base / "firm.toml"


def _ensure_appdata_config() -> Path | None:
    """Copy bundled config to %APPDATA% if not already present."""
    target = _appdata_config_path()
    if target.exists():
        return target
    bundled = _bundled_config_path()
    if bundled is None:
        return None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(bundled, target)
        log.info("Copied default config to %s", target)
        return target
    except OSError as e:
        log.warning("Could not copy config to %s: %s", target, e)
        return None


def _find_config() -> Path | None:
    """Find the config file, preferring project-local over appdata."""
    # 1. Project-local (development)
    bundled = _bundled_config_path()
    if bundled is not None:
        return bundled
    # 2. User appdata (deployed)
    appdata = _appdata_config_path()
    if appdata.exists():
        return appdata
    # 3. Try to create appdata from bundled
    return _ensure_appdata_config()


def _parse_toml(path: Path) -> dict:
    """Parse a TOML file, returning empty dict on failure."""
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except Exception as e:
        log.warning("Failed to parse %s: %s — using defaults", path, e)
        return {}


def load_config() -> AppConfig:
    """Load application configuration. Never raises."""
    path = _find_config()
    if path is None:
        log.info("No config file found — using built-in defaults")
        return AppConfig()

    data = _parse_toml(path)
    if not data:
        return AppConfig(config_path=path)

    firm_data = data.get("firm", {})
    firm = FirmConfig(
        name=firm_data.get("name", FirmConfig.name),
        address_line1=firm_data.get("address_line1", FirmConfig.address_line1),
        address_line2=firm_data.get("address_line2", FirmConfig.address_line2),
        phone=firm_data.get("phone", FirmConfig.phone),
    )

    jur_data = data.get("jurisdiction", {})
    jurisdiction = JurisdictionConfig(
        default_state=jur_data.get("default_state", JurisdictionConfig.default_state),
        default_county=jur_data.get(
            "default_county", JurisdictionConfig.default_county
        ),
        trust_code_citation=jur_data.get(
            "trust_code_citation", JurisdictionConfig.trust_code_citation
        ),
    )

    drafts_data = data.get("drafts", {})
    drafts = DraftsConfig(
        auto_purge_days=drafts_data.get(
            "auto_purge_days", DraftsConfig.auto_purge_days
        ),
    )

    log.info("Loaded config from %s", path)
    return AppConfig(
        firm=firm, jurisdiction=jurisdiction, drafts=drafts, config_path=path
    )
