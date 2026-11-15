"""ECharts option builders.  Invalid channels are omitted, never shown as zero."""

from __future__ import annotations

import math
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


def _axis_bounds(low: float, high: float) -> tuple[float, float]:
    """Round a raw-count axis to readable ticks with headroom for bar labels.

    Raw ADC values are never rescaled, but an axis whose ends are the sample
    minimum/maximum produces fractional ticks such as "2,134.55".
    """
    span = max(high - low, 1.0)
    step = 10 ** math.floor(math.log10(span / 4)) if span >= 4 else 1.0
    for factor in (1, 2, 2.5, 5, 10):
        candidate = step * factor
        if span / candidate <= 5:
            step = candidate
            break
    lower = math.floor(low / step) * step
    upper = math.ceil((high + span * 0.12) / step) * step
    if upper <= high:
        upper = high + step
    return lower, upper


def _config(value):
    if value is None:
        return None
    if hasattr(value, "matrix_channels"):
        return value
    try:
        from ..models import ChannelConfiguration

        return ChannelConfiguration.from_dict(value)
    except (TypeError, ValueError):
        return None


def matrix_view(channel_config=None) -> str:
    """Classify available matrix visualization without inventing 36 cells."""
    config = _config(channel_config)
    if config is None:
        return "NONE"
    if config.matrix_channels:
        return "CELLS"
    if config.electrode_channels:
        return "ELECTRODES"
    return "NONE"


def heatmap_options(frame: dict[str, Any], channel_config=None) -> dict[str, Any]:
    """Matrix-only heatmap.

    Positions come from channel metadata, never from ``divmod(channel_id)``.
    FSR channels are excluded even when their id happens to fit the grid.
    The reserved 12-electrode profile has no 36-cell positions, so it returns
    an empty option instead of drawing an invented pressure map.
    """
    config = _config(channel_config)
    if config is not None and config.electrode_channels and not config.matrix_channels:
        return {}
    rows = int(frame.get("matrix_rows") or (config.matrix_rows if config else 0) or 0)
    cols = int(frame.get("matrix_cols") or (config.matrix_cols if config else 0) or 0)
    values = _values(frame)
    positions = {}
    if config is not None:
        positions = {
            channel.channel_id: (channel.matrix_row, channel.matrix_col)
            for channel in config.matrix_channels
        }
    points = []
    valid = []
    for channel_id, value, is_valid in values:
        if not is_valid or value is None:
            continue
        if config is not None:
            if channel_id not in positions:
                continue
            row_value, col_value = positions[channel_id]
            if row_value is None or col_value is None:
                continue
            row, col = int(row_value), int(col_value)
        else:
            row, col = divmod(channel_id, cols) if cols else (0, 0)
        if row >= rows or col >= cols:
            continue
        points.append([col, row, round(float(value), 1)])
        valid.append(float(value))
    low, high = _range(valid)
    return {
        "backgroundColor": "transparent",
        "animationDuration": 250,
        "grid": {"left": 28, "right": 12, "top": 12, "bottom": 58},
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
                "name": "ADC 原始值",
                "type": "heatmap",
                "data": points,
                "label": {"show": rows * cols <= 36, "fontSize": 8, "color": "#0f172a"},
                "emphasis": {"itemStyle": {"shadowBlur": 8, "shadowColor": "rgba(15,23,42,.25)"}},
                "itemStyle": {"borderColor": "#ffffff", "borderWidth": 2, "borderRadius": 4},
            }
        ],
    }


