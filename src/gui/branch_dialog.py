from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QVBoxLayout,
)

from database.models import Branch
from gui.plain_text import PlainFormLayout as QFormLayout, message_text
from gui.sizing import resize_dialog_to_content
from openvpn.addressing import ValidationError, validate_branch_number


class BranchDialog(QDialog):
    def __init__(self, translate, branch: Branch | None = None, parent=None) -> None:
        super().__init__(parent)
        self._t = translate
        self._branch = branch
        self.setWindowTitle(self._t("edit_branch") if branch else self._t("add_branch"))

        self.number_edit = QLineEdit(branch.branch_number if branch else "")
        self.description_edit = QLineEdit(branch.description if branch else "")

        form = QFormLayout()
        form.addRow(self._t("branch"), self.number_edit)
        form.addRow(self._t("description"), self.description_edit)
        self.mango_count_spin: QSpinBox | None = None
        if branch is None:
            self.mango_count_spin = QSpinBox()
            self.mango_count_spin.setRange(0, 10)
            self.mango_count_spin.setValue(1)
            form.addRow(self._t("mango_count"), self.mango_count_spin)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText(self._t("save"))
        buttons.button(QDialogButtonBox.Cancel).setText(self._t("cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)
        resize_dialog_to_content(self)

    def accept(self) -> None:
        try:
            validate_branch_number(self.number_edit.text())
        except ValidationError as exc:
            QMessageBox.warning(self, self._t("validation_error"), message_text(self._t.error(exc)))
            return
        super().accept()

    def mango_count(self) -> int:
        return self.mango_count_spin.value() if self.mango_count_spin is not None else 0

    def value(self) -> Branch:
        return Branch(
            self._branch.id if self._branch else None,
            self.number_edit.text().strip(),
            self._branch.internal_id if self._branch else 0,
            self.description_edit.text().strip(),
        )

