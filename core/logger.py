"""
core/logger.py
Centralized logger with console and rotating file support.
"""
import logging
from logging.handlers import RotatingFileHandler
import sys
from core import config

_logger = None

def get_logger(name: str = "surf") -> logging.Logger:
    global _logger
    if _logger is not None:
        return _logger.getChild(name) if name != "surf" else _logger

    logger = logging.getLogger("surf")
    level = getattr(logging, config.LOG_LEVEL.upper(), logging.INFO)
    logger.setLevel(level)
    logger.propagate = False

    # Clear existing handlers to prevent duplicates
    if logger.hasHandlers():
        logger.handlers.clear()

    # Console Handler (clean format)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_format = logging.Formatter(
        "[%(levelname)s] %(message)s"
    )
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)

    # File Handler (detailed rotating file)
    try:
        file_handler = RotatingFileHandler(
            config.LOG_FILE,
            maxBytes=2 * 1024 * 1024, # 2 MB
            backupCount=3,
            encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_format = logging.Formatter(
            "%(asctime)s [%(levelname)s] [%(name)s:%(lineno)d]: %(message)s"
        )
        file_handler.setFormatter(file_format)
        logger.addHandler(file_handler)
    except Exception as e:
        logger.warning(f"Could not initialize file logger: {e}")

    _logger = logger
    return logger.getChild(name) if name != "surf" else logger
