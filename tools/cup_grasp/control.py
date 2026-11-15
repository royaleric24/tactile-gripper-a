"""Fixed-clamp and tactile-feedback finite state controllers.

Commands are pulse-width targets, never measured force/position.  The feedback
FSM stops (FAULT) on invalid/timeout/saturation and never auto-recovers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Protocol

from .model import CupGraspConfig
from .tactile import TactileSample


class CupState(str, Enum):
    OPEN = "OPEN"
    APPROACH = "APPROACH"
    CONTACT = "CONTACT"
    HOLD = "HOLD"
    ADJUST = "ADJUST"
    RELEASE = "RELEASE"
    FAULT = "FAULT"
    DONE = "DONE"


class GripperPort(Protocol):
    def command_pulse(self, pulse_us: int, reason: str) -> None: ...
    def stop(self, reason: str) -> None: ...
    def state(self) -> str: ...


class FakeCupGripper:
    """SIMULATED gripper for tests/dry-run; no hardware."""
    def __init__(self) -> None:
        self.commands: List[Dict] = []
        self._state = "DISARMED"

    def command_pulse(self, pulse_us: int, reason: str) -> None:
        self.commands.append({"kind": "PULSE", "pulse_us": int(pulse_us), "reason": reason})
        self._state = "ACTIVE"

    def stop(self, reason: str) -> None:
        self.commands.append({"kind": "STOP", "reason": reason})
        self._state = "DISARMED"

    def state(self) -> str:
        return self._state


@dataclass
class ControlEvent:
    host_monotonic_ns: int
    state: str
    pulse_us: Optional[int]
    reason: str
    sample: Optional[TactileSample] = None


class FixedClampMode:
    def __init__(self, config: CupGraspConfig, gripper: GripperPort) -> None:
        config.require_gripper()
        self.config = config
        self.gripper = gripper
        self.state = CupState.OPEN
        self.pulse: Optional[int] = None
        self.events: List[ControlEvent] = []

    def start(self, now_ns: int) -> None:
        g = self.config.gripper
        self._command(g.open_pulse_us, "open_before_clamp", now_ns)
        self._command(g.fixed_pulse_us, "fixed_clamp", now_ns)
        self.state = CupState.HOLD

    def _command(self, pulse: int, reason: str, now_ns: int) -> None:
        self.pulse = int(pulse)
        self.gripper.command_pulse(self.pulse, reason)
        self.events.append(ControlEvent(now_ns, self.state.value, self.pulse, reason))

    def stop(self, now_ns: int, reason: str = "user_stop") -> None:
        self.gripper.stop(reason)
        self.state = CupState.DONE
        self.events.append(ControlEvent(now_ns, self.state.value, None, reason))


class TactileFeedbackFSM:
    def __init__(self, config: CupGraspConfig, gripper: GripperPort) -> None:
        config.require_gripper()
        config.require_tactile_thresholds()
        self.config = config
        self.gripper = gripper
        self.state = CupState.OPEN
        self.pulse = config.gripper.open_pulse_us
        self.steps = 0
        self.contact_frames = 0
        self.release_frames = 0
        self.events: List[ControlEvent] = []
        self.fault_reason: Optional[str] = None
        self.last_sample: Optional[TactileSample] = None
        self.last_step_ns: Optional[int] = None

    def _emit(self, now_ns: int, reason: str, sample: Optional[TactileSample] = None) -> None:
        self.events.append(ControlEvent(now_ns, self.state.value, self.pulse, reason, sample))

    def _command(self, pulse: int, reason: str, now_ns: int, sample: Optional[TactileSample] = None) -> None:
        self.pulse = int(pulse)
        self.gripper.command_pulse(self.pulse, reason)
        self._emit(now_ns, reason, sample)

    def _fault(self, now_ns: int, reason: str) -> None:
        self.state = CupState.FAULT
        self.fault_reason = reason
        self.gripper.stop(reason)
        self._emit(now_ns, reason)

    def start(self, now_ns: int) -> None:
        self._command(self.pulse, "open", now_ns)
        self.state = CupState.APPROACH
        self._emit(now_ns, "approach")

    def at_limit(self) -> bool:
        g = self.config.gripper
        if self.pulse is None or self.steps >= g.max_steps:
            return True
        next_pulse = self.pulse + g.close_direction * g.step_us
        return not (g.min_pulse_us <= next_pulse <= g.max_pulse_us)

    def can_step(self, now_ns: int) -> bool:
        g = self.config.gripper
        return self.last_step_ns is None or (now_ns - self.last_step_ns) / 1_000_000.0 >= g.step_interval_ms

    def step_toward_close(self, now_ns: int, reason: str) -> bool:
        g = self.config.gripper
        if self.pulse is None or self.at_limit() or not self.can_step(now_ns):
            return False
        next_pulse = self.pulse + g.close_direction * g.step_us
        self.steps += 1
        self.last_step_ns = now_ns
        self._command(next_pulse, reason, now_ns)
        return True

    def update(self, sample: TactileSample, now_ns: int, sensor_ok: bool) -> None:
        self.last_sample = sample
        if self.state in (CupState.FAULT, CupState.DONE, CupState.RELEASE):
            return
        # Wait for the local baseline before judging contact validity.
        if not sample.baseline_ready:
            return
        if not sensor_ok or not sample.usable or sample.delta is None:
            self._fault(now_ns, "NO_VALID_TACTILE")
            return
        delta = sample.delta
        contact = self.config.tactile.contact_delta_counts
        release = self.config.tactile.release_delta_counts
        confirm = self.config.tactile.confirmation_frames
        if self.state == CupState.APPROACH:
            if delta >= contact:
                self.contact_frames += 1
                if self.contact_frames >= confirm:
                    self.state = CupState.CONTACT
                    self._emit(now_ns, "contact_confirmed", sample)
                    self.state = CupState.HOLD
                    self._emit(now_ns, "hold", sample)
            else:
                self.contact_frames = 0
                if self.at_limit():
                    self._fault(now_ns, "NO_CONTACT_WITHIN_LIMITS")
                else:
                    self.step_toward_close(now_ns, "approach_step")
        elif self.state == CupState.HOLD:
            if delta < release:
                self.release_frames += 1
                if self.release_frames >= confirm:
                    self.state = CupState.ADJUST
                    if self.at_limit():
                        self._fault(now_ns, "CONTACT_LOSS_NO_ADJUST")
                    elif self.step_toward_close(now_ns, "contact_loss_adjust"):
                        self.state = CupState.HOLD
                        self._emit(now_ns, "adjusted_hold", sample)
                    else:
                        # waiting for the step interval: remain in HOLD without fault
                        self.state = CupState.HOLD
            else:
                self.release_frames = 0
        elif self.state == CupState.ADJUST:
            self.state = CupState.HOLD

    def tick(self, now_ns: int, sensor_ok: bool) -> None:
        if self.state in (CupState.FAULT, CupState.DONE, CupState.RELEASE):
            return
        if self.last_sample is None or not self.last_sample.baseline_ready:
            return
        if not sensor_ok:
            self._fault(now_ns, "TACTILE_TIMEOUT")

    def release(self, now_ns: int, reason: str = "user_release") -> None:
        if self.state == CupState.FAULT:
            return
        g = self.config.gripper
        if g.release_pulse_us is not None:
            self._command(g.release_pulse_us, reason, now_ns)
        else:
            self.gripper.stop(reason)
            self._emit(now_ns, reason)
        self.state = CupState.RELEASE

    def stop(self, now_ns: int, reason: str = "user_stop") -> None:
        self.gripper.stop(reason)
        self.state = CupState.DONE
        self._emit(now_ns, reason)


def summarize_control(mode: FixedClampMode | TactileFeedbackFSM) -> Dict:
    events = [{"host_monotonic_ns": e.host_monotonic_ns, "state": e.state,
               "pulse_us": e.pulse_us, "reason": e.reason} for e in mode.events]
    return {"state": mode.state.value, "pulse_us": mode.pulse, "events": events,
            "fault_reason": getattr(mode, "fault_reason", None)}
