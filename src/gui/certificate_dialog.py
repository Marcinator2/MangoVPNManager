from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
)

from config.settings import AppSettings
from database.database import Database
from database.models import Mango
from gui.sizing import button_row_fits, resize_dialog_to_content
from openvpn.easyrsa import (
    EasyRSAError,
    EasyRSAPaths,
    EasyRSAResult,
    EasyRSAService,
)


class CertificateDialog(QDialog):
    def __init__(
        self,
        translate,
        database: Database,
        settings: AppSettings,
        selected_mango_id: int | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._t = translate
        self.database = database
        self.settings = settings
        self.service = EasyRSAService(
            EasyRSAPaths(
                openvpn_root=settings.openvpn_root,
                easyrsa_root=settings.easyrsa_root,
                pki_path=settings.pki_path,
            )
        )
        self.setWindowTitle(self._t("certificate_management"))

        self.installation_value = QLabel()
        self.version_value = QLabel()
        self.pki_value = QLabel()
        self.ca_value = QLabel()
        self.server_material_value = QLabel()
        self.path_value = QLabel(str(settings.pki_path))
        self.path_value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        for value_label in (
            self.installation_value,
            self.version_value,
            self.pki_value,
            self.ca_value,
            self.server_material_value,
            self.path_value,
        ):
            value_label.setWordWrap(True)
            value_label.setMinimumWidth(0)
            value_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

        status_form = QFormLayout()
        status_form.addRow(self._t("easyrsa_installation"), self.installation_value)
        status_form.addRow(self._t("easyrsa_version"), self.version_value)
        status_form.addRow(self._t("pki_directory"), self.path_value)
        status_form.addRow(self._t("pki_status"), self.pki_value)
        status_form.addRow(self._t("ca_status"), self.ca_value)
        status_form.addRow(
            self._t("server_material_status"),
            self.server_material_value,
        )

        self.guidance_label = QLabel()
        self.guidance_label.setObjectName("guidanceLabel")
        self.guidance_label.setWordWrap(True)

        self.mango_combo = QComboBox()
        for mango in self.database.list_mangos():
            self.mango_combo.addItem(mango.name, mango.id)
        if selected_mango_id is not None:
            index = self.mango_combo.findData(selected_mango_id)
            if index >= 0:
                self.mango_combo.setCurrentIndex(index)
        self.mango_status_value = QLabel()
        self.mango_status_value.setWordWrap(True)
        self.mango_status_value.setSizePolicy(
            QSizePolicy.Ignored,
            QSizePolicy.Preferred,
        )
        mango_form = QFormLayout()
        mango_form.addRow(self._t("mango"), self.mango_combo)
        mango_form.addRow(self._t("certificate_status"), self.mango_status_value)

        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setMaximumHeight(120)
        self.output = QTextEdit()
        self.output.setReadOnly(True)

        self.refresh_button = QPushButton(self._t("refresh"))
        self.reset_button = QPushButton(self._t("reset_pki"))
        self.initialize_button = QPushButton(self._t("initialize_ca"))
        self.create_server_button = QPushButton(self._t("create_server_material"))
        self.create_all_button = QPushButton(self._t("create_all_certificates"))
        self.create_button = QPushButton(self._t("create_certificate"))
        self.reset_button.setObjectName("dangerButton")
        self.initialize_button.setObjectName("dangerButton")
        self.create_server_button.setObjectName("addButton")
        self.create_all_button.setObjectName("primaryButton")
        self.create_all_button.setDefault(True)
        self.create_all_button.setAutoDefault(True)
        self.create_button.setObjectName("addButton")
        self.create_button.setAutoDefault(False)
        self.refresh_button.clicked.connect(self.refresh)
        self.reset_button.clicked.connect(self.reset_pki)
        self.initialize_button.clicked.connect(self.initialize_ca)
        self.create_server_button.clicked.connect(self.create_server_material)
        self.create_all_button.clicked.connect(self.create_all_certificates)
        self.create_button.clicked.connect(self.create_certificate)
        self.mango_combo.currentIndexChanged.connect(self.refresh)

        maintenance_layout = QHBoxLayout()
        maintenance_layout.addWidget(self.refresh_button)
        maintenance_layout.addStretch()
        maintenance_layout.addWidget(self.reset_button)
        maintenance_layout.addWidget(self.initialize_button)

        for button in (
            self.create_server_button,
            self.create_button,
            self.create_all_button,
        ):
            button.setMinimumWidth(button.sizeHint().width())

        certificate_layout = QVBoxLayout()
        certificate_layout.setSpacing(8)
        server_action_row = QHBoxLayout()
        server_action_row.addWidget(self.create_server_button)
        server_action_row.addStretch()
        certificate_layout.addLayout(server_action_row)

        screen = self.screen() or QApplication.primaryScreen()
        available_action_width = (
            max(1, screen.availableGeometry().width() - 96)
            if screen is not None
            else 1000
        )
        mango_button_widths = [
            self.create_button.minimumWidth(),
            self.create_all_button.minimumWidth(),
        ]
        if button_row_fits(mango_button_widths, available_action_width):
            mango_action_layout = QHBoxLayout()
            mango_action_layout.addStretch()
            mango_action_layout.addWidget(self.create_button)
            mango_action_layout.addWidget(self.create_all_button)
        else:
            mango_action_layout = QVBoxLayout()
            mango_action_layout.addWidget(self.create_button)
            mango_action_layout.addWidget(self.create_all_button)
        certificate_layout.addLayout(mango_action_layout)

        close_buttons = QDialogButtonBox(QDialogButtonBox.Close)
        close_buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(status_form)
        layout.addWidget(self.guidance_label)
        layout.addSpacing(8)
        layout.addLayout(mango_form)
        layout.addWidget(QLabel(self._t("command_preview")))
        layout.addWidget(self.preview)
        layout.addWidget(QLabel(self._t("operation_output")))
        layout.addWidget(self.output, 1)
        layout.addLayout(maintenance_layout)
        layout.addLayout(certificate_layout)
        layout.addWidget(close_buttons)
        self.refresh()
        resize_dialog_to_content(
            self,
            minimum_width=760,
            minimum_height=620,
        )

    def _selected_mango(self) -> Mango | None:
        mango_id = self.mango_combo.currentData()
        return next(
            (mango for mango in self.database.list_mangos() if mango.id == mango_id),
            None,
        )

    def _missing_mangos(self) -> list[Mango]:
        missing: list[Mango] = []
        for mango in self.database.list_mangos():
            certificate = self.service.certificate_status(mango.name)
            if not certificate.certificate_exists and not certificate.private_key_exists:
                missing.append(mango)
        return missing

    def refresh(self) -> None:
        status = self.service.status()
        self.installation_value.setText(
            self._t("ready") if status.installation_ready else self._t("not_ready")
        )
        if status.installation_ready:
            try:
                self.version_value.setText(self.service.version())
            except EasyRSAError:
                self.version_value.setText(self._t("unknown"))
        else:
            self.version_value.setText(self._t("unknown"))
        self.pki_value.setText(
            self._t("initialized") if status.pki_initialized else self._t("not_initialized")
        )
        self.ca_value.setText(
            self._t("ready") if status.ca_ready else self._t("not_initialized")
        )
        server_material = self.service.server_material_status()
        self.server_material_value.setText(
            self._t("server_material_complete")
            if server_material.complete
            else self._t("server_material_missing")
        )

        mango = self._selected_mango()
        if mango is None:
            self.mango_status_value.setText(self._t("no_mangos"))
            self.preview.clear()
            self.create_button.setEnabled(False)
        else:
            certificate = self.service.certificate_status(mango.name)
            self.database.set_certificate_created(mango.id or 0, certificate.complete)
            self.mango_status_value.setText(
                self._t("certificate_complete")
                if certificate.complete
                else self._t("certificate_missing")
            )
            self.preview.setPlainText(self.service.command_preview("client", mango.name))
            self.create_button.setEnabled(
                status.ca_ready
                and server_material.complete
                and not certificate.complete
            )

        self.initialize_button.setEnabled(
            status.installation_ready
            and not status.ca_certificate_exists
            and not status.ca_key_exists
        )
        self.reset_button.setEnabled(
            status.pki_initialized
            or status.ca_certificate_exists
            or status.ca_key_exists
        )
        self.create_server_button.setEnabled(
            status.ca_ready and not server_material.complete
        )
        missing_mangos = self._missing_mangos()
        self.create_all_button.setEnabled(
            status.ca_ready
            and server_material.complete
            and bool(missing_mangos)
        )

        if not status.installation_ready:
            guidance = self._t("certificate_next_install")
        elif not status.ca_ready:
            guidance = self._t("certificate_next_ca")
        elif not server_material.complete:
            guidance = self._t("certificate_next_server")
        elif missing_mangos:
            guidance = self._t("certificate_next_mangos").format(
                len(missing_mangos)
            )
        else:
            guidance = self._t("certificate_all_ready")
        self.guidance_label.setText(guidance)

    def _run_busy(self, operation) -> None:
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            result = operation()
        except EasyRSAError as exc:
            QMessageBox.critical(self, self._t("certificate_error"), str(exc))
            self.refresh()
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.output.setPlainText(result.output or self._t("operation_successful"))
        self.refresh()

    def reset_pki(self) -> None:
        answer = QMessageBox.warning(
            self,
            self._t("reset_pki"),
            self._t("reset_pki_question").format(self.settings.pki_path),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        phrase, accepted = QInputDialog.getText(
            self,
            self._t("reset_pki"),
            self._t("reset_pki_phrase"),
        )
        if not accepted:
            return
        if phrase.strip() != "RESET PKI":
            QMessageBox.warning(
                self,
                self._t("reset_pki"),
                self._t("reset_pki_phrase_mismatch"),
            )
            return

        def reset_and_sync() -> EasyRSAResult:
            result = self.service.reset_pki_to_backup()
            for mango in self.database.list_mangos():
                self.database.set_certificate_created(mango.id or 0, False)
            self.database.reset_config_statuses()
            return result

        self._run_busy(reset_and_sync)

    def initialize_ca(self) -> None:
        preview = self.service.command_preview("initialize")
        answer = QMessageBox.warning(
            self,
            self._t("initialize_ca"),
            self._t("initialize_ca_question").format(
                self.settings.pki_path,
                preview,
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self._run_busy(
            lambda: self.service.initialize_ca(
                common_name="MangoVPNManager-CA",
                validity_days=3650,
            )
        )

    def create_server_material(self) -> None:
        preview = self.service.command_preview("server")
        answer = QMessageBox.warning(
            self,
            self._t("create_server_material"),
            self._t("create_server_material_question").format(preview),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        def create_and_invalidate() -> EasyRSAResult:
            result = self.service.create_server_material()
            self.database.reset_config_statuses()
            return result

        self._run_busy(create_and_invalidate)

    def create_all_certificates(self) -> None:
        mangos = self._missing_mangos()
        if not mangos:
            return
        names = "\n".join(f"• {mango.name}" for mango in mangos)
        answer = QMessageBox.question(
            self,
            self._t("create_all_certificates"),
            self._t("create_all_certificates_question").format(
                len(mangos),
                names,
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        def create_all() -> EasyRSAResult:
            outputs: list[str] = []
            for mango in mangos:
                result = self.service.create_client_certificate(
                    mango.name,
                    validity_days=825,
                )
                if mango.id is not None:
                    self.database.reset_config_statuses([mango.id])
                outputs.append(f"{mango.name}: OK\n{result.output}")
            return EasyRSAResult("\n\n".join(outputs))

        self._run_busy(create_all)

    def create_certificate(self) -> None:
        mango = self._selected_mango()
        if mango is None:
            return
        answer = QMessageBox.question(
            self,
            self._t("create_certificate"),
            self._t("create_certificate_question").format(mango.name),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        def create_and_invalidate() -> EasyRSAResult:
            result = self.service.create_client_certificate(
                mango.name,
                validity_days=825,
            )
            if mango.id is not None:
                self.database.reset_config_statuses([mango.id])
            return result

        self._run_busy(create_and_invalidate)
