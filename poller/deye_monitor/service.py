"""Background poll loop that the web app can reconfigure while running."""

import logging
import threading
import time

from .config import Config
from .reader import make_reader
from .registers import decode
from .sinks import InfluxSink, MqttSink

log = logging.getLogger(__name__)


class Poller:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.io_lock = threading.Lock()   # one conversation with the inverter at a time
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._reload = True
        self._reader = None
        self._sinks: list = []
        self._mqtt: MqttSink | None = None
        self.values: dict[str, float] = {}
        self.last_ok: float | None = None
        self.last_error: str | None = None
        self.failures = 0
        self._thread = threading.Thread(target=self._run, name="poller", daemon=True)

    # --- control -----------------------------------------------------------

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        self._thread.join(timeout=10)
        self._close()

    def apply(self, cfg: Config) -> None:
        """Switch to new settings on the next loop iteration."""
        self.cfg = cfg
        self.values, self.last_ok, self.last_error, self.failures = {}, None, None, 0
        self._reload = True
        self._wake.set()

    def status(self) -> dict:
        state = ("not_configured" if not self.cfg.configured
                 else "ok" if self.last_ok and self.failures == 0
                 else "connecting" if self.last_error is None
                 else "error")
        return {
            "state": state,
            "last_ok": self.last_ok,
            "last_error": self.last_error,
            "failures": self.failures,
            "values": self.values,
            "mqtt_connected": bool(self._mqtt and self._mqtt.connected),
            "mqtt_error": self._mqtt.error if self._mqtt else None,
        }

    def test(self, cfg: Config) -> dict[str, float]:
        """One-off read with candidate settings; pauses the loop while it runs."""
        reader = make_reader(cfg, quick=True)
        try:
            with self.io_lock:
                if self._reader is not None:
                    self._reader.close()   # free the port/socket for the test
                return decode(reader.read_raw())
        finally:
            reader.close()

    # --- loop ----------------------------------------------------------------

    def _close(self) -> None:
        if self._reader is not None:
            self._reader.close()
        if self._mqtt is not None:
            self._mqtt.close()
        self._reader, self._mqtt, self._sinks = None, None, []

    def _build(self) -> None:
        self._close()
        cfg = self.cfg
        if not cfg.configured:
            log.info("waiting for setup on port %s", cfg.web_port)
            return
        self._reader = make_reader(cfg)
        if cfg.influx_url and cfg.influx_token:
            self._sinks.append(InfluxSink(cfg))
        if cfg.mqtt_host:
            self._mqtt = MqttSink(cfg)
            self._sinks.append(self._mqtt)
        log.info("polling via %s every %ss", cfg.transport, cfg.poll_seconds)

    def _run(self) -> None:
        while not self._stop.is_set():
            if self._reload:
                self._reload = False
                try:
                    self._build()
                except Exception as e:  # e.g. adapter unplugged - retry next cycle
                    log.error("could not start polling: %s", e)
                    self._close()
                    self.last_error, self.failures = str(e), self.failures + 1
                    self._reload = True
            started = time.monotonic()
            if self._reader is not None:
                self._poll_once()
            delay = self.cfg.poll_seconds if self.cfg.configured else 3600
            self._wake.wait(max(0.0, delay - (time.monotonic() - started)))
            self._wake.clear()
        log.info("poller stopped")

    def _poll_once(self) -> None:
        try:
            with self.io_lock:
                values = decode(self._reader.read_raw())
        except Exception as e:   # never let one bad poll kill the thread
            self.failures += 1
            self.last_error = str(e)
            log.error("inverter read failed (%d in a row): %s", self.failures, e)
            if self._mqtt and self.failures == 3:
                self._mqtt.mark_offline()
            return
        self.values, self.last_ok, self.failures, self.last_error = values, time.time(), 0, None
        for sink in self._sinks:
            try:
                sink.write(values)
            except Exception:
                log.exception("sink %s failed", type(sink).__name__)
