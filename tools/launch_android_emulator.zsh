#!/bin/zsh
set -euo pipefail

script_dir="${0:A:h}"
project_root="${MJA_PROJECT_ROOT:-${script_dir:h}}"
sdk_root="$project_root/install/android-sdk"
adb="$sdk_root/platform-tools/adb"
emulator="$sdk_root/emulator/emulator"
python="$project_root/.venv/bin/python"
# Bundled runtime venv; it ships PyObjC which is required to bring the
# emulator window to the foreground in visible mode.
pyobjc_python="$project_root/install/.venv/bin/python"
avd_name="mja-api35-apis"
serial="emulator-5556"
emulator_log="/tmp/mja-android-emulator.log"
emulator_pid=""
started_here="false"
# Visible mode is used by the macOS dock/desktop entry (MJA Android
# Emulator.app): the emulator window is shown instead of hidden.  Automation
# keeps the default hidden mode unchanged.
visible="${MJA_EMULATOR_VISIBLE:-0}"

show_error() {
    local message="$1"
    # Never open a modal alert here.  This script is also used as the
    # emulator child of the MFW runner; a modal alert would keep the parent
    # process alive forever after QEMU has already exited.
    print -u2 -- "MJA Android Emulator 无法启动：$message"
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
    if [[ "$visible" == "1" ]]; then
        running_pid="$(pgrep -f -- "qemu-system.*-avd $avd_name" | head -n 1 || true)"
        if [[ -n "$running_pid" ]] && ps -p "$running_pid" -o command= 2>/dev/null | grep -q -- "-qt-hide-window"; then
            # ADB is ready but the running instance was started hidden by
            # automation; restart it with a visible window (same pattern as
            # launch_mfw.zsh MJA_EMULATOR_VISIBLE=1).
            "$adb" -s "$serial" emu kill >/dev/null 2>&1 || kill -TERM "$running_pid" 2>/dev/null || true
            for _attempt in {1..30}; do
                if ! kill -0 "$running_pid" 2>/dev/null; then
                    break
                fi
                sleep 1
            done
            # Fall through to the normal start path below.
        else
            # The instance is already visible: bring its window forward.
            # PyObjC works in terminal context; GUI-launched processes cannot
            # read the project volume, so fall back to System Events.
            foreground_ok="false"
            if [[ -x "$pyobjc_python" ]] && PYTHONPATH="$project_root" "$pyobjc_python" -c '
import sys
from agent.android.emulator_window import ensure_emulator_foreground
sys.exit(0 if ensure_emulator_foreground(sys.argv[1]) else 1)
' "$avd_name" >/dev/null 2>&1; then
                foreground_ok="true"
            fi
            if [[ "$foreground_ok" != "true" ]] && [[ -n "$running_pid" ]]; then
                if osascript -e "tell application \"System Events\" to set frontmost of first process whose unix id is $running_pid to true" >/dev/null 2>&1; then
                    foreground_ok="true"
                fi
            fi
            if [[ "$foreground_ok" == "true" ]]; then
                osascript -e 'display notification "emulator-5556 已经在前台" with title "MJA Android Emulator"' >/dev/null 2>&1 || true
                exit 0
            else
                osascript -e 'display notification "emulator-5556 已经在运行" with title "MJA Android Emulator"' >/dev/null 2>&1 || true
                exit 0
            fi
        fi
    else
        "$python" "$project_root/tools/mfw_android_preflight.py"
        osascript -e 'display notification "emulator-5556 已经在运行" with title "MJA Android Emulator"' >/dev/null 2>&1 || true
        exit 0
    fi
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
    -gpu host
    -selinux permissive
    -crash-report-mode never
    -no-metrics
    -memory 6144
    -port 5556
)

# The dock/desktop entry opens a visible window; automation keeps the
# window hidden so it cannot steal focus from the user.
if [[ "$visible" != "1" ]]; then
    emulator_args+=(-qt-hide-window)
fi

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

if [[ "$visible" == "1" ]] && ! head -c 1 "$project_root/config/android.json" >/dev/null 2>&1; then
    # GUI-launched processes cannot read the external project volume
    # (macOS removable-volume TCC).  The emulator contract flags are enforced
    # by construction above, so preflight adds nothing here and must not turn
    # the dock entry into an error.
    print -r -- "[$(date '+%Y-%m-%dT%H:%M:%S%z')] skipping preflight: project volume not readable from GUI context" >>"$emulator_log"
else
    if ! "$python" "$project_root/tools/mfw_android_preflight.py"; then
        stop_started_emulator
        show_error "模拟器未通过运行时契约检查；日志：$emulator_log"
        exit 1
    fi
fi

if [[ "$visible" == "1" ]]; then
    # Dock entry: hand the emulator over to the OS and exit, so that clicking
    # the icon again re-runs the launcher (e.g. to bring the window forward).
    # Automation keeps the blocking wait below.
    print -r -- "[$(date '+%Y-%m-%dT%H:%M:%S%z')] emulator ready; detaching (dock entry)" >>"$emulator_log"
    exit 0
fi

set +e
wait "$emulator_pid"
emulator_status=$?
set -e
if [[ "$emulator_status" != "0" ]]; then
    show_error "模拟器异常退出（状态 $emulator_status）；日志：$emulator_log"
fi
exit "$emulator_status"
