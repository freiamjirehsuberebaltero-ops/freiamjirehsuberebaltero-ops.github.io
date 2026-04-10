"""CurseForge API integration."""

from typing import Any, Dict, List, Optional

from .base_api import BaseAPI, ModInfo, ModVersion
from utils.constants import (
    CURSEFORGE_BASE_URL,
    CURSEFORGE_MINECRAFT_GAME_ID,
    CURSEFORGE_MODS_CLASS_ID,
)
from utils.logger import get_logger

logger = get_logger("curseforge_api")

_LOADER_IDS: Dict[str, int] = {
    "forge": 1,
    "cauldron": 2,
    "liteloader": 3,
    "fabric": 4,
    "quilt": 5,
    "neoforge": 6,
}


class CurseForgeAPI(BaseAPI):
    """Client for the CurseForge v1 REST API."""

    SOURCE = "curseforge"

    def __init__(self, api_key: str = "") -> None:
        super().__init__(api_key=api_key)

    # ------------------------------------------------------------------
    # BaseAPI implementation
    # ------------------------------------------------------------------

    def _default_headers(self) -> Dict[str, str]:
        headers = super()._default_headers()
        if self.api_key:
            headers["x-api-key"] = self.api_key
        return headers

    def search_mods(
        self,
        query: str,
        game_version: str = "",
        mod_loader: str = "",
        page: int = 0,
        page_size: int = 20,
    ) -> List[ModInfo]:
        if not self.api_key:
            logger.warning("CurseForge API key not configured – skipping search")
            return []

        params: Dict[str, Any] = {
            "gameId": CURSEFORGE_MINECRAFT_GAME_ID,
            "classId": CURSEFORGE_MODS_CLASS_ID,
            "searchFilter": query,
            "index": page * page_size,
            "pageSize": min(page_size, 50),  # CurseForge max is 50
            "sortField": 2,  # 2 = Popularity (downloads), 3 = Last Updated, 0 = Relevance
            "sortOrder": "desc",  # Descending order
        }
        if game_version:
            params["gameVersion"] = game_version
            # Per CurseForge docs: modLoaderType MUST be coupled with gameVersion
            loader_id = _LOADER_IDS.get(mod_loader.lower())
            if loader_id:
                params["modLoaderType"] = loader_id

        # Let exceptions propagate so callers can show proper error messages
        resp = self._get(f"{CURSEFORGE_BASE_URL}/mods/search", params=params)
        data = resp.json()

        results: List[ModInfo] = []
        for mod in data.get("data", []):
            results.append(self._parse_mod(mod))
        return results

    def get_mod_versions(
        self,
        mod_id: str,
        game_version: str = "",
        mod_loader: str = "",
    ) -> List[ModVersion]:
        if not self.api_key:
            return []

        params: Dict[str, Any] = {}
        if game_version:
            params["gameVersion"] = game_version
            # Per docs: modLoaderType must be coupled with gameVersion
            loader_id = _LOADER_IDS.get(mod_loader.lower())
            if loader_id:
                params["modLoaderType"] = loader_id

        try:
            resp = self._get(f"{CURSEFORGE_BASE_URL}/mods/{mod_id}/files", params=params)
            data = resp.json()
        except Exception as exc:
            logger.error("CurseForge get_versions error: %s", exc)
            return []

        versions: List[ModVersion] = []
        for f in data.get("data", []):
            versions.append(self._parse_file(f, mod_id))
        return versions

    def get_mod_info(self, mod_id: str) -> Optional[ModInfo]:
        if not self.api_key:
            return None
        try:
            resp = self._get(f"{CURSEFORGE_BASE_URL}/mods/{mod_id}")
            data = resp.json().get("data", {})
        except Exception as exc:
            logger.error("CurseForge get_mod_info error: %s", exc)
            return None
        return self._parse_mod(data)

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    def _parse_mod(self, data: Dict[str, Any]) -> ModInfo:
        """Parse a mod from CurseForge search or detail response."""
        authors = ", ".join(a.get("name", "") for a in data.get("authors", []))
        latest_files = data.get("latestFilesIndexes", [])
        game_versions = list({f.get("gameVersion", "") for f in latest_files})
        
        # Extract loader names from gameVersions in latest files
        mod_loaders = []
        for f in latest_files:
            for gv in f.get("gameVersions", []):
                if gv in ("Forge", "Fabric", "Quilt", "NeoForge"):
                    mod_loaders.append(gv)
        mod_loaders = list(dict.fromkeys(mod_loaders))  # Remove duplicates while preserving order
        
        slug = data.get("slug", "")
        return ModInfo(
            id=str(data.get("id", "")),
            name=data.get("name", ""),
            slug=slug,
            summary=data.get("summary", ""),
            author=authors,
            downloads=data.get("downloadCount", 0),
            icon_url=(data.get("logo") or {}).get("url", ""),
            source=self.SOURCE,
            game_versions=game_versions,
            mod_loaders=mod_loaders,
            categories=[c.get("name", "") for c in data.get("categories", [])],
            project_url=data.get("links", {}).get("websiteUrl", ""),
        )

    def _parse_file(self, f: Dict[str, Any], mod_id: str) -> ModVersion:
        """Parse a file/version from CurseForge."""
        deps = [
            {
                "mod_id": str(d.get("modId", "")),
                "dependency_type": d.get("relationType", 3),
            }
            for d in f.get("dependencies", [])
        ]
        
        # Extract mod loaders from gameVersions
        mod_loaders = [
            gv for gv in f.get("gameVersions", [])
            if gv in ("Forge", "Fabric", "Quilt", "NeoForge")
        ]
        
        return ModVersion(
            id=str(f.get("id", "")),
            mod_id=str(mod_id),
            name=f.get("displayName", ""),
            version_number=f.get("fileName", ""),
            changelog="",
            download_url=f.get("downloadUrl", ""),
            filename=f.get("fileName", ""),
            game_versions=f.get("gameVersions", []),
            mod_loaders=mod_loaders,
            dependencies=deps,
            date_published=f.get("fileDate", ""),
            source=self.SOURCE,
        )