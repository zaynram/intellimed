# Full Data Entry GUI Mode — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let paralegals create trust documents from scratch via field-by-field data entry in the GUI, without needing a pre-filled .docx questionnaire. Support save/load of work-in-progress as JSON.

**Architecture:** Add a new `ui/forms.py` module with reusable Tkinter form widgets and a two-way data binder. Extend the existing `TrustGeneratorApp` in `ui/gui.py` with a mode-selection step (New vs Import) and a tabbed data-entry step. The entry step produces a `TrustData` instance that feeds into the existing Review → Generate → Results pipeline.

**Tech Stack:** Python 3.12+, Tkinter/ttk, Pydantic 2, pytest

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `src/trust_generator/ui/forms.py` | Reusable form widgets: TextField, DropdownField, CheckboxField, ListField, FormTab |
| Modify | `src/trust_generator/ui/gui.py` | Add Step 0 (mode selection), Step 1a (data entry), save/load draft |
| Create | `tests/test_forms.py` | Unit tests for form serialization and data binding |
| Modify | `tests/test_cli.py` | No changes needed (CLI is unaffected) |

---

### Task 1: Create form widget module with TextField and serialization

**Files:**
- Create: `src/trust_generator/ui/forms.py`
- Create: `tests/test_forms.py`

- [ ] **Step 1: Write failing tests for TextField and form serialization**

Create `tests/test_forms.py`:

```python
"""Tests for the form widget module."""

from __future__ import annotations

import tkinter as tk

import pytest


@pytest.fixture
def root():
    """Create and destroy a Tk root for widget tests."""
    r = tk.Tk()
    r.withdraw()  # hide window
    yield r
    r.destroy()


def test_text_field_get_set(root):
    from trust_generator.ui.forms import TextField

    parent = tk.Frame(root)
    field = TextField(parent, label="Full Name", field_path="husband.full_legal_name")
    field.pack()

    field.set_value("John Smith")
    assert field.get_value() == "John Smith"


def test_text_field_empty_default(root):
    from trust_generator.ui.forms import TextField

    parent = tk.Frame(root)
    field = TextField(parent, label="Name", field_path="husband.full_legal_name")
    field.pack()

    assert field.get_value() == ""


def test_text_field_field_path(root):
    from trust_generator.ui.forms import TextField

    parent = tk.Frame(root)
    field = TextField(parent, label="Name", field_path="husband.full_legal_name")
    assert field.field_path == "husband.full_legal_name"


def test_form_tab_collect(root):
    from trust_generator.ui.forms import FormTab, TextField

    parent = tk.Frame(root)
    tab = FormTab(parent, title="Husband")
    tab.pack()

    f1 = tab.add_text_field("Full Name", "husband.full_legal_name")
    f2 = tab.add_text_field("Date of Birth", "husband.date_of_birth")

    f1.set_value("John Smith")
    f2.set_value("01/15/1970")

    data = tab.collect()
    assert data == {
        "husband.full_legal_name": "John Smith",
        "husband.date_of_birth": "01/15/1970",
    }


def test_form_tab_populate(root):
    from trust_generator.ui.forms import FormTab

    parent = tk.Frame(root)
    tab = FormTab(parent, title="Husband")
    tab.pack()

    f1 = tab.add_text_field("Full Name", "husband.full_legal_name")
    f2 = tab.add_text_field("DOB", "husband.date_of_birth")

    tab.populate({
        "husband.full_legal_name": "Jane Doe",
        "husband.date_of_birth": "03/20/1975",
    })

    assert f1.get_value() == "Jane Doe"
    assert f2.get_value() == "03/20/1975"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_forms.py -v -x`
Expected: FAIL with `ModuleNotFoundError: No module named 'trust_generator.ui.forms'`

- [ ] **Step 3: Create forms.py with TextField and FormTab**

Create `src/trust_generator/ui/forms.py`:

