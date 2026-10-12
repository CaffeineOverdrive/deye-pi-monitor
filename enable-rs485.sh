#!/usr/bin/env bash
# Give the monitor access to ONE USB-RS485 adapter - and nothing else (e.g. not a
# 3D printer on the same Pi). Finds the adapter by asking you to unplug and re-plug it.
#
#   ./enable-rs485.sh            pick the adapter and enable RS485
#   ./enable-rs485.sh --disable  remove serial access again (Wi-Fi logger only)
set -euo pipefail
cd "$(dirname "$0")"
[[ -f .env ]] || { echo "Run install.sh first."; exit 1; }
docker info >/dev/null 2>&1 && DOCKER=docker || DOCKER="sudo docker"

set_env() {   # set_env KEY VALUE  (VALUE empty = remove)
  sed -i "/^$1=/d" .env
  [[ -n $2 ]] && echo "$1=$2" >> .env
  return 0
}

if [[ ${1:-} == --disable ]]; then
  set_env RS485_DEVICE ""; set_env COMPOSE_FILE ""
  $DOCKER compose up -d poller
  echo "Serial access removed. Use the Wi-Fi logger option on the setup page."
  exit 0
fi

serial_devices() {   # stable by-id names, else raw tty names
  local d
  for d in /dev/serial/by-id/* /dev/ttyUSB* /dev/ttyACM*; do
    [[ -e $d ]] || continue
    if [[ $d == /dev/tty* ]] && ls -l /dev/serial/by-id/ 2>/dev/null | grep -q "/${d##*/}$"; then
      continue   # already listed under by-id
    fi
    echo "$d"
  done | sort
}

users_of() {   # programs that have the device open, e.g. OctoPrint
  local real pid
  real=$(readlink -f "$1")
  { sudo -n find /proc/[0-9]*/fd -lname "$real" 2>/dev/null
    find /proc/[0-9]*/fd -lname "$real" 2>/dev/null; } | cut -d/ -f3 | sort -u |
  while read -r pid; do
    printf '%s (pid %s); ' "$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null | cut -c1-60)" "$pid"
  done
  return 0
}

echo "This finds your RS485 adapter by comparing the USB devices before and after"
echo "you plug it in. Leave everything else (like the 3D printer) as it is."
echo
read -rp "1. UNPLUG the RS485 adapter, then press Enter " _ </dev/tty
sleep 1; before=$(serial_devices)
read -rp "2. PLUG IN the RS485 adapter, then press Enter " _ </dev/tty
echo "   waiting for it to appear..."
new=""
for _ in $(seq 1 10); do
  sleep 1
  new=$(comm -13 <(echo "$before") <(serial_devices))
  [[ -n $new ]] && break
done

count=$(grep -c . <<<"$new" || true)
if (( count == 0 )); then
  echo "No new serial device appeared. Try another USB port or cable, then run this again."; exit 1
elif (( count > 1 )); then
  echo "More than one new device appeared - unplug other USB devices and run this again:"; echo "$new"; exit 1
fi

dev=$new
inuse=$(users_of "$dev")
if [[ -n $inuse ]]; then
  echo "$dev is already in use by: $inuse"
  echo "That is not a free RS485 adapter. Nothing was changed."; exit 1
fi

echo "Found: $dev -> $(readlink -f "$dev")"
set_env RS485_DEVICE "$dev"
set_env COMPOSE_FILE "docker-compose.yml:docker-compose.rs485.yml"
$DOCKER compose up -d poller
echo
echo "Done. On the setup page choose \"RS485 cable\", then test and save."
echo "Note: the adapter must be plugged in when the Pi starts, or the monitor won't start."
