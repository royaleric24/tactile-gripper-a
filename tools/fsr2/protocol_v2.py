"""Profile-aware reference parser for the V2 tactile-gripper JSONL stream.

This module is the hardware group's reading of docs/PROTOCOL_V2_PROPOSAL.md and
docs/WIRING_FREEZE_V2.md.  It intentionally accepts both sensor profiles and is
stricter than the historical 12-channel parser in tools/tactile_acq/protocol.py:

* the channel count must match the declared sensor_profile,
* an invalid channel must carry ``null`` raw/value/sample time and the NO_DATA
  flag -- a zero is a *measurement*, never a placeholder,
* ``valid[i]`` must be the exact inverse of the NO_DATA flag,
* ``reference_mode`` must be AVDD_AVSS for FSR profiles (the 2.048 V internal
  reference clips a 3.3 V divider),
* channel ids must be contiguous from 0.

The data in tests/fixtures/fsr2 was emitted by this firmware compiled against
the host simulation.  It is fixture data for parser tests, NOT hardware
evidence, and every file says so.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

PROTOCOL_VERSION = 1
MAX_LINE_BYTES = 8192
ADC_COUNT = 4
ADC_MIN = -8388608
ADC_MAX = 8388607

FLAG_SAT_HIGH = 0x01
FLAG_SAT_LOW = 0x02
FLAG_NEGATIVE_SINGLE_ENDED = 0x04
FLAG_NEAR_RAIL = 0x08
FLAG_STUCK_EXTREME = 0x10
FLAG_NO_DATA = 0x20

CHANNEL_FLAGS = {
    FLAG_SAT_HIGH: "SAT_HIGH",
    FLAG_SAT_LOW: "SAT_LOW",
    FLAG_NEGATIVE_SINGLE_ENDED: "NEGATIVE_SINGLE_ENDED",
    FLAG_NEAR_RAIL: "NEAR_RAIL",
    FLAG_STUCK_EXTREME: "STUCK_EXTREME",
    FLAG_NO_DATA: "NO_DATA",
}

ADC_STATES = ("OK", "CONFIG_ERROR", "NO_RESPONSE", "RECOVERING", "FAILED")
ADC_STATE_CODES = {name: index for index, name in enumerate(ADC_STATES)}
SENSOR_KINDS = ("ELECTRODE", "FSR")
ELECTRODE_ROLES = ("ROW", "COLUMN", "NONE")
ELECTRODE_NAMES = tuple(
    ["R%d" % index for index in range(1, 7)] + ["C%d" % index for index in range(1, 7)]
)
REFERENCE_MODES = ("AVDD_AVSS",)
REFERENCE_MODES_ALLOWED = ("AVDD_AVSS", "INTERNAL_2V048")

# Electrode-only and electrode+FSR variants are both valid for the same profile:
# the declared channel_count selects 12 or 14 and is cross-checked below.
PROFILE_CHANNEL_COUNTS = {"FSR_ONLY": 2, "MATRIX_ELECTRODES_12": 12}
PROFILE_OPTIONAL_FSR_COUNTS = {"MATRIX_ELECTRODES_12": (12, 14)}
HISTORICAL_PROFILES = ("HYBRID_6X6_FSR2",)
PROFILE_MATRIX = {"FSR_ONLY": None, "MATRIX_ELECTRODES_12": None}


class ProtocolError(Exception):
    """A line is not a well-formed protocol message."""


class FrameValidationError(ProtocolError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _unique_pairs(pairs: Sequence[Tuple[str, Any]]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FrameValidationError("DUPLICATE_KEY", "duplicate JSON key %r" % (key,))
        result[key] = value
    return result


def decode_line(raw: Any, max_bytes: int = MAX_LINE_BYTES) -> Dict[str, Any]:
    if isinstance(raw, bytes):
        data = raw
    elif isinstance(raw, str):
        data = raw.encode("utf-8")
    else:
        raise ProtocolError("line must be bytes or str")
    if len(data) > max_bytes:
        raise FrameValidationError("LINE_TOO_LONG", "line exceeds %d bytes" % (max_bytes,))
    text = data.decode("utf-8").strip()
    if not text:
        raise FrameValidationError("EMPTY_LINE", "empty line")
    if "\n" in text:
        raise FrameValidationError("MULTIPLE_LINES", "line contains more than one frame")
    try:
        payload = json.loads(text, object_pairs_hook=_unique_pairs)
    except FrameValidationError:
        raise
    except ValueError as exc:
        raise FrameValidationError("INVALID_JSON", "invalid JSON: %s" % (exc,)) from exc
    if not isinstance(payload, dict):
        raise FrameValidationError("NOT_AN_OBJECT", "frame root must be a JSON object")
    return payload


def _require(message: Dict[str, Any], key: str) -> Any:
    if key not in message:
        raise FrameValidationError("MISSING_FIELD", "missing field %r" % (key,))
    return message[key]


def _require_int(message: Dict[str, Any], key: str, minimum: int, maximum: int) -> int:
    value = _require(message, key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise FrameValidationError("INVALID_TYPE", "%s must be an integer" % (key,))
    if value < minimum or value > maximum:
        raise FrameValidationError("OUT_OF_RANGE", "%s=%d out of range" % (key, value))
    return value


def _require_bool(message: Dict[str, Any], key: str) -> bool:
    value = _require(message, key)
    if not isinstance(value, bool):
        raise FrameValidationError("INVALID_TYPE", "%s must be a boolean" % (key,))
    return value


def _require_str(message: Dict[str, Any], key: str, max_length: int = 64) -> str:
    value = _require(message, key)
    if not isinstance(value, str) or not value:
        raise FrameValidationError("INVALID_TYPE", "%s must be a non-empty string" % (key,))
    if len(value) > max_length:
        raise FrameValidationError("OUT_OF_RANGE", "%s is too long" % (key,))
    return value


def _require_list(message: Dict[str, Any], key: str, length: Optional[int]) -> List[Any]:
    value = _require(message, key)
    if not isinstance(value, list):
        raise FrameValidationError("INVALID_TYPE", "%s must be a list" % (key,))
    if length is not None and len(value) != length:
        raise FrameValidationError(
            "CHANNEL_COUNT_MISMATCH",
            "%s has %d entries, expected %d" % (key, len(value), length),
        )
    return value


def profile_of(message: Dict[str, Any]) -> str:
    profile = message.get("sensor_profile")
    if profile is None:
        raise FrameValidationError("MISSING_PROFILE", "sensor_profile is required for V2 frames")
    if profile in HISTORICAL_PROFILES:
        raise FrameValidationError(
            "PROFILE_HISTORICAL",
            "%s is withdrawn: the cloth has twelve independent electrodes, not a scanned 6x6 matrix"
            % (profile,),
        )
    if not isinstance(profile, str) or profile not in PROFILE_CHANNEL_COUNTS:
        raise FrameValidationError("UNKNOWN_PROFILE", "unknown sensor_profile %r" % (profile,))
    return profile


def expected_channel_count(profile: str, declared: Optional[int] = None) -> int:
    if profile in HISTORICAL_PROFILES:
        raise FrameValidationError("PROFILE_HISTORICAL", "%s is withdrawn" % (profile,))
    try:
        base = PROFILE_CHANNEL_COUNTS[profile]
    except KeyError as exc:
        raise FrameValidationError("UNKNOWN_PROFILE", "unknown sensor_profile %r" % (profile,)) from exc
    allowed = PROFILE_OPTIONAL_FSR_COUNTS.get(profile)
    if allowed is None:
        if declared is not None and declared != base:
            raise FrameValidationError(
                "CHANNEL_COUNT_MISMATCH", "%s has %d channels, frame declares %d" % (profile, base, declared)
            )
        return base
    if declared is None:
        return base
    if declared not in allowed:
        raise FrameValidationError(
            "CHANNEL_COUNT_MISMATCH",
            "%s allows %s channels, frame declares %d" % (profile, allowed, declared),
        )
    return declared


def channel_count_of(message: Dict[str, Any], profile: str) -> int:
    declared = _require_int(message, "channel_count", 1, 64)
    return expected_channel_count(profile, declared)


@dataclass(frozen=True)
class ChannelLayout:
    channel_id: int
    kind: str
    role: str
    position: int
    matrix_row: Optional[int] = None
    matrix_col: Optional[int] = None


def expected_layout(profile: str, channel_count: int) -> List[ChannelLayout]:
    """Return kind/role/position for each channel; the ADC map is checked separately."""
    if profile == "FSR_ONLY":
        layout = [ChannelLayout(0, "FSR", "NONE", 0), ChannelLayout(1, "FSR", "NONE", 0)]
    elif profile == "MATRIX_ELECTRODES_12":
        layout = []
        for channel in range(12):
            role = "ROW" if channel < 6 else "COLUMN"
            position = channel % 6 + 1
            layout.append(ChannelLayout(channel, "ELECTRODE", role, position))
        if channel_count == 14:
            layout.append(ChannelLayout(12, "FSR", "NONE", 0))
            layout.append(ChannelLayout(13, "FSR", "NONE", 0))
    else:
        raise FrameValidationError("UNKNOWN_PROFILE", "unknown sensor_profile %r" % (profile,))
    if len(layout) != channel_count:
        raise FrameValidationError("CHANNEL_COUNT_MISMATCH", "layout size does not match channel_count")
    return layout


def parse_adc_status(message: Dict[str, Any], expected_ids: int = ADC_COUNT) -> List[Dict[str, Any]]:
    entries = _require_list(message, "adc_status", expected_ids)
    parsed: List[Dict[str, Any]] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise FrameValidationError("INVALID_TYPE", "adc_status entries must be objects")
        device_id = _require_int(entry, "id", 1, expected_ids)
        if device_id != index + 1:
            raise FrameValidationError("ADC_STATUS_ORDER", "adc_status ids must be 1..%d in order" % (expected_ids,))
        state = _require_str(entry, "state", 32)
        if state not in ADC_STATES:
            raise FrameValidationError("UNKNOWN_ADC_STATE", "unknown adc state %r" % (state,))
        if _require_int(entry, "code", 0, len(ADC_STATES) - 1) != ADC_STATE_CODES[state]:
            raise FrameValidationError("ADC_STATE_CODE", "ADC state and code disagree")
        _require_int(entry, "consecutive_errors", 0, 65535)
        _require_int(entry, "total_errors", 0, 65535)
        _require_int(entry, "recovered", 0, 65535)
        last_error = entry.get("last_error")
        if last_error is not None and (not isinstance(last_error, str) or not last_error):
            raise FrameValidationError("INVALID_TYPE", "last_error must be a string or null")
        parsed.append(
            {
                "id": device_id,
                "state": state,
                "code": ADC_STATE_CODES[state],
                "consecutive_errors": entry["consecutive_errors"],
                "total_errors": entry["total_errors"],
                "recovered": entry["recovered"],
                "last_error": last_error,
            }
        )
    return parsed


@dataclass(frozen=True)
class SampleFrame:
    profile: str
    device_id: str
    boot_id: str
    firmware_version: str
    frame_seq: int
    timestamp_us: int
    mcu_time_us: int
    frame_period_us: Optional[int]
    channel_count: int
    channel_ids: List[int]
    raw_adc: List[Optional[int]]
    channels: List[Optional[int]]
    valid: List[bool]
    valid_mask: List[bool]
    sample_timestamp_us: List[Optional[int]]
    channel_flags: List[int]
    reference_mode: str
    effective_frame_rate_hz: float
    adc_status: List[Dict[str, Any]]

    @property
    def electrode_values(self) -> Dict[str, Optional[int]]:
        if self.profile != "MATRIX_ELECTRODES_12":
            return {}
        return {name: self.channels[index] for index, name in enumerate(ELECTRODE_NAMES)}

    @property
    def fsr_values(self) -> Dict[str, Optional[int]]:
        if self.profile == "FSR_ONLY":
            return {"FSR_A": self.channels[0], "FSR_B": self.channels[1]}
        if self.profile == "MATRIX_ELECTRODES_12" and self.channel_count == 14:
            return {"FSR_A": self.channels[12], "FSR_B": self.channels[13]}
        return {}

    def flags_for(self, channel_id: int) -> List[str]:
        value = self.channel_flags[channel_id]
        return [name for bit, name in CHANNEL_FLAGS.items() if value & bit]


def parse_sample(message: Dict[str, Any]) -> SampleFrame:
    if message.get("type") != "SAMPLE":
        raise FrameValidationError("WRONG_TYPE", "expected SAMPLE")
    profile = profile_of(message)
    count = channel_count_of(message, profile)
    _require_int(message, "protocol_version", PROTOCOL_VERSION, PROTOCOL_VERSION)
    device_id = _require_str(message, "device_id", 64)
    boot_id = _require_str(message, "boot_id", 64)
    firmware_version = _require_str(message, "firmware_version", 64)
    frame_seq = _require_int(message, "frame_seq", 0, 0xFFFFFFFF)
    timestamp_us = _require_int(message, "timestamp_us", 0, 0xFFFFFFFF)
    mcu_time_us = _require_int(message, "mcu_time_us", 0, 0xFFFFFFFF)
    if timestamp_us != mcu_time_us:
        raise FrameValidationError("TIMESTAMP_CONFLICT", "timestamp_us and mcu_time_us disagree")
    frame_period = message.get("frame_period_us")
    if frame_period is not None:
        if not isinstance(frame_period, int) or isinstance(frame_period, bool) or frame_period <= 0:
            raise FrameValidationError("INVALID_TYPE", "frame_period_us must be a positive integer or null")

    channel_ids = _require_list(message, "channel_ids", count)
    if any(type(channel_id) is not int for channel_id in channel_ids) or channel_ids != list(range(count)):
        raise FrameValidationError("CHANNEL_IDS", "channel_ids must be 0..%d in order" % (count - 1,))

    raw_adc = _require_list(message, "raw_adc", count)
    channels = _require_list(message, "channels", count)
    valid = _require_list(message, "valid", count)
    valid_mask = _require_list(message, "valid_mask", count)
    sample_times = _require_list(message, "sample_timestamp_us", count)
    flags = _require_list(message, "channel_flags", count)

    for index in range(count):
        if not isinstance(valid[index], bool):
            raise FrameValidationError("INVALID_TYPE", "valid[%d] must be a boolean" % (index,))
        if not isinstance(valid_mask[index], bool):
            raise FrameValidationError("INVALID_TYPE", "valid_mask[%d] must be a boolean" % (index,))
        if valid[index] != valid_mask[index]:
            raise FrameValidationError(
                "VALID_MASK_MISMATCH", "valid[%d] and valid_mask[%d] disagree" % (index, index)
            )
        if not isinstance(flags[index], int) or isinstance(flags[index], bool):
            raise FrameValidationError("INVALID_TYPE", "channel_flags[%d] must be an integer" % (index,))
        if flags[index] < 0 or flags[index] > 0x3F:
            raise FrameValidationError("OUT_OF_RANGE", "channel_flags[%d] out of range" % (index,))
        no_data = bool(flags[index] & FLAG_NO_DATA)
        if valid[index] == no_data:
            raise FrameValidationError(
                "VALID_FLAG_CONTRADICTION",
                "channel %d: valid=%s but NO_DATA=%s" % (index, valid[index], no_data),
            )
        value = raw_adc[index]
        mirror = channels[index]
        sample_time = sample_times[index]
        if valid[index]:
            for name, candidate in (("raw_adc", value), ("channels", mirror)):
                if not isinstance(candidate, int) or isinstance(candidate, bool):
                    raise FrameValidationError(
                        "INVALID_TYPE", "%s[%d] must be an integer when valid" % (name, index)
                    )
                if candidate < ADC_MIN or candidate > ADC_MAX:
                    raise FrameValidationError("OUT_OF_RANGE", "%s[%d] outside 24-bit range" % (name, index))
            if value != mirror:
                raise FrameValidationError(
                    "CHANNELS_MISMATCH", "channels[%d] must mirror raw_adc[%d]" % (index, index)
                )
            if type(sample_time) is not int or not 0 <= sample_time <= 0xFFFFFFFF:
                raise FrameValidationError(
                    "INVALID_TYPE", "sample_timestamp_us[%d] must be uint32 when valid" % (index,)
                )
        else:
            if value is not None or mirror is not None:
                raise FrameValidationError(
                    "ZERO_FOR_INVALID", "channel %d is invalid but carries a value" % (index,)
                )
            if sample_time is not None:
                raise FrameValidationError(
                    "TIMESTAMP_FOR_INVALID", "channel %d is invalid but carries a sample time" % (index,)
                )
            if flags[index] & ~FLAG_NO_DATA:
                raise FrameValidationError(
                    "FLAG_FOR_INVALID", "channel %d is invalid but carries extra flags" % (index,)
                )

    reference_mode = _require_str(message, "reference_mode", 32)
    if reference_mode not in REFERENCE_MODES:
        raise FrameValidationError(
            "REFERENCE_MODE",
            "V2 FSR profiles must use AVDD_AVSS, got %r" % (reference_mode,),
        )
    rate = _require(message, "effective_frame_rate_hz")
    if type(rate) not in (int, float) or not 0 <= rate <= 1_000_000 or not math.isfinite(rate):
        raise FrameValidationError("INVALID_TYPE", "effective_frame_rate_hz must be a number")
    adc_status = parse_adc_status(message)

    return SampleFrame(
        profile=profile,
        device_id=device_id,
        boot_id=boot_id,
        firmware_version=firmware_version,
        frame_seq=frame_seq,
        timestamp_us=timestamp_us,
        mcu_time_us=mcu_time_us,
        frame_period_us=frame_period,
        channel_count=count,
        channel_ids=list(channel_ids),
        raw_adc=list(raw_adc),
        channels=list(channels),
        valid=list(valid),
        valid_mask=list(valid_mask),
        sample_timestamp_us=list(sample_times),
        channel_flags=list(flags),
        reference_mode=reference_mode,
        effective_frame_rate_hz=float(rate),
        adc_status=adc_status,
    )


def parse_channel_config(message: Dict[str, Any], profile: str, count: int) -> List[ChannelLayout]:
    config = _require(message, "channel_config")
    if not isinstance(config, dict):
        raise FrameValidationError("INVALID_TYPE", "channel_config must be an object")
    if "sensor_profile" in config and config["sensor_profile"] != profile:
        raise FrameValidationError("PROFILE_CONFLICT", "top-level and channel_config sensor_profile disagree")
    if config.get("status") not in ("IMPLEMENTED", "IMPLEMENTED_UNVERIFIED"):
        raise FrameValidationError(
            "CHANNEL_CONFIG_STATUS", "unexpected channel_config.status %r" % (config.get("status"),)
        )
    # No V2 profile is a scanned matrix; these fields stay null on purpose.
    if config.get("matrix_rows") is not None or config.get("matrix_cols") is not None:
        raise FrameValidationError("MATRIX_SHAPE", "matrix_rows/matrix_cols must be null for %s" % (profile,))
    if config.get("adc_count") != ADC_COUNT:
        raise FrameValidationError("ADC_COUNT", "adc_count must be %d" % (ADC_COUNT,))
    entries = _require_list(config, "channels", count)
    layout = expected_layout(profile, count)
    mapped_pairs = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise FrameValidationError("INVALID_TYPE", "channel_config.channels entries must be objects")
        want = layout[index]
        if type(entry.get("channel_id")) is not int or entry["channel_id"] != want.channel_id:
            raise FrameValidationError("CHANNEL_IDS", "channel_config.channels out of order at %d" % (index,))
        if entry.get("sensor_kind") != want.kind:
            raise FrameValidationError(
                "SENSOR_KIND", "channel %d kind %r, expected %r" % (index, entry.get("sensor_kind"), want.kind)
            )
        if entry.get("matrix_row") is not None or entry.get("matrix_col") is not None:
            raise FrameValidationError("MATRIX_CELL", "channel %d is not a matrix cell" % (index,))
        if want.kind == "ELECTRODE" and (
            entry.get("electrode_role") != want.role or entry.get("electrode_position") != want.position
        ):
            raise FrameValidationError("ELECTRODE_LAYOUT", "channel %d role or position mismatch" % index)
        mapped_fields = (entry.get("ads1220_id"), entry.get("adc_input"), entry.get("mux_channel"))
        if all(field is None for field in mapped_fields):
            if want.kind != "ELECTRODE":
                raise FrameValidationError("ADC_INDEX", "channel %d must carry an ADC/AIN" % (index,))
            continue
        if any(field is None for field in mapped_fields):
            raise FrameValidationError("ADC_INDEX", "channel %d has a partial ADC/AIN mapping" % (index,))
        for name, pin in (("ads1220_id", entry.get("ads1220_id")), ("adc_input", entry.get("adc_input"))):
            if not isinstance(pin, int) or isinstance(pin, bool):
                raise FrameValidationError("INVALID_TYPE", "channel %d %s must be an integer" % (index, name))
        ads1220_id = entry["ads1220_id"]
        adc_input = entry["adc_input"]
        if want.kind == "FSR":
            if ads1220_id != ADC_COUNT:
                raise FrameValidationError("FSR_ADC", "FSR channel %d must live on ADC%d" % (index, ADC_COUNT))
        elif ads1220_id >= ADC_COUNT:
            raise FrameValidationError(
                "ADC_INDEX", "electrode %d must not use ADC%d (reserved for the FSR dividers)" % (index, ADC_COUNT)
            )
        if not 1 <= ads1220_id <= ADC_COUNT or not 0 <= adc_input <= 3:
            raise FrameValidationError("ADC_INPUT", "channel %d ADC/AIN out of range" % (index,))
        if entry.get("mux_channel") != 8 + adc_input:
            raise FrameValidationError("MUX_CHANNEL", "channel %d mux_channel must be 8 + AIN" % (index,))
        if (ads1220_id, adc_input) in mapped_pairs:
            raise FrameValidationError("ADC_INDEX", "duplicate ADC/AIN mapping")
        mapped_pairs.add((ads1220_id, adc_input))
    return layout


def parse_electrode_layout(message: Dict[str, Any], count: int) -> List[Dict[str, Any]]:
    layout = _require(message, "electrode_layout")
    if not isinstance(layout, dict):
        raise FrameValidationError("INVALID_TYPE", "electrode_layout must be an object")
    if layout.get("count") != 12 or layout.get("rows") != 6 or layout.get("columns") != 6:
        raise FrameValidationError("ELECTRODE_SHAPE", "electrode_layout must describe a 6x6 electrode set")
    if layout.get("row_bias") != "PULLDOWN_10K_TO_GND":
        raise FrameValidationError("ELECTRODE_BIAS", "rows are pulled to GND through 10 kOhm")
    if layout.get("column_bias") != "PULLUP_1K_TO_3V3":
        raise FrameValidationError("ELECTRODE_BIAS", "columns are pulled to 3.3 V through 1 kOhm")
    # SIM_SYNTHETIC_MAPPING only appears in host-test fixtures produced by
    # tools/fsr2_sim/electrode_test_profile.h; production builds never emit it.
    status = layout.get("mapping_status")
    if status not in ("PENDING_REAL_WIRING", "TABLE_PROVIDED", "SIM_SYNTHETIC_MAPPING"):
        raise FrameValidationError("MAPPING_STATUS", "unexpected mapping_status %r" % (status,))
    if layout.get("validated") is not False:
        raise FrameValidationError(
            "ELECTRODE_VALIDATED", "electrode_layout.validated must stay false until the real map is recorded"
        )
    if layout.get("gpio_excitation") is not False:
        raise FrameValidationError("ELECTRODE_LAYOUT", "GPIO excitation is prohibited")
    entries = _require_list(layout, "channels", 12)
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise FrameValidationError("INVALID_TYPE", "electrode_layout.channels entries must be objects")
        if entry.get("channel_id") != index:
            raise FrameValidationError("CHANNEL_IDS", "electrode_layout.channels out of order at %d" % (index,))
        expected_role = "ROW" if index < 6 else "COLUMN"
        if entry.get("role") != expected_role:
            raise FrameValidationError("ELECTRODE_ROLE", "electrode_layout channel %d role mismatch" % (index,))
        if entry.get("position") != index % 6 + 1:
            raise FrameValidationError("ELECTRODE_POSITION", "electrode_layout channel %d position mismatch" % (index,))
        fields = (entry.get("adc_id"), entry.get("adc_input"), entry.get("mux_channel"))
        configured = message["channel_config"]["channels"][index]
        if fields != tuple(configured.get(key) for key in ("ads1220_id", "adc_input", "mux_channel")):
            raise FrameValidationError("MAPPING_STATUS", "electrode layout and channel_config disagree")
        if status == "PENDING_REAL_WIRING":
            if any(field is not None for field in fields):
                raise FrameValidationError(
                    "MAPPING_STATUS",
                    "channel %d invents an ADC/AIN while the real wiring is still PENDING" % (index,),
                )
        else:
            if all(field is None for field in fields):
                raise FrameValidationError(
                    "MAPPING_STATUS", "channel %d has no ADC/AIN although the table claims to be provided" % (index,)
                )
    return entries


def parse_hello(message: Dict[str, Any]) -> Dict[str, Any]:
    if message.get("type") != "HELLO":
        raise FrameValidationError("WRONG_TYPE", "expected HELLO")
    profile = profile_of(message)
    count = channel_count_of(message, profile)
    _require_int(message, "protocol_version", PROTOCOL_VERSION, PROTOCOL_VERSION)
    _require_str(message, "device_id", 64)
    _require_str(message, "boot_id", 64)
    _require_str(message, "firmware_version", 64)
    if message.get("spi_mode") != "MODE1_BITBANG":
        raise FrameValidationError("SPI_MODE", "V2 firmware uses MODE1_BITBANG")
    _require_int(message, "data_rate_sps", 20, 1000)
    _require_int(message, "conversion_wait_us", 900, 200000)
    if message.get("reference_mode") not in REFERENCE_MODES:
        raise FrameValidationError("REFERENCE_MODE", "V2 FSR profiles must run on AVDD_AVSS")
    allowed = _require_list(message, "reference_modes_allowed", None)
    if "AVDD_AVSS" not in allowed:
        raise FrameValidationError("REFERENCE_MODES", "AVDD_AVSS must be an allowed reference")
    pins = _require(message, "pins")
    if not isinstance(pins, dict):
        raise FrameValidationError("INVALID_TYPE", "pins must be an object")
    if pins.get("sclk") != 18 or pins.get("mosi") != 23:
        raise FrameValidationError("SPI_PINS", "V2 shares SCLK=18 and MOSI=23")
    for name in ("miso", "cs"):
        values = _require_list(pins, name, ADC_COUNT)
        for pin in values:
            if not isinstance(pin, int) or isinstance(pin, bool) or pin < 0 or pin > 39:
                raise FrameValidationError("PIN_RANGE", "%s contains an invalid pin" % (name,))
    parse_channel_config(message, profile, count)
    has_fsr = profile == "FSR_ONLY" or count == 14
    if has_fsr:
        fsr_layout = _require(message, "fsr_layout")
        if not isinstance(fsr_layout, dict):
            raise FrameValidationError("INVALID_TYPE", "fsr_layout must be an object")
        if fsr_layout.get("adc_id") != ADC_COUNT:
            raise FrameValidationError("FSR_ADC", "FSR channels must live on ADC4")
        if fsr_layout.get("independent_pulldowns") is not True:
            raise FrameValidationError(
                "FSR_PULLDOWNS", "each FSR node needs its own 10 kOhm pulldown to GND"
            )
        if fsr_layout.get("validated") is not False:
            raise FrameValidationError(
                "FSR_VALIDATED",
                "fsr_layout.validated must stay false until a real bench session is recorded",
            )
        fsr_channels = _require_list(fsr_layout, "channels", 2)
        for index, entry in enumerate(fsr_channels):
            if not isinstance(entry, dict):
                raise FrameValidationError("INVALID_TYPE", "fsr_layout.channels entries must be objects")
            for key in ("channel_id", "name", "adc_input", "mux_channel"):
                _require(entry, key)
            channel_id = count - 2 + index
            configured = message["channel_config"]["channels"][channel_id]
            if (entry["channel_id"] != channel_id or entry["name"] != ("FSR_A", "FSR_B")[index]
                    or any(entry[key] != configured.get(key) for key in ("adc_input", "mux_channel"))):
                raise FrameValidationError("FSR_LAYOUT", "FSR layout and channel_config disagree")
    if profile == "MATRIX_ELECTRODES_12":
        parse_electrode_layout(message, count)
    parse_adc_status(message)
    return message


def parse_status(message: Dict[str, Any]) -> Dict[str, Any]:
    if message.get("type") != "STATUS":
        raise FrameValidationError("WRONG_TYPE", "expected STATUS")
    profile = profile_of(message)
    count = channel_count_of(message, profile)
    _require_int(message, "protocol_version", PROTOCOL_VERSION, PROTOCOL_VERSION)
    _require_str(message, "device_id", 64)
    _require_str(message, "boot_id", 64)
    if message.get("sensor_state") not in ("STREAMING", "STOPPED"):
        raise FrameValidationError("SENSOR_STATE", "sensor_state must be STREAMING or STOPPED")
    if _require_bool(message, "streaming") != (message["sensor_state"] == "STREAMING"):
        raise FrameValidationError("SENSOR_STATE", "streaming flag and sensor_state disagree")
    _require_int(message, "last_frame_seq", 0, 0xFFFFFFFF)
    _require_int(message, "uptime_ms", 0, 0xFFFFFFFF)
    rate = _require(message, "effective_frame_rate_hz")
    if type(rate) not in (int, float) or not 0 <= rate <= 1_000_000 or not math.isfinite(rate):
        raise FrameValidationError("INVALID_TYPE", "effective_frame_rate_hz must be a number")
    if message.get("reference_mode") not in REFERENCE_MODES:
        raise FrameValidationError("REFERENCE_MODE", "STATUS must report AVDD_AVSS")
    parse_channel_config(message, profile, count)
    if profile == "MATRIX_ELECTRODES_12":
        parse_electrode_layout(message, count)
    parse_adc_status(message)
    request_id = message.get("request_id")
    if request_id is not None and (not isinstance(request_id, str) or len(request_id) > 64):
        raise FrameValidationError("INVALID_TYPE", "request_id must be a short string or null")
    return message


def parse_error(message: Dict[str, Any]) -> Dict[str, Any]:
    if message.get("type") != "ERROR":
        raise FrameValidationError("WRONG_TYPE", "expected ERROR")
    _require_int(message, "protocol_version", PROTOCOL_VERSION, PROTOCOL_VERSION)
    code = _require_str(message, "code", 64)
    if not code.replace("_", "").isalnum():
        raise FrameValidationError("ERROR_CODE", "error codes are upper-case identifiers")
    _require_str(message, "message", 512)
    if message.get("fatal") is not False:
        raise FrameValidationError("FATAL_FLAG", "V2 firmware never marks errors fatal")
    return message


def parse_pong(message: Dict[str, Any]) -> Dict[str, Any]:
    if message.get("type") != "PONG":
        raise FrameValidationError("WRONG_TYPE", "expected PONG")
    profile_of(message)
    _require_int(message, "protocol_version", PROTOCOL_VERSION, PROTOCOL_VERSION)
    _require_str(message, "device_id", 64)
    _require_str(message, "boot_id", 64)
    return message


PARSERS = {
    "SAMPLE": parse_sample,
    "HELLO": parse_hello,
    "STATUS": parse_status,
    "ERROR": parse_error,
    "PONG": parse_pong,
}


def parse_message(raw: Any) -> Any:
    message = decode_line(raw)
    frame_type = message.get("type")
    if frame_type not in PARSERS:
        raise FrameValidationError("UNKNOWN_TYPE", "unknown frame type %r" % (frame_type,))
    return PARSERS[frame_type](message)


def encode_command(cmd: str, value: Optional[str] = None, request_id: Optional[str] = None) -> bytes:
    payload: Dict[str, Any] = {"cmd": cmd}
    if value is not None:
        payload["value"] = value
    if request_id is not None:
        payload["request_id"] = request_id
    return (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")


def flag_names(value: int) -> List[str]:
    return [name for bit, name in CHANNEL_FLAGS.items() if value & bit]
