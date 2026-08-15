"""Narrow custom actions registered by the embedded MFW Agent."""

from .guarded_input import GuardedInput
from .convergence_lifecycle import ConvergenceLifecycle
from .jianlin_planner import ChallengePlan, PlanJianlinChallenge, plan_safe_challenge
from .restart_game import RestartGameSurface
from .runtime_health import RuntimeHealth
from .task_lifecycle import (
    BeginTask,
    CompleteTaskBoundary,
    FailStartupRecovery,
    RecordActiveTaskFailure,
    RecordTaskOutcome,
)

__all__ = [
    "BeginTask",
    "CompleteTaskBoundary",
    "ConvergenceLifecycle",
    "ChallengePlan",
    "FailStartupRecovery",
    "GuardedInput",
    "PlanJianlinChallenge",
    "RecordActiveTaskFailure",
    "RecordTaskOutcome",
    "RuntimeHealth",
    "RestartGameSurface",
    "plan_safe_challenge",
]
