from __future__ import annotations

import typing
import fitz

if typing.TYPE_CHECKING:
    from collections.abc import *
    from pathlib import Path


class Preprocessor:
    file_in: Path
    out_dir: Path
    trim_start: int
    trim_end: int
    split_indices: list[int]
    keep_original: str

    def _iter_preprocess_splits(self) -> Generator[int]:
        return (n for n in self.split_indices or [])

    def _get_preprocess_path(self, suffix: str = "") -> Path:
        suffix_with_ext = suffix if ".pdf" in suffix else f"{suffix}.pdf"
        return (
            self.out_dir or self.file_in.parent
        ) / f"{self.file_in.stem}{suffix_with_ext}"

    def _preprocess_clone_doc(
        self,
        from_page: int,
        to_page: int,
        suffix: str = "",
    ) -> None:
        src = fitz.open(self.file_in)
        out = fitz.open()
        out.insert_pdf(src, from_page=from_page, to_page=to_page)
        out.save(self._get_preprocess_path(suffix))
        src.close()

    def _preprocess_trim_doc(self) -> None:
        self._preprocess_clone_doc(
            from_page=self.trim_start,
            to_page=self.trim_end,
            suffix="_trim",
        )

    def _preprocess_split_doc(self) -> None:
        iterator = self._iter_preprocess_splits()
        try:
            count = 0
            prev_split = 0
            while index := next(iterator):
                self._preprocess_clone_doc(
                    from_page=prev_split,
                    to_page=index,
                    suffix=f"_split_{prev_split}-{index}",
                )
                count += 1
                prev_split = index

        except StopIteration:
            pass

    def preprocess(self) -> None:
        from .utils import log

        if not self.split_indices or self.trim_end:
            log("Nothing to preprocess.", "Exiting...")
            return

        if self.split_indices:
            log("Starting split operation...")
            self._preprocess_split_doc()
            log("Split complete.")
        if self.trim_end:
            log("Starting trim operation...")
            self._preprocess_trim_doc()
            log("Trim complete.")
        if self.keep_original.startswith("y"):
            self.file_in.unlink()
            log("Removed original file.")
