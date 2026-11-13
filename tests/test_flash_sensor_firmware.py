"""Regression tests for the esptool identity parser in scripts/flash_sensor_firmware.py.

All outputs here are captured/fabricated text: these tests never open a serial
port, never run esptool and never write flash.  They exist because esptool v5.1.0
replaced the old "Chip is ESP32..." line with "Chip type: ... (revision v1.1)"
and emits ANSI cursor-control sequences.
"""
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
MODULE_NAME = "flash_sensor_firmware_under_test"
SPEC = importlib.util.spec_from_file_location(MODULE_NAME, ROOT / "scripts/flash_sensor_firmware.py")
flash = importlib.util.module_from_spec(SPEC)
sys.modules[MODULE_NAME] = flash
SPEC.loader.exec_module(flash)

# Verbatim esptool v5.1.0 `chip-id` output from the old ESP32 (MAC
# 02:00:00:00:00:01), including the CSI cursor moves and colour escapes.
REAL_V5_OUTPUT = (
    "\n"
    "esptool v5.1.0\n"
    "Serial port /dev/cu.usbserial-EXAMPLE_ESP32:\n"
    "Connecting......\n"
    "Detecting chip type... ESP32\n"
    "\x1b[1A\x1b[2K\x1b[1A\x1b[2K\x1b[1A\x1b[2KConnected to ESP32 on /dev/cu.usbserial-EXAMPLE_ESP32:\n"
    "Chip type:          ESP32-D0WDQ6 (revision v1.1)\n"
    "Features:           Wi-Fi, BT, Dual Core + LP Core, 240MHz, Vref calibration in eFuse, Coding Scheme None\n"
    "Crystal frequency:  40MHz\n"
    "MAC:                02:00:00:00:00:01\n"
    "\n"
    "Uploading stub flasher...\n"
    "Running stub flasher...\n"
    "\x1b[1A\x1b[2K\x1b[1A\x1b[2K\x1b[1A\x1b[2KStub flasher running.\n"
    "Changing baud rate to 460800...\n"
    "Changed.\n"
    "\n"
    "\x1b[0;33mWarning:\x1b[0m ESP32 has no chip ID. Reading MAC address instead.\n"
    "MAC:                02:00:00:00:00:01\n"
    "\n"
    "Hard resetting via RTS pin...\n"
)

OLD_FORMAT_OUTPUT = "Chip is ESP32-D0WDQ6 (revision 1)\nMAC: 02:00:00:00:00:01\n"


def load_board():
    return json.loads((ROOT / "config/board_esp32_tactile.json").read_text())


class ParseIdentityTests(unittest.TestCase):
    def test_real_esptool_v5_output_with_ansi(self):
        identity = flash.parse_identity(REAL_V5_OUTPUT)
        self.assertEqual(identity.model, "ESP32-D0WDQ6")
        self.assertEqual(identity.family, "ESP32")
        self.assertEqual(identity.revision, "v1.1")
        self.assertEqual(identity.mac, "02:00:00:00:00:01")

    def test_old_esptool_format_still_accepted(self):
        identity = flash.parse_identity(OLD_FORMAT_OUTPUT)
        self.assertEqual(identity.model, "ESP32-D0WDQ6")
        self.assertEqual(identity.revision, "1")
        self.assertEqual(identity.mac, "02:00:00:00:00:01")

    def test_ansi_inside_chip_and_mac_lines(self):
        output = (
            "\x1b[1A\x1b[2K\x1b[1mChip type:\x1b[0m          \x1b[32mESP32-D0WDQ6\x1b[0m (revision v1.1)\n"
            "\x1b[0;33mWarning:\x1b[0m ESP32 has no chip ID.\n"
            "MAC:\x1b[0m                02:00:00:00:00:01\n"
        )
        identity = flash.parse_identity(output)
        self.assertEqual(identity.model, "ESP32-D0WDQ6")
        self.assertEqual(identity.mac, "02:00:00:00:00:01")

    def test_case_whitespace_and_revision_suffix(self):
        output = "CHIP TYPE :   ESP32-D0WDQ6   ( REVISION   V1.1 )\nmac address = 02:00:00:00:00:01\n"
        identity = flash.parse_identity(output)
        self.assertEqual(identity.model, "ESP32-D0WDQ6")
        self.assertEqual(identity.revision, "V1.1")
        self.assertEqual(identity.mac, "02:00:00:00:00:01")

    def test_cr_line_endings(self):
        output = "Chip type:  ESP32-D0WDQ6 (revision v1.1)\rMAC: 02:00:00:00:00:01\r"
        self.assertEqual(flash.parse_identity(output).mac, "02:00:00:00:00:01")

    def test_conflicting_mac_lines_refused(self):
        output = REAL_V5_OUTPUT.replace(
            "MAC:                02:00:00:00:00:01\n\nHard resetting",
            "MAC:                02:00:00:00:00:02\n\nHard resetting",
        )
        with self.assertRaises(flash.IdentityError) as ctx:
            flash.parse_identity(output)
        self.assertIn("conflicting MAC", str(ctx.exception))

    def test_conflicting_chip_lines_refused(self):
        output = REAL_V5_OUTPUT + "Chip type: ESP32-S3 (revision v0.2)\n"
        with self.assertRaises(flash.IdentityError) as ctx:
            flash.parse_identity(output)
        self.assertIn("conflicting chip", str(ctx.exception))

    def test_missing_mac_refused(self):
        output = "Chip type: ESP32-D0WDQ6 (revision v1.1)\n"
        with self.assertRaises(flash.IdentityError) as ctx:
            flash.parse_identity(output)
        self.assertIn("MAC", str(ctx.exception))

    def test_missing_chip_refused(self):
        output = "Detecting chip type... ESP32\nMAC: 02:00:00:00:00:01\n"
        with self.assertRaises(flash.IdentityError) as ctx:
            flash.parse_identity(output)
        self.assertIn("chip model", str(ctx.exception))


