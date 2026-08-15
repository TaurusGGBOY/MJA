# MJA MFW 日常任务批次 B Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **2026-08-05 target correction (authoritative):** 批次 B 的实机目标是本机 macOS/iOS 游戏窗口，通过 `MacOS` Controller + `ScreenCaptureKit` + `GlobalEvent` 验收；不是 Android 模拟器。Android fixture、ADB 命令和 Android live gate 不能作为当前 MFW 任务的验收证据。

**Goal:** 将购买茶、消耗凝晶、食用体力食物和剑林凝晶体力迁移为资源名、单次次数和每日预算均受当前帧门禁保护的独立 MFW 任务。

**Architecture:** Maa Pipeline 负责业务页导航、数量选择和后置条件，所有购买、食用、确认和挑战输入都调用 `GuardedInput`。剑林只把纯挑战数量计算留给 `PlanJianlinChallenge`，该 Action 不截图、不导航、不发送输入。

**Tech Stack:** Maa Pipeline JSON、embedded Python Agent、ProjectInterface v2、pytest、现有 Android fixture、MFW direct-run

## Global Constraints

- 开始本计划前，批次 A 的 9 个单项、简化版、手工全选、同日重跑和 Abort 隔离实机门必须通过。
- 本批迁移顺序固定为 `BUY_TEA_DAILY`、`SPEND_CONDENSATE_DAILY`、`EAT_STAMINA_FOOD_DAILY`、`JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY`。
- 资源政策必须与冻结基线一致：茶只消耗 `文` 且每日最多 500；凝晶购买只消耗 `凝晶` 且总上限 100000；食物只消耗 `龙井虾仁` 且最多 6；剑林最多消耗 `紫色魂玉` 1 和体力 120。
- 相同候选运行中，`TaskRunStore` 在发送输入前原子累计动作次数/资源预算；`observed_amount` 是当前帧价格/消耗 OCR，`budget_amount` 是冻结 policy 的累计单位。除剑林体力购买外二者相等；剑林必须 `observed_amount=10` 紫色魂玉、`budget_amount=1` 次购买。超过政策时零输入并显式 Abort。
- 价格 OCR 冲突、资源名不一致、数量不唯一、真实货币/充值入口、第二次体力购买或未知确认框必须零输入并 Abort。
- 已售罄、体力过满、资源正常不足、功能未开放属于 `already_complete` 或 `not_eligible`，不得伪装为失败。
- 每个副作用动作后必须取得新截图验证库存、状态、体力或结果；超时不得无条件重放购买/食用/挑战。
- 不使用 `daily_all`、中央 driver、shell input、speedrun 或 MFW 队列重试。
- macOS 屏幕录制/辅助功能权限、真实窗口截图和当前坐标校准缺失时，任务只能停留在静态候选状态，不得伪造 fixture 或 live evidence。
- 现有未跟踪 `uv.lock` 不修改、不暂存、不提交。

---

## 批次 B 文件边界

| Canonical ID | Pipeline | 资源上限 |
| --- | --- | --- |
| `BUY_TEA_DAILY` | `assets/resource/base/pipeline/daily/buy_tea_daily.json` | `文: 500` |
| `SPEND_CONDENSATE_DAILY` | `assets/resource/base/pipeline/daily/spend_condensate_daily.json` | `凝晶: 100000` |
| `EAT_STAMINA_FOOD_DAILY` | `assets/resource/base/pipeline/daily/eat_stamina_food_daily.json` | `龙井虾仁: 6` |
| `JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY` | `assets/resource/base/pipeline/daily/jianlin_resource_condensate_stamina_daily.json` | `紫色魂玉: 1`, `体力: 120` |

Evidence sources are the same-basename files under `assets/resource_android/pipeline/daily/` and `agent/workflows/definitions/`. `BUY_TEA_DAILY`, `SPEND_CONDENSATE_DAILY`, and `EAT_STAMINA_FOOD_DAILY` also consume the concrete behavior in `agent/workflows/definitions/batch23.py`; Jianlin consumes its dedicated definition's pure planner semantics. These sources freeze page evidence, action IDs and postconditions only; central Python navigation does not move into the target.

Before each task's live/test gate, manually place the emulator on the recognized normal-ineligible state and then on a supported off-route page, capturing the two missing fixture cases with these exact screenshot-only commands:

```bash
python3 -m tools.capture_mfw_fixture --task-id BUY_TEA_DAILY --case not_eligible
python3 -m tools.capture_mfw_fixture --task-id BUY_TEA_DAILY --case known_drift
python3 -m tools.capture_mfw_fixture --task-id SPEND_CONDENSATE_DAILY --case not_eligible
python3 -m tools.capture_mfw_fixture --task-id SPEND_CONDENSATE_DAILY --case known_drift
python3 -m tools.capture_mfw_fixture --task-id EAT_STAMINA_FOOD_DAILY --case not_eligible
python3 -m tools.capture_mfw_fixture --task-id EAT_STAMINA_FOOD_DAILY --case known_drift
python3 -m tools.capture_mfw_fixture --task-id JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY --case not_eligible
python3 -m tools.capture_mfw_fixture --task-id JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY --case known_drift
```

Each live-gate command block is an ordered operator checklist. Run its concrete `mfw_install.py` line first, then pause, open the newly named output once, create and save the exact profile name shown with only the required task(s), close MFW, and only then run the following `mfw_profile.py` line. Never open or mutate `install/mfw-foundation-candidate`; it is the immutable release/runtime base.

### Task 1: 扩展资源消耗任务契约

**Files:**
- Create: `tests/mfw/tasks/test_batch_b.py`
- Modify: `tests/mfw/task_contract.py`
- Modify: `tests/mfw/test_task_contract_helpers.py`
- Modify: `tests/test_mfw_safety.py`
- Modify: `tests/test_mfw_presets.py`

**Interfaces:**
- Consumes: `TaskContract`、`TASK_POLICIES`、`GuardedInput`、最终完整版顺序常量。
- Produces: `assert_resource_guard(task_id, action_id, resource, maximum)`；`assert_no_side_effect_retry(nodes, action_id)`。

- [ ] **Step 1: 写四任务和资源预算失败测试**

```python
BATCH_B = [
    TaskContract("BUY_TEA_DAILY", "buy_tea_daily.json"),
    TaskContract("SPEND_CONDENSATE_DAILY", "spend_condensate_daily.json"),
    TaskContract("EAT_STAMINA_FOOD_DAILY", "eat_stamina_food_daily.json"),
    TaskContract("JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY", "jianlin_resource_condensate_stamina_daily.json"),
]


def test_batch_b_contracts():
    for contract in BATCH_B:
        assert_task_contract(contract)
        assert_fixture_matrix(
            contract.task_id,
            required={"entry", "actionable", "completed", "not_eligible", "known_drift", "danger"},
        )


@pytest.mark.parametrize(("task_id", "resource", "maximum"), [
    ("BUY_TEA_DAILY", "文", 500),
    ("SPEND_CONDENSATE_DAILY", "凝晶", 100_000),
    ("EAT_STAMINA_FOOD_DAILY", "龙井虾仁", 6),
    ("JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY", "紫色魂玉", 1),
    ("JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY", "体力", 120),
])
def test_resource_budgets(task_id, resource, maximum):
    assert TASK_POLICIES[task_id].resource_caps[resource] == maximum
```

- [ ] **Step 2: 运行测试确认先失败**

Run: `uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/mfw/tasks/test_batch_b.py tests/test_mfw_safety.py -q`

Expected: FAIL because batch-B task declarations/Pipelines are absent and helper assertions do not exist.

- [ ] **Step 3: 实现资源契约辅助器**

```python
def assert_no_side_effect_retry(nodes: Mapping[str, Mapping[str, object]], action_id: str) -> None:
    matches = guarded_nodes_for_action(nodes, action_id)
    assert matches, f"missing guarded action {action_id}"
    for node in matches:
        assert node.get("retry_times", 0) == 0
        assert action_id not in reachable_on_error_actions(nodes, node)
```

`assert_resource_guard` reads each CustomAction JSON param and requires exact canonical task ID, existing action ID, exact resource string, integer amount, same-frame page/target evidence nodes, and a fresh postcondition node. `tests/test_mfw_presets.py` continues to assert imported IDs are a unique order-preserving subset of the final 17-ID order.

- [ ] **Step 4: 运行辅助器测试**

Run: `uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/mfw/test_task_contract_helpers.py tests/test_mfw_safety.py -q`

Expected: PASS，malformed resource/amount/retry examples are rejected.