def fsr_trend_options(history: list[dict[str, Any]]) -> dict[str, Any]:
    """Raw FSR counts (left axis) plus relative contact score (right axis)."""
    if not history:
        return {}
    channel_names: dict[int, str] = {}
    for item in history:
        for reading in item.get("readings") or []:
            channel_names.setdefault(int(reading["channel_id"]), str(reading.get("name") or f"FSR{reading['channel_id']}"))
    seq = [item.get("frame_seq") for item in history]
    palette = ["#0f766e", "#0ea5e9", "#f59e0b", "#8b5cf6"]
    series = []
    for order, channel_id in enumerate(sorted(channel_names)):
        data = []
        for item in history:
            match = next(
                (reading for reading in item.get("readings") or [] if int(reading["channel_id"]) == channel_id),
                None,
            )
            data.append(
                round(float(match["raw"]), 1)
                if match and match.get("valid") and match.get("raw") is not None
                else None
            )
        series.append(
            {
                "name": f"{channel_names[channel_id]} 原始 ADC",
                "type": "line",
                "yAxisIndex": 0,
                "data": data,
                "showSymbol": len(history) <= 12,
                "symbolSize": 5,
                "connectNulls": False,
                "lineStyle": {"width": 1.6, "color": palette[order % len(palette)]},
                "itemStyle": {"color": palette[order % len(palette)]},
            }
        )
    series.append(
        {
            "name": "接触评分",
            "type": "line",
            "yAxisIndex": 1,
            "data": [item.get("score") for item in history],
            "showSymbol": len(history) <= 12,
            "symbolSize": 5,
            "connectNulls": False,
            "lineStyle": {"width": 1.2, "type": "dashed", "color": "#b45309"},
            "itemStyle": {"color": "#b45309"},
        }
    )
    return {
        "backgroundColor": "transparent",
        "animationDuration": 250,
        "tooltip": {"trigger": "axis"},
        "legend": {"top": 0, "textStyle": {"color": TEXT, "fontSize": 10}, "icon": "roundRect"},
        "grid": {"left": 52, "right": 44, "top": 36, "bottom": 32},
        "xAxis": {
            "type": "category",
            "data": seq,
            "name": "帧序",
            "nameTextStyle": {"color": TEXT, "fontSize": 9},
            "axisLabel": {"color": TEXT, "fontSize": 9},
            "axisLine": {"lineStyle": {"color": AXIS}},
        },
        # Axis names are omitted on purpose: the legend already says "原始 ADC" and
        # "接触评分", and a top-left axis name collided with the legend text.
        "yAxis": [
            {
                "type": "value",
                "axisLabel": {"color": TEXT, "fontSize": 9},
                "splitLine": {"lineStyle": {"color": GRID}},
            },
            {
                "type": "value",
                "min": 0,
                "max": 1,
                "axisLabel": {"color": TEXT, "fontSize": 9},
                "splitLine": {"show": False},
            },
        ],
        "series": series,
    }


def bar_options(frame: dict[str, Any], channel_config=None, *, electrode_only: bool = False) -> dict[str, Any]:
    values = _values(frame)
    config = _config(channel_config)
    if electrode_only and config is not None:
        ids = {channel.channel_id for channel in config.electrode_channels}
        values = [item for item in values if item[0] in ids]
    labels = {
        channel.channel_id: channel.name or f"CH{channel.channel_id}"
        for channel in (config.channels if config is not None else ())
    }
    valid = [float(value) for _, value, is_valid in values if is_valid and value is not None]
    low, high = _range(valid)
    axis_low, axis_high = _axis_bounds(low, high)
    axis_low, axis_high = min(0, axis_low), max(0, axis_high)
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
        "grid": {"left": 12, "right": 14, "top": 32, "bottom": 12, "containLabel": True},
        "tooltip": {"trigger": "axis"},
        "xAxis": {
            "type": "category",
            "data": [labels.get(channel_id, f"CH{channel_id}") for channel_id, _, _ in values],
            "axisLine": {"lineStyle": {"color": AXIS}},
            "axisTick": {"show": False},
            "axisLabel": {"color": TEXT, "fontSize": 9, "interval": 0, "rotate": 0},
        },
        "yAxis": {
            "type": "value",
            "name": "ADC 计数",
            "nameTextStyle": {"color": TEXT, "fontSize": 9},
            "min": axis_low,
            "max": axis_high,
            "axisLabel": {"color": TEXT, "fontSize": 9},
            "splitLine": {"lineStyle": {"color": GRID}},
        },
        "series": [
            {
                "type": "bar",
                "data": data,
                "barMaxWidth": 24,
                # At most 14 channels (the 12-electrode profile) still fit a
                # readable count label above each bar without a hover tooltip.
                "label": {"show": len(values) <= 14, "position": "top", "fontSize": 8, "color": TEXT},
            }
        ],
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
                "name": "PWM 目标",
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


