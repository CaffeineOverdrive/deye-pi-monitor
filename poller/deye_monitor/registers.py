"""Deye single-phase hybrid (SUN-xK-SG0xLP1) Modbus holding-register map.

Addresses follow the community-verified map used by kellerza/sunsynk and
StephanJoubert/home_assistant_solarman (deye_hybrid). Run
``python -m deye_monitor.dump`` on first install and sanity-check the values
against the inverter's LCD before trusting the dashboards.

The poller is read-only: it only ever issues function 0x03 reads.
"""

from dataclasses import dataclass

# Contiguous ranges read per poll as (start, count). Every register below must
# fall inside one of these blocks.
READ_BLOCKS: list[tuple[int, int]] = [
    (59, 54),   # 59..112  running state, daily/total energy, PV strings
    (150, 44),  # 150..193 grid, inverter, load, battery, PV power
]


@dataclass(frozen=True)
class Sensor:
    key: str
    name: str
    regs: tuple[int, ...]       # low word first for 32-bit values
    scale: float = 1.0
    unit: str | None = None
    signed: bool = False
    offset: float = 0.0         # subtracted from the raw value before scaling
    device_class: str | None = None
    state_class: str | None = "measurement"
    icon: str | None = None
    # raw value -> text, for states like the running mode. Home Assistant shows the
    # text; InfluxDB keeps the number.
    options: dict[int, str] | None = None


def _kwh_day(key: str, name: str, reg: int) -> Sensor:
    return Sensor(key, name, (reg,), 0.1, "kWh", device_class="energy",
                  state_class="total_increasing")


def _kwh_total(key: str, name: str, lo: int, hi: int) -> Sensor:
    return Sensor(key, name, (lo, hi), 0.1, "kWh", device_class="energy",
                  state_class="total_increasing")


def _watts(key: str, name: str, reg: int, signed: bool = False) -> Sensor:
    return Sensor(key, name, (reg,), 1, "W", signed=signed, device_class="power")


SENSORS: list[Sensor] = [
    Sensor("running_state", "Running state", (59,), state_class=None,
           icon="mdi:state-machine",
           options={0: "Standby", 1: "Self-check", 2: "Normal", 3: "Alarm", 4: "Fault"}),

    # Daily energy (resets at midnight on the inverter clock)
    _kwh_day("day_battery_charge", "Battery charge today", 70),
    _kwh_day("day_battery_discharge", "Battery discharge today", 71),
    _kwh_day("day_grid_import", "Grid import today", 76),
    _kwh_day("day_grid_export", "Grid export today", 77),
    _kwh_day("day_load_energy", "Load energy today", 84),
    _kwh_day("day_pv_energy", "PV energy today", 108),

    # Lifetime energy (use these for the Home Assistant Energy dashboard)
    _kwh_total("total_battery_charge", "Battery charge total", 72, 73),
    _kwh_total("total_battery_discharge", "Battery discharge total", 74, 75),
    _kwh_total("total_grid_import", "Grid import total", 78, 80),
    _kwh_total("total_grid_export", "Grid export total", 81, 82),
    _kwh_total("total_load_energy", "Load energy total", 85, 86),
    _kwh_total("total_pv_energy", "PV energy total", 96, 97),

    # Temperatures
    Sensor("dc_temperature", "DC transformer temperature", (90,), 0.1, "°C",
           offset=1000, device_class="temperature"),
    Sensor("radiator_temperature", "Radiator temperature", (91,), 0.1, "°C",
           offset=1000, device_class="temperature"),
    Sensor("battery_temperature", "Battery temperature", (182,), 0.1, "°C",
           offset=1000, device_class="temperature"),

    # PV strings
    Sensor("pv1_voltage", "PV1 voltage", (109,), 0.1, "V", device_class="voltage"),
    Sensor("pv1_current", "PV1 current", (110,), 0.1, "A", device_class="current"),
    Sensor("pv2_voltage", "PV2 voltage", (111,), 0.1, "V", device_class="voltage"),
    Sensor("pv2_current", "PV2 current", (112,), 0.1, "A", device_class="current"),
    _watts("pv1_power", "PV1 power", 186),
    _watts("pv2_power", "PV2 power", 187),

    # Grid / inverter / load
    Sensor("grid_voltage", "Grid voltage", (150,), 0.1, "V", device_class="voltage"),
    Sensor("inverter_voltage", "Inverter voltage", (154,), 0.1, "V",
           device_class="voltage"),
    Sensor("grid_frequency", "Grid frequency", (79,), 0.01, "Hz",
           device_class="frequency"),
    _watts("grid_power", "Grid power", 169, signed=True),         # + import, - export
    _watts("grid_ct_power", "Grid CT power", 172, signed=True),
    _watts("inverter_power", "Inverter power", 175, signed=True),
    _watts("load_power", "Load power", 178, signed=True),

    # Battery
    Sensor("battery_voltage", "Battery voltage", (183,), 0.01, "V",
           device_class="voltage"),
    Sensor("battery_soc", "Battery SOC", (184,), 1, "%", device_class="battery"),
    _watts("battery_power", "Battery power", 190, signed=True),   # + discharge, - charge
    Sensor("battery_current", "Battery current", (191,), 0.01, "A", signed=True,
           device_class="current"),
]


def _to_signed16(v: int) -> int:
    return v - 0x10000 if v & 0x8000 else v


def decode(raw: dict[int, int]) -> dict[str, float]:
    """Turn {address: raw_u16} into {sensor_key: value}. Adds pv_power."""
    out: dict[str, float] = {}
    for s in SENSORS:
        if not all(r in raw for r in s.regs):
            continue
        if len(s.regs) == 1:
            v = raw[s.regs[0]]
            if s.signed:
                v = _to_signed16(v)
        else:
            v = raw[s.regs[0]] | (raw[s.regs[1]] << 16)
        value = (v - s.offset) * s.scale
        out[s.key] = round(value, 3)

    if "pv1_power" in out and "pv2_power" in out:
        out["pv_power"] = out["pv1_power"] + out["pv2_power"]
    return out


# Derived sensor so Home Assistant and Grafana see total PV power directly.
DERIVED: list[Sensor] = [_watts("pv_power", "PV power", -1)]


def all_sensors() -> list[Sensor]:
    return SENSORS + DERIVED
