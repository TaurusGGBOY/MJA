from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from agent.errors import ErrorCode, MJAError
from agent.workflows.maa_android import (
    MaaAndroidWorkflowDriver,
    _daily_page_visible,
    _dungeon_bag_full_visible,
    _dungeon_sweep_panel_visible,
    _mail_page_visible,
    _ring_battle_result_visible,
    _ring_sweep_reward_popup_visible,
    _shop_page_visible,
    _welcome_title_visible,
)
from agent.workflows.models import ActionIntent, InputKind, VisualEvidence


class Job:
    succeeded = True

    def __init__(self, image):
        self.image = image

    def wait(self):
        return self

    def get(self):
        return self.image


class Controller:
    def __init__(self):
        self.clicks = []
        self.keys = []
        self.swipes = []
        self.touches = []

    def post_screencap(self):
        return Job(np.zeros((720, 1280, 3), dtype=np.uint8))

    def post_click(self, x, y):
        self.clicks.append((x, y))
        return Job(None)

    def post_click_key(self, key):
        self.keys.append(key)
        return Job(None)

    def post_swipe(self, x1, y1, x2, y2, duration):
        self.swipes.append((x1, y1, x2, y2, duration))
        return Job(None)

    def post_touch_down(self, x, y, contact=0, pressure=1):
        self.touches.append(("down", x, y, contact, pressure))
        return Job(None)

    def post_touch_up(self, contact=0):
        self.touches.append(("up", contact))
        return Job(None)


class Detail:
    def __init__(self, hit, box, results=(), all_results=(), best_result=None):
        self.hit = hit
        self.box = box
        self.filtered_results = list(results)
        self.all_results = list(all_results)
        self.best_result = best_result


class OcrResult:
    def __init__(self, text):
        self.text = text


def test_dungeon_full_bag_visual_fallback_is_conservative():
    toast = np.zeros((720, 1280, 3), dtype=np.uint8)
    toast[30:48, 400:800] = (220, 210, 195)

    assert _dungeon_bag_full_visible(toast)
    assert not _dungeon_bag_full_visible(np.zeros((720, 1280, 3), dtype=np.uint8))


def test_dungeon_sweep_panel_visual_fallback_requires_blue_start_control():
    panel = np.zeros((720, 1280, 3), dtype=np.uint8)
    panel[150:510, 120:1260] = (50, 50, 50)
    panel[525:575, 950:1240] = (40, 130, 230)

    assert _dungeon_sweep_panel_visible(panel)
    assert not _dungeon_sweep_panel_visible(np.zeros_like(panel))


def test_dungeon_sweep_panel_fallback_is_bound_to_open_panel_action():
    class PanelController(Controller):
        def post_screencap(self):
            image = np.zeros((720, 1280, 3), dtype=np.uint8)
            image[150:510, 120:1260] = (50, 50, 50)
            image[525:575, 950:1240] = (40, 130, 230)
            return Job(image)

    context = Context()
    context.tasker.controller = PanelController()
    context.run_recognition = lambda name, image: (
        Detail(True, (900, 260, 250, 80))
        if name == "yanwangling_title"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    driver._last_action_id = "open_sweep_panel"

    evidence = driver.recognize(
        driver.capture(),
        ("yanwangling_title", "sweep_panel_page", "ticket_plus", "start_sweep"),
    )

    assert evidence.page_hits["sweep_panel_page"] == 1
    assert evidence.target_hits["ticket_plus"] == 1
    assert evidence.target_hits["start_sweep"] == 1

    driver._last_action_id = None
    resumed = driver.recognize(
        driver.capture(),
        ("yanwangling_title", "sweep_panel_page", "ticket_plus", "start_sweep"),
    )
    assert resumed.page_hits["sweep_panel_page"] == 1


def test_dungeon_ticket_assignment_fallback_requires_assign_action():
    class PanelController(Controller):
        def post_screencap(self):
            image = np.zeros((720, 1280, 3), dtype=np.uint8)
            image[150:510, 120:1260] = (50, 50, 50)
            image[525:575, 950:1240] = (40, 130, 230)
            return Job(image)

    context = Context()
    context.tasker.controller = PanelController()
    context.run_recognition = lambda name, image: Detail(False, None)
    driver = MaaAndroidWorkflowDriver(context)

    driver._last_action_id = "open_sweep_panel"
    untouched = driver.recognize(
        driver.capture(),
        (
            "sweep_panel_page",
            "ticket_plus",
            "start_sweep",
            "assigned_ticket_counter_changed",
        ),
    )
    assert untouched.target_hits.get("assigned_ticket_counter_changed", 0) == 0

    driver._last_action_id = "assign_sweep_ticket"
    assigned = driver.recognize(
        driver.capture(),
        (
            "sweep_panel_page",
            "ticket_plus",
            "start_sweep",
            "assigned_ticket_counter_changed",
        ),
    )
    assert assigned.target_hits["assigned_ticket_counter_changed"] == 1


def test_mail_page_visual_fallback_requires_mail_sheet_layout():
    mail = np.zeros((720, 1280, 3), dtype=np.uint8)
    mail[120:600, 520:1100] = (210, 230, 245)
    mail[160:525, 200:515] = (155, 185, 215)

    assert _mail_page_visible(mail)
    assert not _mail_page_visible(np.zeros_like(mail))


def test_shop_page_visual_fallback_requires_product_grid_and_dark_rail():
    shop = np.zeros((720, 1280, 3), dtype=np.uint8)
    shop[130:600, 300:1240] = (50, 140, 180)

    assert _shop_page_visible(shop)
    shop[65:520, 30:265] = (130, 130, 130)
    assert not _shop_page_visible(shop)


def test_welcome_title_visual_fallback_requires_magenta_title_surface():
    title = np.full((720, 1280, 3), (254, 0, 254), dtype=np.uint8)

    assert _welcome_title_visible(title)
    assert not _welcome_title_visible(np.zeros_like(title))


def test_welcome_title_visual_fallback_exposes_only_start_markers():
    class TitleController(Controller):
        def post_screencap(self):
            return Job(np.full((720, 1280, 3), (254, 0, 254), dtype=np.uint8))

    context = Context()
    context.tasker.controller = TitleController()
    driver = MaaAndroidWorkflowDriver(context)

    evidence = driver.recognize(
        driver.capture(),
        ("reset.start_game", "reset.start_game_welcome", "reset.start_game_button"),
    )

    assert all(
        evidence.target_hits[marker] == 1
        for marker in (
            "reset.start_game",
            "reset.start_game_welcome",
            "reset.start_game_button",
        )
    )
    assert all(
        driver._boxes[marker] == (evidence.frame_id, (430, 600, 420, 100))
        for marker in (
            "reset.start_game",
            "reset.start_game_welcome",
            "reset.start_game_button",
        )
    )
    assert evidence.texts[-1] == "进入游戏"


def test_mail_page_fallback_is_bound_to_open_mail_action():
    image = np.zeros((720, 1280, 3), dtype=np.uint8)
    image[120:600, 520:1100] = (210, 230, 245)
    image[160:525, 200:515] = (155, 185, 215)

    class MailController(Controller):
        def post_screencap(self):
            return Job(image)

    context = Context()
    context.tasker.controller = MailController()
    driver = MaaAndroidWorkflowDriver(context)
    driver._last_action_id = "open_mail"

    evidence = driver.recognize(driver.capture(), ("邮件奖励-邮件-页面", "邮件奖励-邮件-空"))

    assert evidence.page_hits["邮件奖励-邮件-页面"] == 1
    assert evidence.target_hits["邮件奖励-邮件-空"] == 1


def test_shop_period_benefits_fallback_is_bound_to_open_tab_action():
    image = np.zeros((720, 1280, 3), dtype=np.uint8)
    image[130:600, 300:1240] = (50, 140, 180)

    class ShopController(Controller):
        def post_screencap(self):
            return Job(image)

    context = Context()
    context.tasker.controller = ShopController()
    driver = MaaAndroidWorkflowDriver(context)
    driver._last_action_id = "open_period_benefits"

    evidence = driver.recognize(
        driver.capture(), ("商店免费礼包-商店-页面", "商店免费礼包-商店-周期-权益-页面")
    )

    assert evidence.page_hits["商店免费礼包-商店-周期-权益-页面"] == 1
    driver._last_action_id = "open_shop"
    evidence = driver.recognize(driver.capture(), ("商店免费礼包-商店-页面",))
    assert evidence.page_hits["商店免费礼包-商店-页面"] == 1


def test_dungeon_full_bag_visual_fallback_is_action_bound():
    class ToastController(Controller):
        def post_screencap(self):
            image = np.zeros((720, 1280, 3), dtype=np.uint8)
            image[30:48, 400:800] = (220, 210, 195)
            return Job(image)

    context = Context()
    context.tasker.controller = ToastController()

    def recognize(name, image):
        if name == "yanwangling_title":
            return Detail(True, (329, 358, 262, 69))
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)
    driver._last_action_id = "study_martial_slot"
    driver._last_action_id = "open_sweep_panel"

    evidence = driver.recognize(
        driver.capture(),
        ("yanwangling_title", "dungeon_bag_full", "sweep_panel_page"),
    )

    assert evidence.target_hits["dungeon_bag_full"] == 1
    assert driver._boxes["dungeon_bag_full"][0] == evidence.frame_id
    assert any("背包已满" in text for text in evidence.texts)

    driver._last_action_id = "select_yanwangling"
    evidence = driver.recognize(
        driver.capture(),
        ("yanwangling_title", "dungeon_bag_full", "sweep_panel_page"),
    )
    assert evidence.target_hits.get("dungeon_bag_full", 0) == 0


def test_dungeon_full_bag_fallback_accepts_faded_toast_on_unchanged_detail_page():
    context = Context()

    def recognize(name, image):
        if name == "yanwangling_title":
            return Detail(True, (329, 358, 262, 69))
        if name == "sweep_target":
            return Detail(True, (1003, 605, 39, 21))
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)
    driver._last_action_id = "open_sweep_panel"

    evidence = driver.recognize(
        driver.capture(),
        ("yanwangling_title", "sweep_target", "dungeon_bag_full", "sweep_panel_page"),
    )

    assert evidence.target_hits["dungeon_bag_full"] == 1


class Context:
    def __init__(self):
        self.tasker = type("Tasker", (), {"controller": Controller()})()

    def run_recognition(self, name, image):
        if name == "target":
            return Detail(True, (100, 200, 40, 20))
        if name == "page":
            return Detail(True, (0, 0, 100, 100))
        return Detail(False, None)


def test_maa_adapter_preserves_same_frame_box_for_bounded_click():
    context = Context()
    driver = MaaAndroidWorkflowDriver(context)
    frame = driver.capture()
    evidence = driver.recognize(frame, ("page", "target"))
    assert evidence.page_hits["page"] == 1
    intent = ActionIntent("click_target", "page", "target", input_kind=InputKind.CLICK)
    driver.execute(intent)
    assert context.tasker.controller.clicks == [(120, 210)]


def test_trial_entry_uses_the_same_frame_maa_button_box():
    context = Context()
    driver = MaaAndroidWorkflowDriver(context)
    driver._last_frame_id = "frame-1"
    driver._boxes["试剑-试炼-打开"] = ("frame-1", (986, 640, 50, 28))
    boxes = []
    driver._controller_tap = boxes.append

    driver.execute(
        ActionIntent(
            "open_trial_sword",
            "home",
            "试剑-试炼-打开",
            input_kind=InputKind.CLICK,
        )
    )

    assert boxes == [(986, 640, 50, 28)]


def test_maa_adapter_derives_martial_full_slots_without_native_pipeline_lookup():
    context = Context()
    requested = []

    def recognize(name, image):
        requested.append(name)
        assert name != "martial_full_slots"
        if name == "martial_page":
            return Detail(True, (0, 0, 1280, 720))
        if name.startswith("martial_timer_slot_"):
            return Detail(True, (800, 540, 120, 70))
        return Detail(False, None)

    context.run_recognition = recognize

    class Gate:
        device = object()

        def require_foreground(self):
            return None

    driver = MaaAndroidWorkflowDriver(context, runtime_gate=Gate())
    evidence = driver.recognize(
        driver.capture(),
        (
            "martial_page",
            "martial_full_slots",
            "martial_timer_slot_0",
            "martial_timer_slot_1",
            "martial_timer_slot_2",
        ),
    )

    assert "martial_full_slots" not in requested
    assert evidence.target_hits["martial_full_slots"] == 1


def test_maa_adapter_derives_jianlin_completion_from_same_row_green_tick():
    class GreenController(Controller):
        def post_screencap(self):
            image = np.zeros((720, 1280, 3), dtype=np.uint8)
            image[270:365, 1040:1100, 1] = 200
            return Job(image)

    context = Context()
    context.tasker.controller = GreenController()

    def recognize(name, image):
        if name == "日常任务奖励-日常-页面":
            return Detail(True, (0, 0, 620, 190))
        if name == "jianlin_daily_row":
            return Detail(True, (290, 295, 300, 35))
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)
    evidence = driver.recognize(
        driver.capture(),
        ("日常任务奖励-日常-页面", "jianlin_daily_row", "jianlin_daily_done"),
    )

    assert evidence.target_hits["jianlin_daily_done"] == 1


def test_maa_adapter_derives_martial_detail_from_action_after_slot_open():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (1100, 545, 150, 80))
        if name == "martial_study_action"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    driver._last_action_id = "open_martial_plus_slot_2"

    evidence = driver.recognize(
        driver.capture(),
        ("martial_study_detail", "martial_study_action"),
    )

    assert evidence.page_hits["martial_study_detail"] == 1
    assert evidence.target_hits["martial_study_action"] == 1


def test_maa_adapter_promotes_martial_page_after_open_when_title_ocr_misses():
    context = Context()

    def recognize(name, image):
        if name == "martial_plus_slot_1":
            return Detail(True, (920, 250, 160, 300))
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)
    driver._last_action_id = "open_martial_study"

    evidence = driver.recognize(
        driver.capture(),
        ("martial_page", "martial_plus_slot_1", "martial_close"),
    )

    assert evidence.page_hits["martial_page"] == 1
    assert evidence.target_hits["martial_close"] == 1
    assert driver._boxes["martial_close"][1] == (1160, 0, 100, 100)


def test_maa_adapter_keeps_martial_detail_after_study_refresh_ocr_misses():
    context = Context()

    def recognize(name, image):
        if name == "martial_close":
            return Detail(True, (1160, 0, 100, 100))
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)
    driver._last_action_id = "study_martial_slot"

    evidence = driver.recognize(
        driver.capture(),
        (
            "martial_study_detail",
            "martial_study_button",
            "martial_page",
            "martial_close",
        ),
    )

    assert evidence.page_hits["martial_study_detail"] == 1
    assert evidence.target_hits["martial_study_button"] == 1
    assert driver._boxes["martial_study_button"][1] == (880, 535, 320, 70)


def test_maa_adapter_reports_unavailable_martial_configuration_as_evidence():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (850, 450, 380, 200))
        if name == "martial_study_detail"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    driver._last_action_id = "study_martial_slot"
    driver._martial_configuration_unavailable = True

    evidence = driver.recognize(
        driver.capture(),
        ("martial_study_detail",),
    )

    assert evidence.target_hits["martial_no_sufficient_configuration"] == 1


def test_maa_adapter_does_not_raise_when_martial_material_search_is_exhausted(
    monkeypatch,
):
    context = Context()
    driver = MaaAndroidWorkflowDriver(context)
    driver._last_frame_id = "frame-1"
    driver._boxes["martial_study_action"] = ("frame-1", (1080, 530, 160, 90))
    monkeypatch.setattr(
        driver,
        "_prepare_martial_study_configuration",
        lambda **_kwargs: False,
    )

    driver.execute(
        ActionIntent(
            "study_martial_slot",
            "martial_study_detail",
            "martial_study_action",
            input_kind=InputKind.CLICK,
        )
    )

    assert driver._martial_configuration_unavailable is True
    assert context.tasker.controller.clicks == []
    assert context.tasker.controller.touches == []


def test_maa_adapter_closes_martial_detail_with_android_back_key():
    context = Context()
    driver = MaaAndroidWorkflowDriver(context)
    driver._last_frame_id = "frame-1"
    driver._boxes["martial_close"] = ("frame-1", (1160, 0, 100, 100))

    driver.execute(
        ActionIntent(
            "close_martial_page",
            "martial_study_detail",
            "martial_close",
            input_kind=InputKind.CLICK,
        )
    )

    assert context.tasker.controller.keys == [4]
    assert context.tasker.controller.clicks == []


