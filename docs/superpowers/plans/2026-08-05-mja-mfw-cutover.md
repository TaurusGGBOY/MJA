# MJA MFW 生产切换与旧架构退役 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **2026-08-05 target correction (authoritative):** 生产切换的实机目标是本机 macOS 上运行的 iOS 版本游戏，使用 `MacOS` Controller、`ScreenCaptureKit` 和 `GlobalEvent`；不是 Android ADB。游戏由用户预先打开，MacOS Controller 不支持 `StartApp`。Android 文档与历史产物不满足本切换门禁。

**Goal:** 将已通过完整 macOS/iOS 验收的 MFW 候选提升为 MJA 唯一生产入口，并通过两个连续、可回滚、同一候选发布的提交安全删除旧 MFA/Python 聚合架构。

**Architecture:** 第一个切换提交用已验收的 `interface.mfw.json` 和 `mfw_install.py` 替换正式入口，同时删除所有旧生产调度入口并更新发布/运行文档。重新索引知识图谱并确认入站依赖归零后，第二个提交删除残余中央 workflow 和旧资源；与当前 macOS/iOS MFW 目标无关的 Android 兼容工具按依赖审计结果处理。

**Tech Stack:** Git、codebase-memory-mcp、MFW/MaaFramework、ProjectInterface v2、MaaFramework MacOS Controller、GitHub Actions、pytest、Ruff、SHA-256 evidence verifier

## Global Constraints

- 只有 `verification/mfw/candidate-summary.json` 证明同一 candidate 的 17 个单项、完整版、手工全选、同日重跑、Abort 继续和基础设施停止全部通过，且证据来自 macOS/iOS `MacOS` Controller，才允许开始切换。
- 切换由两个连续提交组成：提交 1 提升新入口并移除旧生产入口；提交 2 在依赖归零后删除残余旧实现。两者只能在同一候选产物中一起发布。
- 两个提交都必须可单独 `git revert`；不得 squash 后丢失切换边界，不得发布只含其中一个提交的中间状态。
- `assets/interface.json` 最终只声明 Android MFW v2 架构；不得保留 `assets/interface.mfw.json`、`daily_all`、MFA Controller/resource 或 hidden compatibility task。
- `tools/install.py` 是唯一生产安装器；它仍然每次构建只解析一次最新正式 MFW/MaaFramework 并记录 SHA，禁止 fallback。
- 生产代码不得导入 aggregate scheduler、`MaaAndroidWorkflowDriver`、旧 workflow engine、MFA action/sink、macOS 控制面或 `MJA_CONTROLLER` 分支。
- 保留一次性 Android 环境准备：`agent/android/{adb,avd,config,game,login,sdk}.py`、`tools/android_setup.py`、`tools/android_device.py`、`tools/capture_android_templates.py` 及仍对应的测试。
- 删除文件前必须用 codebase-memory graph 查入站依赖，再用字符串搜索补查 JSON、shell、CI 和文档；不能通过批量删测试制造绿色结果。
- 历史设计/计划可以保留旧架构文字，但 README、当前 runbook、CI、发布 workflow 和运行 skill 只能描述 MFW 生产入口。
- 回滚通过已保存的旧 release/tag 与完整产物完成；当前代码不保留运行时双栈开关。
- 不推送 Git tag、commit、artifact 或 GitHub release，除非用户在执行阶段明确授权外部发布动作；本计划先生成本地、可验证候选。
- 现有未跟踪 `uv.lock` 不修改、不暂存、不提交。

---

## 最终保留边界

```text
assets/interface.json
assets/tasks/**
assets/resource/base/**
agent/main.py
agent/custom/**
agent/android/{__init__,adb,avd,config,game,login,sdk}.py
tools/{install,mfw_release,check_mfw_resources,verify_mfw_evidence}.py
tools/{android_setup,android_device,capture_android_templates}.py
CFA_setting.json
requirements.txt
```

## 明确退役边界

