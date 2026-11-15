#!/usr/bin/env python3
"""Headless SIMULATION demo: record a trial, export CSV, then stop.

Writes only under data/simulated/trials.  This is a software demo, not a real
gripper experiment, and never opens a serial port.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from tactile_gripper.control import build_core
from tactile_gripper.sources import DataSource


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticks", type=int, default=30)
    parser.add_argument("--interval", type=float, default=0.05)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()

    core = build_core(source=DataSource.SIMULATION, root=args.root)
    if core.source is not DataSource.SIMULATION:
        raise SystemExit("demo must be SIMULATION")
    core.connect_gripper()
    core.begin_manual_session()
    core.set_demo_stream(True)
    trial = core.create_trial(
        "Headless SIMULATION demo",
        conditions={
            "object": "demo block",
            "cup_type": "SIMULATION",
            "material": "SIMULATION",
            "water_mass_g": None,
            "grasp_target": "1500 μs",
        },
        notes="Synthetic demo; no real sensor, no real PWM.",
        operator="demo",
    )
    core.start_trial()
    core.request_pwm(core.gripper.pwm_initial_us or 1500)
    for _ in range(max(1, args.ticks)):
        core.tick()
        time.sleep(max(0.0, args.interval))
    core.add_trial_event("MARKER", "headless demo complete", {"source": "SIMULATION"})
    stopped = core.stop_trial("demo complete")
    core.disconnect_gripper()
    print(f"Trial: {stopped['trial_id']}")
    print(f"Directory: {stopped.get('directory')}")
    print(f"Frames: {stopped.get('counts', {}).get('frames', 0)}")
    print("Source: SIMULATION (not a real experiment)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
