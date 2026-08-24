#!/usr/bin/env python3
"""Process-safe exclusive simulator leases for MFW workers.

This helper owns *only* the simulator lease.  It deliberately does not start
MFW, inspect task results, schedule work, inject ADB input, or terminate a
runner.

The resource lock is a POSIX ``flock`` held by the owner process for the
complete ``GAME_START + business task + native teardown`` interval.  The JSON
file is metadata and protocol state; it is never the source of truth for
ownership.  A crashed owner therefore releases the kernel lock when its file
descriptor is closed, even though its last metadata can remain ``held_active``.

The normal in-process API is:

    with SimulatorLease.acquire(
        resource="emulator-5556",
        owner_id="worker:MAIL_REWARD_DAILY",
        state_dir=Path("debug/leases"),
    ) as lease:
        lease.heartbeat(native_state="game_start")
        # run GAME_START + the one business task + native teardown here
        lease.heartbeat(
            native_state="teardown_complete",
            in_use=False,
            release_ready=True,
        )

        # The context manager performs the final CAS-protected release.

For a long-lived shell holder, ``acquire --hold`` prints one JSON record and
then accepts JSON commands on stdin.  The holder must keep that process alive
while it owns the simulator:

    python tools/mfw_simulator_lock.py acquire \
      --resource emulator-5556 --state-dir debug/leases \
      --owner-id worker:MAIL_REWARD_DAILY --hold

The holder protocol accepts ``heartbeat``, ``probe`` (return the owner's
current response), and ``release``.  An external lock manager can call the
standalone ``probe`` command with the JSON response obtained from the holder.
No response is a blocked condition, not an idle result.  ``reclaim`` is
reserved for a dead owner and requires a lease-matching teardown evidence
record; it never steals a live lock.

The metadata is updated with an atomic same-directory ``os.replace`` and a
short-lived metadata mutex.  The mutex makes lease-id compare-and-swap
updates safe even when a lock manager updates metadata while the owner keeps
the resource ``flock`` held.  The resource ``flock`` itself remains the only
authority for simulator ownership.  If the kernel lock is free but metadata
still describes an active or suspect lease, ``acquire`` fails closed and
requires ``reclaim`` with teardown evidence; it does not silently overwrite a
crashed owner's lease.
"""

from __future__ import annotations

import argparse
import datetime as dt
import errno
import fcntl
import hashlib
import json
import os
import re
import sys
import tempfile
import time
import uuid
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO


SCHEMA_VERSION = 1
DEFAULT_STATE_DIR = Path(".mfw-simulator-leases")
DEFAULT_POLL_SECONDS = 0.05

REQUIRED_METADATA_FIELDS = (
    "resource",
    "lease_id",
    "owner_id",
    "pid",
    "native_pid",
    "acquired_at",
    "last_probe_at",
    "last_owner_response_at",
    "state",
    "native_state",
    "in_use",
    "release_ready",
)

OWNER_RESPONSE_FIELDS = (
    "lease_id",
    "in_use",
    "native_state",
    "pid_alive",
    "last_action_at",
    "release_ready",
)

FREE_STATES = frozenset({"released", "reclaimed"})

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_LOCK_BUSY = 10
EXIT_LEASE_MISMATCH = 11
EXIT_LOCK_BLOCKED = 12
EXIT_METADATA_ERROR = 13
EXIT_NO_LEASE = 14
EXIT_LEASE_NOT_HELD = 15


class LeaseError(RuntimeError):
    """Base error with a stable machine-readable status and exit code."""

    status = "ERROR"
    exit_code = EXIT_ERROR

    def __init__(
        self,
        message: str,
        *,
        status: str | None = None,
        exit_code: int | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        if status is not None:
            self.status = status
        if exit_code is not None:
            self.exit_code = exit_code
        self.details = dict(details or {})

    def as_payload(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "error": str(self),
            **self.details,
        }


class LockBusyError(LeaseError):
    status = "LOCK_BUSY"
    exit_code = EXIT_LOCK_BUSY


class LeaseMismatchError(LeaseError):
    status = "LEASE_ID_MISMATCH"
    exit_code = EXIT_LEASE_MISMATCH


class LockBlockedError(LeaseError):
    status = "LOCK_BLOCKED"
    exit_code = EXIT_LOCK_BLOCKED


class MetadataError(LeaseError):
    status = "INVALID_METADATA"
    exit_code = EXIT_METADATA_ERROR


class NoLeaseError(LeaseError):
    status = "NO_LEASE"
    exit_code = EXIT_NO_LEASE


class LeaseNotHeldError(LeaseError):
    status = "LEASE_NOT_HELD"
    exit_code = EXIT_LEASE_NOT_HELD


@dataclass(frozen=True, slots=True)
class LeasePaths:
    """The resource lock, metadata, and metadata-mutex paths."""

    lock_path: Path
    metadata_path: Path
    metadata_mutex_path: Path


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _valid_text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _valid_optional_pid(value: object, *, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field} must be a positive integer or null")
    return value


def _parse_bool(value: str) -> bool:
    normalized = value.strip().casefold()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"expected true/false, got {value!r}")


def _parse_timestamp(value: str, *, field: str) -> str:
    value = _valid_text(value, field=field)
    try:
        dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
    return value


def _timestamp_age_seconds(value: str) -> float:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    return max(0.0, (dt.datetime.now(dt.timezone.utc) - parsed).total_seconds())


def _pid_alive(pid: int) -> bool:
    """Return whether the local OS still has a process with ``pid``.

    ``PermissionError`` means the process exists but is not signalable by this
    user.  The helper never sends a signal other than the harmless existence
    probe ``kill(pid, 0)``.
    """

    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError as exc:
        if exc.errno == errno.ESRCH:
            return False
        if exc.errno == errno.EPERM:
            return True
        raise
    return True


