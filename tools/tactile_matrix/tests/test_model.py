import unittest

from tools.tactile_matrix.model import (
    CELL_COUNT,
    MatrixFrameError,
    build_frame,
    cell_coord,
    cell_index,
    cell_label,
    flag_names,
    validate_frame,
    FLAG_NEAR_RAIL,
)


class ModelTests(unittest.TestCase):
    def test_coordinates(self):
        self.assertEqual(cell_index(1, 1), 0)
        self.assertEqual(cell_index(6, 6), 35)
        self.assertEqual(cell_coord(0), (1, 1))
        self.assertEqual(cell_label(7), "R2C2")
        with self.assertRaises(ValueError):
            cell_index(0, 1)
        with self.assertRaises(ValueError):
            cell_coord(36)

    def test_valid_frame(self):
        cells = [1000 + index for index in range(CELL_COUNT)]
        message = build_frame(1, 1000, cells, [True] * CELL_COUNT, [0] * CELL_COUNT, 60000)
        frame = validate_frame(message)
        self.assertEqual(frame.valid_count, 36)
        self.assertEqual(frame.value(1, 1), 1000)
        self.assertEqual(frame.value(6, 6), 1035)
        self.assertEqual(frame.frame_period_us, 60000)

    def test_invalid_cell_must_be_null(self):
        cells = [None] + [1000] * (CELL_COUNT - 1)
        valid = [False] + [True] * (CELL_COUNT - 1)
        message = build_frame(1, 1000, cells, valid, [0] * CELL_COUNT)
        frame = validate_frame(message)
        self.assertFalse(frame.valid[0])
        self.assertEqual(frame.valid_count, 35)
        bad = dict(message)
        bad["cells"] = [0] + [1000] * (CELL_COUNT - 1)
        with self.assertRaises(MatrixFrameError):
            validate_frame(bad)

    def test_wrong_length_rejected(self):
        with self.assertRaises(MatrixFrameError):
            build_frame(1, 1000, [1] * 35, [True] * 35, [0] * 35)
        cells = [1] * 35
        with self.assertRaises(MatrixFrameError):
            validate_frame({"type": "MATRIX_FRAME", "protocol_version": 1, "scan_mode": "ROW_SCAN_6X6",
                            "rows": 6, "cols": 6, "cell_order": "ROW_MAJOR_R1C1", "frame_seq": 1,
                            "timestamp_us": 1, "cells": cells, "valid": [True] * 36, "flags": [0] * 36})

    def test_flag_names(self):
        self.assertEqual(flag_names(FLAG_NEAR_RAIL | 0x01), ["SAT_HIGH", "NEAR_RAIL"])


if __name__ == "__main__":
    unittest.main()
