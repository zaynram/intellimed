"""Tests for the v3 PDF parser (§6.9).

Tier 2 (synthetic): constructs PDF fixtures via reportlab in tmp_path.
All tests are gated on pypdf + reportlab availability.
Import path: from trust_generator.v3.parsers.pdf_parser import parse_pdf
(parse_pdf is not re-exported from __init__ until the 'registry' plan executes).
"""
from __future__ import annotations

import pytest

pypdf = pytest.importorskip("pypdf")
reportlab = pytest.importorskip("reportlab")

from io import BytesIO
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

from trust_generator.v3.schema import (
    MaritalStatus,
    QuestionnaireSeed,
    TrustType,
    promote_seed,
)

# ---------------------------------------------------------------------------
# §5.4.A field-presence normalization — three required pin tests + whitespace
# ---------------------------------------------------------------------------

class TestFieldPresenceNormalization:
    """§5.4.A: absent / present-None / present-empty all normalize to None."""

    def test_pdf_field_absent_is_None_at_coercion(self, tmp_path):
        """A field not present in get_fields() dict is treated as None."""
        from trust_generator.v3.parsers.pdf_parser import _normalize_field_values

        # Simulate get_fields() returning a dict without the key.
        fields: dict = {}  # 'grantor.full_legal_name' absent
        normalized = _normalize_field_values(fields)
        assert "grantor.full_legal_name" not in normalized

    def test_pdf_field_present_None_is_None_at_coercion(self, tmp_path):
        """A field present in get_fields() with value None normalizes to None."""
        from trust_generator.v3.parsers.pdf_parser import _normalize_field_values

        # Simulate a Field object whose .value is None.
        class _MockField:
            value = None

        fields = {"grantor.full_legal_name": _MockField()}
        normalized = _normalize_field_values(fields)
        assert normalized.get("grantor.full_legal_name") is None

    def test_pdf_field_present_empty_is_None_at_coercion(self, tmp_path):
        """A field present in get_fields() with value '' normalizes to None."""
        from trust_generator.v3.parsers.pdf_parser import _normalize_field_values

        class _MockField:
            value = ""

        fields = {"grantor.full_legal_name": _MockField()}
        normalized = _normalize_field_values(fields)
        assert normalized.get("grantor.full_legal_name") is None

    def test_pdf_field_whitespace_only_is_None_at_coercion(self, tmp_path):
        """A field with a whitespace-only string normalizes to None after .strip()."""
        from trust_generator.v3.parsers.pdf_parser import _normalize_field_values

        class _MockField:
            value = "   "

        fields = {"grantor.full_legal_name": _MockField()}
        normalized = _normalize_field_values(fields)
        assert normalized.get("grantor.full_legal_name") is None


# ---------------------------------------------------------------------------
# Smoke test — parser exists, opens a minimal PDF, returns TrustData
# ---------------------------------------------------------------------------

class TestParsePdfSmoke:
    """Cycle 7 parallel to cycle 4a (docx smoke). Parser-existence signal only."""

    def test_parse_pdf_smoke(self, tmp_path):
        """parse_pdf exists, opens a blank-field PDF, returns a TrustData.

        Also asserts P3 invariant: seed_initialized is field-level equal
        before and after the call.
        """
        from trust_generator.v3.parsers.pdf_parser import parse_pdf

        seed = QuestionnaireSeed(
            trust_type=TrustType.JOINT,
            marital_status=MaritalStatus.MARRIED,
        )
        seed_initialized = promote_seed(seed)
        seed_snapshot = seed_initialized.model_copy(deep=True)

        # Build a minimal PDF with no meaningful content.
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        pdf_path = tmp_path / "blank.pdf"
        with open(pdf_path, "wb") as f:
            writer.write(f)

        result = parse_pdf(pdf_path, seed_initialized)

        assert result is not None
        # P3: seed_initialized must be field-level equal before and after.
        assert seed_initialized == seed_snapshot
        # Deepcopy proof: returned instance is distinct.
        assert result is not seed_initialized

    def test_parse_pdf_preserves_seed_trust_type(self, tmp_path):
        """When no trust_type field is present in the PDF, seed trust_type persists."""
        from trust_generator.v3.parsers.pdf_parser import parse_pdf

        seed = QuestionnaireSeed(
            trust_type=TrustType.INDIVIDUAL,
            marital_status=MaritalStatus.UNMARRIED,
        )
        seed_initialized = promote_seed(seed)

        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        pdf_path = tmp_path / "no_trust_type.pdf"
        with open(pdf_path, "wb") as f:
            writer.write(f)

        result = parse_pdf(pdf_path, seed_initialized)
        assert result.trust_id.trust_type == TrustType.INDIVIDUAL


