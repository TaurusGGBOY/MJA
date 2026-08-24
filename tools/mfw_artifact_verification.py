"""Verify provenance and immutable integrity of packaged MFW artifacts."""

from __future__ import annotations

import dis
import hashlib
import json
import marshal
import struct
import subprocess
import types
import zlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from tools.mfw_native_bundle import verify_mfw_native_bundle, verify_mfw_shared_runtime

ROOT = Path(__file__).resolve().parents[1]
TARGET = "macos-aarch64"
METADATA_NAME = "build-metadata.json"
PAYLOAD_ROOTS = ("tasks", "resource", "resource_android", "agent")
RESOURCE_ROOTS = ("resource", "resource_android")
PAYLOAD_FILES = ("interface.json", "CFA_setting.json", "requirements.txt")
MFW_LAYOUT_PYINSTALLER = "pyinstaller"
MFW_LAYOUT_LEGACY = "legacy"

_CARCHIVE_COOKIE_MAGIC = b"MEI\x0c\x0b\x0a\x0b\x0e"
_CARCHIVE_COOKIE_FORMAT = "!8sIIii64s"
_CARCHIVE_COOKIE_SIZE = struct.calcsize(_CARCHIVE_COOKIE_FORMAT)
_CARCHIVE_ENTRY_FORMAT = "!iIIIBc"
_CARCHIVE_ENTRY_SIZE = struct.calcsize(_CARCHIVE_ENTRY_FORMAT)
_PYZ_MAGIC = b"PYZ\x00"
_TASK_FLOW_MODULE = "app.core.runner.task_flow"
_HEX64 = frozenset("0123456789abcdefABCDEF")


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


def _is_generated_runtime_cache(relative: Path) -> bool:
    return (
        "__pycache__" in relative.parts
        or relative.suffix in {".pyc", ".pyo"}
        or any(part.startswith("._") for part in relative.parts)
    )


def _source_interface(repo_root: Path) -> Path:
    for candidate in (repo_root / "assets/interface.json", repo_root / "assets/interface.mfw.json"):
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("assets/interface.json or assets/interface.mfw.json")


def _payload_directories(interface_path: Path) -> tuple[str, ...]:
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
    if not any(root in RESOURCE_ROOTS for root in roots):
        roots.append("resource")
    roots.append("agent")
    return tuple(dict.fromkeys(roots))


