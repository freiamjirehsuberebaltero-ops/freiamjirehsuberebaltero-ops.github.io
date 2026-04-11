# Minecraft Mod Manager

A cross-platform desktop application for browsing, installing, updating, and managing Minecraft mods — powered by the [Modrinth](https://modrinth.com) and [CurseForge](https://www.curseforge.com) APIs.

---

## Features

- **Mod Browser** — Search mods from Modrinth and/or CurseForge with filters for Minecraft version and mod loader.
- **One-click Install** — Download and install mod JARs directly into any Minecraft installation directory.
- **Update Checking** — Detect outdated mods and update them in place.
- **Dependency Resolution** — Automatically identifies and installs required mod dependencies.
- **Compatibility Checking** — Warns you when a mod doesn't support your selected Minecraft version or loader.
- **Profile Management** — Save named mod collections (profiles) tied to a specific Minecraft version and loader. Import and export profiles as JSON files.
- **Automatic Backups** — Creates timestamped backups of mods before updates or removals, with configurable retention.
- **Dark Theme UI** — Clean, dark-themed PyQt5 interface with tabbed navigation.
- **Cross-platform** — Runs on Windows, macOS, and Linux with platform-appropriate config directories.

## Supported Minecraft Versions

1.8 · 1.8.9 · 1.12 – 1.12.2 · 1.14 – 1.14.4 · 1.15 – 1.15.2 · 1.16 – 1.16.5 · 1.17 – 1.17.1 · 1.18 – 1.18.2 · 1.19 – 1.19.4 · 1.20 – 1.20.4

## Supported Mod Loaders

Forge · Fabric · Quilt · NeoForge

---

## Requirements

- Python 3.8+
- The packages listed in `requirements.txt`:

| Package | Min version |
|---------|-------------|
| PyQt5 | 5.15.0 |
| requests | 2.28.0 |
| aiohttp | 3.8.0 |
| packaging | 21.0 |

---

## Installation

```bash
# 1. Clone the repository
git clone https://github.com/freiamjirehsuberebaltero-ops/freiamjirehsuberebaltero-ops.github.io.git
cd freiamjirehsuberebaltero-ops.github.io

# 2. (Recommended) Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Launch the application
python main.py
```

---

## Configuration

On first launch the application creates a config directory and a `settings.json` file in the platform default location:

| Platform | Path |
|----------|------|
| Windows | `%APPDATA%\MinecraftModManager\config\settings.json` |
| macOS | `~/Library/Application Support/MinecraftModManager/config/settings.json` |
| Linux | `~/.local/share/MinecraftModManager/config/settings.json` |

### Key settings

| Key | Default | Description |
|-----|---------|-------------|
| `curseforge_api_key` | `""` | CurseForge API key (required for CurseForge searches) |
| `preferred_api` | `"modrinth"` | Which API(s) to query: `"modrinth"`, `"curseforge"`, or `"both"` |
| `default_mc_version` | `"1.20.1"` | Pre-selected Minecraft version in the UI |
| `default_mod_loader` | `"Fabric"` | Pre-selected mod loader in the UI |
| `backup_before_update` | `true` | Back up mods before updating/removing |
| `max_backups` | `5` | Number of backup snapshots to retain |
| `download_threads` | `4` | Parallel download workers |
| `theme` | `"dark"` | UI theme (`"dark"` is the only built-in theme) |

Settings can also be changed at runtime from the **⚙ Settings** tab.

---

## Project Structure

```
.
├── main.py                  # Entry point
├── requirements.txt
├── apis/
│   ├── base_api.py          # Abstract base + shared data classes (ModInfo, ModVersion)
│   ├── modrinth_api.py      # Modrinth REST API v2 client
│   └── curseforge_api.py    # CurseForge REST API v1 client
├── config/
│   └── settings.py          # JSON-backed settings store
├── core/
│   ├── mod_manager.py       # Install / update / remove / search / backup logic
│   ├── mod_loader.py        # Detects installed mod JARs
│   ├── profile_manager.py   # Save / load / import / export mod profiles
│   └── minecraft_detector.py# Locates Minecraft installation directories
├── gui/
│   ├── main_window.py       # Top-level QMainWindow + tab layout
│   ├── mod_browser.py       # Mod search & install panel
│   ├── installation_manager.py # Manage installed mods panel
│   ├── profile_manager_gui.py  # Profile CRUD panel
│   └── settings_panel.py    # Settings editor panel
└── utils/
    ├── constants.py         # App-wide constants and default paths
    └── logger.py            # Logging setup
```

---

## Usage

### Browsing & Installing Mods

1. Open the **🔍 Mod Browser** tab.
2. Enter a search term and optionally filter by Minecraft version and mod loader.
3. Select a mod from the results list to view details and available versions.
4. Choose a version and click **Install** to download it to your mods folder.

### Managing Installations

Use the **🎮 Installations** tab to view mods in a directory, remove mods, and check for updates.

### Profiles

Use the **📦 Profiles** tab to:
- Create named profiles that pin a set of mods to a specific game version and loader.
- Export profiles as portable JSON files to share with others.
- Import profiles shared by others.

### CurseForge API Key

CurseForge requires an API key for mod searches. Obtain one from the [CurseForge developer portal](https://console.curseforge.com/) and paste it into the **⚙ Settings** tab (or set `curseforge_api_key` in `settings.json`).

---

## License

This project is provided as-is. See repository for licensing details.
