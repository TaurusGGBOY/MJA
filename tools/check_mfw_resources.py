"""Static checks for the MFW resource tree and Maa Pipeline graph."""

from __future__ import annotations

import argparse
import json
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FORBIDDEN = (
    "daily_all",
    "DailyWorkflowAction",
    "MaaAndroidWorkflowDriver",
    "speedrun",
)

RECOGNITION_TYPES = frozenset(
    {
        "DirectHit",
        "directhit",
        "TemplateMatch",
        "templatematch",
        "FeatureMatch",
        "featurematch",
        "OCR",
        "ocr",
        "NeuralNetworkClassify",
        "neuralnetworkclassify",
        "NNClassify",
        "NeuralNetworkDetect",
        "neuralnetworkdetect",
        "NNDetect",
        "ColorMatch",
        "colormatch",
        "And",
        "and",
        "Or",
        "or",
        "Custom",
        "custom",
    }
)

TASK_ENTRY_RULES = (
    "entry_convergence",
    "unified_end_boundary",
    "duplicate_game_start_recovery",
)

_SHARED_CONVERGENCE_NAMES = frozenset(
    {
        "启动-游戏启动",
        "启动-游戏就绪",
        "MJA_COMMON_ENTRY",
        "MJA_STATE_CONVERGENCE",
    }
)
_SHARED_STARTUP_NAMES = (
    "启动-游戏启动",
    "启动-游戏就绪",
    "启动-标题-或-加载",
    "MJA_START_KNOWN_POPUP",
    "MJA_START_KNOWN_PAGE",
)
_RESUME_MARKERS = (
    "RESUME",
    "CONTINUE",
    "PENDING",
    "IN_PROGRESS",
    "RETRY",
    "恢复",
    "继续",
    "待处理",
    "进行中",
    "重试",
)
_RECOVERY_EVIDENCE_MARKERS = (
    "PAGE",
    "PANEL",
    "RESULT",
    "REWARD",
    "STATE",
    "TASK",
    "CARD",
    "BATTLE",
    "页面",
    "面板",
    "结果",
    "奖励",
    "状态",
    "任务",
    "卡",
    "战斗",
)
_STARTUP_FAILURE_MARKERS = (
    "UNKNOWN",
    "FAIL",
    "ABORT",
    "RUNTIME",
    "未知",
    "失败",
    "中止",
    "运行时",
)
_HOME_MARKERS = ("HOME", "MAIN", "LOBBY", "HUB", "主页", "首页", "大厅")
_STARTUP_COPY_MARKERS = (
    "START",
    "LOADING",
    "POPUP",
    "TITLE",
    "READY",
    "GAME",
    "启动",
    "加载",
    "弹窗",
    "标题",
    "就绪",
    "游戏",
)
_TASK_SPECIFIC_FIELDS = frozenset(
    {
        "action_id",
        "amount_index",
        "budget_amount",
        "condition",
        "error_code",
        "evidence",
        "material_id",
        "material_relation",
        "observed_amount",
        "postcondition",
        "resource_id",
        "resource_index",
        "task_id",
    }
)


@dataclass(frozen=True)
class TaskEntryDiagnostic:
    """One structured result from the daily task-entry static gate."""

    task_file: str
    rule: str
    ok: bool
    evidence_nodes: tuple[str, ...] = ()
    gap: str | None = None
    entry_nodes: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_file": self.task_file,
            "rule": self.rule,
            "ok": self.ok,
            "evidence_nodes": list(self.evidence_nodes),
            "gap": self.gap,
            "entry_nodes": list(self.entry_nodes),
        }

    to_dict = as_dict

    def __getitem__(self, key: str) -> Any:
        return self.as_dict()[key]

    def format(self) -> str:
        evidence = ", ".join(self.evidence_nodes) or "none"
        entries = ", ".join(self.entry_nodes) or "none"
        status = "ok" if self.ok else "gap"
        gap = f"; gap: {self.gap}" if self.gap else ""
        return (
            f"task entry gate: {self.task_file} [{self.rule}] {status}; "
            f"entry nodes: {entries}; evidence nodes: {evidence}{gap}"
        )


