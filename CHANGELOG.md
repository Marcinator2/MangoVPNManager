# Changelog

All notable changes to this project are documented here. The project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Settings dialog for per-language singular/plural display terms, with live preview,
  safe free text, defaults, and matching Excel headers.

### Changed

- Default terminology is now Location, Router and Device. New router identities
  use the fixed `_Router` prefix independently of display terms; old test data
  is not migrated automatically.
- Long action labels wrap and stack to fit the available screen.

- Renamed the project and packaged application to OpenVPN Manager, including
  executables, release archives, updater identifiers, and default data paths.

## [0.2.0] - 2026-09-19

### Added

- Secure in-application updates with package verification, transactional
  replacement, rollback, and a standalone updater helper.
- Manual stable releases from main with explicit version input and an optional
  build-only run. Tags, application versions, ZIP names, and releases share the
  same validated version, with complete-history scanning before publication.

## [0.1.0] - 2026-09-16

### Added

- Branch and Mango management with validated automatic addressing.
- Easy-RSA CA, server, and client certificate workflows.
- Recoverable PKI reset and restricted Windows ACL handling.
- Complete OpenVPN server, CCD, and client configuration exports.
- Explicit server installation, backup, ACL repair, and service restart flow.
- Live OpenVPN server and Mango connection status.
- English and German UI translations with light and dark themes.
- Windows packaging through PyInstaller.

[Unreleased]: https://github.com/Marcinator2/OpenVPN-Manager/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/Marcinator2/OpenVPN-Manager/releases/tag/v0.2.0
[0.1.0]: https://github.com/Marcinator2/OpenVPN-Manager/releases/tag/v0.1.0
