from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_container_uses_mtu_from_host_default_interface(tmp_path):
    commands = {
        "ip": 'test "$*" = "-o -4 route show default"\nprintf "default via 192.0.2.1 dev uplink0 proto dhcp\\n"',
        "cat": 'test "$1" = /sys/class/net/uplink0/mtu\nprintf "1440\\n"',
        "sudo": """if [ "$1" = docker ]; then
  test "$2" = inspect
  test "$5" = test-container
  printf '1234\n'
else
  test "$*" = 'nsenter --target 1234 --net ip link set dev test-nic mtu 1440'
  printf '%s\n' "$*" > "$MJA_TEST_NETWORK_COMMAND"
fi""",
    }
    for name, script in commands.items():
        command = tmp_path / name
        command.write_text("#!/bin/sh\nset -eu\n" + script + "\n")
        command.chmod(0o700)

    link_command = tmp_path / "link-command"
    env = os.environ | {
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "MJA_TEST_NETWORK_COMMAND": str(link_command),
    }
    result = subprocess.run(
        ["bash", str(ROOT / "tools/align_container_mtu.sh"), "test-container", "test-nic"],
        text=True,
        capture_output=True,
        check=True,
        env=env,
    )
    assert result.stdout == "MJA_ANDROID_MTU=1440\n"
    assert link_command.read_text().endswith("mtu 1440\n")
