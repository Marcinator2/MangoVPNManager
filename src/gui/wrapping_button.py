"""Native-styled buttons with literal, wrapped labels for custom terminology."""
from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QPushButton, QSizePolicy, QStyle, QStyleOptionButton, QStylePainter


class WrappingButton(QPushButton):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        policy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)

    def _text_height(self, width: int) -> int:
        rect = self.fontMetrics().boundingRect(
            QRect(0, 0, max(1, width - 32), 10000),
            Qt.TextWordWrap | Qt.TextWrapAnywhere, self.text(),
        )
        return rect.height() + 18

    def sizeHint(self) -> QSize:
        self.ensurePolished()
        screen = self.screen()
        limit = max(120, screen.availableGeometry().width() - 96) if screen else 700
        width = min(limit, self.fontMetrics().horizontalAdvance(self.text()) + 40)
        return QSize(width, max(super().sizeHint().height(), self._text_height(width)))

    def minimumSizeHint(self) -> QSize:
        return QSize(min(120, self.sizeHint().width()), self.fontMetrics().height() + 18)

    def heightForWidth(self, width: int) -> int:
        return max(super().sizeHint().height(), self._text_height(width))

    def paintEvent(self, event):
        option = QStyleOptionButton()
        self.initStyleOption(option)
        option.text = ""
        painter = QStylePainter(self)
        painter.drawControl(QStyle.CE_PushButton, option)
        rect = self.rect().adjusted(16, 9, -16, -9)
        if self.isDown():
            rect.translate(1, 1)
        group = QPalette.Active if self.isEnabled() else QPalette.Disabled
        painter.setPen(option.palette.color(group, QPalette.ButtonText))
        painter.drawText(rect, Qt.AlignCenter | Qt.TextWordWrap | Qt.TextWrapAnywhere, self.text())
