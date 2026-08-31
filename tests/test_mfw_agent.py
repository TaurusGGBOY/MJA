from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from agent.custom.action.guarded_input import GuardedInput
from agent.custom.action.restart_game import RestartGameSurface
from agent.custom.action.runtime_health import RuntimeHealth
from agent.custom.action.task_lifecycle import (
    BeginTask,
    CloseKnownPaintingSurface,
)
from agent.custom.support.state import RUN_STORE
from tests.mfw.fakes import (
    FailingController,
    FakeArgv,
    FakeContext,
    and_reco,
    hit_reco,
    miss_reco,
)


def _action_argv(reco_detail, *, kind: str = "click", evidence: dict | None = None):
    payload = {
        "task_id": "MAIL_REWARD_DAILY",
        "action_id": "claim_all_mail",
        "kind": kind,
        "evidence": evidence or {"page_index": 0, "target_index": 1},
    }
    return FakeArgv(json.dumps(payload), reco_detail=reco_detail)


def test_guarded_input_clicks_only_after_page_target_and_budget_match():
    context = FakeContext()
    RUN_STORE.begin("MAIL_REWARD_DAILY")
    argv = _action_argv(
        and_reco(hit_reco("邮件奖励-邮件-页面"), hit_reco("1049-邮件奖励-邮件-领取-全部"))
    )

    assert GuardedInput().run(context, argv) is True
    assert context.tasker.controller.actions == [("click", (120, 210))]


def test_guarded_input_clicks_verified_target_box_inside_and_result():
    context = FakeContext()
    RUN_STORE.begin("MAIL_REWARD_DAILY")
    argv = _action_argv(
        and_reco(
            hit_reco("邮件奖励-邮件-页面", (10, 20, 300, 200)),
            hit_reco("1049-邮件奖励-邮件-领取-全部", (150, 240, 40, 20)),
        )
    )

    assert GuardedInput().run(context, argv) is True
    assert context.tasker.controller.actions == [("click", (170, 250))]


def test_guarded_input_uses_mail_claim_button_center_instead_of_ocr_baseline():
    context = FakeContext()
    RUN_STORE.begin("MAIL_REWARD_DAILY")
    payload = {
        "task_id": "MAIL_REWARD_DAILY",
        "action_id": "claim_all_mail",
        "kind": "click",
        "fixed_click_mode": "mail_claim_all_button",
        "evidence": {
            "page_index": 0,
            "target_index": 1,
            "page_name": "1053-邮件奖励-邮件-关闭",
            "target_name": "1049-邮件奖励-邮件-领取-全部",
        },
    }
    argv = FakeArgv(
        json.dumps(payload),
        reco_detail=and_reco(
            hit_reco("1053-邮件奖励-邮件-关闭", (1053, 115, 45, 45)),
            hit_reco("1049-邮件奖励-邮件-领取-全部", (245, 563, 68, 19)),
        ),
    )

    assert GuardedInput().run(context, argv) is True
    assert context.tasker.controller.actions == [("click", (280, 557))]


def test_guarded_input_opens_painting_scroll_at_named_world_anchor():
    context = FakeContext()
    RUN_STORE.begin("BUY_TEA_DAILY")
    payload = {
        "task_id": "BUY_TEA_DAILY",
        "action_id": "open_painting_scroll",
        "kind": "click",
        "fixed_click_mode": "painting_scroll_button",
        "evidence": {
            "page_index": 0,
            "target_index": 1,
            "page_name": "0210-买茶-茶-主页-页面",
            "target_name": "0211-买茶-茶-画卷-滚动-入口",
        },
    }
    argv = FakeArgv(
        json.dumps(payload),
        reco_detail=and_reco(
            hit_reco("0210-买茶-茶-主页-页面", (1040, 0, 240, 110)),
            hit_reco("0211-买茶-茶-画卷-滚动-入口", (1040, 0, 240, 110)),
        ),
    )

    assert GuardedInput().run(context, argv) is True
    assert context.tasker.controller.actions == [("click", (1130, 62))]