def test_maa_adapter_requires_all_four_martial_materials_for_sufficiency():
    context = Context()
    ratios = {
        "martial_material_ratio_1": "6435/2400",
        "martial_material_ratio_2": "1079/160",
        "martial_material_ratio_3": "0/100",
        "martial_material_ratio_4": "60/60",
    }

    def recognize(name, image):
        if name in ratios:
            return Detail(True, (500, 535, 100, 65), results=[OcrResult(ratios[name])])
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)
    evidence = driver.recognize(
        driver.capture(),
        (
            "martial_material_ratio_1",
            "martial_material_ratio_2",
            "martial_material_ratio_3",
            "martial_material_ratio_4",
            "martial_materials_sufficient",
            "martial_materials_insufficient",
        ),
    )

    assert evidence.target_hits.get("martial_materials_sufficient", 0) == 0
    assert evidence.target_hits["martial_materials_insufficient"] == 1


def test_maa_adapter_accepts_a_three_material_martial_configuration():
    context = Context()
    ratios = {
        "martial_material_ratio_1": "6435/800",
        "martial_material_ratio_2": "598/80",
        "martial_material_ratio_3": "50/50",
    }

    def recognize(name, image):
        if name in ratios:
            return Detail(True, (500, 535, 100, 65), results=[OcrResult(ratios[name])])
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)
    evidence = driver.recognize(
        driver.capture(),
        (
            "martial_material_ratio_1",
            "martial_material_ratio_2",
            "martial_material_ratio_3",
            "martial_material_ratio_4",
            "martial_materials_sufficient",
            "martial_materials_insufficient",
        ),
    )

    assert evidence.target_hits["martial_materials_sufficient"] == 1
    assert evidence.target_hits.get("martial_materials_insufficient", 0) == 0


def test_maa_adapter_keeps_breakthrough_progress_on_detail_boundary():
    context = Context()

    def recognize(name, image):
        if name == "martial_candidate_in_progress":
            return Detail(True, (700, 520, 250, 80))
        if name == "martial_page":
            return Detail(True, (0, 0, 1280, 720))
        if name == "martial_plus_slot_1":
            return Detail(True, (920, 250, 160, 300))
        if name == "martial_close":
            return Detail(True, (1160, 0, 100, 100))
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)
    driver._last_action_id = "confirm_martial_breakthrough"

    evidence = driver.recognize(
        driver.capture(),
        (
            "martial_page",
            "martial_study_detail",
            "martial_candidate_in_progress",
            "martial_plus_slot_1",
            "martial_close",
        ),
    )

    assert evidence.page_hits["martial_study_detail"] == 1
    assert evidence.page_hits["martial_page"] == 0
    assert evidence.target_hits["martial_plus_slot_1"] == 0


def test_maa_adapter_promotes_function_panel_after_its_authorized_open_action():
    context = Context()
    driver = MaaAndroidWorkflowDriver(context)
    driver._last_action_id = "open_function_panel"

    evidence = driver.recognize(
        driver.capture(),
        ("function_panel.page", "日常任务奖励-日常-入口", "unknown_dialog", "破阵武学-安全-付费"),
    )

    assert evidence.page_hits["function_panel.page"] == 1
    assert evidence.target_hits["function_panel.page"] == 1


def test_maa_adapter_uses_calibrated_daily_entry_fallback_without_ocr_box():
    context = Context()

    def recognize(name, image):
        if name == "function_panel.page":
            return Detail(True, (0, 0, 1280, 720))
        if name == "日常任务奖励-日常-入口":
            # This is the live failure mode: OCR hits 日常 but Maa does not
            # return a usable result rectangle on the transition frame.
            return Detail(True, None)
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)
    evidence = driver.recognize(
        driver.capture(),
        ("function_panel.page", "日常任务奖励-日常-入口"),
    )

    assert evidence.target_hits["日常任务奖励-日常-入口"] == 1
    assert driver._boxes["日常任务奖励-日常-入口"][1] == (1065, 220, 110, 105)
    driver.execute(
        ActionIntent(
            "open_daily_tasks",
            "function_panel.page",
            "日常任务奖励-日常-入口",
            input_kind=InputKind.CLICK,
        )
    )
    assert context.tasker.controller.clicks == [(1120, 273)]


def test_maa_adapter_does_not_guess_a_bag_tile_before_the_panel_scroll():
    context = Context()

    def recognize(name, image):
        if name == "function_panel.page":
            return Detail(True, (840, 0, 280, 160))
        if name == "bag_entry":
            return Detail(False, None)
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)
    frame = driver.capture()
    evidence = driver.recognize(frame, ("function_panel.page", "bag_entry"))

    assert evidence.target_hits["bag_entry"] == 0
    assert "bag_entry" not in driver._boxes


def test_maa_adapter_exposes_generic_martial_study_button_on_detail_page():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (0, 0, 1280, 720))
        if name == "martial_study_detail"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)

    evidence = driver.recognize(
        driver.capture(),
        ("martial_study_detail", "martial_study_button"),
    )

    assert evidence.target_hits["martial_study_button"] == 1
    assert driver._boxes["martial_study_button"][1] == (880, 535, 320, 70)


def test_maa_adapter_normalizes_partial_martial_glyph_to_full_button_box():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (1120, 550, 30, 40))
        if name == "martial_breakthrough_action"
        else Detail(True, (0, 0, 1280, 720))
        if name == "martial_study_detail"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)

    evidence = driver.recognize(
        driver.capture(),
        ("martial_study_detail", "martial_breakthrough_action"),
    )

    assert evidence.target_hits["martial_breakthrough_action"] == 1
    assert driver._boxes["martial_breakthrough_action"][1] == (880, 535, 320, 70)


def test_dungeon_assigns_target_plus_exactly_ten_times(monkeypatch):
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (1200, 370, 80, 100))
        if name == "ticket_plus"
        else Detail(True, (300, 100, 900, 520))
        if name == "sweep_panel_page"
        else Detail(False, None)
    )
    monkeypatch.setattr("agent.workflows.maa_android.sleep", lambda _seconds: None)
    driver = MaaAndroidWorkflowDriver(context)
    frame = driver.capture()
    driver.recognize(frame, ("sweep_panel_page", "ticket_plus"))

    driver.execute(
        ActionIntent(
            "assign_sweep_ticket",
            "sweep_panel_page",
            "ticket_plus",
            input_kind=InputKind.CLICK,
        )
    )

    assert context.tasker.controller.clicks == [(1240, 420)] * 10


def test_maa_adapter_cleanup_stops_at_recognized_home():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (1040, 0, 240, 110))
        if name == "reset.home"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)

    assert driver.return_to_home() is True
    assert context.tasker.controller.clicks == []


def test_maa_adapter_boundary_closes_martial_detail_with_android_control(monkeypatch):
    context = Context()
    surface = {"name": "detail"}

    def recognize(name, image):
        if surface["name"] == "detail" and name == "martial_study_detail":
            return Detail(True, (500, 100, 730, 540))
        if surface["name"] == "page" and name == "martial_page":
            return Detail(True, (60, 30, 120, 30))
        if surface["name"] == "panel" and name in {
            "reset.function_panel",
            "reset.panel_close",
        }:
            return Detail(True, (1100, 0, 100, 100))
        if surface["name"] == "home" and name == "reset.home":
            return Detail(True, (1040, 0, 240, 110))
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)
    driver._last_action_id = "study_martial_slot"

    def drag_tap(box):
        context.tasker.controller.touches.extend(
            [("down", 1210, 50, 0, 1), ("up", 0)]
        )
        if box == (1160, 0, 100, 100):
            surface["name"] = "page" if surface["name"] == "detail" else "home"

    driver._controller_drag_tap = drag_tap
    monkeypatch.setattr("agent.workflows.maa_android.sleep", lambda _seconds: None)

    assert driver.return_to_home(max_steps=4) is True
    assert context.tasker.controller.keys == []
    assert context.tasker.controller.clicks == []
    assert context.tasker.controller.touches == [
        ("down", 1210, 50, 0, 1),
        ("up", 0),
        ("down", 1210, 50, 0, 1),
        ("up", 0),
    ]


def test_maa_adapter_cleanup_does_not_treat_launcher_ocr_as_home():
    context = Context()

    def recognize(name, image):
        if name == "home.painting_scroll_text":
            return Detail(True, (850, 0, 430, 180))
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)

    assert driver.return_to_home() is False
    assert context.tasker.controller.clicks == []


def test_maa_adapter_cleanup_accepts_game_hud_plus_painting_ocr_as_home():
    context = Context()

    def recognize(name, image):
        if name == "home.painting_scroll_text":
            return Detail(True, (850, 0, 430, 180))
        if name in {"home.power_text", "home.quest_text"}:
            return Detail(True, (0, 0, 430, 360))
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)

    assert driver.return_to_home() is True
    assert context.tasker.controller.clicks == []


def test_maa_adapter_android_boundary_rejects_launcher_home_template():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (1040, 0, 240, 110))
        if name == "reset.home"
        else Detail(False, None)
    )

    class Gate:
        device = object()

        def require_foreground(self):
            return None

    driver = MaaAndroidWorkflowDriver(context, runtime_gate=Gate())

    assert driver.return_to_home(max_steps=1) is False
    assert context.tasker.controller.clicks == []


def test_maa_adapter_android_boundary_accepts_home_template_with_hud():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (1040, 0, 240, 110))
        if name in {"reset.home", "home.power_text"}
        else Detail(False, None)
    )

    class Gate:
        device = object()

        def require_foreground(self):
            return None

    driver = MaaAndroidWorkflowDriver(context, runtime_gate=Gate())

    assert driver.return_to_home(max_steps=1) is True


def test_maa_adapter_android_boundary_accepts_hud_when_home_template_drifts():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (850, 0, 430, 180))
        if name == "home.painting_scroll_text"
        else Detail(True, (200, 0, 400, 80))
        if name == "home.power_text"
        else Detail(True, (0, 210, 350, 100))
        if name == "home.quest_text"
        else Detail(False, None)
    )

    class Gate:
        device = object()

        def require_foreground(self):
            return None

    driver = MaaAndroidWorkflowDriver(context, runtime_gate=Gate())

    assert driver.return_to_home(max_steps=1) is True


def test_maa_adapter_android_boundary_accepts_updated_hud_without_painting_label():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (200, 0, 400, 80))
        if name == "home.power_text"
        else Detail(True, (0, 210, 350, 100))
        if name == "home.quest_text"
        else Detail(False, None)
    )

    class Gate:
        device = object()

        def require_foreground(self):
            return None

    driver = MaaAndroidWorkflowDriver(context, runtime_gate=Gate())

    assert driver.return_to_home(max_steps=1) is True


def test_maa_adapter_dismisses_guild_unlock_dialog_before_accepting_home():
    context = Context()
    state = {"dialog": True}

    def recognize(name, image):
        if state["dialog"] and name == "reset.guild_unlock_dialog":
            return Detail(True, (760, 120, 470, 180))
        if state["dialog"] and name == "reset.dialog_skip":
            return Detail(True, (1080, 80, 80, 60))
        if name == "home.power_text":
            return Detail(True, (200, 0, 400, 80))
        if name == "home.quest_text":
            return Detail(True, (0, 210, 350, 100))
        return Detail(False, None)

    context.run_recognition = recognize

    class Gate:
        device = object()

        def require_foreground(self):
            return None

    driver = MaaAndroidWorkflowDriver(context, runtime_gate=Gate())

    original_tap = driver._controller_tap

    def tap(box):
        original_tap(box)
        state["dialog"] = False

    driver._controller_tap = tap

    assert driver.return_to_home(max_steps=3) is True
    assert context.tasker.controller.clicks == [(1120, 110)]


def test_maa_adapter_does_not_promote_daily_ring_announcement_to_ring_page():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (0, 0, 620, 190))
        if name == "日常任务奖励-日常-页面"
        else Detail(True, (0, 0, 1280, 180))
        if name in {"ring_page", "ring_page_close"}
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)

    evidence = driver.recognize(
        driver.capture(),
        ("日常任务奖励-日常-页面", "ring_page", "ring_page_close"),
    )

    assert evidence.page_hits["日常任务奖励-日常-页面"] == 1
    assert evidence.page_hits["ring_page"] == 0


def test_maa_adapter_does_not_derive_ring_completion_from_a_green_tick():
    class GreenController(Controller):
        def post_screencap(self):
            image = np.zeros((720, 1280, 3), dtype=np.uint8)
            image[520:640, 1040:1100, 1] = 200
            return Job(image)

    context = Context()
    context.tasker.controller = GreenController()

    context.run_recognition = lambda name, image: (
        Detail(True, (0, 0, 620, 190))
        if name == "日常任务奖励-日常-页面"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)

    evidence = driver.recognize(
        driver.capture(),
        ("日常任务奖励-日常-页面", "ring_daily_row", "ring_daily_done"),
    )

    assert evidence.target_hits["ring_daily_done"] == 0


def test_maa_adapter_derives_ring_completion_from_same_row_green_tick():
    class GreenController(Controller):
        def post_screencap(self):
            image = np.zeros((720, 1280, 3), dtype=np.uint8)
            image[520:640, 1040:1100, 1] = 200
            return Job(image)

    context = Context()
    context.tasker.controller = GreenController()
    context.run_recognition = lambda name, image: (
        Detail(True, (0, 0, 620, 190))
        if name == "日常任务奖励-日常-页面"
        else Detail(True, (200, 550, 300, 30))
        if name == "ring_daily_task_text"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)

    frame = driver.capture()
    evidence = driver.recognize(
        frame,
        ("日常任务奖励-日常-页面", "ring_daily_task_text", "ring_daily_done"),
    )

    assert evidence.target_hits["ring_daily_done"] == 1
    assert driver._boxes["ring_daily_done"] == (
        frame.frame_id,
        (950, 505, 220, 120),
    )


def test_maa_adapter_does_not_forge_ring_row_from_daily_page_alone():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (0, 0, 620, 190))
        if name == "日常任务奖励-日常-页面"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)

    evidence = driver.recognize(
        driver.capture(),
        ("日常任务奖励-日常-页面", "ring_daily_task_text", "ring_daily_row"),
    )

    assert evidence.target_hits["ring_daily_row"] == 0


def test_maa_adapter_recovers_ring_row_only_from_exact_task_text():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (0, 0, 620, 190))
        if name == "日常任务奖励-日常-页面"
        else Detail(True, (200, 200, 800, 110))
        if name == "ring_daily_task_text"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    frame = driver.capture()

    evidence = driver.recognize(
        frame,
        ("日常任务奖励-日常-页面", "ring_daily_task_text", "ring_daily_row"),
    )

    assert evidence.target_hits["ring_daily_row"] == 1
    assert driver._boxes["ring_daily_row"] == (
        frame.frame_id,
        (1000, 155, 240, 180),
    )


def test_trial_zero_counter_alone_does_not_prove_free_trial_was_used():
    context = Context()

    def recognize(name, image):
        if name == "试剑-试炼-页面":
            return Detail(True, (0, 160, 500, 300))
        if name == "trial.current_reward_zero":
            return Detail(True, (30, 495, 120, 105))
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)
    evidence = driver.recognize(
        driver.capture(),
        ("试剑-试炼-页面", "trial.free_used", "trial.current_reward_zero"),
    )

    assert evidence.target_hits["trial.current_reward_zero"] == 1
    assert evidence.target_hits["trial.free_used"] == 0


def test_maa_adapter_closes_mail_from_fast_page_probe_with_fixed_region():
    context = Context()
    current = {"name": "mail"}
    requested = []

    def recognize(name, image):
        requested.append(name)
        if name == "邮件奖励-邮件-页面" and current["name"] == "mail":
            return Detail(True, (300, 90, 420, 100))
        if name == "邮件奖励-邮件-空" and current["name"] == "mail":
            return Detail(True, (300, 520, 900, 180))
        if name == "reset.home" and current["name"] == "home":
            return Detail(True, (1040, 0, 240, 110))
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)
    original_tap = driver._controller_tap

    def tap(box):
        original_tap(box)
        current["name"] = "home"

    driver._controller_tap = tap

    assert driver.return_to_home() is True
    assert context.tasker.controller.clicks == [(1120, 160)]
    assert {"邮件奖励-邮件-页面", "邮件奖励-邮件-空", "邮件奖励-邮件-关闭", "reset.mail_close"}.issubset(
        requested
    )


