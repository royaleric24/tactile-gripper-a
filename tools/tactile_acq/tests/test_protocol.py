import json
import unittest

from tools.tactile_acq.protocol import (
    CHANNEL_FLAGS,
    FrameValidationError,
    SampleFrame,
    channel_id,
    channel_label,
    encode_command,
    flag_names,
    parse_message,
)
from tools.tactile_acq.tests.fixtures import make_sample


def encode(message):
    return (json.dumps(message, separators=(",", ":")) + "\n").encode()


class ProtocolTests(unittest.TestCase):
    def test_valid_sample(self):
        frame = parse_message(encode(make_sample()))
        self.assertIsInstance(frame, SampleFrame)
        self.assertEqual(frame.channel_count, 12)
        self.assertEqual(frame.valid_count, 12)
        self.assertEqual(frame.reference_mode, "INTERNAL_2V048")
        self.assertEqual(frame.raw_adc[0], -5000)
        self.assertEqual(frame.raw_adc[11], 6000)

    def test_signed_24_bit_extremes(self):
        values = [-8388608, 8388607] + [0] * 10
        frame = parse_message(encode(make_sample(values=values)))
        self.assertEqual(frame.raw_adc[0], -8388608)
        self.assertEqual(frame.raw_adc[1], 8388607)

    def test_out_of_range_rejected(self):
        values = [8388608] + [0] * 11
        with self.assertRaises(FrameValidationError):
            parse_message(encode(make_sample(values=values)))

    def test_invalid_channel_null(self):
        values = [None] + [0] * 11
        valid = [False] + [True] * 11
        flags = [0x20] + [0] * 11
        frame = parse_message(encode(make_sample(values=values, valid=valid, flags=flags)))
        self.assertFalse(frame.valid[0])
        self.assertIsNone(frame.raw_adc[0])
        self.assertEqual(frame.invalid_channels, (0,))

    def test_invalid_channel_with_value_rejected(self):
        values = [123] + [0] * 11
        valid = [False] + [True] * 11
        flags = [0x20] + [0] * 11
        with self.assertRaises(FrameValidationError):
            parse_message(encode(make_sample(values=values, valid=valid, flags=flags)))

    def test_valid_channel_null_rejected(self):
        values = [None] + [0] * 11
        with self.assertRaises(FrameValidationError):
            parse_message(encode(make_sample(values=values)))

    def test_valid_flag_and_no_data_disagree(self):
        flags = [0x20] + [0] * 11
        with self.assertRaises(FrameValidationError):
            parse_message(encode(make_sample(flags=flags)))

    def test_wrong_channel_count_rejected(self):
        message = make_sample()
        message["raw_adc"] = message["raw_adc"][:11]
        message["channels"] = message["raw_adc"]
        with self.assertRaises(FrameValidationError):
            parse_message(encode(message))

    def test_compat_channels_mismatch_rejected(self):
        message = make_sample()
        message["channels"] = [0] * 12
        with self.assertRaises(FrameValidationError):
            parse_message(encode(message))

    def test_duplicate_json_key_rejected(self):
        raw = b'{"protocol_version":1,"type":"SAMPLE","type":"SAMPLE"}\n'
        with self.assertRaises(FrameValidationError):
            parse_message(raw)

    def test_unknown_reference_mode_rejected(self):
        with self.assertRaises(FrameValidationError):
            parse_message(encode(make_sample(reference_mode="VCC")))

    def test_adc_status_order_rejected(self):
        message = make_sample()
        message["adc_status"][0]["id"] = 2
        with self.assertRaises(FrameValidationError):
            parse_message(encode(message))

    def test_unknown_adc_state_rejected(self):
        with self.assertRaises(FrameValidationError):
            parse_message(encode(make_sample(adc_states=["OK", "BROKEN", "OK"])))

    def test_hello_and_status(self):
        hello = {
            "protocol_version": 1,
            "type": "HELLO",
            "device_id": "tactile-esp32-01",
            "boot_id": "b1",
            "firmware_version": "tactile-sense-0.1.0",
            "channel_count": 12,
            "channel_ids": list(range(12)),
            "reference_mode": "INTERNAL_2V048",
        }
        parsed = parse_message(encode(hello))
        self.assertEqual(parsed.channel_count, 12)
        status = {
            "protocol_version": 1,
            "type": "STATUS",
            "device_id": "tactile-esp32-01",
            "boot_id": "b1",
            "firmware_version": "tactile-sense-0.1.0",
            "streaming": True,
            "sensor_state": "STREAMING",
            "reference_mode": "INTERNAL_2V048",
            "effective_frame_rate_hz": 47.5,
            "last_frame_seq": 3,
            "uptime_ms": 1000,
            "adc_status": [
                {"id": 1, "state": "OK"},
                {"id": 2, "state": "OK"},
                {"id": 3, "state": "NO_RESPONSE"},
            ],
            "request_id": "abc",
        }
        parsed_status = parse_message(encode(status))
        self.assertTrue(parsed_status.streaming)
        self.assertEqual(parsed_status.adc_status[2].state, "NO_RESPONSE")

    def test_channel_mapping(self):
        self.assertEqual(channel_id(1, 0), 0)
        self.assertEqual(channel_id(3, 3), 11)
        self.assertEqual(channel_label(4), "ADC2_AIN0")
        self.assertEqual(channel_label(11), "ADC3_AIN3")

    def test_flags(self):
        self.assertEqual(flag_names(0x01 | 0x08), ["SAT_HIGH", "NEAR_RAIL"])
        self.assertIn(0x20, CHANNEL_FLAGS)

    def test_encode_command(self):
        raw = encode_command("STATUS", request_id="r1")
        self.assertEqual(json.loads(raw), {"cmd": "STATUS", "request_id": "r1"})


if __name__ == "__main__":
    unittest.main()
