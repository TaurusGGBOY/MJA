from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Sequence

from agent.android.adb import AdbDevice
from agent.android.avd import AndroidAvd
from agent.android.config import AndroidConfig
from agent.android.game import GameInstaller
from agent.android.login import LoginGate
from agent.android.sdk import AndroidSdk
from agent.diagnostics import write_android_result
from agent.errors import ErrorCode, MJAError
from tools.android_maa_config import CLI_COMMAND, build_android_maa_config

ROOT = Path(__file__).resolve().parents[1]

# MaaPiCli normally exits when the registered CustomAction returns. A native
# runner bug or an OCR/controller deadlock must not turn that expectation into
# an unbounded wait for the outer daily supervisor. These are child-process
# budgets only; startup/login remains governed by the Android configuration and
# the workflow-specific budgets in ``agent.actions.daily_workflow``.
_ANDROID_TASK_TIMEOUT_SECONDS = {
    # The first daily job is also the update gate.  A client hot-update can
    # legitimately download several gigabytes before the business workflow
    # can reach its first home boundary.
    "mail_reward_daily": 1_200.0,
    "shop_free_gift_daily": 240.0,
    # Keep the child lifetime above the workflow's 240-second OCR budget so
    # the supervisor can consume the task-local terminal result instead of
    # killing a still-progressing weekly-tab transition at the same deadline.
    "weekly_free_gift_monday": 360.0,
    "trial_sword_daily": 240.0,
    "free_appraisal_daily": 240.0,
    "buy_tea_daily": 360.0,
    "collection_deployment_daily": 420.0,
    "hero_dispatch_daily": 720.0,
    "shadow_ruins_daily": 1_980.0,
    "spend_condensate_daily": 600.0,
    "martial_study_breakthrough_daily": 720.0,
    "eat_stamina_food_daily": 720.0,
    "dungeon_sweep_daily": 600.0,
    "jianlin_resource_condensate_stamina_daily": 2_100.0,
    "ring_challenge_daily": 1_500.0,
    "daily_task_reward_claim_daily": 480.0,
    "battle_pass_reward_daily": 480.0,
}
_DEFAULT_ANDROID_TASK_TIMEOUT_SECONDS = 600.0
class AndroidRun:
    def __init__(
        self,
        config: AndroidConfig | None = None,
        *,
        install_root: Path = ROOT / "install",
        runner: Callable[..., Any] = subprocess.run,
        spawn: Callable[..., Any] | None = None,
    ) -> None:
        self.config = config or AndroidConfig.load()
        self.install_root = install_root
        self.runner = runner
        self.spawn = spawn
        # Keep the Unity process reusable across task-local Maa children. The
        # game has a native startup guard which can terminate a cleanly
        # force-stopped process on the next launch; an explicit
        # ``fresh_process`` request remains available for recovery/debugging.
        # Failed runs deliberately leave their surface alone for diagnosis.
        self._last_task_succeeded = False

    def run(
        self,
        task_name: str = "mail_smoke_test",
        *,
        stop: bool = False,
        wipe_data: bool = False,
        start_session: bool = True,
        fresh_process: bool = False,
        timeout_seconds: float | None = None,
    ) -> int:
        started_at = datetime.now().astimezone().isoformat(timespec="microseconds")
        debug_root = self.install_root / "debug" / "runs"
        result_directory = debug_root / "android" / datetime.now().strftime("%Y%m%dT%H%M%S%f%z")
        result_path = result_directory / "result.json"
        status = "error"
        child: Any | None = None
        sdk = AndroidSdk(self.config, runner=self.runner)
        avd: AndroidAvd | None = None
        process: Any | None = None
        package_name: str | None = self.config.package_name
        failure_code: str | None = None
        child_timeout = (
            self._task_timeout_seconds(task_name)
            if timeout_seconds is None
            else float(timeout_seconds)
        )
        if child_timeout <= 0:
            raise ValueError("timeout_seconds must be positive")
        try:
            paths = sdk.ensure(install_missing=True)
            avd = AndroidAvd(self.config, paths, runner=self.runner)
            process = avd.start(wipe_data=wipe_data)
            device = AdbDevice(self.config, paths, runner=self.runner)
            device.wait_ready()
            ensure_phantom_monitor_disabled = getattr(
                device,
                "ensure_phantom_process_monitor_disabled",
                None,
            )
            if callable(ensure_phantom_monitor_disabled):
                ensure_phantom_monitor_disabled()
            ensure_selinux_mode = getattr(device, "ensure_selinux_mode", None)
            if callable(ensure_selinux_mode):
                ensure_selinux_mode(self.config.selinux_mode)
            package_name = GameInstaller(self.config, device).ensure_installed()
            runtime_config = replace(self.config, package_name=package_name)
            if start_session:
                self._prepare_game_session(
                    device,
                    runtime_config,
                    package_name,
                    restart_if_running=fresh_process,
                )
            config_path = self.install_root / "config" / "maa_pi_config.json"
            config_path.parent.mkdir(parents=True, exist_ok=True)
            maa_config = build_android_maa_config(
                paths.adb,
                runtime_config.serial,
                task_name,
            )
            config_path.write_text(
                json.dumps(maa_config, indent=2) + "\n",
                encoding="utf-8",
            )
            if start_session:
                # Config generation and Maa controller startup form a small
                # hand-off window after the main login/health gate.  Recheck
                # the live foreground and process at the last possible point
                # before spawning Maa, and recover once if Android returned
                # to Launcher in that interval.
                self._stabilize_game_handoff(
                    device,
                    runtime_config,
                    package_name,
                )
            child = self._spawn(
                CLI_COMMAND,
                adb_path=paths.adb,
                serial=runtime_config.serial,
                package_name=package_name,
            )
            try:
                # This legacy diagnostic command has one bounded child wait.
                # Native MFW Tasker events, result evidence, and queue stop
                # semantics belong to the embedded Agent/Pipeline path; this
                # helper must not infer them from logs or schedule recovery.
                result = self._wait_for_child(child, child_timeout)
            except subprocess.TimeoutExpired:
                # Leave the emulator surface untouched; only the native child
                # is terminated so the next isolated task can start its own
                # session boundary.
                status = "failed"
                failure_code = "WORKFLOW_TIMEOUT"
                return 124
            status = "succeeded" if result == 0 else "failed"
            if status == "failed":
                failure_code = "MAA_CHILD_EXIT_NONZERO"
            return result
        except Exception as exc:
            failure_code = getattr(getattr(exc, "code", None), "value", None)
            failure_code = str(failure_code or "ANDROID_RUN_FAILED")
            # A live system-UI ANR is a shared runtime failure, not a
            # task-local workflow result. The outer supervisor uses this code
            # to stop the remaining sequence after this child is terminated.
            status = (
                "failed"
                if failure_code == ErrorCode.ANDROID_SYSTEM_UI_NOT_RESPONDING.value
                else "error"
            )
            raise
        finally:
            self._stop_child(child)
            if status != "succeeded":
                self._finalize_task_artifacts(
                    debug_root,
                    task_name,
                    started_at=started_at,
                    error_code=failure_code or "ANDROID_RUN_FAILED",
                )
            package_for_result = self.config.package_name or "unknown"
            package_for_result = package_name or package_for_result
            finished_at = datetime.now().astimezone().isoformat(timespec="microseconds")
            write_android_result(
                result_path,
                avd=self.config.avd_name,
                serial=self.config.serial,
                package=package_for_result,
                display_size=self.config.display_size,
                task_name=task_name,
                started_at=started_at,
                finished_at=finished_at,
                status=status,
            )
            # A failed run is an inspection point: keep the emulator and
            # game exactly where Maa stopped so a human can direct the next
            # action.
            should_stop = status == "succeeded" and (
                stop or not self.config.keep_running
            )
            if avd is not None and should_stop:
                avd.stop()
            process_running = (
                process is not None
                and getattr(process, "poll", lambda: None)() is None
                and should_stop
            )
            if process_running:
                process.terminate()
            self._last_task_succeeded = status == "succeeded"

    @staticmethod
    def _prepare_game_session(
        device: AdbDevice,
        runtime_config: AndroidConfig,
        package_name: str,
        *,
        restart_if_running: bool = False,
    ) -> None:
        """Start and health-check one isolated task session.

        The emulator can leave a previous task's Unity process behind while a
        launcher, camera, or system surface owns the foreground.  A normal
        ``start_app`` is intentionally attempted first; only the typed,
        recoverable foreground/process failures get one force-stop/start
        recovery. Login, storage, network, and memory failures remain
        fail-closed and are reported to this task only.
        """

        login = LoginGate(runtime_config)
        for attempt in range(2):
            if attempt == 0 and not restart_if_running:
                if not AndroidRun._game_process_is_foreground(device, package_name):
                    device.start_app(package_name)
            else:
                restart = getattr(device, "restart", None)
                if callable(restart):
                    restart(package_name)
                else:
                    device.start_app(package_name)
            device.dismiss_first_run_overlay()
            try:
                login.wait_until_ready(
                    device,
                    # Isolated task sessions are force-stopped before launch;
                    # wait for the title/home template rather than accepting
                    # a colorful Unity loading screen as ready.
                    require_interactive=restart_if_running,
                )
                device.require_runtime_health()
                require_memory_health = getattr(device, "require_memory_health", None)
                if callable(require_memory_health):
                    require_memory_health()
                require_game_process = getattr(device, "require_game_process", None)
                if callable(require_game_process):
                    require_game_process(package_name)
                return
            except MJAError as exc:
                if attempt == 0 and exc.code in {
                    ErrorCode.ANDROID_GAME_NOT_FOREGROUND,
                    ErrorCode.ANDROID_GAME_PROCESS_DIED,
                }:
                    continue
                raise

    @staticmethod
    def _game_process_is_foreground(device: AdbDevice, package_name: str) -> bool:
        """Return whether an existing game process can be reused safely."""

        try:
            foreground_package = getattr(device, "foreground_package", None)
            if not callable(foreground_package) or foreground_package() != package_name:
                return False
            process_id = getattr(device, "game_process_id", None)
            if callable(process_id) and process_id(package_name) is None:
                return False
            return True
        except (MJAError, OSError):
            return False

    @classmethod
    def _stabilize_game_handoff(
        cls,
        device: AdbDevice,
        runtime_config: AndroidConfig,
        package_name: str,
    ) -> None:
        """Require a stable game foreground immediately before Maa starts.

        The normal session preparation performs the full login, storage,
        network, renderer, memory, and process gates.  This final hand-off
        check specifically closes the race where Android returns to Launcher
        after those checks but before the Maa child reaches its first task
        boundary.  Only foreground/process loss is recovered; every other
        typed health failure is propagated unchanged.
        """

        recoverable = {
            ErrorCode.ANDROID_GAME_NOT_FOREGROUND,
            ErrorCode.ANDROID_GAME_PROCESS_DIED,
        }

        def require_current_runtime() -> None:
            device.require_runtime_health()
            require_process = getattr(device, "require_game_process", None)
            if callable(require_process):
                require_process(package_name)

        try:
            require_current_runtime()
            return
        except MJAError as exc:
            if exc.code not in recoverable:
                raise

        cls._prepare_game_session(
            device,
            runtime_config,
            package_name,
            restart_if_running=True,
        )
        # Never trust recovery by return value alone: prove the foreground
        # and process again immediately before the child is spawned.
        require_current_runtime()

    @staticmethod
    def _task_timeout_seconds(task_name: str) -> float:
        canonical = str(task_name).strip().lower()
        return _ANDROID_TASK_TIMEOUT_SECONDS.get(
            canonical,
            _DEFAULT_ANDROID_TASK_TIMEOUT_SECONDS,
        )

    @staticmethod
    def _wait_for_child(child: Any, timeout_seconds: float) -> int:
        """Wait with a hard bound while retaining small test doubles."""

        wait = getattr(child, "wait")
        try:
            return int(wait(timeout=timeout_seconds))
        except TypeError as exc:
            # Existing unit-test fakes expose wait() without a keyword. Real
            # subprocess.Popen accepts timeout and never takes this branch.
            if "timeout" not in str(exc):
                raise
            return int(wait())

    @staticmethod
    def _stop_child(child: Any | None) -> None:
        if child is None:
            return
        poll = getattr(child, "poll", None)
        if not callable(poll):
            return
        try:
            active = poll() is None
        except Exception:
            active = True
        if not active:
            return
        if not AndroidRun._signal_child_group(child, signal.SIGTERM):
            terminate = getattr(child, "terminate", None)
            if callable(terminate):
                try:
                    terminate()
                except Exception:
                    pass
        try:
            AndroidRun._wait_for_child(child, 5.0)
            return
        except subprocess.TimeoutExpired:
            if not AndroidRun._signal_child_group(child, signal.SIGKILL):
                kill = getattr(child, "kill", None)
                if callable(kill):
                    try:
                        kill()
                    except Exception:
                        pass
        except Exception:
            # A custom child/test double may raise while waiting after
            # terminate. It is still potentially alive; continue to the
            # hard-kill path instead of returning with an unreaped process.
            pass
        try:
            AndroidRun._wait_for_child(child, 5.0)
        except Exception:
            pass

    @staticmethod
    def _signal_child_group(child: Any, signal_number: int) -> bool:
        """Signal the isolated Maa process group when a real Popen is used."""

        pid = getattr(child, "pid", None)
        if not isinstance(pid, int) or pid <= 1:
            return False
        try:
            group = os.getpgid(pid)
            # ``_spawn`` creates a new session, so the group must be the child
            # itself. Refuse to signal our own runner group if a test double or
            # a custom launcher violates that contract.
            if group != pid:
                return False
            os.killpg(group, signal_number)
            return True
        except (OSError, ProcessLookupError):
            return False

    @staticmethod
    def _finalize_task_artifacts(
        debug_root: Path,
        task_name: str,
        *,
        started_at: str,
        error_code: str,
    ) -> None:
        """Close a child-created diagnostic run left open by a hard stop."""

        task_root = Path(debug_root) / "daily" / str(task_name).strip().lower()
        try:
            start_timestamp = datetime.fromisoformat(started_at).timestamp()
        except ValueError:
            start_timestamp = 0.0
        candidates: list[Path] = []
        if task_root.is_dir():
            for child_dir in task_root.iterdir():
                if not child_dir.is_dir():
                    continue
                try:
                    if child_dir.stat().st_mtime >= start_timestamp - 1.0:
                        candidates.append(child_dir)
                except OSError:
                    continue
        candidates.sort(key=lambda path: path.stat().st_mtime_ns, reverse=True)
        if candidates:
            directory = candidates[0]
        else:
            directory = task_root / datetime.now().astimezone().isoformat(
                timespec="microseconds"
            )
            directory.mkdir(parents=True, exist_ok=True)

        finished_at = datetime.now().astimezone().isoformat(timespec="microseconds")
        run_path = directory / "run.json"
        try:
            payload = json.loads(run_path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            payload = {
                "schema_version": 1,
                "started_at": started_at,
                "components": {},
                "window": None,
                "events": [],
            }
        if not isinstance(payload, dict):
            payload = {}
        # Maa may have flushed a truthful terminal diagnostic immediately
        # before the native child exits.  Only close an open/missing record;
        # never replace a task-local error with the supervisor's generic
        # child-exit code after the task has already recorded its outcome.
        if payload.get("status") not in {"succeeded", "failed"}:
            payload.update(
                {
                    "status": "failed",
                    "finished_at": finished_at,
                    "duration_ms": payload.get("duration_ms"),
                    "error": {
                        "code": error_code,
                        "message": f"Android task runner ended with {error_code}",
                    },
                }
            )
            run_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

        result_path = directory / "result.json"
        try:
            result_payload = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            result_payload = None
        if not isinstance(result_payload, dict) or result_payload.get("status") != "failed":
            existing_postcondition = (
                result_payload.get("postcondition")
                if isinstance(result_payload, dict)
                else None
            )
            existing_counts = (
                result_payload.get("action_counts", {})
                if isinstance(result_payload, dict)
                else {}
            )
            result_path.write_text(
                json.dumps(
                    {
                        "task_id": str(task_name).strip().upper(),
                        "status": "failed",
                        "postcondition": existing_postcondition or "android_runner",
                        "action_counts": existing_counts
                        if isinstance(existing_counts, dict)
                        else {},
                        "error_code": error_code,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        elif not isinstance(result_payload.get("error_code"), str) or not result_payload[
            "error_code"
        ].strip():
            # Older workflow definitions could write a failed terminal result
            # without a code. Never publish a failed task with a null/blank
            # machine-readable reason; the supervisor needs a task-local
            # explanation even when it must use the runner fallback.
            result_payload["error_code"] = error_code
            result_path.write_text(
                json.dumps(result_payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

    def _spawn(
        self,
        argv: Sequence[str],
        *,
        adb_path: Path | None = None,
        serial: str | None = None,
        package_name: str | None = None,
    ) -> Any:
        if self.spawn is not None:
            return self.spawn(argv)
        environment = os.environ.copy()
        environment["MJA_DEBUG_DIR"] = str(self.install_root / "debug" / "runs")
        environment["MJA_CONTROLLER"] = "android"
        environment["MJA_ANDROID_AVD"] = self.config.avd_name
        resolved_package = package_name or self.config.package_name
        if not resolved_package:
            raise MJAError(
                ErrorCode.ANDROID_GAME_NOT_FOUND,
                "package_name is required before launching Maa",
            )
        environment["MJA_ANDROID_PACKAGE"] = resolved_package
        if adb_path is not None:
            environment["MJA_ANDROID_ADB"] = str(adb_path)
            environment["MJA_ANDROID_SDK_ROOT"] = str(Path(adb_path).parent.parent)
        if serial is not None:
            environment["MJA_ANDROID_SERIAL"] = serial
        return subprocess.Popen(
            list(argv),
            cwd=self.install_root,
            env=environment,
            start_new_session=True,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run MJA against the Android emulator")
    parser.add_argument("--task", default="mail_smoke_test")
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--wipe-data", action="store_true")
    args = parser.parse_args(argv)
    try:
        return AndroidRun().run(args.task, stop=args.stop, wipe_data=args.wipe_data)
    except Exception as exc:
        code = getattr(getattr(exc, "code", None), "value", "ANDROID_RUN_FAILED")
        print(f"ERROR: {code}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
