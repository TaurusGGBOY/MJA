from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from agent.custom.support.policy import TASK_POLICIES
from tests.mfw.task_contract import (
    TaskContract,
    assert_no_side_effect_retry,
    assert_outcome,
    assert_reachable,
    load_task_nodes,
)

JIANLIN = TaskContract(
    "JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY",
    "daily/jianlin_resource_condensate_stamina_daily.json",
)
TASK_PREFIX = "MJA_JIANLIN_"
START = "MJA_JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY_START"
RECOVERY = "MJA_JIANLIN_GAME_START_RECOVERY"
RECOVERY_FAILED = "MJA_JIANLIN_GAME_START_RECOVERY_FAILED"
SHADOW_PAGE = "MJA_JIANLIN_SHADOW_PAGE_PROBE"
DUNGEON_PAGE = "MJA_JIANLIN_DUNGEON_PAGE_PROBE"
RECOVERY_SHADOW_PAGE = "MJA_JIANLIN_RECOVERY_SHADOW_PAGE_PROBE"
FOREIGN_PAGE_CLOSE = "jianlin.foreign.page.close"
RECORD_FAILURE = "MJA_JIANLIN_RECORD_FAILURE"
CLEANUP_ROUTE = "MJA_JIANLIN_TERMINAL_CLEANUP_ROUTE"


def _targets(node: Mapping[str, Any]) -> list[str]:
    result: list[str] = []
    for field in ("next", "on_error"):
        value = node.get(field, [])
        values = [value] if isinstance(value, str) else value
        if not isinstance(values, list):
            continue
        for target in values:
            if not isinstance(target, str):
                continue
            while target.startswith("[") and "]" in target:
                target = target[target.index("]") + 1 :]
            result.append(target)
    return result


def _reachable_names(nodes: Mapping[str, Mapping[str, Any]], source: str) -> set[str]:
    pending = [source]
    visited: set[str] = set()
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)
        pending.extend(_targets(nodes.get(current, {})))
    return visited


def test_jianlin_launcher_recovery_is_root_visible_bounded_and_truthful() -> None:
    nodes = load_task_nodes(JIANLIN)

    assert nodes[START]["next"] == [
        "MJA_JIANLIN_CLOSE_REWARD_POPUP",
        "MJA_JIANLIN_GUILD_ACTIVITY_PAGE_PROBE",
        "MJA_JIANLIN_GUILD_HOME_PAGE_PROBE",
        "MJA_JIANLIN_FUNCTION_PANEL_CLOSE_PROBE",
        "MJA_JIANLIN_RESUME_RESULT_PROBE",
        "MJA_JIANLIN_BATTLE_PAGE_PROBE",
        "MJA_JIANLIN_RING_PAGE_PROBE",
        "MJA_JIANLIN_HOME_PROBE",
        "MJA_JIANLIN_RESUME_PAGE_PROBE",
        "MJA_JIANLIN_DAILY_PAGE_PROBE",
        "MJA_JIANLIN_SHADOW_PAGE_PROBE",
        "MJA_JIANLIN_DUNGEON_PAGE_PROBE",
        RECOVERY,
    ]
    assert nodes[START]["on_error"] == [RECOVERY_FAILED]

    assert "MJA_JIANLIN_FOREIGN_GUILD_DEFEAT_PROBE" not in nodes

    recovery = nodes[RECOVERY]
    assert recovery["action"] == "StartApp"
    assert recovery["package"] == "com.hanjiasongshu.dr22/.MainActivity"
    assert recovery["max_hit"] == 1
    assert recovery["retry_times"] == 0
    assert recovery["next"] == [
        "MJA_JIANLIN_RECOVERY_ANNOUNCEMENT",
        "MJA_JIANLIN_RECOVERY_TITLE",
        "MJA_JIANLIN_RECOVERY_TITLE_TEMPLATE",
        "MJA_JIANLIN_RECOVERY_STATE_PROBE",
    ]
    assert recovery["on_error"] == [RECOVERY_FAILED]

    state_probe = nodes["MJA_JIANLIN_RECOVERY_STATE_PROBE"]
    assert state_probe["timeout"] == 30_000
    assert state_probe["next"] == [
        "MJA_JIANLIN_FUNCTION_PANEL_CLOSE_PROBE",
        RECOVERY_SHADOW_PAGE,
        "MJA_JIANLIN_RESUME_RESULT_PROBE",
        "MJA_JIANLIN_BATTLE_PAGE_PROBE",
        "MJA_JIANLIN_RING_PAGE_PROBE",
        "MJA_JIANLIN_HOME_PROBE",
        "MJA_JIANLIN_RESUME_PAGE_PROBE",
        "MJA_JIANLIN_DAILY_PAGE_PROBE",
    ]
    assert state_probe["on_error"] == ["MJA_JIANLIN_GAME_START_RECOVERY_RELAUNCH"]

    assert_outcome(
        nodes,
        RECOVERY_FAILED,
        "failed",
        "jianlin.game_foreground_or_recoverable_state",
    )
    assert nodes[RECOVERY_FAILED]["custom_action_param"]["error_code"] == (
        "JIANLIN_GAME_START_RECOVERY_EXHAUSTED"
    )
    assert nodes[RECOVERY_FAILED]["Abort"] is True
    assert_reachable(nodes, RECOVERY_FAILED, "MJA_COMMON_ABORT")

    task_nodes = {name: node for name, node in nodes.items() if name.startswith(TASK_PREFIX)}
    assert all(
        target != "[JumpBack]MJA_GAME_START"
        for node in task_nodes.values()
        for field in ("next", "on_error")
        for target in node.get(field, [])
    )
    assert all(node.get("action") != "StopApp" for node in task_nodes.values())


