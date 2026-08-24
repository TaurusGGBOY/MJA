from __future__ import annotations

import ast
import json
from pathlib import Path

from tools.mfw_install import verify_default_task_flow_runner

ROOT = Path(__file__).parents[1]
FORMAL_INTERFACE = ROOT / "assets/interface.json"
TASK_ROOT = ROOT / "assets/tasks"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _imported_tasks(interface: dict) -> list[dict]:
    tasks: list[dict] = []
    for relative in interface["import"]:
        payload = _read(FORMAL_INTERFACE.parent / relative)
        tasks.extend(payload["task"])
    return tasks


def test_formal_interface_is_the_single_native_mfw_control_plane() -> None:
    interface = _read(FORMAL_INTERFACE)

    assert isinstance(interface.get("import"), list)
    assert interface["task"] == []
    assert interface["resource"][0]["path"] == ["./resource/base"]
    assert interface["agent"]["child_args"] == ["{PROJECT_DIR}/agent/main.py"]
    assert "daily_all" not in json.dumps(interface, ensure_ascii=False).casefold()
    assert "mja_daily_" not in json.dumps(interface, ensure_ascii=False).casefold()

    tasks = _imported_tasks(interface)
    names = [task["name"] for task in tasks]
    assert len(names) == len(set(names))
    assert names[0] == "GAME_START"
    assert names[1] == "GAME_STOP"
    assert names[2:] == [
        "MAIL_REWARD_DAILY",
        "SHOP_FREE_GIFT_DAILY",
        "BUY_TEA_DAILY",
        "FREE_APPRAISAL_DAILY",
        "TRIAL_SWORD_DAILY",
        "HERO_DISPATCH_DAILY",
        "COLLECTION_DEPLOYMENT_DAILY",
        "WEEKLY_FREE_GIFT_DAILY",
        "SHADOW_RUINS_DAILY",
        "SPEND_CONDENSATE_DAILY",
        "MARTIAL_STUDY_BREAKTHROUGH_DAILY",
        "EAT_STAMINA_FOOD_DAILY",
        "EQUIPMENT_DECOMPOSE_DAILY",
        "DUNGEON_SWEEP_DAILY",
        "JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY",
        "RING_CHALLENGE_DAILY",
        "BREAK_ARRAY_MARTIAL_DAILY",
        "GUILD_ACTIVITY_CHALLENGE_DAILY",
        "GUILD_AFFAIRS_DAILY",
        "GUILD_DONATION_DAILY",
        "DAILY_TASK_REWARD_CLAIM_DAILY",
        "BATTLE_PASS_REWARD_DAILY",
    ]
    for preset in interface["preset"]:
        assert [task["name"] for task in preset["task"]][0] != "GAME_START"
        assert "GAME_STOP" not in {task["name"] for task in preset["task"]}


def test_formal_imports_are_relative_and_point_at_checked_in_task_files() -> None:
    interface = _read(FORMAL_INTERFACE)

    for relative in interface["import"]:
        path = FORMAL_INTERFACE.parent / relative
        assert path.is_file(), relative
        assert not Path(relative).is_absolute()
        assert path.parent == TASK_ROOT / ("日常" if "日常" in relative else "")


def test_embedded_agent_has_no_legacy_aggregate_registration() -> None:
    source = (ROOT / "agent/main.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }

    assert ".".join(("agent", "workflows", "aggregate")) not in imported_modules
    assert ".".join(("agent", "workflows", "engine")) not in imported_modules
    assert ".".join(("agent", "workflows", "maa_android")) not in imported_modules
    assert "Daily" + "WorkflowAction" not in source
    assert "Aggregate" + "Daily" + "WorkflowAction" not in source


def test_base_pipelines_do_not_route_through_the_legacy_daily_action() -> None:
    for path in (ROOT / "assets/resource/base/pipeline").rglob("*.json"):
        text = path.read_text(encoding="utf-8")
        assert "Daily" + "WorkflowAction" not in text, path
        assert "Aggregate" + "Daily" + "WorkflowAction" not in text, path
        assert "daily_all" not in text.casefold(), path


def test_mfw_production_sources_do_not_reference_an_external_watchdog() -> None:
    production_roots = (
        ROOT / "assets",
        ROOT / "agent",
        ROOT / "tools/mfw_live_acceptance.py",
        ROOT / "tools/mfw_task_selection.py",
        ROOT / "tools/launch_mfw.zsh",
    )
    for root in production_roots:
        paths = [root] if root.is_file() else root.rglob("*")
        for path in paths:
            if not path.is_file() or path.suffix not in {".py", ".json", ".sh", ".zsh"}:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            assert "mfw_runtime_watchdog.py" not in text, path
            if path == ROOT / "tools/launch_mfw.zsh":
                assert "while kill -0" not in text, path
                assert "adb_failure_streak" not in text, path
                assert "kill -INT" not in text, path


def test_mfw_pyqt6_runtime_uses_official_queue_behavior() -> None:
    installer = (ROOT / "tools/mfw_install.py").read_text(encoding="utf-8")
    sink = (ROOT / "agent/custom/sink/task_flow.py").read_text(encoding="utf-8")

    assert "apply_mfw_pyqt6_runtime_patch" not in installer
    assert "verify_mfw_pyqt6_runtime_patch" not in installer
    assert "verify_default_task_flow_runner" in installer
    assert "GlobalPrerequisiteStopSink" in sink
    assert "TaskFlowStopSink" not in sink
    assert not (ROOT / "tools/mfw_pyqt6_patch.py").exists()
    assert not (ROOT / "native/mfw-pyqt6/patches/0001-return-false-on-task-failure.patch").exists()


def test_fake_candidate_passes_default_task_flow_verification(tmp_path: Path) -> None:
    (tmp_path / "MFW").write_bytes(b"official-test-runtime")

    verify_default_task_flow_runner(tmp_path)


def test_retired_legacy_execution_surface_is_absent() -> None:
    retired = (
        ROOT / "agent/actions/daily_workflow.py",
        ROOT / "agent/workflows",
        ROOT / "tools/android_run.py",
        ROOT / "tools/android_daily_run.py",
        ROOT / "tools/project_interface.py",
        ROOT / "tools/verification_records.py",
        ROOT / "tools/verify_live_tasks.py",
        ROOT / "scripts/run-all-dailies.sh",
    )
    assert all(
        not any(path.glob("*.py")) if path.is_dir() else not path.exists()
        for path in retired
    )


def test_supported_android_setup_surface_remains_present() -> None:
    retained = (
        ROOT / "tools/android_device.py",
        ROOT / "tools/android_emulator_contract.py",
        ROOT / "tools/android_maa_config.py",
        ROOT / "tools/android_setup.py",
        ROOT / "tools/launch_android_emulator.zsh",
        ROOT / "tools/mfw_android_preflight.py",
    )
    assert all(path.is_file() for path in retained)
