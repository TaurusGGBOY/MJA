from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path


PIPELINE = (
    Path(__file__).resolve().parents[3]
    / "assets/resource/base/pipeline/daily/shadow_ruins_daily.json"
)

FIRST = "影之遗迹-领取-胜利-宝箱-首个"
RETRY = "影之遗迹-领取-胜利-宝箱-重试"
WAIT = "影之遗迹-胜利-宝箱-之后-重试-等待"
FINAL = "影之遗迹-最终-探测"
REWARD = "影之遗迹-奖励-探测"
CHEST_PROBE = "影之遗迹-胜利-宝箱-奖励-探测"
CHEST_DISMISS = "影之遗迹-关闭-胜利-宝箱-奖励"
EXPLORATION = "影之遗迹-探索-页面"
FAILURE = "影之遗迹-记录-失败"
LEAF = "影之遗迹-影-胜利-宝箱-奖励"


def _nodes() -> dict[str, dict[str, object]]:
    return json.loads(PIPELINE.read_text(encoding="utf-8"))


def _incoming_edges(nodes: dict[str, dict[str, object]]) -> dict[str, set[str]]:
    incoming: dict[str, set[str]] = defaultdict(set)
    for source, node in nodes.items():
        for edge_name in ("next", "on_error"):
            for target in node.get(edge_name, []):
                if isinstance(target, str) and not target.startswith("[JumpBack]"):
                    incoming[target].add(source)
    return incoming


def test_r30_chest_reward_boundary_is_exact_bounded_and_same_frame() -> None:
    nodes = _nodes()
    battle_cap = nodes["影之遗迹-战斗-循环"]["max_hit"]

    assert nodes[LEAF] == {
        "recognition": "OCR",
        "expected": "^恭喜获得$",
        "roi": [150, 200, 90, 290],
        "action": "DoNothing",
    }

    probe = nodes[CHEST_PROBE]
    assert probe["recognition"] == {
        "type": "And",
        "param": {"all_of": [LEAF]},
    }
    assert probe["action"] == "DoNothing"
    assert probe["next"] == [CHEST_DISMISS]
    assert probe["on_error"] == [FAILURE]
    assert probe["max_hit"] == battle_cap
    assert probe["retry_times"] == 0
    assert probe["timeout"] == 8000

    dismiss = nodes[CHEST_DISMISS]
    assert dismiss["recognition"] == {
        "type": "And",
        "param": {"all_of": [LEAF]},
    }
    assert dismiss["custom_action"] == "GuardedInput"
    assert dismiss["custom_action_param"] == {
        "task_id": "SHADOW_RUINS_DAILY",
        "action_id": "dismiss_shadow_reward_popup",
        "kind": "click",
        "fixed_click_mode": "shadow_reward_blank",
        "evidence": {
            "page_index": 0,
            "target_index": 0,
            "page_name": LEAF,
            "target_name": LEAF,
        },
    }
    assert dismiss["next"] == [EXPLORATION]
    assert dismiss["on_error"] == [FAILURE]
    assert dismiss["max_hit"] == battle_cap
    assert dismiss["retry_times"] == 0
    assert dismiss["timeout"] == 8000
    assert dismiss["post_delay"] == 750


def test_r30_chest_reward_recovery_is_private_to_bounded_victory_routes() -> None:
    nodes = _nodes()
    incoming = _incoming_edges(nodes)

    assert nodes[FIRST]["next"] == [FINAL, REWARD, CHEST_PROBE, RETRY]
    assert nodes[FIRST]["on_error"] == [FINAL, REWARD, CHEST_PROBE, FAILURE]
    assert nodes[RETRY]["next"] == [FINAL, REWARD, CHEST_PROBE, WAIT]
    assert nodes[RETRY]["on_error"] == [FINAL, REWARD, CHEST_PROBE, WAIT]
    assert nodes[WAIT]["next"] == [FINAL, REWARD, CHEST_PROBE, FAILURE]
    assert nodes[WAIT]["on_error"] == [FAILURE]

    assert incoming[CHEST_PROBE] == {FIRST, RETRY, WAIT}
    assert CHEST_PROBE not in nodes["影之遗迹-任务入口"]["next"]
    assert CHEST_PROBE not in nodes["影之遗迹-探索-页面"]["next"]
    assert CHEST_PROBE not in nodes[REWARD].get("next", [])
    assert CHEST_PROBE not in nodes["影之遗迹-关闭-奖励"].get("next", [])
    assert CHEST_PROBE not in nodes["影之遗迹-最终-奖励-探测"].get(
        "next", []
    )
    assert CHEST_PROBE not in nodes["影之遗迹-最终-关闭-奖励"].get(
        "next", []
    )

    leaf_users = {
        name
        for name, node in nodes.items()
        if isinstance((recognition := node.get("recognition")), dict)
        and LEAF in recognition.get("param", {}).get("all_of", [])
    }
    assert leaf_users == {CHEST_PROBE, CHEST_DISMISS}

    # Ordinary and final rewards still require their original close-only leaf.
    assert nodes[REWARD]["recognition"]["param"]["all_of"] == [
        "影之遗迹-影-奖励-关闭"
    ]
    assert nodes["影之遗迹-关闭-奖励"]["recognition"]["param"][
        "all_of"
    ] == ["影之遗迹-影-奖励", "影之遗迹-影-奖励-关闭"]
    assert nodes["影之遗迹-最终-奖励-探测"]["recognition"]["param"][
        "all_of"
    ] == ["影之遗迹-影-奖励-关闭"]
    assert nodes["影之遗迹-最终-关闭-奖励"]["recognition"]["param"][
        "all_of"
    ] == ["影之遗迹-影-奖励", "影之遗迹-影-奖励-关闭"]

    # An unrecognized popup cannot dismiss, return to exploration, or succeed.
    assert nodes[CHEST_PROBE]["on_error"] == [FAILURE]
    assert nodes[CHEST_DISMISS]["on_error"] == [FAILURE]
    failure = nodes[FAILURE]
    assert failure["custom_action_param"]["status"] == "failed"
    assert failure["custom_action_param"]["native_fail_after_record"] is True
    assert failure["Abort"] is True
    assert failure["next"] == ["公共-通用中止"]
