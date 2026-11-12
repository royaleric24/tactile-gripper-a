"""Shared offline fixtures.  Everything here is TEST/SIMULATION, never hardware."""

from __future__ import annotations

import json
from pathlib import Path

from tactile_gripper.models import ChannelConfig, ChannelConfiguration, TactileFrame
from tactile_gripper.protocol import encode_hello, encode_sample

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def channel_config(count: int = 4, *, rows: int | None = 2, cols: int | None = 2) -> ChannelConfiguration:
    channels = []
    for index in range(count):
        mapped = bool(rows and cols and index < rows * cols)
        row = index // cols if mapped else None
        col = index % cols if mapped else None
        channels.append(
            ChannelConfig(
                channel_id=index,
                adc_input=index,
                ads1220_id=index // 4,
                mux_channel=index % 4,
                matrix_row=row,
                matrix_col=col,
            )
        )
    return ChannelConfiguration(
        channels=tuple(channels),
        matrix_rows=rows,
        matrix_cols=cols,
        adc_count=3,
        scan_mode="TEST_FIXTURE",
        status="TEST",
    )


def demo_config() -> ChannelConfiguration:
    value = json.loads((PROJECT_ROOT / "config/sensor_channels.demo.json").read_text())
    return ChannelConfiguration.from_dict(value)


def frame(
    *,
    seq: int = 1,
    boot_id: str = "boot-1",
    mcu_time_us: int | None = None,
    host_received_ns: int = 1_000_000_000,
    count: int = 4,
    values: list | None = None,
    mask: list | None = None,
    source=None,
    device_id: str = "sensor-test",
) -> TactileFrame:
    from tactile_gripper.sources import DataSource

    config = channel_config(count)
    if values is None:
        values = [100 + index for index in range(count)]
    if mask is None:
        mask = [True] * count
    if mcu_time_us is None:
        mcu_time_us = seq * 1000
    return TactileFrame(
        protocol_version=1,
        device_id=device_id,
        boot_id=boot_id,
        frame_seq=seq,
        mcu_time_us=mcu_time_us,
        host_received_ns=host_received_ns,
        channels=tuple(values),
        valid_mask=tuple(mask),
        source=source or DataSource.LIVE,
        channel_ids=tuple(range(count)),
        matrix_rows=config.matrix_rows,
        matrix_cols=config.matrix_cols,
        contact_score=None,
    ).validate(config)


def sample_message(
    *,
    seq: int = 1,
    boot_id: str = "boot-1",
    mcu_time_us: int | None = None,
    count: int = 4,
    values: list | None = None,
    mask: list | None = None,
    device_id: str = "sensor-test",
) -> dict:
    if values is None:
        values = [100 + index for index in range(count)]
    if mask is None:
        mask = [True] * count
    if mcu_time_us is None:
        mcu_time_us = seq * 1000
    return {
        "protocol_version": 1,
        "type": "SAMPLE",
        "device_id": device_id,
        "boot_id": boot_id,
        "frame_seq": seq,
        "mcu_time_us": mcu_time_us,
        "channels": values,
        "valid_mask": mask,
        "channel_ids": list(range(count)),
    }


def hello_line(config: ChannelConfiguration | None = None, *, boot_id: str = "boot-1") -> bytes:
    return encode_hello("sensor-test", boot_id, config or channel_config())


def sample_line(**kwargs) -> bytes:
    return encode_sample(frame(**kwargs))


class FakeLineTransport:
    """In-memory read-only line transport with an optional trap write method."""

    def __init__(self, lines: list[bytes] | None = None):
        self.lines = list(lines or [])
        self.offset = 0
        self.connected = False
        self.writes: list[bytes] = []
        self.closed = False

    def connect(self) -> None:
        self.connected = True

    def close(self) -> None:
        self.closed = True
        self.connected = False

    def readline(self, timeout_s: float) -> bytes | None:
        if self.offset >= len(self.lines):
            return None
        line = self.lines[self.offset]
        self.offset += 1
        return line

    def write(self, data: bytes) -> int:  # pragma: no cover - should never be called
        self.writes.append(data)
        raise AssertionError("sensor transport must never write")


class FakeBenchTransport:
    """Offline stand-in for the S3 serial transport (no device, no pyserial)."""

    def __init__(self, *, firmware_version: str = "gripper-control-s3-0.9b26.0"):
        self.firmware_version = firmware_version
        self.boot_id = "FAKE-BOOT-001"
        self.state = "DISARMED"
        self.output_state = "DISABLED_UNMEASURED"
        self.bench_active = False
        self.commands: list[dict] = []
        self.raw_writes: list[bytes] = []
        self.connected = False
        self.closed = False
        self.timeout_on: str | None = None
        self.reject_on: str | None = None
        self.hold_mode = False

    def connect(self, port=None) -> None:
        self.connected = True

    def close(self) -> None:
        self.closed = True
        self.connected = False

    def exchange(self, raw: bytes, request_id: str) -> dict:
        self.raw_writes.append(raw)
        request = json.loads(raw.decode("utf-8"))
        self.commands.append(request)
        command = request["command"]
        if self.timeout_on == command:
            raise TimeoutError("fake response timeout")
        if self.reject_on == command:
            return self._response(request, "ERROR", error="LOCAL_TEST_REJECTION")
        if command == "GET_STATUS":
            return self._response(request, "STATUS")
        if command == "PING":
            return self._response(request, "PONG")
        if command == "BEGIN_BENCH":
            if self.state != "DISARMED":
                return self._response(request, "ERROR", error="ALREADY_ARMED")
            self.state = "ARMED"
            self.bench_active = True
            return self._response(request, "ACK")
        if command == "BENCH_HOLD_MODE":
            self.hold_mode = True
            return self._response(request, "ACK")
        if command == "BENCH_PULSE_MODE":
            self.hold_mode = False
            return self._response(request, "ACK")
        if command in ("BENCH_HOLD", "BENCH_PULSE"):
            if self.state not in ("ARMED", "ACTIVE"):
                return self._response(request, "ERROR", error="NOT_ARMED")
            self.state = "ACTIVE"
            self.output_state = "PWM_ACTIVE_UNMEASURED"
            return self._response(request, "ACK")
        if command == "STOP":
            self.state = "DISARMED"
            self.bench_active = False
            self.output_state = "DISABLED_UNMEASURED"
            return self._response(request, "ACK")
        if command == "DISARM":
            self.state = "DISARMED"
            self.bench_active = False
            self.output_state = "DISABLED_UNMEASURED"
            return self._response(request, "ACK")
        if command == "HEARTBEAT":
            return self._response(request, "PONG")
        return self._response(request, "ERROR", error="UNKNOWN_COMMAND")

    def _response(self, request: dict, response_type: str, *, error: str | None = None) -> dict:
        response = {
            "protocol_version": 1,
            "request_id": request.get("request_id"),
            "firmware_version": self.firmware_version,
            "type": response_type,
            "state": self.state,
            "output_state": self.output_state,
            "boot_id": self.boot_id,
            "uptime_ms": 1234,
            "last_sequence": request.get("sequence", 0),
            "calibration_state": "UNCALIBRATED",
            "hardware_enabled": False,
            "motion_enabled": False,
            "bench_capable": True,
            "bench_active": self.bench_active,
            "fault_reason": None,
            "commanded_pulse_us": request.get("pulse_us"),
            "actual_angle_deg": None,
            "actual_opening": None,
        }
        if error is not None:
            response["error"] = error
        return response

    def pwm_commands(self) -> list[dict]:
        return [item for item in self.commands if item["command"] in ("BENCH_HOLD", "BENCH_PULSE")]