class VerifyIdentityTests(unittest.TestCase):
    def setUp(self):
        self.board = load_board()

    def extract(self, output):
        return flash.parse_identity(output)

    def test_real_identity_accepted(self):
        flash.verify_identity(self.extract(REAL_V5_OUTPUT), self.board)

    def test_wrong_mac_refused(self):
        output = REAL_V5_OUTPUT.replace("02:00:00:00:00:01", "02:00:00:00:00:02")
        with self.assertRaises(flash.IdentityError) as ctx:
            flash.verify_identity(self.extract(output), self.board)
        self.assertIn("MAC", str(ctx.exception))
        self.assertIn("02:00:00:00:00:02", str(ctx.exception))

    def test_esp32_s3_refused(self):
        output = REAL_V5_OUTPUT.replace("ESP32-D0WDQ6", "ESP32-S3 (QFN56)")
        with self.assertRaises(flash.IdentityError) as ctx:
            flash.verify_identity(self.extract(output), self.board)
        self.assertIn("ESP32-S3", str(ctx.exception))

    def test_other_esp32_model_refused(self):
        # Same family but not the configured chip: strict model check must fail.
        output = REAL_V5_OUTPUT.replace("ESP32-D0WDQ6", "ESP32-D0WD-V3")
        with self.assertRaises(flash.IdentityError) as ctx:
            flash.verify_identity(self.extract(output), self.board)
        self.assertIn("ESP32-D0WD-V3", str(ctx.exception))

    def test_missing_board_expectations_refused(self):
        with self.assertRaises(flash.IdentityError) as ctx:
            flash.verify_identity(self.extract(REAL_V5_OUTPUT), {})
        self.assertIn("board config", str(ctx.exception))


class MainIdentityGateTests(unittest.TestCase):
    """main() must refuse before issuing read-flash/write-flash/verify-flash."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = Path(self.tmp.name) / "sensor.ino.bin"
        self.app.write_bytes(b"\x00" * 1024)

    def run_main(self, output, returncode=0):
        calls = []

        def fake_run(cmd, log_path=None):
            calls.append(list(cmd))
            return returncode, output

        argv = [
            "flash_sensor_firmware.py",
            "--port", "/dev/cu.usbserial-EXAMPLE_ESP32",
            "--authorize-write",
            "--backup-dir", self.tmp.name,
        ]
        stdout = io.StringIO()
        with mock.patch.object(flash, "APP_BIN", self.app), \
                mock.patch.object(flash, "find_esptool", return_value="esptool-fake"), \
                mock.patch.object(flash, "run", side_effect=fake_run), \
                mock.patch.object(sys, "argv", argv), \
                redirect_stdout(stdout):
            with self.assertRaises(SystemExit) as ctx:
                flash.main()
        return calls, str(ctx.exception), stdout.getvalue()

    def commands(self, calls):
        return [cmd[-1] for cmd in calls]

    def test_wrong_mac_refused_before_backup(self):
        calls, message, _ = self.run_main(REAL_V5_OUTPUT.replace("02:00:00:00:00:01", "02:00:00:00:00:02"))
        self.assertIn("refusing device", message)
        self.assertIn("MAC", message)
        self.assertEqual(self.commands(calls), ["chip-id"])

    def test_s3_refused_before_backup(self):
        calls, message, _ = self.run_main(REAL_V5_OUTPUT.replace("ESP32-D0WDQ6", "ESP32-S3 (QFN56)"))
        self.assertIn("refusing device", message)
        self.assertIn("ESP32-S3", message)
        self.assertEqual(self.commands(calls), ["chip-id"])

    def test_unparseable_output_refused(self):
        calls, message, _ = self.run_main("esptool v5.1.0\nChip type: ESP32-D0WDQ6\nNo MAC here\n")
        self.assertTrue(message.startswith("could not parse chip/MAC from esptool output"))
        self.assertEqual(self.commands(calls), ["chip-id"])

    def test_v5_identity_accepted_then_stops_when_backup_fails(self):
        # chip-id succeeds and is accepted; read-flash fails, so no write occurs.
        calls = []

        def fake_run(cmd, log_path=None):
            calls.append(list(cmd))
            if "chip-id" in cmd:
                return 0, REAL_V5_OUTPUT
            return 1, "read failed"

        argv = [
            "flash_sensor_firmware.py",
            "--port", "/dev/cu.usbserial-EXAMPLE_ESP32",
            "--authorize-write",
            "--backup-dir", self.tmp.name,
        ]
        stdout = io.StringIO()
        with mock.patch.object(flash, "APP_BIN", self.app), \
                mock.patch.object(flash, "find_esptool", return_value="esptool-fake"), \
                mock.patch.object(flash, "run", side_effect=fake_run), \
                mock.patch.object(sys, "argv", argv), \
                redirect_stdout(stdout):
            with self.assertRaises(SystemExit) as ctx:
                flash.main()
        self.assertIn("identity OK: chip=ESP32-D0WDQ6", stdout.getvalue())
        self.assertIn("flash backup failed", str(ctx.exception))
        self.assertEqual(len(calls), 2)
        self.assertIn("chip-id", calls[0])
        self.assertIn("read-flash", calls[1])
        self.assertFalse(any("write-flash" in cmd or "verify-flash" in cmd for cmd in calls))


if __name__ == "__main__":
    unittest.main()
