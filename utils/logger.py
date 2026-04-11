"""Logging utilities for the Minecraft Mod Manager."""

import logging
import os
import sys
from pathlib import Path


def setup_logger(log_dir: Path, level: int = logging.INFO) -> logging.Logger:
    """Configure the root application logger with file and console handlers."""
    print(f"[DIAGNOSTIC] setup_logger() called with log_dir={log_dir}, level={level}")
    sys.stdout.flush()
    
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "mod_manager.log"
    print(f"[DIAGNOSTIC] Log file path: {log_file}")
    sys.stdout.flush()

    logger = logging.getLogger("mod_manager")
    logger.setLevel(level)
    print(f"[DIAGNOSTIC] Root logger created: {logger}, level={level}")
    sys.stdout.flush()

    if logger.handlers:
        print(f"[DIAGNOSTIC] Logger already has {len(logger.handlers)} handler(s), returning existing logger")
        sys.stdout.flush()
        return logger

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    try:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        logger.addHandler(file_handler)
        print(f"[DIAGNOSTIC] File handler added successfully: {log_file}")
        sys.stdout.flush()
    except Exception as e:
        print(f"[DIAGNOSTIC] ERROR adding file handler: {e}")
        sys.stdout.flush()

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.DEBUG)  # Changed to DEBUG to see all output
    logger.addHandler(console_handler)
    print(f"[DIAGNOSTIC] Console handler added successfully")
    sys.stdout.flush()

    logger.info("Logger initialized successfully")
    print(f"[DIAGNOSTIC] Logger has {len(logger.handlers)} handler(s)")
    sys.stdout.flush()

    return logger


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the 'mod_manager' namespace."""
    child_logger = logging.getLogger(f"mod_manager.{name}")
    print(f"[DIAGNOSTIC] get_logger('{name}') called, returning: {child_logger}")
    sys.stdout.flush()
    return child_logger