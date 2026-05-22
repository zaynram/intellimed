"""Unit tests for AnthropicBackend and the prompt-module split."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import anthropic
import pytest

from trust_generator.v3.extraction import ExtractionError, ExtractionResult
from trust_generator.v3.extraction.anthropic_backend import AnthropicBackend

# Shared test-model identifier — mirrors core cycle 4's ctor default.
# If core changes the default model, update this one constant; the
# instrumentation tests instantiate AnthropicBackend(model=_TEST_MODEL, ...) throughout.
_TEST_MODEL: str = "claude-sonnet-4-6"


def _make_minimal_anthropic_response() -> object:
    """Minimal mock SDK response sufficient for instrumentation call-args tests.

    Returns a Message-shaped MagicMock with one text block containing an empty
    envelope. For output_config mode the test's extract() call succeeds and
    returns a valid ExtractionResult. For tool_use mode the absence of a
    tool_use block triggers ExtractionError in _invoke_envelope_call's refusal
    path; instrumentation tests catch that ExtractionError before asserting
    on messages.create.call_args, since the call has already happened.
    """
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = '{"grantors": [], "beneficiaries": []}'
    response = MagicMock()
    response.stop_reason = "end_turn"
    response.content = [text_block]
    return response


def test_prompt_ollama_module_exposes_build_intake_prompt() -> None:
    """`prompt_ollama.build_intake_prompt()` returns a non-empty str."""
    from trust_generator.v3.extraction import prompt_ollama

    out = prompt_ollama.build_intake_prompt()
    assert isinstance(out, str)
    assert out.strip()  # non-empty after stripping


def test_prompt_ollama_build_intake_prompt_byte_equal_to_prompt_module_reexport() -> None:
    """Relocation is byte-exact — `prompt.build_intake_prompt()` and
    `prompt_ollama.build_intake_prompt()` return the same string.

    This pins the Ollama-side relocation as a pure rename: the existing
    OllamaBackend import path (`from ...prompt import build_intake_prompt`,
    ollama_backend.py:13) MUST continue resolving to the same string,
    since ollama_backend.py is outside this plan's blast-radius and
    cannot be edited.
    """
    from trust_generator.v3.extraction import prompt, prompt_ollama

    assert prompt.build_intake_prompt() == prompt_ollama.build_intake_prompt()


def test_prompt_module_reexports_build_intake_prompt_for_ollama_backend_compat() -> None:
    """The `prompt.build_intake_prompt` name is still importable.

    OllamaBackend imports `build_intake_prompt` from `prompt`; the
    relocation must not break that path.
    """
    from trust_generator.v3.extraction.prompt import build_intake_prompt

    assert callable(build_intake_prompt)
    assert isinstance(build_intake_prompt(), str)


def test_prompt_anthropic_module_exposes_build_intake_prompt() -> None:
    """`prompt_anthropic.build_intake_prompt()` returns a non-empty str."""
    from trust_generator.v3.extraction import prompt_anthropic

    out = prompt_anthropic.build_intake_prompt()
    assert isinstance(out, str)
    assert out.strip()


def test_prompt_anthropic_prompt_contains_legal_intake_framing() -> None:
    """The Anthropic prompt names the legal-intake domain context.

    Pins that the backend-fork retains the §8.2 domain orientation
    (legal trust intake; grantors / beneficiaries / etc.).
    """
    from trust_generator.v3.extraction.prompt_anthropic import build_intake_prompt

    out = build_intake_prompt()
    assert "legal" in out.lower()
    assert "trust" in out.lower()
    assert "grantor" in out.lower()


def test_prompt_anthropic_prompt_omits_reasoning_aloud_channel() -> None:
    """The Anthropic prompt does NOT instruct the model to reason aloud
    in a schema reasoning field — extended thinking handles that channel
    out-of-band, and the AnthropicGenerationEnvelope has no ``reasoning``
    field (spec §6).
    """
    from trust_generator.v3.extraction.prompt_anthropic import build_intake_prompt

    out = build_intake_prompt().lower()
    # The Ollama prompt uses the phrase "reasoning aloud first" / "reasoning"
    # field; Anthropic-side must not direct the model to populate such a field.
    assert "reasoning" not in out
    assert '"reasoning"' not in out


def test_prompt_anthropic_prompt_acknowledges_pdf_intake() -> None:
    """The Anthropic prompt mentions PDF intake explicitly.

    Anthropic's `document` content block accepts PDFs natively (spec
    §2 In-scope, §8.1); the prompt should cue the model that the
    attachment may be a multi-page PDF rather than a single image.
    """
    from trust_generator.v3.extraction.prompt_anthropic import build_intake_prompt

    out = build_intake_prompt().lower()
    assert "pdf" in out


def test_anthropic_field_flag_default_is_not_illegible() -> None:
    from trust_generator.v3.extraction.anthropic_backend import AnthropicFieldFlag

    assert AnthropicFieldFlag().illegible is False


def test_anthropic_field_flag_rejects_extra_keys() -> None:
    from pydantic import ValidationError

    from trust_generator.v3.extraction.anthropic_backend import AnthropicFieldFlag

    with pytest.raises(ValidationError):
        AnthropicFieldFlag.model_validate({"illegible": True, "note": "extra"})


def test_anthropic_grantor_envelope_default_field_flags_are_inert() -> None:
    from trust_generator.v3.extraction.anthropic_backend import AnthropicGrantorEnvelope

    g = AnthropicGrantorEnvelope()
    assert g.full_legal_name is None
    assert g.full_legal_name_flag.illegible is False
    assert g.date_of_birth is None
    assert g.date_of_birth_flag.illegible is False


def test_anthropic_beneficiary_envelope_default_field_flags_are_inert() -> None:
    from trust_generator.v3.extraction.anthropic_backend import (
        AnthropicBeneficiaryEnvelope,
    )

    b = AnthropicBeneficiaryEnvelope()
    assert b.full_legal_name is None
    assert b.relationship is None
    assert b.share_percent is None
    assert b.full_legal_name_flag.illegible is False
    assert b.relationship_flag.illegible is False
    assert b.share_percent_flag.illegible is False


def test_anthropic_generation_envelope_round_trips() -> None:
    """model_validate(model_dump()) is an identity for a populated envelope."""
    from trust_generator.v3.extraction.anthropic_backend import (
        AnthropicBeneficiaryEnvelope,
        AnthropicFieldFlag,
        AnthropicGenerationEnvelope,
        AnthropicGrantorEnvelope,
    )

    env = AnthropicGenerationEnvelope(
        grantors=[
            AnthropicGrantorEnvelope(
                full_legal_name="James William Thompson, Jr.",
                date_of_birth="1962-03-14",
            ),
            AnthropicGrantorEnvelope(
                full_legal_name_flag=AnthropicFieldFlag(illegible=True),
            ),
        ],
        beneficiaries=[
            AnthropicBeneficiaryEnvelope(
                full_legal_name="Jane Doe",
                relationship="daughter",
                share_percent="50",
            ),
        ],
    )

    dumped = env.model_dump()
    rehydrated = AnthropicGenerationEnvelope.model_validate(dumped)
    assert rehydrated == env


def test_anthropic_generation_envelope_rejects_extra_keys() -> None:
    from pydantic import ValidationError

    from trust_generator.v3.extraction.anthropic_backend import (
        AnthropicGenerationEnvelope,
    )

    with pytest.raises(ValidationError):
        AnthropicGenerationEnvelope.model_validate(
            {"grantors": [], "beneficiaries": [], "reasoning": "should-be-rejected"}
        )


def test_anthropic_generation_envelope_has_no_reasoning_field() -> None:
    """Spec §6: no reasoning field (extended thinking carries that
    channel out-of-band) and no overall_confidence (deferred to 4.3c).
    """
    from trust_generator.v3.extraction.anthropic_backend import (
        AnthropicGenerationEnvelope,
    )

    fields = set(AnthropicGenerationEnvelope.model_fields)
    assert "reasoning" not in fields
    assert "overall_confidence" not in fields
    assert fields == {"grantors", "beneficiaries"}


def test_map_grantor_anthropic_envelope_happy_path() -> None:
    from trust_generator.v3.extraction.anthropic_backend import (
        AnthropicGrantorEnvelope,
        _map_grantor_anthropic_envelope,
    )

    fields, needs_co_grantor = _map_grantor_anthropic_envelope(
        [
            AnthropicGrantorEnvelope(
                full_legal_name="James William Thompson, Jr.",
                date_of_birth="1962-03-14",
            ),
        ]
    )

    assert needs_co_grantor is False
    field_paths = [f.field_path for f in fields]
    assert field_paths == ["grantor.full_legal_name", "grantor.date_of_birth"]
    name_field = fields[0]
    assert name_field.raw_value == "James William Thompson, Jr."
    assert name_field.normalized_value == "James William Thompson, Jr."
    assert name_field.illegible is False


def test_map_grantor_anthropic_envelope_two_grantors_signals_co_grantor() -> None:
    from trust_generator.v3.extraction.anthropic_backend import (
        AnthropicGrantorEnvelope,
        _map_grantor_anthropic_envelope,
    )

    fields, needs_co_grantor = _map_grantor_anthropic_envelope(
        [
            AnthropicGrantorEnvelope(full_legal_name="A"),
            AnthropicGrantorEnvelope(full_legal_name="B"),
        ]
    )

    assert needs_co_grantor is True
    assert [f.field_path for f in fields] == [
        "grantor.full_legal_name",
        "co_grantor.full_legal_name",
    ]


def test_map_grantor_anthropic_envelope_ignores_third_grantor() -> None:
    """Positional mapping caps at index 1; entries beyond are ignored."""
    from trust_generator.v3.extraction.anthropic_backend import (
        AnthropicGrantorEnvelope,
        _map_grantor_anthropic_envelope,
    )

    fields, needs_co_grantor = _map_grantor_anthropic_envelope(
        [
            AnthropicGrantorEnvelope(full_legal_name="A"),
            AnthropicGrantorEnvelope(full_legal_name="B"),
            AnthropicGrantorEnvelope(full_legal_name="C"),
        ]
    )

    paths = [f.field_path for f in fields]
    assert "C" not in [f.raw_value for f in fields]
    assert paths == ["grantor.full_legal_name", "co_grantor.full_legal_name"]
    assert needs_co_grantor is True


def test_map_grantor_anthropic_envelope_illegibility_degrades_value() -> None:
    from trust_generator.v3.extraction.anthropic_backend import (
        AnthropicFieldFlag,
        AnthropicGrantorEnvelope,
        _map_grantor_anthropic_envelope,
    )

    fields, _ = _map_grantor_anthropic_envelope(
        [
            AnthropicGrantorEnvelope(
                full_legal_name_flag=AnthropicFieldFlag(illegible=True),
            ),
        ]
    )

    assert len(fields) == 1
    assert fields[0].field_path == "grantor.full_legal_name"
    assert fields[0].illegible is True
    assert fields[0].normalized_value is None
    assert fields[0].raw_value == ""


def test_map_grantor_anthropic_envelope_omits_absent_field() -> None:
    """Per spec §8.3 omit-if-absent: data=None AND flag quiet → no entry."""
    from trust_generator.v3.extraction.anthropic_backend import (
        AnthropicGrantorEnvelope,
        _map_grantor_anthropic_envelope,
    )

    fields, _ = _map_grantor_anthropic_envelope([AnthropicGrantorEnvelope()])

    assert fields == []


def test_map_grantor_anthropic_envelope_date_uses_incomplete_sentinel() -> None:
    """Legible-but-not-yet-normalized date → normalized_value is INCOMPLETE."""
    from trust_generator.v3.extraction.anthropic_backend import (
        AnthropicGrantorEnvelope,
        _map_grantor_anthropic_envelope,
    )
    from trust_generator.v3.extraction.trace import INCOMPLETE

    fields, _ = _map_grantor_anthropic_envelope(
        [AnthropicGrantorEnvelope(date_of_birth="1962-03-14")]
    )
    dob = next(f for f in fields if f.field_path == "grantor.date_of_birth")
    assert dob.normalized_value is INCOMPLETE
    assert dob.illegible is False
    assert dob.raw_value == "1962-03-14"


def test_map_beneficiary_anthropic_envelope_happy_path() -> None:
    from trust_generator.v3.extraction.anthropic_backend import (
        AnthropicBeneficiaryEnvelope,
        _map_beneficiary_anthropic_envelope,
    )
    from trust_generator.v3.extraction.trace import INCOMPLETE
    from trust_generator.v3.schema import BeneficiaryShare, OtherBeneficiary

    fields, others, shares = _map_beneficiary_anthropic_envelope(
        [
            AnthropicBeneficiaryEnvelope(
                full_legal_name="Jane Doe",
                relationship="daughter",
                share_percent="50",
            ),
        ]
    )

    assert len(others) == 1 and isinstance(others[0], OtherBeneficiary)
    assert len(shares) == 1 and isinstance(shares[0], BeneficiaryShare)
    assert shares[0].recipient_ref == "other_beneficiaries[0]"

    paths = [f.field_path for f in fields]
    assert paths == [
        "other_beneficiaries[0].full_legal_name",
        "other_beneficiaries[0].relationship_other",
        "beneficiary_shares[0].share_percent",
    ]
    share_field = next(f for f in fields if f.field_path.endswith("share_percent"))
    assert share_field.normalized_value is INCOMPLETE
    assert share_field.raw_value == "50"


def test_map_beneficiary_anthropic_envelope_illegibility_degrades_value() -> None:
    from trust_generator.v3.extraction.anthropic_backend import (
        AnthropicBeneficiaryEnvelope,
        AnthropicFieldFlag,
        _map_beneficiary_anthropic_envelope,
    )

    fields, others, shares = _map_beneficiary_anthropic_envelope(
        [
            AnthropicBeneficiaryEnvelope(
                share_percent_flag=AnthropicFieldFlag(illegible=True),
            ),
        ]
    )

    assert len(others) == 1
    assert len(shares) == 1
    share_field = next(f for f in fields if f.field_path.endswith("share_percent"))
    assert share_field.illegible is True
    assert share_field.normalized_value is None
    assert share_field.raw_value == ""


def test_anthropic_envelope_to_extraction_result_assembles_trace() -> None:
    """Composer mirrors ``_envelope_to_extraction_result`` in ollama_backend
    (spec §6 composer construction pattern)."""
    from trust_generator.v3.extraction.anthropic_backend import (
        AnthropicBeneficiaryEnvelope,
        AnthropicGenerationEnvelope,
        AnthropicGrantorEnvelope,
        _anthropic_envelope_to_extraction_result,
    )

    env = AnthropicGenerationEnvelope(
        grantors=[
            AnthropicGrantorEnvelope(full_legal_name="Alice"),
            AnthropicGrantorEnvelope(full_legal_name="Bob"),
        ],
        beneficiaries=[
            AnthropicBeneficiaryEnvelope(full_legal_name="Charlie"),
        ],
    )

    result = _anthropic_envelope_to_extraction_result(env, model="claude-sonnet-4-6")

    assert result.trace.backend_id == "anthropic:claude-sonnet-4-6"
    assert result.data.co_grantor is not None  # second grantor → co_grantor
    assert len(result.data.other_beneficiaries) == 1
    assert len(result.data.beneficiary_shares) == 1
    field_paths = [f.field_path for f in result.trace.fields]
    assert "grantor.full_legal_name" in field_paths
    assert "co_grantor.full_legal_name" in field_paths
    assert "other_beneficiaries[0].full_legal_name" in field_paths


def test_anthropic_backend_importable_from_module() -> None:
    from trust_generator.v3.extraction.anthropic_backend import AnthropicBackend

    assert AnthropicBackend.__name__ == "AnthropicBackend"


def test_anthropic_backend_requires_model_keyword_only() -> None:
    """``model`` is required and keyword-only (spec §6 ``__init__`` signature)."""
    from unittest.mock import MagicMock

    from trust_generator.v3.extraction.anthropic_backend import AnthropicBackend

    with pytest.raises(TypeError):
        AnthropicBackend()  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        AnthropicBackend("claude-sonnet-4-6", client=MagicMock())  # type: ignore[misc]

    backend = AnthropicBackend(model="claude-sonnet-4-6", client=MagicMock())
    assert backend.model == "claude-sonnet-4-6"


def test_anthropic_backend_constructor_defaults_match_spec() -> None:
    """Spec §6 defaults: thinking_budget_tokens=5000, mechanism='output_config',
    prompt_builder defaults to prompt_anthropic.build_intake_prompt."""
    from unittest.mock import MagicMock

    from trust_generator.v3.extraction.anthropic_backend import AnthropicBackend
    from trust_generator.v3.extraction.prompt_anthropic import build_intake_prompt

    backend = AnthropicBackend(model="claude-sonnet-4-6", client=MagicMock())
    assert backend.thinking_budget_tokens == 5000
    assert backend.mechanism == "output_config"
    assert backend.prompt_builder is build_intake_prompt


def test_anthropic_backend_accepts_injected_client() -> None:
    from unittest.mock import MagicMock

    from trust_generator.v3.extraction.anthropic_backend import AnthropicBackend

    injected = MagicMock()
    backend = AnthropicBackend(model="claude-sonnet-4-6", client=injected)
    assert backend.client is injected


def test_anthropic_backend_accepts_mechanism_choice() -> None:
    """Both literal values accepted; invalid mechanism reaches the type
    checker but at runtime the constructor simply stores the value."""
    from unittest.mock import MagicMock

    from trust_generator.v3.extraction.anthropic_backend import AnthropicBackend

    a = AnthropicBackend(
        model="claude-sonnet-4-6", client=MagicMock(), mechanism="tool_use"
    )
    b = AnthropicBackend(
        model="claude-sonnet-4-6", client=MagicMock(), mechanism="output_config"
    )
    assert a.mechanism == "tool_use"
    assert b.mechanism == "output_config"


def test_anthropic_backend_accepts_custom_prompt_builder() -> None:
    from unittest.mock import MagicMock

    from trust_generator.v3.extraction.anthropic_backend import AnthropicBackend

    def custom() -> str:
        return "custom-prompt"

    backend = AnthropicBackend(
        model="claude-sonnet-4-6", client=MagicMock(), prompt_builder=custom
    )
    assert backend.prompt_builder is custom


def test_anthropic_backend_accepts_thinking_budget_override() -> None:
    from unittest.mock import MagicMock

    from trust_generator.v3.extraction.anthropic_backend import AnthropicBackend

    backend = AnthropicBackend(
        model="claude-sonnet-4-6",
        client=MagicMock(),
        thinking_budget_tokens=8000,
    )
    assert backend.thinking_budget_tokens == 8000


def test_anthropic_sdk_is_pinned_in_pyproject() -> None:
    """The `anthropic` package appears in pyproject.toml's `dependencies`.

    Defense against accidental removal during a future merge / rebase.
    The exact version pin is whatever Cycle 4 committed (see commit
    message); this test only asserts the package is declared.

    Path resolution: ``pixi run test`` sets cwd to ``tests/``; ``__file__``
    is the only stable anchor. ``parents[3]`` is the repo root
    (parents[0]=extraction, [1]=v3, [2]=tests, [3]=repo root).
    """
    import tomllib
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[3]
    pyproject = tomllib.loads(
        (repo_root / "pyproject.toml").read_text(encoding="utf-8")
    )
    deps = pyproject["project"]["dependencies"]
    assert any(d.startswith("anthropic") for d in deps), (
        f"anthropic SDK not declared in [project].dependencies: {deps}"
    )


def _make_mock_anthropic_message_with_tool_use(envelope_dict: dict) -> object:
    """Construct a mock anthropic.types.Message with a tool_use content block.

    Spec §9.3 mocking convention. Returns a MagicMock shaped to match
    the SDK's Message type (`stop_reason`, `content` list with blocks
    each carrying `type` discriminator).
    """
    from unittest.mock import MagicMock

    tool_use_block = MagicMock()
    tool_use_block.type = "tool_use"
    tool_use_block.name = "submit_intake_extraction"
    tool_use_block.input = envelope_dict

    response = MagicMock()
    response.stop_reason = "tool_use"
    response.content = [tool_use_block]
    return response


def test_invoke_envelope_call_tool_use_returns_input_dict() -> None:
    """tool_use mode: seam returns the tool_use block's `input` as dict."""
    from unittest.mock import MagicMock

    from trust_generator.v3.extraction.anthropic_backend import (
        AnthropicBackend,
        AnthropicGenerationEnvelope,
    )

    envelope_dict = {"grantors": [], "beneficiaries": []}
    client = MagicMock()
    client.messages.create.return_value = (
        _make_mock_anthropic_message_with_tool_use(envelope_dict)
    )
    backend = AnthropicBackend(
        model="claude-sonnet-4-6", client=client, mechanism="tool_use"
    )

    schema = AnthropicGenerationEnvelope.model_json_schema()
    out = backend._invoke_envelope_call(
        system="sys-prompt",
        user_msg={"role": "user", "content": [{"type": "text", "text": "x"}]},
        schema=schema,
    )

    assert out == envelope_dict


