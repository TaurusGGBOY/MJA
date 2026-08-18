from __future__ import annotations

from agent.custom.support.policy import TASK_POLICIES
from tests.mfw.task_contract import (
    TaskContract,
    assert_fixture_matrix,
    assert_guarded_actions,
    assert_no_side_effect_retry,
    assert_ordered_actions,
    assert_outcome,
    assert_reachable,
    assert_task_contract,
    assert_terminal_after_loop,
    load_task_declaration,
    load_task_nodes,
)

MAIL = TaskContract("MAIL_REWARD_DAILY", "daily/mail_reward_daily.json")
SHOP = TaskContract("SHOP_FREE_GIFT_DAILY", "daily/shop_free_gift_daily.json")
APPRAISAL = TaskContract("FREE_APPRAISAL_DAILY", "daily/free_appraisal_daily.json")
TRIAL = TaskContract("TRIAL_SWORD_DAILY", "daily/trial_sword_daily.json")
HERO = TaskContract("HERO_DISPATCH_DAILY", "daily/hero_dispatch_daily.json")
COLLECTION = TaskContract(
    "COLLECTION_DEPLOYMENT_DAILY",
    "daily/collection_deployment_daily.json",
)
WEEKLY = TaskContract(
    "WEEKLY_FREE_GIFT_MONDAY",
    "daily/weekly_free_gift_monday.json",
    group="周常",
)
DAILY_REWARD = TaskContract(
    "DAILY_TASK_REWARD_CLAIM_DAILY",
    "daily/daily_task_reward_claim_daily.json",
)
BATTLE_PASS = TaskContract(
    "BATTLE_PASS_REWARD_DAILY",
    "daily/battle_pass_reward_daily.json",
)


def test_mail_task_contract_and_existing_fixture_matrix() -> None:
    assert_task_contract(MAIL)
    assert_fixture_matrix(
        MAIL.task_id,
        {"entry", "actionable", "completed", "danger"},
    )


def test_mail_flow_guards_every_side_effect_and_has_truthful_outcomes() -> None:
    nodes = load_task_nodes(MAIL)
    assert nodes["邮件奖励-任务入口"]["action"] == "DoNothing"
    assert nodes["邮件奖励-任务入口"]["next"] == ["邮件奖励-打开-面板"]
    assert "on_error" not in nodes["邮件奖励-任务入口"]
    assert nodes["邮件奖励-页面-探测"]["next"] == ["邮件奖励-领取"]
    assert nodes["邮件奖励-页面-探测"]["on_error"] == ["邮件奖励-领取"]
    assert nodes["邮件奖励-领取"]["on_error"] == ["邮件奖励-已完成"]
    assert nodes["邮件奖励-已完成"]["next"] == ["邮件奖励-关闭"]
    assert nodes["邮件奖励-主页-页面"]["recognition"] == {
        "type": "And",
        "param": {"all_of": ["公共-游戏主页-页面"], "box_index": 0},
    }
    assert nodes["邮件奖励-面板-探测"]["threshold"] == 0.375
    assert nodes["邮件奖励-面板-页面"]["threshold"] == 0.375
    assert nodes["邮件奖励-面板-邮件-入口"]["threshold"] == 0.39
    assert nodes["邮件奖励-面板-关闭"]["threshold"] == 0.1
    assert_guarded_actions(
        nodes,
        MAIL.task_id,
        [
            "open_function_panel",
            "open_mail",
            "claim_all_mail",
            "close_reward_popup",
            "close_mail",
        "close_function_panel",
    ],
    )
    assert nodes["邮件奖励-奖励-探测"]["next"] == ["邮件奖励-领取-成功"]
    assert nodes["邮件奖励-领取-成功"]["next"] == ["邮件奖励-关闭-奖励"]
    assert nodes["邮件奖励-关闭-奖励"]["next"] == ["邮件奖励-关闭"]
    assert_outcome(nodes, "邮件奖励-领取-成功", "success", "mail.reward_claimed")
    assert_outcome(nodes, "邮件奖励-已完成", "already_complete", "mail.empty")
    assert nodes["邮件奖励-已完成"]["custom_action_param"][
        "defer_home_boundary"
    ] is True
    assert nodes["邮件奖励-领取-成功"]["custom_action_param"][
        "defer_home_boundary"
    ] is True
    assert nodes["邮件奖励-关闭-面板"]["next"] == ["公共-主页边界"]
    assert_outcome(nodes, "邮件奖励-记录-失败", "failed", "MAIL_POSTCONDITION_MISSING")


