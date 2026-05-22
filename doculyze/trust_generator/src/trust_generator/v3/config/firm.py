"""TGv3 firm configuration models and loader.

Public surface (see ``__init__.py`` for re-exports):

* ``FirmConfig``       — the full typed configuration, composed of nested sections.
* ``load_firm_config`` — the single public loader entry point.
* ``FirmConfigError``  — raised on discovery, parse, or validation failure.

Construct ``FirmConfig`` directly only in tests. Production code uses the loader.
"""

from __future__ import annotations

import logging
import os
import re
import sys
import time
import tomllib
import warnings

logging.captureWarnings(True)
from collections.abc import Iterator, Mapping
from datetime import timedelta
from pathlib import Path
from typing import Any, Final, Literal, get_args

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    ValidationError,
    model_validator,
)
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from trust_generator.v3.schema import Address

DEFAULT_LOCAL_CONFIG_PATH: Final[Path] = Path("config/firm.toml")
ENV_VAR_LOCAL_CONFIG_PATH: Final[str] = "TGV3_FIRM_CONFIG"
ENV_VAR_SHARED_CONFIG_PATH: Final[str] = "TGV3_FIRM_SHARED_CONFIG"
ENV_PREFIX: Final[str] = "TGV3_"
CONVENTIONAL_SHARED_CONFIG_PATH: Final[Path] = Path(
    "~/Crosby and Crosby LLP/internal-applications - trust-generator"
    "/firm/config/firm.toml"
)
_USER_UPN_SENTINEL: Final[str] = "${user.upn}"

_SHARED_REQUIRED_SECTIONS: Final[frozenset[str]] = frozenset({
    "firm",
    "estate_thresholds",
    "diagnostics",
})


def deep_merge(
    shared: Mapping[str, Any], local: Mapping[str, Any]
) -> dict[str, Any]:
    result: dict[str, Any] = dict(shared)
    for key, local_value in local.items():
        if _is_empty(local_value):
            continue
        existing = result.get(key)
        if isinstance(existing, Mapping) and isinstance(local_value, Mapping):
            result[key] = deep_merge(existing, local_value)
        elif isinstance(existing, list) and isinstance(local_value, list):
            result[key] = [*existing, *local_value]
        else:
            result[key] = local_value
    return result


_EMPTY_LITERALS: Final[tuple[str, dict[str, Any], list[Any]]] = ("", {}, [])


def _is_empty(value: Any) -> bool:
    return value in _EMPTY_LITERALS


class FirmConfigError(Exception):
    """Raised when firm_config cannot be loaded or fails validation.

    The message quotes the originating pydantic / tomllib error for diagnostics.
    """


class SharedConfigStalenessWarning(UserWarning):
    """Emitted when the loader falls back to a cached shared config copy due to availability failure.

    Per spec §5.4.4 + D-7. Distinct from ``SharedConfigIntegrityWarning``
    so consumers can route the categories to different surfaces.
    Operational signal: shared was unavailable (file missing, OSError,
    or empty bytes consistent with OneDrive placeholder state); the
    cache is being used as a known-good fallback. Routine; the next
    successful sync resolves it.
    """


class SharedConfigIntegrityWarning(UserWarning):
    """Emitted when the loader falls back to a cached shared config copy due to integrity failure.

    Per spec §5.4.4.1 + D-7 + D-10. Distinct from
    ``SharedConfigStalenessWarning``. Operational signal: shared was
    reachable and non-empty but TOML-malformed; the cache is being
    used as a known-good fallback. Non-routine — the maintainer must
    repair the shared file before the cache is overwritten on a
    successful load.
    """


_ONBOARDING_ERROR_TEMPLATE: Final[str] = (
    "Shared firm.toml is unreachable and no cached copy exists.\n"
    "  Resolved shared path: {shared_path}\n"
    "  Expected cache path:  {cache}\n"
    "\n"
    "  This typically indicates first-time workstation setup before the "
    "shared file has synced. Verify TGV3_FIRM_SHARED_CONFIG points at the "
    "correct location, or contact the maintainer."
)