def load_pipeline_nodes(root: Path) -> dict[str, dict[str, Any]]:
    root = Path(root)
    if not root.is_dir():
        raise FileNotFoundError(root)
    nodes: dict[str, dict[str, Any]] = {}
    for path in sorted(root.rglob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"pipeline file must contain an object: {path}")
        candidate = payload.get("pipeline", payload)
        if not isinstance(candidate, dict):
            raise ValueError(f"pipeline nodes must be an object: {path}")
        for name, node in candidate.items():
            if not isinstance(name, str) or not isinstance(node, dict):
                raise ValueError(f"malformed pipeline node in {path}")
            if name in nodes:
                raise ValueError(f"duplicate pipeline node: {name}")
            nodes[name] = node
    return nodes


def _targets(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        target = value
        while target.startswith("[") and "]" in target:
            target = target[target.index("]") + 1 :]
        return [target]
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        targets: list[str] = []
        for item in value:
            target = item
            while target.startswith("[") and "]" in target:
                target = target[target.index("]") + 1 :]
            targets.append(target)
        return targets
    return ["<malformed-target>"]


def _has_unbounded_cycle(nodes: dict[str, dict[str, Any]]) -> set[str]:
    unbounded: set[str] = set()
    for name, node in nodes.items():
        targets = _targets(node.get("next")) + _targets(node.get("on_error"))
        if name in targets and not any(
            key in node
            for key in ("max_hit", "max_times", "retry_times", "limit", "timeout")
        ):
            unbounded.add(name)
    return unbounded


def _load_task_file_nodes(path: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"pipeline file must contain an object: {path}")
    candidate = payload.get("pipeline", payload)
    if not isinstance(candidate, dict):
        raise ValueError(f"pipeline nodes must be an object: {path}")
    nodes: dict[str, dict[str, Any]] = {}
    for name, node in candidate.items():
        if not isinstance(name, str) or not isinstance(node, dict):
            raise ValueError(f"malformed pipeline node in {path}")
        nodes[name] = node
    return nodes


def _pipeline_daily_root(root: Path) -> tuple[Path, Path | None]:
    root = Path(root)
    if (root / "pipeline" / "daily").is_dir():
        return root / "pipeline", root / "pipeline" / "daily"
    if (root / "daily").is_dir():
        return root, root / "daily"
    if root.name == "daily" and root.is_dir():
        return root.parent, root
    return root, None


def _entry_candidates(nodes: Mapping[str, Mapping[str, Any]]) -> tuple[str, ...]:
    explicit = sorted(
        name
        for name, node in nodes.items()
        if node.get("entry") is True or node.get("is_entry") is True
    )
    if explicit:
        return tuple(explicit)

    begin_task = sorted(
        name for name, node in nodes.items() if node.get("custom_action") == "BeginTask"
    )
    if begin_task:
        return tuple(begin_task)

    start_nodes = sorted(
        name
        for name in nodes
        if name.upper().endswith("_START") or name.endswith("任务入口")
    )
    return tuple(start_nodes)


def _reachable_distances(
    nodes: Mapping[str, Mapping[str, Any]], sources: tuple[str, ...]
) -> dict[str, int]:
    distances: dict[str, int] = {}
    pending = deque((source, 0) for source in sources)
    while pending:
        current, distance = pending.popleft()
        if current in distances:
            continue
        distances[current] = distance
        node = nodes.get(current)
        if not isinstance(node, Mapping):
            continue
        targets = _targets(node.get("next")) + _targets(node.get("on_error"))
        pending.extend((target, distance + 1) for target in targets)
    return distances


def _node_targets(node: Mapping[str, Any]) -> list[str]:
    return _targets(node.get("next")) + _targets(node.get("on_error"))


def _is_shared_convergence_node(name: str, node: Mapping[str, Any]) -> bool:
    upper = name.upper()
    if name in _SHARED_CONVERGENCE_NAMES:
        return True
    if any(
        marker in upper
        for marker in ("STATE_CONVERGENCE", "SHARED_ENTRY", "状态收敛", "共享入口")
    ):
        return node.get("action") != "StopTask"
    return False


def _is_task_resume_node(name: str, node: Mapping[str, Any]) -> bool:
    upper = name.upper()
    if node.get("action") == "StopTask" or node.get("custom_action") == "RecordTaskOutcome":
        return False
    if any(marker in upper for marker in _RESUME_MARKERS):
        return not any(marker in upper for marker in _STARTUP_FAILURE_MARKERS)
    if "RECOVER" not in upper and "恢复" not in upper:
        return False
    if any(marker in upper for marker in _STARTUP_FAILURE_MARKERS):
        return False
    return any(marker in upper for marker in _RECOVERY_EVIDENCE_MARKERS)


def _is_home_entry_node(name: str, node: Mapping[str, Any]) -> bool:
    upper = name.upper()
    if not any(marker in upper for marker in _HOME_MARKERS):
        return False
    if any(
        marker in upper
        for marker in ("UNKNOWN", "FAIL", "ABORT", "CLOSE", "EXIT", "未知", "失败", "中止", "关闭", "退出")
    ):
        return False
    if node.get("action") == "StopTask" or node.get("custom_action") == "RecordTaskOutcome":
        return False
    return (
        bool(node.get("recognition"))
        or "PROBE" in upper
        or "ENTRY" in upper
        or "探测" in upper
        or "入口" in upper
    )


def _entry_convergence_diagnostic(
    task_file: str,
    nodes: Mapping[str, Mapping[str, Any]],
    entry_nodes: tuple[str, ...],
) -> TaskEntryDiagnostic:
    if not entry_nodes:
        return TaskEntryDiagnostic(
            task_file=task_file,
            rule="entry_convergence",
            ok=False,
            gap=(
                "no task entry found; expected a BeginTask, an explicit entry marker, "
                "or a node whose name ends with _START"
            ),
        )

    distances = _reachable_distances(nodes, entry_nodes)
    predicates = (
        _is_shared_convergence_node,
        _is_task_resume_node,
        _is_home_entry_node,
    )
    for predicate in predicates:
        candidates = sorted(
            (
                name
                for name in distances
                if name in nodes and predicate(name, nodes[name])
            ),
            key=lambda name: (distances[name], name),
        )
        if candidates:
            return TaskEntryDiagnostic(
                task_file=task_file,
                rule="entry_convergence",
                ok=True,
                evidence_nodes=(candidates[0],),
                entry_nodes=entry_nodes,
            )

    reachable = sorted(
        (name for name in distances if name in nodes),
        key=lambda name: (distances[name], name),
    )
    observed = ", ".join(reachable[:12]) or "none"
    return TaskEntryDiagnostic(
        task_file=task_file,
        rule="entry_convergence",
        ok=False,
        entry_nodes=entry_nodes,
        gap=(
            "entry does not reach a shared convergence node, a current-task "
            f"resume/continuation node, or a home entry; reachable nodes: {observed}"
        ),
    )


def _outcome_status(node: Mapping[str, Any]) -> Any:
    params = node.get("custom_action_param")
    if isinstance(params, Mapping):
        return params.get("status")
    return node.get("status", node.get("outcome"))


def _is_recorded_outcome(node: Mapping[str, Any]) -> bool:
    return node.get("custom_action") == "RecordTaskOutcome"


def _is_failed_outcome(name: str, node: Mapping[str, Any]) -> bool:
    if _outcome_status(node) == "failed":
        return True
    if node.get("Abort") is True:
        return True
    if _outcome_status(node) is None:
        upper = name.upper()
        return any(marker in upper for marker in ("FAIL", "ABORT", "失败", "中止"))
    return False


def _is_stop_boundary(name: str, node: Mapping[str, Any]) -> bool:
    if name == "公共-通用停止":
        return True
    if node.get("action") == "StopTask":
        return node.get("Abort") is not True
    if _is_recorded_outcome(node) and not _is_failed_outcome(name, node):
        return not _node_targets(node)
    return (
        _is_home_entry_node(name, node)
        and node.get("action") == "DoNothing"
        and not _node_targets(node)
    )


def _is_abort_boundary(name: str, node: Mapping[str, Any]) -> bool:
    if name == "公共-通用中止":
        return True
    return node.get("Abort") is True and (
        node.get("action") == "StopTask" or _is_recorded_outcome(node)
    )


def _common_boundaries(
    nodes: Mapping[str, Mapping[str, Any]],
    sources: list[str],
    predicate: Any,
) -> set[str]:
    reachable_boundaries: list[set[str]] = []
    for source in sources:
        distances = _reachable_distances(nodes, (source,))
        reachable_boundaries.append(
            {
                name
                for name in distances
                if name in nodes and predicate(name, nodes[name])
            }
        )
    if not reachable_boundaries:
        return set()
    return set.intersection(*reachable_boundaries)


def _unified_end_diagnostic(
    task_file: str,
    nodes: Mapping[str, Mapping[str, Any]],
    entry_nodes: tuple[str, ...],
) -> TaskEntryDiagnostic:
    if not entry_nodes:
        return TaskEntryDiagnostic(
            task_file=task_file,
            rule="unified_end_boundary",
            ok=False,
            gap="cannot inspect end boundary because no task entry was found",
        )

    entry_distances = _reachable_distances(nodes, entry_nodes)
    reachable_outcomes = [
        name
        for name in entry_distances
        if name in nodes and _is_recorded_outcome(nodes[name])
    ]
    normal_outcomes = [
        name for name in reachable_outcomes if not _is_failed_outcome(name, nodes[name])
    ]
    failed_outcomes = [
        name for name in reachable_outcomes if _is_failed_outcome(name, nodes[name])
    ]
    normal_sources = normal_outcomes or list(entry_nodes)
    failure_sources = failed_outcomes or list(entry_nodes)
    normal_boundaries = _common_boundaries(nodes, normal_sources, _is_stop_boundary)
    failure_boundaries = _common_boundaries(nodes, failure_sources, _is_abort_boundary)
    evidence = tuple(sorted(normal_boundaries | failure_boundaries))

    gaps: list[str] = []
    if not normal_boundaries:
        if normal_outcomes:
            gaps.append(
                "normal completion outcomes do not share one stop/home/success boundary"
            )
        else:
            gaps.append("no normal completion path reaches a stop/home/success boundary")
    if not failure_boundaries:
        if failed_outcomes:
            gaps.append("failure outcomes do not share one abort boundary")
        else:
            gaps.append("no failure path reaches an abort boundary")
    return TaskEntryDiagnostic(
        task_file=task_file,
        rule="unified_end_boundary",
        ok=not gaps,
        evidence_nodes=evidence,
        gap="; ".join(gaps) if gaps else None,
        entry_nodes=entry_nodes,
    )


def _static_node_signature(node: Mapping[str, Any]) -> str:
    comparable = {
        key: value for key, value in node.items() if key not in {"next", "on_error"}
    }
    return json.dumps(comparable, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _has_task_specific_condition(node: Mapping[str, Any]) -> bool:
    if _TASK_SPECIFIC_FIELDS.intersection(node):
        return True
    params = node.get("custom_action_param")
    return isinstance(params, Mapping) and bool(_TASK_SPECIFIC_FIELDS.intersection(params))


def _duplicate_game_start_diagnostic(
    task_file: str,
    all_nodes: Mapping[str, Mapping[str, Any]],
    local_nodes: Mapping[str, Mapping[str, Any]],
    entry_nodes: tuple[str, ...],
) -> TaskEntryDiagnostic:
    shared_signatures: dict[str, list[str]] = {}
    for name in _SHARED_STARTUP_NAMES:
        node = all_nodes.get(name)
        if node is not None:
            shared_signatures.setdefault(_static_node_signature(node), []).append(name)

    matches: list[tuple[str, str]] = []
    for name, node in local_nodes.items():
        if name in _SHARED_STARTUP_NAMES or _has_task_specific_condition(node):
            continue
        shared_names = shared_signatures.get(_static_node_signature(node), [])
        if not shared_names:
            continue
        if not any(marker in name.upper() for marker in _STARTUP_COPY_MARKERS):
            continue
        matches.append((name, shared_names[0]))

    local_matches = tuple(sorted(name for name, _ in matches))
    startup_named_matches = sum(
        any(marker in name.upper() for marker in _STARTUP_COPY_MARKERS)
        for name in local_matches
    )
    if len(local_matches) < 3 or startup_named_matches < 2:
        return TaskEntryDiagnostic(
            task_file=task_file,
            rule="duplicate_game_start_recovery",
            ok=True,
            entry_nodes=entry_nodes,
        )

    shared_matches = tuple(sorted(shared_name for _, shared_name in matches))
    return TaskEntryDiagnostic(
        task_file=task_file,
        rule="duplicate_game_start_recovery",
        ok=False,
        evidence_nodes=local_matches,
        entry_nodes=entry_nodes,
        gap=(
            "task file contains a complete group of nodes structurally matching "
            "shared GAME_START recovery nodes "
            f"{', '.join(shared_matches)}; copied nodes: {', '.join(local_matches)}"
        ),
    )


def check_task_entry_contracts(
    pipeline_root: Path,
    nodes: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[TaskEntryDiagnostic]:
    """Inspect daily task entry, end-boundary, and recovery-copy contracts.

    The function is deliberately diagnostic-only.  It reads ``pipeline/daily``
    files, while ``nodes`` supplies the complete graph used for reachability and
    shared-node comparisons.  A pipeline root without a daily directory has no
    task-entry scope and returns an empty list for compatibility with older
    resource bundles.
    """

    graph_root, daily_root = _pipeline_daily_root(Path(pipeline_root))
    if daily_root is None:
        return []
    all_nodes = nodes if nodes is not None else load_pipeline_nodes(graph_root)
    diagnostics: list[TaskEntryDiagnostic] = []
    for path in sorted(daily_root.glob("*.json")):
        local_nodes = _load_task_file_nodes(path)
        task_file = path.relative_to(graph_root).as_posix()
        entry_nodes = _entry_candidates(local_nodes)
        diagnostics.extend(
            (
                _entry_convergence_diagnostic(task_file, all_nodes, entry_nodes),
                _unified_end_diagnostic(task_file, all_nodes, entry_nodes),
                _duplicate_game_start_diagnostic(
                    task_file, all_nodes, local_nodes, entry_nodes
                ),
            )
        )
    return diagnostics


def validate_guarded_input_evidence(
    nodes: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    """Validate GuardedInput indices and names against its And recognition.

    GuardedInput validates all evidence against the same Maa ``And`` result.
    When a pipeline removes an ``all_of`` member but keeps the old evidence
    indices, the recognition can still succeed while the input is denied.
    Keep this structural contract in the offline resource validator so that a
    simplification cannot silently create that runtime-only failure.
    """

    errors: list[str] = []
    indexed_fields = (
        "page_index",
        "target_index",
        "resource_index",
        "amount_index",
        "material_index",
        "owned_index",
        "required_index",
        "material_relation_index",
    )
    name_fields = (
        ("page_index", "page_name"),
        ("target_index", "target_name"),
    )

    for node_name, node in nodes.items():
        if node.get("custom_action") != "GuardedInput":
            continue

        params = node.get("custom_action_param")
        if not isinstance(params, Mapping):
            errors.append(f"{node_name} GuardedInput has malformed custom_action_param")
            continue

        recognition = node.get("recognition")
        if not isinstance(recognition, Mapping) or str(
            recognition.get("type", "")
        ).casefold() != "and":
            errors.append(f"{node_name} GuardedInput requires And recognition")
            continue

        recognition_param = recognition.get("param")
        all_of = (
            recognition_param.get("all_of")
            if isinstance(recognition_param, Mapping)
            else None
        )
        if not isinstance(all_of, list) or not all_of:
            errors.append(f"{node_name} GuardedInput requires non-empty And.all_of")
            continue

        evidence = params.get("evidence")
        if not isinstance(evidence, Mapping):
            errors.append(f"{node_name} GuardedInput has malformed evidence")
            continue

        for field in indexed_fields:
            if field not in evidence and field not in params:
                continue
            value = evidence.get(field) if field in evidence else params.get(field)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
                or value >= len(all_of)
            ):
                errors.append(
                    f"{node_name} GuardedInput {field}={value!r} is outside "
                    f"And.all_of (size {len(all_of)})"
                )

        for index_field, name_field in name_fields:
            if name_field not in evidence:
                continue
            index = evidence.get(index_field)
            name = evidence.get(name_field)
            if (
                isinstance(index, int)
                and not isinstance(index, bool)
                and 0 <= index < len(all_of)
                and name != all_of[index]
            ):
                errors.append(
                    f"{node_name} GuardedInput {name_field}={name!r} does not "
                    f"match And.all_of[{index}]={all_of[index]!r}"
                )

    return errors


def validate_nodes(nodes: dict[str, dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    serialized = json.dumps(nodes, ensure_ascii=False).lower()
    for forbidden in FORBIDDEN:
        if forbidden.lower() in serialized:
            errors.append(f"forbidden control plane: {forbidden}")

    names = set(nodes)
    for name, node in nodes.items():
        recognition = node.get("recognition")
        if isinstance(recognition, str) and recognition not in RECOGNITION_TYPES:
            errors.append(
                f"{name} has unknown recognition type {recognition}; "
                "node references must be nested in And/Or sub-recognition"
            )
        for field in ("next", "on_error"):
            if field not in node:
                continue
            raw_targets = node[field]
            targets = _targets(raw_targets)
            if targets == ["<malformed-target>"]:
                errors.append(f"{name} has malformed {field}")
            for target in targets:
                if target not in names:
                    errors.append(f"{name} references missing target {target}")
        status = node.get("status", node.get("outcome"))
        if status == "failed" and node.get("Abort") is not True:
            errors.append(f"business failure node {name} must set Abort=true")

    for name in _has_unbounded_cycle(nodes):
        errors.append(f"unbounded cycle at {name}")
    errors.extend(validate_guarded_input_evidence(nodes))
    return errors


def check_resource_tree(root: Path, task_entry_gate: bool = False) -> list[str]:
    root = Path(root)
    errors: list[str] = []
    for relative in (
        Path("model/ocr/det.onnx"),
        Path("model/ocr/rec.onnx"),
        Path("model/ocr/keys.txt"),
    ):
        if not (root / relative).is_file():
            errors.append(f"missing resource file: {relative}")
    try:
        nodes = load_pipeline_nodes(root / "pipeline")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [str(exc)]
    errors.extend(validate_nodes(nodes))
    for required in ("公共-通用停止", "公共-通用中止"):
        if required not in nodes:
            errors.append(f"missing common node: {required}")
    if task_entry_gate:
        errors.extend(
            diagnostic.format()
            for diagnostic in check_task_entry_contracts(root / "pipeline", nodes)
            if not diagnostic.ok
        )
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument(
        "--task-entry-gate",
        action="store_true",
        help="include non-ok daily task-entry diagnostics in resource errors",
    )
    args = parser.parse_args(argv)
    errors = check_resource_tree(args.root, task_entry_gate=args.task_entry_gate)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    nodes = load_pipeline_nodes(args.root / "pipeline")
    print(f"validated {len(nodes)} pipeline nodes with zero errors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
