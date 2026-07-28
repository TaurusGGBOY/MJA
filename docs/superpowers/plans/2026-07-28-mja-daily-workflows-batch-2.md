# MJA Daily Workflows Batch 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 capture fallback、workflow foundation 和 Batch 1 已完成的基础上，迁移并验证六个日常任务：HERO_DISPATCH_DAILY、BUY_TEA_DAILY、SPEND_CONDENSATE_DAILY、MARTIAL_STUDY_BREAKTHROUGH_DAILY、EAT_STAMINA_FOOD_DAILY、DUNGEON_SWEEP_DAILY。每项都拥有独立的 canonical definition、pipeline、四态 PNG 夹具、ProjectInterface V2 入口、TDD 测试和可审计的前台实机验证记录。

**Architecture:** Batch 2 只提供六个 WorkflowDefinition、六个 daily pipeline、任务模板和测试。任务统一交给 foundation 已定义的 run_workflow 执行，由 DailyWorkflowAction 作为 Maa custom action 入口；任务策略使用既有 TaskPolicy，结果只使用既有 TaskResult 和五个运行态。每一个有副作用的决定都把当前截图中的页面证据和目标证据组装为 VisualEvidence，并通过既有 authorize_action；识别框由当前帧提供给 MacOSForegroundClick 或 foundation 已注册的动作执行器。Batch 2 不重建模型、runtime、action executor、诊断、注册器或 CLI。

**Tech Stack:** Python 3.14、MaaFramework v5.12.2、ProjectInterface V2、Maa pipeline JSON、既有 ScreenCaptureKit/CoreGraphicsRegion MacOSController、Pillow、pytest、foundation 已定义的 run_workflow 和 tools.run_cli --task。

## Global Constraints

- 前置必须已经完成并通过质量门：docs/superpowers/plans/2026-07-28-mja-macos-capture-fallback.md、docs/superpowers/plans/2026-07-28-mja-workflow-foundation.md，以及主线程已完成的 Batch 1 实现。若其中任何一项没有可消费的接口或验证记录，先停止 Batch 2 实现，不复制接口来绕过前置。
- 业务真值始终是 `/Users/gaoguobin/project/computer-use/tools/jianzhichuan_daily/workflows.py`。`/Users/gaoguobin/project/computer-use/tools/jianzhichuan_maa` 只提供历史校准和失败证据，不能直接当成完成实现。
- 直接消费 foundation 的 TaskPolicy、TaskStatus、TaskResult、VisualEvidence、ActionIntent、authorize_action、run_workflow、DailyWorkflowAction、RunDiagnostics，以及 foundation 已定义的 tools.run_cli --task。不得新增 parallel models.py、safety.py、engine.py、daily_workflow.py、diagnostics.py、run_cli.py 或第二个动作注册入口。
- 运行时 TaskStatus 只能是 completed、already_complete、not_eligible、blocked_safety、failed。live_pending 和 live_verified 只能由后续 aggregate admission 计划写入 verification/tasks/{TASK_ID}.json，不能写入 TaskResult.status、任务策略、pipeline 返回值或本批人工报告；Batch 2 不创建机器验证记录。
- canonical layout 固定如下：
  - agent/workflows/definitions/{lowercase task ID}.py
  - assets/resource/pipeline/daily/{lowercase task ID}.json
  - assets/resource/image/daily/{canonical task ID}/
  - tests/fixtures/{canonical task ID}/manifest.json、entry.png、actionable.png、completed.png、danger.png
  - tests/workflows/test_{lowercase task ID}.py
- 所有任务引用 assets/resource/calibration.json。当前校准可能是 1051x820 logical 和 923x720 MAA；任何历史坐标只能带 reference_size 作为归一化取样依据。不得把 1280x720 写成运行前提或新的固定窗口尺寸。输入点必须来自当前识别框，不能从 manifest、历史坐标或 pipeline ROI 直接盲点。
- 模板采集使用 capture fallback 已定义的当前 Maa MacOSController 截图链路。四个 PNG 必须是对应状态的真实采集结果，不得用绘制、复制、透明伪图或伪造 PNG 填充。PNG 缺失时夹具测试按计划保持 red，并明确报告缺失路径；采集后才转 green。
- 每个副作用页面必须同时有唯一页面证据和唯一目标证据；两者的 recognizer_frame_ids 必须等于同一个当前 frame_id。证据不完整、目标多于一个、页面不符、当前框失效或出现付费/登录/安全信号时，禁止输入。
- foundation 的 VisualEvidence.danger_hits 是同帧危险识别结果；每个 definition 和 fixture test 都消费该 Mapping[str, int]，任何正危险命中都先终止。foundation 的 SafetyReason.UNKNOWN_DIALOG 也属于硬停止原因，不能降级为普通 failed 或继续寻找目标。
- ¥、￥、Apple Pay、支付、充值、月卡、付费礼包、价格、登录、密码、验证码、生物识别、安全验证和无法确认货币的购买对话框均为硬停止。通用购买文字只有在同一帧明确识别到该任务批准的非付费存量资源时才可能授权，并且不能覆盖硬停止信号。
- 不发送键盘事件，不使用 standard Click、StartApp、空白区域恢复点击或猜测性全局坐标。任务只能在现有前台 MacOSController 和既有安全动作边界内运行。
- 每个 workflow 和每个动作都有显式上限。达到上限仍未验证后置条件时返回 failed，保存 failure evidence，不继续尝试。
- 诊断目录统一为 diagnostics/YYYY-MM-DD/TASK_ID/run-id/，至少保存 result.json、agent.log、maafw.log、action-trace.jsonl 和适用的 before.png、after.png、failure.png。本批只在 docs/verification/2026-07-28-mja-daily-workflows-batch-2.md 建立人工命令/结果/证据索引；后续 aggregate admission 计划独占 live_pending/live_verified 机器记录。
- 每个任务从已知入口开始，结束后验证后置条件；不得把日常任务领取、活动宝箱领取或与目标无关的 reward 节点加入本批任务。Hero 只保留真值中首个可见派遣项的完成态处理，且该处理也必须遵守同帧页面与目标证据。所有任务必须拥有 entry、actionable、completed、danger 四态夹具和 input-free recognition 测试。
- 每个实机任务开始前记录 `git rev-parse HEAD` 和 `git status --short`，从该 checkout 重组并校验 install，同时保存全桌面与 Maa 控制器的 before/after 截图及摘要到人工验收报告。
- 只能按任务的精确路径 git add。不能 git add .、git add -A、git add assets、git add tests、git add agent 或暂存 AGENTS.md。

## Predecessor Contract and File Map

Batch 2 消费的 foundation 接口形状如下；实际导入路径和实现以 foundation 已提交版本为准，任务文件只引用，不重新声明这些类型：

~~~python
from agent.workflows.models import TaskPolicy, TaskResult, TaskStatus
from agent.safety import ActionIntent, SafetyReason, VisualEvidence, authorize_action
from agent.workflows.engine import Decision, StateSnapshot, run_workflow
from agent.actions.daily_workflow import DailyWorkflowAction
from agent.diagnostics import RunDiagnostics

def run_workflow(
    definition: WorkflowDefinition,
    driver: WorkflowDriver,
    policy: TaskPolicy,
    diagnostics: RunDiagnostics,
    *,
    day: date | None = None,
) -> TaskResult: ...
~~~

Foundation 的 DailyWorkflowAction 已负责根据 canonical task ID 解析 definition 和 policy、创建 RunDiagnostics、适配 Maa context、调用 run_workflow、结束 Maa log 和 diagnostics。foundation 的 VisualEvidence 同时提供 page_hits、target_hits、recognizer_frame_ids、texts、resource_hits 和 danger_hits；Batch 2 不重新声明该模型。六个 definition 不创建 action class，也不直接启动 MaaPiCli。

每个任务的 Green 阶段按同一顺序完成三项增量注册：把唯一 TaskPolicy 写入 agent/workflows/catalog.py 的 TASK_POLICIES，把 definition 写入 agent/workflows/registry.py，把 definition 名称导出到 agent/workflows/definitions/__init__.py。definition 通过 registry 使用 TASK_POLICIES[TASK_ID]，不复制策略字段。

每一项只新增或修改以下路径：

~~~text
agent/workflows/definitions/hero_dispatch_daily.py
agent/workflows/definitions/buy_tea_daily.py
agent/workflows/definitions/spend_condensate_daily.py
agent/workflows/definitions/martial_study_breakthrough_daily.py
agent/workflows/definitions/eat_stamina_food_daily.py
agent/workflows/definitions/dungeon_sweep_daily.py

assets/resource/pipeline/daily/hero_dispatch_daily.json
assets/resource/pipeline/daily/buy_tea_daily.json
assets/resource/pipeline/daily/spend_condensate_daily.json
assets/resource/pipeline/daily/martial_study_breakthrough_daily.json
assets/resource/pipeline/daily/eat_stamina_food_daily.json
assets/resource/pipeline/daily/dungeon_sweep_daily.json

assets/resource/image/daily/HERO_DISPATCH_DAILY/
assets/resource/image/daily/BUY_TEA_DAILY/
assets/resource/image/daily/SPEND_CONDENSATE_DAILY/
assets/resource/image/daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/
assets/resource/image/daily/EAT_STAMINA_FOOD_DAILY/
assets/resource/image/daily/DUNGEON_SWEEP_DAILY/

tests/fixtures/HERO_DISPATCH_DAILY/manifest.json, entry.png, actionable.png, completed.png, danger.png
tests/fixtures/BUY_TEA_DAILY/manifest.json, entry.png, actionable.png, completed.png, danger.png
tests/fixtures/SPEND_CONDENSATE_DAILY/manifest.json, entry.png, actionable.png, completed.png, danger.png
tests/fixtures/MARTIAL_STUDY_BREAKTHROUGH_DAILY/manifest.json, entry.png, actionable.png, completed.png, danger.png
tests/fixtures/EAT_STAMINA_FOOD_DAILY/manifest.json, entry.png, actionable.png, completed.png, danger.png
tests/fixtures/DUNGEON_SWEEP_DAILY/manifest.json, entry.png, actionable.png, completed.png, danger.png

tests/workflows/test_hero_dispatch_daily.py
tests/workflows/test_buy_tea_daily.py
tests/workflows/test_spend_condensate_daily.py
tests/workflows/test_martial_study_breakthrough_daily.py
tests/workflows/test_eat_stamina_food_daily.py
tests/workflows/test_dungeon_sweep_daily.py

assets/interface.json
~~~

Batch 2 不修改 foundation 已有的 agent/workflows/models.py、agent/safety.py、agent/workflows/engine.py、agent/actions/daily_workflow.py、agent/diagnostics.py、tools/run_cli.py，也不修改 AGENTS.md。每个任务都增量更新 foundation 已有的 agent/workflows/catalog.py、agent/workflows/registry.py 和 agent/workflows/definitions/__init__.py，并在 assets/interface.json 的 singular task 数组中增加一个已测试的 lowercase task entry。每个 definition 只从 TASK_POLICIES[TASK_ID] 消费 policy，不声明本模块 POLICY 或其他并行策略真值。保留已有 mail_smoke_test、mja resource、macos controller 和 agent.child_args 仅为 agent/main.py；socket ID 由 MaaPiCli 追加，不写进 child_args。

每个 pipeline 的入口和 interface 对应关系必须是：

~~~json
{
  "name": "hero_dispatch_daily",
  "entry": "MJA_Daily_HERO_DISPATCH_DAILY",
  "default_check": false,
  "resource": ["mja"],
  "controller": ["macos"]
}
~~~

对应的 pipeline 最小 contract 必须保留识别和 custom action 分离：

~~~json
{
  "MJA_Daily_HERO_DISPATCH_DAILY": {
    "recognition": "DirectHit",
    "action": "Custom",
    "custom_action": "DailyWorkflowAction",
    "custom_action_param": {
      "task_id": "HERO_DISPATCH_DAILY"
    }
  }
}
~~~

assets/interface.json 使用 ProjectInterface 的 singular task key，任务 name 是 lowercase CLI 选择值，entry 是 canonical uppercase ID：

~~~json
{
  "task": [
    {
      "name": "buy_tea_daily",
      "label": "购买茶叶",
      "entry": "MJA_Daily_BUY_TEA_DAILY",
      "default_check": false,
      "resource": ["mja"],
      "controller": ["macos"]
    }
  ]
}
~~~

实际 pipeline 必须为 **Files:** 中每个被 definition 引用的模板增加唯一 recognizer-only `DoNothing` 节点；模板值相对 `assets/resource/image/`，因此统一写成 `daily/{TASK_ID}/file.png`，不能写成 `image/daily/...`。只有 `MJA_Daily_{TASK_ID}` 根节点使用 `Custom`/`DailyWorkflowAction`；不能增加 standard Click、StartApp、Key、Input 或第二个自定义输入节点。模板和 pipeline 的 ROI 由 calibration.json 的 MAA 尺寸解释；若 pipeline 需要 reference_size，必须明确写出校准面尺寸并由 loader 做归一化，不能假设 1280x720。

每个 fixture manifest 至少遵守以下结构，expected_status 只能写五态之一或 null：

~~~json
{
  "schema_version": 1,
  "task_id": "HERO_DISPATCH_DAILY",
  "reference_size": [923, 720],
  "cases": {
    "entry": {
      "image": "entry.png",
      "expected_page": "dispatch_page",
      "expected_targets": ["first_visible_dispatch_row"],
      "expected_status": null
    },
    "actionable": {
      "image": "actionable.png",
      "expected_page": "dispatch_page",
      "expected_targets": ["first_visible_dispatch_row", "dispatch_action"],
      "expected_status": null
    },
    "completed": {
      "image": "completed.png",
      "expected_page": "dispatch_page",
      "expected_targets": ["first_visible_dispatch_row_completed"],
      "expected_status": "already_complete"
    },
    "danger": {
      "image": "danger.png",
      "expected_page": "dispatch_page",
      "expected_targets": ["paid_or_verification_signal", "unknown_dialog"],
      "expected_status": "blocked_safety"
    }
  }
}
~~~

For entries and actions, tests assert expected_page and expected_targets use the same frame ID and no input is issued during recognition. The completed case proves the no-op branch. The danger case proves blocked_safety for paid, verification, or UNKNOWN_DIALOG evidence and proves the input spy saw no click, swipe, long press, keyboard event or process launch.

