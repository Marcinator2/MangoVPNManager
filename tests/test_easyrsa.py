import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from openvpn.easyrsa import (
    OPENVPN_SERVICE_ACCOUNT,
    EasyRSAError,
    EasyRSAPaths,
    EasyRSAService,
    grant_openvpn_service_material_access,
    openvpn_service_material_access_ready,
)


class FakeRunner:
    def __init__(self, paths: EasyRSAPaths) -> None:
        self.paths = paths
        self.calls: list[list[str]] = []

    def __call__(self, command, **kwargs):
        self.calls.append(command)
        if "--genkey" in command:
            Path(command[-1]).write_text(
                "-----BEGIN OpenVPN Static key V1-----\ntest\n"
                "-----END OpenVPN Static key V1-----\n",
                encoding="utf-8",
            )
            return SimpleNamespace(returncode=0, stdout="genkey complete\n", stderr="")
        action = next(
            (
                item
                for item in command
                if item
                in {
                    "--version",
                    "init-pki",
                    "build-ca",
                    "build-client-full",
                    "build-server-full",
                    "sign-req",
                }
            ),
            "",
        )
        pki = self.paths.pki_path
        if action == "--version":
            return SimpleNamespace(returncode=0, stdout="Version: 3.2.6\n", stderr="")
        if action == "init-pki":
            (pki / "private").mkdir(parents=True)
            (pki / "issued").mkdir()
            (pki / "reqs").mkdir()
            (pki / "vars.example").write_text("test", encoding="utf-8")
        elif action == "build-ca":
            (pki / "ca.crt").write_text("certificate", encoding="utf-8")
            (pki / "private" / "ca.key").write_text("private", encoding="utf-8")
        elif action in {"build-client-full", "build-server-full", "sign-req"}:
            index = command.index(action)
            name = command[index + 2] if action == "sign-req" else command[index + 1]
            (pki / "issued" / f"{name}.crt").write_text("certificate", encoding="utf-8")
            if action != "sign-req":
                (pki / "private" / f"{name}.key").write_text("private", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout=f"{action} complete\n", stderr="")


@pytest.fixture
def service(tmp_path: Path):
    openvpn = tmp_path / "OpenVPN"
    easyrsa = openvpn / "easy-rsa"
    for file in (
        easyrsa / "bin" / "sh.exe",
        easyrsa / "easyrsa",
        openvpn / "bin" / "openssl.exe",
        openvpn / "bin" / "openvpn.exe",
    ):
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("test", encoding="utf-8")
    paths = EasyRSAPaths(openvpn, easyrsa, tmp_path / "pki")
    runner = FakeRunner(paths)
    return EasyRSAService(paths, runner=runner, acl_hardener=lambda path: None), runner


def test_initializes_passwordless_ca_in_configured_pki(service) -> None:
    manager, runner = service
    manager.initialize_ca()
    status = manager.status()
    assert status.pki_initialized
    assert status.ca_ready
    assert any("init-pki" in call for call in runner.calls)
    assert any("build-ca" in call and "nopass" in call for call in runner.calls)


def test_detects_realistic_easyrsa_326_pki_without_openssl_copy(service) -> None:
    manager, _ = service
    manager.initialize_ca()
    assert not (manager.paths.pki_path / "openssl-easyrsa.cnf").exists()
    assert manager.status().pki_initialized


def test_creates_passwordless_client_certificate(service) -> None:
    manager, runner = service
    manager.initialize_ca()
    manager.create_client_certificate("0004_Router1")
    assert manager.certificate_status("0004_Router1").complete
    call = next(call for call in runner.calls if "build-client-full" in call)
    assert call[-2:] == ["0004_Router1", "nopass"]


def test_creates_server_certificate_and_tls_key(service) -> None:
    manager, runner = service
    manager.initialize_ca()
    manager.create_server_material()

    assert manager.server_material_status().complete
    assert any("build-server-full" in call for call in runner.calls)
    assert any("--genkey" in call for call in runner.calls)


