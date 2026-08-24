"""Narrow custom actions registered by the embedded MFW Agent."""

from .convergence_lifecycle import ConvergenceLifecycle
from .fail_task import FailTask
from .guarded_input import GuardedInput
from .jianlin_planner import ChallengePlan, PlanJianlinChallenge, plan_safe_challenge
from .restart_game import RestartGameSurface
from .runtime_health import RuntimeHealth
from .task_lifecycle import (
    BeginTask,
    FailStartupRecovery,
)

__all__ = [
    "BeginTask",
    "ConvergenceLifecycle",
    "ChallengePlan",
    "FailStartupRecovery",
    "FailTask",
    "GuardedInput",
    "PlanJianlinChallenge",
    "RuntimeHealth",
    "RestartGameSurface",
    "plan_safe_challenge",
]
