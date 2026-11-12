"""Offline ESP32-S3 board-profile and 14-bit conversion checks; no serial."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads((ROOT / path).read_text())


class S3ConfigTests(unittest.TestCase):
    def setUp(self):
        self.s3 = load("config/gripper_s3.json")
        self.old = load("config/gripper_bench.json")
        self.board = load("config/board_s3.json")

    def test_board_profile(self):
        self.assertEqual(self.s3["gpio"], 4)
        self.assertEqual(self.s3["frequency_hz"], 50)
        self.assertEqual(self.s3["resolution_bits"], 14)
        self.assertEqual(self.s3["firmware_version"], "gripper-control-s3-0.9b26.0")
        self.assertEqual(self.s3["bench_min_us"], 500)
        self.assertEqual(self.s3["bench_max_us"], 2500)
        self.assertEqual(self.s3["bench_hold_ms"], 5000)
        self.assertEqual(self.s3["readback_settle_ms"], 25)
        self.assertEqual(self.s3["first_readback_settle_ms"], 25)
        self.assertIs(self.s3["hardware_enabled"], False)
        self.assertEqual(self.s3["calibration_state"], "UNCALIBRATED")

    def test_old_target_is_untouched(self):
        self.assertEqual(self.old["gpio"], 23)
        self.assertEqual(self.old["resolution_bits"], 16)
        self.assertEqual(self.old["firmware_version"], "gripper-control-bench-0.9b24.0")

    def test_firmware_handshake_versions_match_but_targets_differ(self):
        self.assertEqual(self.s3["serial"]["firmware_version"], self.s3["firmware_version"])
        self.assertEqual(self.old["serial"]["firmware_version"], self.old["firmware_version"])
        self.assertNotEqual(self.s3["firmware_version"], self.old["firmware_version"])

    def test_s3_build_profile(self):
        self.assertEqual(self.board["fqbn"], "esp32:esp32:esp32s3")
        options = self.board["fqbn_options"]
        self.assertEqual(options["FlashSize"], "16M")
        self.assertEqual(options["PSRAM"], "opi")
        self.assertEqual(options["PartitionScheme"], "app3M_fat9M_16MB")
        self.assertEqual(self.board["storage"]["flash_bytes"], 16 * 1024 * 1024)
        self.assertEqual(self.board["storage"]["psram_bytes"], 8 * 1024 * 1024)

    def test_14bit_duty_conversion(self):
        def duty(us, hz=50, bits=14):
            if us >= 1000000 // hz:
                return 0
            return (us * hz * (1 << bits) + 500000) // 1000000

        self.assertEqual(duty(500), 410)
        self.assertEqual(duty(1150), 942)
        self.assertEqual(duty(1200), 983)
        self.assertEqual(duty(1400), 1147)
        self.assertEqual(duty(1500), 1229)
        self.assertEqual(duty(2500), 2048)
        self.assertEqual(duty(20000), 0)
        # The old target keeps its 16-bit result.
        self.assertEqual((1500 * 50 * (1 << 16) + 500000) // 1000000, 4915)

    def test_console_has_no_fixed_s3_port(self):
        source = (ROOT / "scripts/pwm_console.py").read_text()
        self.assertNotIn("/dev/cu.usbserial-EXAMPLE_ESP32", source)
        self.assertNotIn("/dev/cu.usbserial-EXAMPLE_S3", source)
        self.assertIn('"s3"', source)
        self.assertIn("--list-ports", source)


if __name__ == "__main__":
    unittest.main()
