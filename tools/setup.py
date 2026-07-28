from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import stat
import subprocess
import tarfile
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit

from tools.native_bundle import load_patched_bundle

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CLICLICK = Path("/opt/homebrew/bin/cliclick")
CHUNK_SIZE = 1024 * 1024
MAAFW_VERSION = "5.12.2"
MACOS_CONTROL_UNIT_LIBRARY = "libMaaMacOSControlUnit.dylib"
OFFICIAL_BASE_LIBRARY_SHA256 = (
    "f9f341ca13db62ef6f8bd642862510d191efbfc55de896fdec523b5b507ffc9a"
)
OVERLAY_JOURNAL_NAME = ".mja-macos-control-unit-overlay.json"


@dataclass(frozen=True)
class Artifact:
    id: str
    version: str
    filename: str
    size: int
    sha256: str
    url: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> Artifact:
        fields = ("id", "version", "filename", "size", "sha256", "url")
        missing = next((field for field in fields if field not in value), None)
        if missing:
            raise ValueError(f"manifest artifact missing {missing}")
        filename = str(value["filename"])
        if Path(filename).name != filename or not filename:
            raise ValueError("manifest filename must be a simple file name")
        digest = str(value["sha256"]).lower()
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError("manifest sha256 must be a 64-character hexadecimal digest")
        if urlsplit(str(value["url"])).scheme.lower() != "https":
            raise ValueError("manifest artifact URL must use HTTPS")
        size = value["size"]
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise ValueError("manifest artifact size must be a non-negative integer")
        return cls(
            id=str(value["id"]),
            version=str(value["version"]),
            filename=filename,
            size=size,
            sha256=digest,
            url=str(value["url"]),
        )


def load_manifest(path: Path) -> tuple[Artifact, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("runtime manifest schema_version must be 1")
    artifacts = tuple(Artifact.from_mapping(item) for item in payload.get("artifacts", []))
    if {item.id for item in artifacts} != {"maafw", "mfa"}:
        raise ValueError("runtime manifest must contain exactly maafw and mfa")
    return artifacts


def verify_download(path: Path, expected_size: int, expected_sha256: str) -> None:
    actual_size = path.stat().st_size
    if actual_size != expected_size:
        raise ValueError(f"size mismatch: expected {expected_size}, got {actual_size}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    if digest.hexdigest().lower() != expected_sha256.lower():
        raise ValueError("SHA-256 digest mismatch")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_https(url: str) -> None:
    if urlsplit(url).scheme.lower() != "https":
        raise ValueError("runtime downloads must use HTTPS")


def stream_download(
    url: str,
    destination: Path,
    expected_size: int,
    expected_sha256: str,
    *,
    opener: Callable[..., Any] | None = None,
) -> Path:
    """Download one artifact into a verified final file without exposing partial data."""

    _require_https(url)
    opener = opener or urllib.request.urlopen
    destination.parent.mkdir(parents=True, exist_ok=True)
    part = destination.with_name(destination.name + ".part")
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "MJA-setup/1"})
        with opener(request) as response:
            final_url = str(getattr(response, "geturl", lambda: url)())
            _require_https(final_url)
            with part.open("wb") as handle:
                while True:
                    chunk = response.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())
        verify_download(part, expected_size, expected_sha256)
        part.replace(destination)
    except Exception:
        part.unlink(missing_ok=True)
        raise
    return destination


def download_artifact(artifact: Artifact, downloads_dir: Path) -> Path:
    destination = downloads_dir / artifact.filename
    if destination.exists():
        try:
            verify_download(destination, artifact.size, artifact.sha256)
            return destination
        except (OSError, ValueError):
            destination.unlink(missing_ok=True)
    return stream_download(
        artifact.url,
        destination,
        artifact.size,
        artifact.sha256,
    )


def _safe_member_path(destination: Path, name: str) -> Path:
    normalized = name.replace("\\", "/")
    posix = PurePosixPath(normalized)
    windows = PureWindowsPath(normalized)
    if posix.is_absolute() or windows.is_absolute() or windows.drive:
        raise ValueError(f"archive path traversal rejected: {name}")
    if any(part == ".." for part in posix.parts):
        raise ValueError(f"archive path traversal rejected: {name}")
    target = (destination / posix).resolve()
    if target != destination.resolve() and destination.resolve() not in target.parents:
        raise ValueError(f"archive path traversal rejected: {name}")
    return target


