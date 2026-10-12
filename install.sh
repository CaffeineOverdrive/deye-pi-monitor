#!/usr/bin/env bash
# Deye Pi Monitor installer for Raspberry Pi (64-bit Raspberry Pi OS / Debian / Ubuntu).
#
#   curl -fsSL https://raw.githubusercontent.com/CaffeineOverdrive/deye-pi-monitor/main/install.sh | bash
#
# Re-running it updates an existing install and keeps your settings and data.
set -euo pipefail

REPO=${DEYE_MONITOR_REPO:-https://github.com/CaffeineOverdrive/deye-pi-monitor.git}
BRANCH=${DEYE_MONITOR_BRANCH:-main}
DIR=${DEYE_MONITOR_DIR:-$HOME/deye-pi-monitor}

say()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31mError:\033[0m %s\n' "$*" >&2; exit 1; }

[[ $(uname -s) == Linux ]] || fail "This installer is for Linux (Raspberry Pi OS)."
# The userland architecture is what matters for Docker images: a 32-bit OS (e.g. most
# OctoPi images) can run a 64-bit kernel, so uname -m alone would say aarch64.
arch=$(dpkg --print-architecture 2>/dev/null || uname -m)
case $arch in
  arm64|amd64|aarch64|x86_64) ;;
  armhf|armel|armv7l|armv6l) fail "This Pi runs a 32-bit OS ($arch) and InfluxDB needs 64-bit. Use Raspberry Pi OS (64-bit), or OctoPi's 64-bit image, then run this again." ;;
  *) fail "Unsupported architecture: $arch" ;;
esac
[[ $EUID -eq 0 ]] && SUDO="" || SUDO="sudo"
command -v apt-get >/dev/null || fail "apt-get not found - use Raspberry Pi OS, Debian or Ubuntu."

mem_mb=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)
if (( mem_mb < 900 )); then say "Warning: only ${mem_mb} MB RAM. 1 GB or more is recommended."; fi

if pgrep -f octoprint >/dev/null 2>&1; then
  say "OctoPrint is running on this Pi. The monitor won't touch the printer's USB port"
  say "(it has no USB access unless you run ./enable-rs485.sh), but the first install"
  say "builds software for several minutes - don't run it during a print."
  if [[ -r /dev/tty ]]; then
    read -rp "    Press Enter to continue, or Ctrl-C to stop. " _ </dev/tty || true
  fi
fi

say "Installing git and curl (if needed)"
if ! command -v git >/dev/null || ! command -v curl >/dev/null; then
  $SUDO apt-get update -qq && $SUDO apt-get install -y -qq git curl
fi

if ! command -v docker >/dev/null; then
  say "Installing Docker (takes a few minutes)"
  curl -fsSL https://get.docker.com | $SUDO sh
fi
$SUDO systemctl enable --now docker >/dev/null 2>&1 || true
if [[ -n $SUDO ]] && ! id -nG "$USER" | grep -qw docker; then
  $SUDO usermod -aG docker "$USER"
fi
# This shell doesn't have the new group yet, so use sudo for docker here.
docker info >/dev/null 2>&1 && DOCKER=docker || DOCKER="$SUDO docker"
$DOCKER compose version >/dev/null 2>&1 || fail "Docker Compose plugin missing - run: $SUDO apt-get install -y docker-compose-plugin"

if [[ -d $DIR/.git ]]; then
  say "Updating $DIR"
  git -C "$DIR" pull --ff-only
else
  say "Downloading to $DIR"
  git clone --depth 1 -b "$BRANCH" "$REPO" "$DIR"
fi
cd "$DIR"

say "Creating passwords"
DOCKER="$DOCKER" ./setup.sh

say "Building and starting (first run takes 5-10 minutes on a Pi)"
$DOCKER compose up -d --build

say "Waiting for the setup page"
port=$(grep -E '^WEB_PORT=' .env | cut -d= -f2-); port=${port:-8088}
for _ in $(seq 1 60); do
  curl -fs "http://localhost:$port/healthz" >/dev/null && break
  sleep 2
done
curl -fs "http://localhost:$port/healthz" >/dev/null || fail "Setup page didn't start. See: cd $DIR && $DOCKER compose logs poller"

ip=$(hostname -I | awk '{print $1}')
pw=$(grep -E '^ADMIN_PASSWORD=' .env | cut -d= -f2-)
cat <<MSG

  Deye Pi Monitor is running.

  1. Open the setup page:  http://$ip:$port
     Log in as  admin  /  $pw
  2. Pick "Wi-Fi logger" or "RS485 cable", test the connection, and save.
     (RS485: first run  $DIR/enable-rs485.sh  to choose the adapter.)
  3. Dashboard:            http://$ip:$(grep -E '^GRAFANA_PORT=' .env | cut -d= -f2- || echo 3000)

  The password is also in $DIR/.env.
  Update later by running this installer again.

MSG
