import typing as ty
import pathlib as pl
import argparse as ap
import datetime as dt


class _ProgramArgs(ap.Namespace):
    command: str
    dir: pl.Path
    _desc: str
    _date: str


class ProgramArgs:
    _parsed: _ProgramArgs
    _path: pl.Path
    command: str

    def params(self) -> tuple[ty.Any, ...]:
        match self.command:
            case "analyze":
                return (
                    self._parsed._desc,
                    dt.date.fromisoformat(self._parsed._date),
                    self._path,
                )
            case "extract":
                return (self._path,)
            case _:
                return ()

    @classmethod
    def from_parsed(cls, parsed: _ProgramArgs) -> ty.Self:
        inst: ProgramArgs = cls()
        path = parsed.dir.resolve(strict=True)
        if not path.is_dir():
            raise ValueError("The provided path is not a dir.")
        inst._path = path
        inst._parsed = parsed
        inst.command = parsed.command
        return inst


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
    dest="dir",
    type=pl.Path,
    nargs=1,
    metavar="DIRECTORY",
    help="Path to a directory with extracted text files to analyze.",
)
_analysis_parser.add_argument(
    "--desc",
    dest="_desc",
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
    dest="dir",
    type=pl.Path,
    metavar="DIRECTORY",
    help="Path to a directory containing PDF files to parse.",
)


def parse() -> ProgramArgs:
    parsed = _parser.parse_args(namespace=_ProgramArgs())
    try:
        return ProgramArgs.from_parsed(parsed)
    except AttributeError:
        help()
        _parser.exit(1)


def help() -> None:
    _parser.print_help()
