from __future__ import annotations

import json
from pathlib import Path

from tests.mfw.pipeline_assertions import assert_no_custom_outcome_nodes
from tests.mfw.task_contract import (
    TaskContract,
)


ROOT = Path(__file__).parents[3]
FOOD = TaskContract("EAT_STAMINA_FOOD_DAILY", "daily/eat_stamina_food_daily.json")
PIPELINE_PATH = ROOT / "assets/resource/base/pipeline" / FOOD.pipeline_file
RECORDER = "0411-吃体力食物-记录-失败"


def _scoped_nodes() -> dict[str, dict[str, object]]:
    return json.loads(PIPELINE_PATH.read_text(encoding="utf-8"))


def test_food_entry_uses_bottom_item_label_and_preserves_existing_use_flow() -> None:
    scoped = _scoped_nodes()
    entry = scoped["0007-吃体力食物-任务入口"]
    open_resource = scoped["0382-吃体力食物-打开-资源"]
    item_entry = scoped["0413-吃体力食物-食物-资源-入口"]

    assert item_entry["recognition"] == "OCR"
    assert item_entry["expected"] == "(?:道)?具"
    assert item_entry["roi"] == [980, 580, 300, 140]
    assert entry["custom_action"] == "BeginTask"
    assert entry["custom_action_param"] == {"task_id": FOOD.task_id}
    assert entry["next"] == ["0382-吃体力食物-打开-资源"]
    assert open_resource["custom_action"] == "GuardedInput"
    assert open_resource["custom_action_param"]["action_id"] == "open_resource_page"
    assert open_resource["next"] == ["0383-吃体力食物-打开-分类"]
    assert scoped["0422-吃体力食物-食物-使用-目标"]["expected"] == "使用"
    assert scoped["0431-吃体力食物-食物-替换-提示"] == {
        "recognition": "OCR",
        "expected": ["^提示$", "^提$"],
        "roi": [0, 0, 500, 720],
        "action": "DoNothing",
    }
    assert scoped["0432-吃体力食物-食物-替换-确认"] == {
        "recognition": "TemplateMatch",
        "template": "daily/EAT_STAMINA_FOOD_DAILY/food_buff_replace_confirm.png",
        "roi": [780, 450, 250, 100],
        "threshold": 0.28,
        "action": "DoNothing",
    }
    assert "ColorMatch" not in json.dumps(item_entry, ensure_ascii=False)


def test_food_graph_has_no_obsolete_home_color_entry() -> None:
    scoped = _scoped_nodes()

    entry = scoped["0007-吃体力食物-任务入口"]
    assert entry["recognition"]["param"]["all_of"] == [
        "0412-吃体力食物-食物-主页-页面",
    ]
    assert entry["recognition"]["param"]["box_index"] == 0
    assert scoped["0382-吃体力食物-打开-资源"]["recognition"]["param"]["all_of"] == [
        "0412-吃体力食物-食物-主页-页面",
        "0413-吃体力食物-食物-资源-入口",
    ]
    assert scoped["0416-吃体力食物-食物-分类-页面"]["expected"] == [
        "消耗品",
        "食物",
        "料理",
    ]
    assert scoped["0417-吃体力食物-食物-食物-标签"]["expected"] == "食物"
    assert scoped["0393-吃体力食物-食用-龙井虾仁"]["recognition"]["param"]["all_of"] == [
        "0420-吃体力食物-食物-详情",
        "0422-吃体力食物-食物-使用-目标",
        "0423-吃体力食物-食物-当前拥有",
    ]
    assert scoped["0413-吃体力食物-食物-资源-入口"]["recognition"] != "ColorMatch"
    assert "0, 90, 70, 100" not in json.dumps(scoped, ensure_ascii=False)


