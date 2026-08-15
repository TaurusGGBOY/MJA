import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GAME_START = ROOT / "assets/resource/base/pipeline/startup/game_start.json"


def test_r17_black_screen_is_not_a_game_start_color_gate() -> None:
    startup = json.loads(GAME_START.read_text(encoding="utf-8"))

    assert "MJA_START_BLACK_SCREEN_WAIT" in startup
    assert "MJA_START_PERSISTENT_BLACK_SCREEN_RECOVERY" in startup
    assert startup["MJA_GAME_START"]["next"] == ["MJA_GAME_READY"]
    assert not any(
        name in startup["MJA_GAME_START"]["next"]
        for name in (
            "MJA_START_BLACK_SCREEN_WAIT",
            "MJA_START_PERSISTENT_BLACK_SCREEN_RECOVERY",
        )
    )

