"""Simple, interpretable cross-round models for the 12-channel experiment.

Leakage rules:
- features are computed only from raw ADC windows; they never contain point_id,
  round, seed, segment index, order or event label;
- train/validation/test splits are whole rounds, never adjacent frames;
- labels live in separate metadata columns and are used only for fitting/scoring.

The models are intentionally small: nearest centroid, KNN and a regularized
multinomial logistic regression.
"""
from __future__ import annotations

import csv
import json
import math
import random
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .analysis import (
    CHANNEL_LABELS,
    load_events,
    load_samples,
    _corr,
    _cosine,
    _mean,
    _slope_per_s,
    _std,
    _values,
    _window,
)

LOCAL_BASELINE_S = 1.5
POST_WINDOW_S = 1.5
PRESS = "PRESS"
APPROACH = "APPROACH"
NO_CONTACT = "NO_CONTACT"
CLASS_CONTACT = "CONTACT"


@dataclass
class FeatureRow:
    round_index: int
    segment_index: int
    segment_kind: str
    label: str
    point_id: Optional[int]
    row: Optional[int]
    column: Optional[int]
    features: Dict[str, float]
    baseline_saturation: float
    press_saturation: float
    valid_fraction: float


def _segments(events: Sequence[Dict]) -> List[Dict[str, Any]]:
    by_key: Dict[Tuple[Optional[int], Optional[int]], Dict[str, Any]] = {}
    for event in events:
        key = (event.get("round_index"), event.get("segment_index"))
        if key == (None, None):
            continue
        item = by_key.setdefault(key, {"round_index": key[0], "segment_index": key[1]})
        kind = event.get("kind")
        if kind in ("SEGMENT_READY", "PRESS_START", "APPROACH_START", "NO_CONTACT_START"):
            item.setdefault("ready", event)
        if kind in ("PRESS_START", "APPROACH_START", "NO_CONTACT_START"):
            item.setdefault("start", event)
        if kind in ("RELEASE_START", "APPROACH_END", "NO_CONTACT_END"):
            item.setdefault("end", event)
        if kind == "SEGMENT_DONE":
            item.setdefault("done", event)
    segments = []
    for key, item in by_key.items():
        start = item.get("start") or item.get("ready")
        if not start:
            continue
        segment_kind = start.get("segment_kind")
        if segment_kind not in (PRESS, APPROACH, NO_CONTACT):
            continue
        end = item.get("end")
        if not end:
            continue
        segments.append({
            "round_index": key[0],
            "segment_index": key[1],
            "segment_kind": segment_kind,
            "point_id": start.get("point_id"),
            "row": start.get("row"),
            "column": start.get("column"),
            "label": start.get("label") or "",
            "start_ns": int(start["host_event_monotonic_ns"]),
            "end_ns": int(end["host_event_monotonic_ns"]),
        })
    segments.sort(key=lambda s: (s["round_index"], s["segment_index"]))
    return segments


