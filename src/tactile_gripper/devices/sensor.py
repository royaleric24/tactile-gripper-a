"""Sensor adapters for LIVE/REPLAY/SIMULATION sources.

No real sensor transport is implemented because the hardware-side transport,
scanning and channel map are still PENDING-HW.  The adapter itself is fully
testable with an injected line transport, a JSONL replay file, or the clearly
labelled synthetic demo source.
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Protocol

from ..constants import DEFAULT_SENSOR_STALE_S, MAX_SENSOR_LINE_BYTES, PROTOCOL_VERSION
from ..errors import FrameValidationError, ProtocolError, SensorOffline, SensorStale
from ..models import ChannelConfiguration, DeviceStatus, TactileFrame
from ..protocol import (
    ErrorMessage,
    FrameTracker,
    HelloMessage,
    encode_hello,
    encode_sample,
    parse_envelope,
    parse_error,
    parse_hello,
    parse_sample,
    parse_status,
)
from ..sources import DataSource

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class LineTransport(Protocol):
    """Minimal read-only line transport.  It has no write method by design."""

    def connect(self) -> None: ...
    def close(self) -> None: ...
    def readline(self, timeout_s: float) -> bytes | None: ...


class SensorAdapter:
    def __init__(
        self,
        transport: LineTransport,
        channel_config: ChannelConfiguration | None,
        *,
        source: DataSource,
        device_id: str = "sensor-unknown",
        clock_ns=time.monotonic_ns,
        stale_after_s: float = DEFAULT_SENSOR_STALE_S,
        max_line_bytes: int = MAX_SENSOR_LINE_BYTES,
    ):
        self.transport = transport
        self.channel_config = channel_config
        self.source = source
        self.device_id = device_id
        self.clock_ns = clock_ns
        self.stale_after_s = stale_after_s
        self.max_line_bytes = max_line_bytes
        self.connected = False
        self.tracker = FrameTracker()
        self.last_frame: TactileFrame | None = None
        self.last_error: str | None = None
        self.last_hello: HelloMessage | None = None
        self.last_error_message: ErrorMessage | None = None
        self.invalid_frames = 0
        self.messages_received = 0
        self.last_anomalies: list = []
        self.state = "OFFLINE"
        self.started_ns = clock_ns()

    # -- lifecycle ---------------------------------------------------------

    def connect(self) -> DeviceStatus:
        if self.connected:
            raise RuntimeError("already_connected")
        try:
            self.transport.connect()
        except Exception as exc:
            self.state = "OFFLINE"
            raise SensorOffline(f"transport connect failed: {exc}") from exc
        self.connected = True
        self.state = "WAITING"
        self.started_ns = self.clock_ns()
        self.last_error = None
        return self.status()

    def close(self) -> None:
        try:
            self.transport.close()
        finally:
            self.connected = False
            self.state = "OFFLINE"

    # -- reading -----------------------------------------------------------

    def read_frame(self, timeout_s: float = 0.0) -> TactileFrame | None:
        if not self.connected:
            raise SensorOffline("sensor is not connected")
        deadline = time.monotonic() + max(0.0, timeout_s)
        while True:
            remaining = max(0.0, deadline - time.monotonic())
            try:
                line = self.transport.readline(remaining)
            except Exception as exc:
                self.connected = False
                self.state = "OFFLINE"
                self.last_error = f"transport: {exc}"
                raise SensorOffline(f"transport read failed: {exc}") from exc
            if line is None:
                break
            self.messages_received += 1
            try:
                result = self._handle_line(line)
            except FrameValidationError as exc:
                self.invalid_frames += 1
                self.last_error = f"{exc.code}: {exc}"
                raise
            if result is not None:
                return result
            if time.monotonic() >= deadline:
                break
        self._update_state()
        return None

    def _handle_line(self, line: bytes | str) -> TactileFrame | None:
        self.last_anomalies = []
        message = parse_envelope(line, max_bytes=self.max_line_bytes)
        message_type = message["type"]
        if message_type == "HELLO":
            hello = parse_hello(message)
            self.last_hello = hello
            self.channel_config = hello.channel_config
            self.device_id = hello.device_id
            self.state = "WAITING"
            return None
        if message_type == "SAMPLE":
            if self.channel_config is None:
                raise FrameValidationError(
                    "SAMPLE received before channel configuration/HELLO",
                    code="MISSING_CONFIG",
                )
            frame = parse_sample(
                message,
                self.channel_config,
                source=self.source,
                host_received_ns=self.clock_ns(),
            )
            anomalies = self.tracker.accept(frame)
            self.last_anomalies = list(anomalies)
            self.last_frame = frame
            self.last_error = None
            self.state = "STREAMING"
            if anomalies:
                self.last_error = anomalies[-1].detail
            return frame
        if message_type == "STATUS":
            status = parse_status(message, source=self.source)
            self.last_error = status.last_error
            self._update_state()
            return None
        if message_type == "ERROR":
            error = parse_error(message)
            self.last_error_message = error
            self.last_error = f"DEVICE_ERROR {error.code}: {error.message}"
            self.state = "DEVICE_ERROR"
            raise ProtocolError(
                self.last_error,
                code="DEVICE_ERROR",
                detail={"device_code": error.code, "fatal": error.fatal},
            )
        raise FrameValidationError(f"unsupported message type {message_type}", code="UNKNOWN_MESSAGE")

    def _update_state(self) -> None:
        if not self.connected:
            self.state = "OFFLINE"
            return
        now = self.clock_ns()
        if self.tracker.stale(now, timeout_s=self.stale_after_s):
            self.state = "WAITING" if self.tracker.last_host_received_ns is None else "STALE"
        elif self.last_frame is not None:
            self.state = "STREAMING"
        else:
            self.state = "WAITING"

    # -- introspection -----------------------------------------------------

    def poll(self) -> DeviceStatus:
        self._update_state()
        return self.status()

    def status(self) -> DeviceStatus:
        self._update_state()
        detail = {
            "messages_received": self.messages_received,
            "accepted_frames": self.tracker.accepted_frames,
            "recent_anomalies": self.tracker.recent_anomalies(10),
            "last_error_message": self.last_error_message.raw if self.last_error_message else None,
            "channel_config_status": self.channel_config.status if self.channel_config else None,
        }
        if self.last_hello is not None:
            detail["hello"] = {
                "firmware_version": self.last_hello.firmware_version,
                "capabilities": list(self.last_hello.capabilities),
            }
        return DeviceStatus(
            device_id=self.device_id,
            kind="SENSOR",
            source=self.source,
            connected=self.connected,
            state=self.state,
            protocol_version=PROTOCOL_VERSION,
            firmware_version=self.last_hello.firmware_version if self.last_hello else None,
            boot_id=self.tracker.last_boot_id,
            channel_count=(
                self.channel_config.expected_channel_count if self.channel_config else None
            ),
            scan_mode=self.channel_config.scan_mode if self.channel_config else None,
            sample_rate_hz=self.last_hello.sample_rate_hz if self.last_hello else None,
            last_frame_seq=self.tracker.last_seq,
            last_mcu_time_us=self.tracker.last_mcu_time_us,
            last_host_received_ns=self.tracker.last_host_received_ns,
            dropped_frames=self.tracker.dropped_frames,
            invalid_frames=self.invalid_frames,
            restart_count=self.tracker.restart_count,
            last_error=self.last_error,
            detail=detail,
        )


class JsonlReplayTransport:
    """Read-only JSONL source.  It can never write to hardware."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.lines = self.path.read_text(encoding="utf-8").splitlines()
        self.offset = 0

    def connect(self) -> None:
        if not self.path.is_file():
            raise FileNotFoundError(str(self.path))

    def close(self) -> None:
        pass

    def readline(self, timeout_s: float) -> bytes | None:
        if self.offset >= len(self.lines):
            return None
        line = self.lines[self.offset]
        self.offset += 1
        return (line + "\n").encode("utf-8")

    def reset(self) -> None:
        self.offset = 0


