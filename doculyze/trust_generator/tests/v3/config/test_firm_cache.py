"""Cycle 4 + cycle 5 tests — shared firm_config cache writer and read-with-fallback helper.

Per spec §5.4.2 (atomic cache write) and §5.4.3-§5.4.5 (four-case
fallback decision tree), §5.4.4 (staleness warning), §5.4.4.1
(integrity warning), §5.4.7 (helper-return-shape contract: tuple of
bytes, parsed dict, used_cache boolean).

Tests in this module run with `XDG_CACHE_HOME` redirected to a
per-test ``tmp_path`` via the autouse fixture below, so every test
gets an isolated cache directory and the cycle-3 ``_cache_path()``
helper resolves predictably under POSIX. Windows-platform branches
of ``_cache_path()`` are covered in the foundation plan's
``test_firm.py`` (cycle 3); this file does not re-test ``_cache_path``
itself, only consumes it.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture(autouse=True)
def _isolate_cache_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect ``XDG_CACHE_HOME`` so every test has an isolated cache directory.

    Spec §5.4.1 routes POSIX cache resolution through
    ``XDG_CACHE_HOME``; setting it to ``tmp_path`` means
    ``_cache_path()`` returns a path under ``tmp_path`` and tests
    cannot collide with the real user cache directory.
    """
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    # Defensive: also clear any TGV3_FIRM_SHARED_CONFIG that might leak
    # from a parent process, so cycle 5's discovery exercises do
    # not inadvertently route to an unrelated path.
    monkeypatch.delenv("TGV3_FIRM_SHARED_CONFIG", raising=False)


# ---------------------------------------------------------------------------
# Cycle 4 — _write_cache (spec §5.4.2)
# ---------------------------------------------------------------------------


def test_cache_write_creates_file(tmp_path: Path) -> None:
    """``_write_cache(bytes)`` produces a file at the resolved cache path."""
    from trust_generator.v3.config.firm import _cache_path, _write_cache

    payload = b"firm_name = 'Example LLP'\n"
    _write_cache(payload)

    target = _cache_path()
    assert target.exists()
    assert target.read_bytes() == payload


def test_cache_write_creates_parent_directory(tmp_path: Path) -> None:
    """If the cache directory does not yet exist, ``_write_cache`` creates it."""
    from trust_generator.v3.config.firm import _cache_path, _write_cache

    target = _cache_path()
    # Sanity: parent should not exist before the first call (the autouse
    # fixture pins XDG_CACHE_HOME but does not pre-create the
    # ``trust-generator/`` subdirectory).
    assert not target.parent.exists(), (
        f"precondition violated — cache parent {target.parent} already exists"
    )

    _write_cache(b"k = 1\n")

    assert target.parent.is_dir()
    assert target.exists()


def test_cache_write_is_atomic(tmp_path: Path) -> None:
    """A successful write leaves no ``firm.shared.cache.toml.tmp`` artifact."""
    from trust_generator.v3.config.firm import _cache_path, _write_cache

    _write_cache(b"k = 1\n")

    target = _cache_path()
    tmp_artifact = target.with_suffix(target.suffix + ".tmp")
    assert not tmp_artifact.exists(), (
        f"atomicity violated — tmp artifact {tmp_artifact} survived the write"
    )


def test_cache_write_overwrites_existing(tmp_path: Path) -> None:
    """A second call with different bytes replaces the first call's content."""
    from trust_generator.v3.config.firm import _cache_path, _write_cache

    _write_cache(b"first = 1\n")
    _write_cache(b"second = 2\n")

    assert _cache_path().read_bytes() == b"second = 2\n"


def test_cache_write_updates_mtime(tmp_path: Path) -> None:
    """Cache file's mtime after a write is within 5 seconds of wall-clock time."""
    import time as _time

    from trust_generator.v3.config.firm import _cache_path, _write_cache

    before = _time.time()
    _write_cache(b"k = 1\n")
    after = _time.time()

    mtime = _cache_path().stat().st_mtime
    assert before - 1.0 <= mtime <= after + 1.0, (
        f"mtime {mtime} outside the [{before - 1.0}, {after + 1.0}] window"
    )


