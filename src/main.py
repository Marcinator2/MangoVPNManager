from __future__ import annotations

import sys


def main() -> int:
    # Recovery must run before loading application DLLs or touching user data.
    from updater.bootstrap import startup_guard

    allowed, installation_lock = startup_guard()
    if not allowed:
        return 1
    try:
        return run_application()
    finally:
        if installation_lock:
            installation_lock.close()


def run_application() -> int:
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication, QMessageBox

    from config.settings import DATABASE_PATH, load_settings, resource_path
    from config.version import read_build_info
    from database.database import Database
    from gui.main_window import MainWindow
    from gui.theme import apply_theme

    application = QApplication(sys.argv)
    application.setApplicationName("OpenVPN Manager")
    application.setApplicationVersion(read_build_info().version)
    # Load Qt and UI modules without opening user data or contacting services.
    if "--smoke-test" in sys.argv:
        # An optional bounded delay permits process-handoff integration tests.
        delay = 100
        for argument in sys.argv:
            if argument.startswith("--smoke-test-delay="):
                delay = max(100, min(30000, int(argument.split("=", 1)[1])))
        QTimer.singleShot(delay, application.quit)
        return application.exec()
    settings = load_settings()
    apply_theme(application, settings.theme)
    icon_path = resource_path("icons", "mb-soft.png")
    if icon_path.exists():
        application.setWindowIcon(QIcon(str(icon_path)))
    try:
        database = Database(DATABASE_PATH)
    except Exception as exc:
        QMessageBox.critical(None, "OpenVPN Manager", f"Could not open database:\n{exc}")
        return 1
    window = MainWindow(database, settings)
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
