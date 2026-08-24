"""Resolve and directly run an existing MFW saved profile."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import time
import subprocess
from pathlib import Path
from typing import Any, Sequence


_INFRASTRUCTURE_TASKS = frozenset(
    {"PreTask", "Controller", "Resource", "Post-Action"}
)
_CONTROL_TASKS = frozenset({"GAME_START", "GAME_STOP"})
_PAIR_PROFILE_PREFIX = "MJA auto GAME_START+"
_PAIR_CONFIG_PREFIX = "c_mja_pair_"
_SEQUENCE_PROFILE_PREFIX = "MJA auto GAME_START+SEQUENCE+"
_SEQUENCE_CONFIG_PREFIX = "c_mja_sequence_"


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


def _interface_path(install_root: Path) -> Path:
    root = Path(install_root)
    for path in (root / "interface.json", root / "interface.mfw.json"):
        if path.is_file():
            return path
    raise ValueError(f"candidate has no interface declaration: {root}")


def _declared_task_names(install_root: Path) -> tuple[str, ...]:
    """Read task names without requiring the full selection machinery.

    Candidate builders also use this helper with small fixture interfaces that
    do not contain an ``import`` list.  In that case the task declarations are
    discovered from the copied ``tasks`` tree.
    """

    root = Path(install_root)
    interface_path = _interface_path(root)
    interface = json.loads(interface_path.read_text(encoding="utf-8"))
    if not isinstance(interface, dict):
        raise ValueError(f"invalid interface declaration: {interface_path}")

    paths: list[Path] = []
    imports = interface.get("import")
    if isinstance(imports, list):
        paths.extend(interface_path.parent / item for item in imports if isinstance(item, str))
    elif isinstance(interface.get("task"), list):
        paths.append(interface_path)
    else:
        paths.extend(sorted((root / "tasks").rglob("*.json")))

    names: list[str] = []
    for path in paths:
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict) or not isinstance(payload.get("task"), list):
            continue
        for task in payload["task"]:
            if isinstance(task, dict) and isinstance(task.get("name"), str):
                name = task["name"].strip()
                if name and name not in names:
                    names.append(name)

    retired = {
        item.strip()
        for item in interface.get("retired_tasks", [])
        if isinstance(item, str) and item.strip()
    }
    return tuple(
        name
        for name in names
        if not name.startswith("GAME_")
        and name not in _CONTROL_TASKS
        and name not in retired
    )


def _config_tasks(payload: dict[str, Any]) -> list[dict[str, Any]]:
    tasks = payload.get("tasks")
    if not isinstance(tasks, list):
        raise ValueError("saved profile has no tasks list")
    if not all(isinstance(item, dict) for item in tasks):
        raise ValueError("saved profile contains an invalid task item")
    return tasks


def _checked_business_tasks(payload: dict[str, Any]) -> tuple[str, ...]:
    return tuple(
        str(item["name"]).strip()
        for item in _config_tasks(payload)
        if item.get("is_checked") is True
        and isinstance(item.get("name"), str)
        and item["name"] not in _INFRASTRUCTURE_TASKS
    )


def _config_id_slug(task_id: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", task_id.casefold()).strip("_")
    return f"{_PAIR_CONFIG_PREFIX}{slug}"


def _synthetic_task_item(
    name: str, interface: dict[str, Any]
) -> dict[str, Any]:
    """Create the minimal saved-task record when no historical one exists."""

    if name in _INFRASTRUCTURE_TASKS:
        if name == "Controller":
            controller_type = "android"
            controllers = interface.get("controller")
            if isinstance(controllers, list) and controllers:
                first = controllers[0]
                if isinstance(first, dict) and isinstance(first.get("name"), str):
                    controller_type = first["name"]
            option: dict[str, Any] = {"controller_type": controller_type}
        elif name == "Resource":
            resource_name = "mja_android"
            resources = interface.get("resource")
            if isinstance(resources, list) and resources:
                first = resources[0]
                if isinstance(first, dict) and isinstance(first.get("name"), str):
                    resource_name = first["name"]
            option = {"resource": resource_name, "setting_options": {}}
        else:
            option = {}
        return {
            "name": name,
            "item_id": name,
            "is_checked": True,
            "task_option": option,
        }
    if name == "GAME_START":
        return {
            "name": name,
            "item_id": "t_mja_game_start",
            "is_checked": False,
            "task_option": {"MJA_START_FAST_MODE": {"value": "No"}},
        }
    digest = hashlib.sha256(f"mja-task:{name}".encode("utf-8")).hexdigest()[:32]
    return {
        "name": name,
        "item_id": f"t_{digest}",
        "is_checked": False,
        "task_option": {},
    }


def _profile_template_data(
    config_payloads: dict[str, dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any] | None]:
    """Return reusable task records and the richest usable profile template."""

    task_items: dict[str, dict[str, Any]] = {}
    template: dict[str, Any] | None = None
    template_score = -1
    for payload in config_payloads.values():
        try:
            tasks = _config_tasks(payload)
        except ValueError:
            continue
        names: set[str] = set()
        for item in tasks:
            name = item.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            normalized = copy.deepcopy(item)
            normalized["name"] = name.strip()
            task_items.setdefault(normalized["name"], normalized)
            names.add(normalized["name"])
        if not _INFRASTRUCTURE_TASKS - names or {
            "PreTask",
            "Controller",
            "Resource",
        }.issubset(names):
            score = len(names) + len(_checked_business_tasks(payload))
            if score > template_score:
                template = copy.deepcopy(payload)
                template_score = score
    return task_items, template


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_name(path.name + ".part")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def ensure_pair_profiles(install_root: Path) -> dict[str, str]:
    """Ensure one registered ``GAME_START + task`` profile per active task.

    MFW saves profiles as mutable JSON rather than deriving them from
    ``interface.json`` at run time.  Older candidates therefore lost newly
    added tasks when they were copied from a historical base candidate.  This
    repair is deterministic and offline: it clones the richest saved profile
    that contains each task, unchecks every other business task, registers the
    generated config, and leaves existing exact pair profiles untouched.

    Returns a mapping from task name to profile name.  The helper never starts
    MFW, ADB, an emulator, or any controller.
    """

    root = Path(install_root).resolve()
    interface_path = _interface_path(root)
    interface = json.loads(interface_path.read_text(encoding="utf-8"))
    if not isinstance(interface, dict):
        raise ValueError(f"invalid interface declaration: {interface_path}")
    active_tasks = _declared_task_names(root)
    if not active_tasks:
        return {}

    config_dir = root / "config" / "configs"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_payloads: dict[str, dict[str, Any]] = {}
    for path in sorted(config_dir.glob("c_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            config_payloads[path.stem] = payload

    task_items, template = _profile_template_data(config_payloads)
    template_names: list[str] = []
    if template is not None:
        for item in _config_tasks(template):
            name = item.get("name")
            if isinstance(name, str) and name.strip() and name.strip() not in template_names:
                template_names.append(name.strip())
    ordered_names = ["PreTask", "Controller", "Resource"]
    if "Post-Action" in template_names:
        ordered_names.append("Post-Action")
    ordered_names.append("GAME_START")
    for name in (*template_names, *active_tasks):
        if name not in ordered_names:
            ordered_names.append(name)

    for name in ordered_names:
        task_items.setdefault(name, _synthetic_task_item(name, interface))

    registry_path = root / "config" / "multi_config.json"
    if registry_path.is_file():
        raw = json.loads(registry_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"invalid MFW config registry: {registry_path}")
        registry: dict[str, Any] = raw
    else:
        registry = {
            "curr_config_id": None,
            "config_list": [],
            "bundle": {"MJA": {"name": "MJA", "path": "./"}},
        }
    registered = registry.get("config_list", [])
    if not isinstance(registered, list) or not all(
        isinstance(item, str) and item.strip() for item in registered
    ):
        raise ValueError(f"MFW config registry must provide config_list: {registry_path}")
    registered = list(dict.fromkeys(registered))
    pair_profiles: dict[str, str] = {}

    for task_id in active_tasks:
        exact = [
            (config_id, payload)
            for config_id, payload in config_payloads.items()
            if _checked_business_tasks(payload) == ("GAME_START", task_id)
        ]
        if exact:
            config_id, payload = sorted(exact)[0]
            if config_id not in registered:
                registered.append(config_id)
            pair_profiles[task_id] = str(payload.get("name") or config_id)
            continue

        generated_id = _config_id_slug(task_id)
        generated_name = f"{_PAIR_PROFILE_PREFIX}{task_id}"
        payload = config_payloads.get(generated_id)
        if payload is None:
            payload = copy.deepcopy(template) if template is not None else {
                "name": generated_name,
                "item_id": generated_id,
                "tasks": [],
            }
        tasks: list[dict[str, Any]] = []
        for name in ordered_names:
            item = copy.deepcopy(task_items[name])
            item["name"] = name
            item["is_checked"] = name in _INFRASTRUCTURE_TASKS or name in {
                "GAME_START",
                task_id,
            }
            tasks.append(item)
        payload["name"] = generated_name
        payload["item_id"] = generated_id
        payload["tasks"] = tasks
        _write_json(config_dir / f"{generated_id}.json", payload)
        config_payloads[generated_id] = payload
        if generated_id not in registered:
            registered.append(generated_id)
        pair_profiles[task_id] = generated_name

    registry["config_list"] = registered
    current = registry.get("curr_config_id")
    if not isinstance(current, str) or not (
        current in registered and (config_dir / f"{current}.json").is_file()
    ):
        registry["curr_config_id"] = _config_id_slug(active_tasks[0])
    _write_json(registry_path, registry)
    return pair_profiles


def ensure_sequence_profile(
    install_root: Path,
    task_ids: Sequence[str],
    profile_name: str | None = None,
) -> str:
    """Create/register one ``GAME_START + task_ids`` saved profile.

    The profile is mutable MFW configuration, not project payload.  It is
    generated from the candidate's existing profile records so controller,
    resource, and task options remain identical to the candidate's validated
    runtime.  ``GAME_START`` is inserted exactly once before the requested
    business tasks; task order is preserved exactly as supplied.
    """

    root = Path(install_root).resolve()
    requested = tuple(item.strip() for item in task_ids if item and item.strip())
    if not requested:
        raise ValueError("at least one business task is required")
    if len(set(requested)) != len(requested):
        raise ValueError(f"duplicate business task in sequence: {requested!r}")
    active = _declared_task_names(root)
    missing = [item for item in requested if item not in active]
    if missing:
        raise ValueError(f"sequence contains unavailable task(s): {missing!r}")

    ensure_pair_profiles(root)
    config_dir = root / "config" / "configs"
    pair_path = config_dir / f"{_config_id_slug(requested[0])}.json"
    if not pair_path.is_file():
        raise ValueError(f"cannot find pair profile template: {pair_path}")
    template = json.loads(pair_path.read_text(encoding="utf-8"))
    if not isinstance(template, dict):
        raise ValueError(f"invalid pair profile template: {pair_path}")
    tasks = _config_tasks(template)
    task_by_name = {
        item["name"]: item
        for item in tasks
        if isinstance(item.get("name"), str) and item["name"].strip()
    }
    for name in ("PreTask", "Controller", "Resource", "GAME_START", *requested):
        task_by_name.setdefault(name, _synthetic_task_item(name, {}))
    selected = {"GAME_START", *requested}
    output_tasks: list[dict[str, Any]] = []
    ordered_names = ["PreTask", "Controller", "Resource", "GAME_START", *requested]
    for name in ordered_names:
        item = task_by_name[name]
        cloned = copy.deepcopy(item)
        cloned["is_checked"] = name in _INFRASTRUCTURE_TASKS or name in selected
        output_tasks.append(cloned)
    checked_business = tuple(
        item["name"]
        for item in output_tasks
        if item.get("is_checked") is True
        and isinstance(item.get("name"), str)
        and item["name"] not in _INFRASTRUCTURE_TASKS
    )
    if checked_business != ("GAME_START", *requested):
        raise ValueError(
            "candidate profile template cannot materialize exact sequence: "
            f"expected={("GAME_START", *requested)!r}, actual={checked_business!r}"
        )

    digest = hashlib.sha256(",".join(requested).encode("utf-8")).hexdigest()[:16]
    config_id = f"{_SEQUENCE_CONFIG_PREFIX}{digest}"
    name = profile_name or f"{_SEQUENCE_PROFILE_PREFIX}{'+'.join(requested)}"
    payload = copy.deepcopy(template)
    payload["name"] = name
    payload["item_id"] = config_id
    payload["tasks"] = output_tasks
    _write_json(config_dir / f"{config_id}.json", payload)

    registry_path = root / "config" / "multi_config.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    if not isinstance(registry, dict) or not isinstance(registry.get("config_list"), list):
        raise ValueError(f"invalid MFW config registry: {registry_path}")
    registry["config_list"] = list(dict.fromkeys([*registry["config_list"], config_id]))
    registry["curr_config_id"] = config_id
    _write_json(registry_path, registry)
    return name


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
    debug_root = root / "debug"
    gui_log = debug_root / "gui.log"
    maafw_log = debug_root / "maafw.log"
    offsets = {
        gui_log: gui_log.stat().st_size if gui_log.exists() else 0,
        maafw_log: maafw_log.stat().st_size if maafw_log.exists() else 0,
    }
    process = subprocess.Popen(build_run_argv(root, config_id), cwd=root)

    # MFW's Qt wrapper can remain alive after native Tasker/controller teardown.
    # The task lifecycle, rather than GUI-process exit, is the authoritative
    # batch boundary.  This observer has no timeout and never sends input or
    # schedules another task; it only waits for this process's fresh teardown
    # records or the child process to exit normally.
    markers = {
        "task_flow_stop": False,
        "tasker_destroy": False,
        "controller_destroy": False,
    }
    controller_disconnected = False
    while True:
        for path, offset in offsets.items():
            if not path.exists():
                continue
            with path.open("rb") as stream:
                stream.seek(offset)
                text = stream.read().decode("utf-8", errors="replace")
            offsets[path] = path.stat().st_size
            if path == gui_log and "监控循环中检测到控制器断开" in text:
                controller_disconnected = True
            if path == gui_log and "TASK_FLOW_STOP" in text:
                markers["task_flow_stop"] = True
            if path == maafw_log:
                if "MaaTaskerDestroy" in text:
                    markers["tasker_destroy"] = True
                if "MaaControllerDestroy" in text:
                    markers["controller_destroy"] = True
        returncode = process.poll()
        if returncode is not None:
            return returncode
        if controller_disconnected:
            # A controller disconnect is a shared-runtime hard blocker, not a
            # business-task failure. Stop this exact native child promptly so
            # the batch cannot wait for the pipeline's later failure node.
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            return 2
        if all(markers.values()):
            return 0
        time.sleep(0.2)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    ensure = subparsers.add_parser(
        "ensure-pair-profiles",
        help="materialize and register one GAME_START+task profile per active task",
    )
    ensure.add_argument("--install", type=Path, required=True)

    sequence = subparsers.add_parser(
        "ensure-sequence-profile",
        help="materialize and register one GAME_START+task sequence profile",
    )
    sequence.add_argument("--install", type=Path, required=True)
    sequence.add_argument("--task", action="append", required=True)
    sequence.add_argument("--profile-name")

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
    if args.command == "ensure-pair-profiles":
        print(json.dumps(ensure_pair_profiles(args.install), ensure_ascii=False, indent=2))
        return 0
    if args.command == "ensure-sequence-profile":
        print(
            ensure_sequence_profile(
                args.install, args.task, profile_name=args.profile_name
            )
        )
        return 0
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
    "ensure_pair_profiles",
    "ensure_sequence_profile",
    "main",
    "profile_task_order",
    "resolve_config_id",
    "run_profile",
    "verify_profile_tasks",
]
