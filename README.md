# Deye Pi Monitor

Monitor a Deye single-phase hybrid inverter (SUN-xK-SG0xLP1) from a Raspberry Pi:
history on the Pi, a Grafana dashboard, and live data in Home Assistant.

```
Deye ─┬─ Wi-Fi logger (Solarman stick) ──LAN──┐
      └─ or RS485 cable + USB adapter ────────┤
                                              ▼
                                Raspberry Pi
                                 ├─ setup page   http://<pi>:8088
                                 ├─ InfluxDB     history on the Pi
                                 └─ Grafana      dashboard  http://<pi>:3000
                                              │
                                              ▼  MQTT (optional)
                      Home Assistant's broker, or a built-in one on the Pi
                      → Home Assistant (auto-discovered)
```

It only ever *reads* from the inverter and never changes its settings.

## Install

You need a Raspberry Pi 3, 4 or 5 running a **64-bit** OS: Raspberry Pi OS (64-bit), or
OctoPi's 64-bit image. Check with `dpkg --print-architecture`; it must say `arm64`. The
stack uses about 200 MB of RAM. On the Pi, run:

```bash
curl -fsSL https://raw.githubusercontent.com/CaffeineOverdrive/deye-pi-monitor/main/install.sh | bash
```

This installs Docker if needed, downloads the project to `~/deye-pi-monitor`, creates
random passwords and starts everything. The first run takes 5–10 minutes. At the end it
prints the setup page address and the admin password.

### Sharing a Pi with OctoPrint or other projects

- The monitor has **no access to USB devices** unless you run `enable-rs485.sh`. Even
  then it gets only the adapter you identify, never the printer.
- Its containers run at low CPU priority, so the printer host gets the CPU first.
  Install or update when the printer is idle: the first build takes a few minutes of CPU.
- Any default port already in use is moved automatically, so it won't clash with
  OctoPi's webcam on 8080 or nginx on 8088.
- It doesn't run its own MQTT broker unless you ask it to (see step 3 below).

## Set up

Open `http://<pi-ip>:8088` (the installer prints the exact address) and log in as `admin` with the password the installer printed.
It's also stored in `~/deye-pi-monitor/.env`.

1. **Choose how the inverter is connected.**
   - **Wi-Fi logger:** the Solarman stick that came with the inverter. Press **Find my
     logger** and the Pi searches your network. If nothing is found, type in the logger's
     IP address and the serial number from the sticker on the stick (not the inverter's
     serial). Give the logger a fixed IP in your router so the address doesn't change.
   - **RS485 cable:** see [Wiring](#rs485-wiring). For safety the monitor can't see any
     USB devices until you choose one: on the Pi run `~/deye-pi-monitor/enable-rs485.sh`.
     It asks you to unplug and re-plug the adapter, so it can never pick a 3D printer or
     anything else, then press **Refresh** on the setup page.
2. Press **Test connection**. You should see PV, load and battery readings that match
   the inverter's screen. Then press **Save and start**.
3. **Home Assistant (optional):** live data reaches Home Assistant through an MQTT
   broker. MQTT stays off until you choose one.
   - **Home Assistant with the Mosquitto broker add-on (usual):** press **Find broker**.
     The Pi looks for Home Assistant on your network and checks for a broker on it.
     Pick it, enter a broker login, press **Test broker**, then **Save**.
     For the login, add one to the add-on itself under **Settings → Add-ons →
     Mosquitto broker → Configuration → Logins** (e.g. `deye-monitor`) and restart
     the add-on. Don't use a Home Assistant person's login: that also works for the
     Home Assistant app and could control your home if this Pi were compromised.
   - **No broker in Home Assistant:** install its Mosquitto broker add-on, or run
     `~/deye-pi-monitor/enable-broker.sh` to start one on the Pi. The page then shows
     what to enter under **Settings → Devices & services → Add integration → MQTT**.

   Either way a **Deye inverter** device then appears in Home Assistant automatically.

For the HA **Energy** dashboard use *Grid import total*, *Grid export total*,
*PV energy total* and *Battery charge total* / *Battery discharge total*.

## Dashboard

`http://<pi-ip>:3000`. Anyone on your home network can view it; log in as `admin` to edit.

- **Now:** PV, load, battery SOC, battery power, grid power, inverter temperature.
- **Today:** PV, load, grid import and export (kWh), **self-sufficiency** (share of
  load not bought from the grid) and **PV self-consumption** (share of PV not exported).
- **Power flow** over time, battery SOC, the two PV strings, and **daily energy for the
  last 30 days**.

Day boundaries use `Africa/Johannesburg`. To change that or the layout, edit
`tools/build_dashboard.py`, run it, and `docker compose restart grafana`.

## RS485 wiring

Use a USB-to-RS485 adapter (CH340 or FTDI) and the inverter's **RS485 / Modbus** RJ45
port: not the BMS (battery) port and not the meter port. The Wi-Fi logger can stay
plugged in.

| RJ45 pin (SG04LP1 RS485 port) | Adapter |
|---|---|
| 1 | B− |
| 2 | A+ |

Pinouts differ between hardware revisions, so check the inverter manual. Swapping A
and B is harmless: if the test fails, swap them and try again. The inverter's
"Modbus SN" (Advanced settings) must match the Modbus ID on the setup page (default 1).

## Everyday commands

Run these in `~/deye-pi-monitor`:

| | |
|---|---|
| Update | run the install command again (keeps settings, passwords and history) |
| Logs | `docker compose logs -f poller` |
| Raw register dump | `docker compose exec poller python -m deye_monitor.dump` |
| Restart | `docker compose restart` |
| Stop using RS485 | `./enable-rs485.sh --disable` |
| Built-in MQTT broker on / off | `./enable-broker.sh` / `./enable-broker.sh --disable` |
| Uninstall, keeping data | `docker compose down` |
| Uninstall, deleting data | `docker compose down -v && cd .. && rm -rf deye-pi-monitor` |

Back up history with
`docker compose exec influxdb influx backup /var/lib/influxdb2/backup -t <INFLUX_TOKEN from .env>`.

## Troubleshooting

- **"Find broker" finds nothing:** it relies on Home Assistant announcing itself on the
  network (mDNS), which some routers block between Wi-Fi and wired clients. Type the
  Home Assistant IP into **Broker host** and press **Test broker**.

- **"Find my logger" finds nothing:** the Pi and the logger must be on the same network,
  and some routers block broadcast between Wi-Fi and wired clients. Enter the IP by hand:
  it's on the router's client list, often named after the logger's MAC address.
- **Test says "no valid reply":** for Wi-Fi, check the serial number is the *logger's*
  (10 digits, on the stick). For RS485, swap A/B and check the Modbus ID.
- **RS485: monitor won't start after a reboot:** the adapter must be plugged in at boot.
  Plug it in and run `docker compose up -d`, or run `./enable-rs485.sh --disable`.
- **Values look wrong:** `dump` prints each raw register next to its decoded value.
  The register map is in `poller/deye_monitor/registers.py` and follows the community map
  used by kellerza/sunsynk. Sign conventions: battery power is **+ discharge / − charge**,
  grid power is **+ import / − export**.

## Development

```bash
cd poller && pip install -r requirements.txt && python -m unittest discover -s tests
```

`install.sh` honours `DEYE_MONITOR_REPO`, `DEYE_MONITOR_BRANCH` and `DEYE_MONITOR_DIR`
for testing forks and branches.
