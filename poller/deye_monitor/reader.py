"""Read-only access to the inverter's holding registers.

Two transports, same interface:
  RS485Reader    USB-RS485 adapter wired to the inverter (Modbus RTU)
  SolarmanReader the inverter's Solarman Wi-Fi logger over the LAN (V5 protocol, port 8899)
"""

import logging
import queue
import time

from .config import Config
from .registers import READ_BLOCKS

log = logging.getLogger(__name__)


class _Reader:
    errors: tuple[type[BaseException], ...] = (OSError,)
    retries = 3

    def _read(self, start: int, count: int) -> list[int]:
        raise NotImplementedError

    def _reset(self) -> None:
        pass

    def close(self) -> None:
        """Release the port/socket; the next read reopens it."""
        self._reset()

    def read_block(self, start: int, count: int) -> list[int]:
        retries, reason = self.retries, ""
        for attempt in range(1, retries + 1):
            try:
                return self._read(start, count)
            except self.errors as e:
                reason = str(e) or ("no reply" if isinstance(e, queue.Empty) else type(e).__name__)
                log.warning("read %d+%d failed (attempt %d/%d): %s",
                            start, count, attempt, retries, reason)
                self._reset()
                if attempt < retries:
                    time.sleep(0.5 * attempt)
        raise IOError(f"no valid reply from the inverter ({reason})")

    def read_raw(self) -> dict[int, int]:
        raw: dict[int, int] = {}
        for start, count in READ_BLOCKS:
            for i, v in enumerate(self.read_block(start, count)):
                raw[start + i] = v
        return raw


class RS485Reader(_Reader):
    def __init__(self, port: str, slave_id: int = 1, baudrate: int = 9600):
        import minimalmodbus
        import serial

        self.errors = (minimalmodbus.ModbusException, serial.SerialException, OSError)
        self.inst = minimalmodbus.Instrument(port, slave_id)
        self.inst.serial.baudrate = baudrate
        self.inst.serial.bytesize = 8
        self.inst.serial.parity = serial.PARITY_NONE
        self.inst.serial.stopbits = 1
        self.inst.serial.timeout = 1.0
        self.inst.clear_buffers_before_each_transaction = True

    def _read(self, start: int, count: int) -> list[int]:
        if not self.inst.serial.is_open:
            self.inst.serial.open()
        return self.inst.read_registers(start, count, functioncode=3)

    def _reset(self) -> None:
        self.inst.serial.close()


class SolarmanReader(_Reader):
    """Connects lazily and reconnects after any error - loggers drop idle sockets."""

    def __init__(self, host: str, serial_number: int, port: int = 8899, slave_id: int = 1,
                 timeout: float = 10):
        from pysolarmanv5 import NoSocketAvailableError, V5FrameError

        # queue.Empty is how pysolarmanv5 reports "no reply before the timeout"
        self.errors = (V5FrameError, NoSocketAvailableError, OSError, queue.Empty)
        self.host, self.serial_number, self.port, self.slave_id = host, serial_number, port, slave_id
        self.timeout = timeout
        self.client = None

    def _read(self, start: int, count: int) -> list[int]:
        if self.client is None:
            from pysolarmanv5 import PySolarmanV5

            self.client = PySolarmanV5(self.host, self.serial_number, port=self.port,
                                       mb_slave_id=self.slave_id, socket_timeout=self.timeout,
                                       v5_error_correction=True)
        return self.client.read_holding_registers(start, count)

    def _reset(self) -> None:
        if self.client is not None:
            try:
                self.client.disconnect()
            except Exception:
                pass
            self.client = None


def make_reader(cfg: Config, quick: bool = False) -> _Reader:
    """quick: one attempt with a short timeout, for the setup page's test button."""
    if not cfg.transport:
        raise SystemExit("not configured yet - open the setup page on port 8088")
    if cfg.transport == "solarman":
        if not cfg.logger_ip or not cfg.logger_serial:
            raise SystemExit("DEYE_TRANSPORT=solarman needs LOGGER_IP and LOGGER_SERIAL")
        reader = SolarmanReader(cfg.logger_ip, cfg.logger_serial, cfg.logger_port, cfg.slave_id,
                                timeout=5 if quick else 10)
    elif cfg.transport == "rs485":
        reader = RS485Reader(cfg.serial_port, cfg.slave_id, cfg.baudrate)
    else:
        raise SystemExit(f"unknown DEYE_TRANSPORT {cfg.transport!r} (use solarman or rs485)")
    if quick:
        reader.retries = 1
    return reader
