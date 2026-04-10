#!/usr/bin/env python3
"""Entry point for the Minecraft Mod Manager application."""

import sys
import os

# Ensure the package root is on sys.path when run directly
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

from config.settings import Settings
from gui.main_window import MainWindow
from utils.constants import LOGS_DIR
from utils.logger import setup_logger


def main() -> int:
    # Bootstrap logger
    setup_logger(LOGS_DIR)

    # Load settings
    settings = Settings()

    # Create Qt application
    app = QApplication(sys.argv)
    app.setApplicationName("Minecraft Mod Manager")
    app.setApplicationVersion("1.0.0")
    app.setAttribute(Qt.AA_EnableHighDpiScaling, True)

    # Launch main window
    window = MainWindow(settings=settings)
    window.show()

    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
