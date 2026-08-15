from __future__ import annotations

from collections.abc import Mapping, Sequence

from agent.custom.support.policy import TASK_POLICIES
from tests.mfw.task_contract import TaskContract, load_task_nodes

HERO = TaskContract("HERO_DISPATCH_DAILY", "daily/hero_dispatch_daily.json")
FRAME_AREA = 1280 * 720


def _contains(roi: Sequence[int], observed_box: Sequence[int]) -> bool:
    rx, ry, rw, rh = roi
    bx, by, bw, bh = observed_box
    return (
        rx <= bx
        and ry <= by
        and bx + bw <= rx + rw
        and by + bh <= ry + rh
    )


def _overlaps(left: Sequence[int], right: Sequence[int]) -> bool:
    lx, ly, lw, lh = left
    rx, ry, rw, rh = right
    return lx < rx + rw and rx < lx + lw and ly < ry + rh and ry < ly + lh


def _hero_edges(node: Mapping[str, object]) -> tuple[str, ...]:
    edges: list[str] = []
    for field in ("next", "on_error"):
        value = node.get(field, ())
        if isinstance(value, list):
            edges.extend(
                item
                for item in value
                if isinstance(item, str) and item.startswith("英雄派遣-")
            )
    return tuple(edges)


def test_r21_painting_ocr_uses_tight_exact_same_frame_markers() -> None:
    nodes = load_task_nodes(HERO)
    observed = {
        "英雄派遣-画卷-页面-标题": [92, 29, 44, 25],
        "英雄派遣-画卷-页面-偃武-世界": [136, 145, 96, 24],
        "英雄派遣-英雄-派遣-入口": [1006, 648, 86, 28],
    }
    expected = {
        "英雄派遣-画卷-页面-标题": "^画卷$",
        "英雄派遣-画卷-页面-偃武-世界": "^偃武世界$",
        "英雄派遣-英雄-派遣-入口": "^(?:侠客派遣|俠客派遣)$",
    }

    for name, observed_box in observed.items():
        node = nodes[name]
        assert node["recognition"] == "OCR"
        assert node["expected"] == expected[name]
        assert _contains(node["roi"], observed_box)
        assert node["roi"][2] * node["roi"][3] < FRAME_AREA // 50

    painting_page = nodes["英雄派遣-画卷-页面"]
    assert painting_page["recognition"] == {
        "type": "And",
        "param": {
            "all_of": ["英雄派遣-画卷-页面-标题", "英雄派遣-画卷-页面-偃武-世界"],
            "box_index": 0,
        },
    }

    # The adjacent 蜃影武墟 OCR box must not enter the dispatch click ROI.
    shadow_entry = [1116, 651, 84, 22]
    assert not _overlaps(nodes["英雄派遣-英雄-派遣-入口"]["roi"], shadow_entry)


def test_r21_dispatch_entry_is_page_bounded_and_single_shot() -> None:
    nodes = load_task_nodes(HERO)
    entry = nodes["英雄派遣-打开-派遣"]

    assert entry["recognition"] == {
        "type": "And",
        "param": {
            "all_of": ["英雄派遣-画卷-页面", "英雄派遣-英雄-派遣-入口"],
            "box_index": 1,
        },
    }
    assert entry["action"] == "Custom"
    assert entry["custom_action"] == "GuardedInput"
    assert entry["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "英雄派遣-画卷-页面",
        "target_name": "英雄派遣-英雄-派遣-入口",
    }
    assert entry["timeout"] == 8000
    assert entry["max_hit"] == 1
    assert entry["retry_times"] == 0
    assert TASK_POLICIES[HERO.task_id].action_caps["open_hero_dispatch"] == 1


