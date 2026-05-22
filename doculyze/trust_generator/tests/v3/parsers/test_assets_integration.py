"""Asset-anchored integration tests (Tier 3 per spec §8.3).

These tests exercise the parsers against the checked-in intake artifacts
in `assets/`. They are gated by `pytest.mark.skipif(not <PATH>.exists())`
so that workstation setups without the assets directory still get a
green test run; the synthetic-fixture tests (Tier 2) carry the
deterministic coverage.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from trust_generator.v3.parsers.docx_parser import parse_docx
from trust_generator.v3.schema import (
    MaritalStatus,
    QuestionnaireSeed,
    TrustType,
    promote_seed,
)

QUESTIONNAIRE_PATH = (
    Path(__file__).resolve().parents[3] / "assets" / "Trust_Intake_Questionnaire.docx"
)


@pytest.mark.skipif(
    not QUESTIONNAIRE_PATH.exists(),
    reason="Trust_Intake_Questionnaire.docx not found in assets/",
)
def test_parse_docx_blank_template_into_seed_initialized():
    """Parsing a blank template into a JT+MR seed produces a TrustData
    with the seed's defaults preserved and minimal new content extracted.

    The blank-template input is the integration anchor for the v2.2
    questionnaire shape: it exercises the table-walk, paragraph-walk,
    and checkbox-detection code paths against a real artifact whose
    structure the synthetic fixtures (cycle 5) approximate.
    """
    seed = QuestionnaireSeed(
        trust_type=TrustType.JOINT,
        marital_status=MaritalStatus.MARRIED,
    )
    seed_initialized = promote_seed(seed)
    result = parse_docx(QUESTIONNAIRE_PATH, seed_initialized)

    # Seed-projected defaults survive a no-mutation parse:
    assert result.trust_id.trust_type == TrustType.JOINT
    assert result.trust_id.grantor_caption == "Grantor A"
    assert result.trust_id.co_grantor_caption == "Grantor B"
    assert result.co_grantor is not None
