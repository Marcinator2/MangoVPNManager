from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

from openvpn.easyrsa import (
    DEFAULT_EASYRSA_ROOT,
    DEFAULT_OPENVPN_ROOT,
    DEFAULT_PKI_PATH,
)


def application_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def resource_path(*parts: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", application_root()))
    return base.joinpath(*parts)


DATA_DIR = application_root() / "data"
DATABASE_PATH = DATA_DIR / "openvpn_manager.db"
SETTINGS_PATH = DATA_DIR / "settings.json"


@dataclass(slots=True)
class AppSettings:
    language: str = "en"
    theme: str = "light"
    last_export_directory: str = ""
    vpn_server_host: str = ""
    vpn_server_port: int = 1194
    openvpn_root: Path = DEFAULT_OPENVPN_ROOT
    easyrsa_root: Path = DEFAULT_EASYRSA_ROOT
    pki_path: Path = DEFAULT_PKI_PATH


def load_settings(path: Path = SETTINGS_PATH) -> AppSettings:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return AppSettings()
    language = raw.get("language", "en")
    if language not in {"en", "de"}:
        language = "en"
    theme = raw.get("theme", "light")
    if theme not in {"light", "dark"}:
        theme = "light"
    try:
        vpn_server_port = int(raw.get("vpn_server_port", 1194))
    except (TypeError, ValueError):
        vpn_server_port = 1194
    if not 1 <= vpn_server_port <= 65535:
        vpn_server_port = 1194
    return AppSettings(
        language=language,
        theme=theme,
        last_export_directory=str(raw.get("last_export_directory", "")),
        vpn_server_host=str(raw.get("vpn_server_host", "")),
        vpn_server_port=vpn_server_port,
        openvpn_root=Path(raw.get("openvpn_root", DEFAULT_OPENVPN_ROOT)),
        easyrsa_root=Path(raw.get("easyrsa_root", DEFAULT_EASYRSA_ROOT)),
        pki_path=Path(raw.get("pki_path", DEFAULT_PKI_PATH)),
    )


def save_settings(settings: AppSettings, path: Path = SETTINGS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            {
                "language": settings.language,
                "theme": settings.theme,
                "last_export_directory": settings.last_export_directory,
                "vpn_server_host": settings.vpn_server_host,
                "vpn_server_port": settings.vpn_server_port,
                "openvpn_root": str(settings.openvpn_root),
                "easyrsa_root": str(settings.easyrsa_root),
                "pki_path": str(settings.pki_path),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    temporary.replace(path)

