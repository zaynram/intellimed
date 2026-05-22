__all__ = ["if_win"]

import sys
from collections.abc import Callable


def if_win(func: Callable[[], None]) -> None:
    if sys.platform != "win32":
        msg = f"Windows is required to perform {getattr(func, '__name__', 'this operation')}"
        raise OSError(msg)
    else:
        return func()
