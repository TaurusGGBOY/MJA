from __future__ import annotations

from agent.custom.support.policy import TASK_POLICIES
from tests.mfw.task_contract import (
    TaskContract,
    assert_no_side_effect_retry,
    assert_outcome,
    load_task_nodes,
)


BATTLE_PASS = TaskContract(
    "BATTLE_PASS_REWARD_DAILY",
    "daily/battle_pass_reward_daily.json",
)
FAILURE = "MJA_BP_RECORD_FAILURE"


def _contains(roi: list[int], box: list[int]) -> bool:
    x, y, width, height = roi
    bx, by, bwidth, bheight = box
    return (
        x <= bx
        and y <= by
        and bx + bwidth <= x + width
        and by + bheight <= y + height
    )


def test_r20_start_uses_finite_page_and_entry_siblings() -> None:
    nodes = load_task_nodes(BATTLE_PASS)
    start = nodes["MJA_BATTLE_PASS_REWARD_DAILY_START"]

    assert start["next"] == [
        "MJA_BP_RESUME_REWARD_PROBE",
        "MJA_BP_RESUME_ITEM_PROBE",
        "MJA_BP_TASKS_PAGE_PROBE",
        "MJA_BP_REWARDS_START_PROBE",
        "MJA_BP_PAGE_PROBE",
        "MJA_BP_HOME_PROBE",
    ]
    assert start["on_error"] == [FAILURE]
    assert "MJA_BP_OPEN_PANEL" not in nodes
    assert "MJA_BP_PANEL_PROBE" not in nodes
    assert "open_function_panel" not in TASK_POLICIES[BATTLE_PASS.task_id].action_caps

    for name, node in nodes.items():
        if not name.startswith("MJA_BP_"):
            continue
        if name in {"MJA_BP_ALL_CLAIMED", "MJA_BP_ALL_CLAIMED_SUCCESS"}:
            continue
        for edge in (*node.get("next", []), *node.get("on_error", [])):
            assert not edge.startswith("[JumpBack]"), edge


def test_r20_home_ocr_proves_direct_top_level_battle_pass_entry() -> None:
    nodes = load_task_nodes(BATTLE_PASS)
    home = nodes["battle_pass.home.page"]
    entry = nodes["battle_pass.open"]

    assert home == {
        "recognition": {
            "type": "And",
            "param": {
                "all_of": [
                    "battle_pass.home.activity",
                    "battle_pass.home.pray",
                    "battle_pass.home.dungeon",
                    "battle_pass.home.painting",
                ],
                "box_index": 0,
            },
        },
        "action": "DoNothing",
    }
    assert entry == {
        "recognition": "OCR",
        "expected": "^战令$",
        "roi": [800, 45, 80, 40],
        "action": "DoNothing",
    }

    # Fresh r20 OCR from the failed formal ticket.
    assert _contains(entry["roi"], [824, 56, 30, 18])
    assert _contains(nodes["battle_pass.home.activity"]["roi"], [882, 58, 35, 14])
    assert _contains(nodes["battle_pass.home.pray"]["roi"], [1001, 58, 31, 14])
    assert _contains(nodes["battle_pass.home.dungeon"]["roi"], [1057, 58, 36, 14])
    assert _contains(nodes["battle_pass.home.painting"]["roi"], [1116, 58, 32, 14])

    probe = nodes["MJA_BP_HOME_PROBE"]
    assert probe["recognition"]["param"] == {
        "all_of": ["battle_pass.home.page", "battle_pass.open"],
        "box_index": 0,
    }
    opened = nodes["MJA_BP_OPEN_BATTLE_PASS"]
    assert opened["recognition"]["param"] == {
        "all_of": ["battle_pass.home.page", "battle_pass.open"],
        "box_index": 1,
    }
    assert opened["max_hit"] == 1
    assert opened["retry_times"] == 0


