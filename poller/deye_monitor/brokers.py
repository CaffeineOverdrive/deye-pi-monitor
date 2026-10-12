"""Find MQTT brokers on the LAN for the setup page.

Home Assistant announces itself over mDNS (_home-assistant._tcp), and Home Assistant OS
answers to homeassistant.local; its Mosquitto add-on listens on 1883 on the same host.
Some brokers also announce _mqtt._tcp. Each candidate
is then probed with a bare MQTT CONNECT, which tells us whether a broker is really there
and whether it wants a username and password.
"""

import logging
import socket
import struct
import time

from .config import BUILTIN_HOSTS

log = logging.getLogger(__name__)

MQTT_PORT = 1883
SERVICES = {
    "_home-assistant._tcp.local.": "Home Assistant",
    "_mqtt._tcp.local.": "MQTT broker",
}

# CONNACK return codes (MQTT 3.1.1)
_ACCEPTED, _BAD_CREDENTIALS, _NOT_AUTHORIZED = 0, 4, 5


def _mqtt_string(s: str) -> bytes:
    b = s.encode()
    return struct.pack("!H", len(b)) + b


def _remaining_length(n: int) -> bytes:
    out = bytearray()
    while True:
        n, digit = divmod(n, 128)
        out.append(digit | (0x80 if n else 0))
        if not n:
            return bytes(out)


def connect_packet(client_id: str, user: str | None = None, password: str | None = None) -> bytes:
    flags = 0x02                      # clean session
    payload = _mqtt_string(client_id)
    if user:
        flags |= 0x80
        payload += _mqtt_string(user)
        if password:
            flags |= 0x40
            payload += _mqtt_string(password)
    body = _mqtt_string("MQTT") + bytes([4, flags]) + struct.pack("!H", 10) + payload
    return b"\x10" + _remaining_length(len(body)) + body


def probe(host: str, port: int = MQTT_PORT, user: str | None = None,
          password: str | None = None, timeout: float = 3.0) -> dict:
    """Try to log in. status is one of: ok, auth_required, bad_credentials,
    refused, not_mqtt, unreachable."""
    try:
        with socket.create_connection((host, port), timeout=timeout) as s:
            s.settimeout(timeout)
            s.sendall(connect_packet(f"deye-monitor-probe-{int(time.time())}", user, password))
            reply = b""
            while len(reply) < 4:
                chunk = s.recv(4 - len(reply))
                if not chunk:
                    break
                reply += chunk
            if len(reply) < 4 or reply[0] != 0x20:
                return {"status": "not_mqtt", "detail": "something answered, but not an MQTT broker"}
            code = reply[3]
            if code == _ACCEPTED:
                s.sendall(b"\xe0\x00")   # DISCONNECT
                return {"status": "ok", "detail": "logged in"}
            if code in (_BAD_CREDENTIALS, _NOT_AUTHORIZED):
                return ({"status": "bad_credentials", "detail": "username or password rejected"} if user
                        else {"status": "auth_required", "detail": "needs a username and password"})
            return {"status": "refused", "detail": f"broker refused the connection (code {code})"}
    except OSError as e:
        return {"status": "unreachable", "detail": str(e) or type(e).__name__}


def browse_mdns(timeout: float = 3.0) -> list[dict]:
    """Hosts announcing Home Assistant or MQTT over mDNS."""
    from zeroconf import ServiceBrowser, ServiceStateChange, Zeroconf

    names: list[tuple[str, str]] = []

    def on_change(zeroconf, service_type, name, state_change):
        if state_change is ServiceStateChange.Added:
            names.append((service_type, name))

    zc = Zeroconf()
    try:
        ServiceBrowser(zc, list(SERVICES), handlers=[on_change])
        time.sleep(timeout)
        found = []
        for service_type, name in names:
            info = zc.get_service_info(service_type, name, timeout=1500)
            if not info:
                continue
            port = info.port if service_type == "_mqtt._tcp.local." else MQTT_PORT
            for addr in info.parsed_addresses():
                if ":" not in addr:   # IPv4 only: simpler for users to read and type
                    found.append({"host": addr, "port": port, "source": SERVICES[service_type],
                                  "name": name.split(".")[0]})
        return found
    finally:
        zc.close()


def mdns_query(name: str) -> bytes:
    labels = b"".join(bytes([len(p)]) + p.encode() for p in name.rstrip(".").split("."))
    return struct.pack("!6H", 0, 0, 1, 0, 0, 0) + labels + b"\x00" + struct.pack("!2H", 1, 1)


def _skip_name(data: bytes, i: int) -> int:
    while True:
        n = data[i]
        if n == 0:
            return i + 1
        if n & 0xC0 == 0xC0:   # compression pointer ends the name
            return i + 2
        i += n + 1


def parse_a_records(data: bytes) -> list[str]:
    """IPv4 addresses from the answer and additional sections of a DNS reply."""
    try:
        _, flags, qd, an, ns, ar = struct.unpack_from("!6H", data)
        if not flags & 0x8000:   # a query, not a response
            return []
        i = 12
        for _ in range(qd):
            i = _skip_name(data, i) + 4
        found = []
        for _ in range(an + ns + ar):
            i = _skip_name(data, i)
            rtype, _, _, rdlen = struct.unpack_from("!HHIH", data, i)
            i += 10
            if rtype == 1 and rdlen == 4:
                found.append(socket.inet_ntoa(data[i:i + 4]))
            i += rdlen
        return found
    except (struct.error, IndexError):
        return []


def resolve_mdns_host(name: str, timeout: float = 2.0) -> list[str]:
    """Every IPv4 address that answers for NAME.local. Done by hand because the
    container has no .local resolver; replies come straight back to this socket."""
    found: list[str] = []
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(0.3)
        s.sendto(mdns_query(name), ("224.0.0.251", 5353))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                data, _ = s.recvfrom(9000)
            except socket.timeout:
                continue
            found += [a for a in parse_a_records(data) if a not in found]
    return found


def find_brokers(include_builtin: bool, builtin_port: int = MQTT_PORT, timeout: float = 3.0) -> list[dict]:
    try:
        candidates = browse_mdns(timeout)
    except Exception as e:   # no multicast on this network, etc.
        log.warning("mDNS search failed: %s", e)
        candidates = []
    # Home Assistant OS always answers to homeassistant.local, even when its service
    # announcement is off - so ask for the name too.
    try:
        candidates += [{"host": a, "port": MQTT_PORT, "source": "Home Assistant", "name": "homeassistant.local"}
                       for a in resolve_mdns_host("homeassistant.local")]
    except OSError as e:
        log.warning("mDNS name lookup failed: %s", e)
    if include_builtin:
        candidates.insert(0, {"host": "localhost", "port": builtin_port,
                              "source": "Built-in broker on this Pi", "name": "mosquitto"})
    seen, result = set(), []
    for c in candidates:
        key = (c["host"], c["port"])
        if key in seen:
            continue
        seen.add(key)
        result.append({**c, **probe(c["host"], c["port"], timeout=2.0)})
    return result
