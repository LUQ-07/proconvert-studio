"""Application context: one place that owns the long-lived services."""
from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal

from .. import config
from ..history.db import HistoryDB
from ..localization import Translator
from ..services.logging_setup import install_crash_handler, setup_logging
from ..services.temp_manager import TempManager
from ..settings.store import AppSettings, SettingsStore
from ..utils.paths import default_temp_root

log = logging.getLogger("proconvert.ui")


class AppContext(QObject):
    settings_changed = Signal()      # any setting changed
    language_changed = Signal()      # UI must rebuild (text + direction)
    appearance_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.store = SettingsStore()
        s = self.store.settings
        setup_logging(s.log_level)
        install_crash_handler(s.crash_reports_local)
        self.history = HistoryDB()
        self.temp = TempManager(s.temp_dir or default_temp_root())
        self.temp.ensure()
        self.temp.cleanup_stale()
        self.tr = Translator(s.language)

    @property
    def settings(self) -> AppSettings:
        return self.store.settings

    def update(self, **changes) -> None:
        before = self.store.settings
        after = self.store.update(**changes)
        if after.language != before.language:
            self.tr = Translator(after.language)
            self.language_changed.emit()
        if after.appearance != before.appearance:
            self.appearance_changed.emit()
        if after.log_level != before.log_level:
            logging.getLogger("proconvert").setLevel(after.log_level)
        if after.temp_dir != before.temp_dir:
            self.temp = TempManager(after.temp_dir or default_temp_root())
            self.temp.ensure()
        install_crash_handler(after.crash_reports_local)
        self.settings_changed.emit()

    @property
    def repository_url(self) -> str:
        return config.REPOSITORY_URL
