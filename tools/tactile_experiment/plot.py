"""Dependency-free SVG plots for the 12-channel press experiment."""
from __future__ import annotations

import html
import math
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

COLORS = [
    "#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#8c564b",
    "#17becf", "#e377c2", "#7f7f7f", "#bcbd22", "#393b79", "#637939",
]
CHANNEL_LABELS = [
    "ADC1_AIN0", "ADC1_AIN1", "ADC1_AIN2", "ADC1_AIN3",
    "ADC2_AIN0", "ADC2_AIN1", "ADC2_AIN2", "ADC2_AIN3",
    "ADC3_AIN0", "ADC3_AIN1", "ADC3_AIN2", "ADC3_AIN3",
]


def _esc(text: str) -> str:
    return html.escape(str(text), quote=True)


def _scale(value: float, lo: float, hi: float, out_lo: float, out_hi: float) -> float:
    if hi <= lo:
        return (out_lo + out_hi) / 2.0
    return out_lo + (value - lo) * (out_hi - out_lo) / (hi - lo)


def write_timeseries_svg(
    path,
    samples: Sequence[Dict],
    events: Sequence[Dict],
    title: str = "12-channel raw ADC during 36-point press experiment",
    max_points: int = 1500,
) -> None:
    width, height = 1700, 850
    left, right, top, bottom = 90, 300, 70, 90
    plot_w = width - left - right
    plot_h = height - top - bottom
    if not samples:
        path.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="800" height="200"><text x="20" y="50">No samples</text></svg>')
        return
    stride = max(1, len(samples) // max_points)
    picked = samples[::stride]
    t0 = picked[0]["host_monotonic_ns"]
    xs = [(s["host_monotonic_ns"] - t0) / 1e9 for s in picked]
    all_values = [v for s in picked for v in s["channels"] if v is not None]
    y_min, y_max = min(all_values), max(all_values)
    pad = max(1.0, (y_max - y_min) * 0.05)
    y_min -= pad
    y_max += pad
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="{}" height="{}" viewBox="0 0 {} {}">'.format(width, height, width, height),
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<text x="{}" y="32" font-family="Helvetica,Arial" font-size="20" font-weight="bold">{}</text>'.format(left, _esc(title)),
        '<text x="{}" y="52" font-family="Helvetica,Arial" font-size="12" fill="#555">Raw ADC counts; vertical lines = prompt events (red press, blue release). Per-point labels are experimental markers, not simultaneous pressure.</text>'.format(left),
    ]
    # axes
    parts.append('<line x1="{}" y1="{}" x2="{}" y2="{}" stroke="#222"/>'.format(left, top + plot_h, left + plot_w, top + plot_h))
    parts.append('<line x1="{}" y1="{}" x2="{}" y2="{}" stroke="#222"/>'.format(left, top, left, top + plot_h))
    for i in range(6):
        val = y_min + (y_max - y_min) * i / 5.0
        y = _scale(val, y_min, y_max, top + plot_h, top)
        parts.append('<line x1="{}" y1="{:.1f}" x2="{}" y2="{:.1f}" stroke="#eeeeee"/>'.format(left, y, left + plot_w, y))
        parts.append('<text x="{}" y="{:.1f}" font-family="Helvetica,Arial" font-size="11" text-anchor="end">{:.0f}</text>'.format(left - 8, y + 4, val))
    t_end = xs[-1] if xs else 1.0
    for i in range(6):
        t = t_end * i / 5.0
        x = _scale(t, 0, t_end, left, left + plot_w)
        parts.append('<text x="{:.1f}" y="{}" font-family="Helvetica,Arial" font-size="11" text-anchor="middle">{:.1f}s</text>'.format(x, top + plot_h + 20, t))
    parts.append('<text x="{:.1f}" y="{}" font-family="Helvetica,Arial" font-size="12" text-anchor="middle">host monotonic time (s)</text>'.format(left + plot_w / 2, height - 25))
    # event lines
    for event in events:
        kind = event.get("kind")
        if kind not in ("PRESS_START", "RELEASE_START"):
            continue
        ts = event.get("host_event_monotonic_ns") or event.get("host_monotonic_ns")
        if not ts:
            continue
        t = (int(ts) - t0) / 1e9
        if t < 0 or t > t_end:
            continue
        x = _scale(t, 0, t_end, left, left + plot_w)
        color = "#d62728" if kind == "PRESS_START" else "#1f77b4"
        parts.append('<line x1="{:.1f}" y1="{}" x2="{:.1f}" y2="{}" stroke="{}" stroke-width="1" opacity="0.35"/>'.format(x, top, x, top + plot_h, color))
        if kind == "PRESS_START" and event.get("point_id"):
            pid = int(event["point_id"])
            if pid == 1 or pid % 6 == 1 or pid == 36:
                parts.append('<text x="{:.1f}" y="{}" font-family="Helvetica,Arial" font-size="9" fill="#d62728" transform="rotate(-90 {:.1f},{})">{}</text>'.format(x - 2, top - 4, x - 2, top - 4, pid))
    # channel lines
    for ch in range(12):
        coords = []
        for x, sample in zip(xs, picked):
            value = sample["channels"][ch]
            if value is None:
                continue
            y = _scale(value, y_min, y_max, top + plot_h, top)
            coords.append("{:.1f},{:.1f}".format(_scale(x, 0, t_end, left, left + plot_w), y))
        if coords:
            parts.append('<polyline fill="none" stroke="{}" stroke-width="1.1" points="{}"/>'.format(COLORS[ch], " ".join(coords)))
    # legend
    lx, ly = left + plot_w + 20, top + 10
    for ch in range(12):
        y = ly + ch * 22
        parts.append('<line x1="{}" y1="{}" x2="{}" y2="{}" stroke="{}" stroke-width="3"/>'.format(lx, y, lx + 24, y, COLORS[ch]))
        parts.append('<text x="{}" y="{}" font-family="Helvetica,Arial" font-size="11">{}</text>'.format(lx + 30, y + 4, _esc(CHANNEL_LABELS[ch])))
    parts.append('</svg>')
    path.write_text("\n".join(parts))


