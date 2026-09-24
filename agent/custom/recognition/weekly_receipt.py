"""Recognize a same-account weekly claim from existing native MFW evidence.

The game removes the free card after claiming it. No separate receipt or
business-result file is written: the source remains the native task log.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from maa.agent.agent_server import AgentServer
from maa.custom_recognition import CustomRecognition

# The embedded MFW Python omits zoneinfo. The current China game clock is
# fixed UTC+8, so weekly receipts need no historical timezone database.
_ZONE = timezone(timedelta(hours=8))
_ENTRY = "0022-每周免费礼包-任务入口"
_EVENT = re.compile(r"\[msg=([^]]+)\].*\[details=(\{.*\})\]")
_TASK_ID = re.compile(r'"task_id"\s*:\s*(\d+)')
_UID = re.compile(r"^UID\s*[:：]\s*(\d+)$", re.IGNORECASE)


def _texts(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        if isinstance(value.get("text"), str):
            yield value["text"]
        for child in value.values():
            yield from _texts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _texts(child)


def weekly_start(now: datetime) -> datetime:
    local = now.astimezone(_ZONE) - timedelta(hours=5)
    return (local - timedelta(days=local.weekday())).replace(
        hour=5, minute=0, second=0, microsecond=0
    )


def find_weekly_native_receipt(
    paths: Iterable[Path], account: str, now: datetime,
) -> dict[str, Any] | None:
    """Require claim input, visible reward, account identity and native success."""
    start = weekly_start(now)
    runs: dict[tuple[Path, int], dict[str, Any]] = {}
    for path in sorted(paths, key=lambda p: p.stat().st_mtime):
        with path.open(encoding="utf-8", errors="replace") as stream:
            for line in stream:
                if "!!!OnEventNotify!!!" not in line:
                    continue
                # Large OCR payloads from unrelated daily tasks need no JSON
                # decoding. A weekly start must still be read before tracking.
                starting = "[msg=Tasker.Task.Starting]" in line
                if starting:
                    if _ENTRY not in line:
                        task = _TASK_ID.search(line)
                        if task is not None:
                            runs.pop((path.parent, int(task[1])), None)
                        continue
                else:
                    if not any(f"[msg={event}]" in line for event in (
                        "Node.Recognition.Succeeded", "Node.Action.Succeeded",
                        "Tasker.Task.Succeeded", "Tasker.Task.Failed",
                    )):
                        continue
                    task = _TASK_ID.search(line)
                    if task is None or (path.parent, int(task[1])) not in runs:
                        continue
                try:
                    stamp = datetime.fromisoformat(line[1:24]).replace(tzinfo=_ZONE)
                    if not start <= stamp <= now:
                        continue
                    match = _EVENT.search(line)
                    if not match:
                        continue
                    event, data = match[1], json.loads(match[2])
                    task_id = data.get("task_id")
                    key = (path.parent, task_id)
                    if event == "Tasker.Task.Starting" and data.get("entry") == _ENTRY:
                        runs[key] = {"claim": False, "reward": False, "account": False,
                                     "reward_close": False}
                    run = runs.get(key)
                    if run is None:
                        continue
                    if event == "Node.Recognition.Succeeded":
                        texts = set(_texts(data.get("reco_details", {})))
                        run["account"] |= any(
                            (uid := _UID.fullmatch(text.strip())) is not None and uid[1] == account
                            for text in texts
                        )
                        if data.get("name") == "1342-每周免费礼包-关闭-奖励":
                            run["reward"] |= "恭喜获得" in texts and "点击空白处关闭" in texts
                    if event == "Node.Action.Succeeded":
                        run["claim"] |= data.get("name") == "1340-每周免费礼包-免费-领取"
                        run["reward_close"] |= data.get("name") == "1342-每周免费礼包-关闭-奖励"
                    if event == "Tasker.Task.Failed":
                        runs.pop(key, None)
                    elif event == "Tasker.Task.Succeeded" and data.get("entry") == _ENTRY:
                        if all(run.values()):
                            return {"source": str(path), "claimed_at": stamp.isoformat(),
                                    "native_task_id": task_id, "same_account": True}
                        runs.pop(key, None)
                except (ValueError, TypeError, KeyError):
                    continue
    return None


@AgentServer.custom_recognition("WeeklyNativeClaimReceipt")
class WeeklyNativeClaimReceipt(CustomRecognition):
    def __init__(self):
        super().__init__()
        self._cache: dict[tuple[str, datetime], dict[str, Any]] = {}

    def analyze(self, context: Any, argv: CustomRecognition.AnalyzeArg):
        try:
            page = context.run_recognition("1350-每周免费礼包-商店-每周-页面", argv.image)
            identity = context.run_recognition("每周免费礼包-当前账号", argv.image)
            if not page or not page.hit or not identity or not identity.hit:
                return None
            ids = {_UID.fullmatch(r.text.strip())[1] for r in identity.filtered_results
                   if _UID.fullmatch(r.text.strip())}
            if len(ids) != 1:
                return None
            account = ids.pop()
            now = datetime.now(_ZONE)
            key = (account, weekly_start(now))
            receipt = self._cache.get(key)
            if receipt is None:
                # Runtime paths are relative to the immutable candidate; only
                # existing native logs from its installation root are read.
                install_root = Path(__file__).resolve().parents[3].parent
                oldest = key[1].timestamp()
                paths = [p for p in install_root.glob("*/debug/maafw*.log")
                         if not p.name.startswith("._") and p.stat().st_mtime >= oldest]
                receipt = find_weekly_native_receipt(paths, account, now)
                if receipt is None:
                    return None
                self._cache[key] = receipt
            return CustomRecognition.AnalyzeResult(box=[1060, 690, 220, 30], detail=receipt)
        except (OSError, RuntimeError, TypeError, ValueError, AttributeError):
            return None


__all__ = ["WeeklyNativeClaimReceipt", "find_weekly_native_receipt", "weekly_start"]
