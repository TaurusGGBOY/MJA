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


def test_game_start_entry_is_a_probe_and_does_not_start_app() -> None:
    node = _startup()["MJA_GAME_START_ENTRY"]

    assert node["recognition"] == "DirectHit"
    assert node["action"] == "DoNothing"
    assert node["max_hit"] == 1
    assert node["timeout"] == 1000
    assert node["next"] == ["MJA_GAME_START"]
    assert node["on_error"] == ["MJA_COMMON_STARTUP_RECOVERY_RESTART"]


def test_game_start_only_short_circuits_on_home_ocr() -> None:
    startup = _startup()
    start = startup["MJA_GAME_START"]
    ready = startup["MJA_GAME_READY"]
    home = load_nodes(ROOT / "assets/resource/base/pipeline")["MJA_GAME_HOME_PAGE"]

    expected = {
        "recognition": "OCR",
        "expected": "^画[卷券]$",
        "roi": [1080, 0, 200, 120],
    }
    assert start["recognition"] == "DirectHit"
    assert start["action"] == "DoNothing"
    assert start["timeout"] == 1000
    assert start["next"] == [
        "[JumpBack]MJA_START_OPTIONAL_CLICK_BLANK_TO_CLOSE",
        "[JumpBack]MJA_START_OPTIONAL_MONTHLY_REWARD_PAGE_CLOSE",
        "MJA_GAME_READY",
        "MJA_START_GAME_BUTTON_AFTER_RESTART",
    ]
    assert start["on_error"] == ["MJA_COMMON_STARTUP_RECOVERY_RESTART"]
    assert {key: ready[key] for key in expected} == expected
    assert ready["action"] == "Custom"
    assert ready["custom_action"] == "RuntimeHealth"
    assert "on_error" not in ready
    assert {key: home[key] for key in expected} == expected


def test_restart_handoff_waits_twenty_seconds_then_clicks_both_buttons() -> None:
    startup = _startup()
    terminal = load_nodes(ROOT / "assets/resource/base/pipeline")[
        "MJA_COMMON_STARTUP_RECOVERY_RESTART"
    ]
    wait_after_restart = startup["MJA_GAME_START_AFTER_RESTART"]
    start_button = startup["MJA_START_GAME_BUTTON_AFTER_RESTART"]
    enter_button = startup["MJA_START_ENTER_GAME_BUTTON_AFTER_RESTART"]
    wait_after_enter = startup["MJA_GAME_START_WAIT_AFTER_ENTER"]

    assert terminal["custom_action"] == "RestartGameSurface"
    assert terminal["post_delay"] == 0
    assert terminal["max_hit"] == 1
    assert terminal["next"] == ["MJA_GAME_START_AFTER_RESTART"]
    assert terminal["on_error"] == ["MJA_GAME_START_APP_RESTART_FAILED"]

    assert wait_after_restart["recognition"] == "DirectHit"
    assert wait_after_restart["action"] == "DoNothing"
    assert wait_after_restart["post_delay"] == 20000
    assert wait_after_restart["max_hit"] == 1
    assert wait_after_restart["next"] == ["MJA_START_GAME_BUTTON_AFTER_RESTART"]

    assert start_button["recognition"] == "OCR"
    assert start_button["expected"] == [
        "^开始游戏$",
        "^点击开始游戏$",
        "^点击开始游戏[！!]?$",
    ]
    assert start_button["action"] == "Click"
    assert start_button["post_delay"] == 5000
    assert start_button["next"] == ["MJA_START_ENTER_GAME_BUTTON_AFTER_RESTART"]
    assert start_button["on_error"] == ["MJA_GAME_START_RETRY_2"]

    assert enter_button["recognition"] == "OCR"
    assert enter_button["expected"] == ["^进入游戏[！!]?$", "^点击进入游戏[！!]?$"]
    assert enter_button["action"] == "Click"
    assert enter_button["post_delay"] == 0
    assert enter_button["next"] == ["MJA_GAME_START_WAIT_AFTER_ENTER"]
    assert enter_button["on_error"] == ["MJA_GAME_START_ENTER_BUTTON_NOT_FOUND"]

    assert wait_after_enter["recognition"] == "DirectHit"
    assert wait_after_enter["action"] == "DoNothing"
    assert wait_after_enter["post_delay"] == 30000
    assert wait_after_enter["next"] == [
        "[JumpBack]MJA_START_OPTIONAL_CLICK_BLANK_TO_CLOSE",
        "[JumpBack]MJA_START_OPTIONAL_MONTHLY_REWARD_PAGE_CLOSE",
        "MJA_GAME_READY",
    ]
    assert wait_after_enter["on_error"] == ["MJA_GAME_START_HOME_NOT_REACHED"]


def test_restart_handoff_relaunches_at_most_five_times_when_start_button_is_missing() -> None:
    startup = _startup()
    terminal = load_nodes(ROOT / "assets/resource/base/pipeline")

    assert terminal["MJA_COMMON_STARTUP_RECOVERY_RESTART"]["next"] == [
        "MJA_GAME_START_AFTER_RESTART"
    ]

    for attempt in range(1, 6):
        suffix = "" if attempt == 1 else f"_{attempt}"
        wait_name = f"MJA_GAME_START_AFTER_RESTART{suffix}"
        button_name = f"MJA_START_GAME_BUTTON_AFTER_RESTART{suffix}"
        wait = startup[wait_name]
        button = startup[button_name]
        next_failure = (
            f"MJA_GAME_START_RETRY_{attempt + 1}"
            if attempt < 5
            else "MJA_GAME_START_START_BUTTON_NOT_FOUND"
        )

        assert wait["post_delay"] == 20000
        assert wait["max_hit"] == 1
        assert wait["next"] == [button_name]
        assert wait["on_error"] == [next_failure]
        assert button["recognition"] == "OCR"
        assert button["action"] == "Click"
        assert button["max_hit"] == 1
        assert button["next"] == ["MJA_START_ENTER_GAME_BUTTON_AFTER_RESTART"]
        assert button["on_error"] == [next_failure]

    for attempt in range(2, 6):
        restart = startup[f"MJA_GAME_START_RETRY_{attempt}"]
        assert restart["custom_action"] == "RestartGameSurface"
        assert restart["max_hit"] == 1
        assert restart["next"] == [f"MJA_GAME_START_AFTER_RESTART_{attempt}"]
        assert restart["on_error"] == ["MJA_GAME_START_APP_RESTART_FAILED"]


