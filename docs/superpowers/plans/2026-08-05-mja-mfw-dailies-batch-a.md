# MJA MFW 日常任务批次 A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **2026-08-05 target correction (authoritative):** 批次 A 的实机目标是本机 macOS/iOS 游戏窗口，通过 `MacOS` Controller + `ScreenCaptureKit` + `GlobalEvent` 验收；不是 Android 模拟器。当前截图工具仍需补齐 macOS capture path，在此之前不得执行下面的 Android capture 命令，也不得把 Android fixture 冒充 macOS 证据。

**Goal:** 将 9 个免费、领取和非战斗日常迁移为可在 MFW 中单独选择、自判完成状态、安全重跑并串行执行的独立 Maa Pipeline。

**Architecture:** 每个 canonical task 拥有一个拆分任务声明和一个自包含 Pipeline，入口从业务页、主页、已知偏航或 `[JumpBack]MJA_GAME_START` 收敛。Python Agent 只执行 `BeginTask`、`GuardedInput` 和 `RecordTaskOutcome`，所有导航与完成判定保留在 Maa Pipeline。

**Tech Stack:** ProjectInterface v2、Maa Pipeline JSON、MaaFramework MacOS Controller、embedded Agent、pytest fixture contract、MFW `--direct-run`

## Global Constraints

- 开始本计划前，基座计划的 interface/resource/Agent 加载、Python 3.12 和失败传播契约必须全部通过；macOS 屏幕录制/辅助功能权限未具备时只能完成静态门禁，不能宣称实机通过。
- 任务迁移顺序固定为邮件、商城免费礼包、免费鉴宝、试剑、侠客派遣、采集、周一礼包、日常奖励、战令奖励。
- 每个任务只在 `assets/tasks/日常/{CANONICAL_ID}.json` 声明一次，入口为 `MJA_{CANONICAL_ID}_START`。
- 每个 Pipeline 必须支持主页、业务页、统一启动恢复、已完成、正常不适用、已知偏航、危险状态和显式 Abort。
- 每个副作用动作必须使用 `GuardedInput`，由当前帧页面与唯一目标授权，并在新截图中验证后置条件；`SHOP_FREE_GIFT_DAILY` 的奖励关闭动作 `dismiss_free_gift_reward` 也必须保留并受独立预算保护。
- `success`、`already_complete`、`not_eligible` 正常 StopTask；受支持失败记录 `failed` 后进入 `MJA_COMMON_ABORT`。
- 不使用 `daily_all`、`DailyWorkflowAction`、`MaaAndroidWorkflowDriver`、aggregate scheduler、`speedrun` 或外部 Controller。
- 每个任务自动化通过后还必须完成单项主页、业务页、同日重跑和串行实机验收；未运行不得记为 passed。
- 现有 `tests/fixtures/{TASK_ID}/{entry,actionable,completed,danger}.png` 是迁移证据源，不覆盖原图；新增状态使用新的 PNG 文件和 manifest case。
- 现有未跟踪 `uv.lock` 不修改、不暂存、不提交。

---

## 批次 A 文件边界

| Canonical ID | 任务声明 | Pipeline |
| --- | --- | --- |
| `MAIL_REWARD_DAILY` | `assets/tasks/日常/MAIL_REWARD_DAILY.json` | `assets/resource/base/pipeline/daily/mail_reward_daily.json` |
| `SHOP_FREE_GIFT_DAILY` | `assets/tasks/日常/SHOP_FREE_GIFT_DAILY.json` | `assets/resource/base/pipeline/daily/shop_free_gift_daily.json` |
| `FREE_APPRAISAL_DAILY` | `assets/tasks/日常/FREE_APPRAISAL_DAILY.json` | `assets/resource/base/pipeline/daily/free_appraisal_daily.json` |
| `TRIAL_SWORD_DAILY` | `assets/tasks/日常/TRIAL_SWORD_DAILY.json` | `assets/resource/base/pipeline/daily/trial_sword_daily.json` |
| `HERO_DISPATCH_DAILY` | `assets/tasks/日常/HERO_DISPATCH_DAILY.json` | `assets/resource/base/pipeline/daily/hero_dispatch_daily.json` |
| `COLLECTION_DEPLOYMENT_DAILY` | `assets/tasks/日常/COLLECTION_DEPLOYMENT_DAILY.json` | `assets/resource/base/pipeline/daily/collection_deployment_daily.json` |
| `WEEKLY_FREE_GIFT_MONDAY` | `assets/tasks/日常/WEEKLY_FREE_GIFT_MONDAY.json` | `assets/resource/base/pipeline/daily/weekly_free_gift_monday.json` |
| `DAILY_TASK_REWARD_CLAIM_DAILY` | `assets/tasks/日常/DAILY_TASK_REWARD_CLAIM_DAILY.json` | `assets/resource/base/pipeline/daily/daily_task_reward_claim_daily.json` |
| `BATTLE_PASS_REWARD_DAILY` | `assets/tasks/日常/BATTLE_PASS_REWARD_DAILY.json` | `assets/resource/base/pipeline/daily/battle_pass_reward_daily.json` |

For each row, preserve recognized postconditions/action caps from `agent/workflows/definitions/{lowercase canonical ID}.py` and the same-basename file in `assets/resource_android/pipeline/daily/`. `MAIL_REWARD_DAILY`, `SHOP_FREE_GIFT_DAILY`, `FREE_APPRAISAL_DAILY`, and `TRIAL_SWORD_DAILY` also consume shared definitions in `agent/workflows/definitions/batch1.py`; `HERO_DISPATCH_DAILY` and `COLLECTION_DEPLOYMENT_DAILY` also consume `agent/workflows/definitions/batch23.py`. These are evidence sources only: do not copy Python navigation or `DailyWorkflowAction` into the target.

Before each task's live/test gate, manually place the emulator on the recognized feature-locked/not-open state and run the task's first command below; then manually place it on a supported off-route page and run the second. The capture tool is screenshot-only, refuses overwrites, and the manifest must add `not_eligible` and `known_drift` cases with their exact expected terminal/recovery node.

