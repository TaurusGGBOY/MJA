"""Observe game process exit through a native MFW read-only shell action."""

from maa.agent.agent_server import AgentServer
from maa.custom_recognition import CustomRecognition

from agent.custom.support.crash_evidence import emit


@AgentServer.custom_recognition("GameProcessExited")
class GameProcessExited(CustomRecognition):
    def analyze(self, context, argv):
        try:
            result = context.run_action("启动-读取游戏进程")
            if not result or not result.success or not result.result.success:
                return None
            if result.result.output.strip() != "MJA_GAME_PROCESS_EXITED":
                return None
            emit("game_process_absent", task_id=getattr(context, "task_id", None),
                 node=getattr(argv, "node_name", None))
            return CustomRecognition.AnalyzeResult(
                box=[0, 0, 1, 1], detail={"game_process_absent": True}
            )
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return None
