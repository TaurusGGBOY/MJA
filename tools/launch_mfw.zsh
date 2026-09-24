#!/bin/zsh
set -euo pipefail

script_dir="${0:A:h}"
project_root="${MJA_PROJECT_ROOT:-${script_dir:h}}"
candidate="${MJA_MFW_CANDIDATE:-$project_root/install/mfw-gray-panel-20260915-r2}"
candidate="${candidate:A}"
sdk_root="${MJA_ANDROID_SDK_ROOT:-$project_root/install/android-sdk}"
adb="$sdk_root/platform-tools/adb"
emulator="$sdk_root/emulator/emulator"
python="$project_root/.venv/bin/python"
avd_name="mja-api35-apis"
serial="emulator-5556"
game_package="com.hanjiasongshu.dr22"
emulator_log="${MJA_EMULATOR_LOG:-/tmp/codextmp/mja-mfw-emulator.log}"
boot_timeout="${MJA_EMULATOR_BOOT_TIMEOUT_SECONDS:-600}"
export MJA_ANDROID_ADB="$adb"
export MJA_ANDROID_SERIAL="$serial"
export MJA_MFW_CANDIDATE="$candidate"
observer_pid=""

show_error() {
    local message="$1"
    # Keep launcher failures non-blocking.  This script is normally started
    # from another runner, so a modal alert would leave an outer process
    # waiting even after the emulator/MFW child has stopped.
    print -u2 -- "MJA MFW 无法启动：$message"
}

if [[ "$boot_timeout" != <1-> ]]; then
    show_error "MJA_EMULATOR_BOOT_TIMEOUT_SECONDS 必须是正整数。"
    exit 1
fi

if [[ ! -x "$candidate/MFW" ]]; then
    show_error "MFW 候选包不存在：$candidate"
    exit 1
fi

if [[ ! -x "$adb" || ! -x "$emulator" ]]; then
    show_error "Android SDK 不完整：需要 bundled adb 和 emulator。"
    exit 1
fi

# Prepare local diagnostics before starting any child. An explicit ticket wins;
# otherwise the helper uses the candidate's recent unfinished acceptance ticket.
if [[ "${MJA_CRASH_OBSERVE:-1}" == "1" ]]; then
    evidence_dir="$($python "$project_root/tools/mfw_observe_runtime.py" --prepare "$candidate")" || evidence_dir=""
    if [[ -n "$evidence_dir" ]]; then
        export MJA_CRASH_EVIDENCE_DIR="$evidence_dir"
        "$python" "$project_root/tools/mfw_observe_runtime.py" --parent $$ </dev/null >>"$evidence_dir/observer.log" 2>&1 &
        observer_pid=$!
    fi
else
    unset MJA_CRASH_EVIDENCE_DIR
fi
stop_observer() {
    if [[ -n "$observer_pid" ]]; then
        kill -TERM "$observer_pid" 2>/dev/null || true
        local observer_deadline=$(( SECONDS + 12 ))
        while kill -0 "$observer_pid" 2>/dev/null && (( SECONDS < observer_deadline )); do
            sleep 0.2
        done
        kill -KILL "$observer_pid" 2>/dev/null || true
        wait "$observer_pid" 2>/dev/null || true
    fi
}
trap 'stop_observer' EXIT

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
    "$python" "$project_root/tools/mfw_observe_runtime.py" --capture before_visibility_restart || true
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
launched_emulator_pid=""
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
        # Keep the mandated host GPU backend, but allow a controlled
        # mitigation for the confirmed host-Vulkan/gfxstream SIGSEGV.  The
        # Android emulator launcher exposes the same switch.
        if [[ "${MJA_EMULATOR_DISABLE_VULKAN:-0}" == "1" ]]; then
            emulator_args+=(-feature -Vulkan)
        fi
        if [[ "${MJA_EMULATOR_DISABLE_VULKAN_QUEUE:-1}" == "1" ]]; then
            emulator_args+=(-feature -VulkanQueueSubmitWithCommands)
        fi
        mkdir -p "${emulator_log:h}"
        print -r -- "[$(date '+%Y-%m-%dT%H:%M:%S%z')] starting emulator: ${emulator_args[*]}" >>"$emulator_log"
        if [[ -n "${MJA_CRASH_EVIDENCE_DIR:-}" ]]; then
            "$python" "$project_root/tools/mfw_observe_runtime.py" -- "$emulator" "${emulator_args[@]}" >>"$emulator_log" 2>&1 </dev/null &!
        else
            "$emulator" "${emulator_args[@]}" >>"$emulator_log" 2>&1 </dev/null &!
        fi
        launched_emulator_pid=$!
    fi

