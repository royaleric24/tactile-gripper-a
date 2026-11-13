"""Single-channel tactile processing for cup-grasp control."""
from __future__ import annotations

import math
import statistics
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, Optional

from .model import SAT_HIGH, SAT_LOW, TactileConfig

FLAG_SAT_HIGH = 0x01
FLAG_SAT_LOW = 0x02
FLAG_NEAR_RAIL = 0x08
FLAG_NO_DATA = 0x20


@dataclass
class TactileSample:
    host_monotonic_ns: int
    device_timestamp_us: int
    frame_seq: int
    raw: Optional[int]
    filtered: Optional[float]
    baseline: Optional[float]
    baseline_std: Optional[float]
    delta: Optional[float]
    valid: bool
    usable: bool
    saturated: bool
    saturation_fraction: float
    flags: int
    baseline_ready: bool


class TactileProcessor:
    def __init__(self, config: TactileConfig) -> None:
        self.config = config
        self.baseline_values: Deque[int] = deque(maxlen=max(2, config.baseline_samples))
        self.saturation_window: Deque[bool] = deque(maxlen=max(2, config.saturation_window))
        self.filtered: Optional[float] = None
        self.baseline: Optional[float] = None
        self.baseline_std: Optional[float] = None
        self.last_valid_ns: Optional[int] = None
        self.baseline_ready = False

    def update(self, frame, now_ns: Optional[int] = None) -> TactileSample:
        now_ns = now_ns if now_ns is not None else int(getattr(frame, "host_monotonic_ns", 0) or 0)
        channel = self.config.channel
        raw = frame.raw_adc[channel]
        flag = int(frame.channel_flags[channel])
        valid = bool(frame.valid[channel]) and raw is not None
        saturated = bool(flag & (FLAG_SAT_HIGH | FLAG_SAT_LOW | FLAG_NEAR_RAIL)) or (
            raw is not None and (raw >= SAT_HIGH or raw <= SAT_LOW))
        self.saturation_window.append(bool(saturated))
        saturation_fraction = (
            sum(1 for item in self.saturation_window if item) / len(self.saturation_window)
            if self.saturation_window else 1.0
        )
        if valid and not saturated:
            self.last_valid_ns = now_ns
            if not self.baseline_ready:
                self.baseline_values.append(int(raw))
                if len(self.baseline_values) >= max(2, self.config.baseline_samples):
                    values = list(self.baseline_values)
                    self.baseline = statistics.mean(values)
                    self.baseline_std = statistics.pstdev(values) if len(values) > 1 else 0.0
                    self.baseline_ready = True
                    self.filtered = float(raw)
            else:
                alpha = self.config.ema_alpha
                self.filtered = (alpha * float(raw) + (1.0 - alpha) * self.filtered) if self.filtered is not None else float(raw)
        delta = (self.filtered - self.baseline) if self.filtered is not None and self.baseline is not None else None
        usable = bool(valid and not saturated and self.baseline_ready
                      and saturation_fraction <= self.config.max_saturation_fraction)
        return TactileSample(
            host_monotonic_ns=now_ns,
            device_timestamp_us=int(getattr(frame, "timestamp_us", 0)),
            frame_seq=int(getattr(frame, "frame_seq", 0)),
            raw=raw,
            filtered=self.filtered,
            baseline=self.baseline,
            baseline_std=self.baseline_std,
            delta=delta,
            valid=bool(valid),
            usable=usable,
            saturated=bool(saturated),
            saturation_fraction=saturation_fraction,
            flags=flag,
            baseline_ready=self.baseline_ready,
        )

    def sensor_ok(self, now_ns: int) -> bool:
        if not self.baseline_ready or self.last_valid_ns is None:
            return False
        if (now_ns - self.last_valid_ns) / 1_000_000.0 > self.config.sensor_timeout_ms:
            return False
        if self.saturation_window:
            fraction = sum(1 for item in self.saturation_window if item) / len(self.saturation_window)
            if fraction > self.config.max_saturation_fraction:
                return False
        return True


class SimulatedTactileSource:
    """SIMULATED source for software tests; never written as real data."""

    def __init__(self, baseline: int = 1000, contact_delta: int = 700, contact_at_ns: int = 2_000_000_000):
        self.baseline = baseline
        self.contact_delta = contact_delta
        self.contact_at_ns = contact_at_ns
        self.seq = 0
        self.start_ns: Optional[int] = None

    def make(self, now_ns: int):
        if self.start_ns is None:
            self.start_ns = now_ns
        self.seq += 1
        delta = self.contact_delta if now_ns - self.start_ns >= self.contact_at_ns else 0
        value = self.baseline + delta
        class Frame:
            pass
        frame = Frame()
        frame.raw_adc = tuple(value if i == 0 else 0 for i in range(12))
        frame.valid = tuple(True for _ in range(12))
        frame.channel_flags = tuple(0 for _ in range(12))
        frame.timestamp_us = int((now_ns - self.start_ns) / 1000)
        frame.frame_seq = self.seq
        frame.host_monotonic_ns = now_ns
        return frame
