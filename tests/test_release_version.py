from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess

import pytest

SPEC = importlib.util.spec_from_file_location("release_version", Path(__file__).resolve().parents[1] / "scripts" / "release_version.py")
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)
COMMIT = "a" * 40


@pytest.mark.parametrize("value,expected", [("0.2.0", "v0.2.0"), ("v1.10.2", "v1.10.2"), (" v0.2.0 ", "v0.2.0")])
def test_normalizes_stable_version(value, expected):
    assert release.normalize_version(value) == expected


@pytest.mark.parametrize("value", ["", "v01.2.3", "v1.2", "v1.2.3-rc1", "v1.2.3+build", "latest", "v1.2.3\npublish=true"])
def test_rejects_invalid_release_versions(value):
    with pytest.raises(ValueError):
        release.normalize_version(value)


def test_numeric_order_and_nonstable_tags():
    release.validate_version("v0.10.0", COMMIT, {"v0.9.0": "b" * 40, "develop-123": "c", "v1.0.0-rc1": "d"})
    with pytest.raises(ValueError, match="newer"):
        release.validate_version("v0.9.0", COMMIT, {"v0.10.0": "b" * 40})


def test_tag_retry_requires_same_commit_and_no_newer_version():
    release.validate_version("v0.2.0", COMMIT, {"v0.2.0": COMMIT})
    with pytest.raises(ValueError, match="another commit"):
        release.validate_version("v0.2.0", COMMIT, {"v0.2.0": "b" * 40})
    with pytest.raises(ValueError, match="newer"):
        release.validate_version("v0.2.0", COMMIT, {"v0.2.0": COMMIT, "v0.3.0": "c" * 40})


@pytest.mark.parametrize("publish", ["true", "false"])
def test_manual_release_on_main(publish):
    assert release.requested_release("workflow_dispatch", "refs/heads/main", "0.2.0", publish) == ("v0.2.0", publish == "true")


@pytest.mark.parametrize("ref", ["refs/heads/develop", "refs/heads/feature", "refs/tags/v0.2.0"])
def test_manual_release_rejects_other_refs(ref):
    with pytest.raises(ValueError, match="Select main"):
        release.requested_release("workflow_dispatch", ref, "v0.2.0", "true")


def test_legacy_tag_push_and_invalid_events():
    assert release.requested_release("push", "refs/tags/v0.2.0", "", "") == ("v0.2.0", True)
    with pytest.raises(ValueError):
        release.requested_release("push", "refs/heads/main", "", "")
    with pytest.raises(ValueError):
        release.requested_release("pull_request", "refs/heads/main", "v0.2.0", "true")
    with pytest.raises(ValueError):
        release.requested_release("workflow_dispatch", "refs/heads/main", "v0.2.0", "yes")


def setup_context(monkeypatch):
    monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_dispatch")
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    monkeypatch.setenv("REQUESTED_VERSION", "0.2.0")
    monkeypatch.setenv("REQUESTED_PUBLISH", "false")
    monkeypatch.setattr(release, "read_tags", lambda: {"v0.1.0": "b" * 40})
    monkeypatch.setattr(release, "git", lambda *args: COMMIT if args == ("rev-parse", "HEAD") else "")
    monkeypatch.setattr(release, "github", lambda *args: None)


def test_preparation_has_no_tag_or_release_writes(monkeypatch, tmp_path):
    setup_context(monkeypatch)
    requests = []
    def api(method, endpoint, payload=None):
        requests.append((method, endpoint))
        return None
    monkeypatch.setattr(release, "github", api)
    output = tmp_path / "output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    release.prepare_release()
    assert output.read_text() == f"tag=v0.2.0\ncommit={COMMIT}\npublish=false\n"
    assert requests == [("GET", "releases/tags/v0.2.0")]


def test_existing_release_is_never_replaced(monkeypatch):
    setup_context(monkeypatch)
    monkeypatch.setattr(release, "github", lambda *args: {"id": 1, "draft": True})
    with pytest.raises(ValueError, match="never replaced"):
        release.resolve_release()


def test_commit_must_belong_to_main(monkeypatch):
    setup_context(monkeypatch)
    def git(*args):
        if args[0] == "merge-base":
            raise subprocess.CalledProcessError(1, "git")
        return COMMIT if args == ("rev-parse", "HEAD") else ""
    monkeypatch.setattr(release, "git", git)
    with pytest.raises(ValueError, match="contained in main"):
        release.resolve_release()


def test_build_only_mode_cannot_create_tag(monkeypatch):
    monkeypatch.setattr(release, "resolve_release", lambda: ("v0.2.0", COMMIT, False, {}))
    monkeypatch.setattr(release, "github", lambda *args: pytest.fail("No write allowed"))
    with pytest.raises(ValueError, match="build-only"):
        release.create_release_tag()


@pytest.mark.parametrize("planned_tag,planned_commit", [("v0.3.0", COMMIT), ("v0.2.0", "b" * 40)])
def test_tag_creation_checks_original_build_identity(monkeypatch, planned_tag, planned_commit):
    monkeypatch.setattr(release, "resolve_release", lambda: ("v0.2.0", COMMIT, True, {}))
    monkeypatch.setenv("PLANNED_TAG", planned_tag)
    monkeypatch.setenv("PLANNED_COMMIT", planned_commit)
    monkeypatch.setattr(release, "github", lambda *args: pytest.fail("No write allowed"))
    with pytest.raises(ValueError, match="identity changed"):
        release.create_release_tag()


def test_creates_annotated_tag_on_exact_tested_commit(monkeypatch):
    monkeypatch.setattr(release, "resolve_release", lambda: ("v0.2.0", COMMIT, True, {}))
    monkeypatch.setenv("PLANNED_TAG", "v0.2.0")
    monkeypatch.setenv("PLANNED_COMMIT", COMMIT)
    requests = []
    def api(method, endpoint, payload):
        requests.append((method, endpoint, payload))
        return {"sha": "c" * 40}
    monkeypatch.setattr(release, "github", api)
    release.create_release_tag()
    assert requests[0] == ("POST", "git/tags", {"tag": "v0.2.0", "message": "OpenVPN Manager v0.2.0", "object": COMMIT, "type": "commit"})
    assert requests[1] == ("POST", "git/refs", {"ref": "refs/tags/v0.2.0", "sha": "c" * 40})


def test_retry_reuses_existing_tag_without_updating_it(monkeypatch):
    monkeypatch.setattr(release, "resolve_release", lambda: ("v0.2.0", COMMIT, True, {"v0.2.0": COMMIT}))
    monkeypatch.setenv("PLANNED_TAG", "v0.2.0")
    monkeypatch.setenv("PLANNED_COMMIT", COMMIT)
    monkeypatch.setattr(release, "github", lambda *args: pytest.fail("Existing tag must not be rewritten"))
    release.create_release_tag()
