#!/usr/bin/env bash
# Match a Linux container's network interface to the host's IPv4 default route.
set -euo pipefail

container="${1:?Usage: align_container_mtu.sh CONTAINER [INTERFACE]}"
container_interface="${2:-eth0}"
host_interface="$(ip -o -4 route show default | awk '
  { for (i = 1; i < NF; i++) if ($i == "dev") { print $(i + 1); exit } }
')"
host_mtu="$(cat "/sys/class/net/$host_interface/mtu")"
container_pid="$(sudo docker inspect --format='{{.State.Pid}}' -- "$container")"
sudo nsenter --target "$container_pid" --net ip link set dev "$container_interface" mtu "$host_mtu"
printf 'MJA_ANDROID_MTU=%s\n' "$host_mtu"