def test_mail_page_without_claim_template_is_already_complete_after_open():
    context = Context()

    def recognize(name, image):
        if name == "邮件奖励-邮件-页面":
            return Detail(True, (300, 90, 420, 100))
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)
    driver._last_action_id = "open_mail"

    evidence = driver.recognize(
        driver.capture(),
        ("邮件奖励-邮件-页面", "邮件奖励-邮件-领取-全部", "邮件奖励-邮件-空"),
    )

    assert evidence.page_hits["邮件奖励-邮件-页面"] == 1
    assert evidence.target_hits["邮件奖励-邮件-领取-全部"] == 0
    assert evidence.target_hits["邮件奖励-邮件-空"] == 1
    assert driver._boxes["邮件奖励-邮件-空"][1] == (300, 520, 900, 180)
    assert context.tasker.controller.clicks == []


def test_maa_adapter_closes_ring_not_open_from_fast_page_probe():
    context = Context()
    current = {"name": "ring"}

    def recognize(name, image):
        if name == "ring_page" and current["name"] == "ring":
            return Detail(True, (0, 0, 1280, 180))
        if name == "ring_not_open" and current["name"] == "ring":
            return Detail(True, (740, 580, 540, 100))
        if name == "reset.home" and current["name"] == "home":
            return Detail(True, (1040, 0, 240, 110))
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)
    original_tap = driver._controller_tap

    def tap(box):
        original_tap(box)
        current["name"] = "home"

    driver._controller_tap = tap

    assert driver.return_to_home() is True
    assert context.tasker.controller.clicks == [(1210, 50)]


def test_maa_adapter_does_not_treat_ring_opponent_page_as_result_in_boundary():
    context = Context()
    current = {"surface": "opponents"}

    def recognize(name, image):
        if current["surface"] == "opponents":
            if name == "ring_opponent_page":
                return Detail(True, (90, 28, 84, 24))
            if name == "ring_opponent_close":
                return Detail(True, (1120, 0, 160, 120))
        if current["surface"] == "home" and name == "reset.home":
            return Detail(True, (1040, 0, 240, 110))
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)
    original_tap = driver._controller_tap

    def tap(box):
        original_tap(box)
        current["surface"] = "home"

    driver._controller_tap = tap

    assert driver.return_to_home() is True
    assert context.tasker.controller.clicks == [(1210, 50)]


def test_maa_adapter_closes_shadow_recommendation_boundary_before_next_task(
    monkeypatch,
):
    context = Context()
    state = {"surface": "recommendation"}

    def recognize(name, image):
        if state["surface"] == "recommendation" and name == "shadow_recommended_team_page":
            return Detail(True, (40, 10, 120, 60))
        if state["surface"] == "formation" and name == "shadow_formation_page":
            return Detail(True, (450, 0, 420, 100))
        if state["surface"] == "home" and name == "reset.home":
            return Detail(True, (1040, 0, 240, 110))
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)
    original_tap = driver._controller_tap
    monkeypatch.setattr("agent.workflows.maa_android.sleep", lambda _: None)

    def tap(box):
        original_tap(box)
        state["surface"] = (
            "formation" if state["surface"] == "recommendation" else "home"
        )

    driver._controller_tap = tap

    assert driver.return_to_home(max_steps=4) is True
    assert context.tasker.controller.clicks == [(1210, 50), (1210, 50)]


def test_maa_adapter_limits_repeated_full_boundary_scans():
    context = Context()
    captures = {"count": 0}
    original_capture = context.tasker.controller.post_screencap

    def capture():
        captures["count"] += 1
        return original_capture()

    context.tasker.controller.post_screencap = capture
    context.run_recognition = lambda name, image: (
        Detail(True, (0, 0, 420, 110))
        if name == "采集部署-采集-页面"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)

    assert driver.return_to_home(max_steps=30) is False
    # A recognized collection close is followed only by cheap probes; a stale
    # screen must not restart the expensive full-scan loop indefinitely.
    assert captures["count"] <= 4


def test_maa_adapter_cleanup_does_not_click_unknown_top_right_chrome():
    context = Context()
    driver = MaaAndroidWorkflowDriver(context)

    assert driver.return_to_home() is False
    assert context.tasker.controller.clicks == []


def test_task_boundary_accepts_home_after_foreground_check():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (1040, 0, 240, 110))
        if name == "reset.home"
        else Detail(False, None)
    )

    class Gate:
        def __init__(self):
            self.calls = 0

        def require_foreground(self):
            self.calls += 1

    gate = Gate()
    driver = MaaAndroidWorkflowDriver(context, runtime_gate=gate)

    driver.require_task_boundary("MAIL_REWARD_DAILY")

    assert gate.calls == 1
    assert context.tasker.controller.clicks == []


def test_task_boundary_retries_transient_launcher_recovery_before_actions():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (1040, 0, 240, 110))
        if name == "reset.home"
        else Detail(False, None)
    )

    class Gate:
        def __init__(self):
            self.calls = 0

        def require_foreground(self):
            self.calls += 1
            if self.calls < 3:
                raise MJAError(
                    ErrorCode.ANDROID_GAME_NOT_FOREGROUND,
                    "transient Launcher handoff",
                )

    gate = Gate()
    driver = MaaAndroidWorkflowDriver(context, runtime_gate=gate)
    recoveries: list[bool] = []

    def recover_game_ready(*, restart_if_needed: bool = True) -> bool:
        recoveries.append(restart_if_needed)
        return len(recoveries) == 2

    driver.recover_game_ready = recover_game_ready

    driver.require_task_boundary("MAIL_REWARD_DAILY")

    assert gate.calls == 3
    assert recoveries == [True, True]
    assert context.tasker.controller.clicks == []


def test_task_boundary_rejects_unknown_screen_without_input():
    context = Context()
    driver = MaaAndroidWorkflowDriver(context)

    with pytest.raises(MJAError) as error:
        driver.require_task_boundary("MAIL_REWARD_DAILY")

    assert error.value.code is ErrorCode.WORKFLOW_POSTCONDITION_MISSING
    assert context.tasker.controller.clicks == []


def test_task_boundary_preserves_failed_shadow_surface_for_resume():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (0, 0, 1280, 720))
        if name == "shadow_exploration_page"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)

    driver.require_task_boundary("SHADOW_RUINS_DAILY")

    assert context.tasker.controller.clicks == []


def test_recovery_restarts_after_initial_process_loss(monkeypatch):
    context = Context()
    events = []
    readiness_modes = []

    class Device:
        config = object()

        def foreground_package(self):
            return "com.google.android.apps.nexuslauncher"

        def game_process_id(self, package_name):
            return None

        def start_app(self, package_name):
            events.append("start")

        def restart(self, package_name):
            events.append("restart")

        def require_memory_health(self):
            return None

        def require_game_process(self, package_name):
            if events == ["start"]:
                raise MJAError(ErrorCode.ANDROID_GAME_PROCESS_DIED, "process exited")

    class Gate:
        device = Device()
        package_name = "com.hanjiasongshu.dr22"

    class Login:
        def __init__(self, config):
            pass

        def wait_until_ready(self, device, **kwargs):
            readiness_modes.append(kwargs.get("require_interactive"))
            return None

    monkeypatch.setattr("agent.workflows.maa_android.LoginGate", Login)
    driver = MaaAndroidWorkflowDriver(context, runtime_gate=Gate())
    driver.return_to_home = lambda **_: True
    driver._verify_android_home_boundary = lambda: True

    assert driver.recover_game_ready() is True
    assert events == ["start", "restart"]
    assert readiness_modes == [True, True]


def test_recovery_dismisses_a_stale_daily_reward_popup_before_login_gate(monkeypatch):
    context = Context()
    state = {"popup": True}

    def recognize(name, image):
        if state["popup"] and name in {
            "日常任务奖励-日常-奖励-弹窗",
            "日常任务奖励-日常-奖励-弹窗-关闭",
        }:
            return Detail(True, (300, 560, 700, 160))
        return Detail(False, None)

    context.run_recognition = recognize

    class Device:
        config = object()

        def foreground_package(self):
            return "com.hanjiasongshu.dr22"

        def game_process_id(self, package_name):
            return 1

        def require_memory_health(self):
            return None

        def require_game_process(self, package_name):
            return None

    class Gate:
        device = Device()
        package_name = "com.hanjiasongshu.dr22"

    class Login:
        def __init__(self, config):
            pass

        def wait_until_ready(self, device, **kwargs):
            return None

    monkeypatch.setattr("agent.workflows.maa_android.LoginGate", Login)
    driver = MaaAndroidWorkflowDriver(context, runtime_gate=Gate())
    original_tap = driver._controller_tap

    def tap(box):
        original_tap(box)
        state["popup"] = False

    driver._controller_tap = tap
    driver.return_to_home = lambda **_: True
    driver._verify_android_home_boundary = lambda: True

    assert driver.recover_game_ready() is True
    assert context.tasker.controller.clicks == [(1200, 670)]


def test_daily_page_visual_fallback_rejects_launcher():
    daily = np.full((720, 1280, 3), (160, 150, 140), dtype=np.uint8)
    daily[210:300, 210:1160] = (220, 240, 250)
    daily[320:410, 210:1160] = (220, 240, 250)
    daily[430:520, 210:1160] = (220, 240, 250)
    daily[540:630, 210:1160] = (220, 240, 250)
    launcher = np.zeros_like(daily)

    assert _daily_page_visible(daily) is True
    assert _daily_page_visible(launcher) is False


def test_maa_adapter_closes_recognized_monthly_signin_sheet():
    context = Context()
    current = {"name": "monthly_signin"}

    def recognize(name, image):
        if name == "reset.monthly_signin_page" and current["name"] == "monthly_signin":
            return Detail(True, (240, 100, 880, 500))
        if name == "reset.home" and current["name"] == "home":
            return Detail(True, (850, 0, 430, 180))
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)
    original_tap = driver._controller_tap

    def tap(box):
        original_tap(box)
        current["name"] = "home"

    driver._controller_tap = tap

    assert driver.return_to_home() is True
    assert context.tasker.controller.clicks == [(1080, 160)]


def test_maa_adapter_closes_recognized_shop_page_before_next_task():
    context = Context()
    current = {"name": "shop"}

    def recognize(name, image):
        if name == "商店免费礼包-商店-页面" and current["name"] == "shop":
            return Detail(True, (0, 0, 1280, 720))
        if name == "reset.modal_close" and current["name"] == "shop":
            return Detail(True, (1160, 0, 100, 100))
        if name == "reset.home" and current["name"] == "home":
            return Detail(True, (850, 0, 430, 180))
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)
    original_tap = driver._controller_tap

    def tap(box):
        original_tap(box)
        current["name"] = "home"

    driver._controller_tap = tap

    assert driver.return_to_home() is True
    assert context.tasker.controller.clicks == [(1210, 50)]


def test_maa_adapter_closes_recognized_shop_page_with_daily_close_target():
    context = Context()
    current = {"name": "shop"}

    def recognize(name, image):
        if name == "商店免费礼包-商店-页面" and current["name"] == "shop":
            return Detail(True, (0, 0, 1280, 720))
        if name == "reset.daily_close" and current["name"] == "shop":
            return Detail(True, (1160, 0, 100, 100))
        if name == "reset.home" and current["name"] == "home":
            return Detail(True, (850, 0, 430, 180))
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)
    original_tap = driver._controller_tap

    def tap(box):
        original_tap(box)
        current["name"] = "home"

    driver._controller_tap = tap

    assert driver.return_to_home() is True
    assert context.tasker.controller.clicks == [(1210, 50)]


def test_maa_adapter_closes_recognized_universal_shop_boundary():
    context = Context()
    current = {"name": "universal_shop"}

    def recognize(name, image):
        if (
            name == "universal_shop_boundary"
            and current["name"] == "universal_shop"
        ):
            return Detail(True, (0, 0, 320, 120))
        if name == "reset.home" and current["name"] == "home":
            return Detail(True, (850, 0, 430, 180))
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)
    original_tap = driver._controller_tap

    def tap(box):
        original_tap(box)
        current["name"] = "home"

    driver._controller_tap = tap

    assert driver.return_to_home() is True
    assert context.tasker.controller.clicks == [(1210, 50)]


def test_maa_adapter_closes_dispatch_and_painting_before_next_task():
    context = Context()
    current = {"name": "dispatch"}

    def recognize(name, image):
        if name == "英雄派遣-英雄-派遣-页面" and current["name"] == "dispatch":
            return Detail(True, (0, 0, 520, 180))
        if name == "英雄派遣-英雄-全部-已完成" and current["name"] == "dispatch":
            return Detail(True, (210, 80, 130, 60))
        if name == "painting_page" and current["name"] == "painting":
            return Detail(True, (0, 0, 1280, 720))
        if name == "reset.home" and current["name"] == "home":
            return Detail(True, (850, 0, 430, 180))
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)
    original_tap = driver._controller_tap

    def tap(box):
        original_tap(box)
        current["name"] = "painting" if current["name"] == "dispatch" else "home"

    driver._controller_tap = tap

    assert driver.return_to_home() is True
    assert context.tasker.controller.clicks == [(1213, 43), (1213, 43)]


def test_maa_adapter_closes_collection_page_before_next_task():
    context = Context()
    current = {"name": "collection"}

    def recognize(name, image):
        if name == "采集部署-采集-页面" and current["name"] == "collection":
            return Detail(True, (0, 0, 420, 110))
        if name == "painting_page" and current["name"] == "painting":
            return Detail(True, (0, 0, 1280, 720))
        if name == "reset.home" and current["name"] == "home":
            return Detail(True, (850, 0, 430, 180))
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)
    original_tap = driver._controller_tap

    def tap(box):
        original_tap(box)
        current["name"] = "painting" if current["name"] == "collection" else "home"

    driver._controller_tap = tap

    assert driver.return_to_home() is True
    assert context.tasker.controller.clicks == [(1213, 43), (1213, 43)]


def test_maa_adapter_uses_live_painting_text_as_day_night_home_alias():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (850, 0, 430, 180))
        if name == "home.painting_scroll_text"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)

    evidence = driver.recognize(driver.capture(), ("home", "function_panel.open"))

    assert evidence.page_hits["home"] == 1
    assert evidence.page_hits["home.painting_scroll_text"] == 1


def test_maa_adapter_does_not_treat_home_painting_entry_as_painting_page():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (850, 0, 430, 180))
        if name == "home.painting_scroll_text"
        else Detail(True, (0, 0, 1280, 720))
        if name == "painting_page"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)

    evidence = driver.recognize(
        driver.capture(),
        ("home.painting_scroll_text", "painting_page"),
    )

    assert evidence.page_hits["home.painting_scroll_text"] == 1
    assert evidence.page_hits["painting_page"] == 0


def test_maa_adapter_select_yanwu_uses_calibrated_row_without_ocr_box():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (0, 0, 1280, 720))
        if name == "painting_page"
        else Detail(True, None)
        if name == "yanwu_world_tab"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    driver._last_action_id = "transfer_shadow_stage"
    frame = driver.capture()
    driver.recognize(frame, ("painting_page", "yanwu_world_tab"))

    driver.execute(
        ActionIntent(
            "select_yanwu_world",
            "painting_page",
            "yanwu_world_tab",
            input_kind=InputKind.CLICK,
        )
    )

    assert context.tasker.controller.clicks == [(200, 168)]


def test_maa_adapter_closes_recognized_painting_page_before_next_task():
    context = Context()
    current = {"name": "painting"}

    def recognize(name, image):
        if name == "painting_page" and current["name"] == "painting":
            current["name"] = "home"
            return Detail(True, (0, 0, 1280, 720))
        if name == "reset.home" and current["name"] == "home":
            return Detail(True, (850, 0, 430, 180))
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)

    assert driver.return_to_home() is True
    assert context.tasker.controller.clicks == [(1213, 43)]


def test_maa_adapter_closes_shadow_exploration_page_with_leave_control():
    context = Context()
    current = {"name": "exploration"}

    def recognize(name, image):
        if name == "shadow_exploration_page" and current["name"] == "exploration":
            return Detail(True, (850, 0, 400, 720))
        if name == "reset.shadow_leave" and current["name"] == "exploration":
            current["name"] = "home"
            return Detail(True, (1050, 580, 180, 100))
        if name == "reset.home" and current["name"] == "home":
            return Detail(True, (1040, 0, 240, 110))
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)

    assert driver.return_to_home() is True
    assert context.tasker.controller.clicks == [(1140, 630)]


