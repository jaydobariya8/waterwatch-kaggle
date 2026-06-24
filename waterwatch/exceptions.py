"""WaterWatch exception hierarchy — catch specific errors, never bare ``except``."""

from __future__ import annotations


class WaterWatchError(Exception):
    """Base class for all WaterWatch errors."""

    code: str = "waterwatch_error"


class DataLayerError(WaterWatchError):
    """Raised when bundled ground-truth data is missing or malformed."""

    code = "data_layer_error"


class ToolNotFoundError(WaterWatchError):
    """Raised when an MCP tool / data-layer function is requested but unknown."""

    code = "tool_not_found"


class ParseError(WaterWatchError):
    """Raised when an uploaded report cannot be parsed into structured parameters."""

    code = "parse_error"


class VerificationError(WaterWatchError):
    """Raised when the Verifier cannot reach a fully-cited report within its loop budget."""

    code = "verification_error"


class StoreError(WaterWatchError):
    """Raised on persistence-layer failures (complaints / sessions)."""

    code = "store_error"
