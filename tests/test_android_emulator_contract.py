from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from agent.android.config import AndroidConfig
from agent.errors import ErrorCode, MJAError
from tools.android_emulator_contract import verify_emulator_contract


def _config(tmp_path: Path) -> AndroidConfig:
    avd_home = tmp_path / "avd"
    avd_root = avd_home / "mja-api35-apis.avd"
    avd_root.mkdir(parents=True)
    (avd_root / "config.ini").write_text(
        "hw.gpu.enabled=yes\nhw.gpu.mode=host\nhw.lcd.width=1280\nhw.lcd.height=720\n",
        encoding="utf-8",
    )
    return AndroidConfig(sdk_root=tmp_path / "sdk", avd_home=avd_home)


def _ps_runner(command: str):
    def runner(argv, **_kwargs):
        assert argv == ["ps", "-axo", "pid=,command="]
        return SimpleNamespace(
            stdout=(
                "82914 /sdk/emulator/qemu/darwin-aarch64/qemu-system-aarch64 "
                "-avd mja-api35-apis -gpu host -port 5556 "
                "-feature -VulkanQueueSubmitWithCommands\n"
                if command == "safe"
                else command + "\n"
            )
        )

    return runner


def test_verify_emulator_contract_requires_host_gpu_and_safe_queue_override(
    tmp_path: Path,
) -> None:
    result = verify_emulator_contract(_config(tmp_path), process_runner=_ps_runner("safe"))

    assert result["emulator_pid"] == "82914"
    assert result["qemu_gpu_backend"] == "host"
    assert result["vulkan_queue_submit_with_commands"] == "disabled"
    assert result["avd_gpu_enabled"] == "yes"
    assert result["avd_gpu_mode"] == "host"


@pytest.mark.parametrize(
    "command",
    [
        "/sdk/qemu-system-aarch64 -avd mja-api35-apis -gpu software -port 5556 "
        "-feature -VulkanQueueSubmitWithCommands",
        "/sdk/qemu-system-aarch64 -avd mja-api35-apis -gpu host -port 5556",
    ],
)
def test_verify_emulator_contract_rejects_unsafe_qemu_command(
    tmp_path: Path,
    command: str,
) -> None:
    with pytest.raises(MJAError) as exc_info:
        verify_emulator_contract(_config(tmp_path), process_runner=_ps_runner(command))

    assert exc_info.value.code is ErrorCode.ANDROID_EMULATOR_CONTRACT_FAILED


@pytest.mark.parametrize("gpu,valid", [("host", True), ("software", False)])
def test_slow_process_probe_still_checks_actual_gpu(tmp_path, gpu, valid):
    import subprocess

    command = (
        "82914 /sdk/qemu-system-aarch64 -avd mja-api35-apis "
        f"-gpu {gpu} -port 5556 -feature -VulkanQueueSubmitWithCommands"
    )

    def slow_runner(argv, **kwargs):
        if kwargs["timeout"] < 5:
            raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
        return _ps_runner(command)(argv, **kwargs)

    config = _config(tmp_path)
    if valid:
        assert (
            verify_emulator_contract(config, process_runner=slow_runner)["qemu_gpu_backend"]
            == "host"
        )
    else:
        with pytest.raises(MJAError):
            verify_emulator_contract(config, process_runner=slow_runner)


def test_process_probe_timeout_never_bypasses_contract(tmp_path):
    import subprocess

    def timed_out(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, kwargs["timeout"])

    with pytest.raises(MJAError) as exc_info:
        verify_emulator_contract(_config(tmp_path), process_runner=timed_out)
    assert exc_info.value.code is ErrorCode.ANDROID_EMULATOR_CONTRACT_FAILED
