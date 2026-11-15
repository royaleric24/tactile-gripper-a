"""Wire parsing for the S1 sensor proposal (HELLO/SAMPLE/STATUS/ERROR).

This module implements the *software-side* proposal documented in
``docs/INTERFACE_CONTRACT.md``.  It is not an agreed device protocol.  The
parser is intentionally strict: malformed or ambiguous input is rejected with
a stable error code instead of being silently repaired.
"""

from __future__ import annotations

import json
import math
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Iterable

from tools.fsr2 import protocol_v2 as wire_v2

from .constants import (
    DEFAULT_SENSOR_STALE_S,
    MAX_SENSOR_LINE_BYTES,
    MAX_TRACKED_ANOMALIES,
    PROTOCOL_VERSION,
    SENSOR_MESSAGE_TYPES,
)
from .errors import FrameValidationError, ProtocolError
from .models import (
    ChannelConfiguration,
    DeviceStatus,
    TactileFrame,
    utc_now_iso,
)
from .sources import DataSource


def _unique_pairs(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FrameValidationError(f"duplicate JSON key: {key}", code="INVALID_JSON")
        result[key] = value
    return result


def decode_line(raw: bytes | str, *, max_bytes: int = MAX_SENSOR_LINE_BYTES) -> dict[str, Any]:
    """Decode one bounded JSONL line into an object.

    A single trailing newline is allowed.  Embedded newlines, invalid UTF-8,
    duplicate keys, non-object roots and oversize lines are rejected.
    """
    if isinstance(raw, str):
        try:
            data = raw.encode("utf-8")
        except UnicodeError as exc:
            raise FrameValidationError("invalid UTF-8", code="INVALID_JSON") from exc
    elif isinstance(raw, (bytes, bytearray)):
        data = bytes(raw)
    else:
        raise FrameValidationError("line must be bytes or str", code="INVALID_JSON")
    if len(data) > max_bytes:
        raise FrameValidationError(
            f"line exceeds {max_bytes} bytes", code="FRAME_TOO_LARGE"
        )
    if data.endswith(b"\n"):
        data = data[:-1]
    if not data:
        raise FrameValidationError("empty line", code="INVALID_JSON")
    if b"\n" in data or b"\r" in data:
        raise FrameValidationError("embedded newline", code="INVALID_JSON")
    try:
        text = data.decode("utf-8")
    except UnicodeError as exc:
        raise FrameValidationError("invalid UTF-8", code="INVALID_JSON") from exc
    try:
        value = json.loads(text, object_pairs_hook=_unique_pairs)
    except FrameValidationError:
        raise
    except (ValueError, TypeError) as exc:
        raise FrameValidationError("invalid JSON", code="INVALID_JSON") from exc
    if not isinstance(value, dict):
        raise FrameValidationError("message root must be an object", code="INVALID_JSON")
    return value


def parse_envelope(
    raw: bytes | str,
    *,
    expected_protocol_version: int = PROTOCOL_VERSION,
    max_bytes: int = MAX_SENSOR_LINE_BYTES,
) -> dict[str, Any]:
    message = decode_line(raw, max_bytes=max_bytes)
    if "protocol_version" not in message:
        raise FrameValidationError("missing protocol_version", code="MISSING_FIELD")
    version = message["protocol_version"]
    if type(version) is not int:
        raise FrameValidationError("protocol_version must be an integer", code="PROTOCOL_VERSION")
    if version != expected_protocol_version:
        raise FrameValidationError(
            f"unsupported protocol_version {version}; host supports {expected_protocol_version}",
            code="PROTOCOL_VERSION",
        )
    message_type = message.get("type")
    if not isinstance(message_type, str) or not message_type:
        raise FrameValidationError("missing type", code="MISSING_FIELD")
    if message_type not in SENSOR_MESSAGE_TYPES:
        raise FrameValidationError(f"unknown message type: {message_type}", code="UNKNOWN_MESSAGE")
    return message


def _required_string(message: dict, key: str) -> str:
    value = message.get(key)
    if not isinstance(value, str) or not value:
        raise FrameValidationError(f"{key} must be a non-empty string", code="MISSING_FIELD")
    return value


def _required_int(message: dict, key: str, *, minimum: int = 0) -> int:
    if key not in message:
        raise FrameValidationError(f"missing field: {key}", code="MISSING_FIELD")
    value = message[key]
    if type(value) is not int or value < minimum:
        raise FrameValidationError(f"{key} must be an integer >= {minimum}", code="INVALID_VALUE")
    return value


@dataclass(frozen=True)
class HelloMessage:
    device_id: str
    boot_id: str
    channel_config: ChannelConfiguration
    firmware_version: str = "UNKNOWN"
    scan_mode: str = "UNKNOWN"
    sample_rate_hz: float | None = None
    capabilities: tuple[str, ...] = ()
    sensor_profile: str = "UNKNOWN"
    raw: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)


