"""Mod browser tab – search, filter, and install mods."""

import threading
from typing import List, Optional

from PyQt5.QtCore import Qt, QThread, pyqtSignal, QObject
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QComboBox,
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
    QProgressBar,
)

from apis.base_api import ModInfo, ModVersion
from core.mod_manager import ModManager
from config.settings import Settings
from utils.constants import MC_VERSIONS, MOD_LOADERS
from utils.logger import get_logger

logger = get_logger("mod_browser")


# ---------------------------------------------------------------------------
# Worker threads
# ---------------------------------------------------------------------------

class SearchWorker(QObject):
    results_ready = pyqtSignal(list)
    error = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, manager: ModManager, query: str, mc_ver: str, loader: str, source: str) -> None:
        super().__init__()
        self._manager = manager
        self._query = query
        self._mc_ver = mc_ver
        self._loader = loader
        self._source = source

    def run(self) -> None:
        try:
            results = self._manager.search(
                self._query, self._mc_ver, self._loader, self._source
            )
            self.results_ready.emit(results)
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.finished.emit()


class VersionWorker(QObject):
    versions_ready = pyqtSignal(list)
    finished = pyqtSignal()

    def __init__(self, manager: ModManager, mod: ModInfo, mc_ver: str, loader: str) -> None:
        super().__init__()
        self._manager = manager
        self._mod = mod
        self._mc_ver = mc_ver
        self._loader = loader

    def run(self) -> None:
        versions = self._manager.get_versions(self._mod, self._mc_ver, self._loader)
        self.versions_ready.emit(versions)
        self.finished.emit()


class InstallWorker(QObject):
    progress = pyqtSignal(int, int)
    finished = pyqtSignal(bool, str)

    def __init__(self, manager: ModManager, version: ModVersion, mods_dir: str) -> None:
        super().__init__()
        self._manager = manager
        self._version = version
        self._mods_dir = mods_dir

    def run(self) -> None:
        from pathlib import Path
        ok = self._manager.install_mod(
            self._version,
            Path(self._mods_dir),
            progress_callback=lambda d, t: self.progress.emit(d, t),
        )
        msg = f"Installed {self._version.filename}" if ok else "Installation failed"
        self.finished.emit(ok, msg)


# ---------------------------------------------------------------------------
# Mod browser widget
# ---------------------------------------------------------------------------

