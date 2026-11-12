"""S1 wire parser and stream-tracker tests.  No hardware is opened."""

import unittest

from tactile_gripper.errors import FrameValidationError, ProtocolError
from tactile_gripper.protocol import (
    FrameTracker,
    decode_line,
    encode_hello,
    encode_sample,
    parse_envelope,
    parse_hello,
    parse_sample,
)

from support import channel_config, demo_config, frame, sample_line, sample_message


class DecodeTests(unittest.TestCase):
    def test_valid_line(self):
        value = decode_line(sample_line())
        self.assertEqual(value["type"], "SAMPLE")

    def test_invalid_json_and_root(self):
        with self.assertRaises(FrameValidationError):
            decode_line(b"{not json}\n")
        with self.assertRaises(FrameValidationError):
            decode_line(b"[]\n")

    def test_duplicate_keys_rejected(self):
        with self.assertRaises(FrameValidationError) as ctx:
            decode_line(b'{"type":"SAMPLE","type":"SAMPLE"}\n')
        self.assertEqual(ctx.exception.code, "INVALID_JSON")

    def test_oversize_rejected(self):
        with self.assertRaises(FrameValidationError) as ctx:
            decode_line(b"{" + b"a" * 50 + b"}\n", max_bytes=10)
        self.assertEqual(ctx.exception.code, "FRAME_TOO_LARGE")

    def test_invalid_utf8_and_embedded_newline(self):
        with self.assertRaises(FrameValidationError):
            decode_line(b"\xff\n")
        with self.assertRaises(FrameValidationError):
            decode_line(b'{"a":1}\n{"b":2}\n')


class EnvelopeTests(unittest.TestCase):
    def test_wrong_version_and_unknown_type(self):
        with self.assertRaises(FrameValidationError) as ctx:
            parse_envelope(b'{"protocol_version":2,"type":"SAMPLE"}\n')
        self.assertEqual(ctx.exception.code, "PROTOCOL_VERSION")
        with self.assertRaises(FrameValidationError) as ctx:
            parse_envelope(b'{"protocol_version":1,"type":"MAGIC"}\n')
        self.assertEqual(ctx.exception.code, "UNKNOWN_MESSAGE")
        with self.assertRaises(FrameValidationError) as ctx:
            parse_envelope(b'{"protocol_version":1}\n')
        self.assertEqual(ctx.exception.code, "MISSING_FIELD")

    def test_hello_roundtrip_dynamic_36(self):
        config = demo_config()
        line = encode_hello("sensor-test", "boot-9", config)
        hello = parse_hello(parse_envelope(line))
        self.assertEqual(hello.device_id, "sensor-test")
        self.assertEqual(hello.channel_config.expected_channel_count, 36)
        self.assertEqual(hello.channel_config.matrix_rows, 6)

    def test_hello_rejects_bad_channel_config(self):
        line = encode_hello("sensor-test", "boot-9", channel_config()).replace(
            b'"channel_id":0', b'"channel_id":"zero"'
        )
        with self.assertRaises(FrameValidationError):
            parse_hello(parse_envelope(line))


class SampleParseTests(unittest.TestCase):
    def setUp(self):
        self.config = channel_config(4)

    def test_parse_valid_sample(self):
        message = parse_envelope(sample_line(seq=3))
        parsed = parse_sample(message, self.config, host_received_ns=123)
        self.assertEqual(parsed.frame_seq, 3)
        self.assertEqual(parsed.channel_count, 4)
        self.assertEqual(parsed.host_received_ns, 123)

    def test_length_mismatch(self):
        message = parse_envelope(sample_line(count=4))
        message["channels"] = message["channels"][:3]
        message["valid_mask"] = message["valid_mask"][:3]
        with self.assertRaises(FrameValidationError) as ctx:
            parse_sample(message, self.config, host_received_ns=1)
        self.assertEqual(ctx.exception.code, "LENGTH_MISMATCH")

    def test_missing_field(self):
        message = parse_envelope(sample_line())
        del message["mcu_time_us"]
        with self.assertRaises(FrameValidationError) as ctx:
            parse_sample(message, self.config, host_received_ns=1)
        self.assertEqual(ctx.exception.code, "MISSING_FIELD")

    def test_bad_channel_id(self):
        message = parse_envelope(sample_line())
        message["channel_ids"] = [0, 1, 2, 99]
        with self.assertRaises(FrameValidationError) as ctx:
            parse_sample(message, self.config, host_received_ns=1)
        self.assertEqual(ctx.exception.code, "INVALID_CHANNEL")

    def test_nan_rejected(self):
        message = parse_envelope(sample_line())
        message["channels"][1] = float("nan")
        with self.assertRaises(FrameValidationError) as ctx:
            parse_sample(message, self.config, host_received_ns=1)
        self.assertEqual(ctx.exception.code, "INVALID_VALUE")

    def test_not_a_sample(self):
        with self.assertRaises(ProtocolError):
            parse_sample({"type": "STATUS"}, self.config)


class FrameTrackerTests(unittest.TestCase):
    def setUp(self):
        self.tracker = FrameTracker()

    def test_duplicate_and_gap(self):
        self.tracker.accept(frame(seq=1))
        self.tracker.accept(frame(seq=2))
        anomalies = self.tracker.accept(frame(seq=4))
        self.assertEqual(anomalies[0].kind, "FRAME_GAP")
        self.assertEqual(anomalies[0].dropped, 1)
        self.assertEqual(self.tracker.dropped_frames, 1)
        with self.assertRaises(FrameValidationError) as ctx:
            self.tracker.accept(frame(seq=4))
        self.assertEqual(ctx.exception.code, "DUPLICATE_FRAME")
        with self.assertRaises(FrameValidationError) as ctx:
            self.tracker.accept(frame(seq=3))
        self.assertEqual(ctx.exception.code, "SEQUENCE_REGRESSION")

    def test_timestamp_anomaly(self):
        self.tracker.accept(frame(seq=1, mcu_time_us=1000))
        with self.assertRaises(FrameValidationError) as ctx:
            self.tracker.accept(frame(seq=2, mcu_time_us=1000))
        self.assertEqual(ctx.exception.code, "TIMESTAMP_ANOMALY")

    def test_host_clock_anomaly(self):
        self.tracker.accept(frame(seq=1, host_received_ns=200))
        with self.assertRaises(FrameValidationError) as ctx:
            self.tracker.accept(frame(seq=2, host_received_ns=100))
        self.assertEqual(ctx.exception.code, "HOST_CLOCK_ANOMALY")

    def test_device_restart_detected_and_baseline_reset(self):
        self.tracker.accept(frame(seq=100, boot_id="boot-1", mcu_time_us=9000))
        anomalies = self.tracker.accept(
            frame(seq=1, boot_id="boot-2", mcu_time_us=100, host_received_ns=2_000_000_000)
        )
        self.assertEqual(anomalies[0].kind, "DEVICE_RESTART")
        self.assertEqual(self.tracker.restart_count, 1)
        self.assertEqual(self.tracker.last_seq, 1)

    def test_stale_window(self):
        self.assertTrue(self.tracker.stale(1000))
        self.tracker.accept(frame(seq=1, host_received_ns=1_000_000_000))
        self.assertFalse(self.tracker.stale(1_500_000_000, timeout_s=1.0))
        self.assertTrue(self.tracker.stale(3_000_000_000, timeout_s=1.0))


if __name__ == "__main__":
    unittest.main()
