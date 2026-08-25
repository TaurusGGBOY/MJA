from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from agent.custom.support.policy import TASK_POLICIES
from tests.mfw.pipeline_assertions import (
    assert_all_cycles_bounded,
    assert_no_custom_outcome_nodes,
    assert_on_error_contract,
)
from tests.mfw.task_contract import TaskContract, assert_reachable, load_task_nodes

MARTIAL = TaskContract(
    "MARTIAL_STUDY_BREAKTHROUGH_DAILY",
    "daily/martial_study_breakthrough_daily.json",
)
ROOT = Path(__file__).parents[3]
PIPELINE = ROOT / "assets/resource/base/pipeline" / MARTIAL.pipeline_file


def _local_nodes() -> dict[str, dict]:
    return json.loads(PIPELINE.read_text(encoding="utf-8"))


def test_r20_entry_keeps_sibling_resume_paths_and_only_shared_home_recovery() -> None:
    nodes = load_task_nodes(MARTIAL)
    start = nodes["0016-武学突破-任务入口"]

    assert start["next"] == ["1056-武学突破-打开-面板"]
    assert start["on_error"] == [
        "MJA-任务入口失败-MARTIAL_STUDY_BREAKTHROUGH_DAILY",
        "MJA-公共-任务入口-恢复耗尽",
    ]
    assert start["retry_times"] == 0
    assert "1068-武学突破-记录-失败" not in nodes


def test_r20_function_panel_entry_is_distinct_from_home_power_ocr() -> None:
    nodes = load_task_nodes(MARTIAL)
    panel = nodes["1069-武学突破-武学-面板-打开"]
    panel_entry = nodes["0030-公共-游戏功能面板-入口"]

    assert panel["recognition"] == {
        "type": "And",
        "param": {"all_of": ["0030-公共-游戏功能面板-入口"], "box_index": 0},
    }
    assert panel["action"] == "DoNothing"
    assert panel_entry == {
        "recognition": "ColorMatch",
        "method": 4,
        "lower": [165, 135, 75],
        "upper": [255, 225, 180],
        "roi": [1170, 10, 60, 60],
        "connected": True,
        "count": 50,
        "order_by": "Area",
        "index": 0,
        "action": "DoNothing",
    }


def test_r20_panel_action_is_same_frame_guarded_and_capped_once() -> None:
    nodes = load_task_nodes(MARTIAL)
    open_panel = nodes["1056-武学突破-打开-面板"]

    assert open_panel["recognition"]["param"] == {
        "all_of": ["1069-武学突破-武学-面板-打开"],
        "box_index": 0,
    }
    assert open_panel["custom_action"] == "GuardedInput"
    assert open_panel["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 0,
        "target_name": "1069-武学突破-武学-面板-打开",
    }
    assert open_panel["max_hit"] == 1
    assert open_panel["retry_times"] == 0
    assert open_panel["timeout"] == 8000
    assert TASK_POLICIES[MARTIAL.task_id].action_caps["open_function_panel"] == 1

    assert nodes["1071-武学突破-武学-入口"]["roi"] == [650, 120, 600, 560]
    assert nodes["1072-武学突破-武学-页面"]["roi"] == [0, 0, 500, 420]


def test_martial_error_routes_are_removed_except_bounded_local_recovery() -> None:
    nodes = _local_nodes()
    assert_no_custom_outcome_nodes(nodes)
    assert_on_error_contract(
        nodes,
        local_nodes=set(nodes),
        shared_targets={"1365-公共-主页边界-失败"},
    )
    assert_all_cycles_bounded(nodes)
    assert not any(
        "1068-武学突破-记录-失败" in node.get("on_error", [])
        for node in nodes.values()
    )
    assert not any(
        "1068-武学突破-记录-失败" in node.get("next", [])
        for node in nodes.values()
    )


