"""36-point press/release protocol.

The protocol is deliberately independent of serial I/O: the caller owns a reader
thread and passes emit_event/status_provider callbacks.  This lets the timing and
event order be unit-tested with a fake clock without touching hardware.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Sequence

ROWS = 6
COLUMNS = 6
TOTAL_POINTS = ROWS * COLUMNS


@dataclass(frozen=True)
class Point:
    point_id: int
    row: int
    column: int

    @property
    def label(self) -> str:
        return "R{}C{}".format(self.row, self.column)


POINTS: List[Point] = [
    Point(point_id, (point_id - 1) // COLUMNS + 1, (point_id - 1) % COLUMNS + 1)
    for point_id in range(1, TOTAL_POINTS + 1)
]


def point_from_id(point_id: int) -> Point:
    if not 1 <= point_id <= TOTAL_POINTS:
        raise ValueError("point_id must be 1..36")
    return POINTS[point_id - 1]


class ExperimentProtocol:
    def __init__(
        self,
        emit_event: Callable[..., Dict],
        status_provider: Callable[[], Optional[Dict]],
        baseline_s: float = 10.0,
        press_s: float = 3.0,
        release_s: float = 3.0,
        confirm_each: bool = True,
        points: Sequence[Point] = tuple(POINTS),
        print_fn: Callable[..., None] = print,
        input_fn: Callable[[str], str] = input,
        sleep_fn: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        tick_s: float = 0.05,
    ) -> None:
        if baseline_s < 0 or press_s <= 0 or release_s <= 0:
            raise ValueError("baseline must be >=0; press/release must be >0")
        self.emit_event = emit_event
        self.status_provider = status_provider
        self.baseline_s = float(baseline_s)
        self.press_s = float(press_s)
        self.release_s = float(release_s)
        self.confirm_each = confirm_each
        self.points = list(points)
        self.print_fn = print_fn
        self.input_fn = input_fn
        self.sleep_fn = sleep_fn
        self.clock = clock
        self.tick_s = max(0.01, float(tick_s))
        self.event_seq = 0

    def _emit(self, kind: str, point: Optional[Point] = None, phase: Optional[str] = None, **extra) -> Dict:
        status = self.status_provider() or {}
        now_ns = time.time_ns()
        mono_ns = time.monotonic_ns()
        latest_mono = status.get("host_monotonic_ns")
        age_ms = None
        if latest_mono:
            age_ms = (mono_ns - int(latest_mono)) / 1_000_000.0
        self.event_seq += 1
        fields = {
            "event_seq": self.event_seq,
            "phase": phase or kind,
            "point_id": None if point is None else point.point_id,
            "row": None if point is None else point.row,
            "column": None if point is None else point.column,
            "label": None if point is None else point.label,
            "device_timestamp_us": status.get("device_timestamp_us"),
            "frame_seq": status.get("frame_seq"),
            "latest_frame_age_ms": age_ms,
            "host_event_unix_ns": now_ns,
            "host_event_monotonic_ns": mono_ns,
        }
        fields.update(extra)
        return self.emit_event(kind, **fields)

    def _baseline(self, phase: str, seconds: float) -> None:
        self.print_fn("\n=== {}: NO CONTACT for {:.0f}s ===".format(phase, seconds), flush=True)
        self._emit("BASELINE_START", phase=phase, planned_s=seconds)
        self._countdown("NO CONTACT", seconds, None)
        self._emit("BASELINE_END", phase=phase, planned_s=seconds)

    def _countdown(self, label: str, seconds: float, point: Optional[Point]) -> None:
        self.print_fn(">>> {}  ({:.0f}s)".format(label, seconds), flush=True)
        start = self.clock()
        end = start + seconds
        next_print = math.ceil(seconds)
        while True:
            remaining = end - self.clock()
            if remaining <= 0:
                break
            if remaining <= next_print:
                self.print_fn("    {}... {:.0f}s".format(label, max(1, math.ceil(remaining))), flush=True)
                next_print -= 1
            self.sleep_fn(min(self.tick_s, max(0.0, remaining)))
        self.print_fn("    {} done".format(label), flush=True)

    def run(self) -> Dict:
        self.print_fn("36-POINT PRESS EXPERIMENT", flush=True)
        self.print_fn("Order: R1C1..R1C6, R2C1..R2C6, ... R6C6 (point_id=(row-1)*6+column)", flush=True)
        self.print_fn("Use the same non-conductive tool, same contact area/force; do not touch bare electrodes.", flush=True)
        self._emit("EXPERIMENT_START", phase="EXPERIMENT_START", total_points=len(self.points),
                   baseline_s=self.baseline_s, press_s=self.press_s, release_s=self.release_s)
        self._baseline("PRE_BASELINE", self.baseline_s)
        completed = 0
        for index, point in enumerate(self.points, start=1):
            self.print_fn("\n=== POINT {}/{} = {} (row {}, column {}) ===".format(
                index, len(self.points), point.label, point.row, point.column), flush=True)
            self._emit("POINT_READY", point=point, phase="POINT_READY", point_index=index,
                       total_points=len(self.points), completed=completed)
            if self.confirm_each:
                self.input_fn("Position the tool at {} and press Enter when ready... ".format(point.label))
                self._emit("USER_READY", point=point, phase="USER_READY", point_index=index)
            self.print_fn(">>> PRESS {} NOW and HOLD for {:.0f}s".format(point.label, self.press_s), flush=True)
            self._emit("PRESS_START", point=point, phase="PRESS_START", point_index=index, planned_s=self.press_s)
            self._countdown("PRESS {}".format(point.label), self.press_s, point)
            self.print_fn(">>> RELEASE {} NOW for {:.0f}s".format(point.label, self.release_s), flush=True)
            self._emit("RELEASE_START", point=point, phase="RELEASE_START", point_index=index, planned_s=self.release_s)
            self._countdown("RELEASE {}".format(point.label), self.release_s, point)
            completed += 1
            self._emit("POINT_DONE", point=point, phase="POINT_DONE", point_index=index, completed=completed)
        self._baseline("POST_BASELINE", self.baseline_s)
        self._emit("EXPERIMENT_END", phase="EXPERIMENT_END", completed=completed, total_points=len(self.points))
        return {"completed": completed, "total_points": len(self.points), "events": self.event_seq}
