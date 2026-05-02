"""Application-wide constants and default paths."""

import os
import sys
from pathlib import Path

# ------------------------------------------------------------------
# Application metadata
# ------------------------------------------------------------------
APP_NAME = "Minecraft Mod Manager"
APP_VERSION = "1.0.0"

# ------------------------------------------------------------------
# Directories
# ------------------------------------------------------------------
if sys.platform == "win32":
    _base = Path(os.environ.get("APPDATA", Path.home()))
elif sys.platform == "darwin":
    _base = Path.home() / "Library" / "Application Support"
else:
    _base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))

APP_DIR = _base / "MinecraftModManager"
CONFIG_DIR = APP_DIR / "config"
PROFILES_DIR = APP_DIR / "profiles"
BACKUP_DIR = APP_DIR / "backups"
LOGS_DIR = APP_DIR / "logs"

# ------------------------------------------------------------------
# Supported Minecraft versions
# ------------------------------------------------------------------
MC_VERSIONS = [
    "1.20.4", "1.20.2", "1.20.1", "1.20",
    "1.19.4", "1.19.3", "1.19.2", "1.19.1", "1.19",
    "1.18.2", "1.18.1", "1.18",
    "1.17.1", "1.17",
    "1.16.5", "1.16.4", "1.16.3", "1.16.2", "1.16.1", "1.16",
    "1.15.2", "1.15.1", "1.15",
    "1.14.4", "1.14.3", "1.14.2", "1.14.1", "1.14",
    "1.12.2", "1.12.1", "1.12",
    "1.8.9", "1.8",
]

# ------------------------------------------------------------------
# Supported mod loaders
# ------------------------------------------------------------------
MOD_LOADERS = ["Forge", "Fabric", "Quilt", "NeoForge"]

# ------------------------------------------------------------------
# API configuration
# ------------------------------------------------------------------
CURSEFORGE_BASE_URL = "https://api.curseforge.com/v1"
MODRINTH_BASE_URL = "https://api.modrinth.com/v2"

# CurseForge game id for Minecraft
CURSEFORGE_MINECRAFT_GAME_ID = 432
CURSEFORGE_MODS_CLASS_ID = 6

# HTTP request timeout (seconds)
REQUEST_TIMEOUT = 30

# ------------------------------------------------------------------
# File patterns
# ------------------------------------------------------------------
MOD_FILE_EXTENSIONS = (".jar",)
PROFILE_FILE_EXTENSION = ".json"
