"""Poll loop: read inverter -> InfluxDB + MQTT."""

import logging
import signal
import time

from .config import Config
from .reader import DeyeReader
from .registers import decode
from .sinks import InfluxSink, MqttSink

log = logging.getLogger("deye_monitor")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = Config()
    reader = DeyeReader(cfg.serial_port, cfg.slave_id, cfg.baudrate)

    sinks = []
    if cfg.influx_url and cfg.influx_token:
        sinks.append(InfluxSink(cfg))
    mqtt = MqttSink(cfg) if cfg.mqtt_host else None
    if mqtt:
        sinks.append(mqtt)
    if not sinks:
        log.warning("No InfluxDB or MQTT configured - values will only be logged")

    stop = False

    def _stop(*_):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    failures = 0
    while not stop:
        started = time.monotonic()
        try:
            values = decode(reader.read_raw())
            failures = 0
            log.debug("%s", values)
            for sink in sinks:
                try:
                    sink.write(values)
                except Exception:
                    log.exception("sink %s failed", type(sink).__name__)
        except IOError as e:
            failures += 1
            log.error("inverter read failed (%d in a row): %s", failures, e)
            if mqtt and failures == 3:
                mqtt.mark_offline()
        time.sleep(max(0.0, cfg.poll_seconds - (time.monotonic() - started)))

    if mqtt:
        mqtt.mark_offline()


if __name__ == "__main__":
    main()
