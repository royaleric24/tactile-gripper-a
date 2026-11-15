"""Preliminary two-round repeatability + cross-round baselines."""
from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .ml import evaluate_rounds, load_round, write_features_csv
from .plot import write_confusion_svg


def _mean(values):
    values = [v for v in values if v is not None]
    return statistics.mean(values) if values else None


def analyze_session(session_dir: Path) -> Dict[str, Any]:
    session_dir = Path(session_dir)
    session = json.loads((session_dir / "session.json").read_text())
    rounds = []
    for item in session.get("rounds", []):
        round_dir = session_dir / item["dir"]
        if not (round_dir / "samples.csv").is_file():
            continue
        rows = load_round(round_dir, int(item["round_index"]))
        rounds.append({"round_index": int(item["round_index"]), "dir": str(round_dir), "rows": rows,
                       "schedule": item})
    if len(rounds) < 2:
        raise RuntimeError("need at least two completed rounds; found {}".format(len(rounds)))
    evaluation = evaluate_rounds(rounds)
    baseline_sat = _mean([row.baseline_saturation for r in rounds for row in r["rows"]])
    press_sat = _mean([row.press_saturation for r in rounds for row in r["rows"]])
    valid_fraction = _mean([row.valid_fraction for r in rounds for row in r["rows"]])
    quality = "EXPLORATORY_ONLY"
    reasons = []
    if baseline_sat is not None and baseline_sat > 0.10:
        quality = "INVALID_OR_FLOATING"
        reasons.append("baseline saturation mean {:.1%} > 10%".format(baseline_sat))
    if press_sat is not None and press_sat > 0.10:
        quality = "INVALID_OR_FLOATING"
        reasons.append("press saturation mean {:.1%} > 10%".format(press_sat))
    if not reasons:
        reasons.append("two rounds only; single press per point per round; exploratory")
    # choose best point model by top1, then top3
    best = None
    for item in evaluation["results"]:
        point = item.get("point")
        if not point:
            continue
        key = (point["top1"], point["top3"], -point["mean_confidence"])
        if best is None or key > best[0]:
            best = (key, item)
    best_item = best[1] if best else None
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "data_kind": "REAL_HARDWARE_SERIAL",
        "session_dir": str(session_dir),
        "rounds": [{"round_index": r["round_index"], "dir": r["dir"], "rows": len(r["rows"])} for r in rounds],
        "quality": quality,
        "quality_reasons": reasons,
        "baseline_saturation_mean": baseline_sat,
        "press_saturation_mean": press_sat,
        "valid_fraction_mean": valid_fraction,
        "evaluation": evaluation,
        "best_result": best_item,
        "interpretation": (
            "Whole-round cross-validation of raw-ADC features. Two rounds cannot validate 36-class "
            "position recognition; labels never enter the feature vector. Raw counts are not pressure."
        ),
    }
    (session_dir / "ml_report.json").write_text(json.dumps(report, indent=2) + "\n")
    write_features_csv(session_dir / "features.csv", rounds)
    if best_item:
        point = best_item["point"]
        write_confusion_svg(
            session_dir / "confusion_matrix.svg",
            point["confusion"],
            point["classes"],
            "36-class cross-round confusion",
            "EXPLORATORY - one press per class per round; not a validated 36-class result",
        )
    _write_report(session_dir, report, rounds)
    return report


def _fmt(value, digits=3):
    if value is None:
        return "-"
    if isinstance(value, float):
        return "{:.{}f}".format(value, digits)
    return str(value)


def _write_report(session_dir: Path, report: Dict[str, Any], rounds: List[Dict[str, Any]]) -> None:
    evaluation = report["evaluation"]
    lines = [
        "# 36-Point Multi-Round Preliminary Report",
        "",
        "Generated: {}".format(report["timestamp_utc"]),
        "",
        "## Verdict",
        "",
        "- Signal quality: **{}**".format(report["quality"]),
        "- Reasons: {}".format("; ".join(report["quality_reasons"])),
        "- Rounds: {}".format(", ".join("round {} ({} rows)".format(r["round_index"], r["rows"]) for r in report["rounds"])),
        "- Baseline saturation mean: {}".format(_fmt(report["baseline_saturation_mean"], 3)),
        "- Press saturation mean: {}".format(_fmt(report["press_saturation_mean"], 3)),
        "- Valid fraction mean: {}".format(_fmt(report["valid_fraction_mean"], 3)),
        "",
        "**Raw ADC counts only. Two rounds are insufficient for a validated 36-class result. "
        "Labels are used only for scoring; features contain no point/round/seed/order.**",
        "",
        "## Cross-round metrics (whole rounds)",
        "",
        "| train | test | model | features | Top-1 | Top-3 | row | col | control false-contact |",
        "|---:|---:|---|---|---:|---:|---:|---:|---:|",
    ]
    for item in evaluation["results"]:
        point = item.get("point")
        control = item.get("control")
        if not point:
            continue
        lines.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
            item["train_round"], item["test_round"], point["model"], point["feature_set"],
            _fmt(point["top1"]), _fmt(point["top3"]), _fmt(point["row_accuracy"]),
            _fmt(point["column_accuracy"]),
            _fmt(control.get("false_contact_rate") if control else None),
        ))
    repeat = evaluation["repeatability"]
    lines += [
        "",
        "## Repeatability",
        "",
        "- points with ≥2 rounds: {}".format(repeat.get("points_with_multiple_rounds")),
        "- same-point cosine mean: {}".format(_fmt(repeat.get("same_point_cosine_mean"))),
        "- different-point cosine mean: {}".format(_fmt(repeat.get("different_point_cosine_mean"))),
        "- separation: {}".format(_fmt(repeat.get("separation"))),
        "- random Top-1 / Top-3: {} / {}".format(_fmt(evaluation["random_baseline"]["top1"]),
                                                  _fmt(evaluation["random_baseline"]["top3"])),
        "",
        "## Controls",
        "",
        "Control model classes: PRESS / APPROACH / NO_CONTACT. A control predicted as PRESS is a "
        "false-contact; APPROACH/NO_CONTACT can be reported as UNKNOWN rather than forced to a point.",
        "",
        "## Files",
        "",
        "- `features.csv` (metadata + raw-signal features)",
        "- `ml_report.json` (all metrics, predictions, confusion)",
        "- `confusion_matrix.svg` (best cross-round point model)",
        "",
        "## Boundaries",
        "",
        "- A high score here would be candidate-only; it cannot be called 36-point independent pressure.",
        "- If quality is INVALID_OR_FLOATING, the pattern is dominated by saturation/common-mode/MUX artifacts.",
        "- A blind test needs 3 training rounds + validation + independent test, with models frozen before labels.",
    ]
    if report.get("best_result"):
        best = report["best_result"]
        point = best["point"]
        lines += [
            "",
            "## Best cross-round result (descriptive only)",
            "",
            "- train round {} -> test round {}".format(best["train_round"], best["test_round"]),
            "- model {} / features {}".format(point["model"], point["feature_set"]),
            "- Top-1 {} / Top-3 {} / row {} / col {}".format(
                _fmt(point["top1"]), _fmt(point["top3"]), _fmt(point["row_accuracy"]), _fmt(point["column_accuracy"])),
        ]
    (session_dir / "REPORT.md").write_text("\n".join(lines) + "\n")
