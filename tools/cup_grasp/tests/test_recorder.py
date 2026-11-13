import json
import tempfile
import unittest
from pathlib import Path

from tools.cup_grasp.session import run_simulated


class RecorderTests(unittest.TestCase):
    def test_simulated_fixed_trial_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_simulated("fixed", Path("config/cup_grasp.simulated.json"), 1.0, root=Path(tmp))
            run = Path(result["dir"])
            for name in ("meta.json", "tactile.jsonl", "gripper_commands.jsonl",
                         "load_events.jsonl", "trial_events.jsonl", "metrics.json", "REPORT.md"):
                self.assertTrue((run / name).is_file(), name)
            meta = json.loads((run / "meta.json").read_text())
            self.assertEqual(meta["data_kind"], "SIMULATED")
            metrics = json.loads((run / "metrics.json").read_text())
            self.assertEqual(metrics["data_kind"], "SIMULATED")
            self.assertGreater(metrics["tactile_frames"], 0)
            self.assertIn("SIMULATED", (run / "REPORT.md").read_text())

    def test_simulated_feedback_trial_reaches_hold_or_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_simulated("feedback", Path("config/cup_grasp.simulated.json"), 3.0, root=Path(tmp))
            metrics = result["metrics"]
            self.assertIn(metrics["control"]["state"], ("HOLD", "RELEASE"))
            self.assertIsNone(metrics["control"]["fault_reason"])
            self.assertGreater(metrics["tactile_frames"], 0)


if __name__ == "__main__":
    unittest.main()
