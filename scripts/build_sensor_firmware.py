#!/usr/bin/env python3
"""Build the tactile ADS1220 firmware for the old ESP32 only.

This script generates the board header, compiles `firmware/sensor` with the
pinned Arduino-ESP32 3.3.2 core, records SHA-256 hashes and performs no serial
access or upload.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config/sensor_esp32.json"
DEFAULT_BOARD = ROOT / "config/board_esp32_tactile.json"
DEFAULT_BUILD = ROOT / "evidence/sensor/build_sensor"
HEADER = ROOT / "firmware/sensor/generated_config.h"
SKETCH = ROOT / "firmware/sensor"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_cli() -> str:
    candidates = [
        os.environ.get("ARDUINO_CLI"),
        str(ROOT / ".tools/bin/arduino-cli"),
        shutil.which("arduino-cli"),
        "/Applications/Arduino IDE.app/Contents/Resources/app/lib/backend/resources/arduino-cli",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise SystemExit("arduino-cli not found; set ARDUINO_CLI")


def run(cmd: list[str], log_path: Path) -> int:
    print("+", " ".join(cmd), flush=True)
    proc = subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    log_path.write_text("$ " + " ".join(cmd) + "\n\n" + proc.stdout)
    print(proc.stdout, end="", flush=True)
    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--board-config", default=str(DEFAULT_BOARD))
    parser.add_argument("--build-dir", default=str(DEFAULT_BUILD))
    parser.add_argument("--no-clean", action="store_true")
    args = parser.parse_args()

    board = json.loads(Path(args.board_config).read_text())
    fqbn = board["fqbn"]
    options = board.get("fqbn_options") or {}
    if options:
        fqbn += ":" + ",".join(f"{key}={value}" for key, value in options.items())

    build_dir = Path(args.build_dir)
    build_dir.mkdir(parents=True, exist_ok=True)
    evidence = ROOT / "evidence/sensor"
    evidence.mkdir(parents=True, exist_ok=True)
    cli = find_cli()

    generate = [
        sys.executable,
        "scripts/generate_sensor_config.py",
        "--config",
        str(Path(args.config)),
        "--output",
        str(HEADER),
    ]
    if run(generate, evidence / "generate_sensor_config.txt") != 0:
        raise SystemExit("config generation failed")

    compile_cmd = [
        cli,
        "--config-file",
        str(ROOT / ".tools/arduino-cli.yaml"),
        "compile",
        "--fqbn",
        fqbn,
        "--build-path",
        str(build_dir),
        "--warnings",
        "default",
    ]
    if not args.no_clean:
        compile_cmd.append("--clean")
    compile_cmd.append(str(SKETCH))
    code = run(compile_cmd, evidence / "build_sensor.txt")

    artifacts = {}
    for name in (
        "sensor.ino.bin",
        "sensor.ino.bootloader.bin",
        "sensor.ino.partitions.bin",
        "sensor.ino.elf",
        "sensor.ino.merged.bin",
    ):
        path = build_dir / name
        if path.is_file():
            artifacts[name] = {
                "path": str(path.relative_to(ROOT)),
                "size": path.stat().st_size,
                "sha256": sha256(path),
            }
    header_copy = evidence / "generated_config_sensor.h"
    header_copy.write_text(HEADER.read_text())
    version = subprocess.run(
        [cli, "version"], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    ).stdout.strip()
    metadata = {
        "target": "old_esp32_only",
        "result": "PASS" if code == 0 and artifacts else "FAIL",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "fqbn": fqbn,
        "board_config": str(Path(args.board_config)),
        "runtime_config": str(Path(args.config)),
        "generated_header": str(HEADER.relative_to(ROOT)),
        "build_dir": str(build_dir.relative_to(ROOT)),
        "arduino_cli": version,
        "command": compile_cmd,
        "artifacts": artifacts,
    }
    (evidence / "build_sensor.json").write_text(json.dumps(metadata, indent=2) + "\n")
    with open(evidence / "build_sensor_sha256.txt", "w") as handle:
        for name, item in artifacts.items():
            handle.write(f"{item['sha256']}  {item['path']}\n")
    print(json.dumps(metadata, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
