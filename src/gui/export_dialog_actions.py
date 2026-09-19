from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMessageBox

from config.settings import save_settings
from gui.certificate_dialog import CertificateDialog
from openvpn.addressing import ValidationError
from openvpn.easyrsa import (
    EasyRSAError,
    grant_openvpn_service_material_access,
    openvpn_service_material_access_ready,
)
from openvpn.exporter import existing_export_files, write_export
from openvpn.installer import (
    ServerInstallStatus,
    build_server_install_plan,
    inspect_server_installation,
    install_server_files,
    repair_server_file_acls,
    restart_openvpn_service,
)


class ExportDialogActionsMixin:
    def _update_installation_panel(self, bundle: ExportBundle | None) -> None:
        state = "neutral"
        button_text = self._t("install_server")
        button_enabled = False
        tooltip = self._t("install_server_disabled_hint")
        if self.scope_combo.currentData() != "all":
            text = self._t("install_status_select_all")
        elif bundle is None or not bundle.ready_for_export:
            state = "warning"
            text = self._t("install_status_not_ready")
        else:
            try:
                plan = build_server_install_plan(bundle, self.runtime.config_dir)
                status = self._inspect_server_installation(plan)
            except (ValidationError, OSError) as exc:
                text = self._t("install_status_unknown").format(exc)
            else:
                if status.state == "current":
                    state = "ready"
                    text = self._t("install_status_current").format(
                        status.current_files,
                        status.total_files,
                    )
                    button_text = self._t("installation_current_button")
                    tooltip = self._t("install_status_current_tooltip")
                elif status.state == "not_installed":
                    state = "warning"
                    text = self._t("install_status_missing").format(
                        len(status.missing_files),
                    )
                    button_enabled = True
                    tooltip = ""
                elif status.state == "update_required":
                    state = "warning"
                    text = self._t("install_status_update").format(
                        len(status.changed_files),
                        len(status.missing_files),
                    )
                    button_text = self._t("update_server")
                    button_enabled = True
                    tooltip = ""
                elif status.state == "permissions_repair_required":
                    state = "error"
                    text = self._t("install_status_permissions")
                    button_text = self._t("repair_server_permissions")
                    button_enabled = True
                    tooltip = ""
                else:
                    text = self._t("install_status_unknown").format("")
        self.install_status.setText(f"●  {text}")
        self.install_status.setProperty("status", state)
        self.install_status.style().unpolish(self.install_status)
        self.install_status.style().polish(self.install_status)
        self.install_button.setText(button_text)
        self.install_button.setEnabled(button_enabled)
        self.install_button.setToolTip(tooltip)

    def _inspect_server_installation(self, plan) -> ServerInstallStatus:
        status = inspect_server_installation(plan)
        if (
            status.state == "current"
            and not openvpn_service_material_access_ready(self.settings.pki_path)
        ):
            return ServerInstallStatus(
                state="permissions_repair_required",
                total_files=status.total_files,
                current_files=status.current_files,
                missing_files=status.missing_files,
                changed_files=status.changed_files,
            )
        return status

    def _manage_certificates(self) -> None:
        dialog = CertificateDialog(
            self._t,
            self.database,
            self.settings,
            self.selected_mango_id,
            self,
        )
        dialog.exec()
        self._show_preview()

    def done(self, result: int) -> None:
        host = self.server_host_edit.text().strip()
        port = self.server_port_spin.value()
        export_directory = self.directory_edit.text().strip()
        if (
            host != self._original_server_host
            or port != self._original_server_port
        ):
            self.database.reset_config_statuses()
        self.settings.vpn_server_host = host
        self.settings.vpn_server_port = port
        self.settings.last_export_directory = export_directory
        save_settings(self.settings)
        super().done(result)

    def _browse(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self,
            self._t("choose_export_directory"),
            self.directory_edit.text(),
        )
        if directory:
            self.directory_edit.setText(directory)

    def _export(self) -> None:
        try:
            bundle = self._bundle()
            if not self.directory_edit.text().strip():
                raise ValidationError(self._t("choose_export_directory"))
            if not bundle.ready_for_export:
                QMessageBox.information(
                    self,
                    self._t("export_not_ready_title"),
                    self._t("export_disabled_hint"),
                )
                return
            if bundle.contains_private_keys:
                answer = QMessageBox.warning(
                    self,
                    self._t("sensitive_export_title"),
                    self._t("sensitive_export_question"),
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if answer != QMessageBox.Yes:
                    return
            directory = Path(self.directory_edit.text().strip())
            collisions = existing_export_files(bundle, directory)
            overwrite = False
            if collisions:
                answer = QMessageBox.question(
                    self,
                    self._t("overwrite_title"),
                    self._t("overwrite_question").format(len(collisions)),
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if answer != QMessageBox.Yes:
                    return
                overwrite = True
            written = write_export(bundle, directory, overwrite=overwrite)
            host = self.server_host_edit.text().strip()
            port = self.server_port_spin.value()
            if (
                host != self._original_server_host
                or port != self._original_server_port
            ):
                self.database.reset_config_statuses()
            self.database.mark_configs_created(list(bundle.complete_mango_ids))
            self.settings.last_export_directory = str(directory.resolve())
            self.settings.vpn_server_host = host
            self.settings.vpn_server_port = port
            self._original_server_host = host
            self._original_server_port = port
            save_settings(self.settings)
        except (ValidationError, FileExistsError, OSError) as exc:
            QMessageBox.critical(self, self._t("export_failed"), str(exc))
            return
        self.exported = True
        message = self._t("export_complete_text").format(len(written))
        if bundle.warnings:
            message += "\n\n" + self._t("export_complete_warning")
        QMessageBox.information(
            self,
            self._t("export_complete"),
            message,
        )
        self.accept()

    def _persist_server_settings(self) -> None:
        host = self.server_host_edit.text().strip()
        port = self.server_port_spin.value()
        if host != self._original_server_host or port != self._original_server_port:
            self.database.reset_config_statuses()
        self.settings.vpn_server_host = host
        self.settings.vpn_server_port = port
        self._original_server_host = host
        self._original_server_port = port
        save_settings(self.settings)

    def _install_server(self) -> None:
        if self.scope_combo.currentData() != "all":
            return
        try:
            bundle = self._bundle()
            plan = build_server_install_plan(bundle, self.runtime.config_dir)
            install_status = self._inspect_server_installation(plan)
        except (ValidationError, OSError, EasyRSAError) as exc:
            QMessageBox.critical(self, self._t("install_failed"), str(exc))
            return

        repair_permissions = (
            install_status.state == "permissions_repair_required"
        )
        if repair_permissions:
            question = self._t("repair_permissions_question").format(
                len(plan.files),
                plan.config_dir,
            )
            title = self._t("repair_server_permissions")
        else:
            question = self._t("install_server_question").format(
                len(plan.files),
                plan.config_dir,
                len(plan.collisions),
            )
            title = self._t("install_server_title")
        answer = QMessageBox.warning(
            self,
            title,
            question,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            if repair_permissions:
                written = repair_server_file_acls(plan)
            else:
                written = install_server_files(
                    plan,
                    replace=bool(plan.collisions),
                )
            grant_openvpn_service_material_access(self.settings.pki_path)
            self._persist_server_settings()
            self.database.mark_configs_created(list(bundle.complete_mango_ids))
        except (ValidationError, FileExistsError, OSError, EasyRSAError) as exc:
            QMessageBox.critical(
                self,
                self._t("install_failed"),
                self._t("install_failed_text").format(exc),
            )
            return

        restart = QMessageBox.question(
            self,
            self._t("restart_service_title"),
            self._t("restart_service_question"),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        restarted = False
        if restart == QMessageBox.Yes:
            try:
                restart_openvpn_service(self.runtime.service_name)
                restarted = True
            except OSError as exc:
                QMessageBox.warning(
                    self,
                    self._t("restart_service_failed"),
                    str(exc),
                )
        if repair_permissions:
            message = self._t("repair_permissions_complete").format(
                len(written),
                plan.config_dir,
            )
        else:
            message = self._t("install_complete_text").format(
                len(written),
                plan.config_dir,
            )
        if restarted:
            message += "\n\n" + self._t("restart_service_complete")
        QMessageBox.information(self, self._t("install_complete"), message)
        self.exported = True
        self.accept()
