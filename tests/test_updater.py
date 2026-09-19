from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import stat
import threading
from types import SimpleNamespace
import urllib.error
import zipfile

import pytest

from config.version import BuildInfo, read_build_info, version_tuple
from updater import package, transaction
from updater.package import MANAGED, archive_entries, extract_package, verify_checksum
from updater.release import Cancelled, ReleaseClient, SafeRedirect, UpdateError, validate_url


def release_payload(tag="v1.10.0"):
    name = f"OpenVPNManager-{tag}-windows-x64.zip"
    return {
        "tag_name": tag, "draft": False, "prerelease": False,
        "assets": [{"name": asset, "size": 100, "state": "uploaded",
                    "browser_download_url": f"https://github.com/Marcinator2/OpenVPN-Manager/releases/download/{tag}/{asset}"}
                   for asset in (name, name + ".sha256")],
    }


def mock_client(payload):
    client = ReleaseClient()
    client.fetch = lambda *args: json.dumps(payload).encode()
    return client


def make_archive(path, version="v1.10.0", extra=None):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("OpenVPNManager/OpenVPNManager.exe", b"synthetic program")
        archive.writestr("OpenVPNManager/OpenVPNUpdater.exe", b"synthetic helper")
        archive.writestr("OpenVPNManager/_internal/build-info.json", json.dumps({
            "version": version, "build_type": "stable", "commit": "synthetic",
        }))
        archive.writestr("OpenVPNManager/_internal/runtime.dll", b"synthetic runtime")
        if extra:
            for name, data in extra:
                archive.writestr(name, data)
    return path


def install_fixture(tmp_path):
    root = tmp_path / "application"
    root.mkdir()
    (root / MANAGED[0]).write_bytes(b"old program")
    (root / MANAGED[2]).write_bytes(b"old helper")
    (root / "_internal").mkdir()
    (root / "_internal" / "runtime").write_bytes(b"old runtime")
    (root / "data").mkdir()
    (root / "data" / "database.db").write_bytes(b"synthetic database")
    (root / "data" / "settings.json").write_bytes(b"synthetic settings")
    (root / "unmanaged.txt").write_bytes(b"keep")
    operation = transaction.create_operation(root)
    stage = operation / "verified"
    stage.mkdir()
    (stage / MANAGED[0]).write_bytes(b"new program")
    (stage / MANAGED[2]).write_bytes(b"new helper")
    (stage / "_internal").mkdir()
    (stage / "_internal" / "runtime").write_bytes(b"new runtime")
    return root, operation


def assert_old(root):
    assert (root / MANAGED[0]).read_bytes() == b"old program"
    assert (root / MANAGED[2]).read_bytes() == b"old helper"
    assert (root / "_internal" / "runtime").read_bytes() == b"old runtime"


def assert_data(root):
    assert (root / "data" / "database.db").read_bytes() == b"synthetic database"
    assert (root / "data" / "settings.json").read_bytes() == b"synthetic settings"
    assert (root / "unmanaged.txt").read_bytes() == b"keep"


def test_release_numeric_comparison_and_no_downgrade():
    client = mock_client(release_payload())
    assert client.latest("v1.9.9", threading.Event()).version == "v1.10.0"
    assert client.latest("v1.10.0", threading.Event()) is None
    assert client.latest("v2.0.0", threading.Event()) is None
    assert version_tuple("v10.2.3") == (10, 2, 3)


@pytest.mark.parametrize("version", ["v01.0.0", "develop-123", "v1.0", "v1.0.0-rc1", "", "1.2.3.4"])
def test_invalid_stable_versions(version):
    with pytest.raises(ValueError):
        version_tuple(version)


@pytest.mark.parametrize("change", [
    {"draft": True}, {"prerelease": True}, {"tag_name": "develop-123"},
    {"tag_name": "v1.10.0-rc1"}, {"assets": []}, {"assets": None},
])
def test_invalid_release_metadata(change):
    payload = release_payload()
    payload.update(change)
    with pytest.raises(UpdateError, match="release_invalid"):
        mock_client(payload).latest("v1.0.0", threading.Event())


