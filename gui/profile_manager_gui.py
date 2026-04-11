"""Profile manager GUI tab – create, load, save, export, import profiles."""

from pathlib import Path
from typing import List, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
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
    QScrollArea,
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
from core.event_bus import EventBus
from config.settings import Settings
from utils.constants import MC_VERSIONS, MOD_LOADERS
from utils.logger import get_logger

logger = get_logger("profile_manager_gui")


# ---------------------------------------------------------------------------
# Helper dialog
# ---------------------------------------------------------------------------

class AddInstalledModsDialog(QDialog):
    """Let the user pick which installed mods to add to the active profile."""

    def __init__(self, installed_mods: list, already_in_profile: set, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Installed Mods to Profile")
        self.setMinimumWidth(480)
        self.setMinimumHeight(400)
        self._installed_mods = installed_mods
        self._checkboxes: List[tuple] = []  # (QCheckBox, mod_dict)
        self._build_ui(already_in_profile)

    def _build_ui(self, already_in_profile: set) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Select the installed mods you want to add to this profile:"))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        vbox = QVBoxLayout(container)
        vbox.setSpacing(4)

        if not self._installed_mods:
            vbox.addWidget(QLabel(
                "No installed mods found.\n\n"
                "Go to the 🎮 Installations tab, select an installation, "
                "and the mods list will be populated here."
            ))
        else:
            for mod in self._installed_mods:
                name = mod.get("mod_name", mod.get("filename", "Unknown"))
                version = mod.get("mod_version", "")
                label = f"{name}" + (f"  [{version}]" if version else "")
                cb = QCheckBox(label)
                # Pre-tick mods already in the profile so user can see the overlap
                mod_id = _make_installed_mod_id(mod)
                cb.setChecked(mod_id not in already_in_profile)
                self._checkboxes.append((cb, mod))
                vbox.addWidget(cb)

        vbox.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll)

        # Select / deselect all helpers
        helper_row = QHBoxLayout()
        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(lambda: [cb.setChecked(True) for cb, _ in self._checkboxes])
        deselect_all_btn = QPushButton("Deselect All")
        deselect_all_btn.clicked.connect(lambda: [cb.setChecked(False) for cb, _ in self._checkboxes])
        helper_row.addWidget(select_all_btn)
        helper_row.addWidget(deselect_all_btn)
        helper_row.addStretch()
        layout.addLayout(helper_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_mods(self) -> list:
        """Return list of mod dicts whose checkboxes are ticked."""
        return [mod for cb, mod in self._checkboxes if cb.isChecked()]


def _make_installed_mod_id(mod: dict) -> str:
    """Build a stable synthetic ID for a mod coming from the Installation Manager."""
    import hashlib
    key = mod.get("filename") or mod.get("mod_name") or mod.get("path", "")
    return "installed_" + hashlib.sha1(key.encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Main panel
# ---------------------------------------------------------------------------

class ProfileManagerPanel(QWidget):
    """Manage mod-pack profiles."""

    def __init__(
        self,
        profile_manager: ProfileManager,
        mod_manager: ModManager,
        settings: Settings,
        event_bus: EventBus = None,
        parent: QWidget = None,
    ) -> None:
        super().__init__(parent)
        self._pm = profile_manager
        self._mm = mod_manager
        self._settings = settings
        self._event_bus = event_bus
        self._current_profile: Optional[ModProfile] = None
        self._build_ui()
        self._refresh_profile_list()

        # Wire up event bus signals
        if self._event_bus is not None:
            self._event_bus.mods_updated.connect(self._on_mods_updated)
            self._event_bus.mod_installed.connect(self._on_mod_installed)

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
        self._add_installed_btn = QPushButton("📥 Add from Installed")
        self._add_installed_btn.setToolTip(
            "Pick mods from the Installation Manager scan and add them to this profile"
        )
        self._add_installed_btn.clicked.connect(self._do_add_from_installed)
        self._remove_mod_btn = QPushButton("🗑 Remove Mod")
        self._remove_mod_btn.clicked.connect(self._do_remove_mod)
        action_row.addWidget(self._save_btn)
        action_row.addWidget(self._export_btn)
        action_row.addWidget(self._install_all_btn)
        action_row.addWidget(self._add_installed_btn)
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

    def _current_profile_mod_ids(self) -> set:
        """Return the set of mod_ids already in the current profile."""
        if not self._current_profile:
            return set()
        return {m.get("mod_id", "") for m in self._current_profile.mods}

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
        # Default to the mods_directory from Settings; let user override via dialog
        default_dir = self._settings.get("mods_directory", "")
        from PyQt5.QtWidgets import QFileDialog
        mods_dir = QFileDialog.getExistingDirectory(
            self, "Select Mods Directory", default_dir
        )
        if not mods_dir:
            return

        mc_ver = self._current_profile.minecraft_version
        loader = self._current_profile.mod_loader
        installed = 0
        failed = 0
        skipped = 0
        for mod_entry in self._current_profile.mods:
            source = mod_entry.get("source", "modrinth")

            if source in ("modrinth", "curseforge"):
                # Real API mod — use the stored mod_id to fetch versions directly.
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

            else:
                # Locally-scanned or browser-installed mod (synthetic ID).
                # If the .jar still exists on disk, nothing to do.
                # If it has been deleted, try to re-download via a Modrinth search.
                filename = mod_entry.get("filename", "")
                mod_name = mod_entry.get("mod_name", "")
                if filename and Path(mods_dir, filename).exists():
                    skipped += 1
                    continue

                if not mod_name:
                    # No name to search with — cannot recover.
                    failed += 1
                    continue

                try:
                    search_results = self._mm._modrinth.search_mods(
                        mod_name, mc_ver, loader
                    )
                    target = None
                    if search_results:
                        versions = self._mm._modrinth.get_mod_versions(
                            search_results[0].id, mc_ver, loader
                        )
                        if versions:
                            target = versions[0]
                except Exception:
                    target = None

                if target:
                    ok = self._mm.install_mod(target, Path(mods_dir))
                    if ok:
                        installed += 1
                    else:
                        failed += 1
                else:
                    failed += 1

        msg = f"Installed {installed} mod(s)."
        if skipped:
            msg += f" {skipped} local mod(s) skipped (already on disk)."
        if failed:
            msg += f" {failed} failed."
        self._status_label.setText(msg)
        QMessageBox.information(self, "Install All", msg)

    def _do_add_from_installed(self) -> None:
        """Open a checklist dialog and add the chosen installed mods to the active profile."""
        if not self._current_profile:
            QMessageBox.information(
                self,
                "Add from Installed",
                "Please create or load a profile first.",
            )
            return

        installed_mods = self._settings.get("installed_mods", [])
        if not installed_mods:
            QMessageBox.information(
                self,
                "Add from Installed",
                "No installed mods found.\n\n"
                "Go to the 🎮 Installations tab, select an installation, "
                "and then come back here to add those mods to the profile.",
            )
            return

        already = self._current_profile_mod_ids()
        dialog = AddInstalledModsDialog(installed_mods, already, parent=self)
        if dialog.exec_() != QDialog.Accepted:
            return

        chosen = dialog.selected_mods()
        if not chosen:
            self._status_label.setText("No mods selected.")
            return

        added = 0
        for mod in chosen:
            mod_id = _make_installed_mod_id(mod)
            mod_name = mod.get("mod_name", mod.get("filename", "Unknown"))
            mod_version = mod.get("mod_version", "")
            filename = mod.get("filename", "")
            self._current_profile.add_mod(
                mod_id=mod_id,
                mod_name=mod_name,
                version_id="",
                version_number=mod_version,
                filename=filename,
                source="installed",
            )
            added += 1

        self._load_profile_into_ui(self._current_profile)
        self._status_label.setText(f"Added {added} mod(s) to profile.")

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

    # ------------------------------------------------------------------
    # Event bus handlers
    # ------------------------------------------------------------------

    def _on_mods_updated(self) -> None:
        """Called when Installation Manager refreshes its mod list.

        Update the status label so the user knows new mods are available
        to add via the 'Add from Installed' button.
        """
        installed = self._settings.get("installed_mods", [])
        count = len(installed)
        logger.debug("mods_updated signal received – %d installed mod(s) available", count)
        msg = f"Installation Manager found {count} mod(s). Use '📥 Add from Installed' to add them."
        self._status_label.setText(msg)

    def _on_mod_installed(self, mod_name: str, mod_path: str) -> None:
        """Called when Mod Browser installs a new mod.

        Auto-adds a lightweight entry to the currently active profile so
        users don't have to manually manage profile membership.
        """
        import hashlib
        logger.info(
            "mod_installed signal received: name=%s path=%s", mod_name, mod_path
        )
        if not self._current_profile:
            return
        # Build a collision-resistant synthetic ID from the name + path
        raw = f"{mod_name}:{mod_path}"
        synthetic_id = "browser_" + hashlib.sha1(raw.encode()).hexdigest()[:12]
        self._current_profile.add_mod(
            mod_id=synthetic_id,
            mod_name=mod_name,
            version_id="",
            version_number="",
            filename="",
            source="browser",
        )
        self._load_profile_into_ui(self._current_profile)
        self._status_label.setText(f"Auto-added '{mod_name}' to active profile.")