def test_r20_task_rewards_require_same_frame_page_and_exact_claim() -> None:
    nodes = load_task_nodes(BATTLE_PASS)
    page = nodes["MJA_BP_TASKS_PAGE_PROBE"]
    assert nodes["battle_pass.tasks"]["recognition"]["param"] == {
        "all_of": [
            "battle_pass.page",
            "battle_pass.tasks_tab",
            "battle_pass.tasks_content",
        ],
        "box_index": 0,
    }
    assert nodes["battle_pass.tasks_content"]["expected"] == [
        "^每周任务$",
        "^当期任务$",
        "^追赶任务$",
    ]
    assert page["next"] == [
        "MJA_BP_TASK_CLAIM_LOOP",
        "MJA_BP_TASK_INITIAL_NO_CLAIM_PROBE",
    ]

    for name in (
        "MJA_BP_TASK_CLAIM_LOOP",
        "MJA_BP_TASK_CLAIM_LOOP_AFTER_CLAIM",
    ):
        claim = nodes[name]
        assert claim["recognition"]["param"] == {
            "all_of": ["battle_pass.tasks", "battle_pass.task_reward_claim"],
            "box_index": 1,
        }
        assert claim["custom_action_param"]["evidence"] == {
            "page_index": 0,
            "target_index": 1,
            "page_name": "battle_pass.tasks",
            "target_name": "battle_pass.task_reward_claim",
        }
        assert claim["max_hit"] == 50
        assert claim["retry_times"] == 0
        assert claim["next"] == [
            "MJA_BP_TASK_REWARD_PROBE",
            "MJA_BP_TASK_ITEM_PROBE",
            "MJA_BP_TASK_REWARD_VERIFY",
        ]

    target = nodes["battle_pass.task_reward_claim"]
    assert target["expected"] == "^领取$"
    assert target["roi"] == [700, 190, 220, 180]
    no_claim = nodes["battle_pass.task_no_claimable"]
    assert no_claim["expected"] == [
        "^已领取$",
        "^暂无可领取$",
        "^未完成$",
        "^前往$",
    ]
    assert "已完成" not in no_claim["expected"]
    assert nodes["battle_pass.reward_popup"]["expected"] == [
        "^恭喜获得$",
        "^恭喜$",
        "^喜获得$",
        "^罗喜获得$",
        "^墨喜获得$",
        "^获得$",
        "^获得奖励$",
    ]


def test_r20_basic_rewards_prioritize_tight_red_dot_before_claimed_state() -> None:
    nodes = load_task_nodes(BATTLE_PASS)

    assert nodes["MJA_BP_INITIAL_REWARDS_PAGE_PROBE"]["next"] == [
        "MJA_BP_BASIC_CLAIM_LOOP",
        "MJA_BP_INITIAL_BASIC_STATUS_PROBE",
        "MJA_BP_INITIAL_BASIC_CHECK_PROBE",
    ]
    assert nodes["MJA_BP_MUTATED_REWARDS_PAGE_PROBE"]["next"] == [
        "MJA_BP_MUTATED_BASIC_CLAIM_LOOP",
        "MJA_BP_MUTATED_BASIC_STATUS_PROBE",
        "MJA_BP_MUTATED_BASIC_CHECK_PROBE",
    ]
    assert nodes["battle_pass.basic_red_dot_reward"] == {
        "recognition": "ColorMatch",
        "method": 4,
        "lower": [180, 0, 0],
        "upper": [255, 120, 120],
        "roi": [300, 330, 280, 60],
        "connected": True,
        "count": 80,
        "order_by": "Area",
        "index": 0,
        "action": "DoNothing",
    }
    assert nodes["battle_pass.basic_all_claimed"]["expected"] == "^已领取$"
    assert nodes["battle_pass.basic_claimed_check"] == {
        "recognition": "TemplateMatch",
        "template": "daily/BATTLE_PASS_REWARD_DAILY/basic_claimed.png",
        "roi": [250, 320, 300, 150],
        "threshold": 0.42,
        "action": "DoNothing",
    }

    for name in ("MJA_BP_BASIC_CLAIM_LOOP", "MJA_BP_MUTATED_BASIC_CLAIM_LOOP"):
        claim = nodes[name]
        assert claim["recognition"]["param"] == {
            "all_of": ["battle_pass.rewards", "battle_pass.basic_red_dot_reward"],
            "box_index": 1,
        }
        assert claim["custom_action_param"]["evidence"] == {
            "page_index": 0,
            "target_index": 1,
            "page_name": "battle_pass.rewards",
            "target_name": "battle_pass.basic_red_dot_reward",
        }
        assert claim["max_hit"] == 50
        assert claim["retry_times"] == 0
        assert claim["next"] == [
            "MJA_BP_BASIC_REWARD_PROBE",
            "MJA_BP_BASIC_ITEM_PROBE",
            "MJA_BP_BASIC_REWARD_VERIFY",
        ]

    assert nodes["MJA_BP_BASIC_REWARD_PROBE"]["timeout"] == 12000
    assert nodes["MJA_BP_BASIC_ITEM_PROBE"]["timeout"] == 12000
    assert nodes["MJA_BP_BASIC_REWARD_PROBE"]["on_error"] == [
        "MJA_BP_BASIC_REWARD_WAIT"
    ]
    assert nodes["MJA_BP_BASIC_REWARD_WAIT"] == {
        "recognition": "DirectHit",
        "action": "DoNothing",
        "post_delay": 1000,
        "max_hit": 12,
        "next": ["MJA_BP_BASIC_REWARD_PROBE"],
        "on_error": ["MJA_BP_RECORD_FAILURE"],
    }


