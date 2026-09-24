"""Exercise launcher handoff without starting an emulator or a game."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def executable(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(0o755)


@pytest.fixture
def launcher(tmp_path: Path):
    if not shutil.which("zsh"):
        pytest.skip("zsh is required for the macOS launcher")
    candidate = tmp_path / "candidate"
    executable(candidate / "MFW", "echo MFW_STARTED\n")
    executable(
        tmp_path / ".venv/bin/python",
        '[ -e "$TEST_FRAMEWORK_COMPLETED" ] || exit 9\necho PREFLIGHT_STARTED\n',
    )
    executable(tmp_path / "install/android-sdk/emulator/emulator", "exit 1\n")
    executable(tmp_path / "bin/pgrep", '[ "$TEST_EMULATOR_ALIVE" = 1 ] && echo 4242\n')
    executable(tmp_path / "bin/sleep", "exit 0\n")
    executable(
        tmp_path / "install/android-sdk/platform-tools/adb",
        r"""case "$*" in
  *get-state) echo "$TEST_ADB_STATE" ;;
  *getprop*)
    if [ "$TEST_READY" = 1 ]; then echo 1; else echo 0; fi ;;
  *get-current-user*)
    if [ ! -e "$TEST_FRAMEWORK_PROBED" ]; then
      touch "$TEST_FRAMEWORK_PROBED"
      exit 1
    fi
    touch "$TEST_FRAMEWORK_COMPLETED"
    echo 0 ;;
esac
""",
    )
    env = dict(
        os.environ,
        MJA_PROJECT_ROOT=str(tmp_path),
        MJA_CRASH_OBSERVE="0",
        MJA_MFW_CANDIDATE=str(candidate),
        MJA_EMULATOR_LOG=str(tmp_path / "emulator.log"),
        MJA_EMULATOR_BOOT_TIMEOUT_SECONDS="600",
        MJA_EMULATOR_VISIBLE="0",
        MJA_CLOSE_GAME_BEFORE_RUN="0",
        TEST_ADB_STATE="device",
        TEST_EMULATOR_ALIVE="1",
        TEST_READY="1",
        TEST_FRAMEWORK_PROBED=str(tmp_path / "framework-probed"),
        TEST_FRAMEWORK_COMPLETED=str(tmp_path / "framework-completed"),
        PATH=str(tmp_path / "bin") + os.pathsep + os.environ["PATH"],
    )

    def run(**overrides):
        return subprocess.run(
            ["zsh", str(ROOT / "tools/launch_mfw.zsh")],
            env=env | overrides,
            capture_output=True,
            text=True,
            timeout=60,
        )

    return run


def test_online_adb_waits_for_framework_before_handoff(launcher):
    result = launcher()
    assert result.returncode == 0, result.stderr
    assert result.stdout.count("PREFLIGHT_STARTED") == 1
    assert result.stdout.count("MFW_STARTED") == 1


def test_online_adb_without_boot_completion_cannot_launch_mfw(launcher):
    result = launcher(TEST_READY="0", MJA_EMULATOR_BOOT_TIMEOUT_SECONDS="1")
    assert result.returncode != 0
    assert "未就绪" in result.stderr
    assert "PREFLIGHT_STARTED" not in result.stdout
    assert "MFW_STARTED" not in result.stdout


def test_dead_emulator_stops_waiting_before_timeout(launcher):
    result = launcher(
        TEST_ADB_STATE="offline", TEST_EMULATOR_ALIVE="0", MJA_EMULATOR_BOOT_TIMEOUT_SECONDS="600"
    )
    assert result.returncode != 0
    assert "模拟器已退出" in result.stderr
    assert "MFW_STARTED" not in result.stdout


@pytest.mark.parametrize("value", ["0", "-1", "invalid"])
def test_invalid_boot_timeout_fails_explicitly(launcher, value):
    result = launcher(MJA_EMULATOR_BOOT_TIMEOUT_SECONDS=value)
    assert result.returncode != 0
    assert "必须是正整数" in result.stderr
    assert "MFW_STARTED" not in result.stdout


def test_starting_wrapper_is_not_mistaken_for_exited_qemu(launcher, tmp_path):
    ready = tmp_path / "device-ready"
    executable(
        tmp_path / "install/android-sdk/emulator/emulator", f'/bin/sleep 0.2\ntouch "{ready}"\n'
    )
    adb = tmp_path / "install/android-sdk/platform-tools/adb"
    adb.write_text(
        adb.read_text().replace(
            'echo "$TEST_ADB_STATE"',
            f'if [ -e "{ready}" ]; then echo device; else echo offline; fi',
        )
    )
    # After the wrapper exits, a real QEMU process remains discoverable.
    executable(tmp_path / "bin/pgrep", f'[ -e "{ready}" ] && echo 4242\n')
    (tmp_path / "framework-probed").touch()
    result = launcher(TEST_ADB_STATE="offline", TEST_EMULATOR_ALIVE="0")
    assert result.returncode == 0, result.stderr
    assert "MFW_STARTED" in result.stdout


def test_disappeared_emulator_terminates_only_launched_runner(launcher, tmp_path):
    started = tmp_path / "runner-started"
    stopped = tmp_path / "runner-stopped"
    executable(
        tmp_path / "candidate/MFW",
        f'trap \'touch "{stopped}"; exit 0\' TERM\n'
        f'touch "{started}"\nwhile :; do /bin/sleep 0.1; done\n',
    )
    executable(tmp_path / "bin/pgrep", f'[ ! -e "{started}" ] && echo 4242\n')
    result = launcher()
    assert result.returncode == 1
    assert "模拟器已退出，结束本轮 MFW" in result.stderr
    assert stopped.exists()


def test_enabled_observer_handoff_preserves_mfw_exit(launcher, tmp_path):
    helper = tmp_path / "tools/mfw_observe_runtime.py"
    helper.parent.mkdir()
    helper.symlink_to(ROOT / "tools/mfw_observe_runtime.py")
    executable(
        tmp_path / ".venv/bin/python",
        f'case "$1" in *mfw_observe_runtime.py) exec "{sys.executable}" "$@" ;; esac\n'
        '[ -e "$TEST_FRAMEWORK_COMPLETED" ] || exit 9\necho PREFLIGHT_STARTED\n',
    )
    result = launcher(MJA_CRASH_OBSERVE="1")
    assert result.returncode == 0, result.stderr
    runs = list((tmp_path / "candidate/debug/observability").glob("launch-*"))
    assert len(runs) == 1
    assert "MFW_STARTED" in (runs[0] / "mfw-console.log").read_text()
    assert '"shell_wait_status": 0' in (runs[0] / "events.jsonl").read_text()
