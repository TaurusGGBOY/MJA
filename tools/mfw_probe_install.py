"""Derive an isolated candidate containing only the MFW failure probe overlay."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from tools.mfw_artifact_verification import (
    _verify_runtime_candidate,
    hash_project_payload,
    sha256,
)
from tools.mfw_install import (
    ROOT,
    _new_metadata,
    _write_metadata,
    build_from_base,
    prepare_output,
)

PROBE_ROOT = ROOT / "tests/mfw/probes"
OVERLAY_FILES = (
    (Path("tasks/失败传播探针.json"), Path("tasks/失败传播探针.json")),
    (
        Path("resource/pipeline/failure_contract.json"),
        Path("resource/base/pipeline/failure_contract.json"),
    ),
)
PROBE_METADATA_NAME = "probe-metadata.json"


def _overlay_records(probe_root: Path = PROBE_ROOT) -> Iterable[tuple[str, bytes]]:
    for source_relative, _destination_relative in OVERLAY_FILES:
        source = Path(probe_root) / source_relative
        if not source.is_file():
            raise FileNotFoundError(source)
        yield source_relative.as_posix(), source.read_bytes()


def _overlay_hash(records: Iterable[tuple[str, bytes]]) -> str:
    digest = hashlib.sha256()
    for name, payload in sorted(records):
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(payload)
        digest.update(b"\0")
    return digest.hexdigest()


def _copy_overlay(output: Path, probe_root: Path) -> list[dict[str, str]]:
    records = list(_overlay_records(probe_root))
    copied: list[dict[str, str]] = []
    for (source_relative, destination_relative), (_name, payload) in zip(
        OVERLAY_FILES, records, strict=True
    ):
        source = Path(probe_root) / source_relative
        destination = Path(output) / destination_relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied.append(
            {
                "source": source_relative.as_posix(),
                "destination": destination_relative.as_posix(),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    return copied


def _append_probe_import(output: Path) -> None:
    interface_path = Path(output) / "interface.json"
    payload = json.loads(interface_path.read_text(encoding="utf-8"))
    imports = payload.setdefault("import", [])
    if not isinstance(imports, list):
        raise ValueError("candidate interface import must be a list")
    if "tasks/失败传播探针.json" not in imports:
        imports.append("tasks/失败传播探针.json")
    interface_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=4) + "\n", encoding="utf-8"
    )


def _write_probe_metadata(
    output: Path,
    base: Path,
    base_metadata: Any,
    copied: list[dict[str, str]],
    probe_root: Path,
) -> Path:
    records = list(_overlay_records(probe_root))
    payload = {
        "schema_version": 1,
        "base_metadata_sha256": sha256(Path(base) / "build-metadata.json"),
        "base_payload_sha256": base_metadata.payload_sha256,
        "overlay_sha256": _overlay_hash(records),
        "overlay": copied,
        "candidate_payload_sha256": hash_project_payload(output),
    }
    target = Path(output) / PROBE_METADATA_NAME
    temporary = target.with_name(target.name + ".part")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(target)
    return target


def install_probe(
    base_candidate: Path,
    output: Path,
    *,
    repo_root: Path = ROOT,
    probe_root: Path = PROBE_ROOT,
) -> Path:
    base = Path(base_candidate).resolve()
    destination = Path(output).resolve()
    source_root = Path(repo_root).resolve()
    if destination == source_root:
        raise ValueError("probe output cannot overwrite the production source tree")
    base_metadata = _verify_runtime_candidate(base)
    prepare_output(destination)
    build_from_base(source_root, base, destination, base_metadata.mja_commit)
    copied = _copy_overlay(destination, Path(probe_root))
    _append_probe_import(destination)
    metadata = _new_metadata(
        commit=base_metadata.mja_commit,
        mfw=base_metadata.mfw,
        maafw=base_metadata.maafw,
        output=destination,
        base_metadata_sha256=sha256(base / "build-metadata.json"),
    )
    _write_metadata(destination, metadata)
    _write_probe_metadata(destination, base, base_metadata, copied, Path(probe_root))
    return destination / PROBE_METADATA_NAME


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    metadata = install_probe(args.base, args.output)
    print(metadata)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["install_probe", "main"]
