from __future__ import annotations

import json
import re
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def test_android_resource_has_verified_live_capture_contract() -> None:
    calibration = json.loads(
        (ROOT / "assets/resource_android/calibration.json").read_text(encoding="utf-8")
    )
    contract = calibration["template_contract"]
    assert contract["profile"] == "android_live_capture"
    assert contract["capture_size"] == [1280, 720]
    assert contract["status"] == "live_capture_verified"
    assert contract["capture_method"] == "adb_screencap"
    assert contract["profiles"] == ["home", "panel", "mail"]
    for template in (
        "home/home_marker.png",
        "home/panel_open.png",
        "panel/panel_marker.png",
        "panel/mail_entry.png",
        "panel/panel_close.png",
        "mail/mail_marker.png",
        "mail/mail_close.png",
    ):
        assert (ROOT / "assets/resource_android/image" / template).is_file()


def test_android_pipeline_has_only_safe_custom_clicks() -> None:
    pipeline = json.loads(
        (ROOT / "assets/resource_android/pipeline/mail_smoke_test.json").read_text(
            encoding="utf-8"
        )
    )
    serialized = json.dumps(pipeline, ensure_ascii=False).lower()
    assert all(term not in serialized for term in ("领取", "claim", "startapp", '"click"'))
    assert {
        node["custom_action"]
        for node in pipeline.values()
        if node.get("action") == "Custom"
    } == {"AndroidForegroundClick"}


def test_android_start_game_recognizes_both_live_title_labels() -> None:
    pipeline = json.loads(
        (ROOT / "assets/resource_android/pipeline/daily_common.json").read_text(
            encoding="utf-8"
        )
    )
    assert pipeline["reset.start_game"]["expected"] == [
        "点击开始游戏",
        "点击开始游戏!",
        "点击开始游戏！",
        "进入游戏",
    ]
    assert pipeline["reset.start_game_welcome"]["expected"] == "欢迎进入游戏"
    assert pipeline["reset.start_game_welcome"]["roi"] == [0, 0, 1280, 260]
    start_button = pipeline["reset.start_game_button"]
    assert start_button["recognition"] == "TemplateMatch"
    assert start_button["template"] == "home/start_game_button.png"
    assert start_button["roi"] == [560, 638, 180, 45]
    assert start_button["threshold"] == 0.275
    with Image.open(ROOT / "assets/resource_android/image/home/start_game_button.png") as image:
        assert image.size == (180, 45)
    assert pipeline["reset.loading"]["expected"] == ["穿梭入世", "加载中"]
    assert pipeline["reset.loading"]["roi"] == [900, 600, 380, 120]
    assert pipeline["reset.resource_update_prompt"]["recognition"] == "OCR"
    assert "热更" in pipeline["reset.resource_update_prompt"]["expected"]
    assert pipeline["reset.resource_update_allow"]["expected"] == "允许下载"
    assert pipeline["reset.resource_update_progress"]["expected"] == ["下载中", "共计"]
    assert pipeline["reset.announcement_page"]["expected"] == ["公告", "万象藏宝阁"]
    assert pipeline["reset.version_announcement_page"]["expected"] == [
        "版本更新",
        "公告说明",
        "更新详情",
    ]
    assert pipeline["reset.guild_unlock_dialog"]["expected"] == [
        "帮会已解锁",
        "共筑霸业",
        "帮会",
    ]
    assert pipeline["reset.dialog_skip"]["expected"] == "跳过"
    assert pipeline["reset.monthly_signin_page"]["expected"] == "已签到"
    assert pipeline["reset.monthly_signin_page"]["roi"] == [240, 100, 880, 500]


def test_android_resource_provides_the_jumpback_game_start_anchor() -> None:
    pipeline = json.loads(
        (
            ROOT
            / "assets/resource_android/pipeline/startup/game_start.json"
        ).read_text(encoding="utf-8")
    )
    assert pipeline["启动-游戏入口"]["next"] == ["启动-游戏启动"]
    assert pipeline["启动-游戏启动"]["next"] == ["启动-游戏就绪"]
    assert pipeline["启动-游戏就绪"]["custom_action"] == "RuntimeHealth"


