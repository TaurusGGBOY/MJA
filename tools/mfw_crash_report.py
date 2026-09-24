"""Produce a local evidence index and optional offline LLDB inspection."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def report(
    root: Path, binary: Path | None = None, core: Path | None = None, address: int | None = None
) -> Path:
    lines = ["# MFW crash evidence", "", "Diagnostics only; native MFW logs own task outcomes.", ""]
    events = root / "events.jsonl"
    records = []
    if events.exists():
        for line in events.read_text().splitlines():
            try:
                records.append(json.loads(line))
            except ValueError:
                lines.append("Incomplete diagnostic record present.")
    lines += ["## Timeline", "", "```text"]
    lines += [json.dumps(row, ensure_ascii=False) for row in records[-100:]]
    lines += ["```", "", "## Evidence files", ""]
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "report.md":
            lines.append(f"- {path.relative_to(root)} ({path.stat().st_size} bytes)")
    lines += [
        "",
        "## Debugging limits",
        "",
        "A disappeared process is not proof of SIGSEGV. Compare recovery request timestamps.",
        "A nonzero capture command or timeout means the artifact may be empty or partial.",
        "Logcat rotates at 8 MiB x 5 files; older content can be absent.",
        "Match captured Mach-O UUID / tombstone ELF Build ID to the actual binary "
        "before attributing instructions.",
    ]
    if binary and (core or address is not None):
        command = ["lldb", "--batch"]
        if core:
            command += ["--core", str(core)]
        command += [str(binary), "-o", "image list -u"]
        if core:
            command += [
                "-o",
                "thread backtrace all",
                "-o",
                "register read",
                "-o",
                "disassemble --pc --count 32",
            ]
        else:
            command += [
                "-o",
                f"image lookup --address {address:#x}",
                "-o",
                f"disassemble --start-address {address:#x} --count 32",
            ]
        output = root / "lldb.txt"
        try:
            with output.open("wb") as stream:
                result = subprocess.run(
                    command, stdout=stream, stderr=subprocess.STDOUT, timeout=30, check=False
                )
            lines.append(f"LLDB exit code: {result.returncode}; see lldb.txt.")
        except (OSError, subprocess.TimeoutExpired) as exc:
            lines.append(f"LLDB unavailable/incomplete: {exc}")
        lines.append(
            "Core inspection requested; validate dump/binary identity."
            if core
            else "STATIC disassembly only: this is not a captured crash PC "
            "or proof the instruction executed."
        )
    else:
        lines.append(
            "No core/binary pair supplied: "
            "fault PC, registers and causal instruction remain unverified."
        )
    output = root / "report.md"
    output.write_text("\n".join(lines) + "\n")
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--core", type=Path)
    parser.add_argument("--address", type=lambda value: int(value, 0))
    args = parser.parse_args()
    print(report(args.evidence, args.binary, args.core, args.address))
