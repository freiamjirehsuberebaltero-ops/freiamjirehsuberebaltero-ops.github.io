"""Detect Minecraft installations across platforms."""

import os
import sys
import json
import re
import zipfile
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
        logger.debug(
            "Created MinecraftInstallation: path=%s, versions=%s, mod_loader=%s, mods_dir=%s",
            path,
            self.versions,
            mod_loader,
            self.mods_dir,
        )

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
        logger.debug("MinecraftDetector initialized with extra_dirs: %s", self._extra_dirs)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def find_installations(self) -> List[MinecraftInstallation]:
        """Return a list of detected Minecraft installations."""
        logger.info("Starting scan for Minecraft installations...")
        candidates = self._default_candidates() + self._extra_dirs
        logger.debug("Total candidate paths to check: %d", len(candidates))
        results: List[MinecraftInstallation] = []
        seen: set = set()

        for idx, path in enumerate(candidates, 1):
            logger.debug("Checking candidate #%d: %s", idx, path)
            try:
                if not path.exists():
                    logger.debug("Path does not exist, skipping: %s", path)
                    continue
                path = path.resolve()
                logger.debug("Resolved path to: %s", path)
            except OSError as e:
                logger.warning("OSError while checking path %s: %s", path, e)
                continue

            if path in seen:
                logger.debug("Path already seen, skipping: %s", path)
                continue
            seen.add(path)

            logger.debug("Probing path: %s", path)
            inst = self._probe(path)
            if inst:
                logger.info("Found valid Minecraft installation at: %s", path)
                results.append(inst)
            else:
                logger.debug("Path is not a valid Minecraft installation: %s", path)

        logger.info("Scan complete. Found %d Minecraft installation(s)", len(results))
        return results

    def get_installed_mods(self, installation: MinecraftInstallation) -> List[Dict]:
        """Return metadata about JAR files with smart metadata extraction."""
        logger.debug("Loading mods from: %s", installation.mods_dir)
        mods: List[Dict] = []
        mods_dir = installation.mods_dir
        if not mods_dir.exists():
            logger.warning("Mods directory does not exist: %s", mods_dir)
            return mods
        try:
            jar_files = sorted(mods_dir.glob("*.jar"))
            logger.debug("Found %d JAR files in mods directory", len(jar_files))
            for jar in jar_files:
                try:
                    mod_name, mod_version = self._extract_mod_metadata(jar)
                    mod_info = {
                        "filename": jar.name,
                        "path": str(jar),
                        "size": jar.stat().st_size,
                        "mod_name": mod_name,
                        "mod_version": mod_version,
                    }
                    mods.append(mod_info)
                    logger.debug(
                        "Added mod: filename=%s, mod_name=%s, mod_version=%s",
                        jar.name,
                        mod_name,
                        mod_version,
                    )
                except OSError as e:
                    logger.warning("Failed to stat file %s: %s", jar, e)
                    continue
        except OSError as e:
            logger.error("Error reading mods directory %s: %s", mods_dir, e)
        logger.info("Loaded %d mods from %s", len(mods), mods_dir)
        return mods

    # ------------------------------------------------------------------
    # Mod metadata extraction (Smart Scanner)
    # ------------------------------------------------------------------

    @staticmethod
    def _clean_version(version: str, filename: str) -> str:
        """Extract version from filename if metadata version is a placeholder."""
        if version and ("${" in version or version == "N/A"):
            match = re.search(r'(\d+\.\d+(?:\.\d+)?(?:[\-\w\.]+)?)', filename)
            if match:
                return match.group(1)
        return version

    def _extract_mod_metadata(self, jar_path: Path) -> tuple:
        """Extract mod name and version from JAR metadata.
        
        Tries multiple strategies:
        1. Fabric (fabric.mod.json)
        2. Forge modern (META-INF/mods.toml)
        3. Forge legacy (mcmod.info)
        4. MANIFEST.MF fallback
        """
        filename = jar_path.name
        mod_name = filename.replace(".jar", "")
        mod_version = "N/A"

        try:
            with zipfile.ZipFile(jar_path, 'r') as jar:
                names = jar.namelist()

                # 1. Try Fabric
                if 'fabric.mod.json' in names:
                    try:
                        with jar.open('fabric.mod.json') as f:
                            data = json.load(f, strict=False)
                            mod_name = data.get('name', mod_name)
                            mod_version = data.get('version', mod_version)
                            logger.debug("Extracted Fabric metadata from %s: %s v%s", filename, mod_name, mod_version)
                    except Exception as e:
                        logger.debug("Failed to parse fabric.mod.json in %s: %s", filename, e)

                # 2. Try Forge modern (mods.toml)
                elif 'META-INF/mods.toml' in names:
                    try:
                        with jar.open('META-INF/mods.toml') as f:
                            content = f.read().decode('utf-8', errors='ignore')
                            name_match = re.search(r'displayName\s*=\s*"(.*?)"', content)
                            version_match = re.search(r'version\s*=\s*"(.*?)"', content)
                            if name_match:
                                mod_name = name_match.group(1)
                            if version_match:
                                mod_version = version_match.group(1)
                            logger.debug("Extracted Forge (modern) metadata from %s: %s v%s", filename, mod_name, mod_version)
                    except Exception as e:
                        logger.debug("Failed to parse mods.toml in %s: %s", filename, e)

                # 3. Try Forge legacy (mcmod.info)
                elif 'mcmod.info' in names:
                    try:
                        with jar.open('mcmod.info') as f:
                            content = f.read().decode('utf-8', errors='ignore')
                            # Clean up common JSON errors
                            content = re.sub(r',\s*([\]}])', r'\1', content)
                            data = json.loads(content)
                            if isinstance(data, list) and len(data) > 0:
                                mod_name = data[0].get('name', mod_name)
                                mod_version = data[0].get('version', mod_version)
                            logger.debug("Extracted Forge (legacy) metadata from %s: %s v%s", filename, mod_name, mod_version)
                    except Exception as e:
                        logger.debug("Failed to parse mcmod.info in %s: %s", filename, e)

                # 4. Fallback: Check MANIFEST.MF for version
                if "${" in mod_version or mod_version == "N/A":
                    if 'META-INF/MANIFEST.MF' in names:
                        try:
                            with jar.open('META-INF/MANIFEST.MF') as f:
                                for line in f:
                                    line_str = line.decode('utf-8', errors='ignore')
                                    if "Implementation-Version:" in line_str:
                                        mod_version = line_str.split(":", 1)[1].strip()
                                        logger.debug("Extracted version from MANIFEST.MF in %s: %s", filename, mod_version)
                                        break
                        except Exception as e:
                            logger.debug("Failed to parse MANIFEST.MF in %s: %s", filename, e)

        except zipfile.BadZipFile:
            logger.warning("File is not a valid ZIP/JAR: %s", jar_path)
            return (mod_name, mod_version)
        except Exception as e:
            logger.warning("Failed to extract metadata from %s: %s", jar_path, e)
            return (mod_name, mod_version)

        # Final cleanup: extract version from filename if still placeholder
        mod_version = self._clean_version(mod_version, filename)
        logger.debug("Final metadata for %s: %s v%s", filename, mod_name, mod_version)
        return (mod_name, mod_version)

    # ------------------------------------------------------------------
    # Default search paths per platform
    # ------------------------------------------------------------------

    def _default_candidates(self) -> List[Path]:
        logger.debug("Generating default candidate paths for platform: %s", sys.platform)
        system = sys.platform
        candidates: List[Path] = []

        if system == "win32":
            logger.debug("Detected Windows platform")
            appdata = os.environ.get("APPDATA", "")
            if appdata:
                candidates.append(Path(appdata) / ".minecraft")
                candidates.append(Path(appdata) / ".tlauncher" / ".minecraft")
                candidates.append(Path(appdata) / "TLauncher" / ".minecraft")
                logger.debug("Added Windows APPDATA candidates")
            else:
                logger.warning("APPDATA environment variable not set")
            for pf in ("ProgramFiles", "ProgramFiles(x86)"):
                pf_path = os.environ.get(pf, "")
                if pf_path:
                    candidates.append(
                        Path(pf_path) / "Minecraft Launcher" / ".minecraft"
                    )
                    logger.debug("Added %s candidate", pf)
                else:
                    logger.debug("%s environment variable not set", pf)

        elif system == "darwin":
            logger.debug("Detected macOS platform")
            mac_path = Path.home() / "Library" / "Application Support" / "minecraft"
            candidates.append(mac_path)
            logger.debug("Added macOS candidate: %s", mac_path)

        else:  # Linux / other POSIX
            logger.debug("Detected Linux/POSIX platform")
            home = Path.home()
            candidates.append(home / ".minecraft")
            xdg_data = os.environ.get("XDG_DATA_HOME", "")
            if xdg_data:
                candidates.append(Path(xdg_data) / ".minecraft")
                logger.debug("Added XDG_DATA_HOME candidate")
            else:
                logger.debug("XDG_DATA_HOME environment variable not set")
            candidates.append(
                home / ".var" / "app" / "com.mojang.Minecraft" / ".minecraft"
            )
            logger.debug("Added Linux candidates")

        logger.debug("Total default candidates generated: %d", len(candidates))
        return candidates

    # ------------------------------------------------------------------
    # Probe a single directory
    # ------------------------------------------------------------------

    def _probe(self, path: Path) -> Optional[MinecraftInstallation]:
        """Return a MinecraftInstallation if *path* looks like a .minecraft dir."""
        logger.debug("Probing directory: %s", path)
        if not path.is_dir():
            logger.debug("Path is not a directory: %s", path)
            return None

        # launcher_profiles.json is the strongest indicator
        launcher_profiles = path / "launcher_profiles.json"
        if launcher_profiles.exists():
            logger.info("Found launcher_profiles.json at: %s", path)
            return self._build_installation(path)

        # Fallback: any well-known subdirectory is enough
        known_subdirs = (
            "versions", "mods", "saves",
            "resourcepacks", "shaderpacks", "screenshots",
        )
        found_subdirs = [sub for sub in known_subdirs if (path / sub).is_dir()]
        if found_subdirs:
            logger.info("Found known subdirectories at %s: %s", path, found_subdirs)
            return self._build_installation(path)

        logger.debug("No launcher_profiles.json or known subdirs found at: %s", path)
        return None

    def _build_installation(self, path: Path) -> MinecraftInstallation:
        logger.debug("Building MinecraftInstallation for: %s", path)
        versions = self._detect_versions(path)
        loader = self._detect_loader(path, versions)
        logger.info("Detected versions: %s, loader: %s", versions, loader)
        return MinecraftInstallation(
            path=path,
            versions=versions,
            mod_loader=loader,
            mods_dir=path / "mods",
        )

    def _detect_versions(self, mc_dir: Path) -> List[str]:
        """List installed Minecraft version folders."""
        logger.debug("Detecting versions in: %s", mc_dir)
        versions_dir = mc_dir / "versions"
        if not versions_dir.is_dir():
            logger.debug("Versions directory does not exist: %s", versions_dir)
            return []
        versions: List[str] = []
        try:
            entries = sorted(versions_dir.iterdir())
            logger.debug("Found %d entries in versions directory", len(entries))
            for entry in entries:
                if entry.is_dir():
                    versions.append(entry.name)
                    logger.debug("Added version: %s", entry.name)
        except OSError as e:
            logger.error("Error reading versions directory %s: %s", versions_dir, e)
        logger.debug("Total versions detected: %d", len(versions))
        return versions

    def _detect_loader(self, mc_dir: Path, versions: List[str]) -> str:
        """Heuristically detect the active mod loader for this installation."""
        logger.info("=" * 60)
        logger.info("LOADER DETECTION START for: %s", mc_dir)
        logger.info("=" * 60)
        
        # PRIORITY 1: Check for loader installer JARs
        logger.info("STEP 1: Checking for loader installer JARs in root directory...")
        installer_checks = {
            "NeoForge": [mc_dir / "neoforge-installer.jar"],
            "Forge": [mc_dir / "forge-installer.jar"],
            "Quilt": [mc_dir / "quilt-installer.jar"],
            "Fabric": [mc_dir / "fabric-installer.jar"],
        }
        for loader, paths in installer_checks.items():
            for path in paths:
                exists = path.exists()
                logger.info("  Checking: %s -> %s", path, "FOUND" if exists else "not found")
                if exists:
                    logger.info("✓✓✓ DETECTED LOADER: %s (installer JAR)", loader)
                    return loader
        
        # PRIORITY 2: Check for loader marker directories
        logger.info("STEP 2: Checking for loader marker directories...")
        marker_checks = {
            "Quilt": [mc_dir / ".quilt", mc_dir / "quilt_loader.jar"],
            "Fabric": [mc_dir / ".fabric", mc_dir / "fabric-loader.jar"],
        }
        for loader, paths in marker_checks.items():
            for path in paths:
                exists = path.exists()
                logger.info("  Checking: %s -> %s", path, "FOUND" if exists else "not found")
                if exists:
                    logger.info("✓✓✓ DETECTED LOADER: %s (marker)", loader)
                    return loader
        
        # PRIORITY 3: Inspect mod JARs
        logger.info("STEP 3: Inspecting mod JARs for loader metadata...")
        mods_dir = mc_dir / "mods"
        logger.info("  Mods directory: %s", mods_dir)
        logger.info("  Mods directory exists: %s", mods_dir.exists())
        if mods_dir.is_dir():
            detected = self._inspect_jars_for_loader(mods_dir)
            if detected:
                logger.info("✓✓✓ DETECTED LOADER: %s (mod JAR metadata)", detected)
                return detected
        
        # PRIORITY 4: Check version folder names
        logger.info("STEP 4: Checking version folder names...")
        logger.info("  Available versions: %s", versions)
        if versions:
            for version_name in versions:
                lower = version_name.lower()
                logger.info("  Checking version: %s", version_name)
                if "neoforge" in lower:
                    logger.info("✓✓✓ DETECTED LOADER: NeoForge (version name)")
                    return "NeoForge"
                if "forge" in lower:
                    logger.info("✓✓✓ DETECTED LOADER: Forge (version name)")
                    return "Forge"
                if "quilt" in lower:
                    logger.info("✓✓✓ DETECTED LOADER: Quilt (version name)")
                    return "Quilt"
                if "fabric" in lower:
                    logger.info("✓✓✓ DETECTED LOADER: Fabric (version name)")
                    return "Fabric"
        
        logger.warning("✗✗✗ NO LOADER DETECTED")
        logger.info("=" * 60)
        return ""

    def _inspect_jars_for_loader(self, mods_dir: Path) -> str:
        """Look inside JARs for loader-specific metadata files."""
        logger.info("  Examining JAR files in: %s", mods_dir)
        
        try:
            jar_files = list(mods_dir.glob("*.jar"))
            logger.info("  Found %d JAR files", len(jar_files))
            
            for jar_path in jar_files[:10]:  # Only check first 10 to avoid spam
                logger.debug("  Checking JAR: %s", jar_path.name)
                try:
                    with zipfile.ZipFile(jar_path, 'r') as zf:
                        names = zf.namelist()
                        
                        # Check for NeoForge
                        neoforge_files = [n for n in names if "neoforge" in n.lower()]
                        if neoforge_files:
                            logger.info("    → Found NeoForge in: %s", jar_path.name)
                            return "NeoForge"
                        
                        # Check for Quilt
                        if "quilt.mod.json" in names:
                            logger.info("    → Found Quilt in: %s", jar_path.name)
                            return "Quilt"
                        
                        # Check for Fabric
                        if "fabric.mod.json" in names:
                            logger.info("    → Found Fabric in: %s", jar_path.name)
                            return "Fabric"
                        
                        # Check for Forge
                        if "META-INF/mods.toml" in names:
                            logger.info("    → Found Forge (mods.toml) in: %s", jar_path.name)
                            return "Forge"
                        
                        if "mcmod.info" in names:
                            logger.info("    → Found Forge (mcmod.info) in: %s", jar_path.name)
                            return "Forge"
                            
                except zipfile.BadZipFile:
                    logger.debug("    ✗ Invalid ZIP: %s", jar_path.name)
                    continue
                except Exception as e:
                    logger.debug("    ✗ Error reading: %s (%s)", jar_path.name, e)
                    continue
            
            logger.info("  No loader metadata found in mod JARs")
        except Exception as e:
            logger.error("  Error reading mods directory: %s", e)
        
        return ""
    def _detect_loader_for_version(self, mc_dir: Path, version: str) -> str:
        """Detect the mod loader for a specific Minecraft version.
        
        This checks the version folder for loader-specific files.
        """
        logger.info("Detecting loader for version: %s", version)
        version_dir = mc_dir / "versions" / version
        
        if not version_dir.exists():
            logger.warning("Version directory not found: %s", version_dir)
            return ""
        
        # Check if version directory name contains loader hints
        lower = version.lower()
        if "neoforge" in lower:
            logger.info("Version %s is NeoForge", version)
            return "NeoForge"
        if "forge" in lower:
            logger.info("Version %s is Forge", version)
            return "Forge"
        if "quilt" in lower:
            logger.info("Version %s is Quilt", version)
            return "Quilt"
        if "fabric" in lower:
            logger.info("Version %s is Fabric", version)
            return "Fabric"
        
        logger.info("Could not determine loader from version name: %s", version)
        return ""