"""Socket-only entry point for the embedded MFW Agent."""

from __future__ import annotations

import sys
from pathlib import Path

# MaaPiCli launches this file by path (``agent/main.py``), so Python places
# ``agent`` itself on sys.path instead of the install root.  Put the package
# root first before importing the embedded agent modules.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from maa.agent.agent_server import AgentServer

# Import every narrow action, recognition, and sink module referenced by the
# shipped MFW resources.  The retired Python workflow/aggregate adapters are
# intentionally absent: independent Pipeline entries own their own state,
# terminal outcome, and native abort boundary.
from agent.custom.action.break_array_martial_daily import (  # noqa: F401
    BreakArrayMartialDailyAction as _break_array_martial_daily,
)
from agent.custom.action.convergence_lifecycle import (  # noqa: F401
    ConvergenceLifecycle as _convergence_lifecycle,
)
from agent.custom.action.fail_task import FailTask as _fail_task  # noqa: F401
from agent.custom.action.food_progress import (  # noqa: F401
    FoodBudgetReached as _food_budget_reached,
)
from agent.custom.action.guarded_input import GuardedInput as _guarded_input  # noqa: F401
from agent.custom.action.jianlin_planner import (
    PlanJianlinChallenge as _jianlin_planner,  # noqa: F401
)
from agent.custom.action.restart_game import (
    RestartGameSurface as _restart_game_surface,  # noqa: F401
)
from agent.custom.action.runtime_health import RuntimeHealth as _runtime_health  # noqa: F401
from agent.custom.action.task_lifecycle import (  # noqa: F401
    BeginTask,
    CloseKnownPaintingSurface,
    FailStartupRecovery,
    OpenGameHomeMenu,
    ReturnToHome,
    ReturnToWorldHome,
)
from agent.custom.recognition.martial_material import (  # noqa: F401
    MartialMaterialRelation as _martial_material_relation,
)
from agent.custom.sink.task_flow import (  # noqa: F401
    GlobalPrerequisiteStopSink as _global_prerequisite_stop_sink,
)


def main(socket_id: str) -> int:
    """Start the embedded AgentServer on one MFW-provided socket."""

    if not isinstance(socket_id, str) or not socket_id.strip():
        print("Usage: python -m agent.main <socket_id>", file=sys.stderr)
        return 2

    result = 0
    try:
        if not AgentServer.start_up(socket_id.strip()):
            raise RuntimeError("AgentServer.start_up returned false")
        try:
            AgentServer.join()
        except KeyboardInterrupt:
            result = 130
    except KeyboardInterrupt:
        result = 130
    except Exception as exc:
        print(f"AgentServer failed: {exc}", file=sys.stderr)
        result = 3
    finally:
        try:
            AgentServer.shut_down()
        except Exception as exc:
            print(f"AgentServer shutdown failed: {exc}", file=sys.stderr)
    return result


if __name__ == "__main__":  # pragma: no cover - exercised by the CLI.
    command_args = sys.argv[1:]
    if len(command_args) != 1:
        print("Usage: python -m agent.main <socket_id>", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main(command_args[0]))


__all__ = ["main"]