def test_guarded_input_assigns_sweep_ticket_at_fixed_plus_anchor_without_ticket_ocr():
    context = FakeContext()
    RUN_STORE.begin("DUNGEON_SWEEP_DAILY")
    payload = {
        "task_id": "DUNGEON_SWEEP_DAILY",
        "action_id": "assign_sweep_ticket",
        "kind": "click",
        "fixed_click_mode": "dungeon_yanwang_master_plus",
        "evidence": {
            "page_index": 0,
            "target_index": 2,
            "page_name": "0355-副本扫荡-副本-扫荡-面板",
            "target_name": "0358-副本扫荡-副本-宗师-80",
        },
    }
    argv = FakeArgv(
        json.dumps(payload),
        reco_detail=and_reco(
            hit_reco("0355-副本扫荡-副本-扫荡-面板"),
            hit_reco("0357-副本扫荡-副本-扫荡-燕王-秘陵-卡片"),
            hit_reco("0358-副本扫荡-副本-宗师-80"),
        ),
    )

    assert GuardedInput().run(context, argv) is True
    assert context.tasker.controller.actions == [("click", (1247, 422))]
    assert RUN_STORE.snapshot("DUNGEON_SWEEP_DAILY")["resources"] == {}


def test_guarded_input_closes_equipment_page_with_a_regular_controller_click():
    context = FakeContext()
    RUN_STORE.begin("EQUIPMENT_DECOMPOSE_DAILY")
    payload = {
        "task_id": "EQUIPMENT_DECOMPOSE_DAILY",
        "action_id": "close_equipment_page",
        "kind": "click",
        "fixed_click_mode": "equipment_page_close",
        "evidence": {
            "page_index": 0,
            "target_index": 1,
            "page_name": "0462-分解装备-装备-分解-页面",
            "target_name": "0474-分解装备-装备-关闭",
        },
    }
    argv = FakeArgv(
        json.dumps(payload),
        reco_detail=and_reco(
            hit_reco("0462-分解装备-装备-分解-页面", (0, 0, 1280, 720)),
            hit_reco("0474-分解装备-装备-关闭", (1160, 0, 100, 100)),
        ),
    )

    assert GuardedInput().run(context, argv) is True
    assert context.tasker.controller.actions == [("click", (1218, 56))]


def test_known_painting_surface_cleanup_uses_the_small_close_anchor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent.custom.action import task_lifecycle

    monkeypatch.setattr(task_lifecycle, "sleep", lambda _seconds: None)
    context = FakeContext()

    assert CloseKnownPaintingSurface().run(context, FakeArgv("{}")) is True
    assert context.tasker.controller.actions == [("click", (1214, 42))]


def test_guarded_input_dismisses_jianlin_stamina_purchase_at_safe_close_anchor() -> None:
    context = FakeContext()
    RUN_STORE.begin("JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY")
    payload = {
        "task_id": "JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY",
        "action_id": "dismiss_jianlin_stamina_purchase",
        "kind": "click",
        "fixed_click_mode": "jianlin_page_close",
        "evidence": {
            "page_index": 0,
            "target_index": 2,
            "page_name": "0978-剑林凝结体体力-剑林-体力-购买-提示",
            "target_name": "0981-剑林凝结体体力-剑林-体力-价格50-可选",
        },
    }
    argv = FakeArgv(
        json.dumps(payload),
        reco_detail=and_reco(
            hit_reco("0978-剑林凝结体体力-剑林-体力-购买-提示"),
            hit_reco("0979-剑林凝结体体力-剑林-体力-加号80"),
            hit_reco("0981-剑林凝结体体力-剑林-体力-价格50-可选"),
        ),
    )

    assert GuardedInput().run(context, argv) is True
    assert context.tasker.controller.actions == [("click", (1214, 42))]