## Implementation Sequence

### Task 1: Implement HERO_DISPATCH_DAILY with first-visible-item and six-team bounds

**Business truth:** Read the relevant HERO_DISPATCH_DAILY branch in /Users/gaoguobin/project/computer-use/tools/jianzhichuan_daily/workflows.py before writing tests. Preserve these exact rules: inspect only the first visible dispatch item, handle its own completed-dispatch state before dispatching, never scroll, and dispatch at most six teams in one run. Do not claim daily-task rewards or unrelated rewards.

**Files:**

- Create: `agent/workflows/definitions/hero_dispatch_daily.py`
- Create: `assets/resource/pipeline/daily/hero_dispatch_daily.json`
- Create: `assets/resource/image/daily/HERO_DISPATCH_DAILY/entry.png`
- Create: `assets/resource/image/daily/HERO_DISPATCH_DAILY/painting_scroll_entry.png`
- Create: `assets/resource/image/daily/HERO_DISPATCH_DAILY/hero_dispatch_entry.png`
- Create: `assets/resource/image/daily/HERO_DISPATCH_DAILY/dispatch_page.png`
- Create: `assets/resource/image/daily/HERO_DISPATCH_DAILY/first_visible_dispatch_row.png`
- Create: `assets/resource/image/daily/HERO_DISPATCH_DAILY/dispatch_action.png`
- Create: `assets/resource/image/daily/HERO_DISPATCH_DAILY/dispatch_claim_target.png`
- Create: `assets/resource/image/daily/HERO_DISPATCH_DAILY/smart_configure.png`
- Create: `assets/resource/image/daily/HERO_DISPATCH_DAILY/team_dispatch_confirm.png`
- Create: `assets/resource/image/daily/HERO_DISPATCH_DAILY/expected_reward_popup_close.png`
- Create: `assets/resource/image/daily/HERO_DISPATCH_DAILY/first_visible_dispatch_complete.png`
- Create: `tests/fixtures/HERO_DISPATCH_DAILY/manifest.json`
- Create: `tests/fixtures/HERO_DISPATCH_DAILY/entry.png`
- Create: `tests/fixtures/HERO_DISPATCH_DAILY/actionable.png`
- Create: `tests/fixtures/HERO_DISPATCH_DAILY/completed.png`
- Create: `tests/fixtures/HERO_DISPATCH_DAILY/danger.png`
- Update: `agent/workflows/catalog.py` (TASK_POLICIES entry)
- Update: `agent/workflows/registry.py` (definition registration)
- Update: `agent/workflows/definitions/__init__.py` (definition export)
- Create: `tests/workflows/test_hero_dispatch_daily.py`
- Update: `assets/interface.json` (one singular task entry only)

**Interfaces:**

~~~python
TASK_ID = "HERO_DISPATCH_DAILY"
MAX_TEAMS = 6
MAX_FIRST_ITEM_CLAIMS = 6

from agent.safety import ActionIntent
from agent.workflows.engine import Transition

TRANSITIONS = {
    "home": Transition("home", ActionIntent("open_painting_scroll", "home", "painting_scroll_entry"), "click", {}, "painting", "painting_page"),
    "painting": Transition("painting", ActionIntent("open_hero_dispatch", "painting_page", "hero_dispatch_entry"), "click", {}, "dispatch", "dispatch_page"),
    "claim": Transition("dispatch", ActionIntent("claim_first_dispatch", "dispatch_page", "first_visible_dispatch_claim"), "click", {}, "claim_result", "dispatch_claim_result"),
    "dismiss_claim": Transition("claim_result", ActionIntent("dismiss_dispatch_claim_result", "dispatch_claim_result", "expected_reward_popup_close"), "click", {}, "dispatch", "dispatch_page"),
    "select": Transition("dispatch", ActionIntent("select_first_visible_dispatch", "dispatch_page", "first_visible_dispatch_row"), "click", {}, "team_setup", "smart_configure"),
    "configure": Transition("team_setup", ActionIntent("smart_configure_team", "team_setup_page", "smart_configure"), "click", {}, "team_ready", "team_dispatch_confirm"),
    "dispatch": Transition("team_ready", ActionIntent("dispatch_team", "team_ready_page", "team_dispatch_confirm"), "click", {}, "dispatch", "dispatch_page"),
}

TERMINAL_MARKERS = {
    "already_or_completed": "first_visible_dispatch_in_progress",
    "dispatchable": "first_visible_dispatch_row",
    "claimable": "first_visible_dispatch_claim",
}
~~~

The only policy source is appended to agent/workflows/catalog.py:

~~~python
TASK_POLICIES[TASK_ID] = TaskPolicy(
    task_id=TASK_ID,
    label="侠客派遣",
    entry="MJA_Daily_HERO_DISPATCH_DAILY",
    risk_levels=frozenset({RiskLevel.STATEFUL}),
    max_steps=64,
    action_caps={
        "open_painting_scroll": 1,
        "open_hero_dispatch": 1,
        "claim_first_dispatch": MAX_FIRST_ITEM_CLAIMS,
        "dismiss_dispatch_claim_result": MAX_FIRST_ITEM_CLAIMS,
        "select_first_visible_dispatch": MAX_TEAMS,
        "smart_configure_team": MAX_TEAMS,
        "dispatch_team": MAX_TEAMS,
    },
    approved_resources=frozenset(),
)
~~~

The definition uses `initial_state = "home"` and recognizes the current state's page, transition target, transition postcondition, `first_visible_dispatch_claim`, `first_visible_dispatch_row`, `dispatch_action`, `first_visible_dispatch_in_progress`, and all unconditional safety markers. It never exposes a scroll, daily-task claim, activity-chest claim or unrelated reward transition. In `dispatch`, decision priority is danger, exact in-progress marker, exact claimable marker, then exact dispatchable marker. Claiming recaptures and either dismisses only the expected non-paid result or rechecks the first row. A dispatchable first row must show `派遣` or `耗时 x小时`; it is selected, then `智能配置` is applied to that team, then the final `派遣` target is clicked. Each of those three targets is independently recognized in its own current frame. Only explicit `正在派遣中`, `派遣中`, or a remaining countdown with no dispatch action is terminal. Return `completed` when any protected claim/dispatch counter changed, `already_complete` only for that explicit terminal state before protected input, `failed/HERO_FIRST_VISIBLE_UNRESOLVED` for every ambiguous or actionless row, and `failed/HERO_DISPATCH_CAP` when six teams are reached without the terminal marker. Never inspect a second row and never scroll.

**Pipeline contract:**

~~~json
{
  "MJA_Daily_HERO_DISPATCH_DAILY": {
    "recognition": "DirectHit",
    "action": "Custom",
    "custom_action": "DailyWorkflowAction",
    "custom_action_param": {"task_id": "HERO_DISPATCH_DAILY"}
  },
  "MJA_HERO_DISPATCH_DAILY_PAGE": {
    "recognition": "TemplateMatch",
    "template": "daily/HERO_DISPATCH_DAILY/dispatch_page.png",
    "action": "DoNothing",
    "next": ["MJA_HERO_DISPATCH_DAILY_ACTION"]
  },
  "MJA_HERO_DISPATCH_DAILY_ACTION": {
    "recognition": "TemplateMatch",
    "template": "daily/HERO_DISPATCH_DAILY/dispatch_action.png",
    "action": "DoNothing"
  },
  "MJA_HERO_DISPATCH_DAILY_CLAIM": {
    "recognition": "TemplateMatch",
    "template": "daily/HERO_DISPATCH_DAILY/dispatch_claim_target.png",
    "action": "DoNothing"
  }
}
~~~

The definition, not a fixed pipeline coordinate, supplies the current recognized box to the existing MacOSForegroundClick boundary.

**TDD, live verification, and handoff:**

- [ ] **Red, 3 minutes:** Add tests for policy exactness, normal first-row dispatch to completed, already_complete in-progress no-op, failed cap/postcondition, blocked_safety paid/verification/UNKNOWN_DIALOG danger via snapshot.evidence.danger_hits, no scroll/no daily-task claim/no reward action IDs, first-row claim handling, and unique page-plus-target same-frame evidence.
- [ ] **Red, 2 minutes:** Run install/.venv/bin/python -m pytest tests/workflows/test_hero_dispatch_daily.py -q. Expected collection failure: ModuleNotFoundError: No module named 'agent.workflows.definitions.hero_dispatch_daily'.
- [ ] **Green implementation, 5 minutes:** Add the immutable policy and deterministic state table above. It claims only the first visible completed dispatch when the claim target is unique, then recaptures; every dispatched team goes through select-first-row, 智能配置 and 派遣, with a cap of six for each repeated protected action. It returns already_complete only when the first row has an explicit in-progress/countdown marker before protected input; an ambiguous or actionless row is failed, not already complete. It returns completed only after a post-action terminal marker, failed on cap or unchanged postcondition, and blocked_safety on danger evidence.
- [ ] **Green pipeline and interface, 3 minutes:** Add recognizer-only nodes and the DailyWorkflowAction entry. Verify no standard Click, StartApp, Key or Input action appears and the entry name exactly matches MJA_Daily_HERO_DISPATCH_DAILY.
- [ ] **Green fixtures, 4 minutes:** Capture the four live state PNGs with the calibrated Maa controller. Write manifest with exactly schema_version, task_id, reference_size and cases.entry/actionable/completed/danger; each case contains only image, expected_page, expected_targets and expected_status. Use expected_page dispatch_page and expected_targets for first_visible_dispatch_row, dispatch_action, completed marker and paid_or_verification_signal or unknown_dialog. Do not fabricate any PNG.
- [ ] **Green fixture tests, 3 minutes:** Run the foundation fixture validator and this test. Expected all four images decode, same-frame evidence is true, actionable executes only a recognized first-row action, completed emits no input, and danger returns blocked_safety.
- [ ] **Live verification, 5 minutes:** Run install/.venv/bin/python -m tools.run_cli --task hero_dispatch_daily from the authorized foreground host. Save the pre-action capture, after-action capture, action trace and result under diagnostics/YYYY-MM-DD/HERO_DISPATCH_DAILY/run-id/ and append their relative paths plus the five-state TaskResult to docs/verification/2026-07-28-mja-daily-workflows-batch-2.md. Do not create verification/tasks/HERO_DISPATCH_DAILY.json; the later aggregate admission plan creates that machine record.
- [ ] **Live postcondition/no-op, 4 minutes:** Verify only the first visible item changed, every team used 智能配置 before 派遣, no scroll occurred, no daily-task claim, activity-chest claim or unrelated reward control was used, and the dispatched team count never exceeded six. The first-row dispatch claim, when present in the source state, must have its own same-frame trace. Re-run after the explicit in-progress/countdown postcondition is visible; expect already_complete with zero claim/configure/dispatch inputs and a second diagnostics run directory. Any paid, login, unknown, ambiguous or failed postcondition must be blocked_safety or failed with evidence.
- [ ] **Commit, 2 minutes:**
~~~bash
git add -- agent/workflows/catalog.py agent/workflows/registry.py agent/workflows/definitions/__init__.py \
  agent/workflows/definitions/hero_dispatch_daily.py \
  assets/resource/pipeline/daily/hero_dispatch_daily.json \
  assets/resource/image/daily/HERO_DISPATCH_DAILY/entry.png \
  assets/resource/image/daily/HERO_DISPATCH_DAILY/painting_scroll_entry.png \
  assets/resource/image/daily/HERO_DISPATCH_DAILY/hero_dispatch_entry.png \
  assets/resource/image/daily/HERO_DISPATCH_DAILY/dispatch_page.png \
  assets/resource/image/daily/HERO_DISPATCH_DAILY/first_visible_dispatch_row.png \
  assets/resource/image/daily/HERO_DISPATCH_DAILY/dispatch_action.png \
  assets/resource/image/daily/HERO_DISPATCH_DAILY/dispatch_claim_target.png \
  assets/resource/image/daily/HERO_DISPATCH_DAILY/smart_configure.png \
  assets/resource/image/daily/HERO_DISPATCH_DAILY/team_dispatch_confirm.png \
  assets/resource/image/daily/HERO_DISPATCH_DAILY/expected_reward_popup_close.png \
  assets/resource/image/daily/HERO_DISPATCH_DAILY/first_visible_dispatch_complete.png \
  tests/fixtures/HERO_DISPATCH_DAILY/manifest.json \
  tests/fixtures/HERO_DISPATCH_DAILY/entry.png \
  tests/fixtures/HERO_DISPATCH_DAILY/actionable.png \
  tests/fixtures/HERO_DISPATCH_DAILY/completed.png \
  tests/fixtures/HERO_DISPATCH_DAILY/danger.png \
  tests/workflows/test_hero_dispatch_daily.py \
  assets/interface.json
git commit -m "feat: add hero dispatch daily workflow"
~~~

### Task 2: Implement BUY_TEA_DAILY with stock interpretation and usable-inventory verification

**Business truth:** Read the BUY_TEA_DAILY branch in workflows.py. Preserve the distinction that a displayed 10/10 means ten units remain available, not that ten units have already been bought. Select the full currently available quantity in the quantity control and confirm one non-paid purchase, including quantity ten when the screen says 10/10; verify that the purchased units are usable.

**Files:**

- Create: `agent/workflows/definitions/buy_tea_daily.py`
- Create: `assets/resource/pipeline/daily/buy_tea_daily.json`
- Create: `assets/resource/image/daily/BUY_TEA_DAILY/entry.png`
- Create: `assets/resource/image/daily/BUY_TEA_DAILY/painting_scroll_entry.png`
- Create: `assets/resource/image/daily/BUY_TEA_DAILY/yanwu_world_tab.png`
- Create: `assets/resource/image/daily/BUY_TEA_DAILY/universal_shop_entry.png`
- Create: `assets/resource/image/daily/BUY_TEA_DAILY/tea_tab.png`
- Create: `assets/resource/image/daily/BUY_TEA_DAILY/tea_shop_page.png`
- Create: `assets/resource/image/daily/BUY_TEA_DAILY/tea_purchase_target.png`
- Create: `assets/resource/image/daily/BUY_TEA_DAILY/tea_stock_counter.png`
- Create: `assets/resource/image/daily/BUY_TEA_DAILY/quantity_max.png`
- Create: `assets/resource/image/daily/BUY_TEA_DAILY/quantity_readout.png`
- Create: `assets/resource/image/daily/BUY_TEA_DAILY/condensate_cost.png`
- Create: `assets/resource/image/daily/BUY_TEA_DAILY/buy_confirm.png`
- Create: `assets/resource/image/daily/BUY_TEA_DAILY/sold_out.png`
- Create: `assets/resource/image/daily/BUY_TEA_DAILY/expected_purchase_result_close.png`
- Create: `assets/resource/image/daily/BUY_TEA_DAILY/usable_tea_inventory.png`
- Create: `tests/fixtures/BUY_TEA_DAILY/manifest.json`
- Create: `tests/fixtures/BUY_TEA_DAILY/entry.png`
- Create: `tests/fixtures/BUY_TEA_DAILY/actionable.png`
- Create: `tests/fixtures/BUY_TEA_DAILY/completed.png`
- Create: `tests/fixtures/BUY_TEA_DAILY/danger.png`
- Update: `agent/workflows/catalog.py` (TASK_POLICIES entry)
- Update: `agent/workflows/registry.py` (definition registration)
- Update: `agent/workflows/definitions/__init__.py` (definition export)
- Create: `tests/workflows/test_buy_tea_daily.py`
- Update: `assets/interface.json` (one singular task entry only)

