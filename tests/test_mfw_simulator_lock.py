from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tools.mfw_simulator_lock import (
    EXIT_LOCK_BLOCKED,
    EXIT_LOCK_BUSY,
    LeaseMismatchError,
    LockBlockedError,
    SimulatorLease,
    heartbeat,
    probe,
    read_metadata,
    reclaim,
)


ROOT = Path(__file__).parents[1]
LOCK_CLI = ROOT / "tools/mfw_simulator_lock.py"


def _cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(LOCK_CLI), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _start_holder(tmp_path: Path, owner_id: str = "worker:holder") -> subprocess.Popen[str]:
    return subprocess.Popen(
        [
            sys.executable,
            str(LOCK_CLI),
            "acquire",
            "--resource",
            "emulator-5556",
            "--state-dir",
            str(tmp_path),
            "--owner-id",
            owner_id,
            "--hold",
        ],
        cwd=ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
    )


def _read_line(process: subprocess.Popen[str]) -> dict[str, Any]:
    assert process.stdout is not None
    line = process.stdout.readline()
    assert line
    payload = json.loads(line)
    assert isinstance(payload, dict)
    return payload


def _send_holder_command(process: subprocess.Popen[str], command: dict[str, Any]) -> dict[str, Any]:
    assert process.stdin is not None
    process.stdin.write(json.dumps(command) + "\n")
    process.stdin.flush()
    return _read_line(process)


def _paths(tmp_path: Path) -> tuple[Path, Path]:
    lock = tmp_path / "simulator.lock"
    metadata = tmp_path / "simulator.lock.json"
    return lock, metadata


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_competing_acquire_is_serialized_by_kernel_flock(tmp_path: Path) -> None:
    holder = _start_holder(tmp_path)
    try:
        acquired = _read_line(holder)
        assert acquired["status"] == "ACQUIRED"
        lease_id = acquired["lease_id"]
        assert lease_id

        second = _cli(
            "acquire",
            "--resource",
            "emulator-5556",
            "--state-dir",
            str(tmp_path),
            "--owner-id",
            "worker:second",
        )
        assert second.returncode == EXIT_LOCK_BUSY
        assert json.loads(second.stdout)["status"] == "LOCK_BUSY"
        assert read_metadata(Path(acquired["metadata_file"]))["lease_id"] == lease_id

        released = _send_holder_command(holder, {"command": "release"})
        assert released["status"] == "RELEASED"
        assert holder.wait(timeout=5) == 0
    finally:
        if holder.poll() is None:
            holder.kill()
            holder.wait(timeout=5)


def test_acquire_metadata_contains_required_lease_fields(tmp_path: Path) -> None:
    lock, metadata_path = _paths(tmp_path)
    lease = SimulatorLease.acquire(
        "emulator-5556",
        "worker:fields",
        lock_path=lock,
        metadata_path=metadata_path,
        native_state="game_start",
    )
    try:
        metadata = read_metadata(metadata_path, lock_path=lock)
        assert {
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
        } <= metadata.keys()
        assert metadata["resource"] == "emulator-5556"
        assert metadata["lease_id"] == lease.lease_id
        assert metadata["owner_id"] == "worker:fields"
        assert metadata["state"] == "held_active"
        assert metadata["in_use"] is True
        assert metadata["release_ready"] is False
    finally:
        lease.release()


def test_lease_id_is_a_cas_token_and_old_owner_cannot_update_new_lease(
    tmp_path: Path,
) -> None:
    lock, metadata_path = _paths(tmp_path)
    first = SimulatorLease.acquire(
        "emulator-5556",
        "worker:first",
        lock_path=lock,
        metadata_path=metadata_path,
    )
    first_id = first.lease_id
    first.release()

    second = SimulatorLease.acquire(
        "emulator-5556",
        "worker:second",
        lock_path=lock,
        metadata_path=metadata_path,
    )
    try:
        with pytest.raises(LeaseMismatchError):
            heartbeat(
                metadata_path,
                first_id,
                lock_path=lock,
                native_state="stale-owner-write",
            )
        current = read_metadata(metadata_path, lock_path=lock)
        assert current["lease_id"] == second.lease_id
        assert current["owner_id"] == "worker:second"
        assert current["native_state"] != "stale-owner-write"
    finally:
        second.release()


