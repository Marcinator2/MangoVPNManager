from __future__ import annotations

from pathlib import Path

import pytest

from database.models import Mango
from openvpn.addressing import ValidationError
from openvpn.exporter import build_export_bundle
from openvpn.installer import (
    build_server_install_plan,
    inspect_server_installation,
    install_server_files,
    repair_server_file_acls,
)


CERTIFICATE = "-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----"
PRIVATE_KEY = "-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----"


def _ready_bundle(tmp_path: Path):
    mango = Mango(1, 1, 1, "0004_Mango1", "10.8.4.1", "10.4.1.0/24", "10.4.1.1", "10.4.1.101")
    pki = tmp_path / "pki"
    (pki / "issued").mkdir(parents=True)
    (pki / "private").mkdir()
    (pki / "ca.crt").write_text(CERTIFICATE, encoding="utf-8")
    (pki / "issued" / "server.crt").write_text(CERTIFICATE, encoding="utf-8")
    (pki / "private" / "server.key").write_text(PRIVATE_KEY, encoding="utf-8")
    (pki / "issued" / f"{mango.name}.crt").write_text(CERTIFICATE, encoding="utf-8")
    (pki / "private" / f"{mango.name}.key").write_text(PRIVATE_KEY, encoding="utf-8")
    return build_export_bundle([mango], pki_path=pki, server_host="vpn.example.com")


def test_install_writes_only_server_and_ccd_and_backs_up_existing(tmp_path: Path) -> None:
    bundle = _ready_bundle(tmp_path)
    config_dir = tmp_path / "OpenVPN" / "config-auto"
    config_dir.mkdir(parents=True)
    existing = config_dir / "server.ovpn"
    existing.write_text("old server", encoding="utf-8")

    plan = build_server_install_plan(bundle, config_dir)
    acl_targets: list[Path] = []
    written = install_server_files(
        plan,
        replace=True,
        acl_resetter=lambda paths: acl_targets.extend(paths),
    )

    assert {path.relative_to(config_dir).as_posix() for path in written} == {
        "server.ovpn",
        "ccd/0004_Mango1",
    }
    assert not (config_dir / "clients").exists()
    backups = list((config_dir.parent / "MangoVPNManager-backups").rglob("server.ovpn"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "old server"
    assert acl_targets == written
    status = inspect_server_installation(plan, acl_checker=lambda _path: True)
    assert status.state == "current"
    assert not status.installation_needed


def test_installation_status_distinguishes_missing_and_changed_files(tmp_path: Path) -> None:
    bundle = _ready_bundle(tmp_path)
    config_dir = tmp_path / "OpenVPN" / "config-auto"
    config_dir.mkdir(parents=True)
    plan = build_server_install_plan(bundle, config_dir)
    missing = inspect_server_installation(plan, acl_checker=lambda _path: True)
    assert missing.state == "not_installed"
    assert missing.installation_needed

    (config_dir / "server.ovpn").write_text("outdated", encoding="utf-8")
    changed = inspect_server_installation(plan, acl_checker=lambda _path: True)
    assert changed.state == "update_required"
    assert changed.changed_files == (config_dir / "server.ovpn",)


def test_current_files_request_permission_repair_when_acl_is_not_inherited(
    tmp_path: Path,
) -> None:
    bundle = _ready_bundle(tmp_path)
    config_dir = tmp_path / "OpenVPN" / "config-auto"
    config_dir.mkdir(parents=True)
    plan = build_server_install_plan(bundle, config_dir)
    install_server_files(plan, acl_resetter=lambda _paths: None)
    status = inspect_server_installation(plan, acl_checker=lambda _path: False)
    assert status.state == "permissions_repair_required"
    assert status.installation_needed


def test_permission_repair_targets_only_expected_server_files(tmp_path: Path) -> None:
    bundle = _ready_bundle(tmp_path)
    config_dir = tmp_path / "OpenVPN" / "config-auto"
    config_dir.mkdir(parents=True)
    plan = build_server_install_plan(bundle, config_dir)
    install_server_files(plan, acl_resetter=lambda _paths: None)
    unrelated = config_dir / "unrelated.ovpn"
    unrelated.write_text("leave me alone", encoding="utf-8")
    repaired: list[Path] = []
    targets = repair_server_file_acls(
        plan,
        acl_resetter=lambda paths: repaired.extend(paths),
    )
    assert repaired == targets
    assert unrelated not in repaired


def test_acl_failure_rolls_back_replaced_server_file(tmp_path: Path) -> None:
    bundle = _ready_bundle(tmp_path)
    config_dir = tmp_path / "OpenVPN" / "config-auto"
    config_dir.mkdir(parents=True)
    existing = config_dir / "server.ovpn"
    existing.write_text("old server", encoding="utf-8")
    plan = build_server_install_plan(bundle, config_dir)

    def fail_acl(_paths: list[Path]) -> None:
        raise OSError("ACL failure")

    with pytest.raises(OSError, match="ACL failure"):
        install_server_files(plan, replace=True, acl_resetter=fail_acl)
    assert existing.read_text(encoding="utf-8") == "old server"


def test_install_refuses_incomplete_bundle(tmp_path: Path) -> None:
    mango = Mango(1, 1, 1, "0004_Mango1", "10.8.4.1", "10.4.1.0/24", "10.4.1.1", "10.4.1.101")
    bundle = build_export_bundle([mango])
    target = tmp_path / "OpenVPN" / "config-auto"
    target.parent.mkdir()
    with pytest.raises(ValidationError):
        build_server_install_plan(bundle, target)
