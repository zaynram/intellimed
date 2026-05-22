"""Loader unit tests for trust_generator.v3.config.firm (spec §10.1)."""

from __future__ import annotations

import importlib
import logging
import os
import sys
import unittest.mock
from pathlib import Path

import pytest

from trust_generator.v3.config import (
    DEFAULT_LOCAL_CONFIG_PATH,
    ENV_PREFIX,
    ENV_VAR_LOCAL_CONFIG_PATH,
    ENV_VAR_SHARED_CONFIG_PATH,
    FirmConfig,
    FirmConfigError,
    SharedConfigIntegrityWarning,
    SharedConfigStalenessWarning,
    load_firm_config,
)

# Empty required-section placeholders. Spec §5.4.8 requires `[firm]`,
# `[estate_thresholds]`, and `[diagnostics]` to be present in shared (default
# field values are accepted; the check is for section presence, not content).
# Tests that need to populate these sections splice their content into these
# placeholders using `.replace()` rather than appending duplicate headers.
_REQUIRED_SECTION_PLACEHOLDERS = """
[estate_thresholds]
[diagnostics]
"""

WELL_FORMED_SHARED = """
[firm]
name = "Test Firm LLP"
phone = "(555) 555-5555"

[firm.office_address]
street = "1 Main St."
city = "Rockford"
state = "IL"
zip_code = "61114"

[jurisdiction]
default_state = "Illinois"
default_county = "Winnebago"
trust_code_citation = "Illinois Trust Code (760 ILCS 3/101, et seq.)"
""" + _REQUIRED_SECTION_PLACEHOLDERS


WELL_FORMED_LOCAL = """
[user]
upn = "testuser"
"""


MINIMAL_SHARED = """
[firm]
name = "Minimal LLP"
phone = "(555) 000-0000"

[firm.office_address]
street = "1 Way"
city = "City"
state = "XX"
zip_code = "00000"

[jurisdiction]
default_state = "Illinois"
default_county = "Winnebago"
trust_code_citation = "Illinois Trust Code"
"""


MINIMAL_LOCAL = """
[user]
upn = "testuser"
"""


def _write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith(ENV_PREFIX):
            monkeypatch.delenv(key, raising=False)


def test_constants_match_spec() -> None:
    assert DEFAULT_LOCAL_CONFIG_PATH == Path("config/firm.toml")
    assert ENV_VAR_LOCAL_CONFIG_PATH == "TGV3_FIRM_CONFIG"
    assert ENV_VAR_SHARED_CONFIG_PATH == "TGV3_FIRM_SHARED_CONFIG"
    assert ENV_PREFIX == "TGV3_"


# ─── Spec §5.5.5.5: captureWarnings at module import ─────────────────────────


def test_capture_warnings_called_at_import_time() -> None:
    """Spec §5.5.5.5: logging.captureWarnings(True) is called at module-import time.

    Imports a fresh copy of the firm module into a temporary namespace (without
    touching sys.modules) while patching logging.captureWarnings, then verifies
    the call was made. Using importlib.util.spec_from_file_location with a
    unique module name avoids replacing the live entry in sys.modules, so other
    tests' isinstance checks against the session-level FirmConfig class are not
    disrupted.
    """
    import importlib.util

    import trust_generator.v3.config.firm as firm_module

    spec = importlib.util.spec_from_file_location(
        "_firm_reload_probe", firm_module.__file__
    )
    assert spec is not None and spec.loader is not None
    fresh = importlib.util.module_from_spec(spec)
    with unittest.mock.patch.object(logging, "captureWarnings") as mock_cw:
        spec.loader.exec_module(fresh)  # type: ignore[union-attr]
        mock_cw.assert_called_once_with(True)


def test_happy_path_loads_expected_values(tmp_path: Path) -> None:
    local = _write(tmp_path / "local.toml", WELL_FORMED_LOCAL)
    shared = _write(tmp_path / "shared.toml", WELL_FORMED_SHARED)
    cfg = load_firm_config(local_path=local, shared_path=shared)
    assert isinstance(cfg, FirmConfig)
    assert cfg.firm.name == "Test Firm LLP"
    assert cfg.firm.phone == "(555) 555-5555"
    assert cfg.firm.office_address.zip_code == "61114"
    assert cfg.jurisdiction.default_state == "Illinois"


def test_minimal_file_yields_section_defaults(tmp_path: Path) -> None:
    local = _write(tmp_path / "local.toml", MINIMAL_LOCAL)
    shared = _write(tmp_path / "shared.toml", MINIMAL_SHARED)
    cfg = load_firm_config(local_path=local, shared_path=shared)
    assert cfg.estate_thresholds.single_soft == 3_000_000
    assert cfg.estate_thresholds.joint_soft == 6_000_000
    assert cfg.estate_thresholds.single_hard == 4_000_000
    assert cfg.estate_thresholds.joint_hard == 8_000_000
    assert cfg.estate_thresholds.approaching_cliff_ratio == pytest.approx(0.90)
    assert cfg.trustee_catalog.radius_miles == 100
    assert cfg.trustee_catalog.refresh_days == 30
    assert cfg.trustee_catalog.fdic_request_timeout_s == 30
    assert cfg.diagnostics.default_restriction_level == "error"
    assert cfg.diagnostics.allow_force_generation is True
    assert cfg.diagnostics.audit_log_rotation == "monthly"
    assert cfg.guardianship.default_policy == "EXPLICIT_DESIGNATIONS"
    assert cfg.drafts.auto_purge_days == 90
    assert cfg.meta.schema_version is None
    assert cfg.meta.comment is None


