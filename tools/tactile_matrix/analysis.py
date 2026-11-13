"""Baseline, response, repeatability and crosstalk analysis for 36 cells.

All values are raw ADC counts unless the caller converts them.  This module does
not claim pressure/force units; counts -> resistance requires R_ref and is only
valid when the divider assumptions hold.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .model import CELL_COUNT, cell_coord, cell_index, cell_label

Matrix = List[Optional[float]]


@dataclass(frozen=True)
class Baseline:
    mean: Tuple[Optional[float], ...]
    std: Tuple[Optional[float], ...]
    count: Tuple[int, ...]


def baseline_from_frames(frames: Sequence) -> Baseline:
    values: List[List[float]] = [[] for _ in range(CELL_COUNT)]
    for frame in frames:
        for index in range(CELL_COUNT):
            if frame.valid[index] and frame.cells[index] is not None:
                values[index].append(float(frame.cells[index]))
    means: List[Optional[float]] = []
    stds: List[Optional[float]] = []
    counts: List[int] = []
    for series in values:
        counts.append(len(series))
        if len(series) >= 2:
            means.append(statistics.mean(series))
            stds.append(statistics.pstdev(series))
        elif len(series) == 1:
            means.append(series[0])
            stds.append(0.0)
        else:
            means.append(None)
            stds.append(None)
    return Baseline(tuple(means), tuple(stds), tuple(counts))


def delta_map(frame, baseline: Baseline) -> Matrix:
    result: Matrix = []
    for index in range(CELL_COUNT):
        if not frame.valid[index] or frame.cells[index] is None or baseline.mean[index] is None:
            result.append(None)
        else:
            result.append(float(frame.cells[index]) - float(baseline.mean[index]))
    return result


def localize(delta: Matrix, threshold: float = 0.0, positive_only: bool = True) -> Dict[str, object]:
    active = []
    for index, value in enumerate(delta):
        if value is None:
            continue
        if positive_only and value <= threshold:
            continue
        if not positive_only and abs(value) <= threshold:
            continue
        active.append((index, value))
    if not active:
        return {"peak_cell": None, "peak_row": None, "peak_column": None, "peak_value": None,
                "centroid_row": None, "centroid_column": None, "active_cells": []}
    peak_index, peak_value = max(active, key=lambda item: abs(item[1]))
    weights = [(index, max(0.0, value) if positive_only else abs(value)) for index, value in active]
    total = sum(weight for _, weight in weights)
    if total <= 0:
        row, column = cell_coord(peak_index)
        return {"peak_cell": cell_label(peak_index), "peak_row": row, "peak_column": column,
                "peak_value": peak_value, "centroid_row": float(row), "centroid_column": float(column),
                "active_cells": [cell_label(index) for index, _ in active]}
    centroid_row = 0.0
    centroid_column = 0.0
    for index, weight in weights:
        row, column = cell_coord(index)
        centroid_row += row * weight
        centroid_column += column * weight
    row, column = cell_coord(peak_index)
    return {
        "peak_cell": cell_label(peak_index),
        "peak_row": row,
        "peak_column": column,
        "peak_value": peak_value,
        "centroid_row": centroid_row / total,
        "centroid_column": centroid_column / total,
        "active_cells": [cell_label(index) for index, _ in active],
    }


def crosstalk_ratio(delta: Matrix, target_index: int) -> Optional[float]:
    if not 0 <= target_index < CELL_COUNT:
        raise ValueError("target_index must be 0..35")
    target = delta[target_index]
    if target is None or target <= 0:
        return None
    off = [abs(value) for index, value in enumerate(delta) if index != target_index and value is not None]
    if not off:
        return None
    return max(off) / float(target)


def repeatability(frames: Sequence) -> Dict[str, object]:
    series: List[List[float]] = [[] for _ in range(CELL_COUNT)]
    for frame in frames:
        for index in range(CELL_COUNT):
            if frame.valid[index] and frame.cells[index] is not None:
                series[index].append(float(frame.cells[index]))
    cells = []
    for index, values in enumerate(series):
        if len(values) < 2:
            cells.append({"cell": cell_label(index), "count": len(values), "mean": None, "std": None, "cv": None})
            continue
        mean = statistics.mean(values)
        std = statistics.pstdev(values)
        cells.append({
            "cell": cell_label(index),
            "count": len(values),
            "mean": mean,
            "std": std,
            "cv": (std / mean) if mean else None,
        })
    return {"cells": cells}


def contact_metric(delta: Matrix, baseline: Optional[Baseline] = None, k: float = 3.0,
                   min_abs: float = 0.0) -> Dict[str, object]:
    active = []
    for index, value in enumerate(delta):
        if value is None:
            continue
        threshold = min_abs
        if baseline is not None and baseline.std[index] is not None:
            threshold = max(min_abs, k * float(baseline.std[index]))
        if value > threshold:
            active.append((index, value))
    total = sum(value for _, value in active)
    peak = max((value for _, value in active), default=None)
    return {
        "active_count": len(active),
        "sum_delta": total,
        "max_delta": peak,
        "active_cells": [cell_label(index) for index, _ in active],
        "localization": localize(delta, threshold=0.0),
    }


def summarize_frames(frames: Sequence) -> Dict[str, object]:
    if not frames:
        return {"frames": 0}
    baseline = baseline_from_frames(frames)
    valid_counts = [frame.valid_count for frame in frames]
    periods = [frame.frame_period_us for frame in frames if frame.frame_period_us]
    return {
        "frames": len(frames),
        "valid_ratio": sum(valid_counts) / float(len(frames) * CELL_COUNT),
        "min_valid_per_frame": min(valid_counts),
        "max_valid_per_frame": max(valid_counts),
        "mean_frame_period_us": statistics.mean(periods) if periods else None,
        "baseline": {
            "mean": list(baseline.mean),
            "std": list(baseline.std),
            "count": list(baseline.count),
        },
    }
