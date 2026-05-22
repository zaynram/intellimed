"""ExtractionTrace, FieldExtraction, ExtractionResult, INCOMPLETE sentinel."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Final

from pydantic import BaseModel, ConfigDict, Field, model_validator

from trust_generator.v3.extraction.markers import (
    IncompleteUntilValidated,
    RawSelfReport,
)
from trust_generator.v3.schema import TrustData

INCOMPLETE: Final[object] = object()
"""Module-level sentinel for ``FieldExtraction.normalized_value`` when
extraction completed but normalization against the target TrustData
field type has not yet been validated.

Compared via identity (``field.normalized_value is INCOMPLETE``), never
by equality. The sentinel is not exported via ``__all__``; consumers
import it explicitly.
"""


class FieldExtraction(BaseModel):
    """A single per-field extraction record.

    ``field_path`` uses the dotted-path convention shared with
    ``Diagnostic.field_path`` (e.g., 'children[0].full_legal_name',
    'real_property[2].value'). The match is deliberate: a single
    convention across both surfaces keeps GUI anchor logic uniform.
    The path is resolved against the paired TrustData via
    ``extraction.paths.resolve`` at synthesis time; paths that no
    longer resolve are filtered as stale.

    ``field_path`` MUST be unique within an ``ExtractionTrace``
    (data-integrity invariant; enforced at construction by the
    ``_field_paths_are_unique`` model-validator, with ``verify_field``
    re-checking as defense-in-depth).

    Verification is bound to the value at verify time. If ``TrustData``
    is mutated to a different value at the same path AFTER
    verification, the verification flag is not invalidated by the
    mutation; the trace remains a faithful record of "the paralegal
    confirmed this field was correct at the time of verification."
    Surfacing post-verification divergence to the paralegal is a
    consumer-layer (GUI/CLI) concern; the trace itself does not detect
    it.
    """

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    field_path: str
    raw_value: str
    normalized_value: Annotated[object, IncompleteUntilValidated] | None = None
    illegible: bool = False
    confidence_self_report: Annotated[float, RawSelfReport] | None = None
    verified: bool = False
    verified_at: datetime | None = None

    @model_validator(mode="after")
    def _illegible_excludes_normalized_value(self) -> FieldExtraction:
        """Reject illegible=True alongside a non-None normalized_value."""
        if self.illegible and self.normalized_value is not None:
            msg = (
                "FieldExtraction invariant violated: illegible=True is mutually "
                "exclusive with a non-None normalized_value (field_path="
                f"{self.field_path!r})"
            )
            raise ValueError(msg)
        return self


class ExtractionTrace(BaseModel):
    """A list of per-field extraction records produced by a single
    ``extract()`` call, with verify-mutation methods.

    The trace is the spine of the verification, provenance, and
    forward-compatible confidence architecture. It is paired with a
    ``TrustData`` (in ``ExtractionResult``) and consumed by
    ``diagnose()`` via the ``extraction`` namespace in eval_context
    (added in 9c).
    """

    model_config = ConfigDict(extra="forbid")

    fields: list[FieldExtraction] = Field(default_factory=list)
    backend_id: str
    """``<backend>:<model>`` convention (e.g., ``ollama:qwen2.5vl:7b``)."""
    extracted_at: datetime

    @model_validator(mode="after")
    def _field_paths_are_unique(self) -> ExtractionTrace:
        """Reject duplicate field_path values at construction time.

        field_path MUST be unique within an ExtractionTrace
        (data-integrity invariant; see FieldExtraction docstring).
        """
        seen: set[str] = set()
        for fe in self.fields:
            if fe.field_path in seen:
                msg = (
                    "ExtractionTrace invariant violated: duplicate FieldExtraction "
                    f"entries for field_path={fe.field_path!r}"
                )
                raise ValueError(msg)
            seen.add(fe.field_path)
        return self

    def verify_field(self, field_path: str, *, at: datetime | None = None) -> None:
        """Mark the field at ``field_path`` as verified.

        Raises ``KeyError`` if no FieldExtraction has a matching
        ``field_path``. Raises ``ValueError`` if multiple do
        (data-integrity invariant: ``field_path`` is unique within a
        trace).
        """
        matches = [fe for fe in self.fields if fe.field_path == field_path]
        if not matches:
            msg = f"no FieldExtraction matches field_path={field_path!r}"
            raise KeyError(msg)
        if len(matches) > 1:
            msg = (
                f"duplicate FieldExtraction entries for field_path={field_path!r}: "
                f"trace data-integrity invariant violated"
            )
            raise ValueError(msg)
        target = matches[0]
        target.verified = True
        target.verified_at = at if at is not None else datetime.now(UTC)


class ExtractionResult(BaseModel):
    """The pairing returned by every ``ExtractionProtocol.extract()`` call.

    Both fields are required.
    """

    model_config = ConfigDict(extra="forbid")

    data: TrustData
    trace: ExtractionTrace


__all__: tuple[str, ...] = (
    "ExtractionResult",
    "ExtractionTrace",
    "FieldExtraction",
)
