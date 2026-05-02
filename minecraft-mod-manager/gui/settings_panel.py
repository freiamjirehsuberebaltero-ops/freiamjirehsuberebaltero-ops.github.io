"""Settings panel GUI tab."""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
    QCheckBox,
    QFileDialog,
    QMessageBox,
)

from config.settings import Settings
from utils.constants import MC_VERSIONS, MOD_LOADERS
from utils.logger import get_logger

logger = get_logger("settings_panel")


class SettingsPanel(QWidget):
    """Tab for configuring application preferences."""

    def __init__(self, settings: Settings, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._build_ui()
        self._load_values()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # --- API Keys ---
        api_group = QGroupBox("API Keys")
        api_form = QFormLayout(api_group)

        self._cf_key_edit = QLineEdit()
        self._cf_key_edit.setEchoMode(QLineEdit.Password)
        self._cf_key_edit.setPlaceholderText("Enter CurseForge API key (optional)")
        api_form.addRow("CurseForge API Key:", self._cf_key_edit)

        root.addWidget(api_group)

        # --- Defaults ---
        defaults_group = QGroupBox("Defaults")
        defaults_form = QFormLayout(defaults_group)

        self._mc_version_combo = QComboBox()
        self._mc_version_combo.addItems(MC_VERSIONS)
        defaults_form.addRow("Default MC Version:", self._mc_version_combo)

        self._loader_combo = QComboBox()
        self._loader_combo.addItems(MOD_LOADERS)
        defaults_form.addRow("Default Mod Loader:", self._loader_combo)

        self._api_combo = QComboBox()
        self._api_combo.addItems(["both", "modrinth", "curseforge"])
        defaults_form.addRow("Preferred API:", self._api_combo)

        root.addWidget(defaults_group)

        # --- Behaviour ---
        behaviour_group = QGroupBox("Behaviour")
        behaviour_form = QFormLayout(behaviour_group)

        self._auto_update_cb = QCheckBox("Check for updates on startup")
        behaviour_form.addRow(self._auto_update_cb)

        self._backup_cb = QCheckBox("Backup mods before updating/removing")
        behaviour_form.addRow(self._backup_cb)

        self._max_backups_spin = QSpinBox()
        self._max_backups_spin.setRange(1, 50)
        behaviour_form.addRow("Max backup snapshots:", self._max_backups_spin)

        self._threads_spin = QSpinBox()
        self._threads_spin.setRange(1, 16)
        behaviour_form.addRow("Download threads:", self._threads_spin)

        root.addWidget(behaviour_group)

        # --- Custom Minecraft Directories ---
        dirs_group = QGroupBox("Custom Minecraft Directories")
        dirs_vbox = QVBoxLayout(dirs_group)

        dirs_vbox.addWidget(QLabel(
            "Add extra .minecraft folders to scan (e.g. TLauncher installs):"
        ))

        self._dirs_list = QListWidget()
        self._dirs_list.setFixedHeight(100)
        dirs_vbox.addWidget(self._dirs_list)

        dir_btn_row = QHBoxLayout()
        self._add_dir_btn = QPushButton("Browse…")
        self._add_dir_btn.clicked.connect(self._browse_dir)
        self._remove_dir_btn = QPushButton("Remove Selected")
        self._remove_dir_btn.clicked.connect(self._remove_dir)
        dir_btn_row.addWidget(self._add_dir_btn)
        dir_btn_row.addWidget(self._remove_dir_btn)
        dir_btn_row.addStretch()
        dirs_vbox.addLayout(dir_btn_row)

        root.addWidget(dirs_group)

        # --- Buttons ---
        btn_row = QHBoxLayout()
        self._save_btn = QPushButton("Save Settings")
        self._save_btn.clicked.connect(self._save)
        self._reset_btn = QPushButton("Reset to Defaults")
        self._reset_btn.clicked.connect(self._reset)
        btn_row.addStretch()
        btn_row.addWidget(self._save_btn)
        btn_row.addWidget(self._reset_btn)
        root.addLayout(btn_row)

        root.addStretch()

    # ------------------------------------------------------------------
    # Load / Save
    # ------------------------------------------------------------------

    def _load_values(self) -> None:
        s = self._settings
        self._cf_key_edit.setText(s.get("curseforge_api_key", ""))

        mc_ver = s.get("default_mc_version", MC_VERSIONS[0])
        idx = self._mc_version_combo.findText(mc_ver)
        if idx >= 0:
            self._mc_version_combo.setCurrentIndex(idx)

        loader = s.get("default_mod_loader", "Fabric")
        idx = self._loader_combo.findText(loader)
        if idx >= 0:
            self._loader_combo.setCurrentIndex(idx)

        api = s.get("preferred_api", "both")
        idx = self._api_combo.findText(api)
        if idx >= 0:
            self._api_combo.setCurrentIndex(idx)

        self._auto_update_cb.setChecked(bool(s.get("auto_update_check", True)))
        self._backup_cb.setChecked(bool(s.get("backup_before_update", True)))
        self._max_backups_spin.setValue(int(s.get("max_backups", 5)))
        self._threads_spin.setValue(int(s.get("download_threads", 4)))

        self._dirs_list.clear()
        for d in s.get("minecraft_dirs", []):
            self._dirs_list.addItem(d)

    def _save(self) -> None:
        minecraft_dirs = [
            self._dirs_list.item(i).text()
            for i in range(self._dirs_list.count())
        ]
        self._settings.update(
            {
                "curseforge_api_key": self._cf_key_edit.text().strip(),
                "default_mc_version": self._mc_version_combo.currentText(),
                "default_mod_loader": self._loader_combo.currentText(),
                "preferred_api": self._api_combo.currentText(),
                "auto_update_check": self._auto_update_cb.isChecked(),
                "backup_before_update": self._backup_cb.isChecked(),
                "max_backups": self._max_backups_spin.value(),
                "download_threads": self._threads_spin.value(),
                "minecraft_dirs": minecraft_dirs,
            }
        )
        QMessageBox.information(self, "Settings", "Settings saved successfully.")

    def _reset(self) -> None:
        from config.settings import DEFAULT_SETTINGS
        self._settings.update(DEFAULT_SETTINGS)
        self._load_values()
        QMessageBox.information(self, "Settings", "Settings reset to defaults.")

    def _browse_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Minecraft Directory",
            "",
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks,
        )
        if not folder:
            return
        existing = [
            self._dirs_list.item(i).text()
            for i in range(self._dirs_list.count())
        ]
        if folder in existing:
            QMessageBox.information(self, "Custom Directories", "That directory is already in the list.")
            return
        self._dirs_list.addItem(folder)

    def _remove_dir(self) -> None:
        selected = self._dirs_list.selectedItems()
        if not selected:
            return
        for item in selected:
            self._dirs_list.takeItem(self._dirs_list.row(item))
