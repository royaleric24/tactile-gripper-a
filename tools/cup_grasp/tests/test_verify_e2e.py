import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import scripts.verify_single_point_config as verifier
from tools.tactile_acq.protocol import parse_hello
from tools.tactile_acq.transport import DeviceIdentity


def channel_config():
    return {"status": "IMPLEMENTED", "scan_mode": "SINGLE_SHOT_3X4", "channels": [
        {"channel_id": ch, "mux_channel": 8 + ch % 4, "adc_input": ch % 4,
         "ads1220_id": ch // 4 + 1, "enabled": True, "unit": "ADC_COUNTS"}
        for ch in range(12)
    ]}


def hello_dict(include_channel_config=True):
    value = {"protocol_version": 1, "type": "HELLO", "device_id": "tactile-esp32-01",
             "boot_id": "boot-1", "firmware_version": "tactile-sense-0.1.3",
             "channel_count": 12, "channel_ids": list(range(12)),
             "reference_mode": "AVDD_AVSS", "streaming": True}
    if include_channel_config:
        value["channel_config"] = channel_config()
    return value


def sample_dict():
    return {"protocol_version": 1, "type": "SAMPLE", "device_id": "tactile-esp32-01",
            "boot_id": "boot-1", "firmware_version": "tactile-sense-0.1.3",
            "frame_seq": 7, "timestamp_us": 1000000,
            "raw_adc": [123456] + [0] * 11, "valid": [True] * 12,
            "sample_timestamp_us": [1000000 + i for i in range(12)],
            "channel_flags": [0] * 12,
            "adc_status": [{"id": i, "state": "OK"} for i in (1, 2, 3)],
            "reference_mode": "AVDD_AVSS",
            "effective_frame_rate_hz": 46.7}


def status_dict(request_id, config=False):
    value = {"protocol_version": 1, "type": "STATUS", "device_id": "tactile-esp32-01",
             "boot_id": "boot-1", "firmware_version": "tactile-sense-0.1.3",
             "sensor_state": "STREAMING", "streaming": True,
             "reference_mode": "AVDD_AVSS", "request_id": request_id}
    if config:
        value["config_report"] = {"devices": [
            {"id": i, "read_ok": True, "registers": [0xB1, 0x80, 0xC0, 0x00],
             "mux": 11, "gain_code": 0, "pga_bypass": True, "vref_code": 3,
             "vref": "AVDD_AVSS", "psw": 0, "idac_code": 0} for i in (1, 2, 3)
        ]}
    return value


class FakeSession:
    def __init__(self, identity, lines):
        self.identity = identity
        self.lines = list(lines)
        self.sent = []
        self.closed = False
        self.pending_after_config = False

    def open(self):
        pass

    def identify(self, timeout_s=8.0):
        return self.identity

    def send_command(self, cmd, value=None, target_id=None, request_id=None):
        self.sent.append((cmd, value, request_id))
        if cmd == "SET_REF":
            self.lines.append((json.dumps(status_dict(request_id)) + "\n").encode())
        elif cmd == "VERIFY_CONFIG":
            self.lines.append((json.dumps(status_dict(request_id, config=True)) + "\n").encode())
            self.pending_after_config = True
        return request_id

    def read_available(self):
        lines, self.lines = self.lines, []
        if not lines and self.pending_after_config:
            self.pending_after_config = False
            lines = [(json.dumps(sample_dict()) + "\n").encode()]
        return lines

    def set_streaming(self, value, timeout_s=1.0):
        pass

    def close(self):
        self.closed = True


def identity_from_hello(include_channel_config=True):
    hello = parse_hello(hello_dict(include_channel_config))
    return DeviceIdentity(
        device_id=hello.device_id, boot_id=hello.boot_id, firmware_version=hello.firmware_version,
        channel_count=hello.channel_count, reference_mode=hello.reference_mode, streaming=True,
        adc_status=[], port="/dev/fake", port_info={}, hello_seen=True, hello=hello.raw,
        channel_config=hello.channel_config,
    )


class VerifyEndToEndTests(unittest.TestCase):
    def test_hello_through_config_report_to_scan_pass(self):
        identity = identity_from_hello()
        fake = FakeSession(identity, [(json.dumps(sample_dict()) + "\n").encode()])
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "verify.json"
            with mock.patch.object(verifier, "SerialSession", lambda *a, **k: fake):
                with contextlib.redirect_stdout(io.StringIO()) as stdout, \
                        contextlib.redirect_stderr(io.StringIO()) as stderr:
                    rc = verifier.main(["--port", "/dev/fake", "--out", str(out)])
            self.assertEqual(rc, 0, stderr.getvalue())
            self.assertIn("SCAN_MODE_PASS", stdout.getvalue())
            saved = json.loads(out.read_text())
            self.assertTrue(saved["validation"]["passed"])
            self.assertEqual(saved["channel_config"]["channels"][0]["mux_channel"], 8)
            self.assertEqual(saved["frame_evidence"]["valid0"], True)
            self.assertEqual(saved["config_report"]["devices"][0]["registers"],
                             [0xB1, 0x80, 0xC0, 0x00])
            self.assertTrue(fake.closed)

    def test_missing_sample_is_clear_failure_not_crash(self):
        fake = FakeSession(identity_from_hello(), [])
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(verifier, "SerialSession", lambda *a, **k: fake):
                with contextlib.redirect_stdout(io.StringIO()), \
                        contextlib.redirect_stderr(io.StringIO()) as stderr:
                    rc = verifier.main(["--port", "/dev/fake", "--out", str(Path(tmp) / "x.json")])
        self.assertEqual(rc, 2)
        self.assertIn("NO SAMPLE FRAME", stderr.getvalue())

    def test_missing_hello_channel_config_falls_back_to_ch0_only(self):
        identity = identity_from_hello(include_channel_config=False)
        fake = FakeSession(identity, [(json.dumps(sample_dict()) + "\n").encode()])
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "x.json"
            with mock.patch.object(verifier, "SerialSession", lambda *a, **k: fake):
                with contextlib.redirect_stdout(io.StringIO()) as stdout, \
                        contextlib.redirect_stderr(io.StringIO()) as stderr:
                    rc = verifier.main(["--port", "/dev/fake", "--out", str(out)])
                    self.assertEqual(rc, 0, stderr.getvalue())
                    self.assertIn("SINGLE_POINT_CH0_PASS", stdout.getvalue())
                    saved = json.loads(out.read_text())
                    self.assertEqual(saved["validation"]["channel_map_status"], "NOT_REPORTED")
                    self.assertFalse(saved["validation"]["channel_evidence"].get("passed") is False)

    def test_real_0_1_3_hello_fixture_has_full_channel_config(self):
        fixture = Path(__file__).resolve().parent / "fixtures/hello_0_1_3_real.json"
        raw = json.loads(fixture.read_text())
        self.assertEqual(raw["firmware_version"], "tactile-sense-0.1.3")
        hello = parse_hello(raw)
        self.assertEqual(len(hello.channel_config["channels"]), 12)
        self.assertEqual(hello.channel_config["channels"][0]["mux_channel"], 8)
        self.assertEqual(hello.channel_config["channels"][11]["mux_channel"], 11)


if __name__ == "__main__":
    unittest.main()
