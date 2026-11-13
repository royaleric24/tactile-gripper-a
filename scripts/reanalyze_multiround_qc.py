#!/usr/bin/env python3
"""Re-run the two-round analysis with QC overrides (offline only)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.tactile_experiment.qc_analysis import run_corrected_analysis  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_dir")
    parser.add_argument("--revision-dir", help="new output directory (default: revision_qc_<UTC>)")
    args = parser.parse_args()
    session_dir = Path(args.session_dir)
    revision = Path(args.revision_dir) if args.revision_dir else None
    if revision is not None and revision.exists():
        print("refusing to overwrite revision directory: {}".format(revision), file=sys.stderr)
        return 2
    report = run_corrected_analysis(session_dir, revision)
    print(json.dumps({
        "quality": report["quality"],
        "quality_reasons": report["quality_reasons"],
        "coverage": report["coverage"],
        "best_corrected_point": report["best_corrected_point"],
        "best_contact": {
            k: report["best_contact"].get(k) for k in
            ("model", "feature_set", "accuracy", "balanced_accuracy", "approach_to_press_rate",
             "no_contact_to_press_rate", "test_samples")
        } if report.get("best_contact") else None,
        "revision_dir": report["revision_dir"],
    }, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
