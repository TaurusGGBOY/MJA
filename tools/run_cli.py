from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Protocol

GAME_APP_NAME = "对决！剑之川"
PREPARE_TIMEOUT_SECONDS = 60
CLI_COMMAND = ["./MaaPiCli", "-d"]


class Lifecycle(Protocol):
    def prepare(self, timeout_seconds: int) -> Any: ...

    def restore(self) -> None: ...


class ChildProcess(Protocol):
    def wait(self) -> int: ...

    def send_signal(self, signal_number: signal.Signals) -> None: ...


def _launch_game() -> None:
    subprocess.run(["/usr/bin/open", "-a", GAME_APP_NAME], check=True)


def _write_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _window_id(prepared: Any) -> int:
    value = getattr(prepared, "window_id", prepared)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"lifecycle.prepare() returned invalid window ID: {value!r}")
    return value


def _maa_config(window_id: int) -> dict[str, Any]:
    return {
        "controller": {"name": "macos"},
        "macos": {
            "window_id": window_id,
            "title": GAME_APP_NAME,
            "screencap": "ScreenCaptureKit",
            "input": "GlobalEvent",
        },
        "resource": "mja",
        "task": [{"name": "mail_smoke_test"}],
    }


def _default_spawn(
    argv: Sequence[str], *, install_root: Path, environment: dict[str, str]
) -> ChildProcess:
    return subprocess.Popen(list(argv), cwd=install_root, env=environment)


def run_cli(
    lifecycle: Lifecycle,
    *,
    install_root: str | Path = Path("install"),
    launch: Callable[[], None] | None = None,
    spawn: Callable[[Sequence[str]], ChildProcess] | None = None,
) -> int:
    """Run MaaPiCli with the same assembled project and guaranteed restore."""
    root = Path(install_root)
    config_path = root / "config" / "maa_pi_config.json"
    environment = os.environ.copy()
    environment["MJA_DEBUG_DIR"] = str(root / "debug" / "runs")
    child: ChildProcess | None = None
    previous_sigint = signal.getsignal(signal.SIGINT)

    def forward_sigint(signum: int, _frame: Any) -> None:
        if child is not None:
            child.send_signal(signum)

    try:
        signal.signal(signal.SIGINT, forward_sigint)
        (launch or _launch_game)()
        prepared = lifecycle.prepare(timeout_seconds=PREPARE_TIMEOUT_SECONDS)
        _write_atomic(config_path, _maa_config(_window_id(prepared)))
        if spawn is None:
            child = _default_spawn(CLI_COMMAND, install_root=root, environment=environment)
        else:
            child = spawn(CLI_COMMAND)
        return child.wait()
    finally:
        signal.signal(signal.SIGINT, previous_sigint)
        active_exception = sys.exc_info()[0]
        try:
            lifecycle.restore()
        except Exception:
            if active_exception is None:
                raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the MJA MaaPiCli smoke test")
    parser.add_argument("--install-root", type=Path, default=Path("install"))
    args = parser.parse_args(argv)
    from agent.macos.window_lifecycle import build_lifecycle

    try:
        return run_cli(build_lifecycle(), install_root=args.install_root)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover - CLI exercised on the target Mac
    raise SystemExit(main())


__all__ = ["CLI_COMMAND", "main", "run_cli"]

