import json
import os
import unittest
from unittest import mock

from deye_monitor.config import Config
from deye_monitor.registers import all_sensors
from deye_monitor.sinks import discovery_payload

try:
    import jinja2   # what Home Assistant renders value_template with
except ImportError:
    jinja2 = None


@mock.patch.dict(os.environ, {}, clear=True)
class DiscoveryTest(unittest.TestCase):
    def payload(self, key):
        return discovery_payload(next(s for s in all_sensors() if s.key == key), Config())

    def test_running_state_is_an_enum_with_text(self):
        p = self.payload("running_state")
        self.assertEqual(p["device_class"], "enum")
        self.assertEqual(p["options"], ["Standby", "Self-check", "Normal", "Alarm", "Fault", "Unknown"])
        self.assertNotIn("unit_of_measurement", p)
        self.assertNotIn("state_class", p)

    @unittest.skipUnless(jinja2, "jinja2 not installed")
    def test_running_state_template_maps_values(self):
        tpl = jinja2.Environment().from_string(self.payload("running_state")["value_template"])
        render = lambda v: tpl.render(value_json=json.loads(json.dumps({"running_state": v})))
        self.assertEqual(render(2.0), "Normal")
        self.assertEqual(render(4.0), "Fault")
        self.assertEqual(render(9.0), "Unknown")

    def test_plain_sensors_unchanged(self):
        p = self.payload("pv_power")
        self.assertEqual(p["value_template"], "{{ value_json.pv_power }}")
        self.assertEqual(p["unit_of_measurement"], "W")
        self.assertNotIn("options", p)


if __name__ == "__main__":
    unittest.main()
