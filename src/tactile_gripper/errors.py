"""Typed errors with stable machine-readable codes."""

from __future__ import annotations


class TactileError(Exception):
    code = "TACTILE_ERROR"

    def __init__(self, message: str = "", *, code: str | None = None, detail: dict | None = None):
        self.code = code or self.code
        self.detail = dict(detail or {})
        super().__init__(message or self.code)


class ProtocolError(TactileError):
    code = "PROTOCOL_ERROR"


class FrameValidationError(ProtocolError):
    code = "INVALID_FRAME"


class SensorOffline(TactileError):
    code = "SENSOR_OFFLINE"


class SensorStale(SensorOffline):
    code = "SENSOR_STALE"


class ControlDenied(TactileError):
    code = "CONTROL_DENIED"


class UnsupportedCommand(ControlDenied):
    code = "UNSUPPORTED_COMMAND"


class CommunicationFailure(TactileError):
    code = "COMMUNICATION_FAILURE"


class DeviceRejected(TactileError):
    code = "DEVICE_REJECTED"


class OwnershipError(TactileError):
    code = "WRITE_AUTHORITY_CONFLICT"


class ModeUnavailable(ControlDenied):
    code = "MODE_UNAVAILABLE"
