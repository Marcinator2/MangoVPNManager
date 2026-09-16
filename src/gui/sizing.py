from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QApplication, QDialog


def button_row_fits(
    button_widths: list[int],
    available_width: int,
    *,
    spacing: int = 8,
) -> bool:
    if not button_widths:
        return True
    return sum(button_widths) + spacing * (len(button_widths) - 1) <= available_width


def bounded_dialog_size(
    content_hint: QSize,
    available_size: QSize,
    *,
    minimum_width: int,
    minimum_height: int,
    screen_margin: int = 48,
) -> QSize:
    maximum_width = max(1, available_size.width() - screen_margin)
    maximum_height = max(1, available_size.height() - screen_margin)
    width = min(maximum_width, max(minimum_width, content_hint.width()))
    height = min(maximum_height, max(minimum_height, content_hint.height()))
    return QSize(width, height)


def resize_dialog_to_content(
    dialog: QDialog,
    *,
    minimum_width: int = 460,
    minimum_height: int = 0,
) -> None:
    layout = dialog.layout()
    if layout is not None:
        layout.activate()
    content_hint = dialog.sizeHint()
    screen = dialog.screen() or QApplication.primaryScreen()
    if screen is None:
        dialog.resize(
            max(minimum_width, content_hint.width()),
            max(minimum_height, content_hint.height()),
        )
        return
    dialog.resize(
        bounded_dialog_size(
            content_hint,
            screen.availableGeometry().size(),
            minimum_width=minimum_width,
            minimum_height=minimum_height,
        )
    )
