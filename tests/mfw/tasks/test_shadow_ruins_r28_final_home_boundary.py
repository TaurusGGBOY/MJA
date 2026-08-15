from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path


PIPELINE = (
    Path(__file__).resolve().parents[3]
    / "assets/resource/base/pipeline/daily/shadow_ruins_daily.json"
)

FINAL_REWARD = "影之遗迹-最终-奖励-探测"
FINAL_DISMISS = "影之遗迹-最终-关闭-奖励"
DONE = "MJA_SHADOW_DONE_PROBE"
HOME = "影之遗迹-主页边界-探测"
SUCCESS = "影之遗迹-记录-成功"
FAILURE = "影之遗迹-边界-失败"


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
        "影之遗迹-影-页面",
        "shadow.done",
    ]
    assert done["next"] == ["MJA_SHADOW_SUCCESS"]
    assert done["on_error"] == [HOME]

    home = nodes[HOME]
    assert home["recognition"] == {
        "type": "And",
        "param": {"all_of": ["影之遗迹-影-主页-页面"]},
    }
    assert nodes["影之遗迹-影-主页-页面"] == {
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
    assert nodes["影之遗迹-确认-完成"]["next"] == [FINAL_REWARD]
    assert nodes["影之遗迹-关闭-奖励"]["next"] == [
        "影之遗迹-探索-页面"
    ]
    assert HOME not in nodes["影之遗迹-任务入口"]["next"]

    # If neither the done page nor exact home is present, the chain remains
    # fail closed and can never record success.
    assert nodes[DONE]["on_error"] == [HOME]
    assert nodes[HOME]["on_error"] == [FAILURE]
    boundary_failure = nodes[FAILURE]
    assert boundary_failure["custom_action_param"]["status"] == "failed"
    assert boundary_failure["custom_action_param"]["native_fail_after_record"] is True
    assert boundary_failure["Abort"] is True
    assert boundary_failure["next"] == ["公共-通用中止"]
    assert SUCCESS not in boundary_failure.get("next", [])
