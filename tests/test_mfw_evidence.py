from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from agent.custom.support.policy import TASK_POLICIES
from tools.verify_mfw_evidence import (
    BATCH_A_IDS,
    BATCH_B_IDS,
    MFW_FINAL_CANONICAL_IDS,
    MFW_FULL_TASK_ORDER,
    verify_batch,
    verify_full_candidate,
)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resource_actions(task_id: str) -> list[dict[str, object]]:
    if task_id == "BUY_TEA_DAILY":
        return [
            {
                "action_id": "buy_tea",
                "count": 1,
                "resource_id": "文",
                "observed_amount": 500,
                "budget_amount": 500,
                "ocr_text": "文 500",
            }
        ]
    if task_id == "SPEND_CONDENSATE_DAILY":
        return [
            {
                "action_id": "buy_yanwu_currency_max",
                "count": 1,
                "resource_id": "凝晶",
                "observed_amount": 50_000,
                "budget_amount": 50_000,
                "ocr_text": "凝晶 50000",
            },
            {
                "action_id": "buy_yunzhou_currency_max",
                "count": 1,
                "resource_id": "凝晶",
                "observed_amount": 50_000,
                "budget_amount": 50_000,
                "ocr_text": "凝晶 50000",
            },
        ]
    if task_id == "EAT_STAMINA_FOOD_DAILY":
        return [
            {
                "action_id": "eat_longjing_shrimp",
                "count": 6,
                "resource_id": "龙井虾仁",
                "observed_amount": 6,
                "budget_amount": 1,
                "ocr_text": "龙井虾仁 6",
            }
        ]
    if task_id == "JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY":
        return [
            {
                "action_id": "buy_stamina_once",
                "count": 1,
                "resource_id": "紫色魂玉",
                "observed_amount": 10,
                "budget_amount": 1,
                "ocr_text": "紫色魂玉 10",
            },
            {
                "action_id": "start_jianlin_battle",
                "count": 1,
                "resource_id": "体力",
                "observed_amount": 120,
                "budget_amount": 120,
                "ocr_text": "体力 120",
            },
        ]
    policy = TASK_POLICIES[task_id]
    action_id = next(iter(policy.action_caps))
    return [{"action_id": action_id, "count": 1}]


def _write_task_evidence(root: Path, task_id: str, build_sha: str) -> None:
    actions = _resource_actions(task_id)
    action_counts: dict[str, int] = {}
    resource_totals = {resource_id: 0 for resource_id in TASK_POLICIES[task_id].resource_caps}
    for index, action in enumerate(actions):
        action_id = str(action["action_id"])
        count = int(action["count"])
        action_counts[action_id] = action_counts.get(action_id, 0) + count
        for field, suffix in (
            ("before_image", "before.png"),
            ("after_image", "after.png"),
            ("trace_path", "trace.json"),
        ):
            path = root / f"{task_id}-{index}-{suffix}"
            path.write_bytes(b"evidence")
            action[field] = path.name
        if "resource_id" in action:
            resource_id = str(action["resource_id"])
            resource_totals[resource_id] += int(action["budget_amount"]) * count

    metadata_path = root / f"{task_id}-metadata.json"
    _write_json(metadata_path, {"task_id": task_id, "build_sha256": build_sha})
    log_path = root / f"{task_id}.log"
    log_path.write_text(f"run {task_id}\n", encoding="utf-8")
    rerun_log_path = root / f"{task_id}-rerun.log"
    rerun_log_path.write_text(f"rerun {task_id}\n", encoding="utf-8")

    rerun_counts = {action_id: 0 for action_id in action_counts}
    _write_json(
        root / f"{task_id}.json",
        {
            "schema_version": 1,
            "task_id": task_id,
            "status": "passed",
            "candidate": {
                "build_sha256": build_sha,
                "metadata_path": metadata_path.name,
                "metadata_sha256": _sha256(metadata_path),
            },
            "run_id": f"run-{task_id}",
            "log_path": log_path.name,
            "start_page": "home",
            "controller_backend": "ScreenCaptureKit",
            "terminal_status": "success",
            "action_counts": action_counts,
            "actions": actions,
            "resource_totals": resource_totals,
            "rerun": {
                "run_id": f"rerun-{task_id}",
                "log_path": rerun_log_path.name,
                "terminal_status": "already_complete",
                "action_counts": rerun_counts,
                "duplicate_side_effects": [],
            },
        },
    )


def _write_valid_task_evidence_set(
    root: Path, task_ids: tuple[str, ...] | list[str], build_sha: str = "a" * 64
) -> None:
    for task_id in task_ids:
        _write_task_evidence(root, task_id, build_sha)


