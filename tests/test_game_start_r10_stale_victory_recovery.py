import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GAME_START = ROOT / "assets/resource/base/pipeline/startup/game_start.json"
KNOWN_POPUPS = ROOT / "assets/resource/base/pipeline/common/known_popups.json"

# Fresh r10 batch OCR evidence from 2026-08-13 16:49:45.128.
VICTORY_TEXT = "战斗胜利"
VICTORY_BOX = (745, 101, 500, 143)


def _contains(outer: tuple[int, int, int, int], inner: tuple[int, int, int, int]) -> bool:
    outer_x, outer_y, outer_width, outer_height = outer
    inner_x, inner_y, inner_width, inner_height = inner
    return (
        outer_x <= inner_x
        and outer_y <= inner_y
        and outer_x + outer_width >= inner_x + inner_width
        and outer_y + outer_height >= inner_y + inner_height
    )


def test_r10_stale_victory_result_has_exact_bounded_startup_recovery() -> None:
    startup = json.loads(GAME_START.read_text(encoding="utf-8"))
    popups = json.loads(KNOWN_POPUPS.read_text(encoding="utf-8"))
    route = startup["启动-游戏启动"]["next"]

    victory_name = "公共-已知-战斗胜利结果关闭"
    victory = popups[victory_name]
    victory_jump = f"[JumpBack]{victory_name}"
    failure_jump = "[JumpBack]公共-已知-战斗结果关闭"

    assert victory["recognition"] == "OCR"
    assert victory["expected"] == f"^{re.escape(VICTORY_TEXT)}$"
    assert victory["roi"] == [700, 60, 580, 220]
    assert _contains(tuple(victory["roi"]), VICTORY_BOX)
    assert victory["timeout"] == 5000
    assert victory["max_hit"] == 1
    assert victory["action"] == "Custom"
    assert victory["custom_action"] == "RestartGameSurface"
    assert victory["custom_action_param"] == {
        "package": "com.hanjiasongshu.dr22",
        "activity": "com.hanjiasongshu.dr22/.MainActivity",
    }
    assert victory["post_delay"] == 5000
    assert victory["next"] == ["启动-游戏启动"]
    assert "on_error" not in victory

    assert route.count(victory_jump) == 1
    assert route.count(failure_jump) == 1
    assert route.index("[JumpBack]公共-已知-网络-确认") < route.index(
        victory_jump
    )
    assert route.index("[JumpBack]公共-已知-资源更新确认") < route.index(
        victory_jump
    )
    assert route.index(victory_jump) + 1 == route.index(failure_jump)

    failure = popups["公共-已知-战斗结果关闭"]
    assert failure["recognition"]["param"]["all_of"] == [
        "公共-已知-战斗-失败-标题",
        "公共-已知-战斗-失败-详情",
    ]
    assert failure["timeout"] == 5000
    assert failure["max_hit"] == 1
    assert failure["custom_action"] == "RestartGameSurface"
    assert failure["post_delay"] == 5000
    assert failure["next"] == ["启动-游戏启动"]
    assert "on_error" not in failure
    assert popups["公共-已知-战斗-失败-标题"]["expected"] == "^战斗失败$"
    assert popups["公共-已知-战斗-失败-详情"]["expected"] == (
        "^可以通过以下途径提升$"
    )

    network = popups["公共-已知-网络-确认"]
    assert network["roi"] == [830, 350, 80, 130]
    assert network["max_hit"] == 1
