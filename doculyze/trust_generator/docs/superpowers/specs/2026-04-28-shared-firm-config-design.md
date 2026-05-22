# TGv3 Shared firm_config Module Design

| Field             | Value                                                                                                                              |
| ----------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| Spec date         | 2026-04-27                                                                                                                         |
| Status            | Draft                                                                                                                              |
| Supersedes        | n/a (retroactive Tier 1 refactor; postdates `2026-04-22-firm-config` plan)                                                         |
| Relevant entities | `audit_log_persistence`, `diagnostics_enforcement`, `bounded_context_design`, `library_reconnaissance_process`, `estate_thresholds` |
| Out of scope      | `paralegal-onboarding` (roadmap-tracked); diagnostic rule content; firm-config schema key surface; `schema.py` modifications; write-path mechanisms for either source file |

## 1. Motivation

The current `2026-04-21-firm-config-design` loader resolves a single TOML
file from a three-step discovery chain and parses it into `FirmConfig`. The
file carries every section: firm identity, jurisdiction defaults, estate
thresholds, restriction-level policy, audit-log destination, and the
workstation-bound `[user]` table.

This architecture has held through the v3 build-out because there is
currently exactly one workstation running the code (the maintainer's). The
moment a second workstation joins — the first paralegal's machine — the
single-file model breaks in two distinct ways:

1. **The `[user]` table cannot be firm-wide.** Each workstation needs its
   own `upn` value because audit logs path through `users/${user.upn}/logs/`.
   Sharing one file across workstations would either require maintaining
   per-workstation files manually (no canonical source of truth) or
   inventing a workstation-aware substitution layer (substantial loader
   complexity).
2. **Firm-wide policy changes require manual propagation.** When the
   maintainer updates a threshold (for example, after Illinois HB2601 takes
   effect and the single-tier-1 estate hard limit changes), the updated
   value must reach every workstation through some reliable channel.
   Manual file distribution — "send the new config to everyone" — is
   the kind of process that fails silently: someone misses the email,
   someone forgets to apply the update, someone applies a stale version.
   The integrity property the audit trail exists to protect is not
   "every workstation runs the same threshold at the same wall-clock
   instant" (this design does not deliver that, and §2 explicitly rules
   out live-reload), but rather "each audit-log entry records the
   configuration that was effective on that workstation at decision
   time, so the forensic record remains coherent even when workstations
   differ." That property has two halves: (i) a single canonical source
   of truth maintainers can edit reliably, plus per-workstation
   refresh on the next-application-start cadence so drift is bounded
   by restart frequency rather than email-reading attentiveness — both
   delivered by this spec; AND (ii) the audit-log writer must capture
   enough configuration context per decision to forensically
   reconstruct the policy in effect at that decision. Half (ii) is the
   audit-log-persistence module's responsibility; today it captures
   `restriction_level` only (per
   `2026-04-23-diagnostics-engine-design.md` §5.5). Full effective-
   configuration capture (thresholds, jurisdiction, audit-log path
   substitutions) is the subject of §10 chore #5 below — that chore
   must complete before this spec's integrity argument fully holds.
   Manual propagation delivers neither half; the shared/local split
   delivers half (i) and points the way to half (ii).

The shared/local split addresses both problems by separating firm-wide
canonical state (shared, hosted on SharePoint, edited by the maintainer)
from workstation identity and overrides (local, lives on the workstation,
contains essentially `[user]`). SharePoint's existing OneDrive sync
becomes the propagation mechanism for firm-wide changes; per-workstation
identity stays local. The same Pydantic validation pass operates on the
merged result, so the schema and downstream consumers are unchanged.

The design parallels the audit-log-persistence layer's existing convention
(also SharePoint-hosted under the same library root), reusing patterns the
firm has already operationally validated.

## 2. Scope

### In scope

- The merge contract for combining shared and local TOML sources into a
  single dict (§5.3).
- Discovery and path conventions for both source files (§5.2).
- Cache layer for shared-file fallback when SharePoint sync is unavailable
  (§5.4).
- SharePoint permission model documenting the maintainer-vs.-paralegal
  access surface (§5.5).
- Updated public API surface for the loader (§5.6).
- Migration from the current single-file state (§8).
- Amendment content for the firm-config spec documenting this change
  (§9).

### Out of scope (enforced)

The following are deliberate non-goals for this spec. Each has either an
already-tracked future home or an explicit rationale for permanent
exclusion.

- **Onboarding workflow** — the `paralegal-onboarding` plan (roadmap-
  tracked, currently blocked) owns first-time workstation setup, including
  initial local-file materialization at production-conventional paths.
  This spec defers to that plan and provides only the failure-mode hook
  (the onboarding-pointer error from 5.4.5) that onboarding consumes.
- **Diagnostic rule content** — covered by the `diagnostics-engine-design`
  spec; this spec does not modify any rules nor change how rules are
  defined.
- **`FirmConfig` schema key surface** — the schema's set of accepted keys
  is unchanged. Only the load mechanism changes; `schema.py` is not
  modified.
- **Write-path mechanisms for either source file** — the loader is
  read-only for both files. The shared file is edited by the maintainer
  through the SharePoint web UI (or a synced editor). The local file's
  write path is owned by `paralegal-onboarding`. No GUI editor for the
  shared firm-config exists or is currently planned in the roadmap.
- **Live-reload of either source** — `load_firm_config()` reads at call
  time only. There is no polling, no watcher, no scheduled refresh. A
  configuration update on SharePoint takes effect on the next call.

## 3. Reference material

A claude-code session composing the implementation plan from this spec
should load the following before writing any code.

### 3.1 Memory entities

Open via `memory:open_nodes` with the exact name list:

- `audit_log_persistence` — establishes the OneDrive sync convention this
  spec parallels for the shared firm-config path; documents the
  `users/${user.upn}/logs/` subtree that the `firm/config/` subtree mirrors.
- `diagnostics_enforcement` — documents the firm-wide policy surface
  (restriction levels, force-generation audit) that depends on having a
  single firm-wide source of truth for thresholds and policy.
- `bounded_context_design` — frames the v3 module boundaries; the loader
  belongs to the config bounded context and is consumed by every other
  context.
- `library_reconnaissance_process` — documents the recon discipline this
  spec applies in §4; relevant for understanding why no third-party merge
  library is adopted.
- `estate_thresholds` — the canonical example of a shared-file-resident
  policy that benefits from centralized maintenance.

### 3.2 Source files

Read before authoring code:

- `src/trust_generator/v3/config/firm.py` — the current single-source
  loader; this spec extends it. Pay particular attention to
  `_resolve_paths`, `FirmConfigError`, and the existing discovery chain
  shape.
- `src/trust_generator/v3/config/__init__.py` — the module's public
  re-export surface; updates per 5.6.2 land here.
- `config/firm.toml` — the current single TOML; §8 specifies how it
  splits.
- `tests/v3/config/test_firm.py` — the existing test fixture pattern;
  Cycle 6's migration step rewrites it.
- `docs/superpowers/specs/2026-04-21-firm-config-design.md` — the
  predecessor spec; §9 of THIS spec defines the amendment that lands
  in that file.
- `docs/superpowers/specs/2026-04-23-diagnostics-engine-design.md` —
  §12.2 of that spec is the original mention of the shared/local split
  and is the source of the SharePoint sync convention this spec inherits.

### 3.3 External references

