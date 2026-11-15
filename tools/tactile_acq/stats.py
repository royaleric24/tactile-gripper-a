"""Frame-rate, drop, saturation and channel-quality statistics.

No value is invented: invalid channels are counted as invalid and excluded from
min/max/mean/std.  A fixed channel is reported as FIXED, not as a working
sensor and not as zero contact.
"""
from __future__ import annotations

import csv
import math
import statistics
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from .protocol import (
    ADC_MAX,
    ADC_MIN,
    CHANNEL_COUNT,
    CHANNEL_FLAGS,
    FLAG_STUCK_EXTREME,
    SampleFrame,
    channel_label,
)

NEAR_RAIL_LIMIT = int(ADC_MAX * 0.98)


@dataclass
class ChannelStats:
    index: int
    valid_count: int = 0
    invalid_count: int = 0
    minimum: Optional[int] = None
    maximum: Optional[int] = None
    mean: float = 0.0
    m2: float = 0.0
    unique: Set[int] = field(default_factory=set)
    unique_overflow: bool = False
    sat_high: int = 0
    sat_low: int = 0
    near_rail: int = 0
    negative: int = 0
    stuck_flag_count: int = 0
    flag_counts: Dict[str, int] = field(default_factory=dict)

    def add(self, value: Optional[int], flags: int, is_valid: bool) -> None:
        if not is_valid or value is None:
            self.invalid_count += 1
            return
        self.valid_count += 1
        if self.minimum is None or value < self.minimum:
            self.minimum = value
        if self.maximum is None or value > self.maximum:
            self.maximum = value
        delta = value - self.mean
        self.mean += delta / self.valid_count
        self.m2 += delta * (value - self.mean)
        if len(self.unique) < 8192:
            self.unique.add(value)
        else:
            self.unique_overflow = True
        if value >= ADC_MAX:
            self.sat_high += 1
        if value <= ADC_MIN:
            self.sat_low += 1
        if value > NEAR_RAIL_LIMIT or value < -NEAR_RAIL_LIMIT:
            self.near_rail += 1
        if value < 0:
            self.negative += 1
        for bit, name in CHANNEL_FLAGS.items():
            if flags & bit:
                self.flag_counts[name] = self.flag_counts.get(name, 0) + 1
        if flags & FLAG_STUCK_EXTREME:
            self.stuck_flag_count += 1

    @property
    def std(self) -> Optional[float]:
        if self.valid_count < 2:
            return None
        return math.sqrt(self.m2 / (self.valid_count - 1))

    @property
    def fixed(self) -> bool:
        return self.valid_count > 0 and not self.unique_overflow and len(self.unique) == 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "channel": self.index,
            "label": channel_label(self.index),
            "valid_count": self.valid_count,
            "invalid_count": self.invalid_count,
            "min": self.minimum,
            "max": self.maximum,
            "mean": None if self.valid_count == 0 else round(self.mean, 3),
            "std": None if self.std is None else round(self.std, 2),
            "unique_values": len(self.unique) if not self.unique_overflow else ">8192",
            "fixed": self.fixed,
            "saturated_high": self.sat_high,
            "saturated_low": self.sat_low,
            "near_rail": self.near_rail,
            "negative_single_ended": self.negative,
            "stuck_extreme_flag": self.stuck_flag_count,
            "flag_counts": dict(sorted(self.flag_counts.items())),
        }


