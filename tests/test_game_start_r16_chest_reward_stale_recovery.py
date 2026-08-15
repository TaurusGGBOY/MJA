import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GAME_START = ROOT / "assets/resource/base/pipeline/startup/game_start.json"


def test_r16_stale_chest_is_not_a_game_start_recovery_gate() -> None:
    startup = json.loads(GAME_START.read_text(encoding="utf-8"))

    assert "MJA_START_STALE_CHEST_REWARD_RECOVERY" in startup
    assert startup["MJA_GAME_START"]["next"] == ["MJA_GAME_READY"]
    assert "[JumpBack]MJA_START_STALE_CHEST_REWARD_RECOVERY" not in startup[
        "MJA_GAME_START"
    ].get("next", [])