```text
scripts/run-all-dailies.sh
tools/android_daily_run.py
tools/android_daily_run.sh
tools/android_run.py
tools/android_run.sh
tools/run_cli.py
tools/project_interface.py
tools/configure_mfa.py
tools/setup.py
tools/verify_install.py
tools/native_bundle.py
tools/request_permissions.py
tools/capture_templates.py
tools/verify_live_tasks.py
tools/verify_macos_controller.py
tools/verification_records.py
agent/actions/**
agent/macos/**
agent/sinks/**
agent/pretask.py
agent/safety.py
agent/diagnostics.py
agent/android/runtime_gate.py
agent/workflows/**
assets/resource_android/**
assets/resource/calibration.json
assets/resource/image/**
assets/resource/pipeline/**
native/maafw-android-cli/**
native/maafw-macos-fallback/**
verification/tasks/**
```

### Task 1: 验证切换前置条件并冻结旧回滚点

**Files:**
- Verify: `verification/mfw/candidate-summary.json`
- Verify: `install/mfw-full-candidate/build-metadata.json`
- Create: `verification/mfw/legacy-rollback.json`
- Modify: `tools/verify_mfw_evidence.py`
- Test: `tests/test_mfw_evidence.py`

**Interfaces:**
- Consumes: `verify_full_candidate(root)` 和尚可运行的旧安装入口。
- Produces: 本地 annotated tag `mja-legacy-final-2026-08-05`、旧产物 SHA-256 manifest、新候选确认记录。

- [ ] **Step 1: 验证新候选证据与工作树归属**

```bash
python3 tools/verify_mfw_evidence.py --root verification/mfw --require-all-tasks --require-full-preset --require-manual-all
git status --short --branch
git rev-parse HEAD
```

Expected: verifier PASS；除了明确的计划产物和用户 `uv.lock` 外无未知改动；candidate summary 的 MJA commit 可追溯。

- [ ] **Step 2: 组装并验证最后一个旧架构回滚产物**

```bash
test ! -e install/legacy-final
MJA_LEGACY_STAGE=$(mktemp -d /tmp/mja-legacy-final.XXXXXX)
rsync -a --exclude .git --exclude install --exclude downloads --exclude uv.lock ./ "$MJA_LEGACY_STAGE/"
python3 "$MJA_LEGACY_STAGE/tools/setup.py" --root "$MJA_LEGACY_STAGE"
cp -R "$MJA_LEGACY_STAGE/install" install/legacy-final
python3 tools/verify_install.py install/legacy-final
(cd install/legacy-final && find . -type f -print0 | sort -z | xargs -0 shasum -a 256) > install/legacy-final.sha256
```

Expected: 旧产物验证成功，manifest 使用产物根目录相对路径并覆盖全部文件；目标路径已存在时第一条命令立即停止，不覆盖或删除用户现有安装。临时 stage 保留到本任务结束供失败诊断，最终可由系统临时目录清理策略回收。

- [ ] **Step 3: 实现回滚记录生成器并校验 tag 不冲突**

Extend `tools/verify_mfw_evidence.py` with `--write-legacy-rollback`, which runs `git rev-parse HEAD`, verifies every line in the SHA-256 manifest against the exact artifact root, and atomically writes `tag`, full commit, artifact path, manifest path, manifest SHA-256, `artifact_storage: local-pending-publication`, and `verified: true`. Add tests for mismatched file SHA and dirty manifest rejection.

Run: `git rev-parse -q --verify refs/tags/mja-legacy-final-2026-08-05`

Expected: command exits non-zero before creation；若 tag 已存在，确认其 commit 和 manifest 完全一致，否则停止切换。

- [ ] **Step 4: 创建本地回滚 tag 并验证 manifest**

```bash
git tag -a mja-legacy-final-2026-08-05 -m "Last validated legacy MJA control plane"
cd install/legacy-final && shasum -a 256 -c ../legacy-final.sha256
cd ../.. && python3 tools/verify_mfw_evidence.py --write-legacy-rollback verification/mfw/legacy-rollback.json --tag mja-legacy-final-2026-08-05 --artifact install/legacy-final --manifest install/legacy-final.sha256
```

Expected: all files OK；不执行 `git push` 或发布 artifact。

- [ ] **Step 5: 提交仓库内回滚记录**

```bash
git add verification/mfw/legacy-rollback.json tools/verify_mfw_evidence.py tests/test_mfw_evidence.py
git commit -m "chore: record final legacy rollback point"
```