def test_heartbeat_updates_state_and_owner_response_fields(tmp_path: Path) -> None:
    lock, metadata_path = _paths(tmp_path)
    lease = SimulatorLease.acquire(
        "emulator-5556",
        "worker:heartbeat",
        lock_path=lock,
        metadata_path=metadata_path,
    )
    try:
        updated = lease.heartbeat(native_state="business_task", last_action_at=None)
        assert updated["native_state"] == "business_task"
        assert updated["in_use"] is True
        assert updated["last_owner_response_at"] is not None
        response = lease.owner_response()
        assert response == {
            "lease_id": lease.lease_id,
            "in_use": True,
            "native_state": "business_task",
            "pid_alive": True,
            "last_action_at": updated["last_action_at"],
            "release_ready": False,
            "responded_at": response["responded_at"],
        }
    finally:
        lease.release()


def test_probe_records_a_fresh_owner_response(tmp_path: Path) -> None:
    lock, metadata_path = _paths(tmp_path)
    lease = SimulatorLease.acquire(
        "emulator-5556",
        "worker:probe",
        lock_path=lock,
        metadata_path=metadata_path,
    )
    try:
        response = lease.owner_response()
        result = probe(
            metadata_path,
            lease.lease_id,
            lock_path=lock,
            owner_response=response,
        )
        assert result["status"] == "ACTIVE"
        assert result["owner_response"]["lease_id"] == lease.lease_id
        assert result["owner_response"]["pid_alive"] is True
        current = read_metadata(metadata_path, lock_path=lock)
        assert current["last_probe_at"] is not None
        assert current["last_owner_response_at"] is not None
        assert current["in_use"] is True
    finally:
        lease.release()


def test_missing_probe_response_is_blocked_and_never_becomes_idle(tmp_path: Path) -> None:
    lock, metadata_path = _paths(tmp_path)
    lease = SimulatorLease.acquire(
        "emulator-5556",
        "worker:no-response",
        lock_path=lock,
        metadata_path=metadata_path,
    )
    try:
        with pytest.raises(LockBlockedError) as exc_info:
            probe(metadata_path, lease.lease_id, lock_path=lock)
        assert exc_info.value.status == "LOCK_BLOCKED"
        assert exc_info.value.details["reason"] == "no_owner_response"
        current = read_metadata(metadata_path, lock_path=lock)
        assert current["state"] == "suspect"
        assert current["in_use"] is True
        assert current["release_ready"] is False
    finally:
        lease.release()


def test_owner_idle_then_release_allows_next_owner(tmp_path: Path) -> None:
    lock, metadata_path = _paths(tmp_path)
    lease = SimulatorLease.acquire(
        "emulator-5556",
        "worker:idle",
        lock_path=lock,
        metadata_path=metadata_path,
    )
    lease.heartbeat(
        native_state="teardown_complete",
        in_use=False,
        release_ready=True,
    )
    response = lease.owner_response()
    result = probe(
        metadata_path,
        lease.lease_id,
        lock_path=lock,
        owner_response=response,
    )
    assert result["status"] == "IDLE"
    released = lease.release()
    assert released["state"] == "released"
    assert released["in_use"] is False
    assert released["release_ready"] is True

    next_lease = SimulatorLease.acquire(
        "emulator-5556",
        "worker:next",
        lock_path=lock,
        metadata_path=metadata_path,
    )
    try:
        assert next_lease.lease_id != lease.lease_id
    finally:
        next_lease.release()


