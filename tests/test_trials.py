"""Trial storage tests: JSONL, metadata, CSV and source isolation."""

import csv
import json
import tempfile
import unittest
from pathlib import Path

from tactile_gripper.experiments.store import TrialStore, summarize_trial
from tactile_gripper.models import ControlAction, ControlCommand, ControlEvent
from tactile_gripper.sources import DataSource

from support import frame


class TrialStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = TrialStore(self.root, DataSource.SIMULATION)

    def tearDown(self):
        self.tmp.cleanup()

    def test_simulation_trial_writes_only_simulated_directory(self):
        recorder = self.store.create_trial("grasp test", mode="MANUAL", conditions={"object": "cup"})
        directory = recorder.directory
        self.assertEqual(directory.parent, self.root / "data" / "simulated" / "trials")
        self.assertFalse((self.root / "data" / "real").exists())
        self.assertTrue((directory / "metadata.json").is_file())
        metadata = json.loads((directory / "metadata.json").read_text())
        self.assertEqual(metadata["source"], "SIMULATION")
        self.assertEqual(metadata["status"], "CREATED")

    def test_start_record_stop_and_read(self):
        recorder = self.store.create_trial("grasp test", mode="MANUAL")
        recorder.start()
        command = ControlCommand(ControlAction.SET_PWM, DataSource.SIMULATION, target_pwm_us=1500)
        recorder.record_control(
            ControlEvent.from_command(
                command,
                "SIMULATED",
                "MANUAL",
                detail="offline simulation",
            )
        )
        recorder.record_frame(frame(seq=1, source=DataSource.SIMULATION))
        recorder.add_event("MARKER", "operator note", {"note": "test"})
        metadata = recorder.stop("done")
        self.assertEqual(metadata.status, "COMPLETED")
        self.assertEqual(metadata.counts["frames"], 1)
        self.assertGreaterEqual(metadata.counts["events"], 3)
        self.assertTrue((recorder.directory / "frames.jsonl").is_file())
        self.assertTrue((recorder.directory / "events.jsonl").is_file())
        self.assertTrue((recorder.directory / "frames.csv").is_file())

        record = self.store.load(metadata.trial_id)
        self.assertEqual(len(record.frames), 1)
        self.assertEqual(record.frames[0]["source"], "SIMULATION")
        self.assertTrue(any(item.get("record_type") == "CONTROL_EVENT" for item in record.events))
        summary = summarize_trial(record)
        self.assertEqual(summary["frames"], 1)
        self.assertEqual(summary["control_events"], 1)

    def test_csv_has_dynamic_channels_and_validity(self):
        recorder = self.store.create_trial("csv", mode="MANUAL")
        recorder.start()
        recorder.record_frame(
            frame(seq=1, values=[10, 20, None, 40], mask=[True, True, False, True], source=DataSource.SIMULATION)
        )
        recorder.stop("done")
        with open(recorder.directory / "frames.csv", newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["ch_0"], "10")
        self.assertEqual(rows[0]["valid_2"], "false")
        self.assertEqual(rows[0]["ch_2"], "")
        self.assertEqual(rows[0]["valid_count"], "3")

    def test_source_mixing_is_refused(self):
        recorder = self.store.create_trial("mix", mode="MANUAL")
        recorder.start()
        with self.assertRaises(ValueError):
            recorder.record_frame(frame(seq=1, source=DataSource.LIVE))
        recorder.stop("abort")

    def test_stop_requires_recording(self):
        recorder = self.store.create_trial("idle", mode="MANUAL")
        with self.assertRaises(RuntimeError):
            recorder.stop("not recording")

    def test_list_and_find(self):
        first = self.store.create_trial("first", mode="MANUAL")
        second = self.store.create_trial("second", mode="MANUAL")
        items = self.store.list_trials()
        self.assertEqual({item.metadata.trial_id for item in items}, {first.metadata.trial_id, second.metadata.trial_id})
        found = self.store.find(first.metadata.trial_id)
        self.assertEqual(found.metadata.name, "first")
        self.assertIsNone(self.store.find("../etc"))
        with self.assertRaises(FileNotFoundError):
            self.store.load("T-missing")

    def test_replay_cannot_record(self):
        store = TrialStore(self.root, DataSource.REPLAY)
        with self.assertRaises(PermissionError):
            store.create_trial("replay", mode="REPLAY")

    def test_live_path(self):
        store = TrialStore(self.root, DataSource.LIVE)
        recorder = store.create_trial("real test", mode="MANUAL")
        self.assertEqual(recorder.directory.parent, self.root / "data" / "real" / "trials")

    def test_malformed_jsonl_is_reported_not_hidden(self):
        recorder = self.store.create_trial("broken", mode="MANUAL")
        recorder.start()
        recorder.stop("done")
        with open(recorder.directory / "frames.jsonl", "a", encoding="utf-8") as handle:
            handle.write("{not json}\n")
        record = self.store.load(recorder.metadata.trial_id)
        self.assertEqual(len(record.frames), 0)
        self.assertTrue(record.read_errors)
        self.assertTrue(summarize_trial(record)["read_errors"])

    def test_existing_trial_cannot_be_started_twice(self):
        recorder = self.store.create_trial("double", mode="MANUAL")
        recorder.start()
        with self.assertRaises(RuntimeError):
            recorder.start()
        recorder.stop("done")


if __name__ == "__main__":
    unittest.main()
