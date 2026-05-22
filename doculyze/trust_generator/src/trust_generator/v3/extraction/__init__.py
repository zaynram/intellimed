"""OCR extraction surface — markers, trace, Protocol, and helpers.

Public surface declared in ``__all__``; the ``INCOMPLETE`` sentinel is
intentionally NOT exported (per spec §5.3 — consumers import it
explicitly to make the in-memory-identity discipline visible).
"""

from __future__ import annotations

from trust_generator.v3.extraction.anthropic_backend import AnthropicBackend
from trust_generator.v3.extraction.markers import (
    IncompleteUntilValidated,
    RawSelfReport,
)
from trust_generator.v3.extraction.ollama_backend import OllamaBackend
from trust_generator.v3.extraction.paths import resolve
from trust_generator.v3.extraction.protocol import (
    ExtractionError,
    ExtractionProtocol,
    SourceRef,
)
from trust_generator.v3.extraction.synthesis import synthesize_extraction_diagnostics
from trust_generator.v3.extraction.trace import (
    ExtractionResult,
    ExtractionTrace,
    FieldExtraction,
)

__all__ = (
    "AnthropicBackend",
    "ExtractionError",
    "ExtractionProtocol",
    "ExtractionResult",
    "ExtractionTrace",
    "FieldExtraction",
    "IncompleteUntilValidated",
    "OllamaBackend",
    "RawSelfReport",
    "SourceRef",
    "resolve",
    "synthesize_extraction_diagnostics",
)
