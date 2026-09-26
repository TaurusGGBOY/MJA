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
    assert startup["0023-启动-游戏入口"]["next"] == [
        "[JumpBack]启动-Pixel启动器无响应-关闭",
        "庆典演武-结果就绪",
        "庆典演武-准备就绪",
        "[JumpBack]启动-关闭庆典演武残留页",
        "1362-启动-游戏就绪",
        "1356-启动-游戏启动",
    ]
    assert "on_error" not in startup["0023-启动-游戏入口"]
    assert startup["1356-启动-游戏启动"]["on_error"] == [
        "启动-游戏启动恢复",
        "关闭游戏",
        "1365-公共-主页边界-失败",
    ]
    recovery = startup["启动-游戏启动恢复"]
    assert recovery["action"] == "StopApp"
    assert recovery["package"] == "com.hanjiasongshu.dr22"
    assert recovery["post_delay"] == 2000
    relaunch = startup["启动-恢复后重新启动"]
    assert relaunch["action"] == "StartApp"
    assert relaunch["package"] == startup["1356-启动-游戏启动"]["package"]
    assert relaunch["max_hit"] == 2
    assert relaunch["next"] == ["启动-等待游戏就绪"]
    assert recovery["timeout"] == 30000
    assert recovery["max_hit"] == 2
    assert recovery["next"] == ["启动-恢复后重新启动"]
    assert "1371-公共-原生成功-主页边界" not in json.dumps(startup, ensure_ascii=False)
    assert "1358-公共-游戏启动失败" not in json.dumps(startup, ensure_ascii=False)
    assert "启动-世界页-探测" not in startup
    assert "启动-世界页-探测" not in json.dumps(startup, ensure_ascii=False)


def test_game_start_launches_once_then_observes_a_bounded_state_scan() -> None:
    start = _startup()["1356-启动-游戏启动"]
    assert start["action"] == "StartApp"
    assert start["package"] == "com.hanjiasongshu.dr22/.MainActivity"
    assert start["repeat"] == 1
    assert start["max_hit"] == 1
    assert start["timeout"] == 5000
    assert start["next"] == ["启动-等待游戏就绪"]
    # A waiting or absent game must not drive the full OCR list every second.
    assert _startup()["启动-等待游戏就绪"]["rate_limit"] == 3000
    exited = _startup()["启动-进程退出后恢复"]
    recovery = _startup()["启动-游戏启动恢复"]
    assert exited["max_hit"] == recovery["max_hit"] + 1
    assert exited["next"] == [
        "启动-游戏启动恢复", "关闭游戏", "1365-公共-主页边界-失败"
    ]
    assert _startup()["关闭游戏"]["next"] == ["1365-公共-主页边界-失败"]
    start = _startup()["启动-等待游戏就绪"]
    assert start["timeout"] == 120000
    assert start["max_hit"] == 3
    assert start["next"] == [
        "[JumpBack]启动-Pixel启动器无响应-关闭",
        "[JumpBack]启动-关闭庆典演武残留页",
        "启动-进程退出后恢复",
        "[JumpBack]启动-奖励弹窗-点击空白关闭",
        "[JumpBack]启动-七星阵法引导-探寻",
        "[JumpBack]启动-七星阵法引导-跳过",
        "[JumpBack]0038-公共-已知-点击空白关闭",
        "[JumpBack]1277-公共-已知-画卷-关闭",
        "[JumpBack]1394-启动-关闭武学研习详情残留页",
        "[JumpBack]1385-启动-关闭帮会奖励预览残留页",
        "[JumpBack]1388-启动-关闭帮会活动残留页",
        "[JumpBack]1391-启动-关闭帮会主页残留页",
        "[JumpBack]1393-启动-关闭功能面板残留页",
        "[JumpBack]1382-启动-关闭武学研习残留页",
        "[JumpBack]1379-启动-关闭装备残留页",
        "[JumpBack]1376-启动-关闭副本残留页",
        "[JumpBack]1373-启动-关闭剑林残留页",
        "[JumpBack]1359-启动-可选关闭公告页",
        "[JumpBack]1360-启动-数据校验失败-继续下载",
        "[JumpBack]1361-启动-可选关闭月签到奖励页",
        "[JumpBack]1370-启动-游戏启动后-进入按钮",
        "1362-启动-游戏就绪",
    ]


def test_startup_closes_residual_reward_overlay_before_ready_gate() -> None:
    startup = _startup()
    popup = startup["启动-奖励弹窗-点击空白关闭"]

    assert popup["recognition"] == "OCR"
    assert popup["expected"] == "^恭喜获得$"
    assert popup["roi"] == [120, 180, 180, 360]
    assert popup["action"] == "Click"
    assert popup["target"] == [550, 665, 180, 45]
    assert popup["post_delay"] == 1000
    assert startup["启动-等待游戏就绪"]["next"].index(
        "[JumpBack]启动-奖励弹窗-点击空白关闭"
    ) < startup["启动-等待游戏就绪"]["next"].index("1362-启动-游戏就绪")


def test_startup_advances_and_skips_the_seven_star_tutorial_overlay() -> None:
    startup = _startup()
    prompt = startup["启动-七星阵法引导-探寻"]
    skip = startup["启动-七星阵法引导-跳过"]

    assert prompt["expected"] == "^阁主，七星阵法已现世，点击$"
    assert prompt["roi"] == [380, 390, 360, 110]
    assert prompt["target"] == [640, 610, 140, 105]
    assert skip["expected"] == "^跳过$"
    assert skip["roi"] == [1040, 35, 160, 100]
    assert skip["target"] == [1060, 45, 130, 75]


