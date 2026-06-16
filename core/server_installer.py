"""Download Minecraft server binaries from common distribution APIs."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import requests

from utils.logger import get_logger

logger = get_logger("server_installer")


class ServerInstaller:
    """Resolve and download server binaries for different server sources."""

    def __init__(self, timeout: int = 30) -> None:
        self._timeout = timeout

    def download_server(
        self,
        source: str,
        minecraft_version: str,
        target_dir: Path,
        loader_version: str = "",
    ) -> Path:
        """Download a server jar/installer and return the downloaded file path."""
        source = source.lower().strip()
        target_dir = Path(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        if source == "vanilla":
            url, filename = self._resolve_vanilla(minecraft_version)
        elif source == "paper":
            url, filename = self._resolve_paper(minecraft_version)
        elif source == "purpur":
            url, filename = self._resolve_purpur(minecraft_version)
        elif source == "fabric":
            url, filename = self._resolve_fabric(minecraft_version, loader_version)
        elif source == "forge":
            url, filename = self._resolve_forge(minecraft_version)
        elif source == "neoforge":
            url, filename = self._resolve_neoforge(minecraft_version)
        else:
            raise ValueError(f"Unsupported server source: {source}")

        dest = target_dir / filename
        self._download(url, dest)
        return dest

    def _download(self, url: str, destination: Path) -> None:
        logger.info("Downloading %s -> %s", url, destination)
        with requests.get(url, stream=True, timeout=self._timeout) as resp:
            resp.raise_for_status()
            with open(destination, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=1024 * 64):
                    if chunk:
                        fh.write(chunk)

    def _get_json(self, url: str) -> dict:
        resp = requests.get(url, timeout=self._timeout)
        resp.raise_for_status()
        return resp.json()

    def _resolve_vanilla(self, minecraft_version: str) -> tuple[str, str]:
        manifest = self._get_json(
            "https://launchermeta.mojang.com/mc/game/version_manifest.json"
        )
        version_info = next(
            (v for v in manifest.get("versions", []) if v.get("id") == minecraft_version),
            None,
        )
        if not version_info:
            raise ValueError(f"Vanilla version not found: {minecraft_version}")
        detail = self._get_json(version_info["url"])
        server = detail.get("downloads", {}).get("server", {})
        url = server.get("url")
        if not url:
            raise ValueError(f"No server binary for vanilla {minecraft_version}")
        return url, f"server-vanilla-{minecraft_version}.jar"

    def _resolve_paper(self, minecraft_version: str) -> tuple[str, str]:
        builds_resp = self._get_json(
            f"https://api.papermc.io/v2/projects/paper/versions/{minecraft_version}"
        )
        builds = builds_resp.get("builds", [])
        if not builds:
            raise ValueError(f"No Paper build for {minecraft_version}")
        build = builds[-1]
        filename = f"paper-{minecraft_version}-{build}.jar"
        url = (
            f"https://api.papermc.io/v2/projects/paper/versions/{minecraft_version}/"
            f"builds/{build}/downloads/{filename}"
        )
        return url, filename

    def _resolve_purpur(self, minecraft_version: str) -> tuple[str, str]:
        data = self._get_json(f"https://api.purpurmc.org/v2/purpur/{minecraft_version}")
        build = data.get("builds", {}).get("latest")
        if not build:
            raise ValueError(f"No Purpur build for {minecraft_version}")
        filename = f"purpur-{minecraft_version}-{build}.jar"
        url = (
            f"https://api.purpurmc.org/v2/purpur/{minecraft_version}/{build}/download"
        )
        return url, filename

    def _resolve_fabric(
        self,
        minecraft_version: str,
        loader_version: str,
    ) -> tuple[str, str]:
        loaders = self._get_json("https://meta.fabricmc.net/v2/versions/loader")
        installers = self._get_json("https://meta.fabricmc.net/v2/versions/installer")
        chosen_loader = loader_version or loaders[0]["version"]
        chosen_installer = installers[0]["version"]
        filename = f"fabric-server-{minecraft_version}-{chosen_loader}.jar"
        url = (
            f"https://meta.fabricmc.net/v2/versions/loader/{minecraft_version}/"
            f"{chosen_loader}/{chosen_installer}/server/jar"
        )
        return url, filename

    def _resolve_forge(self, minecraft_version: str) -> tuple[str, str]:
        promotions = self._get_json(
            "https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json"
        )
        promos = promotions.get("promos", {})
        key_latest = f"{minecraft_version}-latest"
        key_recommended = f"{minecraft_version}-recommended"
        forge_version = promos.get(key_recommended) or promos.get(key_latest)
        if not forge_version:
            raise ValueError(f"No Forge build found for {minecraft_version}")
        full = f"{minecraft_version}-{forge_version}"
        filename = f"forge-{full}-installer.jar"
        url = (
            "https://maven.minecraftforge.net/net/minecraftforge/forge/"
            f"{full}/{filename}"
        )
        return url, filename

    def _resolve_neoforge(self, minecraft_version: str) -> tuple[str, str]:
        metadata_url = (
            "https://maven.neoforged.net/releases/net/neoforged/neoforge/maven-metadata.xml"
        )
        resp = requests.get(metadata_url, timeout=self._timeout)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
        versions = [v.text for v in root.findall("./versioning/versions/version") if v.text]
        if not versions:
            raise ValueError("No NeoForge versions available")

        prefix = self._build_neoforge_version_prefix(minecraft_version)
        compatible = [v for v in versions if v.startswith(prefix)] or versions
        selected = compatible[-1]
        filename = f"neoforge-{selected}-installer.jar"
        url = (
            "https://maven.neoforged.net/releases/net/neoforged/neoforge/"
            f"{selected}/{filename}"
        )
        return url, filename

    @staticmethod
    def _build_neoforge_version_prefix(minecraft_version: str) -> str:
        """Map MC version to NeoForge artifact prefix (e.g. 1.20.x -> 20.)."""
        parts = minecraft_version.split(".")
        if len(parts) < 2 or not all(p.isdigit() for p in parts[:2]):
            raise ValueError(
                f"Unsupported Minecraft version format for NeoForge: {minecraft_version}"
            )
        major_minor = ".".join(parts[:2])
        if major_minor.startswith("1."):
            return major_minor[2:] + "."
        return f"{major_minor}."