def test_android_mail_claim_has_a_safe_reward_popup_close_path() -> None:
    pipeline = json.loads(
        (
            ROOT
            / "assets/resource_android/pipeline/daily/mail_reward_daily.json"
        ).read_text(encoding="utf-8")
    )
    assert pipeline["邮件奖励-邮件-领取-全部"]["recognition"] == "OCR"
    assert pipeline["邮件奖励-邮件-领取-全部"]["expected"] == "全部领取"
    assert pipeline["邮件奖励-邮件-领取-全部"]["roi"] == [205, 525, 150, 65]
    assert pipeline["邮件奖励-邮件-奖励-弹窗"]["expected"] == ["恭喜获得", "点击空白处关闭"]
    assert pipeline["邮件奖励-邮件-奖励-弹窗-关闭"]["expected"] == "点击空白处关闭"


def test_android_shop_page_marker_is_scoped_to_shop_title() -> None:
    pipeline = json.loads(
        (
            ROOT
            / "assets/resource_android/pipeline/daily/shop_free_gift_daily.json"
        ).read_text(encoding="utf-8")
    )
    assert pipeline["商店免费礼包-商店-页面"]["expected"] == "商城"
    assert pipeline["商店免费礼包-商店-页面"]["roi"] == [0, 0, 300, 100]


def test_android_weekly_paid_marker_uses_a_stable_live_title() -> None:
    pipeline = json.loads(
        (ROOT / "assets/resource_android/pipeline/daily_ocr.json").read_text(
            encoding="utf-8"
        )
    )
    paid = pipeline["周一免费礼包-商店-每周-付费"]
    assert paid["recognition"] == "OCR"
    assert paid["expected"] == "每周特价"
    assert paid["roi"] == [300, 120, 900, 480]


def test_android_daily_reward_uses_live_popup_ocr_without_missing_template() -> None:
    pipeline = json.loads(
        (
            ROOT
            / "assets/resource_android/pipeline/daily/daily_task_reward_claim_daily.json"
        ).read_text(encoding="utf-8")
    )
    popup = pipeline["日常任务奖励-日常-奖励-弹窗"]
    assert popup["recognition"] == "OCR"
    assert popup["expected"] == ["恭喜获得", "点击(?:空白处|任意位置)关闭"]
    assert "template" not in popup


def test_android_martial_success_card_search_covers_all_visible_slots() -> None:
    pipeline = json.loads(
        (
            ROOT
            / "assets/resource_android/pipeline/daily/martial_study_breakthrough_daily.json"
        ).read_text(encoding="utf-8")
    )
    success = pipeline["martial_success_card"]
    assert success["recognition"] == "TemplateMatch"
    assert success["template"] == (
        "daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/success.png"
    )
    # The live account can expose 成功 in the second or third card slot.
    # Search the whole card row instead of hard-coding the rightmost slot.
    assert success["roi"] == [760, 350, 500, 330]


def test_android_verification_ocr_does_not_match_daily_login_row() -> None:
    pipeline = json.loads(
        (ROOT / "assets/resource_android/pipeline/daily_common.json").read_text(
            encoding="utf-8"
        )
    )
    expected = pipeline["破阵武学-安全-校验"]["expected"]
    assert expected == ["验证码", "安全验证", "滑动验证"]
    assert "登录" not in expected
    assert "支付" not in expected


def test_android_ocr_accepts_the_live_yanwu_currency_label() -> None:
    pipeline = json.loads(
        (ROOT / "assets/resource_android/pipeline/daily_ocr.json").read_text(
            encoding="utf-8"
        )
    )
    assert pipeline["yanwu_currency_purchase"]["expected"] == ["长定钱", "长定宝钱"]