_EMPTY_SHARED_ERROR_TEMPLATE: Final[str] = (
    "Shared firm.toml at {shared_path} is unexpectedly empty and no "
    "cached copy exists to fall back to.\n"
    "  Resolved shared path: {shared_path}\n"
    "  Expected cache path:  {cache}\n"
    "\n"
    "  This typically indicates an in-progress OneDrive sync that has "
    "advertised the file but not yet propagated its content "
    "(OneDrive placeholder state). Retry "
    "shortly, or contact the maintainer if the condition persists past "
    "the firm's expected sync window."
)


_INTEGRITY_ERROR_TEMPLATE: Final[str] = (
    "Shared firm.toml at {shared_path} is malformed (TOML parse error: "
    "{integrity_reason}) and no cached copy exists to fall back to.\n"
    "  Resolved shared path: {shared_path}\n"
    "  Expected cache path:  {cache}\n"
    "\n"
    "  The maintainer must repair the shared file. This workstation has "
    "no cached copy to fall back to, so it cannot operate until the "
    "shared file is fixed and re-synced."
)


def _format_duration(seconds: float) -> str:
    """Format a duration in seconds as a human-readable string.

    Wraps ``datetime.timedelta`` for the ``__str__`` representation —
    ``'0:05:23'`` for short windows; ``'1 day, 2:15:40'`` for longer.
    Used in fallback warnings to surface cache age. Not a design
    surface — a one-line passthrough kept as a named helper so
    callers read intent rather than inline ``str(timedelta(...))``.
    """
    return str(timedelta(seconds=int(seconds)))


class Meta(BaseModel):
    """Forward-compatibility seam (firm-config-design §5.8).

    Uses ``extra='allow'`` so future v3.x additions or firm-side annotations
    under ``[meta]`` never trigger validation errors. Every other section in
    ``FirmConfig`` remains ``extra='forbid'`` to catch typos.
    """

    model_config = ConfigDict(extra="allow")

    schema_version: str | None = None
    comment: str | None = None


_US_ZIP_PATTERN = re.compile(r"^\d{5}(-\d{4})?$")


