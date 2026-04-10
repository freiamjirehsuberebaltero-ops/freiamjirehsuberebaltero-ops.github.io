"""Logging utilities for the Minecraft Mod Manager."""

import logging
import os
from pathlib import Path


_loggers: dict = {}


def setup_logger(log_dir: Path, level: int = logging.INFO) -> logging.Logger:
    """Configure the root application logger with file and console handlers."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "mod_manager.log"

    logger = logging.getLogger("mod_manager")
    logger.setLevel(level)

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.WARNING)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the 'mod_manager' namespace."""
    return logging.getLogger(f"mod_manager.{name}")
