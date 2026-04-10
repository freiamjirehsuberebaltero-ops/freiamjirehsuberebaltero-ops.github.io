"""Mod-pack profile save / load / export / import."""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.constants import PROFILES_DIR
from utils.logger import get_logger

logger = get_logger("profile_manager")


class ModProfile:
    """Represents a saved collection of mods with version pins."""

    def __init__(
        self,
        name: str,
        minecraft_version: str = "",
        mod_loader: str = "",
        mods: Optional[List[Dict[str, Any]]] = None,
        description: str = "",
        created_at: str = "",
        updated_at: str = "",
    ) -> None:
        self.name = name
        self.minecraft_version = minecraft_version
        self.mod_loader = mod_loader
        self.mods: List[Dict[str, Any]] = mods or []
        self.description = description
        self.created_at = created_at or datetime.now().isoformat()
        self.updated_at = updated_at or self.created_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "minecraft_version": self.minecraft_version,
            "mod_loader": self.mod_loader,
            "mods": self.mods,
            "description": self.description,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModProfile":
        return cls(
            name=data.get("name", "Unnamed"),
            minecraft_version=data.get("minecraft_version", ""),
            mod_loader=data.get("mod_loader", ""),
            mods=data.get("mods", []),
            description=data.get("description", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )

    def add_mod(
        self,
        mod_id: str,
        mod_name: str,
        version_id: str,
        version_number: str,
        filename: str,
        source: str,
    ) -> None:
        # Replace existing entry for same mod
        self.mods = [m for m in self.mods if m.get("mod_id") != mod_id]
        self.mods.append(
            {
                "mod_id": mod_id,
                "mod_name": mod_name,
                "version_id": version_id,
                "version_number": version_number,
                "filename": filename,
                "source": source,
            }
        )
        self.updated_at = datetime.now().isoformat()

    def remove_mod(self, mod_id: str) -> None:
        self.mods = [m for m in self.mods if m.get("mod_id") != mod_id]
        self.updated_at = datetime.now().isoformat()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ModProfile {self.name!r} ({len(self.mods)} mods)>"


class ProfileManager:
    """Handles persistence of ModProfile objects as JSON files."""

    def __init__(self, profiles_dir: Optional[Path] = None) -> None:
        self._dir = profiles_dir or PROFILES_DIR
        self._dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def list_profiles(self) -> List[str]:
        """Return a sorted list of saved profile names."""
        return sorted(
            p.stem for p in self._dir.glob("*.json")
        )

    def load_profile(self, name: str) -> Optional[ModProfile]:
        path = self._profile_path(name)
        if not path.exists():
            logger.warning("Profile not found: %s", name)
            return None
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return ModProfile.from_dict(data)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Failed to load profile %s: %s", name, exc)
            return None

    def save_profile(self, profile: ModProfile) -> bool:
        path = self._profile_path(profile.name)
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(profile.to_dict(), fh, indent=2)
            logger.info("Saved profile: %s", profile.name)
            return True
        except OSError as exc:
            logger.error("Failed to save profile %s: %s", profile.name, exc)
            return False

    def delete_profile(self, name: str) -> bool:
        path = self._profile_path(name)
        if not path.exists():
            return False
        path.unlink()
        logger.info("Deleted profile: %s", name)
        return True

    # ------------------------------------------------------------------
    # Import / Export
    # ------------------------------------------------------------------

    def export_profile(self, name: str, dest_path: Path) -> bool:
        """Copy a profile JSON to an external location."""
        src = self._profile_path(name)
        if not src.exists():
            return False
        try:
            shutil.copy2(src, dest_path)
            return True
        except OSError as exc:
            logger.error("Export failed: %s", exc)
            return False

    def import_profile(self, src_path: Path) -> Optional[ModProfile]:
        """Import a profile JSON file into the profiles directory."""
        try:
            with open(src_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            profile = ModProfile.from_dict(data)
            self.save_profile(profile)
            return profile
        except (json.JSONDecodeError, OSError, KeyError) as exc:
            logger.error("Import failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _profile_path(self, name: str) -> Path:
        safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in name)
        return self._dir / f"{safe_name}.json"
