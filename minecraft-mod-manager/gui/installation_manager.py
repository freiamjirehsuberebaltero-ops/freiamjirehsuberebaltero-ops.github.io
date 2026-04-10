"""Installation manager tab – scan installations, view mods, update/remove."""

import threading
from pathlib import Path
from typing import List, Optional

from PyQt5.QtCore import Qt, QThread, pyqtSignal, QObject
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QHeaderView,
    QProgressBar,
    QComboBox,
)

from core.minecraft_detector import MinecraftDetector, MinecraftInstallation
from core.mod_manager import ModManager
from config.settings import Settings
from utils.logger import get_logger

logger = get_logger("installation_manager")


class ScanWorker(QObject):
    done = pyqtSignal(list)
    finished = pyqtSignal()

    def __init__(self, detector: MinecraftDetector) -> None:
        super().__init__()
        self._detector = detector

    def run(self) -> None:
        results = self._detector.find_installations()
        self.done.emit(results)
        self.finished.emit()


class UpdateCheckWorker(QObject):
    done = pyqtSignal(list)
    finished = pyqtSignal()

    def __init__(self, manager: ModManager, mods: list, mc_ver: str, loader: str) -> None:
        super().__init__()
        self._manager = manager
        self._mods = mods
        self._mc_ver = mc_ver
        self._loader = loader

    def run(self) -> None:
        updates = self._manager.check_for_updates(self._mods, self._mc_ver, self._loader)
        self.done.emit(updates)
        self.finished.emit()


