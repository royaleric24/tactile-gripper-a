import unittest

from tools.cup_grasp.single_point import VREF_ENCODINGS, summarize_single_point, validate_config_report


def channel_config():
    return {"channels": [
        {"channel_id": ch, "mux_channel": 8 + ch % 4, "adc_input": ch % 4,
         "ads1220_id": ch // 4 + 1} for ch in range(12)
    ]}


def frame_evidence():
    return {"valid0": True, "raw0": 123456, "frame_seq": 42,
            "sample_timestamp_us0": 1000000}


def report_for(reg0):
    mux = (reg0 >> 4) & 0x0F
    return {"devices": [
        {"id": i, "read_ok": True, "registers": [reg0, 0x80, 0xC0, 0x00],
         "mux": mux, "gain_code": 0, "pga_bypass": True, "vref_code": 3,
         "vref": "AVDD_AVSS", "psw": 0, "idac_code": 0}
        for i in (1, 2, 3)
    ]}


class SinglePointTests(unittest.TestCase):
    def test_five_cycles_with_contact_response(self):
        records = []
        cycles = []
        t = 0
        for cycle in range(5):
            press = (cycle * 5 + 1) * 1_000_000_000
            release = press + 2_000_000_000
            cycles.append({"press_ns": press, "release_ns": release})
            for i in range(0, 5_000_000_000, 40_000_000):
                now = t * 1_000_000_000 + i
                delta = 0.0 if not (press <= now < release) else 700.0
                # deterministic baseline noise
                if delta == 0.0:
                    delta = 10.0 if (i // 40_000_000) % 2 else -10.0
                records.append({"host_monotonic_ns": now, "delta": delta, "saturated": False})
            t += 5
        summary = summarize_single_point(records, cycles)
        self.assertEqual(summary["total_cycles"], 5)
        self.assertEqual(summary["passed_cycles"], 5)
        self.assertTrue(summary["pass"])
        for item in summary["cycles"]:
            self.assertGreater(item["snr"], 3)
            self.assertLessEqual(item["saturation_fraction"], 0.05)

    def test_scan_mode_accepts_ain3_with_channel_and_frame_evidence(self):
        result = validate_config_report(report_for(0xB1), mode="scan",
                                        channel_config=channel_config(),
                                        frame=frame_evidence())
        self.assertTrue(result["passed"])
        self.assertEqual(result["mode"], "scan")
        self.assertEqual(result["devices"][0]["mux_name"], "AIN3_AVSS")
        self.assertTrue(result["channel_evidence"]["passed"])
        self.assertTrue(result["frame_evidence"]["passed"])

    def test_scan_mode_accepts_four_legal_mux_values(self):
        for reg0 in (0x81, 0x91, 0xA1, 0xB1):
            result = validate_config_report(report_for(reg0), mode="scan",
                                            channel_config=channel_config(),
                                            frame=frame_evidence())
            self.assertTrue(result["passed"], hex(reg0))

    def test_scan_mode_rejects_ain3_without_ch0_evidence(self):
        result = validate_config_report(report_for(0xB1), mode="scan",
                                        channel_config=None, frame=None)
        self.assertFalse(result["passed"])
        self.assertFalse(result["channel_evidence"]["passed"])
        self.assertFalse(result["frame_evidence"]["passed"])

    def test_fixed_mode_requires_ain0(self):
        good = validate_config_report(report_for(0x81), mode="fixed")
        self.assertTrue(good["passed"])
        bad = validate_config_report(report_for(0xB1), mode="fixed")
        self.assertFalse(bad["passed"])

    def test_reference_pga_and_registers_still_strict(self):
        bad = report_for(0xB1)
        for item in bad["devices"]:
            item["registers"] = [0xB1, 0x80, 0x80, 0x00]
            item["vref_code"] = 2
            item["vref"] = "EXTERNAL_REFP1_REFN1"
        result = validate_config_report(bad, mode="scan", channel_config=channel_config(),
                                        frame=frame_evidence())
        self.assertFalse(result["passed"])

    def test_four_vref_encodings(self):
        self.assertEqual(VREF_ENCODINGS, {
            0: ("INTERNAL_2V048", 0x00),
            1: ("EXTERNAL_REFP0_REFN0", 0x40),
            2: ("EXTERNAL_REFP1_REFN1", 0x80),
            3: ("AVDD_AVSS", 0xC0),
        })

    def test_voltage_and_resistance_conversion(self):
        records = []
        cycles = [{"press_ns": 1_000_000_000, "release_ns": 3_000_000_000}]
        for i in range(0, 5_000_000_000, 40_000_000):
            raw = 1784000 if i < 1_000_000_000 or i >= 3_000_000_000 else 6450000
            records.append({"host_monotonic_ns": i, "delta": 0.0, "raw": raw, "saturated": False})
        summary = summarize_single_point(records, cycles, avdd_mv=3300, r_ref_ohm=10000,
                                         r_row_ohm=1000, v_exc=3.3)
        cycle = summary["cycles"][0]
        self.assertGreater(cycle["approx_contact_volts"], 2.4)
        self.assertLess(cycle["approx_contact_volts"], 2.7)
        self.assertGreater(cycle["inferred_r_cell_ohm"], 1000)
        self.assertLess(cycle["inferred_r_cell_ohm"], 3000)

    def test_saturated_cycles_fail(self):
        records = []
        cycles = [{"press_ns": 1_000_000_000, "release_ns": 3_000_000_000}]
        for i in range(0, 5_000_000_000, 40_000_000):
            records.append({"host_monotonic_ns": i, "delta": 0.0, "saturated": True})
        summary = summarize_single_point(records, cycles)
        self.assertFalse(summary["pass"])
        self.assertEqual(summary["passed_cycles"], 0)


if __name__ == "__main__":
    unittest.main()


class FirmwareScanOrderTests(unittest.TestCase):
    def test_scan_sets_mux_before_conversion_and_maps_ch0_to_ain0(self):
        from pathlib import Path
        text = Path("firmware/sensor/sensor.ino").read_text()
        scan = text[text.index("void scanFrame()"):text.index("void runDiagnostics")]
        self.assertIn("for (uint8_t step = 0; step < 4; ++step)", scan)
        self.assertIn("devices[i].setMux(SENSOR_MUX_CODES[step]);", scan)
        self.assertIn("devices[i].startConversion();", scan)
        self.assertIn("const uint8_t channel = static_cast<uint8_t>(i * 4 + step);", scan)
        self.assertLess(scan.index("devices[i].setMux(SENSOR_MUX_CODES[step]);"),
                        scan.index("devices[i].startConversion();"))