class ReplaySensorAdapter(SensorAdapter):
    def __init__(self, path: Path | str, channel_config: ChannelConfiguration | None = None, **kwargs):
        self.replay_transport = JsonlReplayTransport(path)
        super().__init__(
            self.replay_transport,
            channel_config,
            source=DataSource.REPLAY,
            **kwargs,
        )

    @property
    def at_end(self) -> bool:
        return self.replay_transport.offset >= len(self.replay_transport.lines)

    def rewind(self) -> None:
        self.replay_transport.reset()
        self.tracker = FrameTracker()
        self.invalid_frames = 0
        self.last_frame = None
        self.last_error = None
        self.state = "WAITING"


class SimulatedSensorTransport:
    """Deterministic synthetic source.  Every line is marked SIMULATION."""

    def __init__(
        self,
        channel_config: ChannelConfiguration,
        *,
        device_id: str = "sensor-simulation",
        boot_id: str = "sim-boot-001",
        period_s: float = 0.2,
    ):
        self.channel_config = channel_config
        self.device_id = device_id
        self.boot_id = boot_id
        self.period_s = period_s
        self.seq = 0
        self.t = 0.0
        self.pending: list[bytes] = []
        self._started = False
        self._last_read = 0.0

    def connect(self) -> None:
        self._started = True
        self.pending = [encode_hello(self.device_id, self.boot_id, self.channel_config)]

    def close(self) -> None:
        self._started = False

    def readline(self, timeout_s: float) -> bytes | None:
        if not self._started:
            return None
        if self.pending:
            return self.pending.pop(0)
        now = time.monotonic()
        if now - self._last_read < self.period_s:
            time.sleep(min(max(timeout_s, 0.0), self.period_s))
            if now - self._last_read < self.period_s:
                return None
        self._last_read = now
        self.seq += 1
        self.t += self.period_s if self.period_s > 0 else 0.01
        frame = self._sample(self.seq)
        return encode_sample(frame)

    def _sample(self, seq: int) -> TactileFrame:
        channels: list[float | None] = []
        mask: list[bool] = []
        for index, channel in enumerate(self.channel_config.channels):
            row = channel.matrix_row or 0
            col = channel.matrix_col or 0
            wave = 2048 + 240 * math.sin(seq * 0.35 + index * 0.7) + 60 * math.cos(row + col)
            valid = not (index == 2 and seq % 17 == 0)
            channels.append(round(wave) if valid else None)
            mask.append(valid)
        contact = 0.0
        if seq > 8:
            contact = min(1.0, (seq - 8) / 40.0)
        return TactileFrame(
            protocol_version=PROTOCOL_VERSION,
            device_id=self.device_id,
            boot_id=self.boot_id,
            frame_seq=seq,
            mcu_time_us=int(self.t * 1_000_000),
            host_received_ns=time.monotonic_ns(),
            channels=tuple(channels),
            valid_mask=tuple(mask),
            source=DataSource.SIMULATION,
            channel_ids=self.channel_config.channel_ids,
            matrix_rows=self.channel_config.matrix_rows,
            matrix_cols=self.channel_config.matrix_cols,
            contact_score=contact,
        ).validate(self.channel_config)


