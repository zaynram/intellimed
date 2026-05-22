"""Tests for draft save/load management."""

import os
import time

import pytest

from trust_generator.schema import PersonInfo, TrustData, TrustType
from trust_generator.ui.drafts import (
    delete_draft,
    draft_display_name,
    list_drafts,
    load_draft,
    purge_old_drafts,
    save_draft,
)


@pytest.fixture(autouse=True)
def _use_tmp_drafts(tmp_path, monkeypatch):
    """Redirect drafts_dir() to a temp directory for all tests."""
    monkeypatch.setattr("trust_generator.ui.drafts.drafts_dir", lambda: tmp_path)


def test_draft_display_name_from_trust_name():
    data = TrustData()
    data.trust_id.desired_trust_name = "Anderson Family Trust"
    assert draft_display_name(data) == "Anderson Family Trust"


def test_draft_display_name_from_party_a():
    data = TrustData()
    data.party_a = PersonInfo(full_legal_name="John Anderson")
    assert draft_display_name(data) == "Anderson Trust"


def test_draft_display_name_unnamed():
    data = TrustData()
    assert draft_display_name(data) == "(Unnamed Trust)"


def test_draft_display_name_individual():
    data = TrustData(trust_type=TrustType.INDIVIDUAL)
    data.grantor = PersonInfo(full_legal_name="Alice Smith")
    assert draft_display_name(data) == "Smith Trust"


def test_save_and_load_round_trip():
    data = TrustData()
    data.party_a = PersonInfo(full_legal_name="John Doe", ssn="123-45-6789")
    path = save_draft(data)
    loaded = load_draft(path)
    assert loaded.party_a.full_legal_name == "John Doe"
    assert loaded.party_a.ssn == ""  # SSN excluded
    raw_json = path.read_text()
    assert "123-45-6789" not in raw_json  # SSN not in file


def test_list_drafts_sorted():
    d1 = TrustData()
    d1.party_a = PersonInfo(full_legal_name="Alice First")
    save_draft(d1)
    time.sleep(0.1)
    d2 = TrustData()
    d2.party_a = PersonInfo(full_legal_name="Bob Second")
    save_draft(d2)
    drafts = list_drafts()
    assert len(drafts) >= 2
    assert drafts[0].modified_date >= drafts[1].modified_date  # most recent first


def test_delete_draft():
    data = TrustData()
    path = save_draft(data)
    assert path.exists()
    delete_draft(path)
    assert not path.exists()


def test_purge_old_drafts():
    data = TrustData()
    path = save_draft(data)
    # Make file appear old
    old_time = path.stat().st_mtime - (91 * 86400)
    os.utime(path, (old_time, old_time))
    count = purge_old_drafts(max_age_days=90)
    assert count == 1
    assert not path.exists()


def test_purge_keeps_recent_drafts():
    data = TrustData()
    path = save_draft(data)
    count = purge_old_drafts(max_age_days=90)
    assert count == 0
    assert path.exists()


def test_save_creates_dated_filename(tmp_path):
    from datetime import datetime

    data = TrustData()
    data.trust_id.desired_trust_name = "Smith Family Trust"
    path = save_draft(data)
    today = datetime.now().strftime("%Y-%m-%d")  # noqa: DTZ005
    assert today in path.name
    assert "smith_family_trust" in path.name
    assert path.suffix == ".json"


def test_same_day_same_name_overwrites():
    """Saving twice with same name on same day overwrites (by design)."""
    data1 = TrustData()
    data1.trust_id.desired_trust_name = "Anderson Trust"
    data1.party_a = PersonInfo(full_legal_name="John Anderson v1")
    path1 = save_draft(data1)

    data2 = TrustData()
    data2.trust_id.desired_trust_name = "Anderson Trust"
    data2.party_a = PersonInfo(full_legal_name="John Anderson v2")
    path2 = save_draft(data2)

    # Same path — overwritten
    assert path1 == path2
    loaded = load_draft(path2)
    assert loaded.party_a.full_legal_name == "John Anderson v2"
    # Only one file exists
    drafts = list_drafts()
    anderson_drafts = [d for d in drafts if "Anderson" in d.display_name]
    assert len(anderson_drafts) == 1
