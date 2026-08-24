"""Select declared MFW tasks using only declarations and the operation date."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

CONTROL_TASKS = frozenset({"GAME_START", "GAME_STOP"})
WEEKLY_FREE_GIFT_TASK = "WEEKLY_FREE_GIFT_DAILY"
OPERATION_TIMEZONE_NAME = "Asia/Shanghai"
OPERATION_TIMEZONE = ZoneInfo(OPERATION_TIMEZONE_NAME)


@dataclass(frozen=True, slots=True)
class TaskDeclaration:
    name: str
    entry: str
    weekdays: frozenset[int] | None
    source: str


def _read_object(path: Path, *, kind: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"malformed {kind}: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"malformed {kind}: expected object: {path}")
    return payload


def _string(value: object, *, field: str, path: Path) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"malformed task declaration: {field} in {path}")
    return value.strip()


def _weekday(value: object) -> int | None:
    if isinstance(value, int) and 0 <= value <= 6:
        return value
    if not isinstance(value, str):
        return None
    return {
        "mon": 0,
        "monday": 0,
        "tue": 1,
        "tuesday": 1,
        "wed": 2,
        "wednesday": 2,
        "thu": 3,
        "thursday": 3,
        "fri": 4,
        "friday": 4,
        "sat": 5,
        "saturday": 5,
        "sun": 6,
        "sunday": 6,
    }.get(value.strip().casefold())


def _extract_weekdays(task: Mapping[str, Any], task_name: str) -> frozenset[int] | None:
    candidates: list[object] = []
    for key in ("eligible_weekdays", "weekdays", "days", "schedule_days"):
        if key in task:
            candidates.append(task[key])
    schedule = task.get("schedule")
    if isinstance(schedule, Mapping):
        for key in ("eligible_weekdays", "weekdays", "days"):
            if key in schedule:
                candidates.append(schedule[key])
    if not candidates:
        return None
    raw_days: list[object] = []
    for candidate in candidates:
        if isinstance(candidate, (list, tuple, set, frozenset)):
            raw_days.extend(candidate)
        else:
            raw_days.append(candidate)
    days = {_weekday(value) for value in raw_days}
    if None in days or not days:
        raise ValueError(f"malformed task declaration: invalid weekdays for {task_name}")
    return frozenset(day for day in days if day is not None)


def _interface_path(candidate: Path) -> Path:
    for base in (candidate, candidate / "assets"):
        for path in (base / "interface.json", base / "interface.mfw.json"):
            if not path.is_file():
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                continue
            if isinstance(payload, Mapping) and ("import" in payload or "task" in payload):
                return path
    raise ValueError(f"candidate has no interface declaration: {candidate}")


def _retired_task_names(
    interface: Mapping[str, Any], declarations_by_name: Mapping[str, TaskDeclaration]
) -> frozenset[str]:
    raw_retired = interface.get("retired_tasks", [])
    if not isinstance(raw_retired, list) or not all(
        isinstance(item, str) and item.strip() for item in raw_retired
    ):
        raise ValueError("malformed interface declaration: retired_tasks must be a list")
    retired = {item.strip().casefold() for item in raw_retired}
    unknown = retired - set(declarations_by_name)
    if unknown:
        raise ValueError(f"retired task is not declared: {sorted(unknown)[0]}")
    return frozenset(retired)


def _task_items(payload: Mapping[str, Any], path: Path) -> Iterable[Mapping[str, Any]]:
    tasks = payload.get("task")
    if not isinstance(tasks, list):
        raise ValueError(f"malformed task declaration: task must be a list: {path}")
    for task in tasks:
        if not isinstance(task, Mapping):
            raise ValueError(f"malformed task declaration: task item: {path}")
        yield task


def declarations(candidate: Path) -> tuple[TaskDeclaration, ...]:
    candidate = Path(candidate).resolve()
    interface_path = _interface_path(candidate)
    interface = _read_object(interface_path, kind="interface declaration")
    imports = interface.get("import")
    if imports is not None:
        if not isinstance(imports, list) or not all(isinstance(item, str) for item in imports):
            raise ValueError("malformed interface declaration: import must be a list of paths")
        paths: Iterable[Path] = (interface_path.parent / relative for relative in imports)
    else:
        paths = (interface_path,)
    records: list[TaskDeclaration] = []
    for path in paths:
        payload = _read_object(path, kind="task declaration")
        for task in _task_items(payload, path):
            name = _string(task.get("name"), field="name", path=path)
            entry = _string(task.get("entry"), field="entry", path=path)
            records.append(TaskDeclaration(name, entry, _extract_weekdays(task, name), str(path)))
    names = [record.name.casefold() for record in records]
    if len(names) != len(set(names)):
        raise ValueError("malformed interface declaration: duplicate task name")
    if not records:
        raise ValueError("malformed interface declaration: no tasks")
    return tuple(records)


def _parse_date(value: date | str | None) -> date:
    if value is None:
        return date.today()
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"invalid operation date: {value}") from exc
    raise ValueError(f"invalid operation date: {value!r}")


def _eligible(task: TaskDeclaration, operation_date: date) -> bool:
    if task.name.upper() == WEEKLY_FREE_GIFT_TASK:
        return True
    return task.weekdays is None or operation_date.weekday() in task.weekdays


def select_tasks(
    candidate: Path,
    *,
    operation_date: date | str | None = None,
    explicit_tasks: Sequence[str] = (),
) -> dict[str, Any]:
    """Return the ordered declaration/date selection without runtime evidence."""

    candidate = Path(candidate).resolve()
    operation_day = _parse_date(operation_date)
    declared = declarations(candidate)
    by_name = {task.name.casefold(): task for task in declared}
    interface_path = _interface_path(candidate)
    interface = _read_object(interface_path, kind="interface declaration")
    retired_keys = _retired_task_names(interface, by_name)
    normalized_explicit = tuple(str(task).strip() for task in explicit_tasks if str(task).strip())
    explicit_keys = tuple(task.casefold() for task in normalized_explicit)
    if len(explicit_keys) != len(set(explicit_keys)):
        raise ValueError("explicit tasks must be unique")
    unknown = [task for task, key in zip(normalized_explicit, explicit_keys) if key not in by_name]
    if unknown:
        raise ValueError(f"unknown task: {unknown[0]}")
    controls = [
        by_name[key].name
        for key in explicit_keys
        if by_name[key].name.upper() in CONTROL_TASKS
    ]
    if controls:
        raise ValueError(f"control task is not selectable: {controls[0]}")
    is_explicit = bool(normalized_explicit)
    requested = set(explicit_keys)
    selected: list[str] = []
    eligible: list[str] = []
    omitted: list[str] = []
    blockers: list[dict[str, str]] = []
    evidence: dict[str, Any] = {
        "interface_path": str(interface_path),
        "operation_date": operation_day.isoformat(),
        "operation_timezone": OPERATION_TIMEZONE_NAME,
    }
    for task in declared:
        if task.name.upper() in CONTROL_TASKS:
            continue
        key = task.name.casefold()
        if key in retired_keys:
            reason = "retired"
            eligible_today = False
        elif is_explicit and key not in requested:
            reason = "not_requested"
            eligible_today = False
        elif not _eligible(task, operation_day):
            reason = "not_eligible_today"
            eligible_today = False
        else:
            reason = "eligible"
            eligible_today = True
            eligible.append(task.name)
            selected.append(task.name)
        evidence[task.name] = {
            "eligible": eligible_today,
            "reason": reason,
            "entry": task.entry,
        }
        if is_explicit and key in requested and not eligible_today:
            blockers.append({"task_id": task.name, "reason": reason})
        elif not eligible_today and not (is_explicit and key in requested):
            omitted.append(task.name)
    return {
        "schema_version": 3,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "candidate": str(candidate),
        "operation_date": operation_day.isoformat(),
        "operation_timezone": OPERATION_TIMEZONE_NAME,
        "scope_mode": "explicit" if is_explicit else "full",
        "requested_tasks": list(normalized_explicit),
        "retired_tasks": [task.name for task in declared if task.name.casefold() in retired_keys],
        "omitted_tasks": omitted,
        "scope_blockers": blockers,
        "eligible_tasks": eligible,
        "selected_tasks": selected,
        "evidence": evidence,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--date", dest="operation_date")
    parser.add_argument("--task", dest="explicit_tasks", action="append", default=[])
    parser.add_argument("--output", type=Path, help="atomically write the selection JSON")
    return parser


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        selection = select_tasks(
            args.candidate,
            operation_date=args.operation_date,
            explicit_tasks=tuple(args.explicit_tasks),
        )
    except (OSError, TypeError, ValueError) as exc:
        print(f"mfw task selection failed: {exc}", file=sys.stderr)
        return 2
    if args.output is not None:
        _write_json_atomic(args.output, selection)
    print(json.dumps(selection, ensure_ascii=False, indent=2, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["CONTROL_TASKS", "TaskDeclaration", "declarations", "main", "select_tasks"]
