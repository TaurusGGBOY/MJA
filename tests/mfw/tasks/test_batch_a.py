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
    assert nodes["MJA_MAIL_REWARD_DAILY_START"]["next"] == [
        "[JumpBack]MJA_KNOWN_CLICK_BLANK_TO_CLOSE",
        "MJA_MAIL_PAGE_PROBE",
        "MJA_MAIL_HOME_PROBE",
        "MJA_MAIL_PANEL_PROBE",
    ]
    assert nodes["MJA_MAIL_REWARD_DAILY_START"]["on_error"] == ["MJA_MAIL_RECORD_FAILURE"]
    assert nodes["MJA_MAIL_PAGE_PROBE"]["next"] == ["MJA_MAIL_CLAIM"]
    assert nodes["MJA_MAIL_PAGE_PROBE"]["on_error"] == ["MJA_MAIL_CLAIM"]
    assert nodes["MJA_MAIL_CLAIM"]["on_error"] == ["MJA_MAIL_EMPTY_PROBE"]
    assert nodes["MJA_MAIL_EMPTY_PROBE"]["next"] == ["MJA_MAIL_ALREADY_COMPLETE"]
    assert nodes["MJA_MAIL_ALREADY_COMPLETE"]["next"] == ["MJA_MAIL_CLOSE"]
    assert nodes["MJA_MAIL_HOME_PROBE"]["recognition"] == {
        "type": "And",
        "param": {"all_of": ["MJA_GAME_HOME_PAGE"], "box_index": 0},
    }
    assert nodes["MJA_MAIL_HOME_PROBE"]["on_error"] == ["[JumpBack]MJA_GAME_START"]
    assert nodes["home.page"]["recognition"] == {
        "type": "And",
        "param": {"all_of": ["MJA_GAME_HOME_PAGE"], "box_index": 0},
    }
    assert nodes["MJA_MAIL_PANEL_PROBE"]["threshold"] == 0.375
    assert nodes["panel.page"]["threshold"] == 0.375
    assert nodes["panel.mail_entry"]["threshold"] == 0.39
    assert nodes["panel.close"]["threshold"] == 0.1
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
    assert nodes["MJA_MAIL_REWARD_PROBE"]["next"] == ["MJA_MAIL_CLAIM_SUCCESS"]
    assert nodes["MJA_MAIL_CLAIM_SUCCESS"]["next"] == ["MJA_MAIL_CLOSE_REWARD"]
    assert nodes["MJA_MAIL_CLOSE_REWARD"]["next"] == ["MJA_MAIL_CLOSE"]
    assert_outcome(nodes, "MJA_MAIL_CLAIM_SUCCESS", "success", "mail.reward_claimed")
    assert_outcome(nodes, "MJA_MAIL_ALREADY_COMPLETE", "already_complete", "mail.empty")
    assert nodes["MJA_MAIL_ALREADY_COMPLETE"]["custom_action_param"][
        "defer_home_boundary"
    ] is True
    assert nodes["MJA_MAIL_CLAIM_SUCCESS"]["custom_action_param"][
        "defer_home_boundary"
    ] is True
    assert nodes["MJA_MAIL_CLOSE_PANEL"]["next"] == ["MJA_HOME_BOUNDARY"]
    assert_outcome(nodes, "MJA_MAIL_RECORD_FAILURE", "failed", "MAIL_POSTCONDITION_MISSING")


