from __future__ import annotations

from collections.abc import Mapping

from tests.mfw.task_contract import TaskContract, load_task_nodes


FOOD = TaskContract("EAT_STAMINA_FOOD_DAILY", "daily/eat_stamina_food_daily.json")
NORMAL_OUTCOMES = (
    "吃体力食物-体力-已满",
    "吃体力食物-成功",
    "吃体力食物-无安全卡",
)


def _targets(node: Mapping[str, object]) -> list[str]:
    targets: list[str] = []
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
            targets.append(target)
    return targets


def _reachable(
    nodes: Mapping[str, Mapping[str, object]], source: str, target: str
) -> bool:
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


def test_normal_food_outcomes_cleanup_to_home_boundary() -> None:
    nodes = load_task_nodes(FOOD)

    for outcome_name in NORMAL_OUTCOMES:
        outcome = nodes[outcome_name]
        params = outcome["custom_action_param"]
        assert params["defer_home_boundary"] is True
        assert outcome["next"] == ["吃体力食物-收尾-主页-探测"]
        assert _reachable(nodes, outcome_name, "公共-主页边界")
        assert _reachable(nodes, outcome_name, "公共-通用停止")

    assert nodes["吃体力食物-重新检查-已满"]["next"] == [
        "吃体力食物-体力-已满-关闭-背包"
    ]
    assert nodes["吃体力食物-详情-探测"]["on_error"] == [
        "吃体力食物-无安全卡-关闭-背包"
    ]
    assert nodes["吃体力食物-之后-使用-进度-探测"]["on_error"] == [
        "吃体力食物-关闭-背包"
    ]

    close_bag = nodes["吃体力食物-关闭-背包"]
    assert close_bag["next"] == ["吃体力食物-成功"]
    assert close_bag["on_error"] == ["吃体力食物-记录-失败"]
    for close_name, outcome_name in (
        ("吃体力食物-体力-已满-关闭-背包", "吃体力食物-体力-已满"),
        ("吃体力食物-无安全卡-关闭-背包", "吃体力食物-无安全卡"),
    ):
        close = nodes[close_name]
        assert close["custom_action_param"]["action_id"] == "close_bag"
        assert close["custom_action_param"]["evidence"] == close_bag[
            "custom_action_param"
        ]["evidence"]
        assert close["next"] == [outcome_name]
        assert close["on_error"] == ["吃体力食物-记录-失败"]

    home_probe = nodes["吃体力食物-收尾-主页-探测"]
    assert home_probe["recognition"] == {
        "type": "And",
        "param": {
            "all_of": ["吃体力食物-食物-主页-页面"],
            "box_index": 0,
        },
    }
    assert home_probe["next"] == ["公共-主页边界"]
    assert home_probe["on_error"] == ["吃体力食物-记录-失败"]


def test_food_failure_path_remains_native_abort() -> None:
    nodes = load_task_nodes(FOOD)
    failure = nodes["吃体力食物-记录-失败"]

    assert failure["custom_action_param"]["status"] == "failed"
    assert failure["custom_action_param"]["native_fail_after_record"] is True
    assert failure["Abort"] is True
    assert failure["next"] == ["公共-通用中止"]
