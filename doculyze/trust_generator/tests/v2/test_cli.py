"""Tests for the CLI interface."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from trust_generator.v2.ui.cli import run_cli


def _complete_data_json() -> str:
    """Return a JSON string for a complete TrustData that passes validation."""
    return json.dumps(
        {
            "husband": {"full_legal_name": "John Andrew Smith"},
            "wife": {"full_legal_name": "Jane Marie Smith"},
            "children": [
                {"name": "Alice Smith", "dob": "01/15/2000", "relationship": "Daughter"}
            ],
            "successor_trustees": [
                {"order": "1", "name": "Alice Smith", "relationship": "Daughter"}
            ],
            "beneficiary_shares": [{"name": "Alice Smith", "share": "100"}],
            "real_property": [{"address": "123 Main St"}],
        },
        indent=2,
    )


def _empty_data_json() -> str:
    """Return a JSON string for TrustData with empty grantor names."""
    return json.dumps(
        {
            "husband": {"full_legal_name": ""},
            "wife": {"full_legal_name": ""},
        },
        indent=2,
    )


def test_parse_json_to_stdout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Parse a JSON file and verify valid JSON on stdout."""
    infile = tmp_path / "intake.json"
    infile.write_text(_complete_data_json(), encoding="utf-8")

    run_cli(["parse", "-i", str(infile), "--format", "json"])

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["party_a"]["full_legal_name"] == "John Andrew Smith"
    assert data["party_b"]["full_legal_name"] == "Jane Marie Smith"


def test_validate_empty_data_exits_1(tmp_path: Path) -> None:
    """Validation of empty grantor names should exit with code 1."""
    infile = tmp_path / "empty.json"
    infile.write_text(_empty_data_json(), encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        run_cli(["validate", "-i", str(infile)])

    assert exc_info.value.code == 1


def test_validate_complete_data_exits_0(tmp_path: Path) -> None:
    """Validation of complete data should exit cleanly (no SystemExit)."""
    infile = tmp_path / "complete.json"
    infile.write_text(_complete_data_json(), encoding="utf-8")

    # Should not raise SystemExit
    run_cli(["validate", "-i", str(infile)])


def test_generate_with_force(tmp_path: Path) -> None:
    """Generate with --force and a complete JSON produces an output file."""
    infile = tmp_path / "intake.json"
    infile.write_text(_complete_data_json(), encoding="utf-8")

    outfile = tmp_path / "output.docx"

    run_cli(["generate", "-i", str(infile), "-o", str(outfile), "--force"])

    assert outfile.exists()
    assert outfile.stat().st_size > 0


def test_generate_no_input_exits_error() -> None:
    """Running 'generate' without -i should exit with an error."""
    with pytest.raises(SystemExit) as exc_info:
        run_cli(["generate"])

    assert exc_info.value.code != 0


def test_unknown_subcommand_exits_error() -> None:
    """Running with an unknown subcommand should exit with an error."""
    with pytest.raises(SystemExit) as exc_info:
        run_cli(["nonexistent"])

    assert exc_info.value.code != 0


def test_create_fillable_pdf(tmp_path: Path) -> None:
    """create-fillable-pdf should produce a PDF file."""
    try:
        import reportlab
    except ImportError:
        pytest.skip("reportlab not installed")

    out = tmp_path / "fillable.pdf"
    run_cli(["create-fillable-pdf", "-o", str(out)])
    assert out.exists()
    assert out.stat().st_size > 1000
