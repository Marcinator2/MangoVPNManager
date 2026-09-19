# OpenVPN Manager — agent project context

This repository contains OpenVPN Manager, a Windows desktop tool for managing
locations, routers, OpenVPN certificates, and configuration exports.

## Immutable reference material

- Treat every file under 'sources/' as read-only reference material.
- Do not edit, rename, move, or delete files under 'sources/'.
- Files under 'sources/' may be replaced when the ChatGPT project is synced.
- 'sources/' is local-only and excluded from the public repository.

## Platform and toolchain

- Target platform: Windows Server 2022 or a compatible modern Windows version.
- Supported Python version: Python 3.14.
- Development environment: '.venv'.
- GUI toolkit: PySide6.
- Database: SQLite.
- Packaging: PyInstaller through 'build.ps1'.
- OpenVPN default root: 'C:\Program Files\OpenVPN'.
- Easy-RSA default root: 'C:\Program Files\OpenVPN\easy-rsa'.
- Live PKI default: 'C:\ProgramData\OpenVPNManager\pki'.
- The implementation has been integration-tested with OpenVPN 2.7.7 and
  Easy-RSA 3.2.6.

Do not hardcode the currently configured VPN host, port, export directory, or
other machine-specific values. They are user settings and may change.

## Important data-location distinction

'application_root()' is different between source and packaged execution:

- Running 'python src\main.py' uses 'data/' in the repository.
- Running the packaged EXE uses 'data/' beside the EXE in
  'dist\OpenVPNManager\'.
- New databases are named 'openvpn_manager.db'. Pre-rename development
  databases and PKIs require an explicit manual move/rename; never migrate,
  copy, or merge them automatically.

Do not assume that repository data and packaged-application data are the same.
Never copy, replace, or merge either database automatically.

## Project layout

Primary files:

- 'src/main.py': application entry point and pre-database update recovery.
- 'src/config/version.py': embedded stable/development build identity.
- 'src/updater/': release downloads, package validation, Windows locks, and
  journaled program replacement through a standalone helper.
- 'src/gui/update_controller.py': asynchronous update UI and shutdown handoff.
- 'src/gui/main_window*.py': main window entry point plus separate view,
  runtime/table, workflow/selection, and action modules.
- 'src/gui/certificate_dialog.py': CA, server, and Router certificate workflow.
- 'src/gui/export_dialog.py': guided configuration export.
- 'src/gui/theme.py': light/dark QSS and enabled/disabled button styling.
- 'src/gui/sizing.py': translated-content-aware, screen-bounded dialog sizing.
- 'src/gui/i18n.py': term-aware translator; 'i18n_en.py' and 'i18n_de.py' hold UI strings.
- 'src/config/terminology.py': display-term validation and normalization.
- 'src/gui/terminology_dialog.py': per-language display terms, draft editing and preview.
- 'src/gui/plain_text.py' and 'wrapping_button.py': literal text and wrapping action labels.
- 'src/database/database.py': SQLite schema and persistence.
- 'src/database/models.py': location/router models (internal Branch/Mango names retained).
- 'src/openvpn/addressing.py': validation and address calculation.
- 'src/openvpn/easyrsa.py': Easy-RSA/OpenVPN integration and PKI ACL handling.
- 'src/openvpn/exporter.py': CCD, client, and server configuration generation.
- 'src/openvpn/runtime.py': OpenVPN service-path discovery and live-status parsing.
- 'src/openvpn/installer.py': confirmed server-file installation, backups, and
  service restart.
- 'tests/': automated tests.
- 'icons/': company icon, language flags, and code-native spin-box arrow assets.
- 'build.ps1': Windows packaging script.
- 'scripts/assert-release-safe.ps1': release-content safety gate.
- 'scripts/capture_screenshot.py': synthetic documentation screenshot tool.
- 'scripts/smoke_update.py': packaged updater test using disposable synthetic data.
- 'scripts/release_version.py': stable version and commit validation, immutable tag creation.
- '.github/workflows/': Windows CI, stable tagged releases, and manual develop builds.

## Public repository hygiene

- Public repository: 'Marcinator2/OpenVPN-Manager'.
- Use English for comments, docstrings, commit messages, and documentation.
  German is allowed in localized UI resources and their regression tests.
- Never commit runtime databases, settings, logs, status files, PKI material,
  OpenVPN profiles, exports, or private reference material.
