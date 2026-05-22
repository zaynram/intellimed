"""AnthropicBackend: ExtractionProtocol implementation against the
Anthropic Claude API.

Spec §6 (Public surface), §8 (Backend internals), §8.5 (Error mapping).
Mirrors ``ollama_backend.py``'s single-file layout: envelope models +
forked mappers + class + dual-mechanism seam, no shared helpers with
the Ollama path.
"""

from __future__ import annotations

import base64
import json
import mimetypes
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final, Literal, cast

import anthropic
from anthropic.types import (
    DocumentBlockParam,
    ImageBlockParam,
    MessageParam,
    OutputConfigParam,
    TextBlock,
    TextBlockParam,
    ThinkingConfigEnabledParam,
    ToolChoiceAutoParam,
    ToolParam,
    ToolUseBlock,
)
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pypdf import PdfReader
from pypdf.errors import PyPdfError

# Anthropic source-size limits — per-MIME, pinned at SDK pin time per spec §8.1
# and Anthropic's documented input constraints.
#
# PDFs: 32 MiB documented limit on document content blocks.
# Images: 5 MiB documented limit on image content blocks (image/jpeg,
#         image/png, image/gif, image/webp).
#
# At cycle 8 time only PDFs are in the allow-list; the image constant is
# unused until cycle 9 expands the allow-list. Defining both up-front
# keeps the dispatch structure in this cycle's Green so cycle 9 only
# expands the allow-list and adds a Red test.
_ANTHROPIC_PDF_SIZE_LIMIT_BYTES: Final[int] = 32 * 1024 * 1024  # 32 MiB
_ANTHROPIC_IMAGE_SIZE_LIMIT_BYTES: Final[int] = 5 * 1024 * 1024  # 5 MiB

# Anthropic PDF page-count cap — tiered by context window. 100 pages for
# 200K-context variants (claude-sonnet-4-6 default, claude-opus-4-5+),
# 600 for 1M-context variants. Plan A pins the 200K-context tier
# because the spec's indicative model is 200K. If a future session
# migrates to a 1M-context variant, this constant flips to 600 and the
# cycle 8 page-precheck test updates the boundary.
_ANTHROPIC_PDF_PAGE_LIMIT: Final[int] = 100

# MIME allow-list — PDFs + Anthropic-supported image types. Anthropic's
# docs name image/jpeg, image/png, image/gif, image/webp as supported.
# Cycle 9 (instrumentation) introduced this constant; cycle 8's generic
# size guard dispatches on its members per-MIME.
_ANTHROPIC_SUPPORTED_MIMES: Final[frozenset[str]] = frozenset(
    {
        "application/pdf",
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
    }
)
_ImageMediaType = Literal["image/jpeg", "image/png", "image/gif", "image/webp"]

if TYPE_CHECKING:
    from trust_generator.v3.extraction.protocol import SourceRef

from trust_generator.v3.extraction.prompt_anthropic import build_intake_prompt
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


class AnthropicFieldFlag(BaseModel):
    """Per-field illegibility marker.

    Spec §6: bare bool today; numeric confidence is deferred to 4.3c
    ConfidenceProtocol. The wrapper exists (rather than a raw bool
    inline on each parent envelope row) so 4.3c can add per-field
    signals without changing the parent envelope's schema shape.
    """

    model_config = ConfigDict(extra="forbid")

    illegible: bool = False


class AnthropicGrantorEnvelope(BaseModel):
    """Grantor fields + per-field illegibility flags."""

    model_config = ConfigDict(extra="forbid")

    full_legal_name: str | None = None
    full_legal_name_flag: AnthropicFieldFlag = Field(default_factory=AnthropicFieldFlag)
    date_of_birth: str | None = None
    date_of_birth_flag: AnthropicFieldFlag = Field(default_factory=AnthropicFieldFlag)


class AnthropicBeneficiaryEnvelope(BaseModel):
    """Beneficiary fields + per-field illegibility flags."""

    model_config = ConfigDict(extra="forbid")

    full_legal_name: str | None = None
    full_legal_name_flag: AnthropicFieldFlag = Field(default_factory=AnthropicFieldFlag)
    relationship: str | None = None
    relationship_flag: AnthropicFieldFlag = Field(default_factory=AnthropicFieldFlag)
    share_percent: str | None = None
    share_percent_flag: AnthropicFieldFlag = Field(default_factory=AnthropicFieldFlag)


