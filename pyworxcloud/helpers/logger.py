"""Handling logger setup."""

from __future__ import annotations

import logging

PACKAGE_LOGGER_NAME = "pyworxcloud"


def get_logger(name: str) -> logging.Logger:
    """Return a standard library logger for this package."""

    package_logger = logging.getLogger(PACKAGE_LOGGER_NAME)
    if not any(
        isinstance(handler, logging.NullHandler) for handler in package_logger.handlers
    ):
        package_logger.addHandler(logging.NullHandler())

    return logging.getLogger(name)