```python
"""Reusable Tkinter form widgets for trust data entry.

Each widget is bound to a schema field path (dotted string like
'husband.full_legal_name') and supports get/set for two-way binding.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class TextField(ttk.Frame):
    """Label + Entry widget bound to a schema field path."""

    def __init__(
        self,
        parent: tk.Widget,
        *,
        label: str,
        field_path: str,
        width: int = 50,
    ) -> None:
        super().__init__(parent)
        self.field_path = field_path
        self._var = tk.StringVar()

        ttk.Label(self, text=f"{label}:", width=25, anchor="w").pack(
            side=tk.LEFT, padx=(0, 5)
        )
        ttk.Entry(self, textvariable=self._var, width=width).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )

    def get_value(self) -> str:
        return self._var.get()

    def set_value(self, value: str) -> None:
        self._var.set(value)


class DropdownField(ttk.Frame):
    """Label + Combobox widget bound to an enum field path."""

    def __init__(
        self,
        parent: tk.Widget,
        *,
        label: str,
        field_path: str,
        options: list[str],
        default: str = "",
    ) -> None:
        super().__init__(parent)
        self.field_path = field_path
        self._var = tk.StringVar(value=default)

        ttk.Label(self, text=f"{label}:", width=25, anchor="w").pack(
            side=tk.LEFT, padx=(0, 5)
        )
        combo = ttk.Combobox(
            self, textvariable=self._var, values=options, state="readonly", width=30
        )
        combo.pack(side=tk.LEFT)

    def get_value(self) -> str:
        return self._var.get()

    def set_value(self, value: str) -> None:
        self._var.set(value)


class CheckboxField(ttk.Frame):
    """Label + Checkbutton widget bound to a boolean field path."""

    def __init__(
        self,
        parent: tk.Widget,
        *,
        label: str,
        field_path: str,
        default: bool = False,
    ) -> None:
        super().__init__(parent)
        self.field_path = field_path
        self._var = tk.BooleanVar(value=default)

        ttk.Checkbutton(self, text=label, variable=self._var).pack(
            side=tk.LEFT
        )

    def get_value(self) -> bool:
        return self._var.get()

    def set_value(self, value: bool) -> None:
        self._var.set(value)


class FormTab(ttk.Frame):
    """A frame that holds multiple form fields and supports collect/populate."""

    def __init__(self, parent: tk.Widget, *, title: str) -> None:
        super().__init__(parent, padding=10)
        self.title = title
        self._fields: list[TextField | DropdownField | CheckboxField] = []

    def add_text_field(self, label: str, field_path: str) -> TextField:
        field = TextField(self, label=label, field_path=field_path)
        field.pack(fill=tk.X, pady=2)
        self._fields.append(field)
        return field

    def add_dropdown_field(
        self, label: str, field_path: str, options: list[str], default: str = ""
    ) -> DropdownField:
        field = DropdownField(
            self, label=label, field_path=field_path, options=options, default=default
        )
        field.pack(fill=tk.X, pady=2)
        self._fields.append(field)
        return field

    def add_checkbox_field(
        self, label: str, field_path: str, default: bool = False
    ) -> CheckboxField:
        field = CheckboxField(
            self, label=label, field_path=field_path, default=default
        )
        field.pack(fill=tk.X, pady=2)
        self._fields.append(field)
        return field

    def collect(self) -> dict[str, str | bool]:
        """Collect all field values into a flat dict keyed by field_path."""
        return {f.field_path: f.get_value() for f in self._fields}

    def populate(self, data: dict[str, str | bool]) -> None:
        """Populate fields from a flat dict keyed by field_path."""
        for field in self._fields:
            if field.field_path in data:
                field.set_value(data[field.field_path])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_forms.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/trust_generator/ui/forms.py tests/test_forms.py
git commit -m "feat: add form widget module with TextField, DropdownField, CheckboxField, FormTab"
```

---

### Task 2: Add DropdownField and CheckboxField tests

**Files:**
- Modify: `tests/test_forms.py`

- [ ] **Step 1: Write tests for dropdown and checkbox widgets**

Add to `tests/test_forms.py`:

```python
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
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_forms.py -v`
Expected: ALL PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_forms.py
git commit -m "test: add dropdown and checkbox form widget tests"
```

---

### Task 3: Add flat-dict-to-TrustData and TrustData-to-flat-dict conversion

**Files:**
- Modify: `src/trust_generator/ui/forms.py`
- Modify: `tests/test_forms.py`

This is the data binding layer: converting between the flat `{field_path: value}` dict that form widgets produce and the nested `TrustData` Pydantic model.

- [ ] **Step 1: Write failing tests for conversion functions**

Add to `tests/test_forms.py`:

```python
def test_flat_to_trust_data():
    from trust_generator.ui.forms import flat_to_trust_data
    from trust_generator.schema import TrustData

    flat = {
        "husband.full_legal_name": "John Smith",
        "husband.date_of_birth": "01/15/1970",
        "wife.full_legal_name": "Jane Smith",
        "trust_id.desired_trust_name": "The Smith Trust",
        "elections.initial_trustee": "both",
        "elections.spendthrift": True,
    }
    td = flat_to_trust_data(flat)
    assert isinstance(td, TrustData)
    assert td.husband.full_legal_name == "John Smith"
    assert td.wife.full_legal_name == "Jane Smith"
    assert td.trust_id.desired_trust_name == "The Smith Trust"
    assert td.elections.spendthrift is True