@dataclass
class RunStats:
    device_id: Optional[str] = None
    firmware_version: Optional[str] = None
    boot_ids: List[str] = field(default_factory=list)
    samples: int = 0
    first_device_us: Optional[int] = None
    last_device_us: Optional[int] = None
    first_host_ns: Optional[int] = None
    last_host_ns: Optional[int] = None
    first_monotonic_ns: Optional[int] = None
    last_monotonic_ns: Optional[int] = None
    first_seq: Optional[int] = None
    last_seq: Optional[int] = None
    missing_frames: int = 0
    duplicate_frames: int = 0
    out_of_order_frames: int = 0
    boot_changes: int = 0
    malformed_lines: int = 0
    non_sample_messages: int = 0
    host_timeouts: int = 0
    max_host_gap_s: float = 0.0
    host_gaps: List[int] = field(default_factory=list)
    effective_rates: List[float] = field(default_factory=list)
    frame_periods_us: List[int] = field(default_factory=list)
    channels: List[ChannelStats] = field(default_factory=lambda: [ChannelStats(i) for i in range(CHANNEL_COUNT)])
    last_adc_states: List[str] = field(default_factory=lambda: ["UNKNOWN", "UNKNOWN", "UNKNOWN"])
    adc_state_counts: List[Dict[str, int]] = field(default_factory=lambda: [{}, {}, {}])
    reference_mode: Optional[str] = None
    _prev_seq: Optional[int] = None
    _prev_boot: Optional[str] = None
    _prev_host_ns: Optional[int] = None
    _recent_host_deltas: List[int] = field(default_factory=list)

    def add_sample(self, frame: SampleFrame) -> None:
        if self.device_id is None:
            self.device_id = frame.device_id
        if self.firmware_version is None:
            self.firmware_version = frame.firmware_version
        self.reference_mode = frame.reference_mode
        if frame.boot_id not in self.boot_ids:
            self.boot_ids.append(frame.boot_id)
        if self._prev_boot is not None and frame.boot_id != self._prev_boot:
            self.boot_changes += 1
            self._prev_seq = None
        self._prev_boot = frame.boot_id

        if self.samples == 0:
            self.first_device_us = frame.timestamp_us
            self.first_host_ns = frame.host_received_ns
            self.first_monotonic_ns = frame.host_monotonic_ns
            if frame.frame_seq is not None:
                self.first_seq = frame.frame_seq
        self.samples += 1
        self.last_device_us = frame.timestamp_us
        self.last_host_ns = frame.host_received_ns
        self.last_monotonic_ns = frame.host_monotonic_ns
        self.last_seq = frame.frame_seq

        if self._prev_seq is not None:
            delta = frame.frame_seq - self._prev_seq
            if delta == 1:
                pass
            elif delta == 0:
                self.duplicate_frames += 1
            elif delta > 1:
                self.missing_frames += delta - 1
            else:
                self.out_of_order_frames += 1
        self._prev_seq = frame.frame_seq

        if frame.frame_period_us:
            self.frame_periods_us.append(frame.frame_period_us)
        self.effective_rates.append(frame.effective_frame_rate_hz)

        if self._prev_host_ns is not None:
            gap = frame.host_received_ns - self._prev_host_ns
            if gap > 0:
                # Compare this gap with the recent normal cadence *before*
                # adding the gap itself, otherwise one long gap inflates its
                # own threshold.  With too few deltas, a conservative 2 s
                # threshold is used.
                median = statistics.median(self._recent_host_deltas) if len(self._recent_host_deltas) >= 4 else 0
                threshold = max(2.0, 3.0 * median / 1e9) if median else 2.0
                self.host_gaps.append(gap)
                self._recent_host_deltas.append(gap)
                if len(self._recent_host_deltas) > 120:
                    self._recent_host_deltas.pop(0)
                self.max_host_gap_s = max(self.max_host_gap_s, gap / 1e9)
                if gap / 1e9 > threshold:
                    self.host_timeouts += 1
        self._prev_host_ns = frame.host_received_ns

        for index, (value, is_valid) in enumerate(zip(frame.raw_adc, frame.valid)):
            self.channels[index].add(value, frame.channel_flags[index], is_valid)
        for index, status in enumerate(frame.adc_status):
            self.last_adc_states[index] = status.state
            counts = self.adc_state_counts[index]
            counts[status.state] = counts.get(status.state, 0) + 1

    def note_event(self) -> None:
        self.non_sample_messages += 1

    def note_malformed(self) -> None:
        self.malformed_lines += 1

    @property
    def device_frame_rate_hz(self) -> Optional[float]:
        if self.samples < 2 or self.first_device_us is None or self.last_device_us is None:
            return None
        elapsed = self.last_device_us - self.first_device_us
        if elapsed <= 0:
            return None
        return (self.samples - 1) * 1_000_000.0 / elapsed

    @property
    def host_frame_rate_hz(self) -> Optional[float]:
        if self.samples < 2 or self.first_host_ns is None or self.last_host_ns is None:
            return None
        elapsed = self.last_host_ns - self.first_host_ns
        if elapsed <= 0:
            return None
        return (self.samples - 1) * 1e9 / elapsed

    @property
    def mean_effective_rate_hz(self) -> Optional[float]:
        if not self.effective_rates:
            return None
        return sum(self.effective_rates) / len(self.effective_rates)

    @property
    def drop_rate(self) -> Optional[float]:
        if self.samples == 0:
            return None
        expected = self.samples + self.missing_frames
        if expected <= 0:
            return None
        return self.missing_frames / expected

    @property
    def duration_s(self) -> Optional[float]:
        if self.first_host_ns is None or self.last_host_ns is None:
            return None
        return (self.last_host_ns - self.first_host_ns) / 1e9

    @property
    def valid_ratio(self) -> Optional[float]:
        total = sum(item.valid_count + item.invalid_count for item in self.channels)
        if total == 0:
            return None
        return sum(item.valid_count for item in self.channels) / total

    def summary(self) -> Dict[str, Any]:
        channels = [item.to_dict() for item in self.channels]
        return {
            "device_id": self.device_id,
            "firmware_version": self.firmware_version,
            "boot_ids": list(self.boot_ids),
            "samples": self.samples,
            "duration_s": None if self.duration_s is None else round(self.duration_s, 3),
            "device_frame_rate_hz": None if self.device_frame_rate_hz is None else round(self.device_frame_rate_hz, 3),
            "host_frame_rate_hz": None if self.host_frame_rate_hz is None else round(self.host_frame_rate_hz, 3),
            "mean_effective_frame_rate_hz": None if self.mean_effective_rate_hz is None else round(self.mean_effective_rate_hz, 3),
            "min_effective_frame_rate_hz": None if not self.effective_rates else round(min(self.effective_rates), 3),
            "max_effective_frame_rate_hz": None if not self.effective_rates else round(max(self.effective_rates), 3),
            "frame_seq": {
                "first": self.first_seq,
                "last": self.last_seq,
                "missing": self.missing_frames,
                "duplicates": self.duplicate_frames,
                "out_of_order": self.out_of_order_frames,
                "drop_rate": None if self.drop_rate is None else round(self.drop_rate, 6),
                "boot_changes": self.boot_changes,
            },
            "host_timeouts": self.host_timeouts,
            "max_host_gap_s": round(self.max_host_gap_s, 3),
            "malformed_lines": self.malformed_lines,
            "non_sample_messages": self.non_sample_messages,
            "valid_ratio": None if self.valid_ratio is None else round(self.valid_ratio, 6),
            "reference_mode": self.reference_mode,
            "last_adc_states": [
                {"adc": index + 1, "state": state, "counts": self.adc_state_counts[index]}
                for index, state in enumerate(self.last_adc_states)
            ],
            "channels": channels,
            "saturated_channels": [
                item["label"] for item in channels if item["saturated_high"] or item["saturated_low"]
            ],
            "near_rail_channels": [item["label"] for item in channels if item["near_rail"]],
            "fixed_channels": [item["label"] for item in channels if item["fixed"]],
            "invalid_channels": [item["label"] for item in channels if item["invalid_count"] > 0],
        }

    def to_text(self) -> str:
        s = self.summary()
        lines = []
        lines.append("TACTILE RUN SUMMARY")
        lines.append("  device          : {}".format(s["device_id"]))
        lines.append("  firmware        : {}".format(s["firmware_version"]))
        lines.append("  samples         : {}   duration: {} s".format(s["samples"], s["duration_s"]))
        lines.append("  frame rate      : device {} Hz | host {} Hz | firmware mean {} Hz".format(
            s["device_frame_rate_hz"], s["host_frame_rate_hz"], s["mean_effective_frame_rate_hz"]))
        lines.append("  frame seq       : first={} last={} missing={} duplicates={} out_of_order={} drop_rate={}".format(
            s["frame_seq"]["first"], s["frame_seq"]["last"], s["frame_seq"]["missing"],
            s["frame_seq"]["duplicates"], s["frame_seq"]["out_of_order"], s["frame_seq"]["drop_rate"]))
        lines.append("  host timeouts   : {}   max gap: {} s".format(s["host_timeouts"], s["max_host_gap_s"]))
        lines.append("  malformed lines : {}".format(s["malformed_lines"]))
        lines.append("  valid ratio     : {}".format(s["valid_ratio"]))
        lines.append("  ADC states      : {}".format(
            ", ".join("ADC{}={}".format(item["adc"], item["state"]) for item in s["last_adc_states"])))
        lines.append("")
        lines.append("  CH  label       valid   min        max        mean       std      uniq  fixed  sat  flags")
        for item in s["channels"]:
            lines.append(
                "  {:>2}  {:<10} {:>6}  {:>9}  {:>9}  {:>9}  {:>7}  {:>5}  {:<5}  {:<3}  {}".format(
                    item["channel"], item["label"], item["valid_count"],
                    "-" if item["min"] is None else item["min"],
                    "-" if item["max"] is None else item["max"],
                    "-" if item["mean"] is None else item["mean"],
                    "-" if item["std"] is None else item["std"],
                    item["unique_values"], "YES" if item["fixed"] else "no",
                    item["saturated_high"] + item["saturated_low"],
                    ",".join(item["flag_counts"].keys()) or "-",
                )
            )
        if s["saturated_channels"]:
            lines.append("")
            lines.append("  SATURATED channels: {}".format(", ".join(s["saturated_channels"])))
        if s["fixed_channels"]:
            lines.append("  FIXED channels (constant value; not proof of a working sensor): {}".format(
                ", ".join(s["fixed_channels"])))
        if s["invalid_channels"]:
            lines.append("  Channels with invalid samples: {}".format(", ".join(s["invalid_channels"])))
        return "\n".join(lines)


