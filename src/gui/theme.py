from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from gui.theme_palette import PALETTES, normalize_theme, theme_color


def _icon_path(name: str) -> str:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return (base / "icons" / name).as_posix()


def stylesheet(theme: str) -> str:
    theme = normalize_theme(theme)
    colors = PALETTES[theme]
    arrow_tone = "dark" if theme == "light" else "light"
    spin_up = _icon_path(f"spin-up-{arrow_tone}.svg")
    spin_down = _icon_path(f"spin-down-{arrow_tone}.svg")
    return f"""
QWidget {{
    color: {colors["text"]};
    font-family: "Segoe UI";
    font-size: 10pt;
}}
QMainWindow, QDialog {{
    background: {colors["window_top"]};
}}
QScrollArea#terminologyScroll,
QScrollArea#terminologyScroll QWidget#qt_scrollarea_viewport,
QWidget#terminologyContent {{
    color: {colors["text"]};
    background: {colors["surface"]};
}}
QScrollArea#terminologyScroll {{
    border: 1px solid {colors["border"]};
}}
QMenuBar {{
    background: {colors["surface_alt"]};
    border-bottom: 1px solid {colors["border"]};
    padding: 4px 10px;
}}
QMenuBar::item {{
    border-radius: 2px;
    padding: 5px 9px;
}}
QMenuBar::item:selected {{
    background: {colors["surface_hover"]};
    color: #3988ff;
}}
QMenu {{
    background: {colors["surface"]};
    border: 1px solid {colors["border"]};
    padding: 6px;
}}
QMenu::item {{
    border-radius: 2px;
    padding: 6px 28px 6px 9px;
}}
QMenu::item:selected {{
    background: {colors["selection"]};
    color: {colors["selection_text"]};
}}
QFrame#brandHeader {{
    background: {colors["surface_alt"]};
    border: 1px solid {colors["border"]};
    border-radius: 2px;
}}
QFrame#workflowPanel {{
    background: {colors["surface"]};
    border: 1px solid {colors["border"]};
    border-radius: 2px;
}}
QFrame#runtimePanel {{
    background: {colors["surface"]};
    border: 1px solid {colors["border"]};
    border-radius: 10px;
}}
QFrame#installationPanel {{
    background: {colors["surface_alt"]};
    border: 1px solid {colors["border"]};
    border-radius: 3px;
}}
QLabel#installationTitle {{
    color: {colors["text"]};
    font-size: 11pt;
    font-weight: 700;
}}
QLabel#installationPath {{
    color: {colors["muted"]};
    font-size: 9pt;
}}
QLabel#installationStatus[status="ready"] {{
    color: {colors["ready"]};
    font-weight: 600;
}}
QLabel#installationStatus[status="warning"] {{
    color: {colors["warning_text"]};
    font-weight: 600;
}}
QLabel#installationStatus[status="error"] {{
    color: {colors["offline"]};
    font-weight: 700;
}}
QLabel#installationStatus[status="neutral"] {{
    color: {colors["pending"]};
    font-weight: 600;
}}
QLabel#runtimeTitle {{
    color: {colors["text"]};
    font-weight: 700;
}}
QLabel#runtimePath {{
    color: {colors["muted"]};
}}
QLabel#runtimeStatus[state="online"] {{
    color: {colors["ready"]};
    font-weight: 700;
}}
QLabel#runtimeStatus[state="offline"] {{
    color: {colors["offline"]};
    font-weight: 700;
}}
QLabel#runtimeStatus[state="unknown"] {{
    color: {colors["pending"]};
    font-weight: 700;
}}
QLabel#workflowTitle {{
    color: {colors["text"]};
    font-size: 12pt;
    font-weight: 700;
}}
QLabel#workflowSummary {{
    color: #438fff;
    font-weight: 600;
}}
QLabel#workflowSteps {{
    color: {colors["muted"]};
}}
QLabel#guidanceLabel {{
    color: #438fff;
    background: {colors["badge"]};
    border: 1px solid #4676b5;
    border-radius: 3px;
    padding: 8px 10px;
    font-weight: 600;
}}
QLabel#logoTile {{
    background: #ffffff;
    border: 1px solid #c7ccd3;
    border-radius: 10px;
}}
QLabel#brandTitle {{
    color: {colors["text"]};
    font-size: 11pt;
    font-weight: 600;
}}
QLabel#brandSubtitle {{
    color: {colors["muted"]};
    font-size: 10pt;
}}
QLabel#safetyBadge {{
    color: #438fff;
    background: {colors["badge"]};
    border: 1px solid #4676b5;
    border-radius: 9px;
    padding: 7px 11px;
}}
QLabel#exportStatus {{
    color: {colors["text"]};
    background: {colors["surface_alt"]};
    border: 1px solid {colors["border"]};
    border-radius: 3px;
    padding: 8px 10px;
}}
QLabel#exportStatus[status="ready"] {{
    color: {colors["ready"]};
    border-color: {colors["ready"]};
}}
QLabel#exportStatus[status="warning"] {{
    color: {colors["warning_text"]};
    background: {colors["warning_surface"]};
    border-color: {colors["warning_text"]};
}}
QPushButton {{
    color: {colors["text"]};
    background: {colors["surface"]};
    border: 1px solid {colors["border"]};
    border-radius: 3px;
    padding: 5px 10px;
    min-height: 18px;
}}
QPushButton:hover {{
    background: {colors["surface_hover"]};
    border-color: {colors["border_strong"]};
}}
QPushButton:pressed {{
    background: {colors["surface_alt"]};
}}
QPushButton:disabled {{
    color: {colors["disabled_text"]};
    background: {colors["disabled_surface"]};
    border: 1px dashed {colors["disabled_border"]};
}}
QPushButton#primaryButton:disabled,
QPushButton#addButton:disabled,
QPushButton#dangerButton:disabled {{
    color: {colors["disabled_text"]};
    background: {colors["disabled_surface"]};
    border: 1px dashed {colors["disabled_border"]};
    font-weight: 400;
}}
QPushButton#primaryButton {{
    color: #ffffff;
    background: #2476ff;
    border-color: #2476ff;
    font-weight: 600;
    padding-left: 18px;
    padding-right: 18px;
}}
QPushButton#primaryButton:hover {{
    background: #1769e0;
    border-color: #1769e0;
}}
QPushButton#addButton {{
    color: #3988ff;
    background: {colors["badge"]};
    border-color: #4676b5;
    font-weight: 600;
}}
QPushButton#addButton:hover {{
    background: {colors["surface_hover"]};
    border-color: #5594ed;
}}
QPushButton#dangerButton {{
    color: #e36a72;
    background: {colors["danger_surface"]};
    border-color: #98545a;
}}
QPushButton#dangerButton:hover {{
    background: {colors["surface_hover"]};
    border-color: #d36a72;
}}
QTreeWidget {{
    background: {colors["surface"]};
    alternate-background-color: {colors["surface_alt"]};
    border: 1px solid {colors["border"]};
    border-radius: 0;
    outline: none;
    padding: 0;
}}
QTreeWidget::item {{
    min-height: 27px;
    border-bottom: 1px solid {colors["border"]};
}}
QTreeWidget::item:hover {{
    background: {colors["surface_hover"]};
}}
QTreeWidget::item:selected {{
    color: {colors["selection_text"]};
    background: {colors["selection"]};
}}
QHeaderView::section {{
    color: {colors["muted"]};
    background: {colors["surface_alt"]};
    border: none;
    border-right: 1px solid {colors["border"]};
    border-bottom: 1px solid {colors["border"]};
    padding: 6px 7px;
    font-weight: 600;
}}
QLineEdit, QSpinBox, QComboBox, QTextEdit {{
    color: {colors["text"]};
    background: {colors["input"]};
    border: 1px solid {colors["border"]};
    border-radius: 3px;
    padding: 6px 8px;
    selection-color: #ffffff;
    selection-background-color: #2476ff;
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTextEdit:focus {{
    border: 2px solid #5594ed;
    padding: 6px 8px;
}}
QLineEdit[requiredMissing="true"] {{
    color: {colors["warning_text"]};
    background: {colors["warning_surface"]};
    border: 2px solid {colors["warning_text"]};
    padding: 6px 8px;
}}
QSpinBox {{
    padding-right: 30px;
}}
QSpinBox::up-button, QSpinBox::down-button {{
    subcontrol-origin: border;
    width: 26px;
    background: {colors["surface_alt"]};
    border-left: 1px solid {colors["border"]};
}}
QSpinBox::up-button {{
    subcontrol-position: top right;
    border-top-right-radius: 6px;
    border-bottom: 1px solid {colors["border"]};
}}
QSpinBox::down-button {{
    subcontrol-position: bottom right;
    border-bottom-right-radius: 6px;
}}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
    background: {colors["surface_hover"]};
}}
QSpinBox::up-arrow {{
    image: url("{spin_up}");
    width: 10px;
    height: 7px;
}}
QSpinBox::down-arrow {{
    image: url("{spin_down}");
    width: 10px;
    height: 7px;
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox QAbstractItemView {{
    color: {colors["text"]};
    background: {colors["surface"]};
    selection-background-color: {colors["selection"]};
}}
QDialogButtonBox {{
    margin-top: 8px;
}}
QToolButton {{
    color: {colors["text"]};
    background: {colors["surface"]};
    border: 1px solid {colors["border"]};
    border-radius: 3px;
    padding: 5px 10px;
    min-height: 18px;
}}
QToolButton:hover {{
    background: {colors["surface_hover"]};
}}
QPushButton#scopeButton {{
    text-align: left;
    font-weight: 600;
}}
QPushButton#scopeButton:checked {{
    color: {colors["selection_text"]};
    background: {colors["selection"]};
    border-color: {colors["border_strong"]};
}}
QGroupBox {{
    background: {colors["surface"]};
    border: 1px solid {colors["border"]};
    border-radius: 2px;
    margin-top: 8px;
    padding-top: 6px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
}}
QLabel#detailsTitle, QLabel#dialogTitle {{
    font-size: 13pt;
    font-weight: 700;
}}
QLabel#detailsSubtitle, QLabel#emptyHint {{
    color: {colors["muted"]};
}}
QSplitter::handle {{
    background: {colors["border"]};
    width: 1px;
}}
QStatusBar {{
    background: {colors["surface_alt"]};
    border-top: 1px solid {colors["border"]};
}}
QMessageBox {{
    background: {colors["surface"]};
}}
QToolTip {{
    color: {colors["text"]};
    background: {colors["surface"]};
    border: 1px solid {colors["border_strong"]};
    padding: 5px;
}}
QScrollBar:vertical, QScrollBar:horizontal {{
    background: {colors["surface_alt"]};
    border: none;
}}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
    background: {colors["border_strong"]};
    border-radius: 5px;
    min-height: 24px;
    min-width: 24px;
}}
"""


def apply_theme(application: QApplication, theme: str = "light") -> None:
    application.setStyle("Fusion")
    application.setStyleSheet(stylesheet(theme))
