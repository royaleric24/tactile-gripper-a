"""Long-run/shutdown/lock reliability tests; all SIMULATION."""

import json
import tempfile
import unittest
from collections import deque
from pathlib import Path

from tactile_gripper.control import ApplicationCore, Mode, build_core
from tactile_gripper.errors import TrialWriteError
from tactile_gripper.experiments.store import TrialRecorder, TrialStore
from tactile_gripper.models import TrialMetadata
from tactile_gripper.sources import DataSource

from support import frame


class ShutdownAndLongRunTests(unittest.TestCase):
    def test_short_continuous_run_is_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            core = build_core(source="SIMULATION", root=tmp)
            core.connect_gripper()
            core.begin_manual_session()
            core.set_demo_stream(True)
            core.create_trial("long run")
            core.start_trial()
            for _ in range(300):
                core.tick()
            self.assertLessEqual(len(core.events), core.events.maxlen)
            self.assertGreaterEqual(core.event_overflow_count, 0)
            self.assertGreater(core.trial.frame_count, 0)
            stopped = core.stop_trial("done")
            self.assertEqual(stopped["status"], "COMPLETED")
            core.shutdown()
            self.assertFalse(core.gripper.connected)

    def test_shutdown_aborts_recording_and_closes_resources(self):
        with tempfile.TemporaryDirectory() as tmp:
            core = build_core(source="SIMULATION", root=tmp)
            core.connect_gripper()
            core.begin_manual_session()
            core.set_demo_stream(True)
            core.create_trial("shutdown")
            core.start_trial()
            core.tick()
            trial_id = core.trial.metadata.trial_id
            core.shutdown()
            self.assertIsNone(core.trial)
            self.assertFalse(core.gripper.connected)
            self.assertFalse(core.sensor.connected)
            record = TrialStore(Path(tmp), DataSource.SIMULATION).load(trial_id)
            self.assertEqual(record.metadata.status, "ABORTED")
            self.assertIsNotNone(record.metadata.ended_at)

    def test_event_overflow_is_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            core = ApplicationCore(root=tmp, source=DataSource.SIMULATION)
            core.events = deque(maxlen=2)
            for index in range(5):
                core._system("TEST", f"event {index}")
            self.assertEqual(len(core.events), 2)
            self.assertEqual(core.event_overflow_count, 3)


class LockConflictTests(unittest.TestCase):
    def test_second_recorder_cannot_start_active_trial(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TrialStore(Path(tmp), DataSource.SIMULATION)
            recorder = store.create_trial("lock", mode="MANUAL")
            recorder.start()
            duplicate = TrialRecorder(
                TrialMetadata(
                    trial_id=recorder.metadata.trial_id,
                    name="duplicate",
                    source=DataSource.SIMULATION,
                    mode="MANUAL",
                    status="CREATED",
                ),
                recorder.directory,
            )
            with self.assertRaises(TrialWriteError):
                duplicate.start()
            recorder.stop("done")

    def test_core_list_recovers_dead_recording(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = TrialStore(Path(tmp), DataSource.SIMULATION)
            recorder = store.create_trial("crash", mode="MANUAL")
            recorder.start()
            recorder.record_frame(frame(seq=1, source=DataSource.SIMULATION))
            recorder.close()
            lock = json.loads((recorder.directory / "recording.json").read_text())
            lock["pid"] = 999999
            lock["heartbeat_ns"] = 0
            (recorder.directory / "recording.json").write_text(json.dumps(lock))
            core = ApplicationCore(root=tmp, source=DataSource.SIMULATION)
            items = core.list_trials()
            self.assertEqual(items[0]["status"], "INTERRUPTED")
            self.assertEqual(core.recovered_trials, [recorder.metadata.trial_id])


if __name__ == "__main__":
    unittest.main()
