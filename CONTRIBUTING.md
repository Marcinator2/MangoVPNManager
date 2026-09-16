# Contributing

Thank you for helping improve Mango VPN Manager.

## Language

Use English for source comments, docstrings, commit messages, pull requests,
issues, and developer documentation. German text is allowed only as localized
UI content in `src/gui/i18n.py`.

## Branch workflow

1. Create feature and bug-fix branches from `develop`.
2. Open pull requests back into `develop`.
3. Prepare releases through a pull request from `develop` to `main`.
4. Create hotfix branches from `main`, merge them into `main`, and merge the
   same fix back into `develop`.

Do not force-push protected branches. Release tags use semantic versions such
as `v0.1.0` and must point to a commit on `main`.

## Local verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\build.ps1
.\scripts\assert-release-safe.ps1 -ApplicationDirectory .\dist\MangoVPNManager
```

Use Python 3.14. Run real Easy-RSA integration tests only against a temporary
PKI that is deleted after the test. Never test against the active PKI.

## Security and private material

Never commit or attach real databases, settings, certificates, certificate
requests, private keys, TLS keys, OpenVPN profiles, status files, or exports.
Do not paste private material into issues, logs, screenshots, or pull requests.
Use private vulnerability reporting as described in `SECURITY.md`.

Productive installation, ACL, PKI, and service operations must remain
explicitly confirmed by the user.
