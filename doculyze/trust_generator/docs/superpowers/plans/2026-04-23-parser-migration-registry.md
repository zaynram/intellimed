# Parser Migration — Registry & Public Exports Plan

> **For agentic workers:** Use `spec-pipeline:plan-executor-team` (member of plan-group `2026-04-23-parser-migration`). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire `parse_file` extension-based dispatch (Cycle 8) and update the `v3.parsers` `__init__.py` to the full public API surface (Cycle 9). These two thin cycles stitch together the parser units delivered by siblings `json-and-coercion`, `docx`, and `pdf` into a single callable entry point and a clean importable package surface. No production logic is introduced here beyond dispatch and re-export.

**Architecture:** `registry.py` is a new file containing only `parse_file`. `__init__.py` was created by sibling `json-and-coercion` (during Cycle 1 green phase, per spec §6.2); this plan's Cycle 9 updates it to declare the full `__all__` covering all four public names.

**Tech Stack:** Python ≥3.12, Pydantic v2 (via the `TrustData` type in the dispatch signature), pytest, stdlib `pathlib.Path`.

---

## Plan Metadata (binding, validated by lead against splits.xml)

| Field | Value |
|---|---|
| Plan id | `2026-04-23-parser-migration-registry` |
| Plan-group | `2026-04-23-parser-migration` (plans.xml index 15) |
| Suffix | `registry` |
| Cycles | `[§6.10..§6.11]` (Cycle 8: extension dispatch; Cycle 9: public exports) |
| Depends-on | `docx`, `pdf` |
| Worktree | not-required |
| Blast-radius | `src/trust_generator/v3/parsers/registry.py; src/trust_generator/v3/parsers/__init__.py; tests/v3/parsers/test_registry.py` |
| Spec | `docs/superpowers/specs/2026-04-23-parser-migration-design.md` |
| Splits | `docs/superpowers/specs/2026-04-23-parser-migration-splits.xml` |
| Siblings | `json-and-coercion` (no depends-on — root); `docx` (depends-on=json-and-coercion); `pdf` (depends-on=docx) |

**Discipline notes:**

- Feature branch only — never `main`. Always create a new commit; never `--amend`. Never bypass hooks (`--no-verify`, `--no-gpg-sign`).
- All ad-hoc Python invocation goes through `pixi run python` / `pixi run test` / `pixi run check` (system Python is 3.14; the pixi env pins 3.12 for rule-engine compat).
- `ruff` runs in preview mode targeting py312. RUF022 auto-alphabetizes `__all__` — declare `__all__` entries in sorted order.
- One Red commit + one Green commit per cycle (per `.claude/rules/development-strategy.md`). A Refactor commit is added only when the refactor threshold is met; each cycle below states its threshold verdict explicitly.
- Items surfaced mid-implementation that aren't covered by this plan: open a chore-entry via the `spec-pipeline` scope-maintenance protocol. Do not silently expand the cycle.

---

## `__init__.py` blast-radius overlap note

`src/trust_generator/v3/parsers/__init__.py` appears in both this plan's blast-radius and in sibling `json-and-coercion`'s blast-radius. This is intentional and safe:

- Sibling `json-and-coercion` **creates** `__init__.py` during its Cycle 1 green phase (spec §6.2) with enough structure to satisfy the `parse_json` round-trip test. At that point the file exports only `parse_json`.
- This plan's Cycle 9 **updates** the same file to add `parse_docx`, `parse_pdf`, and `parse_file` to `__all__`, reaching the full §5.2 public surface.
- The transitive depends-on closure (topological order: `json-and-coercion` → `docx` → `pdf` → `registry`) serializes execution: by the time this plan's executor opens `__init__.py`, sibling `json-and-coercion` is fully closed. There is no concurrent-write hazard. Note that `registry` has two direct prerequisites (`docx` and `pdf`, a fan-in); the guarantee that `json-and-coercion` is closed flows transitively through `docx` (which depends on `json-and-coercion` directly), since `pdf` depends on `docx` rather than on `json-and-coercion`.

The `exec-multi-plan` lead should confirm that sibling `json-and-coercion`'s final commit has already closed before dispatching this child.

---

## File structure