def test_missing_required_firm_name_raises(tmp_path: Path) -> None:
    broken_shared = WELL_FORMED_SHARED.replace('name = "Test Firm LLP"\n', "")
    local = _write(tmp_path / "local.toml", WELL_FORMED_LOCAL)
    shared = _write(tmp_path / "shared.toml", broken_shared)
    with pytest.raises(FirmConfigError) as exc:
        load_firm_config(local_path=local, shared_path=shared)
    assert "name" in str(exc.value)


def test_cross_field_hard_less_than_soft_raises(tmp_path: Path) -> None:
    bad_shared = WELL_FORMED_SHARED.replace(
        "[estate_thresholds]",
        """[estate_thresholds]
single_soft = 5_000_000
single_hard = 4_000_000
joint_soft = 6_000_000
joint_hard = 8_000_000
approaching_cliff_ratio = 0.9
""",
    )
    local = _write(tmp_path / "local.toml", WELL_FORMED_LOCAL)
    shared = _write(tmp_path / "shared.toml", bad_shared)
    with pytest.raises(FirmConfigError):
        load_firm_config(local_path=local, shared_path=shared)


def test_env_overlay_overrides_toml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    local = _write(tmp_path / "local.toml", WELL_FORMED_LOCAL)
    shared = _write(tmp_path / "shared.toml", WELL_FORMED_SHARED)
    monkeypatch.setenv("TGV3_ESTATE_THRESHOLDS__SINGLE_HARD", "5000000")
    cfg = load_firm_config(local_path=local, shared_path=shared)
    assert cfg.estate_thresholds.single_hard == 5_000_000


def test_relative_paths_resolve_against_local_parent(tmp_path: Path) -> None:
    local_dir = tmp_path / "nested"
    local_dir.mkdir()
    local_body = WELL_FORMED_LOCAL + """
[diagnostics]
audit_log_dir = "./relative/audit"
rules_dir = "./relative/rules"
"""
    local = _write(local_dir / "local.toml", local_body)
    shared = _write(tmp_path / "shared.toml", WELL_FORMED_SHARED)
    cfg = load_firm_config(local_path=local, shared_path=shared)
    assert cfg.diagnostics.audit_log_dir.is_absolute()
    assert cfg.diagnostics.audit_log_dir == (
        local_dir / "relative" / "audit"
    ).resolve()
    assert cfg.diagnostics.rules_dir == (
        local_dir / "relative" / "rules"
    ).resolve()


def test_absolute_paths_preserved(tmp_path: Path) -> None:
    abs_audit = tmp_path / "abs_audit"
    local_body = WELL_FORMED_LOCAL + f"""
[diagnostics]
audit_log_dir = "{abs_audit.as_posix()}"
"""
    local = _write(tmp_path / "local.toml", local_body)
    shared = _write(tmp_path / "shared.toml", WELL_FORMED_SHARED)
    cfg = load_firm_config(local_path=local, shared_path=shared)
    assert cfg.diagnostics.audit_log_dir == abs_audit.resolve()


def test_strict_extra_outside_meta_rejects_unknown_key(tmp_path: Path) -> None:
    # Inject the unknown key INSIDE the existing [firm] table to exercise
    # pydantic's extra="forbid". Appending a second [firm] header would raise
    # tomllib.TOMLDecodeError (duplicate table), which reaches the same
    # FirmConfigError wrapper but via the wrong failure mode.
    bad_shared = WELL_FORMED_SHARED.replace(
        'phone = "(555) 555-5555"',
        'phone = "(555) 555-5555"\nmystery_extra = "nope"',
    )
    local = _write(tmp_path / "local.toml", WELL_FORMED_LOCAL)
    shared = _write(tmp_path / "shared.toml", bad_shared)
    with pytest.raises(FirmConfigError) as exc:
        load_firm_config(local_path=local, shared_path=shared)
    # Sanity-check: the error names the offending key, proving it came from
    # extra="forbid" rather than a TOML parse failure.
    assert "mystery_extra" in str(exc.value)


def test_meta_accepts_unknown_keys(tmp_path: Path) -> None:
    shared_body = WELL_FORMED_SHARED + """
[meta]
schema_version = "1.0"
comment = "firm notes"
custom_key = "future forward-compat payload"
"""
    local = _write(tmp_path / "local.toml", WELL_FORMED_LOCAL)
    shared = _write(tmp_path / "shared.toml", shared_body)
    cfg = load_firm_config(local_path=local, shared_path=shared)
    assert cfg.meta.schema_version == "1.0"
    assert cfg.meta.comment == "firm notes"
    assert cfg.meta.model_extra is not None
    assert cfg.meta.model_extra["custom_key"] == "future forward-compat payload"


