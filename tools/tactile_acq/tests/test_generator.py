import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("generate_sensor_config", ROOT / "scripts/generate_sensor_config.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class GeneratorTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / "config/sensor_esp32.json").read_text())

    def test_valid_config(self):
        header = MODULE.generate(self.config)
        self.assertIn("SENSOR_SERIAL_BAUD = 921600UL", header)
        self.assertIn("SENSOR_DATA_RATE_CODE = 4", header)
        self.assertIn("SENSOR_CONVERSION_WAIT_US = 4500", header)
        self.assertIn("SENSOR_CS_PINS[SENSOR_ADC_COUNT] = {21, 22, 5}", header)
        self.assertIn("SENSOR_MISO_PINS[SENSOR_ADC_COUNT] = {35, 26, 34}", header)
        self.assertIn("SENSOR_REFERENCE_MODE_INITIAL = 0", header)
        self.assertIn("strapping GPIO(s) used: [5]", header)

    def test_idac_must_be_disabled(self):
        self.config["ads1220"]["idac_enabled"] = True
        with self.assertRaises(SystemExit):
            MODULE.generate(self.config)

    def test_conversion_wait_too_short(self):
        self.config["ads1220"]["conversion_wait_us"] = 3000
        with self.assertRaises(SystemExit):
            MODULE.generate(self.config)

    def test_duplicate_pins(self):
        self.config["pins"]["cs"][0] = self.config["pins"]["miso"][0]
        with self.assertRaises(SystemExit):
            MODULE.generate(self.config)

    def test_input_only_cs_rejected(self):
        self.config["pins"]["cs"][0] = 34
        self.config["pins"]["miso"][0] = 21
        with self.assertRaises(SystemExit):
            MODULE.generate(self.config)

    def test_reference_not_allowed(self):
        self.config["ads1220"]["reference_mode"] = "AVDD_AVSS"
        self.config["ads1220"]["reference_modes_allowed"] = ["INTERNAL_2V048"]
        with self.assertRaises(SystemExit):
            MODULE.generate(self.config)

    def test_bad_baud(self):
        self.config["serial_baud"] = 115200
        with self.assertRaises(SystemExit):
            MODULE.generate(self.config)


if __name__ == "__main__":
    unittest.main()
