"""Application core: one owner for mode, control arbitration and trials."""

from __future__ import annotations

import threading
import time
from collections import deque
from enum import Enum
from pathlib import Path
from typing import Any

from ..constants import SOFTWARE_VERSION, TRIAL_SCHEMA_VERSION
from ..devices.gripper import GripperAdapter
from ..devices.sensor import (
    ReplaySensorAdapter,
    SimulatedSensorAdapter,
    default_demo_config,
)
from ..errors import (
    ControlDenied,
    FrameValidationError,
    ModeUnavailable,
    ProtocolError,
    SensorOffline,
    TrialWriteError,
)
from ..experiments.store import TrialRecorder, TrialStore, summarize_trial
from ..models import (
    ControlAction,
    ControlCommand,
    ControlEvent,
    DeviceStatus,
    TactileFrame,
    utc_now_iso,
)
from ..paths import PROJECT_ROOT, environment_snapshot
from ..sources import DataSource, parse_source


class Mode(str, Enum):
    MANUAL = "MANUAL"
    AUTO = "AUTO"
    STANDBY = "STANDBY"
    FAULT = "FAULT"

    def __str__(self) -> str:
        return self.value


MODE_LABELS = {
    Mode.MANUAL: "MANUAL / 手动",
    Mode.AUTO: "AUTO / 自动（不可用）",
    Mode.STANDBY: "STANDBY / 待机",
    Mode.FAULT: "FAULT / 故障锁存",
}

SENSOR_LABELS = {
    "OFFLINE": "SENSOR OFFLINE",
    "WAITING": "SENSOR WAITING",
    "STREAMING": "SENSOR STREAMING",
    "STALE": "SENSOR STALE",
    "DEVICE_ERROR": "SENSOR ERROR",
    "REPLAY": "SENSOR REPLAY",
}


