#!/bin/zsh
set -euo pipefail

project_root="/Volumes/my_disk/project/MJA"
sdk_root="$project_root/install/android-sdk"
adb="$sdk_root/platform-tools/adb"
emulator="$sdk_root/emulator/emulator"
python="$project_root/.venv/bin/python"
avd_name="mja-api35-apis"
serial="emulator-5556"
emulator_log="/tmp/mja-android-emulator.log"
emulator_pid=""
started_here="false"

show_error() {
    local message="$1"
    osascript -e "display alert \"MJA Android Emulator 无法启动\" message \"$message\" as critical" >/dev/null 2>&1 || true
}

if [[ ! -x "$adb" || ! -x "$emulator" ]]; then
    show_error "Android SDK 不完整：需要 bundled adb 和 emulator。"
    exit 1
fi

device_state() {
    "$adb" -s "$serial" get-state 2>/dev/null || true
}

stop_started_emulator() {
    if [[ "$started_here" == "true" && -n "$emulator_pid" ]] && kill -0 "$emulator_pid" 2>/dev/null; then
        kill -TERM "$emulator_pid" 2>/dev/null || true
    fi
    if [[ "$started_here" == "true" && -n "$emulator_pid" ]]; then
        wait "$emulator_pid" 2>/dev/null || true
    fi
}

on_interrupt() {
    stop_started_emulator
    exit 130
}

if [[ "$(device_state)" == "device" ]]; then
    "$python" "$project_root/tools/mfw_android_preflight.py"
    osascript -e 'display notification "emulator-5556 已经在运行" with title "MJA Android Emulator"' >/dev/null 2>&1 || true
    exit 0
fi

if pgrep -f -- "qemu-system.*-avd $avd_name.*-port 5556" >/dev/null 2>&1; then
    show_error "mja-api35-apis 已经启动但还没有完成 ADB 就绪，请稍候再试。"
    exit 1
fi

if pgrep -f -- "qemu-system.*-avd $avd_name" >/dev/null 2>&1; then
    show_error "检测到同一 AVD 已占用其他端口；请先关闭它，再重新点击此图标。"
    exit 1
fi

emulator_args=(
    -avd "$avd_name"
    -no-snapshot
    -no-boot-anim
    -noaudio
    -qt-hide-window
    -gpu host
    -selinux permissive
    -crash-report-mode never
    -no-metrics
    -memory 6144
    -port 5556
)

# Keep host GLES/Vulkan as the normal contract.  This opt-in switch is used
# for a controlled diagnosis of host Vulkan/gfxstream crashes; it must never
# change the required `-gpu host` backend.
if [[ "${MJA_EMULATOR_DISABLE_VULKAN:-0}" == "1" ]]; then
    emulator_args+=(-feature -Vulkan)
fi

# Second controlled diagnosis switch: keep Vulkan enabled but disable deferred
# queue submission.  This is now the default safety mitigation for the known
# Emulator 36.6.11 host-Vulkan crash; set it to 0 only for a controlled test.
if [[ "${MJA_EMULATOR_DISABLE_VULKAN_QUEUE:-1}" == "1" ]]; then
    emulator_args+=(-feature -VulkanQueueSubmitWithCommands)
fi

print -r -- "[$(date '+%Y-%m-%dT%H:%M:%S%z')] starting emulator: ${emulator_args[*]}" >>"$emulator_log"
trap on_interrupt INT TERM
"$emulator" "${emulator_args[@]}" >>"$emulator_log" 2>&1 &
emulator_pid=$!
started_here="true"

ready="false"
for _attempt in {1..120}; do
    if ! kill -0 "$emulator_pid" 2>/dev/null; then
        set +e
        wait "$emulator_pid"
        emulator_status=$?
        set -e
        show_error "模拟器进程已退出（状态 $emulator_status）；日志：$emulator_log"
        exit "$emulator_status"
    fi
    if [[ "$(device_state)" == "device" ]]; then
        ready="true"
        break
    fi
    sleep 1
done

if [[ "$ready" != "true" ]]; then
    stop_started_emulator
    show_error "固定端口 $serial 未就绪；日志：$emulator_log"
    exit 1
fi

if ! "$python" "$project_root/tools/mfw_android_preflight.py"; then
    stop_started_emulator
    show_error "模拟器未通过运行时契约检查；日志：$emulator_log"
    exit 1
fi

set +e
wait "$emulator_pid"
emulator_status=$?
set -e
if [[ "$emulator_status" != "0" ]]; then
    show_error "模拟器异常退出（状态 $emulator_status）；日志：$emulator_log"
fi
exit "$emulator_status"
