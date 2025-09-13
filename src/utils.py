from __future__ import annotations

import sys
import wx
import typing

if typing.TYPE_CHECKING:
    from .types import *


def log(*lines: object) -> None:
    print(*lines, sep=chr(10), file=sys.stdout, flush=True)


def error(
    *lines: object,
    exception: Exception | type[Exception] | None = None,
    fatal: bool = True,
) -> None:
    if exception:
        print(f"\nOriginal Exception: {exception}\n")

    print(*lines, sep=chr(10), file=sys.stderr, flush=True)

    if fatal:
        sys.exit(1)


def confirm(prompt: str) -> bool:
    dialogue = wx.MessageDialog(
        parent=None,
        message=prompt,
        caption="Confirmation",
        style=wx.YES_NO | wx.ICON_QUESTION,
    )
    choice = dialogue.ShowModal()
    dialogue.Destroy()
    return choice == wx.ID_YES


class track[I]:
    total: ClassVar[int] = 100

    @classmethod
    def set_default_total(cls, n: int) -> None:
        cls.total = n

    iterator: Iterator[I]
    description: str
    current: int = 0

    @property
    def progress(self) -> str:
        return f"progress: {self.current}/{self.total}\n"

    def __init__(self, iterable: Iter[I], desc: str, total: int | None = None) -> None:
        self.total = (
            self.total
            if not total
            else total
            if not isinstance(iterable, typing.Sized)
            else len(iterable)
        )
        self.description = desc
        self.iterator = iter(iterable)

    def _write_progress(
        self,
        *,
        advance: int | None = None,
        complete: bool = False,
    ) -> None:
        if complete:
            self.current = self.total
        elif self.current == self.total:
            self.total += 1
        elif advance:
            self.current += advance
        log(self.progress)

    def __iter__(self) -> Generator[I]:
        log(self.description)
        try:
            while True:
                yield next(self.iterator)
                self._write_progress(advance=1)
        except StopIteration:
            self._write_progress(complete=True)
            del self.iterator, self.current, self.total, self.description
