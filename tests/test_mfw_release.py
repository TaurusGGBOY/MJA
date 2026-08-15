from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pytest

from tools.mfw_release import (
    GITHUB_TIMEOUT_SECONDS,
    MAA_ASSET_PATTERN,
    MAA_REPO,
    MFW_ASSET_PATTERN,
    MFW_REPO,
    ReleaseAsset,
    download_asset,
    fetch_latest_asset,
    resolve_asset,
    resolve_latest_asset,
    write_download,
)

REPO = MFW_REPO
PATTERN = MFW_ASSET_PATTERN
RELEASE = {
    "tag_name": "v4.8.23",
    "prerelease": False,
    "draft": False,
    "assets": [
        {
            "name": "MFW-PyQt6-macos-aarch64-v4.8.23.zip",
            "browser_download_url": "https://example.test/mfw.zip",
        },
        {
            "name": "MFW-PyQt6-windows-x86_64-v4.8.23.zip",
            "browser_download_url": "https://example.test/windows.zip",
        },
    ],
}


class FakeHeaders:
    def __init__(self, content_type: str):
        self.content_type = content_type

    def get(self, name: str, default: str | None = None) -> str | None:
        if name.lower() == "content-type":
            return self.content_type
        return default

    def get_content_type(self) -> str:
        return self.content_type.split(";", 1)[0].strip().lower()


class FakeResponse:
    def __init__(
        self,
        chunks: list[bytes],
        *,
        content_type: str = "application/json; charset=utf-8",
        status: int = 200,
        error: Exception | None = None,
    ):
        self._chunks = iter(chunks)
        self.headers = FakeHeaders(content_type)
        self.status = status
        self.error = error
        self.closed = False

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_: Any) -> None:
        self.closed = True

    def read(self, _size: int = -1) -> bytes:
        if self.error is not None:
            raise self.error
        return next(self._chunks, b"")

    def getcode(self) -> int:
        return self.status


def _json_response(payload: object, **kwargs: Any) -> FakeResponse:
    return FakeResponse([json.dumps(payload).encode()], **kwargs)


def test_resolve_asset_requires_one_formal_macos_arm64_match() -> None:
    asset = resolve_asset(REPO, RELEASE, PATTERN)

    assert asset == ReleaseAsset(
        REPO,
        "v4.8.23",
        RELEASE["assets"][0]["name"],
        "https://example.test/mfw.zip",
    )


def test_release_sources_pin_both_repositories_and_arm64_zip_patterns() -> None:
    assert MFW_REPO == "overflow65537/MFW-PyQt6"
    assert MAA_REPO == "MaaXYZ/MaaFramework"
    assert re.search(MFW_ASSET_PATTERN, "MFW-PyQt6-macos-aarch64-v4.8.23.zip")
    assert re.search(MAA_ASSET_PATTERN, "MAA-macos-aarch64-v5.12.2.zip")
    assert not re.search(MFW_ASSET_PATTERN, "MFW-PyQt6-macos-aarch64-v4.8.23.tar.gz")


def test_resolve_asset_accepts_maa_macos_arm64_zip() -> None:
    release = {
        **RELEASE,
        "tag_name": "v5.12.2",
        "assets": [
            {
                "name": "MAA-macos-aarch64-v5.12.2.zip",
                "browser_download_url": "https://example.test/maa.zip",
            }
        ],
    }

    assert resolve_asset(MAA_REPO, release, MAA_ASSET_PATTERN) == ReleaseAsset(
        MAA_REPO,
        "v5.12.2",
        "MAA-macos-aarch64-v5.12.2.zip",
        "https://example.test/maa.zip",
    )


@pytest.mark.parametrize("release_flag", ["draft", "prerelease"])
def test_resolve_asset_rejects_draft_and_prerelease(release_flag: str) -> None:
    release = {**RELEASE, release_flag: True}

    with pytest.raises(ValueError, match="formal"):
        resolve_asset(REPO, release, PATTERN)


@pytest.mark.parametrize(
    ("assets", "count"),
    [([], 0), ([RELEASE["assets"][0], RELEASE["assets"][1]], 1)],
)
def test_resolve_asset_rejects_zero_or_multiple_matches(
    assets: list[dict[str, str]], count: int
) -> None:
    release = {**RELEASE, "assets": assets}
    pattern = PATTERN if count == 0 else r"^MFW-PyQt6-.*\.zip$"

    with pytest.raises(ValueError, match="exactly one"):
        resolve_asset(REPO, release, pattern)


