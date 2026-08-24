"""Accept a live MFW run from native terminal task events only."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from tools.mfw_native_status import (
    NativeTaskState,
    NativeTerminalEvent,
    parse_native_terminal_events,
)
from tools.mfw_profile import verify_profile_tasks
from tools.mfw_task_selection import CONTROL_TASKS
from tools.mfw_task_selection import declarations as selection_declarations

GUI_TASK_PATTERN = re.compile(r"任务 '([^']+)' 的执行信息")
VALID_TERMINAL_STATES = frozenset({"Succeeded", "Failed"})


@dataclass(frozen=True, slots=True)
class TaskDeclaration:
    name: str
    entry: str


@dataclass(frozen=True, slots=True)
class AcceptanceTicket:
    schema_version: int
    owner: str
    candidate: str
    expected_tasks: tuple[str, ...]
    entries: dict[str, str]
    expected_terminals: dict[str, NativeTaskState]
    started_at: str
    gui_offset: int
    maafw_offset: int
    evidence_directory: str
    selection: dict[str, Any] | None = None
    profile_name: str | None = None


def _read_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def declarations(candidate: Path) -> tuple[TaskDeclaration, ...]:
    result = tuple(
        TaskDeclaration(item.name, item.entry)
        for item in selection_declarations(candidate)
    )
    names = [item.name for item in result]
    if len(names) != len(set(names)) or "GAME_START" not in names:
        raise ValueError("candidate task declarations are duplicate or missing GAME_START")
    return result


def formal_task_order(candidate: Path) -> tuple[str, ...]:
    return tuple(item.name for item in declarations(candidate) if item.name != "GAME_STOP")


def _parse_expected_terminal(value: str) -> tuple[str, NativeTaskState]:
    task_id, separator, state = value.partition("=")
    task_id = task_id.strip().upper()
    state = state.strip()
    if not separator or not task_id or state not in VALID_TERMINAL_STATES:
        raise ValueError(f"invalid --expect-terminal: {value!r}")
    return task_id, state  # type: ignore[return-value]


def parse_expected_terminals(
    values: Sequence[str], expected_tasks: Sequence[str]
) -> dict[str, NativeTaskState]:
    expected = {task.upper() for task in expected_tasks}
    seen: set[str] = set()
    parsed: dict[str, NativeTaskState] = {
        task.upper(): "Succeeded" for task in expected_tasks
    }
    for value in values:
        task_id, state = _parse_expected_terminal(value)
        if task_id not in expected:
            raise ValueError(f"--expect-terminal task is not selected: {task_id}")
        if task_id in seen:
            raise ValueError(f"duplicate --expect-terminal for {task_id}")
        seen.add(task_id)
        parsed[task_id] = state
    return {task: parsed[task] for task in expected_tasks}  # type: ignore[return-value]


def _expected_tasks(
    candidate: Path,
    task_id: str | None,
    exclude_tasks: tuple[str, ...],
    selected_tasks: tuple[str, ...] | None,
) -> tuple[str, ...]:
    declared = formal_task_order(candidate)
    by_name = {name.upper(): name for name in declared}
    excludes = tuple(item.strip().upper() for item in exclude_tasks if item.strip())
    if len(excludes) != len(set(excludes)):
        raise ValueError("excluded tasks must be unique")
    invalid_excludes = [item for item in excludes if item in CONTROL_TASKS or item not in by_name]
    if invalid_excludes:
        raise ValueError(f"unknown excluded business task: {invalid_excludes[0]}")
    if selected_tasks is not None:
        if task_id is not None or excludes:
            raise ValueError("selected tasks cannot be combined with task or exclusions")
        normalized = tuple(item.strip().upper() for item in selected_tasks if item.strip())
        if not normalized:
            raise ValueError("selected tasks must not be empty")
        if len(normalized) != len(set(normalized)):
            raise ValueError("selected tasks must be unique")
        invalid = [item for item in normalized if item in CONTROL_TASKS or item not in by_name]
        if invalid:
            raise ValueError(f"unknown selected business task: {invalid[0]}")
        chosen = set(normalized)
        return ("GAME_START", *(name for name in declared if name.upper() in chosen))
    if task_id is None:
        excluded = set(excludes)
        return tuple(name for name in declared if name not in excluded)
    if excludes:
        raise ValueError("pair acceptance cannot exclude additional tasks")
    normalized_task = task_id.strip().upper()
    if normalized_task == "GAME_START":
        return ("GAME_START",)
    if normalized_task in CONTROL_TASKS or normalized_task not in by_name:
        raise ValueError(f"unknown business task: {normalized_task}")
    return ("GAME_START", by_name[normalized_task])


def begin_acceptance(
    candidate: Path,
    owner: str,
    task_id: str | None,
    exclude_tasks: tuple[str, ...] = (),
    *,
    selected_tasks: tuple[str, ...] | None = None,
    selection: dict[str, Any] | None = None,
    profile_name: str | None = None,
    expected_terminals: Sequence[str] = (),
) -> Path:
    candidate = candidate.resolve()
    if not (candidate / "MFW").is_file():
        raise ValueError(f"candidate has no MFW executable: {candidate}")
    if selection is not None:
        selection_candidate = selection.get("candidate")
        if (
            isinstance(selection_candidate, str)
            and Path(selection_candidate).resolve() != candidate
        ):
            raise ValueError("selection candidate does not match acceptance candidate")
        blockers = selection.get("scope_blockers")
        if isinstance(blockers, list) and blockers:
            raise ValueError(f"selection has scope blockers: {blockers!r}")
        raw_selected = selection.get("selected_tasks")
        if not isinstance(raw_selected, list) or not raw_selected or not all(
            isinstance(item, str) and item.strip() for item in raw_selected
        ):
            raise ValueError("selection.selected_tasks must be a non-empty string list")
        snapshot = tuple(item.strip() for item in raw_selected)
        if selected_tasks is None:
            selected_tasks = snapshot
        elif tuple(item.strip() for item in selected_tasks) != snapshot:
            raise ValueError("selected tasks do not match selection snapshot")
    expected = _expected_tasks(candidate, task_id, exclude_tasks, selected_tasks)
    declared = {item.name: item for item in declarations(candidate)}
    terminals = parse_expected_terminals(expected_terminals, expected)
    if profile_name is not None:
        verify_profile_tasks(candidate, profile_name, expected)
    now = datetime.now(timezone.utc)
    label = task_id.strip().upper() if task_id else "BATCH"
    if expected == ("GAME_START",):
        label = "GAME_START"
    run_id = now.strftime("%Y%m%dT%H%M%S%fZ")
    evidence = candidate / "debug" / "acceptance" / label / run_id
    evidence.mkdir(parents=True, exist_ok=False)
    gui = candidate / "debug" / "gui.log"
    maafw = candidate / "debug" / "maafw.log"
    ticket = AcceptanceTicket(
        2,
        owner,
        str(candidate),
        expected,
        {name: declared[name].entry for name in expected},
        terminals,
        now.isoformat(),
        gui.stat().st_size if gui.is_file() else 0,
        maafw.stat().st_size if maafw.is_file() else 0,
        str(evidence),
        selection,
        profile_name,
    )
    path = evidence / "ticket.json"
    path.write_text(
        json.dumps(asdict(ticket), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _suffix(path: Path, offset: int) -> bytes:
    if not path.is_file():
        return b""
    with path.open("rb") as stream:
        if path.stat().st_size < offset:
            offset = 0
        stream.seek(offset)
        return stream.read()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _suffix_with_rotation(candidate: Path, filename: str, offset: int) -> bytes:
    """Read a fresh log suffix across one or more MAA log rotations."""

    debug = Path(candidate) / "debug"
    current = debug / filename
    backups = sorted(
        debug.glob(f"{filename[:-4]}.bak.*{filename[-4:]}"),
        key=lambda path: path.stat().st_mtime_ns,
    )
    if current.exists() and current.stat().st_size >= offset:
        return _suffix(current, offset)
    if backups:
        # The ticket offset belongs to the pre-rotation main file.  The newest
        # backup is that file's continuation boundary; append the live file.
        source = backups[-1]
        return _suffix(source, offset) + (current.read_bytes() if current.exists() else b"")
    return _suffix(current, offset) if current.exists() else b""


def _load_ticket(ticket_path: Path) -> AcceptanceTicket:
    raw = _read_object(ticket_path)
    if int(raw["schema_version"]) != 2:
        raise ValueError(f"unsupported acceptance ticket schema: {raw.get('schema_version')}")
    expected = tuple(str(item) for item in raw["expected_tasks"])
    raw_terminals = raw.get("expected_terminals")
    if not isinstance(raw_terminals, dict):
        raise ValueError("ticket has no expected native terminals")
    terminals: dict[str, NativeTaskState] = {}
    for task in expected:
        state = raw_terminals.get(task)
        if state not in VALID_TERMINAL_STATES:
            raise ValueError(f"ticket has invalid expected terminal for {task}: {state}")
        terminals[task] = state  # type: ignore[assignment]
    return AcceptanceTicket(
        2,
        str(raw["owner"]),
        str(raw["candidate"]),
        expected,
        {str(key): str(value) for key, value in raw["entries"].items()},
        terminals,
        str(raw["started_at"]),
        int(raw["gui_offset"]),
        int(raw["maafw_offset"]),
        str(raw["evidence_directory"]),
        raw.get("selection") if isinstance(raw.get("selection"), dict) else None,
        str(raw["profile_name"]) if raw.get("profile_name") else None,
    )


def _event_for_task(
    task_id: str, ticket: AcceptanceTicket, events: Sequence[NativeTerminalEvent]
) -> NativeTerminalEvent:
    matching = [event for event in events if event.entry == ticket.entries[task_id]]
    if len(matching) != 1:
        raise ValueError(f"{task_id}: native terminal events={matching!r}")
    event = matching[0]
    expected = ticket.expected_terminals[task_id]
    if event.state != expected:
        raise ValueError(f"{task_id}: expected native terminal {expected}, observed {event.state}")
    return event


def finish_acceptance(ticket_path: Path, *, partial: bool = False) -> Path:
    ticket = _load_ticket(ticket_path)
    candidate = Path(ticket.candidate)
    evidence = Path(ticket.evidence_directory)
    gui_slice = evidence / "gui.log.slice"
    maafw_slice = evidence / "maafw.log.slice"
    gui_slice.write_bytes(_suffix(candidate / "debug" / "gui.log", ticket.gui_offset))
    maafw_slice.write_bytes(
        _suffix_with_rotation(candidate, "maafw.log", ticket.maafw_offset)
    )
    gui_text = gui_slice.read_text(encoding="utf-8", errors="replace")
    maafw_text = maafw_slice.read_text(encoding="utf-8", errors="replace")
    declared_names = set(formal_task_order(candidate))
    executed = tuple(name for name in GUI_TASK_PATTERN.findall(gui_text) if name in declared_names)
    if executed != ticket.expected_tasks:
        raise ValueError(
            f"exact task order mismatch: expected={ticket.expected_tasks}, actual={executed}"
        )
    events = parse_native_terminal_events(maafw_text, ticket.entries)
    task_records: dict[str, dict[str, str]] = {}
    errors: list[str] = []
    for task_id in ticket.expected_tasks:
        try:
            event = _event_for_task(task_id, ticket, events)
        except ValueError as exc:
            if not partial:
                raise
            errors.append(str(exc))
            matching = [event for event in events if event.entry == ticket.entries[task_id]]
            task_records[task_id] = {
                "task_id": task_id,
                "entry": ticket.entries[task_id],
                "native_terminal": matching[0].state if len(matching) == 1 else "Missing",
            }
            continue
        task_records[task_id] = {
            "task_id": task_id,
            "entry": event.entry,
            "native_terminal": event.state,
        }
    summary = evidence / "acceptance.json"
    summary.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "owner": ticket.owner,
                "candidate": ticket.candidate,
                "started_at": ticket.started_at,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "result": "partial" if partial or errors else "passed",
                "expected_tasks": list(ticket.expected_tasks),
                "expected_terminals": ticket.expected_terminals,
                "tasks": task_records,
                "errors": errors,
                "gui_log_sha256": _sha256(gui_slice),
                "maafw_log_sha256": _sha256(maafw_slice),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    list_parser = commands.add_parser("list")
    list_parser.add_argument("--candidate", type=Path, required=True)
    begin_parser = commands.add_parser("begin")
    begin_parser.add_argument("--candidate", type=Path, required=True)
    begin_parser.add_argument("--owner", required=True)
    begin_parser.add_argument("--task")
    begin_parser.add_argument("--selected-task", action="append", default=[])
    begin_parser.add_argument("--selection", type=Path)
    begin_parser.add_argument("--profile-name")
    begin_parser.add_argument("--exclude-task", action="append", default=[])
    begin_parser.add_argument("--expect-terminal", action="append", default=[])
    finish_parser = commands.add_parser("finish")
    finish_parser.add_argument("--ticket", type=Path, required=True)
    finish_parser.add_argument("--partial", action="store_true")
    finish_parser.add_argument("--record", type=Path)
    return parser


def _write_record(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    shutil.copy2(source, temporary)
    temporary.replace(target)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "list":
            for task_id in formal_task_order(args.candidate):
                if task_id not in CONTROL_TASKS:
                    print(json.dumps(["GAME_START", task_id]))
            return 0
        if args.command == "begin":
            selection = _read_object(args.selection) if args.selection is not None else None
            print(
                begin_acceptance(
                    args.candidate,
                    args.owner,
                    args.task,
                    tuple(args.exclude_task),
                    selected_tasks=tuple(args.selected_task) if args.selected_task else None,
                    selection=selection,
                    profile_name=args.profile_name,
                    expected_terminals=tuple(args.expect_terminal),
                )
            )
            return 0
        summary = finish_acceptance(args.ticket, partial=args.partial)
        if args.record is not None:
            _write_record(summary, args.record)
        print(summary)
        return 0
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "AcceptanceTicket",
    "TaskDeclaration",
    "begin_acceptance",
    "declarations",
    "finish_acceptance",
    "formal_task_order",
    "main",
    "parse_expected_terminals",
]