- [ ] **Step 5: 提交**

```bash
git add tests/mfw/task_contract.py tests/mfw/tasks/test_batch_b.py tests/mfw/test_task_contract_helpers.py tests/test_mfw_safety.py tests/test_mfw_presets.py
git commit -m "test: define consumptive MFW task contracts"
```

### Task 2: 迁移 BUY_TEA_DAILY

**Files:**
- Create: `assets/tasks/日常/BUY_TEA_DAILY.json`
- Create: `assets/resource/base/pipeline/daily/buy_tea_daily.json`
- Modify: `assets/interface.mfw.json`
- Modify: `tests/mfw/tasks/test_batch_b.py`
- Modify: `tests/fixtures/BUY_TEA_DAILY/manifest.json`
- Create from captured state: `tests/fixtures/BUY_TEA_DAILY/not_eligible.png`
- Create from captured state: `tests/fixtures/BUY_TEA_DAILY/known_drift.png`
- Create after live run: `verification/mfw/BUY_TEA_DAILY.json`

**Interfaces:**
- Consumes: 公共启动、`GuardedInput`、policy `文: 500`。
- Produces: `MJA_BUY_TEA_DAILY_START`; exact frozen action IDs `open_painting_scroll`, `select_yanwu_world`, `open_universal_shop`, `scroll_tea_list`, `open_tea_tab`, `open_tea_purchase`, `set_tea_quantity_max`, `buy_tea`, `dismiss_tea_purchase_result`。

- [ ] **Step 1: 写茶购买限制测试**

```python
def test_buy_tea_is_one_purchase_of_wen_at_most_500():
    nodes = task_nodes("BUY_TEA_DAILY")
    assert_action_limit("BUY_TEA_DAILY", "buy_tea", 1)
    assert_resource_guard(nodes, "buy_tea", "文", 500)
    assert_no_side_effect_retry(nodes, "buy_tea")
    assert_outcome(nodes, "MJA_TEA_SOLD_OUT", "already_complete", "tea.sold_out")
    assert_abort_code(nodes, "MJA_TEA_PRICE_UNSAFE", "TEA_PRICE_OR_CURRENCY_UNVERIFIED")
```

- [ ] **Step 2: 运行测试确认先失败**

Run: `uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/mfw/tasks/test_batch_b.py -k buy_tea -q`

Expected: FAIL because task/Pipeline are absent.

- [ ] **Step 3: 实现买茶 Pipeline**

```json
{"task":[{"name":"BUY_TEA_DAILY","label":"购买茶","default_check":true,"group":["日常"],"entry":"MJA_BUY_TEA_DAILY_START"}]}
```

Start the target from `assets/resource_android/pipeline/daily/buy_tea_daily.json`; retain its useful Maa recognitions, remove every central-driver delegate, and implement the guarded flow below.

Navigate home → painting → 演武 → universal shop; perform at most one bounded list scroll, open tea tab and tea purchase. Sold-out evidence returns `already_complete`. Select max quantity only when the purchase dialog uniquely identifies tea and `文`; OCR total cost must be an integer ≤500 before one `buy_tea`. Dismiss one recognized result and require sold-out/decremented inventory confirmation for `success`. Any other currency, recharge link, OCR failure or unchanged inventory Aborts without retrying purchase.

- [ ] **Step 4: 运行自动化与单项实机门**

```bash
uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/mfw/tasks/test_batch_b.py -k buy_tea -q
python3 tools/check_mfw_resources.py assets/resource/base
python3 tools/mfw_install.py --base-candidate install/mfw-foundation-candidate --output install/mfw-buy-tea-daily
python3 tools/mfw_profile.py run --install install/mfw-buy-tea-daily --profile-name live-BUY_TEA_DAILY
```

Expected: entry/actionable/completed/danger plus unsafe-currency fixture pass；live buy count ≤1 and total `文` ≤500；rerun sold-out/already_complete. Write evidence JSON.

- [ ] **Step 5: 提交**

```bash
git add assets/tasks/日常/BUY_TEA_DAILY.json assets/resource/base/pipeline/daily/buy_tea_daily.json assets/interface.mfw.json tests/mfw/tasks/test_batch_b.py tests/fixtures/BUY_TEA_DAILY verification/mfw/BUY_TEA_DAILY.json
git commit -m "feat: migrate guarded tea purchase to MFW"
```

