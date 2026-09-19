from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Callable

from openvpn.addressing import ValidationError
from openvpn.exporter import ExportBundle


ACLResetter = Callable[[list[Path]], None]
ACLChecker = Callable[[Path], bool]


@dataclass(frozen=True, slots=True)
class ServerInstallPlan:
    config_dir: Path
    files: dict[str, str]
    collisions: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class ServerInstallStatus:
    state: str
    total_files: int
    current_files: int
    missing_files: tuple[Path, ...] = ()
    changed_files: tuple[Path, ...] = ()

    @property
    def installation_needed(self) -> bool:
        return self.state in {
            "not_installed",
            "update_required",
            "permissions_repair_required",
        }


def build_server_install_plan(bundle: ExportBundle, config_dir: Path) -> ServerInstallPlan:
    if not bundle.ready_for_export:
        raise ValidationError("The complete configuration is not ready for installation.")
    requested_dir = Path(config_dir).expanduser()
    if requested_dir.is_symlink():
        raise ValidationError("The OpenVPN configuration directory cannot be a symbolic link.")
    target_dir = requested_dir.resolve()
    if target_dir == Path(target_dir.anchor):
        raise ValidationError("The OpenVPN configuration target cannot be a drive root.")
    if not target_dir.parent.exists():
        raise ValidationError("The detected OpenVPN installation directory does not exist.")
    files = {
        relative: content
        for relative, content in bundle.files.items()
        if relative == "server.ovpn" or relative.startswith("ccd/")
    }
    if "server.ovpn" not in files or not any(name.startswith("ccd/") for name in files):
        raise ValidationError("The server configuration bundle is incomplete.")
    for relative in files:
        path = PurePosixPath(relative)
        if path.is_absolute() or ".." in path.parts:
            raise ValidationError(f"Unsafe installation path: {relative}")
    collisions = tuple(target_dir / relative for relative in files if (target_dir / relative).exists())
    return ServerInstallPlan(target_dir, files, collisions)


def windows_acl_inherits(
    path: Path,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> bool:
    if os.name != "nt":
        return True
    try:
        completed = runner(
            ["icacls", str(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0 and "(I)" in completed.stdout


def reset_installed_file_acls(
    paths: list[Path],
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> None:
    if os.name != "nt":
        return
    for path in paths:
        try:
            completed = runner(
                ["icacls", str(path), "/reset"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise OSError(
                f"Could not reset inherited permissions for {path.name}."
            ) from exc
        if completed.returncode != 0:
            raise OSError(
                f"Could not reset inherited permissions for {path.name}. "
                "Administrator rights may be required."
            )


def inspect_server_installation(
    plan: ServerInstallPlan,
    *,
    acl_checker: ACLChecker = windows_acl_inherits,
) -> ServerInstallStatus:
    missing: list[Path] = []
    changed: list[Path] = []
    current = 0
    for relative, expected in plan.files.items():
        target = plan.config_dir / relative
        try:
            actual = target.read_text(encoding="utf-8", errors="strict")
        except FileNotFoundError:
            missing.append(target)
            continue
        except PermissionError:
            return ServerInstallStatus(
                "permissions_repair_required",
                len(plan.files),
                current,
            )
        except (OSError, UnicodeError):
            return ServerInstallStatus("unknown", len(plan.files), current)
        normalized_actual = actual.replace("\r\n", "\n")
        normalized_expected = expected.replace("\r\n", "\n")
        if normalized_actual == normalized_expected:
            current += 1
        else:
            changed.append(target)

    if current == len(plan.files):
        server_config = plan.config_dir / "server.ovpn"
        state = (
            "current"
            if acl_checker(server_config)
            else "permissions_repair_required"
        )
    elif len(missing) == len(plan.files):
        state = "not_installed"
    else:
        state = "update_required"
    return ServerInstallStatus(
        state,
        len(plan.files),
        current,
        tuple(missing),
        tuple(changed),
    )


def install_server_files(
    plan: ServerInstallPlan,
    *,
    replace: bool = False,
    acl_resetter: ACLResetter = reset_installed_file_acls,
) -> list[Path]:
    if plan.collisions and not replace:
        raise FileExistsError("OpenVPN server files already exist.")
    plan.config_dir.mkdir(parents=True, exist_ok=True)
    if plan.config_dir.is_symlink():
        raise ValidationError("The OpenVPN configuration directory cannot be a symbolic link.")

    staging = Path(
        tempfile.mkdtemp(prefix=".mango-install-", dir=plan.config_dir.parent)
    )
    backup_root = (
        plan.config_dir.parent
        / "OpenVPNManager-backups"
        / datetime.now().strftime("%Y%m%d-%H%M%S")
    )
    written: list[Path] = []
    replaced: list[tuple[Path, Path]] = []
    try:
        for relative, content in plan.files.items():
            staged_file = staging / relative
            staged_file.parent.mkdir(parents=True, exist_ok=True)
            staged_file.write_text(content, encoding="utf-8", newline="\n")

        for relative in plan.files:
            target = plan.config_dir / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.parent.is_symlink() or not target.parent.resolve().is_relative_to(plan.config_dir):
                raise ValidationError(f"Unsafe OpenVPN target path: {relative}")
            if target.exists():
                backup = backup_root / relative
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, backup)
                replaced.append((target, backup))
            os.replace(staging / relative, target)
            written.append(target)
        acl_resetter(written)
    except Exception:
        for target in reversed(written):
            backup = backup_root / target.relative_to(plan.config_dir)
            if backup.exists():
                os.replace(backup, target)
            elif target.exists():
                target.unlink()
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        if backup_root.exists() and not replaced:
            shutil.rmtree(backup_root, ignore_errors=True)
    return written


def repair_server_file_acls(
    plan: ServerInstallPlan,
    *,
    acl_resetter: ACLResetter = reset_installed_file_acls,
) -> list[Path]:
    targets = [plan.config_dir / relative for relative in plan.files]
    missing = [path for path in targets if not path.is_file()]
    if missing:
        raise ValidationError(
            "Missing OpenVPN server files must be installed before permissions can be repaired."
        )
    acl_resetter(targets)
    return targets


def restart_openvpn_service(service_name: str) -> None:
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    stop = subprocess.run(
        ["sc.exe", "stop", service_name],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
        creationflags=creationflags,
    )
    stop_text = f"{stop.stdout}\n{stop.stderr}".upper()
    if stop.returncode != 0 and "SERVICE_NOT_ACTIVE" not in stop_text and "1062" not in stop_text:
        raise OSError("The OpenVPN service could not be stopped. Administrator rights may be required.")
    deadline = time.monotonic() + 20
    while stop.returncode == 0 and time.monotonic() < deadline:
        query = subprocess.run(
            ["sc.exe", "query", service_name],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3,
            check=False,
            creationflags=creationflags,
        )
        if re.search(r"STATE\s*:\s*1\b", query.stdout, re.IGNORECASE):
            break
        time.sleep(0.25)
    start = subprocess.run(
        ["sc.exe", "start", service_name],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
        creationflags=creationflags,
    )
    start_text = f"{start.stdout}\n{start.stderr}".upper()
    if start.returncode != 0 and "SERVICE_ALREADY_RUNNING" not in start_text and "1056" not in start_text:
        raise OSError("The OpenVPN service could not be started. Administrator rights may be required.")
