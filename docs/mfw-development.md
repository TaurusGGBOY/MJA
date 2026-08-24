# MFW 开发与验收

MJA 的正式执行面是 MFW + Android 模拟器 + ADB Controller。MFW 是任务状态的唯一拥有者，Agent 和 pipeline 不得建立第二套业务结果模型。

## 原生状态契约

MFW 对外保留五个原始状态：

| 状态 | 含义 |
| --- | --- |
| `Invalid` | 任务不存在或句柄无效 |
| `Pending` | 已排队、尚未执行 |
| `Running` | 正在执行 |
| `Succeeded` | 成功终态；包括本次完成和发现已经完成 |
| `Failed` | 失败终态；包括显式业务失败和框架执行失败 |

验收前必须显式声明期望终态，例如 `TASK_ID=Succeeded`。验收只核对本次运行产生的 MFW 原生终态事件；截图、节点轨迹、日志和后置条件用于定位问题，不参与改写终态。普通业务任务失败继续队列，只有 `GAME_START` 失败才停止后续队列。

业务失败节点使用无状态 `FailTask`，不接收状态参数、不写结果文件，也不连接 `next`、`on_error` 或 `external`。`on_error` 默认省略；保留项只能是 Maa_bbb 风格的、有边界的任务内恢复。

失败传播的离线探针仍使用 `failure-contract.json` 验证无状态 `FailTask` 和普通失败后的队列继续执行；它只验证控制流，不生成或读取业务结果文件。

## 组装候选

安装器从官方 MFW 与 MaaFramework release 组装新的 macOS arm64 候选，并记录 MJA commit、release 资产和 SHA-256：

```bash
python3 tools/mfw_install.py \
  --output install/mfw-native-status-20260820 \
  --commit "$(git rev-parse HEAD)"
python3 tools/mfw_install.py \
  --verify-candidate install/mfw-native-status-20260820
python3 tools/check_mfw_resources.py \
  install/mfw-native-status-20260820/resource/base --task-entry-gate
```

候选必须从官方归档开始组装，不使用旧候选作为 base。候选包一旦开始运行就不再编辑。Android 模拟器仍必须使用 `-gpu host`，AVD 保持 `hw.gpu.enabled=yes` 和 `hw.gpu.mode=host`。

若官方归档、构件布局、资源门禁或运行证据任一项不满足，候选状态标记为 `candidate-not-releasable`，不得发布。MacOS 候选只能在当前执行环境中验证，禁止通过脚本手动启动 Terminal.app；需要人工查看时直接提供日志路径。

## 精确 pair profile

每次单任务验收只选择 `GAME_START + 一个业务任务`。可以先为每个任务生成精确 profile：

```bash
python3 tools/mfw_profile.py ensure-pair-profiles \
  --install install/mfw-native-status-20260820
```

profile 只声明 MFW 任务和顺序，不在 Agent 或外部 supervisor 中重建队列。`WEEKLY_FREE_GIFT_DAILY` 每天都可生成和运行；如果页面已经显示已领取，仍应以原生 `Succeeded` 结束。

## 原生终态验收

在启动 MFW 前创建 ticket，并声明期望终态：

```bash
ticket=$(python3 tools/mfw_live_acceptance.py begin \
  --candidate install/mfw-native-status-20260820 \
  --owner "$WORKER" \
  --selected-task BUY_TEA_DAILY \
  --expect-terminal BUY_TEA_DAILY=Succeeded)
```

随后从候选目录直接运行 MFW，并只勾选 `GAME_START` 与声明的业务任务。运行完成后：

```bash
python3 tools/mfw_live_acceptance.py finish \
  --ticket "$ticket" \
  --record verification/mfw/20260820-native-status/BUY_TEA_DAILY.json
```

`finish` 返回 0 且原生终态与启动前声明一致，才算该 pair 验收完成。预期失败时传入 `TASK_ID=Failed`；不要通过修改任务名、命中节点或截图来替代终态声明。

## 离线检查

每次修改资源、Agent 或安装器后至少运行：

```bash
python3 tools/check_mfw_resources.py assets/resource/base --task-entry-gate
install/.venv/bin/python -m pytest tests/mfw -q
install/.venv/bin/python -m pytest -q
git diff --check
```

构建完整候选时还要运行 `tools/mfw_artifact_verification.py` 所覆盖的候选来源、包布局、回滚完整性和官方任务流检查。不要把诊断材料当作任务状态，也不要让构建工具改写仓库中的 `uv.lock`。
