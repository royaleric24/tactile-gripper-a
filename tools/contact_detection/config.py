from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DetectorConfig:
    avdd_mv: float = 3388.0
    baseline_frames: int = 20
    ema_alpha: float = 0.25
    contact_drop_v: float = 0.08
    release_recover_v: float = 0.03
    contact_confirm_frames: int = 3
    release_confirm_frames: int = 5
    unknown_timeout_s: float = 0.7
    baseline_adapt_alpha: float = 0.0005
    calibration_warn_contact: bool = True

    @property
    def counts_per_volt(self) -> float:
        return 8388607.0 / (self.avdd_mv / 1000.0)

    @property
    def contact_drop_counts(self) -> float:
        return self.contact_drop_v * self.counts_per_volt

    @property
    def release_span_counts(self) -> float:
        return self.release_recover_v * self.counts_per_volt
