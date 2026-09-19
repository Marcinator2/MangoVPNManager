from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMainWindow

from config.settings import AppSettings
from config.version import read_build_info
from database.database import Database
from gui.i18n import Translator
from gui.main_window_actions import MainWindowActionsMixin
from gui.main_window_runtime import MainWindowRuntimeMixin
from gui.main_window_shared import (
    NORMAL_STATUS_INTERVAL_MS,
    ROLE_ID,
    ROLE_TYPE,
    STARTUP_STATUS_INTERVAL_MS,
    STARTUP_STATUS_POLL_COUNT,
)
from gui.main_window_view import MainWindowViewMixin
from gui.main_window_workflow import MainWindowWorkflowMixin
from gui.update_controller import UpdateController
from openvpn.runtime import (
    discover_openvpn_runtime,
    openvpn_service_running,
    read_status_snapshot,
)


class MainWindow(
    MainWindowViewMixin,
    MainWindowRuntimeMixin,
    MainWindowWorkflowMixin,
    MainWindowActionsMixin,
    QMainWindow,
):
    def __init__(self, database: Database, settings: AppSettings) -> None:
        super().__init__()
        self.database = database
        self.settings = settings
        self.build_info = read_build_info()
        self.translator = Translator(settings.language)
        self.runtime = discover_openvpn_runtime(settings.openvpn_root)
        self._mango_items = {}
        self._device_items = {}
        self._last_seen_write: datetime | None = None
        self._syncing_selection = False
        self._scope_branch_id: int | None = None
        self._build_ui()
        self._retranslate()
        self.reload_tree()
        self._startup_status_checks_remaining = STARTUP_STATUS_POLL_COUNT
        self.status_timer = QTimer(self)
        self.status_timer.setInterval(STARTUP_STATUS_INTERVAL_MS)
        self.status_timer.timeout.connect(self._poll_runtime_status)
        self.status_timer.start()
        self._refresh_runtime_status()
        self.update_controller = UpdateController(self, self.build_info)

    @property
    def t(self):
        return self.translator


__all__ = [
    "MainWindow",
    "NORMAL_STATUS_INTERVAL_MS",
    "ROLE_ID",
    "ROLE_TYPE",
    "STARTUP_STATUS_POLL_COUNT",
]