def test_trust_data_to_flat():
    from trust_generator.ui.forms import trust_data_to_flat
    from trust_generator.schema import PersonInfo, TrustData, TrustIdentity

    td = TrustData(
        husband=PersonInfo(full_legal_name="John Smith", date_of_birth="01/15/1970"),
        wife=PersonInfo(full_legal_name="Jane Smith"),
        trust_id=TrustIdentity(desired_trust_name="The Smith Trust"),
    )
    flat = trust_data_to_flat(td)
    assert flat["husband.full_legal_name"] == "John Smith"
    assert flat["husband.date_of_birth"] == "01/15/1970"
    assert flat["wife.full_legal_name"] == "Jane Smith"
    assert flat["trust_id.desired_trust_name"] == "The Smith Trust"


def test_round_trip_flat_conversion():
    from trust_generator.ui.forms import flat_to_trust_data, trust_data_to_flat
    from trust_generator.schema import PersonInfo, TrustData

    original = TrustData(
        husband=PersonInfo(full_legal_name="John Smith"),
        wife=PersonInfo(full_legal_name="Jane Smith"),
    )
    flat = trust_data_to_flat(original)
    restored = flat_to_trust_data(flat)
    assert restored.husband.full_legal_name == original.husband.full_legal_name
    assert restored.wife.full_legal_name == original.wife.full_legal_name
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_forms.py::test_flat_to_trust_data -v -x`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement conversion functions**

Add to `src/trust_generator/ui/forms.py`:

```python
from trust_generator.schema import (
    Elections,
    MarriageInfo,
    OfficeInfo,
    PersonInfo,
    TrustData,
    TrustIdentity,
    TrustType,
)

# Mapping of dotted field paths to (parent_attr, child_attr) for scalar sub-models
_SCALAR_MODELS = {
    "husband": PersonInfo,
    "wife": PersonInfo,
    "grantor": PersonInfo,
    "trust_id": TrustIdentity,
    "marriage": MarriageInfo,
    "office": OfficeInfo,
}

# Election fields that are booleans (vs enum strings)
_BOOL_ELECTIONS = {
    "no_contest", "spendthrift", "probate_coordination",
    "portability", "trustee_bond",
}


def trust_data_to_flat(td: TrustData) -> dict[str, str | bool]:
    """Convert a TrustData to a flat {field_path: value} dict for form population."""
    flat: dict[str, str | bool] = {}
    flat["trust_type"] = td.trust_type.value

    for parent_name in ("husband", "wife", "grantor", "trust_id", "marriage", "office"):
        parent_obj = getattr(td, parent_name)
        for field_name, field_value in parent_obj.__dict__.items():
            flat[f"{parent_name}.{field_name}"] = field_value

    # Elections
    for field_name, field_value in td.elections.__dict__.items():
        if isinstance(field_value, bool):
            flat[f"elections.{field_name}"] = field_value
        elif hasattr(field_value, "value"):
            flat[f"elections.{field_name}"] = field_value.value
        else:
            flat[f"elections.{field_name}"] = str(field_value)

    # Text blocks
    for field_name, field_value in td.text_blocks.__dict__.items():
        flat[f"text_blocks.{field_name}"] = field_value

    return flat