def test_shop_task_contract_and_existing_fixture_matrix() -> None:
    assert_task_contract(SHOP)
    assert_fixture_matrix(
        SHOP.task_id,
        {"entry", "actionable", "completed", "danger"},
    )
    nodes = load_task_nodes(SHOP)
    assert nodes["MJA_SHOP_FREE_GIFT_DAILY_START"]["next"] == [
        "MJA_SHOP_DIRECT_STATUS_PROBE",
        "MJA_SHOP_DIRECT_CLAIM_GATE",
        "MJA_SHOP_OPEN_PERIOD",
        "MJA_SHOP_BENEFITS_PAGE_PROBE",
        "MJA_SHOP_PANEL_PROBE",
        "MJA_SHOP_PAGE_PROBE",
        "MJA_SHOP_HOME_PROBE",
    ]
    assert nodes["MJA_SHOP_FREE_GIFT_DAILY_START"]["on_error"] == [
        "MJA_SHOP_RUNTIME_RECOVERY_ATTEMPT_1",
        "MJA_SHOP_RUNTIME_RECOVERY_ATTEMPT_2",
        "MJA_SHOP_RUNTIME_RECOVERY_EXHAUSTED",
    ]
    assert nodes["MJA_SHOP_STATUS_PROBE"]["recognition"] == "OCR"
    assert nodes["MJA_SHOP_STATUS_PROBE"]["expected"] == [
        "已领取",
        "今日已领取",
        "领取完毕",
    ]
    assert nodes["MJA_SHOP_STATUS_PROBE"]["on_error"] == [
        "MJA_SHOP_CLAIM_GATE",
        "MJA_SHOP_RUNTIME_RECOVERY_ATTEMPT_1",
        "MJA_SHOP_RUNTIME_RECOVERY_ATTEMPT_2",
        "MJA_SHOP_RUNTIME_RECOVERY_EXHAUSTED",
    ]
    assert nodes["MJA_SHOP_BENEFITS_PAGE_PROBE"]["next"] == [
        "MJA_SHOP_STATUS_PROBE",
        "MJA_SHOP_CLAIM_GATE",
    ]
    assert "threshold" not in nodes["MJA_SHOP_HOME_PROBE"]
    assert nodes["MJA_SHOP_OPEN_PERIOD"]["next"] == ["MJA_SHOP_BENEFITS_PAGE_PROBE"]
    assert nodes["MJA_SHOP_OPEN_PERIOD"]["on_error"] == [
        "MJA_SHOP_RUNTIME_RECOVERY_ATTEMPT_1",
        "MJA_SHOP_RUNTIME_RECOVERY_ATTEMPT_2",
        "MJA_SHOP_RUNTIME_RECOVERY_EXHAUSTED",
    ]
    assert nodes["shop.close"] == {
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
        "MJA_SHOP_RECORD_ALREADY_COMPLETE",
        "already_complete",
        "shop.daily_free_gift_claimed",
    )
    assert_outcome(
        nodes,
        "MJA_SHOP_RECORD_SUCCESS",
        "success",
        "shop.daily_free_gift_claimed",
    )
    assert_outcome(
        nodes,
        "MJA_SHOP_RECORD_FAILURE",
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
    assert nodes[APPRAISAL.entry]["next"][0] == "[JumpBack]MJA_KNOWN_PAINTING_CLOSE"
    assert nodes[APPRAISAL.entry]["next"][1] == "[JumpBack]MJA_APPRAISAL_EXTRA_POPUP_CLOSE"
    assert nodes["appraisal.result_popup"] == {
        "recognition": "OCR",
        "expected": ["^鉴宝一次$", "^鉴宝十次$"],
        "roi": [350, 560, 600, 100],
        "action": "DoNothing",
    }
    assert nodes["MJA_APPRAISAL_CLOSE_REWARD"]["next"] == [
        "[JumpBack]MJA_APPRAISAL_EXTRA_POPUP_CLOSE",
        "MJA_APPRAISAL_VERIFY",
        "MJA_APPRAISAL_HOME_AFTER_REWARD",
    ]
    assert nodes["MJA_APPRAISAL_EXTRA_POPUP_CLOSE"]["custom_action_param"][
        "action_id"
    ] == "close_extra_reward_popup"
    assert nodes["appraisal.extra_popup.page"]["expected"] == "^秘宝收集$"
    assert nodes["appraisal.extra_popup.close"]["template"] == (
        "daily/BUY_TEA_DAILY/shop_close.png"
    )
    assert nodes["appraisal.free_once"] == {
        "recognition": "OCR",
        "expected": "^免费鉴宝$",
        "roi": [470, 590, 160, 60],
        "action": "DoNothing",
    }
    assert nodes["appraisal.page.close"] == {
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
        "MJA_APPRAISAL_SUCCESS",
        "success",
        "appraisal.used",
    )
    assert_outcome(
        nodes,
        "MJA_APPRAISAL_RECORD_FAILURE",
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
    assert_reachable(nodes, TRIAL.entry, "MJA_COMMON_STOP")
    assert_reachable(nodes, TRIAL.entry, "MJA_COMMON_ABORT")
    assert_fixture_matrix(
        TRIAL.task_id,
        {"entry", "actionable", "completed", "danger"},
    )


def test_trial_flow_guards_every_side_effect_and_has_truthful_outcomes() -> None:
    nodes = load_task_nodes(TRIAL)
    assert nodes[TRIAL.entry]["next"][0] == "[JumpBack]MJA_KNOWN_PAINTING_CLOSE"
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
        "MJA_TRIAL_SUCCESS",
        "success",
        "trial.free_used",
    )
    assert_outcome(
        nodes,
        "MJA_TRIAL_RECORD_FAILURE",
        "failed",
        "TRIAL_POSTCONDITION_MISSING",
    )


def test_trial_r19_home_entry_uses_a_narrow_calibrated_same_frame_target() -> None:
    nodes = load_task_nodes(TRIAL)

    start = nodes["MJA_TRIAL_SWORD_DAILY_START"]
    assert start["next"] == [
        "[JumpBack]MJA_KNOWN_PAINTING_CLOSE",
        "[JumpBack]MJA_KNOWN_TEA_DETAIL_CLOSE",
        "[JumpBack]MJA_KNOWN_TEA_SHOP_CLOSE",
        "MJA_TRIAL_RESUME_FREE_PROBE",
        "MJA_TRIAL_RESUME_RESULT_PROBE",
        "MJA_TRIAL_PAGE_PROBE",
        "MJA_TRIAL_OPEN_TRIAL",
    ]
    assert start["on_error"] == ["MJA_TRIAL_RECORD_FAILURE"]
    assert start["retry_times"] == 0
    assert "MJA_TRIAL_HOME_PROBE" not in nodes

    target = nodes["trial.open"]
    assert target == {
        "recognition": "ColorMatch",
        "method": 4,
        "lower": [100, 100, 90],
        "upper": [255, 255, 255],
        "roi": [980, 590, 85, 85],
        "connected": True,
        "count": 1200,
        "order_by": "Area",
        "index": 0,
        "action": "DoNothing",
    }

    # Offline calibration from the fresh r19 on-error frame at 17:47:11.552.
    # The styled glyph never produced the expected OCR text.  In the exact
    # 1280x720 screenshot its stable white button body is this connected box.
    frame_width, frame_height = 1280, 720
    archived_component_box = [987, 599, 52, 66]
    archived_component_pixels = 1775
    x, y, width, height = target["roi"]
    component_x, component_y, component_width, component_height = archived_component_box
    assert x <= component_x
    assert y <= component_y
    assert x + width >= component_x + component_width
    assert y + height >= component_y + component_height
    assert x + width <= frame_width
    assert y + height <= frame_height
    assert target["count"] < archived_component_pixels

    # The ColorMatch result box, not the ROI or a bare coordinate, supplies
    # the GuardedInput target.  Its center remains inside the visible button.
    click_x = component_x + component_width // 2
    click_y = component_y + component_height // 2
    assert (click_x, click_y) == (1013, 632)
    assert x <= click_x < x + width
    assert y <= click_y < y + height

    old_ocr_roi = [850, 450, 430, 270]
    assert width * height * 10 < old_ocr_roi[2] * old_ocr_roi[3]

    open_trial = nodes["MJA_TRIAL_OPEN_TRIAL"]
    assert open_trial["recognition"]["param"] == {
        "all_of": ["home.page", "trial.open"],
        "box_index": 1,
    }
    assert open_trial["custom_action_param"]["evidence"] == {
        "page_index": 0,
        "target_index": 1,
        "page_name": "home.page",
        "target_name": "trial.open",
    }
    assert open_trial["retry_times"] == 0
    assert TASK_POLICIES[TRIAL.task_id].action_caps["open_trial_sword"] == 1


def test_trial_failure_paths_record_before_native_failure_and_never_stop_as_success() -> None:
    nodes = load_task_nodes(TRIAL)

    failure = nodes["MJA_TRIAL_RECORD_FAILURE"]
    assert failure["custom_action_param"] == {
        "task_id": TRIAL.task_id,
        "status": "failed",
        "postcondition": "TRIAL_POSTCONDITION_MISSING",
        "error_code": "TRIAL_POSTCONDITION_MISSING",
        "native_fail_after_record": True,
    }
    assert failure["Abort"] is True
    assert failure["next"] == ["MJA_COMMON_ABORT"]

    guarded_nodes = {
        name: node
        for name, node in nodes.items()
        if node.get("custom_action") == "GuardedInput"
        and node.get("custom_action_param", {}).get("task_id") == TRIAL.task_id
    }
    assert guarded_nodes
    for node in guarded_nodes.values():
        assert node["on_error"] == ["MJA_TRIAL_RECORD_FAILURE"]
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
        if name.startswith("MJA_TRIAL_")
        and "MJA_COMMON_STOP" in node.get("next", [])
    }
    assert terminal_predecessors == {
        "MJA_TRIAL_ALREADY_COMPLETE",
        "MJA_TRIAL_SUCCESS",
    }
    assert_reachable(
        nodes,
        "MJA_TRIAL_SWORD_DAILY_START",
        "MJA_TRIAL_RECORD_FAILURE",
    )