def _validate_tar_members(members: list[tarfile.TarInfo], destination: Path) -> None:
    for member in members:
        _safe_member_path(destination, member.name)
        if member.issym() or member.islnk() or not (member.isdir() or member.isfile()):
            raise ValueError(f"unsupported or unsafe archive member: {member.name}")


def _validate_zip_members(members: list[zipfile.ZipInfo], destination: Path) -> None:
    for member in members:
        _safe_member_path(destination, member.filename)
        mode = (member.external_attr >> 16) & 0o170000
        if mode == 0o120000:
            raise ValueError(f"unsupported or unsafe archive member: {member.filename}")


def extract_archive(archive: Path, destination: Path) -> Path:
    """Extract a tar/zip archive after validating every member against traversal."""

    destination.mkdir(parents=True, exist_ok=True)
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as handle:
            members = handle.infolist()
            _validate_zip_members(members, destination)
            for member in members:
                target = _safe_member_path(destination, member.filename)
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with handle.open(member) as source, target.open("wb") as output:
                        shutil.copyfileobj(source, output, CHUNK_SIZE)
        return destination
    if tarfile.is_tarfile(archive):
        with tarfile.open(archive) as handle:
            members = handle.getmembers()
            _validate_tar_members(members, destination)
            for member in members:
                target = _safe_member_path(destination, member.name)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                source = handle.extractfile(member)
                if source is None:
                    raise ValueError(f"archive member has no data: {member.name}")
                with source, target.open("wb") as output:
                    shutil.copyfileobj(source, output, CHUNK_SIZE)
        return destination
    raise ValueError(f"unsupported runtime archive: {archive.name}")


def assert_supported_platform(*, system: str | None = None, machine: str | None = None) -> None:
    system = system or platform.system()
    machine = machine or platform.machine()
    if system != "Darwin":
        raise RuntimeError("MJA runtime setup requires Darwin")
    if machine != "arm64":
        raise RuntimeError("MJA runtime setup requires Apple Silicon arm64")


def ensure_venv(
    install_root: Path,
    *,
    python_executable: str = "/opt/homebrew/bin/python3",
    runner: Callable[..., Any] = subprocess.run,
) -> Path:
    venv_root = install_root / ".venv"
    python = venv_root / "bin/python"
    if not python.exists():
        venv_root.parent.mkdir(parents=True, exist_ok=True)
        runner([python_executable, "-m", "venv", str(venv_root)], check=True)
    if not python.exists():
        raise RuntimeError(f"venv creation did not produce {python}")
    return python


def install_requirements(
    python: Path,
    requirements: Path,
    *,
    runner: Callable[..., Any] = subprocess.run,
) -> None:
    runner([str(python), "-m", "pip", "install", "--requirement", str(requirements)], check=True)


def _find_named(root: Path, name: str, *, directory: bool = False) -> Path | None:
    for candidate in root.rglob(name):
        if candidate.is_dir() == directory:
            return candidate
    return None


def _atomic_copytree(source: Path, destination: Path) -> None:
    staging = destination.with_name(destination.name + ".staging")
    if staging.exists():
        shutil.rmtree(staging)
    shutil.copytree(source, staging)
    if destination.exists():
        backup = destination.with_name(destination.name + ".previous")
        if backup.exists():
            shutil.rmtree(backup)
        destination.replace(backup)
    staging.replace(destination)


def _fsync_copy(source: Path, destination: Path) -> None:
    shutil.copyfile(source, destination)
    with destination.open("rb") as handle:
        os.fsync(handle.fileno())


def _require_install_scope(install_root: Path) -> Path:
    root = Path(os.path.abspath(install_root))
    for ancestor in root.parents:
        try:
            if stat.S_ISLNK(ancestor.lstat().st_mode):
                raise ValueError(f"install root ancestor must not be a symlink: {ancestor}")
        except OSError as exc:
            raise ValueError(f"install root ancestor is unavailable: {ancestor}") from exc
    if root.is_symlink() or not root.is_dir():
        raise ValueError(f"install root must be a real directory: {root}")
    for directory in (
        root,
        root / "runtime",
        root / "runtime" / "maafw",
        root / "runtime" / "maafw" / "bin",
    ):
        try:
            mode = directory.lstat().st_mode
        except OSError as exc:
            raise ValueError(f"install directory is unavailable: {directory}") from exc
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            raise ValueError(f"install directory must not be a symlink: {directory}")
    return root


