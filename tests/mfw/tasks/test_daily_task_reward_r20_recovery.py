from __future__ import annotations

import json
from pathlib import Path

from tests.mfw.pipeline_assertions import assert_all_cycles_bounded
from tests.mfw.task_contract import (
    TaskContract,
    assert_guarded_actions,
    assert_no_side_effect_retry,
    assert_reachable,
    assert_task_contract,
    load_task_nodes,
)

DAILY = TaskContract(
    "DAILY_TASK_REWARD_CLAIM_DAILY",
    "daily/daily_task_reward_claim_daily.json",
)
ROOT = Path(__file__).parents[3]
PIPELINE_PATH = ROOT / "assets/resource/base/pipeline" / DAILY.pipeline_file


def _nodes() -> dict[str, dict]:
    return json.loads(PIPELINE_PATH.read_text(encoding="utf-8"))


def _contains(roi: list[int], observed_box: list[int]) -> bool:
    rx, ry, rw, rh = roi
    bx, by, bw, bh = observed_box
    return (
        rx <= bx
        and ry <= by
        and bx + bw <= rx + rw
        and by + bh <= ry + rh
    )


def test_daily_rewards_enters_from_the_right_function_panel() -> None:
    nodes = _nodes()
    entry = nodes["0005-日常任务奖励-任务入口"]
    open_panel = nodes["0255-日常任务奖励-打开-面板"]
    open_daily = nodes["0257-日常任务奖励-打开-日常"]

    assert_task_contract(DAILY, require_game_start_recovery=False)
    assert entry["timeout"] == 5_000
    assert entry["next"] == ["0255-日常任务奖励-打开-面板"]
    assert entry["on_error"] == [
        "MJA-任务入口失败-DAILY_TASK_REWARD_CLAIM_DAILY",
        "MJA-公共-任务入口-恢复耗尽",
    ]
    assert open_panel["next"] == ["0257-日常任务奖励-打开-日常"]
    assert open_daily["next"] == ["0286-日常任务奖励-日常-页面"]
    assert nodes["0285-日常任务奖励-日常-入口"]["expected"] == "日常"
    assert _contains(nodes["0285-日常任务奖励-日常-入口"]["roi"], [1072, 291, 44, 28])
    assert_reachable(
        load_task_nodes(DAILY), DAILY.entry, "1371-公共-原生成功-主页边界"
    )


def test_daily_rewards_require_a_verified_page_before_claim_or_empty_success() -> None:
    nodes = _nodes()
    page = nodes["0286-日常任务奖励-日常-页面"]
    claim = nodes["0267-日常任务奖励-领取-行"]
    chest = nodes["0268-日常任务奖励-领取-宝箱"]
    empty_marker = nodes["0293-日常任务奖励-日常-无-可领取-全局"]
    claimed_marker = nodes["0294-日常任务奖励-日常-已领取-行"]

    assert page["next"] == [
        "0267-日常任务奖励-领取-行",
        "0293-日常任务奖励-日常-无-可领取-全局",
        "0294-日常任务奖励-日常-已领取-行",
    ]
    assert claim["on_error"] == ["0268-日常任务奖励-领取-宝箱"]
    assert chest["on_error"] == ["0280-日常任务奖励-关闭"]
    assert empty_marker["next"] == ["0280-日常任务奖励-关闭"]
    assert claimed_marker["next"] == ["0280-日常任务奖励-关闭"]
    assert empty_marker["expected"] == ["^暂无可领取$", "^前往$"]
    assert claimed_marker["expected"] == "^已领取$"
    assert not any("扫描-耗尽" in name or "主页边界-失败" in name for name in nodes)


def test_daily_rewards_keep_claim_and_chest_popup_cleanup_separate() -> None:
    nodes = _nodes()
    assert nodes["0267-日常任务奖励-领取-行"]["next"] == [
        "0262-日常任务奖励-关闭-奖励",
        "0268-日常任务奖励-领取-宝箱",
    ]
    assert nodes["0262-日常任务奖励-关闭-奖励"]["next"] == [
        "0268-日常任务奖励-领取-宝箱"
    ]
    assert nodes["0268-日常任务奖励-领取-宝箱"]["next"] == [
        "0305-日常任务奖励-关闭-宝箱奖励"
    ]
    assert nodes["0305-日常任务奖励-关闭-宝箱奖励"]["next"] == [
        "0280-日常任务奖励-关闭"
    ]
    assert nodes["0282-日常任务奖励-关闭-面板"]["next"] == [
        "1371-公共-原生成功-主页边界"
    ]


def test_daily_rewards_actions_are_guarded_and_bounded() -> None:
    nodes = load_task_nodes(DAILY)
    assert_guarded_actions(
        nodes,
        DAILY.task_id,
        [
            "open_function_panel",
            "open_daily_tasks",
            "claim_completed_daily_row",
            "close_reward_popup",
            "claim_unlocked_activity_chest",
            "close_daily_tasks",
            "close_function_panel",
        ],
    )
    for action_id in (
        "claim_completed_daily_row",
        "close_reward_popup",
        "claim_unlocked_activity_chest",
    ):
        assert_no_side_effect_retry(nodes, action_id)
    assert_all_cycles_bounded(nodes)
