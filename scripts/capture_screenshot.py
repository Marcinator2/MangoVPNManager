"""Capture a documentation screenshot using synthetic, temporary data only."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from config.settings import AppSettings  # noqa: E402
from database.database import Database  # noqa: E402
from gui import main_window as main_window_module  # noqa: E402
from gui.main_window import MainWindow  # noqa: E402
from gui.theme import apply_theme  # noqa: E402
from openvpn.runtime import OpenVPNRuntimePaths, StatusSnapshot  # noqa: E402


def _write_synthetic_material(path: Path, mango_names: list[str]) -> None:
    files = [
        path / "ca.crt",
        path / "ta.key",
        path / "issued" / "server.crt",
        path / "private" / "server.key",
    ]
    for name in mango_names:
        files.extend((path / "issued" / f"{name}.crt", path / "private" / f"{name}.key"))
    for file in files:
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("synthetic documentation placeholder", encoding="utf-8")


def main() -> int:
    output = PROJECT_ROOT / "docs" / "screenshots" / "main-window.png"
    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="mango-docs-") as temporary:
        root = Path(temporary)
        openvpn_root = root / "OpenVPN"
        easyrsa_root = openvpn_root / "easy-rsa"
        pki_path = root / "pki"
        runtime = OpenVPNRuntimePaths(root / "config-auto", root / "log")
        main_window_module.discover_openvpn_runtime = lambda _root: runtime
        main_window_module.openvpn_service_running = lambda _service: False
        main_window_module.read_status_snapshot = lambda _path: StatusSnapshot(
            available=False,
            fresh=False,
            updated_at=None,
            connections={},
        )

        database = Database(root / "demo.db")
        database.add_branch_with_mangos("1001", 3, "North branch")
        database.add_branch_with_mangos("2042", 2, "South branch")
        mangos = database.list_mangos()
        _write_synthetic_material(pki_path, [mango.name for mango in mangos])
        for relative in (
            "bin/openvpn.exe",
            "bin/openssl.exe",
            "easy-rsa/bin/sh.exe",
            "easy-rsa/easyrsa",
        ):
            tool = openvpn_root / relative
            tool.parent.mkdir(parents=True, exist_ok=True)
            tool.write_text("synthetic documentation placeholder", encoding="utf-8")
        for mango in mangos:
            if mango.id is not None:
                database.set_certificate_created(mango.id, True)
        database.mark_configs_created([mango.id for mango in mangos if mango.id is not None])

        application = QApplication([])
        settings = AppSettings(
            language="en",
            theme="dark",
            vpn_server_host="vpn.example.invalid",
            openvpn_root=openvpn_root,
            easyrsa_root=easyrsa_root,
            pki_path=pki_path,
        )
        apply_theme(application, settings.theme)
        window = MainWindow(database, settings)
        window.resize(1250, 700)
        window.show()
        application.processEvents()
        saved = window.grab().save(str(output), "PNG")
        window.close()
        if not saved:
            raise RuntimeError(f"Could not save screenshot to {output}")

    print(f"Saved synthetic screenshot: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