### Task 3: 迁移 SPEND_CONDENSATE_DAILY

**Files:**
- Create: `assets/tasks/日常/SPEND_CONDENSATE_DAILY.json`
- Create: `assets/resource/base/pipeline/daily/spend_condensate_daily.json`
- Modify: `assets/interface.mfw.json`
- Modify: `tests/mfw/tasks/test_batch_b.py`
- Modify: `tests/fixtures/SPEND_CONDENSATE_DAILY/manifest.json`
- Create from captured state: `tests/fixtures/SPEND_CONDENSATE_DAILY/not_eligible.png`
- Create from captured state: `tests/fixtures/SPEND_CONDENSATE_DAILY/known_drift.png`
- Create after live run: `verification/mfw/SPEND_CONDENSATE_DAILY.json`

**Interfaces:**
- Consumes: 公共启动、policy `凝晶: 100000` 和 current-page probes。
- Produces: `MJA_SPEND_CONDENSATE_DAILY_START`; exact action IDs `open_function_panel`, `open_daily_tasks_initial`, `close_daily_tasks`, `open_painting_scroll`, `select_yanwu_world`, `open_yanwu_currency_purchase`, `close_yanwu_currency_purchase`, `set_yanwu_quantity_max`, `buy_yanwu_currency_max`, `dismiss_yanwu_reward_popup`, `select_yunzhou`, `open_yunzhou_currency_purchase`, `close_yunzhou_currency_purchase`, `set_yunzhou_quantity_max`, `buy_yunzhou_currency_max`, `dismiss_yunzhou_reward_popup`。

- [ ] **Step 1: 写双区域共享预算测试**

```python
def test_condensate_buys_yanwu_then_yunzhou_once_under_shared_budget():
    nodes = task_nodes("SPEND_CONDENSATE_DAILY")
    assert_ordered_actions(nodes, ["buy_yanwu_currency_max", "select_yunzhou", "buy_yunzhou_currency_max"])
    assert_resource_guard(nodes, "buy_yanwu_currency_max", "凝晶", 100_000)
    assert_resource_guard(nodes, "buy_yunzhou_currency_max", "凝晶", 100_000)
    assert_shared_resource_budget("SPEND_CONDENSATE_DAILY", "凝晶", 100_000)
    assert_no_side_effect_retry(nodes, "buy_yanwu_currency_max")
    assert_no_side_effect_retry(nodes, "buy_yunzhou_currency_max")
```

- [ ] **Step 2: 运行测试确认先失败**

Run: `uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/mfw/tasks/test_batch_b.py -k condensate -q`

Expected: FAIL because task/Pipeline are absent.

- [ ] **Step 3: 实现凝晶消耗 Pipeline**

```json
{"task":[{"name":"SPEND_CONDENSATE_DAILY","label":"消耗凝晶","default_check":true,"group":["日常"],"entry":"MJA_SPEND_CONDENSATE_DAILY_START"}]}
```

Start the target from `assets/resource_android/pipeline/daily/spend_condensate_daily.json`; retain its Maa page recognitions, remove every central-driver delegate, and implement the guarded flow below.

Start probes recognize and recover from daily page, painting, 演武, 云州 and either purchase dialog. Navigate to 演武 purchase, mark sold-out as that region complete, otherwise set max and buy once only when currency OCR is exactly `凝晶` and cumulative recognized cost remains ≤100000. After a fresh sold-out/inventory confirmation, move to 云州 and apply the same one-purchase rule using the shared budget. Both regions complete before mutation yields `already_complete`; completing missing purchases yields `success`; ambiguous recovery, non-凝晶 currency or budget overflow Aborts.

- [ ] **Step 4: 运行自动化与单项实机门**

```bash
uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/mfw/tasks/test_batch_b.py -k condensate -q
python3 tools/check_mfw_resources.py assets/resource/base
python3 tools/mfw_install.py --base-candidate install/mfw-foundation-candidate --output install/mfw-spend-condensate-daily
python3 tools/mfw_profile.py run --install install/mfw-spend-condensate-daily --profile-name live-SPEND_CONDENSATE_DAILY
```

Expected: all start-page fixtures and unsafe price fixture pass；live each purchase ≤1, combined spend ≤100000, rerun already_complete. Write evidence JSON.

- [ ] **Step 5: 提交**

