from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from tools.mfw_live_acceptance import (
    SUCCESS_SIGNAL_POSTCONDITIONS,
    begin_acceptance,
    finish_acceptance,
    finish_partial_acceptance,
    formal_task_order,
)

ROOT = Path(__file__).parents[1]
ENTRIES = {
    "GAME_START": "启动-游戏启动",
    "MAIL_REWARD_DAILY": "邮件奖励-任务入口",
    "SHOP_FREE_GIFT_DAILY": "商店免费礼包-任务入口",
}


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def candidate(tmp_path: Path) -> Path:
    candidate = tmp_path / "candidate"
    write_json(
        candidate / "interface.json",
        {
            "import": [
                "tasks/游戏启动.json",
                "tasks/日常/MAIL_REWARD_DAILY.json",
                "tasks/日常/SHOP_FREE_GIFT_DAILY.json",
            ]
        },
    )
    for task_id, entry in ENTRIES.items():
        relative = (
            Path("tasks/游戏启动.json")
            if task_id == "GAME_START"
            else Path(f"tasks/日常/{task_id}.json")
        )
        write_json(
            candidate / relative,
            {"task": [{"name": task_id, "entry": entry, "default_check": True}]},
        )
    executable = candidate / "MFW"
    executable.parent.mkdir(parents=True, exist_ok=True)
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o755)
    debug = candidate / "debug"
    debug.mkdir()
    (debug / "gui.log").write_text("", encoding="utf-8")
    (debug / "maafw.log").write_text("", encoding="utf-8")
    return candidate


def append_run(
    candidate: Path,
    task_ids: tuple[str, ...],
    statuses: dict[str, str],
    *,
    write_results: bool = True,
    postconditions: dict[str, str] | None = None,
    native_states: dict[str, str] | None = None,
) -> None:
    with (candidate / "debug/gui.log").open("a", encoding="utf-8") as gui:
        for task_id in task_ids:
            gui.write(f"任务 '{task_id}' 的执行信息: {{}}\n")
    with (candidate / "debug/maafw.log").open("a", encoding="utf-8") as maafw:
        for task_id in task_ids:
            state = (native_states or {}).get(task_id, "Succeeded")
            maafw.write(
                f"[msg=Tasker.Task.{state}] "
                f'[details={{"entry":"{ENTRIES[task_id]}"}}]\n'
            )
    if not write_results:
        return
    run_number = len(list((candidate / "debug").glob("mfw-*"))) + 1
    for task_id, status in statuses.items():
        signal = (postconditions or {}).get(task_id)
        if signal is None:
            signal = next(
                iter(SUCCESS_SIGNAL_POSTCONDITIONS.get(task_id, ())),
                f"{task_id}.terminal",
            )
        write_json(
            candidate / f"debug/mfw-{run_number}/{task_id}/result.json",
            {
                "schema_version": 1,
                "task_id": task_id,
                "status": status,
                "postcondition": signal,
                "error_code": "TEST_FAILURE" if status == "failed" else None,
            },
        )


def test_formal_order_comes_from_imported_declarations(candidate: Path) -> None:
    assert formal_task_order(candidate) == (
        "GAME_START",
        "MAIL_REWARD_DAILY",
        "SHOP_FREE_GIFT_DAILY",
    )


def test_begin_can_require_exact_saved_profile_order(candidate: Path) -> None:
    write_json(
        candidate / "config/configs/c_batch.json",
        {
            "name": "live-batch",
            "tasks": [
                {"name": "PreTask", "is_checked": True},
                {"name": "Controller", "is_checked": True},
                {"name": "Resource", "is_checked": True},
                {"name": "GAME_START", "is_checked": True},
                {"name": "MAIL_REWARD_DAILY", "is_checked": True},
            ],
        },
    )
    write_json(candidate / "config/multi_config.json", {"config_list": ["c_batch"]})
    ticket = begin_acceptance(
        candidate,
        "worker:mail",
        "MAIL_REWARD_DAILY",
        profile_name="live-batch",
    )
    assert load_json(ticket)["profile_name"] == "live-batch"


def test_martial_acceptance_accepts_claimed_or_no_successful_breakthrough_signal() -> None:
    assert SUCCESS_SIGNAL_POSTCONDITIONS[
        "MARTIAL_STUDY_BREAKTHROUGH_DAILY"
    ] == frozenset(
        {
            "martial.no_successful_breakthrough_to_claim",
            "martial.claim_flow_completed",
        }
    )


def test_equipment_decompose_acceptance_requires_confirmed_decomposition() -> None:
    assert SUCCESS_SIGNAL_POSTCONDITIONS["EQUIPMENT_DECOMPOSE_DAILY"] == frozenset(
        {"equipment.decomposition_confirmed"}
    )


