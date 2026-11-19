from __future__ import annotations

import json
import re
from pathlib import Path

from agent.custom.support.policy import TASK_POLICIES

PIPELINE = (
    Path(__file__).resolve().parents[3]
    / "assets/resource/base/pipeline/daily/shadow_ruins_daily.json"
)
SERVER_ERROR_EDGES = ["影之遗迹-服务器报错-重启应用", "影之遗迹-服务器报错-终止"]


def _nodes() -> dict[str, dict[str, object]]:
    return json.loads(PIPELINE.read_text(encoding="utf-8"))


def test_shadow_cards_are_selected_before_prepare_checkbox() -> None:
    nodes = _nodes()

    assert nodes["1172-影之遗迹-打开-影"]["next"] == [
        "1173-影之遗迹-选择-进行中",
        "影之遗迹-本期关卡均已击破",
    ]
    assert nodes["1173-影之遗迹-选择-进行中"]["next"] == ["1174-影之遗迹-进入-关卡"]
    assert nodes["1192-影之遗迹-影-进行中"]["expected"] == ["探索中", "可探索"]
    assert nodes["1192-影之遗迹-影-进行中"]["roi"] == [80, 430, 720, 270]
    assert nodes["1173-影之遗迹-选择-进行中"]["on_error"] == [
        "影之遗迹-本期关卡均已击破",
        "MJA-公共-原生失败-返回主页",
    ]


def test_completion_reopens_shadow_ruins_until_no_active_card_remains() -> None:
    nodes = _nodes()
    continue_until_exhausted = [
        "1173-影之遗迹-选择-进行中",
        "影之遗迹-本期关卡均已击破",
        "[JumpBack]1170-影之遗迹-打开-画卷",
    ]

    assert nodes["1595-MJA-影之遗迹-确认退出"]["next"] == [
        "1597-MJA-影之遗迹-关闭奖励弹窗",
        *continue_until_exhausted,
    ]
    assert nodes["1597-MJA-影之遗迹-关闭奖励弹窗"]["next"] == [
        "1597-MJA-影之遗迹-关闭奖励弹窗",
        *continue_until_exhausted,
    ]
    # A successful controller tap does not prove the reward overlay disappeared.
    # Re-recognize it before checking the underlying cards, under the existing cap.
    assert nodes["1597-MJA-影之遗迹-关闭奖励弹窗"]["post_delay"] == 1000
    assert TASK_POLICIES["SHADOW_RUINS_DAILY"].action_caps["dismiss_shadow_reward_popup"] == 12
    assert nodes["1597-MJA-影之遗迹-关闭奖励弹窗"]["on_error"] == [
        "MJA-公共-原生失败-返回主页",
    ]


def test_exhaustive_loop_budget_covers_all_four_shadow_cards() -> None:
    caps = TASK_POLICIES["SHADOW_RUINS_DAILY"].action_caps

    for action_id in (
        "open_painting_scroll",
        "open_shadow",
        "select_active_shadow_card",
        "enter_shadow_stage",
    ):
        assert caps[action_id] == 8
    assert caps["confirm_shadow_teleport"] == 4
    assert caps["confirm_shadow_completion"] == 4
    assert caps["dismiss_shadow_battle_result"] == 48