class FirmIdentity(BaseModel):
    """Firm identity and office location (spec §5.1).

    ``office_address`` reuses the v3 ``Address`` model as-is per amendment A-1.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    phone: str = Field(min_length=1)
    office_address: Address

    @model_validator(mode="after")
    def _validate_us_zip_format(self) -> FirmIdentity:
        # Spec §8 cross-field rule: ZIP format if state is US. The imported
        # Address stores country as a str with "US" default, and zip_code as
        # a free-form str. US addresses must match 5-digit or ZIP+4.
        if (
            self.office_address.country == "US"
            and self.office_address.zip_code
            and not _US_ZIP_PATTERN.match(self.office_address.zip_code)
        ):
            raise ValueError(
                "firm.office_address.zip_code must match US ZIP "
                "(NNNNN or NNNNN-NNNN) when country is US; "
                f"got {self.office_address.zip_code!r}"
            )
        return self


class Jurisdiction(BaseModel):
    """Legal/jurisdictional defaults (spec §5.2)."""

    model_config = ConfigDict(extra="forbid")

    default_state: str = "Illinois"
    default_county: str = "Winnebago"
    trust_code_citation: str = "Illinois Trust Code (760 ILCS 3/101, et seq.)"


class EstateThresholds(BaseModel):
    """IL estate-tax cliff parameters (spec §5.3).

    Illinois taxes the entire excess above threshold (cliff). The soft
    thresholds gate detail-collection prompts; the hard thresholds drive the
    blocking diagnostic; ``approaching_cliff_ratio`` sets the near-cliff warning.
    """

    model_config = ConfigDict(extra="forbid")

    single_soft: int = Field(default=3_000_000, gt=0)
    joint_soft: int = Field(default=6_000_000, gt=0)
    single_hard: int = Field(default=4_000_000, gt=0)
    joint_hard: int = Field(default=8_000_000, gt=0)
    approaching_cliff_ratio: float = Field(default=0.90, gt=0, lt=1)

    @model_validator(mode="after")
    def _validate_threshold_ordering(self) -> EstateThresholds:
        if self.single_soft >= self.single_hard:
            raise ValueError(
                "estate_thresholds.single_soft must be strictly less than single_hard"
            )
        if self.joint_soft >= self.joint_hard:
            raise ValueError(
                "estate_thresholds.joint_soft must be strictly less than joint_hard"
            )
        if self.single_soft > self.joint_soft:
            raise ValueError(
                "estate_thresholds.single_soft must be <= joint_soft"
            )
        if self.single_hard > self.joint_hard:
            raise ValueError(
                "estate_thresholds.single_hard must be <= joint_hard"
            )
        return self


class TrusteeCatalog(BaseModel):
    """Corporate trustee catalog (spec §5.4).

    ``db_path``, ``audit_log_dir``, and similar paths are resolved to absolute
    paths by the loader against the config file's parent directory. Relative
    paths here are pre-resolution placeholders.
    """

    # validate_assignment=True: the loader's _resolve_paths rewrites db_path
    # via attribute assignment after construction. Without this, a future
    # refactor that returns a non-Path value would silently corrupt the field.
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    db_path: Path = Path("./data/trustee_catalog.sqlite")
    radius_miles: int = Field(default=100, gt=0)
    refresh_days: int = Field(default=30, gt=0)
    # validate_default=True runs the string default through HttpUrl's validator
    # at model-construction time, so the stored value is an HttpUrl instance and
    # model_dump emits it cleanly (see plan-review concern S3).
    fdic_api_base: HttpUrl = Field(
        default="https://banks.data.fdic.gov/api",  # type: ignore[arg-type]
        validate_default=True,
    )
    fdic_request_timeout_s: int = Field(default=30, gt=0)


class Diagnostics(BaseModel):
    """Diagnostic enforcement (spec §5.5)."""

    # validate_assignment=True: the loader's _resolve_paths rewrites audit_log_dir
    # and rules_dir via attribute assignment after construction. See the paired
    # rationale on TrusteeCatalog.
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    default_restriction_level: Literal["info", "warning", "error"] = "error"
    allow_force_generation: bool = True
    audit_log_dir: Path = Path("./logs/audit")
    audit_log_rotation: Literal["monthly", "weekly", "daily"] = "monthly"
    rules_dir: Path = Path("./config/rules")


class Guardianship(BaseModel):
    """Guardianship policy default (spec §5.6)."""

    model_config = ConfigDict(extra="forbid")

    default_policy: Literal["DELEGATE_TO_TRUSTEES", "EXPLICIT_DESIGNATIONS"] = (
        "EXPLICIT_DESIGNATIONS"
    )


class Drafts(BaseModel):
    """Preserved from v2 (spec §5.7)."""

    model_config = ConfigDict(extra="forbid")

    auto_purge_days: int = Field(default=90, gt=0)


class User(BaseModel):
    """Per-workstation user identity (amendment A-5, 2026-04-24).

    The ``upn`` field is the M365 account prefix used for audit-log
    attribution and for post-parse substitution into ``diagnostics.audit_log_dir``
    (amendment A-6). Format validation is explicitly the onboarding workflow's
    responsibility and not enforced here; the load-time gate rejects empty or
    whitespace-only values because a blank UPN silently corrupts audit-log
    attribution and substituted paths (``str_strip_whitespace`` collapses
    ``"   "`` into ``""``, which then fails ``min_length=1``).
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    upn: str = Field(min_length=1)