def write_response_map_svg(path, points: Sequence[Dict], title: str, subtitle: str) -> None:
    width, height = 820, 820
    cell = 95
    left, top = 80, 120
    values = [abs(float(p.get("response_metric") or 0.0)) for p in points]
    lo, hi = min(values or [0]), max(values or [1])
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="{}" height="{}" viewBox="0 0 {} {}">'.format(width, height, width, height),
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<text x="40" y="35" font-family="Helvetica,Arial" font-size="19" font-weight="bold">{}</text>'.format(_esc(title)),
        '<text x="40" y="58" font-family="Helvetica,Arial" font-size="12" fill="#b00020">{}</text>'.format(_esc(subtitle)),
        '<text x="40" y="78" font-family="Helvetica,Arial" font-size="11" fill="#555">Metric = ||mean(press)-mean(local baseline)|| over 12 raw ADC channels. Not a simultaneous pressure heatmap.</text>',
    ]
    by_id = {int(p["point_id"]): p for p in points if p.get("point_id")}
    for row in range(1, 7):
        for col in range(1, 7):
            pid = (row - 1) * 6 + col
            p = by_id.get(pid, {})
            metric = abs(float(p.get("response_metric") or 0.0))
            ratio = 0.0 if hi <= lo else (metric - lo) / (hi - lo)
            # blue -> yellow -> red
            if ratio < 0.5:
                r = int(40 + ratio * 2 * (255 - 40)); g = int(80 + ratio * 2 * (220 - 80)); b = 200
            else:
                r = 255; g = int(220 - (ratio - 0.5) * 2 * 180); b = int(200 - (ratio - 0.5) * 2 * 170)
            x = left + (col - 1) * cell; y = top + (row - 1) * cell
            parts.append('<rect x="{}" y="{}" width="{}" height="{}" fill="rgb({},{},{})" stroke="#333"/>'.format(x, y, cell, cell, r, g, b))
            parts.append('<text x="{}" y="{}" font-family="Helvetica,Arial" font-size="11" fill="#111">R{}C{}</text>'.format(x + 5, y + 16, row, col))
            parts.append('<text x="{}" y="{}" font-family="Helvetica,Arial" font-size="10" fill="#111">{:.0f}</text>'.format(x + 5, y + 35, metric))
            if p.get("completed"):
                parts.append('<text x="{}" y="{}" font-family="Helvetica,Arial" font-size="9" fill="#111">done</text>'.format(x + 5, y + 80))
    # color bar
    bar_x, bar_y, bar_w, bar_h = left + 6 * cell + 25, top, 22, 6 * cell
    for i in range(60):
        ratio = i / 59.0
        if ratio < 0.5:
            r = int(40 + ratio * 2 * (255 - 40)); g = int(80 + ratio * 2 * (220 - 80)); b = 200
        else:
            r = 255; g = int(220 - (ratio - 0.5) * 2 * 180); b = int(200 - (ratio - 0.5) * 2 * 170)
        y = bar_y + bar_h - (i + 1) * bar_h / 60.0
        parts.append('<rect x="{}" y="{:.1f}" width="{}" height="{:.1f}" fill="rgb({},{},{})"/>'.format(bar_x, y, bar_w, bar_h / 60.0 + 0.5, r, g, b))
    parts.append('<text x="{}" y="{}" font-family="Helvetica,Arial" font-size="10">{:.0f}</text>'.format(bar_x + bar_w + 5, bar_y + 10, hi))
    parts.append('<text x="{}" y="{}" font-family="Helvetica,Arial" font-size="10">{:.0f}</text>'.format(bar_x + bar_w + 5, bar_y + bar_h, lo))
    parts.append('</svg>')
    path.write_text("\n".join(parts))