```bash
python3 -m tools.capture_mfw_fixture --task-id MAIL_REWARD_DAILY --case not_eligible
python3 -m tools.capture_mfw_fixture --task-id MAIL_REWARD_DAILY --case known_drift
python3 -m tools.capture_mfw_fixture --task-id SHOP_FREE_GIFT_DAILY --case not_eligible
python3 -m tools.capture_mfw_fixture --task-id SHOP_FREE_GIFT_DAILY --case known_drift
python3 -m tools.capture_mfw_fixture --task-id FREE_APPRAISAL_DAILY --case not_eligible
python3 -m tools.capture_mfw_fixture --task-id FREE_APPRAISAL_DAILY --case known_drift
python3 -m tools.capture_mfw_fixture --task-id TRIAL_SWORD_DAILY --case not_eligible
python3 -m tools.capture_mfw_fixture --task-id TRIAL_SWORD_DAILY --case known_drift
python3 -m tools.capture_mfw_fixture --task-id HERO_DISPATCH_DAILY --case not_eligible
python3 -m tools.capture_mfw_fixture --task-id HERO_DISPATCH_DAILY --case known_drift
python3 -m tools.capture_mfw_fixture --task-id COLLECTION_DEPLOYMENT_DAILY --case not_eligible
python3 -m tools.capture_mfw_fixture --task-id COLLECTION_DEPLOYMENT_DAILY --case known_drift
python3 -m tools.capture_mfw_fixture --task-id WEEKLY_FREE_GIFT_MONDAY --case not_eligible
python3 -m tools.capture_mfw_fixture --task-id WEEKLY_FREE_GIFT_MONDAY --case known_drift
python3 -m tools.capture_mfw_fixture --task-id DAILY_TASK_REWARD_CLAIM_DAILY --case not_eligible
python3 -m tools.capture_mfw_fixture --task-id DAILY_TASK_REWARD_CLAIM_DAILY --case known_drift
python3 -m tools.capture_mfw_fixture --task-id BATTLE_PASS_REWARD_DAILY --case not_eligible
python3 -m tools.capture_mfw_fixture --task-id BATTLE_PASS_REWARD_DAILY --case known_drift
```

Each live-gate command block is an ordered operator checklist. Run its concrete `mfw_install.py` line first, then pause, open the newly named output once, create and save the exact profile name shown with only the required task(s), close MFW, and only then run the following `mfw_profile.py` line. Never open or mutate `install/mfw-foundation-candidate`; it is the immutable release/runtime base.

### Task 1: 建立单任务 Pipeline 契约与批次预设断言

**Files:**
- Create: `tests/mfw/task_contract.py`
- Create: `tests/mfw/tasks/__init__.py`
- Create: `tests/mfw/test_task_contract_helpers.py`
- Create: `tests/mfw/tasks/test_batch_a.py`
- Create: `tests/test_mfw_presets.py`

**Interfaces:**
- Consumes: `tests/mfw/pipeline_assertions.py`、`assets/interface.mfw.json`、fixture manifest schema v1。
- Produces: `TaskContract`；`assert_task_contract(contract)`；`assert_fixture_matrix(task_id, cases)`；`load_interface_tasks()`。

- [ ] **Step 1: 写会因任务未迁移而失败的批次测试**

```python
from tests.mfw.task_contract import TaskContract, assert_task_contract


BATCH_A = [
    TaskContract("MAIL_REWARD_DAILY", "mail_reward_daily.json"),
    TaskContract("SHOP_FREE_GIFT_DAILY", "shop_free_gift_daily.json"),
    TaskContract("FREE_APPRAISAL_DAILY", "free_appraisal_daily.json"),
    TaskContract("TRIAL_SWORD_DAILY", "trial_sword_daily.json"),
    TaskContract("HERO_DISPATCH_DAILY", "hero_dispatch_daily.json"),
    TaskContract("COLLECTION_DEPLOYMENT_DAILY", "collection_deployment_daily.json"),
    TaskContract("WEEKLY_FREE_GIFT_MONDAY", "weekly_free_gift_monday.json", group="周常"),
    TaskContract("DAILY_TASK_REWARD_CLAIM_DAILY", "daily_task_reward_claim_daily.json"),
    TaskContract("BATTLE_PASS_REWARD_DAILY", "battle_pass_reward_daily.json"),
]


def test_batch_a_contracts():
    for contract in BATCH_A:
        assert_task_contract(contract)
        assert_fixture_matrix(
            contract.task_id,
            required={"entry", "actionable", "completed", "not_eligible", "known_drift", "danger"},
        )
```

`assert_task_contract` must assert: task declaration exists once with `name` equal to `contract.task_id`, `label` non-empty, `default_check=true`, `group=[contract.group]`, and entry equal to `contract.entry`; Pipeline exists; entry can reach business-page probe, home navigation, `MJA_GAME_START`, all three normal outcomes and `MJA_COMMON_ABORT`; all references exist; cycles are bounded; every click/swipe uses `GuardedInput`; forbidden control-plane strings are absent.

- [ ] **Step 2: 运行测试确认先失败**

Run: `uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/mfw/tasks/test_batch_a.py tests/test_mfw_presets.py -q`

Expected: FAIL，9 个新任务文件尚不存在。

- [ ] **Step 3: 实现契约辅助器和增量预设断言**

```python
@dataclass(frozen=True)
class TaskContract:
    task_id: str
    pipeline_file: str
    group: str = "日常"

    @property
    def entry(self) -> str:
        return f"MJA_{self.task_id}_START"


def assert_task_contract(contract: TaskContract) -> None:
    declaration = load_task_declaration(contract.task_id)
    assert declaration["entry"] == contract.entry
    assert declaration["group"] == [contract.group]
    nodes = load_pipeline_file(contract.pipeline_file)
    assert contract.entry in nodes
    assert_reachable(nodes, contract.entry, "MJA_GAME_START")
    assert_reachable(nodes, contract.entry, "MJA_COMMON_ABORT")
    assert_all_inputs_guarded(nodes)
    assert_all_cycles_bounded(nodes)
```

`tests/test_mfw_presets.py` defines these exact orders, then asserts the currently imported canonical IDs are unique and are an order-preserving subset. After Task 10, it additionally asserts the simplified preset exactly equals startup plus all 9 batch-A IDs.

```python
FINAL_CANONICAL_IDS = [
    "MAIL_REWARD_DAILY",
    "SHOP_FREE_GIFT_DAILY",
    "BUY_TEA_DAILY",
    "FREE_APPRAISAL_DAILY",
    "TRIAL_SWORD_DAILY",
    "HERO_DISPATCH_DAILY",
    "COLLECTION_DEPLOYMENT_DAILY",
    "WEEKLY_FREE_GIFT_MONDAY",
    "SHADOW_RUINS_DAILY",
    "SPEND_CONDENSATE_DAILY",
    "MARTIAL_STUDY_BREAKTHROUGH_DAILY",
    "EAT_STAMINA_FOOD_DAILY",
    "DUNGEON_SWEEP_DAILY",
    "JIANLIN_RESOURCE_CONDENSATE_STAMINA_DAILY",
    "RING_CHALLENGE_DAILY",
    "DAILY_TASK_REWARD_CLAIM_DAILY",
    "BATTLE_PASS_REWARD_DAILY",
]
SIMPLIFIED_CANONICAL_IDS = [
    "MAIL_REWARD_DAILY",
    "SHOP_FREE_GIFT_DAILY",
    "FREE_APPRAISAL_DAILY",
    "TRIAL_SWORD_DAILY",
    "HERO_DISPATCH_DAILY",
    "COLLECTION_DEPLOYMENT_DAILY",
    "WEEKLY_FREE_GIFT_MONDAY",
    "DAILY_TASK_REWARD_CLAIM_DAILY",
    "BATTLE_PASS_REWARD_DAILY",
]
SIMPLIFIED_IDS = ["GAME_START", *SIMPLIFIED_CANONICAL_IDS]
FULL_IDS = ["GAME_START", *FINAL_CANONICAL_IDS]
```

