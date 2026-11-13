import json
import unittest

from tools.cup_grasp.diag_serial import DiagProtocolError, LineFramer, parse_diag_line


def hello():
    return {"type": "DIAG_HELLO", "firmware": "tactile-sense-diag-ain1-0.1.3",
            "adc1_regs": [129, 128, 192, 0], "adc2_regs": [145, 128, 192, 2],
            "adc3_regs": [129, 128, 192, 0], "fixed_mux": 9, "fixed_reg0": 145,
            "fixed_reg2": 192, "fixed_reg3": 2, "drdym": 1, "drdy_pin": 26}


def sample(seq=1, restored=True, raw="7D05DD", counts=8193501):
    return {"type": "DIAG_SAMPLE", "seq": seq, "ms": 1000, "ready": True,
            "high_seen": True, "read_ok": True, "wait_us": 3200,
            "before": [145, 128, 192, 2], "after": [145, 128, 192, 2],
            "mux_before": 9, "mux_after": 9, "vref_before": 3, "vref_after": 3,
            "reg3_before": 2, "reg3_after": 2, "restored_before_cs": restored,
            "post_cs_high": restored, "extra_clocks": 8, "raw": raw,
            "counts": counts, "volts_nominal": 3.2232, "reconfigured": False}


class DiagSerialTests(unittest.TestCase):
    def test_valid_hello_and_sample(self):
        kind, item = parse_diag_line(json.dumps(hello()).encode())
        self.assertEqual(kind, "DIAG_HELLO")
        self.assertEqual(item["fixed_reg3"], 2)
        kind, item = parse_diag_line(json.dumps(sample()).encode())
        self.assertEqual(kind, "DIAG_SAMPLE")
        self.assertEqual(item["extra_clocks"], 8)

    def test_garbage_truncated_and_interleaved_are_rejected(self):
        cases = [b"e}\n", b'{"type":"DIAG_SAMPLE"', b"\x80\x00\x80",
                 json.dumps(sample()).encode() + b" " + json.dumps(sample()).encode()]
        for raw in cases:
            with self.assertRaises(DiagProtocolError):
                parse_diag_line(raw)

    def test_bad_registers_and_clocks_are_rejected(self):
        bad = sample(); bad["after"] = [145, 128, 128, 2]
        with self.assertRaises(DiagProtocolError):
            parse_diag_line(json.dumps(bad).encode())
        bad = sample(); bad["extra_clocks"] = 1
        with self.assertRaises(DiagProtocolError):
            parse_diag_line(json.dumps(bad).encode())

    def test_framer_survives_boot_noise_and_partial_lines(self):
        framer = LineFramer()
        data = b"\x80\x00garbage\n" + json.dumps(sample()).encode() + b"\n" + b"partial"
        lines = framer.feed(data)
        self.assertEqual(len(lines), 2)  # garbage is a line but rejected by parser
        self.assertEqual(parse_diag_line(lines[1])[0], "DIAG_SAMPLE")
        lines = framer.feed(b'{"type":"DIAG_SAMPLE"}\n')  # completes and is rejected
        self.assertEqual(len(lines), 1)
        with self.assertRaises(DiagProtocolError):
            parse_diag_line(lines[0])

    def test_long_run_valid_frames(self):
        framer = LineFramer()
        good = 0
        for i in range(5000):
            lines = framer.feed((json.dumps(sample(seq=i)) + "\n").encode())
            for line in lines:
                parse_diag_line(line); good += 1
        self.assertEqual(good, 5000)


if __name__ == "__main__":
    unittest.main()
