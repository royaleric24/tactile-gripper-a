#!/usr/bin/env python3
"""Compile and run the host-side ADS1220 simulation tests.

This validates the bit-bang transaction logic and signed 24-bit assembly against
a deterministic simulated ADS1220.  It is NOT real-hardware evidence.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evidence/sensor/host_test"
SOURCES = [
    "tools/firmware_sim/test_ads1220.cpp",
    "tools/firmware_sim/sim_gpio.cpp",
    "firmware/sensor/ads1220.cpp",
]
INCLUDES = ["-Itools/firmware_sim", "-Ifirmware/sensor"]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    binary = OUT / "test_ads1220"
    compile_cmd = ["g++", "-std=c++17", "-Wall", "-Wextra", *INCLUDES, *SOURCES, "-o", str(binary)]
    print("+", " ".join(compile_cmd))
    compiled = subprocess.run(compile_cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (OUT / "compile.log").write_text(compiled.stdout)
    if compiled.returncode != 0:
        print(compiled.stdout)
        print("HOST TEST COMPILE FAILED")
        return 1
    proc = subprocess.run([str(binary)], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (OUT / "test_ads1220.log").write_text(proc.stdout)
    print(proc.stdout, end="")
    metadata = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "kind": "HOST_SIMULATION_NOT_HARDWARE",
        "result": "PASS" if proc.returncode == 0 else "FAIL",
        "command": compile_cmd,
        "returncode": proc.returncode,
        "sources": {name: sha256(ROOT / name) for name in SOURCES},
        "binary_sha256": sha256(binary),
    }
    (OUT / "host_test.json").write_text(json.dumps(metadata, indent=2) + "\n")
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