def test_discovery_explicit_path_wins_over_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    explicit_local = _write(tmp_path / "explicit.toml", WELL_FORMED_LOCAL)
    other_local = _write(
        tmp_path / "from_env.toml",
        WELL_FORMED_LOCAL.replace("testuser", "envuser"),
    )
    shared = _write(tmp_path / "shared.toml", WELL_FORMED_SHARED)
    monkeypatch.setenv("TGV3_FIRM_CONFIG", str(other_local))
    monkeypatch.setenv("TGV3_FIRM_SHARED_CONFIG", str(shared))
    cfg = load_firm_config(local_path=explicit_local)
    # Explicit local wins over env-pointed local; user.upn comes from explicit.
    assert cfg.user.upn == "testuser"


def test_discovery_env_wins_over_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    via_env_local = _write(tmp_path / "via_env.toml", WELL_FORMED_LOCAL)
    shared = _write(tmp_path / "shared.toml", WELL_FORMED_SHARED)
    monkeypatch.setenv("TGV3_FIRM_CONFIG", str(via_env_local))
    monkeypatch.setenv("TGV3_FIRM_SHARED_CONFIG", str(shared))
    cfg = load_firm_config()
    assert cfg.firm.name == "Test Firm LLP"


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FirmConfigError, match="local firm.toml not found"):
        load_firm_config(local_path=tmp_path / "does_not_exist.toml")


def test_approaching_cliff_ratio_bounds(tmp_path: Path) -> None:
    bad_shared = WELL_FORMED_SHARED.replace(
        "[estate_thresholds]",
        """[estate_thresholds]
single_soft = 3_000_000
single_hard = 4_000_000
joint_soft = 6_000_000
joint_hard = 8_000_000
approaching_cliff_ratio = 1.2
""",
    )
    local = _write(tmp_path / "local.toml", WELL_FORMED_LOCAL)
    shared = _write(tmp_path / "shared.toml", bad_shared)
    with pytest.raises(FirmConfigError):
        load_firm_config(local_path=local, shared_path=shared)


def test_us_zip_format_validator_accepts_canonical_shapes(tmp_path: Path) -> None:
    # NNNNN passes (already covered by WELL_FORMED). Verify NNNNN-NNNN too.
    plus_four_shared = WELL_FORMED_SHARED.replace(
        'zip_code = "61114"', 'zip_code = "61114-1234"'
    )
    local = _write(tmp_path / "local.toml", WELL_FORMED_LOCAL)
    shared = _write(tmp_path / "shared.toml", plus_four_shared)
    cfg = load_firm_config(local_path=local, shared_path=shared)
    assert cfg.firm.office_address.zip_code == "61114-1234"


def test_us_zip_format_validator_rejects_malformed(tmp_path: Path) -> None:
    bad_shared = WELL_FORMED_SHARED.replace(
        'zip_code = "61114"', 'zip_code = "abcde"'
    )
    local = _write(tmp_path / "local.toml", WELL_FORMED_LOCAL)
    shared = _write(tmp_path / "shared.toml", bad_shared)
    with pytest.raises(FirmConfigError) as exc:
        load_firm_config(local_path=local, shared_path=shared)
    assert "zip_code" in str(exc.value)


def test_us_zip_format_validator_skipped_for_non_us_country(tmp_path: Path) -> None:
    # A non-US country code bypasses the US ZIP pattern check; local postal
    # codes (e.g., "SW1A 1AA") are allowed through.
    non_us_shared = WELL_FORMED_SHARED.replace(
        'zip_code = "61114"',
        'zip_code = "SW1A 1AA"\n  country = "GB"',
    )
    local = _write(tmp_path / "local.toml", WELL_FORMED_LOCAL)
    shared = _write(tmp_path / "shared.toml", non_us_shared)
    cfg = load_firm_config(local_path=local, shared_path=shared)
    assert cfg.firm.office_address.zip_code == "SW1A 1AA"
    assert cfg.firm.office_address.country == "GB"


def test_fdic_api_base_must_be_http_url(tmp_path: Path) -> None:
    bad_shared = WELL_FORMED_SHARED + """
[trustee_catalog]
fdic_api_base = "not-a-url"
"""
    local = _write(tmp_path / "local.toml", WELL_FORMED_LOCAL)
    shared = _write(tmp_path / "shared.toml", bad_shared)
    with pytest.raises(FirmConfigError):
        load_firm_config(local_path=local, shared_path=shared)


# ---------------------------------------------------------------------------
# A-4 / A-5 / A-6: [user] section, tilde expansion, ${user.upn} substitution
# ---------------------------------------------------------------------------


def test_user_upn_is_loaded(tmp_path: Path) -> None:
    local = _write(tmp_path / "local.toml", WELL_FORMED_LOCAL)
    shared = _write(tmp_path / "shared.toml", WELL_FORMED_SHARED)
    cfg = load_firm_config(local_path=local, shared_path=shared)
    assert cfg.user.upn == "testuser"


def test_missing_user_section_raises(tmp_path: Path) -> None:
    # A-5: [user] is required; removing it must fail loading.
    no_user_local = WELL_FORMED_LOCAL.replace('[user]\nupn = "testuser"\n', "")
    local = _write(tmp_path / "local.toml", no_user_local)
    shared = _write(tmp_path / "shared.toml", WELL_FORMED_SHARED)
    with pytest.raises(FirmConfigError) as exc:
        load_firm_config(local_path=local, shared_path=shared)
    assert "user" in str(exc.value).lower()