def test_android_ocr_exposes_universal_shop_boundary_title() -> None:
    pipeline = json.loads(
        (ROOT / "assets/resource_android/pipeline/daily_ocr.json").read_text(
            encoding="utf-8"
        )
    )
    marker = pipeline["universal_shop_boundary"]
    assert marker["recognition"] == "OCR"
    assert marker["expected"] == "玉盟商会"
    assert marker["roi"] == [0, 0, 320, 120]


def test_android_home_quest_marker_accepts_updated_live_task_panel() -> None:
    pipeline = json.loads(
        (ROOT / "assets/resource_android/pipeline/daily_ocr.json").read_text(
            encoding="utf-8"
        )
    )

    marker = pipeline["home.quest_text"]
    assert marker["expected"] == ["云州初局", "任务", "侠影"]
    assert marker["roi"] == [0, 210, 350, 100]


def test_regional_currency_sold_out_requires_exact_zero_remaining() -> None:
    pipeline = json.loads(
        (
            ROOT
            / "assets/resource_android/pipeline/daily/spend_condensate_daily.json"
        ).read_text(encoding="utf-8")
    )

    assert pipeline["yanwu_currency_sold_out"]["expected"] == "^0/12500$"
    assert pipeline["yunzhou_currency_sold_out"]["expected"] == "^0/12500$"


def test_yunzhou_page_markers_do_not_match_home_task_text() -> None:
    pipeline = json.loads(
        (
            ROOT
            / "assets/resource_android/pipeline/daily/spend_condensate_daily.json"
        ).read_text(encoding="utf-8")
    )

    for name in ("yunzhou_world_tab", "yunzhou_currency_shop"):
        pattern = pipeline[name]["expected"]
        assert re.fullmatch(pattern, "云州")
        assert re.fullmatch(pattern, "·云州")
        assert not re.fullmatch(pattern, "云州初局")

    page = pipeline["yunzhou_world_page"]
    assert page["recognition"] == "TemplateMatch"
    assert page["template"] == (
        "daily/SPEND_CONDENSATE_DAILY/yunzhou_world_page.png"
    )
    assert page["roi"] == [60, 200, 300, 130]
    assert (
        ROOT
        / "assets/resource_android/image"
        / page["template"]
    ).is_file()


def test_android_dungeon_ocr_covers_full_bag_stop_and_cleanup() -> None:
    pipeline = json.loads(
        (ROOT / "assets/resource_android/pipeline/daily_ocr.json").read_text(
            encoding="utf-8"
        )
    )
    full_bag = pipeline["dungeon_bag_full"]
    assert full_bag["recognition"] == "OCR"
    assert "背包已满" in full_bag["expected"]
    assert full_bag["roi"] == [300, 0, 700, 90]
    assert pipeline["sweep_result_close"]["expected"] == "点击空白处关闭"
    assert pipeline["dungeon_close"]["roi"] == [1160, 0, 100, 100]


