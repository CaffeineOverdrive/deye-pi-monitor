import unittest

from deye_monitor.registers import READ_BLOCKS, SENSORS, decode


def _raw(**regs: int) -> dict[int, int]:
    raw = {a: 0 for start, n in READ_BLOCKS for a in range(start, start + n)}
    raw.update({int(k[1:]): v for k, v in regs.items()})
    return raw


class DecodeTest(unittest.TestCase):
    def test_every_sensor_register_is_in_a_read_block(self):
        covered = {a for start, n in READ_BLOCKS for a in range(start, start + n)}
        for s in SENSORS:
            for r in s.regs:
                self.assertIn(r, covered, f"{s.key} register {r} not read")

    def test_signed_power(self):
        v = decode(_raw(r190=0x10000 - 1500, r169=420))
        self.assertEqual(v["battery_power"], -1500)  # charging
        self.assertEqual(v["grid_power"], 420)       # importing

    def test_scaling_and_offset(self):
        v = decode(_raw(r183=5312, r184=87, r182=1253, r108=154))
        self.assertAlmostEqual(v["battery_voltage"], 53.12)
        self.assertEqual(v["battery_soc"], 87)
        self.assertAlmostEqual(v["battery_temperature"], 25.3)
        self.assertAlmostEqual(v["day_pv_energy"], 15.4)

    def test_32bit_total_low_word_first(self):
        v = decode(_raw(r96=0x0002, r97=0x0001))  # 65538 * 0.1
        self.assertAlmostEqual(v["total_pv_energy"], 6553.8)
        v = decode(_raw(r78=100, r80=1))          # import total skips reg 79
        self.assertAlmostEqual(v["total_grid_import"], 6563.6)

    def test_pv_power_is_sum_of_strings(self):
        v = decode(_raw(r186=2100, r187=1800))
        self.assertEqual(v["pv_power"], 3900)


if __name__ == "__main__":
    unittest.main()
