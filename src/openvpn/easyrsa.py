from __future__ import annotations

import csv
import io
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


DEFAULT_OPENVPN_ROOT = Path(r"C:\Program Files\OpenVPN")
DEFAULT_EASYRSA_ROOT = DEFAULT_OPENVPN_ROOT / "easy-rsa"
DEFAULT_PKI_PATH = Path(r"C:\ProgramData\MangoVPNManager\pki")
OPENVPN_SERVICE_ACCOUNT = r"NT SERVICE\OpenVPNService"
_SAFE_COMMON_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


class EasyRSAError(RuntimeError):
    """A safe, user-facing Easy-RSA operation error."""


@dataclass(frozen=True, slots=True)
class EasyRSAPaths:
    openvpn_root: Path = DEFAULT_OPENVPN_ROOT
    easyrsa_root: Path = DEFAULT_EASYRSA_ROOT
    pki_path: Path = DEFAULT_PKI_PATH

    @property
    def shell(self) -> Path:
        return self.easyrsa_root / "bin" / "sh.exe"

    @property
    def script(self) -> Path:
        return self.easyrsa_root / "easyrsa"

    @property
    def openssl(self) -> Path:
        return self.openvpn_root / "bin" / "openssl.exe"

    @property
    def openvpn(self) -> Path:
        return self.openvpn_root / "bin" / "openvpn.exe"


@dataclass(frozen=True, slots=True)
class PKIStatus:
    installation_ready: bool
    pki_initialized: bool
    ca_certificate_exists: bool
    ca_key_exists: bool

    @property
    def ca_ready(self) -> bool:
        return self.ca_certificate_exists and self.ca_key_exists


@dataclass(frozen=True, slots=True)
class CertificateStatus:
    certificate_exists: bool
    private_key_exists: bool

    @property
    def complete(self) -> bool:
        return self.certificate_exists and self.private_key_exists


@dataclass(frozen=True, slots=True)
class ServerMaterialStatus:
    certificate_exists: bool
    private_key_exists: bool
    tls_crypt_key_exists: bool

    @property
    def complete(self) -> bool:
        return (
            self.certificate_exists
            and self.private_key_exists
            and self.tls_crypt_key_exists
        )


@dataclass(frozen=True, slots=True)
class EasyRSAResult:
    output: str


Runner = Callable[..., subprocess.CompletedProcess[str]]
AclHardener = Callable[[Path], None]


