# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project

**Trust Generator** is a Python tool that automates generation of Family Trust documents for a small estate-planning firm. It accepts client intake data from multiple input formats (.docx, .json, fillable .pdf, GUI), validates it, and produces fully populated trust documents with attorney-review sections highlighted.

Target users: paralegals (run it day-to-day) and attorneys (review output). Clients never interact with the tool.

## Environment

Pixi-managed. After cloning: `pixi install`. The pixi env pins Python 3.12 (rule-engine compat); the maintainer's system Python is 3.14, so any ad-hoc Python invocation must go through `pixi run python` to land in the right interpreter.

Common commands (`pixi run <name>`):

- `trust-generator` — GUI entry point
- `trust-generator-cli <subcommand>` — CLI (subcommands: generate, validate, parse, create-printable, create-fillable-pdf)
- `test [match]` — pytest under the pixi env (cwd `tests/`). Positional `match` defaults to `test_`. Tests marked `@pytest.mark.integration` are skipped by default; run them with `pixi run test -- -m integration`.
- `lint`, `format` — ruff
- `fix`, `fix-unsafe` — ruff autofix (do not invoke during code review; mutates the working tree)
- `mypy [target]` — type check. Positional `target`, e.g. `pixi run mypy v3/diagnostics`.
- `check` — combined gate (lint + mypy + test)
- `build`, `dist`, `bundle` — conda package, Windows .exe, distribution zip
- `ollama-gpu-start` / `ollama-gpu-stop` — swap port 11434 between upstream and IPEX-LLM Ollama (dev-only; see auto-memory)

Pixi tasks accept positional arguments only, applied in declaration order; named-argument syntax (`name=value`) is **not** supported. To forward additional flags to the underlying tool, use `pixi run <task> -- <extra-args>` (everything after `--` is appended verbatim).

Project lint policy: ruff in preview mode targeting py312. RUF022 auto-alphabetizes `__all__` tuples — don't prescribe a non-alphabetic ordering, it won't survive `pixi run fix`. RUF032 autofixes integer-valued `Decimal("n")` to `Decimal(n)` — write integer-form Decimal literals directly to avoid lint thrash.

## Architecture

Schema-centric pipeline (hexagonal): every component connects through the `TrustData` Pydantic model. Parsers produce `TrustData` from input files; validators classify fields and run cross-field rules; the generator emits .docx output.

Production source is `src/trust_generator/v3/`. The canonical schema is `src/trust_generator/v3/schema.py` (`TrustData` and nested models); firm-side configuration is `src/trust_generator/v3/config/firm.py` (`FirmConfig`). All new work targets v3.

`src/trust_generator/v2/` is referential only — excluded from lint/mypy/pytest via `TASK_EXCLUDE='v2'` in the `pixi.toml` activation env. Despite producing the current build artifact, v2 has no active user base and is being fully superseded by v3. Do not edit v2, treat its API as a maintenance target, or propose v2↔v3 signature migrations; it is a same-named ancestor, not a contract to preserve.

## Where context lives

- `docs/superpowers/specs/` — design specs (one per major surface change; preceded by a brainstorm doc when present)
- `docs/superpowers/plans/` — TDD-structured implementation plans (one per spec; cycles map to commits)
- `.claude/context/plans.xml` — index of plans with status (open/closed) and cross-references
- `.claude/context/chores.xml` — outstanding small actionable items, classified as code-chore vs. simple-chore
- `.claude/context/schema/` — XSDs validating the two XML files above
- `.claude/rules/development-strategy.md` — DDD + TDD methodology rules; auto-loaded as project instructions
- Plan/spec/chore execution workflows are owned by the `spec-pipeline` plugin (skill `spec-pipeline:spec-pipeline`; agents `spec-pipeline:plan-executor`, `spec-pipeline:chore-executor`). Invoke through that plugin rather than authoring ad-hoc prompts.

## Conventions

- Tests live in `tests/`, mirroring the `src/trust_generator/` module tree. Fixtures in nearest `conftest.py`.
- TDD discipline per cycle: Red commit → Green commit → optional Refactor commit. Cycle scope is defined in the plan-md.
- Commits land on feature branches, never `main`. Always create a new commit (no `--amend`). Never bypass hooks (`--no-verify`).
- For items raised mid-implementation that aren't covered by the active plan: classify as plan-entry (blocking, scope-significant) or chore-entry (small, isolatable), then add to `plans.xml` or `chores.xml` per the `spec-pipeline` scope-maintenance protocol. Do not silently expand the active plan.
- When project configuration (lint rules, type-checker settings, pixi task definitions, env activation, etc.) creates friction with a desired implementation, raise it as a proposed config change for user review. Do not work around it in code, suppress diagnostics locally, or accept the friction as fixed terrain.
- In any plan-group whose blast-radius includes `pyproject.toml`, the blast-radius implicitly extends to `pixi.toml` and `pixi.lock` for the duration of dep-add cycles (atomic-edit semantics of `pixi add --pypi`). Plans should NOT enumerate `pixi.toml`/`pixi.lock` separately in splits.xml; treat them as transactional mirrors of the pyproject pin.
