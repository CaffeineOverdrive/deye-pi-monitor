"""Outputs: InfluxDB (local history for Grafana) and MQTT (Home Assistant)."""

import json
import logging

from .config import Config
from .registers import Sensor, all_sensors

log = logging.getLogger(__name__)


class InfluxSink:
    def __init__(self, cfg: Config):
        from influxdb_client import InfluxDBClient
        from influxdb_client.client.write_api import SYNCHRONOUS

        self.cfg = cfg
        self.client = InfluxDBClient(url=cfg.influx_url, token=cfg.influx_token, org=cfg.influx_org)
        self.write_api = self.client.write_api(write_options=SYNCHRONOUS)

    def write(self, values: dict[str, float]) -> None:
        from influxdb_client import Point

        p = Point("inverter").tag("device", self.cfg.device_id)
        for k, v in values.items():
            p = p.field(k, float(v))
        self.write_api.write(bucket=self.cfg.influx_bucket, record=p)


def discovery_payload(s: Sensor, cfg: Config) -> dict:
    base = f"{cfg.mqtt_base_topic}/{cfg.device_id}"
    payload = {
        "name": s.name,
        "unique_id": f"{cfg.device_id}_{s.key}",
        "object_id": f"{cfg.device_id}_{s.key}",
        "state_topic": f"{base}/state",
        "value_template": f"{{{{ value_json.{s.key} }}}}",
        "availability_topic": f"{base}/status",
        "device": {
            "identifiers": [cfg.device_id],
            "name": "Deye inverter",
            "manufacturer": "Deye",
            "model": "SUN-SG LP1 hybrid",
        },
    }
    if s.unit:
        payload["unit_of_measurement"] = s.unit
    if s.device_class:
        payload["device_class"] = s.device_class
    if s.state_class:
        payload["state_class"] = s.state_class
    if s.icon:
        payload["icon"] = s.icon
    return payload


class MqttSink:
    def __init__(self, cfg: Config):
        import paho.mqtt.client as mqtt

        self.cfg = cfg
        self.base = f"{cfg.mqtt_base_topic}/{cfg.device_id}"
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                  client_id=f"deye-monitor-{cfg.device_id}")
        if cfg.mqtt_user:
            self.client.username_pw_set(cfg.mqtt_user, cfg.mqtt_password)
        self.client.will_set(f"{self.base}/status", "offline", retain=True)
        self.connected = False
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.connect_async(cfg.mqtt_host, cfg.mqtt_port, keepalive=60)
        self.client.loop_start()

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            log.error("MQTT connect failed: %s", reason_code)
            return
        log.info("MQTT connected to %s:%s", self.cfg.mqtt_host, self.cfg.mqtt_port)
        for s in all_sensors():
            topic = f"{self.cfg.ha_discovery_prefix}/sensor/{self.cfg.device_id}/{s.key}/config"
            client.publish(topic, json.dumps(discovery_payload(s, self.cfg)), retain=True)
        client.publish(f"{self.base}/status", "online", retain=True)
        self.connected = True

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        self.connected = False

    def write(self, values: dict[str, float]) -> None:
        self.client.publish(f"{self.base}/state", json.dumps(values))

    def mark_offline(self) -> None:
        self.client.publish(f"{self.base}/status", "offline", retain=True)

    def close(self) -> None:
        self.mark_offline()
        self.client.disconnect()
        self.client.loop_stop()
