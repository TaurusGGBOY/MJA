"""Observe native actions without changing pipeline or controller behavior."""

from maa.agent.agent_server import AgentServer
from maa.context import ContextEventSink

from agent.custom.support.crash_evidence import emit


@AgentServer.context_sink()
class DiagnosticContextSink(ContextEventSink):
    def on_raw_notification(self, context, msg, details):
        if msg in {"Node.Action.Starting", "Node.Action.Failed", "Node.PipelineNode.Failed"}:
            emit(
                "native_node",
                native_event=msg,
                task_id=details.get("task_id"),
                node=details.get("name"),
                action_id=details.get("action_id"),
                reco_id=details.get("reco_id"),
            )