def test_empty_user_upn_rejected(tmp_path: Path) -> None:
    # A-5: upn must be non-empty. An empty string fails Pydantic validation.
    empty_local = WELL_FORMED_LOCAL.replace('upn = "testuser"', 'upn = ""')
    local = _write(tmp_path / "local.toml", empty_local)
    shared = _write(tmp_path / "shared.toml", WELL_FORMED_SHARED)
    with pytest.raises(FirmConfigError) as exc:
        load_firm_config(local_path=local, shared_path=shared)
    assert "upn" in str(exc.value).lower()


def test_whitespace_only_user_upn_rejected(tmp_path: Path) -> None:
    # A-5: str_strip_whitespace=True on User strips leading/trailing spaces
    # before min_length=1 applies, so "   " collapses to "" and fails
    # validation. Prevents silent attribution corruption in the audit log.
    blank_local = WELL_FORMED_LOCAL.replace('upn = "testuser"', 'upn = "   "')
    local = _write(tmp_path / "local.toml", blank_local)
    shared = _write(tmp_path / "shared.toml", WELL_FORMED_SHARED)
    with pytest.raises(FirmConfigError) as exc:
        load_firm_config(local_path=local, shared_path=shared)
    assert "upn" in str(exc.value).lower()


def test_tilde_in_audit_log_dir_expands_to_home(tmp_path: Path) -> None:
    # A-4: Path fields with leading ~ resolve against the user's home dir.
    local_body = WELL_FORMED_LOCAL + """
[diagnostics]
audit_log_dir = "~/audit-logs"
"""
    local = _write(tmp_path / "local.toml", local_body)
    shared = _write(tmp_path / "shared.toml", WELL_FORMED_SHARED)
    cfg = load_firm_config(local_path=local, shared_path=shared)
    assert cfg.diagnostics.audit_log_dir == (Path.home() / "audit-logs").resolve()


def test_tilde_expansion_applies_to_all_path_fields(tmp_path: Path) -> None:
    # A-4 wording: "all Path-typed fields" get expanduser() — not just
    # audit_log_dir. Pins rules_dir and trustee_catalog.db_path behavior.
    local_body = WELL_FORMED_LOCAL + """
[diagnostics]
audit_log_dir = "~/audit"
rules_dir = "~/rules"

[trustee_catalog]
db_path = "~/tc.sqlite"
"""
    local = _write(tmp_path / "local.toml", local_body)
    shared = _write(tmp_path / "shared.toml", WELL_FORMED_SHARED)
    cfg = load_firm_config(local_path=local, shared_path=shared)
    assert cfg.diagnostics.audit_log_dir == (Path.home() / "audit").resolve()
    assert cfg.diagnostics.rules_dir == (Path.home() / "rules").resolve()
    assert cfg.trustee_catalog.db_path == (Path.home() / "tc.sqlite").resolve()


def test_user_upn_substitution_in_audit_log_dir(tmp_path: Path) -> None:
    # A-6: ${user.upn} in audit_log_dir is replaced with the validated upn
    # value before expanduser + relative-resolve.
    local_body = WELL_FORMED_LOCAL + """
[diagnostics]
audit_log_dir = "~/firm-logs/users/${user.upn}/logs"
"""
    local = _write(tmp_path / "local.toml", local_body)
    shared = _write(tmp_path / "shared.toml", WELL_FORMED_SHARED)
    cfg = load_firm_config(local_path=local, shared_path=shared)
    expected = (Path.home() / "firm-logs" / "users" / "testuser" / "logs").resolve()
    assert cfg.diagnostics.audit_log_dir == expected


def test_user_upn_substitution_scoped_to_audit_log_dir_only(tmp_path: Path) -> None:
    # Spec §11.2: substitution is scoped to diagnostics.audit_log_dir. Other
    # Path fields must NOT receive the ${user.upn} replacement; the literal
    # sentinel survives into the resolved path. Asserting both halves of the
    # contract — sentinel present AND upn value absent — catches a regression
    # that accidentally substitutes across all Path fields.
    local_body = WELL_FORMED_LOCAL + """
[diagnostics]
audit_log_dir = "./audit"
rules_dir = "./rules/${user.upn}"

[trustee_catalog]
db_path = "./db/${user.upn}/cat.sqlite"
"""
    local = _write(tmp_path / "local.toml", local_body)
    shared = _write(tmp_path / "shared.toml", WELL_FORMED_SHARED)
    cfg = load_firm_config(local_path=local, shared_path=shared)
    assert "${user.upn}" in str(cfg.diagnostics.rules_dir)
    assert "testuser" not in str(cfg.diagnostics.rules_dir)
    assert "${user.upn}" in str(cfg.trustee_catalog.db_path)
    assert "testuser" not in str(cfg.trustee_catalog.db_path)


def test_path_resolution_order_substitute_then_expand_then_resolve(
    tmp_path: Path,
) -> None:
    # A-6: resolution order is substitute(${user.upn}) → expanduser → resolve.
    # Using a relative path WITH the sentinel that sits under a ~ prefix
    # exercises all three steps in order.
    local_body = WELL_FORMED_LOCAL.replace(
        'upn = "testuser"',
        'upn = "orderuser"',
    ) + """
[diagnostics]
audit_log_dir = "~/tg/users/${user.upn}/audit"
"""
    local = _write(tmp_path / "local.toml", local_body)
    shared = _write(tmp_path / "shared.toml", WELL_FORMED_SHARED)
    cfg = load_firm_config(local_path=local, shared_path=shared)
    expected = (Path.home() / "tg" / "users" / "orderuser" / "audit").resolve()
    assert cfg.diagnostics.audit_log_dir == expected


