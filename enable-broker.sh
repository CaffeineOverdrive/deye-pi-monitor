#!/usr/bin/env bash
# Run an MQTT broker (Mosquitto) on this Pi for Home Assistant. Only needed when
# Home Assistant has no broker of its own: its Mosquitto add-on is the usual choice,
# and the setup page finds that one.
#
#   ./enable-broker.sh            start the built-in broker and send data to it
#   ./enable-broker.sh --disable  stop it again (MQTT off, or use another broker)
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
  $DOCKER compose --profile broker rm -sf mosquitto
  set_env COMPOSE_PROFILES ""; set_env MQTT_HOST ""
  rm -f mosquitto/config/passwd
  $DOCKER compose up -d poller
  echo "Built-in broker stopped. Choose another broker on the setup page, or leave MQTT off."
  exit 0
fi

set_env COMPOSE_PROFILES broker; set_env MQTT_HOST localhost
DOCKER="$DOCKER" ./setup.sh
$DOCKER compose up -d
port=$(grep -E '^MQTT_PORT=' .env | cut -d= -f2-)
echo
echo "Built-in broker running on port $port. On the setup page, leave the broker host"
echo "blank (or pick \"Built-in broker\" under Find broker) and save; the page then shows"
echo "what to enter in Home Assistant."