- 'main' contains release-ready changes; normal work targets 'develop' through
  pull requests. Stable release tags use semantic versions such as 'v0.1.0'.
- 'Release' supports manual runs on 'main' with an explicit version and publish
  checkbox, plus existing stable tag pushes. Version numbers are not auto-bumped.
  Normalize input to 'vX.Y.Z', require a newer stable version, refuse existing
  releases and tags on other commits, and pin scanning/building/tagging to the
  same Main commit. Create new annotated tags only after every check passes.
  Build-only runs create no tags or releases; artifacts are retained 14 days.
  Keep the workflow on the default branch 'main' for manual dispatch. Tag and
  release creation happen in the same run without token-trigger recursion.
- 'Develop Build' runs manually on 'develop', scans complete history, tests,
  builds, and checks package contents before publishing a pre-release with a
  unique 'develop-<run ID>-<attempt>' tag on the tested commit. It never replaces
  the latest stable release. Disable its publish input for a build-only test;
  both modes retain downloadable ZIP/checksum artifacts for 14 days. Keep the
  workflow on the default branch ('main') for manual dispatch, then select
  'develop' when starting the workflow.
- The MIT license covers source code. The mb-soft PNG and ICO logo files are
  excluded as described in 'ASSETS-LICENSE.md'. 'mb-soft' is an unregistered
  project name, not a registered company or trademark.
- Run Gitleaks over complete history before publishing and in CI afterward.
- A release is valid only after tests, the Windows build, and
  'scripts/assert-release-safe.ps1' all pass.

## Naming and addressing rules

A Router name is:

'<branch number>_Mango<Router number>'

Example: '0004_Router1'.

The internal branch ID, not the visible branch number, controls addressing:

- VPN address: '10.8.<internal ID>.<Router number>'
- Router LAN: '10.<internal ID>.<Router number>.0/24'
- Router LAN IP: '10.<internal ID>.<Router number>.1'
- Device subnet mask: derived from the Router LAN network (`255.255.255.0`).
- Device gateway: the Router LAN IP.
- Device IP: '10.<internal ID>.<Router number>.<100 + Router number>'

The VPN network is '10.8.0.0/16'. Internal branch ID '8' is reserved because
its LAN networks would overlap the VPN range. Router numbers are limited to
1–10 per branch. Internal IDs are assigned automatically and must be unique.
The internal ID is not exposed as an editable field in the normal branch flow.

Validate all names and addresses before database writes and exports. Preserve
the uniqueness constraints in SQLite.

## Current user workflow

The main window uses a two-pane management layout with the branch tree on the
left and a complete device table on the right. Device, network, certificate,
configuration, and connection fields are shown as table columns; the internal
branch ID remains available to the application but is hidden from the table.
Incomplete setup is shown as a compact prompt; the full four-step setup
overview opens in a separate dialog:

1. Create branches and Routers.
2. Prepare the CA, server material, and Router certificates.
3. Enter the public VPN server address and port.
4. Review, export, or explicitly install configurations.

The setup dialog's primary “next step” button must always lead to the first incomplete step.
The progress display is calculated from the database, configured PKI, server
material, and saved VPN server address.

In the certificate dialog the intended strict order is:

1. Initialize PKI / CA.
2. Create server material.
3. Create all missing Router certificates.

Only currently meaningful actions should be enabled. Disabled buttons must
remain visibly distinct in both light and dark themes. Keep the guidance label
synchronized with the real state.

Creating all missing Router certificates is the primary, recommended, and
default action once CA and server material are ready. Creating only the
selected Router certificate is a secondary exception action.

In the export assistant:

- Preview is always allowed.
- Required missing fields are visually highlighted.
- Repeated missing Router certificate warnings are summarized.
- The export button is enabled only when the VPN server address, CA, server
  certificate/key, all selected Router certificate/key pairs, and export
  directory are available.
- The TLS-crypt key is optional for export readiness but should be used when
  available.
- The certificate dialog can be opened directly from the export assistant.
- VPN host, port, and the currently entered export directory are persisted when
  the assistant closes, even when no export was written.
- Changing host, port, PKI material, or certificates invalidates previously
  stored configuration-created states.

The main list shows description next to name instead of the internal ID.
Descriptions need not be unique. Branch names have a Router-count prefix and
start collapsed; reloads preserve the expanded branches.
The main list includes device IP, subnet mask, and gateway. Its separate XLSX
export includes only Router rows from all branches (including collapsed entries), uses
localized headers, repeats the parent branch description on each Router row,
preserves text and leading zeroes, and requires confirmation
before replacing a file. It does not change configuration-created statuses.

