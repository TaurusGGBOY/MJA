"""Patch and verify the packaged MFW-PyQt6 batch-failure return contract.

The production MFW executable is a PyInstaller archive containing Python 3.12
bytecode.  This module intentionally uses only the standard library so the
candidate installer can run it offline.  The actual archive operation must run
under Python 3.12; the installer launches this file with that interpreter when
the current process uses another Python version.
"""

from __future__ import annotations

import argparse
import dis
import json
import marshal
import os
import shutil
import struct
import subprocess
import sys
import types
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CARCHIVE_COOKIE_MAGIC = b"MEI\x0c\x0b\x0a\x0b\x0e"
CARCHIVE_COOKIE_FORMAT = "!8sIIii64s"
CARCHIVE_COOKIE_SIZE = struct.calcsize(CARCHIVE_COOKIE_FORMAT)
CARCHIVE_ENTRY_FORMAT = "!iIIIBc"
CARCHIVE_ENTRY_SIZE = struct.calcsize(CARCHIVE_ENTRY_FORMAT)
PYZ_MAGIC = b"PYZ\x00"
TARGET_MODULE = "app.core.runner.task_flow"


@dataclass(frozen=True)
class PatchResult:
    status: str
    changed: bool
    verified: bool
    detail: str


@dataclass(frozen=True)
class _CArchive:
    overlay_pos: int
    cookie_pos: int
    toc_pos: int
    toc_length: int


def _find_carchive(data: bytes) -> _CArchive | None:
    cookie_pos = data.rfind(CARCHIVE_COOKIE_MAGIC)
    if cookie_pos < 0:
        return None
    cookie_end = cookie_pos + CARCHIVE_COOKIE_SIZE
    if cookie_end > len(data):
        raise ValueError("truncated PyInstaller CArchive cookie")
    magic, archive_length, toc_pos, toc_length, _pyver, _pylib = struct.unpack(
        CARCHIVE_COOKIE_FORMAT, data[cookie_pos:cookie_end]
    )
    if magic != CARCHIVE_COOKIE_MAGIC:
        raise ValueError("invalid PyInstaller CArchive magic")
    if archive_length <= 0 or archive_length > cookie_end:
        raise ValueError("invalid PyInstaller CArchive length")
    overlay_pos = cookie_end - archive_length
    absolute_toc_pos = overlay_pos + toc_pos
    if (
        overlay_pos < 0
        or toc_length <= 0
        or absolute_toc_pos < overlay_pos
        or absolute_toc_pos + toc_length != cookie_pos
    ):
        raise ValueError("invalid PyInstaller CArchive table of contents")
    return _CArchive(overlay_pos, cookie_pos, absolute_toc_pos, toc_length)


def is_pyinstaller_executable(path: Path) -> bool:
    """Return whether *path* contains a recognizable PyInstaller archive."""

    return _find_carchive(Path(path).read_bytes()) is not None


def _carchive_entries(
    data: bytes, archive: _CArchive
) -> list[tuple[str, int, int, int, int, bytes]]:
    table = data[archive.toc_pos : archive.cookie_pos]
    entries: list[tuple[str, int, int, int, int, bytes]] = []
    offset = 0
    while offset < len(table):
        if offset + 4 > len(table):
            raise ValueError("truncated PyInstaller CArchive table entry")
        entry_size = struct.unpack("!i", table[offset : offset + 4])[0]
        if entry_size < CARCHIVE_ENTRY_SIZE or offset + entry_size > len(table):
            raise ValueError("invalid PyInstaller CArchive table entry size")
        _size, entry_pos, compressed_size, uncompressed_size, flag, typecode = struct.unpack(
            CARCHIVE_ENTRY_FORMAT,
            table[offset : offset + CARCHIVE_ENTRY_SIZE],
        )
        raw_name = table[offset + CARCHIVE_ENTRY_SIZE : offset + entry_size]
        name = raw_name.split(b"\0", 1)[0].decode("utf-8")
        entries.append(
            (name, entry_pos, compressed_size, uncompressed_size, flag, typecode)
        )
        offset += entry_size
    if offset != len(table):
        raise ValueError("PyInstaller CArchive table is not aligned")
    return entries


