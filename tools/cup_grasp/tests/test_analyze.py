import tempfile
import unittest
from pathlib import Path

from tools.cup_grasp.analyze import summarize_root, write_summary
from tools.cup_grasp.session import run_simulated


class AnalyzeTests(unittest.TestCase):
    def test_simulated_trials_are_not_real(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_simulated("fixed", Path("config/cup_grasp.simulated.json"), 0.5, root=Path(tmp))
            analysis = summarize_root(Path(tmp))
            self.assertEqual(analysis["real_trials"], 0)
            self.assertEqual(analysis["simulated_trials"], 1)
            self.assertEqual(analysis["trials"][0]["status"], "SIMULATED")
            write_summary(Path(tmp), analysis)
            self.assertTrue((Path(tmp) / "SUMMARY.csv").is_file())
            self.assertTrue((Path(tmp) / "REPORT.md").is_file())


if __name__ == "__main__":
    unittest.main()
