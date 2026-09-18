"""Recoverable replacement of exactly the three managed application entries.

The journal is persisted before any rename. During rollback, the presence of
each backup is authoritative, including after interruption between renames.
No database, PKI, or other user files are copied or restored.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import stat
import uuid

from updater.package import MANAGED
from updater.release import UpdateError

WORK = ".mango-update"


def safe_path(path: Path) -> Path:
    absolute = Path(os.path.abspath(path))
    if not path.is_absolute() or ".." in path.parts or absolute == Path(absolute.anchor):
        raise UpdateError("path")
    for item in (absolute, *absolute.parents):
        try:
            attributes = item.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(attributes.st_mode) or getattr(attributes, "st_file_attributes", 0) & 0x400:
            raise UpdateError("path")
    return absolute


def safe_tree(path: Path) -> None:
    safe_path(path)
    if path.is_dir():
        for child in path.iterdir():
            safe_tree(child)


def read_json(path: Path) -> dict:
    safe_path(path)
    if path.stat().st_size > 65536:
        raise UpdateError("recovery")
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(result, dict):
            raise ValueError("Not an object")
        return result
    except (ValueError, UnicodeError) as exc:
        raise UpdateError("recovery") from exc


def write_json(path: Path, data: dict) -> None:
    safe_path(path)
    temporary = path.with_suffix(".new")
    safe_path(temporary)
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(data, stream)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def validate_installation(root: Path) -> None:
    safe_path(root)
    if not root.is_dir():
        raise UpdateError("path")
    for name in MANAGED:
        target = root / name
        safe_tree(target)
        if not (target.is_dir() if name == "_internal" else target.is_file()):
            raise UpdateError("package_invalid")
    safe_tree(root / WORK)


def preflight(root: Path, required_space: int) -> None:
    validate_installation(root)
    if shutil.disk_usage(root).free < required_space:
        raise UpdateError("space")
    probe = root / (".mango-write-" + uuid.uuid4().hex)
    try:
        probe.mkdir()
        child = probe / "probe"
        child.write_bytes(b"write-access-check")
        child.rename(probe / "renamed")
        (probe / "renamed").unlink()
        probe.rmdir()
        # Opening with DELETE access detects protected managed entries without
        # changing them. Actual sharing locks are checked again during rename.
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            dll = ctypes.WinDLL("kernel32", use_last_error=True)
            dll.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                       ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
            dll.CreateFileW.restype = wintypes.HANDLE
            dll.CloseHandle.argtypes = [wintypes.HANDLE]
            for name in MANAGED:
                handle = dll.CreateFileW(str(root / name), 0x10000, 7, None, 3, 0x02000000, None)
                if handle == ctypes.c_void_p(-1).value:
                    # A running image may deny DELETE sharing. Permission denied
                    # is actionable now; sharing violations are handled later.
                    if ctypes.get_last_error() != 32:
                        raise PermissionError("Managed entry is not writable")
                else:
                    dll.CloseHandle(handle)
    except OSError as exc:
        raise UpdateError("permissions") from exc
    finally:
        if probe.exists():
            safe_tree(probe)
            shutil.rmtree(probe)


def operation_dir(root: Path, identifier: str) -> Path:
    if not isinstance(identifier, str) or len(identifier) != 32:
        raise UpdateError("recovery")
    try:
        if uuid.UUID(hex=identifier).hex != identifier:
            raise ValueError("Invalid operation")
    except ValueError as exc:
        raise UpdateError("recovery") from exc
    return safe_path(root / WORK / identifier)


def load_journal(root: Path) -> dict | None:
    path = safe_path(root / WORK / "journal.json")
    if not path.exists():
        return None
    data = read_json(path)
    operation_dir(root, data.get("id"))
    if data.get("phase") not in {"prepared", "applying", "installed", "rolled_back"}:
        raise UpdateError("recovery")
    return data


def set_phase(root: Path, identifier: str, phase: str) -> None:
    write_json(root / WORK / "journal.json", {"id": identifier, "phase": phase})


def create_operation(root: Path) -> Path:
    validate_installation(root)
    journal = load_journal(root)
    if journal and journal["phase"] == "applying":
        raise UpdateError("recovery")
    work = root / WORK
    work.mkdir(exist_ok=True)
    operation = operation_dir(root, uuid.uuid4().hex)
    operation.mkdir()
    return operation


def rollback(root: Path, identifier: str) -> None:
    operation = operation_dir(root, identifier)
    backup = operation / "backup"
    safe_tree(operation)
    set_phase(root, identifier, "applying")
    failed = operation / "failed"
    failed.mkdir(exist_ok=True)
    for name in reversed(MANAGED):
        target, old = root / name, backup / name
        safe_tree(target)
        if old.exists():
            if target.exists():
                # Unique destinations also make repeated recovery safe if a
                # previous attempt was interrupted after quarantining a file.
                target.rename(failed / (uuid.uuid4().hex + "-" + name))
            old.rename(target)
        elif not target.exists():
            raise UpdateError("recovery")
    set_phase(root, identifier, "rolled_back")


def recover(root: Path) -> bool:
    journal = load_journal(root)
    if journal and journal["phase"] == "applying":
        rollback(root, journal["id"])
        return True
    return False


def apply_update(root: Path, identifier: str) -> None:
    validate_installation(root)
    operation = operation_dir(root, identifier)
    staged, backup = operation / "verified", operation / "backup"
    for name in MANAGED:
        if not (staged / name).exists():
            raise UpdateError("package_invalid")
    safe_tree(operation)
    backup.mkdir(exist_ok=False)
    set_phase(root, identifier, "applying")
    try:
        for name in MANAGED:
            safe_tree(root / name)
            safe_tree(staged / name)
            (root / name).rename(backup / name)
            (staged / name).rename(root / name)
        set_phase(root, identifier, "installed")
    except BaseException:
        rollback(root, identifier)
        raise


def clean_obsolete(root: Path, keep: str) -> None:
    """Keep the current backup; remove only recognized completed operations."""
    work = safe_path(root / WORK)
    for candidate in work.iterdir():
        if candidate.name == keep or not candidate.is_dir():
            continue
        try:
            operation_dir(root, candidate.name)
            job = read_json(candidate / "job.json")
            if job.get("id") != candidate.name or job.get("root") != str(root):
                continue
            safe_tree(candidate)
            shutil.rmtree(candidate)
        except (OSError, UpdateError):
            continue


def discard_operation(root: Path, operation: Path) -> None:
    if operation_dir(root, operation.name) != operation:
        raise UpdateError("path")
    journal = load_journal(root)
    if journal and journal["id"] == operation.name and journal["phase"] in {"applying", "installed"}:
        return
    if operation.exists():
        safe_tree(operation)
        shutil.rmtree(operation)


def clean_payload(root: Path, identifier: str) -> None:
    operation = operation_dir(root, identifier)
    for name in ("prepared", "verified", "download.zip", "checksum.txt"):
        target = operation / name
        safe_tree(target)
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
