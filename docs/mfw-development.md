# MFW 并行开发与验收

MFW 迁移目前在隔离目录中进行，尚未替换旧的正式入口。当前候选面向 macOS arm64，使用 MFW 的 MacOS Controller 连接本机运行的 iOS App；它不能被解释为已经完成生产切换。

目标应用是 App Store 的 iOS 包（`CFBundleSupportedPlatforms=iPhoneOS`、支持 `MacFamily20,1`），不是 PlayCover 包。运行候选前必须手动启动 `/Applications/对决！剑之川.app` 并保持窗口可匹配；MaaFramework 的 MacOS controller 不支持 `StartApp`，启动 Pipeline 只负责识别加载页、已知弹窗和主页收敛。

## 组装候选

安装器每次只解析一个最新正式 MFW 与 MaaFramework release，并把它们、ProjectInterface、资源和 embedded Agent 组装到一个新目录：

```bash
python3 tools/mfw_install.py --output install/mfw-foundation-candidate
python3 tools/mfw_install.py --verify-candidate install/mfw-foundation-candidate
uv run --no-project --with-requirements requirements.txt \
  python tools/load_mfw_resource.py install/mfw-foundation-candidate
python3 tools/check_mfw_resources.py install/mfw-foundation-candidate/resource/base
```

当前 MFW-PyQt6 macOS 包是 PyInstaller 布局：`MFW`、`_internal/Python`、`_internal/maa` 和 `maafw` 同级。`CFA_setting.json` 的 `embedded: true` 与 `agent.child_args` 的 `{PROJECT_DIR}/agent/main.py` 共同启用 MFW 内置 Agent；不应再假设存在 `python/bin/python3`。

候选的 `build-metadata.json` 记录 MJA commit、两个 release 资产和 SHA-256。候选目录内的 `config/` 是 MFW 的可变配置状态，不属于运行时身份；创建后续 live candidate 时使用 `--base-candidate`，不要修改冻结的基础候选。

## 配置档案与直接运行

`tools/mfw_profile.py` 可以离线补齐并注册每个 active 任务的精确
`GAME_START + 一个业务任务` 档案，也可以直接运行已保存档案。候选组装时安装器
会自动执行同样的补齐；手动启动前无需打开 GUI 重新勾选：

```bash
python3 tools/mfw_profile.py ensure-pair-profiles \
  --install install/mfw-foundation-candidate
```

命令输出 `task_id -> profile_name` 映射，随后直接运行对应档案：

```bash
python3 tools/mfw_profile.py run \
  --install install/mfw-failure-probe \
  --profile-name live-failure-contract
```

运行参数固定为 MFW 的 `--config-id=<id> --direct-run`。配置档案应明确列出要验证的任务和顺序；不要用外部 supervisor 或在 Agent 中重新建立任务队列。

## 失败传播探针

探针候选由经过验证的基础候选派生，业务失败节点显式进入 `MJA_COMMON_ABORT`，随后执行哨兵任务；探针文件只允许出现在隔离候选：

```bash
python3 tools/mfw_probe_install.py \
  --base install/mfw-foundation-candidate \
  --output install/mfw-failure-probe
python3 tools/check_mfw_resources.py install/mfw-failure-probe/resource/base
```

只有真实 MFW UI/log 证明 `Abort` 后哨兵仍执行，且 Controller、Resource、Agent、runtime 和设备失联会停止队列，才可以填写 `verification/mfw/failure-contract.json`。填写后必须运行：

```bash
python3 tools/verify_mfw_evidence.py \
  --failure-contract verification/mfw/failure-contract.json
```

没有真实 MacOS controller 连接、当前候选元数据链接或失败传播日志时，不得创建伪证据，也不得把 CI 的 `candidate-not-releasable` artifact 发布为正式版本。

## 全量候选摘要

只有 17 个单项证据、`full-preset`、手工全选、同日重跑、业务 Abort 继续和
Controller 断开停止全部由同一 `install/mfw-full-candidate` 通过验证后，才允许生成候选摘要：

```bash
python3 tools/verify_mfw_evidence.py \
  --root verification/mfw \
  --require-all-tasks --require-full-preset --require-manual-all \
  --write-summary verification/mfw/candidate-summary.json
```

摘要绑定 `build-metadata.json`、payload SHA、MFW/Maa 版本、macOS/iOS
`ScreenCaptureKit` Controller 和所有证据文件 SHA-256。任一证据缺失、哈希不一致或
候选不是 `mfw-full-candidate` 时，命令失败且不产生可用摘要；在此之前不得切换
`assets/interface.json` 或退役旧入口。

## Fixture 与变更门禁

Fixture 捕获只读取人工准备好的画面并保存新文件，不发送输入：

```bash
python3 tools/capture_mfw_fixture.py \
  --controller macos --window-id WINDOW_ID \
  --task-id MAIL_REWARD_DAILY --case not_eligible
```

捕获工具默认使用当前 MFW 目标的 macOS Controller，要求窗口已经由用户打开、Screen Recording/Accessibility 权限已授予，并且 Maa 输出严格为资源使用的 `1280×720`。它只截图、不发送输入、拒绝覆盖已有文件；观测到 `923×720` 或 TCC 拒绝时必须停止并先修复窗口/权限，不能把该帧登记为 MFW fixture。旧 Android 路径只有显式传入 `--controller android --config PATH` 才可用。

每次修改 MFW 基座、资源或 Agent 后，至少运行：

```bash
python3 -m pytest tests/test_mfw_*.py tests/test_capture_mfw_fixture.py -q
uv tool run --from ruff ruff check agent/custom tools tests/mfw tests/test_mfw_*.py tests/test_capture_mfw_fixture.py
git diff --check
```

不要让构建工具生成或改写仓库中的 `uv.lock`；它不是这条迁移链路的发布输入。
