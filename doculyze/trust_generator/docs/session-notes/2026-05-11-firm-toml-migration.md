# 2026-05-11 — `firm.toml` SharePoint migration session (chore #28)

Executed spec `2026-04-28-shared-firm-config-design.md` §8.2 steps 1, 3-7. Step 2 (SharePoint sync round-trip verification) and the conventional-discovery half of step 4 require Windows-native action and are flagged at the bottom of this note.

## Steps executed

**Step 1 — Author shared file at SharePoint mount.**
Wrote `~/desktop/sharepoint/crosbycrosbyllp/internal-applications - trust-generator/firm/config/firm.toml` (Windows path: `C:\Users\ramda\Crosby and Crosby LLP\internal-applications - trust-generator\firm\config\firm.toml`). Source: the pre-migration `config/firm.toml` with `[user]` removed and the §5.3.7.3 path-absoluteness fixes (see step 4 below).

**Step 3 — Test suite.** `pixi run check` green after the post-#27 schema regen amendment (commit `e8fb144`); no migration-introduced failures.

**Step 4 — Production-path verification (explicit-path variant, WSL).**
Loaded via `load_firm_config(local_path=..., shared_path=...)` against pre-strip local + new shared. First attempt rejected the shared file: `_validate_shared_paths_absolute` raised `FirmConfigError` on `trustee_catalog.db_path = "./data/trustee_catalog.sqlite"` because spec §5.3.7.3 prohibits relative paths on the shared side. Fix: changed `db_path` and `diagnostics.rules_dir` to tilde-prefixed absolute paths under the SharePoint library (`~/Crosby and Crosby LLP/internal-applications - trust-generator/firm/{data,config/rules}`). Same fix applied to the checked-in dev template `config/firm.shared.dev.toml` (the original dev-template authoring missed the validator). Re-verification: all values match pre-migration single-file load, zero warnings.

**Step 5 — Strip local.** `config/firm.toml` reduced to header comments + `[meta]` + `[user]` (one field: `upn = "zramdass"`). 65 lines → 23 lines.

**Step 6 — Re-verification after strip.** Identical merged `FirmConfig` to step 4, zero warnings. Confirms the merge correctly takes `user.upn` from LOCAL and everything else from SHARED.

**Step 7 — Cache file.** `~/.cache/trust-generator/firm.shared.cache.toml` written (2750 bytes, byte-exact match with shared file). Atomic-write path verified end-to-end.

## Defect surfaced + fixed mid-session

The dev template at `config/firm.shared.dev.toml` shipped (from integration plan task 13-5) with relative paths for `trustee_catalog.db_path` and `diagnostics.rules_dir`. These violate spec §5.3.7.3's shared-side path-absoluteness invariant and would have prevented any dev environment from using the template via `TGV3_FIRM_SHARED_CONFIG`. The defect escaped review because no test loads the dev template directly — `test_config_integration.py` uses `tmp_path` fixtures. The fix lands as part of the chore #28 commit alongside the local-strip.

## Outstanding user-side actions (post-PR)

1. **Step 2 — Verify OneDrive sync round-trip.** Confirm the new `firm/config/firm.toml` appears in the SharePoint web UI at the corresponding library path. Confirm permission groups: Members = maintainer, Visitors = paralegal group. Wait for OneDrive "fully synced" state.
2. **Step 4 — Conventional-discovery half (Windows-native).** From the maintainer's Windows workstation, with no `TGV3_FIRM_CONFIG` / `TGV3_FIRM_SHARED_CONFIG` env vars set, run a `load_firm_config()` (no arguments) invocation. Expected: both files discovered via conventional paths, no warnings. (From WSL the conventional shared path `~/Crosby and Crosby LLP/...` doesn't resolve to the SharePoint mount; the explicit-path variant above is the WSL-side equivalent.)
3. **Trustee DB + rules dir.** The shared file's paths now point to `~/Crosby and Crosby LLP/internal-applications - trust-generator/firm/{data,config/rules}` — those directories do NOT yet contain the trustee_catalog.sqlite or rules content. Migrating those data files is a separate concern (likely a follow-up chore once those features land their consumer code). The `firm/config/rules/` scaffolding half landed as chore #31 (see addendum below); `firm/data/` is deferred until the trustee_catalog feature has consumers.

## Addendum — chore #31 scaffolding (`firm/config/rules/`)

Created an empty `firm/config/rules/` directory on the SharePoint mount at `~/desktop/sharepoint/crosbycrosbyllp/internal-applications - trust-generator/firm/config/rules` (Windows: `C:\Users\ramda\Crosby and Crosby LLP\internal-applications - trust-generator\firm\config\rules`). The shared `firm.toml` resolves `diagnostics.rules_dir` to this path; `_load_custom_rules` (`v3/diagnostics/rules/registry.py`) tolerates a missing or empty directory, so paralegal workstations don't actually require content here yet — but scaffolding the directory means the path lands on a real (empty) destination rather than a non-existent one, which keeps any future "is this expected?" diagnostic plumbing honest.

`firm/data/` (target for `trustee_catalog.db_path`) is **deliberately not scaffolded** in this chore. Hosting a SQLite database on a OneDrive-synced library introduces non-trivial design questions (WAL-file sync conflicts, partial-write visibility during sync, multi-writer coordination across paralegal workstations) that should be resolved at the trustee_catalog feature's design session, not pre-emptively here. The current absence of a `trustee_catalog` consumer in `src/` makes this deferral safe — nothing references `db_path` yet, so the path's non-existence has no runtime effect.

## Commits

- `e8fb144` — post-#27 schema regen amendment (one-line schema description sync)
- `876accc` — close chore #28: strip local `firm.toml` + dev template tilde-prefix alignment
- `9db4b00` — open chore #31 (`firm/config/rules/` scaffolding)
- (current commit) — close chore #31: scaffold `firm/config/rules/` on SharePoint mount + this addendum