def test_shop_task_contract_and_existing_fixture_matrix() -> None:
    assert_task_contract(SHOP)
    assert_fixture_matrix(
        SHOP.task_id,
        {"entry", "actionable", "completed", "danger"},
    )
    nodes = load_task_nodes(SHOP)
    assert nodes["商店免费礼包-任务入口"]["next"] == [
        "商店免费礼包-直接-状态-探测",
        "商店免费礼包-直接-领取-门禁",
        "商店免费礼包-打开-周期",
        "商店免费礼包-权益-页面-探测",
        "商店免费礼包-面板-探测",
        "商店免费礼包-页面-探测",
        "商店免费礼包-主页-探测",
    ]
    assert nodes["商店免费礼包-任务入口"]["on_error"] == [
        "商店免费礼包-运行时-恢复-尝试-1",
        "商店免费礼包-运行时-恢复-尝试-2",
        "商店免费礼包-运行时-恢复-耗尽",
    ]
    assert nodes["商店免费礼包-状态-探测"]["recognition"] == "OCR"
    assert nodes["商店免费礼包-状态-探测"]["expected"] == [
        "已领取",
        "今日已领取",
        "领取完毕",
    ]
    assert nodes["商店免费礼包-状态-探测"]["on_error"] == [
        "商店免费礼包-领取-门禁",
        "商店免费礼包-运行时-恢复-尝试-1",
        "商店免费礼包-运行时-恢复-尝试-2",
        "商店免费礼包-运行时-恢复-耗尽",
    ]
    assert nodes["商店免费礼包-权益-页面-探测"]["next"] == [
        "商店免费礼包-状态-探测",
        "商店免费礼包-领取-门禁",
    ]
    assert "threshold" not in nodes["商店免费礼包-主页-探测"]
    assert nodes["商店免费礼包-打开-周期"]["next"] == ["商店免费礼包-权益-页面-探测"]
    assert nodes["商店免费礼包-打开-周期"]["on_error"] == [
        "商店免费礼包-运行时-恢复-尝试-1",
        "商店免费礼包-运行时-恢复-尝试-2",
        "商店免费礼包-运行时-恢复-耗尽",
    ]
    assert nodes["商店免费礼包-商店-关闭"] == {
        "recognition": "ColorMatch",
        "lower": [0, 0, 0],
        "upper": [125, 125, 125],
        "roi": [1180, 0, 100, 100],
        "connected": True,
        "count": 180,
        "action": "DoNothing",
    }


def test_shop_flow_guards_every_side_effect_and_has_truthful_outcomes() -> None:
    nodes = load_task_nodes(SHOP)
    assert_guarded_actions(
        nodes,
        SHOP.task_id,
        [
            "open_function_panel",
            "open_shop",
            "open_period_benefits",
            "claim_free_gift",
            "dismiss_free_gift_reward",
            "close_shop",
            "close_function_panel",
        ],
    )
    assert_outcome(
        nodes,
        "商店免费礼包-记录-已完成",
        "already_complete",
        "shop.daily_free_gift_claimed",
    )
    assert_outcome(
        nodes,
        "商店免费礼包-记录-成功",
        "success",
        "shop.daily_free_gift_claimed",
    )
    assert_outcome(
        nodes,
        "商店免费礼包-记录-失败",
        "failed",
        "SHOP_POSTCONDITION_MISSING",
    )


def test_appraisal_task_contract_and_existing_fixture_matrix() -> None:
    assert_task_contract(APPRAISAL)
    assert_fixture_matrix(
        APPRAISAL.task_id,
        {"entry", "actionable", "completed", "danger"},
    )


