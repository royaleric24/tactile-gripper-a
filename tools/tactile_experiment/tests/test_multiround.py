import csv
import json
import tempfile
import unittest
from pathlib import Path

from tools.tactile_acq.protocol import CSV_COLUMNS
from tools.tactile_experiment.ml import (
    COMMON_FEATURES,
    evaluate_rounds,
    feature_names,
    load_round,
    write_features_csv,
)
from tools.tactile_experiment.multiround import (
    APPROACH,
    NO_CONTACT,
    PRESS,
    build_round_schedule,
)


class ScheduleTests(unittest.TestCase):
    def test_36_presses_once_and_random_order(self):
        a = build_round_schedule(1, 1234, approach_controls=2, no_contact_controls=2)
        b = build_round_schedule(2, 5678, approach_controls=2, no_contact_controls=2)
        presses_a = [s.point.point_id for s in a.segments if s.kind == PRESS]
        presses_b = [s.point.point_id for s in b.segments if s.kind == PRESS]
        self.assertEqual(len(presses_a), 36)
        self.assertEqual(sorted(presses_a), list(range(1, 37)))
        self.assertEqual(len(presses_b), 36)
        self.assertNotEqual([s.point.point_id for s in a.press_segments],
                            [s.point.point_id for s in b.press_segments])
        self.assertEqual(sum(1 for s in a.segments if s.kind == APPROACH), 2)
        self.assertEqual(sum(1 for s in a.segments if s.kind == NO_CONTACT), 2)
        self.assertEqual(len(a.segments), 40)

    def test_schedule_serialization_keeps_seed_and_order(self):
        schedule = build_round_schedule(1, 9876, approach_controls=1, no_contact_controls=1)
        data = schedule.as_dict()
        self.assertEqual(data["seed"], 9876)
        self.assertEqual(len(data["press_order"]), 36)
        self.assertEqual(sorted(data["press_order"]), list(range(1, 37)))