def _write_sequence(root: Path, batch: str, task_ids: list[str], build_sha: str = "a" * 64) -> None:
    runs = []
    for index in range(2):
        runs.append(
            {
                "run_id": f"sequence-{batch}-{index}",
                "task_order": task_ids,
                "events": [
                    {
                        "task_id": task_id,
                        "started": True,
                        "terminal_status": "success",
                    }
                    for task_id in task_ids
                ],
            }
        )
    _write_json(
        root / f"batch-{batch}-sequence.json",
        {
            "schema_version": 1,
            "batch": batch,
            "build_sha256": build_sha,
            "runs": runs,
            "abort_isolation": {
                "injected_task_id": task_ids[0],
                "following_task_id": task_ids[1],
                "abort_status": "failed",
                "following_started": True,
                "following_terminal_status": "success",
            },
        },
    )


def _write_full_candidate(root: Path, build_sha: str = "a" * 64) -> None:
    metadata_path = root / "mfw-full-candidate-build-metadata.json"
    _write_json(
        metadata_path,
        {
            "mja_commit": "full-candidate-commit",
            "target": "macos-aarch64",
            "mfw": {"repo": "MFW", "tag": "v-test", "sha256": "c" * 64},
            "maafw": {"repo": "Maa", "tag": "v-test", "sha256": "d" * 64},
            "payload_sha256": "b" * 64,
            "build_sha256": build_sha,
        },
    )
    metadata_sha = _sha256(metadata_path)
    candidate = {
        "install_path": "install/mfw-full-candidate",
        "build_sha256": build_sha,
        "payload_sha256": "b" * 64,
        "metadata_path": metadata_path.name,
        "metadata_sha256": metadata_sha,
    }

    for task_id in MFW_FINAL_CANONICAL_IDS:
        _write_task_evidence(root, task_id, build_sha)
        evidence_path = root / f"{task_id}.json"
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))
        payload["candidate"] = candidate.copy()
        payload["evidence_scope"] = "full-candidate"
        payload["full_candidate"] = {
            "first_entry": "full-preset",
            "rerun_entry": "manual-all",
        }
        payload["rerun"]["same_day"] = True
        payload["rerun"]["resource_totals"] = {
            resource_id: 0 for resource_id in TASK_POLICIES[task_id].resource_caps
        }
        _write_json(evidence_path, payload)

    statuses = {
        task_id: json.loads((root / f"{task_id}.json").read_text(encoding="utf-8"))
        for task_id in MFW_FINAL_CANONICAL_IDS
    }

    def write_entry(entry_name: str) -> None:
        log_path = root / f"{entry_name}.log"
        log_path.write_text(entry_name, encoding="utf-8")
        is_first = entry_name == "full-preset"
        events = [
            {
                "task_id": "GAME_START",
                "started": True,
                "terminal_status": "success",
            }
        ]
        for task_id in MFW_FINAL_CANONICAL_IDS:
            task = statuses[task_id]
            record = task if is_first else task["rerun"]
            event = {
                "task_id": task_id,
                "started": True,
                "terminal_status": record["terminal_status"],
                "run_id": task["run_id"] if is_first else record["run_id"],
            }
            if event["terminal_status"] == "not_eligible":
                event["reason"] = (
                    task.get("reason") if is_first else record.get("reason")
                ) or "not eligible in fixture"
            events.append(event)
        _write_json(
            root / f"{entry_name}.json",
            {
                "schema_version": 1,
                "entry": entry_name,
                "controller_backend": "ScreenCaptureKit",
                "candidate": candidate.copy(),
                "task_order": list(MFW_FULL_TASK_ORDER),
                "runs": [
                    {
                        "run_id": f"{entry_name}-run",
                        "log_path": log_path.name,
                        "task_order": list(MFW_FULL_TASK_ORDER),
                        "events": events,
                    }
                ],
            },
        )

    write_entry("full-preset")
    write_entry("manual-all")

    sequence_runs = []
    for entry_name, is_first in (("full-preset", True), ("manual-all", False)):
        log_path = root / f"batch-c-{entry_name}.log"
        log_path.write_text(entry_name, encoding="utf-8")
        events = [
            {
                "task_id": "GAME_START",
                "started": True,
                "terminal_status": "success",
            }
        ]
        for task_id in MFW_FINAL_CANONICAL_IDS:
            task = statuses[task_id]
            record = task if is_first else task["rerun"]
            events.append(
                {
                    "task_id": task_id,
                    "started": True,
                    "terminal_status": record["terminal_status"],
                }
            )
        sequence_runs.append(
            {
                "entry": entry_name,
                "run_id": f"batch-c-{entry_name}",
                "log_path": log_path.name,
                "task_order": list(MFW_FULL_TASK_ORDER),
                "events": events,
            }
        )
    _write_json(
        root / "batch-c-sequence.json",
        {
            "schema_version": 1,
            "batch": "c",
            "controller_backend": "ScreenCaptureKit",
            "candidate": candidate.copy(),
            "task_order": list(MFW_FULL_TASK_ORDER),
            "runs": sequence_runs,
        },
    )

    probe_metadata_path = root / "full-probe-metadata.json"
    probe_payload = {
        "base_metadata_sha256": metadata_sha,
        "base_payload_sha256": "b" * 64,
        "overlay_sha256": "c" * 64,
    }
    _write_json(probe_metadata_path, probe_payload)
    abort_log_path = root / "full-business-abort.log"
    abort_log_path.write_text("abort then sentinel", encoding="utf-8")
    _write_json(
        root / "full-business-abort.json",
        {
            "schema_version": 1,
            "controller_backend": "ScreenCaptureKit",
            "candidate": candidate.copy(),
            "run_id": "full-business-abort-run",
            "log_path": abort_log_path.name,
            "abort_failed": True,
            "abort_status": "failed",
            "sentinel_ran": True,
            "following_started": True,
            "following_terminal_status": "success",
            "injected_task_id": "MJA_PROBE_BUSINESS_FAILURE",
            "following_task_id": "MJA_PROBE_SENTINEL",
            **probe_payload,
            "probe_metadata_path": probe_metadata_path.name,
            "probe_metadata_sha256": _sha256(probe_metadata_path),
        },
    )

    infra_log_path = root / "full-infrastructure-stop.log"
    infra_log_path.write_text("controller disconnected", encoding="utf-8")
    stop_index = MFW_FULL_TASK_ORDER.index("MAIL_REWARD_DAILY")
    _write_json(
        root / "full-infrastructure-stop.json",
        {
            "schema_version": 1,
            "controller_backend": "ScreenCaptureKit",
            "candidate": candidate.copy(),
            "run_id": "full-infrastructure-stop-run",
            "log_path": infra_log_path.name,
            "terminal_status": "infrastructure_stopped",
            "queue_stopped": True,
            "stop_reason": "controller_disconnected",
            "task_order": [
                "GAME_START",
                "MAIL_REWARD_DAILY",
                "SHOP_FREE_GIFT_DAILY",
            ],
            "stopped_before_task_id": "MAIL_REWARD_DAILY",
            "started_task_ids": list(MFW_FULL_TASK_ORDER[:stop_index]),
            "not_started_task_ids": list(MFW_FULL_TASK_ORDER[stop_index:]),
        },
    )