```bash
git add assets/tasks/日常/SPEND_CONDENSATE_DAILY.json assets/resource/base/pipeline/daily/spend_condensate_daily.json assets/interface.mfw.json tests/mfw/tasks/test_batch_b.py tests/fixtures/SPEND_CONDENSATE_DAILY verification/mfw/SPEND_CONDENSATE_DAILY.json
git commit -m "feat: migrate guarded condensate spending to MFW"
```

### Task 4: 迁移 EAT_STAMINA_FOOD_DAILY

**Files:**
- Create: `assets/tasks/日常/EAT_STAMINA_FOOD_DAILY.json`
- Create: `assets/resource/base/pipeline/daily/eat_stamina_food_daily.json`
- Modify: `assets/interface.mfw.json`
- Modify: `tests/mfw/tasks/test_batch_b.py`
- Modify: `tests/fixtures/EAT_STAMINA_FOOD_DAILY/manifest.json`
- Create from captured state: `tests/fixtures/EAT_STAMINA_FOOD_DAILY/not_eligible.png`
- Create from captured state: `tests/fixtures/EAT_STAMINA_FOOD_DAILY/known_drift.png`
- Create after live run: `verification/mfw/EAT_STAMINA_FOOD_DAILY.json`

**Interfaces:**
- Consumes: policy `龙井虾仁: 6` 和 food/bag templates。
- Produces: `MJA_EAT_STAMINA_FOOD_DAILY_START`; exact action IDs `open_function_panel`, `open_bag`, `open_food_category`, `select_food_tab`, `inspect_food_candidate`, `eat_longjing_shrimp`, `confirm_food_buff_replace`, `close_bag`。

- [ ] **Step 1: 写食物名、六次上限和过满分流测试**

```python
def test_food_consumes_only_longjing_shrimp_at_most_six():
    nodes = task_nodes("EAT_STAMINA_FOOD_DAILY")
    assert_resource_guard(nodes, "eat_longjing_shrimp", "龙井虾仁", 6)
    assert_loop_bound(nodes, "MJA_FOOD_CANDIDATE_LOOP", maximum=6)
    assert_loop_bound(nodes, "MJA_FOOD_REPLACE_CONFIRM_LOOP", maximum=6)
    assert_outcome(nodes, "MJA_FOOD_STAMINA_FULL", "already_complete", "food.stamina_full")
    assert_outcome(nodes, "MJA_FOOD_NO_SAFE_CARD", "not_eligible", "food.longjing_shrimp_unavailable")
```

- [ ] **Step 2: 运行测试确认先失败**

Run: `uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/mfw/tasks/test_batch_b.py -k stamina_food -q`

Expected: FAIL because task/Pipeline are absent.

- [ ] **Step 3: 实现体力食物 Pipeline**

```json
{"task":[{"name":"EAT_STAMINA_FOOD_DAILY","label":"食用体力食物","default_check":true,"group":["日常"],"entry":"MJA_EAT_STAMINA_FOOD_DAILY_START"}]}
```

Start the target from `assets/resource_android/pipeline/daily/eat_stamina_food_daily.json`; retain useful Maa recognitions, remove every central-driver delegate, and implement the guarded flow below.

Navigate panel → bag → food category/tab. Inspect at most six candidates and authorize use only when the same frame identifies `龙井虾仁`, a positive available count and a unique use target. Full/overfull stamina returns `already_complete`; absence of a safe Longjing card returns `not_eligible`. Eat and optional buff-replacement confirm share a max-6 bound; after each use require decreased item count or increased stamina. Unknown food, quantity conflict, confirmation without Longjing context or unchanged postcondition Aborts.

- [ ] **Step 4: 运行自动化与单项实机门**

```bash
uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/mfw/tasks/test_batch_b.py -k stamina_food -q
python3 tools/check_mfw_resources.py assets/resource/base
python3 tools/mfw_install.py --base-candidate install/mfw-foundation-candidate --output install/mfw-eat-stamina-food-daily
python3 tools/mfw_profile.py run --install install/mfw-eat-stamina-food-daily --profile-name live-EAT_STAMINA_FOOD_DAILY
```

Expected: fixture pass；live use count ≤6 and only Longjing；full/no-item rerun has zero input. Write evidence JSON.

- [ ] **Step 5: 提交**