class EasyRSAService:
    def __init__(
        self,
        paths: EasyRSAPaths,
        runner: Runner = subprocess.run,
        acl_hardener: AclHardener | None = None,
    ) -> None:
        self.paths = paths
        self._runner = runner
        self._acl_hardener = acl_hardener or harden_windows_acl

    def status(self) -> PKIStatus:
        pki = self.paths.pki_path
        return PKIStatus(
            installation_ready=all(
                path.is_file()
                for path in (
                    self.paths.shell,
                    self.paths.script,
                    self.paths.openssl,
                    self.paths.openvpn,
                )
            ),
            pki_initialized=(
                (pki / "private").is_dir()
                and (pki / "issued").is_dir()
                and (pki / "reqs").is_dir()
                and any(
                    (pki / marker).is_file()
                    for marker in ("vars.example", "openssl-easyrsa.cnf", "index.txt")
                )
            ),
            ca_certificate_exists=(pki / "ca.crt").is_file(),
            ca_key_exists=(pki / "private" / "ca.key").is_file(),
        )

    def certificate_status(self, common_name: str) -> CertificateStatus:
        common_name = validate_common_name(common_name)
        return CertificateStatus(
            certificate_exists=(self.paths.pki_path / "issued" / f"{common_name}.crt").is_file(),
            private_key_exists=(self.paths.pki_path / "private" / f"{common_name}.key").is_file(),
        )

    def server_material_status(
        self,
        common_name: str = "server",
    ) -> ServerMaterialStatus:
        certificate = self.certificate_status(common_name)
        return ServerMaterialStatus(
            certificate_exists=certificate.certificate_exists,
            private_key_exists=certificate.private_key_exists,
            tls_crypt_key_exists=any(
                (self.paths.pki_path / name).is_file()
                for name in ("ta.key", "tls-crypt.key")
            ),
        )

    def version(self) -> str:
        result = self._execute("--version", batch=False)
        for line in result.output.splitlines():
            if line.startswith("Version:"):
                return line.partition(":")[2].strip()
        return "Unknown"

    def initialize_ca(
        self,
        common_name: str = "MangoVPNManager-CA",
        validity_days: int = 3650,
    ) -> EasyRSAResult:
        common_name = validate_common_name(common_name)
        current = self.status()
        if not current.installation_ready:
            raise EasyRSAError("The OpenVPN/Easy-RSA installation is incomplete.")
        if current.ca_certificate_exists or current.ca_key_exists:
            raise EasyRSAError("CA files already exist. Initialization was refused.")

        outputs: list[str] = []
        if not current.pki_initialized:
            pki = self.paths.pki_path
            if pki.exists() and any(pki.iterdir()):
                raise EasyRSAError(
                    "The configured PKI directory is not empty but is not a valid Easy-RSA PKI."
                )
            result = self._execute("init-pki")
            outputs.append(result.output)

        self._acl_hardener(self.paths.pki_path)
        try:
            result = self._execute(
                "build-ca",
                "nopass",
                extra_environment={
                    "EASYRSA_REQ_CN": common_name,
                    "EASYRSA_CA_EXPIRE": str(validity_days),
                    "EASYRSA_NO_PASS": "1",
                },
            )
        finally:
            self._acl_hardener(self.paths.pki_path)
        outputs.append(result.output)
        if not self.status().ca_ready:
            raise EasyRSAError("Easy-RSA finished without creating a complete CA.")
        return EasyRSAResult(sanitize_output("\n".join(outputs)))

    def create_client_certificate(
        self,
        common_name: str,
        validity_days: int = 825,
    ) -> EasyRSAResult:
        common_name = validate_common_name(common_name)
        current = self.status()
        if not current.ca_ready:
            raise EasyRSAError("The CA is not initialized.")
        self._acl_hardener(self.paths.pki_path)
        certificate = self.certificate_status(common_name)
        request = self.paths.pki_path / "reqs" / f"{common_name}.req"
        if certificate.certificate_exists:
            raise EasyRSAError(
                "The certificate already exists. Existing material will not be overwritten."
            )
        if certificate.private_key_exists and not request.is_file():
            raise EasyRSAError(
                "A private key exists without a matching request. "
                "Automatic recovery was refused."
            )
        if request.is_file() and not certificate.private_key_exists:
            raise EasyRSAError(
                "A certificate request exists without its private key. "
                "Automatic recovery was refused."
            )

        arguments = (
            ("sign-req", "client", common_name)
            if certificate.private_key_exists
            else ("build-client-full", common_name, "nopass")
        )
        try:
            result = self._execute(
                *arguments,
                extra_environment={
                    "EASYRSA_CERT_EXPIRE": str(validity_days),
                    "EASYRSA_NO_PASS": "1",
                },
            )
        finally:
            self._acl_hardener(self.paths.pki_path)
        if not self.certificate_status(common_name).complete:
            raise EasyRSAError(
                "Easy-RSA finished without creating a complete client certificate."
            )
        return EasyRSAResult(sanitize_output(result.output))

    def create_server_material(
        self,
        common_name: str = "server",
        validity_days: int = 825,
    ) -> EasyRSAResult:
        common_name = validate_common_name(common_name)
        current = self.status()
        if not current.ca_ready:
            raise EasyRSAError("The CA is not initialized.")

        self._acl_hardener(self.paths.pki_path)
        material = self.server_material_status(common_name)
        request = self.paths.pki_path / "reqs" / f"{common_name}.req"
        if material.certificate_exists and not material.private_key_exists:
            raise EasyRSAError(
                "A server certificate exists without its private key. "
                "Automatic recovery was refused."
            )
        if (
            not material.certificate_exists
            and material.private_key_exists
            and not request.is_file()
        ):
            raise EasyRSAError(
                "A server private key exists without a matching request. "
                "Automatic recovery was refused."
            )
        if request.is_file() and not material.private_key_exists:
            raise EasyRSAError(
                "A server request exists without its private key. "
                "Automatic recovery was refused."
            )
        if material.complete:
            raise EasyRSAError("Complete server material already exists.")

        outputs: list[str] = []
        if not material.certificate_exists:
            arguments = (
                ("sign-req", "server", common_name)
                if material.private_key_exists
                else ("build-server-full", common_name, "nopass")
            )
            try:
                result = self._execute(
                    *arguments,
                    extra_environment={
                        "EASYRSA_CERT_EXPIRE": str(validity_days),
                        "EASYRSA_NO_PASS": "1",
                    },
                )
            finally:
                self._acl_hardener(self.paths.pki_path)
            outputs.append(result.output)

        if not material.tls_crypt_key_exists:
            tls_key = self.paths.pki_path / "ta.key"
            result = self._execute_openvpn(
                "--genkey",
                "secret",
                str(tls_key),
            )
            outputs.append(result.output)

        self._acl_hardener(self.paths.pki_path)
        if not self.server_material_status(common_name).complete:
            raise EasyRSAError(
                "The operation finished without creating complete server material."
            )
        return EasyRSAResult(sanitize_output("\n".join(outputs)))

    def reset_pki_to_backup(self) -> EasyRSAResult:
        pki = self.paths.pki_path
        current = self.status()
        if not pki.exists():
            raise EasyRSAError("The configured PKI directory does not exist.")
        if pki.is_symlink():
            raise EasyRSAError("Resetting a symbolic-link PKI directory is not allowed.")
        if not (
            current.pki_initialized
            or current.ca_certificate_exists
            or current.ca_key_exists
        ):
            raise EasyRSAError(
                "The configured directory is not recognized as an Easy-RSA PKI. "
                "Reset was refused."
            )

        resolved_pki = pki.resolve()
        if resolved_pki == Path(resolved_pki.anchor):
            raise EasyRSAError("Resetting a drive root is not allowed.")

        backup_root = resolved_pki.parent / "pki-backups"
        backup_root.mkdir(parents=True, exist_ok=True)
        self._acl_hardener(backup_root)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%fZ")
        backup_path = backup_root / f"pki-{timestamp}"
        if backup_path.exists():
            raise EasyRSAError("The generated PKI backup path already exists.")

        try:
            resolved_pki.rename(backup_path)
        except OSError as exc:
            raise EasyRSAError(f"Could not move the PKI to its backup location: {exc}") from exc
        if resolved_pki.exists() or not backup_path.is_dir():
            raise EasyRSAError("PKI reset could not be verified.")
        return EasyRSAResult(f"PKI moved safely to:\n{backup_path}")

    def command_preview(self, command: str, common_name: str | None = None) -> str:
        if command == "initialize":
            return (
                f'PKI: "{self.paths.pki_path}"\n'
                "1. easyrsa --batch init-pki\n"
                "2. easyrsa --batch build-ca nopass"
            )
        if command == "client" and common_name is not None:
            validate_common_name(common_name)
            return (
                f'PKI: "{self.paths.pki_path}"\n'
                f"easyrsa --batch build-client-full {common_name} nopass"
            )
        if command == "server":
            return (
                f'PKI: "{self.paths.pki_path}"\n'
                "1. easyrsa --batch build-server-full server nopass\n"
                f'2. openvpn --genkey secret "{self.paths.pki_path / "ta.key"}"'
            )
        raise EasyRSAError("Unknown Easy-RSA command preview.")

    def _execute_openvpn(self, *arguments: str) -> EasyRSAResult:
        command = [str(self.paths.openvpn), *arguments]
        try:
            completed = self._runner(
                command,
                cwd=self.paths.openvpn.parent,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise EasyRSAError(f"Could not start OpenVPN: {exc}") from exc
        output = "\n".join(
            part for part in (completed.stdout, completed.stderr) if part
        )
        if completed.returncode != 0:
            summary = sanitize_output(output).strip()
            raise EasyRSAError(
                f"OpenVPN failed with exit code {completed.returncode}.\n{summary}"
            )
        return EasyRSAResult(sanitize_output(output))

    def _execute(
        self,
        *arguments: str,
        batch: bool = True,
        extra_environment: dict[str, str] | None = None,
    ) -> EasyRSAResult:
        environment = os.environ.copy()
        path_prefix = os.pathsep.join(
            (
                str(self.paths.easyrsa_root),
                str(self.paths.easyrsa_root / "bin"),
                str(self.paths.openvpn_root / "bin"),
            )
        )
        environment["PATH"] = path_prefix + os.pathsep + environment.get("PATH", "")
        environment["HOME"] = self.paths.easyrsa_root.as_posix()
        environment["EASYRSA_PKI"] = self.paths.pki_path.as_posix()
        if batch:
            environment["EASYRSA_BATCH"] = "1"
        if extra_environment:
            environment.update(extra_environment)

        command = [str(self.paths.shell), self.paths.script.as_posix(), *arguments]
        try:
            completed = self._runner(
                command,
                cwd=self.paths.easyrsa_root,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise EasyRSAError(f"Could not start Easy-RSA: {exc}") from exc
        output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
        if completed.returncode != 0:
            summary = sanitize_output(output).strip()
            if len(summary) > 4000:
                summary = summary[-4000:]
            raise EasyRSAError(
                f"Easy-RSA failed with exit code {completed.returncode}.\n{summary}"
            )
        return EasyRSAResult(sanitize_output(output))


def validate_common_name(common_name: str) -> str:
    if not _SAFE_COMMON_NAME.fullmatch(common_name):
        raise EasyRSAError("The certificate common name contains unsafe characters.")
    return common_name


def sanitize_output(output: str) -> str:
    return re.sub(
        r"-----BEGIN (?:ENCRYPTED )?PRIVATE KEY-----.*?"
        r"-----END (?:ENCRYPTED )?PRIVATE KEY-----",
        "[PRIVATE KEY REDACTED]",
        output,
        flags=re.DOTALL,
    )[-8000:]


def _openvpn_service_access_targets(pki_path: Path) -> tuple[tuple[Path, str], ...]:
    return (
        (pki_path, "(RX)"),
        (pki_path / "issued", "(RX)"),
        (pki_path / "private", "(RX)"),
        (pki_path / "ca.crt", "(R)"),
        (pki_path / "ta.key", "(R)"),
        (pki_path / "issued" / "server.crt", "(R)"),
        (pki_path / "private" / "server.key", "(R)"),
    )


def grant_openvpn_service_material_access(
    pki_path: Path,
    runner: Runner = subprocess.run,
) -> None:
    """Grant OpenVPN read access only to its required server-side material."""
    if os.name != "nt":
        return
    targets = _openvpn_service_access_targets(pki_path)
    if not all(path.is_file() for path, _permission in targets[3:]):
        return
    try:
        for path, permission in targets:
            result = runner(
                [
                    "icacls",
                    str(path),
                    "/grant:r",
                    f"{OPENVPN_SERVICE_ACCOUNT}:{permission}",
                    "/C",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
            )
            if result.returncode != 0:
                details = "\n".join(
                    part.strip()
                    for part in (result.stdout, result.stderr)
                    if part and part.strip()
                )
                raise EasyRSAError(
                    "Could not grant the OpenVPN service access to its server "
                    "certificate material. Run the application with administrator "
                    "rights."
                    + (f"\n{details[-2000:]}" if details else "")
                )
    except (OSError, subprocess.SubprocessError) as exc:
        raise EasyRSAError(
            "Could not grant the OpenVPN service access to its server certificate "
            f"material: {exc}"
        ) from exc


def openvpn_service_material_access_ready(
    pki_path: Path,
    runner: Runner = subprocess.run,
) -> bool:
    if os.name != "nt":
        return True
    targets = _openvpn_service_access_targets(pki_path)
    if not all(path.exists() for path, _permission in targets):
        return False
    # The built-in service authority prefix is localized by Windows, while the
    # virtual service name itself is stable.
    marker = "openvpnservice"
    try:
        for path, _permission in targets:
            result = runner(
                ["icacls", str(path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                check=False,
            )
            if result.returncode != 0 or marker not in result.stdout.casefold():
                return False
    except (OSError, subprocess.SubprocessError):
        return False
    return True


def harden_windows_acl(path: Path) -> None:
    if os.name != "nt":
        return
    try:
        identity = subprocess.run(
            ["whoami", "/user", "/fo", "csv", "/nh"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
        )
        if identity.returncode != 0:
            raise EasyRSAError("Could not determine the current Windows user SID.")
        rows = list(csv.reader(io.StringIO(identity.stdout)))
        if not rows or len(rows[0]) < 2:
            raise EasyRSAError("Could not parse the current Windows user SID.")
        user_sid = rows[0][1].strip()
        root_result = subprocess.run(
            [
                "icacls",
                str(path),
                "/inheritance:r",
                "/grant:r",
                f"*{user_sid}:(OI)(CI)F",
                "*S-1-5-32-544:(OI)(CI)F",
                "*S-1-5-18:(OI)(CI)F",
                "/C",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
        )
        descendants_result = None
        if path.is_dir() and any(path.iterdir()):
            descendants_result = subprocess.run(
                [
                    "icacls",
                    str(path / "*"),
                    "/reset",
                    "/T",
                    "/C",
                    "/Q",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
                check=False,
            )
    except (OSError, subprocess.SubprocessError) as exc:
        raise EasyRSAError(
            f"Could not secure the PKI directory permissions: {exc}"
        ) from exc
    if root_result.returncode != 0 or (
        descendants_result is not None
        and descendants_result.returncode != 0
    ):
        details = "\n".join(
            part.strip()
            for result in (root_result, descendants_result)
            if result is not None
            for part in (result.stdout, result.stderr)
            if part and part.strip()
        )
        raise EasyRSAError(
            "Could not secure the PKI directory permissions. "
            "Run the application with administrator rights."
            + (f"\n{details[-2000:]}" if details else "")
        )
    grant_openvpn_service_material_access(path)
