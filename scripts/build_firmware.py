#!/usr/bin/env python3
"""Build one board target with its own generated config and build directory.

The old ESP32 target and the new ESP32-S3 target never share a generated
header, FQBN, build directory, or binary output.  This script performs no
serial access and no upload.
"""
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
TARGETS = {
    "esp32": {
        "config": "config/gripper_bench.json",
        "board": "config/board_esp32.json",
        "header": "firmware/gripper_control/generated_config.h",
        "build_dir": "evidence/stage09b26/build_esp32_bench",
        "define": None,
    },
    "s3": {
        "config": "config/gripper_s3.json",
        "board": "config/board_s3.json",
        "header": "firmware/gripper_control/generated_config_s3.h",
        "build_dir": "evidence/stage09b26/build_s3",
        "define": "GRIPPER_BOARD_S3",
    },
}


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_cli():
    candidates = [
        os.environ.get("ARDUINO_CLI"),
        str(ROOT / ".tools/bin/arduino-cli"),
        shutil.which("arduino-cli"),
        "/Applications/Arduino IDE.app/Contents/Resources/app/lib/backend/resources/arduino-cli",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise SystemExit(
        "arduino-cli not found; set ARDUINO_CLI or install arduino-cli 1.x"
    )


def run(cmd, log_path):
    print("+", " ".join(cmd), flush=True)
    proc = subprocess.run(
        cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )
    log_path.write_text("$ " + " ".join(cmd) + "\n\n" + proc.stdout)
    print(proc.stdout, end="", flush=True)
    return proc.returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=sorted(TARGETS))
    parser.add_argument("--build-dir")
    parser.add_argument("--no-clean", action="store_true")
    args = parser.parse_args()
    spec = TARGETS[args.target]
    config_path = ROOT / spec["config"]
    board_path = ROOT / spec["board"]
    header_path = ROOT / spec["header"]
    build_dir = ROOT / (args.build_dir or spec["build_dir"])
    evidence = ROOT / "evidence/stage09b26"
    evidence.mkdir(parents=True, exist_ok=True)
    build_dir.mkdir(parents=True, exist_ok=True)

    board = json.loads(board_path.read_text())
    fqbn = board["fqbn"]
    options = board.get("fqbn_options") or {}
    if options:
        fqbn += ":" + ",".join(f"{key}={value}" for key, value in options.items())

    cli = find_cli()
    generate = [
        sys.executable,
        "scripts/generate_gripper_config.py",
        "--config",
        str(config_path),
        "--output",
        str(header_path),
    ]
    if run(generate, evidence / f"generate_{args.target}.txt") != 0:
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
    if spec["define"]:
        compile_cmd += ["--build-property", f"compiler.cpp.extra_flags=-D{spec['define']}"]
    compile_cmd.append(str(ROOT / "firmware/gripper_control"))
    log_path = evidence / f"build_{args.target}.txt"
    code = run(compile_cmd, log_path)

    artifacts = {}
    for name in (
        "gripper_control.ino.bin",
        "gripper_control.ino.bootloader.bin",
        "gripper_control.ino.partitions.bin",
        "gripper_control.ino.elf",
        "gripper_control.ino.merged.bin",
    ):
        path = build_dir / name
        if path.is_file():
            artifacts[name] = {"path": str(path.relative_to(ROOT)), "size": path.stat().st_size, "sha256": sha256(path)}
    header_copy = evidence / f"generated_config_{args.target}.h"
    header_copy.write_text(header_path.read_text())
    version = subprocess.run(
        [cli, "version"], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    ).stdout.strip()
    metadata = {
        "target": args.target,
        "result": "PASS" if code == 0 and artifacts else "FAIL",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "fqbn": fqbn,
        "fqbn_options": options,
        "board_config": str(board_path.relative_to(ROOT)),
        "runtime_config": str(config_path.relative_to(ROOT)),
        "generated_header": str(header_path.relative_to(ROOT)),
        "generated_header_copy": str(header_copy.relative_to(ROOT)),
        "build_dir": str(build_dir.relative_to(ROOT)),
        "arduino_cli": version,
        "command": compile_cmd,
        "artifacts": artifacts,
    }
    (evidence / f"build_{args.target}.json").write_text(json.dumps(metadata, indent=2) + "\n")
    with open(evidence / f"build_{args.target}_sha256.txt", "w") as handle:
        for name, item in artifacts.items():
            handle.write(f"{item['sha256']}  {item['path']}\n")
    print(json.dumps(metadata, indent=2))
    if code != 0:
        raise SystemExit(code)


if __name__ == "__main__":
    main()
