"""Randomized multi-round 36-point schedule with contact controls."""
from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence

from .protocol import POINTS, Point

PRESS = "PRESS"
APPROACH = "APPROACH"
NO_CONTACT = "NO_CONTACT"


@dataclass(frozen=True)
class Segment:
    segment_index: int
    kind: str
    point: Optional[Point]
    control_id: Optional[int]
    hold_s: float
    release_s: float

    @property
    def label(self) -> str:
        if self.kind == PRESS and self.point is not None:
            return self.point.label
        if self.kind == APPROACH:
            target = self.point.label if self.point is not None else "-"
            return "APPROACH-{}-{}".format(self.control_id, target)
        return "NO_CONTACT-{}".format(self.control_id)


@dataclass(frozen=True)
class RoundSchedule:
    round_index: int
    seed: int
    segments: List[Segment]
    press_order: List[int]

    @property
    def press_segments(self) -> List[Segment]:
        return [segment for segment in self.segments if segment.kind == PRESS]

    def as_dict(self) -> Dict:
        return {
            "round_index": self.round_index,
            "seed": self.seed,
            "press_order": list(self.press_order),
            "segments": [
                {
                    "segment_index": segment.segment_index,
                    "kind": segment.kind,
                    "point_id": segment.point.point_id if segment.point else None,
                    "row": segment.point.row if segment.point else None,
                    "column": segment.point.column if segment.point else None,
                    "label": segment.label,
                    "control_id": segment.control_id,
                    "hold_s": segment.hold_s,
                    "release_s": segment.release_s,
                }
                for segment in self.segments
            ],
        }


def build_round_schedule(
    round_index: int,
    seed: int,
    press_s: float = 3.0,
    release_s: float = 3.0,
    approach_controls: int = 4,
    no_contact_controls: int = 4,
) -> RoundSchedule:
    if approach_controls < 0 or no_contact_controls < 0:
        raise ValueError("control counts must be non-negative")
    rng = random.Random(seed)
    order = [point.point_id for point in POINTS]
    rng.shuffle(order)
    segments: List[Segment] = []
    for point_id in order:
        point = POINTS[point_id - 1]
        segments.append(Segment(0, PRESS, point, None, press_s, release_s))
    for index in range(1, approach_controls + 1):
        target = POINTS[rng.randrange(len(POINTS))]
        segments.append(Segment(0, APPROACH, target, index, press_s, release_s))
    for index in range(1, no_contact_controls + 1):
        segments.append(Segment(0, NO_CONTACT, None, index, press_s, release_s))
    rng.shuffle(segments)
    segments = [Segment(i + 1, s.kind, s.point, s.control_id, s.hold_s, s.release_s)
                for i, s in enumerate(segments)]
    return RoundSchedule(round_index, seed, segments, order)


