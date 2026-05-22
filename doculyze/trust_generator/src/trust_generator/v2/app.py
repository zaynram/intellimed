"""Entry point for trust-generator (auto mode: GUI or CLI)."""

from __future__ import annotations

from trust_generator.v2.ui.app import main
from trust_generator.v2.ui.gui import run_gui

__all__ = ["main", "run_gui"]

if __name__ == "__main__":
    main()
