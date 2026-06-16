import tempfile
import unittest
from pathlib import Path

from core.server_manager import ServerManager


class ServerManagerTests(unittest.TestCase):
    def test_create_server_persists_registry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "servers"
            manager = ServerManager(servers_root=root)
            server = manager.create_server(
                name="Alpha",
                source="manual",
                server_type="modded",
                version="1.20.1",
                loader="Fabric",
            )

            self.assertTrue((root / "servers.json").exists())
            self.assertTrue((Path(server.path) / "server.properties").exists())
            self.assertTrue((Path(server.path) / "eula.txt").exists())
            self.assertEqual(len(manager.list_servers()), 1)

    def test_import_server_folder_requires_server_like_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "servers"
            external = Path(tmp) / "external"
            external.mkdir(parents=True, exist_ok=True)
            (external / "server.properties").write_text("motd=Test\n", encoding="utf-8")

            manager = ServerManager(servers_root=root)
            imported = manager.import_server_folder(external)

            self.assertEqual(imported.name, "external")
            self.assertEqual(Path(imported.path), external.resolve())
            self.assertEqual(len(manager.list_servers()), 1)

    def test_write_config_creates_backup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "servers"
            backup = Path(tmp) / "backup"
            manager = ServerManager(servers_root=root, backup_root=backup)
            server = manager.create_server(
                name="Beta",
                source="manual",
                server_type="vanilla",
                version="1.20.1",
            )

            manager.write_config(server.id, "server.properties", "motd=First\n", create_backup=False)
            manager.write_config(server.id, "server.properties", "motd=Second\n", create_backup=True)

            backups = list((backup / server.id / "configs").glob("**/server.properties"))
            self.assertTrue(backups, "Expected backup file for edited config")
            latest = manager.read_config(server.id, "server.properties")
            self.assertEqual(latest, "motd=Second\n")


if __name__ == "__main__":
    unittest.main()
