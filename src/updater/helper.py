"""Standalone updater entry point. This executable never imports Qt."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

from config.version import read_build_info, version_tuple
from updater.package import extract_package, verify_checksum
from updater.release import Cancelled, UpdateError
from updater.transaction import (
    WORK, apply_update, clean_obsolete, clean_payload, load_journal, operation_dir, preflight,
    read_json, recover, rollback, safe_path, set_phase, write_json,
)
from updater.windows import InstallationLock, ProcessIdentity


class FileCancellation(threading.Event):
    def __init__(self, path: Path) -> None:
        super().__init__()
        self.path = path

    def is_set(self) -> bool:
        return self.path.exists()


def verify_startup(root: Path, cancel: FileCancellation) -> None:
    environment = os.environ.copy()
    environment["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    process = subprocess.Popen([str(root / "OpenVPNManager.exe"), "--smoke-test"],
                               cwd=root, env=environment)
    try:
        deadline = time.monotonic() + 30
        while process.poll() is None:
            if cancel.is_set():
                raise Cancelled()
            if time.monotonic() >= deadline:
                raise UpdateError("package_invalid")
            time.sleep(0.1)
        if process.returncode != 0:
            raise UpdateError("package_invalid")
    finally:
        if process.poll() is None:
            # Only the isolated test process owned by this helper is stopped.
            process.terminate()
            process.wait(timeout=10)


def launch(root: Path) -> None:
    # Do not reuse the one-file helper's PyInstaller extraction environment.
    environment = os.environ.copy()
    environment["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    subprocess.Popen([str(root / "OpenVPNManager.exe")], cwd=root, env=environment)


def execute(job_path: Path) -> int:
    job = read_json(job_path)
    root = safe_path(Path(job["root"]))
    operation = operation_dir(root, job["id"])
    if job_path != operation / "job.json" or job.get("protocol") != 1:
        raise UpdateError("path")
    version_tuple(job["version"])
    cancel = FileCancellation(operation / "cancel")
    parent = ProcessIdentity(job["pid"], root / "OpenVPNManager.exe", job["creation"])
    changed = False
    update_lock = InstallationLock(root, "update").acquire()
    app_lock = InstallationLock(root)
    try:
        preflight(root, 1536 * 1024 * 1024)
        installed = read_build_info(root / "_internal" / "build-info.json")
        if installed.build_type != "stable" or version_tuple(job["version"]) <= version_tuple(installed.version):
            raise UpdateError("release_invalid")
        name = f"OpenVPNManager-{job['version']}-windows-x64.zip"
        verify_checksum(operation / "download.zip", (operation / "checksum.txt").read_bytes(), name, cancel)
        extract_package(operation / "download.zip", operation / "verified", job["version"], cancel)
        verify_startup(operation / "verified", cancel)
        if cancel.is_set():
            raise Cancelled()
        write_json(operation / "ready.json", {"ready": True})
        deadline = time.monotonic() + 60
        while not parent.exited():
            if cancel.is_set():
                raise Cancelled()
            if time.monotonic() >= deadline:
                raise UpdateError("process")
            time.sleep(0.1)
        if cancel.is_set():
            raise Cancelled()
        app_lock.acquire()
        set_phase(root, job["id"], "prepared")
        apply_update(root, job["id"])
        changed = True
        try:
            write_json(root / WORK / "result.json", {"code": "success"})
        except OSError:
            pass
        try:
            clean_payload(root, job["id"])
            clean_obsolete(root, job["id"])
        except (OSError, UpdateError):
            pass
        app_lock.close()
        update_lock.close()
        try:
            launch(root)
        except OSError:
            update_lock.acquire()
            app_lock.acquire()
            rollback(root, job["id"])
            changed = False
            raise UpdateError("restart")
        return 0
    except Exception as exc:
        code = exc.code if isinstance(exc, UpdateError) else "install"
        write_json(operation / "error.json", {"code": code})
        if parent.exited() and not changed and code != "busy":
            journal = load_journal(root)
            if journal and journal["phase"] == "applying":
                recover(root)
            write_json(root / WORK / "result.json", {"code": code})
            app_lock.close()
            update_lock.close()
            launch(root)
        return 1
    finally:
        parent.close()
        app_lock.close()
        update_lock.close()


def recover_installation(root: Path) -> int:
    safe_path(root)
    update_lock = InstallationLock(root, "update")
    app_lock = InstallationLock(root)
    deadline = time.monotonic() + 60
    while True:
        try:
            update_lock.acquire()
            app_lock.acquire()
            break
        except UpdateError:
            app_lock.close()
            update_lock.close()
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.2)
    try:
        journal = load_journal(root)
        if not journal or journal["phase"] != "applying":
            raise UpdateError("recovery")
        recover(root)
        write_json(root / WORK / "result.json", {"code": "recovered"})
    finally:
        app_lock.close()
        update_lock.close()
    launch(root)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--job", type=Path)
    modes.add_argument("--recover", type=Path)
    args = parser.parse_args()
    try:
        if args.recover and Path(sys.executable).is_relative_to(args.recover):
            from updater.service import start_helper
            start_helper(args.recover, ["--recover", str(args.recover)], Path(sys.executable))
            return 0
        return execute(args.job) if args.job else recover_installation(args.recover)
    except Exception:
        # Never emit file contents or subprocess output.
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
