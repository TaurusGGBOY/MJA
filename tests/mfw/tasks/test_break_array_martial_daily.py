from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from types import ModuleType

if importlib.util.find_spec("maa") is None:
    maa_module = ModuleType("maa")
    maa_agent_module = ModuleType("maa.agent")
    maa_agent_server_module = ModuleType("maa.agent.agent_server")
    maa_custom_action_module = ModuleType("maa.custom_action")

    class _AgentServer:
        @staticmethod
        def custom_action(_name: str):
            return lambda implementation: implementation

    class _CustomAction:
        RunArg = object

        class RunResult:
            def __init__(self, *, success: bool) -> None:
                self.success = success

    maa_agent_server_module.AgentServer = _AgentServer
    maa_custom_action_module.CustomAction = _CustomAction
    sys.modules.update(
        {
            "maa": maa_module,
            "maa.agent": maa_agent_module,
            "maa.agent.agent_server": maa_agent_server_module,
            "maa.custom_action": maa_custom_action_module,
        }
    )

from agent.workflows.definitions.break_array_martial_daily import (
    BREAK_ARRAY_MARTIAL_DAILY_DEFINITION as DEFINITION,
)
from agent.workflows.definitions.break_array_martial_daily import (
    BREAK_ARRAY_MARTIAL_DAILY_POLICY as POLICY,
)
from agent.workflows.definitions.break_array_martial_daily import (
    CANONICAL_TASK_ID,
    MAX_BATTLE_POLLS,
    MAX_CHALLENGES,
    MAX_RESULT_POLLS,
    MAX_STARTUP_POLLS,
    terminal_postcondition,
)
from agent.workflows.models import (
    CapturedFrame,
    InputKind,
    Recognition,
    StateSnapshot,
    TaskStatus,
    VisualEvidence,
)

ROOT = Path(__file__).resolve().parents[3]
TASK_PATH = ROOT / "assets/tasks/日常/BREAK_ARRAY_MARTIAL_DAILY.json"
PIPELINE_PATH = ROOT / "assets/resource_android/pipeline/daily/break_array_martial_daily.json"
MFW_PIPELINE_PATH = ROOT / "assets/resource/base/pipeline/daily/break_array_martial_daily.json"
CUSTOM_ACTION_PATH = ROOT / "agent/custom/action/break_array_martial_daily.py"
TASK_LIFECYCLE_PATH = ROOT / "agent/custom/action/task_lifecycle.py"
STARTUP_LOADING_FIXTURE_PATH = (
    ROOT / "tests/fixtures/BREAK_ARRAY_MARTIAL_DAILY/r11_startup_loading.json"
)

_CUSTOM_ACTION_SPEC = importlib.util.spec_from_file_location(
    "_break_array_martial_daily_custom_action_test",
    CUSTOM_ACTION_PATH,
)
assert _CUSTOM_ACTION_SPEC is not None and _CUSTOM_ACTION_SPEC.loader is not None
custom_action_module = importlib.util.module_from_spec(_CUSTOM_ACTION_SPEC)
sys.modules[_CUSTOM_ACTION_SPEC.name] = custom_action_module
_CUSTOM_ACTION_SPEC.loader.exec_module(custom_action_module)
BreakArrayMartialDailyAction = custom_action_module.BreakArrayMartialDailyAction
TASK_LOCAL_CLEANUP_RECOGNIZERS = (
    custom_action_module.TASK_LOCAL_CLEANUP_RECOGNIZERS
)


def snapshot(state: str, *markers: str, texts: tuple[str, ...] = ()) -> StateSnapshot:
    frame_id = f"break-array-{state}"
    hits = {marker: 1 for marker in markers}
    evidence = VisualEvidence(
        frame_id,
        hits,
        hits,
        {},
        {marker: frame_id for marker in markers},
        texts=texts,
    )
    recognitions = tuple(
        Recognition(marker, frame_id, 1, ((10, 10, 20, 20),)) for marker in markers
    )
    return StateSnapshot(CapturedFrame(frame_id, (1280, 720)), state, recognitions, evidence)


def decide(
    state: str,
    markers: tuple[str, ...],
    counts: dict[str, int] | None = None,
    *,
    texts: tuple[str, ...] = (),
):
    return DEFINITION.decide(snapshot(state, *markers, texts=texts), counts or {})


def paired_counts(challenges: int, **extra: int) -> dict[str, int]:
    return {
        "start_break_array_challenge": challenges,
        "confirm_break_array_challenge": challenges,
        "start_break_array_battle": challenges,
        **extra,
    }