Expected: commit does not include ignored install artifact or `uv.lock`; external artifact location remains explicit pending until user authorizes publication.

### Task 2: 写正式切换契约测试

**Files:**
- Create: `tests/test_mfw_cutover_contract.py`
- Create: `tests/test_mfw_release_workflow.py`

**Interfaces:**
- Consumes: final interface/presets、保留/退役边界。
- Produces: 在入口提升前必然失败、在两个切换提交后必然通过的生产静态契约。

- [ ] **Step 1: 写唯一入口和禁用路径测试**

```python
from pathlib import Path


FORBIDDEN_PRODUCTION_PATHS = [
    "scripts/run-all-dailies.sh", "tools/android_daily_run.py", "tools/android_run.py",
    "tools/run_cli.py", "tools/project_interface.py", "tools/configure_mfa.py",
    "agent/actions/daily_workflow.py", "agent/workflows/aggregate.py",
    "agent/workflows/maa_android.py", "assets/resource_android/pipeline/daily/daily_all.json",
]


def test_mfw_is_only_production_entry():
    assert Path("assets/interface.json").read_bytes() == Path("assets/interface.mfw.json").read_bytes()
    assert Path("tools/install.py").read_bytes() == Path("tools/mfw_install.py").read_bytes()
    for path in FORBIDDEN_PRODUCTION_PATHS:
        assert not Path(path).exists(), path


def test_current_docs_have_no_legacy_run_commands():
    current = [Path("README.md"), Path("docs/mfw-runbook.md"), Path("docs/testing/mfw-android-dailies.md")]
    forbidden = ("run-all-dailies", "android_daily_run", "configure_mfa", "MFAAvalonia", "daily_all")
    for path in current:
        text = path.read_text()
        assert not any(token in text for token in forbidden)
```

- [ ] **Step 2: 写保留工具和全预设测试**

```python
def test_one_time_android_setup_is_preserved():
    for path in [
        "agent/android/adb.py", "agent/android/avd.py", "agent/android/config.py",
        "agent/android/game.py", "agent/android/login.py", "agent/android/sdk.py",
        "tools/android_setup.py", "tools/android_device.py", "tools/capture_android_templates.py",
    ]:
        assert Path(path).is_file(), path


def test_final_interface_has_no_compatibility_task():
    text = Path("assets/interface.json").read_text()
    assert "daily_all" not in text.lower()
    assert "speedrun" not in text.lower()
    assert "MFA" not in text
```

- [ ] **Step 3: 运行测试确认先失败**

Run: `uv run --no-project --with pytest pytest tests/test_mfw_cutover_contract.py tests/test_mfw_release_workflow.py -q`

Expected: FAIL because formal interface still differs/missing, legacy entries exist and release workflow is absent.

- [ ] **Step 4: 确认失败只来自预期切换差异**

```bash
uv run --no-project --with pytest pytest tests/test_mfw_interface.py tests/test_mfw_presets.py tests/test_mfw_candidate_summary.py -q
```

Expected: PASS；新候选本身仍然完整，只有正式入口未切换。

- [ ] **Step 5: 提交失败契约测试**

```bash
git add tests/test_mfw_cutover_contract.py tests/test_mfw_release_workflow.py
git commit -m "test: define atomic MFW cutover contract"
```

### Task 3: 切换提交 1——提升新入口并删除旧生产入口

**Files:**
- Replace: `assets/interface.json` with validated `assets/interface.mfw.json`, then delete `assets/interface.mfw.json`
- Rename: `tools/mfw_install.py` to `tools/install.py`
- Delete: `assets/resource_android/pipeline/daily/daily_all.json`
- Delete: `scripts/run-all-dailies.sh`
- Delete: `tools/android_daily_run.py`
- Delete: `tools/android_daily_run.sh`
- Delete: `tools/android_run.py`
- Delete: `tools/android_run.sh`
- Delete: `tools/run_cli.py`
- Delete: `tools/project_interface.py`
- Delete: `tools/configure_mfa.py`
- Delete: `tools/setup.py`
- Delete: `tools/verify_install.py`
- Create: `.github/workflows/mfw-release.yml`
- Modify: `.github/workflows/mfw-check.yml`
- Modify: `README.md`
- Create: `docs/mfw-runbook.md`
- Create: `docs/testing/mfw-android-dailies.md`
- Modify outside repository: `/Users/gaoguobin/.codex/skills/maa-run-jianzhichuan-dailies/SKILL.md`
- Delete corresponding entry tests: `tests/test_android_daily_run.py`, `tests/test_android_run.py`, `tests/test_run_cli.py`, `tests/test_project_interface.py`, `tests/test_configure_mfa.py`, `tests/test_setup.py`, `tests/test_verify_install.py`, `tests/test_mfa_daily_contract.py`
- Modify: `tests/test_mfw_cutover_contract.py`
- Modify: `tests/test_mfw_install.py`