def test_guarded_input_clicks_shadow_foreground_triplet_in_fixed_order():
    context = FakeContext()
    RUN_STORE.begin("SHADOW_RUINS_DAILY")
    payload = {
        "task_id": "SHADOW_RUINS_DAILY",
        "action_id": "advance_shadow_foreground_triplet",
        "kind": "click",
        "fixed_click_boxes": [
            [436, 536, 24, 24],
            [629, 536, 24, 24],
            [822, 536, 24, 24],
        ],
        "evidence": {
            "page_index": 0,
            "target_index": 1,
            "page_name": "1200-影之遗迹-影-探索-页面",
            "target_name": "影之遗迹-影-前台-就绪",
        },
    }
    argv = FakeArgv(
        json.dumps(payload),
        reco_detail=and_reco(
            hit_reco("1200-影之遗迹-影-探索-页面", (850, 0, 400, 720)),
            hit_reco("影之遗迹-影-前台-就绪", (1040, 80, 90, 30)),
        ),
    )

    assert GuardedInput().run(context, argv) is True
    assert context.tasker.controller.actions == [
        ("click", (448, 548)),
        ("click", (641, 548)),
        ("click", (834, 548)),
    ]


def test_guarded_input_rejects_fixed_click_boxes_for_other_actions():
    context = FakeContext()
    RUN_STORE.begin("MAIL_REWARD_DAILY")
    payload = {
        "task_id": "MAIL_REWARD_DAILY",
        "action_id": "claim_all_mail",
        "kind": "click",
        "fixed_click_boxes": [[436, 536, 24, 24]] * 3,
        "evidence": {"page_index": 0, "target_index": 1},
    }

    assert GuardedInput().run(
        context,
        FakeArgv(
            json.dumps(payload),
            reco_detail=and_reco(
                hit_reco("邮件奖励-邮件-页面"),
                hit_reco("1049-邮件奖励-邮件-领取-全部"),
            ),
        ),
    ) is False
    assert context.tasker.controller.actions == []


def test_guarded_input_uses_named_blank_area_for_shadow_result_dismissal():
    context = FakeContext()
    RUN_STORE.begin("SHADOW_RUINS_DAILY")
    payload = {
        "task_id": "SHADOW_RUINS_DAILY",
        "action_id": "dismiss_shadow_battle_result",
        "kind": "click",
        "fixed_click_mode": "shadow_result_blank",
        "evidence": {
            "page_index": 0,
            "target_index": 1,
            "page_name": "1201-影之遗迹-影-战斗-结果-页面",
            "target_name": "1202-影之遗迹-影-战斗-胜利",
        },
    }
    argv = FakeArgv(
        json.dumps(payload),
        reco_detail=and_reco(
            hit_reco("1201-影之遗迹-影-战斗-结果-页面", (650, 0, 630, 240)),
            hit_reco("1202-影之遗迹-影-战斗-胜利", (780, 100, 300, 140)),
        ),
    )

    assert GuardedInput().run(context, argv) is True
    assert context.tasker.controller.actions == [("click", (640, 660))]


def test_guarded_input_uses_named_blank_area_for_ring_result_dismissal():
    context = FakeContext()
    RUN_STORE.begin("RING_CHALLENGE_DAILY")
    payload = {
        "task_id": "RING_CHALLENGE_DAILY",
        "action_id": "dismiss_ring_result",
        "kind": "click",
        "fixed_click_mode": "ring_result_blank",
        "evidence": {
            "page_index": 0,
            "target_index": 1,
            "page_name": "1159-擂台挑战-擂台-战斗-结果",
            "target_name": "1165-擂台挑战-擂台-结果-关闭",
        },
    }
    argv = FakeArgv(
        json.dumps(payload),
        reco_detail=and_reco(
            hit_reco("1159-擂台挑战-擂台-战斗-结果", (740, 100, 390, 145)),
            hit_reco("1165-擂台挑战-擂台-结果-关闭", (770, 625, 150, 35)),
        ),
    )

    assert GuardedInput().run(context, argv) is True
    assert context.tasker.controller.actions == [("click", (640, 660))]


