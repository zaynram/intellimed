"""
Tkinter GUI for Trust Generator.

Multi-step workflow: Import -> Review/Validate -> Generate -> Results.
"""

# ruff: noqa: BLE001
from __future__ import annotations

import logging
import os
import sys
import threading
import tkinter as tk
from collections.abc import Callable
from operator import attrgetter
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from trust_generator.v2.config import AppConfig, load_config
from trust_generator.v2.logging_setup import setup_logging
from trust_generator.v2.schema import TrustData

log = logging.getLogger(__name__)


def _friendly_error(exc: Exception) -> str:
    """Convert an exception into a user-friendly error message."""
    from pydantic import ValidationError

    if isinstance(exc, ValidationError):
        return "Some fields have invalid values. Please check the highlighted fields."
    if isinstance(exc, FileNotFoundError):
        return "The selected file could not be found. Please check the path."
    if isinstance(exc, ValueError):
        return "The file appears to be in an unexpected format."
    if isinstance(exc, PermissionError):
        return "Cannot write to the output location. Please choose a different folder."
    return f"An unexpected error occurred: {exc}"


class TrustGeneratorApp:
    """Main GUI application with a four-step workflow."""

    def __init__(self, root: tk.Tk, config: AppConfig) -> None:
        self.root = root
        self.config = config
        self.data: TrustData | None = None
        self.source_path: str = ""
        self.output_path: str = ""

        # Auto-purge old drafts on startup (best-effort, never blocks app)
        try:
            from trust_generator.v2.ui.drafts import purge_old_drafts

            purge_old_drafts(self.config.drafts.auto_purge_days)
        except Exception:
            log.warning("Auto-purge of old drafts failed on startup", exc_info=True)

        # Window setup
        firm = config.firm.name
        root.title(f"Trust Generator - {firm}")
        root.geometry("900x650")
        root.minsize(700, 500)
        self._center_window()

        # Style
        style = ttk.Style()
        style.configure("Title.TLabel", font=("Segoe UI", 16, "bold"))
        style.configure("Subtitle.TLabel", font=("Segoe UI", 11))
        style.configure("Section.TLabel", font=("Segoe UI", 11, "bold"))
        style.configure("Banner.TLabel", font=("Segoe UI", 10, "bold"), padding=8)
        style.configure(
            "BannerError.TLabel",
            font=("Segoe UI", 10, "bold"),
            background="#ffcccc",
            foreground="#990000",
            padding=8,
        )
        style.configure(
            "BannerWarn.TLabel",
            font=("Segoe UI", 10, "bold"),
            background="#fff3cd",
            foreground="#664d03",
            padding=8,
        )
        style.configure(
            "BannerOk.TLabel",
            font=("Segoe UI", 10, "bold"),
            background="#d1e7dd",
            foreground="#0f5132",
            padding=8,
        )
        style.configure("FindingError.TLabel", foreground="#cc0000")
        style.configure("FindingWarn.TLabel", foreground="#996600")
        style.configure("FindingInfo.TLabel", foreground="#666666")
        style.configure("Big.TButton", font=("Segoe UI", 11, "bold"), padding=6)
        style.configure("Action.TButton", font=("Segoe UI", 10), padding=4)

        # Container that holds all steps
        self.container = ttk.Frame(root)
        self.container.pack(fill=tk.BOTH, expand=True)

        self._show_step0()

    # -----------------------------------------------------------------
    # Pre-review defaults
    # -----------------------------------------------------------------

    def _apply_jurisdiction_defaults(self) -> None:
        """Apply config defaults to empty jurisdiction fields before review."""
        assert self.data is not None
        if not self.data.trust_id.state_of_governing_law:
            self.data.trust_id.state_of_governing_law = (
                self.config.jurisdiction.default_state
            )
        if not self.data.trust_id.county_of_execution:
            self.data.trust_id.county_of_execution = (
                self.config.jurisdiction.default_county
            )
        if not self.data.trust_id.date:
            from datetime import datetime

            self.data.trust_id.date = datetime.now().strftime("%B %d, %Y")  # noqa: DTZ005

    # -----------------------------------------------------------------
    # Utility
    # -----------------------------------------------------------------

    def _center_window(self) -> None:
        self.root.update_idletasks()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.root.geometry(f"+{x}+{y}")

    def _clear_container(self) -> None:
        # Unbind global mouse-wheel handler that may have been set in Step 2
        self.root.unbind_all("<MouseWheel>")
        for child in self.container.winfo_children():
            child.destroy()

    # -----------------------------------------------------------------
    # Step 0: Mode Selection
    # -----------------------------------------------------------------

    def _show_step0(self) -> None:
        """Step 0: Choose mode — Import existing questionnaire or New trust."""
        self._clear_container()
        self.data = None

        frame = ttk.Frame(self.container, padding=40)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Trust Generator", style="Title.TLabel").pack(pady=(0, 2))
        ttk.Label(frame, text=self.config.firm.name, style="Subtitle.TLabel").pack(
            pady=(0, 30)
        )
        ttk.Separator(frame, orient="horizontal").pack(fill=tk.X, pady=10)

        ttk.Label(
            frame,
            text="Choose how to start: import an existing questionnaire, begin a new trust, or continue a saved draft.",
            font=("Segoe UI", 9),
            foreground="gray",
            wraplength=600,
        ).pack(pady=(5, 5))

        ttk.Label(
            frame,
            text="How would you like to begin?",
            font=("Segoe UI", 11),
        ).pack(pady=(10, 30))

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

        ttk.Button(
            btn_frame,
            text="Continue Draft",
            style="Big.TButton",
            command=self._show_draft_picker,
        ).pack(side=tk.LEFT, padx=20)

        ttk.Separator(frame, orient="horizontal").pack(fill=tk.X, pady=(40, 10))
        ttk.Label(
            frame,
            text="Import: Parse a completed .docx, .pdf questionnaire, or .json save. \n"
            "New Trust: Enter client data directly in the application.\n"
            "Continue Draft: Resume a previously saved draft.",
            font=("Segoe UI", 9),
            foreground="gray",
            justify="center",
        ).pack()

    def _show_entry(self) -> None:
        """Step 1a: Manual data entry with tabbed form."""
        self._clear_container()

        from trust_generator.v2.ui.forms import FormTab

        frame = ttk.Frame(self.container, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="New Trust — Data Entry", style="Title.TLabel").pack(
            pady=(0, 5)
        )
        ttk.Label(
            frame,
            text="Enter the client's information below. Required fields are marked with *. Use the tabs to navigate.",
            font=("Segoe UI", 9),
            foreground="gray",
            wraplength=700,
        ).pack(pady=(0, 10))

        # Button bar packed FIRST so it always gets space (Tkinter clips last-packed)
        ttk.Separator(frame, orient="horizontal").pack(
            fill=tk.X, pady=5, side=tk.BOTTOM
        )
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=5, side=tk.BOTTOM)

        ttk.Button(
            btn_frame, text="Back", style="Action.TButton", command=self._show_step0
        ).pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(
            btn_frame,
            text="Save Draft",
            style="Action.TButton",
            command=self._save_draft,
        ).pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(
            btn_frame,
            text="Continue to Review",
            style="Big.TButton",
            command=self._entry_to_review,
        ).pack(side=tk.RIGHT)

        notebook = ttk.Notebook(frame)
        notebook.pack(fill=tk.BOTH, expand=True, pady=5)

        self._entry_tabs: list[FormTab] = []

        # Party label presets
        _LABEL_PRESETS: dict[str, tuple[str, str]] = {
            "Husband / Wife": ("Husband", "Wife"),
            "Wife / Wife": ("Wife", "Wife"),
            "Husband / Husband": ("Husband", "Husband"),
            "Spouse 1 / Spouse 2": ("Spouse 1", "Spouse 2"),
            "Partner 1 / Partner 2": ("Partner 1", "Partner 2"),
            "Custom...": ("", ""),
        }

        # Tab: Trust Info
        tab_trust = FormTab(notebook, title="Trust Info")
        tab_trust.add_dropdown_field(
            "Trust Type",
            "trust_type",
            options=["joint", "individual"],
            default="joint",
        )

        # Party Labels dropdown
        label_var = tk.StringVar(value="Husband / Wife")
        custom_a_var = tk.StringVar(value="Husband")
        custom_b_var = tk.StringVar(value="Wife")

        label_frame = ttk.Frame(tab_trust)
        label_frame.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(label_frame, text="Party Labels", width=20, anchor="w").pack(
            side=tk.LEFT
        )
        label_combo = ttk.Combobox(
            label_frame,
            textvariable=label_var,
            values=list(_LABEL_PRESETS.keys()),
            state="readonly",
            width=25,
        )
        label_combo.pack(side=tk.LEFT, padx=(5, 0))

        # Custom label entry fields (initially hidden)
        custom_frame = ttk.Frame(tab_trust)
        lbl_a_frame = ttk.Frame(custom_frame)
        lbl_a_frame.pack(fill=tk.X, padx=5, pady=1)
        ttk.Label(lbl_a_frame, text="Party A Label", width=20, anchor="w").pack(
            side=tk.LEFT
        )
        ttk.Entry(lbl_a_frame, textvariable=custom_a_var, width=27).pack(
            side=tk.LEFT, padx=(5, 0)
        )
        lbl_b_frame = ttk.Frame(custom_frame)
        lbl_b_frame.pack(fill=tk.X, padx=5, pady=1)
        ttk.Label(lbl_b_frame, text="Party B Label", width=20, anchor="w").pack(
            side=tk.LEFT
        )
        ttk.Entry(lbl_b_frame, textvariable=custom_b_var, width=27).pack(
            side=tk.LEFT, padx=(5, 0)
        )

        # Store references for later data collection
        self._party_label_var = label_var
        self._custom_a_var = custom_a_var
        self._custom_b_var = custom_b_var

        def _on_label_preset_change(_event: object = None) -> None:
            preset = label_var.get()
            if preset == "Custom...":
                custom_frame.pack(fill=tk.X, after=label_frame)
            else:
                custom_frame.pack_forget()
                a, b = _LABEL_PRESETS[preset]
                custom_a_var.set(a)
                custom_b_var.set(b)
            # Update tab titles dynamically
            a_label = custom_a_var.get() or "Party A"
            b_label = custom_b_var.get() or "Party B"
            notebook.tab(tab_party_a_idx, text=a_label)
            notebook.tab(tab_party_b_idx, text=b_label)

        label_combo.bind("<<ComboboxSelected>>", _on_label_preset_change)

        tab_trust.add_text_field("Trust Name", "trust_id.desired_trust_name")
        tab_trust.add_text_field("Trust Date", "trust_id.date")
        tab_trust.add_text_field("State", "trust_id.state_of_governing_law")
        tab_trust.add_text_field("County", "trust_id.county_of_execution")
        tab_trust.add_text_field(
            "Whose SSN for Tax ID", "trust_id.whose_ssn_for_tax_id"
        )
        notebook.add(tab_trust, text="Trust Info")
        self._entry_tabs.append(tab_trust)

        # Tab: Grantor (for individual trusts)
        tab_grantor = FormTab(notebook, title="Grantor")
        for label, path in [
            ("Full Legal Name", "grantor.full_legal_name"),
            ("Date of Birth", "grantor.date_of_birth"),
            ("SSN", "grantor.ssn"),
            ("Address", "grantor.address"),
            ("Phone", "grantor.phone"),
            ("Email", "grantor.email"),
            ("Employer", "grantor.employer"),
        ]:
            tab_grantor.add_text_field(label, path)
        notebook.add(tab_grantor, text="Grantor")
        self._entry_tabs.append(tab_grantor)

        # Tab: Party A
        tab_party_a = FormTab(notebook, title="Husband")
        for label, path in [
            ("Full Legal Name", "party_a.full_legal_name"),
            ("Date of Birth", "party_a.date_of_birth"),
            ("SSN", "party_a.ssn"),
            ("Address", "party_a.address"),
            ("Phone", "party_a.phone"),
            ("Email", "party_a.email"),
            ("Employer", "party_a.employer"),
        ]:
            tab_party_a.add_text_field(label, path)
        notebook.add(tab_party_a, text="Husband")
        self._entry_tabs.append(tab_party_a)
        tab_party_a_idx = notebook.index("end") - 1

        # Tab: Party B
        tab_party_b = FormTab(notebook, title="Wife")
        for label, path in [
            ("Full Legal Name", "party_b.full_legal_name"),
            ("Date of Birth", "party_b.date_of_birth"),
            ("SSN", "party_b.ssn"),
            ("Address", "party_b.address"),
            ("Phone", "party_b.phone"),
            ("Email", "party_b.email"),
            ("Employer", "party_b.employer"),
            ("Maiden Name", "party_b.maiden_name"),
        ]:
            tab_party_b.add_text_field(label, path)
        notebook.add(tab_party_b, text="Wife")
        self._entry_tabs.append(tab_party_b)
        tab_party_b_idx = notebook.index("end") - 1

        # Tab: Elections — grouped with display labels and tooltips
        from trust_generator.v2.ui.forms import (
            ELECTION_DISPLAY,
            ELECTION_TOOLTIPS,
            ToolTip,
            display_options,
        )

        tab_elections = FormTab(notebook, title="Elections")

        def _election_group_header(title: str, desc: str) -> None:
            ttk.Label(
                tab_elections,
                text=title,
                font=("Segoe UI", 10, "bold"),
            ).pack(anchor="w", pady=(10, 0))
            ttk.Label(
                tab_elections,
                text=desc,
                font=("Segoe UI", 8, "italic"),
                foreground="gray",
            ).pack(anchor="w", pady=(0, 4))

        def _add_election_dropdown(
            label: str,
            path: str,
            opts: list[str],
            default: str,
        ) -> None:
            field = tab_elections.add_dropdown_field(
                label,
                path,
                options=display_options(opts),
                default=ELECTION_DISPLAY.get(default, default),
            )
            tip_text = ELECTION_TOOLTIPS.get(path)
            if tip_text:
                ToolTip(field, tip_text)

        def _add_election_checkbox(
            label: str,
            path: str,
            default: bool,
        ) -> None:
            field = tab_elections.add_checkbox_field(label, path, default=default)
            tip_text = ELECTION_TOOLTIPS.get(path)
            if tip_text:
                ToolTip(field, tip_text)

        # -- Trustee Settings --
        _election_group_header(
            "Trustee Settings",
            "Configure who manages the trust and their compensation.",
        )
        _add_election_dropdown(
            "Initial Trustee",
            "elections.initial_trustee",
            ["both", "husband", "wife"],
            "both",
        )
        _add_election_dropdown(
            "Trustee Compensation",
            "elections.trustee_compensation",
            ["reasonable", "none"],
            "reasonable",
        )
        _add_election_checkbox("Trustee Bond", "elections.trustee_bond", default=False)

        # -- Distribution Rules --
        _election_group_header(
            "Distribution Rules",
            "How trust assets are distributed to beneficiaries.",
        )
        _add_election_dropdown(
            "Distribution Standard",
            "elections.distribution_standard",
            ["hems", "broad"],
            "hems",
        )
        _add_election_dropdown(
            "Tangible Distribution",
            "elections.tangible_distribution",
            ["equal_children", "equal_beneficiaries"],
            "equal_children",
        )
        _add_election_dropdown(
            "Division Method",
            "elections.division_method",
            ["trustee", "lottery", "sell"],
            "trustee",
        )
        _add_election_dropdown(
            "Beneficiary Death",
            "elections.beneficiary_death",
            ["per_stirpes_beneficiary", "per_stirpes_grantors", "redistribute"],
            "per_stirpes_beneficiary",
        )
        _add_election_dropdown(
            "Remote Contingent",
            "elections.remote_contingent",
            ["intestacy", "charity"],
            "intestacy",
        )
        f_charity = tab_elections.add_text_field(
            "Charity Name",
            "elections.remote_contingent_charity",
        )
        ToolTip(f_charity, ELECTION_TOOLTIPS["elections.remote_contingent_charity"])

        # -- Surviving Spouse --
        _election_group_header(
            "Surviving Spouse",
            "Rights of the surviving spouse after the first spouse passes.",
        )
        _add_election_dropdown(
            "Surviving Amendment",
            "elections.surviving_amendment",
            ["full", "limited", "irrevocable"],
            "full",
        )
        _add_election_dropdown(
            "Power of Appointment",
            "elections.power_of_appointment",
            ["general", "limited", "none"],
            "general",
        )

        # -- Tax & Legal --
        _election_group_header(
            "Tax & Legal",
            "Tax planning, retirement, and insurance strategies.",
        )
        _add_election_dropdown(
            "Property Classification",
            "elections.property_classification",
            ["communal", "separate"],
            "communal",
        )
        _add_election_dropdown(
            "Retirement Strategy",
            "elections.retirement_strategy",
            ["pod", "trust", "mix"],
            "pod",
        )
        _add_election_dropdown(
            "Insurance Strategy",
            "elections.insurance_strategy",
            ["spouse_then_children"],
            "spouse_then_children",
        )
        _add_election_checkbox("Portability", "elections.portability", default=True)

        # -- Protections --
        _election_group_header(
            "Protections",
            "Clauses that protect the trust and its beneficiaries.",
        )
        _add_election_checkbox(
            "No-Contest Clause",
            "elections.no_contest",
            default=True,
        )
        _add_election_checkbox(
            "Spendthrift Protection",
            "elections.spendthrift",
            default=True,
        )
        _add_election_checkbox(
            "Probate Coordination",
            "elections.probate_coordination",
            default=True,
        )

        # -- Dispute Resolution --
        _add_election_dropdown(
            "Dispute Resolution",
            "elections.dispute_resolution",
            ["mediation_arbitration", "court"],
            "mediation_arbitration",
        )

        notebook.add(tab_elections, text="Elections")
        self._entry_tabs.append(tab_elections)

        # --- List editing tabs ---
        from trust_generator.v2.ui.forms import ListEditor

        # Family tab
        tab_family = ttk.Frame(notebook)
        notebook.add(tab_family, text="Family")
        self._children_editor = ListEditor(
            tab_family,
            [
                ("name", "Name", 25),
                ("dob", "Date of Birth", 12),
                ("relationship", "Relationship", 15),
                ("minor", "Minor?", 6),
            ],
            title="Children",
        )
        self._children_editor.pack(fill="both", expand=True, padx=10, pady=5)

        # Trustees tab
        tab_trustees = ttk.Frame(notebook)
        notebook.add(tab_trustees, text="Trustees")
        self._trustees_editor = ListEditor(
            tab_trustees,
            [
                ("order", "#", 3),
                ("name", "Name", 25),
                ("relationship", "Relationship", 15),
                ("contact", "Contact", 20),
            ],
            title="Successor Trustees",
        )
        self._trustees_editor.pack(fill="both", expand=True, padx=10, pady=5)

        # Beneficiaries tab
        tab_ben = ttk.Frame(notebook)
        notebook.add(tab_ben, text="Beneficiaries")
        self._shares_editor = ListEditor(
            tab_ben,
            [
                ("name", "Name", 20),
                ("relationship", "Relationship", 12),
                ("share", "Share %", 8),
                ("conditions", "Conditions", 20),
            ],
            title="Beneficiary Shares",
        )
        self._shares_editor.pack(fill="x", padx=10, pady=5)
        self._bequests_editor = ListEditor(
            tab_ben,
            [
                ("item", "Item", 30),
                ("recipient", "Recipient", 25),
                ("instructions", "Instructions", 20),
            ],
            title="Specific Bequests",
        )
        self._bequests_editor.pack(fill="x", padx=10, pady=5)

        # Assets tab with sub-tabs
        tab_assets = ttk.Frame(notebook)
        notebook.add(tab_assets, text="Assets")
        assets_nb = ttk.Notebook(tab_assets)
        assets_nb.pack(fill="both", expand=True)

        rp_tab = ttk.Frame(assets_nb)
        assets_nb.add(rp_tab, text="Real Property")
        self._real_property_editor = ListEditor(
            rp_tab,
            [
                ("address", "Address", 30),
                ("value", "Value", 12),
                ("equity", "Equity", 12),
            ],
        )
        self._real_property_editor.pack(fill="both", expand=True, padx=5, pady=5)

        fa_tab = ttk.Frame(assets_nb)
        assets_nb.add(fa_tab, text="Financial")
        self._financial_editor = ListEditor(
            fa_tab,
            [
                ("institution", "Institution", 20),
                ("type", "Type", 15),
                ("value", "Value", 12),
            ],
        )
        self._financial_editor.pack(fill="both", expand=True, padx=5, pady=5)

        v_tab = ttk.Frame(assets_nb)
        assets_nb.add(v_tab, text="Vehicles")
        self._vehicles_editor = ListEditor(
            v_tab,
            [
                ("description", "Description", 30),
                ("vin", "VIN", 20),
                ("value", "Value", 12),
            ],
        )
        self._vehicles_editor.pack(fill="both", expand=True, padx=5, pady=5)

        ins_tab = ttk.Frame(assets_nb)
        assets_nb.add(ins_tab, text="Insurance")
        self._insurance_editor = ListEditor(
            ins_tab,
            [
                ("company", "Company", 20),
                ("policy_number", "Policy #", 15),
                ("benefit", "Benefit", 12),
                ("beneficiary", "Beneficiary", 20),
            ],
        )
        self._insurance_editor.pack(fill="both", expand=True, padx=5, pady=5)

        pen_tab = ttk.Frame(assets_nb)
        assets_nb.add(pen_tab, text="Pensions")
        self._pensions_editor = ListEditor(
            pen_tab,
            [("source", "Source", 25), ("type", "Type", 15), ("value", "Value", 12)],
        )
        self._pensions_editor.pack(fill="both", expand=True, padx=5, pady=5)

        val_tab = ttk.Frame(assets_nb)
        assets_nb.add(val_tab, text="Valuables")
        self._valuables_editor = ListEditor(
            val_tab,
            [("description", "Description", 35), ("value", "Value", 12)],
        )
        self._valuables_editor.pack(fill="both", expand=True, padx=5, pady=5)

    def _show_draft_picker(self) -> None:
        """Show a draft picker dialog listing saved drafts."""
        from trust_generator.v2.ui.drafts import delete_draft, list_drafts, load_draft

        self._clear_container()

        frame = ttk.Frame(self.container, padding=30)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Continue Draft", style="Title.TLabel").pack(pady=(0, 10))
        ttk.Separator(frame, orient="horizontal").pack(fill=tk.X, pady=5)

        drafts = list_drafts()

        if not drafts:
            ttk.Label(
                frame,
                text="No saved drafts found.",
                font=("Segoe UI", 11),
                foreground="gray",
            ).pack(pady=40)
            ttk.Button(
                frame, text="Back", style="Action.TButton", command=self._show_step0
            ).pack()
            return

        # Listbox with draft names and dates
        list_frame = ttk.Frame(frame)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical")
        listbox = tk.Listbox(
            list_frame,
            font=("Segoe UI", 10),
            yscrollcommand=scrollbar.set,
            selectmode=tk.SINGLE,
        )
        scrollbar.config(command=listbox.yview)
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        for d in drafts:
            date_str = d.modified_date.strftime("%Y-%m-%d %H:%M")
            listbox.insert(tk.END, f"{d.display_name}  --  {date_str}")

        if drafts:
            listbox.selection_set(0)

        # Buttons
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=10)

        ttk.Button(
            btn_frame, text="Back", style="Action.TButton", command=self._show_step0
        ).pack(side=tk.LEFT, padx=(0, 10))

        def _open_selected() -> None:
            sel = listbox.curselection()
            if not sel:
                messagebox.showinfo("No Selection", "Please select a draft to open.")
                return
            draft_info = drafts[sel[0]]
            try:
                td = load_draft(draft_info.path)
                self._load_draft_into_entry(td)
            except Exception as exc:
                messagebox.showerror(
                    "Load Error", f"Failed to load draft:\n\n{_friendly_error(exc)}"
                )

        def _delete_selected() -> None:
            sel = listbox.curselection()
            if not sel:
                messagebox.showinfo("No Selection", "Please select a draft to delete.")
                return
            draft_info = drafts[sel[0]]
            confirm = messagebox.askyesno(
                "Delete Draft",
                f"Delete draft '{draft_info.display_name}'?\n\nThis cannot be undone.",
            )
            if confirm:
                delete_draft(draft_info.path)
                self._show_draft_picker()  # refresh

        ttk.Button(
            btn_frame,
            text="Open",
            style="Big.TButton",
            command=_open_selected,
        ).pack(side=tk.RIGHT, padx=(10, 0))

        ttk.Button(
            btn_frame,
            text="Delete",
            style="Action.TButton",
            command=_delete_selected,
        ).pack(side=tk.RIGHT, padx=(10, 0))

    def _load_draft_into_entry(self, td: TrustData) -> None:
        """Show data entry form pre-populated with draft data."""
        self._show_entry()

        from trust_generator.v2.ui.forms import trust_data_to_flat

        flat = trust_data_to_flat(td)
        for tab in self._entry_tabs:
            tab.populate(flat)
        self._populate_list_editors(td)

    def _entry_to_review(self) -> None:
        """Collect form data, build TrustData, proceed to review."""
        from trust_generator.v2.ui.forms import flat_to_trust_data

        flat: dict[str, str | bool] = {}
        for tab in self._entry_tabs:
            flat.update(tab.collect())

        try:
            self.data = flat_to_trust_data(flat)
            self._collect_list_editors(self.data)  # pyright: ignore[reportArgumentType]
            # Apply party labels from the preset dropdown
            self.data.party_a_label = self._custom_a_var.get() or "Husband"  # pyright: ignore[reportOptionalMemberAccess]
            self.data.party_b_label = self._custom_b_var.get() or "Wife"  # pyright: ignore[reportOptionalMemberAccess]
            self.source_path = "(manual entry)"
            self._apply_jurisdiction_defaults()
            self._show_step2()
        except Exception as exc:
            messagebox.showerror(
                "Data Error", f"Could not build trust data:\n\n{_friendly_error(exc)}"
            )

    def _collect_list_editors(self, data: TrustData) -> None:
        """Collect list editor data into TrustData."""
        from trust_generator.v2.schema import (
            BeneficiaryShare,
            Child,
            FinancialAccount,
            InsurancePolicy,
            Pension,
            RealProperty,
            SpecificBequest,
            SuccessorTrustee,
            Valuable,
            Vehicle,
        )

        data.children = [Child(**r) for r in self._children_editor.get_items()]
        data.successor_trustees = [
            SuccessorTrustee(**r) for r in self._trustees_editor.get_items()
        ]
        data.beneficiary_shares = [
            BeneficiaryShare(**r) for r in self._shares_editor.get_items()
        ]
        data.specific_bequests = [
            SpecificBequest(**r) for r in self._bequests_editor.get_items()
        ]
        data.real_property = [
            RealProperty(**r) for r in self._real_property_editor.get_items()
        ]
        data.financial_accounts = [
            FinancialAccount(**r) for r in self._financial_editor.get_items()
        ]
        data.vehicles = [Vehicle(**r) for r in self._vehicles_editor.get_items()]
        data.insurance_policies = [
            InsurancePolicy(**r) for r in self._insurance_editor.get_items()
        ]
        data.pensions = [Pension(**r) for r in self._pensions_editor.get_items()]
        data.valuables = [Valuable(**r) for r in self._valuables_editor.get_items()]

    def _populate_list_editors(self, data: TrustData) -> None:
        """Populate list editors from TrustData."""
        self._children_editor.set_items([c.model_dump() for c in data.children])
        self._trustees_editor.set_items(
            [t.model_dump() for t in data.successor_trustees]
        )
        self._shares_editor.set_items([s.model_dump() for s in data.beneficiary_shares])
        self._bequests_editor.set_items(
            [b.model_dump() for b in data.specific_bequests]
        )
        self._real_property_editor.set_items(
            [r.model_dump() for r in data.real_property]
        )
        self._financial_editor.set_items(
            [f.model_dump() for f in data.financial_accounts]
        )
        self._vehicles_editor.set_items([v.model_dump() for v in data.vehicles])
        self._insurance_editor.set_items(
            [i.model_dump() for i in data.insurance_policies]
        )
        self._pensions_editor.set_items([p.model_dump() for p in data.pensions])
        self._valuables_editor.set_items([v.model_dump() for v in data.valuables])

    def _save_draft(self) -> None:
        """Save current form data as a managed draft (no file dialog)."""
        from trust_generator.v2.ui.drafts import save_draft
        from trust_generator.v2.ui.forms import flat_to_trust_data

        flat: dict[str, str | bool] = {}
        for tab in self._entry_tabs:
            flat.update(tab.collect())

        try:
            td = flat_to_trust_data(flat)
            self._collect_list_editors(td)
        except Exception as exc:
            log.exception("Failed to build trust data for draft save")
            messagebox.showerror("Data Error", f"Cannot save: {_friendly_error(exc)}")
            return

        try:
            path = save_draft(td)
            messagebox.showinfo("Draft Saved", f"Draft saved.\n{path.name}")
        except Exception as exc:
            log.exception("Failed to save draft")
            messagebox.showerror(
                "Save Error", f"Failed to save draft:\n\n{_friendly_error(exc)}"
            )

    # -----------------------------------------------------------------
    # Step 1: Import
    # -----------------------------------------------------------------

    def _show_step1(self) -> None:
        self._clear_container()
        self.data = None

        frame = ttk.Frame(self.container, padding=30)
        frame.pack(fill=tk.BOTH, expand=True)

        # Header
        ttk.Label(frame, text="Trust Generator", style="Title.TLabel").pack(pady=(0, 2))
        ttk.Label(frame, text=self.config.firm.name, style="Subtitle.TLabel").pack(
            pady=(0, 20)
        )
        ttk.Separator(frame, orient="horizontal").pack(fill=tk.X, pady=10)

        # Guidance text
        ttk.Label(
            frame,
            text="Select a completed questionnaire file to import.",
            font=("Segoe UI", 9),
            foreground="gray",
            wraplength=600,
        ).pack(pady=(5, 5))
        # Instructions
        ttk.Label(
            frame,
            text="Select a completed questionnaire (.docx), a form (.pdf), or saved data (.json) to begin.",
            font=("Segoe UI", 10),
        ).pack(pady=(10, 20))

        # File picker row
        picker = ttk.Frame(frame)
        picker.pack(fill=tk.X, pady=10)

        self._file_var = tk.StringVar()
        entry = ttk.Entry(picker, textvariable=self._file_var, width=70)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        ttk.Button(
            picker,
            text="Select Questionnaire...",
            style="Action.TButton",
            command=self._browse_file,
        ).pack(side=tk.RIGHT)

        # Status label
        self._status_var = tk.StringVar(value="No file selected.")
        ttk.Label(
            frame,
            textvariable=self._status_var,
            font=("Segoe UI", 9, "italic"),
            foreground="gray",
        ).pack(pady=(5, 20))

        # Parse button
        ttk.Button(
            frame,
            text="Parse & Continue",
            style="Big.TButton",
            command=self._parse_and_continue,
        ).pack(pady=10)

        # Footer
        ttk.Separator(frame, orient="horizontal").pack(fill=tk.X, pady=(30, 10))
        ttk.Label(
            frame,
            text="Supported formats: .docx (Trust Intake Questionnaire), .json (Saved Form Data), .pdf (Fillable PDF)",
            font=("Segoe UI", 9),
            foreground="gray",
        ).pack()

    def _browse_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Select Questionnaire",
            filetypes=[
                ("Supported files", "*.docx *.json *.pdf"),
                ("Word Documents", "*.docx"),
                ("JSON Files", "*.json"),
                ("PDF Files", "*.pdf"),
                ("All Files", "*.*"),
            ],
        )
        if path:
            self._file_var.set(path)
            self._status_var.set(f"Selected: {Path(path).name}")

    def _parse_and_continue(self) -> None:
        filepath = self._file_var.get().strip()
        if not filepath:
            messagebox.showerror(
                "No file selected", "Please select a questionnaire file first."
            )
            return
        if not Path(filepath).exists():
            messagebox.showerror("File not found", f"File does not exist:\n{filepath}")
            return

        self._status_var.set("Parsing...")
        self.root.update()

        try:
            from trust_generator.v2.parsers import parse_file

            data = parse_file(filepath)
            self.data = data
            self.source_path = filepath
            log.info("Parsed %s successfully", Path(filepath).name)
            self._apply_jurisdiction_defaults()
            self._show_step2()
        except Exception as exc:
            log.exception("Parse failed for %s", filepath)
            self._status_var.set("Parse failed.")
            messagebox.showerror(
                "Parse Error",
                f"Failed to parse the questionnaire:\n\n{_friendly_error(exc)}",
            )

    # -----------------------------------------------------------------
    # Step 2: Review & Validate
    # -----------------------------------------------------------------

    def _show_step2(self) -> None:
        assert self.data is not None
        self._clear_container()

        from trust_generator.v2.validators import Severity, validate

        report = validate(self.data, self.config)

        frame = ttk.Frame(self.container, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)

        # Header
        ttk.Label(frame, text="Review & Validate", style="Title.TLabel").pack(
            pady=(0, 5)
        )
        ttk.Label(
            frame,
            text="Review the information below. Fields marked with [!] have errors that must be fixed.",
            font=("Segoe UI", 9),
            foreground="gray",
            wraplength=700,
        ).pack(pady=(0, 3))
        ttk.Label(
            frame,
            text=f"Source: {Path(self.source_path).name}",
            font=("Segoe UI", 9),
            foreground="gray",
        ).pack(pady=(0, 10))

        # Validation banner
        n_errors = len(report.errors)
        n_warnings = len(report.warnings)
        n_info = len([f for f in report.findings if f.severity == Severity.INFO])

        if n_errors > 0:
            banner_text = f"Cannot generate -- fix {n_errors} required field(s)"
            banner_style = "BannerError.TLabel"
        elif n_warnings > 0:
            banner_text = f"Warnings found ({n_warnings}) -- review before generating"
            banner_style = "BannerWarn.TLabel"
        else:
            banner_text = "All required fields present"
            banner_style = "BannerOk.TLabel"

        ttk.Label(frame, text=banner_text, style=banner_style).pack(
            fill=tk.X, pady=(0, 5)
        )

        # Summary counts
        summary_frame = ttk.Frame(frame)
        summary_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(
            summary_frame,
            text=f"Errors: {n_errors}",
            foreground="#cc0000" if n_errors else "gray",
            font=("Segoe UI", 9, "bold"),
        ).pack(side=tk.LEFT, padx=(0, 15))
        ttk.Label(
            summary_frame,
            text=f"Warnings: {n_warnings}",
            foreground="#996600" if n_warnings else "gray",
            font=("Segoe UI", 9, "bold"),
        ).pack(side=tk.LEFT, padx=(0, 15))
        ttk.Label(
            summary_frame,
            text=f"Info: {n_info}",
            foreground="gray",
            font=("Segoe UI", 9),
        ).pack(side=tk.LEFT)

        ttk.Separator(frame, orient="horizontal").pack(fill=tk.X, pady=5)

        # Scrollable review area
        canvas_frame = ttk.Frame(frame)
        canvas_frame.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(canvas_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        scroll_content = ttk.Frame(canvas)

        scroll_content.bind(
            "<Configure>",
            lambda _: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=scroll_content, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Bind mouse wheel to canvas
        def _on_mousewheel(event: Any) -> None:
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        # Build the findings lookup: field_path -> list of findings
        findings_by_field: dict[str, list[Any]] = {}
        for finding in report.findings:
            findings_by_field.setdefault(finding.field_path, []).append(finding)

        # Populate review sections
        self._add_review_sections(scroll_content, findings_by_field)

        # Findings detail section
        if report.findings:
            ttk.Separator(scroll_content, orient="horizontal").pack(fill=tk.X, pady=10)
            ttk.Label(
                scroll_content, text="Validation Findings", style="Section.TLabel"
            ).pack(anchor="w", pady=(5, 5))
            for finding in report.findings:
                if finding.severity == Severity.ERROR:
                    icon = "[ERROR]"
                    style = "FindingError.TLabel"
                elif finding.severity == Severity.WARNING:
                    icon = "[WARN]"
                    style = "FindingWarn.TLabel"
                else:
                    icon = "[INFO]"
                    style = "FindingInfo.TLabel"
                ttk.Label(
                    scroll_content,
                    text=f"  {icon} {finding.message}",
                    style=style,
                    wraplength=800,
                ).pack(anchor="w", pady=1)

        # Output path selector
        ttk.Separator(frame, orient="horizontal").pack(fill=tk.X, pady=(10, 5))

        output_row = ttk.Frame(frame)
        output_row.pack(fill=tk.X, pady=3)
        ttk.Label(
            output_row,
            text="Output:",
            font=("Segoe UI", 9, "bold"),
        ).pack(side=tk.LEFT)

        # Compute default output path
        from datetime import datetime as _dt

        stamp = _dt.now().strftime("%Y%m%d")  # noqa: DTZ005
        if self.source_path.startswith("("):
            _out_dir = Path.home()
            _out_name = f"Trust_{stamp}.docx"
        else:
            _src = Path(self.source_path)
            _out_dir = _src.parent
            _out_name = f"{_src.stem}_TRUST_{stamp}.docx"
        self._output_path_var = tk.StringVar(value=str(_out_dir / _out_name))

        ttk.Label(
            output_row,
            textvariable=self._output_path_var,
            font=("Segoe UI", 9),
            foreground="#333333",
            wraplength=550,
        ).pack(side=tk.LEFT, padx=(5, 5), fill=tk.X, expand=True)

        ttk.Button(
            output_row,
            text="Change...",
            command=self._choose_output_path,
        ).pack(side=tk.RIGHT)

        # Button bar
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=5)

        ttk.Button(
            btn_frame, text="Back", style="Action.TButton", command=self._show_step0
        ).pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(
            btn_frame,
            text="Save Data as JSON",
            style="Action.TButton",
            command=self._save_json,
        ).pack(side=tk.LEFT, padx=(0, 10))

        can_generate = report.can_generate
        gen_btn = ttk.Button(
            btn_frame,
            text="Generate Trust Document",
            style="Big.TButton",
            command=self._start_generation,
        )
        gen_btn.pack(side=tk.RIGHT)
        if not can_generate:
            gen_btn.state(["disabled"])

        # "Continue in Data Entry" button — saves draft and transitions to entry
        if n_errors > 0:
            ttk.Button(
                btn_frame,
                text="Continue in Data Entry",
                style="Action.TButton",
                command=self._review_to_entry,
            ).pack(side=tk.RIGHT, padx=(0, 10))

    def _choose_output_path(self) -> None:
        """Let the user pick a different output file location."""
        current = self._output_path_var.get()
        path = filedialog.asksaveasfilename(
            title="Choose Output Location",
            defaultextension=".docx",
            filetypes=[("Word Documents", "*.docx"), ("All Files", "*.*")],
            initialfile=Path(current).name,
            initialdir=str(Path(current).parent),
        )
        if path:
            self._output_path_var.set(path)

    def _review_to_entry(self) -> None:
        """Auto-save current data as draft and switch to data entry."""
        assert self.data is not None
        from trust_generator.v2.ui.drafts import save_draft

        try:
            save_draft(self.data)
        except Exception:
            log.warning(
                "Auto-save draft failed during review-to-entry transition",
                exc_info=True,
            )
            messagebox.showwarning(
                "Draft Save Failed",
                "Could not auto-save your current work. You may want to save manually.",
            )
        self._load_draft_into_entry(self.data)

    def _add_review_sections(
        self,
        parent: ttk.Frame,
        findings: dict[str, list[Any]],
    ) -> None:
        """Build the read-only review display organized by section."""
        assert self.data is not None
        d = self.data

        from trust_generator.v2.schema import TrustType

        def get_or_empty(*field_path: str) -> str:
            return d.get_or_default(*field_path, default="(empty)")

        if d.trust_type == TrustType.INDIVIDUAL:
            grantor_section: tuple[str, list[tuple[str, str, str]]] = (
                "Grantor",
                [
                    (
                        "Grantor",
                        get_or_empty("grantor.full_legal_name"),
                        "grantor.full_legal_name",
                    ),
                    ("Trust Type", "Individual", ""),
                ],
            )
        else:
            grantor_section = (
                "Grantors",
                [
                    (
                        "Party A",
                        get_or_empty("party_a.full_legal_name"),
                        "party_a.full_legal_name",
                    ),
                    (
                        "Party B",
                        get_or_empty("party_b.full_legal_name"),
                        "party_b.full_legal_name",
                    ),
                    ("Trust Type", "Joint", ""),
                ],
            )

        def stub_placeholder(
            prop_name: str,
            *,
            stub: str = "(computed)",
            assign: Callable[[], None] | None = None,
        ) -> str:
            if assign:
                assign()
            value: str = attrgetter(prop_name)(d)
            if value != "[MISSING]":  # placeholder check
                return value
            return stub

        from trust_generator.v2.ui.forms import ELECTION_DISPLAY_BY_FIELD

        def _edl(val: str, field_path: str = "") -> str:
            """Election display label: convert enum value to human-readable text."""
            if field_path and field_path in ELECTION_DISPLAY_BY_FIELD:
                return ELECTION_DISPLAY_BY_FIELD[field_path].get(val, val)
            return val

        sections: list[tuple[str, list[tuple[str, str, str]]]] = [
            grantor_section,
            (
                "Trust",
                [
                    (
                        "Trust Name",
                        stub_placeholder("trust_name", stub="(derived from name)"),
                        "trust_id.desired_trust_name",
                    ),
                    (
                        "Date",
                        stub_placeholder("trust_date", stub="(today's date)"),
                        "trust_id.date",
                    ),
                    (
                        "State",
                        stub_placeholder(
                            "state",
                            stub=f"{self.config.jurisdiction.default_state} (default)",
                        ),
                        "trust_id.state_of_governing_law",
                    ),
                    (
                        "County",
                        stub_placeholder(
                            "county",
                            stub=f"{self.config.jurisdiction.default_county} (default)",
                        ),
                        "trust_id.county_of_execution",
                    ),
                ],
            ),
            (
                "Children",
                [
                    ("Count", str(len(d.children)), "children"),
                ]
                + [(f"  Child {i + 1}", c.name, "") for i, c in enumerate(d.children)],
            ),
            (
                "Successor Trustees",
                [
                    ("Count", str(len(d.successor_trustees)), "successor_trustees"),
                ]
                + [(f"  #{s.order}", s.name, "") for s in d.successor_trustees],
            ),
            (
                "Assets",
                [
                    ("Real Property", str(len(d.real_property)), ""),
                    ("Financial Accounts", str(len(d.financial_accounts)), ""),
                    ("Vehicles", str(len(d.vehicles)), ""),
                    ("Insurance Policies", str(len(d.insurance_policies)), ""),
                    ("Pensions", str(len(d.pensions)), ""),
                    ("Valuables", str(len(d.valuables)), ""),
                ],
            ),
            (
                "Beneficiaries",
                [
                    ("Count", str(len(d.beneficiary_shares)), "beneficiary_shares"),
                ]
                + [
                    (f"  {b.name}", f"{b.share}%" if b.share else "(no share)", "")
                    for b in d.beneficiary_shares
                ],
            ),
            (
                "Elections",
                [
                    (
                        "Initial Trustee",
                        _edl(
                            d.elections.initial_trustee.value,
                            "elections.initial_trustee",
                        ),
                        "",
                    ),
                    (
                        "Property Classification",
                        _edl(
                            d.elections.property_classification.value,
                            "elections.property_classification",
                        ),
                        "",
                    ),
                    (
                        "Distribution Standard",
                        _edl(
                            d.elections.distribution_standard.value,
                            "elections.distribution_standard",
                        ),
                        "",
                    ),
                    (
                        "Tangible Distribution",
                        _edl(
                            d.elections.tangible_distribution.value,
                            "elections.tangible_distribution",
                        ),
                        "",
                    ),
                    (
                        "Division Method",
                        _edl(
                            d.elections.division_method.value,
                            "elections.division_method",
                        ),
                        "",
                    ),
                    (
                        "Surviving Amendment",
                        _edl(
                            d.elections.surviving_amendment.value,
                            "elections.surviving_amendment",
                        ),
                        "",
                    ),
                    (
                        "Power of Appointment",
                        _edl(
                            d.elections.power_of_appointment.value,
                            "elections.power_of_appointment",
                        ),
                        "",
                    ),
                    (
                        "Beneficiary Death",
                        _edl(
                            d.elections.beneficiary_death.value,
                            "elections.beneficiary_death",
                        ),
                        "",
                    ),
                    (
                        "Remote Contingent",
                        _edl(
                            d.elections.remote_contingent.value,
                            "elections.remote_contingent",
                        ),
                        "",
                    ),
                    (
                        "Retirement Strategy",
                        _edl(
                            d.elections.retirement_strategy.value,
                            "elections.retirement_strategy",
                        ),
                        "",
                    ),
                    (
                        "Insurance Strategy",
                        _edl(
                            d.elections.insurance_strategy.value,
                            "elections.insurance_strategy",
                        ),
                        "",
                    ),
                    (
                        "Dispute Resolution",
                        _edl(
                            d.elections.dispute_resolution.value,
                            "elections.dispute_resolution",
                        ),
                        "",
                    ),
                    (
                        "Trustee Compensation",
                        _edl(
                            d.elections.trustee_compensation.value,
                            "elections.trustee_compensation",
                        ),
                        "",
                    ),
                    ("No Contest", "Yes" if d.elections.no_contest else "No", ""),
                    ("Spendthrift", "Yes" if d.elections.spendthrift else "No", ""),
                    (
                        "Probate Coordination",
                        "Yes" if d.elections.probate_coordination else "No",
                        "",
                    ),
                    ("Portability", "Yes" if d.elections.portability else "No", ""),
                    ("Trustee Bond", "Yes" if d.elections.trustee_bond else "No", ""),
                ],
            ),
        ]

        from trust_generator.v2.validators import Severity

        for section_title, fields in sections:
            ttk.Label(parent, text=section_title, style="Section.TLabel").pack(
                anchor="w", pady=(10, 3)
            )

            for label, value, field_path in fields:
                row = ttk.Frame(parent)
                row.pack(fill=tk.X, padx=(10, 0), pady=1)

                ttk.Label(
                    row,
                    text=f"{label}:",
                    font=("Segoe UI", 9, "bold"),
                    width=25,
                    anchor="w",
                ).pack(side=tk.LEFT)

                # Check for findings on this field
                field_findings = findings.get(field_path, []) if field_path else []
                has_error = any(f.severity == Severity.ERROR for f in field_findings)
                has_warn = any(f.severity == Severity.WARNING for f in field_findings)

                val_color = "black"
                suffix = ""
                if has_error:
                    val_color = "#cc0000"
                    suffix = " [!]"
                elif has_warn:
                    val_color = "#996600"
                    suffix = " [?]"

                ttk.Label(
                    row,
                    text=f"{value}{suffix}",
                    font=("Segoe UI", 9),
                    foreground=val_color,
                    wraplength=600,
                ).pack(side=tk.LEFT, fill=tk.X, expand=True)

    def _save_json(self) -> None:
        if self.data is None:
            return
        path = filedialog.asksaveasfilename(
            title="Save Parsed Data as JSON",
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")],
            initialfile=f"{Path(self.source_path).stem}_data.json",
        )
        if not path:
            return
        try:
            json_str = self.data.model_dump_json(indent=2)
            Path(path).write_text(json_str, encoding="utf-8")
            log.info("Saved data to %s", path)
            messagebox.showinfo("Saved", f"Data saved to:\n{path}")
        except Exception as exc:
            log.exception("Failed to save JSON")
            messagebox.showerror(
                "Save Error", f"Failed to save:\n\n{_friendly_error(exc)}"
            )

    # -----------------------------------------------------------------
    # Step 3: Generate
    # -----------------------------------------------------------------

    def _start_generation(self) -> None:
        assert self.data is not None
        self._show_step3()

        thread = threading.Thread(target=self._run_generation, daemon=True)
        thread.start()

    def _show_step3(self) -> None:
        self._clear_container()

        frame = ttk.Frame(self.container, padding=40)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Generating", style="Title.TLabel").pack(pady=(40, 10))

        self._gen_status_var = tk.StringVar(value="Generating trust document...")
        ttk.Label(frame, textvariable=self._gen_status_var, font=("Segoe UI", 11)).pack(
            pady=(10, 20)
        )

        self._gen_progress = ttk.Progressbar(frame, mode="indeterminate", length=400)
        self._gen_progress.pack(pady=10)
        self._gen_progress.start(15)

    def _run_generation(self) -> None:
        assert self.data is not None
        try:
            from trust_generator.v2.generators import generate_trust_document

            # Use the output path selected in the review step (if available),
            # otherwise compute a default.
            if hasattr(self, "_output_path_var") and self._output_path_var.get():
                out_path = Path(self._output_path_var.get())
            else:
                from datetime import datetime

                stamp = datetime.now().strftime("%Y%m%d")  # noqa: DTZ005
                if self.source_path.startswith("("):
                    out_dir = Path.home()
                    out_name = f"Trust_{stamp}.docx"
                else:
                    source = Path(self.source_path)
                    out_dir = source.parent
                    out_name = f"{source.stem}_TRUST_{stamp}.docx"
                out_path = out_dir / out_name

            result = generate_trust_document(self.data, out_path, config=self.config)
            self.output_path = result
            log.info("Generation complete: %s", result)
            self.root.after(0, self._show_step4)
        except Exception as exc:
            log.exception("Generation failed")
            self.root.after(0, self._generation_failed, _friendly_error(exc))

    def _generation_failed(self, error_msg: str) -> None:
        messagebox.showerror(
            "Generation Error",
            f"Failed to generate trust document:\n\n{error_msg}",
        )
        self._show_step2()

    # -----------------------------------------------------------------
    # Step 4: Results
    # -----------------------------------------------------------------

    def _show_step4(self) -> None:
        self._clear_container()

        frame = ttk.Frame(self.container, padding=40)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Generation Complete", style="Title.TLabel").pack(
            pady=(40, 10)
        )

        # Guidance text
        ttk.Label(
            frame,
            text="The trust document has been generated. Sections highlighted in red and yellow require attorney review.",
            font=("Segoe UI", 9),
            foreground="gray",
            wraplength=600,
        ).pack(pady=(5, 5))

        # Success icon text
        ttk.Label(
            frame,
            text="Trust document generated successfully.",
            font=("Segoe UI", 12),
            foreground="#0f5132",
        ).pack(pady=(10, 20))

        # Output path
        ttk.Label(frame, text="Output file:", font=("Segoe UI", 9, "bold")).pack(
            anchor="w", padx=40
        )
        ttk.Label(
            frame,
            text=self.output_path,
            font=("Segoe UI", 9),
            foreground="#333333",
            wraplength=750,
        ).pack(anchor="w", padx=40, pady=(0, 5))

        ttk.Label(
            frame,
            text="Review all highlighted 'MANUAL REVIEW' sections before finalizing.",
            font=("Segoe UI", 9, "italic"),
            foreground="#666666",
        ).pack(pady=(5, 30))

        # Buttons
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(pady=10)

        if sys.platform == "win32":
            ttk.Button(
                btn_frame,
                text="Open in Word",
                style="Big.TButton",
                command=self._open_in_word,
            ).pack(side=tk.LEFT, padx=10)

        ttk.Button(
            btn_frame,
            text="Generate Another",
            style="Action.TButton",
            command=self._show_step1,
        ).pack(side=tk.LEFT, padx=10)

        ttk.Button(
            btn_frame,
            text="Exit",
            style="Action.TButton",
            command=self.root.destroy,
        ).pack(side=tk.LEFT, padx=10)

    def _open_in_word(self) -> None:
        try:
            os.startfile(self.output_path)  # type: ignore[attr-defined]
        except Exception as exc:
            log.exception("Failed to open file")
            messagebox.showerror(
                "Error", f"Could not open file:\n\n{_friendly_error(exc)}"
            )


def run_gui() -> None:
    """Entry point for the GUI."""
    setup_logging()
    config = load_config()
    log.info("Starting Trust Generator GUI")

    root = tk.Tk()
    TrustGeneratorApp(root, config)
    root.mainloop()
