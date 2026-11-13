"""Rule-based AUTO policy framework (offline/simulation only).

This is deliberately NOT connected to a real gripper.  A real AUTO session is
gated on a confirmed sensor protocol, real sensor data, PWM/mechanical limits
and calibration.  The tests use synthetic frames to validate stale-data,
invalid-channel, contact-stop and step-limit behavior.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from ..errors import ControlDenied
from ..models import TactileFrame
from ..sources import DataSource, parse_source

# Hard switch for V1.0: real AUTO remains disabled even if a future gate would
# otherwise be satisfiable.  Do not flip without measured sensor/PWM validation.
AUTO_REAL_ENABLED = False


@dataclass(frozen=True)
class AutoGate:
    source: DataSource = DataSource.SIMULATION
    real_sensor: bool = False
    calibration_confirmed: bool = False
    hardware_armed: bool = False
    protocol_confirmed: bool = False
    allow_simulation: bool = False

    def evaluate(self) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        if self.source is DataSource.SIMULATION and self.allow_simulation:
            return True, []
        if self.source is not DataSource.LIVE:
            reasons.append("AUTO 真实闭环只允许 LIVE 来源")
        if not self.real_sensor:
            reasons.append("真实传感器未连接/未确认")
        if not self.protocol_confirmed:
            reasons.append("传感器协议未确认（PROPOSED v0.1）")
        if not self.calibration_confirmed:
            reasons.append("PWM/触觉标定未确认")
        if not self.hardware_armed:
            reasons.append("真实硬件未授权/未 ARM")
        return False, reasons


@dataclass(frozen=True)
class AutoLimits:
    stale_after_ms: int = 200
    min_valid_channels: int = 1
    contact_threshold: float | None = None
    step_us: int = 20
    min_interval_ms: int = 100
    max_steps: int = 10
    max_total_us: int = 100

    def __post_init__(self) -> None:
        for name in ("stale_after_ms", "min_valid_channels", "step_us", "min_interval_ms", "max_steps", "max_total_us"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if self.contact_threshold is not None:
            if type(self.contact_threshold) not in (int, float):
                raise ValueError("contact_threshold must be null or number")
            if not 0 <= self.contact_threshold <= 1:
                raise ValueError("contact_threshold must be in [0,1]")
        if self.max_total_us < self.step_us:
            raise ValueError("max_total_us must be >= step_us")


@dataclass(frozen=True)
class AutoDecision:
    action: str
    reason: str
    frame_seq: int | None = None
    host_received_ns: int | None = None
    target_delta_us: int | None = None
    valid_channels: int | None = None
    age_ms: float | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "reason": self.reason,
            "frame_seq": self.frame_seq,
            "host_received_ns": self.host_received_ns,
            "target_delta_us": self.target_delta_us,
            "valid_channels": self.valid_channels,
            "age_ms": self.age_ms,
            "details": self.details,
        }


class RuleBasedAutoPolicy:
    """Deterministic, testable policy; it never sends a command by itself."""

    def __init__(self, limits: AutoLimits, gate: AutoGate | None = None):
        self.limits = limits
        self.gate = gate or AutoGate()
        self.last_step_ns: int | None = None

    def availability(self) -> tuple[bool, list[str]]:
        return self.gate.evaluate()

    def reset(self) -> None:
        self.last_step_ns = None

    def evaluate(
        self,
        frame: TactileFrame | None,
        *,
        now_ns: int,
        target_us: int,
        steps: int,
        total_change_us: int,
        sensor_state: str = "STREAMING",
    ) -> AutoDecision:
        available, reasons = self.availability()
        if not available:
            return AutoDecision("UNAVAILABLE", "AUTO unavailable: " + "; ".join(reasons), details={"reasons": reasons})
        if frame is None:
            return AutoDecision("WAIT", "no sensor frame")
        if sensor_state == "STALE":
            return AutoDecision("FAULT", "sensor stale", frame_seq=frame.frame_seq, host_received_ns=frame.host_received_ns)
        age_ns = max(0, now_ns - frame.host_received_ns)
        age_ms = age_ns / 1_000_000
        if age_ms > self.limits.stale_after_ms:
            return AutoDecision(
                "FAULT",
                "frame older than stale limit",
                frame_seq=frame.frame_seq,
                host_received_ns=frame.host_received_ns,
                age_ms=age_ms,
            )
        if frame.valid_channel_count < self.limits.min_valid_channels:
            return AutoDecision(
                "FAULT",
                "insufficient valid channels",
                frame_seq=frame.frame_seq,
                valid_channels=frame.valid_channel_count,
                age_ms=age_ms,
            )
        if frame.contact_score is None:
            return AutoDecision(
                "FAULT",
                "contact metric missing; no AUTO inference from ADC values",
                frame_seq=frame.frame_seq,
                valid_channels=frame.valid_channel_count,
                age_ms=age_ms,
            )
        if self.limits.contact_threshold is not None and frame.contact_score >= self.limits.contact_threshold:
            return AutoDecision(
                "STOP",
                "contact threshold reached",
                frame_seq=frame.frame_seq,
                valid_channels=frame.valid_channel_count,
                age_ms=age_ms,
                details={"contact_score": frame.contact_score, "threshold": self.limits.contact_threshold},
            )
        if steps >= self.limits.max_steps or total_change_us + self.limits.step_us > self.limits.max_total_us:
            return AutoDecision(
                "STOP",
                "step/total limit reached",
                frame_seq=frame.frame_seq,
                valid_channels=frame.valid_channel_count,
                age_ms=age_ms,
            )
        if self.last_step_ns is not None and (now_ns - self.last_step_ns) < self.limits.min_interval_ms * 1_000_000:
            return AutoDecision(
                "WAIT",
                "rate limit",
                frame_seq=frame.frame_seq,
                valid_channels=frame.valid_channel_count,
                age_ms=age_ms,
            )
        self.last_step_ns = now_ns
        return AutoDecision(
            "STEP",
            "fresh valid frame; one bounded step",
            frame_seq=frame.frame_seq,
            valid_channels=frame.valid_channel_count,
            target_delta_us=self.limits.step_us,
            age_ms=age_ms,
            details={"target_us_before": target_us},
        )


class SimulatedAutoSession:
    """Offline-only session that applies policy decisions to an in-memory target."""

    def __init__(self, policy: RuleBasedAutoPolicy):
        available, reasons = policy.availability()
        if not available:
            raise ControlDenied("AUTO unavailable: " + "; ".join(reasons))
        self.policy = policy
        self.target_us = 0
        self.steps = 0
        self.total_change_us = 0
        self.decisions: list[AutoDecision] = []
        self.state = "RUNNING"

    def step(self, frame: TactileFrame | None, *, now_ns: int | None = None, sensor_state: str = "STREAMING") -> AutoDecision:
        now_ns = time.monotonic_ns() if now_ns is None else now_ns
        decision = self.policy.evaluate(
            frame,
            now_ns=now_ns,
            target_us=self.target_us,
            steps=self.steps,
            total_change_us=self.total_change_us,
            sensor_state=sensor_state,
        )
        self.decisions.append(decision)
        if decision.action == "STEP" and decision.target_delta_us is not None:
            self.target_us += decision.target_delta_us
            self.steps += 1
            self.total_change_us += abs(decision.target_delta_us)
        elif decision.action in ("STOP", "FAULT", "UNAVAILABLE"):
            self.state = decision.action
        return decision
