#!/usr/bin/env python3
"""Run all offline checks: Python tests, firmware build, host driver simulation,
and the exact SAMPLE JSON builder check.

These are NOT real-hardware results.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evidence/sensor/offline_checks"
PY = sys.executable
STEPS = [
    ("python_unittest", [PY, "-m", "unittest", "discover", "-s", "tools/tactile_acq/tests", "-t", "."]),
    ("matrix_python_unittest", [PY, "-m", "unittest", "discover", "-s", "tools/tactile_matrix/tests", "-t", "."]),
    ("experiment_python_unittest", [PY, "-m", "unittest", "discover", "-s", "tools/tactile_experiment/tests", "-t", "."]),
    ("cup_python_unittest", [PY, "-m", "unittest", "discover", "-s", "tools/cup_grasp/tests", "-t", "."]),
    ("firmware_build", [PY, "scripts/build_sensor_firmware.py"]),
    ("matrix_firmware_build", [PY, "scripts/build_sensor_matrix_firmware.py"]),
    ("sensor_diag_build", [PY, "scripts/build_sensor_diag_firmware.py"]),
    ("host_ads1220_driver", [PY, "scripts/run_host_tests.py"]),
    ("frame_builder", [PY, "scripts/check_frame_builder.py"]),
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    for name, command in STEPS:
        print("\n=== {} ===".format(name), flush=True)
        proc = subprocess.run(command, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        log_path = OUT / (name + ".log")
        log_path.write_text("$ " + " ".join(command) + "\n\n" + proc.stdout)
        tail = proc.stdout.strip().splitlines()[-3:]
        print("\n".join(tail))
        results.append({"step": name, "returncode": proc.returncode, "result": "PASS" if proc.returncode == 0 else "FAIL", "log": str(log_path)})
    metadata = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "kind": "OFFLINE_ONLY_NOT_HARDWARE",
        "result": "PASS" if all(item["returncode"] == 0 for item in results) else "FAIL",
        "steps": results,
    }
    (OUT / "summary.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print("\nOFFLINE CHECKS {}".format(metadata["result"]))
    return 0 if metadata["result"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