fi

# ADB can be online before Android's framework is usable. Cold boots on a
# loaded host also exceeded the old 90-iteration window. Wait for the same
# readiness condition for both new and existing devices, with elapsed time
# rather than a count of potentially slow ADB calls.
boot_deadline=$(( SECONDS + boot_timeout ))
ready="false"
while (( SECONDS < boot_deadline )); do
    if [[ "$(device_state)" == "device" ]] && android_framework_ready; then
        ready="true"
        break
    fi
    if [[ -z "$(emulator_pid)" ]] && \
       { [[ -z "$launched_emulator_pid" ]] || ! kill -0 "$launched_emulator_pid" 2>/dev/null; }; then
        show_error "模拟器已退出，停止等待；模拟器日志：$emulator_log"
        exit 1
    fi
    sleep 1
done
if [[ "$ready" != "true" ]]; then
    show_error "Android 在 ${boot_timeout} 秒内未就绪；模拟器日志：$emulator_log"
    exit 1
fi

if [[ "${MJA_CLOSE_GAME_BEFORE_RUN:-0}" == "1" ]]; then
    "$python" "$project_root/tools/mfw_observe_runtime.py" --capture before_launcher_force_stop || true
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
if [[ -n "${MJA_CRASH_EVIDENCE_DIR:-}" ]]; then
    "$candidate/MFW" "$@" >>"$MJA_CRASH_EVIDENCE_DIR/mfw-console.log" 2>&1 &
else
    "$candidate/MFW" "$@" &
fi
mfw_pid=$!

stop_launched_mfw() {
    if kill -0 "$mfw_pid" 2>/dev/null; then
        kill -TERM "$mfw_pid" 2>/dev/null || true
        local stop_deadline=$(( SECONDS + 5 ))
        while kill -0 "$mfw_pid" 2>/dev/null && (( SECONDS < stop_deadline )); do
            sleep 0.2
        done
        if kill -0 "$mfw_pid" 2>/dev/null; then
            kill -KILL "$mfw_pid" 2>/dev/null || true
        fi
    fi
    wait "$mfw_pid" 2>/dev/null || true
}

trap 'stop_launched_mfw; exit 130' INT
trap 'stop_launched_mfw; exit 143' TERM HUP

# A missing QEMU process cannot recover through MFW's ADB reconnect loop.
# Stop only this launcher's child and return failure, retaining native logs
# as an interrupted run rather than allowing the GUI to idle and reconnect.
while kill -0 "$mfw_pid" 2>/dev/null; do
    if [[ -z "$(emulator_pid)" ]]; then
        show_error "模拟器已退出，结束本轮 MFW；本轮未完成，请查看原生日志。"
        stop_launched_mfw
        exit 1
    fi
    sleep 2
done

mfw_exit=0
wait "$mfw_pid" || mfw_exit=$?
if [[ -n "${MJA_CRASH_EVIDENCE_DIR:-}" ]]; then
    MJA_OBSERVED_EXIT="$mfw_exit" "$python" "$project_root/tools/mfw_observe_runtime.py" --record-mfw-exit || true
fi
exit "$mfw_exit"