def test_invoke_envelope_call_tool_use_passes_tool_choice_auto() -> None:
    """Spec §1, §8.4: tool_choice MUST be `{"type": "auto"}` — forced
    `{"type": "tool", ...}` or `{"type": "any"}` is incompatible with
    extended thinking and would raise at the API.
    """
    from unittest.mock import MagicMock

    from trust_generator.v3.extraction.anthropic_backend import (
        AnthropicBackend,
        AnthropicGenerationEnvelope,
    )

    client = MagicMock()
    client.messages.create.return_value = (
        _make_mock_anthropic_message_with_tool_use(
            {"grantors": [], "beneficiaries": []}
        )
    )
    backend = AnthropicBackend(
        model="claude-sonnet-4-6", client=client, mechanism="tool_use"
    )

    backend._invoke_envelope_call(
        system="sys",
        user_msg={"role": "user", "content": []},
        schema=AnthropicGenerationEnvelope.model_json_schema(),
    )

    _, kwargs = client.messages.create.call_args
    assert kwargs["tool_choice"] == {"type": "auto"}


def _make_mock_anthropic_message_with_text(json_text: str) -> object:
    """Construct a mock anthropic.types.Message with a single text block."""
    from unittest.mock import MagicMock

    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = json_text

    response = MagicMock()
    response.stop_reason = "end_turn"
    response.content = [text_block]
    return response