def test_guarded_input_uses_named_blank_area_for_guild_result_dismissal():
    context = FakeContext()
    RUN_STORE.begin("GUILD_ACTIVITY_CHALLENGE_DAILY")
    payload = {
        "task_id": "GUILD_ACTIVITY_CHALLENGE_DAILY",
        "action_id": "dismiss_guild_result",
        "kind": "click",
        "fixed_click_mode": "guild_result_blank",
        "evidence": {
            "page_index": 0,
            "target_index": 1,
            "page_name": "0582-帮派活动挑战-帮派-结果-页面",
            "target_name": "0583-帮派活动挑战-帮派-结果-胜利",
        },
    }
    argv = FakeArgv(
        json.dumps(payload),
        reco_detail=and_reco(
            hit_reco("0582-帮派活动挑战-帮派-结果-页面", (700, 70, 580, 210)),
            hit_reco("0583-帮派活动挑战-帮派-结果-胜利", (700, 70, 580, 210)),
        ),
    )

    assert GuardedInput().run(context, argv) is True
    assert context.tasker.controller.actions == [("click", (640, 660))]


def test_guarded_input_uses_named_blank_area_for_guild_defeat_dismissal():
    context = FakeContext()
    RUN_STORE.begin("GUILD_ACTIVITY_CHALLENGE_DAILY")
    payload = {
        "task_id": "GUILD_ACTIVITY_CHALLENGE_DAILY",
        "action_id": "dismiss_guild_defeat_result",
        "kind": "click",
        "fixed_click_mode": "guild_result_defeat_blank",
        "evidence": {
            "page_index": 0,
            "target_index": 1,
            "page_name": "0584-帮派活动挑战-帮派-结果-失败-2",
            "target_name": "0585-帮派活动挑战-帮派-结果-失败-提升",
        },
    }
    argv = FakeArgv(
        json.dumps(payload),
        reco_detail=and_reco(
            hit_reco("0584-帮派活动挑战-帮派-结果-失败-2", (700, 70, 580, 210)),
            hit_reco("0585-帮派活动挑战-帮派-结果-失败-提升", (840, 390, 340, 90)),
        ),
    )

    assert GuardedInput().run(context, argv) is True
    assert context.tasker.controller.actions == [("click", (640, 660))]


def test_guarded_input_uses_mid_lower_blank_area_for_guild_reward_overlays():
    cases = (
        (
            "dismiss_guild_activity_reward_popup",
            "guild_activity_reward_blank",
            (640, 660),
        ),
        (
            "dismiss_guild_defeat_reward",
            "guild_activity_reward_blank",
            (640, 660),
        ),
        (
            "dismiss_guild_conquest_reward",
            "guild_activity_reward_blank",
            (640, 660),
        ),
        (
            "close_guild_conquest_reward",
            "guild_activity_close",
            (1221, 46),
        ),
    )
    for action_id, mode, expected_point in cases:
        context = FakeContext()
        RUN_STORE.begin("GUILD_ACTIVITY_CHALLENGE_DAILY")
        payload = {
            "task_id": "GUILD_ACTIVITY_CHALLENGE_DAILY",
            "action_id": action_id,
            "kind": "click",
            "fixed_click_mode": mode,
            "evidence": {
                "page_index": 0,
                "target_index": 0,
                "page_name": "reward-target",
                "target_name": "reward-target",
            },
        }
        argv = FakeArgv(
            json.dumps(payload),
            reco_detail=and_reco(hit_reco("reward-target", (500, 600, 200, 80))),
        )

        assert GuardedInput().run(context, argv) is True
        assert context.tasker.controller.actions == [("click", expected_point)]


