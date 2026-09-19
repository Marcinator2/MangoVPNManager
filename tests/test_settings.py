from pathlib import Path

from config.settings import AppSettings, DATABASE_PATH, load_settings, save_settings
from gui.theme import normalize_theme, stylesheet
from openvpn.easyrsa import DEFAULT_PKI_PATH


def test_renamed_default_data_paths() -> None:
    assert DATABASE_PATH.name == "openvpn_manager.db"
    assert str(DEFAULT_PKI_PATH) == r"C:\ProgramData\OpenVPNManager\pki"


def test_settings_round_trip_includes_theme(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    save_settings(
        AppSettings(
            language="de",
            theme="dark",
            last_export_directory="C:/export",
            vpn_server_host="vpn.example.com",
            vpn_server_port=443,
        ),
        path,
    )
    loaded = load_settings(path)
    assert loaded.language == "de"
    assert loaded.theme == "dark"
    assert loaded.last_export_directory == "C:/export"
    assert loaded.vpn_server_host == "vpn.example.com"
    assert loaded.vpn_server_port == 443


def test_invalid_saved_theme_falls_back_to_light(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text('{"language": "en", "theme": "unknown"}', encoding="utf-8")
    assert load_settings(path).theme == "light"


def test_both_themes_generate_distinct_stylesheets() -> None:
    light = stylesheet("light")
    dark = stylesheet("dark")
    assert light != dark
    assert normalize_theme("invalid") == "light"
    assert "#e7eaee" in light
    assert "#292d32" in dark
    assert "QPushButton#dangerButton:disabled" in dark