def test_pair_acceptance_requires_exact_order_and_fresh_success(candidate: Path) -> None:
    ticket = begin_acceptance(candidate, "worker:mail", "MAIL_REWARD_DAILY")
    append_run(
        candidate,
        ("GAME_START", "MAIL_REWARD_DAILY"),
        {"MAIL_REWARD_DAILY": "success"},
    )
    summary = finish_acceptance(ticket)
    assert summary.is_file()
    assert load_json(summary)["expected_tasks"] == ["GAME_START", "MAIL_REWARD_DAILY"]
    evidence_result = Path(load_json(summary)["tasks"]["MAIL_REWARD_DAILY"]["result_path"])
    assert load_json(evidence_result)["native_terminal_verified"] is True
    assert load_json(evidence_result)["evidence_origin"] == "mfw_live_acceptance"
    assert load_json(evidence_result)["acceptance_result"] == "passed"


def test_partial_acceptance_archives_first_failure_and_next_tasks(candidate: Path) -> None:
    ticket = begin_acceptance(
        candidate,
        "worker:batch",
        None,
        selected_tasks=("MAIL_REWARD_DAILY", "SHOP_FREE_GIFT_DAILY"),
    )
    append_run(
        candidate,
        ("GAME_START", "MAIL_REWARD_DAILY"),
        {"MAIL_REWARD_DAILY": "failed"},
        native_states={"MAIL_REWARD_DAILY": "Failed"},
    )

    summary = finish_partial_acceptance(ticket)
    payload = load_json(summary)
    assert payload["result"] == "partial"
    assert payload["first_failed_task"] == "MAIL_REWARD_DAILY"
    assert payload["unrun_after_first_failure"] == ["SHOP_FREE_GIFT_DAILY"]
    assert payload["next_tasks"] == ["SHOP_FREE_GIFT_DAILY"]
    assert (summary.parent / "partial.json").is_file()


def test_partial_acceptance_classifies_game_start_block_without_business_failure(
    candidate: Path,
) -> None:
    ticket = begin_acceptance(
        candidate,
        "worker:batch",
        None,
        selected_tasks=("MAIL_REWARD_DAILY", "SHOP_FREE_GIFT_DAILY"),
    )
    append_run(
        candidate,
        ("GAME_START",),
        {},
        write_results=False,
        native_states={"GAME_START": "Failed"},
    )

    summary = finish_partial_acceptance(ticket)
    payload = load_json(summary)
    assert payload["failure_kind"] == "startup_blocked"
    assert payload["first_failed_task"] == "GAME_START"
    assert payload["next_tasks"] == ["MAIL_REWARD_DAILY", "SHOP_FREE_GIFT_DAILY"]
    assert payload["task_outcomes"]["MAIL_REWARD_DAILY"]["result"] is None
    assert payload["task_outcomes"]["SHOP_FREE_GIFT_DAILY"]["result"] is None


def test_partial_acceptance_continues_after_game_start_recovery_exhaustion(
    candidate: Path,
) -> None:
    ticket = begin_acceptance(
        candidate,
        "worker:batch",
        None,
        selected_tasks=("MAIL_REWARD_DAILY", "SHOP_FREE_GIFT_DAILY"),
    )
    append_run(
        candidate,
        ("GAME_START",),
        {},
        write_results=False,
        native_states={"GAME_START": "Failed"},
    )
    with (candidate / "debug/maafw.log").open("a", encoding="utf-8") as maafw:
        maafw.write("公共-通用-启动恢复-耗尽 GAME_START_RECOVERY_EXHAUSTED\n")

    summary = finish_partial_acceptance(ticket)
    payload = load_json(summary)
    assert payload["failure_kind"] == "startup_recovery_failed"
    assert payload["startup_recovery_failed"] is True
    assert payload["first_failed_task"] == "GAME_START"
    assert payload["next_tasks"] == ["MAIL_REWARD_DAILY", "SHOP_FREE_GIFT_DAILY"]
    assert payload["task_outcomes"]["MAIL_REWARD_DAILY"]["result"] is None
    assert payload["task_outcomes"]["SHOP_FREE_GIFT_DAILY"]["result"] is None


def test_selected_batch_records_the_selector_snapshot_and_keeps_game_start(
    candidate: Path,
) -> None:
    ticket = begin_acceptance(
        candidate,
        "worker:batch",
        None,
        selected_tasks=("MAIL_REWARD_DAILY",),
        selection={
            "scope_mode": "full",
            "failed_task": "MAIL_REWARD_DAILY",
            "unrun_after_first_failure": [],
            "selected_tasks": ["MAIL_REWARD_DAILY"],
        },
    )
    ticket_payload = load_json(ticket)
    assert ticket_payload["expected_tasks"] == ["GAME_START", "MAIL_REWARD_DAILY"]
    assert ticket_payload["selection"]["failed_task"] == "MAIL_REWARD_DAILY"