**Interfaces:**

~~~python
TASK_ID = "BUY_TEA_DAILY"
APPROVED_RESOURCE = "凝晶"
MAX_PURCHASES = 1
MAX_QUANTITY = 10

from agent.safety import ActionIntent
from agent.workflows.engine import Transition

def parse_available_stock(text: str) -> int:
    available, separator, limit = text.replace(" ", "").partition("/")
    if separator != "/" or not available.isdigit() or not limit.isdigit():
        raise ValueError("tea stock must be an integer remaining/limit counter")
    value = int(available)
    if int(limit) != MAX_QUANTITY or value > MAX_QUANTITY:
        raise ValueError("tea stock exceeds the finite quantity cap")
    return value

TRANSITIONS = {
    "home": Transition("home", ActionIntent("open_painting_scroll", "home", "painting_scroll_entry"), "click", {}, "painting", "painting_page"),
    "painting": Transition("painting", ActionIntent("select_yanwu_world", "painting_page", "yanwu_world_tab"), "click", {}, "yanwu", "yanwu_world_page"),
    "yanwu": Transition("yanwu", ActionIntent("open_universal_shop", "yanwu_world_page", "universal_shop_entry"), "click", {}, "shop", "universal_shop_page"),
    "shop": Transition("shop", ActionIntent("open_tea_tab", "universal_shop_page", "tea_tab"), "click", {}, "tea", "tea_shop_page"),
    "tea": Transition("tea", ActionIntent("open_tea_purchase", "tea_shop_page", "tea_purchase_target"), "click", {}, "quantity", "quantity_panel"),
    "quantity": Transition("quantity", ActionIntent("set_tea_quantity_max", "quantity_panel", "quantity_max"), "click", {}, "quantity_ready", "quantity_readout"),
    "buy": Transition("quantity_ready", ActionIntent("buy_tea", "quantity_panel", "buy_confirm", APPROVED_RESOURCE), "click", {}, "purchase_result", "expected_purchase_result"),
    "dismiss": Transition("purchase_result", ActionIntent("dismiss_tea_purchase_result", "expected_purchase_result", "expected_purchase_result_close"), "click", {}, "verify", "tea_shop_page"),
}
~~~

The only policy source is appended to agent/workflows/catalog.py:

~~~python
TASK_POLICIES[TASK_ID] = TaskPolicy(
    task_id=TASK_ID,
    label="购买茶叶",
    entry="MJA_Daily_BUY_TEA_DAILY",
    risk_levels=frozenset({RiskLevel.CONSUMPTIVE}),
    max_steps=32,
    action_caps={
        "open_painting_scroll": 1,
        "select_yanwu_world": 1,
        "open_universal_shop": 1,
        "open_tea_tab": 1,
        "open_tea_purchase": 1,
        "set_tea_quantity_max": 1,
        "buy_tea": 1,
        "dismiss_tea_purchase_result": 1,
    },
    approved_resources=frozenset({"凝晶"}),
)
~~~

OCR parsing must convert 10/10 to available_count=10 and never to purchased_count=10. It must reject any denominator other than 10, a missing denominator, non-integer text, mixed currency, or a counter whose page evidence is not the tea shop page. `initial_state` is `home`. In `tea`, exact 0/10, 售罄/已售罄, or a clearly disabled buy target is terminal; the status is `already_complete` before `buy_tea` and `completed` after it. For positive stock, `open_tea_purchase`, `set_tea_quantity_max`, and `buy_tea` are three separate recaptured transitions. Before `buy_tea`, the unique quantity readout must equal the previously parsed available count, and the same frame must contain the exact stored-resource `凝晶` cost and no danger marker. The buy intent uses page marker `quantity_panel`, target marker `buy_confirm`, and approved_resource 凝晶. After the expected result is closed, re-read remaining stock and verify both a stock decrease to zero/sold-out/disabled and a usable tea inventory increase; unchanged stock, a mismatched quantity, or missing usability evidence is `failed/TEA_PURCHASE_UNVERIFIED`. The reference daily row `消耗 100 凝晶` is not evidence that tea has already been bought.

**Pipeline contract:**

~~~json
{
  "MJA_Daily_BUY_TEA_DAILY": {
    "recognition": "DirectHit",
    "action": "Custom",
    "custom_action": "DailyWorkflowAction",
    "custom_action_param": {"task_id": "BUY_TEA_DAILY"}
  },
  "MJA_BUY_TEA_DAILY_STOCK": {
    "recognition": "OCR",
    "text": "茶叶",
    "action": "DoNothing",
    "next": ["MJA_BUY_TEA_DAILY_PURCHASE"]
  },
  "MJA_BUY_TEA_DAILY_PURCHASE": {
    "recognition": "TemplateMatch",
    "template": "daily/BUY_TEA_DAILY/tea_purchase_target.png",
    "action": "DoNothing"
  }
}
~~~

**TDD, live verification, and handoff:**

- [ ] **Red, 3 minutes:** Test normal full-quantity purchase to completed, already_complete zero-stock no-op, failed stock/postcondition, blocked_safety paid/verification/UNKNOWN_DIALOG danger_hits, stock parsing for 10/10, 0/10, 3/10 and missing denominator, same-frame 凝晶 evidence, quantity cap ten and purchase action cap one.
- [ ] **Red, 2 minutes:** Run install/.venv/bin/python -m pytest tests/workflows/test_buy_tea_daily.py -q. Expected collection failure: ModuleNotFoundError: No module named 'agent.workflows.definitions.buy_tea_daily'.
- [ ] **Green implementation, 5 minutes:** Implement deterministic stock parsing and the exact route/open/max/buy/verify transitions above. Return already_complete with zero purchase inputs for 0/10, sold-out or disabled purchase state; return completed only after remaining stock and usable-inventory delta are verified; return blocked_safety for paid/unknown purchase evidence; return failed for inconsistent stock, quantity or postcondition. A 10/10 fixture must produce one max-control input and one buy input whose verified quantity is 10, never ten unbounded clicks and never a synthetic multi-input `quantity` argument on one click.
- [ ] **Green pipeline and interface, 3 minutes:** Add the pipeline and append this exact entry, preserving agent.child_args as agent/main.py:
~~~json
{
  "name": "buy_tea_daily",
  "label": "购买茶叶",
  "entry": "MJA_Daily_BUY_TEA_DAILY",
  "default_check": false,
  "resource": ["mja"],
  "controller": ["macos"]
}
~~~
- [ ] **Green fixtures, 4 minutes:** Capture entry, actionable with 10/10, completed with zero remaining stock and usable inventory, and danger with payment, verification or UNKNOWN_DIALOG evidence. Manifest contains exactly schema_version, task_id, reference_size and cases; each case contains image, expected_page, expected_targets and expected_status. expected_status is null for entry/actionable, already_complete for completed, blocked_safety for danger.
- [ ] **Green fixture tests, 3 minutes:** Run the fixture validator and this test. Expected the actionable case schedules one bounded purchase with quantity 10 when 10/10 is present, completed has no input, and danger has no input.
- [ ] **Live verification, 5 minutes:** Run install/.venv/bin/python -m tools.run_cli --task buy_tea_daily. Save diagnostics/YYYY-MM-DD/BUY_TEA_DAILY/run-id/ and append its relative paths to docs/verification/2026-07-28-mja-daily-workflows-batch-2.md. Record the before stock, the one authorized full-quantity purchase, after stock, inventory usability marker and final TaskResult; leave verification/tasks/BUY_TEA_DAILY.json for the later aggregate admission plan.
- [ ] **Live postcondition/no-op, 4 minutes:** Prove that 10/10 resulted in one max-control selection, a visible quantity 10, one stored-凝晶 purchase, zero/sold-out/disabled remaining stock, and usable purchased tea. Re-run with zero stock; expect already_complete and zero open-purchase/max/buy inputs. A paid signal, unknown currency, inconsistent count or ambiguous target is blocked_safety or failed and must stop.
- [ ] **Commit, 2 minutes:**
~~~bash
git add -- agent/workflows/catalog.py agent/workflows/registry.py agent/workflows/definitions/__init__.py \
  agent/workflows/definitions/buy_tea_daily.py \
  assets/resource/pipeline/daily/buy_tea_daily.json \
  assets/resource/image/daily/BUY_TEA_DAILY/entry.png \
  assets/resource/image/daily/BUY_TEA_DAILY/painting_scroll_entry.png \
  assets/resource/image/daily/BUY_TEA_DAILY/yanwu_world_tab.png \
  assets/resource/image/daily/BUY_TEA_DAILY/universal_shop_entry.png \
  assets/resource/image/daily/BUY_TEA_DAILY/tea_tab.png \
  assets/resource/image/daily/BUY_TEA_DAILY/tea_shop_page.png \
  assets/resource/image/daily/BUY_TEA_DAILY/tea_purchase_target.png \
  assets/resource/image/daily/BUY_TEA_DAILY/tea_stock_counter.png \
  assets/resource/image/daily/BUY_TEA_DAILY/quantity_max.png \
  assets/resource/image/daily/BUY_TEA_DAILY/quantity_readout.png \
  assets/resource/image/daily/BUY_TEA_DAILY/condensate_cost.png \
  assets/resource/image/daily/BUY_TEA_DAILY/buy_confirm.png \
  assets/resource/image/daily/BUY_TEA_DAILY/sold_out.png \
  assets/resource/image/daily/BUY_TEA_DAILY/expected_purchase_result_close.png \
  assets/resource/image/daily/BUY_TEA_DAILY/usable_tea_inventory.png \
  tests/fixtures/BUY_TEA_DAILY/manifest.json \
  tests/fixtures/BUY_TEA_DAILY/entry.png \
  tests/fixtures/BUY_TEA_DAILY/actionable.png \
  tests/fixtures/BUY_TEA_DAILY/completed.png \
  tests/fixtures/BUY_TEA_DAILY/danger.png \
  tests/workflows/test_buy_tea_daily.py \
  assets/interface.json
git commit -m "feat: add buy tea daily workflow"
~~~

### Task 3: Implement SPEND_CONDENSATE_DAILY with two stores and 10000 verification

**Business truth:** Read the SPEND_CONDENSATE_DAILY branch in workflows.py. Preserve both purchase sources: the 偃武世界 regional-currency shop and the 云州 regional-currency shop. On each page, buy the full currently visible stock using stored 凝晶 only, then reopen 日常任务 and verify the 消耗10000凝晶 progress is complete or claimable without claiming its reward.

**Files:**

- Create: `agent/workflows/definitions/spend_condensate_daily.py`
- Create: `assets/resource/pipeline/daily/spend_condensate_daily.json`
- Create: `assets/resource/image/daily/SPEND_CONDENSATE_DAILY/entry.png`
- Create: `assets/resource/image/daily/SPEND_CONDENSATE_DAILY/function_panel_entry.png`
- Create: `assets/resource/image/daily/SPEND_CONDENSATE_DAILY/daily_tasks_entry.png`
- Create: `assets/resource/image/daily/SPEND_CONDENSATE_DAILY/daily_tasks_close.png`
- Create: `assets/resource/image/daily/SPEND_CONDENSATE_DAILY/painting_scroll_entry.png`
- Create: `assets/resource/image/daily/SPEND_CONDENSATE_DAILY/yanwu_world_tab.png`
- Create: `assets/resource/image/daily/SPEND_CONDENSATE_DAILY/yunzhou_tab.png`
- Create: `assets/resource/image/daily/SPEND_CONDENSATE_DAILY/yanwu_currency_shop.png`
- Create: `assets/resource/image/daily/SPEND_CONDENSATE_DAILY/yunzhou_currency_shop.png`
- Create: `assets/resource/image/daily/SPEND_CONDENSATE_DAILY/yanwu_currency_purchase_target.png`
- Create: `assets/resource/image/daily/SPEND_CONDENSATE_DAILY/yunzhou_currency_purchase_target.png`
- Create: `assets/resource/image/daily/SPEND_CONDENSATE_DAILY/yanwu_stock_counter.png`
- Create: `assets/resource/image/daily/SPEND_CONDENSATE_DAILY/yunzhou_stock_counter.png`
- Create: `assets/resource/image/daily/SPEND_CONDENSATE_DAILY/quantity_max.png`
- Create: `assets/resource/image/daily/SPEND_CONDENSATE_DAILY/condensate_cost.png`
- Create: `assets/resource/image/daily/SPEND_CONDENSATE_DAILY/buy_confirm.png`
- Create: `assets/resource/image/daily/SPEND_CONDENSATE_DAILY/expected_reward_popup_close.png`
- Create: `assets/resource/image/daily/SPEND_CONDENSATE_DAILY/daily_progress_10000.png`
- Create: `tests/fixtures/SPEND_CONDENSATE_DAILY/manifest.json`
- Create: `tests/fixtures/SPEND_CONDENSATE_DAILY/entry.png`
- Create: `tests/fixtures/SPEND_CONDENSATE_DAILY/actionable.png`
- Create: `tests/fixtures/SPEND_CONDENSATE_DAILY/completed.png`
- Create: `tests/fixtures/SPEND_CONDENSATE_DAILY/danger.png`
- Update: `agent/workflows/catalog.py` (TASK_POLICIES entry)
- Update: `agent/workflows/registry.py` (definition registration)
- Update: `agent/workflows/definitions/__init__.py` (definition export)
- Create: `tests/workflows/test_spend_condensate_daily.py`
- Update: `assets/interface.json` (one singular task entry only)

