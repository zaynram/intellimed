"""Generate config/firm-config.schema.json from FirmConfig.

Usage:

    pixi run python scripts/generate_firm_config_schema.py

Writes to ``<repo_root>/config/firm-config.schema.json``. The output path is
anchored to the script file's location (not the current working directory),
so the artifact always lands in the checked-in repo location regardless of
where the script is invoked from. Output is pretty-printed with deterministic
key sort and a trailing newline. Re-run after any change to FirmConfig or its
nested models.

An optional ``output_path`` kwarg on ``main()`` lets tests target a tmp
directory without chdir-ing the process.
"""

from __future__ import annotations

import json
from pathlib import Path

from trust_generator.v3.config import FirmConfig
from trust_generator.v3.config.schema_gen import TombiAwareGenerator

# Anchor the output path to the repo via the script file's location rather than
# the process CWD. The script lives at <repo>/scripts/..., so walking up one
# level lands at the repo root.
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_PATH = REPO_ROOT / "config" / "firm-config.schema.json"


def main(output_path: Path | None = None) -> int:
    target = output_path if output_path is not None else DEFAULT_OUTPUT_PATH
    schema = FirmConfig.model_json_schema(schema_generator=TombiAwareGenerator)
    rendered = json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