def test_absolute_audit_log_dir_still_gets_substitution(tmp_path: Path) -> None:
    # An absolute audit_log_dir with the sentinel still gets substitution.
    # Tilde expansion is a no-op on an absolute path; relative-resolve is a
    # no-op on an absolute path; substitution runs first and is independent
    # of the other two transforms.
    abs_base = tmp_path / "firm-logs"
    local_body = WELL_FORMED_LOCAL + f"""
[diagnostics]
audit_log_dir = "{abs_base.as_posix()}/users/${{user.upn}}/logs"
"""
    local = _write(tmp_path / "local.toml", local_body)
    shared = _write(tmp_path / "shared.toml", WELL_FORMED_SHARED)
    cfg = load_firm_config(local_path=local, shared_path=shared)
    expected = (abs_base / "users" / "testuser" / "logs").resolve()
    assert cfg.diagnostics.audit_log_dir == expected


@pytest.mark.parametrize(
    "exc_type",
    [OSError, RuntimeError],
    ids=["oserror", "runtimeerror"],
)
def test_path_resolution_errors_wrapped_as_firm_config_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    exc_type: type[Exception],
) -> None:
    # Spec §7 promises FirmConfigError for any load-time failure. Path.expanduser()
    # raises RuntimeError when the home directory is undeterminable; Path.resolve()
    # can raise OSError on pathological symlink/permission states. Both must
    # surface through the FirmConfigError contract, not as raw stdlib exceptions.
    local = _write(tmp_path / "local.toml", WELL_FORMED_LOCAL)
    shared = _write(tmp_path / "shared.toml", WELL_FORMED_SHARED)

    def boom(_cfg: object, _anchor: object) -> object:
        raise exc_type("path-resolution-boom")

    monkeypatch.setattr(
        "trust_generator.v3.config.firm._resolve_paths", boom
    )

    with pytest.raises(FirmConfigError, match="path resolution failed") as exc:
        load_firm_config(local_path=local, shared_path=shared)
    assert isinstance(exc.value.__cause__, exc_type)


# ─── Cycle 1: deep_merge (foundation plan §6.2) ────────────────────────────

from trust_generator.v3.config.firm import deep_merge


def test_deep_merge_both_empty_returns_empty() -> None:
    assert deep_merge({}, {}) == {}


def test_deep_merge_shared_only_passes_through() -> None:
    shared = {"a": 1, "section": {"b": 2}}
    assert deep_merge(shared, {}) == {"a": 1, "section": {"b": 2}}


def test_deep_merge_local_only_passes_through() -> None:
    local = {"a": 1, "section": {"b": 2}}
    assert deep_merge({}, local) == {"a": 1, "section": {"b": 2}}


def test_deep_merge_scalar_overlap_local_wins() -> None:
    assert deep_merge({"k": "shared"}, {"k": "local"}) == {"k": "local"}


def test_deep_merge_table_overlap_recurses() -> None:
    shared = {"section": {"a": 1, "b": 2}}
    local = {"section": {"b": 20, "c": 3}}
    assert deep_merge(shared, local) == {"section": {"a": 1, "b": 20, "c": 3}}


def test_deep_merge_list_overlap_extends_shared_first() -> None:
    shared = {"items": ["a", "b"]}
    local = {"items": ["c", "a"]}
    assert deep_merge(shared, local) == {"items": ["a", "b", "c", "a"]}


def test_deep_merge_empty_string_treated_as_unset() -> None:
    assert deep_merge({"k": "value"}, {"k": ""}) == {"k": "value"}


def test_deep_merge_empty_table_treated_as_no_op() -> None:
    shared = {"section": {"k": 1}}
    local = {"section": {}}
    assert deep_merge(shared, local) == {"section": {"k": 1}}


def test_deep_merge_inputs_not_mutated() -> None:
    shared = {"a": 1, "section": {"b": 2}}
    local = {"a": 10, "section": {"c": 3}}
    shared_snapshot = {"a": 1, "section": {"b": 2}}
    local_snapshot = {"a": 10, "section": {"c": 3}}
    deep_merge(shared, local)
    assert shared == shared_snapshot
    assert local == local_snapshot


# ─── Cycle 2: Discovery functions (foundation plan §6.3) ───────────────────

from trust_generator.v3.config.firm import (
    CONVENTIONAL_SHARED_CONFIG_PATH,
    _discover_local_path,
    _discover_shared_path,
)


