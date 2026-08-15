# MJA MFW 基座 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **2026-08-05 target correction (authoritative):** 本基座面向本机 macOS 上运行的 iOS 版本游戏，统一使用 `MacOS` Controller、`ScreenCaptureKit` 和 `GlobalEvent`。游戏必须预先打开；MacOS Controller 不支持 `StartApp`。早先 Android/ADB 文字属于历史方案，不得据此修改当前 MFW interface 或资源。

**Goal:** 建成可独立安装、加载和验收的 Maa_bbb 同构 MFW 基座，为 17 个独立任务提供稳定的 interface、资源、启动恢复、窄 Agent、安全诊断和失败传播契约。

**Architecture:** 新架构在 `assets/interface.mfw.json`、`assets/resource/base/`、`agent/custom/` 和 `tools/mfw_install.py` 中并行建设，不触碰旧正式入口。安装器一次解析并锁定最新 MFW/MaaFramework 正式版，窄 Agent 只操作当前 Maa Controller，公共 Pipeline 负责游戏启动、已知弹窗和回主页。

**Tech Stack:** Python 3.12–3.14、MFW PyQt6、MaaFramework AgentServer、ProjectInterface v2、Maa Pipeline JSON、pytest、Ruff、GitHub Actions

## Global Constraints

- 第一阶段只声明 macOS `MacOS` Controller 和 `resource/base`；当前 iOS App 使用 WindowServer 窗口标题匹配，不走 PlayCover/MaaTools，也不使用 Android `Adb` Controller。
- `assets/interface.json` 与旧生产入口在本计划中保持不变；新入口只写 `assets/interface.mfw.json`。
- MFW 与 MaaFramework 每次构建各解析一次最新正式 release，资产必须唯一匹配 macOS arm64，禁止静默回退。
- 安装输出目录必须是不存在或为空的隔离目录；禁止覆盖现有安装和用户配置。
- 所有下载资产计算 SHA-256，且 `build-metadata.json` 是本次构建后续自动化、实机和发布的唯一版本依据。
- Agent 必须兼容 Python `>=3.12,<3.15`；Ruff 最低目标为 `py312`。
- Agent 不拥有任务队列、页面导航或设备生命周期；所有输入只通过 `context.tasker.controller`。
- 当前 `agent/safety.py` 的兼容放行行为不能迁移；新 `GuardedInput` 必须真实拒绝越权动作。
- 正常终态是 `success`、`already_complete`、`not_eligible`；业务失败显式 `Abort`；基础设施失败保留给 Maa/MFW 并停止队列。
- 公共 Pipeline 禁止包含业务任务列表，禁止使用 `speedrun`、无限循环和无条件重放副作用动作。
- 不自动处理登录凭据、验证码、实名、支付和未知弹窗。
- 现有未跟踪 `uv.lock` 不修改、不暂存、不提交。

---

## 文件结构与职责

| 文件 | 职责 |
| --- | --- |
| `tools/mfw_release.py` | 查询 GitHub 最新正式 release、唯一选择 macOS arm64 资产、下载并计算 SHA-256 |
| `tools/mfw_install.py` | 在隔离目录组装 MFW、Maa runtime、interface、tasks、resource、Agent 和构建元数据 |
| `tools/check_mfw_resources.py` | 加载并静态验证 Maa Pipeline 引用、Abort 收敛和禁止符号 |
| `tools/mfw_profile.py` | 按 MFW 保存的配置显示名唯一解析 config ID，并用布尔 `--direct-run` 启动 |
| `assets/interface.mfw.json` | 迁移期间的 ProjectInterface v2 唯一新架构入口 |
| `assets/tasks/游戏启动.json` | MFW 可见的统一启动任务声明 |
| `assets/resource/base/pipeline/common/*.json` | 公共成功、Abort、回主页和已知弹窗节点 |
| `assets/resource/base/pipeline/startup/game_start.json` | 启动、等待和主页后置条件 |
| `agent/custom/support/models.py` | 终态、动作/任务政策和值对象 |
| `agent/custom/support/policy.py` | 17 个任务现有动作上限与资源白名单的不可变映射 |
| `agent/custom/support/state.py` | 单任务动作计数和终态内存状态，不参与排队 |
| `agent/custom/support/diagnostics.py` | `debug/runs/{run-id}/{TASK_ID}/` 结构化证据写入 |
| `agent/custom/support/controller_input.py` | 当前 Maa Controller 的 click/swipe 薄封装 |
| `agent/custom/support/params.py` | CustomAction JSON 参数解析与类型校验 |
| `agent/custom/action/task_lifecycle.py` | `BeginTask`、`RecordTaskOutcome` |
| `agent/custom/action/guarded_input.py` | `GuardedInput` 的同帧页面/目标/预算授权 |
| `agent/custom/action/runtime_health.py` | `RuntimeHealth` 的当前 Tasker 只读检查 |
| `agent/main.py` | 从 MFW socket 启动 AgentServer 并导入窄能力注册模块 |
| `tests/mfw/fakes.py` | 无真实输入的 Maa Context/Controller/Tasker 测试替身 |

### Task 1: 固定 Python 3.12 契约与测试替身

**Files:**
- Modify: `pyproject.toml`
- Create: `requirements.txt`
- Create: `tests/mfw/__init__.py`
- Create: `tests/mfw/fakes.py`
- Create: `tests/test_mfw_python_contract.py`

**Interfaces:**
- Consumes: 当前 pytest 配置和 Maa CustomAction 的 `context.tasker.controller` 访问模式。
- Produces: `FakeController`, `FakeTasker`, `FakeContext`, `FakeArgv`；项目 Python 范围 `>=3.12,<3.15`。

- [ ] **Step 1: 写 Python 与测试替身契约测试**

```python
from pathlib import Path
import tomllib

from tests.mfw.fakes import FakeContext


def test_python_floor_and_ruff_target_are_312():
    data = tomllib.loads(Path("pyproject.toml").read_text())
    assert data["project"]["requires-python"] == ">=3.12,<3.15"
    assert data["tool"]["ruff"]["target-version"] == "py312"


def test_fake_context_exposes_only_current_controller():
    context = FakeContext()
    assert context.tasker.controller is context.controller
    assert not hasattr(context, "controller_env")
```

- [ ] **Step 2: 运行测试确认先失败**

Run: `uv run --no-project --with pytest pytest tests/test_mfw_python_contract.py -q`

Expected: FAIL，因为 `tests.mfw.fakes` 尚不存在，Python 版本仍为 3.14。

- [ ] **Step 3: 实现最小测试替身和版本声明**