def test_maa_adapter_closes_daily_page_before_next_task():
    context = Context()
    current = {"name": "daily"}

    def recognize(name, image):
        if name == "日常任务奖励-日常-页面" and current["name"] == "daily":
            return Detail(True, (0, 0, 620, 190))
        if name == "reset.daily_close" and current["name"] == "daily":
            return Detail(True, (1160, 0, 100, 100))
        if name == "reset.home" and current["name"] == "home":
            return Detail(True, (850, 0, 430, 180))
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)
    original_tap = driver._controller_tap

    def tap(box):
        original_tap(box)
        current["name"] = "home"

    driver._controller_tap = tap

    assert driver.return_to_home() is True
    assert context.tasker.controller.clicks == [(1210, 50)]


def test_maa_adapter_closes_battle_pass_rewards_before_next_task():
    context = Context()
    current = {"name": "rewards"}

    def recognize(name, image):
        if name == "战令奖励-战斗-战令-奖励" and current["name"] == "rewards":
            return Detail(True, (100, 230, 700, 430))
        if name == "战令奖励-战斗-战令-关闭" and current["name"] == "rewards":
            return Detail(True, (1180, 10, 70, 70))
        if name == "reset.home" and current["name"] == "home":
            return Detail(True, (850, 0, 430, 180))
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)
    original_tap = driver._controller_tap

    def tap(box):
        original_tap(box)
        current["name"] = "home"

    driver._controller_tap = tap

    assert driver.return_to_home() is True
    assert context.tasker.controller.clicks == [(1215, 45)]


def test_maa_adapter_cleans_battle_pass_offer_before_next_task():
    class OfferController(Controller):
        def __init__(self):
            super().__init__()
            self.surface = "offer"

        def post_screencap(self):
            image = np.zeros((720, 1280, 3), dtype=np.uint8)
            if self.surface == "offer":
                image[240:470, :] = (210, 230, 240)
            return Job(image)

    context = Context()
    controller = OfferController()
    context.tasker.controller = controller

    def recognize(name, image):
        if controller.surface == "page" and name in {
            "战令奖励-战斗-战令-页面",
            "战令奖励-战斗-战令-关闭",
        }:
            return Detail(True, (1180, 10, 70, 70))
        if controller.surface == "home" and name == "reset.home":
            return Detail(True, (1040, 0, 240, 110))
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)
    original_tap = driver._controller_tap

    def tap(box):
        original_tap(box)
        if controller.surface == "offer":
            controller.surface = "page"
        elif controller.surface == "page":
            controller.surface = "home"

    driver._controller_tap = tap

    assert driver.return_to_home() is True
    assert controller.clicks == [(1200, 670), (1215, 45)]


def test_maa_adapter_closes_appraisal_page_before_next_task():
    context = Context()
    current = {"name": "appraisal"}

    def recognize(name, image):
        if name == "免费鉴定-鉴定-页面" and current["name"] == "appraisal":
            return Detail(True, (0, 0, 500, 230))
        if name == "reset.modal_close" and current["name"] == "appraisal":
            return Detail(True, (1160, 0, 100, 100))
        if name == "reset.home" and current["name"] == "home":
            return Detail(True, (850, 0, 430, 180))
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)
    original_tap = driver._controller_tap

    def tap(box):
        original_tap(box)
        current["name"] = "home"

    driver._controller_tap = tap

    assert driver.return_to_home() is True
    assert context.tasker.controller.clicks == [(1210, 50)]


def test_maa_adapter_closes_appraisal_page_with_daily_close_target():
    context = Context()
    current = {"name": "appraisal"}

    def recognize(name, image):
        if name == "免费鉴定-鉴定-页面" and current["name"] == "appraisal":
            return Detail(True, (0, 0, 500, 230))
        if name == "reset.daily_close" and current["name"] == "appraisal":
            return Detail(True, (1160, 0, 100, 100))
        if name == "reset.home" and current["name"] == "home":
            return Detail(True, (850, 0, 430, 180))
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)
    original_tap = driver._controller_tap

    def tap(box):
        original_tap(box)
        current["name"] = "home"

    driver._controller_tap = tap

    assert driver.return_to_home() is True
    assert context.tasker.controller.clicks == [(1210, 50)]


def test_collection_reward_close_waits_for_home_renderer(monkeypatch):
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (0, 0, 1280, 720))
        if name == "采集部署-采集-奖励-弹窗"
        else Detail(True, (1150, 620, 100, 100))
        if name == "采集部署-采集-弹窗-关闭"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    monkeypatch.setattr("agent.workflows.maa_android.monotonic", lambda: 100.0)
    frame = driver.capture()
    driver.recognize(
        frame,
        ("采集部署-采集-奖励-弹窗", "采集部署-采集-弹窗-关闭"),
    )

    driver.execute(
        ActionIntent(
            "close_reward_popup",
            "采集部署-采集-奖励-弹窗",
            "采集部署-采集-弹窗-关闭",
            input_kind=InputKind.CLICK,
        )
    )

    assert driver._settle_until == 110.0


def test_open_shop_waits_through_android_page_transition(monkeypatch):
    context = Context()
    driver = MaaAndroidWorkflowDriver(context)
    monkeypatch.setattr("agent.workflows.maa_android.monotonic", lambda: 100.0)
    frame = driver.capture()
    driver.recognize(frame, ("function_panel.page", "商店免费礼包-商店-页面"))
    driver._boxes["商店免费礼包-商店-页面"] = (frame.frame_id, (0, 0, 1280, 720))

    driver.execute(
        ActionIntent(
            "open_shop",
            "function_panel.page",
            "商店免费礼包-商店-页面",
            input_kind=InputKind.CLICK,
        )
    )

    assert driver._settle_until == 103.0


def test_shop_close_uses_same_frame_shop_page_fallback():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (0, 0, 300, 100))
        if name == "商店免费礼包-商店-页面"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)

    evidence = driver.recognize(
        driver.capture(),
        ("商店免费礼包-商店-页面", "商店免费礼包-商店-关闭"),
    )

    assert evidence.page_hits["商店免费礼包-商店-页面"] == 1
    assert evidence.target_hits["商店免费礼包-商店-关闭"] == 1
    assert driver._boxes["商店免费礼包-商店-关闭"][1] == (1160, 0, 100, 100)


def test_shadow_foreground_move_waits_for_loading_transition(monkeypatch):
    context = Context()
    driver = MaaAndroidWorkflowDriver(context)
    monkeypatch.setattr("agent.workflows.maa_android.monotonic", lambda: 100.0)
    frame = driver.capture()
    driver.recognize(frame, ("shadow_exploration_page", "shadow_foreground_left"))
    driver._boxes["shadow_foreground_left"] = (frame.frame_id, (280, 535, 300, 25))

    driver.execute(
        ActionIntent(
            "move_shadow_foreground_left",
            "shadow_exploration_page",
            "shadow_foreground_left",
            input_kind=InputKind.CLICK,
        )
    )

    assert driver._settle_until == 108.0


def test_shadow_transfer_sheet_overrides_ambiguous_exploration_markers():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (900, 0, 300, 120))
        if name == "shadow_exploration_page"
        else Detail(True, (0, 0, 1280, 720))
        if name in {"shadow_stage_any", "shadow_progress_any"}
        else Detail(True, (378, 608, 60, 35))
        if name in {"shadow_transfer_page", "shadow_confirm_transfer"}
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    driver._last_action_id = "transfer_shadow_stage"
    frame = driver.capture()

    evidence = driver.recognize(
        frame,
        (
            "shadow_exploration_page",
            "shadow_stage_any",
            "shadow_progress_any",
            "shadow_transfer_page",
            "shadow_confirm_transfer",
        ),
    )

    assert evidence.page_hits["shadow_transfer_page"] == 1
    assert evidence.target_hits["shadow_confirm_transfer"] == 1
    assert evidence.page_hits["shadow_exploration_page"] == 0
    assert evidence.page_hits["shadow_stage_any"] == 0
    assert evidence.page_hits["shadow_progress_any"] == 0
    assert driver._boxes["shadow_confirm_transfer"] == (
        frame.frame_id,
        (378, 608, 60, 35),
    )


def test_shadow_left_transfer_layout_wins_over_false_right_layout_ocr():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (378, 608, 60, 35))
        if name in {"shadow_transfer_page", "shadow_confirm_transfer"}
        else Detail(True, (900, 560, 360, 160))
        if name in {"shadow_transfer_right_page", "shadow_confirm_transfer_right"}
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    driver._last_action_id = "transfer_shadow_stage"
    frame = driver.capture()

    evidence = driver.recognize(
        frame,
        (
            "shadow_transfer_page",
            "shadow_confirm_transfer",
            "shadow_transfer_right_page",
            "shadow_confirm_transfer_right",
        ),
    )

    assert evidence.page_hits["shadow_transfer_page"] == 1
    assert evidence.target_hits["shadow_confirm_transfer"] == 1
    assert evidence.page_hits["shadow_transfer_right_page"] == 0
    assert evidence.target_hits["shadow_confirm_transfer_right"] == 0
    assert "shadow_confirm_transfer_right" not in driver._boxes


def test_shadow_left_transfer_layout_visual_fallback_wins_when_left_ocr_misses():
    context = Context()
    image = np.zeros((720, 1280, 3), dtype=np.uint8)
    image[545:710, 320:500] = (20, 70, 180)
    context.tasker.controller.post_screencap = lambda: Job(image)
    context.run_recognition = lambda name, current: (
        Detail(True, (900, 560, 360, 160))
        if name in {"shadow_transfer_right_page", "shadow_confirm_transfer_right"}
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    driver._last_action_id = "transfer_shadow_stage"
    frame = driver.capture()
    evidence = driver.recognize(
        frame,
        (
            "shadow_transfer_page",
            "shadow_confirm_transfer",
            "shadow_transfer_right_page",
            "shadow_confirm_transfer_right",
        ),
    )

    assert evidence.page_hits["shadow_transfer_page"] == 1
    assert evidence.target_hits["shadow_confirm_transfer"] == 1
    assert evidence.page_hits["shadow_transfer_right_page"] == 0
    assert evidence.target_hits["shadow_confirm_transfer_right"] == 0
    assert driver._boxes["shadow_confirm_transfer"] == (
        frame.frame_id,
        (330, 560, 170, 140),
    )


def test_shadow_transfer_confirmation_clicks_live_ocr_box():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (378, 608, 60, 35))
        if name == "shadow_confirm_transfer"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    driver._last_action_id = "transfer_shadow_stage"
    frame = driver.capture()
    driver.recognize(frame, ("shadow_transfer_page", "shadow_confirm_transfer"))

    driver.execute(
        ActionIntent(
            "confirm_shadow_transfer",
            "shadow_transfer_page",
            "shadow_confirm_transfer",
            input_kind=InputKind.CLICK,
        )
    )

    assert context.tasker.controller.clicks == []
    assert context.tasker.controller.swipes == [(408, 626, 409, 627, 100)]


def test_shadow_exploration_transfer_button_is_not_a_transfer_sheet():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (940, 625, 125, 45))
        if name in {"shadow_transfer_right_page", "shadow_confirm_transfer_right"}
        else Detail(True, (850, 0, 400, 720))
        if name == "shadow_exploration_page"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    driver._last_action_id = "enter_shadow_stage"
    frame = driver.capture()

    evidence = driver.recognize(
        frame,
        (
            "shadow_exploration_page",
            "shadow_transfer_right_page",
            "shadow_confirm_transfer_right",
        ),
    )

    assert evidence.page_hits["shadow_exploration_page"] == 1
    assert evidence.page_hits["shadow_transfer_right_page"] == 0
    assert evidence.target_hits["shadow_confirm_transfer_right"] == 0
    assert "shadow_confirm_transfer_right" not in driver._boxes


def test_shadow_right_transfer_marker_requires_transfer_action_context():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (940, 625, 125, 45))
        if name in {"shadow_transfer_right_page", "shadow_confirm_transfer_right"}
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    driver._last_action_id = "enter_shadow_stage"
    frame = driver.capture()

    evidence = driver.recognize(
        frame,
        ("shadow_transfer_right_page", "shadow_confirm_transfer_right"),
    )

    assert evidence.page_hits["shadow_transfer_right_page"] == 0
    assert evidence.target_hits["shadow_confirm_transfer_right"] == 0


def test_shadow_recommended_team_use_uses_unity_drag_tap():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (1064, 593, 130, 43))
        if name == "shadow_use_recommended_team"
        else Detail(True, (40, 10, 120, 60))
        if name == "shadow_recommended_team_page"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    frame = driver.capture()
    driver.recognize(
        frame,
        ("shadow_recommended_team_page", "shadow_use_recommended_team"),
    )

    driver.execute(
        ActionIntent(
            "use_shadow_recommended_team",
            "shadow_recommended_team_page",
            "shadow_use_recommended_team",
            input_kind=InputKind.CLICK,
        )
    )

    assert context.tasker.controller.clicks == []
    assert context.tasker.controller.swipes == [(1129, 615, 1130, 616, 100)]


def test_shadow_foreground_anchors_scale_computer_use_coordinates():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (0, 0, 1280, 720))
        if name == "shadow_exploration_page"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    frame = driver.capture()
    driver.recognize(
        frame,
        (
            "shadow_exploration_page",
            "shadow_foreground_left",
            "shadow_foreground_center",
            "shadow_foreground_right",
        ),
    )

    assert driver._boxes["shadow_foreground_left"][1] == (436, 536, 24, 24)
    assert driver._boxes["shadow_foreground_center"][1] == (629, 536, 24, 24)
    assert driver._boxes["shadow_foreground_right"][1] == (822, 536, 24, 24)


def test_shadow_foreground_action_clicks_three_current_frame_anchors_in_order(monkeypatch):
    context = Context()
    driver = MaaAndroidWorkflowDriver(context)
    monkeypatch.setattr("agent.workflows.maa_android.monotonic", lambda: 100.0)
    monkeypatch.setattr("agent.workflows.maa_android.sleep", lambda _: None)
    frame = driver.capture()
    driver._boxes["shadow_foreground_left"] = (frame.frame_id, (436, 536, 24, 24))
    driver._boxes["shadow_foreground_center"] = (frame.frame_id, (629, 536, 24, 24))
    driver._boxes["shadow_foreground_right"] = (frame.frame_id, (822, 536, 24, 24))
    driver.execute(
        ActionIntent(
            "advance_shadow_foreground_triplet",
            "shadow_exploration_page",
            "shadow_foreground_left",
            input_kind=InputKind.CLICK,
        )
    )

    assert context.tasker.controller.clicks == [(448, 548), (641, 548), (834, 548)]
    assert context.tasker.controller.touches == []
    assert driver._settle_until == 108.0


def test_shadow_grid_advanced_requires_a_real_grid_change():
    context = Context()
    driver = MaaAndroidWorkflowDriver(context)
    frame = driver.capture()
    driver._last_action_id = "advance_shadow_foreground_triplet"
    driver._shadow_move_baseline = frame.payload.copy()

    unchanged = driver.recognize(frame, ("shadow_grid_advanced",))
    assert unchanged.page_hits.get("shadow_grid_advanced", 0) == 0

    changed = frame.payload.copy()
    changed[360:560, 400:800] = 255
    next_frame = type(frame)("maa-android:next", frame.size, changed)
    driver._last_frame_id = next_frame.frame_id
    first_observation = driver.recognize(next_frame, ("shadow_grid_advanced",))
    assert first_observation.page_hits.get("shadow_grid_advanced", 0) == 0
    second_observation = driver.recognize(next_frame, ("shadow_grid_advanced",))
    assert second_observation.page_hits["shadow_grid_advanced"] == 1


def test_shadow_foreground_move_retries_same_frame_network_timeout(monkeypatch):
    context = Context()
    timeout_frames = iter((True, False))

    def recognize(name, image):
        if name == "reset.network_timeout":
            return Detail(next(timeout_frames), (450, 180, 460, 300))
        if name == "reset.network_retry":
            return Detail(True, (844, 334, 60, 164))
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)
    monkeypatch.setattr("agent.workflows.maa_android.sleep", lambda _: None)
    driver._last_frame_id = "frame-1"
    driver._last_frame_payload = np.zeros((720, 1280, 3), dtype=np.uint8)
    for marker, box in {
        "shadow_foreground_left": (436, 536, 24, 24),
        "shadow_foreground_center": (629, 536, 24, 24),
        "shadow_foreground_right": (822, 536, 24, 24),
    }.items():
        driver._boxes[marker] = ("frame-1", box)

    driver.execute(
        ActionIntent(
            "advance_shadow_foreground_triplet",
            "shadow_exploration_page",
            "shadow_foreground_left",
            input_kind=InputKind.CLICK,
        )
    )

    assert context.tasker.controller.clicks[:3] == [(448, 548), (641, 548), (834, 548)]
    assert context.tasker.controller.clicks[3] == (874, 416)


