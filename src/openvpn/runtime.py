from __future__ import annotations

import csv
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


OPENVPN_SERVICE_NAME = "OpenVPNService"
STATUS_FILENAME = "mango-server-status.tsv"
STATUS_INTERVAL_SECONDS = 5
STATUS_STALE_AFTER_SECONDS = 20


@dataclass(frozen=True, slots=True)
class OpenVPNRuntimePaths:
    config_dir: Path
    log_dir: Path
    service_name: str = OPENVPN_SERVICE_NAME

    @property
    def status_path(self) -> Path:
        return self.log_dir / STATUS_FILENAME


@dataclass(frozen=True, slots=True)
class ClientConnection:
    common_name: str
    remote_address: str
    virtual_address: str
    connected_since: datetime | None


@dataclass(frozen=True, slots=True)
class StatusSnapshot:
    available: bool
    fresh: bool
    updated_at: datetime | None
    connections: dict[str, ClientConnection]


RegistryReader = Callable[[str], str | None]
CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


def _windows_registry_value(name: str) -> str | None:
    if sys.platform != "win32":
        return None
    try:
        import winreg
    except ImportError:
        return None

    access_modes = (winreg.KEY_READ | winreg.KEY_WOW64_64KEY, winreg.KEY_READ)
    for key_path in (r"SOFTWARE\OpenVPN", r"SOFTWARE\WOW6432Node\OpenVPN"):
        for access in access_modes:
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path, 0, access) as key:
                    value, _ = winreg.QueryValueEx(key, name)
            except OSError:
                continue
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def discover_openvpn_runtime(
    openvpn_root: Path,
    registry_reader: RegistryReader | None = None,
) -> OpenVPNRuntimePaths:
    """Discover service paths, preferring OpenVPN's machine configuration."""
    root = Path(openvpn_root).expanduser()
    read_registry = registry_reader or _windows_registry_value
    configured_config = read_registry("autostart_config_dir")
    configured_log = read_registry("log_dir")

    config_dir = Path(os.path.expandvars(configured_config)) if configured_config else root / "config-auto"
    log_dir = Path(os.path.expandvars(configured_log)) if configured_log else root / "log"
    return OpenVPNRuntimePaths(config_dir.resolve(), log_dir.resolve())


def openvpn_service_running(
    service_name: str = OPENVPN_SERVICE_NAME,
    runner: CommandRunner = subprocess.run,
) -> bool | None:
    if sys.platform != "win32":
        return None
    try:
        completed = runner(
            ["sc.exe", "query", service_name],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return False
    return bool(re.search(r"STATE\s*:\s*4\b", completed.stdout, re.IGNORECASE))


def _parse_timestamp(value: str) -> datetime | None:
    value = value.strip()
    if not value:
        return None
    try:
        return datetime.fromtimestamp(int(value), timezone.utc).astimezone()
    except (ValueError, OSError, OverflowError):
        pass
    for pattern in ("%Y-%m-%d %H:%M:%S", "%a %b %d %H:%M:%S %Y"):
        try:
            return datetime.strptime(value, pattern).replace(tzinfo=timezone.utc).astimezone()
        except ValueError:
            continue
    return None


def _remote_host(address: str) -> str:
    address = address.strip()
    if address.startswith("[") and "]:" in address:
        return address[1 : address.rfind("]:")]
    host, separator, port = address.rpartition(":")
    if separator and port.isdigit() and host:
        return host
    return address


def parse_status_text(content: str) -> dict[str, ClientConnection]:
    """Parse OpenVPN status versions 1-3 without exposing unrelated log data."""
    lines = [line for line in content.splitlines() if line.strip()]
    delimiter = "\t" if any("\t" in line for line in lines) else ","
    rows = list(csv.reader(lines, delimiter=delimiter))
    header: list[str] | None = None
    in_legacy_client_list = False
    connections: dict[str, ClientConnection] = {}
    for row in rows:
        if not row:
            continue
        record = row[0].strip()
        if record == "OpenVPN CLIENT LIST":
            in_legacy_client_list = True
            continue
        if record in {"ROUTING TABLE", "GLOBAL STATS", "END"}:
            in_legacy_client_list = False
            continue
        if record == "HEADER" and len(row) > 2 and row[1].strip() == "CLIENT_LIST":
            header = [value.strip() for value in row[2:]]
            continue
        if record == "CLIENT_LIST":
            values = [value.strip() for value in row[1:]]
            fields = dict(zip(header or (), values))
            common_name = fields.get("Common Name", values[0] if values else "")
            if not common_name:
                continue
            real_address = fields.get("Real Address", values[1] if len(values) > 1 else "")
            virtual_address = fields.get("Virtual Address", values[2] if len(values) > 2 else "")
            connected = fields.get("Connected Since (time_t)", "") or fields.get("Connected Since", "")
            connections[common_name.casefold()] = ClientConnection(
                common_name=common_name,
                remote_address=_remote_host(real_address),
                virtual_address=virtual_address,
                connected_since=_parse_timestamp(connected),
            )
            continue
        if header is None and in_legacy_client_list and record not in {
            "Updated",
            "Common Name",
            "Virtual Address",
        } and len(row) >= 5:
            common_name = row[0].strip()
            connections[common_name.casefold()] = ClientConnection(
                common_name=common_name,
                remote_address=_remote_host(row[1]),
                virtual_address="",
                connected_since=_parse_timestamp(row[4]),
            )
    return connections


def read_status_snapshot(
    path: Path,
    *,
    now: datetime | None = None,
    stale_after_seconds: int = STATUS_STALE_AFTER_SECONDS,
) -> StatusSnapshot:
    now = now or datetime.now(timezone.utc).astimezone()
    try:
        stat = path.stat()
        content = path.read_text(encoding="utf-8", errors="replace")
        updated_at = datetime.fromtimestamp(stat.st_mtime, timezone.utc).astimezone()
    except OSError:
        return StatusSnapshot(False, False, None, {})
    age = max(0.0, (now - updated_at).total_seconds())
    if not any(line.strip() == "END" for line in content.splitlines()):
        return StatusSnapshot(False, False, updated_at, {})
    try:
        connections = parse_status_text(content)
    except (csv.Error, UnicodeError):
        return StatusSnapshot(False, False, updated_at, {})
    return StatusSnapshot(True, age <= stale_after_seconds, updated_at, connections)
