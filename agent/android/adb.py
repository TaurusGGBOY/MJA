from __future__ import annotations

import re
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from math import sqrt
from pathlib import Path
from typing import Any, Callable

from PIL import Image

from agent.android.config import AndroidConfig
from agent.android.sdk import SdkPaths
from agent.errors import ErrorCode, MJAError

UI_XML_MAX_ATTEMPTS = 3
UI_XML_RETRY_DELAY_SECONDS = 1.0
NETWORK_PROBE_ATTEMPTS = 3
NETWORK_PROBE_RETRY_DELAY_SECONDS = 1.0
PHANTOM_PROCESS_MONITOR_SETTING = "settings_enable_monitor_phantom_procs"
RENDERER_READY_SAMPLE_SIZE = (64, 36)
RENDERER_READY_LUMA_THRESHOLD = 24
RENDERER_READY_MIN_VISIBLE_RATIO = 0.05
_INTERACTIVE_READY_ROOT = (
    Path(__file__).resolve().parents[2] / "resource_android" / "image" / "home"
)
_INTERACTIVE_READY_TEMPLATES = (
    # A fresh isolated session must reach the title button before Maa starts.
    # A bright loading surface is not a usable game frame.
    ("title", _INTERACTIVE_READY_ROOT / "start_game_button.png", (560, 638, 180, 45), 0.55),
    # A non-fresh invocation may already be on the game home page.
    ("home", _INTERACTIVE_READY_ROOT / "home_marker.png", (1040, 0, 240, 110), 0.45),
)


@dataclass(frozen=True)
class DeviceInfo:
    serial: str
    width: int
    height: int
    sdk: str


@dataclass(frozen=True)
class MemoryInfo:
    """Guest memory values reported by Android's ``/proc/meminfo``."""

    total_bytes: int
    available_bytes: int
    swap_total_bytes: int
    swap_free_bytes: int


def _normalized_template_similarity(candidate: Image.Image, template: Image.Image) -> float:
    """Return a small dependency-free normalized grayscale correlation."""

    candidate_gray = candidate.convert("L")
    template_gray = template.convert("L")
    if candidate_gray.size != template_gray.size:
        candidate_gray = candidate_gray.resize(template_gray.size)
    candidate_values = [float(value) for value in candidate_gray.getdata()]
    template_values = [float(value) for value in template_gray.getdata()]
    if not candidate_values or len(candidate_values) != len(template_values):
        return 0.0
    candidate_mean = sum(candidate_values) / len(candidate_values)
    template_mean = sum(template_values) / len(template_values)
    centered_candidate = [value - candidate_mean for value in candidate_values]
    centered_template = [value - template_mean for value in template_values]
    numerator = sum(left * right for left, right in zip(centered_candidate, centered_template))
    denominator = sqrt(
        sum(value * value for value in centered_candidate)
        * sum(value * value for value in centered_template)
    )
    return numerator / denominator if denominator else 0.0


