"""Configuration and data model for cup-grasp trials."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

CHANNEL_LABELS = [
    "ADC1_AIN0", "ADC1_AIN1", "ADC1_AIN2", "ADC1_AIN3",
    "ADC2_AIN0", "ADC2_AIN1", "ADC2_AIN2", "ADC2_AIN3",
    "ADC3_AIN0", "ADC3_AIN1", "ADC3_AIN2", "ADC3_AIN3",
]
SAT_HIGH = 8388607
SAT_LOW = -8388608
FLAG_NO_DATA = 0x20


class ConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class TactileConfig:
    channel: int
    channel_label: str
    reference_mode: str
    baseline_samples: int
    ema_alpha: float
    contact_delta_counts: Optional[float]
    release_delta_counts: Optional[float]
    confirmation_frames: int
    sensor_timeout_ms: int
    max_saturation_fraction: float
    saturation_window: int


@dataclass(frozen=True)
class GripperConfig:
    open_pulse_us: Optional[int]
    fixed_pulse_us: Optional[int]
    release_pulse_us: Optional[int]
    step_us: Optional[int]
    close_direction: Optional[int]
    min_pulse_us: Optional[int]
    max_pulse_us: Optional[int]
    max_steps: Optional[int]
    step_interval_ms: Optional[int]
    hold_s: Optional[float]


@dataclass(frozen=True)
class CupGraspConfig:
    data_kind: str
    schema_status: str
    mode: str
    cup_model: Optional[str]
    empty_cup_g: Optional[float]
    video_path: Optional[str]
    tactile: TactileConfig
    gripper: GripperConfig
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def simulated(self) -> bool:
        return self.data_kind == "SIMULATED"

    def require_tactile_thresholds(self) -> None:
        t = self.tactile
        if t.contact_delta_counts is None or t.release_delta_counts is None:
            raise ConfigurationError("contact/release thresholds are null; run a valid single-point test first")
        if not 0 < t.release_delta_counts < t.contact_delta_counts:
            raise ConfigurationError("release threshold must be positive and below contact threshold")
        if t.channel < 0 or t.channel > 11:
            raise ConfigurationError("tactile channel must be 0..11")
        if t.reference_mode != "AVDD_AVSS":
            raise ConfigurationError("single-point measurement requires AVDD_AVSS reference (or documented equivalent)")

    def require_gripper(self) -> None:
        g = self.gripper
        values = (g.open_pulse_us, g.fixed_pulse_us, g.step_us, g.close_direction,
                  g.min_pulse_us, g.max_pulse_us, g.max_steps)
        if any(v is None for v in values):
            raise ConfigurationError("gripper pulse/range/step/direction is null; blocked until user verification")
        if g.close_direction not in (-1, 1):
            raise ConfigurationError("close_direction must be +1 or -1")
        if not g.min_pulse_us <= g.open_pulse_us <= g.max_pulse_us:
            raise ConfigurationError("open pulse outside verified min/max")
        if not g.min_pulse_us <= g.fixed_pulse_us <= g.max_pulse_us:
            raise ConfigurationError("fixed pulse outside verified min/max")
        if g.step_us <= 0 or g.max_steps <= 0 or g.step_interval_ms is None or g.step_interval_ms <= 0:
            raise ConfigurationError("step and max_steps must be positive")
        if g.hold_s is None or g.hold_s <= 0:
            raise ConfigurationError("hold_s must be positive")


def _require_int(value, name, minimum=None, maximum=None):
    if type(value) is not int:
        raise ConfigurationError("{} must be an integer".format(name))
    if minimum is not None and value < minimum:
        raise ConfigurationError("{} below minimum".format(name))
    if maximum is not None and value > maximum:
        raise ConfigurationError("{} above maximum".format(name))
    return value


def _require_float(value, name, minimum=None):
    if type(value) not in (int, float):
        raise ConfigurationError("{} must be numeric".format(name))
    value = float(value)
    if minimum is not None and value < minimum:
        raise ConfigurationError("{} below minimum".format(name))
    return value


def load_config(path: Path) -> CupGraspConfig:
    raw = json.loads(Path(path).read_text())
    trial = raw.get("trial") or {}
    t = raw.get("tactile") or {}
    g = raw.get("gripper") or {}
    tactile = TactileConfig(
        channel=_require_int(t.get("channel"), "tactile.channel", 0, 11),
        channel_label=str(t.get("channel_label", CHANNEL_LABELS[t.get("channel", 0)])),
        reference_mode=str(t.get("reference_mode", "")),
        baseline_samples=_require_int(t.get("baseline_samples"), "tactile.baseline_samples", 2),
        ema_alpha=_require_float(t.get("ema_alpha"), "tactile.ema_alpha", 0.0),
        contact_delta_counts=(None if t.get("contact_delta_counts") is None else _require_float(t["contact_delta_counts"], "tactile.contact_delta_counts")),
        release_delta_counts=(None if t.get("release_delta_counts") is None else _require_float(t["release_delta_counts"], "tactile.release_delta_counts")),
        confirmation_frames=_require_int(t.get("confirmation_frames"), "tactile.confirmation_frames", 1),
        sensor_timeout_ms=_require_int(t.get("sensor_timeout_ms"), "tactile.sensor_timeout_ms", 1),
        max_saturation_fraction=_require_float(t.get("max_saturation_fraction"), "tactile.max_saturation_fraction", 0.0),
        saturation_window=_require_int(t.get("saturation_window"), "tactile.saturation_window", 2),
    )
    if not 0.0 < tactile.ema_alpha <= 1.0:
        raise ConfigurationError("tactile.ema_alpha must be in (0,1]")
    def opt_int(key):
        value = g.get(key)
        return None if value is None else _require_int(value, "gripper." + key)
    def opt_float(key):
        value = g.get(key)
        return None if value is None else _require_float(value, "gripper." + key)
    gripper = GripperConfig(
        open_pulse_us=opt_int("open_pulse_us"),
        fixed_pulse_us=opt_int("fixed_pulse_us"),
        release_pulse_us=opt_int("release_pulse_us"),
        step_us=opt_int("step_us"),
        close_direction=opt_int("close_direction"),
        min_pulse_us=opt_int("min_pulse_us"),
        max_pulse_us=opt_int("max_pulse_us"),
        max_steps=opt_int("max_steps"),
        step_interval_ms=opt_int("step_interval_ms"),
        hold_s=opt_float("hold_s"),
    )
    return CupGraspConfig(
        data_kind=str(raw.get("data_kind", "UNKNOWN")),
        schema_status=str(raw.get("schema_status", "UNKNOWN")),
        mode=str(trial.get("mode", g.get("mode", "FIXED"))).upper(),
        cup_model=trial.get("cup_model"),
        empty_cup_g=(None if trial.get("empty_cup_g") is None else _require_float(trial["empty_cup_g"], "trial.empty_cup_g", 0.0)),
        video_path=trial.get("video_path"),
        tactile=tactile,
        gripper=gripper,
        raw=raw,
    )
