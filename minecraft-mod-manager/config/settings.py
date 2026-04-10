"""Configuration management for the Minecraft Mod Manager."""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from utils.constants import (
    CONFIG_DIR,
    PROFILES_DIR,
    BACKUP_DIR,
    LOGS_DIR,
)
from utils.logger import get_logger

logger = get_logger("settings")

DEFAULT_SETTINGS: Dict[str, Any] = {
    "curseforge_api_key": "",
    "default_mc_version": "1.20.1",
    "default_mod_loader": "Fabric",
    "auto_update_check": True,
    "backup_before_update": True,
    "max_backups": 5,
    "download_threads": 4,
    "preferred_api": "modrinth",  # "modrinth" | "curseforge" | "both"
    "minecraft_dirs": [],  # manually added Minecraft directories
    "theme": "dark",
}


class Settings:
    """Persistent JSON-backed settings store."""

    def __init__(self, config_dir: Optional[Path] = None) -> None:
        self._config_dir = config_dir or CONFIG_DIR
        self._config_file = self._config_dir / "settings.json"
        self._data: Dict[str, Any] = dict(DEFAULT_SETTINGS)
        self._ensure_dirs()
        self._load()

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        """Return setting value, falling back to *default*."""
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Update a setting value and persist to disk."""
        self._data[key] = value
        self._save()

    def update(self, mapping: Dict[str, Any]) -> None:
        """Bulk-update settings from a dictionary."""
        self._data.update(mapping)
        self._save()

    def all(self) -> Dict[str, Any]:
        """Return a copy of all settings."""
        return dict(self._data)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_dirs(self) -> None:
        for d in (self._config_dir, PROFILES_DIR, BACKUP_DIR, LOGS_DIR):
            d.mkdir(parents=True, exist_ok=True)

    def _load(self) -> None:
        if self._config_file.exists():
            try:
                with open(self._config_file, "r", encoding="utf-8") as fh:
                    stored = json.load(fh)
                self._data.update(stored)
                logger.debug("Settings loaded from %s", self._config_file)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Could not load settings: %s", exc)

    def _save(self) -> None:
        try:
            with open(self._config_file, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, indent=2)
        except OSError as exc:
            logger.error("Could not save settings: %s", exc)