def test_asset_url_cannot_point_to_another_repository():
    payload = release_payload()
    payload["assets"][0]["browser_download_url"] = "https://github.com/attacker/project/file.zip"
    with pytest.raises(UpdateError, match="release_invalid"):
        mock_client(payload).latest("v1.0.0", threading.Event())


@pytest.mark.parametrize("url", [
    "http://github.com/file", "https://github.com.evil.test/file",
    "file:///C:/file", "https://user@github.com/file", "https://github.com:8443/file",
])
def test_untrusted_urls(url):
    with pytest.raises(UpdateError):
        validate_url(url)


def test_redirect_validates_new_host():
    with pytest.raises(UpdateError):
        SafeRedirect().redirect_request(None, None, 302, "", {}, "https://evil.test/file")


@pytest.mark.parametrize("status,code", [(404, "no_release"), (403, "network"), (429, "network"), (500, "network")])
def test_http_failure_codes(status, code):
    client = ReleaseClient()
    def fail(*args, **kwargs):
        raise urllib.error.HTTPError("https://api.github.com", status, "test", {}, None)
    client.opener = SimpleNamespace(open=fail)
    with pytest.raises(UpdateError, match=code):
        client.latest("v1.0.0", threading.Event())


def test_download_limits_incomplete_and_cancelled():
    class Response(io.BytesIO):
        headers = {"Content-Length": "10"}
        def geturl(self):
            return "https://github.com/file"
    client = ReleaseClient()
    client.opener = SimpleNamespace(open=lambda *a, **k: Response(b"abc"))
    with pytest.raises(UpdateError, match="download_size"):
        client.fetch("https://github.com/file", 2, threading.Event())
    with pytest.raises(UpdateError, match="download_incomplete"):
        client.fetch("https://github.com/file", 20, threading.Event())
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(Cancelled):
        client.fetch("https://github.com/file", 20, cancel)


def test_checksum_and_extraction(tmp_path):
    path = make_archive(tmp_path / "release.zip")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    verify_checksum(path, f"{digest} *release.zip\n".encode(), "release.zip", threading.Event())
    extract_package(path, tmp_path / "prepared", "v1.10.0", threading.Event())
    assert read_build_info(tmp_path / "prepared" / "_internal" / "build-info.json").version == "v1.10.0"
    with pytest.raises(UpdateError, match="checksum"):
        verify_checksum(path, (("0" * 64) + " *release.zip").encode(), "release.zip", threading.Event())
    with pytest.raises(UpdateError, match="checksum"):
        verify_checksum(path, f"{digest} *other.zip".encode(), "release.zip", threading.Event())


@pytest.mark.parametrize("entry", [
    "OpenVPNManager/../escape", "OpenVPNManager/_internal/../../escape",
    "/OpenVPNManager/_internal/a", "C:/escape", "OpenVPNManager\\_internal\\a",
    "OpenVPNManager/_internal/nul.txt", "OpenVPNManager/_internal/COM1",
    "OpenVPNManager/_internal/evil:stream", "OpenVPNManager/_internal/a.",
    "OpenVPNManager/_internal/a ", "OpenVPNManager/_internal//a",
    "OpenVPNManager/data/settings.json", "OpenVPNManager/_internal/client.key",
    "OpenVPNManager/_internal/BUILD-INFO.JSON",
    "OpenVPNManager/extra.exe", "OpenVPNManager/_internal/foo\u0000bar",
])
def test_hostile_archive_never_extracts(tmp_path, entry):
    # zipfile normalizes Windows separators and truncates NULs when writing.
    # Patch equal-length raw names so the reader receives the hostile bytes.
    stored = entry.replace("\\", "/").replace("\x00", "_")
    path = make_archive(tmp_path / "release.zip", extra=[(stored, b"bad")])
    if stored != entry:
        path.write_bytes(path.read_bytes().replace(stored.encode(), entry.encode()))
    destination = tmp_path / "prepared"
    with pytest.raises(UpdateError, match="package_invalid"):
        extract_package(path, destination, "v1.10.0", threading.Event())
    assert not destination.exists()


