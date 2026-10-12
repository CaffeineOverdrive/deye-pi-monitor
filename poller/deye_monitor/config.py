"""Runtime configuration.

Infrastructure settings (InfluxDB, built-in MQTT broker, admin password) come from
the environment. Connection settings are chosen in the web setup page and stored in
SETTINGS_FILE; they override the matching environment variables.
"""

import json
import logging
import os
from dataclasses import asdict, dataclass, field

log = logging.getLogger(__name__)

SETTINGS_FILE = os.environ.get("SETTINGS_FILE", "/data/settings.json")
# The only serial device the container can see: the adapter chosen with enable-rs485.sh
RS485_PATH = "/dev/deye-rs485"
# MQTT_HOST values that mean the optional Mosquitto container (enable-broker.sh)
BUILTIN_HOSTS = ("localhost", "127.0.0.1", "mosquitto")

# Fields the web UI may change and persist.
EDITABLE = (
    "transport", "logger_ip", "logger_serial", "logger_port",
    "serial_port", "baudrate", "slave_id", "poll_seconds",
    "mqtt_host", "mqtt_port", "mqtt_user", "mqtt_password",
)
_INT = {"logger_serial", "logger_port", "baudrate", "slave_id", "mqtt_port"}
_FLOAT = {"poll_seconds"}


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    return v if v not in (None, "") else default


def _int_or_none(v: str | None) -> int | None:
    return int(v) if v else None


@dataclass
class Config:
    # "" means not configured yet - the poller waits for the setup page
    transport: str = field(default_factory=lambda: (_env("DEYE_TRANSPORT", "") or "").lower())
    logger_ip: str | None = field(default_factory=lambda: _env("LOGGER_IP"))
    logger_serial: int | None = field(default_factory=lambda: _int_or_none(_env("LOGGER_SERIAL")))
    logger_port: int = field(default_factory=lambda: int(_env("LOGGER_PORT", "8899")))
    serial_port: str = field(default_factory=lambda: _env("DEYE_SERIAL_PORT", RS485_PATH))
    baudrate: int = field(default_factory=lambda: int(_env("DEYE_BAUDRATE", "9600")))
    slave_id: int = field(default_factory=lambda: int(_env("DEYE_SLAVE_ID", "1")))
    poll_seconds: float = field(default_factory=lambda: float(_env("POLL_SECONDS", "10")))
    device_id: str = field(default_factory=lambda: _env("DEVICE_ID", "deye"))

    influx_url: str | None = field(default_factory=lambda: _env("INFLUX_URL"))
    influx_token: str | None = field(default_factory=lambda: _env("INFLUX_TOKEN"))
    influx_org: str = field(default_factory=lambda: _env("INFLUX_ORG", "home"))
    influx_bucket: str = field(default_factory=lambda: _env("INFLUX_BUCKET", "deye"))

    mqtt_host: str | None = field(default_factory=lambda: _env("MQTT_HOST"))
    mqtt_port: int = field(default_factory=lambda: int(_env("MQTT_PORT", "1883")))
    mqtt_user: str | None = field(default_factory=lambda: _env("MQTT_USER"))
    mqtt_password: str | None = field(default_factory=lambda: _env("MQTT_PASSWORD"))
    mqtt_base_topic: str = field(default_factory=lambda: _env("MQTT_BASE_TOPIC", "deye"))
    ha_discovery_prefix: str = field(default_factory=lambda: _env("HA_DISCOVERY_PREFIX", "homeassistant"))

    admin_password: str | None = field(default_factory=lambda: _env("ADMIN_PASSWORD"))
    web_port: int = field(default_factory=lambda: int(_env("WEB_PORT", "8088")))
    grafana_port: int = field(default_factory=lambda: int(_env("GRAFANA_PORT", "3000")))

    @property
    def configured(self) -> bool:
        if self.transport == "solarman":
            return bool(self.logger_ip and self.logger_serial)
        return self.transport == "rs485" and bool(self.serial_port)

    @property
    def builtin_broker(self) -> bool:
        return self.mqtt_host in BUILTIN_HOSTS

    def editable(self) -> dict:
        return {k: getattr(self, k) for k in EDITABLE}

    def updated(self, changes: dict) -> "Config":
        """Copy with validated changes applied. Raises ValueError on bad input."""
        data = asdict(self)
        defaults = asdict(Config())   # environment values
        changes = dict(changes)
        new_host = str(changes.get("mqtt_host") or "").strip()
        if "mqtt_host" in changes and not new_host:
            # blank broker = back to the default: the built-in one with its own
            # credentials if enabled with enable-broker.sh, otherwise MQTT off
            for k in ("mqtt_host", "mqtt_port", "mqtt_user", "mqtt_password"):
                changes.pop(k, None)
                data[k] = defaults[k]
        elif new_host and new_host != self.mqtt_host:
            # a different broker never inherits the old one's credentials
            for k in ("mqtt_user", "mqtt_password"):
                if not changes.get(k):
                    changes.pop(k, None)
                    data[k] = None
        for k, v in changes.items():
            if k not in EDITABLE:
                continue
            if v in ("", None):
                data[k] = defaults[k]   # blank = default
                continue
            try:
                data[k] = int(v) if k in _INT else float(v) if k in _FLOAT else str(v).strip()
            except ValueError:
                raise ValueError(f"{k.replace('_', ' ')} must be a number") from None
        cfg = Config(**data)
        if cfg.transport not in ("solarman", "rs485"):
            raise ValueError("transport must be solarman or rs485")
        if not 1 <= cfg.slave_id <= 247:
            raise ValueError("Modbus ID must be between 1 and 247")
        if cfg.poll_seconds < 2:
            raise ValueError("poll interval must be at least 2 seconds")
        if not cfg.configured:
            raise ValueError("Wi-Fi logger needs an IP and serial number" if cfg.transport == "solarman"
                             else "choose a serial port")
        return cfg


def load_config(path: str = SETTINGS_FILE) -> Config:
    cfg = Config()
    try:
        with open(path) as f:
            saved = json.load(f)
    except FileNotFoundError:
        return cfg
    except (OSError, ValueError) as e:
        log.error("ignoring unreadable settings file %s: %s", path, e)
        return cfg
    data = asdict(cfg)
    data.update({k: v for k, v in saved.items() if k in EDITABLE})
    return Config(**data)


def save_config(cfg: Config, path: str = SETTINGS_FILE) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w") as f:
        json.dump(cfg.editable(), f, indent=2)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
