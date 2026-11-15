"""Strict parser for the tactile ADS1220 JSON Lines protocol.

This module is deliberately dependency-free (standard library only) so the
software group can import or copy it.  Invalid or ambiguous input raises
``FrameValidationError``; nothing is silently repaired.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

PROTOCOL_VERSION = 1
CHANNEL_COUNT = 12
ADC_COUNT = 3
ADC_MIN = -8388608
ADC_MAX = 8388607
MAX_LINE_BYTES = 65536

REFERENCE_MODES = ("INTERNAL_2V048", "AVDD_AVSS")
ADC_STATES = ("OK", "CONFIG_ERROR", "NO_RESPONSE", "RECOVERING", "FAILED")

# Channel quality bit flags emitted by the firmware.  A valid channel may carry
# flags (for example saturation) without being fabricated; invalid channels have
# CH_FLAG_NO_DATA and a null raw value.
FLAG_SAT_HIGH = 0x01
FLAG_SAT_LOW = 0x02
FLAG_NEGATIVE_SINGLE_ENDED = 0x04
FLAG_NEAR_RAIL = 0x08
FLAG_STUCK_EXTREME = 0x10
FLAG_NO_DATA = 0x20

CHANNEL_FLAGS = {
    0x01: "SAT_HIGH",
    0x02: "SAT_LOW",
    0x04: "NEGATIVE_SINGLE_ENDED",
    0x08: "NEAR_RAIL",
    0x10: "STUCK_EXTREME",
    0x20: "NO_DATA",
}


class ProtocolError(Exception):
    def __init__(self, message: str, code: str = "PROTOCOL_ERROR") -> None:
        super().__init__(message)
        self.code = code


class FrameValidationError(ProtocolError):
    pass


def flag_names(mask: int) -> List[str]:
    return [name for bit, name in CHANNEL_FLAGS.items() if mask & bit]


def channel_id(adc: int, ain: int) -> int:
    """Channel index for ADC 1..3 and AIN 0..3 (fixed order)."""
    if not 1 <= adc <= 3 or not 0 <= ain <= 3:
        raise ValueError("adc must be 1..3 and ain must be 0..3")
    return (adc - 1) * 4 + ain


def channel_label(index: int) -> str:
    if not 0 <= index < CHANNEL_COUNT:
        raise ValueError("channel index must be 0..11")
    return "ADC{}_AIN{}".format(index // 4 + 1, index % 4)


def _unique_pairs(pairs: Iterable[Tuple[str, Any]]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FrameValidationError("duplicate JSON key: {}".format(key), code="INVALID_JSON")
        result[key] = value
    return result


def decode_line(raw: Any, max_bytes: int = MAX_LINE_BYTES) -> Dict[str, Any]:
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
        raise FrameValidationError("line exceeds {} bytes".format(max_bytes), code="FRAME_TOO_LARGE")
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
        raise FrameValidationError("invalid JSON: {}".format(exc), code="INVALID_JSON") from exc
    if not isinstance(value, dict):
        raise FrameValidationError("message root must be an object", code="INVALID_JSON")
    return value


def _require_int(value: Any, name: str, minimum: Optional[int] = None) -> int:
    if type(value) is not int:
        raise FrameValidationError("{} must be an integer".format(name), code="INVALID_VALUE")
    if minimum is not None and value < minimum:
        raise FrameValidationError("{} must be >= {}".format(name, minimum), code="INVALID_VALUE")
    return value


def _optional_int(value: Any, name: str, minimum: Optional[int] = None) -> Optional[int]:
    if value is None:
        return None
    return _require_int(value, name, minimum)


def _require_str(value: Any, name: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value):
        raise FrameValidationError("{} must be a non-empty string".format(name), code="INVALID_VALUE")
    return value


def _require_bool(value: Any, name: str) -> bool:
    if type(value) is not bool:
        raise FrameValidationError("{} must be boolean".format(name), code="INVALID_VALUE")
    return value


def _require_list(value: Any, name: str, length: int) -> List[Any]:
    if not isinstance(value, list):
        raise FrameValidationError("{} must be an array".format(name), code="MISSING_FIELD")
    if len(value) != length:
        raise FrameValidationError(
            "{} must contain exactly {} entries (got {})".format(name, length, len(value)),
            code="LENGTH_MISMATCH",
        )
    return value


def _require_number(value: Any, name: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise FrameValidationError("{} must be a finite number".format(name), code="INVALID_VALUE")
    return float(value)


@dataclass(frozen=True)
class AdcStatus:
    index: int
    state: str
    code: Optional[int] = None
    consecutive_errors: Optional[int] = None
    total_errors: Optional[int] = None
    recovered: Optional[int] = None
    last_error: Optional[str] = None

    @classmethod
    def from_dict(cls, value: Any, expected_index: int) -> "AdcStatus":
        if not isinstance(value, dict):
            raise FrameValidationError("adc_status entries must be objects", code="INVALID_ADC_STATUS")
        index = _require_int(value.get("id"), "adc_status.id", 1)
        if index != expected_index:
            raise FrameValidationError(
                "adc_status order/id mismatch: expected {}, got {}".format(expected_index, index),
                code="INVALID_ADC_STATUS",
            )
        state = _require_str(value.get("state"), "adc_status.state")
        if state not in ADC_STATES:
            raise FrameValidationError("unknown ADC state: {}".format(state), code="INVALID_ADC_STATUS")
        code = _optional_int(value.get("code"), "adc_status.code", 0)
        consecutive = _optional_int(value.get("consecutive_errors"), "adc_status.consecutive_errors", 0)
        total = _optional_int(value.get("total_errors"), "adc_status.total_errors", 0)
        recovered = _optional_int(value.get("recovered"), "adc_status.recovered", 0)
        last_error = value.get("last_error")
        if last_error is not None and not isinstance(last_error, str):
            raise FrameValidationError("adc_status.last_error must be null or string", code="INVALID_ADC_STATUS")
        return cls(index, state, code, consecutive, total, recovered, last_error)


def parse_adc_status(value: Any) -> Tuple[AdcStatus, ...]:
    entries = _require_list(value, "adc_status", ADC_COUNT)
    return tuple(AdcStatus.from_dict(item, index + 1) for index, item in enumerate(entries))


@dataclass(frozen=True)
class SampleFrame:
    device_id: str
    boot_id: str
    frame_seq: int
    timestamp_us: int
    raw_adc: Tuple[Optional[int], ...]
    valid: Tuple[bool, ...]
    sample_timestamp_us: Tuple[Optional[int], ...]
    channel_flags: Tuple[int, ...]
    adc_status: Tuple[AdcStatus, ...]
    reference_mode: str
    effective_frame_rate_hz: float
    firmware_version: str = "UNKNOWN"
    mcu_time_us: Optional[int] = None
    frame_period_us: Optional[int] = None
    host_received_ns: int = 0
    host_received_utc: str = ""
    host_monotonic_ns: int = 0
    raw: Dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    @property
    def channel_count(self) -> int:
        return len(self.raw_adc)

    @property
    def valid_count(self) -> int:
        return sum(1 for flag in self.valid if flag)

    @property
    def invalid_channels(self) -> Tuple[int, ...]:
        return tuple(index for index, flag in enumerate(self.valid) if not flag)

    def channels(self) -> Tuple[Optional[int], ...]:
        return self.raw_adc

    def pairs(self):
        for index, (value, is_valid) in enumerate(zip(self.raw_adc, self.valid)):
            yield index, value, is_valid

    def to_csv_row(self) -> Dict[str, Any]:
        row: Dict[str, Any] = {
            "frame_seq": self.frame_seq,
            "device_timestamp_us": self.timestamp_us,
            "host_received_unix_ns": self.host_received_ns,
            "host_received_iso": self.host_received_utc,
            "host_monotonic_ns": self.host_monotonic_ns,
            "boot_id": self.boot_id,
            "reference_mode": self.reference_mode,
            "effective_frame_rate_hz": "{:.2f}".format(self.effective_frame_rate_hz),
        }
        for index in range(CHANNEL_COUNT):
            row["ch{}".format(index)] = "" if self.raw_adc[index] is None else self.raw_adc[index]
            row["valid{}".format(index)] = 1 if self.valid[index] else 0
            row["flag{}".format(index)] = self.channel_flags[index]
        for index, status in enumerate(self.adc_status):
            row["adc{}_state".format(index + 1)] = status.state
        return row


CSV_COLUMNS = (
    ["frame_seq", "device_timestamp_us", "host_received_unix_ns", "host_received_iso", "host_monotonic_ns", "boot_id", "reference_mode", "effective_frame_rate_hz"]
    + ["ch{}".format(index) for index in range(CHANNEL_COUNT)]
    + ["valid{}".format(index) for index in range(CHANNEL_COUNT)]
    + ["flag{}".format(index) for index in range(CHANNEL_COUNT)]
    + ["adc1_state", "adc2_state", "adc3_state"]
)


def parse_sample(message: Dict[str, Any]) -> SampleFrame:
    if message.get("type") != "SAMPLE":
        raise ProtocolError("not a SAMPLE message")
    device_id = _require_str(message.get("device_id"), "device_id")
    boot_id = _require_str(message.get("boot_id"), "boot_id")
    firmware_version = str(message.get("firmware_version", "UNKNOWN"))
    frame_seq = _require_int(message.get("frame_seq"), "frame_seq", 0)
    timestamp_us = _require_int(message.get("timestamp_us", message.get("mcu_time_us")), "timestamp_us", 0)
    mcu_time_us = _optional_int(message.get("mcu_time_us"), "mcu_time_us", 0)
    frame_period_us = _optional_int(message.get("frame_period_us"), "frame_period_us", 0)

    raw_values = message.get("raw_adc", message.get("channels"))
    valid_values = message.get("valid", message.get("valid_mask"))
    raw_values = _require_list(raw_values, "raw_adc", CHANNEL_COUNT)
    valid_values = _require_list(valid_values, "valid", CHANNEL_COUNT)
    timestamp_values = _require_list(message.get("sample_timestamp_us"), "sample_timestamp_us", CHANNEL_COUNT)
    flag_values = _require_list(message.get("channel_flags"), "channel_flags", CHANNEL_COUNT)

    raw_adc: List[Optional[int]] = []
    valid: List[bool] = []
    sample_timestamp: List[Optional[int]] = []
    flags: List[int] = []
    for index in range(CHANNEL_COUNT):
        is_valid = _require_bool(valid_values[index], "valid[{}]".format(index))
        value = raw_values[index]
        if is_valid:
            if type(value) is not int:
                raise FrameValidationError(
                    "valid channel {} must contain an integer raw value".format(index), code="INVALID_VALUE"
                )
            if not ADC_MIN <= value <= ADC_MAX:
                raise FrameValidationError(
                    "channel {} outside signed 24-bit range: {}".format(index, value), code="OUT_OF_RANGE"
                )
            sample_time = _optional_int(timestamp_values[index], "sample_timestamp_us[{}]".format(index), 0)
            if sample_time is None:
                raise FrameValidationError(
                    "valid channel {} has no sample timestamp".format(index), code="MISSING_FIELD"
                )
            raw_adc.append(value)
            sample_timestamp.append(sample_time)
        else:
            if value is not None:
                raise FrameValidationError(
                    "invalid channel {} must be null, not a fabricated value".format(index), code="INVALID_VALUE"
                )
            if timestamp_values[index] is not None:
                raise FrameValidationError(
                    "invalid channel {} must have a null sample timestamp".format(index), code="INVALID_VALUE"
                )
            raw_adc.append(None)
            sample_timestamp.append(None)
        valid.append(is_valid)
        flag_value = _optional_int(flag_values[index], "channel_flags[{}]".format(index), 0)
        if flag_value is None:
            raise FrameValidationError("channel_flags[{}] must be an integer".format(index), code="INVALID_VALUE")
        flags.append(flag_value)

    # Reject a channel marked valid that claims NO_DATA, and an invalid channel
    # that hides its NO_DATA flag.  This keeps the two validity representations
    # consistent.
    for index in range(CHANNEL_COUNT):
        no_data = bool(flags[index] & FLAG_NO_DATA)
        if valid[index] == no_data:
            raise FrameValidationError(
                "channel {} valid flag and NO_DATA flag disagree".format(index), code="INVALID_MASK"
            )

    # If the compatibility fields are present they must agree exactly.
    if "channels" in message:
        compat = _require_list(message.get("channels"), "channels", CHANNEL_COUNT)
        if list(compat) != raw_adc:
            raise FrameValidationError("channels disagrees with raw_adc", code="INVALID_VALUE")
    if "valid_mask" in message:
        compat = _require_list(message.get("valid_mask"), "valid_mask", CHANNEL_COUNT)
        if [bool(item) for item in compat] != valid:
            raise FrameValidationError("valid_mask disagrees with valid", code="INVALID_VALUE")

    reference_mode = _require_str(message.get("reference_mode"), "reference_mode")
    if reference_mode not in REFERENCE_MODES:
        raise FrameValidationError("unknown reference_mode: {}".format(reference_mode), code="INVALID_VALUE")
    rate = _require_number(message.get("effective_frame_rate_hz"), "effective_frame_rate_hz")
    if rate < 0:
        raise FrameValidationError("effective_frame_rate_hz must be >= 0", code="INVALID_VALUE")

    return SampleFrame(
        device_id=device_id,
        boot_id=boot_id,
        frame_seq=frame_seq,
        timestamp_us=timestamp_us,
        raw_adc=tuple(raw_adc),
        valid=tuple(valid),
        sample_timestamp_us=tuple(sample_timestamp),
        channel_flags=tuple(flags),
        adc_status=parse_adc_status(message.get("adc_status")),
        reference_mode=reference_mode,
        effective_frame_rate_hz=rate,
        firmware_version=firmware_version,
        mcu_time_us=mcu_time_us,
        frame_period_us=frame_period_us,
        raw=message,
    )


@dataclass(frozen=True)
class HelloMessage:
    device_id: str
    boot_id: str
    firmware_version: str
    channel_count: int
    channel_ids: Tuple[int, ...]
    reference_mode: Optional[str]
    raw: Dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    @property
    def channel_config(self):
        value = self.raw.get("channel_config")
        return value if isinstance(value, dict) else None


@dataclass(frozen=True)
class StatusMessage:
    device_id: str
    boot_id: str
    firmware_version: str
    streaming: bool
    sensor_state: str
    reference_mode: Optional[str]
    adc_status: Tuple[AdcStatus, ...]
    effective_frame_rate_hz: Optional[float]
    last_frame_seq: Optional[int]
    uptime_ms: Optional[int]
    diag: Optional[Dict[str, Any]] = None
    request_id: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict, compare=False, repr=False)


@dataclass(frozen=True)
class ErrorMessage:
    code: str
    message: str
    fatal: bool = False
    request_id: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict, compare=False, repr=False)


@dataclass(frozen=True)
class PongMessage:
    device_id: str
    boot_id: str
    firmware_version: str
    request_id: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict, compare=False, repr=False)


def parse_hello(message: Dict[str, Any]) -> HelloMessage:
    channel_count = _require_int(message.get("channel_count"), "channel_count", 0)
    if channel_count != CHANNEL_COUNT:
        raise FrameValidationError("HELLO channel_count must be 12", code="LENGTH_MISMATCH")
    channel_ids = message.get("channel_ids")
    if channel_ids is None:
        # 0.1.3 emits channel identity inside channel_config, not a top-level
        # channel_ids array.  Derive it only from device-provided channel
        # metadata; never synthesize a map when the field is absent.
        config = message.get("channel_config")
        channels = config.get("channels") if isinstance(config, dict) else None
        if not isinstance(channels, list):
            raise FrameValidationError("HELLO missing channel_ids and channel_config", code="MISSING_FIELD")
        channel_ids = [item.get("channel_id") for item in channels if isinstance(item, dict)]
    channel_ids = _require_list(channel_ids, "channel_ids", CHANNEL_COUNT)
    if [int(item) for item in channel_ids] != list(range(CHANNEL_COUNT)):
        raise FrameValidationError("HELLO channel_ids must be 0..11", code="INVALID_CHANNEL")
    reference_mode = message.get("reference_mode")
    if reference_mode is not None and reference_mode not in REFERENCE_MODES:
        raise FrameValidationError("unknown reference_mode in HELLO", code="INVALID_VALUE")
    return HelloMessage(
        device_id=_require_str(message.get("device_id"), "device_id"),
        boot_id=_require_str(message.get("boot_id"), "boot_id"),
        firmware_version=str(message.get("firmware_version", "UNKNOWN")),
        channel_count=channel_count,
        channel_ids=tuple(int(item) for item in channel_ids),
        reference_mode=reference_mode,
        raw=message,
    )


def parse_status(message: Dict[str, Any]) -> StatusMessage:
    reference_mode = message.get("reference_mode")
    if reference_mode is not None and reference_mode not in REFERENCE_MODES:
        raise FrameValidationError("unknown reference_mode in STATUS", code="INVALID_VALUE")
    rate = message.get("effective_frame_rate_hz")
    rate_value: Optional[float] = None
    if rate is not None:
        rate_value = _require_number(rate, "effective_frame_rate_hz")
    streaming = message.get("streaming")
    if streaming is not None:
        streaming = _require_bool(streaming, "streaming")
    else:
        streaming = str(message.get("sensor_state", "")).upper() == "STREAMING"
    return StatusMessage(
        device_id=str(message.get("device_id", "UNKNOWN")),
        boot_id=str(message.get("boot_id", "UNKNOWN")),
        firmware_version=str(message.get("firmware_version", "UNKNOWN")),
        streaming=bool(streaming),
        sensor_state=str(message.get("sensor_state", "UNKNOWN")),
        reference_mode=reference_mode,
        adc_status=parse_adc_status(message.get("adc_status")) if "adc_status" in message else (),
        effective_frame_rate_hz=rate_value,
        last_frame_seq=_optional_int(message.get("last_frame_seq"), "last_frame_seq", 0),
        uptime_ms=_optional_int(message.get("uptime_ms"), "uptime_ms", 0),
        diag=message.get("diag") if isinstance(message.get("diag"), dict) else None,
        request_id=message.get("request_id") if isinstance(message.get("request_id"), str) else None,
        raw=message,
    )


def parse_error(message: Dict[str, Any]) -> ErrorMessage:
    return ErrorMessage(
        code=_require_str(message.get("code"), "code"),
        message=str(message.get("message", "")),
        fatal=_require_bool(message.get("fatal", False), "fatal"),
        request_id=message.get("request_id") if isinstance(message.get("request_id"), str) else None,
        raw=message,
    )


def parse_pong(message: Dict[str, Any]) -> PongMessage:
    return PongMessage(
        device_id=str(message.get("device_id", "UNKNOWN")),
        boot_id=str(message.get("boot_id", "UNKNOWN")),
        firmware_version=str(message.get("firmware_version", "UNKNOWN")),
        request_id=message.get("request_id") if isinstance(message.get("request_id"), str) else None,
        raw=message,
    )


def parse_message(raw: Any) -> Any:
    message = decode_line(raw)
    if "protocol_version" not in message:
        raise FrameValidationError("missing protocol_version", code="MISSING_FIELD")
    version = message["protocol_version"]
    if type(version) is not int or version != PROTOCOL_VERSION:
        raise FrameValidationError("unsupported protocol_version", code="PROTOCOL_VERSION")
    message_type = message.get("type")
    if not isinstance(message_type, str) or not message_type:
        raise FrameValidationError("missing type", code="MISSING_FIELD")
    if message_type == "SAMPLE":
        return parse_sample(message)
    if message_type == "HELLO":
        return parse_hello(message)
    if message_type == "STATUS":
        return parse_status(message)
    if message_type == "ERROR":
        return parse_error(message)
    if message_type == "PONG":
        return parse_pong(message)
    raise FrameValidationError("unknown message type: {}".format(message_type), code="UNKNOWN_MESSAGE")


def encode_command(cmd: str, value: Any = None, request_id: Optional[str] = None, target_id: Optional[int] = None) -> bytes:
    payload: Dict[str, Any] = {"cmd": cmd}
    if value is not None:
        payload["value"] = value
    if target_id is not None:
        payload["id"] = target_id
    if request_id is not None:
        payload["request_id"] = request_id
    return (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