def write_confusion_svg(path, matrix, classes, title: str, subtitle: str) -> None:
    n = len(classes)
    cell = max(12, int(760 / max(1, n)))
    left, top = 100, 110
    width = left + n * cell + 60
    height = top + n * cell + 90
    maximum = max((max(row) for row in matrix), default=1) or 1
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="{}" height="{}" viewBox="0 0 {} {}">'.format(width, height, width, height),
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<text x="30" y="30" font-family="Helvetica,Arial" font-size="18" font-weight="bold">{}</text>'.format(_esc(title)),
        '<text x="30" y="50" font-family="Helvetica,Arial" font-size="12" fill="#b00020">{}</text>'.format(_esc(subtitle)),
        '<text x="30" y="70" font-family="Helvetica,Arial" font-size="11" fill="#555">Rows = truth, columns = prediction. Whole-round split; single round per class.</text>',
    ]
    for i in range(n):
        for j in range(n):
            value = matrix[i][j]
            ratio = value / maximum
            color = "rgb({},{},{})".format(int(255 - 200 * ratio), int(255 - 150 * ratio), int(255 - 80 * ratio))
            x = left + j * cell
            y = top + i * cell
            parts.append('<rect x="{}" y="{}" width="{}" height="{}" fill="{}" stroke="#ddd" stroke-width="0.5"/>'.format(x, y, cell, cell, color))
    for i in range(n):
        if n <= 12 or i % 6 == 0:
            parts.append('<text x="{}" y="{}" font-family="Helvetica,Arial" font-size="9" text-anchor="end">{}</text>'.format(left - 4, top + i * cell + cell - 2, _esc(classes[i])))
            parts.append('<text x="{}" y="{}" font-family="Helvetica,Arial" font-size="9" text-anchor="end">{}</text>'.format(left + i * cell + cell - 2, top - 4, _esc(classes[i])))
    parts.append('<text x="{}" y="{}" font-family="Helvetica,Arial" font-size="12" text-anchor="middle">prediction</text>'.format(left + n * cell / 2, top - 25))
    parts.append('<text x="{}" y="{}" font-family="Helvetica,Arial" font-size="12" transform="rotate(-90 {}, {})">truth</text>'.format(20, top + n * cell / 2, 20, top + n * cell / 2))
    parts.append('</svg>')
    path.write_text("\n".join(parts))