def test_cache_write_failure_emits_warning_not_error(tmp_path: Path) -> None:
    """Write failure (unwriteable cache dir) emits a warning rather than raising."""
    from trust_generator.v3.config.firm import _cache_path, _write_cache

    # Force the parent directory to exist but be unwriteable. The
    # write attempts a tmp-file write inside the parent; chmod 0o500
    # (read+execute, no write) makes that fail with PermissionError on
    # POSIX. (PermissionError is a subclass of OSError, so the
    # function's blanket ``except OSError`` covers it.)
    target = _cache_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.parent.chmod(0o500)
    try:
        with pytest.warns(UserWarning, match="failed to update shared firm.toml cache"):
            _write_cache(b"k = 1\n")
    finally:
        # Restore writeability so tmp_path teardown can remove the dir.
        target.parent.chmod(stat.S_IRWXU)


# ---------------------------------------------------------------------------
# Cycle 5 — _read_shared_with_fallback (spec §5.4.3-§5.4.5)
# ---------------------------------------------------------------------------


def _seed_cache(content: bytes) -> Path:
    """Helper: write ``content`` to the cache path via the cache writer.

    Uses ``_write_cache`` (cycle 4) to populate the cache so
    cycle 5 tests do not depend on the cache-write
    implementation detail beyond its public contract.
    """
    from trust_generator.v3.config.firm import _cache_path, _write_cache

    _write_cache(content)
    cache = _cache_path()
    assert cache.exists(), "test setup failed: _write_cache did not produce a cache file"
    return cache


# Happy-path (case 1) -------------------------------------------------------


def test_shared_present_reads_shared(tmp_path: Path) -> None:
    """When shared exists, non-empty, and parses, returns (bytes, dict, used_cache=False) with no warning."""
    import warnings as _warnings

    from trust_generator.v3.config.firm import _read_shared_with_fallback

    shared = tmp_path / "firm.shared.toml"
    shared_bytes = b"[firm]\nname = 'Example LLP'\n"
    shared.write_bytes(shared_bytes)

    with _warnings.catch_warnings(record=True) as captured:
        _warnings.simplefilter("always")
        content, parsed, used_cache = _read_shared_with_fallback(shared)

    assert content == shared_bytes
    assert parsed == {"firm": {"name": "Example LLP"}}
    assert used_cache is False
    assert captured == [], f"happy path emitted unexpected warnings: {[str(w.message) for w in captured]}"


# Availability-fallback (case 2) --------------------------------------------


def test_shared_missing_cache_present_uses_cache_with_staleness_warning(
    tmp_path: Path,
) -> None:
    """When shared is missing but cache exists, returns cache content + StalenessWarning."""
    from trust_generator.v3.config.firm import (
        SharedConfigStalenessWarning,
        _read_shared_with_fallback,
    )

    cache_bytes = b"[firm]\nname = 'Cached LLP'\n"
    _seed_cache(cache_bytes)

    shared = tmp_path / "firm.shared.toml"  # deliberately not created
    assert not shared.exists(), "test setup violated — shared should not exist"

    with pytest.warns(SharedConfigStalenessWarning) as captured:
        content, parsed, used_cache = _read_shared_with_fallback(shared)

    assert content == cache_bytes
    assert parsed == {"firm": {"name": "Cached LLP"}}
    assert used_cache is True
    assert len(captured) == 1
    assert "unreachable" in str(captured[0].message)


def test_shared_missing_cache_present_warning_includes_age(tmp_path: Path) -> None:
    """The staleness warning includes the cache file's age in human-readable form."""
    from trust_generator.v3.config.firm import (
        SharedConfigStalenessWarning,
        _read_shared_with_fallback,
    )

    _seed_cache(b"[firm]\nname = 'Cached LLP'\n")

    shared = tmp_path / "firm.shared.toml"
    with pytest.warns(SharedConfigStalenessWarning) as captured:
        _read_shared_with_fallback(shared)

    message = str(captured[0].message)
    # Age should appear formatted via timedelta — at minimum, the
    # message contains "old" and a digit-bearing duration token.
    assert "old" in message
    assert any(c.isdigit() for c in message), (
        f"warning lacks any duration digits — got {message!r}"
    )


