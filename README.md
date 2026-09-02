<!-- markdownlint-disable MD033 MD041 -->

<p align="center">
  <img src="assets/branding/mja-readme-hero.png" alt="MJA daily-task automation overview" width="100%" />
</p>

<div align="center">

# MJA

MaaFramework automation project for *Duel! Jianzhichuan*

<a href="https://github.com/TaurusGGBOY/MJA/actions/workflows/mfw-check.yml">
  <img alt="CI" src="https://github.com/TaurusGGBOY/MJA/actions/workflows/mfw-check.yml/badge.svg?branch=main" />
</a>
<a href="LICENSE">
  <img alt="License" src="https://img.shields.io/badge/license-Apache--2.0-blue.svg" />
</a>
<img alt="Platform" src="https://img.shields.io/badge/platform-macOS%20%2B%20Android%20emulator-informational" />
<img alt="Daily tasks" src="https://img.shields.io/badge/daily%20tasks-22-0b84f3" />

</div>

## Overview

MJA uses MaaFramework, an ADB Android controller, and an isolated Android emulator to provide reusable and auditable daily-task automation. The project currently targets macOS hosts, with all task entry points running through MFW and an Android emulator.

Design goals:

- Each business task is an independent MFW task that can be selected individually in the GUI.
- `Invalid`, `Pending`, `Running`, `Succeeded`, and `Failed` are the only task states.
- Already-completed tasks and tasks completed during the current run both end as `Succeeded`; ordinary business failures end as `Failed` without blocking subsequent tasks.
- Recognition, input, recovery, and termination use bounded budgets to avoid unbounded clicking or cross-task side effects.
- Logs, screenshots, and node traces are diagnostic artifacts; they do not replace MFW's native terminal state.

## Supported daily tasks

The project currently defines 22 daily tasks in the repository's daily-task definitions directory:

| Task | Task | Task |
| --- | --- | --- |
| Battle Pass rewards | Break Array | Buy Tea |
| Collection Deployment | Daily task rewards | Dungeon sweep |
| Eat stamina food | Equipment decomposition | Free appraisal |
| Guild activity challenge | Guild affairs | Guild donation |
| Hero dispatch | Jianlin condensate stamina | Mail rewards |
| Martial study breakthrough | Ring challenge | Shadow ruins |
| Daily special offer | Spend condensate | Trial Sword |
| Weekly free gift |  |  |

The weekly-free-gift task may run every day. If the UI already shows that it has been claimed, it still ends with MFW's native `Succeeded` state.

## Quick start

### Environment

- macOS on Apple Silicon, or a compatible macOS host
- Python 3.12–3.14
- Android SDK, ADB, and an ARM64 Android emulator
- MaaFramework runtime
- An installed and already-signed-in game environment

Install Python dependencies:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
```

Place the local APK at the ignored path `artifacts/jianzhichuan.apk`, or update the local configuration in `config/android.json`. Do not commit APKs, account data, or runtime logs.

### Build and run an MFW candidate

```bash
.venv/bin/python tools/mfw_install.py --output install/mfw-candidate
MJA_MFW_CANDIDATE="$PWD/install/mfw-candidate" ./tools/launch_mfw.zsh
```

You may need to complete game sign-in manually on the first run. MJA does not automatically enter accounts, passwords, or verification codes.

### Run tests

```bash
.venv/bin/python -m pytest -q
```

Check resources and candidate loading:

```bash
.venv/bin/python tools/check_mfw_resources.py install/mfw-candidate/resource/base
.venv/bin/python tools/load_mfw_resource.py install/mfw-candidate
```

## Runtime constraints

- The emulator must use `-gpu host`; do not replace it with `software`, `auto`, or SwiftShader.
- Scripts support local path overrides through variables such as `MJA_PROJECT_ROOT` and `MJA_ANDROID_SDK_ROOT`.
- Tasks do not automate sign-in, payments, verification codes, identity verification, or other high-risk operations.
- Before a real run, select only `GAME_START` plus the intended task and state the expected MFW terminal state.
- Do not run multiple MFW runners or multiple production emulator tasks at the same time.

## Project layout

```text
agent/       Custom agent actions, recognizers, and runtime support
assets/      MFW interface, pipeline, task definitions, and OCR resources
docs/        Architecture and development documentation for contributors
native/      MaaFramework native patches and reproducible build scripts
runtime/     macOS emulator launch helpers
tests/       Unit tests, pipeline contracts, and sanitized fixtures
tools/       Installation, checking, candidate build, and run tooling
vendor/      License-reviewed third-party runtime libraries
```

Read [`AGENTS.md`](AGENTS.md) and [`CONTRIBUTING.md`](CONTRIBUTING.md) before contributing.

## License and third-party content

Project code and original content are released under the [Apache License 2.0](LICENSE). MaaFramework, MFAAvalonia, OCR models, the game name, game screenshots, and other binary assets remain subject to their respective licenses or terms of service. See [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md). This project does not distribute the game itself or grant permission to bypass service terms.

## Disclaimer

This project is intended for personal research, automation testing, and development assistance. Users are responsible for following the rules of the game operator, platform, and their jurisdiction, and for accepting the risks of use.
