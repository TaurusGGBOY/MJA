from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path

import pytest

from tools.mfw_install import (
    BuildMetadata,
    build_from_base,
    build_install,
    hash_project_payload,
    load_metadata,
    prepare_output,
    safe_extract,
    sha256,
    verify_candidate,
)
from tools.mfw_release import ReleaseAsset


def _write_zip(path: Path, files: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as bundle:
        for name, payload in files.items():
            bundle.writestr(name, payload)
    return path


def _assert_startup_payload(candidate: Path) -> None:
    startup = json.loads(
        (candidate / "resource/base/pipeline/startup/game_start.json").read_text(
            encoding="utf-8"
        )
    )
    shutdown = json.loads(
        (candidate / "resource/base/pipeline/startup/game_stop.json").read_text(
            encoding="utf-8"
        )
    )
    task_file = json.loads((candidate / "tasks/游戏启动.json").read_text(encoding="utf-8"))

    assert "启动-游戏启动" in startup
    assert "启动-游戏停止" not in startup
    assert not any(
        key.startswith("MJA_GAME_BACK_") or "UNKNOWN_ABORT" in key for key in startup
    )
    assert all(
        node.get("action") != "StopApp"
        for node in startup.values()
        if isinstance(node, dict)
    )
    assert shutdown["启动-游戏停止"] == {
        "action": "StopApp",
        "package": "com.hanjiasongshu.dr22",
    }
    assert not (candidate / "resource_android/pipeline/startup/game_start.json").exists()

    tasks = {task["name"]: task for task in task_file["task"]}
    assert tasks["GAME_START"]["entry"] == "启动-游戏入口"
    assert tasks["GAME_START"]["default"] is True
    assert tasks["GAME_STOP"]["entry"] == "启动-游戏停止"
    assert tasks["GAME_STOP"]["default"] is False


@pytest.fixture
def repo_fixture(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "assets/tasks").mkdir(parents=True)
    (root / "assets/resource/base/pipeline/startup").mkdir(parents=True)
    (root / "agent").mkdir()
    (root / "assets/interface.mfw.json").write_text(
        json.dumps(
            {
                "version": "0.1.0",
                "agent": {
                    "child_exec": "python3",
                    "child_args": ["{PROJECT_DIR}/agent/main.py"],
                    "embedded": False,
                },
                "resource": ["base"],
            }
        ),
        encoding="utf-8",
    )
    (root / "assets/tasks/游戏启动.json").write_text(
        json.dumps(
            {
                "task": [
                    {"name": "GAME_START", "entry": "启动-游戏入口", "default": True},
                    {"name": "GAME_STOP", "entry": "启动-游戏停止", "default": False},
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "assets/resource/base/pipeline/startup/game_start.json").write_text(
        json.dumps(
            {
                "启动-游戏入口": {"next": ["启动-游戏启动"]},
                "启动-游戏启动": {
                    "next": ["[JumpBack]启动-游戏就绪", "[JumpBack]MJA_GAME_LAUNCH"]
                },
                "启动-游戏就绪": {
                    "recognition": "TemplateMatch",
                    "template": "home/home_marker.png",
                    "action": "Custom",
                    "custom_action": "RuntimeHealth",
                },
                "MJA_GAME_LAUNCH": {
                    "action": "StartApp",
                    "package": "com.hanjiasongshu.dr22/.MainActivity",
                },
                "启动-空闲": {"action": "DoNothing"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "assets/resource/base/pipeline/startup/game_stop.json").write_text(
        '{"启动-游戏停止":{"action":"StopApp","package":"com.hanjiasongshu.dr22"}}\n',
        encoding="utf-8",
    )
    (root / "agent/main.py").write_text("print('agent')\n", encoding="utf-8")
    (root / "CFA_setting.json").write_text('{"embedded":true}\n', encoding="utf-8")
    (root / "requirements.txt").write_text("MaaFw\n", encoding="utf-8")
    return root


@pytest.fixture
def runtime_archives(tmp_path: Path) -> tuple[Path, Path, ReleaseAsset, ReleaseAsset]:
    mfw_archive = _write_zip(
        tmp_path / "mfw.zip",
        {
            "MFW": b"mfw-binary",
            "python/bin/python3": b"python",
            "config/default.json": b"{}",
        },
    )
    maa_archive = _write_zip(
        tmp_path / "maa.zip",
        {
            "bin/libMaaFramework.dylib": b"maa-runtime",
            "share/MaaAgentBinary/agent.bin": b"agent-runtime",
        },
    )
    return (
        mfw_archive,
        maa_archive,
        ReleaseAsset("mfw/repo", "v1", "MFW.zip", "https://example.test/MFW.zip"),
        ReleaseAsset("maa/repo", "v2", "MAA.zip", "https://example.test/MAA.zip"),
    )


@pytest.fixture
def current_runtime_archives(
    tmp_path: Path,
) -> tuple[Path, Path, ReleaseAsset, ReleaseAsset]:
    mfw_archive = _write_zip(
        tmp_path / "mfw-current.zip",
        {
            "MFW": b"mfw-binary",
            "MFWUpdater": b"mfw-updater",
            "_internal/Python": b"python-runtime",
            "_internal/maa/agent/agent_server.py": b"agent-server",
            "maafw/libMaaFramework.dylib": b"maa-bundled-runtime",
        },
    )
    maa_archive = _write_zip(
        tmp_path / "maa-current.zip",
        {
            "bin/libMaaFramework.dylib": b"maa-runtime",
            "share/MaaAgentBinary/agent.bin": b"agent-runtime",
        },
    )
    return (
        mfw_archive,
        maa_archive,
        ReleaseAsset("mfw/repo", "v-current", "MFW-current.zip", "https://example.test/MFW-current.zip"),
        ReleaseAsset("maa/repo", "v-current", "MAA-current.zip", "https://example.test/MAA-current.zip"),
    )


def test_prepare_output_rejects_nonempty_directory(tmp_path: Path) -> None:
    output = tmp_path / "candidate"
    output.mkdir()
    (output / "user.json").write_text("{}", encoding="utf-8")
    with pytest.raises(FileExistsError, match="not empty"):
        prepare_output(output)


def test_load_metadata_rejects_invalid_digest(tmp_path: Path) -> None:
    payload = {
        "mja_commit": "commit",
        "target": "macos-aarch64",
        "resolved_at": "now",
        "mfw": {"sha256": "0" * 64},
        "maafw": {"sha256": "0" * 64},
        "payload_sha256": "not-a-digest",
        "immutable_tree_sha256": "0" * 64,
    }
    (tmp_path / "build-metadata.json").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="payload_sha256"):
        load_metadata(tmp_path)


def test_safe_extract_rejects_parent_traversal(tmp_path: Path) -> None:
    archive = _write_zip(tmp_path / "bad.zip", {"../escape": b"x"})
    with pytest.raises(ValueError, match="unsafe zip member"):
        safe_extract(archive, tmp_path / "out")


def test_build_install_emits_maa_bbb_layout(
    repo_fixture: Path,
    runtime_archives: tuple[Path, Path, ReleaseAsset, ReleaseAsset],
    tmp_path: Path,
) -> None:
    mfw_archive, maa_archive, mfw_asset, maa_asset = runtime_archives
    output = tmp_path / "candidate"
    metadata = build_install(
        repo_fixture,
        output,
        mfw_asset,
        maa_asset,
        "deadbeef",
        mfw_archive=mfw_archive,
        maa_archive=maa_archive,
    )

    assert isinstance(metadata, BuildMetadata)
    assert metadata.target == "macos-aarch64"
    assert (output / "MFW").read_bytes() == b"mfw-binary"
    assert (output / "python/bin/python3").is_file()
    assert (output / "runtimes/osx-arm64/libMaaFramework.dylib").is_file()
    assert (output / "runtimes/osx-arm64/MaaAgentBinary/agent.bin").is_file()
    assert (output / "tasks/游戏启动.json").is_file()
    installed_interface = json.loads((output / "interface.json").read_text())
    assert installed_interface["agent"] == {
        "child_exec": "./python/bin/python3",
        "child_args": ["-u", "./agent/main.py"],
        "embedded": True,
    }
    assert json.loads((output / "build-metadata.json").read_text())["mja_commit"] == "deadbeef"
    _assert_startup_payload(output)
    assert verify_candidate(repo_fixture, output) == metadata


def test_generated_python_cache_does_not_break_candidate_integrity(
    repo_fixture: Path,
    runtime_archives: tuple[Path, Path, ReleaseAsset, ReleaseAsset],
    tmp_path: Path,
) -> None:
    mfw_archive, maa_archive, mfw_asset, maa_asset = runtime_archives
    output = tmp_path / "candidate"
    metadata = build_install(
        repo_fixture,
        output,
        mfw_asset,
        maa_asset,
        "cache-safe-commit",
        mfw_archive=mfw_archive,
        maa_archive=maa_archive,
    )
    cache = output / "python/lib/__pycache__/generated.cpython-312.pyc"
    cache.parent.mkdir(parents=True)
    cache.write_bytes(b"re-creatable cache")

    assert verify_candidate(repo_fixture, output) == metadata


def test_appledouble_metadata_does_not_break_candidate_integrity(
    repo_fixture: Path,
    runtime_archives: tuple[Path, Path, ReleaseAsset, ReleaseAsset],
    tmp_path: Path,
) -> None:
    mfw_archive, maa_archive, mfw_asset, maa_asset = runtime_archives
    output = tmp_path / "candidate"
    metadata = build_install(
        repo_fixture,
        output,
        mfw_asset,
        maa_asset,
        "appledouble-safe-commit",
        mfw_archive=mfw_archive,
        maa_archive=maa_archive,
    )
    (output / "._MFW").write_bytes(b"filesystem metadata")
    sidecar = output / "_internal/._libMaaFramework.dylib"
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_bytes(b"filesystem metadata")

    assert verify_candidate(repo_fixture, output) == metadata


def test_build_install_excludes_appledouble_metadata(
    repo_fixture: Path,
    runtime_archives: tuple[Path, Path, ReleaseAsset, ReleaseAsset],
    tmp_path: Path,
) -> None:
    mfw_archive, maa_archive, mfw_asset, maa_asset = runtime_archives
    resource_sidecar = repo_fixture / "assets/resource/base/pipeline/._sidecar.json"
    resource_sidecar.write_bytes(b"AppleDouble metadata")
    agent_sidecar = repo_fixture / "agent/._sidecar.py"
    agent_sidecar.write_bytes(b"AppleDouble metadata")

    output = tmp_path / "candidate"
    metadata = build_install(
        repo_fixture,
        output,
        mfw_asset,
        maa_asset,
        "appledouble-copy-safe-commit",
        mfw_archive=mfw_archive,
        maa_archive=maa_archive,
    )

    assert not (output / "resource/base/pipeline/._sidecar.json").exists()
    assert not (output / "agent/._sidecar.py").exists()
    assert verify_candidate(repo_fixture, output) == metadata


def test_build_install_accepts_current_mfw_pyinstaller_layout(
    repo_fixture: Path,
    current_runtime_archives: tuple[Path, Path, ReleaseAsset, ReleaseAsset],
    tmp_path: Path,
) -> None:
    mfw_archive, maa_archive, mfw_asset, maa_asset = current_runtime_archives
    output = tmp_path / "current-candidate"
    metadata = build_install(
        repo_fixture,
        output,
        mfw_asset,
        maa_asset,
        "current-commit",
        mfw_archive=mfw_archive,
        maa_archive=maa_archive,
    )

    assert (output / "MFW").is_file()
    assert os.access(output / "MFW", os.X_OK)
    assert (output / "_internal/Python").is_file()
    assert not (output / "python/bin/python3").exists()
    assert (output / "maafw/libMaaFramework.dylib").is_file()
    installed_interface = json.loads((output / "interface.json").read_text())
    assert installed_interface["agent"] == {
        "child_exec": "python3",
        "child_args": ["{PROJECT_DIR}/agent/main.py"],
        "embedded": True,
    }
    assert verify_candidate(repo_fixture, output) == metadata


def test_embedded_mfw_decorator_rewrite_does_not_break_payload_verification(
    repo_fixture: Path,
    runtime_archives: tuple[Path, Path, ReleaseAsset, ReleaseAsset],
    tmp_path: Path,
) -> None:
    action = repo_fixture / "agent/custom/action/embedded_probe.py"
    action.parent.mkdir(parents=True)
    action.write_text(
        "from maa.agent.agent_server import AgentServer\n"
        "from maa.custom_action import CustomAction\n\n"
        "@AgentServer.custom_action(\"EmbeddedProbe\")\n"
        "class EmbeddedProbe(CustomAction):\n"
        "    pass\n",
        encoding="utf-8",
    )
    mfw_archive, maa_archive, mfw_asset, maa_asset = runtime_archives
    candidate = tmp_path / "candidate"
    metadata = build_install(
        repo_fixture,
        candidate,
        mfw_asset,
        maa_asset,
        "embedded-rewrite-commit",
        mfw_archive=mfw_archive,
        maa_archive=maa_archive,
    )

    installed = candidate / "agent/custom/action/embedded_probe.py"
    installed.write_text(
        installed.read_text(encoding="utf-8")
        .replace(
            "from maa.agent.agent_server import AgentServer",
            "from maa.resource import resource",
        )
        .replace("@AgentServer.custom_action(", "@resource.custom_action("),
        encoding="utf-8",
    )

    assert hash_project_payload(repo_fixture) == hash_project_payload(candidate)
    assert verify_candidate(repo_fixture, candidate) == metadata


def test_embedded_mfw_custom_recognition_rewrite_does_not_break_payload_verification(
    repo_fixture: Path,
    runtime_archives: tuple[Path, Path, ReleaseAsset, ReleaseAsset],
    tmp_path: Path,
) -> None:
    recognition = repo_fixture / "agent/custom/recognition/embedded_probe.py"
    recognition.parent.mkdir(parents=True)
    recognition.write_text(
        "from maa.agent.agent_server import AgentServer\n"
        "from maa.custom_recognition import CustomRecognition\n\n"
        "@AgentServer.custom_recognition(\"EmbeddedProbe\")\n"
        "class EmbeddedProbe(CustomRecognition):\n"
        "    pass\n",
        encoding="utf-8",
    )
    mfw_archive, maa_archive, mfw_asset, maa_asset = runtime_archives
    candidate = tmp_path / "candidate"
    metadata = build_install(
        repo_fixture,
        candidate,
        mfw_asset,
        maa_asset,
        "embedded-recognition-rewrite-commit",
        mfw_archive=mfw_archive,
        maa_archive=maa_archive,
    )

    installed = candidate / "agent/custom/recognition/embedded_probe.py"
    installed.write_text(
        installed.read_text(encoding="utf-8")
        .replace(
            "from maa.agent.agent_server import AgentServer",
            "from maa.resource import resource",
        )
        .replace(
            "@AgentServer.custom_recognition(",
            "@resource.custom_recognition(",
        ),
        encoding="utf-8",
    )

    assert hash_project_payload(repo_fixture) == hash_project_payload(candidate)
    assert verify_candidate(repo_fixture, candidate) == metadata


def test_embedded_mfw_tasker_sink_rewrite_does_not_break_payload_verification(
    repo_fixture: Path,
    runtime_archives: tuple[Path, Path, ReleaseAsset, ReleaseAsset],
    tmp_path: Path,
) -> None:
    sink = repo_fixture / "agent/custom/sink/embedded_probe.py"
    sink.parent.mkdir(parents=True)
    sink.write_text(
        "from maa.agent.agent_server import AgentServer\n"
        "from maa.tasker import TaskerEventSink\n\n"
        "@AgentServer.tasker_sink()\n"
        "class EmbeddedSink(TaskerEventSink):\n"
        "    pass\n",
        encoding="utf-8",
    )
    mfw_archive, maa_archive, mfw_asset, maa_asset = runtime_archives
    candidate = tmp_path / "candidate"
    metadata = build_install(
        repo_fixture,
        candidate,
        mfw_asset,
        maa_asset,
        "embedded-sink-rewrite-commit",
        mfw_archive=mfw_archive,
        maa_archive=maa_archive,
    )

    installed = candidate / "agent/custom/sink/embedded_probe.py"
    installed.write_text(
        installed.read_text(encoding="utf-8")
        .replace(
            "from maa.agent.agent_server import AgentServer\n",
            "",
        )
        .replace("@AgentServer.tasker_sink()\n", ""),
        encoding="utf-8",
    )

    assert hash_project_payload(repo_fixture) == hash_project_payload(candidate)
    assert verify_candidate(repo_fixture, candidate) == metadata


def test_derived_candidate_preserves_runtime_and_replaces_project_payload(
    repo_fixture: Path,
    runtime_archives: tuple[Path, Path, ReleaseAsset, ReleaseAsset],
    tmp_path: Path,
) -> None:
    mfw_archive, maa_archive, mfw_asset, maa_asset = runtime_archives
    base = tmp_path / "base"
    build_install(
        repo_fixture,
        base,
        mfw_asset,
        maa_asset,
        "base-commit",
        mfw_archive=mfw_archive,
        maa_archive=maa_archive,
    )
    (base / "config/configs").mkdir(parents=True)
    (base / "config/configs/user.json").write_text("profile", encoding="utf-8")
    (base / "config/configs/c_controller.json").write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "name": "Controller",
                        "task_option": {
                            "controller_type": "android",
                            "android": {"adb_path": "/old/checkout/adb"},
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    changed = repo_fixture / "assets/tasks/游戏启动.json"
    changed.write_text('{"task":[{"name":"GAME_START_CHANGED"}]}\n', encoding="utf-8")

    derived = tmp_path / "derived"
    metadata = build_from_base(repo_fixture, base, derived, "derived-commit")

    assert (derived / "MFW").read_bytes() == (base / "MFW").read_bytes()
    assert (derived / "tasks/游戏启动.json").read_bytes() == changed.read_bytes()
    assert (derived / "config/configs/user.json").read_text(encoding="utf-8") == "profile"
    controller = json.loads(
        (derived / "config/configs/c_controller.json").read_text(encoding="utf-8")
    )
    assert controller["tasks"][0]["task_option"]["android"]["adb_path"] == str(
        (repo_fixture / "install/android-sdk/platform-tools/adb").resolve()
    )
    assert metadata.mfw == load_metadata(base).mfw
    assert metadata.maafw == load_metadata(base).maafw
    assert metadata.base_metadata_sha256 == sha256(base / "build-metadata.json")
    assert metadata.payload_sha256 == hash_project_payload(derived)
    assert verify_candidate(repo_fixture, derived) == metadata


def test_verify_candidate_rejects_payload_and_runtime_tampering(
    repo_fixture: Path,
    runtime_archives: tuple[Path, Path, ReleaseAsset, ReleaseAsset],
    tmp_path: Path,
) -> None:
    mfw_archive, maa_archive, mfw_asset, maa_asset = runtime_archives
    candidate = tmp_path / "candidate"
    build_install(
        repo_fixture,
        candidate,
        mfw_asset,
        maa_asset,
        "commit",
        mfw_archive=mfw_archive,
        maa_archive=maa_archive,
    )

    (candidate / "agent/main.py").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(ValueError, match="payload"):
        verify_candidate(repo_fixture, candidate)

    (candidate / "agent/main.py").write_text("print('agent')\n", encoding="utf-8")
    (candidate / "MFW").write_bytes(b"tampered-runtime")
    with pytest.raises(ValueError, match="immutable"):
        verify_candidate(repo_fixture, candidate)


def test_runtime_debug_logs_do_not_break_candidate_integrity(
    repo_fixture: Path,
    runtime_archives: tuple[Path, Path, ReleaseAsset, ReleaseAsset],
    tmp_path: Path,
) -> None:
    mfw_archive, maa_archive, mfw_asset, maa_asset = runtime_archives
    candidate = tmp_path / "candidate"
    build_install(
        repo_fixture,
        candidate,
        mfw_asset,
        maa_asset,
        "commit",
        mfw_archive=mfw_archive,
        maa_archive=maa_archive,
    )

    (candidate / "debug").mkdir()
    (candidate / "debug/gui.log").write_text("runtime log\n", encoding="utf-8")
    (candidate / "debug/maafw.log").write_text("runtime log\n", encoding="utf-8")

    verify_candidate(repo_fixture, candidate)


def test_runtime_python_caches_do_not_break_payload_integrity(
    repo_fixture: Path,
    runtime_archives: tuple[Path, Path, ReleaseAsset, ReleaseAsset],
    tmp_path: Path,
) -> None:
    mfw_archive, maa_archive, mfw_asset, maa_asset = runtime_archives
    candidate = tmp_path / "candidate"
    build_install(
        repo_fixture,
        candidate,
        mfw_asset,
        maa_asset,
        "commit",
        mfw_archive=mfw_archive,
        maa_archive=maa_archive,
    )

    cache = candidate / "agent/workflows/__pycache__"
    cache.mkdir(parents=True)
    (cache / "runtime.cpython-314.pyc").write_bytes(b"re-creatable cache")

    verify_candidate(repo_fixture, candidate)


def test_verify_candidate_rejects_probe_files(
    repo_fixture: Path,
    runtime_archives: tuple[Path, Path, ReleaseAsset, ReleaseAsset],
    tmp_path: Path,
) -> None:
    mfw_archive, maa_archive, mfw_asset, maa_asset = runtime_archives
    candidate = tmp_path / "candidate"
    build_install(
        repo_fixture,
        candidate,
        mfw_asset,
        maa_asset,
        "commit",
        mfw_archive=mfw_archive,
        maa_archive=maa_archive,
    )
    (candidate / "tasks/MJA_PROBE_bad.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="probe"):
        verify_candidate(repo_fixture, candidate)
