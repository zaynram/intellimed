"""Path resolver for ``field_path`` strings against a TrustData (spec §5.7).

Supports attribute access (``grantor``, ``office.file_number``),
bracket indexing (``children[0]``), and chains
(``children[0].full_legal_name``). Returns ``(False, None)`` on any
unresolvable path, including pathological inputs.
"""

from __future__ import annotations

import re

_SEGMENT_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)(?:\[(\d+)\])?$")


def resolve(trust: object, field_path: str) -> tuple[bool, object]:
    """Walk ``field_path`` against ``trust`` and return (resolved, value).

    Returns ``(True, value)`` when the path resolves end-to-end. Returns
    ``(False, None)`` on any failure: missing attribute, out-of-range
    index, bracket on a non-list, or malformed segment syntax.
    """
    if not field_path:
        return (False, None)

    segments = field_path.split(".")
    if any(seg == "" for seg in segments):
        return (False, None)

    current: object = trust
    for segment in segments:
        match = _SEGMENT_RE.match(segment)
        if match is None:
            return (False, None)
        attr_name, index_str = match.group(1), match.group(2)

        if not hasattr(current, attr_name):
            return (False, None)
        current = getattr(current, attr_name)

        if index_str is not None:
            if not isinstance(current, list):
                return (False, None)
            index = int(index_str)
            if index >= len(current) or index < 0:
                return (False, None)
            current = current[index]

    return (True, current)


__all__ = ("resolve",)