**Interfaces:**

~~~python
TASK_ID = "SPEND_CONDENSATE_DAILY"
APPROVED_RESOURCE = "凝晶"
STORE_ORDER = ("yanwu_currency_shop", "yunzhou_currency_shop")
TARGET_PROGRESS = 10000

from agent.safety import ActionIntent
from agent.workflows.engine import Transition

TRANSITIONS = (
    Transition("home", ActionIntent("open_function_panel", "home", "function_panel_entry"), "click", {}, "function_panel_initial", "function_panel_page"),
    Transition("function_panel_initial", ActionIntent("open_daily_tasks_initial", "function_panel_page", "daily_tasks_entry"), "click", {}, "daily_initial", "daily_tasks_page"),
    Transition("daily_initial", ActionIntent("close_daily_tasks", "daily_tasks_page", "daily_tasks_close"), "click", {}, "home_after_progress", "home"),
    Transition("home_after_progress", ActionIntent("open_painting_scroll", "home", "painting_scroll_entry"), "click", {}, "painting", "painting_page"),
    Transition("painting", ActionIntent("select_yanwu_world", "painting_page", "yanwu_world_tab"), "click", {}, "yanwu", "yanwu_currency_shop"),
    Transition("yanwu", ActionIntent("open_yanwu_currency_purchase", "yanwu_currency_shop", "yanwu_currency_purchase_target"), "click", {}, "yanwu_quantity", "yanwu_quantity_panel"),
    Transition("yanwu_quantity", ActionIntent("set_yanwu_quantity_max", "yanwu_quantity_panel", "quantity_max"), "click", {}, "yanwu_ready", "yanwu_quantity_readout"),
    Transition("yanwu_ready", ActionIntent("buy_yanwu_currency_max", "yanwu_quantity_panel", "buy_confirm", APPROVED_RESOURCE), "click", {}, "yanwu_result", "expected_yanwu_reward_popup"),
    Transition("yanwu_result", ActionIntent("dismiss_yanwu_reward_popup", "expected_yanwu_reward_popup", "expected_reward_popup_close"), "click", {}, "painting_after_yanwu", "painting_page"),
    Transition("painting_after_yanwu", ActionIntent("select_yunzhou", "painting_page", "yunzhou_tab"), "click", {}, "yunzhou", "yunzhou_currency_shop"),
    Transition("yunzhou", ActionIntent("open_yunzhou_currency_purchase", "yunzhou_currency_shop", "yunzhou_currency_purchase_target"), "click", {}, "yunzhou_quantity", "yunzhou_quantity_panel"),
    Transition("yunzhou_quantity", ActionIntent("set_yunzhou_quantity_max", "yunzhou_quantity_panel", "quantity_max"), "click", {}, "yunzhou_ready", "yunzhou_quantity_readout"),
    Transition("yunzhou_ready", ActionIntent("buy_yunzhou_currency_max", "yunzhou_quantity_panel", "buy_confirm", APPROVED_RESOURCE), "click", {}, "yunzhou_result", "expected_yunzhou_reward_popup"),
    Transition("yunzhou_result", ActionIntent("dismiss_yunzhou_reward_popup", "expected_yunzhou_reward_popup", "expected_reward_popup_close"), "click", {}, "home_for_verify", "home"),
    Transition("home_for_verify", ActionIntent("open_function_panel_verify", "home", "function_panel_entry"), "click", {}, "function_panel_verify", "function_panel_page"),
    Transition("function_panel_verify", ActionIntent("open_daily_tasks_verify", "function_panel_page", "daily_tasks_entry"), "click", {}, "daily_verify", "daily_tasks_page"),
)
~~~

The only policy source is appended to agent/workflows/catalog.py:

~~~python
TASK_POLICIES[TASK_ID] = TaskPolicy(
    task_id=TASK_ID,
    label="消耗凝晶",
    entry="MJA_Daily_SPEND_CONDENSATE_DAILY",
    risk_levels=frozenset({RiskLevel.CONSUMPTIVE}),
    max_steps=64,
    action_caps={
        "open_function_panel": 1, "open_daily_tasks_initial": 1, "close_daily_tasks": 1,
        "open_painting_scroll": 1, "select_yanwu_world": 1,
        "open_yanwu_currency_purchase": 1, "set_yanwu_quantity_max": 1,
        "buy_yanwu_currency_max": 1, "dismiss_yanwu_reward_popup": 1,
        "select_yunzhou": 1, "open_yunzhou_currency_purchase": 1,
        "set_yunzhou_quantity_max": 1, "buy_yunzhou_currency_max": 1,
        "dismiss_yunzhou_reward_popup": 1, "open_function_panel_verify": 1,
        "open_daily_tasks_verify": 1,
    },
    approved_resources=frozenset({"凝晶"}),
)
~~~

The definition uses `initial_state = "home"` and recognizes each transition's current page, target and postcondition plus the daily progress row, both store stock counters, exact regional-currency item, 凝晶 cost, max-quantity readout, expected result popup and unconditional safety markers. It records initial progress but never treats `10000/10000` alone as completion: the business objective is to inspect both stores and buy their full current stock. For each store, uniquely parse stock, skip the max/buy transitions with an input-free state advance only when stock is exactly zero/sold-out, otherwise open the purchase, click the max control, re-read a quantity equal to that store's full stock, require same-frame stored `凝晶`, and perform exactly one store-specific buy. The expected non-paid result must have a recognized close target; never use a blind blank click. After both stores, reopen 日常任务 and require the `消耗10000凝晶` row to be complete or claimable without clicking `领取`. Return `completed` when either buy counter changed and the final row is verified; return `already_complete` only when both stores were already exhausted and the final row was already complete; return `failed/CONDENSATE_PROGRESS_UNVERIFIED` when both stores are exhausted but the row is below 10000, and never search for a third source.

**Pipeline contract:**

~~~json
{
  "MJA_Daily_SPEND_CONDENSATE_DAILY": {
    "recognition": "DirectHit",
    "action": "Custom",
    "custom_action": "DailyWorkflowAction",
    "custom_action_param": {"task_id": "SPEND_CONDENSATE_DAILY"}
  },
  "MJA_SPEND_CONDENSATE_DAILY_YANWU": {
    "recognition": "TemplateMatch",
    "template": "daily/SPEND_CONDENSATE_DAILY/yanwu_currency_shop.png",
    "action": "DoNothing",
    "next": ["MJA_SPEND_CONDENSATE_DAILY_YUNZHOU"]
  },
  "MJA_SPEND_CONDENSATE_DAILY_YUNZHOU": {
    "recognition": "TemplateMatch",
    "template": "daily/SPEND_CONDENSATE_DAILY/yunzhou_currency_shop.png",
    "action": "DoNothing"
  }
}
~~~

**TDD, live verification, and handoff:**

- [ ] **Red, 3 minutes:** Test normal two-store full-stock purchase to completed, progress 10000 with nonzero store stock still purchases both stores, already_complete only for progress 10000 plus two exhausted stores, failed below-target two-store exhaustion, blocked_safety paid/verification/UNKNOWN_DIALOG danger_hits, exact store order, separate max/readout/buy postconditions, two distinct purchase caps and approved 凝晶 cost matching.
- [ ] **Red, 2 minutes:** Run install/.venv/bin/python -m pytest tests/workflows/test_spend_condensate_daily.py -q. Expected collection failure: ModuleNotFoundError: No module named 'agent.workflows.definitions.spend_condensate_daily'.
- [ ] **Green implementation, 5 minutes:** Implement the exact initial-daily → 偃武 max/readout/buy → 云州 max/readout/buy → final-daily state machine. One current-frame purchase per store is allowed only when page, regional item, full-stock quantity, 凝晶 cost and no-danger evidence are unique; re-capture after every max selection and purchase. Never short-circuit on initial progress 10000 and never claim the final row.
- [ ] **Green pipeline and interface, 3 minutes:** Add both store recognizers and append this exact single entry; do not register a second entry for the two stores:
~~~json
{
  "name": "spend_condensate_daily",
  "label": "消耗凝晶",
  "entry": "MJA_Daily_SPEND_CONDENSATE_DAILY",
  "default_check": false,
  "resource": ["mja"],
  "controller": ["macos"]
}
~~~
- [ ] **Green fixtures, 4 minutes:** Capture the four required PNGs. The actionable case visibly identifies one active regional-currency shop, its full stock and 凝晶 cost; the completed case visibly verifies daily progress 10000; the danger case contains paid, verification or UNKNOWN_DIALOG evidence. Manifest contains exactly schema_version, task_id, reference_size and cases; each case contains image, expected_page, expected_targets and expected_status, with null, null, already_complete and blocked_safety respectively.
- [ ] **Green fixture tests, 3 minutes:** Run the foundation fixture validator and task test. Expected no input on completed/danger and no purchase without same-frame store plus 凝晶 evidence.
- [ ] **Live verification, 5 minutes:** Run install/.venv/bin/python -m tools.run_cli --task spend_condensate_daily. Save diagnostics/YYYY-MM-DD/SPEND_CONDENSATE_DAILY/run-id/ and append its relative paths to docs/verification/2026-07-28-mja-daily-workflows-batch-2.md. Record both store visits, full stock quantities, approved resource 凝晶, daily progress after each purchase, and final status; leave verification/tasks/SPEND_CONDENSATE_DAILY.json for the later aggregate admission plan.
- [ ] **Live postcondition/no-op, 4 minutes:** Verify both 偃武世界 and 云州 regional stock inspections occurred, each nonzero stock used its full visible quantity and stored 凝晶 cost, then verify the 日常任务 消耗10000凝晶 row is complete or claimable without clicking its reward. Re-run only after both store stocks are exhausted and the row is complete; expect already_complete with zero max/buy inputs. Initial progress 10000 with remaining store stock must still buy both stocks. If 10000 cannot be reached from the two current stocks, return failed without searching or clicking a third source.
- [ ] **Commit, 2 minutes:**
~~~bash
git add -- agent/workflows/catalog.py agent/workflows/registry.py agent/workflows/definitions/__init__.py \
  agent/workflows/definitions/spend_condensate_daily.py \
  assets/resource/pipeline/daily/spend_condensate_daily.json \
  assets/resource/image/daily/SPEND_CONDENSATE_DAILY/entry.png \
  assets/resource/image/daily/SPEND_CONDENSATE_DAILY/function_panel_entry.png \
  assets/resource/image/daily/SPEND_CONDENSATE_DAILY/daily_tasks_entry.png \
  assets/resource/image/daily/SPEND_CONDENSATE_DAILY/daily_tasks_close.png \
  assets/resource/image/daily/SPEND_CONDENSATE_DAILY/painting_scroll_entry.png \
  assets/resource/image/daily/SPEND_CONDENSATE_DAILY/yanwu_world_tab.png \
  assets/resource/image/daily/SPEND_CONDENSATE_DAILY/yunzhou_tab.png \
  assets/resource/image/daily/SPEND_CONDENSATE_DAILY/yanwu_currency_shop.png \
  assets/resource/image/daily/SPEND_CONDENSATE_DAILY/yunzhou_currency_shop.png \
  assets/resource/image/daily/SPEND_CONDENSATE_DAILY/yanwu_currency_purchase_target.png \
  assets/resource/image/daily/SPEND_CONDENSATE_DAILY/yunzhou_currency_purchase_target.png \
  assets/resource/image/daily/SPEND_CONDENSATE_DAILY/yanwu_stock_counter.png \
  assets/resource/image/daily/SPEND_CONDENSATE_DAILY/yunzhou_stock_counter.png \
  assets/resource/image/daily/SPEND_CONDENSATE_DAILY/quantity_max.png \
  assets/resource/image/daily/SPEND_CONDENSATE_DAILY/condensate_cost.png \
  assets/resource/image/daily/SPEND_CONDENSATE_DAILY/buy_confirm.png \
  assets/resource/image/daily/SPEND_CONDENSATE_DAILY/expected_reward_popup_close.png \
  assets/resource/image/daily/SPEND_CONDENSATE_DAILY/daily_progress_10000.png \
  tests/fixtures/SPEND_CONDENSATE_DAILY/manifest.json \
  tests/fixtures/SPEND_CONDENSATE_DAILY/entry.png \
  tests/fixtures/SPEND_CONDENSATE_DAILY/actionable.png \
  tests/fixtures/SPEND_CONDENSATE_DAILY/completed.png \
  tests/fixtures/SPEND_CONDENSATE_DAILY/danger.png \
  tests/workflows/test_spend_condensate_daily.py \
  assets/interface.json
git commit -m "feat: add condensate purchase daily workflow"
~~~

### Task 4: Implement MARTIAL_STUDY_BREAKTHROUGH_DAILY with three attempts per slot and no timer acceleration

**Business truth:** Read the MARTIAL_STUDY_BREAKTHROUGH_DAILY branch in workflows.py. Claim all visible 成功 cards first; then fill every visible + slot in deterministic order, skipping a character already shown as 正在突破中 in another slot, using at most three 研习 attempts per slot before 突破. Never accelerate a timer. Check 馈赠奖励 red dot last, then verify 完成一次武学突破 on 日常任务 without claiming that daily-row reward.

**Files:**

