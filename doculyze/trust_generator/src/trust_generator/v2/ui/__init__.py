"""User interface layer — GUI (tkinter) and CLI entry points."""

from __future__ import annotations

from .app import main
from .gui import run_gui

__all__ = ["main", "run_gui"]