def test_appraisal_flow_guards_every_side_effect_and_has_truthful_outcomes() -> None:
    nodes = load_task_nodes(APPRAISAL)
    assert nodes[APPRAISAL.entry]["next"][0] == "[JumpBack]公共-已知-画卷-关闭"
    assert nodes[APPRAISAL.entry]["next"][1] == "[JumpBack]免费鉴定-额外-弹窗-关闭"
    assert nodes["免费鉴定-鉴定-结果-弹窗"] == {
        "recognition": "TemplateMatch",
        "template": "daily/BUY_TEA_DAILY/shop_close.png",
        "roi": [1170, 0, 110, 110],
        "threshold": 0.39,
        "action": "DoNothing",
    }
    assert nodes["免费鉴定-关闭-奖励"]["next"] == [
        "[JumpBack]免费鉴定-额外-弹窗-关闭",
        "MJA_APPRAISAL_VERIFY",
        "免费鉴定-主页-之后-奖励",
    ]
    assert nodes["免费鉴定-额外-弹窗-关闭"]["custom_action_param"][
        "action_id"
    ] == "close_extra_reward_popup"
    assert nodes["免费鉴定-鉴定-额外-弹窗-页面"]["expected"] == "^秘宝收集$"
    assert nodes["免费鉴定-鉴定-额外-弹窗-关闭"]["template"] == (
        "daily/BUY_TEA_DAILY/shop_close.png"
    )
    assert nodes["免费鉴定-鉴定-免费-一次"] == {
        "recognition": "OCR",
        "expected": "^免费鉴宝$",
        "roi": [470, 590, 160, 60],
        "action": "DoNothing",
    }
    assert nodes["免费鉴定-鉴定-页面-关闭"] == {
        "recognition": "TemplateMatch",
        "template": "daily/BUY_TEA_DAILY/shop_close.png",
        "roi": [1170, 0, 110, 110],
        "threshold": 0.39,
        "action": "DoNothing",
    }
    assert_guarded_actions(
        nodes,
        APPRAISAL.task_id,
        [
            "close_function_panel",
            "close_extra_reward_popup",
            "open_appraisal",
            "claim_free_appraisal_once",
            "close_appraisal_popup",
            "close_appraisal_page",
        ],
    )
    assert_outcome(
        nodes,
        "MJA_APPRAISAL_ALREADY_COMPLETE",
        "already_complete",
        "appraisal.used",
    )
    assert_outcome(
        nodes,
        "免费鉴定-成功",
        "success",
        "appraisal.used",
    )
    assert_outcome(
        nodes,
        "免费鉴定-记录-失败",
        "failed",
        "APPRAISAL_POSTCONDITION_MISSING",
    )


def test_trial_task_contract_and_existing_fixture_matrix() -> None:
    declaration = load_task_declaration(TRIAL.task_id)
    assert declaration["label"]
    assert declaration["default_check"] is True
    assert declaration["group"] == [TRIAL.group]
    assert declaration["entry"] == TRIAL.entry
    nodes = load_task_nodes(TRIAL)
    assert TRIAL.entry in nodes
    assert_reachable(nodes, TRIAL.entry, "公共-通用停止")
    assert_reachable(nodes, TRIAL.entry, "公共-通用中止")
    assert_fixture_matrix(
        TRIAL.task_id,
        {"entry", "actionable", "completed", "danger"},
    )


def test_trial_flow_guards_every_side_effect_and_has_truthful_outcomes() -> None:
    nodes = load_task_nodes(TRIAL)
    assert nodes[TRIAL.entry]["next"][0] == "[JumpBack]公共-已知-画卷-关闭"
    assert_guarded_actions(
        nodes,
        TRIAL.task_id,
        [
            "open_trial_sword",
            "claim_trial_sword_reward",
            "close_reward_popup",
            "claim_free_trial",
            "confirm_free_trial",
            "close_trial",
        ],
    )
    assert_outcome(
        nodes,
        "MJA_TRIAL_ALREADY_COMPLETE",
        "success",
        "trial.free_used",
    )
    assert_outcome(
        nodes,
        "试剑-成功",
        "success",
        "trial.free_used",
    )
    assert_outcome(
        nodes,
        "试剑-记录-失败",
        "failed",
        "TRIAL_POSTCONDITION_MISSING",
    )