- [ ] **Step 4: 运行辅助器自身测试**

Run: `uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/mfw/test_task_contract_helpers.py -q`

Expected: PASS after creating `tests/mfw/test_task_contract_helpers.py` with malformed fixture cases for duplicate task, raw click, missing target, unbounded cycle and absent Abort.

- [ ] **Step 5: 提交**

```bash
git add tests/mfw tests/mfw/tasks tests/test_mfw_presets.py
git commit -m "test: define independent MFW daily task contracts"
```

### Task 2: 迁移 MAIL_REWARD_DAILY

**Files:**
- Create: `assets/tasks/日常/MAIL_REWARD_DAILY.json`
- Create: `assets/resource/base/pipeline/daily/mail_reward_daily.json`
- Modify: `assets/interface.mfw.json`
- Modify: `tests/mfw/tasks/test_batch_a.py`
- Modify: `tests/fixtures/MAIL_REWARD_DAILY/manifest.json`
- Create from captured state: `tests/fixtures/MAIL_REWARD_DAILY/not_eligible.png`
- Create from captured state: `tests/fixtures/MAIL_REWARD_DAILY/known_drift.png`
- Create after live run: `verification/mfw/MAIL_REWARD_DAILY.json`

**Interfaces:**
- Consumes: `MJA_GAME_START`, `MJA_COMMON_STOP`, `MJA_COMMON_ABORT`, `BeginTask`, `GuardedInput`, `RecordTaskOutcome`。
- Produces: entry `MJA_MAIL_REWARD_DAILY_START`; exact frozen action IDs `open_function_panel`, `open_mail`, `claim_all_mail`, `close_reward_popup`, `close_mail`, `close_function_panel`。

- [ ] **Step 1: 写邮件流程失败测试**

```python
def test_mail_flow_and_terminals():
    nodes = task_nodes("MAIL_REWARD_DAILY")
    assert_path(nodes, "MJA_MAIL_REWARD_DAILY_START", ["MJA_MAIL_PAGE", "MJA_MAIL_EMPTY"])
    assert_outcome(nodes, "MJA_MAIL_EMPTY", "already_complete", "mail.empty")
    assert_guarded_actions(nodes, ["open_function_panel", "open_mail", "claim_all_mail", "close_reward_popup", "close_mail", "close_function_panel"])
    assert_outcome(nodes, "MJA_MAIL_CLAIM_VERIFIED", "success", "mail.empty")
```

- [ ] **Step 2: 运行邮件测试确认先失败**

Run: `uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/mfw/tasks/test_batch_a.py -k mail -q`

Expected: FAIL because `MAIL_REWARD_DAILY` task/Pipeline are absent.

- [ ] **Step 3: 实现邮件 Pipeline**

```json
{"task":[{"name":"MAIL_REWARD_DAILY","label":"领取邮件奖励","default_check":true,"group":["日常"],"entry":"MJA_MAIL_REWARD_DAILY_START"}]}
```

Start the target from `assets/resource_android/pipeline/daily/mail_reward_daily.json`, then remove every `DailyWorkflowAction`/central-driver node and apply the flow below in `assets/resource/base/pipeline/daily/mail_reward_daily.json`.

Declare label `领取邮件奖励`, group `日常`, entry `MJA_MAIL_REWARD_DAILY_START`. Probe mail page first, then home → function panel → mail, otherwise JumpBack startup. On `mail.empty`, record `already_complete`; on claimable unique `mail.claim_all`, invoke `claim_all_mail` once, close bounded reward popup through `close_reward_popup`, require fresh `mail.empty`, then record `success`; unknown popup, ambiguous claim target or missing postcondition records `failed`/`MAIL_POSTCONDITION_MISSING` and Aborts. Close mail/panel only after terminal evidence and never replay `claim_all_mail` on timeout.

- [ ] **Step 4: 运行 fixture、资源和真实单项门**

```bash
uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/mfw/tasks/test_batch_a.py -k mail -q
python3 tools/check_mfw_resources.py assets/resource/base
python3 tools/mfw_install.py --base-candidate install/mfw-foundation-candidate --output install/mfw-mail-reward-daily
python3 tools/mfw_profile.py run --install install/mfw-mail-reward-daily --profile-name live-MAIL_REWARD_DAILY
```

Expected: entry/actionable/completed/danger fixture pass；实机从主页、邮件页、完成后重跑分别得到 success/success/already_complete，输入次数不超政策。真实 run-id、build SHA、日志和证据路径写入 `verification/mfw/MAIL_REWARD_DAILY.json`。

- [ ] **Step 5: 提交**

```bash
git add assets/tasks/日常/MAIL_REWARD_DAILY.json assets/resource/base/pipeline/daily/mail_reward_daily.json assets/interface.mfw.json tests/mfw/tasks/test_batch_a.py tests/fixtures/MAIL_REWARD_DAILY verification/mfw/MAIL_REWARD_DAILY.json
git commit -m "feat: migrate mail reward to independent MFW task"
```

### Task 3: 迁移 SHOP_FREE_GIFT_DAILY

**Files:**
- Create: `assets/tasks/日常/SHOP_FREE_GIFT_DAILY.json`
- Create: `assets/resource/base/pipeline/daily/shop_free_gift_daily.json`
- Modify: `assets/interface.mfw.json`
- Modify: `tests/mfw/tasks/test_batch_a.py`
- Modify: `tests/fixtures/SHOP_FREE_GIFT_DAILY/manifest.json`
- Create from captured state: `tests/fixtures/SHOP_FREE_GIFT_DAILY/not_eligible.png`
- Create from captured state: `tests/fixtures/SHOP_FREE_GIFT_DAILY/known_drift.png`
- Create after live run: `verification/mfw/SHOP_FREE_GIFT_DAILY.json`

**Interfaces:**
- Consumes: 公共启动/终点和窄 Agent actions。
- Produces: `MJA_SHOP_FREE_GIFT_DAILY_START`; exact frozen action IDs `open_function_panel`, `open_shop`, `open_period_benefits`, `claim_free_gift`, `dismiss_free_gift_reward`, `close_shop`。

- [ ] **Step 1: 写免费礼包安全测试**

```python
def test_shop_gift_requires_free_text_and_claimed_postcondition():
    nodes = task_nodes("SHOP_FREE_GIFT_DAILY")
    assert_ocr_guard(nodes, "MJA_SHOP_FREE_CLAIM", required_text="免费")
    assert_guarded_actions(nodes, ["open_function_panel", "open_shop", "open_period_benefits", "claim_free_gift", "dismiss_free_gift_reward", "close_shop"])
    assert_outcome(nodes, "MJA_SHOP_FREE_ALREADY_CLAIMED", "already_complete", "shop.free_gift.claimed")
    assert_abort_code(nodes, "MJA_SHOP_PRICE_UNSAFE", "SHOP_NONFREE_OR_UNKNOWN_PRICE")
```

