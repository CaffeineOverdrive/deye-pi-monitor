import socket
import struct
import threading
import unittest

from deye_monitor.brokers import connect_packet, mdns_query, parse_a_records, probe


def fake_broker(reply: bytes | None):
    """One-shot TCP server that answers a CONNECT with `reply` (None = close)."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    received = {}

    def serve():
        conn, _ = srv.accept()
        with conn:
            received["connect"] = conn.recv(1024)
            if reply is not None:
                conn.sendall(reply)
                conn.recv(16)   # DISCONNECT or close
        srv.close()

    threading.Thread(target=serve, daemon=True).start()
    return srv.getsockname()[1], received


class ProbeTest(unittest.TestCase):
    def test_accepted(self):
        port, got = fake_broker(b"\x20\x02\x00\x00")
        self.assertEqual(probe("127.0.0.1", port)["status"], "ok")
        self.assertEqual(got["connect"][0], 0x10)

    def test_auth_required_without_credentials(self):
        port, _ = fake_broker(b"\x20\x02\x00\x05")
        self.assertEqual(probe("127.0.0.1", port)["status"], "auth_required")

    def test_bad_credentials(self):
        port, got = fake_broker(b"\x20\x02\x00\x04")
        self.assertEqual(probe("127.0.0.1", port, "u", "p")["status"], "bad_credentials")
        self.assertTrue(got["connect"].endswith(b"\x00\x01u\x00\x01p"))

    def test_not_mqtt(self):
        port, _ = fake_broker(b"HTTP/1.1 400\r\n")
        self.assertEqual(probe("127.0.0.1", port)["status"], "not_mqtt")

    def test_unreachable(self):
        s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
        self.assertEqual(probe("127.0.0.1", port, timeout=1)["status"], "unreachable")


class PacketTest(unittest.TestCase):
    def test_flags_and_long_remaining_length(self):
        pkt = connect_packet("c", "user", "x" * 200)
        self.assertEqual(pkt[0], 0x10)
        self.assertTrue(pkt[1] & 0x80)                    # length needs two bytes
        length = (pkt[1] & 0x7F) + (pkt[2] << 7)
        self.assertEqual(length, len(pkt) - 3)
        self.assertEqual(pkt[3:9], b"\x00\x04MQTT")
        self.assertEqual(pkt[10], 0x80 | 0x40 | 0x02)      # user, password, clean session

    def test_no_password_without_user(self):
        self.assertEqual(connect_packet("c", None, "pw")[9], 0x02)   # 1-byte length: flags at 9


class MdnsTest(unittest.TestCase):
    def test_query(self):
        q = mdns_query("homeassistant.local")
        self.assertEqual(q[:12], struct.pack("!6H", 0, 0, 1, 0, 0, 0))
        self.assertEqual(q[12:], b"\x0dhomeassistant\x05local\x00\x00\x01\x00\x01")

    def test_parse_reply_with_compressed_names(self):
        question = mdns_query("homeassistant.local")[12:]
        a = lambda ip: b"\xc0\x0c" + struct.pack("!HHIH", 1, 0x8001, 120, 4) + bytes(ip)
        aaaa = b"\xc0\x0c" + struct.pack("!HHIH", 28, 0x8001, 120, 16) + bytes(16)
        reply = struct.pack("!6H", 0, 0x8400, 1, 2, 0, 1) + question + a([192, 168, 1, 33]) + aaaa + a([10, 0, 0, 2])
        self.assertEqual(parse_a_records(reply), ["192.168.1.33", "10.0.0.2"])

    def test_ignores_queries_and_garbage(self):
        self.assertEqual(parse_a_records(mdns_query("x.local")), [])
        self.assertEqual(parse_a_records(b"\x00\x00\x84\x00\x00\x01"), [])


if __name__ == "__main__":
    unittest.main()