```python
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any


@dataclass
class FakeController:
    connected: bool = True
    actions: list[tuple[str, Any]] = field(default_factory=list)

    def post_click(self, x: int, y: int):
        self.actions.append(("click", (x, y)))
        return SimpleNamespace(wait=lambda: True)

    def post_swipe(self, x1: int, y1: int, x2: int, y2: int, duration: int):
        self.actions.append(("swipe", (x1, y1, x2, y2, duration)))
        return SimpleNamespace(wait=lambda: True)


class FailingController(FakeController):
    def __init__(self, error: Exception):
        super().__init__()
        self.error = error

    def post_click(self, x: int, y: int):
        raise self.error


@dataclass
class FakeTasker:
    controller: FakeController


class FakeContext:
    def __init__(self, controller: FakeController | None = None):
        self.controller = controller or FakeController()
        self.tasker = FakeTasker(self.controller)


@dataclass
class FakeArgv:
    custom_action_param: str
    node_name: str = "MJA_TEST_AND_NODE"
    box: tuple[int, int, int, int] = (100, 200, 40, 20)
    reco_detail: Any = None


def and_reco(*sub_results: Any) -> Any:
    return SimpleNamespace(
        hit=True,
        algorithm="And",
        best_result=SimpleNamespace(sub_results=list(sub_results)),
    )


def hit_reco(name: str) -> Any:
    return SimpleNamespace(name=name, hit=True, filtered_results=[])


def miss_reco(name: str) -> Any:
    return SimpleNamespace(name=name, hit=False, filtered_results=[])
```

Modify `pyproject.toml` to `requires-python = ">=3.12,<3.15"` and `target-version = "py312"`. Create `requirements.txt` with exactly one runtime dependency line, `MaaFw`, matching Maa_bbb's embedded Agent package; pytest and Ruff stay CI/development-only and are installed explicitly by test commands.

- [ ] **Step 4: 运行契约和旧测试**

Run: `uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/test_mfw_python_contract.py -q && uv run --no-project --with ruff ruff check tests/mfw tests/test_mfw_python_contract.py`

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add pyproject.toml requirements.txt tests/mfw tests/test_mfw_python_contract.py
git commit -m "build: support embedded Agent on Python 3.12"
```

### Task 2: 解析并确定最新正式 release

**Files:**
- Create: `tools/mfw_release.py`
- Create: `tests/test_mfw_release.py`

**Interfaces:**
- Consumes: GitHub REST `GET /repos/{owner}/{repo}/releases/latest`。
- Produces: `ReleaseAsset(repo: str, tag: str, name: str, url: str)`；`resolve_latest_asset(repo, pattern, opener) -> ReleaseAsset`；`download_asset(asset, target, opener) -> str` 返回 SHA-256。

- [ ] **Step 1: 写资产唯一性和校验测试**

```python
import hashlib
from pathlib import Path

import pytest

from tools.mfw_release import ReleaseAsset, resolve_asset, write_download


RELEASE = {
    "tag_name": "v4.8.23",
    "prerelease": False,
    "draft": False,
    "assets": [
        {"name": "MFW-PyQt6-macos-aarch64-v4.8.23.zip", "browser_download_url": "https://example/mfw.zip"},
        {"name": "MFW-PyQt6-windows-x86_64-v4.8.23.zip", "browser_download_url": "https://example/win.zip"},
    ],
}


def test_resolve_asset_requires_one_formal_macos_arm64_match():
    asset = resolve_asset("overflow65537/MFW-PyQt6", RELEASE, r"^MFW.*macos-aarch64.*\\.zip$")
    assert asset == ReleaseAsset("overflow65537/MFW-PyQt6", "v4.8.23", RELEASE["assets"][0]["name"], "https://example/mfw.zip")


def test_resolve_asset_rejects_zero_or_multiple_matches():
    with pytest.raises(ValueError, match="exactly one"):
        resolve_asset("repo", {**RELEASE, "assets": []}, r"macos-aarch64")


def test_write_download_returns_sha256(tmp_path: Path):
    target = tmp_path / "asset.zip"
    digest = write_download([b"mfw", b"-payload"], target)
    assert digest == hashlib.sha256(b"mfw-payload").hexdigest()
```

- [ ] **Step 2: 运行测试确认先失败**

Run: `uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/test_mfw_release.py -q`

Expected: FAIL with `ModuleNotFoundError: tools.mfw_release`。

- [ ] **Step 3: 实现正式 release 解析和流式下载**

```python
@dataclass(frozen=True)
class ReleaseAsset:
    repo: str
    tag: str
    name: str
    url: str


def resolve_asset(repo: str, release: Mapping[str, Any], pattern: str) -> ReleaseAsset:
    if release.get("draft") or release.get("prerelease"):
        raise ValueError("latest release must be formal")
    matches = [a for a in release["assets"] if re.search(pattern, a["name"])]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one asset for {repo}, got {len(matches)}")
    item = matches[0]
    return ReleaseAsset(repo, release["tag_name"], item["name"], item["browser_download_url"])


def write_download(chunks: Iterable[bytes], target: Path) -> str:
    digest = hashlib.sha256()
    with target.open("wb") as stream:
        for chunk in chunks:
            stream.write(chunk)
            digest.update(chunk)
    return digest.hexdigest()
```

Add `fetch_latest_asset()` with a 30-second timeout, GitHub JSON content-type validation, and exact patterns `^MFW.*macos-aarch64.*\.zip$` and `^MAA-macos-aarch64.*`.

- [ ] **Step 4: 运行测试和静态检查**

Run: `uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/test_mfw_release.py -q && uv run --no-project --with ruff ruff check tools/mfw_release.py tests/test_mfw_release.py`

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add tools/mfw_release.py tests/test_mfw_release.py
git commit -m "build: resolve latest macOS arm64 MFW releases"
```

### Task 3: 组装不可覆盖的隔离安装产物

**Files:**
- Create: `tools/mfw_install.py`
- Create: `tests/test_mfw_install.py`

**Interfaces:**
- Consumes: `ReleaseAsset`, `fetch_latest_asset()`, `write_download()`。
- Produces: `BuildMetadata`；`safe_extract(zip_path, output)`；`build_install(repo_root, output, mfw_asset, maa_asset, commit) -> BuildMetadata`；`build_from_base(repo_root, base_candidate, output, commit) -> BuildMetadata`；`verify_candidate(repo_root, candidate) -> BuildMetadata`。

- [ ] **Step 1: 写路径安全、布局和元数据测试**

