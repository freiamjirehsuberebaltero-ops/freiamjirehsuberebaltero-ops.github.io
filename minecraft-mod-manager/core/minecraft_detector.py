"""Detect Minecraft installations across platforms."""

import json
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
        print("\n" + "="*60)
        print("🔍 STARTING MINECRAFT INSTALLATION SCAN")
        print("="*60)
        
        candidates = self._default_candidates() + self._extra_dirs
        print(f"\n📋 Total paths to check: {len(candidates)}")
        for i, cand in enumerate(candidates, 1):
            print(f"   [{i}] {cand}")
        
        results: List[MinecraftInstallation] = []
        seen: set = set()
        
        for idx, path in enumerate(candidates, 1):
            print(f"\n⏳ [{idx}/{len(candidates)}] Checking: {path}")
            
            # Quick skip if path doesn't exist
            try:
                exists = path.exists()
                print(f"      → Path exists: {exists}")
                if not exists:
                    print(f"      ❌ SKIP (path doesn't exist)")
                    continue
            except Exception as exc:
                print(f"      ❌ ERROR checking path: {exc}")
                continue
            
            try:
                path = path.resolve()
                print(f"      → Resolved: {path}")
            except Exception as exc:
                print(f"      ❌ ERROR resolving path: {exc}")
                continue
            
            if path in seen:
                print(f"      ❌ SKIP (already checked)")
                continue
            
            seen.add(path)
            print(f"      → Probing directory...")
            
            try:
                inst = self._probe(path)
                if inst:
                    results.append(inst)
                    print(f"      ✅ FOUND! Versions: {inst.versions}, Loader: {inst.mod_loader}")
                else:
                    print(f"      ❌ Not a Minecraft installation")
            except Exception as exc:
                print(f"      ❌ ERROR during probe: {exc}")
                continue
        
        print("\n" + "="*60)
        print(f"✅ SCAN COMPLETE - Found {len(results)} installation(s)")
        print("="*60 + "\n")
        
        logger.info("Found %d Minecraft installations", len(results))
        return results

    def get_installed_mods(self, installation: MinecraftInstallation) -> List[Dict]:
        """Return metadata about JAR files in the mods directory."""
        print(f"\n📦 Loading mods from: {installation.mods_dir}")
        mods: List[Dict] = []
        mods_dir = installation.mods_dir
        
        try:
            exists = mods_dir.exists()
            print(f"   → Mods directory exists: {exists}")
            if not exists:
                print(f"   ❌ Mods directory not found")
                return mods
        except Exception as exc:
            print(f"   ❌ ERROR: {exc}")
            return mods
        
        try:
            jar_files = list(sorted(mods_dir.glob("*.jar")))
            print(f"   → Found {len(jar_files)} JAR files")
            
            for jar in jar_files:
                try:
                    stat = jar.stat()
                    size_kb = stat.st_size / 1024
                    mods.append(
                        {
                            "filename": jar.name,
                            "path": str(jar),
                            "size": stat.st_size,
                        }
                    )
                    print(f"      ✓ {jar.name} ({size_kb:.1f} KB)")
                except OSError as exc:
                    print(f"      ❌ Error reading {jar.name}: {exc}")
                    continue
        except Exception as exc:
            print(f"   ❌ ERROR reading directory: {exc}")
        
        print(f"   ✅ Loaded {len(mods)} mods total\n")
        logger.info("Loaded %d mods from %s", len(mods), mods_dir)
        return mods

    # ------------------------------------------------------------------
    # Default search paths per platform
    # ------------------------------------------------------------------

    def _default_candidates(self) -> List[Path]:
        system = sys.platform
        print(f"\n🖥️  System detected: {system}")
        candidates: List[Path] = []

        if system == "win32":
            appdata = os.environ.get("APPDATA", "")
            print(f"   APPDATA: {appdata}")
            if appdata:
                candidates.append(Path(appdata) / ".minecraft")
                candidates.append(Path(appdata) / ".tlauncher" / ".minecraft")
                candidates.append(Path(appdata) / "TLauncher" / ".minecraft")
            
            for pf in ("ProgramFiles", "ProgramFiles(x86)"):
                pf_path = os.environ.get(pf, "")
                if pf_path:
                    print(f"   {pf}: {pf_path}")
                    candidates.append(
                        Path(pf_path) / "Minecraft Launcher" / ".minecraft"
                    )

        elif system == "darwin":
            home = Path.home()
            print(f"   Home: {home}")
            candidates.append(
                home / "Library" / "Application Support" / "minecraft"
            )

        else:  # Linux / other POSIX
            home = Path.home()
            print(f"   Home: {home}")
            candidates.append(home / ".minecraft")
            xdg_data = os.environ.get("XDG_DATA_HOME", "")
            if xdg_data:
                print(f"   XDG_DATA_HOME: {xdg_data}")
                candidates.append(Path(xdg_data) / ".minecraft")
            candidates.append(
                home
                / ".var"
                / "app"
                / "com.mojang.Minecraft"
                / ".minecraft"
            )

        print(f"   Total candidates: {len(candidates)}")
        return candidates

    # ------------------------------------------------------------------
    # Probe a single directory
    # ------------------------------------------------------------------

    def _probe(self, path: Path) -> Optional[MinecraftInstallation]:
        """Quickly probe if a directory is a valid Minecraft installation."""
        try:
            is_dir = path.is_dir()
            if not is_dir:
                print(f"         Not a directory")
                return None
        except Exception as exc:
            print(f"         ERROR: {exc}")
            return None
        
        # Fast check: launcher_profiles.json is the strongest indicator
        launcher_profiles = path / "launcher_profiles.json"
        try:
            lp_exists = launcher_profiles.exists()
            if lp_exists:
                print(f"         ✓ Found launcher_profiles.json")
                versions = self._detect_versions(path)
                mod_loader = self._detect_loader(path)
                inst = MinecraftInstallation(
                    path=path,
                    versions=versions,
                    mod_loader=mod_loader,
                    mods_dir=path / "mods",
                )
                return inst
        except Exception as exc:
            print(f"         ERROR checking launcher_profiles.json: {exc}")
        
        # Fallback: check for essential subdirectories
        essential_dirs = ("versions", "mods")
        has_essential = False
        
        try:
            for subdir in essential_dirs:
                subpath = path / subdir
                try:
                    is_subdir = subpath.is_dir()
                    if is_subdir:
                        print(f"         ✓ Found {subdir}/ directory")
                        has_essential = True
                        break
                except Exception as exc:
                    print(f"         ERROR checking {subdir}/: {exc}")
                    continue
        except Exception as exc:
            print(f"         ERROR: {exc}")
            return None
        
        if has_essential:
            versions = self._detect_versions(path)
            mod_loader = self._detect_loader(path)
            inst = MinecraftInstallation(
                path=path,
                versions=versions,
                mod_loader=mod_loader,
                mods_dir=path / "mods",
            )
            return inst
        
        return None

    def _detect_versions(self, mc_dir: Path) -> List[str]:
        """List installed Minecraft version folders."""
        versions_dir = mc_dir / "versions"
        
        try:
            is_dir = versions_dir.is_dir()
            if not is_dir:
                return []
        except Exception as exc:
            print(f"         ERROR reading versions: {exc}")
            return []
        
        versions: List[str] = []
        try:
            entries = sorted(versions_dir.iterdir())
            for entry in entries:
                try:
                    if entry.is_dir():
                        versions.append(entry.name)
                except Exception as exc:
                    continue
        except Exception as exc:
            print(f"         ERROR iterating versions: {exc}")
        
        return versions

    def _detect_loader(self, mc_dir: Path) -> str:
        """Heuristically detect the active mod loader for this installation."""
        mods_dir = mc_dir / "mods"

        # Check for loader-specific directories / files (fast checks first)
        loader_hints: Dict[str, List[Path]] = {
            "Fabric": [mc_dir / ".fabric"],
            "Quilt": [mc_dir / ".quilt"],
            "NeoForge": [mc_dir / "neoforge-installer.jar"],
            "Forge": [mc_dir / "forge-installer.jar"],
        }
        
        for loader, hints in loader_hints.items():
            for hint in hints:
                try:
                    exists = hint.exists()
                    if exists:
                        return loader
                except Exception as exc:
                    continue

        # Fall back to inspecting the versions folder names
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
            except Exception as exc:
                pass

        return ""