class ApplicationCore:
    def __init__(
        self,
        *,
        root: Path | str = PROJECT_ROOT,
        config_root: Path | str = PROJECT_ROOT,
        source: DataSource = DataSource.SIMULATION,
        gripper: GripperAdapter | None = None,
        sensor=None,
        trial_store: TrialStore | None = None,
        clock=time.monotonic,
        clock_ns=time.monotonic_ns,
        demo_period_s: float = 0.2,
    ):
        self.root = Path(root)
        self.config_root = Path(config_root)
        self.source = parse_source(source)
        if self.source is DataSource.REPLAY and gripper is not None:
            raise ControlDenied("REPLAY cannot own a gripper adapter")
        if gripper is not None and gripper.source is not self.source:
            raise ControlDenied("gripper source does not match application source")
        if sensor is not None and sensor.source is not self.source:
            raise ControlDenied("sensor source does not match application source")
        self.gripper = gripper
        self.sensor = sensor
        self.trial_store = trial_store or TrialStore(self.root, self.source)
        self.clock = clock
        self.clock_ns = clock_ns
        self.demo_period_s = demo_period_s
        self.mode = Mode.STANDBY
        self.fault_reason: str | None = None
        self.events: deque[dict[str, Any]] = deque(maxlen=250)
        self._lock = threading.RLock()
        self._busy = False
        self.latest_frame: TactileFrame | None = None
        self.frames_received = 0
        self.last_sensor_error: str | None = None
        self.last_control_event: dict[str, Any] | None = None
        self.trial: TrialRecorder | None = None
        self.last_trial: dict[str, Any] | None = None
        self.trial_error: str | None = None
        self.recovered_trials: list[str] = []
        self.started_at = utc_now_iso()
        self._last_anomaly_seq: int | None = None

    # -- event log ---------------------------------------------------------

    def _append(self, event: ControlEvent) -> ControlEvent:
        payload = event.to_dict()
        self.events.append(payload)
        self.last_control_event = payload
        if self.trial is not None:
            try:
                self.trial.record_control(event)
            except ValueError as exc:
                self.events.append(
                    ControlEvent(
                        action="SYSTEM",
                        stage="WARNING",
                        source=self.source,
                        mode=self.mode.value,
                        detail=f"trial event source mismatch: {exc}",
                    ).to_dict()
                )
            except TrialWriteError as exc:
                self._note_trial_write_error(exc)
        return event

    def _note_trial_write_error(self, exc: BaseException) -> None:
        """Trial persistence failed; latch a visible FAULT without touching PWM."""
        self.trial_error = str(exc)
        self.fault_reason = f"trial write failure: {exc}"
        if self.mode is not Mode.FAULT:
            self.mode = Mode.FAULT
        payload = ControlEvent(
            action="TRIAL_WRITE_ERROR",
            stage="FAILED",
            source=self.source,
            mode=self.mode.value,
            detail=self.trial_error,
        ).to_dict()
        self.events.append(payload)
        self.last_control_event = payload

    def _system(self, action: str, detail: str, **data) -> ControlEvent:
        event = ControlEvent(
            action=action,
            stage="INFO",
            source=self.source,
            mode=self.mode.value,
            detail=detail,
        )
        return self._append(event)

    def _deny(self, action: str, detail: str, *, command: ControlCommand | None = None) -> ControlEvent:
        if command is not None:
            return self._append(ControlEvent.from_command(command, "REJECTED", self.mode.value, detail=detail))
        return self._append(
            ControlEvent(
                action=action,
                stage="REJECTED",
                source=self.source,
                mode=self.mode.value,
                detail=detail,
            )
        )

    # -- device lifecycle --------------------------------------------------

    def connect_gripper(self, port: str | None = None) -> dict[str, Any]:
        with self._lock:
            if self.source is DataSource.REPLAY:
                self._deny("CONNECT", "REPLAY is read-only")
                raise ControlDenied("REPLAY is read-only")
            if self.gripper is None:
                self._deny("CONNECT", "no gripper adapter configured")
                raise ControlDenied("no gripper adapter configured")
            try:
                status = self.gripper.connect(port)
            except Exception as exc:
                self.mode = Mode.FAULT
                self.fault_reason = f"connect failed: {exc}"
                self._append(
                    ControlEvent(
                        action="CONNECT",
                        stage="FAILED",
                        source=self.source,
                        mode=self.mode.value,
                        detail=self.fault_reason,
                    )
                )
                raise
            self.mode = Mode.STANDBY
            self.fault_reason = None
            self._system("CONNECT", f"gripper connected ({self.source.value})")
            return status

    def disconnect_gripper(self) -> None:
        with self._lock:
            if self.trial is not None and self.trial.recording:
                directory = str(self.trial.directory)
                try:
                    self.trial.stop("gripper disconnected", aborted=True)
                except TrialWriteError as exc:
                    self._note_trial_write_error(exc)
                finally:
                    if self.trial is not None:
                        self.last_trial = {**self.trial.metadata.to_dict(), "directory": directory}
                    self.trial = None
            if self.gripper is not None:
                self.gripper.close()
            self.mode = Mode.STANDBY
            self.fault_reason = None
            self._system("DISCONNECT", "gripper closed; output state may be UNKNOWN")

    def begin_manual_session(self) -> ControlEvent:
        with self._lock:
            denial = self._session_denial()
            if denial is not None:
                return self._deny("BEGIN_SESSION", denial)
            command = ControlCommand(ControlAction.BEGIN_SESSION, self.source)
            event = self.gripper.execute(command, mode=self.mode.value)
            self._append(event)
            if event.stage in ("DEVICE_ACK", "SIMULATED", "INFO") and event.firmware_state != "FAULT":
                self.mode = Mode.MANUAL
                self.fault_reason = None
            elif event.stage == "FAILED":
                self.mode = Mode.FAULT
                self.fault_reason = event.detail
            return event

    def _session_denial(self) -> str | None:
        if self.source is DataSource.REPLAY:
            return "REPLAY is read-only"
        if self.gripper is None or not self.gripper.connected:
            return "gripper is OFFLINE"
        return None

    # -- modes -------------------------------------------------------------

    def auto_available(self) -> tuple[bool, list[str]]:
        reasons = ["AUTO 闭环算法未实现（S2-B 仍不启用）"]
        if self.source is not DataSource.LIVE:
            reasons.append("数据来源不是 LIVE")
        if self.sensor is None or getattr(self.sensor, "state", "OFFLINE") != "STREAMING":
            reasons.append("真实传感器未连接/未收到有效帧")
        if self.gripper is None or self.gripper.source is not DataSource.LIVE:
            reasons.append("真实 S3 控制器未连接")
        calibration = (self.gripper.config if self.gripper else {}).get("calibration_state")
        if calibration != "CONFIRMED":
            reasons.append(f"标定状态为 {calibration or 'UNKNOWN'}")
        return False, reasons

    def set_mode(self, mode: Mode | str) -> Mode:
        with self._lock:
            target = Mode(mode)
            if target is Mode.FAULT:
                raise ModeUnavailable("FAULT is entered by the core on failure, not by the UI")
            if target is Mode.AUTO:
                available, reasons = self.auto_available()
                if not available:
                    raise ModeUnavailable("AUTO unavailable: " + "; ".join(reasons), detail={"reasons": reasons})
            if target is self.mode:
                return self.mode
            if self.mode is Mode.FAULT:
                raise ModeUnavailable("clear the fault explicitly before changing mode")
            if target is Mode.STANDBY and self.mode is Mode.MANUAL and self.gripper is not None:
                self.gripper.stop_updates()
                self._append(
                    ControlEvent(
                        action=ControlAction.STOP_UPDATES.value,
                        stage="SOFTWARE_ONLY",
                        source=self.source,
                        mode=self.mode.value,
                        detail="leaving MANUAL stops host updates; device output is unchanged",
                    )
                )
            if target is Mode.MANUAL:
                if self.source is DataSource.REPLAY:
                    raise ModeUnavailable("REPLAY cannot enter MANUAL")
                if self.gripper is None or not self.gripper.connected:
                    raise ModeUnavailable("MANUAL requires a connected gripper")
                if self.gripper.state == "FAULT":
                    raise ModeUnavailable("MANUAL requires a non-FAULT controller; reconnect explicitly")
                if not self._manual_session_active():
                    raise ModeUnavailable("MANUAL requires a started manual session")
            previous = self.mode
            self.mode = target
            self._system("MODE_CHANGE", f"{previous.value} -> {target.value}")
            return self.mode

    def _manual_session_active(self) -> bool:
        if self.gripper is None or not self.gripper.connected:
            return False
        return bool(getattr(self.gripper, "session_active", False))

    # -- control -----------------------------------------------------------

    def _manual_denial(self) -> str | None:
        if self.source is DataSource.REPLAY:
            return "REPLAY is read-only; no hardware write"
        if self.mode is not Mode.MANUAL:
            return f"mode is {self.mode.value}, not MANUAL"
        if self.gripper is None or not self.gripper.connected:
            return "gripper is OFFLINE"
        if self.gripper.state == "FAULT":
            return "gripper is in FAULT; reconnect before further targets"
        if not self._manual_session_active():
            return "manual session is not active"
        return None

    def request_pwm(self, pulse_us: int) -> ControlEvent:
        with self._lock:
            if type(pulse_us) is not int:
                return self._deny("SET_PWM", "pwm must be an integer")
            command = ControlCommand(ControlAction.SET_PWM, self.source, target_pwm_us=pulse_us)
            if self._busy:
                return self._deny("SET_PWM", "another command is in flight", command=command)
            denial = self._manual_denial()
            if denial is not None:
                return self._deny("SET_PWM", denial, command=command)
            assert self.gripper is not None
            if not self.gripper.pwm_min_us <= pulse_us <= self.gripper.pwm_max_us:
                return self._deny(
                    "SET_PWM",
                    f"pwm outside configured range {self.gripper.pwm_min_us}..{self.gripper.pwm_max_us}",
                    command=command,
                )
            self._busy = True
            try:
                event = self.gripper.execute(command, mode=self.mode.value)
            finally:
                self._busy = False
            self._append(event)
            if event.stage == "FAILED":
                self.mode = Mode.FAULT
                self.fault_reason = event.detail
            return event

    def stop(self) -> ControlEvent:
        command = ControlCommand(ControlAction.STOP, self.source)
        with self._lock:
            if self.source is DataSource.REPLAY:
                return self._deny("STOP", "REPLAY is read-only", command=command)
            if self.gripper is None or not self.gripper.connected:
                return self._deny("STOP", "gripper is OFFLINE", command=command)
            event = self.gripper.execute(command, mode=self.mode.value)
            self._append(event)
            if event.firmware_state == "FAULT" or getattr(self.gripper, "state", None) == "FAULT":
                self.mode = Mode.FAULT
                self.fault_reason = "device reports FAULT after STOP; STOP does not clear FAULT"
            elif event.stage in ("DEVICE_ACK", "SIMULATED"):
                self.mode = Mode.STANDBY
                self.fault_reason = None
            elif event.stage == "FAILED":
                self.mode = Mode.FAULT
                self.fault_reason = event.detail
            return event

    def stop_updates(self) -> ControlEvent:
        command = ControlCommand(ControlAction.STOP_UPDATES, self.source)
        with self._lock:
            if self.gripper is not None:
                self.gripper.stop_updates()
            event = ControlEvent.from_command(
                command,
                "SOFTWARE_ONLY",
                self.mode.value,
                detail="host stops submitting targets; device output is not changed",
            )
            self._append(event)
            if self.mode is Mode.MANUAL:
                self.mode = Mode.STANDBY
            return event

    def hold(self) -> ControlEvent:
        command = ControlCommand(ControlAction.HOLD, self.source)
        with self._lock:
            if self.gripper is None:
                return self._deny("HOLD", "no gripper adapter", command=command)
            event = self.gripper.execute(command, mode=self.mode.value)
            self._append(event)
            return event

    def release(self) -> ControlEvent:
        command = ControlCommand(ControlAction.RELEASE, self.source)
        with self._lock:
            if self.gripper is None:
                return self._deny("RELEASE", "no gripper adapter", command=command)
            event = self.gripper.execute(command, mode=self.mode.value)
            self._append(event)
            return event

    def clear_fault(self) -> None:
        with self._lock:
            if self.mode is not Mode.FAULT:
                return
            if self.gripper is not None and self.gripper.state == "FAULT":
                raise ModeUnavailable(
                    "underlying device is still in FAULT; reconnect and re-authorize explicitly"
                )
            self.mode = Mode.STANDBY
            self.fault_reason = None
            self._system("CLEAR_FAULT", "fault cleared; device remains disarmed unless explicitly reconnected")

    # -- sensors -----------------------------------------------------------

    def set_demo_stream(self, enabled: bool) -> DeviceStatus | None:
        with self._lock:
            if self.source is not DataSource.SIMULATION:
                self._deny("DEMO_STREAM", "simulation demo only available for SIMULATION source")
                raise ControlDenied("simulation demo only available for SIMULATION source")
            if enabled:
                if self.sensor is not None and getattr(self.sensor, "connected", False):
                    return self.sensor.status()
                self.sensor = SimulatedSensorAdapter(
                    default_demo_config(self.config_root),
                    period_s=self.demo_period_s,
                    clock_ns=self.clock_ns,
                )
                self.sensor.connect()
                self._system("DEMO_STREAM", "SIMULATION sensor connected; not real hardware")
                return self.sensor.status()
            if self.sensor is not None:
                self.sensor.close()
                self.sensor = None
                self.latest_frame = None
                self._system("DEMO_STREAM", "SIMULATION sensor disconnected")
            return None

    def _read_sensor(self) -> None:
        if self.sensor is None:
            return
        try:
            if not self.sensor.connected:
                return
        except AttributeError:
            return
        for _ in range(8):
            try:
                frame = self.sensor.read_frame(0.0)
            except FrameValidationError as exc:
                self.last_sensor_error = f"{exc.code}: {exc}"
                self._append(
                    ControlEvent(
                        action="SENSOR",
                        stage="INVALID_DATA",
                        source=self.source,
                        mode=self.mode.value,
                        detail=self.last_sensor_error,
                    )
                )
                break
            except SensorOffline as exc:
                self.last_sensor_error = str(exc)
                self._append(
                    ControlEvent(
                        action="SENSOR",
                        stage="OFFLINE",
                        source=self.source,
                        mode=self.mode.value,
                        detail=self.last_sensor_error,
                    )
                )
                break
            except ProtocolError as exc:
                self.last_sensor_error = str(exc)
                self._append(
                    ControlEvent(
                        action="SENSOR",
                        stage="DEVICE_ERROR",
                        source=self.source,
                        mode=self.mode.value,
                        detail=self.last_sensor_error,
                    )
                )
                break
            if frame is None:
                break
            self.latest_frame = frame
            self.frames_received += 1
            self.last_sensor_error = None
            self._record_frame_anomalies()
            if self.trial is not None and self.trial.recording:
                try:
                    self.trial.record_frame(frame)
                except ValueError as exc:
                    self._append(
                        ControlEvent(
                            action="TRIAL",
                            stage="WARNING",
                            source=self.source,
                            mode=self.mode.value,
                            detail=f"frame not recorded: {exc}",
                        )
                    )
                except TrialWriteError as exc:
                    self._note_trial_write_error(exc)

    def _record_frame_anomalies(self) -> None:
        if self.sensor is None or not hasattr(self.sensor, "last_anomalies"):
            return
        for anomaly in getattr(self.sensor, "last_anomalies", []):
            key = (anomaly.kind, anomaly.actual_seq)
            if getattr(self, "_last_anomaly_key", None) == key:
                continue
            self._last_anomaly_key = key
            self._append(
                ControlEvent(
                    action="SENSOR_ANOMALY",
                    stage=anomaly.kind,
                    source=self.source,
                    mode=self.mode.value,
                    detail=anomaly.detail,
                )
            )

    # -- trials ------------------------------------------------------------

    def create_trial(
        self,
        name: str,
        *,
        conditions: dict | None = None,
        notes: str = "",
    ) -> dict[str, Any]:
        with self._lock:
            if self.source is DataSource.REPLAY:
                raise ControlDenied("REPLAY is read-only; it cannot create a trial")
            if self.trial is not None and self.trial.recording:
                raise ControlDenied("a trial is already recording")
            environment = environment_snapshot()
            environment["software_version"] = SOFTWARE_VERSION
            parameters = {
                "software_version": SOFTWARE_VERSION,
                "source": self.source.value,
                "mode": self.mode.value,
                "schema_version": TRIAL_SCHEMA_VERSION,
                "git_commit": environment["git_commit"],
                "environment": environment,
                "firmware_version": self.gripper.firmware_version if self.gripper else None,
                "pwm_limits": self.gripper.pwm_limits if self.gripper else None,
                "gripper_config": dict(self.gripper.config) if self.gripper else None,
                "sensor_config": (
                    self.sensor.channel_config.to_dict()
                    if self.sensor is not None and self.sensor.channel_config is not None
                    else None
                ),
                "sensor": (
                    {
                        "channel_count": self.sensor.channel_config.expected_channel_count,
                        "matrix": [self.sensor.channel_config.matrix_rows, self.sensor.channel_config.matrix_cols],
                        "config_status": self.sensor.channel_config.status,
                    }
                    if self.sensor is not None and self.sensor.channel_config is not None
                    else None
                ),
                "auto_available": self.auto_available()[0],
            }
            self.trial = self.trial_store.create_trial(
                name,
                mode=self.mode.value,
                conditions=conditions,
                parameters=parameters,
                notes=notes,
                git_commit=environment["git_commit"],
            )
            self.trial_error = None
            self._system("TRIAL_CREATED", f"trial {self.trial.metadata.trial_id} created")
            return self.trial.metadata.to_dict()

    def start_trial(self) -> dict[str, Any]:
        with self._lock:
            if self.trial is None:
                raise ControlDenied("no trial created")
            if self.trial.recording:
                raise ControlDenied("trial is already recording")
            try:
                self.trial.start()
            except TrialWriteError as exc:
                self._note_trial_write_error(exc)
                raise
            self._system("TRIAL_START", f"recording {self.trial.metadata.trial_id}")
            return self.trial.metadata.to_dict()

    def stop_trial(self, reason: str = "manual", *, aborted: bool = False) -> dict[str, Any]:
        with self._lock:
            if self.trial is None or not self.trial.recording:
                raise ControlDenied("no trial recording")
            directory = str(self.trial.directory)
            try:
                metadata = self.trial.stop(reason, aborted=aborted)
            except TrialWriteError as exc:
                self._note_trial_write_error(exc)
                metadata = self.trial.metadata
                self.last_trial = {**metadata.to_dict(), "directory": directory}
                self.trial = None
                raise
            self.last_trial = {**metadata.to_dict(), "directory": directory}
            self.trial = None
            self.trial_error = None
            self._system("TRIAL_STOP", f"trial {metadata.trial_id} stopped: {reason}")
            return self.last_trial

    def add_trial_event(self, event_type: str, message: str, data: dict | None = None) -> dict[str, Any]:
        with self._lock:
            if self.trial is None:
                raise ControlDenied("no active trial")
            try:
                event = self.trial.add_event(event_type, message, data)
            except TrialWriteError as exc:
                self._note_trial_write_error(exc)
                raise
            return event.to_dict()

    def list_trials(self) -> list[dict[str, Any]]:
        self.recovered_trials = self.trial_store.recover_interrupted()
        items = []
        for stored in self.trial_store.list_trials():
            item = stored.metadata.to_dict()
            item["directory"] = str(stored.directory)
            items.append(item)
        return items

    def read_trial(self, trial_id: str) -> dict[str, Any]:
        self.trial_store.recover_interrupted()
        record = self.trial_store.load(trial_id)
        return {
            "metadata": record.metadata.to_dict(),
            "directory": str(record.directory),
            "events": record.events,
            "frames": record.frames,
            "read_errors": record.read_errors,
            "summary": summarize_trial(record),
        }

    # -- status ------------------------------------------------------------

    def tick(self) -> None:
        with self._lock:
            self._read_sensor()
            if self.trial is not None and self.trial.recording:
                try:
                    self.trial.heartbeat()
                except TrialWriteError as exc:
                    self._note_trial_write_error(exc)
            if (
                self.gripper is not None
                and self.gripper.connected
                and self.gripper.session_active
            ):
                try:
                    self.gripper.poll()
                except Exception as exc:
                    self.mode = Mode.FAULT
                    self.fault_reason = f"heartbeat/poll failed: {exc}"

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            gripper_status = (
                self.gripper.status().to_dict()
                if self.gripper is not None
                else DeviceStatus(
                    device_id="s3-controller",
                    kind="GRIPPER",
                    source=self.source,
                    connected=False,
                    state="OFFLINE",
                    last_error=None,
                    detail={"note": "no gripper adapter for this source"},
                ).to_dict()
            )
            if self.sensor is not None:
                sensor_status = self.sensor.status().to_dict()
            else:
                sensor_status = DeviceStatus(
                    device_id="sensor",
                    kind="SENSOR",
                    source=self.source,
                    connected=False,
                    state="WAITING" if self.source is not DataSource.REPLAY else "REPLAY",
                    detail={"note": "no sensor connected; no waveform is fabricated"},
                ).to_dict()
            auto_ok, auto_reasons = self.auto_available()
            denial = self._manual_denial()
            latest = None
            if self.latest_frame is not None:
                frame = self.latest_frame
                latest = {
                    "frame_seq": frame.frame_seq,
                    "boot_id": frame.boot_id,
                    "mcu_time_us": frame.mcu_time_us,
                    "host_received_ns": frame.host_received_ns,
                    "host_received_utc": frame.host_received_utc,
                    "source": frame.source.value,
                    "channels": list(frame.channels),
                    "valid_mask": list(frame.valid_mask),
                    "channel_ids": list(frame.channel_ids) if frame.channel_ids is not None else None,
                    "matrix_rows": frame.matrix_rows,
                    "matrix_cols": frame.matrix_cols,
                    "channel_count": frame.channel_count,
                    "valid_count": frame.valid_channel_count,
                    "contact_score": frame.contact_score,
                }
            trial = None
            if self.trial is not None:
                trial = self.trial.metadata.to_dict()
                trial["directory"] = str(self.trial.directory)
                trial["recording"] = self.trial.recording
                trial["counts"] = {
                    "frames": self.trial.frame_count,
                    "events": self.trial.event_count,
                    "invalid_channel_samples": self.trial.invalid_channel_samples,
                    "frames_with_invalid_channels": self.trial.frames_with_invalid,
                    "dropped_frames": self.trial.dropped_frames,
                    "restarts": self.trial.restarts,
                }
            elif self.last_trial is not None:
                trial = self.last_trial
                trial["recording"] = False
            return {
                "time": utc_now_iso(),
                "mode": self.mode.value,
                "mode_label": MODE_LABELS[self.mode],
                "fault_reason": self.fault_reason,
                "source": self.source.value,
                "source_label": self.source.label,
                "gripper": gripper_status,
                "sensor": sensor_status,
                "sensor_state_label": SENSOR_LABELS.get(sensor_status.get("state"), sensor_status.get("state", "UNKNOWN")),
                "latest_frame": latest,
                "frames_received": self.frames_received,
                "last_sensor_error": self.last_sensor_error,
                "apply_enabled": denial is None,
                "apply_denial": denial,
                "stop_enabled": bool(self.gripper is not None and self.gripper.connected and self.source is not DataSource.REPLAY),
                "auto_available": auto_ok,
                "auto_reasons": auto_reasons,
                "pwm": self.gripper.pwm_limits if self.gripper else None,
                "last_pwm_us": (gripper_status.get("detail") or {}).get("last_pwm_us"),
                "trial": trial,
                "trial_error": self.trial_error,
                "recovered_trials": list(self.recovered_trials),
                "recent_events": list(self.events)[-15:][::-1],
                "manual_session_active": self._manual_session_active(),
                "sensor_connected": sensor_status.get("connected", False),
            }


def build_core(
    *,
    source: DataSource | str = DataSource.SIMULATION,
    root: Path | str = PROJECT_ROOT,
    config_path: Path | str | None = None,
    hardware_permission: bool = False,
    port: str | None = None,
    connect: bool = False,
    sensor_file: Path | str | None = None,
) -> ApplicationCore:
    source = parse_source(source)
    gripper = None
    if source is not DataSource.REPLAY:
        gripper = GripperAdapter(
            source=source,
            config_path=config_path,
            hardware_permission=hardware_permission,
        )
    sensor = None
    if sensor_file is not None:
        if source is not DataSource.REPLAY:
            raise ControlDenied("sensor_file replay requires --source REPLAY")
        sensor = ReplaySensorAdapter(sensor_file)
    core = ApplicationCore(root=root, source=source, gripper=gripper, sensor=sensor)
    if connect:
        if source is DataSource.REPLAY:
            raise ControlDenied("REPLAY cannot connect a gripper")
        core.connect_gripper(port)
        core.begin_manual_session()
    return core
