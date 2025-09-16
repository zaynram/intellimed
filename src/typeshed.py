# ruff: noqa: F401
import typing

if typing.TYPE_CHECKING:
    from typing import *
    from collections.abc import *
    from datetime import date, time, datetime
    from fitz import TextPage, Page, Document
    from argparse import ArgumentParser, _SubParsersAction

    type Subparsers = _SubParsersAction[ArgumentParser]
    type Iter[T: Any] = Iterable[T]

type JSONPrimitive = str | int | float | bool | None
type JSONList = list[JSONSerializable]
type JSONDict = dict[str, JSONSerializable]
type JSONSerializable = JSONPrimitive | JSONList | JSONDict
type ValidationSubject = Literal["injuries", "treatments"]
type ValidatedResult = dict[ValidationVerdict, dict[str, tuple[float, list[str]]]]
type ValidationVerdict = Literal["verified", "unverified"]
type AnalysisResults = dict[ValidationSubject, list[str]]
type ValidationSummary = dict[ValidationSubject, dict[ValidationVerdict, int]]
