"""Display editable terms as literal text in Qt's auto-rich-text surfaces."""
from __future__ import annotations

from html import escape

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFormLayout, QLabel


def message_text(text: str) -> str:
    """Preserve line breaks while preventing user text from becoming HTML."""
    return "<qt>" + escape(str(text)).replace("\n", "<br>") + "</qt>"


class PlainLabel(QLabel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setTextFormat(Qt.PlainText)


class PlainFormLayout(QFormLayout):
    def addRow(self, *args):
        if args and isinstance(args[0], str):
            label = PlainLabel(args[0])
            label.setWordWrap(True)
            args = (label, *args[1:])
        super().addRow(*args)
