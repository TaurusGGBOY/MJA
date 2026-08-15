"""Resolve and directly run an existing MFW saved profile."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Sequence


def _registered_config_ids(install_root: Path) -> list[str]:
    path = Path(install_root) / "config" / "multi_config.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid MFW config registry: {path}") from exc
    config_list = payload.get("config_list") if isinstance(payload, dict) else None
    if not isinstance(config_list, list) or not all(
        isinstance(config_id, str) for config_id in config_list
    ):
        raise ValueError(
            f"MFW config registry must provide config_list in {path}"
        )
    return config_list


def resolve_config_id(install_root: Path, profile_name: str) -> str:
    if not isinstance(profile_name, str) or not profile_name.strip():
        raise ValueError("profile_name must be non-empty")
    config_dir = Path(install_root) / "config" / "configs"
    matches: list[str] = []
    for path in sorted(config_dir.glob("c_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid saved profile: {path}") from exc
        if isinstance(payload, dict) and payload.get("name") == profile_name:
            matches.append(path.stem)
    if len(matches) != 1:
        raise ValueError(
            f"expected exactly one saved profile named {profile_name}, got {len(matches)}"
        )
    config_id = matches[0]
    registered = _registered_config_ids(install_root)
    if config_id not in registered:
        raise ValueError(
            f"config ID {config_id!r} is not registered in "
            f"multi_config.json.config_list; registered config IDs: {registered!r}"
        )
    return config_id


def _config_path(install_root: Path, config_id: str) -> Path:
    if not isinstance(config_id, str) or not config_id.strip():
        raise ValueError("config_id must be non-empty")
    if Path(config_id).name != config_id:
        raise ValueError("config_id must be a single identifier")
    path = Path(install_root) / "config" / "configs" / f"{config_id}.json"
    if not path.is_file():
        raise ValueError(f"saved profile does not exist: {path}")
    return path


def profile_task_order(install_root: Path, config_id: str) -> tuple[str, ...]:
    """Return the checked MFW task names in the saved profile's order."""

    path = _config_path(Path(install_root), config_id)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid saved profile: {path}") from exc
    tasks = payload.get("tasks") if isinstance(payload, dict) else None
    if not isinstance(tasks, list):
        raise ValueError(f"saved profile has no tasks list: {path}")
    infrastructure = {"PreTask", "Controller", "Resource", "Post-Action"}
    result: list[str] = []
    for item in tasks:
        if not isinstance(item, dict):
            raise ValueError(f"invalid task item in saved profile: {path}")
        if item.get("is_checked") is not True:
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"checked profile task has no name: {path}")
        if name not in infrastructure:
            result.append(name.strip())
    return tuple(result)


def verify_profile_tasks(
    install_root: Path,
    profile_name: str,
    expected_tasks: Sequence[str],
) -> tuple[str, ...]:
    """Resolve a profile and require its checked task order to be exact."""

    root = Path(install_root).resolve()
    config_id = resolve_config_id(root, profile_name)
    actual = profile_task_order(root, config_id)
    expected = tuple(item.strip() for item in expected_tasks if item.strip())
    if actual != expected:
        raise ValueError(
            f"profile task order mismatch for {profile_name!r}: "
            f"expected={expected!r}, actual={actual!r}"
        )
    return actual


def build_run_argv(install_root: Path, config_id: str) -> list[str]:
    if not isinstance(config_id, str) or not config_id.strip():
        raise ValueError("config_id must be non-empty")
    if Path(config_id).name != config_id:
        raise ValueError("config_id must be a single identifier")
    return [str(Path(install_root) / "MFW"), f"--config-id={config_id}", "--direct-run"]


def run_profile(install_root: Path, profile_name: str) -> int:
    # ``cwd`` is the candidate root, so the executable must be resolved before
    # changing directories.  A relative install path would otherwise become
    # ``<root>/<relative-root>/MFW`` and fail with FileNotFoundError.
    root = Path(install_root).resolve()
    config_id = resolve_config_id(root, profile_name)
    completed = subprocess.run(
        build_run_argv(root, config_id),
        cwd=root,
        check=False,
    )
    return completed.returncode


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    resolve = subparsers.add_parser("resolve", help="resolve a saved profile name")
    resolve.add_argument("--install", type=Path, required=True)
    resolve.add_argument("--profile-name", required=True)

    run = subparsers.add_parser("run", help="run a saved profile with MFW direct-run")
    run.add_argument("--install", type=Path, required=True)
    run.add_argument("--profile-name", required=True)
    run.add_argument("--expected-task", action="append", default=[])
    verify = subparsers.add_parser("verify", help="verify exact checked task order")
    verify.add_argument("--install", type=Path, required=True)
    verify.add_argument("--profile-name", required=True)
    verify.add_argument("--expected-task", action="append", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "resolve":
        print(resolve_config_id(args.install, args.profile_name))
        return 0
    if args.command == "verify":
        actual = verify_profile_tasks(args.install, args.profile_name, args.expected_task)
        print(json.dumps(list(actual), ensure_ascii=False))
        return 0
    if args.expected_task:
        verify_profile_tasks(args.install, args.profile_name, args.expected_task)
    return run_profile(args.install, args.profile_name)


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "build_run_argv",
    "main",
    "profile_task_order",
    "resolve_config_id",
    "run_profile",
    "verify_profile_tasks",
]