def test_task_declaration_and_pipeline_entry_are_task_local():
    declaration = json.loads(TASK_PATH.read_text(encoding="utf-8"))
    task = declaration["task"][0]
    assert task == {
        "name": CANONICAL_TASK_ID,
        "label": "破阵演武（每日三次）",
        "default_check": True,
        "group": ["日常"],
        "entry": "破阵武学-任务入口",
    }
    pipeline = json.loads(PIPELINE_PATH.read_text(encoding="utf-8"))
    mfw_pipeline = json.loads(MFW_PIPELINE_PATH.read_text(encoding="utf-8"))
    native_start = mfw_pipeline["破阵武学-任务入口"]
    assert native_start["custom_action"] == "BeginTask"
    assert native_start["custom_action_param"] == {"task_id": CANONICAL_TASK_ID}
    assert native_start["next"] == [
        "破阵武学-启动-探测",
        "破阵武学-页面-探测",
        "破阵武学-活动-探测",
        "破阵武学-主页-探测",
    ]
    assert native_start["on_error"] == ["破阵武学-记录-失败"]
    assert "MJA_BREAK_ARRAY_MARTIAL_DAILY_EXECUTE" not in mfw_pipeline
    assert "BreakArrayMartialDailyAction" not in json.dumps(mfw_pipeline)
    assert "[JumpBack]启动-游戏启动" not in json.dumps(mfw_pipeline)
    # The Android resource is retained as a read-only compatibility archive;
    # only the base MFW resource is the native execution contract.
    assert "破阵武学-任务入口" in pipeline
    for resource_pipeline in (pipeline, mfw_pipeline):
        assert not any(
            node.get("action") in {"Click", "StartApp"}
            for node in resource_pipeline.values()
        )
    assert mfw_pipeline["破阵武学-安全-付费"]["recognition"] == "OCR"
    assert mfw_pipeline["破阵武学-安全-校验"]["recognition"] == "OCR"
    assert "破阵武学-安全-付费" not in pipeline
    assert "破阵武学-安全-校验" not in pipeline
    assert pipeline["破阵武学-突破-阵法-未知-对话框"]["recognition"] == "OCR"
    assert mfw_pipeline["破阵武学-突破-阵法-未知-对话框"]["recognition"] == "OCR"
    assert mfw_pipeline["破阵武学-活动-入口"]["roi"] == [840, 20, 110, 90]
    assert mfw_pipeline["破阵武学-活动-页面"]["expected"] == ["破阵演武", "破阵"]
    assert mfw_pipeline["破阵武学-活动-页面"]["roi"] == [0, 120, 1280, 600]
    assert mfw_pipeline["破阵武学-活动-页面"] == {
        "recognition": "OCR",
        "expected": ["破阵演武", "破阵"],
        "roi": [0, 120, 1280, 600],
        "action": "DoNothing",
    }
    for resource_pipeline in (pipeline, mfw_pipeline):
        assert resource_pipeline["破阵武学-突破-阵法-启动-加载"] == {
            "recognition": "OCR",
            "expected": ["穿梭入世", "穿梭入世中", "加载中"],
            "roi": [350, 580, 900, 140],
            "action": "DoNothing",
        }


    for resource_pipeline in (pipeline, mfw_pipeline):
        assert resource_pipeline["破阵武学-突破-阵法-页面"] == {
            "recognition": {
                "type": "And",
                "param": {
                    "all_of": [
                        "破阵武学-突破-阵法-已选择-入口",
                        "破阵武学-突破-阵法-剩余",
                    ]
                },
            },
            "action": "DoNothing",
        }
        assert resource_pipeline["破阵武学-突破-阵法-已选择-入口"] == {
            "recognition": "OCR",
            "expected": "破阵演武",
            "roi": [35, 390, 135, 100],
            "action": "DoNothing",
        }

        assert resource_pipeline["破阵武学-突破-阵法-开始"] == {
            "recognition": {
                "type": "And",
                "param": {
                    "all_of": [
                        "破阵武学-突破-阵法-开始-顶部",
                        "破阵武学-突破-阵法-开始-底部",
                    ],
                    "box_index": 0,
                },
            },
            "action": "DoNothing",
        }
        assert resource_pipeline["破阵武学-突破-阵法-开始-顶部"] == {
            "recognition": "OCR",
            "expected": "^开始$",
            "roi": [1050, 520, 190, 90],
            "action": "DoNothing",
        }
        assert resource_pipeline["破阵武学-突破-阵法-开始-底部"] == {
            "recognition": "OCR",
            "expected": "^挑战$",
            "roi": [1050, 565, 190, 95],
            "action": "DoNothing",
        }

        assert resource_pipeline["破阵武学-突破-阵法-开始-确认-对话框"] == {
            "recognition": {
                "type": "And",
                "param": {
                    "all_of": [
                        "破阵武学-突破-阵法-开始-确认-标题",
                        "破阵武学-突破-阵法-开始-确认-消耗",
                        "破阵武学-突破-阵法-开始-确认-准备",
                    ]
                },
            },
            "action": "DoNothing",
        }
        assert resource_pipeline["破阵武学-突破-阵法-开始-确认-标题"] == {
            "recognition": "OCR",
            "expected": "^提\\s*示$",
            "roi": [285, 175, 80, 110],
            "action": "DoNothing",
        }
        assert resource_pipeline["破阵武学-突破-阵法-开始-确认-消耗"] == {
            "recognition": "OCR",
            "expected": "开始挑战.*消耗\\s*1\\s*次挑战次数",
            "roi": [400, 285, 520, 90],
            "action": "DoNothing",
        }
        assert resource_pipeline["破阵武学-突破-阵法-开始-确认-准备"] == {
            "recognition": "OCR",
            "expected": ["进入准备界面", "搭配适合的出战阵容"],
            "roi": [430, 315, 470, 100],
            "action": "DoNothing",
        }
        assert resource_pipeline["破阵武学-突破-阵法-开始-确认-按钮"] == {
            "recognition": "OCR",
            "expected": "^确认$",
            "roi": [790, 455, 180, 90],
            "action": "DoNothing",
        }
        assert resource_pipeline["破阵武学-突破-阵法-确认-过渡-暗-字段"] == {
            "recognition": "ColorMatch",
            "method": 4,
            "lower": [0, 0, 0],
            "upper": [8, 8, 8],
            "roi": [140, 180, 1000, 420],
            "connected": True,
            "count": 400000,
            "action": "DoNothing",
        }
        assert resource_pipeline["破阵武学-突破-阵法-确认-过渡-传闻-字形"] == {
            "recognition": "ColorMatch",
            "method": 4,
            "lower": [210, 210, 210],
            "upper": [255, 255, 255],
            "roi": [430, 80, 840, 90],
            "connected": False,
            "count": 3000,
            "action": "DoNothing",
        }
        assert resource_pipeline["破阵武学-突破-阵法-确认-过渡-用户标识-字形"] == {
            "recognition": "ColorMatch",
            "method": 4,
            "lower": [80, 80, 65],
            "upper": [190, 190, 175],
            "roi": [1100, 680, 180, 40],
            "connected": False,
            "count": 350,
            "action": "DoNothing",
        }
        assert resource_pipeline["破阵武学-突破-阵法-确认-过渡"] == {
            "recognition": {
                "type": "And",
                "param": {
                    "all_of": [
                        "破阵武学-突破-阵法-确认-过渡-暗-字段",
                        "破阵武学-突破-阵法-确认-过渡-传闻-字形",
                        "破阵武学-突破-阵法-确认-过渡-用户标识-字形",
                    ]
                },
            },
            "action": "DoNothing",
        }

        assert resource_pipeline["破阵武学-突破-阵法-准备-页面"] == {
            "recognition": {
                "type": "And",
                "param": {
                    "all_of": [
                        "破阵武学-突破-阵法-准备-阵容",
                        "破阵武学-突破-阵法-准备-首领",
                        "破阵武学-突破-阵法-准备-时长",
                        "破阵武学-突破-阵法-准备-战术",
                    ]
                },
            },
            "action": "DoNothing",
        }
        assert resource_pipeline["破阵武学-突破-阵法-准备-阵容"] == {
            "recognition": "OCR",
            "expected": "^阵容$",
            "roi": [40, 10, 150, 70],
            "action": "DoNothing",
        }
        assert resource_pipeline["破阵武学-突破-阵法-准备-首领"] == {
            "recognition": "OCR",
            "expected": "^首领战斗$",
            "roi": [520, 10, 240, 55],
            "action": "DoNothing",
        }
        assert resource_pipeline["破阵武学-突破-阵法-准备-时长"] == {
            "recognition": "OCR",
            "expected": r"^战(?:斗)?时长\s*[：:]\s*02\s*[：:]\s*00$",
            "roi": [520, 40, 250, 60],
            "action": "DoNothing",
        }
        assert resource_pipeline["破阵武学-突破-阵法-准备-战术"] == {
            "recognition": "OCR",
            "expected": "^战术谱$",
            "roi": [980, 480, 140, 80],
            "action": "DoNothing",
        }
        assert resource_pipeline["破阵武学-突破-阵法-准备-开始"] == {
            "recognition": "ColorMatch",
            "method": 4,
            "lower": [200, 65, 0],
            "upper": [255, 170, 70],
            "roi": [1100, 550, 150, 145],
            "connected": False,
            "count": 4500,
            "action": "DoNothing",
        }
        assert "break_array.challenge_page" not in resource_pipeline
        battle_patterns = resource_pipeline["破阵武学-突破-阵法-战斗"]["expected"]
        assert battle_patterns == ["^跳过$", "^自动战斗$", "^战斗中$"]
        assert not any(re.search(pattern, "首领战斗") for pattern in battle_patterns)

        for row in ("破阵武学-突破-阵法-开始-顶部", "破阵武学-突破-阵法-开始-底部"):
            x, y, width, height = resource_pipeline[row]["roi"]
            assert x >= 1030 and y >= 500
            assert x + width <= 1280 and y + height <= 660

        remaining = resource_pipeline["破阵武学-突破-阵法-剩余"]
        assert remaining["roi"] == [1000, 620, 280, 100]
        assert any(
            re.search(pattern, "剩余挑战次数：9/9")
            for pattern in remaining["expected"]
        )
        assert all("/\\s*3" not in pattern for pattern in remaining["expected"])

        exhausted = resource_pipeline["破阵武学-突破-阵法-剩余-耗尽"]
        assert exhausted["roi"] == [1000, 620, 280, 100]
        assert any(
            re.search(pattern, "剩余挑战次数：0/9")
            for pattern in exhausted["expected"]
        )

        for remaining_after_confirm in range(9):
            exact_name = f"break_array.remaining_exact_{remaining_after_confirm}_of_9"
            page_name = f"break_array.page.remaining_{remaining_after_confirm}_of_9"
            assert re.search(
                resource_pipeline[exact_name]["expected"],
                f"剩余挑战次数：{remaining_after_confirm}/9",
            )
            assert resource_pipeline[page_name] == {
                "recognition": {
                    "type": "And",
                    "param": {
                        "all_of": [
                            "破阵武学-突破-阵法-已选择-入口",
                            exact_name,
                        ]
                    },
                },
                "action": "DoNothing",
            }


