from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

from agent.android.config import DEFAULT_SYSTEM_IMAGE_PACKAGE, AndroidConfig
from agent.errors import ErrorCode, MJAError

BASE_REQUIRED_PACKAGES = (
    "platform-tools",
    "emulator",
    "platforms;android-35",
)
REQUIRED_PACKAGES = (*BASE_REQUIRED_PACKAGES, DEFAULT_SYSTEM_IMAGE_PACKAGE)


def required_packages(config: AndroidConfig) -> tuple[str, ...]:
    """Return SDK components for the configured non-Play system image."""
    return (*BASE_REQUIRED_PACKAGES, config.system_image_package)


@dataclass(frozen=True)
class SdkPaths:
    root: Path
    sdkmanager: Path
    avdmanager: Path
    adb: Path
    emulator: Path


Runner = Callable[..., Any]


class AndroidSdk:
    def __init__(self, config: AndroidConfig, *, runner: Runner = subprocess.run) -> None:
        self.config = config
        self.runner = runner

    @property
    def required_packages(self) -> tuple[str, ...]:
        return required_packages(self.config)

    def discover(self) -> SdkPaths | None:
        root = self.config.sdk_root
        sdkmanager = self._first_file(
            root / "cmdline-tools" / "latest" / "bin" / "sdkmanager",
            root / "cmdline-tools" / "bin" / "sdkmanager",
            Path("/opt/homebrew/bin/sdkmanager"),
            Path("/opt/homebrew/share/android-commandlinetools/cmdline-tools/latest/bin/sdkmanager"),
            shutil.which("sdkmanager"),
        )
        avdmanager = self._first_file(
            root / "cmdline-tools" / "latest" / "bin" / "avdmanager",
            root / "cmdline-tools" / "bin" / "avdmanager",
            Path("/opt/homebrew/bin/avdmanager"),
            Path("/opt/homebrew/share/android-commandlinetools/cmdline-tools/latest/bin/avdmanager"),
            shutil.which("avdmanager"),
        )
        adb = self._first_file(root / "platform-tools" / "adb", shutil.which("adb"))
        emulator = self._first_file(root / "emulator" / "emulator", shutil.which("emulator"))
        if not all((sdkmanager, avdmanager, adb, emulator)):
            return None
        return SdkPaths(root, sdkmanager, avdmanager, adb, emulator)

    def ensure(self, *, install_missing: bool = False) -> SdkPaths:
        paths = self.discover()
        if paths is None and install_missing:
            if self._find_sdkmanager() is None:
                self._install_homebrew_tools()
            self._install_components_from_toolchain()
            paths = self.discover()
        if paths is None:
            raise MJAError(
                ErrorCode.ANDROID_SDK_UNAVAILABLE,
                "Android SDK command-line tools, adb, or emulator are unavailable; "
                "run tools/android_setup.py --install",
            )
        if install_missing and not self._manifest_is_current():
            self._install_components(paths)
        return paths

    def _install_homebrew_tools(self) -> None:
        self._run(["brew", "install", "--cask", "android-commandlinetools"])
        self._run(["brew", "install", "openjdk@17"])

    def _install_components(self, paths: SdkPaths) -> None:
        self._install_components_with_manager(paths.sdkmanager)

    def _install_components_from_toolchain(self) -> None:
        sdkmanager = self._find_sdkmanager()
        if sdkmanager is None:
            raise MJAError(
                ErrorCode.ANDROID_SDK_UNAVAILABLE,
                "Homebrew installed no usable sdkmanager",
            )
        self._install_components_with_manager(sdkmanager)

    def _install_components_with_manager(self, sdkmanager: Path) -> None:
        self._run(
            [str(sdkmanager), f"--sdk_root={self.config.sdk_root}", *self.required_packages],
            input="y\n" * 8,
        )
        self._run(
            [str(sdkmanager), f"--sdk_root={self.config.sdk_root}", "--licenses"],
            input="y\n" * 32,
        )
        self.config.sdk_root.mkdir(parents=True, exist_ok=True)
        (self.config.sdk_root / ".mja-sdk-manifest.json").write_text(
            json.dumps(
                {"schema_version": 1, "packages": list(self.required_packages)},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def _find_sdkmanager(self) -> Path | None:
        return self._first_file(
            self.config.sdk_root / "cmdline-tools" / "latest" / "bin" / "sdkmanager",
            self.config.sdk_root / "cmdline-tools" / "bin" / "sdkmanager",
            Path("/opt/homebrew/bin/sdkmanager"),
            Path("/opt/homebrew/share/android-commandlinetools/cmdline-tools/latest/bin/sdkmanager"),
            shutil.which("sdkmanager"),
        )

    def _manifest_is_current(self) -> bool:
        manifest_path = self.config.sdk_root / ".mja-sdk-manifest.json"
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, TypeError, json.JSONDecodeError):
            return False
        return (
            payload.get("schema_version") == 1
            and payload.get("packages") == list(self.required_packages)
        )

    def _run(self, argv: Sequence[str], **kwargs: Any) -> Any:
        environment = os.environ.copy()
        java_home = Path("/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home")
        if java_home.is_dir():
            environment["JAVA_HOME"] = str(java_home)
            environment["PATH"] = f"{java_home / 'bin'}{os.pathsep}{environment.get('PATH', '')}"
        try:
            return self.runner(
                list(argv),
                check=True,
                capture_output=True,
                text=True,
                timeout=kwargs.pop("timeout", 600),
                env=environment,
                **kwargs,
            )
        except (OSError, subprocess.TimeoutExpired, subprocess.CalledProcessError) as exc:
            raise MJAError(ErrorCode.ANDROID_SDK_UNAVAILABLE, str(exc)) from exc

    @staticmethod
    def _first_file(*candidates: Path | str | None) -> Path | None:
        for candidate in candidates:
            if candidate is None:
                continue
            path = Path(os.fspath(candidate))
            if path.is_file() and os.access(path, os.X_OK):
                return path
        return None


__all__ = [
    "AndroidSdk",
    "BASE_REQUIRED_PACKAGES",
    "REQUIRED_PACKAGES",
    "SdkPaths",
    "required_packages",
]
