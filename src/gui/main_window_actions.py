from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QFileDialog, QMessageBox

from database.models import Branch, Mango
from gui.branch_dialog import BranchDialog
from gui.certificate_dialog import CertificateDialog
from gui.export_dialog import ExportDialog
from gui.main_window_shared import ROLE_ID, ROLE_TYPE
from gui.mango_dialog import MangoDialog
from gui.plain_text import message_text
from gui.spreadsheet import write_list_xlsx
from openvpn.addressing import ValidationError


class MainWindowActionsMixin:
    def _selected_branch_id(self) -> int | None:
        item = self._selected_item()
        if item is None:
            return None
        if item.data(0, ROLE_TYPE) == "branch":
            return item.data(0, ROLE_ID)
        parent = item.parent()
        return parent.data(0, ROLE_ID) if parent else None

    def _selected_mango_id(self) -> int | None:
        rows = self.device_table.selectedItems()
        if rows:
            return rows[0].data(0, ROLE_ID)
        item = self._selected_item()
        return (
            item.data(0, ROLE_ID)
            if item and item.data(0, ROLE_TYPE) == "mango"
            else None
        )

    def _branch(self, branch_id: int | None) -> Branch | None:
        return next(
            (branch for branch in self.database.list_branches() if branch.id == branch_id),
            None,
        )

    def _mango(self, mango_id: int | None) -> Mango | None:
        return next(
            (mango for mango in self.database.list_mangos() if mango.id == mango_id),
            None,
        )

    def _show_validation(self, exc: Exception) -> None:
        QMessageBox.warning(self, self.t("validation_error"), message_text(self.t.error(exc)))

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
            QMessageBox.information(
                self, self.t("edit_branch"), message_text(self.t("select_branch_first"))
            )
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
            QMessageBox.information(
                self, self.t("delete_branch"), message_text(self.t("select_branch_first"))
            )
            return
        answer = QMessageBox.question(
            self,
            self.t("confirm_delete"),
            message_text(self.t("delete_branch_question", branch.branch_number)),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer == QMessageBox.Yes and branch.id is not None:
            self.database.delete_branch(branch.id)
            self.reload_tree()

    def add_mango(self) -> None:
        branches = self.database.list_branches()
        if not branches:
            QMessageBox.information(
                self, self.t("add_mango"), message_text(self.t("select_branch_first"))
            )
            return
        dialog = MangoDialog(
            self.t,
            branches,
            initial_branch_id=self._selected_branch_id(),
            parent=self,
        )
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
            QMessageBox.information(
                self, self.t("edit_mango"), message_text(self.t("select_mango_first"))
            )
            return
        dialog = MangoDialog(
            self.t, self.database.list_branches(), mango=mango, parent=self
        )
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
            QMessageBox.information(
                self, self.t("delete_mango"), message_text(self.t("select_mango_first"))
            )
            return
        answer = QMessageBox.question(
            self,
            self.t("confirm_delete"),
            message_text(self.t("delete_mango_question", mango.name)),
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
            self,
            self.t("export_list"),
            "OpenVPNManager.xlsx",
            self.t("xlsx_filter"),
            options=QFileDialog.DontConfirmOverwrite,
        )
        if not filename:
            return
        path = Path(filename)
        if path.suffix.lower() != ".xlsx":
            path = Path(str(path) + ".xlsx")
        overwrite = path.exists()
        if overwrite and QMessageBox.question(
            self,
            self.t("export_list"),
            message_text(self.t("xlsx_replace", path)),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        headers = [
            self.tree.headerItem().text(column)
            for column in range(self.tree.columnCount())
        ]
        rows = []
        for index in range(self.tree.topLevelItemCount()):
            branch = self.tree.topLevelItem(index)
            for child_index in range(branch.childCount()):
                child = branch.child(child_index)
                row = [child.text(column) for column in range(self.tree.columnCount())]
                row[1] = branch.text(1)
                rows.append(row)
        try:
            write_list_xlsx(
                path, headers, rows, self.t("branches_mangos"), overwrite=overwrite
            )
        except Exception as exc:
            QMessageBox.warning(
                self, self.t("export_list"), message_text(self.t("xlsx_error", exc))
            )
            return
        QMessageBox.information(
            self, self.t("export_list"), message_text(self.t("xlsx_saved", path))
        )

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
        if hasattr(self, "update_controller") and not self.update_controller.can_close():
            event.ignore()
            return
        if hasattr(self, "status_timer"):
            self.status_timer.stop()
        self.database.close()
        super().closeEvent(event)
