"""Schema-generation tests for firm_config (spec §10.2)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import jsonschema
import pytest

from trust_generator.v3.config import FirmConfig
from trust_generator.v3.config.firm import (
    Diagnostics,
    Drafts,
    EstateThresholds,
    FirmIdentity,
    Guardianship,
    Jurisdiction,
    Meta,
    TrusteeCatalog,
    User,
)
from trust_generator.v3.config.schema_gen import TombiAwareGenerator
from trust_generator.v3.schema import Address

REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = REPO_ROOT / "config" / "firm-config.schema.json"
GENERATOR_SCRIPT = REPO_ROOT / "scripts" / "generate_firm_config_schema.py"


def _load_generator_main():
    spec = importlib.util.spec_from_file_location(
        "generate_firm_config_schema", GENERATOR_SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _emit_schema() -> dict:
    return FirmConfig.model_json_schema(schema_generator=TombiAwareGenerator)


def _canonical_firm_config() -> FirmConfig:
    return FirmConfig(
        meta=Meta(),
        user=User(upn="canonuser"),
        firm=FirmIdentity(
            name="Canon LLP",
            phone="(555) 555-5555",
            office_address=Address(
                street="1 Main",
                city="Rockford",
                state="IL",
                zip_code="61114",
            ),
        ),
        jurisdiction=Jurisdiction(),
        estate_thresholds=EstateThresholds(),
        trustee_catalog=TrusteeCatalog(),
        diagnostics=Diagnostics(),
        guardianship=Guardianship(),
        drafts=Drafts(),
    )


def test_generator_runs_without_error() -> None:
    schema = _emit_schema()
    assert isinstance(schema, dict)


def test_schema_declares_draft_2020_12_dialect() -> None:
    schema = _emit_schema()
    assert schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema"


def test_root_carries_tombi_extensions() -> None:
    schema = _emit_schema()
    assert schema.get("x-tombi-toml-version") == "1.0.0"
    assert "x-tombi-table-keys-order" in schema
    order = schema["x-tombi-table-keys-order"]
    assert order == [
        "meta",
        "user",
        "firm",
        "jurisdiction",
        "estate_thresholds",
        "trustee_catalog",
        "diagnostics",
        "guardianship",
        "drafts",
    ]
    assert "x-tombi-string-formats" in schema
    assert "uri" in schema["x-tombi-string-formats"]


def test_top_level_properties_match_firm_config_fields() -> None:
    schema = _emit_schema()
    properties = set(schema.get("properties", {}).keys())
    expected = set(FirmConfig.model_fields.keys())
    assert properties == expected
    assert "meta" in properties


def test_lat_lon_emit_number_not_decimal_string() -> None:
    schema = _emit_schema()
    address_schema = _address_subschema(schema)
    for key in ("latitude", "longitude"):
        sub = address_schema["properties"][key]
        types = _collect_types(sub)
        assert "number" in types
        assert "string" not in types


def test_approaching_cliff_ratio_emits_bounded_number() -> None:
    schema = _emit_schema()
    sub = _resolve_ref(schema, schema["properties"]["estate_thresholds"])
    ratio = sub["properties"]["approaching_cliff_ratio"]
    assert ratio["type"] == "number"
    assert ratio.get("exclusiveMinimum") == 0
    assert ratio.get("exclusiveMaximum") == 1


def test_fdic_api_base_emits_uri_format() -> None:
    schema = _emit_schema()
    sub = _resolve_ref(schema, schema["properties"]["trustee_catalog"])
    fdic = sub["properties"]["fdic_api_base"]
    assert fdic.get("format") == "uri"


def test_meta_subschema_is_permissive() -> None:
    schema = _emit_schema()
    sub = _resolve_ref(schema, schema["properties"]["meta"])
    additional = sub.get("additionalProperties", True)
    assert additional is True or additional == {}


def test_on_disk_schema_matches_generator_byte_equal() -> None:
    # sort_keys=True handles within-run determinism, but upgrading Pydantic or
    # pydantic-settings can shift the shape of $defs (new format keys,
    # rearranged anyOf branches for nullable types). When that happens this
    # test fires as the drift detector; the remediation is always the same —
    # regenerate and re-commit.
    assert SCHEMA_PATH.is_file(), (
        f"Expected checked-in schema at {SCHEMA_PATH}. "
        f"Run: pixi run python scripts/generate_firm_config_schema.py"
    )
    expected = (
        json.dumps(_emit_schema(), indent=2, sort_keys=True, ensure_ascii=False)
        + "\n"
    )
    actual = SCHEMA_PATH.read_text(encoding="utf-8")
    assert actual == expected, (
        "Schema drift detected. Regenerate via "
        "`pixi run python scripts/generate_firm_config_schema.py`."
    )


def test_canonical_round_trip_against_generated_schema(tmp_path: Path) -> None:
    import tomllib

    cfg = _canonical_firm_config()
    # exclude_none=True drops unset optional fields (lat/lon, meta.schema_version,
    # meta.comment) — TOML has no null literal and the JSON Schema marks these
    # as number|null / string|null. Dropping them is the canonical round-trip.
    payload = cfg.model_dump(mode="json", exclude_none=True)
    toml_body = _to_toml(payload)
    path = tmp_path / "canonical.toml"
    path.write_text(toml_body, encoding="utf-8")
    with path.open("rb") as handle:
        loaded = tomllib.load(handle)
    schema = _emit_schema()
    jsonschema.validate(loaded, schema)


def test_generator_script_writes_schema(tmp_path: Path) -> None:
    # The script anchors its default output path via __file__ so it always
    # writes to <repo>/config/firm-config.schema.json regardless of CWD. The
    # main() function accepts an output_path kwarg to let tests target a
    # tmp directory without mutating the checked-in artifact.
    module = _load_generator_main()
    target = tmp_path / "config" / "firm-config.schema.json"
    rc = module.main(output_path=target)
    assert rc == 0
    produced = target.read_text(encoding="utf-8")
    assert produced.endswith("\n")
    expected = (
        json.dumps(_emit_schema(), indent=2, sort_keys=True, ensure_ascii=False)
        + "\n"
    )
    assert produced == expected


def _resolve_ref(root: dict, node: dict) -> dict:
    if "$ref" in node:
        ref = node["$ref"]
        assert ref.startswith("#/"), ref
        target: dict = root
        for segment in ref.removeprefix("#/").split("/"):
            target = target[segment]
        return target
    return node


def _address_subschema(schema: dict) -> dict:
    firm = _resolve_ref(schema, schema["properties"]["firm"])
    return _resolve_ref(schema, firm["properties"]["office_address"])


def _collect_types(node: dict) -> set[str]:
    """Accept either ``type: "x"`` or ``anyOf: [{"type": "x"}, {"type": "null"}]``."""
    types: set[str] = set()
    if "type" in node:
        value = node["type"]
        if isinstance(value, list):
            types.update(value)
        else:
            types.add(value)
    for branch_key in ("anyOf", "oneOf"):
        for branch in node.get(branch_key, []):
            types.update(_collect_types(branch))
    return types


def _to_toml(payload: dict) -> str:
    """Round-trip a ``FirmConfig.model_dump()`` payload into TOML text.

    Minimal encoder; only handles the shapes FirmConfig emits (scalars, nested
    tables, strings, bools, ints, floats, lists of scalars). Not a general TOML
    writer — exists only for the round-trip test.
    """

    import re

    def _encode_scalar(value: object) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return repr(value)
        if value is None:
            # TOML has no null literal. Callers pass exclude_none=True upstream;
            # if a None slips through, raise loudly rather than silently mis-encode
            # as empty string.
            raise ValueError(
                "cannot encode None in TOML; use exclude_none=True upstream"
            )
        text = str(value)
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'

    def _emit_table(header: str, data: dict) -> list[str]:
        lines = [f"[{header}]"] if header else []
        tail: list[str] = []
        for key, value in data.items():
            if isinstance(value, dict):
                nested_header = f"{header}.{key}" if header else key
                tail.extend(_emit_table(nested_header, value))
            else:
                lines.append(f"{key} = {_encode_scalar(value)}")
        lines.append("")
        return lines + tail

    top_scalars = {k: v for k, v in payload.items() if not isinstance(v, dict)}
    tables = {k: v for k, v in payload.items() if isinstance(v, dict)}

    output: list[str] = []
    if top_scalars:
        output.extend(_emit_table("", top_scalars))
    for key, value in tables.items():
        output.extend(_emit_table(key, value))

    rendered = "\n".join(output)
    rendered = re.sub(r"\n{3,}", "\n\n", rendered)
    return rendered
