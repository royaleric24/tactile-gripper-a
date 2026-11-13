"""Python data models for the S1 protocol and S2-A application.

The models are deliberately small dataclasses with explicit validation.  They
do not depend on NiceGUI or pyserial, so they can be tested offline.
"""

from __future__ import annotations

import math
import time
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, Mapping

from .constants import FIRMWARE_COMMAND_MAP, PROTOCOL_VERSION, SOFTWARE_VERSION, TRIAL_SCHEMA_VERSION
from .errors import FrameValidationError
from .sources import DataSource, parse_source


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_int(value: Any) -> bool:
    return type(value) is int  # bool is deliberately excluded


def _is_number(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _require(mapping: Mapping, key: str) -> Any:
    if key not in mapping:
        raise FrameValidationError(f"missing field: {key}", code="MISSING_FIELD")
    return mapping[key]


def _int_field(mapping: Mapping, key: str, *, minimum: int = 0, code: str = "INVALID_VALUE") -> int:
    value = _require(mapping, key)
    if not _is_int(value) or value < minimum:
        raise FrameValidationError(f"{key} must be an integer >= {minimum}", code=code)
    return value


def _optional_int(mapping: Mapping, key: str, *, minimum: int = 0) -> int | None:
    value = mapping.get(key)
    if value is None:
        return None
    if not _is_int(value) or value < minimum:
        raise FrameValidationError(f"{key} must be null or an integer >= {minimum}", code="INVALID_VALUE")
    return value


def _string_field(mapping: Mapping, key: str, *, allow_empty: bool = False) -> str:
    value = _require(mapping, key)
    if not isinstance(value, str) or (not allow_empty and not value):
        raise FrameValidationError(f"{key} must be a non-empty string", code="INVALID_VALUE")
    return value


@dataclass(frozen=True)
class ChannelConfig:
    """Description of one *scan channel*.

    A scan channel is not necessarily one sensing cell.  ``adc_input``,
    ``mux_channel`` and the matrix position are separate facts and may all be
    UNKNOWN (``None``).  They must be supplied by configuration or HELLO, never
    inferred from a hard-coded 12/16/36 layout.
    """

    channel_id: int
    adc_input: int | None = None
    ads1220_id: int | None = None
    mux_channel: int | None = None
    matrix_row: int | None = None
    matrix_col: int | None = None
    enabled: bool = True
    unit: str = "ADC_COUNTS"
    extra: dict[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        if not _is_int(self.channel_id) or self.channel_id < 0:
            raise ValueError("channel_id must be an integer >= 0")
        for name in ("adc_input", "ads1220_id", "mux_channel", "matrix_row", "matrix_col"):
            value = getattr(self, name)
            if value is not None and (not _is_int(value) or value < 0):
                raise ValueError(f"{name} must be null or an integer >= 0")
        if (self.matrix_row is None) != (self.matrix_col is None):
            raise ValueError("matrix_row and matrix_col must be provided together")
        if type(self.enabled) is not bool:
            raise ValueError("enabled must be boolean")
        if self.unit not in ("ADC_COUNTS", "UNKNOWN"):
            raise ValueError("unit must be ADC_COUNTS or UNKNOWN (no unverified conversion)")

    @property
    def has_matrix_position(self) -> bool:
        return self.matrix_row is not None and self.matrix_col is not None

    @classmethod
    def from_dict(cls, value: Mapping) -> "ChannelConfig":
        if not isinstance(value, Mapping):
            raise ValueError("channel config entry must be an object")
        extra = {
            key: item
            for key, item in value.items()
            if key
            not in {
                "channel_id",
                "adc_input",
                "ads1220_id",
                "mux_channel",
                "matrix_row",
                "matrix_col",
                "enabled",
                "unit",
            }
        }
        return cls(
            channel_id=_int_field(value, "channel_id"),
            adc_input=_optional_int(value, "adc_input"),
            ads1220_id=_optional_int(value, "ads1220_id"),
            mux_channel=_optional_int(value, "mux_channel"),
            matrix_row=_optional_int(value, "matrix_row"),
            matrix_col=_optional_int(value, "matrix_col"),
            enabled=value.get("enabled", True),
            unit=value.get("unit", "ADC_COUNTS"),
            extra=extra,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel_id": self.channel_id,
            "adc_input": self.adc_input,
            "ads1220_id": self.ads1220_id,
            "mux_channel": self.mux_channel,
            "matrix_row": self.matrix_row,
            "matrix_col": self.matrix_col,
            "enabled": self.enabled,
            "unit": self.unit,
            **self.extra,
        }


@dataclass(frozen=True)
class ChannelConfiguration:
    """Dynamic channel/matrix description received from HELLO or local config."""

    channels: tuple[ChannelConfig, ...]
    matrix_rows: int | None = None
    matrix_cols: int | None = None
    adc_count: int | None = None
    scan_mode: str = "UNKNOWN"
    status: str = "PROPOSED"

    def __post_init__(self) -> None:
        if not self.channels:
            raise ValueError("at least one channel is required")
        ids = [channel.channel_id for channel in self.channels]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate channel_id")
        if (self.matrix_rows is None) != (self.matrix_cols is None):
            raise ValueError("matrix_rows and matrix_cols must be provided together")
        if self.matrix_rows is not None:
            if not _is_int(self.matrix_rows) or self.matrix_rows <= 0:
                raise ValueError("matrix_rows must be a positive integer")
            if not _is_int(self.matrix_cols) or self.matrix_cols <= 0:
                raise ValueError("matrix_cols must be a positive integer")
            positions = []
            for channel in self.channels:
                if channel.has_matrix_position:
                    assert channel.matrix_row is not None and channel.matrix_col is not None
                    if channel.matrix_row >= self.matrix_rows or channel.matrix_col >= self.matrix_cols:
                        raise ValueError("channel matrix position outside configured matrix")
                    positions.append((channel.matrix_row, channel.matrix_col))
            if len(positions) != len(set(positions)):
                raise ValueError("duplicate matrix position")
        if self.adc_count is not None and (not _is_int(self.adc_count) or self.adc_count <= 0):
            raise ValueError("adc_count must be a positive integer")
        if not isinstance(self.scan_mode, str):
            raise ValueError("scan_mode must be a string")
        if not isinstance(self.status, str):
            raise ValueError("status must be a string")

    @property
    def expected_channel_count(self) -> int:
        return len(self.channels)

    @property
    def channel_ids(self) -> tuple[int, ...]:
        return tuple(channel.channel_id for channel in self.channels)

    @property
    def matrix_cells(self) -> int | None:
        if self.matrix_rows is None or self.matrix_cols is None:
            return None
        return self.matrix_rows * self.matrix_cols

    @property
    def enabled_channels(self) -> tuple[ChannelConfig, ...]:
        return tuple(channel for channel in self.channels if channel.enabled)

    def channel(self, channel_id: int) -> ChannelConfig:
        for item in self.channels:
            if item.channel_id == channel_id:
                return item
        raise KeyError(channel_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "matrix_rows": self.matrix_rows,
            "matrix_cols": self.matrix_cols,
            "adc_count": self.adc_count,
            "scan_mode": self.scan_mode,
            "channels": [channel.to_dict() for channel in self.channels],
        }

    @classmethod
    def from_dict(cls, value: Mapping) -> "ChannelConfiguration":
        if not isinstance(value, Mapping):
            raise ValueError("channel_config must be an object")
        raw_channels = value.get("channels")
        if not isinstance(raw_channels, list):
            raise ValueError("channel_config.channels must be a list")
        return cls(
            channels=tuple(ChannelConfig.from_dict(item) for item in raw_channels),
            matrix_rows=value.get("matrix_rows"),
            matrix_cols=value.get("matrix_cols"),
            adc_count=value.get("adc_count"),
            scan_mode=value.get("scan_mode", "UNKNOWN"),
            status=value.get("status", "PROPOSED"),
        )


@dataclass(frozen=True)
class TactileFrame:
    """One validated sensor scan.

    ``channels`` holds raw ADC counts or the protocol's raw value.  It is never
    converted to resistance, force, opening or angle here.  Invalid channels
    remain ``None`` and are never treated as zero contact.
    """

    protocol_version: int
    device_id: str
    boot_id: str
    frame_seq: int
    mcu_time_us: int
    host_received_ns: int
    channels: tuple[float | None, ...]
    valid_mask: tuple[bool, ...]
    source: DataSource = DataSource.SIMULATION
    channel_ids: tuple[int, ...] | None = None
    matrix_rows: int | None = None
    matrix_cols: int | None = None
    contact_score: float | None = None
    host_received_utc: str = field(default_factory=utc_now_iso)
    frame_valid: bool = True
    raw: dict[str, Any] | None = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        source = parse_source(self.source)
        object.__setattr__(self, "source", source)

    @property
    def channel_count(self) -> int:
        return len(self.channels)

    @property
    def valid_channel_count(self) -> int:
        return sum(1 for flag in self.valid_mask if flag)

    @property
    def invalid_channels(self) -> tuple[int, ...]:
        return tuple(index for index, flag in enumerate(self.valid_mask) if not flag)

    def pairs(self) -> Iterable[tuple[int, float | None, bool]]:
        ids = self.channel_ids or tuple(range(self.channel_count))
        for channel_id, value, valid in zip(ids, self.channels, self.valid_mask):
            yield channel_id, value, valid

    def validate(self, config: ChannelConfiguration | None = None) -> "TactileFrame":
        if self.protocol_version != PROTOCOL_VERSION:
            raise FrameValidationError(
                f"unsupported protocol_version: {self.protocol_version}",
                code="PROTOCOL_VERSION",
            )
        for name in ("device_id", "boot_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise FrameValidationError(f"{name} must be a non-empty string")
        if not _is_int(self.frame_seq) or self.frame_seq < 0:
            raise FrameValidationError("frame_seq must be an integer >= 0", code="INVALID_VALUE")
        if not _is_int(self.mcu_time_us) or self.mcu_time_us < 0:
            raise FrameValidationError("mcu_time_us must be an integer >= 0", code="INVALID_VALUE")
        if not _is_int(self.host_received_ns) or self.host_received_ns < 0:
            raise FrameValidationError("host_received_ns must be an integer >= 0", code="INVALID_VALUE")
        if not isinstance(self.channels, tuple) or not isinstance(self.valid_mask, tuple):
            raise FrameValidationError("channels and valid_mask must be sequences", code="INVALID_MASK")
        if len(self.channels) != len(self.valid_mask):
            raise FrameValidationError(
                "channels and valid_mask length differ", code="LENGTH_MISMATCH"
            )
        if len(self.channels) == 0:
            raise FrameValidationError("empty channel array", code="LENGTH_MISMATCH")
        for index, flag in enumerate(self.valid_mask):
            if type(flag) is not bool:
                raise FrameValidationError(
                    f"valid_mask[{index}] must be boolean", code="INVALID_MASK"
                )
            value = self.channels[index]
            if value is None:
                if flag:
                    raise FrameValidationError(
                        f"valid channel {index} has no value", code="INVALID_VALUE"
                    )
                continue
            if not _is_number(value):
                raise FrameValidationError(
                    f"channel {index} is not a finite number", code="INVALID_VALUE"
                )
        if self.contact_score is not None and not _is_number(self.contact_score):
            raise FrameValidationError("contact_score must be null or finite", code="INVALID_VALUE")
        if (self.matrix_rows is None) != (self.matrix_cols is None):
            raise FrameValidationError("matrix dimensions must be provided together", code="INVALID_VALUE")
        if config is not None:
            if config.expected_channel_count != self.channel_count:
                raise FrameValidationError(
                    f"expected {config.expected_channel_count} channels, got {self.channel_count}",
                    code="LENGTH_MISMATCH",
                )
            if self.channel_ids is not None and tuple(self.channel_ids) != config.channel_ids:
                raise FrameValidationError("channel_ids do not match configuration", code="INVALID_CHANNEL")
            known = set(config.channel_ids)
            for channel_id in self.channel_ids or ():
                if channel_id not in known or not _is_int(channel_id):
                    raise FrameValidationError(f"unknown channel_id: {channel_id}", code="INVALID_CHANNEL")
        if not isinstance(self.frame_valid, bool):
            raise FrameValidationError("frame_valid must be boolean")
        return self

    def to_dict(self, *, include_wire: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "protocol_version": self.protocol_version,
            "device_id": self.device_id,
            "boot_id": self.boot_id,
            "frame_seq": self.frame_seq,
            "mcu_time_us": self.mcu_time_us,
            "host_received_ns": self.host_received_ns,
            "host_received_utc": self.host_received_utc,
            "source": self.source.value,
            "channels": list(self.channels),
            "valid_mask": list(self.valid_mask),
            "channel_count": self.channel_count,
            "valid_count": self.valid_channel_count,
            "channel_ids": list(self.channel_ids) if self.channel_ids is not None else None,
            "matrix_rows": self.matrix_rows,
            "matrix_cols": self.matrix_cols,
            "contact_score": self.contact_score,
            "frame_valid": self.frame_valid,
        }
        if include_wire and self.raw is not None:
            data["raw"] = self.raw
        return data

    def with_source(self, source: DataSource) -> "TactileFrame":
        return replace(self, source=source)


@dataclass
class DeviceStatus:
    device_id: str
    kind: str
    source: DataSource
    connected: bool = False
    state: str = "OFFLINE"
    protocol_version: int | None = PROTOCOL_VERSION
    firmware_version: str | None = None
    boot_id: str | None = None
    uptime_ms: int | None = None
    channel_count: int | None = None
    scan_mode: str | None = None
    sample_rate_hz: float | None = None
    last_frame_seq: int | None = None
    last_mcu_time_us: int | None = None
    last_host_received_ns: int | None = None
    dropped_frames: int = 0
    invalid_frames: int = 0
    restart_count: int = 0
    last_error: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "kind": self.kind,
            "source": self.source.value,
            "connected": self.connected,
            "state": self.state,
            "protocol_version": self.protocol_version,
            "firmware_version": self.firmware_version,
            "boot_id": self.boot_id,
            "uptime_ms": self.uptime_ms,
            "channel_count": self.channel_count,
            "scan_mode": self.scan_mode,
            "sample_rate_hz": self.sample_rate_hz,
            "last_frame_seq": self.last_frame_seq,
            "last_mcu_time_us": self.last_mcu_time_us,
            "last_host_received_ns": self.last_host_received_ns,
            "dropped_frames": self.dropped_frames,
            "invalid_frames": self.invalid_frames,
            "restart_count": self.restart_count,
            "last_error": self.last_error,
            "detail": self.detail,
        }


class ControlAction(str, Enum):
    QUERY_STATUS = "QUERY_STATUS"
    BEGIN_SESSION = "BEGIN_SESSION"
    SET_PWM = "SET_PWM"
    STOP = "STOP"
    DISARM = "DISARM"
    HEARTBEAT = "HEARTBEAT"
    STOP_UPDATES = "STOP_UPDATES"
    HOLD = "HOLD"
    RELEASE = "RELEASE"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


@dataclass
class ControlCommand:
    action: ControlAction
    source: DataSource
    target_pwm_us: int | None = None
    reason: str = ""
    command_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_ns: int = field(default_factory=time.monotonic_ns)
    created_utc: str = field(default_factory=utc_now_iso)
    firmware_command: str | None = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.action, ControlAction):
            self.action = ControlAction(self.action)
        self.source = parse_source(self.source)
        if self.action is ControlAction.SET_PWM:
            if not _is_int(self.target_pwm_us):
                raise ValueError("SET_PWM requires an integer target_pwm_us")
        elif self.target_pwm_us is not None and not _is_int(self.target_pwm_us):
            raise ValueError("target_pwm_us must be null or integer")
        self.firmware_command = FIRMWARE_COMMAND_MAP.get(self.action.value)

    @property
    def software_only(self) -> bool:
        return self.firmware_command is None and self.action is ControlAction.STOP_UPDATES

    @property
    def unsupported(self) -> bool:
        return self.firmware_command is None and self.action in (ControlAction.HOLD, ControlAction.RELEASE)

    def to_dict(self) -> dict[str, Any]:
        return {
            "command_id": self.command_id,
            "action": self.action.value,
            "source": self.source.value,
            "target_pwm_us": self.target_pwm_us,
            "reason": self.reason,
            "created_ns": self.created_ns,
            "created_utc": self.created_utc,
            "firmware_command": self.firmware_command,
            "software_only": self.software_only,
            "unsupported": self.unsupported,
        }


@dataclass
class ControlEvent:
    """A control decision/outcome.

    ``serial_write_ok`` and ``device_ack`` are separate.  ``actual_pwm_us`` and
    ``actual_position_known`` must remain unknown unless independent position
    feedback exists; an ACK is never copied into them.
    """

    action: str
    stage: str
    source: DataSource
    mode: str
    command_id: str | None = None
    firmware_command: str | None = None
    timestamp_ns: int = field(default_factory=time.monotonic_ns)
    timestamp_utc: str = field(default_factory=utc_now_iso)
    commanded_pwm_us: int | None = None
    serial_write_ok: bool = False
    device_ack: bool = False
    actual_pwm_us: int | None = None
    actual_position_known: bool = False
    detail: str = ""
    response: dict[str, Any] | None = None
    firmware_state: str | None = None

    def __post_init__(self) -> None:
        self.source = parse_source(self.source)
        if self.actual_pwm_us is not None:
            raise ValueError("actual_pwm_us must remain unknown without position feedback")
        if self.firmware_state is None and isinstance(self.response, dict):
            state = self.response.get("state")
            if isinstance(state, str):
                self.firmware_state = state

    @classmethod
    def from_command(
        cls,
        command: ControlCommand,
        stage: str,
        mode: str,
        *,
        serial_write_ok: bool = False,
        device_ack: bool = False,
        detail: str = "",
        response: dict | None = None,
    ) -> "ControlEvent":
        return cls(
            action=command.action.value,
            stage=stage,
            source=command.source,
            mode=mode,
            command_id=command.command_id,
            firmware_command=command.firmware_command,
            commanded_pwm_us=command.target_pwm_us,
            serial_write_ok=serial_write_ok,
            device_ack=device_ack,
            detail=detail,
            response=response,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": uuid.uuid4().hex,
            "action": self.action,
            "stage": self.stage,
            "source": self.source.value,
            "mode": self.mode,
            "command_id": self.command_id,
            "firmware_command": self.firmware_command,
            "timestamp_ns": self.timestamp_ns,
            "timestamp_utc": self.timestamp_utc,
            "commanded_pwm_us": self.commanded_pwm_us,
            "serial_write_ok": self.serial_write_ok,
            "device_ack": self.device_ack,
            "actual_pwm_us": self.actual_pwm_us,
            "actual_position_known": self.actual_position_known,
            "detail": self.detail,
            "response": self.response,
            "firmware_state": self.firmware_state,
        }


@dataclass
class TrialEvent:
    event_type: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    timestamp_ns: int = field(default_factory=time.monotonic_ns)
    timestamp_utc: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "timestamp_ns": self.timestamp_ns,
            "timestamp_utc": self.timestamp_utc,
            "event_type": self.event_type,
            "message": self.message,
            "data": self.data,
        }


