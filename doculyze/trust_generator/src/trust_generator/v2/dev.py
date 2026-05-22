"""Entry point for trust-generator-cli (forces CLI mode)."""

from __future__ import annotations


def main() -> None:
    """CLI entry point callable from pyproject.toml console_scripts."""
    from trust_generator.v2.ui import app

    app.main("cli")


if __name__ == "__main__":
    main()
