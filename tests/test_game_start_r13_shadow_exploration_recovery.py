import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GAME_START = ROOT / "assets/resource/base/pipeline/startup/game_start.json"


def test_r13_shadow_exploration_is_not_a_game_start_gate_anymore() -> None:
    startup = json.loads(GAME_START.read_text(encoding="utf-8"))
    route = startup["MJA_GAME_START"]["next"]

    assert route == ["MJA_GAME_READY"]
    assert "[JumpBack]MJA_START_SHADOW_PAGE_BACK" not in route
    assert "[JumpBack]MJA_START_SHADOW_EXPLORATION_PAGE_BACK" not in route