# ---------------------------------------------------------------------------
# Error surfaces
# ---------------------------------------------------------------------------

class TestParsePdfErrors:
    """Hard-fail surface per §5.5."""

    def test_parse_pdf_raises_for_missing_file(self, tmp_path):
        """FileNotFoundError raised when the path does not exist."""
        from trust_generator.v3.parsers.pdf_parser import parse_pdf

        seed_initialized = promote_seed(
            QuestionnaireSeed(trust_type=TrustType.JOINT, marital_status=MaritalStatus.MARRIED)
        )
        with pytest.raises(FileNotFoundError):
            parse_pdf(tmp_path / "nonexistent.pdf", seed_initialized)


# ---------------------------------------------------------------------------
# Fill-and-reparse pattern (parallel to v2 tests/v2/test_pdf_parser.py)
# ---------------------------------------------------------------------------

class TestParsePdfFillAndReparse:
    """AcroForm round-trip: fill fields → write PDF → parse → assert TrustData."""

    def _write_acroform_pdf(self, tmp_path: Path, fields: dict[str, str]) -> Path:
        """Build a PDF with AcroForm text fields set to the given values.

        Uses reportlab's canvas.acroForm API to create real AcroForm text fields
        so that pypdf's PdfReader.get_fields() can read them back as Field objects
        with a .value property. PdfWriter.update_page_form_field_values is not used
        here because it requires a pre-existing /AcroForm dictionary.
        """
        from reportlab.lib.pagesizes import letter

        out = tmp_path / "filled.pdf"
        c = canvas.Canvas(str(out), pagesize=letter)
        form = c.acroForm
        y = 750
        for name, value in fields.items():
            form.textfield(
                name=name,
                tooltip=name,
                value=value,
                x=50,
                y=y,
                width=400,
                height=20,
                fontSize=10,
                borderWidth=0,
            )
            y -= 30
        c.showPage()
        c.save()
        return out

    def test_grantor_name_round_trips(self, tmp_path):
        """'grantor.full_legal_name' field value is reflected in result.grantor."""
        from trust_generator.v3.parsers.pdf_parser import parse_pdf

        pdf_path = self._write_acroform_pdf(
            tmp_path, {"grantor.full_legal_name": "Alice Marie Doe"}
        )
        seed = QuestionnaireSeed(trust_type=TrustType.JOINT, marital_status=MaritalStatus.MARRIED)
        result = parse_pdf(pdf_path, promote_seed(seed))
        assert result.grantor.full_legal_name == "Alice Marie Doe"

    def test_trust_type_mutation_via_field(self, tmp_path):
        """A 'trust_id.trust_type' field value overrides the seed trust_type."""
        from trust_generator.v3.parsers.pdf_parser import parse_pdf

        pdf_path = self._write_acroform_pdf(
            tmp_path, {"trust_id.trust_type": "individual"}
        )
        seed = QuestionnaireSeed(trust_type=TrustType.JOINT, marital_status=MaritalStatus.MARRIED)
        result = parse_pdf(pdf_path, promote_seed(seed))
        # trust_type change → _apply_post_promotion_protocol fires
        assert result.trust_id.trust_type == TrustType.INDIVIDUAL

    def test_date_field_coercion(self, tmp_path):
        """A date field in MM/DD/YYYY format is coerced correctly."""
        from datetime import date

        from trust_generator.v3.parsers.pdf_parser import parse_pdf

        pdf_path = self._write_acroform_pdf(
            tmp_path, {"grantor.date_of_birth": "03/15/1975"}
        )
        seed = QuestionnaireSeed(trust_type=TrustType.INDIVIDUAL, marital_status=MaritalStatus.UNMARRIED)
        result = parse_pdf(pdf_path, promote_seed(seed))
        assert result.grantor.date_of_birth == date(1975, 3, 15)

    def test_malformed_date_falls_back_to_None(self, tmp_path, caplog):
        """A date field with unparseable text falls back to None; warning logged."""
        import logging

        from trust_generator.v3.parsers.pdf_parser import parse_pdf

        pdf_path = self._write_acroform_pdf(
            tmp_path, {"grantor.date_of_birth": "sometime in 1975"}
        )
        seed = QuestionnaireSeed(trust_type=TrustType.INDIVIDUAL, marital_status=MaritalStatus.UNMARRIED)
        with caplog.at_level(logging.WARNING, logger="trust_generator.v3.parsers.pdf_parser"):
            result = parse_pdf(pdf_path, promote_seed(seed))
        assert result.grantor.date_of_birth is None
        assert any("could not parse date" in r.message for r in caplog.records)

    def test_post_promotion_protocol_not_reinvoked(self, tmp_path):
        """parse_pdf does not call promote_seed under any branch (P1)."""
        from unittest.mock import patch

        from trust_generator.v3.parsers.pdf_parser import parse_pdf

        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        pdf_path = tmp_path / "blank.pdf"
        with open(pdf_path, "wb") as f:
            writer.write(f)

        seed_initialized = promote_seed(
            QuestionnaireSeed(trust_type=TrustType.JOINT, marital_status=MaritalStatus.MARRIED)
        )
        with patch("trust_generator.v3.parsers.pdf_parser.promote_seed", autospec=True) as m:
            parse_pdf(pdf_path, seed_initialized)
        assert m.call_count == 0

    def test_withdrawal_missing_age_logs_dropped_row(self, tmp_path, caplog):
        """C1 (PR #12 review): a withdrawal row with percent/description but
        no age is dropped per §5.4.7 — but the drop must be logged, mirroring
        the age-parse-failure branch. A silent drop loses paralegal-entered data.
        """
        import logging

        from trust_generator.v3.parsers.pdf_parser import parse_pdf

        pdf_path = self._write_acroform_pdf(
            tmp_path,
            {
                "withdrawal[0].percent": "25",
                "withdrawal[0].description": "first tranche",
            },
        )
        seed = QuestionnaireSeed(
            trust_type=TrustType.INDIVIDUAL, marital_status=MaritalStatus.UNMARRIED
        )
        with caplog.at_level(
            logging.WARNING, logger="trust_generator.v3.parsers.pdf_parser"
        ):
            parse_pdf(pdf_path, promote_seed(seed))
        assert any(
            "withdrawal[0]" in r.message and "age" in r.message
            for r in caplog.records
        )

    def test_withdrawal_missing_percent_logs_default(self, tmp_path, caplog):
        """C5-log (PR #12 review): a withdrawal row with a valid age but no
        percent defaults percent to Decimal(0). That substitution must be
        logged — a blank field silently becoming a meaningful 0% allocation
        is a wrong-but-valid-looking value. The row still survives (the age
        is valid); only the silent substitution is the defect.
        """
        import logging

        from trust_generator.v3.parsers.pdf_parser import parse_pdf

        pdf_path = self._write_acroform_pdf(
            tmp_path,
            {
                "withdrawal[0].age": "30",
                "withdrawal[0].description": "at thirty",
            },
        )
        seed = QuestionnaireSeed(
            trust_type=TrustType.INDIVIDUAL, marital_status=MaritalStatus.UNMARRIED
        )
        with caplog.at_level(
            logging.WARNING, logger="trust_generator.v3.parsers.pdf_parser"
        ):
            result = parse_pdf(pdf_path, promote_seed(seed))
        assert any(
            "withdrawal[0]" in r.message and "percent" in r.message
            for r in caplog.records
        )
        assert len(result.withdrawal_schedule) == 1
        assert result.withdrawal_schedule[0].age == 30

    def test_withdrawal_full_row_round_trips(self, tmp_path):
        """A fully-populated withdrawal row (age + percent + description)
        produces a WithdrawalStep with correctly coerced values.

        Pins the happy path of the §6.9 / §5.4.7 withdrawal loop, which was
        restructured under PR #12 review fix C1 — the prior test suite
        covered only the degraded branches (missing age, missing percent),
        leaving the valid-row path unverified against a branch-ordering
        regression.
        """
        from decimal import Decimal

        from trust_generator.v3.parsers.pdf_parser import parse_pdf

        pdf_path = self._write_acroform_pdf(
            tmp_path,
            {
                "withdrawal[0].age": "25",
                "withdrawal[0].percent": "50",
                "withdrawal[0].description": "first distribution",
            },
        )
        seed = QuestionnaireSeed(
            trust_type=TrustType.INDIVIDUAL, marital_status=MaritalStatus.UNMARRIED
        )
        result = parse_pdf(pdf_path, promote_seed(seed))
        assert len(result.withdrawal_schedule) == 1
        step = result.withdrawal_schedule[0]
        assert step.age == 25
        assert step.percent == Decimal(50)
        assert step.description == "first distribution"


