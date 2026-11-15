import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from tools.tactile_acq.protocol import parse_message
from tools.tactile_acq.recorder import RunRecorder
from tools.tactile_acq.stats import RunStats, stats_from_csv
from tools.tactile_acq.tests.fixtures import make_sample


def frame(seq, timestamp_us=1000000, **kwargs):
    message = make_sample(seq=seq, timestamp_us=timestamp_us, **kwargs)
    return parse_message((json.dumps(message) + "\n").encode())


def attach_host(item, host_ns):
    return replace(item, host_received_ns=host_ns, host_monotonic_ns=host_ns, host_received_utc="t")


class StatsTests(unittest.TestCase):
    def test_frame_rate_and_missing(self):
        stats = RunStats()
        for seq, ts in ((0, 1_000_000), (1, 1_021_000), (4, 1_042_000)):
            stats.add_sample(attach_host(frame(seq, ts), ts * 1000))
        summary = stats.summary()
        self.assertEqual(summary["frame_seq"]["missing"], 2)
        self.assertEqual(summary["frame_seq"]["duplicates"], 0)
        self.assertAlmostEqual(summary["device_frame_rate_hz"], 2 * 1e6 / 42000, places=2)
        self.assertAlmostEqual(summary["frame_seq"]["drop_rate"], 0.4, places=6)

    def test_duplicate_and_out_of_order(self):
        stats = RunStats()
        for seq in (0, 0, 2, 1):
            stats.add_sample(attach_host(frame(seq), 1000 + seq))
        summary = stats.summary()
        self.assertEqual(summary["frame_seq"]["duplicates"], 1)
        self.assertEqual(summary["frame_seq"]["missing"], 1)
        self.assertEqual(summary["frame_seq"]["out_of_order"], 1)

    def test_boot_change_does_not_count_gap(self):
        stats = RunStats()
        stats.add_sample(attach_host(frame(10, boot_id="a"), 1000))
        stats.add_sample(attach_host(frame(0, boot_id="b"), 2000))
        summary = stats.summary()
        self.assertEqual(summary["frame_seq"]["missing"], 0)
        self.assertEqual(summary["frame_seq"]["boot_changes"], 1)
        self.assertEqual(len(summary["boot_ids"]), 2)

    def test_invalid_and_fixed_channels(self):
        stats = RunStats()
        stats.add_sample(
            attach_host(
                frame(
                    0,
                    values=[None, 7] + [0] * 10,
                    valid=[False, True] + [True] * 10,
                    flags=[0x20, 0] + [0] * 10,
                ),
                1000,
            )
        )
        stats.add_sample(
            attach_host(
                frame(
                    1,
                    timestamp_us=1100000,
                    values=[None, 7] + [0] * 10,
                    valid=[False, True] + [True] * 10,
                    flags=[0x20, 0] + [0] * 10,
                ),
                2000,
            )
        )
        summary = stats.summary()
        self.assertEqual(summary["channels"][0]["invalid_count"], 2)
        self.assertTrue(summary["channels"][1]["fixed"])
        self.assertEqual(summary["channels"][1]["mean"], 7.0)
        self.assertIn("ADC1_AIN1", summary["fixed_channels"])

    def test_saturation(self):
        stats = RunStats()
        stats.add_sample(attach_host(frame(0, values=[8388607] + [0] * 11, flags=[0x01] + [0] * 11), 1000))
        summary = stats.summary()
        self.assertEqual(summary["channels"][0]["saturated_high"], 1)
        self.assertIn("ADC1_AIN0", summary["saturated_channels"])
        self.assertEqual(summary["channels"][0]["near_rail"], 1)

    def test_host_timeout(self):
        stats = RunStats()
        stats.add_sample(attach_host(frame(0), 1_000_000_000))
        stats.add_sample(attach_host(frame(1, timestamp_us=1_050_000), 4_000_000_000))
        summary = stats.summary()
        self.assertEqual(summary["host_timeouts"], 1)
        self.assertAlmostEqual(summary["max_host_gap_s"], 3.0, places=3)

    def test_recorder_and_csv_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            recorder = RunRecorder(root, "/dev/test", 921600, {"device_id": "x"}, {"serial_baud": 921600})
            for index in range(3):
                item = frame(index, 1000000 + index * 20000)
                recorder.record_line(
                    (json.dumps(make_sample(seq=index, timestamp_us=1000000 + index * 20000)) + "\n").encode(),
                    item,
                )
            run = recorder.finalize()
            self.assertTrue((root / "raw_frames.jsonl").is_file())
            self.assertTrue((root / "samples.csv").is_file())
            self.assertTrue((root / "run.json").is_file())
            self.assertEqual(run["summary"]["samples"], 3)
            self.assertEqual(len(run["files"]["samples.csv"]["sha256"]), 64)
            saved = json.loads((root / "run.json").read_text())
            self.assertEqual(saved["data_kind"], "REAL_HARDWARE_SERIAL")
            recomputed = stats_from_csv(str(root / "samples.csv"))
            self.assertEqual(recomputed.samples, 3)
            self.assertEqual(recomputed.missing_frames, 0)


if __name__ == "__main__":
    unittest.main()
