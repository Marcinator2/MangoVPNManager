from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QTreeWidgetItem

from database.models import Mango
from gui.main_window_shared import NORMAL_STATUS_INTERVAL_MS, ROLE_ID, ROLE_TYPE
from gui.plain_text import message_text
from gui.theme import theme_color


class MainWindowRuntimeMixin:
    def reload_tree(self) -> None:
        self._sync_certificate_statuses()
        selected_branch_id = self._scope_branch_id
        selected_mango_id = self._selected_mango_id()
        expanded_ids = {
            item.data(0, ROLE_ID)
            for index in range(self.tree.topLevelItemCount())
            if (item := self.tree.topLevelItem(index)).isExpanded()
        }
        branches = self.database.list_branches()
        mangos = self.database.list_mangos()
        self.tree.clear()
        self._mango_items.clear()
        branch_items = {}
        mangos_by_branch: dict[int, list[Mango]] = {}
        for mango in mangos:
            mangos_by_branch.setdefault(mango.branch_id, []).append(mango)
        for branch in branches:
            branch_mangos = mangos_by_branch.get(branch.id, [])
            branch_title = f"({len(branch_mangos)}) {branch.branch_number}"
            if branch.description:
                branch_title += f" - {branch.description}"
            branch_item = QTreeWidgetItem(
                [branch_title, branch.description]
                + [""] * 12
            )
            branch_item.setData(0, ROLE_TYPE, "branch")
            branch_item.setData(0, ROLE_ID, branch.id)
            branch_item.setToolTip(0, message_text(branch.description))
            if branch.id is not None:
                branch_items[branch.id] = branch_item
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
                mango_item = QTreeWidgetItem(self._mango_row(mango, branch.description))
                mango_item.setData(0, ROLE_TYPE, "mango")
                mango_item.setData(0, ROLE_ID, mango.id)
                if mango.id is not None:
                    self._mango_items[mango.id] = mango_item
                self._color_readiness(mango_item, mango)
                branch_item.addChild(mango_item)
            branch_item.setExpanded(branch.id in expanded_ids)
        self.tree.resizeColumnToContents(0)

        self._syncing_selection = True
        try:
            if selected_mango_id in self._mango_items:
                item = self._mango_items[selected_mango_id]
                item.setSelected(True)
                item.parent().setExpanded(True)
                self.tree.setCurrentItem(item)
            elif selected_branch_id in branch_items:
                item = branch_items[selected_branch_id]
                item.setSelected(True)
                self.tree.setCurrentItem(item)
            else:
                selected_branch_id = None
                selected_mango_id = None
        finally:
            self._syncing_selection = False
        self._populate_device_table(selected_branch_id, selected_mango_id)
        self._update_action_states()
        self._update_workflow()
        self._refresh_runtime_status()

    def _mango_row(self, mango: Mango, description: str) -> list[str]:
        return [
            mango.name,
            description,
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

    def _color_readiness(
        self, item: QTreeWidgetItem, mango: Mango, certificate_column: int = 8
    ) -> None:
        for column, ready in (
            (certificate_column, mango.certificate_created),
            (certificate_column + 1, mango.config_created),
        ):
            item.setForeground(
                column,
                QBrush(
                    QColor(
                        theme_color(
                            self.settings.theme, "ready" if ready else "pending"
                        )
                    )
                ),
            )
            item.setTextAlignment(column, Qt.AlignCenter)

    def _populate_device_table(
        self, branch_id: int | None, selected_mango_id: int | None = None
    ) -> None:
        self._scope_branch_id = branch_id
        self.all_mangos_button.setChecked(branch_id is None)
        branches = {branch.id: branch for branch in self.database.list_branches()}
        mangos = self.database.list_mangos(branch_id)
        self.device_table.setSortingEnabled(False)
        self.device_table.clear()
        self._device_items.clear()
        selected_item = None
        for mango in mangos:
            branch = branches.get(mango.branch_id)
            item = QTreeWidgetItem([
                mango.name,
                branch.branch_number if branch else mango.branch_number,
                branch.description if branch else "",
                str(branch.internal_id) if branch else "",
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
            ])
            item.setData(0, ROLE_TYPE, "mango")
            item.setData(0, ROLE_ID, mango.id)
            self._color_readiness(item, mango, 10)
            item.setTextAlignment(12, Qt.AlignCenter)
            if mango.id is not None:
                self._device_items[mango.id] = item
                if mango.id == selected_mango_id:
                    selected_item = item
            self.device_table.addTopLevelItem(item)
        self.device_table.setSortingEnabled(True)
        if selected_item is not None:
            self._syncing_selection = True
            try:
                self.device_table.setCurrentItem(selected_item)
                selected_item.setSelected(True)
            finally:
                self._syncing_selection = False
        self.count_status_label.setText(
            self.t("branch_device_count", len(self.database.list_branches()), len(self.database.list_mangos()))
        )
        self._update_selection_status()

    @staticmethod
    def _format_time(value: datetime | None) -> str:
        return value.astimezone().strftime("%d.%m.%Y %H:%M:%S") if value else ""

    @staticmethod
    def _format_stored_time(value: str) -> str:
        if not value:
            return ""
        try:
            return MainWindowRuntimeMixin._format_time(datetime.fromisoformat(value))
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
        # Keep these lookups on gui.main_window so tests and the synthetic
        # screenshot tool can replace the productive Windows probes.
        from gui import main_window as main_window_module

        service_running = main_window_module.openvpn_service_running(
            self.runtime.service_name
        )
        snapshot = main_window_module.read_status_snapshot(self.runtime.status_path)
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
            key = "server_config_unreadable" if config_unreadable else "server_status_stale"
            self._set_server_indicator("offline", self.t(key))
        else:
            self._set_server_indicator("unknown", self.t("server_status_unknown"))

        connected_ids = []
        for mango in self.database.list_mangos():
            if mango.id is None:
                continue
            connection = snapshot.connections.get(mango.name.casefold()) if healthy else None
            if connection is not None:
                state, status_text = "online", self.t("connected")
                connected_since = self._format_time(connection.connected_since)
                remote_address = connection.remote_address
                last_seen = self._format_time(snapshot.updated_at)
                connected_ids.append(mango.id)
            elif healthy:
                state, status_text = "offline", self.t("disconnected")
                connected_since, remote_address = "", ""
                last_seen = self._format_stored_time(mango.last_seen_at)
            else:
                state, status_text = "unknown", self.t("unknown")
                connected_since, remote_address = "", ""
                last_seen = self._format_stored_time(mango.last_seen_at)
            color_name = {"online": "ready", "offline": "offline", "unknown": "pending"}[state]
            tree_item = self._mango_items.get(mango.id)
            if tree_item is not None:
                self._set_connection_cells(
                    tree_item, 10, status_text, connected_since,
                    remote_address, last_seen, color_name,
                )
            device_item = self._device_items.get(mango.id)
            if device_item is not None:
                self._set_connection_cells(
                    device_item, 12, status_text, connected_since,
                    remote_address, last_seen, color_name,
                )
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

    def _set_connection_cells(
        self, item, column: int, status_text: str, connected_since: str,
        remote_address: str, last_seen: str, color_name: str,
    ) -> None:
        item.setText(column, f"●  {status_text}")
        item.setText(column + 1, connected_since)
        item.setText(column + 2, remote_address)
        item.setText(column + 3, last_seen)
        item.setForeground(
            column, QBrush(QColor(theme_color(self.settings.theme, color_name)))
        )
        item.setTextAlignment(column, Qt.AlignCenter)
