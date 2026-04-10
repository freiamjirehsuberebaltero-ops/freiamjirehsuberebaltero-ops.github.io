"""Core mod operations: install, update, remove, backup."""

import shutil
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from apis.base_api import ModInfo, ModVersion
from apis.modrinth_api import ModrinthAPI
from apis.curseforge_api import CurseForgeAPI
from utils.constants import BACKUP_DIR
from utils.logger import get_logger

logger = get_logger("mod_manager")

ProgressCallback = Callable[[int, int], None]


class ModManager:
    """High-level operations for managing mods in a Minecraft installation."""

    def __init__(
        self,
        modrinth_api: Optional[ModrinthAPI] = None,
        curseforge_api: Optional[CurseForgeAPI] = None,
        backup_dir: Optional[Path] = None,
        max_backups: int = 5,
    ) -> None:
        self._modrinth = modrinth_api or ModrinthAPI()
        self._curseforge = curseforge_api or CurseForgeAPI()
        self._backup_dir = backup_dir or BACKUP_DIR
        self._max_backups = max_backups
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        game_version: str = "",
        mod_loader: str = "",
        source: str = "both",
        page: int = 0,
        page_size: int = 20,
    ) -> List[ModInfo]:
        """Search for mods across one or both platforms."""
        results: List[ModInfo] = []
        if source in ("modrinth", "both"):
            results += self._modrinth.search_mods(
                query, game_version, mod_loader, page, page_size
            )
        if source in ("curseforge", "both"):
            results += self._curseforge.search_mods(
                query, game_version, mod_loader, page, page_size
            )
        # De-duplicate by (source, id)
        seen: set = set()
        unique: List[ModInfo] = []
        for m in results:
            key = (m.source, m.id)
            if key not in seen:
                seen.add(key)
                unique.append(m)
        return unique

    # ------------------------------------------------------------------
    # Version listing
    # ------------------------------------------------------------------

    def get_versions(
        self,
        mod: ModInfo,
        game_version: str = "",
        mod_loader: str = "",
    ) -> List[ModVersion]:
        """Fetch available versions for a ModInfo object."""
        api = self._modrinth if mod.source == "modrinth" else self._curseforge
        return api.get_mod_versions(mod.id, game_version, mod_loader)

    # ------------------------------------------------------------------
    # Install
    # ------------------------------------------------------------------

    def install_mod(
        self,
        version: ModVersion,
        mods_dir: Path,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> bool:
        """Download a specific mod version into *mods_dir*."""
        mods_dir = Path(mods_dir)
        mods_dir.mkdir(parents=True, exist_ok=True)
        dest = mods_dir / version.filename
        if dest.exists():
            logger.info("Mod already installed: %s", dest)
            return True

        api = self._modrinth if version.source == "modrinth" else self._curseforge
        logger.info("Installing %s -> %s", version.filename, mods_dir)
        return api.download_file(version.download_url, str(dest), progress_callback)

    # ------------------------------------------------------------------
    # Remove
    # ------------------------------------------------------------------

    def remove_mod(self, mod_path: Path, backup: bool = True) -> bool:
        """Delete (or back up and delete) a mod JAR file."""
        mod_path = Path(mod_path)
        if not mod_path.exists():
            logger.warning("Mod not found: %s", mod_path)
            return False
        if backup:
            self._backup_file(mod_path)
        mod_path.unlink()
        logger.info("Removed mod: %s", mod_path)
        return True

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update_mod(
        self,
        installed_path: Path,
        new_version: ModVersion,
        mods_dir: Path,
        progress_callback: Optional[ProgressCallback] = None,
        backup: bool = True,
    ) -> bool:
        """Replace an installed mod with a new version."""
        installed_path = Path(installed_path)
        if backup and installed_path.exists():
            self._backup_file(installed_path)
        if installed_path.exists():
            installed_path.unlink()
        return self.install_mod(new_version, mods_dir, progress_callback)

    # ------------------------------------------------------------------
    # Check for updates
    # ------------------------------------------------------------------

    def check_for_updates(
        self,
        installed_mods: List[Dict],
        game_version: str,
        mod_loader: str,
    ) -> List[Dict[str, Any]]:
        """Compare installed filenames against available versions.

        Returns a list of dicts describing available updates.
        """
        updates: List[Dict[str, Any]] = []
        for mod_info in installed_mods:
            filename = mod_info.get("filename", "")
            # Very simple heuristic: search by filename stem
            stem = Path(filename).stem
            search_results = self._modrinth.search_mods(stem, game_version, mod_loader)
            if not search_results:
                continue
            match = search_results[0]
            versions = self._modrinth.get_mod_versions(match.id, game_version, mod_loader)
            if versions:
                latest = versions[0]
                if latest.filename != filename:
                    updates.append(
                        {
                            "current_path": mod_info.get("path", ""),
                            "current_filename": filename,
                            "new_version": latest,
                            "mod_info": match,
                        }
                    )
        return updates

    # ------------------------------------------------------------------
    # Dependency resolution
    # ------------------------------------------------------------------

    def resolve_dependencies(
        self,
        version: ModVersion,
        game_version: str,
        mod_loader: str,
        mods_dir: Path,
    ) -> List[ModVersion]:
        """Return a list of ModVersion objects that need to be installed.

        Only 'required' dependencies that are not already installed are
        included.
        """
        to_install: List[ModVersion] = []
        installed_names = {p.name for p in Path(mods_dir).glob("*.jar")}

        for dep in version.dependencies:
            if dep.get("dependency_type") not in ("required", 3):
                continue
            dep_id = dep.get("mod_id", "")
            if not dep_id:
                continue
            dep_versions = self._modrinth.get_mod_versions(
                dep_id, game_version, mod_loader
            )
            if not dep_versions:
                continue
            latest_dep = dep_versions[0]
            if latest_dep.filename not in installed_names:
                to_install.append(latest_dep)
        return to_install

    # ------------------------------------------------------------------
    # Compatibility check
    # ------------------------------------------------------------------

    @staticmethod
    def check_compatibility(
        version: ModVersion,
        game_version: str,
        mod_loader: str,
    ) -> Dict[str, Any]:
        """Return a compatibility report for *version*."""
        version_ok = not version.game_versions or game_version in version.game_versions
        loader_ok = not version.mod_loaders or mod_loader.lower() in [
            ml.lower() for ml in version.mod_loaders
        ]
        warnings: List[str] = []
        if not version_ok:
            warnings.append(
                f"Mod does not support MC {game_version}. "
                f"Supported: {', '.join(version.game_versions)}"
            )
        if not loader_ok:
            warnings.append(
                f"Mod requires {', '.join(version.mod_loaders)}, "
                f"but selected loader is {mod_loader}."
            )
        return {
            "compatible": version_ok and loader_ok,
            "version_ok": version_ok,
            "loader_ok": loader_ok,
            "warnings": warnings,
        }

    # ------------------------------------------------------------------
    # Backup helpers
    # ------------------------------------------------------------------

    def _backup_file(self, src: Path) -> None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dest = self._backup_dir / timestamp / src.name
        backup_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, backup_dest)
        logger.info("Backed up %s -> %s", src, backup_dest)
        self._prune_backups()

    def _prune_backups(self) -> None:
        if not self._backup_dir.exists():
            return
        snapshots = sorted(self._backup_dir.iterdir())
        while len(snapshots) > self._max_backups:
            oldest = snapshots.pop(0)
            shutil.rmtree(oldest, ignore_errors=True)
            logger.debug("Pruned old backup: %s", oldest)
