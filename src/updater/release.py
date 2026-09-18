"""Bounded HTTPS access to the public stable release feed."""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from config.version import version_tuple

REPOSITORY = "Marcinator2/MangoVPNManager"
API_URL = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
MAX_DOWNLOAD = 512 * 1024 * 1024
HOSTS = {"api.github.com", "github.com", "release-assets.githubusercontent.com",
         "objects.githubusercontent.com", "github-releases.githubusercontent.com"}


class UpdateError(Exception):
    """A stable error code translated at the UI boundary."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class Cancelled(UpdateError):
    def __init__(self) -> None:
        super().__init__("cancelled")


def check_cancel(cancel: threading.Event) -> None:
    if cancel.is_set():
        raise Cancelled()


def validate_url(url: str) -> None:
    try:
        parsed = urllib.parse.urlsplit(url)
        valid = (parsed.scheme == "https" and parsed.hostname in HOSTS
                 and parsed.port in (None, 443) and not parsed.username and not parsed.password)
    except (ValueError, TypeError):
        valid = False
    if not valid:
        raise UpdateError("release_invalid")


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    max_redirections = 3
    max_repeats = 1

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


@dataclass(frozen=True)
class Release:
    version: str
    url: str
    archive_url: str
    checksum_url: str
    archive_name: str
    size: int


class ReleaseClient:
    def __init__(self) -> None:
        self.opener = urllib.request.build_opener(SafeRedirect())

    def fetch(self, url: str, limit: int, cancel: threading.Event,
              destination: Path | None = None,
              progress: Callable[[int, int], None] = lambda done, total: None) -> bytes:
        validate_url(url)
        check_cancel(cancel)
        request = urllib.request.Request(url, headers={
            "User-Agent": "MangoVPNManager-Updater",
            "Accept": "application/vnd.github+json" if url == API_URL else "application/octet-stream",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        output = None
        try:
            with self.opener.open(request, timeout=15) as response:
                validate_url(response.geturl())
                total = int(response.headers.get("Content-Length", "0"))
                if total < 0 or total > limit:
                    raise UpdateError("download_size")
                if destination is not None:
                    output = destination.open("xb")
                chunks = []
                received = 0
                while True:
                    check_cancel(cancel)
                    chunk = response.read(128 * 1024)
                    if not chunk:
                        break
                    received += len(chunk)
                    if received > limit:
                        raise UpdateError("download_size")
                    if output:
                        output.write(chunk)
                    else:
                        chunks.append(chunk)
                    progress(received, total)
                check_cancel(cancel)
                if total and received != total:
                    raise UpdateError("download_incomplete")
                return b"".join(chunks)
        except UpdateError:
            raise
        except urllib.error.HTTPError as exc:
            raise UpdateError("no_release" if exc.code == 404 else "network") from exc
        except (OSError, ValueError) as exc:
            raise UpdateError("network") from exc
        finally:
            if output:
                output.close()

    def latest(self, current: str, cancel: threading.Event) -> Release | None:
        try:
            raw = json.loads(self.fetch(API_URL, 2 * 1024 * 1024, cancel))
            if raw.get("draft") is not False or raw.get("prerelease") is not False:
                raise ValueError("Not a stable release")
            tag = raw["tag_name"]
            if not tag.startswith("v"):
                raise ValueError("Not a stable tag")
            candidate = version_tuple(tag)
            if candidate <= version_tuple(current):
                return None
            name = f"MangoVPNManager-{tag}-windows-x64.zip"
            assets = raw["assets"]
            archive, checksum = ([asset for asset in assets if asset["name"] == key]
                                 for key in (name, name + ".sha256"))
            if len(archive) != 1 or len(checksum) != 1:
                raise ValueError("Missing or ambiguous assets")
            for asset in (archive[0], checksum[0]):
                expected = f"https://github.com/{REPOSITORY}/releases/download/{tag}/{asset['name']}"
                if asset["browser_download_url"] != expected or asset.get("state") != "uploaded":
                    raise ValueError("Unexpected asset")
            size = archive[0]["size"]
            if type(size) is not int or not 0 < size <= MAX_DOWNLOAD:
                raise ValueError("Invalid size")
            return Release(tag, f"https://github.com/{REPOSITORY}/releases/tag/{tag}",
                           archive[0]["browser_download_url"], checksum[0]["browser_download_url"], name, size)
        except UpdateError:
            raise
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise UpdateError("release_invalid") from exc