def test_jianlin_foreign_shadow_page_closes_once_on_exact_page() -> None:
    nodes = load_task_nodes(JIANLIN)

    shadow_probe = nodes[SHADOW_PAGE]
    assert shadow_probe["recognition"] == {
        "type": "And",
        "param": {
            "all_of": ["jianlin.foreign.shadow.page", FOREIGN_PAGE_CLOSE],
            "box_index": 1,
        },
    }
    assert shadow_probe["timeout"] == 8_000
    assert shadow_probe["max_hit"] == 1
    assert shadow_probe["action"] == "Click"
    assert shadow_probe["post_delay"] == 1_000
    assert shadow_probe["retry_times"] == 0
    assert shadow_probe["next"] == ["MJA_JIANLIN_HOME_PROBE"]
    assert shadow_probe["on_error"] == [RECOVERY_FAILED]

    assert nodes[FOREIGN_PAGE_CLOSE] == {
        "recognition": "TemplateMatch",
        "template": "home/modal_close.png",
        "roi": [1160, 0, 100, 100],
        "threshold": 0.36,
        "timeout": 8_000,
        "action": "DoNothing",
    }

    residual_shadow_probe = nodes[RECOVERY_SHADOW_PAGE]
    assert residual_shadow_probe["recognition"] == {
        "type": "And",
        "param": {
            "all_of": ["jianlin.foreign.shadow.page"],
            "box_index": 0,
        },
    }
    assert residual_shadow_probe["next"] == [RECOVERY_FAILED]
    assert residual_shadow_probe["on_error"] == [RECOVERY_FAILED]

    page = nodes["jianlin.foreign.shadow.page"]
    assert page["recognition"] == {
        "type": "And",
        "param": {
            "all_of": [
                "jianlin.foreign.shadow.title",
                "jianlin.foreign.shadow.level",
            ],
            "box_index": 0,
        },
    }
    assert nodes["jianlin.foreign.shadow.title"] == {
        "recognition": "OCR",
        "expected": "^蜃影武墟$",
        "roi": [300, 360, 360, 150],
        "timeout": 8_000,
        "action": "DoNothing",
    }
    assert nodes["jianlin.foreign.shadow.level"] == {
        "recognition": "OCR",
        "expected": "当前武墟等级",
        "roi": [620, 390, 320, 120],
        "timeout": 8_000,
        "action": "DoNothing",
    }

    assert "MJA_JIANLIN_RESTART_RECOVERY" not in nodes


