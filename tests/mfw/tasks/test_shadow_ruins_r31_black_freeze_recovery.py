from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path


PIPELINE = (
    Path(__file__).resolve().parents[3]
    / "assets/resource/base/pipeline/daily/shadow_ruins_daily.json"
)

EXPLORATION = "影之遗迹-探索-页面"
FOREGROUND = "影之遗迹-前台-循环"
RECOVERY = "影之遗迹-黑屏-冻结-恢复"
RESUME = "影之遗迹-黑屏-冻结-恢复继续"
START = "影之遗迹-任务入口"
HOME = "影之遗迹-主页-探测"
TERMINAL_HOME = "影之遗迹-主页边界-探测"
SUCCESS = "影之遗迹-记录-成功"
FAILURE = "影之遗迹-记录-失败"


def _nodes() -> dict[str, dict[str, object]]:
    return json.loads(PIPELINE.read_text(encoding="utf-8"))


def _incoming_edges(nodes: dict[str, dict[str, object]]) -> dict[str, set[str]]:
    incoming: dict[str, set[str]] = defaultdict(set)
    for source, node in nodes.items():
        for edge_name in ("next", "on_error"):
            edges = node.get(edge_name, [])
            if isinstance(edges, str):
                edges = [edges]
            for target in edges:
                if isinstance(target, str) and not target.startswith("[JumpBack]"):
                    incoming[target].add(source)
    return incoming


def test_r31_black_freeze_recovery_is_exact_bounded_and_click_free() -> None:
    nodes = _nodes()
    recovery = nodes[RECOVERY]

    assert recovery["recognition"] == "ColorMatch"
    assert recovery["upper"] == [0, 0, 0]
    assert recovery["lower"] == [0, 0, 0]
    assert recovery["connected"] is True
    assert recovery["count"] == 80000
    assert recovery["timeout"] == 5000
    assert recovery["max_hit"] == 1
    assert recovery["retry_times"] == 0

    assert recovery["action"] == "Custom"
    assert recovery["custom_action"] == "RestartGameSurface"
    assert recovery["custom_action_param"] == {
        "package": "com.hanjiasongshu.dr22",
        "activity": "com.hanjiasongshu.dr22/.MainActivity",
    }
    assert recovery["post_delay"] == 5000
    assert "target" not in recovery
    assert "target_offset" not in recovery
    assert recovery["next"] == [RESUME]
    assert recovery["on_error"] == [FAILURE]


def test_r31_black_freeze_recovery_is_private_to_exploration_successors() -> None:
    nodes = _nodes()
    incoming = _incoming_edges(nodes)

    assert incoming[RECOVERY] == {EXPLORATION, FOREGROUND}
    assert RECOVERY in nodes[EXPLORATION]["next"]
    assert RECOVERY in nodes[FOREGROUND]["next"]
    assert nodes[FOREGROUND]["next"].index(RECOVERY) < nodes[FOREGROUND][
        "next"
    ].index(EXPLORATION)

    for source in incoming[RECOVERY]:
        assert source.startswith("影之遗迹-")
    assert RECOVERY not in nodes[START].get("next", [])
    assert RECOVERY not in nodes[START].get("on_error", [])

    exact_black_nodes = {
        name
        for name, node in nodes.items()
        if node.get("recognition") == "ColorMatch"
        and node.get("upper") == [0, 0, 0]
        and node.get("lower") == [0, 0, 0]
        and node.get("connected") is True
        and node.get("count") == 80000
    }
    assert exact_black_nodes == {RECOVERY}


def test_r31_recovery_resumes_same_task_through_shared_start_without_success_escape() -> None:
    nodes = _nodes()
    resume = nodes[RESUME]

    assert resume["recognition"] == "DirectHit"
    assert resume["action"] == "DoNothing"
    assert resume["timeout"] == 120000
    assert resume["retry_times"] == 0
    assert resume["next"] == [HOME, "[JumpBack]启动-游戏启动"]
    assert resume["on_error"] == [FAILURE]

    assert TERMINAL_HOME not in resume["next"]
    assert SUCCESS not in resume["next"]
    assert START not in resume["next"]
    assert nodes[HOME]["next"] == ["影之遗迹-打开-画卷"]

    begin_nodes = {
        name
        for name, node in nodes.items()
        if node.get("custom_action") == "BeginTask"
    }
    assert begin_nodes == {START}
    assert _incoming_edges(nodes)[START] == set()

    failure = nodes[FAILURE]
    assert failure["custom_action_param"]["status"] == "failed"
    assert failure["custom_action_param"]["native_fail_after_record"] is True
    assert failure["Abort"] is True
    assert failure["next"] == ["公共-通用中止"]
