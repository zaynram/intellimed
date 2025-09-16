from __future__ import annotations

import wx
import os

os.environ.setdefault(
    "TESSDATA_PREFIX",
    "C:\\Program Files\\Tesseract-OCR\\tessdata",
)

from src.utils import console
from src.preprocess import Preprocessor
from src.analyze import Analyzer
from gooey import Gooey, GooeyParser
from argparse import Namespace

app = wx.App()


class Program(Namespace, Preprocessor, Analyzer):
    command: str

    def invoke(self) -> None:
        console.FILE.write_text("")
        func = self._debug if self.debug else getattr(self, self.command, None)
        if not callable(func):
            raise TypeError("Invalid command.")
        func.__call__(self)

    def _debug(self) -> None:
        console.debug(**{key: val for key, val in self.__dict__.items() if not callable(val)})


@Gooey(
    advanced=True,
    program_name="Medical Records Analyzer",
    program_description="Preprocess and analyze medical record PDF files using local tools and LLMs.",
    header_show_help=True,
    hide_progress_msg=True,
    timing_options={
        "show_time_remaining": True,
        "hide_time_remaining_on_complete": True,
    },
    progress_regex=r"^progress: (?P<current>\d+)/(?P<total>\d+)$",
    progress_expr="current / total * 100",
    default_size=(1200, 600),
    return_to_config=False,
    show_failure_modal=True,
    tabbed_groups=True,
    show_restart_button=False,
    run_validation=True,
    group_by_type=True,
    show_preview_warning=False,
)
def main():
    parser = GooeyParser(description="Process medical record PDF files using LLMs.")
    subparsers = parser.add_subparsers(help="Commands", dest="command")
    Program.init_analysis_args(subparsers)
    Program.init_preprocess_args(subparsers)
    program: Program = parser.parse_args(namespace=Program())
    program.invoke()


if __name__ == "__main__":
    main()
