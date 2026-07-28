from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
_TOP_LEVEL_KEYS = {"schema_version", "restored", "snapshot"}
_SNAPSHOT_KEYS = {"window_id", "pid", "bounds", "previous_frontmost_bundle_id"}
_BOUNDS_KEYS = {"x", "y", "width", "height"}


@dataclass(frozen=True)
class Bounds:
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class WindowSnapshot:
    window_id: int
    pid: int
    bounds: Bounds
    previous_frontmost_bundle_id: str | None


class WindowStateStore:
    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)

    def save(self, snapshot: WindowSnapshot) -> None:
        self._write(
            {
                "schema_version": SCHEMA_VERSION,
                "restored": False,
                "snapshot": self._snapshot_to_json(snapshot),
            }
        )

    def load_pending(self) -> WindowSnapshot | None:
        if not self.path.exists():
            return None
        payload = self._read()
        if payload["restored"]:
            return None
        return self._snapshot_from_json(payload["snapshot"])

    def mark_restored(self) -> None:
        if not self.path.exists():
            return
        payload = self._read()
        if payload["restored"]:
            return
        payload["restored"] = True
        self._write(payload)

    @staticmethod
    def _snapshot_to_json(snapshot: WindowSnapshot) -> dict[str, Any]:
        if not isinstance(snapshot, WindowSnapshot):
            raise ValueError("invalid window state: snapshot has an invalid type")
        WindowStateStore._validate_positive_int(snapshot.window_id, "window_id")
        WindowStateStore._validate_positive_int(snapshot.pid, "pid")
        WindowStateStore._validate_bounds(snapshot.bounds)
        if snapshot.previous_frontmost_bundle_id is not None and not isinstance(
            snapshot.previous_frontmost_bundle_id, str
        ):
            raise ValueError("invalid window state: bundle id must be a string or null")
        return asdict(snapshot)

    @classmethod
    def _snapshot_from_json(cls, value: Any) -> WindowSnapshot:
        if not isinstance(value, dict) or set(value) != _SNAPSHOT_KEYS:
            raise ValueError("invalid window state: incomplete snapshot")
        bounds = value["bounds"]
        if not isinstance(bounds, dict) or set(bounds) != _BOUNDS_KEYS:
            raise ValueError("invalid window state: incomplete bounds")
        try:
            snapshot = WindowSnapshot(
                window_id=value["window_id"],
                pid=value["pid"],
                bounds=Bounds(
                    x=bounds["x"],
                    y=bounds["y"],
                    width=bounds["width"],
                    height=bounds["height"],
                ),
                previous_frontmost_bundle_id=value["previous_frontmost_bundle_id"],
            )
        except (KeyError, TypeError) as exc:
            raise ValueError("invalid window state: malformed snapshot") from exc
        cls._snapshot_to_json(snapshot)
        return snapshot

    @classmethod
    def _validate_bounds(cls, bounds: Bounds) -> None:
        if not isinstance(bounds, Bounds):
            raise ValueError("invalid window state: bounds have an invalid type")
        for name in ("x", "y", "width", "height"):
            value = getattr(bounds, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"invalid window state: {name} must be an integer")
        if bounds.width <= 0 or bounds.height <= 0:
            raise ValueError("invalid window state: width and height must be positive")

    @staticmethod
    def _validate_positive_int(value: Any, name: str) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"invalid window state: {name} must be a positive integer")

    def _read(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or set(payload) != _TOP_LEVEL_KEYS:
                raise ValueError("invalid window state: invalid top-level fields")
            if (
                isinstance(payload["schema_version"], bool)
                or not isinstance(payload["schema_version"], int)
                or payload["schema_version"] != SCHEMA_VERSION
            ):
                raise ValueError("invalid window state: unsupported schema version")
            if not isinstance(payload["restored"], bool):
                raise ValueError("invalid window state: restored must be boolean")
            self._snapshot_from_json(payload["snapshot"])
            return payload
        except ValueError as exc:
            if str(exc).startswith("invalid window state"):
                raise
            raise ValueError("invalid window state: malformed JSON") from exc
        except (OSError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid window state: unreadable state") from exc

    def _write(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f"{self.path.name}.tmp")
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(self.path)
        finally:
            if temporary.exists():
                temporary.unlink()
