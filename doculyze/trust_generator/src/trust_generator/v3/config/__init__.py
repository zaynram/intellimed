"""TGv3 firm configuration package.

Exposes the canonical ``FirmConfig`` settings object, the ``load_firm_config``
loader, and the two warning classes the loader emits on cache fallback.
The loader is the only public entry point; construct ``FirmConfig`` directly
only in tests.
"""

from trust_generator.v3.config.firm import (
    DEFAULT_LOCAL_CONFIG_PATH,
    ENV_PREFIX,
    ENV_VAR_LOCAL_CONFIG_PATH,
    ENV_VAR_SHARED_CONFIG_PATH,
    Diagnostics,
    Drafts,
    EstateThresholds,
    FirmConfig,
    FirmConfigError,
    FirmIdentity,
    Guardianship,
    Jurisdiction,
    Meta,
    SharedConfigIntegrityWarning,
    SharedConfigStalenessWarning,
    TrusteeCatalog,
    User,
    load_firm_config,
)

__all__ = [
    "DEFAULT_LOCAL_CONFIG_PATH",
    "ENV_PREFIX",
    "ENV_VAR_LOCAL_CONFIG_PATH",
    "ENV_VAR_SHARED_CONFIG_PATH",
    "Diagnostics",
    "Drafts",
    "EstateThresholds",
    "FirmConfig",
    "FirmConfigError",
    "FirmIdentity",
    "Guardianship",
    "Jurisdiction",
    "Meta",
    "SharedConfigIntegrityWarning",
    "SharedConfigStalenessWarning",
    "TrusteeCatalog",
    "User",
    "load_firm_config",
]