- [ ] **Step 2: 运行测试确认先失败**

Run: `uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/mfw/tasks/test_batch_a.py -k shop_free -q`

Expected: FAIL because task/Pipeline are absent.

- [ ] **Step 3: 实现商城免费礼包 Pipeline**

```json
{"task":[{"name":"SHOP_FREE_GIFT_DAILY","label":"商城免费礼包","default_check":true,"group":["日常"],"entry":"MJA_SHOP_FREE_GIFT_DAILY_START"}]}
```

Start the target from `assets/resource_android/pipeline/daily/shop_free_gift_daily.json`, remove its delegate nodes, and implement the following Maa-only flow.

Navigate panel → shop → period benefits. A claim is authorized only when the same frame uniquely recognizes the gift card, claim control and OCR `免费`; any currency icon, numeric price, duplicate target or OCR conflict Aborts before input. Claimed/sold-out visual is `already_complete`; after one claim dismiss the reward and require claimed visual for `success`; bounded close returns to a known page.

- [ ] **Step 4: 运行 fixture、资源和真实单项门**

```bash
uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/mfw/tasks/test_batch_a.py -k shop_free -q
python3 tools/check_mfw_resources.py assets/resource/base
python3 tools/mfw_install.py --base-candidate install/mfw-foundation-candidate --output install/mfw-shop-free-gift-daily
python3 tools/mfw_profile.py run --install install/mfw-shop-free-gift-daily --profile-name live-SHOP_FREE_GIFT_DAILY
```

Expected: four existing fixtures plus explicit non-free OCR test pass；live主页/商城页/重跑 pass，免费领取最多一次。记录 `verification/mfw/SHOP_FREE_GIFT_DAILY.json`。

- [ ] **Step 5: 提交**

```bash
git add assets/tasks/日常/SHOP_FREE_GIFT_DAILY.json assets/resource/base/pipeline/daily/shop_free_gift_daily.json assets/interface.mfw.json tests/mfw/tasks/test_batch_a.py tests/fixtures/SHOP_FREE_GIFT_DAILY verification/mfw/SHOP_FREE_GIFT_DAILY.json
git commit -m "feat: migrate free shop gift to independent MFW task"
```

### Task 4: 迁移 FREE_APPRAISAL_DAILY

**Files:**
- Create: `assets/tasks/日常/FREE_APPRAISAL_DAILY.json`
- Create: `assets/resource/base/pipeline/daily/free_appraisal_daily.json`
- Modify: `assets/interface.mfw.json`
- Modify: `tests/mfw/tasks/test_batch_a.py`
- Modify: `tests/fixtures/FREE_APPRAISAL_DAILY/manifest.json`
- Create from captured state: `tests/fixtures/FREE_APPRAISAL_DAILY/not_eligible.png`
- Create from captured state: `tests/fixtures/FREE_APPRAISAL_DAILY/known_drift.png`
- Create after live run: `verification/mfw/FREE_APPRAISAL_DAILY.json`

**Interfaces:**
- Consumes: 公共启动/终点和窄 Agent actions。
- Produces: `MJA_FREE_APPRAISAL_DAILY_START`; exact frozen action IDs `open_appraisal`, `claim_free_appraisal_once`, `close_appraisal_popup`。

- [ ] **Step 1: 写免费鉴宝一次性测试**

```python
def test_appraisal_only_uses_verified_free_once():
    nodes = task_nodes("FREE_APPRAISAL_DAILY")
    assert_ocr_guard(nodes, "MJA_APPRAISAL_FREE_ONCE", required_text="免费")
    assert_action_limit("FREE_APPRAISAL_DAILY", "claim_free_appraisal_once", 1)
    assert_outcome(nodes, "MJA_APPRAISAL_USED", "already_complete", "appraisal.used")
    assert_outcome(nodes, "MJA_APPRAISAL_RESULT_VERIFIED", "success", "appraisal.used")
```

- [ ] **Step 2: 运行测试确认先失败**

Run: `uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/mfw/tasks/test_batch_a.py -k appraisal -q`

Expected: FAIL because task/Pipeline are absent.

- [ ] **Step 3: 实现免费鉴宝 Pipeline**

```json
{"task":[{"name":"FREE_APPRAISAL_DAILY","label":"免费鉴宝","default_check":true,"group":["日常"],"entry":"MJA_FREE_APPRAISAL_DAILY_START"}]}
```

Start the target from `assets/resource_android/pipeline/daily/free_appraisal_daily.json`, remove its delegate nodes, and implement the following Maa-only flow.

Probe appraisal page, otherwise navigate from home or startup. Recognized `appraisal.used` records `already_complete`. Only unique `免费` once control may invoke `claim_free_appraisal_once`; paid ten-pull, currency confirmation, unknown result or second request Aborts. Close at most one result through `close_appraisal_popup` and require used visual on a fresh frame before `success`.

- [ ] **Step 4: 运行 fixture、资源和真实单项门**

```bash
uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/mfw/tasks/test_batch_a.py -k appraisal -q
python3 tools/check_mfw_resources.py assets/resource/base
python3 tools/mfw_install.py --base-candidate install/mfw-foundation-candidate --output install/mfw-free-appraisal-daily
python3 tools/mfw_profile.py run --install install/mfw-free-appraisal-daily --profile-name live-FREE_APPRAISAL_DAILY
```

Expected: fixtures pass；live action count exactly 0 or 1，重跑为 already_complete。记录 `verification/mfw/FREE_APPRAISAL_DAILY.json`。

- [ ] **Step 5: 提交**

```bash
git add assets/tasks/日常/FREE_APPRAISAL_DAILY.json assets/resource/base/pipeline/daily/free_appraisal_daily.json assets/interface.mfw.json tests/mfw/tasks/test_batch_a.py tests/fixtures/FREE_APPRAISAL_DAILY verification/mfw/FREE_APPRAISAL_DAILY.json
git commit -m "feat: migrate free appraisal to independent MFW task"
```

### Task 5: 迁移 TRIAL_SWORD_DAILY

**Files:**
- Create: `assets/tasks/日常/TRIAL_SWORD_DAILY.json`
- Create: `assets/resource/base/pipeline/daily/trial_sword_daily.json`
- Modify: `assets/interface.mfw.json`
- Modify: `tests/mfw/tasks/test_batch_a.py`
- Modify: `tests/fixtures/TRIAL_SWORD_DAILY/manifest.json`
- Create from captured state: `tests/fixtures/TRIAL_SWORD_DAILY/not_eligible.png`
- Create from captured state: `tests/fixtures/TRIAL_SWORD_DAILY/known_drift.png`
- Create after live run: `verification/mfw/TRIAL_SWORD_DAILY.json`

