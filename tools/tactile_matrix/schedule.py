"""Row-scan schedule and state machine for the 6x6 matrix.

The real firmware will perform the GPIO/ADS1220 calls; this module defines the
exact phase order, durations and per-round column groups so host tests can
validate timing and coverage before any hardware is driven.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

from .model import COLS, ROWS, cell_index


class Phase(str, Enum):
    IDLE = "IDLE"
    DISCHARGE = "DISCHARGE"
    SETTLE = "SETTLE"
    CONVERT = "CONVERT"
    READ = "READ"
    NEXT_ROW = "NEXT_ROW"
    FRAME_DONE = "FRAME_DONE"


@dataclass(frozen=True)
class ScanAction:
    phase: Phase
    row: int
    round: int
    duration_us: int
    columns: Tuple[int, ...] = ()
    note: str = ""


@dataclass(frozen=True)
class MatrixTiming:
    pre_discharge_us: int = 200
    settle_us: int = 1000
    conversion_wait_us: int = 4500
    read_overhead_us: int = 100
    row_overhead_us: int = 100
    adc_count: int = 3

    def __post_init__(self) -> None:
        if self.pre_discharge_us < 0 or self.settle_us < 0:
            raise ValueError("timing values must be non-negative")
        if self.conversion_wait_us <= 0:
            raise ValueError("conversion_wait_us must be positive")
        if self.adc_count != 3:
            raise ValueError("this matrix maps two columns per each of three ADCs")

    @property
    def rounds(self) -> int:
        return (COLS + self.adc_count - 1) // self.adc_count

    def columns_for_round(self, round_index: int) -> Tuple[int, ...]:
        # ADC1 owns C1/C2, ADC2 C3/C4, ADC3 C5/C6.  Round 0 uses AIN0 of each
        # ADC (C1,C3,C5); round 1 uses AIN1 (C2,C4,C6).
        return tuple(2 * adc + round_index + 1 for adc in range(self.adc_count))

    @property
    def row_period_us(self) -> int:
        per_round = self.conversion_wait_us + self.read_overhead_us
        return (
            self.pre_discharge_us
            + self.settle_us
            + self.rounds * per_round
            + self.row_overhead_us
        )

    @property
    def frame_period_us(self) -> int:
        return ROWS * self.row_period_us

    @property
    def frame_rate_hz(self) -> float:
        return 1_000_000.0 / self.frame_period_us


def load_timing(config: Dict) -> MatrixTiming:
    matrix = config["matrix"]
    return MatrixTiming(
        pre_discharge_us=int(matrix.get("pre_discharge_us", 200)),
        settle_us=int(matrix.get("settle_us", 1000)),
        conversion_wait_us=int(matrix.get("conversion_wait_us", 4500)),
        read_overhead_us=int(matrix.get("read_overhead_us", 100)),
        row_overhead_us=int(matrix.get("row_overhead_us", 100)),
        adc_count=3,
    )


def iter_frame_actions(timing: MatrixTiming) -> Iterator[ScanAction]:
    """Yield the complete ordered action list for one 36-cell frame.

    Row selection rule: all rows are driven LOW during DISCHARGE, then all rows
    become HIGH_Z, then only the selected row is HIGH.  Unselected rows are never
    left LOW during the measurement.
    """
    for row in range(1, ROWS + 1):
        yield ScanAction(Phase.DISCHARGE, row, 0, timing.pre_discharge_us, note="all rows LOW")
        yield ScanAction(Phase.SETTLE, row, 0, timing.settle_us, note="selected row HIGH, others HIGH_Z")
        for round_index in range(timing.rounds):
            columns = timing.columns_for_round(round_index)
            yield ScanAction(
                Phase.CONVERT,
                row,
                round_index,
                timing.conversion_wait_us,
                columns=columns,
                note="start 3 ADCs with one column each",
            )
            yield ScanAction(
                Phase.READ,
                row,
                round_index,
                timing.read_overhead_us,
                columns=columns,
                note="read RDATA for each column",
            )
        yield ScanAction(Phase.NEXT_ROW, row, 0, timing.row_overhead_us, note="next row")
    yield ScanAction(Phase.FRAME_DONE, 0, 0, 0, note="36 cells ready")


def simulate_frame(timing: Optional[MatrixTiming] = None) -> List[ScanAction]:
    timing = timing or MatrixTiming()
    return list(iter_frame_actions(timing))


def covered_cells(actions: Iterable[ScanAction]) -> List[int]:
    cells: List[int] = []
    for action in actions:
        if action.phase == Phase.READ:
            for column in action.columns:
                cells.append(cell_index(action.row, column))
    return cells


def summarize(timing: Optional[MatrixTiming] = None) -> Dict[str, object]:
    timing = timing or MatrixTiming()
    actions = simulate_frame(timing)
    cells = covered_cells(actions)
    return {
        "rounds": timing.rounds,
        "row_period_us": timing.row_period_us,
        "frame_period_us": timing.frame_period_us,
        "frame_rate_hz": timing.frame_rate_hz,
        "actions": len(actions),
        "covered_cells": len(cells),
        "unique_cells": len(set(cells)),
        "all_cells_once": sorted(cells) == list(range(36)),
    }


class ScanStateMachine:
    """Minimal phase machine mirroring the firmware loop.

    Exposes the current phase/action and advances by the action duration.  It is
    intentionally free of GPIO/ADC calls so it can be unit-tested on the host.
    """

    def __init__(self, timing: Optional[MatrixTiming] = None) -> None:
        self.timing = timing or MatrixTiming()
        self.actions: List[ScanAction] = simulate_frame(self.timing)
        self.index = 0
        self.elapsed_us = 0
        self.cells: List[Optional[int]] = [None] * 36
        self.valid: List[bool] = [False] * 36

    @property
    def current(self) -> ScanAction:
        if self.index >= len(self.actions):
            return self.actions[-1]
        return self.actions[self.index]

    @property
    def finished(self) -> bool:
        return self.index >= len(self.actions) or self.current.phase == Phase.FRAME_DONE

    def advance(self, value: Optional[int] = 0) -> ScanAction:
        action = self.current
        if self.finished:
            return action
        if action.phase == Phase.READ:
            for column in action.columns:
                cell = cell_index(action.row, column)
                self.cells[cell] = int(value)
                self.valid[cell] = True
        self.elapsed_us += action.duration_us
        self.index += 1
        return action

    def run(self, value: int = 0) -> "ScanStateMachine":
        while not self.finished:
            self.advance(value)
        return self
