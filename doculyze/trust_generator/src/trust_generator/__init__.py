"""Namespace package for the trust-generator application."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("trust-generator")
except PackageNotFoundError:
    __version__ = "2.2.0-dev"

__all__ = [
    "TrustData",
    "TrustType",
    "AppConfig",
    "load_config",
    "parse_file",
    "validate",
    "generate_trust_document",
    "generate_printable_questionnaire",
]

from .config import AppConfig, load_config
from .generators import generate_printable_questionnaire, generate_trust_document
from .parsers import parse_file
from .schema import TrustData, TrustType
from .validators import validate