class AnthropicGenerationEnvelope(BaseModel):
    """Top-level Anthropic envelope.

    Spec §6: no ``reasoning`` field (extended thinking carries the
    reasoning channel out-of-band); no ``overall_confidence`` (deferred
    to 4.3c ConfidenceProtocol per spec §2). Plain ``list[...]`` for
    sub-envelopes — Anthropic's structured-output mechanism has no
    GBNF key-order pin and no integer-keyed-dict workaround need.
    """

    model_config = ConfigDict(extra="forbid")

    grantors: list[AnthropicGrantorEnvelope] = Field(default_factory=list)
    beneficiaries: list[AnthropicBeneficiaryEnvelope] = Field(default_factory=list)


def _map_grantor_anthropic_envelope(
    grantors: list[AnthropicGrantorEnvelope],
) -> tuple[list[FieldExtraction], bool]:
    """Map envelope.grantors → trace fields under 'grantor.*' / 'co_grantor.*'.

    Spec §6 *Positional mapping semantics*: envelope.grantors[0] collapses
    onto ``grantor`` and [1] onto ``co_grantor``; entries beyond [1] are
    ignored at this layer. Returns ``(fields, needs_co_grantor)``.
    """
    fields: list[FieldExtraction] = []
    grantor_paths = ("grantor", "co_grantor")
    # needs_co_grantor gates on *content*, not list length: an empty
    # second envelope (grantors[1] with no populated field, no illegible
    # flag) must NOT materialize an empty co_grantor downstream. Snapshot
    # the field count before iterating index 1 and compare after.
    co_grantor_field_floor = 0
    needs_co_grantor = False
    for idx, grantor in enumerate(grantors[:2]):
        prefix = grantor_paths[idx]
        if idx == 1:
            co_grantor_field_floor = len(fields)
        if (
            grantor.full_legal_name is not None
            or grantor.full_legal_name_flag.illegible
        ):
            illegible = grantor.full_legal_name_flag.illegible
            fields.append(
                FieldExtraction(
                    field_path=f"{prefix}.full_legal_name",
                    raw_value=grantor.full_legal_name or "",
                    normalized_value=None if illegible else grantor.full_legal_name,
                    illegible=illegible,
                )
            )
        if grantor.date_of_birth is not None or grantor.date_of_birth_flag.illegible:
            illegible = grantor.date_of_birth_flag.illegible
            fields.append(
                FieldExtraction(
                    field_path=f"{prefix}.date_of_birth",
                    raw_value=grantor.date_of_birth or "",
                    # Date normalization deferred per spec §6 final paragraph:
                    # INCOMPLETE sentinel for legible-but-not-yet-normalized;
                    # None for illegible (the _illegible_excludes_normalized_value
                    # validator on FieldExtraction enforces the invariant).
                    normalized_value=None if illegible else INCOMPLETE,
                    illegible=illegible,
                )
            )
        if idx == 1 and len(fields) > co_grantor_field_floor:
            needs_co_grantor = True
    return fields, needs_co_grantor


def _map_beneficiary_anthropic_envelope(
    beneficiaries: list[AnthropicBeneficiaryEnvelope],
) -> tuple[list[FieldExtraction], list[OtherBeneficiary], list[BeneficiaryShare]]:
    """Map envelope.beneficiaries → trace fields + TrustData lists.

    Spec §6: conservative classification fallback (every envelope
    beneficiary lands in ``other_beneficiaries[j]`` with paired
    ``beneficiary_shares[j]``; ``recipient_ref=f"other_beneficiaries[{j}]"``).
    Relationship lands as the free-text fallback (``relationship_other``).
    """
    fields: list[FieldExtraction] = []
    others: list[OtherBeneficiary] = []
    shares: list[BeneficiaryShare] = []
    for j, beneficiary in enumerate(beneficiaries):
        others.append(OtherBeneficiary())
        shares.append(BeneficiaryShare(recipient_ref=f"other_beneficiaries[{j}]"))

        if (
            beneficiary.full_legal_name is not None
            or beneficiary.full_legal_name_flag.illegible
        ):
            illegible = beneficiary.full_legal_name_flag.illegible
            fields.append(
                FieldExtraction(
                    field_path=f"other_beneficiaries[{j}].full_legal_name",
                    raw_value=beneficiary.full_legal_name or "",
                    normalized_value=None
                    if illegible
                    else beneficiary.full_legal_name,
                    illegible=illegible,
                )
            )
        if (
            beneficiary.relationship is not None
            or beneficiary.relationship_flag.illegible
        ):
            illegible = beneficiary.relationship_flag.illegible
            fields.append(
                FieldExtraction(
                    field_path=f"other_beneficiaries[{j}].relationship_other",
                    raw_value=beneficiary.relationship or "",
                    normalized_value=None if illegible else beneficiary.relationship,
                    illegible=illegible,
                )
            )
        if (
            beneficiary.share_percent is not None
            or beneficiary.share_percent_flag.illegible
        ):
            illegible = beneficiary.share_percent_flag.illegible
            fields.append(
                FieldExtraction(
                    field_path=f"beneficiary_shares[{j}].share_percent",
                    raw_value=beneficiary.share_percent or "",
                    # Numeric normalization deferred per spec §6: INCOMPLETE
                    # sentinel for legible-but-not-yet-normalized.
                    normalized_value=None if illegible else INCOMPLETE,
                    illegible=illegible,
                )
            )
    return fields, others, shares


