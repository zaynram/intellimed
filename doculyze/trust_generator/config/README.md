# Trust Generator — `config/` directory

This directory holds firm-configuration files for development environments.
Production paralegal workstations resolve their shared configuration from
SharePoint via OneDrive; the files in this directory are convenience
templates and per-workstation defaults for non-OneDrive environments.

## Two-source loader

`load_firm_config()` reads two TOML files and merges them:

- **Local file** (`config/firm.toml`): per-workstation, version-controlled.
  Currently contains only `[user]` post-migration.
- **Shared file**: firm-wide policy. Production loads from the OneDrive-synced
  SharePoint library; development environments load from
  `config/firm.shared.dev.toml` via env-var override.

Discovery for each file is:

1. Explicit `local_path=` / `shared_path=` argument to `load_firm_config()`.
2. Environment variable: `TGV3_FIRM_CONFIG` (local) or `TGV3_FIRM_SHARED_CONFIG` (shared).
3. Conventional default: `config/firm.toml` (local), or the OneDrive-synced library path (shared).

See `docs/superpowers/specs/2026-04-28-shared-firm-config-design.md` §5.2 for
the discovery contract.

## Dev-environment workflow

If you are developing locally without OneDrive (e.g., WSL, CI, fresh checkout
pre-sync), the conventional shared path will not resolve. Use the dev template:

```bash
export TGV3_FIRM_SHARED_CONFIG=$(realpath config/firm.shared.dev.toml)
```

Then run the application normally. The first successful load also populates
the local cache at `${XDG_CACHE_HOME:-~/.cache}/trust-generator/firm.shared.cache.toml`
(POSIX) or `%LOCALAPPDATA%/trust-generator/firm.shared.cache.toml` (Windows);
subsequent invocations succeed without the env var until the cache file
is removed or expires.

## Production deployment posture

Paralegal production deployments do **NOT** include the `config/` directory.
The deployed application reads the local file from the workstation's user
profile and the shared file from OneDrive. The dev template is never used
in production.

## Files

- `config/firm.toml` — local per-workstation firm config (currently `[user]` only post-migration).
- `config/firm.shared.dev.toml` — dev-environment shared template; copy of
  the SharePoint-hosted shared file at migration time. May drift from
  SharePoint over time; see spec §8.4.1.
- `config/firm.v2.toml` — legacy v2 single-source config (preserved for
  reference/migration).
- `config/firm-config.schema.json` — JSON Schema for editor integrations.

## Migration provenance

The split into `config/firm.toml` (local-only post-migration) and
`config/firm.shared.dev.toml` (dev-environment shared) lands as part of plan
#13 (`docs/superpowers/plans/2026-04-29-shared-firm-config-integration.md`).
The maintainer's migration session that uploads the shared content to
SharePoint and strips the duplicate sections from `config/firm.toml`
is described in spec §8.2 migration steps 1-8.