def test_shared_missing_cache_missing_raises_onboarding_error(tmp_path: Path) -> None:
    """When both shared and cache are missing, raises FirmConfigError naming both paths and 'no cached copy exists'."""
    from trust_generator.v3.config.firm import (
        FirmConfigError,
        _cache_path,
        _read_shared_with_fallback,
    )

    shared = tmp_path / "firm.shared.toml"
    cache = _cache_path()
    assert not shared.exists()
    assert not cache.exists()

    with pytest.raises(FirmConfigError) as excinfo:
        _read_shared_with_fallback(shared)

    message = str(excinfo.value)
    assert str(shared) in message
    assert str(cache) in message
    assert "no cached copy exists" in message


def test_shared_missing_cache_corrupt_raises_corruption_error(tmp_path: Path) -> None:
    """When shared is missing and cache fails to parse, raises FirmConfigError naming cache + 'corrupt'."""
    from trust_generator.v3.config.firm import (
        FirmConfigError,
        _cache_path,
        _read_shared_with_fallback,
    )

    _seed_cache(b"this is not valid TOML\n[unterminated")
    cache = _cache_path()

    shared = tmp_path / "firm.shared.toml"
    assert not shared.exists()

    with pytest.raises(FirmConfigError) as excinfo:
        _read_shared_with_fallback(shared)

    message = str(excinfo.value)
    assert str(cache) in message
    assert "corrupt" in message


# Empty-shared-fallback (case 3) --------------------------------------------


def test_shared_empty_bytes_falls_back_to_cache_with_staleness_warning(
    tmp_path: Path,
) -> None:
    """When shared exists but is empty, returns cache content + StalenessWarning ('advertised but empty')."""
    from trust_generator.v3.config.firm import (
        SharedConfigStalenessWarning,
        _read_shared_with_fallback,
    )

    cache_bytes = b"[firm]\nname = 'Cached LLP'\n"
    _seed_cache(cache_bytes)

    shared = tmp_path / "firm.shared.toml"
    shared.write_bytes(b"")  # OneDrive placeholder state simulation

    with pytest.warns(SharedConfigStalenessWarning) as captured:
        content, parsed, used_cache = _read_shared_with_fallback(shared)

    assert content == cache_bytes
    assert parsed == {"firm": {"name": "Cached LLP"}}
    assert used_cache is True
    assert len(captured) == 1
    assert "advertised but empty" in str(captured[0].message)


def test_shared_empty_bytes_no_cache_raises_empty_shared_error(tmp_path: Path) -> None:
    """When shared is empty and no cache exists, raises FirmConfigError with 'unexpectedly empty' and 'OneDrive placeholder'."""
    from trust_generator.v3.config.firm import (
        FirmConfigError,
        _cache_path,
        _read_shared_with_fallback,
    )

    shared = tmp_path / "firm.shared.toml"
    shared.write_bytes(b"")
    assert not _cache_path().exists()

    with pytest.raises(FirmConfigError) as excinfo:
        _read_shared_with_fallback(shared)

    message = str(excinfo.value)
    assert "unexpectedly empty" in message
    assert "OneDrive placeholder state" in message


# Integrity-fallback (case 4) -----------------------------------------------


def test_shared_malformed_falls_back_to_cache_with_integrity_warning(
    tmp_path: Path,
) -> None:
    """When shared is reachable but TOML-malformed and cache exists, returns cache content + IntegrityWarning."""
    from trust_generator.v3.config.firm import (
        SharedConfigIntegrityWarning,
        SharedConfigStalenessWarning,
        _read_shared_with_fallback,
    )

    cache_bytes = b"[firm]\nname = 'Cached LLP'\n"
    _seed_cache(cache_bytes)

    shared = tmp_path / "firm.shared.toml"
    shared.write_bytes(b"[firm\nname = 'Broken")  # unterminated table header

    with pytest.warns(SharedConfigIntegrityWarning) as captured:
        content, parsed, used_cache = _read_shared_with_fallback(shared)

    assert content == cache_bytes
    assert parsed == {"firm": {"name": "Cached LLP"}}
    assert used_cache is True
    assert len(captured) == 1
    assert "is malformed" in str(captured[0].message)
    # Must NOT also emit a staleness warning.
    assert not isinstance(captured[0].message, SharedConfigStalenessWarning)