def _validate_bundle_base(bundle_root: Path, base_library: Path) -> None:
    bundle = load_patched_bundle(bundle_root, require_library=True)
    if bundle.manifest["base_library_sha256"] != OFFICIAL_BASE_LIBRARY_SHA256:
        raise ValueError("patched bundle is not bound to the official base library")
    if base_library.is_symlink() or not base_library.is_file():
        raise ValueError(f"official base library is missing: {base_library}")
    if sha256_file(base_library) != OFFICIAL_BASE_LIBRARY_SHA256:
        raise ValueError(f"official base library digest mismatch: {base_library}")


def _remove_file(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _write_overlay_journal(path: Path, payload: Mapping[str, Any]) -> None:
    staging = path.with_name(path.name + ".staging")
    try:
        staging.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        with staging.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(staging, path)
    finally:
        _remove_file(staging)


def _recover_overlay_journal(root: Path, destinations: tuple[Path, ...]) -> None:
    journal_path = root / OVERLAY_JOURNAL_NAME
    if not journal_path.exists():
        return
    recovered = False
    try:
        payload = json.loads(journal_path.read_text(encoding="utf-8"))
        backup_names = payload["backup_names"]
        if payload.get("schema_version") != 1 or not isinstance(backup_names, list):
            raise ValueError("invalid overlay journal")
        expected = {path.name for path in destinations}
        if len(backup_names) != len(expected) or {
            item.get("destination") if isinstance(item, dict) else None for item in backup_names
        } != expected:
            raise ValueError("invalid overlay journal destinations")
        for item in backup_names:
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("backup"), str)
                or Path(item["backup"]).name != item["backup"]
            ):
                raise ValueError("invalid overlay journal destination")
        for destination in destinations:
            item = next(item for item in backup_names if item["destination"] == destination.name)
            backup = destination.with_name(item["backup"])
            if backup.is_symlink() or backup.parent != destination.parent:
                raise ValueError("overlay journal backup is unavailable")
            if backup.is_file():
                os.replace(backup, destination)
            elif (
                destination.is_file()
                and not destination.is_symlink()
                and sha256_file(destination) == OFFICIAL_BASE_LIBRARY_SHA256
            ):
                # The prior recovery may have completed this destination before
                # the process crashed. Treat that state as already restored.
                continue
            else:
                raise ValueError("overlay journal backup is unavailable")
        recovered = True
    finally:
        if recovered:
            _remove_file(journal_path)


