# ruff: noqa: F401
import typing


if typing.TYPE_CHECKING:
    from typing import *
    from collections.abc import *
    from pathlib import Path
    from datetime import date
    from fitz import TextPage, Page, Document
    from argparse import ArgumentParser, Namespace

    type JSONSerializable = (
        str
        | int
        | float
        | bool
        | None
        | list[JSONSerializable]
        | dict[str, JSONSerializable]
    )

    type JSONDict = dict[str, JSONSerializable]
    type JSONList = list[JSONSerializable]

    type Iter[T: Any] = Iterable[T]

    type OptInt = int | None
    type PageRange = tuple[OptInt, OptInt]

    type ValidationSubject = Literal["injuries", "treatments"]
    type ValidationVerdict = Literal["verified", "unverified"]
    type ValidatedResult = dict[ValidationVerdict, list[str]]
    type ValidationSummary = dict[ValidationSubject, dict[ValidationVerdict, int]]
