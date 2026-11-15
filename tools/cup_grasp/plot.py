"""Dependency-free SVG curve for a cup-grasp trial."""
from __future__ import annotations

import html
from typing import Dict, List, Sequence


def _esc(text) -> str:
    return html.escape(str(text), quote=True)


def _scale(value, lo, hi, out_lo, out_hi):
    if hi <= lo:
        return (out_lo + out_hi) / 2.0
    return out_lo + (value - lo) * (out_hi - out_lo) / (hi - lo)


def write_tactile_svg(path, samples: Sequence[Dict], commands: Sequence[Dict], loads: Sequence[Dict]) -> None:
    width, height = 1500, 700
    left, right, top, bottom = 90, 60, 70, 80
    plot_w, plot_h = width - left - right, height - top - bottom
    points = [(int(s["host_monotonic_ns"]), float(s["delta"])) for s in samples
              if s.get("delta") is not None]
    if not points:
        path.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="800" height="200"><text x="20" y="50">No usable tactile samples</text></svg>')
        return
    t0 = points[0][0]
    xs = [(t - t0) / 1e9 for t, _ in points]
    ys = [v for _, v in points]
    y_lo, y_hi = min(ys), max(ys)
    pad = max(1.0, (y_hi - y_lo) * 0.08)
    y_lo -= pad
    y_hi += pad
    t_end = max(xs[-1], 0.001)
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="{}" height="{}" viewBox="0 0 {} {}">'.format(width, height, width, height),
        '<rect width="100%" height="100%" fill="#fff"/>',
        '<text x="{}" y="30" font-family="Helvetica,Arial" font-size="18" font-weight="bold">Cup trial tactile proxy (ADC delta from local baseline)</text>'.format(left),
        '<text x="{}" y="50" font-family="Helvetica,Arial" font-size="11" fill="#b00020">ADC counts, not pressure/force. Commands are PWM targets, not measured force/position.</text>'.format(left),
        '<line x1="{}" y1="{}" x2="{}" y2="{}" stroke="#222"/>'.format(left, top + plot_h, left + plot_w, top + plot_h),
        '<line x1="{}" y1="{}" x2="{}" y2="{}" stroke="#222"/>'.format(left, top, left, top + plot_h),
    ]
    for i in range(5):
        value = y_lo + (y_hi - y_lo) * i / 4.0
        y = _scale(value, y_lo, y_hi, top + plot_h, top)
        parts.append('<line x1="{}" y1="{:.1f}" x2="{}" y2="{:.1f}" stroke="#eee"/>'.format(left, y, left + plot_w, y))
        parts.append('<text x="{}" y="{:.1f}" font-family="Helvetica,Arial" font-size="10" text-anchor="end">{:.0f}</text>'.format(left - 5, y + 3, value))
    for i in range(6):
        t = t_end * i / 5.0
        x = _scale(t, 0, t_end, left, left + plot_w)
        parts.append('<text x="{:.1f}" y="{}" font-family="Helvetica,Arial" font-size="10" text-anchor="middle">{:.1f}s</text>'.format(x, top + plot_h + 18, t))
    for command in commands:
        ts = command.get("host_monotonic_ns")
        if not ts:
            continue
        t = (int(ts) - t0) / 1e9
        if not 0 <= t <= t_end:
            continue
        x = _scale(t, 0, t_end, left, left + plot_w)
        color = "#1f77b4" if command.get("kind") == "PULSE" else "#d62728"
        parts.append('<line x1="{:.1f}" y1="{}" x2="{:.1f}" y2="{}" stroke="{}" stroke-width="1" opacity="0.5"/>'.format(x, top, x, top + plot_h, color))
    for load in loads:
        ts = load.get("host_monotonic_ns")
        if not ts:
            continue
        t = (int(ts) - t0) / 1e9
        if not 0 <= t <= t_end:
            continue
        x = _scale(t, 0, t_end, left, left + plot_w)
        parts.append('<line x1="{:.1f}" y1="{}" x2="{:.1f}" y2="{}" stroke="#2ca02c" stroke-width="1.5" stroke-dasharray="4,2"/>'.format(x, top, x, top + plot_h))
        parts.append('<text x="{:.1f}" y="{}" font-family="Helvetica,Arial" font-size="9" fill="#2ca02c">{}</text>'.format(x + 2, top + 12, _esc(load.get("kind"))))
    coords = ["{:.1f},{:.1f}".format(_scale(x, 0, t_end, left, left + plot_w),
                                      _scale(y, y_lo, y_hi, top + plot_h, top)) for x, y in zip(xs, ys)]
    parts.append('<polyline fill="none" stroke="#6a3d9a" stroke-width="1.4" points="{}"/>'.format(" ".join(coords)))
    parts.append('</svg>')
    path.write_text("\n".join(parts))
