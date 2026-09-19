from __future__ import annotations

from PySide6.QtWidgets import QInputDialog, QMessageBox

from gui.plain_text import message_text
from openvpn.easyrsa import EasyRSAResult


class CertificateOperationsMixin:
    def reset_pki(self) -> None:
        answer = QMessageBox.warning(
            self,
            self._t("reset_pki"),
            message_text(self._t("reset_pki_question", self.settings.pki_path)),
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
                message_text(self._t("reset_pki_phrase_mismatch")),
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
            message_text(self._t("initialize_ca_question", self.settings.pki_path, preview)),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self._run_busy(
            lambda: self.service.initialize_ca(
                common_name="OpenVPNManager-CA",
                validity_days=3650,
            )
        )

    def create_server_material(self) -> None:
        preview = self.service.command_preview("server")
        answer = QMessageBox.warning(
            self,
            self._t("create_server_material"),
            message_text(self._t("create_server_material_question", preview)),
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
            message_text(self._t("create_all_certificates_question", len(mangos), names)),
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
            message_text(self._t("create_certificate_question", mango.name)),
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
