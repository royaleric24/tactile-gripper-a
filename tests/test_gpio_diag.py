"""Host-side checks for the ADC1 GPIO_DIAG reporter. No serial access."""
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_NAME = "diag_ads1220_gpio_under_test"
SPEC = importlib.util.spec_from_file_location(MODULE_NAME, ROOT / "scripts/diag_ads1220_gpio.py")
diag = importlib.util.module_from_spec(SPEC)
sys.modules[MODULE_NAME] = diag
SPEC.loader.exec_module(diag)


def result(reset=(0, 0, 0, 0), read_a=(0x81, 0x80, 0, 0), read_b=(0x91, 0x80, 0x80, 0)):
    return {
        "reset_ok": True,
        "reset": list(reset),
        "read_a_return": True,
        "read_a": list(read_a),
        "read_b_return": True,
        "read_b": list(read_b),
    }


class GpioDiagTests(unittest.TestCase):
    def test_matching_bytes_pass(self):
        self.assertTrue(diag.true_pass(result()))

    def test_all_zero_readback_fails(self):
        self.assertFalse(diag.true_pass(result(read_a=(0, 0, 0, 0), read_b=(0, 0, 0, 0))))

    def test_floating_ff_readback_fails(self):
        self.assertFalse(diag.true_pass(result(read_a=(0xFF,) * 4, read_b=(0xFF,) * 4)))

    def test_shifted_pattern_fails(self):
        self.assertFalse(diag.true_pass(result(read_a=(0x40, 0x40, 0, 0), read_b=(0x48, 0x40, 0, 0))))

    def test_reset_before_write_required(self):
        value = result()
        value["reset_ok"] = False
        self.assertFalse(diag.true_pass(value))


if __name__ == "__main__":
    unittest.main()