# ---------------------------------------------------------------------------
# Corrupt / unreadable PDF — pypdf-exception wrap (chore #47 item 1, H4)
# ---------------------------------------------------------------------------

class TestParsePdfCorruptFile:
    """A file that exists but is not a readable PDF must surface ValueError.

    `parse_pdf`'s contract enumerates FileNotFoundError and ValueError only;
    a raw pypdf PyPdfError escaping would breach the parser-layer contract
    that registry.parse_file documents.
    """

    def test_corrupt_pdf_raises_value_error_not_raw_pypdf(self, tmp_path):
        """A file with a PDF header but garbage body raises ValueError."""
        from trust_generator.v3.parsers.pdf_parser import parse_pdf

        corrupt = tmp_path / "corrupt.pdf"
        corrupt.write_bytes(b"%PDF-1.4\n garbage not a real pdf body")
        seed_initialized = promote_seed(
            QuestionnaireSeed(
                trust_type=TrustType.JOINT, marital_status=MaritalStatus.MARRIED
            )
        )
        with pytest.raises(ValueError, match="could not read PDF"):
            parse_pdf(corrupt, seed_initialized)

    def test_empty_file_raises_value_error_not_raw_pypdf(self, tmp_path):
        """A zero-byte file raises ValueError, not a raw pypdf EmptyFileError."""
        from pypdf.errors import PyPdfError

        from trust_generator.v3.parsers.pdf_parser import parse_pdf

        empty = tmp_path / "empty.pdf"
        empty.write_bytes(b"")
        seed_initialized = promote_seed(
            QuestionnaireSeed(
                trust_type=TrustType.JOINT, marital_status=MaritalStatus.MARRIED
            )
        )
        with pytest.raises(ValueError) as excinfo:
            parse_pdf(empty, seed_initialized)
        # The wrap must not leak the raw pypdf exception type.
        assert not isinstance(excinfo.value, PyPdfError)