def test_jianlin_dungeon_page_closes_once_without_replaying_business_actions() -> None:
    nodes = load_task_nodes(JIANLIN)

    dungeon_probe = nodes[DUNGEON_PAGE]
    assert dungeon_probe["recognition"] == {
        "type": "And",
        "param": {
            "all_of": ["dungeon.page", "dungeon.close"],
            "box_index": 1,
        },
    }
    assert dungeon_probe["timeout"] == 8_000
    assert dungeon_probe["action"] == "Click"
    assert dungeon_probe["max_hit"] == 1
    assert dungeon_probe["post_delay"] == 1_000
    assert dungeon_probe["retry_times"] == 0
    assert dungeon_probe["next"] == ["MJA_JIANLIN_HOME_PROBE"]
    assert dungeon_probe["on_error"] == [RECOVERY_FAILED]


def test_jianlin_daily_page_uses_sibling_candidates_for_done_and_pending_rows() -> None:
    nodes = load_task_nodes(JIANLIN)

    # MFW evaluates names in ``next`` as sibling recognition candidates. A miss on
    # one candidate does not execute that candidate's own ``on_error`` route.
    page_probe = nodes["MJA_JIANLIN_DAILY_PAGE_PROBE"]
    assert page_probe["next"] == [
        "MJA_JIANLIN_DAILY_ROW_PROBE",
        "MJA_JIANLIN_SCROLL_DAILY_JIANLIN",
    ]
    assert page_probe["on_error"] == [RECORD_FAILURE]

    already_probe = nodes["MJA_JIANLIN_DAILY_ALREADY_PROBE"]
    assert already_probe["recognition"]["param"]["all_of"] == [
        "jianlin.daily.page",
        "jianlin.daily.row",
        "jianlin.daily.done",
    ]
    assert already_probe["on_error"] == ["MJA_JIANLIN_DAILY_ROW_PROBE"]

    pending_probe = nodes["MJA_JIANLIN_DAILY_ROW_PROBE"]
    assert pending_probe["recognition"]["param"]["all_of"] == [
        "jianlin.daily.page",
        "jianlin.daily.row",
    ]
    assert pending_probe["next"] == ["MJA_JIANLIN_OPEN_JIANLIN"]

    after_scroll = nodes["MJA_JIANLIN_DAILY_PAGE_AFTER_SCROLL"]
    assert after_scroll["next"] == [
        "MJA_JIANLIN_DAILY_ROW_PROBE",
        "MJA_JIANLIN_SCROLL_DAILY_JIANLIN",
    ]
    assert nodes["MJA_JIANLIN_SCROLL_DAILY_JIANLIN"]["next"] == [
        "MJA_JIANLIN_DAILY_PAGE_AFTER_SCROLL"
    ]
    scroll_recognition = nodes["MJA_JIANLIN_SCROLL_DAILY_JIANLIN"]["recognition"]["param"]
    assert scroll_recognition["all_of"] == ["jianlin.daily.page"]
    assert scroll_recognition["box_index"] == 0

    scroll_marker = nodes["jianlin.daily.scroll"]
    assert scroll_marker["expected"] == "完成一次蜃影武墟挑战"
    assert scroll_marker["roi"] == [200, 170, 850, 550]


