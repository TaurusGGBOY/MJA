"""Celebration reuses the combat flow with independent page/session identity."""

import json
from pathlib import Path

from agent.custom.support.policy import TASK_POLICIES
from tools.check_mfw_resources import load_pipeline_nodes, validate_nodes

ROOT = Path(__file__).resolve().parents[3]
PIPELINES = ROOT / "assets/resource/base/pipeline"


def test_celebration_is_selectable_and_old_event_stays_retired():
    interface = json.loads((ROOT / "assets/interface.json").read_text())
    old = json.loads((ROOT / "assets/tasks/日常/BREAK_ARRAY_MARTIAL_DAILY.json").read_text())[
        "task"
    ][0]
    new = json.loads((ROOT / "assets/tasks/日常/CELEBRATION_MARTIAL_DAILY.json").read_text())[
        "task"
    ][0]
    assert old["name"] in interface["retired_tasks"]
    assert old["default_check"] is False
    assert new["name"] not in interface["retired_tasks"]
    assert "tasks/日常/CELEBRATION_MARTIAL_DAILY.json" in interface["import"]
    assert all(old["name"] != t["name"] for p in interface["preset"] for t in p["task"])


def test_clone_has_independent_nodes_and_safety_session_but_same_combat_limits():
    old = json.loads((PIPELINES / "daily/break_array_martial_daily.json").read_text())
    new = json.loads((PIPELINES / "daily/celebration_martial_daily.json").read_text())
    assert not (old.keys() & new.keys())
    for node in new.values():
        params = node.get("custom_action_param", {})
        if "task_id" in params:
            assert params["task_id"] == "CELEBRATION_MARTIAL_DAILY"
    for prefix in ("0108-", "0114-", "0115-", "0119-"):
        before = next(v for k, v in old.items() if k.startswith(prefix))
        after = next(v for k, v in new.items() if k.startswith(prefix))
        assert before["max_hit"] == after["max_hit"]
    assert (
        TASK_POLICIES["CELEBRATION_MARTIAL_DAILY"].action_caps
        == TASK_POLICIES["BREAK_ARRAY_MARTIAL_DAILY"].action_caps
    )
    assert not validate_nodes(load_pipeline_nodes(PIPELINES))


def test_live_activity_label_and_counter_gate_startup_close():
    nodes = json.loads((PIPELINES / "daily/celebration_martial_daily.json").read_text())
    label = nodes["0142-庆典演武-突破-阵法-已选择-入口"]
    assert label["expected"] == "庆典演武"
    x, y, w, h = label["roi"]
    assert x <= 64 and y <= 402 and x + w >= 141 and y + h >= 424
    assert y <= 507 and y + h >= 530
    page = nodes["0143-庆典演武-突破-阵法-页面"]["recognition"]["param"]["all_of"]
    assert page == ["0142-庆典演武-突破-阵法-已选择-入口", "0156-庆典演武-突破-阵法-剩余"]
    startup = json.loads((PIPELINES / "startup/game_start.json").read_text())
    close = startup["启动-关闭庆典演武残留页"]
    assert close["recognition"]["param"]["all_of"] == ["0143-庆典演武-突破-阵法-页面"]
    assert close["max_hit"] == 1
    assert close["target"] == [1200, 30, 25, 25]


def test_home_opens_activity_button_not_activity_page_title():
    nodes = json.loads((PIPELINES / "daily/celebration_martial_daily.json").read_text())
    button = nodes["0138-庆典演武-活动-入口"]
    assert "活动" in button["expected"]
    assert "启程" not in button["expected"]
    assert button["roi"] == [780, 20, 180, 100]


def test_explicit_failure_returns_home_before_native_failure():
    nodes = json.loads((PIPELINES / "daily/celebration_martial_daily.json").read_text())
    for prefix in ("0126-", "0131-", "0132-", "0133-", "0134-", "0135-"):
        node = next(v for k, v in nodes.items() if k.startswith(prefix))
        assert node["next"] == [
            "庆典演武-失败收尾-关闭结果",
            "庆典演武-失败收尾-关闭活动",
            "庆典演武-失败收尾-主页",
        ]
    assert nodes["庆典演武-失败收尾-主页"]["next"] == ["庆典演武-原生失败"]
    assert nodes["庆典演武-原生失败"]["custom_action"] == "FailTask"


def test_preparation_resume_preserves_the_consumed_attempt():
    import re

    nodes = json.loads((PIPELINES / "daily/celebration_martial_daily.json").read_text())
    pattern = nodes["0160-庆典演武-突破-阵法-准备-阵容"]["expected"]
    assert re.fullmatch(pattern, "阵容一")
    assert re.fullmatch(pattern, "阵容")
    assert not re.fullmatch(pattern, "阵容设置")
    entry = nodes["0002-庆典演武-任务入口"]
    assert entry["next"][:2] == ["0116-庆典演武-结果-探测", "0112-庆典演武-准备-页面-探测"]
    assert "0165-庆典演武-突破-阵法-准备-页面" in entry["recognition"]["param"]["any_of"]
    assert nodes["0110-庆典演武-确认-挑战"]["timeout"] == 30000
    assert nodes["庆典演武-准备就绪"]["custom_action"] == "RuntimeHealth"


def test_new_victory_card_requires_title_and_statistics_icon():
    nodes = json.loads((PIPELINES / "daily/celebration_martial_daily.json").read_text())
    title = "0171-庆典演武-突破-阵法-结果-胜利-标题"
    icon = "0172-庆典演武-突破-阵法-结果-标识"
    for name in ("0168-庆典演武-突破-阵法-结果", "0170-庆典演武-突破-阵法-成功"):
        assert nodes[name]["recognition"]["param"]["all_of"] == [title, icon]
    assert nodes[icon]["recognition"] == "TemplateMatch"
    assert nodes[icon]["roi"] == [1180, 0, 100, 100]
    assert (ROOT / "assets/resource/base/image" / nodes[icon]["template"]).is_file()
    assert nodes["庆典演武-结果就绪"]["custom_action"] == "RuntimeHealth"


def test_activity_closes_once_before_waiting_for_home():
    nodes = json.loads((PIPELINES / "daily/celebration_martial_daily.json").read_text())
    close = nodes["0128-庆典演武-完成-关闭-阵法"]
    assert close["next"] == ["0130-庆典演武-完成-主页-探测"]
    assert close["post_delay"] >= 1000