def test_link_and_file_directory_conflicts(tmp_path):
    link = zipfile.ZipInfo("OpenVPNManager/_internal/link")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    for index, extra in enumerate([[(link, "target")], [
        ("OpenVPNManager/_internal/a", "file"), ("OpenVPNManager/_internal/a/b", "child"),
    ]]):
        path = make_archive(tmp_path / f"{index}.zip", extra=extra)
        with zipfile.ZipFile(path) as archive:
            with pytest.raises(UpdateError, match="package_invalid"):
                archive_entries(archive)


def test_incomplete_or_wrong_version_package(tmp_path):
    path = tmp_path / "empty.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("OpenVPNManager/OpenVPNManager.exe", "incomplete")
    with pytest.raises(UpdateError):
        extract_package(path, tmp_path / "missing", "v1.0.0", threading.Event())
    path = make_archive(tmp_path / "wrong.zip")
    with pytest.raises(UpdateError):
        extract_package(path, tmp_path / "wrong", "v2.0.0", threading.Event())


def test_archive_limits_and_cancellation(tmp_path, monkeypatch):
    path = make_archive(tmp_path / "release.zip")
    monkeypatch.setattr(package, "MAX_ENTRIES", 1)
    with pytest.raises(UpdateError):
        extract_package(path, tmp_path / "big", "v1.10.0", threading.Event())
    monkeypatch.setattr(package, "MAX_ENTRIES", 20000)
    monkeypatch.setattr(package, "MAX_UNPACKED", 1)
    with pytest.raises(UpdateError):
        extract_package(path, tmp_path / "big2", "v1.10.0", threading.Event())
    monkeypatch.setattr(package, "MAX_UNPACKED", 1024 * 1024)
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(Cancelled):
        extract_package(path, tmp_path / "cancel", "v1.10.0", cancel)


def test_apply_keeps_data_and_backup(tmp_path):
    root, operation = install_fixture(tmp_path)
    transaction.apply_update(root, operation.name)
    assert (root / MANAGED[0]).read_bytes() == b"new program"
    assert (operation / "backup" / MANAGED[0]).read_bytes() == b"old program"
    assert transaction.load_journal(root)["phase"] == "installed"
    assert_data(root)
    assert not transaction.recover(root)


@pytest.mark.parametrize("failed_name", MANAGED)
def test_failed_rename_rolls_back(tmp_path, monkeypatch, failed_name):
    root, operation = install_fixture(tmp_path)
    rename = Path.rename
    def fail(self, target):
        if self == operation / "verified" / failed_name:
            raise PermissionError("simulated locked file")
        return rename(self, target)
    monkeypatch.setattr(Path, "rename", fail)
    with pytest.raises(PermissionError):
        transaction.apply_update(root, operation.name)
    assert_old(root)
    assert_data(root)
    assert transaction.load_journal(root)["phase"] == "rolled_back"


@pytest.mark.parametrize("completed,moved_old", [(0, False), (0, True), (1, False), (1, True), (2, False), (2, True), (3, False)])
def test_recovery_after_interruption_between_renames(tmp_path, completed, moved_old):
    root, operation = install_fixture(tmp_path)
    backup = operation / "backup"
    backup.mkdir()
    transaction.set_phase(root, operation.name, "applying")
    for name in MANAGED[:completed]:
        (root / name).rename(backup / name)
        (operation / "verified" / name).rename(root / name)
    if moved_old:
        name = MANAGED[completed]
        (root / name).rename(backup / name)
    assert transaction.recover(root)
    assert_old(root)
    assert_data(root)
    assert not transaction.recover(root)