def test_shadow_grid_advanced_detects_upper_card_scroll():
    context = Context()
    driver = MaaAndroidWorkflowDriver(context)
    frame = driver.capture()
    driver._last_action_id = "advance_shadow_foreground_triplet"
    driver._shadow_move_baseline = frame.payload.copy()

    # A one-row scroll can change the upper card stack while the lower
    # foreground row remains almost identical. This region is intentionally
    # above the old y=300 detector boundary.
    changed = frame.payload.copy()
    changed[200:280, 500:750] = 255
    next_frame = type(frame)("maa-android:upper-scroll", frame.size, changed)
    driver._last_frame_id = next_frame.frame_id

    first_observation = driver.recognize(next_frame, ("shadow_grid_advanced",))
    assert first_observation.page_hits.get("shadow_grid_advanced", 0) == 0
    second_observation = driver.recognize(next_frame, ("shadow_grid_advanced",))
    assert second_observation.page_hits["shadow_grid_advanced"] == 1


def test_shadow_grid_advanced_accepts_subtle_upper_card_scroll():
    context = Context()
    driver = MaaAndroidWorkflowDriver(context)
    frame = driver.capture()
    driver._last_action_id = "advance_shadow_foreground_triplet"
    driver._shadow_move_baseline = frame.payload.copy()

    # This models the live second-layer trace: only a small upper-card band
    # changes, so the old 2%/0.8 thresholds rejected a real one-row move after
    # downsampling.  It is intentionally below those old thresholds.
    changed = frame.payload.copy()
    changed[230:326, 552:720:4] = 40
    next_frame = type(frame)("maa-android:subtle-upper-scroll", frame.size, changed)
    driver._last_frame_id = next_frame.frame_id

    first_observation = driver.recognize(next_frame, ("shadow_grid_advanced",))
    assert first_observation.page_hits.get("shadow_grid_advanced", 0) == 0
    second_observation = driver.recognize(next_frame, ("shadow_grid_advanced",))
    assert second_observation.page_hits["shadow_grid_advanced"] == 1


def test_weekly_must_buy_fallback_targets_top_tab_strip():
    context = Context()

    def recognize(name, image):
        if name == "周一免费礼包-商店-礼包-标签-页面":
            return Detail(True, (0, 100, 1280, 620))
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)
    frame = driver.capture()
    evidence = driver.recognize(
        frame,
        ("周一免费礼包-商店-礼包-标签-页面", "周一免费礼包-商店-每周-必须-购买"),
    )

    assert evidence.target_hits["周一免费礼包-商店-每周-必须-购买"] == 1
    assert driver._boxes["周一免费礼包-商店-每周-必须-购买"][1] == (500, 70, 160, 80)


def test_shadow_battle_uses_short_initial_settle_before_engine_ocr_polling(monkeypatch):
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (0, 0, 1280, 720))
        if name in {"shadow_stage_page", "shadow_speed_enabled", "shadow_auto_enabled"}
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    monkeypatch.setattr("agent.workflows.maa_android.monotonic", lambda: 100.0)
    frame = driver.capture()
    driver.recognize(frame, ("shadow_stage_any", "shadow_battle_target"))
    driver._boxes["shadow_battle_target"] = (frame.frame_id, (700, 450, 500, 230))

    driver.execute(
        ActionIntent(
            "battle",
            "shadow_stage_any",
            "shadow_battle_target",
            input_kind=InputKind.CLICK,
        )
    )

    assert driver._settle_until == 103.0


def test_shadow_battle_waits_through_black_loading_frame(monkeypatch):
    context = Context()
    driver = MaaAndroidWorkflowDriver(context)
    frames = [
        type("Frame", (), {"frame_id": "loading"})(),
        type("Frame", (), {"frame_id": "battle"})(),
    ]
    evidence = [
        VisualEvidence("loading", {}, {}, {}, {}),
        VisualEvidence(
            "battle",
            {"shadow_stage_page": 1},
            {"shadow_speed_enabled": 1, "shadow_auto_enabled": 1},
            {},
            {},
        ),
    ]
    captures = iter(frames)
    recognitions = iter(evidence)
    monkeypatch.setattr(driver, "capture", lambda: next(captures))
    monkeypatch.setattr(
        driver,
        "recognize",
        lambda frame, names: next(recognitions),
    )
    monkeypatch.setattr("agent.workflows.maa_android.monotonic", lambda: 100.0)

    driver._ensure_shadow_battle_modes()

    assert driver._settle_until == 102.0


def test_shadow_battle_enables_only_missing_auto_mode(monkeypatch):
    state = {"auto": False}

    class ModeController(Controller):
        def post_click(self, x, y):
            if 1110 <= x <= 1190 and 20 <= y <= 90:
                state["auto"] = True
            return super().post_click(x, y)

    context = Context()
    context.tasker.controller = ModeController()

    def recognize(name, image):
        if name == "shadow_stage_page":
            return Detail(True, (0, 0, 1280, 720))
        if name == "shadow_speed_enabled":
            return Detail(True, (1035, 20, 110, 70))
        if name == "shadow_auto_enabled":
            return Detail(state["auto"], (1110, 20, 80, 70) if state["auto"] else None)
        if name == "shadow_auto_toggle":
            return Detail(not state["auto"], (1110, 20, 80, 70) if not state["auto"] else None)
        return Detail(False, None)

    context.run_recognition = recognize
    monkeypatch.setattr("agent.workflows.maa_android.sleep", lambda _: None)
    driver = MaaAndroidWorkflowDriver(context)
    frame = driver.capture()
    driver._boxes["shadow_battle_target"] = (frame.frame_id, (700, 450, 500, 230))

    driver.execute(
        ActionIntent(
            "battle",
            "shadow_stage_any",
            "shadow_battle_target",
            input_kind=InputKind.CLICK,
        )
    )

    assert context.tasker.controller.clicks == [(950, 565), (1150, 55)]


def test_shadow_battle_result_dismisses_from_blank_center_not_leave_control():
    context = Context()
    driver = MaaAndroidWorkflowDriver(context)
    frame = driver.capture()
    driver._boxes["shadow_battle_result"] = (frame.frame_id, (650, 0, 630, 240))

    driver.execute(
        ActionIntent(
            "dismiss_shadow_battle_result",
            "shadow_battle_result",
            "shadow_battle_result",
            input_kind=InputKind.CLICK,
        )
    )

    assert context.tasker.controller.clicks == [(640, 660)]


def test_shadow_reward_popup_dismisses_from_blank_center(monkeypatch):
    context = Context()
    driver = MaaAndroidWorkflowDriver(context)
    monkeypatch.setattr("agent.workflows.maa_android.monotonic", lambda: 100.0)
    frame = driver.capture()
    driver._boxes["shadow_reward_popup"] = (
        frame.frame_id,
        (0, 100, 1280, 620),
    )

    driver.execute(
        ActionIntent(
            "dismiss_shadow_reward_popup",
            "shadow_reward_popup",
            "shadow_reward_popup",
            input_kind=InputKind.CLICK,
        )
    )

    assert context.tasker.controller.clicks == [(640, 660)]
    assert driver._settle_until == 108.0


def test_trial_free_confirmation_taps_inside_live_confirm_button():
    context = Context()
    driver = MaaAndroidWorkflowDriver(context)
    frame = driver.capture()
    driver._boxes["试剑-试炼-免费-确认"] = (
        frame.frame_id,
        (780, 440, 220, 120),
    )

    driver.execute(
        ActionIntent(
            "confirm_free_trial",
            "试剑-试炼-免费-弹窗",
            "试剑-试炼-免费-确认",
            input_kind=InputKind.CLICK,
        )
    )

    assert context.tasker.controller.clicks == [(880, 500)]


def test_trial_reward_page_supplies_safe_blank_close_target_when_ocr_misses():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (0, 120, 1280, 520))
        if name == "试剑-试炼-奖励-弹窗"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    frame = driver.capture()

    evidence = driver.recognize(
        frame,
        ("试剑-试炼-奖励-弹窗", "试剑-试炼-弹窗-关闭"),
    )

    assert evidence.page_hits["试剑-试炼-奖励-弹窗"] == 1
    assert evidence.target_hits["试剑-试炼-弹窗-关闭"] == 1
    assert driver._boxes["试剑-试炼-弹窗-关闭"] == (
        frame.frame_id,
        (350, 580, 600, 140),
    )


def test_trial_free_claim_fallback_is_bound_to_closed_reward_popup():
    context = Context()

    def recognize(name, image):
        if name == "试剑-试炼-页面":
            return Detail(True, (0, 160, 500, 300))
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)
    driver._last_action_id = "close_reward_popup"
    evidence = driver.recognize(
        driver.capture(),
        ("试剑-试炼-页面", "试剑-试炼-免费-领取", "trial.current_reward_zero"),
    )

    assert evidence.page_hits["试剑-试炼-页面"] == 1
    assert evidence.target_hits["试剑-试炼-免费-领取"] == 1
    assert "免费" in evidence.texts
    assert driver._boxes["试剑-试炼-免费-领取"] == (
        driver._last_frame_id,
        (270, 600, 100, 100),
    )


def test_trial_confirmed_close_without_strict_free_used_proof_stays_unknown():
    context = Context()

    def recognize(name, image):
        if name == "试剑-试炼-页面":
            return Detail(True, (0, 160, 500, 300))
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)
    driver._last_action_id = "close_reward_popup"
    driver._trial_free_confirmed = True
    evidence = driver.recognize(
        driver.capture(),
        (
            "试剑-试炼-页面",
            "trial.free_waiting",
            "trial.free_used",
            "trial.current_reward_zero",
        ),
    )

    assert evidence.target_hits["trial.free_used"] == 0


def test_trial_strict_free_used_state_suppresses_stale_claim_controls():
    context = Context()

    def recognize(name, image):
        if name == "试剑-试炼-页面":
            return Detail(True, (30, 267, 106, 27))
        if name == "trial.free_used":
            return Detail(True, (1000, 638, 188, 29))
        if name in {
            "试剑-试炼-奖励-领取",
            "trial.current_reward_claim",
            "试剑-试炼-免费-领取",
        }:
            return Detail(True, (180, 632, 58, 34))
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)
    evidence = driver.recognize(
        driver.capture(),
        (
            "试剑-试炼-页面",
            "trial.free_used",
            "试剑-试炼-奖励-领取",
            "trial.current_reward_claim",
            "试剑-试炼-免费-领取",
        ),
    )

    assert evidence.target_hits["trial.free_used"] == 1
    assert evidence.target_hits["试剑-试炼-奖励-领取"] == 0
    assert evidence.target_hits["trial.current_reward_claim"] == 0
    assert evidence.target_hits["试剑-试炼-免费-领取"] == 0


def test_shadow_formation_supplies_stable_battle_button_when_ocr_misses():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (450, 0, 420, 100))
        if name == "shadow_formation_page"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    frame = driver.capture()

    evidence = driver.recognize(
        frame,
        ("shadow_formation_page", "shadow_battle_target"),
    )

    assert evidence.page_hits["shadow_formation_page"] == 1
    assert evidence.target_hits["shadow_battle_target"] == 1
    assert driver._boxes["shadow_battle_target"] == (
        frame.frame_id,
        (1090, 545, 175, 175),
    )


def test_shadow_formation_visual_boundary_overrides_exploration_misrecognition():
    context = Context()

    def recognize(name, image):
        if name == "shadow_exploration_page":
            return Detail(True, (850, 0, 400, 720))
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)
    driver._last_action_id = "advance_shadow_foreground_triplet"
    frame = driver.capture()
    image = frame.payload.copy()
    # Model the live lower-right blue 开战 control while the title and its
    # OCR target are absent. The page body remains dark, as on the Android
    # formation surface.
    image[545:710, 1060:1280] = (30, 100, 220)
    frame = type(frame)("maa-android:formation", frame.size, image)
    driver._last_frame_id = frame.frame_id

    evidence = driver.recognize(
        frame,
        (
            "shadow_exploration_page",
            "shadow_formation_page",
            "shadow_battle_target",
            "shadow_foreground_left",
            "shadow_grid_advanced",
        ),
    )

    assert evidence.page_hits["shadow_formation_page"] == 1
    assert evidence.target_hits["shadow_battle_target"] == 1
    assert evidence.page_hits["shadow_exploration_page"] == 0
    assert evidence.target_hits["shadow_foreground_left"] == 0
    assert evidence.page_hits["shadow_grid_advanced"] == 1


def test_shadow_formation_supplies_recommended_team_button():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (450, 0, 420, 100))
        if name == "shadow_formation_page"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    frame = driver.capture()

    evidence = driver.recognize(
        frame,
        ("shadow_formation_page", "shadow_recommended_team"),
    )

    assert evidence.target_hits["shadow_recommended_team"] == 1
    assert driver._boxes["shadow_recommended_team"] == (
        frame.frame_id,
        (190, 0, 150, 80),
    )


def test_shadow_recommended_team_page_supplies_use_button_when_ocr_misses():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (40, 10, 120, 60))
        if name == "shadow_recommended_team_page"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    frame = driver.capture()

    evidence = driver.recognize(
        frame,
        ("shadow_recommended_team_page", "shadow_use_recommended_team"),
    )

    assert evidence.page_hits["shadow_recommended_team_page"] == 1
    assert evidence.target_hits["shadow_use_recommended_team"] == 1
    assert driver._boxes["shadow_use_recommended_team"] == (
        frame.frame_id,
        (1020, 550, 240, 150),
    )


def test_shadow_reward_popup_uses_visual_sheet_when_transition_ocr_misses():
    class RewardController(Controller):
        def post_screencap(self):
            image = np.zeros((720, 1280, 3), dtype=np.uint8)
            image[240:470, :] = 230
            return Job(image)

    context = Context()
    context.tasker.controller = RewardController()
    context.run_recognition = lambda name, image: Detail(False, None)
    driver = MaaAndroidWorkflowDriver(context)
    driver._last_action_id = "advance_shadow_foreground_triplet"
    frame = driver.capture()

    evidence = driver.recognize(frame, ("shadow_reward_popup",))

    assert evidence.page_hits["shadow_reward_popup"] == 1
    assert evidence.target_hits["shadow_reward_popup"] == 1
    assert driver._boxes["shadow_reward_popup"] == (
        frame.frame_id,
        (0, 100, 1280, 620),
    )


def test_claim_reward_popup_uses_visual_sheet_when_ocr_returns_nothing():
    class RewardController(Controller):
        def post_screencap(self):
            image = np.zeros((720, 1280, 3), dtype=np.uint8)
            image[240:470, :] = (210, 230, 240)
            return Job(image)

    context = Context()
    context.tasker.controller = RewardController()
    context.run_recognition = lambda name, image: Detail(False, None)
    driver = MaaAndroidWorkflowDriver(context)
    driver._last_action_id = "claim_completed_daily_row"
    frame = driver.capture()

    evidence = driver.recognize(
        frame,
        ("日常任务奖励-日常-奖励-弹窗", "日常任务奖励-日常-奖励-弹窗-关闭"),
    )

    assert evidence.page_hits["日常任务奖励-日常-奖励-弹窗"] == 1
    assert evidence.target_hits["日常任务奖励-日常-奖励-弹窗-关闭"] == 1
    assert driver._boxes["日常任务奖励-日常-奖励-弹窗-关闭"] == (
        frame.frame_id,
        (300, 560, 700, 160),
    )


def test_hero_claim_reward_popup_uses_visual_sheet_when_ocr_returns_nothing():
    class RewardController(Controller):
        def post_screencap(self):
            image = np.zeros((720, 1280, 3), dtype=np.uint8)
            image[240:470, :] = (210, 230, 240)
            return Job(image)

    context = Context()
    context.tasker.controller = RewardController()
    context.run_recognition = lambda name, image: Detail(False, None)
    driver = MaaAndroidWorkflowDriver(context)
    driver._last_action_id = "claim_first_dispatch"
    frame = driver.capture()

    evidence = driver.recognize(
        frame,
        ("英雄派遣-英雄-奖励-弹窗", "英雄派遣-英雄-奖励-弹窗-关闭"),
    )

    assert evidence.page_hits["英雄派遣-英雄-奖励-弹窗"] == 1
    assert evidence.target_hits["英雄派遣-英雄-奖励-弹窗-关闭"] == 1