def test_final_regression_loading_archive_is_a_task_local_read_only_boundary():
    fixture = json.loads(STARTUP_LOADING_FIXTURE_PATH.read_text(encoding="utf-8"))
    loading = fixture["recognitions"]["破阵武学-突破-阵法-启动-加载"]
    pipeline = json.loads(PIPELINE_PATH.read_text(encoding="utf-8"))
    node = pipeline["破阵武学-突破-阵法-启动-加载"]
    assert loading["hit"] is True
    assert any(re.search(pattern, loading["text"]) for pattern in node["expected"])
    rx, ry, rw, rh = node["roi"]
    bx, by, bw, bh = loading["box"]
    assert rx <= bx and ry <= by
    assert bx + bw <= rx + rw and by + bh <= ry + rh
    assert fixture["result"] == {
        "status": "failed",
        "postcondition": "break_array.postcondition_missing",
        "error_code": "WORKFLOW_POSTCONDITION_MISSING",
    }

    decision = decide("home", ("破阵武学-突破-阵法-启动-加载",))
    assert decision.transition is not None
    assert decision.transition.intent.action_id == "wait_break_array_startup"
    assert decision.transition.intent.input_kind is InputKind.NONE

    archived = ROOT / fixture["source"]
    if archived.is_file():
        assert hashlib.sha256(archived.read_bytes()).hexdigest() == fixture["sha256"]
    archived_result = ROOT / fixture["result_source"]
    if archived_result.is_file():
        assert json.loads(archived_result.read_text(encoding="utf-8")) == {
            "schema_version": 1,
            "task_id": CANONICAL_TASK_ID,
            "status": "failed",
            "started_at": "2026-08-11T14:04:32.685+00:00",
            "finished_at": "2026-08-11T14:04:34.695+00:00",
            "postcondition": "break_array.postcondition_missing",
            "error_code": "WORKFLOW_POSTCONDITION_MISSING",
        }


