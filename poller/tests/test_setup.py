import json
import os
import tempfile
import unittest
from unittest import mock

from deye_monitor.config import Config, load_config, save_config
from deye_monitor.discovery import parse_reply

ENV = {"MQTT_HOST": "localhost", "MQTT_USER": "deye", "MQTT_PASSWORD": "builtin-pw"}


@mock.patch.dict(os.environ, ENV, clear=True)
class ConfigTest(unittest.TestCase):
    def test_unconfigured_by_default(self):
        self.assertFalse(Config().configured)

    def test_wifi_logger_settings(self):
        cfg = Config().updated({"transport": "solarman", "logger_ip": " 192.168.1.50 ",
                                "logger_serial": "2712345678", "slave_id": "1"})
        self.assertTrue(cfg.configured)
        self.assertEqual(cfg.logger_ip, "192.168.1.50")
        self.assertEqual(cfg.logger_serial, 2712345678)

    def test_rejects_incomplete_or_bad_input(self):
        with self.assertRaises(ValueError):
            Config().updated({"transport": "solarman", "logger_ip": "192.168.1.50"})
        with self.assertRaises(ValueError):
            Config().updated({"transport": "solarman", "logger_ip": "x", "logger_serial": "abc"})
        with self.assertRaises(ValueError):
            Config().updated({"transport": "rs485", "serial_port": "/dev/ttyUSB0", "slave_id": "0"})
        with self.assertRaises(ValueError):
            Config().updated({"transport": "carrier-pigeon"})

    def test_blank_broker_returns_to_builtin_with_its_credentials(self):
        ext = Config().updated({"transport": "rs485", "mqtt_host": "ha.local",
                                "mqtt_user": "ha", "mqtt_password": "ha-pw"})
        self.assertEqual((ext.mqtt_host, ext.mqtt_password), ("ha.local", "ha-pw"))
        back = ext.updated({"mqtt_host": "", "mqtt_user": ""})
        self.assertEqual((back.mqtt_host, back.mqtt_user, back.mqtt_password),
                         ("localhost", "deye", "builtin-pw"))

    def test_save_and_load_round_trip_ignores_unknown_keys(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "settings.json")
            save_config(Config().updated({"transport": "solarman", "logger_ip": "10.0.0.5",
                                          "logger_serial": "123"}), path)
            data = json.load(open(path))
            data["influx_token"] = "should-not-load"
            json.dump(data, open(path, "w"))
            cfg = load_config(path)
            self.assertEqual((cfg.transport, cfg.logger_ip, cfg.logger_serial), ("solarman", "10.0.0.5", 123))
            self.assertIsNone(cfg.influx_token)
            if os.name == "posix":   # Windows doesn't keep Unix permission bits
                self.assertEqual(oct(os.stat(path).st_mode & 0o777), "0o600")


class DiscoveryTest(unittest.TestCase):
    def test_parse_reply(self):
        self.assertEqual(parse_reply(b"192.168.1.50,98D8630A1B2C,2712345678", "x"),
                         {"ip": "192.168.1.50", "mac": "98D8630A1B2C", "serial": 2712345678})
        self.assertIsNone(parse_reply(b"+ok", "x"))


if __name__ == "__main__":
    unittest.main()