```python
import json
from pathlib import Path
import zipfile

import pytest

from tools.mfw_install import (
    build_from_base,
    hash_project_payload,
    load_metadata,
    prepare_output,
    safe_extract,
    sha256,
    verify_candidate,
)


def test_prepare_output_rejects_nonempty_directory(tmp_path: Path):
    output = tmp_path / "candidate"
    output.mkdir()
    (output / "user.json").write_text("{}")
    with pytest.raises(FileExistsError, match="not empty"):
        prepare_output(output)


def test_safe_extract_rejects_parent_traversal(tmp_path: Path):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("../escape", "x")
    with pytest.raises(ValueError, match="unsafe zip member"):
        safe_extract(archive, tmp_path / "out")


def test_fixture_build_has_maa_bbb_layout(fixture_install: Path):
    assert (fixture_install / "interface.json").is_file()
    assert (fixture_install / "tasks/游戏启动.json").is_file()
    assert (fixture_install / "resource/base/pipeline").is_dir()
    assert (fixture_install / "runtimes/osx-arm64").is_dir()
    assert (fixture_install / "agent/main.py").is_file()
    metadata = json.loads((fixture_install / "build-metadata.json").read_text())
    assert metadata["target"] == "macos-aarch64"
    assert len(metadata["mfw"]["sha256"]) == 64
    interface = json.loads((fixture_install / "interface.json").read_text())
    assert interface["agent"]["child_exec"] == "./python/bin/python3"
    assert interface["agent"]["child_args"] == ["-u", "./agent/main.py"]
    assert interface["agent"]["embedded"] is True


def test_derived_candidate_preserves_runtime_and_replaces_project_payload(
    repo_fixture: Path, fixture_install: Path, tmp_path: Path
):
    output = tmp_path / "derived"
    metadata = build_from_base(repo_fixture, fixture_install, output, "deadbeef")
    assert sha256(output / "MFW") == sha256(fixture_install / "MFW")
    assert metadata.mfw == load_metadata(fixture_install).mfw
    assert metadata.maafw == load_metadata(fixture_install).maafw
    assert metadata.base_metadata_sha256 == sha256(fixture_install / "build-metadata.json")
    assert metadata.payload_sha256 == hash_project_payload(output)
    assert (output / "tasks/游戏启动.json").read_bytes() == (
        repo_fixture / "assets/tasks/游戏启动.json"
    ).read_bytes()
    assert verify_candidate(repo_fixture, output) == metadata
```

- [ ] **Step 2: 运行测试确认先失败**

Run: `uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/test_mfw_install.py -q`

Expected: FAIL，因为安装器、`fixture_install` fixture 和 synthetic `repo_fixture` 尚不存在；测试 fixture 必须在 `tmp_path` 下组装最小的 interface/tasks/resource/agent/CFA/requirements 与伪 MFW/Maa zip，不得提前创建生产资源。

- [ ] **Step 3: 实现安全解压、相对布局和原子元数据**

```python
@dataclass(frozen=True)
class BuildMetadata:
    mja_commit: str
    target: str
    resolved_at: str
    mfw: Mapping[str, str]
    maafw: Mapping[str, str]
    payload_sha256: str
    immutable_tree_sha256: str
    base_metadata_sha256: str | None = None


def prepare_output(output: Path) -> None:
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)


def safe_extract(archive: Path, output: Path) -> None:
    root = output.resolve()
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            target = (output / member.filename).resolve()
            if root != target and root not in target.parents:
                raise ValueError(f"unsafe zip member: {member.filename}")
        bundle.extractall(output)
```

Copy MFW root files to output root; copy Maa libraries/binaries to `runtimes/osx-arm64/`; copy `share/MaaAgentBinary` to `runtimes/osx-arm64/MaaAgentBinary`; copy `assets/interface.mfw.json` as output `interface.json`, then copy `assets/tasks`, `assets/resource`, `agent`, `CFA_setting.json`, and `requirements.txt`. The current formal MFW-PyQt6 macOS arm64 release is a PyInstaller bundle with `MFW`, `_internal/Python`, `_internal/maa`, and `maafw`; it does not contain Maa_bbb's legacy `python/bin/python3` path. For that current layout, the installed interface preserves the documented `agent.child_args` entry (`{PROJECT_DIR}/agent/main.py`) and sets only `agent.embedded` to `true`, allowing MFW to generate its embedded custom loader. The installer retains a compatibility branch for older bundles that do contain `python/bin/python3`, where it applies Maa_bbb's standalone-Python path rewrite. Both layouts are verified before metadata is written; an unsupported runtime fails the build.

`--base-candidate` is the only supported way to assemble later live candidates without re-resolving releases. It requires a validated, immutable base with matching `target`, release SHA-256 values and a supported MFW runtime layout; verifies `immutable_tree_sha256` over every base file except project-owned payload, mutable MFW profile/config state and `build-metadata.json`; copies that tree to a nonexistent output while omitting saved profiles; replaces exactly `interface.json`, `tasks/`, `resource/`, `agent/`, `CFA_setting.json`, and `requirements.txt` from the current repository; reapplies the layout-specific embedded Agent contract; and writes new metadata containing `mja_commit`, deterministic `payload_sha256`, `immutable_tree_sha256`, and `base_metadata_sha256` while preserving the base MFW/Maa identities. It rejects a dirty/mutated base and never copies a derived candidate's saved profiles back into the base. `--verify-candidate PATH` validates those hashes and compares every project-owned file with the repository, normalizing only the documented installed Agent paths; it also rejects probe imports/files.

- [ ] **Step 4: 运行测试和 CLI help**

Run: `uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/test_mfw_install.py -q && python3 tools/mfw_install.py --help`

Expected: PASS；CLI requires `--output` for builds, accepts optional `--mfw-archive`/`--maa-archive` for reproducible offline tests, accepts exactly one `--base-candidate` as the pinned-runtime derivation mode, and exposes mutually exclusive read-only `--verify-candidate PATH`.

- [ ] **Step 5: 提交**

```bash
git add tools/mfw_install.py tests/test_mfw_install.py
git commit -m "build: assemble isolated MFW distribution"
```

### Task 4: 建立 ProjectInterface v2 骨架

**Files:**
- Create: `assets/interface.mfw.json`
- Create: `assets/tasks/游戏启动.json`
- Create: `CFA_setting.json`
- Create: `tests/test_mfw_interface.py`

**Interfaces:**
- Consumes: MFW ProjectInterface v2 和 Maa_bbb embedded 配置契约。
- Produces: controller `android`、resource `mja_android`、任务 `GAME_START`、preset `日常-简化版`/`日常-完整版` 的增量容器。

- [ ] **Step 1: 写 v2、相对路径和禁用入口测试**

```python
import json
from pathlib import Path


def test_interface_is_android_only_v2_skeleton():
    interface = json.loads(Path("assets/interface.mfw.json").read_text())
    assert interface["interface_version"] == 2
    assert interface["task"] == []
    assert [item["name"] for item in interface["controller"]] == ["android"]
    assert interface["controller"][0]["type"] == "Adb"
    assert [item["name"] for item in interface["resource"]] == ["mja_android"]
    assert interface["resource"][0]["path"] == ["./resource/base"]
    assert [group["name"] for group in interface["group"]] == ["启动", "日常", "周常", "工具"]
    assert all(isinstance(item, dict) for preset in interface["preset"] for item in preset["task"])
    assert interface["agent"]["child_args"] == ["{PROJECT_DIR}/agent/main.py"]
    assert "daily_all" not in Path("assets/interface.mfw.json").read_text().lower()
    assert "speedrun" not in Path("assets/interface.mfw.json").read_text().lower()


def test_start_task_is_imported_once():
    interface = json.loads(Path("assets/interface.mfw.json").read_text())
    assert interface["import"] == ["tasks/游戏启动.json"]
    task_file = json.loads(Path("assets/tasks/游戏启动.json").read_text())
    assert task_file["task"][0]["name"] == "GAME_START"
    assert task_file["task"][0]["entry"] == "MJA_GAME_START"
```

