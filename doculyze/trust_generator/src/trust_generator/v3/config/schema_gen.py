"""JSON Schema generator with tombi-aware root extensions.

Subclasses ``pydantic.json_schema.GenerateJsonSchema`` so the root schema
carries ``x-tombi-*`` vendor extensions required by the tombi LSP for accurate
edit-time validation of ``config/firm.toml``. Per-field tombi extensions (when
any are needed) live on the Pydantic fields themselves via
``Field(json_schema_extra=...)`` so schema concerns stay colocated with field
definitions.
"""

from __future__ import annotations

from typing import Any

from pydantic.json_schema import GenerateJsonSchema, JsonSchemaMode, JsonSchemaValue

TOMBI_TABLE_KEYS_ORDER: tuple[str, ...] = (
    "meta",
    "user",
    "firm",
    "jurisdiction",
    "estate_thresholds",
    "trustee_catalog",
    "diagnostics",
    "guardianship",
    "drafts",
)


class TombiAwareGenerator(GenerateJsonSchema):
    """Emit JSON Schema draft-2020-12 with tombi root extensions."""

    def generate(
        self, schema: Any, mode: JsonSchemaMode = "validation"
    ) -> JsonSchemaValue:
        result = super().generate(schema, mode=mode)
        # Pydantic tracks schema_dialect internally but doesn't emit it — add
        # it so tombi (and any other dialect-aware validator) sees the
        # declaration explicitly.
        result["$schema"] = self.schema_dialect
        result["x-tombi-toml-version"] = "1.0.0"
        result["x-tombi-table-keys-order"] = list(TOMBI_TABLE_KEYS_ORDER)
        result["x-tombi-string-formats"] = ["uri"]
        return result