def test_invoke_envelope_call_output_config_parses_text_block_json() -> None:
    """output_config mode: seam json.loads the final text block."""
    import json
    from unittest.mock import MagicMock

    from trust_generator.v3.extraction.anthropic_backend import (
        AnthropicBackend,
        AnthropicGenerationEnvelope,
    )

    envelope_dict = {"grantors": [], "beneficiaries": []}
    client = MagicMock()
    client.messages.create.return_value = (
        _make_mock_anthropic_message_with_text(json.dumps(envelope_dict))
    )
    backend = AnthropicBackend(
        model="claude-sonnet-4-6", client=client, mechanism="output_config"
    )

    out = backend._invoke_envelope_call(
        system="sys",
        user_msg={"role": "user", "content": []},
        schema=AnthropicGenerationEnvelope.model_json_schema(),
    )

    assert out == envelope_dict


def test_invoke_envelope_call_output_config_passes_output_config_kwarg() -> None:
    """output_config mode constructs ``output_config={"format": {...}}``."""
    import json
    from unittest.mock import MagicMock

    from trust_generator.v3.extraction.anthropic_backend import (
        AnthropicBackend,
        AnthropicGenerationEnvelope,
    )

    client = MagicMock()
    client.messages.create.return_value = (
        _make_mock_anthropic_message_with_text(
            json.dumps({"grantors": [], "beneficiaries": []})
        )
    )
    backend = AnthropicBackend(
        model="claude-sonnet-4-6", client=client, mechanism="output_config"
    )
    schema = AnthropicGenerationEnvelope.model_json_schema()

    backend._invoke_envelope_call(
        system="sys",
        user_msg={"role": "user", "content": []},
        schema=schema,
    )

    _, kwargs = client.messages.create.call_args
    output_config = kwargs["output_config"]
    assert output_config["format"]["type"] == "json_schema"
    assert output_config["format"]["schema"] == schema