def test_trial_home_entry_uses_home_evidence_and_named_fixed_target() -> None:
    nodes = load_task_nodes(TRIAL)

    start = nodes["试剑-任务入口"]
    assert start["next"] == [
        "[JumpBack]公共-已知-画卷-关闭",
        "[JumpBack]公共-已知-茶-详情-关闭",
        "[JumpBack]公共-已知-茶-商店-关闭",
        "试剑-领取-奖励",
        "试剑-打开-试炼",
    ]
    assert start["on_error"] == ["[JumpBack]启动-游戏启动", "试剑-记录-失败"]
    assert start.get("retry_times", 0) == 0
    assert "MJA_TRIAL_HOME_PROBE" not in nodes

    open_trial = nodes["试剑-打开-试炼"]
    assert open_trial["recognition"]["param"] == {
        "all_of": ["公共-游戏主页-页面"],
        "box_index": 0,
    }
    assert "试剑-试炼-打开" not in nodes
    assert open_trial["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 0,
        "page_name": "公共-游戏主页-页面",
        "target_name": "公共-游戏主页-页面",
    }
    assert open_trial["custom_action_param"]["fixed_click_mode"] == (
        "trial_entry_button"
    )
    assert open_trial["retry_times"] == 0
    assert TASK_POLICIES[TRIAL.task_id].action_caps["open_trial_sword"] == 1


def test_trial_failure_paths_record_before_native_failure_and_never_stop_as_success() -> None:
    nodes = load_task_nodes(TRIAL)

    failure = nodes["试剑-记录-失败"]
    assert failure["custom_action_param"] == {
        "task_id": TRIAL.task_id,
        "status": "failed",
        "postcondition": "TRIAL_POSTCONDITION_MISSING",
        "error_code": "TRIAL_POSTCONDITION_MISSING",
        "native_fail_after_record": True,
    }
    assert failure["Abort"] is True
    assert failure["next"] == ["公共-通用中止"]

    guarded_nodes = {
        name: node
        for name, node in nodes.items()
        if node.get("custom_action") == "GuardedInput"
        and node.get("custom_action_param", {}).get("task_id") == TRIAL.task_id
    }
    assert guarded_nodes
    for node in guarded_nodes.values():
        assert node["on_error"] == ["试剑-记录-失败"]
        assert node.get("action") == "Custom"

    for action_id in (
        "open_trial_sword",
        "claim_trial_sword_reward",
        "close_reward_popup",
        "claim_free_trial",
        "confirm_free_trial",
        "close_trial",
    ):
        assert_no_side_effect_retry(nodes, action_id)

    terminal_predecessors = {
        name
        for name, node in nodes.items()
        if name.startswith("试剑-")
        and "公共-通用停止" in node.get("next", [])
    }
    assert terminal_predecessors == {
        "MJA_TRIAL_ALREADY_COMPLETE",
        "试剑-成功",
    }
    assert_reachable(
        nodes,
        "试剑-任务入口",
        "试剑-记录-失败",
    )


def test_trial_records_outcome_only_after_used_state_close_and_home_boundary() -> None:
    nodes = load_task_nodes(TRIAL)

    assert nodes["MJA_TRIAL_FREE_VERIFY"]["recognition"]["param"] == {
        "all_of": ["试剑-试炼-页面", "trial.free_used"],
        "box_index": 1,
    }
    assert nodes["MJA_TRIAL_FREE_VERIFY"]["next"] == [
        "试剑-关闭-成功"
    ]
    assert nodes["MJA_TRIAL_POST_REWARD_FREE_STATUS"]["next"] == [
        "试剑-关闭-成功"
    ]
    assert nodes["MJA_TRIAL_ALREADY_STATUS"]["next"] == [
        "MJA_TRIAL_CLOSE_ALREADY"
    ]
    assert nodes["MJA_TRIAL_PREEXISTING_FREE_STATUS"]["next"] == [
        "MJA_TRIAL_CLOSE_ALREADY"
    ]

    expected_close_evidence = {
        "page_index": 0,
        "target_index": 1,
        "page_name": "试剑-试炼-页面",
        "target_name": "试剑-试炼-关闭",
    }
    for close_name, home_name, outcome_name in (
        (
            "试剑-关闭-成功",
            "试剑-成功-主页-探测",
            "试剑-成功",
        ),
        (
            "MJA_TRIAL_CLOSE_ALREADY",
            "MJA_TRIAL_ALREADY_HOME_PROBE",
            "MJA_TRIAL_ALREADY_COMPLETE",
        ),
    ):
        close = nodes[close_name]
        assert close["custom_action_param"]["action_id"] == "close_trial"
        assert close["custom_action_param"]["evidence"] == expected_close_evidence
        assert close["next"] == [home_name]
        assert close["on_error"] == ["试剑-记录-失败"]

        home = nodes[home_name]
        assert home["recognition"]["param"] == {"all_of": ["邮件奖励-主页-页面"]}
        assert home["action"] == "DoNothing"
        assert home["next"] == [outcome_name]
        assert home["on_error"] == ["试剑-记录-失败"]

    assert_reachable(nodes, "MJA_TRIAL_FREE_VERIFY", "试剑-成功")
    assert_reachable(
        nodes,
        "MJA_TRIAL_ALREADY_STATUS",
        "MJA_TRIAL_ALREADY_COMPLETE",
    )


