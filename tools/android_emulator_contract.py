"""Read-only checks for the Android emulator process contract.

The ADB device can remain reachable for a short time after QEMU has started
tearing down.  Direct MFW runs therefore need to validate both sides of the
boundary: the Android device and the host QEMU process that owns it.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path
from typing import Any, Callable

from agent.android.config import AndroidConfig
from agent.errors import ErrorCode, MJAError

SAFE_VULKAN_FEATURE = "VulkanQueueSubmitWithCommands"


def emulator_port(serial: str) -> int | None:
    """Return the TCP port encoded in an emulator serial, if present."""

    prefix, separator, suffix = str(serial).rpartition("-")
    if not separator or not suffix.isdigit() or prefix != "emulator":
        return None
    return int(suffix)


def avd_config_path(config: AndroidConfig) -> Path:
    base = config.avd_home or Path(
        os.environ.get("ANDROID_AVD_HOME", Path.home() / ".android" / "avd")
    )
    return base / f"{config.avd_name}.avd" / "config.ini"


def _avd_properties(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise MJAError(
            ErrorCode.ANDROID_EMULATOR_CONTRACT_FAILED,
            f"AVD config is unreadable: {path}",
        ) from exc
    values: dict[str, str] = {}
    for line in lines:
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _process_rows(
    runner: Callable[..., Any] = subprocess.run,
) -> list[tuple[int, str]]:
    try:
        result = runner(
            ["ps", "-axo", "pid=,command="],
            capture_output=True,
            text=True,
            timeout=3.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MJAError(
            ErrorCode.ANDROID_EMULATOR_CONTRACT_FAILED,
            f"cannot inspect host emulator processes: {exc}",
        ) from exc

    rows: list[tuple[int, str]] = []
    for line in str(getattr(result, "stdout", "")).splitlines():
        fields = line.strip().split(None, 1)
        if len(fields) != 2 or not fields[0].isdigit():
            continue
        rows.append((int(fields[0]), fields[1]))
    return rows


def _command_value(tokens: list[str], flag: str) -> str | None:
    try:
        index = tokens.index(flag)
    except ValueError:
        return None
    if index + 1 >= len(tokens):
        return None
    return tokens[index + 1]


def find_qemu_process(
    config: AndroidConfig,
    *,
    process_runner: Callable[..., Any] = subprocess.run,
) -> dict[str, Any]:
    """Find and validate the QEMU command serving ``config.serial``."""

    port = emulator_port(config.serial)
    if port is None:
        raise MJAError(
            ErrorCode.ANDROID_EMULATOR_CONTRACT_FAILED,
            f"Android serial is not a fixed emulator serial: {config.serial}",
        )

    candidates: list[tuple[int, str]] = []
    for pid, command in _process_rows(process_runner):
        if "qemu-system" not in command:
            continue
        try:
            tokens = shlex.split(command)
        except ValueError:
            continue
        if _command_value(tokens, "-avd") != config.avd_name:
            continue
        if _command_value(tokens, "-port") != str(port):
            continue
        candidates.append((pid, command))

    if len(candidates) != 1:
        state = "none" if not candidates else f"{len(candidates)} processes"
        raise MJAError(
            ErrorCode.ANDROID_EMULATOR_CONTRACT_FAILED,
            f"expected exactly one QEMU process for {config.avd_name}/{port}, found {state}",
        )

    pid, command = candidates[0]
    tokens = shlex.split(command)
    gpu = _command_value(tokens, "-gpu")
    if gpu != "host":
        raise MJAError(
            ErrorCode.ANDROID_EMULATOR_CONTRACT_FAILED,
            f"QEMU GPU backend must be host, got {gpu or '<missing>'}",
        )

    feature_disabled = any(
        tokens[index : index + 2] == ["-feature", f"-{SAFE_VULKAN_FEATURE}"]
        for index in range(len(tokens) - 1)
    )
    if not feature_disabled:
        raise MJAError(
            ErrorCode.ANDROID_EMULATOR_CONTRACT_FAILED,
            "QEMU is missing the required Vulkan queue safety feature override",
        )

    return {
        "emulator_pid": str(pid),
        "qemu_gpu_backend": gpu,
        "vulkan_queue_submit_with_commands": "disabled",
        "qemu_command": command,
    }


def verify_emulator_contract(
    config: AndroidConfig,
    *,
    process_runner: Callable[..., Any] = subprocess.run,
) -> dict[str, str]:
    """Validate persisted AVD settings and the live QEMU command line."""

    path = avd_config_path(config)
    if not path.is_file():
        raise MJAError(
            ErrorCode.ANDROID_EMULATOR_CONTRACT_FAILED,
            f"AVD config does not exist: {path}",
        )
    values = _avd_properties(path)
    expected = {
        "hw.gpu.enabled": "yes",
        "hw.gpu.mode": "host",
        "hw.lcd.width": "1280",
        "hw.lcd.height": "720",
    }
    mismatches = [
        f"{key}={values.get(key, '<missing>')} (expected {value})"
        for key, value in expected.items()
        if values.get(key) != value
    ]
    if mismatches:
        raise MJAError(
            ErrorCode.ANDROID_EMULATOR_CONTRACT_FAILED,
            "AVD contract mismatch: " + "; ".join(mismatches),
        )

    process = find_qemu_process(config, process_runner=process_runner)
    return {
        "emulator_pid": str(process["emulator_pid"]),
        "qemu_gpu_backend": str(process["qemu_gpu_backend"]),
        "vulkan_queue_submit_with_commands": str(
            process["vulkan_queue_submit_with_commands"]
        ),
        "qemu_command": str(process["qemu_command"]),
        "avd_gpu_enabled": values["hw.gpu.enabled"],
        "avd_gpu_mode": values["hw.gpu.mode"],
    }


__all__ = [
    "SAFE_VULKAN_FEATURE",
    "avd_config_path",
    "emulator_port",
    "find_qemu_process",
    "verify_emulator_contract",
]