def test_guarded_input_uses_separate_safe_blank_area_for_shadow_reward_dismissal():
    context = FakeContext()
    RUN_STORE.begin("SHADOW_RUINS_DAILY")
    payload = {
        "task_id": "SHADOW_RUINS_DAILY",
        "action_id": "dismiss_shadow_reward_popup",
        "kind": "click",
        "fixed_click_mode": "shadow_reward_blank",
        "evidence": {
            "page_index": 0,
            "target_index": 1,
            "page_name": "1204-影之遗迹-影-奖励",
            "target_name": "1205-影之遗迹-影-奖励-关闭",
        },
    }
    argv = FakeArgv(
        json.dumps(payload),
        reco_detail=and_reco(
            hit_reco("1204-影之遗迹-影-奖励", (0, 100, 1280, 620)),
            hit_reco("1205-影之遗迹-影-奖励-关闭", (500, 650, 300, 40)),
        ),
    )

    assert GuardedInput().run(context, argv) is True
    assert context.tasker.controller.actions == [("click", (650, 677))]


def test_guarded_input_accepts_named_same_index_shadow_reward_evidence():
    context = FakeContext()
    RUN_STORE.begin("SHADOW_RUINS_DAILY")
    evidence_name = "影之遗迹-影-胜利-宝箱-奖励"
    payload = {
        "task_id": "SHADOW_RUINS_DAILY",
        "action_id": "dismiss_shadow_reward_popup",
        "kind": "click",
        "fixed_click_mode": "shadow_reward_blank",
        "evidence": {
            "page_index": 0,
            "target_index": 0,
            "page_name": evidence_name,
            "target_name": evidence_name,
        },
    }
    argv = FakeArgv(
        json.dumps(payload),
        reco_detail=and_reco(hit_reco(evidence_name, (168, 238, 56, 235))),
    )

    assert GuardedInput().run(context, argv) is True
    assert context.tasker.controller.actions == [("click", (650, 677))]


def test_guarded_input_uses_named_shadow_stage_entry_button():
    context = FakeContext()
    RUN_STORE.begin("SHADOW_RUINS_DAILY")
    payload = {
        "task_id": "SHADOW_RUINS_DAILY",
        "action_id": "enter_shadow_stage",
        "kind": "click",
        "fixed_click_mode": "shadow_stage_entry_button",
        "evidence": {
            "page_index": 0,
            "target_index": 1,
            "page_name": "1191-影之遗迹-影-页面",
            "target_name": "1193-影之遗迹-影-关卡-入口",
        },
    }
    argv = FakeArgv(
        json.dumps(payload),
        reco_detail=and_reco(
            hit_reco("1191-影之遗迹-影-页面", (0, 0, 1280, 720)),
            hit_reco("1193-影之遗迹-影-关卡-入口", (870, 530, 58, 32)),
        ),
    )

    assert GuardedInput().run(context, argv) is True
    assert context.tasker.controller.actions == [("click", (845, 515))]


def test_guarded_input_swipe_uses_bounded_relative_vector():
    context = FakeContext()
    RUN_STORE.begin("MAIL_REWARD_DAILY")
    argv = _action_argv(
        and_reco(hit_reco("邮件奖励-邮件-页面"), hit_reco("1049-邮件奖励-邮件-领取-全部")),
        kind="swipe",
        evidence={"page_index": 0, "target_index": 1, "dx": 10, "dy": -5, "duration_ms": 300},
    )

    assert GuardedInput().run(context, argv) is True
    assert context.tasker.controller.actions == [("swipe", (120, 210, 130, 205, 300))]


