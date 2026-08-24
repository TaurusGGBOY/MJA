"""Resolve and download the formal macOS arm64 MFW dependencies."""

from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

GITHUB_API = "https://api.github.com"
MFW_REPO = "overflow65537/MFW-PyQt6"
MAA_REPO = "MaaXYZ/MaaFramework"
MFW_ASSET_PATTERN = r"^MFW.*macos-aarch64.*\.zip$"
MAA_ASSET_PATTERN = r"^MAA-macos-aarch64.*\.zip$"
GITHUB_TIMEOUT_SECONDS = 30
CHUNK_SIZE = 1024 * 1024

Opener = Callable[..., Any]


@dataclass(frozen=True)
class ReleaseAsset:
    """One uniquely selected asset from a formal GitHub release."""

    repo: str
    tag: str
    name: str
    url: str


def _release_url(repo: str) -> str:
    if repo.count("/") != 1 or any(not part for part in repo.split("/")):
        raise ValueError(f"invalid GitHub repository: {repo!r}")
    return f"{GITHUB_API}/repos/{repo}/releases/latest"


def _content_type(response: Any) -> str:
    headers = getattr(response, "headers", None)
    if headers is None:
        return ""
    get_content_type = getattr(headers, "get_content_type", None)
    if callable(get_content_type):
        return str(get_content_type()).lower()
    value = headers.get("Content-Type", "")
    return str(value).split(";", 1)[0].strip().lower()


def _response_status(response: Any) -> int | None:
    status = getattr(response, "status", None)
    if status is None:
        getcode = getattr(response, "getcode", None)
        status = getcode() if callable(getcode) else None
    return int(status) if status is not None else None


def _require_success(response: Any) -> None:
    status = _response_status(response)
    if status is not None and not 200 <= status < 300:
        raise RuntimeError(f"GitHub request returned HTTP {status}")


def fetch_latest_asset(
    repo: str,
    pattern: str | Opener | None = None,
    opener: Opener | None = None,
) -> Mapping[str, Any] | ReleaseAsset:
    """Fetch the ``releases/latest`` JSON, optionally resolving one asset.

    With only ``repo`` this returns the validated release mapping. Supplying
    ``pattern`` also resolves the unique matching asset, which keeps this
    helper convenient for callers that want a single network operation.
    """

    if callable(pattern) and opener is None:
        opener = pattern
        pattern = None

    request = urllib.request.Request(
        _release_url(repo),
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "MJA-mfw-release/1",
        },
    )
    if opener is None:
        response_context = urllib.request.urlopen(request, timeout=GITHUB_TIMEOUT_SECONDS)
    else:
        response_context = opener(request, GITHUB_TIMEOUT_SECONDS)
    with response_context as response:
        _require_success(response)
        content_type = _content_type(response)
        if not content_type.endswith("+json") and content_type != "application/json":
            raise ValueError("GitHub release response must use a JSON Content-Type")
        payload = json.loads(response.read())

    if not isinstance(payload, Mapping):
        raise ValueError("GitHub release response must be a JSON object")
    if "tag_name" not in payload or "assets" not in payload:
        raise ValueError("GitHub release response is missing tag_name or assets")
    if pattern is None:
        return payload
    return resolve_asset(repo, payload, pattern)


def resolve_asset(repo: str, release: Mapping[str, Any], pattern: str) -> ReleaseAsset:
    """Resolve exactly one formal zip asset from a release JSON object."""

    if release.get("draft") or release.get("prerelease"):
        raise ValueError("latest release must be formal")

    tag = release.get("tag_name")
    assets = release.get("assets")
    if not isinstance(tag, str) or not tag:
        raise ValueError("formal release must have a tag_name")
    if not isinstance(assets, list):
        raise ValueError("formal release must have an assets list")

    try:
        matcher = re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"invalid asset pattern: {pattern!r}") from exc

    matches = [
        asset
        for asset in assets
        if isinstance(asset, Mapping)
        and isinstance(asset.get("name"), str)
        and asset["name"].lower().endswith(".zip")
        and matcher.search(asset["name"])
    ]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one asset for {repo}, got {len(matches)}")

    item = matches[0]
    name = item.get("name")
    url = item.get("browser_download_url")
    if not isinstance(name, str) or not isinstance(url, str) or not url:
        raise ValueError(f"selected asset for {repo} is missing name or download URL")
    return ReleaseAsset(repo, tag, name, url)


def resolve_latest_asset(
    repo: str,
    pattern: str,
    opener: Opener | None = None,
) -> ReleaseAsset:
    """Fetch GitHub's latest release and resolve one matching formal asset."""

    release = fetch_latest_asset(repo, opener=opener)
    if not isinstance(release, Mapping):
        raise TypeError("fetch_latest_asset returned a resolved asset unexpectedly")
    return resolve_asset(repo, release, pattern)


def write_download(chunks: Iterable[bytes], target: Path) -> str:
    """Write chunks atomically and return their SHA-256 digest.

    The temporary ``.part`` file is removed on every failure. An existing
    destination is left untouched until the complete stream is flushed.
    """

    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")
    digest = hashlib.sha256()
    try:
        with part.open("wb") as stream:
            for chunk in chunks:
                if not isinstance(chunk, bytes):
                    raise TypeError("download chunks must be bytes")
                stream.write(chunk)
                digest.update(chunk)
            stream.flush()
        part.replace(target)
    except Exception:
        part.unlink(missing_ok=True)
        raise
    return digest.hexdigest()


def _response_chunks(response: Any) -> Iterable[bytes]:
    while True:
        chunk = response.read(CHUNK_SIZE)
        if not chunk:
            return
        yield chunk


def download_asset(
    asset: ReleaseAsset,
    target: Path,
    opener: Opener | None = None,
) -> str:
    """Stream one selected asset to ``target`` and return its SHA-256."""

    parsed = urllib.parse.urlparse(asset.url)
    if parsed.scheme.lower() != "https":
        raise ValueError("asset downloads require HTTPS")

    request = urllib.request.Request(
        asset.url,
        headers={"User-Agent": "MJA-mfw-release/1"},
    )
    if opener is None:
        response_context = urllib.request.urlopen(request, timeout=GITHUB_TIMEOUT_SECONDS)
    else:
        response_context = opener(request, GITHUB_TIMEOUT_SECONDS)
    with response_context as response:
        _require_success(response)
        return write_download(_response_chunks(response), Path(target))
