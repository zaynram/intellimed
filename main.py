from __future__ import annotations
import os
import wx
import argparse

os.environ.setdefault(
    "TESSDATA_PREFIX",
    "C:\\Program Files\\Tesseract-OCR\\tessdata",
)

from src.preprocess import Preprocessor
from src.analyze import Analyzer
from gooey import Gooey, GooeyParser
from pathlib import Path
import datetime
import typing

if typing.TYPE_CHECKING:
    from .src.types import *

app = wx.App()


class Program(argparse.Namespace, Preprocessor, Analyzer):
    command: str

    def invoke(self, help_fn: Callable[..., None] | None = None) -> None:
        fn = getattr(self, self.command, None)

        if callable(fn):
            fn()
        elif callable(help_fn):
            help_fn()

    @staticmethod
    def transform_date(string: str) -> date:
        return datetime.date.fromisoformat(string)

    @staticmethod
    def transform_flag(string: str) -> bool:
        match string:
            case "no":
                return False
            case _:
                return True


@Gooey(
    advanced=True,
    program_name="Medical Records Analyzer",
    program_description="Preprocess and analyze medical record PDF files using local tools and LLMs.",
    header_show_help=True,
    progress_regex=r"^progress: (?P<current>\d+)/(?P<total>\d+)$",
    progress_expr="f'{current / total * 100:.2}%'",
    hide_progress_msg=True,
    timing_options={
        "show_time_remaining": True,
        "hide_time_remaining_on_complete": True,
    },
    default_size=(600, 700),
    return_to_config=False,
    show_failure_modal=True,
    tabbed_groups=True,
    show_restart_button=False,
)
def main():
    parser = typing.cast(
        "ArgumentParser",
        GooeyParser(description="Process medical record PDF files using local LLMs."),
    )

    subparsers = parser.add_subparsers(help="Commands", dest="command")

    preprocess_parser = subparsers.add_parser(
        "preprocess",
        description="Preprocess files by splitting or slicing them.",
        prog="Preprocess Files",
    )

    preprocess_args_group = preprocess_parser.add_argument_group(
        "Preprocessing Arguments",
        "Configure the behavior and parameters for editing the given file.",
    )

    preprocess_args_group.add_argument(
        "--file_in",
        type=Path,
        help="The PDF file to edit.",
        widget="FileChooser",
        required=True,
    )
    preprocess_args_group.add_argument(
        "--out_dir",
        type=Path,
        help="The destination folder for the processed file. Defaults to the same directory as the original.",
        widget="DirChooser",
    )

    preprocess_options_group = preprocess_parser.add_argument_group(
        "Preprocessing Options",
        "Configure the behavior and parameters for editing the given file.",
    )

    preprocess_options_group.add_argument(
        "--keep_original",
        choices=["yes", "no"],
        default="yes",
        help="Keep the original file after preprocessing.",
    )

    preprocess_options_group.add_argument(
        "--split_indices",
        type=int,
        nargs="*",
        help="Page numbers (inclusive) marking where to split the document. Separate page numbers with spaces.",
    )

    trim_options_group = preprocess_options_group.add_argument_group(
        "Trim Range",
        description="Include only the pages from the specified range.",
    )

    trim_options_group.add_argument(
        "--trim_start",
        type=int,
        default=0,
        help="The starting page number (inclusive) for trimming the document (e.g., 1).",
        widget="IntegerField",
    )
    trim_options_group.add_argument(
        "--trim_end",
        type=int,
        default=-1,
        help="The ending page number (inclusive) for trimming the document (e.g., 5).",
        widget="IntegerField",
    )

    analyze_parser = subparsers.add_parser(
        "analyze",
        description="Analyze medical record PDF files using local LLM inferencing.",
        prog="Analyze Files",
    )

    analyze_args_group = analyze_parser.add_argument_group(
        "Analysis Arguments",
        description="Configure the location(s) of output files.",
    )

    analyze_args_group.add_argument(
        "--path",
        type=Path,
        help="The folder containing the medical records. Only PDF files will be used for analysis.",
        widget="DirChooser",
        required=True,
    )
    analyze_args_group.add_argument(
        "--desc",
        type=str,
        help="A brief description of the related accident.",
        required=True,
    )
    analyze_args_group.add_argument(
        "--date",
        type=Program.transform_date,
        help="The date that the accident occured on.",
        widget="DateChooser",
        required=True,
    )

    analyze_options_group = analyze_parser.add_argument_group(
        "Analysis Options",
        description="Configure the location(s) of output files.",
    )

    analyze_options_group.add_argument(
        "--custom_text_dir",
        help="The folder to save extracted plaintext to.",
        widget="DirChooser",
    )

    analyze_options_group.add_argument(
        "--custom_results_dir",
        help="The folder to save analysis results to.",
        widget="DirChooser",
    )

    analyze_options_group.add_argument(
        "--max_tokens_per_request",
        type=int,
        help="(Advanced) The maximum amount of tokens for a single request.",
        widget="IntegerField",
        default=96000,
    )

    analyze_options_group.add_argument(
        "--ollama_model_id",
        type=str,
        help="(Advanced) The identifier for the model to use for analysis.",
        default="gemma3n:e4b",
    )

    parser.parse_args(namespace=Program()).invoke(parser.print_help)


if __name__ == "__main__":
    main()
