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

    def test_other_broker_does_not_inherit_credentials(self):
        cfg = Config().updated({"transport": "rs485", "mqtt_host": "192.168.1.33"})
        self.assertEqual((cfg.mqtt_host, cfg.mqtt_user, cfg.mqtt_password), ("192.168.1.33", None, None))
        cfg = cfg.updated({"mqtt_host": "192.168.1.33", "mqtt_user": "pi", "mqtt_password": "pw"})
        self.assertEqual((cfg.mqtt_user, cfg.mqtt_password), ("pi", "pw"))
        same = cfg.updated({"mqtt_host": "192.168.1.33", "poll_seconds": "20"})
        self.assertEqual((same.mqtt_user, same.mqtt_password), ("pi", "pw"))
        moved = cfg.updated({"mqtt_host": "ha.local", "mqtt_user": "pi"})
        self.assertEqual((moved.mqtt_user, moved.mqtt_password), ("pi", None))


    def test_broker_saves_without_inverter_and_inverter_save_keeps_broker(self):
        cfg = Config().updated({"mqtt_host": "192.168.1.33", "mqtt_user": "u", "mqtt_password": "p"},
                               mqtt_only=True)
        self.assertFalse(cfg.configured)
        self.assertEqual((cfg.mqtt_host, cfg.mqtt_user, cfg.mqtt_password), ("192.168.1.33", "u", "p"))
        ignored = cfg.updated({"transport": "solarman", "logger_ip": "x"}, mqtt_only=True)
        self.assertEqual(ignored.transport, "")
        cfg = cfg.updated({"transport": "solarman", "logger_ip": "10.0.0.5", "logger_serial": "123"})
        self.assertEqual((cfg.mqtt_host, cfg.mqtt_password), ("192.168.1.33", "p"))
        with self.assertRaises(ValueError):
            Config().updated({"mqtt_port": "abc"}, mqtt_only=True)


@mock.patch.dict(os.environ, {"MQTT_USER": "deye", "MQTT_PASSWORD": "builtin-pw"}, clear=True)
class NoBuiltinBrokerTest(unittest.TestCase):
    def test_mqtt_off_by_default_and_after_clearing(self):
        self.assertIsNone(Config().mqtt_host)
        self.assertFalse(Config().builtin_broker)
        ext = Config().updated({"transport": "rs485", "mqtt_host": "ha.local", "mqtt_user": "u"})
        self.assertIsNone(ext.updated({"mqtt_host": ""}).mqtt_host)


class DiscoveryTest(unittest.TestCase):
    def test_parse_reply(self):
        self.assertEqual(parse_reply(b"192.168.1.50,98D8630A1B2C,2712345678", "x"),
                         {"ip": "192.168.1.50", "mac": "98D8630A1B2C", "serial": 2712345678})
        self.assertIsNone(parse_reply(b"+ok", "x"))


if __name__ == "__main__":
    unittest.main()
