"""Verify every remaining dispatch row, including rows below the fold."""

from __future__ import annotations

import re
from time import sleep
from typing import Any

from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction

_TIMER = re.compile(r"(?:[QO〇○]?\s*)?(\d{1,2}):(\d{2}):(\d{2})$")


def waiting_rows(results: Any) -> list[int] | None:
    """Read running countdowns in screen order, without reading row names."""
    lines = sorted(
        [(str(r.text).strip(), tuple(r.box)) for r in results], key=lambda item: item[1][1]
    )
    if any(re.match(r"^(?:耗时|已完成|完成)(?:$|[:：\s])", text) for text, _ in lines):
        return None
    rows = []
    for text, _ in lines:
        match = _TIMER.fullmatch(text.replace("：", ":").replace(" ", ""))
        if not match:
            continue
        hour, minute, second = map(int, match.groups())
        if minute >= 60 or second >= 60:
            return None
        rows.append(hour * 3600 + minute * 60 + second)
    return rows or None


def append_overlapping_rows(seen: list[int], page: list[int]) -> list[int] | None:
    """Merge countdown overlap; task names never participate in matching."""
    overlaps = []
    for size in range(1, min(len(seen), len(page)) + 1):
        if all(0 <= a - b <= 20 for a, b in zip(seen[-size:], page[:size])):
            overlaps.append(size)
    if len(overlaps) > 1:
        longest = max(overlaps)
        seen_timers, page_timers = seen[-longest:], page[:longest]
        if (all(a < b for a, b in zip(seen_timers, seen_timers[1:]))
                and all(a < b for a, b in zip(page_timers, page_timers[1:]))):
            overlaps = [longest]
    if len(overlaps) != 1:
        return None
    return [*seen, *page[overlaps[0]:]]


@AgentServer.custom_action("VerifyDispatchList")
class VerifyDispatchList(CustomAction):
    """Native screenshots and bounded list swipes; never claim or send a team."""

    def run(self, context: Any, argv: CustomAction.RunArg) -> bool:
        controller = context.tasker.controller
        seen: list[int] = []
        total = None
        try:
            # Explicitly restore the top before counting; a stale scroll position
            # otherwise makes it possible to miss pending rows above the viewport.
            if not controller.post_swipe(175, 170, 175, 580, 500).wait().status.succeeded:
                return False
            sleep(0.7)
            for _ in range(12):
                if not controller.post_screencap().wait().status.succeeded:
                    return False
                frame = controller.cached_image
                if not context.run_recognition("0742-英雄派遣-英雄-派遣-页面", frame).hit:
                    return False
                header = context.run_recognition("英雄派遣-列表-计数", frame)
                text = " ".join(r.text for r in header.filtered_results)
                count = re.search(r"(?<!成)任务\s*[:：]\s*(\d+)\s*/\s*12", text)
                completed = re.search(r"已完成\s*[:：]\s*0(?!\d)", text)
                if not count or not completed or not 1 <= int(count[1]) <= 12:
                    return False
                if total is not None and total != int(count[1]):
                    return False
                total = int(count[1])
                detail = context.run_recognition("英雄派遣-列表-文字", frame)
                page = waiting_rows(detail.filtered_results)
                if not page:
                    return False
                combined = append_overlapping_rows(seen, page) if seen else page
                if combined is None or len(combined) > total:
                    return False
                if len(combined) == total:
                    return True
                if seen and len(combined) == len(seen):
                    return False
                seen = combined
                # A fast 250px gesture coasted past the overlap on the live
                # list. Move less than one 135px row and lower the velocity.
                if not controller.post_swipe(175, 500, 175, 380, 1000).wait().status.succeeded:
                    return False
                sleep(0.7)
            return False
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return False


__all__ = ["VerifyDispatchList", "append_overlapping_rows", "waiting_rows"]