def test_invoke_envelope_call_output_config_does_not_pass_tools_or_tool_choice() -> None:
    """output_config mode: no tools array, no tool_choice."""
    import json
    from unittest.mock import MagicMock

    from trust_generator.v3.extraction.anthropic_backend import (
        AnthropicBackend,
        AnthropicGenerationEnvelope,
    )

    client = MagicMock()
    client.messages.create.return_value = (
        _make_mock_anthropic_message_with_text(
            json.dumps({"grantors": [], "beneficiaries": []})
        )
    )
    backend = AnthropicBackend(
        model="claude-sonnet-4-6", client=client, mechanism="output_config"
    )

    backend._invoke_envelope_call(
        system="sys",
        user_msg={"role": "user", "content": []},
        schema=AnthropicGenerationEnvelope.model_json_schema(),
    )

    _, kwargs = client.messages.create.call_args
    assert "tools" not in kwargs
    assert "tool_choice" not in kwargs


def _make_pdf_fixture(tmp_path):
    """Write a minimal *parseable* 1-page PDF to a tmp path.

    Cycle 8 (instrumentation) added a PDF page-count precheck which
    invokes ``pypdf.PdfReader(source)`` on every PDF source. The
    earlier stub byte sequence (``b"%PDF-1.4\\n%..."``) is not
    parseable; pypdf raises ``PdfStreamError`` before reaching the
    mocked client. Switching to a writer-built 1-page PDF keeps the
    fixture parseable for the new precheck while preserving the
    "mocked client, byte-content irrelevant" intent of the original.
    """
    from pypdf import PdfWriter

    p = tmp_path / "intake.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with p.open("wb") as fh:
        writer.write(fh)
    return p


@pytest.mark.parametrize("mechanism", ["tool_use", "output_config"])
def test_anthropic_backend_extract_happy_path(tmp_path, mechanism: str) -> None:
    """End-to-end extract() returns an ExtractionResult through both mechanisms.

    Asserts: TrustData.grantor.full_legal_name reflects envelope[0]
    positional mapping; backend_id is f"anthropic:{model}"; trace.fields
    is populated; ExtractionTrace consumable identically across
    mechanisms.
    """
    import json
    from unittest.mock import MagicMock

    from trust_generator.v3.extraction.anthropic_backend import AnthropicBackend

    envelope_dict = {
        "grantors": [
            {"full_legal_name": "Alice Tester"},
            {"full_legal_name": "Bob Tester"},
        ],
        "beneficiaries": [
            {"full_legal_name": "Charlie Child", "share_percent": "100"},
        ],
    }

    client = MagicMock()
    if mechanism == "tool_use":
        client.messages.create.return_value = (
            _make_mock_anthropic_message_with_tool_use(envelope_dict)
        )
    else:
        client.messages.create.return_value = (
            _make_mock_anthropic_message_with_text(json.dumps(envelope_dict))
        )

    backend = AnthropicBackend(
        model="claude-sonnet-4-6", client=client, mechanism=mechanism
    )
    pdf = _make_pdf_fixture(tmp_path)

    result = backend.extract(pdf)

    assert isinstance(result, ExtractionResult)
    assert result.trace.backend_id == "anthropic:claude-sonnet-4-6"
    assert result.data.co_grantor is not None  # two grantors in envelope
    assert len(result.data.other_beneficiaries) == 1
    paths = {f.field_path for f in result.trace.fields}
    assert "grantor.full_legal_name" in paths
    assert "co_grantor.full_legal_name" in paths
    assert "other_beneficiaries[0].full_legal_name" in paths
    assert "beneficiary_shares[0].share_percent" in paths

    # Mechanism-specific kwarg presence on messages.create. MagicMock
    # accepts any kwarg silently — without this assertion a typo in
    # the seam (e.g., "output_configs", "tool_uses") would surface
    # only at live-API time. Cycles 5/6 cover the seam units; this is
    # the integration-site safety net.
    _, kwargs = client.messages.create.call_args
    if mechanism == "output_config":
        assert "output_config" in kwargs
        assert "tools" not in kwargs and "tool_choice" not in kwargs
    else:
        assert "tools" in kwargs
        assert kwargs["tool_choice"] == {"type": "auto"}


def test_anthropic_backend_extract_invokes_messages_create_once(tmp_path) -> None:
    """Single call per extract() (no auto-retry in v1 per spec §2)."""
    import json
    from unittest.mock import MagicMock

    from trust_generator.v3.extraction.anthropic_backend import AnthropicBackend

    client = MagicMock()
    client.messages.create.return_value = (
        _make_mock_anthropic_message_with_text(
            json.dumps({"grantors": [], "beneficiaries": []})
        )
    )
    backend = AnthropicBackend(
        model="claude-sonnet-4-6", client=client, mechanism="output_config"
    )
    pdf = _make_pdf_fixture(tmp_path)

    backend.extract(pdf)

    assert client.messages.create.call_count == 1


def test_anthropic_backend_exported_from_extraction_package() -> None:
    """AnthropicBackend is importable from the extraction package
    and listed in __all__, mirroring OllamaBackend."""
    from trust_generator.v3 import extraction

    assert hasattr(extraction, "AnthropicBackend")
    assert "AnthropicBackend" in extraction.__all__


def _make_failing_client(error: Exception) -> object:
    """Construct a MagicMock-shaped anthropic.Anthropic whose
    messages.create raises ``error``.

    Spec §9.3 mocking convention: ``MagicMock(spec=anthropic.Anthropic)``
    catches typos in the SDK surface (a future rename of ``create``
    would fail the spec check). The same convention should retrofit
    the happy-path helpers (``_make_mock_anthropic_message_with_*``)
    introduced in cycles 5/6 — assess as a refactor at end-of-cycle-10d
    when the test-helper surface has stabilized.
    """
    client = MagicMock(spec=anthropic.Anthropic)
    client.messages.create.side_effect = error
    return client


def test_api_connection_error_is_wrapped(tmp_path) -> None:
    """anthropic.APIConnectionError → ExtractionError, chained via __cause__."""
    from trust_generator.v3.extraction import ExtractionError
    from trust_generator.v3.extraction.anthropic_backend import AnthropicBackend

    err = anthropic.APIConnectionError(request=MagicMock(method="POST", url="x"))
    backend = AnthropicBackend(
        model="claude-sonnet-4-6", client=_make_failing_client(err)
    )
    pdf = _make_pdf_fixture(tmp_path)

    with pytest.raises(ExtractionError) as exc_info:
        backend.extract(pdf)

    assert exc_info.value.__cause__ is err
    assert "APIConnectionError" in str(exc_info.value) or "connection" in str(
        exc_info.value
    ).lower()


def test_api_connection_error_message_does_not_leak_api_key(tmp_path) -> None:
    """Spec §8.5 *ExtractionError message hygiene*: api_key substring
    MUST NOT appear in the wrapped error message."""
    from trust_generator.v3.extraction import ExtractionError
    from trust_generator.v3.extraction.anthropic_backend import AnthropicBackend

    secret = "sk-ant-fake-key-do-not-leak-XYZ"
    err = anthropic.APIConnectionError(request=MagicMock())
    backend = AnthropicBackend(
        model="claude-sonnet-4-6",
        api_key=secret,
        client=_make_failing_client(err),
    )
    pdf = _make_pdf_fixture(tmp_path)

    with pytest.raises(ExtractionError) as exc_info:
        backend.extract(pdf)

    assert secret not in str(exc_info.value)


