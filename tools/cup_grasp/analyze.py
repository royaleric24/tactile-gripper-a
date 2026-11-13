"""Aggregate fixed/feedback cup-grasp trials without mixing real and simulated."""
from __future__ import annotations

import csv
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List


def _load(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def classify_trial(meta: Dict[str, Any], metrics: Dict[str, Any], loads: List[Dict[str, Any]]) -> str:
    if metrics.get("data_kind") == "SIMULATED" or meta.get("data_kind") == "SIMULATED":
        return "SIMULATED"
    status = str(metrics.get("status") or meta.get("status") or "UNKNOWN")
    if status in ("NO_VALID_TACTILE", "FAULT", "BLOCKED_GRIPPER_UNCALIBRATED"):
        return status
    if any(item.get("kind") == "DEFORM" for item in loads):
        return "DEFORM"
    if any(item.get("kind") == "SLIP" for item in loads):
        return "SLIP"
    if status in ("HELD", "HOLD", "SUCCESS"):
        return "SUCCESS"
    if status == "TACTILE_ONLY":
        return "TACTILE_ONLY"
    return status


def analyze_trial(run_dir: Path) -> Dict[str, Any]:
    meta = _load(run_dir / "meta.json", {})
    metrics = _load(run_dir / "metrics.json", {})
    loads = []
    if (run_dir / "load_events.jsonl").is_file():
        for line in (run_dir / "load_events.jsonl").read_text().splitlines():
            if line.strip():
                try:
                    loads.append(json.loads(line))
                except ValueError:
                    pass
    return {
        "trial_id": meta.get("trial_id") or run_dir.name,
        "dir": str(run_dir),
        "data_kind": metrics.get("data_kind") or meta.get("data_kind"),
        "mode": meta.get("mode") or metrics.get("mode"),
        "status": classify_trial(meta, metrics, loads),
        "water_total_g": sum(float(e.get("water_g") or 0) for e in loads if e.get("kind") == "WATER"),
        "slip_events": sum(1 for e in loads if e.get("kind") == "SLIP"),
        "deform_events": sum(1 for e in loads if e.get("kind") == "DEFORM"),
        "tactile_frames": metrics.get("tactile_frames"),
        "usable_fraction": metrics.get("usable_fraction"),
        "saturation_fraction": metrics.get("saturation_fraction"),
        "gripper_commands": metrics.get("gripper_commands"),
        "duration_s": metrics.get("duration_s"),
        "video_path": meta.get("video_path"),
    }


def summarize_root(root: Path) -> Dict[str, Any]:
    root = Path(root)
    trials = []
    for run_dir in sorted(root.glob("*/")):
        if (run_dir / "meta.json").is_file() or (run_dir / "metrics.json").is_file():
            trials.append(analyze_trial(run_dir))
    real = [t for t in trials if t["data_kind"] != "SIMULATED"]
    simulated = [t for t in trials if t["data_kind"] == "SIMULATED"]
    by_mode = {}
    for mode in ("FIXED", "FEEDBACK", "fixed", "feedback"):
        items = [t for t in real if str(t.get("mode")).upper() == mode.upper()]
        if items:
            by_mode[mode.upper()] = {
                "n": len(items),
                "success": sum(1 for t in items if t["status"] == "SUCCESS"),
                "slip": sum(1 for t in items if t["status"] == "SLIP"),
                "deform": sum(1 for t in items if t["status"] == "DEFORM"),
                "no_valid_tactile": sum(1 for t in items if t["status"] == "NO_VALID_TACTILE"),
                "fault": sum(1 for t in items if t["status"] == "FAULT"),
                "usable_fraction_mean": statistics.mean([t["usable_fraction"] for t in items if t["usable_fraction"] is not None]) if any(t["usable_fraction"] is not None for t in items) else None,
            }
    return {"root": str(root), "real_trials": len(real), "simulated_trials": len(simulated),
            "by_mode": by_mode, "trials": trials,
            "note": "SIMULATED trials are excluded from real success rates. Slip/deformation are qualitative."}


def write_summary(root: Path, analysis: Dict[str, Any]) -> None:
    root = Path(root)
    csv_path = root / "SUMMARY.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["trial_id", "data_kind", "mode", "status", "water_g", "slip", "deform",
                         "tactile_frames", "usable_fraction", "saturation_fraction", "gripper_commands", "duration_s", "dir"])
        for t in analysis["trials"]:
            writer.writerow([t["trial_id"], t["data_kind"], t["mode"], t["status"], t["water_total_g"],
                             t["slip_events"], t["deform_events"], t["tactile_frames"], t["usable_fraction"],
                             t["saturation_fraction"], t["gripper_commands"], t["duration_s"], t["dir"]])
    lines = [
        "# Cup Grasp Trials Summary",
        "",
        "- root: `{}`".format(root),
        "- real trials: {}".format(analysis["real_trials"]),
        "- simulated trials: {} (excluded from real success rates)".format(analysis["simulated_trials"]),
        "",
        "| mode | n | success | slip | deform | NO_VALID_TACTILE | fault | usable fraction mean |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for mode, item in analysis["by_mode"].items():
        lines.append("| {} | {} | {} | {} | {} | {} | {} | {} |".format(
            mode, item["n"], item["success"], item["slip"], item["deform"],
            item["no_valid_tactile"], item["fault"],
            "-" if item["usable_fraction_mean"] is None else "{:.3f}".format(item["usable_fraction_mean"])))
    lines += [
        "",
        "## Boundaries",
        "",
        "PWM is a command, not measured force/position. ADC deltas are proxies, not Newtons. "
        "Slip/deformation are qualitative unless independently measured. SIMULATED rows are not hardware evidence.",
    ]
    (root / "REPORT.md").write_text("\n".join(lines) + "\n")
