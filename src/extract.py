import os

os.environ.setdefault("TESSDATA_PREFIX", "C:\\Program Files\\Tesseract-OCR\\tessdata")

import typing as ty
import pathlib as pl
import tqdm
import pymupdf as fitz


if ty.TYPE_CHECKING:
    from pathlib import Path

ALL_PAGES = (0, None)

type OptInt = int | None
type PageRange = tuple[OptInt, OptInt] | tuple[OptInt, OptInt, OptInt]


def plaintext_from_pdfs(
    directory_path: pl.Path, page_range: PageRange = ALL_PAGES
) -> None:
    """
    Extracts text from all PDF files in a given directory and saves it to
    corresponding .txt files.

    Args:
        directory_path (str): The path to the directory containing PDF files.
    """
    input_dir: Path = directory_path.resolve(strict=True)

    output_dir: Path = input_dir / "plaintext"
    output_dir.mkdir(parents=True, exist_ok=True)

    for f in tqdm.tqdm(
        iterable=input_dir.iterdir(),
        desc="processing item",
        unit=" file",
    ):
        if not f.name.lower().endswith(".pdf"):
            continue

        out_file: Path = output_dir / f"{f.stem}.txt"

        with fitz.open(input_dir / f.name) as pdf:
            page_texts: list[str] = []
            raw_pages: list[fitz.Page] = [*pdf.pages(*page_range)]

            for page in tqdm.tqdm(
                iterable=raw_pages,
                desc="extracting text",
                unit=" page",
            ):
                text: str = fitz.utils.get_textpage_ocr(page, full=True).extractText()
                page_texts.append(text)

            out_file.write_text(
                data=chr(12).join(page_texts),
                encoding="utf-8",
            )
