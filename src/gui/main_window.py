from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QBrush, QCloseEvent, QColor, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from config.settings import AppSettings, resource_path, save_settings
from config.version import read_build_info
from gui.update_controller import UpdateController
from database.database import Database
from database.models import Branch, Mango
from gui.branch_dialog import BranchDialog
from gui.certificate_dialog import CertificateDialog
from gui.export_dialog import ExportDialog
from gui.i18n import Translator
from gui.mango_dialog import MangoDialog
from gui.spreadsheet import write_list_xlsx
from gui.theme import apply_theme, theme_color
from openvpn.addressing import ValidationError
from openvpn.easyrsa import EasyRSAPaths, EasyRSAService
from openvpn.runtime import (
    discover_openvpn_runtime,
    openvpn_service_running,
    read_status_snapshot,
)


ROLE_TYPE = Qt.UserRole
ROLE_ID = Qt.UserRole + 1
STARTUP_STATUS_INTERVAL_MS = 1000
NORMAL_STATUS_INTERVAL_MS = 5000
STARTUP_STATUS_POLL_COUNT = 10


class MainWindow(QMainWindow):
    def __init__(self, database: Database, settings: AppSettings) -> None:
        super().__init__()
        self.database = database
        self.settings = settings
        self.build_info = read_build_info()
        self.translator = Translator(settings.language)
        self.runtime = discover_openvpn_runtime(settings.openvpn_root)
        self._mango_items: dict[int, QTreeWidgetItem] = {}
        self._last_seen_write: datetime | None = None
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

    def _build_ui(self) -> None:
        self.tree = QTreeWidget()
        self.tree.setObjectName("mainTree")
        self.tree.setColumnCount(14)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.setAlternatingRowColors(True)
        self.tree.itemDoubleClicked.connect(self._edit_selected)
        self.tree.itemSelectionChanged.connect(self._update_action_states)

        self.add_branch_button = QPushButton()
        self.edit_branch_button = QPushButton()
        self.delete_branch_button = QPushButton()
        self.add_mango_button = QPushButton()
        self.edit_mango_button = QPushButton()
        self.delete_mango_button = QPushButton()
        self.certificate_button = QPushButton()
        self.export_button = QPushButton()
        self.xlsx_button = QPushButton()
        self.xlsx_button.clicked.connect(self.export_list)
        self.add_branch_button.setObjectName("addButton")
        self.add_mango_button.setObjectName("addButton")
        self.delete_branch_button.setObjectName("dangerButton")
        self.delete_mango_button.setObjectName("dangerButton")
        self.certificate_button.setObjectName("addButton")
        self.export_button.setObjectName("primaryButton")
        self.add_branch_button.clicked.connect(self.add_branch)
        self.edit_branch_button.clicked.connect(self.edit_branch)
        self.delete_branch_button.clicked.connect(self.delete_branch)
        self.add_mango_button.clicked.connect(self.add_mango)
        self.edit_mango_button.clicked.connect(self.edit_mango)
        self.delete_mango_button.clicked.connect(self.delete_mango)
        self.certificate_button.clicked.connect(self.manage_certificates)
        self.export_button.clicked.connect(self.export_configs)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)
        for button in (
            self.add_branch_button,
            self.edit_branch_button,
            self.delete_branch_button,
            self.add_mango_button,
            self.edit_mango_button,
            self.delete_mango_button,
        ):
            button_layout.addWidget(button)
        button_layout.addStretch()
        button_layout.addWidget(self.certificate_button)
        button_layout.addWidget(self.export_button)

        self.header = QFrame()
        self.header.setObjectName("brandHeader")
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(18, 14, 18, 14)
        header_layout.setSpacing(14)

        logo_label = QLabel()
        logo_label.setObjectName("logoTile")
        logo_label.setFixedSize(72, 72)
        logo_label.setAlignment(Qt.AlignCenter)
        logo = QPixmap(str(resource_path("icons", "mb-soft.png")))
        if not logo.isNull():
            logo_label.setPixmap(
                logo.scaled(68, 68, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        header_layout.addWidget(logo_label)

        title_layout = QVBoxLayout()
        title_layout.setSpacing(2)
        self.brand_title_label = QLabel()
        self.brand_title_label.setObjectName("brandTitle")
        self.brand_subtitle_label = QLabel()
        self.brand_subtitle_label.setObjectName("brandSubtitle")
        title_layout.addWidget(self.brand_title_label)
        title_layout.addWidget(self.brand_subtitle_label)
        title_layout.addStretch()
        header_layout.addLayout(title_layout)
        header_layout.addStretch()

        self.notice_label = QLabel()
        self.notice_label.setObjectName("safetyBadge")
        self.notice_label.setWordWrap(True)
        self.notice_label.setMaximumWidth(390)
        header_layout.addWidget(self.notice_label)

        self.workflow_frame = QFrame()
        self.workflow_frame.setObjectName("workflowPanel")
        workflow_layout = QVBoxLayout(self.workflow_frame)
        workflow_layout.setContentsMargins(16, 12, 16, 12)
        workflow_layout.setSpacing(6)
        self.workflow_title_label = QLabel()
        self.workflow_title_label.setObjectName("workflowTitle")
        self.workflow_summary_label = QLabel()
        self.workflow_summary_label.setObjectName("workflowSummary")
        self.workflow_steps_label = QLabel()
        self.workflow_steps_label.setObjectName("workflowSteps")
        self.workflow_steps_label.setWordWrap(True)
        self.next_step_button = QPushButton()
        self.next_step_button.setObjectName("primaryButton")
        self.next_step_button.setMinimumWidth(210)
        self.next_step_button.clicked.connect(self._run_next_workflow_step)

        workflow_layout.addWidget(self.workflow_title_label)
        workflow_layout.addWidget(self.workflow_summary_label)
        workflow_bottom = QHBoxLayout()
        workflow_bottom.addWidget(self.workflow_steps_label, 1)
        workflow_bottom.addWidget(self.next_step_button)
        workflow_layout.addLayout(workflow_bottom)

        self.runtime_frame = QFrame()
        self.runtime_frame.setObjectName("runtimePanel")
        runtime_layout = QHBoxLayout(self.runtime_frame)
        runtime_layout.setContentsMargins(14, 9, 14, 9)
        self.server_status_title = QLabel()
        self.server_status_title.setObjectName("runtimeTitle")
        self.server_status_value = QLabel()
        self.server_status_value.setObjectName("runtimeStatus")
        self.server_status_value.setProperty("state", "unknown")
        self.status_path_label = QLabel()
        self.status_path_label.setObjectName("runtimePath")
        self.status_path_label.setText(str(self.runtime.status_path))
        self.status_path_label.setToolTip(str(self.runtime.status_path))
        runtime_layout.addWidget(self.server_status_title)
        runtime_layout.addWidget(self.server_status_value)
        runtime_layout.addStretch()
        runtime_layout.addWidget(self.status_path_label, 1)

        central_layout = QVBoxLayout()
        central_layout.setContentsMargins(22, 18, 22, 22)
        central_layout.setSpacing(14)
        central_layout.addWidget(self.header)
        central_layout.addWidget(self.workflow_frame)
        central_layout.addWidget(self.runtime_frame)
        central_layout.addLayout(button_layout)
        list_actions = QHBoxLayout()
        list_actions.addStretch()
        list_actions.addWidget(self.xlsx_button)
        central_layout.addLayout(list_actions)
        central_layout.addWidget(self.tree, 1)
        central = QWidget()
        central.setLayout(central_layout)
        self.setCentralWidget(central)

        self.language_menu = self.menuBar().addMenu("")
        group = QActionGroup(self)
        group.setExclusive(True)
        self.english_action = QAction("English", self, checkable=True)
        self.german_action = QAction("Deutsch", self, checkable=True)
        self.english_action.setData("en")
        self.german_action.setData("de")
        for action in (self.english_action, self.german_action):
            group.addAction(action)
            self.language_menu.addAction(action)
            action.triggered.connect(lambda checked, a=action: self.set_language(a.data()))

        self.appearance_menu = self.menuBar().addMenu("")
        theme_group = QActionGroup(self)
        theme_group.setExclusive(True)
        self.light_theme_action = QAction("", self, checkable=True)
        self.dark_theme_action = QAction("", self, checkable=True)
        self.light_theme_action.setData("light")
        self.dark_theme_action.setData("dark")
        for action in (self.light_theme_action, self.dark_theme_action):
            theme_group.addAction(action)
            self.appearance_menu.addAction(action)
            action.triggered.connect(lambda checked, a=action: self.set_theme(a.data()))

        self._update_shadows()
        self.resize(1250, 700)

    def _retranslate(self) -> None:
        self.setWindowTitle(f'{self.t("app_title")} — {self.build_info.version}')
        if hasattr(self, "update_controller"):
            self.update_controller.retranslate()
        self.brand_title_label.setText(self.t("app_title"))
        self.brand_subtitle_label.setText(self.t("app_subtitle"))
        self.add_branch_button.setText(self.t("add_branch"))
        self.edit_branch_button.setText(self.t("edit_branch"))
        self.delete_branch_button.setText(self.t("delete_branch"))
        self.add_mango_button.setText(self.t("add_mango"))
        self.edit_mango_button.setText(self.t("edit_mango"))
        self.delete_mango_button.setText(self.t("delete_mango"))
        self.certificate_button.setText(self.t("certificates"))
        self.export_button.setText(self.t("export"))
        self.xlsx_button.setText(self.t("export_list"))
        self.notice_label.setText(self.t("phase1_notice"))
        self.server_status_title.setText(self.t("server_live_status"))
        self.workflow_title_label.setText(self.t("workflow_title"))
        self.language_menu.setTitle(self.t("language"))
        self.appearance_menu.setTitle(self.t("appearance"))
        self.light_theme_action.setText(self.t("light_theme"))
        self.dark_theme_action.setText(self.t("dark_theme"))
        self.tree.setHeaderLabels(
            [
                self.t("name"),
                self.t("description"),
                self.t("vpn_ip"),
                self.t("lan_network"),
                self.t("mango_ip"),
                self.t("oven_ip"),
                self.t("oven_subnet_mask"),
                self.t("oven_gateway"),
                self.t("certificate"),
                self.t("configuration"),
                self.t("connection"),
                self.t("connected_since"),
                self.t("remote_ip"),
                self.t("last_seen"),
            ]
        )
        self.english_action.setChecked(self.settings.language == "en")
        self.german_action.setChecked(self.settings.language == "de")
        self.light_theme_action.setChecked(self.settings.theme == "light")
        self.dark_theme_action.setChecked(self.settings.theme == "dark")

    def _update_shadows(self) -> None:
        shadow_color = QColor(theme_color(self.settings.theme, "shadow"))
        for widget, blur, vertical_offset in (
            (self.header, 24, 5),
            (self.tree, 16, 3),
        ):
            effect = QGraphicsDropShadowEffect(widget)
            effect.setBlurRadius(blur)
            effect.setOffset(0, vertical_offset)
            effect.setColor(shadow_color)
            widget.setGraphicsEffect(effect)

    def set_theme(self, theme: str) -> None:
        if theme not in {"light", "dark"}:
            return
        self.settings.theme = theme
        application = QApplication.instance()
        if application is not None:
            apply_theme(application, theme)
        self._update_shadows()
        save_settings(self.settings)
        self._retranslate()
        self.reload_tree()

    def set_language(self, language: str) -> None:
        self.settings.language = language
        self.translator.set_language(language)
        save_settings(self.settings)
        self._retranslate()
        self.reload_tree()

    def reload_tree(self) -> None:
        self._sync_certificate_statuses()
        expanded_ids = {
            item.data(0, ROLE_ID)
            for index in range(self.tree.topLevelItemCount())
            if (item := self.tree.topLevelItem(index)).isExpanded()
        }
        self.tree.clear()
        self._mango_items.clear()
        mangos_by_branch: dict[int, list[Mango]] = {}
        for mango in self.database.list_mangos():
            mangos_by_branch.setdefault(mango.branch_id, []).append(mango)
        for branch in self.database.list_branches():
            branch_mangos = mangos_by_branch.get(branch.id, [])
            branch_item = QTreeWidgetItem(
                [
                    f"({len(branch_mangos)}) {branch.branch_number}",
                    branch.description,
                    *([""] * 12),
                ]
            )
            branch_item.setData(0, ROLE_TYPE, "branch")
            branch_item.setData(0, ROLE_ID, branch.id)
            for column in range(self.tree.columnCount()):
                branch_item.setBackground(
                    column,
                    QBrush(QColor(theme_color(self.settings.theme, "branch"))),
                )
                font = branch_item.font(column)
                font.setBold(True)
                branch_item.setFont(column, font)
            self.tree.addTopLevelItem(branch_item)
            for mango in branch_mangos:
                mango_item = QTreeWidgetItem(
                    [
                        mango.name,
                        "",
                        mango.vpn_ip,
                        mango.lan_network,
                        mango.mango_ip,
                        mango.oven_ip,
                        mango.oven_subnet_mask,
                        mango.oven_gateway,
                        self.t("yes") if mango.certificate_created else self.t("no"),
                        self.t("yes") if mango.config_created else self.t("no"),
                        self.t("unknown"),
                        "",
                        "",
                        self._format_stored_time(mango.last_seen_at),
                    ]
                )
                mango_item.setData(0, ROLE_TYPE, "mango")
                mango_item.setData(0, ROLE_ID, mango.id)
                if mango.id is not None:
                    self._mango_items[mango.id] = mango_item
                for column, ready in (
                    (8, mango.certificate_created),
                    (9, mango.config_created),
                ):
                    mango_item.setForeground(
                        column,
                        QBrush(
                            QColor(
                                theme_color(
                                    self.settings.theme,
                                    "ready" if ready else "pending",
                                )
                            )
                        ),
                    )
                    mango_item.setTextAlignment(column, Qt.AlignCenter)
                branch_item.addChild(mango_item)
            branch_item.setExpanded(branch.id in expanded_ids)
        for column in range(self.tree.columnCount()):
            self.tree.resizeColumnToContents(column)
        self._update_action_states()
        self._update_workflow()
        self._refresh_runtime_status()

    @staticmethod
    def _format_time(value: datetime | None) -> str:
        return value.astimezone().strftime("%d.%m.%Y %H:%M:%S") if value else ""

    @staticmethod
    def _format_stored_time(value: str) -> str:
        if not value:
            return ""
        try:
            return MainWindow._format_time(datetime.fromisoformat(value))
        except ValueError:
            return ""

    def _set_server_indicator(self, state: str, text: str) -> None:
        self.server_status_value.setText(f"●  {text}")
        self.server_status_value.setProperty("state", state)
        self.server_status_value.style().unpolish(self.server_status_value)
        self.server_status_value.style().polish(self.server_status_value)

    def _poll_runtime_status(self) -> None:
        self._refresh_runtime_status()
        if self._startup_status_checks_remaining <= 0:
            return
        self._startup_status_checks_remaining -= 1
        if self._startup_status_checks_remaining == 0:
            self.status_timer.setInterval(NORMAL_STATUS_INTERVAL_MS)

    def _refresh_runtime_status(self) -> None:
        service_running = openvpn_service_running(self.runtime.service_name)
        snapshot = read_status_snapshot(self.runtime.status_path)
        healthy = service_running is True and snapshot.fresh
        if healthy:
            self._set_server_indicator("online", self.t("server_running"))
        elif service_running is False:
            self._set_server_indicator("offline", self.t("server_stopped"))
        elif service_running is True:
            server_config = self.runtime.config_dir / "server.ovpn"
            try:
                with server_config.open("rb") as handle:
                    handle.read(1)
                config_unreadable = False
            except PermissionError:
                config_unreadable = True
            except OSError:
                config_unreadable = False
            self._set_server_indicator(
                "offline",
                self.t(
                    "server_config_unreadable"
                    if config_unreadable
                    else "server_status_stale"
                ),
            )
        else:
            self._set_server_indicator("unknown", self.t("server_status_unknown"))

        mangos = self.database.list_mangos()
        connected_ids: list[int] = []
        for mango in mangos:
            if mango.id is None or mango.id not in self._mango_items:
                continue
            item = self._mango_items[mango.id]
            connection = snapshot.connections.get(mango.name.casefold()) if healthy else None
            if connection is not None:
                state = "online"
                status_text = self.t("connected")
                item.setText(11, self._format_time(connection.connected_since))
                item.setText(12, connection.remote_address)
                item.setText(13, self._format_time(snapshot.updated_at))
                connected_ids.append(mango.id)
            elif healthy:
                state = "offline"
                status_text = self.t("disconnected")
                item.setText(11, "")
                item.setText(12, "")
                item.setText(13, self._format_stored_time(mango.last_seen_at))
            else:
                state = "unknown"
                status_text = self.t("unknown")
                item.setText(11, "")
                item.setText(12, "")
                item.setText(13, self._format_stored_time(mango.last_seen_at))
            item.setText(10, f"●  {status_text}")
            color_name = {
                "online": "ready",
                "offline": "offline",
                "unknown": "pending",
            }[state]
            item.setForeground(10, QBrush(QColor(theme_color(self.settings.theme, color_name))))
            item.setTextAlignment(10, Qt.AlignCenter)

        now = datetime.now().astimezone()
        should_store = (
            connected_ids
            and snapshot.updated_at is not None
            and (
                self._last_seen_write is None
                or (now - self._last_seen_write).total_seconds() >= 30
            )
        )
        if should_store:
            self.database.mark_mangos_seen(connected_ids, snapshot.updated_at.isoformat())
            self._last_seen_write = now

    def _workflow_state(self):
        mangos = self.database.list_mangos()
        service = EasyRSAService(
            EasyRSAPaths(
                self.settings.openvpn_root,
                self.settings.easyrsa_root,
                self.settings.pki_path,
            )
        )
        pki_status = service.status()
        certificate_count = sum(
            service.certificate_status(mango.name).complete
            for mango in mangos
        )
        server_ready = service.server_material_status().complete
        config_count = sum(mango.config_created for mango in mangos)
        return (
            mangos,
            pki_status,
            certificate_count,
            server_ready,
            config_count,
        )

    def _update_workflow(self) -> None:
        (
            mangos,
            pki_status,
            certificate_count,
            server_ready,
            config_count,
        ) = self._workflow_state()
        total = len(mangos)
        steps_complete = (
            total > 0,
            (
                total > 0
                and pki_status.ca_ready
                and certificate_count == total
                and server_ready
            ),
            bool(self.settings.vpn_server_host.strip()),
            total > 0 and config_count == total,
        )
        try:
            active_step = steps_complete.index(False)
        except ValueError:
            active_step = 3

        markers = [
            "✓" if complete else ("➜" if index == active_step else "○")
            for index, complete in enumerate(steps_complete)
        ]
        ca_text = self.t("ready") if pki_status.ca_ready else self.t("not_ready")
        server_text = self.t("ready") if server_ready else self.t("not_ready")
        host_text = (
            self.settings.vpn_server_host
            if self.settings.vpn_server_host.strip()
            else self.t("not_configured")
        )
        lines = (
            self.t("workflow_step_mangos").format(markers[0], total),
            self.t("workflow_step_certificates").format(
                markers[1],
                ca_text,
                certificate_count,
                total,
                server_text,
            ),
            self.t("workflow_step_server").format(markers[2], host_text),
            self.t("workflow_step_export").format(
                markers[3],
                config_count,
                total,
            ),
        )
        self.workflow_steps_label.setText("\n".join(lines))

        if not self.database.list_branches():
            summary_key = "workflow_summary_branch"
            button_key = "workflow_action_branch"
        elif not mangos:
            summary_key = "workflow_summary_mango"
            button_key = "workflow_action_mango"
        elif not steps_complete[1]:
            summary_key = "workflow_summary_certificates"
            button_key = "workflow_action_certificates"
        elif not steps_complete[2]:
            summary_key = "workflow_summary_server"
            button_key = "workflow_action_server"
        elif not steps_complete[3]:
            summary_key = "workflow_summary_export"
            button_key = "workflow_action_export"
        else:
            summary_key = "workflow_summary_complete"
            button_key = "workflow_action_update"
        self.workflow_summary_label.setText(self.t(summary_key))
        self.next_step_button.setText(self.t(button_key))

    def _run_next_workflow_step(self) -> None:
        mangos, pki_status, certificate_count, server_ready, _ = (
            self._workflow_state()
        )
        if not self.database.list_branches():
            self.add_branch()
        elif not mangos:
            self.add_mango()
        elif (
            not pki_status.ca_ready
            or certificate_count != len(mangos)
            or not server_ready
        ):
            self.manage_certificates()
        else:
            self.export_configs()

    def _update_action_states(self) -> None:
        item = self._selected_item()
        selected_type = item.data(0, ROLE_TYPE) if item is not None else None
        has_branches = bool(self.database.list_branches())
        has_mangos = bool(self.database.list_mangos())
        branch_selected = selected_type == "branch"
        mango_selected = selected_type == "mango"

        self.edit_branch_button.setEnabled(branch_selected)
        self.delete_branch_button.setEnabled(branch_selected)
        self.add_mango_button.setEnabled(has_branches)
        self.edit_mango_button.setEnabled(mango_selected)
        self.delete_mango_button.setEnabled(mango_selected)
        self.export_button.setEnabled(has_mangos)
        self.xlsx_button.setEnabled(has_branches)

    def _sync_certificate_statuses(self) -> None:
        service = EasyRSAService(
            EasyRSAPaths(
                self.settings.openvpn_root,
                self.settings.easyrsa_root,
                self.settings.pki_path,
            )
        )
        for mango in self.database.list_mangos():
            complete = service.certificate_status(mango.name).complete
            if mango.id is not None and mango.certificate_created != complete:
                self.database.set_certificate_created(mango.id, complete)

    def _selected_item(self):
        items = self.tree.selectedItems()
        return items[0] if items else None

    def _selected_branch_id(self) -> int | None:
        item = self._selected_item()
        if item is None:
            return None
        if item.data(0, ROLE_TYPE) == "branch":
            return item.data(0, ROLE_ID)
        parent = item.parent()
        return parent.data(0, ROLE_ID) if parent else None

    def _selected_mango_id(self) -> int | None:
        item = self._selected_item()
        return item.data(0, ROLE_ID) if item and item.data(0, ROLE_TYPE) == "mango" else None

    def _branch(self, branch_id: int | None) -> Branch | None:
        return next((branch for branch in self.database.list_branches() if branch.id == branch_id), None)

    def _mango(self, mango_id: int | None) -> Mango | None:
        return next((mango for mango in self.database.list_mangos() if mango.id == mango_id), None)

    def _show_validation(self, exc: Exception) -> None:
        QMessageBox.warning(self, self.t("validation_error"), str(exc))

    def add_branch(self) -> None:
        dialog = BranchDialog(self.t, parent=self)
        if dialog.exec():
            value = dialog.value()
            try:
                self.database.add_branch_with_mangos(
                    value.branch_number,
                    dialog.mango_count(),
                    description=value.description,
                )
            except ValidationError as exc:
                self._show_validation(exc)
                return
            self.reload_tree()

    def edit_branch(self) -> None:
        branch = self._branch(self._selected_branch_id())
        if branch is None:
            QMessageBox.information(self, self.t("edit_branch"), self.t("select_branch_first"))
            return
        dialog = BranchDialog(self.t, branch, self)
        if dialog.exec():
            try:
                self.database.update_branch(dialog.value())
            except ValidationError as exc:
                self._show_validation(exc)
                return
            self.reload_tree()

    def delete_branch(self) -> None:
        branch = self._branch(self._selected_branch_id())
        if branch is None:
            QMessageBox.information(self, self.t("delete_branch"), self.t("select_branch_first"))
            return
        answer = QMessageBox.question(
            self,
            self.t("confirm_delete"),
            self.t("delete_branch_question").format(branch.branch_number),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer == QMessageBox.Yes and branch.id is not None:
            self.database.delete_branch(branch.id)
            self.reload_tree()

    def add_mango(self) -> None:
        branches = self.database.list_branches()
        if not branches:
            QMessageBox.information(self, self.t("add_mango"), self.t("select_branch_first"))
            return
        dialog = MangoDialog(self.t, branches, initial_branch_id=self._selected_branch_id(), parent=self)
        if dialog.exec():
            branch_id, number = dialog.value()
            try:
                self.database.add_mango(branch_id, number)
            except ValidationError as exc:
                self._show_validation(exc)
                return
            self.reload_tree()

    def edit_mango(self) -> None:
        mango = self._mango(self._selected_mango_id())
        if mango is None:
            QMessageBox.information(self, self.t("edit_mango"), self.t("select_mango_first"))
            return
        dialog = MangoDialog(self.t, self.database.list_branches(), mango=mango, parent=self)
        if dialog.exec():
            branch_id, number = dialog.value()
            try:
                self.database.update_mango(mango.id or 0, branch_id, number)
            except ValidationError as exc:
                self._show_validation(exc)
                return
            self.reload_tree()

    def delete_mango(self) -> None:
        mango = self._mango(self._selected_mango_id())
        if mango is None:
            QMessageBox.information(self, self.t("delete_mango"), self.t("select_mango_first"))
            return
        answer = QMessageBox.question(
            self,
            self.t("confirm_delete"),
            self.t("delete_mango_question").format(mango.name),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer == QMessageBox.Yes and mango.id is not None:
            self.database.delete_mango(mango.id)
            self.reload_tree()

    def manage_certificates(self) -> None:
        dialog = CertificateDialog(
            self.t,
            self.database,
            self.settings,
            self._selected_mango_id(),
            self,
        )
        dialog.exec()
        self.reload_tree()

    def export_list(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(
            self, self.t("export_list"), "OpenVPNManager.xlsx",
            self.t("xlsx_filter"), options=QFileDialog.DontConfirmOverwrite,
        )
        if not filename:
            return
        path = Path(filename)
        if path.suffix.lower() != ".xlsx":
            path = Path(str(path) + ".xlsx")
        overwrite = path.exists()
        if overwrite and QMessageBox.question(
            self, self.t("export_list"), self.t("xlsx_replace").format(path),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        headers = [self.tree.headerItem().text(c) for c in range(self.tree.columnCount())]
        rows = []
        for index in range(self.tree.topLevelItemCount()):
            branch = self.tree.topLevelItem(index)
            for child_index in range(branch.childCount()):
                child = branch.child(child_index)
                row = [child.text(c) for c in range(self.tree.columnCount())]
                row[1] = branch.text(1)
                rows.append(row)
        try:
            write_list_xlsx(path, headers, rows, self.t("branches_mangos"), overwrite=overwrite)
        except Exception as exc:
            QMessageBox.warning(self, self.t("export_list"), self.t("xlsx_error").format(exc))
            return
        QMessageBox.information(self, self.t("export_list"), self.t("xlsx_saved").format(path))

    def export_configs(self) -> None:
        dialog = ExportDialog(
            self.t,
            self.database,
            self.settings,
            self._selected_branch_id(),
            self._selected_mango_id(),
            self,
        )
        dialog.exec()
        self.reload_tree()

    def _edit_selected(self) -> None:
        item = self._selected_item()
        if item is None:
            return
        if item.data(0, ROLE_TYPE) == "mango":
            self.edit_mango()
        else:
            self.edit_branch()

    def closeEvent(self, event: QCloseEvent) -> None:
        if hasattr(self, 'update_controller') and not self.update_controller.can_close():
            event.ignore()
            return
        if hasattr(self, "status_timer"):
            self.status_timer.stop()
        self.database.close()
        super().closeEvent(event)
