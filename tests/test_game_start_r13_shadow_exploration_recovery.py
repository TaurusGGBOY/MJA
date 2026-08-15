import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GAME_START = ROOT / "assets/resource/base/pipeline/startup/game_start.json"


def test_r13_shadow_exploration_is_not_a_game_start_gate_anymore() -> None:
    startup = json.loads(GAME_START.read_text(encoding="utf-8"))
    route = startup["启动-游戏启动"]["next"]

    assert route == ["启动-游戏就绪"]
    assert "[JumpBack]启动-影-页面-返回" not in route
    assert "[JumpBack]启动-影-探索-页面-返回" not in route

