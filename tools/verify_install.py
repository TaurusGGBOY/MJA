from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Callable, Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CLICLICK = Path("/opt/homebrew/bin/cliclick")
REQUIRED_VERSIONS = {"maafw": "5.12.2", "mfa": "2.13.0-beta.5"}
FORBIDDEN_ACTIONS = {"Click", "Swipe", "Key", "Input", "StartApp"}


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


def verify_install(
    install_root: Path,
    *,
    runner: Callable[..., Any] = subprocess.run,
    cliclick_path: Path = DEFAULT_CLICLICK,
    run_runtime_checks: bool = True,
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