def test_no_success_card_is_an_ordered_success_candidate() -> None:
    nodes = load_task_nodes(MARTIAL)
    no_card = nodes["1061-武学突破-无-成功-突破"]

    selector = [
        "1058-武学突破-领取-左框",
        "1080-武学突破-领取-中框",
        "1081-武学突破-领取-右框",
        "1061-武学突破-无-成功-突破",
    ]
    assert nodes["1057-武学突破-打开-研习"]["next"] == selector
    assert nodes["1060-武学突破-关闭-奖励"]["next"] == [
        "1093-武学突破-关闭-研习详情"
    ]
    assert nodes["1093-武学突破-关闭-研习详情"]["next"] == selector
    assert no_card["recognition"] == {
        "type": "And",
        "param": {"all_of": ["1072-武学突破-武学-页面"], "box_index": 0},
    }
    assert no_card["next"] == [
        "1084-武学突破-打开-馈赠奖励",
        "1062-武学突破-关闭-页面-用于-成功",
    ]
    assert "on_error" not in no_card

    success = nodes["1066-武学突破-成功-无-领取"]
    assert success["action"] == "DoNothing"
    assert success["next"] == ["1100-武学突破-成功-关闭功能面板"]
    assert "on_error" not in success
    assert_reachable(nodes, "1066-武学突破-成功-无-领取", "1371-公共-原生成功-主页边界")

    close_panel = nodes["1100-武学突破-成功-关闭功能面板"]
    assert close_panel["custom_action"] == "ReturnToWorldHome"
    assert close_panel["next"] == ["1371-公共-原生成功-主页边界"]
    assert close_panel["on_error"] == ["1095-武学突破-馈赠领取失败-回主页"]


def test_martial_checks_three_non_overlapping_success_templates_left_to_right() -> None:
    nodes = load_task_nodes(MARTIAL)
    assert nodes["1057-武学突破-打开-研习"]["post_delay"] == 1500
    slots = [
        ("1073-武学突破-武学-成功-左框", [780, 500, 130, 150]),
        ("1082-武学突破-武学-成功-中框", [938, 500, 130, 150]),
        ("1083-武学突破-武学-成功-右框", [1097, 500, 130, 150]),
    ]
    previous_right = 0
    for name, roi in slots:
        success = nodes[name]
        assert success["recognition"] == "TemplateMatch"
        assert success["template"] == (
            "daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/success.png"
        )
        assert success["roi"] == roi
        assert success["threshold"] == 0.55
        assert success["action"] == "DoNothing"
        assert roi[0] >= previous_right
        previous_right = roi[0] + roi[2]

    claims = [
        ("1058-武学突破-领取-左框", slots[0][0]),
        ("1080-武学突破-领取-中框", slots[1][0]),
        ("1081-武学突破-领取-右框", slots[2][0]),
    ]
    for action_name, target_name in claims:
        claim = nodes[action_name]
        assert claim["recognition"]["param"] == {
            "all_of": ["1072-武学突破-武学-页面", target_name],
            "box_index": 1,
        }
        assert claim["max_hit"] == 1
        assert claim["retry_times"] == 0
        assert claim["custom_action_param"]["action_id"] == "claim_success_card"
        assert claim["next"] == ["1059-武学突破-领取-结果"]

    assert nodes["1075-武学突破-武学-结果-关闭"]["expected"] == [
        "点击空白处关闭",
        "点击任意空白区域关闭",
    ]
    detail = nodes["1093-武学突破-关闭-研习详情"]
    assert nodes["1060-武学突破-关闭-奖励"]["next"] == [
        "1093-武学突破-关闭-研习详情"
    ]
    assert detail["recognition"]["param"] == {
        "all_of": [
            "1094-武学突破-研习详情-页面",
            "1076-武学突破-武学-关闭",
        ],
        "box_index": 1,
    }
    assert detail["custom_action_param"]["action_id"] == "close_martial_detail"
    assert detail["max_hit"] == 3
    assert detail["retry_times"] == 0
    assert detail["next"] == [
        "1058-武学突破-领取-左框",
        "1080-武学突破-领取-中框",
        "1081-武学突破-领取-右框",
        "1061-武学突破-无-成功-突破",
    ]


