"""Run installation recovery before importing Qt or opening the database."""
from __future__ import annotations

import ctypes
from pathlib import Path
import sys

from updater.release import UpdateError
from updater.service import start_helper
from updater.transaction import load_journal, operation_dir, safe_path
from updater.windows import InstallationLock


def startup_guard() -> tuple[bool, InstallationLock | None]:
    if not getattr(sys, "frozen", False) or sys.platform != "win32":
        return True, None
    application_lock = None
    try:
        root = safe_path(Path(sys.executable).absolute().parent)
        application_lock = InstallationLock(root)
        with InstallationLock(root, "update"):
            application_lock.acquire()
            journal = load_journal(root)
            if journal and journal["phase"] == "applying":
                operation = operation_dir(root, journal["id"])
                sources = [root / "MangoVPNUpdater.exe",
                           operation / "backup" / "MangoVPNUpdater.exe",
                           operation / "verified" / "MangoVPNUpdater.exe"]
                source = next((item for item in sources if item.is_file()), None)
                if source is None:
                    raise UpdateError("recovery")
                application_lock.close()
                start_helper(root, ["--recover", str(root)], source)
                return False, None
        return True, application_lock
    except (OSError, UpdateError) as exc:
        if application_lock:
            application_lock.close()
        from config.settings import load_settings
        from gui.i18n import Translator
        t = Translator(load_settings().language)
        code = exc.code if isinstance(exc, UpdateError) else "recovery"
        ctypes.windll.user32.MessageBoxW(None, t("update_" + code), t("update_title"), 0x10)
        return False, None
