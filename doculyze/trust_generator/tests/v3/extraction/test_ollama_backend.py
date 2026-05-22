"""Cycle 9b-3 tests — OllamaBackend.extract happy path."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock


def _make_mock_client_returning(envelope_json: str) -> MagicMock:
    """Construct a MagicMock-shaped ollama.Client whose chat() returns
    a response object with .message.content equal to envelope_json."""
    response = MagicMock()
    response.message.content = envelope_json
    client = MagicMock()
    client.chat.return_value = response
    return client


def test_ollama_backend_importable() -> None:
    """``OllamaBackend`` is importable from the extraction package."""
    from trust_generator.v3.extraction import OllamaBackend

    assert OllamaBackend.__name__ == "OllamaBackend"


def test_ollama_backend_in_dunder_all() -> None:
    """``OllamaBackend`` is exported via ``__all__``."""
    from trust_generator.v3.extraction import __all__

    assert "OllamaBackend" in __all__


def test_ollama_backend_constructor_accepts_model() -> None:
    """``OllamaBackend(model='qwen2.5vl:7b')`` constructs."""
    from trust_generator.v3.extraction import OllamaBackend

    backend = OllamaBackend(model="qwen2.5vl:7b", client=MagicMock())
    assert backend.model == "qwen2.5vl:7b"


def test_ollama_backend_constructor_accepts_injected_client() -> None:
    """The ``client`` parameter is honored when provided."""
    from trust_generator.v3.extraction import OllamaBackend

    injected = MagicMock()
    backend = OllamaBackend(model="qwen2.5vl:7b", client=injected)
    assert backend.client is injected


def test_ollama_backend_constructor_accepts_prompt_builder() -> None:
    """The ``prompt_builder`` parameter is honored when provided."""
    from trust_generator.v3.extraction import OllamaBackend

    custom = lambda: "custom prompt"
    backend = OllamaBackend(
        model="qwen2.5vl:7b",
        client=MagicMock(),
        prompt_builder=custom,
    )
    assert backend.prompt_builder is custom


def test_ollama_backend_satisfies_extraction_protocol_structurally() -> None:
    """An ``OllamaBackend`` instance satisfies ``ExtractionProtocol``.

    Spec §5.4 — ExtractionProtocol is NOT @runtime_checkable; the
    structural type-check role is served by the static type checker.
    This test pins the assignability via a typed local annotation.
    mypy will reject this assignment if ``OllamaBackend.extract`` has
    drifted from the Protocol signature.
    """
    from trust_generator.v3.extraction import ExtractionProtocol, OllamaBackend

    backend: ExtractionProtocol = OllamaBackend(model="qwen2.5vl:7b", client=MagicMock())
    assert backend is not None  # runtime no-op; the assignment IS the test


def test_ollama_backend_extract_returns_extraction_result() -> None:
    """``extract`` returns an ExtractionResult on the happy path."""
    from trust_generator.v3.extraction import ExtractionResult, OllamaBackend

    envelope_json = (
        '{"reasoning": "Form has one grantor and one beneficiary.",'
        ' "grantors": [{"full_legal_name": "James William Thompson, Jr.",'
        '              "full_legal_name_diag": {"illegible": false, "note": null},'
        '              "date_of_birth": "March 15, 1958",'
        '              "date_of_birth_diag": {"illegible": false, "note": null}}],'
        ' "beneficiaries": []}'
    )
    client = _make_mock_client_returning(envelope_json)
    backend = OllamaBackend(model="qwen2.5vl:7b", client=client)

    result = backend.extract(Path("fake.png"))

    assert isinstance(result, ExtractionResult)


def test_ollama_backend_extract_trace_has_correct_backend_id() -> None:
    """``trace.backend_id`` follows the ``ollama:<model>`` convention (spec §5.3)."""
    from trust_generator.v3.extraction import OllamaBackend

    envelope_json = '{"reasoning": "empty form", "grantors": [], "beneficiaries": []}'
    client = _make_mock_client_returning(envelope_json)
    backend = OllamaBackend(model="qwen2.5vl:7b", client=client)

    result = backend.extract(Path("fake.png"))

    assert result.trace.backend_id == "ollama:qwen2.5vl:7b"


def test_ollama_backend_extract_trace_extracted_at_is_set() -> None:
    """``trace.extracted_at`` is set to a tz-aware datetime."""
    from trust_generator.v3.extraction import OllamaBackend

    before = datetime.now(UTC)
    envelope_json = '{"reasoning": "empty form", "grantors": [], "beneficiaries": []}'
    client = _make_mock_client_returning(envelope_json)
    backend = OllamaBackend(model="qwen2.5vl:7b", client=client)

    result = backend.extract(Path("fake.png"))
    after = datetime.now(UTC)

    assert result.trace.extracted_at.tzinfo is not None
    assert before <= result.trace.extracted_at <= after


def test_ollama_backend_extract_emits_field_per_non_none_envelope_data() -> None:
    """One FieldExtraction per non-None envelope data field (spec §8.3 omit-if-absent).

    Field paths follow spec §7.3.1: envelope.grantors[0] → field_path 'grantor.*'
    (singular; collapses onto TrustData.grantor). Verifies trace fields
    resolve via extraction.paths.resolve against a default-constructed
    TrustData (i.e., the path syntax is valid, not the values).
    """
    from trust_generator.v3.extraction import OllamaBackend, resolve
    from trust_generator.v3.schema import TrustData

    envelope_json = (
        '{"reasoning": "Form has grantor name; date is illegible.",'
        ' "grantors": [{"full_legal_name": "James William Thompson, Jr.",'
        '              "full_legal_name_diag": {"illegible": false, "note": null},'
        '              "date_of_birth": null,'
        '              "date_of_birth_diag": {"illegible": true, "note": "smudged"}}],'
        ' "beneficiaries": []}'
    )
    client = _make_mock_client_returning(envelope_json)
    backend = OllamaBackend(model="qwen2.5vl:7b", client=client)

    result = backend.extract(Path("fake.png"))

    field_paths = [f.field_path for f in result.trace.fields]
    assert "grantor.full_legal_name" in field_paths
    # date_of_birth was illegible AND null → emit FieldExtraction with illegible=True
    assert "grantor.date_of_birth" in field_paths

    # Spec §7.3.1 — paths must resolve against TrustData via paths.resolve.
    # Resolution is tested against a default TrustData since the mapper does
    # NOT propagate values into data (spec §7.3.4 validator-fragility coercion).
    default_data = TrustData()
    for path in field_paths:
        resolved, _ = resolve(default_data, path)
        assert resolved, f"field_path {path!r} does not resolve against TrustData"


def test_ollama_backend_extract_collapses_two_grantors_to_co_grantor() -> None:
    """Spec §7.3.1 — envelope.grantors[1] → field_path 'co_grantor.*', and
    TrustData.co_grantor is instantiated (no longer None) when present.
    """
    from trust_generator.v3.extraction import OllamaBackend, resolve

    envelope_json = (
        '{"reasoning": "Joint trust with two grantors.",'
        ' "grantors": ['
        '   {"full_legal_name": "James William Thompson, Jr.",'
        '    "full_legal_name_diag": {"illegible": false, "note": null},'
        '    "date_of_birth": null,'
        '    "date_of_birth_diag": {"illegible": false, "note": null}},'
        '   {"full_legal_name": "Mary-Beth O\'Brien Thompson",'
        '    "full_legal_name_diag": {"illegible": false, "note": null},'
        '    "date_of_birth": null,'
        '    "date_of_birth_diag": {"illegible": false, "note": null}}'
        ' ],'
        ' "beneficiaries": []}'
    )
    client = _make_mock_client_returning(envelope_json)
    backend = OllamaBackend(model="qwen2.5vl:7b", client=client)

    result = backend.extract(Path("fake.png"))

    field_paths = [f.field_path for f in result.trace.fields]
    assert "grantor.full_legal_name" in field_paths
    assert "co_grantor.full_legal_name" in field_paths
    # TrustData.co_grantor must be instantiated for the co_grantor.* path to resolve.
    assert result.data.co_grantor is not None
    resolved, _ = resolve(result.data, "co_grantor.full_legal_name")
    assert resolved


def test_ollama_backend_extract_maps_beneficiaries_to_other_beneficiaries() -> None:
    """Spec §7.3.1 + §7.3.2 — envelope.beneficiaries[i] defaults to
    other_beneficiaries[i] (conservative classification fallback). The
    corresponding beneficiary_shares[i].recipient_ref is the canonical
    string id 'other_beneficiaries[{i}]'.
    """
    from trust_generator.v3.extraction import OllamaBackend, resolve

    envelope_json = (
        '{"reasoning": "One beneficiary with a share.",'
        ' "grantors": [],'
        ' "beneficiaries": [{'
        '   "full_legal_name": "Michael Thompson",'
        '   "full_legal_name_diag": {"illegible": false, "note": null},'
        '   "relationship": "child",'
        '   "relationship_diag": {"illegible": false, "note": null},'
        '   "share_percent": "100",'
        '   "share_percent_diag": {"illegible": false, "note": null}}]}'
    )
    client = _make_mock_client_returning(envelope_json)
    backend = OllamaBackend(model="qwen2.5vl:7b", client=client)

    result = backend.extract(Path("fake.png"))

    field_paths = [f.field_path for f in result.trace.fields]
    assert "other_beneficiaries[0].full_legal_name" in field_paths
    assert "other_beneficiaries[0].relationship_other" in field_paths
    assert "beneficiary_shares[0].share_percent" in field_paths

    assert len(result.data.other_beneficiaries) == 1
    assert len(result.data.beneficiary_shares) == 1
    assert result.data.beneficiary_shares[0].recipient_ref == "other_beneficiaries[0]"

    for path in field_paths:
        resolved, _ = resolve(result.data, path)
        assert resolved, f"field_path {path!r} does not resolve against TrustData"


def test_ollama_backend_extract_empty_form_yields_default_trust_data() -> None:
    """Spec §7.6 row 5 — empty form (no fields) is NOT a failure: the result
    is a default-constructed TrustData paired with an empty-fields trace.
    """
    from trust_generator.v3.extraction import OllamaBackend
    from trust_generator.v3.schema import TrustData

    envelope_json = (
        '{"reasoning": "Form is blank or unreadable.",'
        ' "grantors": [],'
        ' "beneficiaries": []}'
    )
    client = _make_mock_client_returning(envelope_json)
    backend = OllamaBackend(model="qwen2.5vl:7b", client=client)

    result = backend.extract(Path("fake.png"))

    assert result.trace.fields == []
    # Default-constructed: no co_grantor, no beneficiary lists populated, etc.
    default = TrustData()
    assert result.data.co_grantor == default.co_grantor  # both None
    assert result.data.other_beneficiaries == default.other_beneficiaries  # both []
    assert result.data.beneficiary_shares == default.beneficiary_shares  # both []


def test_ollama_backend_extract_legible_deferred_fields_use_incomplete_sentinel() -> None:
    """Spec §7.3.3 — non-string TrustData fields (Decimal share_percent,
    date_of_birth) leave normalized_value as the INCOMPLETE sentinel when
    legible but not yet normalized. The IncompleteUntilValidated marker
    on FieldExtraction.normalized_value enforces this discipline at the
    type level; the mapper enforces it at runtime.

    Plan 9c's diagnostics integration emits ``extraction.no_normalized_value``
    when a field is legible but normalized_value is INCOMPLETE/None at
    verify time — this test pins that the mapper produces the signal
    correctly.
    """
    from trust_generator.v3.extraction import OllamaBackend
    from trust_generator.v3.extraction.trace import INCOMPLETE

    envelope_json = (
        '{"reasoning": "Form has grantor DOB and one beneficiary with share.",'
        ' "grantors": [{"full_legal_name": "James William Thompson, Jr.",'
        '              "full_legal_name_diag": {"illegible": false, "note": null},'
        '              "date_of_birth": "March 15, 1958",'
        '              "date_of_birth_diag": {"illegible": false, "note": null}}],'
        ' "beneficiaries": [{"full_legal_name": "Michael Thompson",'
        '                    "full_legal_name_diag": {"illegible": false, "note": null},'
        '                    "relationship": null,'
        '                    "relationship_diag": {"illegible": false, "note": null},'
        '                    "share_percent": "100",'
        '                    "share_percent_diag": {"illegible": false, "note": null}}]}'
    )
    client = _make_mock_client_returning(envelope_json)
    backend = OllamaBackend(model="qwen2.5vl:7b", client=client)

    result = backend.extract(Path("fake.png"))

    by_path = {f.field_path: f for f in result.trace.fields}
    # date_of_birth is legible but date-normalization is deferred → INCOMPLETE.
    assert by_path["grantor.date_of_birth"].normalized_value is INCOMPLETE
    assert by_path["grantor.date_of_birth"].raw_value == "March 15, 1958"
    # share_percent is legible but Decimal-normalization is deferred → INCOMPLETE.
    assert by_path["beneficiary_shares[0].share_percent"].normalized_value is INCOMPLETE
    assert by_path["beneficiary_shares[0].share_percent"].raw_value == "100"
    # full_legal_name is str → str (no normalization needed); INCOMPLETE not used.
    assert (
        by_path["grantor.full_legal_name"].normalized_value
        == "James William Thompson, Jr."
    )


def test_ollama_backend_extract_illegible_yields_normalized_value_none() -> None:
    """Spec §7.6 row 4 + FieldExtraction._illegible_excludes_normalized_value
    invariant: when envelope.field_diag.illegible is True, the trace's
    FieldExtraction.normalized_value is None (NOT the raw envelope value).
    """
    from trust_generator.v3.extraction import OllamaBackend

    # Envelope where the data field is null but diag flags illegible:
    # the mapper emits a FieldExtraction(illegible=True, normalized_value=None).
    envelope_json = (
        '{"reasoning": "Grantor name is smudged beyond recognition.",'
        ' "grantors": [{"full_legal_name": null,'
        '              "full_legal_name_diag": {"illegible": true, "note": "ink smudge"},'
        '              "date_of_birth": null,'
        '              "date_of_birth_diag": {"illegible": false, "note": null}}],'
        ' "beneficiaries": []}'
    )
    client = _make_mock_client_returning(envelope_json)
    backend = OllamaBackend(model="qwen2.5vl:7b", client=client)

    result = backend.extract(Path("fake.png"))

    illegible_fields = [f for f in result.trace.fields if f.illegible]
    assert len(illegible_fields) == 1
    assert illegible_fields[0].field_path == "grantor.full_legal_name"
    assert illegible_fields[0].normalized_value is None
    assert illegible_fields[0].raw_value == ""


def test_ollama_backend_extract_passes_format_schema_to_client() -> None:
    """``client.chat`` is invoked with ``format=GenerationEnvelope.model_json_schema()``."""
    from trust_generator.v3.extraction import OllamaBackend
    from trust_generator.v3.extraction.ollama_backend import GenerationEnvelope

    envelope_json = '{"reasoning": "empty form", "grantors": [], "beneficiaries": []}'
    client = _make_mock_client_returning(envelope_json)
    backend = OllamaBackend(model="qwen2.5vl:7b", client=client)

    backend.extract(Path("fake.png"))

    call_kwargs = client.chat.call_args.kwargs
    assert call_kwargs["format"] == GenerationEnvelope.model_json_schema()


def test_ollama_backend_extract_passes_temperature_zero_to_client() -> None:
    """``client.chat`` is invoked with ``options={"temperature": 0}`` (spec §7.4 determinism)."""
    from trust_generator.v3.extraction import OllamaBackend

    envelope_json = '{"reasoning": "empty form", "grantors": [], "beneficiaries": []}'
    client = _make_mock_client_returning(envelope_json)
    backend = OllamaBackend(model="qwen2.5vl:7b", client=client)

    backend.extract(Path("fake.png"))

    call_kwargs = client.chat.call_args.kwargs
    assert call_kwargs["options"] == {"temperature": 0}


def test_ollama_backend_extract_passes_image_path_as_str(tmp_path: Path) -> None:
    """``messages[0]['images']`` carries the resolved path as a string (spec §7.6)."""
    from trust_generator.v3.extraction import OllamaBackend

    fake_image = tmp_path / "form.png"
    fake_image.touch()

    envelope_json = '{"reasoning": "empty form", "grantors": [], "beneficiaries": []}'
    client = _make_mock_client_returning(envelope_json)
    backend = OllamaBackend(model="qwen2.5vl:7b", client=client)

    backend.extract(fake_image)

    call_kwargs = client.chat.call_args.kwargs
    images = call_kwargs["messages"][0]["images"]
    assert images == [str(fake_image.resolve())]


def test_ollama_backend_extract_passes_prompt_to_client() -> None:
    """``messages[0]['content']`` carries the rendered prompt string."""
    from trust_generator.v3.extraction import OllamaBackend
    from trust_generator.v3.extraction.prompt import build_intake_prompt

    envelope_json = '{"reasoning": "empty form", "grantors": [], "beneficiaries": []}'
    client = _make_mock_client_returning(envelope_json)
    backend = OllamaBackend(model="qwen2.5vl:7b", client=client)

    backend.extract(Path("fake.png"))

    call_kwargs = client.chat.call_args.kwargs
    content = call_kwargs["messages"][0]["content"]
    assert content == build_intake_prompt()


def test_ollama_backend_extract_passes_model_to_client() -> None:
    """``client.chat`` is invoked with ``model=<self.model>``."""
    from trust_generator.v3.extraction import OllamaBackend

    envelope_json = '{"reasoning": "empty form", "grantors": [], "beneficiaries": []}'
    client = _make_mock_client_returning(envelope_json)
    backend = OllamaBackend(model="qwen2.5vl:7b", client=client)

    backend.extract(Path("fake.png"))

    call_kwargs = client.chat.call_args.kwargs
    assert call_kwargs["model"] == "qwen2.5vl:7b"
