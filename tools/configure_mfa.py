from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, TextIO

GAME_APP_NAME = "对决！剑之川"
STARTUP_WAIT_SECONDS = 60


def _timestamp() -> str:
    from datetime import datetime

    return datetime.now().astimezone().strftime("%Y%m%dT%H%M%S")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON in {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"MFA instance JSON must contain an object: {path}")
    return value


def _require_object(payload: Mapping[str, Any], key: str) -> dict[str, Any]:
    current = payload.get(key)
    if current is None:
        return {}
    if not isinstance(current, dict):
        raise ValueError(f"MFA instance field {key!r} must be an object")
    return dict(current)


def build_patch(install_root: Path) -> dict[str, Any]:
    """Return the complete, deterministic set of fields owned by MJA."""
    install_root = Path(install_root)
    return {
        "startup": {
            "program": "/usr/bin/open",
            "args": ["-a", GAME_APP_NAME],
            "wait_seconds": STARTUP_WAIT_SECONDS,
        },
        "controller": {
            "name": "macos",
            "auto_detect_window": True,
        },
        "project": str(install_root / "interface.json"),
        "pretask": {
            "program": str(install_root / ".venv" / "bin" / "python"),
            "args": ["-m", "agent.pretask"],
        },
    }


def _merge_patch(payload: dict[str, Any], patch: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    for key in ("startup", "controller", "pretask"):
        current = _require_object(result, key)
        current.update(patch[key])
        result[key] = current
    result["project"] = patch["project"]
    return result


def _backup_path(path: Path, timestamp: str) -> Path:
    candidate = path.with_name(f"{path.name}.{timestamp}.bak")
    index = 1
    while candidate.exists():
        candidate = path.with_name(f"{path.name}.{timestamp}-{index}.bak")
        index += 1
    return candidate


def _write_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def configure_instance(
    instance_path: str | Path,
    *,
    install_root: str | Path,
    now: Callable[[], str] = _timestamp,
    dry_run: bool = False,
    output: TextIO | None = None,
) -> Path | None:
    """Safely patch one explicitly supplied MFA instance JSON file.

    The source is parsed before any backup is made. A normal run creates a
    timestamped sibling backup, then atomically replaces the instance file.
    ``dry_run`` emits only the MJA-owned patch and leaves the source untouched.
    """
    path = Path(instance_path)
    if not path.is_file():
        raise FileNotFoundError(f"MFA instance JSON does not exist: {path}")

    original = _load_json(path)
    patch = build_patch(Path(install_root))
    if dry_run:
        stream = output or sys.stdout
        stream.write(json.dumps(patch, ensure_ascii=False, indent=2) + "\n")
        return None

    updated = _merge_patch(original, patch)
    backup = _backup_path(path, now())
    backup.write_bytes(path.read_bytes())
    _write_atomic(path, updated)
    return backup


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Patch one explicit MFA instance JSON")
    parser.add_argument("instance_path", type=Path)
    parser.add_argument("--install-root", type=Path, default=Path("install"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        configure_instance(
            args.instance_path,
            install_root=args.install_root,
            dry_run=args.dry_run,
        )
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI smoke tested by users
    raise SystemExit(main())


__all__ = ["build_patch", "configure_instance", "main"]

