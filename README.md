<!-- markdownlint-disable MD033 MD041 -->

<p align="center">
  <img src="assets/branding/mja-readme-hero.png" alt="MJA 主题图" width="100%" />
</p>

<div align="center">

# MJA

《对决！剑之川》的 MaaFramework 自动化项目

<a href="https://github.com/TaurusGGBOY/MJA/actions/workflows/mfw-check.yml">
  <img alt="CI" src="https://github.com/TaurusGGBOY/MJA/actions/workflows/mfw-check.yml/badge.svg?branch=main" />
</a>
<a href="LICENSE">
  <img alt="license" src="https://img.shields.io/badge/license-Apache--2.0-blue.svg" />
</a>
<img alt="platform" src="https://img.shields.io/badge/platform-macOS%20%2B%20Android%20emulator-informational" />
<img alt="tasks" src="https://img.shields.io/badge/daily%20tasks-22-0b84f3" />

</div>

## 简介

MJA 使用 MaaFramework、ADB Android Controller 和隔离的 Android 模拟器，提供可复用、可审计的日常任务自动化。项目当前以 macOS 主机为主要运行环境，任务入口统一为 MFW + Android 模拟器。

设计目标：

- 每个业务任务都是独立的 MFW 任务，可在 GUI 中单独选择。
- `Invalid`、`Pending`、`Running`、`Succeeded`、`Failed` 是唯一任务状态模型。
- 已完成和本次执行成功都归入 `Succeeded`；普通业务失败归入 `Failed`，不会阻塞后续任务。
- 识别、输入、恢复和终态都使用有限预算，避免无界点击或跨任务副作用。
- 日志、截图和节点轨迹只用于诊断，不替代 MFW 原生终态。

## 支持的任务

当前包含 22 个日常任务定义，位于 [`assets/tasks/日常`](assets/tasks/日常)：

| 任务 | 任务 | 任务 |
| --- | --- | --- |
| 战令奖励 | 突破阵法 | 买茶 |
| 采集部署 | 日常任务奖励 | 副本扫荡 |
| 吃体力食物 | 装备分解 | 免费鉴定 |
| 帮派活动挑战 | 帮派事务 | 帮派捐献 |
| 英雄派遣 | 剑林凝结体体力 | 邮件奖励 |
| 武学研习突破 | 擂台挑战 | 影之遗迹 |
| 每日特惠礼包 | 消耗凝结体 | 试剑 |
| 每周免费礼包 |  |  |

每周礼包任务每天都允许运行；如果页面已经显示已领取，任务仍以 MFW 原生 `Succeeded` 结束。

## 快速开始

### 环境

- macOS Apple Silicon 或兼容的 macOS 主机
- Python 3.12–3.14
- Android SDK、ADB 和 ARM64 Android 模拟器
- MaaFramework 运行时
- 已安装并完成登录的游戏环境

安装 Python 依赖：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
```

将本地 APK 放在被忽略的 `artifacts/jianzhichuan.apk`，或按 `config/android.json` 修改本地配置。不要把 APK、账号信息或运行日志提交到仓库。

### 构建并运行 MFW 候选

```bash
.venv/bin/python tools/mfw_install.py --output install/mfw-candidate
MJA_MFW_CANDIDATE="$PWD/install/mfw-candidate" ./tools/launch_mfw.zsh
```

首次运行可能需要手动完成游戏登录；登录完成后，MJA 不会自动填写账号、密码或验证码。

### 运行测试

```bash
.venv/bin/python -m pytest -q
```

资源检查和候选加载：

```bash
.venv/bin/python tools/check_mfw_resources.py install/mfw-candidate/resource/base
.venv/bin/python tools/load_mfw_resource.py install/mfw-candidate
```

## 运行约束

- 模拟器必须使用 `-gpu host`，不能替换为 software、auto 或 SwiftShader。
- 项目脚本支持通过 `MJA_PROJECT_ROOT`、`MJA_ANDROID_SDK_ROOT` 等环境变量覆盖本机路径。
- 任务不会自动化登录、支付、验证码、实名或其他高风险操作。
- 真实运行前只选择 `GAME_START + 指定任务`，并声明期望的 MFW 原生终态。
- 不要同时启动多个 MFW runner 或多个正式模拟器任务。

## 项目结构

```text
agent/       Agent 自定义动作、识别器和运行时支持
assets/      MFW interface、pipeline、任务定义和 OCR 资源
docs/        面向贡献者的架构与开发文档
native/      MaaFramework 原生补丁和可复现构建脚本
runtime/     macOS 模拟器启动辅助程序
tests/       单元测试、pipeline 契约和脱敏夹具
tools/       安装、检查、候选构建和运行工具
vendor/      经许可审核后随项目分发的第三方运行库
```

贡献前请阅读 [`AGENTS.md`](AGENTS.md) 和 [`CONTRIBUTING.md`](CONTRIBUTING.md)。

## 许可证与第三方内容

项目代码和原创内容按 [Apache License 2.0](LICENSE) 发布。MaaFramework、MFAAvalonia、OCR 模型、游戏名称、游戏截图和其他二进制资源仍受各自许可证或服务条款约束，详见 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。本项目不分发游戏本体，也不授予绕过服务条款的权限。

## 免责声明

本项目仅用于个人研究、自动化测试和辅助开发。使用者应遵守游戏运营商、平台和所在地区的相关规则，并自行承担使用风险。
