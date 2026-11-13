#!/usr/bin/env python3
"""Re-run preliminary analysis for a multi-round session directory."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.tactile_experiment.multiround_analysis import analyze_session  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_dir")
    args = parser.parse_args()
    path = Path(args.session_dir)
    if not (path / "session.json").is_file():
        print("no session.json in {}".format(path), file=sys.stderr)
        return 2
    report = analyze_session(path)
    print(json.dumps({
        "quality": report["quality"],
        "quality_reasons": report["quality_reasons"],
        "rounds": report["rounds"],
        "repeatability": report["evaluation"]["repeatability"],
        "best": (report.get("best_result") or {}).get("point"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
