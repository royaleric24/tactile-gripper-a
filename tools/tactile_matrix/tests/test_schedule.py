import unittest

from tools.tactile_matrix.model import cell_index
from tools.tactile_matrix.schedule import (
    MatrixTiming,
    Phase,
    ScanStateMachine,
    covered_cells,
    iter_frame_actions,
    summarize,
)


class ScheduleTests(unittest.TestCase):
    def test_default_timing_and_coverage(self):
        timing = MatrixTiming(pre_discharge_us=200, settle_us=1000, conversion_wait_us=4500)
        summary = summarize(timing)
        self.assertEqual(summary["rounds"], 2)
        self.assertEqual(summary["row_period_us"], 10500)
        self.assertEqual(summary["frame_period_us"], 63000)
        self.assertAlmostEqual(summary["frame_rate_hz"], 15.873, places=3)
        self.assertEqual(summary["covered_cells"], 36)
        self.assertEqual(summary["unique_cells"], 36)
        self.assertTrue(summary["all_cells_once"])

    def test_scan_order_and_row_states(self):
        actions = list(iter_frame_actions(MatrixTiming(settle_us=500)))
        phases = [(a.phase, a.row) for a in actions]
        self.assertEqual(phases[0], (Phase.DISCHARGE, 1))
        self.assertEqual(phases[1], (Phase.SETTLE, 1))
        self.assertIn((Phase.CONVERT, 1), phases)
        self.assertIn((Phase.CONVERT, 6), phases)
        # No row is selected before DISCHARGE and no conversion happens before SETTLE.
        for index, action in enumerate(actions):
            if action.phase == Phase.SETTLE:
                self.assertEqual(actions[index - 1].phase, Phase.DISCHARGE)
            if action.phase == Phase.CONVERT:
                self.assertIn(actions[index - 1].phase, (Phase.SETTLE, Phase.READ))
        cells = covered_cells(actions)
        self.assertEqual(sorted(cells), list(range(36)))

    def test_state_machine_fills_36_cells(self):
        machine = ScanStateMachine(MatrixTiming(settle_us=500)).run(value=1234)
        self.assertTrue(machine.finished)
        self.assertEqual(machine.valid, [True] * 36)
        self.assertEqual(machine.cells, [1234] * 36)
        self.assertLessEqual(machine.elapsed_us, 60000)
        for row in (1, 6):
            for column in (1, 6):
                self.assertEqual(machine.cells[cell_index(row, column)], 1234)

    def test_round_columns(self):
        timing = MatrixTiming()
        self.assertEqual(timing.columns_for_round(0), (1, 3, 5))
        self.assertEqual(timing.columns_for_round(1), (2, 4, 6))


if __name__ == "__main__":
    unittest.main()