def _safe_resource_name(resource: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", resource).strip("._-")
    return name or "resource"


def resolve_paths(
    resource: str | None = None,
    *,
    state_dir: Path | str = DEFAULT_STATE_DIR,
    lock_path: Path | str | None = None,
    metadata_path: Path | str | None = None,
) -> LeasePaths:
    """Resolve stable paths without using a PID file as an ownership lock."""

    if resource is not None:
        resource = _valid_text(resource, field="resource")

    if lock_path is None and metadata_path is None and resource is None:
        raise ValueError("resource or lock_path/metadata_path is required")

    if lock_path is None:
        if resource is not None:
            digest = hashlib.sha256(resource.encode("utf-8")).hexdigest()[:12]
            lock_path = (
                Path(state_dir)
                / f"{_safe_resource_name(resource)}-{digest}.lock"
            )
        else:
            metadata_candidate = Path(metadata_path)  # type: ignore[arg-type]
            name = metadata_candidate.name
            lock_name = name[:-5] if name.endswith(".json") else f"{name}.lock"
            lock_path = metadata_candidate.with_name(lock_name)

    lock = Path(lock_path)
    if metadata_path is None:
        metadata = lock.with_name(f"{lock.name}.json")
    else:
        metadata = Path(metadata_path)
    mutex = metadata.with_name(f"{metadata.name}.mutex")
    return LeasePaths(lock, metadata, mutex)


def _require_posix() -> None:
    if os.name != "posix":  # pragma: no cover - project runtime is macOS
        raise RuntimeError("mfw_simulator_lock requires POSIX fcntl.flock")


def _open_rw(path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0)
    return os.open(path, flags, 0o600)


def _is_lock_busy(exc: OSError) -> bool:
    return isinstance(exc, BlockingIOError) or exc.errno in {errno.EACCES, errno.EAGAIN}


def _acquire_flock(
    fd: int,
    *,
    wait: bool = False,
    timeout_seconds: float | None = None,
    poll_seconds: float = DEFAULT_POLL_SECONDS,
) -> None:
    _require_posix()
    if timeout_seconds is not None and timeout_seconds < 0:
        raise ValueError("timeout_seconds must be non-negative")
    if poll_seconds <= 0:
        raise ValueError("poll_seconds must be positive")

    if wait and timeout_seconds is None:
        fcntl.flock(fd, fcntl.LOCK_EX)
        return

    deadline = None
    if timeout_seconds is not None:
        deadline = time.monotonic() + timeout_seconds

    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except OSError as exc:
            if not _is_lock_busy(exc):
                raise
            if not wait and timeout_seconds is None:
                raise LockBusyError("simulator resource is already leased") from exc
            if deadline is not None and time.monotonic() >= deadline:
                raise LockBusyError("timed out waiting for simulator resource") from exc
            remaining = None if deadline is None else max(0.0, deadline - time.monotonic())
            time.sleep(poll_seconds if remaining is None else min(poll_seconds, remaining))


def _close_flock(fd: int) -> None:
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass
    try:
        os.close(fd)
    except OSError:
        pass


@contextmanager
def _metadata_guard(path: Path):
    """Serialize metadata CAS operations without taking the resource flock."""

    _require_posix()
    fd = _open_rw(path)
    locked = False
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        locked = True
        yield
    finally:
        if locked:
            _close_flock(fd)
        else:
            try:
                os.close(fd)
            except OSError:
                pass


def _fsync_directory(directory: Path) -> None:
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    """Atomically replace a JSON object in the target directory."""

    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            fd = -1
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if fd >= 0:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _read_json_object(path: Path, *, missing_ok: bool = False) -> dict[str, Any] | None:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        if missing_ok:
            return None
        raise NoLeaseError(f"lease metadata does not exist: {path}")
    except OSError as exc:
        raise MetadataError(f"cannot read lease metadata: {path}: {exc}") from exc
    try:
        payload = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise MetadataError(f"lease metadata is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise MetadataError(f"lease metadata must be a JSON object: {path}")
    return payload


def _validate_metadata(payload: Mapping[str, Any], *, path: Path) -> dict[str, Any]:
    missing = [field for field in REQUIRED_METADATA_FIELDS if field not in payload]
    if missing:
        raise MetadataError(
            f"lease metadata is missing fields {missing!r}: {path}",
            details={"metadata_path": str(path)},
        )

    resource = _valid_text(payload["resource"], field="resource")
    lease_id = _valid_text(payload["lease_id"], field="lease_id")
    owner_id = _valid_text(payload["owner_id"], field="owner_id")
    pid = _valid_optional_pid(payload["pid"], field="pid")
    if pid is None:
        raise ValueError("pid must be a positive integer")
    native_pid = _valid_optional_pid(payload["native_pid"], field="native_pid")
    for field in ("acquired_at", "native_state"):
        _valid_text(payload[field], field=field)
    for field in ("last_probe_at", "last_owner_response_at"):
        if payload[field] is not None:
            _parse_timestamp(str(payload[field]), field=field)
    if payload.get("last_action_at") is not None:
        _parse_timestamp(str(payload["last_action_at"]), field="last_action_at")
    _valid_text(payload["state"], field="state")
    if type(payload["in_use"]) is not bool:
        raise ValueError("in_use must be boolean")
    if type(payload["release_ready"]) is not bool:
        raise ValueError("release_ready must be boolean")
    revision = payload.get("revision", 0)
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise ValueError("revision must be a non-negative integer")
    result = dict(payload)
    result.update(
        {
            "resource": resource,
            "lease_id": lease_id,
            "owner_id": owner_id,
            "pid": pid,
            "native_pid": native_pid,
            "revision": revision,
        }
    )
    return result


def read_metadata(
    metadata_path: Path | str,
    *,
    lock_path: Path | str | None = None,
) -> dict[str, Any]:
    """Read and validate the current metadata snapshot."""

    paths = resolve_paths(lock_path=lock_path, metadata_path=metadata_path)
    with _metadata_guard(paths.metadata_mutex_path):
        payload = _read_json_object(paths.metadata_path)
        assert payload is not None
        try:
            return _validate_metadata(payload, path=paths.metadata_path)
        except ValueError as exc:
            raise MetadataError(
                str(exc),
                details={"metadata_path": str(paths.metadata_path)},
            ) from exc


def _metadata_for_paths(paths: LeasePaths) -> dict[str, Any]:
    payload = _read_json_object(paths.metadata_path)
    assert payload is not None
    try:
        return _validate_metadata(payload, path=paths.metadata_path)
    except ValueError as exc:
        raise MetadataError(
            str(exc),
            details={"metadata_path": str(paths.metadata_path)},
        ) from exc


def _assert_metadata_can_be_replaced(
    metadata: Mapping[str, Any],
    *,
    path: Path,
) -> None:
    """Reject an unlocked-but-active lease until it is explicitly reclaimed."""

    if metadata["state"] in FREE_STATES:
        return
    if (
        metadata["state"] == "idle"
        and metadata["in_use"] is False
        and metadata["release_ready"] is True
    ):
        return
    raise LockBlockedError(
        "previous lease metadata is still active; reclaim requires owner death "
        "and native teardown evidence",
        details={
            "reason": "stale_lease",
            "previous_lease_id": metadata["lease_id"],
            "previous_owner_id": metadata["owner_id"],
            "previous_pid": metadata["pid"],
            "metadata_path": str(path),
        },
    )


def _next_revision(metadata: Mapping[str, Any]) -> int:
    revision = metadata.get("revision", 0)
    return int(revision) + 1


def _require_matching_lease(
    metadata: Mapping[str, Any],
    lease_id: str,
    *,
    owner_id: str | None = None,
    require_live: bool = True,
) -> None:
    lease_id = _valid_text(lease_id, field="lease_id")
    if metadata["lease_id"] != lease_id:
        raise LeaseMismatchError(
            "lease_id does not match the current simulator lease",
            details={
                "expected_lease_id": lease_id,
                "current_lease_id": metadata["lease_id"],
            },
        )
    if owner_id is not None and metadata["owner_id"] != _valid_text(owner_id, field="owner_id"):
        raise LeaseMismatchError("owner_id does not match the current simulator lease")
    if require_live and metadata["state"] in FREE_STATES:
        raise LeaseNotHeldError(
            f"lease is already {metadata['state']}",
            details={"lease_id": lease_id},
        )


def _mutate_metadata(
    paths: LeasePaths,
    lease_id: str,
    mutator: Callable[[dict[str, Any]], None],
    *,
    owner_id: str | None = None,
    require_live: bool = True,
) -> dict[str, Any]:
    with _metadata_guard(paths.metadata_mutex_path):
        metadata = _metadata_for_paths(paths)
        _require_matching_lease(
            metadata,
            lease_id,
            owner_id=owner_id,
            require_live=require_live,
        )
        mutator(metadata)
        metadata["revision"] = _next_revision(metadata)
        try:
            _validate_metadata(metadata, path=paths.metadata_path)
        except ValueError as exc:
            raise MetadataError(
                str(exc),
                details={"metadata_path": str(paths.metadata_path)},
            ) from exc
        _write_json_atomic(paths.metadata_path, metadata)
        return metadata


def _state_for(in_use: bool, release_ready: bool) -> str:
    if release_ready and in_use:
        raise ValueError("release_ready cannot be true while in_use is true")
    if not in_use and release_ready:
        return "idle"
    if not in_use:
        return "idle_not_ready"
    return "held_active"


def _owner_response_from_metadata(
    metadata: Mapping[str, Any],
    *,
    responded_at: str | None = None,
) -> dict[str, Any]:
    response = {
        "lease_id": metadata["lease_id"],
        "in_use": metadata["in_use"],
        "native_state": metadata["native_state"],
        "pid_alive": _pid_alive(metadata["pid"]),
        "last_action_at": metadata.get("last_action_at", metadata["acquired_at"]),
        "release_ready": metadata["release_ready"],
    }
    if responded_at is not None:
        response["responded_at"] = responded_at
    return response


def _validate_owner_response(
    response: Mapping[str, Any],
    metadata: Mapping[str, Any],
    *,
    expected_lease_id: str,
    max_age_seconds: float | None = None,
) -> dict[str, Any]:
    if not isinstance(response, Mapping):
        raise LockBlockedError(
            "owner response must be a JSON object",
            details={"reason": "invalid_owner_response"},
        )
    missing = [field for field in OWNER_RESPONSE_FIELDS if field not in response]
    if missing:
        raise LockBlockedError(
            f"owner response is missing fields {missing!r}",
            details={"reason": "invalid_owner_response"},
        )
    if response["lease_id"] != expected_lease_id:
        raise LeaseMismatchError(
            "owner response lease_id does not match the current lease",
            details={
                "expected_lease_id": expected_lease_id,
                "response_lease_id": response["lease_id"],
            },
        )
    if type(response["in_use"]) is not bool:
        raise LockBlockedError("owner response in_use must be boolean")
    if type(response["pid_alive"]) is not bool:
        raise LockBlockedError("owner response pid_alive must be boolean")
    if type(response["release_ready"]) is not bool:
        raise LockBlockedError("owner response release_ready must be boolean")
    try:
        native_state = _valid_text(response["native_state"], field="native_state")
        last_action_at = _parse_timestamp(
            str(response["last_action_at"]),
            field="last_action_at",
        )
    except ValueError as exc:
        raise LockBlockedError(
            str(exc),
            details={"reason": "invalid_owner_response"},
        ) from exc
    if response["release_ready"] and response["in_use"]:
        raise LockBlockedError(
            "owner response cannot be release_ready while in_use is true",
            details={"reason": "contradictory_owner_response"},
        )

    actual_pid_alive = _pid_alive(metadata["pid"])
    if response["pid_alive"] != actual_pid_alive:
        raise LockBlockedError(
            "owner response pid_alive disagrees with the local owner process probe",
            details={
                "reason": "owner_liveness_mismatch",
                "reported_pid_alive": response["pid_alive"],
                "actual_pid_alive": actual_pid_alive,
            },
        )

    responded_at = response.get("responded_at")
    if responded_at is not None:
        try:
            parsed_responded_at = _parse_timestamp(
                str(responded_at),
                field="responded_at",
            )
        except ValueError as exc:
            raise LockBlockedError(
                str(exc),
                details={"reason": "invalid_owner_response"},
            ) from exc
        if (
            max_age_seconds is not None
            and _timestamp_age_seconds(parsed_responded_at) > max_age_seconds
        ):
            raise LockBlockedError(
                "owner response is stale",
                details={"reason": "stale_owner_response"},
            )
    elif max_age_seconds is not None:
        raise LockBlockedError(
            "freshness checking requires owner response responded_at",
            details={"reason": "missing_response_timestamp"},
        )

    return {
        "lease_id": expected_lease_id,
        "in_use": response["in_use"],
        "native_state": native_state,
        "pid_alive": response["pid_alive"],
        "last_action_at": last_action_at,
        "release_ready": response["release_ready"],
        **({"responded_at": str(responded_at)} if responded_at is not None else {}),
    }


def _probe_payload(
    metadata: Mapping[str, Any],
    *,
    status: str,
    owner_response: Mapping[str, Any] | None,
    reason: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": status,
        "lease_id": metadata["lease_id"],
        "metadata": dict(metadata),
        "owner_response": dict(owner_response) if owner_response is not None else None,
    }
    if reason is not None:
        payload["reason"] = reason
    return payload


def _heartbeat_metadata(
    paths: LeasePaths,
    lease_id: str,
    *,
    owner_id: str | None = None,
    native_state: str | None = None,
    native_pid: int | None = None,
    in_use: bool | None = None,
    release_ready: bool | None = None,
    last_action_at: str | None = None,
) -> dict[str, Any]:
    now = _utc_now()

    def mutate(metadata: dict[str, Any]) -> None:
        next_in_use = metadata["in_use"] if in_use is None else in_use
        next_release_ready = (
            metadata["release_ready"] if release_ready is None else release_ready
        )
        if type(next_in_use) is not bool or type(next_release_ready) is not bool:
            raise ValueError("in_use and release_ready must be boolean")
        metadata["in_use"] = next_in_use
        metadata["release_ready"] = next_release_ready
        metadata["state"] = _state_for(next_in_use, next_release_ready)
        if native_state is not None:
            metadata["native_state"] = _valid_text(native_state, field="native_state")
        if native_pid is not None:
            metadata["native_pid"] = _valid_optional_pid(native_pid, field="native_pid")
        metadata["last_action_at"] = (
            _parse_timestamp(last_action_at, field="last_action_at")
            if last_action_at is not None
            else now
        )
        metadata["last_owner_response_at"] = now

    return _mutate_metadata(paths, lease_id, mutate, owner_id=owner_id)


def heartbeat(
    metadata_path: Path | str,
    lease_id: str,
    *,
    lock_path: Path | str | None = None,
    owner_id: str | None = None,
    native_state: str | None = None,
    native_pid: int | None = None,
    in_use: bool | None = None,
    release_ready: bool | None = None,
    last_action_at: str | None = None,
) -> dict[str, Any]:
    """CAS-update owner state without touching task scheduling or MFW."""

    paths = resolve_paths(lock_path=lock_path, metadata_path=metadata_path)
    return _heartbeat_metadata(
        paths,
        lease_id,
        owner_id=owner_id,
        native_state=native_state,
        native_pid=native_pid,
        in_use=in_use,
        release_ready=release_ready,
        last_action_at=last_action_at,
    )


def probe(
    metadata_path: Path | str,
    lease_id: str,
    *,
    lock_path: Path | str | None = None,
    owner_response: Mapping[str, Any] | None = None,
    max_age_seconds: float | None = None,
) -> dict[str, Any]:
    """Record a manager probe and validate the holder's response.

    A missing response raises :class:`LockBlockedError`.  In particular,
    metadata saying ``in_use=false`` from an old write is not treated as a
    fresh response.
    """

    if max_age_seconds is not None and max_age_seconds < 0:
        raise ValueError("max_age_seconds must be non-negative")
    paths = resolve_paths(lock_path=lock_path, metadata_path=metadata_path)
    now = _utc_now()
    if owner_response is None:

        def mark_probe(metadata: dict[str, Any]) -> None:
            metadata["last_probe_at"] = now
            if metadata["state"] not in FREE_STATES:
                metadata["state"] = "suspect"

        current = _mutate_metadata(
            paths,
            lease_id,
            mark_probe,
            require_live=False,
        )
        if current["state"] in FREE_STATES:
            return _probe_payload(
                current,
                status="ALREADY_FREE",
                owner_response=None,
                reason="lease_is_not_held",
            )
        raise LockBlockedError(
            "owner did not return a probe response",
            details=_probe_payload(
                current,
                status="LOCK_BLOCKED",
                owner_response=None,
                reason="no_owner_response",
            ),
        )

    def record_response(metadata: dict[str, Any]) -> None:
        validated = _validate_owner_response(
            owner_response,
            metadata,
            expected_lease_id=lease_id,
            max_age_seconds=max_age_seconds,
        )
        metadata["last_probe_at"] = now
        metadata["last_owner_response_at"] = now
        metadata["native_state"] = validated["native_state"]
        metadata["in_use"] = validated["in_use"]
        metadata["release_ready"] = validated["release_ready"]
        metadata["last_action_at"] = validated["last_action_at"]
        metadata["state"] = _state_for(
            validated["in_use"],
            validated["release_ready"],
        )

    current = _mutate_metadata(paths, lease_id, record_response)
    response = _owner_response_from_metadata(current, responded_at=now)
    return _probe_payload(
        current,
        status="IDLE" if not current["in_use"] else "ACTIVE",
        owner_response=response,
    )


def _load_owner_response_file(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise LockBlockedError(
            f"owner response file is not a regular file: {path}",
            details={"reason": "missing_owner_response"},
        )
    try:
        payload = _read_json_object(path)
    except LeaseError as exc:
        raise LockBlockedError(
            f"owner response file is invalid: {path}",
            details={"reason": "invalid_owner_response"},
        ) from exc
    assert payload is not None
    return payload


def _read_teardown_evidence(
    evidence: Path | Mapping[str, Any] | None,
    *,
    metadata: Mapping[str, Any],
    expected_lease_id: str,
) -> dict[str, Any]:
    if evidence is None:
        raise LockBlockedError(
            "native teardown evidence is required for reclaim",
            details={"reason": "missing_teardown_evidence"},
        )
    evidence_path: Path | None = None
    if isinstance(evidence, (str, Path)):
        evidence_path = Path(evidence)
        if evidence_path.is_symlink() or not evidence_path.is_file():
            raise LockBlockedError(
                f"native teardown evidence is not a regular file: {evidence_path}",
                details={"reason": "missing_teardown_evidence"},
            )
        payload = _read_json_object(evidence_path)
        assert payload is not None
    elif isinstance(evidence, Mapping):
        payload = dict(evidence)
    else:
        raise LockBlockedError(
            "native teardown evidence must be a JSON object or file",
            details={"reason": "invalid_teardown_evidence"},
        )

    if payload.get("lease_id") != expected_lease_id:
        raise LeaseMismatchError(
            "native teardown evidence lease_id does not match the current lease",
            details={
                "expected_lease_id": expected_lease_id,
                "evidence_lease_id": payload.get("lease_id"),
            },
        )
    if payload.get("teardown_complete") is not True:
        raise LockBlockedError(
            "native teardown evidence is not marked complete",
            details={"reason": "teardown_not_complete"},
        )
    evidence_native_pid = payload.get("native_pid")
    if evidence_native_pid is not None and evidence_native_pid != metadata["native_pid"]:
        raise LockBlockedError(
            "native teardown evidence native_pid does not match lease metadata",
            details={"reason": "native_pid_mismatch"},
        )
    if metadata["native_pid"] is not None and payload.get("native_pid_alive") is not False:
        raise LockBlockedError(
            "native teardown evidence must prove native_pid is no longer alive",
            details={"reason": "native_pid_liveness_missing"},
        )
    native_state = payload.get("native_state", "teardown_complete")
    _valid_text(native_state, field="native_state")
    result = dict(payload)
    if evidence_path is not None:
        result["evidence_path"] = str(evidence_path)
    return result


def _acquire_primary(
    paths: LeasePaths,
    *,
    wait: bool = False,
    timeout_seconds: float | None = None,
    poll_seconds: float = DEFAULT_POLL_SECONDS,
) -> int:
    fd = _open_rw(paths.lock_path)
    try:
        _acquire_flock(
            fd,
            wait=wait,
            timeout_seconds=timeout_seconds,
            poll_seconds=poll_seconds,
        )
    except BaseException:
        _close_flock(fd)
        raise
    return fd


def _released_metadata(
    paths: LeasePaths,
    lease_id: str,
    *,
    owner_id: str | None = None,
    native_state: str | None = None,
    state: str = "released",
) -> dict[str, Any]:
    now = _utc_now()

    def mutate(metadata: dict[str, Any]) -> None:
        metadata["state"] = state
        metadata["in_use"] = False
        metadata["release_ready"] = True
        if native_state is not None:
            metadata["native_state"] = _valid_text(native_state, field="native_state")
        metadata["last_action_at"] = now
        metadata["last_owner_response_at"] = now
        metadata["last_probe_at"] = now

    return _mutate_metadata(
        paths,
        lease_id,
        mutate,
        owner_id=owner_id,
        require_live=False,
    )


def release(
    metadata_path: Path | str,
    lease_id: str,
    *,
    lock_path: Path | str | None = None,
    owner_id: str | None = None,
    native_state: str = "teardown_complete",
) -> dict[str, Any]:
    """Release a lease from a separate process only when it is already idle.

    A separate command cannot unlock an ``flock`` owned by another process.
    Therefore this function succeeds only if the resource lock is currently
    free and metadata says the owner explicitly reached
    ``in_use=false, release_ready=true``.  The holder process should use
    :meth:`SimulatorLease.release` or the ``acquire --hold`` protocol.
    """

    paths = resolve_paths(lock_path=lock_path, metadata_path=metadata_path)
    try:
        fd = _acquire_primary(paths)
    except LockBusyError as exc:
        raise LockBlockedError(
            "resource lock is still held; the holder must release it",
            details={"reason": "lock_busy"},
        ) from exc
    try:
        with _metadata_guard(paths.metadata_mutex_path):
            current = _metadata_for_paths(paths)
            if current["state"] in FREE_STATES:
                _require_matching_lease(
                    current,
                    lease_id,
                    owner_id=owner_id,
                    require_live=False,
                )
                return {
                    "status": "ALREADY_FREE",
                    "metadata": current,
                    "lease_id": current["lease_id"],
                }
            _require_matching_lease(
                current,
                lease_id,
                owner_id=owner_id,
                require_live=True,
            )
            if (
                current["state"] != "idle"
                or current["in_use"]
                or not current["release_ready"]
            ):
                raise LockBlockedError(
                    "owner has not explicitly marked the lease idle and release-ready",
                    details={"reason": "owner_not_release_ready"},
                )
        result = _released_metadata(
            paths,
            lease_id,
            owner_id=owner_id,
            native_state=native_state,
        )
        return {"status": "RELEASED", "metadata": result, "lease_id": lease_id}
    finally:
        _close_flock(fd)


def reclaim(
    metadata_path: Path | str,
    lease_id: str,
    *,
    lock_path: Path | str | None = None,
    owner_id: str | None = None,
    teardown_evidence: Path | str | Mapping[str, Any] | None = None,
    pid_alive: Callable[[int], bool] = _pid_alive,
) -> dict[str, Any]:
    """Safely reclaim a stale lease after owner death and teardown evidence.

    The function first obtains the same kernel resource lock that a new owner
    would need.  It then performs a lease-id CAS while holding the metadata
    mutex.  A live owner, a held kernel lock, missing evidence, or any
    mismatch returns ``LOCK_BLOCKED``/``LEASE_ID_MISMATCH`` and never removes
    or overwrites another lease.
    """

    paths = resolve_paths(lock_path=lock_path, metadata_path=metadata_path)
    try:
        fd = _acquire_primary(paths)
    except LockBusyError as exc:
        raise LockBlockedError(
            "resource lock is still held; reclaim cannot prove owner death",
            details={"reason": "lock_busy"},
        ) from exc
    try:
        with _metadata_guard(paths.metadata_mutex_path):
            current = _metadata_for_paths(paths)
            _require_matching_lease(
                current,
                lease_id,
                owner_id=owner_id,
                require_live=False,
            )
            if current["state"] in FREE_STATES:
                return {
                    "status": "ALREADY_FREE",
                    "metadata": current,
                    "lease_id": current["lease_id"],
                }
            if pid_alive(current["pid"]):
                raise LockBlockedError(
                    "owner process is still alive; reclaim is forbidden",
                    details={"reason": "owner_alive", "pid": current["pid"]},
                )
            native_pid = current["native_pid"]
            if native_pid is not None and pid_alive(native_pid):
                raise LockBlockedError(
                    "native process is still alive; reclaim is forbidden",
                    details={"reason": "native_pid_alive", "native_pid": native_pid},
                )
            evidence = _read_teardown_evidence(
                teardown_evidence,
                metadata=current,
                expected_lease_id=lease_id,
            )
            now = _utc_now()
            current["state"] = "reclaimed"
            current["native_state"] = _valid_text(
                evidence.get("native_state", "teardown_complete"),
                field="native_state",
            )
            current["in_use"] = False
            current["release_ready"] = True
            current["last_probe_at"] = now
            current["last_action_at"] = now
            current["reclaimed_at"] = now
            current["reclaim_evidence"] = evidence
            current["revision"] = _next_revision(current)
            _write_json_atomic(paths.metadata_path, current)
            return {
                "status": "RECLAIMED",
                "metadata": current,
                "lease_id": lease_id,
            }
    finally:
        _close_flock(fd)


class SimulatorLease:
    """A live owner handle whose open fd holds the simulator ``flock``."""

    def __init__(
        self,
        *,
        paths: LeasePaths,
        lock_fd: int,
        metadata: Mapping[str, Any],
    ) -> None:
        self.paths = paths
        self._lock_fd: int | None = lock_fd
        self._metadata = dict(metadata)

    @classmethod
    def acquire(
        cls,
        resource: str,
        owner_id: str,
        *,
        state_dir: Path | str = DEFAULT_STATE_DIR,
        lock_path: Path | str | None = None,
        metadata_path: Path | str | None = None,
        pid: int | None = None,
        native_pid: int | None = None,
        native_state: str = "acquiring",
        wait: bool = False,
        timeout_seconds: float | None = None,
        poll_seconds: float = DEFAULT_POLL_SECONDS,
    ) -> "SimulatorLease":
        resource = _valid_text(resource, field="resource")
        owner_id = _valid_text(owner_id, field="owner_id")
        pid = os.getpid() if pid is None else _valid_optional_pid(pid, field="pid")
        if pid is None:
            raise ValueError("pid must be a positive integer")
        native_pid = _valid_optional_pid(native_pid, field="native_pid")
        native_state = _valid_text(native_state, field="native_state")
        paths = resolve_paths(
            resource,
            state_dir=state_dir,
            lock_path=lock_path,
            metadata_path=metadata_path,
        )
        fd = _acquire_primary(
            paths,
            wait=wait,
            timeout_seconds=timeout_seconds,
            poll_seconds=poll_seconds,
        )
        now = _utc_now()
        metadata: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "resource": resource,
            "lease_id": uuid.uuid4().hex,
            "owner_id": owner_id,
            "pid": pid,
            "native_pid": native_pid,
            "acquired_at": now,
            "last_probe_at": None,
            "last_owner_response_at": None,
            "last_action_at": now,
            "state": "held_active",
            "native_state": native_state,
            "in_use": True,
            "release_ready": False,
            "revision": 1,
        }
        try:
            with _metadata_guard(paths.metadata_mutex_path):
                existing_payload = _read_json_object(
                    paths.metadata_path,
                    missing_ok=True,
                )
                if existing_payload is not None:
                    try:
                        existing = _validate_metadata(
                            existing_payload,
                            path=paths.metadata_path,
                        )
                    except ValueError as exc:
                        raise MetadataError(
                            str(exc),
                            details={"metadata_path": str(paths.metadata_path)},
                        ) from exc
                    _assert_metadata_can_be_replaced(
                        existing,
                        path=paths.metadata_path,
                    )
                _write_json_atomic(paths.metadata_path, metadata)
        except BaseException:
            _close_flock(fd)
            raise
        return cls(paths=paths, lock_fd=fd, metadata=metadata)

    @property
    def lease_id(self) -> str:
        return str(self._metadata["lease_id"])

    @property
    def owner_id(self) -> str:
        return str(self._metadata["owner_id"])

    @property
    def pid(self) -> int:
        return int(self._metadata["pid"])

    @property
    def metadata_path(self) -> Path:
        return self.paths.metadata_path

    @property
    def lock_path(self) -> Path:
        return self.paths.lock_path

    @property
    def closed(self) -> bool:
        return self._lock_fd is None

    @property
    def metadata(self) -> dict[str, Any]:
        self._ensure_open()
        return read_metadata(self.paths.metadata_path, lock_path=self.paths.lock_path)

    def _ensure_open(self) -> None:
        if self._lock_fd is None:
            raise LeaseNotHeldError(f"lease {self.lease_id} is no longer held")

    def owner_response(self) -> dict[str, Any]:
        """Return the JSON response a holder can send to a lock manager."""

        self._ensure_open()
        current = self.metadata
        return _owner_response_from_metadata(current, responded_at=_utc_now())

    def heartbeat(
        self,
        *,
        native_state: str | None = None,
        native_pid: int | None = None,
        in_use: bool | None = None,
        release_ready: bool | None = None,
        last_action_at: str | None = None,
    ) -> dict[str, Any]:
        self._ensure_open()
        result = _heartbeat_metadata(
            self.paths,
            self.lease_id,
            owner_id=self.owner_id,
            native_state=native_state,
            native_pid=native_pid,
            in_use=in_use,
            release_ready=release_ready,
            last_action_at=last_action_at,
        )
        self._metadata = dict(result)
        return result

    def probe_response(self) -> dict[str, Any]:
        """Alias used by holder-side probe loops."""

        return self.owner_response()

    def release(self, *, native_state: str = "teardown_complete") -> dict[str, Any]:
        """CAS-release this holder's lease and then unlock its kernel fd."""

        self._ensure_open()
        error: BaseException | None = None
        result: dict[str, Any] | None = None
        try:
            result = _released_metadata(
                self.paths,
                self.lease_id,
                owner_id=self.owner_id,
                native_state=native_state,
            )
            self._metadata = dict(result)
        except BaseException as exc:
            error = exc
        finally:
            fd, self._lock_fd = self._lock_fd, None
            assert fd is not None
            _close_flock(fd)
        if error is not None:
            raise error
        assert result is not None
        return result

    def __enter__(self) -> "SimulatorLease":
        self._ensure_open()
        return self

    def __exit__(
        self,
        exc_type: object,
        _exc_value: object,
        _exc_traceback: object,
    ) -> None:
        if self.closed:
            return
        if exc_type is None:
            self.release()
            return

        # An exception is not evidence that native teardown completed, so do
        # not mark the lease released or idle.  Close the kernel fd anyway:
        # keeping a descriptor open after the protected block has unwound can
        # strand the simulator indefinitely in a still-live Python process.
        # The active metadata then forces the next owner through
        # reclaim(teardown_evidence=...), which preserves fail-closed
        # semantics without relying on process death to unlock the resource.
        fd, self._lock_fd = self._lock_fd, None
        assert fd is not None
        _close_flock(fd)


def _lease_payload(lease: SimulatorLease) -> dict[str, Any]:
    metadata = lease.metadata
    return {
        "status": "ACQUIRED",
        "lease_id": lease.lease_id,
        "lock_file": str(lease.lock_path),
        "metadata_file": str(lease.metadata_path),
        "metadata": metadata,
        "owner_response": _owner_response_from_metadata(
            metadata,
            responded_at=_utc_now(),
        ),
    }


def _hold_command(lease: SimulatorLease, command: Mapping[str, Any]) -> dict[str, Any]:
    operation = command.get("command", command.get("op"))
    if operation == "heartbeat":
        allowed = {
            "native_state",
            "native_pid",
            "in_use",
            "release_ready",
            "last_action_at",
        }
        kwargs = {key: command[key] for key in allowed if key in command}
        result = lease.heartbeat(**kwargs)
        return {
            "status": "HEARTBEAT",
            "lease_id": lease.lease_id,
            "metadata": result,
            "owner_response": lease.owner_response(),
        }
    if operation == "probe":
        return {
            "status": "OWNER_RESPONSE",
            "owner_response": lease.owner_response(),
        }
    if operation == "release":
        result = lease.release(
            native_state=str(command.get("native_state", "teardown_complete"))
        )
        return {"status": "RELEASED", "lease_id": result["lease_id"], "metadata": result}
    raise ValueError("hold command must be heartbeat, probe, or release")


def _hold_loop(lease: SimulatorLease, stream: TextIO) -> int:
    print(json.dumps(_lease_payload(lease), ensure_ascii=False), flush=True)
    for line in stream:
        if not line.strip():
            continue
        try:
            command = json.loads(line)
            if isinstance(command, str):
                command = {"command": command}
            if not isinstance(command, Mapping):
                raise ValueError("hold command must be a JSON object")
            payload = _hold_command(lease, command)
        except LeaseError as exc:
            payload = exc.as_payload()
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            payload = {"status": "ERROR", "error": str(exc)}
        print(json.dumps(payload, ensure_ascii=False), flush=True)
        if payload.get("status") == "RELEASED":
            return EXIT_OK
    if not lease.closed:
        print(
            json.dumps(
                {
                    "status": "LOCK_BLOCKED",
                    "reason": "holder_input_closed_without_release",
                    "lease_id": lease.lease_id,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return EXIT_LOCK_BLOCKED
    return EXIT_OK


def _add_path_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--resource", help="logical simulator resource identifier")
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=DEFAULT_STATE_DIR,
        help=f"directory for derived lock metadata (default: {DEFAULT_STATE_DIR})",
    )
    parser.add_argument(
        "--lock-file",
        "--lock-path",
        dest="lock_path",
        type=Path,
        help="explicit POSIX flock path",
    )
    parser.add_argument(
        "--metadata",
        "--metadata-path",
        dest="metadata_path",
        type=Path,
        help="explicit atomic JSON metadata path",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    acquire_parser = subparsers.add_parser(
        "acquire",
        help="acquire the resource flock and create a fresh lease",
    )
    _add_path_options(acquire_parser)
    acquire_parser.add_argument("--owner-id", required=True)
    acquire_parser.add_argument("--pid", type=int)
    acquire_parser.add_argument("--native-pid", type=int)
    acquire_parser.add_argument("--native-state", default="acquiring")
    acquire_parser.add_argument("--wait", action="store_true")
    acquire_parser.add_argument("--timeout", type=float, dest="timeout_seconds")
    acquire_parser.add_argument("--poll-seconds", type=float, default=DEFAULT_POLL_SECONDS)
    acquire_parser.add_argument(
        "--hold",
        action="store_true",
        help="keep the lease process alive and accept JSON commands on stdin",
    )

    heartbeat_parser = subparsers.add_parser(
        "heartbeat",
        help="CAS-update owner state while another process holds the flock",
    )
    _add_path_options(heartbeat_parser)
    heartbeat_parser.add_argument("--lease-id", required=True)
    heartbeat_parser.add_argument("--owner-id")
    heartbeat_parser.add_argument("--native-pid", type=int)
    heartbeat_parser.add_argument("--native-state")
    heartbeat_parser.add_argument("--in-use", type=_parse_bool)
    heartbeat_parser.add_argument("--release-ready", type=_parse_bool)
    heartbeat_parser.add_argument("--last-action-at")

    probe_parser = subparsers.add_parser(
        "probe",
        help="validate a holder response; no response is LOCK_BLOCKED",
    )
    _add_path_options(probe_parser)
    probe_parser.add_argument("--lease-id", required=True)
    response_group = probe_parser.add_mutually_exclusive_group()
    response_group.add_argument("--owner-response-json")
    response_group.add_argument("--owner-response-file", type=Path)
    probe_parser.add_argument("--max-response-age", type=float, dest="max_age_seconds")

    release_parser = subparsers.add_parser(
        "release",
        help="release an already-idle lease when this process can obtain the flock",
    )
    _add_path_options(release_parser)
    release_parser.add_argument("--lease-id", required=True)
    release_parser.add_argument("--owner-id")
    release_parser.add_argument("--native-state", default="teardown_complete")

    reclaim_parser = subparsers.add_parser(
        "reclaim",
        help="reclaim only a dead-owner lease with matching teardown evidence",
    )
    _add_path_options(reclaim_parser)
    reclaim_parser.add_argument("--lease-id", required=True)
    reclaim_parser.add_argument("--owner-id")
    reclaim_parser.add_argument(
        "--teardown-evidence",
        "--evidence",
        dest="teardown_evidence",
        type=Path,
        required=True,
    )

    status_parser = subparsers.add_parser(
        "status",
        help="read current lease metadata without mutating it",
    )
    _add_path_options(status_parser)

    return parser


def _paths_from_args(args: argparse.Namespace, *, resource_required: bool = False) -> LeasePaths:
    if resource_required and not args.resource:
        raise ValueError("acquire requires --resource")
    return resolve_paths(
        args.resource,
        state_dir=args.state_dir,
        lock_path=args.lock_path,
        metadata_path=args.metadata_path,
    )


def _main(args: argparse.Namespace) -> int:
    if args.command == "acquire":
        paths = _paths_from_args(args, resource_required=True)
        lease = SimulatorLease.acquire(
            args.resource,
            args.owner_id,
            state_dir=args.state_dir,
            lock_path=paths.lock_path,
            metadata_path=paths.metadata_path,
            pid=args.pid,
            native_pid=args.native_pid,
            native_state=args.native_state,
            wait=args.wait or args.timeout_seconds is not None,
            timeout_seconds=args.timeout_seconds,
            poll_seconds=args.poll_seconds,
        )
        if args.hold:
            return _hold_loop(lease, sys.stdin)
        payload = _lease_payload(lease)
        # A command-line process cannot keep a useful flock after it exits.
        # Make the short-lived behavior explicit instead of pretending that a
        # lease token alone owns the simulator.  Real holders use --hold or the
        # in-process API.
        lease.release()
        payload["status"] = "ACQUIRED_AND_RELEASED"
        payload["metadata"] = lease._metadata
        return _print_payload(payload)

    if args.command == "heartbeat":
        paths = _paths_from_args(args)
        metadata = heartbeat(
            paths.metadata_path,
            args.lease_id,
            lock_path=paths.lock_path,
            owner_id=args.owner_id,
            native_state=args.native_state,
            native_pid=args.native_pid,
            in_use=args.in_use,
            release_ready=args.release_ready,
            last_action_at=args.last_action_at,
        )
        return _print_payload(
            {
                "status": "HEARTBEAT",
                "lease_id": metadata["lease_id"],
                "metadata": metadata,
                "owner_response": _owner_response_from_metadata(
                    metadata,
                    responded_at=_utc_now(),
                ),
            }
        )

    if args.command == "probe":
        paths = _paths_from_args(args)
        response: Mapping[str, Any] | None = None
        if args.owner_response_json is not None:
            raw = json.loads(args.owner_response_json)
            if not isinstance(raw, Mapping):
                raise ValueError("--owner-response-json must contain a JSON object")
            response = raw
        elif args.owner_response_file is not None:
            response = _load_owner_response_file(args.owner_response_file)
        return _print_payload(
            probe(
                paths.metadata_path,
                args.lease_id,
                lock_path=paths.lock_path,
                owner_response=response,
                max_age_seconds=args.max_age_seconds,
            )
        )

    if args.command == "release":
        paths = _paths_from_args(args)
        return _print_payload(
            release(
                paths.metadata_path,
                args.lease_id,
                lock_path=paths.lock_path,
                owner_id=args.owner_id,
                native_state=args.native_state,
            )
        )

    if args.command == "reclaim":
        paths = _paths_from_args(args)
        return _print_payload(
            reclaim(
                paths.metadata_path,
                args.lease_id,
                lock_path=paths.lock_path,
                owner_id=args.owner_id,
                teardown_evidence=args.teardown_evidence,
            )
        )

    if args.command == "status":
        paths = _paths_from_args(args)
        metadata = read_metadata(paths.metadata_path, lock_path=paths.lock_path)
        return _print_payload(
            {
                "status": "HELD" if metadata["state"] not in FREE_STATES else "FREE",
                "lease_id": metadata["lease_id"],
                "metadata": metadata,
            }
        )

    raise AssertionError(f"unhandled command: {args.command}")


def _print_payload(payload: Mapping[str, Any]) -> int:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        return _main(args)
    except LeaseError as exc:
        _print_payload(exc.as_payload())
        return exc.exit_code
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        _print_payload({"status": "ERROR", "error": str(exc)})
        return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFAULT_STATE_DIR",
    "EXIT_ERROR",
    "EXIT_LEASE_MISMATCH",
    "EXIT_LEASE_NOT_HELD",
    "EXIT_LOCK_BLOCKED",
    "EXIT_LOCK_BUSY",
    "EXIT_METADATA_ERROR",
    "EXIT_NO_LEASE",
    "EXIT_OK",
    "EXIT_USAGE",
    "LeaseError",
    "LeaseMismatchError",
    "LeaseNotHeldError",
    "LeasePaths",
    "LockBlockedError",
    "LockBusyError",
    "MetadataError",
    "NoLeaseError",
    "OWNER_RESPONSE_FIELDS",
    "REQUIRED_METADATA_FIELDS",
    "SimulatorLease",
    "heartbeat",
    "main",
    "probe",
    "read_metadata",
    "reclaim",
    "release",
    "resolve_paths",
]
