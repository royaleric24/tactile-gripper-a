import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from tools.tactile_acq.recorder import RunRecorder
from tools.tactile_acq.tests.fixtures import make_sample
from tools.tactile_experiment import analysis  # noqa: F401  (import smoke)
from scripts.tactile_36point_experiment import SerialReader


class FakeSession:
    def __init__(self, lines):
        self.lines = list(lines)

    def read_available(self):
        if not self.lines:
            return []
        time.sleep(0.002)
        return [self.lines.pop(0)]


class ReaderTests(unittest.TestCase):
    def test_reader_thread_records_frames_and_events(self):
        identity = SimpleNamespace(
            device_id="tactile-esp32-01", boot_id="boot", firmware_version="tactile-sense-0.1.0",
            channel_count=12, reference_mode="INTERNAL_2V048", streaming=True,
            adc_status=[], port="/dev/fake", port_info={},
        )
        lines = []
        for seq in range(1, 6):
            message = make_sample(seq=seq, timestamp_us=seq * 40000, values=[seq * 100 + i for i in range(12)])
            lines.append((json.dumps(message, separators=(",", ":")) + "\n").encode())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recorder = RunRecorder(root, "/dev/fake", 921600, identity, {"test": True})
            lock = threading.Lock()
            reader = SerialReader(FakeSession(lines), recorder, lock)
            reader.start()
            deadline = time.time() + 2.0
            while reader.latest is None and time.time() < deadline:
                time.sleep(0.005)
            with lock:
                recorder.record_event("TEST_EVENT", point_id=1)
            reader.stop()
            reader.join(timeout=2.0)
            run = recorder.finalize()
            self.assertGreaterEqual(run["summary"]["samples"], 1)
            self.assertTrue((root / "raw_frames.jsonl").is_file())
            self.assertTrue((root / "samples.csv").is_file())
            event_lines = (root / "events.jsonl").read_text().splitlines()
            self.assertTrue(any("TEST_EVENT" in line for line in event_lines))
            self.assertIsNotNone(reader.latest)
            self.assertIsNone(reader.error)


if __name__ == "__main__":
    unittest.main()