def test_selection_snapshot_controls_the_batch_and_rejects_mismatch(
    candidate: Path,
) -> None:
    selection = {
        "scope_mode": "full",
        "selected_tasks": ["MAIL_REWARD_DAILY"],
        "pending_tasks": ["MAIL_REWARD_DAILY"],
    }

    ticket = begin_acceptance(
        candidate,
        "worker:batch",
        None,
        selection=selection,
    )
    ticket_payload = load_json(ticket)
    assert ticket_payload["expected_tasks"] == ["GAME_START", "MAIL_REWARD_DAILY"]

    with pytest.raises(ValueError, match="do not match"):
        begin_acceptance(
            candidate,
            "worker:batch",
            None,
            selected_tasks=("SHOP_FREE_GIFT_DAILY",),
            selection=selection,
        )


def test_empty_selection_does_not_create_a_game_start_only_batch(
    candidate: Path,
) -> None:
    with pytest.raises(ValueError, match="non-empty string list"):
        begin_acceptance(
            candidate,
            "worker:batch",
            None,
            selection={"scope_mode": "full", "selected_tasks": []},
        )


def test_acceptance_requires_a_task_specific_success_signal(candidate: Path) -> None:
    ticket = begin_acceptance(candidate, "worker:mail", "MAIL_REWARD_DAILY")
    append_run(
        candidate,
        ("GAME_START", "MAIL_REWARD_DAILY"),
        {"MAIL_REWARD_DAILY": "success"},
        postconditions={"MAIL_REWARD_DAILY": "MAIL_REWARD_DAILY.terminal"},
    )
    with pytest.raises(ValueError, match="success signal"):
        finish_acceptance(ticket)


def test_pair_acceptance_reads_logs_from_start_after_runtime_truncation(candidate: Path) -> None:
    (candidate / "debug/gui.log").write_text("old gui\n" * 128, encoding="utf-8")
    (candidate / "debug/maafw.log").write_text("old maafw\n" * 128, encoding="utf-8")
    ticket = begin_acceptance(candidate, "worker:mail", "MAIL_REWARD_DAILY")

    (candidate / "debug/gui.log").write_text("", encoding="utf-8")
    (candidate / "debug/maafw.log").write_text("", encoding="utf-8")
    append_run(
        candidate,
        ("GAME_START", "MAIL_REWARD_DAILY"),
        {"MAIL_REWARD_DAILY": "success"},
    )

    summary = finish_acceptance(ticket)
    assert summary.is_file()


@pytest.mark.parametrize("status", ["running", "failed"])
def test_pair_acceptance_rejects_nonterminal_business_result(
    candidate: Path, status: str
) -> None:
    ticket = begin_acceptance(candidate, "worker:mail", "MAIL_REWARD_DAILY")
    append_run(
        candidate,
        ("GAME_START", "MAIL_REWARD_DAILY"),
        {"MAIL_REWARD_DAILY": status},
    )
    with pytest.raises(ValueError, match=f"status={status}"):
        finish_acceptance(ticket)


def test_pair_acceptance_rejects_a_result_that_existed_before_begin(candidate: Path) -> None:
    append_run(
        candidate,
        ("GAME_START", "MAIL_REWARD_DAILY"),
        {"MAIL_REWARD_DAILY": "success"},
    )
    ticket = begin_acceptance(candidate, "worker:mail", "MAIL_REWARD_DAILY")
    append_run(
        candidate,
        ("GAME_START", "MAIL_REWARD_DAILY"),
        {},
        write_results=False,
    )
    with pytest.raises(ValueError, match="fresh result"):
        finish_acceptance(ticket)


def test_pair_acceptance_rejects_extra_selected_task(candidate: Path) -> None:
    ticket = begin_acceptance(candidate, "worker:mail", "MAIL_REWARD_DAILY")
    append_run(
        candidate,
        ("GAME_START", "MAIL_REWARD_DAILY", "SHOP_FREE_GIFT_DAILY"),
        {
            "MAIL_REWARD_DAILY": "success",
            "SHOP_FREE_GIFT_DAILY": "success",
        },
    )
    with pytest.raises(ValueError, match="exact task order"):
        finish_acceptance(ticket)


