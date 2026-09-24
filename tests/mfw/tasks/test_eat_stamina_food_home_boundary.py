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
    close_panel = scoped["0410-吃体力食物-关闭-残留功能面板"]
    open_resource = scoped["0382-吃体力食物-打开-资源"]
    item_entry = scoped["0413-吃体力食物-食物-资源-入口"]

    assert item_entry["recognition"] == "OCR"
    assert item_entry["expected"] == "(?:道)?具"
    assert item_entry["roi"] == [980, 580, 300, 140]
    assert entry["custom_action"] == "BeginTask"
    assert entry["custom_action_param"] == {"task_id": FOOD.task_id}
    assert entry["next"] == [
        "0410-吃体力食物-关闭-残留功能面板",
        "0382-吃体力食物-打开-资源",
    ]
    assert close_panel["custom_action"] == "GuardedInput"
    assert close_panel["custom_action_param"]["action_id"] == "close_function_panel"
    assert close_panel["custom_action_param"]["fixed_click_mode"] == "function_panel_close"
    assert close_panel["next"] == ["0382-吃体力食物-打开-资源"]
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
    assert scoped["0410-吃体力食物-关闭-残留功能面板"]["recognition"]["param"]["all_of"] == [
        "0412-吃体力食物-食物-主页-页面",
        "0031-公共-已知-面板-标记",
        "0032-公共-已知-面板-关闭",
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
        "0421-吃体力食物-食物-龙井虾仁-名称",
    ]
    assert scoped["0413-吃体力食物-食物-资源-入口"]["recognition"] != "ColorMatch"
    assert "0, 90, 70, 100" not in json.dumps(scoped, ensure_ascii=False)


def test_food_requires_observed_quantity_decrement_before_continuing() -> None:
    nodes = _scoped_nodes()
    use = nodes["0393-吃体力食物-食用-龙井虾仁"]
    verify = nodes["0400-吃体力食物-消耗数量-确认"]
    failure = ["0405-吃体力食物-失败-返回主页"]
    assert use["custom_action_param"]["resource_id"] == "龙井虾仁"
    assert use["custom_action_param"]["budget_amount"] == 1
    assert use["custom_action_param"]["amount_index"] == 2
    assert use["custom_action_param"]["resource_index"] == 3
    assert verify["recognition"]["param"]["all_of"] == [
        "0420-吃体力食物-食物-详情",
        "0421-吃体力食物-食物-龙井虾仁-名称",
        "0424-吃体力食物-食物-消耗后数量",
    ]
    assert nodes["0424-吃体力食物-食物-消耗后数量"]["expected"] == "(?!)"
    assert verify["custom_action"] == "FoodConsumptionConfirmed"
    for name in [
        "0383-吃体力食物-打开-分类",
        "0393-吃体力食物-食用-龙井虾仁",
        "0399-吃体力食物-替换-确认-循环",
        "0400-吃体力食物-消耗数量-确认",
    ]:
        assert nodes[name]["on_error"] == failure
    assert "0404-吃体力食物-关闭-背包" not in nodes
    assert "六次点击" not in json.dumps(nodes, ensure_ascii=False)
    assert nodes["0406-吃体力食物-今日已吃满"]["expected"] == "吃得太撑"
    # The game's refusal toast appeared at y=315, not in the top navigation.
    x, y, width, height = nodes["0406-吃体力食物-今日已吃满"]["roi"]
    assert x <= 404 and x + width >= 900
    assert y <= 315 and y + height >= 342
    assert nodes["0405-吃体力食物-失败-返回主页"]["next"] == ["1365-公共-主页边界-失败"]


def test_food_has_no_obsolete_recorder_or_custom_outcome() -> None:
    scoped = _scoped_nodes()
    assert_no_custom_outcome_nodes(scoped)
    assert RECORDER not in scoped
