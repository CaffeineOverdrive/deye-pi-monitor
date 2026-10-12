"""Find Solarman Wi-Fi loggers and USB serial adapters for the setup page."""

import os
import socket
import time

from .config import RS485_PATH

DISCOVERY_PORT = 48899
# Different logger firmwares answer to different probe strings; send both.
PROBES = (b"WIFIKIT-214028-READ", b"HF-A11ASSISTHREAD")


def parse_reply(data: bytes, addr: str) -> dict | None:
    """Replies look like b'192.168.1.50,98D8630A1B2C,2712345678'."""
    parts = data.decode(errors="ignore").strip().split(",")
    if len(parts) < 3 or not parts[2].strip().isdigit():
        return None
    return {"ip": parts[0].strip() or addr, "mac": parts[1].strip(), "serial": int(parts[2])}


def scan_loggers(timeout: float = 3.0, targets: tuple[str, ...] = ("255.255.255.255",),
                 port: int = DISCOVERY_PORT) -> list[dict]:
    found: dict[int, dict] = {}
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.settimeout(0.3)
        for target in targets:
            for probe in PROBES:
                try:
                    s.sendto(probe, (target, port))
                except OSError:
                    pass
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                data, (addr, _) = s.recvfrom(1024)
            except socket.timeout:
                continue
            if (hit := parse_reply(data, addr)):
                found[hit["serial"]] = hit
    return sorted(found.values(), key=lambda h: h["ip"])


def list_serial_ports() -> list[dict]:
    """The container only sees the adapter passed through by enable-rs485.sh -
    never other USB serial devices such as a 3D printer."""
    if os.path.exists(RS485_PATH):
        return [{"path": RS485_PATH, "label": "RS485 adapter (enabled with enable-rs485.sh)"}]
    return []


def local_ip() -> str:
    """The address other devices on the LAN use to reach this Pi."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("10.255.255.255", 1))  # no packet is sent
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"