class FirmConfig(BaseSettings):
    """Full typed firm configuration, composed of nested sections.

    See ``load_firm_config`` for loader semantics. Do not construct directly
    outside tests.
    """

    model_config = SettingsConfigDict(
        env_prefix=ENV_PREFIX,
        env_nested_delimiter="__",
        extra="forbid",
    )

    meta: Meta = Field(default_factory=Meta)
    user: User
    firm: FirmIdentity
    jurisdiction: Jurisdiction = Field(default_factory=Jurisdiction)
    estate_thresholds: EstateThresholds = Field(default_factory=EstateThresholds)
    trustee_catalog: TrusteeCatalog = Field(default_factory=TrusteeCatalog)
    diagnostics: Diagnostics = Field(default_factory=Diagnostics)
    guardianship: Guardianship = Field(default_factory=Guardianship)
    drafts: Drafts = Field(default_factory=Drafts)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Precedence (highest first): env vars (TGV3_*) > init kwargs (TOML
        # payload handed in by the loader) > file secrets > pydantic defaults.
        # Dotenv is dropped: we don't read .env files for firm config.
        return (env_settings, init_settings, file_secret_settings)


def _discover_local_path(arg: Path | None) -> Path:
    if arg is not None:
        return arg.expanduser().resolve(strict=False)
    env = os.environ.get(ENV_VAR_LOCAL_CONFIG_PATH)
    if env:
        return Path(env).expanduser().resolve(strict=False)
    return (Path.cwd() / "config" / "firm.toml").resolve(strict=False)


def _discover_shared_path(arg: Path | None) -> Path:
    if arg is not None:
        return arg.expanduser().resolve(strict=False)
    env = os.environ.get(ENV_VAR_SHARED_CONFIG_PATH)
    if env:
        return Path(env).expanduser().resolve(strict=False)
    return CONVENTIONAL_SHARED_CONFIG_PATH.expanduser().resolve(strict=False)


def _cache_path() -> Path:
    if sys.platform == "win32":
        local_appdata = os.environ.get("LOCALAPPDATA")
        if not local_appdata:
            raise FirmConfigError(
                "LOCALAPPDATA environment variable is not set; "
                "cannot determine cache directory."
            )
        cache_dir = Path(local_appdata) / "trust-generator"
    else:
        xdg = os.environ.get("XDG_CACHE_HOME")
        cache_dir = (
            Path(xdg) if xdg else Path.home() / ".cache"
        ) / "trust-generator"
    return cache_dir / "firm.shared.cache.toml"


def _write_cache(content: bytes) -> None:
    """Atomically replace the shared-config cache file with ``content``.

    Per spec §5.4.2: writes go to a tmp file in the same parent
    directory and ``os.replace`` swaps it into place, so the cache
    file is either fully old or fully new — never partially written.
    Write failures emit a ``UserWarning`` rather than raising, so a
    workstation that cannot update its cache (disk full, read-only
    filesystem, permission denied) still completes its load on the
    shared file's bytes; the next successful load retries.
    """
    target = _cache_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_bytes(content)
        os.replace(tmp, target)
    except OSError as exc:
        warnings.warn(
            f"failed to update shared firm.toml cache: {exc}",
            stacklevel=2,
        )


def _read_cache_or_raise(
    shared_path: Path,
    *,
    warning_class: type[UserWarning],
    warning_phrasing: str,
    no_cache_error_template: str,
    integrity_reason: str | None = None,
) -> tuple[bytes, dict[str, Any], bool]:
    """Read from the cache file or raise with a case-specific error template.

    Per spec §5.4.3 cases 2/3/4 fallback dispatch and §5.4.5 /
    §5.4.5.1 / §5.4.5.2 error variants. Keyword-only past
    ``shared_path`` so the integration plan's partial-sync re-route
    (spec §5.4.8.3) can call this directly with explicit category
    arguments. Returns ``(cache_bytes, parsed_cache_dict, used_cache=True)``;
    raises ``FirmConfigError`` if the cache is missing (using
    ``no_cache_error_template``) or fails to parse (corruption error).
    """
    cache = _cache_path()
    if not cache.exists():
        raise FirmConfigError(
            no_cache_error_template.format(
                shared_path=shared_path,
                cache=cache,
                integrity_reason=integrity_reason or "",
            )
        )
    content = cache.read_bytes()
    try:
        parsed = tomllib.loads(content.decode("utf-8-sig"))
    except tomllib.TOMLDecodeError as exc:
        raise FirmConfigError(
            f"shared firm.toml cache at {cache} is corrupt: {exc}"
        ) from exc
    age_seconds = time.time() - cache.stat().st_mtime
    age_str = _format_duration(age_seconds)
    warnings.warn(
        f"shared firm.toml at {shared_path} {warning_phrasing}; "
        f"falling back to cached copy ({age_str} old).\n"
        f"  source: {shared_path}\n  cache:  {cache}",
        category=warning_class,
        stacklevel=3,
    )
    return content, parsed, True


def _read_shared_with_fallback(
    shared_path: Path,
) -> tuple[bytes, dict[str, Any], bool]:
    """Read shared TOML, falling back to cache on any availability or integrity failure.

    Per spec §5.4.3 four-case dispatch and §5.4.7 helper-return-shape
    contract.

    Returns ``(bytes, parsed_dict, used_cache)``. The bytes are the
    verbatim source content (used by cycle 6 to gate cache writing).
    The parsed dict is the result of parsing those bytes, returned to
    avoid double-parse. The boolean indicates whether the fallback
    path was taken (``True`` = cache was consumed; ``False`` = shared
    was the source).

    Raises ``FirmConfigError`` when both shared and cache are
    unavailable, with case-specific message variants per §5.4.5 /
    §5.4.5.1 / §5.4.5.2.

    The 3-tuple return shape is contract-load-bearing per the
    spec §6.6 C1 plan-review finding — collapsing it to ``bytes``
    re-introduces a TOCTOU window in the integration plan's cache-
    write gate. Do not simplify.
    """
    # Case 2: file missing or unreadable → availability-fallback.
    if not shared_path.exists():
        return _read_cache_or_raise(
            shared_path,
            warning_class=SharedConfigStalenessWarning,
            warning_phrasing="unreachable",
            no_cache_error_template=_ONBOARDING_ERROR_TEMPLATE,
        )
    try:
        content = shared_path.read_bytes()
    except OSError:
        return _read_cache_or_raise(
            shared_path,
            warning_class=SharedConfigStalenessWarning,
            warning_phrasing="unreachable",
            no_cache_error_template=_ONBOARDING_ERROR_TEMPLATE,
        )

    # Case 3: empty bytes → availability-fallback (OneDrive placeholder).
    if not content:
        return _read_cache_or_raise(
            shared_path,
            warning_class=SharedConfigStalenessWarning,
            warning_phrasing="advertised but empty",
            no_cache_error_template=_EMPTY_SHARED_ERROR_TEMPLATE,
        )

    # Case 4: parse-fail → integrity-fallback.
    try:
        parsed = tomllib.loads(content.decode("utf-8-sig"))
    except tomllib.TOMLDecodeError as exc:
        return _read_cache_or_raise(
            shared_path,
            warning_class=SharedConfigIntegrityWarning,
            warning_phrasing=f"is malformed (TOML parse error: {exc})",
            no_cache_error_template=_INTEGRITY_ERROR_TEMPLATE,
            integrity_reason=str(exc),
        )

    # Case 1: happy path.
    return content, parsed, False


def _unwrap_optional(annotation: Any) -> tuple[Any, ...]:
    """Return the non-NoneType arguments of a Union/Optional annotation.

    For a bare (non-Union) annotation, returns a one-tuple containing that
    annotation unchanged. This lets callers iterate over possible types
    uniformly without special-casing Optional vs. plain annotations.
    """
    args = get_args(annotation)
    if not args:
        # Not a parameterised type — bare annotation, return as-is.
        return (annotation,)
    return tuple(a for a in args if a is not type(None))


def _enumerate_path_fields(
    schema: type[BaseModel],
    prefix: str = "",
) -> Iterator[str]:
    """Yield dotted keys for every Path-typed field in `schema`.

    Recurses into BaseModel-typed sub-models at any depth below the root,
    handling annotations of shape:

      - ``Path`` — qualifies; yield the dotted key.
      - ``Path | None`` / ``Optional[Path]`` — qualifies; yield the dotted key.
      - ``BaseModel`` subclass — recurse with an extended prefix.
      - ``BaseModel | None`` / ``Optional[<BaseModel>]`` — recurse.
      - Anything else (scalar, list, dict, …) — skip.

    Lists, dicts, and other parameterised containers are NOT recursed into per
    spec §5.3.7.5. A future ``list[Path]`` annotation would require a walker
    update and a ``test_enumerate_path_fields_yields_known_set`` refresh.
    """
    for field_name, field_info in schema.model_fields.items():
        annotation = field_info.annotation
        for t in _unwrap_optional(annotation):
            if t is Path:
                yield f"{prefix}{field_name}"
            elif isinstance(t, type) and issubclass(t, BaseModel):
                yield from _enumerate_path_fields(
                    t, prefix=f"{prefix}{field_name}."
                )


def _get_dotted(d: dict[str, Any], dotted_key: str) -> str | None:
    """Look up a dotted-key path in a nested dict; return None if absent.

    Returns the value as a `str` if present (TOML serialization always yields
    string for path-typed fields pre-validation). Returns None if any segment
    along the path is missing.
    """
    parts = dotted_key.split(".")
    current: Any = d
    for part in parts:
        if not isinstance(current, dict):
            return None
        if part not in current:
            return None
        current = current[part]
    return current if isinstance(current, str) else None


def _is_windows_absolute(value: str) -> bool:
    """Return True if `value` looks like a Windows absolute path.

    Matches drive-letter prefixes (`C:\\`, `D:\\`, etc.) and UNC prefixes
    (`\\\\`). Used by the shared-side relative-path validator to recognize
    cross-platform absolute paths since `os.path.isabs` is platform-dependent.
    """
    if len(value) >= 3 and value[1] == ":" and value[2] in ("\\", "/"):
        return True
    return value.startswith("\\\\")


def _validate_shared_paths_absolute(
    shared_dict: dict[str, Any],
    schema: type[BaseModel] = FirmConfig,
) -> None:
    """Reject relative paths declared in shared per spec §5.3.7.3-4.

    Iterates every Path-typed field in `schema` (via `_enumerate_path_fields`),
    looks up the corresponding value in `shared_dict` (via `_get_dotted`),
    and rejects values that are not absolute, tilde-prefixed, or Windows-
    style absolute. Raises `FirmConfigError` with the dotted field name
    and the rejected value in the message per spec §5.6.3.
    """
    for dotted_key in _enumerate_path_fields(schema):
        value = _get_dotted(shared_dict, dotted_key)
        if value is None:
            continue
        if not (value.startswith(("/", "~")) or _is_windows_absolute(value)):
            raise FirmConfigError(
                f"shared firm.toml field {dotted_key} must be absolute or "
                f"tilde-prefixed; got {value!r}. Relative paths in shared "
                f"have ambiguous semantics across workstations and are "
                f"not permitted."
            )


def _resolve_paths(cfg: FirmConfig, anchor: Path) -> FirmConfig:
    # Order per amendment A-6 (2026-04-24): substitute ${user.upn} → expanduser
    # → resolve-relative. Substitution is scoped to diagnostics.audit_log_dir
    # only (spec §11.2 limits the sentinel to that field).
    cfg.diagnostics.audit_log_dir = Path(
        str(cfg.diagnostics.audit_log_dir).replace(
            _USER_UPN_SENTINEL, cfg.user.upn
        )
    )

    # A-4 (2026-04-24): expanduser() runs before relative-resolve on every
    # Path-typed field, so a leading ~ resolves against the current user's
    # home directory. .resolve() on both branches keeps absolute and relative
    # paths symmetric — each reaches its canonical, symlink-resolved form so
    # downstream code compares paths consistently regardless of how they
    # were written in TOML.
    def _resolve(p: Path) -> Path:
        expanded = p.expanduser()
        return (
            expanded.resolve()
            if expanded.is_absolute()
            else (anchor / expanded).resolve()
        )

    cfg.trustee_catalog.db_path = _resolve(cfg.trustee_catalog.db_path)
    cfg.diagnostics.audit_log_dir = _resolve(cfg.diagnostics.audit_log_dir)
    cfg.diagnostics.rules_dir = _resolve(cfg.diagnostics.rules_dir)
    return cfg


def load_firm_config(
    local_path: Path | None = None,
    shared_path: Path | None = None,
) -> FirmConfig:
    """Load, validate, and return the firm configuration from two sources.

    Discovery order for the LOCAL TOML file (workstation-specific):

    1. ``local_path`` argument, if provided.
    2. ``$TGV3_FIRM_CONFIG`` environment variable, if set.
    3. ``./config/firm.toml`` relative to CWD.

    Discovery order for the SHARED TOML file (firm-wide, SharePoint-hosted):

    1. ``shared_path`` argument, if provided.
    2. ``$TGV3_FIRM_SHARED_CONFIG`` environment variable, if set.
    3. ``CONVENTIONAL_SHARED_CONFIG_PATH`` (OneDrive-synced library default).

    Merge precedence: shared file provides firm-wide policy; local file
    overrides per-workstation values. Empty TOML literals on the local
    side are treated as unset (per spec §5.3.3).

    Cache fallback: on shared-file unavailability or integrity failure,
    falls back to a local cache file at ``%LOCALAPPDATA%/trust-generator/...``
    (Windows) or ``${XDG_CACHE_HOME:-~/.cache}/trust-generator/...`` (POSIX),
    emitting ``SharedConfigStalenessWarning`` or ``SharedConfigIntegrityWarning``.

    Path resolution: ``${user.upn}`` substitution applies to
    ``diagnostics.audit_log_dir``; relative paths in LOCAL resolve against
    the local file's parent directory. Relative paths in SHARED are rejected.

    Raises:
        FirmConfigError: on missing local file, parse error, validation
            error, shared-side relative-path declaration, missing required
            shared section (cycle 13-2), or unrecoverable cache state.
    """
    resolved_local = _discover_local_path(local_path)
    resolved_shared = _discover_shared_path(shared_path)

    if not resolved_local.exists():
        raise FirmConfigError(
            f"local firm.toml not found at {resolved_local}"
        )

    shared_bytes, shared_dict, used_cache = _read_shared_with_fallback(
        resolved_shared
    )

    # Spec §5.4.8: shared completeness check. If shared was reachable
    # (used_cache is False) but is missing one of _SHARED_REQUIRED_SECTIONS,
    # route to integrity-fallback. Cache-side reads (used_cache already True)
    # cannot be partial in a recoverable way — a parsed cache missing
    # required sections is a corrupt cache, surfaced separately via
    # _read_cache_or_raise's existing corruption error path.
    if not used_cache:
        missing = _SHARED_REQUIRED_SECTIONS - set(shared_dict.keys())
        if missing:
            shared_bytes, shared_dict, used_cache = _read_cache_or_raise(
                resolved_shared,
                warning_class=SharedConfigIntegrityWarning,
                warning_phrasing=(
                    f"is missing required section(s) "
                    f"{sorted(missing)} (likely partial OneDrive sync)"
                ),
                no_cache_error_template=_INTEGRITY_ERROR_TEMPLATE,
                integrity_reason=(
                    f"missing required section(s): {sorted(missing)}"
                ),
            )

    _validate_shared_paths_absolute(shared_dict)

    local_bytes = resolved_local.read_bytes()
    try:
        local_dict = tomllib.loads(local_bytes.decode("utf-8-sig"))
    except tomllib.TOMLDecodeError as exc:
        raise FirmConfigError(
            f"local firm.toml at {resolved_local} is malformed: {exc}"
        ) from exc

    merged = deep_merge(shared_dict, local_dict)

    try:
        cfg = FirmConfig(**merged)
    except ValidationError as exc:
        raise FirmConfigError(str(exc)) from exc

    try:
        cfg = _resolve_paths(cfg, resolved_local.parent)
    except (OSError, RuntimeError) as exc:
        raise FirmConfigError(
            f"firm_config path resolution failed for "
            f"local={resolved_local}: {exc}"
        ) from exc

    if not used_cache:
        _write_cache(shared_bytes)

    return cfg
