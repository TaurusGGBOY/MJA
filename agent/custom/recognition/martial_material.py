"""Same-frame martial material relation recognition for the MFW pipeline."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from maa.agent.agent_server import AgentServer
from maa.custom_recognition import CustomRecognition

_RATIO_PATTERN = re.compile(
    r"(?<!\d)(\d{1,6})\s*/\s*(\d{1,6})(?!\d)"
)
_RELATIONS = frozenset({"owned>=required", "owned<required"})


def _parameters(raw: Any) -> tuple[tuple[str, ...], str, tuple[int, int, int, int]]:
    if isinstance(raw, str):
        payload = json.loads(raw)
    else:
        payload = raw
    if not isinstance(payload, Mapping):
        raise ValueError("martial material parameters must be an object")

    raw_nodes = payload.get("ratio_nodes")
    if (
        not isinstance(raw_nodes, Sequence)
        or isinstance(raw_nodes, (str, bytes, bytearray))
        or not 2 <= len(raw_nodes) <= 4
    ):
        raise ValueError("ratio_nodes must contain two to four OCR nodes")
    nodes = tuple(raw_nodes)
    if any(not isinstance(node, str) or not node.strip() for node in nodes):
        raise ValueError("ratio_nodes must contain non-empty strings")
    if len(set(nodes)) != len(nodes):
        raise ValueError("ratio_nodes must be unique")

    relation = payload.get("material_relation")
    if relation not in _RELATIONS:
        raise ValueError("unsupported martial material relation")

    raw_box = payload.get("box", [500, 520, 410, 90])
    if (
        not isinstance(raw_box, Sequence)
        or isinstance(raw_box, (str, bytes, bytearray))
        or len(raw_box) != 4
        or any(isinstance(value, bool) or not isinstance(value, int) for value in raw_box)
    ):
        raise ValueError("box must contain four integers")
    box = tuple(raw_box)
    if box[0] < 0 or box[1] < 0 or box[2] <= 0 or box[3] <= 0:
        raise ValueError("box must be a positive on-screen rectangle")
    return nodes, relation, box


def _ocr_texts(detail: Any) -> tuple[str, ...]:
    if not getattr(detail, "hit", False):
        return ()
    values: list[str] = []
    best = getattr(detail, "best_result", None)
    best_text = getattr(best, "text", None)
    if isinstance(best_text, str) and best_text.strip():
        values.append(best_text.strip())
    for result in getattr(detail, "filtered_results", ()) or ():
        text = getattr(result, "text", None)
        if isinstance(text, str) and text.strip():
            values.append(text.strip())
    return tuple(dict.fromkeys(values))


def _single_ratio(detail: Any) -> tuple[int, int] | None:
    texts = _ocr_texts(detail)
    ratios: list[tuple[int, int]] = []
    candidates = list(texts)
    # Game icons can split a visible ratio into multiple OCR results, for
    # example 920 + 武 + /1200. The ratio ROI is already scoped to one
    # material, so joining OCR fragments after removing non-ratio glyphs is
    # safe and keeps the relation fail-closed when either side is absent.
    compact = re.sub(r"[^0-9/]", "", "".join(texts))
    if compact:
        candidates.append(compact)
    for text in candidates:
        for match in _RATIO_PATTERN.finditer(text):
            ratio = (int(match.group(1)), int(match.group(2)))
            if ratio[1] > 0:
                ratios.append(ratio)
    unique = tuple(dict.fromkeys(ratios))
    if len(unique) != 1:
        return None
    return unique[0]


def material_relation_holds(
    ratios: Sequence[tuple[int, int]], relation: str
) -> bool:
    """Return the requested relation only for a complete non-empty ratio set."""

    if not ratios or relation not in _RELATIONS:
        return False
    if relation == "owned>=required":
        return all(owned >= required for owned, required in ratios)
    return any(owned < required for owned, required in ratios)


@AgentServer.custom_recognition("MartialMaterialRelation")
class MartialMaterialRelation(CustomRecognition):
    """Evaluate every configured owned/required pair on the callback image."""

    def analyze(
        self,
        context: Any,
        argv: CustomRecognition.AnalyzeArg,
    ) -> CustomRecognition.AnalyzeResult | None:
        try:
            nodes, relation, box = _parameters(argv.custom_recognition_param)
            ratios: list[tuple[int, int]] = []
            for node in nodes:
                detail = context.run_recognition(node, argv.image)
                ratio = _single_ratio(detail)
                if ratio is None:
                    return None
                ratios.append(ratio)
            if not material_relation_holds(ratios, relation):
                return None
            return CustomRecognition.AnalyzeResult(
                box=box,
                detail={
                    "material_relation": relation,
                    "ratios": [
                        {"owned": owned, "required": required}
                        for owned, required in ratios
                    ],
                },
            )
        except (KeyError, RuntimeError, TypeError, ValueError):
            return None


__all__ = ["MartialMaterialRelation", "material_relation_holds"]
