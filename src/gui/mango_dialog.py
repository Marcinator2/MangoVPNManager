from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QMessageBox,
    QSpinBox,
    QVBoxLayout,
)

from database.models import Branch, Mango
from gui.sizing import resize_dialog_to_content
from openvpn.addressing import ValidationError, calculate_addresses


class MangoDialog(QDialog):
    def __init__(
        self,
        translate,
        branches: list[Branch],
        mango: Mango | None = None,
        initial_branch_id: int | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._t = translate
        self._mango = mango
        self._branches = {branch.id: branch for branch in branches}
        self.setWindowTitle(self._t("edit_mango") if mango else self._t("add_mango"))

        self.branch_combo = QComboBox()
        for branch in branches:
            self.branch_combo.addItem(
                f"{branch.branch_number} — {branch.description}".rstrip(" —"), branch.id
            )
        selected_branch_id = mango.branch_id if mango else initial_branch_id
        if selected_branch_id is not None:
            index = self.branch_combo.findData(selected_branch_id)
            if index >= 0:
                self.branch_combo.setCurrentIndex(index)

        self.number_spin = QSpinBox()
        self.number_spin.setRange(1, 10)
        self.number_spin.setValue(mango.mango_number if mango else 1)
        self.preview_labels = {key: QLabel() for key in ("name", "vpn_ip", "lan_network", "mango_ip", "oven_ip")}

        form = QFormLayout()
        form.addRow(self._t("branch"), self.branch_combo)
        form.addRow(self._t("mango_number"), self.number_spin)
        for key, label in self.preview_labels.items():
            form.addRow(self._t(key), label)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText(self._t("save"))
        buttons.button(QDialogButtonBox.Cancel).setText(self._t("cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.branch_combo.currentIndexChanged.connect(self._update_preview)
        self.number_spin.valueChanged.connect(self._update_preview)
        self._update_preview()
        resize_dialog_to_content(self)

    def _update_preview(self) -> None:
        branch = self._branches.get(self.branch_combo.currentData())
        if branch is None:
            for label in self.preview_labels.values():
                label.clear()
            return
        try:
            values = calculate_addresses(branch.branch_number, branch.internal_id, self.number_spin.value())
        except ValidationError:
            return
        for key, label in self.preview_labels.items():
            label.setText(getattr(values, key))

    def accept(self) -> None:
        branch = self._branches.get(self.branch_combo.currentData())
        if branch is None:
            QMessageBox.warning(self, self._t("validation_error"), self._t("select_branch_first"))
            return
        try:
            calculate_addresses(branch.branch_number, branch.internal_id, self.number_spin.value())
        except ValidationError as exc:
            QMessageBox.warning(self, self._t("validation_error"), str(exc))
            return
        super().accept()

    def value(self) -> tuple[int, int]:
        return int(self.branch_combo.currentData()), self.number_spin.value()
