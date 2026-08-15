from .batch1 import DAILY_TASK_REWARD_CLAIM_DAILY_DEFINITION, TableWorkflowDefinition

TRANSITIONS = DAILY_TASK_REWARD_CLAIM_DAILY_DEFINITION.transitions
DailyTaskRewardClaimDailyDefinition = TableWorkflowDefinition

__all__ = [
    "DAILY_TASK_REWARD_CLAIM_DAILY_DEFINITION",
    "DailyTaskRewardClaimDailyDefinition",
    "TRANSITIONS",
]
