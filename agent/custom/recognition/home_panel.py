"""Color-independent matching for the fixed home-panel button only."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
from maa.agent.agent_server import AgentServer
from maa.custom_recognition import CustomRecognition
from PIL import Image

LOG = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[3]


def _gray(rgb: np.ndarray) -> np.ndarray:
    # Identical luminance conversion for templates and the callback BGR frame.
    return np.asarray(rgb, dtype=np.float64) @ np.array([0.299, 0.587, 0.114])


def _correlation(left: np.ndarray, right: np.ndarray) -> float | None:
    left = left - left.mean()
    right = right - right.mean()
    denominator = np.sqrt(np.square(left).sum() * np.square(right).sum())
    if not np.isfinite(denominator) or denominator <= 0:
        return None
    score = float((left * right).sum() / denominator)
    return score if np.isfinite(score) else None


@AgentServer.custom_recognition("HomePanelGray")
class HomePanelGray(CustomRecognition):
    """Use only argv.image; return the original full button hit box."""

    def analyze(self, context: Any, argv: CustomRecognition.AnalyzeArg):
        try:
            params = json.loads(argv.custom_recognition_param)
            box = params["roi"]
            if box != [1170, 10, 60, 60]:
                return None
            threshold = params["threshold"]
            if isinstance(threshold, bool) or not 0 < threshold <= 1:
                return None
            frame = argv.image
            if frame.shape != (720, 1280, 3) or frame.dtype != np.uint8:
                return None
            names = params["templates"]
            if not isinstance(names, list) or not names:
                return None
            default = (
                "resource/base/image" if (ROOT / "resource").is_dir()
                else "assets/resource/base/image"
            )
            image_root = ROOT / params.get("image_dir", default)
            x, y, width, height = box
            gray = _gray(frame[y:y + height, x:x + width, ::-1])
            scores = []
            for name in names:
                with Image.open(image_root / name) as image:
                    if image.size != (width, height):
                        return None
                    template = _gray(np.asarray(image.convert("RGB")))
                score = _correlation(template, gray)
                if score is not None:
                    scores.append((name, score))
            if not scores:
                return None
            name, best = max(scores, key=lambda item: item[1])
            LOG.debug("home panel gray node=%s score=%.6f threshold=%.6f template=%s",
                      argv.node_name, best, threshold, name)
            if best <= threshold:
                return None
            return CustomRecognition.AnalyzeResult(
                box=box,
                detail={"method": "gray_ccoeff_normed", "score": best,
                        "threshold": threshold, "template": name, "roi": box},
            )
        except (OSError, KeyError, TypeError, ValueError, AttributeError):
            LOG.debug("Home panel gray recognition unavailable", exc_info=True)
            return None
