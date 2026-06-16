"""Server instance management, persistence, process lifecycle, and config editing."""

from __future__ import annotations

import json
import shlex
import shutil
import subprocess
import threading
from collections import deque
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from core.server_installer import ServerInstaller
from utils.logger import get_logger

logger = get_logger("server_manager")


@dataclass
class ServerInstance:
    id: str
    name: str
    path: str
    server_type: str
    version: str
    loader: str
    source: str
    java_args: str = ""
    status: str = "stopped"
    pid: int = 0
    last_error: str = ""
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        now = datetime.now().isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ServerInstance":
        return cls(**payload)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ServerManager:
    """Manage server registry and running server processes."""

    def __init__(self, servers_root: Path, backup_root: Optional[Path] = None) -> None:
        self._servers_root = Path(servers_root)
        self._servers_root.mkdir(parents=True, exist_ok=True)
        self._registry_file = self._servers_root / "servers.json"
        self._backup_root = (Path(backup_root) if backup_root else self._servers_root / "backups")
        self._backup_root.mkdir(parents=True, exist_ok=True)
        self._installer = ServerInstaller()
        self._servers: Dict[str, ServerInstance] = {}
        self._processes: Dict[str, subprocess.Popen] = {}
        self._logs: Dict[str, deque[str]] = {}
        self._load_registry()

    def list_servers(self) -> List[ServerInstance]:
        self._refresh_statuses()
        return sorted(self._servers.values(), key=lambda s: s.name.lower())

    def get_server(self, server_id: str) -> Optional[ServerInstance]:
        self._refresh_statuses()
        return self._servers.get(server_id)

    def create_server(
        self,
        name: str,
        source: str,
        server_type: str,
        version: str,
        loader: str = "",
        java_args: str = "",
    ) -> ServerInstance:
        safe_folder = self._safe_name(name)
        path = self._servers_root / safe_folder
        path.mkdir(parents=True, exist_ok=True)
        self._ensure_bootstrap(path)
        server = ServerInstance(
            id=uuid4().hex,
            name=name,
            path=str(path),
            server_type=server_type,
            version=version,
            loader=loader,
            source=source,
            java_args=java_args,
        )
        self._servers[server.id] = server
        self._save_registry()
        return server

    def import_server_folder(
        self,
        folder: Path,
        name: Optional[str] = None,
        server_type: str = "manual",
        version: str = "",
        loader: str = "",
    ) -> ServerInstance:
        folder = Path(folder).resolve()
        if not folder.exists() or not folder.is_dir():
            raise ValueError("Selected folder does not exist or is not a directory")
        if not self._looks_like_server_folder(folder):
            raise ValueError("Folder does not look like a Minecraft server directory")

        display_name = name or folder.name
        server = ServerInstance(
            id=uuid4().hex,
            name=display_name,
            path=str(folder),
            server_type=server_type,
            version=version,
            loader=loader,
            source="manual",
        )
        self._servers[server.id] = server
        self._save_registry()
        return server

    def install_server_binary(
        self,
        server_id: str,
        source: str,
        minecraft_version: str,
        loader_version: str = "",
    ) -> Path:
        server = self._require_server(server_id)
        target = Path(server.path)
        downloaded = self._installer.download_server(
            source=source,
            minecraft_version=minecraft_version,
            target_dir=target,
            loader_version=loader_version,
        )
        server.updated_at = datetime.now().isoformat()
        self._save_registry()
        return downloaded

    def start_server(
        self,
        server_id: str,
        java_path: str = "java",
        memory_mb: int = 2048,
    ) -> bool:
        server = self._require_server(server_id)
        if server.status == "running":
            return True

        server_dir = Path(server.path)
        jar = self._resolve_server_jar(server_dir)
        if not jar:
            server.last_error = "No server jar found in folder."
            self._save_registry()
            return False

        cmd = [
            java_path or "java",
            f"-Xms{memory_mb}M",
            f"-Xmx{memory_mb}M",
            *shlex.split(server.java_args or ""),
            "-jar",
            jar.name,
            "nogui",
        ]
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(server_dir),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            server.last_error = str(exc)
            server.status = "error"
            self._save_registry()
            return False

        self._processes[server.id] = proc
        self._logs.setdefault(server.id, deque(maxlen=1000))
        self._start_log_reader(server.id, proc)
        server.status = "running"
        server.pid = proc.pid or 0
        server.last_error = ""
        server.updated_at = datetime.now().isoformat()
        self._save_registry()
        return True

    def stop_server(self, server_id: str, timeout: int = 10) -> bool:
        server = self._require_server(server_id)
        proc = self._processes.get(server.id)
        if not proc:
            server.status = "stopped"
            server.pid = 0
            self._save_registry()
            return True

        try:
            if proc.stdin:
                proc.stdin.write("stop\n")
                proc.stdin.flush()
            proc.wait(timeout=timeout)
        except Exception:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except Exception:
                proc.kill()

        self._processes.pop(server.id, None)
        server.status = "stopped"
        server.pid = 0
        server.updated_at = datetime.now().isoformat()
        self._save_registry()
        return True

    def restart_server(
        self,
        server_id: str,
        java_path: str = "java",
        memory_mb: int = 2048,
    ) -> bool:
        self.stop_server(server_id)
        return self.start_server(server_id, java_path=java_path, memory_mb=memory_mb)

    def get_console_output(self, server_id: str, lines: int = 300) -> str:
        buffer = self._logs.get(server_id, deque())
        return "\n".join(list(buffer)[-lines:])

    def get_mods_dir(self, server_id: str) -> Path:
        server = self._require_server(server_id)
        mods_dir = Path(server.path) / "mods"
        mods_dir.mkdir(parents=True, exist_ok=True)
        return mods_dir

    def health_check(self, server_id: str, java_path: str = "java") -> Dict[str, Any]:
        server = self._require_server(server_id)
        folder = Path(server.path)
        jar = self._resolve_server_jar(folder)
        return {
            "path_exists": folder.exists(),
            "jar_found": bool(jar),
            "java_path": java_path,
            "status": server.status,
            "last_error": server.last_error,
        }

    def list_config_files(self, server_id: str) -> List[str]:
        server = self._require_server(server_id)
        root = Path(server.path)
        common = [
            "server.properties",
            "eula.txt",
            "whitelist.json",
            "ops.json",
            "banned-ips.json",
            "banned-players.json",
        ]
        out: List[str] = []
        for rel in common:
            if (root / rel).exists():
                out.append(rel)

        config_dir = root / "config"
        if config_dir.is_dir():
            for ext in ("*.json", "*.toml", "*.yml", "*.yaml", "*.cfg", "*.properties"):
                for entry in sorted(config_dir.glob(ext)):
                    out.append(str(entry.relative_to(root)))
        return sorted(set(out))

    def read_config(self, server_id: str, relative_path: str) -> str:
        server = self._require_server(server_id)
        file_path = self._safe_server_file(Path(server.path), relative_path)
        with open(file_path, "r", encoding="utf-8") as fh:
            return fh.read()

    def write_config(
        self,
        server_id: str,
        relative_path: str,
        content: str,
        create_backup: bool = True,
    ) -> None:
        server = self._require_server(server_id)
        file_path = self._safe_server_file(Path(server.path), relative_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        if create_backup and file_path.exists():
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = (
                self._backup_root
                / server.id
                / "configs"
                / stamp
                / relative_path.replace("/", "_")
            )
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_path, backup_path)
        with open(file_path, "w", encoding="utf-8") as fh:
            fh.write(content)
        server.updated_at = datetime.now().isoformat()
        self._save_registry()

    def _refresh_statuses(self) -> None:
        for server_id, server in self._servers.items():
            proc = self._processes.get(server_id)
            if not proc:
                continue
            if proc.poll() is not None:
                server.status = "stopped"
                server.pid = 0
                self._processes.pop(server_id, None)
                server.updated_at = datetime.now().isoformat()
        self._save_registry()

    def _safe_server_file(self, root: Path, relative_path: str) -> Path:
        candidate = (root / relative_path).resolve()
        if not str(candidate).startswith(str(root.resolve())):
            raise ValueError("Invalid config path")
        return candidate

    def _start_log_reader(self, server_id: str, process: subprocess.Popen) -> None:
        def _reader() -> None:
            stream = process.stdout
            if not stream:
                return
            for line in stream:
                clean = line.rstrip("\n")
                self._logs.setdefault(server_id, deque(maxlen=1000)).append(clean)

        t = threading.Thread(target=_reader, daemon=True)
        t.start()

    def _load_registry(self) -> None:
        if not self._registry_file.exists():
            return
        try:
            with open(self._registry_file, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
            self._servers = {
                item["id"]: ServerInstance.from_dict(item)
                for item in payload.get("servers", [])
            }
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.error("Failed to load server registry: %s", exc)
            self._servers = {}

    def _save_registry(self) -> None:
        payload = {"servers": [s.to_dict() for s in self._servers.values()]}
        with open(self._registry_file, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)

    def _ensure_bootstrap(self, server_dir: Path) -> None:
        eula = server_dir / "eula.txt"
        if not eula.exists():
            eula.write_text("eula=true\n", encoding="utf-8")
        props = server_dir / "server.properties"
        if not props.exists():
            props.write_text("motd=Managed by Minecraft Mod Manager\n", encoding="utf-8")
        (server_dir / "mods").mkdir(parents=True, exist_ok=True)

    def _resolve_server_jar(self, server_dir: Path) -> Optional[Path]:
        preferred = server_dir / "server.jar"
        if preferred.exists():
            return preferred
        jars = sorted(server_dir.glob("*.jar"))
        return jars[0] if jars else None

    def _require_server(self, server_id: str) -> ServerInstance:
        server = self._servers.get(server_id)
        if not server:
            raise ValueError(f"Server not found: {server_id}")
        return server

    def _looks_like_server_folder(self, folder: Path) -> bool:
        checks = [
            folder / "server.properties",
            folder / "eula.txt",
            folder / "mods",
        ]
        if any(c.exists() for c in checks):
            return True
        return any(folder.glob("*.jar"))

    @staticmethod
    def _safe_name(name: str) -> str:
        return "".join(c if c.isalnum() or c in "._-" else "_" for c in name).strip("._") or uuid4().hex[:8]
