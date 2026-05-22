"""Extension-based dispatch for v3 parser (§6.10).

Routes an input file to the appropriate parser by inspecting the file's
suffix. Provides the unified `parse_file` entry point declared in §5.2.

Dispatch table:
    .json  → parse_json(filepath)                       — seed_initialized ignored
    .docx  → parse_docx(filepath, seed_initialized)     — seed_initialized required
    .pdf   → parse_pdf(filepath, seed_initialized)      — seed_initialized required

Any other extension raises ValueError.
"""

from __future__ import annotations

from pathlib import Path

from trust_generator.v3.parsers.docx_parser import parse_docx
from trust_generator.v3.parsers.json_parser import parse_json
from trust_generator.v3.parsers.pdf_parser import parse_pdf
from trust_generator.v3.schema import TrustData

_SUPPORTED_EXTENSIONS = {".json", ".docx", ".pdf"}


def parse_file(
    filepath: Path,
    seed_initialized: TrustData | None = None,
) -> TrustData:
    """Dispatch to the appropriate parser by file extension.

    Args:
        filepath: Path to the input file (.json, .docx, or .pdf).
        seed_initialized: A `TrustData` instance produced by `promote_seed`.
            Required for `.docx` and `.pdf` inputs (used as the merge
            baseline per spec §5.3 step 1).  Ignored silently for `.json`
            inputs — JSON files carry a complete `TrustData` serialisation
            and are self-sufficient (M2 contract, spec §6.10 plan-review
            pass 1).

    Returns:
        A validated `TrustData` instance populated from the input file.

    Raises:
        ValueError: Extension is not one of {.json, .docx, .pdf}.
        ValueError: Extension is .docx or .pdf and seed_initialized is None.
        FileNotFoundError: The file does not exist (propagated from the
            delegated parser).
    """
    suffix = Path(filepath).suffix.lower()

    if suffix == ".json":
        # seed_initialized is intentionally ignored — JSON is self-sufficient.
        return parse_json(filepath)

    if suffix in {".docx", ".pdf"}:
        if seed_initialized is None:
            raise ValueError(
                f"seed_initialized is required for {suffix} parsing but was not "
                f"provided. Call promote_seed(QuestionnaireSeed(...)) first."
            )
        if suffix == ".docx":
            return parse_docx(filepath, seed_initialized)
        return parse_pdf(filepath, seed_initialized)

    raise ValueError(
        f"Unsupported file extension: '{suffix}'. "
        f"Supported extensions are: {sorted(_SUPPORTED_EXTENSIONS)}"
    )