def _anthropic_envelope_to_extraction_result(
    envelope: AnthropicGenerationEnvelope, *, model: str
) -> ExtractionResult:
    """Map a validated AnthropicGenerationEnvelope to an ExtractionResult.

    Composer construction pattern (spec §6): default-construct
    ``TrustData()``; optionally instantiate ``co_grantor``; assign
    ``other_beneficiaries`` and ``beneficiary_shares`` via attribute
    mutation. Mirrors OllamaBackend's ``_envelope_to_extraction_result``
    at the call-site, simplifying diff-driven review when conventions
    evolve.

    ``backend_id`` follows spec 4.3a §5.3's ``<backend>:<model>``
    convention (e.g., ``"anthropic:claude-sonnet-4-6"``).
    """
    data = TrustData()
    grantor_fields, needs_co_grantor = _map_grantor_anthropic_envelope(envelope.grantors)
    if needs_co_grantor:
        data.co_grantor = GrantorInfo()
    beneficiary_fields, others, shares = _map_beneficiary_anthropic_envelope(
        envelope.beneficiaries
    )
    data.other_beneficiaries = others
    data.beneficiary_shares = shares

    trace = ExtractionTrace(
        fields=[*grantor_fields, *beneficiary_fields],
        backend_id=f"anthropic:{model}",
        extracted_at=datetime.now(UTC),
    )
    return ExtractionResult(data=data, trace=trace)