@dataclass(frozen=True)
class ErrorMessage:
    code: str
    message: str
    request_id: str | None = None
    fatal: bool = False
    device_id: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)


CURRENT_SENSOR_PROFILES = ("FSR_ONLY", "MATRIX_ELECTRODES_12")


def validate_wire_v2(message: dict[str, Any]):
    """Reuse the firmware team's reference checks; translate errors for the UI."""
    try:
        return wire_v2.PARSERS[message["type"]](message)
    except wire_v2.FrameValidationError as exc:
        raise FrameValidationError(str(exc), code=exc.code) from exc


def is_wire_v2(message: dict[str, Any]) -> bool:
    return "reference_mode" in message or "raw_adc" in message


def v2_channel_config(message: dict[str, Any]) -> ChannelConfiguration:
    """Project a validated HELLO/STATUS into the existing host model."""
    config = message["channel_config"]
    profile = message["sensor_profile"]
    count = message["channel_count"]
    channels = []
    for layout, entry in zip(wire_v2.expected_layout(profile, count), config["channels"]):
        electrode = layout.kind == "ELECTRODE"
        channels.append({
            "channel_id": layout.channel_id,
            "sensor_kind": "MATRIX_ELECTRODE" if electrode else "FSR",
            "name": (wire_v2.ELECTRODE_NAMES[layout.channel_id] if electrode
                     else ("FSR_A", "FSR_B")[layout.channel_id - (count - 2)]),
            "electrode_axis": layout.role if electrode else None,
            "electrode_index": layout.position - 1 if electrode else None,
            "ads1220_id": entry.get("ads1220_id"),
            "adc_input": entry.get("adc_input"),
            "mux_channel": entry.get("mux_channel"),
            "unit": "ADC_COUNTS",
            "adc_bits": 24,
        })
    return ChannelConfiguration.from_dict({
        "status": config["status"],
        "scan_mode": config.get("scan_mode", "UNKNOWN"),
        "adc_count": config["adc_count"],
        "sensor_profile": profile,
        "mapping_status": (message.get("electrode_layout") or {}).get("mapping_status"),
        "channels": channels,
    })


def parse_hello(message: dict[str, Any], *, strict_v2: bool = False) -> HelloMessage:
    if message.get("type") != "HELLO":
        raise ProtocolError("not a HELLO message")
    channel_config = message.get("channel_config")
    if not isinstance(channel_config, dict):
        raise FrameValidationError("missing channel_config", code="MISSING_FIELD")
    if "sensor_profile" in channel_config and "sensor_profile" in message and (
        channel_config["sensor_profile"] != message["sensor_profile"]
    ):
        raise FrameValidationError("top-level and channel_config sensor_profile disagree", code="PROFILE_CONFLICT")
    config_payload = dict(channel_config)
    if "sensor_profile" not in config_payload and message.get("sensor_profile") is not None:
        config_payload["sensor_profile"] = message.get("sensor_profile")
    try:
        if strict_v2 or is_wire_v2(message):
            validate_wire_v2(message)
            config = v2_channel_config(message)
        else:
            config = ChannelConfiguration.from_dict(config_payload)
    except ValueError as exc:
        raise FrameValidationError(f"invalid channel_config: {exc}", code="INVALID_CHANNEL") from exc
    sample_rate = message.get("sample_rate_hz")
    if sample_rate is not None and (
        type(sample_rate) not in (int, float) or not math.isfinite(sample_rate) or sample_rate <= 0
    ):
        raise FrameValidationError("sample_rate_hz must be null or positive finite", code="INVALID_VALUE")
    capabilities = message.get("capabilities", [])
    if not isinstance(capabilities, list) or not all(isinstance(item, str) for item in capabilities):
        raise FrameValidationError("capabilities must be a list of strings", code="INVALID_VALUE")
    return HelloMessage(
        device_id=_required_string(message, "device_id"),
        boot_id=_required_string(message, "boot_id"),
        channel_config=config,
        firmware_version=str(message.get("firmware_version", "UNKNOWN")),
        scan_mode=str(message.get("scan_mode", "UNKNOWN")),
        sample_rate_hz=float(sample_rate) if sample_rate is not None else None,
        capabilities=tuple(capabilities),
        sensor_profile=config.sensor_profile,
        raw=message,
    )