def overlay_patched_macos_control_unit(install_root: Path, bundle_root: Path) -> None:
    """Safely replace both installed macOS control-unit copies with the patch."""

    root = _require_install_scope(install_root)
    destinations = (
        root / MACOS_CONTROL_UNIT_LIBRARY,
        root / "runtime" / "maafw" / "bin" / MACOS_CONTROL_UNIT_LIBRARY,
    )
    _recover_overlay_journal(root, destinations)
    bundle = load_patched_bundle(bundle_root, require_library=True)
    if bundle.library is None:  # pragma: no cover - require_library enforces this
        raise ValueError(f"patched library is missing: {MACOS_CONTROL_UNIT_LIBRARY}")
    if bundle.manifest["base_library_sha256"] != OFFICIAL_BASE_LIBRARY_SHA256:
        raise ValueError("patched bundle is not bound to the official base library")

    version_path = root / "runtime" / "maafw" / "VERSION"
    try:
        installed_version = version_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError("installed MaaFramework version is unavailable") from exc
    if installed_version != f"{MAAFW_VERSION}\n":
        raise ValueError(f"installed MaaFramework version must be {MAAFW_VERSION}")

    expected_base = bundle.manifest["base_library_sha256"]
    for destination in destinations:
        if destination.is_symlink() or not destination.is_file():
            raise ValueError(f"installed base library is missing: {destination}")
        if sha256_file(destination) != expected_base:
            raise ValueError(f"installed base library digest mismatch: {destination}")

    stages = tuple(
        destination.with_name(destination.name + ".staging") for destination in destinations
    )
    backup_paths: list[Path] = []
    backup_candidates: list[Path] = []
    journal_path = root / OVERLAY_JOURNAL_NAME
    committed = False
    rollback_ok = True
    try:
        for stage in stages:
            _remove_file(stage)
        for stage in stages:
            _fsync_copy(bundle.library, stage)

        for destination in destinations:
            fd, name = tempfile.mkstemp(
                prefix=f".{destination.name}.backup.", dir=destination.parent
            )
            os.close(fd)
            backup = Path(name)
            backup_candidates.append(backup)
            _remove_file(backup)
            _fsync_copy(destination, backup)
            backup_paths.append(backup)
        _write_overlay_journal(
            journal_path,
            {
                "schema_version": 1,
                "backup_names": [
                    {"destination": destination.name, "backup": backup.name}
                    for destination, backup in zip(destinations, backup_paths)
                ],
            },
        )
        for stage, destination in zip(stages, destinations):
            os.replace(stage, destination)
        committed = True
    except Exception:
        if backup_paths:
            for destination, backup in zip(destinations, backup_paths):
                if backup.exists():
                    try:
                        os.replace(backup, destination)
                    except OSError:
                        rollback_ok = False
        raise
    finally:
        for stage in stages:
            _remove_file(stage)
        if committed or rollback_ok:
            _remove_file(journal_path)
            for backup in backup_paths:
                _remove_file(backup)
        for backup in backup_candidates:
            if backup not in backup_paths:
                _remove_file(backup)


def _assemble_install_in_place(
    install_root: Path,
    extracted: Mapping[str, Path],
    *,
    project_root: Path = ROOT,
) -> None:
    """Assemble only known project/runtime destinations under install_root."""

    if install_root.exists() and install_root.is_symlink():
        raise ValueError(f"install root must not be a symlink: {install_root}")
    install_root.mkdir(parents=True, exist_ok=True)
    runtime_root = install_root / "runtime"
    if runtime_root.exists() and runtime_root.is_symlink():
        raise ValueError(f"install directory must not be a symlink: {runtime_root}")
    runtime_root.mkdir(exist_ok=True)
    for directory in (
        runtime_root / "maafw",
        runtime_root / "maafw" / "bin",
    ):
        if directory.exists() and directory.is_symlink():
            raise ValueError(f"install directory must not be a symlink: {directory}")
    for artifact_id, source in extracted.items():
        if artifact_id == "maafw":
            _validate_bundle_base(
                project_root / "vendor" / "maafw" / "v5.12.2" / "macos-arm64",
                source / "bin" / MACOS_CONTROL_UNIT_LIBRARY,
            )
    for artifact_id, source in extracted.items():
        if artifact_id == "maafw":
            bin_root = source / "bin"
            cli = bin_root / "MaaPiCli"
            if not cli.is_file():
                raise RuntimeError("MaaFramework archive does not contain MaaPiCli")
            # MaaPiCli uses @rpath for the framework and control-unit dylibs;
            # keep the official bin layout beside the CLI in the assembled
            # install so dyld can resolve those dependencies.
            for runtime_file in bin_root.iterdir():
                if runtime_file.is_file():
                    shutil.copy2(runtime_file, install_root / runtime_file.name)
            legacy_plugin_dir = install_root / "plugins" / "osx-arm64"
            if legacy_plugin_dir.is_dir():
                shutil.rmtree(legacy_plugin_dir)
            cli = install_root / "MaaPiCli"
            (install_root / "MaaPiCli").chmod(0o755)
            target = runtime_root / "maafw"
            _atomic_copytree(source, target)
            (target / "VERSION").write_text(f"{MAAFW_VERSION}\n", encoding="utf-8")
            overlay_patched_macos_control_unit(
                install_root,
                project_root / "vendor" / "maafw" / "v5.12.2" / "macos-arm64",
            )
        elif artifact_id == "mfa":
            app = _find_named(source, "MFAAvalonia.app", directory=True)
            if app is not None:
                _atomic_copytree(app, install_root / "MFAAvalonia.app")
            else:
                executable = source / "MFAAvalonia"
                if not executable.is_file():
                    raise RuntimeError(
                        "MFAAvalonia archive does not contain MFAAvalonia.app or MFAAvalonia"
                    )
                # The official macOS tarball is a self-contained .NET host
                # directory with a Mach-O executable at its root, not an
                # Apple application bundle. Copy the complete host directory
                # so its runtimeconfig, libs, plugins, and native dylibs stay
                # beside the executable.
                shutil.copytree(source, install_root, dirs_exist_ok=True)
                (install_root / "MFAAvalonia").chmod(0o755)
                nested_plugin_dir = install_root / "plugins" / "osx-arm64"
                if nested_plugin_dir.is_dir():
                    shutil.rmtree(nested_plugin_dir)
            target = runtime_root / "mfa"
            _atomic_copytree(source, target)
            (target / "VERSION").write_text("2.13.0-beta.5\n", encoding="utf-8")

    interface = project_root / "assets/interface.json"
    if interface.exists():
        shutil.copy2(interface, install_root / "interface.json")
    resource = project_root / "assets/resource"
    if resource.is_dir():
        shutil.copytree(resource, install_root / "resource", dirs_exist_ok=True)
    agent = project_root / "agent"
    if agent.is_dir():
        shutil.copytree(agent, install_root / "agent", dirs_exist_ok=True)


