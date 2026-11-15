"""Strict-parser tests for the V2 JSONL protocol after the 12-electrode fix.

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

ELECTRODE_NAMES = ["R%d" % index for index in range(1, 7)] + [
    "C%d" % index for index in range(1, 7)
]


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
        self.assertNotIn("matrix_columns", hello["pins"])
        self.assertEqual(hello["fsr_layout"]["adc_id"], 4)
        self.assertEqual(hello["fsr_layout"]["divider_resistor_ohm"], 10000)
        self.assertFalse(hello["fsr_layout"]["validated"])
        self.assertIsNone(hello["channel_config"]["matrix_rows"])

    def test_sample_fsr_only_valid(self) -> None:
        sample = protocol.parse_message(line(load("sample_fsr_only_valid.json")))
        self.assertEqual(sample.channel_count, 2)
        self.assertTrue(all(sample.valid))
        self.assertEqual(sorted(sample.fsr_values), ["FSR_A", "FSR_B"])
        self.assertEqual(sample.reference_mode, "AVDD_AVSS")
        self.assertTrue(all(status["state"] == "OK" for status in sample.adc_status))

    def test_sample_fsr_only_missing_adc4(self) -> None:
        sample = protocol.parse_message(line(load("sample_fsr_only_no_adc4.json")))
        self.assertEqual(sample.valid, [False, False])
        self.assertEqual(sample.channel_flags, [protocol.FLAG_NO_DATA] * 2)
        self.assertIsNone(sample.channels[0])
        self.assertEqual(sample.adc_status[3]["state"], "NO_RESPONSE")

    def test_hello_electrodes_unmapped(self) -> None:
        hello = protocol.parse_message(line(load("hello_electrodes12_fsr2_unmapped.json")))
        self.assertEqual(hello["sensor_profile"], "MATRIX_ELECTRODES_12")
        self.assertEqual(hello["channel_count"], 14)
        self.assertIsNone(hello["channel_config"]["matrix_rows"])
        layout = hello["electrode_layout"]
        self.assertEqual(layout["count"], 12)
        self.assertEqual(layout["mapping_status"], "PENDING_REAL_WIRING")
        self.assertEqual(layout["row_bias"], "PULLDOWN_10K_TO_GND")
        self.assertEqual(layout["column_bias"], "PULLUP_1K_TO_3V3")
        self.assertFalse(layout["validated"])
        self.assertFalse(layout["gpio_excitation"])
        self.assertTrue(all(entry["adc_id"] is None for entry in layout["channels"]))
        self.assertEqual([entry["role"] for entry in layout["channels"]], ["ROW"] * 6 + ["COLUMN"] * 6)

    def test_sample_electrodes_unmapped(self) -> None:
        sample = protocol.parse_message(line(load("sample_electrodes12_fsr2_unmapped.json")))
        self.assertEqual(sample.channel_count, 14)
        for index in range(12):
            self.assertFalse(sample.valid[index])
            self.assertIsNone(sample.channels[index])
            self.assertEqual(sample.channel_flags[index], protocol.FLAG_NO_DATA)
        self.assertTrue(sample.valid[12] and sample.valid[13])
        self.assertEqual(sorted(sample.fsr_values), ["FSR_A", "FSR_B"])
        self.assertEqual(sample.electrode_values["R1"], None)

    def test_sample_electrodes_fsr_absent(self) -> None:
        sample = protocol.parse_message(line(load("sample_electrodes12_fsr2_fsr_absent.json")))
        self.assertEqual(sample.valid[12:], [False, False])
        self.assertIsNone(sample.channels[13])
        self.assertEqual(sample.adc_status[3]["state"], "NO_RESPONSE")

    def test_hello_electrodes_synthetic_mapping(self) -> None:
        hello = protocol.parse_message(line(load("hello_electrodes12_mapped_synthetic.json")))
        self.assertEqual(hello["channel_count"], 12)
        self.assertNotIn("fsr_layout", hello)
        layout = hello["electrode_layout"]
        self.assertEqual(layout["mapping_status"], "SIM_SYNTHETIC_MAPPING")
        self.assertTrue(all(entry["adc_id"] is not None for entry in layout["channels"]))

    def test_sample_electrodes_synthetic_mapping(self) -> None:
        sample = protocol.parse_message(line(load("sample_electrodes12_mapped_synthetic.json")))
        self.assertEqual(sample.channel_count, 12)
        self.assertTrue(all(sample.valid))
        values = sample.electrode_values
        self.assertEqual(sorted(values), sorted(ELECTRODE_NAMES))
        self.assertEqual(len(set(values.values())), 12)
        self.assertLess(values["R1"], values["C6"])

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

    def test_withdrawn_hybrid_profile_is_rejected(self) -> None:
        hello = copy.deepcopy(load("hello_fsr_only.json"))
        hello["sensor_profile"] = "HYBRID_6X6_FSR2"
        self.reject(hello, "PROFILE_HISTORICAL")

    def test_invalid_channel_zero_is_rejected(self) -> None:
        sample = copy.deepcopy(load("sample_fsr_only_no_adc4.json"))
        sample["raw_adc"][0] = 0
        sample["channels"][0] = 0
        self.reject(sample, "ZERO_FOR_INVALID")

    def test_invalid_without_no_data_flag_is_rejected(self) -> None:
        sample = copy.deepcopy(load("sample_fsr_only_no_adc4.json"))
        sample["channel_flags"][0] = 0
        self.reject(sample, "VALID_FLAG_CONTRADICTION")

    def test_wrong_channel_count_is_rejected(self) -> None:
        # 12 and 14 are both legal for MATRIX_ELECTRODES_12 (with/without FSR);
        # anything else must be rejected instead of silently re-interpreted.
        sample = copy.deepcopy(load("sample_electrodes12_fsr2_unmapped.json"))
        sample["channel_count"] = 13
        self.reject(sample, "CHANNEL_COUNT_MISMATCH")

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

    def test_invented_electrode_map_while_missing_is_rejected(self) -> None:
        hello = copy.deepcopy(load("hello_electrodes12_fsr2_unmapped.json"))
        hello["electrode_layout"]["channels"][0]["adc_id"] = 1
        hello["electrode_layout"]["channels"][0]["adc_input"] = 0
        hello["electrode_layout"]["channels"][0]["mux_channel"] = 8
        self.reject(hello, "MAPPING_STATUS")

    def test_gpio_excitation_claim_is_ignored_but_bias_is_checked(self) -> None:
        hello = copy.deepcopy(load("hello_electrodes12_fsr2_unmapped.json"))
        hello["electrode_layout"]["row_bias"] = "PULLUP_1K_TO_3V3"
        self.reject(hello, "ELECTRODE_BIAS")


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