def _canonical_interface(path: Path) -> bytes:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload.get("agent"), dict):
        agent = payload["agent"]
        for key in ("child_exec", "child_args", "embedded"):
            agent.pop(key, None)
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _canonical_embedded_agent_source(relative: str, payload: bytes) -> bytes:
    if not (relative.startswith("agent/") and relative.endswith(".py")):
        return payload
    try:
        source = payload.decode("utf-8")
    except UnicodeDecodeError:
        return payload
    agent_import = "from maa.agent.agent_server import AgentServer"
    resource_import = "from maa.resource import resource"
    if agent_import in source and "@AgentServer.custom_action(" in source:
        return source.replace(agent_import, resource_import).replace(
            "@AgentServer.custom_action(", "@resource.custom_action("
        ).encode("utf-8")
    if resource_import in source and "@resource.custom_recognition(" in source:
        return source.replace(resource_import, agent_import).replace(
            "@resource.custom_recognition(", "@AgentServer.custom_recognition("
        ).encode("utf-8")
    if "@AgentServer.tasker_sink()" in source:
        return source.replace(f"    {agent_import}\n", "").replace(
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
    return relative.parts[:1] in {("config",), ("debug",)}


def _immutable_tree_hash(candidate: Path, *, include_generated_cache: bool = False) -> str:
    records: list[tuple[str, bytes]] = []
    for path in _iter_files(candidate):
        relative = path.relative_to(candidate)
        if (
            relative.name == METADATA_NAME
            or _is_project_file(relative)
            or _is_mutable_state(relative)
            or (not include_generated_cache and _is_generated_runtime_cache(relative))
        ):
            continue
        records.append((relative.as_posix(), path.read_bytes()))
    return _hash_records(records)


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
            if not isinstance(value, str) or len(value) != 64 or any(
                character not in _HEX64 for character in value
            ):
                raise ValueError(f"invalid metadata {key}")
        for asset_key in ("mfw", "maafw"):
            asset = payload[asset_key]
            if not isinstance(asset, Mapping):
                raise ValueError(f"invalid metadata {asset_key}")
            asset_digest = asset.get("sha256")
            if not isinstance(asset_digest, str) or len(asset_digest) != 64 or any(
                character not in _HEX64 for character in asset_digest
            ):
                raise ValueError(f"invalid metadata {asset_key}.sha256")
        base_digest = payload.get("base_metadata_sha256")
        if base_digest is not None and (
            not isinstance(base_digest, str)
            or len(base_digest) != 64
            or any(character not in _HEX64 for character in base_digest)
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
            base_metadata_sha256=base_digest,
        )


def load_metadata(candidate: Path) -> BuildMetadata:
    path = Path(candidate) / METADATA_NAME
    return BuildMetadata.from_mapping(json.loads(path.read_text(encoding="utf-8")))


def _find_carchive(data: bytes) -> tuple[int, int, int] | None:
    cookie_pos = data.rfind(_CARCHIVE_COOKIE_MAGIC)
    if cookie_pos < 0:
        return None
    cookie_end = cookie_pos + _CARCHIVE_COOKIE_SIZE
    if cookie_end > len(data):
        raise ValueError("truncated PyInstaller CArchive cookie")
    magic, archive_length, toc_pos, toc_length, _pyver, _pylib = struct.unpack(
        _CARCHIVE_COOKIE_FORMAT, data[cookie_pos:cookie_end]
    )
    if magic != _CARCHIVE_COOKIE_MAGIC:
        raise ValueError("invalid PyInstaller CArchive magic")
    overlay_pos = cookie_end - archive_length
    absolute_toc_pos = overlay_pos + toc_pos
    if (
        archive_length <= 0
        or archive_length > cookie_end
        or overlay_pos < 0
        or toc_length <= 0
        or absolute_toc_pos < overlay_pos
        or absolute_toc_pos + toc_length != cookie_pos
    ):
        raise ValueError("invalid PyInstaller CArchive table of contents")
    return overlay_pos, absolute_toc_pos, cookie_pos


def _carchive_entries(data: bytes, archive: tuple[int, int, int]) -> list[tuple[str, int, int]]:
    _overlay_pos, toc_pos, cookie_pos = archive
    table = data[toc_pos:cookie_pos]
    entries: list[tuple[str, int, int]] = []
    offset = 0
    while offset < len(table):
        if offset + 4 > len(table):
            raise ValueError("truncated PyInstaller CArchive table entry")
        entry_size = struct.unpack("!i", table[offset : offset + 4])[0]
        if entry_size < _CARCHIVE_ENTRY_SIZE or offset + entry_size > len(table):
            raise ValueError("invalid PyInstaller CArchive table entry size")
        _size, entry_pos, compressed_size, _uncompressed_size, _flag, _typecode = struct.unpack(
            _CARCHIVE_ENTRY_FORMAT, table[offset : offset + _CARCHIVE_ENTRY_SIZE]
        )
        raw_name = table[offset + _CARCHIVE_ENTRY_SIZE : offset + entry_size]
        entries.append((raw_name.split(b"\0", 1)[0].decode("utf-8"), entry_pos, compressed_size))
        offset += entry_size
    if offset != len(table):
        raise ValueError("PyInstaller CArchive table is not aligned")
    return entries


def _pyinstaller_pyz(data: bytes) -> bytes | None:
    archive = _find_carchive(data)
    if archive is None:
        return None
    overlay_pos, _toc_pos, _cookie_pos = archive
    for name, entry_pos, compressed_size in _carchive_entries(data, archive):
        if name == "PYZ.pyz":
            start = overlay_pos + entry_pos
            return data[start : start + compressed_size]
    raise ValueError("PyInstaller archive does not contain PYZ.pyz")


def _contains_legacy_fail_fast(pyz: bytes) -> bool:
    if not pyz.startswith(_PYZ_MAGIC) or len(pyz) < 12:
        raise ValueError("invalid PYZ.pyz header")
    toc_pos = struct.unpack("!i", pyz[8:12])[0]
    toc = marshal.loads(pyz[toc_pos:])
    _ispkg, code_pos, compressed_size = next(
        entry[1] for entry in toc if entry[0] == _TASK_FLOW_MODULE
    )
    module = marshal.loads(zlib.decompress(pyz[code_pos : code_pos + compressed_size]))

    def walk(code: types.CodeType) -> bool:
        if code.co_name == "run_task" and "_stop_task_timeout" in code.co_names:
            # Python 3.14 cannot always disassemble bytecode marshalled by an
            # older PyInstaller runtime (the code object's name table can be
            # indexed using an opcode layout that changed between versions).
            # This verifier is a defensive legacy-pattern scan; an
            # undecodable function is not evidence that the retired pattern
            # exists, so let the runtime candidate verification continue.
            try:
                instructions = list(dis.get_instructions(code))
            except (IndexError, ValueError):
                return False
            for index, instruction in enumerate(instructions[:-2]):
                if (
                    instruction.opname == "RETURN_CONST"
                    and instruction.argval is False
                    and instructions[index + 1].opname == "LOAD_DEREF"
                    and instructions[index + 1].argval == "self"
                    and instructions[index + 2].opname == "LOAD_ATTR"
                    and instructions[index + 2].argval == "_stop_task_timeout"
                ):
                    return True
        return any(
            isinstance(constant, types.CodeType) and walk(constant)
            for constant in code.co_consts
        )

    return walk(module)


def _verify_task_flow_runtime(runtime: Path) -> None:
    if not runtime.is_file():
        raise FileNotFoundError(runtime)
    data = runtime.read_bytes()
    if _find_carchive(data) is None:
        return
    pyz = _pyinstaller_pyz(data)
    if pyz is not None and _contains_legacy_fail_fast(pyz):
        raise ValueError("candidate MFW runtime contains the retired fail-fast patch")


def verify_default_task_flow_runner(candidate: Path) -> None:
    """Reject a packaged MFW binary containing the retired queue patch."""

    _verify_task_flow_runtime(Path(candidate) / "MFW")


def _verify_runtime_candidate(candidate: Path) -> BuildMetadata:
    metadata = load_metadata(candidate)
    actual_hash = _immutable_tree_hash(candidate)
    if metadata.immutable_tree_sha256 != actual_hash:
        legacy_hash = _immutable_tree_hash(candidate, include_generated_cache=True)
        if metadata.immutable_tree_sha256 != legacy_hash:
            raise ValueError("immutable candidate tree hash mismatch")
    _mfw_layout(candidate)
    for path in _iter_files(candidate):
        relative = path.relative_to(candidate)
        if _is_generated_runtime_cache(relative):
            continue
        if any("MJA_PROBE_" in part for part in relative.parts):
            raise ValueError("probe files are not allowed in a production candidate")
        if path.suffix == ".json" and "MJA_PROBE_" in path.read_text(encoding="utf-8"):
            raise ValueError("probe nodes are not allowed in a production candidate")
    return metadata


def _is_production_install_candidate(candidate: Path) -> bool:
    return Path(candidate).resolve().parent == ROOT / "install"


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
    verify_default_task_flow_runner(candidate)
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


def _load_object(path: Path, *, kind: str) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {kind}: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{kind} must be an object")
    return payload


def _digest(payload: Mapping[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or len(value) != 64 or any(
        character not in _HEX64 for character in value
    ):
        raise ValueError(f"artifact record has invalid {field}")
    return value.lower()


def _non_empty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"artifact record is missing {field}")
    return value.strip()


def _git_output(repo_root: Path, *args: str) -> str:
    record = subprocess.run(
        ["git", *args], cwd=repo_root, check=False, capture_output=True, text=True
    )
    if record.returncode != 0:
        detail = record.stderr.strip() or record.stdout.strip()
        raise ValueError(f"git {' '.join(args)} failed: {detail}")
    return record.stdout.strip()


def _repo_relative_path(path: Path, repo_root: Path, field: str) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(f"{field} must be inside the repository: {path}") from exc


def _record_repo_path(value: Any, repo_root: Path, field: str) -> Path:
    relative = Path(_non_empty_string(value, field))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"artifact record {field} escapes repository")
    return repo_root / relative


def _artifact_manifest(artifact: Path, manifest_path: Path) -> dict[str, str]:
    artifact = Path(artifact)
    if not artifact.is_dir():
        raise ValueError(f"artifact is not a directory: {artifact}")
    if manifest_path.resolve() == artifact.resolve() or manifest_path.is_relative_to(artifact):
        raise ValueError("artifact manifest must be outside the artifact root")
    files: dict[str, str] = {}
    for path in sorted(artifact.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"artifact contains symlink: {path}")
        if path.is_file():
            files[path.relative_to(artifact).as_posix()] = sha256(path)
    if not files:
        raise ValueError("artifact has no files")
    return files


def _read_sha_manifest(manifest_path: Path, artifact: Path) -> dict[str, str]:
    try:
        lines = Path(manifest_path).read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValueError(f"cannot read artifact manifest: {manifest_path}") from exc
    entries: dict[str, str] = {}
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            raise ValueError(f"artifact manifest line {line_number} is malformed")
        digest, raw_path = parts
        if len(digest) != 64 or any(character not in _HEX64 for character in digest):
            raise ValueError(f"artifact manifest line {line_number} has invalid SHA")
        relative = Path(raw_path.lstrip("*"))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"artifact manifest line {line_number} escapes artifact")
        normalized = relative.as_posix()
        if normalized in entries:
            raise ValueError(f"artifact manifest contains duplicate path: {normalized}")
        target = artifact / relative
        if not target.is_file() or target.is_symlink():
            raise ValueError(f"artifact manifest path does not exist: {normalized}")
        actual = sha256(target)
        if actual != digest.lower():
            raise ValueError(f"artifact manifest SHA mismatch: {normalized}")
        entries[normalized] = digest.lower()
    expected = _artifact_manifest(artifact, Path(manifest_path))
    if set(entries) != set(expected):
        missing = sorted(set(expected) - set(entries))
        extra = sorted(set(entries) - set(expected))
        raise ValueError(f"artifact manifest file set mismatch; missing={missing}, extra={extra}")
    return entries