def assemble_install(
    install_root: Path,
    extracted: Mapping[str, Path],
    *,
    project_root: Path = ROOT,
) -> None:
    """Assemble into a sibling staging tree and swap it into place on success."""

    install_root = Path(install_root)
    if install_root.exists() and install_root.is_symlink():
        raise ValueError(f"install root must not be a symlink: {install_root}")
    parent = install_root.parent
    parent.mkdir(parents=True, exist_ok=True)
    for ancestor in Path(os.path.abspath(install_root)).parents:
        if stat.S_ISLNK(ancestor.lstat().st_mode):
            raise ValueError(f"install root ancestor must not be a symlink: {ancestor}")

    staging = Path(tempfile.mkdtemp(prefix=f".{install_root.name}.staging-", dir=parent))
    staging.rmdir()
    backup: Path | None = None
    try:
        if install_root.exists():
            shutil.copytree(install_root, staging, symlinks=True, dirs_exist_ok=True)
        _assemble_install_in_place(staging, extracted, project_root=project_root)
        if install_root.exists():
            backup = Path(tempfile.mkdtemp(prefix=f".{install_root.name}.backup-", dir=parent))
            backup.rmdir()
            install_root.replace(backup)
        staging.replace(install_root)
    except Exception:
        if backup is not None and backup.exists() and not install_root.exists():
            backup.replace(install_root)
        raise
    else:
        if backup is not None and backup.exists():
            shutil.rmtree(backup)
        backup = None
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def setup(root: Path) -> Path:
    assert_supported_platform()
    if not DEFAULT_CLICLICK.is_file() or not os.access(DEFAULT_CLICLICK, os.X_OK):
        raise RuntimeError(f"missing executable {DEFAULT_CLICLICK}")
    manifest = load_manifest(root / "runtime-manifest.json")
    install_root = root / "install"
    downloads = root / "downloads"
    install_root.mkdir(exist_ok=True)
    downloads.mkdir(exist_ok=True)
    artifacts = {artifact.id: artifact for artifact in manifest}
    archives = {item_id: download_artifact(item, downloads) for item_id, item in artifacts.items()}
    python = ensure_venv(install_root)
    install_requirements(python, root / "requirements.lock")
    with tempfile.TemporaryDirectory(prefix=".mja-runtime-", dir=install_root) as staging:
        extracted = {
            item_id: extract_archive(archive, Path(staging) / item_id)
            for item_id, archive in archives.items()
        }
        assemble_install(install_root, extracted, project_root=root)
    from tools.verify_install import verify_install

    errors = verify_install(
        install_root,
        bundle_root=root / "vendor" / "maafw" / "v5.12.2" / "macos-arm64",
    )
    if errors:
        raise RuntimeError("installation verification failed: " + "; ".join(errors))
    return install_root


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download and assemble the MJA runtime")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        setup(args.root.resolve())
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 1
    print("MJA setup complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