class RoundProtocol:
    """Interactive event protocol for one randomized round.

    Only the schedule knows the label/order; the model later receives features
    extracted from the raw signal, not the segment label.
    """

    def __init__(
        self,
        schedule: RoundSchedule,
        emit_event: Callable[..., Dict],
        status_provider: Callable[[], Optional[Dict]],
        baseline_s: float = 10.0,
        confirm_each: bool = True,
        print_fn: Callable[..., None] = print,
        input_fn: Callable[[str], str] = input,
        sleep_fn: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        tick_s: float = 0.05,
    ) -> None:
        self.schedule = schedule
        self.emit_event = emit_event
        self.status_provider = status_provider
        self.baseline_s = baseline_s
        self.confirm_each = confirm_each
        self.print_fn = print_fn
        self.input_fn = input_fn
        self.sleep_fn = sleep_fn
        self.clock = clock
        self.tick_s = max(0.01, tick_s)
        self.event_seq = 0
        self.completed = 0

    def _emit(self, kind: str, segment: Optional[Segment] = None, **extra) -> Dict:
        status = self.status_provider() or {}
        now_ns = time.time_ns()
        mono_ns = time.monotonic_ns()
        latest = status.get("host_monotonic_ns")
        age = None if not latest else (mono_ns - int(latest)) / 1_000_000.0
        self.event_seq += 1
        fields = {
            "event_seq": self.event_seq,
            "round_index": self.schedule.round_index,
            "round_seed": self.schedule.seed,
            "phase": kind,
            "segment_index": None if segment is None else segment.segment_index,
            "segment_kind": None if segment is None else segment.kind,
            "label": None if segment is None else segment.label,
            "point_id": (segment.point.point_id if segment is not None and segment.point else None),
            "row": (segment.point.row if segment is not None and segment.point else None),
            "column": (segment.point.column if segment is not None and segment.point else None),
            "control_id": None if segment is None else segment.control_id,
            "device_timestamp_us": status.get("device_timestamp_us"),
            "frame_seq": status.get("frame_seq"),
            "latest_frame_age_ms": age,
            "host_event_unix_ns": now_ns,
            "host_event_monotonic_ns": mono_ns,
        }
        fields.update(extra)
        return self.emit_event(kind, **fields)

    def _countdown(self, label: str, seconds: float) -> None:
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

    def _baseline(self, phase: str, seconds: float) -> None:
        self.print_fn("\n=== {}: NO CONTACT for {:.0f}s ===".format(phase, seconds), flush=True)
        self._emit("BASELINE_START", phase=phase, planned_s=seconds)
        self._countdown("NO CONTACT", seconds)
        self._emit("BASELINE_END", phase=phase, planned_s=seconds)

    def run(self) -> Dict:
        self.print_fn("\n" + "=" * 70)
        self.print_fn("ROUND {}  seed={}  segments={} (36 presses + {} approach + {} no-contact)".format(
            self.schedule.round_index, self.schedule.seed, len(self.schedule.segments),
            sum(1 for s in self.schedule.segments if s.kind == APPROACH),
            sum(1 for s in self.schedule.segments if s.kind == NO_CONTACT)))
        self.print_fn("=" * 70, flush=True)
        self._emit("ROUND_START", phase="ROUND_START", seed=self.schedule.seed,
                   total_segments=len(self.schedule.segments), total_presses=36)
        self._baseline("PRE_BASELINE", self.baseline_s)
        for segment in self.schedule.segments:
            self.print_fn("\n=== SEGMENT {}/{}: {} ===".format(
                segment.segment_index, len(self.schedule.segments), segment.label), flush=True)
            if segment.kind == PRESS and segment.point:
                self.print_fn("    TARGET: {} (row {}, column {})".format(
                    segment.label, segment.point.row, segment.point.column), flush=True)
            elif segment.kind == APPROACH:
                self.print_fn("    CONTROL: move tool close to {} but DO NOT TOUCH".format(
                    segment.label), flush=True)
            else:
                self.print_fn("    CONTROL: keep tool completely away from the cloth", flush=True)
            self._emit("SEGMENT_READY", segment=segment, planned_s=segment.hold_s,
                       completed_presses=self.completed)
            if self.confirm_each:
                self.input_fn("Position for {} and press Enter when ready... ".format(segment.label))
                self._emit("USER_READY", segment=segment)
            if segment.kind == PRESS:
                self.print_fn(">>> PRESS {} NOW and HOLD {:.0f}s".format(segment.label, segment.hold_s), flush=True)
                self._emit("PRESS_START", segment=segment, planned_s=segment.hold_s)
                self._countdown("PRESS {}".format(segment.label), segment.hold_s)
                self.print_fn(">>> RELEASE {} NOW for {:.0f}s".format(segment.label, segment.release_s), flush=True)
                self._emit("RELEASE_START", segment=segment, planned_s=segment.release_s)
                self._countdown("RELEASE {}".format(segment.label), segment.release_s)
                self.completed += 1
            elif segment.kind == APPROACH:
                self.print_fn(">>> APPROACH {} (NO TOUCH) and HOLD {:.0f}s".format(segment.label, segment.hold_s), flush=True)
                self._emit("APPROACH_START", segment=segment, planned_s=segment.hold_s)
                self._countdown("APPROACH NO TOUCH", segment.hold_s)
                self.print_fn(">>> WITHDRAW from {} NOW for {:.0f}s".format(segment.label, segment.release_s), flush=True)
                self._emit("APPROACH_END", segment=segment, planned_s=segment.release_s)
                self._countdown("WITHDRAW", segment.release_s)
            else:
                self.print_fn(">>> NO_CONTACT control #{} HOLD {:.0f}s".format(
                    segment.control_id, segment.hold_s), flush=True)
                self._emit("NO_CONTACT_START", segment=segment, planned_s=segment.hold_s)
                self._countdown("NO CONTACT", segment.hold_s)
                self._emit("NO_CONTACT_END", segment=segment, planned_s=segment.release_s)
                self._countdown("IDLE AFTER NO CONTACT", segment.release_s)
            self._emit("SEGMENT_DONE", segment=segment)
        self._baseline("POST_BASELINE", self.baseline_s)
        self._emit("ROUND_END", phase="ROUND_END", completed_presses=self.completed)
        return {"completed_presses": self.completed, "segments": len(self.schedule.segments),
                "events": self.event_seq}
