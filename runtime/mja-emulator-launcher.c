#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

int main(int argc, char **argv) {
    char sdk_root_buffer[PATH_MAX];
    char emulator_root_buffer[PATH_MAX];
    char bundled_emulator_buffer[PATH_MAX];
    char qt_lib_buffer[PATH_MAX];
    char qt_plugins_buffer[PATH_MAX];
    char dyld_path_buffer[PATH_MAX * 2];
    const char *project_root = getenv("MJA_PROJECT_ROOT");
    const char *sdk_root = getenv("MJA_ANDROID_SDK_ROOT");
    const char *emulator_root = getenv("MJA_EMULATOR_ROOT");
    const char *bundled_emulator = getenv("MJA_EMULATOR_BINARY");

    if (project_root == NULL || *project_root == '\0') {
        project_root = ".";
    }
    if (sdk_root == NULL || *sdk_root == '\0') {
        if (snprintf(sdk_root_buffer, sizeof(sdk_root_buffer), "%s/install/android-sdk", project_root) >= (int)sizeof(sdk_root_buffer)) {
            fprintf(stderr, "MJA emulator wrapper path is too long\n");
            return 1;
        }
        sdk_root = sdk_root_buffer;
    }
    if (emulator_root == NULL || *emulator_root == '\0') {
        if (snprintf(emulator_root_buffer, sizeof(emulator_root_buffer), "%s/emulator", sdk_root) >= (int)sizeof(emulator_root_buffer)) {
            fprintf(stderr, "MJA emulator wrapper path is too long\n");
            return 1;
        }
        emulator_root = emulator_root_buffer;
    }
    if (bundled_emulator == NULL || *bundled_emulator == '\0') {
        if (snprintf(bundled_emulator_buffer, sizeof(bundled_emulator_buffer), "%s/runtime/MJAAndroidEmulator.app/Contents/MacOS/emulator", project_root) >= (int)sizeof(bundled_emulator_buffer)) {
            fprintf(stderr, "MJA emulator wrapper path is too long\n");
            return 1;
        }
        bundled_emulator = bundled_emulator_buffer;
    }
    if (snprintf(qt_lib_buffer, sizeof(qt_lib_buffer), "%s/lib64/qt/lib", emulator_root) >= (int)sizeof(qt_lib_buffer) ||
        snprintf(qt_plugins_buffer, sizeof(qt_plugins_buffer), "%s/lib64/qt/plugins", emulator_root) >= (int)sizeof(qt_plugins_buffer) ||
        snprintf(dyld_path_buffer, sizeof(dyld_path_buffer), "%s/lib64:%s/lib64/qt/lib", emulator_root, emulator_root) >= (int)sizeof(dyld_path_buffer) ||
        setenv("ANDROID_SDK_ROOT", sdk_root, 1) != 0 ||
        setenv("ANDROID_HOME", sdk_root, 1) != 0 ||
        setenv("ANDROID_EMULATOR_LAUNCHER_DIR", emulator_root, 1) != 0 ||
        setenv("ANDROID_QT_LIB_PATH", qt_lib_buffer, 1) != 0 ||
        setenv("ANDROID_QT_QPA_PLATFORM_PLUGIN_PATH", qt_plugins_buffer, 1) != 0 ||
        setenv("DYLD_LIBRARY_PATH", dyld_path_buffer, 1) != 0 ||
        setenv("DYLD_FALLBACK_LIBRARY_PATH", dyld_path_buffer, 1) != 0 ||
        chdir(emulator_root) != 0) {
        fprintf(stderr, "MJA emulator wrapper setup failed: %s\n", strerror(errno));
        return 1;
    }

    // LaunchServices adds this marker for the app wrapper. The Android
    // emulator uses its own SDK/process discovery and must not inherit it.
    unsetenv("__CFBundleIdentifier");

    char **bundled_argv = calloc((size_t)argc + 1, sizeof(*bundled_argv));
    if (bundled_argv == NULL) {
        fprintf(stderr, "MJA emulator wrapper argv allocation failed\n");
        return 1;
    }

    bundled_argv[0] = (char *)bundled_emulator;
    for (int i = 1; i < argc; ++i) {
        bundled_argv[i] = argv[i];
    }

    execv(bundled_emulator, bundled_argv);
    int exec_error = errno;
    free(bundled_argv);
    if (exec_error != 0) {
        fprintf(stderr, "MJA emulator wrapper could not exec bundled emulator: %s\n", strerror(exec_error));
        return 1;
    }
    return 1;
}