def test_external_release_requires_idle_and_works_after_holder_exit(
    tmp_path: Path,
) -> None:
    holder = _start_holder(tmp_path, "worker:external-release")
    acquired = _read_line(holder)
    lease_id = str(acquired["lease_id"])
    lock_path = Path(acquired["lock_file"])
    metadata_path = Path(acquired["metadata_file"])
    try:
        blocked = _cli(
            "release",
            "--lock-file",
            str(lock_path),
            "--metadata",
            str(metadata_path),
            "--lease-id",
            lease_id,
        )
        assert blocked.returncode == EXIT_LOCK_BLOCKED
        assert json.loads(blocked.stdout)["reason"] == "lock_busy"

        heartbeat_result = _cli(
            "heartbeat",
            "--lock-file",
            str(lock_path),
            "--metadata",
            str(metadata_path),
            "--lease-id",
            lease_id,
            "--native-state",
            "teardown_complete",
            "--in-use",
            "false",
            "--release-ready",
            "true",
        )
        assert heartbeat_result.returncode == 0
        assert json.loads(heartbeat_result.stdout)["metadata"]["state"] == "idle"

        holder.kill()
        assert holder.wait(timeout=5) is not None
        released = _cli(
            "release",
            "--lock-file",
            str(lock_path),
            "--metadata",
            str(metadata_path),
            "--lease-id",
            lease_id,
        )
        assert released.returncode == 0
        assert json.loads(released.stdout)["status"] == "RELEASED"
    finally:
        if holder.poll() is None:
            holder.kill()
            holder.wait(timeout=5)


def test_reclaim_requires_dead_owner_and_teardown_evidence(tmp_path: Path) -> None:
    holder = _start_holder(tmp_path, "worker:crashed")
    acquired = _read_line(holder)
    lease_id = str(acquired["lease_id"])
    metadata_path = Path(acquired["metadata_file"])
    lock_path = Path(acquired["lock_file"])
    owner_pid = int(acquired["metadata"]["pid"])
    try:
        holder.kill()
        assert holder.wait(timeout=5) is not None

        with pytest.raises(LockBlockedError) as missing_evidence:
            reclaim(
                metadata_path,
                lease_id,
                lock_path=lock_path,
            )
        assert missing_evidence.value.details["reason"] == "missing_teardown_evidence"

        evidence_path = tmp_path / "teardown-evidence.json"
        _write_json(
            evidence_path,
            {
                "schema_version": 1,
                "lease_id": lease_id,
                "owner_pid": owner_pid,
                "native_pid": None,
                "native_state": "teardown_complete",
                "teardown_complete": True,
                "verified_at": "2026-08-17T00:00:00Z",
            },
        )
        reclaimed = reclaim(
            metadata_path,
            lease_id,
            lock_path=lock_path,
            teardown_evidence=evidence_path,
        )
        assert reclaimed["status"] == "RECLAIMED"
        assert reclaimed["metadata"]["state"] == "reclaimed"
        assert reclaimed["metadata"]["in_use"] is False
        assert reclaimed["metadata"]["release_ready"] is True

        replacement = SimulatorLease.acquire(
            "emulator-5556",
            "worker:replacement",
            lock_path=lock_path,
            metadata_path=metadata_path,
        )
        replacement.release()
    finally:
        if holder.poll() is None:
            holder.kill()
            holder.wait(timeout=5)


def test_reclaim_blocks_live_owner_even_with_evidence(tmp_path: Path) -> None:
    lock, metadata_path = _paths(tmp_path)
    lease = SimulatorLease.acquire(
        "emulator-5556",
        "worker:live",
        lock_path=lock,
        metadata_path=metadata_path,
    )
    evidence = {
        "lease_id": lease.lease_id,
        "native_state": "teardown_complete",
        "teardown_complete": True,
    }
    try:
        with pytest.raises(LockBlockedError) as exc_info:
            reclaim(
                metadata_path,
                lease.lease_id,
                lock_path=lock,
                teardown_evidence=evidence,
            )
        assert exc_info.value.details["reason"] in {"owner_alive", "lock_busy"}
        assert read_metadata(metadata_path, lock_path=lock)["state"] == "held_active"
    finally:
        lease.release()