def extract_features(samples: Sequence[Dict], events: Sequence[Dict], round_index: int) -> List[FeatureRow]:
    rows: List[FeatureRow] = []
    for seg in _segments(events):
        start = seg["start_ns"]
        end = seg["end_ns"]
        if end <= start:
            continue
        baseline = _window(samples, start - int(LOCAL_BASELINE_S * 1e9), start)
        press = _window(samples, start, end)
        post = _window(samples, end, end + int(POST_WINDOW_S * 1e9))
        if not press:
            continue
        features: Dict[str, float] = {}
        deltas = []
        zs = []
        sat_total = 0
        valid_total = 0
        for ch in range(12):
            base_values = _values(baseline, ch)
            press_values = _values(press, ch)
            post_values = _values(post, ch)
            base_mean = _mean(base_values) or 0.0
            base_std = _std(base_values) or 0.0
            press_mean = _mean(press_values) or 0.0
            press_median = statistics.median(press_values) if press_values else 0.0
            press_std = _std(press_values) or 0.0
            post_mean = _mean(post_values)
            delta = press_mean - base_mean
            z = delta / base_std if base_std > 0 else 0.0
            slope = _slope_per_s(press, ch) or 0.0
            sat = sum(1 for v in press_values if v >= 8388607)
            sat_total += sat
            valid_total += len(press_values)
            features["f_base_mean_{}".format(ch)] = base_mean
            features["f_base_std_{}".format(ch)] = base_std
            features["f_delta_{}".format(ch)] = delta
            features["f_z_{}".format(ch)] = z
            features["f_press_std_{}".format(ch)] = press_std
            features["f_press_median_{}".format(ch)] = press_median
            features["f_slope_norm_{}".format(ch)] = slope / (abs(base_mean) + 1.0)
            features["f_sat_frac_{}".format(ch)] = sat / len(press_values) if press_values else 0.0
            features["f_valid_frac_{}".format(ch)] = len(press_values) / len(press) if press else 0.0
            features["f_post_delta_{}".format(ch)] = (post_mean - base_mean) if post_mean is not None else 0.0
            deltas.append(delta)
            zs.append(z)
        features["f_common_delta_mean"] = statistics.mean(deltas) if deltas else 0.0
        features["f_common_abs_delta_mean"] = statistics.mean([abs(v) for v in deltas]) if deltas else 0.0
        features["f_common_z_mean"] = statistics.mean(zs) if zs else 0.0
        features["f_common_z_abs_mean"] = statistics.mean([abs(v) for v in zs]) if zs else 0.0
        features["f_saturation_total"] = sat_total / max(1, valid_total)
        features["f_valid_total"] = valid_total / max(1, len(press) * 12)
        base_sat = 0
        base_count = 0
        for ch in range(12):
            vals = _values(baseline, ch)
            base_count += len(vals)
            base_sat += sum(1 for v in vals if v >= 8388607)
        rows.append(FeatureRow(
            round_index=round_index,
            segment_index=int(seg["segment_index"]),
            segment_kind=seg["segment_kind"],
            label=seg["label"],
            point_id=seg["point_id"],
            row=seg["row"],
            column=seg["column"],
            features=features,
            baseline_saturation=(base_sat / base_count) if base_count else 0.0,
            press_saturation=features["f_saturation_total"],
            valid_fraction=features["f_valid_total"],
        ))
    return rows


PER_CHANNEL_FEATURES = [
    "f_base_mean_{}", "f_base_std_{}", "f_delta_{}", "f_z_{}", "f_press_std_{}",
    "f_press_median_{}", "f_slope_norm_{}", "f_sat_frac_{}", "f_valid_frac_{}", "f_post_delta_{}",
]
COMMON_FEATURES = [
    "f_common_delta_mean", "f_common_abs_delta_mean", "f_common_z_mean",
    "f_common_z_abs_mean", "f_saturation_total", "f_valid_total",
]


def feature_names(feature_set: str = "per_channel") -> List[str]:
    names = []
    for template in PER_CHANNEL_FEATURES:
        for ch in range(12):
            names.append(template.format(ch))
    if feature_set == "plus_common":
        names.extend(COMMON_FEATURES)
    elif feature_set == "common_only":
        return list(COMMON_FEATURES)
    elif feature_set != "per_channel":
        raise ValueError("unknown feature_set")
    return names


def rows_to_xy(rows: Sequence[FeatureRow], feature_set: str, label_kind: str = "point") -> Tuple[List[List[float]], List[str]]:
    names = feature_names(feature_set)
    X: List[List[float]] = []
    y: List[str] = []
    for row in rows:
        if label_kind == "point" and row.segment_kind != PRESS:
            continue
        if label_kind == "control" and row.segment_kind == PRESS:
            continue
        if label_kind == "contact" and row.segment_kind == PRESS:
            label = CLASS_CONTACT
        elif label_kind == "control":
            label = row.segment_kind
        else:
            label = "R{}C{}".format(row.row, row.column)
        X.append([float(row.features.get(name, 0.0)) for name in names])
        y.append(label)
    return X, y


