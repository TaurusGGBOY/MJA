"""Load an MFW candidate's Maa resource bundle with the bundled runtime."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from maa.library import Library
from maa.resource import Resource


def load_resource(candidate: Path) -> str:
    candidate = Path(candidate).resolve()
    runtime = candidate / "runtimes/osx-arm64"
    if not runtime.is_dir():
        raise FileNotFoundError(runtime)

    interface_path = candidate / "interface.json"
    if not interface_path.is_file():
        raise FileNotFoundError(interface_path)
    interface = json.loads(interface_path.read_text(encoding="utf-8"))
    resource_roots: list[Path] = []
    for resource in interface.get("resource", ()):
        if not isinstance(resource, dict):
            continue
        for raw_path in resource.get("path", ()):
            if not isinstance(raw_path, str):
                continue
            relative = Path(raw_path)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError(f"unsafe resource path: {raw_path}")
            root = candidate / relative
            if root.is_dir() and root not in resource_roots:
                resource_roots.append(root)
    if not resource_roots:
        raise FileNotFoundError(f"no resource roots declared by {interface_path}")

    Library.open(runtime)
    resource = Resource()
    for resource_root in resource_roots:
        job = resource.post_bundle(resource_root)
        job.wait()
        if not job.succeeded:
            raise RuntimeError(
                f"Maa resource bundle load failed for {resource_root}: "
                f"status={job.status}"
            )
    return Library.version()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path)
    args = parser.parse_args(argv)
    print(load_resource(args.candidate))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["load_resource", "main"]
