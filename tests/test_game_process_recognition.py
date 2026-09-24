from types import SimpleNamespace

import pytest
from maa.define import ActionDetail, ActionEnum, ShellActionResult

from agent.custom.recognition.game_process import GameProcessExited


@pytest.mark.parametrize("success,output,hit", [
    (True, "MJA_GAME_PROCESS_EXITED\n", True),
    (True, "MJA_GAME_PROCESS_RUNNING\n", False),
    (True, "", False),
    (True, "adb: device not found", False),
    (False, "MJA_GAME_PROCESS_EXITED", False),
])
def test_only_positive_native_exit_evidence_triggers_recovery(success, output, hit):
    calls = []

    def run_action(entry):
        calls.append(entry)
        return ActionDetail(
            action_id=1, name=entry, action=ActionEnum.Shell, box=[0, 0, 0, 0],
            success=success,
            result=ShellActionResult(cmd="pidof", shell_timeout=3000,
                                     success=success, output=output),
            raw_detail={},
        )

    result = GameProcessExited().analyze(SimpleNamespace(run_action=run_action), None)
    assert (result is not None) is hit
    assert calls == ["启动-读取游戏进程"]
