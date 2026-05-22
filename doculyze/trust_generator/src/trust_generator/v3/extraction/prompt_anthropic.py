"""Anthropic-side intake prompt assembly.

Backend-specific differentiation from ``prompt_ollama``:
- No reasoning-aloud directive (extended thinking carries that channel
  out-of-band; the AnthropicGenerationEnvelope has no ``reasoning``
  field).
- Acknowledges PDF intake (Anthropic's ``document`` content block
  accepts PDFs natively).
- Retains §8.1 verbatim-transcription / illegibility-as-first-class
  discipline and §8.3 anti-hallucination guardrails.

Spec §4 *Prompt module split rationale*; §4 *Single-fragment prompt
strategy* — this builder returns a single string consumed as the
cacheable system prompt; the user message carries only the document /
image content block.
"""

from __future__ import annotations

_INTAKE_PROMPT = """\
You are a careful legal-intake transcriber. The attached document — which may be a multi-page PDF or a single image — is a handwritten trust intake form. Extract its field values into the structured output schema provided alongside this request.

Reading discipline:
1. Verbatim transcription. Transcribe what is written, not what the writer "meant." Do not normalize names, dates, currency, suffixes, or punctuation. Do not reformat. If the form says "James William Thompson, Jr." emit that exact string; do not rewrite to "James W. Thompson Jr."
2. Illegibility is first-class. If you cannot read a field with confidence, set the matching illegible flag to true on that field. Marking a field illegible is preferred over guessing.

Domain context: the document is a legal trust intake form. Expected sections include grantors, beneficiaries, real property, personal property, and fiduciaries.

Anti-hallucination guardrails:
- If a field is not present on the form at all, omit it from the output. Do not invent a default value.
- If a field is partially filled, transcribe what is there. Do not complete it.
- If multiple readings are plausible, pick the most likely transcription. Set the matching illegible flag on the field rather than presenting a confident transcription you do not actually hold.
"""


def build_intake_prompt() -> str:
    """Return the Anthropic-side OCR extraction prompt.

    Used as the cacheable system prompt (spec §8.2 breakpoint 1).
    The ``prompt_builder`` constructor seam on ``AnthropicBackend``
    defaults to this function; passing a custom builder is supported
    for future firm-customized variants.
    """
    return _INTAKE_PROMPT
