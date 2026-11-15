#!/usr/bin/env python3
"""Build the V2 four-ADS1220 acquisition firmware (offline, no upload).

Generates the board header from the JSON config, compiles firmware/sensor_fsr2
for the pinned Arduino-ESP32 3.3.2 core and records hashes.  No serial port is
opened and nothing is flashed.

Profiles:
    Current: fsr1 (default), electrodes12, electrodes12_fsr1
    Historical dual-FSR builds: fsr, electrodes12_fsr2

Usage:
    python3 scripts/build_sensor_fsr2_firmware.py --build-dir "$PWD/evidence/fsr2/build_sensor_fsr2"
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
DEFAULT_BOARD = ROOT / "config/board_esp32_tactile.json"
DEFAULT_BUILD = ROOT / "evidence/fsr2/build_sensor_fsr2"
SKETCH = ROOT / "firmware/sensor_fsr2"

PROFILES = {
    "fsr1": {
        "config": ROOT / "config/sensor_esp32_fsr1.json",
        "header": ROOT / "firmware/sensor_fsr2/fsr2_config_fsr1.h",
        "extra_flags": "",
        "sensor_profile": "FSR_ONLY",
    },
    "electrodes12_fsr1": {
        "config": ROOT / "config/sensor_esp32_electrodes12_fsr1.json",
        "header": ROOT / "firmware/sensor_fsr2/fsr2_config_electrodes12_fsr1.h",
        "extra_flags": "-DFSR2_PROFILE_ELECTRODES12_FSR1",
        "sensor_profile": "MATRIX_ELECTRODES_12",
    },
    "fsr": {
        "config": ROOT / "config/sensor_esp32_fsr2.json",
        "header": ROOT / "firmware/sensor_fsr2/fsr2_config.h",
        "extra_flags": "-DFSR2_PROFILE_LEGACY_FSR2",
        "sensor_profile": "FSR_ONLY",
    },
    "electrodes12": {
        "config": ROOT / "config/sensor_esp32_electrodes12.json",
        "header": ROOT / "firmware/sensor_fsr2/fsr2_config_electrodes12.h",
        "extra_flags": "-DFSR2_PROFILE_ELECTRODES12",
        "sensor_profile": "MATRIX_ELECTRODES_12",
    },
    "electrodes12_fsr2": {
        "config": ROOT / "config/sensor_esp32_electrodes12_fsr2.json",
        "header": ROOT / "firmware/sensor_fsr2/fsr2_config_electrodes12_fsr2.h",
        "extra_flags": "-DFSR2_PROFILE_ELECTRODES12_FSR2",
        "sensor_profile": "MATRIX_ELECTRODES_12",
    },
}


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
    parser.add_argument("--profile", choices=sorted(PROFILES), default="fsr1")
    parser.add_argument("--board-config", default=str(DEFAULT_BOARD))
    parser.add_argument("--build-dir", default=str(DEFAULT_BUILD))
    parser.add_argument("--evidence-dir", default=str(ROOT / "evidence/fsr2"),
                        help="directory for compile logs, manifests and hashes")
    parser.add_argument("--no-clean", action="store_true")
    args = parser.parse_args()

    profile = PROFILES[args.profile]
    board = json.loads(Path(args.board_config).read_text())
    fqbn = board["fqbn"]
    options = board.get("fqbn_options") or {}
    if options:
        fqbn += ":" + ",".join("%s=%s" % (key, value) for key, value in options.items())

    build_dir = Path(args.build_dir).resolve()
    build_dir.mkdir(parents=True, exist_ok=True)
    evidence = Path(args.evidence_dir).resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    cli = find_cli()

    generate = [
        sys.executable,
        "scripts/generate_sensor_fsr2_config.py",
        "--config",
        str(profile["config"]),
        "--output",
        str(profile["header"]),
    ]
    if run(generate, evidence / ("generate_%s.txt" % (args.profile,))) != 0:
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
    if profile["extra_flags"]:
        compile_cmd += ["--build-property", "build.extra_flags=" + profile["extra_flags"]]
    if not args.no_clean:
        compile_cmd.append("--clean")
    compile_cmd.append(str(SKETCH))
    code = run(compile_cmd, evidence / ("build_%s.txt" % (args.profile,)))

    artifacts = {}
    for name in (
        "sensor_fsr2.ino.bin",
        "sensor_fsr2.ino.bootloader.bin",
        "sensor_fsr2.ino.partitions.bin",
        "sensor_fsr2.ino.elf",
        "sensor_fsr2.ino.merged.bin",
    ):
        path = build_dir / name
        if path.is_file():
            artifacts[name] = {
                "path": str(path.relative_to(ROOT)),
                "size": path.stat().st_size,
                "sha256": sha256(path),
            }

    version = subprocess.run(
        [cli, "version"], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    ).stdout.strip()
    metadata = {
        "target": "v2_four_ads1220_%s" % (args.profile,),
        "sensor_profile": profile["sensor_profile"],
        "result": "PASS" if code == 0 and artifacts else "FAIL",
        "kind": "OFFLINE_COMPILE_ONLY",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "fqbn": fqbn,
        "board_config": str(Path(args.board_config)),
        "runtime_config": str(profile["config"].relative_to(ROOT)),
        "generated_header": str(profile["header"].relative_to(ROOT)),
        "generated_header_sha256": sha256(profile["header"]),
        "build_dir": str(build_dir.relative_to(ROOT)),
        "arduino_cli": version,
        "command": compile_cmd,
        "artifacts": artifacts,
    }
    (evidence / ("build_sensor_fsr2_%s.json" % (args.profile,))).write_text(
        json.dumps(metadata, indent=2) + "\n"
    )
    with open(evidence / ("build_sensor_fsr2_%s_sha256.txt" % (args.profile,)), "w") as handle:
        for name, item in artifacts.items():
            handle.write("%s  %s\n" % (item["sha256"], item["path"]))
    print(json.dumps({key: metadata[key] for key in ("result", "sensor_profile", "fqbn")}, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
