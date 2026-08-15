from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path


PIPELINE = (
    Path(__file__).resolve().parents[3]
    / "assets/resource/base/pipeline/daily/shadow_ruins_daily.json"
)

FIRST = "MJA_SHADOW_CLAIM_VICTORY_CHEST_FIRST"
RETRY = "MJA_SHADOW_CLAIM_VICTORY_CHEST_RETRY"
WAIT = "MJA_SHADOW_VICTORY_CHEST_POST_RETRY_WAIT"
FINAL = "MJA_SHADOW_FINAL_PROBE"
REWARD = "MJA_SHADOW_REWARD_PROBE"
CHEST_PROBE = "MJA_SHADOW_VICTORY_CHEST_REWARD_PROBE"
CHEST_DISMISS = "MJA_SHADOW_DISMISS_VICTORY_CHEST_REWARD"
EXPLORATION = "MJA_SHADOW_EXPLORATION_PAGE"
FAILURE = "MJA_SHADOW_RECORD_FAILURE"
LEAF = "shadow.victory.chest.reward"


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
    battle_cap = nodes["MJA_SHADOW_BATTLE_LOOP"]["max_hit"]

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
    assert CHEST_PROBE not in nodes["MJA_SHADOW_RUINS_DAILY_START"]["next"]
    assert CHEST_PROBE not in nodes["MJA_SHADOW_EXPLORATION_PAGE"]["next"]
    assert CHEST_PROBE not in nodes[REWARD].get("next", [])
    assert CHEST_PROBE not in nodes["MJA_SHADOW_DISMISS_REWARD"].get("next", [])
    assert CHEST_PROBE not in nodes["MJA_SHADOW_FINAL_REWARD_PROBE"].get(
        "next", []
    )
    assert CHEST_PROBE not in nodes["MJA_SHADOW_FINAL_DISMISS_REWARD"].get(
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
        "shadow.reward.close"
    ]
    assert nodes["MJA_SHADOW_DISMISS_REWARD"]["recognition"]["param"][
        "all_of"
    ] == ["shadow.reward", "shadow.reward.close"]
    assert nodes["MJA_SHADOW_FINAL_REWARD_PROBE"]["recognition"]["param"][
        "all_of"
    ] == ["shadow.reward.close"]
    assert nodes["MJA_SHADOW_FINAL_DISMISS_REWARD"]["recognition"]["param"][
        "all_of"
    ] == ["shadow.reward", "shadow.reward.close"]

    # An unrecognized popup cannot dismiss, return to exploration, or succeed.
    assert nodes[CHEST_PROBE]["on_error"] == [FAILURE]
    assert nodes[CHEST_DISMISS]["on_error"] == [FAILURE]
    failure = nodes[FAILURE]
    assert failure["custom_action_param"]["status"] == "failed"
    assert failure["custom_action_param"]["native_fail_after_record"] is True
    assert failure["Abort"] is True
    assert failure["next"] == ["MJA_COMMON_ABORT"]
