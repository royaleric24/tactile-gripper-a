import unittest

from tools.cup_grasp.single_point import summarize_single_point, validate_config_report


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

    def test_register_report_avdd(self):
        report = {"devices": [
            {"id": i, "read_ok": True, "registers": [0x81, 0x80, 0x80, 0x00],
             "mux": 8, "gain_code": 0, "pga_bypass": True, "vref_code": 2,
             "vref": "AVDD_AVSS", "psw": 0, "idac_code": 0}
            for i in (1, 2, 3)
        ]}
        result = validate_config_report(report)
        self.assertTrue(result["passed"])
        bad = {"devices": [dict(item) for item in report["devices"]]}
        for item in bad["devices"]:
            item["registers"] = [0x81, 0x80, 0xC0, 0x00]
            item["vref_code"] = 3
            item["vref"] = "EXTERNAL_REFP1_REFN1"
        self.assertFalse(validate_config_report(bad)["passed"])

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
