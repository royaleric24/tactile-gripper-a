import unittest

from tools.cup_grasp.single_point import summarize_single_point


class SinglePointTests(unittest.TestCase):
    def test_five_cycles_with_contact_response(self):
        records = []
        cycles = []
        t = 0
        for cycle in range(5):
            press = (cycle * 5 + 1) * 1_000_000_000
            release = press + 2_000_000_000
            cycles.append({"press_ns": press, "release_ns": release})
            for i in range(0, 5_000_000_000, 40_000_000):
                now = t * 1_000_000_000 + i
                delta = 0.0 if not (press <= now < release) else 700.0
                # deterministic baseline noise
                if delta == 0.0:
                    delta = 10.0 if (i // 40_000_000) % 2 else -10.0
                records.append({"host_monotonic_ns": now, "delta": delta, "saturated": False})
            t += 5
        summary = summarize_single_point(records, cycles)
        self.assertEqual(summary["total_cycles"], 5)
        self.assertEqual(summary["passed_cycles"], 5)
        self.assertTrue(summary["pass"])
        for item in summary["cycles"]:
            self.assertGreater(item["snr"], 3)
            self.assertLessEqual(item["saturation_fraction"], 0.05)

    def test_saturated_cycles_fail(self):
        records = []
        cycles = [{"press_ns": 1_000_000_000, "release_ns": 3_000_000_000}]
        for i in range(0, 5_000_000_000, 40_000_000):
            records.append({"host_monotonic_ns": i, "delta": 0.0, "saturated": True})
        summary = summarize_single_point(records, cycles)
        self.assertFalse(summary["pass"])
        self.assertEqual(summary["passed_cycles"], 0)


if __name__ == "__main__":
    unittest.main()