- [PEP 680](https://peps.python.org/pep-0680/) — `tomllib` standard
  library module; used for both shared and local file parsing.
- [XDG Base Directory Specification](https://specifications.freedesktop.org/basedir-spec/latest/)
  — governs the POSIX cache path resolution per 5.4.1.
- [Microsoft Learn: SharePoint permission levels](https://learn.microsoft.com/en-us/sharepoint/understanding-permission-levels)
  — reference for the Members vs. Visitors permission groups used in
  5.5.1.
- Pydantic v2 documentation on `field_validator` decorators — referenced
  in 5.3.2 for the future set-like field extension pattern.

## 4. Library reconnaissance

This spec is a Tier 1 retrofit of an existing pure-Python module. Each
subsystem this spec introduces was evaluated against existing-library
options before settling on custom implementation. The recon results:

### 4.1 Deep-merge utility

Candidate libraries:

- **`deepmerge`** (PyPI). Mature, configurable merge strategies, ~3M
  monthly downloads. Supports per-type strategy registration.
- **`mergedeep`** (PyPI). Lighter, fewer features, MIT-licensed.
- **`pydantic`'s `BaseModel.model_copy(update=...)`**. Built-in but
  works on instantiated models, not raw dicts.

Decision: **build custom**. Rationale:

1. The merge contract in 5.3 has spec-specific semantics (empty-as-unset,
   list extension with shared-first ordering) that don't map cleanly onto
   either library's defaults; using either would require a per-strategy
   configuration that ends up roughly the same line count as a custom
   implementation.
2. The merge function fits in ~12 lines of Python; the cost of taking on
   a dependency exceeds the cost of implementation.
3. The custom function is testable as pure code without library-version
   pinning concerns.

The recon outcome is documented as an observation on
`library_reconnaissance_process` per the continuous-refinement discipline.

### 4.2 Atomic file write

Candidate libraries:

- **`atomicwrites`** (PyPI). Cross-platform atomic file replacement.
  Unmaintained since 2022.
- **`portalocker`** (PyPI). Adds advisory locking on top of writes.
  Heavier than needed.
- **stdlib `os.replace`** + tempfile pattern. Always available; the
  documented stdlib idiom for atomic replacement on POSIX and Windows.

Decision: **stdlib**. Rationale:

1. `atomicwrites` is unmaintained and its replacement candidates duplicate
   what `os.replace` already provides correctly on both platforms since
   Python 3.3.
2. The cache write does not need locking; concurrent writers within a
   single process are not a concern (the loader is called serially), and
   cross-process concurrent writes from multiple processes loading config
   simultaneously would each produce a valid result with last-write-wins
   semantics, which matches the spec's contract.
3. No third-party dependency is justified for what is a 4-line idiom.

### 4.3 Cache directory resolution

Candidate libraries:

- **`platformdirs`** (PyPI). Cross-platform user-directory resolution.
  ~50M monthly downloads; well-maintained.
- **`appdirs`** (PyPI). Predecessor of `platformdirs`; deprecated.
- **stdlib + manual platform branching**. What today's `audit_log_dir`
  resolution uses.

Decision: **stdlib + manual platform branching**. Rationale:

1. The cache resolution has exactly two branches (Windows uses
   `LOCALAPPDATA`; POSIX honors `XDG_CACHE_HOME` then falls back to
   `~/.cache`). `platformdirs` would consolidate this into one call but
   adds a dependency for what is roughly 8 lines of `os.environ` checks.
2. The existing v3 code already manages platform branching manually for
   the audit-log path; introducing `platformdirs` here would create
   inconsistency with adjacent code.
3. The behavior of `platformdirs.user_cache_dir("trust-generator")` is
   subtly platform-dependent (it returns `~/Library/Caches/trust-generator`
   on macOS, which the spec hasn't reasoned about). Manual branching
   makes the rules explicit and reviewable.

### 4.4 Recon outcome summary

No third-party libraries adopted. All three subsystems use stdlib only.
This is consistent with the predecessor firm-config spec's posture (also
stdlib-only) and with the v3 module's general preference for explicit,
minimal-dependency code in the configuration boundary.

## 5. Architecture overview

### 5.1 Two-source mental model

At the highest level, the loader composes a single `FirmConfig` from two
physical TOML sources: a **shared file** (firm-wide, hosted on SharePoint,
read-mostly, edited by the maintainer) and a **local file** (per-workstation,
lives on the user's machine, contains the small set of fields that vary
between workstations — today, just `[user]`).

The shared file is the canonical source of firm policy: thresholds, audit-log
paths, jurisdiction defaults, restriction levels. The local file is the
canonical source of workstation identity and any narrow per-workstation
overrides. Neither file is complete on its own; the loader's job is to merge
them into a single dict that satisfies `FirmConfig`'s validation contract.

#### 5.1.1 Load sequence

A typical successful load proceeds in this order:

1. **Resolve paths.** The local-file path is resolved through its discovery
   chain (5.2.1); the shared-file path is resolved through its independent
   discovery chain (5.2.2). Resolution at this step does not check existence
   — it produces concrete `Path` objects ready for IO.
2. **Read shared.** The loader attempts to open and read the shared path's
   bytes. If this fails (file missing, permissions error, IO error), control
   passes to the cache fallback (5.4.3). If the shared file exists but is
   malformed, fail fast — do NOT fall back to the cache (5.4.3 case 3).
3. **Read local.** The local file is opened and read. A missing local file
   is a hard error with no fallback (5.2.1).
4. **Parse both.** Each file's bytes are parsed into a raw `dict[str, Any]`
   via `tomllib.load`. Neither dict is validated against `FirmConfig`
   independently; structural completeness is a property of the merged
   result, not of either input.
5. **Merge.** The shared and local dicts are combined by `deep_merge`
   (5.3) into a single dict. Tables descend recursively; scalars and lists
   follow the rules in 5.3.1 and 5.3.2.
6. **Validate.** `FirmConfig(**merged)` runs the existing Pydantic
   validation pass. Any field-level error surfaces here with Pydantic's
   standard error message naming the offending field.
7. **Cache.** If steps 2 and 6 both succeeded with a non-cache shared
   read, the shared file's verbatim bytes are written to the cache path
   (5.4.2) atomically.
8. **Return.** The validated `FirmConfig` is returned to the caller.

When the cache fallback path is taken at step 2, steps 3–6 still run
normally with the cache's bytes substituting for shared; step 7 is skipped
(the cache is the source for this load); and a `SharedConfigStalenessWarning`
is emitted before the return at step 8.

#### 5.1.2 Boundary clarifications

A few things the design deliberately does NOT do, captured here so the
reader can hold the right mental model when reading 5.2–5.6:

- **No live-reload.** The loader does not poll for changes. A
  configuration update on SharePoint takes effect on the next
  `load_firm_config()` call, which typically means the next application
  start. This matches the existing single-file loader's contract.
- **No write-back.** The loader never writes to either source file. It
  writes only to the cache file, which is workstation-local. Editing
  the shared file is a SharePoint-side action by the maintainer; editing
  the local file is a paralegal-onboarding-side action (Plan 6).
- **No partial validation.** Neither source file is validated against
  `FirmConfig` in isolation. The shared file is structurally incomplete
  (missing `[user]`); validating it alone would always fail. The local
  file is also structurally incomplete (likely missing `[firm]` and
  threshold sections); validating it alone would also fail. Validation
  applies only to the merged dict.
- **No identity-aware behavior.** The loader does not branch on whether
  it is running as the maintainer or a paralegal. It reads what it can
  read; permissions are enforced at the filesystem and SharePoint layers
  (5.5). This keeps the loader testable without mock authentication and
  avoids the maintenance cost of a parallel in-app permission model.
- **No multi-shared composition.** Exactly one shared file. The design
  has no mechanism for layering multiple shared sources (e.g., a
  practice-area-specific shared file overlaying a firm-wide one). If
  that need arises, it is a future spec.

#### 5.1.3 Where the design's complexity lives

Most of this spec is dedicated to two subsystems:

- The **merge contract** (5.3), which has to make precise decisions about
  how lists, empty values, and type mismatches are handled, even though
  none of those cases arise frequently in the current schema. Precision
  here pays compound interest: every future schema field inherits these
  rules without re-litigating them.
- The **cache and fallback layer** (5.4), which has to handle several
  failure modes (sync down, cache missing, cache corrupt, shared
  malformed) with distinct semantics. The complexity is irreducible —
  conflating any two of these modes produces user-facing failures that
  misdirect troubleshooting.

Everything else (discovery, permissions, API surface) is mechanical.

### 5.2 Discovery and path conventions

The loader resolves two file paths before reading anything: the local-file path
and the shared-file path. Each has its own three-step discovery chain. They
are independent of each other; failure or override on one side does not affect
the other.

#### 5.2.1 Local-file discovery chain

The local-file chain extends today's existing single-file chain unchanged:

1. **Explicit argument** — `load_firm_config(local_path=Path("..."), ...)`. Used
   primarily by tests and one-off tooling. Highest precedence.
2. **Environment variable** — `TGV3_FIRM_CONFIG`. Existing variable, existing
   semantics, no rename. Already documented in `2026-04-21-firm-config-design.md`.
3. **Convention** — `<repo>/config/firm.toml`. The repository's existing
   default. Resolved relative to the current working directory at load time.

If none of these resolve to an existing file, the loader raises
`FirmConfigError("local firm.toml not found at <path>")` naming the path that
was attempted at the lowest precedence step that succeeded in resolving (i.e.,
the path that *would* have been read, had it existed).

#### 5.2.2 Shared-file discovery chain

The shared-file chain mirrors the local chain's shape:

1. **Explicit argument** — `load_firm_config(..., shared_path=Path("..."))`.
2. **Environment variable** — `TGV3_FIRM_SHARED_CONFIG`. New variable
   introduced by this spec.
3. **Convention** — the `CONVENTIONAL_SHARED_CONFIG_PATH` module constant
   (see 5.2.3).

When the resolved path does not exist, the loader does NOT immediately raise;
control passes to the cache fallback path described in 5.4. This is the
key behavioral difference from local-file discovery: a missing local file is a
hard error, but a missing shared file is a recoverable condition iff a cached
copy is available.

#### 5.2.3 The `CONVENTIONAL_SHARED_CONFIG_PATH` constant

The loader module exposes a single constant for the production-conventional
shared-file location:

```python
CONVENTIONAL_SHARED_CONFIG_PATH: Final = Path(
    "~/Crosby and Crosby LLP/internal-applications - trust-generator"
    "/firm/config/firm.toml"
)
```

This path is the OneDrive-synced local mount of the SharePoint document
library, expressed as a tilde-prefixed POSIX-style path that
`Path.expanduser()` will resolve correctly on Windows. It parallels the
`audit_log_dir` convention already established by the audit-log persistence
layer (`internal-applications - trust-generator/users/${user.upn}/logs`),
sharing the same library root.

The firm name ("Crosby and Crosby LLP") and library segment
("internal-applications - trust-generator") are firm-specific strings.
They are hardcoded in the loader module — deliberately. The codebase is
not a multi-tenant product; it is a single-firm internal tool. Hardcoding
the firm name is consistent with the audit-log path convention already
baked into in-repo config (`config/firm.toml` declares the same string in
its `audit_log_dir` field). If the codebase ever needs to support a second
firm, this constant becomes the single, locatable site of change.

#### 5.2.4 Path expansion for shared paths

The shared file's path goes through `expanduser()` and `resolve()` only. It
has no `${user.upn}` substitution — the shared file is firm-wide, not
user-scoped. This is a narrower expansion pipeline than the audit-log path
established by amendments A-4 through A-6 to the firm-config spec.

Expansion order:

1. `Path.expanduser()` — resolves leading `~` to the user's home directory.
2. `Path.resolve(strict=False)` — normalizes to an absolute path without
   requiring the file to exist (existence is checked separately, with the
   distinct fallback semantics of 5.2.2).

This applies regardless of which discovery step (1, 2, or 3) produced the
raw path. The explicit-argument and env-var paths are user-supplied strings
that may or may not contain `~`; treating them uniformly with the constant
is simpler than special-casing.

#### 5.2.5 Filename ambiguity

Both files are named `firm.toml`. They are disambiguated by directory
context (`<repo>/config/firm.toml` vs.
`~/Crosby and Crosby LLP/.../firm/config/firm.toml`) and by role-naming in
logs and error messages ("local firm.toml" vs. "shared firm.toml").

Renaming the shared file to `firm.shared.toml` was considered and rejected:
the SharePoint web UI is paralegals' primary interaction surface with the
shared file, and `firm.toml` reads naturally there. The maintainer's
workstation — the only place where both files coexist as locally-mounted
artifacts — is the only context where ambiguity matters, and that context
is adequately served by directory paths and role names. The cost of renaming
(SharePoint UI showing a less natural name) outweighs the benefit
(maintainer's editor tabs disambiguating without contextual reading).

#### 5.2.6 Development-environment paths (WSL)

The maintainer's development environment is Debian under WSL. WSL has no
default OneDrive mount, so `Path.home() / "Crosby and Crosby LLP" / ...`
resolves to `/home/<user>/Crosby and Crosby LLP/...` — a path that does not
exist by default.

Development workflow uses one of:

- **`TGV3_FIRM_SHARED_CONFIG` override** — point the env var at any path
  the WSL session can reach; tests and ad-hoc development sessions use this.
- **Symlink or bind-mount** into the WSL filesystem from the Windows-side
  OneDrive sync directory — not loader concern, but a workable workstation
  setup for matching production behavior in dev.
- **Test fixtures via `tmp_path`** — the existing `test_firm.py` pattern
  generalizes; tests pass `shared_path` explicitly and never touch the
  conventional path.

No loader change is needed to support these. The discovery chain's
explicit-argument and env-var precedence steps already cover them.

#### 5.2.7 Production-deployment paths (deferred)

For non-maintainer workstations — paralegal users running an installed
build rather than a development checkout — the local-file path will not
live in `<repo>/config/firm.toml` because there is no repo. The appropriate
location is platform-conventional state (Windows: `%LOCALAPPDATA%/trust-generator/firm.toml`).

Implementing that requires:

- A platform-aware fallback step in the local-file discovery chain (between
  the env-var step and the repo-relative step).
- An onboarding workflow that materializes the local file at that path on
  first run.

Both are scoped to the `paralegal-onboarding` plan (roadmap-tracked,
currently blocked). This spec deliberately does not introduce that
fallback step. The local-file chain remains repo-relative until Plan 6
lands. The maintainer's workstation is the only target environment in
scope, and it is a development environment.

Noting this constraint here so that Plan 6 inherits a clear seam to extend
rather than a structure to refactor.

### 5.3 Merge contract

The loader reads two TOML files (shared, local), parses each into a raw
`dict[str, Any]` via `tomllib.load`, then produces a single merged dict by
recursive descent. The merged dict is the sole input to `FirmConfig(**merged)`;
neither source is ever validated independently. This subsection specifies the
merge function's behavior precisely enough to drive Cycle 2's tests.

The merge function's signature, conceptually:

```python
def deep_merge(shared: Mapping[str, Any], local: Mapping[str, Any]) -> dict[str, Any]:
    ...
```

It returns a new dict. Inputs are not mutated.

#### 5.3.1 Recursion: tables descend, leaves replace

For each key present in either source:

- Key in shared only → carry shared's value into the result unchanged.
- Key in local only → carry local's value into the result unchanged.
- Key in both, both values are tables (Python dicts) → recurse; the result
  at this key is `deep_merge(shared[k], local[k])`.
- Key in both, both values are lists → EXTEND policy (see 5.3.2).
- Key in both, at least one value is a non-table non-list scalar →
  local's value replaces shared's value verbatim. No type-compatibility check
  is performed at the merge layer (see 5.3.4).

"Table" here means specifically a Python `dict`, which is what `tomllib`
returns for TOML tables. Inline tables are indistinguishable from regular tables
at the parse level; both descend.

#### 5.3.2 List handling: EXTEND, shared-first, verbatim

When a key resolves to a list in both sources, the merged value is
`shared_list + local_list` — shared entries first, local entries appended,
no deduplication.

Rationale for each choice:

- **EXTEND over REPLACE:** the merge framing is "local supplements/refines
  shared"; replacing the entire list whenever local mentions it forces
  per-workstation files to restate the firm's full list to add a single entry,
  which defeats the point of the shared file as canonical state.
- **Shared-first ordering:** for any field where list position carries
  semantic meaning (precedence chains, ordered policies), preserving the firm's
  declared ordering and treating local entries as suffix matches the framing
  above. Local-first would imply "workstation overrides come first", which is
  inconsistent with how scalar overrides work (local replaces, but doesn't
  reorder anything around it).
- **Verbatim concatenation, no deduplication:** the merge function carries no
  per-field type information and cannot know whether a list is set-like
  (dedup-correct) or sequence-like (dedup-lossy). Picking either silently is a
  hidden semantic. Not picking is honest.

##### Future extension for set-like fields

When a future schema field requires set-like semantics (no duplicates,
order-irrelevant), the correct mechanism is a Pydantic field validator on
`FirmConfig`, not a special case in the merge function. Two viable shapes:

```python
# Shape 1: declare the field as a set
allowed_jurisdictions: set[str] = Field(default_factory=set)

# Shape 2: declare as list, dedup in a validator
allowed_jurisdictions: list[str] = Field(default_factory=list)

@field_validator("allowed_jurisdictions")
@classmethod
def _dedup(cls, v: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in v:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
```

Shape 1 is preferred when ordering is irrelevant; shape 2 preserves first-seen
order. Either keeps the merge function's contract simple and pushes
type-specific semantics to the validation layer, where per-field information
actually exists.

##### No-shrink constraint

Under EXTEND, a per-workstation file can ADD list entries but cannot REMOVE
entries that the shared file declares. There is no syntactic mechanism in this
contract for a workstation to express "use a strict subset of shared's list."

No current schema field surfaces this need. Any future field for which a
workstation might legitimately need to shrink the firm's list must either (a)
remain scalar with a different override pattern, or (b) prompt a follow-up
spec introducing escape-hatch syntax (e.g., a `__replace__` wrapper or a
dotted-path subtraction map). Inventing such a mechanism preemptively is
out of scope for this design.

#### 5.3.3 Empty-as-unset semantics

A local-side value that is an empty TOML literal is treated as if the key were
absent. Specifically:

- `key = ""` (empty string) → no-op; shared's value (if any) is preserved.
- `key = []` (empty list) → no-op; equivalent to `shared_list + []`,
  which already collapses to `shared_list` under EXTEND. No special case needed.
- `[section]` declared with no keys (empty table) → no-op; recursion into the
  table finds nothing to merge and leaves shared's table unchanged.

Numeric `0` and boolean `false` are NOT empty — they are values, and they
override shared verbatim per 5.3.1.

##### Bounded-applicability audit

The empty-as-unset rule assumes no current schema field treats the empty
literal as a semantically meaningful value (distinct from "unset"). The
audit below confirms this holds today across every section of `FirmConfig`,
including the external `Address` model imported from
`trust_generator.v3.schema` (which the predecessor audit elided).

Per-field results (every string-typed or path-typed field in the merged
schema as of this spec):

| Section | Field | Type | Default | Empty-literal behavior |
|---|---|---|---|---|
| `meta` | `schema_version` | `str \| None` | `None` | Empty no-ops; if a workstation writes `schema_version = ""` to clear an inherited value, shared's value is preserved. |
| `meta` | `comment` | `str \| None` | `None` | Same as `schema_version`. Free-form string; no behavioral consumer today. |
| `firm` | `name` | `str` | (required, `min_length=1`) | Empty literal would override shared with `""`, then fail Pydantic validation. The rule is a no-op here because validation rejects empty regardless. |
| `firm` | `phone` | `str` | (required, `min_length=1`) | Same as `name`. |
| `firm.office_address` | `street` | `str` | (no default visible from `firm.toml`; treat as required) | Empty literal would no-op under the rule. If the `Address` model permits empty (no `min_length`), this elides an override path; if not, the rule is a no-op. **Implementation note: confirm `Address`'s field constraints during plan composition.** |
| `firm.office_address` | `city`, `state`, `zip_code` | `str` | (same as `street`) | Same as `street`. The `zip_code` field has a US-format validator at the `FirmIdentity` level (see `firm.py:_validate_us_zip_format`); empty literal would no-op before that validator runs. |
| `firm.office_address` | `country` | `str` | `"US"` (per `firm.toml` comment and `firm.py:84`) | **Override-gap candidate**: a workstation cannot use `country = ""` to revert to the Pydantic default `"US"` after shared sets it to a non-default. See "Override-gap with non-empty defaults" below. |
| `jurisdiction` | `default_state` | `str` | `"Illinois"` | **Override-gap candidate** per the same rule. |
| `jurisdiction` | `default_county` | `str` | `"Winnebago"` | **Override-gap candidate**. |
| `jurisdiction` | `trust_code_citation` | `str` | `"Illinois Trust Code (760 ILCS 3/101, et seq.)"` | **Override-gap candidate**. |
| `estate_thresholds` | all fields | `int` / `float` | numeric defaults | Numeric `0` is a value, not empty (per the §5.3.3 base rule); these are not affected. |
| `trustee_catalog` | `db_path` | `Path` | `"./data/trustee_catalog.sqlite"` | **Override-gap candidate** for path-typed fields. Empty string parses to `Path(".")` after `tomllib.loads`; the rule treats `""` as empty pre-merge, so the override-gap form is `db_path = ""` no-ops to shared's value. |
| `trustee_catalog` | `radius_miles`, `refresh_days`, `fdic_request_timeout_s` | `int` | numeric defaults | Same as `estate_thresholds`. |
| `trustee_catalog` | `fdic_api_base` | `HttpUrl` | `"https://banks.data.fdic.gov/api"` | Empty string would fail `HttpUrl` validation; rule no-ops first. |
| `diagnostics` | `default_restriction_level` | `Literal["info","warning","error"]` | `"error"` | Empty string would fail `Literal` validation; rule no-ops first. |
| `diagnostics` | `allow_force_generation` | `bool` | `True` | Booleans are values, not empty. |
| `diagnostics` | `audit_log_dir` | `Path` | `"./logs/audit"` | **Override-gap candidate**. |
| `diagnostics` | `audit_log_rotation` | `Literal["monthly","weekly","daily"]` | `"monthly"` | Same as `default_restriction_level`. |
| `diagnostics` | `rules_dir` | `Path` | `"./config/rules"` | **Override-gap candidate**. |
| `guardianship` | `default_policy` | `Literal[...]` | `"EXPLICIT_DESIGNATIONS"` | Same `Literal` reasoning. |
| `drafts` | `auto_purge_days` | `int` | `90` | Numeric. |
| `user` | `upn` | `str` | (required, `min_length=1`, `str_strip_whitespace=True`) | Empty literal no-ops to shared, but shared has no `[user]` table, so the merged dict ends up with no `user.upn` and Pydantic fails with "field required" — correct error surface. |

##### Override-gap with non-empty defaults

For fields with non-empty Pydantic defaults (the table rows tagged
"Override-gap candidate"), the empty-as-unset rule eliminates the override
path "fall back to the Pydantic default rather than inherit from shared."
Once shared declares a value for such a field, a workstation cannot
syntactically request "use the Pydantic default here" via empty literal —
because empty is treated as absence, which falls through to shared's value
rather than to the Pydantic default.

Concrete example: if shared declares
`jurisdiction.trust_code_citation = "Illinois Trust Code..."` (matching the
firm's actual practice area today), a future Wisconsin-jurisdiction
workstation cannot write `trust_code_citation = ""` in local to mean "use
whatever the Pydantic default would be (which is also Illinois, but the
intent is to disambiguate)." The workaround is for shared to omit the
field entirely (so the Pydantic default applies firm-wide), or for the
workstation to write the explicit desired string in local.

This gap is accepted, not closed. Adding an escape-hatch syntax (e.g., a
sentinel like `__default__` or `__inherit_pydantic__`) would introduce a
parallel value-language readers must learn, and the gap surfaces only in
the narrow scenario where (i) shared sets a non-default value AND (ii) a
specific workstation wants the Pydantic default rather than shared's value
AND (iii) the desired Pydantic-default value differs from shared's value
in a way that matters. None of those conditions are operationally live
today. See appendix D-12 for the rationale.

##### Un-checkable surface: `Meta.extra="allow"`

The `Meta` section uses `model_config = ConfigDict(extra="allow")` per
`firm.py:57`, which is the documented forward-compat seam for future v3.x
schema additions and firm-side annotations. The empty-as-unset rule
applies to fields landing under this seam (they are merged like any other
value), but the audit cannot statically enumerate them — by definition,
the seam exists to admit fields not listed in the model. Any future field
that lands under `[meta]` and uses empty literal as a meaningful value
will silently be elided by the merge; this is an accepted cost of the
forward-compat posture.

Mitigation: when a future field migrates from `[meta]` extra-allow to a
declared schema field, the migration spec must include re-running this
audit for the newly-declared field.

##### Posture for new string fields

Any future schema addition where the empty literal carries meaning AS A
VALUE must either (a) constrain the field with `Field(min_length=1)` to
prevent the ambiguous case from arising at all, or (b) prompt a redesign
of this rule. The `min_length=1` constraint is the recommended posture
for new string fields for this reason, paralleling the constraint already
applied to `User.upn`.

#### 5.3.4 Type mismatches: surface at validation, not at merge

The merge function performs no type-compatibility checking between sources.
If shared has `single_hard = 4_000_000` (int) and a misconfigured local has
`single_hard = "four million"` (str), the merged dict carries the local's
string; Pydantic's existing `FirmConfig` validation raises a `ValidationError`
naming the offending field, with the standard Pydantic error surface preserved.

This is a deliberate division of responsibility:

- The merge layer's job is dict composition, not schema enforcement.
- The validation layer (Pydantic + `FirmConfig`) already names fields and
  produces actionable error messages.
- Adding a pre-merge type-walk would duplicate validation logic and introduce a
  second source of "this field has the wrong type" errors.

A future config-editor GUI may want sharper, source-attributed error messages
("this value came from `firm.toml` line 12; this value came from
`firm.shared.toml` line 5; they disagree on type"). That is a presentation
concern for the editor, not a contract concern for the loader. The editor can
run its own pre-flight diagnostics over both raw dicts before submitting them
to the loader, without changing the loader's behavior.

#### 5.3.5 Top-level section pass-through

If local declares a top-level table that shared lacks (or vice versa), the
merge function passes it through to the merged dict unchanged. Validation of
whether that top-level key is part of the schema is delegated to Pydantic's
`extra="forbid"` model config, which already raises on unknown top-level keys.

The merge layer does not police section identity. This keeps the merge
function schema-agnostic and maintains a single source of truth for
"what keys does `FirmConfig` accept" (the Pydantic model, not the loader).

#### 5.3.6 Determinism and immutability

The merge function is pure: same inputs produce same output, with no
file-system, environment, or time dependencies. Inputs are not mutated; the
function returns a new dict, with new nested dicts at every level where
recursion occurred. This is required for the cache writer (5.4) to safely
serialize the shared dict without worrying about post-merge mutation, and for
testing (Cycle 2) to be straightforward.

#### 5.3.7 Path resolution in two-source mode

The single-source loader's `_resolve_paths` (existing `firm.py:266`)
expands `~`, substitutes `${user.upn}` into `diagnostics.audit_log_dir`,
and absolutizes relative paths anchored at "the config file's parent
directory." With two sources, "the config file's parent" is ambiguous;
this subsection nails down the contract.

##### 5.3.7.1 Anchor for relative-path resolution

Relative paths in the merged config resolve against
`resolved_local.parent` — the directory containing the local TOML file
on the workstation that ran the load.

Rejected alternatives:

- **`resolved_shared.parent`** rejected because OneDrive sync roots vary
  per workstation. A relative path like `./logs` evaluated against the
  shared file's parent would resolve to a different directory on each
  paralegal's machine, and the resulting absolute path would refer to a
  location inside the OneDrive-synced library — exactly the opposite of
  the workstation-local intent for fields like `audit_log_dir`. Worse,
  it would silently differ on the maintainer's WSL development
  environment where there is no OneDrive mount at all.
- **Forbid all relative paths** rejected as too strict. Local-side
  relative paths work today and the existing `test_relative_paths_*`
  fixtures depend on them. Forcing every workstation to spell paths
  absolutely creates onboarding friction for no integrity gain in the
  local-only case.

The anchor choice (local-side) preserves today's local-relative behavior
exactly. The shared-side prohibition (5.3.7.3) closes the cross-workstation
ambiguity that motivates this subsection.

##### 5.3.7.2 `${user.upn}` substitution timing

The `${user.upn}` sentinel is substituted ONLY into
`diagnostics.audit_log_dir`, matching the current single-source contract
(amendment A-6 to the firm-config spec, `firm.py:268-274`). The shared
file may declare the sentinel; the substitution runs after merge,
against the merged dict's `user.upn` value (which always comes from
local since shared has no `[user]` table).

The substitution sequence per `_resolve_paths`:

1. **Substitute `${user.upn}`** in `diagnostics.audit_log_dir` against
   the validated `user.upn` value.
2. **`expanduser()`** every Path-typed field's value, expanding leading
   `~` to `Path.home()`.
3. **Absolutize** every Path-typed field's value: if the result of
   step 2 is absolute, take it as-is; otherwise resolve against
   `resolved_local.parent`.

This is the existing single-source order, unchanged. The two-source
change is only the anchor identity (now explicitly "the local file's
parent") and the addition of the shared-side prohibition.

##### 5.3.7.3 Shared-side relative-path prohibition

Shared-side TOML must not declare relative paths for any Path-typed
field. The prohibition applies to fields the schema declares as
`Path`-typed and to the cross-field-validated audit-log path:

- `trustee_catalog.db_path`
- `diagnostics.audit_log_dir`
- `diagnostics.rules_dir`

A shared-side value that is neither absolute (`/...` or `C:\...`) nor
tilde-prefixed (`~/...` or `~user/...`) is rejected with
`FirmConfigError("shared firm.toml field <dotted.key> must be absolute "
"or tilde-prefixed; got <value>. Relative paths in shared have
ambiguous semantics across workstations and are not permitted.")`.

The prohibition applies only to the shared source. Local-side relative
paths remain supported (5.3.7.1).

##### 5.3.7.4 Validator implementation choice

Two implementation shapes were considered:

1. **Pre-merge validator** that walks `shared_dict` against a
   loader-internal allowlist of dotted Path keys before calling
   `deep_merge`. Pros: source-attributed by construction; runs before
   any merging. Cons: duplicates the schema's knowledge of which fields
   are Path-typed; would drift if a future schema addition adds a new
   Path field and the allowlist is not updated.
2. **Post-merge `model_validator(mode="before")`** on `FirmConfig` that
   inspects merge-provenance metadata. Cons: requires threading
   provenance metadata through `deep_merge`, which contradicts the
   merge function's purity (5.3.6) and adds an information-flow
   dependency that doesn't exist today.

Decision: **shape 1 (pre-merge validator)** is preferred for spec
authority. The drift risk is mitigated by deriving the allowlist
introspectively from `FirmConfig`'s field annotations (any field whose
annotation is `Path` or `Path | None` qualifies) rather than maintaining
a hardcoded list. Cycle 6's green phase implements this introspective
walk.

The implementation skeleton for the validator:

```python
def _validate_shared_paths_absolute(
    shared_dict: dict[str, Any],
    schema: type[BaseModel] = FirmConfig,
) -> None:
    """Raise FirmConfigError if shared_dict contains relative Path values."""
    for dotted_key in _enumerate_path_fields(schema):
        value = _get_dotted(shared_dict, dotted_key)
        if value is None:
            continue
        if not (
            value.startswith("/")
            or value.startswith("~")
            or _is_windows_absolute(value)
        ):
            raise FirmConfigError(
                f"shared firm.toml field {dotted_key} must be absolute or "
                f"tilde-prefixed; got {value!r}. Relative paths in "
                f"shared have ambiguous semantics across workstations "
                f"and are not permitted."
            )
```

##### 5.3.7.5 Recursion semantics for `_enumerate_path_fields`

Plan-review (round 2) flagged that the introspective walker MUST
recurse into nested sub-models, because every `Path`-typed field
in the current schema lives on a sub-model (`TrusteeCatalog.db_path`,
`Diagnostics.audit_log_dir`, `Diagnostics.rules_dir`) — a naive
shallow walker over `FirmConfig.model_fields` would yield ZERO
matches and silently leave the shared-side prohibition unenforced.

Recursion semantics, pinned:

```python
def _enumerate_path_fields(
    schema: type[BaseModel],
    prefix: str = "",
) -> Iterator[str]:
    """Yield dotted keys for every Path-typed field in `schema`,
    recursing into BaseModel-typed sub-models.

    Handles annotations of shape:
      - `Path` (qualifies; yield the dotted key)
      - `Path | None` and `Optional[Path]` (qualifies; yield the
        dotted key)
      - `BaseModel` subclass (recurse with prefix)
      - `BaseModel | None` and `Optional[<BaseModel>]` (recurse)
      - Anything else (skip)

    Lists, dicts, and other parameterized container types are NOT
    recursed into. If a future schema field's annotation is
    `list[Path]` or similar, this walker will skip it; that
    schema addition must trigger a re-audit and a walker update.
    """
    for field_name, field_info in schema.model_fields.items():
        annotation = field_info.annotation
        # Strip Optional / Union[..., None]
        non_none_types = _unwrap_optional(annotation)
        for t in non_none_types:
            if t is Path:
                yield f"{prefix}{field_name}"
            elif isinstance(t, type) and issubclass(t, BaseModel):
                yield from _enumerate_path_fields(
                    t, prefix=f"{prefix}{field_name}."
                )
```

`_unwrap_optional(annotation)` is a one-line helper that returns the
non-`None` types from a `Path | None` annotation (using
`typing.get_args` and filtering `NoneType`); for non-Optional
annotations it returns `(annotation,)`.

The walker's contract is asserted by an explicit Cycle 6 test
(added to §6.7 Red phase):

```python
def test_enumerate_path_fields_yields_known_set() -> None:
    """Pin the walker's coverage so a shallow re-implementation
    cannot regress to silently yielding zero matches."""
    expected = {
        "trustee_catalog.db_path",
        "diagnostics.audit_log_dir",
        "diagnostics.rules_dir",
    }
    assert set(_enumerate_path_fields(FirmConfig)) == expected
```

This test runs INDEPENDENTLY of the integration tests for shared-
side rejection — it asserts the walker's coverage at the unit level,
so a regression to a shallow walker would fail this test BEFORE
failing the integration tests. The two-layer assertion (walker
output set + integration rejection behavior) prevents the failure
mode where a buggy walker yields zero matches and the integration
tests trivially pass because there are no fields to validate.

##### 5.3.7.6 Future-schema-extension protocol

When a future schema field is added that is path-bearing but uses
an annotation pattern outside the four above (e.g., `list[Path]`),
the schema-extension spec MUST update both `_enumerate_path_fields`
AND `test_enumerate_path_fields_yields_known_set`. The test
serves as a tripwire: it pins the current set of dotted keys, so
adding a new Path-typed field automatically fails the test until
the expected set is updated to include it. This converts "future
extensibility risk" from "silent shallow-walker drift" into "loud
test failure that forces the schema-extension author to consciously
update the walker's coverage."

`_get_dotted(shared_dict, dotted_key)` is the passthrough lookup
that traverses the dict according to a dotted key path:

```python
def _get_dotted(d: dict[str, Any], dotted_key: str) -> str | None:
    """Return d[k1][k2]...[kn] for dotted_key='k1.k2...kn',
    or None if any intermediate key is missing or not a dict.

    Returns the leaf value as-is (typically a string from TOML
    parsing). Does not coerce to Path; the validator inspects the
    raw string."""
    parts = dotted_key.split(".")
    current: Any = d
    for part in parts:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
        if current is None:
            return None
    return current if isinstance(current, str) else None
```

Both `_enumerate_path_fields` and `_get_dotted` are module-private
(no leading-underscore exposure to consumers); they are exercised
by Cycle 6's `test_shared_side_relative_path_rejected`,
`test_enumerate_path_fields_yields_known_set`, and the existing
positive-path tests.

### 5.4 Cache and sync-unavailability

The shared file lives on a SharePoint document library, accessed through
OneDrive's local sync. Sync can be unavailable for ordinary reasons: the
workstation is offline, the OneDrive client is paused or signing in, the
library path is mid-rename, or the file has not yet propagated. The loader
must degrade gracefully across these cases without failing every load that
happens to coincide with a transient sync gap.

The cache layer's purpose is to enable continuity of operation across short
sync outages. It is NOT a long-term offline mode and not a replacement for
the canonical SharePoint copy.

#### 5.4.1 Cache file location and naming

The cache file lives at platform-conventional state paths:

- **Windows:** `%LOCALAPPDATA%/trust-generator/firm.shared.cache.toml`.
- **POSIX (incl. WSL development):** `${XDG_CACHE_HOME:-~/.cache}/trust-generator/firm.shared.cache.toml`.

The `XDG_CACHE_HOME` environment variable is honored when set, per the
XDG Base Directory specification; fallback to `~/.cache` covers the default
case.

The filename `firm.shared.cache.toml` is chosen for unambiguous future
extensibility — if cached copies of other shared assets become needed
(rule packs, templates), they sit alongside this file with parallel naming
(`rules.shared.cache.toml`, etc.) without collision.

The loader exposes a helper that resolves the cache path on demand,
encapsulating the platform branching:

```python
def _cache_path() -> Path:
    if sys.platform == "win32":
        local_appdata = os.environ.get("LOCALAPPDATA")
        if not local_appdata:
            raise FirmConfigError(
                "LOCALAPPDATA environment variable is not set; "
                "cannot determine cache directory."
            )
        cache_dir = Path(local_appdata) / "trust-generator"
    else:
        xdg = os.environ.get("XDG_CACHE_HOME")
        cache_dir = (Path(xdg) if xdg else Path.home() / ".cache") / "trust-generator"
    return cache_dir / "firm.shared.cache.toml"
```

The cache directory is created on first write via `mkdir(parents=True, exist_ok=True)`.

#### 5.4.2 Cache write

The cache write happens after every fully successful load — specifically,
after the merged dict has been validated by `FirmConfig(**merged)` without
raising. The write is unconditional: the cache is overwritten on every
successful load, regardless of whether the shared file's content has changed
since the last cache write.

Rationale for unconditional overwrite: the cache file's mtime then tracks
"timestamp of last fully successful load," which is precisely the staleness
signal the fallback warning (5.4.4) reports to the user. Conditional
overwrite (e.g., "only write if hash differs") would either cost an extra
read per load to compute the comparison, or require persisting a hash
separately — and would lose the mtime-as-recency-signal in exchange for
a one-write-per-load saving on shutdown-cost-per-byte storage that is
unimportant.

The write is atomic: the loader writes raw bytes to a sibling tempfile
(`firm.shared.cache.toml.tmp`) and `os.replace()`s it onto the final path.
This avoids leaving a half-written cache visible if the process crashes
mid-write.

The cache content is a verbatim byte-copy of the shared file as read from
disk. No serialization round-trip through `tomllib` and back, no Pydantic
model involved. This is required for two reasons:

- **Format preservation:** TOML supports comments, key ordering, and
  formatting that don't survive `tomllib` parse → `tomli_w` re-emission.
  Verbatim copy preserves them, which matters for human inspection of the
  cache file when triaging issues.
- **Determinism:** the cache file IS the shared file, byte-for-byte. The
  cache-read code path can be the SAME as the shared-read code path,
  pointed at a different file. No second parse implementation, no
  divergent behavior.

Cache write failure does not fail the load. If the cache write raises
(disk full, permissions issue, parent directory unwriteable), the loader
catches and emits `warnings.warn("failed to update shared firm.toml cache: <reason>")`
but returns the validated `FirmConfig` normally. The current load completes;
the next load will face the same write issue, or it will succeed if the
underlying problem clears. Treating cache-write failure as fatal would
make transient disk issues silently break the application, which is worse
than a missed cache update.

#### 5.4.3 Cache read and fallback policy

Cache reads happen when the shared-file discovery (5.2.2) resolves to a
path that does not exist, cannot be opened, returns empty bytes, or
fails TOML parsing. The fallback decision tree:

1. **Shared file resolved, exists, opens cleanly, non-empty, parses
   cleanly:** read its bytes, parse, merge, validate, return. Cache
   write happens on the way out (5.4.2). Cache file is not consulted.
2. **Shared file resolved, does not exist OR raises `OSError` on open:**
   attempt cache read with `SharedConfigStalenessWarning` (5.4.4) on
   success. This is the *availability-fallback* path.
3. **Shared file resolved, opens cleanly, but `read_bytes()` returns
   empty bytes:** attempt cache read with `SharedConfigStalenessWarning`
   on success, naming the empty-shared condition in the warning text.
   This is treated as availability failure: empty bytes are the
   characteristic OneDrive placeholder state for a file that is
   advertised as present but whose content has not yet propagated. If
   the cache is also unavailable, raise the dedicated empty-shared
   error (5.4.5.1) rather than the generic onboarding-pointer error,
   so the maintainer can distinguish "sync in flight" from "sync never
   completed."
4. **Shared file resolved, opens cleanly, non-empty, but parses with
   `tomllib.TOMLDecodeError`:** attempt cache read with
   `SharedConfigIntegrityWarning` (5.4.4.1) on success. This is the
   *integrity-fallback* path: shared was reachable but unparseable. The
   distinct warning class signals to operators that the maintainer
   needs to be notified the shared file is broken, even though the
   workstation continues operating. If the cache is unavailable, raise
   the integrity-error variant (5.4.5.2) rather than the
   onboarding-pointer error.

For each cache-read attempt referenced above:

- **Cache file exists, parses cleanly:** read its bytes, parse, merge,
  validate, return. Emit the appropriate warning per the case that
  triggered the fallback. NO cache write happens — the cache is the
  source for this load, overwriting it with itself would be pointless
  and the mtime would falsely reset.
- **Cache file does not exist:** raise the appropriate error variant
  per 5.4.5 / 5.4.5.1 / 5.4.5.2.
- **Cache file exists, fails to parse with `tomllib.TOMLDecodeError`:**
  raise `FirmConfigError("shared firm.toml cache at <path> is corrupt: <reason>")`.
  Do NOT silently treat a corrupt cache as missing; surface it. A
  corrupt cache is a real problem requiring maintainer attention;
  masking it as "not yet onboarded" would misdirect the user.

##### Operational rationale for integrity-fallback (case 4)

The predecessor draft (revision 2026-04-27 pre-review) treated case 4
as fail-fast: any malformed shared file would hard-stop every workstation
on every `load_firm_config()` call until the maintainer fixed the shared
file. Plan-review surfaced that this inverts the audit-trail-integrity
property the design aims to protect. A workstation falling back to its
last-known-good cache continues writing audit-log entries with
last-known-good thresholds — which is exactly "what was in effect at
decision time" per §5.5.3. Hard-stopping prevents work entirely, so
nothing is "in effect" for those decisions; the audit trail loses the
records that would have been written.

The distinct `SharedConfigIntegrityWarning` class (separate from the
availability-fallback `SharedConfigStalenessWarning`) preserves the
operational signal the predecessor draft sought: a category that
notifies operators "the maintainer's shared file is broken; this is
not a routine sync hiccup." Diagnostics consumers (per the §5.5.5
trust-boundary subscriber) can route this category to a louder
notification surface than the staleness category.

Recovery latency: in the small-firm context (single maintainer,
non-technical paralegals, OneDrive sync), fail-fast on every
workstation produces hours of lost productivity per maintainer edit
error, with no compensating integrity gain. Fall-back-with-distinct-
warning preserves work continuity; the maintainer's notification
surface flags the broken shared file for repair on the next
maintainer-available window.

#### 5.4.4 Staleness warning

When the availability-fallback path is taken (case 2 or case 3 in
5.4.3) AND the cache read succeeds, the loader emits a warning via
`warnings.warn` before returning:

```
shared firm.toml unreachable; falling back to cached copy from
  2026-04-15 14:32 UTC (12 days, 4 hours old).
source: <resolved shared path>
cache:  <cache file path>
```

For case 3 (empty bytes, characteristic OneDrive placeholder state),
the message text replaces "unreachable" with "advertised but empty"
to give the maintainer a triage clue distinct from the generic-missing
case.

The age is computed from the cache file's `st_mtime` against the
current UTC time at load. This gives the user a self-service triage
signal: a cache from minutes ago suggests a transient sync hiccup; a
cache from days ago suggests a sync configuration problem that needs
attention.

The warning category is a custom `SharedConfigStalenessWarning`
subclass of `UserWarning`. Isolating the category lets consuming code
filter or elevate it independently of other warnings — for example,
the §5.5.5 diagnostics subscriber routes this category to the
application audit log without affecting other `UserWarning` consumers.

The warning is emitted exactly once per load, regardless of how many
downstream consumers query the loaded `FirmConfig`. The loader does
not repeat-warn across multiple `load_firm_config()` calls within a
single process; each call's fallback emits its own warning.

##### 5.4.4.1 Integrity warning

When the integrity-fallback path is taken (case 4 in 5.4.3) AND the
cache read succeeds, the loader emits a warning of category
`SharedConfigIntegrityWarning` instead of `SharedConfigStalenessWarning`:

```
shared firm.toml at <resolved shared path> is malformed
  (TOML parse error: <reason>); falling back to cached copy from
  2026-04-15 14:32 UTC (12 days, 4 hours old).
This indicates the shared file was reachable but unparseable. The
maintainer must repair the shared file; this workstation continues
running on its last-known-good cached copy.
source: <resolved shared path>
cache:  <cache file path>
```

`SharedConfigIntegrityWarning` is a separate `UserWarning` subclass
from `SharedConfigStalenessWarning` so consumers can route the two
categories to different surfaces. The semantic distinction is:

- **Staleness** signals "shared was unavailable; the cache is older
  than ideal but the system is in a degraded-but-known state." The
  recovery action is "wait for sync to recover, or check OneDrive
  client status."
- **Integrity** signals "shared was reachable but corrupt; the
  maintainer needs to be notified the file they edited is broken."
  The recovery action is "contact the maintainer to repair the shared
  file."

Both warnings are emitted exactly once per load.

##### 5.4.4.2 What the warning surfaces do NOT deliver

This spec preserves per-workstation forensic completeness for the
configuration fields currently captured by the audit-log
persistence layer — today, `restriction_level` only, per
`2026-04-23-diagnostics-engine-design.md` §5.5. Full effective-
configuration capture (thresholds, jurisdiction, audit_log_dir
substitutions) is conditional on §10 chore #5; until that chore
lands, the per-workstation forensic completeness is partial.

The spec does NOT deliver firm-level edit-propagation timeliness;
specifically, when the maintainer pushes a deliberately-restrictive
edit (e.g., tightening a threshold) and the edit contains a TOML
syntax error, every paralegal workstation silently falls back to
the previous-known-good cache and continues operating on the
previous (more permissive) thresholds.

The integrity warning class (5.4.4.1) is the loader's signal that
this divergence has occurred. The notification recovery loop —
"how does the maintainer learn their edit failed to apply, and how
quickly?" — is owned by the diagnostics-engine subscriber per
§5.5.5.4 and §10 chore #4. That chore is responsible for pinning a
target latency (e.g., end-of-day digest, real-time desktop alert,
Outlook notification on next maintainer login). This spec
deliberately does not pin the latency value because the pinning
belongs in the diagnostics engine's operational surface, not in
the loader's contract.

A maintainer-side smoke-test workflow (a script the maintainer runs
post-edit that does a clean `load_firm_config()` against the
production-conventional paths and reports success/failure) would
provide a more immediate detection surface than the post-hoc
audit log. Scripting this is out of scope for this spec; the seam
is noted in §7 ("Open seams") for a future iteration.

The disclaimer here exists so readers do not over-rely on the §1
motivation argument as guaranteeing maintainer-edit timeliness.
This spec guarantees:

- **Firm-canonical-source unambiguity** — the maintainer's
  SharePoint file IS the source of truth, full stop.
- **Per-workstation forensic completeness for currently-captured
  fields** — today's audit record captures `restriction_level`;
  expansion to full effective configuration is gated on chore #5.
  When that chore lands, this property strengthens to "every
  audit record forensically reconstructs the policy in effect at
  decision time on that workstation."

It does NOT guarantee:

- **Firm-wide edit-propagation timeliness** — maintainer-intended
  edits do not land on every workstation within any specific time
  window; the loader is best-effort under degraded sync conditions
  and may continue serving last-known-good cache content
  indefinitely until shared becomes reachable again.
- **Maintainer-edit-failure detection latency** — pinned by chore
  #4 to whatever value the diagnostics-engine plan author
  selects; this spec is silent on the value.

#### 5.4.5 Onboarding-pointer error

When the availability-fallback is triggered by case 2 (file absent or
`OSError`) AND the cache is also unavailable, the loader raises:

```
FirmConfigError:
  Shared firm.toml is unreachable and no cached copy exists.
  Resolved shared path: <path>
  Expected cache path:  <path>

  This typically indicates either (1) initial setup of this workstation
  has not yet completed, or (2) the SharePoint sync has never succeeded
  on this machine.

  See the paralegal-onboarding workflow for first-time setup, or contact
  the maintainer for sync troubleshooting.
```

The error message names both paths so the user (or the maintainer
debugging on their behalf) can immediately see what was attempted. The
reference to the onboarding workflow is intentionally a textual pointer,
not a code reference — the onboarding workflow does not yet exist
(roadmap-tracked, blocked); the message describes its eventual role
without coupling to its implementation.

This error case should be impossible on any workstation that has ever
successfully completed a load. The cache, once written, persists;
subsequent cache absences imply explicit deletion of the cache file by
the user or a separate process. That is a recoverable condition
(restoring sync access produces a cache write on the next successful
load), not a routine occurrence.

##### 5.4.5.1 Empty-shared error variant

When case 3 of 5.4.3 (shared file resolved, opens cleanly, but
`read_bytes()` returns empty) AND the cache is unavailable, the loader
raises:

```
FirmConfigError:
  Shared firm.toml at <resolved shared path> is unexpectedly empty
  (likely OneDrive placeholder state) and no cached copy exists.
  Resolved shared path: <path>
  Expected cache path:  <path>

  This typically indicates an in-progress OneDrive sync that has
  advertised the file but not yet propagated its content. Retry shortly,
  or contact the maintainer if the condition persists past the firm's
  expected sync window.
```

The empty-shared variant exists because conflating it with the
onboarding-pointer error misdirects troubleshooting: a workstation
that is mid-sync (transient) is operationally distinct from a
workstation that has never sync'd (configuration problem).

##### 5.4.5.2 Integrity-error variant

When case 4 of 5.4.3 (shared malformed) AND the cache is unavailable,
the loader raises:

```
FirmConfigError:
  Shared firm.toml at <resolved shared path> is malformed
  (TOML parse error: <reason>) and no cached copy exists to fall back to.
  Resolved shared path: <path>
  Expected cache path:  <path>

  The maintainer must repair the shared file. This workstation has no
  cached copy to fall back to, so it cannot operate until the shared
  file is fixed and re-synced.
```

The integrity-error variant is reachable only on a workstation that
has never successfully completed a load (no cache exists) AND
encountered a malformed shared file. Per 5.4.5's "this should be
impossible after first successful load" property, this combination
implies first-time setup hit a corrupt shared push. The error message
distinguishes from the onboarding-pointer case so the maintainer can
triage shared-file repair rather than workstation-onboarding repair.

#### 5.4.6 Cache invalidation and explicit refresh

The cache has no automatic invalidation policy. It is overwritten on every
successful load (5.4.2) and that is the sole mechanism by which it
refreshes.

This spec does not expose a public "invalidate cache" or "force refresh"
API. Maintainer-side cache management uses the filesystem directly
(deleting the cache file forces the next load to fail-or-refresh based on
shared availability). A future spec may introduce a CLI command for this
if operational experience surfaces a need; preemptive API surface is
declined here to avoid premature commitment.

#### 5.4.7 Properties verifiable in tests

The behavioral contract above factors into testable properties for
Cycles 4 and 5. The helper-return-shape contract changes from
`bytes` to `tuple[bytes, dict[str, Any], bool]` per 5.6.6 (where the
boolean is `used_cache`); the test list reflects that contract.

**Cache-write properties (Cycle 4):**

- After a successful load with reachable shared, the cache file exists
  at the resolved cache path and its bytes equal the shared file's
  bytes.
- After a successful load with reachable shared, the cache file's
  mtime is within seconds of the load's wall-clock time.
- A second successful load overwrites the cache atomically; no
  `firm.shared.cache.toml.tmp` is left behind.
- Cache write failure does not fail the load; a warning is emitted
  instead.

**Availability-fallback properties (Cycle 5, case 2 of 5.4.3):**

- When the shared path resolves to a nonexistent file and the cache
  exists, the helper returns `(cache_bytes, parsed_cache_dict,
  used_cache=True)` and emits exactly one
  `SharedConfigStalenessWarning`. The integration does NOT call
  `_write_cache`.
- When the shared path resolves to a nonexistent file and the cache
  does not exist, the helper raises `FirmConfigError` whose message
  contains both the resolved shared path and the expected cache
  path (per 5.4.5).
- When the shared path resolves to a nonexistent file and the cache
  exists but is corrupt, the helper raises `FirmConfigError` whose
  message names the cache path and uses the word "corrupt".

**Empty-shared-fallback properties (Cycle 5, case 3 of 5.4.3):**

- When the shared file exists but `read_bytes()` returns empty bytes
  and the cache exists, the helper returns `(cache_bytes,
  parsed_cache_dict, used_cache=True)` and emits exactly one
  `SharedConfigStalenessWarning` whose message text contains
  "advertised but empty" rather than "unreachable".
- When the shared file exists but `read_bytes()` returns empty bytes
  and the cache does not exist, the helper raises `FirmConfigError`
  per 5.4.5.1, whose message contains the phrase "unexpectedly empty"
  and "OneDrive placeholder state".

**Integrity-fallback properties (Cycle 5, case 4 of 5.4.3):**

- When the shared file is reachable but TOML-malformed and the cache
  exists, the helper returns `(cache_bytes, parsed_cache_dict,
  used_cache=True)` and emits exactly one
  `SharedConfigIntegrityWarning` (NOT `SharedConfigStalenessWarning`).
  The integration does NOT call `_write_cache`.
- When the shared file is reachable but TOML-malformed and the cache
  does not exist, the helper raises `FirmConfigError` per 5.4.5.2,
  whose message contains "is malformed" and "no cached copy exists".
- `SharedConfigIntegrityWarning` is a subclass of `UserWarning` and is
  NOT a subclass of `SharedConfigStalenessWarning` (independent
  filtering).

**Single-parse / TOCTOU properties:**

- The helper parses each source file's bytes exactly once and returns
  the parsed dict alongside the bytes. A successful return implies
  the dict is consumable for merging without re-parsing.
- The helper's `exists() + read_bytes()` sequence is treated atomically
  for the purpose of fallback decisions: any `OSError` between
  `exists()` returning `True` and `read_bytes()` returning bytes
  routes to the availability-fallback path (case 2), preserving
  determinism in the face of OneDrive-driven mid-load state changes.
- The integration's `used_cache` decision (whether to call
  `_write_cache`) consumes the helper's returned boolean directly and
  never re-queries `resolved_shared.exists()` after the helper
  returns. This eliminates the predecessor draft's TOCTOU window in
  which a mid-load file-appears event could write cache bytes back
  onto the cache, falsely resetting mtime.

#### 5.4.8 Shared completeness check

Plan-review (round 2) surfaced that the four cases in §5.4.3 cover
`tomllib.TOMLDecodeError` and empty-bytes (`b""`) but do NOT cover
*partial-but-parseable* shared content. OneDrive Files-On-Demand can
deliver non-empty truncated content if a sync is interrupted between
section boundaries; truncated TOML often parses cleanly because TOML
allows arbitrary section ordering with no required-section
declaration. A merge proceeding with a partial shared dict would
silently activate `FirmConfig`'s `default_factory=...` defaults for
any missing top-level table — silently substituting Pydantic defaults
for firm policy.

This subsection adds a completeness check between parse and merge,
treating partial-but-parseable shared content as integrity failure.

##### 5.4.8.1 Required-from-shared section set

The loader maintains a module-private constant
`_SHARED_REQUIRED_SECTIONS` enumerating the top-level tables that
shared MUST declare:

```python
_SHARED_REQUIRED_SECTIONS: Final[frozenset[str]] = frozenset({
    "firm",
    "estate_thresholds",
    "diagnostics",
})
```

These three sections are firm-policy-bearing: `firm` carries
identity (no Pydantic default exists; absence would fail
validation, but only after merging in local — partial sync masks
the absence to mean 'workstation user, not maintainer, broke
something'); `estate_thresholds` carries the threshold values whose
silent-replacement-by-Pydantic-defaults would be the most
operationally consequential failure mode; `diagnostics` carries the
restriction-level policy that gates audit-log generation.

`jurisdiction`, `trustee_catalog`, `guardianship`, `drafts`, and
`meta` are NOT required from shared. Each has reasonable Pydantic
defaults that match firm policy as of this spec date, and silent
fallback to those defaults during partial-sync conditions is
operationally indistinguishable from "the firm runs the defaults"
— which IS the firm's policy for those sections today.

If a future schema field on a currently-default-bearing section
becomes policy-bearing in a way that defaults-fallback would be
operationally consequential, that section moves into
`_SHARED_REQUIRED_SECTIONS` via amendment.

##### 5.4.8.2 Check timing and failure routing

The check runs in Cycle 6's pipeline (§6.7) immediately after the
shared dict is obtained from `_read_shared_with_fallback` and
before `deep_merge`. If any required section is missing from the
parsed shared dict, the load routes to the integrity-fallback path
(case 4 of §5.4.3) with `SharedConfigIntegrityWarning` and the
message phrasing "missing required section(s):
<comma-separated-list>" rather than "TOML parse error: <reason>".
The cache fallback then proceeds normally (or raises the integrity-
error variant of §5.4.5.2 if no cache exists).

Routing through case 4 (rather than inventing a fifth case) keeps
the warning class set at two and the operational signal consistent:
"shared was reachable but the maintainer's edit produced something
the loader cannot trust." Whether the un-trustworthiness comes from
TOML parse failure or partial-sync truncation is operationally
identical — the maintainer must intervene.

##### 5.4.8.3 Cache write gate for partial-sync content

The cache write (5.4.2) is gated on the integration's `used_cache`
boolean (5.4.7). Partial-sync content reaches the integration via
`_read_shared_with_fallback`'s normal path (case 1: shared
exists, non-empty, parses), with `used_cache=False`. Cycle 6's
pre-merge completeness check is the load's last opportunity to
detect partial sync; on detection, the integration MUST short-
circuit before the cache write step. The check raises a routable
integrity condition that the integration converts to an
integrity-fallback re-read (re-invoking
`_read_shared_with_fallback` is wasteful; the simpler shape is to
raise an internal exception that the integration catches and
responds to by reading from cache directly with the integrity
warning).

The implementation pattern in Cycle 6 green:

```python
shared_bytes, shared_dict, used_cache = _read_shared_with_fallback(
    resolved_shared
)
if not used_cache:
    missing = _SHARED_REQUIRED_SECTIONS - set(shared_dict.keys())
    if missing:
        # Integrity failure via partial-sync. Re-route to cache.
        shared_bytes, shared_dict, used_cache = _read_cache_or_raise(
            resolved_shared,
            warning_class=SharedConfigIntegrityWarning,
            warning_phrasing=(
                f"is missing required section(s) "
                f"{sorted(missing)} (likely partial OneDrive sync)"
            ),
            no_cache_error_template=_INTEGRITY_ERROR_TEMPLATE,
            integrity_reason=(
                f"missing required section(s): {sorted(missing)}"
            ),
        )
```

This shape preserves the helper's tuple-return contract (the second
call assigns the same three-tuple) and reuses the existing
integrity-error template. No new error variant is introduced.

##### 5.4.8.4 Testable properties

Adds to the §5.4.7 list:

- When shared parses cleanly but is missing one or more sections in
  `_SHARED_REQUIRED_SECTIONS`, the load emits exactly one
  `SharedConfigIntegrityWarning` whose message names the missing
  sections; the cache file is consulted for the actual configuration;
  the cache file is NOT overwritten.
- When shared is missing required sections AND no cache exists, the
  load raises `FirmConfigError` per 5.4.5.2 with the message
  containing "missing required section(s)".
- When shared declares all required sections plus an arbitrary set of
  optional sections (e.g., `jurisdiction` only), the completeness
  check passes and the load proceeds normally.
- The `_SHARED_REQUIRED_SECTIONS` constant is module-private; tests
  in the same package import it directly. External consumers cannot
  rely on its existence.

##### 5.4.8.5 Manifest/checksum alternative considered and deferred

A heavier alternative considered: ship a maintainer-authored
manifest file alongside the shared TOML (e.g.,
`firm.toml.manifest`) listing required-sections, schema version,
and a content hash; the loader cross-checks. Rejected for this
spec: the manifest adds a second file the maintainer must
maintain; manifest drift becomes a new failure mode; the
required-section-set approach gives most of the integrity benefit
with zero maintainer burden. If a future iteration surfaces a
need for content-level integrity (e.g., the firm starts running
multiple maintainer-edits in flight and partial commits become
common), the manifest is a reasonable upgrade path.

### 5.5 SharePoint permission model

Write access to the shared file is enforced at the SharePoint document
library layer, not by the application. This is a deliberate division of
responsibility: SharePoint is already the firm's authentication and
authorization substrate for document access, and routing the shared
firm.toml through that substrate inherits its identity verification,
auditing, and revocation properties without re-implementing them.

#### 5.5.1 Library-level permission groups

The SharePoint document library hosting `trust-generator/firm/config/firm.toml`
uses two permission groups:

- **Maintainer group** — SharePoint **Members** role (Edit). The
  maintainer is the sole occupant. Members can read and write all
  files in the library.
- **Paralegal group** — SharePoint **Visitors** role (Read). All
  paralegal users belong to this group. Visitors can read all files
  in the library, including `firm/config/firm.toml`, but cannot write,
  rename, or delete.

These groups are managed at the library level. There are no per-folder
or per-file ACLs. Folder-scoped ACLs in SharePoint are operationally
fragile (they break in non-obvious ways when files move between folders)
and offer no benefit at the firm's current scale, where there is exactly
one maintainer and the surface to protect is well-bounded.

#### 5.5.2 Application-layer permission posture

The loader does NOT check the user's permission level before reading the
shared file. It does not need to: SharePoint's permission system already
gates physical access. A paralegal's read succeeds; their write attempt
would fail at the OneDrive sync layer (returning a permissions error
from the OS file API), and no application code path attempts a write to
the shared file in any case.

The application also does not check permission level before reading the
local file. The local file lives in a per-workstation location whose
filesystem-level permissions reflect the workstation's user account; this
is sufficient.

This posture means the loader's code is identity-agnostic. It reads what
it can read, writes what it can write (only the cache file, in the
user's `LOCALAPPDATA` or `XDG_CACHE_HOME`), and surfaces OS-level errors
as `FirmConfigError` without interpreting them. This keeps the loader
testable without a mock authentication layer and avoids the maintenance
cost of an in-app permission model that would inevitably drift from the
authoritative SharePoint groupings.

#### 5.5.3 Audit trail division

Two audit trails operate independently:

- **SharePoint version history** records who edited the shared file,
  when, and what changed. This is the authoritative trail for
  configuration changes and is accessed through the SharePoint web UI's
  version history feature. The application does not surface this trail
  internally.
- **Application audit log** (per `audit_log_persistence`) records the
  EFFECT of configuration on operational decisions — which threshold
  was active when a force-generation happened, what restriction_level
  applied to a given case. The application audit log captures what was
  *in effect* at decision time, not who *put it in effect*.

Reconstructing a complete narrative across the two trails requires
cross-referencing timestamps. This is acceptable given the low frequency
of configuration changes (firm-policy updates, threshold adjustments
following legislative changes — both rare events) and the high
frequency of operational decisions (per-document restriction enforcement
— happens dozens of times daily). Coupling the two trails would force
every operational decision to query SharePoint version history at
decision time, which is operationally heavy and offline-fragile.

The audit-log entries written by the application include
configuration context for forensic reconstruction. Today the
`force_generation()` audit record captures `restriction_level` (per
`2026-04-23-diagnostics-engine-design.md` §5.5); the audit-log
record does NOT yet capture effective thresholds, jurisdiction, or
the substituted `audit_log_dir` path. Expanding the audit record to
include the full effective configuration is the subject of §10 chore
#5; until that chore completes, forensic reconstruction of the
threshold policy in effect at decision time depends on
cross-referencing the SharePoint version history with the audit-
record timestamp, which is a recoverable but operationally heavier
posture.

The §1 motivation argument depends on chore #5 completing. For the
duration of any window in which this spec ships ahead of chore #5,
the design's integrity property is partially preserved (per-
decision restriction-level capture) but not fully (per-decision
threshold capture is still externally cross-referenced). Documenting
this dependency explicitly here so readers do not over-rely on the
forensic property in the interim.

#### 5.5.4 First-write seeding

The initial creation of `trust-generator/firm/config/firm.toml` in the
SharePoint library is a manual maintainer action, performed once during
migration (§8). It is not a loader concern. The loader's behavior on a
workstation that has never seen the shared file is governed by the
cache-absent error path (5.4.5).

#### 5.5.5 Cache and env-var trust boundaries

The permission model in 5.5.1 through 5.5.4 covers reads of the
SharePoint-mediated shared file. Two other paths through which the
loader consumes shared-equivalent data sit outside that boundary, and
the asymmetry is documented here so future security review knows what
the design assumes.

##### 5.5.5.1 Cache trust shift

The cache file at `%LOCALAPPDATA%/trust-generator/firm.shared.cache.toml`
(Windows) or `${XDG_CACHE_HOME:-~/.cache}/trust-generator/firm.shared.cache.toml`
(POSIX) is writable by the workstation user. Whenever the
shared-fallback path is taken (5.4.3 cases 2, 3, 4), the loader
trusts the cache file fully — it merges the cache's bytes into the
configuration as if they had come from SharePoint.

This is a trust shift relative to the SharePoint-mediated read path:
- **SharePoint-mediated read** carries SharePoint's identity
  verification, audit logging, and revocation properties (5.5.1).
- **Cache-mediated read** carries only filesystem-level workstation
  user authorization. Any process running as that user (legitimate or
  not) can replace the cache file's content.

A user (or a compromised tool running in that user's session) with
write access to `LOCALAPPDATA` but no edit access to the SharePoint
library can inject altered configuration that takes effect during any
sync outage. The compromised configuration would persist on that
workstation only — it is never written back to SharePoint — but the
audit trail's claim "the workstation ran with the configuration in
the cache file" remains accurate even when the cache was tampered
with.

##### 5.5.5.2 Env-var trust shift

The `TGV3_FIRM_SHARED_CONFIG` environment variable (5.2.2) lets a
user point the shared-discovery chain at any TOML file the user-
context process can read. This is intentional — it is the WSL
development-mode story (5.2.6) and the migration step 4a story (8.2).
But it is also a trust shift: any process running as that user can
set the env var before invoking `load_firm_config()` and substitute
its own shared TOML.

In production paralegal workstations the env var is not set; the
convention path applies; the trust posture is the SharePoint-mediated
one. The env var only matters in development, CI, and migration
contexts where the user explicitly opts into a non-SharePoint shared
source.

##### 5.5.5.3 Threat-model assessment

The firm's threat model is "non-hostile insiders, unsophisticated
external threats." The two trust shifts above are acceptable under
this model:

- The cache trust shift requires LOCALAPPDATA write access, which the
  legitimate user has by definition. The realistic abuse vector is a
  paralegal making a mistake (e.g., manually editing the cache to
  "see what happens") rather than malicious insider activity.
- The env-var trust shift requires the ability to set environment
  variables in the loading process, which again the user has. The
  realistic abuse vector is a developer accidentally pointing at a
  stale fixture rather than malicious substitution.

If the firm's threat model changes (e.g., adversarial paralegal
workstations, regulatory requirements pinning configuration
authenticity), revisit:

- Add a maintainer-signed manifest covering the cache file content
  and verify on read.
- Restrict the env-var override to development builds only (compile-
  time gate).
- Cache integrity check via filesystem ACL setting cache file
  unwriteable except by the loader process.

None of these are implemented today.

##### 5.5.5.4 Audit-log coverage of fallback events

Every fallback event (`SharedConfigStalenessWarning` or
`SharedConfigIntegrityWarning`) is recorded in the application audit
log via the diagnostics-engine subscriber referenced in §10 chore #4.
Each entry records:

- Timestamp of the load event.
- Resolved shared path that was attempted.
- Cache path that was used.
- Cache file mtime (age signal).
- Warning category (staleness vs. integrity).
- For integrity events, the TOML parse error reason (truncated to a
  reasonable length).

This is the post-hoc detection surface for prolonged sync outages,
anomalous cache use, and suspected configuration tampering — the
maintainer can review the audit log to spot patterns even though the
loader itself does not block on these conditions.

##### 5.5.5.5 Subscription-timing guarantee

Plan-review (round 2) flagged that the subscriber-registration
order matters: many applications initialize config first (because
every other subsystem needs it) and only then bootstrap the
diagnostics engine. If the diagnostics engine subscribes via a
`warnings.showwarning` override or a Python `logging` handler
registered after `load_firm_config()`'s first invocation, the
inaugural fallback warning (often the most diagnostically
valuable, e.g., a paralegal's morning-sync-gap warning) is missed.

To eliminate the registration-ordering dependency, the loader
module calls `logging.captureWarnings(True)` at module import
time (before any `load_firm_config()` call can occur):

```python
# At top of trust_generator.v3.config.firm:
import logging
logging.captureWarnings(True)
```

Effect: every `warnings.warn(...)` call (including the loader's
emission of `SharedConfigStalenessWarning` and
`SharedConfigIntegrityWarning`) is routed through Python's
`logging` machinery to the `py.warnings` logger. The diagnostics
engine subscribes by attaching a logging handler to that logger
at any point — registration order with respect to
`load_firm_config()` no longer matters, because:

- If the handler is attached BEFORE the first warning fires, it
  receives the warning live.
- If the handler is attached AFTER the first warning fires, the
  warning was already emitted and routed to `py.warnings`'s
  handlers in effect at emission time. The default Python logger
  configuration writes to stderr, so the warning is at minimum
  observed in process output even if no logger handler is
  attached. Subsequent warnings are received live.

The chore #4 implementation guidance: subscribe via
`logging.getLogger("py.warnings").addHandler(...)` rather than
overriding `warnings.showwarning` directly. The former composes
with `logging.captureWarnings(True)`; the latter conflicts with
it.

##### Testability tradeoff

Module-import-time `logging.captureWarnings(True)` creates two
testability considerations the test author must handle:

- **`pytest.warns` context managers** continue to work because
  pytest's warning-capture machinery instruments the `warnings`
  module before tests run, and `captureWarnings(True)` does not
  prevent `warnings.warn` from also recording the warning into
  the `_filters` list pytest reads from. Tests using
  `pytest.warns(SharedConfigStalenessWarning)` and similar
  patterns are unaffected.
- **`logging.captureWarnings(False)` called by other code** would
  un-route subsequent warnings from the logger. Test fixtures
  that toggle this setting MUST restore it via try/finally or
  pytest's `monkeypatch` (which auto-restores).
- **`importlib.reload(trust_generator.v3.config.firm)`** re-runs
  the module body, including the second `captureWarnings(True)`.
  This is benign — `captureWarnings` is idempotent with respect
  to repeated calls of the same value — but tests that reload
  the module should be aware of the no-op semantic and not assert
  freshness of the routing setup.

These are not show-stoppers; they are coordination requirements
the test plan accepts as part of the trade for eliminating the
subscriber-registration-ordering dependency.

##### 5.5.5.6 Loader's responsibility scope

The loader's responsibility ends at:

- Emitting the warning via `warnings.warn(..., category=...)`
  with the correct class.
- Calling `logging.captureWarnings(True)` at module import time
  to route warnings through `logging`.
- Documenting the subscription path in this section so the
  diagnostics-engine plan author knows what mechanism to use.

The actual subscription, audit-log writing, and operational
notification surfaces are diagnostics-engine concerns. This
spec's §10 chore #4 names the requirement; chore #4's owner
implements it.

### 5.6 Loader API

The loader module's public surface is intentionally small: one entry-point
function, one error class, one warning class, plus the existing `FirmConfig`
and its sub-models. Every other helper described in this spec is module-private.

#### 5.6.1 Function signature

```python
def load_firm_config(
    local_path: Path | None = None,
    shared_path: Path | None = None,
) -> FirmConfig: ...
```

Both parameters are optional. Each `None` triggers the corresponding
discovery chain (5.2.1 for `local_path`, 5.2.2 for `shared_path`); each
explicit `Path` short-circuits discovery for that source. The two
parameters are independent: explicit local + discovered shared is a valid
combination, and vice versa.

Parameter ordering puts `local_path` first because:

- It mirrors today's single-argument signature where `path` referred to
  what is now the local file. Existing call sites that pass
  `load_firm_config(some_path)` keep working under positional invocation
  if `some_path` was previously the local path — which it always was.
- Tests most frequently override the local source (per
  `test_firm.py`'s existing pattern) while letting shared discover from
  env or convention. Putting the more-overridden parameter first matches
  call-site frequency.

The call site for typical test use:

```python
config = load_firm_config(local_path=tmp_path / "local.toml",
                          shared_path=tmp_path / "shared.toml")
```

And for typical production use (both discovered from env or convention):

```python
config = load_firm_config()
```

#### 5.6.2 Module-level public symbols

The `trust_generator.v3.config.firm` module exposes the following
public names (no leading underscore):

**Pydantic models (existing, unchanged):**

- `FirmConfig` — top-level settings model.
- `FirmIdentity`, `Jurisdiction`, `EstateThresholds`,
  `TrusteeCatalog`, `Diagnostics`, `Guardianship`, `Drafts`, `User`,
  `Meta` — sub-models composing `FirmConfig`.

**Loader entry point and exception class (existing names):**

- `FirmConfigError` — umbrella exception class. Continues to cover
  all error paths introduced by this spec; this spec adds message
  variants but no new exception subclasses.
- `load_firm_config` — entry point. Signature changes per 5.6.1.

**Warning classes (new, both subclasses of `UserWarning`):**

- `SharedConfigStalenessWarning` — emitted by the loader when falling
  back to the cached shared file due to availability failure (5.4.4).
- `SharedConfigIntegrityWarning` — emitted by the loader when falling
  back to the cached shared file due to integrity failure (5.4.4.1).

Both warning classes are made public so consuming code (the
diagnostics-engine subscriber per §5.5.5.4, application-level filter
configuration, future surfaces) can route them independently. The two
classes are independent subclasses of `UserWarning`; neither is a
subclass of the other, so consumers can filter or elevate them in any
combination without one category inheriting the other's filter rules.
Justifying the categories on their own filterability merits — a
non-failing signal that consumers may want to handle differently from
other application warnings — is sufficient; no specific consumer
surface (such as a startup banner) is presumed to exist.

**Module-level constants:**

- `ENV_PREFIX = "TGV3_"` — unchanged. Continues to scope the env-var
  overlay for `FirmConfig`'s `BaseSettings` (`firm.py:38`).
- `DEFAULT_LOCAL_CONFIG_PATH = Path("config/firm.toml")` — replaces
  the existing `DEFAULT_CONFIG_PATH`. The rename adds `LOCAL_` for
  parity with the new `CONVENTIONAL_SHARED_CONFIG_PATH` constant
  (5.2.3). The value is unchanged.
- `ENV_VAR_LOCAL_CONFIG_PATH = "TGV3_FIRM_CONFIG"` — replaces the
  existing `ENV_VAR_CONFIG_PATH`. The rename adds `LOCAL_` for parity
  with the new `ENV_VAR_SHARED_CONFIG_PATH` constant. The string
  value is unchanged so existing environment-variable bindings keep
  working.
- `ENV_VAR_SHARED_CONFIG_PATH = "TGV3_FIRM_SHARED_CONFIG"` — new.
  Names the env var consulted by the shared-side discovery chain
  (5.2.2 step 2).

**Module-private symbols (do not depend on these from outside the
package):**

- `_cache_path`, `_discover_local_path`, `_discover_shared_path`,
  `deep_merge`, `_resolve_paths`, `_read_shared_with_fallback`,
  `_read_cache_or_raise`, `_validate_shared_paths_absolute`,
  `_enumerate_path_fields`, `_get_dotted`, `_is_windows_absolute`,
  `_format_duration`, `_write_cache`, `_parse_or_raise`,
  the `CONVENTIONAL_SHARED_CONFIG_PATH` constant, and any error-
  template constants referenced in §6.6 green-phase code.

Tests in the same package may import private symbols directly via
the underscore-prefixed names; external consumers cannot rely on
their existence.

The package's `__init__.py` re-exports the public symbols above and
removes the old constant names from its `__all__`. The constant
renames are part of the no-shim posture (5.6.4): no compatibility
aliases for `DEFAULT_CONFIG_PATH` or `ENV_VAR_CONFIG_PATH` are
retained.

#### 5.6.3 Exception surface

All error paths described in this spec raise `FirmConfigError`. The
spec adds the following message templates to the existing surface; no
new exception subclasses are introduced.

| Trigger | Message template |
|---|---|
| Local file resolved but missing | `local firm.toml not found at <path>` |
| Local file malformed | `local firm.toml at <path> is malformed: <reason>` |
| Shared resolved-but-missing AND cache absent | (multi-line; see 5.4.5) |
| Shared empty bytes AND cache absent | (multi-line; see 5.4.5.1) |
| Shared malformed AND cache absent | (multi-line; see 5.4.5.2) |
| Cache file corrupt | `shared firm.toml cache at <path> is corrupt: <reason>` |
| Shared declares relative path for Path-typed field | `shared firm.toml field <dotted.key> must be absolute or tilde-prefixed; got <value>. Relative paths in shared have ambiguous semantics across workstations and are not permitted.` |
| `LOCALAPPDATA` env var missing on Windows | `LOCALAPPDATA environment variable is not set; cannot determine cache directory.` |
| Path resolution post-validation fails | `firm_config path resolution failed for local=<path>: <reason>` |
| Validation fails on merged dict | (delegated to Pydantic's `ValidationError`, wrapped per existing pattern) |

The single-exception-class posture matches the existing spec's
contract (`FirmConfigError` already covers parse, IO, and validation
errors uniformly). Splitting into specialized subclasses would tempt
callers to branch on type rather than on whether-to-recover, which is
the relevant question; in practice every caller of `load_firm_config`
has the same recovery posture ("this didn't load, surface to the
user and fail-fast"). One exception class matches one recovery
posture.

The two warning classes (`SharedConfigStalenessWarning` and
`SharedConfigIntegrityWarning`) are separate because their semantics
are operationally different — staleness signals "shared was
unavailable, the cache is being used as a known-good fallback"
(routine), while integrity signals "shared was corrupt, the
maintainer must repair it" (non-routine, requires human action).
Routing the two categories to different surfaces preserves the
operational signal each carries.

#### 5.6.4 Backward-compatibility posture

v3 is in pre-stable build-out; no external consumers exist outside
the repo, and no API stability promise has been made for any v3
module. This spec changes `load_firm_config`'s signature and renames
two module-level constants with no compatibility shim. Specifically:

- The previous single-argument form `load_firm_config(path=...)`
  ceases to exist. The keyword `path` is not aliased to `local_path`.
- The constant rename in 5.6.2 (`DEFAULT_CONFIG_PATH` →
  `DEFAULT_LOCAL_CONFIG_PATH`, `ENV_VAR_CONFIG_PATH` →
  `ENV_VAR_LOCAL_CONFIG_PATH`) ships without an alias for the old
  names. Internal callers must update their imports.
- Internal callers within the repo are migrated as part of Cycle 6
  (loader integration). Migration is mechanical: locate calls via
  `rg "load_firm_config\("` and `rg "DEFAULT_CONFIG_PATH|ENV_VAR_CONFIG_PATH"`
  across `src/` and `tests/`, rewrite each to use the new names.
  Tests additionally migrate their fixture patterns per the
  convention described in §6.7.

No deprecation period is observed. The cost of a transition shim
(maintaining both code paths during a deprecation window) outweighs the
benefit (smoother migration for non-existent external consumers).

#### 5.6.5 Idempotence and side-effect inventory

A call to `load_firm_config()` has the following side effects:

- Reads the local file from disk (one open, one read).
- Reads the shared file from disk (one open, one read), OR reads the
  cache file from disk if shared is unavailable.
- On successful load with shared file readable: writes the cache file
  via temp-file-and-rename (one write, one rename).
- On successful load with shared file unavailable: emits exactly one
  `SharedConfigStalenessWarning` via `warnings.warn`.
- On any failure path: raises `FirmConfigError`; no other side effects
  before raising.

The function is idempotent in the sense that calling it twice
back-to-back with identical inputs and identical filesystem state
produces identical `FirmConfig` instances and identical cache file
contents (atomic rename ensures the second call's cache write does not
leave a different artifact than the first's). Mtime updates on the
cache file are not considered a violation of idempotence, since they
encode the wall-clock fact that two calls happened.

## 6. Implementation: TDD cycles

This section prescribes the implementation work as a sequence of inside-out
TDD cycles. Each cycle covers a single design surface meeting the
`design_surface_threshold`: a function with branching logic, a composition of
two or more independently-tested units, a contract surface external consumers
depend on, or a non-obvious failure mode worth pinning. Pure constants,
trivial dataclasses, and one-line passthroughs are not cycled.

Each cycle runs Red → Green → Refactor, with the Refactor stage prescribed
only when the cycle meets the `refactor_threshold` (green-phase code has
structural duplication, nested conditionals that flatten into dispatch, or
orthogonal concerns that extract cleanly). Cycles that do not meet that
threshold explicitly note their absence with reasoning, rather than including
a ceremonial Refactor stage.

### 6.1 Cycle ordering and dependency graph

The ordering is bottom-up: the smallest pure unit first, each subsequent
cycle composing earlier units. Integration emerges from composition rather
than being separately scaffolded.

```
Cycle 1: deep_merge              (pure utility, no dependencies)
    │
    ├─ Cycle 2: discovery       (pure path resolution, no dependencies)
    │
    ├─ Cycle 3: _cache_path     (pure platform branching, no dependencies)
    │     │
    │     └─ Cycle 4: cache writer    (uses Cycle 3)
    │           │
    │           └─ Cycle 5: cache reader / fallback   (uses Cycles 3 + 4)
    │
    └─ Cycle 6: load_firm_config integration   (composes 1, 2, 5)
```

Each arrow is a dependency: the upstream cycle's tests must be green before
the downstream cycle begins. There is no held outer integration test waiting
to flip green at the end; integration is verified by Cycle 6's own test set,
which exercises the full composition end-to-end.

Cycle 1 and Cycle 2 are independent of each other and could be implemented
in either order. The listed order matches conceptual centrality (merge is
the spec's core contribution; discovery is auxiliary).

### 6.2 Cycle 1 — `deep_merge`

The pure dict-merging utility specified in 5.3. No filesystem, no environment,
no time dependencies; takes two `Mapping` inputs and returns a new dict.

#### Red

Write 9 test cases covering the merge-contract surface:

1. `test_both_empty_returns_empty` — `deep_merge({}, {})` returns `{}`.
2. `test_shared_only_passes_through` — keys present only in shared appear
   in the result with shared's values unchanged.
3. `test_local_only_passes_through` — keys present only in local appear
   in the result with local's values unchanged (5.3.5 top-level pass-through).
4. `test_scalar_overlap_local_wins` — when both sources have the same
   non-table non-list key, local's value replaces shared's verbatim.
5. `test_table_overlap_recurses` — when both have a table at the same key,
   the result recurses; values are merged per the same rules at the next
   level.
6. `test_list_overlap_extends_shared_first` — when both have a list at the
   same key, the result is `shared_list + local_list` verbatim, no dedup
   (5.3.2).
7. `test_empty_string_treated_as_unset` — `local = {"k": ""}` against
   `shared = {"k": "value"}` produces `{"k": "value"}` (5.3.3).
8. `test_empty_table_treated_as_no_op` — `local = {"section": {}}` against
   `shared = {"section": {"k": 1}}` produces `{"section": {"k": 1}}`.
9. `test_inputs_not_mutated` — after `deep_merge(s, l)`, the original `s`
   and `l` dicts are unchanged at all nesting levels (5.3.6).

Each test imports `from trust_generator.v3.config.firm import deep_merge`,
which does not yet exist. All 9 fail with `ImportError`. Failure is
meaningful: the absence of the function is the gap the cycle exists to fill.

#### Green

Implement `deep_merge` against the contract in 5.3. A straightforward
recursive walk over the union of keys handles cases 1–6 and 9. Cases 7
and 8 require explicit treatment: an empty string on the local side at a
leaf, and an empty table on the local side at any level, are recognized
as no-ops before they reach the scalar-overwrite branch.

A reasonable first-green shape:

```python
def deep_merge(
    shared: Mapping[str, Any], local: Mapping[str, Any]
) -> dict[str, Any]:
    result: dict[str, Any] = dict(shared)
    for key, local_value in local.items():
        if _is_empty(local_value):
            continue
        if key in result and isinstance(result[key], Mapping) and isinstance(local_value, Mapping):
            result[key] = deep_merge(result[key], local_value)
        elif key in result and isinstance(result[key], list) and isinstance(local_value, list):
            result[key] = list(result[key]) + list(local_value)
        else:
            result[key] = local_value
    return result


def _is_empty(value: Any) -> bool:
    return value == "" or value == {} or value == []
```

All 9 tests pass.

#### Refactor

The initial green has structural duplication: the table branch and the list
branch both check `key in result` plus a per-side `isinstance`. The empty
detection collapses three independent equality checks into one. After
refactor:

```python
def deep_merge(
    shared: Mapping[str, Any], local: Mapping[str, Any]
) -> dict[str, Any]:
    result: dict[str, Any] = dict(shared)
    for key, local_value in local.items():
        if _is_empty(local_value):
            continue
        existing = result.get(key)
        if isinstance(existing, Mapping) and isinstance(local_value, Mapping):
            result[key] = deep_merge(existing, local_value)
        elif isinstance(existing, list) and isinstance(local_value, list):
            result[key] = [*existing, *local_value]
        else:
            result[key] = local_value
    return result


_EMPTY_LITERALS: Final = ("", {}, [])


def _is_empty(value: Any) -> bool:
    return value in _EMPTY_LITERALS
```

The `result.get(key)` consolidates the existence-and-type check into a
single pattern; the unpacking syntax for list concat reads more clearly than
`list() + list()`; the empty-literals tuple makes the rule's surface
explicit and extensible. All 9 tests stay green.

### 6.3 Cycle 2 — Discovery functions

Two parallel three-step discovery chains per 5.2.1 and 5.2.2.

#### Red

Write 8 test cases covering both chains. The autouse `_clean_env` fixture
from the existing `test_firm.py` is extended to also clear
`TGV3_FIRM_SHARED_CONFIG`.

1. `test_local_explicit_arg_wins` — explicit `local_path` argument
   short-circuits env and convention.
2. `test_local_env_var_used_when_no_arg` — `TGV3_FIRM_CONFIG` is consulted
   when arg is None.
3. `test_local_convention_used_when_no_env` — `<repo>/config/firm.toml`
   is the default when arg and env are both absent.
4. `test_shared_explicit_arg_wins` — mirror of 1 for shared.
5. `test_shared_env_var_used_when_no_arg` — mirror of 2 for shared,
   reading `TGV3_FIRM_SHARED_CONFIG`.
6. `test_shared_convention_uses_path_constant` — the
   `CONVENTIONAL_SHARED_CONFIG_PATH` constant is the default.
7. `test_shared_path_expanduser_applied` — a `~`-prefixed path returned
   from any discovery step is expanded against the current home directory.
8. `test_local_and_shared_independent` — explicit `local_path` does not
   affect shared discovery, and vice versa.

All fail because `_discover_local_path` and `_discover_shared_path` do not
yet exist.

#### Green

Implement two helpers with the same shape:

```python
def _discover_local_path(arg: Path | None) -> Path:
    if arg is not None:
        return arg.expanduser().resolve(strict=False)
    env = os.environ.get("TGV3_FIRM_CONFIG")
    if env:
        return Path(env).expanduser().resolve(strict=False)
    return (Path.cwd() / "config" / "firm.toml").resolve(strict=False)


def _discover_shared_path(arg: Path | None) -> Path:
    if arg is not None:
        return arg.expanduser().resolve(strict=False)
    env = os.environ.get("TGV3_FIRM_SHARED_CONFIG")
    if env:
        return Path(env).expanduser().resolve(strict=False)
    return CONVENTIONAL_SHARED_CONFIG_PATH.expanduser().resolve(strict=False)
```

The `CONVENTIONAL_SHARED_CONFIG_PATH` module constant is added at this point
(the constant itself is not a design surface; it gets introduced as part of
Green).

All 8 tests pass.

#### Refactor

No refactor stage — green output is already minimal. The two helpers'
shared shape (arg → env → default, with uniform `expanduser` + `resolve`)
is already factored: each helper is three lines of dispatch plus a single
default. Extracting the common shape into a higher-order helper would add
an abstraction layer (e.g., `_discover(arg, env_var, default)`) for two
call sites that diverge only on string literals. The cost of the
abstraction (one more name, one more call frame, indirection on every
lookup) outweighs the benefit (saving ~3 duplicated lines).

### 6.4 Cycle 3 — `_cache_path`

Pure platform-branching helper resolving the cache file location per 5.4.1.

#### Red

4 test cases:

1. `test_windows_uses_localappdata` — with `sys.platform == "win32"` and
   `LOCALAPPDATA` set in the environment, the returned path is
   `<LOCALAPPDATA>/trust-generator/firm.shared.cache.toml`.
2. `test_windows_missing_localappdata_raises` — with `sys.platform == "win32"`
   and `LOCALAPPDATA` unset, `_cache_path()` raises `FirmConfigError`.
3. `test_posix_uses_xdg_cache_home_when_set` — with non-Windows platform
   and `XDG_CACHE_HOME` set, the returned path is
   `<XDG_CACHE_HOME>/trust-generator/firm.shared.cache.toml`.
4. `test_posix_falls_back_to_home_cache` — with non-Windows platform and
   `XDG_CACHE_HOME` unset, the returned path is
   `~/.cache/trust-generator/firm.shared.cache.toml`.

Tests use `monkeypatch` to set `sys.platform` and the relevant environment
variables. All fail because `_cache_path` does not exist.

#### Green

Implement per 5.4.1:

```python
def _cache_path() -> Path:
    if sys.platform == "win32":
        local_appdata = os.environ.get("LOCALAPPDATA")
        if not local_appdata:
            raise FirmConfigError(
                "LOCALAPPDATA environment variable is not set; "
                "cannot determine cache directory."
            )
        cache_dir = Path(local_appdata) / "trust-generator"
    else:
        xdg = os.environ.get("XDG_CACHE_HOME")
        cache_dir = (Path(xdg) if xdg else Path.home() / ".cache") / "trust-generator"
    return cache_dir / "firm.shared.cache.toml"
```

All 4 tests pass.

#### Refactor

No refactor stage — green output is already minimal. The function has two
platform branches and one literal filename suffix; there is no further
compression available. Extracting the filename to a constant would be
premature — it is referenced exactly once.

### 6.5 Cycle 4 — Cache writer

Atomic verbatim-byte write of shared file content to the cache path, with
write-failure-as-warning policy per 5.4.2.

#### Red

6 test cases. Tests use `tmp_path` for the cache directory via
`monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))`.

1. `test_cache_write_creates_file` — calling `_write_cache(bytes_content)`
   produces a file at the resolved cache path with the given bytes.
2. `test_cache_write_creates_parent_directory` — if the parent directory
   does not exist, it is created.
3. `test_cache_write_is_atomic` — a successful write leaves no
   `firm.shared.cache.toml.tmp` artifact behind.
4. `test_cache_write_overwrites_existing` — a second call with different
   bytes replaces the first call's content.
5. `test_cache_write_updates_mtime` — mtime after a write is within 5
   seconds of `time.time()`.
6. `test_cache_write_failure_emits_warning_not_error` — if the write
   raises (simulated by chmodding the cache directory unwriteable), the
   function emits a warning and returns rather than raising.

All fail because `_write_cache` does not exist.

#### Green

Implement per 5.4.2:

```python
def _write_cache(content: bytes) -> None:
    target = _cache_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_bytes(content)
        os.replace(tmp, target)
    except OSError as exc:
        warnings.warn(
            f"failed to update shared firm.toml cache: {exc}",
            stacklevel=2,
        )
```

All 6 tests pass. Test 6 uses `pytest.warns(UserWarning)` to assert the
warning emission.

#### Refactor

Conditional refactor opportunity: the temp-file creation, byte-write, and
rename are three operations the green-phase code presents inline. For
failure-path testing it is sometimes useful to factor the“write-bytes-and-rename”
sequence into its own helper so a test can simulate failure at the rename
step specifically. However, the current test set does not differentiate
failure modes — test 6 treats any `OSError` uniformly — and adding the
factoring purely for hypothetical future tests is YAGNI.

Decision: no refactor stage. The 9 lines of green-phase code are already
minimal and the test set does not motivate further factoring.

### 6.6 Cycle 5 — Cache reader and fallback

The four-case fallback decision tree per 5.4.3, plus the staleness
warning per 5.4.4, the integrity warning per 5.4.4.1, and the three
error variants per 5.4.5 / 5.4.5.1 / 5.4.5.2. The helper's return
contract is `tuple[bytes, dict[str, Any], bool]` per the helper-return-
shape contract in 5.4.7: bytes (verbatim source content for cache write
gating), parsed dict (consumed by 6.7's merge step without re-parsing),
and `used_cache` boolean (consumed by 6.7's cache-write gate).

#### Red

12 test cases. The autouse fixture sets `XDG_CACHE_HOME` to `tmp_path`
so every test has an isolated cache. Tests use `pytest.warns` and
`pytest.raises` per case.

**Happy-path:**

1. `test_shared_present_reads_shared` — when the shared path exists,
   non-empty, and parses cleanly, the function returns
   `(content_bytes, parsed_dict, used_cache=False)`; no warning is
   emitted.

**Availability-fallback (case 2):**

2. `test_shared_missing_cache_present_uses_cache_with_staleness_warning`
   — when the shared path does not exist but the cache does, the
   function returns `(cache_bytes, parsed_cache_dict,
   used_cache=True)` and emits exactly one
   `SharedConfigStalenessWarning`.
3. `test_shared_missing_cache_present_warning_includes_age` — the
   warning message includes the cache file's age in human-readable
   form.
4. `test_shared_missing_cache_missing_raises_onboarding_error` — when
   both are missing, `FirmConfigError` is raised with both paths named
   in the message and the message contains "no cached copy exists".
5. `test_shared_missing_cache_corrupt_raises_corruption_error` — when
   shared is missing and cache exists but fails to parse,
   `FirmConfigError` is raised naming the cache path with the word
   "corrupt".

**Empty-shared-fallback (case 3):**

6. `test_shared_empty_bytes_falls_back_to_cache_with_staleness_warning`
   — when the shared file exists but `read_bytes()` returns `b""` and
   the cache exists, the function returns
   `(cache_bytes, parsed_cache_dict, used_cache=True)` and emits
   exactly one `SharedConfigStalenessWarning` whose message contains
   "advertised but empty".
7. `test_shared_empty_bytes_no_cache_raises_empty_shared_error` — when
   the shared file exists but is empty and the cache does not exist,
   `FirmConfigError` is raised with the message containing
   "unexpectedly empty" and "OneDrive placeholder state" per 5.4.5.1.

**Integrity-fallback (case 4):**

8. `test_shared_malformed_falls_back_to_cache_with_integrity_warning`
   — when the shared file is reachable but TOML-malformed and the
   cache exists, the function returns
   `(cache_bytes, parsed_cache_dict, used_cache=True)` and emits
   exactly one `SharedConfigIntegrityWarning` (NOT a
   `SharedConfigStalenessWarning`).
9. `test_shared_malformed_no_cache_raises_integrity_error` — when the
   shared file is malformed and the cache does not exist,
   `FirmConfigError` is raised with the message containing "is
   malformed" and "no cached copy exists to fall back to" per 5.4.5.2.
10. `test_integrity_warning_distinct_from_staleness_warning` — both
    warning classes are subclasses of `UserWarning`, but neither is a
    subclass of the other (verified via `issubclass` assertions in
    both directions).

**Single-emission and category properties:**

11. `test_warning_emitted_exactly_once_per_call` — a single fallback
    produces exactly one warning, not multiple.
12. `test_used_cache_boolean_matches_fallback_decision` — for every
    case 2/3/4 invocation, the returned `used_cache` boolean is
    `True`; for every case 1 invocation, it is `False`. Pinned via
    parameterized cases covering all four branches.

**Encoding tolerance (round-2 plan-review):**

13. `test_shared_with_utf8_bom_loads_normally` — a shared file
    saved with a UTF-8 BOM (`\xef\xbb\xbf` byte prefix) loads
    successfully via the helper's `decode("utf-8-sig")` and routes
    to case 1 (happy path), not to integrity-fallback. Pinned
    because some Windows editors save TOML with a BOM by default,
    and a maintainer using such an editor should not silently
    break every workstation.

All fail because the read function, the two warning classes, and the
empty-shared error variant do not exist.

#### Green

Implement the read-with-fallback function and both warning classes:

```python
class SharedConfigStalenessWarning(UserWarning):
    """Emitted when the loader falls back to a cached shared config
    copy due to availability failure (file missing, OSError, or empty
    bytes consistent with OneDrive placeholder state)."""


class SharedConfigIntegrityWarning(UserWarning):
    """Emitted when the loader falls back to a cached shared config
    copy due to integrity failure (file present and non-empty but
    TOML-malformed). Distinct from SharedConfigStalenessWarning so
    consumers can route the categories to different surfaces; see
    5.4.4.1 for the operational semantics."""


def _read_shared_with_fallback(
    shared_path: Path,
) -> tuple[bytes, dict[str, Any], bool]:
    """Read shared TOML, falling back to cache on any availability or
    integrity failure.

    Returns (bytes, parsed_dict, used_cache). The bytes are the
    verbatim source content (used by 6.7 to gate cache writing). The
    parsed_dict is the result of parsing those bytes, returned to
    avoid double-parse (5.4.7). The boolean indicates whether the
    fallback path was taken.

    Raises FirmConfigError when both shared and cache are unavailable,
    with case-specific message variants per 5.4.5 / 5.4.5.1 / 5.4.5.2.
    """
    # Case 2: file missing or unreadable → availability-fallback.
    if not shared_path.exists():
        return _read_cache_or_raise(
            shared_path,
            warning_class=SharedConfigStalenessWarning,
            warning_phrasing="unreachable",
            no_cache_error_template=_ONBOARDING_ERROR_TEMPLATE,
        )
    try:
        content = shared_path.read_bytes()
    except OSError:
        return _read_cache_or_raise(
            shared_path,
            warning_class=SharedConfigStalenessWarning,
            warning_phrasing="unreachable",
            no_cache_error_template=_ONBOARDING_ERROR_TEMPLATE,
        )

    # Case 3: empty bytes → availability-fallback (OneDrive placeholder).
    if not content:
        return _read_cache_or_raise(
            shared_path,
            warning_class=SharedConfigStalenessWarning,
            warning_phrasing="advertised but empty",
            no_cache_error_template=_EMPTY_SHARED_ERROR_TEMPLATE,
        )

    # Case 4: parse-fail → integrity-fallback.
    try:
        parsed = tomllib.loads(content.decode("utf-8-sig"))
    except tomllib.TOMLDecodeError as exc:
        return _read_cache_or_raise(
            shared_path,
            warning_class=SharedConfigIntegrityWarning,
            warning_phrasing=f"is malformed (TOML parse error: {exc})",
            no_cache_error_template=_INTEGRITY_ERROR_TEMPLATE,
            integrity_reason=str(exc),
        )

    # Case 1: happy path.
    return content, parsed, False
```

The error templates `_ONBOARDING_ERROR_TEMPLATE`,
`_EMPTY_SHARED_ERROR_TEMPLATE`, and `_INTEGRITY_ERROR_TEMPLATE` are
module-level format strings matching the verbatim text in 5.4.5,
5.4.5.1, and 5.4.5.2. They are not design surfaces; they are
implementation detail of the helper.

The `_read_cache_or_raise` helper:

```python
def _read_cache_or_raise(
    shared_path: Path,
    *,
    warning_class: type[UserWarning],
    warning_phrasing: str,
    no_cache_error_template: str,
    integrity_reason: str | None = None,
) -> tuple[bytes, dict[str, Any], bool]:
    cache = _cache_path()
    if not cache.exists():
        raise FirmConfigError(
            no_cache_error_template.format(
                shared_path=shared_path,
                cache=cache,
                integrity_reason=integrity_reason or "",
            )
        )
    content = cache.read_bytes()
    try:
        parsed = tomllib.loads(content.decode("utf-8-sig"))
    except tomllib.TOMLDecodeError as exc:
        raise FirmConfigError(
            f"shared firm.toml cache at {cache} is corrupt: {exc}"
        ) from exc
    age_seconds = time.time() - cache.stat().st_mtime
    age_str = _format_duration(age_seconds)
    warnings.warn(
        f"shared firm.toml at {shared_path} {warning_phrasing}; "
        f"falling back to cached copy ({age_str} old).\n"
        f"  source: {shared_path}\n  cache:  {cache}",
        category=warning_class,
        stacklevel=3,
    )
    return content, parsed, True
```

A `_format_duration` helper (not a design surface; one-line
passthrough around `datetime.timedelta`) handles the age formatting.
All 12 tests pass.

#### Refactor

The green output already factors the dispatch through
`_read_cache_or_raise`'s parameter-driven branching: a single helper
serves all three fallback paths (availability-missing,
availability-empty, integrity-malformed) by varying its
`warning_class`, `warning_phrasing`, and `no_cache_error_template`
arguments. The four cases of `_read_shared_with_fallback` each
produce a distinct call shape (or a happy-path return); there is no
remaining structural duplication that flattens cleanly.

One micro-refactor opportunity: the four `if not / try / except`
branches in `_read_shared_with_fallback` could collapse into a
dispatch table mapping `(file_exists, read_succeeded, parse_succeeded)
→ (warning_class, phrasing, template, integrity_reason)`. The cost
(an extra abstraction layer; an indirection on every call) exceeds
the benefit (4 lines saved, dispatch becomes harder to read for the
narrow benefit of being slightly more uniform). Per the
`refactor_threshold` discipline (§6 preamble), this is YAGNI.

**Decision: no further refactor stage.** The green-phase factoring
already addresses the predecessor draft's dispatch-flattening
motivation (the `_parse_or_raise` extraction collapsed the duplicated
try/except). Reverting the predecessor's return-shape simplification
(per the C1 finding in plan-review) reintroduces the boolean and the
parsed dict as load-bearing return-channel components, which Cycle 6
then consumes directly without re-deriving via `exists()`.

All 12 tests stay green.

##### Note on the C1 finding

Plan-review flagged that the predecessor draft's Cycle 5 refactor —
which simplified the return type from `tuple[bytes, bool]` to bare
`bytes` and offloaded the cache-decision signal to a re-`exists()`
check in Cycle 6 — introduced a TOCTOU window where mid-load
file-appears or file-disappears events would corrupt the cache mtime
or skip a cache write. The current Cycle 5 design returns
`tuple[bytes, dict[str, Any], bool]` precisely so Cycle 6 consumes
the boolean directly without re-querying. The predecessor's
"marginally less-redundant" framing of the alternative (single-value
return) was correct in style but wrong in correctness: the redundancy
the spec accepted was the TOCTOU window itself.

The dispatch-flattening that motivated the predecessor refactor is
preserved in the current Green phase via the
`_read_cache_or_raise(*, warning_class, warning_phrasing,
no_cache_error_template, integrity_reason)` parameter-driven helper.
That factoring serves the original intent (no duplicated try/except
across cases) without coupling the caller to a re-existence check.

### 6.7 Cycle 6 — `load_firm_config` integration

Wires Cycles 1, 2, and 5 into the public entry point. Adds the cache
write from Cycle 4 to the success path. Adds the shared-side relative-
path validator (5.3.7.4) and the post-merge `_resolve_paths` step
(5.3.7.2). Migrates existing `test_firm.py` from the single-file
fixture pattern to the two-file pattern, including the constant rename
per 5.6.2.

#### Red

11 test cases plus the migration of all existing tests in
`test_firm.py`. The new tests:

**Core integration:**

1. `test_load_with_explicit_paths_succeeds` — calling
   `load_firm_config(local_path=L, shared_path=S)` with valid files at
   L and S returns a `FirmConfig` reflecting the merged values.
2. `test_load_writes_cache_on_success` — after a successful load with
   reachable shared, the cache file exists at `_cache_path()` and its
   bytes equal the shared file's bytes.
3. `test_load_default_paths_use_discovery_chains` — calling
   `load_firm_config()` with no arguments triggers both discovery
   chains independently. Verified by `monkeypatch`-ing both env vars
   and asserting the returned config reflects both env-pointed files.
4. `test_load_keyword_path_alias_not_supported` — calling
   `load_firm_config(path=...)` raises `TypeError`. Confirms the v3
   no-shim posture from 5.6.4.

**Cache-write gating (consumes the helper's `used_cache` boolean):**

5. `test_load_uses_cache_when_shared_missing` — with a pre-populated
   cache and a missing shared file, the load succeeds and emits one
   `SharedConfigStalenessWarning`.
6. `test_load_no_cache_write_on_availability_fallback` — a case-2/3
   fallback load does not modify the cache file's mtime. Pinned by
   recording the cache mtime before the load and asserting it is
   unchanged after.
7. `test_load_no_cache_write_on_integrity_fallback` — a case-4
   fallback load (shared-malformed → cache used, integrity warning)
   does not modify the cache file's mtime. Pinned the same way as #6.
   This test specifically verifies the C1-fix property: even when
   `resolved_shared.exists()` returns True (the shared file is
   present), the helper's `used_cache=True` return correctly gates
   the write off.
8. `test_load_validation_error_does_not_write_cache` — if the merged
   dict fails Pydantic validation, the cache file is not updated.
   (The load raises; verify cache mtime is unchanged.)

**Path resolution in two-source mode (5.3.7):**

9. `test_relative_paths_resolve_against_local_parent` — replaces the
   existing `test_relative_paths_resolve_against_config_parent`. With
   `audit_log_dir = "./relative/audit"` declared in LOCAL (not
   shared), the resolved path is
   `(resolved_local.parent / "relative/audit").resolve()`. Pinned
   with the local file in a `nested/` subdirectory so the difference
   between local-parent and CWD is observable.
10. `test_shared_side_relative_path_rejected` — with
    `audit_log_dir = "./relative/audit"` declared in SHARED, the
    load raises `FirmConfigError` whose message contains the dotted
    key (`"diagnostics.audit_log_dir"`) and the rejected value, per
    5.3.7.3. Verified across all three Path-typed fields
    (`trustee_catalog.db_path`, `diagnostics.audit_log_dir`,
    `diagnostics.rules_dir`).

**`${user.upn}` substitution:**

11. `test_user_upn_substitution_uses_post_merge_user_value` —
    confirms the substitution timing per 5.3.7.2: shared declares
    `audit_log_dir = "~/firm-logs/users/${user.upn}/logs"`, local
    declares `[user] upn = "testuser"`, and the resolved path
    contains `testuser`. Pins that the substitution happens after
    merge, against the merged dict's `user.upn`.

**Shared completeness check (§5.4.8) — round-3 plan-review:**

12. `test_load_partial_shared_falls_back_to_cache_with_integrity_warning`
    — with a pre-populated cache and a shared file that parses
    cleanly but is missing one of `_SHARED_REQUIRED_SECTIONS` (test
    parameterizes across `firm`, `estate_thresholds`, `diagnostics`),
    the load succeeds using cache content and emits exactly one
    `SharedConfigIntegrityWarning` whose message names the missing
    section(s). The cache file's mtime is unchanged after the load
    (no cache write on integrity-fallback per 5.4.8.3).
13. `test_load_partial_shared_no_cache_raises_with_missing_sections_message`
    — with no cache and a shared file missing one of
    `_SHARED_REQUIRED_SECTIONS`, the load raises `FirmConfigError`
    per 5.4.5.2; the message contains "missing required section(s)"
    and names the specific section list.

**Walker coverage tripwire (§5.3.7.5) — round-3 plan-review:**

14. `test_enumerate_path_fields_yields_known_set` — asserts that
    `set(_enumerate_path_fields(FirmConfig))` equals exactly
    `{"trustee_catalog.db_path", "diagnostics.audit_log_dir",
    "diagnostics.rules_dir"}`. Pins the walker's coverage at the
    unit level; would fail loudly if a regression caused the
    walker to yield zero matches (which would silently leave the
    shared-side prohibition unenforced).

All fail because `load_firm_config` has the old single-argument
signature, the helper's return type does not yet support unpacking,
the shared-path-validator does not exist, the
`_SHARED_REQUIRED_SECTIONS` constant does not exist, and the
completeness check is not yet wired into the integration.

Additionally, every existing test in `test_firm.py` is updated:

- Constants imported from `trust_generator.v3.config` change names per
  5.6.2: `DEFAULT_CONFIG_PATH` → `DEFAULT_LOCAL_CONFIG_PATH`,
  `ENV_VAR_CONFIG_PATH` → `ENV_VAR_LOCAL_CONFIG_PATH`, plus a new
  import for `ENV_VAR_SHARED_CONFIG_PATH`. `ENV_PREFIX` is
  unchanged.
- `test_constants_match_spec` is rewritten to assert the new
  constant names and add the shared-side env-var-name assertion.
- `_clean_env` autouse fixture is unchanged (it scopes by
  `ENV_PREFIX`, which still covers both the local and shared env
  vars).
- `WELL_FORMED` / `MINIMAL` split into `WELL_FORMED_SHARED` /
  `WELL_FORMED_LOCAL` / `MINIMAL_SHARED` / `MINIMAL_LOCAL` per the
  Migration subsection below.
- `test_relative_paths_resolve_against_config_parent` is renamed to
  `test_relative_paths_resolve_against_local_parent` and adjusted to
  declare the relative paths in LOCAL (not shared).
- `test_path_resolution_errors_wrapped_as_firm_config_error` is
  retained verbatim — `_resolve_paths` still runs at the same point
  in the load pipeline; only the anchor identity changed.
- All other call sites switch from `load_firm_config(path)` to
  `load_firm_config(local_path=..., shared_path=...)`.

#### Green

Rewrite `load_firm_config` to consume the helper's three-tuple return
and add `_resolve_paths`:

```python
def load_firm_config(
    local_path: Path | None = None,
    shared_path: Path | None = None,
) -> FirmConfig:
    resolved_local = _discover_local_path(local_path)
    resolved_shared = _discover_shared_path(shared_path)

    if not resolved_local.exists():
        raise FirmConfigError(
            f"local firm.toml not found at {resolved_local}"
        )

    # Cycle 5 helper: returns (bytes, parsed_dict, used_cache).
    # Single-parse contract per 5.4.7; used_cache is the authoritative
    # signal for cache-write gating (no re-derivation via exists()).
    shared_bytes, shared_dict, used_cache = _read_shared_with_fallback(
        resolved_shared
    )

    # Shared completeness check per §5.4.8. If shared was reachable
    # (used_cache is False) but is missing required sections, route
    # to the integrity-fallback path. Cache-side reads (used_cache
    # already True) cannot be partial — a parsed cache that is missing
    # required sections is a corrupt cache, surfaced separately.
    if not used_cache:
        missing = _SHARED_REQUIRED_SECTIONS - set(shared_dict.keys())
        if missing:
            shared_bytes, shared_dict, used_cache = _read_cache_or_raise(
                resolved_shared,
                warning_class=SharedConfigIntegrityWarning,
                warning_phrasing=(
                    f"is missing required section(s) "
                    f"{sorted(missing)} (likely partial OneDrive sync)"
                ),
                no_cache_error_template=_INTEGRITY_ERROR_TEMPLATE,
                integrity_reason=(
                    f"missing required section(s): {sorted(missing)}"
                ),
            )

    # Shared-side relative-path validator (5.3.7.3 / 5.3.7.4). Runs
    # against the parsed shared dict before merge, so violations are
    # caught with source-attributed error messages. Note: if the
    # completeness check above re-routed to cache, shared_dict now
    # holds the cache content; the validator runs against THAT
    # content. Cache content was previously written from a known-good
    # shared (per 5.4.2 + 5.4.8 cache-write gate), so re-validating
    # is consistent: the cache cannot contain shared-side relative
    # paths because such paths would have failed validation at the
    # original write time and the cache write is gated behind
    # successful validation.
    _validate_shared_paths_absolute(shared_dict)

    local_bytes = resolved_local.read_bytes()
    try:
        local_dict = tomllib.loads(local_bytes.decode("utf-8-sig"))
    except tomllib.TOMLDecodeError as exc:
        raise FirmConfigError(
            f"local firm.toml at {resolved_local} is malformed: {exc}"
        ) from exc

    merged = deep_merge(shared_dict, local_dict)

    try:
        config = FirmConfig(**merged)
    except ValidationError as exc:
        raise FirmConfigError(str(exc)) from exc

    # Path resolution per 5.3.7: anchor at resolved_local.parent;
    # ${user.upn} substitution scoped to diagnostics.audit_log_dir;
    # expanduser then absolutize.
    try:
        config = _resolve_paths(config, resolved_local.parent)
    except (OSError, RuntimeError) as exc:
        raise FirmConfigError(
            f"firm_config path resolution failed for "
            f"local={resolved_local}: {exc}"
        ) from exc

    # Cache write gated on the helper's authoritative used_cache signal.
    # No re-query of resolved_shared.exists() here — that re-query is
    # the TOCTOU window the C1 finding closed.
    if not used_cache:
        _write_cache(shared_bytes)

    return config
```

`_validate_shared_paths_absolute` is the helper specified in 5.3.7.4:

```python
def _validate_shared_paths_absolute(
    shared_dict: dict[str, Any],
    schema: type[BaseModel] = FirmConfig,
) -> None:
    for dotted_key in _enumerate_path_fields(schema):
        value = _get_dotted(shared_dict, dotted_key)
        if value is None:
            continue
        if not (
            value.startswith("/")
            or value.startswith("~")
            or _is_windows_absolute(value)
        ):
            raise FirmConfigError(
                f"shared firm.toml field {dotted_key} must be absolute or "
                f"tilde-prefixed; got {value!r}. Relative paths in "
                f"shared have ambiguous semantics across workstations "
                f"and are not permitted."
            )
```

`_enumerate_path_fields`, `_get_dotted`, and `_is_windows_absolute`
are one-line helpers that are not design surfaces in their own right.

All 11 new tests plus the migrated existing tests pass.

#### Refactor

The integration is now an 11-step linear sequence (resolve local,
resolve shared, check local exists, read shared via helper, validate
shared paths, read local bytes, parse local, merge, validate via
Pydantic, resolve paths, gate cache write, return). There is no
structural duplication and no nested conditionals. The composition
is intentional and reads top-to-bottom.

**Decision: no refactor stage.** Per `refactor_threshold` discipline,
no extraction is motivated by the green-phase code.

#### Migration of existing test fixtures

The existing `test_firm.py` defines `WELL_FORMED` and `MINIMAL` as
module-level TOML strings. The migration splits each into shared/local
pairs:

```python
WELL_FORMED_SHARED = """
[firm]
name = "Test Firm LLP"
phone = "(555) 555-5555"

[firm.office_address]
street = "1 Main St."
city = "Rockford"
state = "IL"
zip_code = "61114"

[jurisdiction]
default_state = "Illinois"
default_county = "Winnebago"
trust_code_citation = "Illinois Trust Code (760 ILCS 3/101, et seq.)"
"""

WELL_FORMED_LOCAL = """
[user]
upn = "testuser"
"""
```

`MINIMAL_SHARED` and `MINIMAL_LOCAL` follow the same split shape.
The `_write` helper is updated to take a target path explicitly
(rather than inferring from a single `tmp_path/firm.toml` convention).
Tests that previously called `_write(tmp_path / "firm.toml",
WELL_FORMED)` become `_write(tmp_path / "local.toml",
WELL_FORMED_LOCAL)` and `_write(tmp_path / "shared.toml",
WELL_FORMED_SHARED)`, with `load_firm_config(local_path=...,
shared_path=...)` consuming both.

For tests that previously appended a section to `WELL_FORMED` (e.g.,
`test_relative_paths_resolve_against_config_parent`,
`test_user_upn_substitution_in_audit_log_dir`), the appended section
goes into `WELL_FORMED_LOCAL` if the test exercises a local-side
override path or into `WELL_FORMED_SHARED` if the test exercises
firm-wide defaults. The renamed
`test_relative_paths_resolve_against_local_parent` puts the
relative-path declaration in LOCAL because §5.3.7.3 forbids relative
paths in shared.

The migration is mechanical and is included as part of Cycle 6's
Green.

## 7. Open seams

The design intentionally leaves the following surfaces unimplemented.
Future specs may address them; this spec does not.

- **Shared-file polling.** The loader reads shared at
  `load_firm_config()` call time only. No background polling, no
  inotify-style watchers, no scheduled re-reads. A configuration change
  on SharePoint takes effect on the next call, which typically means the
  next application start.
- **Loader-initiated shared-file writes.** The loader never writes to
  the shared file. All shared-file edits are SharePoint-side maintainer
  actions through the SharePoint web UI or a synced editor.
- **Multi-shared-file composition.** Exactly one shared file. There is
  no mechanism to layer multiple shared sources (e.g., a
  practice-area-specific shared file overlaying a firm-wide one).
- **Per-workstation file editor surface.** The loader reads the local
  file but provides no API for writing it. Local-file edits are paralegal-
  onboarding-side actions, owned by Plan 6.
- **List-shrink syntax.** Per 5.3.2, EXTEND-only list semantics mean
  per-workstation files cannot remove entries from shared's lists. No
  escape-hatch syntax exists today; introducing one is a future spec
  triggered by an actual need.
- **Cache-invalidation API.** The cache refreshes only via the
  next-successful-load mechanism (5.4.6). There is no public
  "force refresh" or "invalidate cache" entry point.
- **Cross-process cache contention handling.** The atomic-write semantics
  (5.4.2) make concurrent writes safe in the sense that no half-written
  cache file is ever observable, but there is no coordination between
  processes; last-write-wins is the contract.
- **Type-source-attributed validation errors.** Per 5.3.4, type mismatches
  surface through Pydantic's standard error path, which names the field
  but not the source file. A future config-editor GUI may need
  source-attribution; the loader provides no hooks for this today.
- **Maintainer-side smoke-test workflow.** A short script the
  maintainer runs post-edit that does a clean `load_firm_config()`
  against production-conventional paths and reports success/failure.
  Provides faster feedback on shared-file integrity than the
  diagnostics-engine subscriber's post-hoc audit log (§5.5.5.4).
  Cross-reference: §5.4.4.2 names this seam in the context of the
  maintainer-notification recovery loop. Out of scope for this spec;
  scripting and integration belong in a later operational chore or
  a `maintainer-tools` plan.

## 8. Migration from current single-file state

The current `config/firm.toml` is a single file containing every section
including `[user]`. Migration splits its content across two files and
uploads one to SharePoint.

### 8.1 Pre-migration state

- `config/firm.toml` exists in the repo, version-controlled.
- The maintainer's workstation is the only environment running the v3
  code today.
- No SharePoint shared file exists yet at the conventional path.
- No cache file exists at any workstation.

### 8.2 Migration steps

Execute in order. The sequence is structured so that no committed
state references infrastructure that has not been verified working.
Specifically, step 5 (which commits the stripped local-only
`config/firm.toml` to the repo) does not run until step 4 confirms
that production-shape `load_firm_config()` succeeds against the
maintainer's workstation paths.

The Cycle 6 loader implementation is presumed to have landed in main
BEFORE migration begins. To eliminate the broken-pull window the
plan-review (round 2) flagged, **the Cycle 6 PR itself includes the
dev-environment template** (`config/firm.shared.dev.toml`) per §8.4
— so any developer pulling main from the moment Cycle 6 lands has a
self-service shared-config option, without waiting for the
maintainer's migration session to commit it later.

#### Step 0 (part of Cycle 6 PR, NOT part of the migration session)

**Commit the dev-environment template** at
`config/firm.shared.dev.toml` AS PART OF the Cycle 6 PR. The content
is the not-yet-stripped section payload that will eventually move to
SharePoint — i.e., everything in today's `config/firm.toml` EXCEPT
`[user]`. Authoring this template at Cycle 6 PR time is mechanical:
copy the relevant sections from the existing single-file
`config/firm.toml` into `config/firm.shared.dev.toml` and commit
both as part of the same PR.

Until the migration session begins, the dev template's content
duplicates what is also in `config/firm.toml`. That duplication is
intentional and lasts only until step 5 strips the duplicated
sections from the local file. During this window, devs without
OneDrive can either set `TGV3_FIRM_SHARED_CONFIG=$(realpath
config/firm.shared.dev.toml)` or rely on the still-complete
`config/firm.toml` as both local and shared (via env-var
override pointing both env vars at the same file).

#### Migration-session steps (run by the maintainer in one sitting)

1. **Author the shared file** at
   `<sync-root>/Crosby and Crosby LLP/internal-applications - trust-generator/firm/config/firm.toml`
   on the maintainer's workstation. Content: every section of the
   current `config/firm.toml` EXCEPT `[user]`. The file syncs to
   SharePoint via OneDrive automatically once written.
2. **Verify SharePoint sync round-trip.** Confirm the file appears in
   the SharePoint web UI at the corresponding library path. Confirm
   the library's permission groups (5.5.1) are configured: Members =
   maintainer, Visitors = paralegal group. Wait for OneDrive to
   report the file as fully synced (not just "uploading"); the
   conventional path on the maintainer's workstation must report
   `Path.exists() is True` and `read_bytes()` must return non-empty
   content matching what was authored in step 1.
3. **Run the test suite.** All migrated tests in `test_firm.py` must
   pass. Tests use `tmp_path` and explicit `local_path=`/`shared_path=`
   arguments, so they are independent of the conventional path's
   state — they pass regardless of whether step 1 has propagated.
   This step verifies the loader code is healthy.
4. **(NEW) Production-path verification — DO NOT COMMIT YET.** On the
   maintainer's workstation, with no `TGV3_FIRM_CONFIG` or
   `TGV3_FIRM_SHARED_CONFIG` env vars set, run a short Python
   invocation that calls `load_firm_config()` (no arguments,
   triggering both conventional discovery chains) against the
   *current* (not yet stripped) `config/firm.toml` AND the just-
   authored shared file. Expected behavior: both files load
   successfully; the merge produces a `FirmConfig` whose values
   match the pre-migration single-file load; no warnings are
   emitted. If anything fails, return to step 1; the shared file or
   the OneDrive sync needs fixing.
5. **Strip non-`[user]` sections from `config/firm.toml` and commit.**
   With step 4a green, commit the stripped local file. The local
   file now contains only `[user] upn = "zramdass"` (plus optional
   `[meta]`). This is the first migration step that produces a
   permanent main-branch artifact.
6. **Re-run production-path verification.** Same invocation as step
   4a, but now against the stripped local file. Expected behavior:
   load succeeds; the merged `FirmConfig` is identical to step 4a's
   output (because all stripped content moved to shared, not
   disappeared); no warnings.
7. **Confirm the cache file is written.** After the load in step 6,
   verify a file exists at the platform-conventional cache path
   (`%LOCALAPPDATA%/trust-generator/firm.shared.cache.toml` on
   Windows; `${XDG_CACHE_HOME:-~/.cache}/trust-generator/firm.shared.cache.toml`
   on POSIX). This confirms the cache write path works end-to-end.
8. **Tag migration complete.** No further migration actions required.
   Subsequent shared-file edits happen through SharePoint; subsequent
   local-file edits happen on the workstation directly.

### 8.3 Rollback

The rollback story differs by step:

- **Failure during steps 1, 2, 3, or 4** — these have not yet
  modified main-branch state. Rollback consists of: delete the
  SharePoint shared file (or revoke the library permissions); fix
  the underlying issue; restart from step 1.
- **Failure during step 5** (commit fails or post-commit local-load
  fails) — revert via `git checkout HEAD~1 -- config/firm.toml` and
  push the revert (or amend the bad commit if it has not been pushed
  to a shared branch). Do NOT leave step 5's commit in main-branch
  history without step 6 passing; doing so creates the broken-pull
  window §8.4 covers.
- **Failure during step 6 or 7** — investigate as a real bug; the
  loader is misbehaving even though the data is valid. Do not
  rollback the local-file commit yet; instead, set
  `TGV3_FIRM_SHARED_CONFIG` to point at the shared file (bypassing
  the conventional path) and re-run to isolate where the failure
  is.

Cache files written by any partial migration attempt can be deleted
manually; the next successful load will recreate them.

No loader code change is part of the migration steps because Cycle 6's
implementation lands BEFORE migration runs. The migration is a data
reshape against an already-deployed loader.

### 8.4 Dev-environment fallback for non-OneDrive workstations

The conventional shared path (5.2.3) requires OneDrive to mount the
SharePoint library at `~/Crosby and Crosby LLP/...`. Several
environments cannot rely on that mount:

- **Maintainer's WSL development environment** (per 5.2.6) has no
  default OneDrive mount.
- **CI runners** have neither a OneDrive client nor any reason to
  authenticate with the firm's SharePoint.
- **Future automated agents or scheduled tasks** that run outside the
  paralegal user's interactive session.

For these environments, the migration plan provides a checked-in
template at `config/firm.shared.dev.toml`. The template content is
identical to the SharePoint-hosted shared file (it is the same
content that step 1 above authors), but it lives in the repo so it is
available without OneDrive sync. Workstations that need it set
`TGV3_FIRM_SHARED_CONFIG=$(realpath config/firm.shared.dev.toml)` (or
the platform equivalent) before invoking `load_firm_config()`.

The template is checked in as part of **step 0 of §8.2** — the
Cycle 6 PR itself. This is earlier than the surrounding migration
session and intentional: it eliminates the broken-pull window in
which a developer pulling main between Cycle-6 land and the
maintainer's migration session would otherwise hit `FirmConfigError`
with no mitigation.

Workstation-class behavior from the moment Cycle 6 lands:

- **Production paralegal workstation (OneDrive synced):** loads via
  the conventional shared path. The presence of the dev template in
  the repo is irrelevant; production deployments do not include
  `config/`.
- **Maintainer / developer with OneDrive (Windows-side):** same as
  production paralegal — the OneDrive-synced path resolves and the
  load succeeds.
- **Developer without OneDrive (WSL, CI, fresh checkout pre-sync):**
  must set `TGV3_FIRM_SHARED_CONFIG=$(realpath
  config/firm.shared.dev.toml)` before the first invocation. The
  `config/README.md` entry per §10 chore #6 documents this
  workflow. Once the load runs once, the cache is populated and
  subsequent invocations succeed without the env var until the
  cache file is deleted or expires — at which point the developer
  re-sets the env var.

The dev-template-and-env-var workflow is the prescribed handling
for any environment without OneDrive sync. It is not a fallback or
recovery mode; it is the deliberate developer-path discovery
contract.

The dev template is NOT used in production — production paralegal
workstations always go through the OneDrive-synced conventional
path. The template's presence in the repo is a convenience for
non-paralegal contexts; production deployments simply ignore it
because production deployments do not include `config/` in their
distribution.

##### 8.4.1 Keeping the dev template in sync

The dev template is a snapshot at migration time. Subsequent
maintainer edits to the SharePoint shared file are NOT automatically
reflected in `config/firm.shared.dev.toml`. Two options for keeping
them aligned (the choice is operational, not a spec contract):

- **Manual periodic refresh** — maintainer copy-pastes the SharePoint
  content into the repo file periodically (every threshold change,
  for example) and commits.
- **CI sync job** — out of scope for this spec, but a future CI job
  could re-author the dev template from SharePoint on a schedule.

Drift between the dev template and SharePoint is acceptable for
development and CI use cases (which exercise loader behavior, not
firm-policy correctness). Production cannot drift because production
reads SharePoint directly.

## 9. Amendment content for firm-config spec

This section provides the verbatim text to insert into
`docs/superpowers/specs/2026-04-21-firm-config-design.md` after
finalization. Following the established amendment pattern (A-1 through
A-6 already landed), this is amendment **A-7**.

---

### A-7. Two-source loader (added 2026-04-28)

The loader described in §3–§5 of this spec resolves a single TOML file
from the discovery chain and parses it. As of the
`2026-04-27-shared-firm-config-design` spec, the loader is restructured to
resolve and merge TWO TOML files: a shared firm-wide file (read-mostly,
hosted on SharePoint) and a local per-workstation file (writable, lives on
the user's machine). The merged dict feeds into the same Pydantic
validation pass; `FirmConfig`'s schema is unchanged.

Key contract changes:

- `load_firm_config()` signature changes from `load_firm_config(path=None)`
  to `load_firm_config(local_path=None, shared_path=None)`. The legacy
  `path=` keyword is no longer accepted.
- The shared file's discovery chain mirrors the local file's chain:
  explicit arg → `TGV3_FIRM_SHARED_CONFIG` env var →
  `CONVENTIONAL_SHARED_CONFIG_PATH` constant.
- A cache layer at `%LOCALAPPDATA%/trust-generator/firm.shared.cache.toml`
  (Windows) or `${XDG_CACHE_HOME:-~/.cache}/trust-generator/firm.shared.cache.toml`
  (POSIX) provides continuity when SharePoint sync is unavailable. Cache
  fallbacks emit a `SharedConfigStalenessWarning`.
- The merge contract specifies recursive deep-merge with EXTEND semantics
  for lists (shared-first, verbatim concatenation), empty-as-unset for
  empty TOML literals, and Pydantic-deferred type-mismatch handling.

For the full contract, see
`docs/superpowers/specs/2026-04-27-shared-firm-config-design.md`.

---

## 10. Pre-planning chores

Before the implementation plan composing this spec can be authored, the
following chores must complete in the listed order. None are part of the
plan itself; they are precondition work this spec creates.

1. **Apply amendment A-7 to the firm-config spec.** Insert §9's content
   verbatim into `docs/superpowers/specs/2026-04-21-firm-config-design.md`
   under a new "A-7" heading in the Post-finalization amendments section.
   This must land before plan composition references the firm-config spec
   as authoritative for the loader's pre-A-7 contract.
2. **Confirm SharePoint library exists.** The maintainer verifies the
   `internal-applications - trust-generator` library exists in the firm's
   SharePoint, with the `firm/config/` subdirectory accessible. If the
   subdirectory does not exist, the maintainer creates it as part of
   step 1 of the migration (§8.2), but plan composition need not wait
   on that creation — only on confirmation that the library itself
   exists with appropriate permissions.
3. **Apply approved graph edits.** Per the
   `graph_edit_methodology` of the spec-drafting protocol, this session
   produces a list of proposed graph edits that require user confirmation
   and application via the memory MCP. Plan composition should run
   AFTER graph edits have landed, so that plan-author claude-code
   sessions retrieve the new entities/observations during their own
   `memory:open_nodes` step.
4. **Diagnostics-engine warning subscriber.** The diagnostics engine
   (per `2026-04-23-diagnostics-engine-design.md`) is the consumer of
   record for the `SharedConfigStalenessWarning` and
   `SharedConfigIntegrityWarning` categories per §5.5.5.4. The
   diagnostics engine's plan must add a subscriber that captures both
   categories and writes audit-log entries containing the timestamp,
   resolved shared path, cache path, cache age, warning category, and
   (for integrity events) truncated parse-error reason. The subscriber
   is the operational surface for post-hoc detection of prolonged
   sync outages and configuration tampering. This spec does not
   implement the subscriber; it exits emitting the two warning
   categories and assumes the diagnostics engine routes them. If the
   diagnostics engine has not added the subscriber before this spec's
   implementation lands, the warnings are still emitted (they reach
   the default `warnings` handler) and module-level
   `logging.captureWarnings(True)` per §5.5.5.4 routes them to
   Python's logging machinery, but no audit-log entries are written
   for them.

   The chore must additionally name a target latency for "maintainer
   learns of an integrity-fallback event" (e.g., one business day,
   end-of-week digest, etc.). This spec deliberately does not pin the
   number — it is an operational choice for the diagnostics-engine
   plan. The latency target is what makes §5.4.4.2's disclaimer
   actionable: it converts "unbounded notification latency" into
   "bounded notification latency under SLA X."
5. **Audit-log effective-configuration capture amendment.** The
   `2026-04-23-diagnostics-engine-design.md` spec's §5.5 audit
   record captures `restriction_level` per decision but not the full
   effective configuration. This spec's §1 motivation and §5.5.3
   integrity argument depend on per-decision capture of the policy
   in effect at decision time, which today requires cross-referencing
   the SharePoint version history with the audit-record timestamp.
   The audit-log spec must be amended to add at minimum the effective
   threshold values (`single_soft`, `joint_soft`, `single_hard`,
   `joint_hard`, `approaching_cliff_ratio`) and the substituted
   `audit_log_dir` path to the audit record, so each entry is
   self-contained for forensic reconstruction. Until chore #5
   completes, integrity-fallback events (case 4 of §5.4.3) recorded
   by chore #4's subscriber are the only on-record signal that
   firm-policy edits failed to propagate; this is acceptable as a
   transitional posture but should not be the long-term position.
6. **Onboarding documentation for non-OneDrive contributors.** Add
   a `config/README.md` entry as part of the Cycle 6 PR (alongside
   the dev-template commit per §8.2 step 0) that documents:
   - The two-source loader's discovery chains (a brief pointer to
     §5.2 of this spec).
   - The dev-environment workflow: `export
     TGV3_FIRM_SHARED_CONFIG=$(realpath
     config/firm.shared.dev.toml)` for any environment without
     OneDrive sync (WSL, CI, future automation).
   - The expectation that paralegal production deployments do NOT
     include the `config/` directory and rely on the OneDrive-
     synced shared file.

   Additionally, the §5.4.5 onboarding-pointer error message should
   include a hint at the dev template path, conditional on its
   presence in the working directory:

   ```
   FirmConfigError:
     Shared firm.toml is unreachable and no cached copy exists.
     Resolved shared path: <path>
     Expected cache path:  <path>

     This typically indicates either (1) initial setup of this
     workstation has not yet completed, or (2) the SharePoint sync
     has never succeeded on this machine.

     [If <repo>/config/firm.shared.dev.toml exists:]
     If you are a developer (not a paralegal), set
     TGV3_FIRM_SHARED_CONFIG to point at config/firm.shared.dev.toml
     in this repository to use the developer template.

     See the paralegal-onboarding workflow for first-time setup, or
     contact the maintainer for sync troubleshooting.
   ```

   The conditional clause is checked at error-construction time by
   testing `(Path.cwd() / "config" / "firm.shared.dev.toml").exists()`;
   the hint appears only when the template is in scope (i.e., the
   process is running from a repo checkout, not from an installed
   paralegal build).

## Design decisions and scope additions

This appendix records design decisions made during this session that are
not already captured in the section bodies above. Following the convention
of prior specs, decisions are listed in order made, with rationale.

### D-1. List-merge semantics (§5.3.2)

The initial framing considered three list-merge policies: REPLACE,
EXTEND, element-wise. EXTEND with shared-first verbatim concatenation
won. REPLACE was rejected because it would force per-workstation files
to restate the firm's full list to add a single entry. Element-wise was
rejected because it requires identity semantics that lists don't carry
at the merge layer.

The sub-decisions within EXTEND (shared-first ordering, verbatim with no
dedup) followed the principle that the merge function should be schema-
agnostic. Where dedup or other set-like semantics are needed, the
responsibility belongs to a Pydantic field validator on `FirmConfig`,
not to the merge function. This is documented as a future-extension
pattern in 5.3.2.

### D-2. Empty-as-unset semantics (§5.3.3)

Decided that empty TOML literals on the local side (`""`, `[]`, empty
table) are treated as if the key were absent. Numeric `0` and boolean
`false` remain values.

The assumption (no current schema field treats empty as a meaningful
value) was audited against the current `FirmConfig` and confirmed. The
future-proofing posture is `Field(min_length=1)` on new string fields,
following the constraint already applied to `User.upn`.

### D-3. Discovery chain symmetry (§5.2)

Local and shared files use parallel three-step discovery chains (explicit
arg → env var → convention). The two chains are independent: failure on
one does not affect the other.

Missing local file is a hard error; missing shared file falls back to
cache. This asymmetry reflects that the local file's existence is a
workstation invariant (every workstation has one or the workstation is
not configured), while the shared file's reachability is contingent on
SharePoint sync state.

### D-4. Hardcoded firm name in `CONVENTIONAL_SHARED_CONFIG_PATH` (§5.2.3)

The firm name ("Crosby and Crosby LLP") and library segment are
hardcoded in the loader module rather than parameterized. The codebase is
a single-firm internal tool; multi-tenancy is not a current or planned
requirement. Hardcoding centralizes the would-be-change site if
multi-tenancy ever becomes relevant.

### D-5. Cache location at platform-conventional state directory (§5.4.1)

The cache lives at platform-conventional paths (`%LOCALAPPDATA%` on
Windows, `${XDG_CACHE_HOME:-~/.cache}` on POSIX) rather than alongside the
local config file. Rationale: separates "config that humans edit" from
"state that the loader manages." Paralegals will not accidentally
hand-edit the cache file because they will not encounter it in the same
directory as their config.

The v2 codebase's prior precedent for AppData usage (`_appdata_config_path`)
informed this decision but was not the source of authority. v3 is a
rewrite, not a v2 derivative; the choice was re-made on its own merits.

### D-6. Single exception class for all loader error paths (§5.6.3)

All error paths raise `FirmConfigError` with descriptive message
templates rather than using a hierarchy of specialized subclasses.
Matches the existing single-exception posture from the firm-config spec.
Rationale: every caller of `load_firm_config` has the same recovery
posture ("surface to user, fail-fast"); branching on exception type
would tempt callers to make distinctions the application doesn't need.

### D-7. Two distinct warning classes for fallback events (§5.6.2)

Unlike errors (collapsed to one class per D-6), fallback events use
two separate `UserWarning` subclasses: `SharedConfigStalenessWarning`
for availability-fallback (case 2 or case 3 of 5.4.3) and
`SharedConfigIntegrityWarning` for integrity-fallback (case 4).
Rationale: warnings are non-failing signals that consuming code may
want to filter or elevate independently of other application
warnings; isolating each category lets consumers route them to
different surfaces. The two categories carry operationally different
signals — staleness is "shared was unavailable, the cache is being
used as a known-good fallback (routine)"; integrity is "shared was
corrupt, the maintainer must repair it (non-routine, requires human
action)" — so flattening them into a single class would erase the
distinction that motivates per-category routing in the first place.

The justification rests on filterability and operational-signal
fidelity alone; no specific consumer surface is presumed to exist as
a precondition for shipping the classes. The diagnostics-engine
subscriber referenced in §5.5.5.4 and §10 chore #4 is the first
consumer of record, but the spec does not depend on its existence —
the classes are emitted into Python's `warnings` machinery with
sensible defaults regardless of whether any subscriber is registered.

### D-8. No backward-compatibility shim for `load_firm_config` signature (§5.6.4)

The new two-arg signature replaces the old single-arg signature with no
deprecation period. v3 is pre-stable; no external consumers exist;
internal call sites migrate as part of Cycle 6. The cost of maintaining
a transition shim outweighs the benefit for non-existent external
consumers.

### D-9. Inside-out TDD with explicit refactor pruning (§6)

The implementation cycles use Detroit-school inside-out TDD per the
spec-drafting protocol. Refactor stages are prescribed only when the
cycle's `refactor_threshold` is met (structural duplication or nested
conditionals that flatten); cycles that don't meet the threshold
explicitly note the absence with reasoning. Three of six cycles get a
prescribed refactor; three don't.

This discipline addresses the prior-session observation that TDD's
refactor stage can become ceremonial when applied uniformly. Per-cycle
threshold evaluation keeps refactor work meaningful.

### D-10. Shared-file integrity failures fall back to cache with distinct warning (§5.4.3)

A malformed shared file falls back to the cached copy with a
`SharedConfigIntegrityWarning` (distinct from the
availability-fallback `SharedConfigStalenessWarning`) rather than
hard-stopping the workstation.

This decision reverses the predecessor draft's posture, which treated
malformed shared as a fail-fast condition. Plan-review surfaced that
fail-fast inverts the audit-trail-integrity argument: the workstation
running on its last-known-good cache continues writing audit-log
entries with last-known-good thresholds (which is exactly "what was
in effect at decision time" per §5.5.3), while a workstation that
hard-stops produces no audit-log entries at all for the affected
window. Falling back preserves the audit trail's forensic
completeness; failing closed sacrifices it.

The distinct warning class preserves the operational signal the
predecessor sought: integrity failures are categorically different
from availability failures and warrant a different operational
response (notify the maintainer to repair the shared file, vs. wait
for sync to recover). Routing the two warning categories to different
surfaces (per §5.5.5.4 and §10 chore #4) gives operators the
notification asymmetry the predecessor draft was reaching for,
without sacrificing work continuity.

Recovery-latency consideration: in the small-firm context (single
maintainer, non-technical paralegals, OneDrive sync), fail-fast on
every workstation produces hours of lost productivity per maintainer
edit error, with no compensating integrity gain. Fall-back-with-
distinct-warning preserves work continuity; the maintainer's
notification surface flags the broken shared file for repair on the
next maintainer-available window.

### D-11. Cache write happens after full validation success (§5.4.2)

The cache file is updated only after `FirmConfig(**merged)` succeeds.
Rationale: the cache should always reflect a *known-good* shared file.
Writing it after parse but before validation would risk caching a
shared file that produces invalid configurations when merged with the
workstation's local file.

This trades off cache freshness when local-side bugs prevent validation
(the cache won't update during such windows) against the integrity
property that any cached file is one the loader has previously
successfully consumed end-to-end. The tradeoff favors integrity.

### D-12. Empty-as-unset override gap accepted as-is (§5.3.3)

The §5.3.3 audit identified a gap: for fields with non-empty Pydantic
defaults, a workstation cannot use `key = ""` to mean "fall back to
the Pydantic default rather than inherit shared's value." The empty
literal is treated as absence (rule definition), which falls through
to shared, not to the Pydantic default.

Concrete affected fields per the audit table: `country` (default
"US"), `default_state` (default "Illinois"), `default_county`
(default "Winnebago"), `trust_code_citation` (default Illinois Trust
Code citation), and the path-typed fields `db_path`, `audit_log_dir`,
`rules_dir` with their non-empty defaults.

Closing the gap would require an escape-hatch syntax such as
`key = "__default__"` or `key = "__inherit_pydantic_default__"`. This
introduces a parallel value-language readers must learn (in addition
to the empty-as-unset rule itself), and the gap surfaces only in the
narrow scenario where (i) shared sets a non-default value AND (ii) a
specific workstation wants the Pydantic default rather than shared's
value AND (iii) the desired Pydantic-default value differs from
shared's value in a way that operationally matters. None of those
conditions are live in today's deployment (the firm operates only in
Illinois; the Illinois-default values match shared).

Decision: accept the gap. If a future operational scenario surfaces
the need (e.g., a Wisconsin-jurisdiction workstation), the response
is a follow-up spec introducing the escape-hatch syntax, not a
preemptive design change here. The audit's `min_length=1` posture
for new string fields (§5.3.3 "Posture for new string fields")
prevents the gap from arising for newly-added fields without
explicit consideration.

### D-13. Cycle 5 return-shape revert (§6.6)

The 2026-04-27 draft refactored Cycle 5's `_read_shared_with_fallback`
helper to return bare `bytes` (down from `tuple[bytes, bool]`),
offloading the cache-fallback signal to a re-`exists()` check in
Cycle 6. Plan-review surfaced that this introduces a TOCTOU window:
between the helper's internal `exists()` check and Cycle 6's
re-`exists()` call, OneDrive can change the file's existence state.
The two failure modes:

- **Mid-load file appears** (helper fell back to cache; sync then
  delivers the file before Cycle 6's re-check): Cycle 6's
  `exists()` returns True, `used_cache` evaluates False, Cycle 6
  calls `_write_cache(shared_bytes)` where `shared_bytes` are
  actually the cache bytes — overwriting the cache with itself and
  resetting mtime to now. Breaks §5.4.2's stated contract that mtime
  tracks "timestamp of last fully successful load"; the staleness
  warning (5.4.4) reports a stale cache as fresh.
- **Mid-load file disappears** (helper read shared successfully;
  file then disappears before Cycle 6's re-check): Cycle 6's
  `exists()` returns False, `used_cache` evaluates True, the cache
  write is skipped despite having known-good shared bytes that
  could have refreshed the cache.

The revert in this revision is to keep the boolean (and adds the
parsed dict for I3's single-parse contract): the helper now returns
`tuple[bytes, dict[str, Any], bool]`. Cycle 6 unpacks the tuple and
consumes the `used_cache` boolean directly, never re-querying
`resolved_shared.exists()`. The dispatch-flattening that the original
refactor pursued (`_parse_or_raise` extraction) is preserved in the
current Cycle 5 green output through the parameter-driven
`_read_cache_or_raise` helper, so the revert recovers correctness
without sacrificing the refactor's clarity goal.

The lesson recorded for future TDD discipline: a refactor that
simplifies a return type by offloading the discarded signal to a
re-derivation in the caller is correctness-equivalent only if the
re-derivation is free of TOCTOU concerns. For helpers that read
filesystem state, that condition is rarely satisfied; the boolean's
"redundancy" was actually load-bearing.
