"""Validate stable release identities and create immutable tags after validation."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from config.version import version_tuple


def normalize_version(value: str) -> str:
    version = value.strip()
    version_tuple(version)
    return "v" + version.removeprefix("v")


def validate_version(tag: str, commit: str, existing: dict[str, str]) -> None:
    candidate = version_tuple(tag)
    if tag in existing and existing[tag] != commit:
        raise ValueError("This version already belongs to another commit; tags cannot be moved.")
    for other in existing:
        if other != tag and other.startswith("v"):
            try:
                previous = version_tuple(other)
            except ValueError:
                continue
            if candidate <= previous:
                raise ValueError(f"The version must be newer than existing stable tag {other}.")


def requested_release(event: str, ref: str, version: str, publish: str) -> tuple[str, bool]:
    if event == "workflow_dispatch":
        if ref != "refs/heads/main":
            raise ValueError("Select main in the Run workflow branch dropdown.")
        if publish not in {"true", "false"}:
            raise ValueError("Publish must be true or false.")
        return normalize_version(version), publish == "true"
    if event == "push" and ref.startswith("refs/tags/v"):
        tag = ref.removeprefix("refs/tags/")
        if normalize_version(tag) != tag:
            raise ValueError("Stable tags must use vX.Y.Z.")
        return tag, True
    raise ValueError("Stable releases require a manual run on main or a vX.Y.Z tag push.")


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True, stderr=subprocess.PIPE).strip()


def read_tags() -> dict[str, str]:
    tags = {}
    for name in git("tag", "--list", "v*").splitlines():
        try:
            if normalize_version(name) == name:
                tags[name] = git("rev-parse", f"refs/tags/{name}^{{commit}}")
        except ValueError:
            continue
    return tags


def github(method: str, endpoint: str, payload: dict | None = None) -> dict | None:
    repository = os.environ["GITHUB_REPOSITORY"]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Invalid GitHub repository.")
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}/{endpoint}",
        method=method,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Authorization": "Bearer " + os.environ["GH_TOKEN"],
                 "Accept": "application/vnd.github+json", "Content-Type": "application/json",
                 "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "OpenVPNManager-release"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        if method == "GET" and exc.code == 404:
            return None
        raise RuntimeError(f"GitHub rejected the release operation (HTTP {exc.code}).") from None


def resolve_release() -> tuple[str, str, bool, dict[str, str]]:
    tag, publish = requested_release(
        os.environ["GITHUB_EVENT_NAME"], os.environ["GITHUB_REF"],
        os.environ.get("REQUESTED_VERSION", ""), os.environ.get("REQUESTED_PUBLISH", ""),
    )
    git("fetch", "origin", "main", "--tags")
    commit = git("rev-parse", "HEAD")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Invalid source commit.")
    try:
        git("merge-base", "--is-ancestor", commit, "origin/main")
    except subprocess.CalledProcessError:
        raise ValueError("The selected commit must be contained in main.") from None
    tags = read_tags()
    validate_version(tag, commit, tags)
    if github("GET", "releases/tags/" + urllib.parse.quote(tag, safe="")) is not None:
        raise ValueError("A release already exists for this version; existing releases are never replaced.")
    return tag, commit, publish, tags


def prepare_release() -> None:
    tag, commit, publish, _ = resolve_release()
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
        output.write(f"tag={tag}\ncommit={commit}\npublish={str(publish).lower()}\n")
    print(f"Validated stable release {tag} at {commit}; publish={str(publish).lower()}.")


def create_release_tag() -> None:
    # Revalidate immediately before publication, after tests, build, and scan.
    tag, commit, publish, tags = resolve_release()
    if not publish:
        raise ValueError("This is a build-only run; tag creation is disabled.")
    if tag != os.environ["PLANNED_TAG"] or commit != os.environ["PLANNED_COMMIT"]:
        raise ValueError("Release identity changed after validation.")
    if tag not in tags:
        annotated = github("POST", "git/tags", {
            "tag": tag, "message": f"OpenVPN Manager {tag}", "object": commit, "type": "commit",
        })
        if not annotated or not re.fullmatch(r"[0-9a-f]{40}", annotated.get("sha", "")):
            raise RuntimeError("GitHub returned an invalid tag object.")
        github("POST", "git/refs", {"ref": f"refs/tags/{tag}", "sha": annotated["sha"]})
    print(f"Immutable release tag {tag} identifies tested commit {commit}.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "tag"))
    args = parser.parse_args()
    try:
        prepare_release() if args.action == "prepare" else create_release_tag()
        return 0
    except (ValueError, RuntimeError, OSError, KeyError, subprocess.CalledProcessError) as exc:
        # Do not include raw API responses, command stderr, or credentials.
        message = str(exc) if isinstance(exc, (ValueError, RuntimeError)) else "Release validation failed."
        print(f"::error::{message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
