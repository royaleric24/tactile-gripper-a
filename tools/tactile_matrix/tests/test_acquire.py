import json
import tempfile
import unittest
from pathlib import Path

from tools.tactile_matrix.acquire import MatrixRecorder, record_session
from tools.tactile_matrix.model import CELL_COUNT, load_config
from tools.tactile_matrix.protocol import encode_matrix_frame


class FakeSession:
    def __init__(self, lines):
        self.lines = list(lines)

    def read_available(self):
        if not self.lines:
            return []
        return [self.lines.pop(0)]

    def close(self):
        pass


class AcquireTests(unittest.TestCase):
    def test_record_and_finalize(self):
        config = load_config()
        with tempfile.TemporaryDirectory() as tmp:
            recorder = MatrixRecorder(Path(tmp), "/dev/fake", 921600, config)
            frames = [
                encode_matrix_frame(1, 60000, [1000 + i for i in range(CELL_COUNT)], [True] * CELL_COUNT, [0] * CELL_COUNT, 60000),
                encode_matrix_frame(2, 120000, [1000 + i for i in range(CELL_COUNT)], [True] * CELL_COUNT, [0] * CELL_COUNT, 60000),
                b"not json\n",
            ]
            run = record_session(FakeSession(frames), 0.05, recorder, poll_s=0.001)
            self.assertEqual(run["frames"], 2)
            self.assertEqual(run["parse_errors"], 1)
            self.assertAlmostEqual(run["summary"]["valid_ratio"], 1.0)
            self.assertTrue((Path(tmp) / "raw_frames.jsonl").is_file())
            self.assertTrue((Path(tmp) / "cells.csv").is_file())
            self.assertTrue((Path(tmp) / "run.json").is_file())
            data = json.loads((Path(tmp) / "run.json").read_text())
            self.assertEqual(data["frames"], 2)
            self.assertIn("raw_frames.jsonl", data["file_sha256"])
            csv_lines = (Path(tmp) / "cells.csv").read_text().splitlines()
            self.assertEqual(len(csv_lines), 1 + 2 * CELL_COUNT)

    def test_no_data_run(self):
        config = load_config()
        with tempfile.TemporaryDirectory() as tmp:
            recorder = MatrixRecorder(Path(tmp), "/dev/fake", 921600, config)
            run = record_session(FakeSession([]), 0.01, recorder, poll_s=0.001)
            self.assertEqual(run["frames"], 0)
            self.assertEqual(run["data_kind"], "NO_DATA")
            self.assertIsNone(run["measured_frame_rate_hz"])


if __name__ == "__main__":
    unittest.main()
