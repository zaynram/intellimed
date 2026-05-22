"""Cycle 9b-2 tests — prompt builder for legal handwritten intake (§8)."""

from __future__ import annotations


def test_build_intake_prompt_importable() -> None:
    """``build_intake_prompt`` is importable from the prompt module."""
    from trust_generator.v3.extraction.prompt import build_intake_prompt

    assert callable(build_intake_prompt)


def test_build_intake_prompt_returns_str() -> None:
    """``build_intake_prompt()`` returns a non-empty string."""
    from trust_generator.v3.extraction.prompt import build_intake_prompt

    result = build_intake_prompt()
    assert isinstance(result, str)
    assert result.strip() != ""


def test_prompt_contains_verbatim_pillar() -> None:
    """§8.1 pillar 1 — verbatim transcription discipline.

    The prompt MUST instruct the model to transcribe verbatim, not
    normalize. We assert presence of the term ``verbatim`` and a
    no-normalization phrase.
    """
    from trust_generator.v3.extraction.prompt import build_intake_prompt

    prompt = build_intake_prompt().lower()
    assert "verbatim" in prompt
    assert "do not normalize" in prompt or "do not reformat" in prompt


def test_prompt_contains_illegibility_pillar() -> None:
    """§8.1 pillar 2 — illegibility-as-first-class outcome.

    The prompt MUST frame illegibility flagging as preferred over
    guessing, and reference the ``illegible`` channel by name.
    """
    from trust_generator.v3.extraction.prompt import build_intake_prompt

    prompt = build_intake_prompt().lower()
    assert "illegible" in prompt
    assert "preferred over guessing" in prompt or "preferred over a guess" in prompt or "rather than guessing" in prompt


def test_prompt_contains_reasoning_aloud_pillar() -> None:
    """§8.1 pillar 3 — reasoning-aloud first.

    The prompt MUST instruct the model to use the ``reasoning`` field
    first, before committing to data fields.
    """
    from trust_generator.v3.extraction.prompt import build_intake_prompt

    prompt = build_intake_prompt().lower()
    assert "reasoning" in prompt
    assert "first" in prompt or "before" in prompt


def test_prompt_contains_domain_orientation() -> None:
    """§8.2 — domain orientation: legal trust intake.

    The prompt MUST identify the document type (legal trust intake)
    and reference at least one structural section (grantors,
    beneficiaries, real property, personal property, fiduciaries).
    """
    from trust_generator.v3.extraction.prompt import build_intake_prompt

    prompt = build_intake_prompt().lower()
    assert "trust" in prompt
    assert "intake" in prompt or "intake form" in prompt
    sections = ("grantor", "beneficiar", "real property", "personal property", "fiduciar")
    assert any(s in prompt for s in sections)


def test_prompt_contains_omit_if_absent_guardrail() -> None:
    """§8.3 guardrail 1 — omit-if-absent."""
    from trust_generator.v3.extraction.prompt import build_intake_prompt

    prompt = build_intake_prompt().lower()
    assert "omit" in prompt
    assert "do not invent" in prompt or "do not fabricate" in prompt or "do not guess" in prompt


def test_prompt_contains_partial_filling_guardrail() -> None:
    """§8.3 guardrail 2 — partial-filling: do not complete partial entries."""
    from trust_generator.v3.extraction.prompt import build_intake_prompt

    prompt = build_intake_prompt().lower()
    assert "do not complete" in prompt or "do not fill in" in prompt


def test_prompt_contains_multiple_readings_guardrail() -> None:
    """§8.3 guardrail 3 — multiple-readings note channel.

    The prompt MUST instruct the model to use the ``note`` channel
    for ambiguity when multiple readings are plausible.
    """
    from trust_generator.v3.extraction.prompt import build_intake_prompt

    prompt = build_intake_prompt().lower()
    assert "note" in prompt
    assert "ambiguity" in prompt or "ambiguous" in prompt or "multiple readings" in prompt


def test_prompt_length_under_cap() -> None:
    """Spec §8 closing — verbose prompts are noisy under constrained decoding.

    The cap (2000 characters) is a structural soft-warn against verbosity
    creep; the cap is documented in spec §8 and tested here.
    """
    from trust_generator.v3.extraction.prompt import build_intake_prompt

    assert len(build_intake_prompt()) <= 2000
