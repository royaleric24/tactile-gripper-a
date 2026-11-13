#!/usr/bin/env python3
"""Compile the fixed ADC2-AIN1 diagnostic firmware. Never opens serial or flashes."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKETCH = ROOT / "firmware/sensor_diag_ain1"
OUT = ROOT / "evidence/sensor/build_sensor_diag_ain1"
BUILD = OUT / "build"
CLI = ROOT / ".tools/bin/arduino-cli"
CONFIG = ROOT / ".tools/arduino-cli.yaml"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    if not CLI.is_file():
        raise SystemExit("arduino-cli not found: {}".format(CLI))
    command = [str(CLI), "--config-file", str(CONFIG), "compile",
               "--fqbn", "esp32:esp32:nodemcu-32s", "--build-path", str(BUILD),
               "--warnings", "default", str(SKETCH)]
    proc = subprocess.run(command, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (OUT / "build.txt").write_text("$ " + " ".join(command) + "\n\n" + proc.stdout)
    print(proc.stdout, end="")
    if proc.returncode != 0:
        return 1
    artifacts = {}
    for name in ("sensor_diag_ain1.ino.bin", "sensor_diag_ain1.ino.elf"):
        path = BUILD / name
        if path.is_file():
            artifacts[name] = {"path": str(path), "size": path.stat().st_size, "sha256": sha256(path)}
    metadata = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "target": "old_esp32_fixed_ADC2_AIN1_diagnostic",
        "version": "tactile-sense-diag-ain1-0.1.2",
        "result": "PASS",
        "note": "OFFLINE BUILD ONLY - NOT FLASHED",
        "fqbn": "esp32:esp32:nodemcu-32s",
        "sketch": str(SKETCH),
        "command": command,
        "artifacts": artifacts,
        "source_sha256": {str(path.relative_to(ROOT)): sha256(path)
                          for path in sorted(SKETCH.glob("*")) if path.is_file()},
    }
    (OUT / "build.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print("\nDIAG BUILD PASS (not flashed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