def parse_sample(
    message: dict[str, Any],
    channel_config: ChannelConfiguration,
    *,
    source: DataSource = DataSource.LIVE,
    host_received_ns: int | None = None,
    host_received_utc: str | None = None,
    strict_v2: bool = False,
) -> TactileFrame:
    if message.get("type") != "SAMPLE":
        raise ProtocolError("not a SAMPLE message")
    if strict_v2 or is_wire_v2(message):
        wire = validate_wire_v2(message)
        if wire.profile != channel_config.sensor_profile or wire.channel_count != channel_config.expected_channel_count:
            raise FrameValidationError("SAMPLE profile/count differs from HELLO", code="PROFILE_CONFLICT")
        for entry, valid in zip(channel_config.channels, wire.valid):
            if not valid:
                continue
            if entry.ads1220_id is None:
                raise FrameValidationError("SAMPLE claims data from an unmapped ADC", code="ADC_DATA_CONFLICT")
    channels_raw = message.get("channels")
    mask_raw = message.get("valid_mask")
    if not isinstance(channels_raw, list) or not isinstance(mask_raw, list):
        raise FrameValidationError("channels and valid_mask must be arrays", code="MISSING_FIELD")
    if len(channels_raw) != len(mask_raw):
        raise FrameValidationError("channels and valid_mask length differ", code="LENGTH_MISMATCH")
    channel_ids_raw = message.get("channel_ids")
    channel_ids: tuple[int, ...] | None = None
    if channel_ids_raw is not None:
        if not isinstance(channel_ids_raw, list) or not all(type(item) is int for item in channel_ids_raw):
            raise FrameValidationError("channel_ids must be an array of integers", code="INVALID_CHANNEL")
        channel_ids = tuple(channel_ids_raw)
    contact_score = None if strict_v2 or is_wire_v2(message) else message.get("contact_score")
    if contact_score is not None and (
        type(contact_score) not in (int, float) or not math.isfinite(contact_score)
    ):
        raise FrameValidationError("contact_score must be null or finite", code="INVALID_VALUE")
    if host_received_ns is None:
        import time

        host_received_ns = time.monotonic_ns()
    if host_received_utc is None:
        host_received_utc = utc_now_iso()
    frame = TactileFrame(
        protocol_version=int(message["protocol_version"]),
        device_id=_required_string(message, "device_id"),
        boot_id=_required_string(message, "boot_id"),
        frame_seq=_required_int(message, "frame_seq"),
        mcu_time_us=_required_int(message, "mcu_time_us"),
        host_received_ns=_required_int({"host_received_ns": host_received_ns}, "host_received_ns"),
        channels=tuple(channels_raw),
        valid_mask=tuple(mask_raw),
        source=source,
        channel_ids=channel_ids,
        matrix_rows=message.get("matrix_rows"),
        matrix_cols=message.get("matrix_cols"),
        contact_score=float(contact_score) if contact_score is not None else None,
        host_received_utc=host_received_utc,
        raw=message,
    )
    return frame.validate(channel_config)


def parse_status(message: dict[str, Any], *, source: DataSource = DataSource.LIVE) -> DeviceStatus:
    if message.get("type") != "STATUS":
        raise ProtocolError("not a STATUS message")
    channel_count = message.get("channel_count")
    if channel_count is not None and (type(channel_count) is not int or channel_count < 0):
        raise FrameValidationError("channel_count must be null or integer", code="INVALID_VALUE")
    uptime = message.get("uptime_ms")
    if uptime is not None and (type(uptime) is not int or uptime < 0):
        raise FrameValidationError("uptime_ms must be null or integer", code="INVALID_VALUE")
    return DeviceStatus(
        device_id=str(message.get("device_id", "UNKNOWN")),
        kind="SENSOR",
        source=source,
        connected=True,
        state=str(message.get("sensor_state", "UNKNOWN")),
        firmware_version=message.get("firmware_version"),
        boot_id=message.get("boot_id"),
        uptime_ms=uptime,
        channel_count=channel_count,
        scan_mode=message.get("scan_mode"),
        sample_rate_hz=message.get("sample_rate_hz"),
        last_frame_seq=message.get("last_frame_seq"),
        last_error=message.get("last_error"),
        detail={"wire": message},
    )