def test_forward_waits_for_stage_page_then_checks_unchecked_prepare_box() -> None:
    nodes = _nodes()

    forward = nodes["1174-影之遗迹-进入-关卡"]
    wait = nodes["1592-MJA-影之遗迹-自动寻路-等待-关卡"]
    prepare = nodes["1208-影之遗迹-跳过-准备-点击"]

    assert forward["next"] == [
        *SERVER_ERROR_EDGES,
        "1176-影之遗迹-跨图-确认",
        "1595-MJA-影之遗迹-确认退出",
        "1593-MJA-影之遗迹-进入-探索页",
        "1592-MJA-影之遗迹-自动寻路-等待-关卡",
    ]
    assert wait["recognition"] == {
        "type": "And",
        "param": {"all_of": ["1194-影之遗迹-影-关卡-页面"], "box_index": 0},
    }
    assert wait["timeout"] == 120000
    assert wait["on_error"] == ["1221-影之遗迹-记录-失败"]
    assert wait["max_hit"] == 4
    assert nodes["1176-影之遗迹-跨图-确认"]["recognition"]["param"]["all_of"] == [
        "影之遗迹-跨图寻路提示", "1175-影之遗迹-跨图-确认-文案",
    ]
    assert wait["next"] == [
        *SERVER_ERROR_EDGES,
        "1595-MJA-影之遗迹-确认退出",
        "1176-影之遗迹-跨图-确认",
        "1509-MJA-影之遗迹地图推进-战斗等待",
        "1511-MJA-影之遗迹地图推进-战斗胜利",
        "1512-MJA-影之遗迹地图推进-战斗失败",
        "1594-MJA-影之遗迹-开始战斗",
        "1593-MJA-影之遗迹-进入-探索页",
        "1208-影之遗迹-跳过-准备-点击",
    ]
    assert (
        "1501-MJA-影之遗迹地图推进-前景三点循环" in nodes["1593-MJA-影之遗迹-进入-探索页"]["next"]
    )
    assert prepare["recognition"] == {
        "type": "And",
        "param": {
            "all_of": [
                "1194-影之遗迹-影-关卡-页面",
                "1224-影之遗迹-影-跳过-准备",
                "1226-影之遗迹-影-跳过-准备-未勾选",
            ],
            "box_index": 2,
        },
    }
    assert prepare["custom_action_param"]["evidence"]["target_index"] == 2
    assert (
        prepare["custom_action_param"]["evidence"]["target_name"]
        == "1226-影之遗迹-影-跳过-准备-未勾选"
    )
    assert prepare["next"] == ["1501-MJA-影之遗迹地图推进-前景三点循环"]


def test_server_error_restarts_once_before_combat_and_never_clicks_logout() -> None:
    nodes = _nodes()
    restart, failure = map(nodes.__getitem__, SERVER_ERROR_EDGES)
    marker = nodes["影之遗迹-服务器报错-文案"]
    assert re.fullmatch(marker["expected"], "服务器调用出错，退出登录")
    for unrelated in ("是否领取最终奖励", "跨图寻路", "退出登录", "确认"):
        assert not re.fullmatch(marker["expected"], unrelated)
    assert restart["recognition"] == failure["recognition"]
    assert restart["custom_action"] == "RestartGameSurface"
    assert restart["custom_action_param"]["force_stop"] is True
    assert restart["custom_action_param"]["start_repeat"] == 1
    assert restart["custom_action_param"]["capture_request_error"] is True
    assert restart["max_hit"] == 1
    assert restart["next"] == [
        SERVER_ERROR_EDGES[1],
        "[JumpBack]1370-启动-游戏启动后-进入按钮",
        "1170-影之遗迹-打开-画卷",
    ]
    assert failure["custom_action"] == "FailTask"
    assert failure["custom_action_param"]["capture_request_error"] is True
    assert failure["Abort"] is True
    assert {
        name for name, node in nodes.items() if SERVER_ERROR_EDGES[0] in node.get("next", [])
    } == {
        "1174-影之遗迹-进入-关卡",
        "1176-影之遗迹-跨图-确认",
        "1592-MJA-影之遗迹-自动寻路-等待-关卡",
    }


def test_cross_map_confirmation_accepts_current_forward_label() -> None:
    marker = _nodes()["1175-影之遗迹-跨图-确认-文案"]
    pattern = marker["expected"]

    assert re.fullmatch(pattern, "前往")
    assert re.fullmatch(pattern, "确认")
    assert not re.fullmatch(pattern, "取消")


def test_unchecked_prepare_marker_is_visual_and_scoped_to_checkbox() -> None:
    marker = _nodes()["1226-影之遗迹-影-跳过-准备-未勾选"]

    assert marker["recognition"] == "ColorMatch"
    assert marker["roi"] == [1045, 430, 35, 35]
    assert marker["lower"] == [80, 80, 80]
    assert marker["upper"] == [120, 120, 120]
    assert marker["connected"] is True
    assert marker["action"] == "DoNothing"


