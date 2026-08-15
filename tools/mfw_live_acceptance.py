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
from typing import Any

from tools.mfw_profile import verify_profile_tasks
from tools.mfw_task_selection import (
    SUCCESS_POSTCONDITIONS,
)
from tools.mfw_task_selection import (
    declarations as selection_declarations,
)

# A native task success event only proves that the pipeline terminated.  The
# business result must carry an explicit terminal outcome as well.  An
# already-complete task is a valid terminal outcome; it must not be mistaken
# for a business failure merely because it did not perform a consumptive
# action.
SUCCESS_STATUSES = frozenset({"success"})
ACCEPTED_STATUSES = frozenset({"success", "already_complete", "not_eligible"})
# A task result is accepted only when its success status is paired with one of
# the signals that the task pipeline can reach after recognizing the business
# outcome.  The result's ``postcondition`` is the persisted signal name; a
# native Tasker.Succeeded event alone is never sufficient.
SUCCESS_SIGNAL_POSTCONDITIONS = SUCCESS_POSTCONDITIONS

# These are terminal signals emitted when a task has no eligible work left.
# They are kept separate from normal success signals so a successful action
# cannot be certified merely because an already-complete marker is visible.
TERMINAL_POSTCONDITIONS: dict[str, frozenset[str]] = {
    "MAIL_REWARD_DAILY": frozenset({"mail.empty"}),
    "SHOP_FREE_GIFT_DAILY": frozenset({"shop.daily_free_gift_claimed"}),
    "BUY_TEA_DAILY": frozenset({"tea.sold_out", "tea.no_remaining_stock"}),
    "FREE_APPRAISAL_DAILY": frozenset({"appraisal.used"}),
    "HERO_DISPATCH_DAILY": frozenset(
        {"hero.all_completed", "hero.all_dispatched_waiting", "hero.first_task_in_progress"}
    ),
    "BREAK_ARRAY_MARTIAL_DAILY": frozenset(
        {"break_array.daily_exhausted", "break_array.unavailable"}
    ),
    "DUNGEON_SWEEP_DAILY": frozenset(
        {"dungeon.ticket_unavailable", "dungeon.sweep_unavailable"}
    ),
    "EAT_STAMINA_FOOD_DAILY": frozenset({"food.longjing_shrimp_unavailable"}),
    "GUILD_DONATION_DAILY": frozenset({"guild.donation.unavailable"}),
    "SPEND_CONDENSATE_DAILY": frozenset({"condensate.both_regions_sold_out"}),
    "DAILY_TASK_REWARD_CLAIM_DAILY": frozenset({"daily_reward.no_claimable"}),
    "BATTLE_PASS_REWARD_DAILY": frozenset(
        {"battle_pass.no_task_or_basic_claimable"}
    ),
}
CONTROL_TASKS = frozenset({"GAME_START", "GAME_STOP"})
GUI_TASK_PATTERN = re.compile(r"任务 '([^']+)' 的执行信息")
NATIVE_TASK_PATTERN = re.compile(
    r"\[msg=Tasker\.Task\.(Succeeded|Failed)\].*?\"entry\":\"([^\"]+)\""
)
STARTUP_RECOVERY_EXHAUSTED_MARKERS = (
    "GAME_START_RECOVERY_EXHAUSTED",
    "公共-通用-启动恢复-耗尽",
)


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
    started_at: str
    gui_offset: int
    maafw_offset: int
    existing_results: dict[str, int]
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


def _result_snapshot(candidate: Path) -> dict[str, int]:
    return {
        str(path.resolve()): path.stat().st_mtime_ns
        for path in candidate.glob("debug/mfw-*/*/result.json")
    }