def parse_error(message: dict[str, Any]) -> ErrorMessage:
    if message.get("type") != "ERROR":
        raise ProtocolError("not an ERROR message")
    code = message.get("code")
    if not isinstance(code, str) or not code:
        raise FrameValidationError("error code must be a non-empty string", code="MISSING_FIELD")
    fatal = message.get("fatal", False)
    if type(fatal) is not bool:
        raise FrameValidationError("fatal must be boolean", code="INVALID_VALUE")
    return ErrorMessage(
        code=code,
        message=str(message.get("message", "")),
        request_id=message.get("request_id"),
        fatal=fatal,
        device_id=message.get("device_id"),
        raw=message,
    )


# ---------------------------------------------------------------------------
# Encoders (used by the simulator, replay fixtures and tests; not a device SDK)


def _json_line(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n").encode("utf-8")


def encode_hello(
    device_id: str,
    boot_id: str,
    channel_config: ChannelConfiguration,
    *,
    firmware_version: str = "sensor-h1-proposal.0",
    sample_rate_hz: float | None = None,
) -> bytes:
    return _json_line(
        {
            "protocol_version": PROTOCOL_VERSION,
            "type": "HELLO",
            "device_id": device_id,
            "boot_id": boot_id,
            "firmware_version": firmware_version,
            "scan_mode": channel_config.scan_mode,
            "sample_rate_hz": sample_rate_hz,
            "sensor_profile": channel_config.sensor_profile,
            "channel_config": channel_config.to_dict(),
        }
    )


def encode_sample(frame: TactileFrame) -> bytes:
    payload: dict[str, Any] = {
        "protocol_version": frame.protocol_version,
        "type": "SAMPLE",
        "device_id": frame.device_id,
        "boot_id": frame.boot_id,
        "frame_seq": frame.frame_seq,
        "mcu_time_us": frame.mcu_time_us,
        "channels": list(frame.channels),
        "valid_mask": list(frame.valid_mask),
    }
    if frame.channel_ids is not None:
        payload["channel_ids"] = list(frame.channel_ids)
    if frame.matrix_rows is not None:
        payload["matrix_rows"] = frame.matrix_rows
        payload["matrix_cols"] = frame.matrix_cols
    if frame.contact_score is not None:
        payload["contact_score"] = frame.contact_score
    return _json_line(payload)


def encode_status(
    *,
    device_id: str,
    boot_id: str,
    firmware_version: str = "sensor-h1-proposal.0",
    uptime_ms: int = 0,
    channel_count: int | None = None,
    sensor_state: str = "STREAMING",
    sample_rate_hz: float | None = None,
) -> bytes:
    return _json_line(
        {
            "protocol_version": PROTOCOL_VERSION,
            "type": "STATUS",
            "device_id": device_id,
            "boot_id": boot_id,
            "firmware_version": firmware_version,
            "uptime_ms": uptime_ms,
            "channel_count": channel_count,
            "sample_rate_hz": sample_rate_hz,
            "scan_mode": "UNKNOWN",
            "sensor_state": sensor_state,
            "last_frame_seq": None,
            "last_error": None,
        }
    )


def encode_status_query(*, request_id: str | None = None) -> bytes:
    """V2 read-only STATUS command; firmware echoes an optional request ID."""
    return wire_v2.encode_command("STATUS", request_id=request_id)


def encode_hello_query() -> bytes:
    """Ask V2 firmware to repeat HELLO; it never echoes a request ID."""
    return wire_v2.encode_command("HELLO")


def encode_error(
    code: str,
    message: str = "",
    *,
    device_id: str = "sensor-esp32-01",
    request_id: str | None = None,
    fatal: bool = False,
) -> bytes:
    return _json_line(
        {
            "protocol_version": PROTOCOL_VERSION,
            "type": "ERROR",
            "device_id": device_id,
            "code": code,
            "message": message,
            "request_id": request_id,
            "fatal": fatal,
        }
    )


# ---------------------------------------------------------------------------
# Stateful stream checks


@dataclass(frozen=True)
class FrameAnomaly:
    kind: str
    detail: str
    expected_seq: int | None = None
    actual_seq: int | None = None
    dropped: int = 0
    boot_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "detail": self.detail,
            "expected_seq": self.expected_seq,
            "actual_seq": self.actual_seq,
            "dropped": self.dropped,
            "boot_id": self.boot_id,
        }