def stats_from_csv(path: str) -> RunStats:
    """Recompute the run summary from the saved samples.csv."""
    stats = RunStats()
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            raw = []
            valid = []
            flags = []
            for index in range(CHANNEL_COUNT):
                value_text = row.get("ch{}".format(index), "")
                raw.append(None if value_text in ("", None) else int(value_text))
                valid.append(row.get("valid{}".format(index), "0") == "1")
                flags.append(int(row.get("flag{}".format(index), "0")))
            sample = SampleFrame(
                device_id="csv",
                boot_id=row.get("boot_id", ""),
                frame_seq=int(row.get("frame_seq", "0")),
                timestamp_us=int(row.get("device_timestamp_us", "0")),
                raw_adc=tuple(raw),
                valid=tuple(valid),
                sample_timestamp_us=tuple(None for _ in range(CHANNEL_COUNT)),
                channel_flags=tuple(flags),
                adc_status=(),
                reference_mode=row.get("reference_mode", "INTERNAL_2V048"),
                effective_frame_rate_hz=float(row.get("effective_frame_rate_hz", "0") or 0),
                host_received_ns=int(row.get("host_received_unix_ns", "0") or 0),
                host_received_utc=row.get("host_received_iso", ""),
                host_monotonic_ns=int(row.get("host_monotonic_ns", "0") or 0),
            )
            stats.add_sample(sample)
    return stats