def test_hero_task_contract_and_existing_fixture_matrix() -> None:
    assert_task_contract(HERO)
    assert_fixture_matrix(
        HERO.task_id,
        {"entry", "actionable", "completed", "danger"},
    )


def test_hero_flow_guards_first_visible_dispatch_and_has_truthful_outcomes() -> None:
    nodes = load_task_nodes(HERO)
    assert TASK_POLICIES[HERO.task_id].action_caps["close_reward_popup"] == 6
    assert TASK_POLICIES[HERO.task_id].action_caps["select_first_visible_dispatch"] == 12
    assert nodes[HERO.entry]["on_error"] == [
        "英雄派遣-游戏启动恢复",
        "英雄派遣-记录-失败",
    ]
    assert nodes["英雄派遣-游戏启动恢复"]["max_hit"] == 1
    assert nodes["英雄派遣-游戏启动恢复"]["next"][-1] == (
        "[JumpBack]启动-游戏启动"
    )
    assert nodes["英雄派遣-领取-循环"]["max_hit"] == 6
    assert nodes["英雄派遣-填充-循环"]["max_hit"] == 6
    assert_terminal_after_loop(
        nodes,
        "英雄派遣-领取-循环",
        6,
        "HERO_CLAIM_LOOP_EXHAUSTED",
    )
    assert_terminal_after_loop(
        nodes,
        "英雄派遣-填充-循环",
        6,
        "HERO_DISPATCH_LOOP_EXHAUSTED",
    )
    assert nodes["英雄派遣-初始-领取"]["custom_action_param"]["action_id"] == (
        "select_first_visible_dispatch"
    )
    assert nodes["英雄派遣-初始-领取-按钮"]["next"] == ["英雄派遣-初始-领取-动作"]
    assert "完成派遣" in nodes["英雄派遣-英雄-首个-任务-可领取"]["expected"]
    assert nodes["英雄派遣-英雄-全部-已完成"]["expected"] == [
        r"任务\s*[:：]?\s*9\s*/\s*9",
        r"已完成\s*[:：]?\s*9",
    ]
    assert_ordered_actions(
        nodes,
        [
            "claim_first_dispatch",
            "select_first_visible_dispatch",
            "smart_configure_team",
            "dispatch_team",
        ],
    )
    assert_guarded_actions(
        nodes,
        HERO.task_id,
        [
            "open_painting_scroll",
            "open_hero_dispatch",
            "claim_first_dispatch",
            "close_reward_popup",
            "select_first_visible_dispatch",
            "smart_configure_team",
            "dispatch_team",
            "close_hero_dispatch",
            "close_hero_dispatch_painting",
        ],
    )
    assert_outcome(
        nodes,
        "英雄派遣-已完成-全部",
        "already_complete",
        "hero.all_completed",
    )
    assert_outcome(
        nodes,
        "英雄派遣-已完成-进度",
        "already_complete",
        "hero.first_task_in_progress",
    )
    assert_outcome(
        nodes,
        "英雄派遣-成功-全部",
        "success",
        "hero.all_completed",
    )
    assert_outcome(
        nodes,
        "英雄派遣-成功-进度",
        "success",
        "hero.first_task_in_progress",
    )
    assert_outcome(
        nodes,
        "英雄派遣-记录-失败",
        "failed",
        "HERO_POSTCONDITION_MISSING",
    )
    assert_outcome(
        nodes,
        "英雄派遣-填充-循环-耗尽",
        "failed",
        "hero.dispatch_state_known",
    )
    assert_outcome(
        nodes,
        "英雄派遣-领取-循环-耗尽",
        "failed",
        "hero.claim_state_known",
    )
    assert nodes["英雄派遣-关闭-画卷"]["next"] == ["英雄派遣-主页边界-探测"]


