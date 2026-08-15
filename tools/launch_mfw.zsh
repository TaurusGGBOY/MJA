#!/bin/zsh
set -euo pipefail

project_root="/Volumes/my_disk/project/MJA"
candidate="${MJA_MFW_CANDIDATE:-$project_root/install/mfw-game-startup-maa-bbb-20260808-final-r14}"
sdk_root="$project_root/install/android-sdk"
adb="$sdk_root/platform-tools/adb"
emulator="$sdk_root/emulator/emulator"
python="$project_root/.venv/bin/python"
avd_name="mja-api35-apis"
serial="emulator-5556"
game_package="com.hanjiasongshu.dr22"
emulator_log="/tmp/mja-mfw-emulator.log"

show_error() {
    local message="$1"
    osascript -e "display alert \"MJA MFW 无法启动\" message \"$message\" as critical" >/dev/null 2>&1 || true
}

if [[ ! -x "$candidate/MFW" ]]; then
    show_error "MFW 候选包不存在：$candidate"
    exit 1
fi

if [[ ! -x "$adb" || ! -x "$emulator" ]]; then
    show_error "Android SDK 不完整：需要 bundled adb 和 emulator。"
    exit 1
fi

device_state() {
    "$adb" -s "$serial" get-state 2>/dev/null || true
}

android_framework_ready() {
    local boot_completed
    boot_completed="$("$adb" -s "$serial" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r\n' || true)"
    [[ "$boot_completed" == "1" ]] || return 1
    "$adb" -s "$serial" shell cmd activity get-current-user >/dev/null 2>&1
}

emulator_pid() {
    pgrep -f -- "qemu-system.*-avd $avd_name.*-port 5556" | head -n 1 || true
}

restart_hidden_emulator_for_visibility() {
    local pid cmdline
    pid="$(emulator_pid)"
    if [[ -z "$pid" ]]; then
        return 1
    fi
    cmdline="$(ps -p "$pid" -o command= 2>/dev/null || true)"
    if [[ "$cmdline" != *"-qt-hide-window"* ]]; then
        return 1
    fi

    print -r -- "可见模式：停止隐藏的 AVD（pid=$pid）并重新启动可见窗口。"
    "$adb" -s "$serial" emu kill >/dev/null 2>&1 || kill -TERM "$pid" 2>/dev/null || true
    for _attempt in {1..30}; do
        if ! kill -0 "$pid" 2>/dev/null; then
            return 0
        fi
        sleep 1
    done
    show_error "隐藏的 AVD 未能在 30 秒内退出，无法切换到可见模式。"
    exit 1
}

state="$(device_state)"
if [[ "${MJA_EMULATOR_VISIBLE:-0}" == "1" ]]; then
    if restart_hidden_emulator_for_visibility; then
        state="offline"
    fi
fi
if [[ "$state" != "device" ]]; then
    if ! pgrep -f -- "qemu-system.*-avd $avd_name.*-port 5556" >/dev/null 2>&1; then
        if pgrep -f -- "qemu-system.*-avd $avd_name" >/dev/null 2>&1; then
            show_error "检测到同一 AVD 已占用其他端口；请先关闭它，再从 MJA MFW 图标启动。"
            exit 1
        fi
        emulator_args=(
            -avd "$avd_name" \
            -no-snapshot \
            -no-boot-anim \
            -noaudio \
            -gpu host \
            -selinux permissive \
            -crash-report-mode never \
            -no-metrics \
            -memory 6144 \
            -port 5556
        )
        if [[ "${MJA_EMULATOR_VISIBLE:-0}" != "1" ]]; then
            emulator_args+=(-qt-hide-window)
        fi
        if [[ "${MJA_EMULATOR_DISABLE_VULKAN_QUEUE:-1}" == "1" ]]; then
            emulator_args+=(-feature -VulkanQueueSubmitWithCommands)
        fi
        print -r -- "[$(date '+%Y-%m-%dT%H:%M:%S%z')] starting emulator: ${emulator_args[*]}" >>"$emulator_log"
        "$emulator" "${emulator_args[@]}" >>"$emulator_log" 2>&1 </dev/null &!
    fi

    ready="false"
    for _attempt in {1..90}; do
        if [[ "$(device_state)" == "device" ]] && android_framework_ready; then
            ready="true"
            break
        fi
        sleep 1
    done
    if [[ "$ready" != "true" ]]; then
        show_error "固定端口 $serial 未就绪；模拟器日志：$emulator_log"
        exit 1
    fi
fi

if [[ "${MJA_CLOSE_GAME_BEFORE_RUN:-0}" == "1" ]]; then
    print -r -- "预运行清理：关闭游戏 App（$game_package），不清除应用数据。"
    if ! "$adb" -s "$serial" shell am force-stop "$game_package"; then
        show_error "无法在 GAME_START 前关闭游戏 App：$game_package"
        exit 1
    fi
    sleep 1
fi

preflight_json="$($python "$project_root/tools/mfw_android_preflight.py")"
print -r -- "$preflight_json"

export MJA_CONTROLLER="android"
export MJA_ANDROID_AVD="$avd_name"
export MJA_ANDROID_ADB="$adb"
export MJA_DEBUG_DIR="$candidate/debug"

cd "$candidate"
exec "$candidate/MFW" "$@"
