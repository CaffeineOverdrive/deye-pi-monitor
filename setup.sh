#!/usr/bin/env bash
# Create .env with random secrets and the MQTT password file. Safe to re-run:
# an existing .env is kept. Called by install.sh.
set -euo pipefail
cd "$(dirname "$0")"
DOCKER=${DOCKER:-docker}

rand() { head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n' | cut -c1-"$1"; }

if [[ ! -f .env ]]; then
  sed -e "s/^ADMIN_PASSWORD=.*/ADMIN_PASSWORD=$(rand 12)/" \
      -e "s/^MQTT_PASSWORD=.*/MQTT_PASSWORD=$(rand 16)/" \
      -e "s/^INFLUX_TOKEN=.*/INFLUX_TOKEN=$(rand 64)/" \
      -e "s/^INFLUX_ADMIN_PASSWORD=.*/INFLUX_ADMIN_PASSWORD=$(rand 20)/" \
      .env.example > .env
  chmod 600 .env
  echo "Created .env with random passwords."

  # Move any default port that something else on this Pi already uses.
  in_use() {   # anything LISTENing on this TCP port (IPv4 or IPv6)?
    awk -v p=":$(printf '%04X' "$1")" '$4 == "0A" && substr($2, length($2) - 4) == p { f = 1 }
         END { exit !f }' $(ls /proc/net/tcp /proc/net/tcp6 2>/dev/null)
  }
  for key in WEB_PORT GRAFANA_PORT MQTT_PORT INFLUX_PORT; do
    port=$(grep -E "^$key=" .env | cut -d= -f2)
    orig=$port
    while in_use "$port"; do port=$((port + 1)); done
    if [[ $port != "$orig" ]]; then
      sed -i "s/^$key=.*/$key=$port/" .env
      echo "Port $orig is already in use on this Pi - using $port for $key."
    fi
  done
fi

MQTT_USER=$(grep -E '^MQTT_USER=' .env | cut -d= -f2-)
MQTT_PASSWORD=$(grep -E '^MQTT_PASSWORD=' .env | cut -d= -f2-)
$DOCKER run --rm -v "$PWD/mosquitto/config:/mosquitto/config" eclipse-mosquitto:2.0.18 sh -c \
  "rm -f /mosquitto/config/passwd && touch /mosquitto/config/passwd && chmod 0700 /mosquitto/config/passwd && \
   mosquitto_passwd -b /mosquitto/config/passwd '$MQTT_USER' '$MQTT_PASSWORD'"
echo "MQTT user '$MQTT_USER' ready."