def test_all_acceptance_requires_every_imported_business_result(candidate: Path) -> None:
    ticket = begin_acceptance(candidate, "integrator", None)
    append_run(
        candidate,
        ("GAME_START", "MAIL_REWARD_DAILY", "SHOP_FREE_GIFT_DAILY"),
        {
            "MAIL_REWARD_DAILY": "success",
            "SHOP_FREE_GIFT_DAILY": "success",
        },
    )
    assert finish_acceptance(ticket).is_file()


def test_all_acceptance_accepts_mail_already_complete(candidate: Path) -> None:
    ticket = begin_acceptance(candidate, "integrator", None)
    append_run(
        candidate,
        ("GAME_START", "MAIL_REWARD_DAILY", "SHOP_FREE_GIFT_DAILY"),
        {
            "MAIL_REWARD_DAILY": "already_complete",
            "SHOP_FREE_GIFT_DAILY": "success",
        },
        postconditions={"MAIL_REWARD_DAILY": "mail.empty"},
    )
    summary = finish_acceptance(ticket)
    payload = load_json(summary)
    assert payload["tasks"]["MAIL_REWARD_DAILY"]["status"] == "already_complete"
    assert payload["tasks"]["MAIL_REWARD_DAILY"]["postcondition"] == "mail.empty"


@pytest.mark.parametrize("status", ["completed"])
def test_all_acceptance_rejects_non_terminal_business_states(
    candidate: Path, status: str
) -> None:
    ticket = begin_acceptance(candidate, "integrator", None)
    append_run(
        candidate,
        ("GAME_START", "MAIL_REWARD_DAILY", "SHOP_FREE_GIFT_DAILY"),
        {"MAIL_REWARD_DAILY": status, "SHOP_FREE_GIFT_DAILY": "success"},
    )
    with pytest.raises(ValueError, match=f"status={status}"):
        finish_acceptance(ticket)


def test_all_acceptance_can_exclude_one_declared_business_task(candidate: Path) -> None:
    ticket = begin_acceptance(
        candidate,
        "integrator",
        None,
        ("SHOP_FREE_GIFT_DAILY",),
    )
    append_run(
        candidate,
        ("GAME_START", "MAIL_REWARD_DAILY"),
        {"MAIL_REWARD_DAILY": "success"},
    )
    summary = finish_acceptance(ticket)
    assert load_json(summary)["expected_tasks"] == [
        "GAME_START",
        "MAIL_REWARD_DAILY",
    ]


@pytest.mark.parametrize("excluded", [("GAME_START",), ("NOT_A_TASK",)])
def test_all_acceptance_rejects_invalid_excluded_tasks(
    candidate: Path, excluded: tuple[str, ...]
) -> None:
    with pytest.raises(ValueError, match="unknown excluded business task"):
        begin_acceptance(candidate, "integrator", None, excluded)


def test_pair_acceptance_rejects_excluded_tasks(candidate: Path) -> None:
    with pytest.raises(ValueError, match="pair acceptance cannot exclude"):
        begin_acceptance(
            candidate,
            "worker:mail",
            "MAIL_REWARD_DAILY",
            ("SHOP_FREE_GIFT_DAILY",),
        )


def test_game_start_only_acceptance_does_not_require_a_business_task(
    candidate: Path,
) -> None:
    ticket = begin_acceptance(candidate, "worker:game-start", "GAME_START")
    append_run(candidate, ("GAME_START",), {})

    summary = finish_acceptance(ticket)
    payload = load_json(summary)
    assert payload["expected_tasks"] == ["GAME_START"]
    assert payload["tasks"] == {}



def materialize_repository_candidate_shell(tmp_path: Path) -> Path:
    candidate = tmp_path / "repository-candidate"
    interface = json.loads(
        (ROOT / "assets/interface.json").read_text(encoding="utf-8")
    )
    write_json(candidate / "interface.json", interface)
    for relative in interface["import"]:
        source = ROOT / "assets" / relative
        destination = candidate / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    executable = candidate / "MFW"
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o755)
    (candidate / "debug").mkdir()
    return candidate


def test_repository_interface_exposes_the_22_expected_repair_pairs(
    tmp_path: Path,
) -> None:
    candidate = materialize_repository_candidate_shell(tmp_path)
    assert formal_task_order(candidate) == (
        "GAME_START",
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
        "EQUIPMENT_DECOMPOSE_DAILY",
        "DUNGEON_SWEEP_DAILY",
        "JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY",
        "RING_CHALLENGE_DAILY",
        "BREAK_ARRAY_MARTIAL_DAILY",
        "GUILD_ACTIVITY_CHALLENGE_DAILY",
        "GUILD_AFFAIRS_DAILY",
        "GUILD_DONATION_DAILY",
        "DAILY_TASK_REWARD_CLAIM_DAILY",
        "BATTLE_PASS_REWARD_DAILY",
    )