```
src/trust_generator/v3/parsers/
├── __init__.py        # MODIFY (Cycle 9): add parse_docx, parse_pdf, parse_file
│                      #   to __all__ (created by json-and-coercion with parse_json only)
├── registry.py        # CREATE (Cycle 8): parse_file extension dispatch
├── docx_parser.py     # NOT TOUCHED (owned by sibling docx)
├── pdf_parser.py      # NOT TOUCHED (owned by sibling pdf)
├── json_parser.py     # NOT TOUCHED (owned by sibling json-and-coercion)
└── coercion.py        # NOT TOUCHED (owned by sibling json-and-coercion)

tests/v3/parsers/
└── test_registry.py   # CREATE (Cycle 8): all registry dispatch tests
```

---

## Out of scope (handed to sibling plans)

This plan owns only §6.10 and §6.11. Everything else is owned by exact-named siblings:

| Sibling suffix | Cycles owned | Scope summary |
|---|---|---|
| `json-and-coercion` | §6.1–§6.4 | JSON parser (`parse_json`, round-trip + error surfaces) and pure coercion helpers (`_to_date`, `_to_decimal`, `_to_address`, `_to_person_reference`) in `coercion.py`. Creates `__init__.py` and `json_parser.py`. |
| `docx` | §6.5–§6.8 | `docx_parser.py` inside-out: smoke (§6.5), asset integration (§6.6), post-promotion contract with combinatorial `trust_type`/`marital_status` mutation tests (§6.7), coercion + post-merge resolution integration (§6.8). |
| `pdf` | §6.9 | `pdf_parser.py`: AcroForm field iteration, `_normalize_field_values` per §5.4.A, reuse of cycle-3 coercion helpers and the `_apply_post_promotion_protocol` helper extracted in §6.6 refactor. |

---

## Cycle 8 — Registry: `parse_file` extension dispatch (spec §6.10)

**Source:** spec §6.10 (lines 690–710), §5.2 (public API shape, lines 177–194).

### Pre-cycle gate

- [ ] Confirm siblings `docx` and `pdf` are closed (their plan-group children are `status="closed"` in `plans.xml`).
- [ ] Run `pixi run test` — expect **green** (all prior parser tests pass before touching registry).

### Red

Create `tests/v3/parsers/test_registry.py` with the following six tests (spec §6.10, lines 697–706). All six run **red** with `ModuleNotFoundError` / `ImportError` because `registry.py` does not exist yet.

```python
# tests/v3/parsers/test_registry.py

def test_parse_file_dispatches_json(tmp_path): ...
def test_parse_file_dispatches_docx(tmp_path, seed_initialized): ...
def test_parse_file_dispatches_pdf(tmp_path, seed_initialized): ...
def test_parse_file_raises_for_unsupported_extension(tmp_path): ...
def test_parse_file_raises_when_seed_required_for_docx(tmp_path):
    """Calling parse_file('foo.docx') without seed_initialized raises ValueError."""

def test_parse_file_ignores_seed_for_json(tmp_path):
    """parse_file('foo.json', seed_initialized=non_None) and
    parse_file('foo.json', seed_initialized=None) produce equal TrustData.

    This is the M2 contract test (spec plan-review pass 1, finding M2; §6.10):
    the equality assertion verifies that seed_initialized is ignored —
    not merely accepted — when the extension is .json.
    The assertion shape (spec §5.2, lines 193–194):
        assert parse_file(json_path, seed_initialized=seed_td) == \
               parse_file(json_path, seed_initialized=None)
    """
```

