from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout

from gui.main_window_shared import ROLE_ID, ROLE_TYPE
from openvpn.easyrsa import EasyRSAPaths, EasyRSAService


class MainWindowWorkflowMixin:
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
            service.certificate_status(mango.name).complete for mango in mangos
        )
        server_ready = service.server_material_status().complete
        config_count = sum(mango.config_created for mango in mangos)
        return mangos, pki_status, certificate_count, server_ready, config_count

    def _update_workflow(self) -> None:
        mangos, pki_status, certificate_count, server_ready, config_count = (
            self._workflow_state()
        )
        total = len(mangos)
        steps_complete = (
            total > 0,
            total > 0
            and pki_status.ca_ready
            and certificate_count == total
            and server_ready,
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
        host_text = self.settings.vpn_server_host.strip() or self.t("not_configured")
        self._workflow_lines = (
            self.t("workflow_step_mangos").format(markers[0], total),
            self.t("workflow_step_certificates").format(
                markers[1], ca_text, certificate_count, total, server_text
            ),
            self.t("workflow_step_server").format(markers[2], host_text),
            self.t("workflow_step_export").format(markers[3], config_count, total),
        )
        if not self.database.list_branches():
            summary_key, button_key = "workflow_summary_branch", "workflow_action_branch"
        elif not mangos:
            summary_key, button_key = "workflow_summary_mango", "workflow_action_mango"
        elif not steps_complete[1]:
            summary_key = "workflow_summary_certificates"
            button_key = "workflow_action_certificates"
        elif not steps_complete[2]:
            summary_key, button_key = "workflow_summary_server", "workflow_action_server"
        elif not steps_complete[3]:
            summary_key, button_key = "workflow_summary_export", "workflow_action_export"
        else:
            summary_key, button_key = "workflow_summary_complete", "workflow_action_update"
        self.workflow_summary_label.setText(self.t(summary_key))
        self.next_step_button.setText(self.t(button_key))
        self.workflow_frame.setVisible(not all(steps_complete))

    def show_setup(self) -> None:
        self._update_workflow()
        dialog = QDialog(self)
        dialog.setWindowTitle(self.t("workflow_title"))
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        title = QLabel(self.t("workflow_title"))
        title.setObjectName("dialogTitle")
        steps = QLabel("\n".join(self._workflow_lines))
        steps.setWordWrap(True)
        summary = QLabel(self.workflow_summary_label.text())
        summary.setObjectName("guidanceLabel")
        summary.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(steps)
        layout.addWidget(summary)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        next_button = buttons.addButton(
            self.next_step_button.text(), QDialogButtonBox.ActionRole
        )
        next_button.setObjectName("primaryButton")
        next_button.clicked.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.resize(610, 300)
        if dialog.exec() == QDialog.Accepted:
            self._run_next_workflow_step()

    def _run_next_workflow_step(self) -> None:
        mangos, pki_status, certificate_count, server_ready, _ = self._workflow_state()
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
        self.edit_button.setEnabled(branch_selected or mango_selected)
        self.delete_branch_action.setEnabled(branch_selected)
        self.add_mango_button.setEnabled(has_branches)
        self.delete_mango_action.setEnabled(mango_selected)
        self.export_button.setEnabled(has_mangos)
        self.xlsx_action.setEnabled(has_branches)

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

    def _select_all_mangos(self) -> None:
        self._syncing_selection = True
        try:
            self.tree.clearSelection()
            self.tree.setCurrentItem(None)
        finally:
            self._syncing_selection = False
        self.all_mangos_button.setChecked(True)
        self._populate_device_table(None)
        self._update_action_states()
        self._refresh_runtime_status()

    def _tree_selection_changed(self) -> None:
        if self._syncing_selection:
            return
        item = self._selected_item()
        branch_id = self._selected_branch_id()
        mango_id = (
            item.data(0, ROLE_ID)
            if item is not None and item.data(0, ROLE_TYPE) == "mango"
            else None
        )
        self._populate_device_table(branch_id, mango_id)
        self._update_action_states()
        self._refresh_runtime_status()

    def _table_selection_changed(self) -> None:
        if self._syncing_selection:
            return
        rows = self.device_table.selectedItems()
        mango_id = rows[0].data(0, ROLE_ID) if rows else None
        tree_item = self._mango_items.get(mango_id)
        if tree_item is not None:
            self._syncing_selection = True
            try:
                self.tree.clearSelection()
                tree_item.parent().setExpanded(True)
                self.tree.setCurrentItem(tree_item)
                tree_item.setSelected(True)
            finally:
                self._syncing_selection = False
        self._update_action_states()
        self._update_selection_status()

    def _update_selection_status(self) -> None:
        mango = self._mango(self._selected_mango_id())
        branch = self._branch(self._selected_branch_id())
        if mango is not None:
            self.selection_status_label.setText(mango.name)
        elif branch is not None:
            self.selection_status_label.setText(branch.branch_number)
        else:
            self.selection_status_label.setText(self.t("all_mangos"))
