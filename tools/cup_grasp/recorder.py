"""Cup-grasp trial recorder with a single host monotonic timebase."""
from __future__ import annotations

import json
import statistics
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .model import CupGraspConfig
from .plot import write_tactile_svg
from .tactile import TactileSample


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class CupTrialRecorder:
    def __init__(self, root: Path, config: CupGraspConfig, *, trial_id: Optional[str] = None,
                 video_path: Optional[str] = None) -> None:
        self.config = config
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.trial_id = trial_id or "{}_{}".format(
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"), uuid.uuid4().hex[:8])
        self.run_dir = self.root / self.trial_id
        self.run_dir.mkdir(parents=True, exist_ok=False)
        self.video_path = video_path
        self.started_utc = utc_now_iso()
        self.tactile_path = self.run_dir / "tactile.jsonl"
        self.gripper_path = self.run_dir / "gripper_commands.jsonl"
        self.load_path = self.run_dir / "load_events.jsonl"
        self.events_path = self.run_dir / "trial_events.jsonl"
        self.meta_path = self.run_dir / "meta.json"
        self.metrics_path = self.run_dir / "metrics.json"
        self.report_path = self.run_dir / "REPORT.md"
        self._tactile = open(self.tactile_path, "w", encoding="utf-8")
        self._gripper = open(self.gripper_path, "w", encoding="utf-8")
        self._load = open(self.load_path, "w", encoding="utf-8")
        self._events = open(self.events_path, "w", encoding="utf-8")
        self.samples: List[Dict[str, Any]] = []
        self.gripper_events: List[Dict[str, Any]] = []
        self.load_events: List[Dict[str, Any]] = []
        self.events: List[Dict[str, Any]] = []
        self.first_host_ns: Optional[int] = None
        self.last_host_ns: Optional[int] = None
        self.first_device_us: Optional[int] = None
        self.last_device_us: Optional[int] = None
        self._write_meta(status="RUNNING")

    def _write_meta(self, status: str) -> None:
        meta = {
            "trial_id": self.trial_id,
            "started_utc": self.started_utc,
            "status": status,
            "data_kind": self.config.data_kind,
            "mode": self.config.mode,
            "cup_model": self.config.cup_model,
            "empty_cup_g": self.config.empty_cup_g,
            "video_path": self.video_path,
            "config_path": self.config.raw.get("_config_path"),
            "config": self.config.raw,
            "tactile_channel": self.config.tactile.channel,
            "tactile_channel_label": self.config.tactile.channel_label,
            "gripper_pulses": {
                "open": self.config.gripper.open_pulse_us,
                "fixed": self.config.gripper.fixed_pulse_us,
                "release": self.config.gripper.release_pulse_us,
            },
            "units": "ADC counts; PWM pulse-width commands are targets, not measured force/position",
            "note": "SIMULATED runs are not real hardware evidence.",
        }
        self.meta_path.write_text(json.dumps(meta, indent=2) + "\n")

    def _write(self, handle, value: Dict[str, Any]) -> None:
        handle.write(json.dumps(value, ensure_ascii=False) + "\n")
        handle.flush()

    def record_tactile(self, raw_line: str, frame, sample: TactileSample) -> None:
        host_ns = sample.host_monotonic_ns
        if self.first_host_ns is None:
            self.first_host_ns = host_ns
            self.first_device_us = sample.device_timestamp_us
        self.last_host_ns = host_ns
        self.last_device_us = sample.device_timestamp_us
        record = {
            "host_monotonic_ns": host_ns,
            "host_utc": utc_now_iso(),
            "device_timestamp_us": sample.device_timestamp_us,
            "frame_seq": sample.frame_seq,
            "channel": self.config.tactile.channel,
            "raw": sample.raw,
            "filtered": sample.filtered,
            "baseline": sample.baseline,
            "delta": sample.delta,
            "valid": sample.valid,
            "usable": sample.usable,
            "saturated": sample.saturated,
            "saturation_fraction": sample.saturation_fraction,
            "flags": sample.flags,
            "raw_line": raw_line.rstrip("\r\n"),
        }
        self.samples.append(record)
        self._write(self._tactile, record)

    def record_gripper(self, event: Dict[str, Any]) -> None:
        event = dict(event)
        event.setdefault("host_utc", utc_now_iso())
        self.gripper_events.append(event)
        self._write(self._gripper, event)

    def record_load(self, kind: str, **fields) -> None:
        event = {"host_monotonic_ns": fields.pop("host_monotonic_ns", None),
                 "host_utc": utc_now_iso(), "kind": kind}
        event.update(fields)
        self.load_events.append(event)
        self._write(self._load, event)

    def record_trial_event(self, kind: str, **fields) -> None:
        event = {"host_monotonic_ns": fields.pop("host_monotonic_ns", None),
                 "host_utc": utc_now_iso(), "kind": kind}
        event.update(fields)
        self.events.append(event)
        self._write(self._events, event)

    def finalize(self, *, status: str, control_summary: Dict[str, Any], notes: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        duration_s = ((self.last_host_ns - self.first_host_ns) / 1e9) if self.first_host_ns and self.last_host_ns else 0.0
        valid = [s for s in self.samples if s["usable"]]
        saturated = [s for s in self.samples if s["saturated"]]
        deltas = [s["delta"] for s in self.samples if s["delta"] is not None]
        water_total = sum(float(e.get("water_g") or 0.0) for e in self.load_events if e.get("kind") == "WATER")
        metrics = {
            "trial_id": self.trial_id,
            "data_kind": self.config.data_kind,
            "status": status,
            "mode": self.config.mode,
            "duration_s": duration_s,
            "tactile_frames": len(self.samples),
            "usable_fraction": len(valid) / len(self.samples) if self.samples else None,
            "saturation_fraction": len(saturated) / len(self.samples) if self.samples else None,
            "baseline_counts": self.samples[0]["baseline"] if self.samples else None,
            "delta_min": min(deltas) if deltas else None,
            "delta_max": max(deltas) if deltas else None,
            "delta_mean": statistics.mean(deltas) if deltas else None,
            "gripper_commands": len(self.gripper_events),
            "load_events": len(self.load_events),
            "water_total_g": water_total,
            "control": control_summary,
            "time_sync": {
                "host_duration_s": duration_s,
                "first_device_us": self.first_device_us,
                "last_device_us": self.last_device_us,
                "host_device_offset_us": (
                    (self.first_host_ns / 1000.0 - self.first_device_us) if self.first_host_ns and self.first_device_us else None),
                "note": "host monotonic_ns is the primary timeline; device microseconds are MCU time and wrap.",
            },
            "notes": notes or {},
        }
        self.metrics_path.write_text(json.dumps(metrics, indent=2) + "\n")
        write_tactile_svg(self.run_dir / "tactile_curve.svg", self.samples, self.gripper_events, self.load_events)
        self._write_meta(status=status)
        lines = [
            "# Cup Grasp Trial {}".format(self.trial_id),
            "",
            "- data kind: **{}**".format(self.config.data_kind),
            "- mode: **{}**".format(self.config.mode),
            "- status: **{}**".format(status),
            "- duration: {:.3f} s".format(duration_s),
            "- tactile frames: {}; usable {}; saturation {}".format(
                len(self.samples),
                "{:.3f}".format(metrics["usable_fraction"]) if metrics["usable_fraction"] is not None else "-",
                "{:.3f}".format(metrics["saturation_fraction"]) if metrics["saturation_fraction"] is not None else "-"),
            "- delta counts min/max/mean: {} / {} / {}".format(
                metrics["delta_min"], metrics["delta_max"],
                "{:.2f}".format(metrics["delta_mean"]) if metrics["delta_mean"] is not None else "-"),
            "- gripper commands: {}; load events: {}; water total: {} g".format(
                len(self.gripper_events), len(self.load_events), water_total),
            "- video: {}".format(self.video_path or "NONE"),
            "- curve: tactile_curve.svg",
            "",
            "## Boundary",
            "",
            "PWM values are commands, not measured force, angle or opening. ADC deltas are contact/pressure proxies, "
            "not Newtons. Slip/deformation are qualitative unless independently measured. SIMULATED data is not real.",
        ]
        if self.config.data_kind == "SIMULATED":
            lines += ["", "**This trial is SIMULATED and must not be counted as a real cup-grasp result.**"]
        self.report_path.write_text("\n".join(lines) + "\n")
        for handle in (self._tactile, self._gripper, self._load, self._events):
            handle.close()
        return metrics
