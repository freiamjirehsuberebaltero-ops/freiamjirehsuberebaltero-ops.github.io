"""Base API class for mod platform integrations."""

import threading
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import requests

from utils.constants import REQUEST_TIMEOUT
from utils.logger import get_logger

logger = get_logger("base_api")


class ModInfo:
    """Lightweight data class representing a single mod."""

    __slots__ = (
        "id", "name", "slug", "summary", "author",
        "downloads", "icon_url", "source",
        "latest_version", "game_versions", "mod_loaders",
        "categories", "project_url",
    )

    def __init__(
        self,
        id: str,
        name: str,
        slug: str,
        summary: str = "",
        author: str = "",
        downloads: int = 0,
        icon_url: str = "",
        source: str = "",
        latest_version: str = "",
        game_versions: Optional[List[str]] = None,
        mod_loaders: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
        project_url: str = "",
    ) -> None:
        self.id = id
        self.name = name
        self.slug = slug
        self.summary = summary
        self.author = author
        self.downloads = downloads
        self.icon_url = icon_url
        self.source = source
        self.latest_version = latest_version
        self.game_versions = game_versions or []
        self.mod_loaders = mod_loaders or []
        self.categories = categories or []
        self.project_url = project_url

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ModInfo {self.source}/{self.name}>"


class ModVersion:
    """Represents a specific release of a mod."""

    __slots__ = (
        "id", "mod_id", "name", "version_number",
        "changelog", "download_url", "filename",
        "game_versions", "mod_loaders", "dependencies",
        "date_published", "source",
    )

    def __init__(
        self,
        id: str,
        mod_id: str,
        name: str,
        version_number: str,
        changelog: str = "",
        download_url: str = "",
        filename: str = "",
        game_versions: Optional[List[str]] = None,
        mod_loaders: Optional[List[str]] = None,
        dependencies: Optional[List[Dict[str, Any]]] = None,
        date_published: str = "",
        source: str = "",
    ) -> None:
        self.id = id
        self.mod_id = mod_id
        self.name = name
        self.version_number = version_number
        self.changelog = changelog
        self.download_url = download_url
        self.filename = filename
        self.game_versions = game_versions or []
        self.mod_loaders = mod_loaders or []
        self.dependencies = dependencies or []
        self.date_published = date_published
        self.source = source

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ModVersion {self.version_number}>"


class BaseAPI(ABC):
    """Abstract base for CurseForge and Modrinth API clients."""

    def __init__(self, api_key: str = "") -> None:
        self.api_key = api_key
        self._session: Optional[requests.Session] = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def _get_session(self) -> requests.Session:
        with self._lock:
            if self._session is None:
                self._session = requests.Session()
                self._session.headers.update(self._default_headers())
            return self._session

    def close(self) -> None:
        with self._lock:
            if self._session:
                self._session.close()
                self._session = None

    def _default_headers(self) -> Dict[str, str]:
        return {
            "User-Agent": "MinecraftModManager/1.0 (github.com/minecraft-mod-manager)",
            "Accept": "application/json",
        }

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _get(self, url: str, **kwargs: Any) -> requests.Response:
        session = self._get_session()
        kwargs.setdefault("timeout", REQUEST_TIMEOUT)
        try:
            response = session.get(url, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            logger.error("GET %s failed: %s", url, exc)
            raise

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    def search_mods(
        self,
        query: str,
        game_version: str = "",
        mod_loader: str = "",
        page: int = 0,
        page_size: int = 20,
    ) -> List[ModInfo]:
        """Search for mods and return a list of ModInfo objects."""

    @abstractmethod
    def get_mod_versions(
        self,
        mod_id: str,
        game_version: str = "",
        mod_loader: str = "",
    ) -> List[ModVersion]:
        """Retrieve available versions for a given mod."""

    @abstractmethod
    def get_mod_info(self, mod_id: str) -> Optional[ModInfo]:
        """Fetch detailed metadata for a specific mod."""

    def download_file(
        self,
        url: str,
        dest_path: str,
        progress_callback: Optional[Any] = None,
    ) -> bool:
        """Download a file from *url* to *dest_path*.

        *progress_callback* is called with ``(bytes_downloaded, total_bytes)``
        whenever a chunk arrives.  Returns ``True`` on success.
        """
        import os

        try:
            response = self._get_session().get(url, stream=True, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            total = int(response.headers.get("content-length", 0))
            downloaded = 0
            os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
            with open(dest_path, "wb") as fh:
                for chunk in response.iter_content(chunk_size=65536):
                    if chunk:
                        fh.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback:
                            progress_callback(downloaded, total)
            logger.info("Downloaded %s -> %s", url, dest_path)
            return True
        except (requests.RequestException, OSError) as exc:
            logger.error("Download failed (%s): %s", url, exc)
            return False
