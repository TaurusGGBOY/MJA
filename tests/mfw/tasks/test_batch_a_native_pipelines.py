from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]

TASKS: tuple[tuple[str, str, str], ...] = (
    ("MAIL_REWARD_DAILY", "日常/MAIL_REWARD_DAILY.json", "daily/mail_reward_daily.json"),
    ("SHOP_FREE_GIFT_DAILY", "日常/SHOP_FREE_GIFT_DAILY.json", "daily/shop_free_gift_daily.json"),
    ("FREE_APPRAISAL_DAILY", "日常/FREE_APPRAISAL_DAILY.json", "daily/free_appraisal_daily.json"),
    ("TRIAL_SWORD_DAILY", "日常/TRIAL_SWORD_DAILY.json", "daily/trial_sword_daily.json"),
    ("HERO_DISPATCH_DAILY", "日常/HERO_DISPATCH_DAILY.json", "daily/hero_dispatch_daily.json"),
    (
        "COLLECTION_DEPLOYMENT_DAILY",
        "日常/COLLECTION_DEPLOYMENT_DAILY.json",
        "daily/collection_deployment_daily.json",
    ),
    (
        "WEEKLY_FREE_GIFT_MONDAY",
        "日常/WEEKLY_FREE_GIFT_MONDAY.json",
        "daily/weekly_free_gift_monday.json",
    ),
    ("GUILD_AFFAIRS_DAILY", "日常/GUILD_AFFAIRS_DAILY.json", "daily/guild_affairs_daily.json"),
    ("GUILD_DONATION_DAILY", "日常/GUILD_DONATION_DAILY.json", "daily/guild_donation_daily.json"),
    (
        "DAILY_TASK_REWARD_CLAIM_DAILY",
        "日常/DAILY_TASK_REWARD_CLAIM_DAILY.json",
        "daily/daily_task_reward_claim_daily.json",
    ),
    (
        "BATTLE_PASS_REWARD_DAILY",
        "日常/BATTLE_PASS_REWARD_DAILY.json",
        "daily/battle_pass_reward_daily.json",
    ),
)

ALLOWED_EXTERNAL_NODES = {
    "公共-通用停止",
    "公共-通用中止",
    "启动-游戏启动",
    "公共-主页边界",
}


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict), path
    return payload


def _nodes(path: Path) -> dict[str, dict[str, Any]]:
    payload = _load(path)
    candidate = payload.get("pipeline", payload)
    assert isinstance(candidate, dict), path
    assert all(isinstance(name, str) and isinstance(node, dict) for name, node in candidate.items())
    return candidate


def _targets(node: Mapping[str, Any]) -> list[str]:
    result: list[str] = []
    for field in ("next", "on_error"):
        raw = node.get(field, [])
        values: Iterable[Any] = [raw] if isinstance(raw, str) else raw
        if not isinstance(values, Iterable):
            continue
        for value in values:
            if not isinstance(value, str):
                continue
            target = value
            while target.startswith("[") and "]" in target:
                target = target[target.index("]") + 1 :]
            result.append(target)
    return result


def _reachable(nodes: Mapping[str, Mapping[str, Any]], source: str, target: str) -> bool:
    pending = [source]
    visited: set[str] = set()
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)
        if current == target:
            return True
        pending.extend(_targets(nodes.get(current, {})))
    return False


def _reaches_failed_outcome(nodes: Mapping[str, Mapping[str, Any]], source: str) -> bool:
    pending = [source]
    visited: set[str] = set()
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)
        node = nodes.get(current, {})
        if (
            node.get("custom_action") == "RecordTaskOutcome"
            and node.get("custom_action_param", {}).get("status") == "failed"
        ):
            return True
        pending.extend(_targets(node))
    return False


def _is_bounded(node: Mapping[str, Any]) -> bool:
    return any(
        isinstance(node.get(field), int)
        and not isinstance(node.get(field), bool)
        and node[field] > 0
        for field in ("max_hit", "timeout")
    )


