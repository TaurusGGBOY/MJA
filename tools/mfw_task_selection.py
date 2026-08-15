"""Select the current repair scope from declarations and task evidence.

This module intentionally has no runtime-control dependencies.  A call reads
the candidate declarations and one immutable snapshot of result files, then
returns a JSON-serializable selection record.  It never changes the candidate
or starts an external command.
"""

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
OPERATION_TIMEZONE_NAME = "Asia/Shanghai"
OPERATION_TIMEZONE = ZoneInfo(OPERATION_TIMEZONE_NAME)
FAILURE_STATUSES = frozenset({"failed", "blocked_safety"})
NON_SUCCESS_STATUSES = frozenset(
    {
        "failed",
        "blocked_safety",
        "already_complete",
        "not_eligible",
        "completed",
        "running",
    }
)

# These are the normal business markers currently used by the native task
# pipelines.  An unknown task may still use a task-qualified marker, which is
# useful for fixture candidates and future task declarations.
SUCCESS_POSTCONDITIONS: dict[str, frozenset[str]] = {
    "MAIL_REWARD_DAILY": frozenset({"mail.reward_claimed"}),
    "SHOP_FREE_GIFT_DAILY": frozenset({"shop.daily_free_gift_claimed"}),
    "BUY_TEA_DAILY": frozenset(
        {"tea.purchase_result_seen", "tea.sold_out", "tea.no_remaining_stock"}
    ),
    "FREE_APPRAISAL_DAILY": frozenset({"appraisal.reward_popup_seen"}),
    "TRIAL_SWORD_DAILY": frozenset({"trial.reward_popup_seen"}),
    "HERO_DISPATCH_DAILY": frozenset(
        {"hero.all_completed", "hero.all_dispatched_waiting", "hero.no_dispatch_tasks"}
    ),
    "COLLECTION_DEPLOYMENT_DAILY": frozenset({"collection.harvest_clicked"}),
    "WEEKLY_FREE_GIFT_MONDAY": frozenset({"weekly_gift.reward_popup_seen"}),
    "SHADOW_RUINS_DAILY": frozenset({"shadow.final_reward_claimed_and_home"}),
    "SPEND_CONDENSATE_DAILY": frozenset({"condensate.both_regions_sold_out"}),
    "MARTIAL_STUDY_BREAKTHROUGH_DAILY": frozenset(
        {
            "martial.no_successful_breakthrough_to_claim",
            "martial.claim_flow_completed",
        }
    ),
    "EAT_STAMINA_FOOD_DAILY": frozenset(
        {
            "food.stamina_full",
            "food.used_five_times",
            "food.buff_after_verified_use",
            "food.longjing_shrimp_unavailable",
            "food.overfull",
        }
    ),
    "EQUIPMENT_DECOMPOSE_DAILY": frozenset({"equipment.decomposition_confirmed"}),
    "DUNGEON_SWEEP_DAILY": frozenset({"dungeon.reward_popup_seen"}),
    "JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY": frozenset(
        {
            "jianlin.challenge_condensate.required",
            "jianlin.stamina_below_20_or_second_offer",
        }
    ),
    "RING_CHALLENGE_DAILY": frozenset(
        {"ring.attempts_exhausted", "ring.manual_attempts_complete", "ring.challenge_done"}
    ),
    "BREAK_ARRAY_MARTIAL_DAILY": frozenset(
        {"break_array.three_challenges", "break_array.daily_exhausted"}
    ),
    "GUILD_ACTIVITY_CHALLENGE_DAILY": frozenset(
        {
            "guild.challenge_result_known",
            "guild.home_restored",
        }
    ),
    "GUILD_AFFAIRS_DAILY": frozenset(
        {"guild.affairs.daily.all_rows_started_or_no_action"}
    ),
    "GUILD_DONATION_DAILY": frozenset({"guild.donation.remaining_9_of_10"}),
    "DAILY_TASK_REWARD_CLAIM_DAILY": frozenset({"daily_reward.no_claimable"}),
    "BATTLE_PASS_REWARD_DAILY": frozenset({"battle_pass.no_task_or_basic_claimable"}),
}

