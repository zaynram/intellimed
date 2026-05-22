from __future__ import annotations

import importlib
from argparse import ArgumentParser
from collections.abc import Callable
from functools import wraps
from typing import Any, final

from .platform import if_win


class GooeyParser(ArgumentParser):
    pass


def import_deps():
    global GooeyParser, Gooey
    gooey = importlib.import_module("Gooey")
    GooeyParser = gooey.GooeyParser
    Gooey = gooey.Gooey


if_win(import_deps)

DEFAULT_GOOEY_ARGS = final({
    "header_show_help": True,
    "hide_progress_msg": True,
    "timing_options": {
        "show_time_remaining": True,
        "hide_time_remaining_on_complete": True,
    },
    "progress_regex": r"^progress: (?P<current>\d+)/(?P<total>\d+)$",
    "progress_expr": "current / total * 100",
    "default_size": (1200, 600),
    "return_to_config": False,
    "show_failure_modal": True,
    "tabbed_groups": True,
    "show_restart_button": False,
    "run_validation": True,
    "group_by_type": True,
    "show_preview_warning": False,
})


def gooify[**P, T](
    name: str,
    desc: str = "",
    *,
    basic: bool = False,
    **kwds: object,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    gooey_dict: dict[str, Any] = DEFAULT_GOOEY_ARGS.copy()
    gooey_dict.update({
        **kwds,
        "advanced": not basic,
        "program_name": name,
        "program_description": desc,
    })

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        @Gooey(**gooey_dict)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            return func(*args, **kwargs)

        return wrapper

    return decorator


def gooparse(desc: str) -> Any | ArgumentParser:
    return GooeyParser(description=desc)