class InstallationManagerPanel(QWidget):
    """Scan Minecraft installations and manage their installed mods."""

    def __init__(
        self,
        manager: ModManager,
        settings: Settings,
        parent: QWidget = None,
    ) -> None:
        super().__init__(parent)
        self._manager = manager
        self._settings = settings
        self._installations: List[MinecraftInstallation] = []
        self._current_install: Optional[MinecraftInstallation] = None
        self._installed_mods: List[dict] = []
        self._threads: List[QThread] = []
        self._build_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # Top toolbar
        toolbar = QHBoxLayout()
        self._scan_btn = QPushButton("🔍 Scan for Installations")
        self._scan_btn.clicked.connect(self._do_scan)
        toolbar.addWidget(self._scan_btn)
        toolbar.addStretch()
        root.addLayout(toolbar)

        self._progress_bar = QProgressBar()
        self._progress_bar.setVisible(False)
        self._progress_bar.setRange(0, 0)
        root.addWidget(self._progress_bar)

        splitter = QSplitter(Qt.Horizontal)

        # Left: installations list
        left = QWidget()
        left_vbox = QVBoxLayout(left)
        left_vbox.setContentsMargins(0, 0, 0, 0)
        left_vbox.addWidget(QLabel("Detected Installations:"))
        self._install_list = QListWidget()
        self._install_list.currentRowChanged.connect(self._on_install_selected)
        left_vbox.addWidget(self._install_list)
        splitter.addWidget(left)

        # Right: mods in selected installation
        right = QWidget()
        right_vbox = QVBoxLayout(right)
        right_vbox.setContentsMargins(0, 0, 0, 0)
        right_vbox.addWidget(QLabel("Installed Mods:"))

        self._mods_table = QTableWidget(0, 2)
        self._mods_table.setHorizontalHeaderLabels(["Filename", "Size (KB)"])
        self._mods_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._mods_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._mods_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        right_vbox.addWidget(self._mods_table)

        mod_btns = QHBoxLayout()
        self._remove_btn = QPushButton("Remove Selected")
        self._remove_btn.clicked.connect(self._do_remove)
        self._update_check_btn = QPushButton("Check for Updates")
        self._update_check_btn.clicked.connect(self._do_update_check)
        mod_btns.addWidget(self._remove_btn)
        mod_btns.addWidget(self._update_check_btn)
        mod_btns.addStretch()
        right_vbox.addLayout(mod_btns)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter)

        self._status_label = QLabel("Click 'Scan for Installations' to begin.")
        root.addWidget(self._status_label)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _do_scan(self) -> None:
        extra_dirs = self._settings.get("minecraft_dirs", [])
        detector = MinecraftDetector(extra_dirs)
        self._scan_btn.setEnabled(False)
        self._progress_bar.setVisible(True)
        self._install_list.clear()

        thread = QThread(self)
        worker = ScanWorker(detector)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.done.connect(self._on_scan_done)
        worker.finished.connect(thread.quit)
        worker.finished.connect(lambda: self._scan_btn.setEnabled(True))
        worker.finished.connect(lambda: self._progress_bar.setVisible(False))
        thread.finished.connect(thread.deleteLater)
        self._threads.append(thread)
        thread.start()

    def _on_scan_done(self, installations: List[MinecraftInstallation]) -> None:
        self._installations = installations
        self._install_list.clear()
        if not installations:
            self._status_label.setText("No Minecraft installations found.")
            return
        for inst in installations:
            loader_str = f" [{inst.mod_loader}]" if inst.mod_loader else ""
            label = f"{inst.path.name}{loader_str}"
            item = QListWidgetItem(label)
            item.setToolTip(str(inst.path))
            self._install_list.addItem(item)
        self._status_label.setText(f"Found {len(installations)} installation(s).")

    def _on_install_selected(self, row: int) -> None:
        if row < 0 or row >= len(self._installations):
            return
        inst = self._installations[row]
        self._current_install = inst
        detector = MinecraftDetector()
        self._installed_mods = detector.get_installed_mods(inst)
        self._refresh_mods_table()
        self._status_label.setText(
            f"Loaded {len(self._installed_mods)} mod(s) from {inst.path}"
        )

    def _refresh_mods_table(self) -> None:
        self._mods_table.setRowCount(0)
        for mod in self._installed_mods:
            row = self._mods_table.rowCount()
            self._mods_table.insertRow(row)
            self._mods_table.setItem(row, 0, QTableWidgetItem(mod["filename"]))
            size_kb = f"{mod['size'] / 1024:.1f}"
            self._mods_table.setItem(row, 1, QTableWidgetItem(size_kb))

    def _do_remove(self) -> None:
        rows = {idx.row() for idx in self._mods_table.selectedIndexes()}
        if not rows:
            return
        backup = self._settings.get("backup_before_update", True)
        result = QMessageBox.question(
            self,
            "Remove Mods",
            f"Remove {len(rows)} selected mod(s)?",
        )
        if result != QMessageBox.Yes:
            return
        for row in sorted(rows, reverse=True):
            mod_info = self._installed_mods[row]
            self._manager.remove_mod(Path(mod_info["path"]), backup=backup)
        # Refresh
        if self._current_install:
            detector = MinecraftDetector()
            self._installed_mods = detector.get_installed_mods(self._current_install)
            self._refresh_mods_table()
        self._status_label.setText("Selected mod(s) removed.")

    def _do_update_check(self) -> None:
        if not self._current_install:
            QMessageBox.information(self, "Update Check", "Please select an installation first.")
            return
        mc_ver = (
            self._current_install.versions[-1]
            if self._current_install.versions
            else self._settings.get("default_mc_version", "")
        )
        loader = self._current_install.mod_loader or self._settings.get("default_mod_loader", "")

        self._update_check_btn.setEnabled(False)
        self._status_label.setText("Checking for updates…")

        thread = QThread(self)
        worker = UpdateCheckWorker(self._manager, self._installed_mods, mc_ver, loader)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.done.connect(self._on_update_check_done)
        worker.finished.connect(thread.quit)
        worker.finished.connect(lambda: self._update_check_btn.setEnabled(True))
        thread.finished.connect(thread.deleteLater)
        self._threads.append(thread)
        thread.start()

    def _on_update_check_done(self, updates: list) -> None:
        if not updates:
            self._status_label.setText("All mods are up to date.")
            QMessageBox.information(self, "Update Check", "All mods are up to date!")
            return
        lines = [
            f"  • {u['current_filename']} → {u['new_version'].filename}"
            for u in updates
        ]
        msg = f"{len(updates)} update(s) available:\n" + "\n".join(lines)
        self._status_label.setText(f"{len(updates)} update(s) available.")
        result = QMessageBox.question(self, "Updates Available", msg + "\n\nUpdate all?")
        if result != QMessageBox.Yes:
            return
        backup = self._settings.get("backup_before_update", True)
        for u in updates:
            self._manager.update_mod(
                Path(u["current_path"]),
                u["new_version"],
                Path(u["current_path"]).parent,
                backup=backup,
            )
        if self._current_install:
            detector = MinecraftDetector()
            self._installed_mods = detector.get_installed_mods(self._current_install)
            self._refresh_mods_table()
        self._status_label.setText("Mods updated.")
