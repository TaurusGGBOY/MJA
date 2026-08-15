import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GAME_START = ROOT / "assets/resource/base/pipeline/startup/game_start.json"
TERMINAL = ROOT / "assets/resource/base/pipeline/common/terminal.json"


def test_r15_restart_retries_five_bounded_start_attempts() -> None:
    startup = json.loads(GAME_START.read_text(encoding="utf-8"))
    terminal = json.loads(TERMINAL.read_text(encoding="utf-8"))

    wait_after_restart = startup["MJA_GAME_START_AFTER_RESTART"]
    restart = terminal["MJA_COMMON_STARTUP_RECOVERY_RESTART"]

    assert restart["next"] == ["MJA_GAME_START_AFTER_RESTART"]
    assert restart["on_error"] == ["MJA_GAME_START_APP_RESTART_FAILED"]
    assert wait_after_restart["recognition"] == "DirectHit"
    assert wait_after_restart["post_delay"] == 20000
    assert wait_after_restart["next"] == ["MJA_START_GAME_BUTTON_AFTER_RESTART"]
    for attempt in range(2, 6):
        retry = startup[f"MJA_GAME_START_RETRY_{attempt}"]
        wait = startup[f"MJA_GAME_START_AFTER_RESTART_{attempt}"]
        button = startup[f"MJA_START_GAME_BUTTON_AFTER_RESTART_{attempt}"]
        assert retry["custom_action"] == "RestartGameSurface"
        assert retry["next"] == [f"MJA_GAME_START_AFTER_RESTART_{attempt}"]
        assert wait["post_delay"] == 20000
        assert button["action"] == "Click"
    assert startup["MJA_START_GAME_BUTTON_AFTER_RESTART_5"]["on_error"] == [
        "MJA_GAME_START_START_BUTTON_NOT_FOUND"
    ]
    assert "MJA_GAME_LAUNCH" not in startup