```bash
git add assets/tasks/日常/EAT_STAMINA_FOOD_DAILY.json assets/resource/base/pipeline/daily/eat_stamina_food_daily.json assets/interface.mfw.json tests/mfw/tasks/test_batch_b.py tests/fixtures/EAT_STAMINA_FOOD_DAILY verification/mfw/EAT_STAMINA_FOOD_DAILY.json
git commit -m "feat: migrate guarded stamina food task to MFW"
```

### Task 5: 提取纯剑林挑战计划器

**Files:**
- Create: `agent/custom/action/jianlin_planner.py`
- Modify: `agent/custom/action/__init__.py`
- Modify: `agent/main.py`
- Modify: `tests/mfw/fakes.py`
- Create: `tests/test_mfw_jianlin_planner.py`

**Interfaces:**
- Consumes: 当前纯算法语义 `ChallengePlan(count, multiplier)` 和 safe multipliers。
- Produces: `ChallengePlan`; `plan_safe_challenge(stamina, cost, visible_max, safe_multipliers) -> ChallengePlan`; Maa action `PlanJianlinChallenge`，通过官方 `context.override_next(dispatch_node, [branch])` 选择预声明 Maa 分支。

- [ ] **Step 1: 写边界表驱动测试**

```python
@pytest.mark.parametrize(("stamina", "cost", "visible_max", "multipliers", "expected"), [
    (120, 20, 6, (1, 2, 3), ChallengePlan(2, 3)),
    (40, 20, 6, (1, 2, 3), ChallengePlan(1, 2)),
])
def test_plan_safe_challenge(stamina, cost, visible_max, multipliers, expected):
    assert plan_safe_challenge(stamina, cost, visible_max, multipliers) == expected


@pytest.mark.parametrize(("stamina", "cost", "visible_max", "multipliers"), [
    (19, 20, 6, (1, 2, 3)),
    (120, 0, 6, (1, 2, 3)),
    (120, 20, 0, (1, 2, 3)),
    (120, 20, 6, ()),
])
def test_plan_safe_challenge_rejects_unsafe_inputs(stamina, cost, visible_max, multipliers):
    with pytest.raises(ValueError):
        plan_safe_challenge(stamina, cost, visible_max, multipliers)


def test_planner_action_selects_declared_branch_without_controller_access():
    context = FakeContext()
    context.nodes.add("MJA_JIANLIN_SET_COUNT_2_MULTIPLIER_3")
    argv = jianlin_planner_argv(stamina=120, cost=20, visible_max=6, multipliers=(1, 2, 3))
    assert PlanJianlinChallenge().run(context, argv) is True
    assert context.next_overrides == [
        ("MJA_JIANLIN_PLAN_DISPATCH", ["MJA_JIANLIN_SET_COUNT_2_MULTIPLIER_3"])
    ]
    assert context.controller.actions == []
```

- [ ] **Step 2: 运行测试确认先失败**

Run: `uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/test_mfw_jianlin_planner.py -q`

Expected: FAIL because narrow planner does not exist.

- [ ] **Step 3: 实现无输入纯计算和注册 Action**

```python
@dataclass(frozen=True)
class ChallengePlan:
    count: int
    multiplier: int


def plan_safe_challenge(
    stamina: int,
    cost: int,
    visible_max: int,
    safe_multipliers: tuple[int, ...],
) -> ChallengePlan:
    if stamina < 0 or cost <= 0 or visible_max <= 0 or not safe_multipliers:
        raise ValueError("unsafe challenge inputs")
    multipliers = tuple(value for value in safe_multipliers if value > 0)
    if not multipliers:
        raise ValueError("unsafe multipliers")
    for multiplier in sorted(multipliers, reverse=True):
        count = min(stamina // (cost * multiplier), visible_max)
        if count >= 1:
            return ChallengePlan(count=count, multiplier=multiplier)
    raise ValueError("insufficient stamina")
```

`PlanJianlinChallenge.run` receives one Maa `And` recognition whose indexed OCR sub-results contain stamina, cost, visible max and safe multipliers. It invokes the pure function, builds branch `MJA_JIANLIN_SET_COUNT_{count}_MULTIPLIER_{multiplier}`, verifies that branch with `context.get_node_data`, and calls `context.override_next("MJA_JIANLIN_PLAN_DISPATCH", [branch])`. The Pipeline predeclares all 36 branches for count 1–12 and multiplier 1–3; each branch uses guarded `set_safe_count`/`set_safe_multiplier` inputs before joining the challenge node. The Action returns false on malformed OCR or missing branch and must not access `context.tasker.controller`, image, filesystem, adb or diagnostics.

