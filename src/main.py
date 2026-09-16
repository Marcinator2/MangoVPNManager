from __future__ import annotations

import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from config.settings import DATABASE_PATH, load_settings, resource_path
from database.database import Database
from gui.main_window import MainWindow
from gui.theme import apply_theme


def main() -> int:
    application = QApplication(sys.argv)
    application.setApplicationName("Mango VPN Manager")
    settings = load_settings()
    apply_theme(application, settings.theme)
    icon_path = resource_path("icons", "mb-soft.png")
    if icon_path.exists():
        application.setWindowIcon(QIcon(str(icon_path)))
    try:
        database = Database(DATABASE_PATH)
    except Exception as exc:
        QMessageBox.critical(None, "Mango VPN Manager", f"Could not open database:\n{exc}")
        return 1
    window = MainWindow(database, settings)
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())