**Interfaces:**
- Consumes: validated candidate SHA and rollback tag/manifest。
- Produces: 正式 `assets/interface.json`、正式 `tools/install.py`、MFW-only release/run path；切换提交 1。

- [ ] **Step 1: 原样提升已经验收的入口**

```bash
python3 tools/mfw_install.py --verify-candidate install/mfw-full-candidate
cp assets/interface.mfw.json /tmp/mja-interface-validated.json
git mv tools/mfw_install.py tools/install.py
```

Use `apply_patch` to replace `assets/interface.json` with `/tmp/mja-interface-validated.json` content and delete `assets/interface.mfw.json`. Do not regenerate task ordering during cutover.

Expected: verifier proves the candidate matches current source after only documented installed-Agent normalization；formal interface is copied byte-for-byte from the verified source；installer code is unchanged except source path now reads `assets/interface.json` and CLI/help name is `install.py`.

- [ ] **Step 2: 删除旧生产入口及其直接契约测试**

Delete exactly the production scripts and corresponding tests listed in this task's Files block. Do not delete `agent/workflows/**` yet. Update `tests/test_mfw_cutover_contract.py` to read only formal files after `interface.mfw.json` and `mfw_install.py` are removed.

- [ ] **Step 3: 写 MFW-only 当前文档、运行 skill 和 release workflow**

`README.md`, `docs/mfw-runbook.md`, and the external daily skill must give this exact production flow:

```bash
python3 tools/verify_mfw_evidence.py --root verification/mfw --require-cutover-release
./install/release-final/MFW
python3 tools/mfw_profile.py run --install install/release-final --profile-name 日常-完整版
```

Document GUI manual all-select: selecting every visible task queues `GAME_START` first and then the exact 17 independent business tasks, no aggregate task exists, and every selected ID is queued once. Document local Abort continuation versus infrastructure stop, evidence locations and rollback release. The external skill must no longer run shell supervisor or old Python runners.

`.github/workflows/mfw-release.yml` resolves/builds once, runs all automated/evidence checks, rebuilds from recorded archives, verifies metadata SHA, and uploads `candidate-not-releasable` unless an Android evidence bundle matching that metadata is present. It never publishes on resolver/test/load failure.

- [ ] **Step 4: 运行切换提交 1 门禁**

```bash
uv run --no-project --with-requirements requirements.txt --with pytest --with ruff pytest tests/test_mfw_interface.py tests/test_mfw_presets.py tests/test_mfw_install.py tests/test_mfw_cutover_contract.py tests/test_mfw_release_workflow.py -q
uv run --no-project --with ruff ruff check tools/install.py tests/test_mfw_*.py
python3 tools/check_mfw_resources.py assets/resource/base
python3 tools/install.py --base-candidate install/mfw-full-candidate --output install/cutover-commit-1
python3 tools/install.py --verify-candidate install/cutover-commit-1
```

Expected: PASS；formal candidate loads；旧 production entry files absent；中央旧实现仍存在但已无正式入口。

- [ ] **Step 5: 创建切换提交 1**

```bash
git add assets/interface.json assets/tasks assets/resource/base tools/install.py tools/check_mfw_resources.py tools/mfw_release.py tools/verify_mfw_evidence.py CFA_setting.json requirements.txt .github README.md docs/mfw-runbook.md docs/testing/mfw-android-dailies.md tests
git add -u assets/interface.mfw.json assets/resource_android/pipeline/daily/daily_all.json scripts tools
git commit -m "feat: switch production control plane to MFW"
```

