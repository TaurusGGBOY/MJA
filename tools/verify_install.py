from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Callable, Iterable

from tools.native_bundle import load_patched_bundle

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CLICLICK = Path("/opt/homebrew/bin/cliclick")
REQUIRED_VERSIONS = {"maafw": "5.12.2", "mfa": "2.13.0-beta.5"}
FORBIDDEN_ACTIONS = {"Click", "Swipe", "Key", "Input", "StartApp"}
CONTROL_UNIT_NAME = "libMaaMacOSControlUnit.dylib"
DEFAULT_CONTROL_UNIT_BUNDLE = ROOT / "vendor" / "maafw" / "v5.12.2" / "macos-arm64"
FILE_TOOL = "/usr/bin/file"
LIPO_TOOL = "/usr/bin/lipo"
CODESIGN_TOOL = "/usr/bin/codesign"
OTOOL_TOOL = "/usr/bin/otool"


def _walk_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _walk_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_strings(item)


def _referenced_paths(payload: Any) -> Iterable[str]:
    for value in _walk_strings(payload):
        if value.startswith(("resource/", "resource\\")) or value.endswith(
            (".png", ".json")
        ):
            yield value.replace("\\", "/")


def _pipeline_errors(resource_root: Path) -> list[str]:
    errors: list[str] = []
    for path in resource_root.rglob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"invalid {path.relative_to(resource_root.parent)}: {exc}")
            continue
        for key, value in _walk_mapping_items(payload):
            if key in {"action", "action_type", "input"} and value in FORBIDDEN_ACTIONS:
                errors.append(f"forbidden input action {value} in {path.name}")
    return errors