def test_android_ring_ticket_ocr_accepts_the_live_counter_capsule() -> None:
    pipeline = json.loads(
        (ROOT / "assets/resource_android/pipeline/daily_ocr.json").read_text(
            encoding="utf-8"
        )
    )
    recognizer = pipeline["擂台券"]
    assert recognizer["roi"] == [0, 0, 1280, 720]
    expected = recognizer["expected"]
    assert "擂台券" in expected
    assert any(re.search(pattern, "12/12") for pattern in expected)

    assert pipeline["ring_daily_done"]["expected"] == "已完成"
    assert pipeline["ring_challenge_target.done"]["expected"] == "挑战完成"
    assert pipeline["ring_challenge_target.done"]["roi"] == [150, 100, 980, 520]
    ring = json.loads(
        (
            ROOT
            / "assets/resource_android/pipeline/daily/ring_challenge_daily.json"
        ).read_text(encoding="utf-8")
    )
    assert "大师赛" in ring["ring_master_mode"]["expected"]
    assert "论剑阵容模式" not in ring["ring_master_mode"]["expected"]
    assert "大师赛模式" in ring["ring_master_mode"]["expected"]
    assert any(
        re.search(pattern, "剩余挑战次数 11/12")
        for pattern in ring["ring_attempts"]["expected"]
    )
    assert any(
        re.search(pattern, "剩余挑战次数 0/12")
        for pattern in ring["ring_attempts_exhausted"]["expected"]
    )
    assert ring["ring_page"]["expected"] == ["擂台", "论剑"]
    assert ring["ring_score_label"]["roi"] == [820, 180, 440, 180]
    assert ring["ring_score_value"]["roi"] == [820, 180, 440, 180]
    assert ring["ring_not_open"]["roi"] == [740, 580, 540, 100]
    assert "练习" in ring["ring_start"]["expected"]
    assert ring["ring_fight_target"]["roi"] == [0, 100, 1280, 600]
    assert ring["ring_battle_prepare_page"]["expected"] == "战前准备"
    assert "准备就绪" in ring["ring_ready"]["expected"]
    assert "正在进入战场" in ring["ring_battle_loading"]["expected"]
    assert "正在进入战斗" in ring["ring_battle_loading"]["expected"]
    assert "获得" not in ring["ring_battle_result"]["expected"]
    assert ring["ring_sweep_confirm"]["expected"] == "确认"


def test_android_study_material_ocr_accepts_the_live_counter_capsule() -> None:
    pipeline = json.loads(
        (ROOT / "assets/resource_android/pipeline/daily_ocr.json").read_text(
            encoding="utf-8"
        )
    )
    recognizer = pipeline["研习材料"]
    assert recognizer["roi"] == [1000, 0, 190, 100]
    expected = recognizer["expected"]
    assert "研习材料" in expected
    assert any(re.search(pattern, "813") for pattern in expected)


def test_android_food_target_uses_the_verified_third_row_fourth_column_template() -> None:
    daily_ocr = json.loads(
        (ROOT / "assets/resource_android/pipeline/daily_ocr.json").read_text(encoding="utf-8")
    )
    food_pipeline = json.loads(
        (
            ROOT
            / "assets/resource_android/pipeline/daily/eat_stamina_food_daily.json"
        ).read_text(encoding="utf-8")
    )

    expected_template = "daily/EAT_STAMINA_FOOD_DAILY/longjing_shrimp.png"
    for recognizer in (daily_ocr["龙井虾仁"], food_pipeline["food_candidate"]):
        assert recognizer["recognition"] == "TemplateMatch"
        assert recognizer["template"] == expected_template
        assert recognizer["roi"] == [500, 370, 160, 170]
    assert (
        ROOT
        / "assets/resource_android/image/daily/EAT_STAMINA_FOOD_DAILY/longjing_shrimp.png"
    ).is_file()

    food_use = food_pipeline["food_use_result"]
    assert food_use["recognition"] == "OCR"
    assert "消耗品" in food_use["expected"]
    assert "正在恢复体力" in food_use["expected"]
    assert "当前已存在检定类食物的增益" in food_use["expected"]
    assert "吃得太撑" in food_use["expected"]
    prompt = food_pipeline["food_buff_replace_prompt"]
    assert prompt["recognition"] == "OCR"
    assert prompt["expected"] == [
        "当前已存在检定类食物",
        "使用道具将替换此效果",
        "是否继续",
    ]
    assert prompt["roi"] == [380, 270, 520, 150]
    prompt_template = food_pipeline["food_buff_replace_prompt_template"]
    assert prompt_template["recognition"] == "TemplateMatch"
    assert prompt_template["template"] == (
        "daily/EAT_STAMINA_FOOD_DAILY/food_buff_replace_prompt.png"
    )
    assert prompt_template["roi"] == [250, 130, 800, 500]
    confirm_template = food_pipeline["food_buff_replace_confirm_template"]
    assert confirm_template["recognition"] == "TemplateMatch"
    assert confirm_template["template"] == (
        "daily/EAT_STAMINA_FOOD_DAILY/food_buff_replace_confirm.png"
    )
    assert confirm_template["roi"] == [780, 450, 250, 100]
    assert (
        ROOT / "assets/resource_android/image/daily/EAT_STAMINA_FOOD_DAILY/"
        "food_buff_replace_prompt.png"
    ).is_file()
    assert (
        ROOT / "assets/resource_android/image/daily/EAT_STAMINA_FOOD_DAILY/"
        "food_buff_replace_confirm.png"
    ).is_file()
    overfull = food_pipeline["food_overfull"]
    assert overfull["recognition"] == "OCR"
    assert "吃得太撑" in overfull["expected"]
    assert overfull["roi"] == [300, 0, 700, 80]


