"""Main application window."""

import sys
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from apis.curseforge_api import CurseForgeAPI
from apis.modrinth_api import ModrinthAPI
from config.settings import Settings
from core.event_bus import get_event_bus
from core.mod_manager import ModManager
from core.profile_manager import ProfileManager
from gui.installation_manager import InstallationManagerPanel
from gui.mod_browser import ModBrowserPanel
from gui.profile_manager_gui import ProfileManagerPanel
from gui.settings_panel import SettingsPanel
from utils.constants import APP_NAME, APP_VERSION
from utils.logger import get_logger

logger = get_logger("main_window")


class MainWindow(QMainWindow):
    """Top-level application window."""

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self._settings = settings
        self._event_bus = get_event_bus()
        self._init_services()
        self._build_ui()
        self._apply_theme()
        logger.info("MainWindow initialised")

    # ------------------------------------------------------------------
    # Service layer
    # ------------------------------------------------------------------

    def _init_services(self) -> None:
        cf_key = self._settings.get("curseforge_api_key", "")
        modrinth_api = ModrinthAPI()
        curseforge_api = CurseForgeAPI(api_key=cf_key)

        self._mod_manager = ModManager(
            modrinth_api=modrinth_api,
            curseforge_api=curseforge_api,
            max_backups=self._settings.get("max_backups", 5),
        )
        self._profile_manager = ProfileManager()

    # ------------------------------------------------------------------
    # Build UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.setMinimumSize(1000, 700)

        self._tabs = QTabWidget()
        self.setCentralWidget(self._tabs)

        # Mod Browser tab
        self._browser_panel = ModBrowserPanel(
            manager=self._mod_manager,
            settings=self._settings,
            event_bus=self._event_bus,
        )
        self._tabs.addTab(self._browser_panel, "🔍 Mod Browser")

        # Installation Manager tab
        self._install_panel = InstallationManagerPanel(
            manager=self._mod_manager,
            settings=self._settings,
            event_bus=self._event_bus,
        )
        self._tabs.addTab(self._install_panel, "🎮 Installations")

        # Profile Manager tab
        self._profile_panel = ProfileManagerPanel(
            profile_manager=self._profile_manager,
            mod_manager=self._mod_manager,
            settings=self._settings,
            event_bus=self._event_bus,
        )
        self._tabs.addTab(self._profile_panel, "📦 Profiles")

        # Settings tab
        self._settings_panel = SettingsPanel(
            settings=self._settings,
            event_bus=self._event_bus,
        )
        self._tabs.addTab(self._settings_panel, "⚙ Settings")

        # Status bar
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage(f"{APP_NAME} ready.")

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def _apply_theme(self) -> None:
        theme = self._settings.get("theme", "dark")
        if theme == "dark":
            self.setStyleSheet(
                """
                QMainWindow, QWidget {
                    background-color: #2b2b2b;
                    color: #f0f0f0;
                }
                QTabWidget::pane {
                    border: 1px solid #555;
                }
                QTabBar::tab {
                    background: #3c3c3c;
                    color: #ccc;
                    padding: 6px 14px;
                    border-radius: 4px 4px 0 0;
                }
                QTabBar::tab:selected {
                    background: #555;
                    color: #fff;
                }
                QPushButton {
                    background-color: #4a7c59;
                    color: white;
                    border: none;
                    padding: 6px 12px;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #5a9c69;
                }
                QPushButton:disabled {
                    background-color: #555;
                    color: #888;
                }
                QLineEdit, QTextEdit, QComboBox, QSpinBox {
                    background-color: #3c3c3c;
                    color: #f0f0f0;
                    border: 1px solid #666;
                    border-radius: 3px;
                    padding: 3px;
                }
                QListWidget, QTableWidget {
                    background-color: #333;
                    color: #f0f0f0;
                    border: 1px solid #555;
                    alternate-background-color: #3a3a3a;
                }
                QHeaderView::section {
                    background-color: #444;
                    color: #ccc;
                    border: none;
                    padding: 4px;
                }
                QGroupBox {
                    border: 1px solid #555;
                    border-radius: 4px;
                    margin-top: 8px;
                    padding-top: 4px;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 8px;
                    color: #aaa;
                }
                QProgressBar {
                    border: 1px solid #555;
                    border-radius: 3px;
                    text-align: center;
                    color: white;
                }
                QProgressBar::chunk {
                    background-color: #4a7c59;
                }
                QStatusBar {
                    background-color: #222;
                    color: #aaa;
                }
                """
            )