def test_lifecycle_uses_embedded_agent_server_registration():
    lifecycle_source = TASK_LIFECYCLE_PATH.read_text(encoding="utf-8")
    action_source = CUSTOM_ACTION_PATH.read_text(encoding="utf-8")
    assert '@AgentServer.custom_action("BeginTask")' in lifecycle_source
    assert '@AgentServer.custom_action("RecordTaskOutcome")' in lifecycle_source
    assert "resource.custom_action" not in lifecycle_source
    assert '@AgentServer.custom_action("BreakArrayMartialDailyAction")' in action_source
    assert "CustomAction.RunResult(success=False)" in action_source
    assert "run_workflow" not in action_source
    assert "MaaAndroidWorkflowDriver" not in action_source
    assert "_MfwResultLifecycle" not in action_source
    assert "_mfw_lifecycle" not in action_source


def test_mfw_resource_covers_every_runtime_recognizer_without_legacy_probes():
    pipeline = json.loads(MFW_PIPELINE_PATH.read_text(encoding="utf-8"))
    runtime_recognizers = set(TASK_LOCAL_CLEANUP_RECOGNIZERS)
    for state in (
        "home",
        "activity",
        "break_array",
        "confirm_break_array:9_of_9",
        "post_confirm_break_array:9_of_9",
        "battle",
        "result",
        "verify",
    ):
        runtime_recognizers.update(DEFINITION.recognizers(state))

    assert runtime_recognizers <= pipeline.keys()
    assert runtime_recognizers.isdisjoint(
        {
            "reset.home",
            "home.painting_scroll_text",
            "ring_page",
            "martial_page",
            "tea_purchase_result",
            "shadow_page",
            "shadow_formation_page",
        }
    )
    assert pipeline["破阵武学-突破-阵法-主页"] == {
        "recognition": "TemplateMatch",
        "template": "home/home_marker.png",
        "roi": [1040, 0, 240, 110],
        "threshold": 0.375,
        "action": "DoNothing",
    }
    for marker in ("破阵武学-突破-阵法-关闭", "破阵武学-活动-关闭"):
        assert pipeline[marker]["recognition"] == "TemplateMatch"
        assert pipeline[marker]["template"] == "home/modal_close.png"
        assert pipeline[marker]["roi"] == [1120, 0, 160, 140]


