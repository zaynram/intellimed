"""Shared legal-handwriting prompt coordinator.

Hosts the back-compat re-export of ``build_intake_prompt`` so that
``ollama_backend.py``'s existing import path
(``from trust_generator.v3.extraction.prompt import build_intake_prompt``)
keeps working unchanged. The Ollama-side prompt body now lives in
``prompt_ollama.py``; the Anthropic-side body lives in
``prompt_anthropic.py``.

Pure shared-constants extraction (e.g., a single ``_DOMAIN_CONTEXT``
constant referenced by both backend assemblers) is a future refactor —
deferred because both prompt strings are short enough that DRY-driven
extraction would obscure them. Revisit if a third backend lands.
"""

from __future__ import annotations

from trust_generator.v3.extraction.prompt_ollama import build_intake_prompt

__all__ = ("build_intake_prompt",)
