from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from tests.mfw.pipeline_assertions import (
    assert_all_cycles_bounded,
    load_fixture_manifest,
    load_nodes,
)

ROOT = Path(__file__).parents[1]
STARTUP_PATH = ROOT / "assets/resource/base/pipeline/startup/game_start.json"
HOME_MARKER_ROI = [1040, 0, 240, 110]
HOME_MARKER_THRESHOLD = 0.375
LIVE_HOME_MARKER_SCORE = 0.767864


def _startup() -> dict[str, dict]:
    return json.loads(STARTUP_PATH.read_text(encoding="utf-8"))


def test_game_start_entry_launches_app_before_readiness_checks() -> None:
    node = _startup()["启动-游戏入口"]

    assert node["recognition"] == "DirectHit"
    assert node["action"] == "StartApp"
    assert node["package"] == "com.hanjiasongshu.dr22/.MainActivity"
    assert node["max_hit"] == 1
    assert node["repeat"] == 5
    assert node["repeat_delay"] == 1000
    assert node["timeout"] == 1000
    assert node["next"] == ["启动-游戏启动"]
    assert node["on_error"] == ["公共-通用-启动恢复-重启"]


def test_game_start_pipeline_has_no_post_delay() -> None:
    startup = _startup()

    assert all("post_delay" not in node for node in startup.values())


def test_game_start_only_short_circuits_on_home_ocr() -> None:
    startup = _startup()
    start = startup["启动-游戏启动"]
    ready = startup["启动-游戏就绪"]
    home = load_nodes(ROOT / "assets/resource/base/pipeline")["公共-游戏主页-页面"]

    expected = {
        "recognition": "OCR",
        "expected": "已击破",
        "roi": [940, 660, 140, 40],
    }
    assert start["recognition"] == "DirectHit"
    assert start["action"] == "DoNothing"
    assert start["timeout"] == 20000
    assert start["next"] == [
        "[JumpBack]启动-可选点击空白关闭",
        "[JumpBack]启动-可选关闭月签到奖励页",
        "启动-游戏就绪",
        "[JumpBack]启动-进入-游戏-按钮-之后-重启",
        "[JumpBack]启动-游戏-按钮-之后-重启",
    ]
    assert start["on_error"] == ["公共-通用-启动恢复-重启"]
    assert {key: ready[key] for key in expected} == expected
    assert ready["action"] == "Custom"
    assert ready["custom_action"] == "RuntimeHealth"
    assert "on_error" not in ready
    assert {key: home[key] for key in expected} == expected


def test_restart_handoff_repeats_visible_buttons_until_ready_or_timeout() -> None:
    startup = _startup()
    terminal = load_nodes(ROOT / "assets/resource/base/pipeline")[
        "公共-通用-启动恢复-重启"
    ]
    wait_after_restart = startup["启动-游戏重启后"]
    start_button = startup["启动-游戏-按钮-之后-重启"]
    enter_button = startup["启动-进入-游戏-按钮-之后-重启"]

    assert terminal["custom_action"] == "RestartGameSurface"
    assert terminal["post_delay"] == 0
    assert terminal["max_hit"] == 1
    assert terminal["next"] == ["启动-游戏重启后"]
    assert terminal["on_error"] == ["公共-游戏启动应用重启失败"]

    assert wait_after_restart["recognition"] == "DirectHit"
    assert wait_after_restart["action"] == "DoNothing"
    assert "post_delay" not in wait_after_restart
    assert wait_after_restart["max_hit"] == 1
    assert wait_after_restart["timeout"] == 20000
    assert wait_after_restart["next"] == [
        "启动-游戏就绪",
        "[JumpBack]启动-进入-游戏-按钮-之后-重启",
        "[JumpBack]启动-游戏-按钮-之后-重启",
    ]

    assert start_button["recognition"] == "OCR"
    assert start_button["expected"] == [
        "^开始游戏$",
        "^点击开始游戏$",
        "^点击开始游戏[！!]?$",
    ]
    assert start_button["action"] == "Click"
    assert "post_delay" not in start_button
    assert start_button["max_hit"] == 20
    assert start_button["next"] == []
    assert start_button["on_error"] == ["公共-游戏启动开始按钮未找到"]

    assert enter_button["recognition"] == "OCR"
    assert enter_button["expected"] == ["^进入游戏[！!]?$", "^点击进入游戏[！!]?$"]
    assert enter_button["action"] == "Click"
    assert "post_delay" not in enter_button
    assert enter_button["max_hit"] == 20
    assert enter_button["next"] == []
    assert enter_button["on_error"] == ["公共-游戏启动进入按钮未找到"]


def test_restart_handoff_click_loop_has_no_legacy_retry_chain() -> None:
    startup = _startup()
    assert not any(name.startswith("启动-游戏启动重试-") for name in startup)
    for name in (
        "启动-游戏-按钮-之后-重启",
        "启动-进入-游戏-按钮-之后-重启",
    ):
        assert startup[name]["max_hit"] == 20
        assert startup[name]["next"] == []