Expected: review `git show --stat --oneline HEAD` confirms no residual implementation deletions from `agent/workflows/**` and no `uv.lock`. Record external skill's separate file diff in the cutover evidence because it cannot be part of this repository commit.

### Task 4: 重新索引并证明旧实现入站依赖归零

**Files:**
- Create: `verification/mfw/legacy-dependency-audit.json`
- Create: `verification/mfw/legacy-graph-results.json`
- Create: `verification/mfw/legacy-delete-paths.txt`
- Create: `tools/legacy_dependency_audit.py`
- Create: `tests/test_legacy_dependency_audit.py`
- Modify: `tests/test_mfw_cutover_contract.py`

**Interfaces:**
- Consumes: 切换提交 1 的正式代码图。
- Produces: graph index ID/时间、每个旧边界的 inbound=0 结果、字符串补查结果、允许删除的精确 manifest。

- [ ] **Step 1: 重新索引当前仓库**

```text
index_repository({"repo_path":"/Users/gaoguobin/project/MJA","name":"MJA","mode":"full","persistence":true})
```

Expected: index completes against cutover commit 1; audit records indexed commit SHA.

- [ ] **Step 2: 查询旧控制面定义与入站依赖**

```text
search_graph({"project":"MJA","name_pattern":".*(Aggregate|MaaAndroidWorkflowDriver|DailyWorkflow|WorkflowEngine).*","include_connected":true,"limit":200})
trace_path({"project":"MJA","function_name":"MaaAndroidWorkflowDriver","direction":"inbound","depth":8,"include_tests":true})
trace_path({"project":"MJA","function_name":"run_selected_workflow","direction":"inbound","depth":8,"include_tests":true})
```

Expected: production inbound paths from formal interface, `agent/main.py`, tools, CI and current docs are zero. Remaining inbound paths are only files listed for second-commit deletion; preserved setup modules do not import the old workflow control plane.

- [ ] **Step 3: 补查非代码和动态字符串引用**

```bash
rg -n "daily_all|AggregateScheduler|run_selected_workflow|MaaAndroidWorkflowDriver|DailyWorkflowAction|MJA_CONTROLLER|android_daily_run|run-all-dailies|MFAAvalonia|speedrun" assets agent tools scripts .github README.md docs/mfw-runbook.md docs/testing/mfw-android-dailies.md tests
```

Expected: only negative cutover tests and soon-to-delete legacy implementation/tests match；正式 JSON/shell/CI/current docs zero positive reference.

- [ ] **Step 4: 生成可删除 manifest 与审计记录**

Save the complete MCP query results from Steps 1–2 in `legacy-graph-results.json`, including indexed commit, qualified name, inbound source path, test/production classification and hop path. Write the exact Task 5 implementation/test delete paths, one sorted repository-relative path per line, to `legacy-delete-paths.txt`. Implement `tools/legacy_dependency_audit.py` to require zero production inbound rows, run the Step 3 forbidden-string scan, verify every delete path exists, compute the path-list SHA-256, read `git rev-parse HEAD`, and atomically write `legacy-dependency-audit.json`. Add tests that reject a nonzero production inbound row, missing path, current-doc match and indexed-commit mismatch.

Run: `python3 tools/legacy_dependency_audit.py --repository . --graph-results verification/mfw/legacy-graph-results.json --delete-paths verification/mfw/legacy-delete-paths.txt --output verification/mfw/legacy-dependency-audit.json`

Expected: PASS and output records the actual full commit SHA, zero production inbound count, `retained_android_setup_imports_legacy_control_plane: false`, zero forbidden current-doc matches, path-list SHA-256 and the four graph query families.

- [ ] **Step 5: 保持审计产物未提交，供紧邻的删除提交吸收**

Run: `git status --short verification/mfw tools/legacy_dependency_audit.py tests/test_legacy_dependency_audit.py tests/test_mfw_cutover_contract.py`

Expected: audit files are the only planned uncommitted changes after cutover commit 1. Do not create an intermediate commit: Task 5 must be the immediately following commit so the switch and retirement commits remain consecutive. If any preserved production path imports old control-plane code, do not write a zero count; fix that dependency by amending cutover commit 1, rerun the index, and regenerate the audit.

