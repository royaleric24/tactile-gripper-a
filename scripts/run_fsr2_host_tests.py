#!/usr/bin/env python3
"""Compile and run the V2 FSR firmware host tests.

These tests exercise the bit-bang driver, the sampler and the JSON builders
against tools/fsr2_sim, a deterministic simulation of four ADS1220 devices.
They produce HOST_SIMULATION evidence only: no board is attached, no divider is
measured and nothing here proves the wiring.

Usage:
    python3 scripts/run_fsr2_host_tests.py [--evidence-dir DIR]
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE = ROOT / "evidence" / "fsr2" / "host_tests"

SIM_SOURCES = [
    "tools/fsr2_sim/sim_fsr2.cpp",
    "firmware/sensor_fsr2/ads1220_multi.cpp",
    "firmware/sensor_fsr2/fsr2.cpp",
    "firmware/sensor_fsr2/frame_builder_fsr2.cpp",
    "firmware/sensor_fsr2/sampler_fsr2.cpp",
]

TESTS = [
    ("test_fsr2_driver", "tools/fsr2_sim/test_fsr2_driver.cpp", []),
    ("test_fsr2_sampler", "tools/fsr2_sim/test_fsr2_sampler.cpp", []),
    ("test_fsr2_sampler_hybrid", "tools/fsr2_sim/test_fsr2_sampler_hybrid.cpp", []),
]

INCLUDE_DIRS = ["tools/firmware_sim", "tools/fsr2_sim", "firmware/sensor_fsr2"]


def find_cxx() -> str:
    for candidate in ("g++", "clang++"):
        path = shutil.which(candidate)
        if path:
            return path
    raise SystemExit("no C++ compiler found (need g++ or clang++)")


def compile_test(cxx: str, source: str, output: Path, log: Path) -> bool:
    command = [cxx, "-std=c++17", "-Wall", "-Wextra"]
    for directory in INCLUDE_DIRS:
        command += ["-I", directory]
    command += [source] + SIM_SOURCES + ["-o", str(output)]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    log.write_text("$ " + " ".join(command) + "\n" + result.stdout + result.stderr)
    if result.returncode != 0:
        print("compile failed: %s" % source)
        print(result.stderr)
        return False
    if result.stderr.strip():
        print("compiler warnings for %s:\n%s" % (source, result.stderr))
    return True


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", default=str(DEFAULT_EVIDENCE))
    args = parser.parse_args(argv)

    evidence = Path(args.evidence_dir).resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    cxx = find_cxx()
    print("compiler:", cxx)

    summary = {"kind": "HOST_SIMULATION_NOT_HARDWARE", "compiler": cxx, "tests": []}
    failed = 0
    for name, source, extra_args in TESTS:
        binary = evidence / name
        log = evidence / (name + ".compile.log")
        if not compile_test(cxx, source, binary, log):
            summary["tests"].append({"name": name, "status": "COMPILE_FAILED"})
            failed += 1
            continue
        result = subprocess.run(
            [str(binary)] + extra_args, cwd=ROOT, capture_output=True, text=True
        )
        (evidence / (name + ".log")).write_text(result.stdout + result.stderr)
        passed = result.returncode == 0
        print("%s: %s" % (name, "PASS" if passed else "FAIL"))
        summary["tests"].append(
            {
                "name": name,
                "status": "PASS" if passed else "FAIL",
                "exit_code": result.returncode,
                "assertions": result.stdout.count("PASS "),
                "failures": result.stdout.count("FAIL "),
            }
        )
        if not passed:
            failed += 1
            print(result.stdout[-4000:])

    summary["result"] = "PASS" if failed == 0 else "FAIL"
    summary["note"] = (
        "Offline host simulation of four ADS1220 devices. It validates driver timing, "
        "decode, sampler validity semantics and JSON framing. It is not hardware evidence."
    )
    (evidence / "host_tests.json").write_text(json.dumps(summary, indent=2) + "\n")
    print("host tests:", summary["result"])
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