class AdbDevice:
    def __init__(
        self,
        config: AndroidConfig,
        sdk: SdkPaths,
        *,
        runner: Callable[..., Any] = subprocess.run,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = config
        self.sdk = sdk
        self.runner = runner
        self.sleeper = sleeper

    def wait_ready(self, timeout_seconds: int = 120) -> DeviceInfo:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            devices = self._devices()
            try:
                booted = self.shell("getprop", "sys.boot_completed").strip() == "1"
            except MJAError:
                self.sleeper(1.0)
                continue
            if devices == [self.config.serial] and booted:
                width, height = self._size()
                if (width, height) != self.config.display_size:
                    raise MJAError(
                        ErrorCode.DISPLAY_CONTRACT_MISMATCH,
                        f"Android device must be 1280x720, got {width}x{height}",
                    )
                return DeviceInfo(
                    serial=self.config.serial,
                    width=width,
                    height=height,
                    sdk=self.shell("getprop", "ro.build.version.sdk").strip(),
                )
            self.sleeper(1.0)
        raise MJAError(
            ErrorCode.ADB_DEVICE_FAILED,
            f"ADB device {self.config.serial} did not become the only ready device",
        )

    def shell(self, *args: str) -> str:
        result = self._run([str(self.sdk.adb), "-s", self.config.serial, "shell", *args])
        return str(getattr(result, "stdout", ""))

    def ensure_selinux_mode(self, mode: str | None = None) -> str:
        """Apply and verify the SELinux mode required by the game runtime.

        The Android 15 game build loads executable hot-patch libraries from
        app data.  On this isolated userdebug AVD that requires permissive
        SELinux; enforcing mode kills the process during ``DongDong`` init.
        Keep the change explicit and verified so MAA never starts against an
        emulator that cannot launch the game.
        """

        target = str(mode or getattr(self.config, "selinux_mode", "permissive")).lower()
        if target not in {"enforcing", "permissive"}:
            raise ValueError("selinux mode must be enforcing or permissive")

        current = self.shell("getenforce").strip().lower()
        if current == target:
            return current

        root_result = self._run(
            [str(self.sdk.adb), "-s", self.config.serial, "root"],
            check=False,
        )
        if getattr(root_result, "returncode", 1) != 0:
            detail = str(
                getattr(root_result, "stderr", "")
                or getattr(root_result, "stdout", "")
                or "adb root failed"
            ).strip()
            raise MJAError(
                ErrorCode.ANDROID_SELINUX_INCOMPATIBLE,
                f"cannot obtain emulator root to set SELinux {target}: {detail}",
            )

        last_error: MJAError | None = None
        for _ in range(10):
            try:
                self.shell("id", "-u")
                break
            except MJAError as exc:
                last_error = exc
                self.sleeper(0.5)
        else:
            raise MJAError(
                ErrorCode.ANDROID_SELINUX_INCOMPATIBLE,
                "ADB did not reconnect after restarting adbd as root",
            ) from last_error

        set_result = self._run(
            [
                str(self.sdk.adb),
                "-s",
                self.config.serial,
                "shell",
                "setenforce",
                "0" if target == "permissive" else "1",
            ],
            check=False,
        )
        if getattr(set_result, "returncode", 1) != 0:
            detail = str(
                getattr(set_result, "stderr", "")
                or getattr(set_result, "stdout", "")
                or "setenforce failed"
            ).strip()
            raise MJAError(
                ErrorCode.ANDROID_SELINUX_INCOMPATIBLE,
                f"cannot set emulator SELinux to {target}: {detail}",
            )

        current = self.shell("getenforce").strip().lower()
        if current != target:
            raise MJAError(
                ErrorCode.ANDROID_SELINUX_INCOMPATIBLE,
                f"emulator SELinux mode is {current or 'unknown'}, expected {target}",
            )
        return current

    def ensure_phantom_process_monitor_disabled(self) -> str:
        """Disable Android's phantom child-process monitor for the game AVD.

        The game forks a native helper process. Android's phantom-process
        policy can kill that helper together with the foreground parent,
        returning MFW to Launcher without a Java crash or ANR. This is the
        same persistent global feature flag exposed by Android Developer
        Options, and it is scoped to the current emulator userdata.
        """

        setting = PHANTOM_PROCESS_MONITOR_SETTING
        current = self.shell("settings", "get", "global", setting).strip().lower()
        if current != "false":
            self.shell("settings", "put", "global", setting, "false")
            current = self.shell("settings", "get", "global", setting).strip().lower()
        if current != "false":
            raise MJAError(
                ErrorCode.ANDROID_SHARED_RUNTIME_FAILURE,
                f"Android phantom-process monitor remains {current or 'unknown'}",
            )
        return current

    def storage_free_bytes(self) -> int:
        """Return free bytes reported by Android's userdata filesystem."""
        output = self.shell("df", "-Pk", "/data/user/0")
        for line in reversed(output.splitlines()):
            fields = line.split()
            if len(fields) < 4:
                continue
            try:
                available_kib = int(fields[3])
            except ValueError:
                continue
            return available_kib * 1024
        raise MJAError(
            ErrorCode.ADB_DEVICE_FAILED,
            "unable to parse free userdata space from adb df output",
        )

    def memory_info(self) -> MemoryInfo:
        """Read the guest memory budget without sending game input."""

        output = self.shell("cat", "/proc/meminfo")
        values: dict[str, int] = {}
        for line in output.splitlines():
            fields = line.split()
            if len(fields) < 2 or not fields[0].endswith(":"):
                continue
            try:
                value = int(fields[1])
            except ValueError:
                continue
            unit = fields[2].lower() if len(fields) >= 3 else ""
            multiplier = 1024 if unit == "kb" else 1
            values[fields[0][:-1]] = value * multiplier

        required = ("MemTotal", "MemAvailable", "SwapTotal", "SwapFree")
        if any(key not in values for key in required):
            raise MJAError(
                ErrorCode.ADB_DEVICE_FAILED,
                "unable to parse Android guest memory information",
            )
        return MemoryInfo(
            total_bytes=values["MemTotal"],
            available_bytes=values["MemAvailable"],
            swap_total_bytes=values["SwapTotal"],
            swap_free_bytes=values["SwapFree"],
        )

    def require_memory_health(
        self,
        *,
        min_available_bytes: int = 256 * 1024 * 1024,
        min_swap_free_bytes: int = 128 * 1024 * 1024,
    ) -> MemoryInfo:
        """Fail before Maa starts when the Android guest is near OOM."""

        if min_available_bytes < 0 or min_swap_free_bytes < 0:
            raise ValueError("memory health thresholds must not be negative")
        info = self.memory_info()
        if info.available_bytes < min_available_bytes or (
            info.swap_total_bytes > 0 and info.swap_free_bytes < min_swap_free_bytes
        ):
            raise MJAError(
                ErrorCode.ANDROID_MEMORY_LOW,
                "Android guest memory is too low: "
                f"available={info.available_bytes} bytes, "
                f"swap_free={info.swap_free_bytes} bytes",
            )
        return info

    def game_process_id(self, package_name: str | None = None) -> int | None:
        """Return the configured game's PID, or ``None`` when it is gone."""

        package = package_name or self.config.package_name
        if not package:
            raise MJAError(
                ErrorCode.ANDROID_GAME_NOT_FOUND,
                "package_name is required to inspect the Android game process",
            )
        try:
            output = self.shell("pidof", package)
        except MJAError:
            return None
        for token in output.split():
            try:
                return int(token)
            except ValueError:
                continue
        return None

    def require_game_process(self, package_name: str | None = None) -> int:
        """Fail with a typed diagnostic when Android killed the game process."""

        pid = self.game_process_id(package_name)
        if pid is None:
            raise MJAError(
                ErrorCode.ANDROID_GAME_PROCESS_DIED,
                f"Android game process is not running: {package_name or self.config.package_name}",
            )
        return pid

    def require_runtime_health(self, min_free_bytes: int = 1_073_741_824) -> None:
        """Fail closed when the emulator cannot safely run an Android task."""
        if min_free_bytes < 0:
            raise ValueError("min_free_bytes must not be negative")

        free_bytes = self.storage_free_bytes()
        if free_bytes < min_free_bytes:
            raise MJAError(
                ErrorCode.ANDROID_STORAGE_LOW,
                f"Android userdata has only {free_bytes} free bytes; "
                f"minimum is {min_free_bytes}",
            )

        network_error: MJAError | None = None
        for attempt in range(NETWORK_PROBE_ATTEMPTS):
            try:
                self.shell("ping", "-c", "1", "-W", "5", "223.5.5.5")
                network_error = None
                break
            except MJAError as exc:
                network_error = exc
                if attempt + 1 < NETWORK_PROBE_ATTEMPTS:
                    self.sleeper(NETWORK_PROBE_RETRY_DELAY_SECONDS)
        if network_error is not None:
            raise MJAError(
                ErrorCode.ANDROID_NETWORK_UNAVAILABLE,
                "Android emulator network probe failed after bounded retries",
            ) from network_error

        package_name = self.config.package_name
        if not package_name:
            raise MJAError(
                ErrorCode.ANDROID_GAME_NOT_FOUND,
                "package_name is required for Android runtime health checks",
            )
        foreground = self.foreground_package()
        if foreground != package_name:
            raise MJAError(
                ErrorCode.ANDROID_GAME_NOT_FOREGROUND,
                f"expected {package_name} in the foreground, got {foreground or 'none'}",
            )

        with tempfile.TemporaryDirectory(prefix="mja-android-health-") as directory:
            self.screencap(Path(directory) / "health.png")

    def screencap(self, destination: Path) -> tuple[int, int]:
        result = self._run(
            [str(self.sdk.adb), "-s", self.config.serial, "exec-out", "screencap", "-p"],
            binary=True,
        )
        data = getattr(result, "stdout", b"")
        if not isinstance(data, bytes) or not data:
            raise MJAError(ErrorCode.ADB_DEVICE_FAILED, "adb screencap returned no PNG data")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        try:
            with Image.open(destination) as image:
                size = image.size
        except (OSError, ValueError) as exc:
            raise MJAError(ErrorCode.ADB_DEVICE_FAILED, f"invalid adb screenshot: {exc}") from exc
        if size != self.config.display_size:
            raise MJAError(
                ErrorCode.DISPLAY_CONTRACT_MISMATCH,
                f"Android screenshot must be 1280x720, got {size[0]}x{size[1]}",
            )
        return size

    def renderer_ready(
        self,
        *,
        min_visible_ratio: float = RENDERER_READY_MIN_VISIBLE_RATIO,
    ) -> bool:
        """Return whether the foreground game has rendered a real frame.

        Unity can own the foreground package for tens of seconds while the
        surface is still black.  Package-only readiness lets Maa send valid
        input into that loading gap and produces misleading workflow failures.
        Keep this as a read-only ADB screencap probe; it never sends input.
        """

        if not 0.0 <= min_visible_ratio <= 1.0:
            raise ValueError("min_visible_ratio must be between 0 and 1")
        with tempfile.TemporaryDirectory(prefix="mja-android-renderer-") as directory:
            path = Path(directory) / "frame.png"
            self.screencap(path)
            with Image.open(path) as image:
                sample = image.convert("RGB").resize(RENDERER_READY_SAMPLE_SIZE)
                visible = sum(
                    1
                    for red, green, blue in sample.getdata()
                    if max(red, green, blue) >= RENDERER_READY_LUMA_THRESHOLD
                )
        total = RENDERER_READY_SAMPLE_SIZE[0] * RENDERER_READY_SAMPLE_SIZE[1]
        return visible / total >= min_visible_ratio

    def interactive_ready(self) -> bool:
        """Return whether the game is on a usable title/home surface.

        The Unity loading screens are colorful and therefore pass the older
        luma-only ``renderer_ready`` check.  Maa's first native screenshot can
        then block for 30 seconds while the renderer is still initializing.
        Use the same small, project-owned templates as the Android pipeline to
        distinguish the title/home surface from those loading frames.  A
        transient ADB screenshot timeout is treated as "not ready" so the
        login gate can keep polling within its bounded startup deadline.
        """

        with tempfile.TemporaryDirectory(prefix="mja-android-interactive-") as directory:
            path = Path(directory) / "frame.png"
            try:
                self.screencap(path)
            except MJAError as exc:
                if exc.code is ErrorCode.ADB_DEVICE_FAILED:
                    return False
                raise
            available_template = False
            with Image.open(path) as image:
                for _name, template_path, roi, threshold in _INTERACTIVE_READY_TEMPLATES:
                    if not template_path.is_file():
                        continue
                    available_template = True
                    try:
                        with Image.open(template_path) as template:
                            candidate = image.crop(
                                (roi[0], roi[1], roi[0] + roi[2], roi[1] + roi[3])
                            )
                            if _normalized_template_similarity(candidate, template) >= threshold:
                                return True
                    except (OSError, ValueError):
                        continue
        if available_template:
            # The title/home artwork is updated independently of the game
            # binary.  A stale bundled template must not turn a rendered title
            # page into a 15-minute startup wait; Maa owns the authoritative
            # OCR/page decision once it attaches.  Keep this fallback read-only
            # and conservative: a black/blank renderer still returns False.
            return self.renderer_ready()
        # Keep installations that do not carry the optional project templates
        # usable; the luma probe remains a conservative compatibility fallback.
        return self.renderer_ready()

    def tap(self, x: int, y: int) -> None:
        if not (0 <= x < self.config.display_size[0] and 0 <= y < self.config.display_size[1]):
            raise ValueError("tap coordinates are outside 1280x720")
        self._run(
            [str(self.sdk.adb), "-s", self.config.serial, "shell", "input", "tap", str(x), str(y)]
        )

    def launch(self, package_name: str) -> None:
        self._start_activity(self._resolve_activity(package_name))

    def start_app(self, package_name: str) -> None:
        """Start or foreground an app using MaaFramework's Adb StartApp command."""
        self._run(
            [
                str(self.sdk.adb),
                "-s",
                self.config.serial,
                "shell",
                "monkey",
                "-p",
                package_name,
                "--pct-syskeys",
                "0",
                "1",
            ]
        )

    def restart(self, package_name: str) -> None:
        """Start a clean game process without clearing its app data.

        ``am start`` may reuse a wedged existing process.  Stopping only the
        package first keeps the account/login state intact while restoring a
        responsive renderer for the MAA tasker.
        """
        activity = self._resolve_activity(package_name)
        self._run(
            [
                str(self.sdk.adb),
                "-s",
                self.config.serial,
                "shell",
                "am",
                "force-stop",
                package_name,
            ]
        )
        self._start_activity(activity)

    def _resolve_activity(self, package_name: str) -> str:
        resolved = self.shell("cmd", "package", "resolve-activity", "--brief", package_name)
        activity = next(
            (line.strip() for line in reversed(resolved.splitlines()) if "/" in line),
            None,
        )
        if not activity:
            raise MJAError(
                ErrorCode.ANDROID_GAME_NOT_FOUND,
                f"unable to resolve launch activity for {package_name}",
            )
        return activity

    def _start_activity(self, activity: str) -> None:
        self._run(
            [
                str(self.sdk.adb),
                "-s",
                self.config.serial,
                "shell",
                "am",
                "start",
                "-W",
                "-n",
                activity,
            ]
        )

    def dismiss_first_run_overlay(self) -> None:
        """Dismiss Android's own first-run immersive-mode hint when present."""
        try:
            root = ET.fromstring(self.ui_xml())
        except ET.ParseError:
            return
        for node in root.iter("node"):
            if (node.attrib.get("text") or "").strip() not in {"Got it", "知道了"}:
                continue
            bounds = node.attrib.get("bounds", "")
            try:
                first, second = bounds.split("][", 1)
                left, top = (int(value) for value in first.strip("[]").split(","))
                right, bottom = (int(value) for value in second.strip("[]").split(","))
            except (ValueError, IndexError):
                return
            self.tap((left + right) // 2, (top + bottom) // 2)
            return

    def install(self, apk_path: Path) -> str:
        result = self._run(
            [str(self.sdk.adb), "-s", self.config.serial, "install", "-r", str(apk_path)]
        )
        return str(getattr(result, "stdout", ""))

    def package_installed(self, package_name: str) -> bool:
        try:
            return "package:" in self.shell("pm", "path", package_name)
        except MJAError:
            # `pm path` exits non-zero for a package that is not installed.
            return False

    def list_packages(self) -> set[str]:
        output = self.shell("pm", "list", "packages", "-3")
        return {
            line.removeprefix("package:").strip()
            for line in output.splitlines()
            if line.startswith("package:")
        }

    def foreground_package(self) -> str | None:
        text = self.shell("dumpsys", "window", "windows")
        for marker in ("mCurrentFocus=Window{", "mFocusedApp=AppWindowToken{"):
            index = text.find(marker)
            if index >= 0:
                fragment = text[index : index + 300]
                parts = fragment.split()
                for part in parts:
                    if "/" in part and "." in part.split("/", 1)[0]:
                        return part.split("/", 1)[0].split("}", 1)[0]
        # Android 15/35 may omit mCurrentFocus from dumpsys window output.
        # The activity manager still exposes the resumed activity reliably.
        activities = self.shell("dumpsys", "activity", "activities")
        match = re.search(
            r"(?:topResumedActivity|ResumedActivity):.*?\bu\d+\s+([A-Za-z0-9._$]+)/",
            activities,
        )
        return match.group(1) if match else None

    def ui_xml(self) -> str:
        last_error: MJAError | None = None
        for attempt in range(UI_XML_MAX_ATTEMPTS):
            try:
                self.shell("uiautomator", "dump", "/sdcard/window.xml")
                return self.shell("cat", "/sdcard/window.xml")
            except MJAError as exc:
                last_error = exc
                if attempt + 1 < UI_XML_MAX_ATTEMPTS:
                    # The Android UI service can be briefly busy immediately
                    # after the game is foregrounded.  A bounded retry keeps
                    # that transient race from aborting the whole daily run.
                    self.sleeper(UI_XML_RETRY_DELAY_SECONDS)
        assert last_error is not None
        raise last_error

    def _devices(self) -> list[str]:
        result = self._run([str(self.sdk.adb), "devices"])
        output = str(getattr(result, "stdout", ""))
        return [
            fields[0]
            for line in output.splitlines()
            if (fields := line.split()) and len(fields) >= 2 and fields[1] == "device"
        ]

    def _size(self) -> tuple[int, int]:
        output = self.shell("wm", "size")
        for line in output.splitlines():
            if "Physical size:" in line or "Override size:" in line:
                value = line.rsplit(":", 1)[-1].strip()
                width, height = value.split("x", 1)
                return int(width), int(height)
        raise MJAError(ErrorCode.ADB_DEVICE_FAILED, "unable to read Android display size")

    def _run(self, argv: list[str], *, binary: bool = False, check: bool = True) -> Any:
        # ADB can remain blocked indefinitely when the emulator's UI service
        # is wedged (most notably on `uiautomator dump`).  Every command must
        # have a finite bound so one task cannot stall the whole batch.
        timeout = 15 if argv[-3:] == ["uiautomator", "dump", "/sdcard/window.xml"] else 30
        try:
            return self.runner(
                argv,
                check=check,
                capture_output=True,
                text=not binary,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise MJAError(
                ErrorCode.ADB_DEVICE_FAILED,
                f"ADB command timed out after {timeout}s: {argv[2:]}",
            ) from exc
        except (OSError, subprocess.CalledProcessError) as exc:
            raise MJAError(ErrorCode.ADB_DEVICE_FAILED, f"ADB command failed: {argv[2:]}") from exc


__all__ = ["AdbDevice", "DeviceInfo", "MemoryInfo"]
