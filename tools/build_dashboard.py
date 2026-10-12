"""Generate grafana/dashboards/deye.json.  Run: python tools/build_dashboard.py

Entity colours use a fixed CVD-validated categorical order and stay the same
on every panel: PV, Load, Battery, Grid import, Grid export.
"""

import json
from pathlib import Path

TZ = "Africa/Johannesburg"   # day boundaries for the daily-energy bars
KWH = "suffix: kWh"   # fixed unit; Grafana's kwatth auto-scales to Wh
DS = {"type": "influxdb", "uid": "influx-deye"}

COLOR = {
    "pv": "#3987e5",       # slot 1 blue
    "load": "#d95926",     # slot 2 orange
    "battery": "#199e70",  # slot 3 aqua
    "grid": "#c98500",     # slot 4 yellow (grid import)
    "export": "#d55181",   # slot 5 magenta
}


def flux(field: str, fn: str = "mean", window: str = "v.windowPeriod") -> str:
    return (
        'from(bucket: v.defaultBucket)\n'
        f'  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n'
        f'  |> filter(fn: (r) => r._measurement == "inverter" and r._field == "{field}")\n'
        f'  |> aggregateWindow(every: {window}, fn: {fn}, createEmpty: false, timeSrc: "_start")\n'
        f'  |> keep(columns: ["_time", "_value"])'
    )


def last_today(field: str) -> str:
    return (
        'from(bucket: v.defaultBucket)\n'
        '  |> range(start: -1h)\n'
        f'  |> filter(fn: (r) => r._measurement == "inverter" and r._field == "{field}")\n'
        '  |> last()\n  |> keep(columns: ["_time", "_value"])'
    )


def ratio_today(num_total: str, minus: str, label: str) -> str:
    # 100 * (total - minus) / total, from today's counters
    return (
        'from(bucket: v.defaultBucket)\n'
        '  |> range(start: -1h)\n'
        f'  |> filter(fn: (r) => r._measurement == "inverter" and (r._field == "{num_total}" or r._field == "{minus}"))\n'
        '  |> last()\n  |> group()\n'
        '  |> pivot(rowKey: ["_measurement"], columnKey: ["_field"], valueColumn: "_value")\n'
        f'  |> map(fn: (r) => ({{_time: r._time, "{label}": if r.{num_total} > 0.0 '
        f'then 100.0 * (r.{num_total} - r.{minus}) / r.{num_total} else 0.0}}))'
    )


def target(ref: str, query: str) -> dict:
    return {"refId": ref, "datasource": DS, "query": query}


def override(ref: str, name: str, color: str | None = None) -> dict:
    props = [{"id": "displayName", "value": name}]
    if color:
        props.append({"id": "color", "value": {"mode": "fixed", "fixedColor": color}})
    return {"matcher": {"id": "byFrameRefID", "options": ref}, "properties": props}


_id = 0


def panel(kind: str, title: str, grid: tuple[int, int, int, int], targets, **extra) -> dict:
    global _id
    _id += 1
    x, y, w, h = grid
    p = {"id": _id, "type": kind, "title": title, "datasource": DS,
         "gridPos": {"x": x, "y": y, "w": w, "h": h}, "targets": targets}
    p.update(extra)
    return p


def stat(title, grid, field, unit, decimals=0, query=None, minmax=None):
    defaults = {"unit": unit, "decimals": decimals, "color": {"mode": "fixed", "fixedColor": "text"}}
    if minmax:
        defaults.update(min=minmax[0], max=minmax[1])
    return panel("stat", title, grid, [target("A", query or flux(field, "last", "1m").replace(
                     "range(start: v.timeRangeStart, stop: v.timeRangeStop)", "range(start: -5m)"))],
                 fieldConfig={"defaults": defaults, "overrides": []},
                 options={"reduceOptions": {"calcs": ["lastNotNull"], "values": False},
                          "colorMode": "none", "graphMode": "none", "textMode": "value",
                          "justifyMode": "center"})


def timeseries(title, grid, series, unit, draw="line", window="v.windowPeriod", fn="mean",
               **extra):
    targets, overrides = [], []
    for ref, (field, name, color) in zip("ABCDEFG", series):
        targets.append(target(ref, flux(field, fn, window)))
        overrides.append(override(ref, name, color))
    custom = {"drawStyle": draw, "lineWidth": 2, "fillOpacity": 0 if draw == "line" else 90,
              "showPoints": "never", "spanNulls": 60000, "axisSoftMin": 0,
              "gradientMode": "none", "barAlignment": 0}
    return panel("timeseries", title, grid, targets,
                 fieldConfig={"defaults": {"unit": unit, "custom": custom}, "overrides": overrides},
                 options={"legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
                          "tooltip": {"mode": "multi", "sort": "none"}},
                 **extra)