def test_trial_records_outcome_only_after_used_state_close_and_home_boundary() -> None:
    nodes = load_task_nodes(TRIAL)

    assert nodes["MJA_TRIAL_FREE_VERIFY"]["recognition"]["param"] == {
        "all_of": ["trial.page", "trial.free_used"],
        "box_index": 1,
    }
    assert nodes["MJA_TRIAL_FREE_VERIFY"]["next"] == [
        "MJA_TRIAL_CLOSE_SUCCESS"
    ]
    assert nodes["MJA_TRIAL_POST_REWARD_FREE_STATUS"]["next"] == [
        "MJA_TRIAL_CLOSE_SUCCESS"
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
        "page_name": "trial.page",
        "target_name": "trial.close",
    }
    for close_name, home_name, outcome_name in (
        (
            "MJA_TRIAL_CLOSE_SUCCESS",
            "MJA_TRIAL_SUCCESS_HOME_PROBE",
            "MJA_TRIAL_SUCCESS",
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
        assert close["on_error"] == ["MJA_TRIAL_RECORD_FAILURE"]

        home = nodes[home_name]
        assert home["recognition"]["param"] == {"all_of": ["home.page"]}
        assert home["action"] == "DoNothing"
        assert home["next"] == [outcome_name]
        assert home["on_error"] == ["MJA_TRIAL_RECORD_FAILURE"]

    assert_reachable(nodes, "MJA_TRIAL_FREE_VERIFY", "MJA_TRIAL_SUCCESS")
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
        "MJA_HERO_GAME_START_RECOVERY",
        "MJA_HERO_RECORD_FAILURE",
    ]
    assert nodes["MJA_HERO_GAME_START_RECOVERY"]["max_hit"] == 1
    assert nodes["MJA_HERO_GAME_START_RECOVERY"]["next"][-1] == (
        "[JumpBack]MJA_GAME_START"
    )
    assert nodes["MJA_DISPATCH_CLAIM_LOOP"]["max_hit"] == 6
    assert nodes["MJA_DISPATCH_FILL_LOOP"]["max_hit"] == 6
    assert_terminal_after_loop(
        nodes,
        "MJA_DISPATCH_CLAIM_LOOP",
        6,
        "HERO_CLAIM_LOOP_EXHAUSTED",
    )
    assert_terminal_after_loop(
        nodes,
        "MJA_DISPATCH_FILL_LOOP",
        6,
        "HERO_DISPATCH_LOOP_EXHAUSTED",
    )
    assert nodes["MJA_HERO_INITIAL_CLAIM"]["custom_action_param"]["action_id"] == (
        "select_first_visible_dispatch"
    )
    assert nodes["MJA_HERO_INITIAL_CLAIM_BUTTON"]["next"] == ["MJA_HERO_INITIAL_CLAIM_ACTION"]
    assert "完成派遣" in nodes["hero.first_task_claimable"]["expected"]
    assert nodes["hero.all_completed"]["expected"] == [
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
        "MJA_HERO_ALREADY_ALL",
        "already_complete",
        "hero.all_completed",
    )
    assert_outcome(
        nodes,
        "MJA_HERO_ALREADY_PROGRESS",
        "already_complete",
        "hero.first_task_in_progress",
    )
    assert_outcome(
        nodes,
        "MJA_HERO_SUCCESS_ALL",
        "success",
        "hero.all_completed",
    )
    assert_outcome(
        nodes,
        "MJA_HERO_SUCCESS_PROGRESS",
        "success",
        "hero.first_task_in_progress",
    )
    assert_outcome(
        nodes,
        "MJA_HERO_RECORD_FAILURE",
        "failed",
        "HERO_POSTCONDITION_MISSING",
    )
    assert_outcome(
        nodes,
        "MJA_DISPATCH_FILL_LOOP_EXHAUSTED",
        "failed",
        "hero.dispatch_state_known",
    )
    assert_outcome(
        nodes,
        "MJA_DISPATCH_CLAIM_LOOP_EXHAUSTED",
        "failed",
        "hero.claim_state_known",
    )
    assert nodes["MJA_HERO_CLOSE_PAINTING"]["next"] == ["MJA_HERO_HOME_BOUNDARY_PROBE"]


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
        "MJA_COLLECTION_RECORD_FAILURE",
        "failed",
        "COLLECTION_POSTCONDITION_MISSING",
    )


