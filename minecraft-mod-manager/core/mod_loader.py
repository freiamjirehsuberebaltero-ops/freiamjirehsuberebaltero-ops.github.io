"""Identify mod loaders from Minecraft installation directories."""

import zipfile
from pathlib import Path
from typing import Optional

from utils.logger import get_logger

logger = get_logger("mod_loader")

KNOWN_LOADERS = ("Forge", "Fabric", "Quilt", "NeoForge")


class ModLoaderDetector:
    """Probe a Minecraft installation to determine the active mod loader."""

    def detect(self, mc_dir: Path) -> str:
        """Return the loader name or empty string if unknown."""
        mc_dir = Path(mc_dir)

        # 1. Check versions folder names
        versions_dir = mc_dir / "versions"
        if versions_dir.is_dir():
            for entry in sorted(versions_dir.iterdir()):
                if not entry.is_dir():
                    continue
                lower = entry.name.lower()
                if "neoforge" in lower:
                    return "NeoForge"
                if "forge" in lower:
                    return "Forge"
                if "quilt" in lower:
                    return "Quilt"
                if "fabric" in lower:
                    return "Fabric"

        # 2. Check for marker files / dirs
        markers = {
            "NeoForge": [mc_dir / "neoforge-installer.jar"],
            "Forge": [mc_dir / "forge-installer.jar"],
            "Quilt": [mc_dir / ".quilt", mc_dir / "quilt_loader.jar"],
            "Fabric": [mc_dir / ".fabric", mc_dir / "fabric-loader.jar"],
        }
        for loader, paths in markers.items():
            if any(p.exists() for p in paths):
                return loader

        # 3. Inspect installed JARs in the mods folder
        mods_dir = mc_dir / "mods"
        if mods_dir.is_dir():
            detected = self._inspect_jars(mods_dir)
            if detected:
                return detected

        return ""

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _inspect_jars(self, mods_dir: Path) -> str:
        """Look inside JARs for loader-specific metadata files."""
        for jar_path in mods_dir.glob("*.jar"):
            try:
                with zipfile.ZipFile(jar_path, "r") as zf:
                    names = zf.namelist()
                    if "quilt.mod.json" in names:
                        return "Quilt"
                    if "fabric.mod.json" in names:
                        return "Fabric"
                    if any(n.startswith("META-INF/neoforge") for n in names):
                        return "NeoForge"
                    if "META-INF/mods.toml" in names or any(
                        n.endswith("mcmod.info") for n in names
                    ):
                        return "Forge"
            except (zipfile.BadZipFile, OSError):
                continue
        return ""