def test_hero_dispatch_distinguishes_duration_from_live_in_progress_status() -> None:
    pipeline = json.loads(
        (
            ROOT
            / "assets/resource_android/pipeline/daily/hero_dispatch_daily.json"
        ).read_text(encoding="utf-8")
    )

    assert pipeline["英雄派遣-英雄-首个-任务-可领取"]["expected"] == [
        "完成派遣",
        "可领取",
        "领取",
    ]
    assert pipeline["英雄派遣-英雄-首个-任务-可派遣"]["expected"] == [
        "耗时",
        "派遣(?!中)",
    ]
    assert pipeline["英雄派遣-英雄-首个-任务-可派遣"]["roi"] == [20, 130, 300, 130]
    assert pipeline["英雄派遣-英雄-首个-任务-中-进度"]["expected"] == [
        "正在派遣中",
        "派遣中",
        r"剩余\s*\d{1,2}:\d{2}:\d{2}",
        r"^\d{1,2}:\d{2}:\d{2}$",
    ]
    assert pipeline["英雄派遣-英雄-首个-任务-中-进度"]["roi"] == [20, 130, 300, 130]
    assert pipeline["英雄派遣-英雄-全部-已完成"]["expected"] == [
        r"任务\s*[:：]?\s*9\s*/\s*9",
        r"已完成\s*[:：]?\s*9",
    ]
    assert pipeline["英雄派遣-英雄-全部-已完成"]["roi"] == [0, 80, 360, 70]
    assert pipeline["英雄派遣-英雄-派遣-关闭"]["template"] == (
        "daily/HERO_DISPATCH_DAILY/dispatch_close.png"
    )
    assert pipeline["英雄派遣-英雄-画卷-关闭"]["template"] == (
        "daily/HERO_DISPATCH_DAILY/painting_close.png"
    )
    assert pipeline["英雄派遣-英雄-派遣-关闭"]["green_mask"] is True
    assert pipeline["英雄派遣-英雄-画卷-关闭"]["green_mask"] is True
    assert pipeline["英雄派遣-英雄-派遣-关闭"]["roi"] == [1175, 5, 75, 75]
    assert pipeline["英雄派遣-英雄-画卷-关闭"]["roi"] == [1175, 5, 75, 75]