def test_write_download_streams_chunks_and_returns_sha256(tmp_path: Path) -> None:
    target = tmp_path / "asset.zip"
    payload = b"mfw-payload"

    digest = write_download([payload[:3], payload[3:]], target)

    assert digest == hashlib.sha256(payload).hexdigest()
    assert target.read_bytes() == payload
    assert not target.with_name("asset.zip.part").exists()


def test_write_download_removes_half_file_when_a_chunk_fails(tmp_path: Path) -> None:
    target = tmp_path / "asset.zip"

    def chunks():
        yield b"partial"
        raise OSError("stream broke")

    with pytest.raises(OSError, match="stream broke"):
        write_download(chunks(), target)

    assert not target.exists()
    assert not target.with_name("asset.zip.part").exists()


def test_fetch_latest_asset_requires_github_json_and_uses_30_second_timeout() -> None:
    calls: list[tuple[Any, int]] = []

    def opener(request: Any, timeout: int) -> FakeResponse:
        calls.append((request, timeout))
        return _json_response(RELEASE)

    fetched = fetch_latest_asset(REPO, opener=opener)

    assert fetched == RELEASE
    assert calls[0][1] == GITHUB_TIMEOUT_SECONDS == 30
    assert calls[0][0].full_url.endswith(f"/repos/{REPO}/releases/latest")


def test_fetch_latest_asset_rejects_non_json_content_type() -> None:
    response = _json_response(RELEASE, content_type="text/html; charset=utf-8")

    with pytest.raises(ValueError, match="JSON"):
        fetch_latest_asset(REPO, opener=lambda request, timeout: response)


def test_fetch_latest_asset_propagates_timeout() -> None:
    timeout = TimeoutError("GitHub timed out")

    def opener(request: Any, timeout_seconds: int) -> FakeResponse:
        raise timeout

    with pytest.raises(TimeoutError, match="GitHub timed out"):
        fetch_latest_asset(REPO, opener=opener)


def test_resolve_latest_asset_fetches_and_resolves_formal_asset() -> None:
    response = _json_response(RELEASE)

    asset = resolve_latest_asset(
        REPO,
        PATTERN,
        opener=lambda request, timeout: response,
    )

    assert asset.name == "MFW-PyQt6-macos-aarch64-v4.8.23.zip"


def test_resolve_latest_asset_rejects_draft_and_prerelease_payloads() -> None:
    for flag in ("draft", "prerelease"):
        response = _json_response({**RELEASE, flag: True})

        with pytest.raises(ValueError, match="formal"):
            resolve_latest_asset(
                REPO,
                PATTERN,
                opener=lambda request, timeout, response=response: response,
            )


def test_download_asset_streams_response_and_returns_sha256(tmp_path: Path) -> None:
    payload = b"mfw-zip-bytes"
    asset = ReleaseAsset(REPO, "v4.8.23", "mfw.zip", "https://example.test/mfw.zip")
    response = FakeResponse([payload[:4], payload[4:]], content_type="application/zip")
    target = tmp_path / "mfw.zip"

    calls: list[int] = []

    def opener(request: Any, timeout: int) -> FakeResponse:
        calls.append(timeout)
        return response

    digest = download_asset(asset, target, opener=opener)

    assert digest == hashlib.sha256(payload).hexdigest()
    assert target.read_bytes() == payload
    assert response.closed
    assert calls == [30]


def test_download_asset_removes_half_file_when_response_fails(tmp_path: Path) -> None:
    asset = ReleaseAsset(REPO, "v4.8.23", "mfw.zip", "https://example.test/mfw.zip")
    target = tmp_path / "mfw.zip"
    response = FakeResponse([b"partial"], content_type="application/zip", error=OSError("reset"))

    with pytest.raises(OSError, match="reset"):
        download_asset(asset, target, opener=lambda request, timeout: response)

    assert not target.exists()
    assert not target.with_name("mfw.zip.part").exists()


def test_download_asset_rejects_http_url_before_open(tmp_path: Path) -> None:
    asset = ReleaseAsset(REPO, "v4.8.23", "mfw.zip", "http://example.test/mfw.zip")
    opened = False

    def opener(request: Any, timeout: int) -> FakeResponse:
        nonlocal opened
        opened = True
        return FakeResponse([b"unexpected"], content_type="application/zip")

    with pytest.raises(ValueError, match="HTTPS"):
        download_asset(asset, tmp_path / "mfw.zip", opener=opener)

    assert not opened
