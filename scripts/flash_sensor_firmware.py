#!/usr/bin/env python3
"""Back up and flash the tactile firmware to the OLD ESP32 only.

Safety sequence:
1. enumerate the port and read the chip family/MAC with esptool (read-only);
2. refuse anything that is not the configured old ESP32;
3. read and hash the complete 4 MB flash into evidence/;
4. write only the application partition at 0x10000 and verify it.

The ESP32-S3 is never accepted.  The stable old-ESP32 gripper firmware is
preserved by the full-flash backup and by the existing evidence copies.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / "config/board_esp32_tactile.json"
BUILD = ROOT / "evidence/sensor/build_sensor"
APP_BIN = BUILD / "sensor.ino.bin"
APP_OFFSET = 0x10000
FLASH_SIZE = 0x400000


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_esptool() -> str:
    candidates = [
        os.environ.get("ESPTOOL"),
        str(ROOT / ".tools/bin/esptool"),
        "/home/example/Developer/research/tactile-gripper-a/.tools/arduino-data/packages/esp32/tools/esptool_py/5.1.0/esptool",
        shutil.which("esptool"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    core_root = Path("/home/example/Developer/research/tactile-gripper-a/.tools/arduino-data/packages/esp32/tools/esptool_py")
    if core_root.is_dir():
        for path in sorted(core_root.glob("*/esptool"), reverse=True):
            if path.is_file():
                return str(path)
    raise SystemExit("esptool not found; set ESPTOOL")


def run(cmd: list[str], log_path: Path | None = None) -> tuple[int, str]:
    print("+", " ".join(cmd), flush=True)
    proc = subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = proc.stdout
    print(output, end="", flush=True)
    if log_path is not None:
        log_path.write_text("$ " + " ".join(cmd) + "\n\n" + output)
    return proc.returncode, output


def parse_identity(output: str) -> tuple[str, str]:
    chip_match = re.search(r"Chip is (ESP32[^\s(]*)", output)
    mac_match = re.search(r"MAC:\s*([0-9A-Fa-f:]{17})", output)
    if not chip_match or not mac_match:
        raise SystemExit("could not parse chip/MAC from esptool output")
    return chip_match.group(1), mac_match.group(1).lower()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--baud", type=int, default=460800)
    parser.add_argument("--authorize-write", action="store_true", help="required: explicitly allow flashing the old ESP32")
    parser.add_argument("--backup-dir", default=str(ROOT / "evidence/sensor/backups"))
    parser.add_argument("--app-bin", default=str(APP_BIN))
    parser.add_argument("--skip-verify", action="store_true")
    args = parser.parse_args()
    if not args.authorize_write:
        raise SystemExit("refusing to write flash without --authorize-write")

    board = json.loads(BOARD.read_text())
    expected_mac = board["expected_mac"].lower()
    app = Path(args.app_bin)
    if not app.is_file():
        raise SystemExit("application binary not found: {} (run scripts/build_sensor_firmware.py)".format(app))
    build_meta_path = ROOT / "evidence/sensor/build_sensor.json"
    if build_meta_path.is_file():
        build_meta = json.loads(build_meta_path.read_text())
        if build_meta.get("target") != "old_esp32_only":
            raise SystemExit("build metadata target is not old_esp32_only")
        if not str(build_meta.get("fqbn", "")).startswith("esp32:esp32:nodemcu-32s"):
            raise SystemExit("build metadata FQBN is not nodemcu-32s")
    esptool = find_esptool()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evidence = ROOT / "evidence/sensor"
    evidence.mkdir(parents=True, exist_ok=True)
    log_path = evidence / "flash_{}.txt".format(stamp)

    # 1. Read-only identity check.
    code, output = run([esptool, "--port", args.port, "--baud", str(args.baud), "chip-id"], log_path)
    if code != 0:
        raise SystemExit("chip-id failed; nothing was written")
    chip, mac = parse_identity(output)
    if "S3" in chip.upper() or not chip.upper().startswith("ESP32"):
        raise SystemExit("refusing device: chip is {}, not the old ESP32".format(chip))
    if mac != expected_mac:
        raise SystemExit(
            "refusing device: MAC {} does not match expected old ESP32 {}".format(mac, expected_mac)
        )
    print("identity OK: chip={} mac={}".format(chip, mac))

    # 2. Full-flash backup before any write.
    backup_dir = Path(args.backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / "old_esp32_fullflash_{}_{}.bin".format(stamp, mac.replace(":", ""))
    code, _ = run(
        [esptool, "--port", args.port, "--baud", str(args.baud), "read-flash", "0", hex(FLASH_SIZE), str(backup_path)],
        log_path,
    )
    if code != 0 or not backup_path.is_file():
        raise SystemExit("flash backup failed; refusing to write")
    if backup_path.stat().st_size != FLASH_SIZE:
        raise SystemExit("backup size is {} bytes, expected {}".format(backup_path.stat().st_size, FLASH_SIZE))
    backup_sha = sha256(backup_path)
    backup_meta = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "port": args.port,
        "chip": chip,
        "mac": mac,
        "size": backup_path.stat().st_size,
        "sha256": backup_sha,
        "path": str(backup_path),
        "note": "Full 4 MB flash read before writing the tactile application.",
    }
    (backup_dir / "old_esp32_fullflash_{}_{}.json".format(stamp, mac.replace(":", ""))).write_text(
        json.dumps(backup_meta, indent=2) + "\n"
    )
    print("backup OK: {} sha256={}".format(backup_path, backup_sha))

    # 3. Write only the application partition, then verify.
    app_sha = sha256(app)
    code, _ = run(
        [esptool, "--port", args.port, "--baud", str(args.baud), "write-flash", hex(APP_OFFSET), str(app)],
        log_path,
    )
    if code != 0:
        raise SystemExit("write-flash failed; backup is at {}".format(backup_path))
    if not args.skip_verify:
        code, _ = run(
            [esptool, "--port", args.port, "--baud", str(args.baud), "verify-flash", hex(APP_OFFSET), str(app)],
            log_path,
        )
        if code != 0:
            raise SystemExit("verify-flash failed; backup is at {}".format(backup_path))
    metadata = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "result": "PASS",
        "port": args.port,
        "chip": chip,
        "mac": mac,
        "app_offset": hex(APP_OFFSET),
        "app_bin": str(app),
        "app_size": app.stat().st_size,
        "app_sha256": app_sha,
        "backup": backup_meta,
        "esptool": esptool,
        "verify": not args.skip_verify,
    }
    (evidence / "flash_{}.json".format(stamp)).write_text(json.dumps(metadata, indent=2) + "\n")
    print("\nFLASH PASS")
    print("backup: {}".format(backup_path))
    print("app   : {} ({}, sha256 {})".format(app, metadata["app_size"], app_sha))
    print("next  : .venv/bin/python -m tools.tactile_acq identify --port {}".format(args.port))
    return 0


if __name__ == "__main__":
    sys.exit(main())
