import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GAME_START = ROOT / "assets/resource/base/pipeline/startup/game_start.json"


def test_r17_black_screen_is_not_a_game_start_color_gate() -> None:
    startup = json.loads(GAME_START.read_text(encoding="utf-8"))

    assert "启动-黑屏-屏幕-等待" in startup
    assert "启动-持续黑屏恢复" in startup
    assert startup["启动-游戏启动"]["next"] == ["启动-游戏就绪"]
    assert not any(
        name in startup["启动-游戏启动"]["next"]
        for name in (
            "启动-黑屏-屏幕-等待",
            "启动-持续黑屏恢复",
        )
    )

