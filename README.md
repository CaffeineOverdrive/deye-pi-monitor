# deye-pi-monitor

Raspberry Pi 5 monitor for a Deye single-phase hybrid inverter (SUN-xK-SG0xLP1).

```
Deye ──RS485──► USB adapter ──► Pi 5
                                 ├─ poller      reads Modbus every 10 s (read-only)
                                 ├─ InfluxDB    stores the history on the Pi
                                 ├─ Grafana     dashboards  → http://<pi>:3000
                                 └─ Mosquitto   MQTT broker → Home Assistant (auto-discovered)
```

The poller only issues Modbus *read* requests (function 0x03). It never writes
settings to the inverter.

## Hardware

- Raspberry Pi 5 (2 GB is plenty — the whole stack uses about 200 MB of RAM) with a
  good SD card or, better, an NVMe/USB SSD.
- USB-to-RS485 adapter (CH340 or FTDI based, with A/B screw terminals).
- A length of CAT5/6 cable with an RJ45 plug on the inverter end.

### Wiring

Use the inverter's **RS485 / Modbus** RJ45 port — not the BMS (battery) port and
not the meter port. The Wi-Fi logger stick can stay plugged in; it uses its own port.

| RJ45 pin (Deye SG04LP1 RS485 port) | Adapter |
|---|---|
| 1 | B− |
| 2 | A+ |

Pinouts differ between hardware revisions, so check your inverter's manual. Swapping
A and B is harmless; if `dump` below gets timeouts, swap the two wires and try again.
Defaults: slave ID 1, 9600 baud, 8N1 (the "Modbus SN" setting on the inverter
display, under Advanced settings, must match `DEYE_SLAVE_ID`).

## Install on the Pi

```bash
# Raspberry Pi OS Lite 64-bit (Bookworm), then:
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER   # log out and back in

git clone <this repo> deye-pi-monitor && cd deye-pi-monitor
./setup.sh                      # writes .env with random secrets + MQTT user

# 1. Check the readings against the inverter's LCD before going further
docker compose run --rm poller python -m deye_monitor.dump

# 2. Start everything
docker compose up -d --build
```

Grafana: `http://<pi-ip>:3000`. Log in as `admin` with `GRAFANA_ADMIN_PASSWORD`
from `.env`. The "Deye inverter" dashboard is the home page.

## Dashboard

- **Now:** PV, load, battery SOC, battery power, grid power, inverter temperature.
- **Today:** PV, load, grid import and export (kWh), **self-sufficiency** (share of
  load not bought from the grid) and **PV self-consumption** (share of PV not exported).
- **Power flow** over time: PV, load, battery (+ discharge / − charge), grid (+ import / − export).
- Battery SOC, the two PV strings, and **daily energy bars for the last 30 days**.

To change the dashboard, edit `tools/build_dashboard.py`, run it, and
`docker compose restart grafana`. Day boundaries use `Africa/Johannesburg`; change
`TZ` at the top of that file if needed.

## Home Assistant

1. In HA: **Settings → Devices & services → Add integration → MQTT**.
   Broker = Pi IP, port 1883, username/password = `MQTT_USER` / `MQTT_PASSWORD` from `.env`.
2. A **Deye inverter** device appears with all the sensors (MQTT discovery). It shows
   *unavailable* if the poller stops or loses the inverter.
3. **Settings → Dashboards → Energy:**
   - Grid consumption → `Grid import total`
   - Return to grid → `Grid export total`
   - Solar production → `PV energy total`
   - Home battery → `Battery charge total` / `Battery discharge total`

Topics: state is JSON on `deye/<DEVICE_ID>/state`, availability on
`deye/<DEVICE_ID>/status`, discovery under `homeassistant/sensor/<DEVICE_ID>/…`.

## Configuration (`.env`)

| Variable | Default | |
|---|---|---|
| `DEYE_SERIAL_DEVICE` | `/dev/ttyUSB0` | `setup.sh` switches this to the stable `/dev/serial/by-id/…` path |
| `DEYE_SLAVE_ID` | `1` | Must match the inverter's Modbus SN |
| `POLL_SECONDS` | `10` | |
| `DEVICE_ID` | `deye` | Used in MQTT topics and HA entity IDs |

## Register map

`poller/deye_monitor/registers.py` follows the community map used by
kellerza/sunsynk and home_assistant_solarman. Sign conventions: battery power is
**+ discharge / − charge** and grid power is **+ import / − export**. If a value looks
wrong on your firmware, `dump` prints the raw register next to each decoded value.

## Development

```bash
cd poller && python -m unittest discover -s tests
```

## Maintenance

- Back up InfluxDB: `docker compose exec influxdb influx backup /var/lib/influxdb2/backup -t $INFLUX_TOKEN`.
  A 10 s poll stores well under 1 GB a year.
- Update: `git pull && docker compose up -d --build`.
- Logs: `docker compose logs -f poller`.
