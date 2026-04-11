"""Installation manager tab – scan installations, view mods, update/remove."""

import re
from pathlib import Path
from typing import List, Optional

from PyQt5.QtCore import Qt, QThread, pyqtSignal, QObject
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
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
)

from core.minecraft_detector import MinecraftDetector, MinecraftInstallation
from core.mod_manager import ModManager
from core.event_bus import EventBus
from config.settings import Settings
from utils.logger import get_logger

logger = get_logger("installation_manager")


class ScanWorker(QObject):
    done = pyqtSignal(list)
    finished = pyqtSignal()

    def __init__(self, detector: MinecraftDetector) -> None:
        super().__init__()
        self._detector = detector
        logger.debug("ScanWorker initialized with detector: %s", self._detector)

    def run(self) -> None:
        logger.info("ScanWorker.run() starting...")
        try:
            logger.debug("Calling detector.find_installations()...")
            results = self._detector.find_installations()
            logger.info("ScanWorker found %d installation(s)", len(results))
            self.done.emit(results)
        except Exception as exc:
            logger.error("Scan failed with exception: %s", exc, exc_info=True)
            self.done.emit([])
        finally:
            logger.debug("ScanWorker finished.")
            self.finished.emit()


class UpdateCheckWorker(QObject):
    done = pyqtSignal(list)
    error = pyqtSignal(str)  # NEW: error signal
    finished = pyqtSignal()

    def __init__(self, manager: ModManager, mods: list, mc_ver: str, loader: str) -> None:
        super().__init__()
        self._manager = manager
        self._mods = mods
        self._mc_ver = mc_ver
        self._loader = loader
        logger.debug(
            "UpdateCheckWorker initialized: mods_count=%d, mc_ver=%s, loader=%s",
            len(mods),
            mc_ver,
            loader,
        )

    def run(self) -> None:
        logger.info("UpdateCheckWorker.run() starting with %d mods...", len(self._mods))
        try:
            logger.debug("Calling manager.check_for_updates() with 60 second timeout...")
            updates = self._manager.check_for_updates(
                self._mods,
                self._mc_ver,
                self._loader,
                timeout=60  # 60 second timeout
            )
            logger.info("UpdateCheckWorker found %d update(s)", len(updates))
            self.done.emit(updates)
        except Exception as exc:
            logger.error("Update check failed with exception: %s", exc, exc_info=True)
            self.error.emit(str(exc))  # NEW: emit error
            self.done.emit([])
        finally:
            logger.debug("UpdateCheckWorker finished.")
            self.finished.emit()

class UpdateSelectionDialog(QDialog):
    """Let the user choose which available updates to apply."""

    def __init__(self, updates: list, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Updates Available")
        self.setMinimumWidth(600)
        self._updates = updates
        self._chosen: List[int] = []
        logger.debug("UpdateSelectionDialog initialized with %d updates", len(updates))
        self._build_ui()

    def _build_ui(self) -> None:
        logger.debug("Building UpdateSelectionDialog UI...")
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(f"{len(self._updates)} update(s) available. Select which mods to update:")
        )

        self._list = QListWidget()
        self._list.setSelectionMode(QAbstractItemView.MultiSelection)
        for idx, u in enumerate(self._updates):
            current_name = u.get("current_mod_name", u.get("current_filename", "Unknown"))
            current_ver = u.get("current_version", "?")
            new_ver = u.get("new_version").version_number
            item_text = f"{current_name:<35} | {current_ver:<20} → {new_ver}"
            logger.debug("Adding update item #%d: %s", idx, item_text)
            self._list.addItem(QListWidgetItem(item_text))
        self._list.selectAll()
        layout.addWidget(self._list)

        btns = QHBoxLayout()
        update_sel_btn = QPushButton("Update Selected")
        update_sel_btn.clicked.connect(self._accept_selected)
        update_all_btn = QPushButton("Update All")
        update_all_btn.clicked.connect(self._accept_all)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(update_sel_btn)
        btns.addWidget(update_all_btn)
        btns.addStretch()
        btns.addWidget(cancel_btn)
        layout.addLayout(btns)
        logger.debug("UpdateSelectionDialog UI built successfully")

    def _accept_selected(self) -> None:
        self._chosen = [idx.row() for idx in self._list.selectedIndexes()]
        logger.debug("User selected %d update(s)", len(self._chosen))
        if not self._chosen:
            logger.warning("No mods selected in UpdateSelectionDialog")
            QMessageBox.warning(self, "No Selection", "Please select at least one mod to update.")
            return
        logger.info("Accepting %d selected update(s)", len(self._chosen))
        self.accept()

    def _accept_all(self) -> None:
        self._chosen = list(range(len(self._updates)))
        logger.info("User selected to update all %d mod(s)", len(self._chosen))
        self.accept()

    def chosen_updates(self) -> list:
        chosen_list = [self._updates[i] for i in self._chosen]
        logger.debug("Returning %d chosen update(s)", len(chosen_list))
        return chosen_list