def test_recovery_itself_can_be_retried(tmp_path, monkeypatch):
    root, operation = install_fixture(tmp_path)
    transaction.apply_update(root, operation.name)
    transaction.set_phase(root, operation.name, "applying")
    rename = Path.rename
    def fail(self, target):
        if self == operation / "backup" / "_internal":
            raise PermissionError("temporary lock")
        return rename(self, target)
    monkeypatch.setattr(Path, "rename", fail)
    with pytest.raises(PermissionError):
        transaction.recover(root)
    monkeypatch.setattr(Path, "rename", rename)
    assert transaction.recover(root)
    assert_old(root)
    assert_data(root)


def test_preflight_permissions_and_space(tmp_path, monkeypatch):
    root, _ = install_fixture(tmp_path)
    monkeypatch.setattr(transaction.shutil, "disk_usage", lambda _: SimpleNamespace(free=0))
    with pytest.raises(UpdateError, match="space"):
        transaction.preflight(root, 100)
    monkeypatch.setattr(transaction.shutil, "disk_usage", lambda _: SimpleNamespace(free=1000))
    mkdir = Path.mkdir
    def fail(self, *args, **kwargs):
        if self.name.startswith(".openvpn-manager-write-"):
            raise PermissionError("not writable")
        return mkdir(self, *args, **kwargs)
    monkeypatch.setattr(Path, "mkdir", fail)
    with pytest.raises(UpdateError, match="permissions"):
        transaction.preflight(root, 100)
    assert_old(root)
    assert_data(root)


def test_paths_and_journal_are_fail_closed(tmp_path):
    root, _ = install_fixture(tmp_path)
    with pytest.raises(UpdateError, match="path"):
        transaction.safe_path(Path(root.anchor))
    with pytest.raises(UpdateError):
        transaction.operation_dir(root, "../escape")
    transaction.write_json(root / transaction.WORK / "journal.json", {"id": "x", "phase": "applying"})
    with pytest.raises(UpdateError):
        transaction.recover(root)
    assert_old(root)


@pytest.mark.skipif(os.name != "nt", reason="Windows mutex and process APIs")
def test_windows_mutex_and_process_identity(tmp_path):
    from updater.windows import InstallationLock, ProcessIdentity, current_identity
    import sys
    with InstallationLock(tmp_path):
        with pytest.raises(UpdateError, match="busy"):
            InstallationLock(tmp_path).acquire()
    with InstallationLock(tmp_path):
        pass
    creation = current_identity(Path(sys._base_executable))
    process = ProcessIdentity(os.getpid(), Path(sys._base_executable), creation)
    assert not process.exited()
    process.close()
    with pytest.raises(UpdateError, match="process"):
        ProcessIdentity(os.getpid(), Path(sys._base_executable), creation + 1)



def test_reparse_point_is_rejected_before_any_replacement(tmp_path, monkeypatch):
    root, operation = install_fixture(tmp_path)
    original = Path.lstat
    def reparse(self, *args, **kwargs):
        if self == root / "_internal":
            return SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
        return original(self, *args, **kwargs)
    monkeypatch.setattr(Path, "lstat", reparse)
    with pytest.raises(UpdateError, match="path"):
        transaction.apply_update(root, operation.name)
    assert_old(root)
    assert_data(root)


@pytest.mark.skipif(os.name != "nt", reason="Windows file sharing")
def test_real_locked_executable_restores_previous_components(tmp_path):
    import ctypes
    from ctypes import wintypes
    root, operation = install_fixture(tmp_path)
    dll = ctypes.WinDLL("kernel32", use_last_error=True)
    dll.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                               wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    dll.CreateFileW.restype = wintypes.HANDLE
    dll.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = dll.CreateFileW(str(root / MANAGED[2]), 0x80000000, 1, None, 3, 0, None)
    assert handle != ctypes.c_void_p(-1).value
    try:
        with pytest.raises(OSError):
            transaction.apply_update(root, operation.name)
        assert_old(root)
        assert_data(root)
    finally:
        dll.CloseHandle(handle)


