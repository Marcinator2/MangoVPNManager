from pathlib import Path

import pytest

from database.models import Mango
from openvpn.exporter import build_export_bundle, render_preview, write_export


CERTIFICATE = """-----BEGIN CERTIFICATE-----
test-certificate
-----END CERTIFICATE-----"""
PRIVATE_KEY_LABEL = "PRIVATE" + " KEY"
PRIVATE_KEY = f"""-----BEGIN {PRIVATE_KEY_LABEL}-----
test-private-key
-----END {PRIVATE_KEY_LABEL}-----"""
TLS_KEY = """-----BEGIN OpenVPN Static key V1-----
test-tls-key
-----END OpenVPN Static key V1-----"""


@pytest.fixture
def mango() -> Mango:
    return Mango(
        id=1,
        branch_id=1,
        mango_number=1,
        name="0004_Mango1",
        vpn_ip="10.8.4.1",
        lan_network="10.4.1.0/24",
        mango_ip="10.4.1.1",
        oven_ip="10.4.1.101",
    )


@pytest.fixture
def pki(tmp_path: Path, mango: Mango) -> Path:
    path = tmp_path / "pki"
    (path / "issued").mkdir(parents=True)
    (path / "private").mkdir()
    (path / "ca.crt").write_text(CERTIFICATE, encoding="utf-8")
    (path / "issued" / f"{mango.name}.crt").write_text(
        CERTIFICATE,
        encoding="utf-8",
    )
    (path / "private" / f"{mango.name}.key").write_text(
        PRIVATE_KEY,
        encoding="utf-8",
    )
    (path / "issued" / "server.crt").write_text(CERTIFICATE, encoding="utf-8")
    (path / "private" / "server.key").write_text(PRIVATE_KEY, encoding="utf-8")
    (path / "ta.key").write_text(TLS_KEY, encoding="utf-8")
    return path


def test_bundle_contains_ccd_routes_client_and_server(mango: Mango) -> None:
    bundle = build_export_bundle([mango])
    assert bundle.files["ccd/0004_Mango1"] == (
        "ifconfig-push 10.8.4.1 255.255.0.0\n"
        "iroute 10.4.1.0 255.255.255.0\n"
    )
    assert "route 10.4.1.0 255.255.255.0" in bundle.files["server.ovpn"]
    assert "server 10.8.0.0 255.255.0.0" in bundle.files["server.ovpn"]
    assert "<CLIENT_PRIVATE_KEY_MISSING:0004_Mango1>" in bundle.files[
        "clients/0004_Mango1.ovpn"
    ]
    assert bundle.warnings
    assert not bundle.ready_for_export


def test_complete_bundle_embeds_material_but_preview_redacts_keys(
    mango: Mango,
    pki: Path,
) -> None:
    bundle = build_export_bundle(
        [mango],
        pki_path=pki,
        server_host="vpn.example.com",
        server_port=1194,
    )

    client = bundle.files["clients/0004_Mango1.ovpn"]
    assert "remote vpn.example.com 1194" in client
    assert "-----BEGIN CERTIFICATE-----" in client
    assert "-----BEGIN PRIVATE KEY-----" in client
    assert "-----BEGIN OpenVPN Static key V1-----" in client
    assert bundle.complete_mango_ids == (1,)
    assert bundle.contains_private_keys
    assert bundle.ready_for_export

    preview = render_preview(bundle)
    assert "test-private-key" not in preview
    assert "test-tls-key" not in preview
    assert "[PRIVATE KEY HIDDEN IN PREVIEW]" in preview
    assert "[TLS KEY HIDDEN IN PREVIEW]" in preview


def test_server_uses_machine_runtime_paths_and_parseable_status(
    mango: Mango,
    pki: Path,
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "custom-config"
    status_path = tmp_path / "custom-log" / "status.tsv"
    bundle = build_export_bundle(
        [mango],
        pki_path=pki,
        server_host="vpn.example.com",
        openvpn_config_dir=config_dir,
        openvpn_status_path=status_path,
    )
    server = bundle.files["server.ovpn"]
    escaped_config_dir = str(config_dir).replace("\\", "\\\\")
    escaped_status_path = str(status_path).replace("\\", "\\\\")
    assert f'client-config-dir "{escaped_config_dir}\\\\ccd"' in server
    assert f'status "{escaped_status_path}" 5' in server
    assert "status-version 3" in server


def test_server_escapes_backslashes_in_windows_paths(mango: Mango, pki: Path) -> None:
    bundle = build_export_bundle(
        [mango],
        pki_path=pki,
        server_host="vpn.example.com",
        openvpn_config_dir=Path(r"C:\Program Files\OpenVPN\config-auto"),
        openvpn_status_path=Path(r"C:\ProgramData\OpenVPN\log\status.tsv"),
    )
    server = bundle.files["server.ovpn"]
    assert 'client-config-dir "C:\\\\Program Files\\\\OpenVPN\\\\config-auto\\\\ccd"' in server
    assert 'status "C:\\\\ProgramData\\\\OpenVPN\\\\log\\\\status.tsv" 5' in server
    assert 'ca "C:\\\\' in server


def test_export_does_not_overwrite_without_permission(
    tmp_path: Path,
    mango: Mango,
) -> None:
    bundle = build_export_bundle([mango])
    write_export(bundle, tmp_path)
    with pytest.raises(FileExistsError):
        write_export(bundle, tmp_path)


def test_export_can_explicitly_replace_existing_files(
    tmp_path: Path,
    mango: Mango,
) -> None:
    bundle = build_export_bundle([mango])
    written = write_export(bundle, tmp_path)
    assert len(written) == 5
    changed = tmp_path / "ccd" / mango.name
    changed.write_text("old", encoding="utf-8")
    write_export(bundle, tmp_path, overwrite=True)
    assert "ifconfig-push 10.8.4.1" in changed.read_text(encoding="utf-8")