- [ ] **Step 2: 运行测试确认先失败**

Run: `uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/test_mfw_interface.py -q`

Expected: FAIL，因为并行 interface 尚不存在。

- [ ] **Step 3: 写入最小合法 interface、启动任务和 embedded 设置**

```json
{
  "interface_version": 2,
  "name": "MJA",
  "controller": [{"name": "android", "label": "安卓端", "type": "Adb"}],
  "resource": [{"name": "mja_android", "label": "Android 模拟器", "path": ["./resource/base"], "controller": ["android"]}],
  "agent": {"child_exec": "python", "child_args": ["{PROJECT_DIR}/agent/main.py"], "identifier": "mja_agent"},
  "group": [
    {"name": "启动", "default_expand": true},
    {"name": "日常", "default_expand": true},
    {"name": "周常", "default_expand": true},
    {"name": "工具", "default_expand": false}
  ],
  "import": ["tasks/游戏启动.json"],
  "task": [],
  "option": {},
  "preset": [
    {"name": "日常-简化版", "task": [{"name": "GAME_START", "enabled": true}]},
    {"name": "日常-完整版", "task": [{"name": "GAME_START", "enabled": true}]}
  ]
}
```

`assets/tasks/游戏启动.json` contains `{"task":[{"name":"GAME_START","label":"启动并进入游戏","default_check":true,"group":["启动"],"entry":"MJA_GAME_START"}]}`. `CFA_setting.json` content is exactly `{"update_flag":"1","embedded":true}`. Validate these fields against the checked-out MFW v4.8.23 `docs/interface.md`; do not convert preset task objects into string arrays.

- [ ] **Step 4: 运行 interface 测试**

Run: `uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/test_mfw_interface.py -q`

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add assets/interface.mfw.json assets/tasks/游戏启动.json CFA_setting.json tests/test_mfw_interface.py
git commit -m "feat: add Android-only MFW interface skeleton"
```

### Task 5: 迁移公共资源并建立资源检查器

**Files:**
- Create: `assets/resource/base/model/ocr/det.onnx`
- Create: `assets/resource/base/model/ocr/rec.onnx`
- Create: `assets/resource/base/model/ocr/keys.txt`
- Create: `assets/resource/base/image/`
- Create: `assets/resource/base/pipeline/common/terminal.json`
- Create: `tools/check_mfw_resources.py`
- Create: `tests/test_mfw_pipeline_contract.py`

**Interfaces:**
- Consumes: `assets/resource_android/model/ocr/`, `assets/resource_android/image/` 和 Maa resource loader。
- Produces: `load_pipeline_nodes(root) -> dict[str, dict]`；公共节点 `MJA_COMMON_STOP`、`MJA_COMMON_ABORT`。

- [ ] **Step 1: 写资源完整性和 Abort 收敛测试**

```python
from pathlib import Path

from tools.check_mfw_resources import load_pipeline_nodes, validate_nodes


def test_base_resource_contains_ocr_and_common_terminals():
    root = Path("assets/resource/base")
    assert (root / "model/ocr/det.onnx").is_file()
    assert (root / "model/ocr/rec.onnx").is_file()
    assert (root / "model/ocr/keys.txt").is_file()
    nodes = load_pipeline_nodes(root / "pipeline")
    assert nodes["MJA_COMMON_STOP"]["action"] == "StopTask"
    assert nodes["MJA_COMMON_ABORT"]["Abort"] is True
    assert nodes["MJA_COMMON_ABORT"]["action"] == "StopTask"


def test_pipeline_validator_rejects_forbidden_control_planes(tmp_path: Path):
    nodes = {"X": {"action": "Custom", "custom_action": "DailyWorkflowAction"}}
    errors = validate_nodes(nodes)
    assert any("DailyWorkflowAction" in error for error in errors)
```

- [ ] **Step 2: 运行测试确认先失败**

Run: `uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/test_mfw_pipeline_contract.py -q`

Expected: FAIL，因为新资源树和检查器尚不存在。

- [ ] **Step 3: 复制经验证的模型/模板并实现检查器**

Use `rsync -a assets/resource_android/model/ocr/ assets/resource/base/model/ocr/` and `rsync -a assets/resource_android/image/ assets/resource/base/image/` as mechanical binary/template copies. Implement `load_pipeline_nodes` to reject duplicate node names and malformed JSON; implement `validate_nodes` to reject `daily_all`, `DailyWorkflowAction`, `MaaAndroidWorkflowDriver`, `speedrun`, missing `next/on_error` targets, unbounded self-cycles, and business failure nodes without `Abort: true`.

```json
{
  "MJA_COMMON_STOP": {"recognition": "DirectHit", "action": "StopTask"},
  "MJA_COMMON_ABORT": {"recognition": "DirectHit", "Abort": true, "action": "StopTask"}
}
```

- [ ] **Step 4: 运行资源检查**

Run: `uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/test_mfw_pipeline_contract.py -q && python3 tools/check_mfw_resources.py assets/resource/base`

Expected: PASS；输出节点数和零错误。

- [ ] **Step 5: 提交**

```bash
git add assets/resource/base tools/check_mfw_resources.py tests/test_mfw_pipeline_contract.py
git commit -m "feat: add validated MFW base resource"
```

### Task 6: 实现不可变政策、任务状态和结构化诊断

**Files:**
- Create: `agent/custom/support/__init__.py`
- Create: `agent/custom/support/models.py`
- Create: `agent/custom/support/policy.py`
- Create: `agent/custom/support/state.py`
- Create: `agent/custom/support/diagnostics.py`
- Create: `agent/custom/support/params.py`
- Create: `tests/test_mfw_safety.py`
- Create: `tests/test_mfw_diagnostics.py`

**Interfaces:**
- Consumes: `agent/workflows/catalog.py` 中 17 项 `_POLICY_VALUES`，仅复制数据含义，不复制调度/导航。
- Produces: `TaskOutcomeStatus`、`TaskPolicy`、`TASK_POLICIES`、`TaskRunStore`、`RUN_STORE`、`TaskDiagnostics`、`parse_action_params()`。

- [ ] **Step 1: 写政策等价、上限和脱敏诊断测试**

```python
import json
from pathlib import Path

import pytest

from agent.custom.support.diagnostics import TaskDiagnostics
from agent.custom.support.models import TaskOutcomeStatus
from agent.custom.support.policy import TASK_POLICIES
from agent.custom.support.state import TaskRunStore


def test_all_17_policies_are_migrated_without_control_plane_data():
    assert len(TASK_POLICIES) == 17
    assert "MAIL_REWARD_DAILY" in TASK_POLICIES
    assert all(not hasattr(policy, "task_order") for policy in TASK_POLICIES.values())


