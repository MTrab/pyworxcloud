"""Handling logger setup."""

from __future__ import annotations

import logging


def get_logger(name: str) -> logging.Logger:
    """Configure the logger component."""

    logger = logging.getLogger(name)

    # configure log formatter
    logFormatter = logging.Formatter(
        "%(asctime)s [%(filename)s] [%(funcName)s] [%(levelname)s] [%(lineno)d] %(message)s"
    )

    # configure stream handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logFormatter)

    if not logger.handlers:
        logger.setLevel(logging.DEBUG)
        logger.addHandler(console_handler)

    return logger