**Interfaces:**
- Consumes: 公共启动/终点和窄 Agent actions。
- Produces: `MJA_TRIAL_SWORD_DAILY_START`; exact frozen action IDs `open_trial_sword`, `claim_trial_sword_reward`, `close_reward_popup`, `claim_free_trial`, `confirm_free_trial`, `close_trial`。

- [ ] **Step 1: 写普通奖励和免费领取顺序测试**

```python
def test_trial_claims_ordinary_reward_before_one_free_claim():
    nodes = task_nodes("TRIAL_SWORD_DAILY")
    assert_ordered_actions(nodes, ["claim_trial_sword_reward", "close_reward_popup", "claim_free_trial", "confirm_free_trial", "close_reward_popup"])
    assert_ocr_guard(nodes, "MJA_TRIAL_FREE_CLAIM", required_text="免费")
    assert_action_limit("TRIAL_SWORD_DAILY", "claim_free_trial", 1)
    assert_outcome(nodes, "MJA_TRIAL_FREE_USED", "already_complete", "trial.free_used")
```

- [ ] **Step 2: 运行测试确认先失败**

Run: `uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/mfw/tasks/test_batch_a.py -k trial -q`

Expected: FAIL because task/Pipeline are absent.

- [ ] **Step 3: 实现试剑 Pipeline**

```json
{"task":[{"name":"TRIAL_SWORD_DAILY","label":"试剑免费领取","default_check":true,"group":["日常"],"entry":"MJA_TRIAL_SWORD_DAILY_START"}]}
```

Start the target from `assets/resource_android/pipeline/daily/trial_sword_daily.json`, remove its delegate nodes, and implement the following Maa-only flow.

Enter trial from home/startup. If free-used evidence exists, record `already_complete`. Claim an ordinary ready reward at most once, close its popup, then authorize the free claim only with same-frame `免费`; confirm only when the dialog still identifies the free trial. Paid/unknown confirmation Aborts. After result close, require free-used evidence before `success`.

- [ ] **Step 4: 运行 fixture、资源和真实单项门**

```bash
uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/mfw/tasks/test_batch_a.py -k trial -q
python3 tools/check_mfw_resources.py assets/resource/base
python3 tools/mfw_install.py --base-candidate install/mfw-foundation-candidate --output install/mfw-trial-sword-daily
python3 tools/mfw_profile.py run --install install/mfw-trial-sword-daily --profile-name live-TRIAL_SWORD_DAILY
```

Expected: fixture and live states pass，免费领取至多一次，重跑无副作用。记录 `verification/mfw/TRIAL_SWORD_DAILY.json`。

- [ ] **Step 5: 提交**

```bash
git add assets/tasks/日常/TRIAL_SWORD_DAILY.json assets/resource/base/pipeline/daily/trial_sword_daily.json assets/interface.mfw.json tests/mfw/tasks/test_batch_a.py tests/fixtures/TRIAL_SWORD_DAILY verification/mfw/TRIAL_SWORD_DAILY.json
git commit -m "feat: migrate trial sword to independent MFW task"
```

### Task 6: 迁移 HERO_DISPATCH_DAILY

**Files:**
- Create: `assets/tasks/日常/HERO_DISPATCH_DAILY.json`
- Create: `assets/resource/base/pipeline/daily/hero_dispatch_daily.json`
- Modify: `assets/interface.mfw.json`
- Modify: `tests/mfw/tasks/test_batch_a.py`
- Modify: `tests/fixtures/HERO_DISPATCH_DAILY/manifest.json`
- Create from captured state: `tests/fixtures/HERO_DISPATCH_DAILY/not_eligible.png`
- Create from captured state: `tests/fixtures/HERO_DISPATCH_DAILY/known_drift.png`
- Create after live run: `verification/mfw/HERO_DISPATCH_DAILY.json`

**Interfaces:**
- Consumes: 公共启动/终点和现有 dispatch templates。
- Produces: `MJA_HERO_DISPATCH_DAILY_START`; exact frozen action IDs `open_painting_scroll`, `open_hero_dispatch`, `claim_first_dispatch`, `select_first_visible_dispatch`, `smart_configure_team`, `dispatch_team`, `close_hero_dispatch`, `close_hero_dispatch_painting`。

- [ ] **Step 1: 写派遣有界循环测试**

```python
def test_dispatch_claims_then_fills_at_most_six_slots():
    nodes = task_nodes("HERO_DISPATCH_DAILY")
    assert_loop_bound(nodes, "MJA_DISPATCH_CLAIM_LOOP", maximum=6)
    assert_loop_bound(nodes, "MJA_DISPATCH_FILL_LOOP", maximum=6)
    assert_ordered_actions(nodes, ["claim_first_dispatch", "select_first_visible_dispatch", "smart_configure_team", "dispatch_team"])
    assert_outcome(nodes, "MJA_DISPATCH_ALL_RUNNING", "success", "dispatch.all_completed_or_in_progress")
    assert_outcome(nodes, "MJA_DISPATCH_ALREADY_RUNNING", "already_complete", "dispatch.all_completed_or_in_progress")
```

- [ ] **Step 2: 运行测试确认先失败**

Run: `uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/mfw/tasks/test_batch_a.py -k dispatch -q`

Expected: FAIL because task/Pipeline are absent.

- [ ] **Step 3: 实现侠客派遣 Pipeline**

```json
{"task":[{"name":"HERO_DISPATCH_DAILY","label":"侠客派遣","default_check":true,"group":["日常"],"entry":"MJA_HERO_DISPATCH_DAILY_START"}]}
```

Start the target from `assets/resource_android/pipeline/daily/hero_dispatch_daily.json`, remove any central-driver delegate, and implement the following bounded Maa-only loops.

Navigate home → painting → dispatch. First claim each uniquely claimable completed row in a max-6 loop. Then configure and start each empty eligible row in a separate max-6 loop; every start requires a fresh empty-row recognition and selected-hero postcondition. If all visible/known rows are completed or in progress before action, return `already_complete`; after mutations return `success` only when no claimable/empty eligible row remains. Ambiguous row identity, team conflict or loop exhaustion Aborts.

- [ ] **Step 4: 运行 fixture、资源和真实单项门**

```bash
uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/mfw/tasks/test_batch_a.py -k dispatch -q
python3 tools/check_mfw_resources.py assets/resource/base
python3 tools/mfw_install.py --base-candidate install/mfw-foundation-candidate --output install/mfw-hero-dispatch-daily
python3 tools/mfw_profile.py run --install install/mfw-hero-dispatch-daily --profile-name live-HERO_DISPATCH_DAILY
```

Expected: fixture pass；live claim/fill total each ≤6，完成后重跑为 already_complete。记录 `verification/mfw/HERO_DISPATCH_DAILY.json`。

- [ ] **Step 5: 提交**

