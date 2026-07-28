from __future__ import annotations

import json
import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from threading import RLock
from time import monotonic, monotonic_ns
from typing import Any, Callable

from .errors import MJAError

TimestampFactory = Callable[[], str | datetime]

_SENSITIVE_KEY_PARTS = frozenset(
    {
        "account",
        "command",
        "credential",
        "env",
        "password",
        "secret",
        "token",
        "user",
    }
)


def _default_timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="microseconds")


def _format_timestamp(value: str | datetime) -> str:
    if isinstance(value, datetime):
        return value.astimezone().isoformat(timespec="microseconds")
    if not isinstance(value, str) or not value:
        raise ValueError("timestamp factory must return a non-empty string or datetime")
    return value


def _safe_details(value: Any) -> Any:
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for key, item in value.items():
            normalized = str(key).casefold().replace("-", "_")
            parts = set(normalized.split("_"))
            if parts & _SENSITIVE_KEY_PARTS or any(
                part in normalized for part in _SENSITIVE_KEY_PARTS
            ):
                continue
            safe[str(key)] = _safe_details(item)
        return safe
    if isinstance(value, list):
        return [_safe_details(item) for item in value]
    if isinstance(value, tuple):
        return [_safe_details(item) for item in value]
    return value


class RunDiagnostics:
    """Persist structured, local-only diagnostics for one task execution."""

    def __init__(
        self,
        directory: Path,
        started_at: str,
        now: TimestampFactory,
    ) -> None:
        self.directory = directory
        self._now = now
        self._started_at = started_at
        self._started_monotonic = monotonic()
        self._lock = RLock()
        self._logger = logging.getLogger(f"mja.run.{id(self)}")
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False
        self._handler = RotatingFileHandler(
            self.directory / "agent.log",
            maxBytes=1_048_576,
            backupCount=2,
            encoding="utf-8",
        )
        self._handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        )
        self._logger.addHandler(self._handler)
        self._payload: dict[str, Any] = {
            "schema_version": 1,
            "status": "running",
            "started_at": started_at,
            "finished_at": None,
            "duration_ms": None,
            "components": {},
            "window": None,
            "events": [],
            "error": None,
        }
        self._write()
        self._logger.info("run started")

    @classmethod
    def create(
        cls,
        root: Path,
        *,
        now: TimestampFactory = _default_timestamp,
    ) -> RunDiagnostics:
        """Create ``root/<timestamp>`` and initialize its diagnostic files."""
        root = Path(root)
        timestamp = _format_timestamp(now())
        directory = root / timestamp
        suffix = 1
        while directory.exists():
            directory = root / f"{timestamp}-{suffix}"
            suffix += 1
        directory.mkdir(parents=True, exist_ok=False)
        return cls(directory, timestamp, now)

    @property
    def logger(self) -> logging.Logger:
        return self._logger

    def record_component(self, name: str, version: str) -> None:
        with self._lock:
            self._payload["components"][name] = version
            self._logger.info("component %s=%s", name, version)
            self._write()

    def record_window(
        self,
        *,
        window_id: int,
        pid: int,
        screenshot_size: tuple[int, int],
    ) -> None:
        width, height = screenshot_size
        with self._lock:
            self._payload["window"] = {
                "window_id": window_id,
                "pid": pid,
                "screenshot_size": {"width": width, "height": height},
            }
            self._logger.info("window recorded id=%s pid=%s", window_id, pid)
            self._write()

    def event(self, name: str, details: dict[str, Any] | None = None) -> None:
        record: dict[str, Any] = {
            "name": name,
            "monotonic_ms": monotonic_ns() // 1_000_000,
            "details": _safe_details(details or {}),
        }
        with self._lock:
            self._payload["events"].append(record)
            self._logger.info("event %s", name)
            self._write()

    def succeed(self) -> None:
        with self._lock:
            self._payload["status"] = "succeeded"
            self._payload["finished_at"] = _format_timestamp(self._now())
            self._payload["duration_ms"] = self._duration_ms()
            self._payload["error"] = None
            self._logger.info("run succeeded")
            self._write()

    def fail(self, error: MJAError) -> None:
        if not isinstance(error, MJAError):
            raise TypeError("RunDiagnostics.fail requires MJAError")
        with self._lock:
            self._payload["status"] = "failed"
            self._payload["finished_at"] = _format_timestamp(self._now())
            self._payload["duration_ms"] = self._duration_ms()
            self._payload["error"] = error.as_dict()
            self._logger.error("run failed code=%s message=%s", error.code.value, error)
            self._write()

    def close(self) -> None:
        with self._lock:
            if self._handler not in self._logger.handlers:
                return
            self._logger.removeHandler(self._handler)
            self._handler.flush()
            self._handler.close()

    def __enter__(self) -> RunDiagnostics:
        return self

    def __exit__(self, _exc_type: Any, _exc: Any, _traceback: Any) -> None:
        self.close()

    def _duration_ms(self) -> int:
        return max(0, int((monotonic() - self._started_monotonic) * 1000))

    def _write(self) -> None:
        target = self.directory / "run.json"
        temporary = self.directory / "run.json.tmp"
        temporary.write_text(
            json.dumps(self._payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(target)


__all__ = ["RunDiagnostics"]