def flat_to_trust_data(flat: dict[str, str | bool]) -> TrustData:
    """Convert a flat {field_path: value} dict back to TrustData."""
    from trust_generator.schema import Elections, TextBlocks

    kwargs: dict[str, object] = {}

    # Trust type
    trust_type_val = flat.get("trust_type", "joint")
    kwargs["trust_type"] = TrustType(trust_type_val) if isinstance(trust_type_val, str) else TrustType.JOINT

    # Scalar sub-models
    for parent_name, model_cls in _SCALAR_MODELS.items():
        parent_data: dict[str, str] = {}
        prefix = f"{parent_name}."
        for key, val in flat.items():
            if key.startswith(prefix) and isinstance(val, str):
                parent_data[key[len(prefix):]] = val
        if parent_data:
            kwargs[parent_name] = model_cls(**parent_data)

    # Elections
    election_data: dict[str, object] = {}
    for key, val in flat.items():
        if not key.startswith("elections."):
            continue
        field_name = key[len("elections."):]
        if field_name in _BOOL_ELECTIONS:
            election_data[field_name] = val if isinstance(val, bool) else val == "True"
        else:
            election_data[field_name] = val
    if election_data:
        kwargs["elections"] = Elections(**election_data)

    # Text blocks
    text_data: dict[str, str] = {}
    for key, val in flat.items():
        if key.startswith("text_blocks.") and isinstance(val, str):
            text_data[key[len("text_blocks."):]] = val
    if text_data:
        kwargs["text_blocks"] = TextBlocks(**text_data)

    return TrustData(**kwargs)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_forms.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/trust_generator/ui/forms.py tests/test_forms.py
git commit -m "feat: add flat-dict <-> TrustData conversion for form data binding"
```

---

### Task 4: Add mode selection (Step 0) to GUI

**Files:**
- Modify: `src/trust_generator/ui/gui.py`

- [ ] **Step 1: Add _show_step0 method**

In `src/trust_generator/ui/gui.py`, modify `__init__` to call `_show_step0()` instead of `_show_step1()` (line 64).

Add a new `_show_step0` method:

```python
    def _show_step0(self) -> None:
        """Step 0: Choose mode — Import existing questionnaire or New trust."""
        self._clear_container()
        self.data = None

        frame = ttk.Frame(self.container, padding=40)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Trust Generator", style="Title.TLabel").pack(
            pady=(0, 2)
        )
        ttk.Label(
            frame, text=self.config.firm.name, style="Subtitle.TLabel"
        ).pack(pady=(0, 30))
        ttk.Separator(frame, orient="horizontal").pack(fill=tk.X, pady=10)

        ttk.Label(
            frame,
            text="How would you like to begin?",
            font=("Segoe UI", 11),
        ).pack(pady=(20, 30))

        btn_frame = ttk.Frame(frame)
        btn_frame.pack()

        ttk.Button(
            btn_frame,
            text="Import Questionnaire",
            style="Big.TButton",
            command=self._show_step1,
        ).pack(side=tk.LEFT, padx=20)

        ttk.Button(
            btn_frame,
            text="New Trust (Manual Entry)",
            style="Big.TButton",
            command=self._show_entry,
        ).pack(side=tk.LEFT, padx=20)

        ttk.Separator(frame, orient="horizontal").pack(fill=tk.X, pady=(40, 10))
        ttk.Label(
            frame,
            text="Import: Parse a completed .docx or .json questionnaire\n"
                 "New Trust: Enter client data directly in the application",
            font=("Segoe UI", 9),
            foreground="gray",
            justify="center",
        ).pack()
