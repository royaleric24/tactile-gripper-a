#!/usr/bin/env python3
"""Compile the offline 6x6 matrix prototype.  This script never opens serial and
never uploads firmware."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKETCH = ROOT / "firmware/sensor_matrix"
OUT = ROOT / "evidence/sensor_matrix"
BUILD = OUT / "build_matrix"
CLI = ROOT / ".tools/bin/arduino-cli"
CONFIG = ROOT / ".tools/arduino-cli.yaml"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    if not CLI.is_file():
        raise SystemExit("arduino-cli not found: {}".format(CLI))
    command = [
        str(CLI),
        "--config-file", str(CONFIG),
        "compile",
        "--fqbn", "esp32:esp32:nodemcu-32s",
        "--build-path", str(BUILD),
        "--warnings", "default",
        str(SKETCH),
    ]
    proc = subprocess.run(command, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (OUT / "build_matrix.txt").write_text("$ " + " ".join(command) + "\n\n" + proc.stdout)
    print(proc.stdout, end="")
    if proc.returncode != 0:
        return 1
    artifacts = {}
    for name in ("sensor_matrix.ino.bin", "sensor_matrix.ino.elf"):
        path = BUILD / name
        if path.is_file():
            artifacts[name] = {"path": str(path), "size": path.stat().st_size, "sha256": sha256(path)}
    metadata = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "target": "old_esp32_matrix_prototype",
        "result": "PASS",
        "note": "OFFLINE BUILD ONLY - NOT FLASHED",
        "fqbn": "esp32:esp32:nodemcu-32s",
        "sketch": str(SKETCH),
        "command": command,
        "artifacts": artifacts,
        "source_sha256": {
            str(path.relative_to(ROOT)): sha256(path)
            for path in sorted(SKETCH.glob("*"))
            if path.is_file()
        },
    }
    (OUT / "build_matrix.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print("\nMATRIX BUILD PASS (not flashed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
