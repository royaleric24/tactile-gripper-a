import unittest

from scripts.diag_all_channels import channel_stats


class DiagChannelTests(unittest.TestCase):
    def test_channel_stats_follow_selected_channel(self):
        rows = []
        for i in range(10):
            raw = [8_300_000] * 12
            raw[5] = 2_400_000 if i >= 5 else 1_000_000
            rows.append({"raw_adc": raw, "valid": [True] * 12,
                         "channel_flags": [0] * 12})
        result = channel_stats(rows, 5, 3300)
        self.assertEqual(result["samples"], 10)
        self.assertAlmostEqual(result["raw_mean"], 1_700_000.0)
        self.assertAlmostEqual(result["volts_mean"], 1_700_000 / 8388607 * 3.3)
        other = channel_stats(rows, 0, 3300)
        self.assertAlmostEqual(other["raw_mean"], 8_300_000.0)

    def test_all_channels_independent(self):
        rows = [{"raw_adc": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
                 "valid": [True] * 12, "channel_flags": [0] * 12}]
        for ch in range(12):
            self.assertEqual(channel_stats(rows, ch, 3300)["raw_mean"], ch + 1)


if __name__ == "__main__":
    unittest.main()