def test_legacy_custom_action_registration_fails_closed() -> None:
    action_source = CUSTOM_ACTION_PATH.read_text(encoding="utf-8")
    assert "run_workflow" not in action_source
    assert "MaaAndroidWorkflowDriver" not in action_source
    result = BreakArrayMartialDailyAction().run(
        object(),
        object(),
    )
    assert result.success is False


def test_path_enters_activity_then_break_array():
    activity = decide("home", ("破阵武学-活动-入口",))
    assert activity.transition is not None
    assert activity.transition.intent.action_id == "open_break_array_activity"
    assert activity.transition.next_state == "activity"

    target = decide("activity", ("破阵武学-活动-页面", "破阵武学-突破-阵法-入口"))
    assert target.transition is not None
    assert target.transition.intent.action_id == "open_break_array"
    assert target.transition.postcondition == "break_array.page"


def test_unavailable_and_already_complete_are_explicit_non_failure_outcomes():
    unavailable = decide("break_array", ("破阵武学-突破-阵法-页面", "破阵武学-突破-阵法-不可用"))
    assert unavailable.status is TaskStatus.NOT_ELIGIBLE

    complete = decide(
        "break_array",
        ("破阵武学-突破-阵法-页面", "破阵武学-突破-阵法-已完成"),
    )
    assert complete.status is TaskStatus.ALREADY_COMPLETE

    danger = decide("break_array", ("破阵武学-突破-阵法-页面", "破阵武学-突破-阵法-未知-对话框"))
    assert danger.status is TaskStatus.FAILED


def test_challenge_loop_is_exactly_three_and_requires_result_close():
    start = decide(
        "break_array",
        ("破阵武学-突破-阵法-页面", "破阵武学-突破-阵法-开始", "破阵武学-突破-阵法-剩余"),
        texts=("剩余挑战次数：9/9",),
    )
    assert start.transition is not None
    assert start.transition.intent.action_id == "start_break_array_challenge"
    assert start.transition.intent.page_marker == "破阵武学-突破-阵法-页面"
    assert start.transition.intent.target_marker == "破阵武学-突破-阵法-开始"
    assert start.transition.postcondition == "break_array.start_confirm_dialog"
    assert start.transition.next_state == "confirm_break_array:9_of_9"

    start_without_page = decide(
        "break_array",
        ("破阵武学-突破-阵法-开始", "破阵武学-突破-阵法-剩余"),
        texts=("剩余挑战次数：9/9",),
    )
    assert start_without_page.status is TaskStatus.FAILED

    result = decide(
        "result",
        ("破阵武学-突破-阵法-结果", "破阵武学-突破-阵法-成功"),
        paired_counts(1),
    )
    assert result.transition is not None
    assert result.transition.intent.action_id == "wait_break_array_result"

    exhausted_result = decide(
        "result",
        ("破阵武学-突破-阵法-结果", "破阵武学-突破-阵法-成功"),
        paired_counts(1, wait_break_array_result=MAX_RESULT_POLLS),
    )
    assert exhausted_result.status is TaskStatus.FAILED

    close = decide(
        "result",
        ("破阵武学-突破-阵法-结果", "破阵武学-突破-阵法-成功", "破阵武学-突破-阵法-结果-关闭"),
        paired_counts(1),
    )
    assert close.transition is not None
    assert close.transition.intent.action_id == "dismiss_break_array_result"
    assert close.transition.next_state == "break_array"