Extend `FakeContext` with `nodes: set[str]`, `next_overrides: list[tuple[str, list[str]]]`, `get_node_data(name)` returning a non-empty dict only for declared nodes, and `override_next(name, next_list)` recording the pair and returning true.

- [ ] **Step 4: 运行 planner 和 Agent import 测试**

Run: `uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/test_mfw_jianlin_planner.py tests/test_mfw_agent_entry.py -q`

Expected: PASS，AST test confirms planner has no input/controller imports.

- [ ] **Step 5: 提交**

```bash
git add agent/custom/action/jianlin_planner.py agent/custom/action/__init__.py agent/main.py tests/mfw/fakes.py tests/test_mfw_jianlin_planner.py
git commit -m "feat: extract pure Jianlin challenge planner"
```

### Task 6: 迁移 JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY

**Files:**
- Create: `assets/tasks/日常/JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY.json`
- Create: `assets/resource/base/pipeline/daily/jianlin_resource_condensate_stamina_daily.json`
- Modify: `assets/interface.mfw.json`
- Modify: `tests/mfw/tasks/test_batch_b.py`
- Modify: `tests/fixtures/JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY/manifest.json`
- Create from captured state: `tests/fixtures/JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY/not_eligible.png`
- Create from captured state: `tests/fixtures/JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY/known_drift.png`
- Create after live run: `verification/mfw/JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY.json`

**Interfaces:**
- Consumes: `PlanJianlinChallenge`, resources `紫色魂玉: 1`, `体力: 120`。
- Produces: `MJA_JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY_START`; exact action IDs `open_function_panel`, `open_daily_tasks`, `scroll_daily_jianlin`, `open_jianlin`, `select_jianlin_condensate`, `open_jianlin_stamina_purchase`, `buy_stamina_once`, `confirm_jianlin_stamina_purchase`, `close_postpurchase_stamina_prompt`, `dismiss_jianlin_stamina_result`, `set_safe_count`, `set_safe_multiplier`, `challenge_condensate`, `start_jianlin_battle`, `close_condensate_result`, `close_jianlin_page`。

- [ ] **Step 1: 写一次体力购买和十二轮挑战测试**

```python
def test_jianlin_has_one_verified_purchase_and_bounded_challenges():
    nodes = task_nodes("JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY")
    assert_resource_guard(nodes, "buy_stamina_once", "紫色魂玉", 1)
    assert_observed_resource_cost(nodes, "buy_stamina_once", "紫色魂玉", 10)
    assert_action_limit("JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY", "buy_stamina_once", 1)
    assert_abort_code(nodes, "MJA_JIANLIN_SECOND_OFFER", "JIANLIN_ESCALATED_STAMINA_OFFER")
    assert_loop_bound(nodes, "MJA_JIANLIN_CHALLENGE_LOOP", maximum=12)
    assert_resource_guard(nodes, "start_jianlin_battle", "体力", 120)
    assert_no_side_effect_retry(nodes, "buy_stamina_once")
    assert_no_side_effect_retry(nodes, "start_jianlin_battle")
```

- [ ] **Step 2: 运行测试确认先失败**

Run: `uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/mfw/tasks/test_batch_b.py -k jianlin -q`

Expected: FAIL because task/Pipeline are absent.

- [ ] **Step 3: 实现剑林 Pipeline**

```json
{"task":[{"name":"JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY","label":"剑林凝晶体力","default_check":true,"group":["日常"],"entry":"MJA_JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY_START"}]}
```

Start the target from `assets/resource_android/pipeline/daily/jianlin_resource_condensate_stamina_daily.json`; retain its rich Maa recognitions, delete any central Python delegation, and wire its count calculation only to `PlanJianlinChallenge`.

Navigate panel → daily, scroll at most 3, open Jianlin and select condensate. The only stamina purchase allowed is a same-frame verified `+80 体力` offer costing exactly `10 紫色魂玉`; require two known confirmations, budget one purchase, and explicitly Abort on any escalated second offer. Read stamina, per-run cost, visible max and safe multipliers; call `PlanJianlinChallenge`; set exact count/multiplier, challenge and battle in a max-12 loop. After each result close require stamina decrease/result evidence, then replan. Insufficient stamina before any applicable action is `not_eligible`; after completed battles it is a normal `success`; malformed OCR, resource mismatch, loop exhaustion or missing result Aborts.