def test_rate_limit_error_is_wrapped(tmp_path) -> None:
    """anthropic.RateLimitError → ExtractionError, chained, no retry attempted."""
    from trust_generator.v3.extraction import ExtractionError
    from trust_generator.v3.extraction.anthropic_backend import AnthropicBackend

    err = anthropic.RateLimitError(
        message="rate limit", response=MagicMock(status_code=429), body=None
    )
    client = _make_failing_client(err)
    backend = AnthropicBackend(model="claude-sonnet-4-6", client=client)
    pdf = _make_pdf_fixture(tmp_path)

    with pytest.raises(ExtractionError) as exc_info:
        backend.extract(pdf)

    assert exc_info.value.__cause__ is err
    assert client.messages.create.call_count == 1  # no auto-retry


def test_rate_limit_error_message_mentions_rate_limit(tmp_path) -> None:
    from trust_generator.v3.extraction import ExtractionError
    from trust_generator.v3.extraction.anthropic_backend import AnthropicBackend

    err = anthropic.RateLimitError(
        message="rate limit", response=MagicMock(status_code=429), body=None
    )
    backend = AnthropicBackend(
        model="claude-sonnet-4-6", client=_make_failing_client(err)
    )
    pdf = _make_pdf_fixture(tmp_path)

    # Strengthened: `(?i)rate limit` (space-bearing) distinguishes the
    # specialized "rate limit hit" message from the generic fallthrough
    # `"Anthropic API error (RateLimitError)"`, where "rate" appears
    # only as part of the class-name substring without a following space.
    with pytest.raises(ExtractionError, match="(?i)rate limit"):
        backend.extract(pdf)


def test_authentication_error_is_wrapped(tmp_path) -> None:
    """AuthenticationError → ExtractionError.

    Unlike the other 10a/10b/10d mappings, AuthenticationError uses
    ``raise ... from None`` (NOT ``from err``) to drop the cause-chain
    — the SDK's AuthenticationError carries the bad api_key in its
    own message, which would bleed through every standard log surface
    (``logging.exception``, ``traceback.format_exception``,
    pytest failure rendering) if ``__cause__`` retained ``err``. The
    sibling test ``test_authentication_error_message_does_not_leak_api_key``
    pins this against a traceback-rendered surface.
    """
    from trust_generator.v3.extraction import ExtractionError
    from trust_generator.v3.extraction.anthropic_backend import AnthropicBackend

    err = anthropic.AuthenticationError(
        message="invalid api key",
        response=MagicMock(status_code=401),
        body=None,
    )
    backend = AnthropicBackend(
        model="claude-sonnet-4-6", client=_make_failing_client(err)
    )
    pdf = _make_pdf_fixture(tmp_path)

    with pytest.raises(ExtractionError) as exc_info:
        backend.extract(pdf)

    # AuthenticationError uses ``from None`` — cause-chain is deliberately
    # dropped (see docstring). The cause class name + status are preserved
    # in the wrap message text.
    assert exc_info.value.__cause__ is None
    assert "authentication" in str(exc_info.value).lower()


def test_authentication_error_message_does_not_leak_api_key(tmp_path) -> None:
    """The api_key MUST NOT appear anywhere log-paths walk —
    including ``__cause__``-chain rendering via
    ``traceback.format_exception``. Spec §8.5: the ExtractionError
    message is user-visible (firm-admin logs); the Anthropic SDK's
    AuthenticationError carries the bad key in its OWN message
    (adversarial cause). ``raise ... from None`` is required on the
    AuthenticationError branch to drop the chain — ``str(outer_exc)``
    alone does not check what ``logging.exception()`` /
    ``traceback.format_exception(...)`` render.
    """
    import traceback

    from trust_generator.v3.extraction import ExtractionError
    from trust_generator.v3.extraction.anthropic_backend import AnthropicBackend

    secret = "sk-ant-fake-key-XXXX"
    err = anthropic.AuthenticationError(
        message=f"invalid api key: {secret}",  # adversarial cause-message
        response=MagicMock(status_code=401),
        body=None,
    )
    backend = AnthropicBackend(
        model="claude-sonnet-4-6",
        api_key=secret,
        client=_make_failing_client(err),
    )
    pdf = _make_pdf_fixture(tmp_path)

    with pytest.raises(ExtractionError) as exc_info:
        backend.extract(pdf)

    # Necessary but not sufficient: outer wrap text alone.
    assert secret not in str(exc_info.value)
    # Sufficient: the surface CI logs / paralegal-visible logs walk.
    exc = exc_info.value
    rendered = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    assert secret not in rendered, (
        "api_key leaked through __cause__-chain rendering — "
        "AuthenticationError branch must use ``raise ... from None``"
    )


def test_generic_api_error_is_wrapped(tmp_path) -> None:
    """A non-specialized anthropic.APIError raises ExtractionError, chained.

    Per spec §8.5, the generic fallthrough preserves the cause-class name
    in the wrap message so paralegals reading the log can distinguish it
    from the specialized subclass mappings. ``__cause__`` is retained
    (unlike the AuthenticationError branch) so debug-time inspection has
    access to the SDK's original message and request.
    """
    from trust_generator.v3.extraction import ExtractionError
    from trust_generator.v3.extraction.anthropic_backend import AnthropicBackend

    err = anthropic.APIError(message="unexpected", request=MagicMock(), body=None)
    backend = AnthropicBackend(
        model="claude-sonnet-4-6", client=_make_failing_client(err)
    )
    pdf = _make_pdf_fixture(tmp_path)

    with pytest.raises(ExtractionError) as exc_info:
        backend.extract(pdf)

    assert exc_info.value.__cause__ is err
    # Class-name discriminator: the generic fallthrough must name the
    # subclass that triggered it so the log distinguishes a bare APIError
    # from a not-yet-mapped subclass.
    assert "APIError" in str(exc_info.value)


def test_tool_use_refusal_under_auto_choice_raises(tmp_path) -> None:
    """No tool_use block in response (stop_reason='end_turn' with text-only
    content) → ExtractionError with stop_reason in message."""
    from trust_generator.v3.extraction import ExtractionError
    from trust_generator.v3.extraction.anthropic_backend import AnthropicBackend

    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "I cannot extract this image."

    response = MagicMock()
    response.stop_reason = "end_turn"
    response.content = [text_block]

    client = MagicMock()
    client.messages.create.return_value = response
    backend = AnthropicBackend(
        model="claude-sonnet-4-6", client=client, mechanism="tool_use"
    )
    pdf = _make_pdf_fixture(tmp_path)

    with pytest.raises(ExtractionError) as exc_info:
        backend.extract(pdf)

    assert "end_turn" in str(exc_info.value)
    assert "submit_intake_extraction" in str(exc_info.value) or "tool_use" in str(
        exc_info.value
    )


def test_output_config_refusal_non_json_raises(tmp_path) -> None:
    """output_config mode + non-JSON text → ExtractionError with JSON parse failure."""
    from trust_generator.v3.extraction import ExtractionError
    from trust_generator.v3.extraction.anthropic_backend import AnthropicBackend

    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "I refuse to process this image."

    response = MagicMock()
    response.stop_reason = "end_turn"
    response.content = [text_block]

    client = MagicMock()
    client.messages.create.return_value = response
    backend = AnthropicBackend(
        model="claude-sonnet-4-6", client=client, mechanism="output_config"
    )
    pdf = _make_pdf_fixture(tmp_path)

    with pytest.raises(ExtractionError, match="(?i)json"):
        backend.extract(pdf)