def test_collection_entry_closes_archived_stale_universal_shop_before_probes() -> None:
    nodes = load_task_nodes(COLLECTION)
    start = nodes[COLLECTION.entry]
    assert start["next"] == [
        "[JumpBack]MJA_KNOWN_COLLECTION_STALE_SHOP_CLOSE",
        "MJA_COLLECTION_RESUME_REWARD_PROBE",
        "MJA_COLLECTION_PAGE_PROBE",
        "MJA_COLLECTION_HOME_PROBE",
    ]

    recovery = nodes["MJA_KNOWN_COLLECTION_STALE_SHOP_CLOSE"]
    assert recovery["action"] == "Click"
    assert recovery["max_hit"] == 1
    assert recovery["retry_times"] == 0
    assert recovery["post_delay"] == 750
    assert recovery["recognition"] == {
        "type": "And",
        "param": {
            "all_of": [
                "collection.universal_shop.boundary",
                "collection.universal_shop.close",
            ],
            "box_index": 1,
        },
    }
    assert nodes["collection.universal_shop.boundary"] == {
        "recognition": "OCR",
        "expected": "玉盟商会",
        "roi": [0, 0, 320, 120],
        "action": "DoNothing",
    }
    assert nodes["collection.universal_shop.close"] == {
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
    free_claim = nodes["MJA_WEEKLY_FREE_CLAIM"]["recognition"]["param"]["all_of"]
    assert "shop.weekly_lucky_bag_free" in free_claim
    assert_outcome(nodes, "MJA_WEEKLY_CLAIMED", "already_complete", "weekly_gift.claimed")
    assert_outcome(nodes, "MJA_WEEKLY_CLAIM_SUCCESS", "success", "weekly_gift.claimed")
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
    assert nodes["MJA_DAILY_REWARD_SCAN"]["max_hit"] == 5
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
    assert nodes["MJA_DAILY_CLAIM_ROW"]["next"] == [
        "MJA_DAILY_REWARD_PROBE",
        "MJA_DAILY_REWARD_PAGE_VERIFY",
    ]
    assert nodes["MJA_DAILY_CLOSE_REWARD"]["next"] == ["MJA_DAILY_REWARD_PAGE_VERIFY"]
    assert_outcome(
        nodes,
        "MJA_DAILY_REWARD_NONE",
        "already_complete",
        "daily_reward.no_claimable",
    )
    assert_outcome(
        nodes,
        "MJA_DAILY_REWARD_DONE",
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
    assert nodes["MJA_BP_TASK_CLAIM_LOOP"]["max_hit"] == 50
    assert nodes["MJA_BP_BASIC_CLAIM_LOOP"]["max_hit"] == 50
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
    assert nodes["MJA_BP_TASK_CLAIM_LOOP"]["next"] == [
        "MJA_BP_TASK_REWARD_PROBE",
        "MJA_BP_TASK_ITEM_PROBE",
        "MJA_BP_TASK_REWARD_VERIFY",
    ]
    assert nodes["MJA_BP_BASIC_CLAIM_LOOP"]["next"] == [
        "MJA_BP_BASIC_REWARD_PROBE",
        "MJA_BP_BASIC_ITEM_PROBE",
        "MJA_BP_BASIC_REWARD_VERIFY",
    ]
    assert_outcome(
        nodes,
        "MJA_BP_ALL_CLAIMED",
        "already_complete",
        "battle_pass.no_task_or_basic_claimable",
    )
    assert_outcome(
        nodes,
        "MJA_BP_ALL_CLAIMED_SUCCESS",
        "success",
        "battle_pass.no_task_or_basic_claimable",
    )
    assert_outcome(
        nodes,
        "MJA_BP_REWARDS_AMBIGUOUS",
        "failed",
        "BATTLE_PASS_REWARDS_PAGE_AMBIGUOUS",
    )
