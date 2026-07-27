from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Sequence

from agent.actions import macos_foreground_click as _macos_foreground_click  # noqa: F401
from agent.diagnostics import RunDiagnostics
from agent.errors import ErrorCode, MJAError
from agent.macos.window_lifecycle import WindowLifecycle, build_lifecycle
from agent.sinks.restore_window import RestoreWindowSink

try:
    from maa.agent.agent_server import AgentServer
except ImportError:  # pragma: no cover - allows unit tests without MaaFw installed.
    AgentServer = None  # type: ignore[assignment]


def _write_failure_diagnostics(error: MJAError) -> None:
    try:
        root = Path(os.environ.get("MJA_DEBUG_DIR", "debug/runs"))
        run = RunDiagnostics.create(root)
        try:
            run.fail(error)
        finally:
            run.close()
    except Exception:
        print(f"diagnostics unavailable: {error.code}: {error}", file=sys.stderr)


def _configure_maa_log_dir() -> None:
    debug_dir = os.environ.get("MJA_DEBUG_DIR")
    if not debug_dir:
        return
    path = Path(debug_dir)
    path.mkdir(parents=True, exist_ok=True)
    try:
        from maa.tasker import Tasker
    except ImportError:  # pragma: no cover - only bare unit-test environments.
        return
    if not Tasker.set_log_dir(path):
        raise RuntimeError(f"could not set Maa log directory: {path}")


def _controller_error(exc: BaseException) -> MJAError:
    if isinstance(exc, MJAError):
        return exc
    return MJAError(ErrorCode.CONTROLLER_CONNECT_FAILED, f"AgentServer failed: {exc}")


def _register_tasker_sink(lifecycle: WindowLifecycle) -> None:
    if AgentServer is None or not hasattr(AgentServer, "tasker_sink"):
        return

    @AgentServer.tasker_sink()
    class _MjaRestoreWindowSink(RestoreWindowSink):
        def __init__(self) -> None:
            super().__init__(restore=lifecycle.restore)


    del _MjaRestoreWindowSink


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("Usage: python -m agent.main <socket_id>", file=sys.stderr)
        return 2

    lifecycle: WindowLifecycle = build_lifecycle()
    result = 0
    try:
        if AgentServer is None:
            raise MJAError(ErrorCode.CONTROLLER_CONNECT_FAILED, "Maa AgentServer is unavailable")
        _register_tasker_sink(lifecycle)
        _configure_maa_log_dir()
        if not AgentServer.start_up(args[0]):
            raise MJAError(
                ErrorCode.CONTROLLER_CONNECT_FAILED,
                "AgentServer.start_up returned false",
            )
        try:
            AgentServer.join()
        except KeyboardInterrupt:
            result = 130
    except KeyboardInterrupt:
        result = 130
    except Exception as exc:
        error = _controller_error(exc)
        _write_failure_diagnostics(error)
        print(f"{error.code}: {error}", file=sys.stderr)
        result = 3
    finally:
        if AgentServer is not None:
            try:
                AgentServer.shut_down()
            except Exception as exc:
                print(f"AgentServer shutdown failed: {exc}", file=sys.stderr)
        try:
            lifecycle.restore()
        except Exception as exc:
            print(f"window restore failed: {exc}", file=sys.stderr)
    return result


if __name__ == "__main__":  # pragma: no cover - exercised by the CLI.
    raise SystemExit(main())


__all__ = ["main"]