def test_tool_use_malformed_input_raises_validation_error_wrap(tmp_path) -> None:
    """tool_use.input does not match envelope schema → ExtractionError."""
    from pydantic import ValidationError

    from trust_generator.v3.extraction import ExtractionError
    from trust_generator.v3.extraction.anthropic_backend import AnthropicBackend

    # Missing required structure: pass a string where a dict is expected.
    tool_use_block = MagicMock()
    tool_use_block.type = "tool_use"
    tool_use_block.name = "submit_intake_extraction"
    tool_use_block.input = {"grantors": "not-a-list", "beneficiaries": []}

    response = MagicMock()
    response.stop_reason = "tool_use"
    response.content = [tool_use_block]

    client = MagicMock()
    client.messages.create.return_value = response
    backend = AnthropicBackend(
        model="claude-sonnet-4-6", client=client, mechanism="tool_use"
    )
    pdf = _make_pdf_fixture(tmp_path)

    with pytest.raises(ExtractionError) as exc_info:
        backend.extract(pdf)

    assert isinstance(exc_info.value.__cause__, ValidationError)
    assert "schema-invalid" in str(exc_info.value).lower() or "envelope" in str(
        exc_info.value
    ).lower()


def test_output_config_unknown_keys_raises_validation_error_wrap(tmp_path) -> None:
    """output_config mode + JSON that violates extra='forbid' → ExtractionError."""
    import json

    from pydantic import ValidationError

    from trust_generator.v3.extraction import ExtractionError
    from trust_generator.v3.extraction.anthropic_backend import AnthropicBackend

    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = json.dumps(
        {
            "grantors": [],
            "beneficiaries": [],
            "rogue_reasoning_field": "should be rejected by extra=forbid",
        }
    )

    response = MagicMock()
    response.stop_reason = "end_turn"
    response.content = [text_block]

    client = MagicMock()
    client.messages.create.return_value = response
    backend = AnthropicBackend(
        model="claude-sonnet-4-6", client=client, mechanism="output_config"
    )
    pdf = _make_pdf_fixture(tmp_path)

    with pytest.raises(ExtractionError) as exc_info:
        backend.extract(pdf)

    assert isinstance(exc_info.value.__cause__, ValidationError)


def test_anthropic_backend_satisfies_extraction_protocol() -> None:
    """Structural type check: ``AnthropicBackend`` matches
    ``ExtractionProtocol`` (mirrors the 4.3a 9b cycle 5 test on
    OllamaBackend).

    Pattern: assignment to a variable typed as ``ExtractionProtocol``
    forces the static type checker (mypy) to verify structural
    compatibility. At runtime the Protocol is not @runtime_checkable
    (per spec 4.3a §5.4 commentary), so the test serves primarily as
    a mypy gate; the runtime assertion is the absence of an exception
    during construction and assignment.
    """
    from trust_generator.v3.extraction import (
        AnthropicBackend,
        ExtractionProtocol,
    )

    backend: ExtractionProtocol = AnthropicBackend(
        model="claude-sonnet-4-6", client=MagicMock()
    )
    # Probe the protocol method exists on the bound instance.
    assert callable(backend.extract)


# --- Cycle 8: PDF size + page-count prechecks ---------------------------------


def test_pdf_size_precheck_raises_before_api_call(tmp_path: Path) -> None:
    """A PDF exceeding the Anthropic PDF file-size limit raises ExtractionError
    *before* any client.messages.create call (spec §8.5).

    Per Anthropic docs at SDK pin time: PDF documents accept up to 32 MiB.
    """
    oversized = tmp_path / "oversized.pdf"
    # 33 MiB of zero bytes — beyond the 32 MiB Anthropic PDF cap.
    oversized.write_bytes(b"%PDF-1.7\n" + b"\x00" * (33 * 1024 * 1024))

    fake_client = MagicMock()
    backend = AnthropicBackend(
        model=_TEST_MODEL,
        client=fake_client,
    )

    with pytest.raises(ExtractionError, match=r"PDF exceeds Anthropic file-size limit"):
        backend.extract(oversized)

    fake_client.messages.create.assert_not_called()


def test_pdf_page_count_precheck_raises_before_api_call(tmp_path: Path) -> None:
    """A PDF exceeding the model's context-window page-count limit raises
    ExtractionError before any API call (spec §8.5).

    The 200K-context tier (claude-sonnet-4-6 default) caps at 100 pages
    per the spec §8.1 constant pin. We mock pypdf so the disk fixture
    stays tiny.
    """
    small_pdf = tmp_path / "many_pages.pdf"
    small_pdf.write_bytes(b"%PDF-1.7\n" + b"\x00" * 1024)  # well under size cap

    fake_client = MagicMock()
    backend = AnthropicBackend(
        model=_TEST_MODEL,
        client=fake_client,
    )

    fake_pdf = MagicMock()
    fake_pdf.pages = [MagicMock()] * 101  # one over the 200K-tier limit

    with patch(
        "trust_generator.v3.extraction.anthropic_backend.PdfReader",
        return_value=fake_pdf,
    ), pytest.raises(ExtractionError, match=r"PDF exceeds Anthropic page limit"):
        backend.extract(small_pdf)

    fake_client.messages.create.assert_not_called()


# --- Cycle 9: Image source acceptance + image-size precheck -------------------


def test_image_source_uses_image_content_block(tmp_path: Path) -> None:
    """A JPG/PNG source produces an `image` content block, not a
    `document` block (spec §8.1 image branch; §9.1 test 12)."""
    jpg = tmp_path / "intake.jpg"
    # Minimal JPEG SOI + APP0 JFIF header + EOI bytes — mimetypes
    # resolves .jpg → image/jpeg from the suffix alone (no magic-byte
    # parse), so the actual content does not need to be a decodable JPEG.
    jpg.write_bytes(
        bytes.fromhex("ffd8ffe000104a464946") + b"\x00" * 64 + bytes.fromhex("ffd9")
    )

    fake_client = MagicMock()
    # output_config mode is the default; minimal text-block response
    # parses cleanly so extract() returns normally and call_args is
    # populated before assertion.
    fake_client.messages.create.return_value = _make_minimal_anthropic_response()

    backend = AnthropicBackend(
        model=_TEST_MODEL,
        client=fake_client,
    )

    try:
        backend.extract(jpg)
    except ExtractionError:
        # Defensive: if the minimal response shape changes for any
        # reason, fall through — we only care about call_args here.
        pass

    fake_client.messages.create.assert_called_once()
    _, kwargs = fake_client.messages.create.call_args
    user_message = kwargs["messages"][0]
    content_block = user_message["content"][0]

    assert content_block["type"] == "image", (
        f"Expected image content block for JPG source; got {content_block['type']!r}"
    )
    assert content_block["source"]["media_type"] == "image/jpeg"


def test_image_size_precheck_raises_before_api_call(tmp_path: Path) -> None:
    """An image exceeding the Anthropic image file-size limit (5 MiB)
    raises ExtractionError before any client.messages.create call.

    Per spec §8.5 + the lead's M2 finding: the size guard added in
    cycle 8 dispatches per-MIME and auto-extends to images once the
    allow-list expands in cycle 9 Green. This test asserts the
    auto-extension fires.
    """
    oversized = tmp_path / "oversized.jpg"
    # 6 MiB JPEG header + padding — beyond the 5 MiB image cap.
    oversized.write_bytes(
        bytes.fromhex("ffd8ffe000104a464946")
        + b"\x00" * (6 * 1024 * 1024 - 12)
        + bytes.fromhex("ffd9")
    )

    fake_client = MagicMock()
    backend = AnthropicBackend(
        model=_TEST_MODEL,
        client=fake_client,
    )

    with pytest.raises(ExtractionError, match=r"image exceeds Anthropic file-size limit"):
        backend.extract(oversized)

    fake_client.messages.create.assert_not_called()


# --- Cycle 11: Prompt-caching call-args (single-branch under G2-negative) -----