def test_guarded_input_swipe_uses_verified_target_box_for_shape_and_input():
    context = FakeContext()
    RUN_STORE.begin("MAIL_REWARD_DAILY")
    argv = _action_argv(
        and_reco(
            hit_reco("邮件奖励-邮件-页面", (0, 0, 40, 20)),
            hit_reco("mail.list", (100, 300, 200, 200)),
        ),
        kind="swipe",
        evidence={"page_index": 0, "target_index": 1, "dx": 0, "dy": -260, "duration_ms": 350},
    )

    assert GuardedInput().run(context, argv) is True
    assert context.tasker.controller.actions == [("swipe", (200, 400, 200, 140, 350))]


def test_guarded_input_none_validates_evidence_without_touching_controller():
    context = FakeContext()
    RUN_STORE.begin("RING_CHALLENGE_DAILY")
    argv = FakeArgv(
        json.dumps(
            {
                "task_id": "RING_CHALLENGE_DAILY",
                "action_id": "wait_ring_battle",
                "kind": "none",
                "evidence": {"page_index": 0, "target_index": 0},
            }
        ),
        reco_detail=and_reco(hit_reco("1155-擂台挑战-擂台-战斗-加载")),
    )

    assert GuardedInput().run(context, argv) is True
    assert context.tasker.controller.actions == []


def test_guarded_input_accepts_dynamic_positive_resource_amount():
    def ocr(name: str, text: str, box: tuple[int, int, int, int]):
        return SimpleNamespace(
            name=name,
            hit=True,
            box=box,
            filtered_results=[SimpleNamespace(text=text)],
            best_result=SimpleNamespace(text=text),
        )

    payload = {
        "task_id": "DUNGEON_SWEEP_DAILY",
        "action_id": "assign_sweep_ticket",
        "kind": "click",
        "resource_id": "副本票",
        "resource_index": 2,
        "amount_index": 3,
        "budget_amount": 1,
        "evidence": {
            "page_index": 0,
            "target_index": 1,
            "page_name": "0355-副本扫荡-副本-扫荡-面板",
            "target_name": "0359-副本扫荡-副本-券-加号",
        },
    }
    context = FakeContext()
    RUN_STORE.begin("DUNGEON_SWEEP_DAILY")
    argv = FakeArgv(
        json.dumps(payload),
        reco_detail=and_reco(
            hit_reco("0355-副本扫荡-副本-扫荡-面板"),
            hit_reco("0359-副本扫荡-副本-券-加号", (1180, 360, 40, 40)),
            ocr("副本票", "副本票", (740, 490, 100, 40)),
            ocr("0361-副本扫荡-副本-券-余额", "2(-2)", (900, 490, 100, 40)),
        ),
    )

    assert GuardedInput().run(context, argv) is True
    assert context.tasker.controller.actions == [("click", (1200, 380))]
    assert RUN_STORE.snapshot("DUNGEON_SWEEP_DAILY")["resources"] == {"副本票": 1}


def test_guarded_input_allows_explicit_visual_resource_identity_but_not_by_default():
    def ocr(name: str, text: str, box: tuple[int, int, int, int]):
        return SimpleNamespace(
            name=name,
            hit=True,
            box=box,
            filtered_results=[SimpleNamespace(text=text)],
            best_result=SimpleNamespace(text=text),
        )

    payload = {
        "task_id": "DUNGEON_SWEEP_DAILY",
        "action_id": "assign_sweep_ticket",
        "kind": "click",
        "resource_id": "副本票",
        "resource_index": 2,
        "amount_index": 3,
        "budget_amount": 1,
        "evidence": {
            "page_index": 0,
            "target_index": 1,
            "page_name": "0355-副本扫荡-副本-扫荡-面板",
            "target_name": "0359-副本扫荡-副本-券-加号",
        },
    }
    reco_detail = and_reco(
        hit_reco("0355-副本扫荡-副本-扫荡-面板"),
        hit_reco("0359-副本扫荡-副本-券-加号", (1228, 400, 40, 40)),
        hit_reco("副本扫荡-副本-券-图标", (770, 510, 95, 75)),
        ocr("0361-副本扫荡-副本-券-余额", "2", (840, 520, 90, 70)),
    )
    context = FakeContext()
    RUN_STORE.begin("DUNGEON_SWEEP_DAILY")

    assert GuardedInput().run(
        context, FakeArgv(json.dumps(payload), reco_detail=reco_detail)
    ) is False
    assert context.tasker.controller.actions == []

    payload["resource_evidence_name"] = "副本扫荡-副本-券-图标"
    assert GuardedInput().run(
        context, FakeArgv(json.dumps(payload), reco_detail=reco_detail)
    ) is True
    assert context.tasker.controller.actions == [("click", (1248, 420))]
    assert RUN_STORE.snapshot("DUNGEON_SWEEP_DAILY")["resources"] == {"副本票": 1}