## Certificate and PKI behavior

Certificate operations are real, not placeholders, and always require explicit
user confirmation.

- CA: passwordless, default validity 3650 days.
- Router client certificates: passwordless, default validity 825 days.
- Server certificate: common name 'server', passwordless.
- TLS-crypt key: generated as 'ta.key' through OpenVPN.
- Never overwrite an existing certificate, request, or private key silently.
- If a previous Easy-RSA failure left a matching private key and request but no
  certificate, resume with 'sign-req'; do not regenerate or overwrite the key.
- Refuse automatic recovery when only one side of a key/request pair exists.
- Never display or log private key contents.
- Easy-RSA process output must be sanitized before it reaches the UI.

### Critical Windows ACL rule

Easy-RSA/MSYS-created files can end up with protected empty ACLs. This previously
made 'index.txt' unreadable after server-material creation and caused
'BIO_new_file' / “could not load/parse index.txt” failures.

The correct ACL strategy in 'harden_windows_acl()' is:

1. Restrict the PKI root to the current user SID, Administrators, and SYSTEM,
   with inheritable full-control entries.
2. Reset descendant ACLs so they inherit those restricted root entries.
3. Repair ACLs before and after every certificate operation.

Do not restore the old recursive pattern that applied
'/inheritance:r /grant:r ... /T' directly to every descendant; it produced
files with no effective ACEs.

Any real ACL or Easy-RSA integration test must use a temporary PKI. Do not run
certificate creation against the live PKI during development or automated
testing.

## PKI reset behavior

“Reset PKI” is recoverable and requires two confirmations, including typing
'RESET PKI'.

- Never delete the active PKI permanently.
- Move it to a timestamped sibling backup:
  'C:\ProgramData\OpenVPNManager\pki-backups\pki-<timestamp>'.
- Refuse symlink paths, drive roots, missing PKIs, and unrecognized directories.
- Reset certificate and configuration statuses only after a successful move.
- Never invoke PKI reset automatically.

## Configuration export

A bundle contains:

- 'server.ovpn'
- 'server_routes.conf'
- 'ccd/<Router name>'
- 'clients/<Router name>.ovpn'
- 'EXPORT_README.txt'

Client profiles embed the existing CA certificate, client certificate, private
client key, and TLS-crypt key when available. Private keys and TLS static keys
must always be redacted from the on-screen preview. Before writing a bundle
that contains private keys, require an explicit security confirmation.

'server.ovpn' uses the '10.8.0.0/16' VPN pool and contains a route for every
selected Router LAN. It references the configured PKI and the normal OpenVPN
configuration directory.

Quoted Windows paths in generated OpenVPN configurations must contain doubled
backslashes because OpenVPN treats a single backslash as an escape character.

Exports must remain non-productive:

- Write only to a user-selected export directory.
- Reject OpenVPN installation directories as export targets.
- Ask before replacing any existing export files.
- Use staged writes with rollback on failure.
- Do not install files into OpenVPN automatically.
- Do not start or restart any Windows/OpenVPN service.

Server installation is a separate, explicitly confirmed action:

- Discover 'autostart_config_dir' and 'log_dir' from the OpenVPN machine
  registry settings; use 'config-auto' and 'log' only as fallbacks.
- Install only 'server.ovpn' and 'ccd/*'. Never install embedded client profiles
  on the server.
- Permit installation only for the complete “All Routers” scope so a partial
  selection cannot replace the full server routing configuration.
- Back up replaced files to a timestamped sibling directory outside the
  OpenVPN configuration scan directory.
- After writing, reset the ACL of each exact managed 'server.ovpn' and 'ccd/*'
  target so it inherits the readable ACL from the OpenVPN configuration
  directory. Never apply a broad recursive ACL rewrite to the OpenVPN tree.
- Detect missing ACL inheritance as a permission-repair-required state and
  offer an explicitly confirmed repair action that touches only the expected
  managed server files.
- The OpenVPN service account receives read/traverse access only to the PKI
  directories and four server runtime files it needs: 'ca.crt', 'ta.key',
  'issued/server.crt', and 'private/server.key'. Never grant it access to
  client keys or 'private/ca.key'. Detect missing runtime access as a
  permission-repair-required state and require explicit confirmation.