class SimulatedSensorAdapter(SensorAdapter):
    def __init__(
        self,
        channel_config: ChannelConfiguration,
        *,
        device_id: str = "sensor-simulation",
        period_s: float = 0.2,
        **kwargs,
    ):
        self.sim_transport = SimulatedSensorTransport(
            channel_config, device_id=device_id, period_s=period_s
        )
        super().__init__(
            self.sim_transport,
            channel_config,
            source=DataSource.SIMULATION,
            device_id=device_id,
            **kwargs,
        )


def config_from_json_file(path: Path | str) -> ChannelConfiguration:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if "channel_config" in value:
        value = value["channel_config"]
    return ChannelConfiguration.from_dict(value)


def default_demo_config(root: Path | str | None = None) -> ChannelConfiguration:
    """Load the clearly labelled simulation demo channel map.

    It is *not* a hardware map: 6x6 is a Stage H1 target and its scan method is
    still PENDING-HW.
    """
    base = Path(root) if root is not None else PROJECT_ROOT
    return config_from_json_file(base / "config" / "sensor_channels.demo.json")


def describe_config(config: ChannelConfiguration | None) -> dict:
    if config is None:
        return {"channel_count": None, "matrix": None, "status": "UNKNOWN"}
    return {
        "channel_count": config.expected_channel_count,
        "matrix": [config.matrix_rows, config.matrix_cols],
        "status": config.status,
        "scan_mode": config.scan_mode,
        "adc_count": config.adc_count,
    }
