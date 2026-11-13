import unittest
from types import SimpleNamespace

from tools.cup_grasp.model import load_config
from tools.cup_grasp.tactile import TactileProcessor


def frame(value, seq=1, flag=0, valid=True):
    raw = [value] + [0] * 11
    flags = [flag] + [0] * 11
    valid_list = [valid] + [True] * 11
    return SimpleNamespace(raw_adc=raw, valid=valid_list, channel_flags=flags,
                           timestamp_us=seq * 40000, frame_seq=seq, host_monotonic_ns=seq * 40_000_000)


class TactileTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config("config/cup_grasp.simulated.json")
        self.processor = TactileProcessor(self.config.tactile)

    def test_baseline_and_contact_delta(self):
        for i in range(1, 11):
            sample = self.processor.update(frame(1000, i), i * 40_000_000)
        self.assertTrue(self.processor.baseline_ready)
        self.assertTrue(sample.usable)
        self.assertAlmostEqual(sample.baseline, 1000)
        for i in range(11, 21):
            sample = self.processor.update(frame(1700, i), i * 40_000_000)
        self.assertGreater(sample.delta, 500)
        self.assertTrue(sample.usable)

    def test_saturation_is_not_usable(self):
        for i in range(1, 11):
            self.processor.update(frame(1000, i), i * 40_000_000)
        sample = self.processor.update(frame(8388607, 11, flag=0x01), 11 * 40_000_000)
        self.assertTrue(sample.saturated)
        self.assertFalse(sample.usable)

    def test_sensor_timeout(self):
        for i in range(1, 11):
            self.processor.update(frame(1000, i), i * 40_000_000)
        self.assertTrue(self.processor.sensor_ok(10 * 40_000_000))
        self.assertFalse(self.processor.sensor_ok(10 * 40_000_000 + 2_000_000_000))


if __name__ == "__main__":
    unittest.main()
