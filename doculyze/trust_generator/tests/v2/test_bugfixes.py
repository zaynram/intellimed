"""Tests for Task 5 bug fixes: pre-generation check and mutual exclusivity validation."""

from __future__ import annotations

from functools import partial
from pathlib import Path

import pytest

from trust_generator.v2.config import load_config
from trust_generator.v2.generators import generate_trust_document
from trust_generator.v2.schema import (
    BeneficiaryShare,
    Child,
    PersonInfo,
    SuccessorTrustee,
    TrustData,
    TrustIdentity,
    TrustType,
)
from trust_generator.v2.validators import Severity
from trust_generator.v2.validators import validate as _validate

validate = partial(_validate, config=load_config())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _complete_joint_data() -> TrustData:
    return TrustData(
        party_a=PersonInfo(full_legal_name="John Andrew Smith"),
        party_b=PersonInfo(full_legal_name="Jane Marie Smith"),
        trust_id=TrustIdentity(
            desired_trust_name="The Smith Family Trust",
            date="January 1, 2026",
            state_of_governing_law="Illinois",
            county_of_execution="Winnebago",
        ),
        children=[
            Child(name="Alice Smith", dob="01/15/2000"),
        ],
        successor_trustees=[
            SuccessorTrustee(order="1", name="Alice Smith", relationship="Daughter"),
        ],
        beneficiary_shares=[
            BeneficiaryShare(name="Alice Smith", share="100"),
        ],
    )


def _complete_individual_data() -> TrustData:
    return TrustData(
        trust_type=TrustType.INDIVIDUAL,
        grantor=PersonInfo(full_legal_name="Robert James Wilson"),
        trust_id=TrustIdentity(
            desired_trust_name="The Wilson Family Trust",
            date="March 15, 2026",
            state_of_governing_law="Illinois",
            county_of_execution="Winnebago",
        ),
        children=[
            Child(name="Sarah Wilson", dob="05/10/1995"),
        ],
        successor_trustees=[
            SuccessorTrustee(order="1", name="Sarah Wilson", relationship="Daughter"),
        ],
        beneficiary_shares=[
            BeneficiaryShare(name="Sarah Wilson", share="100"),
        ],
    )


# ===========================================================================
# Fix 2: Pre-generation check
# ===========================================================================


class TestPreGenerationCheck:
    """Pre-generation check should block on missing critical fields."""

    def test_blocks_when_critical_field_missing(self, tmp_path: Path):
        """Empty TrustData should raise ValueError (missing critical fields)."""
        data = TrustData()
        path = tmp_path / "should_fail.docx"
        with pytest.raises(ValueError, match="missing critical fields"):
            generate_trust_document(data, path)

    def test_passes_with_complete_data(self, tmp_path: Path):
        """Complete data should generate without errors."""
        data = _complete_joint_data()
        path = tmp_path / "should_pass.docx"
        result = generate_trust_document(data, path)
        assert Path(result).exists()

    def test_bypassed_with_force(self, tmp_path: Path):
        """force=True should skip the pre-generation check."""
        data = TrustData()
        path = tmp_path / "forced.docx"
        result = generate_trust_document(data, path, force=True)
        assert Path(result).exists()

    def test_individual_blocks_without_grantor(self, tmp_path: Path):
        """Individual trust without grantor name should raise ValueError."""
        data = TrustData(trust_type=TrustType.INDIVIDUAL)
        path = tmp_path / "individual_fail.docx"
        with pytest.raises(ValueError, match="missing critical fields"):
            generate_trust_document(data, path)

    def test_individual_passes_with_complete_data(self, tmp_path: Path):
        """Complete individual data should generate without errors."""
        data = _complete_individual_data()
        path = tmp_path / "individual_pass.docx"
        result = generate_trust_document(data, path)
        assert Path(result).exists()


# ===========================================================================
# Fix 7: Mutual exclusivity validation
# ===========================================================================