@dataclass
class TrialMetadata:
    trial_id: str
    name: str
    source: DataSource
    mode: str
    created_at: str = field(default_factory=utc_now_iso)
    started_at: str | None = None
    ended_at: str | None = None
    status: str = "CREATED"
    conditions: dict[str, Any] = field(default_factory=dict)
    parameters: dict[str, Any] = field(default_factory=dict)
    notes: str = ""
    software_version: str = SOFTWARE_VERSION
    protocol_version: int = PROTOCOL_VERSION
    schema_version: int = TRIAL_SCHEMA_VERSION
    git_commit: str | None = None
    write_error: str | None = None
    files: dict[str, str] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.source = parse_source(self.source)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trial_id": self.trial_id,
            "name": self.name,
            "source": self.source.value,
            "mode": self.mode,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "status": self.status,
            "conditions": self.conditions,
            "parameters": self.parameters,
            "notes": self.notes,
            "software_version": self.software_version,
            "protocol_version": self.protocol_version,
            "schema_version": self.schema_version,
            "git_commit": self.git_commit,
            "write_error": self.write_error,
            "files": self.files,
            "counts": self.counts,
        }

    @classmethod
    def from_dict(cls, value: Mapping) -> "TrialMetadata":
        if not isinstance(value, Mapping):
            raise ValueError("trial metadata must be an object")
        try:
            source = parse_source(value["source"])
            trial_id = str(value["trial_id"])
            name = str(value.get("name", trial_id))
        except (KeyError, ValueError) as exc:
            raise ValueError("trial metadata is missing required fields") from exc
        return cls(
            trial_id=trial_id,
            name=name,
            source=source,
            mode=str(value.get("mode", "UNKNOWN")),
            created_at=str(value.get("created_at", "")),
            started_at=value.get("started_at"),
            ended_at=value.get("ended_at"),
            status=str(value.get("status", "UNKNOWN")),
            conditions=dict(value.get("conditions") or {}),
            parameters=dict(value.get("parameters") or {}),
            notes=str(value.get("notes", "")),
            software_version=str(value.get("software_version", SOFTWARE_VERSION)),
            protocol_version=int(value.get("protocol_version", PROTOCOL_VERSION)),
            schema_version=int(value.get("schema_version", 1)),
            git_commit=value.get("git_commit"),
            write_error=value.get("write_error"),
            files=dict(value.get("files") or {}),
            counts=dict(value.get("counts") or {}),
        )