```

Update the Back button in `_show_step1` to go back to `_show_step0` instead of nowhere.

- [ ] **Step 2: Verify GUI launches without crash**

Run: `python -c "import trust_generator.ui.forms"` (quick import check)
Expected: No error

- [ ] **Step 3: Commit**

```bash
git add src/trust_generator/ui/gui.py
git commit -m "feat: add mode selection step (Import vs New Trust) to GUI"
```

---

### Task 5: Add tabbed data entry step to GUI

**Files:**
- Modify: `src/trust_generator/ui/gui.py`

- [ ] **Step 1: Add _show_entry method with tabbed form**

Add a `_show_entry` method to `TrustGeneratorApp`. This builds a `ttk.Notebook` with tabs for each data section:

```python
    def _show_entry(self) -> None:
        """Step 1a: Manual data entry with tabbed form."""
        self._clear_container()

        from trust_generator.ui.forms import FormTab, flat_to_trust_data, trust_data_to_flat

        frame = ttk.Frame(self.container, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="New Trust — Data Entry", style="Title.TLabel").pack(
            pady=(0, 10)
        )

        notebook = ttk.Notebook(frame)
        notebook.pack(fill=tk.BOTH, expand=True, pady=5)

        self._entry_tabs: list[FormTab] = []

        # Tab: Trust Info
        tab_trust = FormTab(notebook, title="Trust Info")
        tab_trust.add_dropdown_field(
            "Trust Type", "trust_type",
            options=["joint", "individual"], default="joint",
        )
        tab_trust.add_text_field("Trust Name", "trust_id.desired_trust_name")
        tab_trust.add_text_field("Trust Date", "trust_id.date")
        tab_trust.add_text_field("State", "trust_id.state_of_governing_law")
        tab_trust.add_text_field("County", "trust_id.county_of_execution")
        tab_trust.add_text_field("Whose SSN for Tax ID", "trust_id.whose_ssn_for_tax_id")
        notebook.add(tab_trust, text="Trust Info")
        self._entry_tabs.append(tab_trust)

        # Tab: Husband
        tab_husband = FormTab(notebook, title="Husband")
        for label, path in [
            ("Full Legal Name", "husband.full_legal_name"),
            ("Date of Birth", "husband.date_of_birth"),
            ("SSN", "husband.ssn"),
            ("Address", "husband.address"),
            ("Phone", "husband.phone"),
            ("Email", "husband.email"),
            ("Employer", "husband.employer"),
        ]:
            tab_husband.add_text_field(label, path)
        notebook.add(tab_husband, text="Husband")
        self._entry_tabs.append(tab_husband)

        # Tab: Wife
        tab_wife = FormTab(notebook, title="Wife")
        for label, path in [
            ("Full Legal Name", "wife.full_legal_name"),
            ("Date of Birth", "wife.date_of_birth"),
            ("SSN", "wife.ssn"),
            ("Address", "wife.address"),
            ("Phone", "wife.phone"),
            ("Email", "wife.email"),
            ("Employer", "wife.employer"),
            ("Maiden Name", "wife.maiden_name"),
        ]:
            tab_wife.add_text_field(label, path)
        notebook.add(tab_wife, text="Wife")
        self._entry_tabs.append(tab_wife)

        # Tab: Elections
        tab_elections = FormTab(notebook, title="Elections")
        tab_elections.add_dropdown_field(
            "Initial Trustee", "elections.initial_trustee",
            options=["both", "husband", "wife"], default="both",
        )
        tab_elections.add_dropdown_field(
            "Property Classification", "elections.property_classification",
            options=["communal", "separate"], default="communal",
        )
        tab_elections.add_dropdown_field(
            "Distribution Standard", "elections.distribution_standard",
            options=["hems", "broad"], default="hems",
        )
        tab_elections.add_dropdown_field(
            "Surviving Amendment", "elections.surviving_amendment",
            options=["full", "limited", "irrevocable"], default="full",
        )
        tab_elections.add_dropdown_field(
            "Power of Appointment", "elections.power_of_appointment",
            options=["general", "limited", "none"], default="general",
        )
        tab_elections.add_dropdown_field(
            "Beneficiary Death", "elections.beneficiary_death",
            options=["per_stirpes_beneficiary", "per_stirpes_grantors", "redistribute"],
            default="per_stirpes_beneficiary",
        )
        tab_elections.add_dropdown_field(
            "Remote Contingent", "elections.remote_contingent",
            options=["intestacy", "charity"], default="intestacy",
        )
        tab_elections.add_text_field("Charity Name", "elections.remote_contingent_charity")
        tab_elections.add_dropdown_field(
            "Dispute Resolution", "elections.dispute_resolution",
            options=["mediation_arbitration", "court"], default="mediation_arbitration",
        )
        tab_elections.add_dropdown_field(
            "Trustee Compensation", "elections.trustee_compensation",
            options=["reasonable", "none"], default="reasonable",
        )
        tab_elections.add_checkbox_field("No-Contest Clause", "elections.no_contest", default=True)
        tab_elections.add_checkbox_field("Spendthrift Protection", "elections.spendthrift", default=True)
        tab_elections.add_checkbox_field("Probate Coordination", "elections.probate_coordination", default=True)
        tab_elections.add_checkbox_field("Portability", "elections.portability", default=True)
        tab_elections.add_checkbox_field("Trustee Bond", "elections.trustee_bond", default=False)
        notebook.add(tab_elections, text="Elections")
        self._entry_tabs.append(tab_elections)

        # Button bar
        ttk.Separator(frame, orient="horizontal").pack(fill=tk.X, pady=5)
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=5)

        ttk.Button(
            btn_frame, text="Back", style="Action.TButton", command=self._show_step0
        ).pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(
            btn_frame, text="Save Draft", style="Action.TButton",
            command=self._save_draft
        ).pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(
            btn_frame, text="Load Draft", style="Action.TButton",
            command=self._load_draft
        ).pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(
            btn_frame, text="Continue to Review",
            style="Big.TButton", command=self._entry_to_review
        ).pack(side=tk.RIGHT)