def test_startup_button_flow_uses_the_visible_button_and_shared_recovery() -> None:
    import re

    startup = _startup()
    enter_button = startup["1370-启动-游戏启动后-进入按钮"]
    assert "1357-启动-游戏启动成功-左下12探测" not in startup
    assert enter_button["max_hit"] == 6
    assert enter_button["target"] is True
    assert enter_button["roi"] == [350, 540, 580, 120]
    patterns = enter_button["expected"]
    for label in ("点击开始游戏！", "进入游戏", "点击进入游戏!"):
        assert any(re.search(pattern, label) for pattern in patterns)
    for label in ("12+", "游戏著作权人", "戏", "正在连接服务器"):
        assert not any(re.search(pattern, label) for pattern in patterns)
    # Every post-launch screen returns to the same bounded state scan.
    assert "[JumpBack]1370-启动-游戏启动后-进入按钮" in startup["启动-等待游戏就绪"]["next"]
    assert startup["1356-启动-游戏启动"]["on_error"] == [
        "启动-游戏启动恢复",
        "关闭游戏",
        "1365-公共-主页边界-失败",
    ]
    assert "next" not in enter_button
    assert startup["1361-启动-可选关闭月签到奖励页"]["max_hit"] == 3
    assert startup["1361-启动-可选关闭月签到奖励页"]["post_delay"] == 5000
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
    martial_residual = startup["1382-启动-关闭武学研习残留页"]
    assert martial_residual["recognition"]["param"] == {
        "all_of": [
            "1383-启动-武学研习残留页-标题",
            "1384-启动-武学研习残留页-关闭",
        ],
        "box_index": 1,
    }
    assert martial_residual["action"] == "Click"
    assert martial_residual["target"] == [1202, 30, 24, 24]
    assert martial_residual["max_hit"] == 1
    assert martial_residual["post_delay"] == 1500
    guild_reward = startup["1385-启动-关闭帮会奖励预览残留页"]
    assert guild_reward["recognition"]["param"] == {
        "all_of": [
            "1386-启动-帮会奖励预览残留页-累计征讨",
            "1387-启动-帮会奖励预览残留页-关闭",
        ],
        "box_index": 1,
    }
    assert guild_reward["action"] == "Click"
    assert guild_reward["target"] == [1019, 138, 28, 28]
    assert guild_reward["max_hit"] == 1
    guild_activity = startup["1388-启动-关闭帮会活动残留页"]
    assert guild_activity["recognition"]["param"]["all_of"] == [
        "1389-启动-帮会活动残留页-标题",
        "1390-启动-帮会页面残留-关闭",
    ]
    assert guild_activity["target"] == [1201, 27, 40, 39]
    assert guild_activity["max_hit"] == 1
    guild_home = startup["1391-启动-关闭帮会主页残留页"]
    assert guild_home["recognition"]["param"]["all_of"] == [
        "1392-启动-帮会主页残留页-标题",
        "1390-启动-帮会页面残留-关闭",
    ]
    assert guild_home["max_hit"] == 1
    panel = startup["1393-启动-关闭功能面板残留页"]
    assert panel["recognition"]["param"]["all_of"] == ["0029-公共-游戏侧边面板-打开"]
    assert panel["target"] == [1195, 10, 70, 70]
    assert panel["max_hit"] == 1
    martial_detail = startup["1394-启动-关闭武学研习详情残留页"]
    assert martial_detail["recognition"]["param"] == {
        "all_of": [
            "1395-启动-武学研习详情残留页-研习按钮",
            "1384-启动-武学研习残留页-关闭",
        ],
        "box_index": 1,
    }
    assert martial_detail["target"] == [1202, 30, 24, 24]
    assert martial_detail["max_hit"] == 1


def test_startup_confirms_the_single_public_home_boundary() -> None:
    nodes = load_nodes(ROOT / "assets/resource/base/pipeline")
    home = nodes["0026-公共-游戏主页-页面"]
    assert home == {
        "recognition": "OCR",
        "expected": ["已击破"],
        "roi": PUBLIC_HOME_ROI,
        "action": "DoNothing",
    }
    assert "next" not in _startup()["1362-启动-游戏就绪"]


def test_startup_failures_are_stateless_native_failures() -> None:
    terminal = json.loads(
        (ROOT / "assets/resource/base/pipeline/common/terminal.json").read_text(encoding="utf-8")
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


def test_launcher_anr_recovery_is_scoped_bounded_and_cannot_finish_game_start():
    import re

    startup = _startup()
    name = "启动-Pixel启动器无响应-关闭"
    node = startup[name]
    parts = node["recognition"]["param"]["all_of"]
    title, button = (startup[part] for part in parts)
    # Text observed in the native OCR replay of today's actual ANR screenshot.
    assert re.fullmatch(title["expected"], "Pixel 启动器没有响应")
    assert not re.fullmatch(title["expected"], "对决剑之川没有响应")
    assert not re.fullmatch(title["expected"], "系统界面没有响应")
    assert re.fullmatch(button["expected"], "关闭应用")
    assert not re.fullmatch(button["expected"], "等待")
    assert node["recognition"]["param"]["box_index"] == 1
    assert node["action"] == "Click" and node["target"] is True
    assert node["max_hit"] == 1
    assert "next" not in node
    for entry in ("0023-启动-游戏入口", "启动-等待游戏就绪"):
        assert startup[entry]["next"][0] == "[JumpBack]" + name
        assert "1362-启动-游戏就绪" in startup[entry]["next"]