```bash
git add assets/tasks/日常/HERO_DISPATCH_DAILY.json assets/resource/base/pipeline/daily/hero_dispatch_daily.json assets/interface.mfw.json tests/mfw/tasks/test_batch_a.py tests/fixtures/HERO_DISPATCH_DAILY verification/mfw/HERO_DISPATCH_DAILY.json
git commit -m "feat: migrate hero dispatch to independent MFW task"
```

### Task 7: 迁移 COLLECTION_DEPLOYMENT_DAILY

**Files:**
- Create: `assets/tasks/日常/COLLECTION_DEPLOYMENT_DAILY.json`
- Create: `assets/resource/base/pipeline/daily/collection_deployment_daily.json`
- Modify: `assets/interface.mfw.json`
- Modify: `tests/mfw/tasks/test_batch_a.py`
- Modify: `tests/fixtures/COLLECTION_DEPLOYMENT_DAILY/manifest.json`
- Create from captured state: `tests/fixtures/COLLECTION_DEPLOYMENT_DAILY/not_eligible.png`
- Create from captured state: `tests/fixtures/COLLECTION_DEPLOYMENT_DAILY/known_drift.png`
- Create after live run: `verification/mfw/COLLECTION_DEPLOYMENT_DAILY.json`

**Interfaces:**
- Consumes: 公共启动/终点和 painting/Yanwu/collection templates。
- Produces: `MJA_COLLECTION_DEPLOYMENT_DAILY_START`; exact frozen action IDs `open_painting_scroll`, `select_yanwu_world`, `open_collection_deployment`, `claim_all_collection`, `close_reward_popup`, `close_collection_deployment`。

- [ ] **Step 1: 写采集收取后置条件测试**

```python
def test_collection_harvests_once_and_requires_empty_state():
    nodes = task_nodes("COLLECTION_DEPLOYMENT_DAILY")
    assert_action_limit("COLLECTION_DEPLOYMENT_DAILY", "claim_all_collection", 1)
    assert_guarded_actions(nodes, ["open_painting_scroll", "select_yanwu_world", "open_collection_deployment", "claim_all_collection", "close_reward_popup", "close_collection_deployment"])
    assert_outcome(nodes, "MJA_COLLECTION_ALREADY_HARVESTED", "already_complete", "collection.harvested")
    assert_outcome(nodes, "MJA_COLLECTION_HARVEST_VERIFIED", "success", "collection.harvested")
```

- [ ] **Step 2: 运行测试确认先失败**

Run: `uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/mfw/tasks/test_batch_a.py -k collection -q`

Expected: FAIL because task/Pipeline are absent.

- [ ] **Step 3: 实现采集 Pipeline**

```json
{"task":[{"name":"COLLECTION_DEPLOYMENT_DAILY","label":"采集收取","default_check":true,"group":["日常"],"entry":"MJA_COLLECTION_DEPLOYMENT_DAILY_START"}]}
```

Start the target from `assets/resource_android/pipeline/daily/collection_deployment_daily.json`, remove any central-driver delegate, and implement the following Maa-only flow.

Navigate painting → 演武 → collection. Existing harvested/empty state returns `already_complete`. A unique harvest-all control may be clicked once; close reward popups with a fixed maximum, then require harvested/empty fresh frame before `success`. Missing collection entry is `not_eligible` only when the recognized feature-lock state is present; unknown layout or missing postcondition Aborts.

- [ ] **Step 4: 运行 fixture、资源和真实单项门**

```bash
uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/mfw/tasks/test_batch_a.py -k collection -q
python3 tools/check_mfw_resources.py assets/resource/base
python3 tools/mfw_install.py --base-candidate install/mfw-foundation-candidate --output install/mfw-collection-deployment-daily
python3 tools/mfw_profile.py run --install install/mfw-collection-deployment-daily --profile-name live-COLLECTION_DEPLOYMENT_DAILY
```

Expected: fixture pass；live harvest ≤1，重跑 already_complete，feature-lock fixture returns not_eligible。记录 evidence。

- [ ] **Step 5: 提交**

```bash
git add assets/tasks/日常/COLLECTION_DEPLOYMENT_DAILY.json assets/resource/base/pipeline/daily/collection_deployment_daily.json assets/interface.mfw.json tests/mfw/tasks/test_batch_a.py tests/fixtures/COLLECTION_DEPLOYMENT_DAILY verification/mfw/COLLECTION_DEPLOYMENT_DAILY.json
git commit -m "feat: migrate collection deployment to independent MFW task"
```

### Task 8: 迁移 WEEKLY_FREE_GIFT_MONDAY

**Files:**
- Create: `assets/tasks/日常/WEEKLY_FREE_GIFT_MONDAY.json`
- Create: `assets/resource/base/pipeline/daily/weekly_free_gift_monday.json`
- Modify: `assets/interface.mfw.json`
- Modify: `tests/mfw/tasks/test_batch_a.py`
- Modify: `tests/fixtures/WEEKLY_FREE_GIFT_MONDAY/manifest.json`
- Create from captured state: `tests/fixtures/WEEKLY_FREE_GIFT_MONDAY/not_eligible.png`
- Create from captured state: `tests/fixtures/WEEKLY_FREE_GIFT_MONDAY/known_drift.png`
- Create after live run: `verification/mfw/WEEKLY_FREE_GIFT_MONDAY.json`

**Interfaces:**
- Consumes: 公共启动/终点和 shop weekly templates。
- Produces: `MJA_WEEKLY_FREE_GIFT_MONDAY_START`; exact frozen action IDs `open_function_panel`, `open_shop`, `open_gift_tab`, `open_weekly_must_buy`, `claim_weekly_lucky_bag`, `dismiss_weekly_reward`, `close_shop`。

- [ ] **Step 1: 写免费/付费分流测试**

```python
def test_weekly_gift_only_claims_free_and_treats_paid_as_not_eligible():
    nodes = task_nodes("WEEKLY_FREE_GIFT_MONDAY")
    assert_ocr_guard(nodes, "MJA_WEEKLY_FREE_CLAIM", required_text="免费")
    assert_outcome(nodes, "MJA_WEEKLY_CLAIMED", "already_complete", "weekly_gift.claimed")
    assert_outcome(nodes, "MJA_WEEKLY_PAID_ONLY", "not_eligible", "weekly_gift.no_free_offer")
    assert_abort_code(nodes, "MJA_WEEKLY_UNKNOWN_PRICE", "WEEKLY_PRICE_UNVERIFIED")
```

- [ ] **Step 2: 运行测试确认先失败**

Run: `uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/mfw/tasks/test_batch_a.py -k weekly -q`

Expected: FAIL because task/Pipeline are absent.

- [ ] **Step 3: 实现周一礼包 Pipeline**

```json
{"task":[{"name":"WEEKLY_FREE_GIFT_MONDAY","label":"周一免费礼包","default_check":true,"group":["周常"],"entry":"MJA_WEEKLY_FREE_GIFT_MONDAY_START"}]}
```

Start the target from `assets/resource_android/pipeline/daily/weekly_free_gift_monday.json`, remove its delegate nodes, and implement the following Maa-only price/state partition.

