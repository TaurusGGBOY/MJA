from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path


PIPELINE = (
    Path(__file__).resolve().parents[3]
    / "assets/resource/base/pipeline/daily/shadow_ruins_daily.json"
)

FINAL_REWARD = "MJA_SHADOW_FINAL_REWARD_PROBE"
FINAL_DISMISS = "MJA_SHADOW_FINAL_DISMISS_REWARD"
DONE = "MJA_SHADOW_DONE_PROBE"
HOME = "MJA_SHADOW_HOME_BOUNDARY_PROBE"
SUCCESS = "MJA_SHADOW_RECORD_SUCCESS"
FAILURE = "MJA_SHADOW_BOUNDARY_FAILURE"


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


def test_r28_final_chain_accepts_done_page_or_exact_home_boundary() -> None:
    nodes = _nodes()

    assert nodes[FINAL_REWARD]["next"] == [FINAL_DISMISS]
    assert nodes[FINAL_REWARD]["on_error"] == [DONE]
    assert nodes[FINAL_DISMISS]["next"] == [DONE]

    done = nodes[DONE]
    assert done["recognition"]["param"]["all_of"] == [
        "shadow.page",
        "shadow.done",
    ]
    assert done["next"] == ["MJA_SHADOW_SUCCESS"]
    assert done["on_error"] == [HOME]

    home = nodes[HOME]
    assert home["recognition"] == {
        "type": "And",
        "param": {"all_of": ["shadow.home.page"]},
    }
    assert nodes["shadow.home.page"] == {
        "recognition": "TemplateMatch",
        "template": "home/home_marker.png",
        "roi": [1040, 0, 240, 110],
        "threshold": 0.375,
        "action": "DoNothing",
    }
    assert home["action"] == "DoNothing"
    assert home["next"] == [SUCCESS]
    assert home["on_error"] == [FAILURE]


def test_r28_home_success_is_scoped_to_proven_terminal_paths() -> None:
    nodes = _nodes()
    incoming = _incoming_edges(nodes)

    # The exact home boundary remains shared with the existing bounded restart
    # path.  The only new direct-home caller is DONE, which itself is reachable
    # only after the final confirmation/reward chain.
    assert incoming[HOME] == {"MJA_SHADOW_RESTART_SURFACE", DONE}
    assert nodes["MJA_SHADOW_CONFIRM_COMPLETION"]["next"] == [FINAL_REWARD]
    assert nodes["MJA_SHADOW_DISMISS_REWARD"]["next"] == [
        "MJA_SHADOW_EXPLORATION_PAGE"
    ]
    assert HOME not in nodes["MJA_SHADOW_RUINS_DAILY_START"]["next"]

    # If neither the done page nor exact home is present, the chain remains
    # fail closed and can never record success.
    assert nodes[DONE]["on_error"] == [HOME]
    assert nodes[HOME]["on_error"] == [FAILURE]
    boundary_failure = nodes[FAILURE]
    assert boundary_failure["custom_action_param"]["status"] == "failed"
    assert boundary_failure["custom_action_param"]["native_fail_after_record"] is True
    assert boundary_failure["Abort"] is True
    assert boundary_failure["next"] == ["MJA_COMMON_ABORT"]
    assert SUCCESS not in boundary_failure.get("next", [])