def test_collection_task_contract_and_existing_fixture_matrix() -> None:
    assert_task_contract(COLLECTION)
    assert_fixture_matrix(
        COLLECTION.task_id,
        {"entry", "actionable", "completed", "danger"},
    )


def test_collection_flow_guards_single_harvest_and_requires_fresh_empty_state() -> None:
    nodes = load_task_nodes(COLLECTION)
    assert TASK_POLICIES[COLLECTION.task_id].action_caps["claim_all_collection"] == 1
    assert_guarded_actions(
        nodes,
        COLLECTION.task_id,
        [
            "open_painting_scroll",
            "select_yanwu_world",
            "open_collection_deployment",
            "claim_all_collection",
            "close_reward_popup",
            "close_collection_deployment",
            "close_collection_painting",
        ],
    )
    assert_outcome(
        nodes,
        "MJA_COLLECTION_ALREADY_HARVESTED",
        "success",
        "collection.harvested",
    )
    assert_outcome(
        nodes,
        "MJA_COLLECTION_HARVEST_VERIFIED",
        "success",
        "collection.harvested",
    )
    assert_outcome(
        nodes,
        "采集部署-记录-失败",
        "failed",
        "COLLECTION_POSTCONDITION_MISSING",
    )


def test_collection_entry_closes_archived_stale_universal_shop_before_probes() -> None:
    nodes = load_task_nodes(COLLECTION)
    start = nodes[COLLECTION.entry]
    assert start["next"] == [
        "[JumpBack]采集部署-已知-采集-过期-商店-关闭",
        "采集部署-恢复继续-奖励-探测",
        "采集部署-页面-探测",
        "采集部署-主页-探测",
    ]

    recovery = nodes["采集部署-已知-采集-过期-商店-关闭"]
    assert recovery["action"] == "Click"
    assert recovery["max_hit"] == 1
    assert recovery["retry_times"] == 0
    assert recovery["post_delay"] == 750
    assert recovery["recognition"] == {
        "type": "And",
        "param": {
            "all_of": [
                "采集部署-采集-万用-商店-边界",
                "采集部署-采集-万用-商店-关闭",
            ],
            "box_index": 1,
        },
    }
    assert nodes["采集部署-采集-万用-商店-边界"] == {
        "recognition": "OCR",
        "expected": "玉盟商会",
        "roi": [0, 0, 320, 120],
        "action": "DoNothing",
    }
    assert nodes["采集部署-采集-万用-商店-关闭"] == {
        "recognition": "TemplateMatch",
        "template": "daily/BUY_TEA_DAILY/shop_close.png",
        "roi": [1160, 0, 100, 100],
        "threshold": 0.36,
        "action": "DoNothing",
    }


def test_weekly_task_contract_and_existing_fixture_matrix() -> None:
    assert_task_contract(WEEKLY)
    assert_fixture_matrix(
        WEEKLY.task_id,
        {"entry", "actionable", "completed", "danger"},
    )


def test_weekly_flow_partitions_free_paid_and_unknown_price_states() -> None:
    nodes = load_task_nodes(WEEKLY)
    assert TASK_POLICIES[WEEKLY.task_id].eligible_weekdays == frozenset({0})
    assert_guarded_actions(
        nodes,
        WEEKLY.task_id,
        [
            "open_function_panel",
            "open_shop",
            "open_gift_tab",
            "open_weekly_must_buy",
            "claim_weekly_lucky_bag",
            "dismiss_weekly_reward",
            "close_shop",
        ],
    )
    free_claim = nodes["周一免费礼包-免费-领取"]["recognition"]["param"]["all_of"]
    assert "周一免费礼包-商店-每周-幸运-背包-免费" in free_claim
    assert_outcome(nodes, "MJA_WEEKLY_CLAIMED", "already_complete", "weekly_gift.claimed")
    assert_outcome(nodes, "周一免费礼包-领取-成功", "success", "weekly_gift.claimed")
    assert_outcome(
        nodes,
        "MJA_WEEKLY_PAID_ONLY",
        "not_eligible",
        "weekly_gift.no_free_offer",
    )
    assert_outcome(nodes, "MJA_WEEKLY_UNKNOWN_PRICE", "failed", "WEEKLY_PRICE_UNVERIFIED")