# ---------------------------------------------------------------------------
# Unknown-enum fallback — trust_type / marital_status (chore #47 item 3)
# ---------------------------------------------------------------------------

class TestParsePdfUnknownEnumFallback:
    """An AcroForm enum field carrying an unrecognized value is logged and
    the seed value is preserved (pdf_parser.py §5.3 step 3-4 fallback)."""

    def _write_acroform_pdf(self, tmp_path: Path, fields: dict[str, str]) -> Path:
        from reportlab.lib.pagesizes import letter

        out = tmp_path / "filled.pdf"
        c = canvas.Canvas(str(out), pagesize=letter)
        form = c.acroForm
        y = 750
        for name, value in fields.items():
            form.textfield(
                name=name,
                tooltip=name,
                value=value,
                x=50,
                y=y,
                width=400,
                height=20,
                fontSize=10,
                borderWidth=0,
            )
            y -= 30
        c.showPage()
        c.save()
        return out

    def test_unknown_trust_type_preserves_seed_and_warns(self, tmp_path, caplog):
        """An unrecognized trust_type value warns and the seed value persists."""
        import logging

        from trust_generator.v3.parsers.pdf_parser import parse_pdf

        pdf_path = self._write_acroform_pdf(
            tmp_path, {"trust_id.trust_type": "revocable-ish"}
        )
        seed = QuestionnaireSeed(
            trust_type=TrustType.INDIVIDUAL, marital_status=MaritalStatus.UNMARRIED
        )
        with caplog.at_level(
            logging.WARNING, logger="trust_generator.v3.parsers.pdf_parser"
        ):
            result = parse_pdf(pdf_path, promote_seed(seed))
        assert result.trust_id.trust_type == TrustType.INDIVIDUAL
        assert any(
            "Unknown trust_type" in r.message for r in caplog.records
        )

    def test_unknown_marital_status_preserves_seed_and_warns(self, tmp_path, caplog):
        """An unrecognized marital_status value warns; seed value persists."""
        import logging

        from trust_generator.v3.parsers.pdf_parser import parse_pdf

        pdf_path = self._write_acroform_pdf(
            tmp_path, {"trust_id.marital_status": "complicated"}
        )
        seed = QuestionnaireSeed(
            trust_type=TrustType.INDIVIDUAL, marital_status=MaritalStatus.UNMARRIED
        )
        with caplog.at_level(
            logging.WARNING, logger="trust_generator.v3.parsers.pdf_parser"
        ):
            result = parse_pdf(pdf_path, promote_seed(seed))
        assert result.trust_id.marital_status == MaritalStatus.UNMARRIED
        assert any(
            "Unknown marital_status" in r.message for r in caplog.records
        )

    def test_marital_status_mutation_via_field(self, tmp_path):
        """A valid marital_status field value overrides the seed value."""
        from trust_generator.v3.parsers.pdf_parser import parse_pdf

        pdf_path = self._write_acroform_pdf(
            tmp_path, {"trust_id.marital_status": "married"}
        )
        seed = QuestionnaireSeed(
            trust_type=TrustType.INDIVIDUAL, marital_status=MaritalStatus.UNMARRIED
        )
        result = parse_pdf(pdf_path, promote_seed(seed))
        assert result.trust_id.marital_status == MaritalStatus.MARRIED