def test_shared_malformed_no_cache_raises_integrity_error(tmp_path: Path) -> None:
    """When shared is malformed and no cache exists, raises FirmConfigError with 'is malformed' and 'no cached copy exists to fall back to'."""
    from trust_generator.v3.config.firm import (
        FirmConfigError,
        _cache_path,
        _read_shared_with_fallback,
    )

    shared = tmp_path / "firm.shared.toml"
    shared.write_bytes(b"[firm\nname = 'Broken")
    assert not _cache_path().exists()

    with pytest.raises(FirmConfigError) as excinfo:
        _read_shared_with_fallback(shared)

    message = str(excinfo.value)
    assert "is malformed" in message
    assert "no cached copy exists to fall back to" in message


def test_integrity_warning_distinct_from_staleness_warning() -> None:
    """Both warning classes are UserWarning subclasses; neither subclasses the other."""
    from trust_generator.v3.config.firm import (
        SharedConfigIntegrityWarning,
        SharedConfigStalenessWarning,
    )

    assert issubclass(SharedConfigStalenessWarning, UserWarning)
    assert issubclass(SharedConfigIntegrityWarning, UserWarning)
    assert not issubclass(SharedConfigStalenessWarning, SharedConfigIntegrityWarning)
    assert not issubclass(SharedConfigIntegrityWarning, SharedConfigStalenessWarning)


# Single-emission and category properties -----------------------------------


def test_warning_emitted_exactly_once_per_call(tmp_path: Path) -> None:
    """A single fallback produces exactly one warning, not multiple."""
    import warnings as _warnings

    from trust_generator.v3.config.firm import (
        SharedConfigStalenessWarning,
        _read_shared_with_fallback,
    )

    _seed_cache(b"[firm]\nname = 'Cached LLP'\n")
    shared = tmp_path / "firm.shared.toml"  # missing → case 2

    with _warnings.catch_warnings(record=True) as captured:
        _warnings.simplefilter("always")
        _read_shared_with_fallback(shared)

    staleness = [w for w in captured if isinstance(w.message, SharedConfigStalenessWarning)]
    assert len(staleness) == 1, (
        f"expected exactly one StalenessWarning; got {len(staleness)}: "
        f"{[str(w.message) for w in captured]}"
    )


@pytest.mark.parametrize(
    "scenario,expected_used_cache",
    [
        ("case_1_happy", False),
        ("case_2_missing", True),
        ("case_3_empty", True),
        ("case_4_malformed", True),
    ],
)
def test_used_cache_boolean_matches_fallback_decision(
    tmp_path: Path,
    scenario: str,
    expected_used_cache: bool,
) -> None:
    """``used_cache`` is False for case 1, True for cases 2/3/4."""
    import warnings as _warnings

    from trust_generator.v3.config.firm import _read_shared_with_fallback

    shared = tmp_path / "firm.shared.toml"
    if scenario == "case_1_happy":
        shared.write_bytes(b"[firm]\nname = 'Example LLP'\n")
    elif scenario == "case_2_missing":
        _seed_cache(b"[firm]\nname = 'Cached LLP'\n")
        # shared deliberately absent
    elif scenario == "case_3_empty":
        _seed_cache(b"[firm]\nname = 'Cached LLP'\n")
        shared.write_bytes(b"")
    elif scenario == "case_4_malformed":
        _seed_cache(b"[firm]\nname = 'Cached LLP'\n")
        shared.write_bytes(b"[firm\nbroken")
    else:
        pytest.fail(f"unexpected scenario {scenario!r}")

    with _warnings.catch_warnings():
        _warnings.simplefilter("always")
        _, _, used_cache = _read_shared_with_fallback(shared)

    assert used_cache is expected_used_cache


# Encoding tolerance (round-2 plan-review) ----------------------------------


def test_shared_with_utf8_bom_loads_normally(tmp_path: Path) -> None:
    """A shared file saved with a UTF-8 BOM loads via case 1, not integrity-fallback."""
    import warnings as _warnings

    from trust_generator.v3.config.firm import _read_shared_with_fallback

    bom = b"\xef\xbb\xbf"
    shared = tmp_path / "firm.shared.toml"
    shared.write_bytes(bom + b"[firm]\nname = 'Example LLP'\n")

    with _warnings.catch_warnings(record=True) as captured:
        _warnings.simplefilter("always")
        content, parsed, used_cache = _read_shared_with_fallback(shared)

    assert content.startswith(bom)
    assert parsed == {"firm": {"name": "Example LLP"}}
    assert used_cache is False
    assert captured == [], (
        f"BOM-prefixed shared emitted unexpected warnings: {[str(w.message) for w in captured]}"
    )