def test_martial_gift_reward_is_optional_red_dot_scoped_and_one_shot() -> None:
    nodes = load_task_nodes(MARTIAL)
    open_gift = nodes["1084-武学突破-打开-馈赠奖励"]
    assert open_gift["recognition"]["param"] == {
        "all_of": [
            "1072-武学突破-武学-页面",
            "1088-武学突破-馈赠奖励-入口",
            "1089-武学突破-馈赠奖励-红点",
        ],
        "box_index": 1,
    }
    assert open_gift["custom_action_param"]["action_id"] == "open_martial_gift_reward"
    assert open_gift["max_hit"] == 1
    assert open_gift["retry_times"] == 0
    assert nodes["1089-武学突破-馈赠奖励-红点"]["roi"] == [90, 345, 80, 70]
    assert nodes["1089-武学突破-馈赠奖励-红点"]["count"] == 2
    gift_page = nodes["1090-武学突破-馈赠奖励-页面"]
    assert gift_page["recognition"] == "TemplateMatch"
    assert gift_page["template"] == "daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/gift_reward_close.png"
    assert gift_page["roi"] == [980, 100, 100, 100]

    claim = nodes["1085-武学突破-领取-馈赠宝箱"]
    assert claim["recognition"]["param"] == {
        "all_of": [
            "1090-武学突破-馈赠奖励-页面",
            "1091-武学突破-馈赠奖励-第一排宝箱",
        ],
        "box_index": 1,
    }
    assert claim["custom_action_param"]["action_id"] == "claim_martial_gift_reward"
    assert claim["max_hit"] == 1
    assert claim["retry_times"] == 0
    assert nodes["1092-武学突破-馈赠奖励-领取结果"]["expected"] == [
        "^领取$",
        "^恭喜获得$",
        "^[恭悉]喜获得$",
        "^获得$",
    ]
    assert nodes["1086-武学突破-关闭-馈赠领取结果"]["next"] == [
        "1087-武学突破-关闭-馈赠奖励页",
        "1062-武学突破-关闭-页面-用于-成功",
    ]
    assert_reachable(nodes, "1084-武学突破-打开-馈赠奖励", "1371-公共-原生成功-主页边界")


def test_martial_gift_chest_uses_green_mask_and_tight_first_row_roi() -> None:
    nodes = load_task_nodes(MARTIAL)
    chest = nodes["1091-武学突破-馈赠奖励-第一排宝箱"]

    assert chest["template"] == (
        "daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/gift_reward_chest_green.png"
    )
    assert chest["roi"] == [930, 195, 75, 75]
    assert chest["threshold"] == 0.8
    assert chest["green_mask"] is True

    asset = ROOT / "assets/resource/base/image" / chest["template"]
    with Image.open(asset) as image:
        assert image.size == (60, 60)
        assert image.mode == "RGB"
        assert image.getpixel((0, 0)) == (0, 255, 0)


def test_martial_side_effect_limits_are_claim_only() -> None:
    nodes = load_task_nodes(MARTIAL)
    policy = TASK_POLICIES[MARTIAL.task_id]
    expected_limits = {
        "open_function_panel": 1,
        "open_martial_study": 1,
        "claim_success_card": 3,
        "close_reward_popup": 3,
        "close_martial_detail": 3,
        "open_martial_gift_reward": 1,
        "claim_martial_gift_reward": 1,
        "dismiss_martial_gift_reward": 1,
        "close_martial_gift_reward": 1,
        "close_martial_page": 1,
    }
    assert dict(policy.action_caps) == expected_limits
    assert policy.risk_levels == frozenset({"stateful"})
    assert nodes["1058-武学突破-领取-左框"]["max_hit"] == 1
    assert nodes["1060-武学突破-关闭-奖励"]["custom_action_param"]["action_id"] == (
        "close_reward_popup"
    )
    assert nodes["1062-武学突破-关闭-页面-用于-成功"]["custom_action_param"][
        "action_id"
    ] == "close_martial_page"


def test_martial_missing_first_slot_marker_reaches_native_success_without_item_navigation() -> None:
    nodes = _local_nodes()
    no_marker = nodes["1061-武学突破-无-成功-突破"]
    close_page = nodes["1062-武学突破-关闭-页面-用于-成功"]

    assert no_marker["next"] == [
        "1084-武学突破-打开-馈赠奖励",
        "1062-武学突破-关闭-页面-用于-成功",
    ]
    assert close_page["next"] == ["1066-武学突破-成功-无-领取"]
    assert nodes["1066-武学突破-成功-无-领取"]["next"] == [
        "1100-武学突破-成功-关闭功能面板"
    ]
    serialized = json.dumps(nodes, ensure_ascii=False)
    assert "加号" not in serialized
    assert "道具" not in serialized
    assert "open_martial_plus_slot" not in serialized