class InstallationManagerPanel(QWidget):
    """Scan Minecraft installations and manage their installed mods."""

    def __init__(
        self,
        manager: ModManager,
        settings: Settings,
        event_bus: EventBus = None,
        parent: QWidget = None,
    ) -> None:
        super().__init__(parent)
        self._manager = manager
        self._settings = settings
        self._event_bus = event_bus
        self._installations: List[MinecraftInstallation] = []
        self._current_install: Optional[MinecraftInstallation] = None
        self._installed_mods: List[dict] = []
        self._threads: List[QThread] = []
        self._clean_version_text = ""  # Store clean version number
        logger.debug("InstallationManagerPanel initialized")
        self._build_ui()

        # React to mod_installed signal so the list stays fresh
        if self._event_bus is not None:
            self._event_bus.mod_installed.connect(self._on_mod_installed_externally)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        logger.debug("Building InstallationManagerPanel UI...")
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

        # Right: mods and version selector
        right = QWidget()
        right_vbox = QVBoxLayout(right)
        right_vbox.setContentsMargins(0, 0, 0, 0)

        # Version selector row
        ver_row = QHBoxLayout()
        ver_row.addWidget(QLabel("Minecraft version:"))
        self._version_combo = QComboBox()
        self._version_combo.setMinimumWidth(160)
        self._version_combo.setToolTip("Select the Minecraft version to check updates against")
        self._version_combo.currentTextChanged.connect(self._on_version_changed)
        ver_row.addWidget(self._version_combo)
        
        # Loader label
        ver_row.addWidget(QLabel("Loader:"))
        self._loader_label = QLabel("-")
        self._loader_label.setMinimumWidth(100)
        ver_row.addWidget(self._loader_label)
        
        ver_row.addStretch()
        right_vbox.addLayout(ver_row)

        right_vbox.addWidget(QLabel("Installed Mods:"))

        # Updated table with 3 columns: Name, Version, Size
        self._mods_table = QTableWidget(0, 3)
        self._mods_table.setHorizontalHeaderLabels(["Mod Name", "Version", "Size (MB)"])
        self._mods_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._mods_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._mods_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
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
        logger.debug("InstallationManagerPanel UI built successfully")

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _do_scan(self) -> None:
        logger.info("Scan button clicked")
        extra_dirs = self._settings.get("minecraft_dirs", [])
        logger.debug("Extra directories from settings: %s", extra_dirs)
        detector = MinecraftDetector(extra_dirs)
        logger.debug("MinecraftDetector created: %s", detector)
        self._scan_btn.setEnabled(False)
        self._progress_bar.setVisible(True)
        self._install_list.clear()
        logger.debug("UI updated: button disabled, progress bar visible, list cleared")

        logger.debug("Creating and starting ScanWorker thread...")
        thread = QThread(self)
        worker = ScanWorker(detector)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.done.connect(self._on_scan_done)
        worker.finished.connect(thread.quit)
        worker.finished.connect(lambda: self._scan_btn.setEnabled(True))
        worker.finished.connect(lambda: self._progress_bar.setVisible(False))
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._threads.append(thread)
        logger.debug("ScanWorker thread configured, starting...")
        thread.start()
        logger.info("Scan thread started")

    def _on_scan_done(self, installations: List[MinecraftInstallation]) -> None:
        logger.info("_on_scan_done() called with %d installation(s)", len(installations))
        self._installations = installations
        self._install_list.clear()
        if not installations:
            logger.warning("No Minecraft installations found")
            self._status_label.setText("No Minecraft installations found.")
            return
        
        logger.debug("Populating installation list...")
        for idx, inst in enumerate(installations, 1):
            item_text = f"{inst.path.name}"
            logger.debug("Adding installation #%d to list: %s (path: %s)", idx, item_text, inst.path)
            item = QListWidgetItem(item_text)
            item.setToolTip(str(inst.path))
            self._install_list.addItem(item)
        
        self._status_label.setText(f"Found {len(installations)} installation(s).")
        
        # Auto-select if there is exactly one
        if len(installations) == 1:
            logger.debug("Only one installation found, auto-selecting it")
            self._install_list.setCurrentRow(0)
        logger.info("Scan completed successfully with %d installation(s)", len(installations))

    def _on_install_selected(self, row: int) -> None:
        logger.info("Installation selected: row=%d", row)
        if row < 0 or row >= len(self._installations):
            logger.warning("Invalid installation row selected: %d", row)
            return
        inst = self._installations[row]
        self._current_install = inst
        logger.debug("Current installation set to: %s", inst.path)

        # Populate version combo with this installation's versions
        logger.debug("Populating version combo with %d version(s)...", len(inst.versions))
        self._version_combo.clear()
        for ver in inst.versions:
            self._version_combo.addItem(ver)
            logger.debug("Added version to combo: %s", ver)
        
        # Default to the last (newest) version
        if inst.versions:
            self._version_combo.setCurrentIndex(len(inst.versions) - 1)
            logger.debug("Set version combo to newest version: %s", inst.versions[-1])

        logger.debug("Loading mods from installation...")
        detector = MinecraftDetector()
        self._installed_mods = detector.get_installed_mods(inst)
        logger.info("Loaded %d mods from %s", len(self._installed_mods), inst.path)

        # Persist to Settings so Profiles tab can read the list
        self._sync_installed_mods_to_settings()

        self._refresh_mods_table()
        self._status_label.setText(
            f"Loaded {len(self._installed_mods)} mod(s) from {inst.path}"
        )

    def _extract_version_number(self, version_text: str) -> str:
        """Extract the version number from version folder name.
        
        Examples:
        - "1.20.1" -> "1.20.1"
        - "Forge 1.20.1" -> "1.20.1"
        - "ForgeOptiFine 1.18.2" -> "1.18.2"
        - "neoforge-21.1.214" -> "21.1.214"
        - "FabricSodium 1.19.2" -> "1.19.2"
        """
        # Try to find a version pattern like 1.20.1 or 21.1.214
        match = re.search(r'(\d+\.\d+(?:\.\d+)?)', version_text)
        if match:
            extracted = match.group(1)
            logger.debug("Extracted version number '%s' from '%s'", extracted, version_text)
            return extracted
        
        # Fallback to original text if no pattern found
        logger.warning("Could not extract version number from: %s, using as-is", version_text)
        return version_text

    def _on_version_changed(self, version_text: str) -> None:
        """Called when user selects a different Minecraft version.
        
        Detects the mod loader for this specific version and extracts clean version number.
        """
        if not self._current_install or not version_text:
            self._loader_label.setText("-")
            self._clean_version_text = ""
            return
        
        logger.info("Version changed to: %s", version_text)
        
        # Extract clean version number from version_text
        clean_version = self._extract_version_number(version_text)
        self._clean_version_text = clean_version  # Store for later use in update check
        logger.info("Clean version stored: %s", clean_version)
        
        # Detect loader based on selected version
        detector = MinecraftDetector()
        loader = detector._detect_loader_for_version(self._current_install.path, version_text)
        
        logger.info("Detected loader for %s: %s", version_text, loader or "Unknown")
        self._loader_label.setText(loader if loader else "Unknown")

    def _refresh_mods_table(self) -> None:
        logger.debug("Refreshing mods table with %d mod(s)...", len(self._installed_mods))
        self._mods_table.setRowCount(0)
        for idx, mod in enumerate(self._installed_mods):
            row = self._mods_table.rowCount()
            self._mods_table.insertRow(row)
            
            # Get mod name (prefer extracted name over filename)
            mod_name = mod.get("mod_name", mod.get("filename", "Unknown"))
            mod_version = mod.get("mod_version", "N/A")
            size_mb = mod.get("size", 0) / (1024 * 1024)
            
            # Create table items
            name_item = QTableWidgetItem(mod_name)
            version_item = QTableWidgetItem(mod_version)
            size_item = QTableWidgetItem(f"{size_mb:.2f}")
            
            # Add to table
            self._mods_table.setItem(row, 0, name_item)
            self._mods_table.setItem(row, 1, version_item)
            self._mods_table.setItem(row, 2, size_item)
            
            logger.debug(
                "Added mod to table row %d: %s | %s | %.2f MB",
                row,
                mod_name,
                mod_version,
                size_mb,
            )
        logger.debug("Mods table refresh complete")

    def _do_remove(self) -> None:
        logger.info("Remove button clicked")
        rows = {idx.row() for idx in self._mods_table.selectedIndexes()}
        logger.debug("Selected rows for removal: %s", rows)
        if not rows:
            logger.warning("No mods selected for removal")
            return
        
        result = QMessageBox.question(
            self,
            "Remove Mods",
            f"Remove {len(rows)} selected mod(s)?",
        )
        if result != QMessageBox.Yes:
            logger.info("User cancelled mod removal")
            return
        
        logger.info("User confirmed removal of %d mod(s)", len(rows))
        backup = self._settings.get("backup_before_update", True)
        logger.debug("Backup before removal enabled: %s", backup)
        
        for row in sorted(rows, reverse=True):
            mod_info = self._installed_mods[row]
            mod_path = Path(mod_info["path"])
            mod_name = mod_info.get("mod_name", mod_path.name)
            logger.info("Removing mod: %s (%s)", mod_name, mod_path)
            self._manager.remove_mod(mod_path, backup=backup)
        
        logger.debug("All selected mods removed, reloading mod list...")
        if self._current_install:
            detector = MinecraftDetector()
            self._installed_mods = detector.get_installed_mods(self._current_install)
            logger.debug("Reloaded %d mods after removal", len(self._installed_mods))
            self._sync_installed_mods_to_settings()
            self._refresh_mods_table()
        self._status_label.setText("Selected mod(s) removed.")
        logger.info("Mod removal complete")

    def _do_update_check(self) -> None:
        logger.info("Update check button clicked")
        if not self._current_install:
            logger.warning("Update check clicked but no installation selected")
            QMessageBox.information(self, "Update Check", "Please select an installation first.")
            return
        if not self._installed_mods:
            logger.warning("Update check clicked but no mods found")
            QMessageBox.information(self, "Update Check", "No mods found in the mods folder.")
            return

        # Use the clean version number (e.g., "1.20.1" not "Forge 1.20.1")
        mc_ver = self._clean_version_text if self._clean_version_text else self._settings.get("default_mc_version", "")
        
        # Get loader from label (detected for current version)
        loader = self._loader_label.text() if self._loader_label.text() != "-" else self._settings.get("default_mod_loader", "")
        
        logger.info("Update check parameters: version=%s, loader=%s, mods_count=%d", mc_ver, loader, len(self._installed_mods))

        self._update_check_btn.setEnabled(False)
        self._status_label.setText(f"Checking for updates against Minecraft {mc_ver} [{loader}]… (timeout: 60s)")

        logger.debug("Creating and starting UpdateCheckWorker thread...")
        thread = QThread(self)
        worker = UpdateCheckWorker(self._manager, self._installed_mods, mc_ver, loader)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.done.connect(self._on_update_check_done)
        worker.error.connect(self._on_update_check_error)  # NEW: connect error signal
        worker.finished.connect(thread.quit)
        worker.finished.connect(lambda: self._update_check_btn.setEnabled(True))
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._threads.append(thread)
        logger.debug("UpdateCheckWorker thread configured, starting...")
        thread.start()
        logger.info("Update check thread started")

    def _on_update_check_error(self, error_msg: str) -> None:
        """Called when update check encounters an error."""
        logger.error("Update check error: %s", error_msg)
        self._status_label.setText("Update check failed - see error below")
        QMessageBox.critical(
            self,
            "Update Check Failed",
            f"An error occurred while checking for updates:\n\n{error_msg}\n\nMake sure you have internet connection and try again.",
        )

    def _on_update_check_done(self, updates: list) -> None:
        logger.info("_on_update_check_done() called with %d update(s)", len(updates))
        if not updates:
            logger.info("No updates available")
            self._status_label.setText("All mods are up to date.")
            QMessageBox.information(self, "Update Check", "All mods are up to date!")
            return

        logger.debug("Updates available: %d", len(updates))
        self._status_label.setText(f"{len(updates)} update(s) available.")
        dialog = UpdateSelectionDialog(updates, parent=self)
        logger.debug("UpdateSelectionDialog created, showing to user...")
        if dialog.exec_() != QDialog.Accepted:
            logger.info("User cancelled update selection")
            return

        chosen = dialog.chosen_updates()
        logger.debug("User chose %d update(s) to apply", len(chosen))
        if not chosen:
            logger.warning("No updates chosen despite accepting dialog")
            return

        backup = self._settings.get("backup_before_update", True)
        logger.debug("Backup before update enabled: %s", backup)
        
        for idx, u in enumerate(chosen, 1):
            current_path = Path(u["current_path"])
            current_name = u.get("current_mod_name", current_path.name)
            new_version = u["new_version"].version_number
            logger.info(
                "Applying update #%d/%d: %s (%s -> %s)",
                idx,
                len(chosen),
                current_name,
                u.get("current_version", "?"),
                new_version,
            )
            self._manager.update_mod(
                current_path,
                u["new_version"],
                current_path.parent,
                backup=backup,
            )

        logger.debug("All updates applied, reloading mod list...")
        if self._current_install:
            detector = MinecraftDetector()
            self._installed_mods = detector.get_installed_mods(self._current_install)
            logger.debug("Reloaded %d mods after update", len(self._installed_mods))
            self._sync_installed_mods_to_settings()
            self._refresh_mods_table()
        self._status_label.setText(f"Updated {len(chosen)} mod(s).")
        logger.info("Update complete: %d mod(s) updated", len(chosen))

    # ------------------------------------------------------------------
    # Settings synchronisation & event bus helpers
    # ------------------------------------------------------------------

    def _sync_installed_mods_to_settings(self) -> None:
        """Persist the current installed-mods list to Settings and notify peers."""
        self._settings.set("installed_mods", list(self._installed_mods))
        logger.debug(
            "Synced %d installed mod(s) to settings", len(self._installed_mods)
        )
        if self._event_bus is not None:
            self._event_bus.mods_updated.emit()

    def _on_mod_installed_externally(self, mod_name: str, mod_path: str) -> None:
        """Called when Mod Browser emits mod_installed.

        If the installed mod lives in the same folder as the currently
        selected installation, reload the mod list so the new entry
        appears immediately.
        """
        logger.info(
            "mod_installed signal received: name=%s, path=%s", mod_name, mod_path
        )
        if self._current_install is None:
            return
        if mod_path:
            try:
                target = Path(mod_path).resolve()
                install_root = self._current_install.path.resolve()
                # Refresh if the installed-mod path is inside this installation
                if target == install_root / "mods" or target.is_relative_to(install_root):
                    detector = MinecraftDetector()
                    self._installed_mods = detector.get_installed_mods(self._current_install)
                    self._sync_installed_mods_to_settings()
                    self._refresh_mods_table()
                    self._status_label.setText(
                        f"Refreshed – {len(self._installed_mods)} mod(s) installed."
                    )
            except Exception as exc:
                logger.warning("Could not check path relativity: %s", exc)