def test_r21_startup_recovery_has_no_painting_probe_or_failure_cycle() -> None:
    nodes = load_task_nodes(HERO)
    assert "MJA_HERO_PAINTING_PROBE" not in nodes
    assert all(
        "MJA_HERO_PAINTING_PROBE" not in _hero_edges(node)
        for node in nodes.values()
    )

    start = nodes[HERO.entry]
    assert start["next"] == ["英雄派遣-主页-探测"]
    assert nodes["英雄派遣-恢复继续-奖励-探测"]["on_error"] == [
        "英雄派遣-派遣-页面-探测"
    ]
    assert nodes["英雄派遣-派遣-页面-探测"]["on_error"] == [
        "英雄派遣-打开-派遣"
    ]
    assert nodes["英雄派遣-主页-探测"]["on_error"] == [
        "英雄派遣-恢复继续-奖励-探测"
    ]
    assert nodes["英雄派遣-打开-画卷"]["next"] == [
        "英雄派遣-打开-派遣"
    ]
    assert nodes["英雄派遣-打开-派遣"]["next"] == [
        "英雄派遣-派遣-页面-之后-打开"
    ]
    assert nodes["英雄派遣-派遣-页面-之后-打开"]["on_error"] == [
        "英雄派遣-记录-失败"
    ]

    recovery_nodes = {
        HERO.entry,
        "英雄派遣-恢复继续-奖励-探测",
        "英雄派遣-恢复继续-关闭-奖励",
        "英雄派遣-派遣-页面-探测",
        "英雄派遣-派遣-页面-之后-打开",
        "英雄派遣-主页-探测",
        "英雄派遣-打开-画卷",
        "英雄派遣-打开-派遣",
        "英雄派遣-记录-失败",
    }
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(name: str) -> None:
        if name in visiting:
            raise AssertionError(f"startup recovery cycle detected at {name}")
        if name in visited:
            return
        visiting.add(name)
        for target in _hero_edges(nodes[name]):
            if target in recovery_nodes:
                visit(target)
        visiting.remove(name)
        visited.add(name)

    visit(HERO.entry)


def test_r21_unknown_boundary_records_failure_before_native_abort() -> None:
    nodes = load_task_nodes(HERO)
    for name in (
        HERO.entry,
        "英雄派遣-恢复继续-奖励-探测",
        "英雄派遣-派遣-页面-探测",
        "英雄派遣-主页-探测",
        "英雄派遣-打开-画卷",
        "英雄派遣-打开-派遣",
        "英雄派遣-派遣-页面-之后-打开",
    ):
        expected = {
            HERO.entry: ["英雄派遣-游戏启动恢复", "英雄派遣-记录-失败"],
            "英雄派遣-恢复继续-奖励-探测": ["英雄派遣-派遣-页面-探测"],
            "英雄派遣-派遣-页面-探测": ["英雄派遣-打开-派遣"],
            "英雄派遣-主页-探测": ["英雄派遣-恢复继续-奖励-探测"],
            "英雄派遣-打开-画卷": [
                "英雄派遣-打开-画卷-世界",
                "英雄派遣-记录-失败",
            ],
            "英雄派遣-打开-派遣": ["英雄派遣-记录-失败"],
            "英雄派遣-派遣-页面-之后-打开": ["英雄派遣-记录-失败"],
        }[name]
        assert nodes[name]["on_error"] == expected

    failure = nodes["英雄派遣-记录-失败"]
    assert failure["recognition"] == "DirectHit"
    assert failure["custom_action"] == "RecordTaskOutcome"
    assert failure["custom_action_param"] == {
        "task_id": HERO.task_id,
        "status": "failed",
        "postcondition": "HERO_POSTCONDITION_MISSING",
        "error_code": "HERO_POSTCONDITION_MISSING",
        "native_fail_after_record": True,
    }
    assert failure["Abort"] is True
    assert failure["next"] == ["公共-通用中止"]


def test_r21_exit_actions_remain_bounded_and_home_verified() -> None:
    nodes = load_task_nodes(HERO)
    policy = TASK_POLICIES[HERO.task_id]

    for node_name, action_id in (
        ("英雄派遣-关闭-派遣", "close_hero_dispatch"),
        ("英雄派遣-关闭-画卷", "close_hero_dispatch_painting"),
    ):
        node = nodes[node_name]
        assert node["custom_action"] == "GuardedInput"
        assert node["custom_action_param"]["action_id"] == action_id
        assert policy.action_caps[action_id] == 1
        assert node["max_hit"] == 1
        assert node["retry_times"] == 0

    assert nodes["英雄派遣-关闭-画卷"]["next"] == [
        "英雄派遣-主页边界-探测"
    ]
    assert nodes["英雄派遣-主页边界-探测"]["timeout"] == 8000
    assert nodes["英雄派遣-主页边界-探测"]["on_error"] == [
        "英雄派遣-边界-失败"
    ]