def _find_pyz(data: bytes, archive: _CArchive) -> bytes:
    for name, entry_pos, compressed_size, uncompressed_size, flag, typecode in _carchive_entries(
        data, archive
    ):
        if name != "PYZ.pyz":
            continue
        if flag != 0 or typecode != b"z":
            raise ValueError("unsupported compressed PYZ.pyz CArchive entry")
        start = archive.overlay_pos + entry_pos
        end = start + compressed_size
        if end > archive.toc_pos:
            raise ValueError("PYZ.pyz entry extends beyond the CArchive overlay")
        payload = data[start:end]
        if len(payload) != uncompressed_size:
            raise ValueError("unexpected compressed PYZ.pyz entry")
        return payload
    raise ValueError("PyInstaller archive does not contain PYZ.pyz")


def _rewrite_code(module: types.CodeType) -> tuple[types.CodeType, bool]:
    constants = list(module.co_consts)
    changed = False
    for index, constant in enumerate(constants):
        if isinstance(constant, types.CodeType):
            rewritten, nested_changed = _rewrite_code(constant)
            if nested_changed:
                constants[index] = rewritten
                changed = True

    if module.co_name == "run_task" and "_stop_task_timeout" in module.co_names:
        instructions = list(dis.get_instructions(module))
        for index, instruction in enumerate(instructions[:-2]):
            next_instruction = instructions[index + 1]
            after_next = instructions[index + 2]
            if not (
                instruction.opname == "RETURN_CONST"
                and instruction.argval in (None, False)
                and next_instruction.opname == "LOAD_DEREF"
                and next_instruction.argval == "self"
                and after_next.opname == "LOAD_ATTR"
                and after_next.argval == "_stop_task_timeout"
            ):
                continue
            if instruction.argval is False:
                return module.replace(co_consts=tuple(constants)) if changed else module, changed
            try:
                false_index = next(index for index, value in enumerate(constants) if value is False)
            except StopIteration:
                constants.append(False)
                false_index = len(constants) - 1
            if false_index > 255:
                raise ValueError("patched False constant does not fit RETURN_CONST")
            code = bytearray(module.co_code)
            code[instruction.offset + 1] = false_index
            rewritten = module.replace(co_code=bytes(code), co_consts=tuple(constants))
            return rewritten, True

    if changed:
        return module.replace(co_consts=tuple(constants)), True
    return module, False


def _patch_pyz(pyz: bytes) -> tuple[bytes, bool]:
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError(
            "the packaged MFW-PyQt6 bytecode must be patched with Python 3.12"
        )
    if not pyz.startswith(PYZ_MAGIC) or len(pyz) < 12:
        raise ValueError("invalid PYZ.pyz header")
    toc_pos = struct.unpack("!i", pyz[8:12])[0]
    if toc_pos < 12 or toc_pos >= len(pyz):
        raise ValueError("invalid PYZ.pyz table offset")
    toc = marshal.loads(pyz[toc_pos:])
    if not isinstance(toc, list):
        raise ValueError("unsupported PYZ.pyz table format")
    target_index = next(
        (index for index, entry in enumerate(toc) if entry[0] == TARGET_MODULE),
        None,
    )
    if target_index is None:
        raise ValueError(f"PYZ.pyz is missing {TARGET_MODULE}")
    original_entry = toc[target_index]
    _ispkg, code_pos, old_compressed_size = original_entry[1]
    code_end = code_pos + old_compressed_size
    if code_pos < 12 or code_end > toc_pos:
        raise ValueError("invalid target module range in PYZ.pyz")
    old_compressed = pyz[code_pos:code_end]
    module = marshal.loads(zlib.decompress(old_compressed))
    rewritten, changed = _rewrite_code(module)
    if not changed:
        return pyz, False
    new_raw = marshal.dumps(rewritten)
    compressed_options = [zlib.compress(new_raw, level) for level in (9, 6, 1)]
    new_compressed = min(compressed_options, key=len)
    if len(new_compressed) > old_compressed_size:
        raise ValueError("patched PYZ module no longer fits its archive slot")
    toc_copy = list(toc)
    original_entry = toc_copy[target_index]
    toc_copy[target_index] = (
        original_entry[0],
        (original_entry[1][0], original_entry[1][1], len(new_compressed)),
    )
    new_toc = marshal.dumps(toc_copy)
    if len(new_toc) > len(pyz) - toc_pos:
        raise ValueError("patched PYZ table no longer fits its archive slot")
    result = bytearray(pyz)
    result[code_pos:code_end] = new_compressed + b"\0" * (
        old_compressed_size - len(new_compressed)
    )
    result[toc_pos:] = new_toc + b"\0" * (len(pyz) - toc_pos - len(new_toc))
    return bytes(result), True


