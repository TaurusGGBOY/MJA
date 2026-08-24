from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any, Callable

from agent.android.config import DEFAULT_SYSTEM_IMAGE_PACKAGE, AndroidConfig
from agent.android.sdk import SdkPaths
from agent.errors import ErrorCode, MJAError

AVD_PACKAGE = DEFAULT_SYSTEM_IMAGE_PACKAGE
AVD_DEVICE = "pixel_6"


class AndroidAvd:
    def __init__(
        self,
        config: AndroidConfig,
        sdk: SdkPaths,
        *,
        runner: Callable[..., Any] = subprocess.run,
        popen: Callable[..., Any] = subprocess.Popen,
    ) -> None:
        self.config = config
        self.sdk = sdk
        self.runner = runner
        self.popen = popen

    @property
    def avd_root(self) -> Path:
        base = self.config.avd_home or Path(
            os.environ.get("ANDROID_AVD_HOME", Path.home() / ".android" / "avd")
        )
        return base / f"{self.config.avd_name}.avd"

    @property
    def config_path(self) -> Path:
        return self.avd_root / "config.ini"

    def ensure(self) -> Path:
        if not self.config_path.is_file():
            self.avd_root.parent.mkdir(parents=True, exist_ok=True)
            self._run(
                [
                    str(self.sdk.avdmanager),
                    "create",
                    "avd",
                    "--name",
                    self.config.avd_name,
                    "--package",
                    self.config.system_image_package,
                    "--device",
                    AVD_DEVICE,
                    "--force",
                ],
                input="no\n",
            )
        if not self.config_path.is_file():
            raise MJAError(
                ErrorCode.ANDROID_AVD_FAILED,
                f"avdmanager did not create {self.config_path}",
            )
        self._enforce_display_contract()
        return self.config_path

    def start(self, *, wipe_data: bool = False) -> Any:
        self.ensure()
        state = self._run(
            [str(self.sdk.adb), "-s", self.config.serial, "get-state"],
            check=False,
        )
        if str(getattr(state, "stdout", "")).strip() == "device":
            return None
        command = [
            str(self.sdk.emulator),
            "-avd",
            self.config.avd_name,
            "-no-snapshot",
            "-no-boot-anim",
            "-noaudio",
            "-gpu",
            # The Android emulator must use the host GPU backend.
            "host",
            "-qt-hide-window",
            # This game build requires permissive SELinux on the isolated AVD.
            "-selinux",
            "permissive",
            "-crash-report-mode",
            "never",
            "-no-metrics",
            "-memory",
            str(self.config.avd_ram_size_mb),
        ]
        if wipe_data:
            command.append("-wipe-data")
        # Android Emulator 36.6.11 can crash in the host Vulkan/gfxstream
        # path while Unity repeatedly recreates its VkDevice.  Keep the
        # smallest verified feature mitigation enabled by default without
        # changing the required host GPU backend.  Setting this to 0 is
        # reserved for a controlled diagnosis and is rejected by the MFW
        # preflight contract.
        if os.environ.get("MJA_EMULATOR_DISABLE_VULKAN_QUEUE", "1") == "1":
            command.extend(["-feature", "-VulkanQueueSubmitWithCommands"])
        port = _emulator_port(self.config.serial)
        if port is not None:
            command.extend(["-port", str(port)])
        try:
            return self.popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
                text=True,
                env=self._environment(),
                start_new_session=True,
            )
        except OSError as exc:
            raise MJAError(ErrorCode.ANDROID_AVD_FAILED, str(exc)) from exc

    def stop(self) -> None:
        self._run([str(self.sdk.adb), "-s", self.config.serial, "emu", "kill"], check=False)

    def _enforce_display_contract(self) -> None:
        values = {
            "hw.lcd.width": "1280",
            "hw.lcd.height": "720",
            "hw.initialOrientation": "landscape",
            "hw.lcd.density": "320",
            "hw.gpu.enabled": "yes",
            # Keep the persisted AVD contract aligned with the launch flag.
            "hw.gpu.mode": "host",
            "hw.ramSize": f"{self.config.avd_ram_size_mb}M",
            "disk.dataPartition.size": f"{self.config.data_partition_size_gb}G",
        }
        lines = self.config_path.read_text(encoding="utf-8").splitlines()
        remaining = dict(values)
        output: list[str] = []
        for line in lines:
            key = line.split("=", 1)[0]
            if key in values:
                output.append(f"{key}={values[key]}")
                remaining.pop(key, None)
            else:
                output.append(line)
        output.extend(f"{key}={value}" for key, value in remaining.items())
        self.config_path.write_text("\n".join(output) + "\n", encoding="utf-8")

    def _run(self, argv: list[str], **kwargs: Any) -> Any:
        try:
            return self.runner(
                argv, capture_output=True, text=True, env=self._environment(), **kwargs
            )
        except OSError as exc:
            raise MJAError(ErrorCode.ANDROID_AVD_FAILED, str(exc)) from exc

    def _environment(self) -> dict[str, str]:
        environment = os.environ.copy()
        environment["ANDROID_SDK_ROOT"] = str(self.sdk.root)
        environment["ANDROID_HOME"] = str(self.sdk.root)
        if self.config.avd_home is not None:
            environment["ANDROID_AVD_HOME"] = str(self.config.avd_home)
            environment["ANDROID_USER_HOME"] = str(self.config.avd_home.parent)
        return environment


def _emulator_port(serial: str) -> int | None:
    match = re.fullmatch(r"emulator-(\d+)", serial)
    return int(match.group(1)) if match else None


__all__ = ["AVD_PACKAGE", "AndroidAvd"]