def test_daily_reward_task_contract_and_existing_fixture_matrix() -> None:
    assert_task_contract(DAILY_REWARD)
    assert_fixture_matrix(
        DAILY_REWARD.task_id,
        {"entry", "actionable", "completed", "danger"},
    )


def test_daily_reward_scan_prioritizes_claims_and_has_five_scroll_bound() -> None:
    nodes = load_task_nodes(DAILY_REWARD)
    assert nodes["日常任务奖励-奖励-扫描"]["max_hit"] == 5
    assert TASK_POLICIES[DAILY_REWARD.task_id].action_caps["claim_completed_daily_row"] == 50
    assert TASK_POLICIES[DAILY_REWARD.task_id].action_caps["claim_unlocked_activity_chest"] == 10
    assert TASK_POLICIES[DAILY_REWARD.task_id].action_caps["close_reward_popup"] == 60
    assert_guarded_actions(
        nodes,
        DAILY_REWARD.task_id,
        [
            "open_function_panel",
            "open_daily_tasks",
            "claim_completed_daily_row",
            "scroll_daily_reward_rows",
                "close_reward_popup",
                "claim_unlocked_activity_chest",
                "close_daily_tasks",
                "close_function_panel",
            ],
        )
    assert nodes["日常任务奖励-领取-行"]["next"] == [
        "日常任务奖励-奖励-探测",
        "日常任务奖励-奖励-页面-校验",
    ]
    assert nodes["日常任务奖励-关闭-奖励"]["next"] == ["日常任务奖励-奖励-页面-校验"]
    assert_outcome(
        nodes,
        "日常任务奖励-奖励-无",
        "already_complete",
        "daily_reward.no_claimable",
    )
    assert_outcome(
        nodes,
        "日常任务奖励-奖励-完成",
        "success",
        "daily_reward.no_claimable",
    )


def test_battle_pass_task_and_basic_reward_phases_are_bounded_and_safe() -> None:
    assert_task_contract(BATTLE_PASS)
    assert_fixture_matrix(
        BATTLE_PASS.task_id,
        {"entry", "actionable", "completed", "danger"},
    )
    nodes = load_task_nodes(BATTLE_PASS)
    assert nodes["战令奖励-任务-领取-循环"]["max_hit"] == 50
    assert nodes["战令奖励-基础-领取-循环"]["max_hit"] == 50
    assert TASK_POLICIES[BATTLE_PASS.task_id].action_caps["close_reward_popup"] == 50
    assert_guarded_actions(
        nodes,
        BATTLE_PASS.task_id,
        [
            "open_battle_pass",
            "open_battle_pass_tasks",
            "claim_task_reward",
            "close_reward_popup",
            "open_battle_pass_rewards",
            "claim_basic_red_dot_reward",
            "close_battle_pass",
        ],
    )
    assert nodes["战令奖励-任务-领取-循环"]["next"] == [
        "战令奖励-任务-奖励-探测",
        "战令奖励-任务-物品-探测",
        "战令奖励-任务-奖励-校验",
    ]
    assert nodes["战令奖励-基础-领取-循环"]["next"] == [
        "战令奖励-基础-奖励-探测",
        "战令奖励-基础-物品-探测",
        "战令奖励-基础-奖励-校验",
    ]
    assert_outcome(
        nodes,
        "战令奖励-全部已领取",
        "already_complete",
        "battle_pass.no_task_or_basic_claimable",
    )
    assert_outcome(
        nodes,
        "战令奖励-全部已领取-成功",
        "success",
        "battle_pass.no_task_or_basic_claimable",
    )
    assert_outcome(
        nodes,
        "战令奖励-奖励-歧义",
        "failed",
        "BATTLE_PASS_REWARDS_PAGE_AMBIGUOUS",
    )