def test_recovers_existing_key_and_request_by_signing_them(service) -> None:
    manager, runner = service
    manager.initialize_ca()
    name = "0004_Router2"
    (manager.paths.pki_path / "private" / f"{name}.key").write_text(
        "private",
        encoding="utf-8",
    )
    (manager.paths.pki_path / "reqs" / f"{name}.req").write_text(
        "request",
        encoding="utf-8",
    )

    manager.create_client_certificate(name)

    assert manager.certificate_status(name).complete
    assert any(
        "sign-req" in call and "client" in call and name in call
        for call in runner.calls
    )


def test_refuses_to_overwrite_existing_certificate(service) -> None:
    manager, _ = service
    manager.initialize_ca()
    manager.create_client_certificate("0004_Router1")
    with pytest.raises(EasyRSAError):
        manager.create_client_certificate("0004_Router1")


def test_rejects_unsafe_common_name(service) -> None:
    manager, _ = service
    with pytest.raises(EasyRSAError):
        manager.certificate_status("../escape")


def test_resets_pki_by_moving_it_to_timestamped_backup(service) -> None:
    manager, _ = service
    manager.initialize_ca()
    manager.create_client_certificate("0004_Router1")

    result = manager.reset_pki_to_backup()

    assert not manager.paths.pki_path.exists()
    backups = list((manager.paths.pki_path.parent / "pki-backups").glob("pki-*"))
    assert len(backups) == 1
    assert (backups[0] / "ca.crt").is_file()
    assert (backups[0] / "private" / "ca.key").is_file()
    assert (backups[0] / "issued" / "0004_Router1.crt").is_file()
    assert (backups[0] / "private" / "0004_Router1.key").is_file()
    assert str(backups[0]) in result.output


def test_refuses_to_reset_missing_pki(service) -> None:
    manager, _ = service
    with pytest.raises(EasyRSAError):
        manager.reset_pki_to_backup()


def _create_server_runtime_material(pki: Path) -> None:
    for relative in (
        "ca.crt",
        "ta.key",
        "issued/server.crt",
        "private/server.key",
    ):
        target = pki / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("test", encoding="utf-8")


@pytest.mark.skipif(os.name != "nt", reason="Windows ACL behavior")
def test_openvpn_service_access_targets_only_server_runtime_material(
    tmp_path: Path,
) -> None:
    pki = tmp_path / "pki"
    _create_server_runtime_material(pki)
    ca_key = pki / "private" / "ca.key"
    client_key = pki / "private" / "0004_Router1.key"
    ca_key.write_text("private", encoding="utf-8")
    client_key.write_text("private", encoding="utf-8")
    calls: list[list[str]] = []

    def runner(command, **_kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="processed", stderr="")

    grant_openvpn_service_material_access(pki, runner=runner)

    granted = {Path(call[1]) for call in calls}
    assert granted == {
        pki,
        pki / "issued",
        pki / "private",
        pki / "ca.crt",
        pki / "ta.key",
        pki / "issued" / "server.crt",
        pki / "private" / "server.key",
    }
    assert ca_key not in granted
    assert client_key not in granted
    assert all(OPENVPN_SERVICE_ACCOUNT in call[3] for call in calls)


@pytest.mark.skipif(os.name != "nt", reason="Windows ACL behavior")
def test_detects_openvpn_service_material_access(tmp_path: Path) -> None:
    pki = tmp_path / "pki"
    _create_server_runtime_material(pki)

    def allowed(command, **_kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout=f"{command[1]} NT-DIENST\\OpenVPNService:(R)",
            stderr="",
        )

    assert openvpn_service_material_access_ready(pki, runner=allowed)

    def denied(command, **_kwargs):
        return SimpleNamespace(returncode=0, stdout=str(command[1]), stderr="")

    assert not openvpn_service_material_access_ready(pki, runner=denied)
