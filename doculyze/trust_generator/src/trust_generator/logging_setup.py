"""
Logging configuration for trust-generator.

Call setup_logging() once at application startup (in app.py / cli entry point).
All modules use logging.getLogger(__name__) and inherit this config.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path


def setup_logging(*, verbose: bool = False) -> None:
    """Configure root logger with console and optional file output."""
    level = logging.DEBUG if verbose else logging.INFO

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)-7s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    console = logging.StreamHandler(sys.stderr)
    console.setLevel(level)
    console.setFormatter(fmt)

    handlers: list[logging.Handler] = [console]

    # File handler in %APPDATA%/trust-generator/logs/
    try:
        if sys.platform == "win32":
            log_dir = Path.home() / "AppData" / "Local" / "trust-generator" / "logs"
        else:
            log_dir = Path.home() / ".config" / "trust-generator" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_dir / "trust-generator.log",
            encoding="utf-8",
            maxBytes=5 * 1024 * 1024,  # 5 MB
            backupCount=3,
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(fmt)
        handlers.append(file_handler)
    except OSError:
        pass  # File logging is best-effort

    logging.basicConfig(level=level, handlers=handlers, force=True)