class ModBrowserPanel(QWidget):
    """Search and install mods from CurseForge / Modrinth."""

    def __init__(
        self,
        manager: ModManager,
        settings: Settings,
        mods_dir: str = "",
        parent: QWidget = None,
    ) -> None:
        super().__init__(parent)
        self._manager = manager
        self._settings = settings
        self._mods_dir = mods_dir
        self._current_mod: Optional[ModInfo] = None
        self._versions: List[ModVersion] = []
        self._search_results: List[ModInfo] = []
        self._threads: List[QThread] = []
        self._workers: List[object] = []  # keep strong refs to prevent GC
        self._build_ui()

    # ------------------------------------------------------------------
    # Build UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # Search bar
        search_row = QHBoxLayout()
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Search mods…")
        self._search_edit.returnPressed.connect(self._do_search)

        self._mc_combo = QComboBox()
        self._mc_combo.addItem("Any version")
        self._mc_combo.addItems(MC_VERSIONS)
        self._mc_combo.setCurrentText(
            self._settings.get("default_mc_version", MC_VERSIONS[0])
        )

        self._loader_combo = QComboBox()
        self._loader_combo.addItem("Any loader")
        self._loader_combo.addItems(MOD_LOADERS)
        self._loader_combo.setCurrentText(
            self._settings.get("default_mod_loader", "Fabric")
        )

        self._source_combo = QComboBox()
        self._source_combo.addItems(["both", "modrinth", "curseforge"])
        self._source_combo.setCurrentText(self._settings.get("preferred_api", "both"))

        self._search_btn = QPushButton("Search")
        self._search_btn.clicked.connect(self._do_search)

        search_row.addWidget(self._search_edit, 4)
        search_row.addWidget(self._mc_combo, 2)
        search_row.addWidget(self._loader_combo, 2)
        search_row.addWidget(self._source_combo, 1)
        search_row.addWidget(self._search_btn)
        root.addLayout(search_row)

        # Progress
        self._progress_bar = QProgressBar()
        self._progress_bar.setVisible(False)
        self._progress_bar.setTextVisible(True)
        root.addWidget(self._progress_bar)

        # Splitter: results list | details
        splitter = QSplitter(Qt.Horizontal)

        # Left: results
        left = QWidget()
        left_vbox = QVBoxLayout(left)
        left_vbox.setContentsMargins(0, 0, 0, 0)
        self._results_list = QListWidget()
        self._results_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self._results_list.currentRowChanged.connect(self._on_result_selected)
        left_vbox.addWidget(QLabel("Results:"))
        left_vbox.addWidget(self._results_list)
        splitter.addWidget(left)

        # Right: details
        right = QWidget()
        right_vbox = QVBoxLayout(right)
        right_vbox.setContentsMargins(0, 0, 0, 0)

        self._detail_text = QTextEdit()
        self._detail_text.setReadOnly(True)
        right_vbox.addWidget(QLabel("Details:"))
        right_vbox.addWidget(self._detail_text)

        ver_row = QHBoxLayout()
        ver_row.addWidget(QLabel("Version:"))
        self._version_combo = QComboBox()
        ver_row.addWidget(self._version_combo, 1)
        right_vbox.addLayout(ver_row)

        install_row = QHBoxLayout()
        self._mods_dir_edit = QLineEdit(self._mods_dir)
        self._mods_dir_edit.setPlaceholderText("Mods directory path")
        self._browse_btn = QPushButton("Browse…")
        self._browse_btn.clicked.connect(self._browse_mods_dir)
        self._install_btn = QPushButton("Install Mod")
        self._install_btn.clicked.connect(self._do_install)
        install_row.addWidget(QLabel("Mods dir:"))
        install_row.addWidget(self._mods_dir_edit, 2)
        install_row.addWidget(self._browse_btn)
        install_row.addWidget(self._install_btn)
        right_vbox.addLayout(install_row)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter)

        self._status_label = QLabel("Ready.")
        root.addWidget(self._status_label)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _do_search(self) -> None:
        query = self._search_edit.text().strip()
        if not query:
            return
        mc_ver = self._mc_combo.currentText()
        if mc_ver == "Any version":
            mc_ver = ""
        loader = self._loader_combo.currentText()
        if loader == "Any loader":
            loader = ""
        source = self._source_combo.currentText()

        self._search_btn.setEnabled(False)
        self._results_list.clear()
        self._status_label.setText("Searching…")

        # Hint if CurseForge is selected but has no API key
        if source in ("curseforge", "both") and not self._settings.get("curseforge_api_key", ""):
            self._status_label.setText(
                "Searching… (CurseForge requires an API key – configure it in Settings)"
            )

        thread = QThread(self)
        worker = SearchWorker(self._manager, query, mc_ver, loader, source)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.results_ready.connect(self._on_search_results)
        worker.error.connect(self._on_search_error)
        worker.finished.connect(thread.quit)
        worker.finished.connect(lambda: self._search_btn.setEnabled(True))
        thread.finished.connect(thread.deleteLater)
        self._threads.append(thread)
        self._workers.append(worker)  # prevent GC while thread runs
        thread.start()

    def _on_search_results(self, results: List[ModInfo]) -> None:
        self._search_results = results
        self._results_list.clear()
        for mod in results:
            item = QListWidgetItem(f"[{mod.source}] {mod.name}")
            item.setToolTip(mod.summary)
            self._results_list.addItem(item)
        if results:
            self._status_label.setText(f"Found {len(results)} result(s).")
        else:
            hint = ""
            source = self._source_combo.currentText()
            if source in ("curseforge", "both") and not self._settings.get("curseforge_api_key", ""):
                hint = " (CurseForge skipped – no API key; configure in Settings)"
            self._status_label.setText(f"No results found.{hint}")

    def _on_search_error(self, error_msg: str) -> None:
        self._status_label.setText(f"Search failed: {error_msg}")
        QMessageBox.warning(
            self,
            "Search Error",
            f"The search could not be completed:\n\n{error_msg}\n\n"
            "Please check your internet connection and API keys in Settings.",
        )

    def _on_result_selected(self, row: int) -> None:
        if row < 0 or row >= len(self._search_results):
            return
        mod = self._search_results[row]
        self._current_mod = mod
        self._version_combo.clear()

        details = (
            f"<b>{mod.name}</b><br>"
            f"<i>by {mod.author}</i><br><br>"
            f"{mod.summary}<br><br>"
            f"<b>Downloads:</b> {mod.downloads:,}<br>"
            f"<b>Source:</b> {mod.source}<br>"
            f"<b>Loaders:</b> {', '.join(mod.mod_loaders)}<br>"
            f"<b>MC Versions:</b> {', '.join(mod.game_versions[-5:])}<br>"
            f'<a href="{mod.project_url}">View on website</a>'
        )
        self._detail_text.setHtml(details)

        # Load versions in background
        mc_ver = self._mc_combo.currentText()
        if mc_ver == "Any version":
            mc_ver = ""
        loader = self._loader_combo.currentText()
        if loader == "Any loader":
            loader = ""

        thread = QThread(self)
        worker = VersionWorker(self._manager, mod, mc_ver, loader)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.versions_ready.connect(self._on_versions_ready)
        worker.finished.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)
        self._threads.append(thread)
        self._workers.append(worker)  # prevent GC while thread runs
        thread.start()

    def _on_versions_ready(self, versions: List[ModVersion]) -> None:
        self._versions = versions
        self._version_combo.clear()
        for v in versions:
            label = f"{v.version_number}  [{', '.join(v.game_versions)}]"
            self._version_combo.addItem(label)

    def _browse_mods_dir(self) -> None:
        from PyQt5.QtWidgets import QFileDialog
        d = QFileDialog.getExistingDirectory(self, "Select Mods Directory")
        if d:
            self._mods_dir_edit.setText(d)

    def _do_install(self) -> None:
        idx = self._version_combo.currentIndex()
        if idx < 0 or idx >= len(self._versions):
            QMessageBox.warning(self, "Install", "No version selected.")
            return
        version = self._versions[idx]
        mods_dir = self._mods_dir_edit.text().strip()
        if not mods_dir:
            QMessageBox.warning(self, "Install", "Please select a mods directory.")
            return

        # Compatibility check
        mc_ver = self._mc_combo.currentText()
        if mc_ver == "Any version":
            mc_ver = ""
        loader = self._loader_combo.currentText()
        if loader == "Any loader":
            loader = ""
        compat = ModManager.check_compatibility(version, mc_ver, loader)
        if not compat["compatible"] and compat["warnings"]:
            msg = "\n".join(compat["warnings"])
            result = QMessageBox.question(
                self,
                "Compatibility Warning",
                f"{msg}\n\nInstall anyway?",
            )
            if result != QMessageBox.Yes:
                return

        self._install_btn.setEnabled(False)
        self._progress_bar.setVisible(True)
        self._progress_bar.setValue(0)

        thread = QThread(self)
        worker = InstallWorker(self._manager, version, mods_dir)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_install_progress)
        worker.finished.connect(self._on_install_done)
        worker.finished.connect(lambda ok, msg: thread.quit())
        thread.finished.connect(thread.deleteLater)
        self._threads.append(thread)
        self._workers.append(worker)  # prevent GC while thread runs
        thread.start()

    def _on_install_progress(self, downloaded: int, total: int) -> None:
        if total > 0:
            self._progress_bar.setMaximum(total)
            self._progress_bar.setValue(downloaded)

    def _on_install_done(self, ok: bool, msg: str) -> None:
        self._install_btn.setEnabled(True)
        self._progress_bar.setVisible(False)
        self._status_label.setText(msg)
        if ok:
            QMessageBox.information(self, "Install", msg)
        else:
            QMessageBox.critical(self, "Install", msg)

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def set_mods_dir(self, path: str) -> None:
        self._mods_dir = path
        self._mods_dir_edit.setText(path)