Navigate panel → shop → gift tab → weekly. Do not use host weekday as the sole gate: page state decides. Claimed visual returns `already_complete`; a recognized paid-only/no-free offer returns `not_eligible`; unique OCR `免费` authorizes one claim and fresh claimed visual yields `success`; conflicting OCR/currency or unknown layout Aborts. This allows the full preset to include the task every day safely.

- [ ] **Step 4: 运行 fixture、资源和真实单项门**

```bash
uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/mfw/tasks/test_batch_a.py -k weekly -q
python3 tools/check_mfw_resources.py assets/resource/base
python3 tools/mfw_install.py --base-candidate install/mfw-foundation-candidate --output install/mfw-weekly-free-gift-monday
python3 tools/mfw_profile.py run --install install/mfw-weekly-free-gift-monday --profile-name live-WEEKLY_FREE_GIFT_MONDAY
```

Expected: free, claimed, paid-only and danger states produce exact outcomes；live non-Monday run makes zero purchase。记录 evidence。

- [ ] **Step 5: 提交**

```bash
git add assets/tasks/日常/WEEKLY_FREE_GIFT_MONDAY.json assets/resource/base/pipeline/daily/weekly_free_gift_monday.json assets/interface.mfw.json tests/mfw/tasks/test_batch_a.py tests/fixtures/WEEKLY_FREE_GIFT_MONDAY verification/mfw/WEEKLY_FREE_GIFT_MONDAY.json
git commit -m "feat: migrate weekly free gift to independent MFW task"
```

### Task 9: 迁移 DAILY_TASK_REWARD_CLAIM_DAILY

**Files:**
- Create: `assets/tasks/日常/DAILY_TASK_REWARD_CLAIM_DAILY.json`
- Create: `assets/resource/base/pipeline/daily/daily_task_reward_claim_daily.json`
- Modify: `assets/interface.mfw.json`
- Modify: `tests/mfw/tasks/test_batch_a.py`
- Modify: `tests/fixtures/DAILY_TASK_REWARD_CLAIM_DAILY/manifest.json`
- Create from captured state: `tests/fixtures/DAILY_TASK_REWARD_CLAIM_DAILY/not_eligible.png`
- Create from captured state: `tests/fixtures/DAILY_TASK_REWARD_CLAIM_DAILY/known_drift.png`
- Create after live run: `verification/mfw/DAILY_TASK_REWARD_CLAIM_DAILY.json`

**Interfaces:**
- Consumes: 公共启动/终点和 daily task templates。
- Produces: `MJA_DAILY_TASK_REWARD_CLAIM_DAILY_START`; exact frozen action IDs `open_function_panel`, `open_daily_tasks`, `claim_completed_daily_row`, `scroll_daily_reward_rows`, `close_reward_popup`, `claim_unlocked_activity_chest`, `close_daily_tasks`。

- [ ] **Step 1: 写领取和滚动边界测试**

```python
def test_daily_rewards_claim_rows_then_chests_with_five_scroll_limit():
    nodes = task_nodes("DAILY_TASK_REWARD_CLAIM_DAILY")
    assert_loop_bound(nodes, "MJA_DAILY_REWARD_SCAN", maximum=5)
    assert_action_limit("DAILY_TASK_REWARD_CLAIM_DAILY", "claim_completed_daily_row", 50)
    assert_action_limit("DAILY_TASK_REWARD_CLAIM_DAILY", "claim_unlocked_activity_chest", 10)
    assert_action_limit("DAILY_TASK_REWARD_CLAIM_DAILY", "close_reward_popup", 60)
    assert_ordered_actions(nodes, ["claim_completed_daily_row", "close_reward_popup", "claim_unlocked_activity_chest"])
    assert_outcome(nodes, "MJA_DAILY_REWARD_NONE", "already_complete", "daily_reward.no_claimable")
    assert_outcome(nodes, "MJA_DAILY_REWARD_DONE", "success", "daily_reward.no_claimable")
```

- [ ] **Step 2: 运行测试确认先失败**

Run: `uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/mfw/tasks/test_batch_a.py -k daily_task_reward -q`

Expected: FAIL because task/Pipeline are absent.

- [ ] **Step 3: 实现日常奖励 Pipeline**

```json
{"task":[{"name":"DAILY_TASK_REWARD_CLAIM_DAILY","label":"日常任务奖励","default_check":true,"group":["日常"],"entry":"MJA_DAILY_TASK_REWARD_CLAIM_DAILY_START"}]}
```

Start the target from `assets/resource_android/pipeline/daily/daily_task_reward_claim_daily.json`, remove its delegate nodes, and implement the following bounded Maa-only scan.

Navigate panel → daily. In each fresh frame prefer one completed-row claim, dismiss bounded reward popups, then claim one uniquely active activity chest. Scroll only when no target is visible, at most five times. If no claimable target is found before any mutation, return `already_complete`; after any claim, restart scan from current page and finish `success` only after a full bounded scan finds none. Ambiguous row/chest or exhausted scan with unresolved red dot Aborts.

- [ ] **Step 4: 运行 fixture、资源和真实单项门**

```bash
uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/mfw/tasks/test_batch_a.py -k daily_task_reward -q
python3 tools/check_mfw_resources.py assets/resource/base
python3 tools/mfw_install.py --base-candidate install/mfw-foundation-candidate --output install/mfw-daily-task-reward-claim-daily
python3 tools/mfw_profile.py run --install install/mfw-daily-task-reward-claim-daily --profile-name live-DAILY_TASK_REWARD_CLAIM_DAILY
```

Expected: fixture pass；live scroll ≤5，重跑 no claimable/already_complete。记录 evidence。

- [ ] **Step 5: 提交**

```bash
git add assets/tasks/日常/DAILY_TASK_REWARD_CLAIM_DAILY.json assets/resource/base/pipeline/daily/daily_task_reward_claim_daily.json assets/interface.mfw.json tests/mfw/tasks/test_batch_a.py tests/fixtures/DAILY_TASK_REWARD_CLAIM_DAILY verification/mfw/DAILY_TASK_REWARD_CLAIM_DAILY.json
git commit -m "feat: migrate daily reward claim to independent MFW task"
```

### Task 10: 迁移 BATTLE_PASS_REWARD_DAILY 并完成简化版预设

**Files:**
- Create: `assets/tasks/日常/BATTLE_PASS_REWARD_DAILY.json`
- Create: `assets/resource/base/pipeline/daily/battle_pass_reward_daily.json`
- Modify: `assets/interface.mfw.json`
- Modify: `tests/mfw/tasks/test_batch_a.py`
- Modify: `tests/test_mfw_presets.py`
- Modify: `tests/fixtures/BATTLE_PASS_REWARD_DAILY/manifest.json`
- Create from captured state: `tests/fixtures/BATTLE_PASS_REWARD_DAILY/not_eligible.png`
- Create from captured state: `tests/fixtures/BATTLE_PASS_REWARD_DAILY/known_drift.png`
- Create after live run: `verification/mfw/BATTLE_PASS_REWARD_DAILY.json`