@pytest.mark.parametrize("mechanism", ["tool_use", "output_config"])
def test_cache_control_breakpoints_layout(
    tmp_path: Path,
    mechanism: str,
) -> None:
    """Spec §8.2 breakpoints 1 + 2 always-on; breakpoint 3 conditional on mode.

    Always-on:
      - cache_control={'type': 'ephemeral'} on system block (breakpoint 1)
      - cache_control on document/image content block (breakpoint 2)

    tool_use mode adds:
      - cache_control on tools-array entry (breakpoint 3 in tool_use mode)

    output_config mode does NOT assert cache_control on
    output_config.format — gate G2-negative confirmed at lead-time
    (auto-memory project-anthropic-api-gate-outcomes 2026-05-18:
    API rejects the placement with HTTP 400 "Extra inputs are not
    permitted").
    """
    pdf = _make_pdf_fixture(tmp_path)

    fake_client = MagicMock()
    fake_client.messages.create.return_value = _make_minimal_anthropic_response()

    backend = AnthropicBackend(
        model=_TEST_MODEL,
        client=fake_client,
        mechanism=mechanism,
    )

    try:
        backend.extract(pdf)
    except ExtractionError:
        pass  # we only assert on call kwargs

    fake_client.messages.create.assert_called_once()
    _, kwargs = fake_client.messages.create.call_args

    # Breakpoint 1: system block.
    system_blocks = kwargs["system"]
    assert any(
        block.get("cache_control") == {"type": "ephemeral"} for block in system_blocks
    ), f"system block missing cache_control: {system_blocks!r}"

    # Breakpoint 2: document/image content block on the user message.
    user_message = kwargs["messages"][0]
    content_block = user_message["content"][0]
    assert content_block.get("cache_control") == {"type": "ephemeral"}, (
        f"content block missing cache_control: {content_block!r}"
    )

    if mechanism == "tool_use":
        # Breakpoint 3 in tool_use mode: tools-array entry.
        tools = kwargs.get("tools") or []
        assert tools, "tool_use mode must pass a tools array"
        assert tools[0].get("cache_control") == {"type": "ephemeral"}, (
            f"tools[0] missing cache_control: {tools[0]!r}"
        )
    else:
        # output_config mode: per G2-negative, format-block cache_control
        # would be API-rejected. Defensive negative assertion documents
        # that this plan intentionally does NOT place cache_control here.
        output_config = kwargs.get("output_config") or {}
        format_block = output_config.get("format") or {}
        assert "cache_control" not in format_block, (
            f"output_config.format must NOT carry cache_control "
            f"(API-rejected per gate G2-negative); got {format_block!r}"
        )


# --- Cycle 12: Extended-thinking always-on + tool_choice=auto (G1-positive) ---


@pytest.mark.parametrize("mechanism", ["tool_use", "output_config"])
def test_thinking_param_always_present(
    tmp_path: Path,
    mechanism: str,
) -> None:
    """Spec §8.3 (under gate G1-positive): extended thinking is always-on.

    The constructor's thinking_budget_tokens default is 5000 per spec §6
    / core cycle 4. This test asserts the parameter lands on the
    messages.create call with that budget, in both mechanism branches.
    """
    pdf = _make_pdf_fixture(tmp_path)

    fake_client = MagicMock()
    fake_client.messages.create.return_value = _make_minimal_anthropic_response()

    backend = AnthropicBackend(
        model=_TEST_MODEL,
        client=fake_client,
        mechanism=mechanism,
    )

    try:
        backend.extract(pdf)
    except ExtractionError:
        pass

    fake_client.messages.create.assert_called_once()
    _, kwargs = fake_client.messages.create.call_args

    assert kwargs.get("thinking") == {"type": "enabled", "budget_tokens": 5000}, (
        f"thinking must be always-on with budget=5000 (spec §8.3, "
        f"gate G1-positive); got {kwargs.get('thinking')!r}"
    )


def test_tool_use_mode_uses_auto_choice(tmp_path: Path) -> None:
    """Spec §8.4 thinking-compat: tool_use mode must run under
    tool_choice={'type': 'auto'}; never {'type': 'tool'} or
    {'type': 'any'} (incompatible with extended thinking per
    Anthropic docs).
    """
    pdf = _make_pdf_fixture(tmp_path)

    fake_client = MagicMock()
    fake_client.messages.create.return_value = _make_minimal_anthropic_response()

    backend = AnthropicBackend(
        model=_TEST_MODEL,
        client=fake_client,
        mechanism="tool_use",
    )

    try:
        backend.extract(pdf)
    except ExtractionError:
        pass

    fake_client.messages.create.assert_called_once()
    _, kwargs = fake_client.messages.create.call_args

    assert kwargs.get("tool_choice") == {"type": "auto"}, (
        f"tool_use mode must use tool_choice={{'type': 'auto'}}; "
        f"got {kwargs.get('tool_choice')!r}"
    )
    # Defensive negatives.
    assert kwargs.get("tool_choice") != {"type": "tool"}, (
        "forbidden tool_choice (thinking-incompatible per spec §8.4)"
    )
    assert kwargs.get("tool_choice") != {"type": "any"}, (
        "forbidden tool_choice (thinking-incompatible per spec §8.4)"
    )


# --- Cycle 13b: Pin mechanism default to benchmark winner ---------------------


import json as _json

_MECHANISM_LOG_DIR = (
    Path(__file__).resolve().parents[3] / "tests/data/anthropic_mechanism_log"
)
_DECISION_PATH = _MECHANISM_LOG_DIR / "_decision.json"


def test_default_mechanism_matches_benchmark_winner() -> None:
    """Spec §7 row 13b — AnthropicBackend default `mechanism` matches
    the cycle 13a benchmark winner recorded in _decision.json.

    Skips if _decision.json is absent (e.g., a fresh clone where task
    13a has not run). The skip is intentional: the benchmark is opt-in
    (real API spend gated by project-anthropic-api-credit-cap); the
    unit suite cannot block on it.
    """
    if not _DECISION_PATH.exists():
        pytest.skip(
            f"benchmark decision file absent at {_DECISION_PATH}; "
            f"run task 13a (mechanism benchmark) to generate it"
        )

    decision = _json.loads(_DECISION_PATH.read_text())
    winner = decision["winner"]
    assert winner in ("tool_use", "output_config"), (
        f"_decision.json winner must be 'tool_use' or 'output_config'; "
        f"got {winner!r}"
    )

    # Use a MagicMock client so __init__'s eager validation (if any)
    # does not require a real API key. Mirror cycles 8/9 pattern.
    backend = AnthropicBackend(
        model=_TEST_MODEL,
        client=MagicMock(),
    )

    assert backend.mechanism == winner, (
        f"AnthropicBackend default mechanism is {backend.mechanism!r}, "
        f"but the cycle 13a benchmark "
        f"({decision.get('winner_log_files', ['_decision.json'])[0]}) "
        f"selected {winner!r}. Flip the ctor default to match."
    )


# --- Chore #46: error-handling hardening --------------------------------------


def test_map_grantor_anthropic_envelope_empty_second_grantor_no_co_grantor() -> None:
    """Chore #46 item M: a second grantor envelope with NO populated field
    (and no illegible flag) must NOT signal needs_co_grantor — gating on
    list length alone would materialize an empty co_grantor downstream.
    """
    from trust_generator.v3.extraction.anthropic_backend import (
        AnthropicGrantorEnvelope,
        _map_grantor_anthropic_envelope,
    )

    fields, needs_co_grantor = _map_grantor_anthropic_envelope(
        [
            AnthropicGrantorEnvelope(full_legal_name="A"),
            AnthropicGrantorEnvelope(),  # empty second envelope
        ]
    )

    assert needs_co_grantor is False
    assert [f.field_path for f in fields] == ["grantor.full_legal_name"]


def test_anthropic_envelope_empty_second_grantor_dematerializes_co_grantor() -> None:
    """Chore #46 item M (composer side): an empty grantors[1] must leave
    ``data.co_grantor`` as None rather than an empty GrantorInfo()."""
    from trust_generator.v3.extraction.anthropic_backend import (
        AnthropicGenerationEnvelope,
        AnthropicGrantorEnvelope,
        _anthropic_envelope_to_extraction_result,
    )

    env = AnthropicGenerationEnvelope(
        grantors=[
            AnthropicGrantorEnvelope(full_legal_name="Alice"),
            AnthropicGrantorEnvelope(),  # empty
        ],
    )
    result = _anthropic_envelope_to_extraction_result(env, model=_TEST_MODEL)

    assert result.data.co_grantor is None