def test_android_dungeon_panel_marker_is_not_the_detail_page_sweep_button() -> None:
    android = json.loads(
        (ROOT / "assets/resource_android/pipeline/daily_ocr.json").read_text(
            encoding="utf-8"
        )
    )
    base = json.loads(
        (
            ROOT
            / "assets/resource/base/pipeline/daily/dungeon_sweep_daily.json"
        ).read_text(encoding="utf-8")
    )

    assert android["sweep_panel_page"]["recognition"] == {
        "type": "And",
        "param": {
            "all_of": ["sweep_panel_button", "sweep_panel_yanwangling_card"]
        },
    }
    assert base["副本扫荡-副本-扫荡-面板"]["recognition"] == {
        "type": "And",
        "param": {
            "all_of": [
                "副本扫荡-副本-扫荡-按钮",
                "dungeon.sweep.yanwangling.card",
            ]
        },
    }

    expected_button_text = ["开始扫荡", "开始扫"]
    assert android["sweep_panel_button"]["expected"] == expected_button_text
    assert android["start_sweep"]["expected"] == expected_button_text
    assert base["副本扫荡-副本-扫荡-按钮"]["expected"] == expected_button_text
    assert base["副本扫荡-副本-开始"]["expected"] == expected_button_text
    assert "开始" not in expected_button_text

    expected_card = ["燕王秘陵", "燕王"]
    card_roi = [880, 240, 400, 100]
    assert android["sweep_panel_yanwangling_card"]["expected"] == expected_card
    assert android["sweep_panel_yanwangling_card"]["roi"] == card_roi
    assert base["dungeon.sweep.yanwangling.card"]["expected"] == expected_card
    assert base["dungeon.sweep.yanwangling.card"]["roi"] == card_roi

    no_ticket = android["dungeon_no_sweep_ticket"]
    assert no_ticket["expected"] == r"0\s*/\s*10"
    assert no_ticket["roi"] == [1030, 0, 160, 90]


def test_android_jianlin_recognition_is_scoped_to_the_correct_controls() -> None:
    daily_ocr = json.loads(
        (ROOT / "assets/resource_android/pipeline/daily_ocr.json").read_text(encoding="utf-8")
    )
    jianlin = json.loads(
        (
            ROOT
            / (
                "assets/resource_android/pipeline/daily/"
                "jianlin_resource_condensate_stamina_daily.json"
            )
        ).read_text(encoding="utf-8")
    )

    assert daily_ocr["jianlin_daily_row"]["expected"] == (
        r"^战胜一次剑林的首领[。.]?$"
    )
    assert daily_ocr["jianlin_daily_row"]["roi"] == [200, 170, 650, 550]
    entry = daily_ocr["jianlin_entry"]
    assert entry["recognition"] == "And"
    assert entry["box_index"] == 1
    assert entry["all_of"][0]["sub_name"] == "jianlin_target_row"
    assert entry["all_of"][0]["expected"] == daily_ocr["jianlin_daily_row"]["expected"]
    assert entry["all_of"][1] == {
        "sub_name": "jianlin_target_row_go",
        "recognition": "OCR",
        "expected": r"^前往$",
        "roi": "jianlin_target_row",
        "roi_offset": [700, -5, -20, 50],
    }
    assert daily_ocr["jianlin_daily_done"]["recognition"] == "And"
    page = jianlin["jianlin_page"]
    assert page["recognition"] == "And"
    assert page["box_index"] == 0
    assert page["all_of"][0]["expected"] == r"^养成\s*/\s*资源$"
    assert page["all_of"][0]["roi"] == [40, 0, 280, 100]
    assert page["all_of"][1:] == ["jianlin_multiplier_bar", "jianlin_count_bar"]
    assert "jianlin_page.png" not in json.dumps(jianlin, ensure_ascii=False)
    assert jianlin["jianlin_stamina_amount"]["expected"] == r"\+80"
    assert jianlin["jianlin_stamina_price"]["expected"] == r"(?<!\d)10(?!\d)"
    assert jianlin["jianlin_stamina_purchase_confirm"]["roi"] == [680, 375, 150, 80]
    assert jianlin["jianlin_stamina_resource"]["expected"] == "紫色魂玉"
    assert jianlin["jianlin_stamina_plus"]["roi"] == [1110, 10, 55, 60]
    assert "体力" not in jianlin["jianlin_stamina_purchase_prompt"]["expected"]
    assert jianlin["jianlin_count_bar"]["roi"] == [880, 450, 350, 100]
    assert jianlin["jianlin_multiplier_bar"]["roi"] == [880, 370, 350, 100]
    assert jianlin["jianlin_challenge_button"]["expected"] == "挑战"
    assert jianlin["jianlin_challenge_button"]["roi"] == [900, 560, 380, 160]
    assert jianlin["jianlin_buy_confirm"]["expected"] == "挑战"
    assert jianlin["jianlin_buy_confirm"]["roi"] == [900, 560, 380, 160]
    assert daily_ocr["jianlin_condensate_resource"]["roi"] == [0, 210, 280, 150]
    assert daily_ocr["jianlin_condensate_title"]["recognition"] == "TemplateMatch"
    assert daily_ocr["jianlin_condensate_title"]["template"].endswith("condensate_title.png")
    assert daily_ocr["jianlin_battle_page"]["expected"] == "开战"
    assert daily_ocr["ring_daily_task_text"]["expected"] == [
        "挑战一次擂台",
        "挑战一次擂台。",
        "挑战一次论剑",
        "挑战一次论剑。",
    ]
    assert daily_ocr["ring_daily_task_text"]["roi"] == [200, 170, 800, 500]
    assert daily_ocr["ring_daily_row"]["roi"] == [950, 170, 300, 500]
    assert daily_ocr["ring_daily_done"]["roi"] == [950, 170, 300, 500]
    ring = json.loads(
        (
            ROOT
            / "assets/resource_android/pipeline/daily/ring_challenge_daily.json"
        ).read_text(encoding="utf-8")
    )
    assert ring["ring_master_mode"]["roi"] == [0, 560, 540, 160]
    assert ring["ring_master_rank"]["roi"] == [0, 560, 540, 160]


