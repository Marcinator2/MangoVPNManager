"""Exercise the packaged updater using disposable synthetic installations only."""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from config.settings import AppSettings, save_settings
from database.database import Database
from updater.package import MANAGED
from updater.service import cleanup_helper, start_helper
from updater.transaction import WORK, create_operation, load_journal, safe_tree, write_json
from updater.windows import ProcessIdentity, kernel


def stop_test_application(executable: Path) -> None:
    """Stop only processes whose open OS handle identifies our temporary EXE."""
    dll = kernel()
    dll.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    psapi = ctypes.WinDLL("psapi")
    identifiers = (wintypes.DWORD * 8192)()
    needed = wintypes.DWORD()
    if not psapi.EnumProcesses(identifiers, ctypes.sizeof(identifiers), ctypes.byref(needed)):
        raise OSError("Could not enumerate test processes")
    for pid in identifiers[:needed.value // ctypes.sizeof(wintypes.DWORD)]:
        handle = dll.OpenProcess(0x1000 | 0x100000 | 0x1, False, pid)
        if not handle:
            continue
        try:
            buffer = ctypes.create_unicode_buffer(32768)
            length = wintypes.DWORD(len(buffer))
            if (dll.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(length))
                    and Path(buffer.value) == executable):
                # This is a test-owned process in a unique temporary directory.
                dll.TerminateProcess(handle, 0)
                if dll.WaitForSingleObject(handle, 10000) != 0:
                    raise OSError("Test process did not exit")
        finally:
            dll.CloseHandle(handle)


def smoke_update(source: Path) -> None:
    for name in MANAGED:
        safe_tree(source / name)
        if not (source / name).exists():
            raise ValueError("Build the application and updater first")
    environment = os.environ.copy()
    environment["QT_QPA_PLATFORM"] = "offscreen"
    # A restarted GUI cannot contact GitHub or a configured external proxy.
    environment["HTTPS_PROXY"] = "http://127.0.0.1:9"
    environment["HTTP_PROXY"] = "http://127.0.0.1:9"
    environment["NO_PROXY"] = ""
    os.environ.update({key: environment[key] for key in (
        "QT_QPA_PLATFORM", "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY")})
    with tempfile.TemporaryDirectory(prefix="MangoVPNManager-update-smoke-") as directory:
        temporary = Path(directory)
        root = temporary / "Application with spaces"
        root.mkdir()
        for name in MANAGED:
            if (source / name).is_dir():
                shutil.copytree(source / name, root / name)
            else:
                shutil.copy2(source / name, root / name)
        metadata = root / "_internal" / "build-info.json"
        old_info = {"version": "v1.0.0", "build_type": "stable", "commit": "synthetic"}
        write_json(metadata, old_info)
        database = Database(root / "data" / "test.db")
        database.add_branch_with_mangos("0004", 1, "Synthetic smoke test")
        database.close()
        # The real app uses this name, so the restart opens only synthetic data.
        (root / "data" / "test.db").rename(root / "data" / "mango_vpn_manager.db")
        save_settings(AppSettings(pki_path=temporary / "pki",
                                  openvpn_root=temporary / "OpenVPN",
                                  easyrsa_root=temporary / "EasyRSA"),
                      root / "data" / "settings.json")
        (root / "keep.txt").write_bytes(b"unmanaged synthetic content")
        preserved = {path: path.read_bytes() for path in [
            root / "data" / "mango_vpn_manager.db", root / "data" / "settings.json", root / "keep.txt",
        ]}
        operation = create_operation(root)
        name = "MangoVPNManager-v1.1.0-windows-x64.zip"
        archive_path = operation / "download.zip"
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for managed in MANAGED:
                item = root / managed
                entries = list(item.rglob("*")) if item.is_dir() else [item]
                for path in entries:
                    if not path.is_file():
                        continue
                    archive_name = "MangoVPNManager/" + path.relative_to(root).as_posix()
                    if path == metadata:
                        archive.writestr(archive_name, json.dumps({**old_info, "version": "v1.1.0"}))
                    else:
                        archive.write(path, archive_name)
        digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
        (operation / "checksum.txt").write_text(f"{digest} *{name}\n", encoding="ascii")
        parent = subprocess.Popen([str(root / MANAGED[0]), "--smoke-test", "--smoke-test-delay=15000"],
                                  cwd=root, env=environment)
        helper = None
        helper_directory = None
        try:
            time.sleep(1)
            identity = ProcessIdentity(parent.pid, root / MANAGED[0])
            creation = identity.creation
            identity.close()
            write_json(operation / "job.json", {
                "protocol": 1, "root": str(root), "id": operation.name,
                "version": "v1.1.0", "pid": parent.pid, "creation": creation,
            })
            helper, helper_directory = start_helper(root, ["--job", str(operation / "job.json")])
            result = helper.wait(timeout=90)
            if result != 0:
                error_file = operation / "error.json"
                error = json.loads(error_file.read_text())["code"] if error_file.exists() else "helper startup"
                raise AssertionError(f"Packaged update failed: {error}")
            assert parent.wait(timeout=10) == 0
            assert load_journal(root)["phase"] == "installed"
            assert json.loads(metadata.read_text())["version"] == "v1.1.0"
            assert (operation / "backup" / MANAGED[0]).is_file()
            # Stop the restarted test GUI before it performs periodic work.
            stop_test_application(root / MANAGED[0])
            for path, data in preserved.items():
                assert path.read_bytes() == data, f"Modified synthetic user data: {path.name}"
            subprocess.run([str(root / MANAGED[0]), "--smoke-test"], cwd=root,
                           env=environment, check=True, timeout=30)
            print("Packaged startup, parent handoff, replacement, backup and data preservation passed.")
        finally:
            if helper and helper.poll() is None:
                (operation / "cancel").touch()
                try:
                    helper.wait(timeout=35)
                except subprocess.TimeoutExpired:
                    helper.terminate()
                    helper.wait(timeout=10)
            if parent.poll() is None:
                parent.terminate()
                parent.wait(timeout=10)
            stop_test_application(root / MANAGED[0])
            cleanup_helper(root)
            if helper_directory and helper_directory.exists():
                safe_tree(helper_directory)
                shutil.rmtree(helper_directory)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("application_directory", type=Path)
    args = parser.parse_args()
    smoke_update(args.application_directory.resolve())
