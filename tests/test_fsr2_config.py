"""Offline checks for the V2 FSR firmware configuration and generated header.

These tests never touch hardware. They pin the board facts that the V2 plan
freezes (four ADS1220, ADC4 = CS32/MISO33, AVDD/AVSS reference for the divider
measurement) and prove that the committed generated header matches its JSON
source, so a silent pin or reference regression fails here.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FSR_CONFIG = ROOT / "config" / "sensor_esp32_fsr2.json"
HYBRID_CONFIG = ROOT / "config" / "sensor_esp32_fsr2_hybrid.json"
FSR_HEADER = ROOT / "firmware" / "sensor_fsr2" / "fsr2_config.h"
HYBRID_HEADER = ROOT / "firmware" / "sensor_fsr2" / "fsr2_config_hybrid.h"


def load_generator():
    path = ROOT / "scripts" / "generate_sensor_fsr2_config.py"
    spec = importlib.util.spec_from_file_location("generate_sensor_fsr2_config", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


GENERATOR = load_generator()


def load(path: Path) -> dict:
    return json.loads(path.read_text())


class BoardFactTests(unittest.TestCase):
    """The frozen V2 wiring facts, as consumed by the generator."""

    def test_fsr_config_pins(self) -> None:
        config = load(FSR_CONFIG)
        self.assertEqual(config["pins"]["sclk"], 18)
        self.assertEqual(config["pins"]["mosi"], 23)
        self.assertEqual(config["pins"]["miso"], [34, 35, 26, 33])
        self.assertEqual(config["pins"]["cs"], [21, 22, 5, 32])
        self.assertEqual(config["sensor_profile"], "FSR_ONLY")

    def test_adc4_owns_the_two_fsr_channels(self) -> None:
        config = load(FSR_CONFIG)
        self.assertEqual(config["fsr"]["adc_id"], 4)
        self.assertEqual(config["fsr"]["adc4_cs_gpio"], 32)
        self.assertEqual(config["fsr"]["adc4_miso_gpio"], 33)
        inputs = [channel["adc_input"] for channel in config["fsr"]["channels"]]
        self.assertEqual(inputs, [0, 1])
        self.assertTrue(config["fsr"]["independent_pulldowns_required"])
        self.assertFalse(config["fsr"]["validated"])

    def test_fsr_measurement_uses_avdd_reference(self) -> None:
        config = load(FSR_CONFIG)
        adc = config["ads1220"]
        self.assertEqual(adc["reference_mode"], "AVDD_AVSS")
        self.assertEqual(adc["reference_modes_allowed"], ["AVDD_AVSS"])
        self.assertEqual(adc["gain"], 1)
        self.assertTrue(adc["pga_bypass"])
        self.assertFalse(adc["idac_enabled"])
        self.assertEqual(adc["data_rate_sps"], 330)

    def test_legacy_three_adc_mapping_is_not_reused(self) -> None:
        config = load(FSR_CONFIG)
        self.assertNotEqual(config["pins"]["miso"], [35, 26, 34])
        self.assertEqual(len(config["pins"]["cs"]), 4)
        self.assertIn(32, config["pins"]["cs"])

    def test_serial_baud_is_the_device_value(self) -> None:
        for path in (FSR_CONFIG, HYBRID_CONFIG):
            self.assertEqual(load(path)["serial_baud"], 921600, path.name)

    def test_hybrid_profile_extends_without_blocking_fsr(self) -> None:
        hybrid = load(HYBRID_CONFIG)
        self.assertEqual(hybrid["sensor_profile"], "HYBRID_6X6_FSR2")
        self.assertEqual(hybrid["matrix"]["rows"], 6)
        self.assertEqual(hybrid["matrix"]["column_pins"], [4, 13, 14, 25, 27, 19])
        self.assertEqual([channel["channel_id"] for channel in hybrid["fsr"]["channels"]], [36, 37])
        self.assertEqual(hybrid["matrix"]["validated"], False)


class GeneratorValidationTests(unittest.TestCase):
    """Every rejected mutation corresponds to a wiring or measurement bug."""

    def generate_from(self, config: dict) -> str:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "config.json"
            source.write_text(json.dumps(config))
            output = Path(temporary) / "header.h"
            GENERATOR.generate(source, output)
            return output.read_text()

    def assert_rejected(self, config: dict, needle: str) -> None:
        with self.assertRaises(SystemExit) as raised:
            self.generate_from(config)
        self.assertIn(needle, str(raised.exception))

    def test_rejects_three_adc_mapping(self) -> None:
        config = copy.deepcopy(load(FSR_CONFIG))
        config["pins"]["miso"] = [35, 26, 34]
        config["pins"]["cs"] = [21, 22, 5]
        self.assert_rejected(config, "exactly 4")

    def test_rejects_internal_reference_for_fsr(self) -> None:
        config = copy.deepcopy(load(FSR_CONFIG))
        config["ads1220"]["reference_mode"] = "INTERNAL_2V048"
        config["ads1220"]["reference_modes_allowed"] = ["INTERNAL_2V048"]
        self.assert_rejected(config, "AVDD_AVSS")

    def test_rejects_gain_above_one_for_fsr(self) -> None:
        config = copy.deepcopy(load(FSR_CONFIG))
        config["ads1220"]["gain"] = 2
        self.assert_rejected(config, "gain")

    def test_rejects_adc4_select_on_another_pin(self) -> None:
        config = copy.deepcopy(load(FSR_CONFIG))
        config["fsr"]["adc4_cs_gpio"] = 5
        self.assert_rejected(config, "fourth chip select")

    def test_rejects_adc4_miso_on_another_pin(self) -> None:
        config = copy.deepcopy(load(FSR_CONFIG))
        config["fsr"]["adc4_miso_gpio"] = 34
        self.assert_rejected(config, "miso")

    def test_rejects_slow_conversion_wait(self) -> None:
        config = copy.deepcopy(load(FSR_CONFIG))
        config["ads1220"]["conversion_wait_us"] = 100
        self.assert_rejected(config, "conversion_wait_us")

    def test_rejects_duplicate_chip_select(self) -> None:
        config = copy.deepcopy(load(FSR_CONFIG))
        config["pins"]["cs"] = [21, 22, 5, 21]
        self.assert_rejected(config, "share a GPIO")

    def test_rejects_flash_pin_as_column(self) -> None:
        config = copy.deepcopy(load(HYBRID_CONFIG))
        config["matrix"]["column_pins"][0] = 6
        self.assert_rejected(config, "flash")

    def test_rejects_hybrid_row_order(self) -> None:
        config = copy.deepcopy(load(HYBRID_CONFIG))
        config["matrix"]["row_inputs"] = list(reversed(config["matrix"]["row_inputs"]))
        self.assert_rejected(config, "row_inputs")

    def test_rejects_fsr_channel_not_last(self) -> None:
        config = copy.deepcopy(load(FSR_CONFIG))
        config["fsr"]["channels"][0]["channel_id"] = 5
        config["fsr"]["channels"][1]["channel_id"] = 6
        self.assert_rejected(config, "last channel ids")

    def test_rejects_oversized_line(self) -> None:
        config = copy.deepcopy(load(FSR_CONFIG))
        config["stream"]["max_line_bytes"] = 20000
        self.assert_rejected(config, "max_line_bytes")


class GeneratedHeaderTests(unittest.TestCase):
    """The committed header must be reproducible from its JSON source."""

    def test_fsr_header_matches_generator(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "fsr2_config.h"
            GENERATOR.generate(FSR_CONFIG, output)
            self.assertEqual(output.read_text(), FSR_HEADER.read_text())

    def test_hybrid_header_matches_generator(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "fsr2_config_hybrid.h"
            GENERATOR.generate(HYBRID_CONFIG, output)
            self.assertEqual(output.read_text(), HYBRID_HEADER.read_text())

    def test_fsr_header_content(self) -> None:
        text = FSR_HEADER.read_text()
        self.assertIn("static const uint8_t FSR2_MISO_PINS[4] = {34, 35, 26, 33};", text)
        self.assertIn("static const uint8_t FSR2_CS_PINS[4] = {21, 22, 5, 32};", text)
        self.assertIn('"FSR_ONLY"', text)
        self.assertIn("3,  // reference_mode_code", text)
        self.assertIn("4,  // data_rate_code", text)
        self.assertIn("FSR2_KIND_FSR", text)
        self.assertNotIn("FSR2_KIND_MATRIX_CELL", text)

    def test_hybrid_header_content(self) -> None:
        text = HYBRID_HEADER.read_text()
        self.assertIn("static const uint8_t FSR2_COLUMN_PINS[6] = {4, 13, 14, 25, 27, 19};", text)
        self.assertIn("38", text)
        self.assertIn('"R6C6"', text)
        self.assertIn('"FSR_A"', text)


class ScriptSurfaceTests(unittest.TestCase):
    """The scripts the handoff asks the next engineer to run must exist and parse."""

    def test_scripts_exist(self) -> None:
        for name in (
            "generate_sensor_fsr2_config.py",
            "build_sensor_fsr2_firmware.py",
            "run_fsr2_host_tests.py",
            "check_fsr2_frames.py",
        ):
            path = ROOT / "scripts" / name
            self.assertTrue(path.is_file(), name)

    def test_scripts_are_valid_python(self) -> None:
        for name in ("generate_sensor_fsr2_config.py", "run_fsr2_host_tests.py",
                     "check_fsr2_frames.py", "build_sensor_fsr2_firmware.py"):
            result = subprocess.run(
                [sys.executable, "-m", "py_compile", str(ROOT / "scripts" / name)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
