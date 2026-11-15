import unittest

from tools.tactile_acq.protocol import StatusMessage, parse_hello
from tools.tactile_acq.transport import SerialSession


def hello(include_channel_config=True):
    value = {"protocol_version": 1, "type": "HELLO", "device_id": "tactile-esp32-01",
             "boot_id": "boot-1", "firmware_version": "tactile-sense-0.1.3",
             "channel_count": 12, "channel_ids": list(range(12)),
             "reference_mode": "AVDD_AVSS", "streaming": True}
    if include_channel_config:
        value["channel_config"] = {"status": "IMPLEMENTED", "channels": [
            {"channel_id": ch, "mux_channel": 8 + ch % 4, "adc_input": ch % 4,
             "ads1220_id": ch // 4 + 1} for ch in range(12)]}
    return value


class IdentitySession(SerialSession):
    def __init__(self, hello_dict):
        self.port = "/dev/fake"
        self.ser = object()
        self._buffer = bytearray()
        self._line_count = 0
        self.hello_message = parse_hello(hello_dict)
        self.request_id = None
        self.status_returned = False

    @property
    def is_open(self):
        return True

    def wait_hello(self, timeout_s=2.0):
        return self.hello_message

    def send_command(self, cmd, value=None, target_id=None, request_id=None):
        self.request_id = request_id
        return request_id

    def messages(self, timeout_s=0.0):
        if self.request_id is not None and not self.status_returned:
            self.status_returned = True
            return [StatusMessage(
                device_id="tactile-esp32-01", boot_id="boot-1",
                firmware_version="tactile-sense-0.1.3", streaming=True,
                sensor_state="STREAMING", reference_mode="AVDD_AVSS", adc_status=(),
                effective_frame_rate_hz=46.7, last_frame_seq=7, uptime_ms=1000,
                request_id=self.request_id, raw={"channel_count": 12},
            )]
        return []


class DeviceIdentityTests(unittest.TestCase):
    def test_identify_preserves_hello_channel_config(self):
        identity = IdentitySession(hello()).identify(timeout_s=0.2)
        self.assertTrue(identity.hello_seen)
        self.assertIsNotNone(identity.channel_config)
        self.assertEqual(identity.channel_config["channels"][0]["mux_channel"], 8)
        self.assertEqual(identity.channel_config["channels"][11]["mux_channel"], 11)

    def test_identify_without_channel_config_is_none_not_crash(self):
        identity = IdentitySession(hello(include_channel_config=False)).identify(timeout_s=0.2)
        self.assertIsNone(identity.channel_config)


if __name__ == "__main__":
    unittest.main()