GENERIC_POSTCONDITIONS = frozenset(
    {
        "completed",
        "home",
        "startup.game_ready",
        "success",
        "task.terminal",
        "terminal",
    }
)
INVALID_POSTCONDITION_MARKERS = (
    "ambiguous",
    "error",
    "failed",
    "failure",
    "missing",
    "unknown",
    "unverified",
    "unsafe",
)
NATIVE_SUCCESS_MARKERS = frozenset(
    {
        "completed",
        "mja_common_stop",
        "normal",
        "success",
        "succeeded",
        "tasker.task.succeeded",
    }
)


@dataclass(frozen=True, slots=True)
class TaskDeclaration:
    name: str
    entry: str
    weekdays: frozenset[int] | None
    source: str


@dataclass(frozen=True, slots=True)
class ResultRecord:
    path: Path
    payload: dict[str, Any]
    sort_key: tuple[datetime, int]


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
    normalized = value.strip().casefold()
    names = {
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
    }
    return names.get(normalized)


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
    if not candidates and task_name.casefold().endswith("_monday"):
        return frozenset({0})
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
        candidates = [
            base / "interface.json",
            base / "interface.mfw.json",
        ]
        for path in candidates:
            if not path.is_file():
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                continue
            if isinstance(payload, Mapping) and isinstance(payload.get("import"), list):
                return path
        for path in candidates:
            if path.is_file():
                return path
    raise ValueError(f"candidate has no interface declaration: {candidate}")


def _retired_task_names(
    interface: Mapping[str, Any], declarations_by_name: Mapping[str, TaskDeclaration]
) -> frozenset[str]:
    """Return tasks that are explicitly retired by the candidate contract.

    ``retired_tasks`` is the authoritative registry.  The all-presets-disabled
    fallback keeps older candidates safe while they are being rebuilt: a task
    disabled in every preset that mentions it is not silently reintroduced by
    a full-scope selector.
    """

    retired: set[str] = set()
    raw_retired = interface.get("retired_tasks", [])
    if not isinstance(raw_retired, list) or not all(
        isinstance(item, str) and item.strip() for item in raw_retired
    ):
        raise ValueError("malformed interface declaration: retired_tasks must be a list")
    for item in raw_retired:
        key = item.strip().casefold()
        if key not in declarations_by_name:
            raise ValueError(f"retired task is not declared: {item}")
        retired.add(key)

    presets = interface.get("preset")
    states: dict[str, list[bool]] = {}
    if isinstance(presets, list):
        for preset in presets:
            if not isinstance(preset, Mapping):
                continue
            preset_tasks = preset.get("task")
            if not isinstance(preset_tasks, list):
                continue
            for item in preset_tasks:
                if not isinstance(item, Mapping) or not isinstance(item.get("name"), str):
                    continue
                key = item["name"].strip().casefold()
                if key not in declarations_by_name or "enabled" not in item:
                    continue
                states.setdefault(key, []).append(bool(item["enabled"]))
    retired.update(key for key, values in states.items() if values and not any(values))
    return frozenset(retired)