def make_round(root: Path, round_index: int, seed: int):
    schedule = build_round_schedule(round_index, seed, approach_controls=2, no_contact_controls=2)
    t = 0.0
    samples = []
    frame = 0
    events = []

    def add_samples(duration, point=None, kind=PRESS):
        nonlocal t, frame
        end = t + duration
        while t < end:
            channels = [1000 + ch * 10 for ch in range(12)]
            if kind == PRESS and point is not None:
                row, col = (point - 1) // 6 + 1, (point - 1) % 6 + 1
                channels[0] += row * 500
                channels[1] += col * 500
                channels[2] += row * col * 50
            samples.append({
                "frame": frame,
                "host_ns": int(t * 1e9),
                "device_us": int(t * 1e6),
                "channels": channels,
            })
            frame += 1
            t += 0.04
        return int(t * 1e9)

    def event(kind, start_ns, segment):
        events.append({
            "kind": kind,
            "host_event_monotonic_ns": int(start_ns),
            "round_index": round_index,
            "segment_index": segment.segment_index,
            "segment_kind": segment.kind,
            "point_id": segment.point.point_id if segment.point else None,
            "row": segment.point.row if segment.point else None,
            "column": segment.point.column if segment.point else None,
            "label": segment.label,
            "latest_frame_age_ms": 1.0,
        })

    event("BASELINE_START", 0, type("S", (), {"segment_index": None, "kind": "BASELINE", "point": None, "label": "BASELINE"})())
    add_samples(0.5)
    event("BASELINE_END", int(t * 1e9), type("S", (), {"segment_index": None, "kind": "BASELINE", "point": None, "label": "BASELINE"})())
    for segment in schedule.segments:
        press_start = int(t * 1e9)
        event("SEGMENT_READY", press_start, segment)
        if segment.kind == PRESS:
            event("PRESS_START", press_start, segment)
            end_ns = add_samples(0.4, segment.point.point_id, PRESS)
            event("RELEASE_START", end_ns, segment)
            add_samples(0.4)
            add_samples(1.2)  # rest so the 1.5 s local baseline is not contaminated
        elif segment.kind == APPROACH:
            event("APPROACH_START", press_start, segment)
            end_ns = add_samples(0.4, None, APPROACH)
            event("APPROACH_END", end_ns, segment)
            add_samples(0.4)
            add_samples(1.2)
        else:
            event("NO_CONTACT_START", press_start, segment)
            end_ns = add_samples(0.4, None, NO_CONTACT)
            event("NO_CONTACT_END", end_ns, segment)
            add_samples(0.4)
            add_samples(1.2)
        event("SEGMENT_DONE", int(t * 1e9), segment)
    event("BASELINE_START", int(t * 1e9), type("S", (), {"segment_index": None, "kind": "BASELINE", "point": None, "label": "BASELINE"})())
    add_samples(0.5)
    event("BASELINE_END", int(t * 1e9), type("S", (), {"segment_index": None, "kind": "BASELINE", "point": None, "label": "BASELINE"})())

    root.mkdir(parents=True, exist_ok=True)
    with open(root / "samples.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for item in samples:
            row = {
                "frame_seq": item["frame"], "device_timestamp_us": item["device_us"],
                "host_received_unix_ns": item["host_ns"], "host_received_iso": "",
                "host_monotonic_ns": item["host_ns"], "boot_id": "boot",
                "reference_mode": "INTERNAL_2V048", "effective_frame_rate_hz": "25.00",
            }
            for ch, value in enumerate(item["channels"]):
                row["ch{}".format(ch)] = value
                row["valid{}".format(ch)] = 1
                row["flag{}".format(ch)] = 0
            row["adc1_state"] = row["adc2_state"] = row["adc3_state"] = "OK"
            writer.writerow(row)
    with open(root / "events.jsonl", "w", encoding="utf-8") as handle:
        for item in events:
            handle.write(json.dumps(item) + "\n")
    (root / "meta.json").write_text(json.dumps({"seed": seed}) + "\n")
    (root / "run.json").write_text(json.dumps({"summary": {"samples": len(samples)}}) + "\n")
    return schedule


class MLTests(unittest.TestCase):
    def test_no_label_fields_in_features(self):
        names = feature_names("plus_common")
        for forbidden in ("point", "round", "seed", "order", "label"):
            self.assertFalse(any(forbidden in name.lower() for name in names), forbidden)
        self.assertIn("f_common_delta_mean", names)
        self.assertEqual(len(feature_names("per_channel")), 120)

    def test_cross_round_models(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            make_round(base / "round_01", 1, 111)
            make_round(base / "round_02", 2, 222)
            rounds = [
                {"round_index": 1, "rows": load_round(base / "round_01", 1)},
                {"round_index": 2, "rows": load_round(base / "round_02", 2)},
            ]
            result = evaluate_rounds(rounds)
            self.assertEqual(len(result["results"]), 12)  # 2 directions x 3 models x 2 feature sets
            for item in result["results"]:
                self.assertIsNotNone(item["point"])
                self.assertIsNotNone(item["control"])
            nearest = [item for item in result["results"]
                       if item["point"]["model"] == "nearest_centroid" and item["point"]["feature_set"] == "per_channel"]
            self.assertTrue(nearest)
            for item in nearest:
                self.assertGreaterEqual(item["point"]["top1"], 0.9)
                self.assertLessEqual(item["control"]["false_contact_rate"], 0.1)
            self.assertGreater(result["repeatability"]["same_point_cosine_mean"], 0.9)
            self.assertGreater(result["repeatability"]["same_point_cosine_mean"],
                               result["repeatability"]["different_point_cosine_mean"])
            write_features_csv(base / "features.csv", rounds)
            lines = (base / "features.csv").read_text().splitlines()
            self.assertEqual(len(lines), 1 + 2 * 40)
            self.assertIn("f_delta_0", lines[0])


if __name__ == "__main__":
    unittest.main()
