from __future__ import annotations

from .utils import DATA_DIR, timings, console, argtype

import fitz
import typing

if typing.TYPE_CHECKING:
    from .typeshed import *

from pathlib import Path


class Preprocessor:
    debug: bool = False
    keep_original: bool = True

    file_in: Path
    out_dir: Path

    trim_start: int
    trim_end: int

    split_indices: list[int]

    def _trim_range_exists(self) -> bool:
        return any(n > 0 for n in [self.trim_start, self.trim_end])

    def _split_generator(self) -> Generator[int]:
        return (n for n in self.split_indices or [])

    def _get_path(self, suffix: str = "") -> Path:
        suffix_with_ext = suffix if ".pdf" in suffix else f"{suffix}.pdf"
        return (self.out_dir or self.file_in.parent) / f"{self.file_in.stem}{suffix_with_ext}"

    @timings(strip_prefix="_")
    def _clone_doc(
        self,
        from_page: int,
        to_page: int,
        start_at: int = -1,
        suffix: str = "",
    ) -> None:
        src = fitz.open(self.file_in)
        out = fitz.open()
        out.insert_pdf(src, from_page=from_page, to_page=to_page, start_at=start_at)
        out.save(self._get_path(suffix))
        src.close()

    @timings(strip_prefix="_")
    def _trim_doc(self) -> None:
        self._clone_doc(
            from_page=self.trim_start - 1,
            to_page=self.trim_end,
            suffix="_trim",
        )

    @timings(strip_prefix="_")
    def _split_doc(self) -> None:
        prev = getattr(self, "trim_start", 1) - 1
        for curr in self._split_generator():
            self._clone_doc(
                from_page=prev,
                to_page=curr - 1,
                suffix=f"_split_{prev + 1}-{curr}",
                start_at=0,
            )
            prev = curr

    @timings()
    def preprocess(self) -> None:
        should_trim = self._trim_range_exists()

        if not (self.split_indices or should_trim):
            console.log("Nothing to preprocess.", "Exiting...")
            return

        if self.split_indices:
            self._split_doc()
        if should_trim:
            self._trim_doc()

        if not self.keep_original:
            self.file_in.unlink()
            console.log("Removed original file.")

    @staticmethod
    def init_preprocess_args(subparsers: Subparsers) -> None:
        subparser = subparsers.add_parser(
            "preprocess",
            description="Preprocess files by splitting or slicing them.",
            prog="Preprocess Files",
        )

        options = subparser.add_argument_group("Options")
        options.add_argument(
            "--file_in",
            metavar="Input File",
            help="The PDF file to edit.",
            required=True,
            widget="FileChooser",
            gooey_options={"default_dir": DATA_DIR},
            type=Path,
        )
        options.add_argument(
            "--out_dir",
            metavar="Output Folder",
            help="The destination folder for the processed file. Defaults to the same directory as the original.",
            widget="DirChooser",
            gooey_options={"default_path": DATA_DIR},
            type=Path,
        )
        options.add_argument(
            "--keep_original",
            metavar="Keep Original",
            choices=[True, False],
            default=True,
            help="Whether to keep or remove the original file after preprocessing.",
            type=argtype.boolstring,
        )

        config = subparser.add_argument_group(
            "Configuration",
            "Configure the behavior of editing the given file.",
        )
        config.add_argument(
            "--split_indices",
            metavar="File Splits",
            help="Page numbers (inclusive) marking where to split the document. Separate page numbers with commas.",
            widget="Textarea",
            type=argtype.integerlist,
        )

        trim_range = config.add_argument_group(
            "Trim Range",
            description="Include only the pages from the specified range.",
        )
        trim_range.add_argument(
            "--trim_start",
            metavar="Page Start",
            help="The starting page number (inclusive) for trimming the document. Defaults to the first page of the document.",
            widget="IntegerField",
            gooey_options={"min": 0, "initial_value": 0},
            type=int,
        )
        trim_range.add_argument(
            "--trim_end",
            metavar="Page End",
            help="The ending page number (inclusive) for trimming the document. Defaults to the end of the document.",
            widget="IntegerField",
            gooey_options={"min": -1, "initial_value": -1},
            type=int,
        )
        dev = subparser.add_argument_group("Developer")
        dev.add_argument(
            "--debug",
            metavar="Debug",
            choices=[True, False],
            default=False,
            help="If set to True, will print the program configuration and exit without execution.",
            type=argtype.boolstring,
        )