**Fixture note:** `seed_initialized` can be provided by a module-level or session-scoped pytest fixture that calls `promote_seed(QuestionnaireSeed(...))`. The `tmp_path` fixture constructs minimal valid `.json`, `.docx`, and `.pdf` files as needed (for `.json`, `model_dump_json()` of a minimal `TrustData`; for `.docx` and `.pdf`, use the same construction approach as sibling `docx`'s cycle-4a smoke test).

- [ ] Red commit: `test(registry): red — parse_file dispatch (6 tests, all failing)`

### Green

Create `src/trust_generator/v3/parsers/registry.py`:

```python
# src/trust_generator/v3/parsers/registry.py

from pathlib import Path

from trust_generator.v3.schema import TrustData

_SUPPORTED_EXTENSIONS = {".json", ".docx", ".pdf"}


def parse_file(
    filepath: Path,
    seed_initialized: TrustData | None = None,
) -> TrustData:
    """Dispatch by extension.

    .json  → parse_json(filepath)          (seed_initialized is ignored if provided)
    .docx  → parse_docx(filepath, seed_initialized)  (raises ValueError if absent)
    .pdf   → parse_pdf(filepath, seed_initialized)   (raises ValueError if absent)

    Raises ValueError for unsupported extensions.
    Raises ValueError if seed_initialized is None for .docx or .pdf.
    """
    ...
```

Implementation rules derived from spec §5.2 (lines 177–194):

1. Resolve `.suffix` on the `filepath` argument; lowercase for comparison.
2. `.json` branch: call `parse_json(filepath)` and return. `seed_initialized` is silently ignored regardless of whether it is `None` or non-`None`. (This is the M2 contract property.)
3. `.docx` / `.pdf` branches: if `seed_initialized is None`, raise `ValueError` with a descriptive message naming the extension and stating that `seed_initialized` is required. Otherwise delegate to `parse_docx(filepath, seed_initialized)` or `parse_pdf(filepath, seed_initialized)`.
4. Any other extension: raise `ValueError("Unsupported file extension: ...")`.

- [ ] Green commit: `feat(registry): implement parse_file extension dispatch (§6.10)`

### Refactor verdict

No refactor stage — green output is already minimal. The dispatch function is a single match/if-else over four branches (`.json`, `.docx`, `.pdf`, unsupported); no structural duplication exists; the concerns (extension lookup + guard + delegate) are not orthogonal enough to extract without adding ceremony. Per `refactor_threshold` rule: explicitly noting "no refactor stage — green output is already minimal."

---

## Cycle 9 — Public exports: `v3.parsers` `__init__.py` (spec §6.11)

**Source:** spec §6.11 (lines 712–718), §5.1 module layout (lines 128–136), §5.2 public API (lines 145–188).

### Red

Add a test to `tests/v3/parsers/test_registry.py` (or a new module — either is acceptable; co-locating with `test_registry.py` keeps the public-surface tests together):

```python
def test_public_api_importable():
    """All four names declared in §5.2 are importable from trust_generator.v3.parsers."""
    from trust_generator.v3.parsers import (  # noqa: F401
        parse_docx,
        parse_file,
        parse_json,
        parse_pdf,
    )
```

This test runs **red** if `parse_file` (and any of the other three names) is not yet exported from `__init__.py`.

- [ ] Red commit: `test(parsers): red — public API surface importability (§6.11)`

### Green

Update `src/trust_generator/v3/parsers/__init__.py` to export all four public names from §5.2. The `__all__` list must be **alphabetically sorted** (RUF022 enforcement):

```python
# src/trust_generator/v3/parsers/__init__.py

from trust_generator.v3.parsers.docx_parser import parse_docx
from trust_generator.v3.parsers.json_parser import parse_json
from trust_generator.v3.parsers.pdf_parser import parse_pdf
from trust_generator.v3.parsers.registry import parse_file

__all__ = [
    "parse_docx",
    "parse_file",
    "parse_json",
    "parse_pdf",
]
```

**Public surface rationale (grounded in spec §5.2, lines 145–188):**

| Name | Declared at | Notes |
|---|---|---|
| `parse_docx` | §5.2 signature (line 153) | Fills a seed-initialized `TrustData` from a `.docx` intake artifact |
| `parse_pdf` | §5.2 signature (line 162) | Same contract as `parse_docx` for fillable PDF |
| `parse_json` | §5.2 signature (line 169) | Accepts full v3 TrustData JSON; no seed required |
| `parse_file` | §5.2 signature (line 178) | Dispatcher; delegates to one of the three above |

Coercion helpers (`_to_date`, `_to_decimal`, `_to_address`, `_to_person_reference`) are underscore-prefixed private symbols. They are NOT added to `__all__` — they are consumed internally by `docx_parser.py` and `pdf_parser.py` via direct `coercion` module imports and are not part of the public contract.

- [ ] Green commit: `feat(parsers): update __init__ to full public API surface (§6.11)`

### Refactor verdict

No refactor stage — green output is already minimal. A four-line `__all__` with four corresponding imports has no duplication, no mixed concerns, and no structural improvement available. Per `refactor_threshold` rule: explicitly noting "no refactor stage — green output is already minimal."

---

## Exit criterion

`pixi run test` is **green** across all parser tests (Tier 1 coercion, Tier 2 synthetic, Tier 3 asset-anchored where assets exist) after Cycle 9's green commit. Expected total parser-test count at this point: ~50–70 tests (per spec §8.5).

Confirm with:

```bash
pixi run test test_  # or targeted: pixi run test -- tests/v3/parsers/
```
