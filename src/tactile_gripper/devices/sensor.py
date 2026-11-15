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
        transport_factory=None,
        reconnect_initial_s: float = 0.5,
        reconnect_max_s: float = 10.0,
        max_reconnect_attempts: int | None = None,
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
        self.last_status: DeviceStatus | None = None
        self.last_error_message: ErrorMessage | None = None
        self.invalid_frames = 0
        self.messages_received = 0
        self.last_anomalies: list = []
        self.state = "OFFLINE"
        self.started_ns = clock_ns()
        self.transport_factory = transport_factory
        self.reconnect_initial_s = max(0.0, float(reconnect_initial_s))
        self.reconnect_max_s = max(self.reconnect_initial_s, float(reconnect_max_s))
        self.max_reconnect_attempts = max_reconnect_attempts
        self.reconnect_count = 0
        self.reconnect_attempts = 0
        self.last_reconnect_error: str | None = None
        self._reconnect_delay = self.reconnect_initial_s
        self.next_reconnect_ns = 0

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
        self.last_reconnect_error = None
        self.next_reconnect_ns = 0
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
                self._mark_offline(f"transport: {exc}")
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

    def _mark_offline(self, reason: str) -> None:
        self.connected = False
        self.state = "OFFLINE"
        self.last_error = reason
        self._reconnect_delay = self.reconnect_initial_s
        self.next_reconnect_ns = self.clock_ns() + int(self._reconnect_delay * 1_000_000_000)
        try:
            self.transport.close()
        except Exception:
            pass

    def maybe_reconnect(self) -> bool:
        """Attempt one bounded reconnect attempt.  Never runs implicitly in connect()."""
        if self.connected or self.transport_factory is None:
            return False
        now = self.clock_ns()
        if now < self.next_reconnect_ns:
            return False
        if self.max_reconnect_attempts is not None and self.reconnect_attempts >= self.max_reconnect_attempts:
            return False
        self.reconnect_attempts += 1
        try:
            new_transport = self.transport_factory()
            new_transport.connect()
        except Exception as exc:
            self.last_reconnect_error = str(exc)
            self._reconnect_delay = min(self.reconnect_max_s, max(self.reconnect_initial_s, self._reconnect_delay * 2))
            self.next_reconnect_ns = now + int(self._reconnect_delay * 1_000_000_000)
            return False
        self.transport = new_transport
        self.connected = True
        self.state = "WAITING"
        self.last_error = None
        self.last_reconnect_error = None
        self.reconnect_count += 1
        self._reconnect_delay = self.reconnect_initial_s
        self.next_reconnect_ns = 0
        return True

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
            self.last_status = status
            self.last_error = status.last_error
            if status.state in ("STREAMING", "FAULT", "WAITING"):
                self.state = status.state
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

    def query_status(self, *, request_id: str | None = None) -> bool:
        """Send an opt-in STATUS query if the transport allows it.

        The device answers on the normal read path; this method never changes
        control state and does not wait for a reply.  A missing capability is
        reported, not silently ignored.
        """
        from ..protocol import encode_status_query

        return self._send_query("STATUS", encode_status_query(request_id=request_id))

    def query_hello(self, *, request_id: str | None = None) -> bool:
        """Ask for a repeat HELLO after a missed boot announcement."""
        from ..protocol import encode_hello_query

        return self._send_query("HELLO", encode_hello_query(request_id=request_id))

    def _send_query(self, label: str, payload: bytes) -> bool:
        write_line = getattr(self.transport, "write_line", None)
        if write_line is None:
            self.last_error = f"transport does not support {label} query"
            return False
        try:
            write_line(payload)
        except Exception as exc:
            self.last_error = f"{label} query failed: {exc}"
            return False
        self.last_error = None
        return True

    def identity(self) -> dict:
        """Identity facts actually observed, not a guessed port name."""
        return {
            "role": "SENSOR",
            "device_id": self.device_id,
            "boot_id": self.tracker.last_boot_id,
            "firmware_version": self.last_hello.firmware_version if self.last_hello else None,
            "sensor_profile": self.channel_config.sensor_profile if self.channel_config else None,
            "channel_count": (
                self.channel_config.expected_channel_count if self.channel_config else None
            ),
            "port": getattr(self.transport, "port", None),
            "baudrate": getattr(self.transport, "baudrate", None),
            "source": self.source.value,
        }

    def status(self) -> DeviceStatus:
        self._update_state()
        detail = {
            "messages_received": self.messages_received,
            "accepted_frames": self.tracker.accepted_frames,
            "recent_anomalies": self.tracker.recent_anomalies(10),
            "last_error_message": self.last_error_message.raw if self.last_error_message else None,
            "channel_config_status": self.channel_config.status if self.channel_config else None,
            "sensor_profile": self.channel_config.sensor_profile if self.channel_config else None,
            "channel_config": self.channel_config.to_dict() if self.channel_config else None,
            "matrix": (
                [self.channel_config.matrix_rows, self.channel_config.matrix_cols]
                if self.channel_config is not None
                else None
            ),
            "fsr_channel_ids": (
                [channel.channel_id for channel in self.channel_config.fsr_channels]
                if self.channel_config is not None
                else []
            ),
            "matrix_channel_ids": (
                [channel.channel_id for channel in self.channel_config.matrix_channels]
                if self.channel_config is not None
                else []
            ),
            "electrode_channel_ids": (
                [channel.channel_id for channel in self.channel_config.electrode_channels]
                if self.channel_config is not None
                else []
            ),
            "device_identity": self.identity(),
            "last_status": self.last_status.to_dict() if self.last_status is not None else None,
            "reconnect_count": self.reconnect_count,
            "reconnect_attempts": self.reconnect_attempts,
            "last_reconnect_error": self.last_reconnect_error,
            "next_reconnect_ns": self.next_reconnect_ns,
            "transport": type(self.transport).__name__,
            "oversize_lines": getattr(self.transport, "oversize_lines", 0),
            "anomaly_overflow_count": self.tracker.anomaly_overflow_count,
        }
        if self.last_hello is not None:
            detail["hello"] = {
                "firmware_version": self.last_hello.firmware_version,
                "sensor_profile": self.last_hello.sensor_profile,
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
    """Read-only JSONL source.  It can never write to hardware.

    A file may be a raw wire capture (HELLO/SAMPLE) or a Trial
    ``frames.jsonl``.  Trial rows are unwrapped into wire SAMPLE messages and
    a HELLO is synthesized from sibling ``metadata.json`` so an existing Trial
    can be replayed without a separate export step.
    """

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.lines = self.path.read_text(encoding="utf-8").splitlines()
        self.lines = self._normalise_trial_lines(self.lines)
        self.offset = 0

    def _normalise_trial_lines(self, lines: list[str]) -> list[str]:
        records: list[dict] = []
        for line in lines:
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                return lines
            if not isinstance(value, dict):
                return lines
            records.append(value)
        frames = [row for row in records if row.get("record_type") == "SENSOR_FRAME"]
        if not frames:
            return lines
        metadata_path = self.path.parent / "metadata.json"
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            metadata = {}
        parameters = metadata.get("parameters") if isinstance(metadata, dict) else {}
        config_payload = (parameters or {}).get("sensor_config")
        if not isinstance(config_payload, dict):
            return lines
        try:
            config = ChannelConfiguration.from_dict(config_payload)
        except (TypeError, ValueError):
            return lines
        identities = (parameters or {}).get("device_identities") or {}
        identity = identities.get("sensor") or {}
        first = frames[0]
        normalised: list[str] = [
            encode_hello(
                str(first.get("device_id") or identity.get("device_id") or "trial-replay"),
                str(first.get("boot_id") or identity.get("boot_id") or "trial-replay"),
                config,
                firmware_version=str(identity.get("firmware_version") or "trial-replay"),
            ).decode("utf-8").strip()
        ]
        for row in frames:
            raw = row.get("raw")
            if isinstance(raw, dict) and raw.get("type") == "SAMPLE":
                payload = raw
            else:
                payload = {
                    "protocol_version": PROTOCOL_VERSION,
                    "type": "SAMPLE",
                    "device_id": row.get("device_id") or identity.get("device_id") or "trial-replay",
                    "boot_id": row.get("boot_id") or identity.get("boot_id") or "trial-replay",
                    "frame_seq": row.get("frame_seq"),
                    "mcu_time_us": row.get("mcu_time_us"),
                    "channel_ids": row.get("channel_ids") or list(config.channel_ids),
                    "channels": row.get("channels"),
                    "valid_mask": row.get("valid_mask"),
                }
                if row.get("contact_score") is not None:
                    payload["contact_score"] = row.get("contact_score")
            normalised.append(json.dumps(payload, ensure_ascii=False, allow_nan=False))
        return normalised

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
        fsr_index = 0
        for index, channel in enumerate(self.channel_config.channels):
            kind = self.channel_config.effective_kind(channel)
            row = channel.matrix_row or 0
            col = channel.matrix_col or 0
            if kind == "FSR":
                # Two clearly different unloaded levels, then a contact ramp.
                # This is synthetic, not a calibrated sensor model.
                baseline = 80_000 + fsr_index * 25_000
                ramp = max(0.0, min(1.0, (seq - 6) / 45.0))
                wave = baseline + 420_000 * ramp + 18_000 * math.sin(seq * 0.31 + fsr_index)
                fsr_index += 1
                valid = not (seq % 29 == 0 and fsr_index == 1)
            elif kind == "MATRIX_ELECTRODE":
                # 12 raw row/column electrode channels only.  No 36-cell
                # pressure estimate is synthesized from them.
                electrode = channel.electrode_index or 0
                wave = 1800 + 260 * math.sin(seq * 0.27 + electrode * 0.9)
                valid = not (index == 7 and seq % 23 == 0)
            else:
                wave = 2048 + 240 * math.sin(seq * 0.35 + index * 0.7) + 60 * math.cos(row + col)
                valid = not (index == 2 and seq % 17 == 0)
            channels.append(round(wave) if valid else None)
            mask.append(valid)
        contact = None
        if (
            not self.channel_config.fsr_channels
            and not self.channel_config.electrode_channels
            and seq > 8
        ):
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


def demo_config_for_profile(
    profile: str = "MATRIX_6X6",
    root: Path | str | None = None,
) -> ChannelConfiguration:
    """Load a labelled offline demo map for a supported sensor profile.

    These are synthetic fixtures, not hardware maps.  ``MATRIX_6X6`` is kept
    as the default to preserve V1 behaviour.
    """
    base = Path(root) if root is not None else PROJECT_ROOT
    names = {
        "MATRIX_6X6": "sensor_channels.demo.json",
        "FSR_ONLY": "sensor_channels.fsr_only.demo.json",
        "HYBRID_6X6_FSR2": "sensor_channels.hybrid.demo.json",
        "MATRIX_ELECTRODES_12": "sensor_channels.matrix_electrodes12.demo.json",
    }
    try:
        name = names[profile.upper()]
    except KeyError as exc:
        raise ValueError(f"unknown demo profile: {profile}") from exc
    return config_from_json_file(base / "config" / name)


def describe_config(config: ChannelConfiguration | None) -> dict:
    if config is None:
        return {"channel_count": None, "matrix": None, "status": "UNKNOWN"}
    return {
        "channel_count": config.expected_channel_count,
        "matrix": [config.matrix_rows, config.matrix_cols],
        "status": config.status,
        "scan_mode": config.scan_mode,
        "adc_count": config.adc_count,
        "sensor_profile": config.sensor_profile,
        "fsr_channel_ids": [channel.channel_id for channel in config.fsr_channels],
        "matrix_channel_count": len(config.matrix_channels),
        "electrode_channel_count": len(config.electrode_channels),
    }