def test_startup_optional_reward_cleanup_is_ordered_and_bounded() -> None:
    startup = _startup()
    blank = startup["启动-可选点击空白关闭"]
    monthly = startup["启动-可选关闭月签到奖励页"]

    assert blank["recognition"] == "OCR"
    assert blank["roi"] == [350, 580, 600, 140]
    assert blank["timeout"] == 1500
    assert blank["action"] == "Click"

    assert monthly["recognition"] == "OCR"
    assert monthly["expected"] == ["^本月可领取物品$", "^本月.*可领取.*物品$"]
    assert monthly["roi"] == [150, 100, 900, 520]
    assert monthly["timeout"] == 1500
    assert monthly["action"] == "Click"
    assert monthly["target"] == [1060, 152, 16, 16]

    expected_gate = [
        "[JumpBack]启动-可选点击空白关闭",
        "[JumpBack]启动-可选关闭月签到奖励页",
    ]
    assert startup["启动-游戏启动"]["next"][:2] == expected_gate
    assert startup["启动-进入游戏后等待"]["next"][:2] == expected_gate


def test_startup_route_has_no_legacy_page_gate_or_restart_recursion() -> None:
    startup = _startup()
    route = startup["启动-游戏启动"]["next"]
    legacy = {
        "启动-公告",
        "启动-移动网络-网络-更新",
        "启动-更新-进度",
        "启动-标题-或-加载",
        "启动-标题-模板",
        "启动-加载",
        "启动-黑屏-屏幕-等待",
        "启动-持续黑屏恢复",
        "启动-白屏-屏幕-等待",
        "公共-已知-网络-确认",
        "公共-已知-资源更新确认",
        "公共-已知-战斗胜利结果关闭",
        "公共-已知-战斗结果关闭",
        "启动-过期-宝箱-奖励-恢复",
        "启动-影-探索-页面-返回",
        "公共-已知-点击空白关闭",
        "公共-已知-月签到-关闭",
        "启动-试炼-页面-关闭",
        "公共-已知-英雄-派遣-关闭",
        "启动-游戏侧边面板-关闭",
        "公共-已知-跨地图-提示-取消",
    }

    assert route == [
        "[JumpBack]启动-可选点击空白关闭",
        "[JumpBack]启动-可选关闭月签到奖励页",
        "启动-游戏就绪",
        "[JumpBack]启动-进入-游戏-按钮-之后-重启",
        "[JumpBack]启动-游戏-按钮-之后-重启",
    ]
    assert not any(item.removeprefix("[JumpBack]") in legacy for item in route)
    assert "MJA_GAME_LAUNCH" not in startup


def test_startup_failure_nodes_keep_stage_specific_human_readable_reasons() -> None:
    nodes = load_nodes(ROOT / "assets/resource/base/pipeline")
    names = (
        "公共-游戏启动应用重启失败",
        "公共-游戏启动开始按钮未找到",
        "公共-游戏启动进入按钮未找到",
        "公共-游戏启动主页未到达",
    )

    for name in names:
        node = nodes[name]
        params = node["custom_action_param"]
        assert node["custom_action"] == "FailStartupRecovery"
        assert node["Abort"] is True
        assert params["error_code"].startswith("GAME_START_")
        assert params["stage"]
        assert params["expected"]
        assert params["observed"]
        assert params["root_cause"]


def test_startup_graph_is_bounded_and_old_nodes_are_not_deleted_accidentally() -> None:
    nodes = load_nodes(ROOT / "assets/resource/base/pipeline")
    assert_all_cycles_bounded(nodes)
    startup = _startup()
    for name in (
        "启动-过期-宝箱-奖励-恢复",
        "启动-影-探索-页面-返回",
        "启动-持续黑屏恢复",
    ):
        assert name in startup
        assert name not in startup["启动-游戏启动"].get("next", [])


def test_home_template_nodes_keep_the_existing_calibration_for_non_startup_tasks() -> None:
    nodes = load_nodes(ROOT / "assets/resource/base/pipeline")
    home_markers = {
        name: node
        for name, node in nodes.items()
        if node.get("template") == "home/home_marker.png"
    }

    assert home_markers
    assert "启动-游戏主页-标记" in home_markers
    assert "启动-游戏就绪" not in home_markers
    for name, node in home_markers.items():
        assert node["recognition"] == "TemplateMatch", name
        assert node["roi"] == HOME_MARKER_ROI, name
        assert node["threshold"] == HOME_MARKER_THRESHOLD, name
        assert node["threshold"] < LIVE_HOME_MARKER_SCORE, name


def test_startup_fixture_manifest_has_valid_images_and_updated_title_route() -> None:
    manifest_path = ROOT / "tests/fixtures/startup/manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    cases = load_fixture_manifest(manifest_path)

    assert payload["schema_version"] == 2
    expected = {
        "ready": "启动-游戏就绪",
        "title": "启动-游戏-按钮-之后-重启",
        "known_popup": "公共-已知弹窗-关闭",
        "known_page": "公共-已知-页面-关闭",
        "launcher": "启动-游戏重启后",
        "black_screen": "启动-黑屏-屏幕-等待",
    }
    assert set(cases) == set(expected)
    for name, case in cases.items():
        assert set(case) == {"image", "expected_first_node"}
        assert case["expected_first_node"] == expected[name]
        image_path = ROOT / case["image"]
        assert image_path.is_file(), image_path
        with Image.open(image_path) as image:
            image.verify()
        with Image.open(image_path) as image:
            assert image.format == "PNG"
            if name in {"launcher", "black_screen"}:
                assert image.size == (1280, 720)
            if name == "black_screen":
                assert image.mode == "RGB"
                assert image.getextrema() == ((0, 0), (0, 0), (0, 0))