def test_jianlin_entry_targets_the_live_go_button_after_row_probe() -> None:
    nodes = load_task_nodes(JIANLIN)

    row = nodes["jianlin.daily.row"]
    assert row["recognition"] == "OCR"
    assert row["expected"] == r"^战胜一次剑林的首领[。.]?$"
    assert row["roi"] == [200, 170, 650, 550]
    assert re.fullmatch(row["expected"], "战胜一次剑林的首领。")
    assert not re.fullmatch(row["expected"], "各位大侠可前往剑林·对弈中参与")
    assert not re.fullmatch(row["expected"], "消耗10000凝晶。")

    entry = nodes["jianlin.entry"]
    # The row is already proved by MJA_JIANLIN_DAILY_ROW_PROBE.  Keep the
    # click target as a top-level OCR result: the Android MFW runtime reports
    # nested inline-AND boxes as the full frame, which previously sent the
    # guarded click to screen center instead of the row's 前往 button.
    assert entry["recognition"] == "OCR"
    assert entry["expected"] == r"^前往$"
    assert entry["roi"] == [980, 400, 240, 100]
    assert entry["roi"] != [0, 0, 1280, 720]

    open_node = nodes["MJA_JIANLIN_OPEN_JIANLIN"]
    assert open_node["recognition"]["param"]["all_of"] == [
        "jianlin.daily.page",
        "jianlin.entry",
    ]
    assert open_node["recognition"]["param"]["box_index"] == 1
    evidence = open_node["custom_action_param"]["evidence"]
    assert evidence == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "jianlin.daily.page",
        "target_name": "jianlin.entry",
    }


def test_jianlin_page_proof_uses_live_ocr_controls_not_the_blank_template() -> None:
    nodes = load_task_nodes(JIANLIN)

    page = nodes["jianlin.page"]
    assert page["recognition"]["type"] == "And"
    assert page["recognition"]["param"] == {
        "all_of": [
            "jianlin.page.title",
            "jianlin.multiplier.bar",
            "jianlin.count.bar",
        ],
        "box_index": 0,
    }
    assert nodes["jianlin.page.title"]["expected"] == r"^养成\s*/\s*资源$"
    assert nodes["jianlin.page.title"]["roi"] == [40, 0, 280, 100]

    for probe_name in (
        "MJA_JIANLIN_RESUME_PAGE_PROBE",
        "MJA_JIANLIN_PAGE_PROBE",
        "MJA_JIANLIN_PAGE_ROUTE",
    ):
        probe = nodes[probe_name]
        assert probe["recognition"]["param"]["all_of"] == ["jianlin.page"]
        assert probe["recognition"]["param"]["box_index"] == 0
        assert "template" not in probe

    serialized = json.dumps(nodes, ensure_ascii=False)
    assert "jianlin_page.png" not in serialized
    assert "jianlin.daily.page" not in page["recognition"]["param"]["all_of"]


def test_jianlin_recovery_cannot_replay_purchase_or_resource_actions() -> None:
    nodes = load_task_nodes(JIANLIN)
    protected_actions = {
        "buy_stamina_once",
        "confirm_jianlin_stamina_purchase",
        "challenge_condensate",
        "start_jianlin_battle",
    }

    for action_id in protected_actions:
        assert_no_side_effect_retry(nodes, action_id)

    for node in nodes.values():
        params = node.get("custom_action_param", {})
        if not isinstance(params, Mapping):
            continue
        if params.get("action_id") not in protected_actions:
            continue
        assert node.get("retry_times", 0) == 0
        assert RECOVERY not in _reachable_names(nodes, RECORD_FAILURE)
        assert node["on_error"] == [RECORD_FAILURE]

    assert nodes["MJA_JIANLIN_DISMISS_STALE_RESULT"]["next"] == [
        "MJA_JIANLIN_HOME_PROBE",
        "MJA_JIANLIN_RESUME_PAGE_PROBE",
        "MJA_JIANLIN_DAILY_PAGE_PROBE",
    ]


