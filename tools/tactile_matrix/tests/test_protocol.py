import unittest

from tools.tactile_matrix.model import CELL_COUNT, MatrixFrameError
from tools.tactile_matrix.protocol import encode_matrix_frame, parse_matrix_line
from tools.tactile_matrix.model import FLAG_NEAR_RAIL


class ProtocolTests(unittest.TestCase):
    def test_round_trip(self):
        cells = [1000 + i for i in range(CELL_COUNT)]
        flags = [0] * CELL_COUNT
        flags[5] = FLAG_NEAR_RAIL
        raw = encode_matrix_frame(7, 420000, cells, [True] * CELL_COUNT, flags, 63000)
        frame = parse_matrix_line(raw)
        self.assertEqual(frame.frame_seq, 7)
        self.assertEqual(frame.timestamp_us, 420000)
        self.assertEqual(frame.frame_period_us, 63000)
        self.assertEqual(frame.cells[5], 1005)
        self.assertEqual(frame.flags[5], FLAG_NEAR_RAIL)
        self.assertEqual(frame.raw["scan_mode"], "ROW_SCAN_6X6")

    def test_invalid_json_rejected(self):
        with self.assertRaises(Exception):
            parse_matrix_line(b"{not json}\n")

    def test_invalid_cell_count_rejected(self):
        raw = encode_matrix_frame(1, 1, [1] * CELL_COUNT, [True] * CELL_COUNT, [0] * CELL_COUNT)
        import json
        message = json.loads(raw)
        message["cells"] = message["cells"][:-1]
        with self.assertRaises(MatrixFrameError):
            from tools.tactile_matrix.model import validate_frame
            validate_frame(message)


if __name__ == "__main__":
    unittest.main()
