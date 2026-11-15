import unittest

from tools.tactile_matrix.analysis import (
    baseline_from_frames,
    contact_metric,
    crosstalk_ratio,
    delta_map,
    localize,
    repeatability,
)
from tools.tactile_matrix.model import CELL_COUNT, build_frame, cell_index, validate_frame


def frame(value=10000, extra=None, seq=1):
    cells = [value] * CELL_COUNT
    if extra:
        for index, delta in extra.items():
            cells[index] += delta
    return validate_frame(build_frame(seq, seq * 60000, cells, [True] * CELL_COUNT, [0] * CELL_COUNT, 60000))


class AnalysisTests(unittest.TestCase):
    def test_baseline_and_delta(self):
        frames = [frame(10000, seq=i) for i in range(1, 5)]
        baseline = baseline_from_frames(frames)
        self.assertEqual(baseline.mean[0], 10000)
        pressed = frame(10000, extra={cell_index(3, 4): 5000}, seq=5)
        delta = delta_map(pressed, baseline)
        self.assertEqual(delta[cell_index(3, 4)], 5000)
        self.assertEqual(delta[0], 0)

    def test_localization_peak_and_centroid(self):
        frames = [frame(10000, seq=i) for i in range(1, 4)]
        baseline = baseline_from_frames(frames)
        pressed = frame(10000, extra={cell_index(3, 4): 5000, cell_index(3, 3): 1000}, seq=4)
        delta = delta_map(pressed, baseline)
        result = localize(delta, threshold=100)
        self.assertEqual(result["peak_cell"], "R3C4")
        self.assertAlmostEqual(result["centroid_row"], 3.0, places=3)
        self.assertLess(result["centroid_column"], 4.0)
        self.assertGreater(result["centroid_column"], 3.0)

    def test_crosstalk_ratio(self):
        frames = [frame(10000, seq=i) for i in range(1, 4)]
        baseline = baseline_from_frames(frames)
        target = cell_index(2, 2)
        pressed = frame(10000, extra={target: 1000, cell_index(2, 3): 100}, seq=4)
        delta = delta_map(pressed, baseline)
        self.assertAlmostEqual(crosstalk_ratio(delta, target), 0.1, places=6)

    def test_contact_metric(self):
        frames = [frame(10000, seq=i) for i in range(1, 4)]
        baseline = baseline_from_frames(frames)
        pressed = frame(10000, extra={cell_index(1, 1): 800, cell_index(1, 2): 300}, seq=4)
        delta = delta_map(pressed, baseline)
        metric = contact_metric(delta, baseline, k=3.0)
        self.assertEqual(metric["active_count"], 2)
        self.assertIn("R1C1", metric["active_cells"])
        self.assertEqual(metric["localization"]["peak_cell"], "R1C1")

    def test_repeatability(self):
        frames = [frame(10000 + i, seq=i) for i in range(1, 4)]
        result = repeatability(frames)
        self.assertEqual(len(result["cells"]), 36)
        self.assertGreater(result["cells"][0]["cv"], 0)


if __name__ == "__main__":
    unittest.main()
