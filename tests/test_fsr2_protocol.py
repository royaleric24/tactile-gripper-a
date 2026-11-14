"""Strict-parser tests for the V2 FSR_ONLY / HYBRID_6X6_FSR2 JSONL protocol.

The fixtures under tests/fixtures/fsr2 are emitted by the firmware frame
builders through the host simulation, not hand-written, so these tests also
guard the wire format the software side is expected to parse.
"""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from tools.fsr2 import protocol_v2 as protocol

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "fsr2"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def line(payload: dict) -> str:
    return json.dumps(payload, separators=(",", ":"))


class FixtureParseTests(unittest.TestCase):
    def test_hello_fsr_only(self) -> None:
        hello = protocol.parse_message(line(load("hello_fsr_only.json")))
        self.assertEqual(hello["type"], "HELLO")
        self.assertEqual(hello["sensor_profile"], "FSR_ONLY")
        self.assertEqual(hello["channel_count"], 2)
        self.assertEqual(hello["pins"]["miso"], [34, 35, 26, 33])
        self.assertEqual(hello["pins"]["cs"], [21, 22, 5, 32])
        self.assertEqual(hello["fsr_layout"]["adc_id"], 4)
        self.assertEqual(hello["fsr_layout"]["divider_resistor_ohm"], 10000)
        self.assertFalse(hello["fsr_layout"]["validated"])
        self.assertIsNone(hello["channel_config"]["matrix_rows"])

    def test_sample_fsr_only_valid(self) -> None:
        sample = protocol.parse_message(line(load("sample_fsr_only_valid.json")))
        self.assertEqual(sample.channel_count, 2)
        self.assertTrue(all(sample.valid))
        self.assertEqual(sorted(sample.fsr_values), ["FSR_A", "FSR_B"])
        self.assertNotEqual(sample.fsr_values["FSR_A"], sample.fsr_values["FSR_B"])
        self.assertEqual(sample.reference_mode, "AVDD_AVSS")
        self.assertEqual(len(sample.adc_status), 4)
        self.assertTrue(all(status["state"] == "OK" for status in sample.adc_status))

    def test_sample_fsr_only_missing_adc4(self) -> None:
        sample = protocol.parse_message(line(load("sample_fsr_only_no_adc4.json")))
        self.assertEqual(sample.valid, [False, False])
        self.assertIsNone(sample.raw_adc[0])
        self.assertIsNone(sample.channels[1])
        self.assertEqual(sample.channel_flags, [protocol.FLAG_NO_DATA] * 2)
        self.assertEqual(sample.adc_status[3]["state"], "NO_RESPONSE")

    def test_hello_hybrid(self) -> None:
        hello = protocol.parse_message(line(load("hello_hybrid.json")))
        self.assertEqual(hello["sensor_profile"], "HYBRID_6X6_FSR2")
        self.assertEqual(hello["channel_count"], 38)
        self.assertEqual(hello["channel_config"]["matrix_rows"], 6)
        self.assertEqual(hello["channel_config"]["matrix_cols"], 6)
        self.assertEqual(hello["pins"]["matrix_columns"], [4, 13, 14, 25, 27, 19])
        kinds = [entry["sensor_kind"] for entry in hello["channel_config"]["channels"]]
        self.assertEqual(kinds.count("MATRIX_CELL"), 36)
        self.assertEqual(kinds.count("FSR"), 2)

    def test_sample_hybrid_valid(self) -> None:
        sample = protocol.parse_message(line(load("sample_hybrid_valid.json")))
        self.assertEqual(len(sample.raw_adc), 38)
        self.assertTrue(all(sample.valid))
        self.assertEqual(sorted(sample.fsr_values), ["FSR_A", "FSR_B"])

    def test_sample_hybrid_missing_adc4(self) -> None:
        sample = protocol.parse_message(line(load("sample_hybrid_no_adc4.json")))
        self.assertTrue(all(sample.valid[:36]))
        self.assertEqual(sample.valid[36:], [False, False])

    def test_fixture_lines_fit_the_declared_buffer(self) -> None:
        for path in sorted(FIXTURES.glob("*.json")):
            text = path.read_text().rstrip("\n")
            self.assertLessEqual(len(text), protocol.MAX_LINE_BYTES, path.name)
            protocol.parse_message(text)


class RejectionTests(unittest.TestCase):
    def reject(self, payload: dict, code: str | None = None) -> None:
        with self.assertRaises(protocol.ProtocolError) as raised:
            protocol.parse_message(line(payload))
        if code is not None:
            self.assertEqual(getattr(raised.exception, "code", None), code)

    def test_invalid_channel_zero_is_rejected(self) -> None:
        sample = copy.deepcopy(load("sample_fsr_only_no_adc4.json"))
        sample["raw_adc"][0] = 0
        sample["channels"][0] = 0
        self.reject(sample, "ZERO_FOR_INVALID")

    def test_invalid_without_no_data_flag_is_rejected(self) -> None:
        # valid=false must carry NO_DATA; silently dropping the flag would let a
        # dead channel look like a healthy zero.
        sample = copy.deepcopy(load("sample_fsr_only_no_adc4.json"))
        sample["channel_flags"][0] = 0
        self.reject(sample, "VALID_FLAG_CONTRADICTION")

    def test_legacy_twelve_channel_count_is_rejected(self) -> None:
        sample = copy.deepcopy(load("sample_fsr_only_valid.json"))
        sample["channel_count"] = 12
        self.reject(sample)

    def test_internal_reference_is_rejected(self) -> None:
        sample = copy.deepcopy(load("sample_fsr_only_valid.json"))
        sample["reference_mode"] = "INTERNAL_2V048"
        self.reject(sample, "REFERENCE_MODE")

    def test_missing_profile_is_rejected(self) -> None:
        sample = copy.deepcopy(load("sample_fsr_only_valid.json"))
        del sample["sensor_profile"]
        self.reject(sample, "MISSING_PROFILE")

    def test_channel_id_order_is_rejected(self) -> None:
        sample = copy.deepcopy(load("sample_fsr_only_valid.json"))
        sample["channel_ids"] = [1, 0]
        self.reject(sample, "CHANNEL_IDS")

    def test_adc_status_must_cover_four_devices(self) -> None:
        sample = copy.deepcopy(load("sample_fsr_only_valid.json"))
        sample["adc_status"] = sample["adc_status"][:3]
        self.reject(sample, "CHANNEL_COUNT_MISMATCH")

    def test_duplicate_json_keys_are_rejected(self) -> None:
        text = '{"protocol_version":1,"type":"PONG","type":"PONG"}'
        with self.assertRaises(protocol.ProtocolError):
            protocol.parse_message(text)

    def test_hybrid_matrix_geometry_mismatch_is_rejected(self) -> None:
        sample = copy.deepcopy(load("sample_hybrid_valid.json"))
        sample["channel_count"] = 36
        self.reject(sample, "OUT_OF_RANGE")


class CommandEncodingTests(unittest.TestCase):
    def test_encode_status_query(self) -> None:
        text = protocol.encode_command("STATUS", request_id="reconnect-1")
        self.assertTrue(text.endswith(b"\n"))
        payload = json.loads(text.decode("utf-8"))
        self.assertEqual(payload["cmd"], "STATUS")
        self.assertEqual(payload["request_id"], "reconnect-1")

    def test_encode_stream_start(self) -> None:
        payload = json.loads(protocol.encode_command("STREAM", value="start").decode("utf-8"))
        self.assertEqual(payload["cmd"], "STREAM")
        self.assertEqual(payload["value"], "start")


if __name__ == "__main__":
    unittest.main()