def _candidate_payload_sha256(candidate: Path) -> str | None:
    metadata_path = candidate / "build-metadata.json"
    if not metadata_path.is_file():
        return None
    metadata = _read_object(metadata_path, kind="candidate metadata")
    raw_digest = metadata.get("payload_sha256")
    return raw_digest.strip() if isinstance(raw_digest, str) and raw_digest.strip() else None


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
    records: list[TaskDeclaration] = []

    imports = interface.get("import")
    if imports is not None:
        if not isinstance(imports, list) or not all(isinstance(item, str) for item in imports):
            raise ValueError("malformed interface declaration: import must be a list of paths")
        for relative in imports:
            task_path = interface_path.parent / relative
            task_payload = _read_object(task_path, kind="task declaration")
            for task in _task_items(task_payload, task_path):
                name = _string(task.get("name"), field="name", path=task_path)
                entry = _string(task.get("entry"), field="entry", path=task_path)
                records.append(
                    TaskDeclaration(name, entry, _extract_weekdays(task, name), str(task_path))
                )
    else:
        for task in _task_items(interface, interface_path):
            name = _string(task.get("name"), field="name", path=interface_path)
            entry = _string(task.get("entry"), field="entry", path=interface_path)
            records.append(
                TaskDeclaration(
                    name,
                    entry,
                    _extract_weekdays(task, name),
                    str(interface_path),
                )
            )

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


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    try:
        if len(raw) == 10:
            return datetime.combine(date.fromisoformat(raw), datetime.min.time())
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _record_timestamp(payload: Mapping[str, Any]) -> datetime | None:
    for field in ("finished_at", "completed_at", "ended_at", "timestamp", "run_date", "date"):
        parsed = _parse_timestamp(payload.get(field))
        if parsed is not None:
            return parsed
    if payload.get("status") == "running":
        return _parse_timestamp(payload.get("started_at"))
    return None


def _sort_datetime(value: datetime | None) -> datetime:
    if value is None:
        return datetime.min
    if value.tzinfo is not None:
        return value.astimezone(OPERATION_TIMEZONE).replace(tzinfo=None)
    return value


def _result_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return ()
    if not root.is_dir():
        raise ValueError(f"result root is not a directory: {root}")
    return (
        path
        for path in sorted(root.rglob("*.json"))
        if path.name == "result.json" or path.name.endswith("-result.json")
    )


def _result_records(
    result_root: Path, declarations_by_name: Mapping[str, TaskDeclaration]
) -> dict[str, ResultRecord]:
    latest: dict[str, ResultRecord] = {}
    for path in _result_files(result_root):
        payload = _read_object(path, kind="result evidence")
        raw_task_id = payload.get("task_id")
        if not isinstance(raw_task_id, str) or not raw_task_id.strip():
            raise ValueError(f"malformed result evidence: missing task_id: {path}")
        key = raw_task_id.strip().casefold()
        if key not in declarations_by_name:
            raise ValueError(f"malformed result evidence: unknown task_id={raw_task_id}: {path}")
        timestamp = _record_timestamp(payload)
        sort_key = (_sort_datetime(timestamp), path.stat().st_mtime_ns)
        record = ResultRecord(path, payload, sort_key)
        previous = latest.get(key)
        if previous is None or record.sort_key >= previous.sort_key:
            latest[key] = record
    return latest


def _freshness(record: ResultRecord | None, operation_date: date) -> tuple[bool, str]:
    if record is None:
        return False, "missing"
    timestamp = _record_timestamp(record.payload)
    if timestamp is None:
        return False, "missing_timestamp"
    local_timestamp = (
        timestamp.astimezone(OPERATION_TIMEZONE)
        if timestamp.tzinfo is not None
        else timestamp
    )
    if local_timestamp.date() != operation_date:
        return False, "expired"
    return True, "fresh"


def _acceptance_evidence_verified(payload: Mapping[str, Any]) -> bool:
    return (
        payload.get("evidence_origin") == "mfw_live_acceptance"
        and payload.get("acceptance_result") == "passed"
    )


def _postcondition_verified(task_id: str, payload: Mapping[str, Any]) -> tuple[bool, str]:
    raw = payload.get("postcondition")
    if not isinstance(raw, str) or not raw.strip():
        return False, "postcondition_missing"
    value = raw.strip()
    normalized = value.casefold()
    if normalized in GENERIC_POSTCONDITIONS:
        return False, "postcondition_not_task_specific"
    if any(marker in normalized for marker in INVALID_POSTCONDITION_MARKERS):
        return False, "postcondition_unverified"
    if payload.get("postcondition_verified") is True and _acceptance_evidence_verified(payload):
        return True, "verified"
    if (
        payload.get("business_postcondition_verified") is True
        and _acceptance_evidence_verified(payload)
    ):
        return True, "verified"

    allowed = SUCCESS_POSTCONDITIONS.get(task_id.upper())
    if allowed is not None and value in allowed:
        return True, "verified"

    task_slug = task_id.casefold()
    if task_slug.endswith("_daily"):
        task_slug = task_slug[: -len("_daily")]
    compact = task_slug.replace("_", ".")
    if value.casefold().startswith(f"{task_slug}."):
        return True, "verified"
    if value.casefold().startswith(f"{compact}."):
        return True, "verified"
    return False, "postcondition_not_task_specific"