class StandardScaler:
    def fit(self, X: Sequence[Sequence[float]]) -> "StandardScaler":
        n = len(X)
        d = len(X[0]) if n else 0
        self.mean = [statistics.mean(row[j] for row in X) if n else 0.0 for j in range(d)]
        self.std = []
        for j in range(d):
            value = statistics.pstdev([row[j] for row in X]) if n > 1 else 0.0
            self.std.append(value if value > 1e-12 else 1.0)
        return self

    def transform(self, X: Sequence[Sequence[float]]) -> List[List[float]]:
        return [[(row[j] - self.mean[j]) / self.std[j] for j in range(len(self.mean))] for row in X]


class NearestCentroid:
    def fit(self, X, y):
        self.classes = sorted(set(y))
        self.centroids = {}
        for label in self.classes:
            vectors = [row for row, target in zip(X, y) if target == label]
            self.centroids[label] = [statistics.mean(row[j] for row in vectors) for j in range(len(vectors[0]))]
        return self

    def predict_proba(self, X):
        result = []
        for row in X:
            distances = []
            for label in self.classes:
                centroid = self.centroids[label]
                dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(row, centroid)))
                distances.append(dist)
            # softmax over negative squared distances
            m = min(distances)
            weights = [math.exp(-(d - m) ** 2) for d in distances]
            total = sum(weights)
            result.append([w / total for w in weights])
        return result


class KNN:
    def __init__(self, k: int = 3):
        self.k = k

    def fit(self, X, y):
        self.X = list(X)
        self.y = list(y)
        self.classes = sorted(set(y))
        return self

    def predict_proba(self, X):
        result = []
        for row in X:
            distances = []
            for other, label in zip(self.X, self.y):
                dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(row, other)))
                distances.append((dist, label))
            distances.sort(key=lambda item: item[0])
            votes = {label: 0.0 for label in self.classes}
            for dist, label in distances[: self.k]:
                votes[label] += 1.0 / (dist + 1e-6)
            total = sum(votes.values())
            result.append([votes[label] / total if total else 1.0 / len(self.classes) for label in self.classes])
        return result


class LogisticRegression:
    def __init__(self, epochs: int = 120, learning_rate: float = 0.15, l2: float = 0.01):
        self.epochs = epochs
        self.learning_rate = learning_rate
        self.l2 = l2

    def fit(self, X, y):
        self.classes = sorted(set(y))
        index = {label: i for i, label in enumerate(self.classes)}
        n = len(X)
        d = len(X[0])
        c = len(self.classes)
        self.W = [[0.0] * (d + 1) for _ in range(c)]
        targets = [[1.0 if index[label] == k else 0.0 for k in range(c)] for label in y]
        for _ in range(self.epochs):
            grad = [[0.0] * (d + 1) for _ in range(c)]
            for row, target in zip(X, targets):
                logits = [self.W[k][0] + sum(self.W[k][j + 1] * row[j] for j in range(d)) for k in range(c)]
                m = max(logits)
                exps = [math.exp(z - m) for z in logits]
                total = sum(exps)
                probs = [e / total for e in exps]
                for k in range(c):
                    error = probs[k] - target[k]
                    grad[k][0] += error
                    for j in range(d):
                        grad[k][j + 1] += error * row[j]
            for k in range(c):
                self.W[k][0] -= self.learning_rate * grad[k][0] / n
                for j in range(d):
                    self.W[k][j + 1] -= self.learning_rate * (grad[k][j + 1] / n + self.l2 * self.W[k][j + 1])
        return self

    def predict_proba(self, X):
        result = []
        d = len(X[0]) if X else 0
        for row in X:
            logits = [self.W[k][0] + sum(self.W[k][j + 1] * row[j] for j in range(d)) for k in range(len(self.classes))]
            m = max(logits)
            exps = [math.exp(z - m) for z in logits]
            total = sum(exps)
            result.append([e / total for e in exps])
        return result


