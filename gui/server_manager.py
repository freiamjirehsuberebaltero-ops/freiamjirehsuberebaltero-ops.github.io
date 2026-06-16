"""Server management tab for multi-server workflows."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QUrl
from PyQt5.QtGui import QTextCursor, QDesktopServices
from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config.settings import Settings
from core.server_manager import ServerInstance, ServerManager
from utils.constants import MC_VERSIONS, MOD_LOADERS
from utils.logger import get_logger

logger = get_logger("server_manager_panel")


class ServerManagerPanel(QWidget):
    """Create/import/start/stop servers and edit server configs."""

    mods_dir_selected = pyqtSignal(str)

    def __init__(self, manager: ServerManager, settings: Settings, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._manager = manager
        self._settings = settings
        self._servers: List[ServerInstance] = []
        self._current_id: str = ""
        self._build_ui()
        self._refresh_servers()

        self._timer = QTimer(self)
        self._timer.setInterval(1200)
        self._timer.timeout.connect(self._refresh_console)
        self._timer.start()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        top = QHBoxLayout()
        self._create_btn = QPushButton("Create Server")
        self._create_btn.clicked.connect(self._create_server)
        self._import_btn = QPushButton("Import Folder")
        self._import_btn.clicked.connect(self._import_server)
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.clicked.connect(self._refresh_servers)
        top.addWidget(self._create_btn)
        top.addWidget(self._import_btn)
        top.addWidget(self._refresh_btn)
        top.addStretch()
        root.addLayout(top)

        splitter = QSplitter(Qt.Horizontal)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("Registered Servers"))
        self._server_list = QListWidget()
        self._server_list.currentRowChanged.connect(self._on_selected)
        left_layout.addWidget(self._server_list)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)

        details = QGroupBox("Details")
        details_layout = QGridLayout(details)
        self._name_label = QLabel("-")
        self._path_label = QLabel("-")
        self._path_label.setWordWrap(True)
        self._status_label = QLabel("-")
        self._version_label = QLabel("-")
        self._loader_label = QLabel("-")
        details_layout.addWidget(QLabel("Name:"), 0, 0)
        details_layout.addWidget(self._name_label, 0, 1)
        details_layout.addWidget(QLabel("Path:"), 1, 0)
        details_layout.addWidget(self._path_label, 1, 1)
        details_layout.addWidget(QLabel("Status:"), 2, 0)
        details_layout.addWidget(self._status_label, 2, 1)
        details_layout.addWidget(QLabel("Version:"), 3, 0)
        details_layout.addWidget(self._version_label, 3, 1)
        details_layout.addWidget(QLabel("Loader:"), 4, 0)
        details_layout.addWidget(self._loader_label, 4, 1)
        right_layout.addWidget(details)

        action_row = QHBoxLayout()
        self._start_btn = QPushButton("Start")
        self._start_btn.clicked.connect(self._start_server)
        self._stop_btn = QPushButton("Stop")
        self._stop_btn.clicked.connect(self._stop_server)
        self._restart_btn = QPushButton("Restart")
        self._restart_btn.clicked.connect(self._restart_server)
        self._open_btn = QPushButton("Open Folder")
        self._open_btn.clicked.connect(self._open_folder)
        self._select_mods_btn = QPushButton("Use For Mod Installs")
        self._select_mods_btn.clicked.connect(self._emit_mods_dir)
        action_row.addWidget(self._start_btn)
        action_row.addWidget(self._stop_btn)
        action_row.addWidget(self._restart_btn)
        action_row.addWidget(self._open_btn)
        action_row.addWidget(self._select_mods_btn)
        action_row.addStretch()
        right_layout.addLayout(action_row)

        config_group = QGroupBox("Config Editor")
        config_layout = QVBoxLayout(config_group)
        config_top = QHBoxLayout()
        self._config_combo = QComboBox()
        self._config_combo.currentTextChanged.connect(self._load_config)
        self._save_config_btn = QPushButton("Save Config")
        self._save_config_btn.clicked.connect(self._save_config)
        config_top.addWidget(QLabel("File:"))
        config_top.addWidget(self._config_combo, 1)
        config_top.addWidget(self._save_config_btn)
        config_layout.addLayout(config_top)
        self._config_text = QTextEdit()
        config_layout.addWidget(self._config_text)
        right_layout.addWidget(config_group)

        console_group = QGroupBox("Console")
        console_layout = QVBoxLayout(console_group)
        self._console_text = QTextEdit()
        self._console_text.setReadOnly(True)
        console_layout.addWidget(self._console_text)
        right_layout.addWidget(console_group)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        root.addWidget(splitter)

        self._status = QLabel("Ready.")
        root.addWidget(self._status)

    def _refresh_servers(self) -> None:
        self._servers = self._manager.list_servers()
        self._server_list.clear()
        for s in self._servers:
            text = f"{s.name} [{s.status}]"
            item = QListWidgetItem(text)
            item.setToolTip(s.path)
            self._server_list.addItem(item)
        if self._servers and not self._current_id:
            self._server_list.setCurrentRow(0)
        self._status.setText(f"Loaded {len(self._servers)} server(s).")

    def _on_selected(self, row: int) -> None:
        if row < 0 or row >= len(self._servers):
            self._current_id = ""
            return
        server = self._servers[row]
        self._current_id = server.id
        self._name_label.setText(server.name)
        self._path_label.setText(server.path)
        self._status_label.setText(server.status)
        self._version_label.setText(server.version or "-")
        self._loader_label.setText(server.loader or "-")
        self._load_config_list()
        self._refresh_console()

    def _create_server(self) -> None:
        dialog = CreateServerDialog(parent=self)
        if dialog.exec_() != QDialog.Accepted:
            return
        payload = dialog.payload()
        try:
            server = self._manager.create_server(
                name=payload["name"],
                source=payload["source"],
                server_type=payload["server_type"],
                version=payload["version"],
                loader=payload["loader"],
                java_args=payload["java_args"],
            )
            try:
                downloaded = self._manager.install_server_binary(
                    server.id,
                    source=payload["source"],
                    minecraft_version=payload["version"],
                )
                self._status.setText(f"Downloaded {downloaded.name}")
            except Exception as install_exc:
                self._status.setText(f"Server created, install failed: {install_exc}")
        except Exception as exc:
            QMessageBox.critical(self, "Create Server", str(exc))
        self._refresh_servers()

    def _import_server(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Existing Server Folder")
        if not folder:
            return
        name = Path(folder).name
        try:
            self._manager.import_server_folder(folder=Path(folder), name=name)
            self._status.setText(f"Imported server: {name}")
            self._refresh_servers()
        except Exception as exc:
            QMessageBox.warning(self, "Import Server", str(exc))

    def _start_server(self) -> None:
        if not self._current_id:
            return
        java_path = self._settings.get("java_path", "java")
        memory_mb = int(self._settings.get("default_server_memory_mb", 2048))
        ok = self._manager.start_server(self._current_id, java_path=java_path, memory_mb=memory_mb)
        self._status.setText("Server started." if ok else "Failed to start server.")
        self._refresh_servers()

    def _stop_server(self) -> None:
        if not self._current_id:
            return
        self._manager.stop_server(self._current_id)
        self._status.setText("Server stopped.")
        self._refresh_servers()

    def _restart_server(self) -> None:
        if not self._current_id:
            return
        java_path = self._settings.get("java_path", "java")
        memory_mb = int(self._settings.get("default_server_memory_mb", 2048))
        ok = self._manager.restart_server(self._current_id, java_path=java_path, memory_mb=memory_mb)
        self._status.setText("Server restarted." if ok else "Failed to restart server.")
        self._refresh_servers()

    def _open_folder(self) -> None:
        if not self._current_id:
            return
        server = self._manager.get_server(self._current_id)
        if not server:
            return
        folder = Path(server.path)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _emit_mods_dir(self) -> None:
        if not self._current_id:
            return
        mods_dir = self._manager.get_mods_dir(self._current_id)
        self.mods_dir_selected.emit(str(mods_dir))
        self._status.setText(f"Mod installs now target: {mods_dir}")

    def _refresh_console(self) -> None:
        if not self._current_id:
            return
        text = self._manager.get_console_output(self._current_id)
        self._console_text.setPlainText(text)
        self._console_text.moveCursor(QTextCursor.End)
        server = self._manager.get_server(self._current_id)
        if server:
            self._status_label.setText(server.status)

    def _load_config_list(self) -> None:
        self._config_combo.clear()
        if not self._current_id:
            return
        files = self._manager.list_config_files(self._current_id)
        self._config_combo.addItems(files)
        if files:
            self._load_config(files[0])

    def _load_config(self, relative_path: str) -> None:
        if not self._current_id or not relative_path:
            self._config_text.clear()
            return
        try:
            content = self._manager.read_config(self._current_id, relative_path)
            self._config_text.setPlainText(content)
        except Exception as exc:
            self._config_text.setPlainText("")
            self._status.setText(f"Failed to read config: {exc}")

    def _save_config(self) -> None:
        if not self._current_id:
            return
        relative_path = self._config_combo.currentText().strip()
        if not relative_path:
            QMessageBox.information(self, "Config", "No config file selected.")
            return
        content = self._config_text.toPlainText()
        try:
            self._manager.write_config(
                self._current_id,
                relative_path=relative_path,
                content=content,
                create_backup=bool(self._settings.get("server_auto_backup", True)),
            )
            self._status.setText(f"Saved {relative_path}")
        except Exception as exc:
            QMessageBox.critical(self, "Save Config", str(exc))


class CreateServerDialog(QDialog):
    """Simple inline create-server form dialog."""

    SOURCES = ["vanilla", "paper", "purpur", "fabric", "forge", "neoforge"]

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Create Server")
        self.setMinimumWidth(420)
        root = QVBoxLayout(self)
        form = QWidget(self)
        layout = QGridLayout(form)
        self._name = QLineEdit("My Server")
        self._source = QComboBox()
        self._source.addItems(self.SOURCES)
        self._type = QComboBox()
        self._type.addItems(["vanilla", "modded"])
        self._version = QComboBox()
        self._version.addItems(MC_VERSIONS)
        self._loader = QComboBox()
        self._loader.addItem("")
        self._loader.addItems(MOD_LOADERS)
        self._java_args = QLineEdit("")
        layout.addWidget(QLabel("Name"), 0, 0)
        layout.addWidget(self._name, 0, 1)
        layout.addWidget(QLabel("Source"), 1, 0)
        layout.addWidget(self._source, 1, 1)
        layout.addWidget(QLabel("Type"), 2, 0)
        layout.addWidget(self._type, 2, 1)
        layout.addWidget(QLabel("Minecraft Version"), 3, 0)
        layout.addWidget(self._version, 3, 1)
        layout.addWidget(QLabel("Loader"), 4, 0)
        layout.addWidget(self._loader, 4, 1)
        layout.addWidget(QLabel("Extra Java Args"), 5, 0)
        layout.addWidget(self._java_args, 5, 1)
        root.addWidget(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def payload(self) -> dict:
        return {
            "name": self._name.text().strip() or "Server",
            "source": self._source.currentText(),
            "server_type": self._type.currentText(),
            "version": self._version.currentText(),
            "loader": self._loader.currentText(),
            "java_args": self._java_args.text().strip(),
        }