def test_r20_task_and_basic_mutations_have_fresh_postconditions() -> None:
    nodes = load_task_nodes(BATTLE_PASS)

    assert nodes["MJA_BP_TASK_INITIAL_NO_CLAIM_PROBE"]["next"] == [
        "MJA_BP_OPEN_REWARDS_INITIAL"
    ]
    assert nodes["MJA_BP_TASK_AFTER_CLAIM_NO_CLAIM_PROBE"]["next"] == [
        "MJA_BP_OPEN_REWARDS_MUTATED"
    ]
    assert nodes["MJA_BP_INITIAL_BASIC_STATUS_PROBE"]["next"] == [
        "MJA_BP_CLOSE_ALREADY_COMPLETE"
    ]
    assert nodes["MJA_BP_MUTATED_BASIC_STATUS_PROBE"]["next"] == [
        "MJA_BP_CLOSE_SUCCESS"
    ]
    assert nodes["MJA_BP_INITIAL_BASIC_CHECK_PROBE"]["next"] == [
        "MJA_BP_CLOSE_ALREADY_COMPLETE"
    ]
    assert nodes["MJA_BP_MUTATED_BASIC_CHECK_PROBE"]["next"] == [
        "MJA_BP_CLOSE_SUCCESS"
    ]
    assert nodes["MJA_BP_BASIC_REWARD_VERIFY"]["next"] == [
        "MJA_BP_MUTATED_REWARDS_PAGE_PROBE"
    ]
    assert nodes["battle_pass.item_popup"]["recognition"]["param"] == {
        "all_of": ["battle_pass.item_popup_type", "battle_pass.item_popup_owned"],
        "box_index": 0,
    }


def test_r20_result_is_recorded_only_after_safe_exit_reaches_home() -> None:
    nodes = load_task_nodes(BATTLE_PASS)

    assert nodes["battle_pass.close"] == {
        "recognition": "TemplateMatch",
        "template": "daily/BUY_TEA_DAILY/shop_close.png",
        "roi": [1170, 0, 110, 110],
        "threshold": 0.36,
        "action": "DoNothing",
    }

    routes = (
        (
            "MJA_BP_CLOSE_ALREADY_COMPLETE",
            "MJA_BP_HOME_AFTER_ALREADY_COMPLETE",
            "MJA_BP_ALL_CLAIMED",
            "already_complete",
        ),
        (
            "MJA_BP_CLOSE_SUCCESS",
            "MJA_BP_HOME_AFTER_SUCCESS",
            "MJA_BP_ALL_CLAIMED_SUCCESS",
            "success",
        ),
    )
    for close_name, home_name, outcome_name, status in routes:
        close = nodes[close_name]
        assert close["recognition"]["param"] == {
            "all_of": ["battle_pass.rewards", "battle_pass.close"],
            "box_index": 1,
        }
        assert close["max_hit"] == 1
        assert close["retry_times"] == 0
        assert close["next"] == [home_name]
        assert close["on_error"] == ["MJA_BP_HOME_BOUNDARY_FAILURE"]

        home = nodes[home_name]
        assert home["recognition"]["param"] == {
            "all_of": ["battle_pass.home.page", "battle_pass.open"],
            "box_index": 0,
        }
        assert home["next"] == [outcome_name]
        assert_outcome(
            nodes,
            outcome_name,
            status,
            "battle_pass.no_task_or_basic_claimable",
        )


def test_r20_unknown_states_record_fresh_failure_then_native_fail() -> None:
    nodes = load_task_nodes(BATTLE_PASS)
    for name in (
        "MJA_BP_TASKS_AMBIGUOUS",
        "MJA_BP_REWARDS_AMBIGUOUS",
        "MJA_BP_HOME_BOUNDARY_FAILURE",
        FAILURE,
    ):
        node = nodes[name]
        params = node["custom_action_param"]
        assert params["task_id"] == BATTLE_PASS.task_id
        assert params["status"] == "failed"
        assert params["error_code"]
        assert params["native_fail_after_record"] is True
        assert node["Abort"] is True
        assert node["next"] == ["MJA_COMMON_ABORT"]
        assert "on_error" not in node


def test_r20_every_battle_pass_side_effect_is_non_retrying_and_capped() -> None:
    nodes = load_task_nodes(BATTLE_PASS)
    policy = TASK_POLICIES[BATTLE_PASS.task_id]

    for action_id in policy.action_caps:
        assert_no_side_effect_retry(nodes, action_id)

    for node in nodes.values():
        params = node.get("custom_action_param", {})
        action_id = params.get("action_id")
        if (
            params.get("task_id") != BATTLE_PASS.task_id
            or action_id not in policy.action_caps
        ):
            continue
        assert node["retry_times"] == 0
        assert 1 <= node["max_hit"] <= policy.action_caps[action_id]
