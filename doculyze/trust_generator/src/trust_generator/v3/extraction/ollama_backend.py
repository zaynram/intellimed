"""OllamaBackend: ExtractionProtocol implementation via local Ollama."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import httpx
import ollama
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from trust_generator.v3.extraction.prompt import build_intake_prompt
from trust_generator.v3.extraction.protocol import ExtractionError
from trust_generator.v3.extraction.trace import (
    INCOMPLETE,
    ExtractionResult,
    ExtractionTrace,
    FieldExtraction,
)
from trust_generator.v3.schema import (
    BeneficiaryShare,
    GrantorInfo,
    OtherBeneficiary,
    TrustData,
)

if TYPE_CHECKING:
    from trust_generator.v3.extraction.protocol import SourceRef


class FieldDiag(BaseModel):
    """Per-field illegibility/note channel emitted by the model alongside data.

    Spec §7.3. Both fields default to "no signal" — the parser MUST
    NOT emit an envelope where ``illegible=True`` coexists with a
    populated data field on the same envelope row. The mapping in
    ``_envelope_to_extraction_result`` honors this invariant when
    constructing FieldExtraction entries.
    """

    model_config = ConfigDict(extra="forbid")

    illegible: bool = False
    note: str | None = Field(default=None, max_length=240)


class GrantorEnvelope(BaseModel):
    """Per-grantor generation envelope shape (mirrors a TrustData subset).

    Spec §7.3 — flatter, OCR-shaped mirror of the TrustData grantor
    submodel. Each data field has a sibling ``*_diag`` per-field
    illegibility/note channel. Every field is Optional because OCR
    extraction may produce ``None`` for absent or illegible fields
    without invalidating the envelope as a whole.
    """

    model_config = ConfigDict(extra="forbid")

    full_legal_name: str | None = None
    full_legal_name_diag: FieldDiag = Field(default_factory=FieldDiag)
    date_of_birth: str | None = None
    date_of_birth_diag: FieldDiag = Field(default_factory=FieldDiag)


class BeneficiaryEnvelope(BaseModel):
    """Per-beneficiary generation envelope shape.

    ``share_percent`` is typed ``str`` (raw transcription, e.g., "50",
    "fifty", "50%") rather than ``Decimal`` so that OCR-time
    transcription drift does not invalidate the envelope at validation
    time. Normalization to a numeric type is the consumer's concern
    (the cycle 9b-3 envelope-to-TrustData mapping handles the
    conversion under ``IncompleteUntilValidated`` discipline).
    """

    model_config = ConfigDict(extra="forbid")

    full_legal_name: str | None = None
    full_legal_name_diag: FieldDiag = Field(default_factory=FieldDiag)
    relationship: str | None = None
    relationship_diag: FieldDiag = Field(default_factory=FieldDiag)
    share_percent: str | None = None
    share_percent_diag: FieldDiag = Field(default_factory=FieldDiag)


class GenerationEnvelope(BaseModel):
    """Constrained-decoding envelope for OllamaBackend.

    CRITICAL: ``reasoning`` MUST be the first field declared. Pydantic
    v2 preserves declaration order in ``model_json_schema()``; grammar-
    constrained decoding generates fields in schema declaration order.
    A leading string-typed reasoning field lets the model "think aloud"
    before committing to typed values, mitigating hallucination on
    illegible inputs. The cycle 9b-1 schema field-order test pins this
    discipline at the unit layer; task 9b-5 pins it at the integration
    layer against live model output.

    Reordering or removing ``reasoning`` is a §7.4 amendment, not a
    refactor. See ``docs/session-notes/2026-05-11-envelope-complexity-ceiling.md``
    for the empirical complexity-ceiling evidence gathered at chore #14 fulfillment.

    The data-fields subset (``grantors``, ``beneficiaries``) is
    deliberately minimal for v3.0 (per plan 9b Q4). Full TrustData
    mirror lands in a follow-up if cycle 9b-3's envelope-to-TrustData
    mapping reveals coverage gaps that the subset cannot resolve.
    """

    model_config = ConfigDict(extra="forbid")

    reasoning: str = Field(max_length=2000)
    grantors: list[GrantorEnvelope] = Field(default_factory=list)
    beneficiaries: list[BeneficiaryEnvelope] = Field(default_factory=list)


class OllamaBackend:
    """ExtractionProtocol implementation against a local Ollama server.

    Pinned dependency: ``ollama >= 0.6.1`` (per spec §7.1, added in
    plan 9a Task 5). Pinned schema delivery: ``format=
    GenerationEnvelope.model_json_schema()`` (spec §7.3). Pinned
    determinism: ``options={'temperature': 0}`` (spec §7.4). Pinned
    field-order discipline: ``reasoning`` is the first field on
    ``GenerationEnvelope`` (spec §7.4 + cycle 9b-1 schema test +
    task 9b-5 live JSON-key-order pin).

    Recommended model: ``qwen2.5vl:7b``. Chore #13 empirical evaluation
    (2026-04-30) measured 77.1% per-field accuracy on a 9-fixture
    handwritten-intake corpus vs. 37.0% for ``minicpm-v``; MiniCPM-V also
    failed the §8.1 illegibility-flag test (silently invented values for
    unreadable fields). Chore #29 (2026-05-12) extended the eval to
    ``qwen2.5vl:3b`` (48.9% MATCH; high hallucination rate; runner-stops
    on §8.1 illegibility fixture — not recommended). Chore #33 (2026-05-13)
    closed out the broader architecture-class sweep with five more
    candidates: ``moondream:1B`` (0.8% MATCH; 82-hallucination explosion
    on §8.3 absent-fields fixture — most paralegal-hostile failure mode
    observed), ``llava-llama3:8b`` (5.9% MATCH; honest-OMIT failure
    pattern but unusable accuracy; CLIP-ViT-L vision tower not trained
    on document understanding), ``gemma3:{4b,12b}`` (runner OOM in
    worst-case-graph reservation — Ollama 0.9 + SYCL0 budget gap,
    infrastructure-bound not model-quality bound),
    ``granite3.2-vision:2b`` (55.9% MATCH, **zero hallucinations**,
    strongest *positive* finding of the sweep — but disqualified on
    wall-clock at 17:56 total + a 600s timeout on `pages/hurried.jpg`),
    and ``llava:7b`` (smoke-tested cleanly at ~6-34s chat-mode but
    >17min on the structured-extraction path before being killed).
    Both granite + llava expose a structural finding: grammar-constrained
    decoding under Ollama 0.9 is fragile for models without
    document-structured pretraining — the `format=<json_schema>` pin
    forces the runner's sampler to navigate a JSON grammar lattice, and
    models with strong free-form priors re-sample pathologically.
    Qwen2.5-VL is the only family that aligns naturally with this
    grammar. 7b recommendation stands across four evaluation rounds and
    six architecture families.
    The constructor accepts ``model`` as configuration — do NOT hard-code;
    production callers pass the model name explicitly. See
    ``docs/session-notes/2026-04-30-vision-model-eval.md`` for full
    methodology, per-fixture detail, and addenda for chores #29 + #33.
    """

    def __init__(
        self,
        model: str,
        client: ollama.Client | None = None,
        prompt_builder: Callable[[], str] | None = None,
    ) -> None:
        self.model = model
        self.client = client if client is not None else ollama.Client()
        self.prompt_builder = (
            prompt_builder if prompt_builder is not None else build_intake_prompt
        )

    def extract(self, source: SourceRef) -> ExtractionResult:
        """Extract a TrustData and ExtractionTrace from one source.

        Spec §5.4 — failure modes raise ``ExtractionError`` (cycle 9b-4
        adds the error contract). Per-field illegibility, missing fields,
        and low-confidence transcriptions are NOT failures: they land on
        the trace as ``FieldExtraction`` entries with ``illegible=True``
        and/or ``normalized_value=None``. Spec §7.3.4 — TrustData stays
        default-constructed; the OCR'd values are evidence carried on
        the trace, not facts asserted into TrustData.
        """
        prompt = self.prompt_builder()
        image_path_str = str(source.resolve())

        try:
            response = self.client.chat(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                        "images": [image_path_str],
                    }
                ],
                format=GenerationEnvelope.model_json_schema(),
                options={"temperature": 0},
            )
        except ollama.ResponseError as e:
            raise ExtractionError(
                f"Ollama returned error status={e.status_code}: {e}"
            ) from e
        except ConnectionError as e:
            # Production path when Ollama is unreachable: the library
            # catches httpx.ConnectError and re-raises Python's builtin
            # ConnectionError (ollama/_client.py:134-135).
            raise ExtractionError(
                f"Cannot connect to Ollama server: {e}"
            ) from e
        except httpx.HTTPError as e:
            # Residual transport errors not wrapped by ollama-python:
            # timeouts, read/write errors, protocol errors.
            raise ExtractionError(
                f"Network error contacting Ollama: {e}"
            ) from e
        except ValueError as e:
            # ollama-python's Image.serialize_model raises ValueError for
            # missing image paths (ollama/_types.py:178-179) and for
            # malformed base64/path inputs. Wrap as ExtractionError so
            # paralegals get a uniform error class for extract() failures.
            raise ExtractionError(
                f"Image path or request construction error: {e}"
            ) from e

        try:
            envelope = GenerationEnvelope.model_validate_json(
                response.message.content or ""
            )
        except ValidationError as e:
            raise ExtractionError(
                f"Malformed envelope from model {self.model}: {e}"
            ) from e

        return _envelope_to_extraction_result(envelope, model=self.model)


def _map_grantor_envelope(
    grantors: list[GrantorEnvelope],
) -> tuple[list[FieldExtraction], bool]:
    """Map envelope.grantors → trace fields under 'grantor.*' / 'co_grantor.*'.

    Returns (fields, needs_co_grantor) — needs_co_grantor signals to the
    caller that ``TrustData.co_grantor`` must be instantiated. Per spec
    §7.3.1, envelope.grantors[0] collapses onto ``grantor`` and [1] onto
    ``co_grantor``; entries beyond index 1 are ignored at this layer
    (the envelope subset is bounded for v3.0 per Q4).
    """
    fields: list[FieldExtraction] = []
    grantor_paths = ("grantor", "co_grantor")
    for idx, grantor in enumerate(grantors[:2]):
        prefix = grantor_paths[idx]
        if (
            grantor.full_legal_name is not None
            or grantor.full_legal_name_diag.illegible
        ):
            illegible = grantor.full_legal_name_diag.illegible
            fields.append(
                FieldExtraction(
                    field_path=f"{prefix}.full_legal_name",
                    raw_value=grantor.full_legal_name or "",
                    normalized_value=None if illegible else grantor.full_legal_name,
                    illegible=illegible,
                )
            )
        if (
            grantor.date_of_birth is not None
            or grantor.date_of_birth_diag.illegible
        ):
            illegible = grantor.date_of_birth_diag.illegible
            fields.append(
                FieldExtraction(
                    field_path=f"{prefix}.date_of_birth",
                    raw_value=grantor.date_of_birth or "",
                    # Date normalization deferred (spec §7.3.3): INCOMPLETE sentinel
                    # for legible-but-not-yet-normalized; None for illegible (the
                    # _illegible_excludes_normalized_value validator rejects non-None
                    # alongside illegible=True).
                    normalized_value=None if illegible else INCOMPLETE,
                    illegible=illegible,
                )
            )
    return fields, len(grantors) >= 2


def _map_beneficiary_envelope(
    beneficiaries: list[BeneficiaryEnvelope],
) -> tuple[list[FieldExtraction], list[OtherBeneficiary], list[BeneficiaryShare]]:
    """Map envelope.beneficiaries → trace fields + TrustData lists.

    Spec §7.3.2 conservative classification fallback: every envelope
    beneficiary lands in ``other_beneficiaries[i]`` and the paired
    ``beneficiary_shares[i]`` uses recipient_ref convention
    ``other_beneficiaries[{i}]``. Returns (trace_fields, others, shares)
    so the caller can attach lists onto a freshly constructed TrustData
    in one assignment.
    """
    fields: list[FieldExtraction] = []
    others: list[OtherBeneficiary] = []
    shares: list[BeneficiaryShare] = []
    for j, beneficiary in enumerate(beneficiaries):
        others.append(OtherBeneficiary())
        shares.append(BeneficiaryShare(recipient_ref=f"other_beneficiaries[{j}]"))

        if (
            beneficiary.full_legal_name is not None
            or beneficiary.full_legal_name_diag.illegible
        ):
            illegible = beneficiary.full_legal_name_diag.illegible
            fields.append(
                FieldExtraction(
                    field_path=f"other_beneficiaries[{j}].full_legal_name",
                    raw_value=beneficiary.full_legal_name or "",
                    normalized_value=None if illegible else beneficiary.full_legal_name,
                    illegible=illegible,
                )
            )
        if (
            beneficiary.relationship is not None
            or beneficiary.relationship_diag.illegible
        ):
            illegible = beneficiary.relationship_diag.illegible
            fields.append(
                FieldExtraction(
                    # Free-text fallback (spec §7.3.1): typed relationship enum
                    # stays default; relationship_other carries the verbatim string.
                    field_path=f"other_beneficiaries[{j}].relationship_other",
                    raw_value=beneficiary.relationship or "",
                    normalized_value=None if illegible else beneficiary.relationship,
                    illegible=illegible,
                )
            )
        if (
            beneficiary.share_percent is not None
            or beneficiary.share_percent_diag.illegible
        ):
            illegible = beneficiary.share_percent_diag.illegible
            fields.append(
                FieldExtraction(
                    field_path=f"beneficiary_shares[{j}].share_percent",
                    raw_value=beneficiary.share_percent or "",
                    # Numeric normalization deferred (spec §7.3.3): INCOMPLETE sentinel
                    # for legible-but-not-yet-normalized.
                    normalized_value=None if illegible else INCOMPLETE,
                    illegible=illegible,
                )
            )
    return fields, others, shares


def _envelope_to_extraction_result(
    envelope: GenerationEnvelope, *, model: str
) -> ExtractionResult:
    """Map a validated GenerationEnvelope to an ExtractionResult.

    Spec §7.3.1-§7.3.4 — collapse envelope.grantors[0..1] onto
    TrustData.grantor + co_grantor; map envelope.beneficiaries[i] to
    other_beneficiaries[i] (conservative classification fallback per
    §7.3.2); emit beneficiary_shares[i] paired by deterministic
    recipient_ref. TrustData is default-constructed apart from
    co_grantor instantiation when needed; OCR'd values land on the
    trace via FieldExtraction (raw_value), with normalized_value=None
    (illegible branch) or normalization deferred under
    IncompleteUntilValidated discipline (legible branch).

    Per spec §8.3 omit-if-absent: a FieldExtraction is emitted only
    when the envelope's data field is non-None OR the sibling diag's
    illegible flag is set. Both branches signal "the model attempted
    this field"; absent (data null AND diag quiet) yields no entry.
    """
    data = TrustData()
    grantor_fields, needs_co_grantor = _map_grantor_envelope(envelope.grantors)
    if needs_co_grantor:
        data.co_grantor = GrantorInfo()
    beneficiary_fields, others, shares = _map_beneficiary_envelope(
        envelope.beneficiaries
    )
    data.other_beneficiaries = others
    data.beneficiary_shares = shares

    trace = ExtractionTrace(
        fields=[*grantor_fields, *beneficiary_fields],
        backend_id=f"ollama:{model}",
        extracted_at=datetime.now(UTC),
    )

    return ExtractionResult(data=data, trace=trace)
