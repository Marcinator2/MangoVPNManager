"""Prepare a verified update without closing the running application."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
from typing import Callable

from updater.package import MAX_UNPACKED, extract_package, verify_checksum
from updater.release import Release, ReleaseClient, UpdateError, check_cancel
from updater.transaction import WORK, create_operation, preflight, read_json, safe_path, safe_tree, write_json
from updater.windows import current_identity


def prepare(root: Path, release: Release, cancel: threading.Event,
            progress: Callable[[int, int], None], client: ReleaseClient | None = None) -> Path:
    preflight(root, release.size + 2 * MAX_UNPACKED)
    operation = create_operation(root)
    try:
        client = client or ReleaseClient()
        checksum = client.fetch(release.checksum_url, 4096, cancel)
        (operation / "checksum.txt").write_bytes(checksum)
        archive = operation / "download.zip"
        client.fetch(release.archive_url, release.size, cancel, archive, progress)
        if archive.stat().st_size != release.size:
            raise UpdateError("download_incomplete")
        verify_checksum(archive, checksum, release.archive_name, cancel)
        extract_package(archive, operation / "prepared", release.version, cancel)
        check_cancel(cancel)
        write_json(operation / "job.json", {
            "protocol": 1, "root": str(root), "id": operation.name,
            "version": release.version, "pid": os.getpid(),
            "creation": current_identity(root / "MangoVPNManager.exe"),
        })
        return operation
    except BaseException:
        safe_tree(operation)
        shutil.rmtree(operation)
        raise


def start_helper(root: Path, arguments: list[str], source: Path | None = None) -> tuple[subprocess.Popen, Path]:
    source = source or root / "MangoVPNUpdater.exe"
    cleanup_helper(root)
    safe_tree(source)
    temporary = Path(tempfile.mkdtemp(prefix="MangoVPNManager-updater-"))
    try:
        helper = temporary / "MangoVPNUpdater.exe"
        shutil.copy2(source, helper)
        environment = os.environ.copy()
        environment["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        work = safe_path(root / WORK)
        work.mkdir(exist_ok=True)
        write_json(work / "helper.json", {"directory": str(temporary)})
        process = subprocess.Popen([str(helper), *arguments], cwd=root, env=environment,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        return process, temporary
    except BaseException:
        shutil.rmtree(temporary)
        raise



def cleanup_helper(root: Path) -> bool:
    """Remove only our recorded temporary helper after Windows releases it."""
    state = root / WORK / "helper.json"
    try:
        if not safe_path(state).exists():
            return True
        directory = Path(read_json(state)["directory"])
        if (directory.parent != Path(tempfile.gettempdir())
                or not directory.name.startswith("MangoVPNManager-updater-")):
            raise UpdateError("path")
        safe_tree(directory)
        if directory.exists():
            if any(item.name != "MangoVPNUpdater.exe" for item in directory.iterdir()):
                raise UpdateError("path")
            # Unlink the executable first. Windows refuses this while it runs.
            (directory / "MangoVPNUpdater.exe").unlink(missing_ok=True)
            directory.rmdir()
        state.unlink()
        return True
    except (OSError, KeyError, TypeError, UpdateError):
        return False
