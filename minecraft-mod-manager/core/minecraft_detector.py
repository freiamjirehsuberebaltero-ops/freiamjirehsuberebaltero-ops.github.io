"""Detect Minecraft installations across platforms."""

import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

from utils.logger import get_logger

logger = get_logger("minecraft_detector")


class MinecraftInstallation:
    """Represents a single Minecraft installation directory."""

    def __init__(
        self,
        path: Path,
        versions: Optional[List[str]] = None,
        mod_loader: str = "",
        mods_dir: Optional[Path] = None,
    ) -> None:
        self.path = path
        self.versions = versions or []
        self.mod_loader = mod_loader
        self.mods_dir = mods_dir or (path / "mods")

    @property
    def display_name(self) -> str:
        versions_str = ", ".join(self.versions) if self.versions else "unknown"
        loader_str = f" [{self.mod_loader}]" if self.mod_loader else ""
        return f"{self.path}{loader_str} ({versions_str})"

    def __repr__(self) -> str:  # pragma: no cover
        return f"<MinecraftInstallation {self.path}>"


class MinecraftDetector:
    """Scans the file system for Minecraft installations."""

    def __init__(self, extra_dirs: Optional[List[str]] = None) -> None:
        self._extra_dirs: List[Path] = [Path(d) for d in (extra_dirs or [])]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def find_installations(self) -> List[MinecraftInstallation]:
        """Return a list of detected Minecraft installations."""
        candidates = self._default_candidates() + self._extra_dirs
        results: List[MinecraftInstallation] = []
        seen: set = set()

        for path in candidates:
            try:
                if not path.exists():
                    continue
                path = path.resolve()
            except OSError:
                continue

            if path in seen:
                continue
            seen.add(path)

            inst = self._probe(path)
            if inst:
                results.append(inst)

        logger.info("Found %d Minecraft installation(s)", len(results))
        return results

    def get_installed_mods(self, installation: MinecraftInstallation) -> List[Dict]:
        """Return metadata about JAR files in the mods directory."""
        mods: List[Dict] = []
        mods_dir = installation.mods_dir
        if not mods_dir.exists():
            return mods
        for jar in sorted(mods_dir.glob("*.jar")):
            try:
                mods.append(
                    {
                        "filename": jar.name,
                        "path": str(jar),
                        "size": jar.stat().st_size,
                    }
                )
            except OSError:
                continue
        logger.info("Loaded %d mods from %s", len(mods), mods_dir)
        return mods

    # ------------------------------------------------------------------
    # Default search paths per platform
    # ------------------------------------------------------------------

    def _default_candidates(self) -> List[Path]:
        system = sys.platform
        candidates: List[Path] = []

        if system == "win32":
            appdata = os.environ.get("APPDATA", "")
            if appdata:
                candidates.append(Path(appdata) / ".minecraft")
                candidates.append(Path(appdata) / ".tlauncher" / ".minecraft")
                candidates.append(Path(appdata) / "TLauncher" / ".minecraft")
            for pf in ("ProgramFiles", "ProgramFiles(x86)"):
                pf_path = os.environ.get(pf, "")
                if pf_path:
                    candidates.append(
                        Path(pf_path) / "Minecraft Launcher" / ".minecraft"
                    )

        elif system == "darwin":
            candidates.append(
                Path.home() / "Library" / "Application Support" / "minecraft"
            )

        else:  # Linux / other POSIX
            home = Path.home()
            candidates.append(home / ".minecraft")
            xdg_data = os.environ.get("XDG_DATA_HOME", "")
            if xdg_data:
                candidates.append(Path(xdg_data) / ".minecraft")
            candidates.append(
                home / ".var" / "app" / "com.mojang.Minecraft" / ".minecraft"
            )

        return candidates

    # ------------------------------------------------------------------
    # Probe a single directory
    # ------------------------------------------------------------------

    def _probe(self, path: Path) -> Optional[MinecraftInstallation]:
        """Return a MinecraftInstallation if *path* looks like a .minecraft dir."""
        if not path.is_dir():
            return None

        # launcher_profiles.json is the strongest indicator
        if (path / "launcher_profiles.json").exists():
            return self._build_installation(path)

        # Fallback: any well-known subdirectory is enough
        known_subdirs = (
            "versions", "mods", "saves",
            "resourcepacks", "shaderpacks", "screenshots",
        )
        if any((path / sub).is_dir() for sub in known_subdirs):
            return self._build_installation(path)

        return None

    def _build_installation(self, path: Path) -> MinecraftInstallation:
        return MinecraftInstallation(
            path=path,
            versions=self._detect_versions(path),
            mod_loader=self._detect_loader(path),
            mods_dir=path / "mods",
        )

    def _detect_versions(self, mc_dir: Path) -> List[str]:
        """List installed Minecraft version folders."""
        versions_dir = mc_dir / "versions"
        if not versions_dir.is_dir():
            return []
        versions: List[str] = []
        try:
            for entry in sorted(versions_dir.iterdir()):
                if entry.is_dir():
                    versions.append(entry.name)
        except OSError:
            pass
        return versions

    def _detect_loader(self, mc_dir: Path) -> str:
        """Heuristically detect the active mod loader for this installation."""
        loader_hints: Dict[str, List[Path]] = {
            "Fabric": [mc_dir / ".fabric"],
            "Quilt": [mc_dir / ".quilt"],
            "NeoForge": [mc_dir / "neoforge-installer.jar"],
            "Forge": [mc_dir / "forge-installer.jar"],
        }
        for loader, hints in loader_hints.items():
            for hint in hints:
                try:
                    if hint.exists():
                        return loader
                except OSError:
                    continue

        versions_dir = mc_dir / "versions"
        if versions_dir.is_dir():
            try:
                names = [e.name.lower() for e in versions_dir.iterdir() if e.is_dir()]
                for name in names:
                    if "neoforge" in name:
                        return "NeoForge"
                    if "forge" in name:
                        return "Forge"
                    if "quilt" in name:
                        return "Quilt"
                    if "fabric" in name:
                        return "Fabric"
            except OSError:
                pass

        return ""