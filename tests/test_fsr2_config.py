"""Offline checks for the V2 firmware configuration and generated headers.

These tests pin the board facts that the 2026-11-15 wiring correction froze
(four ADS1220, ADC4 = CS32/MISO33, twelve passive electrodes with 10 kOhm row
pulldowns and 1 kOhm column pullups, no GPIO column drive) and prove that every
committed generated header matches its JSON source.
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
ELECTRODE_CONFIG = ROOT / "config" / "sensor_esp32_electrodes12.json"
ELECTRODE_FSR_CONFIG = ROOT / "config" / "sensor_esp32_electrodes12_fsr2.json"
FSR_HEADER = ROOT / "firmware" / "sensor_fsr2" / "fsr2_config.h"
ELECTRODE_HEADER = ROOT / "firmware" / "sensor_fsr2" / "fsr2_config_electrodes12.h"
ELECTRODE_FSR_HEADER = ROOT / "firmware" / "sensor_fsr2" / "fsr2_config_electrodes12_fsr2.h"


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

    def test_spi_pins(self) -> None:
        for path in (FSR_CONFIG, ELECTRODE_CONFIG, ELECTRODE_FSR_CONFIG):
            config = load(path)
            self.assertEqual(config["pins"]["sclk"], 18, path.name)
            self.assertEqual(config["pins"]["mosi"], 23, path.name)
            self.assertEqual(config["pins"]["miso"], [34, 35, 26, 33], path.name)
            self.assertEqual(config["pins"]["cs"], [21, 22, 5, 32], path.name)

    def test_adc4_keeps_the_two_fsr_channels(self) -> None:
        config = load(ELECTRODE_FSR_CONFIG)
        self.assertEqual(config["fsr"]["adc_id"], 4)
        self.assertEqual(config["fsr"]["adc4_cs_gpio"], 32)
        self.assertEqual(config["fsr"]["adc4_miso_gpio"], 33)
        self.assertEqual([channel["adc_input"] for channel in config["fsr"]["channels"]], [0, 1])
        self.assertTrue(config["fsr"]["independent_pulldowns_required"])
        self.assertFalse(config["fsr"]["validated"])

    def test_fsr_measurement_uses_avdd_reference(self) -> None:
        for path in (FSR_CONFIG, ELECTRODE_CONFIG, ELECTRODE_FSR_CONFIG):
            adc = load(path)["ads1220"]
            self.assertEqual(adc["reference_mode"], "AVDD_AVSS", path.name)
            self.assertEqual(adc["reference_modes_allowed"], ["AVDD_AVSS"], path.name)
            self.assertEqual(adc["gain"], 1, path.name)
            self.assertTrue(adc["pga_bypass"], path.name)
            self.assertFalse(adc["idac_enabled"], path.name)
            self.assertEqual(adc["data_rate_sps"], 330, path.name)

    def test_legacy_three_adc_mapping_is_not_reused(self) -> None:
        config = load(ELECTRODE_CONFIG)
        self.assertNotEqual(config["pins"]["miso"], [35, 26, 34])
        self.assertEqual(len(config["pins"]["cs"]), 4)
        self.assertIn(32, config["pins"]["cs"])

    def test_serial_baud_is_the_device_value(self) -> None:
        for path in (FSR_CONFIG, ELECTRODE_CONFIG, ELECTRODE_FSR_CONFIG):
            self.assertEqual(load(path)["serial_baud"], 921600, path.name)

    def test_electrode_topology_is_passive(self) -> None:
        for path in (ELECTRODE_CONFIG, ELECTRODE_FSR_CONFIG):
            config = load(path)
            self.assertIsNone(config["matrix"], path.name)
            electrodes = config["electrodes"]
            self.assertEqual(electrodes["count"], 12, path.name)
            self.assertEqual(electrodes["rows"], 6, path.name)
            self.assertEqual(electrodes["columns"], 6, path.name)
            self.assertEqual(electrodes["row_bias"], "PULLDOWN_10K_TO_GND", path.name)
            self.assertEqual(electrodes["column_bias"], "PULLUP_1K_TO_3V3", path.name)
            self.assertFalse(electrodes["gpio_excitation"], path.name)
            self.assertEqual(electrodes["map"], [], path.name)
            self.assertEqual(electrodes["mapping_status"], "PENDING_REAL_WIRING", path.name)

    def test_no_invented_electrode_mapping(self) -> None:
        electrodes = load(ELECTRODE_FSR_CONFIG)["electrodes"]
        self.assertEqual(electrodes["map"], [])
        for entry in electrodes["map"]:
            self.assertNotIn("adc_id", entry)
            self.assertNotIn("adc_input", entry)


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

    def test_rejects_withdrawn_hybrid_profile(self) -> None:
        config = copy.deepcopy(load(ELECTRODE_FSR_CONFIG))
        config["sensor_profile"] = "HYBRID_6X6_FSR2"
        self.assert_rejected(config, "withdrawn")

    def test_rejects_three_adc_mapping(self) -> None:
        config = copy.deepcopy(load(FSR_CONFIG))
        config["pins"]["miso"] = [35, 26, 34]
        config["pins"]["cs"] = [21, 22, 5]
        self.assert_rejected(config, "exactly 4")

    def test_rejects_internal_reference(self) -> None:
        config = copy.deepcopy(load(FSR_CONFIG))
        config["ads1220"]["reference_mode"] = "INTERNAL_2V048"
        config["ads1220"]["reference_modes_allowed"] = ["INTERNAL_2V048"]
        self.assert_rejected(config, "AVDD_AVSS")

    def test_rejects_gain_above_one(self) -> None:
        config = copy.deepcopy(load(FSR_CONFIG))
        config["ads1220"]["gain"] = 2
        self.assert_rejected(config, "gain")

    def test_rejects_adc4_select_on_another_pin(self) -> None:
        config = copy.deepcopy(load(FSR_CONFIG))
        config["fsr"]["adc4_cs_gpio"] = 5
        self.assert_rejected(config, "fourth chip select")

    def test_rejects_gpio_column_excitation(self) -> None:
        config = copy.deepcopy(load(ELECTRODE_CONFIG))
        config["electrodes"]["gpio_excitation"] = True
        self.assert_rejected(config, "gpio_excitation")

    def test_rejects_wrong_row_bias(self) -> None:
        config = copy.deepcopy(load(ELECTRODE_CONFIG))
        config["electrodes"]["row_bias"] = "PULLUP_1K_TO_3V3"
        self.assert_rejected(config, "row_bias")

    def test_rejects_wrong_electrode_count(self) -> None:
        config = copy.deepcopy(load(ELECTRODE_CONFIG))
        config["electrodes"]["count"] = 10
        self.assert_rejected(config, "the pressure cloth has 12 electrodes")

    def test_rejects_partial_map(self) -> None:
        config = copy.deepcopy(load(ELECTRODE_CONFIG))
        config["electrodes"]["mapping_status"] = "TABLE_PROVIDED"
        config["electrodes"]["map"] = [
            {"electrode": "R1", "adc_id": 1, "adc_input": 0}
        ]
        self.assert_rejected(config, "all 12 electrodes")

    def test_rejects_duplicate_ain(self) -> None:
        config = copy.deepcopy(load(ELECTRODE_CONFIG))
        config["electrodes"]["mapping_status"] = "TABLE_PROVIDED"
        config["electrodes"]["map"] = [
            {"electrode": name, "adc_id": 1, "adc_input": 0}
            for name in ["R1", "R2", "R3", "R4", "R5", "R6", "C1", "C2", "C3", "C4", "C5", "C6"]
        ]
        self.assert_rejected(config, "already taken")

    def test_rejects_electrode_on_the_fsr_adc(self) -> None:
        config = copy.deepcopy(load(ELECTRODE_FSR_CONFIG))
        config["electrodes"]["mapping_status"] = "TABLE_PROVIDED"
        mapping = []
        for index, name in enumerate(
            ["R1", "R2", "R3", "R4", "R5", "R6", "C1", "C2", "C3", "C4", "C5", "C6"]
        ):
            mapping.append(
                {
                    "electrode": name,
                    "adc_id": 4 if index == 0 else 1 + index // 4,
                    "adc_input": index % 4,
                }
            )
        config["electrodes"]["map"] = mapping
        self.assert_rejected(config, "FSR ADC")

    def test_rejects_oversized_line(self) -> None:
        config = copy.deepcopy(load(FSR_CONFIG))
        config["stream"]["max_line_bytes"] = 20000
        self.assert_rejected(config, "max_line_bytes")


class GeneratedHeaderTests(unittest.TestCase):
    """Every committed header must be reproducible from its JSON source."""

    def _check(self, config: Path, header: Path, filename: str) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / filename
            GENERATOR.generate(config, output)
            self.assertEqual(output.read_text(), header.read_text())

    def test_fsr_header_matches_generator(self) -> None:
        self._check(FSR_CONFIG, FSR_HEADER, "fsr2_config.h")

    def test_electrode_header_matches_generator(self) -> None:
        self._check(ELECTRODE_CONFIG, ELECTRODE_HEADER, "fsr2_config_electrodes12.h")

    def test_electrode_fsr_header_matches_generator(self) -> None:
        self._check(ELECTRODE_FSR_CONFIG, ELECTRODE_FSR_HEADER, "fsr2_config_electrodes12_fsr2.h")

    def test_current_single_fsr_headers_are_reproducible_and_require_confirmed_input(self) -> None:
        for profile, count in (("fsr1", 1), ("electrodes12_fsr1", 13)):
            with self.subTest(profile=profile), tempfile.TemporaryDirectory() as temporary:
                path = ROOT / "config" / f"sensor_esp32_{profile}.json"
                filename = f"fsr2_config_{profile}.h"
                header = FSR_HEADER.parent / filename
                self._check(path, header, filename)
                config = load(path)
                self.assertEqual(config["fsr"]["channels"], [
                    {"channel_id": count - 1, "name": "FSR_A", "adc_input": 0, "mux_code": 8}
                ])
                config["fsr"]["channels"][0].update(adc_input=1, mux_code=9)
                rejected = Path(temporary) / "wrong-input.json"
                rejected.write_text(json.dumps(config))
                with self.assertRaisesRegex(SystemExit, "ADC4 AIN0"):
                    GENERATOR.generate(rejected, Path(temporary) / filename)

    def test_fsr_header_content(self) -> None:
        text = FSR_HEADER.read_text()
        self.assertIn("static const uint8_t FSR2_MISO_PINS[4] = {34, 35, 26, 33};", text)
        self.assertIn("static const uint8_t FSR2_CS_PINS[4] = {21, 22, 5, 32};", text)
        self.assertIn('"FSR_ONLY"', text)
        self.assertIn("3,  // reference_mode_code", text)
        self.assertIn("4,  // data_rate_code", text)
        self.assertNotIn("FSR2_KIND_ELECTRODE", text)

    def test_electrode_header_content(self) -> None:
        text = ELECTRODE_HEADER.read_text()
        self.assertIn('"MATRIX_ELECTRODES_12"', text)
        self.assertIn('"PENDING_REAL_WIRING"', text)
        self.assertIn('"PULLDOWN_10K_TO_GND"', text)
        self.assertIn('"PULLUP_1K_TO_3V3"', text)
        self.assertIn("255, 255, 255, FSR2_KIND_ELECTRODE, FSR2_ROLE_ROW, 1, \"R1\"", text)
        self.assertIn("12,  // electrode_count", text)
        self.assertIn("0,  // fsr_count", text)
        self.assertNotIn("FSR2_COLUMN_PINS", text)

    def test_electrode_fsr_header_content(self) -> None:
        text = ELECTRODE_FSR_HEADER.read_text()
        self.assertIn("14,  // channel_count", text)
        self.assertIn("static const uint8_t FSR2_FSR_CHANNEL_INDICES[2] = {12, 13};", text)
        self.assertIn('"FSR_A"', text)
        self.assertIn('"C6"', text)


class ScriptSurfaceTests(unittest.TestCase):
    """The scripts the handoff asks the next engineer to run must exist and parse."""

    def test_scripts_exist(self) -> None:
        for name in (
            "generate_sensor_fsr2_config.py",
            "build_sensor_fsr2_firmware.py",
            "run_fsr2_host_tests.py",
            "check_fsr2_frames.py",
        ):
            self.assertTrue((ROOT / "scripts" / name).is_file(), name)

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
