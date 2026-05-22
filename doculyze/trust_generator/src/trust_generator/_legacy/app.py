#!/usr/bin/env python3
"""
=============================================================================
FAMILY TRUST GENERATOR
Crosby and Crosby LLP

REQUIREMENTS:
    pip install python-docx

USAGE:
    GUI:   python trust_generator.py
    CLI:   python trust_generator.py -q questionnaire.docx -o output.docx
=============================================================================
"""

import functools
import sys
import os
import json
import argparse
from datetime import datetime
from pathlib import Path
from typing import Literal

try:
    import docx as _
except ImportError:
    print("ERROR: python-docx required. Install: pip install python-docx")
    sys.exit(1)

try:
    from trust_generator import QuestionnaireParser, TrustGenerator
except ImportError:
    sys.path.insert(0, str(Path(__file__).parents[1].absolute()))
    try:
        from trust_generator import QuestionnaireParser, TrustGenerator
    except ImportError:
        sys.path.insert(0, str(Path(__file__).parent.absolute()))
        from parse import QuestionnaireParser # pyright: ignore
        from build import TrustGenerator # pyright: ignore


def run_gui():
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
    except ImportError:
        print("tkinter not available. Use CLI mode:")
        print("  python trust_generator.py -q <questionnaire.docx> -o <output.docx>")
        sys.exit(1)

    class App:
        def __init__(self, root):
            self.root = root
            root.title("Family Trust Generator \u2014 Crosby and Crosby LLP")
            root.geometry("720x520")
            root.resizable(True, True)

            style = ttk.Style()
            style.configure("Title.TLabel", font=("Arial", 16, "bold"))
            style.configure("Sub.TLabel", font=("Arial", 10))
            style.configure("Big.TButton", font=("Arial", 12, "bold"))

            main = ttk.Frame(root, padding=20)
            main.pack(fill=tk.BOTH, expand=True)

            ttk.Label(main, text="Family Trust Generator",
                      style="Title.TLabel").pack(pady=(0,5))
            ttk.Label(main, text="Crosby and Crosby LLP",
                      style="Sub.TLabel").pack(pady=(0,20))
            ttk.Separator(main, orient="horizontal").pack(fill=tk.X, pady=10)

            # Input
            f1 = ttk.LabelFrame(main, text="Step 1: Select Completed Questionnaire",
                                padding=10)
            f1.pack(fill=tk.X, pady=10)
            self.input_var = tk.StringVar()
            ttk.Entry(f1, textvariable=self.input_var, width=60).pack(
                side=tk.LEFT, fill=tk.X, expand=True, padx=(0,10))
            ttk.Button(f1, text="Browse...", command=self._browse_in).pack(side=tk.RIGHT)

            # Output
            f2 = ttk.LabelFrame(main, text="Step 2: Choose Output Location", padding=10)
            f2.pack(fill=tk.X, pady=10)
            self.output_var = tk.StringVar()
            ttk.Entry(f2, textvariable=self.output_var, width=60).pack(
                side=tk.LEFT, fill=tk.X, expand=True, padx=(0,10))
            ttk.Button(f2, text="Browse...", command=self._browse_out).pack(side=tk.RIGHT)

            ttk.Separator(main, orient="horizontal").pack(fill=tk.X, pady=10)

            ttk.Button(main, text="\u2728  Generate Trust Document  \u2728",
                       style="Big.TButton", command=self._generate).pack(pady=20)

            self.status = tk.StringVar(value="Ready. Select a questionnaire to begin.")
            ttk.Label(main, textvariable=self.status,
                      font=("Arial", 10, "italic")).pack(pady=5)
            self.progress = ttk.Progressbar(main, mode="indeterminate", length=400)
            self.progress.pack(pady=5)

            ttk.Separator(main, orient="horizontal").pack(fill=tk.X, pady=10)
            ttk.Label(main, font=("Arial", 9), foreground="gray",
                text="Reads a completed Trust Intake Questionnaire (.docx) and generates\n"
                     "a populated Family Trust. Highlighted sections require attorney review."
            ).pack()

        def _browse_in(self):
            p = filedialog.askopenfilename(
                title="Select Questionnaire",
                filetypes=[("Word Documents", "*.docx"), ("All", "*.*")])
            if p:
                self.input_var.set(p)
                d = os.path.dirname(p)
                self.output_var.set(os.path.join(d,
                    f"Family_Trust_{datetime.now().strftime('%Y%m%d')}.docx"))

        def _browse_out(self):
            p = filedialog.asksaveasfilename(
                title="Save Trust As", defaultextension=".docx",
                filetypes=[("Word Documents", "*.docx")])
            if p:
                self.output_var.set(p)

        def _generate(self):
            inp = self.input_var.get()
            out = self.output_var.get()
            if not inp:
                messagebox.showerror("Error", "Select a questionnaire."); return
            if not out:
                messagebox.showerror("Error", "Choose output location."); return
            if not os.path.exists(inp):
                messagebox.showerror("Error", f"File not found: {inp}"); return

            self.progress.start()
            self.status.set("Parsing questionnaire...")
            self.root.update()

            try:
                data = QuestionnaireParser(inp).parse()
                self.status.set("Generating trust...")
                self.root.update()
                TrustGenerator(data).generate(out)
                self.progress.stop()
                self.status.set(f"Saved: {out}")

                nc = len(data.get("children", []))
                nb = len(data.get("beneficiary_shares", []))
                na = sum(len(data.get(k, [])) for k in
                         ["real_property","financial_accounts","vehicles","valuables"])
                messagebox.showinfo("Success",
                    f"Trust generated!\n\n"
                    f"Grantors: {data.get('husband.full_legal_name','N/A')} & "
                    f"{data.get('wife.full_legal_name','N/A')}\n"
                    f"Children: {nc}\nBeneficiaries: {nb}\nAssets: {na}\n\n"
                    f"Saved: {out}\n\nReview highlighted sections.")
            except Exception as e:
                self.progress.stop()
                self.status.set(f"Error: {e}")
                messagebox.showerror("Error", f"Failed:\n\n{e}")

    root = tk.Tk()
    App(root)
    root.mainloop()