def test_start_confirmation_is_exactly_bounded_and_same_frame_authorized():
    confirm = decide(
        "confirm_break_array:9_of_9",
        (
            "破阵武学-突破-阵法-开始-确认-对话框",
            "破阵武学-突破-阵法-开始-确认-按钮",
            # The broad legacy detector sees 取消, but the exact known
            # title/body boundary is allowed to disambiguate this prompt.
            "破阵武学-突破-阵法-未知-对话框",
        ),
        {"start_break_array_challenge": 1},
    )
    assert confirm.transition is not None
    assert confirm.transition.intent.action_id == "confirm_break_array_challenge"
    assert (
        confirm.transition.intent.page_marker
        == "破阵武学-突破-阵法-开始-确认-对话框"
    )
    assert confirm.transition.intent.target_marker == "破阵武学-突破-阵法-开始-确认-按钮"
    assert confirm.transition.postcondition == "break_array.prepare_page"
    assert confirm.transition.postcondition_alternatives == ()
    assert confirm.transition.next_state == "post_confirm_break_array:9_of_9"

    missing_body = decide(
        "confirm_break_array:9_of_9",
        ("破阵武学-突破-阵法-开始-确认-按钮", "破阵武学-突破-阵法-未知-对话框"),
        {"start_break_array_challenge": 1},
    )
    assert missing_body.status is TaskStatus.FAILED

    duplicate = decide(
        "confirm_break_array:9_of_9",
        ("破阵武学-突破-阵法-开始-确认-对话框", "破阵武学-突破-阵法-开始-确认-按钮"),
        {
            "start_break_array_challenge": 1,
            "confirm_break_array_challenge": 1,
        },
    )
    assert duplicate.status is TaskStatus.FAILED
    assert POLICY.action_caps["confirm_break_array_challenge"] == MAX_CHALLENGES


