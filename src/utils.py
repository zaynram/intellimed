from __future__ import annotations

from datetime import datetime, date
from pathlib import Path

import json
import sys
import wx
import functools
import typing

if typing.TYPE_CHECKING:
    from .typeshed import *

ROOT_DIR = Path(__file__).parent.parent.resolve(strict=True)

DATA_DIR = (ROOT_DIR / "data").resolve(strict=True).as_posix()


def _fmt_time(dt: datetime) -> str:
    return dt.strftime("%I:%M:%S %p")


def _diff_time(start: datetime, end: datetime | None = None) -> float:
    return ((end or datetime.now()) - start).total_seconds()


def timings(
    *,
    disp_name: str | None = None,
    strip_prefix: str = "_",
):
    def decorator[**P, T](func: Callable[P, T]) -> Callable[P, T]:
        nonlocal disp_name

        disp_name = disp_name or chr(32).join(
            x.strip().capitalize() for x in func.__name__.lstrip(strip_prefix).split("_")
        )

        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            try:
                started_at = datetime.now()
                console.log(f"[{disp_name}]: started at {_fmt_time(started_at)}")

                result = func(*args, **kwargs)

                ended_at = datetime.now()
                console.log(f"[{disp_name}]: completed at {_fmt_time(ended_at)}")

                duration = _diff_time(started_at, ended_at)
                if duration > 1:
                    console.log(f"[{disp_name}]: took {duration} seconds")

                return result
            except Exception as e:
                console.error(f"An unhandled exception occured in {func.__name__}", e)
                raise

        return wrapper

    return decorator