**Interfaces:**
- Consumes: 公共启动/终点和 battle pass templates。
- Produces: `MJA_BATTLE_PASS_REWARD_DAILY_START`; exact frozen action IDs `open_function_panel`, `open_battle_pass`, `open_battle_pass_tasks`, `claim_task_reward`, `close_reward_popup`, `open_battle_pass_rewards`, `claim_basic_red_dot_reward`, `close_battle_pass`；最终简化版 preset。

- [ ] **Step 1: 写战令双阶段和简化预设测试**

```python
def test_battle_pass_claims_task_then_basic_rewards_only():
    nodes = task_nodes("BATTLE_PASS_REWARD_DAILY")
    assert_ordered_actions(nodes, ["open_battle_pass_tasks", "claim_task_reward", "close_reward_popup", "open_battle_pass_rewards", "claim_basic_red_dot_reward"])
    assert_loop_bound(nodes, "MJA_BP_TASK_CLAIM_LOOP", maximum=50)
    assert_loop_bound(nodes, "MJA_BP_BASIC_CLAIM_LOOP", maximum=50)
    assert_action_limit("BATTLE_PASS_REWARD_DAILY", "close_reward_popup", 50)
    assert_abort_code(nodes, "MJA_BP_REWARDS_AMBIGUOUS", "BATTLE_PASS_REWARDS_PAGE_AMBIGUOUS")
    assert_outcome(nodes, "MJA_BP_ALL_CLAIMED", "already_complete", "battle_pass.no_basic_claimable")


def test_simplified_preset_exact_order():
    assert preset_ids("日常-简化版") == ["GAME_START", *BATCH_A_IDS]
```

- [ ] **Step 2: 运行测试确认先失败**

Run: `uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/mfw/tasks/test_batch_a.py -k battle_pass tests/test_mfw_presets.py -q`

Expected: FAIL because task/Pipeline and final simplified preset entry are absent.

- [ ] **Step 3: 实现战令 Pipeline 和简化版预设**

```json
{"task":[{"name":"BATTLE_PASS_REWARD_DAILY","label":"战令基础奖励","default_check":true,"group":["日常"],"entry":"MJA_BATTLE_PASS_REWARD_DAILY_START"}]}
```

Start the target from `assets/resource_android/pipeline/daily/battle_pass_reward_daily.json`, remove its delegate nodes, and implement the following two-phase Maa-only claim flow.

Enter battle pass. First claim uniquely visible completed task rewards in a max-50 loop, dismissing one recognized popup at a time under the shared popup cap 50. Open rewards tab, then claim only basic/free-track red-dot rewards in a max-50 loop; premium/paid-track controls are permanently forbidden. If both phases have no claimable item before mutation, return `already_complete`; after claims require no basic claimable target for `success`; ambiguous rewards page, track identity or unresolved red dot Aborts. Set simplified preset exactly to startup + the 9 IDs in this plan's fixed order.

- [ ] **Step 4: 运行批次自动化和最后单项实机**

```bash
uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/mfw/tasks/test_batch_a.py tests/test_mfw_presets.py -q
python3 tools/check_mfw_resources.py assets/resource/base
python3 tools/mfw_install.py --base-candidate install/mfw-foundation-candidate --output install/mfw-battle-pass-reward-daily
python3 tools/mfw_profile.py run --install install/mfw-battle-pass-reward-daily --profile-name live-BATTLE_PASS_REWARD_DAILY
```

Expected: all batch-A tests pass；live never clicks premium track，重跑 already_complete。记录 evidence。

- [ ] **Step 5: 提交**

```bash
git add assets/tasks/日常/BATTLE_PASS_REWARD_DAILY.json assets/resource/base/pipeline/daily/battle_pass_reward_daily.json assets/interface.mfw.json tests/mfw/tasks/test_batch_a.py tests/test_mfw_presets.py tests/fixtures/BATTLE_PASS_REWARD_DAILY verification/mfw/BATTLE_PASS_REWARD_DAILY.json
git commit -m "feat: migrate battle pass and complete simplified preset"
```

### Task 11: 执行批次 A 串行与失败隔离验收

**Files:**
- Create after live run: `verification/mfw/batch-a-sequence.json`
- Modify: `tools/verify_mfw_evidence.py`
- Test: `tests/test_mfw_evidence.py`

**Interfaces:**
- Consumes: 9 个任务的单项 evidence、简化版 preset、失败传播契约。
- Produces: `verify_batch(root, batch="a")` 和批次 A 可进入批次 B 的唯一实机证据。

- [ ] **Step 1: 写证据完整性测试**

```python
def test_batch_a_evidence_requires_each_task_and_sequence(tmp_path):
    write_valid_task_evidence_set(tmp_path, BATCH_A_IDS)
    with pytest.raises(ValueError, match="batch-a-sequence"):
        verify_batch(tmp_path, batch="a")
```

- [ ] **Step 2: 运行测试确认先失败**

Run: `uv run --no-project --with-requirements requirements.txt --with pytest pytest tests/test_mfw_evidence.py -q`

Expected: FAIL，因为 batch verifier 尚未实现。

- [ ] **Step 3: 实现严格批次验证器**

Require every task evidence to contain candidate metadata SHA, run ID, start page, terminal status, action counts, before/after paths, same-day rerun status and zero duplicate execution. Require sequence evidence to list exactly the 9 IDs in order, plus an injected business Abort case whose following task starts and finishes.

- [ ] **Step 4: 用同一候选执行简化版和手工 9 项全选**

```bash
python3 tools/mfw_install.py --base-candidate install/mfw-foundation-candidate --output install/mfw-batch-a-final
python3 tools/mfw_profile.py run --install install/mfw-batch-a-final --profile-name live-simplified-preset
python3 tools/mfw_profile.py run --install install/mfw-batch-a-final --profile-name live-batch-a-manual-all
python3 tools/verify_mfw_evidence.py --root verification/mfw --batch a
```

Expected: 每个 ID 每次队列恰好出现一次；任务不依赖前一任务回主页；任务局部 Abort 后下一项可恢复；同日第二轮不重复副作用。

- [ ] **Step 5: 提交真实批次证据**

```bash
git add tools/verify_mfw_evidence.py tests/test_mfw_evidence.py verification/mfw/batch-a-sequence.json
git commit -m "test: validate batch A MFW sequence"
```

## 批次 A 完成门

- [ ] 9 个 task 的 fixture、资源引用、输入门禁、终态和 Abort 测试全部通过。
- [ ] 9 个单项均从主页和自己的业务页实机通过；完成后重跑不重复副作用。
- [ ] 简化版和手工 9 项全选都只执行每项一次，且顺序一致。
- [ ] 注入一个业务 Abort 后下一项仍重新建立页面状态并运行。
- [ ] 所有 evidence 使用同一个 build metadata；未执行状态没有被写成 passed。
