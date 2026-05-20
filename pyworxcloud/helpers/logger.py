"""Handling logger setup."""

from __future__ import annotations

import logging

PACKAGE_LOGGER_NAME = "pyworxcloud"


def redact_email_address(value: str) -> str:
    """Return a log-safe representation of an email address."""
    if "@" not in value:
        return "[REDACTED]"

    local_part, domain = value.split("@", 1)
    domain_labels = domain.split(".")
    redacted_domain = ".".join(
        _redact_email_part(label) if index == 0 else label
        for index, label in enumerate(domain_labels)
    )

    return f"{_redact_email_part(local_part)}@{redacted_domain}"


def _redact_email_part(value: str) -> str:
    """Redact the middle of one email address part."""
    if not value:
        return "[REDACTED]"
    if len(value) == 1:
        return f"{value}[REDACTED]"
    return f"{value[0]}[REDACTED]{value[-1]}"


def get_logger(name: str) -> logging.Logger:
    """Return a standard library logger for this package."""

    package_logger = logging.getLogger(PACKAGE_LOGGER_NAME)
    if not any(
        isinstance(handler, logging.NullHandler) for handler in package_logger.handlers
    ):
        package_logger.addHandler(logging.NullHandler())

    return logging.getLogger(name)
