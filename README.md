# Mango VPN Manager

[![CI](https://github.com/Marcinator2/MangoVPNManager/actions/workflows/ci.yml/badge.svg)](https://github.com/Marcinator2/MangoVPNManager/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Mango VPN Manager is a local Windows desktop application for managing branch
sites, Mango routers, OpenVPN certificates, server configuration, exports, and
live connection status. It is published by the unregistered **mb-soft** project.

![Mango VPN Manager main window](docs/screenshots/main-window.png)

## Features

- Manage branches and up to ten Mango routers per branch.
- Calculate VPN and LAN addressing from protected internal branch IDs.
- Show oven IP addresses, subnet masks, and gateways in the list.
- Export all Mango rows to XLSX with localized headers and Excel filters.
- Create a CA, server material, and passwordless Mango client certificates.
- Generate server configuration, CCD files, and client profiles.
- Preview exports with private material redacted.
- Compare and explicitly install the complete server configuration.
- Monitor OpenVPN and display live Mango connection information.
- Use English or German UI text and light or dark themes.

## Requirements

- Windows Server 2022 or a compatible modern Windows version
- Python 3.14 for development
- OpenVPN 2.7.x and Easy-RSA 3.2.x for certificate and server operations
- Administrator rights for protected PKI, installation, ACL, and service work

The application discovers OpenVPN service paths from the Windows registry and
uses standard installation paths only as fallbacks.

## Download and verification

Tagged releases provide an unsigned Windows x64 ZIP and a SHA-256 checksum.
Windows SmartScreen may warn because the executable is not currently
code-signed.

```powershell
Get-FileHash .\MangoVPNManager-v0.1.0-windows-x64.zip -Algorithm SHA256
Get-Content .\MangoVPNManager-v0.1.0-windows-x64.zip.sha256
```

The hashes must match exactly. Release archives never contain a database,
settings, certificates, keys, exported profiles, or other runtime data.

## Development setup

```powershell
git clone https://github.com/Marcinator2/MangoVPNManager.git
cd MangoVPNManager
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python src\main.py
```

Source execution stores SQLite data and settings under the local `data/`
directory. Packaged execution uses `data/` beside the EXE. Both are ignored.

## Tests and Windows build

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\build.ps1
.\scripts\assert-release-safe.ps1 -ApplicationDirectory .\dist\MangoVPNManager
```

CI may pass an already provisioned interpreter explicitly with
`-PythonExecutable`; local builds default to `.venv`.

The build script preserves an existing packaged `data/` directory. The safety
check therefore intentionally rejects a local release folder containing data.

## Security model

- Existing certificates, keys, configurations, and exports are never silently
  overwritten.
- Productive system changes require explicit confirmation.
- PKI resets move the PKI to a timestamped backup instead of deleting it.
- Client private keys and TLS static keys are redacted from previews.
- Exports containing private keys require an additional confirmation.
- OpenVPN receives access only to required server runtime material; client keys
  and the CA private key remain protected.
- Service restarts are always separately confirmed.

Never attach real databases, settings, certificates, keys, profiles, status
files, or exports to an issue. See [SECURITY.md](SECURITY.md).

## Addressing model

- VPN address: `10.8.<internal ID>.<Mango number>`
- Mango LAN: `10.<internal ID>.<Mango number>.0/24`
- Mango LAN IP: `10.<internal ID>.<Mango number>.1`
- Oven IP: `10.<internal ID>.<Mango number>.<100 + Mango number>`
- Oven subnet mask: `255.255.255.0`
- Oven gateway: the Mango LAN IP (`10.<internal ID>.<Mango number>.1`)

The VPN pool is `10.8.0.0/16`; internal branch ID `8` is reserved to prevent
overlap with Mango LAN networks.

## Contributing and releases

Development happens on `develop`; release-ready changes reach `main` through a
pull request. See [CONTRIBUTING.md](CONTRIBUTING.md), [ROADMAP.md](ROADMAP.md),
and [CHANGELOG.md](CHANGELOG.md).

## License and branding

The source code is available under the [MIT License](LICENSE). `mb-soft` is an
unregistered project name, not a registered company or trademark. The logo is
excluded from MIT; see [ASSETS-LICENSE.md](ASSETS-LICENSE.md).
