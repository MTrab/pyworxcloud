"""Handling logger setup."""
import logging


def get_logger(name: str) -> logging.Logger:
    """Configure the logger component."""

    logger = logging.getLogger(name)

    # configure log formatter
    logFormatter = logging.Formatter(
        "%(asctime)s [%(filename)s] [%(funcName)s] [%(levelname)s] [%(lineno)d] %(message)s"
    )

    # configure stream handler
    consoleHandler = logging.StreamHandler()
    consoleHandler.setFormatter(logFormatter)

    if not len(logger.handlers):
        logger.setLevel(logging.DEBUG)
        logger.addHandler(consoleHandler)

    print(logger.handlers)

    return logger