def test_map_grantor_anthropic_envelope_illegible_second_grantor_signals_co() -> None:
    """Chore #46 item M: an illegible-flag-only second grantor DOES count
    as content — it produces a FieldExtraction — so co_grantor is signaled.
    """
    from trust_generator.v3.extraction.anthropic_backend import (
        AnthropicFieldFlag,
        AnthropicGrantorEnvelope,
        _map_grantor_anthropic_envelope,
    )

    _, needs_co_grantor = _map_grantor_anthropic_envelope(
        [
            AnthropicGrantorEnvelope(full_legal_name="A"),
            AnthropicGrantorEnvelope(
                full_legal_name_flag=AnthropicFieldFlag(illegible=True),
            ),
        ]
    )

    assert needs_co_grantor is True


def test_load_pdf_or_image_unsupported_mime_raises_extraction_error(
    tmp_path: Path,
) -> None:
    """Chore #46 test backfill: a source with an unsupported MIME type
    (e.g. .txt) raises ExtractionError, not a bare error."""
    txt = tmp_path / "intake.txt"
    txt.write_text("not a pdf or image", encoding="utf-8")

    backend = AnthropicBackend(model=_TEST_MODEL, client=MagicMock())

    with pytest.raises(ExtractionError, match="unsupported source mime-type"):
        backend.extract(txt)


def test_load_pdf_or_image_permission_error_wrapped_as_extraction_error(
    tmp_path: Path,
) -> None:
    """Chore #46 item H3: a source that passes ``exists()`` but whose
    ``open()`` raises ``PermissionError`` must surface as ExtractionError,
    not a raw OSError escaping the ExtractionProtocol contract.
    """
    pdf = _make_pdf_fixture(tmp_path)
    backend = AnthropicBackend(model=_TEST_MODEL, client=MagicMock())

    original_open = Path.open

    def _denied_open(self: Path, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        if self == pdf:
            raise PermissionError("permission denied")
        return original_open(self, *args, **kwargs)  # type: ignore[arg-type]

    with patch.object(Path, "open", _denied_open), pytest.raises(
        ExtractionError, match="could not read source path"
    ):
        backend.extract(pdf)


def test_load_pdf_or_image_stat_oserror_wrapped_as_extraction_error(
    tmp_path: Path,
) -> None:
    """Chore #46 item H3: an ``OSError`` from the ``source.stat()`` size
    probe (TOCTOU race after ``exists()``) is mapped to ExtractionError,
    not propagated raw.

    ``Path.exists()`` itself calls ``stat`` with the ``follow_symlinks``
    kwarg; the size-probe ``source.stat()`` call passes no kwargs. The
    mock raises only on the kwarg-less call so ``exists()`` still
    succeeds and execution reaches the wrapped probe.
    """
    pdf = _make_pdf_fixture(tmp_path)
    backend = AnthropicBackend(model=_TEST_MODEL, client=MagicMock())

    original_stat = Path.stat

    def _failing_stat(self: Path, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        if self == pdf and not args and not kwargs:
            raise OSError("stat failed")
        return original_stat(self, *args, **kwargs)  # type: ignore[arg-type]

    with patch.object(Path, "stat", _failing_stat), pytest.raises(
        ExtractionError, match="could not stat source path"
    ):
        backend.extract(pdf)


def test_corrupt_pdf_pypdf_error_wrapped_as_extraction_error(
    tmp_path: Path,
) -> None:
    """Chore #46 item H4: a corrupt PDF makes ``PdfReader`` raise a raw
    ``pypdf`` error during page-counting; it must be wrapped as
    ExtractionError so the contract is honoured.
    """
    from pypdf.errors import PdfReadError

    corrupt = tmp_path / "corrupt.pdf"
    # .pdf suffix → mimetypes resolves application/pdf; content is junk.
    corrupt.write_bytes(b"%PDF-1.7\nthis is not a real pdf body\n")
    backend = AnthropicBackend(model=_TEST_MODEL, client=MagicMock())

    with patch(
        "trust_generator.v3.extraction.anthropic_backend.PdfReader",
        side_effect=PdfReadError("corrupt pdf"),
    ), pytest.raises(ExtractionError, match="could not read PDF") as exc_info:
        backend.extract(corrupt)

    assert isinstance(exc_info.value.__cause__, PdfReadError)


def test_output_config_empty_text_blocks_surfaces_stop_reason(tmp_path: Path) -> None:
    """Chore #46 item A3: an output_config response with no text content
    (refusal) raises ExtractionError naming ``stop_reason`` — it must NOT
    be misreported as a JSON parse failure on the empty string.
    """
    response = MagicMock()
    response.stop_reason = "refusal"
    response.content = []  # no text blocks at all

    client = MagicMock()
    client.messages.create.return_value = response
    backend = AnthropicBackend(
        model=_TEST_MODEL, client=client, mechanism="output_config"
    )
    pdf = _make_pdf_fixture(tmp_path)

    with pytest.raises(ExtractionError) as exc_info:
        backend.extract(pdf)

    msg = str(exc_info.value)
    assert "refusal" in msg  # stop_reason surfaced
    assert "no text content" in msg
    # Must NOT be the JSON-parse-failure phrasing for an empty string.
    assert "JSON parse failure" not in msg


def test_output_config_json_non_mapping_raises(tmp_path: Path) -> None:
    """Chore #46 test backfill: output_config text that decodes to valid
    JSON but a non-mapping payload (e.g. a list) raises ExtractionError.
    """
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = '["not", "a", "mapping"]'

    response = MagicMock()
    response.stop_reason = "end_turn"
    response.content = [text_block]

    client = MagicMock()
    client.messages.create.return_value = response
    backend = AnthropicBackend(
        model=_TEST_MODEL, client=client, mechanism="output_config"
    )
    pdf = _make_pdf_fixture(tmp_path)

    with pytest.raises(ExtractionError, match="non-mapping"):
        backend.extract(pdf)


def test_tool_use_input_non_dict_raises_extraction_error(tmp_path: Path) -> None:
    """Chore #46 test backfill: a tool_use block whose ``input`` is not a
    mapping (e.g. a list) raises ExtractionError naming the bad type.
    """
    tool_use_block = MagicMock()
    tool_use_block.type = "tool_use"
    tool_use_block.name = "submit_intake_extraction"
    tool_use_block.input = ["not", "a", "dict"]

    response = MagicMock()
    response.stop_reason = "tool_use"
    response.content = [tool_use_block]

    client = MagicMock()
    client.messages.create.return_value = response
    backend = AnthropicBackend(
        model=_TEST_MODEL, client=client, mechanism="tool_use"
    )
    pdf = _make_pdf_fixture(tmp_path)

    with pytest.raises(ExtractionError, match="not a mapping"):
        backend.extract(pdf)


def test_generic_api_error_includes_sdk_message(tmp_path: Path) -> None:
    """Chore #46 item A4: the generic (non-auth) fallthrough in
    ``_wrap_anthropic_error`` includes the sanitized SDK message — the
    api_key-hygiene message-drop applies ONLY to AuthenticationError.
    """
    err = anthropic.APIError(
        message="model overloaded; retry later",
        request=MagicMock(),
        body=None,
    )
    backend = AnthropicBackend(
        model=_TEST_MODEL, client=_make_failing_client(err)
    )
    pdf = _make_pdf_fixture(tmp_path)

    with pytest.raises(ExtractionError) as exc_info:
        backend.extract(pdf)

    msg = str(exc_info.value)
    assert "APIError" in msg  # class-name discriminator preserved
    assert "model overloaded; retry later" in msg  # SDK message surfaced