def test_batch_b_requires_shared_build_and_resource_totals(tmp_path: Path) -> None:
    task_ids = list(BATCH_A_IDS) + list(BATCH_B_IDS)
    _write_valid_task_evidence_set(tmp_path, task_ids)
    _write_sequence(tmp_path, "b", [
        "MAIL_REWARD_DAILY",
        "SHOP_FREE_GIFT_DAILY",
        "BUY_TEA_DAILY",
        "FREE_APPRAISAL_DAILY",
        "TRIAL_SWORD_DAILY",
        "HERO_DISPATCH_DAILY",
        "COLLECTION_DEPLOYMENT_DAILY",
        "WEEKLY_FREE_GIFT_MONDAY",
        "SPEND_CONDENSATE_DAILY",
        "EAT_STAMINA_FOOD_DAILY",
        "JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY",
        "DAILY_TASK_REWARD_CLAIM_DAILY",
        "BATTLE_PASS_REWARD_DAILY",
    ])

    result = verify_batch(tmp_path, batch="b")

    assert result["batch"] == "b"
    assert result["task_ids"] == [
        "MAIL_REWARD_DAILY",
        "SHOP_FREE_GIFT_DAILY",
        "BUY_TEA_DAILY",
        "FREE_APPRAISAL_DAILY",
        "TRIAL_SWORD_DAILY",
        "HERO_DISPATCH_DAILY",
        "COLLECTION_DEPLOYMENT_DAILY",
        "WEEKLY_FREE_GIFT_MONDAY",
        "SPEND_CONDENSATE_DAILY",
        "EAT_STAMINA_FOOD_DAILY",
        "JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY",
        "DAILY_TASK_REWARD_CLAIM_DAILY",
        "BATTLE_PASS_REWARD_DAILY",
    ]


def test_batch_a_requires_sequence_evidence(tmp_path: Path) -> None:
    _write_valid_task_evidence_set(tmp_path, BATCH_A_IDS)

    with pytest.raises(ValueError, match="batch-a-sequence"):
        verify_batch(tmp_path, batch="a")