def test_battle_pass_tasks_page_does_not_become_visual_reward_popup():
    class TasksController(Controller):
        def post_screencap(self):
            image = np.zeros((720, 1280, 3), dtype=np.uint8)
            image[180:540, 400:880] = (210, 230, 240)
            image[350:530, 420:860] = (220, 235, 245)
            return Job(image)

    context = Context()
    context.tasker.controller = TasksController()
    context.run_recognition = lambda name, image: (
        Detail(True, (0, 120, 520, 180))
        if name == "战令奖励-战斗-战令-任务"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    driver._last_action_id = "open_battle_pass_tasks"
    evidence = driver.recognize(
        driver.capture(),
        ("战令奖励-战斗-战令-任务", "战令奖励-战斗-战令-奖励-弹窗", "战令奖励-战斗-战令-奖励-弹窗-关闭"),
    )

    assert evidence.page_hits["战令奖励-战斗-战令-任务"] == 1
    assert evidence.page_hits.get("战令奖励-战斗-战令-奖励-弹窗", 0) == 0
    assert evidence.target_hits.get("战令奖励-战斗-战令-奖励-弹窗-关闭", 0) == 0


def test_battle_pass_item_detail_is_a_reward_popup_with_safe_close():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (450, 190, 440, 330))
        if name == "战令奖励-战斗-战令-物品-弹窗"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    frame = driver.capture()
    evidence = driver.recognize(
        frame,
        (
            "战令奖励-战斗-战令-物品-弹窗",
            "战令奖励-战斗-战令-奖励-弹窗",
            "战令奖励-战斗-战令-奖励-弹窗-关闭",
        ),
    )

    assert evidence.page_hits["战令奖励-战斗-战令-奖励-弹窗"] == 1
    assert evidence.target_hits["战令奖励-战斗-战令-奖励-弹窗-关闭"] == 1
    assert driver._boxes["战令奖励-战斗-战令-奖励-弹窗-关闭"] == (
        frame.frame_id,
        (300, 560, 700, 160),
    )


def test_battle_pass_rewards_without_basic_red_dot_proves_basic_track_complete():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (100, 230, 700, 430))
        if name == "战令奖励-战斗-战令-奖励"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    evidence = driver.recognize(
        driver.capture(),
        (
            "战令奖励-战斗-战令-奖励",
            "战令奖励-战斗-战令-基础-红色-红点-奖励",
            "战令奖励-战斗-战令-基础-全部已领取",
        ),
    )

    assert evidence.target_hits["战令奖励-战斗-战令-基础-全部已领取"] == 1
    assert driver._boxes["战令奖励-战斗-战令-基础-全部已领取"][1] == (150, 320, 700, 150)


def test_shadow_stage_entry_taps_live_ocr_box_not_grid_anchor():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (850, 490, 80, 50))
        if name == "shadow_go"
        else Detail(True, (280, 130, 740, 450))
        if name == "shadow_popup"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    frame = driver.capture()
    driver.recognize(frame, ("shadow_popup", "shadow_go"))

    driver.execute(
        ActionIntent(
            "enter_shadow_stage",
            "shadow_popup",
            "shadow_go",
            input_kind=InputKind.CLICK,
        )
    )

    assert context.tasker.controller.clicks == []
    assert context.tasker.controller.swipes == [(890, 515, 891, 516, 100)]


def test_hero_dispatch_uses_calibrated_interior_box_after_live_ocr_authorization():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (0, 0, 1280, 720))
        if name == "painting_page"
        else Detail(
            True,
            (1005, 640, 100, 40),
            results=(OcrResult("侠客派遣"),),
        )
        if name == "hero_dispatch_entry"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    frame = driver.capture()
    evidence = driver.recognize(frame, ("painting_page", "hero_dispatch_entry"))
    assert evidence.target_hits["hero_dispatch_entry"] == 1

    driver.execute(
        ActionIntent(
            "open_hero_dispatch",
            "painting_page",
            "hero_dispatch_entry",
            input_kind=InputKind.CLICK,
        )
    )

    assert context.tasker.controller.clicks == [(1050, 625)]


def test_hero_dispatch_uses_painting_bounded_fallback_when_ocr_misses():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (0, 0, 1280, 720))
        if name == "painting_page"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    frame = driver.capture()

    evidence = driver.recognize(frame, ("painting_page", "hero_dispatch_entry"))

    assert evidence.target_hits["hero_dispatch_entry"] == 1
    driver.execute(
        ActionIntent(
            "open_hero_dispatch",
            "painting_page",
            "hero_dispatch_entry",
            input_kind=InputKind.CLICK,
        )
    )
    assert context.tasker.controller.clicks == [(1050, 625)]


def test_hero_dispatch_close_uses_page_bounded_adb_target_when_template_misses():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (0, 0, 1280, 720))
        if name == "英雄派遣-英雄-派遣-页面"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    frame = driver.capture()
    evidence = driver.recognize(frame, ("英雄派遣-英雄-派遣-页面", "英雄派遣-英雄-派遣-关闭"))

    assert evidence.target_hits["英雄派遣-英雄-派遣-关闭"] == 1
    driver.execute(
        ActionIntent(
            "close_hero_dispatch",
            "英雄派遣-英雄-派遣-页面",
            "英雄派遣-英雄-派遣-关闭",
            input_kind=InputKind.CLICK,
        )
    )
    assert context.tasker.controller.clicks == [(1213, 43)]


def test_hero_dispatch_selection_recovers_claim_button_when_ocr_misses():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (0, 0, 520, 180))
        if name == "英雄派遣-英雄-派遣-页面"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    driver._last_action_id = "select_first_visible_dispatch"
    frame = driver.capture()

    evidence = driver.recognize(frame, ("英雄派遣-英雄-派遣-页面", "英雄派遣-英雄-领取-按钮"))

    assert evidence.page_hits["英雄派遣-英雄-派遣-页面"] == 1
    assert evidence.target_hits["英雄派遣-英雄-领取-按钮"] == 1
    assert driver._boxes["英雄派遣-英雄-领取-按钮"] == (
        frame.frame_id,
        (950, 520, 300, 100),
    )


def test_hero_dispatch_promotes_page_from_authorized_close_template_when_title_ocr_misses():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (1190, 20, 44, 44))
        if name == "英雄派遣-英雄-派遣-关闭"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    driver._last_action_id = "open_hero_dispatch"

    frame = driver.capture()
    evidence = driver.recognize(
        frame,
        ("英雄派遣-英雄-派遣-页面", "英雄派遣-英雄-派遣-关闭"),
    )

    assert evidence.page_hits["英雄派遣-英雄-派遣-页面"] == 1
    assert evidence.target_hits["英雄派遣-英雄-派遣-页面"] == 1
    assert driver._boxes["英雄派遣-英雄-派遣-页面"] == (
        frame.frame_id,
        (1190, 20, 44, 44),
    )


def test_maa_adapter_cleanup_requires_panel_marker_and_close(monkeypatch):
    context = Context()
    state = {"page": "panel"}
    context.run_recognition = lambda name, image: (
        Detail(True, (690, 0, 280, 160))
        if state["page"] == "panel" and name == "reset.function_panel"
        else Detail(True, (1180, 0, 100, 100))
        if state["page"] == "panel" and name == "reset.panel_close"
        else Detail(True, (1040, 0, 240, 110))
        if state["page"] == "home" and name == "reset.home"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    taps = []

    def click(box, *, frame_size=None):
        taps.append((box, frame_size))
        state["page"] = "home"

    monkeypatch.setattr(driver.gestures, "click", click)

    assert driver.return_to_home() is True
    assert taps == [((1180, 0, 100, 100), (1280, 720))]
    assert context.tasker.controller.clicks == []


def test_maa_adapter_falls_back_to_panel_close_when_template_misses(monkeypatch):
    context = Context()
    state = {"page": "panel"}

    def recognize(name, image):
        if state["page"] == "panel" and name == "reset.function_panel":
            return Detail(True, (690, 0, 280, 160))
        if state["page"] == "home" and name == "reset.home":
            return Detail(True, (1040, 0, 240, 110))
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)

    def click(box, *, frame_size=None):
        state["page"] = "home"

    monkeypatch.setattr(driver.gestures, "click", click)

    assert driver.return_to_home() is True


def test_maa_adapter_cleanup_closes_martial_page_before_next_task(monkeypatch):
    context = Context()
    state = {"page": "martial"}

    def recognize(name, image):
        if state["page"] == "martial" and name == "martial_page":
            return Detail(True, (0, 0, 1280, 720))
        if state["page"] == "martial" and name == "martial_close":
            return Detail(True, (1160, 0, 100, 100))
        if state["page"] == "panel" and name == "reset.function_panel":
            return Detail(True, (690, 0, 280, 160))
        if state["page"] == "panel" and name == "reset.panel_close":
            return Detail(True, (1180, 0, 100, 100))
        if state["page"] == "home" and name == "reset.home":
            return Detail(True, (1040, 0, 240, 110))
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)
    taps = []
    keys = []

    def click(box, *, frame_size=None):
        taps.append((box, frame_size))
        state["page"] = "panel" if state["page"] == "martial" else "home"

    def click_key(key):
        keys.append(key)
        state["page"] = "panel"

    monkeypatch.setattr(driver.gestures, "click", click)
    monkeypatch.setattr(driver.gestures, "click_key", click_key)

    assert driver.return_to_home() is True
    assert taps == [
        ((1180, 0, 100, 100), (1280, 720)),
    ]
    assert keys == [4]
    assert context.tasker.controller.clicks == []


def test_maa_adapter_cleanup_closes_food_bag_before_next_task(monkeypatch):
    context = Context()
    state = {"page": "bag"}

    def recognize(name, image):
        if state["page"] == "bag" and name == "consumables_page":
            return Detail(True, (0, 0, 150, 100))
        if state["page"] == "bag" and name == "reset.modal_close":
            return Detail(True, (1160, 0, 100, 100))
        if state["page"] == "panel" and name == "reset.function_panel":
            return Detail(True, (690, 0, 280, 160))
        if state["page"] == "panel" and name == "reset.panel_close":
            return Detail(True, (1180, 0, 100, 100))
        if state["page"] == "home" and name == "reset.home":
            return Detail(True, (1040, 0, 240, 110))
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)
    taps = []

    def click(box, *, frame_size=None):
        taps.append((box, frame_size))
        state["page"] = "panel" if state["page"] == "bag" else "home"

    monkeypatch.setattr(driver.gestures, "click", click)

    assert driver.return_to_home() is True
    assert taps == [
        ((1160, 0, 100, 90), (1280, 720)),
        ((1180, 0, 100, 100), (1280, 720)),
    ]
    assert context.tasker.controller.clicks == []


def test_maa_adapter_cleanup_closes_jianlin_page_before_next_task(monkeypatch):
    context = Context()
    state = {"page": "jianlin"}

    def recognize(name, image):
        if state["page"] == "jianlin" and name == "jianlin_page":
            return Detail(True, (0, 0, 280, 100))
        if state["page"] == "jianlin" and name == "jianlin_page_close":
            return Detail(True, (1160, 0, 100, 90))
        if state["page"] == "home" and name == "reset.home":
            return Detail(True, (1040, 0, 240, 110))
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)
    taps = []

    def click(box, *, frame_size=None):
        taps.append((box, frame_size))
        state["page"] = "home"

    monkeypatch.setattr(driver.gestures, "click", click)

    assert driver.return_to_home() is True
    assert taps == [((1160, 0, 100, 90), (1280, 720))]
    assert context.tasker.controller.clicks == []


def test_maa_adapter_closes_blurred_appraisal_result_through_adb_controller():
    context = Context()
    driver = MaaAndroidWorkflowDriver(context)
    driver._last_action_id = "claim_free_appraisal_once"

    frame = driver.capture()
    evidence = driver.recognize(
        frame,
        ("免费鉴定-鉴定-结果-弹窗", "免费鉴定-鉴定-弹窗-关闭"),
    )

    assert evidence.page_hits["免费鉴定-鉴定-结果-弹窗"] == 1
    assert evidence.target_hits["免费鉴定-鉴定-弹窗-关闭"] == 1

    driver.execute(
        ActionIntent(
            "close_appraisal_popup",
            "免费鉴定-鉴定-结果-弹窗",
            "免费鉴定-鉴定-弹窗-关闭",
            input_kind=InputKind.CLICK,
        )
    )

    assert context.tasker.controller.clicks == [(1210, 45)]


def test_maa_adapter_closes_recognized_dungeon_page_before_next_task():
    context = Context()
    state = {"page": "dungeon"}

    def recognize(name, image):
        if state["page"] == "dungeon" and name == "dungeon_page":
            return Detail(True, (0, 0, 500, 240))
        if state["page"] == "dungeon" and name == "dungeon_close":
            return Detail(True, (1160, 0, 100, 90))
        if state["page"] == "home" and name == "reset.home":
            return Detail(True, (1040, 0, 240, 110))
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)

    def controller_tap(box):
        context.tasker.controller.clicks.append((box[0] + box[2] // 2, box[1] + box[3] // 2))
        state["page"] = "home"

    driver._controller_tap = controller_tap

    assert driver.return_to_home() is True
    assert context.tasker.controller.clicks == [(1210, 45)]


def test_maa_adapter_keeps_buy_tea_route_on_yanwu_map_after_tab_selection():
    context = Context()
    driver = MaaAndroidWorkflowDriver(context)
    driver._last_action_id = "select_yanwu_world"
    driver._yanwu_selection_confirmed = True

    frame = driver.capture()
    evidence = driver.recognize(
        frame,
        ("yanwu_world_page", "universal_shop_entry"),
    )

    assert evidence.page_hits["yanwu_world_page"] == 1
    assert evidence.target_hits["universal_shop_entry"] == 1


def test_maa_adapter_uses_the_live_yunzhou_page_after_region_selection():
    context = Context()
    driver = MaaAndroidWorkflowDriver(context)
    driver._last_action_id = "select_yunzhou"

    frame = driver.capture()
    evidence = driver.recognize(frame, ("yunzhou_world_page",))

    assert evidence.page_hits["yunzhou_world_page"] == 1
    assert evidence.target_hits["yunzhou_world_page"] == 1


def test_maa_adapter_cleanup_starts_game_from_recognized_title(monkeypatch):
    context = Context()
    state = {"page": "title"}
    context.run_recognition = lambda name, image: (
        Detail(True, (560, 630, 160, 40))
        if state["page"] == "title" and name == "reset.start_game"
        else Detail(True, (1040, 0, 240, 110))
        if state["page"] == "home" and name == "reset.home"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    taps = []

    def controller_tap(box):
        taps.append(box)
        state["page"] = "home"

    monkeypatch.setattr(driver, "_controller_drag_tap", controller_tap)

    assert driver.return_to_home() is True
    assert taps == [(430, 600, 420, 100)]


def test_maa_adapter_starts_game_from_welcome_title_with_fixed_bottom_tap(monkeypatch):
    context = Context()
    state = {"page": "title"}
    context.run_recognition = lambda name, image: (
        Detail(True, (420, 90, 440, 80))
        if state["page"] == "title" and name == "reset.start_game_welcome"
        else Detail(True, (1040, 0, 240, 110))
        if state["page"] == "home" and name == "reset.home"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    taps = []

    def controller_tap(box):
        taps.append(box)
        state["page"] = "home"

    monkeypatch.setattr(driver, "_controller_drag_tap", controller_tap)

    assert driver.return_to_home() is True
    assert taps == [(430, 600, 420, 100)]


def test_maa_adapter_closes_title_announcement_before_starting(monkeypatch):
    context = Context()
    state = {"page": "announcement"}
    context.run_recognition = lambda name, image: (
        Detail(True, (150, 100, 1000, 450))
        if state["page"] == "announcement" and name == "reset.announcement_page"
        else Detail(True, (560, 630, 160, 40))
        if state["page"] == "title" and name == "reset.start_game"
        else Detail(True, (1040, 0, 240, 110))
        if state["page"] == "home" and name == "reset.home"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    taps = []

    def controller_tap(box):
        taps.append(box)
        if state["page"] == "announcement":
            state["page"] = "title"
        else:
            state["page"] = "home"

    monkeypatch.setattr(driver, "_controller_tap", controller_tap)
    monkeypatch.setattr(driver, "_controller_drag_tap", controller_tap)

    assert driver.return_to_home(max_steps=3) is True
    assert taps == [(1010, 90, 150, 100), (430, 600, 420, 100)]


def test_maa_adapter_carries_ocr_text_into_same_frame_evidence():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (200, 300, 100, 50), [OcrResult("免费领取")])
        if name == "free_gift"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    frame = driver.capture()
    evidence = driver.recognize(frame, ("free_gift",))

    assert evidence.texts == ("免费领取",)


def test_maa_adapter_uses_currency_capsule_instead_of_regional_label():
    context = Context()
    driver = MaaAndroidWorkflowDriver(context)
    frame = driver.capture()
    driver.recognize(frame, ("page", "target"))
    driver.execute(
        ActionIntent(
            "open_yanwu_currency_purchase", "page", "target", input_kind=InputKind.CLICK
        )
    )

    assert context.tasker.controller.clicks == [(1095, 43)]


def test_maa_adapter_selects_yanwu_region_with_the_calibrated_row_click():
    context = Context()
    driver = MaaAndroidWorkflowDriver(context)
    frame = driver.capture()
    context.run_recognition = lambda name, image: (
        Detail(True, (0, 0, 100, 100))
        if name == "page"
        else Detail(True, (133, 144, 100, 26))
        if name == "yanwu_world_tab"
        else Detail(False, None)
    )
    driver.recognize(frame, ("page", "yanwu_world_tab"))
    driver.execute(
        ActionIntent(
            "select_yanwu_world",
            "page",
            "yanwu_world_tab",
            input_kind=InputKind.CLICK,
        )
    )

    assert context.tasker.controller.clicks == [(200, 168)]


def test_maa_adapter_opens_jianlin_from_the_daily_row_button():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (92, 28, 84, 25))
        if name == "日常任务奖励-日常-页面"
        else Detail(True, (1048, 348, 53, 29))
        if name == "jianlin_entry"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    frame = driver.capture()
    driver.recognize(frame, ("日常任务奖励-日常-页面", "jianlin_entry"))

    driver.execute(
        ActionIntent(
            "open_jianlin",
            "日常任务奖励-日常-页面",
            "jianlin_entry",
            input_kind=InputKind.CLICK,
        )
    )

    assert context.tasker.controller.clicks == [(1125, 465)]


def test_maa_adapter_maps_jianlin_row_text_to_its_matching_forward_button():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (92, 28, 84, 25))
        if name == "日常任务奖励-日常-页面"
        else Detail(True, (290, 348, 260, 29))
        if name == "jianlin_daily_row"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    frame = driver.capture()
    driver.recognize(frame, ("日常任务奖励-日常-页面", "jianlin_daily_row"))
    driver.execute(
        ActionIntent(
            "open_jianlin",
            "日常任务奖励-日常-页面",
            "jianlin_daily_row",
            input_kind=InputKind.CLICK,
        )
    )

    assert context.tasker.controller.clicks == [(1125, 362)]


def test_maa_adapter_does_not_use_an_unrelated_claim_button_as_jianlin_done():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (92, 28, 84, 25))
        if name == "日常任务奖励-日常-页面"
        else Detail(True, (1048, 428, 53, 29))
        if name == "jianlin_daily_done"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    frame = driver.capture()
    evidence = driver.recognize(
        frame, ("日常任务奖励-日常-页面", "jianlin_daily_row", "jianlin_daily_done")
    )

    assert evidence.target_hits["jianlin_daily_row"] == 0
    assert evidence.target_hits["jianlin_daily_done"] == 0


def test_maa_adapter_scrolls_jianlin_daily_list_through_adb_controller():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (92, 28, 84, 25)) if name == "日常任务奖励-日常-页面" else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    frame = driver.capture()
    driver.recognize(frame, ("日常任务奖励-日常-页面",))
    driver.execute(
        ActionIntent(
            "scroll_daily_jianlin",
            "日常任务奖励-日常-页面",
            "日常任务奖励-日常-页面",
            input_kind=InputKind.SWIPE,
        )
    )

    assert context.tasker.controller.swipes == [(650, 650, 650, 250, 900)]