class AnthropicBackend:
    """ExtractionProtocol implementation against Anthropic's Claude API.

    Spec §6. Production-facing extraction backend; sibling to
    OllamaBackend (dev-only). Always-on extended thinking; adaptive
    retry deferred to Plan B per spec §2 *Out of scope*. The
    injectable ``client`` parameter is the construction seam Plan B
    relies on.

    The default ``mechanism="output_config"`` reflects spec §1 + §8.4's
    commitment that ``output_config`` composes with extended thinking
    (lead-verified 2026-05-18, gate G1 POSITIVE). If the §8.4 gate
    flips at the live API, the fallback is a single-line edit here to
    ``mechanism="tool_use"`` — no structural changes to the seam.
    """

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None = None,
        client: anthropic.Anthropic | None = None,
        thinking_budget_tokens: int = 5000,
        mechanism: Literal["tool_use", "output_config"] = "output_config",
        prompt_builder: Callable[[], str] | None = None,
    ) -> None:
        self.model = model
        self.thinking_budget_tokens = thinking_budget_tokens
        self.mechanism = mechanism
        self.prompt_builder = (
            prompt_builder if prompt_builder is not None else build_intake_prompt
        )
        self.client = (
            client if client is not None else anthropic.Anthropic(api_key=api_key)
        )

    def _invoke_envelope_call(
        self, *, system: str, user_msg: MessageParam, schema: dict
    ) -> dict:
        """Mechanism-agnostic structured-output seam.

        Spec §8.4: ``output_config`` is the working default; ``tool_use``
        is supported as a fallback. Both paths pass extended thinking
        unconditionally. Refusal under either mechanism (no tool_use
        block or non-JSON text) raises ExtractionError (mapped in
        cycles 10e / 10f below).

        Plan-authoring verification gates §8.2 + §8.4 are accommodated
        structurally: the gate outcomes only affect the constructor
        default mechanism and the instrumentation cycle 11 + 12 call-args
        assertions; the seam structure here is gate-outcome-agnostic.
        """
        # Hoist kwargs into typed locals so mypy can validate each literal
        # against the SDK's TypedDict overloads independently of the
        # call-site shape. The runtime kwarg dict is byte-identical to
        # the inline-literal form; the instrumentation cycle 11/12
        # call-args assertions remain valid.
        system_blocks: list[TextBlockParam] = [
            {
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"},
            }
        ]
        messages: list[MessageParam] = [user_msg]
        thinking: ThinkingConfigEnabledParam = {
            "type": "enabled",
            "budget_tokens": self.thinking_budget_tokens,
        }

        if self.mechanism == "tool_use":
            tools: list[ToolParam] = [
                {
                    "name": "submit_intake_extraction",
                    "description": (
                        "Submit the extracted intake form fields as a structured "
                        "envelope."
                    ),
                    "input_schema": schema,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
            tool_choice: ToolChoiceAutoParam = {"type": "auto"}
            response = self.client.messages.create(
                model=self.model,
                system=system_blocks,
                messages=messages,
                tools=tools,
                tool_choice=tool_choice,
                thinking=thinking,
                max_tokens=8192,
            )
            for block in response.content:
                # Use the `type` discriminator string (rather than
                # ``isinstance(block, ToolUseBlock)``) so the runtime
                # check is compatible with both real SDK objects and
                # MagicMock-shaped test fixtures (spec §9.3 convention).
                # ``cast`` here is a type-checker-only narrowing — the
                # runtime invariant is enforced by the discriminator
                # check above it.
                if getattr(block, "type", None) == "tool_use":
                    tool_block = cast(ToolUseBlock, block)
                    if not isinstance(tool_block.input, dict):
                        raise ExtractionError(
                            "tool_use input is not a mapping: "
                            f"{type(tool_block.input).__name__}"
                        )
                    return dict(tool_block.input)
            # Refusal under auto-choice: no tool_use block emitted.
            # Spec §8.5 diagnostic contract — include stop_reason so
            # paralegals can distinguish refusal-under-auto-choice from
            # other shapes when reading the log.
            raise ExtractionError(
                "model did not emit submit_intake_extraction tool_use: "
                f"stop_reason={response.stop_reason!r}"
            )

        # output_config branch.
        output_config: OutputConfigParam = {
            "format": {"type": "json_schema", "schema": schema},
        }
        response = self.client.messages.create(
            model=self.model,
            system=system_blocks,
            messages=messages,
            output_config=output_config,
            thinking=thinking,
            max_tokens=8192,
        )
        text_chunks: list[str] = []
        for block in response.content:
            # See cycle 7 docstring above _invoke_envelope_call's tool_use
            # branch: type-discriminator check is mock-compatible; cast
            # narrows for mypy.
            if getattr(block, "type", None) == "text":
                text_chunks.append(cast(TextBlock, block).text)
        joined = "".join(text_chunks)
        if not joined:
            # Refusal under output_config: no text emitted at all. Spec
            # §8.5 diagnostic contract — surface stop_reason (mirroring
            # the tool_use refusal branch above) so a content-policy
            # refusal is distinguishable from a JSON decode bug. Without
            # this branch the empty string falls through to json.loads
            # and is misreported as "JSON parse failure: ''".
            raise ExtractionError(
                "model emitted no text content under output_config: "
                f"stop_reason={response.stop_reason!r}"
            )
        try:
            parsed = json.loads(joined)
        except json.JSONDecodeError as e:
            # Spec §8.5 diagnostic contract — name the JSON parse mode
            # and include a sanitized prefix of the offending text so the
            # parse-failure surface is readable. The full text is NOT
            # included to avoid leaking large model outputs into logs.
            # stop_reason is surfaced so a refusal that still produced
            # prose is distinguishable from a structured-output decode bug.
            head = joined[:120]
            raise ExtractionError(
                f"output_config JSON parse failure (stop_reason="
                f"{response.stop_reason!r}): {head!r}"
            ) from e
        if not isinstance(parsed, dict):
            raise ExtractionError("text-block decoded to non-mapping payload")
        return parsed

    def extract(self, source: SourceRef) -> ExtractionResult:
        """Extract a (TrustData, ExtractionTrace) pair from one source.

        Spec §5.4 + §8.1. Failure modes raise ``ExtractionError``;
        per-field illegibility is a success-path trace entry.

        This cycle implements the PDF path with no size/page-count
        prechecks; the prechecks land in the sibling plan
        ``instrumentation`` (cycle 8). The image-source branch lands
        in ``instrumentation`` cycle 9.
        """
        mime, b64 = self._load_pdf_or_image(source)
        system = self._build_system_prompt()
        user_msg = self._build_user_message(mime, b64)

        try:
            raw = self._invoke_envelope_call(
                system=system,
                user_msg=user_msg,
                schema=AnthropicGenerationEnvelope.model_json_schema(),
            )
        except anthropic.AuthenticationError as e:
            # Drop the cause-chain: the SDK's AuthenticationError message
            # may contain the api_key adversarially (spec §8.5 hygiene).
            # AuthenticationError is a subclass of APIError, so this
            # specific handler MUST precede the general one below.
            raise _wrap_anthropic_error(e) from None
        except anthropic.APIError as e:
            # Specific subclass mapping lands in cycles 10a–10d below;
            # this catch-site is the dispatch point.
            raise _wrap_anthropic_error(e) from e

        try:
            envelope = AnthropicGenerationEnvelope.model_validate(raw)
        except ValidationError as e:
            # Spec §6 extra="forbid" rationale + §8.5 diagnostic contract:
            # name the envelope schema and the schema-invalid mode so the
            # defense-in-depth validation layer is readable in logs.
            raise ExtractionError(
                f"Anthropic envelope schema-invalid: {e}"
            ) from e

        return _anthropic_envelope_to_extraction_result(envelope, model=self.model)

    def _load_pdf_or_image(self, source: SourceRef) -> tuple[str, str]:
        """Return (mime_type, base64_data). Spec §8.1.

        Cycle 8 (instrumentation) adds a generic per-MIME size guard
        after MIME detection and a PDF-only page-count guard before
        base64 encoding. Image-source branch lands in cycle 9.

        Per the ``ExtractionProtocol`` contract only ``ExtractionError``
        may escape this method: filesystem failures (``OSError`` /
        ``PermissionError`` from ``stat`` / ``open``) and corrupt-PDF
        failures (``pypdf`` errors from ``PdfReader``) are mapped to
        ``ExtractionError`` rather than allowed to propagate raw.
        """
        if not source.exists():
            raise ExtractionError(f"source path not found: {source}")
        mime, _ = mimetypes.guess_type(str(source))
        if mime not in _ANTHROPIC_SUPPORTED_MIMES:
            raise ExtractionError(
                f"unsupported source mime-type: {mime!r}; "
                f"expected one of {sorted(_ANTHROPIC_SUPPORTED_MIMES)}"
            )

        # Spec §8.5 prechecks — raise before any client.messages.create call.

        # Generic size guard — per-MIME byte limit dispatch. At cycle 8 time
        # only PDFs reach this point; cycle 9 widens the allow-list above
        # and the same dispatch auto-extends to image MIMEs via the
        # ``mime.startswith("image/")`` branch.
        #
        # The filesystem touches (``stat``, ``open``) are wrapped: a
        # source that passes ``exists()`` can still fail ``stat``/``open``
        # under a permission denial or a TOCTOU race; raw ``OSError``
        # would breach the ExtractionProtocol contract.
        try:
            size_bytes = source.stat().st_size
        except OSError as e:
            raise ExtractionError(
                f"could not stat source path {source}: {type(e).__name__}"
            ) from e
        if mime == "application/pdf":
            size_limit = _ANTHROPIC_PDF_SIZE_LIMIT_BYTES
            size_label = "PDF"
        elif mime.startswith("image/"):
            size_limit = _ANTHROPIC_IMAGE_SIZE_LIMIT_BYTES
            size_label = "image"
        else:
            # Allow-list gating happens upstream; reaching here is a
            # programmer error. Conservative fallback uses the smaller
            # image limit.
            size_limit = _ANTHROPIC_IMAGE_SIZE_LIMIT_BYTES
            size_label = "source"
        if size_bytes > size_limit:
            raise ExtractionError(
                f"{size_label} exceeds Anthropic file-size limit "
                f"({size_limit // (1024 * 1024)}MiB): "
                f"got {size_bytes // (1024 * 1024)}MiB"
            )

        # PDF-only page-count guard. A corrupt or encrypted PDF makes
        # ``PdfReader`` raise a raw ``pypdf`` error (``PdfReadError`` /
        # ``FileNotDecryptedError`` / ``EmptyFileError`` — all subclass
        # ``PyPdfError``); map it to ExtractionError.
        if mime == "application/pdf":
            try:
                page_count = len(PdfReader(source).pages)
            except PyPdfError as e:
                raise ExtractionError(
                    f"could not read PDF {source}: {type(e).__name__}"
                ) from e
            if page_count > _ANTHROPIC_PDF_PAGE_LIMIT:
                raise ExtractionError(
                    f"PDF exceeds Anthropic page limit "
                    f"({_ANTHROPIC_PDF_PAGE_LIMIT}): got {page_count}"
                )

        try:
            with source.open("rb") as fh:
                data_bytes = fh.read()
        except OSError as e:
            raise ExtractionError(
                f"could not read source path {source}: {type(e).__name__}"
            ) from e
        b64 = base64.standard_b64encode(data_bytes).decode("ascii")
        return mime, b64

    def _build_system_prompt(self) -> str:
        return self.prompt_builder()

    def _build_user_message(self, mime: str, b64: str) -> MessageParam:
        """Construct the user-message dict carrying one content block.

        Spec §8.1: PDF path emits a ``document`` block; image path emits
        an ``image`` block (cycle 9, instrumentation). ``cache_control``
        placement on both is the §8.2 breakpoint 2; the assertion lives
        in cycle 11.

        ``_load_pdf_or_image`` gates ``mime not in _ANTHROPIC_SUPPORTED_MIMES``
        as an ExtractionError before reaching this method; the ``cast``
        calls below encode that runtime invariant for the type checker.
        """
        content_block: DocumentBlockParam | ImageBlockParam
        if mime == "application/pdf":
            content_block = {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": cast(Literal["application/pdf"], mime),
                    "data": b64,
                },
                "cache_control": {"type": "ephemeral"},
            }
        elif mime.startswith("image/"):
            content_block = {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": cast(_ImageMediaType, mime),
                    "data": b64,
                },
                "cache_control": {"type": "ephemeral"},
            }
        else:
            # _load_pdf_or_image already gates on the allow-list; this
            # branch is defensive — reaching it is a programmer error.
            raise ExtractionError(
                f"unsupported mime-type at message build: {mime!r}"
            )
        return {
            "role": "user",
            "content": [content_block],
        }