def test_food_finishes_after_exactly_six_use_clicks_without_post_use_state_recognition() -> None:
    scoped = _scoped_nodes()
    use = scoped["0393-吃体力食物-食用-龙井虾仁"]
    replacement = scoped["0399-吃体力食物-替换-确认-循环"]
    budget = scoped["0400-吃体力食物-六次点击-成功"]
    failure_cleanup = scoped["0405-吃体力食物-失败-返回主页"]

    assert "0392-吃体力食物-六次上限-成功" not in scoped
    assert "0406-吃体力食物-吃得太撑-成功" not in scoped
    assert "0407-吃体力食物-吃得太撑-关闭-背包" not in scoped
    assert "0408-吃体力食物-六次上限-详情-成功" not in scoped
    assert "吃得太撑" not in json.dumps(scoped, ensure_ascii=False)
    assert "FoodTooFullTerminal" not in json.dumps(scoped, ensure_ascii=False)

    assert use["timeout"] == 8000
    assert use["recognition"]["param"]["box_index"] == 1
    assert use["next"] == [
        "0399-吃体力食物-替换-确认-循环",
        "0400-吃体力食物-六次点击-成功",
        "0385-吃体力食物-候选-循环",
    ]
    assert use["on_error"] == ["0404-吃体力食物-关闭-背包"]
    assert replacement["next"] == [
        "0400-吃体力食物-六次点击-成功",
        "0385-吃体力食物-候选-循环",
    ]
    assert replacement["on_error"] == ["0400-吃体力食物-六次点击-成功"]
    assert budget["recognition"] == "DirectHit"
    assert budget["custom_action"] == "FoodBudgetReached"
    assert budget["custom_action_param"] == {
        "task_id": FOOD.task_id,
        "action_id": "eat_longjing_shrimp",
        "limit": 6,
    }
    assert budget["next"] == ["0401-吃体力食物-六次点击-关闭背包"]
    close_after_six = scoped["0401-吃体力食物-六次点击-关闭背包"]
    assert close_after_six["custom_action"] == "GuardedInput"
    assert close_after_six["custom_action_param"]["action_id"] == "close_bag"
    assert close_after_six["max_hit"] == 2
    assert close_after_six["post_delay"] == 1000
    assert close_after_six["next"] == [
        "0401-吃体力食物-六次点击-关闭背包",
        "1371-公共-原生成功-主页边界",
    ]
    assert close_after_six["on_error"] == ["0405-吃体力食物-失败-返回主页"]
    assert failure_cleanup["custom_action"] == "ReturnToWorldHome"
    assert failure_cleanup["next"] == ["1365-公共-主页边界-失败"]
    assert failure_cleanup["on_error"] == ["1365-公共-主页边界-失败"]


def test_food_preserves_longjing_shrimp_action_contract() -> None:
    scoped = _scoped_nodes()
    action = scoped["0393-吃体力食物-食用-龙井虾仁"]["custom_action_param"]
    assert action["task_id"] == FOOD.task_id
    assert action["action_id"] == "eat_longjing_shrimp"
    assert action["kind"] == "click"
    assert action["evidence"]["target_index"] == 1
    assert scoped["0385-吃体力食物-候选-循环"]["max_hit"] == 6
    assert scoped["0385-吃体力食物-候选-循环"]["on_error"] == [
        "0405-吃体力食物-失败-返回主页",
    ]
    assert scoped["0393-吃体力食物-食用-龙井虾仁"]["next"] == [
        "0399-吃体力食物-替换-确认-循环",
        "0400-吃体力食物-六次点击-成功",
        "0385-吃体力食物-候选-循环",
    ]
    assert scoped["0399-吃体力食物-替换-确认-循环"]["next"] == [
        "0400-吃体力食物-六次点击-成功",
        "0385-吃体力食物-候选-循环",
    ]
    assert scoped["0399-吃体力食物-替换-确认-循环"]["on_error"] == [
        "0400-吃体力食物-六次点击-成功",
    ]


def test_food_has_no_obsolete_recorder_or_custom_outcome() -> None:
    scoped = _scoped_nodes()
    assert_no_custom_outcome_nodes(scoped)
    assert RECORDER not in scoped
