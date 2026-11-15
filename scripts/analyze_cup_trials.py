#!/usr/bin/env python3
"""Summarize cup-grasp trials in a directory (real vs simulated separated)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.cup_grasp.analyze import summarize_root, write_summary  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root")
    args = parser.parse_args()
    root = Path(args.root)
    if not root.is_dir():
        print("not a directory: {}".format(root), file=sys.stderr)
        return 2
    analysis = summarize_root(root)
    write_summary(root, analysis)
    print(json.dumps({k: v for k, v in analysis.items() if k != "trials"}, indent=2))
    print("written: {} {}".format(root / "SUMMARY.csv", root / "REPORT.md"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
