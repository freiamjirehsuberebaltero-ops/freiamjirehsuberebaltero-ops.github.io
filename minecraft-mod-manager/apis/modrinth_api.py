"""Modrinth API integration."""

from typing import Any, Dict, List, Optional

from .base_api import BaseAPI, ModInfo, ModVersion
from utils.constants import MODRINTH_BASE_URL
from utils.logger import get_logger

logger = get_logger("modrinth_api")


class ModrinthAPI(BaseAPI):
    """Client for the Modrinth public REST API (v2)."""

    SOURCE = "modrinth"

    def __init__(self) -> None:
        # Modrinth does not require an API key for read operations
        super().__init__()

    # ------------------------------------------------------------------
    # BaseAPI implementation
    # ------------------------------------------------------------------

    def search_mods(
        self,
        query: str,
        game_version: str = "",
        mod_loader: str = "",
        page: int = 0,
        page_size: int = 20,
    ) -> List[ModInfo]:
        facets: List[List[str]] = [["project_type:mod"]]
        if game_version:
            facets.append([f"versions:{game_version}"])
        if mod_loader:
            facets.append([f"categories:{mod_loader.lower()}"])

        import json as _json

        params: Dict[str, Any] = {
            "query": query,
            "facets": _json.dumps(facets),
            "offset": page * page_size,
            "limit": page_size,
        }

        try:
            resp = self._get(f"{MODRINTH_BASE_URL}/search", params=params)
            data = resp.json()
        except Exception as exc:
            logger.error("Modrinth search error: %s", exc)
            return []

        results: List[ModInfo] = []
        for hit in data.get("hits", []):
            results.append(self._parse_search_hit(hit))
        return results

    def get_mod_versions(
        self,
        mod_id: str,
        game_version: str = "",
        mod_loader: str = "",
    ) -> List[ModVersion]:
        params: Dict[str, Any] = {}
        if game_version:
            params["game_versions"] = f'["{game_version}"]'
        if mod_loader:
            params["loaders"] = f'["{mod_loader.lower()}"]'

        try:
            resp = self._get(
                f"{MODRINTH_BASE_URL}/project/{mod_id}/version",
                params=params,
            )
            versions_data = resp.json()
        except Exception as exc:
            logger.error("Modrinth get_versions error: %s", exc)
            return []

        versions: List[ModVersion] = []
        for v in versions_data:
            versions.append(self._parse_version(v, mod_id))
        return versions

    def get_mod_info(self, mod_id: str) -> Optional[ModInfo]:
        try:
            resp = self._get(f"{MODRINTH_BASE_URL}/project/{mod_id}")
            data = resp.json()
        except Exception as exc:
            logger.error("Modrinth get_mod_info error: %s", exc)
            return None
        return self._parse_project(data)

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    def _parse_search_hit(self, hit: Dict[str, Any]) -> ModInfo:
        return ModInfo(
            id=hit.get("project_id", ""),
            name=hit.get("title", ""),
            slug=hit.get("slug", ""),
            summary=hit.get("description", ""),
            author=hit.get("author", ""),
            downloads=hit.get("downloads", 0),
            icon_url=hit.get("icon_url", ""),
            source=self.SOURCE,
            latest_version=hit.get("latest_version", ""),
            game_versions=hit.get("versions", []),
            mod_loaders=hit.get("categories", []),
            categories=hit.get("categories", []),
            project_url=f"https://modrinth.com/mod/{hit.get('slug', '')}",
        )

    def _parse_project(self, data: Dict[str, Any]) -> ModInfo:
        return ModInfo(
            id=data.get("id", ""),
            name=data.get("title", ""),
            slug=data.get("slug", ""),
            summary=data.get("description", ""),
            author=data.get("team", ""),
            downloads=data.get("downloads", 0),
            icon_url=data.get("icon_url", ""),
            source=self.SOURCE,
            game_versions=data.get("game_versions", []),
            mod_loaders=data.get("loaders", []),
            categories=data.get("categories", []),
            project_url=f"https://modrinth.com/mod/{data.get('slug', '')}",
        )

    def _parse_version(self, v: Dict[str, Any], mod_id: str) -> ModVersion:
        files = v.get("files", [])
        primary = next((f for f in files if f.get("primary")), files[0] if files else {})
        deps = [
            {
                "mod_id": d.get("project_id", ""),
                "version_id": d.get("version_id", ""),
                "dependency_type": d.get("dependency_type", "required"),
            }
            for d in v.get("dependencies", [])
        ]
        return ModVersion(
            id=v.get("id", ""),
            mod_id=mod_id,
            name=v.get("name", ""),
            version_number=v.get("version_number", ""),
            changelog=v.get("changelog", ""),
            download_url=primary.get("url", ""),
            filename=primary.get("filename", ""),
            game_versions=v.get("game_versions", []),
            mod_loaders=v.get("loaders", []),
            dependencies=deps,
            date_published=v.get("date_published", ""),
            source=self.SOURCE,
        )