def _outcomes(nodes: Mapping[str, Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [
        node
        for node in nodes.values()
        if node.get("custom_action") == "RecordTaskOutcome"
    ]


def _outcome_pairs(nodes: Mapping[str, Mapping[str, Any]]) -> set[tuple[str, str]]:
    return {
        (
            node.get("custom_action_param", {}).get("status"),
            node.get("custom_action_param", {}).get("postcondition"),
        )
        for node in _outcomes(nodes)
    }


def test_batch_a_has_one_private_declaration_and_pipeline_entry_per_task() -> None:
    entries: set[str] = set()
    for task_id, declaration_name, pipeline_name in TASKS:
        declaration = _load(ROOT / "assets/tasks" / declaration_name)
        tasks = declaration.get("task")
        assert isinstance(tasks, list) and len(tasks) == 1
        task = tasks[0]
        assert task["name"] == task_id
        assert task["entry"].endswith("任务入口")
        assert task["default_check"] is True
        entries.add(task["entry"])

        nodes = _nodes(ROOT / "assets/resource/base/pipeline" / pipeline_name)
        assert task["entry"] in nodes
        assert any(
            any(marker in name for marker in ("页面", "主页", "面板"))
            and isinstance(node.get("recognition"), (str, dict))
            for name, node in nodes.items()
        ), task_id
        assert not any(
            any(char.isascii() and char.isalpha() for char in name)
            for name in nodes
        ), task_id

    assert len(entries) == len(TASKS)


def test_mail_claim_target_uses_live_ocr_instead_of_template_match() -> None:
    nodes = _nodes(ROOT / "assets/resource/base/pipeline/daily/mail_reward_daily.json")
    target = nodes["邮件奖励-邮件-领取-全部"]

    assert target["recognition"] == "OCR"
    assert target["expected"] == "全部领取"
    assert target["roi"] == [205, 525, 150, 65]
    assert "template" not in target
    assert "threshold" not in target


def test_mail_without_claim_button_is_an_already_complete_terminal_path() -> None:
    nodes = _nodes(ROOT / "assets/resource/base/pipeline/daily/mail_reward_daily.json")

    assert nodes["邮件奖励-领取"]["on_error"] == ["邮件奖励-已完成"]
    empty = nodes["邮件奖励-邮件-空"]
    assert empty["recognition"] == "OCR"
    assert empty["expected"] == ["删除已读", "除已读", "暂无可领取"]
    assert empty["roi"] == [300, 520, 900, 180]
    already = nodes["邮件奖励-已完成"]
    assert already["action"] == "Custom"
    assert already["custom_action"] == "RecordTaskOutcome"
    assert already["custom_action_param"]["status"] == "already_complete"
    assert already["custom_action_param"]["postcondition"] == "mail.empty"
    assert nodes["邮件奖励-已完成"]["next"] == ["邮件奖励-关闭"]
    assert nodes["邮件奖励-已完成"]["custom_action_param"][
        "defer_home_boundary"
    ] is True


def test_batch_a_page_and_known_drift_routes_are_finite() -> None:
    for task_id, declaration_name, pipeline_name in TASKS:
        nodes = _nodes(ROOT / "assets/resource/base/pipeline" / pipeline_name)
        declaration = _load(ROOT / "assets/tasks" / declaration_name)
        entry = declaration["task"][0]["entry"]
        assert _reachable(
            nodes,
            entry,
            next(
                name
                for name, node in nodes.items()
                if any(marker in name for marker in ("页面", "主页", "面板"))
                and isinstance(node.get("recognition"), (str, dict))
            ),
        )

        for name, node in nodes.items():
            action = node.get("custom_action")
            if action in {"BeginTask", "GuardedInput"}:
                assert _is_bounded(node), f"{task_id}:{name} has no max_hit/timeout"

        for name, node in nodes.items():
            for target in _targets(node):
                if target in nodes or target in ALLOWED_EXTERNAL_NODES:
                    continue
                if target.startswith(("公共-", "启动-")):
                    continue
                raise AssertionError(f"{task_id}:{name} references unknown node {target}")


def test_batch_a_outcomes_are_business_specific_and_failures_abort_after_record() -> None:
    expected_outcomes: dict[str, set[tuple[str, str]]] = {
        "MAIL_REWARD_DAILY": {
            ("already_complete", "mail.empty"),
            ("success", "mail.reward_claimed"),
        },
        "SHOP_FREE_GIFT_DAILY": {
            ("already_complete", "shop.daily_free_gift_claimed"),
            ("success", "shop.daily_free_gift_claimed"),
        },
        "FREE_APPRAISAL_DAILY": {
            ("already_complete", "appraisal.used"),
            ("success", "appraisal.used"),
        },
        "TRIAL_SWORD_DAILY": {("success", "trial.free_used")},
        "HERO_DISPATCH_DAILY": {
            ("already_complete", "hero.first_task_in_progress"),
            ("success", "hero.first_task_in_progress"),
            ("success", "hero.no_dispatch_tasks"),
        },
        "COLLECTION_DEPLOYMENT_DAILY": {("success", "collection.harvested")},
        "WEEKLY_FREE_GIFT_MONDAY": {
            ("already_complete", "weekly_gift.claimed"),
            ("success", "weekly_gift.claimed"),
            ("not_eligible", "weekly_gift.no_free_offer"),
        },
        "GUILD_AFFAIRS_DAILY": {
            ("success", "guild.affairs.daily.all_rows_started_or_no_action"),
        },
        "GUILD_DONATION_DAILY": {
            ("already_complete", "guild.donation.remaining_9_of_10"),
            ("success", "guild.donation.remaining_9_of_10"),
        },
        "DAILY_TASK_REWARD_CLAIM_DAILY": {
            ("already_complete", "daily_reward.no_claimable"),
            ("success", "daily_reward.no_claimable"),
        },
        "BATTLE_PASS_REWARD_DAILY": {
            ("already_complete", "battle_pass.no_task_or_basic_claimable"),
            ("success", "battle_pass.no_task_or_basic_claimable"),
        },
    }

    for task_id, _, pipeline_name in TASKS:
        nodes = _nodes(ROOT / "assets/resource/base/pipeline" / pipeline_name)
        pairs = _outcome_pairs(nodes)
        assert expected_outcomes[task_id] <= pairs, task_id

        for name, node in nodes.items():
            if node.get("custom_action") != "RecordTaskOutcome":
                continue
            params = node.get("custom_action_param", {})
            status = params.get("status")
            assert isinstance(params.get("postcondition"), str)
            if status == "failed":
                assert params.get("native_fail_after_record") is True, f"{task_id}:{name}"
                assert node.get("Abort") is True, f"{task_id}:{name}"
                assert node.get("next") == ["公共-通用中止"], f"{task_id}:{name}"
            else:
                assert status in {"success", "already_complete", "not_eligible"}
                assert (
                    _reachable(nodes, name, "公共-通用停止")
                    or _reachable(nodes, name, "公共-主页边界")
                ), f"{task_id}:{name}"


def test_batch_a_side_effects_fail_closed_and_guild_affairs_rejects_incomplete_rows() -> None:
    for task_id, _, pipeline_name in TASKS:
        nodes = _nodes(ROOT / "assets/resource/base/pipeline" / pipeline_name)
        for name, node in nodes.items():
            if node.get("custom_action") not in {"BeginTask", "GuardedInput"}:
                continue
            assert node.get("on_error"), f"{task_id}:{name} has no failure route"
            assert _reaches_failed_outcome(
                nodes, name
            ), f"{task_id}:{name} can bypass failure recording"

    nodes = _nodes(ROOT / "assets/resource/base/pipeline/daily/guild_affairs_daily.json")
    success = "帮派事务-成功"
    assert nodes[success]["custom_action_param"]["postcondition"] == (
        "guild.affairs.daily.all_rows_started_or_no_action"
    )
    paid_or_ambiguous = nodes["帮派事务-付费-或-歧义"]
    assert paid_or_ambiguous["custom_action_param"]["status"] == "failed"
    assert paid_or_ambiguous["custom_action_param"]["error_code"] == (
        "GUILD_FIRST_ROW_PAID_OR_AMBIGUOUS"
    )
    assert paid_or_ambiguous.get("Abort") is True

    for row_index in range(1, 4):
        startable = f"guild.affairs.daily.row{row_index}.startable"
        assert startable in nodes
        assert nodes[startable].get("expected") == "开始事务"
        start_node = nodes[f"帮派事务-行{row_index}-开始"]
        assert _reachable(nodes, start_node["next"][0], success) or _reaches_failed_outcome(
            nodes, start_node["next"][0]
        )
