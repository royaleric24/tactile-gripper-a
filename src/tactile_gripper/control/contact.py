"""Explainable relative FSR contact assessment (offline, no hardware writes).

The score is deliberately *relative*: it is the increase of each valid FSR
count above an explicitly captured unloaded baseline, normalised by an ADC
span.  It is not force, pressure, friction, cup weight or a calibrated contact
force.  A missing/invalid baseline, an invalid channel, a saturated channel or
a stale frame produces a non-actionable state instead of a made-up score.

No thresholds in this module are calibrated against the physical cup.  The
defaults are provisional engineering defaults for offline tests and must be
replaced by measured data before any real AUTO commissioning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..models import ChannelConfig, ChannelConfiguration, TactileFrame

# States are strings so they survive JSONL/CSV without enum codec surprises.
NO_CONTACT = "NO_CONTACT"
INSUFFICIENT = "INSUFFICIENT"
NORMAL = "NORMAL"
TIGHT = "TIGHT"
INVALID = "INVALID"
UNCALIBRATED = "UNCALIBRATED"
NOT_APPLICABLE = "NOT_APPLICABLE"

CONTACT_STATES = (NO_CONTACT, INSUFFICIENT, NORMAL, TIGHT, INVALID, UNCALIBRATED, NOT_APPLICABLE)

# Fallback span only when the ADC bit depth is absent from HELLO/config.  This
# is a heuristic test constant, not a calibrated force conversion.
FSR_SPAN_COUNTS_FALLBACK = 250_000.0
FSR_SPAN_FRACTION = 0.05
FSR_SATURATION_FRACTION = 0.995


@dataclass(frozen=True)
class FsrThresholds:
    """Provisional relative-score thresholds with hysteresis."""

    no_contact: float = 0.10
    insufficient: float = 0.20
    normal: float = 0.45
    tight: float = 0.80
    hysteresis: float = 0.05

    def __post_init__(self) -> None:
        values = (self.no_contact, self.insufficient, self.normal, self.tight)
        if not (0.0 <= values[0] < values[1] < values[2] < values[3] <= 1.0):
            raise ValueError("FSR thresholds must satisfy 0 <= no_contact < insufficient < normal < tight <= 1")
        if not 0.0 <= self.hysteresis < 0.5:
            raise ValueError("hysteresis must be in [0, 0.5)")

    def to_dict(self) -> dict[str, float]:
        return {
            "no_contact": self.no_contact,
            "insufficient": self.insufficient,
            "normal": self.normal,
            "tight": self.tight,
            "hysteresis": self.hysteresis,
        }


DEFAULT_FSR_THRESHOLDS = FsrThresholds()


@dataclass(frozen=True)
class FsrReading:
    channel_id: int
    name: str
    raw: float | None
    valid: bool
    voltage_uv: float | None
    baseline_raw: float | None
    delta_counts: float | None
    relative_change: float | None
    channel_score: float | None
    saturated: bool
    voltage_basis_complete: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel_id": self.channel_id,
            "name": self.name,
            "raw": self.raw,
            "valid": self.valid,
            "voltage_uv": self.voltage_uv,
            "voltage_basis_complete": self.voltage_basis_complete,
            "baseline_raw": self.baseline_raw,
            "delta_counts": self.delta_counts,
            "relative_change": self.relative_change,
            "channel_score": self.channel_score,
            "saturated": self.saturated,
        }


@dataclass(frozen=True)
class ContactAssessment:
    state: str
    score: float | None
    quality: float
    reason: str
    readings: tuple[FsrReading, ...] = ()
    baseline_ready: bool = False
    baseline_source: str | None = None
    baseline_captured_at_utc: str | None = None
    frame_seq: int | None = None
    host_received_ns: int | None = None
    age_ms: float | None = None
    stale_after_ms: float | None = None
    thresholds: dict[str, float] = field(default_factory=dict)

    @property
    def actionable(self) -> bool:
        return self.state in (NO_CONTACT, INSUFFICIENT, NORMAL, TIGHT) and self.score is not None

    @property
    def requires_tightening(self) -> bool:
        return self.state in (NO_CONTACT, INSUFFICIENT)

    @property
    def requires_loosening(self) -> bool:
        return self.state == TIGHT

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "score": self.score,
            "quality": self.quality,
            "reason": self.reason,
            "actionable": self.actionable,
            "baseline_ready": self.baseline_ready,
            "baseline_source": self.baseline_source,
            "baseline_captured_at_utc": self.baseline_captured_at_utc,
            "frame_seq": self.frame_seq,
            "host_received_ns": self.host_received_ns,
            "age_ms": self.age_ms,
            "stale_after_ms": self.stale_after_ms,
            "thresholds": dict(self.thresholds),
            "readings": [reading.to_dict() for reading in self.readings],
        }


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _span_counts(channel: ChannelConfig) -> float:
    if channel.adc_bits is not None:
        return max(1.0, (2 ** (channel.adc_bits - 1)) * FSR_SPAN_FRACTION)
    return FSR_SPAN_COUNTS_FALLBACK


def _full_scale_counts(channel: ChannelConfig) -> float | None:
    if channel.adc_bits is None:
        return None
    return float(2 ** (channel.adc_bits - 1))


def classify_contact(score: float, previous: str | None, thresholds: FsrThresholds = DEFAULT_FSR_THRESHOLDS) -> str:
    """Classify a relative score with hysteresis.

    Four physical bands are reported: ``NO_CONTACT`` below ``no_contact``,
    ``INSUFFICIENT`` below ``normal``, ``NORMAL`` below ``tight`` and ``TIGHT``
    above it.  The optional ``insufficient`` value is retained as a stricter
    "clearly insufficient" reference for policy tuning, not as a fifth state.
    Hysteresis keeps the previous state near a boundary so a grip does not
    chatter at the PWM step rate.
    """
    score = _clamp(score)
    h = thresholds.hysteresis
    if previous == TIGHT:
        if score >= thresholds.tight - h:
            return TIGHT
        if score >= thresholds.normal:
            return NORMAL
        if score >= thresholds.no_contact:
            return INSUFFICIENT
        return NO_CONTACT
    if previous == NORMAL:
        if score >= thresholds.tight:
            return TIGHT
        if score >= thresholds.normal - h:
            return NORMAL
        if score >= thresholds.no_contact:
            return INSUFFICIENT
        return NO_CONTACT
    if previous == INSUFFICIENT:
        if score >= thresholds.tight:
            return TIGHT
        if score >= thresholds.normal:
            return NORMAL
        if score >= thresholds.no_contact - h:
            return INSUFFICIENT
        return NO_CONTACT
    if previous == NO_CONTACT:
        if score >= thresholds.tight:
            return TIGHT
        if score >= thresholds.normal:
            return NORMAL
        if score >= thresholds.no_contact + h:
            return INSUFFICIENT
        return NO_CONTACT
    # No previous state: use enter thresholds.
    if score >= thresholds.tight:
        return TIGHT
    if score >= thresholds.normal:
        return NORMAL
    if score >= thresholds.no_contact:
        return INSUFFICIENT
    return NO_CONTACT


class FsrContactAssessor:
    """Stateful baseline + hysteresis assessment for one sensor config."""

    def __init__(self, thresholds: FsrThresholds = DEFAULT_FSR_THRESHOLDS):
        self.thresholds = thresholds
        self._baseline: dict[int, float] = {}
        self._baseline_source: str | None = None
        self._baseline_captured_at_utc: str | None = None
        self._previous_state: str | None = None
        self.last_assessment: ContactAssessment | None = None

    @property
    def baseline(self) -> dict[int, float]:
        return dict(self._baseline)

    @property
    def baseline_ready(self) -> bool:
        return bool(self._baseline)

    def clear_baseline(self) -> None:
        self._baseline = {}
        self._baseline_source = None
        self._baseline_captured_at_utc = None
        self._previous_state = None
        self.last_assessment = None

    def capture_baseline(
        self,
        frame: TactileFrame | None,
        config: ChannelConfiguration,
        *,
        source: str = "OPERATOR_EXPLICIT",
    ) -> ContactAssessment:
        """Capture unloaded FSR counts from one *valid* frame.

        All configured FSR channels must be valid and unsaturated; a partial
        baseline would silently weaken the two-channel comparison.
        """
        if frame is None:
            raise ValueError("no frame available for FSR baseline")
        channels = config.fsr_channels
        if not channels:
            raise ValueError("configuration has no FSR channels")
        pairs = {channel_id: (value, valid) for channel_id, value, valid in frame.pairs()}
        captured: dict[int, float] = {}
        for channel in channels:
            value, valid = pairs.get(channel.channel_id, (None, False))
            if not valid or value is None:
                raise ValueError(f"FSR {channel.channel_id} is invalid; baseline not captured")
            if _is_saturated(channel, float(value)):
                raise ValueError(f"FSR {channel.channel_id} is saturated; baseline not captured")
            captured[channel.channel_id] = float(value)
        self._baseline = captured
        self._baseline_source = source
        self._baseline_captured_at_utc = frame.host_received_utc
        self._previous_state = None
        return self.assess(frame, config, now_ns=frame.host_received_ns)

    def assess(
        self,
        frame: TactileFrame | None,
        config: ChannelConfiguration,
        *,
        now_ns: int,
        stale_after_ms: float = 200.0,
    ) -> ContactAssessment:
        channels = config.fsr_channels
        if not channels:
            assessment = ContactAssessment(
                state=NOT_APPLICABLE,
                score=None,
                quality=0.0,
                reason="no FSR channels in HELLO channel_config",
                thresholds=self.thresholds.to_dict(),
            )
            self.last_assessment = assessment
            return assessment
        if frame is None:
            assessment = ContactAssessment(
                state=INVALID,
                score=None,
                quality=0.0,
                reason="no sensor frame",
                baseline_ready=bool(self._baseline),
                baseline_source=self._baseline_source,
                baseline_captured_at_utc=self._baseline_captured_at_utc,
                stale_after_ms=stale_after_ms,
                thresholds=self.thresholds.to_dict(),
            )
            self.last_assessment = assessment
            return assessment
        age_ms = max(0.0, (now_ns - frame.host_received_ns) / 1_000_000.0)
        pairs = {channel_id: (value, valid) for channel_id, value, valid in frame.pairs()}
        readings: list[FsrReading] = []
        for channel in channels:
            raw, valid = pairs.get(channel.channel_id, (None, False))
            raw_value = float(raw) if valid and raw is not None else None
            voltage = channel.count_to_voltage_uv(raw_value)
            baseline = self._baseline.get(channel.channel_id)
            delta = None
            relative = None
            channel_score = None
            saturated = bool(raw_value is not None and _is_saturated(channel, raw_value))
            if raw_value is not None and baseline is not None:
                delta = raw_value - baseline
                relative = delta / max(abs(baseline), 1.0)
                channel_score = _clamp(delta / _span_counts(channel))
            readings.append(
                FsrReading(
                    channel_id=channel.channel_id,
                    name=channel.name or f"FSR_{channel.channel_id}",
                    raw=raw_value,
                    valid=bool(valid and raw_value is not None),
                    voltage_uv=voltage,
                    baseline_raw=baseline,
                    delta_counts=delta,
                    relative_change=relative,
                    channel_score=channel_score,
                    saturated=saturated,
                    voltage_basis_complete=channel.voltage_basis_complete,
                )
            )

        invalid = [reading for reading in readings if not reading.valid or reading.saturated]
        if frame.frame_valid is False:
            return self._finish(INVALID, None, 0.0, "frame marked invalid", readings, frame, age_ms, stale_after_ms)
        if age_ms > stale_after_ms:
            return self._finish(
                INVALID,
                None,
                0.0,
                f"stale frame ({age_ms:.1f} ms > {stale_after_ms:.1f} ms)",
                readings,
                frame,
                age_ms,
                stale_after_ms,
            )
        if invalid:
            names = ", ".join(reading.name for reading in invalid)
            return self._finish(
                INVALID,
                None,
                0.0,
                f"invalid or saturated FSR channel(s): {names}",
                readings,
                frame,
                age_ms,
                stale_after_ms,
            )
        if len(self._baseline) != len(channels):
            return self._finish(
                UNCALIBRATED,
                None,
                0.0,
                "unloaded FSR baseline not captured for every channel",
                readings,
                frame,
                age_ms,
                stale_after_ms,
            )
        scores = [reading.channel_score for reading in readings]
        if any(score is None for score in scores):
            return self._finish(
                INVALID,
                None,
                0.0,
                "FSR score unavailable",
                readings,
                frame,
                age_ms,
                stale_after_ms,
            )
        # Conservative: the weaker FSR channel limits the decision, so one
        # finger losing contact cannot be hidden by the other one.
        score = min(float(item) for item in scores if item is not None)
        state = classify_contact(score, self._previous_state, self.thresholds)
        self._previous_state = state
        quality = 1.0
        return self._finish(state, score, quality, self._reason_for(state, score), readings, frame, age_ms, stale_after_ms)

    def _finish(
        self,
        state: str,
        score: float | None,
        quality: float,
        reason: str,
        readings: list[FsrReading],
        frame: TactileFrame,
        age_ms: float,
        stale_after_ms: float,
    ) -> ContactAssessment:
        if state in (INVALID, UNCALIBRATED, NOT_APPLICABLE):
            self._previous_state = None
        assessment = ContactAssessment(
            state=state,
            score=score,
            quality=quality,
            reason=reason,
            readings=tuple(readings),
            baseline_ready=bool(self._baseline),
            baseline_source=self._baseline_source,
            baseline_captured_at_utc=self._baseline_captured_at_utc,
            frame_seq=frame.frame_seq,
            host_received_ns=frame.host_received_ns,
            age_ms=round(age_ms, 3),
            stale_after_ms=stale_after_ms,
            thresholds=self.thresholds.to_dict(),
        )
        self.last_assessment = assessment
        return assessment

    def _reason_for(self, state: str, score: float) -> str:
        if state == NO_CONTACT:
            return "relative FSR increase below no-contact threshold"
        if state == INSUFFICIENT:
            return "relative contact insufficient; tightening may be considered"
        if state == NORMAL:
            return "relative contact in the normal band"
        if state == TIGHT:
            return "relative contact above tight threshold; do not keep tightening"
        return state


def _is_saturated(channel: ChannelConfig, raw: float) -> bool:
    full_scale = _full_scale_counts(channel)
    if full_scale is None:
        return False
    return abs(raw) >= full_scale * FSR_SATURATION_FRACTION
