"""Read-only gate for admitting the complete daily task set."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from typing import Sequence

from agent.workflows.catalog import WORKFLOW_DEFINITION_ORDER
from agent.workflows.verification import VerificationState, load_verification_record


def _is_ancestor(repository_root: Path, commit: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(repository_root), "merge-base", "--is-ancestor", commit, "HEAD"],
        check=False,
    )
    return result.returncode == 0


def verify_live_tasks(
    repository_root: Path,
    *,
    required_task_ids: Sequence[str] = WORKFLOW_DEFINITION_ORDER,
    require_local_evidence: bool = False,
) -> list[str]:
    root = repository_root.resolve()
    record_root = root / "verification" / "tasks"
    errors: list[str] = []
    expected = tuple(required_task_ids)
    for task_id in expected:
        path = record_root / f"{task_id}.json"
        if not path.is_file():
            errors.append(f"{task_id}: missing record")
            continue
        try:
            record = load_verification_record(
                path, repository_root=root, require_local_evidence=require_local_evidence
            )
        except (OSError, ValueError, TypeError) as exc:
            errors.append(f"{task_id}: {exc}")
            continue
        if record.task_id != task_id:
            errors.append(f"{task_id}: record task_id is {record.task_id}")
        if record.state is not VerificationState.LIVE_VERIFIED:
            errors.append(f"{task_id}: state={record.state.value}")
        elif not _is_ancestor(root, record.implementation_commit):
            errors.append(f"{task_id}: implementation commit is not an ancestor of HEAD")
    actual = {path.stem for path in record_root.glob("*.json")} if record_root.is_dir() else set()
    extra = actual - set(expected)
    errors.extend(f"{item}: unexpected record" for item in sorted(extra))
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check live admission records without modifying them"
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--all", action="store_true", help="check all canonical daily tasks")
    parser.add_argument("--require-local-evidence", action="store_true")
    args = parser.parse_args(argv)
    if not args.all:
        parser.error("--all is required")
    errors = verify_live_tasks(
        args.root, require_local_evidence=args.require_local_evidence
    )
    if errors:
        for error in errors:
            print(error)
        return 1
    print(f"live admission passed: {len(WORKFLOW_DEFINITION_ORDER)} tasks")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
