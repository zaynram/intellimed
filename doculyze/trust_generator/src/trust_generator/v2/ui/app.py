"""
Main entry point for trust-generator.

Dispatches to GUI or CLI based on mode / command-line arguments.
"""

from __future__ import annotations

import logging
import sys

log = logging.getLogger(__name__)


def main(mode: str = "auto") -> None:
    """Launch trust-generator in the requested mode.

    Parameters
    ----------
    mode:
        ``"auto"`` -- GUI if no CLI args, CLI if args present.
        ``"gui"``  -- force GUI.
        ``"cli"``  -- force CLI.
    """
    if mode == "gui":
        _launch_gui()
        return

    if mode == "cli":
        _launch_cli()
        return

    # auto: CLI if arguments were passed, GUI otherwise
    # sys.argv[0] is the script name; real args start at [1]
    if len(sys.argv) > 1:
        _launch_cli()
    else:
        _launch_gui()


def _launch_gui() -> None:
    from trust_generator.v2.ui.gui import run_gui

    run_gui()


def _launch_cli() -> None:
    from trust_generator.v2.ui.cli import run_cli

    run_cli()
