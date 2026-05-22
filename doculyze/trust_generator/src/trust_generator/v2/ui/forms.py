"""Reusable Tkinter form widgets for trust data entry.

Each widget is bound to a schema field path (dotted string like
'husband.full_legal_name') and supports get/set for two-way binding.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

from trust_generator.v2.schema import (
    Elections,
    MarriageInfo,
    OfficeInfo,
    PersonInfo,
    TextBlocks,
    TrustData,
    TrustIdentity,
    TrustType,
)

# ---------------------------------------------------------------------------
# ToolTip — hover tooltip for any Tkinter widget
# ---------------------------------------------------------------------------


class ToolTip:
    """Hover tooltip for any Tkinter widget."""

    def __init__(self, widget: tk.Widget, text: str) -> None:
        self._widget = widget
        self._text = text
        self._tip_window: tk.Toplevel | None = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, _event: tk.Event) -> None:  # type: ignore[type-arg]
        x = self._widget.winfo_rootx() + 20
        y = self._widget.winfo_rooty() + self._widget.winfo_height() + 5
        self._tip_window = tw = tk.Toplevel(self._widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tk.Label(
            tw,
            text=self._text,
            justify="left",
            background="#ffffe0",
            relief="solid",
            borderwidth=1,
            font=("Segoe UI", 9),
            wraplength=300,
        ).pack()

    def _hide(self, _event: tk.Event) -> None:  # type: ignore[type-arg]
        if self._tip_window:
            self._tip_window.destroy()
            self._tip_window = None


# ---------------------------------------------------------------------------
# Human-readable election display labels
# ---------------------------------------------------------------------------

# Two-level mapping: field_path -> {enum_value -> display_label}
# Avoids collisions where different enums share the same string value
# (e.g., "limited" in SurvivingAmendment vs PowerOfAppointment)
ELECTION_DISPLAY_BY_FIELD: dict[str, dict[str, str]] = {
    "elections.initial_trustee": {
        "both": "Both parties as co-trustees",
        "husband": "Party A only",
        "wife": "Party B only",
    },
    "elections.distribution_standard": {
        "hems": "Health, Education, Maintenance, Support (HEMS)",
        "broad": "Broad Discretion",
    },
    "elections.beneficiary_death": {
        "per_stirpes_beneficiary": "To beneficiary's descendants (per stirpes)",
        "per_stirpes_grantors": "To grantors' descendants (per stirpes)",
        "redistribute": "Redistribute among remaining beneficiaries",
    },
    "elections.remote_contingent": {
        "intestacy": "Distribute per state intestacy laws",
        "charity": "Donate to charity",
    },
    "elections.surviving_amendment": {
        "full": "Full amendment rights",
        "limited": "Limited amendment rights",
        "irrevocable": "Irrevocable (no changes)",
    },
    "elections.power_of_appointment": {
        "general": "General power of appointment",
        "limited": "Limited power of appointment",
        "none": "No power of appointment",
    },
    "elections.dispute_resolution": {
        "mediation_arbitration": "Mediation then arbitration",
        "court": "Court proceedings",
    },
    "elections.trustee_compensation": {
        "reasonable": "Reasonable compensation",
        "none": "No compensation",
    },
    "elections.property_classification": {
        "communal": "Communal (shared)",
        "separate": "Separate property",
    },
    "elections.tangible_distribution": {
        "equal_children": "Equally among children",
        "equal_beneficiaries": "Equally among beneficiaries",
    },
    "elections.division_method": {
        "trustee": "Trustee decides",
        "lottery": "Lottery / drawing",
        "sell": "Sell and split proceeds",
    },
    "elections.retirement_strategy": {
        "pod": "Payable on Death (POD)",
        "trust": "Through the Trust",
        "mix": "Mixed approach",
    },
    "elections.insurance_strategy": {
        "spouse_then_children": "Spouse then children",
    },
}

# Flat fallback for contexts where field path is unknown
ELECTION_DISPLAY: dict[str, str] = {}
for _field_map in ELECTION_DISPLAY_BY_FIELD.values():
    for _val, _label in _field_map.items():
        ELECTION_DISPLAY.setdefault(_val, _label)

# Reverse mappings
ELECTION_DISPLAY_REVERSE: dict[str, str] = {v: k for k, v in ELECTION_DISPLAY.items()}


def display_options(enum_values: list[str], field_path: str = "") -> list[str]:
    """Convert enum values to display labels, using field-specific mapping if available."""
    if field_path and field_path in ELECTION_DISPLAY_BY_FIELD:
        field_map = ELECTION_DISPLAY_BY_FIELD[field_path]
        return [field_map.get(v, v) for v in enum_values]
    return [ELECTION_DISPLAY.get(v, v) for v in enum_values]


def enum_from_display(display_label: str, field_path: str = "") -> str:
    """Convert a display label back to its enum value."""
    if field_path and field_path in ELECTION_DISPLAY_BY_FIELD:
        reverse = {v: k for k, v in ELECTION_DISPLAY_BY_FIELD[field_path].items()}
        return reverse.get(display_label, display_label)
    return ELECTION_DISPLAY_REVERSE.get(display_label, display_label)


# ---------------------------------------------------------------------------
# Election tooltips
# ---------------------------------------------------------------------------

ELECTION_TOOLTIPS: dict[str, str] = {
    "elections.initial_trustee": (
        "Who manages the trust initially. Most couples choose both as co-trustees."
    ),
    "elections.property_classification": (
        "How assets are owned. Communal means shared equally; "
        "Separate means each spouse's assets are tracked individually."
    ),
    "elections.distribution_standard": (
        "What the trustee can distribute funds for. "
        "HEMS is the standard protective choice."
    ),
    "elections.tangible_distribution": (
        "How tangible personal property (furniture, jewelry, etc.) "
        "is divided among beneficiaries."
    ),
    "elections.division_method": (
        "How to resolve disagreements when dividing tangible property. "
        "Trustee decides is the most common choice."
    ),
    "elections.beneficiary_death": (
        "What happens to a beneficiary's share if they pass away before distribution. "
        "Per stirpes means their descendants inherit."
    ),
    "elections.remote_contingent": (
        "What happens if all named beneficiaries have passed away. "
        "Intestacy follows state law; Charity donates to a named organization."
    ),
    "elections.remote_contingent_charity": (
        "The charity name to receive assets if all beneficiaries predecease. "
        "Only applies when Remote Contingent is set to Charity."
    ),
    "elections.dispute_resolution": (
        "How trust disputes are resolved. Mediation then arbitration avoids court costs."
    ),
    "elections.trustee_compensation": (
        "Whether the trustee receives compensation for managing the trust."
    ),
    "elections.no_contest": (
        "Discourages beneficiaries from challenging the trust in court. "
        "A beneficiary who contests may forfeit their share."
    ),
    "elections.spendthrift": (
        "Prevents creditors from accessing trust assets. Recommended for most trusts."
    ),
    "elections.probate_coordination": (
        "Coordinates trust assets with the probate process to avoid conflicts."
    ),
    "elections.portability": (
        "Allows the surviving spouse to use the deceased spouse's "
        "unused estate tax exemption."
    ),
    "elections.trustee_bond": (
        "Whether the trustee must post a bond. "
        "Usually waived for family trustees to save cost."
    ),
    "elections.surviving_amendment": (
        "What amendment rights the surviving spouse has after the first spouse passes."
    ),
    "elections.power_of_appointment": (
        "Whether the surviving spouse can redirect trust assets to different beneficiaries."
    ),
    "elections.retirement_strategy": (
        "How retirement accounts are handled. POD (Payable on Death) is simplest; "
        "Trust provides more control but may have tax implications."
    ),
    "elections.insurance_strategy": (
        "How life insurance proceeds are distributed. "
        "Spouse then children is the most common choice."
    ),
}


# ---------------------------------------------------------------------------
# Form field widgets
# ---------------------------------------------------------------------------


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
    """Label + Combobox widget bound to an enum field path.

    When *display_map* is provided, the combobox shows human-readable labels
    while ``get_value``/``set_value`` work with the underlying enum values.
    """

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
        # Build a reverse map from display labels to enum values
        self._display_to_enum: dict[str, str] = {}
        self._enum_to_display: dict[str, str] = {}
        for opt in options:
            enum_val = ELECTION_DISPLAY_REVERSE.get(opt, opt)
            self._display_to_enum[opt] = enum_val
            self._enum_to_display[enum_val] = opt

        ttk.Label(self, text=f"{label}:", width=25, anchor="w").pack(
            side=tk.LEFT, padx=(0, 5)
        )
        combo = ttk.Combobox(
            self, textvariable=self._var, values=options, state="readonly", width=40
        )
        combo.pack(side=tk.LEFT)

    def get_value(self) -> str:
        """Return the underlying enum value (not the display label)."""
        display = self._var.get()
        return self._display_to_enum.get(display, display)

    def set_value(self, value: str) -> None:
        """Accept either an enum value or display label."""
        display = self._enum_to_display.get(value, value)
        self._var.set(display)


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

        ttk.Checkbutton(self, text=label, variable=self._var).pack(side=tk.LEFT)

    def get_value(self) -> bool:
        return self._var.get()

    def set_value(self, value: bool) -> None:
        self._var.set(value)


class ListEditor(ttk.Frame):
    """Editable list of items with add/remove rows."""

    def __init__(
        self,
        parent: tk.Widget,
        field_defs: list[tuple[str, str, int]],  # (key, label, width)
        *,
        title: str = "",
    ) -> None:
        super().__init__(parent)
        self._field_defs = field_defs
        self._rows: list[dict[str, ttk.Entry]] = []

        if title:
            ttk.Label(self, text=title, font=("Segoe UI", 10, "bold")).pack(
                anchor="w", pady=(5, 2)
            )

        header = ttk.Frame(self)
        header.pack(fill="x")
        for i, (_, label, width) in enumerate(field_defs):
            ttk.Label(
                header, text=label, width=width, font=("Segoe UI", 9, "bold")
            ).grid(row=0, column=i, padx=2)

        self._rows_frame = ttk.Frame(self)
        self._rows_frame.pack(fill="x")

        add_btn = ttk.Button(self, text="+ Add", command=self._add_row)
        add_btn.pack(anchor="w", pady=4)

    def _add_row(self, values: dict[str, str] | None = None) -> None:
        row_frame = ttk.Frame(self._rows_frame)
        row_frame.pack(fill="x", pady=1)
        entries: dict[str, ttk.Entry] = {}
        for i, (key, _, width) in enumerate(self._field_defs):
            entry = ttk.Entry(row_frame, width=width)
            entry.grid(row=0, column=i, padx=2)
            if values and key in values:
                entry.insert(0, str(values[key]))
            entries[key] = entry
        remove_btn = ttk.Button(
            row_frame,
            text="x",
            width=2,
            command=lambda f=row_frame, e=entries: self._remove_row(f, e),  # type: ignore[misc]
        )
        remove_btn.grid(row=0, column=len(self._field_defs), padx=2)
        self._rows.append(entries)

    def _remove_row(self, frame: ttk.Frame, entries: dict[str, ttk.Entry]) -> None:
        has_data = any(e.get().strip() for e in entries.values())
        if has_data:
            from tkinter import messagebox

            if not messagebox.askyesno("Remove Row", "This row has data. Remove it?"):
                return
        frame.destroy()
        self._rows.remove(entries)

    def get_items(self) -> list[dict[str, str]]:
        """Return list of dicts for all non-empty rows."""
        items: list[dict[str, str]] = []
        for entries in self._rows:
            item = {k: e.get().strip() for k, e in entries.items()}
            if any(item.values()):
                items.append(item)
        return items

    def set_items(self, items: list[dict[str, str]]) -> None:
        """Clear and repopulate from a list of dicts."""
        for row_entries in list(self._rows):
            for entry in row_entries.values():
                entry.master.destroy()  # type: ignore[union-attr]
                break
        self._rows.clear()
        for item in items:
            self._add_row(item)


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
        field = CheckboxField(self, label=label, field_path=field_path, default=default)
        field.pack(fill=tk.X, pady=2)
        self._fields.append(field)
        return field

    def collect(self) -> dict[str, str | bool]:
        """Collect all field values into a flat dict keyed by field_path."""
        return {f.field_path: f.get_value() for f in self._fields}

    def populate(self, data: dict[str, str | bool]) -> None:
        """Populate fields from a flat dict keyed by field_path."""
        for field in self._fields:
            if field.field_path not in data:
                continue
            value = data[field.field_path]
            if isinstance(field, CheckboxField):
                field.set_value(
                    value if isinstance(value, bool) else str(value).lower() == "true"
                )
            else:
                field.set_value(str(value))


# ---------------------------------------------------------------------------
# Sub-models with flat-dict mapping (parent_attr → model class)
# ---------------------------------------------------------------------------

_SCALAR_MODELS: dict[str, type] = {
    "party_a": PersonInfo,
    "party_b": PersonInfo,
    "grantor": PersonInfo,
    "trust_id": TrustIdentity,
    "marriage": MarriageInfo,
    "office": OfficeInfo,
}

# Elections fields that are booleans (vs enum strings)
_BOOL_ELECTIONS = {
    "no_contest",
    "spendthrift",
    "probate_coordination",
    "portability",
    "trustee_bond",
}


def trust_data_to_flat(td: TrustData) -> dict[str, str | bool]:
    """Convert TrustData to a flat {field_path: value} dict for form population.

    Only scalar sub-models are serialized (PersonInfo, TrustIdentity, Elections,
    TextBlocks). List fields (children, assets, beneficiaries) are intentionally
    omitted — the data entry GUI does not yet support list editing.
    """
    flat: dict[str, str | bool] = {}
    flat["trust_type"] = td.trust_type.value

    for parent_name in (
        "party_a",
        "party_b",
        "grantor",
        "trust_id",
        "marriage",
        "office",
    ):
        parent_obj = getattr(td, parent_name)
        for field_name, field_value in parent_obj.model_dump(mode="json").items():
            flat[f"{parent_name}.{field_name}"] = (
                str(field_value) if field_value is not None else ""
            )

    # mode="json" serializes enum fields to their .value strings, not repr
    elections_dump = td.elections.model_dump(mode="json")
    for field_name, field_value in elections_dump.items():
        if field_name in _BOOL_ELECTIONS:
            flat[f"elections.{field_name}"] = bool(field_value)
        elif field_value is not None:
            flat[f"elections.{field_name}"] = str(field_value)

    for field_name, field_value in td.text_blocks.model_dump().items():
        flat[f"text_blocks.{field_name}"] = (
            str(field_value) if field_value is not None else ""
        )

    return flat


def flat_to_trust_data(flat: dict[str, str | bool]) -> TrustData:
    """Convert a flat {field_path: value} dict back to TrustData."""
    kwargs: dict[str, Any] = {}

    trust_type_val = flat.get("trust_type", "joint")
    kwargs["trust_type"] = (
        TrustType(trust_type_val)
        if isinstance(trust_type_val, str)
        else TrustType.JOINT
    )

    for parent_name, model_cls in _SCALAR_MODELS.items():
        prefix = f"{parent_name}."
        parent_data = {
            key[len(prefix) :]: val
            for key, val in flat.items()
            if key.startswith(prefix) and isinstance(val, str) and val
        }
        if parent_data:
            kwargs[parent_name] = model_cls(**parent_data)

    election_data: dict[str, Any] = {}
    for key, val in flat.items():
        if not key.startswith("elections."):
            continue
        field_name = key[len("elections.") :]
        if field_name in _BOOL_ELECTIONS:
            election_data[field_name] = (
                val if isinstance(val, bool) else str(val).lower() == "true"
            )
        else:
            election_data[field_name] = val
    if election_data:
        kwargs["elections"] = Elections(**election_data)

    text_data = {
        key[len("text_blocks.") :]: val
        for key, val in flat.items()
        if key.startswith("text_blocks.") and isinstance(val, str)
    }
    if text_data:
        kwargs["text_blocks"] = TextBlocks(**text_data)

    return TrustData(**kwargs)