- Create: `agent/workflows/definitions/martial_study_breakthrough_daily.py`
- Create: `assets/resource/pipeline/daily/martial_study_breakthrough_daily.json`
- Create: `assets/resource/image/daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/entry.png`
- Create: `assets/resource/image/daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/function_panel_entry.png`
- Create: `assets/resource/image/daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/martial_study_entry.png`
- Create: `assets/resource/image/daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/martial_page.png`
- Create: `assets/resource/image/daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/plus_slot.png`
- Create: `assets/resource/image/daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/character_candidate.png`
- Create: `assets/resource/image/daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/skill_candidate.png`
- Create: `assets/resource/image/daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/character_already_breaking.png`
- Create: `assets/resource/image/daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/study_slot_action.png`
- Create: `assets/resource/image/daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/study_material_present.png`
- Create: `assets/resource/image/daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/study_timer.png`
- Create: `assets/resource/image/daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/success_card.png`
- Create: `assets/resource/image/daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/success_detail_study.png`
- Create: `assets/resource/image/daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/expected_result_close.png`
- Create: `assets/resource/image/daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/breakthrough_target.png`
- Create: `assets/resource/image/daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/breakthrough_confirm.png`
- Create: `assets/resource/image/daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/breakthrough_marker.png`
- Create: `assets/resource/image/daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/gift_reward_red_dot.png`
- Create: `assets/resource/image/daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/gift_reward_claim.png`
- Create: `assets/resource/image/daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/gift_reward_close.png`
- Create: `assets/resource/image/daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/martial_close.png`
- Create: `assets/resource/image/daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/daily_tasks_entry.png`
- Create: `assets/resource/image/daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/daily_list_viewport.png`
- Create: `assets/resource/image/daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/daily_breakthrough_complete.png`
- Create: `tests/fixtures/MARTIAL_STUDY_BREAKTHROUGH_DAILY/manifest.json`
- Create: `tests/fixtures/MARTIAL_STUDY_BREAKTHROUGH_DAILY/entry.png`
- Create: `tests/fixtures/MARTIAL_STUDY_BREAKTHROUGH_DAILY/actionable.png`
- Create: `tests/fixtures/MARTIAL_STUDY_BREAKTHROUGH_DAILY/completed.png`
- Create: `tests/fixtures/MARTIAL_STUDY_BREAKTHROUGH_DAILY/danger.png`
- Update: `agent/workflows/catalog.py` (TASK_POLICIES entry)
- Update: `agent/workflows/registry.py` (definition registration)
- Update: `agent/workflows/definitions/__init__.py` (definition export)
- Create: `tests/workflows/test_martial_study_breakthrough_daily.py`
- Update: `assets/interface.json` (one singular task entry only)

**Interfaces:**

~~~python
TASK_ID = "MARTIAL_STUDY_BREAKTHROUGH_DAILY"
APPROVED_RESOURCE = "martial_study_material"
MAX_SLOTS = 3
MAX_ATTEMPTS_PER_SLOT = 3
MAX_CANDIDATES_PER_SLOT = 6
MAX_SUCCESS_CARDS = 3
MAX_DAILY_SCROLLS = 1

from agent.safety import ActionIntent
from agent.workflows.engine import Transition

ROUTE_TRANSITIONS = (
    Transition("home", ActionIntent("open_function_panel", "home", "function_panel_entry"), "click", {}, "function_panel", "function_panel_page"),
    Transition("function_panel", ActionIntent("open_martial_study", "function_panel_page", "martial_study_entry"), "click", {}, "martial", "martial_page"),
)

def slot_transitions(slot: int) -> tuple[Transition, ...]:
    return (
        Transition("martial", ActionIntent(f"open_plus_slot_{slot}", "martial_page", f"plus_slot_{slot}"), "click", {}, f"character_{slot}", "character_select_page"),
        Transition(f"character_{slot}", ActionIntent(f"select_character_{slot}", "character_select_page", f"character_candidate_{slot}"), "click", {}, f"skill_{slot}", "skill_select_page"),
        Transition(f"skill_{slot}", ActionIntent(f"select_skill_{slot}", "skill_select_page", f"skill_candidate_{slot}"), "click", {}, f"prepare_{slot}", "martial_detail_page"),
        Transition(f"prepare_{slot}", ActionIntent(f"study_slot_{slot}", "martial_detail_page", f"study_slot_{slot}_action", APPROVED_RESOURCE), "click", {}, f"prepare_{slot}", f"study_slot_{slot}_changed"),
        Transition(f"prepare_{slot}", ActionIntent(f"breakthrough_slot_{slot}", "martial_detail_page", f"breakthrough_slot_{slot}_target", APPROVED_RESOURCE), "click", {}, f"confirm_{slot}", "breakthrough_confirm"),
        Transition(f"confirm_{slot}", ActionIntent(f"confirm_breakthrough_slot_{slot}", "breakthrough_confirm_page", "breakthrough_confirm"), "click", {}, "martial", f"breakthrough_slot_{slot}_complete"),
    )

SLOT_TRANSITIONS = tuple(transition for slot in range(MAX_SLOTS) for transition in slot_transitions(slot))

SUCCESS_AND_FINISH_TRANSITIONS = (
    Transition("martial", ActionIntent("claim_success_card", "martial_page", "success_card"), "click", {}, "success_result", "success_result_or_detail"),
    Transition("success_result", ActionIntent("study_success_detail", "success_detail_page", "success_detail_study", APPROVED_RESOURCE), "click", {}, "success_result", "expected_success_result"),
    Transition("success_result", ActionIntent("dismiss_success_result", "expected_success_result", "expected_result_close"), "click", {}, "martial", "martial_page"),
    Transition("martial_done", ActionIntent("open_gift_rewards", "martial_page", "gift_reward_red_dot"), "click", {}, "gift", "gift_reward_page"),
    Transition("gift", ActionIntent("claim_gift_reward", "gift_reward_page", "gift_reward_claim"), "click", {}, "gift_result", "expected_gift_result"),
    Transition("gift_result", ActionIntent("dismiss_gift_result", "expected_gift_result", "expected_result_close"), "click", {}, "gift", "gift_reward_page"),
    Transition("gift", ActionIntent("close_gift_rewards", "gift_reward_page", "gift_reward_close"), "click", {}, "martial_done", "martial_page"),
    Transition("martial_done", ActionIntent("close_martial", "martial_page", "martial_close"), "click", {}, "home_verify", "home"),
    Transition("home_verify", ActionIntent("open_function_panel_verify", "home", "function_panel_entry"), "click", {}, "function_panel_verify", "function_panel_page"),
    Transition("function_panel_verify", ActionIntent("open_daily_tasks", "function_panel_page", "daily_tasks_entry"), "click", {}, "daily_verify", "daily_tasks_page"),
    Transition("daily_verify", ActionIntent("scroll_daily_breakthrough_row", "daily_tasks_page", "daily_list_viewport"), "swipe", {"recognition_marker": "daily_list_viewport", "start_fraction": (0.5, 0.8), "end_fraction": (0.5, 0.3), "duration_ms": 800}, "daily_verify", "daily_breakthrough_row_or_end"),
)
~~~

The only policy source is appended to agent/workflows/catalog.py:

~~~python
TASK_POLICIES[TASK_ID] = TaskPolicy(
    task_id=TASK_ID,
    label="武学研习与突破",
    entry="MJA_Daily_MARTIAL_STUDY_BREAKTHROUGH_DAILY",
    risk_levels=frozenset({RiskLevel.CONSUMPTIVE, RiskLevel.STATEFUL, RiskLevel.PROTECTED_CLAIM}),
    max_steps=128,
    action_caps={
        "open_function_panel": 1, "open_martial_study": 1,
        "claim_success_card": 3, "study_success_detail": 3, "dismiss_success_result": 3,
        "open_plus_slot_0": 1, "open_plus_slot_1": 1, "open_plus_slot_2": 1,
        "select_character_0": 6, "select_character_1": 6, "select_character_2": 6,
        "select_skill_0": 1, "select_skill_1": 1, "select_skill_2": 1,
        "study_slot_0": 3, "study_slot_1": 3, "study_slot_2": 3,
        "breakthrough_slot_0": 1, "breakthrough_slot_1": 1, "breakthrough_slot_2": 1,
        "confirm_breakthrough_slot_0": 1, "confirm_breakthrough_slot_1": 1, "confirm_breakthrough_slot_2": 1,
        "open_gift_rewards": 1, "claim_gift_reward": 3, "dismiss_gift_result": 3, "close_gift_rewards": 1,
        "close_martial": 1, "open_function_panel_verify": 1,
        "open_daily_tasks": 1, "scroll_daily_breakthrough_row": 1,
    },
    approved_resources=frozenset({"martial_study_material"}),
)
~~~

The definition uses `initial_state = "home"`. Decision priority is unconditional danger/`加速`, visible 成功 cards, visible + slots in index order, 馈赠奖励, and final daily verification. For each 成功 card, click the unique card; if it opens detail, click 研习 only with same-frame `martial_study_material` present, then dismiss only the expected non-paid result and recapture until no 成功 card remains. Cap this loop at three visible cards.

For each of at most three visible + slots, select the slot, then choose candidates in current-frame order. If the chosen character name is also uniquely marked `正在突破中` in another visible slot, reject that candidate without starting study and try the next candidate, capped at six candidates for that slot. Select one skill. If 突破 is immediately enabled, do not study; otherwise click 研习 at most three times, requiring `martial_study_material` and a changed slot/detail marker after every click. Then click 突破 and its exact expected confirmation and require the slot to become occupied by a countdown/breakthrough marker. Missing-material purchase UI, paid UI, verification, unknown dialog, and every `加速` target are `blocked_safety`; a three-study unchanged slot or six rejected candidates is stable `failed`.

Only after no visible + slot remains, check 馈赠奖励. Open and claim it only when the red dot is present, close expected non-paid results, then return to 日常任务. Verify `完成一次武学突破` is complete or claimable without clicking its row reward. At most one box-relative swipe of the recognized daily-list viewport is allowed. If that row remains unavailable but the same run proved no 成功 card, no + slot and all three slots occupied by countdown/breakthrough timers, that full-slot evidence is the independent completion postcondition; otherwise return `failed/MARTIAL_DAILY_UNVERIFIED`. A feature-unavailable page is `not_eligible`. A no-op run with full-slot evidence and no red dot returns `already_complete` with zero success/study/breakthrough/gift-claim inputs.

**Pipeline contract:**

~~~json
{
  "MJA_Daily_MARTIAL_STUDY_BREAKTHROUGH_DAILY": {
    "recognition": "DirectHit",
    "action": "Custom",
    "custom_action": "DailyWorkflowAction",
    "custom_action_param": {"task_id": "MARTIAL_STUDY_BREAKTHROUGH_DAILY"}
  },
  "MJA_MARTIAL_STUDY_BREAKTHROUGH_DAILY_PAGE": {
    "recognition": "TemplateMatch",
    "template": "daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/martial_page.png",
    "action": "DoNothing"
  },
  "MJA_MARTIAL_STUDY_BREAKTHROUGH_DAILY_TIMER": {
    "recognition": "OCR",
    "text": "研习中",
    "action": "DoNothing"
  },
  "MJA_MARTIAL_STUDY_BREAKTHROUGH_DAILY_SUCCESS": {
    "recognition": "TemplateMatch",
    "template": "daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/success_card.png",
    "action": "DoNothing"
  },
  "MJA_MARTIAL_STUDY_BREAKTHROUGH_DAILY_BREAKTHROUGH": {
    "recognition": "TemplateMatch",
    "template": "daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/breakthrough_target.png",
    "action": "DoNothing"
  }
}
~~~

**TDD, live verification, and handoff:**

- [ ] **Red, 3 minutes:** Test all visible success cards first; all three + slots; candidate skip when the same character is 正在突破中 elsewhere; immediate-breakthrough and one/two/three-study branches; failed fourth study/candidate exhaustion/unchanged slot; gift red dot last; final daily row without reward claim; already_complete all-timer/no-plus/no-red-dot no-op; not_eligible feature-unavailable; blocked_safety paid/verification/UNKNOWN_DIALOG/acceleration danger_hits; and absence of every accelerate action ID.
- [ ] **Red, 2 minutes:** Run install/.venv/bin/python -m pytest tests/workflows/test_martial_study_breakthrough_daily.py -q. Expected collection failure: ModuleNotFoundError: No module named 'agent.workflows.definitions.martial_study_breakthrough_daily'.
- [ ] **Green implementation, 5 minutes:** Implement the route, success-card loop, `SLOT_TRANSITIONS`, six-candidate skip bound, three-study bound, breakthrough confirmation, gift-red-dot-last branch and final daily-row verifier. Reject any target or decision named accelerate_timer; do not treat a timer as an invitation to wait-and-click. Require a new frame and named postcondition after every protected input.
- [ ] **Green pipeline and interface, 3 minutes:** Add recognizer-only page/timer nodes and append this exact entry; no action node may use standard Click, StartApp or keyboard input:
~~~json
{
  "name": "martial_study_breakthrough_daily",
  "label": "武学研习与突破",
  "entry": "MJA_Daily_MARTIAL_STUDY_BREAKTHROUGH_DAILY",
  "default_check": false,
  "resource": ["mja"],
  "controller": ["macos"]
}
~~~
- [ ] **Green fixtures, 4 minutes:** Capture entry, actionable with a unique eligible plus slot or success card, completed with all visible slots on countdown/breakthrough timers and no plus slot, and danger with timer acceleration, paid, verification or UNKNOWN_DIALOG evidence. Manifest contains exactly schema_version, task_id, reference_size and cases; each case contains image, expected_page, expected_targets and expected_status. Add real supplemental crops for character-already-breaking, gift red dot, daily breakthrough row and expected confirmations; store no fabricated PNG.
- [ ] **Green fixture tests, 3 minutes:** Run foundation fixture validation and the task test. Expected timer and danger cases issue no input; repeated actionable decisions stop at three attempts for each slot.
- [ ] **Live verification, 5 minutes:** Run install/.venv/bin/python -m tools.run_cli --task martial_study_breakthrough_daily. Save diagnostics/YYYY-MM-DD/MARTIAL_STUDY_BREAKTHROUGH_DAILY/run-id/ and append its relative paths to docs/verification/2026-07-28-mja-daily-workflows-batch-2.md. Record success-card IDs, slot IDs, study counts, timer evidence, resource evidence and each postcondition; leave verification/tasks/MARTIAL_STUDY_BREAKTHROUGH_DAILY.json for the later aggregate admission plan.
- [ ] **Live postcondition/no-op, 4 minutes:** Confirm every visible success card was handled first, all visible + slots were filled, any already-breaking character was skipped, every touched slot changed and reached breakthrough within three studies, 馈赠奖励 was checked last, the daily row or bounded full-slot fallback was proven, and no timer acceleration or daily-row reward click occurred. Re-run while all visible slots are on countdown/breakthrough timers with no plus slot and no gift red dot; expect already_complete with zero success/study/breakthrough/gift-claim inputs. A paid signal, ambiguous slot or unchanged postcondition stops safely.
- [ ] **Commit, 2 minutes:**
~~~bash
git add -- agent/workflows/catalog.py agent/workflows/registry.py agent/workflows/definitions/__init__.py \
  agent/workflows/definitions/martial_study_breakthrough_daily.py \
  assets/resource/pipeline/daily/martial_study_breakthrough_daily.json \
  assets/resource/image/daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/entry.png \
  assets/resource/image/daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/function_panel_entry.png \
  assets/resource/image/daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/martial_study_entry.png \
  assets/resource/image/daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/martial_page.png \
  assets/resource/image/daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/plus_slot.png \
  assets/resource/image/daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/character_candidate.png \
  assets/resource/image/daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/skill_candidate.png \
  assets/resource/image/daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/character_already_breaking.png \
  assets/resource/image/daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/study_slot_action.png \
  assets/resource/image/daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/study_material_present.png \
  assets/resource/image/daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/study_timer.png \
  assets/resource/image/daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/success_card.png \
  assets/resource/image/daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/success_detail_study.png \
  assets/resource/image/daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/expected_result_close.png \
  assets/resource/image/daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/breakthrough_target.png \
  assets/resource/image/daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/breakthrough_confirm.png \
  assets/resource/image/daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/breakthrough_marker.png \
  assets/resource/image/daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/gift_reward_red_dot.png \
  assets/resource/image/daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/gift_reward_claim.png \
  assets/resource/image/daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/gift_reward_close.png \
  assets/resource/image/daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/martial_close.png \
  assets/resource/image/daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/daily_tasks_entry.png \
  assets/resource/image/daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/daily_list_viewport.png \
  assets/resource/image/daily/MARTIAL_STUDY_BREAKTHROUGH_DAILY/daily_breakthrough_complete.png \
  tests/fixtures/MARTIAL_STUDY_BREAKTHROUGH_DAILY/manifest.json \
  tests/fixtures/MARTIAL_STUDY_BREAKTHROUGH_DAILY/entry.png \
  tests/fixtures/MARTIAL_STUDY_BREAKTHROUGH_DAILY/actionable.png \
  tests/fixtures/MARTIAL_STUDY_BREAKTHROUGH_DAILY/completed.png \
  tests/fixtures/MARTIAL_STUDY_BREAKTHROUGH_DAILY/danger.png \
  tests/workflows/test_martial_study_breakthrough_daily.py \
  assets/interface.json