def _native_marker_verified(value: object) -> bool:
    if value is True:
        return True
    if isinstance(value, str):
        normalized = value.strip().casefold()
        return normalized in NATIVE_SUCCESS_MARKERS
    if isinstance(value, Mapping):
        return any(
            _native_marker_verified(value.get(key))
            for key in ("status", "event", "name", "terminal")
        )
    if isinstance(value, (list, tuple)):
        return any(_native_marker_verified(item) for item in value)
    return False


def _native_terminal_verified(payload: Mapping[str, Any]) -> bool:
    if payload.get("native_terminal_verified") is True and _acceptance_evidence_verified(
        payload
    ):
        return True
    for key in (
        "native_terminal",
        "native_terminal_status",
        "native_terminal_event",
    ):
        if _native_marker_verified(payload.get(key)):
            return True
    evidence = payload.get("evidence")
    if isinstance(evidence, Mapping):
        for key in ("native_terminal", "native_terminal_status", "tasker_terminal"):
            if _native_marker_verified(evidence.get(key)):
                return True
    return False


def _evidence_item(
    task: TaskDeclaration,
    record: ResultRecord | None,
    operation_date: date,
) -> tuple[dict[str, Any], bool, str]:
    if record is None:
        item = {
            "eligible": True,
            "status": None,
            "fresh": False,
            "reason": "missing",
            "result_path": None,
        }
        return item, False, "missing"

    payload = record.payload
    fresh, freshness_reason = _freshness(record, operation_date)
    status = payload.get("status")
    item: dict[str, Any] = {
        "eligible": True,
        "status": status,
        "fresh": fresh,
        "reason": freshness_reason,
        "result_path": str(record.path),
    }
    for field in ("started_at", "finished_at", "postcondition", "error_code"):
        if field in payload:
            item[field] = payload[field]
    if not fresh:
        return item, False, freshness_reason
    if not isinstance(status, str) or not status.strip():
        item["reason"] = "status_missing"
        return item, False, "status_missing"
    normalized_status = status.strip().casefold()
    if normalized_status != "success":
        item["reason"] = (
            normalized_status
            if normalized_status in NON_SUCCESS_STATUSES
            else "not_success"
        )
        return item, False, item["reason"]
    postcondition_ok, postcondition_reason = _postcondition_verified(task.name, payload)
    if not postcondition_ok:
        item["reason"] = postcondition_reason
        return item, False, postcondition_reason
    if not _native_terminal_verified(payload):
        item["reason"] = "native_terminal_unverified"
        return item, False, "native_terminal_unverified"
    item["reason"] = "accepted"
    item["native_terminal_verified"] = True
    return item, True, "accepted"


def _eligible(task: TaskDeclaration, operation_date: date, explicit: bool) -> bool:
    return explicit or task.weekdays is None or operation_date.weekday() in task.weekdays


