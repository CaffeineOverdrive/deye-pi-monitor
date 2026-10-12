"""Print decoded values and raw registers once - use to verify wiring and the map.

    docker compose run --rm poller python -m deye_monitor.dump
"""

from .config import Config
from .reader import DeyeReader
from .registers import SENSORS, decode


def main() -> None:
    cfg = Config()
    raw = DeyeReader(cfg.serial_port, cfg.slave_id, cfg.baudrate).read_raw()
    values = decode(raw)
    for s in SENSORS:
        regs = ",".join(f"{r}={raw.get(r)}" for r in s.regs)
        print(f"{s.name:30} {values.get(s.key)!s:>10} {s.unit or '':4}  [{regs}]")
    print(f"{'PV power':30} {values.get('pv_power')!s:>10} W")


if __name__ == "__main__":
    main()
