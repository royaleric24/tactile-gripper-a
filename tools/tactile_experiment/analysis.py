"""Automatic analysis of the 36-point press experiment.

This analysis is deliberately conservative: it reports raw-count deltas and
exploratory separability, not calibrated pressure.  If the baseline is dominated
by saturation/common-mode/MUX artifacts, it marks the run INVALID_OR_FLOATING.
"""
from __future__ import annotations

import bisect
import csv
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .plot import CHANNEL_LABELS, write_response_map_svg, write_timeseries_svg

SAT_HIGH = 8388607
LOCAL_BASELINE_S = 1.5
RELEASE_WINDOW_S = 1.5


def _to_int(value, default=None):
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def load_samples(path: Path) -> List[Dict[str, Any]]:
    samples: List[Dict[str, Any]] = []
    with open(path, encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            channels = [_to_int(row.get("ch{}".format(i))) for i in range(12)]
            valid = [row.get("valid{}".format(i)) == "1" for i in range(12)]
            flags = [_to_int(row.get("flag{}".format(i)), 0) or 0 for i in range(12)]
            host_ns = _to_int(row.get("host_monotonic_ns"))
            device_us = _to_int(row.get("device_timestamp_us"))
            frame_seq = _to_int(row.get("frame_seq"))
            if host_ns is None or device_us is None or frame_seq is None:
                continue
            samples.append({
                "host_monotonic_ns": host_ns,
                "host_unix_ns": _to_int(row.get("host_received_unix_ns")),
                "device_timestamp_us": device_us,
                "frame_seq": frame_seq,
                "channels": channels,
                "valid": valid,
                "flags": flags,
            })
    samples.sort(key=lambda item: item["host_monotonic_ns"])
    return samples


def load_events(path: Path) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    if not path.is_file():
        return events
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if not isinstance(event, dict):
                continue
            if "host_event_monotonic_ns" not in event and "host_monotonic_ns" in event:
                event["host_event_monotonic_ns"] = event["host_monotonic_ns"]
            if event.get("host_event_monotonic_ns"):
                events.append(event)
    events.sort(key=lambda item: int(item["host_event_monotonic_ns"]))
    return events


def _window(samples: Sequence[Dict], start_ns: int, end_ns: int) -> List[Dict]:
    # Half-open [start, end): a press boundary frame must not leak into the local
    # baseline, and the release boundary frame must not leak into the press mean.
    return [s for s in samples if start_ns <= s["host_monotonic_ns"] < end_ns]


def _values(samples: Sequence[Dict], channel: int) -> List[int]:
    return [int(s["channels"][channel]) for s in samples
            if s["channels"][channel] is not None and s["valid"][channel]]


def _mean(values: Sequence[float]) -> Optional[float]:
    return statistics.mean(values) if values else None


def _std(values: Sequence[float]) -> Optional[float]:
    return statistics.pstdev(values) if len(values) >= 2 else (0.0 if values else None)


def _slope_per_s(samples: Sequence[Dict], channel: int) -> Optional[float]:
    pairs = [(s["host_monotonic_ns"] / 1e9, int(s["channels"][channel]))
             for s in samples if s["channels"][channel] is not None and s["valid"][channel]]
    if len(pairs) < 2:
        return None
    t0 = pairs[0][0]
    xs = [t - t0 for t, _ in pairs]
    ys = [v for _, v in pairs]
    mx = statistics.mean(xs)
    my = statistics.mean(ys)
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom


def _nearest(samples: Sequence[Dict], host_ns: int) -> Tuple[Optional[Dict], Optional[float]]:
    if not samples:
        return None, None
    keys = [s["host_monotonic_ns"] for s in samples]
    index = bisect.bisect_left(keys, host_ns)
    candidates = []
    for pos in (index - 1, index):
        if 0 <= pos < len(samples):
            candidates.append((abs(samples[pos]["host_monotonic_ns"] - host_ns), samples[pos]))
    if not candidates:
        return None, None
    delta, sample = min(candidates, key=lambda item: item[0])
    return sample, delta / 1_000_000.0


def _corr(a: Sequence[float], b: Sequence[float]) -> Optional[float]:
    if len(a) != len(b) or len(a) < 2:
        return None
    ma, mb = statistics.mean(a), statistics.mean(b)
    sa = math.sqrt(sum((x - ma) ** 2 for x in a))
    sb = math.sqrt(sum((x - mb) ** 2 for x in b))
    if sa == 0 or sb == 0:
        return None
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (sa * sb)


def _cosine(a: Sequence[float], b: Sequence[float]) -> Optional[float]:
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return None
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


def _frame_stats(samples: Sequence[Dict]) -> Dict[str, Any]:
    if not samples:
        return {"frames": 0}
    seqs = [s["frame_seq"] for s in samples]
    missing = duplicates = out_of_order = 0
    for prev, cur in zip(seqs, seqs[1:]):
        if cur == prev:
            duplicates += 1
        elif cur < prev:
            out_of_order += 1
        elif cur > prev + 1:
            missing += cur - prev - 1
    duration = (samples[-1]["host_monotonic_ns"] - samples[0]["host_monotonic_ns"]) / 1e9
    device_duration = (samples[-1]["device_timestamp_us"] - samples[0]["device_timestamp_us"]) / 1e6
    valid_total = sum(sum(1 for v in s["valid"] if v) for s in samples)
    return {
        "frames": len(samples),
        "host_duration_s": duration,
        "device_duration_s": device_duration,
        "host_frame_rate_hz": len(samples) / duration if duration > 0 else None,
        "device_frame_rate_hz": (len(samples) - 1) / device_duration if device_duration > 0 else None,
        "missing_frames": missing,
        "duplicates": duplicates,
        "out_of_order": out_of_order,
        "valid_ratio": valid_total / float(len(samples) * 12),
        "first_frame_seq": seqs[0],
        "last_frame_seq": seqs[-1],
    }


def _baseline_stats(samples: Sequence[Dict], start_ns: int, end_ns: int) -> Dict[str, Any]:
    window = _window(samples, start_ns, end_ns)
    channels = []
    for ch in range(12):
        values = _values(window, ch)
        mean = _mean(values)
        std = _std(values)
        channels.append({
            "channel": ch,
            "label": CHANNEL_LABELS[ch],
            "valid": len(values),
            "mean": mean,
            "std": std,
            "min": min(values) if values else None,
            "max": max(values) if values else None,
            "drift_per_s": _slope_per_s(window, ch),
            "saturation_fraction": (sum(1 for v in values if v >= SAT_HIGH) / len(values)) if values else None,
            "negative_fraction": (sum(1 for v in values if v < 0) / len(values)) if values else None,
        })
    return {"start_host_ns": start_ns, "end_host_ns": end_ns, "samples": len(window), "channels": channels}


def _common_mode(samples: Sequence[Dict]) -> Dict[str, Any]:
    if not samples:
        return {}
    means = []
    channel_values = [[] for _ in range(12)]
    all_sat = all_neg = any_sat = 0
    for sample in samples:
        valid_values = [v for v, ok in zip(sample["channels"], sample["valid"]) if ok and v is not None]
        if len(valid_values) == 12:
            # Correlations need aligned values for every channel; use only frames
            # with all 12 valid so a single null cannot empty the common vector.
            means.append(statistics.mean(valid_values))
            for ch, (value, ok) in enumerate(zip(sample["channels"], sample["valid"])):
                channel_values[ch].append(value)
        if len(valid_values) == 12:
            if all(v >= SAT_HIGH for v in valid_values):
                all_sat += 1
            if all(v < 0 for v in valid_values):
                all_neg += 1
            if any(v >= SAT_HIGH for v in valid_values):
                any_sat += 1
    common = means
    correlations = []
    for ch in range(12):
        series = channel_values[ch]
        if len(series) == len(common) and len(common) > 2:
            r = _corr(series, common)
            if r is not None:
                correlations.append(abs(r))
    frames = len(samples)
    return {
        "frames": frames,
        "frames_all_saturated": all_sat,
        "frames_all_negative": all_neg,
        "frames_any_saturated": any_sat,
        "all_saturated_fraction": all_sat / frames if frames else None,
        "all_negative_fraction": all_neg / frames if frames else None,
        "any_saturated_fraction": any_sat / frames if frames else None,
        "mean_abs_correlation_with_frame_mean": statistics.mean(correlations) if correlations else None,
        "channel_abs_correlations": correlations,
    }


def _point_windows(events: Sequence[Dict]) -> List[Dict[str, Any]]:
    by_point: Dict[int, Dict[str, Any]] = {}
    for event in events:
        pid = event.get("point_id")
        if not isinstance(pid, int):
            continue
        entry = by_point.setdefault(pid, {"point_id": pid})
        kind = event.get("kind")
        if kind in ("POINT_READY", "USER_READY", "PRESS_START", "RELEASE_START", "POINT_DONE"):
            entry.setdefault(kind, event)
    result = []
    for pid in sorted(by_point):
        entry = by_point[pid]
        press = entry.get("PRESS_START")
        release = entry.get("RELEASE_START")
        ready = entry.get("POINT_READY")
        result.append({
            "point_id": pid,
            "row": (pid - 1) // 6 + 1,
            "column": (pid - 1) % 6 + 1,
            "label": "R{}C{}".format((pid - 1) // 6 + 1, (pid - 1) % 6 + 1),
            "ready_ns": int(ready["host_event_monotonic_ns"]) if ready else None,
            "press_ns": int(press["host_event_monotonic_ns"]) if press else None,
            "release_ns": int(release["host_event_monotonic_ns"]) if release else None,
            "completed": bool(press and release),
        })
    return result


def _point_responses(samples: Sequence[Dict], points: Sequence[Dict]) -> List[Dict[str, Any]]:
    responses = []
    for point in points:
        press_ns = point.get("press_ns")
        release_ns = point.get("release_ns")
        result = dict(point)
        result.update({"channels": [], "response_metric": 0.0, "max_abs_z": 0.0})
        if press_ns is None or release_ns is None or release_ns <= press_ns:
            result["completed"] = False
            responses.append(result)
            continue
        pre_start = press_ns - int(LOCAL_BASELINE_S * 1e9)
        baseline = _window(samples, pre_start, press_ns)
        if len(baseline) < 3:
            baseline = _window(samples, release_ns, release_ns + int(LOCAL_BASELINE_S * 1e9))
        press = _window(samples, press_ns, release_ns)
        post = _window(samples, release_ns, release_ns + int(RELEASE_WINDOW_S * 1e9))
        if not press:
            result["completed"] = False
            responses.append(result)
            continue
        deltas = []
        zs = []
        channel_results = []
        saturated = 0
        for ch in range(12):
            base_values = _values(baseline, ch)
            press_values = _values(press, ch)
            post_values = _values(post, ch)
            base_mean = _mean(base_values)
            base_std = _std(base_values)
            press_mean = _mean(press_values)
            post_mean = _mean(post_values)
            delta = (press_mean - base_mean) if press_mean is not None and base_mean is not None else None
            z = (delta / base_std) if delta is not None and base_std not in (None, 0) else None
            sat = sum(1 for v in press_values if v >= SAT_HIGH)
            saturated += sat
            if delta is not None:
                deltas.append(delta)
            if z is not None:
                zs.append(z)
            channel_results.append({
                "channel": ch,
                "label": CHANNEL_LABELS[ch],
                "baseline_mean": base_mean,
                "baseline_std": base_std,
                "press_mean": press_mean,
                "post_mean": post_mean,
                "delta": delta,
                "z": z,
                "press_valid": len(press_values),
                "press_saturation_fraction": sat / len(press_values) if press_values else None,
                "recovered_delta": (post_mean - base_mean) if post_mean is not None and base_mean is not None else None,
            })
        metric = math.sqrt(sum(d * d for d in deltas)) if deltas else 0.0
        max_z = max((abs(z) for z in zs), default=0.0)
        result.update({
            "channels": channel_results,
            "response_metric": metric,
            "max_abs_z": max_z,
            "press_saturation_fraction": saturated / float(len(press) * 12) if press else None,
            "press_samples": len(press),
            "baseline_samples": len(baseline),
        })
        responses.append(result)
    return responses


def _similarity(points: Sequence[Dict]) -> Dict[str, Any]:
    vectors = []
    labels = []
    for point in points:
        if not point.get("completed"):
            continue
        vector = [float(ch.get("delta") or 0.0) for ch in point.get("channels", [])]
        if len(vector) != 12:
            continue
        vectors.append(vector)
        labels.append(point["label"])
    matrix = []
    for i, a in enumerate(vectors):
        row = []
        for j, b in enumerate(vectors):
            value = _cosine(a, b)
            row.append(value)
        matrix.append(row)
    # A single press per class cannot yield a valid leave-one-out classifier:
    # each class has exactly one sample, so a nearest-neighbour "accuracy" would
    # be meaningless.  Report similarity only; independent repeats are required.
    accuracy = None
    off_diagonal = []
    for i, row in enumerate(matrix):
        for j, value in enumerate(row):
            if i != j and value is not None:
                off_diagonal.append(value)
    return {
        "points": labels,
        "cosine_matrix": matrix,
        "mean_off_diagonal_cosine": statistics.mean(off_diagonal) if off_diagonal else None,
        "nearest_neighbour_loo_accuracy": accuracy,
        "note": "No classifier accuracy is computed: one press per class is insufficient. Independent repeats are required.",
    }


def _alignment(samples: Sequence[Dict], events: Sequence[Dict]) -> Dict[str, Any]:
    if not samples:
        return {}
    offsets = []
    for sample in samples:
        offsets.append(sample["host_monotonic_ns"] / 1000.0 - sample["device_timestamp_us"])
    # slope of offset vs host time (us per second)
    t0 = samples[0]["host_monotonic_ns"] / 1e9
    xs = [s["host_monotonic_ns"] / 1e9 - t0 for s in samples]
    mx = statistics.mean(xs)
    my = statistics.mean(offsets)
    denom = sum((x - mx) ** 2 for x in xs)
    drift = sum((x - mx) * (y - my) for x, y in zip(xs, offsets)) / denom if denom else None
    errors = []
    event_rows = []
    for event in events:
        if event.get("kind") not in ("PRESS_START", "RELEASE_START", "POINT_READY"):
            continue
        ns = event.get("host_event_monotonic_ns")
        if not ns:
            continue
        sample, error_ms = _nearest(samples, int(ns))
        if error_ms is not None:
            errors.append(abs(error_ms))
        event_rows.append({
            "kind": event.get("kind"),
            "point_id": event.get("point_id"),
            "error_ms": error_ms,
            "nearest_frame_seq": sample["frame_seq"] if sample else None,
            "nearest_device_timestamp_us": sample["device_timestamp_us"] if sample else None,
            "latest_frame_age_ms": event.get("latest_frame_age_ms"),
        })
    return {
        "event_count": len(event_rows),
        "median_event_alignment_error_ms": statistics.median(errors) if errors else None,
        "max_event_alignment_error_ms": max(errors) if errors else None,
        "host_device_offset_us_mean": statistics.mean(offsets) if offsets else None,
        "host_device_offset_drift_us_per_s": drift,
        "events": event_rows[:200],
    }


def analyze_run(run_dir: Path, make_plots: bool = True) -> Dict[str, Any]:
    run_dir = Path(run_dir)
    samples = load_samples(run_dir / "samples.csv")
    events = load_events(run_dir / "events.jsonl")
    meta = {}
    run = {}
    if (run_dir / "meta.json").is_file():
        meta = json.loads((run_dir / "meta.json").read_text())
    if (run_dir / "run.json").is_file():
        run = json.loads((run_dir / "run.json").read_text())
    frame_stats = _frame_stats(samples)
    starts = [e for e in events if e.get("kind") == "BASELINE_START"]
    ends = [e for e in events if e.get("kind") == "BASELINE_END"]
    pre_start = int(starts[0]["host_event_monotonic_ns"]) if starts else (samples[0]["host_monotonic_ns"] if samples else 0)
    pre_end = int(ends[0]["host_event_monotonic_ns"]) if ends else (samples[min(len(samples) - 1, 260)]["host_monotonic_ns"] if samples else 0)
    baseline = _baseline_stats(samples, pre_start, pre_end)
    post = None
    if len(starts) >= 2 and len(ends) >= 2:
        post = _baseline_stats(samples, int(starts[-1]["host_event_monotonic_ns"]), int(ends[-1]["host_event_monotonic_ns"]))
    common = _common_mode(samples)
    points = _point_windows(events)
    responses = _point_responses(samples, points)
    similarity = _similarity(responses)
    alignment = _alignment(samples, events)
    completed = sum(1 for p in responses if p.get("completed"))
    sat_frac = common.get("any_saturated_fraction") or 0.0
    corr = common.get("mean_abs_correlation_with_frame_mean")
    quality = "INVALID_OR_FLOATING"
    reasons = []
    if sat_frac > 0.10:
        reasons.append("any-channel saturation fraction {:.1%} > 10%".format(sat_frac))
    if corr is not None and corr > 0.80:
        reasons.append("mean |corr(channel, frame mean)| {:.2f} > 0.80".format(corr))
    if not reasons:
        quality = "EXPLORATORY_ONLY"
        reasons.append("baseline is not rail/saturation dominated, but only one press round was recorded")
    analysis = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "data_kind": "REAL_HARDWARE_SERIAL",
        "run_dir": str(run_dir),
        "frames": frame_stats,
        "meta": meta,
        "run_summary": run.get("summary"),
        "baseline_pre": baseline,
        "baseline_post": post,
        "common_mode": common,
        "points": responses,
        "completed_points": completed,
        "expected_points": 36,
        "similarity": similarity,
        "alignment": alignment,
        "signal_quality": quality,
        "quality_reasons": reasons,
        "interpretation": (
            "Raw ADC counts only. This is an exploratory press-response experiment; "
            "it is not a calibrated pressure measurement and a single round cannot prove 36-class accuracy."
        ),
    }
    (run_dir / "analysis.json").write_text(json.dumps(analysis, indent=2) + "\n")
    # responses.csv
    with open(run_dir / "responses.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        header = ["point_id", "row", "column", "label", "completed", "response_metric", "max_abs_z",
                  "press_saturation_fraction", "baseline_samples", "press_samples"]
        for ch in range(12):
            header.extend(["d{}".format(ch), "z{}".format(ch), "base{}".format(ch), "press{}".format(ch)])
        writer.writerow(header)
        for point in responses:
            row = [point.get("point_id"), point.get("row"), point.get("column"), point.get("label"),
                   int(bool(point.get("completed"))), point.get("response_metric"), point.get("max_abs_z"),
                   point.get("press_saturation_fraction"), point.get("baseline_samples"), point.get("press_samples")]
            channels = point.get("channels", [])
            for idx in range(12):
                ch = channels[idx] if idx < len(channels) else {}
                row.extend([ch.get("delta"), ch.get("z"), ch.get("baseline_mean"), ch.get("press_mean")])
            writer.writerow(row)
    if make_plots:
        write_timeseries_svg(run_dir / "timeseries.svg", samples, events)
        write_response_map_svg(
            run_dir / "response_map.svg",
            responses,
            "36-point press experiment: per-point 12-channel response statistic",
            "EXPERIMENTAL STATISTIC, NOT A SIMULTANEOUS PRESSURE HEATMAP",
        )
    _write_report(run_dir, analysis)
    return analysis


def _fmt(value, digits=1):
    if value is None:
        return "-"
    if isinstance(value, float):
        return "{:.{}f}".format(value, digits)
    return str(value)


def _write_report(run_dir: Path, analysis: Dict[str, Any]) -> None:
    frames = analysis["frames"]
    common = analysis["common_mode"]
    similarity = analysis["similarity"]
    lines = [
        "# 36-Point Press Experiment Report",
        "",
        "Generated: {}".format(analysis["timestamp_utc"]),
        "",
        "## Verdict",
        "",
        "- Signal quality: **{}**".format(analysis["signal_quality"]),
        "- Reasons: {}".format("; ".join(analysis["quality_reasons"])),
        "- Completed points: **{}/36**".format(analysis["completed_points"]),
        "- Raw data: `{}`".format(analysis["run_dir"]),
        "",
        "**This is an exploratory raw-ADC experiment, not a validated 36-point pressure measurement. "
        "A single round cannot establish 36-class accuracy.**",
        "",
        "## Acquisition",
        "",
        "| metric | value |",
        "|---|---:|",
        "| frames | {} |".format(frames.get("frames")),
        "| host duration (s) | {} |".format(_fmt(frames.get("host_duration_s"), 3)),
        "| host frame rate (Hz) | {} |".format(_fmt(frames.get("host_frame_rate_hz"), 3)),
        "| device frame rate (Hz) | {} |".format(_fmt(frames.get("device_frame_rate_hz"), 3)),
        "| missing / duplicates / out-of-order | {} / {} / {} |".format(
            frames.get("missing_frames"), frames.get("duplicates"), frames.get("out_of_order")),
        "| valid ratio | {} |".format(_fmt(frames.get("valid_ratio"), 4)),
        "",
        "## Baseline (pre-contact)",
        "",
        "| CH | label | mean | std | min | max | drift/s | sat | neg |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for ch in analysis["baseline_pre"]["channels"]:
        lines.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
            ch["channel"], ch["label"], _fmt(ch["mean"]), _fmt(ch["std"]), ch["min"], ch["max"],
            _fmt(ch["drift_per_s"]), _fmt(ch["saturation_fraction"], 3), _fmt(ch["negative_fraction"], 3)))
    lines += [
        "",
        "## Common-mode / artifact indicators",
        "",
        "- frames all 12 saturated: {} / {} ({})".format(common.get("frames_all_saturated"), common.get("frames"),
                                                        _fmt(common.get("all_saturated_fraction"), 3)),
        "- frames any channel saturated: {} / {} ({})".format(common.get("frames_any_saturated"), common.get("frames"),
                                                              _fmt(common.get("any_saturated_fraction"), 3)),
        "- frames all 12 negative: {} / {} ({})".format(common.get("frames_all_negative"), common.get("frames"),
                                                        _fmt(common.get("all_negative_fraction"), 3)),
        "- mean |corr(channel, frame mean)|: {}".format(_fmt(common.get("mean_abs_correlation_with_frame_mean"), 3)),
        "",
        "## Event alignment",
        "",
        "- events checked: {}".format(analysis["alignment"].get("event_count")),
        "- median event-to-nearest-frame error: {} ms".format(_fmt(analysis["alignment"].get("median_event_alignment_error_ms"), 2)),
        "- max event-to-nearest-frame error: {} ms".format(_fmt(analysis["alignment"].get("max_event_alignment_error_ms"), 2)),
        "- host-device offset drift: {} us/s".format(_fmt(analysis["alignment"].get("host_device_offset_drift_us_per_s"), 3)),
        "",
        "## Per-point response",
        "",
        "| point | label | completed | metric | max_abs_z | sat |",
        "|---|---|---|---:|---:|---:|",
    ]
    for point in analysis["points"]:
        lines.append("| {} | {} | {} | {} | {} | {} |".format(
            point.get("point_id"), point.get("label"), int(bool(point.get("completed"))),
            _fmt(point.get("response_metric"), 0), _fmt(point.get("max_abs_z"), 2),
            _fmt(point.get("press_saturation_fraction"), 3)))
    lines += [
        "",
        "## Exploratory separability",
        "",
        "- completed vectors: {}".format(len(similarity.get("points", []))),
        "- mean off-diagonal cosine similarity: {}".format(_fmt(similarity.get("mean_off_diagonal_cosine"), 3)),
        "- classifier accuracy: not computed (one press per class is insufficient; independent repeats required)",
        "",
        "## Files",
        "",
        "- `raw_frames.jsonl`, `samples.csv`, `events.jsonl`, `meta.json`, `run.json`",
        "- `analysis.json` (all statistics), `responses.csv` (36 x 12 deltas/z)",
        "- `timeseries.svg` (12 raw channels + press/release markers)",
        "- `response_map.svg` (6x6 per-point statistic; NOT simultaneous pressure)",
        "",
        "## Interpretation boundary",
        "",
        "- Raw ADC counts are not pressure, force or calibrated resistance.",
        "- A responsive channel or a separable point pattern is at most a **candidate**; it requires independent repeats.",
        "- If saturation/common-mode dominates, the run is marked INVALID_OR_FLOATING and no spatial claim is made.",
    ]
    (run_dir / "REPORT.md").write_text("\n".join(lines) + "\n")
