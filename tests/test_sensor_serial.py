"""Serial sensor transport tests use an in-memory fake pyserial object."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tactile_gripper.devices.sensor import SensorAdapter, config_from_json_file
from tactile_gripper.devices.sensor_serial import (
    SerialSensorConfig,
    SerialSensorTransport,
    serial_sensor_adapter,
)
from tactile_gripper.devices.firmware_fixture import FIXTURE_ROOT
from tactile_gripper.errors import FrameValidationError, SensorOffline
from tactile_gripper.sources import DataSource

from support import FakeLineTransport, channel_config, hello_line, sample_line


class FakeSerial:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.port = kwargs.get("port")
        self.dtr = True
        self.rts = True
        self.opened = False
        self.closed = False
        self.timeout = kwargs.get("timeout", 0.1)
        self.buffer = bytearray()
        self.in_waiting = 0
        self.writes = []
        FakeSerial.instances.append(self)

    def open(self):
        self.opened = True

    def close(self):
        self.closed = True

    def read(self, size=1):
        if not self.buffer:
            return b""
        chunk = bytes(self.buffer[:size])
        del self.buffer[:size]
        self.in_waiting = len(self.buffer)
        return chunk

    def write(self, payload):
        self.writes.append(json.loads(payload))
        return len(payload)

    def feed(self, chunk):
        self.buffer.extend(chunk)
        self.in_waiting = len(self.buffer)


class Clock:
    def __init__(self):
        self.now = 10_000_000_000

    def __call__(self):
        return self.now


class SerialTransportTests(unittest.TestCase):
    def setUp(self):
        FakeSerial.instances.clear()

    def config(self, **kwargs):
        return SerialSensorConfig(port="/dev/cu.fake-sensor", boot_wait_s=0, **kwargs)

    def test_connect_sets_dtr_rts_false_and_reads_bounded_lines(self):
        with patch("serial.Serial", FakeSerial):
            transport = SerialSensorTransport(self.config())
            self.assertIsNone(transport.port)
            transport.connect()
            fake = FakeSerial.instances[-1]
            self.assertTrue(fake.opened)
            self.assertFalse(fake.dtr)
            self.assertFalse(fake.rts)
            fake.buffer.extend(b'{"a":1}\n{"b":2}\n')
            fake.in_waiting = len(fake.buffer)
            self.assertEqual(transport.readline(0.5), b'{"a":1}\n')
            self.assertEqual(transport.readline(0.5), b'{"b":2}\n')
            transport.close()
            self.assertTrue(fake.closed)

    def test_no_port_is_refused_without_serial_import(self):
        with patch("serial.Serial", side_effect=AssertionError("must not open")):
            transport = SerialSensorTransport(SerialSensorConfig(port=None))
            with self.assertRaises(SensorOffline):
                transport.connect()

    def test_oversize_line_is_discarded_and_counted(self):
        with patch("serial.Serial", FakeSerial):
            transport = SerialSensorTransport(self.config(max_line_bytes=4))
            transport.connect()
            fake = FakeSerial.instances[-1]
            fake.buffer.extend(b"123456\nok\n")
            fake.in_waiting = len(fake.buffer)
            self.assertEqual(transport.readline(0.5), b"ok\n")
            self.assertEqual(transport.oversize_lines, 1)
            self.assertIsNone(transport.readline(0.5))

    def test_config_file_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sensor.json"
            path.write_text(json.dumps({"sensor_serial": {"port": None, "baudrate": 115200}}))
            config = SerialSensorConfig.from_file(path)
            self.assertEqual(config.baudrate, 115200)
            with self.assertRaises(ValueError):
                SerialSensorConfig(baudrate=-1)

    def test_adapter_reads_hello_and_sample(self):
        with patch("serial.Serial", FakeSerial):
            config = self.config()
            adapter = serial_sensor_adapter(config)
            adapter.connect()
            fake = FakeSerial.instances[-1]
            self.assertEqual(fake.kwargs["baudrate"], 921600)
            self.assertEqual((fake.kwargs["bytesize"], fake.kwargs["parity"], fake.kwargs["stopbits"]), (8, "N", 1))
            self.assertEqual(fake.writes, [{"cmd": "HELLO"}])
            historical = (FIXTURE_ROOT / "hello_fsr_only.json").read_bytes()
            fake.feed(historical)
            with self.assertRaisesRegex(FrameValidationError, "dual FSR"):
                adapter.read_frame(0)
            hello = (FIXTURE_ROOT / "hello_fsr1.json").read_bytes()
            sample = (FIXTURE_ROOT / "sample_fsr1_valid.json").read_bytes()
            fake.feed(hello[:100])
            self.assertIsNone(adapter.read_frame(0))
            fake.feed(hello[100:] + sample[:130])
            self.assertIsNone(adapter.read_frame(0))
            self.assertEqual(fake.writes[-1]["cmd"], "STATUS")
            fake.feed(sample[130:])
            parsed = adapter.read_frame(0)
            self.assertIsNotNone(parsed)
            self.assertEqual(parsed.channels, (762601,))
            self.assertEqual(parsed.source, DataSource.LIVE)
            self.assertEqual(adapter.status().state, "STREAMING")
            self.assertNotIn("STREAM", [item["cmd"] for item in fake.writes])
            adapter.close()


class SensorReconnectTests(unittest.TestCase):
    def test_reconnect_after_transport_failure(self):
        clock = Clock()

        class Flaky(FakeLineTransport):
            def readline(self, timeout_s):
                raise OSError("cable removed")

        good = FakeLineTransport([hello_line(), sample_line(seq=1)])
        adapter = SensorAdapter(
            Flaky([]),
            channel_config(),
            source=DataSource.LIVE,
            clock_ns=clock,
            transport_factory=lambda: good,
            reconnect_initial_s=1.0,
            reconnect_max_s=2.0,
        )
        adapter.connect()
        with self.assertRaises(SensorOffline):
            adapter.read_frame(0.1)
        self.assertFalse(adapter.connected)
        self.assertFalse(adapter.maybe_reconnect())  # backoff not elapsed
        clock.now += 2_000_000_000
        self.assertTrue(adapter.maybe_reconnect())
        self.assertEqual(adapter.reconnect_count, 1)
        parsed = adapter.read_frame(0.5)
        self.assertEqual(parsed.frame_seq, 1)
        adapter.close()


if __name__ == "__main__":
    unittest.main()