def test_maa_adapter_scrolls_daily_rewards_without_page_pointer_box():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, None) if name == "日常任务奖励-日常-页面" else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    frame = driver.capture()
    driver.recognize(frame, ("日常任务奖励-日常-页面",))
    driver.execute(
        ActionIntent(
            "scroll_daily_reward_rows",
            "日常任务奖励-日常-页面",
            "日常任务奖励-日常-页面",
            input_kind=InputKind.SWIPE,
        )
    )

    assert context.tasker.controller.swipes == [(650, 650, 650, 300, 800)]


def test_maa_adapter_scrolls_tea_inside_product_grid_not_search_field():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, None) if name == "universal_shop_page" else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    frame = driver.capture()
    driver.recognize(frame, ("universal_shop_page",))
    driver.execute(
        ActionIntent(
            "scroll_tea_list",
            "universal_shop_page",
            "universal_shop_page",
            input_kind=InputKind.SWIPE,
        )
    )

    assert context.tasker.controller.swipes == [
        (500, 270, 500, 500, 600),
        (500, 270, 500, 500, 600),
        (500, 270, 500, 500, 600),
        (500, 500, 500, 270, 800),
    ]
    assert context.tasker.controller.clicks == [(120, 145)]


def test_maa_adapter_uses_touch_lifecycle_for_android_swipe_when_available():
    class TouchController(Controller):
        def post_touch_move(self, x, y, contact=0, pressure=1):
            self.touches.append(("move", x, y, contact, pressure))
            return Job(None)

    context = Context()
    context.tasker.controller = TouchController()
    driver = MaaAndroidWorkflowDriver(context)

    driver._controller_swipe((500, 500), (500, 270), duration_ms=160)

    assert context.tasker.controller.swipes == []
    assert context.tasker.controller.touches[0] == ("down", 500, 500, 0, 1)
    assert context.tasker.controller.touches[-1] == ("up", 0)
    assert [item[0] for item in context.tasker.controller.touches] == [
        "down",
        "move",
        "move",
        "up",
    ]


def test_maa_adapter_keeps_shop_page_after_tea_scroll_hides_tea_label():
    context = Context()

    def recognize(name, image):
        if name == "universal_shop_boundary":
            return Detail(True, (0, 0, 320, 120))
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)
    frame = driver.capture()
    evidence = driver.recognize(
        frame,
        ("universal_shop_page", "universal_shop_boundary"),
    )

    assert evidence.page_hits["universal_shop_page"] == 1
    assert evidence.target_hits["universal_shop_page"] == 1
    assert driver._boxes["universal_shop_page"] == (
        frame.frame_id,
        (0, 0, 320, 120),
    )


def test_maa_adapter_clicks_the_current_tea_card():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (240, 280, 88, 88))
        if name == "tea_item_scrolled"
        else Detail(True, (0, 100, 1000, 500))
        if name == "universal_shop_page"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    frame = driver.capture()
    driver.recognize(frame, ("universal_shop_page", "tea_item_scrolled"))
    driver.execute(
        ActionIntent(
            "open_tea_tab",
            "universal_shop_page",
            "tea_item_scrolled",
            input_kind=InputKind.CLICK,
        )
    )

    assert context.tasker.controller.clicks == [(284, 324)]


def test_maa_adapter_recovers_a_clipped_tea_card_from_its_label():
    context = Context()

    def recognize(name, image):
        if name == "universal_shop_page":
            return Detail(True, (0, 100, 1000, 500))
        if name == "tea_card_label":
            return Detail(True, (235, 195, 80, 25), results=[OcrResult("茶叶")])
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)
    frame = driver.capture()
    evidence = driver.recognize(
        frame,
        ("universal_shop_page", "tea_item_scrolled", "tea_card_label"),
    )

    assert evidence.target_hits["tea_item_scrolled"] == 1
    assert driver._boxes["tea_item_scrolled"] == (
        frame.frame_id,
        (215, 120, 140, 150),
    )


def test_maa_adapter_recovers_quantity_panel_from_live_title():
    context = Context()

    def recognize(name, image):
        if name == "quantity_panel_title":
            return Detail(True, (292, 112, 120, 42), results=[OcrResult("购买物品")])
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)
    driver._last_action_id = "open_tea_purchase"
    frame = driver.capture()
    evidence = driver.recognize(
        frame,
        ("quantity_panel", "quantity_panel_title", "买茶-茶-最大-数量"),
    )

    assert evidence.target_hits["quantity_panel"] == 1
    assert driver._boxes["quantity_panel"] == (
        frame.frame_id,
        (200, 70, 850, 560),
    )


def test_maa_adapter_keeps_collection_page_postcondition_after_open_action():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (0, 0, 100, 100)) if name == "yanwu.page" else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    driver._last_action_id = "open_collection_deployment"
    frame = driver.capture()
    evidence = driver.recognize(frame, ("yanwu.page", "采集部署-采集-打开", "采集部署-采集-页面"))

    assert evidence.page_hits["采集部署-采集-页面"] == 1
    assert evidence.target_hits["采集部署-采集-页面"] == 1


def test_maa_adapter_cleanup_does_not_click_ungated_daily_close():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (1160, 0, 100, 100)) if name == "reset.daily_close" else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)

    assert driver.return_to_home(max_steps=1) is False
    assert context.tasker.controller.clicks == []


def test_maa_adapter_starts_jianlin_from_the_bounded_challenge_button():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (50, 30, 80, 25))
        if name == "jianlin_page"
        else Detail(True, (1040, 630, 80, 40))
        if name == "jianlin_buy_confirm"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    frame = driver.capture()
    driver.recognize(frame, ("jianlin_page", "jianlin_buy_confirm"))

    driver.execute(
        ActionIntent(
            "buy_jianlin_resource",
            "jianlin_page",
            "jianlin_buy_confirm",
            approved_resource="紫色魂玉",
            input_kind=InputKind.CLICK,
        )
    )

    assert context.tasker.controller.clicks == [(1090, 640)]


def test_maa_adapter_selects_jianlin_condensate_resource_card():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (50, 30, 80, 25))
        if name == "jianlin_page"
        else Detail(True, (80, 260, 100, 40))
        if name == "jianlin_condensate_resource"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    frame = driver.capture()
    driver.recognize(frame, ("jianlin_page", "jianlin_condensate_resource"))

    driver.execute(
        ActionIntent(
            "select_jianlin_condensate",
            "jianlin_page",
            "jianlin_condensate_resource",
            input_kind=InputKind.CLICK,
        )
    )

    assert context.tasker.controller.clicks == [(140, 285)]


def test_maa_adapter_starts_jianlin_battle_from_formation():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (1040, 510, 100, 40))
        if name == "jianlin_battle_page"
        else Detail(True, (1120, 560, 100, 100))
        if name == "jianlin_battle_start"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    frame = driver.capture()
    driver.recognize(frame, ("jianlin_battle_page", "jianlin_battle_start"))

    driver.execute(
        ActionIntent(
            "start_jianlin_battle",
            "jianlin_battle_page",
            "jianlin_battle_start",
            approved_resource="体力",
            input_kind=InputKind.CLICK,
        )
    )

    assert context.tasker.controller.clicks == [(1140, 610)]


def test_maa_adapter_uses_adb_controller_for_jianlin_refill_and_safe_controls():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (1110, 10, 55, 60))
        if name == "jianlin_stamina_plus"
        else Detail(True, (800, 340, 100, 60))
        if name == "jianlin_stamina_purchase_confirm"
        else Detail(True, (500, 390, 520, 80))
        if name == "jianlin_count_bar"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)

    frame = driver.capture()
    driver.recognize(frame, ("jianlin_condensate_selected", "jianlin_stamina_plus"))
    driver.execute(
        ActionIntent(
            "open_jianlin_stamina_purchase",
            "jianlin_condensate_selected",
            "jianlin_stamina_plus",
            input_kind=InputKind.CLICK,
        )
    )

    frame = driver.capture()
    driver.recognize(frame, ("jianlin_stamina_purchase_prompt", "jianlin_stamina_purchase_confirm"))
    driver.execute(
        ActionIntent(
            "buy_stamina_once",
            "jianlin_stamina_purchase_prompt",
            "jianlin_stamina_purchase_confirm",
            approved_resource="紫色魂玉",
            input_kind=InputKind.CLICK,
        )
    )

    frame = driver.capture()
    driver.recognize(frame, ("jianlin_condensate_selected", "jianlin_count_bar"))
    driver.execute(
        ActionIntent(
            "set_safe_count",
            "jianlin_condensate_selected",
            "jianlin_count_bar",
            input_kind=InputKind.CLICK,
            parameter=3,
        )
    )

    assert context.tasker.controller.clicks == [(1138, 40), (850, 370)]
    assert context.tasker.controller.swipes == [(930, 505, 1040, 505, 900)]


def test_jianlin_drag_starts_from_the_current_verified_count_tick():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (925, 450, 285, 100), (OcrResult("挑战次数 x6"),))
        if name == "jianlin_count_selected"
        else Detail(True, (925, 485, 285, 42))
        if name == "jianlin_count_bar"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    frame = driver.capture()
    driver.recognize(frame, ("jianlin_count_selected", "jianlin_count_bar"))
    driver.execute(
        ActionIntent(
            "set_safe_count",
            "jianlin_condensate_selected",
            "jianlin_count_bar",
            input_kind=InputKind.CLICK,
            parameter=3,
        )
    )
    assert context.tasker.controller.swipes == [(1204, 505, 1040, 505, 900)]


def test_verified_jianlin_refill_prompt_clears_only_expected_prompt_danger():
    context = Context()

    def recognize(name, image):
        if name in {
            "jianlin_stamina_purchase_prompt",
            "jianlin_stamina_purchase_confirm",
            "jianlin_stamina_amount",
            "jianlin_stamina_price",
            "jianlin_refill_prompt",
        }:
            text = "+80" if name == "jianlin_stamina_amount" else "10"
            return Detail(True, (680, 375, 150, 80), (OcrResult(text),))
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)
    evidence = driver.recognize(
        driver.capture(),
        (
            "jianlin_stamina_purchase_prompt",
            "jianlin_stamina_purchase_confirm",
            "jianlin_stamina_amount",
            "jianlin_stamina_price",
            "jianlin_stamina_resource",
            "jianlin_refill_prompt",
            "紫色魂玉",
        ),
    )

    assert evidence.danger_hits["jianlin_refill_prompt"] == 0
    assert "紫色魂玉" in evidence.resource_hits


def test_verified_jianlin_second_confirmation_uses_adb_confirm_button():
    context = Context()

    def recognize(name, image):
        if name == "jianlin_refill_prompt":
            return Detail(True, (350, 250, 600, 180), (OcrResult("购买体力"),))
        if name in {
            "jianlin_stamina_confirmation_prompt",
            "jianlin_stamina_confirmation_price",
            "jianlin_stamina_confirmation_amount",
            "jianlin_stamina_confirmation_resource",
            "jianlin_stamina_confirmation_confirm",
        }:
            return Detail(True, (815, 480, 130, 50), (OcrResult("确认"),))
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)
    names = (
        "jianlin_stamina_confirmation_prompt",
        "jianlin_stamina_confirmation_price",
        "jianlin_stamina_confirmation_amount",
        "jianlin_stamina_confirmation_resource",
        "jianlin_stamina_confirmation_confirm",
        "jianlin_refill_prompt",
    )
    evidence = driver.recognize(driver.capture(), names)

    assert evidence.danger_hits["jianlin_refill_prompt"] == 0
    driver.execute(
        ActionIntent(
            "confirm_jianlin_stamina_purchase",
            "jianlin_stamina_confirmation_prompt",
            "jianlin_stamina_confirmation_confirm",
            approved_resource="紫色魂玉",
            input_kind=InputKind.CLICK,
        )
    )
    assert context.tasker.controller.clicks == [(880, 505)]


def test_jianlin_closes_escalated_refill_at_safe_top_blank():
    context = Context()
    driver = MaaAndroidWorkflowDriver(context)
    frame = driver.capture()
    driver._boxes["jianlin_stamina_escalated_price"] = (
        frame.frame_id,
        (680, 375, 150, 80),
    )
    driver.execute(
        ActionIntent(
            "close_postpurchase_stamina_prompt",
            "jianlin_stamina_purchase_prompt",
            "jianlin_stamina_escalated_price",
            input_kind=InputKind.CLICK,
        )
    )
    assert context.tasker.controller.clicks == [(640, 90)]


def test_jianlin_resource_page_is_a_resumable_task_surface():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (0, 0, 280, 100))
        if name in {"jianlin_page", "jianlin_condensate_selected"}
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)

    assert driver.can_resume_task("JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY") is True
    assert driver.can_resume_task("MAIL_REWARD_DAILY") is False


