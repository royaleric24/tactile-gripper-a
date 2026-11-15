"""SIMULATED end-to-end CLI run over an in-memory serial object."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.tactile_acq.cli import main
from tools.tactile_acq.tests.fixtures import make_adc_status, make_sample


class FakeSerial:
    def __init__(self, **kwargs):
        self.rx = bytearray()
        self.tx = bytearray()
        self.is_open = True
        self.streaming = False
        self.sample_index = 0
        self.pending_samples = 0

    @property
    def in_waiting(self):
        return len(self.rx) + (1 if self.pending_samples > 0 else 0)

    def read(self, size):
        if size <= 0:
            return b""
        if not self.rx and self.pending_samples > 0:
            message = make_sample(seq=self.sample_index, timestamp_us=1000000 + self.sample_index * 21000)
            self.sample_index += 1
            self.pending_samples -= 1
            return (json.dumps(message) + "\n").encode()
        if not self.rx:
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
                self.respond(json.loads(line))
        return len(payload)

    def flush(self):
        pass

    def reset_input_buffer(self):
        pass

    def close(self):
        self.is_open = False

    def _send(self, message):
        self.rx.extend((json.dumps(message) + "\n").encode())

    def respond(self, command):
        rid = command.get("request_id")
        if command.get("cmd") == "STATUS":
            self._send(
                {
                    "protocol_version": 1,
                    "type": "STATUS",
                    "device_id": "tactile-esp32-01",
                    "boot_id": "fake-boot",
                    "firmware_version": "tactile-sense-0.1.0",
                    "streaming": self.streaming,
                    "sensor_state": "STREAMING" if self.streaming else "STOPPED",
                    "reference_mode": "INTERNAL_2V048",
                    "effective_frame_rate_hz": 0.0,
                    "last_frame_seq": 0,
                    "uptime_ms": 100,
                    "channel_count": 12,
                    "adc_status": make_adc_status(),
                    "request_id": rid,
                }
            )
        elif command.get("cmd") == "STREAM":
            self.streaming = bool(command.get("value"))
            if self.streaming:
                self.pending_samples = 25
            self._send(
                {
                    "protocol_version": 1,
                    "type": "STATUS",
                    "device_id": "tactile-esp32-01",
                    "boot_id": "fake-boot",
                    "firmware_version": "tactile-sense-0.1.0",
                    "streaming": self.streaming,
                    "sensor_state": "STREAMING" if self.streaming else "STOPPED",
                    "channel_count": 12,
                    "adc_status": make_adc_status(),
                    "request_id": rid,
                }
            )


class CliRunTests(unittest.TestCase):
    def test_run_records_frames(self):
        fake = FakeSerial()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            with mock.patch("tools.tactile_acq.transport.serial.Serial", return_value=fake), mock.patch(
                "tools.tactile_acq.cli.choose_port", return_value="/dev/fake"
            ):
                code = main(
                    [
                        "run",
                        "--port",
                        "/dev/fake",
                        "--duration",
                        "0.4",
                        "--monitor",
                        "none",
                        "--out",
                        str(output),
                    ]
                )
            self.assertEqual(code, 0)
            run = json.loads((output / "run.json").read_text())
            self.assertGreater(run["summary"]["samples"], 0)
            self.assertEqual(run["data_kind"], "REAL_HARDWARE_SERIAL")
            self.assertTrue((output / "raw_frames.jsonl").stat().st_size > 0)


if __name__ == "__main__":
    unittest.main()
