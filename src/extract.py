from __future__ import annotations

import os

os.environ.setdefault(
    "TESSDATA_PREFIX",
    "C:\\Program Files\\Tesseract-OCR\\tessdata",
)

import json
import math
import tqdm
import fitz
import pathlib as pl
import datetime as dt

import typing
from datetime import datetime
from pathlib import Path

if typing.TYPE_CHECKING:
    from fitz import Page, TextPage
    from typing import Any, Final
    from collections.abc import Iterable

    type Iter[T] = Iterable[T]
    type OptInt = int | None
    type _PageRange = tuple[OptInt, OptInt, OptInt]


class PageRange:
    type _T = _PageRange
    ALL: Final = (0, None, 1)
    EVEN: Final = (0, None, 2)
    ODD: Final = (1, None, 2)

    @staticmethod
    def before(n: int, *, step: int | None = None) -> _PageRange:
        return (None, n, step)

    @staticmethod
    def after(n: int, *, step: int | None = None) -> _PageRange:
        return (n, None, step)

    @staticmethod
    def custom(
        start: int | None = None,
        end: int | None = None,
        *,
        step: int | None = None,
    ) -> _PageRange:
        return (start, end, step)


def pages_generator(
    input_files: Iter[Path],
    page_ranges: dict[str, _PageRange],
) -> Iter[Iter[Page]]:
    return (fitz.open(f).pages(*page_ranges[f.name]) for f in input_files)


def textpage_generator(
    pages: Iter[Page],
) -> Iter[TextPage]:
    from fitz.utils import get_textpage_ocr

    return (
        get_textpage_ocr(page)
        for page in tqdm.tqdm(
            iterable=pages,
            desc="running optical character recognition",
        )
    )


def get_files(
    input_dir: pl.Path,
    output_folder: str = "plaintext",
) -> tuple[Iter[Path], Iter[Path], Path]:
    output_dir = input_dir.resolve(strict=True) / output_folder

    try:
        output_dir.mkdir()
    except FileExistsError:
        from .arguments import confirm

        if not confirm("Overwrite existing plaintext files?"):
            raise SystemExit(0)

    input_files = [
        file
        for file in tqdm.tqdm(
            iterable=input_dir.iterdir(),
            desc="discovering pdfs",
        )
        if file.name.lower().endswith(".pdf")
    ]

    output_files = [output_dir / f"{f.stem}.txt" for f in input_files]

    return input_files, output_files, output_dir / "metadata.json"


def get_plaintexts(
    input_files: Iter[Path],
    page_ranges: dict[str, _PageRange],
) -> list[str]:
    return [
        chr(12).join(
            textpage.extractText()
            for textpage in tqdm.tqdm(
                iterable=textpages,
                desc="extracting plaintext",
            )
        )
        for textpages in (
            textpage_generator(pages)
            for pages in pages_generator(input_files, page_ranges)
        )
    ]


def get_metadata_json(
    output_files: Iter[Path],
    plaintexts: Iter[str],
) -> str:
    input_dir = next(iter(output_files)).parents[1]
    metadata: dict[str, Any] = {
        name: {
            "source_uri": (input_dir / name.replace("txt", "pdf")).as_uri(),
            "appx_tokens": ct,
        }
        for name, ct in (
            (f.name, math.ceil(f.write_text(data=t, encoding="utf-8") / 4))
            for f, t in zip(output_files, plaintexts, strict=True)
        )
    }
    metadata["last_modified"] = datetime.now(dt.UTC).isoformat()
    return json.dumps(metadata, indent=4)


def plaintext_from_pdfs(
    directory: Path,
    page_ranges: dict[str, _PageRange] | None = None,
) -> None:
    """
    Extracts text from all PDF files in a given directory and saves it to
    corresponding .txt files.

    Args:
        directory (str): The path to the directory containing PDF files.
        page_ranges (dict): The range arguments specifying the pages to include for each file. Defaults to (0, None, 1) for all files.
    """
    pdfs, txts, metadata = get_files(directory)
    ranges: dict[str, _PageRange] = {f.name: PageRange.ALL for f in pdfs}
    ranges.update(page_ranges or {})
    extracted = get_plaintexts(pdfs, ranges)
    info = get_metadata_json(txts, extracted)
    metadata.write_text(info, encoding="utf-8")