MODELS = {
    "nearest_centroid": lambda: NearestCentroid(),
    "knn3": lambda: KNN(3),
    "logistic": lambda: LogisticRegression(),
}


def _top_k(probs: Sequence[float], classes: Sequence[str], k: int) -> List[str]:
    order = sorted(range(len(probs)), key=lambda i: probs[i], reverse=True)
    return [classes[i] for i in order[:k]]


def _point_rc(label: str) -> Tuple[Optional[int], Optional[int]]:
    if not label.startswith("R") or "C" not in label:
        return None, None
    try:
        row, col = label[1:].split("C")
        return int(row), int(col)
    except ValueError:
        return None, None


def evaluate_point_model(train_rows, test_rows, model_name: str, feature_set: str):
    X_train, y_train = rows_to_xy(train_rows, feature_set, "point")
    X_test, y_test = rows_to_xy(test_rows, feature_set, "point")
    if len(X_train) < 2 or not X_test:
        return None
    scaler = StandardScaler().fit(X_train)
    model = MODELS[model_name]()
    model.fit(scaler.transform(X_train), y_train)
    probs = model.predict_proba(scaler.transform(X_test))
    classes = model.classes
    top1 = top3 = row_ok = col_ok = 0
    confidences = []
    confusion = [[0 for _ in classes] for _ in classes]
    predictions = []
    for prob, truth in zip(probs, y_test):
        pred = _top_k(prob, classes, 1)[0]
        top = _top_k(prob, classes, 3)
        top1 += int(pred == truth)
        top3 += int(truth in top)
        r_pred, c_pred = _point_rc(pred)
        r_true, c_true = _point_rc(truth)
        row_ok += int(r_pred == r_true)
        col_ok += int(c_pred == c_true)
        truth_index = classes.index(truth) if truth in classes else None
        pred_index = classes.index(pred)
        if truth_index is not None:
            confusion[truth_index][pred_index] += 1
        confidences.append((max(prob), pred == truth))
        predictions.append({"truth": truth, "prediction": pred, "confidence": max(prob), "top3": top})
    n = len(y_test)
    return {
        "model": model_name,
        "feature_set": feature_set,
        "samples": n,
        "top1": top1 / n,
        "top3": top3 / n,
        "row_accuracy": row_ok / n,
        "column_accuracy": col_ok / n,
        "mean_confidence": statistics.mean([c for c, _ in confidences]),
        "mean_confidence_correct": statistics.mean([c for c, ok in confidences if ok]) if any(ok for _, ok in confidences) else None,
        "mean_confidence_wrong": statistics.mean([c for c, ok in confidences if not ok]) if any(not ok for _, ok in confidences) else None,
        "classes": classes,
        "confusion": confusion,
        "predictions": predictions,
    }


def evaluate_control_model(train_rows, test_rows, model_name: str, feature_set: str):
    X_train, y_train = rows_to_xy(train_rows, feature_set, "control")
    X_test, y_test = rows_to_xy(test_rows, feature_set, "control")
    if len(X_train) < 2 or not X_test:
        return None
    scaler = StandardScaler().fit(X_train)
    model = MODELS[model_name]()
    model.fit(scaler.transform(X_train), y_train)
    probs = model.predict_proba(scaler.transform(X_test))
    classes = model.classes
    top1 = 0
    false_contact = 0
    control_unknown = 0
    predictions = []
    for prob, truth in zip(probs, y_test):
        pred = _top_k(prob, classes, 1)[0]
        top1 += int(pred == truth)
        if pred == PRESS:
            false_contact += 1
        else:
            control_unknown += 1
        predictions.append({"truth": truth, "prediction": pred, "confidence": max(prob)})
    n = len(y_test)
    return {
        "model": model_name,
        "feature_set": feature_set,
        "samples": n,
        "top1": top1 / n,
        "false_contact_rate": false_contact / n,
        "unknown_rate": control_unknown / n,
        "classes": classes,
        "predictions": predictions,
    }


