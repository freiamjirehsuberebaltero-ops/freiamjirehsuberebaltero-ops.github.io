"""Application-wide event bus for cross-component communication."""

from typing import Optional

from PyQt5.QtCore import QObject, pyqtSignal

from utils.logger import get_logger

logger = get_logger("event_bus")


class EventBus(QObject):
    """Singleton Qt-based signal/event bus.

    Signals
    -------
    mod_installed(mod_name, mod_path)
        Emitted by Mod Browser when a mod is successfully downloaded.
        Installation Manager listens to trigger a refresh; Profile Manager
        listens to auto-add the mod to the active profile.
    mods_updated()
        Emitted by Installation Manager when its list of installed mods
        changes (after scan, removal, or update).  Profile Manager listens
        to refresh its installed-mods view.
    settings_changed(key)
        Emitted whenever a settings value is changed so that dependent
        components can react (e.g. reload mods_directory).
    """

    mod_installed = pyqtSignal(str, str)   # mod_name, mod_path
    mods_updated = pyqtSignal()
    settings_changed = pyqtSignal(str)     # settings key that changed


_instance: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """Return the application-wide EventBus singleton.

    The singleton is created on first call and reused for the lifetime of
    the process.  All Qt signal connections are made in the main thread so
    no additional locking is required.
    """
    global _instance
    if _instance is None:
        _instance = EventBus()
        logger.debug("EventBus singleton created")
    return _instance
