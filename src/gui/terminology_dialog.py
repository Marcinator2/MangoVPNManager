"""Edit localized display terms without changing connection identities."""
from __future__ import annotations

from copy import deepcopy

from PySide6.QtWidgets import (
    QBoxLayout,
    QComboBox,
    QDialog,
    QGridLayout,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from config.terminology import FORMS, ROLES, normalize_terminology, validate_term
from gui.i18n import Translator
from gui.plain_text import PlainLabel as QLabel
from gui.sizing import button_row_fits, resize_dialog_to_content


class TerminologyDialog(QDialog):
    def __init__(self, translate: Translator, terminology, parent=None):
        super().__init__(parent)
        self._t = translate
        self._draft = deepcopy(normalize_terminology(terminology))
        self._language = translate.language
        self.setWindowTitle(translate("terminology_title"))
        layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setObjectName("terminologyScroll")
        scroll.setWidgetResizable(True)
        content = QWidget()
        content.setObjectName("terminologyContent")
        body = QVBoxLayout(content)
        help_label = QLabel(translate("terminology_help"))
        help_label.setWordWrap(True)
        body.addWidget(help_label)
        body.addWidget(QLabel(translate("terminology_language")))
        self.language_combo = QComboBox()
        self.language_combo.addItem(translate("english"), "en")
        self.language_combo.addItem(translate("german"), "de")
        self.language_combo.setCurrentIndex(self.language_combo.findData(self._language))
        body.addWidget(self.language_combo)
        grid = QGridLayout()
        for column, key in enumerate(("role", "singular", "plural")):
            grid.addWidget(QLabel(translate("terminology_" + key)), 0, column)
        self.fields = {}
        for row, role in enumerate(ROLES, 1):
            label = QLabel(translate("terminology_" + role))
            label.setWordWrap(True)
            grid.addWidget(label, row, 0)
            for column, form in enumerate(FORMS, 1):
                edit = QLineEdit()
                edit.setAccessibleName(label.text() + " / " + translate("terminology_" + form))
                # Do not truncate pasted text: invalid input stays visible for correction.
                edit.textChanged.connect(self._update_preview)
                self.fields[role, form] = edit
                grid.addWidget(edit, row, column)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)
        body.addLayout(grid)
        self.error_label = QLabel(translate("terminology_invalid"))
        self.error_label.setWordWrap(True)
        body.addWidget(self.error_label)
        body.addWidget(QLabel(translate("terminology_preview")))
        self.preview_label = QLabel()
        self.preview_label.setWordWrap(True)
        body.addWidget(self.preview_label)
        body.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)
        self.reset_button = QPushButton(translate("terminology_reset"))
        self.cancel_button = QPushButton(translate("cancel"))
        self.apply_button = QPushButton(translate("terminology_apply"))
        self.apply_button.setObjectName("primaryButton")
        self.apply_button.setDefault(True)
        self.buttons_layout = QBoxLayout(QBoxLayout.LeftToRight)
        for button in (self.reset_button, self.cancel_button, self.apply_button):
            self.buttons_layout.addWidget(button)
        layout.addLayout(self.buttons_layout)
        self.reset_button.clicked.connect(self.reset_language)
        self.cancel_button.clicked.connect(self.reject)
        self.apply_button.clicked.connect(self.accept)
        self.language_combo.currentIndexChanged.connect(self._switch_language)
        self._load_language()
        resize_dialog_to_content(self, minimum_width=660, minimum_height=460)

    def _store_language(self):
        self._draft[self._language] = {
            role: {form: self.fields[role, form].text() for form in FORMS}
            for role in ROLES
        }

    def _load_language(self):
        defaults = Translator(self._language)
        for (role, form), edit in self.fields.items():
            edit.blockSignals(True)
            edit.setText(self._draft.get(self._language, {}).get(role, {}).get(form, ""))
            edit.setPlaceholderText(defaults.term(role, form))
            edit.blockSignals(False)
        self._update_preview()

    def _switch_language(self):
        self._store_language()
        self._language = self.language_combo.currentData()
        self._load_language()

    def _update_preview(self):
        self._store_language()
        valid = True
        for roles in self._draft.values():
            for forms in roles.values():
                for value in forms.values():
                    try:
                        validate_term(value)
                    except ValueError:
                        valid = False
        self.error_label.setVisible(not valid)
        self.apply_button.setEnabled(valid)
        preview = Translator(self._language, self._draft)
        self.preview_label.setText("\n\n".join((
            preview("add_branch") + " · " + preview("add_mango"),
            " · ".join(preview(key) for key in ("all_mangos", "mango_ip", "oven_ip", "oven_gateway")),
            preview("workflow_summary_certificates"),
        )))

    def reset_language(self):
        self._draft.pop(self._language, None)
        self._load_language()

    def value(self):
        self._store_language()
        return normalize_terminology(self._draft)

    def accept(self):
        self._update_preview()
        if self.apply_button.isEnabled():
            super().accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "buttons_layout"):
            buttons = (self.reset_button, self.cancel_button, self.apply_button)
            fits = button_row_fits([button.sizeHint().width() for button in buttons], self.width() - 24)
            self.buttons_layout.setDirection(QBoxLayout.LeftToRight if fits else QBoxLayout.TopToBottom)