def test_local_explicit_arg_wins(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("TGV3_FIRM_CONFIG", str(tmp_path / "from_env.toml"))
    explicit = tmp_path / "from_arg.toml"
    assert _discover_local_path(explicit) == explicit.resolve()


def test_local_env_var_used_when_no_arg(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    via_env = tmp_path / "from_env.toml"
    monkeypatch.setenv("TGV3_FIRM_CONFIG", str(via_env))
    assert _discover_local_path(None) == via_env.resolve()


def test_local_convention_used_when_no_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    assert _discover_local_path(None) == (
        tmp_path / "config" / "firm.toml"
    ).resolve()


def test_shared_explicit_arg_wins(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("TGV3_FIRM_SHARED_CONFIG", str(tmp_path / "env.toml"))
    explicit = tmp_path / "shared.toml"
    assert _discover_shared_path(explicit) == explicit.resolve()


def test_shared_env_var_used_when_no_arg(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    via_env = tmp_path / "shared_env.toml"
    monkeypatch.setenv("TGV3_FIRM_SHARED_CONFIG", str(via_env))
    assert _discover_shared_path(None) == via_env.resolve()


def test_shared_convention_uses_path_constant() -> None:
    assert _discover_shared_path(None) == (
        CONVENTIONAL_SHARED_CONFIG_PATH.expanduser().resolve()
    )


def test_shared_path_expanduser_applied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TGV3_FIRM_SHARED_CONFIG", "~/my-shared.toml")
    assert _discover_shared_path(None) == (
        Path.home() / "my-shared.toml"
    ).resolve()


def test_local_and_shared_independent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    explicit_local = tmp_path / "local.toml"
    monkeypatch.setenv("TGV3_FIRM_SHARED_CONFIG", str(tmp_path / "shared.toml"))
    assert _discover_local_path(explicit_local) == explicit_local.resolve()
    assert _discover_shared_path(None) == (tmp_path / "shared.toml").resolve()


# ─── Cycle 3: _cache_path (foundation plan §6.4) ───────────────────────────

from trust_generator.v3.config.firm import _cache_path


def test_windows_uses_localappdata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert _cache_path() == (
        tmp_path / "trust-generator" / "firm.shared.cache.toml"
    )


def test_windows_missing_localappdata_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    with pytest.raises(FirmConfigError):
        _cache_path()


def test_posix_uses_xdg_cache_home_when_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert _cache_path() == (
        tmp_path / "trust-generator" / "firm.shared.cache.toml"
    )


def test_posix_falls_back_to_home_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    expected = (
        Path.home() / ".cache" / "trust-generator" / "firm.shared.cache.toml"
    )
    assert _cache_path() == expected


# ─── Cycle 13-1: load_firm_config two-source integration (spec §6.7) ─────────


def test_load_with_explicit_paths_succeeds(tmp_path: Path) -> None:
    """Spec §6.7 test 1: explicit local_path + shared_path returns merged FirmConfig."""
    local = _write(tmp_path / "local.toml", WELL_FORMED_LOCAL)
    shared = _write(tmp_path / "shared.toml", WELL_FORMED_SHARED)
    cfg = load_firm_config(local_path=local, shared_path=shared)
    assert cfg.firm.name == "Test Firm LLP"  # from shared
    assert cfg.user.upn == "testuser"  # from local


def test_load_writes_cache_on_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Spec §6.7 test 2: successful load with reachable shared writes the cache."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    local = _write(tmp_path / "local.toml", WELL_FORMED_LOCAL)
    shared = _write(tmp_path / "shared.toml", WELL_FORMED_SHARED)
    load_firm_config(local_path=local, shared_path=shared)
    cache_file = (
        tmp_path / "cache" / "trust-generator" / "firm.shared.cache.toml"
    )
    assert cache_file.exists()
    assert cache_file.read_bytes() == shared.read_bytes()


def test_load_default_paths_use_discovery_chains(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Spec §6.7 test 3: no-args call uses both env-var discovery chains independently."""
    local = _write(tmp_path / "via_local_env.toml", WELL_FORMED_LOCAL)
    shared = _write(tmp_path / "via_shared_env.toml", WELL_FORMED_SHARED)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("TGV3_FIRM_CONFIG", str(local))
    monkeypatch.setenv("TGV3_FIRM_SHARED_CONFIG", str(shared))
    cfg = load_firm_config()
    assert cfg.user.upn == "testuser"
    assert cfg.firm.name == "Test Firm LLP"


def test_load_keyword_path_alias_not_supported(tmp_path: Path) -> None:
    """Spec §6.7 test 4: legacy `path=` kwarg raises TypeError per §5.6.4 no-shim."""
    with pytest.raises(TypeError):
        load_firm_config(path=tmp_path / "firm.toml")  # type: ignore[call-arg]


def test_load_uses_cache_when_shared_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Spec §6.7 test 5: missing shared + present cache emits one staleness warning."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    cache_dir = tmp_path / "cache" / "trust-generator"
    cache_dir.mkdir(parents=True)
    (cache_dir / "firm.shared.cache.toml").write_bytes(WELL_FORMED_SHARED.encode())
    local = _write(tmp_path / "local.toml", WELL_FORMED_LOCAL)
    missing_shared = tmp_path / "does-not-exist.toml"
    with pytest.warns(SharedConfigStalenessWarning) as captured:
        cfg = load_firm_config(local_path=local, shared_path=missing_shared)
    assert cfg.firm.name == "Test Firm LLP"
    assert len(captured) == 1


def test_load_no_cache_write_on_availability_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Spec §6.7 test 6: case-2/3 fallback does not modify cache mtime."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    cache_dir = tmp_path / "cache" / "trust-generator"
    cache_dir.mkdir(parents=True)
    cache_file = cache_dir / "firm.shared.cache.toml"
    cache_file.write_bytes(WELL_FORMED_SHARED.encode())
    initial_mtime = cache_file.stat().st_mtime
    local = _write(tmp_path / "local.toml", WELL_FORMED_LOCAL)
    missing_shared = tmp_path / "does-not-exist.toml"
    with pytest.warns(SharedConfigStalenessWarning):
        load_firm_config(local_path=local, shared_path=missing_shared)
    assert cache_file.stat().st_mtime == initial_mtime


def test_load_no_cache_write_on_integrity_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Spec §6.7 test 7 (C1-fix regression pin): malformed shared + cache used does not write cache."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    cache_dir = tmp_path / "cache" / "trust-generator"
    cache_dir.mkdir(parents=True)
    cache_file = cache_dir / "firm.shared.cache.toml"
    cache_file.write_bytes(WELL_FORMED_SHARED.encode())
    initial_mtime = cache_file.stat().st_mtime
    local = _write(tmp_path / "local.toml", WELL_FORMED_LOCAL)
    malformed_shared = _write(tmp_path / "shared.toml", "not = valid = toml = at = all")
    with pytest.warns(SharedConfigIntegrityWarning):
        load_firm_config(local_path=local, shared_path=malformed_shared)
    assert cache_file.stat().st_mtime == initial_mtime


def test_load_validation_error_does_not_write_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Spec §6.7 test 8: validation failure on merged dict skips cache write (D-11)."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    cache_dir = tmp_path / "cache" / "trust-generator"
    cache_dir.mkdir(parents=True)
    cache_file = cache_dir / "firm.shared.cache.toml"
    cache_file.write_bytes(b"# pre-existing cache content\n")
    initial_mtime = cache_file.stat().st_mtime
    local = _write(tmp_path / "local.toml", WELL_FORMED_LOCAL)
    bad_shared = _write(
        tmp_path / "shared.toml",
        WELL_FORMED_SHARED.replace(
            "[estate_thresholds]",
            "[estate_thresholds]\nsingle_soft = -1",
        ),
    )
    with pytest.raises(FirmConfigError):
        load_firm_config(local_path=local, shared_path=bad_shared)
    assert cache_file.stat().st_mtime == initial_mtime


def test_relative_paths_resolve_against_local_parent_new(tmp_path: Path) -> None:
    """Spec §6.7 test 9: confirms anchor identity is resolved_local.parent.

    NOTE: this test deliberately differs from the renamed migrated test
    (test_relative_paths_resolve_against_local_parent) by using a deeper
    nested directory structure to make the local-parent vs CWD difference
    unambiguous in the assertion path.
    """
    nested = tmp_path / "nested" / "deep"
    nested.mkdir(parents=True)
    local_body = WELL_FORMED_LOCAL + """
[diagnostics]
audit_log_dir = "./relative/audit"
"""
    local = _write(nested / "local.toml", local_body)
    shared = _write(tmp_path / "shared.toml", WELL_FORMED_SHARED)
    cfg = load_firm_config(local_path=local, shared_path=shared)
    expected = (nested / "relative" / "audit").resolve()
    assert cfg.diagnostics.audit_log_dir == expected


@pytest.mark.parametrize(
    "field_path",
    [
        "trustee_catalog.db_path",
        "diagnostics.audit_log_dir",
        "diagnostics.rules_dir",
    ],
)
def test_shared_side_relative_path_rejected(
    tmp_path: Path, field_path: str
) -> None:
    """Spec §6.7 test 10: relative path declared in SHARED raises with field name + value."""
    section, field = field_path.split(".")
    # If the section is already a required-section placeholder in
    # WELL_FORMED_SHARED, splice into it to avoid duplicate-table TOML
    # errors. Otherwise append a new section.
    section_block = f"[{section}]\n{field} = \"./relative/path\""
    if f"[{section}]" in WELL_FORMED_SHARED:
        shared_body = WELL_FORMED_SHARED.replace(f"[{section}]", section_block)
    else:
        shared_body = WELL_FORMED_SHARED + "\n" + section_block + "\n"
    local = _write(tmp_path / "local.toml", WELL_FORMED_LOCAL)
    shared = _write(tmp_path / "shared.toml", shared_body)
    with pytest.raises(FirmConfigError, match=field_path) as exc_info:
        load_firm_config(local_path=local, shared_path=shared)
    assert "./relative/path" in str(exc_info.value)


def test_user_upn_substitution_uses_post_merge_user_value(tmp_path: Path) -> None:
    """Spec §6.7 test 11: ${user.upn} substitution happens after merge."""
    shared_body = WELL_FORMED_SHARED.replace(
        "[diagnostics]",
        '[diagnostics]\naudit_log_dir = "~/firm-logs/users/${user.upn}/logs"',
    )
    local = _write(tmp_path / "local.toml", WELL_FORMED_LOCAL)
    shared = _write(tmp_path / "shared.toml", shared_body)
    cfg = load_firm_config(local_path=local, shared_path=shared)
    expected = (Path.home() / "firm-logs" / "users" / "testuser" / "logs").resolve()
    assert cfg.diagnostics.audit_log_dir == expected


# ─── Cycle 13-2: Shared completeness check (spec §5.4.8) ─────────────────────


# A "fully-populated" shared body that has all three required sections;
# parametrized tests strip one section at a time to construct a partial-sync
# shared file (parses successfully but is missing one of the firm-policy
# sections that paralegals expect to be present).
_FULLY_POPULATED_SHARED = WELL_FORMED_SHARED.replace(
    "[estate_thresholds]",
    """[estate_thresholds]
single_soft = 3_000_000
joint_soft = 6_000_000
single_hard = 4_000_000
joint_hard = 8_000_000
approaching_cliff_ratio = 0.90
""",
).replace(
    "[diagnostics]",
    '[diagnostics]\ndefault_restriction_level = "warning"',
)


def _strip_section(toml_text: str, section: str) -> str:
    """Remove the named top-level section (and any nested sub-tables) from `toml_text`.

    Naive but adequate for fixture surgery: strips header lines that match
    `[section]` or `[section.<...>]` and every line up to the next top-level
    header (or EOF). Used by the partial-sync test to construct a shared
    file missing exactly one of `_SHARED_REQUIRED_SECTIONS`.
    """
    out: list[str] = []
    skipping = False
    for line in toml_text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("["):
            header = stripped[1:].split("]", 1)[0]
            if header == section or header.startswith(f"{section}."):
                skipping = True
                continue
            skipping = False
        if not skipping:
            out.append(line)
    return "".join(out)


@pytest.mark.parametrize(
    "missing_section",
    ["firm", "estate_thresholds", "diagnostics"],
)
def test_load_partial_shared_falls_back_to_cache_with_integrity_warning(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, missing_section: str
) -> None:
    """Spec §6.7 test 12: partial shared (parses but missing required section) → cache + integrity warning."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    cache_dir = tmp_path / "cache" / "trust-generator"
    cache_dir.mkdir(parents=True)
    cache_file = cache_dir / "firm.shared.cache.toml"
    cache_file.write_bytes(_FULLY_POPULATED_SHARED.encode())
    initial_mtime = cache_file.stat().st_mtime

    partial_shared_text = _strip_section(
        _FULLY_POPULATED_SHARED, missing_section
    )

    local = _write(tmp_path / "local.toml", WELL_FORMED_LOCAL)
    shared = _write(tmp_path / "shared.toml", partial_shared_text)
    with pytest.warns(SharedConfigIntegrityWarning) as captured:
        cfg = load_firm_config(local_path=local, shared_path=shared)
    assert len(captured) == 1
    assert missing_section in str(captured[0].message)
    # Cache used for actual config (cache had the fully-populated shared).
    assert cfg.firm.name == "Test Firm LLP"
    # Cache mtime unchanged (no cache write on integrity-fallback).
    assert cache_file.stat().st_mtime == initial_mtime


def test_load_partial_shared_no_cache_raises_with_missing_sections_message(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Spec §6.7 test 13: partial shared + no cache raises with section list in message."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "no-cache"))
    # MINIMAL_SHARED has [firm] and [jurisdiction] but lacks
    # [estate_thresholds] and [diagnostics] — both are in
    # _SHARED_REQUIRED_SECTIONS.
    local = _write(tmp_path / "local.toml", WELL_FORMED_LOCAL)
    shared = _write(tmp_path / "shared.toml", MINIMAL_SHARED)
    with pytest.raises(FirmConfigError, match="missing required section") as exc_info:
        load_firm_config(local_path=local, shared_path=shared)
    msg = str(exc_info.value)
    assert "estate_thresholds" in msg or "diagnostics" in msg


# ─── Task 13-3: Walker coverage tripwire (spec §5.3.7.5) ─────────────────────


def test_enumerate_path_fields_yields_known_set() -> None:
    """Spec §6.7 test 14: walker coverage is pinned at the known three Path fields.

    Equality, not subset: a regression that accidentally yields fewer fields
    silently leaves the shared-side relative-path prohibition unenforced for
    the missed fields. A schema extension that adds a new Path field also
    trips this test (caught at unit level, not in production).
    """
    from trust_generator.v3.config.firm import _enumerate_path_fields

    assert set(_enumerate_path_fields(FirmConfig)) == {
        "trustee_catalog.db_path",
        "diagnostics.audit_log_dir",
        "diagnostics.rules_dir",
    }


def test_enumerate_path_fields_recurses_depth_two() -> None:
    """Chore #26: recursive walker yields Path fields at depth-2 sub-model nesting.

    Constructs a minimal test-only schema:
      OuterModel
        └── mid: MidModel            (depth 1 — BaseModel sub-model)
              └── deep_path: Path    (depth 2 — the field under test)
              └── label: str         (depth 2 — non-Path, must NOT appear)

    The old one-level-deep implementation would recurse into OuterModel's fields,
    find `mid` is a BaseModel, but stop there without recursing into MidModel.
    The new recursive implementation must yield "mid.deep_path" and nothing else.
    """
    from pydantic import BaseModel as _BaseModel

    from trust_generator.v3.config.firm import _enumerate_path_fields

    class _MidModel(_BaseModel):
        deep_path: Path = Path("./deep")
        label: str = "x"

    class _OuterModel(_BaseModel):
        mid: _MidModel = _MidModel()
        top_str: str = "y"

    assert set(_enumerate_path_fields(_OuterModel)) == {"mid.deep_path"}