def test_batch_rejects_different_candidate_builds(tmp_path: Path) -> None:
    _write_valid_task_evidence_set(tmp_path, list(BATCH_A_IDS))
    evidence_path = tmp_path / "SHOP_FREE_GIFT_DAILY.json"
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    payload["candidate"]["build_sha256"] = "b" * 64
    _write_json(evidence_path, payload)
    _write_sequence(tmp_path, "a", list(BATCH_A_IDS))

    with pytest.raises(ValueError, match="same build"):
        verify_batch(tmp_path, batch="a")


def test_task_rejects_missing_before_image(tmp_path: Path) -> None:
    _write_valid_task_evidence_set(tmp_path, list(BATCH_A_IDS))
    evidence_path = tmp_path / "MAIL_REWARD_DAILY.json"
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    payload["actions"][0]["before_image"] = "missing-before.png"
    _write_json(evidence_path, payload)

    with pytest.raises(ValueError, match="before_image"):
        verify_batch(tmp_path, batch="a")


def test_task_rejects_missing_resource_ocr(tmp_path: Path) -> None:
    _write_valid_task_evidence_set(tmp_path, list(BATCH_A_IDS) + list(BATCH_B_IDS))
    evidence_path = tmp_path / "BUY_TEA_DAILY.json"
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    payload["actions"][0]["ocr_text"] = "500"
    _write_json(evidence_path, payload)

    with pytest.raises(ValueError, match="does not name"):
        verify_batch(tmp_path, batch="b")


def test_rerun_rejects_duplicate_consumptive_action(tmp_path: Path) -> None:
    _write_valid_task_evidence_set(tmp_path, list(BATCH_A_IDS) + list(BATCH_B_IDS))
    evidence_path = tmp_path / "BUY_TEA_DAILY.json"
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    payload["rerun"]["action_counts"]["buy_tea"] = 1
    _write_json(evidence_path, payload)

    with pytest.raises(ValueError, match="consumptive"):
        verify_batch(tmp_path, batch="b")


def test_sequence_rejects_duplicate_task_order(tmp_path: Path) -> None:
    _write_valid_task_evidence_set(tmp_path, BATCH_A_IDS)
    _write_sequence(tmp_path, "a", list(BATCH_A_IDS))
    sequence_path = tmp_path / "batch-a-sequence.json"
    payload = json.loads(sequence_path.read_text(encoding="utf-8"))
    payload["runs"][1]["task_order"][1] = payload["runs"][1]["task_order"][0]
    _write_json(sequence_path, payload)

    with pytest.raises(ValueError, match="canonical order"):
        verify_batch(tmp_path, batch="a")


def test_full_candidate_requires_both_entries_and_failure_boundaries(
    tmp_path: Path,
) -> None:
    _write_full_candidate(tmp_path)

    result = verify_full_candidate(tmp_path)

    assert result["candidate"]["install_path"] == "install/mfw-full-candidate"
    assert result["task_ids"] == list(MFW_FINAL_CANONICAL_IDS)
    assert result["entries"]["full-preset"]["task_order"] == list(MFW_FULL_TASK_ORDER)
    assert result["entries"]["manual-all"]["task_order"] == list(MFW_FULL_TASK_ORDER)
    assert result["business_abort"]["following_task_id"] == "MJA_PROBE_SENTINEL"
    assert result["infrastructure_stop"]["stopped_before_task_id"] == "MAIL_REWARD_DAILY"


def test_full_candidate_rejects_duplicate_or_unexecuted_tasks(tmp_path: Path) -> None:
    _write_full_candidate(tmp_path)
    entry_path = tmp_path / "manual-all.json"
    payload = json.loads(entry_path.read_text(encoding="utf-8"))
    payload["task_order"].append("MAIL_REWARD_DAILY")
    _write_json(entry_path, payload)

    with pytest.raises(ValueError, match="exactly once"):
        verify_full_candidate(tmp_path)

    _write_full_candidate(tmp_path)
    evidence_path = tmp_path / "SHADOW_RUINS_DAILY.json"
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    payload.pop("run_id")
    _write_json(evidence_path, payload)

    with pytest.raises(ValueError, match="run_id"):
        verify_full_candidate(tmp_path)


def test_full_candidate_rejects_development_candidate_evidence(tmp_path: Path) -> None:
    _write_full_candidate(tmp_path)
    evidence_path = tmp_path / "MAIL_REWARD_DAILY.json"
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    payload["candidate"]["install_path"] = "install/mfw-hero-dispatch-release-candidate"
    _write_json(evidence_path, payload)

    with pytest.raises(ValueError, match="mfw-full-candidate"):
        verify_full_candidate(tmp_path)
