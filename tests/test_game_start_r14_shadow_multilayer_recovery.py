import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GAME_START = ROOT / "assets/resource/base/pipeline/startup/game_start.json"


def test_r14_shadow_recovery_definitions_are_not_in_the_startup_route() -> None:
    startup = json.loads(GAME_START.read_text(encoding="utf-8"))
    route = startup["启动-游戏启动"]["next"]

    assert route == ["启动-游戏就绪"]
    assert "[JumpBack]启动-影-页面-返回" not in route
    assert "[JumpBack]启动-影-探索-页面-返回" not in route

