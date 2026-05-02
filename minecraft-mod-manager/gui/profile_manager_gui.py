"""Profile manager GUI tab – create, load, save, export, import profiles."""

from pathlib import Path
from typing import List, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

from core.profile_manager import ModProfile, ProfileManager
from core.mod_manager import ModManager
from config.settings import Settings
from utils.constants import MC_VERSIONS, MOD_LOADERS
from utils.logger import get_logger

logger = get_logger("profile_manager_gui")


class ProfileManagerPanel(QWidget):
    """Manage mod-pack profiles."""

    def __init__(
        self,
        profile_manager: ProfileManager,
        mod_manager: ModManager,
        settings: Settings,
        parent: QWidget = None,
    ) -> None:
        super().__init__(parent)
        self._pm = profile_manager
        self._mm = mod_manager
        self._settings = settings
        self._current_profile: Optional[ModProfile] = None
        self._build_ui()
        self._refresh_profile_list()

    # ------------------------------------------------------------------
    # Build UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        splitter = QSplitter(Qt.Horizontal)

        # Left: profile list
        left = QWidget()
        left_vbox = QVBoxLayout(left)
        left_vbox.setContentsMargins(0, 0, 0, 0)
        left_vbox.addWidget(QLabel("Saved Profiles:"))
        self._profile_list = QListWidget()
        self._profile_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self._profile_list.currentRowChanged.connect(self._on_profile_selected)
        left_vbox.addWidget(self._profile_list)

        btn_row = QHBoxLayout()
        self._new_btn = QPushButton("New")
        self._new_btn.clicked.connect(self._do_new_profile)
        self._delete_btn = QPushButton("Delete")
        self._delete_btn.clicked.connect(self._do_delete)
        self._import_btn = QPushButton("Import…")
        self._import_btn.clicked.connect(self._do_import)
        btn_row.addWidget(self._new_btn)
        btn_row.addWidget(self._delete_btn)
        btn_row.addWidget(self._import_btn)
        left_vbox.addLayout(btn_row)
        splitter.addWidget(left)

        # Right: profile details
        right = QWidget()
        right_vbox = QVBoxLayout(right)
        right_vbox.setContentsMargins(0, 0, 0, 0)

        details_group = QGroupBox("Profile Details")
        form = QFormLayout(details_group)

        self._name_edit = QLineEdit()
        form.addRow("Name:", self._name_edit)

        self._desc_edit = QTextEdit()
        self._desc_edit.setMaximumHeight(60)
        form.addRow("Description:", self._desc_edit)

        self._ver_combo = QComboBox()
        self._ver_combo.addItems(MC_VERSIONS)
        form.addRow("MC Version:", self._ver_combo)

        self._loader_combo = QComboBox()
        self._loader_combo.addItems(MOD_LOADERS)
        form.addRow("Mod Loader:", self._loader_combo)

        right_vbox.addWidget(details_group)

        right_vbox.addWidget(QLabel("Mods in this Profile:"))
        self._mods_table = QTableWidget(0, 4)
        self._mods_table.setHorizontalHeaderLabels(["Mod Name", "Version", "Source", "Mod ID"])
        self._mods_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._mods_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._mods_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        right_vbox.addWidget(self._mods_table)

        action_row = QHBoxLayout()
        self._save_btn = QPushButton("💾 Save Profile")
        self._save_btn.clicked.connect(self._do_save)
        self._export_btn = QPushButton("📤 Export…")
        self._export_btn.clicked.connect(self._do_export)
        self._install_all_btn = QPushButton("⬇ Install All Mods")
        self._install_all_btn.clicked.connect(self._do_install_all)
        self._remove_mod_btn = QPushButton("Remove Mod")
        self._remove_mod_btn.clicked.connect(self._do_remove_mod)
        action_row.addWidget(self._save_btn)
        action_row.addWidget(self._export_btn)
        action_row.addWidget(self._install_all_btn)
        action_row.addWidget(self._remove_mod_btn)
        action_row.addStretch()
        right_vbox.addLayout(action_row)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter)

        self._status_label = QLabel("Select or create a profile.")
        root.addWidget(self._status_label)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _refresh_profile_list(self) -> None:
        self._profile_list.clear()
        for name in self._pm.list_profiles():
            self._profile_list.addItem(QListWidgetItem(name))

    def _load_profile_into_ui(self, profile: ModProfile) -> None:
        self._name_edit.setText(profile.name)
        self._desc_edit.setPlainText(profile.description)
        idx = self._ver_combo.findText(profile.minecraft_version)
        if idx >= 0:
            self._ver_combo.setCurrentIndex(idx)
        idx = self._loader_combo.findText(profile.mod_loader)
        if idx >= 0:
            self._loader_combo.setCurrentIndex(idx)

        self._mods_table.setRowCount(0)
        for mod in profile.mods:
            row = self._mods_table.rowCount()
            self._mods_table.insertRow(row)
            self._mods_table.setItem(row, 0, QTableWidgetItem(mod.get("mod_name", "")))
            self._mods_table.setItem(row, 1, QTableWidgetItem(mod.get("version_number", "")))
            self._mods_table.setItem(row, 2, QTableWidgetItem(mod.get("source", "")))
            self._mods_table.setItem(row, 3, QTableWidgetItem(mod.get("mod_id", "")))

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_profile_selected(self, row: int) -> None:
        names = self._pm.list_profiles()
        if row < 0 or row >= len(names):
            return
        profile = self._pm.load_profile(names[row])
        if profile:
            self._current_profile = profile
            self._load_profile_into_ui(profile)
            self._status_label.setText(f"Loaded profile: {profile.name}")

    def _do_new_profile(self) -> None:
        profile = ModProfile(
            name="New Profile",
            minecraft_version=self._settings.get("default_mc_version", MC_VERSIONS[0]),
            mod_loader=self._settings.get("default_mod_loader", "Fabric"),
        )
        self._current_profile = profile
        self._load_profile_into_ui(profile)
        self._name_edit.setFocus()
        self._status_label.setText("New profile created. Fill in details and save.")

    def _do_save(self) -> None:
        if not self._current_profile:
            QMessageBox.warning(self, "Save", "No profile to save.")
            return
        self._current_profile.name = self._name_edit.text().strip() or "Unnamed"
        self._current_profile.description = self._desc_edit.toPlainText()
        self._current_profile.minecraft_version = self._ver_combo.currentText()
        self._current_profile.mod_loader = self._loader_combo.currentText()
        if self._pm.save_profile(self._current_profile):
            self._refresh_profile_list()
            self._status_label.setText(f"Profile '{self._current_profile.name}' saved.")
        else:
            QMessageBox.critical(self, "Save", "Failed to save profile.")

    def _do_delete(self) -> None:
        row = self._profile_list.currentRow()
        names = self._pm.list_profiles()
        if row < 0 or row >= len(names):
            return
        name = names[row]
        result = QMessageBox.question(self, "Delete Profile", f"Delete profile '{name}'?")
        if result == QMessageBox.Yes:
            self._pm.delete_profile(name)
            self._refresh_profile_list()
            self._current_profile = None
            self._status_label.setText(f"Profile '{name}' deleted.")

    def _do_export(self) -> None:
        if not self._current_profile:
            QMessageBox.warning(self, "Export", "No profile loaded.")
            return
        dest, _ = QFileDialog.getSaveFileName(
            self,
            "Export Profile",
            f"{self._current_profile.name}.json",
            "JSON Files (*.json)",
        )
        if dest:
            ok = self._pm.export_profile(self._current_profile.name, Path(dest))
            if ok:
                QMessageBox.information(self, "Export", f"Exported to {dest}")
            else:
                QMessageBox.critical(self, "Export", "Export failed.")

    def _do_import(self) -> None:
        src, _ = QFileDialog.getOpenFileName(
            self, "Import Profile", "", "JSON Files (*.json)"
        )
        if src:
            profile = self._pm.import_profile(Path(src))
            if profile:
                self._refresh_profile_list()
                self._status_label.setText(f"Imported profile: {profile.name}")
            else:
                QMessageBox.critical(self, "Import", "Failed to import profile.")

    def _do_remove_mod(self) -> None:
        if not self._current_profile:
            return
        rows = {idx.row() for idx in self._mods_table.selectedIndexes()}
        for row in sorted(rows, reverse=True):
            if row < len(self._current_profile.mods):
                mod = self._current_profile.mods[row]
                self._current_profile.remove_mod(mod.get("mod_id", ""))
        self._load_profile_into_ui(self._current_profile)

    def _do_install_all(self) -> None:
        if not self._current_profile:
            QMessageBox.warning(self, "Install", "No profile loaded.")
            return
        from PyQt5.QtWidgets import QFileDialog
        mods_dir = QFileDialog.getExistingDirectory(self, "Select Mods Directory")
        if not mods_dir:
            return

        mc_ver = self._current_profile.minecraft_version
        loader = self._current_profile.mod_loader
        installed = 0
        failed = 0
        for mod_entry in self._current_profile.mods:
            source = mod_entry.get("source", "modrinth")
            mod_id = mod_entry.get("mod_id", "")
            version_id = mod_entry.get("version_id", "")
            api = (
                self._mm._modrinth if source == "modrinth" else self._mm._curseforge
            )
            versions = api.get_mod_versions(mod_id, mc_ver, loader)
            target = next((v for v in versions if v.id == version_id), None)
            if target is None and versions:
                target = versions[0]
            if target:
                ok = self._mm.install_mod(target, Path(mods_dir))
                if ok:
                    installed += 1
                else:
                    failed += 1
            else:
                failed += 1

        msg = f"Installed {installed} mod(s)."
        if failed:
            msg += f" {failed} failed."
        self._status_label.setText(msg)
        QMessageBox.information(self, "Install All", msg)

    # ------------------------------------------------------------------
    # Public API used by MainWindow
    # ------------------------------------------------------------------

    def add_mod_to_current_profile(
        self,
        mod_id: str,
        mod_name: str,
        version_id: str,
        version_number: str,
        filename: str,
        source: str,
    ) -> None:
        """Called externally to pin a mod to the currently-loaded profile."""
        if not self._current_profile:
            QMessageBox.information(
                self,
                "Add to Profile",
                "Please create or load a profile first.",
            )
            return
        self._current_profile.add_mod(
            mod_id, mod_name, version_id, version_number, filename, source
        )
        self._load_profile_into_ui(self._current_profile)
        self._status_label.setText(f"Added '{mod_name}' to profile.")