def daily_bars(grid) -> dict:
    series = [("day_pv_energy", "PV", COLOR["pv"]),
              ("day_load_energy", "Load", COLOR["load"]),
              ("day_grid_import", "Grid import", COLOR["grid"]),
              ("day_grid_export", "Grid export", COLOR["export"])]
    fields = " or ".join(f'r._field == "{f}"' for f, _, _ in series)
    query = (
        f'import "timezone"\noption location = timezone.location(name: "{TZ}")\n'
        'from(bucket: v.defaultBucket)\n'
        '  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n'
        f'  |> filter(fn: (r) => r._measurement == "inverter" and ({fields}))\n'
        '  |> aggregateWindow(every: 1d, fn: max, createEmpty: false, timeSrc: "_start")\n'
        '  |> group()\n'
        '  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")\n'
        f'  |> keep(columns: ["_time", {", ".join(chr(34) + f + chr(34) for f, _, _ in series)}])'
    )
    overrides = [{"matcher": {"id": "byName", "options": f},
                  "properties": [{"id": "displayName", "value": n},
                                 {"id": "color", "value": {"mode": "fixed", "fixedColor": c}}]}
                 for f, n, c in series]
    return panel("barchart", "Daily energy (last 30 days)", grid, [target("A", query)],
                 timeFrom="30d",
                 # pivot sorts columns alphabetically; restore PV, Load, Import, Export
                 transformations=[{"id": "organize", "options": {"indexByName": {
                     "_time": 0, **{f: i + 1 for i, (f, _, _) in enumerate(series)}}}}],
                 fieldConfig={"defaults": {"unit": KWH, "decimals": 1,
                                           "custom": {"fillOpacity": 90, "lineWidth": 0}},
                              "overrides": overrides},
                 options={"xField": "_time", "xTickLabelSpacing": 100, "groupWidth": 0.8,
                          "barWidth": 0.94, "stacking": "none", "showValue": "never",
                          "orientation": "vertical",
                          "legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
                          "tooltip": {"mode": "multi", "sort": "none"}})


panels = [
    stat("PV power", (0, 0, 4, 4), "pv_power", "watt"),
    stat("Load", (4, 0, 4, 4), "load_power", "watt"),
    stat("Battery SOC", (8, 0, 4, 4), "battery_soc", "percent", minmax=(0, 100)),
    stat("Battery power (+ discharge)", (12, 0, 4, 4), "battery_power", "watt"),
    stat("Grid power (+ import)", (16, 0, 4, 4), "grid_power", "watt"),
    stat("Inverter temp", (20, 0, 4, 4), "radiator_temperature", "celsius", 1),

    stat("PV today", (0, 4, 4, 4), None, KWH, 1, last_today("day_pv_energy")),
    stat("Load today", (4, 4, 4, 4), None, KWH, 1, last_today("day_load_energy")),
    stat("Grid import today", (8, 4, 4, 4), None, KWH, 1, last_today("day_grid_import")),
    stat("Grid export today", (12, 4, 4, 4), None, KWH, 1, last_today("day_grid_export")),
    stat("Self-sufficiency today", (16, 4, 4, 4), None, "percent", 0,
         ratio_today("day_load_energy", "day_grid_import", "self_sufficiency"), (0, 100)),
    stat("PV self-consumption today", (20, 4, 4, 4), None, "percent", 0,
         ratio_today("day_pv_energy", "day_grid_export", "self_consumption"), (0, 100)),

    timeseries("Power flow", (0, 8, 24, 9), [
        ("pv_power", "PV", COLOR["pv"]),
        ("load_power", "Load", COLOR["load"]),
        ("battery_power", "Battery (+ discharge / − charge)", COLOR["battery"]),
        ("grid_power", "Grid (+ import / − export)", COLOR["grid"]),
    ], "watt"),

    timeseries("Battery state of charge", (0, 17, 12, 7), [
        ("battery_soc", "SOC", COLOR["battery"]),
    ], "percent"),

    timeseries("PV strings", (12, 17, 12, 7), [
        ("pv1_power", "PV1", COLOR["pv"]),
        ("pv2_power", "PV2", COLOR["load"]),
    ], "watt"),

    daily_bars((0, 24, 24, 9)),
]

# SOC axis is always 0-100
for p in panels:
    if p["title"] == "Battery state of charge":
        p["fieldConfig"]["defaults"].update(min=0, max=100)

dashboard = {
    "uid": "deye-overview",
    "title": "Deye inverter",
    "timezone": "browser",
    "refresh": "30s",
    "time": {"from": "now-24h", "to": "now"},
    "schemaVersion": 39,
    "editable": True,
    "panels": panels,
}

out = Path(__file__).resolve().parent.parent / "grafana" / "dashboards" / "deye.json"
out.write_text(json.dumps(dashboard, indent=2, ensure_ascii=False) + "\n")
print(f"wrote {out}")
