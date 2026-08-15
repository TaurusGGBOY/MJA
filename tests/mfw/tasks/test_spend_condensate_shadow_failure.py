from __future__ import annotations

from tests.mfw.task_contract import TaskContract, assert_reachable, load_task_nodes


CONDENSATE = TaskContract(
    "SPEND_CONDENSATE_DAILY",
    "daily/spend_condensate_daily.json",
)


def test_shadow_world_surface_fails_closed_without_recovery_or_paid_input() -> None:
    nodes = load_task_nodes(CONDENSATE)

    painting = nodes["消耗凝结体-画卷-页面-探测"]
    assert painting["next"] == ["消耗凝结体-选择-偃武"]
    assert painting["on_error"] == [
        "消耗凝结体-影-页面-探测",
        "消耗凝结体-记录-失败",
    ]
    assert painting["retry_times"] == 0

    shadow = nodes["消耗凝结体-影-页面-探测"]
    assert shadow == {
        "recognition": "OCR",
        "expected": "蜃影武墟",
        "roi": [250, 350, 450, 160],
        "timeout": 8000,
        "action": "DoNothing",
        "next": ["消耗凝结体-记录-失败"],
        "on_error": ["消耗凝结体-记录-失败"],
        "retry_times": 0,
    }

    x, y, width, height = shadow["roi"]
    box_x, box_y, box_width, box_height = [326, 389, 282, 83]
    assert x <= box_x and y <= box_y
    assert box_x + box_width <= x + width
    assert box_y + box_height <= y + height

    assert shadow["action"] == "DoNothing"
    assert_reachable(
        nodes,
        "消耗凝结体-影-页面-探测",
        "消耗凝结体-记录-失败",
    )
    assert_reachable(nodes, "消耗凝结体-影-页面-探测", "公共-通用中止")
    assert nodes["消耗凝结体-记录-失败"]["custom_action"] == "RecordTaskOutcome"
    assert nodes["公共-通用中止"]["Abort"] is True


def test_painting_probe_no_longer_jumps_to_unverified_world_or_game_start() -> None:
    nodes = load_task_nodes(CONDENSATE)
    on_error = nodes["消耗凝结体-画卷-页面-探测"]["on_error"]

    assert "消耗凝结体-偃武-页面-探测" not in on_error
    assert "[JumpBack]启动-游戏启动" not in on_error
    assert "消耗凝结体-记录-失败" in on_error


def test_normal_outcomes_cleanup_to_home_boundary() -> None:
    nodes = load_task_nodes(CONDENSATE)

    for outcome_name in ("消耗凝结体-已完成", "消耗凝结体-成功"):
        outcome = nodes[outcome_name]
        assert outcome["custom_action_param"]["defer_home_boundary"] is True
        assert outcome["next"] == ["消耗凝结体-完成-收尾"]
        assert_reachable(nodes, outcome_name, "公共-主页边界")
        assert_reachable(nodes, outcome_name, "公共-通用停止")

    cleanup = nodes["消耗凝结体-完成-收尾"]
    assert cleanup["max_hit"] == 4
    assert cleanup["next"] == [
        "[JumpBack]公共-已知-画卷-关闭",
        "消耗凝结体-完成-主页-探测",
    ]
    assert nodes["消耗凝结体-完成-主页-探测"]["next"] == ["公共-主页边界"]
