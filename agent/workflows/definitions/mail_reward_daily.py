from .batch1 import MAIL_REWARD_DAILY_DEFINITION, TableWorkflowDefinition

TRANSITIONS = MAIL_REWARD_DAILY_DEFINITION.transitions
MailRewardDailyDefinition = TableWorkflowDefinition

__all__ = ["MAIL_REWARD_DAILY_DEFINITION", "MailRewardDailyDefinition", "TRANSITIONS"]