def retry(
    *,
    max_retries: int,
    before_retry: Callable[[], Any] | None = None,
):
    attempts = 0

    def decorator[**P, T](func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                nonlocal attempts

                if attempts <= max_retries:
                    attempts += 1
                    before_retry and before_retry()
                    return wrapper(*args, **kwargs)

                console.error(exception=e)
                raise

        return wrapper

    return decorator


LOG_DIR = (ROOT_DIR / "logs").resolve(strict=True)


def get_dump_file() -> Path:
    return LOG_DIR / f"dump_{datetime.now().timestamp()}.log"


def is_serializable(x: object) -> bool:
    return hasattr(x, "__str__") or hasattr(x, "__repr__")


class dumplocals[**P, T]:
    """
    A decorator class that captures local variables of a decorated function
    if it raises an exception.
    """

    def __init__(self, func: Callable[P, T]):
        """
        Initializes the decorator with the function to be decorated.
        """
        self._locals = {}
        self.func = func

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> T:
        """
        The main decorator logic. Sets up a tracer and calls the function.
        """
        # We need to save the original profile function to restore it later
        original_profile_func = sys.getprofile()

        def tracer(frame, event, arg):
            """
            The tracer function that captures locals on return or exception.
            """
            # Check for the frame of the decorated function itself
            if frame.f_code is self.func.__code__:
                if event == "return":
                    # For a normal return, capture the locals from the frame
                    self._locals = frame.f_locals.copy()
                elif event == "exception":
                    # When an exception is raised, capture the locals from the frame
                    self._locals = frame.f_locals.copy()

            # This is important to not break other profilers
            if original_profile_func:
                original_profile_func(frame, event, arg)

        sys.setprofile(tracer)
        try:
            res = self.func(*args, **kwargs)
        except Exception as e:
            self.write_locals()
            raise SystemExit from e
        finally:
            sys.setprofile(original_profile_func)
            self.clear_locals()

        return res

    def clear_locals(self):
        """
        Clears the captured local variables.
        """
        self._locals = {}

    def write_locals(self, file: Path | None = None):
        file = file or get_dump_file()
        file.write_text(
            json.dumps(
                self.locals,
                indent=4,
                skipkeys=True,
                default=str,
                sort_keys=True,
            )
        )
        console.log(f"Locals dumped to '{file}'")

    @property
    def locals(self):
        """
        Returns the captured local variables.
        """
        return self._locals


class argtype:
    @staticmethod
    def datestring(value) -> date:
        if not value:
            raise TypeError("Date is a required field.")

        if isinstance(value, date):
            return value

        try:
            return date.fromisoformat(value)
        except Exception:
            raise TypeError("Date must be in ISO format.")

    @staticmethod
    def boolstring(value) -> bool:
        if isinstance(value, str):
            return str(value) == "True"
        raise TypeError("Must be either 'True' or 'False'.")

    @staticmethod
    def nowhitespaces(value) -> str:
        if isinstance(value, str) and " " not in value.strip():
            return value.strip()
        raise TypeError("Must be a string not containing any whitespaces.")

    @staticmethod
    def integerlist(value) -> list[int]:
        try:
            return [int(n.strip()) for n in str(value).split(",")]
        except Exception:
            raise TypeError("All values in the list must be integers.")


class console:
    NEWLINE = typing.final(chr(13) + chr(10) if sys.platform == "win32" else chr(10))
    FILE = typing.final(LOG_DIR / "latest-execution.log")
    WHITELIST = typing.final(["progress"])
    BLACKLIST = typing.final([
        "mupdf error",
        "image too small",
        "line cannot be recognized",
        "configuration",
        "file_info",
        "locals dumped",
    ])

    @classmethod
    def debug(cls, **kwds: object) -> None:
        for k, v in kwds.items():
            cls.log(f"[debug] {k}", f"\tvalue: {v}", f"\ttype: {type(v)}")

    @classmethod
    def json(
        cls,
        key: str | None = None,
        obj: JSONDict | None = None,
        *,
        indent: int = 4,
        **kwds: JSONSerializable,
    ) -> None:
        obj = {**(obj or {}), **kwds}
        data: JSONDict = obj if not key else {key: obj}
        cls.log(json.dumps(obj=data, indent=indent))

    @classmethod
    def log(cls, *lines: object) -> None:
        text = " ".join(str(line).lower() for line in lines)
        if all(item not in text for item in cls.WHITELIST) or any(
            item in text for item in cls.BLACKLIST
        ):
            with cls.FILE.open("a+t", encoding="utf-8") as f:
                print(*lines, sep=cls.NEWLINE, file=f)
        else:
            print(*lines, sep=cls.NEWLINE, file=sys.stdout, flush=True)

    @staticmethod
    def error(
        *lines: object,
        exception: Exception | type[Exception] | None = None,
        fatal: bool = False,
    ) -> None:
        exception and console.log(exception)
        lines and console.log(lines)
        fatal and sys.exit(1)

    @staticmethod
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
    GLOBAL_TOTAL: typing.ClassVar[int] = 100

    _total: int

    @property
    def total(self) -> int:
        return getattr(self, "_total", self.GLOBAL_TOTAL)

    @total.setter
    def total(self, value: int | None) -> None:
        self._total = value or self.GLOBAL_TOTAL

    iterator: Iterator[I]
    description: str
    current: int = 0

    @property
    def progress(self) -> str:
        return f"progress: {self.current}/{self.total}\n"

    def __init__(self, iterable: Iter[I], desc: str, total: int | None = None) -> None:
        self.total = total if not isinstance(iterable, typing.Sized) else len(iterable)
        self.description = desc
        self.iterator = iter(iterable)

    def _write_progress(
        self,
        *,
        advance: int | None = None,
        complete: bool = False,
    ) -> None:
        if complete:
            self.current = 0
            self.total = 100
        elif self.current == self.total:
            self.total += 1
        elif advance:
            self.current += advance
        console.log(self.progress)

    def __iter__(self) -> Generator[I]:
        console.log(self.description)
        try:
            while True:
                yield next(self.iterator)
                self._write_progress(advance=1)
        except StopIteration:
            self._write_progress(complete=True)
            del self.iterator, self.current, self._total, self.description
