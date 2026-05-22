"""
Command-line interface for trust-generator.

Provides three subcommands:
- generate: parse, validate, and generate a trust document
- validate: parse and validate only
- parse: parse and dump data as JSON or human-readable summary
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from trust_generator.v2.config import AppConfig, load_config
from trust_generator.v2.generators import (
    generate_printable_questionnaire,
    generate_trust_document,
)
from trust_generator.v2.logging_setup import setup_logging
from trust_generator.v2.parsers import parse_file
from trust_generator.v2.schema import TrustData
from trust_generator.v2.validators import Severity, validate
from trust_generator.v2.validators.report import ValidationReport

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Colored output helpers
# ---------------------------------------------------------------------------


def _color(text: str, code: str) -> str:
    """Wrap text in ANSI color code. No-op if not a TTY."""
    if not sys.stderr.isatty():
        return text
    return f"\033[{code}m{text}\033[0m"


def _red(text: str) -> str:
    return _color(text, "31")


def _yellow(text: str) -> str:
    return _color(text, "33")


def _green(text: str) -> str:
    return _color(text, "32")


def _gray(text: str) -> str:
    return _color(text, "90")


# ---------------------------------------------------------------------------
# Validation report formatting
# ---------------------------------------------------------------------------


def _print_validation_report(report: ValidationReport) -> None:
    """Print a colored validation report to stderr."""
    print("=== Validation Report ===", file=sys.stderr)

    for finding in report.findings:
        match finding.severity:
            case Severity.ERROR:
                symbol = _red("\u2717 ERROR")
            case Severity.WARNING:
                symbol = _yellow("\u26a0 WARNING")
            case _:
                symbol = _gray("\u2139 INFO")
        field_tag = f" [{finding.field_path}]" if finding.field_path else ""
        print(f"{symbol}: {finding.message}{field_tag}", file=sys.stderr)

    n_errors = len(report.errors)
    n_warnings = len(report.warnings)
    n_info = len([f for f in report.findings if f.severity == Severity.INFO])
    print(
        f"\nSummary: {n_errors} error(s), {n_warnings} warning(s), {n_info} info",
        file=sys.stderr,
    )

    if not report.can_generate:
        print(_red("Cannot generate: fix errors first."), file=sys.stderr)
    elif n_warnings > 0:
        print(
            _yellow("Warnings present. Review before generating."),
            file=sys.stderr,
        )
    else:
        print(_green("All checks passed."), file=sys.stderr)


# ---------------------------------------------------------------------------
# Human-readable summary
# ---------------------------------------------------------------------------


def _print_summary(data: TrustData) -> None:
    """Print a human-readable summary of parsed TrustData to stdout."""
    from trust_generator.v2.schema import TrustType

    print("=== Trust Data Summary ===")
    print(f"  Trust Type: {data.trust_type.value.title()}")
    if data.trust_type == TrustType.INDIVIDUAL:
        print(f"  Grantor:    {data.grantor.full_legal_name or '(empty)'}")
    else:
        print(f"  Party A:    {data.party_a.full_legal_name or '(empty)'}")
        print(f"  Party B:    {data.party_b.full_legal_name or '(empty)'}")
    print(f"  Trust Name: {data.trust_name}")
    print(f"  Trust Date: {data.trust_date}")
    print(f"  State:      {data.state}")
    print(f"  County:     {data.county}")
    print(f"  Children:   {len(data.children)}")
    print(f"  Successor Trustees: {len(data.successor_trustees)}")
    print(f"  Beneficiary Shares: {len(data.beneficiary_shares)}")
    print()
    print("Assets:")
    for item in data.asset_summary():
        print(f"  - {item}")
    print()
    print("Elections:")
    print(f"  Initial Trustee:     {data.elections.initial_trustee.value}")
    print(f"  Property Class:      {data.elections.property_classification.value}")
    print(f"  Distribution Std:    {data.elections.distribution_standard.value}")
    print(f"  Surviving Amendment: {data.elections.surviving_amendment.value}")
    print(f"  Power of Appt:      {data.elections.power_of_appointment.value}")


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------


def _cmd_generate(args: argparse.Namespace, config: AppConfig) -> None:
    """Handle the 'generate' subcommand."""
    input_path = Path(args.input)
    log.info("Parsing input file: %s", input_path)

    data = parse_file(input_path)

    report = validate(data, config)
    _print_validation_report(report)

    if not report.can_generate:
        if not args.force:
            print(
                _red("Aborting: validation errors. Use --force to override."),
                file=sys.stderr,
            )
            raise SystemExit(1)
        print(
            _yellow("--force: proceeding despite errors."),
            file=sys.stderr,
        )

    if report.warnings and not args.force:
        try:
            answer = input("Warnings found. Continue? [y/N] ")
        except (EOFError, KeyboardInterrupt):
            answer = ""
        if answer.strip().lower() != "y":
            print("Aborted.", file=sys.stderr)
            raise SystemExit(1)

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        date_str = datetime.now().strftime("%Y%m%d")  # noqa: DTZ005
        output_path = input_path.parent / f"{input_path.stem}_TRUST_{date_str}.docx"

    log.info("Generating trust document: %s", output_path)
    result_path = generate_trust_document(
        data, output_path, config=config, force=args.force
    )
    print(_green(f"Trust document generated: {result_path}"), file=sys.stderr)


def _cmd_validate(args: argparse.Namespace, config: AppConfig) -> None:
    """Handle the 'validate' subcommand."""

    input_path = Path(args.input)
    log.info("Parsing input file: %s", input_path)

    data = parse_file(input_path)

    report = validate(data, config)
    _print_validation_report(report)

    if not report.can_generate:
        raise SystemExit(1)


def _cmd_create_printable(args: argparse.Namespace) -> None:
    """Handle the 'create-printable' subcommand."""
    output_path = Path(args.output)
    trust_type = "individual" if args.individual else "joint"
    log.info("Generating printable questionnaire (%s): %s", trust_type, output_path)
    result_path = generate_printable_questionnaire(
        output_path,
        trust_type=trust_type,
        party_a_label="Husband",
        party_b_label="Wife",
    )
    print(_green(f"Printable questionnaire generated: {result_path}"), file=sys.stderr)


def _cmd_create_fillable_pdf(args: argparse.Namespace) -> None:
    """Handle the 'create-fillable-pdf' subcommand."""
    from trust_generator.v2.generators import generate_fillable_pdf

    output_path = Path(args.output)
    trust_type = "individual" if args.individual else "joint"
    log.info("Generating fillable PDF questionnaire (%s): %s", trust_type, output_path)
    result_path = generate_fillable_pdf(output_path, trust_type=trust_type)
    print(
        _green(f"Fillable PDF questionnaire generated: {result_path}"), file=sys.stderr
    )


def _cmd_parse(args: argparse.Namespace) -> None:
    """Handle the 'parse' subcommand."""
    input_path = Path(args.input)
    log.info("Parsing input file: %s", input_path)

    data = parse_file(input_path)

    if args.format == "summary":
        _print_summary(data)
    else:
        json_str = data.model_dump_json(indent=2)
        if args.output:
            output_path = Path(args.output)
            output_path.write_text(json_str, encoding="utf-8")
            print(
                _green(f"JSON written to: {output_path}"),
                file=sys.stderr,
            )
        else:
            print(json_str)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="trust-generator",
        description="Trust document generation tool for Crosby and Crosby LLP.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )

    subparsers = parser.add_subparsers(dest="command")

    # --- generate ---
    gen_parser = subparsers.add_parser(
        "generate",
        help="Parse, validate, and generate a trust document.",
    )
    gen_parser.add_argument(
        "-i",
        "--input",
        required=True,
        help="Path to the intake file (.docx or .json).",
    )
    gen_parser.add_argument(
        "-o",
        "--output",
        help="Output path for the generated .docx (auto-named if omitted).",
    )
    gen_parser.add_argument(
        "--force",
        action="store_true",
        help="Skip confirmation prompts and override validation errors.",
    )

    # --- validate ---
    val_parser = subparsers.add_parser(
        "validate",
        help="Parse and validate an intake file (no generation).",
    )
    val_parser.add_argument(
        "-i",
        "--input",
        required=True,
        help="Path to the intake file (.docx or .json).",
    )

    # --- parse ---
    parse_parser = subparsers.add_parser(
        "parse",
        help="Parse an intake file and dump data.",
    )
    parse_parser.add_argument(
        "-i",
        "--input",
        required=True,
        help="Path to the intake file (.docx or .json).",
    )
    parse_parser.add_argument(
        "--format",
        choices=["json", "summary"],
        default="json",
        help="Output format: json (default) or summary.",
    )
    parse_parser.add_argument(
        "-o",
        "--output",
        help="Write JSON output to a file instead of stdout.",
    )

    # --- create-printable ---
    printable_parser = subparsers.add_parser(
        "create-printable",
        help="Generate a clean, blank printable questionnaire.",
    )
    printable_parser.add_argument(
        "-o",
        "--output",
        default="Trust_Intake_Questionnaire_Clean.docx",
        help="Output path (default: Trust_Intake_Questionnaire_Clean.docx).",
    )
    printable_parser.add_argument(
        "--individual",
        action="store_true",
        help="Generate an individual (single-grantor) questionnaire.",
    )

    # --- create-fillable-pdf ---
    fillable_parser = subparsers.add_parser(
        "create-fillable-pdf",
        help="Generate a fillable PDF questionnaire (scalar fields only).",
    )
    fillable_parser.add_argument(
        "-o",
        "--output",
        default="Trust_Intake_Questionnaire.pdf",
        help="Output path (default: Trust_Intake_Questionnaire.pdf).",
    )
    fillable_parser.add_argument(
        "--individual",
        action="store_true",
        help="Generate an individual (single-grantor) questionnaire.",
    )

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run_cli(args: list[str] | None = None) -> None:
    """CLI entry point. Parses args (or sys.argv) and dispatches."""
    parser = _build_parser()
    parsed = parser.parse_args(args)

    setup_logging(verbose=parsed.verbose)

    if parsed.command is None:
        parser.print_help(sys.stderr)
        raise SystemExit(2)

    if handler := {
        "parse": _cmd_parse,
        "create-printable": _cmd_create_printable,
        "create-fillable-pdf": _cmd_create_fillable_pdf,
    }.get(parsed.command):
        return handler(parsed)

    if handler := {
        "generate": _cmd_generate,
        "validate": _cmd_validate,
    }.get(parsed.command):
        return handler(parsed, load_config())

    parser.print_help(sys.stderr)
    raise SystemExit(2)
