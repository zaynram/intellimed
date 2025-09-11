from __future__ import annotations

import typing as ty
import pathlib as pl
import argparse as ap
import datetime as dt

if ty.TYPE_CHECKING:
    from extract import PageRange

_parser = ap.ArgumentParser(
    prog="main.py",
    description="Process medical record PDF files using local LLMs.",
)
_subparsers = _parser.add_subparsers(
    dest="command",
    help="Available commands.",
)
_analysis_parser = _subparsers.add_parser(
    name="analyze",
    description="Analyze plaintext from medical records using local LLMs.",
)
_analysis_parser.add_argument(
    dest="path",
    type=pl.Path,
    nargs=1,
    metavar="DIRECTORY",
    help="Path to a directory with extracted text files to analyze.",
)
_analysis_parser.add_argument(
    "--desc",
    dest="desc",
    type=str,
    help="Description of the accident (e.g., 'motor vehicle accident').",
    required=True,
)
_analysis_parser.add_argument(
    "--date",
    dest="_date",
    type=str,
    help="Date of the accident in ISO 8601 format (e.g., '2024-10-20').",
    required=True,
)
_extraction_parser = _subparsers.add_parser(
    name="extract",
    description="Extract plaintext from PDF files.",
)
_extraction_parser.add_argument(
    dest="path",
    type=pl.Path,
    metavar="DIRECTORY",
    help="Path to a directory containing PDF files to parse.",
)


type PageRangeEntry = tuple[str, *PageRange._T]


def parse_page_range(string: str) -> PageRangeEntry:
    values: list[ty.Any] = string.split()
    if 2 > len(values) > 4:
        raise ValueError(values)
    return tuple[str, int, int | None, int | None](
        None if i >= len(values) else values[i] if i == 0 else int(values[i])
        for i in range(4)
    )


_extraction_parser.add_argument(
    "--range",
    dest="_range_map",
    action="append",
    type=parse_page_range,
    help=chr(12).join(
        [
            "The number of the first page to extract text from for the specified document.",
            "The value should be formatted as <filename> <start_index> [end_index]",
        ]
    ),
)


class ProgramArgs(ap.Namespace):
    command: str
    desc: str
    path: pl.Path

    _date: str
    _range_map: list[PageRangeEntry]

    date: dt.date
    range_dict: dict[str, PageRange._T]

    def params(self) -> tuple[ty.Any, ...]:
        path = getattr(self, "path")

        if not path or not path.resolve(strict=True).is_dir():
            raise ValueError("The provided path is not a valid directory.")

        match self.command:
            case "analyze":
                date = getattr(self, "_date")
                if not date:
                    raise ValueError("The date that the accident occurred is required.")
                self.date = dt.date.fromisoformat(date)
            case "extract":
                range_map = getattr(self, "_range_map") or []
                self.range_dict = dict(range_map)

        match self.command:
            case "analyze":
                return (self.desc, self.date, self.path)
            case "extract":
                return (self.path, self.range_dict)
            case _:
                return ()


def parse() -> ProgramArgs:
    return _parser.parse_args(namespace=ProgramArgs())


def help() -> None:
    _parser.print_help()


def confirm(
    prompt: str,
    *,
    choices: list[str] | None = None,
    accept: list[str] | None = None,
    reject: list[str] | None = None,
    match_exact: bool = False,
    default: bool | None = False,
) -> bool:
    if choices is None:
        choices = ["y", "n"]
    if accept is None:
        accept = choices[:0]
    if reject is None:
        reject = []

    res, ok = "", False
    while not ok:
        res = input(f"{prompt} [{'/'.join(choices)}]:")
        if not res and default is not None:
            return default
        ok = bool(res)

    if not match_exact:
        for item in accept, reject:
            item[:] = [x[0] for x in item if isinstance(x, str) and len(x) >= 1]

    def check(iterable: ty.Iterable) -> bool:
        return any(res.startswith(x) for x in iterable)

    return check(accept) and not check(reject)