def run_cli(args):
    print("=" * 60)
    print("  FAMILY TRUST GENERATOR")
    print("  Crosby and Crosby LLP")
    print("=" * 60)

    if not os.path.exists(args.questionnaire):
        print(f"ERROR: {args.questionnaire} not found"); sys.exit(1)

    print(f"\nParsing: {args.questionnaire}")
    data = QuestionnaireParser(args.questionnaire).parse()

    print(f"  Husband: {data.get('husband.full_legal_name','N/A')}")
    print(f"  Wife:    {data.get('wife.full_legal_name','N/A')}")
    print(f"  Children: {len(data.get('children',[]))}")
    print(f"  Beneficiaries: {len(data.get('beneficiary_shares',[]))}")
    print(f"  Successors: {len(data.get('successor_trustees',[]))}")
    print(f"  Assets: {sum(len(data.get(k,[])) for k in ['real_property','financial_accounts','vehicles','valuables','insurance_policies','pensions'])}")

    if args.dump_data:
        print("\n--- Parsed Data ---")
        safe = {k: (v if isinstance(v, (list, dict, bool)) else str(v)) for k, v in data.items()}
        print(json.dumps(safe, indent=2, default=str))

    print(f"\nGenerating: {args.output}")
    TrustGenerator(data).generate(args.output)
    print(f"\nSUCCESS: {args.output}")
    print("Review all highlighted 'MANUAL REVIEW' sections.")


def main(mode: Literal["auto", "cli"] = "auto"):
    parser = argparse.ArgumentParser(description="Family Trust Generator")
    parser.add_argument("-q", "--questionnaire", help="Completed questionnaire .docx")
    parser.add_argument("-o", "--output", help="Output trust .docx path")
    parser.add_argument("--dump-data", action="store_true", help="Print parsed data as JSON")
    args = parser.parse_args()

    if args.questionnaire:
        if not args.output:
            base = os.path.splitext(args.questionnaire)[0]
            args.output = f"{base}_TRUST_{datetime.now().strftime('%Y%m%d')}.docx"
        run_cli(args)
    elif mode == "auto":
        run_gui()
    else:
        parser.print_help(sys.stdout)
        sys.exit(2)

if __name__ == "__main__":
    main()
