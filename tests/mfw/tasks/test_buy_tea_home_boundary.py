from __future__ import annotations

from collections.abc import Mapping

from tests.mfw.task_contract import TaskContract, load_task_nodes


TEA = TaskContract("BUY_TEA_DAILY", "daily/buy_tea_daily.json")
NORMAL_OUTCOMES = ("买茶-售罄", "买茶-结果-成功", "买茶-已完成")


def _targets(node: Mapping[str, object]) -> list[str]:
    targets: list[str] = []
    for field in ("next", "on_error"):
        value = node.get(field, [])
        values = [value] if isinstance(value, str) else value
        if not isinstance(values, list):
            continue
        targets.extend(target for target in values if isinstance(target, str))
    return targets


def _reachable(nodes: Mapping[str, Mapping[str, object]], source: str, target: str) -> bool:
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


def test_normal_buy_tea_outcomes_cleanup_to_home_boundary() -> None:
    nodes = load_task_nodes(TEA)

    for outcome_name in NORMAL_OUTCOMES:
        outcome = nodes[outcome_name]
        params = outcome["custom_action_param"]
        assert params["defer_home_boundary"] is True
        assert outcome["next"] == ["买茶-完成-收尾"]
        assert _reachable(nodes, outcome_name, "公共-主页边界")
        assert _reachable(nodes, outcome_name, "公共-通用停止")

    cleanup = nodes["买茶-完成-收尾"]
    assert cleanup["max_hit"] == 4
    assert cleanup["next"] == [
        "[JumpBack]公共-已知-茶-详情-关闭",
        "[JumpBack]公共-已知-茶-商店-关闭",
        "[JumpBack]公共-已知-画卷-关闭",
        "买茶-完成-主页-探测",
    ]
    assert nodes["买茶-完成-主页-探测"]["next"] == ["公共-主页边界"]


def test_buy_tea_failure_path_defers_abort_until_home_boundary() -> None:
    nodes = load_task_nodes(TEA)
    failure = nodes["买茶-记录-失败"]
    assert failure["custom_action_param"]["status"] == "failed"
    assert failure["custom_action_param"]["defer_home_boundary"] is True
    assert "native_fail_after_record" not in failure["custom_action_param"]
    assert "Abort" not in failure
    assert failure["next"] == ["公共-通用中止"]


def test_buy_tea_painting_entry_uses_world_image_and_action_specific_anchor() -> None:
    nodes = load_task_nodes(TEA)
    entry = nodes["买茶-打开-画卷"]
    target = nodes["买茶-茶-画卷-滚动-入口"]

    assert target["recognition"] == "TemplateMatch"
    assert target["template"] == "home/home_marker.png"
    assert target["roi"] == [1040, 0, 240, 110]
    assert target["threshold"] == 0.375
    assert entry["custom_action_param"]["fixed_click_mode"] == (
        "painting_scroll_button"
    )