- Require confirmation before installation and a separate confirmation before
  restarting the OpenVPN service. Never restart it automatically.
- Protected installation directories may require the application to be run as
  an administrator.
- The export assistant compares the complete generated server file set with
  the detected installation. Show a distinct installation card with
  not-installed, update-required, current, or unknown state. Disable the
  install action when all generated files already match.

## Application updater

- Only packaged stable builds check for updates automatically, once at startup.
  The Updates menu also supports manual checks. Source/development builds do not
  install updates or automatically contact the release service.
- Accept only newer stable 'vX.Y.Z' GitHub releases from
  'Marcinator2/OpenVPN-Manager'. The stable release workflow enforces main
  ancestry, embeds the tag, and marks the release as latest.
- Download and installation require the user's Update now action. Use HTTPS,
  the matching SHA-256 sidecar, bounded downloads, safe archive paths, and a
  data-free packaged startup check before handing off.
- Replace only 'OpenVPNManager.exe', '_internal/', and 'OpenVPNUpdater.exe'.
  Never copy, merge, restore, or migrate user databases as an updater operation.
  Do not touch PKI, exports, or OpenVPN services.
- Run the standalone helper from a temporary external copy; use process
  creation identity and cross-session Windows mutexes before replacement.
  Never forcibly stop the user's application.
- Keep an atomic journal and the last program backup under '.openvpn-manager-update/'.
  Recover interrupted replacements before opening user data. If the loader is
  unavailable, the standalone helper supports '--recover <application-folder>'.
- Refuse linked/junction paths. Missing write access requires restarting the
  app as administrator; do not elevate automatically.
- All real update tests must use disposable installations and synthetic data.

## Live OpenVPN status

- The generated server configuration writes status-version 3 every 5 seconds
  to the detected OpenVPN log directory.
- The main window checks the Windows OpenVPN service and status file
  immediately, then every second for the first 10 seconds, and every 5 seconds
  afterward.
- A server is green only when the Windows service is running and its status
  file is fresh. Use red for stopped/stale and gray when status cannot be
  determined.
- Match connected Routers by certificate common name. Show connected since,
  remote peer IP, and the persisted last-seen time without displaying secrets.
- Treat unavailable or stale status data as unknown rather than falsely
  reporting a Router as disconnected.

## Database status semantics

The database stores certificate-created and configuration-created state.

- Certificate state is synchronized against actual PKI files.
- Mark a configuration as created only after a complete export or confirmed
  complete server installation.
- Reset affected configuration status when its certificate changes.
- Reset all configuration status when CA/server material, server host, or server
  port changes.
- PKI reset clears all certificate and configuration state.

Do not report an item as ready based only on a stale database flag.

## UI and localization

- General defaults are Location/Locations, Router/Routers and Device/Devices
  (localized in German). Settings > Display terms customizes singular/plural per
  language; empty or invalid saved fields use the defaults. Free text is limited
  to 40 characters without control characters. Treat it literally, including
  braces, ampersands and HTML-like text.
- Use explicit term tokens in localized templates and pass runtime arguments to
  Translator directly; never format an already translated string containing terms.
- Applying terms refreshes labels only, preserving selection, tree expansion and
  certificate/configuration status. Excel headers use the same terms; sanitize
  sheet names to Excel's character and length restrictions.
- Router identities use the fixed `_Router` prefix, independently of UI terms
  and language. No automatic migration or deletion of old test data or PKIs.
- Internal Branch/Mango class, table and field names are implementation details.

- UI languages: English and German.
- Language menu entries include SVG flags (UK for English, Germany for German).
- English is the default for a fresh installation; the chosen language persists.
- Any new user-visible string must be added in both languages.
- Themes: light and dark, both gray-based rather than pure white/black.
- Disabled object-specific buttons must retain the common disabled style; add
  explicit ':disabled' selectors when introducing a new button object style.
- Preserve the company logo from 'icons/mb-soft.png' and packaged icon.
- Keep spin-box arrows visible in both themes using the existing SVG assets.
- Size dialogs from the current translated layout content and constrain them to
  the available screen. Long action rows must switch to a stacked layout when
  their complete button texts do not fit; do not truncate primary actions.

## Security constraints

- Treat the live PKI and packaged application database as production-like data.
- Never print, preview, log, transmit, or inspect private key contents.
- Listing certificate/key filenames, sizes, and existence is acceptable when
  needed for diagnostics.
- Do not include real keys, certificates, databases, settings, or exports in
  the packaged application.
