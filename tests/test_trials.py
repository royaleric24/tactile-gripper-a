"""Trial storage tests: JSONL, metadata, CSV and source isolation."""

import csv
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from tactile_gripper.devices.sensor import default_demo_config
from tactile_gripper.errors import TrialWriteError
from tactile_gripper.experiments.store import TrialStore, comparison_summary, summarize_trial, trial_integrity
from tactile_gripper.models import ControlAction, ControlCommand, ControlEvent, TrialMetadata
from tactile_gripper.sources import DataSource

from support import FailingWriter, frame


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
        with self.assertRaises(RuntimeError):
            recorder.start()

    def test_schema_version_and_git_commit_metadata(self):
        recorder = self.store.create_trial("schema", mode="MANUAL", git_commit="a" * 40)
        metadata = json.loads((recorder.directory / "metadata.json").read_text())
        self.assertEqual(metadata["schema_version"], 3)
        self.assertEqual(metadata["git_commit"], "a" * 40)
        legacy = dict(metadata)
        legacy.pop("schema_version")
        parsed = TrialMetadata.from_dict(legacy)
        self.assertEqual(parsed.schema_version, 1)

    def test_interrupted_trial_is_recovered_not_completed(self):
        recorder = self.store.create_trial("crash", mode="MANUAL")
        recorder.start()
        recorder.record_frame(frame(seq=1, source=DataSource.SIMULATION))
        recorder.record_frame(frame(seq=2, source=DataSource.SIMULATION))
        recorder.close()
        lock_path = recorder.directory / "recording.json"
        lock = json.loads(lock_path.read_text())
        lock["pid"] = 999999  # definitely dead in this test process
        lock["heartbeat_ns"] = 0
        lock_path.write_text(json.dumps(lock))

        recovered = self.store.recover_interrupted()
        self.assertEqual(recovered, [recorder.metadata.trial_id])
        record = self.store.load(recorder.metadata.trial_id)
        self.assertEqual(record.metadata.status, "INTERRUPTED")
        self.assertIsNotNone(record.metadata.ended_at)
        self.assertEqual(len(record.frames), 2)
        self.assertTrue(any(item.get("event_type") == "TRIAL_INTERRUPTED" for item in record.events))
        summary = summarize_trial(record)
        self.assertFalse(summary["integrity"]["complete"])
        self.assertTrue(summary["integrity"]["interrupted"])
        self.assertFalse(lock_path.exists())
        self.assertTrue((recorder.directory / "frames.csv").is_file())

    def test_completed_trial_is_not_recovered(self):
        recorder = self.store.create_trial("normal", mode="MANUAL")
        recorder.start()
        recorder.record_frame(frame(seq=1, source=DataSource.SIMULATION))
        recorder.stop("done")
        self.assertEqual(self.store.recover_interrupted(), [])
        self.assertEqual(self.store.load(recorder.metadata.trial_id).metadata.status, "COMPLETED")

    def test_active_recording_is_not_marked_interrupted(self):
        recorder = self.store.create_trial("active", mode="MANUAL")
        recorder.start()
        recorder.record_frame(frame(seq=1, source=DataSource.SIMULATION))
        self.assertEqual(self.store.recover_interrupted(), [])
        self.assertEqual(recorder.metadata.status, "RECORDING")
        recorder.stop("done")

    def test_missing_lock_is_recovered(self):
        recorder = self.store.create_trial("no-lock", mode="MANUAL")
        recorder.start()
        recorder.record_frame(frame(seq=1, source=DataSource.SIMULATION))
        recorder.close()
        (recorder.directory / "recording.json").unlink()
        recovered = self.store.recover_interrupted()
        self.assertEqual(recovered, [recorder.metadata.trial_id])
        self.assertEqual(self.store.load(recorder.metadata.trial_id).metadata.status, "INTERRUPTED")

    def test_frame_write_failure_marks_error_and_preserves_prior_data(self):
        recorder = self.store.create_trial("disk", mode="MANUAL")
        recorder.start()
        recorder.record_frame(frame(seq=1, source=DataSource.SIMULATION))
        recorder._frame_file.close()
        recorder._frame_file = FailingWriter()
        with self.assertRaises(TrialWriteError):
            recorder.record_frame(frame(seq=2, source=DataSource.SIMULATION))
        self.assertEqual(recorder.metadata.status, "ERROR")
        self.assertIsNotNone(recorder.metadata.write_error)
        self.assertFalse((recorder.directory / "recording.json").exists())
        record = self.store.load(recorder.metadata.trial_id)
        self.assertEqual(record.metadata.status, "ERROR")
        self.assertEqual(len(record.frames), 1)
        self.assertTrue(summarize_trial(record)["integrity"]["error"])

    def test_integrity_counts_invalid_channels_gaps_and_restarts(self):
        recorder = self.store.create_trial("integrity", mode="MANUAL")
        recorder.start()
        recorder.record_frame(
            frame(seq=1, values=[10, None, 30, 40], mask=[True, False, True, True], source=DataSource.SIMULATION)
        )
        recorder.record_frame(frame(seq=3, source=DataSource.SIMULATION))
        recorder.record_frame(frame(seq=1, boot_id="boot-2", source=DataSource.SIMULATION))
        recorder.stop("done")
        record = self.store.load(recorder.metadata.trial_id)
        integrity = trial_integrity(record)
        self.assertEqual(integrity["frames"], 3)
        self.assertEqual(integrity["invalid_channel_samples"], 1)
        self.assertEqual(integrity["frames_with_invalid_channels"], 1)
        self.assertEqual(integrity["dropped_frames"], 1)
        self.assertEqual(integrity["restarts"], 1)

    def test_video_operator_tags_and_video_update(self):
        recorder = self.store.create_trial(
            "video", mode="MANUAL", video_path="/tmp/capture.mp4", operator="eric", tags=["cup", "silicone"]
        )
        metadata = json.loads((recorder.directory / "metadata.json").read_text())
        self.assertEqual(metadata["video_path"], "/tmp/capture.mp4")
        self.assertEqual(metadata["operator"], "eric")
        self.assertEqual(metadata["tags"], ["cup", "silicone"])
        recorder.set_video_path("/tmp/capture-2.mp4")
        self.assertEqual(recorder.metadata.video_path, "/tmp/capture-2.mp4")
        self.assertEqual(recorder.metadata.schema_version, 3)
        # Attaching video before Start must not create a recording lock.
        self.assertFalse((recorder.directory / "recording.json").exists())
        recorder.start()
        recorder.stop("done")

    def test_incomplete_final_jsonl_line_is_ignored_and_reported(self):
        recorder = self.store.create_trial("tail", mode="MANUAL")
        recorder.start()
        recorder.record_frame(frame(seq=1, source=DataSource.SIMULATION))
        recorder.stop("done")
        with open(recorder.directory / "frames.jsonl", "ab") as handle:
            handle.write(b'{"record_type":"SENSOR_FRAME","frame_seq":2')
        record = self.store.load(recorder.metadata.trial_id)
        self.assertTrue(record.truncated_tail)
        self.assertEqual(len(record.frames), 1)
        self.assertTrue(any("incomplete final line" in item for item in record.read_errors))
        self.assertTrue(summarize_trial(record)["integrity"]["truncated_tail"])

    def test_trial_ids_are_unique(self):
        recorder = self.store.create_trial("unique", mode="MANUAL")
        trial_ids = {recorder.metadata.trial_id}
        for _ in range(5):
            trial_ids.add(self.store.create_trial("unique", mode="MANUAL").metadata.trial_id)
        self.assertEqual(len(trial_ids), 6)

    def test_comparison_summary_is_read_only_and_source_tagged(self):
        first = self.store.create_trial("first", mode="MANUAL", video_path="/tmp/first.mov")
        first.start()
        first.record_frame(frame(seq=1, source=DataSource.SIMULATION))
        first.stop("done")
        second = self.store.create_trial("second", mode="MANUAL")
        second.start()
        second.record_frame(frame(seq=1, source=DataSource.SIMULATION))
        second.stop("done")
        row1 = comparison_summary(self.store.load(first.metadata.trial_id))
        row2 = comparison_summary(self.store.load(second.metadata.trial_id))
        self.assertEqual(row1["source"], "SIMULATION")
        self.assertEqual(row1["video"], "/tmp/first.mov")
        self.assertEqual(row1["frames"], 1)
        self.assertNotEqual(row1["trial_id"], row2["trial_id"])

    def test_git_commit_is_recorded_in_integrity_metadata(self):
        recorder = self.store.create_trial("git", mode="MANUAL", git_commit="b" * 40)
        metadata = json.loads((recorder.directory / "metadata.json").read_text())
        self.assertEqual(metadata["git_commit"], "b" * 40)
        self.assertEqual(metadata["schema_version"], 3)


if __name__ == "__main__":
    unittest.main()
