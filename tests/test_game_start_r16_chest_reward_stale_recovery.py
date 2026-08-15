import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GAME_START = ROOT / "assets/resource/base/pipeline/startup/game_start.json"


def test_r16_stale_chest_is_not_a_game_start_recovery_gate() -> None:
    startup = json.loads(GAME_START.read_text(encoding="utf-8"))

    assert "启动-过期-宝箱-奖励-恢复" in startup
    assert startup["启动-游戏启动"]["next"] == ["启动-游戏就绪"]
    assert "[JumpBack]启动-过期-宝箱-奖励-恢复" not in startup[
        "启动-游戏启动"
    ].get("next", [])

