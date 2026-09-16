from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from openvpn.runtime import (
    discover_openvpn_runtime,
    parse_status_text,
    read_status_snapshot,
)


STATUS_V3 = """TITLE\tOpenVPN 2.7
TIME\t2026-09-16 10:00:05\t1789552805
HEADER\tCLIENT_LIST\tCommon Name\tReal Address\tVirtual Address\tVirtual IPv6 Address\tBytes Received\tBytes Sent\tConnected Since\tConnected Since (time_t)\tUsername\tClient ID\tPeer ID\tData Channel Cipher
CLIENT_LIST\t0004_Mango1\t203.0.113.7:45678\t10.8.4.1\t\t100\t200\t2026-09-16 10:00:00\t1789552800\tUNDEF\t0\t0\tAES-256-GCM
END
"""


def test_discovers_registry_paths_instead_of_assuming_defaults(tmp_path: Path) -> None:
    values = {
        "autostart_config_dir": str(tmp_path / "service-config"),
        "log_dir": str(tmp_path / "service-log"),
    }
    runtime = discover_openvpn_runtime(
        tmp_path / "OpenVPN",
        registry_reader=values.get,
    )
    assert runtime.config_dir == (tmp_path / "service-config").resolve()
    assert runtime.status_path == (tmp_path / "service-log" / "mango-server-status.tsv").resolve()


def test_status_version_three_exposes_connection_details() -> None:
    connections = parse_status_text(STATUS_V3)
    connection = connections["0004_mango1"]
    assert connection.remote_address == "203.0.113.7"
    assert connection.virtual_address == "10.8.4.1"
    assert connection.connected_since is not None


def test_legacy_status_does_not_treat_routes_as_clients() -> None:
    content = """OpenVPN CLIENT LIST
Updated,Wed Sep 16 10:00:05 2026
Common Name,Real Address,Bytes Received,Bytes Sent,Connected Since
0004_Mango1,203.0.113.7:45678,100,200,Wed Sep 16 10:00:00 2026
ROUTING TABLE
Virtual Address,Common Name,Real Address,Last Ref
10.8.4.1,0004_Mango1,203.0.113.7:45678,Wed Sep 16 10:00:04 2026
GLOBAL STATS
Max bcast/mcast queue length,0
END
"""
    assert list(parse_status_text(content)) == ["0004_mango1"]


def test_status_snapshot_detects_stale_file(tmp_path: Path) -> None:
    path = tmp_path / "status.tsv"
    path.write_text(STATUS_V3, encoding="utf-8")
    modified = datetime.now(timezone.utc) - timedelta(seconds=60)
    os.utime(path, (modified.timestamp(), modified.timestamp()))
    snapshot = read_status_snapshot(path, now=datetime.now(timezone.utc))
    assert snapshot.available
    assert not snapshot.fresh
    assert "0004_mango1" in snapshot.connections


def test_status_snapshot_rejects_partially_written_file(tmp_path: Path) -> None:
    path = tmp_path / "status.tsv"
    path.write_text(STATUS_V3.removesuffix("END\n"), encoding="utf-8")
    snapshot = read_status_snapshot(path)
    assert not snapshot.available
    assert not snapshot.fresh
    assert snapshot.connections == {}
