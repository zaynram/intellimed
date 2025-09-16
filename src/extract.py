from __future__ import annotations
from src.utils import track, console
from src.typeshed import JSONDict

import fitz
import typing

if typing.TYPE_CHECKING:
    from .typeshed import *

from pathlib import Path


Metadata = typing.NamedTuple("Metadata", [("path", Path), ("json", JSONDict)])


class Extractor:
    path: Path

    _skip_extract: bool = False
    _total_files: int

    def set_total_files(self, total: int) -> None:
        self._total_files: int = total
        track.GLOBAL_TOTAL = total

    def _rebase_file(
        self,
        file: str | Path,
        *,
        base_path: Path | None = None,
        suffix: str | None = None,
    ) -> Path:
        orig_name = file if isinstance(file, str) else file.name

        if suffix and not suffix.startswith("."):
            raise ValueError("suffix must start with '.'")
        elif not (suffix or "." in orig_name):
            raise ValueError("invalid file extension")

        stem = orig_name.rsplit(".")[0]
        parts = (
            (stem, suffix)
            if suffix
            else (stem, orig_name[idx:])
            if (idx := orig_name.rindex("."))
            else (None, None)
        )

        if parts == (None, None):
            raise ValueError
        else:
            parts = typing.cast(tuple[str, str], parts)

        return base_path or self.path / "".join(parts)

    def _safe_get_directory(self, dirname: str, *, override: Path | None) -> Path:
        path = (override or self.path) / dirname
        if not path.exists():
            path.mkdir()
        elif any(path.iterdir()):
            if not console.confirm(f"Overwrite existing files at '{path}'?"):
                match dirname:
                    case "analysis":
                        raise SystemExit
                    case "plaintext":
                        self._skip_extract = True
        return path

    custom_text_dir: Path | None = None

    @property
    def text_dir(self) -> Path:
        return self._safe_get_directory("plaintext", override=self.custom_text_dir)

    custom_results_dir: Path | None = None

    @property
    def results_dir(self) -> Path:
        return self._safe_get_directory("analysis", override=self.custom_results_dir)

    def _process_textpage_chunk(
        self,
        textpages: Iter[TextPage],
    ) -> str:
        return chr(12).join(
            textpage.extractText()
            for textpage in track(
                iterable=textpages,
                desc="extracting plaintext",
                total=self._total_files,
            )
        )

    def _extract_text(self) -> list[Path]:
        """
        Extracts text from all PDF files in a given directory and saves it to
        corresponding .txt files.

        Args:
            directory (str): The path to the directory containing PDF files.
            page_ranges (dict): The range arguments specifying the pages to include for each file. Defaults to (0, None, 1) for all files.
        """

        self.path = self.path.resolve(strict=True)

        text_dir = self.text_dir

        if self._skip_extract:
            text_files = [f for f in text_dir.iterdir() if f.suffix == ".txt" and f.is_file()]
            self.set_total_files(len(text_files))
            return text_files

        input_files = [f for f in self.path.iterdir() if f.suffix == ".pdf" and f.is_file()]
        self.set_total_files(len(input_files))

        chunk_generators = [
            (fitz.utils.get_textpage_ocr(p) for p in pages)
            for pages in track(
                iterable=(fitz.open(f).pages() for f in input_files),
                desc="running optical character recognition",
            )
        ]

        text_files = [text_dir / f"{f.stem}.txt" for f in input_files]

        for f, text in track(
            iterable=zip(
                text_files,
                (self._process_textpage_chunk(c) for c in chunk_generators),
                strict=True,
            ),
            desc="extracting plaintexts",
        ):
            f.write_text(text, encoding="utf-8")

        return text_files
