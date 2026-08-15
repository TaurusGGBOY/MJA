"""Verify reproducible links in a real MFW failure-contract evidence record."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

# ``python tools/verify_mfw_evidence.py`` puts ``tools/`` first on sys.path;
# make the repository's local ``agent`` package unambiguous for the CLI.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) in sys.path:
    sys.path.remove(str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT))

from agent.custom.support.policy import TASK_POLICIES  # noqa: E402

_HEX64 = frozenset("0123456789abcdefABCDEF")

MFW_FINAL_CANONICAL_IDS = (
    "MAIL_REWARD_DAILY",
    "SHOP_FREE_GIFT_DAILY",
    "BUY_TEA_DAILY",
    "FREE_APPRAISAL_DAILY",
    "TRIAL_SWORD_DAILY",
    "HERO_DISPATCH_DAILY",
    "COLLECTION_DEPLOYMENT_DAILY",
    "WEEKLY_FREE_GIFT_MONDAY",
    "SHADOW_RUINS_DAILY",
    "SPEND_CONDENSATE_DAILY",
    "MARTIAL_STUDY_BREAKTHROUGH_DAILY",
    "EAT_STAMINA_FOOD_DAILY",
    "DUNGEON_SWEEP_DAILY",
    "JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY",
    "RING_CHALLENGE_DAILY",
    "DAILY_TASK_REWARD_CLAIM_DAILY",
    "BATTLE_PASS_REWARD_DAILY",
)

MFW_FULL_TASK_ORDER = ("GAME_START", *MFW_FINAL_CANONICAL_IDS)
_FULL_CANDIDATE_INSTALL = "install/mfw-full-candidate"

BATCH_A_IDS = (
    "MAIL_REWARD_DAILY",
    "SHOP_FREE_GIFT_DAILY",
    "FREE_APPRAISAL_DAILY",
    "TRIAL_SWORD_DAILY",
    "HERO_DISPATCH_DAILY",
    "COLLECTION_DEPLOYMENT_DAILY",
    "WEEKLY_FREE_GIFT_MONDAY",
    "DAILY_TASK_REWARD_CLAIM_DAILY",
    "BATTLE_PASS_REWARD_DAILY",
)

BATCH_B_IDS = (
    "BUY_TEA_DAILY",
    "SPEND_CONDENSATE_DAILY",
    "EAT_STAMINA_FOOD_DAILY",
    "JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY",
)

_BATCH_IDS = {
    "a": BATCH_A_IDS,
    "b": tuple(
        task_id
        for task_id in MFW_FINAL_CANONICAL_IDS
        if task_id in (*BATCH_A_IDS, *BATCH_B_IDS)
    ),
}
_NORMAL_TERMINAL_STATUSES = frozenset(
    {"success", "already_complete", "not_eligible"}
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _digest(payload: Mapping[str, Any], field: str) -> str:
    value = payload.get(field)
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in _HEX64 for character in value)
    ):
        raise ValueError(f"evidence has invalid {field}")
    return value.lower()


def _path_from_evidence(evidence_path: Path, value: Any, field: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"evidence is missing {field}")
    path = Path(value)
    return path if path.is_absolute() else evidence_path.parent / path


def _non_empty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"evidence is missing {field}")
    return value.strip()


def _non_negative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"evidence has invalid {field}")
    return value


def _positive_int(value: Any, field: str) -> int:
    parsed = _non_negative_int(value, field)
    if parsed == 0:
        raise ValueError(f"evidence has invalid {field}")
    return parsed


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"evidence is missing {field}")
    return value


def _existing_evidence_path(evidence_path: Path, value: Any, field: str) -> Path:
    path = _path_from_evidence(evidence_path, value, field)
    if not path.is_file():
        raise ValueError(f"evidence path does not exist for {field}: {path}")
    return path


def _load_object(path: Path, *, kind: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {kind}: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{kind} must be an object")
    return payload


def _candidate_identity(
    evidence_path: Path,
    candidate_value: Any,
    *,
    field: str = "candidate",
    require_full_install: bool = False,
) -> dict[str, Any]:
    candidate = _mapping(candidate_value, field)
    build_sha256 = _digest(candidate, "build_sha256")
    metadata_sha256 = _digest(candidate, "metadata_sha256")
    metadata_path = _existing_evidence_path(
        evidence_path, candidate.get("metadata_path"), f"{field}.metadata_path"
    )
    if _sha256(metadata_path) != metadata_sha256:
        raise ValueError(f"candidate metadata hash does not match {field}")

    install_path = candidate.get("install_path", candidate.get("install"))
    payload_sha256 = candidate.get("payload_sha256")
    if require_full_install and install_path != _FULL_CANDIDATE_INSTALL:
        raise ValueError(
            "full candidate evidence must use install/mfw-full-candidate"
        )
    if require_full_install:
        metadata = _load_object(metadata_path, kind="candidate metadata")
        metadata_payload_sha256 = _digest(metadata, "payload_sha256")
        payload_sha256 = _digest(candidate, "payload_sha256")
        if payload_sha256 != metadata_payload_sha256:
            raise ValueError("full candidate payload hash does not match metadata")
    elif payload_sha256 is not None:
        payload_sha256 = _digest(candidate, "payload_sha256")
    if install_path is not None:
        install_path = _non_empty_string(install_path, f"{field}.install_path")

    return {
        "build_sha256": build_sha256,
        "metadata_sha256": metadata_sha256,
        "payload_sha256": payload_sha256,
        "metadata_path": str(metadata_path),
        "install_path": install_path,
    }


def _same_candidate(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return all(
        left.get(field) == right.get(field)
        for field in (
            "build_sha256",
            "metadata_sha256",
            "payload_sha256",
            "install_path",
        )
    )


def _verify_action_counts(
    payload: Mapping[str, Any], policy: Any, *, field: str = "action_counts"
) -> dict[str, int]:
    raw_counts = _mapping(payload.get(field), field)
    counts: dict[str, int] = {}
    for action_id, value in raw_counts.items():
        if not isinstance(action_id, str) or action_id not in policy.action_caps:
            raise ValueError(f"evidence has unknown action in {field}: {action_id}")
        count = _non_negative_int(value, f"{field}.{action_id}")
        cap = policy.action_caps[action_id]
        if count > cap:
            raise ValueError(
                f"evidence action {action_id} exceeds policy cap {cap}"
            )
        counts[action_id] = count
    return counts


def _verify_task_evidence(evidence_path: Path, task_id: str) -> dict[str, Any]:
    evidence_path = Path(evidence_path)
    try:
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read task evidence: {evidence_path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("task evidence must be an object")
    if payload.get("schema_version") != 1:
        raise ValueError("task evidence must use schema_version 1")
    if payload.get("task_id") != task_id:
        raise ValueError(f"task evidence has wrong task_id for {task_id}")

    candidate = _mapping(payload.get("candidate"), "candidate")
    candidate_identity = _candidate_identity(evidence_path, candidate)
    build_sha256 = candidate_identity["build_sha256"]
    metadata_sha256 = candidate_identity["metadata_sha256"]
    metadata_path = candidate_identity["metadata_path"]

    run_id = _non_empty_string(payload.get("run_id"), "run_id")
    log_path = _existing_evidence_path(evidence_path, payload.get("log_path"), "log_path")
    _non_empty_string(payload.get("start_page"), "start_page")
    if payload.get("controller_backend") != "ScreenCaptureKit":
        raise ValueError("task evidence must use ScreenCaptureKit")
    terminal_status = payload.get("terminal_status")
    if terminal_status not in _NORMAL_TERMINAL_STATUSES:
        raise ValueError(f"task evidence has invalid terminal_status for {task_id}")
    if payload.get("status") == "passed" and (not run_id or not log_path):
        raise ValueError("passed evidence requires run_id and log_path")

    policy = TASK_POLICIES.get(task_id)
    if policy is None:
        raise ValueError(f"no policy exists for {task_id}")
    action_counts = _verify_action_counts(payload, policy)
    raw_actions = payload.get("actions")
    if (
        not isinstance(raw_actions, Sequence)
        or isinstance(raw_actions, (str, bytes, bytearray))
    ):
        raise ValueError("evidence is missing actions")

    observed_counts: dict[str, int] = {}
    resource_totals = {resource_id: 0 for resource_id in policy.resource_caps}
    resource_action_ids: set[str] = set()
    for index, raw_action in enumerate(raw_actions):
        action = _mapping(raw_action, f"actions[{index}]")
        action_id = _non_empty_string(action.get("action_id"), f"actions[{index}].action_id")
        if action_id not in policy.action_caps:
            raise ValueError(f"evidence has unknown action: {action_id}")
        count = _positive_int(action.get("count"), f"actions[{index}].count")
        observed_counts[action_id] = observed_counts.get(action_id, 0) + count
        if observed_counts[action_id] > policy.action_caps[action_id]:
            raise ValueError(f"evidence action {action_id} exceeds policy cap")

        for field in ("before_image", "after_image", "trace_path"):
            _existing_evidence_path(evidence_path, action.get(field), f"actions[{index}].{field}")

        resource_id = action.get("resource_id")
        if resource_id is None:
            continue
        resource_id = _non_empty_string(resource_id, f"actions[{index}].resource_id")
        if resource_id not in policy.resource_caps:
            raise ValueError(f"evidence has unapproved resource: {resource_id}")
        resource_action_ids.add(action_id)
        observed_amount = _positive_int(
            action.get("observed_amount"), f"actions[{index}].observed_amount"
        )
        budget_amount = _positive_int(
            action.get("budget_amount"), f"actions[{index}].budget_amount"
        )
        if budget_amount > observed_amount:
            raise ValueError(f"budget exceeds observed {resource_id}")
        if budget_amount > policy.resource_caps[resource_id]:
            raise ValueError(f"budget exceeds policy cap for {resource_id}")
        ocr_text = _non_empty_string(action.get("ocr_text"), f"actions[{index}].ocr_text")
        if resource_id not in ocr_text:
            raise ValueError(f"OCR evidence does not name {resource_id}")
        resource_totals[resource_id] += budget_amount * count
        if resource_totals[resource_id] > policy.resource_caps[resource_id]:
            raise ValueError(f"resource total exceeds policy cap for {resource_id}")

    for action_id in set(action_counts) | set(observed_counts):
        if action_counts.get(action_id, 0) != observed_counts.get(action_id, 0):
            raise ValueError(f"action_counts does not match actions for {action_id}")

    raw_resource_totals = _mapping(payload.get("resource_totals"), "resource_totals")
    if set(raw_resource_totals) != set(policy.resource_caps):
        raise ValueError(f"resource_totals does not match policy for {task_id}")
    for resource_id, value in raw_resource_totals.items():
        total = _non_negative_int(value, f"resource_totals.{resource_id}")
        if total > policy.resource_caps[resource_id]:
            raise ValueError(f"resource total exceeds policy cap for {resource_id}")
        if total != resource_totals[resource_id]:
            raise ValueError(f"resource total does not match actions for {resource_id}")

    rerun = _mapping(payload.get("rerun"), "rerun")
    rerun_run_id = _non_empty_string(rerun.get("run_id"), "rerun.run_id")
    if rerun_run_id == run_id:
        raise ValueError("rerun must have a distinct run_id")
    _existing_evidence_path(evidence_path, rerun.get("log_path"), "rerun.log_path")
    if rerun.get("terminal_status") not in {"already_complete", "not_eligible"}:
        raise ValueError("rerun must end already_complete or not_eligible")
    rerun_counts = _verify_action_counts(rerun, policy)
    if any(rerun_counts.get(action_id, 0) for action_id in resource_action_ids):
        raise ValueError("rerun repeats a consumptive action")
    duplicate_side_effects = rerun.get("duplicate_side_effects", [])
    if duplicate_side_effects not in (None, [], {}, "", 0, False):
        raise ValueError("rerun contains duplicate side effects")

    return {
        "task_id": task_id,
        "build_sha256": build_sha256,
        "metadata_sha256": metadata_sha256,
        "metadata_path": metadata_path,
        "run_id": run_id,
        "terminal_status": terminal_status,
        "action_count": len(raw_actions),
        "resource_totals": resource_totals,
        "rerun_run_id": rerun_run_id,
        "rerun_terminal_status": rerun.get("terminal_status"),
    }


def _verify_sequence(
    sequence_path: Path,
    *,
    batch: str,
    build_sha256: str,
    task_ids: Sequence[str],
) -> dict[str, Any]:
    try:
        payload = json.loads(Path(sequence_path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read sequence evidence: {sequence_path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("sequence evidence must be an object")
    if payload.get("schema_version") != 1:
        raise ValueError("sequence evidence must use schema_version 1")
    if payload.get("batch") != batch:
        raise ValueError("sequence evidence has the wrong batch")
    if _digest(payload, "build_sha256") != build_sha256:
        raise ValueError("sequence evidence does not use the same build")

    raw_runs = payload.get("runs")
    if (
        not isinstance(raw_runs, Sequence)
        or isinstance(raw_runs, (str, bytes, bytearray))
        or len(raw_runs) != 2
    ):
        raise ValueError("sequence evidence must contain exactly two runs")
    expected_order = list(task_ids)
    run_ids: set[str] = set()
    for run_index, raw_run in enumerate(raw_runs):
        run = _mapping(raw_run, f"runs[{run_index}]")
        run_id = _non_empty_string(run.get("run_id"), f"runs[{run_index}].run_id")
        if run_id in run_ids:
            raise ValueError("sequence evidence contains duplicate run_id")
        run_ids.add(run_id)
        order = run.get("task_order")
        if (
            not isinstance(order, Sequence)
            or isinstance(order, (str, bytes, bytearray))
            or list(order) != expected_order
        ):
            raise ValueError("sequence task_order is not the canonical order")
        events = run.get("events")
        if (
            not isinstance(events, Sequence)
            or isinstance(events, (str, bytes, bytearray))
            or len(events) != len(expected_order)
        ):
            raise ValueError("sequence events do not contain every task once")
        event_ids: list[str] = []
        for event_index, raw_event in enumerate(events):
            event = _mapping(raw_event, f"runs[{run_index}].events[{event_index}]")
            event_id = _non_empty_string(
                event.get("task_id"),
                f"runs[{run_index}].events[{event_index}].task_id",
            )
            event_ids.append(event_id)
            if event.get("started") is not True:
                raise ValueError(f"sequence task {event_id} did not start")
            if event.get("terminal_status") not in _NORMAL_TERMINAL_STATUSES:
                raise ValueError(f"sequence task {event_id} did not finish normally")
        if event_ids != expected_order or len(set(event_ids)) != len(expected_order):
            raise ValueError("sequence events are not the canonical order")

    abort_isolation = _mapping(payload.get("abort_isolation"), "abort_isolation")
    injected_task_id = _non_empty_string(
        abort_isolation.get("injected_task_id"), "abort_isolation.injected_task_id"
    )
    following_task_id = _non_empty_string(
        abort_isolation.get("following_task_id"), "abort_isolation.following_task_id"
    )
    if injected_task_id not in task_ids or following_task_id not in task_ids:
        raise ValueError("abort isolation names a task outside the batch")
    if injected_task_id == following_task_id:
        raise ValueError("abort isolation must have a following task")
    if abort_isolation.get("abort_status") != "failed":
        raise ValueError("abort isolation does not prove a failed task")
    if abort_isolation.get("following_started") is not True:
        raise ValueError("abort isolation following task did not start")
    if abort_isolation.get("following_terminal_status") not in _NORMAL_TERMINAL_STATUSES:
        raise ValueError("abort isolation following task did not finish normally")

    return {
        "batch": batch,
        "build_sha256": build_sha256,
        "run_ids": sorted(run_ids),
        "task_ids": expected_order,
    }


def verify_batch(root: Path, *, batch: str) -> dict[str, Any]:
    root = Path(root)
    if batch not in _BATCH_IDS:
        raise ValueError(f"unsupported batch: {batch}")
    task_ids = _BATCH_IDS[batch]
    summaries = []
    for task_id in task_ids:
        evidence_path = root / f"{task_id}.json"
        if not evidence_path.is_file():
            raise ValueError(f"missing task evidence: {evidence_path}")
        summaries.append(_verify_task_evidence(evidence_path, task_id))

    build_shas = {summary["build_sha256"] for summary in summaries}
    if len(build_shas) != 1:
        raise ValueError("all batch tasks must use the same build")
    build_sha256 = next(iter(build_shas))
    sequence_path = root / f"batch-{batch}-sequence.json"
    if not sequence_path.is_file():
        raise ValueError(f"missing batch-{batch}-sequence evidence: {sequence_path}")
    sequence = _verify_sequence(
        sequence_path,
        batch=batch,
        build_sha256=build_sha256,
        task_ids=task_ids,
    )
    return {
        "batch": batch,
        "build_sha256": build_sha256,
        "task_ids": list(task_ids),
        "tasks": summaries,
        "sequence": sequence,
    }


def _verify_full_task_evidence(
    evidence_path: Path, task_id: str
) -> dict[str, Any]:
    """Verify one task's two records from the frozen full candidate.

    The older batch evidence format remains supported by ``verify_batch``.  A
    full-candidate record must additionally identify the immutable full
    candidate and explicitly mark the second record as a same-day manual-all
    rerun.  Keeping the two records in one file prevents a later run from
    silently replacing the first-run evidence.
    """

    evidence_path = Path(evidence_path)
    payload = _load_object(evidence_path, kind="full task evidence")
    summary = _verify_task_evidence(evidence_path, task_id)
    candidate = _candidate_identity(
        evidence_path,
        payload.get("candidate"),
        require_full_install=True,
    )

    if payload.get("evidence_scope") != "full-candidate":
        raise ValueError(f"full task evidence has wrong evidence_scope for {task_id}")
    full_candidate = _mapping(payload.get("full_candidate"), "full_candidate")
    if full_candidate.get("first_entry") != "full-preset":
        raise ValueError(f"full task evidence has no full-preset history for {task_id}")
    if full_candidate.get("rerun_entry") != "manual-all":
        raise ValueError(f"full task evidence has no manual-all history for {task_id}")

    terminal_status = payload["terminal_status"]
    if terminal_status == "not_eligible":
        _non_empty_string(payload.get("reason"), "reason")

    rerun = _mapping(payload.get("rerun"), "rerun")
    if rerun.get("same_day") is not True:
        raise ValueError(f"full task rerun is not marked same-day for {task_id}")
    if rerun.get("terminal_status") == "not_eligible":
        _non_empty_string(rerun.get("reason"), "rerun.reason")

    policy = TASK_POLICIES[task_id]
    rerun_resource_totals = _mapping(
        rerun.get("resource_totals"), "rerun.resource_totals"
    )
    if set(rerun_resource_totals) != set(policy.resource_caps):
        raise ValueError(f"rerun resource_totals does not match policy for {task_id}")
    for resource_id, value in rerun_resource_totals.items():
        if _non_negative_int(value, f"rerun.resource_totals.{resource_id}") != 0:
            raise ValueError(f"rerun repeats resource consumption for {resource_id}")

    # If the recorder emitted an explicit history array, make sure it really
    # preserves both records and their evidence logs.  The top-level
    # first-run fields plus ``rerun`` are the canonical representation, so the
    # array is optional for backwards-compatible live recorders.
    history = payload.get("history")
    if history is not None:
        if (
            not isinstance(history, Sequence)
            or isinstance(history, (str, bytes, bytearray))
            or len(history) != 2
        ):
            raise ValueError(f"full task history must contain two records for {task_id}")
        expected_history = (
            (summary["run_id"], "full-preset", summary["terminal_status"]),
            (summary["rerun_run_id"], "manual-all", summary["rerun_terminal_status"]),
        )
        history_ids: set[str] = set()
        for index, raw_record in enumerate(history):
            record = _mapping(raw_record, f"history[{index}]")
            record_run_id = _non_empty_string(
                record.get("run_id"), f"history[{index}].run_id"
            )
            if record_run_id in history_ids:
                raise ValueError(f"full task history has duplicate run_id for {task_id}")
            history_ids.add(record_run_id)
            if (
                record_run_id,
                record.get("entry"),
                record.get("terminal_status"),
            ) != expected_history[index]:
                raise ValueError(f"full task history does not preserve both runs for {task_id}")
            _existing_evidence_path(
                evidence_path, record.get("log_path"), f"history[{index}].log_path"
            )
            evidence_paths = record.get("evidence_paths", [])
            if (
                not isinstance(evidence_paths, Sequence)
                or isinstance(evidence_paths, (str, bytes, bytearray))
            ):
                raise ValueError(f"history[{index}].evidence_paths is invalid")
            for path_index, evidence_value in enumerate(evidence_paths):
                _existing_evidence_path(
                    evidence_path,
                    evidence_value,
                    f"history[{index}].evidence_paths[{path_index}]",
                )

    summary["candidate"] = candidate
    summary["rerun_resource_totals"] = {
        resource_id: 0 for resource_id in policy.resource_caps
    }
    return summary


def _verify_task_order(
    order_value: Any, expected_order: Sequence[str], *, field: str
) -> list[str]:
    if (
        not isinstance(order_value, Sequence)
        or isinstance(order_value, (str, bytes, bytearray))
    ):
        raise ValueError(f"{field} is missing")
    order = list(order_value)
    if any(not isinstance(task_id, str) or not task_id.strip() for task_id in order):
        raise ValueError(f"{field} contains an invalid task id")
    if len(order) != len(set(order)):
        raise ValueError(f"{field} must list every task exactly once")
    if order != list(expected_order):
        raise ValueError(f"{field} is not the canonical order")
    return order


def _verify_entry_events(
    entry_path: Path,
    entry: Mapping[str, Any],
    *,
    entry_name: str,
    expected_order: Sequence[str],
    task_summaries: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    task_order = _verify_task_order(
        entry.get("task_order"), expected_order, field=f"{entry_name}.task_order"
    )
    raw_runs = entry.get("runs")
    if (
        not isinstance(raw_runs, Sequence)
        or isinstance(raw_runs, (str, bytes, bytearray))
        or len(raw_runs) != 1
    ):
        raise ValueError(f"{entry_name} must contain exactly one recorded run")
    run = _mapping(raw_runs[0], f"{entry_name}.runs[0]")
    run_id = _non_empty_string(run.get("run_id"), f"{entry_name}.runs[0].run_id")
    _existing_evidence_path(
        entry_path, run.get("log_path"), f"{entry_name}.runs[0].log_path"
    )
    run_order = run.get("task_order", task_order)
    _verify_task_order(
        run_order, expected_order, field=f"{entry_name}.runs[0].task_order"
    )
    events = run.get("events")
    if (
        not isinstance(events, Sequence)
        or isinstance(events, (str, bytes, bytearray))
        or len(events) != len(expected_order)
    ):
        raise ValueError(f"{entry_name} events must contain every task exactly once")

    event_ids: list[str] = []
    for index, raw_event in enumerate(events):
        event = _mapping(raw_event, f"{entry_name}.events[{index}]")
        task_id = _non_empty_string(
            event.get("task_id"), f"{entry_name}.events[{index}].task_id"
        )
        event_ids.append(task_id)
        if event.get("started") is not True:
            raise ValueError(f"{entry_name} task {task_id} did not start")
        terminal_status = event.get("terminal_status")
        if terminal_status not in _NORMAL_TERMINAL_STATUSES:
            raise ValueError(f"{entry_name} task {task_id} did not finish normally")
        if terminal_status == "not_eligible":
            _non_empty_string(
                event.get("reason"), f"{entry_name}.events[{index}].reason"
            )

        if task_id == "GAME_START":
            if terminal_status != "success":
                raise ValueError(f"{entry_name} GAME_START did not succeed")
            continue
        if task_id not in task_summaries:
            raise ValueError(f"{entry_name} names an unknown task: {task_id}")
        summary = task_summaries[task_id]
        if entry_name == "full-preset":
            expected_run_id = summary["run_id"]
            expected_status = summary["terminal_status"]
        else:
            expected_run_id = summary["rerun_run_id"]
            expected_status = summary["rerun_terminal_status"]
        if event.get("run_id") is not None and event.get("run_id") != expected_run_id:
            raise ValueError(f"{entry_name} event run_id does not match {task_id}")
        if terminal_status != expected_status:
            raise ValueError(f"{entry_name} event status does not match {task_id}")

    if event_ids != list(expected_order) or len(set(event_ids)) != len(expected_order):
        raise ValueError(f"{entry_name} events must list every task exactly once")
    return {"run_id": run_id, "task_order": task_order}


def _verify_full_entry(
    entry_path: Path,
    *,
    entry_name: str,
    task_summaries: Mapping[str, Mapping[str, Any]],
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    payload = _load_object(entry_path, kind=f"{entry_name} evidence")
    if payload.get("schema_version") != 1:
        raise ValueError(f"{entry_name} evidence must use schema_version 1")
    if payload.get("entry") != entry_name:
        raise ValueError(f"{entry_name} evidence has the wrong entry")
    if payload.get("controller_backend") != "ScreenCaptureKit":
        raise ValueError(f"{entry_name} evidence must use ScreenCaptureKit")
    entry_candidate = _candidate_identity(
        entry_path,
        payload.get("candidate"),
        require_full_install=True,
    )
    if not _same_candidate(entry_candidate, candidate):
        raise ValueError(f"{entry_name} does not use the same candidate metadata")
    event_summary = _verify_entry_events(
        entry_path,
        payload,
        entry_name=entry_name,
        expected_order=MFW_FULL_TASK_ORDER,
        task_summaries=task_summaries,
    )
    return {
        "entry": entry_name,
        "run_id": event_summary["run_id"],
        "task_order": list(MFW_FULL_TASK_ORDER),
        "candidate": entry_candidate,
    }


def _verify_full_sequence(
    sequence_path: Path,
    *,
    task_summaries: Mapping[str, Mapping[str, Any]],
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    payload = _load_object(sequence_path, kind="batch-c sequence evidence")
    if payload.get("schema_version") != 1:
        raise ValueError("batch-c sequence evidence must use schema_version 1")
    if payload.get("batch") != "c":
        raise ValueError("batch-c sequence evidence has the wrong batch")
    if payload.get("controller_backend") != "ScreenCaptureKit":
        raise ValueError("batch-c sequence evidence must use ScreenCaptureKit")
    sequence_candidate = _candidate_identity(
        sequence_path,
        payload.get("candidate"),
        require_full_install=True,
    )
    if not _same_candidate(sequence_candidate, candidate):
        raise ValueError("batch-c sequence does not use the same candidate metadata")
    expected_order = _verify_task_order(
        payload.get("task_order"), MFW_FULL_TASK_ORDER, field="batch-c.task_order"
    )
    raw_runs = payload.get("runs")
    if (
        not isinstance(raw_runs, Sequence)
        or isinstance(raw_runs, (str, bytes, bytearray))
        or len(raw_runs) != 2
    ):
        raise ValueError("batch-c sequence must contain exactly two runs")
    run_ids: set[str] = set()
    expected_entries = ("full-preset", "manual-all")
    for run_index, raw_run in enumerate(raw_runs):
        run = _mapping(raw_run, f"batch-c.runs[{run_index}]")
        run_id = _non_empty_string(
            run.get("run_id"), f"batch-c.runs[{run_index}].run_id"
        )
        if run_id in run_ids:
            raise ValueError("batch-c sequence contains duplicate run_id")
        run_ids.add(run_id)
        if run.get("entry") != expected_entries[run_index]:
            raise ValueError("batch-c sequence entries are not full-preset then manual-all")
        _existing_evidence_path(
            sequence_path, run.get("log_path"), f"batch-c.runs[{run_index}].log_path"
        )
        _verify_task_order(
            run.get("task_order", expected_order),
            expected_order,
            field=f"batch-c.runs[{run_index}].task_order",
        )
        events = run.get("events")
        if (
            not isinstance(events, Sequence)
            or isinstance(events, (str, bytes, bytearray))
            or len(events) != len(expected_order)
        ):
            raise ValueError("batch-c sequence events must contain every task exactly once")
        event_ids: list[str] = []
        for event_index, raw_event in enumerate(events):
            event = _mapping(raw_event, f"batch-c.events[{run_index}][{event_index}]")
            task_id = _non_empty_string(
                event.get("task_id"),
                f"batch-c.events[{run_index}][{event_index}].task_id",
            )
            event_ids.append(task_id)
            if event.get("started") is not True:
                raise ValueError(f"batch-c sequence task {task_id} did not start")
            if event.get("terminal_status") not in _NORMAL_TERMINAL_STATUSES:
                raise ValueError(f"batch-c sequence task {task_id} did not finish normally")
            if event.get("terminal_status") == "not_eligible":
                _non_empty_string(event.get("reason"), "batch-c event reason")
            if task_id != "GAME_START":
                if task_id not in task_summaries:
                    raise ValueError(f"batch-c sequence names an unknown task: {task_id}")
                summary = task_summaries[task_id]
                expected_status = (
                    summary["terminal_status"]
                    if run_index == 0
                    else summary["rerun_terminal_status"]
                )
                if event.get("terminal_status") != expected_status:
                    raise ValueError(f"batch-c event status does not match {task_id}")
        if event_ids != expected_order or len(set(event_ids)) != len(expected_order):
            raise ValueError("batch-c sequence events must list every task exactly once")
    return {"run_ids": sorted(run_ids), "task_order": expected_order}


def _verify_full_business_abort(
    evidence_path: Path, *, candidate: Mapping[str, Any]
) -> dict[str, Any]:
    payload = _load_object(evidence_path, kind="full business-abort evidence")
    if payload.get("schema_version") != 1:
        raise ValueError("full business-abort evidence must use schema_version 1")
    if payload.get("controller_backend") != "ScreenCaptureKit":
        raise ValueError("full business-abort evidence must use ScreenCaptureKit")
    evidence_candidate = _candidate_identity(
        evidence_path,
        payload.get("candidate"),
        require_full_install=True,
    )
    if not _same_candidate(evidence_candidate, candidate):
        raise ValueError("full business-abort does not use the same candidate metadata")
    _non_empty_string(payload.get("run_id"), "full business-abort run_id")
    _existing_evidence_path(evidence_path, payload.get("log_path"), "log_path")
    if payload.get("abort_failed") is not True or payload.get("abort_status") != "failed":
        raise ValueError("full business-abort does not prove a failed Abort")
    if payload.get("sentinel_ran") is not True or payload.get("following_started") is not True:
        raise ValueError("full business-abort does not prove the following task ran")
    if payload.get("following_terminal_status") != "success":
        raise ValueError("full business-abort following task did not succeed")
    injected_task_id = _non_empty_string(
        payload.get("injected_task_id"), "injected_task_id"
    )
    following_task_id = _non_empty_string(
        payload.get("following_task_id"), "following_task_id"
    )
    if injected_task_id == following_task_id:
        raise ValueError("full business-abort must have a distinct following task")

    for field in (
        "base_metadata_sha256",
        "base_payload_sha256",
        "overlay_sha256",
        "probe_metadata_sha256",
    ):
        _digest(payload, field)
    if payload["base_metadata_sha256"].lower() != candidate["metadata_sha256"]:
        raise ValueError("full business-abort base metadata does not match candidate")
    if payload["base_payload_sha256"].lower() != candidate["payload_sha256"]:
        raise ValueError("full business-abort base payload does not match candidate")
    probe_metadata_path = _existing_evidence_path(
        evidence_path, payload.get("probe_metadata_path"), "probe_metadata_path"
    )
    if _sha256(probe_metadata_path) != payload["probe_metadata_sha256"].lower():
        raise ValueError("probe metadata hash does not match full business-abort")
    probe_metadata = _load_object(probe_metadata_path, kind="probe metadata")
    for field in ("base_metadata_sha256", "base_payload_sha256", "overlay_sha256"):
        if probe_metadata.get(field) != payload[field].lower():
            raise ValueError(f"probe metadata {field} does not match full business-abort")

    return {
        "run_id": payload["run_id"],
        "injected_task_id": injected_task_id,
        "following_task_id": following_task_id,
        "candidate": evidence_candidate,
    }


def _verify_full_infrastructure_stop(
    evidence_path: Path, *, candidate: Mapping[str, Any]
) -> dict[str, Any]:
    payload = _load_object(evidence_path, kind="full infrastructure-stop evidence")
    if payload.get("schema_version") != 1:
        raise ValueError("full infrastructure-stop evidence must use schema_version 1")
    if payload.get("controller_backend") != "ScreenCaptureKit":
        raise ValueError("full infrastructure-stop evidence must use ScreenCaptureKit")
    evidence_candidate = _candidate_identity(
        evidence_path,
        payload.get("candidate"),
        require_full_install=True,
    )
    if not _same_candidate(evidence_candidate, candidate):
        raise ValueError(
            "full infrastructure-stop does not use the same candidate metadata"
        )
    _non_empty_string(payload.get("run_id"), "full infrastructure-stop run_id")
    _existing_evidence_path(evidence_path, payload.get("log_path"), "log_path")
    if payload.get("terminal_status") not in {"infrastructure_stopped", "stopped"}:
        raise ValueError("infrastructure-stop has no infrastructure terminal status")
    if payload.get("queue_stopped") is not True:
        raise ValueError("infrastructure-stop did not stop the queue")
    reason = _non_empty_string(payload.get("stop_reason"), "stop_reason").lower()
    if "controller" not in reason or "disconnect" not in reason:
        raise ValueError("infrastructure-stop is not a disconnected-controller run")
    _verify_task_order(
        payload.get("task_order"),
        ("GAME_START", "MAIL_REWARD_DAILY", "SHOP_FREE_GIFT_DAILY"),
        field="infrastructure-stop.task_order",
    )

    stopped_before = payload.get("stopped_before_task_id", payload.get("stop_before_task_id"))
    stopped_before = _non_empty_string(stopped_before, "stopped_before_task_id")
    if stopped_before not in MFW_FINAL_CANONICAL_IDS:
        raise ValueError("infrastructure-stop names an invalid task boundary")
    stop_index = MFW_FULL_TASK_ORDER.index(stopped_before)

    started = payload.get("started_task_ids", [])
    if (
        not isinstance(started, Sequence)
        or isinstance(started, (str, bytes, bytearray))
        or len(started) != len(set(started))
    ):
        raise ValueError("infrastructure-stop started_task_ids are invalid")
    started_ids = list(started)
    if any(task_id not in MFW_FULL_TASK_ORDER for task_id in started_ids):
        raise ValueError("infrastructure-stop started an unknown task")
    if any(
        MFW_FULL_TASK_ORDER.index(task_id) >= stop_index for task_id in started_ids
    ):
        raise ValueError("infrastructure-stop started a task after the stop boundary")

    not_started = payload.get("not_started_task_ids")
    if (
        not isinstance(not_started, Sequence)
        or isinstance(not_started, (str, bytes, bytearray))
    ):
        raise ValueError("infrastructure-stop is missing not_started_task_ids")
    not_started_ids = list(not_started)
    expected_not_started = list(MFW_FULL_TASK_ORDER[stop_index:])
    if not_started_ids != expected_not_started or len(set(not_started_ids)) != len(
        expected_not_started
    ):
        raise ValueError("infrastructure-stop did not prove later tasks were skipped")

    return {
        "run_id": payload["run_id"],
        "stopped_before_task_id": stopped_before,
        "started_task_ids": started_ids,
        "candidate": evidence_candidate,
    }


def verify_full_candidate(root: Path) -> dict[str, Any]:
    """Verify the immutable full candidate and both complete-run entry points."""

    root = Path(root)
    summaries: list[dict[str, Any]] = []
    for task_id in MFW_FINAL_CANONICAL_IDS:
        evidence_path = root / f"{task_id}.json"
        if not evidence_path.is_file():
            raise ValueError(f"missing full-candidate task evidence: {evidence_path}")
        summaries.append(_verify_full_task_evidence(evidence_path, task_id))

    candidates = [summary["candidate"] for summary in summaries]
    candidate = candidates[0]
    if any(not _same_candidate(candidate, other) for other in candidates[1:]):
        raise ValueError("full-candidate tasks do not use the same candidate metadata")

    task_summaries = {
        summary["task_id"]: summary for summary in summaries
    }
    entry_results: dict[str, Any] = {}
    for entry_name in ("full-preset", "manual-all"):
        entry_path = root / f"{entry_name}.json"
        if not entry_path.is_file():
            raise ValueError(f"missing {entry_name} evidence: {entry_path}")
        entry_results[entry_name] = _verify_full_entry(
            entry_path,
            entry_name=entry_name,
            task_summaries=task_summaries,
            candidate=candidate,
        )

    sequence_path = root / "batch-c-sequence.json"
    if not sequence_path.is_file():
        raise ValueError(f"missing batch-c sequence evidence: {sequence_path}")
    sequence = _verify_full_sequence(
        sequence_path,
        task_summaries=task_summaries,
        candidate=candidate,
    )

    business_abort_path = root / "full-business-abort.json"
    if not business_abort_path.is_file():
        raise ValueError(f"missing full business-abort evidence: {business_abort_path}")
    business_abort = _verify_full_business_abort(
        business_abort_path, candidate=candidate
    )

    infrastructure_stop_path = root / "full-infrastructure-stop.json"
    if not infrastructure_stop_path.is_file():
        raise ValueError(
            f"missing full infrastructure-stop evidence: {infrastructure_stop_path}"
        )
    infrastructure_stop = _verify_full_infrastructure_stop(
        infrastructure_stop_path, candidate=candidate
    )

    return {
        "candidate": {
            "install_path": candidate["install_path"],
            "build_sha256": candidate["build_sha256"],
            "metadata_sha256": candidate["metadata_sha256"],
            "payload_sha256": candidate["payload_sha256"],
            "metadata_path": candidate["metadata_path"],
        },
        "task_ids": list(MFW_FINAL_CANONICAL_IDS),
        "tasks": summaries,
        "entries": entry_results,
        "batch_c_sequence": sequence,
        "business_abort": business_abort,
        "infrastructure_stop": infrastructure_stop,
    }


def _evidence_manifest(root: Path, *, excluded_path: Path) -> dict[str, str]:
    root = Path(root)
    excluded_path = Path(excluded_path).resolve()
    manifest: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"evidence manifest rejects symlink: {path}")
        if not path.is_file() or path.resolve() == excluded_path:
            continue
        relative = path.relative_to(root).as_posix()
        manifest[relative] = _sha256(path)
    return manifest


def _summary_statuses(payload: Mapping[str, Any]) -> None:
    required_statuses = {
        "automatic_tests": "passed",
        "macos_ios_full_preset": "passed",
        "macos_ios_manual_all": "passed",
        "batch_c_sequence": "passed",
        "business_abort": "passed",
        "infrastructure_stop": "passed",
    }
    for field, expected in required_statuses.items():
        if payload.get(field) != expected:
            raise ValueError(f"candidate summary {field} is not {expected}")


def verify_candidate_summary(
    summary_path: Path, *, evidence_root: Path | None = None
) -> dict[str, Any]:
    """Verify a generated candidate summary and every hashed evidence file."""

    summary_path = Path(summary_path)
    payload = _load_object(summary_path, kind="candidate summary")
    if payload.get("schema_version") != 1:
        raise ValueError("candidate summary must use schema_version 1")
    if payload.get("candidate_install") != _FULL_CANDIDATE_INSTALL:
        raise ValueError("candidate summary does not identify mfw-full-candidate")
    if payload.get("controller_backend") != "ScreenCaptureKit":
        raise ValueError("candidate summary must use ScreenCaptureKit")
    if payload.get("game_platform") != "macOS/iOS":
        raise ValueError("candidate summary must target macOS/iOS")
    _summary_statuses(payload)
    candidate_build_sha256 = _digest(payload, "candidate_build_sha256")

    metadata_path = _existing_evidence_path(
        summary_path, payload.get("build_metadata_path"), "build_metadata_path"
    )
    metadata_sha256 = _digest(payload, "build_metadata_sha256")
    if _sha256(metadata_path) != metadata_sha256:
        raise ValueError("candidate summary build metadata hash does not match")
    metadata = _load_object(metadata_path, kind="candidate build metadata")
    if payload.get("mja_commit") != metadata.get("mja_commit"):
        raise ValueError("candidate summary mja_commit does not match metadata")
    if payload.get("target") != metadata.get("target"):
        raise ValueError("candidate summary target does not match metadata")
    if payload.get("payload_sha256") != metadata.get("payload_sha256"):
        raise ValueError("candidate summary payload SHA does not match metadata")
    if not isinstance(metadata.get("mfw"), Mapping) or payload.get("mfw") != metadata["mfw"]:
        raise ValueError("candidate summary MFW metadata does not match")
    if not isinstance(metadata.get("maafw"), Mapping) or payload.get("maafw") != metadata["maafw"]:
        raise ValueError("candidate summary Maa metadata does not match")

    task_ids = payload.get("task_ids")
    _verify_task_order(task_ids, MFW_FINAL_CANONICAL_IDS, field="candidate summary.task_ids")

    root = Path(evidence_root) if evidence_root is not None else summary_path.parent
    raw_manifest = payload.get("evidence_manifest")
    if not isinstance(raw_manifest, Mapping):
        raise ValueError("candidate summary is missing evidence_manifest")
    manifest: dict[str, str] = {}
    for relative_value, digest_value in raw_manifest.items():
        if not isinstance(relative_value, str) or not relative_value.strip():
            raise ValueError("candidate summary has an invalid evidence path")
        relative_path = Path(relative_value)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise ValueError(f"candidate summary evidence path escapes root: {relative_value}")
        if (
            not isinstance(digest_value, str)
            or len(digest_value) != 64
            or any(character not in _HEX64 for character in digest_value)
        ):
            raise ValueError(f"candidate summary has invalid evidence SHA: {relative_value}")
        manifest[relative_value] = digest_value.lower()

    expected_manifest = _evidence_manifest(root, excluded_path=summary_path)
    if manifest != expected_manifest:
        raise ValueError("candidate summary evidence_manifest does not match evidence files")
    for relative_value, digest_value in manifest.items():
        path = root / relative_value
        if _sha256(path) != digest_value:
            raise ValueError(f"candidate summary evidence hash does not match: {relative_value}")

    full_candidate = verify_full_candidate(root)
    candidate = full_candidate["candidate"]
    if candidate_build_sha256 != candidate["build_sha256"]:
        raise ValueError("candidate summary build SHA does not match task evidence")
    if payload.get("build_metadata_sha256") != candidate["metadata_sha256"]:
        raise ValueError("candidate summary metadata SHA does not match task evidence")
    if payload.get("payload_sha256") != candidate["payload_sha256"]:
        raise ValueError("candidate summary payload SHA does not match task evidence")

    return payload


def write_candidate_summary(summary_path: Path, root: Path) -> dict[str, Any]:
    """Write a summary only after the complete live candidate gate passes."""

    summary_path = Path(summary_path)
    root = Path(root)
    verification = verify_full_candidate(root)
    candidate = verification["candidate"]
    metadata_path = Path(candidate["metadata_path"])
    metadata = _load_object(metadata_path, kind="candidate build metadata")
    mfw = _mapping(metadata.get("mfw"), "candidate metadata.mfw")
    maafw = _mapping(metadata.get("maafw"), "candidate metadata.maafw")
    try:
        relative_metadata_path = metadata_path.resolve().relative_to(
            summary_path.parent.resolve()
        )
    except ValueError:
        relative_metadata_path = Path(
            os.path.relpath(metadata_path.resolve(), summary_path.parent.resolve())
        )

    summary = {
        "schema_version": 1,
        "candidate_install": candidate["install_path"],
        "build_metadata_path": relative_metadata_path.as_posix(),
        "build_metadata_sha256": candidate["metadata_sha256"],
        "candidate_build_sha256": candidate["build_sha256"],
        "payload_sha256": metadata.get("payload_sha256"),
        "mja_commit": metadata.get("mja_commit"),
        "target": metadata.get("target"),
        "mfw": dict(mfw),
        "maafw": dict(maafw),
        "mfw_version": mfw.get("tag") or mfw.get("name"),
        "maa_version": maafw.get("tag") or maafw.get("name"),
        "controller_backend": "ScreenCaptureKit",
        "game_platform": "macOS/iOS",
        "automatic_tests": "passed",
        "macos_ios_full_preset": "passed",
        "macos_ios_manual_all": "passed",
        "batch_c_sequence": "passed",
        "business_abort": "passed",
        "infrastructure_stop": "passed",
        "task_ids": list(MFW_FINAL_CANONICAL_IDS),
        "evidence_manifest": _evidence_manifest(root, excluded_path=summary_path),
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = summary_path.with_name(summary_path.name + ".tmp")
    temporary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary_path.replace(summary_path)
    verify_candidate_summary(summary_path, evidence_root=root)
    return summary


def _git_output(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise ValueError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout.strip()


def _repo_relative_path(path: Path, repo_root: Path, field: str) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(f"{field} must be inside the repository: {path}") from exc


def _record_repo_path(value: Any, repo_root: Path, field: str) -> Path:
    relative = Path(_non_empty_string(value, field))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"legacy rollback {field} escapes repository")
    return repo_root / relative


def _artifact_manifest(artifact: Path, manifest_path: Path) -> dict[str, str]:
    artifact = Path(artifact)
    if not artifact.is_dir():
        raise ValueError(f"legacy artifact is not a directory: {artifact}")
    if manifest_path.resolve() == artifact.resolve() or manifest_path.is_relative_to(artifact):
        raise ValueError("legacy manifest must be outside the artifact root")
    result: dict[str, str] = {}
    for path in sorted(artifact.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"legacy artifact contains symlink: {path}")
        if path.is_file():
            result[path.relative_to(artifact).as_posix()] = _sha256(path)
    if not result:
        raise ValueError("legacy artifact has no files")
    return result


def _read_sha_manifest(manifest_path: Path, artifact: Path) -> dict[str, str]:
    try:
        lines = Path(manifest_path).read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValueError(f"cannot read legacy manifest: {manifest_path}") from exc
    entries: dict[str, str] = {}
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            raise ValueError(f"legacy manifest line {line_number} is malformed")
        digest, raw_path = parts
        if (
            len(digest) != 64
            or any(character not in _HEX64 for character in digest)
        ):
            raise ValueError(f"legacy manifest line {line_number} has invalid SHA")
        relative = Path(raw_path.lstrip("*"))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"legacy manifest line {line_number} escapes artifact")
        normalized = relative.as_posix()
        if normalized in entries:
            raise ValueError(f"legacy manifest contains duplicate path: {normalized}")
        target = artifact / relative
        if not target.is_file() or target.is_symlink():
            raise ValueError(f"legacy manifest path does not exist: {normalized}")
        actual = _sha256(target)
        if actual != digest.lower():
            raise ValueError(f"legacy manifest SHA mismatch: {normalized}")
        entries[normalized] = digest.lower()

    expected = _artifact_manifest(artifact, Path(manifest_path))
    if set(entries) != set(expected):
        missing = sorted(set(expected) - set(entries))
        extra = sorted(set(entries) - set(expected))
        raise ValueError(f"legacy manifest file set mismatch; missing={missing}, extra={extra}")
    return entries


def _tag_commit(repo_root: Path, tag: str) -> str:
    tag = _non_empty_string(tag, "tag")
    _git_output(repo_root, "check-ref-format", f"refs/tags/{tag}")
    return _git_output(repo_root, "rev-parse", "-q", "--verify", f"refs/tags/{tag}^{{}}")


def write_legacy_rollback(
    output_path: Path,
    *,
    tag: str,
    artifact: Path,
    manifest: Path,
    repo_root: Path = PROJECT_ROOT,
) -> dict[str, Any]:
    """Write a rollback record only for a tag and fully verified old artifact."""

    output_path = Path(output_path)
    repo_root = Path(repo_root)
    artifact = Path(artifact)
    manifest = Path(manifest)
    head_commit = _git_output(repo_root, "rev-parse", "HEAD")
    tag_commit = _tag_commit(repo_root, tag)
    if tag_commit != head_commit:
        raise ValueError("legacy rollback tag does not point at current HEAD")
    entries = _read_sha_manifest(manifest, artifact)
    record = {
        "schema_version": 1,
        "tag": tag,
        "commit": head_commit,
        "tag_commit": tag_commit,
        "artifact_path": _repo_relative_path(artifact, repo_root, "artifact"),
        "manifest_path": _repo_relative_path(manifest, repo_root, "manifest"),
        "manifest_sha256": _sha256(manifest),
        "artifact_storage": "local-pending-publication",
        "verified": True,
        "files": entries,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(output_path.name + ".tmp")
    temporary_path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary_path.replace(output_path)
    return record


def verify_legacy_rollback(
    record_path: Path, *, repo_root: Path = PROJECT_ROOT
) -> dict[str, Any]:
    record_path = Path(record_path)
    repo_root = Path(repo_root)
    record = _load_object(record_path, kind="legacy rollback record")
    if record.get("schema_version") != 1 or record.get("verified") is not True:
        raise ValueError("legacy rollback record is not verified")
    if record.get("artifact_storage") != "local-pending-publication":
        raise ValueError("legacy rollback record has invalid artifact_storage")
    tag = _non_empty_string(record.get("tag"), "tag")
    head_commit = _git_output(repo_root, "rev-parse", "HEAD")
    tag_commit = _tag_commit(repo_root, tag)
    if record.get("commit") != head_commit or record.get("tag_commit") != tag_commit:
        raise ValueError("legacy rollback commit does not match tag and HEAD")
    artifact = _record_repo_path(record.get("artifact_path"), repo_root, "artifact_path")
    manifest = _record_repo_path(record.get("manifest_path"), repo_root, "manifest_path")
    if _sha256(manifest) != _digest(record, "manifest_sha256"):
        raise ValueError("legacy rollback manifest hash does not match")
    entries = _read_sha_manifest(manifest, artifact)
    if record.get("files") != entries:
        raise ValueError("legacy rollback file manifest does not match artifact")
    return record


def verify_failure_contract(evidence_path: Path) -> dict[str, Any]:
    evidence_path = Path(evidence_path)
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("failure-contract evidence must be an object")
    if payload.get("abort_failed") is not True:
        raise ValueError("evidence does not prove business Abort failed")
    if payload.get("sentinel_ran") is not True:
        raise ValueError("evidence does not prove sentinel ran after Abort")

    for field in (
        "base_metadata_sha256",
        "base_payload_sha256",
        "overlay_sha256",
        "probe_metadata_sha256",
    ):
        _digest(payload, field)

    probe_metadata_path = _path_from_evidence(
        evidence_path, payload.get("probe_metadata_path"), "probe_metadata_path"
    )
    if not probe_metadata_path.is_file():
        raise ValueError(f"probe metadata does not exist: {probe_metadata_path}")
    if _sha256(probe_metadata_path) != payload["probe_metadata_sha256"].lower():
        raise ValueError("probe metadata hash does not match evidence")

    metadata = json.loads(probe_metadata_path.read_text(encoding="utf-8"))
    if not isinstance(metadata, dict):
        raise ValueError("probe metadata must be an object")
    for field in ("base_metadata_sha256", "base_payload_sha256", "overlay_sha256"):
        if metadata.get(field) != payload[field].lower():
            raise ValueError(f"probe metadata {field} does not match evidence")

    base_metadata_path_value = payload.get("base_metadata_path")
    if base_metadata_path_value is not None:
        base_metadata_path = _path_from_evidence(
            evidence_path, base_metadata_path_value, "base_metadata_path"
        )
        if not base_metadata_path.is_file():
            raise ValueError(f"base metadata does not exist: {base_metadata_path}")
        if _sha256(base_metadata_path) != payload["base_metadata_sha256"].lower():
            raise ValueError("base metadata hash does not match evidence")

    return payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--failure-contract", type=Path)
    inputs.add_argument("--root", type=Path)
    inputs.add_argument("--write-legacy-rollback", type=Path)
    parser.add_argument("--batch", choices=tuple(_BATCH_IDS))
    parser.add_argument("--require-all-tasks", action="store_true")
    parser.add_argument("--require-full-preset", action="store_true")
    parser.add_argument("--require-manual-all", action="store_true")
    parser.add_argument("--write-summary", type=Path)
    parser.add_argument("--tag")
    parser.add_argument("--artifact", type=Path)
    parser.add_argument("--manifest", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.write_legacy_rollback is not None:
        if (
            args.failure_contract is not None
            or args.root is not None
            or args.write_summary is not None
            or args.batch is not None
            or any(
                (
                    args.require_all_tasks,
                    args.require_full_preset,
                    args.require_manual_all,
                )
            )
        ):
            parser.error("legacy rollback cannot be combined with evidence verification")
        if args.tag is None or args.artifact is None or args.manifest is None:
            parser.error("--write-legacy-rollback requires --tag, --artifact and --manifest")
        evidence = write_legacy_rollback(
            args.write_legacy_rollback,
            tag=args.tag,
            artifact=args.artifact,
            manifest=args.manifest,
        )
        print(json.dumps(evidence, ensure_ascii=False, indent=2))
        return 0
    if args.failure_contract is not None:
        if args.batch is not None or any(
            (
                args.require_all_tasks,
                args.require_full_preset,
                args.require_manual_all,
            )
        ) or args.write_summary is not None or any(
            (args.tag is not None, args.artifact is not None, args.manifest is not None)
        ):
            parser.error("full-candidate flags require --root")
        evidence = verify_failure_contract(args.failure_contract)
    else:
        full_flags = (
            args.require_all_tasks,
            args.require_full_preset,
            args.require_manual_all,
        )
        if any((args.tag is not None, args.artifact is not None, args.manifest is not None)):
            parser.error("legacy rollback options require --write-legacy-rollback")
        if args.batch is not None and any(full_flags):
            parser.error("--batch cannot be combined with full-candidate flags")
        if args.batch is not None and args.write_summary is not None:
            parser.error("--write-summary requires full-candidate verification")
        if args.batch is not None and any(
            (args.tag is not None, args.artifact is not None, args.manifest is not None)
        ):
            parser.error("legacy rollback options require --write-legacy-rollback")
        if args.batch is not None:
            evidence = verify_batch(args.root, batch=args.batch)
        elif all(full_flags):
            evidence = (
                write_candidate_summary(args.write_summary, args.root)
                if args.write_summary is not None
                else verify_full_candidate(args.root)
            )
        elif any(full_flags):
            parser.error(
                "full-candidate verification requires --require-all-tasks, "
                "--require-full-preset and --require-manual-all"
            )
        else:
            parser.error("--root requires --batch or all full-candidate flags")
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "BATCH_A_IDS",
    "BATCH_B_IDS",
    "MFW_FINAL_CANONICAL_IDS",
    "MFW_FULL_TASK_ORDER",
    "main",
    "verify_batch",
    "verify_candidate_summary",
    "verify_full_candidate",
    "verify_failure_contract",
    "verify_legacy_rollback",
    "write_legacy_rollback",
    "write_candidate_summary",
]