def test_shadow_completion_does_not_match_possible_rewards_popup() -> None:
    daily_ocr = json.loads(
        (ROOT / "assets/resource_android/pipeline/daily_ocr.json").read_text(encoding="utf-8")
    )

    # The stage detail popup always contains “可能获得”.  Generic “获得” must
    # not end the workflow before its 前往 action runs.
    assert "获得" not in daily_ocr["shadow_challenge.done"]["expected"]


def test_android_pipeline_recognizer_names_are_unique_across_files() -> None:
    owners: dict[str, Path] = {}

    def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
        keys = [key for key, _ in pairs]
        assert len(keys) == len(set(keys)), "duplicate key inside Android pipeline JSON"
        return dict(pairs)

    for path in sorted((ROOT / "assets/resource_android/pipeline").rglob("*.json")):
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicate_keys,
        )
        assert isinstance(payload, dict)
        for name in payload:
            previous = owners.get(name)
            assert previous is None, f"pipeline key {name!r} is defined in {previous} and {path}"
            owners[name] = path


def test_android_resource_has_only_a_nonlaunch_game_start_anchor() -> None:
    startup = json.loads(
        (
            ROOT
            / "assets/resource_android/pipeline/startup/game_start.json"
        ).read_text(encoding="utf-8")
    )
    assert set(startup) == {
        "启动-游戏入口",
        "启动-游戏启动",
        "启动-游戏就绪",
    }
    assert all(node.get("action") != "StartApp" for node in startup.values())

    # The Android runner starts the package before Maa.  The resource copy
    # only needs a home/runtime-health anchor for [JumpBack] recovery and must
    # never gain a second package-launch router.
    for path in sorted((ROOT / "assets/resource_android/pipeline").rglob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert "MJA_GAME_LAUNCH" not in payload
        assert not any(name.startswith("MJA_START_") for name in payload)


def test_android_ocr_expected_patterns_are_valid_regexes() -> None:
    def visit(value: object, path: Path) -> None:
        if isinstance(value, dict):
            if value.get("recognition") == "OCR":
                expected = value.get("expected")
                patterns = expected if isinstance(expected, list) else [expected]
                for pattern in patterns:
                    assert isinstance(pattern, str)
                    try:
                        re.compile(pattern)
                    except re.error as exc:
                        raise AssertionError(f"invalid OCR regex in {path}: {pattern!r}") from exc
            for child in value.values():
                visit(child, path)
        elif isinstance(value, list):
            for child in value:
                visit(child, path)

    for path in sorted((ROOT / "assets/resource_android/pipeline").rglob("*.json")):
        visit(json.loads(path.read_text(encoding="utf-8")), path)