def test_confirmation_transition_requires_one_bounded_formation_start_click():
    transition = decide(
        "post_confirm_break_array:9_of_9",
        ("破阵武学-突破-阵法-确认-过渡",),
        {
            "start_break_array_challenge": 1,
            "confirm_break_array_challenge": 1,
        },
    )
    assert transition.status is TaskStatus.FAILED

    prepare = decide(
        "post_confirm_break_array:9_of_9",
        ("破阵武学-突破-阵法-准备-页面", "破阵武学-突破-阵法-准备-开始"),
        {
            "start_break_array_challenge": 1,
            "confirm_break_array_challenge": 1,
        },
    )
    assert prepare.transition is not None
    assert prepare.transition.intent.action_id == "start_break_array_battle"
    assert prepare.transition.intent.page_marker == "破阵武学-突破-阵法-准备-页面"
    assert prepare.transition.intent.target_marker == "破阵武学-突破-阵法-准备-开始"
    assert prepare.transition.intent.input_kind is InputKind.CLICK
    assert prepare.transition.postcondition == "break_array.battle_loading"
    assert prepare.transition.postcondition_alternatives == (
        "break_array.battle",
        "break_array.result",
        "break_array.success",
        "break_array.failure",
    )
    assert prepare.transition.next_state == "battle"

    prepare_beats_stale_transition = decide(
        "post_confirm_break_array:9_of_9",
        (
            "破阵武学-突破-阵法-准备-页面",
            "破阵武学-突破-阵法-准备-开始",
            "破阵武学-突破-阵法-确认-过渡",
        ),
        {
            "start_break_array_challenge": 1,
            "confirm_break_array_challenge": 1,
        },
    )
    assert prepare_beats_stale_transition.transition is not None
    assert (
        prepare_beats_stale_transition.transition.intent.action_id
        == "start_break_array_battle"
    )

    prepare_after_transition = decide(
        "battle",
        ("破阵武学-突破-阵法-准备-页面", "破阵武学-突破-阵法-准备-开始"),
        {
            "start_break_array_challenge": 1,
            "confirm_break_array_challenge": 1,
        },
    )
    assert prepare_after_transition.transition is not None
    assert (
        prepare_after_transition.transition.intent.action_id
        == "start_break_array_battle"
    )
    assert prepare_after_transition.transition.intent.input_kind is InputKind.CLICK

    missing_start_target = decide(
        "post_confirm_break_array:9_of_9",
        ("破阵武学-突破-阵法-准备-页面",),
        {
            "start_break_array_challenge": 1,
            "confirm_break_array_challenge": 1,
        },
    )
    assert missing_start_target.status is TaskStatus.FAILED

    duplicate_start = decide(
        "battle",
        ("破阵武学-突破-阵法-准备-页面", "破阵武学-突破-阵法-准备-开始"),
        paired_counts(1),
    )
    assert duplicate_start.status is TaskStatus.FAILED
    assert POLICY.action_caps["start_break_array_battle"] == MAX_CHALLENGES

    battle_without_start = decide(
        "post_confirm_break_array:9_of_9",
        ("破阵武学-突破-阵法-战斗",),
        {
            "start_break_array_challenge": 1,
            "confirm_break_array_challenge": 1,
        },
    )
    assert battle_without_start.status is TaskStatus.FAILED

    unexpected_decrement = decide(
        "post_confirm_break_array:9_of_9",
        (
            "破阵武学-突破-阵法-页面",
            "破阵武学-突破-阵法-页面-剩余-8-共-9",
            "破阵武学-突破-阵法-开始",
            "破阵武学-突破-阵法-剩余",
        ),
        {
            "start_break_array_challenge": 1,
            "confirm_break_array_challenge": 1,
        },
        texts=("剩余挑战次数：8/9",),
    )
    assert unexpected_decrement.status is TaskStatus.FAILED

    unchanged = decide(
        "post_confirm_break_array:9_of_9",
        (
            "破阵武学-突破-阵法-页面",
            "破阵武学-突破-阵法-页面-剩余-8-共-9",
            "破阵武学-突破-阵法-开始",
            "破阵武学-突破-阵法-剩余",
        ),
        {
            "start_break_array_challenge": 1,
            "confirm_break_array_challenge": 1,
        },
        texts=("剩余挑战次数：9/9",),
    )
    assert unchanged.status is TaskStatus.FAILED

    unknown = decide(
        "post_confirm_break_array:9_of_9",
        ("破阵武学-突破-阵法-页面", "破阵武学-突破-阵法-未知-对话框"),
        {
            "start_break_array_challenge": 1,
            "confirm_break_array_challenge": 1,
        },
    )
    assert unknown.status is TaskStatus.FAILED


def test_third_result_requires_stable_page_with_live_counter_before_success():
    close = decide(
        "result",
        ("破阵武学-突破-阵法-结果", "破阵武学-突破-阵法-成功", "破阵武学-突破-阵法-结果-关闭"),
        paired_counts(MAX_CHALLENGES),
    )
    assert close.transition is not None
    assert close.transition.next_state == "verify"
    assert close.transition.postcondition == "break_array.page"
    assert close.transition.postcondition_alternatives == (
        "break_array.completed",
        "break_array.remaining_exhausted",
    )

    done = decide(
        "verify",
        ("破阵武学-突破-阵法-页面", "破阵武学-突破-阵法-剩余"),
        paired_counts(MAX_CHALLENGES),
        texts=("剩余挑战次数：6/9",),
    )
    assert done.status is TaskStatus.COMPLETED


def test_failure_and_polling_caps_fail_closed():
    failure = decide("battle", ("破阵武学-突破-阵法-战斗", "破阵武学-突破-阵法-失败"))
    assert failure.status is TaskStatus.FAILED

    exhausted = decide(
        "battle",
        ("破阵武学-突破-阵法-战斗", "破阵武学-突破-阵法-战斗-加载"),
        paired_counts(1, wait_break_array_battle=MAX_BATTLE_POLLS),
    )
    assert exhausted.status is TaskStatus.FAILED
    assert POLICY.max_steps >= MAX_CHALLENGES + MAX_BATTLE_POLLS
    assert POLICY.action_caps["start_break_array_challenge"] == MAX_CHALLENGES
    assert POLICY.action_caps["confirm_break_array_challenge"] == MAX_CHALLENGES
    assert POLICY.action_caps["start_break_array_battle"] == MAX_CHALLENGES

    startup_wait = decide("home", ("破阵武学-突破-阵法-启动-加载",))
    assert startup_wait.transition is not None
    assert startup_wait.transition.intent.action_id == "wait_break_array_startup"
    assert startup_wait.transition.intent.input_kind is InputKind.NONE
    assert startup_wait.transition.postcondition == "break_array.startup_loading"
    assert POLICY.action_caps["wait_break_array_startup"] == MAX_STARTUP_POLLS

    startup_exhausted = decide(
        "home",
        ("破阵武学-突破-阵法-启动-加载",),
        {"wait_break_array_startup": MAX_STARTUP_POLLS},
    )
    assert startup_exhausted.status is TaskStatus.FAILED


