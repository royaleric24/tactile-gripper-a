"""Live terminal and optional matplotlib monitors.

Both displays are fed only by parsed serial SAMPLE frames.  Invalid channels are
shown as INVALID / gaps, never as zero.
"""
from __future__ import annotations

import shutil
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional

from .protocol import CHANNEL_FLAGS, SampleFrame, channel_label, flag_names
from .stats import RunStats


@dataclass
class Snapshot:
    status: str = "DISCONNECTED"
    port: str = ""
    firmware_version: str = ""
    device_id: str = ""
    reference_mode: str = ""
    frame: Optional[SampleFrame] = None
    last_host_ns: Optional[int] = None
    last_error: Optional[str] = None
    samples: int = 0
    adc_states: List[str] = field(default_factory=lambda: ["UNKNOWN", "UNKNOWN", "UNKNOWN"])
    recent_host_ns: Deque[int] = field(default_factory=lambda: deque(maxlen=100))


def _rate_hz(times: Deque[int]) -> Optional[float]:
    if len(times) < 2:
        return None
    elapsed = times[-1] - times[0]
    if elapsed <= 0:
        return None
    return (len(times) - 1) * 1e9 / elapsed


def _bar(value: int, width: int = 18) -> str:
    fraction = min(1.0, abs(value) / 8388607.0)
    filled = int(round(fraction * width))
    if value < 0:
        return "-" * filled + "." * (width - filled)
    return "#" * filled + "." * (width - filled)


class TextMonitor:
    def __init__(self) -> None:
        self._last_draw = 0.0

    def draw(self, snapshot: Snapshot, stats: RunStats, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_draw < 0.15:
            return
        self._last_draw = now
        width = max(80, min(160, shutil.get_terminal_size((100, 30)).columns))
        lines: List[str] = []
        rate = _rate_hz(snapshot.recent_host_ns)
        summary = stats.summary()
        seq = None if snapshot.frame is None else snapshot.frame.frame_seq
        lines.append("\033[H\033[J")
        lines.append("TACTILE 12-CH ADS1220  |  {}".format(snapshot.port))
        lines.append(
            "state={}  fw={}  dev={}  ref={}".format(
                snapshot.status, snapshot.firmware_version or "?", snapshot.device_id or "?", snapshot.reference_mode or "?"
            )
        )
        lines.append(
            "frames={}  rate={} Hz  seq={}  missing={} drop={}  timeouts={}  invalid_ratio={}".format(
                snapshot.samples,
                "?" if rate is None else "{:.1f}".format(rate),
                "?" if seq is None else seq,
                summary["frame_seq"]["missing"],
                "?" if summary["frame_seq"]["drop_rate"] is None else "{:.4f}".format(summary["frame_seq"]["drop_rate"]),
                summary["host_timeouts"],
                "?" if summary["valid_ratio"] is None else "{:.3f}".format(1.0 - summary["valid_ratio"]),
            )
        )
        lines.append("")
        lines.append(" CH  label       raw ADC     valid  flags                 level")
        lines.append(" " + "-" * (width - 1))
        frame = snapshot.frame
        for index in range(12):
            if frame is None:
                value = None
                valid = False
                flags = 0
            else:
                value = frame.raw_adc[index]
                valid = frame.valid[index]
                flags = frame.channel_flags[index]
            flag_text = ",".join(flag_names(flags)) or ("OK" if valid else "NO_DATA")
            value_text = "INVALID" if value is None else str(value)
            level = " " * 18 if value is None else _bar(value)
            lines.append(
                " {:>2}  {:<10} {:>11}  {:<5}  {:<20} {}".format(
                    index, channel_label(index), value_text, "OK" if valid else "BAD", flag_text, level
                )
            )
        lines.append("")
        lines.append(
            " ADC1={}  ADC2={}  ADC3={}".format(
                snapshot.adc_states[0] if len(snapshot.adc_states) > 0 else "?",
                snapshot.adc_states[1] if len(snapshot.adc_states) > 1 else "?",
                snapshot.adc_states[2] if len(snapshot.adc_states) > 2 else "?",
            )
        )
        if snapshot.last_error:
            lines.append(" last_error: {}".format(snapshot.last_error))
        print("\n".join(lines), flush=True)


class PlotMonitor:
    def __init__(self, window_s: float = 10.0) -> None:
        try:
            import matplotlib

            matplotlib.use("TkAgg")
            import matplotlib.pyplot as plt
        except Exception as exc:
            raise RuntimeError(
                "matplotlib/Tk is not available ({}). Use --monitor text, or run "
                "`uv run --with matplotlib python -m tools.tactile_acq run ...`".format(exc)
            ) from exc
        self.plt = plt
        self.window_s = max(1.0, window_s)
        self.fig, self.axes = plt.subplots(4, 3, sharex=True, figsize=(15, 9))
        self.axes = self.axes.flatten()
        self.lines = []
        self.times: List[Deque[float]] = []
        self.values: List[Deque[Optional[int]]] = []
        self._last_draw = 0.0
        for index, axis in enumerate(self.axes):
            axis.set_title(channel_label(index), fontsize=9)
            axis.set_ylim(-1000, 1000)
            axis.grid(True, alpha=0.25)
            axis.tick_params(labelsize=7)
            (line,) = axis.plot([], [], linewidth=0.9, color="#1f77b4")
            self.lines.append(line)
            self.times.append(deque(maxlen=1200))
            self.values.append(deque(maxlen=1200))
        self.fig.suptitle("TACTILE 12-CH (real serial values; invalid = gap)", fontsize=11)
        self.fig.tight_layout(rect=(0, 0.02, 1, 0.97))
        self.plt.show(block=False)

    def draw(self, snapshot: Snapshot, stats: RunStats, force: bool = False) -> None:
        now = time.monotonic()
        if snapshot.frame is not None:
            frame = snapshot.frame
            timestamp = (snapshot.last_host_ns or time.time_ns()) / 1e9
            for index in range(12):
                self.times[index].append(timestamp)
                self.values[index].append(frame.raw_adc[index] if frame.valid[index] else None)
            for index, line in enumerate(self.lines):
                xs = list(self.times[index])
                ys = list(self.values[index])
                line.set_data(xs, ys)
                valid_values = [value for value in ys if value is not None]
                if valid_values:
                    low = min(valid_values)
                    high = max(valid_values)
                    margin = max(1000, int((high - low) * 0.15))
                    self.axes[index].set_ylim(low - margin, high + margin)
                if xs:
                    self.axes[index].set_xlim(max(xs[0], xs[-1] - self.window_s), xs[-1] + 0.05)
        if force or now - self._last_draw >= 0.1:
            self._last_draw = now
            rate = _rate_hz(snapshot.recent_host_ns)
            self.fig.suptitle(
                "TACTILE 12-CH  state={}  rate={} Hz  seq={}  missing={}  timeouts={}  ref={}".format(
                    snapshot.status,
                    "?" if rate is None else "{:.1f}".format(rate),
                    "?" if snapshot.frame is None else snapshot.frame.frame_seq,
                    stats.missing_frames,
                    stats.host_timeouts,
                    snapshot.reference_mode or "?",
                ),
                fontsize=10,
            )
            self.fig.canvas.draw_idle()
            self.plt.pause(0.001)

    def close(self) -> None:
        try:
            self.plt.close(self.fig)
        except Exception:
            pass