### Task 5: 切换提交 2——删除残余旧实现与对应测试

**Files:**
- Create in this commit: `verification/mfw/legacy-dependency-audit.json`
- Create in this commit: `verification/mfw/legacy-graph-results.json`
- Create in this commit: `verification/mfw/legacy-delete-paths.txt`
- Create in this commit: `tools/legacy_dependency_audit.py`
- Create in this commit: `tests/test_legacy_dependency_audit.py`
- Delete: `agent/actions/`
- Delete: `agent/workflows/`
- Delete: `agent/macos/`
- Delete: `agent/sinks/`
- Delete: `agent/pretask.py`
- Delete: `agent/safety.py`
- Delete: `agent/diagnostics.py`
- Delete: `agent/android/runtime_gate.py`
- Delete: `assets/resource_android/`
- Delete: `assets/resource/calibration.json`
- Delete: `assets/resource/image/`
- Delete: `assets/resource/pipeline/`
- Delete: `native/maafw-android-cli/`
- Delete: `native/maafw-macos-fallback/`
- Delete: `verification/tasks/`
- Delete: `tools/native_bundle.py`
- Delete: `tools/request_permissions.py`
- Delete: `tools/capture_templates.py`
- Delete: `tools/verify_live_tasks.py`
- Delete: `tools/verify_macos_controller.py`
- Delete: `tools/verification_records.py`
- Delete legacy tests listed below
- Modify: `tests/test_mfw_cutover_contract.py`

**Interfaces:**
- Consumes: dependency audit whose indexed commit is cutover commit 1, the current `HEAD` before this task.
- Produces: 只含新 MFW 生产架构和保留 setup 工具的切换提交 2。

- [ ] **Step 1: 删除残余实现，保留明确 setup 边界**

Delete exactly the implementation paths in this task's Files block. Before deletion, compare the sorted path list SHA to `legacy-dependency-audit.json`; a mismatch requires rerunning Task 4. Do not delete `agent/android/{adb,avd,config,game,login,sdk}.py`, `tools/android_setup.py`, `tools/android_device.py` or `tools/capture_android_templates.py`.

- [ ] **Step 2: 删除只验证已退役实现的测试**

Delete exactly:

```text
tests/test_agent_main.py
tests/test_aggregate_report.py
tests/test_android_acceptance_contract.py
tests/test_android_daily_acceptance.py
tests/test_android_foreground_click.py
tests/test_android_native_patch_bundle.py
tests/test_android_resources.py
tests/test_android_runtime_gate.py
tests/test_capture_templates.py
tests/test_daily_workflow_action.py
tests/test_diagnostics.py
tests/test_display_contract.py
tests/test_emulator_window.py
tests/test_live_verification_records.py
tests/test_maa_android_workflow.py
tests/test_macos_foreground_click.py
tests/test_native_patch_bundle.py
tests/test_permissions.py
tests/test_pretask.py
tests/test_project_contract.py
tests/test_request_permissions.py
tests/test_restore_window_sink.py
tests/test_safety.py
tests/test_verification_contract.py
tests/test_verify_live_tasks.py
tests/test_verify_macos_controller.py
tests/test_window_lifecycle.py
tests/test_window_state.py
tests/test_workflow_aggregate.py
tests/test_workflow_catalog.py
tests/test_workflow_engine.py
tests/test_workflow_input.py
tests/test_workflow_models.py
tests/test_workflow_navigation.py
tests/workflows/
```

Keep tests for `android_adb`, `android_avd`, `android_config`, `android_game`, `android_login`, `android_sdk`, `android_sdk_install`, `android_setup`, `android_device`/capture template setup when they exercise preserved one-time setup rather than old production control.

- [ ] **Step 3: 更新切换测试为最终零残留断言**

