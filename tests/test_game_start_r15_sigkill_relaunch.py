import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GAME_START = ROOT / "assets/resource/base/pipeline/startup/game_start.json"
TERMINAL = ROOT / "assets/resource/base/pipeline/common/terminal.json"


def test_r15_restart_retries_five_bounded_start_attempts() -> None:
    startup = json.loads(GAME_START.read_text(encoding="utf-8"))
    terminal = json.loads(TERMINAL.read_text(encoding="utf-8"))

    wait_after_restart = startup["启动-游戏重启后"]
    restart = terminal["公共-通用-启动恢复-重启"]

    assert restart["next"] == ["启动-游戏重启后"]
    assert restart["on_error"] == ["公共-游戏启动应用重启失败"]
    assert wait_after_restart["recognition"] == "DirectHit"
    assert "post_delay" not in wait_after_restart
    assert wait_after_restart["next"] == ["启动-游戏-按钮-之后-重启"]
    for attempt in range(2, 6):
        retry = startup[f"启动-游戏启动重试-{attempt}"]
        wait = startup[f"启动-游戏重启后-{attempt}"]
        button = startup[f"启动-游戏-按钮-之后-重启-{attempt}"]
        assert retry["custom_action"] == "RestartGameSurface"
        assert retry["next"] == [f"启动-游戏重启后-{attempt}"]
        assert "post_delay" not in wait
        assert button["action"] == "Click"
    assert startup["启动-游戏-按钮-之后-重启-5"]["on_error"] == [
        "公共-游戏启动开始按钮未找到"
    ]
    assert "MJA_GAME_LAUNCH" not in startup
