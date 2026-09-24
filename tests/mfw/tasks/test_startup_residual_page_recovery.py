import json
from pathlib import Path

STARTUP_PIPELINE = (
    Path(__file__).resolve().parents[3]
    / "assets"
    / "resource"
    / "base"
    / "pipeline"
    / "startup"
    / "game_start.json"
)


def test_startup_has_no_business_task_restart_handoff() -> None:
    pipeline = json.loads(STARTUP_PIPELINE.read_text(encoding="utf-8"))
    start = pipeline["1356-启动-游戏启动"]
    assert start["action"] == "StartApp"
    assert start["repeat"] == 1
    assert start["max_hit"] == 1
    assert start["next"] == ["启动-等待游戏就绪"]
    start = pipeline["启动-等待游戏就绪"]
    assert start["timeout"] == 120000
    assert start["next"][-2:] == [
        "[JumpBack]1370-启动-游戏启动后-进入按钮",
        "1362-启动-游戏就绪",
    ]
    assert start["on_error"] == ["启动-游戏启动恢复", "关闭游戏", "1365-公共-主页边界-失败"]
    assert pipeline["启动-游戏启动恢复"]["action"] == "StopApp"
    assert pipeline["启动-游戏启动恢复"]["max_hit"] == 2
    assert pipeline["关闭游戏"]["max_hit"] == 1
    for node in pipeline.values():
        for edge in node.get("next", []) + node.get("on_error", []):
            assert "任务入口" not in edge
