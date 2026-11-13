import csv
import json
import tempfile
import unittest
from pathlib import Path

from tools.tactile_acq.protocol import CSV_COLUMNS
from tools.tactile_experiment.analysis import analyze_run


def write_run(root: Path, saturate=False, points=3):
    sample_rate = 25.0
    values = []
    for frame in range(0, 200):  # 0..7.96 s
        t = frame / sample_rate
        host_ns = int(t * 1e9)
        device_us = int(t * 1_000_000)
        channels = []
        for ch in range(12):
            value = 8388607 if saturate else 1000 + ch * 10
            if not saturate:
                if 2.0 <= t < 2.4 and ch == 0:
                    value += 500
                if 2.0 <= t < 2.4 and ch == 1:
                    value += 100
                if 4.0 <= t < 4.4 and ch == 1:
                    value += 500
                if 6.0 <= t < 6.4 and ch == 3:
                    value += 500
            channels.append(value)
        values.append({"frame": frame, "host_ns": host_ns, "device_us": device_us, "channels": channels})
    with open(root / "samples.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for item in values:
            row = {
                "frame_seq": item["frame"],
                "device_timestamp_us": item["device_us"],
                "host_received_unix_ns": item["host_ns"],
                "host_received_iso": "",
                "host_monotonic_ns": item["host_ns"],
                "boot_id": "boot-test",
                "reference_mode": "INTERNAL_2V048",
                "effective_frame_rate_hz": "25.00",
            }
            for ch, value in enumerate(item["channels"]):
                row["ch{}".format(ch)] = value
                row["valid{}".format(ch)] = 1
                row["flag{}".format(ch)] = 0
            row["adc1_state"] = "OK"
            row["adc2_state"] = "OK"
            row["adc3_state"] = "OK"
            writer.writerow(row)
    events = []
    def event(kind, t, point=None):
        events.append({
            "kind": kind,
            "host_event_monotonic_ns": int(t * 1e9),
            "point_id": None if point is None else point,
            "row": None if point is None else (point - 1) // 6 + 1,
            "column": None if point is None else (point - 1) % 6 + 1,
            "label": None if point is None else "R{}C{}".format((point - 1) // 6 + 1, (point - 1) % 6 + 1),
            "latest_frame_age_ms": 1.0,
        })
    event("BASELINE_START", 0.0)
    event("BASELINE_END", 0.8)
    for point, press, release in ((1, 2.0, 2.4), (2, 4.0, 4.4), (3, 6.0, 6.4)):
        event("POINT_READY", press - 0.1, point)
        event("PRESS_START", press, point)
        event("RELEASE_START", release, point)
        event("POINT_DONE", release, point)
    event("BASELINE_START", 6.8)
    event("BASELINE_END", 7.5)
    event("EXPERIMENT_END", 7.5)
    with open(root / "events.jsonl", "w", encoding="utf-8") as handle:
        for item in events:
            handle.write(json.dumps(item) + "\n")
    (root / "meta.json").write_text(json.dumps({"identity": {"device_id": "test"}}) + "\n")
    (root / "run.json").write_text(json.dumps({"summary": {"samples": len(values)}}) + "\n")
    return values, events


class AnalysisTests(unittest.TestCase):
    def test_synthetic_response(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_run(root)
            analysis = analyze_run(root)
            self.assertEqual(analysis["completed_points"], 3)
            self.assertEqual(len(analysis["points"]), 3)
            p1 = analysis["points"][0]
            ch0 = p1["channels"][0]
            self.assertAlmostEqual(ch0["delta"], 500, delta=1)
            p2 = analysis["points"][1]
            self.assertAlmostEqual(p2["channels"][1]["delta"], 500, delta=1)
            self.assertTrue((root / "analysis.json").is_file())
            self.assertTrue((root / "responses.csv").is_file())
            self.assertTrue((root / "REPORT.md").is_file())
            self.assertTrue((root / "timeseries.svg").is_file())
            self.assertTrue((root / "response_map.svg").is_file())

    def test_saturated_baseline_marks_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_run(root, saturate=True)
            analysis = analyze_run(root, make_plots=False)
            self.assertEqual(analysis["signal_quality"], "INVALID_OR_FLOATING")
            self.assertTrue(analysis["quality_reasons"])


if __name__ == "__main__":
    unittest.main()