git commit -m "feat: add martial study breakthrough daily workflow"
~~~

### Task 5: Implement EAT_STAMINA_FOOD_DAILY with named food and overfull stop

**Business truth:** Read the EAT_STAMINA_FOOD_DAILY branch in workflows.py. Select only an item whose detail says 龙井虾仁 and +15 stamina, eat at most six, accept only the expected same-category buff-replacement prompt, and on the attempted fourth item stop only for the exact toast `你吃得太撑了，请手抚胸部转圆按摩，或者散一散`.

**Files:**

- Create: `agent/workflows/definitions/eat_stamina_food_daily.py`
- Create: `assets/resource/pipeline/daily/eat_stamina_food_daily.json`
- Create: `assets/resource/image/daily/EAT_STAMINA_FOOD_DAILY/entry.png`
- Create: `assets/resource/image/daily/EAT_STAMINA_FOOD_DAILY/function_panel_entry.png`
- Create: `assets/resource/image/daily/EAT_STAMINA_FOOD_DAILY/bag_entry.png`
- Create: `assets/resource/image/daily/EAT_STAMINA_FOOD_DAILY/food_category.png`
- Create: `assets/resource/image/daily/EAT_STAMINA_FOOD_DAILY/food_page.png`
- Create: `assets/resource/image/daily/EAT_STAMINA_FOOD_DAILY/blue_food_candidate.png`
- Create: `assets/resource/image/daily/EAT_STAMINA_FOOD_DAILY/longjing_shrimp_name.png`
- Create: `assets/resource/image/daily/EAT_STAMINA_FOOD_DAILY/stamina_plus_15.png`
- Create: `assets/resource/image/daily/EAT_STAMINA_FOOD_DAILY/longjing_shrimp_eat_target.png`
- Create: `assets/resource/image/daily/EAT_STAMINA_FOOD_DAILY/food_count.png`
- Create: `assets/resource/image/daily/EAT_STAMINA_FOOD_DAILY/fullness_cap.png`
- Create: `assets/resource/image/daily/EAT_STAMINA_FOOD_DAILY/too_full_toast.png`
- Create: `assets/resource/image/daily/EAT_STAMINA_FOOD_DAILY/food_buff_replace_confirm.png`
- Create: `assets/resource/image/daily/EAT_STAMINA_FOOD_DAILY/bag_close.png`
- Create: `tests/fixtures/EAT_STAMINA_FOOD_DAILY/manifest.json`
- Create: `tests/fixtures/EAT_STAMINA_FOOD_DAILY/entry.png`
- Create: `tests/fixtures/EAT_STAMINA_FOOD_DAILY/actionable.png`
- Create: `tests/fixtures/EAT_STAMINA_FOOD_DAILY/completed.png`
- Create: `tests/fixtures/EAT_STAMINA_FOOD_DAILY/danger.png`
- Update: `agent/workflows/catalog.py` (TASK_POLICIES entry)
- Update: `agent/workflows/registry.py` (definition registration)
- Update: `agent/workflows/definitions/__init__.py` (definition export)
- Create: `tests/workflows/test_eat_stamina_food_daily.py`
- Update: `assets/interface.json` (one singular task entry only)

**Interfaces:**

~~~python
TASK_ID = "EAT_STAMINA_FOOD_DAILY"
APPROVED_RESOURCE = "龙井虾仁"
MAX_FOOD = 6
MAX_VISIBLE_CANDIDATES = 8
MIN_EATEN_BEFORE_TOO_FULL = 3
TOO_FULL_TEXT = "你吃得太撑了，请手抚胸部转圆按摩，或者散一散"

from agent.safety import ActionIntent
from agent.workflows.engine import Transition

TRANSITIONS = (
    Transition("home", ActionIntent("open_function_panel", "home", "function_panel_entry"), "click", {}, "function_panel", "function_panel_page"),
    Transition("function_panel", ActionIntent("open_bag", "function_panel_page", "bag_entry"), "click", {}, "bag", "bag_page"),
    Transition("bag", ActionIntent("open_food_category", "bag_page", "food_category"), "click", {}, "food", "food_page"),
    Transition("food", ActionIntent("inspect_food_candidate", "food_page", "blue_food_candidate"), "click", {}, "food", "food_detail_changed"),
    Transition("food", ActionIntent("eat_longjing_shrimp", "food_page", "longjing_shrimp_eat_target", APPROVED_RESOURCE), "click", {}, "food_result", "food_result_or_prompt"),
    Transition("food_result", ActionIntent("confirm_food_buff_replace", "food_buff_replace_page", "food_buff_replace_confirm"), "click", {}, "food", "food_consumption_changed"),
    Transition("food_done", ActionIntent("close_bag", "food_page", "bag_close"), "click", {}, "home_done", "home"),
)
~~~

The only policy source is appended to agent/workflows/catalog.py:

~~~python
TASK_POLICIES[TASK_ID] = TaskPolicy(
    task_id=TASK_ID,
    label="食用体力食物",
    entry="MJA_Daily_EAT_STAMINA_FOOD_DAILY",
    risk_levels=frozenset({RiskLevel.CONSUMPTIVE}),
    max_steps=48,
    action_caps={
        "open_function_panel": 1,
        "open_bag": 1,
        "open_food_category": 1,
        "inspect_food_candidate": 8,
        "eat_longjing_shrimp": 6,
        "confirm_food_buff_replace": 6,
        "close_bag": 1,
    },
    approved_resources=frozenset({"龙井虾仁"}),
)
~~~

The definition uses `initial_state = "home"` and always opens 背包 through the tai-chi function panel, never through the ambiguous left-side main icon. In the food category it inspects current-frame blue-background candidates, prioritizing visible third/fourth rows, at most eight candidates. Inspection is non-consumptive. Only a unique candidate whose same-frame detail includes both exact `龙井虾仁` and `+15` may expose `eat_longjing_shrimp`; another +15 food is rejected. If no exact candidate is found after the bounded scan, return `not_eligible/FOOD_NOT_AVAILABLE`, not already_complete.

Before each eat, require current food page, exact item name, +15 effect, current food count and unique eat target. After the click, recapture. A normal result must decrease item count by one or increase stamina by exactly 15. The only allowed confirmation is a prompt independently identified as replacement of the same food category; any paid, purchase, verification, unknown or different-category prompt is `blocked_safety`. The exact `TOO_FULL_TEXT` is terminal `completed` only when at least three successful eats were already recorded, i.e. while attempting item four or later; the same toast earlier is `failed/FOOD_CAP_TOO_EARLY`. A visible stable fullness-cap marker before any eat is `already_complete` with zero eat input. Six verified eats is `completed`. Zero inventory without fullness proof is `not_eligible`, never a false completion. Close the bag through its recognized close target after a terminal postcondition.

**Pipeline contract:**

~~~json
{
  "MJA_Daily_EAT_STAMINA_FOOD_DAILY": {
    "recognition": "DirectHit",
    "action": "Custom",
    "custom_action": "DailyWorkflowAction",
    "custom_action_param": {"task_id": "EAT_STAMINA_FOOD_DAILY"}
  },
  "MJA_EAT_STAMINA_FOOD_DAILY_PAGE": {
    "recognition": "TemplateMatch",
    "template": "daily/EAT_STAMINA_FOOD_DAILY/food_page.png",
    "action": "DoNothing",
    "next": ["MJA_EAT_STAMINA_FOOD_DAILY_TARGET"]
  },
  "MJA_EAT_STAMINA_FOOD_DAILY_TARGET": {
    "recognition": "TemplateMatch",
    "template": "daily/EAT_STAMINA_FOOD_DAILY/longjing_shrimp_eat_target.png",
    "action": "DoNothing"
  }
}
~~~

**TDD, live verification, and handoff:**

- [ ] **Red, 3 minutes:** Test exact 龙井虾仁 plus +15 selection, rejection of other +15 foods, bounded candidate scan, six verified eats, exact too-full toast accepted only from the attempted fourth item onward, failed early/mismatched toast and unchanged food/stamina, already_complete stable fullness-cap no-op, not_eligible missing/zero exact food, same-category replacement only, blocked_safety paid/verification/UNKNOWN_DIALOG, and same-frame page/name/effect/target authorization.
- [ ] **Red, 2 minutes:** Run install/.venv/bin/python -m pytest tests/workflows/test_eat_stamina_food_daily.py -q. Expected collection failure: ModuleNotFoundError: No module named 'agent.workflows.definitions.eat_stamina_food_daily'.
- [ ] **Green implementation, 5 minutes:** Implement the exact panel/bag/food route, bounded candidate inspection and one-item transitions. Return already_complete only for a stable pre-existing fullness-cap marker; return completed after six verified consumptions or the exact toast on attempt four or later; return not_eligible when exact 龙井虾仁 +15 is unavailable; return blocked_safety for dangerous prompts; return failed for early toast or unchanged stamina/food postconditions.
- [ ] **Green pipeline and interface, 3 minutes:** Add recognizer-only food nodes and append this exact entry; no generic food purchase or standard click node is permitted:
~~~json
{
  "name": "eat_stamina_food_daily",
  "label": "食用体力食物",
  "entry": "MJA_Daily_EAT_STAMINA_FOOD_DAILY",
  "default_check": false,
  "resource": ["mja"],
  "controller": ["macos"]
}
~~~
- [ ] **Green fixtures, 4 minutes:** Capture entry, actionable with exact 龙井虾仁, +15 and a unique eat target, completed with a stable fullness-cap marker, and danger with paid, verification or UNKNOWN_DIALOG evidence. Manifest contains exactly schema_version, task_id, reference_size and cases; each case contains image, expected_page, expected_targets and expected_status, with exact name/effect/resource targets. Add a real supplemental crop of the exact too-full toast; zero inventory is tested as not_eligible, not encoded as completed.
- [ ] **Green fixture tests, 3 minutes:** Run the foundation fixture validator and task test. Expected no input on completed/danger and no more than six item decisions on a repeated actionable sequence.
- [ ] **Live verification, 5 minutes:** Run install/.venv/bin/python -m tools.run_cli --task eat_stamina_food_daily. Save diagnostics/YYYY-MM-DD/EAT_STAMINA_FOOD_DAILY/run-id/ and append its relative paths to docs/verification/2026-07-28-mja-daily-workflows-batch-2.md. Record each food count, stamina postcondition, overfull signal and current recognition box; leave verification/tasks/EAT_STAMINA_FOOD_DAILY.json for the later aggregate admission plan.
- [ ] **Live postcondition/no-op, 4 minutes:** Verify every consumed item had exact 龙井虾仁 and +15 evidence, count never exceeded six, same-category replacement was the only confirmed prompt, and the exact too-full toast stopped the run only from the attempted fourth item onward. Re-run while the stable fullness-cap marker is visible; expect already_complete with zero inspect/eat/confirm inputs. Zero exact food without fullness proof is not_eligible. Any paid, unknown or ambiguous food target stops.
- [ ] **Commit, 2 minutes:**
~~~bash
git add -- agent/workflows/catalog.py agent/workflows/registry.py agent/workflows/definitions/__init__.py \
  agent/workflows/definitions/eat_stamina_food_daily.py \
  assets/resource/pipeline/daily/eat_stamina_food_daily.json \
  assets/resource/image/daily/EAT_STAMINA_FOOD_DAILY/entry.png \
  assets/resource/image/daily/EAT_STAMINA_FOOD_DAILY/function_panel_entry.png \
  assets/resource/image/daily/EAT_STAMINA_FOOD_DAILY/bag_entry.png \
  assets/resource/image/daily/EAT_STAMINA_FOOD_DAILY/food_category.png \
  assets/resource/image/daily/EAT_STAMINA_FOOD_DAILY/food_page.png \
  assets/resource/image/daily/EAT_STAMINA_FOOD_DAILY/blue_food_candidate.png \
  assets/resource/image/daily/EAT_STAMINA_FOOD_DAILY/longjing_shrimp_name.png \
  assets/resource/image/daily/EAT_STAMINA_FOOD_DAILY/stamina_plus_15.png \
  assets/resource/image/daily/EAT_STAMINA_FOOD_DAILY/longjing_shrimp_eat_target.png \
  assets/resource/image/daily/EAT_STAMINA_FOOD_DAILY/food_count.png \
  assets/resource/image/daily/EAT_STAMINA_FOOD_DAILY/fullness_cap.png \
  assets/resource/image/daily/EAT_STAMINA_FOOD_DAILY/too_full_toast.png \
  assets/resource/image/daily/EAT_STAMINA_FOOD_DAILY/food_buff_replace_confirm.png \
  assets/resource/image/daily/EAT_STAMINA_FOOD_DAILY/bag_close.png \
  tests/fixtures/EAT_STAMINA_FOOD_DAILY/manifest.json \
  tests/fixtures/EAT_STAMINA_FOOD_DAILY/entry.png \
  tests/fixtures/EAT_STAMINA_FOOD_DAILY/actionable.png \
  tests/fixtures/EAT_STAMINA_FOOD_DAILY/completed.png \
  tests/fixtures/EAT_STAMINA_FOOD_DAILY/danger.png \
  tests/workflows/test_eat_stamina_food_daily.py \
  assets/interface.json
