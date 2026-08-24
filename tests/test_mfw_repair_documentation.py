from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_agents_preserves_the_live_success_gate() -> None:
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "tools/mfw_live_acceptance.py finish" in text
    assert "GAME_START + 指定任务" in text


def test_worker_guide_names_all_22_business_tasks() -> None:
    text = (ROOT / "docs/testing/mfw-concurrent-task-repair.md").read_text(
        encoding="utf-8"
    )
    expected = {path.stem for path in (ROOT / "assets/tasks/日常").glob("*.json")}
    assert len(expected) == 22
    assert all(task_id in text for task_id in expected)
