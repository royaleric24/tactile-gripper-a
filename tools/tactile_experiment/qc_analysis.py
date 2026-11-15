"""Corrected QC-aware evaluation for the two-round 36-point experiment.

This module never touches the original raw files.  It reads them, applies the
operator-error overrides to BOTH training and testing, and writes revised
artifacts into a new revision directory.
"""
from __future__ import annotations

import csv
import json
import math
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .analysis import _common_mode, load_events, load_samples
from .ml import (
    CLASS_CONTACT,
    MODELS,
    FeatureRow,
    StandardScaler,
    feature_names,
    load_round,
    write_features_csv,
    _point_rc,
    _top_k,
    _cosine,
)
from .plot import write_confusion_svg

PRESS = "PRESS"
APPROACH = "APPROACH"
NO_CONTACT = "NO_CONTACT"
CONTACT = "CONTACT"
NON_CONTACT = "NON_CONTACT"
POINT_CLASSES = ["R{}C{}".format(r, c) for r in range(1, 7) for c in range(1, 7)]


def _sha(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_qc_overrides(session_dir: Path) -> Dict[str, Any]:
    session_dir = Path(session_dir)
    session = json.loads((session_dir / "session.json").read_text())
    rounds = {int(item["round_index"]): item for item in session.get("rounds", [])}
    expected = [
        {"round_index": 1, "segment_index": 22, "kind": PRESS, "label": "R1C6"},
        {"round_index": 1, "segment_index": 35, "kind": APPROACH, "label": "APPROACH-1-R2C3"},
        {"round_index": 2, "segment_index": 10, "kind": PRESS, "label": "R6C5"},
    ]
    entries = []
    for item in expected:
        round_item = rounds.get(item["round_index"])
        if round_item is None:
            raise RuntimeError("round {} missing".format(item["round_index"]))
        schedule_path = session_dir / round_item["dir"] / "schedule.json"
        schedule = json.loads(schedule_path.read_text())
        match = None
        for segment in schedule.get("segments", []):
            if int(segment["segment_index"]) == item["segment_index"]:
                match = segment
                break
        if match is None:
            raise RuntimeError("segment {} not in round {}".format(item["segment_index"], item["round_index"]))
        if match.get("kind") != item["kind"] or match.get("label") != item["label"]:
            raise RuntimeError("QC identity mismatch for round {} segment {}: {} != {}".format(
                item["round_index"], item["segment_index"], match, item))
        entries.append({
            "round_index": item["round_index"],
            "segment_index": item["segment_index"],
            "kind": item["kind"],
            "label": item["label"],
            "point_id": match.get("point_id"),
            "row": match.get("row"),
            "column": match.get("column"),
            "control_id": match.get("control_id"),
            "status": "OPERATOR_ERROR",
            "reason": "MISSED_AUDIO_OR_VISUAL_CUE",
            "actual_action": "UNKNOWN",
            "exclude_from_training": True,
            "exclude_from_evaluation": True,
            "source": "USER_REPORTED",
            "evidence": {
                "schedule": str(schedule_path),
                "schedule_sha256": _sha(schedule_path),
            },
        })
    return {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source": "USER_REPORTED",
        "note": "Operator errors are excluded from BOTH training and evaluation; actual action is UNKNOWN and must not be relabeled.",
        "overrides": entries,
    }


def load_rounds(session_dir: Path) -> List[Dict[str, Any]]:
    session = json.loads((Path(session_dir) / "session.json").read_text())
    rounds = []
    for item in session.get("rounds", []):
        d = Path(session_dir) / item["dir"]
        run_summary = {}
        if (d / "run.json").is_file():
            try:
                run_summary = json.loads((d / "run.json").read_text()).get("summary", {})
            except ValueError:
                run_summary = {}
        rounds.append({
            "round_index": int(item["round_index"]),
            "dir": str(d),
            "rows": load_round(d, int(item["round_index"])),
            "run_summary": run_summary,
        })
    return rounds


def excluded_keys(overrides: Dict[str, Any]) -> set:
    return {(int(item["round_index"]), int(item["segment_index"])) for item in overrides["overrides"]}


def apply_qc(rounds: Sequence[Dict[str, Any]], overrides: Dict[str, Any]) -> List[Dict[str, Any]]:
    keys = excluded_keys(overrides)
    result = []
    for item in rounds:
        kept = [row for row in item["rows"] if (row.round_index, row.segment_index) not in keys]
        excluded = [row for row in item["rows"] if (row.round_index, row.segment_index) in keys]
        result.append({
            "round_index": item["round_index"], "dir": item["dir"], "rows": kept,
            "excluded": excluded, "run_summary": item.get("run_summary", {}),
        })
    return result


def coverage(rounds: Sequence[Dict[str, Any]], overrides: Dict[str, Any]) -> Dict[str, Any]:
    keys = excluded_keys(overrides)
    per_round = []
    point_sets = []
    for item in rounds:
        rows = item["rows"]
        kept = [row for row in rows if (row.round_index, row.segment_index) not in keys]
        counts = Counter(row.segment_kind for row in kept)
        points = {row.point_id for row in kept if row.segment_kind == PRESS and row.point_id is not None}
        point_labels = {"R{}C{}".format(row.row, row.column) for row in kept
                        if row.segment_kind == PRESS and row.row is not None and row.column is not None}
        point_sets.append(points)
        per_round.append({
            "round_index": item["round_index"],
            "rows_before": len(rows),
            "rows_after": len(kept),
            "excluded": len(rows) - len(kept),
            "press": counts.get(PRESS, 0),
            "approach": counts.get(APPROACH, 0),
            "no_contact": counts.get(NO_CONTACT, 0),
            "point_coverage": len(points),
            "missing_points": sorted(set(POINT_CLASSES) - point_labels),
        })
    common = set.intersection(*point_sets) if point_sets else set()
    all_points = set.union(*point_sets) if point_sets else set()
    return {
        "per_round": per_round,
        "common_points": sorted(common),
        "common_count": len(common),
        "all_valid_points": sorted(all_points),
        "all_valid_count": len(all_points),
        "total_press": sum(r["press"] for r in per_round),
        "total_approach": sum(r["approach"] for r in per_round),
        "total_no_contact": sum(r["no_contact"] for r in per_round),
        "total_rows": sum(r["rows_after"] for r in per_round),
        "excluded_rows": sum(r["excluded"] for r in per_round),
    }


def _rows_for_point_test(rows: Sequence[FeatureRow], allowed: set) -> List[FeatureRow]:
    return [row for row in rows if row.segment_kind == PRESS and row.point_id is not None and row.point_id in allowed]


def _label_point(row: FeatureRow) -> str:
    return "R{}C{}".format(row.row, row.column)


def _fit_predict(train_rows, test_rows, feature_set: str, model_name: str, label_fn):
    names = feature_names(feature_set)
    X_train = [[float(row.features.get(name, 0.0)) for name in names] for row in train_rows]
    X_test = [[float(row.features.get(name, 0.0)) for name in names] for row in test_rows]
    y_train = [label_fn(row) for row in train_rows]
    y_test = [label_fn(row) for row in test_rows]
    scaler = StandardScaler().fit(X_train)
    model = MODELS[model_name]()
    model.fit(scaler.transform(X_train), y_train)
    probs = model.predict_proba(scaler.transform(X_test))
    return model.classes, probs, y_test


def _metrics(y_true, y_pred, classes):
    confusion = [[0 for _ in classes] for _ in classes]
    index = {label: i for i, label in enumerate(classes)}
    for truth, pred in zip(y_true, y_pred):
        if truth in index and pred in index:
            confusion[index[truth]][index[pred]] += 1
    per_class = {}
    for label in classes:
        i = index[label]
        tp = confusion[i][i]
        fn = sum(confusion[i]) - tp
        fp = sum(confusion[r][i] for r in range(len(classes))) - tp
        precision = tp / (tp + fp) if tp + fp else None
        recall = tp / (tp + fn) if tp + fn else None
        f1 = (2 * precision * recall / (precision + recall)) if precision and recall else None
        per_class[label] = {
            "support": sum(confusion[i]),
            "tp": tp, "fp": fp, "fn": fn,
            "precision": precision, "recall": recall, "f1": f1,
        }
    n = len(y_true)
    correct = sum(1 for t, p in zip(y_true, y_pred) if t == p)
    recalls = [v["recall"] for v in per_class.values() if v["support"] > 0 and v["recall"] is not None]
    precisions = [v["precision"] for v in per_class.values() if v["support"] > 0 and v["precision"] is not None]
    f1s = [v["f1"] for v in per_class.values() if v["support"] > 0 and v["f1"] is not None]
    # Wilson 95% interval for overall accuracy
    p = correct / n if n else 0.0
    z = 1.959963984540054
    denom = 1 + z * z / n if n else 1
    centre = (p + z * z / (2 * n)) / denom if n else 0.0
    half = (z * math.sqrt((p * (1 - p) / n) + (z * z / (4 * n * n))) / denom) if n else 0.0
    return {
        "n": n, "correct": correct, "accuracy": p,
        "accuracy_wilson95": [max(0.0, centre - half), min(1.0, centre + half)],
        "balanced_accuracy": statistics.mean(recalls) if recalls else None,
        "macro_precision": statistics.mean(precisions) if precisions else None,
        "macro_recall": statistics.mean(recalls) if recalls else None,
        "macro_f1": statistics.mean(f1s) if f1s else None,
        "per_class": per_class,
        "confusion": confusion, "classes": classes,
    }


def evaluate_point(train_rows, test_rows, allowed: set, feature_set: str, model_name: str):
    train = _rows_for_point_test(train_rows, allowed)
    test = _rows_for_point_test(test_rows, allowed)
    if len(train) < 2 or not test:
        return None
    classes, probs, y_test = _fit_predict(train, test, feature_set, model_name, _label_point)
    labels = sorted(classes)
    preds = []
    top1 = top3 = row_ok = col_ok = 0
    confidences = []
    for index, (prob, truth) in enumerate(zip(probs, y_test)):
        row = test[index]
        pred = _top_k(prob, classes, 1)[0]
        top = _top_k(prob, classes, min(3, len(classes)))
        top1 += int(pred == truth)
        top3 += int(truth in top)
        rp, cp = _point_rc(pred)
        rt, ct = _point_rc(truth)
        row_ok += int(rp == rt)
        col_ok += int(cp == ct)
        confidences.append((max(prob), pred == truth))
        preds.append({
            "truth": truth, "prediction": pred, "confidence": max(prob), "top3": top,
            "correct": pred == truth,
            "round_index": row.round_index,
            "segment_index": row.segment_index,
            "baseline_saturation": row.baseline_saturation,
            "press_saturation": row.press_saturation,
            "valid_fraction": row.valid_fraction,
        })
    n = len(test)
    metric = _metrics(y_test, [item["prediction"] for item in preds], labels)
    return {
        "train_round": train[0].round_index if train else None,
        "test_round": test[0].round_index if test else None,
        "model": model_name, "feature_set": feature_set,
        "train_samples": len(train), "test_samples": n,
        "top1": top1 / n, "top3": top3 / n,
        "row_accuracy": row_ok / n, "column_accuracy": col_ok / n,
        "mean_confidence": statistics.mean([c for c, _ in confidences]),
        "mean_confidence_correct": statistics.mean([c for c, ok in confidences if ok]) if any(ok for _, ok in confidences) else None,
        "mean_confidence_wrong": statistics.mean([c for c, ok in confidences if not ok]) if any(not ok for _, ok in confidences) else None,
        "classes": labels,
        "confusion": metric["confusion"],
        "balanced_accuracy": metric["balanced_accuracy"],
        "per_class": metric["per_class"],
        "predictions": preds,
    }


def evaluate_contact(train_rows, test_rows, feature_set: str, model_name: str):
    train = [row for row in train_rows if row.segment_kind in (PRESS, APPROACH, NO_CONTACT)]
    test = [row for row in test_rows if row.segment_kind in (PRESS, APPROACH, NO_CONTACT)]
    if len(train) < 2 or not test:
        return None
    classes, probs, y_test = _fit_predict(train, test, feature_set, model_name, lambda row: row.segment_kind)
    preds = []
    for prob, truth in zip(probs, y_test):
        pred = _top_k(prob, classes, 1)[0]
        preds.append({"truth": truth, "prediction": pred, "confidence": max(prob)})
    y_pred = [item["prediction"] for item in preds]
    metrics = _metrics(y_test, y_pred, [PRESS, APPROACH, NO_CONTACT])
    controls = [(t, p) for t, p in zip(y_test, y_pred) if t in (APPROACH, NO_CONTACT)]
    approach = [(t, p) for t, p in controls if t == APPROACH]
    no_contact = [(t, p) for t, p in controls if t == NO_CONTACT]
    metrics.update({
        "model": model_name, "feature_set": feature_set,
        "train_round": train[0].round_index if train else None,
        "test_round": test[0].round_index if test else None,
        "train_samples": len(train), "test_samples": len(test),
        "approach_to_press_rate": (sum(1 for t, p in approach if p == PRESS) / len(approach)) if approach else None,
        "no_contact_to_press_rate": (sum(1 for t, p in no_contact if p == PRESS) / len(no_contact)) if no_contact else None,
        "non_contact_false_contact_rate": (
            sum(1 for t, p in controls if p == PRESS) / len(controls)) if controls else None,
        "non_press_rate": (sum(1 for t, p in controls if p != PRESS) / len(controls)) if controls else None,
        "predictions": preds,
    })
    return metrics


def evaluate_binary_contact(train_rows, test_rows, feature_set: str, model_name: str):
    train = [row for row in train_rows if row.segment_kind in (PRESS, APPROACH, NO_CONTACT)]
    test = [row for row in test_rows if row.segment_kind in (PRESS, APPROACH, NO_CONTACT)]
    if len(train) < 2 or not test:
        return None
    classes, probs, y_test = _fit_predict(
        train, test, feature_set, model_name,
        lambda row: CONTACT if row.segment_kind == PRESS else NON_CONTACT,
    )
    y_pred = [_top_k(prob, classes, 1)[0] for prob in probs]
    metrics = _metrics(y_test, y_pred, [CONTACT, NON_CONTACT])
    controls = [(t, p) for t, p in zip(y_test, y_pred) if t == NON_CONTACT]
    metrics.update({
        "model": model_name, "feature_set": feature_set,
        "train_round": train[0].round_index if train else None,
        "test_round": test[0].round_index if test else None,
        "train_samples": len(train), "test_samples": len(test),
        "non_contact_false_contact_rate": (sum(1 for _, p in controls if p == CONTACT) / len(controls)) if controls else None,
    })
    return metrics


def _repeatability(rows: Sequence[FeatureRow]) -> Dict[str, Any]:
    vectors: Dict[str, List[List[float]]] = {}
    for row in rows:
        if row.segment_kind != PRESS or row.point_id is None:
            continue
        vector = [row.features.get(name, 0.0) for name in feature_names("per_channel") if name.startswith(("f_delta_", "f_z_"))]
        vectors.setdefault(_label_point(row), []).append(vector)
    same = []
    for label, items in vectors.items():
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                val = _cosine(items[i], items[j])
                if val is not None:
                    same.append(val)
    all_items = [(label, vec) for label, items in vectors.items() for vec in items]
    different = []
    for i in range(len(all_items)):
        for j in range(i + 1, len(all_items)):
            if all_items[i][0] == all_items[j][0]:
                continue
            val = _cosine(all_items[i][1], all_items[j][1])
            if val is not None:
                different.append(val)
    return {
        "points_with_multiple_rounds": sum(1 for items in vectors.values() if len(items) >= 2),
        "same_point_cosine_mean": statistics.mean(same) if same else None,
        "different_point_cosine_mean": statistics.mean(different) if different else None,
        "separation": (statistics.mean(same) - statistics.mean(different)) if same and different else None,
    }


def _diagnostics(rounds_qc: Sequence[Dict[str, Any]], overrides: Dict[str, Any]) -> Dict[str, Any]:
    keys = excluded_keys(overrides)
    per_round = []
    for item in rounds_qc:
        kept = [row for row in item["rows"] if (row.round_index, row.segment_index) not in keys]
        samples = load_samples(Path(item["dir"]) / "samples.csv")
        events = load_events(Path(item["dir"]) / "events.jsonl")
        common = _common_mode(samples)
        per_round.append({
            "round_index": item["round_index"],
            "baseline_saturation_mean": statistics.mean([row.baseline_saturation for row in kept]) if kept else None,
            "press_saturation_mean": statistics.mean([row.press_saturation for row in kept]) if kept else None,
            "valid_fraction_mean": statistics.mean([row.valid_fraction for row in kept]) if kept else None,
            "run_summary": item.get("run_summary", {}),
            "common_mode": {k: v for k, v in common.items() if k != "channel_abs_correlations"},
        })
    all_rows = [row for item in rounds_qc for row in item["rows"]
                if (row.round_index, row.segment_index) not in keys]
    return {
        "per_round": per_round,
        "repeatability_after_qc": _repeatability(all_rows),
    }


def _original_summary(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text())
    results = data.get("evaluation", {}).get("results", [])
    points = [item["point"] for item in results if item.get("point")]
    controls = [item["control"] for item in results if item.get("control")]
    best = max(points, key=lambda p: (p.get("top1", 0), p.get("top3", 0)), default=None)
    return {
        "quality": data.get("quality"),
        "quality_reasons": data.get("quality_reasons"),
        "best_point": best,
        "mean_point_top1": statistics.mean([p["top1"] for p in points]) if points else None,
        "control_false_contact_note": "Original control model excluded PRESS; false_contact_rate is not a valid contact-detection metric.",
        "control_results": controls[:2],
        "repeatability": data.get("evaluation", {}).get("repeatability"),
    }


def _evaluate_scenario(rounds_qc, allowed, train_round, test_round, feature_sets, models):
    train = next(item for item in rounds_qc if item["round_index"] == train_round)["rows"]
    test = next(item for item in rounds_qc if item["round_index"] == test_round)["rows"]
    point_results = []
    contact_results = []
    binary_results = []
    for model in models:
        for features in feature_sets:
            point = evaluate_point(train, test, allowed, features, model)
            contact = evaluate_contact(train, test, features, model)
            binary = evaluate_binary_contact(train, test, features, model)
            if point:
                point_results.append(point)
            if contact:
                contact_results.append(contact)
            if binary:
                binary_results.append(binary)
    return {"point": point_results, "contact": contact_results, "binary_contact": binary_results}


def run_corrected_analysis(session_dir: Path, revision_dir: Optional[Path] = None) -> Dict[str, Any]:
    session_dir = Path(session_dir)
    revision_dir = Path(revision_dir) if revision_dir else session_dir / ("revision_qc_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    revision_dir.mkdir(parents=True, exist_ok=True)
    overrides = build_qc_overrides(session_dir)
    (revision_dir / "qc_overrides.json").write_text(json.dumps(overrides, indent=2) + "\n")
    rounds = load_rounds(session_dir)
    rounds_qc = apply_qc(rounds, overrides)
    cov = coverage(rounds, overrides)
    allowed = set(cov["common_points"])
    feature_sets = ("per_channel", "plus_common", "common_only")
    models = ("nearest_centroid", "knn3", "logistic")
    scenarios = {}
    for scenario, both_qc in (("test_only_qc", False), ("train_test_qc", True)):
        if both_qc:
            train_source = rounds_qc
            test_source = rounds_qc
        else:
            # train on the original (unfiltered) rows, test after QC
            train_source = rounds
            test_source = rounds_qc
        for direction in ((1, 2), (2, 1)):
            tr = next(item for item in train_source if item["round_index"] == direction[0])["rows"]
            te = next(item for item in test_source if item["round_index"] == direction[1])["rows"]
            key = "{}_r{}_r{}".format(scenario, direction[0], direction[1])
            scenarios[key] = _evaluate_scenario_from_rows(tr, te, allowed, feature_sets, models)
    diagnostics = _diagnostics(rounds_qc, overrides)
    original = _original_summary(session_dir / "ml_report.json")
    all_rows = [row for item in rounds_qc for row in item["rows"]
                if (row.round_index, row.segment_index) not in excluded_keys(overrides)]
    baseline_sat = statistics.mean([row.baseline_saturation for row in all_rows]) if all_rows else None
    press_sat = statistics.mean([row.press_saturation for row in all_rows]) if all_rows else None
    quality = "EXPLORATORY_ONLY"
    reasons = ["two rounds only; one press per common point per round"]
    if (baseline_sat is not None and baseline_sat > 0.10) or (press_sat is not None and press_sat > 0.10):
        quality = "INVALID_OR_FLOATING"
        reasons = ["QC-filtered baseline saturation {:.1%} / press {:.1%} > 10%".format(
            baseline_sat or 0, press_sat or 0)]
    # best corrected point result (train/test both QC)
    # common_only is an artifact diagnostic, not a valid signal model.
    corrected_points = [p for key, value in scenarios.items() if key.startswith("train_test_qc")
                        for p in value["point"] if p["feature_set"] != "common_only"]
    best_point = max(corrected_points, key=lambda p: (p["top1"], p["top3"]), default=None)
    test_only_points = [p for key, value in scenarios.items() if key.startswith("test_only_qc")
                        for p in value["point"] if p["feature_set"] != "common_only"]
    best_test_only = max(test_only_points, key=lambda p: (p["top1"], p["top3"]), default=None)
    common_only_points = [p for key, value in scenarios.items() if key.startswith("train_test_qc")
                          for p in value["point"] if p["feature_set"] == "common_only"]
    best_common_only = max(common_only_points, key=lambda p: (p["top1"], p["top3"]), default=None)
    contact_all = [c for key, value in scenarios.items() if key.startswith("train_test_qc")
                   for c in value["contact"] if c["feature_set"] != "common_only"]
    best_contact = max(contact_all, key=lambda c: (c.get("balanced_accuracy") or 0, c.get("accuracy") or 0), default=None)
    binary_all = [b for key, value in scenarios.items() if key.startswith("train_test_qc")
                  for b in value["binary_contact"] if b["feature_set"] != "common_only"]
    best_binary = max(binary_all, key=lambda b: (b.get("balanced_accuracy") or 0, b.get("accuracy") or 0), default=None)
    random_top1 = 1.0 / max(1, len(allowed))
    random_top3 = 3.0 / max(1, len(allowed))
    blind_reasons = []
    if quality == "INVALID_OR_FLOATING":
        blind_reasons.append("signal quality is INVALID_OR_FLOATING")
    if best_point is None or best_point.get("top1", 0) <= random_top1:
        blind_reasons.append("point Top-1 is at or below the 34-class random baseline")
    if best_point is None or best_point.get("top3", 0) <= random_top3:
        blind_reasons.append("point Top-3 is at or below the 34-class random baseline")
    if best_contact is None or (best_contact.get("balanced_accuracy") or 0) < 0.70:
        blind_reasons.append("contact balanced accuracy < 0.70 with very few controls")
    if diagnostics.get("repeatability_after_qc", {}).get("separation") is None or \
            diagnostics["repeatability_after_qc"]["separation"] < 0.20:
        blind_reasons.append("same-vs-different point similarity separation < 0.20")
    blind = {"recommended": False, "reasons": blind_reasons}
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "session_dir": str(session_dir),
        "revision_dir": str(revision_dir),
        "qc": overrides,
        "coverage": cov,
        "quality": quality,
        "quality_reasons": reasons,
        "baseline_saturation_mean": baseline_sat,
        "press_saturation_mean": press_sat,
        "allowed_common_points": sorted(allowed),
        "random_baseline_common34": {"top1": 1.0 / max(1, len(allowed)),
                                      "top3": 3.0 / max(1, len(allowed)),
                                      "row": 1.0 / 6.0, "column": 1.0 / 6.0},
        "scenarios": scenarios,
        "diagnostics": diagnostics,
        "original": original,
        "best_corrected_point": best_point,
        "best_test_only_point": best_test_only,
        "best_common_only_point": best_common_only,
        "best_contact": best_contact,
        "best_binary_contact": best_binary,
        "validity_error_relationship": _validity_error(best_point),
        "blind_test_recommendation": blind,
        "interpretation": (
            "QC overrides are excluded from training and evaluation. Strict common-point evaluation uses only "
            "points present in both rounds. Contact model includes PRESS/APPROACH/NO_CONTACT. Raw counts are not pressure."
        ),
    }
    (revision_dir / "ml_report_corrected.json").write_text(json.dumps(report, indent=2) + "\n")
    write_features_csv(revision_dir / "features_qc.csv", rounds_qc)
    _write_comparison_csv(revision_dir, scenarios, original)
    _write_qc_summary(revision_dir, overrides, cov)
    if best_point:
        write_confusion_svg(
            revision_dir / "confusion_matrix_corrected.svg",
            best_point["confusion"], best_point["classes"],
            "Corrected 34-point cross-round confusion (QC train+test)",
            "EXPLORATORY - classes present in both rounds only; one sample per class per round",
        )
    if best_contact:
        write_confusion_svg(
            revision_dir / "contact_detection_matrix.svg",
            best_contact["confusion"], best_contact["classes"],
            "Corrected contact detection: PRESS / APPROACH / NO_CONTACT",
            "EXPLORATORY - few controls; not validated contact detection",
        )
    _write_report(revision_dir, report)
    return report


def _validity_error(point_result):
    if not point_result:
        return None
    high = [p for p in point_result.get("predictions", [])
            if (p.get("baseline_saturation") or 0) > 0.10 or (p.get("press_saturation") or 0) > 0.10]
    low = [p for p in point_result.get("predictions", [])
           if not ((p.get("baseline_saturation") or 0) > 0.10 or (p.get("press_saturation") or 0) > 0.10)]
    def acc(items):
        return (sum(1 for item in items if item.get("correct")) / len(items)) if items else None
    return {
        "high_saturation_n": len(high), "high_saturation_accuracy": acc(high),
        "low_saturation_n": len(low), "low_saturation_accuracy": acc(low),
        "note": "Grouped by per-press baseline/press saturation >10%; small groups, descriptive only.",
    }


def _evaluate_scenario_from_rows(train_rows, test_rows, allowed, feature_sets, models):
    point_results = []
    contact_results = []
    binary_results = []
    for model in models:
        for features in feature_sets:
            p = evaluate_point(train_rows, test_rows, allowed, features, model)
            c = evaluate_contact(train_rows, test_rows, features, model)
            b = evaluate_binary_contact(train_rows, test_rows, features, model)
            if p:
                point_results.append(p)
            if c:
                contact_results.append(c)
            if b:
                binary_results.append(b)
    return {"point": point_results, "contact": contact_results, "binary_contact": binary_results}


def _write_comparison_csv(revision_dir: Path, scenarios, original):
    rows = []
    for key, value in scenarios.items():
        for point in value["point"]:
            rows.append({
                "scenario": key, "direction": "{}->{}".format(point["train_round"], point["test_round"]),
                "model": point["model"], "feature_set": point["feature_set"],
                "train_samples": point["train_samples"], "test_samples": point["test_samples"],
                "top1": point["top1"], "top3": point["top3"],
                "row_accuracy": point["row_accuracy"], "column_accuracy": point["column_accuracy"],
                "contact_balanced_accuracy": None, "approach_to_press": None, "no_contact_to_press": None,
            })
        for contact in value["contact"]:
            rows.append({
                "scenario": key, "direction": "{}->{}".format(contact.get("train_round"), contact.get("test_round")),
                "model": contact["model"], "feature_set": contact["feature_set"],
                "train_samples": contact["train_samples"], "test_samples": contact["test_samples"],
                "top1": contact["accuracy"], "top3": None,
                "row_accuracy": None, "column_accuracy": None,
                "contact_balanced_accuracy": contact["balanced_accuracy"],
                "approach_to_press": contact["approach_to_press_rate"],
                "no_contact_to_press": contact["no_contact_to_press_rate"],
            })
    if original.get("best_point"):
        p = original["best_point"]
        rows.append({
            "scenario": "original_reference", "direction": "original", "model": p.get("model"),
            "feature_set": p.get("feature_set"), "train_samples": p.get("train_samples"),
            "test_samples": p.get("test_samples"), "top1": p.get("top1"), "top3": p.get("top3"),
            "row_accuracy": p.get("row_accuracy"), "column_accuracy": p.get("column_accuracy"),
            "contact_balanced_accuracy": None, "approach_to_press": None, "no_contact_to_press": None,
        })
    with open(revision_dir / "evaluation_comparison.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()) if rows else ["scenario"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_qc_summary(revision_dir: Path, overrides, cov):
    lines = [
        "# QC Summary",
        "",
        "Three user-reported operator errors were verified against each round's `schedule.json`.",
        "",
        "| round | segment | kind | label | point | excluded | reason |",
        "|---:|---:|---|---|---:|---|---|",
    ]
    for item in overrides["overrides"]:
        lines.append("| {} | {} | {} | {} | {} | train+eval | {} |".format(
            item["round_index"], item["segment_index"], item["kind"], item["label"],
            item.get("point_id"), item["reason"]))
    lines += [
        "",
        "`actual_action=UNKNOWN`; no segment was relabeled as a different point.",
        "",
        "## Coverage after QC",
        "",
        "| round | rows before | excluded | press | approach | no-contact | point coverage |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in cov["per_round"]:
        lines.append("| {} | {} | {} | {} | {} | {} | {} |".format(
            r["round_index"], r["rows_before"], r["excluded"], r["press"],
            r["approach"], r["no_contact"], r["point_coverage"]))
    lines += [
        "",
        "- Total PRESS: {}".format(cov["total_press"]),
        "- Total APPROACH: {}".format(cov["total_approach"]),
        "- Total NO_CONTACT: {}".format(cov["total_no_contact"]),
        "- Common points in both rounds: {} (expected 34)".format(cov["common_count"]),
        "- All valid distinct points across rounds: {} (expected 36; each round has 35 after exclusion)".format(cov["all_valid_count"]),
        "",
        "Original raw files were hashed and set read-only; this revision directory is separate.",
    ]
    (revision_dir / "qc_summary.md").write_text("\n".join(lines) + "\n")


def _fmt(value, digits=3):
    if value is None:
        return "-"
    if isinstance(value, float):
        return "{:.{}f}".format(value, digits)
    return str(value)


def _write_report(revision_dir: Path, report):
    cov = report["coverage"]
    lines = [
        "# Corrected Two-Round 36-Point Evaluation",
        "",
        "Generated: {}".format(report["timestamp_utc"]),
        "",
        "## Verdict",
        "",
        "- Signal quality: **{}**".format(report["quality"]),
        "- Reasons: {}".format("; ".join(report["quality_reasons"])),
        "- Common points: **{}/34**".format(cov["common_count"]),
        "- PRESS / APPROACH / NO_CONTACT after QC: **{} / {} / {}**".format(
            cov["total_press"], cov["total_approach"], cov["total_no_contact"]),
        "- All valid distinct points across rounds: **{}** (36 positions may appear; each round has 35 after exclusion)".format(cov["all_valid_count"]),
        "",
        "The QC operator-error segments are excluded from **both training and testing**. "
        "Labels are used only for scoring; features contain no point/round/seed/order.",
        "",
        "## Original vs corrected",
        "",
        "| scenario | Top-1 | Top-3 | row | col | contact false-contact |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    orig = report["original"]
    if orig.get("best_point"):
        p = orig["best_point"]
        lines.append("| original best point (reference) | {} | {} | {} | {} | invalid (control model lacked PRESS) |".format(
            _fmt(p.get("top1")), _fmt(p.get("top3")), _fmt(p.get("row_accuracy")), _fmt(p.get("column_accuracy"))))
    best = report.get("best_corrected_point")
    if best:
        lines.append("| corrected best point (QC train+test, common 34) | {} | {} | {} | {} | see contact table |".format(
            _fmt(best["top1"]), _fmt(best["top3"]), _fmt(best["row_accuracy"]), _fmt(best["column_accuracy"])))
    if report.get("best_test_only_point"):
        p = report["best_test_only_point"]
        lines.append("| test-only QC (train original, test QC) | {} | {} | {} | {} | see contact table |".format(
            _fmt(p["top1"]), _fmt(p["top3"]), _fmt(p["row_accuracy"]), _fmt(p["column_accuracy"])))
    if report.get("best_common_only_point"):
        p = report["best_common_only_point"]
        lines.append("| artifact-only features (common_only) | {} | {} | {} | {} | not a valid signal model |".format(
            _fmt(p["top1"]), _fmt(p["top3"]), _fmt(p["row_accuracy"]), _fmt(p["column_accuracy"])))
    lines += [
        "",
        "`train_test_qc` uses the strict 34 common positions; `test_only_qc` trains on the original (including "
        "operator-error labels) and tests after QC, so it is diagnostic only. `common_only` uses saturation/"
        "common-mode features alone and is an artifact-reliance probe, not a valid spatial model.",
        "",
        "The original report's `false_contact_rate=0` was invalid because its control model contained only "
        "APPROACH/NO_CONTACT and could not predict PRESS. The corrected contact model includes all three classes.",
        "",
        "## Corrected point models (selected examples)",
        "",
        "| scenario | direction | model | features | n train/test | Top-1 | Top-3 | row | col |",
        "|---|---|---|---|---:|---:|---:|---:|---:|",
    ]
    shown = 0
    for key, value in report["scenarios"].items():
        if shown >= 18:
            break
        for point in value["point"]:
            if point["model"] == "nearest_centroid" and point["feature_set"] == "per_channel":
                lines.append("| {} | {}->{} | {} | {} | {}/{} | {} | {} | {} | {} |".format(
                    key, point["train_round"], point["test_round"], point["model"], point["feature_set"],
                    point["train_samples"], point["test_samples"], _fmt(point["top1"]),
                    _fmt(point["top3"]), _fmt(point["row_accuracy"]), _fmt(point["column_accuracy"])))
                shown += 1
    best_contact = report.get("best_contact")
    if best_contact:
        lines += [
            "",
            "## Corrected contact detection (best QC train+test model)",
            "",
            "- model / features: {} / {}".format(best_contact["model"], best_contact["feature_set"]),
            "- test n: {} (PRESS/APPROACH/NO_CONTACT counts in per-class table)".format(best_contact["test_samples"]),
            "- accuracy: {} (Wilson95 {}..{})".format(
                _fmt(best_contact["accuracy"]), _fmt(best_contact["accuracy_wilson95"][0]),
                _fmt(best_contact["accuracy_wilson95"][1])),
            "- balanced accuracy: {}".format(_fmt(best_contact["balanced_accuracy"])),
            "- macro precision / recall / F1: {} / {} / {}".format(
                _fmt(best_contact["macro_precision"]), _fmt(best_contact["macro_recall"]), _fmt(best_contact["macro_f1"])),
            "- APPROACH→PRESS: {}; NO_CONTACT→PRESS: {}".format(
                _fmt(best_contact["approach_to_press_rate"]), _fmt(best_contact["no_contact_to_press_rate"])),
            "",
            "| class | support | precision | recall | F1 |",
            "|---|---:|---:|---:|---:|",
        ]
        for label, m in best_contact["per_class"].items():
            lines.append("| {} | {} | {} | {} | {} |".format(label, m["support"], _fmt(m["precision"]),
                                                             _fmt(m["recall"]), _fmt(m["f1"])))
        lines += ["", "Few controls: these intervals are wide; this is exploratory, not validated contact detection."]
    binary = report.get("best_binary_contact")
    if binary:
        lines += [
            "",
            "## Two-stage contact gate (stage 1 CONTACT/NON_CONTACT)",
            "",
            "- model / features: {} / {}".format(binary["model"], binary["feature_set"]),
            "- accuracy: {} (Wilson95 {}..{})".format(
                _fmt(binary["accuracy"]), _fmt(binary["accuracy_wilson95"][0]), _fmt(binary["accuracy_wilson95"][1])),
            "- balanced accuracy: {}; macro precision/recall/F1: {} / {} / {}".format(
                _fmt(binary["balanced_accuracy"]), _fmt(binary["macro_precision"]),
                _fmt(binary["macro_recall"]), _fmt(binary["macro_f1"])),
            "- NON_CONTACT→CONTACT rate: {}".format(_fmt(binary["non_contact_false_contact_rate"])),
            "",
            "Stage 2 is the 34-class point model above, applied only when stage 1 says CONTACT.",
        ]
    validity = report.get("validity_error_relationship")
    if validity:
        lines += [
            "",
            "## Validity vs classification error",
            "",
            "- high-saturation test presses: n={}, accuracy={}".format(validity["high_saturation_n"], _fmt(validity["high_saturation_accuracy"])),
            "- low-saturation test presses: n={}, accuracy={}".format(validity["low_saturation_n"], _fmt(validity["low_saturation_accuracy"])),
            "- This is descriptive; groups are small and the baseline is already INVALID_OR_FLOATING.",
        ]
    diag = report["diagnostics"]
    lines += [
        "",
        "## Diagnostics",
        "",
        "| round | frames | rate Hz | missing/dup | baseline sat | press sat | valid fraction | mean abs corr |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in diag["per_round"]:
        rs = item.get("run_summary") or {}
        fseq = rs.get("frame_seq") or {}
        lines.append("| {} | {} | {} | {}/{} | {} | {} | {} | {} |".format(
            item["round_index"], rs.get("samples"), _fmt(rs.get("device_frame_rate_hz")),
            fseq.get("missing"), fseq.get("duplicates"),
            _fmt(item["baseline_saturation_mean"]), _fmt(item["press_saturation_mean"]),
            _fmt(item["valid_fraction_mean"]),
            _fmt((item["common_mode"] or {}).get("mean_abs_correlation_with_frame_mean"))))
    rep = diag["repeatability_after_qc"]
    lines += [
        "",
        "- same-point cosine mean: {}".format(_fmt(rep["same_point_cosine_mean"])),
        "- different-point cosine mean: {}".format(_fmt(rep["different_point_cosine_mean"])),
        "- separation: {}".format(_fmt(rep["separation"])),
        "- points with multiple rounds: {}".format(rep["points_with_multiple_rounds"]),
        "",
        "## Boundaries",
        "",
        "- Two rounds, one press per common point per round; no classifier accuracy can validate 36-point recognition.",
        "- If quality is INVALID_OR_FLOATING, the signal is dominated by saturation/common-mode/MUX artifacts; "
        "the corrected classifier scores are exploratory only.",
        "- Raw ADC counts are not pressure/force. A blind test would require independent rounds with frozen models.",
        "",
        "## Blind-test recommendation",
        "",
        "- Recommended: **{}**".format("YES" if report.get("blind_test_recommendation", {}).get("recommended") else "NO"),
    ]
    for reason in (report.get("blind_test_recommendation", {}) or {}).get("reasons", []):
        lines.append("- {}".format(reason))
    lines += [
        "- Do not start the 3-train + validation + blind stage until the electrical signal is valid and "
        "repeatability is clearly above the random/similarity baselines.",
        "",
        "## Files",
        "",
        "- `qc_overrides.json`, `qc_summary.md`",
        "- `ml_report_corrected.json`, `evaluation_comparison.csv`",
        "- `confusion_matrix_corrected.svg`, `contact_detection_matrix.svg`",
        "- `features_qc.csv`",
        "- `original_sha256.json` (read-only originals)",
    ]
    (revision_dir / "REPORT_CORRECTED.md").write_text("\n".join(lines) + "\n")