def _patched_return_is_false(pyz: bytes) -> bool:
    if not pyz.startswith(PYZ_MAGIC) or len(pyz) < 12:
        raise ValueError("invalid PYZ.pyz header")
    toc_pos = struct.unpack("!i", pyz[8:12])[0]
    toc = marshal.loads(pyz[toc_pos:])
    _ispkg, code_pos, compressed_size = next(
        entry[1] for entry in toc if entry[0] == TARGET_MODULE
    )
    module = marshal.loads(zlib.decompress(pyz[code_pos : code_pos + compressed_size]))

    def walk(code: types.CodeType) -> bool:
        if code.co_name == "run_task" and "_stop_task_timeout" in code.co_names:
            instructions = list(dis.get_instructions(code))
            for index, instruction in enumerate(instructions[:-2]):
                if (
                    instruction.opname == "RETURN_CONST"
                    and instruction.argval is False
                    and instructions[index + 1].opname == "LOAD_DEREF"
                    and instructions[index + 1].argval == "self"
                    and instructions[index + 2].opname == "LOAD_ATTR"
                    and instructions[index + 2].argval == "_stop_task_timeout"
                ):
                    return True
        return any(
            isinstance(constant, types.CodeType) and walk(constant)
            for constant in code.co_consts
        )

    return walk(module)


def verify_mfw_executable(path: Path) -> bool:
    """Verify the packaged failure-return patch in a Python 3.12 process."""

    if sys.version_info[:2] != (3, 12):
        raise RuntimeError("MFW-PyQt6 bytecode verification requires Python 3.12")
    data = Path(path).read_bytes()
    archive = _find_carchive(data)
    if archive is None:
        return False
    return _patched_return_is_false(_find_pyz(data, archive))


