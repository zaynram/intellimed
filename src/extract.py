from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    from .types import *

import json
import fitz
from .utils import track


class Extractor:
    path: Path

    _metadata: dict[str, Any]

    def _get_dir(self, path: Path) -> Path:
        if not path.exists():
            path.mkdir()
        elif [*path.iterdir()]:
            from .utils import confirm

            if not confirm(f"Overwrite existing files at '{path}'?"):
                print("File processing aborted.", flush=True)
                raise SystemExit(0)

        return path

    custom_text_dir: Path | None = None

    @property
    def text_dir(self) -> Path:
        return self._get_dir(self.custom_text_dir or self.path / "plaintext")

    custom_results_dir: Path | None = None

    @property
    def results_dir(self) -> Path:
        return self._get_dir(self.custom_results_dir or self.path / "analysis")

    def _process_textpage_chunk(
        self,
        textpages: Iter[TextPage],
    ) -> str:
        return chr(12).join(
            textpage.extractText()
            for textpage in track(
                iterable=textpages,
                desc="extracting plaintext",
            )
        )

    def _write_metadata_file(self, metadata: JSONDict) -> None:
        from datetime import datetime, UTC

        metadata["created_at"] = datetime.now(UTC).isoformat()
        self._metadata = metadata
        data_file = self.path / "metadata.json"
        data_file.write_text(
            data=json.dumps(metadata, indent=4),
            encoding="utf-8",
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

        list_dir = [*self.path.iterdir()]

        track.set_default_total(len(list_dir))

        input_files = [
            f
            for f in track(
                iterable=list_dir,
                desc="gathering pdf files",
            )
            if f.name.lower().endswith(".pdf")
        ]

        chunk_generators = [
            (fitz.utils.get_textpage_ocr(p) for p in pages)
            for pages in track(
                iterable=(fitz.open(f).pages() for f in input_files),
                desc="running optical character recognition",
            )
        ]

        text_generator = (self._process_textpage_chunk(c) for c in chunk_generators)
        text_files: list[Path] = [self.text_dir / f"{f.stem}.txt" for f in input_files]

        total: int = 0
        metadata: JSONDict = {}
        for f, text in track(
            iterable=zip(text_files, text_generator, strict=True),
            desc="extracting plaintexts",
        ):
            num_chars = f.write_text(text, encoding="utf-8")
            total += num_chars
            metadata[f.stem] = {
                "source_uri": (self.path / f"{f.stem}.pdf").as_uri(),
                "character_count": num_chars,
            }

        metadata["total_characters"] = total

        self._write_metadata_file(metadata)

        return text_files
