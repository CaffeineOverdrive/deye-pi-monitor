"""Read-only Modbus RTU access to the inverter over a USB-RS485 adapter."""

import logging
import time

import minimalmodbus
import serial

from .registers import READ_BLOCKS

log = logging.getLogger(__name__)


class DeyeReader:
    def __init__(self, port: str, slave_id: int = 1, baudrate: int = 9600):
        self.inst = minimalmodbus.Instrument(port, slave_id)
        self.inst.serial.baudrate = baudrate
        self.inst.serial.bytesize = 8
        self.inst.serial.parity = serial.PARITY_NONE
        self.inst.serial.stopbits = 1
        self.inst.serial.timeout = 1.0
        self.inst.clear_buffers_before_each_transaction = True

    def read_block(self, start: int, count: int, retries: int = 3) -> list[int]:
        for attempt in range(1, retries + 1):
            try:
                return self.inst.read_registers(start, count, functioncode=3)
            except (minimalmodbus.ModbusException, serial.SerialException, OSError) as e:
                log.warning("read %d+%d failed (attempt %d/%d): %s",
                            start, count, attempt, retries, e)
                time.sleep(0.5 * attempt)
        raise IOError(f"read of registers {start}..{start + count - 1} failed")

    def read_raw(self) -> dict[int, int]:
        raw: dict[int, int] = {}
        for start, count in READ_BLOCKS:
            for i, v in enumerate(self.read_block(start, count)):
                raw[start + i] = v
        return raw