def begin_acceptance(
    candidate: Path,
    owner: str,
    task_id: str | None,
    exclude_tasks: tuple[str, ...] = (),
    *,
    selected_tasks: tuple[str, ...] | None = None,
    selection: dict[str, Any] | None = None,
    profile_name: str | None = None,
) -> Path:
    candidate = candidate.resolve()
    if not (candidate / "MFW").is_file():
        raise ValueError(f"candidate has no MFW executable: {candidate}")
    if selection is not None:
        selection_candidate = selection.get("candidate")
        if isinstance(selection_candidate, str) and selection_candidate.strip():
            if Path(selection_candidate).resolve() != candidate:
                raise ValueError("selection candidate does not match acceptance candidate")
        blockers = selection.get("scope_blockers")
        if isinstance(blockers, list) and blockers:
            raise ValueError(f"selection has scope blockers: {blockers!r}")
        raw_selected = selection.get("selected_tasks")
        if not isinstance(raw_selected, list) or not raw_selected or not all(
            isinstance(item, str) and item.strip() for item in raw_selected
        ):
            raise ValueError("selection.selected_tasks must be a non-empty string list")
        selected_from_snapshot = tuple(item.strip() for item in raw_selected)
        if selected_tasks is None:
            selected_tasks = selected_from_snapshot
        elif tuple(item.strip() for item in selected_tasks) != selected_from_snapshot:
            raise ValueError("selected tasks do not match selection snapshot")
    declared = declarations(candidate)
    by_name = {item.name.upper(): item for item in declared}
    normalized_excludes = tuple(item.strip().upper() for item in exclude_tasks)
    if len(normalized_excludes) != len(set(normalized_excludes)):
        raise ValueError("excluded tasks must be unique")
    invalid_excludes = [
        item
        for item in normalized_excludes
        if item in CONTROL_TASKS or item not in by_name
    ]
    if invalid_excludes:
        raise ValueError(f"unknown excluded business task: {invalid_excludes[0]}")
    if selected_tasks is not None:
        if task_id is not None or normalized_excludes:
            raise ValueError("selected tasks cannot be combined with task or exclusions")
        normalized_selected = tuple(item.strip().upper() for item in selected_tasks)
        if not normalized_selected:
            raise ValueError("selected tasks must not be empty")
        if len(normalized_selected) != len(set(normalized_selected)):
            raise ValueError("selected tasks must be unique")
        invalid_selected = [
            item
            for item in normalized_selected
            if item in CONTROL_TASKS or item not in by_name
        ]
        if invalid_selected:
            raise ValueError(f"unknown selected business task: {invalid_selected[0]}")
        selected_set = set(normalized_selected)
        expected_business = tuple(
            name
            for name in formal_task_order(candidate)
            if name.upper() in selected_set and name not in CONTROL_TASKS
        )
        expected = ("GAME_START", *expected_business)
        label = "BATCH"
    elif task_id is None:
        excluded = set(normalized_excludes)
        expected = tuple(
            name for name in formal_task_order(candidate) if name not in excluded
        )
        label = "ALL"
    else:
        if normalized_excludes:
            raise ValueError("pair acceptance cannot exclude additional tasks")
        task_id = task_id.strip().upper()
        if task_id == "GAME_START":
            expected = ("GAME_START",)
            label = "GAME_START"
        elif task_id in CONTROL_TASKS or task_id not in by_name:
            raise ValueError(f"unknown business task: {task_id}")
        else:
            expected = ("GAME_START", task_id)
            label = task_id
    if profile_name is not None:
        verify_profile_tasks(candidate, profile_name, expected)
    now = datetime.now(timezone.utc)
    run_id = now.strftime("%Y%m%dT%H%M%S%fZ")
    evidence = candidate / "debug" / "acceptance" / label / run_id
    evidence.mkdir(parents=True, exist_ok=False)
    gui = candidate / "debug" / "gui.log"
    maafw = candidate / "debug" / "maafw.log"
    ticket = AcceptanceTicket(
        1,
        owner,
        str(candidate),
        expected,
        {name: by_name[name.upper()].entry for name in expected},
        now.isoformat(),
        gui.stat().st_size if gui.is_file() else 0,
        maafw.stat().st_size if maafw.is_file() else 0,
        _result_snapshot(candidate),
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


def _fresh_result(candidate: Path, task_id: str, previous: dict[str, int]) -> Path:
    candidates = []
    for path in candidate.glob(f"debug/mfw-*/{task_id}/result.json"):
        resolved = str(path.resolve())
        if previous.get(resolved) != path.stat().st_mtime_ns:
            candidates.append(path)
    if not candidates:
        raise ValueError(f"{task_id}: no fresh result")
    return max(candidates, key=lambda item: item.stat().st_mtime_ns)


def _require_success_signal(task_id: str, payload: dict[str, Any]) -> str:
    status = payload.get("status")
    if status not in ACCEPTED_STATUSES:
        raise ValueError(f"{task_id}: status={status}")
    signal = payload.get("postcondition")
    if not isinstance(signal, str) or not signal.strip():
        raise ValueError(f"{task_id}: success signal is missing")
    if status == "success":
        allowed = SUCCESS_SIGNAL_POSTCONDITIONS.get(task_id)
        if allowed is not None and signal not in allowed:
            raise ValueError(f"{task_id}: success signal={signal}")
        return signal

    terminal_allowed = TERMINAL_POSTCONDITIONS.get(task_id, frozenset())
    if signal in terminal_allowed:
        return signal

    normalized = signal.strip().casefold()
    if normalized in {"completed", "home", "success", "task.terminal", "terminal"}:
        raise ValueError(f"{task_id}: success signal={signal}")
    if any(
        marker in normalized
        for marker in (
            "ambiguous",
            "error",
            "failed",
            "failure",
            "missing",
            "unknown",
            "unverified",
            "unsafe",
        )
    ):
        raise ValueError(f"{task_id}: success signal={signal}")

    task_slug = task_id.casefold()
    if task_slug.endswith("_daily"):
        task_slug = task_slug[: -len("_daily")]
    compact = task_slug.replace("_", ".")
    if normalized.startswith(f"{task_slug}.") or normalized.startswith(f"{compact}."):
        return signal
    raise ValueError(f"{task_id}: success signal={signal}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _write_verified_result(source: Path, destination: Path, entry: str) -> None:
    payload = _read_object(source)
    payload["native_terminal_verified"] = True
    payload["native_terminal_event"] = "Tasker.Task.Succeeded"
    payload["native_terminal_status"] = "Succeeded"
    payload["evidence_origin"] = "mfw_live_acceptance"
    payload["acceptance_result"] = "passed"
    payload["acceptance_id"] = destination.parent.name
    evidence = payload.get("evidence")
    if not isinstance(evidence, dict):
        evidence = {}
    evidence["native_terminal"] = {
        "event": "Tasker.Task.Succeeded",
        "status": "Succeeded",
        "entry": entry,
    }
    payload["evidence"] = evidence
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def finish_acceptance(ticket_path: Path) -> Path:
    ticket = _load_ticket(ticket_path)
    candidate = Path(ticket.candidate)
    evidence = Path(ticket.evidence_directory)
    gui_bytes = _suffix(candidate / "debug" / "gui.log", ticket.gui_offset)
    maa_bytes = _suffix(candidate / "debug" / "maafw.log", ticket.maafw_offset)
    (evidence / "gui.log.slice").write_bytes(gui_bytes)
    (evidence / "maafw.log.slice").write_bytes(maa_bytes)
    gui_text = gui_bytes.decode("utf-8", errors="replace")
    maa_text = maa_bytes.decode("utf-8", errors="replace")
    declared_names = set(formal_task_order(candidate))
    executed = tuple(name for name in GUI_TASK_PATTERN.findall(gui_text) if name in declared_names)
    if executed != ticket.expected_tasks:
        raise ValueError(
            f"exact task order mismatch: expected={ticket.expected_tasks}, actual={executed}"
        )
    terminals = NATIVE_TASK_PATTERN.findall(maa_text)
    for name in ticket.expected_tasks:
        entry = ticket.entries[name]
        states = [state for state, observed_entry in terminals if observed_entry == entry]
        if states != ["Succeeded"]:
            raise ValueError(f"{name}: native terminal events={states}")
    results: dict[str, dict[str, Any]] = {}
    for task_id in ticket.expected_tasks:
        if task_id in CONTROL_TASKS:
            continue
        source = _fresh_result(candidate, task_id, ticket.existing_results)
        payload = _read_object(source)
        status = payload.get("status")
        if payload.get("task_id") != task_id or status not in ACCEPTED_STATUSES:
            raise ValueError(f"{task_id}: status={status}")
        if payload.get("error_code") not in (None, ""):
            raise ValueError(f"{task_id}: error_code={payload.get('error_code')}")
        success_signal = _require_success_signal(task_id, payload)
        destination = evidence / f"{task_id}-result.json"
        _write_verified_result(source, destination, ticket.entries[task_id])
        results[task_id] = {
            "status": status,
            "postcondition": success_signal,
            "native_terminal": "Tasker.Task.Succeeded",
            "result_path": str(destination),
            "sha256": _sha256(destination),
        }
    summary = evidence / "acceptance.json"
    summary.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "owner": ticket.owner,
                "candidate": ticket.candidate,
                "started_at": ticket.started_at,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "expected_tasks": list(ticket.expected_tasks),
                "selection": ticket.selection,
                "result": "passed",
                "tasks": results,
                "gui_log_sha256": _sha256(evidence / "gui.log.slice"),
                "maafw_log_sha256": _sha256(evidence / "maafw.log.slice"),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return summary


def _load_ticket(ticket_path: Path) -> AcceptanceTicket:
    raw = _read_object(ticket_path)
    return AcceptanceTicket(
        int(raw["schema_version"]),
        str(raw["owner"]),
        str(raw["candidate"]),
        tuple(raw["expected_tasks"]),
        {str(key): str(value) for key, value in raw["entries"].items()},
        str(raw["started_at"]),
        int(raw["gui_offset"]),
        int(raw["maafw_offset"]),
        {str(key): int(value) for key, value in raw["existing_results"].items()},
        str(raw["evidence_directory"]),
        raw.get("selection") if isinstance(raw.get("selection"), dict) else None,
        str(raw["profile_name"]) if raw.get("profile_name") else None,
    )


def _partial_task_outcome(
    candidate: Path,
    ticket: AcceptanceTicket,
    terminal_events: list[tuple[str, str]],
) -> tuple[set[str], dict[str, dict[str, Any]]]:
    """Return tasks proven successful by this round, without writing evidence."""

    terminal_by_name: dict[str, list[str]] = {}
    entry_to_name = {entry: name for name, entry in ticket.entries.items()}
    for state, entry in terminal_events:
        name = entry_to_name.get(entry)
        if name is not None:
            terminal_by_name.setdefault(name, []).append(state)

    successful: set[str] = set()
    details: dict[str, dict[str, Any]] = {}
    for task_id in ticket.expected_tasks:
        if task_id in CONTROL_TASKS:
            continue
        states = terminal_by_name.get(task_id, [])
        try:
            source = _fresh_result(candidate, task_id, ticket.existing_results)
        except ValueError:
            details[task_id] = {"native_states": states, "result": None}
            continue
        payload = _read_object(source)
        status = payload.get("status")
        signal = payload.get("postcondition")
        accepted = False
        if status in ACCEPTED_STATUSES and states and states[-1] == "Succeeded":
            try:
                signal = _require_success_signal(task_id, payload)
            except ValueError:
                pass
            else:
                if payload.get("error_code") in (None, ""):
                    accepted = True
        if accepted:
            successful.add(task_id)
        details[task_id] = {
            "native_states": states,
            "result": str(source),
            "status": status,
            "postcondition": signal,
            "accepted": accepted,
        }
    return successful, details


def finish_partial_acceptance(ticket_path: Path) -> Path:
    """Archive an incomplete round and calculate its next safe task set.

    This path is deliberately separate from strict ``finish``.  It never turns
    a stopped batch into success and never fabricates a result file; it only
    freezes the observed log slices and the fresh results that can be proven.
    """

    ticket = _load_ticket(ticket_path)
    candidate = Path(ticket.candidate)
    evidence = Path(ticket.evidence_directory)
    gui_slice = evidence / "gui.log.slice"
    maa_slice = evidence / "maafw.log.slice"
    gui_slice.write_bytes(_suffix(candidate / "debug" / "gui.log", ticket.gui_offset))
    maa_slice.write_bytes(_suffix(candidate / "debug" / "maafw.log", ticket.maafw_offset))
    gui_text = gui_slice.read_text(encoding="utf-8", errors="replace")
    maa_text = maa_slice.read_text(encoding="utf-8", errors="replace")
    declared_names = set(formal_task_order(candidate))
    executed = tuple(name for name in GUI_TASK_PATTERN.findall(gui_text) if name in declared_names)
    terminal_events = NATIVE_TASK_PATTERN.findall(maa_text)
    entry_to_name = {entry: name for name, entry in ticket.entries.items()}
    terminal_records = [
        {
            "status": state,
            "entry": entry,
            "task_id": entry_to_name.get(entry),
            "recognized": entry in entry_to_name,
        }
        for state, entry in terminal_events
    ]
    first_failed_task = next(
        (
            entry_to_name[entry]
            for state, entry in terminal_events
            if state == "Failed" and entry in entry_to_name
        ),
        None,
    )
    successful_tasks, task_outcomes = _partial_task_outcome(
        candidate, ticket, terminal_events
    )
    startup_recovery_failed = (
        first_failed_task == "GAME_START"
        and any(marker in maa_text for marker in STARTUP_RECOVERY_EXHAUSTED_MARKERS)
    )
    business_expected = [name for name in ticket.expected_tasks if name not in CONTROL_TASKS]
    executed_set = set(executed)
    if first_failed_task == "GAME_START":
        next_tasks = [name for name in business_expected if name not in successful_tasks]
    elif first_failed_task in business_expected:
        failure_index = business_expected.index(first_failed_task)
        next_tasks = [
            name
            for name in business_expected[failure_index + 1 :]
            if name not in successful_tasks
        ]
    else:
        next_tasks = [name for name in business_expected if name not in successful_tasks]
    first_failure_index = (
        ticket.expected_tasks.index(first_failed_task)
        if first_failed_task in ticket.expected_tasks
        else None
    )
    unrun_after_first_failure = []
    continued_after_failure = []
    if first_failure_index is not None:
        for name in ticket.expected_tasks[first_failure_index + 1 :]:
            if name in CONTROL_TASKS:
                continue
            if name not in executed_set:
                unrun_after_first_failure.append(name)
            else:
                continued_after_failure.append(name)

    result = {
        "schema_version": 2,
        "owner": ticket.owner,
        "candidate": ticket.candidate,
        "started_at": ticket.started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "expected_tasks": list(ticket.expected_tasks),
        "executed_tasks": list(executed),
        "terminal_events": terminal_records,
        "first_failed_task": first_failed_task,
        "unrun_after_first_failure": unrun_after_first_failure,
        "continued_after_failure": continued_after_failure,
        "next_tasks": next_tasks,
        "task_outcomes": task_outcomes,
        "selection": ticket.selection,
        "result": "partial",
        "failure_kind": (
            "startup_recovery_failed"
            if startup_recovery_failed
            else "startup_blocked"
            if first_failed_task == "GAME_START"
            else "task_failed"
            if first_failed_task is not None
            else "incomplete_or_infrastructure"
        ),
        "startup_recovery_failed": startup_recovery_failed,
        "gui_log_sha256": _sha256(gui_slice),
        "maafw_log_sha256": _sha256(maa_slice),
    }
    summary = evidence / "acceptance.json"
    summary.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    partial = evidence / "partial.json"
    shutil.copy2(summary, partial)
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
    finish_parser = commands.add_parser("finish")
    finish_parser.add_argument("--ticket", type=Path, required=True)
    finish_parser.add_argument("--record", type=Path)
    finish_parser.add_argument(
        "--partial",
        action="store_true",
        help="archive an incomplete round instead of requiring strict success",
    )
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
            order = formal_task_order(args.candidate)
            for task_id in order:
                if task_id not in CONTROL_TASKS:
                    print(json.dumps(["GAME_START", task_id]))
            return 0
        if args.command == "begin":
            selection = None
            if args.selection is not None:
                selection = _read_object(args.selection)
            print(
                begin_acceptance(
                    args.candidate,
                    args.owner,
                    args.task,
                    tuple(args.exclude_task),
                    selected_tasks=(
                        tuple(args.selected_task) if args.selected_task else None
                    ),
                    selection=selection,
                    profile_name=args.profile_name,
                )
            )
            return 0
        summary = (
            finish_partial_acceptance(args.ticket)
            if args.partial
            else finish_acceptance(args.ticket)
        )
        if args.record is not None:
            _write_record(summary, args.record)
        print(summary)
        return 0
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
