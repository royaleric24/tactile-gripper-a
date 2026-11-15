"""Application core: one owner for mode, control arbitration and trials."""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import replace
from enum import Enum
from pathlib import Path
from typing import Any

from ..constants import SOFTWARE_VERSION, TRIAL_SCHEMA_VERSION
from ..devices.firmware_fixture import firmware_fixture_adapter
from ..devices.gripper import GripperAdapter
from ..devices.sensor import (
    ReplaySensorAdapter,
    SimulatedSensorAdapter,
    demo_config_for_profile,
)
from ..devices.sensor_serial import SerialSensorConfig, serial_sensor_adapter
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
from ..protocol import CURRENT_SENSOR_PROFILES
from ..sources import DataSource, parse_source
from .auto import (
    AUTO_REAL_ENABLED,
    AutoDecision,
    AutoGate,
    AutoLimits,
    RuleBasedAutoPolicy,
)
from .contact import ContactAssessment, FsrContactAssessor, FsrThresholds


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
        demo_profile: str = "FSR_ONLY",
        fsr_thresholds: FsrThresholds | None = None,
        commission_real_auto: bool = False,
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
        self.log_follow = bool(
            getattr(gripper, "read_only", False)
            or getattr(sensor, "log_transport", None) is not None
        )
        self.firmware_fixture = getattr(getattr(sensor, "transport", None), "scenario", None)
        self.trial_store = trial_store or TrialStore(self.root, self.source)
        self.clock = clock
        self.clock_ns = clock_ns
        self.demo_period_s = demo_period_s
        self.demo_profile = demo_profile
        self.contact_assessor = FsrContactAssessor(fsr_thresholds or FsrThresholds())
        self.last_assessment: ContactAssessment | None = None
        self.fsr_history: deque[dict[str, Any]] = deque(maxlen=180)
        # Wider display window for the unified FSR/PWM timeline.  Trial files
        # keep every accepted frame; this is only the live chart buffer.
        self.fsr_timeline: deque[dict[str, Any]] = deque(maxlen=8000)
        self.last_auto_decision: AutoDecision | None = None
        self.last_pwm_command: dict[str, Any] | None = None
        self.pending_command: dict[str, Any] | None = None
        self.real_auto_commissioning_requested = bool(commission_real_auto)
        self.auto_policy = RuleBasedAutoPolicy(
            AutoLimits(),
            AutoGate(source=self.source, allow_simulation=self.source is DataSource.SIMULATION),
        )
        self.mode = Mode.STANDBY
        self.fault_reason: str | None = None
        self.events: deque[dict[str, Any]] = deque(maxlen=250)
        self.event_overflow_count = 0
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

    def _push_event(self, payload: dict[str, Any]) -> None:
        if len(self.events) >= self.events.maxlen:
            self.event_overflow_count += 1
        self.events.append(payload)

    def _append(self, event: ControlEvent) -> ControlEvent:
        payload = event.to_dict()
        self._push_event(payload)
        self.last_control_event = payload
        if self.trial is not None:
            try:
                self.trial.record_control(event)
            except ValueError as exc:
                self._push_event(
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
        self._push_event(payload)
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

    def shutdown(self) -> None:
        """Best-effort resource cleanup; does not claim a safe mechanical stop."""
        with self._lock:
            if self.trial is not None and self.trial.recording:
                try:
                    self.stop_trial("application shutdown", aborted=True)
                except Exception as exc:
                    self.trial_error = str(exc)
            if self.trial is not None:
                try:
                    self.trial.close()
                except Exception:
                    pass
                self.trial = None
            if self.sensor is not None:
                try:
                    self.sensor.close()
                except Exception:
                    pass
            if self.gripper is not None:
                try:
                    self.gripper.close()
                except Exception as exc:
                    self.last_sensor_error = f"gripper close failed: {exc}"
            self.mode = Mode.STANDBY
            self.fault_reason = None

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
        from .auto import AUTO_REAL_ENABLED

        reasons = ["V2 真实 AUTO 仍硬关闭（AUTO_REAL_ENABLED=False）"]
        if not AUTO_REAL_ENABLED:
            reasons.append("等待传感器协议、PWM 方向/范围、触觉标定与实测验证")
        else:
            reasons = ["真实 AUTO 需要显式现场调试入口和标定"]
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

    # -- FSR contact / explicit AUTO commissioning gate --------------------

    def sensor_configuration(self):
        return self.sensor.channel_config if self.sensor is not None else None

    def sensor_identity(self) -> dict[str, Any] | None:
        if self.sensor is None:
            return None
        if hasattr(self.sensor, "identity"):
            return self.sensor.identity()
        return {"role": "SENSOR", "device_id": getattr(self.sensor, "device_id", None)}

    def gripper_identity(self) -> dict[str, Any] | None:
        if self.gripper is None:
            return None
        detail = getattr(self.gripper, "status", lambda: None)()
        detail = detail.to_dict() if detail is not None and hasattr(detail, "to_dict") else {}
        serial_cfg = (self.gripper.config or {}).get("serial", {}) if isinstance(self.gripper.config, dict) else {}
        return {
            "role": "GRIPPER",
            "device_id": detail.get("device_id"),
            "boot_id": detail.get("boot_id"),
            "firmware_version": detail.get("firmware_version"),
            "port": serial_cfg.get("port"),
            "baudrate": serial_cfg.get("baudrate"),
            "source": self.gripper.source.value,
        }

    def device_identities(self) -> dict[str, Any]:
        return {"sensor": self.sensor_identity(), "gripper": self.gripper_identity()}

    def capture_fsr_baseline(self) -> ContactAssessment:
        """Explicit operator action: record unloaded FSR counts.

        No baseline is fabricated for a real device.  Simulation may capture
        automatically from its first valid frame, but that is labelled
        SIMULATION_AUTO and can only drive the in-memory demo policy.
        """
        with self._lock:
            config = self.sensor_configuration()
            frame = self.latest_frame
            if config is None or frame is None:
                raise ControlDenied("no FSR frame available for baseline")
            if not config.fsr_channels:
                raise ControlDenied("sensor profile has no FSR channels")
            if self.sensor.last_frame is None or self.sensor.state not in ("STREAMING", "REPLAY", "FIXTURE_COMPLETE"):
                raise ControlDenied("FSR baseline requires an accepted frame from the current session")
            # A recorded REPLAY is not judged against wall-clock now; its own
            # host_received_ns is the only timebase it has.
            reference_ns = (
                int(frame.host_received_ns)
                if self.source is DataSource.REPLAY
                else self.clock_ns()
            )
            age_ms = max(0, reference_ns - int(frame.host_received_ns)) / 1_000_000
            if age_ms > 500:
                raise ControlDenied(f"latest FSR frame is stale ({age_ms:.0f} ms); capture a fresh unloaded frame")
            try:
                assessment = self.contact_assessor.capture_baseline(frame, config)
            except ValueError as exc:
                raise ControlDenied(f"baseline rejected: {exc}") from exc
            self.last_assessment = assessment
            self._system(
                "FSR_BASELINE_CAPTURED",
                f"FSR baseline captured from frame {frame.frame_seq}; relative score only, not force",
            )
            return assessment

    def clear_fsr_baseline(self) -> None:
        with self._lock:
            self.contact_assessor.clear_baseline()
            self.last_assessment = None
            self._system("FSR_BASELINE_CLEARED", "FSR baseline cleared; AUTO contact assessment is uncalibrated")

    def request_real_auto_commissioning(self) -> None:
        """Explicit future entry point.  It is intentionally denied today."""
        with self._lock:
            self.real_auto_commissioning_requested = True
            detail = "AUTO_REAL_ENABLED=False; real AUTO commissioning requires protocol+hardware+calibration sign-off"
            self._system("AUTO_COMMISSIONING_DENIED", detail)
            raise ControlDenied(detail)

    def evaluate_auto_contact(
        self,
        *,
        pending_command: bool = False,
        sensor_state: str | None = None,
    ) -> AutoDecision:
        """Offline-facing decision record; never sends PWM.

        It exists so tests can prove invalid/stale/partial data cannot issue a
        tightening step.  The real gate remains closed.
        """
        with self._lock:
            frame = self.latest_frame
            assessment = self.last_assessment
            state = self.sensor.status().state if self.sensor is not None else "OFFLINE"
            if state == "FIXTURE_COMPLETE":
                # Offline decision on the last fixture only while its normal
                # monotonic deadline still holds. No actuator dispatch.
                state = "STREAMING"
            config = self.sensor_configuration()
            single_fsr = config.fsr_channels[0] if config and len(config.fsr_channels) == 1 else None
            decision = self.auto_policy.evaluate_contact(
                frame,
                assessment,
                now_ns=self.clock_ns(),
                target_us=int((self.gripper.last_pwm_us or self.gripper.pwm_initial_us) if self.gripper else 0),
                steps=0,
                total_change_us=0,
                sensor_state=state if state != "STREAMING" else (sensor_state or state),
                pending_command=bool(pending_command or self.pending_command or (
                    self.last_pwm_command and self.last_pwm_command.get("acknowledged") is not True
                )),
                single_fsr=single_fsr,
                min_pwm_us=(self.gripper.pwm_limits or {}).get("min_us") if self.gripper else None,
                max_pwm_us=(self.gripper.pwm_limits or {}).get("max_us") if self.gripper else None,
            )
            self.last_auto_decision = decision
            self._append(
                ControlEvent(
                    action="AUTO_DECISION",
                    stage="OFFLINE_NO_COMMAND",
                    source=self.source,
                    mode=self.mode.value,
                    detail=str(decision.to_dict()),
                )
            )
            return decision

    def _assess_latest_frame(self, frame: TactileFrame) -> TactileFrame:
        config = self.sensor_configuration()
        if config is None or not config.fsr_channels:
            self.last_assessment = None
            return frame
        # The synthetic demo starts unloaded. Firmware fixtures and live
        # samples require an explicit baseline because that is not known.
        if (
            self.source is DataSource.SIMULATION
            and not self.firmware_fixture
            and not self.contact_assessor.baseline_ready
            and frame.frame_valid
        ):
            try:
                self.contact_assessor.capture_baseline(frame, config, source="SIMULATION_AUTO")
            except ValueError:
                pass
        # During REPLAY, freshness is relative to the recorded frame itself;
        # otherwise every archived frame would look stale and the FSR state
        # could not be reviewed.  A log-followed LIVE frame is the same case:
        # its host receive time came from the capture file, and stream
        # staleness is reported by the sensor adapter state (STALE/OFFLINE).
        assessment_now_ns = (
            int(frame.host_received_ns)
            if self.source is DataSource.REPLAY or self.log_follow
            else self.clock_ns()
        )
        assessment = self.contact_assessor.assess(
            frame,
            config,
            now_ns=assessment_now_ns,
            stale_after_ms=200.0,
        )
        self.last_assessment = assessment
        self.fsr_history.append(
            {
                "frame_seq": frame.frame_seq,
                "host_received_ns": frame.host_received_ns,
                "host_received_utc": frame.host_received_utc,
                "state": assessment.state,
                "score": assessment.score,
                "readings": [reading.to_dict() for reading in assessment.readings],
            }
        )
        if self.mode is Mode.AUTO and assessment.state in ("INVALID", "UNCALIBRATED", "NOT_APPLICABLE"):
            self.mode = Mode.FAULT
            self.fault_reason = f"AUTO contact assessment {assessment.state}: {assessment.reason}"
            self._system("AUTO_SAFETY_FAULT", self.fault_reason)
        if assessment.score is not None:
            frame = replace(frame, contact_score=assessment.score)
        return frame

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
        if getattr(self.gripper, "read_only", False):
            return "LOG-FOLLOW 只读监控：PWM 只能由独占串口的 pwm_console 发送"
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
            self.pending_command = command.to_dict()
            self.last_pwm_command = self.pending_command
            try:
                event = self.gripper.execute(command, mode=self.mode.value)
            finally:
                self._busy = False
                self.pending_command = None
            self._append(event)
            if self.last_pwm_command is not None:
                self.last_pwm_command = {
                    **self.last_pwm_command,
                    "acknowledged": event.device_ack,
                    "stage": event.stage,
                    "command_id": event.command_id,
                }
            if event.stage == "FAILED":
                self.mode = Mode.FAULT
                self.fault_reason = event.detail
            return event

    def stop(self) -> ControlEvent:
        command = ControlCommand(ControlAction.STOP, self.source)
        with self._lock:
            if self.source is DataSource.REPLAY:
                return self._deny("STOP", "REPLAY is read-only", command=command)
            if getattr(self.gripper, "read_only", False):
                return self._deny(
                    "STOP",
                    "LOG-FOLLOW 只读监控：STOP 只能由 pwm_console 发送",
                    command=command,
                )
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

    def connect_sensor(self) -> dict[str, Any]:
        with self._lock:
            if self.sensor is None:
                raise ControlDenied("no sensor adapter configured")
            try:
                status = self.sensor.connect()
            except SensorOffline as exc:
                self.last_sensor_error = str(exc)
                self._append(
                    ControlEvent(
                        action="SENSOR",
                        stage="CONNECT_FAILED",
                        source=self.source,
                        mode=self.mode.value,
                        detail=self.last_sensor_error,
                    )
                )
                raise
            self.last_sensor_error = None
            self._system("SENSOR_CONNECT", "sensor transport connected; no control write")
            return status.to_dict()

    def query_sensor_status(self) -> bool:
        return self._query_sensor("STATUS")

    def query_sensor_hello(self) -> bool:
        return self._query_sensor("HELLO")

    def request_sensor_stream(self, enabled: bool) -> bool:
        with self._lock:
            if self.source is not DataSource.LIVE or self.sensor is None:
                raise ControlDenied("sensor stream command requires an explicitly authorized LIVE source")
            ok = self.sensor.request_stream(enabled)
            self._system("SENSOR_QUERY", f"sensor stream request {'sent' if ok else 'not sent'}")
            return ok

    def _query_sensor(self, query: str) -> bool:
        with self._lock:
            if self.sensor is None:
                raise ControlDenied("no sensor adapter")
            method = getattr(self.sensor, f"query_{query.lower()}", None)
            if method is None:
                raise ControlDenied(f"sensor adapter does not support {query} query")
            ok = bool(method())
            self._system(
                "SENSOR_QUERY",
                f"{query} query sent" if ok else f"{query} query failed: {self.sensor.last_error}",
            )
            return ok

    def select_demo_profile(self, profile: str) -> None:
        with self._lock:
            if self.source is not DataSource.SIMULATION or self.firmware_fixture:
                raise ControlDenied("demo profile only applies to SIMULATION")
            if profile.upper() not in CURRENT_SENSOR_PROFILES:
                raise ControlDenied("historical sensor profile is replay-only")
            self.demo_profile = profile.upper()
            self.contact_assessor.clear_baseline()
            self.last_assessment = None
            self.fsr_history.clear()
            self._system("DEMO_PROFILE", f"demo profile set to {self.demo_profile}")

    def set_demo_stream(self, enabled: bool, *, profile: str | None = None) -> DeviceStatus | None:
        with self._lock:
            if self.source is not DataSource.SIMULATION or self.firmware_fixture:
                self._deny("DEMO_STREAM", "simulation demo only available for SIMULATION source")
                raise ControlDenied("simulation demo only available for SIMULATION source")
            selected = (profile or self.demo_profile).upper()
            if selected not in CURRENT_SENSOR_PROFILES:
                raise ControlDenied("historical sensor profile is replay-only")
            if enabled:
                if (
                    self.sensor is not None
                    and getattr(self.sensor, "connected", False)
                    and self.sensor.channel_config.sensor_profile == selected
                ):
                    return self.sensor.status()
                if self.sensor is not None:
                    self.sensor.close()
                self.latest_frame = None
                self.demo_profile = selected
                self.contact_assessor.clear_baseline()
                self.last_assessment = None
                self.fsr_history.clear()
                self.sensor = SimulatedSensorAdapter(
                    demo_config_for_profile(selected, self.config_root),
                    period_s=self.demo_period_s,
                    clock_ns=self.clock_ns,
                )
                self.sensor.connect()
                self._system(
                    "DEMO_STREAM",
                    f"SIMULATION sensor connected ({selected}); not real hardware",
                )
                return self.sensor.status()
            if self.sensor is not None:
                self.sensor.close()
                self.sensor = None
                self.latest_frame = None
                self.last_assessment = None
                self.fsr_history.clear()
                self.contact_assessor.clear_baseline()
                self._system("DEMO_STREAM", "SIMULATION sensor disconnected")
            return None

    def _read_sensor(self) -> None:
        if self.sensor is None:
            return
        try:
            if not self.sensor.connected:
                before = getattr(self.sensor, "reconnect_attempts", 0)
                try:
                    reconnected = bool(self.sensor.maybe_reconnect())
                except Exception as exc:
                    self.last_sensor_error = f"sensor reconnect failed: {exc}"
                    return
                if reconnected:
                    self._system("SENSOR_RECONNECT", "sensor serial transport reconnected")
                elif getattr(self.sensor, "reconnect_attempts", 0) != before:
                    self.last_sensor_error = (
                        getattr(self.sensor, "last_reconnect_error", None)
                        or "sensor reconnect attempt failed"
                    )
                return
        except AttributeError:
            return
        # A log-follow attach may have to drain a backlog; reading from a file
        # is fast, so a larger batch avoids minutes of catch-up lag.
        for _ in range(4096 if self.log_follow else 64):
            try:
                frame = self.sensor.read_frame(0.0)
            except FrameValidationError as exc:
                self.last_sensor_error = f"{exc.code}: {exc}"
                self._latch_auto_sensor_fault(self.last_sensor_error)
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
                self._latch_auto_sensor_fault(self.last_sensor_error)
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
                self._latch_auto_sensor_fault(self.last_sensor_error)
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
                # HELLO for a new boot invalidates the previous sample and
                # baseline even before the replacement SAMPLE arrives.
                if self.latest_frame is not None and self.sensor.last_frame is None:
                    self.latest_frame = None
                    self.last_assessment = None
                    self.contact_assessor.clear_baseline()
                    self.fsr_history.clear()
                break
            self._record_frame_anomalies()
            frame = self._assess_latest_frame(frame)
            self.latest_frame = frame
            self.frames_received += 1
            self.last_sensor_error = None
            self._append_timeline_point(frame)
            if self.trial is not None and self.trial.recording:
                try:
                    config = self.sensor_configuration()
                    control_context = self.last_pwm_command
                    if self.log_follow and self.gripper is not None and hasattr(
                        self.gripper, "pwm_context_at"
                    ):
                        # Record the target that was live *at this frame's
                        # timestamp*, not whatever the console reached later.
                        control_context = self.gripper.pwm_context_at(int(frame.host_received_ns))
                    self.trial.record_frame(
                        frame,
                        sensor_identity=self.sensor_identity(),
                        assessment=(
                            self.last_assessment.to_dict()
                            if self.last_assessment is not None
                            else None
                        ),
                        sensor_profile=config.sensor_profile if config is not None else None,
                        control_context=control_context,
                    )
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

    def _append_timeline_point(self, frame: TactileFrame) -> None:
        """Keep a compact FSR_A raw-count point for the unified timeline."""
        config = self.sensor_configuration()
        if config is None:
            return
        fsr = config.fsr_channels
        if not fsr:
            return
        ids = frame.channel_ids or config.channel_ids
        try:
            index = list(ids).index(fsr[0].channel_id)
        except ValueError:
            return
        channels = frame.channels
        mask = frame.valid_mask
        value = channels[index] if index < len(channels) else None
        valid = bool(mask[index]) if index < len(mask) else False
        self.fsr_timeline.append(
            {
                "ns": int(frame.host_received_ns),
                "seq": frame.frame_seq,
                "raw": None if not valid or value is None else float(value),
                "valid": valid,
                "received_utc": frame.host_received_utc,
            }
        )

    def _latch_auto_sensor_fault(self, reason: str) -> None:
        """Invalid/offline sensor data must stop AUTO decisions, never tighten."""
        if self.mode is not Mode.AUTO:
            return
        self.mode = Mode.FAULT
        self.fault_reason = f"sensor data unavailable in AUTO: {reason}"
        self._system("AUTO_SENSOR_FAULT", self.fault_reason)

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
            if getattr(anomaly, "kind", None) == "DEVICE_RESTART":
                self.contact_assessor.clear_baseline()
                self.last_assessment = None
                self.fsr_history.clear()

    # -- trials ------------------------------------------------------------

    def create_trial(
        self,
        name: str,
        *,
        conditions: dict | None = None,
        notes: str = "",
        operator: str | None = None,
        video_path: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            if self.source is DataSource.REPLAY:
                raise ControlDenied("REPLAY is read-only; it cannot create a trial")
            if self.trial is not None and self.trial.recording:
                raise ControlDenied("a trial is already recording")
            environment = environment_snapshot()
            environment["software_version"] = SOFTWARE_VERSION
            # A new Trial must not inherit a PWM command from an earlier
            # session/run; keep the per-frame trace unambiguous.  In log-follow
            # mode the console's latest ACKed target is re-attached explicitly
            # below from the monitor state, never from a stale cached value.
            self.last_pwm_command = None
            if self.log_follow:
                self._sync_monitor_pwm_context()
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
                        "sensor_profile": self.sensor.channel_config.sensor_profile,
                        "fsr_channel_ids": [c.channel_id for c in self.sensor.channel_config.fsr_channels],
                        "fsr_layout": [
                            {"channel_id": c.channel_id, "name": c.name,
                             "adc_id": c.ads1220_id, "adc_input": c.adc_input}
                            for c in self.sensor.channel_config.fsr_channels
                        ],
                    }
                    if self.sensor is not None and self.sensor.channel_config is not None
                    else None
                ),
                "auto_available": self.auto_available()[0],
                "auto_real_enabled": AUTO_REAL_ENABLED,
                "device_identities": self.device_identities(),
                "fsr_baseline": {
                    "ready": self.contact_assessor.baseline_ready,
                    "values": self.contact_assessor.baseline,
                    "thresholds": self.contact_assessor.thresholds.to_dict(),
                },
                "fsr_thresholds": self.contact_assessor.thresholds.to_dict(),
                "monitor": (
                    self.gripper.monitor_snapshot()
                    if self.gripper is not None and hasattr(self.gripper, "monitor_snapshot")
                    else None
                ),
            }
            self.trial = self.trial_store.create_trial(
                name,
                mode=self.mode.value,
                conditions=conditions,
                parameters=parameters,
                notes=notes,
                git_commit=environment["git_commit"],
                video_path=video_path,
                operator=operator,
                tags=tags,
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

    def drain_log_follow(
        self,
        *,
        quiet_rounds: int = 2,
        max_seconds: float = 3.0,
        sleep_s: float = 0.05,
    ) -> int:
        """Read JSONL lines that were written before shutdown, then stop.

        The console/FSR collectors flush their last lines just before exiting.
        Stopping the Trial immediately would leave those frames or PWM events
        out of ``frames.jsonl``/``events.jsonl`` and therefore out of the CSV
        and REPLAY exports.  This drains until two consecutive rounds add
        nothing, bounded by ``max_seconds`` so shutdown cannot hang.
        """
        if not self.log_follow:
            return 0
        deadline = time.monotonic() + max(0.0, max_seconds)
        stable = 0
        rounds = 0
        while time.monotonic() < deadline:
            before = (
                self.frames_received,
                len(self.events),
                self.event_overflow_count,
                self.trial.frame_count if self.trial is not None else -1,
                self.trial.event_count if self.trial is not None else -1,
            )
            try:
                self.tick()
            except Exception as exc:  # shutdown must still export what it has
                self.last_sensor_error = f"shutdown drain failed: {exc}"
                break
            after = (
                self.frames_received,
                len(self.events),
                self.event_overflow_count,
                self.trial.frame_count if self.trial is not None else -1,
                self.trial.event_count if self.trial is not None else -1,
            )
            rounds += 1
            if after == before:
                stable += 1
            else:
                stable = 0
            if stable >= max(1, quiet_rounds):
                break
            time.sleep(max(0.0, sleep_s))
        return rounds

    def finish_log_follow_trial(self, reason: str = "monitor shutdown") -> dict[str, Any] | None:
        """Drain remaining log lines, then stop and export the recording Trial.

        Returns ``None`` when no Trial is recording.  Export happens only after
        the drain, so the CSV/REPLAY include the final console/FSR records.
        """
        with self._lock:
            if self.trial is None or not self.trial.recording:
                return None
            self.drain_log_follow()
            directory = str(self.trial.directory)
            metadata = self.stop_trial(reason)
            trial_id = metadata["trial_id"]
            csv_path = self.trial_store.export_csv(trial_id)
            replay_path = self.trial_store.export_replay_jsonl(trial_id)
            return {
                "trial_id": trial_id,
                "directory": directory,
                "csv": str(csv_path),
                "replay": str(replay_path),
                "counts": metadata.get("counts") or {},
                "status": "COMPLETED",
            }

    def set_trial_video(self, path: str | None) -> dict[str, Any]:
        with self._lock:
            if self.trial is None:
                raise ControlDenied("no active trial")
            metadata = self.trial.set_video_path(path)
            self._system("TRIAL_VIDEO", f"video path set to {path or 'NONE'}")
            return metadata.to_dict()

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
            # In log-follow mode, read the console log BEFORE the FSR log so a
            # frame is attributed to a PWM command that was written earlier in
            # the same tick window.  (A serial poll still happens at the end.)
            if self.log_follow and self.gripper is not None and self.gripper.connected:
                try:
                    self.gripper.poll()
                except Exception as exc:
                    self.mode = Mode.FAULT
                    self.fault_reason = f"console log read failed: {exc}"
            # A log-follow monitor turns console outcomes into normal control
            # events so the same Trial recorder, CSV and replay paths apply.
            if self.gripper is not None and hasattr(self.gripper, "drain_control_events"):
                for event in self.gripper.drain_control_events():
                    self._append(event)
                self._sync_monitor_pwm_context()
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

    def _sync_monitor_pwm_context(self) -> None:
        """Mirror the console's ACKed target as *record context*, never a command.

        Frames carry ``pwm_target_us``; after STOP/DISARM or a lost ACK the
        context is cleared so a stale target is not attributed to new frames.
        """
        if not self.log_follow or self.gripper is None:
            return
        try:
            monitor = self.gripper.monitor_snapshot()
        except Exception:
            return
        target = monitor.get("current_target")
        status = monitor.get("target_status")
        if (
            target
            and isinstance(target.get("pulse_us"), int)
            and status in ("ACKED", "ACKED_UNKNOWN_OUTPUT", "ACK_STALE")
        ):
            self.last_pwm_command = {
                "command_id": target.get("command_id"),
                "target_pwm_us": target["pulse_us"],
                "acknowledged": status == "ACKED",
                "stage": "DEVICE_ACK" if status == "ACKED" else status,
                "source": "PWM_CONSOLE_LOG",
            }
        else:
            self.last_pwm_command = None

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
            freshness_ns = None
            if sensor_status.get("last_host_received_ns"):
                freshness_ns = max(0, self.clock_ns() - int(sensor_status["last_host_received_ns"]))
            monitor = None
            if self.gripper is not None and hasattr(self.gripper, "monitor_snapshot"):
                try:
                    monitor = self.gripper.monitor_snapshot()
                except Exception:
                    monitor = None
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
                "sensor_config": (
                    self.sensor.channel_config.to_dict()
                    if self.sensor is not None and self.sensor.channel_config is not None
                    else None
                ),
                "fsr_assessment": (
                    self.last_assessment.to_dict() if self.last_assessment is not None else None
                ),
                "fsr_history": list(self.fsr_history),
                "baseline_ready": self.contact_assessor.baseline_ready,
                "device_identities": self.device_identities(),
                "auto_real_enabled": AUTO_REAL_ENABLED,
                "auto_commissioning_requested": self.real_auto_commissioning_requested,
                "last_auto_decision": (
                    self.last_auto_decision.to_dict() if self.last_auto_decision is not None else None
                ),
                "frames_received": self.frames_received,
                "last_sensor_error": self.last_sensor_error,
                "apply_enabled": denial is None,
                "apply_denial": denial,
                "stop_enabled": bool(
                    self.gripper is not None
                    and self.gripper.connected
                    and self.source is not DataSource.REPLAY
                    and not getattr(self.gripper, "read_only", False)
                ),
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
                "sensor_freshness_ns": freshness_ns,
                "sensor_sample_rate_hz": sensor_status.get("sample_rate_hz"),
                "sensor_reconnect_count": (sensor_status.get("detail") or {}).get("reconnect_count", 0),
                "sensor_reconnect_attempts": (sensor_status.get("detail") or {}).get("reconnect_attempts", 0),
                "sensor_oversize_lines": (sensor_status.get("detail") or {}).get("oversize_lines", 0),
                "event_overflow_count": self.event_overflow_count,
                "log_follow": self.log_follow,
                "monitor": monitor,
                "fsr_timeline": self._timeline_points(),
            }

    def _timeline_points(self, limit: int = 1800) -> list[dict[str, Any]]:
        items = list(self.fsr_timeline)
        if not items:
            return []
        if len(items) <= limit:
            return items
        step = max(1, len(items) // limit)
        sampled = items[::step]
        if sampled[-1] is not items[-1]:
            sampled.append(items[-1])
        return sampled


def build_core(
    *,
    source: DataSource | str = DataSource.SIMULATION,
    root: Path | str = PROJECT_ROOT,
    config_path: Path | str | None = None,
    hardware_permission: bool = False,
    port: str | None = None,
    connect: bool = False,
    sensor_file: Path | str | None = None,
    firmware_fixture: str | None = None,
    sensor_port: str | None = None,
    sensor_baud: int | None = None,
    sensor_config_path: Path | str | None = None,
    connect_sensor: bool = False,
    follow_pwm_log: Path | str | None = None,
    follow_fsr_log: Path | str | None = None,
) -> ApplicationCore:
    source = parse_source(source)
    if follow_pwm_log is not None or follow_fsr_log is not None:
        if source is not DataSource.LIVE:
            raise ControlDenied("log-follow monitoring requires --source LIVE")
        if port is not None or sensor_port is not None or firmware_fixture is not None:
            raise ControlDenied("log-follow monitoring cannot also open a serial port")
        from ..devices.log_follow import LogFollowGripper, LogFollowSensorAdapter

        gripper = (
            LogFollowGripper(follow_pwm_log, config_path=config_path)
            if follow_pwm_log is not None
            else None
        )
        sensor = LogFollowSensorAdapter(follow_fsr_log) if follow_fsr_log is not None else None
        core = ApplicationCore(root=root, source=source, gripper=gripper, sensor=sensor)
        if gripper is not None:
            core.connect_gripper()
        if sensor is not None:
            core.connect_sensor()
        return core
    gripper = None
    if source is not DataSource.REPLAY:
        gripper = GripperAdapter(
            source=source,
            config_path=config_path,
            hardware_permission=hardware_permission,
        )
    sensor = None
    if firmware_fixture is not None:
        if source is not DataSource.SIMULATION or sensor_file is not None or sensor_port is not None:
            raise ControlDenied("firmware fixtures require the offline SIMULATION source")
        sensor = firmware_fixture_adapter(firmware_fixture)
    elif sensor_file is not None:
        if source is not DataSource.REPLAY:
            raise ControlDenied("sensor_file replay requires --source REPLAY")
        sensor = ReplaySensorAdapter(sensor_file)
    elif source is DataSource.LIVE and (sensor_port is not None or sensor_config_path is not None):
        sensor_config = SerialSensorConfig.from_file(sensor_config_path).with_port(
            sensor_port,
            sensor_baud,
        )
        sensor = serial_sensor_adapter(sensor_config)
    core = ApplicationCore(root=root, source=source, gripper=gripper, sensor=sensor)
    if connect:
        if source is DataSource.REPLAY:
            raise ControlDenied("REPLAY cannot connect a gripper")
        core.connect_gripper(port)
        core.begin_manual_session()
    if connect_sensor or firmware_fixture is not None or sensor_file is not None:
        core.connect_sensor()
    return core