```

- [ ] **Step 2: Add _entry_to_review, _save_draft, _load_draft methods**

```python
    def _entry_to_review(self) -> None:
        """Collect form data, build TrustData, proceed to review."""
        from trust_generator.ui.forms import flat_to_trust_data

        flat: dict[str, str | bool] = {}
        for tab in self._entry_tabs:
            flat.update(tab.collect())

        try:
            self.data = flat_to_trust_data(flat)
            self.source_path = "(manual entry)"
            self._show_step2()
        except Exception as exc:
            from tkinter import messagebox
            messagebox.showerror("Data Error", f"Could not build trust data:\n\n{exc}")

    def _save_draft(self) -> None:
        """Save current form data as JSON draft."""
        from trust_generator.ui.forms import flat_to_trust_data

        flat: dict[str, str | bool] = {}
        for tab in self._entry_tabs:
            flat.update(tab.collect())

        try:
            td = flat_to_trust_data(flat)
        except Exception as exc:
            from tkinter import messagebox
            messagebox.showerror("Data Error", f"Cannot save: {exc}")
            return

        path = filedialog.asksaveasfilename(
            title="Save Draft",
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json")],
            initialfile="trust_draft.json",
        )
        if not path:
            return
        Path(path).write_text(td.model_dump_json(indent=2), encoding="utf-8")
        messagebox.showinfo("Saved", f"Draft saved to:\n{path}")

    def _load_draft(self) -> None:
        """Load a JSON draft into the form."""
        from trust_generator.ui.forms import trust_data_to_flat

        path = filedialog.askopenfilename(
            title="Load Draft",
            filetypes=[("JSON Files", "*.json")],
        )
        if not path:
            return
        try:
            from trust_generator.parsers import parse_json
            td = parse_json(path)
            flat = trust_data_to_flat(td)
            for tab in self._entry_tabs:
                tab.populate(flat)
            messagebox.showinfo("Loaded", f"Draft loaded from:\n{Path(path).name}")
        except Exception as exc:
            messagebox.showerror("Load Error", f"Failed to load draft:\n\n{exc}")
```

- [ ] **Step 3: Verify GUI launches and shows Step 0**

Run: `python -c "from trust_generator.ui.gui import run_gui; print('import ok')"` (import check only)
Expected: `import ok`

- [ ] **Step 4: Commit**

```bash
git add src/trust_generator/ui/gui.py
git commit -m "feat: add tabbed data entry step with save/load draft to GUI"
```

---

### Task 6: Add CLI create-printable --individual flag

**Files:**
- Modify: `src/trust_generator/ui/cli.py`

- [ ] **Step 1: Add --individual flag to create-printable subcommand**

In `src/trust_generator/ui/cli.py`, in the `_build_parser` function, add to the `create-printable` subparser:

```python
    printable_parser.add_argument(
        "--individual",
        action="store_true",
        help="Generate an individual (single-grantor) questionnaire.",
    )
```

Update `_cmd_create_printable`:

```python
def _cmd_create_printable(args: argparse.Namespace) -> None:
    output_path = Path(args.output)
    trust_type = "individual" if args.individual else "joint"
    log.info("Generating printable questionnaire (%s): %s", trust_type, output_path)
    result_path = generate_printable_questionnaire(output_path, trust_type=trust_type)
    print(_green(f"Printable questionnaire generated: {result_path}"), file=sys.stderr)
```

- [ ] **Step 2: Run CLI tests**

Run: `pytest tests/test_cli.py -v`
Expected: ALL PASS

- [ ] **Step 3: Commit**

```bash
git add src/trust_generator/ui/cli.py
git commit -m "feat: add --individual flag to create-printable CLI command"
```

---

### Task 7: Final integration and full test run

**Files:**
- All modified files

- [ ] **Step 1: Run full test suite**

Run: `pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 2: Run linter**

Run: `ruff check src/ tests/`
Expected: `All checks passed!`

- [ ] **Step 3: Commit any remaining fixes**

```bash
git add -A
git commit -m "chore: final cleanup for data entry GUI feature"
```