def select_tasks(
    candidate: Path,
    *,
    operation_date: date | str | None = None,
    explicit_tasks: Sequence[str] = (),
    result_root: Path | None = None,
) -> dict[str, Any]:
    """Return the ordered current selection without changing external state."""

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
    control_explicit = [
        by_name[key].name for key in explicit_keys if by_name[key].name.upper() in CONTROL_TASKS
    ]
    if control_explicit:
        raise ValueError(f"control task is not selectable: {control_explicit[0]}")

    is_explicit = bool(normalized_explicit)
    requested_keys = set(explicit_keys)
    eligible = [
        task
        for task in declared
        if task.name.upper() not in CONTROL_TASKS
        and task.name.casefold() not in retired_keys
        and _eligible(task, operation_day, False)
        and (not is_explicit or task.name.casefold() in requested_keys)
    ]

    root = (Path(result_root) if result_root is not None else candidate / "debug").resolve()
    records = _result_records(root, by_name)
    evidence: dict[str, Any] = {
        "interface_path": str(interface_path),
        "result_root": str(root),
        "operation_date": operation_day.isoformat(),
        "operation_timezone": OPERATION_TIMEZONE_NAME,
    }
    precompleted: list[str] = []
    pending: list[str] = []
    considered_keys = {task.name.casefold() for task in eligible}
    omitted_tasks: list[str] = []
    scope_blockers: list[dict[str, str]] = []

    for task in declared:
        if task.name.upper() in CONTROL_TASKS:
            continue
        task_key = task.name.casefold()
        if task_key in retired_keys:
            reason = "retired"
            item = {
                "eligible": False,
                "status": None,
                "fresh": False,
                "reason": reason,
                "result_path": None,
            }
            if is_explicit and task_key in requested_keys:
                scope_blockers.append({"task_id": task.name, "reason": reason})
            else:
                omitted_tasks.append(task.name)
            evidence[task.name] = item
            continue
        if not _eligible(task, operation_day, False):
            reason = "not_eligible_today"
            evidence[task.name] = {
                "eligible": False,
                "status": None,
                "fresh": False,
                "reason": reason,
                "result_path": None,
            }
            if is_explicit and task_key in requested_keys:
                scope_blockers.append({"task_id": task.name, "reason": reason})
            else:
                omitted_tasks.append(task.name)
            continue
        if is_explicit and task_key not in requested_keys:
            omitted_tasks.append(task.name)
            evidence[task.name] = {
                "eligible": False,
                "status": None,
                "fresh": False,
                "reason": "not_requested",
                "result_path": None,
            }
            continue
        if task_key not in considered_keys:
            raise AssertionError(f"eligible task was not considered: {task.name}")
        item, accepted, reason = _evidence_item(
            task,
            records.get(task_key),
            operation_day,
        )
        evidence[task.name] = item
        if accepted:
            precompleted.append(task.name)
        else:
            pending.append(task.name)

    # Historical result files are evidence for the report only.  They must not
    # silently rewrite this round into a suffix run; a partial round provides
    # its own immutable next_tasks list for the next invocation.
    selected_tasks = list(pending) if not is_explicit else [task.name for task in eligible]

    return {
        "schema_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "candidate": str(candidate),
        "candidate_payload_sha256": _candidate_payload_sha256(candidate),
        "operation_date": operation_day.isoformat(),
        "operation_timezone": OPERATION_TIMEZONE_NAME,
        "scope_mode": "explicit" if is_explicit else "full",
        "requested_tasks": list(normalized_explicit),
        "retired_tasks": [task.name for task in declared if task.name.casefold() in retired_keys],
        "omitted_tasks": omitted_tasks,
        "scope_blockers": scope_blockers,
        "eligible_tasks": [task.name for task in eligible],
        "precompleted_tasks": precompleted,
        "pending_tasks": pending,
        "failed_task": None,
        "unrun_after_first_failure": [],
        "selected_tasks": selected_tasks,
        "evidence": evidence,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--date", dest="operation_date")
    parser.add_argument("--task", dest="explicit_tasks", action="append", default=[])
    parser.add_argument("--result-root", type=Path)
    parser.add_argument("--output", type=Path, help="atomically write the selection JSON")
    return parser


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        selection = select_tasks(
            args.candidate,
            operation_date=args.operation_date,
            explicit_tasks=tuple(args.explicit_tasks),
            result_root=args.result_root,
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


__all__ = [
    "CONTROL_TASKS",
    "SUCCESS_POSTCONDITIONS",
    "TaskDeclaration",
    "declarations",
    "main",
    "select_tasks",
]
