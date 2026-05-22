"""Pure coercion helpers consumed by the docx and pdf parsers.

Each helper takes a string from a docx cell or a normalized PDF AcroForm field
(see pdf_parser._normalize_field_values in sibling plan `pdf`) and returns the
v3-typed equivalent. Failures soft-fail (log.warning + return a schema-default-
shaped value), never raise — the parser-layer error policy (spec §5.5) reserves
hard fails for FileNotFoundError, OSError from the underlying library, and
parse_json's schema-validation wrap.

JSON parsing does NOT use this module: Pydantic's own validators handle every
coercion path on model_validate_json.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation

from pydantic import ValidationError

from trust_generator.v3.schema import Address, PersonReference

log = logging.getLogger(__name__)

# Long-form date formats tried after ISO and MM/DD/YYYY. Order matters:
# longer / more-specific patterns first to prevent strptime accepting a
# shorter pattern on a longer string.
_DATE_FORMATS: tuple[str, ...] = (
    "%m/%d/%Y",
    "%B %d, %Y",
    "%b %d, %Y",
)

# Placeholder-prefix pattern for §5.4.4: strips a leading bracketed hint
# (e.g., '[Spouse name] ') from the start of a person-reference cell.
_PLACEHOLDER_PREFIX_RE = re.compile(r"^\[[^\]]+\]\s*")


def _to_date(text: str) -> date | None:
    """Coerce a docx cell / PDF field to a date (§5.4.1).

    Try ISO first (`date.fromisoformat`), then each `_DATE_FORMATS` pattern in
    order via `datetime.strptime`. On all-fail: return None + warn.
    """
    if not text or not text.strip():
        return None
    stripped = text.strip()

    try:
        return date.fromisoformat(stripped)
    except ValueError:
        pass

    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(stripped, fmt).replace(tzinfo=UTC).date()
        except ValueError:
            continue

    log.warning("could not parse date %r", text)
    return None


def _to_decimal(text: str) -> Decimal | None:
    """Coerce a docx cell / PDF field to a Decimal (§5.4.2).

    Strips '$', thousands ',', trailing '%', surrounding whitespace.
    On parse failure (unparseable / empty): return None + warn. Returning
    None rather than Decimal(0) keeps a genuine zero value distinguishable
    from a parse failure — the parser-level decision (substitute the target
    field's own default, or apply the §5.4.2 share-percent row-drop) belongs
    to the docx/pdf caller, which consumes the None directly.

    The '$' is removed via `.replace`, not `.lstrip`, so a sign-prefixed
    currency value (e.g. "-$50.00") parses correctly — `lstrip("$")` would
    leave the '$' in place because it follows the leading '-'.
    """
    if not text or not text.strip():
        return None
    stripped = text.strip().replace("$", "").rstrip("%").replace(",", "").strip()
    try:
        return Decimal(stripped)
    except InvalidOperation:
        log.warning("could not parse decimal %r", text)
        return None


def _to_address(text: str) -> Address:
    """Coerce a docx cell free-text address to an Address (§5.4.3).

    Heuristic comma-split:
      3 parts -> (street, city, "state zip")
      4 parts -> (street, city, "state zip", country)
    Each "state zip" element is split on the last whitespace.
    On unparseable input (zero or one comma): street = full text, other fields
    empty + warn. latitude / longitude are NEVER set here (spec §5.4.3); the
    geocoder is invoked separately by the GUI / generators.
    """
    if not text:
        return Address()
    parts = [p.strip() for p in text.split(",")]
    if len(parts) < 3:
        log.warning("could not parse address %r", text)
        return Address(street=text.strip())

    if len(parts) > 4:
        # 4 parts is the documented maximum (street, city, state-zip, country).
        # More than that means the heuristic is mis-shaping the input — e.g. a
        # second street line ("Apt 4") is silently absorbed as the city. Surface
        # it without changing the soft-fail return (spec §5.5).
        log.warning(
            "address %r has %d comma-separated parts; expected 3 or 4 — "
            "heuristic split may be mis-shaped",
            text,
            len(parts),
        )

    street = parts[0]
    city = parts[1]
    state_zip = parts[2]

    # Split "state zip" on the last whitespace.
    state_zip_tokens = state_zip.rsplit(None, 1)
    if len(state_zip_tokens) == 2:
        state, zip_code = state_zip_tokens
    else:
        state, zip_code = state_zip, ""

    # Omit `country` unless a 4th part is present: passing country="" would
    # clobber the schema default Address.country="US" (schema.py).
    if len(parts) >= 4:
        return Address(
            street=street,
            city=city,
            state=state,
            zip_code=zip_code,
            country=parts[3],
        )
    return Address(
        street=street,
        city=city,
        state=state,
        zip_code=zip_code,
    )


def _to_person_reference(text: str) -> PersonReference:
    """Coerce a docx cell name to a PersonReference (§5.4.4).

    Steps:
      1. Strip a leading bracketed placeholder hint (e.g., '[Spouse name]').
      2. If the result is empty (zero tokens), return entity form directly —
         PersonReference's `_validate_name` guard is `if v and …`, so it does
         not fire for empty strings; the entity branch must be reached explicitly.
      3. Try PersonReference(full_legal_name=name). On the schema's
         two-token-name validator failure (one-token name, i.e., len < 2),
         re-construct as PersonReference(is_entity=True, entity_name=name,
         full_legal_name="").

    Note: multi-token entity detection (e.g., "ABC Corporation") is NOT done
    here — that belongs to the §5.4.9 CorporateTrustee suffix heuristic inside
    `_apply_post_merge_resolution` (docx-6 territory).
    """
    if text is None:
        text = ""
    stripped = _PLACEHOLDER_PREFIX_RE.sub("", text).strip()

    # Empty input → entity with empty entity_name (zero tokens, entity branch fires).
    if not stripped:
        return PersonReference(is_entity=True, entity_name="", full_legal_name="")

    try:
        return PersonReference(full_legal_name=stripped)
    except ValidationError as exc:
        # Only the §5.4.4 trap is a soft-fail: the schema's two-or-more-token
        # `full_legal_name` validator (schema.py `_validate_name`). Any other
        # PersonReference validation failure is an unrelated schema break and
        # must propagate, not be silently reinterpreted as an entity.
        if not _is_two_token_name_failure(exc):
            raise
        log.warning(
            "name %r is a one-token name; reconstructing as an entity reference",
            stripped,
        )
        return PersonReference(
            is_entity=True,
            entity_name=stripped,
            full_legal_name="",
        )


def _is_two_token_name_failure(exc: ValidationError) -> bool:
    """True iff `exc` is exactly the `full_legal_name` two-token validator failure.

    Pydantic v2 wraps the `ValueError` raised by `PersonReference._validate_name`
    into a `ValidationError` whose error entry has `loc == ("full_legal_name",)`
    and a `msg` carrying the validator's text. Matching both `loc` and the msg
    substring keeps the catch narrow — a `value_error` on any other field (an
    unrelated schema break) does not match and is re-raised by the caller.
    """
    return any(
        err.get("loc") == ("full_legal_name",)
        and "two or more tokens" in err.get("msg", "")
        for err in exc.errors()
    )