def test_action_counter_rejects_limit_plus_one():
    store = TaskRunStore()
    store.begin("MAIL_REWARD_DAILY")
    allowed = TASK_POLICIES["MAIL_REWARD_DAILY"].action_caps["claim_all_mail"]
    for _ in range(allowed):
        store.increment("MAIL_REWARD_DAILY", "claim_all_mail")
    with pytest.raises(PermissionError, match="action limit"):
        store.increment("MAIL_REWARD_DAILY", "claim_all_mail")


def test_diagnostics_redacts_credentials(tmp_path: Path):
    diagnostics = TaskDiagnostics(tmp_path, run_id="run-1")
    diagnostics.begin("MAIL_REWARD_DAILY")
    diagnostics.finish(
        "MAIL_REWARD_DAILY",
        TaskOutcomeStatus.FAILED,
        "mail",
        "password=secret token=abc",
    )
    text = (tmp_path / "run-1/MAIL_REWARD_DAILY/result.json").read_text()
    assert "secret" not in text
    assert "abc" not in text
```

- [ ] **Step 2: 运行测试确认先失败**

Run: `uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/test_mfw_safety.py tests/test_mfw_diagnostics.py -q`

Expected: FAIL，因为 `agent.custom.support` 尚不存在。

- [ ] **Step 3: 实现数据模型和政策迁移**

```python
class TaskOutcomeStatus(StrEnum):
    SUCCESS = "success"
    ALREADY_COMPLETE = "already_complete"
    NOT_ELIGIBLE = "not_eligible"
    FAILED = "failed"


@dataclass(frozen=True)
class TaskPolicy:
    task_id: str
    label: str
    risk_levels: frozenset[str]
    max_steps: int
    action_caps: Mapping[str, int]
    approved_resources: frozenset[str]
    resource_caps: Mapping[str, int]
    eligible_weekdays: frozenset[int] | None = None
```

Move the immutable `_POLICY_VALUES` entries from `agent/workflows/catalog.py` into `TASK_POLICIES` with canonical IDs and the exact existing action/resource limits. `TaskRunStore.increment` checks count before mutating. `TaskDiagnostics` writes `result.json` atomically and appends `action-trace.jsonl`; image methods write `before.png`, `after.png`, and only-on-failure `failure.png`. Diagnostic I/O exceptions are logged and do not rewrite a verified business status.

- [ ] **Step 4: 运行窄组件测试**

Run: `uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/test_mfw_safety.py tests/test_mfw_diagnostics.py -q`

Expected: PASS；17 项政策均存在，limit+1 被拒绝，敏感字段不落盘。

- [ ] **Step 5: 提交**

```bash
git add agent/custom/support tests/test_mfw_safety.py tests/test_mfw_diagnostics.py
git commit -m "feat: add narrow policy state and diagnostics core"
```

### Task 7: 实现任务生命周期、GuardedInput 和 RuntimeHealth

**Files:**
- Create: `agent/custom/action/__init__.py`
- Create: `agent/custom/action/task_lifecycle.py`
- Create: `agent/custom/action/guarded_input.py`
- Create: `agent/custom/action/runtime_health.py`
- Create: `agent/custom/support/controller_input.py`
- Create: `tests/test_mfw_agent.py`

**Interfaces:**
- Consumes: `RUN_STORE`, `TASK_POLICIES`, `TaskDiagnostics`, `parse_action_params`, `context.tasker.controller`。
- Produces: Maa 注册名 `BeginTask`、`GuardedInput`、`RecordTaskOutcome`、`RuntimeHealth`。

- [ ] **Step 1: 写同帧授权、预算拒绝和 Controller 透传测试**

```python
import json

from agent.custom.action.guarded_input import GuardedInput
from tests.mfw.fakes import FailingController, FakeArgv, FakeContext, and_reco, hit_reco, miss_reco


def test_guarded_input_clicks_only_after_page_target_and_budget_match():
    context = FakeContext()
    argv = FakeArgv(json.dumps({
        "task_id": "MAIL_REWARD_DAILY", "action_id": "claim_all_mail",
        "kind": "click", "evidence": {"page_index": 0, "target_index": 1},
    }), reco_detail=and_reco(hit_reco("mail.page"), hit_reco("mail.claim_all")))
    assert GuardedInput().run(context, argv) is True
    assert context.controller.actions == [("click", (120, 210))]


def test_guarded_input_rejects_unverified_target_without_input():
    context = FakeContext()
    argv = FakeArgv(json.dumps({
        "task_id": "MAIL_REWARD_DAILY", "action_id": "claim_all_mail",
        "kind": "click", "evidence": {"page_index": 0, "target_index": 1},
    }), reco_detail=and_reco(hit_reco("mail.page"), miss_reco("mail.claim_all")))
    assert GuardedInput().run(context, argv) is False
    assert context.controller.actions == []


def test_guarded_input_does_not_downgrade_controller_failure():
    context = FakeContext(controller=FailingController(RuntimeError("device lost")))
    argv = FakeArgv(json.dumps({
        "task_id": "MAIL_REWARD_DAILY", "action_id": "claim_all_mail",
        "kind": "click", "evidence": {"page_index": 0, "target_index": 1},
    }), reco_detail=and_reco(hit_reco("mail.page"), hit_reco("mail.claim_all")))
    with pytest.raises(RuntimeError, match="device lost"):
        GuardedInput().run(context, argv)


