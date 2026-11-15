#!/usr/bin/env python3
"""Capture the real ESP32 FSR_A stream to JSONL for the Dashboard monitor.

This is the *only* process that opens the FSR serial port during a monitored
session.  It writes one JSONL record per serial line, including the host UTC
time and host monotonic clock, so the Dashboard can align the FSR curve with
the pwm_console log without opening the port itself.

The output schema is the one already used by the verified P3-B1 captures:

    {"host_time_utc": "...", "host_monotonic_ns": 123, "direction": "RX",
     "raw": "<wire line>", "message": {...}}

``message`` is present only when the line parsed as JSON; NUL-corrupted or boot
lines are kept as ``raw`` with ``message`` absent, never silently dropped.

Read-only with respect to the gripper: this script never sends PWM.  It does
send the sensor HELLO/STREAM commands that the acquisition firmware expects.

Usage (minimum):
    .venv/bin/python scripts/capture_fsr_live.py \
        --port /dev/cu.usbserial-0001 --authorize \
        --output logs/real/sessions/<session>/fsr/fsr_stream.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "sensor_serial.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_serial_config(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        payload = {}
    section = payload.get("sensor_serial") if isinstance(payload, dict) else None
    return section if isinstance(section, dict) else {}


def write_record(handle, direction: str, raw: str, message: dict | None, marker: str | None = None) -> None:
    record = {
        "host_time_utc": utc_now(),
        "host_monotonic_ns": time.monotonic_ns(),
        "direction": direction,
    }
    if raw:
        record["raw"] = raw
    if message is not None:
        record["message"] = message
    if marker is not None:
        record["marker"] = marker
    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    handle.flush()


def send(handle, ser, command: dict) -> None:
    text = json.dumps(command, separators=(",", ":"))
    ser.write((text + "\n").encode("utf-8"))
    ser.flush()
    write_record(handle, "TX", text, command)


def drain(handle, ser, seconds: float, stats: dict) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        line = ser.readline()
        if not line:
            continue
        if b"\x00" in line:
            stats["nul_lines"] += 1
        text = line.decode("utf-8", errors="replace").rstrip("\r\n")
        if not text:
            continue
        try:
            message = json.loads(text)
        except ValueError:
            message = None
        if isinstance(message, dict):
            kind = str(message.get("type") or "UNKNOWN")
            stats["message_types"][kind] = stats["message_types"].get(kind, 0) + 1
            seq = message.get("frame_seq")
            if type(seq) is int:
                if stats["first_seq"] is None:
                    stats["first_seq"] = seq
                stats["last_seq"] = seq
                stats["samples"] += 1
            if kind == "HELLO":
                stats["hello"] = {
                    "device_id": message.get("device_id"),
                    "boot_id": message.get("boot_id"),
                    "firmware_version": message.get("firmware_version"),
                    "sensor_profile": message.get("sensor_profile"),
                }
            if kind == "ERROR":
                stats["device_errors"] += 1
        else:
            stats["unparsed_lines"] += 1
        write_record(handle, "RX", text, message if isinstance(message, dict) else None)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", required=True, help="Mac FSR serial port, e.g. /dev/cu.usbserial-0001")
    parser.add_argument("--output", type=Path, required=True, help="JSONL stream path (fsr_stream.jsonl)")
    parser.add_argument("--duration", type=float, default=0.0, help="seconds; 0 = until Ctrl+C")
    parser.add_argument("--label", default="", help="operator label stored in the summary")
    parser.add_argument("--authorize", action="store_true", help="explicitly authorize opening the FSR serial port")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="serial settings JSON")
    parser.add_argument("--baud", type=int, help="override the configured baudrate")
    parser.add_argument("--boot-wait", type=float, help="seconds to wait after opening the port before HELLO")
    args = parser.parse_args()

    if not args.authorize:
        parser.error("--authorize is required to open the FSR serial port")
    if not args.port.startswith("/dev/cu."):
        parser.error("explicit Mac call-out port required (/dev/cu.*)")
    if args.duration < 0:
        parser.error("--duration must be >= 0")

    settings = load_serial_config(args.config)
    baudrate = int(args.baud or settings.get("baudrate", 921600))
    boot_wait = args.boot_wait if args.boot_wait is not None else float(settings.get("boot_wait_s", 2.5))
    boot_wait = max(0.0, min(10.0, boot_wait))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        parser.error(f"output already exists (refusing to append): {args.output}")
    summary_path = args.output.with_suffix(".summary.json")

    import serial  # local import: no hardware import at module load

    stats: dict = {
        "message_types": {},
        "samples": 0,
        "nul_lines": 0,
        "unparsed_lines": 0,
        "device_errors": 0,
        "first_seq": None,
        "last_seq": None,
        "hello": None,
    }
    started_utc = utc_now()
    started = time.monotonic()
    status = "completed"
    with args.output.open("x", encoding="utf-8") as handle:
        try:
            ser = serial.Serial(
                port=args.port,
                baudrate=baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.1,
                write_timeout=1.0,
                xonxoff=False,
                rtscts=False,
                dsrdtr=False,
                exclusive=True,
            )
        except Exception as exc:
            print(f"FSR port open failed: {exc}", file=sys.stderr, flush=True)
            status = "open_failed"
            summary_path.write_text(
                json.dumps({"status": status, "port": args.port, "error": str(exc)}, indent=2) + "\n"
            )
            return 2
        try:
            ser.dtr = False
            ser.rts = False
            ser.reset_input_buffer()
            write_record(handle, "MARKER", "", None, marker="CAPTURE_START")
            if boot_wait:
                # Opening the CP2102 can reset the ESP32; give it time to boot
                # before asking for HELLO so the handshake is not lost.
                time.sleep(boot_wait)
            send(handle, ser, {"cmd": "HELLO", "request_id": "monitor-hello"})
            drain(handle, ser, 1.5, stats)
            send(handle, ser, {"cmd": "STREAM", "value": "start", "request_id": "monitor-stream-start"})
            deadline = started + args.duration if args.duration > 0 else None
            while deadline is None or time.monotonic() < deadline:
                drain(handle, ser, 0.25, stats)
            send(handle, ser, {"cmd": "STREAM", "value": "stop", "request_id": "monitor-stream-stop"})
            drain(handle, ser, 1.0, stats)
            if stats.get("hello") is None:
                print("WARNING: no HELLO parsed; frames without channel config will be rejected.", flush=True)
        except KeyboardInterrupt:
            status = "interrupted"
            try:
                send(handle, ser, {"cmd": "STREAM", "value": "stop", "request_id": "monitor-stream-stop"})
                drain(handle, ser, 0.5, stats)
            except Exception:
                pass
        finally:
            try:
                ser.close()
            except Exception:
                pass
            write_record(handle, "MARKER", "", None, marker="CAPTURE_END")

    summary = {
        "status": status,
        "label": args.label,
        "port": args.port,
        "baudrate": baudrate,
        "output": str(args.output),
        "started_utc": started_utc,
        "finished_utc": utc_now(),
        "duration_s": round(time.monotonic() - started, 3),
        "samples": stats["samples"],
        "first_seq": stats["first_seq"],
        "last_seq": stats["last_seq"],
        "message_types": stats["message_types"],
        "nul_lines": stats["nul_lines"],
        "unparsed_lines": stats["unparsed_lines"],
        "device_errors": stats["device_errors"],
        "hello": stats["hello"],
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return 0 if status == "completed" else 130


if __name__ == "__main__":
    raise SystemExit(main())