- Do not silently overwrite certificates, keys, configs, or export files.
- Productive system changes require explicit user confirmation.
- Install configuration files or control OpenVPN services only through the
  explicitly confirmed application actions described above.
- Prefer temporary directories for integration tests and ensure they are
  cleaned up.
- Existing user data in a dirty worktree belongs to the user; preserve it.

## Code organization

- Aim to keep hand-written source and test files at or below 400 lines.
- When a file grows beyond 400 lines, prefer splitting it along clear
  responsibilities as part of the relevant change, provided the split improves
  cohesion and does not introduce unnecessary coupling.
- Treat 400 lines as a maintainability target rather than a mechanical limit.
  Do not create artificial modules, duplicate code, or mix unrelated refactoring
  into a focused fix solely to satisfy the line count.
- Generated files, vendored code, data fixtures, and other machine-maintained
  artifacts are exempt.

## Development and verification

Create or refresh the environment only when needed:

    py -3.14 -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt

Run tests:

    .\.venv\Scripts\python.exe -m pytest -q

At the time this file was updated, the suite contains 197 passing tests.

For risky Easy-RSA changes, supplement unit tests with a real integration test
against an automatically deleted temporary PKI. A useful regression sequence
is:

1. Initialize CA.
2. Create server material.
3. Create two client certificates.
4. Confirm that 'index.txt' remains readable after every step.

Build the Windows application:

    .\build.ps1

Expected executable:

'dist\OpenVPNManager\OpenVPNManager.exe'

The build must bundle application code, the standalone updater, build identity,
and icons only. It must not bundle
'data/', PKI material, exports, or settings. After meaningful changes, run
the full tests, build the EXE, and perform a short startup smoke test.

'build.ps1' must build into a staging directory and update only the packaged
EXE, updater EXE, and '_internal' code directory. It defaults to '.venv' locally and accepts
an explicit '-PythonExecutable' for CI. It validates Python 3.14, creates a
missing local environment, installs requirements-dev.txt, and runs pip check.
'-Start' prepares the environment and runs from source instead of building;
it cannot be combined with '-Clean' or '-StagingOnly'. Existing invalid environments are not
replaced automatically. It must preserve an existing
'dist\OpenVPNManager\data' directory, including on clean builds, and refuse
deployment while the packaged application is running. '-StagingOnly' builds to
'build/package-staging/OpenVPNManager' without replacing the installed copy.
'-ReleaseVersion vX.Y.Z' embeds a stable identity; other builds are development
builds. CI runs 'python scripts/smoke_update.py dist/OpenVPNManager' after
building; local staging verification passes the staging directory instead.

## Maintaining this file

- Update 'AGENTS.md' automatically whenever a project change makes its
  architecture, workflows, safety rules, verification commands, test count, or
  verified-state summary inaccurate. Keep it concise and do not record
  transient implementation details.

## Current verified state (2026-09-19)

- Python 3.14 application and PyInstaller build work.
- Light/dark themes and bilingual UI work.
- Per-language display terms, general defaults, literal free text and fixed Router identities work.
- Branch/Router CRUD and automatic internal IDs work.
- Guided four-step setup flow works.
- The main window uses a synchronized branch tree and complete device table.
- Real CA, server-material, and Router certificate operations are implemented.
- Recoverable PKI reset is implemented.
- Complete server/client/CCD export generation is implemented.
- Explicit server installation with detected OpenVPN paths, recoverable
  replacement backups, and separately confirmed service restart is implemented.
- Live server/Router connection indicators show connected-since, peer IP, and
  persisted last-seen information.
- Dialog widths adapt to translated content and long certificate actions stack
  automatically on narrower displays.
- Private material is redacted from previews.
- The Windows ACL regression is fixed and the existing live PKI ACL was
  repaired without changing certificate/key contents.
- The real temporary-PKI sequence CA → server → two clients succeeds.
- English public documentation, GitHub CI/release workflows, release-content
  checks, and contribution/security templates are present.
- Stable-release updater, data-free startup validation, external helper,
  interrupted-transaction recovery, and preserved-data update smoke test work.
- The Windows staging build and release-content safety check pass.
- Manual stable-release version validation and immutable tag safeguards pass.
- The application, executables, release packages, and repository are named OpenVPN Manager.
- New installations use 'openvpn_manager.db' and the OpenVPNManager ProgramData PKI path.
- The test suite passes with 197 tests.
