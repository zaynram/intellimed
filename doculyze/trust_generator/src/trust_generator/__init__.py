"""Namespace package for the trust-generator application."""

__all__ = [
    "AppConfig",
    "TrustData",
    "TrustType",
    "app",
    "generate_printable_questionnaire",
    "generate_trust_document",
    "load_config",
    "parse_file",
    "validate",
]

from importlib import metadata

try:
    __version__ = metadata.version("trust-generator")
except metadata.PackageNotFoundError:
    __version__ = "2.2.0-dev"

from .v2 import *
