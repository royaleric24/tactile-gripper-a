#!/usr/bin/env python3
"""Compile the firmware SAMPLE builder on the host and validate its JSON with
the same strict parser used for the real serial stream."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evidence/sensor/host_test"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    binary = OUT / "test_frame_builder"
    cmd = [
        "g++", "-std=c++17", "-Wall", "-Wextra",
        "-Itools/firmware_sim", "-Ifirmware/sensor",
        "tools/firmware_sim/test_frame_builder.cpp",
        "firmware/sensor/frame_builder.cpp",
        "-o", str(binary),
    ]
    compiled = subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (OUT / "frame_builder_compile.log").write_text(compiled.stdout)
    if compiled.returncode != 0:
        print(compiled.stdout)
        print("FRAME BUILDER COMPILE FAILED")
        return 1
    proc = subprocess.run([str(binary)], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        print(proc.stderr or proc.stdout)
        print("FRAME BUILDER RUN FAILED")
        return 1
    sys.path.insert(0, str(ROOT))
    from tools.tactile_acq.protocol import parse_message

    try:
        frame = parse_message(proc.stdout.encode())
    except Exception as exc:
        print("FRAME BUILDER JSON REJECTED: {}".format(exc))
        print(proc.stdout)
        return 1
    checks = [
        (frame.frame_seq == 42, "frame_seq"),
        (frame.timestamp_us == 1234567, "timestamp_us"),
        (frame.frame_period_us == 21400, "frame_period_us"),
        (frame.raw_adc[0] == 1234, "raw_adc[0]"),
        (frame.raw_adc[1] == -567, "negative raw_adc[1]"),
        (frame.raw_adc[3] == 8388607, "full-scale raw_adc[3]"),
        (frame.raw_adc[4] is None and not frame.valid[4], "invalid null channel"),
        (frame.channel_flags[4] == 0x20, "NO_DATA flag"),
        (frame.adc_status[2].state == "NO_RESPONSE", "ADC3 status"),
        (abs(frame.effective_frame_rate_hz - 46.73) < 1e-9, "frame rate"),
    ]
    failed = [name for ok, name in checks if not ok]
    print(proc.stdout.strip())
    if failed:
        print("FRAME BUILDER CHECK FAILED: {}".format(", ".join(failed)))
        return 1
    print("FRAME BUILDER CHECK PASSED")
    metadata = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "kind": "HOST_SIMULATION_NOT_HARDWARE",
        "result": "PASS",
        "line_bytes": len(proc.stdout),
        "binary_sha256": sha256(binary),
        "sources": {
            name: sha256(ROOT / name)
            for name in ("tools/firmware_sim/test_frame_builder.cpp", "firmware/sensor/frame_builder.cpp", "firmware/sensor/frame_builder.h", "firmware/sensor/json_writer.h")
        },
    }
    (OUT / "frame_builder.json").write_text(json.dumps(metadata, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