def test_process_crash_releases_kernel_lock_without_deleting_lock_file(
    tmp_path: Path,
) -> None:
    holder = _start_holder(tmp_path, "worker:crash-release")
    acquired = _read_line(holder)
    lock_path = Path(acquired["lock_file"])
    metadata_path = Path(acquired["metadata_file"])
    old_lease_id = str(acquired["lease_id"])
    try:
        holder.kill()
        assert holder.wait(timeout=5) is not None
        assert lock_path.is_file()
        stale = read_metadata(metadata_path, lock_path=lock_path)
        assert stale["lease_id"] == old_lease_id
        assert stale["state"] == "held_active"

        # The kernel lock is available again even though the metadata is still
        # active.  The helper must not turn that crash into an unverified
        # takeover; reclaim with teardown evidence is the only safe path.
        raw_fd = os.open(lock_path, os.O_RDWR)
        try:
            fcntl.flock(raw_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            fcntl.flock(raw_fd, fcntl.LOCK_UN)
            os.close(raw_fd)
        with pytest.raises(LockBlockedError) as blocked:
            SimulatorLease.acquire(
                "emulator-5556",
                "worker:after-crash",
                lock_path=lock_path,
                metadata_path=metadata_path,
            )
        assert blocked.value.details["reason"] == "stale_lease"
    finally:
        if holder.poll() is None:
            holder.kill()
            holder.wait(timeout=5)


def test_context_exception_unlocks_kernel_but_preserves_stale_metadata(
    tmp_path: Path,
) -> None:
    lock, metadata_path = _paths(tmp_path)
    lease = SimulatorLease.acquire(
        "emulator-5556",
        "worker:exception",
        lock_path=lock,
        metadata_path=metadata_path,
    )
    lease_id = lease.lease_id
    with pytest.raises(RuntimeError, match="native failure"):
        with lease:
            raise RuntimeError("native failure")

    assert lease.closed
    metadata = read_metadata(metadata_path, lock_path=lock)
    assert metadata["lease_id"] == lease_id
    assert metadata["state"] == "held_active"
    assert metadata["in_use"] is True

    raw_fd = os.open(lock, os.O_RDWR)
    try:
        fcntl.flock(raw_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        fcntl.flock(raw_fd, fcntl.LOCK_UN)
        os.close(raw_fd)

    with pytest.raises(LockBlockedError) as blocked:
        SimulatorLease.acquire(
            "emulator-5556",
            "worker:replacement",
            lock_path=lock,
            metadata_path=metadata_path,
        )
    assert blocked.value.details["reason"] == "stale_lease"


def test_cli_probe_accepts_holder_response_json(tmp_path: Path) -> None:
    lock, metadata_path = _paths(tmp_path)
    lease = SimulatorLease.acquire(
        "emulator-5556",
        "worker:cli-probe",
        lock_path=lock,
        metadata_path=metadata_path,
    )
    try:
        response = json.dumps(lease.owner_response())
        result = _cli(
            "probe",
            "--lock-file",
            str(lock),
            "--metadata",
            str(metadata_path),
            "--lease-id",
            lease.lease_id,
            "--owner-response-json",
            response,
        )
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["status"] == "ACTIVE"
        assert payload["owner_response"]["lease_id"] == lease.lease_id
    finally:
        lease.release()


def test_cli_probe_without_response_returns_nonzero_json_block(tmp_path: Path) -> None:
    lock, metadata_path = _paths(tmp_path)
    lease = SimulatorLease.acquire(
        "emulator-5556",
        "worker:cli-block",
        lock_path=lock,
        metadata_path=metadata_path,
    )
    try:
        result = _cli(
            "probe",
            "--lock-file",
            str(lock),
            "--metadata",
            str(metadata_path),
            "--lease-id",
            lease.lease_id,
        )
        assert result.returncode == EXIT_LOCK_BLOCKED
        payload = json.loads(result.stdout)
        assert payload["status"] == "LOCK_BLOCKED"
        assert payload["reason"] == "no_owner_response"
    finally:
        lease.release()