# ---------------------------------------------------------------------------
# Co-grantor round-trip + successor-trustee numbered loop (chore #47 item 3)
# ---------------------------------------------------------------------------

class TestParsePdfCoGrantorAndTrustees:
    """Co-grantor field round-trip and the successor_trustees[i] loop."""

    def _write_acroform_pdf(self, tmp_path: Path, fields: dict[str, str]) -> Path:
        from reportlab.lib.pagesizes import letter

        out = tmp_path / "filled.pdf"
        c = canvas.Canvas(str(out), pagesize=letter)
        form = c.acroForm
        y = 750
        for name, value in fields.items():
            form.textfield(
                name=name,
                tooltip=name,
                value=value,
                x=50,
                y=y,
                width=400,
                height=20,
                fontSize=10,
                borderWidth=0,
            )
            y -= 30
        c.showPage()
        c.save()
        return out

    def test_co_grantor_name_round_trips(self, tmp_path):
        """'co_grantor.full_legal_name' is reflected when co_grantor exists.

        A (JOINT, MARRIED) seed materializes co_grantor via promote_seed, so
        the field assignment branch in parse_pdf fires.
        """
        from trust_generator.v3.parsers.pdf_parser import parse_pdf

        pdf_path = self._write_acroform_pdf(
            tmp_path, {"co_grantor.full_legal_name": "Bob James Smith"}
        )
        seed = QuestionnaireSeed(
            trust_type=TrustType.JOINT, marital_status=MaritalStatus.MARRIED
        )
        result = parse_pdf(pdf_path, promote_seed(seed))
        assert result.co_grantor is not None
        assert result.co_grantor.full_legal_name == "Bob James Smith"

    def test_co_grantor_dob_round_trips(self, tmp_path):
        """'co_grantor.date_of_birth' is coerced and reflected."""
        from datetime import date

        from trust_generator.v3.parsers.pdf_parser import parse_pdf

        pdf_path = self._write_acroform_pdf(
            tmp_path, {"co_grantor.date_of_birth": "07/22/1980"}
        )
        seed = QuestionnaireSeed(
            trust_type=TrustType.JOINT, marital_status=MaritalStatus.MARRIED
        )
        result = parse_pdf(pdf_path, promote_seed(seed))
        assert result.co_grantor is not None
        assert result.co_grantor.date_of_birth == date(1980, 7, 22)

    def test_successor_trustees_numbered_loop(self, tmp_path):
        """Consecutive successor_trustees[i].full_legal_name fields all land."""
        from trust_generator.v3.parsers.pdf_parser import parse_pdf

        pdf_path = self._write_acroform_pdf(
            tmp_path,
            {
                "successor_trustees[0].full_legal_name": "Carol Anne Jones",
                "successor_trustees[1].full_legal_name": "David Lee Brown",
            },
        )
        seed = QuestionnaireSeed(
            trust_type=TrustType.INDIVIDUAL, marital_status=MaritalStatus.UNMARRIED
        )
        result = parse_pdf(pdf_path, promote_seed(seed))
        names = [t.full_legal_name for t in result.successor_trustees]
        assert "Carol Anne Jones" in names
        assert "David Lee Brown" in names

    def test_successor_trustee_loop_stops_on_first_gap(self, tmp_path):
        """The successor_trustees[i] loop stops at the first absent index —
        a non-contiguous index ([2] present, [1] absent) is not reached."""
        from trust_generator.v3.parsers.pdf_parser import parse_pdf

        pdf_path = self._write_acroform_pdf(
            tmp_path,
            {
                "successor_trustees[0].full_legal_name": "Eve Marie White",
                "successor_trustees[2].full_legal_name": "Frank Owen Green",
            },
        )
        seed = QuestionnaireSeed(
            trust_type=TrustType.INDIVIDUAL, marital_status=MaritalStatus.UNMARRIED
        )
        result = parse_pdf(pdf_path, promote_seed(seed))
        names = [t.full_legal_name for t in result.successor_trustees]
        assert "Eve Marie White" in names
        assert "Frank Owen Green" not in names

    def test_corporate_successor_trustee_discriminated(self, tmp_path):
        """An entity-suffixed trustee name is reconstructed as CorporateTrustee
        by _apply_post_merge_resolution (§5.4.9 discrimination)."""
        from trust_generator.v3.parsers.pdf_parser import parse_pdf
        from trust_generator.v3.schema import CorporateTrustee

        pdf_path = self._write_acroform_pdf(
            tmp_path,
            {"successor_trustees[0].full_legal_name": "First National Bank"},
        )
        seed = QuestionnaireSeed(
            trust_type=TrustType.INDIVIDUAL, marital_status=MaritalStatus.UNMARRIED
        )
        result = parse_pdf(pdf_path, promote_seed(seed))
        assert any(
            isinstance(t, CorporateTrustee) for t in result.successor_trustees
        )


