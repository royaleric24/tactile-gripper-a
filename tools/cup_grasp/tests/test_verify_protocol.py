import json
import unittest

from scripts.verify_single_point_config import ConfigResponseError, wait_config_report


class FakeSession:
    def __init__(self, malformed=False, include_sample=False):
        self.malformed = malformed
        self.include_sample = include_sample
        self.sent = []
        self._lines = []

    def send_command(self, cmd, value=None, target_id=None, request_id=None):
        self.sent.append((cmd, value, request_id))
        if cmd != "VERIFY_CONFIG":
            return request_id
        sample = {"protocol_version": 1, "type": "SAMPLE", "device_id": "x", "boot_id": "b",
                  "frame_seq": 1, "timestamp_us": 1, "raw_adc": [1] * 12, "valid": [True] * 12,
                  "sample_timestamp_us": [1] * 12, "channel_flags": [0] * 12}
        status = {"protocol_version": 1, "type": "STATUS", "device_id": "x", "boot_id": "b",
                  "firmware_version": "0.1.3", "sensor_state": "STREAMING", "streaming": True,
                  "config_report": {"devices": [
                      {"id": i, "read_ok": True, "registers": [0x81, 0x80, 0xC0, 0x00],
                       "mux": 8, "gain_code": 0, "pga_bypass": True, "vref_code": 3,
                       "vref": "AVDD_AVSS", "psw": 0, "idac_code": 0} for i in (1, 2, 3)]},
                  "request_id": request_id}
        if self.include_sample:
            self._lines.append((json.dumps(sample) + "\n").encode())
        if self.malformed:
            # reproduce the old bug: root is closed before request_id is appended
            broken = dict(status)
            broken.pop("request_id", None)
            text = json.dumps(broken) + ',"request_id":"' + request_id + '"}\n'
            self._lines.append(text.encode())
        else:
            self._lines.append((json.dumps(status) + "\n").encode())
        return request_id

    def read_available(self):
        lines, self._lines = self._lines, []
        return lines


class VerifyProtocolTests(unittest.TestCase):
    def test_valid_config_report_survives_interleaved_sample(self):
        session = FakeSession(include_sample=True)
        report, diagnostics = wait_config_report(session, timeout_s=0.5, attempts=1)
        self.assertEqual(len(report["devices"]), 3)
        self.assertEqual(report["devices"][0]["registers"], [0x81, 0x80, 0xC0, 0x00])
        self.assertGreaterEqual(len(diagnostics["raw_lines"]), 2)

    def test_malformed_old_response_reports_raw_lines(self):
        session = FakeSession(malformed=True)
        with self.assertRaises(ConfigResponseError) as ctx:
            wait_config_report(session, timeout_s=0.15, attempts=1)
        self.assertTrue(ctx.exception.raw_lines)
        self.assertTrue(any("config_report" in line for line in ctx.exception.raw_lines))


if __name__ == "__main__":
    unittest.main()
