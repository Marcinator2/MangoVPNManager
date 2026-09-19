# GitHub repository settings

Apply these settings after creating the public `Marcinator2/OpenVPN-Manager`
repository and after its first successful CI run.

## General

- Visibility: Public
- Default branch: `main`
- Issues: Enabled
- Private vulnerability reporting: Enabled
- Actions workflow permissions: Read repository contents by default
- Allow GitHub Actions to create and approve pull requests: Disabled

Enable secret scanning, push protection, Dependabot alerts, and Dependabot
security updates.

## Branch rulesets

Create a ruleset named `protected-development` for `develop` and another named
`protected-release` for `main`. Both rulesets must:

- require a pull request before merging;
- require the `Windows tests and build` and `Gitleaks` status checks;
- require branches to be up to date before merging;
- block force pushes;
- block branch deletion;
- allow zero required approving reviews for the initial single-maintainer setup.

Do not configure bypass actors. The repository owner must also use pull
requests and successful status checks.

## Tag ruleset

Create an active ruleset for tags matching `v*`. Block updates and deletion.
Create release tags only after merging a release pull request from `develop`
into `main`.

## First release

1. Confirm CI is green on `main` and `develop`.
2. Confirm `CHANGELOG.md` contains the release date and notes.
3. Create and push the annotated tag `v0.1.0` on `main`.
4. Confirm the Release workflow publishes the ZIP and checksum.
5. Download the ZIP, verify the checksum, and perform a clean-system smoke test.

## Subsequent stable releases

Use **Actions > Release > Run workflow**, select **main**, and enter a new
semantic version. The publish checkbox controls whether the run creates the
tag and release or only produces downloadable build artifacts. The workflow
must remain on the default branch (`main`) for manual dispatch.

No additional secret or branch protection bypass is required. The release job
uses its repository-scoped `GITHUB_TOKEN` to create a new annotated tag and the
release after all validation succeeds. Existing protected tags are never
updated or deleted. Continue requiring pull requests and successful checks for
all changes to `main`.
