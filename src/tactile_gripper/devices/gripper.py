"""Gripper adapter around the existing, verified S3 Bench protocol.

There is exactly one serial write path: the injected ``BenchController`` from
``gripper_a`` (which uses ``gripper_a.serial_client.SerialClient``).  This file
adds application semantics (source isolation, write authority, event stages)
but does not re-implement the wire protocol or PWM handling.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from gripper_a.bench import BenchController

from ..constants import FIRMWARE_COMMAND_MAP
from ..errors import ControlDenied, OwnershipError, UnsupportedCommand
from ..models import ControlAction, ControlCommand, ControlEvent, DeviceStatus
from ..sources import DataSource

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class WriteAuthority:
    """Process-local single-writer lease for the S3 serial device."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._owner: str | None = None

    @property
    def owner(self) -> str | None:
        return self._owner

    def acquire(self, owner: str) -> str:
        with self._lock:
            if self._owner is not None and self._owner != owner:
                raise OwnershipError(
                    f"device write authority already held by {self._owner}",
                    detail={"owner": self._owner, "requested_by": owner},
                )
            self._owner = owner
            return owner

    def release(self, owner: str) -> None:
        with self._lock:
            if self._owner == owner:
                self._owner = None

    def assert_owner(self, owner: str) -> None:
        if self._owner != owner:
            raise OwnershipError(
                f"write authority is held by {self._owner}, not {owner}",
                detail={"owner": self._owner, "requested_by": owner},
            )