class TestMutualExclusivityValidation:
    """Trust type / grantor fields mutual exclusivity warnings."""

    def test_individual_with_party_fields_warns(self):
        """Individual trust with party_a/b populated should produce a warning."""
        data = TrustData(
            trust_type=TrustType.INDIVIDUAL,
            grantor=PersonInfo(full_legal_name="Robert James Wilson"),
            party_a=PersonInfo(full_legal_name="Should Not Be Here"),
        )
        report = validate(data)
        mutual_warnings = [
            f
            for f in report.findings
            if f.severity == Severity.WARNING and "party a/b" in f.message.lower()
        ]
        assert len(mutual_warnings) == 1

    def test_joint_with_grantor_field_warns(self):
        """Joint trust with grantor populated should produce a warning."""
        data = TrustData(
            trust_type=TrustType.JOINT,
            party_a=PersonInfo(full_legal_name="John Andrew Smith"),
            party_b=PersonInfo(full_legal_name="Jane Marie Smith"),
            grantor=PersonInfo(full_legal_name="Should Not Be Here"),
        )
        report = validate(data)
        mutual_warnings = [
            f
            for f in report.findings
            if f.severity == Severity.WARNING
            and "grantor" in f.message.lower()
            and "ignored" in f.message.lower()
        ]
        assert len(mutual_warnings) == 1

    def test_individual_without_party_fields_no_warning(self):
        """Individual trust without party fields should not produce mutual exclusivity warning."""
        data = _complete_individual_data()
        report = validate(data)
        mutual_warnings = [
            f
            for f in report.findings
            if f.severity == Severity.WARNING and "party a/b" in f.message.lower()
        ]
        assert len(mutual_warnings) == 0

    def test_joint_without_grantor_field_no_warning(self):
        """Joint trust without grantor should not produce mutual exclusivity warning."""
        data = _complete_joint_data()
        report = validate(data)
        mutual_warnings = [
            f
            for f in report.findings
            if f.severity == Severity.WARNING
            and "grantor" in f.message.lower()
            and "ignored" in f.message.lower()
        ]
        assert len(mutual_warnings) == 0


# ===========================================================================
# Pre-generation check with partial data (test gap H)
# ===========================================================================


class TestPreGenerationCheckPartialData:
    """Pre-gen check should identify specific missing fields."""

    def test_joint_missing_party_b_only(self, tmp_path: Path):
        """Joint trust with party_a but no party_b should name party_b_name."""
        data = TrustData(
            party_a=PersonInfo(full_legal_name="John Smith"),
            trust_id=TrustIdentity(
                desired_trust_name="Smith Trust",
                date="January 1, 2026",
                state_of_governing_law="Illinois",
                county_of_execution="Winnebago",
            ),
        )
        path = tmp_path / "partial.docx"
        with pytest.raises(ValueError, match="party_b_name"):
            generate_trust_document(data, path)

    def test_individual_missing_grantor_name(self, tmp_path: Path):
        """Individual trust with no grantor name should name grantor_name."""
        data = TrustData(
            trust_type=TrustType.INDIVIDUAL,
            trust_id=TrustIdentity(
                desired_trust_name="Test Trust",
                date="January 1, 2026",
                state_of_governing_law="Illinois",
                county_of_execution="Winnebago",
            ),
        )
        path = tmp_path / "partial_individual.docx"
        with pytest.raises(ValueError, match="grantor_name"):
            generate_trust_document(data, path)

    def test_missing_county_specifically(self, tmp_path: Path):
        """Missing county should be named in the error."""
        data = TrustData(
            party_a=PersonInfo(full_legal_name="John Smith"),
            party_b=PersonInfo(full_legal_name="Jane Smith"),
            trust_id=TrustIdentity(
                desired_trust_name="Smith Trust",
                date="January 1, 2026",
                state_of_governing_law="Illinois",
                # county_of_execution intentionally missing
            ),
        )
        path = tmp_path / "no_county.docx"
        with pytest.raises(ValueError, match="county"):
            generate_trust_document(data, path)


# ===========================================================================
# Pronoun map verification (test gap A)
# ===========================================================================


