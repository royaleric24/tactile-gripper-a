#!/usr/bin/env python3
"""Cup-grasp trial entry point.

Safe defaults:
- `--simulate` runs a clearly-labelled SIMULATED fixed/feedback trial; no hardware.
- `--record-only` records real tactile frames only; no gripper command/motion.
- `--real` checks the S3 calibration gate and refuses if uncalibrated (current state).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.cup_grasp.model import ConfigurationError, load_config  # noqa: E402
from tools.cup_grasp.session import run_real_tactile_only, run_simulated  # noqa: E402

DEFAULT_SIM = ROOT / "config/cup_grasp.simulated.json"
DEFAULT_TEMPLATE = ROOT / "config/cup_grasp.template.json"
S3_CONFIG = ROOT / "config/gripper_s3.json"


def print_blocked_real() -> int:
    from src.gripper_a.gripper_controller import GripperController
    config = json.loads(S3_CONFIG.read_text())
    controller = GripperController(config=config, dry_run=False, hardware_permission=False)
    if not controller.calibrated():
        print("BLOCKED_GRIPPER_UNCALIBRATED", file=sys.stderr)
        print("S3 config has hardware_enabled={} calibration_state={} safe_min_us={} safe_max_us={} initial_pulse_us={}".format(
            config.get("hardware_enabled"), config.get("calibration_state"),
            config.get("safe_min_us"), config.get("safe_max_us"), config.get("initial_pulse_us")), file=sys.stderr)
        print("Provide a user-verified S3 configuration and explicit motion authorization before running real fixed/feedback mode.", file=sys.stderr)
        return 2
    print("REAL_GRIPPER_MODE_READY_NOT_ENABLED: full live arm/set-pulse integration requires a separate authorized run.", file=sys.stderr)
    return 2


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--simulate", action="store_true")
    parser.add_argument("--record-only", action="store_true")
    parser.add_argument("--real", action="store_true")
    parser.add_argument("--mode", choices=["fixed", "feedback"], default="fixed")
    parser.add_argument("--duration", type=float, default=6.0)
    parser.add_argument("--config", default=None)
    parser.add_argument("--tactile-port", default=None)
    parser.add_argument("--baud", type=int, default=921600)
    args = parser.parse_args(argv)
    if args.real:
        return print_blocked_real()
    if args.simulate:
        try:
            result = run_simulated(args.mode, Path(args.config) if args.config else DEFAULT_SIM, args.duration)
        except ConfigurationError as exc:
            print("SIMULATED TRIAL BLOCKED: {}".format(exc), file=sys.stderr)
            return 2
        print(json.dumps({"trial_id": result["trial_id"], "dir": result["dir"], "metrics": result["metrics"]}, indent=2))
        return 0
    if args.record_only:
        if not args.tactile_port:
            print("--record-only requires --tactile-port", file=sys.stderr)
            return 2
        try:
            result = run_real_tactile_only(Path(args.config) if args.config else DEFAULT_TEMPLATE,
                                           args.tactile_port, args.duration, args.baud)
        except Exception as exc:
            print("RECORD-ONLY FAILED: {}".format(exc), file=sys.stderr)
            return 2
        print(json.dumps({"trial_id": result["trial_id"], "dir": result["dir"], "metrics": result["metrics"]}, indent=2))
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