def test_ring_page_is_a_resumable_task_surface():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (0, 0, 1280, 180))
        if name == "ring_page"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)

    assert driver.can_resume_task("RING_CHALLENGE_DAILY") is True


def test_ring_partial_attempt_surface_is_resumable_without_reusing_daily_success():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (0, 0, 1280, 720))
        if name in {"ring_opponent_page", "ring_fight_target", "ring_attempts"}
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)

    assert driver.can_resume_task("RING_CHALLENGE_DAILY") is True


def test_ring_attempt_counter_alone_is_not_a_resume_boundary():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (900, 0, 300, 120))
        if name == "ring_attempts"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)

    assert driver.can_resume_task("RING_CHALLENGE_DAILY") is False


def test_mail_claim_promotes_reward_popup_from_stable_close_footer():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (350, 560, 600, 140))
        if name == "邮件奖励-邮件-奖励-弹窗-关闭"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    driver._last_action_id = "claim_all_mail"

    evidence = driver.recognize(
        driver.capture(),
        ("邮件奖励-邮件-奖励-弹窗", "邮件奖励-邮件-奖励-弹窗-关闭"),
    )

    assert evidence.page_hits["邮件奖励-邮件-奖励-弹窗"] == 1
    assert evidence.target_hits["邮件奖励-邮件-奖励-弹窗"] == 1
    assert driver._boxes["邮件奖励-邮件-奖励-弹窗"][1] == (0, 100, 1280, 620)


def test_ring_page_is_derived_after_authorized_daily_row_navigation():
    context = Context()
    driver = MaaAndroidWorkflowDriver(context)
    driver._last_action_id = "open_ring_challenge"

    evidence = driver.recognize(driver.capture(), ("ring_page", "日常任务奖励-日常-页面"))

    assert evidence.page_hits["ring_page"] == 1
    assert evidence.target_hits["ring_page"] == 1


def test_daily_reward_popup_is_a_resumable_task_surface():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (130, 180, 130, 350))
        if name == "日常任务奖励-日常-奖励-弹窗"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)

    assert driver.can_resume_task("DAILY_TASK_REWARD_CLAIM_DAILY") is True


def test_martial_success_card_is_a_resumable_task_surface():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (1115, 500, 120, 150))
        if name == "martial_success_card"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)

    assert driver.can_resume_task("MARTIAL_STUDY_BREAKTHROUGH_DAILY") is True


def test_spend_condensate_resumes_from_the_yunzhou_map():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (60, 200, 300, 130))
        if name == "yunzhou_world_page"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)

    assert driver.can_resume_task("SPEND_CONDENSATE_DAILY") is True


def test_daily_reward_close_text_proves_animated_popup_parent():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (300, 560, 700, 160), results=[OcrResult("点击空白处关闭")])
        if name == "日常任务奖励-日常-奖励-弹窗-关闭"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)

    evidence = driver.recognize(
        driver.capture(),
        ("日常任务奖励-日常-奖励-弹窗", "日常任务奖励-日常-奖励-弹窗-关闭"),
    )

    assert evidence.target_hits["日常任务奖励-日常-奖励-弹窗"] == 1


def test_ring_reward_close_text_proves_result_when_title_ocr_misses():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (350, 580, 600, 140), results=[OcrResult("点击空白处关闭")])
        if name == "ring_result_close"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)

    evidence = driver.recognize(
        driver.capture(),
        ("ring_sweep_result", "ring_result_close"),
    )

    assert evidence.page_hits["ring_sweep_result"] == 1
    assert evidence.target_hits["ring_result_close"] == 1


def test_ring_battle_result_visual_proves_result_when_title_ocr_misses():
    image = np.zeros((720, 1280, 3), dtype=np.uint8)
    image[:] = (50, 45, 35)
    # Match the large blue/red result-title geometry from the live Android
    # victory frame without making the test depend on a captured artifact.
    image[120:250, 760:1190] = (50, 80, 160)

    assert _ring_battle_result_visible(image) is True

    context = Context()
    context.tasker.controller.post_screencap = lambda: Job(image)
    driver = MaaAndroidWorkflowDriver(context)
    driver._last_action_id = "wait_ring_battle"

    evidence = driver.recognize(
        driver.capture(),
        ("ring_battle_result", "ring_result_close"),
    )

    assert evidence.page_hits["ring_battle_result"] == 1
    assert evidence.target_hits["ring_result_close"] == 1


def test_ring_sweep_reward_visual_proves_result_after_confirmation():
    image = np.zeros((720, 1280, 3), dtype=np.uint8)
    image[:220] = (60, 65, 70)
    image[600:] = (55, 60, 65)
    image[240:470] = (205, 225, 240)

    assert _ring_sweep_reward_popup_visible(image) is True

    context = Context()
    context.tasker.controller.post_screencap = lambda: Job(image)
    driver = MaaAndroidWorkflowDriver(context)
    driver._last_action_id = "confirm_ring_sweep"

    evidence = driver.recognize(
        driver.capture(),
        ("ring_sweep_result", "ring_result_close"),
    )

    assert evidence.page_hits["ring_sweep_result"] == 1
    assert evidence.target_hits["ring_result_close"] == 1


def test_ring_sweep_reward_visual_does_not_prove_result_before_confirmation():
    image = np.zeros((720, 1280, 3), dtype=np.uint8)
    image[:220] = (60, 65, 70)
    image[600:] = (55, 60, 65)
    image[240:470] = (205, 225, 240)

    context = Context()
    context.tasker.controller.post_screencap = lambda: Job(image)
    driver = MaaAndroidWorkflowDriver(context)
    driver._last_action_id = "sweep_ring"

    evidence = driver.recognize(driver.capture(), ("ring_sweep_result",))

    assert evidence.page_hits["ring_sweep_result"] == 0


def test_maa_adapter_closes_ring_reward_popup_at_task_boundary(monkeypatch):
    context = Context()
    state = {"popup": True}

    def recognize(name, image):
        if state["popup"] and name == "ring_result_close":
            return Detail(
                True,
                (350, 580, 600, 140),
                results=[OcrResult("点击空白处关闭")],
            )
        if not state["popup"] and name == "reset.home":
            return Detail(True, (1040, 0, 240, 110))
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)
    original_tap = driver._controller_tap
    monkeypatch.setattr("agent.workflows.maa_android.sleep", lambda _: None)

    def tap(box):
        original_tap(box)
        state["popup"] = False

    driver._controller_tap = tap

    assert driver.return_to_home() is True
    assert context.tasker.controller.clicks == [(1200, 670)]


def test_jianlin_large_title_proves_condensate_is_selected():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (900, 60, 360, 110))
        if name in {"jianlin_page", "jianlin_condensate_title"}
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    evidence = driver.recognize(
        driver.capture(),
        ("jianlin_page", "jianlin_condensate_title", "jianlin_condensate_selected"),
    )
    assert evidence.target_hits["jianlin_condensate_selected"] == 1
    assert evidence.target_hits["jianlin_page"] == 1


def test_jianlin_bounded_challenge_button_does_not_fake_condensate_selection():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (980, 625, 220, 60))
        if name == "jianlin_challenge_button"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    evidence = driver.recognize(
        driver.capture(),
        ("jianlin_page", "jianlin_condensate_selected", "jianlin_challenge_button"),
    )
    assert evidence.target_hits["jianlin_page"] == 1
    assert evidence.target_hits["jianlin_condensate_selected"] == 0


def test_maa_adapter_does_not_fake_yanwu_page_after_unconfirmed_selection():
    context = Context()
    driver = MaaAndroidWorkflowDriver(context)
    driver._last_action_id = "select_yanwu_world"

    evidence = driver.recognize(driver.capture(), ("yanwu_world_page", "yanwu.page"))

    assert evidence.page_hits["yanwu_world_page"] == 0
    assert evidence.target_hits["yanwu.page"] == 0


def test_maa_adapter_falls_back_to_the_live_bag_food_category_icon():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (51, 46, 49, 28))
        if name == "bag_page"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    frame = driver.capture()
    evidence = driver.recognize(frame, ("bag_page", "food_category"))

    assert evidence.page_hits["bag_page"] == 1
    assert evidence.target_hits["food_category"] == 1
    driver.execute(
        ActionIntent(
            "open_food_category",
            "bag_page",
            "food_category",
            input_kind=InputKind.CLICK,
        )
    )

    assert context.tasker.controller.clicks == [(73, 202)]


def test_maa_adapter_does_not_fake_food_target_from_page_only():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (39, 46, 70, 28))
        if name == "food_tab_page"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    evidence = driver.recognize(
        driver.capture(), ("food_tab_page", "longjing_shrimp_eat_target")
    )

    assert evidence.page_hits["food_tab_page"] == 1
    assert evidence.target_hits["longjing_shrimp_eat_target"] == 0


def test_maa_adapter_accepts_the_recognized_food_replacement_prompt_as_eat_result():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (300, 300, 500, 150))
        if name == "food_buff_replace_prompt"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    driver._last_action_id = "eat_longjing_shrimp"
    evidence = driver.recognize(
        driver.capture(),
        ("consumables_page", "food_buff_replace_prompt"),
    )

    assert evidence.page_hits["food_buff_replace_prompt"] == 1
    assert evidence.page_hits["consumables_page"] == 1


def test_maa_adapter_promotes_confirm_button_to_food_prompt_after_eat():
    context = Context()

    def recognize(name, image):
        if name == "food_buff_replace_confirm":
            return Detail(True, (813, 482, 130, 42))
        if name == "food_use_result":
            return Detail(True, (300, 300, 500, 150))
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)
    driver._last_action_id = "eat_longjing_shrimp"
    evidence = driver.recognize(
        driver.capture(),
        (
            "food_buff_replace_prompt",
            "food_buff_replace_confirm",
            "food_use_result",
        ),
    )

    assert evidence.page_hits["food_buff_replace_prompt"] == 1
    assert evidence.target_hits["food_buff_replace_confirm"] == 1
    assert evidence.recognizer_frame_ids["food_buff_replace_prompt"] == evidence.frame_id
    assert driver._boxes["food_buff_replace_prompt"][1] == (380, 270, 520, 150)


def test_maa_adapter_promotes_food_replacement_templates_to_canonical_targets():
    context = Context()

    def recognize(name, image):
        if name == "food_buff_replace_prompt_template":
            return Detail(True, (300, 180, 680, 370))
        if name == "food_buff_replace_confirm_template":
            return Detail(True, (813, 482, 130, 42))
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)
    evidence = driver.recognize(
        driver.capture(),
        (
            "food_buff_replace_prompt",
            "food_buff_replace_confirm",
            "food_buff_replace_prompt_template",
            "food_buff_replace_confirm_template",
            "food_use_result",
        ),
    )

    assert evidence.target_hits["food_buff_replace_prompt"] == 1
    assert evidence.target_hits["food_buff_replace_confirm"] == 1
    assert driver._boxes["food_buff_replace_confirm"][1] == (813, 482, 130, 42)


def test_maa_adapter_does_not_promote_an_unrelated_confirm_button_to_food_prompt():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (813, 482, 130, 42))
        if name == "food_buff_replace_confirm"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    driver._last_action_id = "eat_longjing_shrimp"
    evidence = driver.recognize(
        driver.capture(),
        ("food_buff_replace_prompt", "food_buff_replace_confirm", "food_use_result"),
    )

    assert evidence.target_hits["food_buff_replace_prompt"] == 0


def test_maa_adapter_retains_short_lived_food_overfull_completion_signal():
    context = Context()
    state = {"overfull": True}

    def recognize(name, image):
        if name == "food_overfull" and state["overfull"]:
            state["overfull"] = False
            return Detail(True, (400, 300, 500, 60))
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)
    driver._last_action_id = "eat_longjing_shrimp"

    frame = driver.capture()
    evidence = driver.recognize(
        frame,
        ("food_use_result", "food_overfull"),
    )

    assert evidence.target_hits["food_overfull"] == 1
    assert evidence.target_hits["food_use_result"] == 1

    frame = driver.capture()
    evidence = driver.recognize(frame, ("food_overfull",))
    assert evidence.target_hits["food_overfull"] == 1


def test_maa_adapter_buys_currency_at_max_with_one_bounded_sequence(monkeypatch):
    context = Context()
    driver = MaaAndroidWorkflowDriver(context)
    frame = driver.capture()
    driver.recognize(frame, ("page", "target"))
    monkeypatch.setattr("agent.workflows.maa_android.sleep", lambda _seconds: None)

    driver.execute(
        ActionIntent(
            "buy_yanwu_currency_max",
            "page",
            "target",
            approved_resource="凝晶",
            input_kind=InputKind.CLICK,
        )
    )

    assert context.tasker.controller.clicks == [(988, 463), (860, 575)]


def test_maa_adapter_uses_confirmed_condensate_region_on_regional_purchase_page():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (250, 80, 1000, 560))
        if name == "yanwu_currency_purchase"
        else Detail(True, (700, 500, 350, 120))
        if name == "yanwu_currency_purchase_target"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)

    evidence = driver.recognize(
        driver.capture(),
        (
            "yanwu_currency_purchase",
            "yanwu_currency_purchase_target",
            "凝晶",
        ),
    )

    assert evidence.target_hits["凝晶"] == 1
    assert evidence.resource_hits == ("凝晶",)


def test_maa_adapter_never_invents_condensate_on_unrelated_purchase_page():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(True, (0, 0, 1280, 720))
        if name == "quantity_panel"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)

    evidence = driver.recognize(driver.capture(), ("quantity_panel", "凝晶"))

    assert evidence.target_hits["凝晶"] == 0
    assert evidence.resource_hits == ()


def test_maa_adapter_scrolls_dungeon_list_through_controller():
    context = Context()
    driver = MaaAndroidWorkflowDriver(context)
    frame = driver.capture()
    driver.recognize(frame, ("page", "target"))

    driver.execute(
        ActionIntent(
            "scroll_dungeon_list", "page", "target", input_kind=InputKind.SWIPE
        )
    )

    assert context.tasker.controller.swipes == [(160, 650, 160, 250, 1000)]


def test_maa_adapter_opens_dungeon_sweep_panel_through_controller():
    context = Context()

    def recognize(name, image):
        if name == "yanwangling_title":
            return Detail(True, (300, 300, 700, 180))
        if name == "sweep_target":
            return Detail(True, (900, 520, 300, 160))
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)
    frame = driver.capture()
    driver.recognize(frame, ("yanwangling_title", "sweep_target"))

    driver.execute(
        ActionIntent(
            "open_sweep_panel",
            "yanwangling_title",
            "sweep_target",
            input_kind=InputKind.CLICK,
        )
    )

    assert context.tasker.controller.clicks == [(1050, 600)]


def test_maa_adapter_uses_title_as_yanwangling_selection_evidence():
    context = Context()

    def recognize(name, image):
        if name == "yanwangling_title":
            return Detail(True, (300, 300, 700, 180))
        return Detail(False, None)

    context.run_recognition = recognize
    driver = MaaAndroidWorkflowDriver(context)
    driver._last_action_id = "select_yanwangling"
    evidence = driver.recognize(
        driver.capture(),
        ("dungeon_page", "yanwangling_title"),
    )

    assert evidence.target_hits["yanwangling_title"] == 1
    assert "selected" not in evidence.target_hits


def test_maa_adapter_has_no_direct_adb_input_side_channel():
    source = (Path(__file__).parents[1] / "agent/workflows/maa_android.py").read_text(
        encoding="utf-8"
    )

    assert '"shell", "input"' not in source
    assert "subprocess.run" not in source


def test_maa_adapter_does_not_promote_unfiltered_ocr_prices_to_evidence():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(False, None, all_results=[OcrResult("￥30.00")])
        if name == "破阵武学-安全-付费"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)
    frame = driver.capture()
    evidence = driver.recognize(frame, ("破阵武学-安全-付费",))

    assert evidence.texts == ()


def test_maa_adapter_keeps_only_best_jianlin_stamina_cost_candidate():
    context = Context()
    context.run_recognition = lambda name, image: (
        Detail(
            True,
            (1155, 535, 65, 50),
            results=[OcrResult("2"), OcrResult("120")],
            best_result=OcrResult("120"),
        )
        if name == "jianlin_stamina_cost_value"
        else Detail(False, None)
    )
    driver = MaaAndroidWorkflowDriver(context)

    evidence = driver.recognize(driver.capture(), ("jianlin_stamina_cost_value",))

    assert evidence.texts == ("120",)