def test_startup_optional_reward_cleanup_is_ordered_and_bounded() -> None:
    startup = _startup()
    blank = startup["MJA_START_OPTIONAL_CLICK_BLANK_TO_CLOSE"]
    monthly = startup["MJA_START_OPTIONAL_MONTHLY_REWARD_PAGE_CLOSE"]

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
        "[JumpBack]MJA_START_OPTIONAL_CLICK_BLANK_TO_CLOSE",
        "[JumpBack]MJA_START_OPTIONAL_MONTHLY_REWARD_PAGE_CLOSE",
    ]
    assert startup["MJA_GAME_START"]["next"][:2] == expected_gate
    assert startup["MJA_GAME_START_WAIT_AFTER_ENTER"]["next"][:2] == expected_gate


def test_startup_route_has_no_legacy_page_gate_or_restart_recursion() -> None:
    startup = _startup()
    route = startup["MJA_GAME_START"]["next"]
    legacy = {
        "MJA_START_ANNOUNCEMENT",
        "MJA_START_MOBILE_NETWORK_UPDATE",
        "MJA_START_UPDATE_PROGRESS",
        "MJA_START_TITLE_OR_LOADING",
        "MJA_START_TITLE_TEMPLATE",
        "MJA_START_LOADING",
        "MJA_START_BLACK_SCREEN_WAIT",
        "MJA_START_PERSISTENT_BLACK_SCREEN_RECOVERY",
        "MJA_START_WHITE_SCREEN_WAIT",
        "MJA_KNOWN_NETWORK_CONFIRM",
        "MJA_KNOWN_RESOURCE_UPDATE_CONFIRM",
        "MJA_KNOWN_BATTLE_VICTORY_RESULT_CLOSE",
        "MJA_KNOWN_BATTLE_RESULT_CLOSE",
        "MJA_START_STALE_CHEST_REWARD_RECOVERY",
        "MJA_START_SHADOW_PAGE_BACK",
        "MJA_START_SHADOW_EXPLORATION_PAGE_BACK",
        "MJA_KNOWN_CLICK_BLANK_TO_CLOSE",
        "MJA_KNOWN_MONTHLY_SIGNIN_CLOSE",
        "MJA_START_TRIAL_PAGE_CLOSE",
        "MJA_KNOWN_HERO_DISPATCH_CLOSE",
        "MJA_GAME_SIDE_PANEL_CLOSE",
        "MJA_KNOWN_CROSS_MAP_PROMPT_CANCEL",
    }

    assert route == [
        "[JumpBack]MJA_START_OPTIONAL_CLICK_BLANK_TO_CLOSE",
        "[JumpBack]MJA_START_OPTIONAL_MONTHLY_REWARD_PAGE_CLOSE",
        "MJA_GAME_READY",
        "MJA_START_GAME_BUTTON_AFTER_RESTART",
    ]
    assert not any(item.removeprefix("[JumpBack]") in legacy for item in route)
    assert "MJA_GAME_LAUNCH" not in startup


def test_startup_failure_nodes_keep_stage_specific_human_readable_reasons() -> None:
    nodes = load_nodes(ROOT / "assets/resource/base/pipeline")
    names = (
        "MJA_GAME_START_APP_RESTART_FAILED",
        "MJA_GAME_START_START_BUTTON_NOT_FOUND",
        "MJA_GAME_START_ENTER_BUTTON_NOT_FOUND",
        "MJA_GAME_START_HOME_NOT_REACHED",
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
        "MJA_START_STALE_CHEST_REWARD_RECOVERY",
        "MJA_START_SHADOW_PAGE_BACK",
        "MJA_START_SHADOW_EXPLORATION_PAGE_BACK",
        "MJA_START_PERSISTENT_BLACK_SCREEN_RECOVERY",
    ):
        assert name in startup
        assert name not in startup["MJA_GAME_START"].get("next", [])


def test_home_template_nodes_keep_the_existing_calibration_for_non_startup_tasks() -> None:
    nodes = load_nodes(ROOT / "assets/resource/base/pipeline")
    home_markers = {
        name: node
        for name, node in nodes.items()
        if node.get("template") == "home/home_marker.png"
    }

    assert home_markers
    assert "MJA_GAME_HOME_MARKER" in home_markers
    assert "MJA_GAME_READY" not in home_markers
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
        "ready": "MJA_GAME_READY",
        "title": "MJA_START_GAME_BUTTON_AFTER_RESTART",
        "known_popup": "MJA_KNOWN_POPUP_CLOSE",
        "known_page": "MJA_KNOWN_PAGE_CLOSE",
        "launcher": "MJA_GAME_START_AFTER_RESTART",
        "black_screen": "MJA_START_BLACK_SCREEN_WAIT",
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