def _codesign_identifier(path: Path) -> str | None:
    if sys.platform != "darwin":
        return None
    codesign = shutil.which("codesign")
    if codesign is None:
        return None
    completed = subprocess.run(
        [codesign, "-dv", "--verbose=4", str(path)],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    for line in completed.stderr.splitlines():
        if line.startswith("Identifier="):
            return line.partition("=")[2]
    return None


def patch_mfw_executable(path: Path) -> PatchResult:
    """Patch one MFW executable, preserving its archive size and re-signing it."""

    if sys.version_info[:2] != (3, 12):
        raise RuntimeError("MFW-PyQt6 bytecode patching requires Python 3.12")
    target = Path(path)
    original = target.read_bytes()
    archive = _find_carchive(original)
    if archive is None:
        return PatchResult("skipped", False, False, "not a PyInstaller executable")
    pyz = _find_pyz(original, archive)
    patched_pyz, changed = _patch_pyz(pyz)
    if not changed:
        return PatchResult("already_patched", False, True, "failure return is already False")
    identifier = _codesign_identifier(target)
    start = archive.overlay_pos + next(
        entry[1]
        for entry in _carchive_entries(original, archive)
        if entry[0] == "PYZ.pyz"
    )
    result = bytearray(original)
    result[start : start + len(pyz)] = patched_pyz
    temporary = target.with_name(f".{target.name}.mja-patch-{os.getpid()}")
    try:
        temporary.write_bytes(result)
        shutil.copymode(target, temporary)
        if sys.platform == "darwin":
            codesign = shutil.which("codesign")
            if codesign is None:
                raise RuntimeError("codesign is required to patch a macOS MFW executable")
            sign_command = [codesign, "--force", "--sign", "-"]
            if identifier:
                sign_command.extend(["--identifier", identifier])
            sign_command.append(str(temporary))
            subprocess.run(
                sign_command,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        verified = verify_mfw_executable(temporary)
        if not verified:
            raise ValueError("patched MFW executable failed bytecode verification")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return PatchResult("patched", True, True, "failure return changed to False")


def _python312() -> str:
    if sys.version_info[:2] == (3, 12):
        return sys.executable
    configured = os.environ.get("MJA_PYTHON312")
    if configured and Path(configured).is_file():
        return configured
    executable = shutil.which("python3.12")
    if executable:
        return executable
    uv = shutil.which("uv")
    if uv:
        try:
            found = subprocess.check_output(
                [uv, "python", "find", "3.12"], text=True, stderr=subprocess.DEVNULL
            ).strip()
        except (OSError, subprocess.CalledProcessError):
            found = ""
        if found and Path(found).is_file():
            return found
    roots = (
        Path.home() / ".local/share/uv/python",
        Path.home() / "Library/Application Support/uv/python",
    )
    for root in roots:
        candidates = sorted(root.glob("cpython-3.12*/bin/python3.12"))
        if candidates:
            return str(candidates[-1])
    raise RuntimeError("Python 3.12 is required to patch the packaged MFW runtime")


def apply_mfw_pyqt6_runtime_patch(path: Path) -> PatchResult:
    """Apply the patch through Python 3.12, or skip non-PyInstaller test runtimes."""

    target = Path(path)
    if not is_pyinstaller_executable(target):
        return PatchResult("skipped", False, False, "not a PyInstaller executable")
    interpreter = _python312()
    completed = subprocess.run(
        [interpreter, str(Path(__file__).resolve()), "--patch", str(target)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        payload: Any = json.loads(completed.stdout.strip().splitlines()[-1])
        return PatchResult(**payload)
    except (IndexError, json.JSONDecodeError, TypeError) as exc:
        raise RuntimeError("MFW-PyQt6 patcher returned invalid status") from exc


def verify_mfw_pyqt6_runtime_patch(path: Path) -> bool:
    """Verify a candidate runtime, skipping intentionally fake test binaries."""

    target = Path(path)
    if not is_pyinstaller_executable(target):
        return True
    interpreter = _python312()
    completed = subprocess.run(
        [interpreter, str(Path(__file__).resolve()), "--verify", str(target)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    payload: Any = json.loads(completed.stdout.strip().splitlines()[-1])
    return bool(payload["verified"])


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--patch", type=Path)
    group.add_argument("--verify", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.patch is not None:
        result = patch_mfw_executable(args.patch)
        print(json.dumps(result.__dict__, ensure_ascii=False))
        return 0
    verified = verify_mfw_executable(args.verify)
    print(json.dumps({"verified": verified}, ensure_ascii=False))
    return 0 if verified else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "PatchResult",
    "apply_mfw_pyqt6_runtime_patch",
    "is_pyinstaller_executable",
    "main",
    "patch_mfw_executable",
    "verify_mfw_executable",
    "verify_mfw_pyqt6_runtime_patch",
]
