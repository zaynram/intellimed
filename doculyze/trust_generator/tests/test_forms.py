"""Tests for the form widget module."""

from __future__ import annotations

import tkinter as tk

import pytest


@pytest.fixture(scope="session")
def root():
    """Shared Tk root for widget tests.

    Session-scoped to avoid Tcl re-initialization failures when pixi's
    Tkinter environment re-reads init.tcl for each tk.Tk() call.
    """
    r = tk.Tk()
    r.withdraw()  # hide window
    yield r
    r.destroy()


def test_text_field_get_set(root):
    from trust_generator.ui.forms import TextField

    parent = tk.Frame(root)
    field = TextField(parent, label="Full Name", field_path="party_a.full_legal_name")
    field.pack()

    field.set_value("John Smith")
    assert field.get_value() == "John Smith"


def test_text_field_empty_default(root):
    from trust_generator.ui.forms import TextField

    parent = tk.Frame(root)
    field = TextField(parent, label="Name", field_path="party_a.full_legal_name")
    field.pack()

    assert field.get_value() == ""


def test_text_field_field_path(root):
    from trust_generator.ui.forms import TextField

    parent = tk.Frame(root)
    field = TextField(parent, label="Name", field_path="party_a.full_legal_name")
    assert field.field_path == "party_a.full_legal_name"


def test_form_tab_collect(root):
    from trust_generator.ui.forms import FormTab

    parent = tk.Frame(root)
    tab = FormTab(parent, title="Party A")
    tab.pack()

    f1 = tab.add_text_field("Full Name", "party_a.full_legal_name")
    f2 = tab.add_text_field("Date of Birth", "party_a.date_of_birth")

    f1.set_value("John Smith")
    f2.set_value("01/15/1970")

    data = tab.collect()
    assert data == {
        "party_a.full_legal_name": "John Smith",
        "party_a.date_of_birth": "01/15/1970",
    }


def test_form_tab_populate(root):
    from trust_generator.ui.forms import FormTab

    parent = tk.Frame(root)
    tab = FormTab(parent, title="Party A")
    tab.pack()

    f1 = tab.add_text_field("Full Name", "party_a.full_legal_name")
    f2 = tab.add_text_field("DOB", "party_a.date_of_birth")

    tab.populate({
        "party_a.full_legal_name": "Jane Doe",
        "party_a.date_of_birth": "03/20/1975",
    })

    assert f1.get_value() == "Jane Doe"
    assert f2.get_value() == "03/20/1975"


def test_dropdown_field_get_set(root):
    from trust_generator.ui.forms import DropdownField

    parent = tk.Frame(root)
    field = DropdownField(
        parent,
        label="Initial Trustee",
        field_path="elections.initial_trustee",
        options=["both", "husband", "wife"],
        default="both",
    )
    field.pack()

    assert field.get_value() == "both"
    field.set_value("wife")
    assert field.get_value() == "wife"


def test_checkbox_field_get_set(root):
    from trust_generator.ui.forms import CheckboxField

    parent = tk.Frame(root)
    field = CheckboxField(
        parent,
        label="Spendthrift Protection",
        field_path="elections.spendthrift",
        default=True,
    )
    field.pack()

    assert field.get_value() is True
    field.set_value(False)
    assert field.get_value() is False


def test_form_tab_mixed_fields(root):
    from trust_generator.ui.forms import FormTab

    parent = tk.Frame(root)
    tab = FormTab(parent, title="Elections")
    tab.pack()

    tab.add_dropdown_field(
        "Trustee", "elections.initial_trustee",
        options=["both", "husband", "wife"], default="both",
    )
    tab.add_checkbox_field("Spendthrift", "elections.spendthrift", default=True)

    data = tab.collect()
    assert data["elections.initial_trustee"] == "both"
    assert data["elections.spendthrift"] is True


def test_flat_to_trust_data():
    from trust_generator.ui.forms import flat_to_trust_data
    from trust_generator.schema import TrustData

    flat = {
        "party_a.full_legal_name": "John Smith",
        "party_a.date_of_birth": "01/15/1970",
        "party_b.full_legal_name": "Jane Smith",
        "trust_id.desired_trust_name": "The Smith Trust",
        "elections.initial_trustee": "both",
        "elections.spendthrift": True,
    }
    td = flat_to_trust_data(flat)
    assert isinstance(td, TrustData)
    assert td.party_a.full_legal_name == "John Smith"
    assert td.party_b.full_legal_name == "Jane Smith"
    assert td.trust_id.desired_trust_name == "The Smith Trust"
    assert td.elections.spendthrift is True


def test_trust_data_to_flat():
    from trust_generator.ui.forms import trust_data_to_flat
    from trust_generator.schema import PersonInfo, TrustData, TrustIdentity

    td = TrustData(
        party_a=PersonInfo(full_legal_name="John Smith", date_of_birth="01/15/1970"),
        party_b=PersonInfo(full_legal_name="Jane Smith"),
        trust_id=TrustIdentity(desired_trust_name="The Smith Trust"),
    )
    flat = trust_data_to_flat(td)
    assert flat["party_a.full_legal_name"] == "John Smith"
    assert flat["party_a.date_of_birth"] == "01/15/1970"
    assert flat["party_b.full_legal_name"] == "Jane Smith"
    assert flat["trust_id.desired_trust_name"] == "The Smith Trust"


def test_round_trip_flat_conversion():
    from trust_generator.ui.forms import flat_to_trust_data, trust_data_to_flat
    from trust_generator.schema import PersonInfo, TrustData

    original = TrustData(
        party_a=PersonInfo(full_legal_name="John Smith"),
        party_b=PersonInfo(full_legal_name="Jane Smith"),
    )
    flat = trust_data_to_flat(original)
    restored = flat_to_trust_data(flat)
    assert restored.party_a.full_legal_name == original.party_a.full_legal_name
    assert restored.party_b.full_legal_name == original.party_b.full_legal_name


# ---------------------------------------------------------------------------
# ListEditor tests
# ---------------------------------------------------------------------------


def test_list_editor_get_empty(root):
    from trust_generator.ui.forms import ListEditor

    editor = ListEditor(root, [("name", "Name", 20)])
    assert editor.get_items() == []


def test_list_editor_add_and_get(root):
    from trust_generator.ui.forms import ListEditor

    editor = ListEditor(root, [("name", "Name", 20), ("value", "Value", 10)])
    editor._add_row({"name": "Test", "value": "123"})
    items = editor.get_items()
    assert len(items) == 1
    assert items[0] == {"name": "Test", "value": "123"}


def test_list_editor_set_items(root):
    from trust_generator.ui.forms import ListEditor

    editor = ListEditor(root, [("name", "Name", 20)])
    editor.set_items([{"name": "Alice"}, {"name": "Bob"}])
    items = editor.get_items()
    assert len(items) == 2
    assert items[0]["name"] == "Alice"
    assert items[1]["name"] == "Bob"


def test_list_editor_empty_rows_excluded(root):
    from trust_generator.ui.forms import ListEditor

    editor = ListEditor(root, [("name", "Name", 20)])
    editor._add_row({"name": "Alice"})
    editor._add_row({"name": ""})
    items = editor.get_items()
    assert len(items) == 1