def test_remaining_counter_limits_a_resumed_run_to_the_daily_remainder():
    start = decide(
        "break_array",
        ("破阵武学-突破-阵法-页面", "破阵武学-突破-阵法-开始", "破阵武学-突破-阵法-剩余"),
        texts=("剩余挑战次数：2/9",),
    )
    assert start.transition is not None
    assert start.transition.intent.action_id == "start_break_array_challenge"

    done = decide(
        "break_array",
        ("破阵武学-突破-阵法-页面", "破阵武学-突破-阵法-剩余-耗尽"),
        paired_counts(2),
        texts=("0/9",),
    )
    assert done.status is TaskStatus.COMPLETED


def test_invalid_remaining_counter_fails_closed():
    invalid = decide(
        "break_array",
        ("破阵武学-突破-阵法-页面", "破阵武学-突破-阵法-开始", "破阵武学-突破-阵法-剩余"),
        texts=("剩余挑战次数：10/9",),
    )
    assert invalid.status is TaskStatus.FAILED


def test_loading_poll_postcondition_accepts_a_still_loading_frame():
    polling = decide(
        "battle",
        ("破阵武学-突破-阵法-战斗-加载",),
        paired_counts(1),
    )
    assert polling.transition is not None
    assert polling.transition.intent.action_id == "wait_break_array_battle"
    assert polling.transition.postcondition == "break_array.battle_loading"
    assert "破阵武学-突破-阵法-战斗" in polling.transition.postcondition_alternatives


def test_startup_loading_wait_is_bounded_and_accepts_only_known_task_boundaries():
    waiting = decide("home", ("破阵武学-突破-阵法-启动-加载",))
    assert waiting.transition is not None
    assert waiting.transition.next_state == "home"
    assert waiting.transition.intent.page_marker == "破阵武学-突破-阵法-启动-加载"
    assert waiting.transition.intent.target_marker == "破阵武学-突破-阵法-启动-加载"
    assert waiting.transition.intent.input_kind is InputKind.NONE
    assert waiting.transition.postcondition_alternatives == (
        "break_array.home",
        "activity.entry",
        "activity.page",
        "break_array.page",
        "break_array.completed",
        "break_array.remaining_exhausted",
        "break_array.unavailable",
    )

    loading_boundary = decide(
        "home",
        ("破阵武学-突破-阵法-启动-加载", "破阵武学-活动-入口"),
    )
    assert loading_boundary.transition is not None
    assert loading_boundary.transition.intent.action_id == "open_break_array_activity"


def test_confirm_transition_never_spends_battle_wait_and_unknown_still_fails():
    pending_start_counts = {
        "start_break_array_challenge": 1,
        "confirm_break_array_challenge": 1,
    }
    transition = decide(
        "battle",
        ("破阵武学-突破-阵法-确认-过渡",),
        pending_start_counts,
    )
    assert transition.status is TaskStatus.FAILED
    assert transition.transition is None

    exhausted = decide(
        "battle",
        ("破阵武学-突破-阵法-确认-过渡",),
        {
            **pending_start_counts,
            "wait_break_array_battle": MAX_BATTLE_POLLS,
        },
    )
    assert exhausted.status is TaskStatus.FAILED

    unknown = decide(
        "battle",
        (),
        paired_counts(1, wait_break_array_battle=1),
    )
    assert unknown.status is TaskStatus.FAILED


def test_terminal_postconditions_are_stable_and_distinct():
    assert terminal_postcondition(TaskStatus.COMPLETED) == "break_array.three_challenges"
    assert terminal_postcondition(TaskStatus.ALREADY_COMPLETE) == "break_array.daily_exhausted"
    assert terminal_postcondition(TaskStatus.NOT_ELIGIBLE) == "break_array.unavailable"
    assert terminal_postcondition(TaskStatus.FAILED) == "break_array.postcondition_missing"