```python
def test_legacy_implementation_roots_are_removed():
    for path in [
        "agent/actions", "agent/workflows", "agent/macos", "agent/sinks",
        "assets/resource_android", "assets/resource/image", "assets/resource/pipeline",
        "assets/resource/calibration.json", "native/maafw-android-cli",
        "native/maafw-macos-fallback", "verification/tasks",
    ]:
        assert not Path(path).exists(), path


def test_agent_is_narrow_and_setup_tools_remain():
    assert Path("agent/custom/action/guarded_input.py").is_file()
    assert Path("agent/custom/support/diagnostics.py").is_file()
    assert Path("assets/resource/base/pipeline").is_dir()
    assert Path("tools/android_setup.py").is_file()
```

- [ ] **Step 4: 运行全量测试与安装 smoke**

Run the build command below first, pause, open `install/cutover-final`, create and save `release-startup-smoke` containing only `GAME_START`, close MFW, and then continue with the profile command. Do not run the block unattended.

```bash
uv run --no-project --with-requirements requirements.txt --with pytest --with ruff pytest -q
uv run --no-project --with ruff ruff check .
python3 tools/check_mfw_resources.py assets/resource/base
python3 tools/verify_mfw_evidence.py --root verification/mfw --require-all-tasks --require-full-preset --require-manual-all
python3 tools/install.py --base-candidate install/mfw-full-candidate --output install/cutover-final
python3 tools/install.py --verify-candidate install/cutover-final
python3 tools/mfw_profile.py run --install install/cutover-final --profile-name release-startup-smoke
git diff --check
```

Expected: all PASS；candidate loads formal interface/resource/Agent；startup smoke succeeds；旧 production symbols absent。

- [ ] **Step 5: 创建切换提交 2**

```bash
git add -u agent assets native tools verification tests
git add verification/mfw/legacy-dependency-audit.json verification/mfw/legacy-graph-results.json verification/mfw/legacy-delete-paths.txt tools/legacy_dependency_audit.py tests/test_legacy_dependency_audit.py tests/test_mfw_cutover_contract.py
git commit -m "refactor: retire legacy MJA orchestration"
```

Expected: `git log -2 --oneline` shows retirement commit immediately above production switch commit; both remain independently revertible. `uv.lock` is not staged.

### Task 6: 重建最终候选并验证两个切换提交共同发布

**Files:**
- Create: `verification/mfw/cutover-release.json`
- Modify: `tools/verify_mfw_evidence.py`
- Modify: `tests/test_mfw_release_workflow.py`

**Interfaces:**
- Consumes: 切换提交 1、依赖审计、切换提交 2 和旧 rollback manifest。
- Produces: 绑定最终 commit、两切换 commit、MFW/Maa hashes 和 smoke evidence 的本地 release manifest。

- [ ] **Step 1: 写两提交共同发布测试**

```python
def test_release_manifest_contains_both_atomic_cutover_commits():
    manifest = load_json("verification/mfw/cutover-release.json")
    assert manifest["switch_commit"]
    assert manifest["retirement_commit"]
    assert manifest["switch_commit"] != manifest["retirement_commit"]
    assert manifest["candidate_commit"] == git_head()
    assert manifest["rollback"]["tag"] == "mja-legacy-final-2026-08-05"
    assert manifest["publish_status"] == "local-validated-not-published"
```

- [ ] **Step 2: 运行测试确认 release manifest 缺失**

Run: `uv run --no-project --with pytest pytest tests/test_mfw_release_workflow.py -q`

Expected: FAIL because final release manifest does not exist.

- [ ] **Step 3: 从最终代码重新构建，不复用切换前目录**

```bash
python3 tools/install.py --base-candidate install/mfw-full-candidate --output install/release-final
python3 tools/install.py --verify-candidate install/release-final
shasum -a 256 install/release-final/build-metadata.json
python3 tools/verify_mfw_evidence.py --root verification/mfw --cutover-release-output verification/mfw/cutover-release.json
```

Verifier requires final candidate commit to contain both named ancestor commits, audit manifest hash to match deleted paths, old rollback manifest to verify, and full/manual evidence compatibility with the promoted resources. `publish_status` remains `local-validated-not-published`.

- [ ] **Step 4: 执行最终 MFW Android smoke**

Open `install/release-final` once, create and save profile `日常-完整版` with startup followed by the exact 17 business tasks, then close MFW before running the command. The new release candidate intentionally does not inherit profiles from the frozen base.