- [ ] **Step 4: 运行批次自动化与剑林实机门**

```bash
uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/mfw/tasks/test_batch_b.py tests/test_mfw_jianlin_planner.py tests/test_mfw_safety.py -q
python3 tools/check_mfw_resources.py assets/resource/base
python3 tools/mfw_install.py --base-candidate install/mfw-foundation-candidate --output install/mfw-jianlin-resource-daily
python3 tools/mfw_profile.py run --install install/mfw-jianlin-resource-daily --profile-name live-JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY
```

Expected: all fixture states pass；live purple-soul purchase ≤1, purchase is exactly 10 for +80, cycles ≤12, total guarded stamina ≤120, second offer gets zero input. Write evidence JSON.

- [ ] **Step 5: 提交**

```bash
git add assets/tasks/日常/JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY.json assets/resource/base/pipeline/daily/jianlin_resource_condensate_stamina_daily.json assets/interface.mfw.json tests/mfw/tasks/test_batch_b.py tests/fixtures/JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY verification/mfw/JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY.json
git commit -m "feat: migrate guarded Jianlin task to MFW"
```

### Task 7: 执行 A+B 串行、重跑和资源审计

**Files:**
- Create after live run: `verification/mfw/batch-b-sequence.json`
- Modify: `tools/verify_mfw_evidence.py`
- Modify: `tests/test_mfw_evidence.py`

**Interfaces:**
- Consumes: 13 个已迁移任务 evidence 和当前完整版的 order-preserving subset。
- Produces: `verify_batch(root, batch="b")` 和允许进入批次 C 的实机门。

- [ ] **Step 1: 写同一 build、预算和重跑证据测试**

```python
def test_batch_b_requires_shared_build_and_resource_totals(tmp_path):
    write_valid_task_evidence_set(tmp_path, [*BATCH_A_IDS, *BATCH_B_IDS], build_sha="a" * 64)
    corrupt_build_sha(tmp_path / "SPEND_CONDENSATE_DAILY.json", "b" * 64)
    with pytest.raises(ValueError, match="same build"):
        verify_batch(tmp_path, batch="b")
```

- [ ] **Step 2: 运行测试确认先失败**

Run: `uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/test_mfw_evidence.py -q`

Expected: FAIL until batch-B budget/build checks are implemented.

- [ ] **Step 3: 实现资源证据审计**

Verify task order, each canonical ID once, exact resource names, amount totals ≤ policy, no purchase action on rerun, and every side-effect action has before/after image paths. Reject missing OCR value, missing build metadata SHA or textual `passed` without a run ID/log path.

- [ ] **Step 4: 用同一候选执行 A+B 串行两次**

```bash
python3 tools/mfw_install.py --base-candidate install/mfw-foundation-candidate --output install/mfw-batch-a-b-final
python3 tools/mfw_profile.py run --install install/mfw-batch-a-b-final --profile-name live-batch-a-b-sequence
python3 tools/verify_mfw_evidence.py --root verification/mfw --batch b
```

Expected: first and same-day rerun preserve task order, no duplicate IDs, no repeated purchase/eat/premium action, resource totals remain within caps, injected task Abort does not prevent next task.

- [ ] **Step 5: 提交真实批次证据**

```bash
git add tools/verify_mfw_evidence.py tests/test_mfw_evidence.py verification/mfw/batch-b-sequence.json
git commit -m "test: validate batch B resource safety and sequence"
```

## 批次 B 完成门

- [ ] 四个任务的资源名、识别数量、动作次数、共享预算和后置条件自动化全部通过。
- [ ] 四个任务均完成主页、业务页、正常不适用、危险状态、成功后同日重跑实机验收。
- [ ] 茶/凝晶/食物/剑林的副作用动作没有超时重放；未知价格和第二次体力购买均零输入。
- [ ] A+B 13 项在同一候选中串行两次，各 ID 每轮一次，第二轮不重复已完成副作用。
- [ ] 证据校验器确认所有 action trace、before/after 和 build metadata 一致后才进入批次 C。
