"""Tests for the input parser layer (docx, JSON, registry)."""

from __future__ import annotations

from pathlib import Path

import pytest

from trust_generator.parsers import parse_docx, parse_file, parse_json
from trust_generator.schema import (
    BeneficiaryShare,
    Child,
    Elections,
    PersonInfo,
    SuccessorTrustee,
    TrustData,
    TrustIdentity,
    TrustType,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ASSETS_DIR = Path(__file__).resolve().parents[1] / "assets"
QUESTIONNAIRE_PATH = ASSETS_DIR / "Trust_Intake_Questionnaire.docx"


@pytest.fixture()
def sample_trust_data() -> TrustData:
    """A TrustData with representative content for round-trip testing."""
    return TrustData(
        party_a=PersonInfo(full_legal_name="John Andrew Doe", ssn="123-45-6789"),
        party_b=PersonInfo(full_legal_name="Jane Susan Doe", maiden_name="Smith"),
        trust_id=TrustIdentity(
            desired_trust_name="The Doe Family Trust",
            state_of_governing_law="Illinois",
            county_of_execution="Winnebago",
        ),
        children=[
            Child(name="Alice Doe", dob="01/15/2000", relationship="Daughter"),
            Child(name="Bob Doe", dob="03/22/2002", relationship="Son"),
        ],
        successor_trustees=[
            SuccessorTrustee(order="1", name="Alice Doe", relationship="Daughter"),
        ],
        beneficiary_shares=[
            BeneficiaryShare(name="Alice Doe", share="50"),
            BeneficiaryShare(name="Bob Doe", share="50"),
        ],
        elections=Elections(spendthrift=False),
    )


# ---------------------------------------------------------------------------
# JSON round-trip
# ---------------------------------------------------------------------------


def test_json_round_trip(sample_trust_data: TrustData, tmp_path: Path) -> None:
    """Create a TrustData, dump to JSON, parse back, verify equality."""
    json_file = tmp_path / "intake.json"
    json_file.write_text(sample_trust_data.model_dump_json(indent=2), encoding="utf-8")

    restored = parse_json(json_file)

    assert restored.party_a.full_legal_name == "John Andrew Doe"
    assert restored.party_a.ssn == "123-45-6789"
    assert restored.party_b.maiden_name == "Smith"
    assert restored.trust_id.desired_trust_name == "The Doe Family Trust"
    assert len(restored.children) == 2
    assert restored.children[0].name == "Alice Doe"
    assert len(restored.beneficiary_shares) == 2
    assert restored.elections.spendthrift is False
    # Full model equality
    assert restored == sample_trust_data


# ---------------------------------------------------------------------------
# Registry dispatch
# ---------------------------------------------------------------------------


def test_parse_file_dispatches_json(
    sample_trust_data: TrustData, tmp_path: Path
) -> None:
    """parse_file should route .json files to the JSON parser."""
    json_file = tmp_path / "intake.json"
    json_file.write_text(sample_trust_data.model_dump_json(), encoding="utf-8")

    result = parse_file(json_file)
    assert isinstance(result, TrustData)
    assert result.party_a.full_legal_name == "John Andrew Doe"


@pytest.mark.skipif(
    not QUESTIONNAIRE_PATH.exists(),
    reason="Trust_Intake_Questionnaire.docx not found in assets/",
)
def test_parse_file_dispatches_docx() -> None:
    """parse_file should route .docx files to the docx parser."""
    result = parse_file(QUESTIONNAIRE_PATH)
    assert isinstance(result, TrustData)


def test_parse_file_raises_for_unsupported_extension(tmp_path: Path) -> None:
    """parse_file should raise ValueError for unknown extensions."""
    bad_file = tmp_path / "intake.xlsx"
    bad_file.write_text("dummy")
    with pytest.raises(ValueError, match="Unsupported file format"):
        parse_file(bad_file)


def test_parse_file_raises_for_missing_file(tmp_path: Path) -> None:
    """parse_file should raise FileNotFoundError for missing files."""
    with pytest.raises(FileNotFoundError):
        parse_file(tmp_path / "nonexistent.json")


# ---------------------------------------------------------------------------
# Docx parser — blank template
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not QUESTIONNAIRE_PATH.exists(),
    reason="Trust_Intake_Questionnaire.docx not found in assets/",
)
def test_docx_parser_blank_template() -> None:
    """Parsing the blank questionnaire template should not crash.

    It should return a TrustData with mostly empty/default values.
    """
    result = parse_docx(QUESTIONNAIRE_PATH)
    assert isinstance(result, TrustData)
    # Config-derived defaults (state/county) are NOT applied during parsing — only during validation
    assert result.trust_id.state_of_governing_law != "Illinois"
    # Election enum defaults from schema are present
    assert result.elections.initial_trustee.value == "both"
    assert result.elections.spendthrift is True


# ---------------------------------------------------------------------------
# JSON parser — error handling
# ---------------------------------------------------------------------------


def test_json_parser_invalid_json(tmp_path: Path) -> None:
    """parse_json should raise ValueError for invalid JSON."""
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON validation failed"):
        parse_json(bad_file)


def test_json_parser_missing_file(tmp_path: Path) -> None:
    """parse_json should raise FileNotFoundError for missing files."""
    with pytest.raises(FileNotFoundError):
        parse_json(tmp_path / "nonexistent.json")


def test_json_parser_empty_object(tmp_path: Path) -> None:
    """An empty JSON object should produce a TrustData with defaults."""
    json_file = tmp_path / "empty.json"
    json_file.write_text("{}", encoding="utf-8")
    result = parse_json(json_file)
    assert isinstance(result, TrustData)
    assert result.elections.initial_trustee.value == "both"


# ---------------------------------------------------------------------------
# Individual trust type detection
# ---------------------------------------------------------------------------


def test_json_round_trip_individual(tmp_path: Path) -> None:
    """Individual trust type should survive JSON round-trip."""
    data = TrustData(
        trust_type=TrustType.INDIVIDUAL,
        grantor=PersonInfo(full_legal_name="Robert Wilson"),
    )
    json_file = tmp_path / "individual.json"
    json_file.write_text(data.model_dump_json(indent=2), encoding="utf-8")

    restored = parse_json(json_file)
    assert restored.trust_type == TrustType.INDIVIDUAL
    assert restored.grantor.full_legal_name == "Robert Wilson"


def test_json_default_trust_type_is_joint(tmp_path: Path) -> None:
    """JSON without trust_type field should default to JOINT (backward compat)."""
    json_file = tmp_path / "legacy.json"
    json_file.write_text(
        '{"husband": {"full_legal_name": "John Smith"}}', encoding="utf-8"
    )

    restored = parse_json(json_file)
    assert restored.trust_type == TrustType.JOINT


def test_docx_parser_detects_individual_trust() -> None:
    """When husband is filled but wife is empty, docx parser should detect individual trust."""
    from trust_generator.parsers.docx_parser import _flat_to_trust_data

    flat = {"husband.full_legal_name": "Robert Wilson"}
    result = _flat_to_trust_data(
        flat,
        children=[],
        successor_trustees=[],
        real_property=[],
        financial_accounts=[],
        vehicles=[],
        insurance_policies=[],
        pensions=[],
        valuables=[],
        beneficiary_shares=[],
        specific_bequests=[],
        withdrawal_schedule=[],
        other_beneficiaries=[],
        checkbox_data={},
        text_blocks={},
    )
    assert result.trust_type == TrustType.INDIVIDUAL
    assert result.grantor.full_legal_name == "Robert Wilson"