def _walk_mapping_items(value: Any) -> Iterable[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield key, item
            yield from _walk_mapping_items(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_mapping_items(item)


def _check_runtime_versions(install_root: Path, errors: list[str]) -> None:
    manifest_path = install_root.parent / "runtime-manifest.json"
    if not manifest_path.is_file():
        return
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        expected = {item["id"]: item["version"] for item in manifest["artifacts"]}
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        errors.append(f"invalid runtime-manifest.json: {exc}")
        return
    for artifact_id, fallback_version in REQUIRED_VERSIONS.items():
        version = expected.get(artifact_id, fallback_version)
        marker = install_root / "runtime" / artifact_id / "VERSION"
        if not marker.is_file():
            errors.append(f"missing runtime/{artifact_id}/VERSION")
        elif marker.read_text(encoding="utf-8").strip() != version:
            errors.append(f"runtime/{artifact_id}/VERSION does not match manifest")


def _sha256_and_size(path: Path) -> tuple[str, int] | None:
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
                size += len(chunk)
    except OSError:
        return None
    return digest.hexdigest(), size


def _command_result(
    runner: Callable[..., Any],
    argv: list[str],
) -> Any | None:
    try:
        return runner(argv, check=False, capture_output=True, text=True)
    except OSError:
        return None


def _command_output(result: Any) -> str:
    return "\n".join(
        value
        for value in (getattr(result, "stdout", ""), getattr(result, "stderr", ""))
        if isinstance(value, str)
    )


def verify_patched_control_unit(
    install_root: Path,
    *,
    bundle_root: Path,
    runner: Callable[..., Any] = subprocess.run,
) -> list[str]:
    """Verify the attested patched control-unit dylib in both install locations."""

    install_root = Path(install_root)
    errors: list[str] = []
    try:
        bundle = load_patched_bundle(Path(bundle_root), require_library=True)
    except (OSError, ValueError) as exc:
        return [f"invalid patched control-unit bundle: {exc}"]

    expected_digest = bundle.manifest["patched_library_sha256"]
    expected_size = bundle.manifest["patched_library_size"]
    installed = {
        "root": install_root / CONTROL_UNIT_NAME,
        "runtime": install_root / "runtime" / "maafw" / "bin" / CONTROL_UNIT_NAME,
        "native": install_root / "runtimes" / "osx-arm64" / "native" / CONTROL_UNIT_NAME,
    }
    for candidate in (install_root / ".venv" / "lib").glob(
        f"python*/site-packages/maa/bin/{CONTROL_UNIT_NAME}"
    ):
        installed["python"] = candidate
    present: list[tuple[str, Path]] = []
    for label, path in installed.items():
        if not path.is_file():
            errors.append(f"missing {label} control-unit dylib: {path}")
            continue
        present.append((label, path))
        actual = _sha256_and_size(path)
        if actual is None:
            errors.append(f"unable to read {label} control-unit dylib: {path}")
            continue
        digest, size = actual
        if size != expected_size:
            errors.append(
                f"{label} control-unit size mismatch: expected {expected_size}, got {size}"
            )
        if digest != expected_digest:
            errors.append(
                f"{label} control-unit SHA-256 mismatch: "
                f"expected {expected_digest}, got {digest}"
            )

    for label, path in present:
        display = f"{label} control-unit"
        file_result = _command_result(runner, [FILE_TOOL, str(path)])
        if file_result is None or getattr(file_result, "returncode", 1) != 0:
            errors.append(f"{display} file inspection failed")
        elif "Mach-O" not in _command_output(file_result):
            errors.append(f"{display} is not a Mach-O binary")

        lipo_result = _command_result(runner, [LIPO_TOOL, "-archs", str(path)])
        if lipo_result is None or getattr(lipo_result, "returncode", 1) != 0:
            errors.append(f"{display} lipo inspection failed")
        elif "arm64" not in _command_output(lipo_result).split():
            errors.append(f"{display} is missing the arm64 architecture")

        signature_result = _command_result(
            runner,
            [CODESIGN_TOOL, "--verify", "--strict", str(path)],
        )
        if signature_result is None or getattr(signature_result, "returncode", 1) != 0:
            errors.append(f"{display} signature verification failed")

        linkage_result = _command_result(runner, [OTOOL_TOOL, "-L", str(path)])
        if linkage_result is None or getattr(linkage_result, "returncode", 1) != 0:
            errors.append(f"{display} linkage inspection failed")
        else:
            linkage = _command_output(linkage_result)
            for framework in ("ApplicationServices", "ScreenCaptureKit", "CoreGraphics"):
                if framework not in linkage:
                    errors.append(f"{display} is missing {framework} linkage")

    return errors


def verify_install(
    install_root: Path,
    *,
    runner: Callable[..., Any] = subprocess.run,
    cliclick_path: Path = DEFAULT_CLICLICK,
    run_runtime_checks: bool = True,
    bundle_root: Path | None = None,
) -> list[str]:
    install_root = Path(install_root)
    errors: list[str] = []
    required = {
        "interface.json": install_root / "interface.json",
        ".venv/bin/python3": install_root / ".venv/bin/python3",
        "MaaPiCli": install_root / "MaaPiCli",
        "resource/": install_root / "resource",
        "agent/": install_root / "agent",
    }
    for label, path in required.items():
        if not path.exists():
            errors.append(f"missing {label}")
    if required["MaaPiCli"].exists() and not os.access(required["MaaPiCli"], os.X_OK):
        errors.append("MaaPiCli is not executable")
    app_bundle = install_root / "MFAAvalonia.app"
    app_executable = install_root / "MFAAvalonia"
    if not app_bundle.exists() and not app_executable.exists():
        errors.append("missing MFAAvalonia.app or MFAAvalonia")
    elif app_executable.exists() and not os.access(app_executable, os.X_OK):
        errors.append("MFAAvalonia is not executable")

    _check_runtime_versions(install_root, errors)
    interface = install_root / "interface.json"
    if interface.is_file():
        try:
            payload = json.loads(interface.read_text(encoding="utf-8"))
            for reference in _referenced_paths(payload):
                candidate = install_root / reference
                if not candidate.exists():
                    errors.append(f"missing {reference}")
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"invalid interface.json: {exc}")

    resource = install_root / "resource"
    if resource.is_dir():
        errors.extend(_pipeline_errors(resource))

    if run_runtime_checks and not errors:
        python = install_root / ".venv/bin/python3"
        result = runner(
            [str(python), "-c", "import maa, Quartz, AppKit"],
            check=False,
            capture_output=True,
            text=True,
        )
        if getattr(result, "returncode", 1) != 0:
            errors.append(".venv cannot import maa, Quartz, or AppKit")
        if not cliclick_path.is_file() or not os.access(cliclick_path, os.X_OK):
            errors.append(f"missing executable {cliclick_path}")
        else:
            result = runner([str(cliclick_path), "-V"], check=False, capture_output=True, text=True)
            if getattr(result, "returncode", 1) != 0:
                errors.append("cliclick -V failed")
        errors.extend(
            verify_patched_control_unit(
                install_root,
                bundle_root=bundle_root or DEFAULT_CONTROL_UNIT_BUNDLE,
                runner=runner,
            )
        )
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify an assembled MJA install")
    parser.add_argument("install_root", nargs="?", type=Path, default=ROOT / "install")
    args = parser.parse_args(argv)
    errors = verify_install(args.install_root.resolve())
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("MJA install verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
