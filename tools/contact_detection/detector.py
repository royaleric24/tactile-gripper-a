"""Adaptive single-point contact detector with hysteresis and quality flags."""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from .config import DetectorConfig

RELEASE = "RELEASE"
CONTACT = "CONTACT"
UNKNOWN = "UNKNOWN"
CALIBRATING = "CALIBRATING"

QUALITY_VERIFIED = "VERIFIED"
QUALITY_UNVERIFIED = "UNVERIFIED"
QUALITY_INVALID = "INVALID"


@dataclass
class DetectorState:
    state: str = CALIBRATING
    quality: str = QUALITY_UNVERIFIED
    filtered: Optional[float] = None
    baseline: Optional[float] = None
    drop_counts: Optional[float] = None
    drop_volts: Optional[float] = None
    contact_count: int = 0
    release_count: int = 0
    last_sample_monotonic_ns: Optional[int] = None
    last_state_change_ns: Optional[int] = None
    last_contact_ns: Optional[int] = None
    last_release_ns: Optional[int] = None
    reason: str = "awaiting_baseline"
    baseline_samples: int = 0
    contact_candidate: bool = False
    control_eligible: bool = False
    config: DetectorConfig = field(default_factory=DetectorConfig)


class ContactDetector:
    def __init__(self, config: Optional[DetectorConfig] = None):
        self.config = config or DetectorConfig()
        self.state = DetectorState(config=self.config, reason="awaiting_baseline")
        self._baseline_values = []
        self._events = []

    def recalibrate(self, now_ns: int, reason: str = "user_recalibrate") -> None:
        self._baseline_values.clear()
        self.state.baseline = None
        self.state.baseline_samples = 0
        self.state.filtered = None
        self.state.contact_count = 0
        self.state.release_count = 0
        self.state.contact_candidate = False
        self.state.control_eligible = False
        self._set_state(CALIBRATING, now_ns, reason)
        self.state.quality = QUALITY_UNVERIFIED

    def _event(self, now_ns: int, kind: str, **fields) -> None:
        event = {"host_monotonic_ns": now_ns, "kind": kind, "state": self.state.state,
                 "quality": self.state.quality, "baseline": self.state.baseline,
                 "filtered": self.state.filtered, "drop_counts": self.state.drop_counts,
                 "drop_volts": self.state.drop_volts}
        event.update(fields)
        self._events.append(event)

    def _set_state(self, new_state: str, now_ns: int, reason: str) -> None:
        if new_state == self.state.state:
            return
        old = self.state.state
        self.state.state = new_state
        self.state.reason = reason
        self.state.last_state_change_ns = now_ns
        if new_state == CONTACT:
            self.state.last_contact_ns = now_ns
        if new_state == RELEASE:
            self.state.last_release_ns = now_ns
        self._event(now_ns, "STATE_CHANGE", from_state=old, to_state=new_state, reason=reason)

    def _quality(self, sample: Dict[str, Any]) -> str:
        if not sample.get("read_ok") or not sample.get("ready"):
            return QUALITY_INVALID
        if not (sample.get("restored_before_cs") is True and sample.get("post_cs_high") is True):
            return QUALITY_UNVERIFIED
        return QUALITY_VERIFIED

    def update(self, sample: Dict[str, Any], now_ns: Optional[int] = None) -> Dict[str, Any]:
        now_ns = now_ns if now_ns is not None else int(sample.get("host_monotonic_ns") or 0)
        self.state.last_sample_monotonic_ns = now_ns
        if sample.get("read_ok") is not True or sample.get("ready") is not True or not isinstance(sample.get("counts"), int):
            self.state.quality = QUALITY_INVALID
            self.state.contact_candidate = False
            self.state.control_eligible = False
            self._set_state(UNKNOWN, now_ns, "invalid_or_timeout_sample")
            self.state.reason = "invalid_or_timeout_sample"
            return self.snapshot()
        counts = float(sample["counts"])
        quality = self._quality(sample)
        self.state.quality = quality
        self.state.filtered = counts if self.state.filtered is None else (
            self.config.ema_alpha * counts + (1.0 - self.config.ema_alpha) * self.state.filtered)
        if not self._baseline_values or self.state.baseline is None:
            self._baseline_values.append(counts)
            if len(self._baseline_values) >= self.config.baseline_frames:
                self.state.baseline = statistics.mean(self._baseline_values)
                self.state.baseline_samples = len(self._baseline_values)
                self._set_state(RELEASE, now_ns, "baseline_ready")
                self._event(now_ns, "BASELINE_READY", baseline=self.state.baseline,
                            frames=self.state.baseline_samples)
            else:
                self.state.baseline_samples = len(self._baseline_values)
                self.state.reason = "calibrating"
                return self.snapshot()
        baseline = self.state.baseline
        if baseline is None:
            return self.snapshot()
        drop = baseline - self.state.filtered
        self.state.drop_counts = drop
        self.state.drop_volts = drop / self.config.counts_per_volt
        contact_threshold = self.config.contact_drop_counts
        release_threshold = contact_threshold - self.config.release_span_counts
        if drop >= contact_threshold:
            self.state.contact_count += 1
            self.state.release_count = 0
        else:
            self.state.contact_count = 0
        if drop <= release_threshold:
            self.state.release_count += 1
        else:
            self.state.release_count = 0
        if self.state.state in (CALIBRATING, RELEASE, UNKNOWN) and self.state.contact_count >= self.config.contact_confirm_frames:
            self.state.contact_candidate = True
            self._set_state(CONTACT, now_ns, "drop_threshold_confirmed")
            self._event(now_ns, "CONTACT_CANDIDATE", verified=(quality == QUALITY_VERIFIED))
        elif self.state.state in (CONTACT, UNKNOWN) and self.state.release_count >= self.config.release_confirm_frames:
            self.state.contact_candidate = False
            self._set_state(RELEASE, now_ns, "recover_threshold_confirmed")
            self._event(now_ns, "RELEASE_CONFIRMED", verified=(quality == QUALITY_VERIFIED))
        elif self.state.state == RELEASE and self.state.contact_count == 0:
            # Slow adaptive baseline only while no contact is present.
            self.state.baseline = (1.0 - self.config.baseline_adapt_alpha) * baseline + \
                                  self.config.baseline_adapt_alpha * counts
            self.state.baseline_samples += 1
        self.state.control_eligible = (self.state.state == CONTACT and quality == QUALITY_VERIFIED
                                       and self.state.contact_candidate)
        return self.snapshot()

    def force_unknown(self, now_ns: int, reason: str) -> Dict[str, Any]:
        self.state.quality = QUALITY_INVALID
        self.state.contact_candidate = False
        self.state.control_eligible = False
        self._set_state(UNKNOWN, now_ns, reason)
        self.state.reason = reason
        return self.snapshot()

    def tick(self, now_ns: int) -> Dict[str, Any]:
        if self.state.last_sample_monotonic_ns is None:
            return self.snapshot()
        if (now_ns - self.state.last_sample_monotonic_ns) / 1e9 > self.config.unknown_timeout_s:
            self.state.quality = QUALITY_INVALID
            self.state.contact_candidate = False
            self.state.control_eligible = False
            self._set_state(UNKNOWN, now_ns, "sample_timeout")
            self.state.reason = "sample_timeout"
        return self.snapshot()

    def drain_events(self) -> list:
        events, self._events = self._events, []
        return events

    def snapshot(self) -> Dict[str, Any]:
        s = self.state
        return {
            "state": s.state,
            "quality": s.quality,
            "reason": s.reason,
            "filtered_counts": s.filtered,
            "baseline_counts": s.baseline,
            "drop_counts": s.drop_counts,
            "drop_volts": s.drop_volts,
            "contact_threshold_counts": self.config.contact_drop_counts,
            "release_threshold_counts": self.config.contact_drop_counts - self.config.release_span_counts,
            "contact_threshold_v": self.config.contact_drop_v,
            "release_recover_v": self.config.release_recover_v,
            "contact_confirm_frames": self.config.contact_confirm_frames,
            "release_confirm_frames": self.config.release_confirm_frames,
            "baseline_samples": s.baseline_samples,
            "last_contact_ns": s.last_contact_ns,
            "last_release_ns": s.last_release_ns,
            "last_state_change_ns": s.last_state_change_ns,
            "control_eligible": s.control_eligible,
            "config": {
                "avdd_mv": self.config.avdd_mv,
                "baseline_frames": self.config.baseline_frames,
                "ema_alpha": self.config.ema_alpha,
                "contact_drop_v": self.config.contact_drop_v,
                "release_recover_v": self.config.release_recover_v,
                "contact_confirm_frames": self.config.contact_confirm_frames,
                "release_confirm_frames": self.config.release_confirm_frames,
                "unknown_timeout_s": self.config.unknown_timeout_s,
            },
        }
