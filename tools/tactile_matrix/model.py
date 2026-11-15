"""Core 6x6 matrix model and strict frame validation.

No serial, GPIO or hardware access happens in this module.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

ROWS = 6
COLS = 6
CELL_COUNT = ROWS * COLS

FLAG_SAT_HIGH = 0x01
FLAG_SAT_LOW = 0x02
FLAG_NEGATIVE = 0x04
FLAG_NEAR_RAIL = 0x08
FLAG_STUCK = 0x10
FLAG_NO_DATA = 0x20

FLAG_NAMES = {
    FLAG_SAT_HIGH: "SAT_HIGH",
    FLAG_SAT_LOW: "SAT_LOW",
    FLAG_NEGATIVE: "NEGATIVE",
    FLAG_NEAR_RAIL: "NEAR_RAIL",
    FLAG_STUCK: "STUCK",
    FLAG_NO_DATA: "NO_DATA",
}

ADC_MIN = -8388608
ADC_MAX = 8388607


class MatrixFrameError(ValueError):
    """The frame is structurally invalid or violates the matrix contract."""


def cell_index(row: int, column: int) -> int:
    if not 1 <= row <= ROWS or not 1 <= column <= COLS:
        raise ValueError("row must be 1..6 and column must be 1..6")
    return (row - 1) * COLS + (column - 1)


def cell_coord(index: int) -> Tuple[int, int]:
    if not 0 <= index < CELL_COUNT:
        raise ValueError("cell index must be 0..35")
    return index // COLS + 1, index % COLS + 1


def cell_label(index: int) -> str:
    row, column = cell_coord(index)
    return "R{}C{}".format(row, column)


def flag_names(mask: int) -> List[str]:
    return [name for bit, name in FLAG_NAMES.items() if mask & bit]


@dataclass(frozen=True)
class MatrixFrame:
    frame_seq: int
    timestamp_us: int
    cells: Tuple[Optional[int], ...]
    valid: Tuple[bool, ...]
    flags: Tuple[int, ...]
    frame_period_us: Optional[int]
    reference_mode: str
    raw: Dict[str, Any]

    @property
    def valid_count(self) -> int:
        return sum(1 for item in self.valid if item)

    def value(self, row: int, column: int) -> Optional[int]:
        return self.cells[cell_index(row, column)]


def load_config(path: Optional[Path] = None) -> Dict[str, Any]:
    if path is None:
        path = Path(__file__).resolve().parents[2] / "config/sensor_matrix.json"
    return json.loads(Path(path).read_text())


def _require_int(value: Any, name: str, minimum: Optional[int] = None, maximum: Optional[int] = None) -> int:
    if type(value) is not int:
        raise MatrixFrameError("{} must be an integer".format(name))
    if minimum is not None and value < minimum:
        raise MatrixFrameError("{} must be >= {}".format(name, minimum))
    if maximum is not None and value > maximum:
        raise MatrixFrameError("{} must be <= {}".format(name, maximum))
    return value


def _require_bool(value: Any, name: str) -> bool:
    if type(value) is not bool:
        raise MatrixFrameError("{} must be a boolean".format(name))
    return value


def build_frame(
    frame_seq: int,
    timestamp_us: int,
    cells: Sequence[Optional[int]],
    valid: Sequence[bool],
    flags: Sequence[int],
    frame_period_us: Optional[int] = None,
    reference_mode: str = "AVDD_AVSS",
) -> Dict[str, Any]:
    if len(cells) != CELL_COUNT or len(valid) != CELL_COUNT or len(flags) != CELL_COUNT:
        raise MatrixFrameError("cells/valid/flags must each contain 36 entries")
    return {
        "protocol_version": 1,
        "type": "MATRIX_FRAME",
        "device_id": "tactile-esp32-01",
        "firmware_version": "tactile-matrix-0.1.0",
        "scan_mode": "ROW_SCAN_6X6",
        "rows": ROWS,
        "cols": COLS,
        "cell_order": "ROW_MAJOR_R1C1",
        "frame_seq": frame_seq,
        "timestamp_us": timestamp_us,
        "frame_period_us": frame_period_us,
        "reference_mode": reference_mode,
        "cells": list(cells),
        "valid": list(valid),
        "flags": list(flags),
    }


def validate_frame(message: Dict[str, Any]) -> MatrixFrame:
    if message.get("type") != "MATRIX_FRAME":
        raise MatrixFrameError("type must be MATRIX_FRAME")
    if message.get("protocol_version") != 1:
        raise MatrixFrameError("protocol_version must be 1")
    if message.get("scan_mode") != "ROW_SCAN_6X6":
        raise MatrixFrameError("scan_mode must be ROW_SCAN_6X6")
    if message.get("rows") != ROWS or message.get("cols") != COLS:
        raise MatrixFrameError("rows/cols must be 6/6")
    if message.get("cell_order") != "ROW_MAJOR_R1C1":
        raise MatrixFrameError("cell_order must be ROW_MAJOR_R1C1")
    cells = message.get("cells")
    valid = message.get("valid")
    flags = message.get("flags")
    if not isinstance(cells, list) or len(cells) != CELL_COUNT:
        raise MatrixFrameError("cells must be a 36-element list")
    if not isinstance(valid, list) or len(valid) != CELL_COUNT:
        raise MatrixFrameError("valid must be a 36-element list")
    if not isinstance(flags, list) or len(flags) != CELL_COUNT:
        raise MatrixFrameError("flags must be a 36-element list")
    parsed_cells: List[Optional[int]] = []
    parsed_valid: List[bool] = []
    parsed_flags: List[int] = []
    for index in range(CELL_COUNT):
        is_valid = _require_bool(valid[index], "valid[{}]".format(index))
        if is_valid:
            value = _require_int(cells[index], "cells[{}]".format(index), ADC_MIN, ADC_MAX)
            parsed_cells.append(value)
            parsed_valid.append(True)
        else:
            if cells[index] is not None:
                raise MatrixFrameError("invalid cell {} must be null, not {!r}".format(index, cells[index]))
            parsed_cells.append(None)
            parsed_valid.append(False)
        parsed_flags.append(_require_int(flags[index], "flags[{}]".format(index), 0, 0x3F))
    frame_seq = _require_int(message.get("frame_seq"), "frame_seq", 0)
    timestamp_us = _require_int(message.get("timestamp_us"), "timestamp_us", 0)
    period = message.get("frame_period_us")
    if period is not None:
        period = _require_int(period, "frame_period_us", 0)
    reference = message.get("reference_mode", "")
    if reference not in ("AVDD_AVSS", "INTERNAL_2V048"):
        raise MatrixFrameError("unknown reference_mode")
    return MatrixFrame(
        frame_seq=frame_seq,
        timestamp_us=timestamp_us,
        cells=tuple(parsed_cells),
        valid=tuple(parsed_valid),
        flags=tuple(parsed_flags),
        frame_period_us=period,
        reference_mode=reference,
        raw=message,
    )