def test_guarded_input_visual_resource_identity_rejects_the_wrong_node_name():
    payload = {
        "task_id": "DUNGEON_SWEEP_DAILY",
        "action_id": "assign_sweep_ticket",
        "kind": "click",
        "resource_id": "副本票",
        "resource_index": 2,
        "resource_evidence_name": "副本扫荡-副本-券-图标",
        "amount_index": 3,
        "budget_amount": 1,
        "evidence": {"page_index": 0, "target_index": 1},
    }
    amount = SimpleNamespace(
        name="0361-副本扫荡-副本-券-余额",
        hit=True,
        box=(840, 520, 90, 70),
        filtered_results=[SimpleNamespace(text="2")],
        best_result=SimpleNamespace(text="2"),
    )
    context = FakeContext()
    RUN_STORE.begin("DUNGEON_SWEEP_DAILY")
    argv = FakeArgv(
        json.dumps(payload),
        reco_detail=and_reco(
            hit_reco("0355-副本扫荡-副本-扫荡-面板"),
            hit_reco("0359-副本扫荡-副本-券-加号", (1228, 400, 40, 40)),
            hit_reco("some.other.icon", (770, 510, 95, 75)),
            amount,
        ),
    )

    assert GuardedInput().run(context, argv) is False
    assert context.tasker.controller.actions == []


def test_guarded_input_accepts_resource_token_in_full_ocr_line():
    def ocr(name: str, text: str):
        return SimpleNamespace(
            name=name,
            hit=True,
            box=(700, 480, 150, 30),
            filtered_results=[SimpleNamespace(text=text)],
            best_result=SimpleNamespace(text=text),
        )

    payload = {
        "task_id": "BUY_TEA_DAILY",
        "action_id": "buy_tea",
        "kind": "click",
        "resource_id": "文",
        "resource_index": 2,
        "amount_index": 3,
        "observed_amount": 500,
        "budget_amount": 500,
        "evidence": {
            "page_index": 0,
            "target_index": 1,
            "page_name": "0222-买茶-茶-数量-面板",
            "target_name": "0225-买茶-茶-购买-确认",
        },
    }
    context = FakeContext()
    RUN_STORE.begin("BUY_TEA_DAILY")
    argv = FakeArgv(
        json.dumps(payload),
        reco_detail=and_reco(
            hit_reco("0222-买茶-茶-数量-面板"),
            hit_reco("0225-买茶-茶-购买-确认", (710, 545, 300, 65)),
            ocr("tea.currency.wen", "：500文"),
            ocr("tea.cost.500", "消耗：500文"),
        ),
    )

    assert GuardedInput().run(context, argv) is True
    assert context.tasker.controller.actions == [("click", (860, 577))]


def test_guarded_input_rejects_unverified_target_without_input():
    context = FakeContext()
    RUN_STORE.begin("MAIL_REWARD_DAILY")
    argv = _action_argv(
        and_reco(
            hit_reco("邮件奖励-邮件-页面"),
            miss_reco("1049-邮件奖励-邮件-领取-全部"),
        )
    )

    assert GuardedInput().run(context, argv) is False
    assert context.tasker.controller.actions == []
    assert RUN_STORE.snapshot("MAIL_REWARD_DAILY")["actions"] == {}