def helper_fixture(tmp_path, monkeypatch):
    from updater import helper
    root, operation = install_fixture(tmp_path)
    # execute() creates its own independently extracted and verified tree.
    import shutil
    shutil.rmtree(operation / "verified")
    transaction.write_json(root / "_internal" / "build-info.json", {
        "version": "v1.0.0", "build_type": "stable", "commit": "synthetic",
    })
    archive = make_archive(operation / "download.zip")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (operation / "checksum.txt").write_text(
        f"{digest} *OpenVPNManager-v1.10.0-windows-x64.zip\n")
    transaction.write_json(operation / "job.json", {
        "protocol": 1, "root": str(root), "id": operation.name,
        "version": "v1.10.0", "pid": 1, "creation": 1,
    })
    parent = SimpleNamespace(exited=lambda: True, close=lambda: None)
    monkeypatch.setattr(helper, "ProcessIdentity", lambda *args: parent)
    monkeypatch.setattr(helper, "preflight", lambda *args: None)
    monkeypatch.setattr(helper, "verify_startup", lambda *args: None)
    return helper, root, operation, parent


@pytest.mark.skipif(os.name != "nt", reason="Windows installation locks")
def test_helper_success_and_payload_cleanup(tmp_path, monkeypatch):
    helper, root, operation, _ = helper_fixture(tmp_path, monkeypatch)
    launched = []
    monkeypatch.setattr(helper, "launch", lambda path: launched.append(path))
    assert helper.execute(operation / "job.json") == 0
    assert launched == [root]
    assert transaction.load_journal(root)["phase"] == "installed"
    assert (operation / "backup" / MANAGED[0]).read_bytes() == b"old program"
    assert not (operation / "download.zip").exists()
    assert_data(root)


@pytest.mark.skipif(os.name != "nt", reason="Windows installation locks")
def test_failed_restart_restores_old_program(tmp_path, monkeypatch):
    helper, root, operation, _ = helper_fixture(tmp_path, monkeypatch)
    launches = []
    def launch(path):
        launches.append(path)
        if len(launches) == 1:
            raise OSError("process creation failed")
    monkeypatch.setattr(helper, "launch", launch)
    assert helper.execute(operation / "job.json") == 1
    assert launches == [root, root]
    assert_old(root)
    assert_data(root)
    assert transaction.load_journal(root)["phase"] == "rolled_back"


@pytest.mark.skipif(os.name != "nt", reason="Windows installation locks")
def test_helper_cancel_before_handoff_never_changes_program(tmp_path, monkeypatch):
    helper, root, operation, parent = helper_fixture(tmp_path, monkeypatch)
    parent.exited = lambda: False
    (operation / "cancel").touch()
    monkeypatch.setattr(helper, "launch", lambda _: pytest.fail("Must not restart"))
    assert helper.execute(operation / "job.json") == 1
    assert json.loads((operation / "error.json").read_text())["code"] == "cancelled"
    assert_old(root)
    assert_data(root)


@pytest.mark.skipif(os.name != "nt", reason="Windows installation locks")
def test_helper_refuses_second_application_instance(tmp_path, monkeypatch):
    from updater.windows import InstallationLock
    helper, root, operation, _ = helper_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(helper, "launch", lambda _: pytest.fail("Must not launch another instance"))
    with InstallationLock(root):
        assert helper.execute(operation / "job.json") == 1
    assert json.loads((operation / "error.json").read_text())["code"] == "busy"
    assert_old(root)
    assert_data(root)


def test_failed_preparation_cleans_download_without_modifying_data(tmp_path, monkeypatch):
    from updater import service
    from updater.release import Release
    root, _ = install_fixture(tmp_path)
    monkeypatch.setattr(service, "preflight", lambda *args: None)
    client = SimpleNamespace(fetch=lambda *args: (_ for _ in ()).throw(UpdateError("network")))
    before = set((root / transaction.WORK).iterdir())
    with pytest.raises(UpdateError, match="network"):
        service.prepare(root, Release("v1.1.0", "", "", "", "a.zip", 10), threading.Event(), lambda *a: None, client)
    assert set((root / transaction.WORK).iterdir()) == before
    assert_old(root)
    assert_data(root)
