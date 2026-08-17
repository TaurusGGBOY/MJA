from __future__ import annotations

import json
from pathlib import Path

from tests.mfw.pipeline_assertions import assert_all_cycles_bounded, load_nodes


ROOT = Path(__file__).parents[1]
STARTUP_PATH = ROOT / "assets/resource/base/pipeline/startup/game_start.json"
PUBLIC_HOME_ROI = [920, 650, 220, 60]


def _startup() -> dict[str, dict]:
    return json.loads(STARTUP_PATH.read_text(encoding="utf-8"))


def test_game_start_is_a_startup_only_pipeline_without_restart_named_nodes() -> None:
    startup = _startup()

    assert not any("重启" in name for name in startup)
    assert startup["启动-游戏入口"]["next"] == ["启动-游戏启动"]
    assert "on_error" not in startup["启动-游戏入口"]
    assert startup["启动-游戏启动"]["on_error"] == ["公共-游戏启动失败"]
    assert "启动-世界页-探测" not in startup
    assert "启动-世界页-探测" not in json.dumps(startup, ensure_ascii=False)


def test_game_start_keeps_the_five_start_reliability_contract() -> None:
    start = _startup()["启动-游戏启动"]
    assert start["action"] == "StartApp"
    assert start["package"] == "com.hanjiasongshu.dr22/.MainActivity"
    assert start["repeat"] == 5
    assert start["repeat_delay"] == 1000
    assert start["next"] == [
        "[JumpBack]启动-可选关闭公告页",
        "启动-游戏启动成功-左下12探测",
    ]


def test_startup_button_flow_has_no_restart_aliases() -> None:
    startup = _startup()
    enter_button = startup["启动-游戏启动后-进入按钮"]
    setting_probe = startup["启动-游戏启动成功-左下12探测"]
    announcement = startup["启动-可选关闭公告页"]

    assert "启动-游戏启动后-开始按钮" not in startup
    assert "启动-游戏启动-启动" not in startup
    assert enter_button["max_hit"] == 5
    assert setting_probe["recognition"] == "OCR"
    assert setting_probe["expected"] == "^12\\+?$"
    assert setting_probe["roi"] == [0, 560, 540, 160]
    assert setting_probe["timeout"] == 200000
    assert announcement == {
        "recognition": "OCR",
        "expected": "公告|公|告",
        "roi": [0, 0, 420, 520],
        "timeout": 1500,
        "max_hit": 1,
        "action": "Click",
        "target": [1160, 0, 120, 100],
        "post_delay": 1000,
    }
    assert setting_probe["next"] == [
        "[JumpBack]启动-数据校验失败-继续下载",
        "[JumpBack]启动-可选关闭月签到奖励页",
        "[JumpBack]启动-游戏启动后-进入按钮",
        "启动-游戏就绪",
    ]
    data_check = startup["启动-数据校验失败-继续下载"]
    assert "next" not in data_check
    assert "on_error" not in data_check
    assert setting_probe["on_error"] == ["公共-游戏启动失败"]
    assert "启动-可选关闭奖励弹窗-图像" not in startup
    assert "next" not in startup["启动-可选关闭月签到奖励页"]
    assert "next" not in enter_button
    assert "on_error" not in enter_button
    assert "启动-进入游戏后等待" not in startup
    assert "启动-欢迎页-进入游戏" not in startup
    assert _startup()["启动-游戏启动"]["next"] == [
        "[JumpBack]启动-可选关闭公告页",
        "启动-游戏启动成功-左下12探测",
    ]
    assert enter_button["target"] == [430, 600, 420, 100]


def test_startup_confirms_the_single_public_home_boundary() -> None:
    nodes = load_nodes(ROOT / "assets/resource/base/pipeline")
    home = nodes["公共-游戏主页-页面"]
    assert home == {
        "recognition": "OCR",
        "expected": "已击破",
        "roi": PUBLIC_HOME_ROI,
        "action": "DoNothing",
    }
    assert _startup()["启动-游戏就绪"]["next"] == ["公共-主页边界"]


def test_startup_graph_is_bounded() -> None:
    assert_all_cycles_bounded(load_nodes(ROOT / "assets/resource/base/pipeline"))
