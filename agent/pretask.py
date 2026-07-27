from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Sequence

from agent.errors import MJAError
from agent.macos.permissions import ensure_permissions
from agent.macos.window_lifecycle import build_lifecycle

PREPARE_TIMEOUT_SECONDS = 60


def _write_failure_diagnostics(error: MJAError) -> None:
    try:
        from agent.diagnostics import RunDiagnostics

        root = Path(os.environ.get("MJA_DEBUG_DIR", "debug/runs"))
        run = RunDiagnostics.create(root)
        try:
            run.fail(error)
        finally:
            run.close()
    except Exception:
        # A diagnostics failure must not hide the stable task error or change
        # its exit code. The concrete code/message is still printed below.
        return


def main(argv: Sequence[str] | None = None) -> int:
    del argv
    try:
        ensure_permissions()
        lifecycle = build_lifecycle()
        if lifecycle.has_pending_restore():
            lifecycle.restore()
        lifecycle.prepare(timeout_seconds=PREPARE_TIMEOUT_SECONDS)
        return 0
    except MJAError as exc:
        _write_failure_diagnostics(exc)
        print(f"{exc.code}: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"unexpected pretask failure: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":  # pragma: no cover - exercised by the CLI
    raise SystemExit(main(sys.argv[1:]))


__all__ = ["PREPARE_TIMEOUT_SECONDS", "main"]