def test_runtime_health_does_not_shell_out(monkeypatch):
    monkeypatch.setattr("subprocess.run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("shell forbidden")))
    context = FakeContext()
    assert RuntimeHealth().run(context, FakeArgv("{}")) is True
```

- [ ] **Step 2: 运行测试确认先失败**

Run: `uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/test_mfw_agent.py -q`

Expected: FAIL，因为 action 模块尚不存在。

- [ ] **Step 3: 实现窄 Action**

```python
def click_box(controller: Any, box: Sequence[int]) -> bool:
    x, y, width, height = map(int, box)
    return bool(controller.post_click(x + width // 2, y + height // 2).wait())


@AgentServer.custom_action("GuardedInput")
class GuardedInput(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> bool:
        params = parse_action_params(argv)
        if not validate_and_evidence(argv.reco_detail, params["evidence"]):
            return False
        RUN_STORE.increment(params["task_id"], params["action_id"])
        return dispatch_current_controller(context.tasker.controller, argv.box, params)
```

`GuardedInput` supports only `click` and `swipe`. For click, it ignores any coordinate-like value in `custom_action_param` and uses only Maa's `argv.box`; for swipe it accepts a bounded relative vector but still requires the recognized target box. `validate_and_evidence` requires `argv.reco_detail.hit`, algorithm `And`, an `AndRecognitionResult`, hit sub-results at exact `page_index` and `target_index`, and optional OCR sub-results at `resource_index`/`amount_index`. Resource params separate the same-frame OCR value (`observed_amount`) from the policy counter increment (`budget_amount`): normally they match, but Jianlin verifies visible cost 10 紫色魂玉 while incrementing its frozen one-purchase budget by 1. It validates exact JSON types, screen bounds, action policy, OCR resource name/observed amount/budget amount and writes before/after diagnostics. Pipeline contract tests require `And.box_index` to equal `target_index`, so the click box is the target from the same recognition frame. Authorization denial returns `False` so that the task's `on_error` reaches its explicit business Abort; once a controller operation is posted, `wait()` failure/exception is re-raised and never converted to policy denial. `RuntimeHealth` checks the documented Maa `controller.connected`, `controller.resolution` and `controller.cached_image` properties; it must not invoke adb, scan devices, start AVD, read `MJA_CONTROLLER`, catch Maa device-loss exceptions, or turn infrastructure failure into business `False`. The Task 11 device-loss probe remains the authoritative proof that MFW stops the queue before a task-local `on_error` can continue.

- [ ] **Step 4: 运行 Agent 测试**

Run: `uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/test_mfw_agent.py tests/test_mfw_safety.py tests/test_mfw_diagnostics.py -q`

Expected: PASS；任何未验证、超预算或未知 kind 均零输入。

- [ ] **Step 5: 提交**

```bash
git add agent/custom/action agent/custom/support/controller_input.py tests/test_mfw_agent.py
git commit -m "feat: add guarded embedded Agent actions"
```

### Task 8: 将 Agent 入口收缩到 embedded 注册器

**Files:**
- Modify: `agent/main.py`
- Create: `tests/test_mfw_agent_entry.py`

**Interfaces:**
- Consumes: MFW 传入的 socket ID 和四个窄 Action 注册模块。
- Produces: `main(socket_id: str) -> int`；无业务调度、无 Controller 选择的 AgentServer 入口。

- [ ] **Step 1: 写导入和禁止依赖测试**

```python
import ast
from pathlib import Path


def test_agent_entry_imports_only_narrow_registration_modules():
    source = Path("agent/main.py").read_text()
    tree = ast.parse(source)
    imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert "agent.custom.action.guarded_input" in imported
    assert "agent.custom.action.task_lifecycle" in imported
    assert "agent.custom.action.runtime_health" in imported
    assert "agent.workflows.aggregate" not in imported
    assert "agent.workflows.maa_android" not in imported
    assert "MJA_CONTROLLER" not in source
```

- [ ] **Step 2: 运行测试确认先失败**

Run: `uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/test_mfw_agent_entry.py -q`

Expected: FAIL，旧 `agent/main.py` 仍注册旧 action/sink 或读取旧环境。

- [ ] **Step 3: 实现 socket-only 入口**

```python
from maa.agent.agent_server import AgentServer

from agent.custom.action import guarded_input, runtime_health, task_lifecycle


def main(socket_id: str) -> int:
    AgentServer.start_up(socket_id)
    AgentServer.join()
    AgentServer.shut_down()
    return 0
```

CLI accepts exactly one positional `socket_id`; errors go to stderr and return non-zero. Do not import old business workflows, aggregate modules, macOS lifecycle modules or sink modules.

- [ ] **Step 4: 在 Python 3.12 和当前 Python 下验证导入**

Run: `uv run --no-project --python 3.12 --with-requirements requirements.txt --with pytest pytest tests/test_mfw_agent_entry.py tests/test_mfw_python_contract.py -q`

Expected: PASS；uv 可下载 Python 3.12 时必须本地通过；下载受限时记录 `environment_unavailable`，但 CI 的 Python 3.12 job 仍是必过门禁。

- [ ] **Step 5: 提交**

```bash
git add agent/main.py tests/test_mfw_agent_entry.py
git commit -m "refactor: reduce Agent entry to embedded narrow actions"
```

### Task 9: 实现统一启动、已知弹窗和回主页 Pipeline

**Files:**
- Create: `assets/resource/base/pipeline/common/home_recovery.json`
- Create: `assets/resource/base/pipeline/common/known_popups.json`
- Create: `assets/resource/base/pipeline/startup/game_start.json`
- Create: `tests/mfw/pipeline_assertions.py`
- Create: `tests/test_mfw_startup_pipeline.py`
- Create: `tests/fixtures/startup/manifest.json`

**Interfaces:**
- Consumes: 已迁移的主页/标题/弹窗模板、`RuntimeHealth`、`GuardedInput`、`RecordTaskOutcome`。
- Produces: `MJA_GAME_START`、`MJA_GAME_READY` 和所有业务任务可 `[JumpBack]` 的公共恢复节点。

- [ ] **Step 1: 写入口、恢复优先级和有界循环测试**

```python
from pathlib import Path

from tests.mfw.pipeline_assertions import load_nodes, assert_all_cycles_bounded


def test_startup_handles_ready_startapp_known_popup_and_unknown_abort():
    nodes = load_nodes(Path("assets/resource/base/pipeline"))
    start = nodes["MJA_GAME_START"]
    assert "MJA_GAME_READY" in start["next"]
    assert "MJA_START_APP" in start["next"]
    assert nodes["MJA_START_APP"]["action"] == "StartApp"
    assert nodes["MJA_START_UNKNOWN_ABORT"]["next"] == ["MJA_COMMON_ABORT"]
    assert_all_cycles_bounded(nodes)


def test_game_ready_requires_fresh_home_recognition():
    nodes = load_nodes(Path("assets/resource/base/pipeline"))
    ready = nodes["MJA_GAME_READY"]
    assert ready["recognition"] in {"TemplateMatch", "OCR"}
    assert ready["post_delay"] >= 500
```

- [ ] **Step 2: 运行测试确认先失败**

Run: `uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/test_mfw_startup_pipeline.py -q`

Expected: FAIL，因为 startup Pipeline 和通用断言尚不存在。

- [ ] **Step 3: 实现公共 Pipeline 和 fixture manifest**

Create `tests/mfw/pipeline_assertions.py` with `load_nodes`, `assert_targets_exist`, `assert_all_cycles_bounded`, and fixture recognition helpers. `MJA_GAME_START` probes in this order: fresh home, title/login/loading, known popup, known closable page, StartApp. `MJA_START_APP` uses configured package and a bounded wait. Known signup/reward/network/resource-update confirmations use explicit templates and `max_hit`/`timeout`; login verification/client update/unknown page record `failed` and enter `MJA_COMMON_ABORT`. `MJA_GAME_READY` always recognizes a fresh home screenshot after the final input.

Fixture manifest entries use exact keys `ready`, `title`, `known_popup`, `known_page`, `unknown`, and map each key to an existing or newly captured PNG plus expected terminal.

- [ ] **Step 4: 运行启动和资源契约测试**

Run: `uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/test_mfw_startup_pipeline.py tests/test_mfw_pipeline_contract.py -q && python3 tools/check_mfw_resources.py assets/resource/base`

Expected: PASS；所有循环有界、所有引用存在、未知页只到 Abort。

- [ ] **Step 5: 提交**

```bash
git add assets/resource/base/pipeline tests/fixtures/startup tests/mfw/pipeline_assertions.py tests/test_mfw_startup_pipeline.py
git commit -m "feat: add bounded MFW startup and home recovery"
```

### Task 10: 建立只读 fixture 捕获和可复现 MFW 实机运行工具

**Files:**
- Create: `tools/capture_mfw_fixture.py`
- Create: `tools/mfw_profile.py`
- Create: `tests/test_capture_mfw_fixture.py`
- Create: `tests/test_mfw_profile.py`

**Interfaces:**
- Consumes: macOS `MacOSController` 的只读截图、严格的 `1280×720` 资源校准，以及 MFW `config/multi_config.json`、`config/configs/*.json` 和布尔开关 `--direct-run`；Android ADB 仅作为显式兼容后端。
- Produces: `fixture_destination(root, task_id, case) -> Path`；CLI `capture_mfw_fixture --task-id ID --case not_eligible|known_drift`；`resolve_config_id(install_root, profile_name) -> str`；CLI `mfw_profile run --install PATH --profile-name NAME`，实际执行 argv `[MFW, --config-id={resolved_id}, --direct-run]`。

- [ ] **Step 1: 写按显示名唯一解析和 argv 测试**

```python
import json
from pathlib import Path

import pytest

from tools.capture_mfw_fixture import fixture_destination, require_new_fixture_path
from tools.mfw_profile import build_run_argv, resolve_config_id


def test_resolve_config_id_uses_saved_profile_name(tmp_path: Path):
    configs = tmp_path / "config/configs"
    configs.mkdir(parents=True)
    (configs / "c_mail.json").write_text(json.dumps({"name": "live-MAIL_REWARD_DAILY"}))
    assert resolve_config_id(tmp_path, "live-MAIL_REWARD_DAILY") == "c_mail"


def test_resolve_config_id_rejects_missing_or_duplicate_name(tmp_path: Path):
    (tmp_path / "config/configs").mkdir(parents=True)
    with pytest.raises(ValueError, match="exactly one"):
        resolve_config_id(tmp_path, "missing")


def test_direct_run_is_boolean_flag_not_task_argument(tmp_path: Path):
    argv = build_run_argv(tmp_path, "c_mail")
    assert argv == [str(tmp_path / "MFW"), "--config-id=c_mail", "--direct-run"]


def test_fixture_destination_is_scoped_and_never_overwrites(tmp_path: Path):
    target = fixture_destination(tmp_path, "MAIL_REWARD_DAILY", "not_eligible")
    assert target == tmp_path / "MAIL_REWARD_DAILY/not_eligible.png"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"existing")
    with pytest.raises(FileExistsError):
        require_new_fixture_path(target)
```

- [ ] **Step 2: 运行测试确认先失败**

Run: `uv run --no-project --with pytest pytest tests/test_capture_mfw_fixture.py tests/test_mfw_profile.py -q`

Expected: FAIL because the two tools do not exist.

- [ ] **Step 3: 实现只读档案解析和直接运行**

```python
def resolve_config_id(install_root: Path, profile_name: str) -> str:
    matches = []
    for path in sorted((install_root / "config/configs").glob("c_*.json")):
        if json.loads(path.read_text())["name"] == profile_name:
            matches.append(path.stem)
    if len(matches) != 1:
        raise ValueError(f"expected exactly one saved profile named {profile_name}, got {len(matches)}")
    return matches[0]


def build_run_argv(install_root: Path, config_id: str) -> list[str]:
    return [str(install_root / "MFW"), f"--config-id={config_id}", "--direct-run"]
```

`capture_mfw_fixture` accepts only IDs present in `TASK_POLICIES` and cases `not_eligible`/`known_drift`; it defaults to a read-only macOS `MacOSController` capture, requires an explicit window ID and the canonical `1280×720` calibration, and refuses an existing destination. It never sends Maa or OS input; the operator manually navigates to the labeled state before capture. Android remains available only through the explicit compatibility backend. The profile CLI uses `subprocess.run(argv, cwd=install_root, check=False)` without shell expansion and returns MFW's exit code. It never creates or mutates MFW profiles. Before each live gate, the operator opens the candidate once, creates a profile with the exact name required by that task, selects the stated tasks in the stated order, saves it, and closes MFW; the helper rejects missing/duplicate names.

- [ ] **Step 4: 运行测试和真实 help**

Run: `uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/test_capture_mfw_fixture.py tests/test_mfw_profile.py -q && python3 -m tools.capture_mfw_fixture --help && python3 tools/mfw_profile.py --help`

Expected: PASS；capture help lists two cases；profile help lists `resolve` and `run` subcommands；no invocation accepts a task name after `--direct-run`.

- [ ] **Step 5: 提交**

```bash
git add tools/capture_mfw_fixture.py tools/mfw_profile.py tests/test_capture_mfw_fixture.py tests/test_mfw_profile.py
git commit -m "test: capture fixtures and run resolved MFW profiles"
```

### Task 11: 用 MFW 探针证明失败传播契约

**Files:**
- Create: `tests/mfw/probes/tasks/失败传播探针.json`
- Create: `tests/mfw/probes/resource/pipeline/failure_contract.json`
- Create: `tests/test_mfw_failure_contract.py`
- Create: `tools/mfw_probe_install.py`
- Create: `tools/verify_mfw_evidence.py`
- Create: `verification/mfw/failure-contract.schema.json`

**Interfaces:**
- Consumes: `MJA_COMMON_STOP`、`MJA_COMMON_ABORT`、MFW `--config-id --direct-run`。
- Produces: 可重复执行的 success/already/not-eligible/Abort/continue/infra-stop 探针、derived `probe-metadata.json` 和严格证据校验器。

- [ ] **Step 1: 写探针形状和证据拒绝测试**

```python
import json
from pathlib import Path

import pytest

from tools.verify_mfw_evidence import verify_failure_contract


def test_failure_probe_has_abort_then_sentinel():
    nodes = json.loads(Path("tests/mfw/probes/resource/pipeline/failure_contract.json").read_text())
    assert nodes["MJA_PROBE_BUSINESS_FAILURE"]["next"] == ["MJA_COMMON_ABORT"]
    assert nodes["MJA_PROBE_SENTINEL"]["next"] == ["MJA_COMMON_STOP"]


def test_evidence_rejects_abort_without_following_sentinel(tmp_path: Path):
    evidence = tmp_path / "failure-contract.json"
    evidence.write_text(json.dumps({"abort_failed": True, "sentinel_ran": False}))
    with pytest.raises(ValueError, match="sentinel"):
        verify_failure_contract(evidence)
```

- [ ] **Step 2: 运行测试确认先失败**

Run: `uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/test_mfw_failure_contract.py -q`

Expected: FAIL，因为探针和验证器尚不存在。

- [ ] **Step 3: 实现六条独立探针路径**

The probe task file declares `MJA_PROBE_SUCCESS`, `MJA_PROBE_ALREADY_COMPLETE`, `MJA_PROBE_NOT_ELIGIBLE`, `MJA_PROBE_BUSINESS_FAILURE`, and `MJA_PROBE_SENTINEL`. The first three record their exact structured status then stop normally. Business failure records `failed` then reaches `MJA_COMMON_ABORT`. `tools/mfw_probe_install.py` requires a validated base candidate and a nonexistent output, copies the candidate, copies only the probe task/resource files, and appends the probe import to the copied interface; it refuses a production source tree as output. It writes `probe-metadata.json` with the base `build-metadata.json` SHA-256, base `payload_sha256`, and deterministic probe overlay SHA-256, and the verifier rejects evidence that cannot reproduce those links. A direct-run profile in that derived candidate queues business failure followed by sentinel. Infrastructure tests use further isolated copies with respectively missing resource, missing Agent executable, missing Maa runtime, and disconnected ADB; they must not enter `RecordTaskOutcome(failed)`. Add a negative contract asserting `assets/interface.mfw.json` and `assets/tasks/` never contain `MJA_PROBE_`.

- [ ] **Step 4: 运行自动化并执行当前构建的真实 MFW 探针**

```bash
uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/test_mfw_failure_contract.py -q
python3 tools/mfw_install.py --output install/mfw-foundation-candidate
python3 tools/mfw_probe_install.py --base install/mfw-foundation-candidate --output install/mfw-failure-probe
python3 tools/mfw_profile.py run --install install/mfw-failure-probe --profile-name live-failure-contract
```

Expected: 自动化 PASS；`live-failure-contract` 档案按顺序只选择 success、already-complete、not-eligible、business-failure、sentinel 五个探针；MFW UI/log 中前三项正常完成，business failure 标记失败，sentinel 随后执行；四种基础设施故障停止队列。把真实 tag/SHA/config/log paths 写入 `verification/mfw/failure-contract.json`，再运行 `python3 tools/verify_mfw_evidence.py --failure-contract verification/mfw/failure-contract.json`。

- [ ] **Step 5: 提交探针代码与真实证据**

```bash
git add tests/mfw/probes tests/test_mfw_failure_contract.py tools/mfw_probe_install.py tools/verify_mfw_evidence.py verification/mfw/failure-contract.schema.json verification/mfw/failure-contract.json
git commit -m "test: prove MFW failure propagation contract"
```

Expected: 没有真实运行时不提交伪造的 `failure-contract.json`，本任务保持未完成并阻止批次 A。

### Task 12: 建立 CI 和基座验收门

**Files:**
- Create: `.github/workflows/mfw-check.yml`
- Modify: `README.md`
- Create: `docs/mfw-development.md`
- Create: `tests/test_mfw_ci_contract.py`
- Test: `tests/test_mfw_install.py`
- Test: `tests/test_capture_mfw_fixture.py`
- Test: `tests/test_mfw_profile.py`

**Interfaces:**
- Consumes: Tasks 1–11 的安装、资源、Agent、档案运行和契约测试。
- Produces: Python 3.12/3.14 检查、Maa resource load、最新正式版候选组装 artifact。

- [ ] **Step 1: 写 CI 契约测试**

```python
from pathlib import Path


def test_ci_checks_python_312_resource_and_isolated_install():
    workflow = Path(".github/workflows/mfw-check.yml").read_text()
    assert "3.12" in workflow
    assert "tools/check_mfw_resources.py" in workflow
    assert "tools/mfw_install.py" in workflow
    assert "install/ci-candidate" in workflow
    assert "uv.lock" not in workflow
```

- [ ] **Step 2: 运行测试确认先失败**

Run: `uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/test_mfw_ci_contract.py -q`

Expected: FAIL because `tests/test_mfw_ci_contract.py` and workflow do not exist; create the test with the code above before rerunning.

- [ ] **Step 3: 实现 CI 与开发文档**

Workflow jobs:

```yaml
jobs:
  python:
    strategy:
      matrix:
        python-version: ["3.12", "3.14"]
  resource:
    runs-on: macos-14
  package:
    runs-on: macos-14
```

`python` installs `requirements.txt`, pytest and Ruff, then runs unit tests and lint. `resource` downloads current MaaFramework macOS arm64 and runs Maa resource load plus `tools/check_mfw_resources.py`. `package` resolves MFW/Maa once, builds `install/ci-candidate`, validates interface/Agent imports, and uploads candidate plus `build-metadata.json`; no Android environment means artifact is explicitly `candidate-not-releasable`.

README only adds a clearly marked “MFW parallel development” section; it does not claim the old production entry has switched. `docs/mfw-development.md` documents isolated build, direct-run probe, fixture tests, real-device evidence fields, and the no-release-without-ADB rule.

- [ ] **Step 4: 运行基座全量门禁**

```bash
uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/test_mfw_python_contract.py tests/test_mfw_release.py tests/test_mfw_install.py tests/test_mfw_interface.py tests/test_mfw_pipeline_contract.py tests/test_mfw_safety.py tests/test_mfw_diagnostics.py tests/test_mfw_agent.py tests/test_mfw_agent_entry.py tests/test_mfw_startup_pipeline.py tests/test_capture_mfw_fixture.py tests/test_mfw_profile.py tests/test_mfw_failure_contract.py tests/test_mfw_ci_contract.py -q
uv run --no-project --with ruff ruff check agent/custom tools/mfw_release.py tools/mfw_install.py tools/check_mfw_resources.py tests/mfw tests/test_mfw_*.py
python3 tools/check_mfw_resources.py assets/resource/base
git diff --check
```

Expected: 全部 PASS；Task 11 的真实 MFW 失败传播证据已通过验证。

- [ ] **Step 5: 提交**

```bash
git add .github/workflows/mfw-check.yml README.md docs/mfw-development.md tests/test_mfw_ci_contract.py
git commit -m "ci: validate MFW foundation and candidate package"
```

## 基座完成门

- [ ] `assets/interface.json` 仍是旧正式入口，`assets/interface.mfw.json` 只在隔离产物中使用。
- [ ] 当前构建解析出的 MFW tag/URL/SHA-256 在一个候选内保持不变。
- [ ] MFW 可加载 `interface.json`、`resource/base`、Maa runtime 和 embedded Agent。
- [ ] `MJA_GAME_START` 能从未启动、标题/加载、主页、已知弹窗、已知页面收敛；未知页面 Abort。
- [ ] `GuardedInput` 对未验证目标、越界坐标、未知动作、超次数和超资源全部零输入。
- [ ] 业务 Abort 后 sentinel 执行；Controller/Resource/Agent/runtime/设备失联停止队列。
- [ ] Python 3.12 导入门和全部自动化通过后，才允许开始批次 A。
