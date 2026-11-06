#!/bin/bash
# Read chip and flash identity through Adafruit's PyPortal USB passthrough.
# No flash writes or erases are performed.
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
tool="$project_dir/.toolchain/data/packages/esp32/tools/esptool_py/5.2.0/esptool"
mkdir -p "$project_dir/logs"
if [[ -d /Volumes/CIRCUITPY || -d /Volumes/PORTALBOOT ]]; then
  printf 'Install the PyPortal ESP32 passthrough UF2 first. CIRCUITPY and PORTALBOOT should be absent.\n'
  exit 1
fi
if [[ ! -x "$tool" ]]; then
  printf 'The installed esptool executable was not found. Complete the build first.\n'
  exit 1
fi
if [[ $# -gt 0 ]]; then
  device_port="$1"
else
  shopt -s nullglob
  devices=(/dev/cu.usbmodem*)
  if [[ ${#devices[@]} -ne 1 ]]; then
    printf 'Expected exactly one USB modem serial port. Found %s.\n' "${#devices[@]}"
    printf 'Specify the verified PyPortal port as the argument to this script.\n'
    exit 1
  fi
  device_port="${devices[0]}"
fi
case "$device_port" in
  /dev/cu.usbmodem*) ;;
  *) printf 'Expected a PyPortal /dev/cu.usbmodem port.\n'; exit 1 ;;
esac
printf 'Inspecting %s without writing flash.\n' "$device_port"
"$tool" --chip esp32 --port "$device_port" --before no-reset --after no-reset \
  --baud 115200 flash-id 2>&1 | tee "$project_dir/logs/esp32-inspect.log"