def unified_timeline_options(
    fsr_points: list[dict[str, Any]],
    pwm_events: list[dict[str, Any]],
) -> dict[str, Any]:
    """FSR raw counts and commanded PWM on one host-clock axis.

    Both streams carry ``host_monotonic_ns`` written by processes on the same
    Mac boot, so the offset is taken from the records themselves instead of
    re-stamping them.  The axis shows seconds since the first record; absolute
    UTC times stay in the tooltip caption/table.  A PWM point is never drawn as
    ACKed unless the console logged a matched ACK.
    """
    points = [p for p in fsr_points if isinstance(p, dict) and type(p.get("ns")) is int]
    events = [
        e
        for e in pwm_events
        if isinstance(e, dict)
        and type(e.get("sent_ns")) is int
        and type(e.get("pulse_us")) is int
    ]
    if not points and not events:
        return {}
    stamps = [p["ns"] for p in points] + [e["sent_ns"] for e in events]
    base = min(stamps)
    fsr_data = []
    for point in points:
        x = round((point["ns"] - base) / 1e9, 3)
        raw = point.get("raw")
        valid = bool(point.get("valid")) and raw is not None
        fsr_data.append([x, round(float(raw), 1) if valid else None])
    pwm_data = []
    for event in events:
        x = round((event["sent_ns"] - base) / 1e9, 3)
        result = event.get("result")
        if event.get("ack") and result == "ACKED":
            color, symbol = "#0ea5e9", "circle"
        elif result in ("TIMEOUT", "CORRUPT_RESPONSE", "FAILED"):
            color, symbol = "#dc2626", "triangle"
        else:
            color, symbol = "#94a3b8", "emptyCircle"
        pwm_data.append(
            {
                "value": [x, int(event["pulse_us"])],
                "itemStyle": {"color": color},
                "symbol": symbol,
                "symbolSize": 8 if symbol != "circle" else 6,
            }
        )
    return {
        "backgroundColor": "transparent",
        "animationDuration": 200,
        "tooltip": {"trigger": "axis"},
        "legend": {
            "top": 0,
            "right": 0,
            "textStyle": {"color": TEXT, "fontSize": 10},
            "icon": "roundRect",
        },
        "grid": {"left": 58, "right": 58, "top": 34, "bottom": 46},
        "dataZoom": [{"type": "inside"}],
        "xAxis": {
            "type": "value",
            "name": "秒（同一主机单调时钟）",
            "nameLocation": "middle",
            "nameGap": 28,
            "nameTextStyle": {"color": TEXT, "fontSize": 9},
            "axisLabel": {"color": TEXT, "fontSize": 9, "formatter": "{value}s"},
            "axisLine": {"lineStyle": {"color": AXIS}},
            "splitLine": {"lineStyle": {"color": GRID}},
        },
        "yAxis": [
            {
                "type": "value",
                "name": "FSR_A 原始计数",
                "nameTextStyle": {"color": TEXT, "fontSize": 9},
                "axisLabel": {"color": TEXT, "fontSize": 9},
                "splitLine": {"lineStyle": {"color": GRID}},
            },
            {
                "type": "value",
                "name": "PWM μs",
                "nameTextStyle": {"color": TEXT, "fontSize": 9},
                "axisLabel": {"color": TEXT, "fontSize": 9},
                "splitLine": {"show": False},
            },
        ],
        "series": [
            {
                "name": "FSR_A 原始 ADC",
                "type": "line",
                "yAxisIndex": 0,
                "data": fsr_data,
                "showSymbol": False,
                "connectNulls": False,
                "lineStyle": {"width": 1.5, "color": "#0f766e"},
                "itemStyle": {"color": "#0f766e"},
            },
            {
                "name": "PWM 目标（console ACK）",
                "type": "line",
                "yAxisIndex": 1,
                "step": "end",
                "data": pwm_data,
                "showSymbol": True,
                "connectNulls": True,
                "lineStyle": {"width": 1.4, "type": "dashed", "color": "#0ea5e9"},
                "itemStyle": {"color": "#0ea5e9"},
            },
        ],
    }
