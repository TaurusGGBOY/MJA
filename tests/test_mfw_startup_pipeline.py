from __future__ import annotations

import json
from pathlib import Path

from tests.mfw.pipeline_assertions import assert_all_cycles_bounded, load_nodes


ROOT = Path(__file__).parents[1]
STARTUP_PATH = ROOT / "assets/resource/base/pipeline/startup/game_start.json"
PUBLIC_HOME_ROI = [920, 540, 220, 100]


def _startup() -> dict[str, dict]:
    return json.loads(STARTUP_PATH.read_text(encoding="utf-8"))


def test_game_start_is_a_startup_only_pipeline_without_restart_named_nodes() -> None:
    startup = _startup()

    assert not any("重启" in name for name in startup)
    assert startup["0023-启动-游戏入口"]["next"] == ["1356-启动-游戏启动"]
    assert "on_error" not in startup["0023-启动-游戏入口"]
    assert startup["1356-启动-游戏启动"]["on_error"] == ["关闭游戏"]
    assert "1371-公共-原生成功-主页边界" not in json.dumps(startup, ensure_ascii=False)
    assert "1358-公共-游戏启动失败" not in json.dumps(startup, ensure_ascii=False)
    assert "启动-世界页-探测" not in startup
    assert "启动-世界页-探测" not in json.dumps(startup, ensure_ascii=False)


def test_game_start_keeps_the_five_start_reliability_contract() -> None:
    start = _startup()["1356-启动-游戏启动"]
    assert start["action"] == "StartApp"
    assert start["package"] == "com.hanjiasongshu.dr22/.MainActivity"
    assert start["repeat"] == 5
    assert start["repeat_delay"] == 1000
    assert start["timeout"] == 120000
    assert start["next"] == [
        "[JumpBack]1379-启动-关闭装备残留页",
        "[JumpBack]1376-启动-关闭副本残留页",
        "[JumpBack]1373-启动-关闭剑林残留页",
        "[JumpBack]1359-启动-可选关闭公告页",
        "[JumpBack]1360-启动-数据校验失败-继续下载",
        "1357-启动-游戏启动成功-左下12探测",
        "1362-启动-游戏就绪",
    ]


def test_startup_button_flow_has_no_restart_aliases() -> None:
    startup = _startup()
    enter_button = startup["1370-启动-游戏启动后-进入按钮"]
    setting_probe = startup["1357-启动-游戏启动成功-左下12探测"]
    announcement = startup["1359-启动-可选关闭公告页"]

    assert "启动-游戏启动后-开始按钮" not in startup
    assert "启动-游戏启动-启动" not in startup
    # The title flow has two distinct visible buttons: 点击开始游戏, then 进入游戏.
    # Each receives one bounded tap inside their live overlapping text area.
    assert enter_button["max_hit"] == 2
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
        "[JumpBack]1361-启动-可选关闭月签到奖励页",
        "[JumpBack]1370-启动-游戏启动后-进入按钮",
        "1362-启动-游戏就绪",
    ]
    data_check = startup["1360-启动-数据校验失败-继续下载"]
    assert data_check["expected"] == ["允许下载", "继续下载"]
    assert data_check["roi"] == [630, 450, 330, 80]
    assert data_check["action"] == "Click"
    assert data_check["target"] == [650, 450, 300, 80]
    assert data_check["post_delay"] == 1000
    assert "next" not in data_check
    assert "on_error" not in data_check
    assert "on_error" not in setting_probe
    close_game = startup["关闭游戏"]
    assert close_game["action"] == "StopApp"
    assert close_game["package"] == "com.hanjiasongshu.dr22"
    assert close_game["max_hit"] == 1
    assert close_game["next"] == ["1356-启动-游戏启动"]
    assert "启动-可选关闭奖励弹窗-图像" not in startup
    assert "next" not in startup["1361-启动-可选关闭月签到奖励页"]
    assert "next" not in enter_button
    assert "on_error" not in enter_button
    assert "启动-进入游戏后等待" not in startup
    assert "启动-欢迎页-进入游戏" not in startup
    assert _startup()["1356-启动-游戏启动"]["next"] == [
        "[JumpBack]1379-启动-关闭装备残留页",
        "[JumpBack]1376-启动-关闭副本残留页",
        "[JumpBack]1373-启动-关闭剑林残留页",
        "[JumpBack]1359-启动-可选关闭公告页",
        "[JumpBack]1360-启动-数据校验失败-继续下载",
        "1357-启动-游戏启动成功-左下12探测",
        "1362-启动-游戏就绪",
    ]
    assert enter_button["target"] == [575, 620, 120, 25]
    assert enter_button["post_delay"] == 10000
    residual = startup["1373-启动-关闭剑林残留页"]
    assert residual["recognition"]["param"] == {
        "all_of": [
            "1374-启动-剑林残留页-标题",
            "1375-启动-剑林残留页-关闭",
        ],
        "box_index": 1,
    }
    assert residual["action"] == "Click"
    assert residual["target"] == [1205, 33, 18, 18]
    assert residual["max_hit"] == 1
    assert residual["post_delay"] == 1500
    dungeon_residual = startup["1376-启动-关闭副本残留页"]
    assert dungeon_residual["recognition"]["param"] == {
        "all_of": [
            "1377-启动-副本残留页-标题",
            "1378-启动-副本残留页-关闭",
        ],
        "box_index": 1,
    }
    assert dungeon_residual["action"] == "Click"
    assert dungeon_residual["target"] == [1202, 30, 24, 24]
    assert dungeon_residual["max_hit"] == 1
    assert dungeon_residual["post_delay"] == 1500
    equipment_residual = startup["1379-启动-关闭装备残留页"]
    assert equipment_residual["recognition"]["param"] == {
        "all_of": [
            "1380-启动-装备残留页-标题",
            "1381-启动-装备残留页-关闭",
        ],
        "box_index": 1,
    }
    assert equipment_residual["action"] == "Click"
    assert equipment_residual["target"] == [1202, 30, 24, 24]
    assert equipment_residual["max_hit"] == 1


def test_startup_confirms_the_single_public_home_boundary() -> None:
    nodes = load_nodes(ROOT / "assets/resource/base/pipeline")
    home = nodes["0026-公共-游戏主页-页面"]
    assert home == {
        "recognition": "OCR",
        "expected": ["已击破", "侠客", "道具", "载具", "成就"],
        "roi": PUBLIC_HOME_ROI,
        "action": "DoNothing",
    }
    assert "next" not in _startup()["1362-启动-游戏就绪"]


def test_startup_failures_are_stateless_native_failures() -> None:
    terminal = json.loads(
        (ROOT / "assets/resource/base/pipeline/common/terminal.json").read_text(
            encoding="utf-8"
        )
    )
    for name in (
        "1358-公共-游戏启动失败",
        "0039-公共-游戏启动开始按钮未找到",
        "0040-公共-游戏启动进入按钮未找到",
        "0041-公共-游戏启动主页未到达",
        "0042-公共-通用-启动恢复-耗尽",
    ):
        node = terminal[name]
        assert node["custom_action"] == "FailTask"
        assert node["Abort"] is True
        assert "custom_action_param" not in node


def test_startup_graph_is_bounded() -> None:
    assert_all_cycles_bounded(load_nodes(ROOT / "assets/resource/base/pipeline"))