def test_guarded_input_rejects_removed_martial_breakthrough_action():
    payload = {
        "task_id": "MARTIAL_STUDY_BREAKTHROUGH_DAILY",
        "action_id": "breakthrough_martial_slot",
        "kind": "click",
        "material_id": "研习材料",
        "material_index": 2,
        "owned_index": 3,
        "required_index": 4,
        "evidence": {"page_index": 0, "target_index": 1},
    }
    context = FakeContext()
    RUN_STORE.begin("MARTIAL_STUDY_BREAKTHROUGH_DAILY")
    argv = FakeArgv(
        json.dumps(payload),
        reco_detail=and_reco(
            hit_reco("1072-武学突破-武学-页面"),
            hit_reco("martial.breakthrough_action"),
        ),
    )

    assert GuardedInput().run(context, argv) is False
    assert context.tasker.controller.actions == []


def test_guarded_input_does_not_downgrade_controller_failure():
    context = FakeContext(controller=FailingController(RuntimeError("device lost")))
    RUN_STORE.begin("MAIL_REWARD_DAILY")
    argv = _action_argv(
        and_reco(hit_reco("邮件奖励-邮件-页面"), hit_reco("1049-邮件奖励-邮件-领取-全部"))
    )

    with pytest.raises(RuntimeError, match="device lost"):
        GuardedInput().run(context, argv)


def test_guarded_input_raises_when_controller_wait_fails():
    class WaitFailureController:
        connected = True

        def post_click(self, x: int, y: int):
            return SimpleNamespace(wait=lambda: False)

    context = FakeContext(controller=WaitFailureController())
    RUN_STORE.begin("MAIL_REWARD_DAILY")
    argv = _action_argv(
        and_reco(hit_reco("邮件奖励-邮件-页面"), hit_reco("1049-邮件奖励-邮件-领取-全部"))
    )

    with pytest.raises(RuntimeError, match="controller click failed"):
        GuardedInput().run(context, argv)


def test_runtime_health_does_not_shell_out(monkeypatch):
    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("shell forbidden")
        ),
    )
    context = FakeContext()

    assert RuntimeHealth().run(context, FakeArgv("{}")) is True


def test_runtime_health_reports_disconnected_controller():
    context = FakeContext()
    context.tasker.controller.connected = False

    assert RuntimeHealth().run(context, FakeArgv("{}")) is False


def test_restart_game_surface_uses_only_maa_controller_lifecycle():
    context = FakeContext()
    calls = []

    class Job:
        def wait(self):
            return True

    def stop_app(intent):
        calls.append(("stop", intent))
        return Job()

    def start_app(intent):
        calls.append(("start", intent))
        return Job()

    context.tasker.controller.post_stop_app = stop_app
    context.tasker.controller.post_start_app = start_app
    argv = FakeArgv(
        json.dumps(
            {
                "package": "com.hanjiasongshu.dr22",
                "activity": "com.hanjiasongshu.dr22/.MainActivity",
            }
        )
    )

    assert RestartGameSurface().run(context, argv) is True
    assert calls == [
        ("stop", "com.hanjiasongshu.dr22"),
        ("start", "com.hanjiasongshu.dr22/.MainActivity"),
    ]


def test_task_lifecycle_starts_safety_only_session(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = FakeContext()

    begin_argv = FakeArgv(json.dumps({"task_id": "MAIL_REWARD_DAILY"}))
    begin_argv.task_detail = SimpleNamespace(task_id=3001)
    assert BeginTask().run(context, begin_argv) is True
    from agent.custom.support.task_session import TASK_SESSIONS

    assert TASK_SESSIONS.business_task_id(3001) == "MAIL_REWARD_DAILY"
    assert not list(tmp_path.rglob("result.json"))