class GripperAdapter:
    """Application-facing gripper interface.

    ``source=SIMULATION`` uses a dry-run BenchController and never opens a
    serial port.  ``source=LIVE`` requires explicit hardware permission and a
    port (or an injected offline fake transport for tests).
    """

    def __init__(
        self,
        *,
        source: DataSource = DataSource.SIMULATION,
        config: dict | None = None,
        config_path: Path | str | None = None,
        authority: WriteAuthority | None = None,
        transport=None,
        hardware_permission: bool = False,
        dry_run: bool | None = None,
        log_path: Path | str | None = None,
        clock=time.monotonic,
        sleeper=time.sleep,
    ):
        source = DataSource(source)
        if source is DataSource.REPLAY:
            raise ControlDenied("REPLAY is read-only; no gripper adapter can be created")
        if config is None:
            path = Path(config_path) if config_path else PROJECT_ROOT / "config" / "gripper_s3.json"
            config = json.loads(Path(path).read_text(encoding="utf-8"))
            self.config_path = str(path)
        else:
            self.config_path = str(config_path) if config_path else "INLINE_CONFIG"
        self.config = config
        self.source = source
        self.authority = authority or WriteAuthority()
        self.owner = f"gripper-adapter-{uuid.uuid4().hex[:10]}"
        self.transport = transport
        self.hardware_permission = bool(hardware_permission)
        if dry_run is None:
            dry_run = source is not DataSource.LIVE
        if source is DataSource.LIVE and dry_run:
            raise ControlDenied("LIVE source cannot use a simulated gripper")
        if source is DataSource.LIVE and not self.hardware_permission:
            raise ControlDenied("LIVE gripper requires explicit hardware permission")
        self.dry_run = bool(dry_run)
        self.clock = clock
        self.sleeper = sleeper
        self.log_path = log_path
        self.connected = False
        self.session_active = False
        self.state = "OFFLINE"
        self.last_status: dict[str, Any] | None = None
        self.last_error: str | None = None
        self.last_pwm_us: int | None = None
        self.controller: BenchController | None = None
        self._lock = threading.RLock()
        self._resolve_pwm_config()

    # -- configuration -----------------------------------------------------

    def _resolve_pwm_config(self) -> None:
        config = self.config
        low = config.get("bench_min_us")
        high = config.get("bench_max_us")
        initial = config.get("bench_initial_us")
        if type(low) is not int or type(high) is not int or not 0 < low < high:
            raise ControlDenied("bench_min_us/bench_max_us missing or invalid in gripper config")
        if initial is not None and (type(initial) is not int or not low <= initial <= high):
            raise ControlDenied("bench_initial_us outside configured range")
        self.pwm_min_us = low
        self.pwm_max_us = high
        self.pwm_initial_us = initial
        self.firmware_version = config.get("firmware_version", "UNKNOWN")
        self.pwm_range_source = f"{self.config_path}:bench_min_us..bench_max_us"

    @property
    def pwm_limits(self) -> dict[str, Any]:
        return {
            "min_us": self.pwm_min_us,
            "max_us": self.pwm_max_us,
            "initial_us": self.pwm_initial_us,
            "source": self.pwm_range_source,
            "note": "Bench config range; NOT a verified mechanical safety limit.",
        }

    # -- lifecycle ---------------------------------------------------------

    def connect(self, port: str | None = None) -> dict[str, Any]:
        with self._lock:
            if self.connected:
                raise ControlDenied("already_connected")
            self.authority.acquire(self.owner)
            try:
                self.controller = BenchController(
                    config=self.config,
                    dry_run=self.dry_run,
                    hardware_permission=self.hardware_permission,
                    authorized=True if self.dry_run else self.hardware_permission,
                    transport=self.transport,
                    log_path=self.log_path,
                    clock=self.clock,
                    sleeper=self.sleeper,
                )
                status = self.controller.connect(port)
            except Exception as exc:
                self.controller = None
                self.connected = False
                self.state = "OFFLINE"
                self.last_error = str(exc)
                self.authority.release(self.owner)
                raise
            self.connected = True
            self.session_active = False
            self.state = "CONNECTED"
            self.last_status = status if isinstance(status, dict) else None
            self.last_error = None
            return self.last_status or {}

    def close(self, *, disarm: bool = True) -> None:
        with self._lock:
            try:
                if self.controller is not None:
                    try:
                        self.controller.close(disarm=disarm)
                    except Exception as exc:
                        self.last_error = f"close/disarm failed: {exc}"
                self.connected = False
                self.session_active = False
                self.state = "OFFLINE"
            finally:
                self.controller = None
                self.authority.release(self.owner)

    def poll(self) -> None:
        with self._lock:
            if not self.connected or self.controller is None:
                return
            if not self.session_active:
                return
            try:
                self.controller.poll()
                self.session_active = bool(getattr(self.controller, "active", False))
                self.state = "SESSION_ACTIVE" if self.session_active else "CONNECTED"
                self.last_error = None
            except Exception as exc:
                self.state = "FAULT"
                self.last_error = str(exc)
                self.session_active = False
                raise

    # -- command execution -------------------------------------------------

    def execute(self, command: ControlCommand, *, mode: str = "UNKNOWN") -> ControlEvent:
        with self._lock:
            if command.source is not self.source:
                return self._event(
                    command,
                    "REJECTED",
                    mode,
                    detail=f"source mismatch: adapter={self.source.value}, command={command.source.value}",
                )
            if self.source is DataSource.REPLAY:
                return self._event(command, "REJECTED", mode, detail="REPLAY is read-only")
            if command.action is ControlAction.STOP_UPDATES:
                return self._event(
                    command,
                    "SOFTWARE_ONLY",
                    mode,
                    detail="host stopped submitting targets; device output state UNKNOWN",
                )
            if command.action in (ControlAction.HOLD, ControlAction.RELEASE):
                return self._event(
                    command,
                    "UNSUPPORTED",
                    mode,
                    detail=f"no verified firmware command for {command.action.value}",
                )
            if not self.connected or self.controller is None:
                return self._event(command, "REJECTED", mode, detail="gripper is OFFLINE")
            try:
                if command.action is ControlAction.QUERY_STATUS:
                    response = self.controller.get_status()
                    self.last_status = response
                    return self._event(
                        command,
                        "DEVICE_ACK" if not self.dry_run else "SIMULATED",
                        mode,
                        serial_write_ok=not self.dry_run,
                        device_ack=not self.dry_run,
                        detail="status query response" if not self.dry_run else "simulated status response",
                        response=response,
                    )
                if command.action is ControlAction.BEGIN_SESSION:
                    if self.session_active:
                        return self._event(command, "INFO", mode, detail="session already active")
                    self.controller.begin(assembled=True)
                    self.controller.select_mode(True)
                    self.session_active = True
                    self.state = "SESSION_ACTIVE"
                    return self._event(
                        command,
                        "DEVICE_ACK" if not self.dry_run else "SIMULATED",
                        mode,
                        serial_write_ok=not self.dry_run,
                        device_ack=not self.dry_run,
                        detail="BEGIN_BENCH + BENCH_HOLD_MODE; no PWM output",
                    )
                if command.action is ControlAction.SET_PWM:
                    if not self.session_active:
                        return self._event(
                            command, "REJECTED", mode, detail="begin_session_required"
                        )
                    value = command.target_pwm_us
                    if type(value) is not int:
                        return self._event(command, "REJECTED", mode, detail="pwm_must_be_integer")
                    if not self.pwm_min_us <= value <= self.pwm_max_us:
                        return self._event(
                            command,
                            "REJECTED",
                            mode,
                            detail=f"pwm outside configured range {self.pwm_min_us}..{self.pwm_max_us}",
                        )
                    response = self.controller.pulse(value)
                    self.last_pwm_us = value
                    if self.dry_run:
                        return self._event(
                            command,
                            "SIMULATED",
                            mode,
                            device_ack=False,
                            detail="dry-run simulation; no serial write, no device ACK",
                            response=response,
                        )
                    ack = isinstance(response, dict) and response.get("type") == "ACK"
                    return self._event(
                        command,
                        "DEVICE_ACK" if ack else "FAILED",
                        mode,
                        serial_write_ok=True,
                        device_ack=ack,
                        detail="BENCH_HOLD accepted; ACK is not position feedback",
                        response=response,
                    )
                if command.action is ControlAction.STOP:
                    response = self.controller.stop()
                    self.session_active = False
                    self.state = "CONNECTED"
                    self.last_pwm_us = None
                    return self._event(
                        command,
                        "DEVICE_ACK" if not self.dry_run else "SIMULATED",
                        mode,
                        serial_write_ok=not self.dry_run,
                        device_ack=not self.dry_run,
                        detail="STOP sent; hold/release behaviour is UNKNOWN, not a hardware E-stop",
                        response=response,
                    )
                if command.action is ControlAction.DISARM:
                    response = self.controller.disarm()
                    self.session_active = False
                    self.state = "CONNECTED"
                    self.last_pwm_us = None
                    return self._event(
                        command,
                        "DEVICE_ACK" if not self.dry_run else "SIMULATED",
                        mode,
                        serial_write_ok=not self.dry_run,
                        device_ack=not self.dry_run,
                        detail="DISARM sent; output state may be UNKNOWN",
                        response=response,
                    )
                if command.action is ControlAction.HEARTBEAT:
                    response = self.controller.heartbeat()
                    return self._event(
                        command,
                        "DEVICE_ACK" if not self.dry_run else "SIMULATED",
                        mode,
                        serial_write_ok=not self.dry_run,
                        device_ack=not self.dry_run,
                        detail="heartbeat only refreshes communication lease",
                        response=response,
                    )
                return self._event(
                    command,
                    "UNSUPPORTED",
                    mode,
                    detail=f"no firmware command mapping for {command.action.value}",
                )
            except (ValueError, PermissionError) as exc:
                return self._event(command, "REJECTED", mode, detail=str(exc))
            except Exception as exc:
                self.session_active = False
                self.connected = False
                self.state = "FAULT"
                self.last_error = str(exc)
                return self._event(
                    command,
                    "FAILED",
                    mode,
                    detail=f"communication/command failure: {exc}",
                )

    def _event(self, command: ControlCommand, stage: str, mode: str, **kwargs) -> ControlEvent:
        return ControlEvent.from_command(command, stage, mode, **kwargs)

    # -- explicit semantic helpers ----------------------------------------

    def stop_updates(self) -> None:
        """Stop submitting new host targets; does not write to the device."""
        self.last_pwm_us = None

    def hold(self) -> None:
        raise UnsupportedCommand("no verified HOLD command on the S3 firmware")

    def release(self) -> None:
        raise UnsupportedCommand("no verified RELEASE command on the S3 firmware")

    # -- status ------------------------------------------------------------

    def status(self) -> DeviceStatus:
        detail = {
            "session_active": self.session_active,
            "dry_run": self.dry_run,
            "pwm_limits": self.pwm_limits,
            "firmware_command_map": dict(FIRMWARE_COMMAND_MAP),
            "transport": type(self.transport).__name__ if self.transport else "BenchController default",
            "last_pwm_us": self.last_pwm_us,
            "actual_pwm_us": None,
            "actual_position_known": False,
            "output_state": getattr(self.controller, "output_state", "UNKNOWN") if self.controller else "UNKNOWN",
            "firmware_state": getattr(self.controller, "state", "UNKNOWN") if self.controller else "UNKNOWN",
            "write_authority_owner": self.authority.owner,
            "config_path": self.config_path,
        }
        if self.last_status:
            for key in ("bench_capable", "bench_active", "output_state", "fault_reason", "last_sequence"):
                if key in self.last_status:
                    detail[key] = self.last_status[key]
        return DeviceStatus(
            device_id="s3-controller",
            kind="GRIPPER",
            source=self.source,
            connected=self.connected,
            state=self.state,
            protocol_version=1,
            firmware_version=self.firmware_version,
            boot_id=self.last_status.get("boot_id") if self.last_status else None,
            last_error=self.last_error,
            detail=detail,
        )
