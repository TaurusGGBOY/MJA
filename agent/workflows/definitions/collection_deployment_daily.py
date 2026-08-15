from .batch1 import COLLECTION_DEPLOYMENT_DAILY_DEFINITION, TableWorkflowDefinition

TRANSITIONS = COLLECTION_DEPLOYMENT_DAILY_DEFINITION.transitions
CollectionDeploymentDailyDefinition = TableWorkflowDefinition

__all__ = [
    "COLLECTION_DEPLOYMENT_DAILY_DEFINITION",
    "CollectionDeploymentDailyDefinition",
    "TRANSITIONS",
]