git commit -m "feat: add stamina food daily workflow"
~~~

### Task 6: Implement DUNGEON_SWEEP_DAILY with exact 燕王秘陵(大师), ticket-bounded sweep and bag-full stop

**Business truth:** Read the DUNGEON_SWEEP_DAILY branch in workflows.py. Use a bounded long-press drag on the recognized dungeon-list viewport to find 燕王秘陵, open its sweep panel, select exact 大师 80级, assign all currently visible 副本票 with the + control, start one sweep, and verify `通关或扫荡一次副本` on 日常任务 without claiming it. Stop on full bag and never disassemble items.

**Files:**

- Create: `agent/workflows/definitions/dungeon_sweep_daily.py`
- Create: `assets/resource/pipeline/daily/dungeon_sweep_daily.json`
- Create: `assets/resource/image/daily/DUNGEON_SWEEP_DAILY/entry.png`
- Create: `assets/resource/image/daily/DUNGEON_SWEEP_DAILY/dungeon_entry.png`
- Create: `assets/resource/image/daily/DUNGEON_SWEEP_DAILY/dungeon_selector.png`
- Create: `assets/resource/image/daily/DUNGEON_SWEEP_DAILY/dungeon_list_viewport.png`
- Create: `assets/resource/image/daily/DUNGEON_SWEEP_DAILY/yanwangling_main.png`
- Create: `assets/resource/image/daily/DUNGEON_SWEEP_DAILY/yanwangling_title.png`
- Create: `assets/resource/image/daily/DUNGEON_SWEEP_DAILY/master_80_row.png`
- Create: `assets/resource/image/daily/DUNGEON_SWEEP_DAILY/sweep_target.png`
- Create: `assets/resource/image/daily/DUNGEON_SWEEP_DAILY/ticket_counter.png`
- Create: `assets/resource/image/daily/DUNGEON_SWEEP_DAILY/assigned_ticket_counter.png`
- Create: `assets/resource/image/daily/DUNGEON_SWEEP_DAILY/ticket_plus.png`
- Create: `assets/resource/image/daily/DUNGEON_SWEEP_DAILY/start_sweep.png`
- Create: `assets/resource/image/daily/DUNGEON_SWEEP_DAILY/confirm_sweep.png`
- Create: `assets/resource/image/daily/DUNGEON_SWEEP_DAILY/expected_sweep_result.png`
- Create: `assets/resource/image/daily/DUNGEON_SWEEP_DAILY/expected_sweep_result_close.png`
- Create: `assets/resource/image/daily/DUNGEON_SWEEP_DAILY/bag_full.png`
- Create: `assets/resource/image/daily/DUNGEON_SWEEP_DAILY/dungeon_close.png`
- Create: `assets/resource/image/daily/DUNGEON_SWEEP_DAILY/function_panel_entry.png`
- Create: `assets/resource/image/daily/DUNGEON_SWEEP_DAILY/daily_tasks_entry.png`
- Create: `assets/resource/image/daily/DUNGEON_SWEEP_DAILY/daily_list_viewport.png`
- Create: `assets/resource/image/daily/DUNGEON_SWEEP_DAILY/daily_dungeon_complete.png`
- Create: `tests/fixtures/DUNGEON_SWEEP_DAILY/manifest.json`
- Create: `tests/fixtures/DUNGEON_SWEEP_DAILY/entry.png`
- Create: `tests/fixtures/DUNGEON_SWEEP_DAILY/actionable.png`
- Create: `tests/fixtures/DUNGEON_SWEEP_DAILY/completed.png`
- Create: `tests/fixtures/DUNGEON_SWEEP_DAILY/danger.png`
- Update: `agent/workflows/catalog.py` (TASK_POLICIES entry)
- Update: `agent/workflows/registry.py` (definition registration)
- Update: `agent/workflows/definitions/__init__.py` (definition export)
- Create: `tests/workflows/test_dungeon_sweep_daily.py`
- Update: `assets/interface.json` (one singular task entry only)

**Interfaces:**

~~~python
TASK_ID = "DUNGEON_SWEEP_DAILY"
APPROVED_RESOURCE = "副本票"
MAX_TICKETS_PER_RUN = 100
MAX_DUNGEON_LIST_SWIPES = 4
MAX_DAILY_SCROLLS = 1

from agent.safety import ActionIntent
from agent.workflows.engine import Transition

TRANSITIONS = (
    Transition("home", ActionIntent("open_dungeon", "home", "dungeon_entry"), "click", {}, "dungeon", "dungeon_page"),
    Transition("dungeon", ActionIntent("scroll_dungeon_list", "dungeon_page", "dungeon_list_viewport"), "swipe", {"recognition_marker": "dungeon_list_viewport", "start_fraction": (0.5, 0.8), "end_fraction": (0.5, 0.25), "hold_ms": 2000, "duration_ms": 4000, "steps": 160}, "dungeon", "dungeon_list_changed"),
    Transition("dungeon", ActionIntent("select_yanwangling", "dungeon_page", "yanwangling_main"), "click", {}, "yanwangling", "yanwangling_title"),
    Transition("yanwangling", ActionIntent("open_sweep_panel", "yanwangling_title", "sweep_target"), "click", {}, "sweep_panel", "sweep_panel_page"),
    Transition("sweep_panel", ActionIntent("select_yanwangling_in_panel", "sweep_panel_page", "yanwangling_main"), "click", {}, "sweep_panel", "yanwangling_panel_selected"),
    Transition("sweep_panel", ActionIntent("select_master_80", "sweep_panel_page", "master_80_row"), "click", {}, "assign_tickets", "yanwangling_master_selected"),
    Transition("assign_tickets", ActionIntent("assign_sweep_ticket", "yanwangling_master_selected", "ticket_plus", APPROVED_RESOURCE), "click", {}, "assign_tickets", "assigned_ticket_counter_changed"),
    Transition("assign_tickets", ActionIntent("start_yanwangling_master_sweep", "yanwangling_master_selected", "start_sweep", APPROVED_RESOURCE), "click", {}, "confirm_sweep", "normal_sweep_confirm_page"),
    Transition("confirm_sweep", ActionIntent("confirm_yanwangling_master_sweep", "normal_sweep_confirm_page", "confirm_sweep", APPROVED_RESOURCE), "click", {}, "sweep_result", "expected_sweep_result_or_bag_full"),
    Transition("sweep_result", ActionIntent("dismiss_sweep_result", "expected_sweep_result", "expected_sweep_result_close"), "click", {}, "dungeon_done", "dungeon_page"),
    Transition("dungeon_done", ActionIntent("close_dungeon", "dungeon_page", "dungeon_close"), "click", {}, "home_verify", "home"),
    Transition("home_verify", ActionIntent("open_function_panel_verify", "home", "function_panel_entry"), "click", {}, "function_panel_verify", "function_panel_page"),
    Transition("function_panel_verify", ActionIntent("open_daily_tasks_verify", "function_panel_page", "daily_tasks_entry"), "click", {}, "daily_verify", "daily_tasks_page"),
    Transition("daily_verify", ActionIntent("scroll_daily_dungeon_row", "daily_tasks_page", "daily_list_viewport"), "swipe", {"recognition_marker": "daily_list_viewport", "start_fraction": (0.5, 0.8), "end_fraction": (0.5, 0.3), "duration_ms": 800}, "daily_verify", "daily_dungeon_row_or_end"),
)
~~~

The only policy source is appended to agent/workflows/catalog.py:

~~~python
TASK_POLICIES[TASK_ID] = TaskPolicy(
    task_id=TASK_ID,
    label="副本扫荡",
    entry="MJA_Daily_DUNGEON_SWEEP_DAILY",
    risk_levels=frozenset({RiskLevel.CONSUMPTIVE, RiskLevel.COMBAT}),
    max_steps=160,
    action_caps={
        "open_dungeon": 1,
        "scroll_dungeon_list": 4,
        "select_yanwangling": 1,
        "open_sweep_panel": 1,
        "select_yanwangling_in_panel": 1,
        "select_master_80": 1,
        "assign_sweep_ticket": 100,
        "start_yanwangling_master_sweep": 1,
        "confirm_yanwangling_master_sweep": 1,
        "dismiss_sweep_result": 1,
        "close_dungeon": 1,
        "open_function_panel_verify": 1,
        "open_daily_tasks_verify": 1,
        "scroll_daily_dungeon_row": 1,
    },
    approved_resources=frozenset({"副本票"}),
)
~~~

The definition uses `initial_state = "home"`. On the normal dungeon page, if 燕王秘陵 is not visible, `scroll_dungeon_list` runs at most four times. Its coordinates are derived from the recognized viewport box and current calibrated frame; the historical 984x768 gesture is evidence for direction/hold/duration only and is never replayed as fixed coordinates. The executor must emit one mouse move, down, 160 held-drag steps and up for the single gesture. If the list does not change or the target remains absent after four gestures, return `failed/DUNGEON_LIST_TARGET_MISSING`.

After selecting and re-verifying title `燕王秘陵 / 云州·燕王秘陵`, open the sweep panel, independently select 燕王秘陵 and exact `大师 80级`, and parse both available and assigned 副本票 counters as unique integers. Available tickets must be 0..100. Above 100 is `failed/DUNGEON_TICKET_CAP` before assignment. Click only the recognized `+` target once per remaining ticket, requiring assigned count to increase by exactly one after each recapture; cap at the initial available count and 100. When assigned equals initial available and is positive, click 开始扫荡 once, verify a normal `燕王秘陵(大师)` confirmation showing the same ticket count and stored resource 副本票, then confirm once. This is one sweep operation using all assigned tickets, not one sweep per ticket.

At every state, the exact full-bag toast `背包已满，请先进行装备分解后再进行扫荡` returns `failed/DUNGEON_BAG_FULL`; it is not `blocked_safety` unless a true paid/login/verification/unknown-currency danger co-occurs. Never expose disassemble, salvage or equipment-confirm action IDs. After a normal result, close through a recognized target, return to 日常任务, allow at most one box-relative list swipe, and verify `通关或扫荡一次副本` is complete or claimable without clicking its reward. Return `completed` only after a confirmed sweep and daily-row postcondition. With zero tickets, still verify the daily row: return `already_complete` only when that row is already complete, otherwise `not_eligible/NO_DUNGEON_TICKETS`. An unchanged assignment/result or missing daily row is failed.

**Pipeline contract:**

~~~json
{
  "MJA_Daily_DUNGEON_SWEEP_DAILY": {
    "recognition": "DirectHit",
    "action": "Custom",
    "custom_action": "DailyWorkflowAction",
    "custom_action_param": {"task_id": "DUNGEON_SWEEP_DAILY"}
  },
  "MJA_DUNGEON_SWEEP_DAILY_YANWANG_MAIN": {
    "recognition": "TemplateMatch",
    "template": "daily/DUNGEON_SWEEP_DAILY/yanwangling_main.png",
    "action": "DoNothing",
    "next": ["MJA_DUNGEON_SWEEP_DAILY_TARGET"]
  },
  "MJA_DUNGEON_SWEEP_DAILY_MASTER_80": {
    "recognition": "TemplateMatch",
    "template": "daily/DUNGEON_SWEEP_DAILY/master_80_row.png",
    "action": "DoNothing"
  },
  "MJA_DUNGEON_SWEEP_DAILY_TARGET": {
    "recognition": "TemplateMatch",
    "template": "daily/DUNGEON_SWEEP_DAILY/sweep_target.png",
    "action": "DoNothing"
  },
  "MJA_DUNGEON_SWEEP_DAILY_BAG_FULL": {
    "recognition": "TemplateMatch",
    "template": "daily/DUNGEON_SWEEP_DAILY/bag_full.png",
    "action": "DoNothing"
  }
}
~~~

**TDD, live verification, and handoff:**