class FrameTracker:
    """Detect duplicate, missing, out-of-order and restarted streams."""

    def __init__(self, *, max_anomalies: int = MAX_TRACKED_ANOMALIES):
        self.max_anomalies = max_anomalies
        self.last_boot_id: str | None = None
        self.last_seq: int | None = None
        self.last_mcu_time_us: int | None = None
        self.last_host_received_ns: int | None = None
        self.dropped_frames = 0
        self.restart_count = 0
        self.accepted_frames = 0
        self.anomaly_overflow_count = 0
        self.anomalies: deque[FrameAnomaly] = deque(maxlen=max_anomalies)

    def reset(self) -> None:
        self.last_boot_id = None
        self.last_seq = None
        self.last_mcu_time_us = None
        self.last_host_received_ns = None

    def _record(self, anomalies: list[FrameAnomaly], anomaly: FrameAnomaly) -> None:
        anomalies.append(anomaly)
        if len(self.anomalies) >= self.anomalies.maxlen:
            self.anomaly_overflow_count += 1
        self.anomalies.append(anomaly)

    def accept(self, frame: TactileFrame) -> list[FrameAnomaly]:
        anomalies: list[FrameAnomaly] = []
        if self.last_boot_id is None:
            pass
        elif frame.boot_id != self.last_boot_id:
            self.restart_count += 1
            self._record(
                anomalies,
                FrameAnomaly(
                    kind="DEVICE_RESTART",
                    detail="boot_id changed; sequence/time baseline reset",
                    actual_seq=frame.frame_seq,
                    boot_id=frame.boot_id,
                ),
            )
            self.last_seq = None
            self.last_mcu_time_us = None
        else:
            assert self.last_seq is not None
            if frame.frame_seq == self.last_seq:
                raise FrameValidationError(
                    f"duplicate frame {frame.frame_seq}", code="DUPLICATE_FRAME"
                )
            if frame.frame_seq < self.last_seq:
                raise FrameValidationError(
                    f"frame_seq regressed from {self.last_seq} to {frame.frame_seq}",
                    code="SEQUENCE_REGRESSION",
                )
            assert self.last_mcu_time_us is not None
            wire = frame.raw or {}
            time_delta = frame.mcu_time_us - self.last_mcu_time_us
            if is_wire_v2(wire):
                time_delta &= 0xFFFFFFFF
            if time_delta <= 0 or (is_wire_v2(wire) and time_delta >= 0x80000000):
                raise FrameValidationError(
                    "mcu_time_us is not strictly increasing", code="TIMESTAMP_ANOMALY"
                )
            if self.last_host_received_ns is not None and frame.host_received_ns < self.last_host_received_ns:
                raise FrameValidationError(
                    "host receive clock moved backwards", code="HOST_CLOCK_ANOMALY"
                )
            if frame.frame_seq > self.last_seq + 1:
                missing = frame.frame_seq - self.last_seq - 1
                self.dropped_frames += missing
                self._record(
                    anomalies,
                    FrameAnomaly(
                        kind="FRAME_GAP",
                        detail=f"{missing} frame(s) missing",
                        expected_seq=self.last_seq + 1,
                        actual_seq=frame.frame_seq,
                        dropped=missing,
                        boot_id=frame.boot_id,
                    ),
                )
        self.accepted_frames += 1
        self.last_boot_id = frame.boot_id
        self.last_seq = frame.frame_seq
        self.last_mcu_time_us = frame.mcu_time_us
        self.last_host_received_ns = frame.host_received_ns
        return anomalies

    def stale(self, now_ns: int, *, timeout_s: float = DEFAULT_SENSOR_STALE_S) -> bool:
        if self.last_host_received_ns is None:
            return True
        return now_ns - self.last_host_received_ns > int(timeout_s * 1_000_000_000)

    def recent_anomalies(self, limit: int = 20) -> list[dict[str, Any]]:
        return [item.to_dict() for item in list(self.anomalies)[-limit:]]
