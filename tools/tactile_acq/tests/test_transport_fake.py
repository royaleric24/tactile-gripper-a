"""SIMULATED serial transport tests using an in-memory fake Serial object."""
import json
import unittest
from unittest import mock

from tools.tactile_acq.protocol import SampleFrame, parse_message
from tools.tactile_acq.tests.fixtures import make_adc_status, make_sample
from tools.tactile_acq.transport import SerialSession


class FakeSerial:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.rx = bytearray()
        self.tx = bytearray()
        self.is_open = True
        self.closed = False

    @property
    def in_waiting(self):
        return len(self.rx)

    def read(self, size):
        if size <= 0 or not self.rx:
            return b""
        data = bytes(self.rx[:size])
        del self.rx[:size]
        return data

    def write(self, payload):
        self.tx.extend(payload)
        while b"\n" in self.tx:
            line, _, rest = self.tx.partition(b"\n")
            self.tx = bytearray(rest)
            if line.strip():
                self._respond(json.loads(line))
        return len(payload)

    def flush(self):
        pass

    def reset_input_buffer(self):
        self.rx.clear()

    def close(self):
        self.is_open = False
        self.closed = True

    def _write_response(self, message):
        self.rx.extend((json.dumps(message) + "\n").encode())

    def _respond(self, command):
        request_id = command.get("request_id")
        if command.get("cmd") == "STATUS":
            self._write_response(
                {
                    "protocol_version": 1,
                    "type": "STATUS",
                    "device_id": "tactile-esp32-01",
                    "boot_id": "fake-boot",
                    "firmware_version": "tactile-sense-0.1.0",
                    "streaming": True,
                    "sensor_state": "STREAMING",
                    "reference_mode": "INTERNAL_2V048",
                    "effective_frame_rate_hz": 0.0,
                    "last_frame_seq": 0,
                    "uptime_ms": 100,
                    "channel_count": 12,
                    "adc_status": make_adc_status(),
                    "request_id": request_id,
                }
            )
        elif command.get("cmd") == "STREAM":
            self._write_response(
                {
                    "protocol_version": 1,
                    "type": "STATUS",
                    "device_id": "tactile-esp32-01",
                    "boot_id": "fake-boot",
                    "firmware_version": "tactile-sense-0.1.0",
                    "streaming": bool(command.get("value")),
                    "sensor_state": "STREAMING" if command.get("value") else "STOPPED",
                    "channel_count": 12,
                    "adc_status": make_adc_status(),
                    "request_id": request_id,
                }
            )


class FakeTransportTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeSerial()
        self.patch = mock.patch("tools.tactile_acq.transport.serial.Serial", return_value=self.fake)
        self.patch.start()
        self.session = SerialSession("/dev/fake", baud=921600)
        self.session.open()

    def tearDown(self):
        self.session.close()
        self.patch.stop()

    def test_identify(self):
        identity = self.session.identify(timeout_s=2.0)
        self.assertEqual(identity.device_id, "tactile-esp32-01")
        self.assertTrue(identity.firmware_version.startswith("tactile-sense-"))
        self.assertEqual(identity.channel_count, 12)

    def test_set_streaming(self):
        status = self.session.set_streaming(False, timeout_s=2.0)
        self.assertIsNotNone(status)
        self.assertFalse(status.streaming)

    def test_sample_reception(self):
        self.fake._write_response(make_sample(seq=9))
        lines = []
        for _ in range(100):
            lines = self.session.read_available()
            if lines:
                break
        self.assertEqual(len(lines), 1)
        frame = parse_message(lines[0])
        self.assertIsInstance(frame, SampleFrame)
        self.assertEqual(frame.frame_seq, 9)


if __name__ == "__main__":
    unittest.main()
