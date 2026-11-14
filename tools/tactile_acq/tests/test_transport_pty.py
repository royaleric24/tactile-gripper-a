"""SIMULATED transport test over a local pseudo-terminal.  Not real hardware."""
import json
import os
import select
import sys
import threading
import time
import tty
import unittest
from unittest.mock import patch

from tools.tactile_acq.protocol import SampleFrame, parse_message
from tools.tactile_acq.tests.fixtures import make_adc_status, make_sample
from tools.tactile_acq.transport import SerialSession


class FakeTactileDevice(threading.Thread):
    def __init__(self, master_fd):
        super().__init__(daemon=True)
        self.master_fd = master_fd
        self.stop_event = threading.Event()
        self.buffer = b""
        self.commands = []

    def run(self):
        while not self.stop_event.is_set():
            ready, _, _ = select.select([self.master_fd], [], [], 0.01)
            if not ready:
                continue
            try:
                data = os.read(self.master_fd, 4096)
            except OSError:
                return
            self.buffer += data
            while b"\n" in self.buffer:
                line, self.buffer = self.buffer.split(b"\n", 1)
                if not line.strip():
                    continue
                command = json.loads(line)
                self.commands.append(command)
                self.respond(command)

    def write(self, message):
        os.write(self.master_fd, (json.dumps(message) + "\n").encode())

    def respond(self, command):
        cmd = command.get("cmd")
        request_id = command.get("request_id")
        if cmd == "STATUS":
            self.write(
                {
                    "protocol_version": 1,
                    "type": "STATUS",
                    "device_id": "tactile-esp32-01",
                    "boot_id": "sim-boot",
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
        elif cmd == "STREAM":
            self.write(
                {
                    "protocol_version": 1,
                    "type": "STATUS",
                    "device_id": "tactile-esp32-01",
                    "boot_id": "sim-boot",
                    "firmware_version": "tactile-sense-0.1.0",
                    "streaming": bool((command.get("value") or {}).get("x")) if isinstance(command.get("value"), dict) else bool(command.get("value")),
                    "sensor_state": "STREAMING",
                    "channel_count": 12,
                    "adc_status": make_adc_status(),
                    "request_id": request_id,
                }
            )


class PtyTransportTests(unittest.TestCase):
    def setUp(self):
        try:
            self.master, self.slave = os.openpty()
        except PermissionError as exc:
            self.skipTest("pseudo-terminal is not available in this sandbox: {}".format(exc))
        tty.setraw(self.slave)
        self.slave_name = os.ttyname(self.slave)
        self.device = FakeTactileDevice(self.master)
        self.device.start()
        # A PTY tests framing only. macOS rejects custom UART speeds on a PTY.
        self.session = SerialSession(self.slave_name, baud=9600)
        self.session.open()
        if sys.platform == "darwin":
            # tcdrain can block on macOS PTYs. The fake peer verifies delivery.
            drain = patch.object(self.session.ser, "flush")
            drain.start()
            self.addCleanup(drain.stop)

    def tearDown(self):
        self.session.close()
        self.device.stop_event.set()
        self.device.join(timeout=1)
        os.close(self.slave)
        os.close(self.master)

    def test_identify_and_sample(self):
        identity = self.session.identify(timeout_s=3.0)
        self.assertEqual(identity.device_id, "tactile-esp32-01")
        self.assertEqual(identity.firmware_version, "tactile-sense-0.1.0")
        self.assertTrue(any(command.get("cmd") == "STATUS" for command in self.device.commands))
        # Drain concurrently: some PTYs buffer less than a full SAMPLE line.
        with_sample = threading.Thread(
            target=self.device.write, args=(make_sample(seq=5),), daemon=True,
        )
        with_sample.start()
        lines = []
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and not lines:
            lines = self.session.read_available()
        with_sample.join(timeout=1.0)
        self.assertFalse(with_sample.is_alive())
        self.assertEqual(len(lines), 1)
        frame = parse_message(lines[0])
        self.assertIsInstance(frame, SampleFrame)
        self.assertEqual(frame.frame_seq, 5)


if __name__ == "__main__":
    unittest.main()
