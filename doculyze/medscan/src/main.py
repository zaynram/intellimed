from __future__ import annotations

import importlib
from typing import final

from . import Medscan
from .goo import gooify, gooparse


def import_deps():
    global wx
    wx = importlib.import_module("wx")


app = wx.App()
description = final(
    "Preprocess and analyze medical record PDF files using local tools and LLMs."
)


@gooify("Medical Records Analyzer", desc=description)
def main():
    program = Medscan()
    parser = gooparse(description)

    cmdparser = parser.add_subparsers(dest="command")
    program.init_analysis_args(cmdparser)
    program.init_preprocess_args(cmdparser)

    parser.parse_args(namespace=program).invoke()


if __name__ == "__main__":
    main()
