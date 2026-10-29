"""Loudmouth package interface — re-exports server entrypoints and metadata."""

from server import (
    DEFAULT_ALLOWED_ORIGINS,
    DEFAULT_PORTS,
    PROTOCOL,
    TRUSTED_APPLICATIONS,
    __version__,
    app,
    main,
)

__all__ = [
    "DEFAULT_ALLOWED_ORIGINS",
    "DEFAULT_PORTS",
    "PROTOCOL",
    "TRUSTED_APPLICATIONS",
    "__version__",
    "app",
    "main",
]