def load_round(round_dir: Path, round_index: int) -> List[FeatureRow]:
    samples = load_samples(Path(round_dir) / "samples.csv")
    events = load_events(Path(round_dir) / "events.jsonl")
    return extract_features(samples, events, round_index)


def _repeatability(rounds: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    point_vectors: Dict[str, List[List[float]]] = {}
    for item in rounds:
        for row in item["rows"]:
            if row.segment_kind != PRESS or row.point_id is None:
                continue
            vector = [row.features.get(name, 0.0) for name in feature_names("per_channel") if name.startswith(("f_delta_", "f_z_"))]
            label = "R{}C{}".format(row.row, row.column)
            point_vectors.setdefault(label, []).append(vector)
    same = []
    for label, vectors in point_vectors.items():
        for i in range(len(vectors)):
            for j in range(i + 1, len(vectors)):
                value = _cosine(vectors[i], vectors[j])
                if value is not None:
                    same.append(value)
    all_vectors = [(label, vector) for label, vectors in point_vectors.items() for vector in vectors]
    different = []
    for i in range(len(all_vectors)):
        for j in range(i + 1, len(all_vectors)):
            if all_vectors[i][0] == all_vectors[j][0]:
                continue
            value = _cosine(all_vectors[i][1], all_vectors[j][1])
            if value is not None:
                different.append(value)
    return {
        "points_with_multiple_rounds": sum(1 for vectors in point_vectors.values() if len(vectors) >= 2),
        "same_point_cosine_mean": statistics.mean(same) if same else None,
        "different_point_cosine_mean": statistics.mean(different) if different else None,
        "separation": (statistics.mean(same) - statistics.mean(different)) if same and different else None,
        "note": "Cosine similarity of per-press delta/z vectors across rounds; descriptive only.",
    }


def evaluate_rounds(rounds: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Cross-round evaluation; each item has round_index/rows."""
    if len(rounds) < 2:
        raise ValueError("at least two rounds are required")
    results = []
    for train in rounds:
        for test in rounds:
            if train["round_index"] == test["round_index"]:
                continue
            for model_name in ("nearest_centroid", "knn3", "logistic"):
                for feature_set in ("per_channel", "plus_common"):
                    point = evaluate_point_model(train["rows"], test["rows"], model_name, feature_set)
                    control = evaluate_control_model(train["rows"], test["rows"], model_name, feature_set)
                    results.append({
                        "train_round": train["round_index"],
                        "test_round": test["round_index"],
                        "point": point,
                        "control": control,
                    })
    repeat = _repeatability(rounds)
    random_top1 = 1.0 / 36.0
    random_top3 = 3.0 / 36.0
    return {
        "rounds": [item["round_index"] for item in rounds],
        "results": results,
        "repeatability": repeat,
        "random_baseline": {"top1": random_top1, "top3": random_top3, "row": 1.0 / 6.0, "column": 1.0 / 6.0},
        "note": "Whole-round train/test. Metrics are exploratory; one press per class per round is not a validated 36-class result.",
    }


def write_features_csv(path: Path, rounds: Sequence[Dict[str, Any]], feature_set: str = "plus_common") -> None:
    names = feature_names(feature_set)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["round_index", "segment_index", "segment_kind", "label", "point_id", "row", "column",
                         "baseline_saturation", "press_saturation", "valid_fraction"] + names)
        for item in rounds:
            for row in item["rows"]:
                writer.writerow([
                    row.round_index, row.segment_index, row.segment_kind, row.label,
                    row.point_id, row.row, row.column, row.baseline_saturation,
                    row.press_saturation, row.valid_fraction,
                ] + [row.features.get(name, 0.0) for name in names])
