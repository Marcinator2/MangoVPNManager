"""Validate every archive entry before extracting executable code."""
from __future__ import annotations

import hashlib
import re
import stat
import threading
import zipfile
from pathlib import Path, PurePosixPath

from config.version import read_build_info
from updater.release import UpdateError, check_cancel

MANAGED = ("OpenVPNManager.exe", "_internal", "OpenVPNUpdater.exe")
MAX_UNPACKED = 1536 * 1024 * 1024
MAX_ENTRIES = 20000
FORBIDDEN = {".db", ".sqlite", ".sqlite3", ".key", ".pem", ".p12", ".pfx",
             ".csr", ".req", ".crt", ".cer", ".ovpn"}


def verify_checksum(archive: Path, checksum: bytes, name: str, cancel: threading.Event) -> None:
    try:
        match = re.fullmatch(r"([a-fA-F0-9]{64}) [ *]" + re.escape(name) + r"\s*", checksum.decode("ascii"))
        if not match:
            raise UpdateError("checksum")
        digest = hashlib.sha256()
        with archive.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                check_cancel(cancel)
                digest.update(chunk)
        if digest.hexdigest() != match[1].lower():
            raise UpdateError("checksum")
    except UnicodeError as exc:
        raise UpdateError("checksum") from exc


def archive_entries(archive: zipfile.ZipFile) -> list[tuple[zipfile.ZipInfo, Path]]:
    entries = archive.infolist()
    if not entries or len(entries) > MAX_ENTRIES or sum(i.file_size for i in entries) > MAX_UNPACKED:
        raise UpdateError("package_invalid")
    seen: dict[str, bool] = {}
    result = []
    for entry in entries:
        name = entry.filename
        parts = name.rstrip("/").split("/")
        if (entry.orig_filename != name or "\\" in name or entry.flag_bits & 1
                or not parts or parts[0] != "OpenVPNManager"):
            raise UpdateError("package_invalid")
        mode = entry.external_attr >> 16
        if stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
            raise UpdateError("package_invalid")
        for part in parts:
            if (not part or part in {".", ".."} or part.endswith((".", " "))
                    or any(ord(c) < 32 or ord(c) == 127 or c in '<>:"|?*' for c in part)
                    or re.fullmatch(r"(?i)(con|prn|aux|nul|com[0-9¹²³]|lpt[0-9¹²³])(?:\..*)?", part)):
                raise UpdateError("package_invalid")
        key = "/".join(parts).casefold()
        if key in seen:
            raise UpdateError("package_invalid")
        seen[key] = entry.is_dir()
        if len(parts) == 1:
            if not entry.is_dir():
                raise UpdateError("package_invalid")
            continue
        if parts[1] not in MANAGED or (parts[1] != "_internal" and (len(parts) != 2 or entry.is_dir())):
            raise UpdateError("package_invalid")
        if parts[1] == "_internal" and len(parts) == 2 and not entry.is_dir():
            raise UpdateError("package_invalid")
        leaf = PurePosixPath(name).name.lower()
        if PurePosixPath(name).suffix.lower() in FORBIDDEN or leaf == "settings.json" or leaf.endswith("status.tsv"):
            raise UpdateError("package_invalid")
        result.append((entry, Path(*parts[1:])))
    for key in seen:
        parents = key.split("/")[:-1]
        for count in range(1, len(parents) + 1):
            if seen.get("/".join(parents[:count])) is False:
                raise UpdateError("package_invalid")
    required = {f"openvpnmanager/{name.lower()}": False for name in (MANAGED[0], MANAGED[2])}
    required["openvpnmanager/_internal/build-info.json"] = False
    if any(seen.get(name) is not directory for name, directory in required.items()):
        raise UpdateError("package_invalid")
    return result


def extract_package(archive_path: Path, destination: Path, version: str, cancel: threading.Event) -> None:
    try:
        with zipfile.ZipFile(archive_path) as archive:
            entries = archive_entries(archive)
            destination.mkdir(exist_ok=False)
            for entry, relative in entries:
                check_cancel(cancel)
                target = destination / relative
                if entry.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(entry) as source, target.open("xb") as output:
                    while chunk := source.read(1024 * 1024):
                        check_cancel(cancel)
                        output.write(chunk)
        info = read_build_info(destination / "_internal" / "build-info.json")
        if info.build_type != "stable" or info.version != version:
            raise UpdateError("package_invalid")
    except (zipfile.BadZipFile, NotImplementedError, RuntimeError) as exc:
        raise UpdateError("package_invalid") from exc
