"""Sensor adapter tests using clearly marked offline data only."""

import tempfile
import unittest
from pathlib import Path

from tactile_gripper.devices.sensor import (
    JsonlReplayTransport,
    ReplaySensorAdapter,
    SensorAdapter,
    SimulatedSensorAdapter,
    default_demo_config,
)
from tactile_gripper.errors import FrameValidationError, SensorOffline
from tactile_gripper.protocol import encode_hello, encode_sample
from tactile_gripper.sources import DataSource

from support import FakeLineTransport, channel_config, frame, hello_line, sample_line


class Clock:
    def __init__(self, now=1_000_000_000):
        self.now = now

    def __call__(self):
        return self.now


class SensorAdapterTests(unittest.TestCase):
    def test_hello_then_sample(self):
        transport = FakeLineTransport([hello_line(), sample_line(seq=1), sample_line(seq=2)])
        clock = Clock()
        adapter = SensorAdapter(
            transport, channel_config(), source=DataSource.LIVE, clock_ns=clock
        )
        self.assertEqual(adapter.connect().state, "WAITING")
        first = adapter.read_frame(0.5)
        self.assertIsNotNone(first)
        self.assertEqual(first.frame_seq, 1)
        self.assertEqual(first.source, DataSource.LIVE)
        self.assertEqual(adapter.status().state, "STREAMING")
        self.assertEqual(transport.writes, [])

    def test_hello_can_replace_dynamic_config(self):
        demo = default_demo_config()
        transport = FakeLineTransport(
            [
                encode_hello("sensor-test", "boot-36", demo),
                encode_sample(frame(seq=1, count=36)),
            ]
        )
        adapter = SensorAdapter(transport, channel_config(4), source=DataSource.LIVE)
        adapter.connect()
        parsed = adapter.read_frame(0.5)
        self.assertEqual(parsed.channel_count, 36)
        self.assertEqual(adapter.channel_config.expected_channel_count, 36)

    def test_invalid_data_is_not_offline(self):
        transport = FakeLineTransport([hello_line(), b'{"protocol_version":1,"type":"SAMPLE"}\n'])
        adapter = SensorAdapter(transport, channel_config(), source=DataSource.LIVE)
        adapter.connect()
        with self.assertRaises(FrameValidationError):
            adapter.read_frame(0.5)
        self.assertTrue(adapter.connected)
        self.assertEqual(adapter.invalid_frames, 1)
        self.assertNotEqual(adapter.status().state, "OFFLINE")

    def test_close_is_offline_and_read_fails(self):
        adapter = SensorAdapter(
            FakeLineTransport([hello_line()]), channel_config(), source=DataSource.LIVE
        )
        adapter.connect()
        adapter.close()
        self.assertEqual(adapter.status().state, "OFFLINE")
        with self.assertRaises(SensorOffline):
            adapter.read_frame(0.1)

    def test_stale_after_no_frames(self):
        clock = Clock()
        transport = FakeLineTransport([hello_line(), sample_line(seq=1), sample_line(seq=2)])
        adapter = SensorAdapter(
            transport, channel_config(), source=DataSource.LIVE, clock_ns=clock, stale_after_s=1.0
        )
        adapter.connect()
        adapter.read_frame(0.5)
        self.assertEqual(adapter.status().state, "STREAMING")
        clock.now += 5_000_000_000
        self.assertEqual(adapter.status().state, "STALE")

    def test_device_error_surfaced(self):
        from tactile_gripper.protocol import encode_error

        transport = FakeLineTransport([hello_line(), encode_error("ADC_TIMEOUT")])
        adapter = SensorAdapter(transport, channel_config(), source=DataSource.LIVE)
        adapter.connect()
        with self.assertRaises(Exception) as ctx:
            adapter.read_frame(0.5)
        self.assertEqual(getattr(ctx.exception, "code", None), "DEVICE_ERROR")
        self.assertEqual(adapter.state, "DEVICE_ERROR")


class ReplayAndSimulationTests(unittest.TestCase):
    def _write_replay(self, folder: Path) -> Path:
        path = folder / "samples.jsonl"
        path.write_bytes(
            hello_line()
            + sample_line(seq=1)
            + sample_line(seq=2)
            + sample_line(seq=3)
        )
        return path

    def test_replay_is_read_only_and_tagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_replay(Path(tmp))
            adapter = ReplaySensorAdapter(path, channel_config())
            self.assertEqual(adapter.source, DataSource.REPLAY)
            self.assertFalse(hasattr(adapter.transport, "write"))
            adapter.connect()
            parsed = adapter.read_frame(0.5)
            self.assertEqual(parsed.source, DataSource.REPLAY)
            self.assertEqual(parsed.frame_seq, 1)
            adapter.close()

    def test_replay_rewind(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_replay(Path(tmp))
            adapter = ReplaySensorAdapter(path, channel_config())
            adapter.connect()
            adapter.read_frame(0.5)
            adapter.read_frame(0.5)
            adapter.rewind()
            first = adapter.read_frame(0.5)
            self.assertEqual(first.frame_seq, 1)

    def test_simulation_is_labeled_and_has_no_serial_transport(self):
        adapter = SimulatedSensorAdapter(default_demo_config(), period_s=0)
        self.assertEqual(adapter.source, DataSource.SIMULATION)
        self.assertFalse(hasattr(adapter.transport, "write"))
        adapter.connect()
        parsed = adapter.read_frame(0.5)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.source, DataSource.SIMULATION)
        self.assertEqual(parsed.channel_count, 36)
        self.assertEqual(adapter.status().state, "STREAMING")
        adapter.close()

    def test_jsonl_replay_transport_cannot_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_replay(Path(tmp))
            transport = JsonlReplayTransport(path)
            transport.connect()
            self.assertIsNotNone(transport.readline(0))
            self.assertFalse(hasattr(transport, "write"))


if __name__ == "__main__":
    unittest.main()
