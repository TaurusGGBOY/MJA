from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).parents[1]
RUNTIME_ROOTS = (ROOT / "agent", ROOT / "tools", ROOT / "native", ROOT / "assets")
RUNTIME_SUFFIXES = {".json", ".plist", ".py", ".sh", ".toml", ".yaml", ".yml", ".zsh"}
FORBIDDEN_TERMINAL_LAUNCHES = (
    re.compile(r"Terminal\.app", re.IGNORECASE),
    re.compile(r"\bopen\s+(?:-[A-Za-z]+\s+)*[\"']?Terminal\b", re.IGNORECASE),
    re.compile(r"tell\s+application\s+[\"'](?:Terminal|终端)", re.IGNORECASE),
)


def test_runtime_never_launches_macos_terminal() -> None:
    violations: list[str] = []
    for runtime_root in RUNTIME_ROOTS:
        for path in runtime_root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in RUNTIME_SUFFIXES:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for pattern in FORBIDDEN_TERMINAL_LAUNCHES:
                if pattern.search(text):
                    violations.append(f"{path.relative_to(ROOT)}: {pattern.pattern}")

    assert not violations, "runtime code must not launch macOS Terminal:\n" + "\n".join(violations)
