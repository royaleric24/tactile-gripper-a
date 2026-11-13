import unittest
from pathlib import Path


class FixedAin1FirmwareSourceTests(unittest.TestCase):
    def test_fixed_mux_and_raw_drdy_path_present(self):
        text = Path("firmware/sensor_diag_ain1/sensor_diag_ain1.ino").read_text()
        self.assertIn('const uint8_t FIXED_REG0 = 0x91;', text)
        self.assertIn('const uint8_t FIXED_REG2 = 0xC0;', text)
        self.assertIn('readDataRaw', text)
        self.assertIn('digitalRead(drdy_pin)', text)
        self.assertIn('readRegisters(0, before, 4)', text)
        self.assertIn('readRegisters(0, after, 4)', text)
        self.assertIn('before[0] != FIXED_REG0', text)
        self.assertNotIn('SENSOR_MUX_CODES[step]', text)


if __name__ == "__main__":
    unittest.main()
