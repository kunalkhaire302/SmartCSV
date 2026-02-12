"""
Structured logging with rotating file handler and console output.

Usage:
    from utils.logger import get_logger
    logger = get_logger(__name__)
    logger.info("Processing file %s", filename)
"""

import logging
import sys
from logging.handlers import RotatingFileHandler

import config


def get_logger(name: str) -> logging.Logger:
    """Create or retrieve a logger with console + rotating-file handlers.

    Args:
        name: Logger name, typically ``__name__``.

    Returns:
        Configured ``logging.Logger`` instance.
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, config.LOG_LEVEL.upper(), logging.INFO))

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    logger.addHandler(console)

    # Rotating file handler
    log_file = config.LOG_FOLDER / "app.log"
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=config.LOG_MAX_BYTES,
        backupCount=config.LOG_BACKUP_COUNT,
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger
