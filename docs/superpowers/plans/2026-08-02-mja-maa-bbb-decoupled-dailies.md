# MJA MAA_BBB-Style Decoupled Dailies Implementation Plan

> 这是仓库内的普通实施计划。按下面的任务顺序执行，每个阶段都必须以代码、资源或实机证据关闭；不依赖任何未授权的外部 skill 或子代理流程。

**Goal:** 将《对决！剑之川》17 个 canonical 日常改造成 Maa 原生独立任务，由独立游戏就绪 Pipeline 和外部监督器编排，使任一任务局部失败都不会取消后续任务，并让 2026-08-03 周一的 17 项任务从标题页一次性全部得到成功终态。

**Architecture:** 采用 MAA_BBB 的“独立 task entry + preset + Pipeline 局部恢复”控制面，不再用一个 `AggregateDailyWorkflowAction` 包住全部任务。Python 保留批次监督、结构化结果、诊断和受保护资源决策；普通导航、识别、点击、回退与回主页迁入各任务 Maa Pipeline。每个业务任务由独立 MaaPiCli 子任务执行，启动/恢复由 `MJA_Game_Ready` 单独完成。

**Tech Stack:** Python 3.12+、MaaFramework v5 Pipeline/Agent、Maa Android ADB Controller、MaaPiCli、pytest、Ruff、JSON/JSONC resources、Android 35 AVD `mja-api35-apis`、1280×720 游戏画面。

## Global Constraints

- 所有游戏画面输入必须通过 MaaFramework Android ADB Controller；禁止 Computer Use、macOS 点击和裸 `adb shell input`。
- Android 进程生命周期操作可以使用现有 `AdbDevice.start_app()`/`restart()`；不得清除数据、卸载游戏、重置 AVD 或丢失登录态。
- `MAIL_REWARD_DAILY` 和任何其他业务任务都不得承担批次首次启动职责。
- 每个 canonical task 必须拥有独立 Maa entry、独立子任务结果、独立诊断目录和独立终态。
- 任务局部 `failed`，或已离开阻塞页面的任务局部 `blocked_safety`，必须被记录但不得取消后续安全任务；仍覆盖全屏的登录、支付、验证或未知安全弹窗属于 `FailureDomain.SAFETY`，在只读复核后终止批次并保留剩余 ID。
- 设备永久不可用、登录/验证码、支付或无法识别的安全弹窗是环境/安全失败，不允许通过猜测输入绕过。
- 业务消费动作不得盲重试；无输入的截图、OCR、渲染等待、Maa/ADB 传输可按明确错误类型有限重试。
- 禁止对子进程调用无期限 `wait()`；每个业务 entry 使用 catalog 中的硬超时，`MJA_Game_Ready` 为 300 秒，`MJA_Game_Recover` 为 180 秒，超时只终止当前 MaaPiCli 子进程并进入恢复/续跑逻辑。
- 原始异常类型、消息、稳定错误码、失败阶段和 traceback path 必须保存；不得统一改写为 `WORKFLOW_DRIVER_FAILED`。
- 每个 `run.json` 在进程退出前必须处于终态；`status=running` 是发布阻断错误。
- 自动测试必须包含“第一项失败而后续全部仍被调用”的故障注入。
- 关键视觉识别必须用真实 1280×720 截图和现场 `--preflight-only` 验证；只检查 JSON 字段不算视觉验收。
- source、`install/agent` 与 `install/resource_android` 必须在正式运行前通过 digest 一致性检查。
- 2026-08-02 周日正式目录为 16 项；2026-08-03 周一必须加入 `WEEKLY_FREE_GIFT_MONDAY`，正式目录为 17 项。
- 最终通过只接受：CLI 退出码 0、batch `status=completed`、所有 eligible task 为 `completed/already_complete/not_eligible`、`remaining_task_ids=[]`、`stop_reason=null`、无悬挂 diagnostics。
- 保留当前工作树中的用户修改；不得覆盖或提交 `.codebase-memory/*`、`AGENTS.md`、`agent/android/avd.py`、`agent/android/config.py`、`tests/test_android_avd.py`、`tests/test_android_config.py`、`uv.lock`，除非后续用户另行授权。

## Current Evidence Gate (2026-08-03)

这份计划当前是“待执行改造计划”，不是完成声明。当前审计 HEAD 为 `a00dc8c`；最新可验证
的周一全量批次 `20260803T032549812529+0800` 已调度 17 项并清空
`remaining_task_ids`，但 CLI 退出码为 1，结果为 11 项完成/已完成、1 项不适用、5 项失败。
此外，`COLLECTION_DEPLOYMENT_DAILY`、`EAT_STAMINA_FOOD_DAILY`、
`BATTLE_PASS_REWARD_DAILY` 的结果虽被标成成功，最后页面分别仍为 `collection`、`food`、
`rewards`，没有满足统一 `home` 交接边界。因此当前实现仍有以下未解决问题：

| 现场证据 | 根因类别 | 必须先完成的计划任务 |
|---|---|---|
| 历史运行中标题页只有包名前台条件，业务任务才首次尝试启动 | 游戏就绪定义错误 | Task 4，再进入 Task 5 |
| `WEEKLY_FREE_GIFT_MONDAY` 在 `weekly` 超时 | 任务页识别/局部恢复不足 | Task 7 |
| `COLLECTION_DEPLOYMENT_DAILY` 在 `collection` 以 `TASK_BOUNDARY_RETURN_FAILED` 结束 | 任务结束边界属于共享清理 | Task 7 |
| `HERO_DISPATCH_DAILY` 在 `painting` 变成 `WORKFLOW_DRIVER_FAILED` | 共享 Python driver 与异常泛化 | Task 2、Task 7 |
| `MARTIAL_STUDY_BREAKTHROUGH_DAILY` 缺少 `function_panel.page` 后置条件 | 任务状态机与页面证据不一致 | Task 8 |
| 历史批次曾以 `WORKFLOW_TIMEOUT` 截断并留下后缀任务；最新批次虽清空队列但仍有 5 项失败 | 聚合器、子任务生命周期和恢复共用失败域 | Task 3、Task 5、Task 6 |
| 历史取证中 `EAT_STAMINA_FOOD_DAILY` 曾留下 `run.json: running`，单项内部预算为 600 秒 | 没有父级 MaaPiCli 硬超时和终态兜底 | Task 2、Task 3、Task 5 |
| 05:15 邮件 canary 已从标题页进入游戏并完成 `open_function_panel`、`open_mail`，随后在 300 秒业务子进程预算内以 `WORKFLOW_TIMEOUT` 失败 | `MJA_Game_Ready` 仍嵌在业务 task 的边界恢复中，启动/业务/恢复共用预算；邮件没有完成可领取或已读后置分支 | Task 3、Task 4、Task 5、Task 7 |

执行顺序必须固定为：

1. 先锁定失败域、异常字段和诊断终态（Task 1–2）；
2. 再建立一次 AVD 会话内的独立 MaaPiCli 子进程和硬超时；启动、业务和恢复使用独立预算（Task 3）；
3. 单独把标题页到主页做成 `MJA_Game_Ready`，将业务计时起点定义为已验证主页，并完成 10 次冷启动预检（Task 4）；
4. 建立 supervisor 的“任务失败—冻结证据—验证恢复—继续下一项”闭环（Task 5）；
5. 切断 `MJA_Daily_All` 生产入口，改为独立 entry/preset（Task 6）；
6. 按“免费/无副作用 → 消费动作 → 战斗循环”迁移任务（Task 7–9）；
7. 删除旧 driver 生产调用链，更新 runbook 和 `maa-run-jianzhichuan-dailies` skill（Task 10–11）；
8. 只在所有单任务 canary、故障注入和资源加载门禁通过后，执行周一 17 项全量验收（Task 12）。

任何一步失败都只能回到该步骤对应的证据目录修复；不得用提高全局超时、重复消费动作或重新从首项盲跑来代替隔离改造。最新全量批次的“队列清空”只能关闭调度隔离门，不能关闭业务成功门。

---

## Target Architecture

```text
scripts/run-all-dailies.sh
        │
        ▼
DailySupervisor ──────────────── batch checkpoint/report
        │
        ├── MJA_Game_Ready (独立 Maa task)
        │       └── title / loading / known popup -> verified home
        │
        ├── MaaPiCli task: MAIL_REWARD_DAILY
        │       └── task-owned navigation -> business -> task-owned return -> result
        │
        ├── MaaPiCli task: SHOP_FREE_GIFT_DAILY
        │
        ├── ... one process/task result per canonical task ...
        │
        └── MaaPiCli task: BATTLE_PASS_REWARD_DAILY

task-local failure
        └── freeze evidence -> MJA_Game_Ready recovery -> continue next task
```

任务之间允许共享设备、主页和通用恢复节点，但不共享一个业务 CustomAction、一个可变 driver 状态或一个“首错即停”的调用栈。

## File Map

| File | Responsibility |
|---|---|
| `agent/daily/__init__.py` | 导出独立批次监督接口。 |
| `agent/daily/models.py` | `FailureDomain`、`RecoveryStatus`、`RecoveryExecution`、`TaskExecution` 和批次序列化模型。 |
| `agent/daily/supervisor.py` | 日期过滤、逐任务独立执行、恢复、checkpoint 和最终状态。 |
| `agent/android/session.py` | 一次准备 AVD/device/package，并为每个 entry 启动独立 MaaPiCli。 |
| `tools/android_run.py` | 复用 `AndroidSession` 执行一个 Maa task，不再独占全量编排。 |
| `tools/android_daily_run.py` | 提供 `--preflight-only`、多 `--task`、全量 supervisor 和结果审计。 |
| `scripts/run-all-dailies.sh` | 稳定的一条命令入口。 |
| `agent/errors.py` | 为 task/session/runtime/safety 失败提供不丢失根因的稳定错误码。 |
| `agent/workflows/models.py` | 扩展 `TaskResult` 的原始错误字段并保持 JSON 兼容。 |
| `agent/diagnostics.py` | 所有异常路径 finalize task run。 |
| `agent/actions/task_result.py` | 小型 `RecordTaskResult` CustomAction，仅记录终态。 |
| `agent/actions/protected_action.py` | 对少数资源消费动作执行同帧 policy 授权。 |
| `agent/actions/daily/jianlin_planner.py` | 只保留剑林挑战次数与倍率的纯计算及无输入 Pipeline override。 |
| `agent/actions/daily_workflow.py` | 迁移期兼容单任务；最终移除 aggregate 生产路径。 |
| `agent/workflows/aggregate.py` | 迁移为报告模型兼容层，不再调度游戏任务。 |
| `agent/workflows/engine.py` | 迁移期保留；全部任务转为 Pipeline 后退出生产调用链。 |
| `agent/workflows/maa_android.py` | 迁移期拆分；删除启动职责和全任务中央 `return_to_home()`。 |
| `assets/resource_android/pipeline/game_ready.json` | 标题页、加载页、已知安全弹层和主页就绪 Pipeline。 |
| `assets/resource_android/pipeline/navigation_common.json` | 只包含真正通用的主页识别、通用返回与安全阻塞识别。 |
| `assets/resource_android/pipeline/daily/*.json` | 17 个任务各自完整控制流、局部恢复和终态记录。 |
| `assets/resource_android/image/game_ready/*` | 标题页稳定复合识别模板。 |
| `assets/interface.json` | 独立启动任务、17 个独立任务和 MAA_BBB 风格 preset。 |
| `tools/capture_templates.py` | 增加 Android game-ready 模板捕获 profile/CLI。 |
| `tools/verify_install.py` | Maa resource bundle、source/install digest 和生产入口检查。 |
| `docs/runbooks/android-daily-one-shot.md` | 仓库内唯一运行与验收真值。 |
| `/Users/gaoguobin/.codex/skills/maa-run-jianzhichuan-dailies/SKILL.md` | 变成调用 runbook/supervisor 的薄 skill。 |

## Core Interfaces

```python
class FailureDomain(StrEnum):
    TASK = "task"
    SESSION = "session"
    RUNTIME = "runtime"
    SAFETY = "safety"


class RecoveryStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED_SAFETY = "blocked_safety"


@dataclass(frozen=True)
class RecoveryExecution:
    entry_name: Literal["MJA_Game_Ready", "MJA_Game_Recover"]
    status: RecoveryStatus
    child_exit_code: int
    failure_domain: FailureDomain | None
    run_directory: Path
    error_code: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    failure_stage: str | None = None
    traceback_path: str | None = None


@dataclass(frozen=True)
class TaskExecution:
    task_id: str
    result: TaskResult
    child_exit_code: int
    failure_domain: FailureDomain | None
    run_directory: Path


class DailyExecutor(Protocol):
    def preflight(self) -> RecoveryExecution: ...
    def run_task(self, task_id: str) -> TaskExecution: ...
    def recover_game_ready(self) -> RecoveryExecution: ...
    def repair_runtime(self) -> RecoveryExecution: ...


class AndroidSession:
    def __init__(
        self,
        config: AndroidConfig,
        *,
        install_root: Path,
        runner: Callable[..., Any],
        spawn: Callable[..., Any] | None,
    ) -> None: ...
    def prepare(self) -> None: ...
    def run_maa_task(
        self,
        task_name: str,
        *,
        run_id: str,
        timeout_seconds: int,
    ) -> TaskExecution: ...
    def run_game_ready(
        self,
        entry_name: Literal["MJA_Game_Ready", "MJA_Game_Recover"],
        *,
        run_id: str,
    ) -> RecoveryExecution: ...
    def recover_game_ready(self, *, cold_start: bool = False) -> RecoveryExecution: ...
    def close(self, *, stop_avd: bool = False) -> None: ...


class DailySupervisor:
    def __init__(
        self,
        executor: DailyExecutor,
        task_order: Sequence[str] = WORKFLOW_DEFINITION_ORDER,
    ) -> None: ...

    def run(
        self,
        selected_task_ids: Sequence[str] | None = None,
        *,
        day: date | None = None,
        checkpoint: Callable[[AggregateResult], None] | None = None,
    ) -> AggregateResult: ...
```

`DailySupervisor.run()` 的控制规则固定为：

```python
task_execution = executor.run_task(task_id)
results.append(task_execution.result)
checkpoint_now()
if task_execution.result.status in SUCCESSFUL_TASK_STATUSES:
    continue
recovery = executor.recover_game_ready()
record_recovery(recovery)
if recovery.status is RecoveryStatus.COMPLETED:
    continue
handle_environment_or_safety_failure(recovery)
```

它不得在普通 `TaskStatus.FAILED` 分支直接 `return`。

---

### Task 1: Lock the Failure-Isolation Contract with Failing Tests

**Files:**

- Create: `tests/test_daily_supervisor.py`
- Modify: `tests/test_workflow_aggregate.py`
- Modify: `tests/test_android_daily_run.py`
- Modify: `tests/test_project_interface.py`

**Interfaces:**

- Produces the non-negotiable test contract for independent task invocation.
- Does not change production behavior yet.

- [ ] **Step 1: Add a first-task failure injection.**

```python
def task_execution(task_id: str, status: TaskStatus) -> TaskExecution:
    failed = status is TaskStatus.FAILED
    return TaskExecution(
        task_id=task_id,
        result=TaskResult(
            task_id=task_id,
            status=status,
            postcondition="fault_injected" if failed else "already_complete",
            action_counts={},
            error_code="WORKFLOW_TIMEOUT" if failed else None,
        ),
        child_exit_code=1 if failed else 0,
        failure_domain=FailureDomain.TASK if failed else None,
        run_directory=Path("runs") / task_id,
    )


def recovery_execution(entry_name: str = "MJA_Game_Recover") -> RecoveryExecution:
    return RecoveryExecution(
        entry_name=entry_name,
        status=RecoveryStatus.COMPLETED,
        child_exit_code=0,
        failure_domain=None,
        run_directory=Path("runs") / entry_name,
    )


@dataclass
class FakeDailyExecutor:
    statuses: Mapping[str, TaskStatus]
    calls: list[str] = field(default_factory=list)

    def preflight(self) -> RecoveryExecution:
        self.calls.append("preflight")
        return recovery_execution("MJA_Game_Ready")

    def run_task(self, task_id: str) -> TaskExecution:
        self.calls.append(f"task:{task_id}")
        return task_execution(task_id, self.statuses[task_id])

    def recover_game_ready(self) -> RecoveryExecution:
        self.calls.append("recovery")
        return recovery_execution()

    def repair_runtime(self) -> RecoveryExecution:
        self.calls.append("runtime_repair")
        return recovery_execution()


def test_task_local_failure_does_not_suppress_remaining_tasks():
    executor = FakeDailyExecutor(
        {
            task_id: TaskStatus.FAILED
            if task_id == IDS[0]
            else TaskStatus.ALREADY_COMPLETE
            for task_id in IDS
        }
    )

    result = DailySupervisor(executor=executor, task_order=IDS).run(
        day=date(2026, 8, 3)
    )

    assert [call.removeprefix("task:") for call in executor.calls if call.startswith("task:")] == list(IDS)
    assert [item.task_id for item in result.task_results] == list(IDS)
    assert result.remaining_task_ids == ()
    assert result.status is AggregateStatus.COMPLETED_WITH_TASK_FAILURES
```

- [ ] **Step 2: Add a recovery-order test.**

```python
def test_next_task_starts_only_after_verified_recovery():
    task_ids = ("MAIL_REWARD_DAILY", "SHOP_FREE_GIFT_DAILY")
    executor = FakeDailyExecutor(
        {
            "MAIL_REWARD_DAILY": TaskStatus.FAILED,
            "SHOP_FREE_GIFT_DAILY": TaskStatus.ALREADY_COMPLETE,
        }
    )

    DailySupervisor(executor=executor, task_order=task_ids).run(
        day=date(2026, 8, 3)
    )

    assert executor.calls == [
        "preflight",
        "task:MAIL_REWARD_DAILY",
        "recovery",
        "task:SHOP_FREE_GIFT_DAILY",
    ]
```

The second task may start only after recovery returns verified `home`.

- [ ] **Step 3: Replace the current fail-fast assertion.**

Delete the assertion that expects `calls == ["MAIL_REWARD_DAILY"]`. Keep a legacy report-deserialization test for old `failed_task` JSON, but no production scheduler test may require ordinary task failure to leave a non-empty suffix.

- [ ] **Step 4: Add production-entry assertions.**

Assert that the final interface/run path exposes independent task names and a preset, and that `scripts/run-all-dailies.sh` does not select `MJA_Daily_All`.

- [ ] **Step 5: Run and confirm the new tests fail for the intended reasons.**

Run:

```bash
./install/.venv/bin/python -m pytest -q \
  tests/test_daily_supervisor.py \
  tests/test_workflow_aggregate.py \
  tests/test_android_daily_run.py \
  tests/test_project_interface.py
```

Expected before implementation: missing `agent.daily`, current first-failure early return, and current `daily_all` entry assertions fail.

- [ ] **Step 6: Commit only the red contract tests.**

```bash
git add -- tests/test_daily_supervisor.py tests/test_workflow_aggregate.py \
  tests/test_android_daily_run.py tests/test_project_interface.py
git commit -m "test: require isolated daily task execution"
```

### Task 2: Make Task Results Truthful and Diagnostics Terminal

**Files:**

- Modify: `agent/errors.py`
- Modify: `agent/workflows/models.py`
- Modify: `agent/diagnostics.py`
- Modify: `agent/workflows/engine.py`
- Modify: `agent/actions/daily_workflow.py`
- Modify: `agent/workflows/aggregate.py`
- Modify: `agent/workflows/aggregate_report.py`
- Modify: `tests/test_workflow_models.py`
- Modify: `tests/test_diagnostics.py`
- Modify: `tests/test_workflow_engine.py`
- Modify: `tests/test_daily_workflow_action.py`
- Modify: `tests/test_aggregate_report.py`

**Interfaces:**

- Extends `TaskResult` with exact optional failure metadata.
- Guarantees that a started diagnostic run always reaches a terminal JSON state.

- [ ] **Step 1: Add exact error fields to the model tests.**

Add `TaskStatus.BLOCKED_SAFETY = "blocked_safety"`. Add optional
`error_type`, `error_message`, `failure_stage`, and `traceback_path` fields to
`TaskResult`; keep the existing `error_code` field. `TaskResult.as_dict()` must
always serialize all five error fields so readers never have to infer schema
from success or failure.

The serialized failure shape must be:

```json
{
  "task_id": "MAIL_REWARD_DAILY",
  "status": "failed",
  "postcondition": "task_boundary",
  "action_counts": {},
  "error_code": "WORKFLOW_POSTCONDITION_MISSING",
  "error_type": "MJAError",
  "error_message": "no recognized game task boundary for MAIL_REWARD_DAILY",
  "failure_stage": "pre_task_boundary",
  "traceback_path": "traceback.txt"
}
```

Successful results keep all five error fields `null`.

- [ ] **Step 2: Add an exception-finalization test.**

```python
def test_context_manager_finalizes_raised_mja_error(tmp_path: Path):
    with pytest.raises(MJAError):
        with RunDiagnostics.create(tmp_path) as diagnostics:
            run_dir = diagnostics.directory
            diagnostics.start_task(
                "MAIL_REWARD_DAILY",
                failure_stage="pre_task_boundary",
            )
            raise MJAError(
                ErrorCode.WORKFLOW_POSTCONDITION_MISSING,
                "no recognized game task boundary for MAIL_REWARD_DAILY",
            )

    payload = json.loads((run_dir / "run.json").read_text())
    result = json.loads((run_dir / "result.json").read_text())
    assert payload["status"] == "failed"
    assert payload["finished_at"] is not None
    assert payload["error"] == {
        "code": "WORKFLOW_POSTCONDITION_MISSING",
        "type": "MJAError",
        "message": "no recognized game task boundary for MAIL_REWARD_DAILY",
        "stage": "pre_task_boundary",
        "traceback_path": "traceback.txt",
    }
    assert result["error_code"] == "WORKFLOW_POSTCONDITION_MISSING"
    assert result["error_type"] == "MJAError"
    assert (run_dir / "traceback.txt").is_file()
```

- [ ] **Step 3: Implement one exception-to-result function.**

```python
def task_result_from_exception(
    task_id: str,
    stage: str,
    exc: BaseException,
    *,
    traceback_path: str,
) -> TaskResult:
    code = (
        exc.code.value
        if isinstance(exc, MJAError)
        else ErrorCode.WORKFLOW_UNEXPECTED_EXCEPTION.value
    )
    return TaskResult(
        task_id=task_id,
        status=TaskStatus.FAILED,
        postcondition=stage,
        action_counts={},
        error_code=code,
        error_type=type(exc).__name__,
        error_message=str(exc),
        failure_stage=stage,
        traceback_path=traceback_path,
    )
```

Add `WORKFLOW_UNEXPECTED_EXCEPTION` and `DIAGNOSTICS_UNFINALIZED` to
`agent.errors.ErrorCode`. Route the exception handlers in
`agent/workflows/engine.py`, `agent/actions/daily_workflow.py`, and
`agent/workflows/aggregate.py` through this function. Delete the
`aggregate_child_exception` result construction. Preserve an existing
`MJAError.code`; only an exception without a stable MJA code receives
`WORKFLOW_UNEXPECTED_EXCEPTION`.

- [ ] **Step 4: Finalize diagnostics in `finally`.**

Change `start_task()` to
`start_task(task_id: str, *, failure_stage: str) -> None` and store both values
on the diagnostic object. In `RunDiagnostics.__exit__`, write
`traceback.txt`, `result.json`, and the terminal `run.json` before closing the
log handler when an exception is present. If no exception is present but the
payload is still `running`, write a failed result with
`DIAGNOSTICS_UNFINALIZED`. Return `False` so the original exception still
propagates. `close()` remains idempotent and only closes the handler.

- [ ] **Step 5: Run focused tests.**

```bash
./install/.venv/bin/python -m pytest -q \
  tests/test_workflow_models.py tests/test_diagnostics.py \
  tests/test_workflow_engine.py tests/test_daily_workflow_action.py \
  tests/test_aggregate_report.py
```

Expected: exact exception metadata survives all layers and no test fixture ends in `running`.

- [ ] **Step 6: Commit the diagnostic contract.**

```bash
git add -- agent/errors.py agent/workflows/models.py agent/diagnostics.py \
  agent/workflows/engine.py agent/actions/daily_workflow.py \
  agent/workflows/aggregate.py agent/workflows/aggregate_report.py \
  tests/test_workflow_models.py tests/test_diagnostics.py \
  tests/test_workflow_engine.py tests/test_daily_workflow_action.py \
  tests/test_aggregate_report.py
git commit -m "fix: preserve exact daily task failures"
```

### Task 3: Introduce One Android Session with Independent Maa Task Processes

**Files:**

- Create: `agent/android/session.py`
- Modify: `agent/workflows/models.py`
- Modify: `agent/workflows/catalog.py`
- Modify: `tools/android_run.py`
- Modify: `tests/test_android_run.py`
- Modify: `tests/test_workflow_models.py`
- Modify: `tests/test_workflow_catalog.py`
- Create: `tests/test_android_session.py`

**Interfaces:**

- Produces `AndroidSession.prepare()`, bounded `run_maa_task()`, `recover_game_ready()`, and `close()`.
- Each call to `run_maa_task()` gets a fresh MaaPiCli process and a fresh result boundary while reusing the same prepared AVD/device.

- [ ] **Step 1: Write lifecycle and process-isolation tests.**

```python
session.prepare()
mail = session.run_maa_task(
    "mail_reward_daily",
    run_id="batch-1-mail",
    timeout_seconds=180,
)
shop = session.run_maa_task(
    "shop_free_gift_daily",
    run_id="batch-1-shop",
    timeout_seconds=180,
)
session.close()

assert avd.start_calls == 1
assert device.wait_ready_calls == 1
assert [call.task for call in spawns] == [
    "mail_reward_daily",
    "shop_free_gift_daily",
]
assert len(spawns) == 2
assert spawns[0] is not spawns[1]
```

Add one test where the first child exits 3 and the second child is still
spawned, and one where the first child's `wait(timeout=180)` raises
`subprocess.TimeoutExpired`. In the timeout case assert `terminate()` is
called, a bounded 10-second wait is attempted, `kill()` is the fallback, the
returned error code is `WORKFLOW_TIMEOUT`, and a subsequent task still gets a
new child.

- [ ] **Step 2: Add hard timeouts to every task policy.**

Add `timeout_seconds: int` to `TaskPolicy` and serialize it. Use these exact
outer watchdog values:

| Task | Seconds |
|---|---:|
| `MAIL_REWARD_DAILY` | 180 |
| `SHOP_FREE_GIFT_DAILY` | 180 |
| `WEEKLY_FREE_GIFT_MONDAY` | 180 |
| `TRIAL_SWORD_DAILY` | 240 |
| `FREE_APPRAISAL_DAILY` | 240 |
| `BUY_TEA_DAILY` | 180 |
| `COLLECTION_DEPLOYMENT_DAILY` | 300 |
| `HERO_DISPATCH_DAILY` | 600 |
| `SHADOW_RUINS_DAILY` | 1200 |
| `SPEND_CONDENSATE_DAILY` | 300 |
| `MARTIAL_STUDY_BREAKTHROUGH_DAILY` | 600 |
| `EAT_STAMINA_FOOD_DAILY` | 240 |
| `DUNGEON_SWEEP_DAILY` | 600 |
| `JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY` | 1800 |
| `RING_CHALLENGE_DAILY` | 1200 |
| `DAILY_TASK_REWARD_CLAIM_DAILY` | 300 |
| `BATTLE_PASS_REWARD_DAILY` | 300 |

- [ ] **Step 3: Move reusable preparation from `AndroidRun.run()` into `AndroidSession.prepare()`.**

The method owns, in this order: run lock, SDK ensure, AVD start, device ready, package ensure, foreground/login observation. It must not report `GAME_READY` merely because the package is foreground; Maa visual preflight is Task 4.

Add an explicit `run_game_ready()` call before the first business task and after a task-local failure. The
business task deadline starts only after `run_game_ready()` returns a verified-home result. Do not call the
full `require_task_boundary()`/global OCR sweep from inside the business task as a substitute; a 300-second
business budget must never be consumed by title-page startup or recovery.

- [ ] **Step 4: Implement one-task MaaPiCli execution.**

`run_maa_task()` writes a task-specific config, snapshots new log offsets,
spawns MaaPiCli, and calls `child.wait(timeout=timeout_seconds)`. On timeout it
terminates the child, waits at most 10 seconds, kills if still alive, and
returns `TaskExecution` with `WORKFLOW_TIMEOUT`; it never performs a business
retry. Otherwise it loads only result artifacts newer than the task start time
and returns `TaskExecution`. A missing/malformed current-run result becomes
`TASK_RESULT_MISSING`, not success inferred from terminal text.

- [ ] **Step 5: Keep `AndroidRun.run()` as a compatibility facade.**

Its body becomes:

```python
run_id = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%f%z")
with AndroidSession(
    config=self.config,
    install_root=self.install_root,
    runner=self.runner,
    spawn=self.spawn,
) as session:
    session.prepare()
    policy = next(
        (
            candidate
            for candidate in TASK_POLICIES.values()
            if candidate.interface_name == task_name
        ),
        None,
    )
    execution = session.run_maa_task(
        task_name,
        run_id=run_id,
        timeout_seconds=policy.timeout_seconds if policy is not None else 300,
    )
    return execution.child_exit_code
```

Do not duplicate SDK/AVD setup in the facade.

- [ ] **Step 6: Run focused tests.**

```bash
./install/.venv/bin/python -m pytest -q \
  tests/test_android_session.py tests/test_android_run.py \
  tests/test_android_adb.py tests/test_android_login.py \
  tests/test_workflow_models.py tests/test_workflow_catalog.py
```

- [ ] **Step 7: Commit the session boundary.**

```bash
git add -- agent/android/session.py agent/workflows/models.py \
  agent/workflows/catalog.py tools/android_run.py tests/test_android_session.py \
  tests/test_android_run.py tests/test_workflow_models.py \
  tests/test_workflow_catalog.py
git commit -m "refactor: isolate Maa tasks in one Android session"
```

### Task 4: Build a Standalone `MJA_Game_Ready` Maa Pipeline

**Files:**

- Create: `assets/resource_android/pipeline/game_ready.json`
- Create: `assets/resource_android/image/game_ready/title_age_12.png`
- Create: `assets/resource_android/image/game_ready/title_welcome.png`
- Modify: `assets/resource_android/pipeline/daily_common.json`
- Modify: `tools/capture_templates.py`
- Modify: `assets/interface.json`
- Modify: `tests/test_capture_templates.py`
- Modify: `tests/test_android_resources.py`
- Modify: `tests/test_android_login.py`
- Create: `tests/fixtures/GAME_READY/title_page.png`
- Create: `tests/fixtures/GAME_READY/home.png`
- Create: `tests/test_game_ready_contract.py`

**Interfaces:**

- Produces Maa entry `MJA_Game_Ready` and recovery entry `MJA_Game_Recover`.
- Both end only after a fresh frame proves `home`; neither consumes a daily business action.

- [ ] **Step 1: Preserve the exact failed title page as a fixture.**

Copy the 1280×720 evidence image
`install/debug/on_error/2026.08.02-19.22.37.894_MJA_Daily_All.png`
to `tests/fixtures/GAME_READY/title_page.png`. Add the Android capture profile with these exact crops:

```python
"game_ready": (
    "game_ready",
    {
        "title_age_12.png": (20, 600, 80, 95),
        "title_welcome.png": (630, 20, 180, 65),
    },
)
```

The age-rating icon and top `欢迎进入游戏` banner are visibly stable in the failure frame; the low-contrast bottom text is not used as the sole page detector.

- [ ] **Step 2: Add failing resource contract tests.**

Assert that title recognition is composite and the click target is a fixed bounded start region authorized only by the title-page composite:

```python
pipeline = json.loads(
    Path("assets/resource_android/pipeline/game_ready.json").read_text(
        encoding="utf-8"
    )
)
cleanup_source = Path("agent/workflows/maa_android.py").read_text(encoding="utf-8")

assert pipeline["game_ready.title"]["recognition"]["type"] == "And"
assert pipeline["game_ready.start"]["action"]["param"]["target"] == [520, 620, 240, 80]
assert "reset.start_game" not in cleanup_source
```

- [ ] **Step 3: Implement the ready graph.**

The entry order is exact:

```text
MJA_Game_Ready
  -> game_ready.home
  -> game_ready.title
  -> game_ready.monthly_signin
  -> game_ready.reward_popup
  -> game_ready.network_retry
  -> game_ready.loading
  -> safety.login_or_verification
  -> safety.unknown_dialog
```

`game_ready.title` requires both stable templates; only then may `game_ready.start` click `[520,620,240,80]`. After the click, the graph loops through known loading/popups until `game_ready.home` is recognized. `safety.*` nodes record `blocked_safety` and perform no input.

- [ ] **Step 4: Correct the login terminology.**

Keep `LoginGate` responsible for foreground/login observation, but rename its successful message/state documentation to `FOREGROUND_LOGIN_CLEAR`. Do not let its result satisfy `GAME_READY`; only the Maa visual entry can do that.

- [ ] **Step 5: Remove startup from cleanup.**

Delete `reset.start_game` from `MaaAndroidWorkflowDriver.return_to_home()` and its tests. Cleanup may return to an in-game home; it may not start a not-yet-ready session.

- [ ] **Step 6: Run static/resource tests and assemble.**

```bash
./install/.venv/bin/python -m pytest -q \
  tests/test_capture_templates.py tests/test_android_resources.py \
  tests/test_android_login.py tests/test_game_ready_contract.py
./install/.venv/bin/python -m tools.setup --root .
./install/.venv/bin/python -m tools.verify_install install
```

- [ ] **Step 7: Run the real preflight from the currently observed title page.**

```bash
scripts/run-all-dailies.sh --preflight-only
```

Pass criteria: exit 0; current-run preflight result is `completed`; evidence starts on title and ends on home; no daily task directory is created; action trace contains only the authorized title/popup navigation actions.

- [ ] **Step 8: Repeat cold-start preflight ten times before commit.**

```bash
for run in 1 2 3 4 5 6 7 8 9 10; do
  scripts/run-all-dailies.sh --cold-start-preflight || exit 1
done
```

Pass criteria: 10/10 exit 0 and 10 distinct preflight result directories end at home.

- [ ] **Step 9: Commit only after 10/10.**

```bash
git add -- assets/resource_android/pipeline/game_ready.json \
  assets/resource_android/pipeline/daily_common.json \
  assets/resource_android/image/game_ready tests/fixtures/GAME_READY \
  assets/interface.json tools/capture_templates.py \
  tests/test_capture_templates.py tests/test_android_resources.py \
  tests/test_android_login.py tests/test_game_ready_contract.py \
  agent/workflows/maa_android.py tests/test_maa_android_workflow.py
git commit -m "feat: add verified game-ready Maa pipeline"
```

### Task 5: Implement the External Daily Supervisor and Recovery Loop

**Files:**

- Modify: `agent/errors.py`
- Create: `agent/daily/__init__.py`
- Create: `agent/daily/models.py`
- Create: `agent/daily/supervisor.py`
- Modify: `agent/workflows/aggregate.py`
- Modify: `agent/workflows/aggregate_report.py`
- Modify: `tools/android_daily_run.py`
- Modify: `tests/test_daily_supervisor.py`
- Modify: `tests/test_android_daily_run.py`
- Modify: `tests/test_aggregate_report.py`

**Interfaces:**

- Produces the `DailySupervisor` interface shown above.
- Uses a fresh Maa task process for preflight, every business task, and recovery.

- [ ] **Step 1: Define failure-domain classification tests.**

Use exact mappings:

```python
TASK_LOCAL_CODES = {
    "WORKFLOW_POSTCONDITION_MISSING",
    "WORKFLOW_TIMEOUT",
    "WORKFLOW_STEP_CAP",
    "DUNGEON_BAG_FULL",
}
SESSION_CODES = {
    "TASK_BOUNDARY_RETURN_FAILED",
    "TASK_BOUNDARY_VERIFY_FAILED",
    "TASK_RESULT_MISSING",
}
RUNTIME_CODES = {
    "ANDROID_GAME_NOT_FOREGROUND",
    "ANDROID_NETWORK_UNAVAILABLE",
    "ANDROID_STORAGE_LOW",
    "ANDROID_RUN_FAILED",
}
SAFETY_CODES = {
    "ANDROID_LOGIN_REQUIRED",
    "WORKFLOW_SAFETY_BLOCKED",
}
```

Add the six new members used above to `agent.errors.ErrorCode`:
`DUNGEON_BAG_FULL`, `TASK_BOUNDARY_RETURN_FAILED`,
`TASK_BOUNDARY_VERIFY_FAILED`, `TASK_RESULT_MISSING`, `ANDROID_RUN_FAILED`, and
`WORKFLOW_SAFETY_BLOCKED`. The other codes already exist and retain their
current values.

Task-local and recovered session failures continue; runtime failures invoke one session repair plus one game-ready recovery; safety failures send no input and terminate only when the blocking surface remains after read-only confirmation.

- [ ] **Step 2: Implement date selection without mutating the task registry.**

`WORKFLOW_DEFINITION_ORDER` remains canonical. Sunday 2026-08-02 returns 16 IDs; Monday 2026-08-03 returns all 17 in catalog order.

- [ ] **Step 3: Implement checkpoint-after-every-event.**

Write the aggregate after preflight, every task, and every recovery. The current task result is never lost if the parent process receives SIGINT afterward.

- [ ] **Step 4: Implement continuation after task-local failure.**

After a failed task, freeze its result, run `MJA_Game_Recover`, then execute the next task when recovery returns home. Do not rerun a consumptive business task unless its own current-state entry later proves `already_complete` without repeating the action.

For every task ID at zero-based `task_index`, set
`child_run_id = f"{batch_run_id}-{task_index:02d}-{task_id.lower()}"`, resolve
`policy = TASK_POLICIES[task_id]`, and call
`AndroidSession.run_maa_task(policy.interface_name,
timeout_seconds=policy.timeout_seconds, run_id=child_run_id)`. A
`WORKFLOW_TIMEOUT` result is classified as `FailureDomain.TASK`; after the
timed-out child is terminated, the same recovery-and-continue branch applies.

- [ ] **Step 5: Implement batch terminal semantics.**

- all selected tasks terminal and no failures: `completed`, exit 0;
- all selected tasks attempted with at least one local failure: `completed_with_task_failures`, exit 1;
- persistent runtime/safety block: `failed_runtime` or `blocked_safety`, nonzero exit, exact `stop_reason`, and untouched IDs retained in `remaining_task_ids` rather than converted into invented task results;
- SIGINT: `interrupted`, exit 130.

Add `AggregateStatus.BLOCKED_SAFETY = "blocked_safety"`. A
`RecoveryExecution` failure serializes the same five error fields as
`TaskResult`; the supervisor copies none of them into a generic replacement
code.

- [ ] **Step 6: Run focused tests.**

```bash
./install/.venv/bin/python -m pytest -q \
  tests/test_daily_supervisor.py tests/test_android_daily_run.py \
  tests/test_aggregate_report.py tests/test_workflow_aggregate.py
```

Expected: the Task 1 red tests now pass, including full suffix execution after first-task failure.

- [ ] **Step 7: Commit the supervisor.**

```bash
git add -- agent/errors.py agent/daily agent/workflows/aggregate.py \
  agent/workflows/aggregate_report.py \
  tools/android_daily_run.py tests/test_daily_supervisor.py \
  tests/test_android_daily_run.py tests/test_aggregate_report.py \
  tests/test_workflow_aggregate.py
git commit -m "feat: supervise daily tasks independently"
```

### Task 6: Replace the Production Aggregate Entry with MAA_BBB-Style Presets

**Files:**

- Modify: `assets/interface.json`
- Delete: `assets/resource_android/pipeline/daily/daily_all.json`
- Modify: `scripts/run-all-dailies.sh`
- Modify: `tools/android_daily_run.py`
- Modify: `agent/actions/daily_workflow.py`
- Modify: `agent/main.py`
- Modify: `tests/test_project_interface.py`
- Modify: `tests/test_mfa_daily_contract.py`
- Modify: `tests/test_android_daily_acceptance.py`
- Modify: `tests/test_project_contract.py`

**Interfaces:**

- Production all-task execution is the supervisor/preset, never `MJA_Daily_All`.
- Single-task entries remain individually selectable.

- [ ] **Step 1: Add a `每日完整任务` preset.**

The preset order is exactly:

```text
game_ready
mail_reward_daily
shop_free_gift_daily
weekly_free_gift_monday
trial_sword_daily
free_appraisal_daily
buy_tea_daily
collection_deployment_daily
hero_dispatch_daily
shadow_ruins_daily
spend_condensate_daily
martial_study_breakthrough_daily
eat_stamina_food_daily
dungeon_sweep_daily
jianlin_resource_condensate_stamina_daily
ring_challenge_daily
daily_task_reward_claim_daily
battle_pass_reward_daily
```

The supervisor applies weekday eligibility; the preset does not hide the weekly task.

- [ ] **Step 2: Remove aggregate production registration.**

Delete `AggregateDailyWorkflowAction` registration from `agent/main.py`/`daily_workflow.py` after report compatibility tests pass. Remove `daily_all` as a GUI task. Old aggregate JSON remains readable but cannot be selected for a new run.

- [ ] **Step 3: Make the shell wrapper explicit.**

`scripts/run-all-dailies.sh` continues to exec `tools/android_daily_run.sh`; the Python entry now invokes `DailySupervisor`. Supported options are:

```text
--preflight-only
--cold-start-preflight
--task TASK_ID          # repeatable
--resume-run RUN_ID
--stop
```

Multiple `--task` values are accepted and executed independently in supplied order after canonical validation.

- [ ] **Step 4: Add no-hidden-aggregate tests.**

```python
source = Path("agent/actions/daily_workflow.py").read_text()
assert "AggregateDailyWorkflowAction" not in source
assert not Path("assets/resource_android/pipeline/daily/daily_all.json").exists()
```

Also assert every canonical task maps to a unique entry and the preset contains no duplicate.

- [ ] **Step 5: Run interface and entry tests.**

```bash
./install/.venv/bin/python -m pytest -q \
  tests/test_project_interface.py tests/test_mfa_daily_contract.py \
  tests/test_android_daily_acceptance.py tests/test_project_contract.py
```

- [ ] **Step 6: Commit the control-plane switch.**

```bash
git add -- assets/interface.json scripts/run-all-dailies.sh \
  tools/android_daily_run.py agent/actions/daily_workflow.py agent/main.py \
  tests/test_project_interface.py tests/test_mfa_daily_contract.py \
  tests/test_android_daily_acceptance.py tests/test_project_contract.py
git rm -- assets/resource_android/pipeline/daily/daily_all.json
git commit -m "refactor: replace aggregate daily entry with independent tasks"
```

### Task 7: Port Non-Consumptive and Free Tasks into Native Maa Pipelines

**Files:**

- Modify: `assets/resource_android/pipeline/daily/mail_reward_daily.json`
- Modify: `assets/resource_android/pipeline/daily/shop_free_gift_daily.json`
- Modify: `assets/resource_android/pipeline/daily/weekly_free_gift_monday.json`
- Modify: `assets/resource_android/pipeline/daily/trial_sword_daily.json`
- Modify: `assets/resource_android/pipeline/daily/free_appraisal_daily.json`
- Modify: `assets/resource_android/pipeline/daily/collection_deployment_daily.json`
- Modify: `assets/resource_android/pipeline/daily/hero_dispatch_daily.json`
- Modify: `assets/resource_android/pipeline/daily/daily_task_reward_claim_daily.json`
- Modify: `assets/resource_android/pipeline/daily/battle_pass_reward_daily.json`
- Create: `agent/actions/task_result.py`
- Modify: `agent/main.py`
- Create: `tests/test_native_daily_pipelines.py`
- Modify: `tests/workflows/test_mail_reward_daily.py`
- Modify: `tests/workflows/test_shop_free_gift_daily.py`
- Modify: `tests/workflows/test_weekly_free_gift_monday.py`
- Modify: `tests/workflows/test_trial_sword_daily.py`
- Modify: `tests/workflows/test_free_appraisal_daily.py`
- Modify: `tests/workflows/test_collection_deployment_daily.py`
- Modify: `tests/workflows/test_batch23.py`
- Modify: `tests/workflows/test_daily_task_reward_claim_daily.py`
- Modify: `tests/workflows/test_battle_pass_reward_daily.py`

**Interfaces:**

- Produces full Maa control graphs for nine tasks.
- `RecordTaskResult` records only a supplied terminal result; it performs no game input.

- [ ] **Step 1: Register the result-only action.**

```python
def _task_run_directory() -> Path:
    value = os.environ.get("MJA_TASK_RUN_DIRECTORY")
    if not value:
        raise RuntimeError("MJA_TASK_RUN_DIRECTORY is required")
    directory = Path(value).resolve()
    if not directory.is_dir():
        raise RuntimeError(f"task run directory does not exist: {directory}")
    return directory


def _action_counts(directory: Path) -> dict[str, int]:
    path = directory / "action-counts.json"
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not all(
        isinstance(key, str) and isinstance(value, int) and value >= 0
        for key, value in payload.items()
    ):
        raise ValueError("action-counts.json must be a non-negative integer map")
    return payload


@AgentServer.custom_action("RecordTaskResult")
class RecordTaskResult(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> CustomAction.RunResult:
        payload = json.loads(argv.custom_action_param)
        if set(payload) != {"task_id", "status", "postcondition"}:
            return CustomAction.RunResult(success=False)
        directory = _task_run_directory()
        result = TaskResult(
            task_id=payload["task_id"],
            status=TaskStatus(payload["status"]),
            postcondition=payload["postcondition"],
            action_counts=_action_counts(directory),
        )
        temporary = directory / "result.json.tmp"
        temporary.write_text(
            json.dumps(result.as_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(directory / "result.json")
        return CustomAction.RunResult(success=True)
```

`AndroidSession.run_maa_task()` sets `MJA_TASK_RUN_DIRECTORY` to the current
child's fresh run directory. This action rejects missing/unknown fields and
never calls a controller method.

- [ ] **Step 2: Give every pipeline the MAA_BBB start-layer shape.**

Use these exact entry and start-layer node names:

| Entry | Current-page node | Home-entry node |
|---|---|---|
| `MJA_Daily_MAIL_REWARD_DAILY` | `mail.task_current_page` | `mail.task_home_entry` |
| `MJA_Daily_SHOP_FREE_GIFT_DAILY` | `shop_daily.task_current_page` | `shop_daily.task_home_entry` |
| `MJA_Daily_WEEKLY_FREE_GIFT_MONDAY` | `shop_weekly.task_current_page` | `shop_weekly.task_home_entry` |
| `MJA_Daily_TRIAL_SWORD_DAILY` | `trial.task_current_page` | `trial.task_home_entry` |
| `MJA_Daily_FREE_APPRAISAL_DAILY` | `appraisal.task_current_page` | `appraisal.task_home_entry` |
| `MJA_Daily_COLLECTION_DEPLOYMENT_DAILY` | `collection.task_current_page` | `collection.task_home_entry` |
| `MJA_Daily_HERO_DISPATCH_DAILY` | `hero_dispatch.task_current_page` | `hero_dispatch.task_home_entry` |
| `MJA_Daily_DAILY_TASK_REWARD_CLAIM_DAILY` | `daily_reward.task_current_page` | `daily_reward.task_home_entry` |
| `MJA_Daily_BATTLE_PASS_REWARD_DAILY` | `battle_pass.task_current_page` | `battle_pass.task_home_entry` |

For each row, set the entry's `next` array to the current-page node, the
home-entry node, and `[JumpBack]MJA_Game_Ready` in that order. No entry may
call `DailyWorkflowAction` after porting.

- [ ] **Step 3: Keep task-owned exits.**

Mail owns mail popup/page closure; shop owns shop closure; appraisal owns appraisal result/page closure; collection owns reward/map closure; hero owns dispatch closure; daily reward and battle pass own their result overlays. The only shared terminal recognizer is `MJA_Home_Verified`.

For mail, the task-owned graph must distinguish all of these same-frame states before
writing a result: `mail.claim_all` (claimable), `mail.empty`/`删除已读` (no claimable
mail), and `mail.close` (safe exit). A detail page without either a claimable marker or
an explicit empty/already-read marker is a failure, not an inferred success.

- [ ] **Step 4: Encode two explicit terminal branches per task.**

- completed branch: action occurred and a fresh postcondition plus home is visible;
- already-complete branch: current-state marker proves no action is needed, then home is visible.

Both branches call `RecordTaskResult` with exact task ID/status/postcondition.

- [ ] **Step 5: Add structural tests for all nine graphs.**

For every file assert: no `DailyWorkflowAction`; has game-ready fallback; has completed and already-complete result nodes; all click nodes have page-scoped recognition; final result node is reachable only after home verification.

- [ ] **Step 6: Run tests and Maa resource load.**

```bash
./install/.venv/bin/python -m pytest -q \
  tests/test_native_daily_pipelines.py tests/test_android_resources.py \
  tests/workflows/test_mail_reward_daily.py \
  tests/workflows/test_shop_free_gift_daily.py \
  tests/workflows/test_collection_deployment_daily.py
./install/.venv/bin/python -m tools.verify_install install
```

- [ ] **Step 7: Live-run each task twice.**

First run must be `completed` or `already_complete`; immediate second run must be `already_complete` without repeating a protected action. Execute in catalog order with repeated `--task` options.

- [ ] **Step 8: Commit the native free-task batch.**

```bash
git add -- assets/resource_android/pipeline/daily agent/actions/task_result.py \
  agent/main.py tests/test_native_daily_pipelines.py tests/workflows \
  tests/test_android_resources.py
git commit -m "feat: move free daily tasks into Maa pipelines"
```

### Task 8: Port Consumptive Tasks with a Narrow Protected-Action Adapter

**Files:**

- Modify: `assets/resource_android/pipeline/daily/buy_tea_daily.json`
- Modify: `assets/resource_android/pipeline/daily/spend_condensate_daily.json`
- Modify: `assets/resource_android/pipeline/daily/martial_study_breakthrough_daily.json`
- Modify: `assets/resource_android/pipeline/daily/eat_stamina_food_daily.json`
- Create: `agent/actions/protected_action.py`
- Modify: `agent/main.py`
- Modify: `agent/workflows/catalog.py`
- Create: `tests/test_protected_action.py`
- Modify: `tests/test_native_daily_pipelines.py`
- Modify: `tests/workflows/test_batch23.py`

**Interfaces:**

- `ProtectedAction` authorizes one action from the current Maa frame; it is not a workflow engine.
- Existing task policy remains the single source for approved resource and action cap.
- `authorize_protected_action(request: ProtectedActionRequest, policy: TaskPolicy) -> ProtectedActionDecision` is the pure same-frame decision function called before the one Maa controller gesture; `ProtectedActionDecision` contains `request`, `allowed`, and `reason`, where `reason` is a `ProtectedActionReason` enum containing at least `ALLOWED` and `STALE_FRAME`.

- [ ] **Step 1: Add same-frame protected-action tests.**

```python
allowed = authorize_protected_action(
    ProtectedActionRequest(
        task_id="BUY_TEA_DAILY",
        action_id="tea.buy_once",
        current_frame_id="f2",
        page_frame_id="f2",
        target_frame_id="f2",
        resource="tea_free_allowance",
        amount=1,
        visible_text=("免费次数 1",),
    ),
    TASK_POLICIES["BUY_TEA_DAILY"],
)
assert allowed.allowed is True

stale = authorize_protected_action(
    replace(allowed.request, page_frame_id="f1"),
    TASK_POLICIES["BUY_TEA_DAILY"],
)
assert stale.allowed is False
assert stale.reason is ProtectedActionReason.STALE_FRAME
```

Define `ProtectedActionRequest` with the fields shown above and return the
request on `AuthorizationDecision` so the stale-frame test is self-contained.
Add parameterized cases for unknown resource, missing amount, exhausted cap,
real-money text, verification text, and duplicate action IDs. The CustomAction
test must additionally assert that a denied decision leaves a fake
controller's gesture list empty.

- [ ] **Step 2: Implement only authorization and one controller gesture.**

`ProtectedAction` accepts `task_id`, `action_id`, `page_marker`, `target_marker`, `postcondition`, and approved resource evidence. It validates policy/current frame, calls the Maa controller once, increments the task-scoped counter, and returns. It contains no page navigation or task transition table.

- [ ] **Step 3: Port four task graphs.**

| Task | Protected action | Required terminal proof |
|---|---|---|
| `BUY_TEA_DAILY` | one approved tea purchase | bought/already-bought marker then home |
| `SPEND_CONDENSATE_DAILY` | approved regional condensate use only | exact quota/zero-remaining marker then home |
| `MARTIAL_STUDY_BREAKTHROUGH_DAILY` | approved breakthrough/claim only | success/full/no-action marker then home |
| `EAT_STAMINA_FOOD_DAILY` | one approved food use | inventory delta or daily-complete marker then home |

Every navigation click remains a native Maa node. Only the listed protected actions call `ProtectedAction`.

- [ ] **Step 4: Remove these tasks from Python definitions after dual-run parity.**

Delete their production registry mappings only after both native Pipeline runs produce the same terminal status and no extra protected action compared with the legacy definition.

- [ ] **Step 5: Run tests, resource load and live idempotency.**

```bash
./install/.venv/bin/python -m pytest -q \
  tests/test_protected_action.py tests/test_native_daily_pipelines.py \
  tests/workflows/test_batch23.py tests/test_workflow_catalog.py
./install/.venv/bin/python -m tools.verify_install install
```

Run each task once, then immediately again. The second run must send zero protected gestures.

- [ ] **Step 6: Commit the protected-action batch.**

```bash
git add -- agent/actions/protected_action.py agent/main.py \
  agent/workflows/catalog.py assets/resource_android/pipeline/daily \
  tests/test_protected_action.py tests/test_native_daily_pipelines.py \
  tests/workflows/test_batch23.py tests/test_workflow_catalog.py
git commit -m "feat: port resource dailies to protected Maa pipelines"
```

### Task 9: Port Complex Battle and Sweep Tasks without Reintroducing a Global Engine

**Files:**

- Modify: `assets/resource_android/pipeline/daily/shadow_ruins_daily.json`
- Modify: `assets/resource_android/pipeline/daily/dungeon_sweep_daily.json`
- Modify: `assets/resource_android/pipeline/daily/jianlin_resource_condensate_stamina_daily.json`
- Modify: `assets/resource_android/pipeline/daily/ring_challenge_daily.json`
- Create: `agent/actions/daily/__init__.py`
- Create: `agent/actions/daily/jianlin_planner.py`
- Modify: `agent/main.py`
- Create: `tests/test_jianlin_planner_action.py`
- Modify: `tests/test_native_daily_pipelines.py`
- Modify: `tests/test_maa_android_workflow.py`
- Modify: `tests/workflows/test_batch23.py`
- Modify: `tests/workflows/test_jianlin_resource_condensate_stamina_daily.py`
- Modify: `tests/workflows/test_ring_challenge_daily.py`

**Interfaces:**

- Complex loops live in their own Pipeline files.
- `plan_safe_challenge(remaining_stamina: int, costs: Sequence[int], multipliers: Sequence[int]) -> ChallengePlan | None` remains a pure function.
- `PlanJianlinChallenge` may override only `jianlin.plan.apply`; it performs no click and cannot dispatch another task.

- [ ] **Step 1: Port Shadow as its own finite graph.**

The graph must explicitly separate: page entry, card state, stage entry, battle, victory/result overlay, reward overlay, exploration return, attempt completion and home return. `max_hit` bounds battle attempts; reward must be dismissed before another movement node can run.

- [ ] **Step 2: Port Dungeon as its own finite graph.**

The graph owns dungeon selection, list scrolling, sweep panel, ticket/bag-full branches, reward and close. `DUNGEON_BAG_FULL` is task-local and records failure; the supervisor then recovers and continues subsequent tasks.

- [ ] **Step 3: Keep Jianlin planning pure and move navigation out.**

Move `ChallengePlan`, `plan_safe_challenge()`, and `_safe_multipliers()` from
`agent/workflows/definitions/jianlin_resource_condensate_stamina_daily.py` to
`agent/actions/daily/jianlin_planner.py`; rename `_safe_multipliers()` to
`safe_multipliers()`. Register exactly one `PlanJianlinChallenge` CustomAction.
It reads scalar OCR values from its current invocation, calls the pure planner,
and uses `context.override_pipeline()` to set the count and multiplier on
`jianlin.plan.apply`. Move page selection, count/multiplier clicks, challenge,
refill confirmation, battle, and result navigation into
`jianlin_resource_condensate_stamina_daily.json`. Never save OCR boxes or a
frame identifier for a later invocation.

- [ ] **Step 4: Port Ring as its own finite graph.**

The graph owns mode/rank recognition, challenge entry, battle/result, exhausted attempts and home return. A failed fight attempt remains inside Ring's result branch and cannot mutate another task's state.

- [ ] **Step 5: Add a generic-engine purity test.**

```python
engine = Path("agent/workflows/engine.py").read_text(encoding="utf-8")
for task_word in ("shadow", "dungeon", "jianlin", "ring"):
    assert task_word not in engine.casefold()
```

The shared engine may enforce generic timeout/cap/diagnostics only during migration; it must not know task-specific markers.

- [ ] **Step 6: Run focused and live tests.**

```bash
./install/.venv/bin/python -m pytest -q \
  tests/test_native_daily_pipelines.py tests/test_jianlin_planner_action.py \
  tests/test_maa_android_workflow.py \
  tests/workflows/test_batch23.py \
  tests/workflows/test_jianlin_resource_condensate_stamina_daily.py \
  tests/workflows/test_ring_challenge_daily.py
./install/.venv/bin/python -m tools.verify_install install
```

Live-run all four independently, then immediate no-op reruns. Each ends at home and writes a terminal result.

- [ ] **Step 7: Commit the complex-task batch.**

```bash
git add -- assets/resource_android/pipeline/daily agent/actions/daily \
  agent/main.py agent/workflows/engine.py tests/test_native_daily_pipelines.py \
  tests/test_jianlin_planner_action.py tests/test_maa_android_workflow.py \
  tests/workflows
git commit -m "feat: isolate complex dailies in Maa pipelines"
```

### Task 10: Remove the Central Workflow Driver from the Production Path

**Files:**

- Delete: `agent/workflows/maa_android.py`
- Delete: `agent/workflows/engine.py`
- Delete: `agent/workflows/registry.py`
- Delete: `agent/workflows/definitions/`
- Delete: `agent/actions/daily_workflow.py`
- Modify: `agent/workflows/aggregate.py`
- Modify: `agent/main.py`
- Delete: `tests/test_maa_android_workflow.py`
- Delete: `tests/test_workflow_engine.py`
- Delete: `tests/test_daily_workflow_action.py`
- Delete: `tests/workflows/support.py`
- Modify: `tests/test_workflow_aggregate.py`
- Modify: `tests/test_android_daily_acceptance.py`
- Modify: `tests/test_workflow_catalog.py`
- Modify: `tests/test_project_contract.py`

**Interfaces:**

- Production task entries resolve directly to Maa Pipeline nodes and narrow actions.
- Legacy report readers remain; legacy aggregate/driver execution does not.

- [ ] **Step 1: Prove all 17 entries have no `DailyWorkflowAction`.**

Parse every `assets/resource_android/pipeline/daily/*.json` and assert its canonical entry has native `next` flow. No production pipeline may name `DailyWorkflowAction` or `AggregateDailyWorkflowAction`.

- [ ] **Step 2: Delete the legacy execution modules.**

After Tasks 7–9 have passed their named live parity gates, remove
`agent/workflows/maa_android.py`, `agent/workflows/engine.py`,
`agent/workflows/registry.py`, the complete `agent/workflows/definitions/`
directory, and `agent/actions/daily_workflow.py`. Remove their four legacy test
files listed above. Keep the rewritten task rule tests and native Pipeline
tests. In `agent/workflows/aggregate.py`, retain only `AggregateStatus`,
`AggregateResult`, and old-JSON deserialization; delete `AggregateScheduler`.

- [ ] **Step 3: Keep only narrow reusable modules.**

Allowed Python production responsibilities are: task result recording, protected action authorization, pure resource planning, diagnostics, Android session and supervisor. No Python function may contain the full navigation graph for more than one task.

- [ ] **Step 4: Run the full automated suite.**

```bash
./install/.venv/bin/python -m pytest -q
./install/.venv/bin/ruff check agent tools tests
./install/.venv/bin/python -m tools.setup --root .
./install/.venv/bin/python -m tools.verify_install install
git diff --check
```

- [ ] **Step 5: Commit the legacy runtime removal.**

```bash
git add -- agent/main.py agent/workflows/aggregate.py \
  tests/test_workflow_aggregate.py tests/test_android_daily_acceptance.py \
  tests/test_workflow_catalog.py tests/test_project_contract.py
git rm -- agent/workflows/maa_android.py agent/workflows/engine.py \
  agent/workflows/registry.py agent/workflows/definitions \
  agent/actions/daily_workflow.py tests/test_maa_android_workflow.py \
  tests/test_workflow_engine.py tests/test_daily_workflow_action.py \
  tests/workflows/support.py
git commit -m "refactor: retire the coupled daily workflow runtime"
```

### Task 11: Rewrite the Runbook and Daily Skill

**Files:**

- Create: `docs/runbooks/android-daily-one-shot.md`
- Modify: `/Users/gaoguobin/.codex/skills/maa-run-jianzhichuan-dailies/SKILL.md`
- Create: `tests/test_daily_runbook_contract.py`

**Interfaces:**

- Repository runbook is the operational source of truth.
- Skill is a thin adapter and contains no contradictory retry policy.

- [ ] **Step 1: Write the runbook around the actual supervisor.**

The runbook must require, in order:

```text
1. confirm no active runner
2. verify source/install digest
3. run --preflight-only
4. run all eligible tasks through DailySupervisor
5. monitor current batch checkpoint
6. audit every expected task ID for the current date
7. accept only the formal success predicate
```

It must explain task/session/runtime/safety failure domains and forbid retrying a protected business action without task-specific no-op evidence.

- [ ] **Step 2: Replace the skill's blind wrapper rule.**

The skill still invokes `scripts/run-all-dailies.sh`, but only after `--preflight-only`. Remove “same step fails twice then stop and ask” and “always preserve failed screen indefinitely.” Replace them with “freeze evidence, follow supervisor recovery, escalate only persistent runtime/safety blocks.”

- [ ] **Step 3: Require complete result auditing in the skill.**

For 2026-08-03, the skill must expect all 17 IDs, including `WEEKLY_FREE_GIFT_MONDAY`. It must reject stale run IDs, missing results, nonterminal `run.json`, nonzero child codes and generic errors lacking original metadata.

- [ ] **Step 4: Add repository contract tests.**

Assert that the runbook documents `--preflight-only`, task isolation, Monday selection, result predicate and Maa ADB-only input. Assert the shell wrapper resolves to the supervisor entry.

- [ ] **Step 5: Run tests and manually dry-run skill commands without game input.**

```bash
./install/.venv/bin/python -m pytest -q tests/test_daily_runbook_contract.py
scripts/run-all-dailies.sh --help
```

- [ ] **Step 6: Commit the repository runbook; keep the home-directory skill change separate.**

```bash
git add -- docs/runbooks/android-daily-one-shot.md \
  tests/test_daily_runbook_contract.py
git commit -m "docs: define the isolated daily run contract"
```

### Task 12: Final Fault-Injection, Live Matrix, Monday Full Run, and Freeze

**Files:**

- Evidence directory: `install/debug/runs/preflight/`
- Evidence directory: `install/debug/runs/daily/`
- Evidence directory: `install/debug/runs/batch/`
- Modify after evidence: the 17 JSON files in `verification/tasks/` whose basenames are the task IDs in the live matrix below
- Modify: `docs/verification/android-daily-aggregate.md`

**Interfaces:**

- Produces the only evidence set allowed to mark the work complete.

- [ ] **Step 1: Run all automated gates from a clean assembled runtime.**

```bash
./install/.venv/bin/python -m pytest -q
./install/.venv/bin/ruff check agent tools tests
./install/.venv/bin/python -m tools.setup --root .
./install/.venv/bin/python -m tools.verify_install install
git diff --check
```

`verify_install` must compare source/install digests and load the complete Maa resource bundle.

- [ ] **Step 2: Run a no-input task-isolation fault injection.**

Use a test-only entry that records `failed` without controller input, followed by two test-only success entries. Pass criteria: all three entries run; recovery is called once; result order is preserved; `remaining_task_ids=[]`.

- [ ] **Step 3: Run cold-start preflight 10/10.**

Run this exact command. Any failure resets the count; fix the observed
recognizer/recovery and repeat until one continuous 10-run set passes.

```bash
for run in 1 2 3 4 5 6 7 8 9 10; do
  scripts/run-all-dailies.sh --cold-start-preflight || exit 1
done
```

- [ ] **Step 4: Complete the 17-task live matrix.**

| # | Task | First accepted result | Immediate rerun |
|---:|---|---|---|
| 1 | `MAIL_REWARD_DAILY` | `completed/already_complete` + home | `already_complete` |
| 2 | `SHOP_FREE_GIFT_DAILY` | `completed/already_complete` + home | `already_complete` |
| 3 | `WEEKLY_FREE_GIFT_MONDAY` | Monday `completed/already_complete` + home | `already_complete` |
| 4 | `TRIAL_SWORD_DAILY` | `completed/already_complete` + home | `already_complete` |
| 5 | `FREE_APPRAISAL_DAILY` | `completed/already_complete` + home | `already_complete` |
| 6 | `BUY_TEA_DAILY` | `completed/already_complete` + home | no duplicate purchase |
| 7 | `COLLECTION_DEPLOYMENT_DAILY` | `completed/already_complete` + home | `already_complete` |
| 8 | `HERO_DISPATCH_DAILY` | `completed/already_complete` + home | no duplicate dispatch |
| 9 | `SHADOW_RUINS_DAILY` | `completed/already_complete` + home | no extra attempt |
| 10 | `SPEND_CONDENSATE_DAILY` | `completed/already_complete` + home | no duplicate spend |
| 11 | `MARTIAL_STUDY_BREAKTHROUGH_DAILY` | `completed/already_complete` + home | no duplicate breakthrough |
| 12 | `EAT_STAMINA_FOOD_DAILY` | `completed/already_complete` + home | no duplicate food use |
| 13 | `DUNGEON_SWEEP_DAILY` | `completed/already_complete/not_eligible` + home | no duplicate sweep |
| 14 | `JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY` | `completed/already_complete` + home | no duplicate refill/spend |
| 15 | `RING_CHALLENGE_DAILY` | `completed/already_complete` + home | no extra challenge |
| 16 | `DAILY_TASK_REWARD_CLAIM_DAILY` | `completed/already_complete` + home | `already_complete` |
| 17 | `BATTLE_PASS_REWARD_DAILY` | `completed/already_complete` + home | `already_complete` |

Every row needs a current commit SHA, current resource digest, task result,
before/after evidence, exact action counts, and terminal home frame. Change the
JSON file in `verification/tasks/` whose basename exactly equals that row's
Task value from `live_pending` to `live_verified` only when the row passes.

- [ ] **Step 5: Run the Sunday 16-task warm acceptance.**

On 2026-08-02, run:

```bash
scripts/run-all-dailies.sh
```

Pass criteria: exactly 16 eligible task results, weekly task excluded by date, all accepted statuses, no remaining IDs, exit 0.

- [ ] **Step 6: Run the Monday 17-task fresh acceptance from the title page.**

On 2026-08-03, start at the title page and run the same one command. Pass criteria:

```text
CLI exit code = 0
batch.status = completed
selected_task_ids = all 17 canonical IDs
remaining_task_ids = []
stop_reason = null
each task has this batch run_id
each task status in {completed, already_complete, not_eligible}
no failed or blocked_safety
each task final boundary = home
no run.json remains running
```

- [ ] **Step 7: Audit diagnostics and runtime integrity.**

Search only the Monday run directories. There must be no `aggregate_child_exception`, generic `WORKFLOW_DRIVER_FAILED` without original fields, stale result from another run, Launcher screenshot after preflight, duplicate protected action, or source/install digest mismatch.

- [ ] **Step 8: Freeze and commit verification evidence.**

Stage only source, tests, docs and small structured verification records. Do not commit account-identifying screenshots/logs. Commit:

```bash
git commit -m "test: verify all Jianzhichuan dailies independently"
```

Tag or merge only after the Monday 17-task predicate passes exactly.

## Final Rejection Conditions

The implementation is not complete if any of the following is true:

- the first task still starts the game;
- `daily_all` is still one CustomAction;
- a task-local failure leaves later task IDs unattempted;
- a business MaaPiCli child can wait without its catalog hard timeout or suppress the next task after timeout;
- a later task starts directly on an unverified failed-task screen;
- the title page is accepted solely from package foreground or low-contrast bottom OCR;
- `return_to_home()` still contains task-specific branches for multiple unrelated tasks;
- `engine.py` still contains Shadow/Dungeon/Jianlin/Ring special cases;
- a protected action can reuse a recognition box from an older frame;
- an exception becomes `aggregate_child_exception`/generic driver failure;
- any current run diagnostics remain `running`;
- verification records remain `live_pending` while code is declared complete;
- the Monday full run omits `WEEKLY_FREE_GIFT_MONDAY`;
- the final result is anything other than the exact success predicate above.
