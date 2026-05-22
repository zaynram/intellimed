"""Cycle 9b-1 tests — GenerationEnvelope schema and field-order discipline."""

from __future__ import annotations

import pytest
from pydantic import ValidationError


def test_generation_envelope_importable() -> None:
    """``GenerationEnvelope`` is importable from the ollama_backend module."""
    from trust_generator.v3.extraction.ollama_backend import GenerationEnvelope

    assert GenerationEnvelope.__name__ == "GenerationEnvelope"


def test_generation_envelope_is_pydantic_basemodel() -> None:
    """``GenerationEnvelope`` is a Pydantic BaseModel."""
    from pydantic import BaseModel

    from trust_generator.v3.extraction.ollama_backend import GenerationEnvelope

    assert issubclass(GenerationEnvelope, BaseModel)


def test_generation_envelope_reasoning_is_first_field() -> None:
    """``reasoning`` MUST be the first field in ``model_json_schema()`` properties.

    Spec §7.4 — grammar-constrained decoding generates fields in schema
    declaration order. A leading string-typed reasoning field is
    load-bearing for the chain-of-thought benefit under constrained
    decoding. This test catches accidental reordering.
    """
    from trust_generator.v3.extraction.ollama_backend import GenerationEnvelope

    properties = GenerationEnvelope.model_json_schema()["properties"]
    field_order = list(properties.keys())
    assert field_order[0] == "reasoning", (
        f"Expected 'reasoning' first; got {field_order[0]!r}. "
        f"See spec §7.4 — reordering requires evidence (chore #14)."
    )


def test_generation_envelope_reasoning_has_max_length() -> None:
    """The ``reasoning`` field has a concrete numeric ``maxLength`` constraint.

    Spec §6.4 pins this at 2000 characters (~500-token proxy). Without
    a max_length, the reasoning channel could produce unbounded output
    under constrained decoding and exhaust context.
    """
    from trust_generator.v3.extraction.ollama_backend import GenerationEnvelope

    properties = GenerationEnvelope.model_json_schema()["properties"]
    reasoning_schema = properties["reasoning"]
    assert reasoning_schema.get("maxLength") == 2000


def test_generation_envelope_validates_minimal_sample() -> None:
    """A minimal envelope (reasoning only, empty data) parses cleanly."""
    from trust_generator.v3.extraction.ollama_backend import GenerationEnvelope

    sample = '{"reasoning": "I see a form with grantor and beneficiary sections.", "grantors": [], "beneficiaries": []}'
    envelope = GenerationEnvelope.model_validate_json(sample)
    assert envelope.reasoning.startswith("I see a form")
    assert envelope.grantors == []
    assert envelope.beneficiaries == []


def test_generation_envelope_rejects_oversized_reasoning() -> None:
    """``reasoning`` exceeding max_length is rejected at validation time."""
    from trust_generator.v3.extraction.ollama_backend import GenerationEnvelope

    oversized = "x" * 2001
    with pytest.raises(ValidationError):
        GenerationEnvelope(reasoning=oversized)


def test_field_diag_importable_and_default_constructible() -> None:
    """``FieldDiag`` exists and constructs with no args."""
    from trust_generator.v3.extraction.ollama_backend import FieldDiag

    diag = FieldDiag()
    assert diag.illegible is False
    assert diag.note is None


def test_field_diag_note_max_length() -> None:
    """``FieldDiag.note`` has max_length=240 per spec §7.3."""
    from pydantic import ValidationError

    from trust_generator.v3.extraction.ollama_backend import FieldDiag

    with pytest.raises(ValidationError):
        FieldDiag(note="x" * 241)


def test_grantor_envelope_carries_diag_per_field() -> None:
    """``GrantorEnvelope`` exposes per-field diag channels for its fields."""
    from trust_generator.v3.extraction.ollama_backend import GrantorEnvelope

    envelope = GrantorEnvelope()
    assert envelope.full_legal_name is None
    assert envelope.full_legal_name_diag.illegible is False
    assert envelope.date_of_birth is None
    assert envelope.date_of_birth_diag.illegible is False


def test_beneficiary_envelope_carries_diag_per_field() -> None:
    """``BeneficiaryEnvelope`` exposes per-field diag channels for its fields."""
    from trust_generator.v3.extraction.ollama_backend import BeneficiaryEnvelope

    envelope = BeneficiaryEnvelope()
    assert envelope.full_legal_name is None
    assert envelope.full_legal_name_diag.illegible is False
    assert envelope.relationship is None
    assert envelope.relationship_diag.illegible is False
    assert envelope.share_percent is None
    assert envelope.share_percent_diag.illegible is False