def test_stage_start_text_is_not_guessed_in_first_stage_repair() -> None:
    nodes = _nodes()

    assert nodes["1534-MJA-影之遗迹地图推进-识别-战斗目标"]["expected"] == "开战"
    assert nodes["1223-影之遗迹-影-挑战-目标"]["expected"] == ["挑战"]
    assert "1534-MJA-影之遗迹地图推进-识别-战斗目标" not in nodes[
        "1208-影之遗迹-跳过-准备-点击"
    ].get("next", [])
    assert "1223-影之遗迹-影-挑战-目标" not in nodes["1208-影之遗迹-跳过-准备-点击"].get("next", [])


def test_completion_requires_defeated_card_and_explicit_remaining_unavailability():
    import json
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    nodes = json.loads(
        (root / "assets/resource/base/pipeline/daily/shadow_ruins_daily.json").read_text()
    )
    assert nodes["影之遗迹-本期关卡均已击破"]["recognition"]["param"]["all_of"] == [
        "1191-影之遗迹-影-页面",
        "影之遗迹-左侧关卡已击破",
        "影之遗迹-其余关卡均不可挑战",
    ]
    assert nodes["影之遗迹-其余关卡均不可挑战"]["recognition"]["param"]["any_of"] == [
        "影之遗迹-右侧关卡已击破",
        "影之遗迹-暂未开放新关卡",
    ]
    pattern = nodes["影之遗迹-暂未开放新关卡"]["expected"]
    assert re.search(pattern, "暂未发现新的武墟！")
    for text in ("正在进行", "开始挑战", "剩余时间：0天05时", ""):
        assert not re.search(pattern, text)


def test_stage_wait_failure_returns_home_before_native_failure():
    nodes = _nodes()
    assert nodes["1221-影之遗迹-记录-失败"]["next"] == ["MJA-公共-原生失败-返回主页"]
    assert nodes["1509-MJA-影之遗迹地图推进-战斗等待"]["timeout"] == 240000


def test_exploration_recognizes_later_floor_in_current_title_region():
    node = _nodes()["1528-MJA-影之遗迹地图推进-识别-探索页"]
    for title in ("第一层", "第四层", "第十层"):
        assert re.fullmatch(node["expected"], title)
    for title in ("战斗胜利", "第四层奖励", "已击破600层"):
        assert not re.fullmatch(node["expected"], title)
    assert node["roi"] == [500, 0, 300, 120]


def test_auto_advance_is_handled_after_exploration_and_battle_result():
    nodes = _nodes()
    for name in (
        "1593-MJA-影之遗迹-进入-探索页",
        "1511-MJA-影之遗迹地图推进-战斗胜利",
        "1512-MJA-影之遗迹地图推进-战斗失败",
    ):
        assert "1509-MJA-影之遗迹地图推进-战斗等待" in nodes[name]["next"]
        assert "1595-MJA-影之遗迹-确认退出" in nodes[name]["next"]
        assert nodes[name]["on_error"] == ["1221-影之遗迹-记录-失败"]


def test_auto_battle_without_hud_can_reach_result_before_map_timeout():
    nodes = _nodes()
    advance = nodes["1501-MJA-影之遗迹地图推进-前景三点循环"]
    assert advance["timeout"] == nodes["1509-MJA-影之遗迹地图推进-战斗等待"]["timeout"]
    assert "[JumpBack]1511-MJA-影之遗迹地图推进-战斗胜利" in advance["next"]
    assert "[JumpBack]1512-MJA-影之遗迹地图推进-战斗失败" in advance["next"]
    assert advance["on_error"] == ["1221-影之遗迹-记录-失败"]


def test_confirm_teleport_waits_for_map_transfer_and_cleans_up_on_timeout():
    node = _nodes()["1176-影之遗迹-跨图-确认"]
    assert node["timeout"] == 120000
    assert node["on_error"] == ["1221-影之遗迹-记录-失败"]