class TestPronounMap:
    """Verify the pronoun substitution map produces correct values."""

    def _get_phrasing(self, trust_type: TrustType) -> dict[str, str]:
        """Get the _p dict for a given trust type."""
        from trust_generator.v2.generators.trust_document import (
            DocxFormatter,
            _TrustDocGen,
        )

        if trust_type == TrustType.INDIVIDUAL:
            data = _complete_individual_data()
        else:
            data = _complete_joint_data()
        gen = _TrustDocGen(data, DocxFormatter(), load_config())
        return gen._p

    def test_individual_pronouns_singular(self):
        """Individual trust uses I/my/me language."""
        p = self._get_phrasing(TrustType.INDIVIDUAL)
        assert p["subject"] == "I"
        assert p["object"] == "me"
        assert p["possessive"] == "my"
        assert p["reflexive"] == "myself"
        assert p["subject_have"] == "I have"
        assert p["children_possessive"] == "my children"

    def test_joint_pronouns_plural(self):
        """Joint trust uses We/our/us language."""
        p = self._get_phrasing(TrustType.JOINT)
        assert p["subject"] == "We"
        assert p["object"] == "us"
        assert p["possessive"] == "our"
        assert p["reflexive"] == "ourselves"
        assert p["subject_have"] == "We have"
        assert p["children_possessive"] == "our children"

    def test_individual_trustee_ref(self):
        """Individual trust refers to 'the Trustee' (no possessive)."""
        p = self._get_phrasing(TrustType.INDIVIDUAL)
        assert p["trustee_ref"] == "the Trustee"
        assert p["trustee_ref_cap"] == "The Trustee"

    def test_joint_trustee_ref(self):
        """Joint trust refers to 'our Trustee'."""
        p = self._get_phrasing(TrustType.JOINT)
        assert p["trustee_ref"] == "our Trustee"
        assert p["trustee_ref_cap"] == "Our Trustee"

    def test_all_keys_present_individual(self):
        """Individual phrasing map has all expected keys."""
        p = self._get_phrasing(TrustType.INDIVIDUAL)
        expected_keys = {
            "subject",
            "subject_lc",
            "object",
            "possessive",
            "possessive_cap",
            "reflexive",
            "subject_have",
            "subject_may",
            "subject_request",
            "subject_intend",
            "subject_create",
            "trustee_ref",
            "trustee_ref_cap",
            "grantor_ref",
            "grantor_ref_plural",
            "grantor_ref_cap",
            "children_possessive",
        }
        assert set(p.keys()) == expected_keys

    def test_all_keys_present_joint(self):
        """Joint phrasing map has the same keys as individual."""
        p_individual = self._get_phrasing(TrustType.INDIVIDUAL)
        p_joint = self._get_phrasing(TrustType.JOINT)
        assert set(p_individual.keys()) == set(p_joint.keys())

    def test_no_individual_pronouns_in_joint(self):
        """Joint trust should never use singular 'I' or 'my'."""
        p = self._get_phrasing(TrustType.JOINT)
        for key, val in p.items():
            # 'I' appears in some joint values legitimately (e.g., "Grantor" contains no I)
            # But the subject should be "We", not "I"
            if key == "subject":
                assert val != "I", f"Joint {key} should not be 'I'"
            if key == "possessive":
                assert val != "my", f"Joint {key} should not be 'my'"


# ===========================================================================
# Trust type auto-detection surfaces as validation finding (issue 10)
# ===========================================================================


class TestTrustTypeValidationFinding:
    """Individual trust type should surface as INFO finding in validation."""

    def test_individual_trust_has_info_finding(self):
        """Individual trust should produce an INFO finding about trust type."""
        data = _complete_individual_data()
        report = validate(data)
        type_findings = [
            f
            for f in report.findings
            if f.severity == Severity.INFO and "individual" in f.message.lower()
        ]
        assert len(type_findings) >= 1

    def test_joint_trust_no_type_finding(self):
        """Joint trust should not produce trust type INFO finding."""
        data = _complete_joint_data()
        report = validate(data)
        type_findings = [f for f in report.findings if f.field_path == "trust_type"]
        assert len(type_findings) == 0
