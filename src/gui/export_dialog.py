from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
)

from config.settings import AppSettings, save_settings
from database.database import Database
from database.models import Mango
from gui.certificate_dialog import CertificateDialog
from gui.export_dialog_actions import ExportDialogActionsMixin
from gui.plain_text import PlainFormLayout as QFormLayout, PlainLabel as QLabel, message_text
from gui.sizing import resize_dialog_to_content
from openvpn.addressing import ValidationError
from openvpn.easyrsa import (
    EasyRSAError,
    grant_openvpn_service_material_access,
    openvpn_service_material_access_ready,
)
from openvpn.exporter import (
    ExportBundle,
    build_export_bundle,
    existing_export_files,
    render_preview,
    write_export,
)
from openvpn.installer import (
    ServerInstallStatus,
    build_server_install_plan,
    inspect_server_installation,
    install_server_files,
    repair_server_file_acls,
    restart_openvpn_service,
)
from openvpn.runtime import discover_openvpn_runtime


class ExportDialog(ExportDialogActionsMixin, QDialog):
    def __init__(
        self,
        translate,
        database: Database,
        settings: AppSettings,
        selected_branch_id: int | None,
        selected_mango_id: int | None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._t = translate
        self.database = database
        self.settings = settings
        self.selected_branch_id = selected_branch_id
        self.selected_mango_id = selected_mango_id
        self.exported = False
        self._original_server_host = settings.vpn_server_host
        self._original_server_port = settings.vpn_server_port
        self.runtime = discover_openvpn_runtime(settings.openvpn_root)
        self.setWindowTitle(self._t("export_title"))

        self.scope_combo = QComboBox()
        self.scope_combo.setMinimumContentsLength(16)
        self.scope_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.scope_combo.addItem(self._t("selected_mango"), "mango")
        self.scope_combo.addItem(self._t("selected_branch"), "branch")
        self.scope_combo.addItem(self._t("all_mangos"), "all")
        if selected_mango_id is None:
            self.scope_combo.model().item(0).setEnabled(False)
            self.scope_combo.setCurrentIndex(1 if selected_branch_id is not None else 2)
        elif selected_branch_id is None:
            self.scope_combo.model().item(1).setEnabled(False)

        self.server_host_edit = QLineEdit(settings.vpn_server_host)
        self.server_host_edit.setPlaceholderText(self._t("vpn_server_host_placeholder"))
        self.server_port_spin = QSpinBox()
        self.server_port_spin.setRange(1, 65535)
        self.server_port_spin.setValue(settings.vpn_server_port)

        self.directory_edit = QLineEdit(settings.last_export_directory)
        browse_button = QPushButton(self._t("browse"))
        browse_button.clicked.connect(self._browse)
        directory_row = QHBoxLayout()
        directory_row.addWidget(self.directory_edit)
        directory_row.addWidget(browse_button)

        form = QFormLayout()
        form.addRow(self._t("scope"), self.scope_combo)
        form.addRow(self._t("vpn_server_host"), self.server_host_edit)
        form.addRow(self._t("vpn_server_port"), self.server_port_spin)
        form.addRow(self._t("directory"), directory_row)

        self.material_status = QLabel()
        self.material_status.setObjectName("exportStatus")
        self.material_status.setWordWrap(True)
        self.manage_certificates_button = QPushButton(
            self._t("manage_certificates")
        )
        self.manage_certificates_button.setObjectName("addButton")
        self.manage_certificates_button.clicked.connect(
            self._manage_certificates
        )
        status_row = QHBoxLayout()
        status_row.addWidget(self.material_status, 1)
        status_row.addWidget(self.manage_certificates_button)

        self.preview_edit = QTextEdit()
        self.preview_edit.setReadOnly(True)
        self.preview_edit.setLineWrapMode(QTextEdit.NoWrap)
        preview_button = QPushButton(self._t("preview"))
        preview_button.setObjectName("addButton")
        preview_button.clicked.connect(self._show_preview)

        self.install_frame = QFrame()
        self.install_frame.setObjectName("installationPanel")
        install_layout = QHBoxLayout(self.install_frame)
        install_layout.setContentsMargins(13, 10, 13, 10)
        install_text_layout = QVBoxLayout()
        install_text_layout.setSpacing(3)
        self.install_title = QLabel(self._t("server_installation_status"))
        self.install_title.setObjectName("installationTitle")
        self.install_status = QLabel()
        self.install_status.setObjectName("installationStatus")
        self.install_status.setWordWrap(True)
        self.install_path = QLabel(str(self.runtime.config_dir))
        self.install_path.setObjectName("installationPath")
        for label in (self.material_status, self.install_title, self.install_status, self.install_path):
            label.setWordWrap(True)
            label.setMinimumWidth(0)
            label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.install_path.setToolTip(message_text(str(self.runtime.config_dir)))
        install_text_layout.addWidget(self.install_title)
        install_text_layout.addWidget(self.install_status)
        install_text_layout.addWidget(self.install_path)
        self.install_button = QPushButton(self._t("install_server"))
        self.install_button.setObjectName("addButton")
        self.install_button.clicked.connect(self._install_server)
        install_layout.addLayout(install_text_layout, 1)
        install_layout.addWidget(self.install_button)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.write_button = buttons.button(QDialogButtonBox.Save)
        self.write_button.setText(self._t("write_export"))
        self.write_button.setObjectName("primaryButton")
        buttons.button(QDialogButtonBox.Cancel).setText(self._t("cancel"))
        buttons.accepted.connect(self._export)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        security_notice = QLabel(self._t("export_security_notice"))
        security_notice.setWordWrap(True)
        layout.addWidget(security_notice)
        layout.addLayout(form)
        layout.addLayout(status_row)
        layout.addWidget(self.install_frame)
        layout.addWidget(preview_button)
        layout.addWidget(self.preview_edit, 1)
        layout.addWidget(buttons)

        self.scope_combo.currentIndexChanged.connect(self._show_preview)
        self.server_host_edit.textChanged.connect(self._show_preview)
        self.server_port_spin.valueChanged.connect(self._show_preview)
        self.directory_edit.textChanged.connect(self._show_preview)
        self._show_preview()
        resize_dialog_to_content(
            self,
            minimum_width=900,
            minimum_height=720,
        )
        if not self.server_host_edit.text().strip():
            self.server_host_edit.setFocus()

    def _selected_mangos(self) -> list[Mango]:
        scope = self.scope_combo.currentData()
        if scope == "all":
            return self.database.list_mangos()
        if scope == "branch" and self.selected_branch_id is not None:
            return self.database.list_mangos(self.selected_branch_id)
        if scope == "mango" and self.selected_mango_id is not None:
            return [
                mango
                for mango in self.database.list_mangos()
                if mango.id == self.selected_mango_id
            ]
        return []

    def _bundle(self) -> ExportBundle:
        mangos = self._selected_mangos()
        if not mangos:
            raise ValidationError(self._t("no_mangos"))
        return build_export_bundle(
            mangos,
            pki_path=self.settings.pki_path,
            server_host=self.server_host_edit.text(),
            server_port=self.server_port_spin.value(),
            openvpn_config_dir=self.runtime.config_dir,
            openvpn_status_path=self.runtime.status_path,
        )

    def _localized_warning(self, warning: str) -> str:
        mapping = {
            "VPN server address is still a placeholder.": self._t(
                "warning_server_host_placeholder"
            ),
            "CA certificate is missing.": self._t("warning_ca_missing"),
            "Server certificate or server private key is missing.": self._t(
                "warning_server_material_missing"
            ),
            "Optional TLS-crypt key is missing; TLS-crypt is omitted.": self._t(
                "warning_tls_key_missing"
            ),
        }
        if warning.startswith("Certificate or private key is missing for "):
            name = warning.removeprefix(
                "Certificate or private key is missing for "
            ).removesuffix(".")
            return self._t("warning_mango_material_missing", name)
        return mapping.get(warning, warning)

    def _show_preview(self, *_args) -> None:
        for field, missing in (
            (
                self.server_host_edit,
                not bool(self.server_host_edit.text().strip()),
            ),
            (
                self.directory_edit,
                not bool(self.directory_edit.text().strip()),
            ),
        ):
            field.setProperty("requiredMissing", missing)
            field.style().unpolish(field)
            field.style().polish(field)

        bundle: ExportBundle | None = None
        try:
            bundle = self._bundle()
            self.preview_edit.setPlainText(render_preview(bundle))
            if bundle.ready_for_export and self.directory_edit.text().strip():
                self.material_status.setText(self._t("export_material_ready"))
                self.material_status.setProperty("status", "ready")
            elif bundle.ready_for_export:
                self.material_status.setText(
                    self._t("export_not_ready", f"• {self._t('export_folder_missing')}")
                )
                self.material_status.setProperty("status", "warning")
            else:
                missing_mangos = [
                    warning.removeprefix(
                        "Certificate or private key is missing for "
                    ).removesuffix(".")
                    for warning in bundle.warnings
                    if warning.startswith(
                        "Certificate or private key is missing for "
                    )
                ]
                details = [
                    self._localized_warning(warning)
                    for warning in bundle.warnings
                    if not warning.startswith(
                        "Certificate or private key is missing for "
                    )
                ]
                if missing_mangos:
                    complete = (
                        len(bundle.mango_ids) - len(missing_mangos)
                    )
                    details.append(
                        self._t("warning_mango_material_summary", complete, len(bundle.mango_ids), ", ".join(missing_mangos))
                    )
                self.material_status.setText(
                    self._t("export_not_ready", "\n".join(f"• {detail}" for detail in details))
                )
                self.material_status.setProperty("status", "warning")
        except ValidationError as exc:
            self.preview_edit.setPlainText(self._t.error(exc))
            self.material_status.setText(self._t.error(exc))
            self.material_status.setProperty("status", "warning")
        self.material_status.style().unpolish(self.material_status)
        self.material_status.style().polish(self.material_status)
        self._update_export_button(bundle)

    def _update_export_button(
        self,
        bundle: ExportBundle | None = None,
    ) -> None:
        ready = (
            bundle is not None
            and bundle.ready_for_export
            and bool(self.directory_edit.text().strip())
        )
        self.write_button.setEnabled(ready)
        self.write_button.setToolTip(
            message_text("" if ready else self._t("export_disabled_hint"))
        )
        self._update_installation_panel(bundle)
        certificate_warning = (
            bundle is None
            or any(
                warning == "CA certificate is missing."
                or warning
                == "Server certificate or server private key is missing."
                or warning.startswith(
                    "Certificate or private key is missing for "
                )
                for warning in bundle.warnings
            )
        )
        self.manage_certificates_button.setVisible(certificate_warning)
