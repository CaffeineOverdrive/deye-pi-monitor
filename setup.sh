#!/usr/bin/env bash
# First-time setup on the Pi: create .env with random secrets and the MQTT password file.
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -f .env ]]; then
  rand() { openssl rand -hex 16; }
  sed -e "s/^INFLUX_TOKEN=.*/INFLUX_TOKEN=$(openssl rand -hex 32)/" \
      -e "s/^INFLUX_ADMIN_PASSWORD=.*/INFLUX_ADMIN_PASSWORD=$(rand)/" \
      -e "s/^GRAFANA_ADMIN_PASSWORD=.*/GRAFANA_ADMIN_PASSWORD=$(rand)/" \
      -e "s/^MQTT_PASSWORD=.*/MQTT_PASSWORD=$(rand)/" \
      .env.example > .env
  chmod 600 .env
  echo "Created .env with random secrets."
fi

by_id=$(ls /dev/serial/by-id/ 2>/dev/null | head -n1 || true)
if [[ -n "$by_id" ]] && grep -q '^DEYE_SERIAL_DEVICE=/dev/ttyUSB0$' .env; then
  sed -i "s#^DEYE_SERIAL_DEVICE=.*#DEYE_SERIAL_DEVICE=/dev/serial/by-id/$by_id#" .env
  echo "Using serial adapter /dev/serial/by-id/$by_id"
fi

set -a; source .env; set +a
touch mosquitto/config/passwd
docker run --rm -v "$PWD/mosquitto/config:/mosquitto/config" eclipse-mosquitto:2.0.18 \
  sh -c "mosquitto_passwd -b /mosquitto/config/passwd '$MQTT_USER' '$MQTT_PASSWORD' && chmod 0700 /mosquitto/config/passwd && chown root:root /mosquitto/config/passwd"
echo "MQTT user '$MQTT_USER' written."

echo
echo "Next:  docker compose run --rm poller python -m deye_monitor.dump   # check readings"
echo "Then:  docker compose up -d --build"
echo "Grafana: http://$(hostname -I | awk '{print $1}'):3000  (admin / GRAFANA_ADMIN_PASSWORD in .env)"
