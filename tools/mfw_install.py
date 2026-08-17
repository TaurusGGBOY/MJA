"""Assemble immutable, self-contained MFW candidates for macOS arm64."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from tools.mfw_native_bundle import (
    install_mfw_native_bundle,
    install_mfw_shared_runtime,
    verify_mfw_native_bundle,
    verify_mfw_shared_runtime,
)
from tools.mfw_pyqt6_patch import (
    apply_mfw_pyqt6_runtime_patch,
    verify_mfw_pyqt6_runtime_patch,
)
from tools.mfw_profile import ensure_pair_profiles
from tools.mfw_release import (
    MAA_ASSET_PATTERN,
    MAA_REPO,
    MFW_ASSET_PATTERN,
    MFW_REPO,
    ReleaseAsset,
    download_asset,
    resolve_latest_asset,
)

ROOT = Path(__file__).resolve().parents[1]
TARGET = "macos-aarch64"
RUNTIME_ROOT = Path("runtimes/osx-arm64")
METADATA_NAME = "build-metadata.json"
# These are all project-owned roots that must be excluded from a copied
# runtime tree.  The actual resource root is selected from the interface so a
# candidate cannot silently omit a platform-specific resource bundle.
PAYLOAD_ROOTS = ("tasks", "resource", "resource_android", "agent")
RESOURCE_ROOTS = ("resource", "resource_android")
PAYLOAD_FILES = ("interface.json", "CFA_setting.json", "requirements.txt")
MFW_LAYOUT_PYINSTALLER = "pyinstaller"
MFW_LAYOUT_LEGACY = "legacy"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _iter_files(root: Path) -> Iterable[Path]:
    root = Path(root)
    if root.is_file():
        yield root
        return
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"symlinks are not allowed in candidate: {path}")
        if path.is_file():
            yield path


def _safe_relative(path: Path, root: Path) -> Path:
    try:
        return path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"path escapes root: {path}") from exc


def _is_probe_path(relative: Path) -> bool:
    return any("MJA_PROBE_" in part for part in relative.parts)


def prepare_output(output: Path) -> None:
    output = Path(output)
    if output.exists():
        if not output.is_dir() or any(output.iterdir()):
            raise FileExistsError(f"output is not empty: {output}")
    else:
        output.mkdir(parents=True)


def _safe_member(member_name: str, destination: Path) -> Path:
    normalized = member_name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise ValueError(f"unsafe zip member: {member_name}")
    target = (destination / Path(*path.parts)).resolve()
    if destination.resolve() not in target.parents:
        raise ValueError(f"unsafe zip member: {member_name}")
    return target


def safe_extract(archive: Path, output: Path) -> None:
    """Extract a zip after validating traversal and symbolic-link members."""

    prepare_output(output)
    with zipfile.ZipFile(archive) as bundle:
        members = bundle.infolist()
        for member in members:
            target = _safe_member(member.filename, output)
            mode = (member.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                raise ValueError(f"unsafe zip member: {member.filename}")
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
        for member in members:
            if member.is_dir():
                continue
            target = _safe_member(member.filename, output)
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(member) as source, target.open("wb") as destination:
                shutil.copyfileobj(source, destination, 1024 * 1024)


def _find_archive_root(extracted: Path, required: tuple[str, ...]) -> Path:
    candidates = [extracted, *sorted(path for path in extracted.iterdir() if path.is_dir())]
    for candidate in candidates:
        if all((candidate / item).exists() for item in required):
            return candidate
    for candidate in sorted(path for path in extracted.rglob("*") if path.is_dir()):
        if all((candidate / item).exists() for item in required):
            return candidate
    raise ValueError(f"archive is missing required layout: {required}")


def _copy_tree(source: Path, destination: Path) -> None:
    if not source.is_dir():
        raise FileNotFoundError(source)
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if _is_generated_runtime_cache(relative):
            continue
        target = destination / relative
        if path.is_symlink():
            raise ValueError(f"symlinks are not allowed in candidate: {path}")
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            _copy_file(path, target)
        else:
            raise ValueError(f"unsupported tree entry: {path}")


def _copy_file(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Candidate payloads are content-addressed; filesystem metadata is neither
    # required nor safe to preserve.  On filesystems without native xattrs,
    # copy2 materializes them as AppleDouble ``._*`` files.  MFW recursively
    # loads resource JSON and would then try to decode those binary sidecars.
    shutil.copyfile(source, destination)


def _remove_appledouble_files(root: Path) -> None:
    """Remove metadata sidecars materialized while assembling a candidate."""

    for path in sorted(Path(root).rglob("._*"), reverse=True):
        if path.is_file():
            path.unlink()


def _find_mfw_archive_root(extracted: Path) -> Path:
    layouts = (
        (
            MFW_LAYOUT_PYINSTALLER,
            ("MFW", "_internal/Python", "_internal/maa/agent/agent_server.py", "maafw"),
        ),
        (MFW_LAYOUT_LEGACY, ("MFW", "python/bin/python3")),
    )
    for _, required in layouts:
        try:
            return _find_archive_root(extracted, required)
        except ValueError:
            continue
    required_layouts = ", ".join(
        f"{name}: {required}" for name, required in layouts
    )
    raise ValueError(f"archive is missing a supported MFW layout: {required_layouts}")


def _mfw_layout(candidate: Path) -> str:
    candidate = Path(candidate)
    if (
        (candidate / "MFW").is_file()
        and (candidate / "_internal/Python").is_file()
        and (candidate / "_internal/maa/agent/agent_server.py").is_file()
        and (candidate / "maafw").is_dir()
    ):
        return MFW_LAYOUT_PYINSTALLER
    if (candidate / "MFW").is_file() and (candidate / "python/bin/python3").is_file():
        return MFW_LAYOUT_LEGACY
    raise ValueError(
        "candidate is missing a supported MFW runtime layout "
        "(MFW + _internal/Python + maafw or python/bin/python3)"
    )


def _make_executable(path: Path) -> None:
    path.chmod(path.stat().st_mode | 0o111)


def _copy_mfw_archive(archive: Path, output: Path) -> str:
    with tempfile.TemporaryDirectory(prefix="mja-mfw-extract-") as temporary:
        extracted = Path(temporary) / "mfw"
        safe_extract(archive, extracted)
        package = _find_mfw_archive_root(extracted)
        for child in package.iterdir():
            target = output / child.name
            if child.is_dir():
                _copy_tree(child, target)
            else:
                _copy_file(child, target)
    for executable in (output / "MFW", output / "MFWUpdater"):
        if executable.is_file():
            _make_executable(executable)
    return _mfw_layout(output)


def _copy_maa_archive(archive: Path, output: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="mja-maa-extract-") as temporary:
        extracted = Path(temporary) / "maa"
        safe_extract(archive, extracted)
        package = _find_archive_root(extracted, ("bin", "share/MaaAgentBinary"))
        runtime = output / RUNTIME_ROOT
        _copy_tree(package / "bin", runtime)
        _copy_tree(package / "share/MaaAgentBinary", runtime / "MaaAgentBinary")


def _source_interface(repo_root: Path) -> Path:
    for candidate in (repo_root / "assets/interface.json", repo_root / "assets/interface.mfw.json"):
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("assets/interface.json or assets/interface.mfw.json")


def _payload_directories(interface_path: Path) -> tuple[str, ...]:
    """Return project roots required by an interface's resource paths.

    Maa_bbb keeps one interface and lets each resource declare the controller
    it belongs to.  MJA has both the legacy iOS resource and the Android
    resource in the checkout, so copying every directory would make a
    candidate ambiguous.  Select only the roots named by the active
    interface, while retaining the common tasks and Agent roots.
    """

    payload = json.loads(Path(interface_path).read_text(encoding="utf-8"))
    roots: list[str] = ["tasks"]
    for resource in payload.get("resource", ()):
        if not isinstance(resource, Mapping):
            continue
        for raw_path in resource.get("path", ()):
            if not isinstance(raw_path, str):
                continue
            parts = PurePosixPath(raw_path).parts
            if parts and parts[0] in RESOURCE_ROOTS:
                roots.append(parts[0])

    # Keep compatibility with the old shorthand path used by early MFW
    # fixtures ("base" means the source's resource/ tree).
    if not any(root in RESOURCE_ROOTS for root in roots):
        roots.append("resource")
    roots.append("agent")
    return tuple(dict.fromkeys(roots))


def _copy_project_payload(repo_root: Path, output: Path) -> None:
    interface = _source_interface(repo_root)
    _copy_file(interface, output / "interface.json")
    for directory in _payload_directories(interface):
        source_root = repo_root if directory == "agent" else repo_root / "assets"
        _copy_tree(source_root / directory, output / directory)
    for filename in ("CFA_setting.json", "requirements.txt"):
        _copy_file(repo_root / filename, output / filename)


def _is_production_install_candidate(candidate: Path) -> bool:
    return Path(candidate).resolve().parent == ROOT / "install"


def _activate_production_shared_runtime(repo_root: Path, candidate: Path) -> None:
    if Path(repo_root).resolve() != ROOT or not _is_production_install_candidate(candidate):
        return
    bundle = ROOT / "vendor/maafw/v5.12.3/macos-arm64"
    if not bundle.is_dir():
        raise FileNotFoundError(f"required MFW native bundle is missing: {bundle}")
    install_mfw_shared_runtime(ROOT / "install", bundle)


def _rewrite_installed_interface(output: Path) -> None:
    path = output / "interface.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    agent = payload.setdefault("agent", {})
    if _mfw_layout(output) == MFW_LAYOUT_PYINSTALLER:
        # Current MFW-PyQt6 converts this entry to embedded custom loading.
        # Keep the documented {PROJECT_DIR} entry so MFW can discover and
        # scan the source tree in its own Python 3.12 environment.
        agent["embedded"] = True
    else:
        # Compatibility for older MFW bundles following Maa_bbb's standalone
        # embedded-Python installation pattern.
        agent["child_exec"] = "./python/bin/python3"
        agent["child_args"] = ["-u", "./agent/main.py"]
        agent["embedded"] = True
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")


def _rewrite_android_controller_paths(output: Path, repo_root: Path) -> None:
    """Point saved Android profiles at this checkout's bundled ADB.

    MFW stores controller settings as mutable profile JSON.  Derived
    candidates can otherwise inherit an absolute path from the machine that
    produced the base candidate, which is especially easy to miss after the
    project moves between volumes.
    """

    config_dir = Path(output) / "config/configs"
    if not config_dir.is_dir():
        return
    adb_path = (Path(repo_root) / "install/android-sdk/platform-tools/adb").resolve()
    for path in sorted(config_dir.glob("c_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        changed = False

        def visit(value: Any) -> None:
            nonlocal changed
            if isinstance(value, dict):
                if value.get("controller_type") == "android":
                    android = value.get("android")
                    if isinstance(android, dict) and "adb_path" in android:
                        android["adb_path"] = str(adb_path)
                        changed = True
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)

        visit(payload)
        if changed:
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=4) + "\n",
                encoding="utf-8",
            )


def _disable_mfw_auto_update(output: Path) -> None:
    """Disable the GUI updater in every assembled MJA candidate.

    The bundled MFW GUI otherwise starts its updater before GAME_START and
    shows a ``GitHub更新失败`` banner when no update source is configured.
    Updating the game resource is a separate, explicit pipeline decision; it
    must not run as a side effect of launching MJA.
    """

    path = Path(output) / "config/config.json"
    if not path.is_file():
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    update = payload.setdefault("Update", {})
    if not isinstance(update, dict):
        raise ValueError("MFW config Update section must be an object")
    update["auto_update"] = False
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")


@dataclass(frozen=True)
class BuildMetadata:
    mja_commit: str
    target: str
    resolved_at: str
    mfw: Mapping[str, str]
    maafw: Mapping[str, str]
    payload_sha256: str
    immutable_tree_sha256: str
    base_metadata_sha256: str | None = None

    def to_mapping(self) -> dict[str, Any]:
        return {
            "mja_commit": self.mja_commit,
            "target": self.target,
            "resolved_at": self.resolved_at,
            "mfw": dict(self.mfw),
            "maafw": dict(self.maafw),
            "payload_sha256": self.payload_sha256,
            "immutable_tree_sha256": self.immutable_tree_sha256,
            "base_metadata_sha256": self.base_metadata_sha256,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "BuildMetadata":
        required = (
            "mja_commit",
            "target",
            "resolved_at",
            "mfw",
            "maafw",
            "payload_sha256",
            "immutable_tree_sha256",
        )
        missing = [key for key in required if key not in payload]
        if missing:
            raise ValueError(f"build metadata missing {', '.join(missing)}")
        if payload["target"] != TARGET:
            raise ValueError(f"unsupported candidate target: {payload['target']!r}")
        for key in ("payload_sha256", "immutable_tree_sha256"):
            value = payload[key]
            if not isinstance(value, str) or len(value) != 64:
                raise ValueError(f"invalid metadata {key}")
            if any(character not in "0123456789abcdefABCDEF" for character in value):
                raise ValueError(f"invalid metadata {key}")
        for asset_key in ("mfw", "maafw"):
            asset = payload[asset_key]
            if not isinstance(asset, Mapping):
                raise ValueError(f"invalid metadata {asset_key}")
            asset_digest = asset.get("sha256")
            if not isinstance(asset_digest, str) or len(asset_digest) != 64:
                raise ValueError(f"invalid metadata {asset_key}.sha256")
            if any(character not in "0123456789abcdefABCDEF" for character in asset_digest):
                raise ValueError(f"invalid metadata {asset_key}.sha256")
        base_digest = payload.get("base_metadata_sha256")
        if base_digest is not None and (
            not isinstance(base_digest, str)
            or len(base_digest) != 64
            or any(character not in "0123456789abcdefABCDEF" for character in base_digest)
        ):
            raise ValueError("invalid metadata base_metadata_sha256")
        return cls(
            mja_commit=str(payload["mja_commit"]),
            target=str(payload["target"]),
            resolved_at=str(payload["resolved_at"]),
            mfw=dict(payload["mfw"]),
            maafw=dict(payload["maafw"]),
            payload_sha256=str(payload["payload_sha256"]),
            immutable_tree_sha256=str(payload["immutable_tree_sha256"]),
            base_metadata_sha256=payload.get("base_metadata_sha256"),
        )


def load_metadata(candidate: Path) -> BuildMetadata:
    path = Path(candidate) / METADATA_NAME
    return BuildMetadata.from_mapping(json.loads(path.read_text(encoding="utf-8")))


def _asset_metadata(asset: ReleaseAsset, archive: Path) -> dict[str, str]:
    return {
        "repo": asset.repo,
        "tag": asset.tag,
        "name": asset.name,
        "url": asset.url,
        "sha256": sha256(archive),
    }


def _canonical_interface(path: Path) -> bytes:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload.get("agent"), dict):
        agent = payload["agent"]
        for key in ("child_exec", "child_args", "embedded"):
            agent.pop(key, None)
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _canonical_embedded_agent_source(relative: str, payload: bytes) -> bytes:
    """Normalize the source rewrite performed by MFW's embedded loader.

    Embedded MFW does not execute ``AgentServer`` decorators in a child
    process.  On its first load it rewrites bare custom-action decorators to
    the equivalent ``maa.resource`` registration and then imports the
    modules in the UI process.  That rewrite is intentional and deterministic
    but changes the copied source files in place.  Treat the two spellings as
    one payload representation so a candidate remains verifiable after its
    first real run without weakening checks for unrelated source changes.
    """

    if not (relative.startswith("agent/") and relative.endswith(".py")):
        return payload
    try:
        source = payload.decode("utf-8")
    except UnicodeDecodeError:
        return payload
    agent_import = "from maa.agent.agent_server import AgentServer"
    resource_import = "from maa.resource import resource"

    # MFW's embedded loader rewrites custom actions to the resource API.  Keep
    # the historical canonical spelling for actions because existing build
    # metadata was generated with that normalization.
    if agent_import in source and "@AgentServer.custom_action(" in source:
        return source.replace(agent_import, resource_import).replace(
            "@AgentServer.custom_action(", "@resource.custom_action("
        ).encode("utf-8")

    # The loader applies the same rewrite to custom recognitions, but the
    # original verifier only handled actions.  Existing candidates therefore
    # retain AgentServer spelling in their metadata while their first MFW run
    # changes the installed file to resource spelling.  Normalize both forms
    # back to the legacy spelling so post-run verification remains stable.
    if resource_import in source and "@resource.custom_recognition(" in source:
        return source.replace(resource_import, agent_import).replace(
            "@resource.custom_recognition(", "@AgentServer.custom_recognition("
        ).encode("utf-8")
    # The embedded loader removes the AgentServer tasker-sink decorator and
    # its indented import, then discovers the sink through the loaded module.
    # Normalize that deterministic rewrite as well so post-run verification
    # does not mistake the loader's registration mode for payload tampering.
    if "@AgentServer.tasker_sink()" in source:
        return source.replace(
            f"    {agent_import}\n", ""
        ).replace(
            f"{agent_import}\n", ""
        ).replace("@AgentServer.tasker_sink()\n", "").encode("utf-8")
    return payload


def _payload_records(root: Path) -> Iterable[tuple[str, bytes]]:
    root = Path(root)
    source_interface = root / "assets/interface.json"
    if not source_interface.is_file():
        source_interface = root / "assets/interface.mfw.json"
    installed = (root / "interface.json").is_file() and not source_interface.is_file()
    interface_path = root / "interface.json" if installed else source_interface
    yield "interface.json", _canonical_interface(interface_path)
    for directory in _payload_directories(interface_path):
        if installed:
            source = root / directory
        else:
            source_root = root if directory == "agent" else root / "assets"
            source = source_root / directory
        if not source.is_dir():
            raise FileNotFoundError(source)
        for file in _iter_files(source):
            relative = file.relative_to(source)
            if _is_generated_runtime_cache(relative):
                continue
            record_name = f"{directory}/{relative.as_posix()}"
            yield record_name, _canonical_embedded_agent_source(
                record_name, file.read_bytes()
            )
    for filename in ("CFA_setting.json", "requirements.txt"):
        file = root / filename
        if not file.is_file():
            raise FileNotFoundError(file)
        yield filename, file.read_bytes()


def _hash_records(records: Iterable[tuple[str, bytes]]) -> str:
    digest = hashlib.sha256()
    for name, payload in sorted(records):
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(payload)
        digest.update(b"\0")
    return digest.hexdigest()


def hash_project_payload(root: Path) -> str:
    return _hash_records(_payload_records(Path(root)))


def _is_project_file(relative: Path) -> bool:
    return relative.name in PAYLOAD_FILES or (
        bool(relative.parts) and relative.parts[0] in PAYLOAD_ROOTS
    )


def _is_mutable_state(relative: Path) -> bool:
    # MFW rewrites both its configuration and diagnostic logs while running.
    # Neither tree is part of the immutable runtime payload.
    return relative.parts[:1] in {("config",), ("debug",)}


def _is_generated_runtime_cache(relative: Path) -> bool:
    return (
        "__pycache__" in relative.parts
        or relative.suffix in {".pyc", ".pyo"}
        or any(part.startswith("._") for part in relative.parts)
    )


def _immutable_tree_hash(
    candidate: Path, *, include_generated_cache: bool = False
) -> str:
    records: list[tuple[str, bytes]] = []
    for path in _iter_files(candidate):
        relative = path.relative_to(candidate)
        if (
            relative.name == METADATA_NAME
            or _is_project_file(relative)
            or _is_mutable_state(relative)
            or (
                not include_generated_cache
                and _is_generated_runtime_cache(relative)
            )
        ):
            continue
        records.append((relative.as_posix(), path.read_bytes()))
    return _hash_records(records)


def _write_metadata(output: Path, metadata: BuildMetadata) -> None:
    target = output / METADATA_NAME
    temporary = target.with_name(target.name + ".part")
    try:
        with temporary.open("w", encoding="utf-8") as stream:
            stream.write(json.dumps(metadata.to_mapping(), ensure_ascii=False, indent=2) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _new_metadata(
    *,
    commit: str,
    mfw: Mapping[str, str],
    maafw: Mapping[str, str],
    output: Path,
    base_metadata_sha256: str | None = None,
) -> BuildMetadata:
    return BuildMetadata(
        mja_commit=commit,
        target=TARGET,
        resolved_at=datetime.now(timezone.utc).isoformat(),
        mfw=dict(mfw),
        maafw=dict(maafw),
        payload_sha256=hash_project_payload(output),
        immutable_tree_sha256=_immutable_tree_hash(output),
        base_metadata_sha256=base_metadata_sha256,
    )


def _verify_runtime_candidate(candidate: Path) -> BuildMetadata:
    metadata = load_metadata(candidate)
    actual_hash = _immutable_tree_hash(candidate)
    if metadata.immutable_tree_sha256 != actual_hash:
        # Candidates created before generated Python caches were excluded from
        # the immutable tree may still be reused when their recorded hash is
        # unchanged.  New candidates never include these re-creatable files.
        legacy_hash = _immutable_tree_hash(candidate, include_generated_cache=True)
        if metadata.immutable_tree_sha256 != legacy_hash:
            raise ValueError("immutable candidate tree hash mismatch")
    _mfw_layout(candidate)
    for path in _iter_files(candidate):
        relative = path.relative_to(candidate)
        if _is_generated_runtime_cache(relative):
            continue
        if _is_probe_path(relative):
            raise ValueError("probe files are not allowed in a production candidate")
        if path.suffix == ".json" and "MJA_PROBE_" in path.read_text(encoding="utf-8"):
            raise ValueError("probe nodes are not allowed in a production candidate")
    return metadata


def build_install(
    repo_root: Path,
    output: Path,
    mfw_asset: ReleaseAsset,
    maa_asset: ReleaseAsset,
    commit: str,
    *,
    mfw_archive: Path,
    maa_archive: Path,
) -> BuildMetadata:
    prepare_output(output)
    _copy_mfw_archive(mfw_archive, output)
    _copy_maa_archive(maa_archive, output)
    native_bundle = repo_root / "vendor/maafw/v5.12.3/macos-arm64"
    if native_bundle.is_dir():
        install_mfw_native_bundle(output, native_bundle)
    elif Path(repo_root).resolve() == ROOT:
        raise FileNotFoundError(f"required MFW native bundle is missing: {native_bundle}")
    _mfw_layout(output)
    _copy_project_payload(repo_root, output)
    _rewrite_installed_interface(output)
    _disable_mfw_auto_update(output)
    _rewrite_android_controller_paths(output, repo_root)
    ensure_pair_profiles(output)
    apply_mfw_pyqt6_runtime_patch(output / "MFW")
    _activate_production_shared_runtime(repo_root, output)
    _remove_appledouble_files(output)
    metadata = _new_metadata(
        commit=commit,
        mfw=_asset_metadata(mfw_asset, mfw_archive),
        maafw=_asset_metadata(maa_asset, maa_archive),
        output=output,
    )
    _write_metadata(output, metadata)
    _remove_appledouble_files(output)
    return metadata


def _copy_base_runtime(base: Path, output: Path) -> None:
    def copy_entry(path: Path) -> None:
        relative = path.relative_to(base)
        if (
            relative.name == METADATA_NAME
            or _is_project_file(relative)
            or _is_generated_runtime_cache(relative)
        ):
            return
        # Debug logs are mutable run evidence, not part of the executable
        # candidate.  Copying them into every derived candidate duplicates
        # gigabytes of prior MFW logs and can exhaust the shared volume
        # before the next candidate is even assembled.  The acceptance run
        # creates a fresh debug tree when it starts.
        if relative.parts[:1] == ("debug",):
            return
        # A derived candidate must retain the base candidate's saved MFW
        # profile and its current profile id.  These files are the executable
        # task selection for a frozen acceptance batch; dropping them causes
        # MFW to silently create a default profile and wait/run the wrong set.
        target = output / relative
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            for child in path.iterdir():
                copy_entry(child)
        elif path.is_file():
            _copy_file(path, target)
        else:
            raise ValueError(f"unsupported base candidate entry: {path}")

    for path in base.iterdir():
        copy_entry(path)


def build_from_base(
    repo_root: Path, base_candidate: Path, output: Path, commit: str
) -> BuildMetadata:
    base_candidate = Path(base_candidate)
    base_metadata = _verify_runtime_candidate(base_candidate)
    prepare_output(output)
    _copy_base_runtime(base_candidate, output)
    native_bundle = repo_root / "vendor/maafw/v5.12.3/macos-arm64"
    if native_bundle.is_dir():
        install_mfw_native_bundle(output, native_bundle)
    elif Path(repo_root).resolve() == ROOT:
        raise FileNotFoundError(f"required MFW native bundle is missing: {native_bundle}")
    _copy_project_payload(repo_root, output)
    _rewrite_installed_interface(output)
    _disable_mfw_auto_update(output)
    _rewrite_android_controller_paths(output, repo_root)
    ensure_pair_profiles(output)
    apply_mfw_pyqt6_runtime_patch(output / "MFW")
    _activate_production_shared_runtime(repo_root, output)
    _remove_appledouble_files(output)
    metadata = _new_metadata(
        commit=commit,
        mfw=base_metadata.mfw,
        maafw=base_metadata.maafw,
        output=output,
        base_metadata_sha256=sha256(base_candidate / METADATA_NAME),
    )
    _write_metadata(output, metadata)
    _remove_appledouble_files(output)
    return metadata


def _compare_payload(repo_root: Path, candidate: Path) -> None:
    if hash_project_payload(repo_root) != hash_project_payload(candidate):
        raise ValueError("candidate payload hash mismatch")
    source_interface = _source_interface(repo_root)
    installed_interface = json.loads((candidate / "interface.json").read_text(encoding="utf-8"))
    if _mfw_layout(candidate) == MFW_LAYOUT_PYINSTALLER:
        source_payload = json.loads(source_interface.read_text(encoding="utf-8"))
        expected_agent = dict(source_payload.get("agent", {}))
        expected_agent["embedded"] = True
    else:
        expected_agent = {
            "child_exec": "./python/bin/python3",
            "child_args": ["-u", "./agent/main.py"],
            "embedded": True,
        }
    if installed_interface.get("agent") != expected_agent:
        raise ValueError("installed Agent interface paths are not normalized")
    if _canonical_interface(source_interface) != _canonical_interface(candidate / "interface.json"):
        raise ValueError("candidate interface payload mismatch")
    for relative, payload in _payload_records(repo_root):
        installed_path = candidate / relative
        if not installed_path.is_file():
            raise ValueError(f"candidate payload file missing: {relative}")
        if relative != "interface.json" and _canonical_embedded_agent_source(
            relative, installed_path.read_bytes()
        ) != payload:
            raise ValueError(f"candidate payload file mismatch: {relative}")


def verify_candidate(repo_root: Path, candidate: Path) -> BuildMetadata:
    candidate = Path(candidate)
    metadata = _verify_runtime_candidate(candidate)
    if not verify_mfw_pyqt6_runtime_patch(candidate / "MFW"):
        raise ValueError("candidate MFW runtime is missing the native failure-return patch")
    if metadata.payload_sha256 != hash_project_payload(candidate):
        raise ValueError("candidate payload metadata mismatch")
    _compare_payload(Path(repo_root), candidate)
    native_bundle = Path(repo_root) / "vendor/maafw/v5.12.3/macos-arm64"
    if native_bundle.is_dir():
        verify_mfw_native_bundle(candidate, native_bundle)
    elif Path(repo_root).resolve() == ROOT:
        raise FileNotFoundError(f"required MFW native bundle is missing: {native_bundle}")
    if Path(repo_root).resolve() == ROOT and _is_production_install_candidate(candidate):
        verify_mfw_shared_runtime(ROOT / "install", native_bundle)
    return metadata


def _git_commit(repo_root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"], text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _offline_asset(repo: str, archive: Path) -> ReleaseAsset:
    return ReleaseAsset(repo, "offline", archive.name, f"https://offline.invalid/{archive.name}")


def _build_cli(args: argparse.Namespace) -> BuildMetadata:
    repo_root = ROOT
    output = Path(args.output)
    commit = args.commit or _git_commit(repo_root)
    if args.base_candidate:
        if args.mfw_archive or args.maa_archive:
            raise ValueError("archive overrides cannot be combined with --base-candidate")
        return build_from_base(repo_root, Path(args.base_candidate), output, commit)
    if bool(args.mfw_archive) != bool(args.maa_archive):
        raise ValueError("--mfw-archive and --maa-archive must be supplied together")
    if args.mfw_archive:
        return build_install(
            repo_root,
            output,
            _offline_asset(MFW_REPO, Path(args.mfw_archive)),
            _offline_asset(MAA_REPO, Path(args.maa_archive)),
            commit,
            mfw_archive=Path(args.mfw_archive),
            maa_archive=Path(args.maa_archive),
        )
    mfw_asset = resolve_latest_asset(MFW_REPO, MFW_ASSET_PATTERN)
    maa_asset = resolve_latest_asset(MAA_REPO, MAA_ASSET_PATTERN)
    with tempfile.TemporaryDirectory(prefix="mja-mfw-download-") as temporary:
        cache = Path(temporary)
        mfw_archive = cache / mfw_asset.name
        maa_archive = cache / maa_asset.name
        download_asset(mfw_asset, mfw_archive)
        download_asset(maa_asset, maa_archive)
        return build_install(
            repo_root,
            output,
            mfw_asset,
            maa_asset,
            commit,
            mfw_archive=mfw_archive,
            maa_archive=maa_archive,
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--output", help="new candidate directory")
    modes.add_argument("--verify-candidate", metavar="PATH", help="validate an existing candidate")
    parser.add_argument("--base-candidate", help="derive output from a pinned runtime candidate")
    parser.add_argument("--mfw-archive", help="offline MFW zip")
    parser.add_argument("--maa-archive", help="offline MaaFramework zip")
    parser.add_argument("--commit", help="MJA source commit recorded in metadata")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.verify_candidate:
        metadata = verify_candidate(ROOT, Path(args.verify_candidate))
    else:
        metadata = _build_cli(args)
    print(json.dumps(metadata.to_mapping(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
