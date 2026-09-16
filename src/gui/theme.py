from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication


PALETTES: dict[str, dict[str, str]] = {
    "light": {
        "window_top": "#e7eaee",
        "window_bottom": "#d9dee4",
        "surface": "#eef1f4",
        "surface_alt": "#e5e9ed",
        "surface_hover": "#dce6f5",
        "input": "#f2f4f6",
        "text": "#252a31",
        "muted": "#66707c",
        "border": "#c5ccd5",
        "border_strong": "#aab4c0",
        "selection": "#cfdeF5",
        "selection_text": "#17365f",
        "branch": "#e1e6ec",
        "ready": "#168150",
        "offline": "#bd3945",
        "pending": "#7b8592",
        "shadow": "#550f1824",
        "badge": "#dce8f8",
        "danger_surface": "#f2e4e5",
        "disabled_text": "#8c949e",
        "disabled_surface": "#d2d7dd",
        "disabled_border": "#b7bec7",
        "warning_surface": "#f2ead7",
        "warning_text": "#875f12",
    },
    "dark": {
        "window_top": "#292d32",
        "window_bottom": "#1f2226",
        "surface": "#30343a",
        "surface_alt": "#292d33",
        "surface_hover": "#35445a",
        "input": "#272b30",
        "text": "#e7eaee",
        "muted": "#abb3bf",
        "border": "#454b54",
        "border_strong": "#626b77",
        "selection": "#294b78",
        "selection_text": "#f1f6ff",
        "branch": "#373c43",
        "ready": "#65d49a",
        "offline": "#ff747e",
        "pending": "#9ba5b2",
        "shadow": "#99000000",
        "badge": "#263c5d",
        "danger_surface": "#4a3034",
        "disabled_text": "#6f7782",
        "disabled_surface": "#24272b",
        "disabled_border": "#353a41",
        "warning_surface": "#453d2c",
        "warning_text": "#f0c66a",
    },
}


def normalize_theme(theme: str) -> str:
    return theme if theme in PALETTES else "light"


def theme_color(theme: str, name: str) -> str:
    return PALETTES[normalize_theme(theme)][name]


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
    background: qlineargradient(
        x1: 0, y1: 0, x2: 1, y2: 1,
        stop: 0 {colors["window_top"]},
        stop: 1 {colors["window_bottom"]}
    );
}}
QMenuBar {{
    background: {colors["surface_alt"]};
    border-bottom: 1px solid {colors["border"]};
    padding: 4px 10px;
}}
QMenuBar::item {{
    border-radius: 6px;
    padding: 6px 10px;
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
    border-radius: 5px;
    padding: 7px 28px 7px 10px;
}}
QMenu::item:selected {{
    background: {colors["selection"]};
    color: {colors["selection_text"]};
}}
QFrame#brandHeader {{
    background: qlineargradient(
        x1: 0, y1: 0, x2: 1, y2: 1,
        stop: 0 {colors["surface"]},
        stop: 1 {colors["surface_alt"]}
    );
    border: 1px solid {colors["border"]};
    border-radius: 14px;
}}
QFrame#workflowPanel {{
    background: {colors["surface"]};
    border: 1px solid {colors["border"]};
    border-radius: 12px;
}}
QFrame#runtimePanel {{
    background: {colors["surface"]};
    border: 1px solid {colors["border"]};
    border-radius: 10px;
}}
QFrame#installationPanel {{
    background: {colors["surface_alt"]};
    border: 1px solid {colors["border"]};
    border-radius: 10px;
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
    border-radius: 8px;
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
    font-size: 19pt;
    font-weight: 700;
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
    border-radius: 8px;
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
    border-radius: 8px;
    padding: 8px 13px;
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
    border-radius: 10px;
    outline: none;
    padding: 2px;
}}
QTreeWidget::item {{
    min-height: 32px;
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
    padding: 9px 8px;
    font-weight: 600;
}}
QLineEdit, QSpinBox, QComboBox, QTextEdit {{
    color: {colors["text"]};
    background: {colors["input"]};
    border: 1px solid {colors["border"]};
    border-radius: 7px;
    padding: 7px 9px;
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