- [ ] **Red, 3 minutes:** Test box-relative four-gesture list bound and changed-list postcondition; exact 燕王秘陵 title plus 大师 80级; unique available/assigned ticket parsing; one-by-one + assignment up to the initial ticket count; one start/confirm using all tickets; completed only after the daily row; zero tickets plus completed row already_complete, zero tickets plus incomplete row not_eligible; failed bag-full/over-cap/unchanged assignment; blocked_safety only for true paid/verification/UNKNOWN_DIALOG; and absence of disassemble/salvage/equipment-confirm actions.
- [ ] **Red, 2 minutes:** Run install/.venv/bin/python -m pytest tests/workflows/test_dungeon_sweep_daily.py -q. Expected collection failure: ModuleNotFoundError: No module named 'agent.workflows.definitions.dungeon_sweep_daily'.
- [ ] **Green implementation, 5 minutes:** Implement the transition table above: bounded held-drag search, exact dungeon and master-row selection, + assignment until assigned equals initial available, one start/confirm, result handling and final daily-row verification. Return failed with DUNGEON_BAG_FULL for full bag and DUNGEON_TICKET_CAP for over-cap tickets; blocked_safety only for true danger; already_complete only for zero tickets plus a completed daily row; not_eligible for zero tickets plus an incomplete row; and failed for unchanged count/result. Never decompose.
- [ ] **Green pipeline and interface, 3 minutes:** Add Yanwangling main and bag-full recognizers and append this exact entry; do not add any disassemble, salvage or standard click node:
~~~json
{
  "name": "dungeon_sweep_daily",
  "label": "副本扫荡",
  "entry": "MJA_Daily_DUNGEON_SWEEP_DAILY",
  "default_check": false,
  "resource": ["mja"],
  "controller": ["macos"]
}
~~~
- [ ] **Green fixtures, 4 minutes:** Capture entry on the dungeon selector, actionable on exact 燕王秘陵(大师) with visible available/assigned ticket counters and + target, completed on the daily dungeon row, and danger with a true paid, verification or UNKNOWN_DIALOG signal. Manifest contains exactly schema_version, task_id, reference_size and cases; each case contains image, expected_page, expected_targets and expected_status. Capture a real supplemental full-bag crop and assert it produces TaskStatus.FAILED/DUNGEON_BAG_FULL with no decomposition input. The danger fixture expected status is blocked_safety.
- [ ] **Green fixture tests, 3 minutes:** Run the foundation fixture validator and task test. Expected actionable assignment increases one at a time up to the captured available count, exactly one start/confirm follows, zero-ticket completed-row branch has no assignment/start/confirm input, bag-full returns failed with DUNGEON_BAG_FULL and no decomposition input, danger returns blocked_safety with no input, and no disassembly transition exists.
- [ ] **Live verification, 5 minutes:** Run install/.venv/bin/python -m tools.run_cli --task dungeon_sweep_daily. Save diagnostics/YYYY-MM-DD/DUNGEON_SWEEP_DAILY/run-id/ and append its relative paths to docs/verification/2026-07-28-mja-daily-workflows-batch-2.md. Record exact 燕王秘陵(大师) marker, current ticket count, each sweep, result marker and bag state; leave verification/tasks/DUNGEON_SWEEP_DAILY.json for the later aggregate admission plan.
- [ ] **Live postcondition/no-op, 4 minutes:** Verify the held-drag stayed inside the recognized list, only exact 燕王秘陵(大师) was selected, assigned count reached the initial available ticket count, exactly one sweep was started/confirmed, the daily row became complete/claimable, and no disassembly input occurred. Re-run with zero tickets and the completed daily row; expect already_complete with zero assignment/start/confirm inputs. Zero tickets with an incomplete row is not_eligible. A previously verified bag-full state remains failed with DUNGEON_BAG_FULL. Any ticket ambiguity, other dungeon, paid signal or disassembly screen stops before protected input.
- [ ] **Commit, 2 minutes:**
~~~bash
git add -- agent/workflows/catalog.py agent/workflows/registry.py agent/workflows/definitions/__init__.py \
  agent/workflows/definitions/dungeon_sweep_daily.py \
  assets/resource/pipeline/daily/dungeon_sweep_daily.json \
  assets/resource/image/daily/DUNGEON_SWEEP_DAILY/entry.png \
  assets/resource/image/daily/DUNGEON_SWEEP_DAILY/dungeon_entry.png \
  assets/resource/image/daily/DUNGEON_SWEEP_DAILY/dungeon_selector.png \
  assets/resource/image/daily/DUNGEON_SWEEP_DAILY/dungeon_list_viewport.png \
  assets/resource/image/daily/DUNGEON_SWEEP_DAILY/yanwangling_main.png \
  assets/resource/image/daily/DUNGEON_SWEEP_DAILY/yanwangling_title.png \
  assets/resource/image/daily/DUNGEON_SWEEP_DAILY/master_80_row.png \
  assets/resource/image/daily/DUNGEON_SWEEP_DAILY/sweep_target.png \
  assets/resource/image/daily/DUNGEON_SWEEP_DAILY/ticket_counter.png \
  assets/resource/image/daily/DUNGEON_SWEEP_DAILY/assigned_ticket_counter.png \
  assets/resource/image/daily/DUNGEON_SWEEP_DAILY/ticket_plus.png \
  assets/resource/image/daily/DUNGEON_SWEEP_DAILY/start_sweep.png \
  assets/resource/image/daily/DUNGEON_SWEEP_DAILY/confirm_sweep.png \
  assets/resource/image/daily/DUNGEON_SWEEP_DAILY/expected_sweep_result.png \
  assets/resource/image/daily/DUNGEON_SWEEP_DAILY/expected_sweep_result_close.png \
  assets/resource/image/daily/DUNGEON_SWEEP_DAILY/bag_full.png \
  assets/resource/image/daily/DUNGEON_SWEEP_DAILY/dungeon_close.png \
  assets/resource/image/daily/DUNGEON_SWEEP_DAILY/function_panel_entry.png \
  assets/resource/image/daily/DUNGEON_SWEEP_DAILY/daily_tasks_entry.png \
  assets/resource/image/daily/DUNGEON_SWEEP_DAILY/daily_list_viewport.png \
  assets/resource/image/daily/DUNGEON_SWEEP_DAILY/daily_dungeon_complete.png \
  tests/fixtures/DUNGEON_SWEEP_DAILY/manifest.json \
  tests/fixtures/DUNGEON_SWEEP_DAILY/entry.png \
  tests/fixtures/DUNGEON_SWEEP_DAILY/actionable.png \
  tests/fixtures/DUNGEON_SWEEP_DAILY/completed.png \
  tests/fixtures/DUNGEON_SWEEP_DAILY/danger.png \
  tests/workflows/test_dungeon_sweep_daily.py \
  assets/interface.json
git commit -m "feat: add Yanwangling dungeon sweep daily workflow"
~~~

### Task 7: Cross-task contract, interface, fixture and calibration gate

**Files:**

- Update: `tests/workflows/test_hero_dispatch_daily.py`
- Update: `tests/workflows/test_buy_tea_daily.py`
- Update: `tests/workflows/test_spend_condensate_daily.py`
- Update: `tests/workflows/test_martial_study_breakthrough_daily.py`
- Update: `tests/workflows/test_eat_stamina_food_daily.py`
- Update: `tests/workflows/test_dungeon_sweep_daily.py`
- Create: `docs/verification/2026-07-28-mja-daily-workflows-batch-2.md`

**Interfaces:**

- Each test imports foundation contracts rather than a local substitute.
- Each pipeline is validated by foundation install verification.
- Each fixture is passed to foundation validate_fixture_case with an InputSpy.
- Each workflow is selected through tools.run_cli --task and enters via DailyWorkflowAction.
- Each task name is lowercase and is looked up in the singular assets/interface.json task array.
- The Markdown report is a human-readable command/result/evidence index only. It contains no verification_state, live_pending or live_verified field and is not a substitute for verification/tasks/{TASK_ID}.json; the later aggregate admission plan exclusively creates those machine records.
- The interface must retain:

~~~json
{
  "agent": {
    "child_exec": ".venv/bin/python3",
    "child_args": ["agent/main.py"],
    "identifier": "mja-python-agent"
  }
}
~~~

MaaPiCli appends socket ID; no socket ID is placed in child_args.

The cross-task test consumes these exact values and does not create another catalog or status model:

~~~python
from collections.abc import Mapping

BATCH2_TASK_IDS = (
    "HERO_DISPATCH_DAILY",
    "BUY_TEA_DAILY",
    "SPEND_CONDENSATE_DAILY",
    "MARTIAL_STUDY_BREAKTHROUGH_DAILY",
    "EAT_STAMINA_FOOD_DAILY",
    "DUNGEON_SWEEP_DAILY",
)
RUNTIME_STATUSES = frozenset({
    "completed", "already_complete", "not_eligible", "blocked_safety", "failed",
})
FIXTURE_CASE_KEYS = ("entry", "actionable", "completed", "danger")
FIXTURE_CASE_FIELDS = ("image", "expected_page", "expected_targets", "expected_status")

def assert_batch2_manifest(manifest: Mapping[str, object]) -> None:
    assert set(manifest) == {"schema_version", "task_id", "reference_size", "cases"}
    cases = manifest["cases"]
    assert tuple(cases) == FIXTURE_CASE_KEYS
    for case in cases.values():
        assert set(case) == set(FIXTURE_CASE_FIELDS)
        assert case["expected_status"] is None or case["expected_status"] in RUNTIME_STATUSES

def assert_project_interface(interface: Mapping[str, object]) -> None:
    names = [item["name"] for item in interface["task"]]
    assert all(name == name.lower() for name in names)
    assert all(item["entry"] == "MJA_Daily_" + item["name"].upper() for item in interface["task"] if item["name"] != "mail_smoke_test")
    assert interface["agent"]["child_args"] == ["agent/main.py"]
~~~

**TDD and final verification steps:**

- [ ] **Red, 4 minutes:** Add cross-task assertions to the six canonical tests: exact five runtime statuses only; no live_pending or live_verified in TaskResult serialization; VisualEvidence.danger_hits and SafetyReason.UNKNOWN_DIALOG block input; every side-effect transition has page and target evidence from one frame; every pipeline has only its DirectHit custom-action root plus recognizer-only DoNothing nodes and no forbidden action; each fixture reference_size matches calibration.json; each manifest contains exactly schema_version, task_id, reference_size and cases, with cases.{kind}.{image,expected_page,expected_targets,expected_status}; no task is registered twice.
- [ ] **Run red suite, 3 minutes:**
~~~bash
install/.venv/bin/python -m pytest tests/workflows/test_hero_dispatch_daily.py tests/workflows/test_buy_tea_daily.py tests/workflows/test_spend_condensate_daily.py tests/workflows/test_martial_study_breakthrough_daily.py tests/workflows/test_eat_stamina_food_daily.py tests/workflows/test_dungeon_sweep_daily.py -q
~~~
Expected: collection fails first with ModuleNotFoundError: No module named 'agent.workflows.definitions.hero_dispatch_daily'; after each task is added, the next missing canonical definition or real PNG is the reported failure.
- [ ] **Green, 4 minutes:** Run foundation fixture and install validators:

~~~bash
install/.venv/bin/python -m tools.validate_fixtures --all-implemented
install/.venv/bin/python -m tools.verify_install install
~~~

Expected: all six task assets, definitions, four fixture states, interface entries and forbidden-action checks pass.
- [ ] **Green, 4 minutes:** Run the complete focused suite and static checks:

~~~bash
install/.venv/bin/python -m pytest tests/workflows/test_hero_dispatch_daily.py tests/workflows/test_buy_tea_daily.py tests/workflows/test_spend_condensate_daily.py tests/workflows/test_martial_study_breakthrough_daily.py tests/workflows/test_eat_stamina_food_daily.py tests/workflows/test_dungeon_sweep_daily.py -q
install/.venv/bin/python -m ruff check agent/workflows/definitions tests/workflows
git diff --check
~~~

- [ ] **Live gate, 5 minutes:** For each task run only the foundation CLI selector from an authorized foreground host. Confirm the exact diagnostics directory pattern, result.json five-state status and action-trace frame IDs. Add checkout revision, command, canonical task ID, run ID, result, relative evidence paths, independent postcondition, no-op outcome and any unavailable branch in prose to docs/verification/2026-07-28-mja-daily-workflows-batch-2.md. Do not create or mutate verification/tasks/{TASK_ID}.json in this batch.
- [ ] **Self-audit, 4 minutes:** Inspect each task for its exact business cap, current-box input, calibration reference, danger hard stop, postcondition, no-op rerun and precise add list. Confirm no 1280x720 assumption, no daily-task or unrelated reward node, no StartApp, no standard Click, no keyboard, no disassembly and no unbounded loop. Confirm Hero's own first-row dispatch claim is the only allowed claim-like transition and remains same-frame authorized.
- [ ] **Commit the cross-task test gate, 2 minutes:**
~~~bash
git add -- tests/workflows/test_hero_dispatch_daily.py \
  tests/workflows/test_buy_tea_daily.py \
  tests/workflows/test_spend_condensate_daily.py \
  tests/workflows/test_martial_study_breakthrough_daily.py \
  tests/workflows/test_eat_stamina_food_daily.py \
  tests/workflows/test_dungeon_sweep_daily.py \
  docs/verification/2026-07-28-mja-daily-workflows-batch-2.md
git commit -m "test: gate batch 2 daily workflow contracts"
~~~

## Final Handoff Checklist

- [ ] capture fallback quality gate is green before any Batch 2 live run.
- [ ] foundation types and runner are imported from their approved modules; no parallel model, runtime, action, diagnostics or CLI exists.
- [ ] Batch 1 remains registered and its tests remain green.
- [ ] six canonical definitions, six lower-case daily pipelines, six canonical fixture directories and six canonical tests exist.
- [ ] every manifest contains exactly schema_version, task_id, reference_size and cases.entry/actionable/completed/danger; every case contains exactly image, expected_page, expected_targets and expected_status, with four real PNGs captured from the calibrated controller.
- [ ] assets/interface.json adds exactly six lower-case task names, each with MJA_Daily_ plus canonical uppercase entry, default_check false, mja resource and macos controller.
- [ ] agent.child_args remains exactly ["agent/main.py"]; socket ID is appended by MaaPiCli.
- [ ] every runtime result uses only completed, already_complete, not_eligible, blocked_safety or failed.
- [ ] the Batch 2 Markdown report contains only a human-readable command/result/evidence index and no verification_state, live_pending or live_verified fields.
- [ ] no Batch 2 task creates a machine verification record; the later aggregate admission plan owns every verification/tasks/{TASK_ID}.json file.
- [ ] VisualEvidence.danger_hits is consumed and SafetyReason.UNKNOWN_DIALOG produces blocked_safety with no input.
- [ ] no workflow assumes 1280x720; calibration.json is consumed and action boxes come from current recognition.
- [ ] diagnostics are under diagnostics/YYYY-MM-DD/TASK_ID/run-id/.
- [ ] Hero uses only the first visible item without scrolling, applies 智能配置 before every dispatch, rechecks after claims, and caps each repeated protected action at six.
- [ ] Tea treats 10/10 as ten available units, separates max selection from one 凝晶 purchase, and verifies zero/sold-out stock plus usable inventory.
- [ ] Condensate inspects and buys the full current stock from both 偃武 and 云州 even when initial progress is 10000, then verifies the daily row without claiming it.
- [ ] Martial claims 成功 cards first, fills all visible + slots, skips already-breaking characters, studies each slot at most three times, checks 馈赠奖励 last, verifies the daily row, and never accelerates timers.
- [ ] Food uses only exact 龙井虾仁 +15, at most six, permits only same-category replacement, and accepts the exact too-full toast only from the attempted fourth item onward.
- [ ] Dungeon uses a bounded box-relative held drag, selects only exact 燕王秘陵(大师), assigns all current tickets before one sweep, verifies the daily row, returns failed with DUNGEON_BAG_FULL on full bag, and never disassembles.
- [ ] every commit uses exact path-scoped git add and never stages AGENTS.md, diagnostics, runtime archives or broad directories.
