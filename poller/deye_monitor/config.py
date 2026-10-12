import os
from dataclasses import dataclass, field


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    return v if v not in (None, "") else default


@dataclass
class Config:
    serial_port: str = field(default_factory=lambda: _env("DEYE_SERIAL_PORT", "/dev/ttyUSB0"))
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