# ---------------------------------------------------------------------------
# Beneficiary parity — children / other_beneficiaries / beneficiary_shares
# (chore #47 item 2)
# ---------------------------------------------------------------------------

class TestParsePdfBeneficiaries:
    """Numbered AcroForm extraction of the three beneficiary categories,
    mirroring docx_parser's convention and §5.4.2 share-drop semantics."""

    def _write_acroform_pdf(self, tmp_path: Path, fields: dict[str, str]) -> Path:
        from reportlab.lib.pagesizes import letter

        out = tmp_path / "filled.pdf"
        c = canvas.Canvas(str(out), pagesize=letter)
        form = c.acroForm
        y = 750
        for name, value in fields.items():
            form.textfield(
                name=name,
                tooltip=name,
                value=value,
                x=50,
                y=y,
                width=400,
                height=20,
                fontSize=10,
                borderWidth=0,
            )
            y -= 22
        c.showPage()
        c.save()
        return out

    def _unmarried_seed(self):
        return promote_seed(
            QuestionnaireSeed(
                trust_type=TrustType.INDIVIDUAL,
                marital_status=MaritalStatus.UNMARRIED,
            )
        )

    def test_children_numbered_loop_round_trips(self, tmp_path):
        """children[i].full_legal_name / .date_of_birth populate result.children."""
        from datetime import date

        from trust_generator.v3.parsers.pdf_parser import parse_pdf

        pdf_path = self._write_acroform_pdf(
            tmp_path,
            {
                "children[0].full_legal_name": "Grace Ann Doe",
                "children[0].date_of_birth": "05/10/2010",
                "children[1].full_legal_name": "Henry Lee Doe",
                "children[1].date_of_birth": "11/03/2012",
            },
        )
        result = parse_pdf(pdf_path, self._unmarried_seed())
        assert len(result.children) == 2
        by_name = {c.full_legal_name: c for c in result.children}
        assert by_name["Grace Ann Doe"].date_of_birth == date(2010, 5, 10)
        assert by_name["Henry Lee Doe"].date_of_birth == date(2012, 11, 3)

    def test_child_without_dob_still_extracted(self, tmp_path):
        """A child row with a name but no date_of_birth lands with DOB None."""
        from trust_generator.v3.parsers.pdf_parser import parse_pdf

        pdf_path = self._write_acroform_pdf(
            tmp_path, {"children[0].full_legal_name": "Iris May Doe"}
        )
        result = parse_pdf(pdf_path, self._unmarried_seed())
        assert len(result.children) == 1
        assert result.children[0].full_legal_name == "Iris May Doe"
        assert result.children[0].date_of_birth is None

    def test_child_dob_without_name_dropped_with_warning(self, tmp_path, caplog):
        """A children[i] row with a DOB but no name is dropped and logged."""
        import logging

        from trust_generator.v3.parsers.pdf_parser import parse_pdf

        pdf_path = self._write_acroform_pdf(
            tmp_path, {"children[0].date_of_birth": "01/01/2015"}
        )
        with caplog.at_level(
            logging.WARNING, logger="trust_generator.v3.parsers.pdf_parser"
        ):
            result = parse_pdf(pdf_path, self._unmarried_seed())
        assert len(result.children) == 0
        assert any(
            "children[0]" in r.message and "full_legal_name" in r.message
            for r in caplog.records
        )

    def test_other_beneficiaries_numbered_loop_round_trips(self, tmp_path):
        """other_beneficiaries[i].full_legal_name populates result."""
        from trust_generator.v3.parsers.pdf_parser import parse_pdf

        pdf_path = self._write_acroform_pdf(
            tmp_path,
            {
                "other_beneficiaries[0].full_legal_name": "Jack Ray Stone",
                "other_beneficiaries[1].full_legal_name": "Kate Sue Wood",
            },
        )
        result = parse_pdf(pdf_path, self._unmarried_seed())
        names = [ob.full_legal_name for ob in result.other_beneficiaries]
        assert names == ["Jack Ray Stone", "Kate Sue Wood"]

    def test_beneficiary_shares_numbered_loop_round_trips(self, tmp_path):
        """beneficiary_shares[i].recipient_name / .share_percent populate result
        with the recipient stored as recipient_external (a PersonReference)."""
        from decimal import Decimal

        from trust_generator.v3.parsers.pdf_parser import parse_pdf

        pdf_path = self._write_acroform_pdf(
            tmp_path,
            {
                "beneficiary_shares[0].recipient_name": "Liam Tom Hall",
                "beneficiary_shares[0].share_percent": "60",
                "beneficiary_shares[1].recipient_name": "Mia Joy Reed",
                "beneficiary_shares[1].share_percent": "40",
            },
        )
        result = parse_pdf(pdf_path, self._unmarried_seed())
        assert len(result.beneficiary_shares) == 2
        first = result.beneficiary_shares[0]
        assert first.recipient_external is not None
        assert first.recipient_external.full_legal_name == "Liam Tom Hall"
        assert first.share_percent == Decimal(60)
        assert result.beneficiary_shares[1].share_percent == Decimal(40)

    def test_beneficiary_share_unparseable_percent_dropped(self, tmp_path, caplog):
        """A beneficiary_shares row whose percent parses to Decimal(0) is
        dropped with a warning, mirroring docx_parser's §5.4.2 branch."""
        import logging

        from trust_generator.v3.parsers.pdf_parser import parse_pdf

        pdf_path = self._write_acroform_pdf(
            tmp_path,
            {
                "beneficiary_shares[0].recipient_name": "Noah Kim Park",
                "beneficiary_shares[0].share_percent": "not a number",
            },
        )
        with caplog.at_level(
            logging.WARNING, logger="trust_generator.v3.parsers.pdf_parser"
        ):
            result = parse_pdf(pdf_path, self._unmarried_seed())
        assert len(result.beneficiary_shares) == 0
        assert any(
            "beneficiary_shares[0]" in r.message and "Dropping" in r.message
            for r in caplog.records
        )

    def test_beneficiary_share_recipient_without_percent_dropped(
        self, tmp_path, caplog
    ):
        """A share row with a recipient but no percent parses to Decimal(0)
        and is dropped (the §5.4.2 zero-drop covers a blank percent)."""
        import logging

        from trust_generator.v3.parsers.pdf_parser import parse_pdf

        pdf_path = self._write_acroform_pdf(
            tmp_path,
            {"beneficiary_shares[0].recipient_name": "Olive Fay Cox"},
        )
        with caplog.at_level(
            logging.WARNING, logger="trust_generator.v3.parsers.pdf_parser"
        ):
            result = parse_pdf(pdf_path, self._unmarried_seed())
        assert len(result.beneficiary_shares) == 0

    def test_no_beneficiary_fields_leaves_lists_empty(self, tmp_path):
        """A PDF with no beneficiary fields produces empty beneficiary lists."""
        from trust_generator.v3.parsers.pdf_parser import parse_pdf

        pdf_path = self._write_acroform_pdf(
            tmp_path, {"grantor.full_legal_name": "Pat Ray Quinn"}
        )
        result = parse_pdf(pdf_path, self._unmarried_seed())
        assert result.children == []
        assert result.other_beneficiaries == []
        assert result.beneficiary_shares == []
