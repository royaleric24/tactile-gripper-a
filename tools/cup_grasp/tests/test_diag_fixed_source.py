import unittest
from pathlib import Path


class FixedAin1FirmwareSourceTests(unittest.TestCase):
    def test_fixed_mux_and_raw_drdy_path_present(self):
        text = Path("firmware/sensor_diag_ain1/sensor_diag_ain1.ino").read_text()
        self.assertIn('const uint8_t FIXED_REG0 = 0x91;', text)
        self.assertIn('const uint8_t FIXED_REG2 = 0xC0;', text)
        self.assertIn('const uint8_t FIXED_REG3 = 0x02;', text)
        self.assertIn('waitDataReady', text)
        self.assertIn('post_cs_high', text)
        self.assertIn('restored_before_cs', text)
        self.assertIn('extra_clocks', text)
        self.assertIn('last_hello_ms', text)
        self.assertIn('millis() - last_hello_ms', text)
        self.assertIn('Serial.available()', text)
        driver = Path('firmware/sensor/ads1220.cpp').read_text()
        self.assertIn('8.5.6', driver)
        self.assertIn('transferByte(0x00)', driver)
        self.assertIn('readDataRaw', text)
        self.assertIn('digitalRead(drdy_pin)', text)
        self.assertIn('digitalRead(drdy_pin)', text)
        self.assertIn('readRegisters(0, before, 4)', text)
        self.assertIn('readRegisters(0, after, 4)', text)
        self.assertIn('before[0] != FIXED_REG0', text)
        self.assertNotIn('SENSOR_MUX_CODES[step]', text)


if __name__ == "__main__":
    unittest.main()
