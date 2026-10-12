#!/usr/bin/env bash
# Create .env with random secrets, and the MQTT password file when the built-in broker
# is enabled. Safe to re-run: an existing .env is kept. Called by install.sh and
# enable-broker.sh.
set -euo pipefail
cd "$(dirname "$0")"
DOCKER=${DOCKER:-docker}

rand() { head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n' | cut -c1-"$1"; }

in_use() {   # anything LISTENing on this TCP port (IPv4 or IPv6)?
  awk -v p=":$(printf '%04X' "$1")" '$4 == "0A" && substr($2, length($2) - 4) == p { f = 1 }
       END { exit !f }' $(ls /proc/net/tcp /proc/net/tcp6 2>/dev/null)
}

free_port() {   # free_port KEY: move the port in .env up until nothing uses it
  local port orig
  port=$(grep -E "^$1=" .env | cut -d= -f2)
  orig=$port
  while in_use "$port"; do port=$((port + 1)); done
  if [[ $port != "$orig" ]]; then
    sed -i "s/^$1=.*/$1=$port/" .env
    echo "Port $orig is already in use on this Pi - using $port for $1."
  fi
}

if [[ ! -f .env ]]; then
  sed -e "s/^ADMIN_PASSWORD=.*/ADMIN_PASSWORD=$(rand 12)/" \
      -e "s/^MQTT_PASSWORD=.*/MQTT_PASSWORD=$(rand 16)/" \
      -e "s/^INFLUX_TOKEN=.*/INFLUX_TOKEN=$(rand 64)/" \
      -e "s/^INFLUX_ADMIN_PASSWORD=.*/INFLUX_ADMIN_PASSWORD=$(rand 20)/" \
      .env.example > .env
  chmod 600 .env
  echo "Created .env with random passwords."

  # Move any default port that something else on this Pi already uses.
  for key in WEB_PORT GRAFANA_PORT INFLUX_PORT; do free_port "$key"; done
elif [[ -f mosquitto/config/passwd ]] && ! grep -qE '^(COMPOSE_PROFILES|MQTT_HOST)=' .env; then
  # Installed before the broker became optional: keep the built-in broker running,
  # so Home Assistant keeps receiving data after this update.
  printf 'COMPOSE_PROFILES=broker\nMQTT_HOST=localhost\n' >> .env
  echo "Kept the built-in MQTT broker from your earlier install."
fi

grep -qE '^COMPOSE_PROFILES=.*broker' .env || exit 0

# Built-in broker: on first enable, make sure its port is free
if [[ ! -f mosquitto/config/passwd ]]; then free_port MQTT_PORT; fi
MQTT_USER=$(grep -E '^MQTT_USER=' .env | cut -d= -f2-)
MQTT_PASSWORD=$(grep -E '^MQTT_PASSWORD=' .env | cut -d= -f2-)
$DOCKER run --rm -v "$PWD/mosquitto/config:/mosquitto/config" eclipse-mosquitto:2.0.18 sh -c \
  "rm -f /mosquitto/config/passwd && touch /mosquitto/config/passwd && chmod 0700 /mosquitto/config/passwd && \
   mosquitto_passwd -b /mosquitto/config/passwd '$MQTT_USER' '$MQTT_PASSWORD'"
echo "MQTT user '$MQTT_USER' ready."