```bash
python3 tools/mfw_profile.py run --install install/release-final --profile-name 日常-完整版
python3 tools/verify_mfw_evidence.py --root verification/mfw --require-cutover-release
```

Expected: 在正式布局且无 supervisor 下启动；17 项各一次；结果写入 cutover-release evidence。若当天副作用已完成，应由画面得到 already_complete/not_eligible，而非本地计数跳过。

- [ ] **Step 5: 提交最终本地发布记录**

```bash
git add verification/mfw/cutover-release.json tools/verify_mfw_evidence.py tests/test_mfw_release_workflow.py
git commit -m "test: validate final MFW cutover release"
```

Expected: 不推送、不创建远端 release；等待用户明确发布授权。

### Task 7: 最终生产和回滚演练

**Files:**
- Modify: `docs/mfw-runbook.md`
- Create: `verification/mfw/rollback-drill.json`
- Modify: `tests/test_mfw_cutover_contract.py`

**Interfaces:**
- Consumes: final MFW release directory 和 legacy rollback directory/tag。
- Produces: 可操作、已实际演练的整包回滚步骤。

- [ ] **Step 1: 写 runbook 命令契约测试**

```python
def test_runbook_documents_whole_release_rollback_only():
    text = Path("docs/mfw-runbook.md").read_text()
    assert "mja-legacy-final-2026-08-05" in text
    assert "git revert" in text
    assert "运行时双栈" not in text
    assert "tools/install.py" in text
    assert "日常-完整版" in text
```

- [ ] **Step 2: 运行测试确认演练记录缺失**

Run: `uv run --no-project --with pytest pytest tests/test_mfw_cutover_contract.py -q`

Expected: FAIL until runbook and rollback drill evidence are complete.

- [ ] **Step 3: 在隔离目录演练旧产物与新产物启动**

Open `install/release-final`, create and save `release-startup-smoke` containing only `GAME_START`, and close MFW. This profile is mutable operator state and is not part of candidate identity.

```bash
(cd install/legacy-final && shasum -a 256 -c ../legacy-final.sha256)
python3 tools/mfw_profile.py run --install install/release-final --profile-name release-startup-smoke
```

For the legacy artifact, run its read-only verify/smoke entry without executing destructive business actions. Record exact commands, exit codes, tag commit, manifests and log paths in `rollback-drill.json`.

- [ ] **Step 4: 更新 runbook 并运行最终审计**

```bash
uv run --no-project --with-requirements requirements.txt --with pytest --with ruff pytest -q
uv run --no-project --with ruff ruff check .
rg -n "daily_all|AggregateScheduler|MaaAndroidWorkflowDriver|DailyWorkflowAction|MJA_CONTROLLER|MFAAvalonia|speedrun" assets agent tools scripts .github README.md docs/mfw-runbook.md docs/testing/mfw-android-dailies.md
git status --short --branch
```

Expected: tests/lint pass；forbidden production search has only explicit negative-test matches outside searched production roots or zero matches；`uv.lock` remains user-untracked.

- [ ] **Step 5: 提交回滚演练记录**

```bash
git add docs/mfw-runbook.md verification/mfw/rollback-drill.json tests/test_mfw_cutover_contract.py
git commit -m "docs: record MFW production rollback drill"
```

## 切换完成门

- [ ] 正式 `assets/interface.json` 和 `tools/install.py` 来自已验收候选，临时源文件已删除。
- [ ] GUI 只有 17 个独立业务任务和预设，不存在 `daily_all`；手工全选每项一次。
- [ ] MFW 是 README、runbook、CI、release workflow 和运行 skill 的唯一生产入口。
- [ ] 旧 production entry 在切换提交 1 删除，残余旧实现在 graph inbound=0 后由切换提交 2 删除。
- [ ] 一次性 Android setup 工具及测试保留，生产 Agent 只剩 `agent/custom` 窄能力。
- [ ] 两个切换提交共同存在于最终候选，自动化、资源加载、embedded Agent、Android full smoke 全部通过。
- [ ] 旧 tag/产物 SHA 和回滚演练有效；当前代码没有运行时双栈。
- [ ] 远端发布仍需用户明确授权，未授权时状态保持 `local-validated-not-published`。