def _wrap_anthropic_error(exc: anthropic.APIError) -> ExtractionError:
    """Translate an anthropic.APIError into an ExtractionError.

    Spec §8.5 *ExtractionError message hygiene*: preserve the cause's
    class name; MUST NOT serialize the api_key, request headers, or
    the full ``repr()`` of the cause.

    Subclass-specific phrasing aids paralegals reading the log; the
    original exception remains accessible via ``__cause__`` for
    debug-time inspection.
    """
    cls_name = type(exc).__name__
    if isinstance(exc, anthropic.APIConnectionError):
        return ExtractionError(f"Anthropic network/connection error ({cls_name})")
    if isinstance(exc, anthropic.RateLimitError):
        return ExtractionError(
            f"Anthropic rate limit hit ({cls_name}); no auto-retry attempted"
        )
    if isinstance(exc, anthropic.AuthenticationError):
        # Do NOT serialize the cause's message — its body may contain
        # the api_key per the adversarial test (spec §8.5). This is the
        # ONLY error class whose message is dropped; the api_key-hygiene
        # rationale is specific to authentication failures.
        return ExtractionError(
            f"Anthropic authentication failed ({cls_name}); "
            "check ANTHROPIC_API_KEY"
        )
    # Generic fallthrough (BadRequestError, InternalServerError, etc.).
    # Unlike AuthenticationError, these SDK messages are diagnostically
    # useful and carry no api_key — surface the message so the failure
    # mode is readable in paralegal-visible logs. The message is taken
    # from ``exc`` directly; the api_key is never part of a non-auth
    # APIError body, and ``__cause__`` retains the full exception for
    # debug-time inspection.
    message = str(exc).strip()
    if message:
        return ExtractionError(f"Anthropic API error ({cls_name}): {message}")
    return ExtractionError(f"Anthropic API error ({cls_name})")