def test_jianlin_terminal_outcomes_use_bounded_best_effort_home_cleanup() -> None:
    nodes = load_task_nodes(JIANLIN)

    for terminal in (
        "MJA_JIANLIN_SUCCESS",
        "MJA_JIANLIN_ALREADY_COMPLETE",
        "MJA_JIANLIN_NOT_ELIGIBLE",
    ):
        next_nodes = nodes[terminal]["next"]
        assert next_nodes in ([CLEANUP_ROUTE], ["MJA_JIANLIN_COMMON_ABORT"])
        assert nodes[terminal]["on_error"] == [RECORD_FAILURE]
        if next_nodes == [CLEANUP_ROUTE]:
            assert_reachable(nodes, terminal, "MJA_JIANLIN_COMMON_STOP")
        else:
            assert_reachable(nodes, terminal, "MJA_COMMON_ABORT")

    cleanup_route = nodes[CLEANUP_ROUTE]
    assert cleanup_route["timeout"] == 10_000
    assert cleanup_route["next"] == [
        "MJA_JIANLIN_CLEANUP_PAGE_CLOSE",
        "MJA_JIANLIN_CLEANUP_DAILY_CLOSE",
        "MJA_JIANLIN_CLEANUP_HOME_PROBE",
    ]
    assert cleanup_route["on_error"] == [
        "MJA_JIANLIN_CLEANUP_START_APP",
        "MJA_JIANLIN_COMMON_STOP",
    ]

    page_close = nodes["MJA_JIANLIN_CLEANUP_PAGE_CLOSE"]
    assert page_close["custom_action_param"]["action_id"] == "close_jianlin_page"
    assert page_close["retry_times"] == 0
    assert page_close["next"] == ["MJA_JIANLIN_CLEANUP_AFTER_PAGE_ROUTE"]

    daily_close = nodes["MJA_JIANLIN_CLEANUP_DAILY_CLOSE"]
    assert daily_close["custom_action_param"]["action_id"] == "close_daily_tasks"
    assert daily_close["retry_times"] == 0
    assert daily_close["next"] == ["MJA_JIANLIN_CLEANUP_HOME_PROBE"]
    assert TASK_POLICIES[JIANLIN.task_id].action_caps["close_daily_tasks"] == 1
    assert nodes["jianlin.daily.close"]["template"] == ("daily/TRIAL_SWORD_DAILY/trial_close.png")

    cleanup_start = nodes["MJA_JIANLIN_CLEANUP_START_APP"]
    assert cleanup_start["action"] == "StartApp"
    assert cleanup_start["max_hit"] == 1
    assert cleanup_start["retry_times"] == 0
    cleanup_wait = nodes["MJA_JIANLIN_CLEANUP_RECOVERY_STATE_PROBE"]
    assert cleanup_wait["timeout"] == 30_000
    assert cleanup_wait["on_error"] == ["MJA_JIANLIN_COMMON_STOP"]

    cleanup_nodes = {
        name: nodes[name] for name in _reachable_names(nodes, CLEANUP_ROUTE) if name in nodes
    }
    assert all(node.get("custom_action") != "RecordTaskOutcome" for node in cleanup_nodes.values())


def test_jianlin_nonterminal_nodes_have_explicit_failure_routes() -> None:
    nodes = load_task_nodes(JIANLIN)
    assert nodes["MJA_JIANLIN_PLAN_DISPATCH"]["on_error"] == [RECORD_FAILURE]

    missing: list[str] = []
    for name, node in nodes.items():
        if not name.startswith(TASK_PREFIX):
            continue
        if name in {
            "MJA_JIANLIN_RECOVERY_ANNOUNCEMENT",
            "MJA_JIANLIN_RECOVERY_TITLE",
            "MJA_JIANLIN_RECOVERY_TITLE_TEMPLATE",
            "MJA_JIANLIN_RING_PAGE_TITLE",
            "MJA_JIANLIN_RING_PAGE_CLOSE_ICON",
        }:
            continue
        if node.get("action") == "StopTask":
            continue
        if node.get("custom_action") == "RecordTaskOutcome":
            continue
        if not node.get("on_error"):
            missing.append(name)
    assert missing == []
