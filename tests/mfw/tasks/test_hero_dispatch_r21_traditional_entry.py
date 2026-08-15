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
                if isinstance(item, str) and item.startswith("MJA_HERO_")
            )
    return tuple(edges)


def test_r21_painting_ocr_uses_tight_exact_same_frame_markers() -> None:
    nodes = load_task_nodes(HERO)
    observed = {
        "painting.page.title": [92, 29, 44, 25],
        "painting.page.yanwu_world": [136, 145, 96, 24],
        "hero.dispatch.entry": [1006, 648, 86, 28],
    }
    expected = {
        "painting.page.title": "^画卷$",
        "painting.page.yanwu_world": "^偃武世界$",
        "hero.dispatch.entry": "^(?:侠客派遣|俠客派遣)$",
    }

    for name, observed_box in observed.items():
        node = nodes[name]
        assert node["recognition"] == "OCR"
        assert node["expected"] == expected[name]
        assert _contains(node["roi"], observed_box)
        assert node["roi"][2] * node["roi"][3] < FRAME_AREA // 50

    painting_page = nodes["painting.page"]
    assert painting_page["recognition"] == {
        "type": "And",
        "param": {
            "all_of": ["painting.page.title", "painting.page.yanwu_world"],
            "box_index": 0,
        },
    }

    # The adjacent 蜃影武墟 OCR box must not enter the dispatch click ROI.
    shadow_entry = [1116, 651, 84, 22]
    assert not _overlaps(nodes["hero.dispatch.entry"]["roi"], shadow_entry)


def test_r21_dispatch_entry_is_page_bounded_and_single_shot() -> None:
    nodes = load_task_nodes(HERO)
    entry = nodes["MJA_HERO_OPEN_DISPATCH"]

    assert entry["recognition"] == {
        "type": "And",
        "param": {
            "all_of": ["painting.page", "hero.dispatch.entry"],
            "box_index": 1,
        },
    }
    assert entry["action"] == "Custom"
    assert entry["custom_action"] == "GuardedInput"
    assert entry["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "painting.page",
        "target_name": "hero.dispatch.entry",
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
    assert start["next"] == ["MJA_HERO_HOME_PROBE"]
    assert nodes["MJA_HERO_RESUME_REWARD_PROBE"]["on_error"] == [
        "MJA_HERO_DISPATCH_PAGE_PROBE"
    ]
    assert nodes["MJA_HERO_DISPATCH_PAGE_PROBE"]["on_error"] == [
        "MJA_HERO_OPEN_DISPATCH"
    ]
    assert nodes["MJA_HERO_HOME_PROBE"]["on_error"] == [
        "MJA_HERO_RESUME_REWARD_PROBE"
    ]
    assert nodes["MJA_HERO_OPEN_PAINTING"]["next"] == [
        "MJA_HERO_OPEN_DISPATCH"
    ]
    assert nodes["MJA_HERO_OPEN_DISPATCH"]["next"] == [
        "MJA_HERO_DISPATCH_PAGE_AFTER_OPEN"
    ]
    assert nodes["MJA_HERO_DISPATCH_PAGE_AFTER_OPEN"]["on_error"] == [
        "MJA_HERO_RECORD_FAILURE"
    ]

    recovery_nodes = {
        HERO.entry,
        "MJA_HERO_RESUME_REWARD_PROBE",
        "MJA_HERO_RESUME_CLOSE_REWARD",
        "MJA_HERO_DISPATCH_PAGE_PROBE",
        "MJA_HERO_DISPATCH_PAGE_AFTER_OPEN",
        "MJA_HERO_HOME_PROBE",
        "MJA_HERO_OPEN_PAINTING",
        "MJA_HERO_OPEN_DISPATCH",
        "MJA_HERO_RECORD_FAILURE",
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
        "MJA_HERO_RESUME_REWARD_PROBE",
        "MJA_HERO_DISPATCH_PAGE_PROBE",
        "MJA_HERO_HOME_PROBE",
        "MJA_HERO_OPEN_PAINTING",
        "MJA_HERO_OPEN_DISPATCH",
        "MJA_HERO_DISPATCH_PAGE_AFTER_OPEN",
    ):
        expected = {
            HERO.entry: ["MJA_HERO_GAME_START_RECOVERY", "MJA_HERO_RECORD_FAILURE"],
            "MJA_HERO_RESUME_REWARD_PROBE": ["MJA_HERO_DISPATCH_PAGE_PROBE"],
            "MJA_HERO_DISPATCH_PAGE_PROBE": ["MJA_HERO_OPEN_DISPATCH"],
            "MJA_HERO_HOME_PROBE": ["MJA_HERO_RESUME_REWARD_PROBE"],
            "MJA_HERO_OPEN_PAINTING": [
                "MJA_HERO_OPEN_PAINTING_WORLD",
                "MJA_HERO_RECORD_FAILURE",
            ],
            "MJA_HERO_OPEN_DISPATCH": ["MJA_HERO_RECORD_FAILURE"],
            "MJA_HERO_DISPATCH_PAGE_AFTER_OPEN": ["MJA_HERO_RECORD_FAILURE"],
        }[name]
        assert nodes[name]["on_error"] == expected

    failure = nodes["MJA_HERO_RECORD_FAILURE"]
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
    assert failure["next"] == ["MJA_COMMON_ABORT"]


def test_r21_exit_actions_remain_bounded_and_home_verified() -> None:
    nodes = load_task_nodes(HERO)
    policy = TASK_POLICIES[HERO.task_id]

    for node_name, action_id in (
        ("MJA_HERO_CLOSE_DISPATCH", "close_hero_dispatch"),
        ("MJA_HERO_CLOSE_PAINTING", "close_hero_dispatch_painting"),
    ):
        node = nodes[node_name]
        assert node["custom_action"] == "GuardedInput"
        assert node["custom_action_param"]["action_id"] == action_id
        assert policy.action_caps[action_id] == 1
        assert node["max_hit"] == 1
        assert node["retry_times"] == 0

    assert nodes["MJA_HERO_CLOSE_PAINTING"]["next"] == [
        "MJA_HERO_HOME_BOUNDARY_PROBE"
    ]
    assert nodes["MJA_HERO_HOME_BOUNDARY_PROBE"]["timeout"] == 8000
    assert nodes["MJA_HERO_HOME_BOUNDARY_PROBE"]["on_error"] == [
        "MJA_HERO_BOUNDARY_FAILURE"
    ]
