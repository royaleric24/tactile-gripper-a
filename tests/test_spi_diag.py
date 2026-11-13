"""Host-side verification of the ADS1220 DIAG_SPI raw-byte reporter.

No serial access: these tests feed synthetic firmware responses and check that
the host independently re-compares the returned bytes with the two patterns.
"""
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_NAME = "diag_ads1220_spi_under_test"
SPEC = importlib.util.spec_from_file_location(MODULE_NAME, ROOT / "scripts/diag_ads1220_spi.py")
diag = importlib.util.module_from_spec(SPEC)
sys.modules[MODULE_NAME] = diag
SPEC.loader.exec_module(diag)


def edge(reset=(0, 0, 0, 0), read_a=(0x81, 0x80, 0, 0), read_b=(0x91, 0x80, 0x80, 0), reset_ok=True):
    return {
        "reset_ok": reset_ok,
        "reset": list(reset),
        "write_a_return": True,
        "read_a_return": True,
        "read_a": list(read_a),
        "read_a_ok": list(read_a) == [0x81, 0x80, 0, 0],
        "write_b_return": True,
        "read_b_return": True,
        "read_b": list(read_b),
        "read_b_ok": list(read_b) == [0x91, 0x80, 0x80, 0],
        "pass": True,  # deliberately ignored by the host
    }


def payload(rising, falling, adc=1):
    return {
        "devices": [
            {
                "adc": adc,
                "cs": 21,
                "miso": 34,
                "idle_miso": 0,
                "after_miso": 0,
                "edges": {"after_rising": rising, "after_falling": falling},
            }
        ]
    }


class SpiDiagTests(unittest.TestCase):
    def test_matching_bytes_pass(self):
        summary = diag.summarize(payload(edge(), edge()))
        self.assertEqual(len(summary["rows"]), 2)
        self.assertTrue(summary["any_pass"])
        self.assertTrue(all(row["pass"] for row in summary["rows"]))

    def test_all_zero_readback_fails(self):
        summary = diag.summarize(payload(edge(read_a=(0, 0, 0, 0), read_b=(0, 0, 0, 0)), edge(read_a=(0, 0, 0, 0), read_b=(0, 0, 0, 0))))
        self.assertFalse(summary["any_pass"])
        self.assertTrue(all(not row["read_a_ok"] and not row["read_b_ok"] for row in summary["rows"]))

    def test_shifted_pattern_fails_even_if_firmware_says_pass(self):
        summary = diag.summarize(payload(edge(read_a=(0x40, 0x40, 0, 0), read_b=(0x48, 0x40, 0, 0)), edge()))
        first = summary["rows"][0]
        self.assertFalse(first["read_a_ok"])
        self.assertTrue(first["firmware_pass"])
        self.assertFalse(first["pass"])
        # The second edge still genuinely passes.
        self.assertTrue(summary["any_pass"])

    def test_reset_failure_fails(self):
        summary = diag.summarize(payload(edge(reset_ok=False), edge(reset_ok=False)))
        self.assertFalse(summary["any_pass"])


if __name__ == "__main__":
    unittest.main()


class SpiDiagProtocolTests(unittest.TestCase):
    def test_status_with_spi_diag_and_request_id_parses(self):
        from tools.tactile_acq.protocol import parse_message

        line = (
            b'{"protocol_version":1,"type":"STATUS","device_id":"tactile-esp32-01",'
            b'"boot_id":"b","firmware_version":"tactile-sense-0.1.0",'
            b'"sensor_state":"STOPPED","streaming":false,"channel_count":12,'
            b'"spi_diag":{"slow_half_period_us":25,"devices":[]},"request_id":"rid-1"}'
        )
        message = parse_message(line)
        self.assertEqual(message.request_id, "rid-1")
        self.assertFalse(message.streaming)
        self.assertEqual(message.raw["spi_diag"]["slow_half_period_us"], 25)
