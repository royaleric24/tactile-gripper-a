"""ECharts option builders.  Invalid channels are omitted, never shown as zero."""

from __future__ import annotations

from datetime import datetime
from typing import Any

TEXT = "#64748b"
AXIS = "#cbd5e1"
GRID = "#eef2f7"


def _values(frame: dict[str, Any]) -> list[tuple[int, float | None, bool]]:
    channels = frame.get("channels") or []
    mask = frame.get("valid_mask") or []
    ids = frame.get("channel_ids")
    if ids is None:
        ids = list(range(len(channels)))
    return [
        (int(channel_id), channels[index] if index < len(channels) else None, bool(mask[index]) if index < len(mask) else False)
        for index, channel_id in enumerate(ids)
    ]


def _range(values: list[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 1.0
    low, high = min(values), max(values)
    if low == high:
        return low - 1, high + 1
    return low, high


def heatmap_options(frame: dict[str, Any]) -> dict[str, Any]:
    rows = int(frame.get("matrix_rows") or 0)
    cols = int(frame.get("matrix_cols") or 0)
    values = _values(frame)
    points = []
    valid = []
    for channel_id, value, is_valid in values:
        if not is_valid or value is None:
            continue
        row, col = divmod(channel_id, cols) if cols else (0, 0)
        if row >= rows or col >= cols:
            continue
        points.append([col, row, round(float(value), 1)])
        valid.append(float(value))
    low, high = _range(valid)
    return {
        "backgroundColor": "transparent",
        "animationDuration": 250,
        "grid": {"left": 28, "right": 12, "top": 12, "bottom": 44},
        "tooltip": {"position": "top"},
        "xAxis": {
            "type": "category",
            "data": [f"C{index}" for index in range(cols)],
            "axisLine": {"lineStyle": {"color": AXIS}},
            "axisTick": {"show": False},
            "axisLabel": {"color": TEXT, "fontSize": 10},
            "splitArea": {"show": True, "areaStyle": {"color": ["#fbfdff", "#f7fafd"]}},
        },
        "yAxis": {
            "type": "category",
            "data": [f"R{index}" for index in range(rows)],
            "inverse": True,
            "axisLine": {"lineStyle": {"color": AXIS}},
            "axisTick": {"show": False},
            "axisLabel": {"color": TEXT, "fontSize": 10},
            "splitArea": {"show": True, "areaStyle": {"color": ["#fbfdff", "#f7fafd"]}},
        },
        "visualMap": {
            "min": low,
            "max": high,
            "calculable": False,
            "orient": "horizontal",
            "left": "center",
            "bottom": 0,
            "itemWidth": 10,
            "itemHeight": 90,
            "textStyle": {"color": TEXT, "fontSize": 10},
            "inRange": {"color": ["#eff6ff", "#ccfbf1", "#5eead4", "#14b8a6", "#0f766e", "#b45309"]},
        },
        "series": [
            {
                "name": "ADC raw",
                "type": "heatmap",
                "data": points,
                "label": {"show": rows * cols <= 36, "fontSize": 8, "color": "#0f172a"},
                "emphasis": {"itemStyle": {"shadowBlur": 8, "shadowColor": "rgba(15,23,42,.25)"}},
                "itemStyle": {"borderColor": "#ffffff", "borderWidth": 2, "borderRadius": 4},
            }
        ],
    }


def bar_options(frame: dict[str, Any]) -> dict[str, Any]:
    values = _values(frame)
    valid = [float(value) for _, value, is_valid in values if is_valid and value is not None]
    low, high = _range(valid)
    data = [
        {
            "value": round(float(value), 1) if is_valid and value is not None else None,
            "itemStyle": {"color": "#14b8a6" if is_valid else "#e2e8f0", "borderRadius": [3, 3, 0, 0]},
        }
        for _, value, is_valid in values
    ]
    return {
        "backgroundColor": "transparent",
        "animationDuration": 250,
        "grid": {"left": 42, "right": 14, "top": 14, "bottom": 30},
        "tooltip": {"trigger": "axis"},
        "xAxis": {
            "type": "category",
            "data": [f"CH{channel_id}" for channel_id, _, _ in values],
            "axisLine": {"lineStyle": {"color": AXIS}},
            "axisTick": {"show": False},
            "axisLabel": {"color": TEXT, "fontSize": 9, "interval": 0, "rotate": 0},
        },
        "yAxis": {
            "type": "value",
            "min": max(0, low - 50),
            "max": high + 50,
            "axisLabel": {"color": TEXT, "fontSize": 9},
            "splitLine": {"lineStyle": {"color": GRID}},
        },
        "series": [{"type": "bar", "data": data, "barMaxWidth": 24}],
    }


def line_options(frames: list[dict[str, Any]], channel_ids: list[int]) -> dict[str, Any]:
    if not frames:
        return {}
    base_ns = frames[0].get("host_received_ns") or 0
    x = [round(((item.get("host_received_ns") or base_ns) - base_ns) / 1e9, 3) for item in frames]
    series = []
    palette = ["#0f766e", "#0ea5e9", "#f59e0b", "#8b5cf6", "#ef4444", "#14b8a6", "#64748b", "#d946ef"]
    for order, channel_id in enumerate(channel_ids):
        data = []
        for item in frames:
            ids = item.get("channel_ids")
            if ids is None:
                ids = list(range(len(item.get("channels") or [])))
            try:
                index = ids.index(channel_id)
            except ValueError:
                data.append(None)
                continue
            channels = item.get("channels") or []
            mask = item.get("valid_mask") or []
            valid = index < len(mask) and mask[index]
            data.append(channels[index] if valid and index < len(channels) else None)
        series.append(
            {
                "name": f"CH{channel_id}",
                "type": "line",
                "data": data,
                "showSymbol": False,
                "smooth": 0.15,
                "connectNulls": False,
                "lineStyle": {"width": 1.6, "color": palette[order % len(palette)]},
                "itemStyle": {"color": palette[order % len(palette)]},
            }
        )
    return {
        "backgroundColor": "transparent",
        "animationDuration": 250,
        "tooltip": {"trigger": "axis"},
        "legend": {"top": 0, "right": 0, "textStyle": {"color": TEXT, "fontSize": 10}, "icon": "roundRect"},
        "grid": {"left": 46, "right": 16, "top": 34, "bottom": 34},
        "xAxis": {
            "type": "category",
            "data": x,
            "name": "s",
            "nameTextStyle": {"color": TEXT, "fontSize": 9},
            "axisLabel": {"color": TEXT, "fontSize": 9},
            "axisLine": {"lineStyle": {"color": AXIS}},
        },
        "yAxis": {
            "type": "value",
            "axisLabel": {"color": TEXT, "fontSize": 9},
            "splitLine": {"lineStyle": {"color": GRID}},
        },
        "series": series,
    }


def pwm_timeline_options(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Commanded PWM targets by host receive time (ACK is not position)."""
    points = []
    for event in events:
        if event.get("record_type") != "CONTROL_EVENT":
            continue
        if event.get("action") != "SET_PWM" or event.get("commanded_pwm_us") is None:
            continue
        stamp = event.get("timestamp_utc")
        try:
            moment = datetime.fromisoformat(stamp)
        except (TypeError, ValueError):
            continue
        points.append((moment, int(event["commanded_pwm_us"]), event.get("stage", ""), bool(event.get("device_ack"))))
    if not points:
        return {}
    base = points[0][0]
    x = [f"{round((moment - base).total_seconds(), 3):.3f}s" for moment, _, _, _ in points]
    values = []
    colors = []
    for _, value, stage, ack in points:
        values.append(value)
        if stage in ("FAILED", "REJECTED", "UNSUPPORTED"):
            colors.append("#dc2626")
        elif ack:
            colors.append("#0f766e")
        else:
            colors.append("#94a3b8")
    return {
        "backgroundColor": "transparent",
        "animationDuration": 250,
        "tooltip": {"trigger": "axis"},
        "grid": {"left": 48, "right": 16, "top": 18, "bottom": 32},
        "xAxis": {
            "type": "category",
            "data": x,
            "name": "s",
            "nameTextStyle": {"color": TEXT, "fontSize": 9},
            "axisLabel": {"color": TEXT, "fontSize": 9},
            "axisLine": {"lineStyle": {"color": AXIS}},
            "splitLine": {"lineStyle": {"color": GRID}},
        },
        "yAxis": {
            "type": "value",
            "name": "μs",
            "nameTextStyle": {"color": TEXT, "fontSize": 9},
            "axisLabel": {"color": TEXT, "fontSize": 9},
            "splitLine": {"lineStyle": {"color": GRID}},
        },
        "series": [
            {
                "name": "commanded PWM",
                "type": "line",
                "step": "end",
                "data": [
                    {"value": value, "itemStyle": {"color": color}}
                    for value, color in zip(values, colors)
                ],
                "showSymbol": True,
                "symbolSize": 5,
                "lineStyle": {"width": 1.8, "color": "#0ea5e9"},
            }
        ],
    }
