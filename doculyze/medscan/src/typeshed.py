# ruff: noqa: F401
from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from argparse import ArgumentParser, _SubParsersAction
    from datetime import date, datetime, time

    from fitz import Document, Page, TextPage

type Subparsers = _SubParsersAction[ArgumentParser]
type ValidationSubject = Literal["injuries", "treatments"]
type ValidatedResult = dict[ValidationVerdict, dict[str, tuple[float, list[str]]]]
type ValidationVerdict = Literal["verified", "unverified"]
type AnalysisResults = dict[ValidationSubject, list[str]]
type ValidationSummary = dict[ValidationSubject, dict[ValidationVerdict, int]]