def _tag_commit(repo_root: Path, tag: str) -> str:
    tag = _non_empty_string(tag, "tag")
    _git_output(repo_root, "check-ref-format", f"refs/tags/{tag}")
    return _git_output(repo_root, "rev-parse", "-q", "--verify", f"refs/tags/{tag}^{{}}")


def write_legacy_rollback(
    output_path: Path,
    *,
    tag: str,
    artifact: Path,
    manifest: Path,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    """Write a rollback record for a tagged, fully hashed artifact."""

    output_path = Path(output_path)
    repo_root = Path(repo_root)
    artifact = Path(artifact)
    manifest = Path(manifest)
    head_commit = _git_output(repo_root, "rev-parse", "HEAD")
    tag_commit = _tag_commit(repo_root, tag)
    if tag_commit != head_commit:
        raise ValueError("rollback tag does not point at current HEAD")
    entries = _read_sha_manifest(manifest, artifact)
    record = {
        "schema_version": 1,
        "tag": tag,
        "commit": head_commit,
        "tag_commit": tag_commit,
        "artifact_path": _repo_relative_path(artifact, repo_root, "artifact"),
        "manifest_path": _repo_relative_path(manifest, repo_root, "manifest"),
        "manifest_sha256": sha256(manifest),
        "artifact_storage": "local-pending-publication",
        "verified": True,
        "files": entries,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(output_path.name + ".tmp")
    temporary_path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary_path.replace(output_path)
    return record


def verify_legacy_rollback(record_path: Path, *, repo_root: Path = ROOT) -> dict[str, Any]:
    record_path = Path(record_path)
    repo_root = Path(repo_root)
    record = _load_object(record_path, kind="rollback record")
    if record.get("schema_version") != 1 or record.get("verified") is not True:
        raise ValueError("rollback record is not verified")
    if record.get("artifact_storage") != "local-pending-publication":
        raise ValueError("rollback record has invalid artifact_storage")
    tag = _non_empty_string(record.get("tag"), "tag")
    head_commit = _git_output(repo_root, "rev-parse", "HEAD")
    tag_commit = _tag_commit(repo_root, tag)
    if record.get("commit") != head_commit or record.get("tag_commit") != tag_commit:
        raise ValueError("rollback commit does not match tag and HEAD")
    artifact = _record_repo_path(record.get("artifact_path"), repo_root, "artifact_path")
    manifest = _record_repo_path(record.get("manifest_path"), repo_root, "manifest_path")
    if sha256(manifest) != _digest(record, "manifest_sha256"):
        raise ValueError("rollback manifest hash does not match")
    entries = _read_sha_manifest(manifest, artifact)
    if record.get("files") != entries:
        raise ValueError("rollback file manifest does not match artifact")
    return record


__all__ = [
    "BuildMetadata",
    "METADATA_NAME",
    "MFW_LAYOUT_LEGACY",
    "MFW_LAYOUT_PYINSTALLER",
    "PAYLOAD_FILES",
    "PAYLOAD_ROOTS",
    "RESOURCE_ROOTS",
    "TARGET",
    "hash_project_payload",
    "load_metadata",
    "sha256",
    "verify_candidate",
    "verify_default_task_flow_runner",
    "verify_legacy_rollback",
    "write_legacy_rollback",
]
