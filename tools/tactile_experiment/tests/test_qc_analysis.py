import unittest

from tools.tactile_experiment.ml import FeatureRow, feature_names
from tools.tactile_experiment.qc_analysis import (
    APPROACH,
    NO_CONTACT,
    PRESS,
    apply_qc,
    coverage,
    evaluate_binary_contact,
    evaluate_contact,
    evaluate_point,
)

FAKE_OVERRIDES = {
    "overrides": [
        {"round_index": 1, "segment_index": 6, "kind": PRESS, "label": "R1C6", "point_id": 6},
        {"round_index": 1, "segment_index": 37, "kind": APPROACH, "label": "APPROACH-1-R2C3", "point_id": 9},
        {"round_index": 2, "segment_index": 35, "kind": PRESS, "label": "R6C5", "point_id": 35},
    ]
}


def make_row(round_index, segment_index, kind, point_id=None):
    row = (point_id - 1) // 6 + 1 if point_id else None
    col = (point_id - 1) % 6 + 1 if point_id else None
    features = {name: 0.0 for name in feature_names("plus_common")}
    if kind == PRESS:
        features["f_delta_0"] = row * 100.0
        features["f_delta_1"] = col * 100.0
        features["f_common_delta_mean"] = (row + col) * 50.0
    return FeatureRow(
        round_index=round_index, segment_index=segment_index, segment_kind=kind,
        label=("R{}C{}".format(row, col) if point_id else kind), point_id=point_id,
        row=row, column=col, features=features,
        baseline_saturation=0.0, press_saturation=0.0, valid_fraction=1.0,
    )


def make_rounds():
    rounds = []
    for round_index in (1, 2):
        rows = []
        for pid in range(1, 37):
            rows.append(make_row(round_index, pid, PRESS, pid))
        rows.append(make_row(round_index, 37, APPROACH, 9))
        rows.append(make_row(round_index, 38, NO_CONTACT))
        rows.append(make_row(round_index, 39, APPROACH, 14))
        rows.append(make_row(round_index, 40, NO_CONTACT))
        rounds.append({"round_index": round_index, "dir": "synthetic", "rows": rows})
    return rounds


class QCTests(unittest.TestCase):
    def test_apply_qc_and_coverage(self):
        rounds = make_rounds()
        kept = apply_qc(rounds, FAKE_OVERRIDES)
        cov = coverage(rounds, FAKE_OVERRIDES)
        self.assertEqual(cov["excluded_rows"], 3)
        self.assertEqual(cov["total_press"], 70)
        self.assertEqual(cov["total_approach"], 3)
        self.assertEqual(cov["total_no_contact"], 4)
        self.assertEqual(cov["common_count"], 34)
        self.assertEqual(cov["all_valid_count"], 36)
        self.assertEqual(cov["per_round"][0]["missing_points"], ["R1C6"])
        self.assertEqual(cov["per_round"][1]["missing_points"], ["R6C5"])
        self.assertEqual(len(kept[0]["excluded"]), 2)
        self.assertEqual(len(kept[1]["excluded"]), 1)

    def test_point_model_uses_qc_train_and_test(self):
        rounds = apply_qc(make_rounds(), FAKE_OVERRIDES)
        allowed = set(coverage(make_rounds(), FAKE_OVERRIDES)["common_points"])
        result = evaluate_point(rounds[0]["rows"], rounds[1]["rows"], allowed, "per_channel", "nearest_centroid")
        self.assertEqual(result["train_samples"], 34)
        self.assertEqual(result["test_samples"], 34)
        self.assertGreaterEqual(result["top1"], 0.99)
        self.assertEqual(len(result["confusion"]), 34)

    def test_contact_model_includes_press(self):
        rounds = apply_qc(make_rounds(), FAKE_OVERRIDES)
        result = evaluate_contact(rounds[0]["rows"], rounds[1]["rows"], "per_channel", "nearest_centroid")
        self.assertEqual(set(result["classes"]), {PRESS, APPROACH, NO_CONTACT})
        self.assertEqual(len(result["confusion"]), 3)
        self.assertIsNotNone(result["approach_to_press_rate"])
        self.assertIsNotNone(result["no_contact_to_press_rate"])
        self.assertGreaterEqual(result["accuracy"], 0.7)
        binary = evaluate_binary_contact(rounds[0]["rows"], rounds[1]["rows"], "per_channel", "nearest_centroid")
        self.assertEqual(set(binary["classes"]), {"CONTACT", "NON_CONTACT"})
        self.assertEqual(len(binary["confusion"]), 2)


if __name__ == "__main__":
    unittest.main()
